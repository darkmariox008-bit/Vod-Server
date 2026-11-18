@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PORT=8787"
set "TOKEN_FILE=%~dp0.vod_access_token.txt"
set "WEBHOOK_FILE=%~dp0discord_webhook.txt"
where python >nul 2>nul
if errorlevel 1 (
  echo Python wurde nicht gefunden. Python 3.10 oder neuer installieren und PATH aktivieren.
  pause
  exit /b 1
)
where cloudflared >nul 2>nul
if errorlevel 1 (
  echo cloudflared wurde nicht gefunden.
  echo Bitte cloudflared.exe installieren und in den Windows-PATH aufnehmen.
  pause
  exit /b 1
)
if not exist "%TOKEN_FILE%" (
  echo Erst Starten.bat ausfuehren, damit der Zugriffsschluessel erzeugt wird.
  pause
  exit /b 1
)
if not exist "%WEBHOOK_FILE%" echo Kein Discord-Webhook eingerichtet. Der Link wird trotzdem angezeigt.
python public_link.py --token-file "%TOKEN_FILE%" --discord-webhook-file "%WEBHOOK_FILE%" --local-url "http://127.0.0.1:%PORT%" --cloudflared cloudflared
pause
