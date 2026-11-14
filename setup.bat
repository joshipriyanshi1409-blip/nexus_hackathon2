@echo off
echo ============================================================
echo   ECHO - Setup
echo ============================================================

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo Created .env from .env.example.
    echo Open .env now and fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL,
    echo GEMINI_API_KEY and a strong ADMIN_PASSWORD ^(12+ characters^). Then run setup.bat again.
    pause
    exit /b 0
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv || goto :fail
)

call .venv\Scripts\activate.bat
echo Installing dependencies...
pip install -r backend\requirements.txt || goto :fail

echo Applying database migrations...
python -m backend.migrate || goto :fail

echo Creating the CEO account...
python -m backend.create_ceo || goto :fail

echo.
echo Setup finished. Run run.bat to start the server.
pause
exit /b 0

:fail
echo.
echo Setup stopped because a step failed. Fix the message above and run setup.bat again.
pause
exit /b 1
