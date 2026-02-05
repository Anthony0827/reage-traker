import cv2
import time
from datetime import datetime
import numpy as np


class EmotionDetector:
    def __init__(self, game_name):
        self.game_name = game_name
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.smile_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_smile.xml"
        )
        self.eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml"
        )
        
        # Contadores de emociones mejorados
        self.emotion_counts = {
            "neutral": 0,
            "happy": 0,
            "angry": 0
        }
        
        # Historial para análisis temporal
        self.emotion_history = []
        self.peak_rage_moments = []  # Momentos de mayor intensidad
        self.happiness_streaks = []   # Rachas de felicidad
        
        # Tiempos mejorados
        self.start_time = time.time()
        self.last_emotion = "neutral"
        self.emotion_threshold = 8  # Frames consecutivos (reducido para mayor sensibilidad)
        self.emotion_counter = 0
        self.frame_count = 0
        self.total_frames = 0
        
        # Configuración mejorada de umbrales
        self.config = {
            # Umbrales para sonrisa
            'smile_scale_factor': 1.7,
            'smile_min_neighbors': 18,
            'smile_min_size': (25, 25),
            
            # Umbrales para ojos
            'eye_scale_factor': 1.1,
            'eye_min_neighbors': 8,
            'eye_min_size': (15, 15),
            
            # Umbrales de intensidad (ajustados)
            'brow_angry_threshold': 75,      # Si brow_mean < esto, posible enojo
            'brow_very_angry_threshold': 65, # Muy enfadado
            'mouth_tense_threshold': 82,     # Boca tensa
            
            # Velocidad de conteo
            'frames_between_counts': 15,  # Cuenta cada 15 frames (0.5 seg aprox)
        }
        
        # Racha actual
        self.current_streak = {"emotion": "neutral", "count": 0, "start_time": time.time()}
        
    def detect_emotion(self, frame, gray, face):
        """Detecta la emoción basándose en características faciales - VERSIÓN MEJORADA"""
        x, y, w, h = face
        roi_gray = gray[y:y + h, x:x + w]
        roi_color = frame[y:y + h, x:x + w]
        
        # Detectar sonrisa con parámetros ajustados
        smiles = self.smile_cascade.detectMultiScale(
            roi_gray,
            scaleFactor=self.config['smile_scale_factor'],
            minNeighbors=self.config['smile_min_neighbors'],
            minSize=self.config['smile_min_size']
        )
        
        # Detectar ojos
        eyes = self.eye_cascade.detectMultiScale(
            roi_gray,
            scaleFactor=self.config['eye_scale_factor'],
            minNeighbors=self.config['eye_min_neighbors'],
            minSize=self.config['eye_min_size']
        )
        
        # Análisis de regiones faciales
        brow_region = roi_gray[0:int(h*0.35), :]
        brow_mean = brow_region.mean()
        
        mouth_region = roi_gray[int(h*0.6):, :]
        mouth_mean = mouth_region.mean()
        
        # Región de ojos para detectar tensión
        eye_region = roi_gray[int(h*0.2):int(h*0.5), :]
        eye_mean = eye_region.mean()
        
        # Calcular varianza para detectar tensión muscular
        brow_variance = np.var(brow_region)
        
        # Lógica de detección MEJORADA Y BALANCEADA
        emotion = "neutral"
        confidence = 0  # Nivel de confianza
        
        # PRIORIDAD 1: Sonrisa clara = Feliz
        if len(smiles) > 0:
            emotion = "happy"
            confidence = min(len(smiles) * 30, 100)
        
        # PRIORIDAD 2: Señales de enojo (múltiples indicadores)
        elif len(eyes) >= 2:
            anger_score = 0
            
            # Cejas oscuras/fruncidas
            if brow_mean < self.config['brow_angry_threshold']:
                anger_score += 30
            if brow_mean < self.config['brow_very_angry_threshold']:
                anger_score += 20
                
            # Boca tensa
            if mouth_mean < self.config['mouth_tense_threshold']:
                anger_score += 25
                
            # Alta varianza en cejas (tensión)
            if brow_variance > 200:
                anger_score += 15
            
            # Región de ojos tensa
            if eye_mean < 70:
                anger_score += 10
                
            if anger_score >= 40:  # Umbral de enojo
                emotion = "angry"
                confidence = min(anger_score, 100)
        
        # PRIORIDAD 3: Solo cejas muy fruncidas
        elif brow_mean < self.config['brow_very_angry_threshold']:
            emotion = "angry"
            confidence = 60
        
        return emotion, confidence
    
    def update_emotion_count(self, emotion, confidence):
        """Actualiza el contador de emociones con confirmación mejorada"""
        # Sistema de confirmación
        if emotion == self.last_emotion:
            self.emotion_counter += 1
        else:
            self.emotion_counter = 0
            self.last_emotion = emotion
        
        # Solo cuenta si la emoción se mantiene varios frames
        if self.emotion_counter >= self.emotion_threshold:
            self.frame_count += 1
            
            # Ralentización para evitar sobreconteo
            if self.frame_count >= self.config['frames_between_counts']:
                self.emotion_counts[emotion] += 1
                self.frame_count = 0
                
                # Registrar en historial temporal
                current_time = time.time() - self.start_time
                self.emotion_history.append({
                    'timestamp': current_time,
                    'emotion': emotion,
                    'confidence': confidence
                })
                
                # Detectar picos de rage
                if emotion == "angry" and confidence > 70:
                    self.peak_rage_moments.append(current_time)
                
                # Actualizar racha actual
                self._update_streak(emotion)
    
    def _update_streak(self, emotion):
        """Actualiza las rachas de emociones"""
        if self.current_streak['emotion'] == emotion:
            self.current_streak['count'] += 1
        else:
            # Guardar racha anterior si fue significativa
            if self.current_streak['count'] >= 3:
                if self.current_streak['emotion'] == "happy":
                    duration = time.time() - self.current_streak['start_time']
                    self.happiness_streaks.append({
                        'count': self.current_streak['count'],
                        'duration': duration
                    })
            
            # Iniciar nueva racha
            self.current_streak = {
                'emotion': emotion,
                'count': 1,
                'start_time': time.time()
            }
    
    def draw_info(self, frame, emotion, confidence):
        """Dibuja información en pantalla con mejor diseño"""
        elapsed_time = int(time.time() - self.start_time)
        minutes = elapsed_time // 60
        seconds = elapsed_time % 60
        
        # Fondo semi-transparente más grande
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (450, 250), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Título del juego con estilo
        cv2.putText(frame, f"RAGE TRACKER", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(frame, f"Juego: {self.game_name}", (20, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Tiempo de sesión
        cv2.putText(frame, f"Tiempo: {minutes:02d}:{seconds:02d}", (20, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 255, 100), 2)
        
        # Emoción actual con color y confianza
        color = (0, 255, 0) if emotion == "happy" else (0, 0, 255) if emotion == "angry" else (255, 255, 255)
        emotion_text = f"{emotion.upper()} ({confidence}%)"
        cv2.putText(frame, f"Estado: {emotion_text}", (20, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # Contadores con iconos
        cv2.putText(frame, "--- CONTADORES ---", (20, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(frame, f"Feliz:    {self.emotion_counts['happy']}", (20, 175),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Enfadado: {self.emotion_counts['angry']}", (20, 200),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.putText(frame, f"Neutral:  {self.emotion_counts['neutral']}", (20, 225),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Barra de progreso de racha
        if self.current_streak['count'] >= 3:
            streak_text = f"Racha {self.current_streak['emotion']}: {self.current_streak['count']}"
            cv2.putText(frame, streak_text, (20, 245),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 1)
        
        # Instrucciones
        cv2.putText(frame, "Presiona 'q' para salir | 'r' para reiniciar", 
                    (20, frame.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    
    def get_session_summary(self):
        """Genera un resumen detallado de la sesión"""
        total_time = int(time.time() - self.start_time)
        total_emotions = sum(self.emotion_counts.values())
        
        # Calcular porcentajes
        percentages = {
            emotion: (count / total_emotions * 100) if total_emotions > 0 else 0
            for emotion, count in self.emotion_counts.items()
        }
        
        # Calcular tendencia emocional (últimos 10 registros)
        recent_emotions = [h['emotion'] for h in self.emotion_history[-10:]]
        if recent_emotions:
            trend = max(set(recent_emotions), key=recent_emotions.count)
        else:
            trend = "neutral"
        
        return {
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
            "total_frames": self.total_frames
        }
    
    def run(self):
        """Ejecuta el detector de emociones"""
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("Error: No se pudo abrir la cámara")
            return None
        
        print(f"\n🎮 Sesión iniciada para: {self.game_name}")
        print("Presiona 'q' para finalizar la sesión")
        print("Presiona 'r' para reiniciar contadores\n")
        
        confidence = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            self.total_frames += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detectar caras
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.3,
                minNeighbors=5,
                minSize=(100, 100)
            )
            
            current_emotion = "neutral"
            
            if len(faces) > 0:
                # Usar solo la primera cara
                face = faces[0]
                x, y, w, h = face
                
                # Dibujar rectángulo de cara
                cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
                
                # Detectar emoción
                current_emotion, confidence = self.detect_emotion(frame, gray, face)
                self.update_emotion_count(current_emotion, confidence)
            
            # Dibujar información
            self.draw_info(frame, current_emotion, confidence)
            
            # Mostrar frame
            cv2.imshow("Rage Tracker - Emotion Detection", frame)
            
            # Controles de teclado
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                # Reiniciar contadores
                self.emotion_counts = {"neutral": 0, "happy": 0, "angry": 0}
                self.emotion_history = []
                self.peak_rage_moments = []
                self.happiness_streaks = []
                print("✅ Contadores reiniciados")
        
        cap.release()
        cv2.destroyAllWindows()
        
        return self.get_session_summary()
