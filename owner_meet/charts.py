# -*- coding: utf-8 -*-
"""
owner_meet.charts — PURE SVG renderers. One renderer for the presentation, the owner's phone page
and the PDF, deterministic to the byte (golden-tested in tests/test_owner_meet_charts.py).

Rules (spec §10): zero-based bars with 4px rounded data ends, a recessive grid, direct labels, no
dual axis, BANDS for peers (never one mark per peer — a viewer could count them, R1), every chart a
role="img" with <title> + <desc>. Time runs RIGHT-TO-LEFT (the first month sits at the right edge),
matching Arabic reading order. Arabic text nodes carry direction="rtl"; numbers are isolated LTR.
No backslashes anywhere in this file (brief P3).
"""

from html import escape

from . import texts

INK, MUTE, LINE, GOLD, GOLD_SOFT = "#0B1A2E", "#5C6470", "#E4E1DA", "#C6A15B", "#EFE4CC"
# The data series colour is Diriyah mud-brick brown (Faisal 2026-10-06: «استخدم لون الدرعية البني بدال الأزرق»).
MUD, MUD_SOFT, GREEN, RED, WASH = "#8B5A3C", "#EBDCCB", "#1F6F55", "#B23A34", "#EDEAE3"


def _f(x):
    """Fixed 2dp coordinates with trailing zeros stripped — stable bytes across platforms."""
    s = "%.2f" % x
    return s.rstrip("0").rstrip(".") if "." in s else s


def _t(x, y, text, cls, anchor="middle", rtl=False, extra=""):
    d = ' direction="rtl"' if rtl else ""
    return '<text x="%s" y="%s" class="%s" text-anchor="%s"%s%s>%s</text>' % (
        _f(x), _f(y), cls, anchor, d, extra, escape(str(text)))


def _top_rounded(x, y, w, h, r=4.0):
    """A bar whose DATA end (top) is rounded and whose base sits square on the zero line."""
    if h <= 0 or w <= 0:
        return ""
    r = min(r, w / 2.0, h)
    return ('<path d="M%s %sV%sQ%s %s %s %sH%sQ%s %s %s %sV%sZ"' % (
        _f(x), _f(y + h), _f(y + r), _f(x), _f(y), _f(x + r), _f(y), _f(x + w - r), _f(x + w), _f(y),
        _f(x + w), _f(y + r), _f(y + h)))


def _bottom_rounded(x, y, w, h, r=4.0):
    """A negative bar: base on the zero line at y, rounded data end at the bottom."""
    if h <= 0 or w <= 0:
        return ""
    r = min(r, w / 2.0, h)
    return ('<path d="M%s %sV%sQ%s %s %s %sH%sQ%s %s %s %sV%sZ"' % (
        _f(x), _f(y), _f(y + h - r), _f(x), _f(y + h), _f(x + r), _f(y + h), _f(x + w - r),
        _f(x + w), _f(y + h), _f(x + w), _f(y + h - r), _f(y)))


def _svg(w, h, title, desc, body, cls="chart"):
    return ('<svg class="%s" viewBox="0 0 %d %d" role="img" aria-label="%s" xmlns="http://www.w3.org/2000/svg">'
            '<title>%s</title><desc>%s</desc>%s</svg>') % (
        cls, w, h, escape(title), escape(title), escape(desc), body)


def _nice_max(v):
    """A round axis top above v (1, 2, 2.5, 5 x 10^k)."""
    if v <= 0:
        return 1.0
    k = 1.0
    while k * 10 <= v:
        k *= 10
    while k > v:
        k /= 10
    for m in (1, 2, 2.5, 5, 10):
        if k * m >= v:
            return k * m
    return k * 10


# ------------------------------------------------------------------ monthly bars
def month_bars(points, title, desc, fmt=texts.compact, height=300, colour=INK, shade=None, notes=None,
               show_values=True, cls="chart", width=1100):
    """points: [{m:'YYYY-MM', value, partial}] oldest first. shade: {m: label} (Ramadan / Eid — a
    wash behind the month and a label under its name); notes: {m: marker} (an annotated month — a
    grey bar and a marker the page explains in a caption). Months run right-to-left. Negative values
    hang below a zero line in red. `width` is the viewBox width: pick it to match the slot's aspect so
    the chart scales without letterboxing."""
    W, top, bottom = width, 26, 50
    n = max(1, len(points))
    vals = [float(p.get("value") or 0) for p in points]
    hi = _nice_max(max([0.0] + vals))
    lo = -_nice_max(-min(vals)) if vals and min(vals) < 0 else 0.0
    plot_h = height - top - bottom
    span = (hi - lo) or 1.0
    zero_y = top + plot_h * (hi / span)
    slot = (W - 20) / float(n)
    bw = min(56.0, slot * 0.62)
    shade, notes = shade or {}, notes or {}
    parts = []
    for i, p in enumerate(points):                         # seasons first, behind everything
        if p["m"] in shade:
            x = W - 10 - slot * (i + 1)
            parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>' % (
                _f(x), _f(top - 18), _f(slot), _f(plot_h + 18 + 26), WASH))
    for g in (0.5, 1.0):                                    # recessive grid: half and top only
        y = top + plot_h * (1 - g) * (hi / span) if lo == 0 else zero_y - (zero_y - top) * g
        parts.append('<line x1="10" x2="%d" y1="%s" y2="%s" stroke="%s" stroke-width="1"/>' % (
            W - 10, _f(y), _f(y), LINE))
    parts.append('<line x1="10" x2="%d" y1="%s" y2="%s" stroke="%s" stroke-width="1.5"/>' % (
        W - 10, _f(zero_y), _f(zero_y), INK))
    for i, p in enumerate(points):
        v = vals[i]
        cx = W - 10 - slot * (i + 0.5)
        x = cx - bw / 2.0
        if p["m"] in notes:
            fill = "#C9CED6"
        elif p.get("partial"):
            fill = MUD_SOFT if colour == MUD else "#9AA6B6"
        else:
            fill = colour
        if v >= 0:
            h = plot_h * (v / span)
            path = _top_rounded(x, zero_y - h, bw, h)
            if path:
                parts.append(path + ' fill="%s"/>' % fill)
            ly = zero_y - h - 7
        else:
            h = plot_h * (-v / span)
            path = _bottom_rounded(x, zero_y, bw, h)
            if path:
                parts.append(path + ' fill="%s"/>' % RED)
            ly = zero_y + h + 15
        if show_values:
            parts.append(_t(cx, ly, fmt(v), "vl", extra=' style="font-variant-numeric:tabular-nums"'))
        parts.append(_t(cx, height - bottom + 20, texts.month_ar(p["m"]), "lb", rtl=True))
        sub = " ".join(x for x in (notes.get(p["m"]), shade.get(p["m"]), "حتى تاريخه" if p.get("partial") else "") if x)
        if sub:
            parts.append(_t(cx, height - bottom + 37, sub, "lbm", rtl=True))
    return _svg(W, height, title, desc, "".join(parts), cls)


# ------------------------------------------------------------------ waterfall
def waterfall(rows, title, desc, labels=None):
    """rows: [{key, amount, sign}] from money.waterfall (income first, net last). Columns run
    right-to-left: income at the right edge, the owner's net at the left — read like a sentence."""
    labels = labels or texts.WATERFALL
    W, H, top, bottom = 760, 340, 40, 58
    n = max(1, len(rows))
    income = float(rows[0]["amount"]) if rows else 0.0
    peak = max([income] + [abs(float(r["amount"])) for r in rows] + [1.0])
    plot_h = H - top - bottom
    base_y = top + plot_h
    slot = (W - 20) / float(n)
    bw = min(78.0, slot * 0.6)
    parts = ['<line x1="10" x2="%d" y1="%s" y2="%s" stroke="%s" stroke-width="1.5"/>' % (
        W - 10, _f(base_y), _f(base_y), INK)]
    level = 0.0
    prev_edge = None
    for i, r in enumerate(rows):
        amt = float(r["amount"])
        cx = W - 10 - slot * (i + 0.5)
        x = cx - bw / 2.0
        if r["key"] == "income":
            lo_v, hi_v, fill = 0.0, amt, INK
            level = amt
        elif r["key"] == "net":
            lo_v, hi_v, fill = min(0.0, amt), max(0.0, amt), GOLD
        elif r["sign"] < 0:
            lo_v, hi_v, fill = level - amt, level, "#B9BFC8"
            level -= amt
        else:
            lo_v, hi_v, fill = level, level + amt, GREEN
            level += amt
        y_hi = base_y - plot_h * (max(hi_v, 0.0) / peak)
        y_lo = base_y - plot_h * (max(lo_v, 0.0) / peak)
        h = y_lo - y_hi
        if r["key"] in ("income", "net"):
            path = _top_rounded(x, y_hi, bw, h)
            if path:
                parts.append(path + ' fill="%s"/>' % fill)
        elif h > 0:
            parts.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" rx="2"/>' % (
                _f(x), _f(y_hi), _f(bw), _f(h), fill))
        if prev_edge is not None:                            # a thin connector carries the running level
            parts.append('<line x1="%s" x2="%s" y1="%s" y2="%s" stroke="%s" stroke-dasharray="3 3"/>' % (
                _f(prev_edge[0]), _f(x + bw), _f(prev_edge[1]), _f(prev_edge[1]), MUTE))
        edge_y = base_y - plot_h * (max(level if r["key"] != "net" else amt, 0.0) / peak)
        prev_edge = (x, edge_y)
        sign = "" if amt == 0 else ("−" if r["sign"] < 0 else ("+" if r["key"] == "adjustments" else ""))
        parts.append(_t(cx, y_hi - 8, sign + texts.money(amt), "vl",
                        extra=' style="font-variant-numeric:tabular-nums"'))
        parts.append(_t(cx, H - bottom + 22, labels.get(r["key"], r["key"]), "lb", rtl=True))
    return _svg(W, H, title, desc, "".join(parts), "chart wf")


# ------------------------------------------------------------------ peer band
def band(b, fmt, title):
    """One metric as a band: the middle half of comparable units (p25..p75) as a soft box, the
    median as a tick, and the owner's unit as a gold mark. No individual peer is ever drawn (R1).
    Low values sit on the left, high on the right (a number line), labelled under the track."""
    W, H = 560, 50
    lo = min(b["p25"], b["value"])
    hi = max(b["p75"], b["value"])
    pad = (hi - lo) * 0.18 or (abs(hi) * 0.2 or 1.0)
    lo, hi = max(0.0, lo - pad) if lo >= 0 else lo - pad, hi + pad
    sx = lambda v: 16 + (W - 32) * ((v - lo) / float(hi - lo))
    y = 18
    p25, p50, p75, me = sx(b["p25"]), sx(b["p50"]), sx(b["p75"]), sx(b["value"])
    parts = [
        '<line x1="16" x2="%d" y1="%d" y2="%d" stroke="%s" stroke-width="3" stroke-linecap="round"/>' % (W - 16, y, y, LINE),
        '<rect x="%s" y="%d" width="%s" height="18" rx="4" fill="%s"/>' % (_f(p25), y - 9, _f(max(2.0, p75 - p25)), MUD_SOFT),
        '<line x1="%s" x2="%s" y1="%d" y2="%d" stroke="%s" stroke-width="2"/>' % (_f(p50), _f(p50), y - 13, y + 13, INK),
        '<circle cx="%s" cy="%d" r="9" fill="%s" stroke="#FFFFFF" stroke-width="3"/>' % (_f(me), y, GOLD),
        _t(p50, y + 29, "الوسيط " + fmt(b["p50"]), "lbm", rtl=True),
    ]
    desc = "شقتك %s، والنصف الأوسط من الشقق المقارنة بين %s و%s، والوسيط %s." % (
        fmt(b["value"]), fmt(b["p25"]), fmt(b["p75"]), fmt(b["p50"]))
    return _svg(W, H, title, desc, "".join(parts), "chart band")


def band_key():
    """The legend that sits once under the band rows."""
    W, H = 520, 22
    parts = [
        '<circle cx="508" cy="11" r="6" fill="%s"/>' % GOLD, _t(498, 15, "شقتك", "lbm", anchor="start", rtl=True),
        '<rect x="402" y="5" width="22" height="12" rx="3" fill="%s"/>' % MUD_SOFT,
        _t(396, 15, "النصف الأوسط من الشقق المقارنة", "lbm", anchor="start", rtl=True),
        '<line x1="186" x2="186" y1="3" y2="19" stroke="%s" stroke-width="2"/>' % INK,
        _t(178, 15, "الوسيط", "lbm", anchor="start", rtl=True),
    ]
    return _svg(W, H, "مفتاح المقارنة", "علامة ذهبية لشقتك، صندوق للنصف الأوسط، وخط للوسيط.",
                "".join(parts), "chart key")


# ------------------------------------------------------------------ recovery ring + score bars
def ring(rate, title, desc, size=220):
    """Received ÷ claimed on closed claims, as one arc. The brief asks for this ring by name; the
    number in its centre carries the meaning, the arc only echoes it."""
    r, c = 88.0, size / 2.0
    circ = 2 * 3.141592653589793 * r
    frac = max(0.0, min(1.0, rate or 0.0))
    parts = ['<circle cx="%s" cy="%s" r="%s" fill="none" stroke="%s" stroke-width="18"/>' % (_f(c), _f(c), _f(r), LINE),
             ('<circle cx="%s" cy="%s" r="%s" fill="none" stroke="%s" stroke-width="18" stroke-linecap="round" '
              'stroke-dasharray="%s %s" transform="rotate(-90 %s %s)"/>') % (
                 _f(c), _f(c), _f(r), GOLD, _f(circ * frac), _f(circ), _f(c), _f(c)) if frac > 0 else "",
             '<text x="%s" y="%s" class="ringv" text-anchor="middle">%s</text>' % (
                 _f(c), _f(c + 12), escape(texts.pct(rate) if rate is not None else "—"))]
    return _svg(size, size, title, desc, "".join(parts), "chart ring")


def score_bars(items, title, desc, top=5.0, target=None):
    """items: [{label, value}] on a 0..top scale, one row each, label on the right (RTL)."""
    W, row = 560, 34
    H = row * max(1, len(items)) + 8
    x0, x1 = 64, 400              # numbers live in their own column left of the track, never on a bar
    parts = []
    for i, it in enumerate(items):
        y = 6 + i * row
        w = (x1 - x0) * max(0.0, min(1.0, float(it["value"]) / top))
        parts.append('<rect x="%d" y="%s" width="%s" height="10" rx="3" fill="%s"/>' % (x0, _f(y + 7), _f(x1 - x0), LINE))
        parts.append('<rect x="%s" y="%s" width="%s" height="10" rx="3" fill="%s"/>' % (_f(x1 - w), _f(y + 7), _f(w), MUD))
        parts.append(_t(W - 4, y + 17, it["label"], "lb", anchor="start", rtl=True))
        parts.append(_t(x0 - 10, y + 17, texts.num(it["value"], 2), "vl", anchor="end"))
    if target:
        tx = x1 - (x1 - x0) * (target / top)
        parts.append('<line x1="%s" x2="%s" y1="2" y2="%s" stroke="%s" stroke-width="1.5" stroke-dasharray="3 3"/>' % (
            _f(tx), _f(tx), _f(H - 2), INK))
    return _svg(W, H, title, desc, "".join(parts), "chart scores")
