"""
RAGE TRACKER - Launcher / GUI nativa  [NUEVO]
=============================================
Ventana de inicio unificada: el único punto de entrada que ve el usuario.
Desde aquí se inicia una sesión (panel de configuración con selección de
sensores y medidor de micrófono en vivo) o se abre el dashboard en el navegador.

DECISIÓN DE IMPLEMENTACIÓN (el plan original pedía CustomTkinter con PyQt6 de
fallback, pero hice esto en su lugar):
- Primario: **CustomTkinter** (tema oscuro, look gaming).
- Fallback: **tkinter** estándar (incluido en CPython) con tema oscuro manual,
  EN LUGAR de PyQt6. Lo decidí así por tres razones: (1) la app SIEMPRE arranca
  aunque no se instale ninguna dependencia extra, (2) evito mantener una segunda
  GUI pesada, y (3) el empaquetado .exe es más sencillo. Un único árbol de
  widgets sirve a ambos backends mediante pequeñas fábricas (_mk_*).

Las sesiones se lanzan como subproceso (`main.py --session ...`) para que Tk y
la ventana de OpenCV no compitan por el hilo principal (clave en macOS).
"""

from __future__ import annotations

import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

# ---- Backends de GUI (import tolerante: el módulo nunca peta al importarse) --
# Si CustomTkinter no está instalado, caigo a tkinter automáticamente.
# Si no hay ninguno, GUI_AVAILABLE es False y launch() imprime un aviso.
_CTK = None
_TK = None
_TTK = None
try:
    import customtkinter as _CTK  # type: ignore
except Exception:
    _CTK = None
try:
    import tkinter as _TK  # type: ignore
    from tkinter import ttk as _TTK  # type: ignore
except Exception:
    _TK = None
    _TTK = None

GUI_AVAILABLE = (_CTK is not None) or (_TK is not None)

from src.data_manager import DataManager
try:
    from src.audio_monitor import AudioMonitor, audio_available, diagnose
except Exception as _exc:  # pragma: no cover
    AudioMonitor = None  # type: ignore

    def audio_available() -> bool:  # type: ignore
        return False

    def diagnose() -> str:
        return (
            f"No se pudo cargar el módulo de audio: {_exc}\n\n"
            "Instalá sounddevice con: pip install sounddevice==0.4.7"
        )


# Rutas (raíz del proyecto, robusto frente al cwd / futuro .exe)
ROOT = Path(__file__).resolve().parents[1]
MAIN_PY = ROOT / "main.py"
DASHBOARD_PORT = 8000

# ---- Paleta (coherente con el dashboard) ------------------------------------
# Mismos tokens que dashboard.html para que la GUI y el dashboard se sientan
# parte de la misma app aunque uno sea Tk y el otro HTML+CSS.
BG        = "#0a0d14"
SURFACE   = "#11161f"
SURFACE2  = "#161c28"
SURFACE3  = "#1c2332"
BORDER    = "#232b3b"
TEXT      = "#e8ecf3"
TEXT2     = "#a4adc1"
TEXT3     = "#6a7488"
CYAN      = "#5cf0d2"
CYAN_DIM  = "#2fb89c"
RAGE      = "#ff5260"
HAPPY     = "#7cd87a"
WARN      = "#ffc857"

MONO = "JetBrains Mono"
DISP = "Big Shoulders Display"
# Familias de respaldo si las anteriores no están instaladas en el sistema
MONO_FB = (MONO, "Consolas", "DejaVu Sans Mono", "Courier")


# =============================================================================
# Fábricas de widgets (un único layout, dos backends)
# =============================================================================
# Cada fábrica crea el widget con CustomTkinter si está disponible, si no,
# con tkinter estándar. Así mantengo UN solo árbol de widgets y no duplico
# layouts. La API de las fábricas es mínima: solo los parámetros que uso.
def _ctk() -> bool:
    return _CTK is not None


def _mk_frame(parent, fg=SURFACE, corner=12, border=0, border_color=BORDER):
    if _ctk():
        return _CTK.CTkFrame(parent, fg_color=fg, corner_radius=corner,
                             border_width=border, border_color=border_color)
    return _TK.Frame(parent, bg=fg, highlightthickness=border,
                     highlightbackground=border_color, highlightcolor=border_color, bd=0)


def _mk_label(parent, text, font, color=TEXT, bg=SURFACE, anchor="w", justify="left"):
    if _ctk():
        return _CTK.CTkLabel(parent, text=text, font=font, text_color=color,
                             fg_color="transparent", anchor=anchor, justify=justify)
    return _TK.Label(parent, text=text, font=font, fg=color, bg=bg,
                     anchor=anchor, justify=justify)


def _mk_button(parent, text, command, fg=CYAN, hover=CYAN_DIM, text_color=BG,
               font=(MONO, 13, "bold"), height=42, width=160):
    if _ctk():
        return _CTK.CTkButton(parent, text=text, command=command, fg_color=fg,
                              hover_color=hover, text_color=text_color, font=font,
                              height=height, width=width, corner_radius=8)
    return _TK.Button(parent, text=text, command=command, bg=fg, fg=text_color,
                      activebackground=hover, activeforeground=text_color, font=font,
                      relief="flat", bd=0, padx=16, pady=8, cursor="hand2",
                      highlightthickness=0)


def _mk_entry(parent, textvariable, placeholder=""):
    if _ctk():
        return _CTK.CTkEntry(parent, textvariable=textvariable, placeholder_text=placeholder,
                             fg_color=SURFACE2, border_color=BORDER, text_color=TEXT,
                             font=(MONO, 12), height=34, corner_radius=6)
    return _TK.Entry(parent, textvariable=textvariable, bg=SURFACE2, fg=TEXT,
                     insertbackground=CYAN, relief="flat", font=(MONO, 12),
                     highlightthickness=1, highlightbackground=BORDER, highlightcolor=CYAN)


def _mk_optionmenu(parent, variable, values, command=None):
    values = values or ["—"]
    if _ctk():
        return _CTK.CTkOptionMenu(parent, variable=variable, values=values, command=command,
                                  fg_color=SURFACE2, button_color=SURFACE3, text_color=TEXT,
                                  button_hover_color=BORDER, font=(MONO, 12),
                                  dropdown_font=(MONO, 12), height=34, corner_radius=6)
    om = _TK.OptionMenu(parent, variable, *values,
                        command=(command if command else None))
    om.config(bg=SURFACE2, fg=TEXT, activebackground=SURFACE3, activeforeground=TEXT,
              relief="flat", font=(MONO, 12), highlightthickness=1,
              highlightbackground=BORDER, bd=0)
    return om


def _mk_checkbox(parent, text, variable, command=None, font=(MONO, 13)):
    if _ctk():
        return _CTK.CTkCheckBox(parent, text=text, variable=variable, command=command,
                                font=font, text_color=TEXT, fg_color=CYAN,
                                hover_color=CYAN_DIM, checkmark_color=BG, border_color=BORDER)
    return _TK.Checkbutton(parent, text=text, variable=variable, command=command,
                           font=font, fg=TEXT, bg=SURFACE, selectcolor=SURFACE2,
                           activebackground=SURFACE, activeforeground=CYAN,
                           highlightthickness=0, bd=0)


def _mk_slider(parent, from_, to, variable, command=None):
    if _ctk():
        return _CTK.CTkSlider(parent, from_=from_, to=to, variable=variable, command=command,
                              fg_color=SURFACE2, progress_color=CYAN, button_color=CYAN,
                              button_hover_color=CYAN_DIM, height=16)
    return _TK.Scale(parent, from_=from_, to=to, variable=variable, command=command,
                     orient="horizontal", bg=SURFACE, fg=TEXT, troughcolor=SURFACE2,
                     highlightthickness=0, bd=0, sliderrelief="flat", showvalue=False)


def _mk_canvas(parent, width, height, bg=SURFACE2):
    if _ctk():
        return _CTK.CTkCanvas(parent, width=width, height=height, bg=bg, highlightthickness=0)
    return _TK.Canvas(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0)


def _str_var(value=""):
    return _TK.StringVar(value=value)


def _bool_var(value=False):
    return _TK.BooleanVar(value=value)


def _double_var(value=0.0):
    return _TK.DoubleVar(value=value)


# =============================================================================
# Servidor del dashboard (thread interno, idempotente)
# =============================================================================
# Cargo web/dashboard_server.py dinámicamente para que el launcher no tenga
# que importarlo al arrancar. El servidor corre en un hilo daemon y es
# idempotente: si ya está corriendo, run_in_thread devuelve el puerto sin más.
_DASH_MOD = None


def _ensure_dashboard_running(port: int = DASHBOARD_PORT) -> int:
    """Carga web/dashboard_server.py y arranca su servidor en un hilo daemon.
    Es idempotente: si ya hay un servidor (propio o externo) en el puerto,
    simplemente devuelve el puerto."""
    global _DASH_MOD
    try:
        if _DASH_MOD is None:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "rt_dashboard_server", str(ROOT / "web" / "dashboard_server.py")
            )
            _DASH_MOD = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_DASH_MOD)  # type: ignore
        return _DASH_MOD.run_in_thread(port)
    except Exception as exc:  # noqa: BLE001
        print(f"[!] No se pudo iniciar el servidor del dashboard: {exc}")
        return port


# =============================================================================
# APP PRINCIPAL
# =============================================================================
class RageTrackerApp:
    """Ventana principal del launcher.

    Diseñé dos pantallas: la ventana principal con dos tarjetas-botón
    (INICIAR TRACKER y VER ESTADÍSTICAS) y un panel de configuración
    que se abre como Toplevel al hacer clic en INICIAR TRACKER.
    """

    def __init__(self):
        if _ctk():
            _CTK.set_appearance_mode("dark")
            self.root = _CTK.CTk()
        else:
            self.root = _TK.Tk()
        self.root.title("RAGE TRACKER")
        self.root.configure(bg=BG)
        self.root.geometry("720x540")
        try:
            self.root.minsize(640, 500)
        except Exception:
            pass

        self.dm = DataManager()
        self._config_win = None
        self._preview = None      # AudioMonitor de previsualización (panel de sesión)
        self._vu_after = None
        self._build_main()

    # ------------------------------------------------------------------ #
    # Ventana principal
    # ------------------------------------------------------------------ #
    def _build_main(self):
        root_bg = BG
        container = _mk_frame(self.root, fg=root_bg, corner=0)
        container.pack(fill="both", expand=True, padx=0, pady=0)

        # --- Header ---
        header = _mk_frame(container, fg=root_bg, corner=0)
        header.pack(fill="x", padx=28, pady=(24, 10))

        brand = _mk_label(header, "RAGE / TRACKER", (DISP, 30, "bold"), CYAN, bg=root_bg)
        brand.pack(anchor="w")
        sub = _mk_label(header, "// Gaming Emotion Telemetry", (MONO, 11), TEXT3, bg=root_bg)
        sub.pack(anchor="w", pady=(2, 0))

        meta = _mk_label(header, "SYS v2.0   ·   ● LIVE", (MONO, 10), CYAN_DIM, bg=root_bg)
        meta.pack(anchor="w", pady=(6, 0))

        # --- Botones principales (tarjetas) ---
        cards = _mk_frame(container, fg=root_bg, corner=0)
        cards.pack(fill="x", padx=28, pady=(14, 8))

        self._card(cards, "🎮  INICIAR TRACKER",
                   "Medir tus emociones y/o gritos en partida",
                   self._open_session_config, accent=CYAN)
        self._card(cards, "📊  VER ESTADÍSTICAS",
                   "Abre el dashboard en tu navegador",
                   self._open_dashboard, accent=HAPPY)

        # --- Footer con stats ---
        sep = _mk_frame(container, fg=BORDER, corner=0)
        sep.pack(fill="x", padx=28, pady=(14, 10))
        try:
            sep.configure(height=1)
        except Exception:
            pass

        self.footer1 = _mk_label(container, "—", (MONO, 11), TEXT2, bg=root_bg)
        self.footer1.pack(anchor="w", padx=28)
        self.footer2 = _mk_label(container, "—", (MONO, 11), TEXT3, bg=root_bg)
        self.footer2.pack(anchor="w", padx=28, pady=(2, 18))

        self._refresh_footer()

    def _card(self, parent, title, subtitle, command, accent=CYAN):
        """Tarjeta-botón grande con título + subtítulo, hover y click."""
        card = _mk_frame(parent, fg=SURFACE, corner=14, border=1, border_color=BORDER)
        card.pack(fill="x", pady=8, ipady=4)

        title_lbl = _mk_label(card, title, (MONO, 17, "bold"), TEXT, bg=SURFACE)
        title_lbl.pack(anchor="w", padx=20, pady=(16, 2))
        sub_lbl = _mk_label(card, subtitle, (MONO, 11), TEXT3, bg=SURFACE)
        sub_lbl.pack(anchor="w", padx=20, pady=(0, 16))

        widgets = [card, title_lbl, sub_lbl]

        def on_click(_e=None):
            command()

        def on_enter(_e=None):
            _set_bg(card, SURFACE3)
            for w in (title_lbl, sub_lbl):
                _set_label_bg(w, SURFACE3)
            _set_border(card, accent)

        def on_leave(_e=None):
            _set_bg(card, SURFACE)
            for w in (title_lbl, sub_lbl):
                _set_label_bg(w, SURFACE)
            _set_border(card, BORDER)

        for w in widgets:
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
        return card

    def _refresh_footer(self):
        try:
            sessions = self.dm.get_all_sessions()
            games = self.dm.get_games()
            if sessions:
                last = sessions[-1]
                rage = float(last.get("angry_percentage", 0) or 0)
                self.footer1.configure(
                    text=f"Última sesión: {last.get('game', '?')} · "
                         f"{last.get('date', '')[5:16]} · {rage:.0f}% rage"
                )
            else:
                self.footer1.configure(text="Aún no hay sesiones registradas.")
            self.footer2.configure(
                text=f"Juegos registrados: {len(games)}  ·  Total sesiones: {len(sessions)}"
            )
        except Exception as exc:  # noqa: BLE001
            self.footer1.configure(text=f"(no se pudieron leer los datos: {exc})")

    # ------------------------------------------------------------------ #
    # Dashboard
    # ------------------------------------------------------------------ #
    def _open_dashboard(self):
        port = _ensure_dashboard_running(DASHBOARD_PORT)
        webbrowser.open(f"http://localhost:{port}/dashboard")

    # ------------------------------------------------------------------ #
    # Panel de configuración de sesión
    # ------------------------------------------------------------------ #
    def _open_session_config(self):
        if self._config_win is not None:
            try:
                self._config_win.lift()
                return
            except Exception:
                self._config_win = None

        win = _CTK.CTkToplevel(self.root) if _ctk() else _TK.Toplevel(self.root)
        win.title("Configurar sesión")
        win.configure(bg=BG)
        win.geometry("520x680")
        self._config_win = win

        def on_close():
            self._stop_preview()
            try:
                win.destroy()
            finally:
                self._config_win = None

        win.protocol("WM_DELETE_WINDOW", on_close)

        body = _mk_frame(win, fg=BG, corner=0)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        _mk_label(body, "CONFIGURAR SESIÓN", (DISP, 22, "bold"), CYAN, bg=BG).pack(anchor="w")
        _mk_label(body, "// elige juego y sensores antes de empezar",
                  (MONO, 10), TEXT3, bg=BG).pack(anchor="w", pady=(0, 14))

        # ---- A) Juego ----
        _section(body, "JUEGO")
        game_box = _mk_frame(body, fg=BG, corner=0)
        game_box.pack(fill="x", pady=(2, 12))
        games = self.dm.get_games()
        self.game_var = _str_var(games[0] if games else "")
        _mk_label(game_box, "Existente:", (MONO, 11), TEXT2, bg=BG).pack(anchor="w")
        _mk_optionmenu(game_box, self.game_var, games or ["(sin juegos)"]).pack(fill="x", pady=(2, 8))
        _mk_label(game_box, "...o añade uno nuevo (deja vacío para usar el de arriba):",
                  (MONO, 10), TEXT3, bg=BG).pack(anchor="w")
        self.new_game_var = _str_var("")
        _mk_entry(game_box, self.new_game_var, "Nuevo juego...").pack(fill="x", pady=(2, 0))

        # ---- B) Modo sensor ----
        _section(body, "MODO SENSOR")
        sens = _mk_frame(body, fg=SURFACE, corner=12, border=1, border_color=BORDER)
        sens.pack(fill="x", pady=(2, 12))
        self.emo_var = _bool_var(True)
        self.scream_var = _bool_var(audio_available())
        _mk_checkbox(sens, "😤  EMOCIONES   ·   detecta tu cara (cámara)",
                     self.emo_var).pack(anchor="w", padx=16, pady=(14, 6))
        _mk_checkbox(sens, "🔊  GRITOS      ·   detecta tu micrófono",
                     self.scream_var, command=self._toggle_mic_panel).pack(anchor="w", padx=16, pady=(0, 6))
        _mk_label(sens, "── puedes activar uno, otro, o ambos ──",
                  (MONO, 9), TEXT3, bg=SURFACE).pack(anchor="w", padx=16, pady=(0, 12))

        # ---- Sub-panel de micrófono (visible solo si GRITOS) ----
        self.mic_panel = _mk_frame(body, fg=SURFACE2, corner=12, border=1, border_color=BORDER)
        self._build_mic_panel(self.mic_panel)

        # ---- C) Botones ----
        actions = _mk_frame(body, fg=BG, corner=0)
        actions.pack(fill="x", side="bottom", pady=(10, 0))
        _mk_button(actions, "▶  INICIAR SENSOR", self._on_start_session,
                   height=46, font=(MONO, 14, "bold")).pack(fill="x")
        _mk_button(actions, "⚙  Recalibrar detección", self._on_recalibrate,
                   fg=SURFACE2, hover=SURFACE3, text_color=TEXT2,
                   height=34, font=(MONO, 11)).pack(fill="x", pady=(8, 0))

        self._toggle_mic_panel()  # estado inicial coherente

    def _build_mic_panel(self, parent):
        _mk_label(parent, "MICRÓFONO", (MONO, 11, "bold"), CYAN, bg=SURFACE2).pack(
            anchor="w", padx=16, pady=(12, 4))

        devices = AudioMonitor.list_input_devices() if AudioMonitor else []
        self._mic_map = {f"{i}: {name}": i for i, name in devices}
        labels = list(self._mic_map.keys()) or ["Sin micrófonos detectados"]
        self.mic_var = _str_var(labels[0])
        _mk_optionmenu(parent, self.mic_var, labels, command=self._on_mic_change).pack(
            fill="x", padx=16, pady=(0, 8))

        # Si no hay dispositivos, muestro el diagnóstico para que el usuario
        # sepa si es falta de backend o un problema de permisos/drivers.
        if not devices:
            diag = diagnose() if AudioMonitor else "Módulo de audio no disponible."
            _mk_label(parent, diag, (MONO, 9), WARN, bg=SURFACE2).pack(
                anchor="w", padx=16, pady=(0, 6))

        # Umbral
        self.thr_var = _double_var(80.0)
        self.thr_label = _mk_label(parent, "Umbral de grito: 80%", (MONO, 11), TEXT2, bg=SURFACE2)
        self.thr_label.pack(anchor="w", padx=16)
        _mk_slider(parent, 0, 100, self.thr_var, command=self._on_thr_change).pack(
            fill="x", padx=16, pady=(2, 10))

        # VU meter (canvas)
        _mk_label(parent, "Nivel en vivo (grita para calibrar):", (MONO, 10), TEXT3, bg=SURFACE2).pack(
            anchor="w", padx=16)
        self.vu_canvas = _mk_canvas(parent, 440, 26, bg=SURFACE)
        self.vu_canvas.pack(fill="x", padx=16, pady=(4, 10))

        # Botón de calibración dedicada (experiencia estilo juego de terror)
        _mk_button(parent, "🎤  Calibrar micrófono", self._open_mic_calibration,
                   fg=SURFACE3, hover=BORDER, text_color=CYAN,
                   height=30, font=(MONO, 10)).pack(fill="x", padx=16, pady=(0, 12))

    def _toggle_mic_panel(self):
        want = bool(self.scream_var.get())
        if want:
            self.mic_panel.pack(fill="x", pady=(0, 12), after=None)
            self._start_preview()
        else:
            self._stop_preview()
            try:
                self.mic_panel.pack_forget()
            except Exception:
                pass

    # ---- Previsualización del micrófono ----
    def _current_mic_index(self):
        return self._mic_map.get(self.mic_var.get())

    def _start_preview(self):
        self._stop_preview()
        if not (AudioMonitor and audio_available()):
            return
        idx = self._current_mic_index()
        try:
            self._preview = AudioMonitor(device_index=idx, threshold_pct=float(self.thr_var.get()))
            if self._preview.start():
                self._poll_vu()
            else:
                self._preview = None
        except Exception:
            self._preview = None

    def _poll_vu(self):
        if self._preview is None or self._config_win is None:
            return
        level = float(getattr(self._preview, "level", 0.0))
        peak = float(getattr(self._preview, "peak_level", 0.0))
        thr = float(self.thr_var.get())
        self._draw_vu(level, peak, thr)
        self._vu_after = self.root.after(50, self._poll_vu)

    def _draw_vu(self, level, peak, thr):
        c = self.vu_canvas
        try:
            c.delete("all")
            w = int(c.winfo_width())
            h = int(c.winfo_height())
        except Exception:
            return
        # Antes del primer layout, winfo_width() devuelve 1 (no 0), así que el
        # 'or 440' no saltaba y la barra quedaba de 1px. Compruebo <= 1.
        if w <= 1:
            w = 440
        if h <= 1:
            h = 26

        c.create_rectangle(0, 0, w, h, fill=SURFACE, outline=BORDER)
        fill = int(w * max(0.0, min(100.0, level)) / 100.0)
        color = RAGE if level >= 90 else (WARN if level >= 60 else HAPPY)
        if fill > 0:
            c.create_rectangle(0, 0, fill, h, fill=color, outline="")

        # Marcador de pico-hold (línea clara que cae despacio).
        px = int(w * max(0.0, min(100.0, peak)) / 100.0)
        c.create_line(px, 0, px, h, fill=TEXT, width=2)

        # Línea de umbral.
        tx = int(w * max(0.0, min(100.0, thr)) / 100.0)
        c.create_line(tx, 0, tx, h, fill=CYAN, width=2)

        # Número de nivel + contador de gritos en vivo.
        c.create_text(w - 6, h // 2, text=f"{int(level)}%",
                      fill=TEXT, font=(MONO, 11, "bold"), anchor="e")
        try:
            scount = self._preview.get_summary().get("scream_count", 0) if self._preview else 0
            screaming = bool(getattr(self._preview, "is_screaming", False))
        except Exception:
            scount, screaming = 0, False
        tag = f"⚡{scount}" if screaming else f"{scount}"
        c.create_text(6, h // 2, text=f"gritos {tag}",
                      fill=(RAGE if screaming else TEXT3), font=(MONO, 9), anchor="w")

    def _stop_preview(self):
        if self._vu_after is not None:
            try:
                self.root.after_cancel(self._vu_after)
            except Exception:
                pass
            self._vu_after = None
        if self._preview is not None:
            try:
                self._preview.stop()
            except Exception:
                pass
            self._preview = None

    def _on_mic_change(self, _value=None):
        if self.scream_var.get():
            self._start_preview()

    def _on_thr_change(self, _value=None):
        thr = int(float(self.thr_var.get()))
        try:
            self.thr_label.configure(text=f"Umbral de grito: {thr}%")
        except Exception:
            pass
        if self._preview is not None:
            self._preview.threshold_pct = float(thr)

    # ------------------------------------------------------------------ #
    # Calibración de micrófono (ventana dedicada, estilo juego de terror)
    # ------------------------------------------------------------------ #
    def _open_mic_calibration(self):
        """Abre la ventana de calibración de micrófono.

        Diseñé esto como una experiencia visual tipo juego de terror:
        una barra de volumen grande que se mueve en vivo, con una línea
        de umbral que el usuario arrastra según lo que ve. La idea es que
        hable normal, grite, y ajuste la línea hasta que solo se active
        cuando realmente grita — sin números fríos, puro feedback visual.
        """
        if not (AudioMonitor and audio_available()):
            self._warn("No hay micrófono disponible.\n"
                       "Instalá sounddevice: pip install sounddevice==0.4.7")
            return

        self._stop_preview()

        # Ventana de calibración
        parent = self._config_win or self.root
        win = _CTK.CTkToplevel(parent) if _ctk() else _TK.Toplevel(parent)
        win.title("Calibrar micrófono")
        win.configure(bg=BG)
        win.geometry("580x460")
        win.resizable(False, False)
        # La ventana de calibración es modal: bloquea la interacción con la
        # ventana padre hasta que el usuario termine de calibrar o cierre.
        win.transient(parent)
        win.grab_set()

        # ---- Estado ----
        idx = self._current_mic_index() if hasattr(self, '_mic_map') else None
        current_thr = self.thr_var.get() if hasattr(self, 'thr_var') else 80.0
        try:
            calib_monitor = AudioMonitor(device_index=idx, threshold_pct=float(current_thr))
            if not calib_monitor.start():
                self._warn("No se pudo abrir el micrófono para calibrar.")
                win.destroy()
                return
        except Exception as e:
            self._warn(f"Error al iniciar el micrófono: {e}")
            win.destroy()
            return

        calib_thr = float(current_thr)  # mutable, capturada por el closure
        calib_dragging = False

        def on_close():
            try:
                calib_monitor.stop()
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", on_close)

        # ---- UI ----
        body = _mk_frame(win, fg=BG, corner=0)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        _mk_label(body, "CALIBRACIÓN DE MICRÓFONO", (DISP, 22, "bold"), CYAN, bg=BG).pack(anchor="w")
        _mk_label(body, "// hablá, gritá, ajustá el umbral hasta que solo "
                  "se active cuando realmente grites",
                  (MONO, 10), TEXT3, bg=BG).pack(anchor="w", pady=(0, 18))

        # ---- Barra de volumen grande (canvas) ----
        _mk_label(body, "NIVEL DE VOZ EN VIVO", (MONO, 10, "bold"), TEXT2, bg=BG).pack(anchor="w")
        bar_h = 120
        bar_canvas = _mk_canvas(body, 520, bar_h, bg=SURFACE)
        bar_canvas.pack(fill="x", pady=(4, 6))

        # ---- Indicador de estado ----
        status_label = _mk_label(body, "●  Hablá normal para ver tu nivel base...",
                                 (MONO, 12), TEXT2, bg=BG)
        status_label.pack(anchor="w", pady=(0, 10))

        # ---- Controles de umbral (mini-barra + etiqueta) ----
        ctrl_frame = _mk_frame(body, fg=SURFACE, corner=10, border=1, border_color=BORDER)
        ctrl_frame.pack(fill="x", pady=(0, 10))

        thr_label = _mk_label(ctrl_frame, f"Umbral de grito: {int(calib_thr)}%",
                              (MONO, 13, "bold"), CYAN, bg=SURFACE)
        thr_label.pack(anchor="w", padx=16, pady=(12, 2))

        hint_label = _mk_label(ctrl_frame,
                               "← más sensible (susurro activa)       "
                               "menos sensible (solo grito) →",
                               (MONO, 9), TEXT3, bg=SURFACE)
        hint_label.pack(anchor="w", padx=16, pady=(0, 0))

        thr_var_local = _double_var(calib_thr)
        thr_slider = _mk_slider(ctrl_frame, 0, 100, thr_var_local)
        thr_slider.pack(fill="x", padx=16, pady=(4, 12))

        def _on_thr_slider(val):
            nonlocal calib_thr
            calib_thr = float(val)
            thr_label.configure(text=f"Umbral de grito: {int(calib_thr)}%")
            calib_monitor.threshold_pct = calib_thr

        # Conecto el slider. En CTk, el command recibe el valor como float.
        # En tk estándar, el command de Scale recibe un string.
        try:
            if _ctk():
                thr_slider.configure(command=_on_thr_slider)
            else:
                thr_slider.configure(command=lambda v: _on_thr_slider(float(v)))
        except Exception:
            pass

        # ---- Botones ----
        btn_frame = _mk_frame(body, fg=BG, corner=0)
        btn_frame.pack(fill="x", pady=(8, 0))

        def _on_save():
            nonlocal calib_thr
            self.thr_var.set(calib_thr)
            self._on_thr_change()
            on_close()

        _mk_button(btn_frame, "💾  GUARDAR UMBRAL", _on_save,
                   height=42, font=(MONO, 13, "bold")).pack(side="right", padx=(6, 0))
        _mk_button(btn_frame, "🔄  Reiniciar contadores", calib_monitor.reset,
                   fg=SURFACE2, hover=SURFACE3, text_color=TEXT2,
                   height=34, font=(MONO, 11)).pack(side="left")

        # ---- Loop de refresco del canvas ----
        def _redraw():
            if not win.winfo_exists():
                return
            try:
                level = float(getattr(calib_monitor, "level", 0.0))
                screaming = bool(getattr(calib_monitor, "is_screaming", False))
                summary = calib_monitor.get_summary()
                scream_count = int(summary.get("scream_count", 0))
            except Exception:
                win.after(60, _redraw)
                return

            c = bar_canvas
            try:
                c.delete("all")
                w = int(c.winfo_width())
                h = int(c.winfo_height())
            except Exception:
                win.after(60, _redraw)
                return
            if w <= 1:
                w = 520
            if h <= 1:
                h = bar_h

            # Fondo con zonas de color (verde → ámbar → rojo)
            green_w = int(w * 0.50)
            yellow_w = int(w * 0.30)
            red_w = w - green_w - yellow_w
            c.create_rectangle(0, 0, green_w, h, fill="#1a3a1a", outline="")
            c.create_rectangle(green_w, 0, green_w + yellow_w, h, fill="#3a2a0a", outline="")
            c.create_rectangle(green_w + yellow_w, 0, w, h, fill="#3a0a0a", outline="")

            # Relleno del nivel actual
            fill = int(w * max(0.0, min(100.0, level)) / 100.0)
            if level >= 90:
                fill_color = RAGE
            elif level >= 60:
                fill_color = WARN
            else:
                fill_color = HAPPY
            if fill > 0:
                c.create_rectangle(0, 0, fill, h, fill=fill_color, outline="", stipple="")

            # Efecto de "barra que respira" con gradiente vertical
            for i in range(0, fill, 4):
                alpha = 0.15 + 0.05 * (i % 12) / 12
                c.create_rectangle(i, 0, i + 3, h,
                                   fill=fill_color, outline="", stipple="")

            # Línea del umbral
            tx = int(w * max(0.0, min(100.0, calib_thr)) / 100.0)
            c.create_line(tx, 0, tx, h, fill=CYAN, width=3)
            # Triángulo indicador arriba
            c.create_polygon(tx - 8, 0, tx + 8, 0, tx, 12,
                             fill=CYAN, outline=CYAN)

            # Porcentaje actual
            c.create_text(w - 44, 18, text=f"{int(level)}%",
                          fill=TEXT, font=(MONO, 16, "bold"), anchor="ne")

            # Etiqueta de umbral
            c.create_text(tx, h - 14, text=f"umbral {int(calib_thr)}%",
                          fill=CYAN, font=(MONO, 9), anchor="s")

            # Estado (gritando / normal)
            if screaming:
                status_label.configure(
                    text=f"⚡  ¡GRITANDO!  ({scream_count} gritos detectados)"
                )
                status_label.configure(text_color=RAGE)
            elif level > 2:
                status_label.configure(
                    text=f"●  Nivel actual: {int(level)}%  —  "
                         f"{'por encima' if level >= calib_thr else 'por debajo'} del umbral"
                )
                status_label.configure(text_color=TEXT2)
            else:
                status_label.configure(text="●  Silencio... hablá o gritá para calibrar")
                status_label.configure(text_color=TEXT3)

            win.after(60, _redraw)

        _redraw()
    def _resolve_game(self):
        new = (self.new_game_var.get() or "").strip()
        if new:
            self.dm.add_game(new)  # idempotente: si existe, no duplica
            return new
        return (self.game_var.get() or "").strip()

    def _on_start_session(self):
        sensors = []
        if self.emo_var.get():
            sensors.append("emotions")
        if self.scream_var.get():
            sensors.append("scream")
        if not sensors:
            self._warn("Selecciona al menos un sensor (emociones o gritos).")
            return

        game = self._resolve_game()
        if not game or game == "(sin juegos)":
            self._warn("Indica un juego (elige uno o escribe uno nuevo).")
            return

        mic_index = self._current_mic_index() if "scream" in sensors else None
        threshold = int(float(self.thr_var.get()))

        # Libero el micrófono de previsualización antes de lanzar la sesión real
        # para que no haya conflicto de dispositivos.
        self._stop_preview()

        cmd = [sys.executable, str(MAIN_PY), "--session", "--game", game,
               "--sensors", *sensors, "--threshold", str(threshold)]
        if mic_index is not None:
            cmd += ["--mic", str(mic_index)]

        # Cierro el panel y oculto la ventana principal mientras corre la sesión.
        # Así el usuario no ve dos ventanas y la experiencia es más limpia.
        try:
            if self._config_win is not None:
                self._config_win.destroy()
                self._config_win = None
        except Exception:
            pass
        self.root.withdraw()
        self._run_subprocess(cmd)

    def _on_recalibrate(self):
        self._stop_preview()
        cmd = [sys.executable, str(MAIN_PY), "--calibrate"]
        try:
            if self._config_win is not None:
                self._config_win.destroy()
                self._config_win = None
        except Exception:
            pass
        self.root.withdraw()
        self._run_subprocess(cmd)

    def _run_subprocess(self, cmd):
        def worker():
            try:
                subprocess.run(cmd, cwd=str(ROOT))
            except Exception as exc:  # noqa: BLE001
                print(f"[!] Error ejecutando la sesión: {exc}")
            finally:
                # Vuelvo a mostrar la GUI en el hilo principal de Tk
                self.root.after(0, self._after_session)

        threading.Thread(target=worker, daemon=True).start()

    def _after_session(self):
        try:
            self.root.deiconify()
            self.root.lift()
        except Exception:
            pass
        self._refresh_footer()

    # ------------------------------------------------------------------ #
    def _warn(self, message):
        try:
            from tkinter import messagebox
            messagebox.showwarning("Rage Tracker", message, parent=self._config_win or self.root)
        except Exception:
            print(f"[!] {message}")

    def run(self):
        self.root.mainloop()


# ---- Helpers de color que funcionan en ambos backends -----------------------
def _set_bg(widget, color):
    try:
        if _ctk():
            widget.configure(fg_color=color)
        else:
            widget.configure(bg=color)
    except Exception:
        pass


def _set_label_bg(widget, color):
    try:
        if _ctk():
            widget.configure(fg_color="transparent")
        else:
            widget.configure(bg=color)
    except Exception:
        pass


def _set_border(widget, color):
    try:
        if _ctk():
            widget.configure(border_color=color)
        else:
            widget.configure(highlightbackground=color, highlightcolor=color)
    except Exception:
        pass


def _section(parent, title):
    lbl = _mk_label(parent, f"// {title}", (MONO, 11, "bold"), TEXT3, bg=BG)
    lbl.pack(anchor="w", pady=(8, 0))
    return lbl


# =============================================================================
# Punto de entrada
# =============================================================================
def launch() -> int:
    """Arranca la GUI. Devuelve un código de salida estilo `int main()`."""
    if not GUI_AVAILABLE:
        print(
            "[!] No hay ninguna librería de GUI disponible.\n"
            "   Instala CustomTkinter:  pip install customtkinter\n"
            "   (o asegúrate de que tu Python incluye tkinter)\n"
            "   Mientras tanto puedes usar el modo terminal:  python main.py --cli"
        )
        return 1
    app = RageTrackerApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(launch())
