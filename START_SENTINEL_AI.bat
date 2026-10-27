@echo off
setlocal
cd /d "%~dp0"
if not exist "backend\venv\Scripts\python.exe" (
  echo Creating backend virtual environment...
  py -3 -m venv "backend\venv"
  if errorlevel 1 python -m venv "backend\venv"
)
if not exist "backend\venv\Scripts\python.exe" (
  echo ERROR: Could not create the backend virtual environment.
  pause
  exit /b 1
)
echo Installing backend dependencies. This may take a few minutes...
"backend\venv\Scripts\python.exe" -m pip install --upgrade pip
"backend\venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 (
  echo ERROR: Backend dependencies could not be installed.
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
start "Sentinel AI Backend" cmd /k "cd /d ""%~dp0backend"" && ""venv\Scripts\python.exe"" app.py"
if not exist "frontend\node_modules" (
  echo Installing frontend dependencies. This may take a few minutes...
  pushd "frontend"
  call npm install
  if errorlevel 1 (
    echo ERROR: Frontend dependencies could not be installed.
    popd
    pause
    exit /b 1
  )
  popd
)
start "Sentinel AI Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"
echo.
echo Sentinel AI is starting. Open http://127.0.0.1:5173 when Vite is ready.
echo If backend setup fails, keep this window open to read the error.
endlocal
