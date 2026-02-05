"""
RAGE TRACKER - Punto de entrada
================================
Reescrito para enganchar correctamente con el flujo real del proyecto
(la versión anterior importaba `detect_face_and_smile` que ya no existe).

Flujo:
    1. Menú principal pide acción al usuario.
    2. Según la acción:
       - "play"      -> abre EmotionDetector con nombre de juego y guarda en CSV.
       - "test"      -> abre EmotionDetector en modo test (sin guardar).
       - "calibrate" -> ejecuta el Calibrator y persiste el perfil.
       - "quit"      -> sale del programa.
    3. Tras cada acción, vuelve al menú.
"""

import logging
import sys

import cv2

from src.menu import Menu
from src.camera import EmotionDetector
from src.calibration import Calibrator, CalibrationProfile
from src.data_manager import DataManager


# Logging mínimo y discreto: solo INFO+ por consola
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rage_tracker")


def run_play_session(game_name: str, data_manager: DataManager) -> None:
    """Ejecuta una sesión real y persiste el resultado en CSV."""
    detector = EmotionDetector(game_name=game_name, test_mode=False)
    summary = detector.run()
    if summary is not None:
        data_manager.save_session(summary)
        log.info(
            "Sesión guardada: %s | Felicidad %.0f%% / Rage %.0f%%",
            game_name,
            summary.get("happy_percentage", 0),
            summary.get("angry_percentage", 0),
        )
        print("\n✅ Sesión guardada correctamente.")
        input("Presiona Enter para volver al menú...")


def run_test_session() -> None:
    """Ejecuta una sesión en modo test (sin guardar datos)."""
    detector = EmotionDetector(game_name="MODO TEST", test_mode=True)
    detector.run()
    print("\n🧪 Modo test finalizado. No se han guardado datos.")
    apply = input("¿Quieres calibrar ahora con tu cara? (s/n): ").strip().lower()
    if apply == "s":
        run_calibration()


def run_calibration() -> None:
    """Lanza el Calibrator de forma independiente y guarda el perfil."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        log.error("No se pudo abrir la cámara para calibrar.")
        input("Presiona Enter para volver al menú...")
        return
    try:
        calibrator = Calibrator(cap, window_name="Rage Tracker - Calibracion")
        profile = calibrator.run_full_calibration()
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if profile is not None:
        profile.save()
        print("\n✅ Perfil de calibración guardado en data/calibration_profile.json")
    else:
        print("\n⚠️  Calibración cancelada.")
    input("Presiona Enter para volver al menú...")


def main() -> int:
    menu = Menu()
    data_manager = DataManager()

    # Aviso si no hay perfil de calibración aún
    if CalibrationProfile.load() is None:
        print("\nℹ️  No hay perfil de calibración. Se usarán valores por defecto.")
        print("   Puedes calibrar desde el menú (opción 4) para mejorar la detección.\n")

    while True:
        try:
            action = menu.main_menu()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Saliendo...")
            return 0

        kind = action.get("action")
        if kind == "quit":
            return 0
        elif kind == "play":
            run_play_session(action["game"], data_manager)
        elif kind == "test":
            run_test_session()
        elif kind == "calibrate":
            run_calibration()
        else:
            log.warning("Acción desconocida: %r", action)


if __name__ == "__main__":
    sys.exit(main())