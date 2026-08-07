"""Ярлык приложения в меню «Пуск» (Windows) и в меню приложений (Linux).

Портативный exe никуда себя не прописывает, а установка через winget
кладёт файл в служебную папку и ярлыков не создаёт вовсе — приложение
попросту негде найти. Поэтому программа заводит ярлык сама.

Windows: .lnk создаётся через системный COM-интерфейс IShellLink
напрямую из ctypes — без сторонних библиотек и без запуска
интерпретаторов (скрытый powershell однажды уже стоил нам детекта).
"""
import ctypes
import os
import sys
from ctypes import POINTER, byref, c_void_p, c_wchar_p

from . import APP_NAME

_LNK_NAME = f"{APP_NAME}.lnk"
_DESKTOP_NAME = "magnifysnap.desktop"


# -- пути -----------------------------------------------------------------

def shortcut_path() -> str | None:
    """Куда кладём ярлык (None — платформа не поддерживается)."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None
        return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                            "Programs", _LNK_NAME)
    if sys.platform.startswith("linux"):
        base = os.environ.get(
            "XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return os.path.join(base, "applications", _DESKTOP_NAME)
    return None


def exists() -> bool:
    path = shortcut_path()
    return bool(path) and os.path.exists(path)


# -- Windows: IShellLink через ctypes -------------------------------------

class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text: str):
        super().__init__()
        ole32 = ctypes.windll.ole32
        if ole32.CLSIDFromString(c_wchar_p(text), byref(self)) < 0:
            raise OSError(f"bad GUID {text}")


_CLSID_ShellLink = "{00021401-0000-0000-C000-000000000046}"
_IID_IShellLinkW = "{000214F9-0000-0000-C000-000000000046}"
_IID_IPersistFile = "{0000010B-0000-0000-C000-000000000046}"

# индексы методов в таблице (первые три — от IUnknown)
_SL_SET_DESCRIPTION = 7
_SL_SET_WORKING_DIR = 9
_SL_SET_ICON = 17
_SL_SET_PATH = 20
_PF_SAVE = 6
_UNK_QUERY = 0
_UNK_RELEASE = 2


def _call(obj, index: int, restype, argtypes, *args) -> int:
    """Вызов метода COM-объекта по индексу в его таблице методов."""
    vtable = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(vtable[index])(obj, *args)


def _create_windows(target: str, path: str, icon: str | None) -> None:
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    shell_link = c_void_p()
    hr = ole32.CoCreateInstance(
        byref(_GUID(_CLSID_ShellLink)), None, 1,  # CLSCTX_INPROC_SERVER
        byref(_GUID(_IID_IShellLinkW)), byref(shell_link))
    if hr < 0:
        raise OSError(f"CoCreateInstance failed: 0x{hr & 0xFFFFFFFF:08x}")
    try:
        _call(shell_link, _SL_SET_PATH, ctypes.HRESULT, [c_wchar_p],
              c_wchar_p(target))
        _call(shell_link, _SL_SET_WORKING_DIR, ctypes.HRESULT, [c_wchar_p],
              c_wchar_p(os.path.dirname(target)))
        _call(shell_link, _SL_SET_DESCRIPTION, ctypes.HRESULT, [c_wchar_p],
              c_wchar_p("Fast screen magnifier"))
        _call(shell_link, _SL_SET_ICON, ctypes.HRESULT,
              [c_wchar_p, ctypes.c_int], c_wchar_p(icon or target), 0)

        persist = c_void_p()
        hr = _call(shell_link, _UNK_QUERY, ctypes.HRESULT,
                   [c_void_p, c_void_p],
                   byref(_GUID(_IID_IPersistFile)), byref(persist))
        if hr < 0:
            raise OSError("QueryInterface(IPersistFile) failed")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            hr = _call(persist, _PF_SAVE, ctypes.HRESULT,
                       [c_wchar_p, ctypes.c_int], c_wchar_p(path), 1)
            if hr < 0:
                raise OSError(f"Save failed: 0x{hr & 0xFFFFFFFF:08x}")
        finally:
            _call(persist, _UNK_RELEASE, ctypes.c_ulong, [])
    finally:
        _call(shell_link, _UNK_RELEASE, ctypes.c_ulong, [])


# -- Linux: .desktop -------------------------------------------------------

def _create_linux(target: str, path: str, icon: str | None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={APP_NAME}\n"
            "Comment=Fast screen magnifier\n"
            f"Exec=\"{target}\"\n"
            f"Icon={icon or target}\n"
            "Terminal=false\n"
            "Categories=Utility;Accessibility;\n"
            "Keywords=magnifier;zoom;accessibility;\n"
        )
    os.chmod(path, 0o755)


# -- публичное API ---------------------------------------------------------

def create() -> bool:
    """Создаёт ярлык на текущий исполняемый файл. True — получилось."""
    path = shortcut_path()
    if not path:
        return False
    target = sys.executable
    if not target or not os.path.exists(target):
        return False
    icon = None
    if sys.platform == "win32":
        icon = target  # иконка вшита в exe
    try:
        if sys.platform == "win32":
            _create_windows(target, path, icon)
        else:
            _create_linux(target, path, icon)
        return os.path.exists(path)
    except Exception:
        return False


def remove() -> bool:
    path = shortcut_path()
    if not path:
        return False
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except OSError:
        return False


def ensure(enabled: bool) -> None:
    """Приводит состояние ярлыка в соответствие с настройкой."""
    if enabled:
        if not exists():
            create()
    elif exists():
        remove()
