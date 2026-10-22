@echo off
setlocal
cd /d "%~dp0"
set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Setting up Glean the first time...
  "%PY%" -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
