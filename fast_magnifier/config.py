"""Загрузка/сохранение настроек в JSON (кросс-платформенно)."""
import json
import os
import sys
from dataclasses import dataclass, field, asdict

from . import APP_ID

DEFAULT_BINDING = {"kind": "mouse", "key": "middle", "mods": []}


def config_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, APP_ID)
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "magnifysnap")


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


@dataclass
class Config:
    zoom_factor: float = 2.0        # кратность увеличения (2.0 = 200%)
    peek_factor: float = 4.0        # усиленный зум при удержании кнопки
    pan_speed: int = 5              # скорость перемещения экрана, 1..10
    edge_size: int = 60             # ширина зоны у края экрана (px), в которой начинается прокрутка
    smooth_zoom: bool = True        # плавная анимация увеличения
    autostart: bool = False         # автозапуск при входе в систему
    start_menu_shortcut: bool = True  # ярлык в меню «Пуск» / меню приложений
    auto_update_check: bool = True  # ежедневная проверка новых версий (GitHub)
    theme: str = "system"           # system | light | dark
    binding: dict = field(default_factory=lambda: dict(DEFAULT_BINDING))

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            with open(config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in asdict(cfg):
                if key in data:
                    setattr(cfg, key, data[key])
        except (OSError, ValueError):
            pass
        cfg.zoom_factor = min(8.0, max(1.25, float(cfg.zoom_factor)))
        cfg.peek_factor = min(8.0, max(1.5, float(cfg.peek_factor)))
        cfg.pan_speed = min(10, max(1, int(cfg.pan_speed)))
        cfg.edge_size = min(150, max(10, int(cfg.edge_size)))
        if cfg.theme not in ("system", "light", "dark"):
            cfg.theme = "system"
        return cfg

    def save(self) -> None:
        try:
            os.makedirs(config_dir(), exist_ok=True)
            with open(config_path(), "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except OSError:
            pass
