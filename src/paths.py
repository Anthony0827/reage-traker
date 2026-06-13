"""
RAGE TRACKER - Resolución de rutas (fuente vs. ejecutable congelado)
====================================================================
Centraliza CÓMO encontrar archivos, para que la app funcione igual
ejecutándose desde el código (`python main.py`) que empaquetada como .exe
con PyInstaller.

Dos tipos de ruta, deliberadamente separados:

- RECURSOS (solo lectura): el modelo de voz, el léxico de insultos, los
  cascades... Van DENTRO del paquete. En un .exe de PyInstaller se extraen a
  una carpeta temporal accesible vía `sys._MEIPASS`.

- DATOS DE USUARIO (escritura): el perfil de calibración y los CSV de sesiones.
  NO pueden vivir dentro del .exe (sería de solo lectura, y además en
  "Archivos de programa" Windows bloquea la escritura). Van a
  `%APPDATA%/RageTracker` cuando está congelado.

En modo desarrollo (sin congelar) AMBOS apuntan a la raíz del proyecto, así
que el comportamiento es idéntico al de siempre: `data/` y `models/` junto al
código.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Nombre de la carpeta de datos de usuario bajo %APPDATA% (modo congelado).
APP_DIR_NAME = "RageTracker"


def is_frozen() -> bool:
    """True si corremos dentro de un ejecutable de PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Carpeta base de los RECURSOS de solo lectura (modelo, léxico, etc.)."""
    if is_frozen():
        # PyInstaller extrae los datos a _MEIPASS; si no existe (onedir muy
        # raro), caemos a la carpeta del ejecutable.
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
        return Path(sys.executable).resolve().parent
    # Desarrollo: raíz del proyecto (este archivo está en src/).
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Carpeta con permisos de ESCRITURA para perfil y CSV de sesiones.

    Congelado → %APPDATA%/RageTracker (siempre escribible por el usuario).
    Desarrollo → raíz del proyecto (mantiene `data/` dentro del repo, como antes).
    """
    if is_frozen():
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = Path(base) / APP_DIR_NAME
    else:
        d = Path(__file__).resolve().parent.parent
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_path(*parts: str) -> str:
    """Ruta absoluta a un recurso empaquetado (solo lectura)."""
    return str(resource_dir().joinpath(*parts))


def user_data_path(*parts: str) -> str:
    """Ruta absoluta a un archivo de datos de usuario (escritura), creando
    los directorios padre si hace falta."""
    p = user_data_dir().joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def app_launch_cmd(*args: str) -> list:
    """Comando para relanzar la propia app con argumentos de CLI.

    Es la pieza que hace que el botón de "Iniciar sesión" / "Recalibrar"
    funcione TAMBIÉN en el .exe:

    - Congelado: `sys.executable` ES la app → `[RageTracker.exe, "--session", ...]`.
    - Desarrollo: `[python, main.py, "--session", ...]` como hasta ahora.
    """
    if is_frozen():
        return [sys.executable, *args]
    return [sys.executable, str(resource_dir() / "main.py"), *args]
