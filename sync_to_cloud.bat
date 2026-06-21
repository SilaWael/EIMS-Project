@echo off
REM ===========================================================================
REM EIMS Cloud Sync Script
REM ===========================================================================
REM This script syncs your local EIMS data to GitHub, which automatically
REM updates the Streamlit Cloud app.
REM
REM Usage: Double-click this file, OR run from command line:
REM        sync_to_cloud.bat
REM
REM What it does:
REM   1. Adds eims.db (your database) to git
REM   2. Adds any new PDF/HTML files in pdf_archive/
REM   3. Commits with a timestamped message
REM   4. Pushes to GitHub
REM   5. Streamlit Cloud auto-redeploys in 1-3 minutes
REM
REM Prerequisites:
REM   - Git installed (https://git-scm.com)
REM   - Repository cloned with: git clone https://github.com/SilaWael/EIMS-Project.git
REM   - OR initialized with: git init && git remote add origin https://github.com/SilaWael/EIMS-Project.git
REM ===========================================================================

title EIMS Cloud Sync
color 0B

echo =========================================================================
echo                    EIMS Cloud Sync - GitHub Push
echo =========================================================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check if git is available
where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git is not installed or not in PATH.
    echo Please download from: https://git-scm.com
    pause
    exit /b 1
)

REM Check if this is a git repository
if not exist ".git" (
    echo [INFO] Initializing git repository...
    git init
    git remote add origin https://github.com/SilaWael/EIMS-Project.git
    git branch -M main
)

REM Get current timestamp
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "YYYY=%dt:~0,4%"
set "MM=%dt:~4,2%"
set "DD=%dt:~6,2%"
set "HH=%dt:~8,2%"
set "Min=%dt:~10,2%"
set "TIMESTAMP=%YYYY%-%MM%-%DD% %HH%:%Min%"

echo [1/5] Adding database and PDFs to git...
echo      (Temporarily overriding .gitignore for eims.db)
git add -f eims.db
git add pdf_archive/ 2>nul
git add core/ auth/ ui/ tests/ 2>nul
git add *.py *.txt *.md *.toml *.yml 2>nul
git add .streamlit/ .github/ 2>nul

echo.
echo [2/5] Committing changes...
git commit -m "Daily sync: %TIMESTAMP%"

if errorlevel 1 (
    echo.
    echo [INFO] No changes to commit. Database is already up-to-date.
    echo.
    pause
    exit /b 0
)

echo.
echo [3/5] Pushing to GitHub...
git push origin main

if errorlevel 1 (
    echo.
    echo [ERROR] Push failed. Possible causes:
    echo   - Authentication issue (need to login with GitHub)
    echo   - No internet connection
    echo   - Remote repository issue
    echo.
    echo Try running: git push origin main
    echo.
    pause
    exit /b 1
)

echo.
echo [4/5] Push complete!
echo.
echo [5/5] Streamlit Cloud will auto-redeploy in 1-3 minutes.
echo       Visit: https://daily-progress-silla.streamlit.app/
echo.
echo =========================================================================
echo  Sync complete at %TIMESTAMP%
echo  Your cloud app will refresh automatically.
echo =========================================================================
echo.
pause
