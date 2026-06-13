# 🎮 RAGE TRACKER

**Sistema multi-sensor de deteccion y analisis de emociones, gritos e insultos en tiempo real durante sesiones de videojuegos**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![OpenCV](https://img.shields.io/badge/opencv-4.13-green.svg)](https://opencv.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 Descripcion

RAGE TRACKER es un sistema que combina **vision por computadora** y **audio en tiempo real** para detectar emociones faciales, gritos e insultos mientras juegas videojuegos. Identifica patrones de felicidad, frustracion, estallidos de voz e insultos, proporcionando estadisticas detalladas y visualizaciones interactivas en un dashboard web.

### 💡 ¿Para que sirve?

- **🎯 Autoconocimiento**: Descubre que juegos te frustran mas
- **📊 Analisis de patrones**: Identifica momentos de mayor rage (gritos + insultos incluidos)
- **🏥 Salud mental**: Detecta cuando necesitas un descanso
- **🎓 Investigacion**: Analiza como diferentes generos afectan emocionalmente
- **🎮 Desarrollo de juegos**: Feedback emocional para game testing

---

## ✨ Caracteristicas Principales

### 🎥 Deteccion Facial en Tiempo Real
- Captura de emociones via webcam durante las sesiones de juego
- Sistema de confianza que muestra la certeza de cada deteccion
- Contadores en vivo de emociones detectadas

### 😊😠 Logica Binaria Optimizada
- **Feliz**: Detecta sonrisas (aunque sean leves)
- **Enfadado**: Cara seria o expresion de frustracion
- **Neutral**: Existe como placeholder para futuras mejoras

### 🔊 Deteccion de Gritos (Audio Monitor)
- Monitoreo en tiempo real del volumen del microfono
- Barra VU con pico-hold visible en el HUD
- Umbral de grito configurable (arrastrable en la GUI)
- Contador de gritos, pico en dBFS y segundos gritando
- Sesiones solo-audio sin camara: ventana ligera con VU y contadores
- Backend: sounddevice (principal) con PyAudio como fallback
- Cada grito suma al indice de rage

### 🤬 Deteccion de Insultos (Vosk STT)
- Reconocimiento de voz espanol en tiempo real via Vosk
- Lexico de insultos pre-cargado con stemmer espanol propio
- Debounce de 2s por insulto para evitar doble conteo
- Indicador en HUD (pastilla superior derecha)
- Sesiones solo-insultos o combinadas con gritos y/o emociones
- Privacidad: **ningun transcripto se muestra al usuario**
- Cada insulto suma al indice de rage

### 🎮 Modos de Sensor Multiples
Selecciona cualquier combinacion al iniciar una sesion:

| Combinacion | Camara | Gritos | Insultos |
|-------------|--------|--------|----------|
| Solo emociones | ✅ | ❌ | ❌ |
| Solo gritos | ❌ | ✅ | ❌ |
| Solo insultos | ❌ | ❌ | ✅ |
| Gritos + insultos | ❌ | ✅ | ✅ |
| Emociones + gritos | ✅ | ✅ | ❌ |
| Emociones + insultos | ✅ | ❌ | ✅ |
| Full (todos) | ✅ | ✅ | ✅ |

### 🖥️ GUI Nativa (Launcher)
- Ventana de inicio unificada con CustomTkinter (fallback a tkinter)
- Configuracion de sensores antes de cada sesion
- Medidor de microfono en vivo en el panel de configuracion
- Calibracion de microfono estilo juego de terror
- Linea de umbral arrastrable en la barra VU
- Boton de calibrar cara integrado

### 📊 Dashboard Web Interactivo
- Diseno moderno estilo cyberpunk/gaming
- Graficos interactivos con Chart.js
- 4 secciones: Overview, Games, Sessions, Analytics
- Metricas de gritos e insultos en tarjetas, timeline y heatmap
- Ranking de "boca mas sucia" por juego
- Responsive para movil y desktop

### 📈 Analisis Historico
- Almacenamiento persistente en CSV
- Estadisticas acumuladas por juego
- Comparacion entre diferentes juegos
- Deteccion de picos de rage y rachas de felicidad

### ⚙️ Configuracion Personalizable
- Herramienta interactiva para ajustar sensibilidad
- Calibracion automatica de camara (captura guiada + busqueda optima)
- Perfil de calibracion persistente en `data/calibration_profile.json`
- Umbral de grito y sensibilidad del microfono ajustables
- Lexico de insultos editable en `data/insultos.csv`
- Multiples perfiles predefinidos
- Exportar/importar configuraciones

---

## 🚀 Instalacion

> **¿Solo quieres usarlo?** Hay un ejecutable de Windows listo para usar (no
> necesita Python ni instalar nada): descarga el ZIP desde la
> [pagina del proyecto](https://anthony0827.github.io/reage-traker/) o las
> [Releases](https://github.com/Anthony0827/reage-traker/releases/latest),
> descomprime y abre `RageTracker.exe`. La guia para generarlo esta en
> [`BUILD.md`](BUILD.md). El resto de esta seccion es para ejecutar desde el codigo.

### Requisitos del Sistema

- **Python**: 3.8 o superior
- **Webcam**: Camara funcional (720p recomendado)
- **Microfono**: Cualquier microfono integrado o externo
- **Disco**: ~200MB + ~200MB (modelo Vosk espanol)
- **SO**: Windows, macOS, o Linux
- **Linux**: `sudo apt install libportaudio2` (para sounddevice)

### Instalacion Rapida

```bash
# 1. Clonar el repositorio
git clone https://github.com/Anthony0827/reage-traker.git
cd reage-traker

# 2. Crear entorno virtual (recomendado)
python -m venv venv

# Activar entorno virtual
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Descargar modelo Vosk para espanol
# (necesario solo para deteccion de insultos)
# Opcion A: descarga automatica (primera ejecucion con insultos activados)
# Opcion B: descarga manual
#    Ve a https://alphacephei.com/vosk/models
#    Descarga "vosk-model-small-es-0.42" (~200MB)
#    Extrae en models/vosk-es/
#    O setea la variable RAGE_VOSK_MODEL apuntando a tu carpeta

# 5. Ejecutar
python main.py
```

---

## 💻 Uso

### 1️⃣ Abrir la GUI (recomendado)

```bash
python main.py
```

Esto abre el **launcher** nativo con:
- Panel de bienvenida con acceso rapido a los comandos
- Botones para iniciar sesion o abrir el dashboard
- Configuracion de juego, sensores y microfono

**Flujo de trabajo desde la GUI:**
1. Haz clic en "CONFIGURAR SESION"
2. Selecciona un juego (o anade uno nuevo)
3. Elige que sensores activar (emociones, gritos, insultos)
4. Configura el microfono (umbral, sensibilidad, dispositivo)
5. Haz clic en "INICIAR RAGE TRACKER"
6. Juega normalmente - el sistema monitorea todo en tiempo real
7. Presiona `Q` para terminar y guardar
8. Revisa el resumen con estadisticas

### 2️⃣ Modo CLI (terminal)

```bash
# Menu de terminal clasico
python main.py --cli

# Sesion directa con sensores especificos
python main.py --session --game "CS2" --sensors emotions scream insults --threshold 80 --sensitivity 1.5

# Calibracion guiada
python main.py --calibrate
```

### 3️⃣ Ver Estadisticas en el Dashboard

```bash
python web/dashboard_server.py
```

Abre tu navegador en: **http://localhost:8000/dashboard**

### 4️⃣ Configurar Sensibilidad (Opcional)

```bash
python utils/config_tool.py
```

### Controles Durante la Sesion

| Tecla | Accion |
|-------|--------|
| `Q` | Terminar y guardar la sesion |
| `R` | Reiniciar todos los contadores |
| `ESC` | Cancelar / volver |

---

## 📁 Estructura del Proyecto

```
reage-traker/
│
├── data/                       # Datos persistentes
│   ├── games.csv              # Lista de juegos
│   ├── sessions.csv           # Registro de sesiones
│   ├── insultos.csv           # Lexico de insultos (stem base)
│   └── calibration_profile.json # Perfil de calibracion
│
├── models/                     # Modelos Vosk (descargar aparte)
│   └── vosk-es/               # vosk-model-small-es-0.42
│
├── src/                        # Codigo fuente principal
│   ├── __init__.py
│   ├── audio_monitor.py       # Monitor de microfono / deteccion de gritos
│   ├── calibration.py         # Calibracion automatica de camara
│   ├── camera.py              # Detector de emociones faciales
│   ├── data_manager.py        # Gestion de datos (CSV)
│   ├── hud.py                 # HUD (Heads-Up Display) sobre frames de camara
│   ├── insult_detector.py     # Deteccion de insultos via Vosk STT
│   ├── launcher.py            # GUI nativa (CustomTkinter + fallback tkinter)
│   ├── menu.py                # Interfaz CLI (menu de terminal)
│   └── session_runner.py      # Orquestador de sesion multi-sensor
│
├── utils/                      # Utilidades
│   ├── __init__.py
│   └── config_tool.py         # Herramienta de configuracion
│
├── web/                        # Dashboard web
│   ├── dashboard.html
│   └── dashboard_server.py
│
├── tests/                      # Tests unitarios
│   └── test_*.py
│
├── main.py                     # Punto de entrada unificado (argparse)
├── requirements.txt
├── pytest.ini                  # Configuracion de pytest
└── README.md
```

---

## 🛠️ Tecnologias

- **Python 3.8+** - Lenguaje principal
- **OpenCV 4.13+** - Vision por computadora
- **NumPy 2.4+** - Procesamiento numerico
- **sounddevice >=0.4.6** - Captura de audio en tiempo real
- **Vosk >=0.3.45** - Reconocimiento de voz offline (STT espanol)
- **customtkinter >=5.2** - GUI nativa (opcional: fallback a tkinter)
- **Chart.js** - Graficos interactivos en el dashboard
- **HTML/CSS/JS** - Dashboard web
- **pytest** - Testing con marcadores unit/integration/e2e

---

## ⚙️ Configuracion

### Parametros de Deteccion Facial

```json
{
  "detection": {
    "smile_scale_factor": 1.9,
    "smile_min_neighbors": 22,
    "brow_angry_threshold": 90,
    "frames_between_counts": 14
  }
}
```

### Parametros de Audio (CLI)

| Flag | Default | Descripcion |
|------|---------|-------------|
| `--threshold` | 80 | Umbral de grito en % de volumen (0-100) |
| `--sensitivity` | 1.0 | Ganancia del microfono. Subelo si la barra apenas se mueve |
| `--mic` | auto | Indice del dispositivo de entrada |
| `--sensors` | emotions | Sensores: emotions, scream, insults |

### Ajustes Comunes

**Detecta demasiado rage:**
```
brow_angry_threshold: 90 -> 95
frames_between_counts: 14 -> 18
```

**No detecta sonrisas:**
```
smile_min_neighbors: 22 -> 18
```

**Barra de microfono apenas se mueve:**
```
--sensitivity 2.0  (o mas)
```

**Demasiados falsos gritos:**
```
--threshold 90     (sube el umbral)
```

### Lexico de Insultos

Edita `data/insultos.csv` para anadir o quitar insultos. Cada linea es una palabra en su forma base (el stemmer se encarga de las variantes). El archivo se carga al iniciar el detector.

---

## 🎯 Como Funciona

### Logica de Deteccion Facial

1. ✅ **Detecta sonrisa** -> FELIZ (85-100% confianza)
2. ❌ **NO detecta sonrisa** -> ENFADADO (80% confianza)
3. 🤷 **Rostro parcial** -> NEUTRAL (raro, baja confianza)

### Sistema Anti-Falsos Positivos
- Requiere 6-8 frames consecutivos
- Solo cuenta cada 14 frames (~0.5 segundos)
- Sistema de confianza visual

### Deteccion de Gritos

1. El `AudioMonitor` captura bloques de 1024 frames desde el microfono
2. Convierte RMS a dBFS y mapea a porcentaje 0-100%
3. Suavizado exponencial para una lectura estable
4. Si el nivel supera el umbral por >=0.3 segundos -> **GRITO**
5. Cada grito suma `RAGE_PER_SCREAM = 1.0` al contador de enfado
6. Pico-hold con caida lenta para visualizacion

### Deteccion de Insultos

1. `InsultDetector` abre un stream independiente de audio a 16kHz
2. Vosk reconoce voz espanol y devuelve texto en resultados parciales y finales
3. Cada palabra se pasa por un stemmer espanol propio (sin NLTK)
4. Si el stem coincide con el lexico -> **INSULTO**
5. Debounce de 2s por stem para evitar doble conteo
6. Cada insulto suma `RAGE_PER_INSULT = 0.3` al contador de enfado
7. **Ningun transcripto se muestra al usuario** (privacidad)

---

## 📊 Formato de Datos

### `data/sessions.csv`

```csv
game,date,duration_seconds,happy_count,angry_count,neutral_count,
happy_percentage,angry_percentage,neutral_percentage,peak_rage_count,
happiness_streaks,emotional_trend,total_frames,
scream_count,scream_peak_db,scream_total_seconds,mic_device_name,
insult_count,insult_peak_count,insult_model_name
```

Las columnas `scream_*` y `insult_*` solo aparecen si esos sensores estaban activos.

---

## 🐛 Solucion de Problemas

### La camara no se abre
```bash
pip install --upgrade opencv-python
```

### El microfono no funciona
```bash
# Verificar backend disponible
python -c "from src.audio_monitor import diagnose; print(diagnose())"

# En Linux: instalar PortAudio
sudo apt install libportaudio2
```

### Deteccion de gritos imprecisa
1. Abre el panel de configuracion de microfono en la GUI
2. Ajusta el umbral (arrastra la linea celeste en la barra VU)
3. Prueba con diferentes sensibilidades
4. Verifica que el microfono correcto este seleccionado

### Vosk no reconoce insultos
1. Verifica que el modelo esta descargado en `models/vosk-es/`
2. O usa la variable de entorno: `set RAGE_VOSK_MODEL=ruta/al/modelo`
3. Verifica el lexico en `data/insultos.csv`

### Deteccion facial imprecisa
1. Mejora la iluminacion
2. Ajusta umbrales: `python utils/config_tool.py`
3. Manten tu cara visible (40-60cm de la camara)
4. Ejecuta calibracion: `python main.py --calibrate`

### La GUI no arranca (CustomTkinter no instalado)
La app cae automaticamente a tkinter incluido en Python. Si quieres la GUI mejorada:
```bash
pip install customtkinter
```

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas!

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/NuevaCaracteristica`)
3. Commit (`git commit -m 'Anadir caracteristica'`)
4. Push (`git push origin feature/NuevaCaracteristica`)
5. Abre un Pull Request

---

## 👥 Autor

- **Anthony** - *Desarrollador Principal* - [@Anthony0827](https://github.com/Anthony0827)

---

## 🔐 Privacidad

- ✅ 100% local - los datos no salen de tu PC
- ✅ Sin conexion a internet requerida (modelos descargados)
- ✅ No se graban videos
- ✅ Deteccion de insultos: ningun transcripto se muestra ni persiste
- ✅ Open source - codigo auditable

---

## 🎮 ¡Empieza Ahora!

```bash
git clone https://github.com/Anthony0827/reage-traker.git
cd reage-traker
pip install -r requirements.txt
python main.py
```

**Desarrollado con 🎮 para gamers que quieren entender sus emociones**

---