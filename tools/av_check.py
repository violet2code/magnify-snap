"""Предрелизная проверка сборки боевым Windows Defender.

Единственный надёжный барьер против ложных срабатываний: CI-раннеры
исключают рабочую папку из проверки, поэтому скан там ничего не значит.
Здесь файл копируется в неисключённую папку, ему ставится «метка
интернета» (именно с ней облачная эвристика строже всего — так и был
пойман Wacatac.B!ml в 1.3.0) и запускается настоящий скан.

    py tools/av_check.py dist/MagnifySnap.exe

Код возврата 0 — чисто, 1 — обнаружено, 2 — проверить не удалось.
"""
import os
import shutil
import subprocess
import sys
import tempfile

MPCMD = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     "Windows Defender", "MpCmdRun.exe")


def check(path: str) -> int:
    if sys.platform != "win32":
        print("не Windows — проверка пропущена")
        return 2
    if not os.path.exists(MPCMD):
        print("MpCmdRun.exe не найден — проверить нельзя")
        return 2

    work = tempfile.mkdtemp(prefix="avcheck-")
    probe = os.path.join(work, os.path.basename(path))
    try:
        shutil.copy2(path, probe)
    except OSError as exc:
        # копирование блокируется, когда файл уже под подозрением
        print(f"ОБНАРУЖЕНО: копирование заблокировано антивирусом ({exc})")
        return 1

    # метка интернета: облако проверяет такие файлы строже
    try:
        with open(probe + ":Zone.Identifier", "w", encoding="utf-8") as f:
            f.write("[ZoneTransfer]\nZoneId=3\n")
    except OSError:
        print("предупреждение: не удалось поставить метку интернета")

    out = subprocess.run([MPCMD, "-Scan", "-ScanType", "3", "-File", probe],
                         capture_output=True, text=True, timeout=600)
    text = (out.stdout or "") + (out.stderr or "")
    print(text.strip())

    survived = os.path.exists(probe)
    shutil.rmtree(work, ignore_errors=True)

    if "found no threats" in text and survived:
        print(f"ЧИСТО: {path}")
        return 0
    if not survived or "found" in text.lower():
        print(f"ОБНАРУЖЕНО — публиковать нельзя: {path}")
        return 1
    print("результат непонятен — проверить вручную")
    return 2


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "dist",
        "MagnifySnap.exe")
    sys.exit(check(os.path.abspath(target)))
