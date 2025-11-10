@echo off

if "%~1"=="" (
    echo Usage: upload ^<commit-message^>
    exit /b 1
)

call git add *
call git add .
call git commit -m "%~1"
call git push

if errorlevel 1 (
    echo Error: Could not commit changes.
    exit /b 1
)