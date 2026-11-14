@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
echo.
echo Para anclarlo: busca "MKV Spanish Default Manager" en el menu Inicio,
echo clic derecho y elige "Anclar a Inicio" o "Anclar a la barra de tareas".
pause
