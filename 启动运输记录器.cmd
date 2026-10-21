@echo off
setlocal
set "PARCEL_PY=%LOCALAPPDATA%\Programs\Python\Python39\pythonw.exe"
if not exist "%PARCEL_PY%" (
  echo Python 3.9 was not found. Run host\parcel_monitor.py with Python and pyserial.
  pause
  exit /b 1
)
start "" /b "%PARCEL_PY%" "%~dp0host\parcel_monitor.py"
