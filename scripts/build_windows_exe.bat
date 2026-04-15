@echo off
setlocal

cd /d %~dp0\..
if not exist .venv (
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name javScraper26 --add-data "webui;webui" app.py

echo.
echo Build finished. Output: dist\javScraper26\javScraper26.exe
