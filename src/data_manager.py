import csv
import os
from datetime import datetime


class DataManager:
    def __init__(self):
        self.data_dir = "data"
        self.games_file = os.path.join(self.data_dir, "games.csv")
        self.sessions_file = os.path.join(self.data_dir, "sessions.csv")
        self._initialize_files()
    
    def _initialize_files(self):
        """Crea el directorio data y los archivos CSV si no existen"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        # Inicializar games.csv
        if not os.path.exists(self.games_file):
            with open(self.games_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['game_name', 'date_added', 'genre', 'notes'])
        
        # Inicializar sessions.csv con CAMPOS MEJORADOS
        if not os.path.exists(self.sessions_file):
            with open(self.sessions_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'game', 'date', 'duration_seconds', 
                    'happy_count', 'angry_count', 'neutral_count',
                    'happy_percentage', 'angry_percentage', 'neutral_percentage',
                    'peak_rage_count', 'happiness_streaks', 'emotional_trend',
                    'total_frames'
                ])
    
    def add_game(self, game_name, genre="", notes=""):
        """Añade un nuevo juego a la lista"""
        # Verificar si ya existe
        if self.game_exists(game_name):
            return False
        
        with open(self.games_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([game_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), genre, notes])
        return True
    
    def game_exists(self, game_name):
        """Verifica si un juego ya existe"""
        games = self.get_games()
        return game_name.lower() in [g.lower() for g in games]
    
    def get_games(self):
        """Obtiene la lista de juegos como STRINGS SIMPLES (compatible con menu.py antiguo)"""
        games = []
        if os.path.exists(self.games_file):
            try:
                with open(self.games_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Devolver solo el nombre del juego como string
                        games.append(row.get('game_name', ''))
            except (KeyError, csv.Error):
                print("⚠️  Archivo games.csv corrupto, reiniciando...")
                with open(self.games_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['game_name', 'date_added', 'genre', 'notes'])
        return games
    
    def save_session(self, session_data):
        """Guarda los datos de una sesión con DATOS MEJORADOS"""
        with open(self.sessions_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                session_data['game'],
                session_data['date'],
                session_data['duration_seconds'],
                session_data['happy_count'],
                session_data['angry_count'],
                session_data['neutral_count'],
                session_data.get('happy_percentage', 0),
                session_data.get('angry_percentage', 0),
                session_data.get('neutral_percentage', 0),
                session_data.get('peak_rage_count', 0),
                session_data.get('happiness_streaks', 0),
                session_data.get('emotional_trend', 'neutral'),
                session_data.get('total_frames', 0)
            ])
    
    def get_game_stats(self, game_name):
        """Obtiene estadísticas acumuladas de un juego"""
        stats = {
            'total_sessions': 0,
            'total_time': 0,
            'total_happy': 0,
            'total_angry': 0,
            'total_neutral': 0,
            'avg_rage_percentage': 0,
            'avg_happy_percentage': 0,
            'total_peak_rages': 0,
            'total_happy_streaks': 0
        }
        
        if not os.path.exists(self.sessions_file):
            return stats
        
        with open(self.sessions_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_game = str(row.get('game', ''))
                if row_game.lower() == str(game_name).lower():
                    stats['total_sessions'] += 1
                    stats['total_time'] += int(row.get('duration_seconds', 0))
                    stats['total_happy'] += int(row.get('happy_count', 0))
                    stats['total_angry'] += int(row.get('angry_count', 0))
                    stats['total_neutral'] += int(row.get('neutral_count', 0))
                    
                    # Nuevos campos
                    stats['avg_rage_percentage'] += float(row.get('angry_percentage', 0))
                    stats['avg_happy_percentage'] += float(row.get('happy_percentage', 0))
                    stats['total_peak_rages'] += int(row.get('peak_rage_count', 0))
                    stats['total_happy_streaks'] += int(row.get('happiness_streaks', 0))
        
        # Calcular promedios
        if stats['total_sessions'] > 0:
            stats['avg_rage_percentage'] /= stats['total_sessions']
            stats['avg_happy_percentage'] /= stats['total_sessions']
        
        return stats
    
    def get_all_sessions(self, game_name=None):
        """Obtiene todas las sesiones, opcionalmente filtradas por juego"""
        sessions = []
        
        if not os.path.exists(self.sessions_file):
            return sessions
        
        with open(self.sessions_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if game_name is None or str(row.get('game', '')).lower() == str(game_name).lower():
                    sessions.append(row)
        
        return sessions
