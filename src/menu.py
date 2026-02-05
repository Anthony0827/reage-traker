"""
RAGE TRACKER - Menú principal
=============================
Cambios respecto a la versión original:

- Devuelve diccionarios de acción (no strings sueltos) para que main.py pueda
  enrutar a las nuevas funcionalidades (modo test y recalibración) sin perder
  compatibilidad con las opciones existentes.
- Añadidas dos opciones nuevas en el menú principal:
    * 🧪 Probar detección (modo test) — abre la cámara con HUD sin guardar.
    * ⚙️  Recalibrar detección — lanza la calibración guiada.
"""

import os

from src.data_manager import DataManager


# Tipo conceptual de retorno (siempre dict, nunca None):
#   {"action": "play",       "game": "<nombre>"}
#   {"action": "test"}
#   {"action": "calibrate"}
#   {"action": "quit"}


class Menu:
    def __init__(self):
        self.data_manager = DataManager()

    # --- utilidades ---------------------------------------------------------
    def clear_screen(self):
        """Limpia la pantalla (Windows / Unix)."""
        os.system("cls" if os.name == "nt" else "clear")

    def print_header(self, title):
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50 + "\n")

    # --- menú principal -----------------------------------------------------
    def main_menu(self):
        """Bucle del menú principal. Devuelve un dict de acción."""
        while True:
            self.clear_screen()
            self.print_header("🎮 RAGE TRACKER - Menú Principal")

            print("1. 🎯 Juegos anteriores")
            print("2. ➕ Añadir juego nuevo")
            print("3. 🧪 Probar detección (modo test)")
            print("4. ⚙️  Recalibrar detección")
            print("5. 📊 Ver estadísticas")
            print("6. 🚪 Salir")
            print()

            choice = input("Selecciona una opción (1-6): ").strip()

            if choice == "1":
                result = self.select_game_menu()
                if result is not None:
                    return result
            elif choice == "2":
                result = self.add_game_menu()
                if result is not None:
                    return result
            elif choice == "3":
                return {"action": "test"}
            elif choice == "4":
                return {"action": "calibrate"}
            elif choice == "5":
                self.show_statistics_menu()
            elif choice == "6":
                print("\n👋 ¡Hasta luego!")
                return {"action": "quit"}
            else:
                print("❌ Opción no válida. Presiona Enter para continuar...")
                input()

    # --- seleccionar juego --------------------------------------------------
    def select_game_menu(self):
        """Permite elegir un juego existente. Devuelve dict de acción o None
        si el usuario quiere volver al menú anterior."""
        games = self.data_manager.get_games()

        if not games:
            print("\n🔭 No hay juegos registrados todavía.")
            print("Añade un juego nuevo para comenzar.")
            input("\nPresiona Enter para continuar...")
            return None

        while True:
            self.clear_screen()
            self.print_header("🎯 Seleccionar Juego")

            for i, game_name in enumerate(games, 1):
                print(f"{i}. {game_name}")
            print(f"{len(games) + 1}. ⬅️  Volver al menú principal")
            print()

            choice = input(f"Selecciona un juego (1-{len(games) + 1}): ").strip()
            try:
                n = int(choice)
                if 1 <= n <= len(games):
                    selected = games[n - 1]
                    print(f"\n✅ Seleccionado: {selected}")

                    stats = self.data_manager.get_game_stats(selected)
                    if stats["total_sessions"] > 0:
                        print(f"\n📊 Estadísticas previas:")
                        print(f"   Sesiones jugadas: {stats['total_sessions']}")
                        mins = stats["total_time"] // 60
                        secs = stats["total_time"] % 60
                        print(f"   Tiempo total: {mins} min {secs} seg")
                        print(f"   Veces enfadado: {stats['total_angry']} 😠")
                        print(f"   Veces feliz: {stats['total_happy']} 😊")

                    input("\nPresiona Enter para iniciar la sesión...")
                    return {"action": "play", "game": selected}
                elif n == len(games) + 1:
                    return None
                else:
                    print("❌ Opción no válida.")
                    input("Presiona Enter para continuar...")
            except ValueError:
                print("❌ Por favor, introduce un número válido.")
                input("Presiona Enter para continuar...")

    # --- añadir juego -------------------------------------------------------
    def add_game_menu(self):
        """Crea un juego nuevo. Devuelve dict de acción o None si el usuario
        decide no continuar."""
        self.clear_screen()
        self.print_header("➕ Añadir Nuevo Juego")

        game_name = input("Introduce el nombre del juego: ").strip()
        if not game_name:
            print("❌ El nombre no puede estar vacío.")
            input("Presiona Enter para continuar...")
            return None

        if self.data_manager.add_game(game_name):
            print(f"\n✅ Juego '{game_name}' añadido correctamente!")
            input("\nPresiona Enter para iniciar la sesión...")
            return {"action": "play", "game": game_name}

        # Ya existe
        print(f"\n⚠️  El juego '{game_name}' ya existe.")
        choice = input("¿Quieres seleccionarlo? (s/n): ").strip().lower()
        if choice == "s":
            return {"action": "play", "game": game_name}
        return None

    # --- estadísticas -------------------------------------------------------
    def show_statistics_menu(self):
        """Muestra estadísticas globales con detalle por juego."""
        while True:
            self.clear_screen()
            self.print_header("📊 Estadísticas")

            games = self.data_manager.get_games()
            if not games:
                print("🔭 No hay datos todavía.")
                input("\nPresiona Enter para volver...")
                return

            print("Selecciona un juego para ver sus estadísticas:\n")
            for i, game_name in enumerate(games, 1):
                stats = self.data_manager.get_game_stats(game_name)
                print(f"{i}. {game_name}")
                if stats["total_sessions"] > 0:
                    print(
                        f"   └─ {stats['total_sessions']} sesiones | "
                        f"😠 {stats['total_angry']} | 😊 {stats['total_happy']}"
                    )

            print(f"{len(games) + 1}. ⬅️  Volver")
            print()

            choice = input(f"Selecciona una opción (1-{len(games) + 1}): ").strip()
            try:
                n = int(choice)
                if 1 <= n <= len(games):
                    self.show_game_details(games[n - 1])
                elif n == len(games) + 1:
                    return
                else:
                    print("❌ Opción no válida.")
                    input("Presiona Enter para continuar...")
            except ValueError:
                print("❌ Por favor, introduce un número válido.")
                input("Presiona Enter para continuar...")

    def show_game_details(self, game_name):
        """Detalle por juego: emociones acumuladas, rage index y últimas sesiones."""
        self.clear_screen()
        self.print_header(f"📊 Estadísticas - {game_name}")

        stats = self.data_manager.get_game_stats(game_name)
        sessions = self.data_manager.get_all_sessions(game_name)

        if stats["total_sessions"] == 0:
            print("No hay sesiones registradas para este juego.")
        else:
            mins = stats["total_time"] // 60
            secs = stats["total_time"] % 60
            print(f"Total de sesiones: {stats['total_sessions']}")
            print(f"Tiempo total jugado: {mins} min {secs} seg")

            print(f"\nContadores totales:")
            print(f"  😠 Enfadado: {stats['total_angry']}")
            print(f"  😊 Feliz: {stats['total_happy']}")
            print(f"  😐 Neutral: {stats['total_neutral']}")

            total_emotions = stats["total_angry"] + stats["total_happy"] + stats["total_neutral"]
            if total_emotions > 0:
                rage_pct = stats["total_angry"] / total_emotions * 100
                print(f"\n🔥 Rage Index: {rage_pct:.1f}%")

            print(f"\n--- Últimas 5 sesiones ---")
            for s in sessions[-5:]:
                date = s.get("date", "N/A")
                duration = int(s.get("duration_seconds", 0))
                angry = s.get("angry_count", 0)
                happy = s.get("happy_count", 0)
                print(f"  {date} | {duration // 60}:{duration % 60:02d} | 😠 {angry} 😊 {happy}")

        input("\nPresiona Enter para volver...")