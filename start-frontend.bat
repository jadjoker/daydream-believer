@echo off
echo Starting Daydream Believer Frontend...
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo Installing dependencies...
    npm install
)

echo.
echo Frontend starting at http://localhost:3000
echo.
npm run dev
