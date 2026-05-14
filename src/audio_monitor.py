"""
RAGE TRACKER - Monitor de micrófono
====================================
AudioMonitor mide el volumen del micrófono en tiempo real y detecta "gritos".

Backends: sounddevice (principal) y PyAudio (fallback). Si ninguno está
instalado, el monitor queda en modo "no disponible" sin romper la app.

Cambios de esta revisión (corrige el medidor y la detección de micros):
- Apertura ROBUSTA del stream: prueba varias combinaciones de samplerate y
  número de canales antes de rendirse, y guarda el motivo del fallo en
  `last_error` para poder mostrárselo al usuario (antes fallaba en silencio).
- Mapeo de nivel CONFIGURABLE: suelo de ruido (`db_floor`) y `sensitivity`
  (ganancia) ajustables, para que micros flojos no dejen la barra muerta.
- Pico-hold: `peak_level` (0..100) que cae lentamente → la barra "reacciona"
  de forma visible y deja un marcador de pico.
- Enumeración de dispositivos con nombre de host API y marca del predeterminado,
  para que sea fácil elegir el micro correcto.
- API pública intacta (level, is_screaming, threshold_pct, device_name,
  start/stop/reset/get_summary, list_input_devices, default_input_device) más
  algunos extras opcionales (peak_level, sensitivity, last_error).

Dependencias (requirements.txt):
    sounddevice>=0.4.6
    numpy
    # PyAudio  (opcional, solo si no usas sounddevice)
En Linux: sudo apt install libportaudio2
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


def _hostapi_name(hostapi_index) -> str:
    """Nombre legible del host API de sounddevice (MME, WASAPI, etc.)."""
    if _sd is None:
        return ""
    try:
        apis = _sd.query_hostapis()
        return str(apis[hostapi_index].get("name", ""))
    except Exception:
        return ""


def diagnose() -> str:
    """Diagnóstico legible del estado del subsistema de audio.

    Pensado para que el launcher muestre un mensaje útil en lugar de un
    silencio confuso cuando no hay micrófonos."""
    if not audio_available():
        return (
            "No hay backend de audio instalado. Instala 'sounddevice':\n"
            "    pip install sounddevice\n"
            "o 'PyAudio' como alternativa:\n"
            "    pip install PyAudio"
        )
    devices = AudioMonitor.list_input_devices()
    if not devices:
        return (
            f"Backend {backend_name()} activo, pero no se encontraron\n"
            "dispositivos de entrada. Comprueba que el micrófono esté conectado\n"
            "y que el sistema tenga permisos de micrófono habilitados\n"
            "(Windows: Configuración → Privacidad → Micrófono)."
        )
    return f"Backend {backend_name()} · {len(devices)} dispositivo(s) de entrada"


# -----------------------------------------------------------------------------
# Utilidades de conversión RMS -> nivel 0..100 / dBFS
# -----------------------------------------------------------------------------
_DEFAULT_DB_FLOOR = -55.0   # antes -60; subido para que el habla normal se vea
_EPS = 1e-7


def _rms_to_db(rms: float) -> float:
    """RMS (0..1 sobre señal normalizada) -> dBFS aproximado."""
    return 20.0 * math.log10(max(rms, _EPS))


# -----------------------------------------------------------------------------
# AudioMonitor
# -----------------------------------------------------------------------------
class AudioMonitor:
    """Monitoriza un micrófono y detecta eventos de grito.

    Args:
        device_index: índice del dispositivo de entrada. None = predeterminado.
        threshold_pct: umbral de "grito" en % de volumen (0..100). Por defecto 80.
        samplerate: muestreo en Hz. None usa el del dispositivo.
        smoothing: suavizado exponencial del nivel (0..1, mayor = más estable).
        sensitivity: ganancia aplicada al RMS antes de medir (1.0 = sin cambio).
                     Súbela si tu micro es flojo y la barra apenas se mueve.
        db_floor: dBFS que corresponde al 0% del medidor (por defecto -55).
    """

    MIN_SCREAM_S = 0.3       # menos que esto suele ser un golpe, no un grito
    BLOCK_SIZE = 1024        # frames por bloque de captura
    _PEAK_DECAY_PER_S = 35.0 # caída del pico-hold (%/s) para que sea visible

    def __init__(
        self,
        device_index: Optional[int] = None,
        threshold_pct: float = 80.0,
        samplerate: Optional[int] = None,
        smoothing: float = 0.35,
        sensitivity: float = 1.0,
        db_floor: float = _DEFAULT_DB_FLOOR,
    ):
        self.device_index = device_index
        self.threshold_pct = float(max(0.0, min(100.0, threshold_pct)))
        self.smoothing = float(max(0.0, min(0.95, smoothing)))
        self.sensitivity = float(max(0.1, sensitivity))
        self.db_floor = float(db_floor)
        self.samplerate = samplerate

        self.device_name = self._resolve_device_name(device_index)
        self.last_error: str = ""   # motivo del último fallo de start()

        # Estado en vivo (lectura simple desde el hilo de la GUI/cámara)
        self.level: float = 0.0          # 0..100 suavizado
        self.peak_level: float = 0.0     # 0..100 pico-hold con caída
        self.is_screaming: bool = False  # True mientras supera el umbral confirmado

        # Métricas acumuladas (protegidas por lock al escribir desde el callback)
        self._lock = threading.Lock()
        self._scream_count = 0
        self._scream_total_seconds = 0.0
        self._peak_db = self.db_floor
        self._peak_pct = 0.0
        self._pending_above_s = 0.0
        self._in_scream = False
        self._last_block_t = time.time()

        # Recursos del backend
        self._running = False
        self._sd_stream = None
        self._pa = None
        self._pa_stream = None
        self._pa_thread: Optional[threading.Thread] = None

    def _db_to_pct(self, db: float) -> float:
        """dBFS -> porcentaje 0..100 (lineal entre db_floor y 0 dB)."""
        denom = (0.0 - self.db_floor) or 1.0
        pct = (db - self.db_floor) / denom * 100.0
        return max(0.0, min(100.0, pct))

    # ------------------------------------------------------------------ #
    # Enumeración de dispositivos
    # ------------------------------------------------------------------ #
    @staticmethod
    def list_input_devices() -> List[Tuple[int, str]]:
        """Devuelve [(index, nombre), ...] de los micrófonos de entrada.

        El nombre incluye el host API y marca el predeterminado con ★, para
        que el usuario distinga duplicados (en Windows un mismo micro aparece
        varias veces, una por host API)."""
        devices: List[Tuple[int, str]] = []
        if _sd is not None:
            try:
                default_idx = AudioMonitor.default_input_device()
                for idx, dev in enumerate(_sd.query_devices()):
                    if dev.get("max_input_channels", 0) > 0:
                        name = dev.get("name", f"Dispositivo {idx}")
                        api = _hostapi_name(dev.get("hostapi", -1))
                        label = f"{name}" + (f" [{api}]" if api else "")
                        if default_idx is not None and idx == default_idx:
                            label = f"★ {label}"
                        devices.append((idx, label))
            except Exception as exc:
                print(f"[!] Error al consultar dispositivos (sounddevice): {exc}")
        elif _pyaudio is not None:
            try:
                pa = _pyaudio.PyAudio()
                try:
                    for idx in range(pa.get_device_count()):
                        info = pa.get_device_info_by_index(idx)
                        if int(info.get("maxInputChannels", 0)) > 0:
                            devices.append(
                                (idx, str(info.get("name", f"Dispositivo {idx}")))
                            )
                finally:
                    pa.terminate()
            except Exception as exc:
                print(f"[!] Error al consultar dispositivos (PyAudio): {exc}")
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
            if _sd is not None:
                info = _sd.query_devices(
                    index if index is not None else self.default_input_device(),
                    "input",
                )
                return str(info.get("name", "Micrófono predeterminado"))
        except Exception:
            pass
        return "Micrófono predeterminado"

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        """Arranca la captura. Devuelve True si se inició correctamente.

        Si falla, deja el motivo en `self.last_error` (antes se perdía)."""
        if self._running or not audio_available():
            return self._running
        self.last_error = ""
        try:
            if _sd is not None:
                self._start_sounddevice()
            else:
                self._start_pyaudio()
            self._running = True
            self._last_block_t = time.time()
        except Exception as exc:  # pragma: no cover - depende del hardware
            self.last_error = str(exc)
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
        self.peak_level = 0.0
        self.is_screaming = False

    def __enter__(self) -> "AudioMonitor":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ------------------------------------------------------------------ #
    # Backends
    # ------------------------------------------------------------------ #
    def _candidate_samplerates(self) -> List[int]:
        rates: List[int] = []
        if self.samplerate:
            rates.append(int(self.samplerate))
        # Samplerate por defecto del dispositivo
        try:
            info = _sd.query_devices(self.device_index, "input")
            dsr = int(info.get("default_samplerate", 0))
            if dsr:
                rates.append(dsr)
        except Exception:
            pass
        # Fallbacks habituales
        for r in (48000, 44100, 32000, 16000):
            if r not in rates:
                rates.append(r)
        return rates

    def _start_sounddevice(self) -> None:
        """Abre el stream probando varias combinaciones (samplerate × canales).

        Esto es lo que arregla 'no detecta el micro': muchos dispositivos
        (sobre todo en Windows) no aceptan 1 canal a su samplerate nominal,
        así que probamos alternativas en lugar de rendirnos al primer fallo."""
        last_exc: Optional[Exception] = None
        for sr in self._candidate_samplerates():
            for channels in (1, 2):
                try:
                    # check_input_settings valida sin abrir realmente el stream
                    _sd.check_input_settings(
                        device=self.device_index, channels=channels,
                        samplerate=sr, dtype="float32",
                    )
                except Exception as exc:
                    last_exc = exc
                    continue

                self.samplerate = sr
                self._sd_channels = channels

                def _callback(indata, frames, time_info, status):  # noqa: ANN001
                    # Mezclo a mono si llegan varios canales.
                    mono = indata.mean(axis=1) if indata.ndim > 1 else indata
                    self._process_block(
                        np.asarray(mono, dtype=np.float32), frames / sr
                    )

                self._sd_stream = _sd.InputStream(
                    samplerate=sr,
                    blocksize=self.BLOCK_SIZE,
                    device=self.device_index,
                    channels=channels,
                    dtype="float32",
                    callback=_callback,
                )
                self._sd_stream.start()
                return

        raise RuntimeError(
            f"ninguna configuración de audio válida para el dispositivo "
            f"{self.device_index} (último error: {last_exc})"
        )

    def _start_pyaudio(self) -> None:
        sr = int(self.samplerate or 44100)
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
                    raw = self._pa_stream.read(
                        self.BLOCK_SIZE, exception_on_overflow=False
                    )
                except Exception:
                    break
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                self._process_block(samples, self.BLOCK_SIZE / sr)

        self._running = True
        self._pa_thread = threading.Thread(target=_reader, daemon=True)
        self._pa_thread.start()

    # ------------------------------------------------------------------ #
    # Procesado de un bloque de audio (corre en hilo de captura)
    # ------------------------------------------------------------------ #
    def _process_block(self, samples: np.ndarray, block_seconds: float) -> None:
        """Calcula RMS -> dBFS -> %, suaviza, mantiene pico y detecta gritos."""
        if samples.size == 0:
            return
        # Sanea NaN/inf que algún driver puede colar.
        samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
        rms = float(np.sqrt(np.mean(np.square(samples)))) * self.sensitivity
        db = _rms_to_db(rms)
        pct = self._db_to_pct(db)

        # Suavizado exponencial del nivel mostrado.
        self.level = self.smoothing * self.level + (1.0 - self.smoothing) * pct

        # Pico-hold con caída: si el nivel nuevo supera el pico, salta;
        # si no, el pico decae poco a poco (visible en la barra).
        decay = self._PEAK_DECAY_PER_S * max(block_seconds, 0.0)
        if self.level >= self.peak_level:
            self.peak_level = self.level
        else:
            self.peak_level = max(self.level, self.peak_level - decay)

        with self._lock:
            if db > self._peak_db:
                self._peak_db = db
            if pct > self._peak_pct:
                self._peak_pct = pct

            above = self.level >= self.threshold_pct
            if above:
                self._pending_above_s += block_seconds
                if not self._in_scream and self._pending_above_s >= self.MIN_SCREAM_S:
                    self._in_scream = True
                    self._scream_count += 1
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
            peak = self._peak_db if self._peak_db > self.db_floor else 0.0
            return {
                "scream_count": int(self._scream_count),
                "scream_peak_db": round(float(peak), 1),
                "scream_peak_pct": round(float(self._peak_pct), 1),
                "scream_total_seconds": round(float(self._scream_total_seconds), 1),
                "mic_device_name": self.device_name,
            }

    def reset(self) -> None:
        """Reinicia los contadores (para el hotkey [R] de la sesión)."""
        with self._lock:
            self._scream_count = 0
            self._scream_total_seconds = 0.0
            self._peak_db = self.db_floor
            self._peak_pct = 0.0
            self._pending_above_s = 0.0
            self._in_scream = False
        self.is_screaming = False
        self.peak_level = 0.0
