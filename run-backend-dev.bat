@echo off
setlocal
title PixivDownloader Backend Dev

set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
set "ENV_PYTHON=%INSTALL_DIR%\env\python.exe"
if "%PIXIVDOWNLOADER_PORT%"=="" set "PIXIVDOWNLOADER_PORT=7653"

if not exist "%ENV_PYTHON%" (
    echo Local environment not found.
    echo Please run run-install.bat first.
    echo.
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%"
echo Starting backend dev server at http://127.0.0.1:%PIXIVDOWNLOADER_PORT%
"%ENV_PYTHON%" -m uvicorn backend.app:create_app --factory --reload --host 127.0.0.1 --port %PIXIVDOWNLOADER_PORT%
echo.
pause
