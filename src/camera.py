"""
RAGE TRACKER - Detector de emociones (refactor con HUD + auto-calibración)
==========================================================================
Cambios principales respecto a la versión original:

1. Toda la pintura del overlay pasa por src/hud.py (HUD estilo cyberpunk).
2. Soporta CalibrationProfile: los umbrales se cargan del perfil del usuario
   si existe, con fallback a los valores por defecto del proyecto.
3. Modo test (test_mode=True): habilita todo el HUD pero NO genera resumen
   para CSV (el caller debe respetar esta semántica).
4. Hotkeys ampliados:  [Q] terminar  [R] reiniciar  [P] pausa  [C] recalibrar
5. Métricas en tiempo real:
   - FPS de procesamiento
   - Sparkline rodante de los últimos ~30s
   - Pills de calidad (luz, distancia, detección)
6. Filosofía de detección sin cambios (sonrisa = feliz, no sonrisa = enfadado).
7. Fase 3: soporte opcional de micrófono vía audio_monitor (duck-typing).
   Añade VU meter en el HUD y fusiona métricas de gritos en el summary.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from typing import Optional, Tuple

import cv2
import numpy as np

from src import hud
from src.calibration import (
    CalibrationProfile,
    Calibrator,
    assess_lighting,
    assess_distance,
    assess_detection,
)


# Hotkeys mostrados en la franja inferior
HOTKEYS_RUN = [
    ("Q", "Terminar"),
    ("R", "Reiniciar"),
    ("P", "Pausa"),
    ("C", "Recalibrar"),
]
HOTKEYS_TEST = [
    ("Q", "Terminar test"),
    ("R", "Reiniciar"),
    ("C", "Recalibrar"),
]


class EmotionDetector:
    """Detector de emociones para una sesión de juego.

    Args:
        game_name: nombre del juego (texto libre, se muestra en el HUD).
        test_mode: si True, no se persiste nada; modo prueba de calibración.
        profile: perfil de calibración a aplicar. Si None, intenta cargar
            data/calibration_profile.json; si tampoco existe, usa defaults.
    """

    WINDOW_NAME = "Rage Tracker"

    def __init__(
        self,
        game_name: str,
        test_mode: bool = False,
        profile: Optional[CalibrationProfile] = None,
        audio_monitor: Optional[object] = None,
        insult_detector: Optional[object] = None,
    ):
        self.game_name = game_name
        self.test_mode = test_mode
        # Monitor de micrófono opcional (Fase 3). Duck-typing: solo asumo que
        # expone .level (0..100), .threshold_pct, .is_screaming y .get_summary().
        # Si es None, el comportamiento es idéntico al de la versión anterior.
        self.audio_monitor = audio_monitor
        self.insult_detector = insult_detector

        # Cargar perfil de calibración (con fallback a defaults)
        self.profile = profile or CalibrationProfile.load() or CalibrationProfile()
        self.config = dict(self.profile.thresholds)

        # Clasificadores Haar
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.smile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_smile.xml"
        )
        self.eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml"
        )

        # Estado de detección
        self.emotion_counts = {"neutral": 0, "happy": 0, "angry": 0}
        self.emotion_history = []      # historial detallado para CSV
        self.peak_rage_moments = []
        self.happiness_streaks = []
        self.current_streak = {"emotion": "neutral", "count": 0, "start_time": time.time()}

        self.start_time = time.time()
        self.pause_offset = 0.0        # acumulado de tiempo en pausa
        self.pause_start: Optional[float] = None
        self.paused = False

        self.last_emotion = "neutral"
        self.emotion_threshold = 8
        self.emotion_counter = 0
        self.frame_count = 0
        self.total_frames = 0

        # Métricas en vivo
        self._fps_window = deque(maxlen=30)
        self._sparkline = deque(maxlen=180)   # ~30s @ 6Hz de muestreo
        self._last_sparkline_t = 0.0
        self._detection_window = deque(maxlen=30)  # 1 si hubo cara, 0 si no
        self._last_face: Optional[Tuple[int, int, int, int]] = None
        self._last_confirmed_t = 0.0

    # =========================================================================
    # API pública
    # =========================================================================
    def run(self) -> Optional[dict]:
        """Ejecuta el bucle principal. Devuelve el resumen de la sesión o None
        si la sesión es modo test (o si falla la cámara)."""
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("❌ Error: no se pudo abrir la cámara.")
            return None

        # Intentar resolución decente; si la webcam no la soporta, OpenCV cae a la nativa
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        mode_str = "TEST" if self.test_mode else "SESIÓN"
        print(f"\n🎮 {mode_str} iniciada para: {self.game_name or '(sin juego)'}")
        print("Atajos:  [Q] terminar  [R] reiniciar  [P] pausa  [C] recalibrar\n")

        last_frame_t = time.time()
        current_emotion = "neutral"
        current_confidence = 0

        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                # FPS
                now = time.time()
                dt = now - last_frame_t
                if dt > 0:
                    self._fps_window.append(1.0 / dt)
                last_frame_t = now

                self.total_frames += 1
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Detección de cara
                faces = self.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.3, minNeighbors=5, minSize=(100, 100)
                )
                self._detection_window.append(1 if len(faces) > 0 else 0)

                if not self.paused and len(faces) > 0:
                    face = tuple(int(v) for v in faces[0])
                    self._last_face = face
                    current_emotion, current_confidence = self._detect_emotion(gray, face)
                    self._update_emotion_count(current_emotion, current_confidence)
                elif self.paused:
                    current_emotion = "neutral"
                    current_confidence = 0

                # Muestreo del sparkline a ritmo fijo (~6Hz) para no saturar la deque
                if now - self._last_sparkline_t >= (1 / 6):
                    self._sparkline.append(current_emotion if not self.paused else "neutral")
                    self._last_sparkline_t = now

                # Pintar HUD completo
                self._draw_hud(frame, gray, current_emotion, current_confidence)

                cv2.imshow(self.WINDOW_NAME, frame)

                # Input de teclado
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                elif key == ord("r"):
                    self._reset_counters()
                    if self.audio_monitor is not None:
                        try:
                            self.audio_monitor.reset()
                        except Exception:
                            pass
                elif key == ord("p") and not self.test_mode:
                    self._toggle_pause()
                elif key == ord("c"):
                    self._recalibrate(cap)
                    last_frame_t = time.time()
        finally:
            cap.release()
            cv2.destroyAllWindows()

        if self.test_mode:
            return None
        return self.get_session_summary()

    def get_session_summary(self) -> dict:
        """Genera resumen de la sesión (mismo schema que la versión original
        para no romper data_manager.py)."""
        total_time = int(self._elapsed())
        total_emotions = sum(self.emotion_counts.values())
        percentages = {
            e: (c / total_emotions * 100) if total_emotions > 0 else 0
            for e, c in self.emotion_counts.items()
        }
        recent = [h["emotion"] for h in self.emotion_history[-10:]]
        trend = max(set(recent), key=recent.count) if recent else "neutral"

        summary = {
            "game": self.game_name,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": total_time,
            "happy_count": self.emotion_counts["happy"],
            "angry_count": self.emotion_counts["angry"],
            "neutral_count": self.emotion_counts["neutral"],
            "happy_percentage": round(percentages["happy"], 2),
            "angry_percentage": round(percentages["angry"], 2),
            "neutral_percentage": round(percentages["neutral"], 2),
            "peak_rage_count": len(self.peak_rage_moments),
            "happiness_streaks": len(self.happiness_streaks),
            "emotional_trend": trend,
            "total_frames": self.total_frames,
        }
        if self.audio_monitor is not None:
            try:
                summary.update(self.audio_monitor.get_summary())
            except Exception:
                pass
        return summary

    # =========================================================================
    # Detección
    # =========================================================================
    def _detect_emotion(self, gray: np.ndarray, face: Tuple[int, int, int, int]) -> Tuple[str, int]:
        """Lógica binaria original: sonrisa => happy, en otro caso => angry.

        Conservada porque es la decisión de diseño explícita del proyecto
        ("MODO DEMO BINARIO"). La calibración solo ajusta los parámetros
        del detector de sonrisa, no la lógica.
        """
        x, y, w, h = face
        roi_gray = gray[y:y + h, x:x + w]

        smiles = self.smile_cascade.detectMultiScale(
            roi_gray,
            scaleFactor=self.config["smile_scale_factor"],
            minNeighbors=self.config["smile_min_neighbors"],
            minSize=tuple(self.config["smile_min_size"]),
        )
        eyes = self.eye_cascade.detectMultiScale(
            roi_gray,
            scaleFactor=self.config["eye_scale_factor"],
            minNeighbors=self.config["eye_min_neighbors"],
            minSize=tuple(self.config["eye_min_size"]),
        )

        if len(smiles) > 0:
            return "happy", 85 + min(len(smiles) * 5, 15)
        if len(eyes) < 2:
            return "neutral", 30
        return "angry", 80

    def _update_emotion_count(self, emotion: str, confidence: int) -> None:
        """Confirma y cuenta emociones con histéresis para evitar parpadeo."""
        # Neutral de baja confianza → tratar como angry (lógica del demo)
        if emotion == "neutral" and confidence < 50:
            emotion = "angry"
            confidence = 60

        if emotion == self.last_emotion:
            self.emotion_counter += 1
        else:
            self.emotion_counter = 0
            self.last_emotion = emotion

        threshold = self.emotion_threshold
        if emotion == "neutral":
            threshold = self.emotion_threshold * 4

        if self.emotion_counter >= threshold:
            self.frame_count += 1
            if self.frame_count >= self.config["frames_between_counts"]:
                self.emotion_counts[emotion] += 1
                self.frame_count = 0
                t = self._elapsed()
                self.emotion_history.append(
                    {"timestamp": t, "emotion": emotion, "confidence": confidence}
                )
                if emotion == "angry" and confidence > 70:
                    self.peak_rage_moments.append(t)
                self._update_streak(emotion)
                self._last_confirmed_t = time.time()

    def _update_streak(self, emotion: str) -> None:
        if self.current_streak["emotion"] == emotion:
            self.current_streak["count"] += 1
        else:
            if self.current_streak["count"] >= 3 and self.current_streak["emotion"] == "happy":
                self.happiness_streaks.append(
                    {
                        "count": self.current_streak["count"],
                        "duration": time.time() - self.current_streak["start_time"],
                    }
                )
            self.current_streak = {
                "emotion": emotion,
                "count": 1,
                "start_time": time.time(),
            }

    # =========================================================================
    # Estado: pausa, reset, recalibración
    # =========================================================================
    def _elapsed(self) -> float:
        """Tiempo de sesión efectivo (descontando pausas)."""
        end = self.pause_start if self.paused else time.time()
        return end - self.start_time - self.pause_offset

    def _toggle_pause(self) -> None:
        if self.paused:
            # Reanudar
            if self.pause_start is not None:
                self.pause_offset += time.time() - self.pause_start
            self.pause_start = None
            self.paused = False
        else:
            self.pause_start = time.time()
            self.paused = True

    def _reset_counters(self) -> None:
        self.emotion_counts = {"neutral": 0, "happy": 0, "angry": 0}
        self.emotion_history = []
        self.peak_rage_moments = []
        self.happiness_streaks = []
        self.current_streak = {"emotion": "neutral", "count": 0, "start_time": time.time()}
        self.start_time = time.time()
        self.pause_offset = 0.0
        self._sparkline.clear()
        print("✅ Contadores reiniciados.")

    def _recalibrate(self, cap: cv2.VideoCapture) -> None:
        """Recalibra en caliente sin destruir la cámara. Aplica el nuevo perfil."""
        print("\n🔁 Recalibrando...")
        cv2.destroyWindow(self.WINDOW_NAME)
        calibrator = Calibrator(cap, window_name=self.WINDOW_NAME)
        profile = calibrator.run_full_calibration()
        if profile is not None:
            profile.save()
            self.profile = profile
            self.config = dict(profile.thresholds)
            print("✅ Nuevo perfil aplicado.")
        else:
            print("⚠️  Calibración cancelada, se mantiene el perfil anterior.")

    # =========================================================================
    # HUD
    # =========================================================================
    def _draw_hud(
        self,
        frame: np.ndarray,
        gray: np.ndarray,
        emotion: str,
        confidence: int,
    ) -> None:
        h, w = frame.shape[:2]

        # 1. Bounding box sobre el rostro detectado (con pulso si recién confirmado)
        if self._last_face is not None:
            x, y, fw, fh = self._last_face
            color = hud.emotion_color(emotion)
            # Mostrar pulso solo si hubo confirmación reciente (< 0.6s)
            pulse_t = time.time() if (time.time() - self._last_confirmed_t) < 0.6 else 0.0
            hud.draw_corner_box(frame, x, y, fw, fh, color, thickness=3, pulse_t=pulse_t)

        # 2. Barra superior (REC, juego, timer, fps)
        fps = sum(self._fps_window) / len(self._fps_window) if self._fps_window else 0.0
        hud.draw_top_bar(
            frame,
            game_name=self.game_name,
            elapsed_s=self._elapsed(),
            fps=fps,
            blink_t=time.time(),
            test_mode=self.test_mode,
            paused=self.paused,
        )

        # 3. Tarjeta de emoción (izquierda)
        card_w = 270
        card_h = 130
        margin = 14
        hud.draw_emotion_card(
            frame,
            x=margin, y=h - 30 - card_h - 110,
            w=card_w, h=card_h,
            emotion=emotion,
            confidence=confidence,
            streak=self.current_streak["count"] if not self.paused else 0,
        )

        # 4. Tarjeta de contadores (debajo de la de emoción)
        hud.draw_counters_card(
            frame,
            x=margin, y=h - 30 - 110,
            w=card_w, h=104,
            happy_count=self.emotion_counts["happy"],
            angry_count=self.emotion_counts["angry"],
        )

        # 5. Sparkline (centro inferior, ancho restante)
        spark_x = margin + card_w + 14
        spark_w = w - spark_x - margin
        spark_h = 80
        hud.draw_sparkline(
            frame,
            x=spark_x, y=h - 30 - spark_h - 6,
            w=spark_w, h=spark_h,
            samples=self._sparkline,
            title=f"Historial reciente · {len(self._sparkline)} muestras",
        )

        # 6. Pills de calidad (encima del sparkline)
        lighting_state, lighting_msg = assess_lighting(gray)
        if self._last_face is not None:
            distance_state, distance_msg = assess_distance(self._last_face[2], w)
        else:
            distance_state, distance_msg = "bad", "Sin cara"
        detected_ratio = (sum(self._detection_window) / len(self._detection_window)
                          if self._detection_window else 0)
        detection_state, detection_msg = assess_detection(detected_ratio)

        hud.draw_quality_panel(
            frame,
            x=spark_x, y=h - 30 - spark_h - 50,
            lighting=lighting_state, lighting_msg=lighting_msg,
            distance=distance_state, distance_msg=distance_msg,
            detection=detection_state, detection_msg=detection_msg,
        )

        # 7. Tira de hotkeys
        hud.draw_hotkeys_strip(frame, HOTKEYS_TEST if self.test_mode else HOTKEYS_RUN)

        # 8. Mini-indicador de micrófono (solo si hay monitor de gritos activo)
        if self.audio_monitor is not None:
            self._draw_mic_indicator(frame)

        # 9. Contador de insultos (solo si hay detector activo)
        if self.insult_detector is not None:
            self._draw_insult_indicator(frame)

    def _draw_mic_indicator(self, frame: np.ndarray) -> None:
        """VU horizontal del micrófono en la esquina superior derecha.

        Dibujo con primitivas de cv2 + hud (sin tocar hud.py): barra de volumen
        con zonas verde/ámbar/rojo, marca del umbral y contador de gritos.
        Parpadea en rojo mientras se está gritando.
        """
        am = self.audio_monitor
        try:
            level = float(getattr(am, "level", 0.0))
            thr = float(getattr(am, "threshold_pct", 80.0))
            screaming = bool(getattr(am, "is_screaming", False))
            scream_count = int(am.get_summary().get("scream_count", 0))
        except Exception:
            return

        h, w = frame.shape[:2]
        pw, ph = 250, 60
        x = w - pw - 14
        y = 52  # justo bajo la barra superior

        flash = screaming and (int(time.time() * 4) % 2 == 0)
        border = hud.COLOR_ANGRY if flash else hud.COLOR_CYAN
        hud.draw_panel(frame, x, y, pw, ph, alpha=0.72, border_color=border)

        hud.draw_text(frame, "MIC / GRITOS", (x + 12, y + 18), 0.42,
                      hud.COLOR_TEXT_DIM, 1)
        hud.draw_text(frame, f"x{scream_count}", (x + pw - 52, y + 18), 0.5,
                      hud.COLOR_ANGRY if scream_count else hud.COLOR_TEXT_DIM, 1, shadow=True)

        # Barra de volumen con zonas de color
        bx, by, bw, bh = x + 12, y + 30, pw - 24, 14
        cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), hud.COLOR_BG_DARK, -1)
        fill = int(bw * max(0.0, min(100.0, level)) / 100.0)
        if level >= 90:
            fill_color = hud.COLOR_BAD
        elif level >= 60:
            fill_color = hud.COLOR_WARN
        else:
            fill_color = hud.COLOR_GOOD
        if fill > 0:
            cv2.rectangle(frame, (bx, by), (bx + fill, by + bh), fill_color, -1)
        # Marca del umbral de grito
        tx = bx + int(bw * max(0.0, min(100.0, thr)) / 100.0)
        cv2.line(frame, (tx, by - 2), (tx, by + bh + 2), hud.COLOR_ANGRY, 2, cv2.LINE_AA)
        cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), hud.COLOR_TEXT_DIM, 1)
        hud.draw_text(frame, f"{int(level):3d}%", (bx + bw - 40, by - 4), 0.4,
                      hud.COLOR_TEXT, 1)

    def _draw_insult_indicator(self, frame: np.ndarray) -> None:
        """Pastilla de insultos en la esquina superior derecha (bajo el indicador de mic)."""
        idet = self.insult_detector
        try:
            summary = idet.get_summary()
            count = int(summary.get("insult_count", 0))
        except Exception:
            return

        h, w = frame.shape[:2]
        pw, ph = 250, 36
        # Posición: bajo el indicador de micrófono (y=52+60=112) si existe, si no, y=52
        y_offset = 52 + (60 + 6 if self.audio_monitor is not None else 0)
        x = w - pw - 14
        y = y_offset + 4

        active = count > 0
        border = hud.COLOR_ANGRY if active else hud.COLOR_TEXT_DIM
        hud.draw_panel(frame, x, y, pw, ph, alpha=0.72, border_color=border)
        hud.draw_text(frame, "INSULTOS", (x + 12, y + 14), 0.42, hud.COLOR_TEXT_DIM, 1)
        count_color = hud.COLOR_ANGRY if active else hud.COLOR_TEXT_DIM
        hud.draw_text(frame, f"x{count}", (x + pw - 52, y + 14), 0.5,
                      count_color, 1, shadow=active)