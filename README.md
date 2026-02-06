# 🎮 RAGE TRACKER

**Sistema de detección y análisis de emociones en tiempo real durante sesiones de videojuegos**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![OpenCV](https://img.shields.io/badge/opencv-4.13-green.svg)](https://opencv.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 Descripción

RAGE TRACKER es un sistema que utiliza **visión por computadora** para detectar y analizar emociones faciales mientras juegas videojuegos. Identifica patrones de felicidad y frustración en tiempo real, proporcionando estadísticas detalladas y visualizaciones interactivas para ayudarte a entender tu experiencia emocional durante el gaming.

### 💡 ¿Para qué sirve?

- **🎯 Autoconocimiento**: Descubre qué juegos te frustran más
- **📊 Análisis de patrones**: Identifica momentos de mayor rage
- **🏥 Salud mental**: Detecta cuando necesitas un descanso
- **🎓 Investigación**: Analiza cómo diferentes géneros afectan emocionalmente
- **🎮 Desarrollo de juegos**: Feedback emocional para game testing

---

## ✨ Características Principales

### 🎥 Detección en Tiempo Real
- Captura de emociones vía webcam durante las sesiones de juego
- Sistema de confianza que muestra la certeza de cada detección
- Contadores en vivo de emociones detectadas

### 😊😠 Lógica Binaria Optimizada
- **Feliz**: Detecta sonrisas (aunque sean leves)
- **Enfadado**: Cara seria o expresión de frustración
- **Neutral**: Existe como placeholder para futuras mejoras

### 📊 Dashboard Web Interactivo
- Diseño moderno estilo cyberpunk/gaming
- Gráficos interactivos con Chart.js
- 4 secciones: Overview, Games, Sessions, Analytics
- Responsive para móvil y desktop

### 📈 Análisis Histórico
- Almacenamiento persistente en CSV
- Estadísticas acumuladas por juego
- Comparación entre diferentes juegos
- Detección de picos de rage y rachas de felicidad

### ⚙️ Configuración Personalizable
- Herramienta interactiva para ajustar sensibilidad
- Múltiples perfiles predefinidos
- Exportar/importar configuraciones

---

## 🚀 Instalación

### Requisitos del Sistema

- **Python**: 3.8 o superior
- **Webcam**: Cámara funcional (720p recomendado)
- **Espacio**: ~200MB
- **SO**: Windows, macOS, o Linux

### Instalación Rápida

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

# 4. Ejecutar
python main.py
```

---

## 💻 Uso

### 1️⃣ Grabar una Sesión de Juego

```bash
python main.py
```

**Flujo de trabajo:**
1. Selecciona un juego (o añade uno nuevo)
2. La cámara se activa automáticamente
3. Juega normalmente - el sistema detecta tus emociones
4. Presiona `Q` para terminar y guardar
5. Revisa el resumen con estadísticas

**Controles:**
- `Q` → Terminar y guardar
- `R` → Reiniciar contadores

### 2️⃣ Ver Estadísticas en el Dashboard

```bash
python web/dashboard_server.py
```

Abre tu navegador en: **http://localhost:8000/dashboard**

### 3️⃣ Configurar Sensibilidad (Opcional)

```bash
python utils/config_tool.py
```

---

## 📁 Estructura del Proyecto

```
reage-traker/
│
├── data/                   # Datos de sesiones (CSV)
│   ├── games.csv          # Lista de juegos
│   └── sessions.csv       # Registro de sesiones
│
├── src/                    # Código fuente principal
│   ├── __init__.py
│   ├── camera.py          # Detector de emociones
│   ├── data_manager.py    # Gestión de datos
│   └── menu.py            # Interfaz CLI
│
├── utils/                  # Utilidades
│   ├── __init__.py
│   └── config_tool.py     # Configuración
│
├── web/                    # Dashboard web
│   ├── dashboard.html
│   └── dashboard_server.py
│
├── main.py                 # Punto de entrada
├── requirements.txt
└── README.md
```

---

## 🛠️ Tecnologías

- **Python 3.8+** - Lenguaje principal
- **OpenCV 4.13** - Visión por computadora
- **NumPy 2.4** - Procesamiento numérico
- **Chart.js** - Gráficos interactivos
- **HTML/CSS/JS** - Dashboard web

---

## ⚙️ Configuración

### Parámetros Principales

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

### Ajustes Comunes

**Detecta demasiado rage:**
```
brow_angry_threshold: 90 → 95
frames_between_counts: 14 → 18
```

**No detecta sonrisas:**
```
smile_min_neighbors: 22 → 18
```

---

## 🎯 Cómo Funciona

### Lógica de Detección

1. ✅ **Detecta sonrisa** → FELIZ (85-100% confianza)
2. ❌ **NO detecta sonrisa** → ENFADADO (80% confianza)
3. 🤷 **Rostro parcial** → NEUTRAL (raro, baja confianza)

### Sistema Anti-Falsos Positivos
- Requiere 6-8 frames consecutivos
- Solo cuenta cada 14 frames (~0.5 segundos)
- Sistema de confianza visual

---

## 📊 Formato de Datos

### `data/sessions.csv`
```csv
game,date,duration_seconds,happy_count,angry_count,neutral_count,
happy_percentage,angry_percentage,neutral_percentage,peak_rage_count,
happiness_streaks,emotional_trend,total_frames
```

---

## 🐛 Solución de Problemas

### La cámara no se abre
```bash
pip install --upgrade opencv-python
```

### Detección imprecisa
1. Mejora la iluminación
2. Ajusta umbrales: `python utils/config_tool.py`
3. Mantén tu cara visible (40-60cm)

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas!

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/NuevaCaracteristica`)
3. Commit (`git commit -m 'Añadir característica'`)
4. Push (`git push origin feature/NuevaCaracteristica`)
5. Abre un Pull Request

---





## 👥 Autor

- **Anthony** - *Desarrollador Principal* - [@Anthony0827](https://github.com/Anthony0827)


---



## 🔐 Privacidad

- ✅ 100% local - los datos no salen de tu PC
- ✅ Sin conexión a internet requerida
- ✅ No se graban videos
- ✅ Open source - código auditable

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


