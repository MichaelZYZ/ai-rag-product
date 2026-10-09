@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PROJECT_ROOT=%~dp0."
set "SETUP_ARGS="
if "%~1"=="--setup-only" set "SETUP_ARGS=-SetupOnly"
if not "%~1"=="" if not "%~1"=="--setup-only" (
    echo Usage: start_windows.bat [--setup-only]
    exit /b 2
)
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL_EXE%" set "POWERSHELL_EXE=powershell.exe"

"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap_windows.ps1" -ProjectRoot "%PROJECT_ROOT%" %SETUP_ARGS%
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo Startup failed. Review the error above.
    if not defined CI pause
)
exit /b %EXIT_CODE%
