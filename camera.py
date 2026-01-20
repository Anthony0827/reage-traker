import cv2


def detect_face_and_smile():
    """
    Detecta la cara y la sonrisa usando Haar Cascades de OpenCV
    y muestra un estado emocional simple en pantalla.
    """

    # Cargar clasificadores Haar (ya vienen con OpenCV)
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    smile_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_smile.xml"
    )

    # Abrir la cámara
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("No se pudo abrir la cámara")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Convertir a escala de grises (necesario para Haar)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detectar caras
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.3,
            minNeighbors=5
        )

        emotion = "neutral"

        for (x, y, w, h) in faces:
            # Dibujar rectángulo de la cara
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

            # Región de interés (cara)
            roi_gray = gray[y:y + h, x:x + w]

            # Detectar sonrisa dentro de la cara
            smiles = smile_cascade.detectMultiScale(
                roi_gray,
                scaleFactor=1.8,
                minNeighbors=20
            )

            if len(smiles) > 0:
                emotion = "happy"
            else:
                emotion = "neutral"

            break  # solo usamos la primera cara detectada

        # Mostrar emoción detectada
        cv2.putText(
            frame,
            f"Emotion: {emotion}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

        # contador de veces que se sonrie

        cv2.countSmaile = len(smiles)
        cv2.putText(
            frame,
            f"Smile Count: {cv2.countSmaile}",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
        )

        cv2.imshow("Emotion Detection", frame)

        # Salir al pulsar 'q'
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
