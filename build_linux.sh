#!/usr/bin/env bash
# Build Magnify.Snap for Linux (single executable)
set -e
cd "$(dirname "$0")"

python3 -m pip install --upgrade -r requirements.txt pyinstaller
python3 tools/make_icon.py

python3 -m PyInstaller --noconfirm --clean --onefile --windowed \
    --name magnifysnap \
    --collect-all customtkinter \
    main.py

echo
echo "Done: dist/magnifysnap"
echo "System deps: python3-tk; tray icon may need gir1.2-ayatanaappindicator3 (GNOME needs the AppIndicator extension)."
