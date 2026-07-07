# Magnify.Snap ⚡🔍

Fast screen magnifier for **Windows** and **Linux**. Lives in the system
tray, toggles with a single middle-mouse click, and the screen stays
**fully interactive** — click, type and work as usual while zoomed in.

![logo](assets/logo.png)

## Features

- **Instant zoom** — press the middle mouse button (default) to magnify the
  screen to 200%; press again to snap back to 100%.
- **Cursor-follow panning** — while zoomed, the view glides smoothly when the
  cursor approaches a screen edge.
- **Fully interactive** — magnification happens at the OS compositor level
  (Windows Magnification API / GNOME magnifier / KWin Zoom), so the mouse and
  keyboard keep working normally.
- **Customizable activation** — any mouse button, key, or combination with
  Ctrl/Alt/Shift/Win. Assigned by physically pressing it.
- **Settings**: zoom level (125–800%), cursor follow speed, edge zone width,
  smooth animation, appearance (System/Light/Dark), start at sign-in.
- **Smooth animation** for zoom in/out.
- Follows the **system theme** by default; single instance; the screen is
  always restored to 100% even on abnormal exit.

## Usage

| Action | How |
|---|---|
| Toggle the magnifier | Middle mouse button (customizable) |
| Pan the view while zoomed | Move the cursor to a screen edge |
| Open settings | Click the tray icon → "Settings…" |
| Quit | Right-click the tray icon → "Quit" |

## Run from source

```bash
pip install -r requirements.txt
python main.py
```

## Build a standalone executable

**Windows** — run `build_windows.bat`; output: `dist\MagnifySnap.exe`
(single file, no console, with icon).

**Linux** — run `./build_linux.sh`; output: `dist/magnifysnap`.

Brand assets for the website are generated into `assets/`:
`logo.png` (transparent) and `logo.svg`.

## Platform notes

**Windows** — uses the system Magnification API
(`MagSetFullscreenTransform`): hardware fullscreen zoom; edge panning and the
smooth animation are computed by the app itself at 60 FPS. The bound mouse
button is suppressed so it doesn't leak into other applications (middle-click
won't trigger autoscroll while it is bound to the magnifier).

**Linux / GNOME** — drives the built-in GNOME magnifier via `gsettings`
(tracking mode `push` — the view moves at the edge, exactly as required).

**Linux / KDE Plasma** — drives the KWin "Zoom" effect via `qdbus`
(the effect must be enabled in system settings).

**Wayland** — global mouse/keyboard capture is restricted by the Wayland
protocol itself; full support is guaranteed on X11. On GNOME Wayland the
built-in `Super+Alt+8` magnifier shortcut is available.

Linux system packages: `python3-tk`; the tray icon on GNOME may require the
AppIndicator extension (`gir1.2-ayatanaappindicator3`).

## Project layout

```
main.py                      — entry point, DPI awareness, single instance
fast_magnifier/
  config.py                  — settings (JSON in %APPDATA% / ~/.config)
  binding.py                 — activation binding model
  input_hook.py              — global mouse/keyboard hooks (pynput)
  magnifier_windows.py       — Windows magnifier (Magnification API, ctypes)
  magnifier_linux.py         — GNOME (gsettings) and KDE (qdbus) magnifiers
  tray_icon.py               — tray icon and menu (pystray)
  settings_ui.py             — settings window (customtkinter)
  icons.py                   — all artwork drawn in code (Pillow)
  autostart.py               — start at sign-in (registry / autostart .desktop)
```
