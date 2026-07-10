"""Binding model: mouse button / key / combination with modifiers."""

MOD_ORDER = ("ctrl", "alt", "shift", "super")

MOD_NAMES = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "super": "Win",
}

MOUSE_NAMES = {
    "left": "Left mouse button",
    "right": "Right mouse button",
    "middle": "Middle mouse button",
    "x1": "Side button X1",
    "x2": "Side button X2",
    "button8": "Side button X1",
    "button9": "Side button X2",
}

KEY_NAMES = {
    "space": "Space",
    "enter": "Enter",
    "tab": "Tab",
    "caps_lock": "CapsLock",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "page_up": "PageUp",
    "page_down": "PageDown",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "print_screen": "PrtScr",
    "scroll_lock": "ScrollLock",
    "pause": "Pause",
    "menu": "Menu",
    "num_lock": "NumLock",
    "esc": "Esc",
}


class Binding:
    """kind: 'mouse' | 'keyboard'; key: button/key name; mods: sorted modifiers.

    vk — виртуальный код клавиши (Windows), нужен низкоуровневому фильтру,
    чтобы подавлять назначенную комбинацию до того, как её увидят приложения.
    """

    def __init__(self, kind: str, key: str, mods=(), vk: int | None = None):
        self.kind = kind
        self.key = key
        self.mods = tuple(sorted(set(mods), key=MOD_ORDER.index))
        self.vk = vk

    def matches(self, kind: str, key: str, mods) -> bool:
        return (
            self.kind == kind
            and self.key == key
            and set(self.mods) == set(mods)
        )

    def display(self) -> str:
        parts = [MOD_NAMES[m] for m in self.mods]
        if self.kind == "mouse":
            parts.append(MOUSE_NAMES.get(self.key, f"Mouse button '{self.key}'"))
        else:
            name = KEY_NAMES.get(self.key)
            if name is None:
                name = self.key.upper() if len(self.key) <= 3 else self.key.capitalize()
            parts.append(name)
        return " + ".join(parts)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "key": self.key, "mods": list(self.mods),
                "vk": self.vk}

    @classmethod
    def from_dict(cls, data: dict) -> "Binding":
        try:
            mods = [m for m in data.get("mods", []) if m in MOD_ORDER]
            vk = data.get("vk")
            return cls(data["kind"], data["key"], mods,
                       vk if isinstance(vk, int) else None)
        except (KeyError, TypeError):
            return cls("mouse", "middle")
