from src.data_manager import DataManager

# Clase principal que gestiona la interfaz de menú de la aplicación
# Proporciona navegación interactiva para gestionar juegos y sesiones
class Menu:
    def __init__(self):
        # Inicializa el gestor de datos para acceder a juegos y sesiones
        self.data_manager = DataManager()
    
    def clear_screen(self):
        """Limpia la pantalla (compatible con Windows y Unix).
        
        Detecta el SO y ejecuta el comando correspondiente:
        - Windows: 'cls'
        - Unix/Linux/Mac: 'clear'
        """
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_header(self, title):
        """Imprime un encabezado formateado con bordes.
        
        Args:
            title (str): Texto del encabezado a mostrar
        """
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50 + "\n")
    
    def main_menu(self):
        """Muestra el menú principal con las opciones disponibles.
        
        Bucle infinito que permite:
        - Seleccionar un juego anterior
        - Añadir un nuevo juego
        - Ver estadísticas
        - Salir de la aplicación
        """
        while True:
            self.clear_screen()
            self.print_header("🎮 RAGE TRACKER - Menú Principal")
            
            # Mostrar opciones disponibles
            print("1. 🎯 Juegos anteriores")
            print("2. ➕ Añadir juego nuevo")
            print("3. 📊 Ver estadísticas")
            print("4. 🚪 Salir")
            print()
            
            # Obtener opción del usuario
            choice = input("Selecciona una opción (1-4): ").strip()
            
            # Procesar la opción seleccionada
            if choice == "1":
                return self.select_game_menu()
            elif choice == "2":
                return self.add_game_menu()
            elif choice == "3":
                # Ver estadísticas y volver al menú
                self.show_statistics_menu()
            elif choice == "4":
                # Salir de la aplicación
                print("\n👋 ¡Hasta luego!")
                return None
            else:
                # Mostrar error si la opción no es válida
                print("❌ Opción no válida. Presiona Enter para continuar...")
                input()
    
    def select_game_menu(self):
        """Menú para seleccionar un juego existente.
        
        Permite al usuario:
        - Ver lista de juegos guardados
        - Seleccionar uno para iniciar una sesión
        - Ver estadísticas previas del juego
        
        Returns:
            str: Nombre del juego seleccionado
        """
        # Obtener lista de juegos del gestor de datos
        games = self.data_manager.get_games()
        
        # Verificar si hay juegos registrados
        if not games:
            print("\n🔭 No hay juegos registrados todavía.")
            print("Añade un juego nuevo para comenzar.")
            input("\nPresiona Enter para continuar...")
            return self.main_menu()
        
        while True:
            self.clear_screen()
            self.print_header("🎯 Seleccionar Juego")
            
            # Mostrar lista numerada de juegos
            for i, game_name in enumerate(games, 1):
                print(f"{i}. {game_name}")
            # Opción para volver
            print(f"{len(games) + 1}. ⬅️  Volver al menú principal")
            print()
            
            # Obtener selección del usuario
            choice = input(f"Selecciona un juego (1-{len(games) + 1}): ").strip()
            
            try:
                # Convertir entrada a número
                choice_num = int(choice)
                
                # Validar si la opción es un juego válido
                if 1 <= choice_num <= len(games):
                    selected_game = games[choice_num - 1]
                    print(f"\n✅ Seleccionado: {selected_game}")
                    
                    # Obtener y mostrar estadísticas previas del juego
                    stats = self.data_manager.get_game_stats(selected_game)
                    if stats['total_sessions'] > 0:
                        print(f"\n📊 Estadísticas previas:")
                        print(f"   Sesiones jugadas: {stats['total_sessions']}")
                        print(f"   Tiempo total: {stats['total_time'] // 60} min {stats['total_time'] % 60} seg")
                        print(f"   Veces enfadado: {stats['total_angry']} 😠")
                        print(f"   Veces feliz: {stats['total_happy']} 😊")
                    
                    input("\nPresiona Enter para iniciar la sesión...")
                    return selected_game
                # Opción para volver al menú principal
                elif choice_num == len(games) + 1:
                    return self.main_menu()
                else:
                    print("❌ Opción no válida.")
                    input("Presiona Enter para continuar...")
            except ValueError:
                # Capturar error si la entrada no es un número
                print("❌ Por favor, introduce un número válido.")
                input("Presiona Enter para continuar...")
    
    def add_game_menu(self):
        """Menú para añadir un nuevo juego.
        
        Permite al usuario:
        - Crear un nuevo juego con nombre único
        - Si el juego ya existe, ofrece seleccionarlo
        
        Returns:
            str: Nombre del nuevo juego o del existente seleccionado
        """
        self.clear_screen()
        self.print_header("➕ Añadir Nuevo Juego")
        
        # Solicitar nombre del nuevo juego
        game_name = input("Introduce el nombre del juego: ").strip()
        
        # Validar que el nombre no esté vacío
        if not game_name:
            print("❌ El nombre no puede estar vacío.")
            input("Presiona Enter para continuar...")
            return self.main_menu()
        
        # Intentar añadir el nuevo juego
        if self.data_manager.add_game(game_name):
            print(f"\n✅ Juego '{game_name}' añadido correctamente!")
            input("\nPresiona Enter para iniciar la sesión...")
            return game_name
        else:
            # El juego ya existe, ofrecer seleccionarlo
            print(f"\n⚠️  El juego '{game_name}' ya existe.")
            choice = input("¿Quieres seleccionarlo? (s/n): ").strip().lower()
            if choice == 's':
                return game_name
            else:
                return self.main_menu()
    
    def show_statistics_menu(self):
        """Menú de estadísticas globales.
        
        Permite al usuario:
        - Ver resumen de todos los juegos
        - Seleccionar un juego para ver detalles completos
        """
        while True:
            self.clear_screen()
            self.print_header("📊 Estadísticas")
            
            # Obtener lista de juegos
            games = self.data_manager.get_games()
            
            # Mostrar mensaje si no hay datos
            if not games:
                print("🔭 No hay datos todavía.")
                input("\nPresiona Enter para volver...")
                return
            
            print("Selecciona un juego para ver sus estadísticas:\n")
            
            # Mostrar lista de juegos con resumen rápido de estadísticas
            for i, game_name in enumerate(games, 1):
                stats = self.data_manager.get_game_stats(game_name)
                print(f"{i}. {game_name}")
                # Mostrar resumen si hay sesiones
                if stats['total_sessions'] > 0:
                    print(f"   └─ {stats['total_sessions']} sesiones | "
                          f"😠 {stats['total_angry']} | 😊 {stats['total_happy']}")
            
            # Opción para volver
            print(f"{len(games) + 1}. ⬅️  Volver")
            print()
            
            # Obtener opción del usuario
            choice = input(f"Selecciona una opción (1-{len(games) + 1}): ").strip()
            
            try:
                # Convertir entrada a número
                choice_num = int(choice)
                
                # Validar si es un juego válido
                if 1 <= choice_num <= len(games):
                    game_name = games[choice_num - 1]
                    self.show_game_details(game_name)
                # Opción para volver
                elif choice_num == len(games) + 1:
                    return
                else:
                    print("❌ Opción no válida.")
                    input("Presiona Enter para continuar...")
            except ValueError:
                # Capturar error si la entrada no es un número
                print("❌ Por favor, introduce un número válido.")
                input("Presiona Enter para continuar...")
    
    def show_game_details(self, game_name):
        """Muestra detalles estadísticos completos de un juego.
        
        Args:
            game_name (str): Nombre del juego del cual mostrar estadísticas
        
        Muestra:
        - Total de sesiones y tiempo jugado
        - Contadores de emociones (enfadado, feliz, neutral)
        - Rage Index (porcentaje de veces enfadado)
        - Últimas 5 sesiones con detalle
        """
        self.clear_screen()
        self.print_header(f"📊 Estadísticas - {game_name}")
        
        # Obtener estadísticas generales y lista de sesiones
        stats = self.data_manager.get_game_stats(game_name)
        sessions = self.data_manager.get_all_sessions(game_name)
        
        # Mostrar mensaje si no hay sesiones
        if stats['total_sessions'] == 0:
            print("No hay sesiones registradas para este juego.")
        else:
            # Mostrar resumen general
            print(f"Total de sesiones: {stats['total_sessions']}")
            print(f"Tiempo total jugado: {stats['total_time'] // 60} min {stats['total_time'] % 60} seg")
            
            # Mostrar contadores de emociones
            print(f"\nContadores totales:")
            print(f"  😠 Enfadado: {stats['total_angry']}")
            print(f"  😊 Feliz: {stats['total_happy']}")
            print(f"  😐 Neutral: {stats['total_neutral']}")
            
            # Calcular y mostrar el Rage Index (porcentaje de enfado)
            total_emotions = stats['total_angry'] + stats['total_happy'] + stats['total_neutral']
            if total_emotions > 0:
                rage_percentage = (stats['total_angry'] / total_emotions) * 100
                print(f"\n🔥 Rage Index: {rage_percentage:.1f}%")
            
            # Mostrar las últimas 5 sesiones con detalles
            print(f"\n--- Últimas 5 sesiones ---")
            for session in sessions[-5:]:
                date = session.get('date', 'N/A')
                duration = int(session.get('duration_seconds', 0))
                angry = session.get('angry_count', 0)
                happy = session.get('happy_count', 0)
                print(f"  {date} | {duration // 60}:{duration % 60:02d} | 😠 {angry} 😊 {happy}")
        
        input("\nPresiona Enter para volver...")
