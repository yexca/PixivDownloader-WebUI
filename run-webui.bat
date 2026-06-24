@echo off
setlocal
title PixivDownloader WebUI

set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
set "ENV_PYTHON=%INSTALL_DIR%\env\python.exe"
set "FRONTEND_INDEX=%INSTALL_DIR%\frontend\dist\index.html"
if "%PIXIVDOWNLOADER_PORT%"=="" set "PIXIVDOWNLOADER_PORT=7653"
set "APP_URL=http://127.0.0.1:%PIXIVDOWNLOADER_PORT%"

if /i "%cd%"=="C:\Windows\System32" (
    color 0C
    echo PixivDownloader does not require administrator permissions.
    echo Please run this script as a regular user from the project folder.
    echo.
    pause
    exit /b 1
)

if not exist "%ENV_PYTHON%" (
    echo Local environment not found.
    echo Please run run-install.bat first to set up the environment.
    echo.
    pause
    exit /b 1
)

if not exist "%FRONTEND_INDEX%" (
    echo Built WebUI assets were not found.
    echo Please run run-install.bat to install dependencies and build the frontend.
    echo Expected file: "%FRONTEND_INDEX%"
    echo.
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%"
echo Starting PixivDownloader WebUI at %APP_URL%
echo Close this window to stop the local backend.
echo.

start "" /min powershell -NoProfile -ExecutionPolicy Bypass -Command "$url = '%APP_URL%'; for ($i = 0; $i -lt 30; $i++) { try { Invoke-WebRequest -UseBasicParsing -Uri ($url + '/api/health') -TimeoutSec 1 | Out-Null; Start-Process $url; exit 0 } catch { Start-Sleep -Seconds 1 } }; Start-Process $url"
"%ENV_PYTHON%" -m backend.app
echo.
pause
