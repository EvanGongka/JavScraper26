#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

APP_NAME="javScraper26"
RELEASE_DIR="release/${APP_NAME}-macos"
ZIP_NAME="${APP_NAME}-macos.zip"

if [ ! -d ".venv-macos-build" ]; then
  /usr/bin/python3 -m venv .venv-macos-build
fi

source .venv-macos-build/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name "${APP_NAME}" --add-data "webui:webui" app.py

mkdir -p "${RELEASE_DIR}"
find "${RELEASE_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -R "dist/${APP_NAME}.app" "${RELEASE_DIR}/"
cp LICENSE "${RELEASE_DIR}/"
cp README.md "${RELEASE_DIR}/"

cd release
rm -f "${ZIP_NAME}"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "${APP_NAME}-macos" "${ZIP_NAME}"

echo
echo "Build finished."
echo "App: dist/${APP_NAME}.app"
echo "Release dir: ${RELEASE_DIR}"
echo "Zip: release/${ZIP_NAME}"
