@echo off
setlocal

title Weibo Bot Detect - Stop
set "SCRIPT_DIR=%~dp0"
set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS_EXE%" set "PS_EXE=powershell"

echo [System] Stopping services, please wait...
echo.

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%stop.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [OK] Stop completed.
) else (
  echo [FAIL] Stop failed. See log: %SCRIPT_DIR%logs\stop_latest.log
)
echo.
echo Press any key to close...
pause
exit /b %EXIT_CODE%
