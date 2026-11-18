@echo off
chcp 65001 >nul
title VOD-Server - Automatische Installation
color 0A

echo ========================================================
echo      Installation der Komponenten fuer den VOD-Server
echo ========================================================
echo.

:: 1. Pruefen ob Python installiert ist
echo [1/4] Pruefe Python-Installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Python wurde nicht gefunden. Starte Installation ueber winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo.
    echo [WICHTIG] Python wurde installiert! 
    echo Bitte schliesse dieses Fenster und starte die install.bat erneut, 
    echo damit Windows die neuen Systempfade erkennt.
    pause
    exit
) else (
    echo [OK] Python ist bereits installiert.
)
echo.

:: 2. Pruefen ob FFmpeg installiert ist (wichtig fuer vod_convert & HLS)
echo [2/4] Pruefe FFmpeg-Installation...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] FFmpeg wird ueber winget installiert...
    winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
) else (
    echo [OK] FFmpeg ist bereits installiert.
)
echo.

:: 3. Python-Pakete aktualisieren und installieren
echo [3/4] Installiere benoetigte Python-Bibliotheken...
python -m pip install --upgrade pip
python -m pip install flask requests aiohttp fastapi uvicorn python-dotenv
echo.

:: 4. Hinweis zu Tunnel-Tools (fuer public_link.py / Freigabe starten.bat)
echo [4/4] Pruefe Cloudflare Tunnel (optional fuer oeffentliche Links)...
cloudflared --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installiere cloudflared fuer oeffentliche Freigabe-Links...
    winget install -e --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
) else (
    echo [OK] cloudflared ist bereits installiert.
)

echo.
echo ========================================================
echo    Installation abgeschlossen!
echo    Du kannst den Server jetzt ueber 'Starten.bat' starten.
echo ========================================================
pause
