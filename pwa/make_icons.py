#!/usr/bin/env python3
"""
Ouja PWA icon generator.

Regenerates every home-screen / install icon in pwa/icons/ from ONE source.

HOW TO USE THE REAL LOGO
------------------------
Drop the real Ouja logo here:

    pwa/logo.png        (square PNG, transparent background, ideally >= 1024x1024)

then run:

    python3 pwa/make_icons.py

Every icon regenerates from it (the logo is centered on the brand tile with the
right safe-zone padding for each purpose). If pwa/logo.png is absent, a clean
"ع" brand-mark placeholder is generated instead so the PWA still installs with a
proper icon today — the moment you add the logo and re-run, the placeholder is
replaced everywhere.

Nothing else in the app needs to change: manifest + HTML already point at these
files by name.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, "icons")
LOGO = os.path.join(HERE, "logo.png")
FONT = os.path.join(os.path.dirname(HERE), "fonts", "ouja-ar.ttf")

# Brand palette (matches the app's own dark brand — see INVEST_HTML :root in bot.py)
BG_EDGE = (14, 13, 12)     # #0E0D0C warm near-black
BG_CORE = (30, 26, 22)     # #1E1A16 warm surface
GOLD = (212, 168, 84)      # #D4A854 brand gold
GLOW = (212, 168, 84)

os.makedirs(ICONS, exist_ok=True)


def _tile(size):
    """The brand background tile: warm near-black with a soft gold core glow."""
    img = Image.new("RGB", (size, size), BG_EDGE)
    px = img.load()
    cx = cy = size / 2.0
    maxd = (size * 0.72)
    for y in range(size):
        for x in range(size):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            t = max(0.0, 1.0 - d / maxd)  # 1 at center → 0 at edge
            t = t * t
            px[x, y] = (
                int(BG_EDGE[0] + (BG_CORE[0] - BG_EDGE[0]) * t),
                int(BG_EDGE[1] + (BG_CORE[1] - BG_EDGE[1]) * t),
                int(BG_EDGE[2] + (BG_CORE[2] - BG_EDGE[2]) * t),
            )
    return img.convert("RGBA")


def _paste_mark(tile, mark, coverage):
    """Center `mark` (RGBA) onto `tile`, scaled so its longest side == coverage*size."""
    size = tile.size[0]
    target = int(size * coverage)
    w, h = mark.size
    scale = target / float(max(w, h))
    mark = mark.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    x = (size - mark.size[0]) // 2
    y = (size - mark.size[1]) // 2
    out = tile.copy()
    out.alpha_composite(mark, (x, y))
    return out


def _glyph_mark(px=800):
    """Placeholder brand mark: a gold 'ع' on transparent, tightly cropped."""
    canvas = px * 2
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT, int(canvas * 0.62))
    except Exception:
        font = ImageFont.load_default()
    d.text((canvas / 2, canvas / 2), "ع", font=font, fill=GOLD + (255,), anchor="mm")
    return img.crop(img.getbbox())


def _load_mark():
    if os.path.exists(LOGO):
        m = Image.open(LOGO).convert("RGBA")
        bb = m.getbbox()
        return (m.crop(bb) if bb else m), True
    return _glyph_mark(), False


def build():
    mark, real = _load_mark()
    src = "logo.png" if real else 'placeholder "ع" brand mark'
    print("Source:", src)

    # purpose "any" + apple-touch: mark covers ~54% (comfortable padding, OS rounds corners)
    for size in (192, 256, 384, 512):
        _paste_mark(_tile(size), mark, 0.54).convert("RGB").save(
            os.path.join(ICONS, f"icon-{size}.png"))
        print("  icon-%d.png" % size)

    # maskable: mark must sit inside the ~80% safe circle → cover only ~40%
    for size in (192, 512):
        _paste_mark(_tile(size), mark, 0.40).convert("RGB").save(
            os.path.join(ICONS, f"icon-maskable-{size}.png"))
        print("  icon-maskable-%d.png" % size)

    # apple-touch (180, no transparency — iOS applies its own mask)
    _paste_mark(_tile(180), mark, 0.54).convert("RGB").save(
        os.path.join(ICONS, "apple-touch-icon.png"))
    print("  apple-touch-icon.png")

    # favicon
    _paste_mark(_tile(32), mark, 0.62).convert("RGB").save(
        os.path.join(ICONS, "favicon-32.png"))
    print("  favicon-32.png")

    print("Done →", ICONS)


if __name__ == "__main__":
    build()
