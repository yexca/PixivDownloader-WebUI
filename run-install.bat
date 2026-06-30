@echo off
setlocal enabledelayedexpansion
title PixivDownloader Installer

echo Welcome to the PixivDownloader WebUI installer.
echo.

set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"
set "ENV_DIR=%INSTALL_DIR%\env"
set "MINICONDA_DIR=%ENV_DIR%\conda"
set "PYTHON_DIR=%ENV_DIR%\python"
set "MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-py312_25.11.1-1-Windows-x86_64.exe"
set "CONDA_EXE=%MINICONDA_DIR%\Scripts\conda.exe"
set "CONDA_BAT=%MINICONDA_DIR%\condabin\conda.bat"
set "ENV_PYTHON=%PYTHON_DIR%\python.exe"
set "NODE_VERSION=v22.12.0"
set "NODE_DIR=%ENV_DIR%\node"
set "NODE_ZIP=%ENV_DIR%\node.zip"
set "NODE_URL=https://nodejs.org/dist/%NODE_VERSION%/node-%NODE_VERSION%-win-x64.zip"
set "NPM_CMD=%NODE_DIR%\npm.cmd"

set "startTime=%TIME%"
set "startHour=%TIME:~0,2%"
set "startMin=%TIME:~3,2%"
set "startSec=%TIME:~6,2%"
set /a startHour=1%startHour% - 100
set /a startMin=1%startMin% - 100
set /a startSec=1%startSec% - 100
set /a startTotal=startHour*3600 + startMin*60 + startSec

cd /d "%INSTALL_DIR%"
if not exist "%ENV_DIR%" mkdir "%ENV_DIR%"
call :prepare_env_layout || goto :error
call :install_miniconda || goto :error
call :create_conda_env || goto :error
call :install_backend_dependencies || goto :error
call :install_node || goto :error
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
echo.
pause
exit /b 0

:prepare_env_layout
if exist "%ENV_DIR%\python.exe" if not exist "%ENV_PYTHON%" (
    echo A legacy env layout was found at "%ENV_DIR%".
    echo The installer now uses:
    echo   env\conda
    echo   env\python
    echo   env\node
    echo.
    set /p RESET_ENV=Delete the old env folder and reinstall local runtimes? [y/N]:
    if /i "!RESET_ENV!"=="Y" (
        echo Removing old env folder...
        rmdir /s /q "%ENV_DIR%"
        if exist "%ENV_DIR%" (
            echo Failed to remove the old env folder. Close terminals or editors using it and try again.
            exit /b 1
        )
        mkdir "%ENV_DIR%"
        echo Old env folder removed.
        echo.
        exit /b 0
    )
    echo Installation cancelled. Please remove or rename the old env folder, then run this installer again.
    exit /b 1
)
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
    echo Local Python environment already exists at "%PYTHON_DIR%".
    echo.
    exit /b 0
)

echo Creating local Conda environment...
if exist "%MINICONDA_DIR%\_conda.exe" (
    call "%MINICONDA_DIR%\_conda.exe" create --no-shortcuts -y -k --prefix "%PYTHON_DIR%" python=3.12
) else (
    call "%CONDA_EXE%" create --no-shortcuts -y -k --prefix "%PYTHON_DIR%" python=3.12
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

echo Installing backend dependencies into the local Python runtime...
"%ENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%ENV_PYTHON%" -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1

echo Backend dependencies installation complete.
echo.
exit /b 0

:install_node
if exist "%NPM_CMD%" (
    echo Local Node.js already exists at "%NODE_DIR%".
    echo.
    exit /b 0
)

echo Installing local Node.js into "%NODE_DIR%"...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $ErrorActionPreference = 'Stop'; $zip = '%NODE_ZIP%'; $extract = '%ENV_DIR%\node-extract'; $nodeDir = '%NODE_DIR%'; if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }; if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }; if (Test-Path $nodeDir) { Remove-Item -LiteralPath $nodeDir -Recurse -Force }; Invoke-WebRequest -Uri '%NODE_URL%' -OutFile $zip; Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force; $expanded = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1; if (-not $expanded) { throw 'Node.js archive did not contain an extracted directory.' }; Move-Item -LiteralPath $expanded.FullName -Destination $nodeDir; Remove-Item -LiteralPath $extract -Recurse -Force; Remove-Item -LiteralPath $zip -Force }"
if errorlevel 1 (
    echo Node.js installation failed.
    exit /b 1
)

if not exist "%NPM_CMD%" (
    echo npm was not found after installing local Node.js.
    exit /b 1
)

echo Local Node.js installation complete.
echo.
exit /b 0

:install_frontend_dependencies
if not exist "%INSTALL_DIR%\frontend\package.json" (
    echo Frontend package.json was not found.
    exit /b 1
)

echo Installing frontend dependencies...
cd /d "%INSTALL_DIR%\frontend"
if exist "package-lock.json" (
    call "%NPM_CMD%" ci
) else (
    call "%NPM_CMD%" install
)
if errorlevel 1 exit /b 1

cd /d "%INSTALL_DIR%"
echo Frontend dependencies installation complete.
echo.
exit /b 0

:build_frontend
echo Building frontend assets...
cd /d "%INSTALL_DIR%\frontend"
call "%NPM_CMD%" run build
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
