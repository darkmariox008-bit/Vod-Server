@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PORT=8787"
set "VOD_FOLDER=G:\Bilder Und Videos\Server"
set "CONFIG_FILE=%~dp0.vod_folder.txt"
if exist "%CONFIG_FILE%" set /p VOD_FOLDER=<"%CONFIG_FILE%"
set "TOKEN_FILE=%~dp0.vod_access_token.txt"
if not exist "%VOD_FOLDER%" (
  echo Videoordner nicht gefunden: %VOD_FOLDER%
  echo Entweder VOD_FOLDER in dieser Datei anpassen oder .vod_folder.txt anlegen.
  pause
  exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden. Python 3.10 oder neuer installieren und PATH aktivieren.
  pause
  exit /b 1
)
if not exist "%TOKEN_FILE%" python -c "import secrets; print(secrets.token_urlsafe(24))" > "%TOKEN_FILE%"
set /p ACCESS_KEY=<"%TOKEN_FILE%"
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do set "PORT_PID=%%P"
if defined PORT_PID (
  echo VOD-HUB laeuft bereits auf Port %PORT%.
  start "" "http://127.0.0.1:%PORT%/?key=%ACCESS_KEY%"
  pause
  exit /b 0
)
start "VOD-HUB Server" "%ComSpec%" /d /k call "%~dp0run_server.bat"
for /l %%N in (1,1,20) do (
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%PORT%/api/status?key=%ACCESS_KEY%', timeout=1)" >nul 2>nul && goto ready
  timeout /t 1 /nobreak >nul
)
echo Server wurde nicht rechtzeitig bereit. Bitte das Serverfenster pruefen.
pause
exit /b 1
:ready
echo Pruefe neue und geaenderte MKV-Dateien ...
python "%~dp0vod_convert.py" --folder "%VOD_FOLDER%"
if errorlevel 1 echo MKV-Scan hatte einen Fehler. Vorhandene MP4-Dateien bleiben verfuegbar.
start "" "http://127.0.0.1:%PORT%/?key=%ACCESS_KEY%"
exit /b 0
