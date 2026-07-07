"""Базовый интерфейс экранной лупы."""


class MagnifierBase:
    def __init__(self, config, notify=None):
        self.config = config
        self.active = False
        self.notify = notify or (lambda msg: None)

    def start(self) -> None:
        """Инициализация ресурсов при запуске приложения."""

    def shutdown(self) -> None:
        """Гарантированный возврат экрана к 100% и освобождение ресурсов."""

    def zoom_in(self) -> None:
        raise NotImplementedError

    def zoom_out(self, instant: bool = False) -> None:
        raise NotImplementedError

    def toggle(self) -> None:
        if self.active:
            self.zoom_out()
        else:
            self.zoom_in()


class NullMagnifier(MagnifierBase):
    """Заглушка для окружений без поддержки увеличения."""

    def zoom_in(self) -> None:
        self.notify(
            "Screen magnification is not supported in this environment.\n"
            "Supported: Windows, GNOME and KDE (Linux)."
        )

    def zoom_out(self, instant: bool = False) -> None:
        pass
