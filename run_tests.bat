@echo off
REM Test runner script for Windows

echo ================================================
echo Running Facial Recognition Photo Organizer Tests
echo ================================================

REM Activate virtual environment
call venv\Scripts\activate.bat

echo.
echo Running all tests with coverage...
echo.

REM Run tests
python -m pytest

echo.
echo ================================================
echo Test run complete!
echo Coverage report saved to: htmlcov\index.html
echo ================================================

pause
