@echo off
setlocal enabledelayedexpansion
title PixivDownloader Installer

echo Welcome to the PixivDownloader WebUI installer.
echo.

set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
set "MINICONDA_DIR=%UserProfile%\Miniconda3"
set "ENV_DIR=%INSTALL_DIR%\env"
set "MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-py312_25.11.1-1-Windows-x86_64.exe"
set "CONDA_EXE=%MINICONDA_DIR%\Scripts\conda.exe"
set "CONDA_BAT=%MINICONDA_DIR%\condabin\conda.bat"
set "ENV_PYTHON=%ENV_DIR%\python.exe"

set "startTime=%TIME%"
set "startHour=%TIME:~0,2%"
set "startMin=%TIME:~3,2%"
set "startSec=%TIME:~6,2%"
set /a startHour=1%startHour% - 100
set /a startMin=1%startMin% - 100
set /a startSec=1%startSec% - 100
set /a startTotal=startHour*3600 + startMin*60 + startSec

cd /d "%INSTALL_DIR%"
call :install_miniconda || goto :error
call :create_conda_env || goto :error
call :install_backend_dependencies || goto :error
call :install_frontend_dependencies || goto :error
call :build_frontend || goto :error

set "endTime=%TIME%"
set "endHour=%TIME:~0,2%"
set "endMin=%TIME:~3,2%"
set "endSec=%TIME:~6,2%"
set /a endHour=1%endHour% - 100
set /a endMin=1%endMin% - 100
set /a endSec=1%endSec% - 100
set /a endTotal=endHour*3600 + endMin*60 + endSec
set /a elapsed=endTotal - startTotal
if %elapsed% lss 0 set /a elapsed+=86400
set /a hours=elapsed / 3600
set /a minutes=(elapsed %% 3600) / 60
set /a seconds=elapsed %% 60

echo Installation time: %hours% hours, %minutes% minutes, %seconds% seconds.
echo.
echo PixivDownloader WebUI has been installed successfully.
echo To start the WebUI, run run-webui.bat.
echo To start the legacy PyQt GUI, run run-gui.bat.
echo.
pause
exit /b 0

:install_miniconda
if exist "%CONDA_EXE%" (
    echo Miniconda already installed. Skipping Miniconda installation.
    echo.
    exit /b 0
)

echo Miniconda not found. Downloading installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& {Invoke-WebRequest -Uri '%MINICONDA_URL%' -OutFile '%INSTALL_DIR%\miniconda.exe'}"
if not exist "%INSTALL_DIR%\miniconda.exe" (
    echo Download failed. Please check your internet connection and try again.
    exit /b 1
)

echo Installing Miniconda...
start /wait "" "%INSTALL_DIR%\miniconda.exe" /InstallationType=JustMe /RegisterPython=0 /S /D=%MINICONDA_DIR%
if errorlevel 1 (
    echo Miniconda installation failed.
    exit /b 1
)

del "%INSTALL_DIR%\miniconda.exe"
echo Miniconda installation complete.
echo.
exit /b 0

:create_conda_env
if exist "%ENV_PYTHON%" (
    echo Local environment already exists at "%ENV_DIR%".
    echo.
    exit /b 0
)

echo Creating local Conda environment...
if exist "%MINICONDA_DIR%\_conda.exe" (
    call "%MINICONDA_DIR%\_conda.exe" create --no-shortcuts -y -k --prefix "%ENV_DIR%" python=3.12
) else (
    call "%CONDA_EXE%" create --no-shortcuts -y -k --prefix "%ENV_DIR%" python=3.12
)
if errorlevel 1 (
    echo Failed to create the local Conda environment.
    exit /b 1
)

echo Local Conda environment created successfully.
echo.
exit /b 0

:install_backend_dependencies
if not exist "%ENV_PYTHON%" (
    echo Local Python was not found at "%ENV_PYTHON%".
    echo The installer will not use a global Python installation.
    exit /b 1
)

echo Installing backend dependencies into the local env folder...
"%ENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%ENV_PYTHON%" -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1

echo Backend dependencies installation complete.
echo.
exit /b 0

:install_frontend_dependencies
where npm >nul 2>nul
if errorlevel 1 (
    echo npm was not found.
    echo Please install the current Windows LTS version of Node.js from https://nodejs.org/
    echo Then run this installer again.
    echo.
    exit /b 1
)

if not exist "%INSTALL_DIR%\frontend\package.json" (
    echo Frontend package.json was not found.
    exit /b 1
)

echo Installing frontend dependencies...
cd /d "%INSTALL_DIR%\frontend"
if exist "package-lock.json" (
    call npm ci
) else (
    call npm install
)
if errorlevel 1 exit /b 1

cd /d "%INSTALL_DIR%"
echo Frontend dependencies installation complete.
echo.
exit /b 0

:build_frontend
echo Building frontend assets...
cd /d "%INSTALL_DIR%\frontend"
call npm run build
if errorlevel 1 exit /b 1

cd /d "%INSTALL_DIR%"
if not exist "%INSTALL_DIR%\frontend\dist\index.html" (
    echo Frontend build did not produce frontend\dist\index.html.
    exit /b 1
)

echo Frontend build complete.
echo.
exit /b 0

:error
echo An error occurred during installation. Please check the output above for details.
pause
exit /b 1
