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

_ASSET_SUFFIX = "-windows-x64.exe" if sys.platform == "win32" else "-linux-x64.tar.gz"


def parse_version(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3]) or (0,)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def managed_install() -> str | None:
    """'winget', если exe живёт в папке WinGet — тогда обновляет он, не мы."""
    exe = (sys.executable or "").lower()
    if sys.platform == "win32" and f"{os.sep}winget{os.sep}".lower() in exe:
        return "winget"
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
    for asset in data.get("assets", []):
        if asset.get("name", "").endswith(_ASSET_SUFFIX):
            digest = asset.get("digest") or ""
            return {
                "version": version,
                "url": asset["browser_download_url"],
                "sha256": digest.removeprefix("sha256:").lower() or None,
                "newer": parse_version(version) > parse_version(VERSION),
            }
    return None


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

    if sys.platform != "win32":
        downloaded = _extract_linux_binary(downloaded)
        os.replace(downloaded, exe)  # на Linux можно поверх работающего
        os.chmod(exe, 0o755)
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
    for attempt in range(60):  # файл освобождается не мгновенно
        try:
            shutil.copy2(source, target)
            break
        except OSError:
            time.sleep(1.0)
    else:
        return 1

    subprocess.Popen(
        [target, CLEANUP_FLAG, source],
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP,
        cwd=os.path.dirname(target) or None,
    )
    return 0


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
