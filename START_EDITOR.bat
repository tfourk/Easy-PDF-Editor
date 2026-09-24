@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto check
py -3 --version >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv .venv
    goto created
)
python --version >nul 2>&1
if errorlevel 1 goto nopython
python -m venv .venv
:created
if not exist ".venv\Scripts\python.exe" goto failed
:check
.venv\Scripts\python.exe -c "import pymupdf, PIL; assert pymupdf.VersionBind == '1.26.6'" >nul 2>&1
if not errorlevel 1 goto launch
echo Installing the editor components. First run needs internet access...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
:launch
.venv\Scripts\python.exe pdf_editor.py
if errorlevel 1 goto failed
exit /b 0
:nopython
echo Python was not found.
echo Install Python 3.12 or 3.13 from https://www.python.org/downloads/windows/
echo During installation, select "Add python.exe to PATH".
echo Then double-click START_EDITOR.bat again.
pause
exit /b 1
:failed
echo.
echo The editor could not start. The error is shown above.
echo Check your internet connection for first-time setup.
echo If setup is damaged, delete only this folder's .venv folder and try again.
pause
exit /b 1
