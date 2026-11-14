@echo off
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env from .env.example. Fill it in, run setup.bat, then run this again.
    pause
    exit /b 1
)
if not exist ".venv" (
    echo No virtual environment yet. Run setup.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
echo Starting ECHO at http://localhost:8000 ...
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
pause
