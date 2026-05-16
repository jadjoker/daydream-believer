@echo off
echo Starting Daydream Believer Backend...
cd /d "%~dp0backend"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing/updating dependencies...
pip install -r requirements.txt -q

echo.
echo Backend starting at http://localhost:8000
echo API docs at http://localhost:8000/docs
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
