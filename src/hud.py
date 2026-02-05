"""
RAGE TRACKER - HUD (Heads-Up Display)
=====================================
Módulo de dibujo del overlay sobre el frame de la cámara.
Estilo "gaming/cyberpunk" coherente con el dashboard web.

Diseño:
- Todas las funciones son sin estado (stateless): reciben el frame y parámetros,
  dibujan in-place y devuelven None. Esto facilita componer el HUD sin
  acoplar el resto del código.
- Paleta y constantes definidas como módulo para mantener coherencia visual.
- Texto con FONT_HERSHEY_DUPLEX para mejor anti-aliasing que SIMPLEX, sin
  dependencias extra. Pillow es opcional pero no requerido.

Autor: Refactor para mejoras visuales del Rage Tracker.
"""

from __future__ import annotations

import math
import time
import unicodedata
from collections import deque
from typing import Deque, Iterable, Tuple

import cv2
import numpy as np


# -----------------------------------------------------------------------------
# COMPATIBILIDAD DE TEXTO
# -----------------------------------------------------------------------------
# Las fuentes HERSHEY de OpenCV son sólo ASCII. Si pasamos "Detección" se pinta
# como "Detecci??n". Convertimos a ASCII automáticamente para no degradar la
# experiencia del usuario y mantener el resto del código con español correcto.
_CHAR_REPLACEMENTS = {
    "·": "-", "—": "-", "–": "-", "°": "o",
    "¿": "?", "¡": "!", "“": '"', "”": '"', "‘": "'", "’": "'",
}

def _to_ascii(s: str) -> str:
    """Convierte un string con acentos/unicode a ASCII puro para cv2.putText."""
    if not isinstance(s, str):
        s = str(s)
    for src, dst in _CHAR_REPLACEMENTS.items():
        s = s.replace(src, dst)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _text_size(text: str, scale: float, thickness: int = 1):
    """Versión sanitizada de cv2.getTextSize para uso interno del HUD."""
    return cv2.getTextSize(_to_ascii(text), FONT, scale, thickness)


# -----------------------------------------------------------------------------
# PALETA (BGR — recordar que OpenCV no usa RGB)
# -----------------------------------------------------------------------------
COLOR_BG = (18, 18, 28)            # Negro azulado para paneles
COLOR_BG_DARK = (8, 8, 14)         # Más oscuro (interiores de barras)
COLOR_CYAN = (255, 220, 80)        # Acento principal cyberpunk
COLOR_MAGENTA = (220, 60, 220)     # Acento secundario
COLOR_HAPPY = (80, 230, 120)       # Verde neón — feliz
COLOR_ANGRY = (60, 60, 240)        # Rojo neón — enfadado
COLOR_NEUTRAL = (180, 180, 180)    # Gris claro — neutral
COLOR_REC = (60, 60, 240)          # Rojo grabación
COLOR_TEXT = (240, 240, 245)       # Blanco roto
COLOR_TEXT_DIM = (150, 155, 165)   # Gris medio
COLOR_GOOD = (80, 230, 120)        # Verde estado OK
COLOR_WARN = (80, 200, 250)        # Ámbar/naranja para advertencias
COLOR_BAD = (60, 60, 240)          # Rojo para problemas

FONT = cv2.FONT_HERSHEY_DUPLEX


# -----------------------------------------------------------------------------
# HELPERS DE COLOR / FORMATO
# -----------------------------------------------------------------------------
def emotion_color(emotion: str) -> Tuple[int, int, int]:
    """Devuelve el color BGR asociado a una emoción."""
    if emotion == "happy":
        return COLOR_HAPPY
    if emotion == "angry":
        return COLOR_ANGRY
    return COLOR_NEUTRAL


def emotion_label(emotion: str) -> str:
    """Etiqueta visible en español."""
    return {
        "happy": "FELIZ",
        "angry": "ENFADADO",
        "neutral": "NEUTRAL",
    }.get(emotion, emotion.upper())


def emotion_icon(emotion: str) -> str:
    """Carácter ASCII compatible con cv2.putText (los emojis no se renderizan)."""
    return {
        "happy": ":)",
        "angry": ":(",
        "neutral": ":|",
    }.get(emotion, "?")


def format_time(seconds: float) -> str:
    """Formatea segundos a MM:SS."""
    seconds = int(max(0, seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# -----------------------------------------------------------------------------
# PRIMITIVAS DE DIBUJO
# -----------------------------------------------------------------------------
def draw_panel(
    frame: np.ndarray,
    x: int, y: int, w: int, h: int,
    alpha: float = 0.65,
    border_color: Tuple[int, int, int] | None = None,
    fill_color: Tuple[int, int, int] | None = None,
) -> None:
    """Panel semi-transparente con borde opcional.

    Recorta automáticamente al tamaño del frame para evitar errores si
    el caller calcula coordenadas que se salen.
    """
    h_frame, w_frame = frame.shape[:2]
    x2 = min(w_frame, x + w)
    y2 = min(h_frame, y + h)
    x1 = max(0, x)
    y1 = max(0, y)
    if x2 <= x1 or y2 <= y1:
        return

    fill = fill_color if fill_color is not None else COLOR_BG
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), fill, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    if border_color is not None:
        cv2.rectangle(frame, (x1, y1), (x2, y2), border_color, 1)


def draw_text(
    frame: np.ndarray,
    text: str,
    org: Tuple[int, int],
    scale: float = 0.55,
    color: Tuple[int, int, int] = COLOR_TEXT,
    thickness: int = 1,
    shadow: bool = False,
) -> None:
    """Texto con sombra opcional (útil para legibilidad sobre vídeo)."""
    text = _to_ascii(text)
    if shadow:
        cv2.putText(frame, text, (org[0] + 1, org[1] + 1), FONT, scale,
                    COLOR_BG_DARK, thickness, cv2.LINE_AA)
    cv2.putText(frame, text, org, FONT, scale, color, thickness, cv2.LINE_AA)


def draw_corner_box(
    frame: np.ndarray,
    x: int, y: int, w: int, h: int,
    color: Tuple[int, int, int],
    thickness: int = 3,
    arm_pct: float = 0.18,
    pulse_t: float = 0.0,
) -> None:
    """Bounding box estilo lock-on: sólo las esquinas, no rectángulo cerrado.

    pulse_t (segundos) añade una animación sutil de "respiración" en el grosor
    para indicar que la detección está activa.
    """
    arm = max(14, int(min(w, h) * arm_pct))
    # Pulso de respiración entre [thickness, thickness+1] para no saturar
    if pulse_t > 0:
        pulse = (math.sin(pulse_t * 3.5) + 1) / 2  # 0..1
        thickness = int(thickness + round(pulse))

    # Esquinas: (origen_x, origen_y, dx_horiz, dy_vert)
    corners = [
        (x, y, 1, 1),                     # top-left
        (x + w, y, -1, 1),                # top-right
        (x, y + h, 1, -1),                # bottom-left
        (x + w, y + h, -1, -1),           # bottom-right
    ]
    for cx, cy, dx, dy in corners:
        cv2.line(frame, (cx, cy), (cx + arm * dx, cy), color, thickness, cv2.LINE_AA)
        cv2.line(frame, (cx, cy), (cx, cy + arm * dy), color, thickness, cv2.LINE_AA)


def draw_progress_bar(
    frame: np.ndarray,
    x: int, y: int, w: int, h: int,
    value: float,                # 0..100
    color: Tuple[int, int, int],
    bg_color: Tuple[int, int, int] = COLOR_BG_DARK,
    border: bool = True,
) -> None:
    """Barra de progreso horizontal con fondo oscuro y borde sutil."""
    cv2.rectangle(frame, (x, y), (x + w, y + h), bg_color, -1)
    value = max(0.0, min(100.0, value))
    fill = int(w * value / 100)
    if fill > 0:
        cv2.rectangle(frame, (x, y), (x + fill, y + h), color, -1)
    if border:
        cv2.rectangle(frame, (x, y), (x + w, y + h), COLOR_TEXT_DIM, 1)


def draw_rec_indicator(frame: np.ndarray, x: int, y: int, blink_t: float,
                       label: str = "REC") -> None:
    """Punto rojo parpadeante + texto. Parpadeo a ~1Hz."""
    on = (int(blink_t * 2) % 2) == 0
    cv2.circle(frame, (x, y), 7, COLOR_REC, -1 if on else 1, cv2.LINE_AA)
    color = COLOR_REC if on else COLOR_TEXT_DIM
    draw_text(frame, label, (x + 14, y + 5), 0.55, color, 1, shadow=True)


def draw_sparkline(
    frame: np.ndarray,
    x: int, y: int, w: int, h: int,
    samples: Deque[str],
    title: str = "Últimos segundos",
) -> None:
    """Sparkline horizontal: cada muestra es una banda vertical coloreada
    según la emoción detectada en ese tick.

    samples: deque de strings ("happy", "angry", "neutral").
    """
    draw_panel(frame, x, y, w, h, alpha=0.55, border_color=COLOR_TEXT_DIM)
    draw_text(frame, title, (x + 8, y + 14), 0.4, COLOR_TEXT_DIM, 1)

    inner_y = y + 18
    inner_h = h - 22
    inner_x = x + 6
    inner_w = w - 12

    if not samples:
        draw_text(frame, "esperando muestras...", (inner_x + 4, inner_y + inner_h // 2 + 4),
                  0.4, COLOR_TEXT_DIM, 1)
        return

    n = len(samples)
    bar_w = max(1, inner_w / n)
    for i, emotion in enumerate(samples):
        bx = inner_x + int(i * bar_w)
        bx2 = inner_x + int((i + 1) * bar_w) - 1
        if bx2 <= bx:
            bx2 = bx + 1
        cv2.rectangle(frame, (bx, inner_y), (bx2, inner_y + inner_h),
                      emotion_color(emotion), -1)


def draw_status_pill(
    frame: np.ndarray,
    x: int, y: int,
    label: str,
    state: str,  # "ok" | "warn" | "bad"
) -> int:
    """Pastilla con icono y etiqueta de estado. Devuelve el ancho dibujado
    para encadenar varias pills horizontalmente."""
    color = {"ok": COLOR_GOOD, "warn": COLOR_WARN, "bad": COLOR_BAD}.get(state, COLOR_TEXT_DIM)
    icon = {"ok": "OK", "warn": "!", "bad": "X"}.get(state, "?")
    text = f"[{icon}] {label}"
    (tw, th), _ = _text_size(text, 0.42, 1)
    pad = 6
    w = tw + pad * 2
    h = th + pad * 2
    cv2.rectangle(frame, (x, y), (x + w, y + h), COLOR_BG_DARK, -1)
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 1)
    draw_text(frame, text, (x + pad, y + th + pad - 2), 0.42, color, 1)
    return w


def draw_hotkeys_strip(frame: np.ndarray, hotkeys: Iterable[Tuple[str, str]]) -> None:
    """Tira inferior con los atajos disponibles."""
    h_frame, w_frame = frame.shape[:2]
    strip_h = 30
    y = h_frame - strip_h
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, y), (w_frame, h_frame), COLOR_BG_DARK, -1)
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
    cv2.line(frame, (0, y), (w_frame, y), COLOR_CYAN, 1)

    x = 14
    for key, label in hotkeys:
        chip = f"[{key}]"
        (cw, _), _ = _text_size(chip, 0.5, 1)
        draw_text(frame, chip, (x, y + 20), 0.5, COLOR_CYAN, 1)
        x += cw + 6
        (lw, _), _ = _text_size(label, 0.5, 1)
        draw_text(frame, label, (x, y + 20), 0.5, COLOR_TEXT, 1)
        x += lw + 22


# -----------------------------------------------------------------------------
# COMPONENTES DE ALTO NIVEL
# -----------------------------------------------------------------------------
def draw_top_bar(
    frame: np.ndarray,
    game_name: str,
    elapsed_s: float,
    fps: float,
    blink_t: float,
    test_mode: bool = False,
    paused: bool = False,
) -> None:
    """Barra superior: REC, juego, timer y FPS."""
    h_frame, w_frame = frame.shape[:2]
    bar_h = 44
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w_frame, bar_h), COLOR_BG_DARK, -1)
    cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
    cv2.line(frame, (0, bar_h), (w_frame, bar_h), COLOR_CYAN, 1)

    # REC / TEST / PAUSE
    if test_mode:
        draw_text(frame, "[TEST] modo prueba - no se guarda", (14, 28),
                  0.55, COLOR_WARN, 1, shadow=True)
    elif paused:
        draw_text(frame, "[PAUSA]", (14, 28), 0.6, COLOR_WARN, 1, shadow=True)
    else:
        draw_rec_indicator(frame, 22, 22, blink_t)

    # Juego (centrado)
    title = f"RAGE TRACKER  ·  {game_name}" if game_name else "RAGE TRACKER"
    (tw, _), _ = _text_size(title, 0.6, 1)
    draw_text(frame, title, ((w_frame - tw) // 2, 28), 0.6, COLOR_CYAN, 1, shadow=True)

    # Timer + FPS (derecha)
    timer = format_time(elapsed_s)
    fps_s = f"{fps:4.1f} fps"
    right_text = f"{timer}   {fps_s}"
    (rw, _), _ = _text_size(right_text, 0.55, 1)
    draw_text(frame, right_text, (w_frame - rw - 14, 28), 0.55, COLOR_TEXT, 1, shadow=True)


def draw_emotion_card(
    frame: np.ndarray,
    x: int, y: int, w: int, h: int,
    emotion: str,
    confidence: float,
    streak: int = 0,
) -> None:
    """Tarjeta lateral con la emoción actual + barra de confianza + racha."""
    color = emotion_color(emotion)
    draw_panel(frame, x, y, w, h, alpha=0.7, border_color=color)

    # Cabecera
    draw_text(frame, "ESTADO ACTUAL", (x + 12, y + 22), 0.45, COLOR_TEXT_DIM, 1)

    # Icono + label grande
    icon = emotion_icon(emotion)
    label = emotion_label(emotion)
    draw_text(frame, icon, (x + 12, y + 60), 1.1, color, 2, shadow=True)
    draw_text(frame, label, (x + 60, y + 60), 0.85, color, 2, shadow=True)

    # Barra de confianza
    draw_text(frame, f"Confianza  {int(confidence)}%", (x + 12, y + 88),
              0.45, COLOR_TEXT_DIM, 1)
    draw_progress_bar(frame, x + 12, y + 95, w - 24, 10, confidence, color)

    # Racha
    if streak > 1:
        draw_text(frame, f"Racha actual: x{streak}", (x + 12, y + h - 12),
                  0.45, COLOR_TEXT_DIM, 1)


def draw_counters_card(
    frame: np.ndarray,
    x: int, y: int, w: int, h: int,
    happy_count: int,
    angry_count: int,
) -> None:
    """Tarjeta con contadores feliz/enfadado y porcentajes."""
    draw_panel(frame, x, y, w, h, alpha=0.7, border_color=COLOR_TEXT_DIM)
    draw_text(frame, "CONTADORES", (x + 12, y + 22), 0.45, COLOR_TEXT_DIM, 1)

    total = max(1, happy_count + angry_count)
    happy_pct = happy_count / total * 100
    angry_pct = angry_count / total * 100

    # Feliz
    draw_text(frame, f"FELIZ  {happy_count}  ({happy_pct:4.0f}%)",
              (x + 12, y + 50), 0.55, COLOR_HAPPY, 1, shadow=True)
    draw_progress_bar(frame, x + 12, y + 56, w - 24, 6, happy_pct, COLOR_HAPPY)

    # Enfadado
    draw_text(frame, f"RAGE   {angry_count}  ({angry_pct:4.0f}%)",
              (x + 12, y + 84), 0.55, COLOR_ANGRY, 1, shadow=True)
    draw_progress_bar(frame, x + 12, y + 90, w - 24, 6, angry_pct, COLOR_ANGRY)


def draw_quality_panel(
    frame: np.ndarray,
    x: int, y: int,
    lighting: str,        # "ok" | "warn" | "bad"
    lighting_msg: str,
    distance: str,
    distance_msg: str,
    detection: str,
    detection_msg: str,
) -> None:
    """Tres pills horizontales con el estado del sistema."""
    cur_x = x
    cur_x += draw_status_pill(frame, cur_x, y, lighting_msg, lighting) + 6
    cur_x += draw_status_pill(frame, cur_x, y, distance_msg, distance) + 6
    cur_x += draw_status_pill(frame, cur_x, y, detection_msg, detection) + 6


def draw_centered_message(
    frame: np.ndarray,
    title: str,
    subtitle: str | None = None,
    countdown: int | None = None,
    accent_color: Tuple[int, int, int] = COLOR_CYAN,
) -> None:
    """Mensaje centrado a pantalla completa con overlay oscuro.

    Usado durante la calibración y avisos modales.
    """
    h_frame, w_frame = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w_frame, h_frame), COLOR_BG_DARK, -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    # Título
    (tw, th), _ = _text_size(title, 1.1, 2)
    cy = h_frame // 2
    draw_text(frame, title, ((w_frame - tw) // 2, cy - 20), 1.1, accent_color, 2, shadow=True)

    if subtitle:
        (sw, _), _ = _text_size(subtitle, 0.6, 1)
        draw_text(frame, subtitle, ((w_frame - sw) // 2, cy + 16),
                  0.6, COLOR_TEXT, 1, shadow=True)

    if countdown is not None:
        countdown_s = str(countdown)
        (cw, ch), _ = _text_size(countdown_s, 3.5, 4)
        draw_text(frame, countdown_s,
                  ((w_frame - cw) // 2, cy + 110),
                  3.5, accent_color, 4, shadow=True)
