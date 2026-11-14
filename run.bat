@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo No hay entorno instalado. Ejecutando install.bat...
  call install.bat
)
start "" ".venv\Scripts\pythonw.exe" main.py
