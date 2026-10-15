@echo off
cd /d "%~dp0"
set "LAUNCHLOG=%TEMP%\dsh-launch.log"
echo [%date% %time%] launcher started >> "%LAUNCHLOG%"

rem fast port check via Get-NetTCPConnection
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 3080 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 goto startdsh
echo [%date% %time%] already running -> openapp >> "%LAUNCHLOG%"
goto openapp

:startdsh
echo [%date% %time%] starting dsh web >> "%LAUNCHLOG%"
rem use absolute path: plain `dsh` may resolve to the stale npm copy (0.1.0) which rejects --no-open
set "DSHCMD=C:\Users\Fox-OS\AppData\Local\hermes\node\dsh.cmd"
if not exist "%DSHCMD%" set "DSHCMD=dsh"
start /min cmd /c "call %DSHCMD% web --no-open > %TEMP%\dsh-web.log 2>&1"

rem poll until port 3080 is listening (max ~60s), then open browser
set /a tries=0
:waitloop
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 3080 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [%date% %time%] port ready after %tries% retries -> openapp >> "%LAUNCHLOG%"
    goto openapp
)
set /a tries+=1
if %tries% geq 30 (
    echo [%date% %time%] gave up waiting for port 3080 >> "%LAUNCHLOG%"
    goto openapp
)
ping -n 3 127.0.0.1 >nul
goto waitloop

:openapp
echo [%date% %time%] opening chrome app window >> "%LAUNCHLOG%"
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://127.0.0.1:3080 --window-size=1400,900
exit /b 0
