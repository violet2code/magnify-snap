"""Лупа для Linux.

GNOME  — штатная лупа через gsettings: режим слежения 'push'
         (экран двигается, когда курсор упирается в край видимой области).
KDE    — эффект Zoom в KWin через глобальные шорткаты (qdbus).
Прочее — не поддерживается, выводится уведомление.
"""
import math
import os
import shutil
import subprocess
import threading

from .magnifier_base import MagnifierBase, NullMagnifier


def _run(cmd) -> bool:
    try:
        return subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class GnomeMagnifier(MagnifierBase):
    SCHEMA_APP = "org.gnome.desktop.a11y.applications"
    SCHEMA_MAG = "org.gnome.desktop.a11y.magnifier"

    def zoom_in(self) -> None:
        if self.active:
            return
        self.active = True
        threading.Thread(target=self._enable, daemon=True).start()

    def zoom_out(self, instant: bool = False) -> None:
        if not self.active:
            return
        self.active = False
        threading.Thread(target=self._disable, daemon=True).start()

    def _enable(self) -> None:
        _run(["gsettings", "set", self.SCHEMA_MAG, "mag-factor",
              str(float(self.config.zoom_factor))])
        # 'push' — экран следует за курсором только у края видимой области
        _run(["gsettings", "set", self.SCHEMA_MAG, "mouse-tracking", "push"])
        ok = _run(["gsettings", "set", self.SCHEMA_APP,
                   "screen-magnifier-enabled", "true"])
        if not ok:
            self.active = False
            self.notify("Could not enable the GNOME magnifier (gsettings).")

    def _disable(self) -> None:
        _run(["gsettings", "set", self.SCHEMA_APP,
              "screen-magnifier-enabled", "false"])

    def set_boost(self, factor: float | None) -> None:
        if not self.active:
            return
        target = float(factor) if factor else float(self.config.zoom_factor)
        threading.Thread(
            target=lambda: _run(["gsettings", "set", self.SCHEMA_MAG,
                                 "mag-factor", str(target)]),
            daemon=True,
        ).start()

    def shutdown(self) -> None:
        if self.active:
            self.active = False
            self._disable()


class KdeMagnifier(MagnifierBase):
    """Управление эффектом KWin Zoom через вызов глобальных шорткатов."""

    def __init__(self, config, notify=None):
        super().__init__(config, notify)
        self._qdbus = next(
            (exe for exe in ("qdbus6", "qdbus", "qdbus-qt6", "qdbus-qt5")
             if shutil.which(exe)),
            None,
        )
        self._lock = threading.Lock()

    def _shortcut(self, name: str) -> bool:
        return _run([self._qdbus, "org.kde.kglobalaccel", "/component/kwin",
                     "invokeShortcut", name])

    def zoom_in(self) -> None:
        with self._lock:
            if self.active:
                return
            self.active = True
        threading.Thread(target=self._enable, daemon=True).start()

    def zoom_out(self, instant: bool = False) -> None:
        with self._lock:
            if not self.active:
                return
            self.active = False
        threading.Thread(
            target=lambda: self._shortcut("view_actual_size"), daemon=True
        ).start()

    def _enable(self) -> None:
        if self._qdbus is None:
            self.active = False
            self.notify("qdbus not found — install the qt-tools/qdbus package.")
            return
        # Шаг зума KWin по умолчанию 1.2 → подбираем число нажатий
        steps = max(1, round(math.log(float(self.config.zoom_factor)) / math.log(1.2)))
        ok = True
        for _ in range(steps):
            ok = self._shortcut("view_zoom_in") and ok
        if not ok:
            self.active = False
            self.notify(
                "Could not enable the KWin Zoom effect.\n"
                "Make sure the Zoom effect is enabled in KDE settings."
            )

    def shutdown(self) -> None:
        if self.active:
            self.active = False
            if self._qdbus:
                self._shortcut("view_actual_size")


def create_linux_magnifier(config, notify=None) -> MagnifierBase:
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP", "")
               + ":" + os.environ.get("DESKTOP_SESSION", "")).lower()
    if "gnome" in desktop or "unity" in desktop or "cinnamon" in desktop:
        return GnomeMagnifier(config, notify)
    if "kde" in desktop or "plasma" in desktop:
        return KdeMagnifier(config, notify)
    if shutil.which("gsettings"):
        return GnomeMagnifier(config, notify)
    return NullMagnifier(config, notify)
