@echo off
rem Serves this folder on http://localhost:8765 (needed once, to install Parquet Pivot as an app).
rem Nothing leaves your machine: the page only runs locally, the data is never uploaded.
cd /d "%~dp0"
start "" cmd /c "timeout /t 2 /nobreak >nul & start msedge http://localhost:8765/app.html"
python -m http.server 8765 --bind 127.0.0.1
