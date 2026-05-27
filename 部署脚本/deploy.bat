@echo off
setlocal

title Weibo Bot Detect - Deploy
set "SCRIPT_DIR=%~dp0"
set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS_EXE%" set "PS_EXE=powershell"

echo [System] Starting one-click deploy, please wait...
echo [System] Steps: check env, install deps, build frontend, start service, health check.
echo [System] Log dir: %SCRIPT_DIR%logs
echo.

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%deploy.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [OK] Deploy completed.
  echo [Info] See log: %SCRIPT_DIR%logs\deploy_latest.log
) else (
  echo [FAIL] Deploy failed.
  echo [Info] Check log: %SCRIPT_DIR%logs\deploy_latest.log
)
echo.
echo Press any key to close...
pause
exit /b %EXIT_CODE%
