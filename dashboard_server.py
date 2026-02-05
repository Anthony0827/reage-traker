#!/usr/bin/env python3
"""
RAGE TRACKER - Dashboard Server
Servidor web simple para visualizar el dashboard con datos reales
"""

import http.server
import socketserver
import json
import csv
import os
from datetime import datetime
from urllib.parse import parse_qs, urlparse


class RageTrackerHandler(http.server.SimpleHTTPRequestHandler):
    """Handler personalizado para servir el dashboard y la API de datos"""
    
    def do_GET(self):
        """Maneja las peticiones GET"""
        parsed_path = urlparse(self.path)
        
        # API endpoint para obtener datos
        if parsed_path.path == '/api/data':
            self.serve_api_data()
        # Servir el dashboard
        elif parsed_path.path == '/' or parsed_path.path == '/dashboard':
            self.serve_dashboard()
        else:
            # Servir archivos estáticos normalmente
            super().do_GET()
    
    def serve_dashboard(self):
        """Sirve el archivo dashboard.html"""
        try:
            with open('dashboard.html', 'r', encoding='utf-8') as f:
                content = f.read()
                
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_error(404, "Dashboard not found")
    
    def serve_api_data(self):
        """Sirve los datos en formato JSON desde los archivos CSV"""
        try:
            data = self.load_data_from_csv()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            json_data = json.dumps(data, ensure_ascii=False, indent=2)
            self.wfile.write(json_data.encode('utf-8'))
        except Exception as e:
            self.send_error(500, f"Error loading data: {str(e)}")
    
    def load_data_from_csv(self):
        """Carga los datos desde los archivos CSV"""
        data_dir = "data"
        games_file = os.path.join(data_dir, "games.csv")
        sessions_file = os.path.join(data_dir, "sessions.csv")
        
        # Cargar juegos
        games = []
        if os.path.exists(games_file):
            with open(games_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    games.append({
                        'name': row.get('game_name', ''),
                        'genre': row.get('genre', ''),
                        'date_added': row.get('date_added', ''),
                        'notes': row.get('notes', '')
                    })
        
        # Cargar sesiones
        sessions = []
        if os.path.exists(sessions_file):
            with open(sessions_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sessions.append({
                        'game': row.get('game', ''),
                        'date': row.get('date', ''),
                        'duration_seconds': int(row.get('duration_seconds', 0)),
                        'happy_count': int(row.get('happy_count', 0)),
                        'angry_count': int(row.get('angry_count', 0)),
                        'neutral_count': int(row.get('neutral_count', 0)),
                        'happy_percentage': float(row.get('happy_percentage', 0)),
                        'angry_percentage': float(row.get('angry_percentage', 0)),
                        'neutral_percentage': float(row.get('neutral_percentage', 0)),
                        'peak_rage_count': int(row.get('peak_rage_count', 0)),
                        'happiness_streaks': int(row.get('happiness_streaks', 0)),
                        'emotional_trend': row.get('emotional_trend', 'neutral'),
                        'total_frames': int(row.get('total_frames', 0))
                    })
        
        # Calcular estadísticas globales
        global_stats = self.calculate_global_stats(sessions)
        
        return {
            'games': games,
            'sessions': sessions,
            'global_stats': global_stats,
            'export_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def calculate_global_stats(self, sessions):
        """Calcula estadísticas globales desde las sesiones"""
        if not sessions:
            return {
                'total_sessions': 0,
                'total_playtime': 0,
                'total_rage_moments': 0,
                'total_happy_moments': 0,
                'most_played_game': None,
                'ragiest_game': None,
                'happiest_game': None
            }
        
        total_sessions = len(sessions)
        total_playtime = sum(s['duration_seconds'] for s in sessions)
        total_rage = sum(s['angry_count'] for s in sessions)
        total_happy = sum(s['happy_count'] for s in sessions)
        
        # Análisis por juego
        game_stats = {}
        for session in sessions:
            game = session['game']
            if game not in game_stats:
                game_stats[game] = {
                    'playtime': 0,
                    'rage_sum': 0,
                    'happy_sum': 0,
                    'sessions': 0
                }
            
            game_stats[game]['playtime'] += session['duration_seconds']
            game_stats[game]['rage_sum'] += session['angry_percentage']
            game_stats[game]['happy_sum'] += session['happy_percentage']
            game_stats[game]['sessions'] += 1
        
        # Calcular promedios
        most_played = None
        ragiest = None
        happiest = None
        max_playtime = 0
        max_rage = 0
        max_happy = 0
        
        for game, stats in game_stats.items():
            avg_rage = stats['rage_sum'] / stats['sessions']
            avg_happy = stats['happy_sum'] / stats['sessions']
            
            if stats['playtime'] > max_playtime:
                max_playtime = stats['playtime']
                most_played = game
            
            if avg_rage > max_rage:
                max_rage = avg_rage
                ragiest = game
            
            if avg_happy > max_happy:
                max_happy = avg_happy
                happiest = game
        
        return {
            'total_sessions': total_sessions,
            'total_playtime': total_playtime,
            'total_rage_moments': total_rage,
            'total_happy_moments': total_happy,
            'most_played_game': most_played,
            'ragiest_game': ragiest,
            'happiest_game': happiest
        }


def start_server(port=8000):
    """Inicia el servidor web"""
    handler = RageTrackerHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print("\n" + "=" * 60)
        print("  🎮 RAGE TRACKER - Dashboard Server")
        print("=" * 60)
        print(f"\n✅ Servidor iniciado en http://localhost:{port}")
        print(f"\n📊 Accede al dashboard en:")
        print(f"   → http://localhost:{port}/dashboard")
        print(f"\n💾 API de datos disponible en:")
        print(f"   → http://localhost:{port}/api/data")
        print(f"\n⚠️  Presiona Ctrl+C para detener el servidor\n")
        print("=" * 60 + "\n")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n👋 Servidor detenido. ¡Hasta luego!")
            httpd.shutdown()


if __name__ == "__main__":
    import sys
    
    # Verificar que existan los archivos necesarios
    if not os.path.exists('dashboard.html'):
        print("❌ Error: No se encuentra dashboard.html")
        print("   Asegúrate de que el archivo esté en el mismo directorio.")
        sys.exit(1)
    
    if not os.path.exists('data'):
        print("⚠️  Advertencia: No existe el directorio 'data'")
        print("   El dashboard mostrará datos de ejemplo hasta que ejecutes el tracker.")
    
    # Obtener puerto desde argumentos o usar 8000 por defecto
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"⚠️  Puerto inválido: {sys.argv[1]}. Usando puerto 8000.")
    
    start_server(port)
