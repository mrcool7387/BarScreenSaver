@echo off
rem Aktiviere virtuelle Umgebung (Windows)
call .\.venv\Scripts\activate.bat

rem Alle übergebenen Dateien formatieren
isort %*
black %*
