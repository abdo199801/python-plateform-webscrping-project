@echo off
echo ============================================
echo Chrome/ChromeDriver Fix Script for Windows
echo ============================================
echo.

:: Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Please right-click and select "Run as administrator"
    pause
    exit /b 1
)

echo [1/6] Checking Chrome installation...
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    echo Chrome found at: C:\Program Files\Google\Chrome\Application\chrome.exe
    "C:\Program Files\Google\Chrome\Application\chrome.exe" --version
) else (
    echo WARNING: Chrome not found at default location!
    echo Please install Chrome from: https://www.google.com/chrome/
)
echo.

echo [2/6] Killing any existing Chrome processes...
taskkill /F /IM chrome.exe 2>nul
taskkill /F /IM chromedriver.exe 2>nul
echo Done.
echo.

echo [3/6] Checking for existing ChromeDriver...
where chromedriver >nul 2>&1
if %errorLevel% equ 0 (
    echo ChromeDriver found in PATH:
    where chromedriver
    chromedriver --version
) else (
    echo ChromeDriver not found in PATH
)
echo.

echo [4/6] Cleaning up temporary Chrome profiles...
if exist "%TEMP%\chrome_profile_*" (
    rd /s /q "%TEMP%\chrome_profile_*" 2>nul
    echo Cleaned up temporary profiles
) else (
    echo No temporary profiles found
)
echo.

echo [5/6] Checking Python and packages...
python --version
pip show selenium | findstr Version
pip show webdriver-manager | findstr Version
echo.

echo [6/6] Installing/updating webdriver-manager...
pip install --upgrade webdriver-manager
echo.

echo ============================================
echo Setup complete!
echo.
echo If you still experience issues:
echo 1. Make sure Chrome is updated to the latest version
echo 2. Run your Python script as Administrator
echo 3. Temporarily disable antivirus software
echo 4. Check that Chrome versions match:
echo    - Open Chrome and go to: chrome://version
echo    - The first number is your Chrome major version
echo    - ChromeDriver must match this version
echo ============================================
pause