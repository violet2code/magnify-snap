"""Генерация файлов иконок для сборки (assets/icon.ico, assets/icon.png)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fast_magnifier import icons  # noqa: E402

assets = os.path.join(os.path.dirname(__file__), "..", "assets")
os.makedirs(assets, exist_ok=True)
icons.save_ico(os.path.join(assets, "icon.ico"))
icons.save_png(os.path.join(assets, "icon.png"))
icons.save_logo_assets(assets)
print("Icon and logo assets saved to assets/")
