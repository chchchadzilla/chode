@echo off
rem chode-start.bat — launch CHODE from this checkout (Windows).
setlocal
set "DIR=%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo CHODE needs Python 3.9+. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
%PY% "%DIR%chode-launcher.py" %*
