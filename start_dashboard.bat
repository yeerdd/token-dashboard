@echo off
rem Token 看板一键启动（防重复实例）
rem 用法：双击运行；或复制到 shell:startup 实现开机自启
cd /d "%~dp0"
tasklist /fi "imagename eq python.exe" /fo csv 2>nul | findstr /i "server.py" >nul
if not errorlevel 1 (
  echo [已运行] 看板服务器已在运行: http://127.0.0.1:8712
  start "" http://127.0.0.1:8712
  exit /b 0
)
start "TokenDashboard" /min python server.py --port 8712 --workspace-only
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8712
