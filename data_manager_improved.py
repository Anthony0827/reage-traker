import csv
import os
from datetime import datetime, timedelta
import json


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
        return game_name.lower() in [g['name'].lower() for g in games]
    
    def get_games(self):
        """Obtiene la lista de juegos con información completa"""
        games = []
        if os.path.exists(self.games_file):
            try:
                with open(self.games_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        games.append({
                            'name': row.get('game_name', ''),
                            'date_added': row.get('date_added', ''),
                            'genre': row.get('genre', ''),
                            'notes': row.get('notes', '')
                        })
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
        """Obtiene estadísticas acumuladas de un juego - MEJORADO"""
        stats = {
            'total_sessions': 0,
            'total_time': 0,
            'total_happy': 0,
            'total_angry': 0,
            'total_neutral': 0,
            'avg_rage_percentage': 0,
            'avg_happy_percentage': 0,
            'total_peak_rages': 0,
            'total_happy_streaks': 0,
            'most_common_trend': 'neutral',
            'sessions_by_date': {},
            'worst_session': None,
            'best_session': None
        }
        
        if not os.path.exists(self.sessions_file):
            return stats
        
        sessions = []
        trends = []
        
        with open(self.sessions_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['game'].lower() == game_name.lower():
                    stats['total_sessions'] += 1
                    stats['total_time'] += int(row['duration_seconds'])
                    stats['total_happy'] += int(row['happy_count'])
                    stats['total_angry'] += int(row['angry_count'])
                    stats['total_neutral'] += int(row['neutral_count'])
                    
                    # Nuevos campos
                    angry_pct = float(row.get('angry_percentage', 0))
                    happy_pct = float(row.get('happy_percentage', 0))
                    stats['avg_rage_percentage'] += angry_pct
                    stats['avg_happy_percentage'] += happy_pct
                    stats['total_peak_rages'] += int(row.get('peak_rage_count', 0))
                    stats['total_happy_streaks'] += int(row.get('happiness_streaks', 0))
                    
                    trend = row.get('emotional_trend', 'neutral')
                    trends.append(trend)
                    
                    # Guardar sesión para análisis
                    session_info = {
                        'date': row['date'],
                        'angry_pct': angry_pct,
                        'happy_pct': happy_pct,
                        'duration': int(row['duration_seconds'])
                    }
                    sessions.append(session_info)
                    
                    # Agrupar por fecha
                    date_only = row['date'].split()[0]
                    if date_only not in stats['sessions_by_date']:
                        stats['sessions_by_date'][date_only] = 0
                    stats['sessions_by_date'][date_only] += 1
        
        # Calcular promedios
        if stats['total_sessions'] > 0:
            stats['avg_rage_percentage'] /= stats['total_sessions']
            stats['avg_happy_percentage'] /= stats['total_sessions']
            
            # Tendencia más común
            if trends:
                stats['most_common_trend'] = max(set(trends), key=trends.count)
            
            # Mejor y peor sesión
            if sessions:
                stats['worst_session'] = max(sessions, key=lambda x: x['angry_pct'])
                stats['best_session'] = max(sessions, key=lambda x: x['happy_pct'])
        
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
    
    def get_global_stats(self):
        """Obtiene estadísticas globales de todos los juegos"""
        stats = {
            'total_games': 0,
            'total_sessions': 0,
            'total_playtime': 0,
            'total_rage_moments': 0,
            'total_happy_moments': 0,
            'most_played_game': None,
            'ragiest_game': None,
            'happiest_game': None,
            'recent_sessions': []
        }
        
        games = self.get_games()
        stats['total_games'] = len(games)
        
        if not os.path.exists(self.sessions_file):
            return stats
        
        game_playtimes = {}
        game_rage_scores = {}
        game_happy_scores = {}
        all_sessions = []
        
        with open(self.sessions_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats['total_sessions'] += 1
                duration = int(row['duration_seconds'])
                stats['total_playtime'] += duration
                
                angry_count = int(row['angry_count'])
                happy_count = int(row['happy_count'])
                stats['total_rage_moments'] += angry_count
                stats['total_happy_moments'] += happy_count
                
                game = row['game']
                
                # Acumular por juego
                if game not in game_playtimes:
                    game_playtimes[game] = 0
                    game_rage_scores[game] = 0
                    game_happy_scores[game] = 0
                
                game_playtimes[game] += duration
                game_rage_scores[game] += float(row.get('angry_percentage', 0))
                game_happy_scores[game] += float(row.get('happy_percentage', 0))
                
                # Guardar sesión
                all_sessions.append({
                    'game': game,
                    'date': row['date'],
                    'duration': duration,
                    'angry_pct': float(row.get('angry_percentage', 0)),
                    'happy_pct': float(row.get('happy_percentage', 0))
                })
        
        # Juego más jugado
        if game_playtimes:
            stats['most_played_game'] = max(game_playtimes, key=game_playtimes.get)
            
            # Promediar rage scores
            avg_rage = {game: score / game_playtimes[game] * 100 
                       for game, score in game_rage_scores.items() if game_playtimes[game] > 0}
            avg_happy = {game: score / game_playtimes[game] * 100 
                        for game, score in game_happy_scores.items() if game_playtimes[game] > 0}
            
            if avg_rage:
                stats['ragiest_game'] = max(avg_rage, key=avg_rage.get)
            if avg_happy:
                stats['happiest_game'] = max(avg_happy, key=avg_happy.get)
        
        # Sesiones recientes (últimas 10)
        all_sessions.sort(key=lambda x: x['date'], reverse=True)
        stats['recent_sessions'] = all_sessions[:10]
        
        return stats
    
    def export_to_json(self, output_file="data/export.json"):
        """Exporta todos los datos a JSON para la interfaz web"""
        data = {
            'games': self.get_games(),
            'sessions': self.get_all_sessions(),
            'global_stats': self.get_global_stats(),
            'export_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return output_file
