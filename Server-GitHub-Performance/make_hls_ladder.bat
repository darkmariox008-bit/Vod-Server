@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON=%~dp0runtime\python\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
set "PATH=%~dp0runtime\ffmpeg;%PATH%"
if "%~1"=="" (
  echo Ziehe eine MP4-Datei auf diese BAT-Datei.
  pause
  exit /b 1
)
"%PYTHON%" --version >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden.
  pause
  exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg wurde nicht gefunden oder ist nicht im PATH.
  pause
  exit /b 1
)
where ffprobe >nul 2>nul
if errorlevel 1 (
  echo FFprobe wurde nicht gefunden oder ist nicht im PATH.
  pause
  exit /b 1
)
"%PYTHON%" "%~dp0make_hls_ladder.py" "%~1"
if errorlevel 1 (
  echo HLS-Ladder konnte nicht erstellt werden.
  pause
  exit /b 1
)
echo HLS-Ladder erfolgreich erstellt.
pause
