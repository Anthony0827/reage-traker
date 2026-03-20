"""
RAGE TRACKER - Orquestador de sesión  [NUEVO]
=============================================
Lanza UNA sesión según los sensores elegidos y persiste el resultado.
Aíslo aquí la lógica de combinación para no tocar camera.py más de lo necesario.

Modos soportados:
- "emotions"            -> EmotionDetector normal (cámara + HUD).
- "emotions" + "scream" -> EmotionDetector con audio_monitor (mini-VU en el HUD).
- "scream" (solo)       -> sesión SIN cámara: ventana ligera con el medidor
                           de volumen, timer y contador de gritos.

Es el punto al que llama `main.py --session ...` (subproceso lanzado por la GUI).
Decidí lanzarlo como subproceso para evitar líos entre el event loop de Tk y el
de OpenCV, sobre todo en macOS donde compiten por el hilo principal.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Iterable, Optional

import cv2
import numpy as np

from src import hud
from src.camera import EmotionDetector
from src.data_manager import DataManager

try:
    from src.audio_monitor import AudioMonitor, audio_available
except Exception:  # pragma: no cover
    AudioMonitor = None  # type: ignore

    def audio_available() -> bool:  # type: ignore
        return False


# Esquema de emociones vacío para sesiones de solo-gritos (sin cámara).
# Lo relleno con ceros para que el CSV tenga todas las columnas y el dashboard
# no se confunda con campos ausentes.
_EMPTY_EMOTIONS = {
    "happy_count": 0, "angry_count": 0, "neutral_count": 0,
    "happy_percentage": 0.0, "angry_percentage": 0.0, "neutral_percentage": 0.0,
    "peak_rage_count": 0, "happiness_streaks": 0, "emotional_trend": "neutral",
}


def run_session(
    game: str,
    sensors: Iterable[str],
    mic_index: Optional[int] = None,
    threshold: float = 80.0,
    data_manager: Optional[DataManager] = None,
) -> Optional[dict]:
    """Ejecuta una sesión y la guarda. Devuelve el resumen o None si se aborta."""
    sensors = set(sensors)
    want_emotions = "emotions" in sensors
    want_scream = "scream" in sensors
    if not (want_emotions or want_scream):
        print("[!] No se ha seleccionado ningún sensor. Nada que medir.")
        return None

    dm = data_manager or DataManager()

    # Monitor de micrófono (si procede)
    monitor = None
    if want_scream:
        if AudioMonitor is None or not audio_available():
            print("[!] No hay backend de audio disponible (instala 'sounddevice').")
            if not want_emotions:
                return None  # solo-gritos sin audio: no hay nada que hacer
            print("    Continuo solo con detección de emociones.")
            want_scream = False
        else:
            monitor = AudioMonitor(device_index=mic_index, threshold_pct=threshold)
            if not monitor.start():
                print("[!] No se pudo abrir el micrófono. Continuo sin gritos.")
                monitor = None
                if not want_emotions:
                    return None

    summary: Optional[dict] = None
    try:
        if want_emotions:
            detector = EmotionDetector(game_name=game, test_mode=False, audio_monitor=monitor)
            summary = detector.run()
        else:
            summary = _run_scream_only_session(game, monitor)
    finally:
        if monitor is not None:
            monitor.stop()

    if summary is None:
        return None

    dm.save_session(summary)
    print(
        f"\n[OK] Sesión guardada: {game} | "
        f"Rage {summary.get('angry_percentage', 0):.0f}% · "
        f"Gritos {summary.get('scream_count', 0)}"
    )
    return summary


def _run_scream_only_session(game: str, monitor) -> Optional[dict]:
    """Sesión sin cámara: solo micrófono. Ventana ligera con VU + timer.

    Aquí creo una ventana de OpenCV desde cero (sin EmotionDetector) porque
    no hay cámara que inicializar. El HUD es minimalista: barra de volumen
    grande, contador de gritos, pico dBFS y segundos gritando.
    """
    if monitor is None:
        return None

    window = "Rage Tracker - Gritos"
    W, H = 760, 440
    start = time.time()

    while True:
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        frame[:] = hud.COLOR_BG_DARK

        elapsed = time.time() - start
        summary_live = monitor.get_summary()
        level = float(getattr(monitor, "level", 0.0))
        thr = float(getattr(monitor, "threshold_pct", 80.0))
        screaming = bool(getattr(monitor, "is_screaming", False))

        # Barra superior
        hud.draw_panel(frame, 0, 0, W, 56, alpha=0.9, border_color=hud.COLOR_CYAN)
        hud.draw_text(frame, f"RAGE TRACKER  -  {game}  [SOLO GRITOS]",
                      (16, 26), 0.6, hud.COLOR_CYAN, 1, shadow=True)
        hud.draw_text(frame, f"{hud.format_time(elapsed)}", (W - 110, 26),
                      0.7, hud.COLOR_TEXT, 1, shadow=True)

        # Medidor grande
        bx, by, bw, bh = 40, 150, W - 80, 46
        cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), hud.COLOR_BG, -1)
        fill = int(bw * max(0.0, min(100.0, level)) / 100.0)
        color = hud.COLOR_BAD if level >= 90 else (hud.COLOR_WARN if level >= 60 else hud.COLOR_GOOD)
        if fill > 0:
            cv2.rectangle(frame, (bx, by), (bx + fill, by + bh), color, -1)
        tx = bx + int(bw * max(0.0, min(100.0, thr)) / 100.0)
        cv2.line(frame, (tx, by - 8), (tx, by + bh + 8), hud.COLOR_ANGRY, 2, cv2.LINE_AA)
        cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), hud.COLOR_TEXT_DIM, 1)
        hud.draw_text(frame, "VOLUMEN DEL MICROFONO", (bx, by - 12), 0.5, hud.COLOR_TEXT_DIM, 1)
        hud.draw_text(frame, f"umbral {int(thr)}%", (tx + 6, by + bh + 24), 0.42, hud.COLOR_ANGRY, 1)
        hud.draw_text(frame, f"{int(level)}%", (bx + bw - 70, by + bh + 24), 0.7,
                      hud.COLOR_TEXT, 1, shadow=True)

        # Contadores
        scount = summary_live.get("scream_count", 0)
        hud.draw_text(frame, "GRITOS", (40, 300), 0.6, hud.COLOR_TEXT_DIM, 1)
        hud.draw_text(frame, str(scount), (40, 350), 1.6,
                      hud.COLOR_ANGRY if scount else hud.COLOR_TEXT, 3, shadow=True)
        hud.draw_text(frame, "PICO (dBFS)", (260, 300), 0.6, hud.COLOR_TEXT_DIM, 1)
        hud.draw_text(frame, f"{summary_live.get('scream_peak_db', 0)}", (260, 350),
                      1.1, hud.COLOR_TEXT, 2, shadow=True)
        hud.draw_text(frame, "SEG. GRITANDO", (480, 300), 0.6, hud.COLOR_TEXT_DIM, 1)
        hud.draw_text(frame, f"{summary_live.get('scream_total_seconds', 0)}", (480, 350),
                      1.1, hud.COLOR_TEXT, 2, shadow=True)

        if screaming:
            cv2.rectangle(frame, (2, 2), (W - 2, H - 2), hud.COLOR_ANGRY, 3)

        hud.draw_hotkeys_strip(frame, [("Q", "Terminar"), ("R", "Reiniciar")])
        cv2.imshow(window, frame)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        if key == ord("r"):
            monitor.reset()
            start = time.time()

    cv2.destroyWindow(window)

    total_time = int(time.time() - start)
    summary = {
        "game": game,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": total_time,
        "total_frames": 0,
    }
    summary.update(_EMPTY_EMOTIONS)
    summary.update(monitor.get_summary())
    return summary
