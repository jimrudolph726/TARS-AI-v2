@echo off
setlocal
cd /d "%~dp0"
python src\app-servotester-qml.py %*
if errorlevel 1 (
  echo.
  echo If PySide6 is missing, run: python -m pip install -r requirements-servotester-qml.txt
  pause
)
