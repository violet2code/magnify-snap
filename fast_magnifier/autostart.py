"""Автозапуск при входе в систему: реестр (Windows) / autostart .desktop (Linux)."""
import os
import sys

from . import APP_ID, APP_NAME

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):  # собранный PyInstaller exe
        return f'"{sys.executable}"'
    script = os.path.abspath(sys.argv[0])
    python = sys.executable
    if sys.platform == "win32":
        pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
        if os.path.exists(pythonw):
            python = pythonw
    return f'"{python}" "{script}"'


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_ID)
            return True
        except OSError:
            return False
    return os.path.exists(_desktop_path())


def set_enabled(enabled: bool) -> bool:
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    winreg.SetValueEx(
                        key, APP_ID, 0, winreg.REG_SZ, _launch_command()
                    )
                else:
                    try:
                        winreg.DeleteValue(key, APP_ID)
                    except FileNotFoundError:
                        pass
        else:
            path = _desktop_path()
            if enabled:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(
                        "[Desktop Entry]\n"
                        "Type=Application\n"
                        f"Name={APP_NAME}\n"
                        f"Exec={_launch_command()}\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            elif os.path.exists(path):
                os.remove(path)
        return True
    except OSError:
        return False


def _desktop_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "autostart", "magnifysnap.desktop")
