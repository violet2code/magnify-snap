"""Magnify.Snap — fast screen magnifier.

Run: python main.py
The app minimizes straight to the system tray. The middle mouse button
(default) toggles screen magnification on and off.
"""
import atexit
import ctypes
import socket
import sys
import threading

SINGLE_INSTANCE_PORT = 47653
HOLD_PEEK_DELAY = 0.30  # сек: дольше — «подглядывание», короче — обычный клик


def set_dpi_aware() -> None:
    """Работаем в физических пикселях — критично для Magnification API."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except (OSError, AttributeError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (OSError, AttributeError):
            pass


def acquire_single_instance():
    """Не даём запустить второй экземпляр (иначе конфликт хуков и лупы)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", SINGLE_INSTANCE_PORT))
        sock.listen(1)
        return sock
    except OSError:
        return None


class FastMagnifierApp:
    def __init__(self):
        import customtkinter as ctk

        from fast_magnifier import APP_NAME
        from fast_magnifier.binding import Binding
        from fast_magnifier.config import Config
        from fast_magnifier.input_hook import GlobalInput
        from fast_magnifier.tray_icon import Tray

        self.cfg = Config.load()
        self.binding = Binding.from_dict(self.cfg.binding)

        ctk.set_appearance_mode(self.cfg.theme)  # system | light | dark
        ctk.set_default_color_theme("blue")
        self.root = ctk.CTk()
        self.root.title(APP_NAME)
        self.root.withdraw()  # окна при запуске нет — только трей

        self.tray = Tray(
            on_toggle=self.on_toggle,
            on_settings=self.open_settings,
            on_exit=self.request_quit,
            is_active=lambda: self.magnifier.active,
        )
        self.magnifier = self._create_magnifier()
        self.input = GlobalInput(self.binding, self.on_bound)

        # состояние «клик против удержания»
        self._hold_lock = threading.Lock()
        self._pressed = False
        self._entered_on_press = False
        self._peeking = False
        self._hold_timer = None

    def _create_magnifier(self):
        from fast_magnifier.magnifier_base import NullMagnifier

        notify = self.tray.notify
        try:
            if sys.platform == "win32":
                from fast_magnifier.magnifier_windows import WindowsMagnifier
                mag = WindowsMagnifier(self.cfg, notify)
            else:
                from fast_magnifier.magnifier_linux import create_linux_magnifier
                mag = create_linux_magnifier(self.cfg, notify)
            mag.start()
            return mag
        except Exception:
            return NullMagnifier(self.cfg, notify)

    # -- события (могут приходить из потоков хуков/трея) -------------------

    def ui_call(self, fn) -> None:
        try:
            self.root.after(0, fn)
        except RuntimeError:
            pass

    def on_toggle(self) -> None:
        """Простое переключение — используется пунктом меню в трее."""
        self.magnifier.toggle()
        self.tray.set_active(self.magnifier.active)

    def on_bound(self, pressed: bool) -> None:
        """Нажатие/отпускание привязанной кнопки.

        Короткий клик: включить лупу / выключить, как обычно.
        Удержание (> HOLD_PEEK_DELAY): временно усилить зум до peek_factor,
        отпускание возвращает обычный масштаб (лупа остаётся включённой).
        """
        with self._hold_lock:
            if pressed:
                if self._pressed:
                    return  # автоповтор клавиатуры
                self._pressed = True
                self._peeking = False
                self._entered_on_press = not self.magnifier.active
                if self._entered_on_press:
                    self.magnifier.zoom_in()  # мгновенно, как раньше
                self._hold_timer = threading.Timer(
                    HOLD_PEEK_DELAY, self._begin_peek
                )
                self._hold_timer.daemon = True
                self._hold_timer.start()
            else:
                if not self._pressed:
                    return
                self._pressed = False
                if self._hold_timer is not None:
                    self._hold_timer.cancel()
                    self._hold_timer = None
                if self._peeking:
                    self._peeking = False
                    self.magnifier.set_boost(None)  # осесть на обычный зум
                elif not self._entered_on_press:
                    self.magnifier.zoom_out()  # быстрый клик при активной лупе
        self.tray.set_active(self.magnifier.active)

    def _begin_peek(self) -> None:
        with self._hold_lock:
            if not self._pressed or not self.magnifier.active:
                return
            self._peeking = True
            peek = max(float(self.cfg.peek_factor),
                       float(self.cfg.zoom_factor))
            self.magnifier.set_boost(peek)

    def open_settings(self) -> None:
        def _open():
            from fast_magnifier.settings_ui import SettingsWindow
            SettingsWindow.show(self)
        self.ui_call(_open)

    def apply_binding(self, binding) -> None:
        self.binding = binding
        self.cfg.binding = binding.to_dict()
        self.cfg.save()
        self.input.set_binding(binding)

    def request_quit(self) -> None:
        self.ui_call(self.root.quit)

    # -- запуск/остановка ----------------------------------------------------

    def run(self) -> None:
        atexit.register(self._cleanup)
        self.input.start()
        self.tray.run()
        try:
            self.root.mainloop()
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        atexit.unregister(self._cleanup)
        try:
            self.input.stop()
        except Exception:
            pass
        try:
            self.magnifier.shutdown()  # гарантированно возвращаем 100%
        except Exception:
            pass
        self.tray.stop()


def main() -> int:
    set_dpi_aware()
    lock = acquire_single_instance()
    if lock is None:
        try:
            print("Magnify.Snap is already running.")
        except OSError:
            pass
        return 1
    app = FastMagnifierApp()
    app.run()
    lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
