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

# Windows low-level keyboard hook messages
_WM_KEYDOWN = (0x0100, 0x0104)  # WM_KEYDOWN, WM_SYSKEYDOWN
_WM_KEYUP = (0x0101, 0x0105)    # WM_KEYUP, WM_SYSKEYUP

# vk-коды модификаторов — их никогда не подавляем (сломались бы во всей ОС)
_MOD_VKS = {0x10, 0xA0, 0xA1,   # Shift
            0x11, 0xA2, 0xA3,   # Ctrl
            0x12, 0xA4, 0xA5,   # Alt
            0x5B, 0x5C}         # Win


def key_vk(key) -> int | None:
    """Виртуальный код клавиши pynput (Windows)."""
    vk = getattr(key, "vk", None)
    if vk is None:
        inner = getattr(key, "value", None)
        vk = getattr(inner, "vk", None)
    return vk


def vk_from_name(name: str) -> int | None:
    """Восстановление vk по имени — для привязок из старых конфигов без vk."""
    if len(name) == 1:
        ch = name.upper()
        if "0" <= ch <= "9" or "A" <= ch <= "Z":
            return ord(ch)
    special = getattr(Key, name, None)
    if special is not None:
        return key_vk(special)
    if name.startswith("vk") and name[2:].isdigit():
        return int(name[2:])
    return None


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
    """on_bound(pressed: bool) вызывается при нажатии/отпускании привязки —
    поверх этого приложение строит логику «клик» против «удержание»."""

    def __init__(self, binding: Binding, on_bound):
        self._binding = binding
        self._on_bound = on_bound
        self._lock = threading.Lock()
        self._mods: set[str] = set()
        self._capture_cb = None
        self._capture_hint = None
        self._suppress_up: set[str] = set()
        self._held_vk: int | None = None    # зажатая назначенная клавиша (win)
        self._bound_btn: str | None = None  # зажатая назначенная кнопка мыши
        self._bound_key_down = False        # зажатая клавиша (не-win путь)
        self._kb = None
        self._ms = None
        self._ensure_vk(binding)

    @staticmethod
    def _ensure_vk(binding: Binding) -> None:
        if (sys.platform == "win32" and binding.kind == "keyboard"
                and binding.vk is None):
            binding.vk = vk_from_name(binding.key)

    # -- API ------------------------------------------------------------

    def start(self) -> None:
        if sys.platform == "win32":
            self._kb = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release,
                win32_event_filter=self._kb_filter,
            )
            self._ms = mouse.Listener(win32_event_filter=self._win32_filter)
        else:
            self._kb = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release
            )
            self._ms = mouse.Listener(on_click=self._on_click)
        self._kb.start()
        self._ms.start()

    def stop(self) -> None:
        for listener in (self._kb, self._ms):
            if listener is not None:
                listener.stop()

    def set_binding(self, binding: Binding) -> None:
        self._ensure_vk(binding)
        with self._lock:
            self._binding = binding

    def start_capture(self, callback, hint=None) -> None:
        """callback(binding | None, error_msg | None) — из потока слушателя.

        hint() вызывается, когда пользователь отпустил модификаторы,
        не нажав основную клавишу (попытка назначить «только модификаторы»).
        """
        with self._lock:
            self._capture_cb = callback
            self._capture_hint = hint

    def cancel_capture(self) -> None:
        with self._lock:
            self._capture_cb = None
            self._capture_hint = None

    # -- обработка мыши ---------------------------------------------------

    def _consume_mouse(self, btn: str) -> str | None:
        """'capture' | 'bound' | None — что произошло с нажатием."""
        with self._lock:
            cb = self._capture_cb
            if cb is not None:
                self._capture_cb = None
                self._capture_hint = None
                mods = sorted(self._mods)
                if btn in ("left", "right") and not mods:
                    cb(None, "Left/right button can only be bound together "
                            "with a modifier (Ctrl, Alt, Shift)")
                else:
                    cb(Binding("mouse", btn, mods), None)
                return "capture"
            if self._binding.matches("mouse", btn, self._mods):
                bound_cb = self._on_bound
            else:
                return None
        bound_cb(True)
        return "bound"

    def _on_click(self, x, y, button, pressed) -> None:  # Linux/macOS
        btn = button.name
        if pressed:
            if self._consume_mouse(btn) == "bound":
                self._bound_btn = btn
        elif btn == self._bound_btn:
            self._bound_btn = None
            self._on_bound(False)

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
            result = self._consume_mouse(btn)
            if result is not None:
                if result == "bound":
                    self._bound_btn = btn
                self._suppress_up.add(btn)
                self._ms.suppress_event()
        elif btn in self._suppress_up:
            self._suppress_up.discard(btn)
            if btn == self._bound_btn:
                self._bound_btn = None
                self._on_bound(False)
            self._ms.suppress_event()
        return True

    # -- обработка клавиатуры ----------------------------------------------

    def _kb_filter(self, msg, data) -> bool:
        """Низкоуровневый фильтр Windows: подавляет назначенную комбинацию,
        чтобы она не «просачивалась» в активное приложение (например,
        Ctrl+Z не делал отмену в текстовом поле)."""
        vk = data.vkCode
        if vk in _MOD_VKS:
            return True  # модификаторы всегда проходят
        if msg in _WM_KEYDOWN:
            fire = False
            consume = False
            with self._lock:
                b = self._binding
                if (self._capture_cb is None
                        and b.kind == "keyboard" and b.vk is not None
                        and vk == b.vk and set(self._mods) == set(b.mods)):
                    consume = True
                    if self._held_vk is None:  # защита от автоповтора
                        self._held_vk = vk
                        fire = True
            if consume:
                if fire:
                    self._on_bound(True)
                self._kb.suppress_event()
        elif msg in _WM_KEYUP:
            if self._held_vk == vk:
                self._held_vk = None
                self._on_bound(False)
                self._kb.suppress_event()
        return True

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
                self._capture_hint = None
                if key == Key.esc:
                    cb(None, None)  # отмена
                elif name is None:
                    cb(None, "Could not recognize that key, try another one")
                else:
                    cb(Binding("keyboard", name, sorted(self._mods),
                               key_vk(key)), None)
                return
            if name is not None and self._binding.matches(
                "keyboard", name, self._mods
            ):
                if sys.platform == "win32" and self._binding.vk is not None:
                    return  # нажатие/отпускание делает низкоуровневый фильтр
                if self._bound_key_down:
                    return  # автоповтор на X11
                self._bound_key_down = True
                bound_cb = self._on_bound
            else:
                return
        bound_cb(True)

    def _on_release(self, key) -> None:
        mod = _MOD_MAP.get(key)
        if mod is not None:
            self._mods.discard(mod)
            hint = None
            with self._lock:
                if self._capture_cb is not None:
                    hint = self._capture_hint
            if hint is not None:
                hint()
            return
        if self._bound_key_down and key_name(key) == self._binding.key:
            self._bound_key_down = False
            self._on_bound(False)
