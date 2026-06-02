@echo off
set PYTHON=venv\Scripts\python.exe
if not exist "%PYTHON%" (
    echo ERROR: no venv
    pause
    exit /b 1
)
"%PYTHON%" -m PyInstaller main.spec
if %errorlevel% neq 0 (
    echo ERROR: build failed
    pause
) else (
    echo OK: exe in dist\
)
