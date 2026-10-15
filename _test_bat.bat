@echo off
chcp 65001 >nul
echo [TEST] bat is running, errorlevel check next
cd /d "%~dp0"

rem check DSH web port 3080
powershell -NoProfile -Command "if (Test-NetConnection 127.0.0.1 -Port 3080 -WarningAction SilentlyContinue -InformationLevel Quiet) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 goto startdsh
goto openapp

:startdsh
echo [START] DSH not running, starting...
start /min cmd /c "dsh web"
ping -n 5 127.0.0.1 >nul
goto openapp

:openapp
echo [OPEN] opening DSH in Chrome...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://127.0.0.1:3080 --window-size=1400,900
ping -n 2 127.0.0.1 >nul
exit /b 0
