@echo off
setlocal EnableExtensions

cd /d %~dp0\.. || goto :error

set "VENV_DIR=.venv-windows-build"
set "OUTPUT_EXE=dist\javScraper26\javScraper26.exe"

where python >nul 2>nul || (
  echo [ERROR] Python was not found in PATH.
  goto :error
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [INFO] Creating Windows build virtualenv: %VENV_DIR%
  python -m venv "%VENV_DIR%" || goto :error
)

call "%VENV_DIR%\Scripts\activate.bat" || goto :error
python -m pip install --upgrade pip || goto :error
pip install -r requirements.txt || goto :error
pyinstaller --noconfirm --clean --windowed --name javScraper26 --add-data "webui;webui" app.py || goto :error

if not exist "%OUTPUT_EXE%" (
  echo [ERROR] Build completed but expected output was not found: %OUTPUT_EXE%
  goto :error
)

echo.
echo Build finished. Output: %OUTPUT_EXE%
exit /b 0

:error
echo.
echo Windows build failed.
exit /b 1
