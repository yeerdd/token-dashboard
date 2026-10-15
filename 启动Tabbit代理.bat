@echo off
chcp 65001 >nul
title Tabbit AI Proxy (Port 8916)
echo ===================================================
echo           Tabbit AI 本地反代网关 (端口 8916)
echo ===================================================
echo.
cd /d "C:\Users\Fox-OS\Desktop\omni-ide-gateway\workers"
node tabbit_proxy.mjs
pause
