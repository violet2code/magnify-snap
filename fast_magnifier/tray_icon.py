"""Иконка в системном трее (pystray) с контекстным меню."""
import threading

import pystray

from . import APP_NAME
from .icons import magnifier_image


class Tray:
    def __init__(self, on_toggle, on_settings, on_exit, is_active):
        self._img_idle = magnifier_image(64, active=False)
        self._img_on = magnifier_image(64, active=True)
        menu = pystray.Menu(
            pystray.MenuItem("Settings…", lambda: on_settings(), default=True),
            pystray.MenuItem(
                "Magnifier", lambda: on_toggle(),
                checked=lambda item: is_active(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: on_exit()),
        )
        self.icon = pystray.Icon(APP_NAME, self._img_idle, APP_NAME, menu)
        self._thread = None

    def run(self) -> None:
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def set_active(self, active: bool) -> None:
        try:
            self.icon.icon = self._img_on if active else self._img_idle
            self.icon.title = (
                f"{APP_NAME} — magnifier active" if active else APP_NAME
            )
        except Exception:
            pass

    def notify(self, message: str) -> None:
        try:
            self.icon.notify(message, APP_NAME)
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass
