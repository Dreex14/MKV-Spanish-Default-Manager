@echo off
setlocal
cd /d "%~dp0"
echo === MKV Spanish Default Manager: instalacion ===

where python >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python. Instala Python 3.10 o superior desde https://www.python.org/downloads/
  echo y marca "Add python.exe to PATH" durante la instalacion.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  python -m venv .venv
  if errorlevel 1 ( echo No se pudo crear el entorno virtual. & pause & exit /b 1 )
)

echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo Error instalando dependencias. & pause & exit /b 1 )

set "FOUND="
where mkvpropedit >nul 2>nul && set "FOUND=1"
if exist "%ProgramFiles%\MKVToolNix\mkvpropedit.exe" set "FOUND=1"
if exist "%ProgramFiles(x86)%\MKVToolNix\mkvpropedit.exe" set "FOUND=1"
if not defined FOUND (
  echo.
  echo AVISO: no se detecta MKVToolNix. Instalalo con:
  echo     winget install MoritzBunkus.MKVToolNix
  echo o desde https://mkvtoolnix.download/downloads.html#windows
)

echo.
echo Listo. Ejecuta run.bat para abrir la aplicacion.
pause
