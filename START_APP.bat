@echo off
echo Starting HS Code PDF Extractor...
echo Open your browser at: http://localhost:5000
echo.
echo Press CTRL+C to stop the server.
echo.
cd /d "%~dp0"
py app.py
pause
