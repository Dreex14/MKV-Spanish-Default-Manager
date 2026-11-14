@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install.bat
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 ( echo Error instalando PyInstaller. & pause & exit /b 1 )

rem Copia mkvmerge, mkvpropedit y sus licencias desde el MKVToolNix instalado para incluirlos en el EXE
".venv\Scripts\python.exe" tools\bundle_mkvtoolnix.py %1
if errorlevel 1 ( echo No se pudo preparar MKVToolNix. & pause & exit /b 1 )

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --icon assets\icon.ico --add-data "assets\icon.ico;assets" ^
  --add-data "vendor\MKVToolNix;MKVToolNix" ^
  --name MKVSpanishDefaultManager main.py
if errorlevel 1 ( echo Error generando el EXE. & pause & exit /b 1 )
echo.
echo EXE generado en dist\MKVSpanishDefaultManager.exe
echo Incluye MKVToolNix (mkvmerge y mkvpropedit): funciona sin instalar nada mas.
pause
