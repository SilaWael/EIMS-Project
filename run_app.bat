@echo off
title EIMS Engineering System - Wael Radwan
echo ==============================================================================
echo              EIMS - Engineering Information Management System
echo                  Smart Engineering Info Management System
echo ==============================================================================
echo.
echo [1/2] Launching the local Streamlit application server...
echo.
py -m streamlit run app.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] An error occurred while trying to launch the application.
    echo Please make sure the 'streamlit' library is correctly installed.
    echo To install it manually, open Command Prompt and run: py -m pip install streamlit
)
echo.
pause
