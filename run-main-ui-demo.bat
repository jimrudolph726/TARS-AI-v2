@echo off
setlocal
cd /d "%~dp0"
python src\app-main-qml.py %*
if errorlevel 1 (
  echo.
  echo If PySide6 is missing, run: python -m pip install -r requirements-main-ui-qml.txt
  pause
)
