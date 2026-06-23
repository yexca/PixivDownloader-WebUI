@echo off
setlocal enabledelayedexpansion
title PixivDownloader Installer

echo Welcome to the PixivDownloader installer.
echo.

set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
set "MINICONDA_DIR=%UserProfile%\Miniconda3"
set "ENV_DIR=%INSTALL_DIR%\env"
set "MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-py312_25.11.1-1-Windows-x86_64.exe"
set "CONDA_EXE=%MINICONDA_DIR%\Scripts\conda.exe"
set "CONDA_BAT=%MINICONDA_DIR%\condabin\conda.bat"

set "startTime=%TIME%"
set "startHour=%TIME:~0,2%"
set "startMin=%TIME:~3,2%"
set "startSec=%TIME:~6,2%"
set /a startHour=1%startHour% - 100
set /a startMin=1%startMin% - 100
set /a startSec=1%startSec% - 100
set /a startTotal=startHour*3600 + startMin*60 + startSec

call :install_miniconda || goto :error
call :create_conda_env || goto :error
call :install_dependencies || goto :error

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
echo PixivDownloader has been installed successfully.
echo To start the GUI, run 'run-gui.bat'.
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
if exist "%ENV_DIR%\python.exe" (
    echo Local environment already exists at "%ENV_DIR%".
    echo.
    exit /b 0
)

echo Creating local Conda environment...
call "%MINICONDA_DIR%\_conda.exe" create --no-shortcuts -y -k --prefix "%ENV_DIR%" python=3.12
if errorlevel 1 (
    echo Failed to create the local Conda environment.
    exit /b 1
)

echo Local Conda environment created successfully.
echo.
exit /b 0

:install_dependencies
echo Installing dependencies into the local env folder...
call "%CONDA_BAT%" activate "%ENV_DIR%"
if errorlevel 1 (
    echo Failed to activate the local environment.
    exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

python -m pip install PyQt6 pixivpy3 requests PyYAML ruff pytest
if errorlevel 1 exit /b 1

call "%CONDA_BAT%" deactivate
echo Dependencies installation complete.
echo.
exit /b 0

:error
echo An error occurred during installation. Please check the output above for details.
pause
exit /b 1
