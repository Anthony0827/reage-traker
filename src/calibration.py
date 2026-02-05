"""
RAGE TRACKER - Calibración automática
=====================================
Sistema de auto-calibración que reemplaza los valores hardcodeados.

Flujo:
1. Assessment del entorno (silencioso, ~2s): brillo, tamaño de cara,
   estabilidad de detección.
2. Captura guiada de tres baselines (neutral, feliz, enfadado), 3s cada uno
   con cuenta atrás visual y barra de progreso.
3. Búsqueda en rejilla de los parámetros óptimos de sonrisa sobre las ROIs
   cacheadas, maximizando separabilidad entre "feliz" y los otros estados.
4. Persistencia en data/calibration_profile.json.

Mantiene compatibilidad hacia atrás: si no hay perfil, EmotionDetector usa
los valores por defecto del proyecto original.

Notas de diseño:
- No usamos time.sleep(): congelaría la ventana de OpenCV. Los tiempos se
  miden vía time.time() dentro del bucle de captura.
- Las ROIs cacheadas se guardan ya convertidas a gris para acelerar la
  búsqueda en rejilla.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from src import hud


# Valores por defecto (los del config_tool original)
DEFAULT_THRESHOLDS: Dict = {
    "smile_scale_factor": 1.9,
    "smile_min_neighbors": 22,
    "smile_min_size": [30, 30],
    "eye_scale_factor": 1.1,
    "eye_min_neighbors": 8,
    "eye_min_size": [15, 15],
    "brow_angry_threshold": 90,
    "brow_very_angry_threshold": 78,
    "mouth_tense_threshold": 88,
    "frames_between_counts": 14,
    "emotion_confirmation_frames": 6,
}


PROFILES_DIR = "data"
PROFILE_FILE = os.path.join(PROFILES_DIR, "calibration_profile.json")


# -----------------------------------------------------------------------------
# PERFIL: carga / guardado
# -----------------------------------------------------------------------------
@dataclass
class CalibrationProfile:
    """Perfil de calibración serializable a JSON."""
    profile_name: str = "default"
    created_at: str = ""
    environment: Dict = field(default_factory=dict)
    thresholds: Dict = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    baselines: Dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str = PROFILE_FILE) -> Optional["CalibrationProfile"]:
        """Carga un perfil del disco. Devuelve None si no existe o es inválido."""
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Fusiona con DEFAULT_THRESHOLDS para tolerar versiones antiguas
            merged = dict(DEFAULT_THRESHOLDS)
            merged.update(data.get("thresholds", {}))
            data["thresholds"] = merged
            return cls(**data)
        except (json.JSONDecodeError, TypeError, OSError) as e:
            print(f"⚠️  Perfil de calibración inválido ({e}). Usando valores por defecto.")
            return None

    def save(self, path: str = PROFILE_FILE) -> None:
        """Persiste el perfil en disco."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)


# -----------------------------------------------------------------------------
# ASSESSMENTS DEL ENTORNO (usados también en tiempo real por el HUD)
# -----------------------------------------------------------------------------
def assess_lighting(gray_frame: np.ndarray) -> Tuple[str, str]:
    """Devuelve (estado, mensaje) sobre la iluminación.

    Estado: "ok" | "warn" | "bad".
    """
    mean = float(gray_frame.mean())
    if mean < 50:
        return "bad", "Luz baja"
    if mean < 80:
        return "warn", "Luz justa"
    if mean > 200:
        return "warn", "Luz alta"
    return "ok", "Luz OK"


def assess_distance(face_w: int, frame_w: int) -> Tuple[str, str]:
    """Evalúa la distancia a partir del ancho relativo de la cara."""
    if frame_w <= 0:
        return "bad", "Sin cara"
    ratio = face_w / frame_w
    if ratio < 0.18:
        return "warn", "Acércate"
    if ratio > 0.6:
        return "warn", "Aléjate"
    return "ok", "Distancia OK"


def assess_detection(detected_ratio: float) -> Tuple[str, str]:
    """Evalúa la estabilidad de detección reciente."""
    if detected_ratio < 0.3:
        return "bad", "Sin rostro"
    if detected_ratio < 0.7:
        return "warn", "Detección irregular"
    return "ok", "Detección OK"


# -----------------------------------------------------------------------------
# CALIBRADOR: flujo interactivo
# -----------------------------------------------------------------------------
@dataclass
class _PhaseData:
    """ROIs cacheadas durante una fase de captura."""
    name: str
    rois: List[np.ndarray] = field(default_factory=list)
    smile_count_runtime: int = 0   # con thresholds actuales (referencia)
    brow_means: List[float] = field(default_factory=list)
    mouth_means: List[float] = field(default_factory=list)


class Calibrator:
    """Ejecuta la calibración usando una cámara ya abierta.

    Uso típico::

        cap = cv2.VideoCapture(0)
        cal = Calibrator(cap, window_name="Rage Tracker")
        profile = cal.run_full_calibration()
        if profile:
            profile.save()
    """

    # Fases de captura (orden, etiqueta, color, duración s)
    PHASES = [
        ("neutral", "Expresión NEUTRAL — relájate", hud.COLOR_NEUTRAL, 3.0),
        ("happy",   "SONRÍE de forma natural",      hud.COLOR_HAPPY,   3.0),
        ("angry",   "Pon cara SERIA / ENFADADA",    hud.COLOR_ANGRY,   3.0),
    ]
    COUNTDOWN_S = 3
    ASSESSMENT_S = 2.0

    def __init__(self, cap: cv2.VideoCapture, window_name: str = "Rage Tracker - Calibracion"):
        self.cap = cap
        self.window_name = window_name
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.smile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_smile.xml"
        )

    # ----- API pública ------------------------------------------------------
    def run_full_calibration(self) -> Optional[CalibrationProfile]:
        """Ejecuta el flujo completo. Devuelve el perfil o None si se canceló."""
        env = self._run_environment_assessment()
        if env is None:
            return None

        phase_data: List[_PhaseData] = []
        for phase_name, instruction, accent, duration in self.PHASES:
            if not self._show_countdown(instruction, accent):
                return None
            data = self._capture_phase(phase_name, instruction, accent, duration)
            if data is None:
                return None
            phase_data.append(data)

        thresholds = self._compute_thresholds(phase_data)
        baselines = {
            d.name: {
                "frames_captured": len(d.rois),
                "brow_mean": float(np.mean(d.brow_means)) if d.brow_means else 0.0,
                "mouth_mean": float(np.mean(d.mouth_means)) if d.mouth_means else 0.0,
            }
            for d in phase_data
        }

        profile = CalibrationProfile(
            profile_name="user",
            created_at=datetime.now().isoformat(timespec="seconds"),
            environment=env,
            thresholds=thresholds,
            baselines=baselines,
        )

        self._show_summary(profile)
        return profile

    # ----- Etapas internas --------------------------------------------------
    def _run_environment_assessment(self) -> Optional[Dict]:
        """Muestra mensaje + captura ~2s para medir brillo y tamaño de cara."""
        brightnesses: List[float] = []
        face_widths: List[int] = []
        detections = 0
        total = 0

        start = time.time()
        while time.time() - start < self.ASSESSMENT_S:
            ok, frame = self.cap.read()
            if not ok:
                break
            total += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightnesses.append(float(gray.mean()))
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.3, minNeighbors=5, minSize=(100, 100)
            )
            if len(faces) > 0:
                detections += 1
                face_widths.append(int(faces[0][2]))

            hud.draw_centered_message(
                frame,
                title="Analizando entorno...",
                subtitle="Mantente quieto frente a la cámara",
                countdown=int(self.ASSESSMENT_S - (time.time() - start)) + 1,
                accent_color=hud.COLOR_CYAN,
            )
            cv2.imshow(self.window_name, frame)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                return None

        env = {
            "avg_brightness": round(float(np.mean(brightnesses)), 1) if brightnesses else 0.0,
            "avg_face_width_px": int(np.mean(face_widths)) if face_widths else 0,
            "detection_rate": round(detections / total, 2) if total else 0.0,
            "frames_sampled": total,
        }
        return env

    def _show_countdown(self, instruction: str, accent_color) -> bool:
        """Cuenta atrás de COUNTDOWN_S segundos antes de la captura."""
        start = time.time()
        while True:
            remaining = self.COUNTDOWN_S - (time.time() - start)
            if remaining <= 0:
                return True
            ok, frame = self.cap.read()
            if not ok:
                return False

            hud.draw_centered_message(
                frame,
                title=instruction,
                subtitle="Prepárate... la captura empezará en",
                countdown=int(remaining) + 1,
                accent_color=accent_color,
            )
            cv2.imshow(self.window_name, frame)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                return False

    def _capture_phase(self, name: str, instruction: str, accent, duration: float) -> Optional[_PhaseData]:
        """Captura `duration` segundos de ROIs faciales para esta fase."""
        data = _PhaseData(name=name)
        start = time.time()
        sample_every = 0.15  # un frame cacheado cada ~150ms para no saturar
        next_sample_at = start

        while True:
            elapsed = time.time() - start
            if elapsed >= duration:
                break
            ok, frame = self.cap.read()
            if not ok:
                return None
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.3, minNeighbors=5, minSize=(100, 100)
            )

            if len(faces) > 0 and time.time() >= next_sample_at:
                x, y, w, h = faces[0]
                roi = gray[y:y + h, x:x + w].copy()
                data.rois.append(roi)
                # Estadísticas adicionales sobre la cara
                brow = roi[0:int(h * 0.35), :]
                mouth = roi[int(h * 0.6):, :]
                data.brow_means.append(float(brow.mean()))
                data.mouth_means.append(float(mouth.mean()))
                next_sample_at = time.time() + sample_every

            # Dibujo de la fase: rectángulo + barra de progreso + instrucción
            for (x, y, w, h) in faces[:1]:
                hud.draw_corner_box(frame, x, y, w, h, accent, thickness=3, pulse_t=time.time())

            h_f, w_f = frame.shape[:2]
            hud.draw_panel(frame, 0, 0, w_f, 70, alpha=0.65, border_color=accent)
            hud.draw_text(frame, "CALIBRACIÓN", (16, 24), 0.55, hud.COLOR_TEXT_DIM, 1)
            hud.draw_text(frame, instruction, (16, 52), 0.7, accent, 1, shadow=True)

            # Barra de progreso de la fase
            bar_y = h_f - 50
            hud.draw_text(frame, f"Capturando {name}...  {len(data.rois)} muestras",
                          (16, bar_y - 6), 0.45, hud.COLOR_TEXT_DIM, 1)
            hud.draw_progress_bar(
                frame, 16, bar_y, w_f - 32, 12,
                value=elapsed / duration * 100, color=accent,
            )

            cv2.imshow(self.window_name, frame)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                return None

        return data

    def _compute_thresholds(self, phases: List[_PhaseData]) -> Dict:
        """Busca en rejilla los parámetros óptimos del detector de sonrisa.

        Maximiza: smile_rate(happy) - max(smile_rate(neutral), smile_rate(angry)),
        con una penalización si el detector no dispara nunca en happy.
        """
        by_name = {p.name: p for p in phases}
        happy = by_name.get("happy")
        if not happy or not happy.rois:
            # Sin datos válidos: devolver defaults
            return dict(DEFAULT_THRESHOLDS)

        scale_grid = [1.5, 1.6, 1.7, 1.8, 1.9, 2.0]
        neighbor_grid = [12, 15, 18, 22, 25, 28]

        best = None
        best_score = -1e9

        for sf in scale_grid:
            for mn in neighbor_grid:
                rates: Dict[str, float] = {}
                for phase in phases:
                    if not phase.rois:
                        rates[phase.name] = 0.0
                        continue
                    hits = 0
                    for roi in phase.rois:
                        smiles = self.smile_cascade.detectMultiScale(
                            roi, scaleFactor=sf, minNeighbors=mn, minSize=(30, 30)
                        )
                        if len(smiles) > 0:
                            hits += 1
                    rates[phase.name] = hits / len(phase.rois)

                happy_r = rates.get("happy", 0.0)
                neutral_r = rates.get("neutral", 0.0)
                angry_r = rates.get("angry", 0.0)

                # Penalizamos fuerte si "happy" no llega al 50%
                if happy_r < 0.5:
                    score = happy_r - max(neutral_r, angry_r) - 0.5
                else:
                    score = happy_r - max(neutral_r, angry_r)

                if score > best_score:
                    best_score = score
                    best = (sf, mn, rates)

        thresholds = dict(DEFAULT_THRESHOLDS)
        if best is not None:
            sf, mn, rates = best
            thresholds["smile_scale_factor"] = sf
            thresholds["smile_min_neighbors"] = mn
            # Ajuste fino de velocidad: si la detección es muy fiable, reaccionar antes
            if rates.get("happy", 0.0) > 0.85 and rates.get("angry", 0.0) < 0.15:
                thresholds["frames_between_counts"] = 10
                thresholds["emotion_confirmation_frames"] = 5
            elif rates.get("happy", 0.0) < 0.7:
                thresholds["frames_between_counts"] = 18
                thresholds["emotion_confirmation_frames"] = 8
            thresholds["_grid_search_best_score"] = round(best_score, 3)
            thresholds["_grid_search_rates"] = {k: round(v, 2) for k, v in rates.items()}

        return thresholds

    def _show_summary(self, profile: CalibrationProfile) -> None:
        """Pantalla final con resumen de la calibración."""
        end_at = time.time() + 3.5
        while time.time() < end_at:
            ok, frame = self.cap.read()
            if not ok:
                break
            h_f, w_f = frame.shape[:2]
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w_f, h_f), hud.COLOR_BG_DARK, -1)
            cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

            hud.draw_text(frame, "CALIBRACIÓN COMPLETADA", (w_f // 2 - 200, 80),
                          0.9, hud.COLOR_HAPPY, 2, shadow=True)
            t = profile.thresholds
            lines = [
                f"smile_scale_factor   = {t.get('smile_scale_factor')}",
                f"smile_min_neighbors  = {t.get('smile_min_neighbors')}",
                f"frames_between_counts= {t.get('frames_between_counts')}",
                f"brillo medio         = {profile.environment.get('avg_brightness')}",
                f"cara media (px)      = {profile.environment.get('avg_face_width_px')}",
            ]
            for i, line in enumerate(lines):
                hud.draw_text(frame, line, (w_f // 2 - 220, 140 + i * 32),
                              0.55, hud.COLOR_TEXT, 1, shadow=True)

            cv2.imshow(self.window_name, frame)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                break
