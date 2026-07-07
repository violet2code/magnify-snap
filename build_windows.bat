@echo off
rem Build Magnify.Snap for Windows (single windowed exe)
cd /d "%~dp0"

py -m pip install --upgrade -r requirements.txt pyinstaller || goto :error
py tools\make_icon.py || goto :error

py -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name MagnifySnap ^
    --icon assets\icon.ico ^
    --collect-all customtkinter ^
    main.py || goto :error

echo.
echo Done: dist\MagnifySnap.exe
exit /b 0

:error
echo Build failed.
exit /b 1
