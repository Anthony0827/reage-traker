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

from src.paths import app_launch_cmd, is_frozen, user_data_dir

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
    # CTkCanvas no existe en CustomTkinter; siempre usamos tk.Canvas directamente
    return _TK.Canvas(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0)


def _mk_scrollable(parent, fg=BG):
    """Devuelve (contenedor, interior): mete los widgets en `interior` y empaqueta
    `contenedor`. El contenido hace scroll vertical si no cabe en la ventana.

    Con CustomTkinter uso CTkScrollableFrame. En tkinter estándar monto un
    Canvas + Scrollbar a mano (con rueda del ratón) para lograr el mismo efecto.
    Esto evita que las ventanas con mucho contenido (p. ej. sesión con los tres
    sensores) recorten botones en pantallas pequeñas."""
    if _ctk():
        # border_width=0 + scrollbar transparente: sin el recuadro/franja que
        # antes se veía como "bordes raros" alrededor del contenido.
        sf = _CTK.CTkScrollableFrame(parent, fg_color=fg, corner_radius=0,
                                     border_width=0, scrollbar_fg_color="transparent")
        return sf, sf

    outer = _TK.Frame(parent, bg=fg, bd=0, highlightthickness=0)
    canvas = _TK.Canvas(outer, bg=fg, bd=0, highlightthickness=0)
    vsb = _TK.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = _TK.Frame(canvas, bg=fg, bd=0, highlightthickness=0)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>",
                lambda e: canvas.itemconfigure(win_id, width=e.width))
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    def _wheel(e):
        canvas.yview_scroll(int(-e.delta / 120), "units")

    inner.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
    inner.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
    return outer, inner


def _str_var(value=""):
    return _TK.StringVar(value=value)


def _bool_var(value=False):
    return _TK.BooleanVar(value=value)


def _double_var(value=0.0):
    return _TK.DoubleVar(value=value)


def _place(win, w, h, min_w=None, min_h=None, top_ratio=0.45):
    """Dimensiona y centra una ventana ajustándola a la pantalla visible.

    En monitores con escala de Windows alta (125-150%) CustomTkinter agranda
    las ventanas según el DPI y pueden salirse de la pantalla, dejando botones
    recortados (típico en monitores grandes de escritorio). Aquí limitamos el
    tamaño a un 96% del ancho y un 90% del alto reales y centramos la ventana,
    de modo que nunca quede nada fuera; el contenido que no entre se ve con
    scroll. Funciona igual con tkinter estándar (escala 1.0)."""
    try:
        win.update_idletasks()
    except Exception:
        pass
    try:
        sw = int(win.winfo_screenwidth())
        sh = int(win.winfo_screenheight())
    except Exception:
        sw, sh = 1920, 1080

    # Factor de escala DPI que aplica CustomTkinter al tamaño (no a la posición).
    scale = 1.0
    if _ctk():
        try:
            scale = float(_CTK.ScalingTracker.get_window_scaling(win))
        except Exception:
            scale = 1.0
    if scale <= 0:
        scale = 1.0

    # geometry() recibe unidades SIN escalar (CTk las multiplica por `scale`),
    # así que convertimos el máximo en px físicos a esas unidades.
    max_w = (sw * 0.96) / scale
    max_h = (sh * 0.90) / scale
    w = int(min(w, max_w))
    h = int(min(h, max_h))

    # La posición x/y va en px físicos (CTk no la escala).
    x = max(0, int((sw - w * scale) / 2))
    y = max(0, int((sh - h * scale) * top_ratio))
    try:
        win.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass

    if min_w or min_h:
        try:
            win.minsize(min(int(min_w or w), w), min(int(min_h or h), h))
        except Exception:
            pass


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
            from src.paths import resource_path
            spec = importlib.util.spec_from_file_location(
                "rt_dashboard_server", resource_path("web", "dashboard_server.py")
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
        _place(self.root, 720, 560, min_w=560, min_h=480)

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
        # El contenido va en un área scrollable, así que un alto moderado basta:
        # si con los tres sensores no entra todo, el usuario hace scroll en vez
        # de encontrarse botones recortados.
        _place(win, 520, 700, min_w=460, min_h=420)
        self._config_win = win

        def on_close():
            self._stop_preview()
            try:
                win.destroy()
            finally:
                self._config_win = None

        win.protocol("WM_DELETE_WINDOW", on_close)

        # Barra de acciones FIJA abajo: siempre visible, fuera del scroll, para
        # que INICIAR nunca quede recortado por mucho contenido que haya arriba.
        actions = _mk_frame(win, fg=BG, corner=0)
        actions.pack(fill="x", side="bottom", padx=22, pady=(8, 16))
        _mk_button(actions, "▶  INICIAR RAGE TRACKER", self._on_start_session,
                   height=46, font=(MONO, 14, "bold")).pack(fill="x")
        _mk_button(actions, "⚙  Recalibrar detección", self._on_recalibrate,
                   fg=SURFACE2, hover=SURFACE3, text_color=TEXT2,
                   height=34, font=(MONO, 11)).pack(fill="x", pady=(8, 0))

        # Contenido scrollable (todo lo demás).
        scroll, body = _mk_scrollable(win, fg=BG)
        scroll.pack(fill="both", expand=True, padx=22, pady=(18, 0))

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
        self.insult_var = _bool_var(False)
        _mk_checkbox(sens, "😤  EMOCIONES   ·   detecta tu cara (cámara)",
                     self.emo_var, command=self._toggle_calib_button).pack(anchor="w", padx=16, pady=(14, 6))
        _mk_checkbox(sens, "🔊  GRITOS      ·   detecta tu micrófono",
                     self.scream_var, command=self._toggle_mic_button).pack(anchor="w", padx=16, pady=(0, 6))
        _mk_checkbox(sens, "🎯  INSULTOS (beta) ·   detecta lenguaje ofensivo",
                     self.insult_var, command=self._toggle_insult_button).pack(anchor="w", padx=16, pady=(0, 6))
        _mk_label(sens, "── puedes activar uno, otro, o ambos ──",
                  (MONO, 9), TEXT3, bg=SURFACE).pack(anchor="w", padx=16, pady=(0, 12))

        # ---- Botón de configuración de micrófono (visible solo si GRITOS) ----
        self.thr_var = _double_var(80.0)
        self.sens_var = _double_var(1.0)
        self._mic_map: dict = {}
        self.mic_var = _str_var("")

        self.mic_btn_frame = _mk_frame(body, fg=BG, corner=0)
        _mk_button(self.mic_btn_frame, "🎤  CONFIGURAR MICRÓFONO",
                   self._open_mic_config, fg=SURFACE2, hover=SURFACE3, text_color=CYAN,
                   height=42, font=(MONO, 13, "bold")).pack(fill="x")

        # ---- Botón de calibración de emociones (si EMOCIONES activado) ----
        self.calib_btn_frame = _mk_frame(body, fg=BG, corner=0)
        _mk_button(self.calib_btn_frame, "🎭  CONFIGURAR CARA",
                   self._open_calibration, fg=SURFACE2, hover=SURFACE3, text_color=CYAN,
                   height=42, font=(MONO, 13, "bold")).pack(fill="x")

        # ---- Botón de configuración de insultos (visible solo si INSULTOS) ----
        self.insult_btn_frame = _mk_frame(body, fg=BG, corner=0)
        _mk_button(self.insult_btn_frame, "🎯  CONFIGURAR INSULTOS",
                   self._open_insult_config, fg=SURFACE2, hover=SURFACE3, text_color=CYAN,
                   height=42, font=(MONO, 13, "bold")).pack(fill="x")

        self._toggle_mic_button()  # estado inicial coherente
        self._toggle_calib_button()  # estado inicial coherente
        self._toggle_insult_button()  # estado inicial coherente

    def _toggle_mic_button(self):
        want = bool(self.scream_var.get())
        if want:
            self.mic_btn_frame.pack(fill="x", pady=(0, 12), after=None)
        else:
            try:
                self.mic_btn_frame.pack_forget()
            except Exception:
                pass

    def _toggle_calib_button(self):
        want = bool(self.emo_var.get())
        if want:
            self.calib_btn_frame.pack(fill="x", pady=(0, 12), after=None)
        else:
            try:
                self.calib_btn_frame.pack_forget()
            except Exception:
                pass

    def _toggle_insult_button(self):
        """Muestra/oculta botón de configuración de insultos (similar a _toggle_mic_button)."""
        want = bool(self.insult_var.get())
        if want:
            self.insult_btn_frame.pack(fill="x", pady=(0, 12), after=None)
        else:
            try:
                self.insult_btn_frame.pack_forget()
            except Exception:
                pass

    def _current_mic_index(self):
        return self._mic_map.get(self.mic_var.get())

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

    # ------------------------------------------------------------------ #
    # Ventana de configuración de micrófono (VU en vivo + ajustes)
    # ------------------------------------------------------------------ #
    def _open_mic_config(self):
        """Ventana dedicada: selector de micro, barra VU grande, umbral y sensibilidad.

        A diferencia del panel embebido que había antes, esta ventana es amplia,
        tiene bordes bien definidos, y la barra de volumen es de 100 px de alto
        para que se vea clara aunque estés a un metro de la pantalla."""
        self._stop_preview()

        parent = self._config_win or self.root
        win = _CTK.CTkToplevel(parent) if _ctk() else _TK.Toplevel(parent)
        win.title("Configurar micrófono")
        win.configure(bg=BG)
        _place(win, 560, 700, min_w=460, min_h=420)
        win.resizable(True, True)
        win.transient(parent)
        win.grab_set()

        # Poblar el mapa de dispositivos (perezoso, se actualiza cada vez que
        # se abre la ventana por si el usuario conectó un micro nuevo).
        devices = AudioMonitor.list_input_devices() if AudioMonitor else []
        self._mic_map = {f"{i}: {name}": i for i, name in devices}
        labels = list(self._mic_map.keys()) or ["Sin micrófonos detectados"]
        if not self.mic_var.get() or self.mic_var.get() not in labels:
            self.mic_var.set(labels[0])

        # Monitor local para la previsualización en vivo.
        mic_monitor = None
        vu_after = None

        def _start():
            nonlocal mic_monitor
            if not (AudioMonitor and audio_available()):
                status_label.configure(text="⚠  Sin backend de audio. Instalá sounddevice.")
                _set_label_fg(status_label, WARN)
                return
            idx = self._mic_map.get(mic_var_local.get())
            try:
                mic_monitor = AudioMonitor(
                    device_index=idx,
                    threshold_pct=float(thr_var_local.get()),
                    sensitivity=float(sens_var_local.get()),
                )
                if not mic_monitor.start():
                    why = getattr(mic_monitor, "last_error", "") or "motivo desconocido"
                    status_label.configure(text=f"⚠  No se pudo abrir: {why}")
                    _set_label_fg(status_label, WARN)
                    mic_monitor = None
            except Exception as e:
                status_label.configure(text=f"⚠  Error: {e}")
                _set_label_fg(status_label, WARN)
                mic_monitor = None

        def _stop():
            nonlocal mic_monitor, vu_after
            if vu_after is not None:
                try:
                    win.after_cancel(vu_after)
                except Exception:
                    pass
                vu_after = None
            if mic_monitor is not None:
                try:
                    mic_monitor.stop()
                except Exception:
                    pass
                mic_monitor = None

        def on_close():
            _stop()
            try:
                win.destroy()
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", on_close)

        # ---- UI ----
        # Barra inferior FIJA (fuera del scroll): el botón GUARDAR siempre queda
        # visible aunque el contenido no entre en la pantalla. _save/_stop/
        # on_close se resuelven al hacer clic, por eso pueden referenciarse aquí
        # aunque _save se defina más abajo.
        actions = _mk_frame(win, fg=BG, corner=0)
        actions.pack(fill="x", side="bottom", padx=22, pady=(8, 16))
        _mk_button(actions, "💾  GUARDAR Y CERRAR", lambda: (_save(), on_close()),
                   height=44, font=(MONO, 13, "bold")).pack(fill="x")
        _mk_button(actions, "🎤  Calibrar con grito real",
                   lambda: (_save(), _stop(), on_close(), self._open_mic_calibration()),
                   fg=SURFACE2, hover=SURFACE3, text_color=CYAN,
                   height=34, font=(MONO, 11)).pack(fill="x", pady=(8, 0))

        # Contenido scrollable (todo lo demás).
        scroll, body = _mk_scrollable(win, fg=BG)
        scroll.pack(fill="both", expand=True, padx=22, pady=(18, 0))

        _mk_label(body, "CONFIGURAR MICRÓFONO", (DISP, 22, "bold"), CYAN, bg=BG).pack(anchor="w")
        _mk_label(body, "// seleccioná el micro, ajustá umbral y sensibilidad",
                  (MONO, 10), TEXT3, bg=BG).pack(anchor="w", pady=(0, 16))

        # ---- Dispositivo ----
        dev_frame = _mk_frame(body, fg=SURFACE, corner=10, border=1, border_color=BORDER)
        dev_frame.pack(fill="x", pady=(0, 12))
        _mk_label(dev_frame, "DISPOSITIVO", (MONO, 10, "bold"), TEXT2, bg=SURFACE).pack(
            anchor="w", padx=16, pady=(12, 4))
        mic_var_local = _str_var(self.mic_var.get())
        _mk_optionmenu(dev_frame, mic_var_local, labels, command=lambda v: _restart()).pack(
            fill="x", padx=16, pady=(0, 4))

        if not devices:
            diag = diagnose() if AudioMonitor else "Módulo de audio no disponible."
            _mk_label(dev_frame, diag, (MONO, 9), WARN, bg=SURFACE).pack(
                anchor="w", padx=16, pady=(0, 10))

        # Indicador de estado del micro
        status_label = _mk_label(dev_frame, "●  Micrófono listo", (MONO, 11), TEXT2, bg=SURFACE)
        status_label.pack(anchor="w", padx=16, pady=(0, 12))

        # ---- VU meter (grande) ----
        vu_frame = _mk_frame(body, fg=SURFACE, corner=10, border=2, border_color=CYAN_DIM)
        vu_frame.pack(fill="x", pady=(0, 12))
        _mk_label(vu_frame, "NIVEL EN VIVO", (MONO, 10, "bold"), TEXT2, bg=SURFACE).pack(
            anchor="w", padx=16, pady=(12, 4))
        BAR_H = 100
        bar_canvas = _mk_canvas(vu_frame, 480, BAR_H, bg=SURFACE2)
        bar_canvas.pack(fill="x", padx=16, pady=(4, 4))

        # ---- Drag del umbral directamente sobre la barra VU ----
        _thr_dragging = [False]  # mutable para el closure

        def _on_thr_click(e):
            w = int(bar_canvas.winfo_width()) or 480
            tx = int(w * float(thr_var_local.get()) / 100.0)
            if abs(e.x - tx) < 18:  # zona de agarre de ±18px alrededor de la línea
                _thr_dragging[0] = True

        def _on_thr_drag(e):
            if not _thr_dragging[0]:
                return
            w = int(bar_canvas.winfo_width()) or 480
            if w <= 1:
                w = 480
            pct = max(0.0, min(100.0, e.x / w * 100.0))
            thr_var_local.set(pct)
            _on_thr(pct)

        def _on_thr_release(e):
            _thr_dragging[0] = False

        bar_canvas.bind("<Button-1>", _on_thr_click, add="+")
        bar_canvas.bind("<B1-Motion>", _on_thr_drag, add="+")
        bar_canvas.bind("<ButtonRelease-1>", _on_thr_release, add="+")

        _mk_label(vu_frame, "↕  arrastrá la línea cyan para ajustar el umbral",
                  (MONO, 9), TEXT3, bg=SURFACE).pack(anchor="w", padx=16, pady=(0, 10))

        # ---- Callbacks de sliders (definidos antes de los sliders) ----
        def _on_thr(val):
            v = float(val)
            thr_val_label.configure(
                text=f"{int(v)}% — cuanto más alto, más fuerte hay que gritar")
            if mic_monitor is not None:
                mic_monitor.threshold_pct = v

        def _on_sens(val):
            v = float(val)
            sens_val_label.configure(
                text=f"{v:.1f}x — subilo si tu micro es flojo y la barra no se mueve")
            if mic_monitor is not None:
                mic_monitor.sensitivity = v

        # ---- Umbral ----
        thr_frame = _mk_frame(body, fg=SURFACE, corner=10, border=1, border_color=BORDER)
        thr_frame.pack(fill="x", pady=(0, 12))
        thr_label = _mk_label(thr_frame, "UMBRAL DE GRITO", (MONO, 10, "bold"), TEXT2, bg=SURFACE)
        thr_label.pack(anchor="w", padx=16, pady=(12, 4))
        thr_var_local = _double_var(self.thr_var.get())
        thr_slider = _mk_slider(thr_frame, 0, 100, thr_var_local, command=_on_thr)
        thr_slider.pack(fill="x", padx=16, pady=(4, 4))
        thr_val_label = _mk_label(thr_frame, f"{int(thr_var_local.get())}% — "
                                  "cuanto más alto, más fuerte hay que gritar",
                                  (MONO, 10), CYAN, bg=SURFACE)
        thr_val_label.pack(anchor="w", padx=16, pady=(0, 12))

        # ---- Sensibilidad ----
        sens_frame = _mk_frame(body, fg=SURFACE, corner=10, border=1, border_color=BORDER)
        sens_frame.pack(fill="x", pady=(0, 12))
        sens_label = _mk_label(sens_frame, "SENSIBILIDAD (ganancia)", (MONO, 10, "bold"), TEXT2, bg=SURFACE)
        sens_label.pack(anchor="w", padx=16, pady=(12, 4))
        sens_var_local = _double_var(self.sens_var.get())
        sens_slider = _mk_slider(sens_frame, 0.5, 5.0, sens_var_local, command=_on_sens)
        sens_slider.pack(fill="x", padx=16, pady=(4, 4))
        sens_val_label = _mk_label(sens_frame, f"{sens_var_local.get():.1f}x — "
                                   "subilo si tu micro es flojo y la barra no se mueve",
                                   (MONO, 10), CYAN, bg=SURFACE)
        sens_val_label.pack(anchor="w", padx=16, pady=(0, 12))

        # (Los botones GUARDAR / Calibrar viven en la barra inferior fija `actions`,
        #  creada arriba, para que nunca queden recortados.)

        def _save():
            self.mic_var.set(mic_var_local.get())
            self.thr_var.set(thr_var_local.get())
            self.sens_var.set(sens_var_local.get())

        def _restart():
            _stop()
            self.mic_var.set(mic_var_local.get())
            # Reconstruyo el mapa por si cambió el dispositivo
            nonlocal labels
            devices = AudioMonitor.list_input_devices() if AudioMonitor else []
            self._mic_map = {f"{i}: {name}": i for i, name in devices}
            labels = list(self._mic_map.keys()) or ["Sin micrófonos detectados"]
            # Solo reseteo si el dispositivo actual ya no está en la lista (ej: se desconectó)
            if mic_var_local.get() not in labels:
                mic_var_local.set(labels[0] if labels else "")
            _start()
            _poll()

        # ---- Loop de refresco de la barra VU ----
        def _poll():
            nonlocal vu_after
            if not win.winfo_exists():
                return
            if mic_monitor is None:
                vu_after = win.after(60, _poll)
                return
            try:
                level = float(getattr(mic_monitor, "level", 0.0))
                peak = float(getattr(mic_monitor, "peak_level", 0.0))
                thr = float(thr_var_local.get())
                screaming = bool(getattr(mic_monitor, "is_screaming", False))
                summary = mic_monitor.get_summary()
                scount = int(summary.get("scream_count", 0))
            except Exception:
                vu_after = win.after(60, _poll)
                return

            c = bar_canvas
            try:
                c.delete("all")
                w = int(c.winfo_width())
                h = int(c.winfo_height())
            except Exception:
                vu_after = win.after(60, _poll)
                return
            if w <= 1:
                w = 480
            if h <= 1:
                h = BAR_H

            # Zonas de color de fondo (verde → ámbar → rojo)
            green_w = int(w * 0.50)
            yellow_w = int(w * 0.30)
            red_w = w - green_w - yellow_w
            c.create_rectangle(0, 0, green_w, h, fill="#1a3a1a", outline="")
            c.create_rectangle(green_w, 0, green_w + yellow_w, h, fill="#3a2a0a", outline="")
            c.create_rectangle(green_w + yellow_w, 0, w, h, fill="#3a0a0a", outline="")

            # Relleno del nivel
            fill_w = int(w * max(0.0, min(100.0, level)) / 100.0)
            if level >= 90:
                fill_color = RAGE
            elif level >= 60:
                fill_color = WARN
            else:
                fill_color = HAPPY
            if fill_w > 0:
                c.create_rectangle(0, 0, fill_w, h, fill=fill_color, outline="")

            # Marcador de pico (línea blanca que cae despacio)
            px = int(w * max(0.0, min(100.0, peak)) / 100.0)
            c.create_line(px, 0, px, h, fill=TEXT, width=2)

            # Línea del umbral (arrastrable — click y mové)
            tx = int(w * max(0.0, min(100.0, thr)) / 100.0)
            c.create_line(tx, 0, tx, h, fill=CYAN, width=3)
            c.create_polygon(tx - 10, 0, tx + 10, 0, tx, 14, fill=CYAN, outline=CYAN)

            # Textos
            c.create_text(w - 44, 18, text=f"{int(level)}%",
                          fill=TEXT, font=(MONO, 16, "bold"), anchor="ne")
            c.create_text(tx, h - 14, text=f"umbral {int(thr)}%",
                          fill=CYAN, font=(MONO, 9), anchor="s")

            # Contador de gritos
            if screaming:
                tag = f"⚡ {scount} gritos"
                tag_color = RAGE
            else:
                tag = f"{scount} gritos"
                tag_color = TEXT3
            c.create_text(44, 18, text=tag, fill=tag_color, font=(MONO, 10), anchor="nw")

            # Borde exterior
            c.create_rectangle(0, 0, w - 1, h - 1, outline=BORDER)

            # Estado
            if screaming:
                status_label.configure(text=f"⚡  ¡GRITANDO!  ({scount} gritos)")
                _set_label_fg(status_label, RAGE)
            elif level > 2:
                status_label.configure(text=f"●  Nivel: {int(level)}%  —  "
                                         f"{'por encima' if level >= thr else 'por debajo'} del umbral")
                _set_label_fg(status_label, TEXT2)
            else:
                status_label.configure(text="●  Silencio... hablá para ver la barra")
                _set_label_fg(status_label, TEXT3)

            vu_after = win.after(50, _poll)

        _start()
        _poll()

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
        _place(win, 580, 480, min_w=460, min_h=380)
        win.resizable(True, True)
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
        # Contador de CRUCES del umbral (flanco de subida) solo para el test:
        # da feedback inmediato de que el slider funciona, sin esperar a los
        # 0.3 s sostenidos que exige el contador de "gritos" de la sesión real.
        calib_cross_count = 0
        calib_was_above = False

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

        # ---- Callback del slider (definido antes del slider) ----
        def _on_thr_slider(val):
            nonlocal calib_thr
            calib_thr = float(val)
            thr_label.configure(text=f"Umbral de grito: {int(calib_thr)}%")
            calib_monitor.threshold_pct = calib_thr

        thr_var_local = _double_var(calib_thr)
        thr_slider = _mk_slider(ctrl_frame, 0, 100, thr_var_local, command=_on_thr_slider)
        thr_slider.pack(fill="x", padx=16, pady=(4, 12))

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
        def _reset_calib_counters():
            nonlocal calib_cross_count, calib_was_above
            calib_cross_count = 0
            calib_was_above = False
            try:
                calib_monitor.reset()
            except Exception:
                pass

        _mk_button(btn_frame, "🔄  Reiniciar contadores", _reset_calib_counters,
                   fg=SURFACE2, hover=SURFACE3, text_color=TEXT2,
                   height=34, font=(MONO, 11)).pack(side="left")

        # ---- Loop de refresco del canvas ----
        def _redraw():
            nonlocal calib_cross_count, calib_was_above
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

            # Cuenta una "superación" cada vez que el nivel cruza el umbral de
            # abajo a arriba (flanco de subida). Feedback inmediato del slider.
            above_now = level >= calib_thr and level > 2
            if above_now and not calib_was_above:
                calib_cross_count += 1
            calib_was_above = above_now

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

            # Estado (gritando / normal). Mostramos SIEMPRE las veces que se
            # cruzó el umbral, para que se vea que el slider responde aunque no
            # se sostenga el grito el tiempo suficiente para contar como "grito".
            if screaming:
                status_label.configure(
                    text=f"⚡  ¡GRITANDO!  —  cruces de umbral: {calib_cross_count}"
                )
                _set_label_fg(status_label, RAGE)
            elif level > 2:
                pos = "por encima" if level >= calib_thr else "por debajo"
                status_label.configure(
                    text=f"●  Nivel: {int(level)}%  ({pos} del umbral)  —  "
                         f"cruces: {calib_cross_count}"
                )
                _set_label_fg(status_label, RAGE if level >= calib_thr else TEXT2)
            else:
                status_label.configure(
                    text=f"●  Silencio... hablá o gritá  —  cruces: {calib_cross_count}"
                )
                _set_label_fg(status_label, TEXT3)

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
        if self.insult_var.get():
            sensors.append("insults")
        if not sensors:
            self._warn("Selecciona al menos un sensor (emociones, gritos o insultos).")
            return

        game = self._resolve_game()
        if not game or game == "(sin juegos)":
            self._warn("Indica un juego (elige uno o escribe uno nuevo).")
            return

        # El micro hace falta tanto para gritos como para insultos: ambos
        # sensores capturan audio y deben usar el dispositivo que el usuario eligió.
        needs_mic = ("scream" in sensors) or ("insults" in sensors)
        mic_index = self._current_mic_index() if needs_mic else None
        threshold = int(float(self.thr_var.get()))
        sensitivity = float(self.sens_var.get())

        # Libero el micrófono de previsualización antes de lanzar la sesión real
        # para que no haya conflicto de dispositivos.
        self._stop_preview()

        cmd = app_launch_cmd("--session", "--game", game,
                             "--sensors", *sensors, "--threshold", str(threshold),
                             "--sensitivity", str(sensitivity))
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
        cmd = app_launch_cmd("--calibrate")
        try:
            if self._config_win is not None:
                self._config_win.destroy()
                self._config_win = None
        except Exception:
            pass
        self.root.withdraw()
        self._run_subprocess(cmd)

    def _open_calibration(self):
        """Calibración de cara: misma ruta que el botón Recalibrar."""
        self._on_recalibrate()

    def _on_thr_change(self):
        """Actualiza cualquier UI que muestre el umbral (no-op: el valor ya está en self.thr_var)."""
        pass

    def _open_insult_config(self):
        """Ventana de información y configuración del detector de insultos."""
        parent = self._config_win or self.root
        win = _CTK.CTkToplevel(parent) if _ctk() else _TK.Toplevel(parent)
        win.title("Configurar insultos")
        win.configure(bg=BG)
        _place(win, 500, 580, min_w=440, min_h=420)
        win.resizable(True, True)
        win.transient(parent)
        win.grab_set()

        body = _mk_frame(win, fg=BG, corner=0)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        _mk_label(body, "DETECTOR DE INSULTOS", (DISP, 22, "bold"), CYAN, bg=BG).pack(anchor="w")
        _mk_label(body, "// detección de lenguaje ofensivo en español (Vosk STT)",
                  (MONO, 10), TEXT3, bg=BG).pack(anchor="w", pady=(0, 16))

        # ---- Léxico ----
        n = self._count_insults()
        lexico = _mk_frame(body, fg=SURFACE, corner=10, border=1, border_color=BORDER)
        lexico.pack(fill="x", pady=(0, 12))
        _mk_label(lexico, "LÉXICO", (MONO, 10, "bold"), TEXT2, bg=SURFACE).pack(
            anchor="w", padx=16, pady=(14, 4))
        _mk_label(lexico, f"data/insultos.csv  ·  {n} entradas cargadas",
                  (MONO, 12, "bold"), CYAN, bg=SURFACE).pack(anchor="w", padx=16, pady=(0, 4))
        _mk_label(lexico, "Edita ese CSV para ampliar o reducir el léxico.",
                  (MONO, 10), TEXT3, bg=SURFACE).pack(anchor="w", padx=16, pady=(0, 14))

        # ---- Modelo Vosk (con estado real) ----
        modelo = _mk_frame(body, fg=SURFACE, corner=10, border=1, border_color=BORDER)
        modelo.pack(fill="x", pady=(0, 12))
        _mk_label(modelo, "MODELO VOSK (STT)", (MONO, 10, "bold"), TEXT2, bg=SURFACE).pack(
            anchor="w", padx=16, pady=(14, 4))
        status_text, status_color = self._vosk_model_status()
        _mk_label(modelo, status_text, (MONO, 12, "bold"), status_color, bg=SURFACE).pack(
            anchor="w", padx=16, pady=(0, 4))
        _mk_label(modelo, "Variable de entorno RAGE_VOSK_MODEL para ruta personalizada.",
                  (MONO, 10), TEXT3, bg=SURFACE).pack(anchor="w", padx=16, pady=(0, 14))

        # ---- Nota de privacidad ----
        _mk_label(body, "🔒  Ningún transcripto se muestra ni se guarda.",
                  (MONO, 10), HAPPY, bg=BG).pack(anchor="w", pady=(0, 6))

        # Botón anclado abajo: así nunca queda fuera del borde de la ventana.
        _mk_button(body, "Cerrar", win.destroy,
                   fg=SURFACE2, hover=SURFACE3, text_color=TEXT2,
                   height=38, font=(MONO, 12)).pack(fill="x", side="bottom")

    def _count_insults(self) -> int:
        """Cuenta entradas válidas en data/insultos.csv."""
        try:
            import csv as _csv
            p = ROOT / "data" / "insultos.csv"
            with open(p, "r", encoding="utf-8") as f:
                return sum(1 for r in _csv.reader(f) if r and r[0].strip())
        except Exception:
            return 0

    def _vosk_model_status(self):
        """Devuelve (texto, color) según si el modelo Vosk está disponible.

        Comprueba RAGE_VOSK_MODEL y, si no, la ruta por defecto models/vosk-es.
        Da feedback claro al usuario en lugar de un texto fijo."""
        import os
        from src.paths import resource_path
        env = os.environ.get("RAGE_VOSK_MODEL")
        candidate = Path(env) if env else Path(resource_path("models", "vosk-es"))
        try:
            present = candidate.exists() and any(candidate.iterdir())
        except Exception:
            present = candidate.exists()
        if present:
            shown = env if env else "models/vosk-es"
            return (f"{shown}  ·  modelo detectado ✓", HAPPY)
        return ("models/vosk-es  ·  no encontrado (se descargará al usar)", WARN)

    def _run_subprocess(self, cmd):
        # En desarrollo lanzamos desde la raíz del proyecto; congelado, desde la
        # carpeta de datos de usuario (escribible) ya que las rutas internas son
        # absolutas y ROOT/main.py no existe dentro del .exe.
        run_cwd = str(user_data_dir()) if is_frozen() else str(ROOT)

        def worker():
            try:
                subprocess.run(cmd, cwd=run_cwd)
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


def _set_label_fg(widget, color):
    try:
        if _ctk():
            widget.configure(text_color=color)
        else:
            widget.configure(fg=color)
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
