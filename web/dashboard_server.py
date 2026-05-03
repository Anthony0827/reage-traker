#!/usr/bin/env python3
"""
RAGE TRACKER - Dashboard Server
===============================
Fase 3: rutas relativas a la raíz del proyecto (Path(__file__).parent.parent)
para que funcione lanzado desde cualquier cwd y empaquetado como .exe. Añade
`run_in_thread(port)` para que el launcher arranque el servidor en un hilo
daemon (idempotente: si ya corre, reutiliza el puerto). La API expone ahora los
campos de gritos (scream_*) con valores por defecto 0 → compatible con CSV
antiguos sin esas columnas.
"""

import http.server
import socketserver
import json
import csv
import os
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


# Raíz del proyecto y rutas absolutas derivadas (no dependen del cwd).
# Crucial para que el servidor funcione cuando se lanza desde la GUI
# o desde cualquier otro directorio, y para el futuro empaquetado .exe.
ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_HTML = ROOT / "web" / "dashboard.html"
DATA_DIR = ROOT / "data"


class RageTrackerHandler(http.server.SimpleHTTPRequestHandler):
    """Handler personalizado para servir el dashboard y la API de datos"""

    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/api/data':
            self.serve_api_data()
        elif parsed_path.path in ('/', '/dashboard'):
            self.serve_dashboard()
        else:
            super().do_GET()

    def log_message(self, *args):
        """Silencioso por defecto (no ensucia la consola de la GUI).

        Cuando el launcher arranca el servidor en un hilo daemon, no quiero
        que cada petición HTTP escupa una línea en la terminal. Si alguien
        necesita debug, que descomente esto."""
        pass

    def serve_dashboard(self):
        try:
            with open(DASHBOARD_HTML, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_error(404, "Dashboard not found")

    def serve_api_data(self):
        try:
            data = self.load_data_from_csv()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            json_data = json.dumps(data, ensure_ascii=False, indent=2)
            self.wfile.write(json_data.encode('utf-8'))
        except Exception as e:  # noqa: BLE001
            self.send_error(500, f"Error loading data: {str(e)}")

    # --- helpers tolerantes a campos ausentes / valores corruptos ---------- #
    # Uso el mismo patrón que data_manager.py: int(float(...)) para tolerar
    # formatos tipo '0,5' o '3.0' que a veces aparecen cuando Excel toca los CSV.
    @staticmethod
    def _as_int(value, default=0):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def load_data_from_csv(self):
        games_file = DATA_DIR / "games.csv"
        sessions_file = DATA_DIR / "sessions.csv"

        games = []
        if games_file.exists():
            with open(games_file, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    games.append({
                        'name': row.get('game_name', ''),
                        'genre': row.get('genre', ''),
                        'date_added': row.get('date_added', ''),
                        'notes': row.get('notes', '')
                    })

        sessions = []
        if sessions_file.exists():
            with open(sessions_file, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    sessions.append({
                        'game': row.get('game', ''),
                        'date': row.get('date', ''),
                        'duration_seconds': self._as_int(row.get('duration_seconds', 0)),
                        'happy_count': self._as_int(row.get('happy_count', 0)),
                        'angry_count': self._as_int(row.get('angry_count', 0)),
                        'neutral_count': self._as_int(row.get('neutral_count', 0)),
                        'happy_percentage': self._as_float(row.get('happy_percentage', 0)),
                        'angry_percentage': self._as_float(row.get('angry_percentage', 0)),
                        'neutral_percentage': self._as_float(row.get('neutral_percentage', 0)),
                        'peak_rage_count': self._as_int(row.get('peak_rage_count', 0)),
                        'happiness_streaks': self._as_int(row.get('happiness_streaks', 0)),
                        'emotional_trend': row.get('emotional_trend', 'neutral'),
                        'total_frames': self._as_int(row.get('total_frames', 0)),
                        # --- campos de micrófono (Fase 3, opcionales) ---
                        'scream_count': self._as_int(row.get('scream_count', 0)),
                        'scream_peak_db': self._as_float(row.get('scream_peak_db', 0)),
                        'scream_total_seconds': self._as_float(row.get('scream_total_seconds', 0)),
                        'mic_device_name': row.get('mic_device_name', '') or '',
                    })

        global_stats = self.calculate_global_stats(sessions)

        return {
            'games': games,
            'sessions': sessions,
            'global_stats': global_stats,
            'export_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def calculate_global_stats(self, sessions):
        if not sessions:
            return {
                'total_sessions': 0,
                'total_playtime': 0,
                'total_rage_moments': 0,
                'total_happy_moments': 0,
                'total_screams': 0,
                'most_played_game': None,
                'ragiest_game': None,
                'happiest_game': None,
                'loudest_game': None,
            }

        total_sessions = len(sessions)
        total_playtime = sum(s['duration_seconds'] for s in sessions)
        total_rage = sum(s['angry_count'] for s in sessions)
        total_happy = sum(s['happy_count'] for s in sessions)
        total_screams = sum(s.get('scream_count', 0) for s in sessions)

        game_stats = {}
        for session in sessions:
            game = session['game']
            gs = game_stats.setdefault(game, {
                'playtime': 0, 'rage_sum': 0, 'happy_sum': 0,
                'scream_sum': 0, 'sessions': 0,
            })
            gs['playtime'] += session['duration_seconds']
            gs['rage_sum'] += session['angry_percentage']
            gs['happy_sum'] += session['happy_percentage']
            gs['scream_sum'] += session.get('scream_count', 0)
            gs['sessions'] += 1

        most_played = ragiest = happiest = loudest = None
        max_playtime = max_rage = max_happy = max_scream = -1.0

        for game, stats in game_stats.items():
            avg_rage = stats['rage_sum'] / stats['sessions']
            avg_happy = stats['happy_sum'] / stats['sessions']
            if stats['playtime'] > max_playtime:
                max_playtime, most_played = stats['playtime'], game
            if avg_rage > max_rage:
                max_rage, ragiest = avg_rage, game
            if avg_happy > max_happy:
                max_happy, happiest = avg_happy, game
            if stats['scream_sum'] > max_scream:
                max_scream, loudest = stats['scream_sum'], game

        if max_scream <= 0:
            loudest = None  # sin datos de gritos todavía

        return {
            'total_sessions': total_sessions,
            'total_playtime': total_playtime,
            'total_rage_moments': total_rage,
            'total_happy_moments': total_happy,
            'total_screams': total_screams,
            'most_played_game': most_played,
            'ragiest_game': ragiest,
            'happiest_game': happiest,
            'loudest_game': loudest,
        }


class _ThreadingServer(socketserver.ThreadingTCPServer):
    """Servidor TCP con hilos y reutilización de dirección.

    allow_reuse_address evita el error 'Address already in use' al reiniciar
    el servidor. daemon_threads asegura que los hilos no bloqueen el cierre
    de la app principal."""
    allow_reuse_address = True
    daemon_threads = True


# --------------------------------------------------------------------------- #
#  Arranque en hilo interno (lo usa el launcher)                              #
# --------------------------------------------------------------------------- #
# run_in_thread es idempotente: si el servidor ya está corriendo, devuelve
# el puerto existente. Si el puerto pedido está ocupado, prueba los siguientes
# hasta encontrar uno libre. Esto evita colisiones cuando hay múltiples
# instancias de la app o cuando otro proceso ya tomó el 8000.
_server_lock = threading.Lock()
_server_thread = None
_server_port = None
_httpd = None


def run_in_thread(port=8000, max_tries=10):
    """Arranca el servidor en un hilo daemon y devuelve el puerto real.

    Idempotente: si ya hay un servidor de esta misma sesión corriendo, devuelve
    su puerto sin abrir otro. Si el puerto está ocupado, prueba los siguientes.
    """
    global _server_thread, _server_port, _httpd
    with _server_lock:
        if _server_thread is not None and _server_thread.is_alive():
            return _server_port

        last_error = None
        for candidate in range(port, port + max_tries):
            try:
                httpd = _ThreadingServer(("", candidate), RageTrackerHandler)
            except OSError as exc:  # puerto ocupado u otro problema de bind
                last_error = exc
                continue

            _httpd = httpd
            _server_port = candidate
            _server_thread = threading.Thread(
                target=httpd.serve_forever, name="rt-dashboard", daemon=True
            )
            _server_thread.start()
            return candidate

        # Si todos los puertos estaban ocupados, asumo que ya hay un
        # dashboard escuchando en el puerto pedido y lo reutilizo.
        if last_error is not None:
            _server_port = port
            return port
        raise RuntimeError("No se pudo arrancar el servidor del dashboard.")


def start_server(port=8000):
    """Inicia el servidor en primer plano (modo standalone / CLI)."""
    with _ThreadingServer(("", port), RageTrackerHandler) as httpd:
        print("\n" + "=" * 60)
        print("  🎮 RAGE TRACKER - Dashboard Server")
        print("=" * 60)
        print(f"\n[OK] Servidor iniciado en http://localhost:{port}")
        print(f"\n📊 Accede al dashboard en:")
        print(f"   → http://localhost:{port}/dashboard")
        print("=" * 60 + "\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n[bye] Servidor detenido. ¡Hasta luego!")
            httpd.shutdown()


if __name__ == "__main__":
    import sys

    if not DASHBOARD_HTML.exists():
        print("[!] Error: No se encuentra web/dashboard.html")
        sys.exit(1)
    if not DATA_DIR.exists():
        print("[!] Advertencia: No existe el directorio 'data'.")
        print("   El dashboard mostrará datos vacíos hasta que ejecutes el tracker.")

    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"[!] Puerto inválido: {sys.argv[1]}. Usando puerto 8000.")
    start_server(port)