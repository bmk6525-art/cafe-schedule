@echo off
start "Backend" /d "%~dp0backend" cmd /k python -m uvicorn app.main:app --reload --port 8000
timeout /t 3 /nobreak > nul
start "Frontend" /d "%~dp0frontend" cmd /k npm run dev
