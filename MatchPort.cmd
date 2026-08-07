@echo off
rem ตัวเปิดระบบ — เป้าหมายของ shortcut บน Desktop (ไอคอน assets\matchport.ico)
title News-Customer Matching - INVX
cd /d "%~dp0"
chcp 65001 >nul

set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1" %*
if errorlevel 1 (
  echo.
  echo === startup failed - see error above ===
  pause
)
