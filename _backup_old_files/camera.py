import cv2
import time
from datetime import datetime


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
        
        # Contadores de emociones
        self.emotion_counts = {
            "neutral": 0,
            "happy": 0,
            "angry": 0
        }
        
        # Tiempos
        self.start_time = time.time()
        self.last_emotion = "neutral"
        self.emotion_threshold = 12  # frames consecutivos - punto medio
        self.emotion_counter = 0
        self.frame_count = 0  # contador para ralentizar aún más
        
    def detect_emotion(self, frame, gray, face):
        """Detecta la emoción basándose en características faciales"""
        x, y, w, h = face
        roi_gray = gray[y:y + h, x:x + w]
        roi_color = frame[y:y + h, x:x + w]
        
        # Detectar sonrisa
        smiles = self.smile_cascade.detectMultiScale(
            roi_gray,
            scaleFactor=1.8,
            minNeighbors=20,  # Balance
            minSize=(25, 25)
        )
        
        # Detectar ojos
        eyes = self.eye_cascade.detectMultiScale(
            roi_gray,
            scaleFactor=1.1,
            minNeighbors=10,  # Balance
            minSize=(15, 15)
        )
        
        # Análisis de región de cejas (parte superior del rostro)
        brow_region = roi_gray[0:int(h*0.35), :]
        brow_mean = brow_region.mean()
        
        # Análisis de región de boca (parte inferior)
        mouth_region = roi_gray[int(h*0.6):, :]
        mouth_mean = mouth_region.mean()
        
        # Lógica de detección BALANCEADA
        emotion = "neutral"
        
        # Si hay sonrisa clara -> feliz
        if len(smiles) > 0:
            emotion = "happy"
        # Para enfadado: punto intermedio
        elif len(eyes) >= 2 and brow_mean < 72 and mouth_mean < 80:
            # Cejas oscuras + boca un poco tensa
            emotion = "angry"
        # O si las cejas están bastante fruncidas
        elif brow_mean < 62:
            emotion = "angry"
        
        return emotion
    
    def update_emotion_count(self, emotion):
        """Actualiza el contador de emociones con confirmación y ralentización"""
        if emotion == self.last_emotion:
            self.emotion_counter += 1
        else:
            self.emotion_counter = 0
            self.last_emotion = emotion
        
        # Solo cuenta si la emoción se mantiene varios frames
        # Y además solo cuenta cada 20 frames (aprox. 0.7 seg)
        if self.emotion_counter >= self.emotion_threshold:
            self.frame_count += 1
            if self.frame_count >= 20:  # Ralentización balanceada
                self.emotion_counts[emotion] += 1
                self.frame_count = 0
    
    def draw_info(self, frame, emotion):
        """Dibuja información en pantalla"""
        elapsed_time = int(time.time() - self.start_time)
        minutes = elapsed_time // 60
        seconds = elapsed_time % 60
        
        # Fondo semi-transparente para mejor legibilidad
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (400, 200), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        # Información del juego
        cv2.putText(frame, f"Juego: {self.game_name}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Tiempo de sesión
        cv2.putText(frame, f"Tiempo: {minutes:02d}:{seconds:02d}", (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Emoción actual
        color = (0, 255, 0) if emotion == "happy" else (0, 0, 255) if emotion == "angry" else (255, 255, 255)
        cv2.putText(frame, f"Emocion: {emotion.upper()}", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # Contadores
        cv2.putText(frame, "--- Contadores ---", (20, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        cv2.putText(frame, f"Feliz: {self.emotion_counts['happy']}", (20, 155),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"Enfadado: {self.emotion_counts['angry']}", (20, 180),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.putText(frame, f"Neutral: {self.emotion_counts['neutral']}", (20, 205),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Instrucciones
        cv2.putText(frame, "Presiona 'q' para salir", (20, frame.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    
    def run(self):
        """Ejecuta el detector de emociones"""
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            print("Error: No se pudo abrir la cámara")
            return None
        
        print(f"\n🎮 Sesión iniciada para: {self.game_name}")
        print("Presiona 'q' para finalizar la sesión\n")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
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
                current_emotion = self.detect_emotion(frame, gray, face)
                self.update_emotion_count(current_emotion)
            
            # Dibujar información
            self.draw_info(frame, current_emotion)
            
            # Mostrar frame
            cv2.imshow("Rage Tracker - Emotion Detection", frame)
            
            # Salir con 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        cap.release()
        cv2.destroyAllWindows()
        
        # Calcular tiempo total
        total_time = int(time.time() - self.start_time)
        
        return {
            "game": self.game_name,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": total_time,
            "happy_count": self.emotion_counts["happy"],
            "angry_count": self.emotion_counts["angry"],
            "neutral_count": self.emotion_counts["neutral"]
        }