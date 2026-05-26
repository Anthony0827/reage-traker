"""
RAGE TRACKER - Gestión de datos (CSV)
=====================================
Cambios Fase 3:
- Añadidas columnas opcionales de micrófono al final de sessions.csv
  (scream_count, scream_peak_db, scream_total_seconds, mic_device_name).
- Migración automática y NO destructiva del esquema: si sessions.csv es de una
  versión anterior, se reescribe añadiendo las columnas nuevas con valores por
  defecto. Las sesiones antiguas siguen cargándose sin errores (.get + default).
- Rutas relativas a la raíz del proyecto (Path(__file__)) de cara al futuro .exe.
"""

import csv
import os
import tempfile
from datetime import datetime
from pathlib import Path


# Raíz del proyecto (… / rage_tracker), independiente del cwd → robusto para .exe
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Esquema canónico de sessions.csv. Las 7 últimas son las nuevas (Fase 3 + insultos).
BASE_SESSION_FIELDS = [
    "game", "date", "duration_seconds",
    "happy_count", "angry_count", "neutral_count",
    "happy_percentage", "angry_percentage", "neutral_percentage",
    "peak_rage_count", "happiness_streaks", "emotional_trend",
    "total_frames",
]
SCREAM_FIELDS = [
    "scream_count", "scream_peak_db", "scream_total_seconds", "mic_device_name",
]
INSULT_FIELDS = [
    "insult_count", "insult_peak_count", "insult_model_name",
]
SESSION_FIELDS = BASE_SESSION_FIELDS + SCREAM_FIELDS + INSULT_FIELDS

# Valor por defecto por campo (para rellenar sesiones antiguas / sin micrófono / sin insultos)
# Uso 0 para numéricos y string vacío para los de texto, así los CSV viejos
# se migran sin perder información y sin romper nada.
_FIELD_DEFAULTS = {f: 0 for f in SESSION_FIELDS}
_FIELD_DEFAULTS.update({
    "game": "",
    "date": "",
    "emotional_trend": "neutral",
    "scream_peak_db": 0.0,
    "scream_total_seconds": 0.0,
    "mic_device_name": "",
    "insult_peak_count": 0,
    "insult_model_name": "",
})

GAMES_FIELDS = ["game_name", "date_added", "genre", "notes"]


class DataManager:
    """Gestor de persistencia en CSV para RAGE TRACKER.

    Decidí mantener CSV como formato de almacenamiento porque es portable,
    legible y no necesita servidor de base de datos. La migración entre
    versiones del esquema es automática y atómica (reescritura con tempfile).
    """

    def __init__(self, data_dir=None):
        # data/ relativa a la raíz del proyecto por defecto (no al cwd).
        # Esto es clave para el futuro .exe: sin importar desde dónde se lance,
        # siempre encuentra los datos al lado del código.
        self.data_dir = str(data_dir) if data_dir else str(PROJECT_ROOT / "data")
        self.games_file = os.path.join(self.data_dir, "games.csv")
        self.sessions_file = os.path.join(self.data_dir, "sessions.csv")
        self._initialize_files()

    # ------------------------------------------------------------------ #
    # Inicialización y migración
    # ------------------------------------------------------------------ #
    def _initialize_files(self):
        """Crea data/ y los CSV si no existen; migra esquemas antiguos."""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        if not os.path.exists(self.games_file):
            with open(self.games_file, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(GAMES_FIELDS)

        if not os.path.exists(self.sessions_file):
            with open(self.sessions_file, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(SESSION_FIELDS)
        else:
            self._migrate_sessions_schema()

    def _migrate_sessions_schema(self):
        """Si faltan columnas nuevas en sessions.csv, reescribe el fichero
        añadiéndolas con valores por defecto. Operación atómica: si algo falla
        a mitad de camino, el archivo original queda intacto."""
        try:
            with open(self.sessions_file, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                header = reader.fieldnames or []
                if all(field in header for field in SESSION_FIELDS):
                    return  # ya está al día
                rows = list(reader)
        except (OSError, csv.Error):
            return

        # Reescritura atómica con el esquema completo.
        # Uso mkstemp + os.replace en lugar de escribirlo directo para que
        # si el proceso muere a mitad, el CSV original no se corrompa.
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.data_dir, suffix=".csv")
        try:
            with os.fdopen(tmp_fd, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=SESSION_FIELDS, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow({
                        field: row.get(field, _FIELD_DEFAULTS[field])
                        for field in SESSION_FIELDS
                    })
            os.replace(tmp_path, self.sessions_file)
            print("[i] sessions.csv migrado al nuevo esquema (columnas de micrófono y insultos añadidas).")
        except OSError:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ------------------------------------------------------------------ #
    # Juegos
    # ------------------------------------------------------------------ #
    def add_game(self, game_name, genre="", notes=""):
        """Añade un nuevo juego a la lista. Si ya existe, no hace nada."""
        if self.game_exists(game_name):
            return False
        with open(self.games_file, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [game_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), genre, notes]
            )
        return True

    def game_exists(self, game_name):
        games = self.get_games()
        return game_name.lower() in [g.lower() for g in games]

    def get_games(self):
        """Lista de juegos como strings simples (compatible con menu.py)."""
        games = []
        if os.path.exists(self.games_file):
            try:
                with open(self.games_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get("game_name", "")
                        if name:
                            games.append(name)
            except (KeyError, csv.Error):
                # Si el CSV está corrupto, lo regenero desde cero.
                # Prefiero perder la metadata de juegos que crashear la app.
                print("⚠️  Archivo games.csv corrupto, reiniciando...")
                with open(self.games_file, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(GAMES_FIELDS)
        return games

    # ------------------------------------------------------------------ #
    # Sesiones
    # ------------------------------------------------------------------ #
    def save_session(self, session_data):
        """Guarda una sesión. Acepta los campos de micrófono como opcionales;
        cualquier ausencia se rellena con el valor por defecto del esquema."""
        row = [
            session_data.get(field, _FIELD_DEFAULTS[field])
            for field in SESSION_FIELDS
        ]
        with open(self.sessions_file, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

    def get_game_stats(self, game_name):
        """Estadísticas acumuladas de un juego (incluye métricas de gritos y insultos)."""
        stats = {
            "total_sessions": 0,
            "total_time": 0,
            "total_happy": 0,
            "total_angry": 0,
            "total_neutral": 0,
            "avg_rage_percentage": 0,
            "avg_happy_percentage": 0,
            "total_peak_rages": 0,
            "total_happy_streaks": 0,
            # Fase 3 (micrófono)
            "total_screams": 0,
            "total_scream_seconds": 0.0,
            "avg_scream_count": 0,
            # Fase 5 (insultos)
            "total_insults": 0,
            "avg_insult_count": 0,
        }

        if not os.path.exists(self.sessions_file):
            return stats

        with open(self.sessions_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("game", "")).lower() != str(game_name).lower():
                    continue
                stats["total_sessions"] += 1
                stats["total_time"] += _as_int(row.get("duration_seconds"))
                stats["total_happy"] += _as_int(row.get("happy_count"))
                stats["total_angry"] += _as_int(row.get("angry_count"))
                stats["total_neutral"] += _as_int(row.get("neutral_count"))
                stats["avg_rage_percentage"] += _as_float(row.get("angry_percentage"))
                stats["avg_happy_percentage"] += _as_float(row.get("happy_percentage"))
                stats["total_peak_rages"] += _as_int(row.get("peak_rage_count"))
                stats["total_happy_streaks"] += _as_int(row.get("happiness_streaks"))
                # Campos de micrófono: opcionales (.get con default)
                stats["total_screams"] += _as_int(row.get("scream_count", 0))
                stats["total_scream_seconds"] += _as_float(row.get("scream_total_seconds", 0))
                # Campos de insultos: opcionales (.get con default)
                stats["total_insults"] += _as_int(row.get("insult_count", 0))

        if stats["total_sessions"] > 0:
            stats["avg_rage_percentage"] /= stats["total_sessions"]
            stats["avg_happy_percentage"] /= stats["total_sessions"]
            stats["avg_scream_count"] = stats["total_screams"] / stats["total_sessions"]
            stats["avg_insult_count"] = stats["total_insults"] / stats["total_sessions"]

        return stats

    def get_all_sessions(self, game_name=None):
        """Todas las sesiones (dicts), opcionalmente filtradas por juego."""
        sessions = []
        if not os.path.exists(self.sessions_file):
            return sessions
        with open(self.sessions_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if game_name is None or str(row.get("game", "")).lower() == str(game_name).lower():
                    sessions.append(row)
        return sessions

    def get_last_session(self):
        """Devuelve la última sesión registrada (dict) o None."""
        sessions = self.get_all_sessions()
        return sessions[-1] if sessions else None


# ---------------------------------------------------------------------- #
# Conversión tolerante (evita ValueError con celdas vacías o '0,0')
# ---------------------------------------------------------------------- #
def _as_int(value, default=0):
    """Convierte un valor de CSV a entero de forma segura.

    El double-cast int(float(...)) me protege de valores como '3.0' o '0,5'
    que a veces aparecen cuando Excel toca los CSV."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
