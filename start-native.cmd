@echo off
rem Starts the native DuckDB engine for huge Parquet files (no browser memory limit) and opens Parquet Pivot.
rem   start-native.cmd                       -> start and open the browser
rem   start-native.cmd "D:\data\big.parquet" -> ...and open that file (use this for "Open with" on .parquet files)
rem Options (put them in front of the file names):  --memory 48GB   --threads 16   --port 8765
cd /d "%~dp0"
python -c "import duckdb" 2>nul || (echo Installing the duckdb package once... & python -m pip install duckdb)
python server.py %*
if errorlevel 1 pause
