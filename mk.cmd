@echo off
if "%~1"=="" (
    echo Usage: mk ^<filename^>
    exit /b 1
)

rem Datei erstellen oder Zeitstempel aktualisieren
type nul > "%~1"

if errorlevel 1 (
    echo Error: Could not create or update file "%~1".
    exit /b 1
)