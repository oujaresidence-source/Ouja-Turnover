# -*- coding: utf-8 -*-
"""digest.art_generated — deterministic, seeded SVG artwork (brief §7 kind C).

A navy field, one gold rule, the item's glyph in Serif Display Black, and a
low-amplitude line texture driven by an LCG seeded from sha256(seed_text). Same input →
same bytes, forever — that is what makes the frozen render test possible. This is the
ONLY artwork for cinema (typographic film cards, no posters) and fixtures (a two-tone
band with the club names set in type, no crests). Pure."""

import hashlib
import html as _html

from .render.tokens import TOKENS

KINDS = {"square": (760, 760), "portrait": (600, 800), "band": (900, 450)}
LINES = 18
AMPLITUDE = 3.0


def _lcg(seed_text):
    x = int(hashlib.sha256((seed_text or "").encode("utf-8")).hexdigest()[:8], 16)
    while True:
        x = (1103515245 * x + 12345) % (2 ** 31)
        yield x / float(2 ** 31)


def _texture(w, h, rnd):
    """18 hairlines that wander by at most ±3px — texture you feel, not see."""
    out = []
    step = h / float(LINES + 1)
    for i in range(1, LINES + 1):
        y = step * i
        pts = []
        x = 0.0
        while x <= w:
            dy = (next(rnd) * 2.0 - 1.0) * AMPLITUDE
            pts.append("%.1f,%.1f" % (x, y + dy))
            x += w / 12.0
        out.append('<polyline points="%s" fill="none" stroke="%s" stroke-opacity="0.10" stroke-width="1"/>'
                   % (" ".join(pts), TOKENS["gold-2"]))
    return "".join(out)


def _first_glyph(text):
    for ch in (text or ""):
        if ch.isalnum():
            return ch
    return "•"


def svg(seed_text, glyph, kind="square", label=""):
    """kind: square | portrait | band. For 'band', glyph is (home, away)."""
    w, h = KINDS.get(kind, KINDS["square"])
    rnd = _lcg(seed_text)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
             'role="img" aria-label="%s" data-seed="%s">' % (w, h, w, h, _html.escape(label or ""),
                                                             hashlib.sha256((seed_text or "").encode("utf-8")).hexdigest()[:12])]
    parts.append('<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
                 '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient></defs>'
                 % (TOKENS["ink-2"], TOKENS["ink"]))
    parts.append('<rect width="%d" height="%d" fill="url(#g)"/>' % (w, h))
    if kind == "band":
        home, away = (glyph if isinstance(glyph, (tuple, list)) and len(glyph) == 2 else (str(glyph), ""))
        parts.append('<rect x="%d" y="0" width="%d" height="%d" fill="%s"/>' % (w // 2, w // 2, h, TOKENS["ink-3"]))
        parts.append(_texture(w, h, rnd))
        parts.append('<rect x="%d" y="%d" width="%d" height="3" fill="%s"/>' % (w * 0.42, h * 0.5 - 1, w * 0.16, TOKENS["gold"]))
        fs = int(h * 0.20)
        parts.append('<text x="%d" y="%d" text-anchor="middle" font-family="Thmanyah Serif Display" '
                     'font-weight="900" font-size="%d" fill="%s" direction="rtl">%s</text>'
                     % (w * 0.75, h * 0.5 + fs * 0.35, fs, TOKENS["paper"], _html.escape(home)))
        parts.append('<text x="%d" y="%d" text-anchor="middle" font-family="Thmanyah Serif Display" '
                     'font-weight="900" font-size="%d" fill="%s" direction="rtl">%s</text>'
                     % (w * 0.25, h * 0.5 + fs * 0.35, fs, TOKENS["paper"], _html.escape(away)))
    else:
        parts.append(_texture(w, h, rnd))
        g = _first_glyph(glyph if isinstance(glyph, str) else "")
        fs = int(min(w, h) * 0.58)
        parts.append('<rect x="%d" y="%d" width="%d" height="3" fill="%s"/>' % (w * 0.42, h * 0.80, w * 0.16, TOKENS["gold"]))
        parts.append('<text x="%d" y="%d" text-anchor="middle" font-family="Thmanyah Serif Display" '
                     'font-weight="900" font-size="%d" fill="%s">%s</text>'
                     % (w / 2, h * 0.5 + fs * 0.33, fs, TOKENS["paper"], _html.escape(g)))
    parts.append("</svg>")
    return "".join(parts)


def sha256_of(svg_text):
    return hashlib.sha256((svg_text or "").encode("utf-8")).hexdigest()
