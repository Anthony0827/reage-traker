from src.menu import Menu
from src.camera import EmotionDetector
from src.data_manager import DataManager


def main():
    print("\n" + "=" * 50)
    print("  🎮 RAGE TRACKER - Detector de Emociones")
    print("=" * 50)
    print("\nBienvenido al sistema de tracking de emociones")
    print("durante tus sesiones de juego.\n")
    
    menu = Menu()
    data_manager = DataManager()
    
    selected_game = menu.main_menu()
    
    if selected_game is None:
        return
    
    detector = EmotionDetector(selected_game)
    session_data = detector.run()
    
    if session_data:
        data_manager.save_session(session_data)
        
        print("\n" + "=" * 50)
        print("  📊 RESUMEN DE LA SESIÓN")
        print("=" * 50)
        print(f"\nJuego: {session_data['game']}")
        print(f"Duración: {session_data['duration_seconds'] // 60} min {session_data['duration_seconds'] % 60} seg")
        print(f"\n📈 Emociones detectadas:")
        print(f"  😊 Feliz: {session_data['happy_count']} ({session_data['happy_percentage']:.1f}%)")
        print(f"  😠 Enfadado: {session_data['angry_count']} ({session_data['angry_percentage']:.1f}%)")
        print(f"  😐 Neutral: {session_data['neutral_count']} ({session_data['neutral_percentage']:.1f}%)")
        
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
