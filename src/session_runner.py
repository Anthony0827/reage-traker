"""
RAGE TRACKER - Orquestador de sesión
====================================
Lanza UNA sesión según los sensores elegidos y persiste el resultado.

Modos soportados:
- "emotions"            -> EmotionDetector normal (cámara + HUD).
- "emotions" + "scream" -> EmotionDetector con audio_monitor (mini-VU en el HUD).
                            Cada grito confirmado SUMA al contador de enfado.
- "scream" (solo)       -> sesión SIN cámara: ventana ligera con el medidor
                            de volumen, timer y contador de gritos.
- "emotions" + "insults" -> EmotionDetector con insult_detector (contador de insultos)
- "emotions" + "scream" + "insults" -> ambos sensores de audio activos

Es el punto al que llama `main.py --session` (subproceso lanzado por la GUI).
Se lanza como subproceso para evitar líos entre el event loop de Tk y el de
OpenCV (sobre todo en macOS, donde compiten por el hilo principal).
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

try:
    from src.insult_detector import InsultDetector
except Exception:  # pragma: no cover
    InsultDetector = None  # type: ignore

    def audio_available() -> bool:  # type: ignore
        return False


# Cuántos "momentos de enfado" suma cada grito confirmado. 1.0 = un grito
# equivale a una detección de cara enfadada. Súbelo si quieres que los gritos
# pesen más en el rage index.
RAGE_PER_SCREAM = 1.0

# Cuántos "momentos de enfado" suma cada insulto detectado. 0.3 = un insulto
# equivale a 0.3 de enfado (menos que un grito).
RAGE_PER_INSULT = 0.3

# Claves de micrófono que el monitor es la fuente de verdad y deben acabar
# siempre en el resumen (y por tanto en el CSV / dashboard).
_SCREAM_KEYS = (
    "scream_count", "scream_peak_db", "scream_total_seconds", "mic_device_name",
)
_INSULT_KEYS = (
    "insult_count", "insult_peak_count", "insult_model_name",
)

# Esquema de emociones vacío para sesiones de solo-gritos (sin cámara).
_EMPTY_EMOTIONS = {
    "happy_count": 0, "angry_count": 0, "neutral_count": 0,
    "happy_percentage": 0.0, "angry_percentage": 0.0, "neutral_percentage": 0.0,
    "peak_rage_count": 0, "happiness_streaks": 0, "emotional_trend": "neutral",
}


def _fold_screams_into_rage(summary: dict, weight: float = RAGE_PER_SCREAM) -> dict:
    """Suma los gritos a la medición de enfado y recalcula porcentajes.

    Cada grito confirmado (volumen por encima del umbral durante el tiempo
    mínimo) cuenta como `weight` "momentos de enfado". Después recalcula los
    porcentajes happy/angry/neutral sobre el nuevo total para que el rage index
    del dashboard refleje también los gritos."""
    screams = int(summary.get("scream_count", 0) or 0)
    if screams <= 0 or weight <= 0:
        return summary

    add = int(round(screams * weight))
    happy = int(summary.get("happy_count", 0) or 0)
    angry = int(summary.get("angry_count", 0) or 0) + add
    neutral = int(summary.get("neutral_count", 0) or 0)

    summary["angry_count"] = angry
    # Cada grito es también un "pico" de rage.
    summary["peak_rage_count"] = int(summary.get("peak_rage_count", 0) or 0) + add

    total = happy + angry + neutral
    if total > 0:
        summary["happy_percentage"] = round(happy / total * 100.0, 1)
        summary["angry_percentage"] = round(angry / total * 100.0, 1)
        summary["neutral_percentage"] = round(neutral / total * 100.0, 1)

    # Si la sesión quedó dominada por gritos, el trend pasa a 'rage'.
    if summary.get("angry_percentage", 0) >= 50:
        summary["emotional_trend"] = "rage"
    return summary


def _fold_insults_into_rage(summary: dict, weight: float = RAGE_PER_INSULT) -> dict:
    """Suma los insultos a la medición de enfado y recalcula porcentajes.

    Cada insulto confirmado (match con lexicon) cuenta como `weight` "momentos de
    enfado". Después recalcula los porcentajes happy/angry/neutral sobre el nuevo
    total para que el rage index del dashboard refleje también los insultos."""
    insults = int(summary.get("insult_count", 0) or 0)
    if insults <= 0 or weight <= 0:
        return summary

    add = int(round(insults * weight))
    happy = int(summary.get("happy_count", 0) or 0)
    angry = int(summary.get("angry_count", 0) or 0) + add
    neutral = int(summary.get("neutral_count", 0) or 0)

    summary["angry_count"] = angry
    # Cada insulto es también un "pico" de rage.
    summary["peak_rage_count"] = int(summary.get("peak_rage_count", 0) or 0) + add

    total = happy + angry + neutral
    if total > 0:
        summary["happy_percentage"] = round(happy / total * 100.0, 1)
        summary["angry_percentage"] = round(angry / total * 100.0, 1)
        summary["neutral_percentage"] = round(neutral / total * 100.0, 1)

    # Si la sesión quedó dominada por insultos, el trend pasa a 'rage'.
    if summary.get("angry_percentage", 0) >= 50:
        summary["emotional_trend"] = "rage"
    return summary


def run_session(
    game: str,
    sensors: Iterable[str],
    mic_index: Optional[int] = None,
    threshold: float = 80.0,
    sensitivity: float = 1.0,
    data_manager: Optional[DataManager] = None,
) -> Optional[dict]:
    """Ejecuta una sesión y la guarda. Devuelve el resumen o None si se aborta."""
    sensors = set(sensors)
    want_emotions = "emotions" in sensors
    want_scream = "scream" in sensors
    want_insults = "insults" in sensors
    if not (want_emotions or want_scream or want_insults):
        print("[!] No se ha seleccionado ningún sensor. Nada que medir.")
        return None

    dm = data_manager or DataManager()

    # Monitor de micrófono (si procede)
    monitor = None
    insult_detector = None
    if want_scream or want_insults:
        if AudioMonitor is None or not audio_available():
            print("[!] No hay backend de audio disponible (instala 'sounddevice').")
            if not want_emotions and not want_insults:
                return None
            print("    Continuo solo con detección de emociones.")
            want_scream = False
            want_insults = False
        elif want_insults and InsultDetector is None:
            print("[!] El módulo de insultos no está disponible. Desactivando sensor.")
            want_insults = False
        else:
            if want_scream:
                monitor = AudioMonitor(
                    device_index=mic_index,
                    threshold_pct=threshold,
                    sensitivity=sensitivity,
                )
                if not monitor.start():
                    why = getattr(monitor, "last_error", "") or "motivo desconocido"
                    print(f"[!] No se pudo abrir el micrófono ({why}). Continuo sin gritos.")
                    monitor = None
                    if not want_emotions and not want_insults:
                        return None
            if want_insults:
                insult_detector = InsultDetector()
                if not insult_detector.start():
                    why = getattr(insult_detector, "last_error", "") or "motivo desconocido"
                    print(f"[!] No se pudo iniciar el detector de insultos ({why}).")
                    insult_detector = None

    summary: Optional[dict] = None
    monitor_summary: dict = {}
    insult_summary: dict = {}
    try:
        if want_emotions:
            detector = EmotionDetector(
                game_name=game, test_mode=False,
                audio_monitor=monitor,
                insult_detector=insult_detector if want_insults else None,
            )
            summary = detector.run()
        else:
            summary = _run_scream_only_session(game, monitor)

        # Capturo las métricas del micro ANTES de pararlo (el monitor es la
        # fuente de verdad para los campos de gritos).
        if monitor is not None:
            monitor_summary = monitor.get_summary()
        if insult_detector is not None:
            insult_summary = insult_detector.get_summary()
    finally:
        if monitor is not None:
            monitor.stop()
        if insult_detector is not None:
            insult_detector.stop()

    if summary is None:
        return None

    # Asegura que las métricas de gritos están en el resumen, gane quien gane.
    if monitor_summary:
        for key in _SCREAM_KEYS:
            if key in monitor_summary:
                summary[key] = monitor_summary[key]

    # Asegura que las métricas de insultos están en el resumen.
    if insult_summary:
        for key in _INSULT_KEYS:
            if key in insult_summary:
                summary[key] = insult_summary[key]

    # Acopla los gritos al rage SOLO si había cámara: en solo-gritos no hay
    # baseline de emociones y forzaríamos 100% de rage de forma artificial.
    if want_emotions and want_scream:
        summary = _fold_screams_into_rage(summary)
    
    # Acopla los insultos al rage SOLO si había cámara.
    if want_emotions and want_insults:
        summary = _fold_insults_into_rage(summary)

    dm.save_session(summary)
    print(
        f"\n[OK] Sesión guardada: {game} | "
        f"Rage {summary.get('angry_percentage', 0):.0f}% · "
        f"Gritos {summary.get('scream_count', 0)} · "
        f"Insultos {summary.get('insult_count', 0)}"
    )
    return summary


def _run_scream_only_session(game: str, monitor) -> Optional[dict]:
    """Sesión sin cámara: solo micrófono. Ventana ligera con VU + timer.

    Creo una ventana de OpenCV desde cero (sin EmotionDetector) porque no hay
    cámara que inicializar. El HUD es minimalista: barra de volumen grande,
    contador de gritos, pico dBFS y segundos gritando."""
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
        peak = float(getattr(monitor, "peak_level", 0.0))
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
        # Marcador de pico-hold
        px = bx + int(bw * max(0.0, min(100.0, peak)) / 100.0)
        cv2.line(frame, (px, by - 4), (px, by + bh + 4), hud.COLOR_TEXT, 2, cv2.LINE_AA)
        # Línea de umbral
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
