# =============================================================================
#  RAGE TRACKER - Compilar ejecutable Windows (onedir + ZIP)
# =============================================================================
#  Uso:   desde la raíz del proyecto, en PowerShell:
#             .\build_windows.ps1
#
#  Qué hace:
#    1. Comprueba que el modelo Vosk está presente (models/vosk-es).
#    2. Instala PyInstaller si falta (en el Python actual).
#    3. Compila con rage_tracker.spec -> dist/RageTracker/RageTracker.exe
#    4. Comprime dist/RageTracker en RageTracker-windows.zip (lo que subes a la
#       Release de GitHub; el botón "Instalar" de la web enlaza a ese archivo).
#
#  Requisitos: las dependencias del proyecto ya instaladas (opencv, numpy,
#  sounddevice, vosk, customtkinter) en el mismo Python con el que compiles.
# =============================================================================

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "=== RAGE TRACKER · build de ejecutable ===" -ForegroundColor Cyan

# --- 1. Comprobar modelo Vosk -------------------------------------------------
$ModelDir = Join-Path $ProjectRoot "models\vosk-es"
if (-not (Test-Path $ModelDir)) {
    Write-Host "[!] No se encuentra el modelo en models\vosk-es." -ForegroundColor Yellow
    Write-Host "    El detector de insultos quedará sin modelo. Coloca el modelo" -ForegroundColor Yellow
    Write-Host "    Vosk español en models\vosk-es antes de compilar si lo quieres." -ForegroundColor Yellow
}

# --- 2. PyInstaller -----------------------------------------------------------
python -m PyInstaller --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[i] PyInstaller no está instalado. Instalándolo..." -ForegroundColor Yellow
    python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar PyInstaller." }
}

# --- 3. Limpiar builds previos y compilar ------------------------------------
Write-Host "[i] Compilando (esto tarda un par de minutos)..." -ForegroundColor Cyan
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist")  { Remove-Item "dist"  -Recurse -Force }

python -m PyInstaller rage_tracker.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "La compilación falló." }

$ExePath = Join-Path $ProjectRoot "dist\RageTracker\RageTracker.exe"
if (-not (Test-Path $ExePath)) { throw "No se generó el ejecutable esperado." }

# --- 4. Comprimir para distribuir --------------------------------------------
$Zip = Join-Path $ProjectRoot "RageTracker-windows.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Write-Host "[i] Comprimiendo dist\RageTracker -> RageTracker-windows.zip" -ForegroundColor Cyan
Compress-Archive -Path "dist\RageTracker\*" -DestinationPath $Zip -CompressionLevel Optimal

$SizeMB = [math]::Round((Get-Item $Zip).Length / 1MB, 1)
Write-Host ""
Write-Host "=== LISTO ===" -ForegroundColor Green
Write-Host "  Ejecutable: dist\RageTracker\RageTracker.exe"
Write-Host "  Para repartir: RageTracker-windows.zip ($SizeMB MB)"
Write-Host ""
Write-Host "  Súbelo como asset en una Release de GitHub. El boton 'Instalar' de"
Write-Host "  la web (docs/index.html) enlaza a la ultima Release."
