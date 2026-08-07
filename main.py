"""Magnify.Snap — fast screen magnifier.

Run: python main.py
The app minimizes straight to the system tray. The middle mouse button
(default) toggles screen magnification on and off.
"""
import atexit
import ctypes
import os
import socket
import sys
import threading

SINGLE_INSTANCE_PORT = int(os.environ.get("MAGNIFYSNAP_PORT", 47653))
HOLD_PEEK_DELAY = 0.30  # сек: дольше — «подглядывание», короче — обычный клик
UPDATE_CHECK_DELAY = 12          # сек после запуска
UPDATE_CHECK_INTERVAL = 86400    # раз в сутки


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

        # обновления
        self.lock_socket = None          # single-instance порт (закрыть перед релончем)
        self.update_info = None          # {'version', 'url', 'sha256'} если есть новее
        self._update_notified = None
        self._updating = False

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

    # -- обновления ---------------------------------------------------------

    def start_update_checks(self) -> None:
        from fast_magnifier import updater
        if not self.cfg.auto_update_check or not updater.is_frozen():
            return
        delay = UPDATE_CHECK_DELAY
        if os.environ.get("MAGNIFYSNAP_UPDATE_API"):  # тестовый режим
            delay = 2

        def loop():
            self.check_updates()
            timer = threading.Timer(UPDATE_CHECK_INTERVAL, loop)
            timer.daemon = True
            timer.start()

        timer = threading.Timer(delay, loop)
        timer.daemon = True
        timer.start()

    def check_updates(self, on_result=None) -> None:
        """Фоновая проверка; on_result(info|None|Exception) — для окна настроек."""
        from fast_magnifier import updater

        def work():
            try:
                info = updater.check_latest()
            except Exception as exc:
                if on_result:
                    on_result(exc)
                return
            if info and info["newer"]:
                self.update_info = info
                label = f"Update to v{info['version']}…"
                self.tray.set_update(label, self.do_update)
                if self._update_notified != info["version"]:
                    self._update_notified = info["version"]
                    self.tray.notify(
                        f"Version {info['version']} is available — "
                        "update from the tray menu or settings"
                    )
                if os.environ.get("MAGNIFYSNAP_AUTOTEST_UPDATE") == "1":
                    self.do_update()  # только для автотестов
            if on_result:
                on_result(self.update_info)

        threading.Thread(target=work, daemon=True).start()

    def do_update(self) -> None:
        """Скачать, проверить, заменить себя и перезапуститься."""
        from fast_magnifier import updater
        if self._updating or self.update_info is None:
            return
        self._updating = True

        def work():
            info = self.update_info
            path = None
            try:
                managed = updater.managed_install()
                if managed:
                    self.tray.notify(
                        f"This copy is managed by {managed} — run: "
                        f"{managed} upgrade magnifysnap"
                    )
                    return
                if not info.get("sha256"):
                    # без отпечатка нечем подтвердить целостность скачанного
                    self.tray.notify(
                        "Update skipped: the release has no checksum to "
                        "verify. Download it from violet2code.github.io"
                    )
                    return
                self.tray.notify(f"Downloading version {info['version']}…")
                path = updater.download_verified(info["url"], info["sha256"])
                # помощник дождётся нашего полного завершения и подменит файл;
                # нам остаётся штатно выйти
                updater.apply_update(path)
                self.request_quit()
            except Exception as exc:
                if path:  # не оставляем 20 МБ мусора после неудачи
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                self.tray.notify(f"Update failed: {exc}")
                self._updating = False

        threading.Thread(target=work, daemon=True).start()

    # -- запуск/остановка ----------------------------------------------------

    def _heartbeat(self) -> None:
        """Регулярно будит tk-цикл: без этого root.after из других потоков
        (ui_call, request_quit) может ждать события от пользователя вечно."""
        self.root.after(200, self._heartbeat)

    def _ensure_shortcut(self) -> None:
        """Ярлык в «Пуске»: без него установленное через winget приложение
        попросту негде найти — оно живёт в служебной папке без ярлыков."""
        from fast_magnifier import shortcut, updater
        if not updater.is_frozen():
            return  # из исходников ярлык вёл бы на интерпретатор
        try:
            shortcut.ensure(self.cfg.start_menu_shortcut)
        except Exception:
            pass

    def run(self) -> None:
        atexit.register(self._cleanup)
        self.input.start()
        self.tray.run()
        threading.Thread(target=self._ensure_shortcut, daemon=True).start()
        self.start_update_checks()
        self.root.after(200, self._heartbeat)
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
    from fast_magnifier import updater

    # служебные режимы самообновления — до всякой инициализации UI
    if len(sys.argv) > 1 and sys.argv[1] == updater.FINISH_FLAG:
        return updater.run_finish_update(sys.argv[2:])
    cleanup_path = None
    if len(sys.argv) > 2 and sys.argv[1] == updater.CLEANUP_FLAG:
        cleanup_path = sys.argv[2]

    set_dpi_aware()
    lock = acquire_single_instance()
    if lock is None:
        try:
            print("Magnify.Snap is already running.")
        except OSError:
            pass
        return 1
    if cleanup_path:
        updater.cleanup_temp_copy(cleanup_path)
    app = FastMagnifierApp()
    app.lock_socket = lock
    app.run()
    try:
        lock.close()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
