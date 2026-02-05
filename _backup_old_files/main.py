from menu import Menu
from camera_improved import EmotionDetector
from data_manager_improved import DataManager


def main():
    print("\n" + "=" * 50)
    print("  🎮 RAGE TRACKER - Detector de Emociones")
    print("=" * 50)
    print("\nBienvenido al sistema de tracking de emociones")
    print("durante tus sesiones de juego.\n")
    print("🆕 Versión MEJORADA con:")
    print("  ✅ Detección más precisa de emociones")
    print("  ✅ Sistema de confianza en detecciones")
    print("  ✅ Análisis avanzado de sesiones")
    print("  ✅ Dashboard web con visualizaciones\n")
    
    menu = Menu()
    data_manager = DataManager()
    
    # Mostrar menú principal
    selected_game = menu.main_menu()
    
    if selected_game is None:
        return
    
    # Iniciar detector de emociones MEJORADO
    detector = EmotionDetector(selected_game)
    session_data = detector.run()
    
    # Guardar sesión si se completó
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
        
        # Nuevas estadísticas
        print(f"\n🔥 Estadísticas avanzadas:")
        print(f"  • Picos de rage intenso: {session_data.get('peak_rage_count', 0)}")
        print(f"  • Rachas de felicidad: {session_data.get('happiness_streaks', 0)}")
        print(f"  • Tendencia emocional: {session_data.get('emotional_trend', 'neutral').upper()}")
        
        # Calcular rage ratio
        rage_ratio = session_data['angry_percentage']
        print(f"\n🔥 Rage Index de esta sesión: {rage_ratio:.1f}%")
        
        if rage_ratio > 50:
            print("⚠️  ¡Nivel de rage muy alto! Considera tomar un descanso.")
        elif rage_ratio > 30:
            print("⚠️  Nivel de rage moderado.")
        else:
            print("✅ Sesión relativamente tranquila.")
        
        print("\n✅ Sesión guardada correctamente.")
        print("\n💡 TIP: Ejecuta 'python dashboard_server.py' para ver")
        print("   tus estadísticas en el dashboard web!")
        print("\n" + "=" * 50 + "\n")


if __name__ == "__main__":
    main()
