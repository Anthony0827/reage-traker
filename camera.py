import cv2 



def test_camera():
    """
    Función de prueba para comprobar que la cámara funciona correctamente.
    Abre la webcam, muestra el vídeo en una ventana y se cierra al pulsar 'q'.
    """

    # Abrimos la cámara (0 = cámara por defecto del sistema)
    cap = cv2.VideoCapture(0)

    # Comprobamos si la cámara se abrió correctamente
    if not cap.isOpened():
        print("No se pudo abrir la cámara")
        return

    # Bucle principal: se ejecuta mientras la cámara esté abierta
    while True:
       
        ret, frame = cap.read()

        # Si no se pudo leer el frame, salimos del bucle
        if not ret:
            print("No se pudo leer el frame de la cámara")
            break

        # Mostramos el frame en una ventana
        cv2.imshow("Test Camera", frame)

        # Espera 1 ms y comprueba si se ha pulsado la tecla 'q'
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Liberamos la cámara
    cap.release()

    # Cerramos todas las ventanas de OpenCV
    cv2.destroyAllWindows()
