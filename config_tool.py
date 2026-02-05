#!/usr/bin/env python3
"""
RAGE TRACKER - Configuration Tool
Herramienta para ajustar los umbrales de detección de emociones
"""

import json
import os


class ConfigTool:
    def __init__(self):
        self.config_file = "config.json"
        self.default_config = {
    "detection": {
        # --- FELICIDAD (única vía para no estar enfadado) ---
        "smile_scale_factor": 1.9,
        "smile_min_neighbors": 22,
        "smile_min_size": [30, 30],

        # --- OJOS ---
        "eye_scale_factor": 1.1,
        "eye_min_neighbors": 8,
        "eye_min_size": [15, 15],

        # --- ENFADO (estado por defecto sin sonrisa) ---
        "brow_angry_threshold": 90,        # cejas casi irrelevantes
        "brow_very_angry_threshold": 78,
        "mouth_tense_threshold": 88,       # boca relajada aún puede ser enfado

        # --- DINÁMICA DE ESTADOS ---
        "frames_between_counts": 14,       # reacciona más rápido
        "emotion_confirmation_frames": 6   # neutro dura poco
    },
    "display": {
        "show_confidence": True,
        "show_debug_info": False,
        "overlay_opacity": 0.7
    }
}

        self.load_config()
    
    def load_config(self):
        """Carga la configuración desde el archivo JSON"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = self.default_config.copy()
            self.save_config()
    
    def save_config(self):
        """Guarda la configuración en el archivo JSON"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)
        print(f"\n✅ Configuración guardada en {self.config_file}")
    
    def show_current_config(self):
        """Muestra la configuración actual"""
        print("\n" + "=" * 60)
        print("  ⚙️  CONFIGURACIÓN ACTUAL")
        print("=" * 60)
        print("\n📊 DETECCIÓN DE EMOCIONES:")
        print(f"  • Sonrisa - Scale Factor: {self.config['detection']['smile_scale_factor']}")
        print(f"  • Sonrisa - Min Neighbors: {self.config['detection']['smile_min_neighbors']}")
        print(f"  • Ojos - Min Neighbors: {self.config['detection']['eye_min_neighbors']}")
        print(f"\n😠 UMBRALES DE RAGE:")
        print(f"  • Cejas enfadadas: {self.config['detection']['brow_angry_threshold']}")
        print(f"  • Cejas muy enfadadas: {self.config['detection']['brow_very_angry_threshold']}")
        print(f"  • Boca tensa: {self.config['detection']['mouth_tense_threshold']}")
        print(f"\n⏱️  VELOCIDAD:")
        print(f"  • Frames entre conteos: {self.config['detection']['frames_between_counts']}")
        print(f"  • Frames de confirmación: {self.config['detection']['emotion_confirmation_frames']}")
        print("\n" + "=" * 60)
    
    def adjust_sensitivity(self):
        """Menú para ajustar la sensibilidad"""
        while True:
            print("\n" + "=" * 60)
            print("  🎚️  AJUSTAR SENSIBILIDAD")
            print("=" * 60)
            print("\n1. Aumentar sensibilidad de RAGE (detecta más rage)")
            print("2. Disminuir sensibilidad de RAGE (detecta menos rage)")
            print("3. Aumentar sensibilidad de FELICIDAD (detecta más sonrisas)")
            print("4. Disminuir sensibilidad de FELICIDAD (detecta menos sonrisas)")
            print("5. Ajustar velocidad de conteo")
            print("6. Restaurar valores por defecto")
            print("7. Ver configuración actual")
            print("8. Volver al menú principal")
            
            choice = input("\nSelecciona una opción (1-8): ").strip()
            
            if choice == "1":
                self.increase_rage_sensitivity()
            elif choice == "2":
                self.decrease_rage_sensitivity()
            elif choice == "3":
                self.increase_happy_sensitivity()
            elif choice == "4":
                self.decrease_happy_sensitivity()
            elif choice == "5":
                self.adjust_speed()
            elif choice == "6":
                self.restore_defaults()
            elif choice == "7":
                self.show_current_config()
            elif choice == "8":
                break
            else:
                print("❌ Opción no válida")
    
    def increase_rage_sensitivity(self):
        """Aumenta la sensibilidad de detección de rage"""
        self.config['detection']['brow_angry_threshold'] -= 5
        self.config['detection']['brow_very_angry_threshold'] -= 5
        self.config['detection']['mouth_tense_threshold'] -= 3
        self.save_config()
        print("\n✅ Sensibilidad de RAGE aumentada")
        print("   → Ahora detectará rage más fácilmente")
    
    def decrease_rage_sensitivity(self):
        """Disminuye la sensibilidad de detección de rage"""
        self.config['detection']['brow_angry_threshold'] += 5
        self.config['detection']['brow_very_angry_threshold'] += 5
        self.config['detection']['mouth_tense_threshold'] += 3
        self.save_config()
        print("\n✅ Sensibilidad de RAGE disminuida")
        print("   → Ahora será más estricto al detectar rage")
    
    def increase_happy_sensitivity(self):
        """Aumenta la sensibilidad de detección de felicidad"""
        self.config['detection']['smile_min_neighbors'] = max(10, self.config['detection']['smile_min_neighbors'] - 2)
        self.config['detection']['smile_scale_factor'] = max(1.5, self.config['detection']['smile_scale_factor'] - 0.1)
        self.save_config()
        print("\n✅ Sensibilidad de FELICIDAD aumentada")
        print("   → Ahora detectará sonrisas más fácilmente")
    
    def decrease_happy_sensitivity(self):
        """Disminuye la sensibilidad de detección de felicidad"""
        self.config['detection']['smile_min_neighbors'] = min(25, self.config['detection']['smile_min_neighbors'] + 2)
        self.config['detection']['smile_scale_factor'] = min(2.0, self.config['detection']['smile_scale_factor'] + 0.1)
        self.save_config()
        print("\n✅ Sensibilidad de FELICIDAD disminuida")
        print("   → Ahora será más estricto al detectar sonrisas")
    
    def adjust_speed(self):
        """Ajusta la velocidad de conteo"""
        print("\n" + "=" * 60)
        print("  ⏱️  AJUSTAR VELOCIDAD DE CONTEO")
        print("=" * 60)
        print("\nValor actual:", self.config['detection']['frames_between_counts'])
        print("\nRecomendaciones:")
        print("  • 10-12: Muy rápido (puede sobrecontar)")
        print("  • 15-18: Balanceado (recomendado)")
        print("  • 20-25: Lento (más preciso)")
        
        try:
            new_value = int(input("\nNuevo valor (5-30): ").strip())
            if 5 <= new_value <= 30:
                self.config['detection']['frames_between_counts'] = new_value
                self.save_config()
                print(f"\n✅ Velocidad ajustada a {new_value} frames")
            else:
                print("❌ Valor fuera de rango")
        except ValueError:
            print("❌ Valor inválido")
    
    def restore_defaults(self):
        """Restaura los valores por defecto"""
        confirm = input("\n⚠️  ¿Estás seguro de restaurar los valores por defecto? (s/n): ").strip().lower()
        if confirm == 's':
            self.config = self.default_config.copy()
            self.save_config()
            print("\n✅ Configuración restaurada a valores por defecto")
        else:
            print("\n❌ Operación cancelada")
    
    def advanced_settings(self):
        """Menú de configuración avanzada"""
        while True:
            print("\n" + "=" * 60)
            print("  🔧 CONFIGURACIÓN AVANZADA")
            print("=" * 60)
            print("\n1. Ajustar umbrales individuales")
            print("2. Configurar detección de ojos")
            print("3. Configurar visualización")
            print("4. Exportar configuración")
            print("5. Importar configuración")
            print("6. Volver")
            
            choice = input("\nSelecciona una opción (1-6): ").strip()
            
            if choice == "1":
                self.adjust_individual_thresholds()
            elif choice == "2":
                self.adjust_eye_detection()
            elif choice == "3":
                self.adjust_display_settings()
            elif choice == "4":
                self.export_config()
            elif choice == "5":
                self.import_config()
            elif choice == "6":
                break
            else:
                print("❌ Opción no válida")
    
    def adjust_individual_thresholds(self):
        """Ajusta umbrales individuales"""
        print("\n📊 UMBRALES ACTUALES:")
        for key, value in self.config['detection'].items():
            if 'threshold' in key:
                print(f"  • {key}: {value}")
        
        print("\nEjemplo de ajuste:")
        print("  brow_angry_threshold: 75")
        print("\nIngresa 'salir' para volver")
        
        while True:
            param = input("\nParámetro a ajustar: ").strip()
            if param.lower() == 'salir':
                break
            
            if param in self.config['detection']:
                try:
                    new_value = float(input(f"Nuevo valor para {param}: ").strip())
                    self.config['detection'][param] = new_value
                    self.save_config()
                    print(f"✅ {param} = {new_value}")
                except ValueError:
                    print("❌ Valor inválido")
            else:
                print(f"❌ Parámetro '{param}' no encontrado")
    
    def adjust_eye_detection(self):
        """Ajusta parámetros de detección de ojos"""
        print("\n👁️  CONFIGURACIÓN DE DETECCIÓN DE OJOS")
        print(f"Scale Factor: {self.config['detection']['eye_scale_factor']}")
        print(f"Min Neighbors: {self.config['detection']['eye_min_neighbors']}")
        
        try:
            scale = float(input("\nNuevo Scale Factor (1.05-1.3): ").strip())
            neighbors = int(input("Nuevo Min Neighbors (5-15): ").strip())
            
            self.config['detection']['eye_scale_factor'] = scale
            self.config['detection']['eye_min_neighbors'] = neighbors
            self.save_config()
            print("\n✅ Configuración de ojos actualizada")
        except ValueError:
            print("❌ Valores inválidos")
    
    def adjust_display_settings(self):
        """Ajusta configuración de visualización"""
        print("\n🖥️  CONFIGURACIÓN DE VISUALIZACIÓN")
        print(f"1. Mostrar confianza: {self.config['display']['show_confidence']}")
        print(f"2. Mostrar info debug: {self.config['display']['show_debug_info']}")
        print(f"3. Opacidad overlay: {self.config['display']['overlay_opacity']}")
        
        choice = input("\n¿Qué deseas cambiar? (1-3): ").strip()
        
        if choice == "1":
            self.config['display']['show_confidence'] = not self.config['display']['show_confidence']
        elif choice == "2":
            self.config['display']['show_debug_info'] = not self.config['display']['show_debug_info']
        elif choice == "3":
            try:
                opacity = float(input("Nueva opacidad (0.0-1.0): ").strip())
                self.config['display']['overlay_opacity'] = max(0.0, min(1.0, opacity))
            except ValueError:
                print("❌ Valor inválido")
                return
        
        self.save_config()
        print("\n✅ Configuración de visualización actualizada")
    
    def export_config(self):
        """Exporta la configuración a un archivo"""
        filename = input("\nNombre del archivo (default: config_backup.json): ").strip()
        if not filename:
            filename = "config_backup.json"
        
        with open(filename, 'w') as f:
            json.dump(self.config, f, indent=4)
        print(f"\n✅ Configuración exportada a {filename}")
    
    def import_config(self):
        """Importa configuración desde un archivo"""
        filename = input("\nNombre del archivo a importar: ").strip()
        
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    self.config = json.load(f)
                self.save_config()
                print(f"\n✅ Configuración importada desde {filename}")
            except Exception as e:
                print(f"❌ Error al importar: {e}")
        else:
            print(f"❌ Archivo '{filename}' no encontrado")
    
    def main_menu(self):
        """Menú principal"""
        while True:
            print("\n" + "=" * 60)
            print("  ⚙️  RAGE TRACKER - CONFIGURACIÓN")
            print("=" * 60)
            print("\n1. 🎚️  Ajustar sensibilidad (modo simple)")
            print("2. 🔧 Configuración avanzada")
            print("3. 📊 Ver configuración actual")
            print("4. 💾 Guardar y salir")
            print("5. ❌ Salir sin guardar")
            
            choice = input("\nSelecciona una opción (1-5): ").strip()
            
            if choice == "1":
                self.adjust_sensitivity()
            elif choice == "2":
                self.advanced_settings()
            elif choice == "3":
                self.show_current_config()
            elif choice == "4":
                print("\n✅ Configuración guardada. ¡Hasta luego!")
                break
            elif choice == "5":
                print("\n👋 Saliendo sin guardar...")
                break
            else:
                print("❌ Opción no válida")


if __name__ == "__main__":
    tool = ConfigTool()
    tool.main_menu()
