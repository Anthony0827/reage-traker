# -*- mode: python ; coding: utf-8 -*-
"""
Spec de PyInstaller para RAGE TRACKER (build onedir).

Genera dist/RageTracker/RageTracker.exe junto con sus dependencias. El script
build_windows.ps1 comprime esa carpeta en RageTracker-windows.zip para repartir.

Empaqueta como RECURSOS (solo lectura): el modelo de voz Vosk, el léxico de
insultos, el HTML del dashboard y su servidor, y los haarcascades de OpenCV.
Los datos de usuario (perfil de calibración, CSV de sesiones) NO van aquí: la
app los escribe en %APPDATA%/RageTracker en tiempo de ejecución (ver src/paths.py).
"""

import os
from PyInstaller.utils.hooks import collect_all

# Carpeta del .spec = raíz del proyecto.
ROOT = os.path.abspath(os.getcwd())

datas = []
binaries = []
hiddenimports = ["_cffi_backend"]  # sounddevice (CFFI) lo necesita explícito

# Paquetes con datos/DLLs nativas que el análisis estático no recoge solo.
for pkg in ("vosk", "sounddevice", "customtkinter"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Haarcascades de OpenCV (cara, ojos, sonrisa). El hook de cv2 suele incluirlos,
# pero los añadimos explícitamente para no depender de ello.
try:
    import cv2
    haar_dir = cv2.data.haarcascades
    if haar_dir and os.path.isdir(haar_dir):
        datas.append((haar_dir, os.path.join("cv2", "data")))
except Exception:
    pass

# Recursos propios del proyecto.
_own = [
    (os.path.join(ROOT, "models", "vosk-es"), os.path.join("models", "vosk-es")),
    (os.path.join(ROOT, "data", "insultos.csv"), "data"),
    (os.path.join(ROOT, "web", "dashboard.html"), "web"),
    (os.path.join(ROOT, "web", "dashboard_server.py"), "web"),
]
for src, dest in _own:
    if os.path.exists(src):
        datas.append((src, dest))

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Stack científico/notebook que se cuela transitivamente pero la app NO usa.
    # Excluirlo recorta el paquete de ~220 MB a una fracción. (PIL se mantiene:
    # customtkinter lo necesita para sus imágenes.)
    excludes=[
        "pandas", "scipy", "matplotlib", "numba", "llvmlite",
        "IPython", "jedi", "parso", "sympy", "openpyxl", "zmq",
        "notebook", "sphinx", "pytest", "setuptools._vendor",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

_icon = os.path.join(ROOT, "web", "icono.ico")
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RageTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI sin ventana de consola. Pon True para depurar.
    disable_windowed_traceback=False,
    icon=_icon if os.path.exists(_icon) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RageTracker",
)
