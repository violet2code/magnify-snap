"""Полноэкранная лупа для Windows на базе Magnification API.

Использует MagSetFullscreenTransform: экран увеличивается на уровне
композитора, при этом ввод (мышь, клавиатура) продолжает работать как обычно.
Панорамирование: видимая область плавно следует за курсором, когда он
приближается к краю экрана.

Важно: Magnification API привязан к потоку — MagSetFullscreenTransform
работает только из потока, вызвавшего MagInitialize. Поэтому вся работа
с API вынесена в один выделенный поток.
"""
import ctypes
import threading
import time
from ctypes import wintypes

from .magnifier_base import MagnifierBase

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

FRAME_DT = 1.0 / 60.0
ZOOM_ANIM_TIME = 0.18  # секунд на анимацию входа/выхода


def _ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


class WindowsMagnifier(MagnifierBase):
    def __init__(self, config, notify=None):
        super().__init__(config, notify)
        self._user32 = ctypes.windll.user32
        self._mag = None
        self._thread = None
        self._wake = threading.Event()
        self._started = threading.Event()
        self._init_ok = False
        self._quit = False
        self._instant_out = False
        self._last = (None, None, None)
        self._fail_reported = False

    # -- жизненный цикл ------------------------------------------------

    def start(self) -> None:
        self._mag = ctypes.WinDLL("Magnification.dll")
        self._mag.MagInitialize.restype = wintypes.BOOL
        self._mag.MagUninitialize.restype = wintypes.BOOL
        self._mag.MagSetFullscreenTransform.restype = wintypes.BOOL
        self._mag.MagSetFullscreenTransform.argtypes = (
            ctypes.c_float, ctypes.c_int, ctypes.c_int,
        )
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        self._started.wait(timeout=5.0)
        if not self._init_ok:
            raise RuntimeError("MagInitialize failed")

    def shutdown(self) -> None:
        self.zoom_out(instant=True)
        self._quit = True
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    # -- публичное управление -------------------------------------------

    def zoom_in(self) -> None:
        if self.active or not self._init_ok:
            return
        self.active = True
        self._instant_out = False
        self._wake.set()

    def zoom_out(self, instant: bool = False) -> None:
        if not self.active:
            return
        self._instant_out = instant
        self.active = False

    # -- поток-владелец Magnification API ---------------------------------

    def _thread_main(self) -> None:
        self._init_ok = bool(self._mag.MagInitialize())
        self._started.set()
        if not self._init_ok:
            return
        try:
            while True:
                self._wake.wait()
                self._wake.clear()
                if self._quit:
                    break
                if self.active:
                    self._session()
        finally:
            vx, vy, _, _ = self._screen()
            self._set(1.0, vx, vy, force=True)
            self._mag.MagUninitialize()

    # -- внутреннее ------------------------------------------------------

    def _screen(self):
        gm = self._user32.GetSystemMetrics
        return (
            gm(SM_XVIRTUALSCREEN), gm(SM_YVIRTUALSCREEN),
            gm(SM_CXVIRTUALSCREEN), gm(SM_CYVIRTUALSCREEN),
        )

    def _cursor(self):
        pt = wintypes.POINT()
        self._user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def _set(self, mag: float, offx: float, offy: float, force: bool = False) -> None:
        params = (round(mag, 4), int(round(offx)), int(round(offy)))
        if not force and params == self._last:
            return
        ok = self._mag.MagSetFullscreenTransform(
            ctypes.c_float(params[0]), params[1], params[2]
        )
        if ok:
            self._last = params
        elif not self._fail_reported:
            self._fail_reported = True
            self.notify(
                "Could not apply screen magnification.\n"
                "It may be blocked by another magnifier application."
            )

    @staticmethod
    def _clamp(v, lo, hi):
        return lo if v < lo else hi if v > hi else v

    def _anchored(self, cx, cy, mag, vx, vy, vw, vh):
        """Смещение, при котором точка под курсором остаётся на месте."""
        offx = cx - (cx - vx) / mag
        offy = cy - (cy - vy) / mag
        offx = self._clamp(offx, vx, vx + vw - vw / mag)
        offy = self._clamp(offy, vy, vy + vh - vh / mag)
        return offx, offy

    def _pan_axis(self, s, dim, off, mag, vmin, vsize):
        """Прокрутка по одной оси, когда курсор в краевой зоне."""
        edge = max(10, int(self.config.edge_size))
        step = self.config.pan_speed * 2.4  # экранных px за кадр при полной силе
        if s < edge:
            k = min((edge - s) / edge, 3.0)
            off -= k * step / mag
        elif s > dim - edge:
            k = min((s - (dim - edge)) / edge, 3.0)
            off += k * step / mag
        return self._clamp(off, vmin, vmin + vsize - vsize / mag)

    def _session(self) -> None:
        """Один сеанс увеличения: вход → слежение за курсором → выход."""
        vx, vy, vw, vh = self._screen()
        cx, cy = self._cursor()
        target = float(self.config.zoom_factor)
        mag = 1.0

        # плавный вход
        if self.config.smooth_zoom:
            t0 = time.perf_counter()
            while self.active:
                t = (time.perf_counter() - t0) / ZOOM_ANIM_TIME
                if t >= 1.0:
                    break
                mag = 1.0 + (target - 1.0) * _ease_out_cubic(t)
                offx, offy = self._anchored(cx, cy, mag, vx, vy, vw, vh)
                self._set(mag, offx, offy)
                time.sleep(FRAME_DT)

        mag = target
        offx, offy = self._anchored(cx, cy, mag, vx, vy, vw, vh)
        self._set(mag, offx, offy)

        # основной цикл: следование за курсором у краёв экрана
        while self.active:
            target = float(self.config.zoom_factor)
            if abs(target - mag) > 0.004:  # живое изменение масштаба из настроек
                mag += (target - mag) * 0.2
                if abs(target - mag) < 0.01:
                    mag = target
                offx = self._clamp(offx, vx, vx + vw - vw / mag)
                offy = self._clamp(offy, vy, vy + vh - vh / mag)

            cx, cy = self._cursor()
            sx = (cx - offx) * mag  # позиция курсора на физическом экране
            sy = (cy - offy) * mag
            offx = self._pan_axis(sx, vw, offx, mag, vx, vw)
            offy = self._pan_axis(sy, vh, offy, mag, vy, vh)

            self._set(mag, offx, offy)
            time.sleep(FRAME_DT)

        # плавный выход
        if self.config.smooth_zoom and not self._instant_out:
            m0, ox0, oy0 = mag, offx, offy
            t0 = time.perf_counter()
            while True:
                t = (time.perf_counter() - t0) / ZOOM_ANIM_TIME
                if t >= 1.0:
                    break
                e = _ease_out_cubic(t)
                self._set(
                    m0 + (1.0 - m0) * e,
                    ox0 + (vx - ox0) * e,
                    oy0 + (vy - oy0) * e,
                )
                time.sleep(FRAME_DT)

        self._set(1.0, vx, vy, force=True)
