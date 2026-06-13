# Compilar y publicar Rage Tracker

Guía para generar el ejecutable de Windows y publicar la web + la descarga.

## 1. Compilar el ejecutable

Requisitos: tener instaladas las dependencias del proyecto (las mismas que para
ejecutar `python main.py`) y el modelo de voz en `models/vosk-es`.

Desde la raíz del proyecto, en PowerShell:

```powershell
.\build_windows.ps1
```

El script:
1. Instala PyInstaller si falta.
2. Compila con `rage_tracker.spec` (modo **onedir**).
3. Deja el programa en `dist\RageTracker\RageTracker.exe`.
4. Comprime todo en **`RageTracker-windows.zip`** (el archivo que repartes).

> El modelo Vosk (58 MB) y el léxico de insultos van **dentro** del paquete, así
> que el usuario final no necesita descargar nada más ni instalar Python.

### Dónde guarda los datos el .exe
- **Recursos** (modelo, léxico, dashboard): dentro del ejecutable (solo lectura).
- **Datos de usuario** (perfil de calibración, CSV de sesiones):
  `%APPDATA%\RageTracker\data` (escribible). Así funciona aunque se instale en
  "Archivos de programa".

### Depurar un fallo del .exe
Si el .exe no arranca, edita `rage_tracker.spec` y pon `console=True` para ver
los mensajes en una consola, recompila y reproduce el error.

## 2. Publicar la descarga (GitHub Releases)

El `.zip` **no** se sube al repositorio (está en `.gitignore`); se publica como
*asset* de una Release:

1. En GitHub: **Releases → Draft a new release**.
2. Crea una etiqueta, p. ej. `v1.0.0`, y un título.
3. Arrastra `RageTracker-windows.zip` a la zona de *assets*.
4. **Publish release.**

El botón "Instalar" de la web apunta a `releases/latest`, así que siempre
ofrecerá la versión más reciente sin tocar el HTML.

## 3. Activar la web (GitHub Pages)

La landing está en `docs/index.html`.

1. En GitHub: **Settings → Pages**.
2. **Source:** Deploy from a branch.
3. **Branch:** `master` · **Folder:** `/docs` · **Save**.
4. En un par de minutos estará en:
   `https://anthony0827.github.io/reage-traker/`

> Si cambias el nombre del repositorio, actualiza los enlaces a GitHub dentro de
> `docs/index.html` (búsqueda: `reage-traker`).
