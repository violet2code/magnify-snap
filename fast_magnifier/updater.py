"""Проверка обновлений и самообновление по кнопке.

Источник — GitHub Releases. Проверка: один анонимный HTTPS-запрос к API
(без каких-либо данных о пользователе), скачанный файл сверяется с
SHA256-отпечатком из API. Самозамена на Windows — через переименование
работающего exe (перезаписать его нельзя, а переименовать можно).

Переменные окружения (только для тестов):
  MAGNIFYSNAP_UPDATE_API — подменить URL API релизов.
"""
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

from . import VERSION

API_LATEST = os.environ.get(
    "MAGNIFYSNAP_UPDATE_API",
    "https://api.github.com/repos/violet2code/magnify-snap/releases/latest",
)

_PORTABLE_SUFFIX = ("-windows-x64.exe" if sys.platform == "win32"
                    else "-linux-x64.tar.gz")
_SETUP_SUFFIX = "-windows-x64-setup.exe"


def installed_by_setup() -> bool:
    """True, если программу поставил наш установщик (рядом лежит деинсталлятор).

    Такую копию нельзя обновлять подменой файла: в реестре останется старый
    номер версии, и winget будет считать, что обновление не состоялось.
    Вместо этого запускаем новый установщик — он обновит и файл, и запись.
    """
    if sys.platform != "win32" or not is_frozen():
        return False
    folder = os.path.dirname(sys.executable or "")
    return bool(folder) and os.path.exists(
        os.path.join(folder, "unins000.exe"))


def _asset_suffix() -> str:
    return _SETUP_SUFFIX if installed_by_setup() else _PORTABLE_SUFFIX


def parse_version(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3]) or (0,)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def managed_install() -> str | None:
    """Имя пакетного менеджера, если приложение установлено им.

    Такие копии обновляет менеджер: подменять файл самим — значит рассинхронить
    его учёт версий (и обновление откатится при следующем `upgrade`).
    """
    exe = (sys.executable or "").lower()
    sep = os.sep.lower()
    if sys.platform != "win32":
        return None
    if f"{sep}winget{sep}" in exe or f"{sep}winget packages{sep}" in exe:
        return "winget"
    if f"{sep}scoop{sep}apps{sep}" in exe:
        return "scoop"
    if f"{sep}chocolatey{sep}" in exe:
        return "chocolatey"
    return None


def check_latest(timeout: float = 15.0) -> dict | None:
    """Описание последнего релиза или None, если подходящего файла нет."""
    req = urllib.request.Request(API_LATEST, headers={
        "User-Agent": "MagnifySnap-Updater",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    version = str(data.get("tag_name", "")).lstrip("vV")
    suffix = _asset_suffix()
    for asset in data.get("assets", []):
        if asset.get("name", "").endswith(suffix):
            digest = asset.get("digest") or ""
            return {
                "version": version,
                "url": asset["browser_download_url"],
                "sha256": digest.removeprefix("sha256:").lower() or None,
                "newer": parse_version(version) > parse_version(VERSION),
            }
    return None


def _replace_atomically(source: str, target: str) -> None:
    """Ставит source на место target без окна «файл уже испорчен».

    Копия сначала пишется рядом с целью (тот же том — os.replace атомарен
    и не спотыкается о EXDEV, когда временная папка на другом разделе),
    и только потом одним движением занимает место цели.
    """
    staging = target + ".new"
    try:
        shutil.copy2(source, staging)
        if sys.platform != "win32":
            os.chmod(staging, 0o755)
        os.replace(staging, target)
    except BaseException:
        try:
            if os.path.exists(staging):
                os.remove(staging)
        except OSError:
            pass
        raise


def download_verified(url: str, sha256: str | None, timeout: float = 60.0) -> str:
    """Скачивает файл во временную папку и сверяет отпечаток."""
    fd, path = tempfile.mkstemp(prefix="magnifysnap-update-")
    digest = hashlib.sha256()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MagnifySnap-Updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, \
                os.fdopen(fd, "wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                digest.update(chunk)
                out.write(chunk)
        if sha256 and digest.hexdigest().lower() != sha256:
            raise ValueError("checksum mismatch — download discarded")
        return path
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise


def _extract_linux_binary(tar_path: str) -> str:
    """Достаёт бинарник magnifysnap из tar.gz во временный файл."""
    out = tar_path + ".bin"
    with tarfile.open(tar_path, "r:gz") as tar:
        member = tar.getmember("magnifysnap")
        src = tar.extractfile(member)
        with open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.chmod(out, 0o755)
    os.remove(tar_path)
    return out


FINISH_FLAG = "--finish-update"   # <target-exe> <pid> [pid…]
CLEANUP_FLAG = "--cleanup-update"  # <temp-exe>


def apply_update(downloaded: str) -> None:
    """Запускает замену исполняемого файла новой версией.

    Windows: перезаписать exe работающего onefile-приложения нельзя (файл
    держит процесс-загрузчик PyInstaller). Поэтому эстафету принимает сама
    СКАЧАННАЯ КОПИЯ: она запускается с флагом --finish-update, дожидается
    завершения старых процессов, копирует себя на их место и стартует
    обновлённое приложение. Никаких сторонних интерпретаторов и временных
    скриптов — только наш собственный подписанный тем же способом файл
    (скрытый PowerShell в этой роли антивирусы принимают за дроппер).

    Linux: работающий бинарник заменяется напрямую (inode остаётся у
    процесса), новая копия запускается сразу.
    """
    if not is_frozen():
        raise RuntimeError("running from source — self-update is disabled")
    exe = sys.executable

    if installed_by_setup():
        # обновляемся своим же установщиком: он закроет работающую копию,
        # заменит файл, обновит запись в реестре и поднимет программу снова
        subprocess.Popen(
            [downloaded, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
             "/AUTOLAUNCH=1"],
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW
            | subprocess.CREATE_NEW_PROCESS_GROUP,
            cwd=os.path.dirname(downloaded) or None,
        )
        return

    if sys.platform != "win32":
        binary = _extract_linux_binary(downloaded)
        try:
            _replace_atomically(binary, exe)
        finally:
            try:
                os.remove(binary)
            except OSError:
                pass
        subprocess.Popen([exe], close_fds=True,
                         cwd=os.path.dirname(exe) or None)
        return

    pids = [os.getpid()]
    try:
        ppid = os.getppid()  # загрузчик PyInstaller держит файл до конца
        if ppid and ppid != pids[0]:
            pids.append(ppid)
    except OSError:
        pass
    subprocess.Popen(
        [downloaded, FINISH_FLAG, exe, *(str(p) for p in pids)],
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP,
        cwd=os.path.dirname(downloaded) or None,
    )


def _wait_for_exit(pids, timeout: float = 90.0) -> None:
    """Ждёт завершения процессов по pid (без сторонних библиотек)."""
    import time
    if sys.platform != "win32":
        return
    SYNCHRONIZE = 0x00100000
    k32 = ctypes.windll.kernel32
    deadline = time.monotonic() + timeout
    for pid in pids:
        handle = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not handle:
            continue  # процесса уже нет
        try:
            left = max(0, deadline - time.monotonic())
            k32.WaitForSingleObject(handle, int(left * 1000))
        finally:
            k32.CloseHandle(handle)


def run_finish_update(argv) -> int:
    """Режим --finish-update: мы — скачанная копия, ставим себя на место.

    argv: [target_exe, pid, …]. Возвращает код выхода процесса.
    """
    import time
    if len(argv) < 1:
        return 2
    target = argv[0]
    pids = [p for p in argv[1:] if p.isdigit()]
    source = sys.executable

    _wait_for_exit(pids)
    replaced = False
    for _ in range(60):  # файл освобождается не мгновенно
        try:
            _replace_atomically(source, target)
            replaced = True
            break
        except OSError:
            time.sleep(1.0)

    if not replaced:
        # обновиться не вышло (нет прав, диск полон) — но старое приложение
        # цело: возвращаем пользователю рабочую программу, а не пустоту
        try:
            subprocess.Popen(
                [target], close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW
                | subprocess.CREATE_NEW_PROCESS_GROUP,
                cwd=os.path.dirname(target) or None,
            )
        except OSError:
            pass
        _notify_update_failed(target)
        return 1

    subprocess.Popen(
        [target, CLEANUP_FLAG, source],
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP,
        cwd=os.path.dirname(target) or None,
    )
    return 0


def _notify_update_failed(target: str) -> None:
    """Сообщает о неудаче: молчаливое исчезновение хуже любой ошибки."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "Magnify.Snap could not replace its own file "
            f"({target}).\n\nThe previous version keeps working. "
            "If the app is installed in a system folder, download the new "
            "version from violet2code.github.io instead.",
            "Magnify.Snap — update failed",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass


def cleanup_temp_copy(path: str) -> None:
    """Удаляет временную копию, из которой мы только что обновились."""
    import threading
    import time

    def work():
        for _ in range(60):
            try:
                if not os.path.exists(path):
                    return
                os.remove(path)
                return
            except OSError:
                time.sleep(1.0)

    threading.Thread(target=work, daemon=True).start()
