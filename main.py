from src.menu import Menu
from src.camera import EmotionDetector
from src.data_manager import DataManager


def main():
    # Cabecera del programa
    print("\n" + "=" * 50)
    print("  🎮 RAGE TRACKER - Detector de Emociones")
    print("=" * 50)
    print("\nBienvenido al sistema de tracking de emociones")
    print("durante tus sesiones de juego.\n")
    
    # Inicialización de componentes principales
    menu = Menu()
    data_manager = DataManager()
    
    # Selección del juego
    selected_game = menu.main_menu()
    if selected_game is None:
        return
    
    # Ejecución del detector de emociones
    detector = EmotionDetector(selected_game)
    session_data = detector.run()
    
    # Guardado y resumen de la sesión
    if session_data:
        data_manager.save_session(session_data)
        
        print("\n" + "=" * 50)
        print("  📊 RESUMEN DE LA SESIÓN")
        print("=" * 50)
        
        print(f"\nJuego: {session_data['game']}")
        print(f"Duración: {session_data['duration_seconds'] // 60} min "
              f"{session_data['duration_seconds'] % 60} seg")
        
        print("\n📈 Emociones detectadas:")
        print(f"  😊 Feliz: {session_data['happy_count']} "
              f"({session_data['happy_percentage']:.1f}%)")
        print(f"  😠 Enfadado: {session_data['angry_count']} "
              f"({session_data['angry_percentage']:.1f}%)")
        print(f"  😐 Neutral: {session_data['neutral_count']} "
              f"({session_data['neutral_percentage']:.1f}%)")
        
        # Índice de rage
        rage_ratio = session_data['angry_percentage']
        print(f"\n🔥 Rage Index: {rage_ratio:.1f}%")
        
        if rage_ratio > 50:
            print("⚠️  ¡Nivel de rage muy alto!")
        elif rage_ratio > 30:
            print("⚠️  Nivel de rage moderado.")
        else:
            print("✅ Sesión tranquila.")
        
        print("\n✅ Sesión guardada.")
        print("\n💡 TIP: Ejecuta 'python web/dashboard_server.py' para ver el dashboard")
        print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    main()
