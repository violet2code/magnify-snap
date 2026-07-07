"""Глобальный перехват мыши и клавиатуры (pynput).

Задачи:
  * переключение лупы по назначенной кнопке/клавише/комбинации;
  * режим захвата: следующее нажатие становится новой привязкой (Esc — отмена);
  * на Windows назначенная кнопка мыши подавляется (не доходит до приложений),
    чтобы, например, средняя кнопка не срабатывала как «вставить»/автоскролл.
"""
import sys
import threading

from pynput import keyboard, mouse

from .binding import Binding

Key = keyboard.Key
KeyCode = keyboard.KeyCode

_MOD_MAP = {}
for _name, _mod in (
    ("ctrl", "ctrl"), ("ctrl_l", "ctrl"), ("ctrl_r", "ctrl"),
    ("alt", "alt"), ("alt_l", "alt"), ("alt_r", "alt"), ("alt_gr", "alt"),
    ("shift", "shift"), ("shift_l", "shift"), ("shift_r", "shift"),
    ("cmd", "super"), ("cmd_l", "super"), ("cmd_r", "super"),
):
    _key = getattr(Key, _name, None)
    if _key is not None:
        _MOD_MAP[_key] = _mod

# Windows low-level mouse hook messages
_WM_DOWN = {0x0201: "left", 0x0204: "right", 0x0207: "middle", 0x020B: "x"}
_WM_UP = {0x0202: "left", 0x0205: "right", 0x0208: "middle", 0x020C: "x"}


def key_name(key) -> str | None:
    """Стабильное имя клавиши, одинаковое при захвате и при проверке."""
    if isinstance(key, Key):
        return key.name
    ch = getattr(key, "char", None)
    if ch and ch.isprintable() and not ch.isspace():
        return ch.lower()
    vk = getattr(key, "vk", None)
    if vk is not None:
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:  # 0-9, A-Z
            return chr(vk).lower()
        return f"vk{vk}"
    return None


class GlobalInput:
    def __init__(self, binding: Binding, on_toggle):
        self._binding = binding
        self._on_toggle = on_toggle
        self._lock = threading.Lock()
        self._mods: set[str] = set()
        self._capture_cb = None
        self._suppress_up: set[str] = set()
        self._kb = None
        self._ms = None

    # -- API ------------------------------------------------------------

    def start(self) -> None:
        self._kb = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        if sys.platform == "win32":
            self._ms = mouse.Listener(win32_event_filter=self._win32_filter)
        else:
            self._ms = mouse.Listener(on_click=self._on_click)
        self._kb.start()
        self._ms.start()

    def stop(self) -> None:
        for listener in (self._kb, self._ms):
            if listener is not None:
                listener.stop()

    def set_binding(self, binding: Binding) -> None:
        with self._lock:
            self._binding = binding

    def start_capture(self, callback) -> None:
        """callback(binding | None, error_msg | None) — из потока слушателя."""
        with self._lock:
            self._capture_cb = callback

    def cancel_capture(self) -> None:
        with self._lock:
            self._capture_cb = None

    # -- обработка мыши ---------------------------------------------------

    def _consume_mouse(self, btn: str) -> bool:
        """True, если нажатие обработано (захват или переключение лупы)."""
        with self._lock:
            cb = self._capture_cb
            if cb is not None:
                self._capture_cb = None
                mods = sorted(self._mods)
                if btn in ("left", "right") and not mods:
                    cb(None, "Left/right button can only be bound together "
                            "with a modifier (Ctrl, Alt, Shift)")
                else:
                    cb(Binding("mouse", btn, mods), None)
                return True
            if self._binding.matches("mouse", btn, self._mods):
                toggle = self._on_toggle
            else:
                return False
        toggle()
        return True

    def _on_click(self, x, y, button, pressed) -> None:  # Linux/macOS
        if pressed:
            self._consume_mouse(button.name)

    def _win32_filter(self, msg, data) -> bool:
        """Низкоуровневый фильтр Windows: позволяет подавлять событие."""
        btn, pressed = None, None
        if msg in _WM_DOWN:
            btn, pressed = _WM_DOWN[msg], True
        elif msg in _WM_UP:
            btn, pressed = _WM_UP[msg], False
        if btn is None:
            return True
        if btn == "x":
            btn = "x1" if (data.mouseData >> 16) & 0xFFFF == 1 else "x2"

        if pressed:
            if self._consume_mouse(btn):
                self._suppress_up.add(btn)
                self._ms.suppress_event()
        elif btn in self._suppress_up:
            self._suppress_up.discard(btn)
            self._ms.suppress_event()
        return True

    # -- обработка клавиатуры ----------------------------------------------

    def _on_press(self, key) -> None:
        mod = _MOD_MAP.get(key)
        if mod is not None:
            self._mods.add(mod)
            return
        name = key_name(key)
        with self._lock:
            cb = self._capture_cb
            if cb is not None:
                self._capture_cb = None
                if key == Key.esc:
                    cb(None, None)  # отмена
                elif name is None:
                    cb(None, "Could not recognize that key, try another one")
                else:
                    cb(Binding("keyboard", name, sorted(self._mods)), None)
                return
            if name is not None and self._binding.matches(
                "keyboard", name, self._mods
            ):
                toggle = self._on_toggle
            else:
                return
        toggle()

    def _on_release(self, key) -> None:
        mod = _MOD_MAP.get(key)
        if mod is not None:
            self._mods.discard(mod)
