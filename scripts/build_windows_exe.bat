@echo off
setlocal

cd /d %~dp0\..
if not exist .venv (
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name JavScraper --add-data "webui;webui" app.py

echo.
echo Build finished. Output: dist\JavScraper\JavScraper.exe
