"""
RAGE TRACKER - Monitor de micrófono  [NUEVO]
============================================
AudioMonitor mide el volumen del micrófono en tiempo real y detecta "gritos".

Lo diseñé con dos backends: sounddevice como principal y PyAudio como fallback.
Si ninguno está instalado, el monitor queda en modo "no disponible" sin romper
la app — simplemente se desactiva la detección de gritos y seguimos con emociones.

Expone `level` (0-100) para el medidor en vivo y `get_summary()` con las
métricas de la sesión (scream_count, scream_peak_db, scream_total_seconds,
mic_device_name), pensadas para fusionarse en el resumen del CSV.

Sin estado global: cada sesión crea su propia instancia (start/stop).
También funciona como context manager (`with AudioMonitor(...) as am:`).

Dependencias (requirements.txt):
    sounddevice==0.4.7          # backend principal
    # PyAudio==0.2.14           # opcional, solo si no usas sounddevice
Nota: sounddevice/PyAudio necesitan PortAudio en el sistema
(Windows trae binarios en la rueda; en Linux: `sudo apt install libportaudio2`).
"""

from __future__ import annotations

import math
import threading
import time
from typing import List, Optional, Tuple

import numpy as np


# -----------------------------------------------------------------------------
# Detección de backend (perezosa y tolerante a fallos)
# -----------------------------------------------------------------------------
# Cargo los backends de audio de forma perezosa: primero sounddevice,
# después PyAudio. Si fallan los dos, la app arranca igual pero sin micrófono.
_sd = None
_pyaudio = None
try:
    import sounddevice as _sd  # type: ignore
except Exception:  # pragma: no cover - depende del entorno
    _sd = None

if _sd is None:
    try:
        import pyaudio as _pyaudio  # type: ignore
    except Exception:  # pragma: no cover
        _pyaudio = None


def audio_available() -> bool:
    """True si hay algún backend de audio utilizable."""
    return _sd is not None or _pyaudio is not None


def backend_name() -> str:
    if _sd is not None:
        return "sounddevice"
    if _pyaudio is not None:
        return "pyaudio"
    return "none"


def diagnose() -> str:
    """Devuelve un diagnóstico legible del estado del subsistema de audio.

    Pensado para que el launcher pueda mostrar un mensaje útil al usuario
    en lugar de un silencio confuso cuando no hay micrófonos."""
    if not audio_available():
        return (
            "No hay backend de audio instalado. Instalá 'sounddevice' con:\n"
            "    pip install sounddevice==0.4.7\n"
            "o 'PyAudio' como alternativa:\n"
            "    pip install PyAudio"
        )
    devices = AudioMonitor.list_input_devices()
    if not devices:
        return (
            f"Backend {backend_name()} activo, pero no se encontraron\n"
            "dispositivos de entrada. Verificá que tu micrófono esté conectado\n"
            "y que Windows tenga permisos de micrófono habilitados:\n"
            "Configuración → Privacidad → Micrófono"
        )
    return f"Backend {backend_name()} · {len(devices)} dispositivo(s) de entrada"


# -----------------------------------------------------------------------------
# Utilidades de conversión RMS -> nivel 0..100 / dBFS
# -----------------------------------------------------------------------------
# El piso de ruido (_DB_FLOOR) lo fijé en -60 dBFS porque por debajo de eso
# cualquier micrófono está prácticamente en silencio. Con esto mapeo el rango
# [-60, 0] dBFS → [0, 100]% de forma lineal, que es lo que espera ver el VU meter.
_DB_FLOOR = -60.0
_EPS = 1e-7


def _rms_to_db(rms: float) -> float:
    """RMS (0..1 sobre señal normalizada) -> dBFS aproximado."""
    return 20.0 * math.log10(max(rms, _EPS))


def _db_to_pct(db: float) -> float:
    """dBFS -> porcentaje 0..100 (lineal entre _DB_FLOOR y 0 dB)."""
    pct = (db - _DB_FLOOR) / (0.0 - _DB_FLOOR) * 100.0
    return max(0.0, min(100.0, pct))


# -----------------------------------------------------------------------------
# AudioMonitor
# -----------------------------------------------------------------------------
class AudioMonitor:
    """Monitoriza un micrófono y detecta eventos de grito.

    Args:
        device_index: índice del dispositivo de entrada. None = predeterminado.
        threshold_pct: umbral de "grito" en % de volumen (0..100). Por defecto 80.
        samplerate: muestreo en Hz. None usa el del dispositivo.
        smoothing: suavizado exponencial del nivel mostrado (0..1, mayor = más estable).
    """

    # Decidí 0.3s como mínimo para considerar un grito: menos que eso suele ser
    # un golpe en la mesa o un pico de audio, no un grito real.
    MIN_SCREAM_S = 0.3
    BLOCK_SIZE = 1024    # frames por bloque de captura

    def __init__(
        self,
        device_index: Optional[int] = None,
        threshold_pct: float = 80.0,
        samplerate: Optional[int] = None,
        smoothing: float = 0.4,
    ):
        self.device_index = device_index
        self.threshold_pct = float(max(0.0, min(100.0, threshold_pct)))
        self.smoothing = float(max(0.0, min(0.95, smoothing)))
        self.samplerate = samplerate

        self.device_name = self._resolve_device_name(device_index)

        # Estado en vivo (lectura simple desde el hilo de la GUI/cámara)
        self.level: float = 0.0          # 0..100 suavizado
        self.is_screaming: bool = False  # True mientras supera el umbral (confirmado)

        # Métricas acumuladas (protegidas por lock al escribir desde el callback)
        # El lock es necesario porque el callback de audio corre en un hilo
        # distinto al hilo principal que lee level/is_screaming/get_summary.
        self._lock = threading.Lock()
        self._scream_count = 0
        self._scream_total_seconds = 0.0
        self._peak_db = _DB_FLOOR
        self._pending_above_s = 0.0      # tiempo acumulado por encima sin confirmar
        self._in_scream = False

        # Recursos del backend
        self._running = False
        self._sd_stream = None
        self._pa = None
        self._pa_stream = None
        self._pa_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Enumeración de dispositivos
    # ------------------------------------------------------------------ #
    @staticmethod
    def list_input_devices() -> List[Tuple[int, str]]:
        """Devuelve [(index, nombre), ...] de los micrófonos de entrada."""
        devices: List[Tuple[int, str]] = []
        if _sd is not None:
            try:
                for idx, dev in enumerate(_sd.query_devices()):
                    if dev.get("max_input_channels", 0) > 0:
                        devices.append((idx, dev.get("name", f"Dispositivo {idx}")))
            except Exception as exc:
                # Si sounddevice está instalado pero PortAudio falla (drivers,
                # permisos, DLLs faltantes), al menos aviso en lugar de silencio.
                print(f"[!] Error al consultar dispositivos de audio (sounddevice): {exc}")
        elif _pyaudio is not None:
            try:
                pa = _pyaudio.PyAudio()
                try:
                    for idx in range(pa.get_device_count()):
                        info = pa.get_device_info_by_index(idx)
                        if int(info.get("maxInputChannels", 0)) > 0:
                            devices.append((idx, str(info.get("name", f"Dispositivo {idx}"))))
                finally:
                    pa.terminate()
            except Exception as exc:
                print(f"[!] Error al consultar dispositivos de audio (PyAudio): {exc}")
        return devices

    @staticmethod
    def default_input_device() -> Optional[int]:
        """Índice del micrófono por defecto, o None si no se puede determinar."""
        if _sd is not None:
            try:
                default = _sd.default.device
                idx = default[0] if isinstance(default, (list, tuple)) else default
                return int(idx) if idx is not None and idx >= 0 else None
            except Exception:
                return None
        if _pyaudio is not None:
            try:
                pa = _pyaudio.PyAudio()
                try:
                    return int(pa.get_default_input_device_info().get("index"))
                except Exception:
                    return None
                finally:
                    pa.terminate()
            except Exception:
                return None
        return None

    def _resolve_device_name(self, index: Optional[int]) -> str:
        if not audio_available():
            return "Sin audio"
        try:
            if index is None:
                index = self.default_input_device()
            for i, name in self.list_input_devices():
                if i == index:
                    return name
        except Exception:
            pass
        return "Micrófono predeterminado"

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        """Arranca la captura. Devuelve True si se inició correctamente."""
        if self._running or not audio_available():
            return self._running
        try:
            if _sd is not None:
                self._start_sounddevice()
            else:
                self._start_pyaudio()
            self._running = True
        except Exception as exc:  # pragma: no cover - depende del hardware
            print(f"[!] No se pudo iniciar el micrófono: {exc}")
            self._running = False
        return self._running

    def stop(self) -> None:
        """Detiene la captura y libera el dispositivo."""
        self._running = False
        try:
            if self._sd_stream is not None:
                self._sd_stream.stop()
                self._sd_stream.close()
        except Exception:
            pass
        self._sd_stream = None
        try:
            if self._pa_thread is not None:
                self._pa_thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            if self._pa_stream is not None:
                self._pa_stream.stop_stream()
                self._pa_stream.close()
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            pass
        self._pa_stream = None
        self._pa = None
        self.level = 0.0
        self.is_screaming = False

    def __enter__(self) -> "AudioMonitor":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ------------------------------------------------------------------ #
    # Backends
    # ------------------------------------------------------------------ #
    def _start_sounddevice(self) -> None:
        sr = self.samplerate
        if sr is None:
            try:
                info = _sd.query_devices(self.device_index, "input")
                sr = int(info["default_samplerate"])
            except Exception:
                sr = 44100
        self.samplerate = sr

        def _callback(indata, frames, time_info, status):  # noqa: ANN001
            if status:
                pass  # overflows puntuales: los ignoro, son normales en tiempo real
            mono = indata[:, 0] if indata.ndim > 1 else indata
            self._process_block(np.asarray(mono, dtype=np.float32), frames / sr)

        self._sd_stream = _sd.InputStream(
            samplerate=sr,
            blocksize=self.BLOCK_SIZE,
            device=self.device_index,
            channels=1,
            dtype="float32",
            callback=_callback,
        )
        self._sd_stream.start()

    def _start_pyaudio(self) -> None:
        sr = self.samplerate or 44100
        self.samplerate = sr
        self._pa = _pyaudio.PyAudio()
        self._pa_stream = self._pa.open(
            format=_pyaudio.paInt16,
            channels=1,
            rate=sr,
            input=True,
            frames_per_buffer=self.BLOCK_SIZE,
            input_device_index=self.device_index,
        )

        def _reader():
            while self._running:
                try:
                    raw = self._pa_stream.read(self.BLOCK_SIZE, exception_on_overflow=False)
                except Exception:
                    break
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                self._process_block(samples, self.BLOCK_SIZE / sr)

        # _running aún no es True aquí; lo activamos justo después en start()
        self._running = True
        self._pa_thread = threading.Thread(target=_reader, daemon=True)
        self._pa_thread.start()

    # ------------------------------------------------------------------ #
    # Procesado de un bloque de audio (corre en hilo de captura)
    # ------------------------------------------------------------------ #
    def _process_block(self, samples: np.ndarray, block_seconds: float) -> None:
        """Procesa un bloque de muestras de audio.

        Calculo RMS, convierto a dBFS y a porcentaje, aplico suavizado
        exponencial para el medidor, y actualizo el detector de gritos
        con histéresis temporal (MIN_SCREAM_S)."""
        if samples.size == 0:
            return
        rms = float(np.sqrt(np.mean(np.square(samples))))
        db = _rms_to_db(rms)
        pct = _db_to_pct(db)

        # Suavizado exponencial para un medidor estable.
        # Con smoothing=0.4, el nivel tarda ~10 bloques en estabilizarse
        # tras un cambio brusco, lo cual evita que el VU meter parpadee.
        self.level = self.smoothing * self.level + (1.0 - self.smoothing) * pct

        with self._lock:
            if db > self._peak_db:
                self._peak_db = db

            above = self.level >= self.threshold_pct
            if above:
                self._pending_above_s += block_seconds
                if not self._in_scream and self._pending_above_s >= self.MIN_SCREAM_S:
                    self._in_scream = True
                    self._scream_count += 1
                    # Contabilizo el tiempo previo que llevó a confirmar el grito
                    self._scream_total_seconds += self._pending_above_s
                elif self._in_scream:
                    self._scream_total_seconds += block_seconds
                self.is_screaming = self._in_scream
            else:
                self._pending_above_s = 0.0
                self._in_scream = False
                self.is_screaming = False

    # ------------------------------------------------------------------ #
    # Resumen para el CSV
    # ------------------------------------------------------------------ #
    def get_summary(self) -> dict:
        """Métricas de la sesión, listas para fusionar en el resumen de sesión."""
        with self._lock:
            peak = self._peak_db if self._peak_db > _DB_FLOOR else 0.0
            return {
                "scream_count": int(self._scream_count),
                "scream_peak_db": round(float(peak), 1),
                "scream_total_seconds": round(float(self._scream_total_seconds), 1),
                "mic_device_name": self.device_name,
            }

    def reset(self) -> None:
        """Reinicia los contadores (para el hotkey [R] de la sesión)."""
        with self._lock:
            self._scream_count = 0
            self._scream_total_seconds = 0.0
            self._peak_db = _DB_FLOOR
            self._pending_above_s = 0.0
            self._in_scream = False
        self.is_screaming = False
