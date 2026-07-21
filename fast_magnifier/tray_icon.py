"""Иконка в системном трее (pystray) с контекстным меню."""
import threading

import pystray

from . import APP_NAME
from .icons import magnifier_image


class Tray:
    def __init__(self, on_toggle, on_settings, on_exit, is_active):
        self._img_idle = magnifier_image(64, active=False)
        self._img_on = magnifier_image(64, active=True)
        self._on_toggle = on_toggle
        self._on_settings = on_settings
        self._on_exit = on_exit
        self._is_active = is_active
        self._update_label = None
        self._on_update = None
        self.icon = pystray.Icon(APP_NAME, self._img_idle, APP_NAME,
                                 self._build_menu())
        self._thread = None

    def _build_menu(self) -> pystray.Menu:
        items = [
            pystray.MenuItem("Settings…", lambda: self._on_settings(),
                             default=True),
            pystray.MenuItem("Magnifier", lambda: self._on_toggle(),
                             checked=lambda item: self._is_active()),
        ]
        if self._update_label:
            items += [pystray.Menu.SEPARATOR,
                      pystray.MenuItem(self._update_label,
                                       lambda: self._on_update())]
        items += [pystray.Menu.SEPARATOR,
                  pystray.MenuItem("Quit", lambda: self._on_exit())]
        return pystray.Menu(*items)

    def set_update(self, label: str | None, action=None) -> None:
        """Показать/убрать пункт «Update to vX…» в меню трея."""
        self._update_label = label
        self._on_update = action
        try:
            self.icon.menu = self._build_menu()
            self.icon.update_menu()
        except Exception:
            pass

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
