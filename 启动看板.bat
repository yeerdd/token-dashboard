@echo off
cd /d "%~dp0"

rem check port 8712
powershell -NoProfile -Command "if (Test-NetConnection 127.0.0.1 -Port 8712 -WarningAction SilentlyContinue -InformationLevel Quiet) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 goto startserver
goto openapp

:startserver
echo [START] server not running, starting...
start /min python server.py --port 8712 --workspace-only
ping -n 4 127.0.0.1 >nul
goto openapp

:openapp
echo [OPEN] opening dashboard in Chrome...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://127.0.0.1:8712 --window-size=1280,800
ping -n 2 127.0.0.1 >nul
exit /b 0