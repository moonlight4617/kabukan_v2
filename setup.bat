@echo off
chcp 65001 >nul
echo 🚀 Setting up the development environment...
echo.

REM Create virtual environment
echo Creating Python virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo ❌ Failed to create virtual environment. Please ensure Python is installed correctly.
    pause
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install --upgrade pip

REM Install production dependencies
echo Installing production dependencies...
pip install -r requirements.txt

REM Install development dependencies
echo Installing development dependencies...
pip install -r requirements-dev.txt

REM Copy environment configuration file
if not exist .env.local (
    echo Creating environment configuration file...
    copy .env.example .env.local
    echo ⚠️  Please update the .env.local file with actual configuration values.
) else (
    echo ℹ️  .env.local file already exists.
)

echo.
echo ✅ Setup complete!
echo.
echo 📋 Next steps:
echo 1. Edit the .env.local file with actual configuration values
echo 2. Activate the virtual environment: venv\Scripts\activate.bat
echo 3. Run locally: python src\main.py
echo 4. Run tests: pytest tests\ -v
echo.
pause