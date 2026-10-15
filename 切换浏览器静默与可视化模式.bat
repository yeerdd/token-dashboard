@echo off
chcp 65001 >nul
title Hermes Agent 浏览器模式切换控制台

:MENU
cls
echo ========================================================
echo        Hermes Agent 浏览器自动化模式切换控制台
echo ========================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$cfgPath = Join-Path $env:USERPROFILE '.agent-browser\config.json'; if (Test-Path $cfgPath) { $c = Get-Content $cfgPath -Raw | ConvertFrom-Json; if ($c.headed) { Write-Host ' [当前状态]：🖥️ 可视化窗口模式 (Headed) - AI操作时会弹出浏览器' -ForegroundColor Yellow } else { Write-Host ' [当前状态]：👻 后台静默模式 (Headless) - AI操作在后台极速执行' -ForegroundColor Cyan } } else { Write-Host ' [当前状态]：默认静默模式' -ForegroundColor Cyan }"
echo.
echo --------------------------------------------------------
echo  [1] 切换为：🖥️ 可视化窗口模式 (Headed)
echo      - 智能体操作网页时会在桌面弹出 Chromium 窗口
echo      - 可以亲眼观察智能体输入、点击、滚动与表单提交
echo.
echo  [2] 切换为：👻 后台静默极速模式 (Headless - 推荐)
echo      - 智能体操作完全在后台静默执行，不抢占焦点
echo      - 极速省资源，适合日常代码编写与沉浸式工作
echo.
echo  [3] 🚀 打开测试页面验证当前模式 (打开 example.com)
echo.
echo  [0] 退出控制台
echo --------------------------------------------------------
set /p choice=请输入选项编号 [1/2/3/0]: 

if "%choice%"=="1" goto SET_HEADED
if "%choice%"=="2" goto SET_HEADLESS
if "%choice%"=="3" goto TEST_BROWSER
if "%choice%"=="0" goto EXIT
echo 输入无效，请重新输入...
timeout /t 2 >nul
goto MENU

:SET_HEADED
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dir = Join-Path $env:USERPROFILE '.agent-browser'; if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }; $cfg = @{ headed = $true; hideScrollbars = $false }; $cfg | ConvertTo-Json | Set-Content (Join-Path $dir 'config.json') -Encoding utf8"
echo.
echo [OK] 已成功切换为：🖥️ 可视化窗口模式 (Headed)！
echo 下次智能体调用 browser 工具时将弹出浏览器窗口。
echo.
pause
goto MENU

:SET_HEADLESS
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dir = Join-Path $env:USERPROFILE '.agent-browser'; if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }; $cfg = @{ headed = $false; hideScrollbars = $true }; $cfg | ConvertTo-Json | Set-Content (Join-Path $dir 'config.json') -Encoding utf8"
echo.
echo [OK] 已成功切换为：👻 后台静默模式 (Headless)！
echo 下次智能体调用 browser 工具时将在后台静默执行。
echo.
pause
goto MENU

:TEST_BROWSER
echo.
echo 正在启动浏览器测试页面...
agent-browser open https://example.com
echo.
echo 测试完成，按任意键关闭测试浏览器会话...
pause >nul
agent-browser close >nul 2>&1
goto MENU

:EXIT
exit /b 0
