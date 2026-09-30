@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo EIMS - Local Test Launcher
echo ==========================================

echo Checking Windows Python launcher...
where py >nul 2>&1
if errorlevel 1 (
    echo ERROR: The Windows Python launcher ^(py.exe^) was not found.
    echo Install Python from python.org with the Python Launcher enabled.
    pause
    exit /b 1
)

for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
if not defined PYTHON_EXE (
    echo ERROR: A real Python 3 installation was not found through py -3.
    pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE%
for %%D in ("%PYTHON_EXE%") do set "PYTHON_DIR=%%~dpD"
set "PATH=%PYTHON_DIR%;%PYTHON_DIR%Scripts;%PATH%"

echo Installing / verifying required packages...
py -3 -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)

echo Starting EIMS local test server...
py -3 -m streamlit run app.py
if errorlevel 1 (
    echo.
    echo ERROR: EIMS failed to start.
    pause
    exit /b 1
)
endlocal
