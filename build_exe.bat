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
    copy /Y "translations.json" "dist\main\translations.json" >nul
    if errorlevel 1 (
        echo ERROR: translations.json was not copied to dist\main\
        pause
        exit /b 1
    ) else (
        echo OK: exe in dist\main\
    )
)
