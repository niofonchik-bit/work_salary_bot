@echo off
setlocal

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher py not found.
    exit /b 1
)

py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if not exist .env copy .env.example .env
alembic upgrade head

echo.
echo Setup completed. Fill .env and run run.bat.
