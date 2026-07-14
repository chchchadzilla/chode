@echo off
rem chode-start.bat — plays a splash video, then launches Chad Code (Chode mode) (Windows).
rem Splash: %CHODE_SPLASH% -> %USERPROFILE%\.chode\splash.mp4 -> splash.mp4 next to this file
setlocal EnableDelayedExpansion

set "DIR=%~dp0"
set "SPLASH=%CHODE_SPLASH%"
if "%SPLASH%"=="" set "SPLASH=%USERPROFILE%\.chode\splash.mp4"
if not exist "%SPLASH%" set "SPLASH=%DIR%splash.mp4"

rem find python (py launcher first, then python)
set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if exist "%SPLASH%" if not "%CHODE_NO_SPLASH%"=="1" (
  where ffmpeg >nul 2>nul
  if !errorlevel! == 0 (
    %PY% "%DIR%chode_splash.py" "%SPLASH%"
  ) else (
    where ffplay >nul 2>nul && ffplay -autoexit -fs -loglevel quiet "%SPLASH%"
  )
)

%PY% "%DIR%chode.py" %*
