@echo off
setlocal
title PixivDownloader Frontend Dev

set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
if "%PIXIVDOWNLOADER_PORT%"=="" set "PIXIVDOWNLOADER_PORT=7653"

where npm >nul 2>nul
if errorlevel 1 (
    echo npm was not found.
    echo Please install the current Windows LTS version of Node.js from https://nodejs.org/
    echo Then run run-install.bat or npm install inside the frontend folder.
    echo.
    pause
    exit /b 1
)

if not exist "%INSTALL_DIR%\frontend\node_modules" (
    echo Frontend dependencies were not found.
    echo Please run run-install.bat first.
    echo.
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%\frontend"
echo Starting frontend dev server.
echo API proxy target: http://127.0.0.1:%PIXIVDOWNLOADER_PORT%
call npm run dev
echo.
pause
