"""
RAGE TRACKER - Calibración automática (pipeline v3: robusto a cualquier cara)
=============================================================================
NOVEDADES v3 (foco: el ÁNGULO de la cara ya no rompe la detección):
   - La ROI canónica se ALINEA por los ojos (deskew): se rota para dejar los
     ojos horizontales antes de buscar la sonrisa. Una cabeza ladeada hacía
     fallar el cascade de sonrisa aunque sonrieras; ahora trabaja casi frontal.
   - Rejilla y umbrales por defecto MÁS permisivos + scoring que prioriza no
     perder sonrisas (recall de happy) → menos "sonrío y no me detecta feliz".
   - El runtime pasa a binario puro feliz/enfadado (se elimina la medición de
     neutral). La calibración SIGUE capturando la fase neutral como negativo
     extra para medir falsos positivos con más fiabilidad.

Mejoras heredadas de v2:

1. PIPELINE NORMALIZADO (la clave para que funcione con cualquier cara):
   - CLAHE (ecualización adaptativa) sobre el frame antes de detectar caras
     → robusto a poca luz, contraluz y distintos tonos de piel.
   - La ROI facial se reescala SIEMPRE a un tamaño canónico (FACE_ROI_SIZE)
     y se le aplica CLAHE local → los parámetros calibrados son
     independientes de la distancia, la resolución de la webcam y la luz.
   - La sonrisa se busca SOLO en la región de la boca (mitad inferior de la
     ROI), eliminando los falsos positivos clásicos del cascade de sonrisa
     sobre ojos y fosas nasales (crítico con barba o gafas).

2. DETECCIÓN DE CARA ROBUSTA (FaceFinder, compartido con camera.py):
   - Cascade principal + fallback a frontalface_alt2 (mejor con caras
     difíciles, inclinación leve y gafas).
   - minSize relativo al tamaño del frame, no en píxeles absolutos.
   - Se elige la cara MÁS GRANDE (el usuario), no faces[0].
   - Suavizado exponencial del bounding box + periodo de gracia: un
     parpadeo del detector ya no corta la medición.

3. CALIBRACIÓN MÁS FIABLE:
   - Validación de muestras mínimas por fase, con reintento automático.
   - Búsqueda en rejilla sobre scaleFactor, minNeighbors Y minSize de la
     sonrisa (el tamaño de boca varía mucho entre personas).
   - Desempate hacia parámetros más estrictos (menos falsos positivos).
   - Métrica de calidad (separabilidad happy/no-happy) persistida y
     mostrada; avisa si la calibración salió pobre.
   - Aviso de contraluz (cara más oscura que el fondo).

4. VERSIONADO DEL PIPELINE:
   - Los perfiles guardan pipeline_version. Un perfil calibrado con el
     pipeline antiguo (ROIs sin normalizar) NO es compatible con el nuevo:
     al cargarlo se usan los defaults y se recomienda recalibrar.

Mantiene compatibilidad hacia atrás de API: CalibrationProfile, Calibrator,
assess_lighting/assess_distance/assess_detection conservan sus firmas.

Notas de diseño:
- No usamos time.sleep(): congelaría la ventana de OpenCV. Los tiempos se
  miden vía time.time() dentro del bucle de captura.
- Las ROIs cacheadas se guardan ya normalizadas (canónicas) para que la
  búsqueda en rejilla evalúe EXACTAMENTE lo que verá el runtime.
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


# -----------------------------------------------------------------------------
# CONSTANTES DEL PIPELINE
# -----------------------------------------------------------------------------
#: Versión del pipeline de preprocesado. Si cambia la forma de extraer/normalizar
#: ROIs, hay que incrementarla: los perfiles antiguos dejan de ser válidos.
#: v3: la ROI canónica se ALINEA por los ojos (deskew) → robusto a la
#:     inclinación/rotación de la cabeza, que era la mayor fuente de fallos.
PIPELINE_VERSION = 3

#: Lado (px) de la ROI facial canónica. Todo el análisis (sonrisa, ojos,
#: calibración) se hace sobre este tamaño fijo → invariante a distancia.
FACE_ROI_SIZE = 220

#: Fracción vertical donde empieza la región de la boca dentro de la ROI.
MOUTH_REGION_TOP = 0.55

#: Fracción vertical donde termina la región de los ojos dentro de la ROI.
EYE_REGION_BOTTOM = 0.62

#: La cara debe ocupar al menos este % del lado menor del frame para detectarla.
FACE_MIN_REL_SIZE = 0.14

#: Inclinación (grados) por debajo de la cual NO merece la pena rotar (ruido) y
#: por encima de la cual la estimación por ojos es poco fiable (no alineamos).
ALIGN_MIN_ANGLE = 3.0
ALIGN_MAX_ANGLE = 35.0


# Valores por defecto (recalibrados para el pipeline v2: ROI canónica + CLAHE
# + región de boca). Los píxeles de *_min_size son relativos a FACE_ROI_SIZE,
# por lo que ya no dependen de la distancia ni de la resolución de la cámara.
DEFAULT_THRESHOLDS: Dict = {
    "smile_scale_factor": 1.7,
    "smile_min_neighbors": 14,           # más permisivo: perder un happy molesta más
    "smile_min_size": [46, 23],          # sobre la región de boca de la ROI canónica
    "smile_window_frames": 9,            # ventana de votación temporal
    "smile_ratio_threshold": 0.4,        # % de frames con sonrisa para confirmar happy
    "eye_scale_factor": 1.1,
    "eye_min_neighbors": 6,
    "eye_min_size": [22, 22],            # sobre la ROI canónica
    # Conservados por compatibilidad con config_tool.py (no usados por el
    # detector binario actual):
    "brow_angry_threshold": 90,
    "brow_very_angry_threshold": 78,
    "mouth_tense_threshold": 88,
    "frames_between_counts": 14,
    "emotion_confirmation_frames": 6,
}


PROFILES_DIR = "data"
PROFILE_FILE = os.path.join(PROFILES_DIR, "calibration_profile.json")


# -----------------------------------------------------------------------------
# PREPROCESADO COMPARTIDO (calibración y runtime DEBEN usar exactamente esto)
# -----------------------------------------------------------------------------
def _make_clahe() -> "cv2.CLAHE":
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


#: Cascade de ojos compartido SOLO para la alineación de la ROI (lazy singleton).
#: El runtime tiene su propia instancia para el conteo de ojos; aquí lo usamos
#: para estimar la inclinación de la cara y enderezarla.
_ALIGN_EYE_CASCADE: Optional["cv2.CascadeClassifier"] = None


def _eye_cascade_for_align() -> "cv2.CascadeClassifier":
    global _ALIGN_EYE_CASCADE
    if _ALIGN_EYE_CASCADE is None:
        _ALIGN_EYE_CASCADE = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml"
        )
    return _ALIGN_EYE_CASCADE


def deskew_roi_by_eyes(roi_canon: np.ndarray) -> np.ndarray:
    """Endereza (deskew) la ROI canónica rotándola para que los ojos queden
    horizontales.

    Esta es la corrección clave para la robustez al ÁNGULO de la cara: los
    Haar cascades (sonrisa, ojos) son muy sensibles a la rotación en el plano,
    así que una cabeza ligeramente ladeada hacía fallar la detección de sonrisa
    aunque la persona estuviese sonriendo. Tras alinear, la boca y los ojos caen
    siempre en la misma franja de la ROI → el detector trabaja en condiciones
    casi frontales.

    Estrategia conservadora: solo rotamos si encontramos 2 ojos y la inclinación
    estimada está en un rango fiable (ALIGN_MIN_ANGLE..ALIGN_MAX_ANGLE). Fuera de
    ese rango devolvemos la ROI sin tocar (mejor no rotar que rotar basura).
    """
    h, w = roi_canon.shape[:2]
    upper = roi_canon[: int(h * EYE_REGION_BOTTOM), :]
    eyes = _eye_cascade_for_align().detectMultiScale(
        upper, scaleFactor=1.1, minNeighbors=5, minSize=(18, 18)
    )
    if len(eyes) < 2:
        return roi_canon

    # Tomamos los dos ojos más grandes y los ordenamos izquierda→derecha.
    eyes = sorted(eyes, key=lambda e: int(e[2]) * int(e[3]), reverse=True)[:2]
    (lx, ly, lw, lh), (rx, ry, rw, rh) = sorted(eyes, key=lambda e: int(e[0]))
    left_c = (lx + lw / 2.0, ly + lh / 2.0)
    right_c = (rx + rw / 2.0, ry + rh / 2.0)

    dx = right_c[0] - left_c[0]
    dy = right_c[1] - left_c[1]
    if abs(dx) < 1e-3:
        return roi_canon
    angle = np.degrees(np.arctan2(dy, dx))

    if abs(angle) < ALIGN_MIN_ANGLE or abs(angle) > ALIGN_MAX_ANGLE:
        return roi_canon

    center = (w / 2.0, h / 2.0)
    rot = cv2.getRotationMatrix2D(center, float(angle), 1.0)
    return cv2.warpAffine(
        roi_canon, rot, (w, h),
        flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
    )


def extract_face_roi(gray: np.ndarray, face: Tuple[int, int, int, int],
                     clahe: Optional["cv2.CLAHE"] = None,
                     align: bool = True) -> Optional[np.ndarray]:
    """Extrae la ROI facial NORMALIZADA (canónica) a partir del gris crudo.

    Pasos: recorte con clamping a los bordes → reescalado a FACE_ROI_SIZE
    → CLAHE local → alineación por ojos (deskew). Devuelve None si la caja
    es degenerada.

    Es la única vía válida para obtener ROIs: garantiza que la calibración
    y el runtime analizan imágenes idénticas en escala, contraste y rotación.
    `align=False` permite saltarse el deskew si el caller ya trabaja con caras
    frontales (no se usa en el flujo normal).
    """
    fh, fw = gray.shape[:2]
    x, y, w, h = (int(v) for v in face)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(fw, x + w), min(fh, y + h)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    roi = gray[y0:y1, x0:x1]
    interp = cv2.INTER_AREA if roi.shape[0] > FACE_ROI_SIZE else cv2.INTER_LINEAR
    roi = cv2.resize(roi, (FACE_ROI_SIZE, FACE_ROI_SIZE), interpolation=interp)
    if clahe is None:
        clahe = _make_clahe()
    roi = clahe.apply(roi)
    if align:
        roi = deskew_roi_by_eyes(roi)
    return roi


def detect_smile_hits(smile_cascade: "cv2.CascadeClassifier",
                      roi_canon: np.ndarray,
                      scale_factor: float,
                      min_neighbors: int,
                      min_size: Tuple[int, int]) -> int:
    """Cuenta detecciones de sonrisa SOLO en la región de la boca de la ROI
    canónica. Compartida entre la búsqueda en rejilla y el runtime."""
    h = roi_canon.shape[0]
    mouth = roi_canon[int(h * MOUTH_REGION_TOP):, :]
    smiles = smile_cascade.detectMultiScale(
        mouth,
        scaleFactor=float(scale_factor),
        minNeighbors=int(min_neighbors),
        minSize=(int(min_size[0]), int(min_size[1])),
    )
    return len(smiles)


class FaceFinder:
    """Detección de cara robusta y estable, compartida por calibración y runtime.

    - CLAHE global antes del cascade (robusto a luz / tono de piel).
    - Cascade principal con fallback a frontalface_alt2.
    - minSize relativo al frame (independiente de la resolución).
    - Selección de la cara más grande (el usuario).
    - Suavizado exponencial del box + periodo de gracia ante pérdidas breves.
    """

    GRACE_FRAMES = 10      # frames que se tolera perder la cara usando el último box
    SMOOTH_ALPHA = 0.35    # peso de la nueva medición en la media exponencial
    JUMP_RESET_FRAC = 0.6  # salto (relativo al ancho de cara) que resetea el suavizado

    def __init__(self):
        self._clahe = _make_clahe()
        self.cascades = [
            cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"),
            cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"),
        ]
        self._smooth_box: Optional[np.ndarray] = None
        self._miss_count = 0

    def preprocess(self, gray: np.ndarray) -> np.ndarray:
        """Ecualización adaptativa del frame completo (para el cascade de cara)."""
        return self._clahe.apply(gray)

    def reset(self) -> None:
        self._smooth_box = None
        self._miss_count = 0

    def find(self, gray_eq: np.ndarray) -> Tuple[Optional[Tuple[int, int, int, int]], bool]:
        """Busca la cara del usuario en un frame ya ecualizado.

        Returns:
            (box, fresh):
              box   -> (x, y, w, h) suavizado, o None si no hay cara fiable.
              fresh -> True si proviene de una detección real en este frame;
                       False si es el último box dentro del periodo de gracia.
        """
        fh, fw = gray_eq.shape[:2]
        min_side = max(60, int(min(fh, fw) * FACE_MIN_REL_SIZE))

        faces = ()
        for cascade in self.cascades:
            faces = cascade.detectMultiScale(
                gray_eq, scaleFactor=1.2, minNeighbors=5,
                minSize=(min_side, min_side),
            )
            if len(faces) > 0:
                break

        if len(faces) == 0:
            self._miss_count += 1
            if self._smooth_box is not None and self._miss_count <= self.GRACE_FRAMES:
                return tuple(int(v) for v in self._smooth_box), False
            self._smooth_box = None
            return None, False

        # La cara más grande es (casi siempre) el usuario sentado delante.
        face = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        meas = np.asarray(face, dtype=np.float64)
        self._miss_count = 0

        if self._smooth_box is None:
            self._smooth_box = meas
        else:
            # Si el salto es enorme (otra cara / falso positivo corregido),
            # reseteamos en lugar de arrastrar el box por la pantalla.
            jump = abs(meas[0] - self._smooth_box[0]) + abs(meas[1] - self._smooth_box[1])
            if jump > self._smooth_box[2] * self.JUMP_RESET_FRAC:
                self._smooth_box = meas
            else:
                a = self.SMOOTH_ALPHA
                self._smooth_box = (1.0 - a) * self._smooth_box + a * meas

        return tuple(int(v) for v in self._smooth_box), True


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
    pipeline_version: int = PIPELINE_VERSION

    @classmethod
    def load(cls, path: str = PROFILE_FILE) -> Optional["CalibrationProfile"]:
        """Carga un perfil del disco. Devuelve None si no existe o es inválido.

        Si el perfil fue creado con un pipeline anterior, sus parámetros de
        sonrisa/ojos NO son compatibles (se calibraron sobre ROIs sin
        normalizar): se sustituyen por los defaults y se recomienda recalibrar.
        """
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Perfiles antiguos no traen pipeline_version → versión 1.
            data.setdefault("pipeline_version", 1)
            # Fusiona con DEFAULT_THRESHOLDS para tolerar versiones antiguas
            merged = dict(DEFAULT_THRESHOLDS)
            merged.update(data.get("thresholds", {}))
            data["thresholds"] = merged
            # Descartar claves desconocidas de versiones futuras
            valid = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
            data = {k: v for k, v in data.items() if k in valid}
            profile = cls(**data)

            if profile.pipeline_version != PIPELINE_VERSION:
                # Aviso en ASCII puro: este camino se dispara SIEMPRE con perfiles
                # de pipelines antiguos, y en consolas Windows (cp1252) un emoji
                # haría reventar el arranque con UnicodeEncodeError.
                print(
                    "[!] El perfil de calibracion es de una version anterior del "
                    "pipeline de deteccion.\n"
                    "    Se usaran los valores por defecto. Ejecuta "
                    "`python main.py --calibrate` para recalibrar."
                )
                profile.thresholds = dict(DEFAULT_THRESHOLDS)
            return profile
        except (json.JSONDecodeError, TypeError, OSError) as e:
            print(f"[!] Perfil de calibracion invalido ({e}). Usando valores por defecto.")
            return None

    def save(self, path: str = PROFILE_FILE) -> None:
        """Persiste el perfil en disco."""
        self.pipeline_version = PIPELINE_VERSION
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)


# -----------------------------------------------------------------------------
# ASSESSMENTS DEL ENTORNO (usados también en tiempo real por el HUD)
# -----------------------------------------------------------------------------
def assess_lighting(gray_frame: np.ndarray) -> Tuple[str, str]:
    """Devuelve (estado, mensaje) sobre la iluminación.

    Estado: "ok" | "warn" | "bad". Evalúa brillo medio Y contraste: una
    imagen plana (poca desviación) degrada los Haar cascades aunque el
    brillo medio parezca correcto.
    """
    mean = float(gray_frame.mean())
    std = float(gray_frame.std())
    if mean < 45:
        return "bad", "Luz baja"
    if std < 22:
        return "warn", "Poco contraste"
    if mean < 75:
        return "warn", "Luz justa"
    if mean > 205:
        return "warn", "Luz alta"
    return "ok", "Luz OK"


def assess_distance(face_w: int, frame_w: int) -> Tuple[str, str]:
    """Evalúa la distancia a partir del ancho relativo de la cara."""
    if frame_w <= 0 or face_w <= 0:
        return "bad", "Sin cara"
    ratio = face_w / frame_w
    if ratio < 0.16:
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


def assess_backlight(face_mean: float, frame_mean: float) -> Tuple[str, str]:
    """Detecta contraluz: cara claramente más oscura que el fondo."""
    if face_mean <= 0:
        return "warn", "Sin datos de cara"
    if frame_mean - face_mean > 35:
        return "warn", "Contraluz: ilumina tu cara de frente"
    return "ok", "Sin contraluz"


# -----------------------------------------------------------------------------
# CALIBRADOR: flujo interactivo
# -----------------------------------------------------------------------------
@dataclass
class _PhaseData:
    """ROIs (canónicas) cacheadas durante una fase de captura."""
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

    # Fases de captura (orden, etiqueta, color, duración s).
    # "neutral" ya NO es una emoción medible en el juego: se captura solo como
    # muestra de referencia (cara relajada sin sonrisa) para que la búsqueda en
    # rejilla tenga más negativos y estime mejor los falsos positivos.
    PHASES = [
        ("neutral", "Cara RELAJADA (referencia)",   hud.COLOR_NEUTRAL, 3.0),
        ("happy",   "SONRÍE de forma natural",      hud.COLOR_HAPPY,   3.0),
        ("angry",   "Pon cara SERIA / ENFADADA",    hud.COLOR_ANGRY,   3.0),
    ]
    COUNTDOWN_S = 3
    ASSESSMENT_S = 2.0
    MIN_SAMPLES_PER_PHASE = 10   # por debajo de esto, la rejilla es ruido
    MAX_PHASE_RETRIES = 2

    # Rejilla de búsqueda (sobre la región de boca de la ROI canónica).
    # Sesgada hacia parámetros MÁS permisivos que antes: perder un "happy"
    # real (sonríes y no te detecta) es la queja principal, así que damos
    # margen a scaleFactor/minNeighbors/minSize bajos.
    SCALE_GRID = [1.4, 1.5, 1.6, 1.7, 1.8, 1.9]
    NEIGHBOR_GRID = [8, 11, 14, 18, 22]   # ASCENDENTE (requisito del corte temprano)
    MIN_W_GRID = [38, 46, 58]    # ancho mínimo de sonrisa; alto = ancho / 2

    def __init__(self, cap: cv2.VideoCapture, window_name: str = "Rage Tracker - Calibracion"):
        self.cap = cap
        self.window_name = window_name
        self.finder = FaceFinder()
        self.smile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_smile.xml"
        )
        self._clahe = _make_clahe()

    # ----- API pública ------------------------------------------------------
    def run_full_calibration(self) -> Optional[CalibrationProfile]:
        """Ejecuta el flujo completo. Devuelve el perfil o None si se canceló."""
        env = self._run_environment_assessment()
        if env is None:
            return None

        # Aviso temprano si el entorno es malo: calibrar con mala luz produce
        # un perfil malo. Avisamos pero dejamos continuar.
        warn_msgs = []
        state, msg = assess_lighting_from_env(env)
        if state != "ok":
            warn_msgs.append(msg)
        bstate, bmsg = assess_backlight(env.get("avg_face_brightness", 0.0),
                                        env.get("avg_brightness", 0.0))
        if bstate != "ok":
            warn_msgs.append(bmsg)
        if env.get("detection_rate", 0.0) < 0.5:
            warn_msgs.append("La cámara apenas detecta tu cara: revisa luz y encuadre")
        if warn_msgs:
            if not self._show_notice(
                "Entorno mejorable",
                " · ".join(warn_msgs),
                seconds=3.0,
                accent=hud.COLOR_WARN,
            ):
                return None

        phase_data: List[_PhaseData] = []
        for phase_name, instruction, accent, duration in self.PHASES:
            data = self._capture_phase_with_retries(phase_name, instruction, accent, duration)
            if data is None:
                return None
            phase_data.append(data)

        thresholds = self._compute_thresholds(phase_data)
        face_brightness = [float(np.mean(d.rois)) for d in phase_data if d.rois]
        baselines = {
            d.name: {
                "frames_captured": len(d.rois),
                "brow_mean": float(np.mean(d.brow_means)) if d.brow_means else 0.0,
                "mouth_mean": float(np.mean(d.mouth_means)) if d.mouth_means else 0.0,
            }
            for d in phase_data
        }
        env["avg_face_brightness_calibrated"] = (
            round(float(np.mean(face_brightness)), 1) if face_brightness else 0.0
        )

        profile = CalibrationProfile(
            profile_name="user",
            created_at=datetime.now().isoformat(timespec="seconds"),
            environment=env,
            thresholds=thresholds,
            baselines=baselines,
            pipeline_version=PIPELINE_VERSION,
        )

        self._show_summary(profile)
        return profile

    # ----- Etapas internas --------------------------------------------------
    def _run_environment_assessment(self) -> Optional[Dict]:
        """Muestra mensaje + captura ~2s para medir brillo, contraste,
        tamaño de cara, contraluz y estabilidad de detección."""
        brightnesses: List[float] = []
        contrasts: List[float] = []
        face_widths: List[int] = []
        face_brightnesses: List[float] = []
        detections = 0
        total = 0

        self.finder.reset()
        start = time.time()
        while time.time() - start < self.ASSESSMENT_S:
            ok, frame = self.cap.read()
            if not ok:
                break
            total += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightnesses.append(float(gray.mean()))
            contrasts.append(float(gray.std()))

            box, fresh = self.finder.find(self.finder.preprocess(gray))
            if box is not None and fresh:
                detections += 1
                face_widths.append(int(box[2]))
                x, y, w, h = box
                fh, fw = gray.shape[:2]
                crop = gray[max(0, y):min(fh, y + h), max(0, x):min(fw, x + w)]
                if crop.size:
                    face_brightnesses.append(float(crop.mean()))

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
            "avg_contrast": round(float(np.mean(contrasts)), 1) if contrasts else 0.0,
            "avg_face_width_px": int(np.mean(face_widths)) if face_widths else 0,
            "avg_face_brightness": round(float(np.mean(face_brightnesses)), 1)
            if face_brightnesses else 0.0,
            "detection_rate": round(detections / total, 2) if total else 0.0,
            "frames_sampled": total,
            "frame_size": self._frame_size(),
        }
        return env

    def _frame_size(self) -> List[int]:
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        return [w, h]

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

    def _show_notice(self, title: str, subtitle: str, seconds: float, accent) -> bool:
        """Pantalla informativa breve. Devuelve False si el usuario cancela."""
        end_at = time.time() + seconds
        while time.time() < end_at:
            ok, frame = self.cap.read()
            if not ok:
                return False
            hud.draw_centered_message(
                frame,
                title=title,
                subtitle=subtitle,
                countdown=int(end_at - time.time()) + 1,
                accent_color=accent,
            )
            cv2.imshow(self.window_name, frame)
            if (cv2.waitKey(1) & 0xFF) == ord("q"):
                return False
        return True

    def _capture_phase_with_retries(self, name: str, instruction: str,
                                    accent, duration: float) -> Optional[_PhaseData]:
        """Captura una fase, reintentando si no se juntan muestras suficientes.

        Sin esto, una fase con 2-3 ROIs (cara perdida, mala luz) contamina la
        búsqueda en rejilla y produce perfiles inservibles silenciosamente.
        """
        attempts = 0
        while True:
            if not self._show_countdown(instruction, accent):
                return None
            data = self._capture_phase(name, instruction, accent, duration)
            if data is None:
                return None
            if len(data.rois) >= self.MIN_SAMPLES_PER_PHASE:
                return data
            attempts += 1
            if attempts > self.MAX_PHASE_RETRIES:
                print(f"⚠️  Fase '{name}': solo {len(data.rois)} muestras tras "
                      f"{attempts} intentos. Se continúa, pero la calibración "
                      f"puede ser poco fiable.")
                return data
            if not self._show_notice(
                "Pocas muestras capturadas",
                f"Solo {len(data.rois)} frames con cara en '{name}'. "
                "Centra tu cara y mejora la luz. Repetimos la fase.",
                seconds=3.0,
                accent=accent,
            ):
                return None

    def _capture_phase(self, name: str, instruction: str, accent, duration: float) -> Optional[_PhaseData]:
        """Captura `duration` segundos de ROIs faciales NORMALIZADAS."""
        data = _PhaseData(name=name)
        start = time.time()
        sample_every = 0.15  # un frame cacheado cada ~150ms para no saturar
        next_sample_at = start

        self.finder.reset()
        while True:
            elapsed = time.time() - start
            if elapsed >= duration:
                break
            ok, frame = self.cap.read()
            if not ok:
                return None
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            box, fresh = self.finder.find(self.finder.preprocess(gray))

            # Solo cacheamos ROIs de detecciones REALES (fresh), nunca del
            # periodo de gracia: para calibrar queremos datos limpios.
            if box is not None and fresh and time.time() >= next_sample_at:
                roi = extract_face_roi(gray, box, self._clahe)
                if roi is not None:
                    data.rois.append(roi)
                    h = roi.shape[0]
                    brow = roi[0:int(h * 0.35), :]
                    mouth = roi[int(h * MOUTH_REGION_TOP):, :]
                    data.brow_means.append(float(brow.mean()))
                    data.mouth_means.append(float(mouth.mean()))
                    next_sample_at = time.time() + sample_every

            # Dibujo de la fase: rectángulo + barra de progreso + instrucción
            if box is not None:
                x, y, w, h = box
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

        Mejoras v2:
        - Trabaja sobre ROIs canónicas + región de boca (idéntico al runtime).
        - Explora también minSize de la sonrisa (el tamaño de boca varía
          mucho entre personas).
        - Desempata hacia minNeighbors más altos (menos falsos positivos).
        - Persiste la separabilidad como métrica de calidad y avisa si es baja.
        """
        by_name = {p.name: p for p in phases}
        happy = by_name.get("happy")
        if not happy or not happy.rois:
            # Sin datos válidos: devolver defaults
            return dict(DEFAULT_THRESHOLDS)

        # Precalcular recortes de boca por fase: la rejilla evalúa miles de
        # combinaciones y no queremos recortar en cada iteración.
        mouth_crops: Dict[str, List[np.ndarray]] = {}
        for phase in phases:
            crops = []
            for roi in phase.rois:
                h = roi.shape[0]
                crops.append(roi[int(h * MOUTH_REGION_TOP):, :])
            mouth_crops[phase.name] = crops

        best = None
        best_key = None
        best_score = -1e9

        self._show_compute_progress(0.0)
        n_sf = len(self.SCALE_GRID)

        for i, sf in enumerate(self.SCALE_GRID):
            for min_w in self.MIN_W_GRID:
                min_size = (min_w, max(15, min_w // 2))

                # hits[fase][mn] = nº de crops con ≥1 sonrisa para ese mn.
                # Aprovechamos que detectMultiScale es MONÓTONO en
                # minNeighbors: si con el mn más bajo no hay detección,
                # con cualquier mn mayor tampoco → corte temprano por crop.
                hits: Dict[str, Dict[int, int]] = {
                    p.name: {mn: 0 for mn in self.NEIGHBOR_GRID} for p in phases
                }
                for phase in phases:
                    for crop in mouth_crops.get(phase.name, []):
                        for mn in self.NEIGHBOR_GRID:  # ascendente
                            smiles = self.smile_cascade.detectMultiScale(
                                crop, scaleFactor=sf, minNeighbors=mn,
                                minSize=min_size,
                            )
                            if len(smiles) == 0:
                                break
                            hits[phase.name][mn] += 1

                for mn in self.NEIGHBOR_GRID:
                    rates: Dict[str, float] = {}
                    for phase in phases:
                        n = len(mouth_crops.get(phase.name, []))
                        rates[phase.name] = hits[phase.name][mn] / n if n else 0.0

                    happy_r = rates.get("happy", 0.0)
                    neutral_r = rates.get("neutral", 0.0)
                    angry_r = rates.get("angry", 0.0)
                    false_r = max(neutral_r, angry_r)

                    # Objetivo: separar happy de no-happy, pero PRIORIZANDO no
                    # perder sonrisas. Por eso el recall de happy pesa más que
                    # el castigo por falsos positivos (1.0 vs 0.8), y penalizamos
                    # con dureza cuando happy no alcanza un recall razonable.
                    score = happy_r - 0.8 * false_r
                    if happy_r < 0.7:
                        score -= 0.6 * (0.7 - happy_r)   # proporcional, no escalón
                    if false_r > 0.4:
                        score -= 0.3                      # demasiados falsos: descartar

                    # Desempate determinista: ante igual score, preferir MÁS
                    # recall de happy (no perder sonrisas), luego MENOS falsos
                    # positivos y, por último, parámetros algo más permisivos
                    # (min_neighbors bajo) para que sonrisas sutiles cuenten.
                    key = (round(score, 4), round(happy_r, 3),
                           round(-false_r, 3), -mn)
                    if best_key is None or key > best_key:
                        best_key = key
                        best_score = score
                        best = (sf, mn, min_size, rates)
            self._show_compute_progress((i + 1) / n_sf * 100.0)

        thresholds = dict(DEFAULT_THRESHOLDS)
        if best is not None:
            sf, mn, min_size, rates = best
            happy_r = rates.get("happy", 0.0)
            false_r = max(rates.get("neutral", 0.0), rates.get("angry", 0.0))
            separation = happy_r - false_r

            thresholds["smile_scale_factor"] = sf
            thresholds["smile_min_neighbors"] = mn
            thresholds["smile_min_size"] = [int(min_size[0]), int(min_size[1])]

            # Adaptar la dinámica temporal a la fiabilidad real medida:
            if separation > 0.7 and false_r < 0.15:
                # Detector muy fiable: reaccionar antes y exigir menos votos.
                thresholds["frames_between_counts"] = 10
                thresholds["emotion_confirmation_frames"] = 5
                thresholds["smile_ratio_threshold"] = 0.45
            elif separation < 0.4:
                # Detector dudoso: más conservador para no contar ruido.
                thresholds["frames_between_counts"] = 18
                thresholds["emotion_confirmation_frames"] = 8
                thresholds["smile_ratio_threshold"] = 0.6

            thresholds["_grid_search_best_score"] = round(best_score, 3)
            thresholds["_grid_search_rates"] = {k: round(v, 2) for k, v in rates.items()}
            thresholds["_quality_separation"] = round(separation, 2)

            if separation < 0.4:
                print(
                    f"⚠️  Calibración con separabilidad baja ({separation:.2f}). "
                    "Consejos: más luz frontal, sonrisa más marcada en la fase "
                    "'happy', cara seria de verdad en 'angry'. Puedes recalibrar "
                    "cuando quieras con [C]."
                )

        return thresholds

    def _show_compute_progress(self, pct: float) -> None:
        """Feedback visual mientras corre la búsqueda en rejilla (bloqueante).

        Usa solo primitivas básicas del HUD (panel/texto/barra) para no
        depender de la firma de draw_centered_message sin cuenta atrás.
        """
        ok, frame = self.cap.read()
        if not ok:
            return
        h_f, w_f = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w_f, h_f), hud.COLOR_BG_DARK, -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        hud.draw_text(frame, "Calculando parámetros óptimos...",
                      (w_f // 2 - 220, h_f // 2 - 20), 0.8, hud.COLOR_CYAN, 2, shadow=True)
        hud.draw_text(frame, "Analizando tus muestras (no hace falta posar)",
                      (w_f // 2 - 220, h_f // 2 + 16), 0.5, hud.COLOR_TEXT_DIM, 1)
        hud.draw_progress_bar(frame, 16, h_f - 50, w_f - 32, 12,
                              value=pct, color=hud.COLOR_CYAN)
        cv2.imshow(self.window_name, frame)
        cv2.waitKey(1)

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

            t = profile.thresholds
            sep = t.get("_quality_separation", 0.0)
            quality = "EXCELENTE" if sep > 0.7 else ("BUENA" if sep >= 0.4 else "MEJORABLE")
            color = hud.COLOR_HAPPY if sep >= 0.4 else hud.COLOR_ANGRY

            hud.draw_text(frame, "CALIBRACIÓN COMPLETADA", (w_f // 2 - 200, 80),
                          0.9, color, 2, shadow=True)
            lines = [
                f"calidad              = {quality} ({sep})",
                f"smile_scale_factor   = {t.get('smile_scale_factor')}",
                f"smile_min_neighbors  = {t.get('smile_min_neighbors')}",
                f"smile_min_size       = {t.get('smile_min_size')}",
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


def assess_lighting_from_env(env: Dict) -> Tuple[str, str]:
    """Versión de assess_lighting que opera sobre el dict de entorno."""
    mean = float(env.get("avg_brightness", 0.0))
    std = float(env.get("avg_contrast", 100.0))
    if mean < 45:
        return "bad", "Luz baja: enciende una luz frontal"
    if std < 22:
        return "warn", "Poco contraste en la imagen"
    if mean < 75:
        return "warn", "Luz justa"
    if mean > 205:
        return "warn", "Luz alta / sobreexposición"
    return "ok", "Luz OK"
