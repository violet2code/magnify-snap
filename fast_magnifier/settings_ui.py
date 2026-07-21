"""Settings window — customtkinter, follows the system theme, branded header.

Горизонтальная двухколоночная компоновка: помещается на любой экран
по вертикали, отступы просторные, подсказки на месте.
"""
import sys

import customtkinter as ctk

from . import APP_NAME, VERSION
from . import autostart, icons
from .binding import Binding

BLUE = "#4f8dfd"
BLUE_HOVER = "#3a76e0"
GREEN = "#2fbe83"
GREEN_HOVER = "#27a06e"
CARD = ("#eef1f7", "#23262e")
TEXT_DIM = ("#5c6470", "#9aa3b2")
WARN_RED = "#e5484d"
AMBER = "#e8a33d"

FONT = "Segoe UI" if sys.platform == "win32" else "Ubuntu"
THEME_VALUES = {"System": "system", "Light": "light", "Dark": "dark"}

BIND_HINT = "One press zooms in, another zooms back out"
PEEK_HINT = "Hold the button to zoom in closer, release to settle back"
PEEK_WARN = "Peek level is not above the zoom level — holding won't zoom further"


class SettingsWindow(ctk.CTkToplevel):
    _instance = None

    @classmethod
    def show(cls, app) -> None:
        if cls._instance is not None and cls._instance.winfo_exists():
            cls._instance.deiconify()
            cls._instance.lift()
            cls._instance.focus_force()
            return
        cls._instance = cls(app)

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.cfg = app.cfg
        self._save_job = None
        self._capturing = False

        self.title(f"{APP_NAME} — Settings")
        self.geometry(self._fit_geometry())
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(180, self._set_window_icon)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(12, 4))

        self._build_header(body)

        cols = ctk.CTkFrame(body, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._build_zoom_card(left)
        self._build_binding_card(left)
        self._build_pan_card(right)
        self._build_misc_card(right)
        self._build_footer()
        self._refresh_peek_state()

        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _fit_geometry(self) -> str:
        """Широкое невысокое окно по центру рабочей области."""
        try:
            scale = self._get_window_scaling()
        except Exception:
            scale = 1.0
        width, height = 880, 515
        try:
            sw = int(self.winfo_screenwidth() / scale)
            sh = int(self.winfo_screenheight() / scale)
            width = min(width, sw - 40)
            height = min(height, sh - 80)
            x = max(0, (sw - width) // 2)
            y = max(0, (sh - height) // 3)
            return f"{width}x{height}+{x}+{y}"
        except Exception:
            return f"{width}x{height}"

    # -- building blocks ---------------------------------------------------

    def _set_window_icon(self) -> None:
        try:
            from PIL import ImageTk
            self._icon_photo = ImageTk.PhotoImage(icons.magnifier_image(64))
            self.iconphoto(False, self._icon_photo)
        except Exception:
            pass

    def _card(self, parent, icon_img, title: str):
        card = ctk.CTkFrame(parent, corner_radius=14, fg_color=CARD)
        card.pack(fill="x", pady=(0, 12))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 2))
        img = ctk.CTkImage(icon_img, size=(20, 20))
        ctk.CTkLabel(head, image=img, text="").pack(side="left")
        ctk.CTkLabel(
            head, text=title,
            font=ctk.CTkFont(FONT, 14, "bold"),
        ).pack(side="left", padx=(9, 0))
        return card, head

    def _build_header(self, parent) -> None:
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", pady=(0, 10))
        logo = ctk.CTkImage(icons.magnifier_image(96), size=(42, 42))
        ctk.CTkLabel(head, image=logo, text="").pack(side="left")
        txt = ctk.CTkFrame(head, fg_color="transparent")
        txt.pack(side="left", padx=(10, 0))
        word = ctk.CTkFrame(txt, fg_color="transparent")
        word.pack(anchor="w")
        ctk.CTkLabel(
            word, text="Magnify", text_color=BLUE,
            font=ctk.CTkFont(FONT, 21, "bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            word, text=".Snap", text_color=GREEN,
            font=ctk.CTkFont(FONT, 21, "bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            txt, text="Fast screen magnifier", anchor="w",
            font=ctk.CTkFont(FONT, 12), text_color=TEXT_DIM,
        ).pack(anchor="w")

    def _build_zoom_card(self, parent) -> None:
        card, head = self._card(parent, icons.icon_zoom(44), "Zoom level")
        self.zoom_value = ctk.CTkLabel(
            head, text=self._fmt_zoom(),
            font=ctk.CTkFont(FONT, 19, "bold"), text_color=BLUE,
        )
        self.zoom_value.pack(side="right")
        self.zoom_slider = ctk.CTkSlider(
            card, from_=1.25, to=8.0, number_of_steps=27,
            command=self._on_zoom, button_color=BLUE,
            button_hover_color=BLUE_HOVER, progress_color=BLUE,
        )
        self.zoom_slider.set(self.cfg.zoom_factor)
        self.zoom_slider.pack(fill="x", padx=18, pady=(10, 8))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 0))
        ctk.CTkLabel(row, text="Hold-to-peek zoom",
                     font=ctk.CTkFont(FONT, 13)).pack(side="left")
        self.peek_value = ctk.CTkLabel(
            row, text=self._fmt_peek(),
            font=ctk.CTkFont(FONT, 13, "bold"), text_color=GREEN,
        )
        self.peek_value.pack(side="right")
        self.peek_slider = ctk.CTkSlider(
            card, from_=1.5, to=8.0, number_of_steps=26,
            command=self._on_peek, button_color=GREEN,
            button_hover_color=GREEN_HOVER, progress_color=GREEN,
        )
        self.peek_slider.set(self.cfg.peek_factor)
        self.peek_slider.pack(fill="x", padx=18, pady=(4, 4))
        self.peek_hint = ctk.CTkLabel(
            card, anchor="w", justify="left", text=PEEK_HINT,
            font=ctk.CTkFont(FONT, 11), text_color=TEXT_DIM,
        )
        self.peek_hint.pack(fill="x", padx=18, pady=(0, 12))

    def _build_binding_card(self, parent) -> None:
        card, _ = self._card(parent, icons.icon_mouse(44), "Activation button")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(10, 4))
        self.bind_label = ctk.CTkLabel(
            row, text=self.app.binding.display(), anchor="w",
            font=ctk.CTkFont(FONT, 15, "bold"), text_color=GREEN,
        )
        self.bind_label.pack(side="left", fill="x", expand=True)
        self.bind_button = ctk.CTkButton(
            row, text="Change…", height=32, width=110, corner_radius=10,
            fg_color=BLUE, hover_color=BLUE_HOVER,
            font=ctk.CTkFont(FONT, 13, "bold"),
            command=self._begin_capture,
        )
        self.bind_button.pack(side="right")
        self.bind_hint = ctk.CTkLabel(
            card, anchor="w", justify="left", text=BIND_HINT,
            font=ctk.CTkFont(FONT, 11), text_color=TEXT_DIM,
        )
        self.bind_hint.pack(fill="x", padx=18, pady=(0, 12))

    def _build_pan_card(self, parent) -> None:
        card, _ = self._card(parent, icons.icon_move(44), "Screen panning")

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=(8, 0))
        ctk.CTkLabel(row1, text="Cursor follow speed",
                     font=ctk.CTkFont(FONT, 13)).pack(side="left")
        self.speed_value = ctk.CTkLabel(
            row1, text=str(self.cfg.pan_speed),
            font=ctk.CTkFont(FONT, 13, "bold"), text_color=BLUE,
        )
        self.speed_value.pack(side="right")
        self.speed_slider = ctk.CTkSlider(
            card, from_=1, to=10, number_of_steps=9,
            command=self._on_speed, button_color=BLUE,
            button_hover_color=BLUE_HOVER, progress_color=BLUE,
        )
        self.speed_slider.set(self.cfg.pan_speed)
        self.speed_slider.pack(fill="x", padx=18, pady=(4, 8))

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(2, 0))
        ctk.CTkLabel(row2, text="Edge reaction zone",
                     font=ctk.CTkFont(FONT, 13)).pack(side="left")
        self.edge_value = ctk.CTkLabel(
            row2, text=f"{self.cfg.edge_size} px",
            font=ctk.CTkFont(FONT, 13, "bold"), text_color=BLUE,
        )
        self.edge_value.pack(side="right")
        self.edge_slider = ctk.CTkSlider(
            card, from_=10, to=150, number_of_steps=28,
            command=self._on_edge, button_color=BLUE,
            button_hover_color=BLUE_HOVER, progress_color=BLUE,
        )
        self.edge_slider.set(self.cfg.edge_size)
        self.edge_slider.pack(fill="x", padx=18, pady=(4, 4))
        ctk.CTkLabel(
            card, anchor="w", justify="left",
            text="While zoomed, the view follows the cursor near screen edges",
            font=ctk.CTkFont(FONT, 11), text_color=TEXT_DIM,
        ).pack(fill="x", padx=18, pady=(0, 12))

    def _build_misc_card(self, parent) -> None:
        card, _ = self._card(parent, icons.icon_gear(44), "Preferences")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(8, 2))
        ctk.CTkLabel(row, text="Appearance",
                     font=ctk.CTkFont(FONT, 13)).pack(side="left")
        current = next(
            (k for k, v in THEME_VALUES.items() if v == self.cfg.theme),
            "System",
        )
        self.theme_seg = ctk.CTkSegmentedButton(
            row, values=list(THEME_VALUES),
            command=self._on_theme,
            font=ctk.CTkFont(FONT, 12),
            selected_color=BLUE, selected_hover_color=BLUE_HOVER,
        )
        self.theme_seg.set(current)
        self.theme_seg.pack(side="right")

        self.smooth_switch = ctk.CTkSwitch(
            card, text="Smooth zoom animation",
            font=ctk.CTkFont(FONT, 13), progress_color=BLUE,
            command=self._on_smooth,
        )
        self.smooth_switch.pack(anchor="w", padx=18, pady=(8, 2))
        if self.cfg.smooth_zoom:
            self.smooth_switch.select()

        self.autostart_switch = ctk.CTkSwitch(
            card, text="Start when I sign in",
            font=ctk.CTkFont(FONT, 13), progress_color=BLUE,
            command=self._on_autostart,
        )
        self.autostart_switch.pack(anchor="w", padx=18, pady=(4, 2))
        if autostart.is_enabled():
            self.autostart_switch.select()

        self.update_switch = ctk.CTkSwitch(
            card, text="Check for updates daily",
            font=ctk.CTkFont(FONT, 13), progress_color=BLUE,
            command=self._on_update_switch,
        )
        self.update_switch.pack(anchor="w", padx=18, pady=(2, 4))
        if self.cfg.auto_update_check:
            self.update_switch.select()

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(2, 12))
        self.version_label = ctk.CTkLabel(
            row2, text=f"Version {VERSION}", anchor="w",
            font=ctk.CTkFont(FONT, 12), text_color=TEXT_DIM,
        )
        self.version_label.pack(side="left")
        self.update_button = ctk.CTkButton(
            row2, text="Check for updates", height=28, width=150,
            corner_radius=8, fg_color=BLUE, hover_color=BLUE_HOVER,
            font=ctk.CTkFont(FONT, 12, "bold"),
            command=self._on_check_updates,
        )
        self.update_button.pack(side="right")
        self._sync_update_button()

    def _build_footer(self) -> None:
        ctk.CTkLabel(
            self,
            text=f"{APP_NAME} v{VERSION} · lives in the system tray",
            font=ctk.CTkFont(FONT, 11), text_color=TEXT_DIM,
        ).pack(pady=(0, 8))

    # -- handlers -----------------------------------------------------------

    def _fmt_zoom(self) -> str:
        return f"{round(self.cfg.zoom_factor * 100)}%"

    def _fmt_peek(self) -> str:
        return f"{round(self.cfg.peek_factor * 100)}%"

    def _refresh_peek_state(self) -> None:
        """Подсветить, если peek не выше обычного зума (удержание бесполезно)."""
        if self.cfg.peek_factor <= self.cfg.zoom_factor:
            self.peek_value.configure(text_color=AMBER)
            self.peek_hint.configure(text=PEEK_WARN, text_color=AMBER)
        else:
            self.peek_value.configure(text_color=GREEN)
            self.peek_hint.configure(text=PEEK_HINT, text_color=TEXT_DIM)

    def _on_zoom(self, value: float) -> None:
        self.cfg.zoom_factor = round(value * 4) / 4
        self.zoom_value.configure(text=self._fmt_zoom())
        self._refresh_peek_state()
        self._schedule_save()

    def _on_peek(self, value: float) -> None:
        self.cfg.peek_factor = round(value * 4) / 4
        self.peek_value.configure(text=self._fmt_peek())
        self._refresh_peek_state()
        self._schedule_save()

    def _on_speed(self, value: float) -> None:
        self.cfg.pan_speed = int(round(value))
        self.speed_value.configure(text=str(self.cfg.pan_speed))
        self._schedule_save()

    def _on_edge(self, value: float) -> None:
        self.cfg.edge_size = int(round(value / 5) * 5)
        self.edge_value.configure(text=f"{self.cfg.edge_size} px")
        self._schedule_save()

    def _on_theme(self, label: str) -> None:
        self.cfg.theme = THEME_VALUES.get(label, "system")
        ctk.set_appearance_mode(self.cfg.theme)
        self._schedule_save()

    def _on_smooth(self) -> None:
        self.cfg.smooth_zoom = bool(self.smooth_switch.get())
        self._schedule_save()

    def _on_autostart(self) -> None:
        enabled = bool(self.autostart_switch.get())
        if not autostart.set_enabled(enabled):
            (self.autostart_switch.deselect if enabled
             else self.autostart_switch.select)()
        self.cfg.autostart = enabled
        self._schedule_save()

    def _on_update_switch(self) -> None:
        self.cfg.auto_update_check = bool(self.update_switch.get())
        self._schedule_save()

    def _sync_update_button(self) -> None:
        from . import updater
        info = self.app.update_info
        if info is not None:
            self.update_button.configure(
                text=f"Update to {info['version']}", fg_color=GREEN,
                hover_color=GREEN_HOVER, command=self.app.do_update,
                state="normal",
            )
            self.version_label.configure(
                text=f"Version {VERSION} → {info['version']} available",
                text_color=GREEN,
            )
        elif not updater.is_frozen():
            self.update_button.configure(state="disabled",
                                         text="Running from source")

    def _on_check_updates(self) -> None:
        self.update_button.configure(state="disabled", text="Checking…")
        self.app.check_updates(on_result=lambda res: self.app.ui_call(
            lambda: self._show_check_result(res)))

    def _show_check_result(self, result) -> None:
        if not self.winfo_exists():
            return
        self.update_button.configure(state="normal", text="Check for updates")
        if isinstance(result, Exception):
            self.version_label.configure(
                text="Could not check — are you online?", text_color=AMBER)
        elif result is None:
            self.version_label.configure(
                text=f"Version {VERSION} — you're up to date",
                text_color=TEXT_DIM)
        else:
            self._sync_update_button()

    def _begin_capture(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self.bind_button.configure(state="disabled")
        self.bind_label.configure(
            text="Press a button or combination…", text_color=BLUE
        )
        self.bind_hint.configure(text="Esc to cancel", text_color=TEXT_DIM)
        self.app.input.start_capture(
            lambda b, err: self.app.ui_call(lambda: self._end_capture(b, err)),
            hint=lambda: self.app.ui_call(self._show_modifier_hint),
        )

    def _show_modifier_hint(self) -> None:
        """Пользователь отпустил модификаторы, не нажав основную клавишу."""
        if not (self.winfo_exists() and self._capturing):
            return
        self.bind_hint.configure(
            text="Modifiers alone can't be a binding — hold them "
                 "and press a key or mouse button",
            text_color=AMBER,
        )

    def _end_capture(self, binding: Binding | None, error: str | None) -> None:
        self._capturing = False
        if not self.winfo_exists():
            return
        self.bind_button.configure(state="normal")
        if binding is not None:
            self.app.apply_binding(binding)
            self.bind_label.configure(text=binding.display(), text_color=GREEN)
            self.bind_hint.configure(text=BIND_HINT, text_color=TEXT_DIM)
        else:
            self.bind_label.configure(
                text=self.app.binding.display(), text_color=GREEN
            )
            self.bind_hint.configure(
                text=error or BIND_HINT,
                text_color=WARN_RED if error else TEXT_DIM,
            )
            if error:
                self.after(4000, lambda: self.winfo_exists() and
                           self.bind_hint.configure(
                               text=BIND_HINT, text_color=TEXT_DIM))

    def _schedule_save(self) -> None:
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(600, self._do_save)

    def _do_save(self) -> None:
        self._save_job = None
        self.cfg.save()

    def _on_close(self) -> None:
        if self._capturing:
            self.app.input.cancel_capture()
        if self._save_job is not None:
            self.after_cancel(self._save_job)
            self.cfg.save()
        SettingsWindow._instance = None
        self.destroy()
