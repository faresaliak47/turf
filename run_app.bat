@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First-time setup: installing the Streamlit app dependencies...
  call setup.bat
  if errorlevel 1 (
    echo Setup failed.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"
set TURF_HR_PRO_DB_PATH=
echo.
echo Local access: http://localhost:8501
echo Mobile access: use the PC Wi-Fi IP printed below, on the same Wi-Fi network.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0show_lan_ip.ps1"
echo.
echo Leave this window open while using the app.
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
pause
