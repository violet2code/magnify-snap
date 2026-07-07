"""All Magnify.Snap artwork drawn in code (Pillow).

Brand: "Magnify" — blue, "Snap" — mint green. The app icon is a magnifier
lens with a lightning bolt inside (snap = instant zoom). Icons are rendered
at 4x and downscaled for smooth antialiasing.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

BLUE = (79, 141, 253, 255)      # "Magnify"
GREEN = (61, 220, 151, 255)     # "Snap" / active state
WHITE = (240, 244, 255, 255)

# lightning bolt outline in unit coordinates (centered at 0,0)
_BOLT = (
    (0.20, -0.95), (-0.52, 0.12), (-0.05, 0.12),
    (-0.20, 0.95), (0.52, -0.12), (0.05, -0.12),
)


def _downscale(img: Image.Image, w: int, h: int) -> Image.Image:
    return img.resize((w, h), Image.LANCZOS)


def _draw_bolt(d: ImageDraw.ImageDraw, cx: float, cy: float,
               scale: float, color) -> None:
    d.polygon([(cx + x * scale, cy + y * scale) for x, y in _BOLT], fill=color)


def magnifier_image(size: int = 64, active: bool = False) -> Image.Image:
    """App/tray icon: lens + bolt. Idle: blue ring, green bolt; active: swapped."""
    ring, bolt = (GREEN, BLUE) if active else (BLUE, GREEN)
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = int(s * 0.31)
    cx = cy = int(s * 0.40)
    rw = max(4, s // 13)
    d.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=(ring[0], ring[1], ring[2], 40),
        outline=ring, width=rw,
    )
    # handle
    hw = max(6, s // 9)
    x0 = cx + int(r * 0.70)
    y0 = cy + int(r * 0.70)
    d.line((x0, y0, int(s * 0.87), int(s * 0.87)), fill=ring, width=hw)
    d.ellipse((int(s * 0.87) - hw // 2, int(s * 0.87) - hw // 2,
               int(s * 0.87) + hw // 2, int(s * 0.87) + hw // 2), fill=ring)
    # bolt inside the lens
    _draw_bolt(d, cx, cy, r * 0.62, bolt)

    return _downscale(img, size, size)


def _load_font(px: int):
    candidates = (
        "C:/Windows/Fonts/segoeuib.ttf",       # Segoe UI Bold
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, px)
            except OSError:
                pass
    return ImageFont.load_default()


def logo_image(height: int = 160) -> Image.Image:
    """Wordmark logo: icon + 'Magnify' (blue) + '.Snap' (green), transparent bg."""
    s = height * 2  # supersample
    font = _load_font(int(s * 0.50))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w1 = probe.textlength("Magnify", font=font)
    w2 = probe.textlength(".Snap", font=font)
    gap = int(s * 0.18)
    width = int(s + gap + w1 + w2 + s * 0.08)

    img = Image.new("RGBA", (width, s), (0, 0, 0, 0))
    icon = magnifier_image(s)
    img.paste(icon, (0, 0), icon)
    d = ImageDraw.Draw(img)
    x = s + gap
    y = int(s * 0.47)
    d.text((x, y), "Magnify", font=font, fill=BLUE, anchor="lm")
    d.text((x + w1, y), ".Snap", font=font, fill=GREEN, anchor="lm")
    return _downscale(img, width // 2, height)


# -- small glyphs for settings cards ------------------------------------

def _glyph_canvas(size: int):
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), s


def icon_zoom(size: int = 22, color=BLUE) -> Image.Image:
    img, d, s = _glyph_canvas(size)
    r = int(s * 0.30)
    cx = cy = int(s * 0.42)
    w = max(4, s // 10)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=w)
    d.line((cx + int(r * 0.7), cy + int(r * 0.7), int(s * 0.88), int(s * 0.88)),
           fill=color, width=w)
    _draw_bolt(d, cx, cy, r * 0.58, GREEN)
    return _downscale(img, size, size)


def icon_mouse(size: int = 22, color=BLUE) -> Image.Image:
    img, d, s = _glyph_canvas(size)
    w = max(4, s // 10)
    x0, y0, x1, y1 = int(s * 0.28), int(s * 0.10), int(s * 0.72), int(s * 0.90)
    d.rounded_rectangle((x0, y0, x1, y1), radius=(x1 - x0) // 2,
                        outline=color, width=w)
    cx = (x0 + x1) // 2
    d.line((cx, int(s * 0.22), cx, int(s * 0.42)), fill=GREEN, width=w)
    return _downscale(img, size, size)


def icon_move(size: int = 22, color=BLUE) -> Image.Image:
    img, d, s = _glyph_canvas(size)
    w = max(4, s // 10)
    c = s // 2
    a = int(s * 0.38)
    h = int(s * 0.14)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        tip = (c + dx * a, c + dy * a)
        d.line((c, c, *tip), fill=color, width=w)
        if dx:
            d.line((tip[0] - dx * h, tip[1] - h, *tip), fill=color, width=w)
            d.line((tip[0] - dx * h, tip[1] + h, *tip), fill=color, width=w)
        else:
            d.line((tip[0] - h, tip[1] - dy * h, *tip), fill=color, width=w)
            d.line((tip[0] + h, tip[1] - dy * h, *tip), fill=color, width=w)
    return _downscale(img, size, size)


def icon_gear(size: int = 22, color=BLUE) -> Image.Image:
    img, d, s = _glyph_canvas(size)
    w = max(4, s // 10)
    c = s // 2
    r_in = int(s * 0.16)
    r_ring = int(s * 0.28)
    d.ellipse((c - r_in, c - r_in, c + r_in, c + r_in), outline=color, width=w)
    d.ellipse((c - r_ring, c - r_ring, c + r_ring, c + r_ring),
              outline=color, width=w)
    for i in range(8):
        ang = math.pi / 4 * i + math.pi / 8
        x0 = c + math.cos(ang) * (r_ring + w // 2)
        y0 = c + math.sin(ang) * (r_ring + w // 2)
        x1 = c + math.cos(ang) * int(s * 0.42)
        y1 = c + math.sin(ang) * int(s * 0.42)
        d.line((x0, y0, x1, y1), fill=color, width=w)
    return _downscale(img, size, size)


# -- build/export helpers ------------------------------------------------

_SVG_LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 660 160">
  <g fill="none" stroke="#4f8dfd" stroke-width="14" stroke-linecap="round">
    <circle cx="76" cy="64" r="46" fill="rgba(79,141,253,0.16)"/>
    <line x1="110" y1="98" x2="138" y2="126"/>
  </g>
  <polygon fill="#3ddc97" points="82.7,32.7 58.9,68.0 74.4,68.0 69.4,95.3 93.2,60.0 77.7,60.0"/>
  <text x="170" y="64" dominant-baseline="central"
        font-family="Segoe UI, Inter, Arial, sans-serif" font-size="66"
        font-weight="700"><tspan fill="#4f8dfd">Magnify</tspan><tspan
        fill="#3ddc97">.Snap</tspan></text>
</svg>
"""


def save_ico(path: str) -> None:
    """Multi-size .ico for the Windows build."""
    base = magnifier_image(256)
    base.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                           (64, 64), (128, 128), (256, 256)])


def save_png(path: str, size: int = 256) -> None:
    magnifier_image(size).save(path)


def save_logo_assets(directory: str) -> None:
    """logo.png (transparent, works on light & dark) + logo.svg for the web."""
    os.makedirs(directory, exist_ok=True)
    logo_image(320).save(os.path.join(directory, "logo.png"))
    with open(os.path.join(directory, "logo.svg"), "w", encoding="utf-8") as f:
        f.write(_SVG_LOGO)
