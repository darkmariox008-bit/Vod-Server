@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PORT=8787"
set "VOD_FOLDER=G:\Bilder Und Videos\Server"
set "CONFIG_FILE=%~dp0.vod_folder.txt"
if exist "%CONFIG_FILE%" set /p VOD_FOLDER=<"%CONFIG_FILE%"
set "TOKEN_FILE=%~dp0.vod_access_token.txt"
set "PATH=%~dp0runtime\ffmpeg;%PATH%"
echo VOD-HUB Server: %VOD_FOLDER%
python local_vod_server.py --folder "%VOD_FOLDER%" --web-root "%~dp0website" --host 127.0.0.1 --port %PORT% --access-token-file "%TOKEN_FILE%"
echo.
echo Server beendet. Fenster bleibt fuer die Fehlersuche offen.
pause
