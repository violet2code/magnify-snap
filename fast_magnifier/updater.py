"""Проверка обновлений и самообновление по кнопке.

Источник — GitHub Releases. Проверка: один анонимный HTTPS-запрос к API
(без каких-либо данных о пользователе), скачанный файл сверяется с
SHA256-отпечатком из API. Самозамена на Windows — через переименование
работающего exe (перезаписать его нельзя, а переименовать можно).

Переменные окружения (только для тестов):
  MAGNIFYSNAP_UPDATE_API — подменить URL API релизов.
"""
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


_PS_TEMPLATE = r"""
$exe  = '{exe}'
$new  = '{new}'
$pids = @({pids})
foreach ($p in $pids) {{
    try {{ Wait-Process -Id $p -Timeout 90 -ErrorAction SilentlyContinue }} catch {{}}
}}
$ok = $false
for ($i = 0; $i -lt 60; $i++) {{
    try {{ Move-Item -LiteralPath $new -Destination $exe -Force -ErrorAction Stop; $ok = $true; break }}
    catch {{ Start-Sleep -Seconds 1 }}
}}
if ($ok) {{
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe)
}}
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""


def apply_update(downloaded: str) -> None:
    """Готовит замену исполняемого файла и запуск новой версии.

    Windows: переписать или переименовать exe работающего onefile-приложения
    нельзя (его держит процесс-загрузчик PyInstaller), поэтому запускается
    скрытый PowerShell-помощник: он ждёт полного завершения обоих процессов
    (python + загрузчик), подменяет уже незапертый файл, стартует новую
    версию и удаляет сам себя. Вызывающий после этого штатно завершает
    приложение. До завершения старый exe остаётся нетронутым.

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

    pids = {os.getpid()}
    try:
        pids.add(os.getppid())  # загрузчик PyInstaller
    except OSError:
        pass
    script = _PS_TEMPLATE.format(
        exe=exe.replace("'", "''"),
        new=downloaded.replace("'", "''"),
        pids=", ".join(str(p) for p in sorted(pids)),
    )
    fd, ps1 = tempfile.mkstemp(prefix="magnifysnap-swap-", suffix=".ps1")
    with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
        f.write(script)
    # ВАЖНО: DETACHED_PROCESS сюда добавлять нельзя — он конфликтует с
    # CREATE_NO_WINDOW, и консольный powershell мгновенно умирает
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", ps1],
        close_fds=True, creationflags=flags,
    )
