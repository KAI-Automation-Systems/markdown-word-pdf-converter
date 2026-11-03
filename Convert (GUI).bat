@echo off
REM Double-click this file to open the Markdown -> DOCX/PDF converter.
cd /d "%~dp0"
py -3.12 md_converter.py
if errorlevel 1 pause
