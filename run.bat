@echo off
REM One-command local start (Windows): creates a venv, installs deps, starts the app, opens the browser.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q --upgrade pip
pip install -q -r requirements.txt
if exist .env for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
if "%DEEPSEEK_API_KEY%"=="" echo No DEEPSEEK_API_KEY set (add it to .env) - running with cached briefs only.
start "" http://localhost:8000
echo Underwriter Exception Copilot -^> http://localhost:8000  (Ctrl+C to stop)
uvicorn web.api:app --port 8000
