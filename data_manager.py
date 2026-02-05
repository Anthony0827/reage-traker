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
                writer.writerow(['game_name', 'date_added'])
        
        # Inicializar sessions.csv
        if not os.path.exists(self.sessions_file):
            with open(self.sessions_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['game', 'date', 'duration_seconds', 'happy_count', 'angry_count', 'neutral_count'])
    
    def add_game(self, game_name):
        """Añade un nuevo juego a la lista"""
        # Verificar si ya existe
        if self.game_exists(game_name):
            return False
        
        with open(self.games_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([game_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        return True
    
    def game_exists(self, game_name):
        """Verifica si un juego ya existe"""
        games = self.get_games()
        return game_name.lower() in [g.lower() for g in games]
    
    def get_games(self):
        """Obtiene la lista de juegos"""
        games = []
        if os.path.exists(self.games_file):
            try:
                with open(self.games_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    games = [row['game_name'] for row in reader if 'game_name' in row]
            except (KeyError, csv.Error):
                # Si el archivo está corrupto, reiniciarlo
                print("⚠️  Archivo games.csv corrupto, reiniciando...")
                with open(self.games_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['game_name', 'date_added'])
        return games
    
    def save_session(self, session_data):
        """Guarda los datos de una sesión"""
        with open(self.sessions_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                session_data['game'],
                session_data['date'],
                session_data['duration_seconds'],
                session_data['happy_count'],
                session_data['angry_count'],
                session_data['neutral_count']
            ])
    
    def get_game_stats(self, game_name):
        """Obtiene estadísticas acumuladas de un juego"""
        stats = {
            'total_sessions': 0,
            'total_time': 0,
            'total_happy': 0,
            'total_angry': 0,
            'total_neutral': 0
        }
        
        if not os.path.exists(self.sessions_file):
            return stats
        
        with open(self.sessions_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['game'].lower() == game_name.lower():
                    stats['total_sessions'] += 1
                    stats['total_time'] += int(row['duration_seconds'])
                    stats['total_happy'] += int(row['happy_count'])
                    stats['total_angry'] += int(row['angry_count'])
                    stats['total_neutral'] += int(row['neutral_count'])
        
        return stats
    
    def get_all_sessions(self, game_name=None):
        """Obtiene todas las sesiones, opcionalmente filtradas por juego"""
        sessions = []
        
        if not os.path.exists(self.sessions_file):
            return sessions
        
        with open(self.sessions_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if game_name is None or row['game'].lower() == game_name.lower():
                    sessions.append(row)
        
        return sessions