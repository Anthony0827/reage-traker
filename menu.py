from data_manager import DataManager


class Menu:
    def __init__(self):
        self.data_manager = DataManager()
    
    def clear_screen(self):
        """Limpia la pantalla (compatible con Windows y Unix)"""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self, title):
        """Imprime un encabezado bonito"""
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50 + "\n")
    
    def main_menu(self):
        """Muestra el menú principal"""
        while True:
            self.clear_screen()
            self.print_header("🎮 RAGE TRACKER - Menú Principal")
            
            print("1. 🎯 Juegos anteriores")
            print("2. ➕ Añadir juego nuevo")
            print("3. 📊 Ver estadísticas")
            print("4. 🚪 Salir")
            print()
            
            choice = input("Selecciona una opción (1-4): ").strip()
            
            if choice == "1":
                return self.select_game_menu()
            elif choice == "2":
                return self.add_game_menu()
            elif choice == "3":
                self.show_statistics_menu()
            elif choice == "4":
                print("\n👋 ¡Hasta luego!")
                return None
            else:
                print("❌ Opción no válida. Presiona Enter para continuar...")
                input()
    
    def select_game_menu(self):
        """Menú para seleccionar un juego existente"""
        games = self.data_manager.get_games()
        
        if not games:
            print("\n📭 No hay juegos registrados todavía.")
            print("Añade un juego nuevo para comenzar.")
            input("\nPresiona Enter para continuar...")
            return self.main_menu()
        
        while True:
            self.clear_screen()
            self.print_header("🎯 Seleccionar Juego")
            
            for i, game in enumerate(games, 1):
                print(f"{i}. {game}")
            print(f"{len(games) + 1}. ⬅️  Volver al menú principal")
            print()
            
            choice = input(f"Selecciona un juego (1-{len(games) + 1}): ").strip()
            
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(games):
                    selected_game = games[choice_num - 1]
                    print(f"\n✅ Seleccionado: {selected_game}")
                    
                    # Mostrar estadísticas previas
                    stats = self.data_manager.get_game_stats(selected_game)
                    if stats['total_sessions'] > 0:
                        print(f"\n📊 Estadísticas previas:")
                        print(f"   Sesiones jugadas: {stats['total_sessions']}")
                        print(f"   Tiempo total: {stats['total_time'] // 60} min {stats['total_time'] % 60} seg")
                        print(f"   Veces enfadado: {stats['total_angry']} 😠")
                        print(f"   Veces feliz: {stats['total_happy']} 😊")
                    
                    input("\nPresiona Enter para iniciar la sesión...")
                    return selected_game
                elif choice_num == len(games) + 1:
                    return self.main_menu()
                else:
                    print("❌ Opción no válida.")
                    input("Presiona Enter para continuar...")
            except ValueError:
                print("❌ Por favor, introduce un número válido.")
                input("Presiona Enter para continuar...")
    
    def add_game_menu(self):
        """Menú para añadir un nuevo juego"""
        self.clear_screen()
        self.print_header("➕ Añadir Nuevo Juego")
        
        game_name = input("Introduce el nombre del juego: ").strip()
        
        if not game_name:
            print("❌ El nombre no puede estar vacío.")
            input("Presiona Enter para continuar...")
            return self.main_menu()
        
        if self.data_manager.add_game(game_name):
            print(f"\n✅ Juego '{game_name}' añadido correctamente!")
            input("\nPresiona Enter para iniciar la sesión...")
            return game_name
        else:
            print(f"\n⚠️  El juego '{game_name}' ya existe.")
            choice = input("¿Quieres seleccionarlo? (s/n): ").strip().lower()
            if choice == 's':
                return game_name
            else:
                return self.main_menu()
    
    def show_statistics_menu(self):
        """Muestra estadísticas generales"""
        while True:
            self.clear_screen()
            self.print_header("📊 Estadísticas")
            
            games = self.data_manager.get_games()
            
            if not games:
                print("📭 No hay datos todavía.")
                input("\nPresiona Enter para volver...")
                return
            
            print("Selecciona un juego para ver sus estadísticas:\n")
            
            for i, game in enumerate(games, 1):
                stats = self.data_manager.get_game_stats(game)
                print(f"{i}. {game}")
                if stats['total_sessions'] > 0:
                    print(f"   └─ {stats['total_sessions']} sesiones | "
                          f"😠 {stats['total_angry']} | 😊 {stats['total_happy']}")
            
            print(f"{len(games) + 1}. ⬅️  Volver")
            print()
            
            choice = input(f"Selecciona una opción (1-{len(games) + 1}): ").strip()
            
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(games):
                    self.show_game_details(games[choice_num - 1])
                elif choice_num == len(games) + 1:
                    return
                else:
                    print("❌ Opción no válida.")
                    input("Presiona Enter para continuar...")
            except ValueError:
                print("❌ Por favor, introduce un número válido.")
                input("Presiona Enter para continuar...")
    
    def show_game_details(self, game_name):
        """Muestra detalles de un juego específico"""
        self.clear_screen()
        self.print_header(f"📊 Estadísticas - {game_name}")
        
        stats = self.data_manager.get_game_stats(game_name)
        sessions = self.data_manager.get_all_sessions(game_name)
        
        if stats['total_sessions'] == 0:
            print("No hay sesiones registradas para este juego.")
        else:
            print(f"Total de sesiones: {stats['total_sessions']}")
            print(f"Tiempo total jugado: {stats['total_time'] // 60} min {stats['total_time'] % 60} seg")
            print(f"\nContadores totales:")
            print(f"  😠 Enfadado: {stats['total_angry']}")
            print(f"  😊 Feliz: {stats['total_happy']}")
            print(f"  😐 Neutral: {stats['total_neutral']}")
            
            # Calcular ratio de rage
            total_emotions = stats['total_angry'] + stats['total_happy'] + stats['total_neutral']
            if total_emotions > 0:
                rage_percentage = (stats['total_angry'] / total_emotions) * 100
                print(f"\n🔥 Rage Index: {rage_percentage:.1f}%")
            
            print(f"\n--- Últimas 5 sesiones ---")
            for session in sessions[-5:]:
                date = session['date']
                duration = int(session['duration_seconds'])
                angry = session['angry_count']
                happy = session['happy_count']
                print(f"  {date} | {duration // 60}:{duration % 60:02d} | 😠 {angry} 😊 {happy}")
        
        input("\nPresiona Enter para volver...")