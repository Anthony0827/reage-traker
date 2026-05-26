"""
RAGE TRACKER - Punto de entrada unificado
=========================================
Fase 3: ahora `python main.py` (sin argumentos) abre la GUI nativa (launcher).
El antiguo menú de terminal sigue disponible con `python main.py --cli`.

Subcomandos internos usados por el launcher: `--session` (lanza una sesión con
los sensores elegidos) y `--calibrate` (recalibración guiada). Los imports
pesados (cv2, cámara) son perezosos para que la GUI arranque aunque OpenCV
falle, y para no abrir la cámara cuando solo se quieren estadísticas.

Uso:
    python main.py                              -> GUI nativa (por defecto)
    python main.py --cli                        -> menú de terminal clásico
    python main.py --session --game "X" \
        --sensors emotions scream --threshold 80 [--mic 1]   (uso interno GUI)
    python main.py --calibrate                  -> calibración guiada
"""

import argparse
import logging
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rage_tracker")


# --------------------------------------------------------------------------- #
#  CLI clásico (modo terminal)                                                #
# --------------------------------------------------------------------------- #
def run_play_session(game_name, data_manager):
    """Ejecuta una sesión real (solo emociones) y persiste el resultado."""
    from src.camera import EmotionDetector
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
        print("\n[OK] Sesión guardada correctamente.")
        input("Presiona Enter para volver al menú...")


def run_test_session():
    """Ejecuta una sesión en modo test (sin guardar datos)."""
    from src.camera import EmotionDetector
    detector = EmotionDetector(game_name="MODO TEST", test_mode=True)
    detector.run()
    print("\n[test] Modo test finalizado. No se han guardado datos.")
    apply = input("¿Quieres calibrar ahora con tu cara? (s/n): ").strip().lower()
    if apply == "s":
        run_calibration()


def run_calibration():
    """Lanza el Calibrator de forma independiente y guarda el perfil."""
    import cv2
    from src.calibration import Calibrator

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        log.error("No se pudo abrir la cámara para calibrar.")
        try:
            input("Presiona Enter para continuar...")
        except (EOFError, KeyboardInterrupt):
            pass
        return
    try:
        calibrator = Calibrator(cap, window_name="Rage Tracker - Calibracion")
        profile = calibrator.run_full_calibration()
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if profile is not None:
        profile.save()
        print("\n[OK] Perfil de calibración guardado en data/calibration_profile.json")
    else:
        print("\n[!] Calibración cancelada.")


def run_cli():
    """Bucle del menú de terminal clásico (compatibilidad CLI)."""
    from src.menu import Menu
    from src.calibration import CalibrationProfile
    from src.data_manager import DataManager

    menu = Menu()
    data_manager = DataManager()

    if CalibrationProfile.load() is None:
        print("\n[i] No hay perfil de calibración. Se usarán valores por defecto.")
        print("   Puedes calibrar desde el menú (opción 4) para mejorar la detección.\n")

    while True:
        try:
            action = menu.main_menu()
        except (KeyboardInterrupt, EOFError):
            print("\n[bye] Saliendo...")
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
            try:
                input("Presiona Enter para volver al menú...")
            except (EOFError, KeyboardInterrupt):
                return 0
        else:
            log.warning("Acción desconocida: %r", action)


# --------------------------------------------------------------------------- #
#  Subcomando de sesión (lo invoca el launcher por subprocess)                #
# --------------------------------------------------------------------------- #
def run_session_cmd(args):
    """Lanza una sesión con los sensores elegidos y guarda el resumen."""
    from src.session_runner import run_session
    from src.data_manager import DataManager

    summary = run_session(
        game=args.game,
        sensors=args.sensors,
        mic_index=args.mic,
        threshold=args.threshold,
        sensitivity=args.sensitivity,
        data_manager=DataManager(),
    )
    return 0 if summary is not None else 1


# --------------------------------------------------------------------------- #
#  Dispatch principal                                                         #
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(
        prog="rage_tracker",
        description="RAGE TRACKER — telemetría de emociones y gritos en partida.",
    )
    p.add_argument("--cli", action="store_true",
                   help="Abre el menú de terminal clásico en lugar de la GUI.")
    p.add_argument("--calibrate", action="store_true",
                   help="Lanza la calibración guiada y sale.")
    p.add_argument("--session", action="store_true",
                   help="(Uso interno de la GUI) Lanza una sesión de medición.")
    p.add_argument("--game", default="Sesión",
                   help="Nombre del juego para la sesión.")
    p.add_argument("--sensors", nargs="+", default=["emotions"],
                   choices=["emotions", "scream", "insults"],
                   help="Sensores a activar: emotions, scream o insults.")
    p.add_argument("--mic", type=int, default=None,
                   help="Índice del micrófono (sounddevice). Por defecto: el del sistema.")
    p.add_argument("--threshold", type=float, default=80.0,
                   help="Umbral de grito en %% de volumen (0-100). Por defecto: 80.")
    p.add_argument("--sensitivity", type=float, default=1.0,
                   help="Ganancia del micrófono (1.0 = sin cambio). Súbela si la "
                        "barra apenas se mueve con tu micro.")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        if args.session:
            return run_session_cmd(args)
        if args.calibrate:
            run_calibration()
            return 0
        if args.cli:
            return run_cli()

        # Sin argumentos -> GUI nativa por defecto.
        # El import es perezoso aquí para que el CLI no tenga que cargar
        # customtkinter/tkinter si no los necesita.
        from src import launcher
        return launcher.launch()
    except KeyboardInterrupt:
        print("\n[bye] Saliendo...")
        return 0


if __name__ == "__main__":
    sys.exit(main())