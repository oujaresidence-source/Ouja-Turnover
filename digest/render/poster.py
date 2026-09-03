# -*- coding: utf-8 -*-
"""digest.render.poster — the ONE tall poster (the reference format: the Ministry of
Industry's «ما وراء الخميس»). 540 CSS px wide, rendered at 2× → 1080 px, height by
content. Header (brand, date pill, section pills), occasion strip, photo cards with a
district pill and a QR in the corners and the facts line beneath, cinema posters with
the IMDb badge, the place, the podcast, the fixtures block with logos, the verse strip,
the saying, and the footer. Our tokens, not theirs. Pure; ZERO backslashes here."""

from ..dates import AR_DAY, ar_digits
from . import fonts, tokens
from .html import NL, _ratings, bidi, esc, qr_svg

PILLS = {"events": "فعاليات", "cinema": "سينما", "fixtures": "مباريات", "worth": "أماكن", "podcast": "بودكاست"}


def _section(payload, key):
    for s in payload.get("sections") or []:
        if s.get("key") == key and s.get("items"):
            return s
    return None


def _photo_card(item, section_key, wide=False):
    art = item.get("art") or {}
    has_img = art.get("kind") in ("owned", "og", "poster", "commons") and art.get("src")
    w, h = int(art.get("w") or 0), int(art.get("h") or 0)
    ratio = ' style="aspect-ratio:%d/%d"' % (w, h) if (has_img and w and h) else ' style="aspect-ratio:16/10"'
    img = ('<img src="%s" alt="">' % esc(art["src"])) if has_img else '<div class="ph">%s</div>' % esc((item.get("ttl") or "•")[:1])
    return (
        '<div class="pc%s">'
        '<div class="pimg"%s>%s<span class="pill">%s</span>%s</div>'
        '<div class="pttl">%s</div><div class="psub">%s</div>%s'
        '</div>'
    ) % (" wide" if wide else "", ratio, img, esc(item.get("chip", "")), qr_svg(item.get("url", "")),
         bidi(item.get("ttl", "")), bidi(item.get("sub", "")), _ratings(item) if section_key == "cinema" else "")


def _fixtures(sec):
    rows = []
    for it in sec.get("items") or []:
        lg = it.get("logos") or {}
        rows.append('<div class="fx"><div class="fxt">%s<span>%s</span></div><span class="fxv">×</span>'
                    '<div class="fxt"><span>%s</span>%s</div><div class="fxw">%s</div></div>'
                    % (('<img src="%s" alt="">' % esc(lg["home"])) if lg.get("home") else "", esc(it.get("home", "")),
                       esc(it.get("away", "")), ('<img src="%s" alt="">' % esc(lg["away"])) if lg.get("away") else "",
                       esc(it.get("when", ""))))
    return '<div class="block fixb"><div class="bh">%s <span class="bhs">%s</span></div>%s</div>' % (
        esc(sec.get("title", "")), esc(sec.get("comp", "")), "".join(rows))


def css():
    st = fonts.stacks()
    return """
html,body{margin:0;padding:0;background:var(--paper)}
body{font-family:%(sans)s;color:var(--ink);direction:rtl;-webkit-print-color-adjust:exact;print-color-adjust:exact}
*{box-sizing:border-box}
.poster{width:540px;padding:26px 22px 30px;background:var(--paper);display:flex;flex-direction:column;gap:14px}
.hdr{display:flex;justify-content:space-between;align-items:center}
.brand{font-family:%(serif)s;font-weight:900;font-size:26px;color:var(--ink)}
.brand small{display:block;font-family:%(sans)s;font-weight:500;font-size:10px;letter-spacing:.14em;color:var(--mute)}
.datepill{border:1px solid var(--gold);color:var(--ink);border-radius:999px;padding:6px 14px;font-weight:600;font-size:14px}
.title{font-family:%(serif)s;font-weight:900;font-size:40px;line-height:1.1;margin:4px 0 0}
.pills{display:flex;flex-wrap:wrap;gap:6px}
.pills span{background:var(--white);border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:12px;font-weight:500;color:var(--mute)}
.occ{background:var(--ink);color:var(--gold-2);border-radius:12px;padding:12px 16px;font-family:%(serif)s;font-weight:700;font-size:18px;text-align:center}
.block{background:var(--white);border:1px solid var(--line);border-radius:14px;padding:14px}
.bh{font-weight:600;font-size:13px;letter-spacing:.08em;color:var(--mute);margin:0 0 10px;padding-bottom:6px;border-bottom:2px solid var(--gold);display:inline-block}
.bhs{font-weight:400;letter-spacing:0;margin-inline-start:6px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.pc{display:flex;flex-direction:column;gap:5px;min-width:0}
.pc.wide{grid-column:1 / -1}
.pimg{position:relative;border-radius:10px;overflow:hidden;background:var(--ink);width:100%%}
.pimg img{width:100%%;height:100%%;display:block;object-fit:contain}
.pimg .ph{width:100%%;height:100%%;display:flex;align-items:center;justify-content:center;font-family:%(serif)s;font-weight:900;font-size:64px;color:var(--paper)}
.pill{position:absolute;inset-block-start:8px;inset-inline-start:8px;background:var(--paper);color:var(--ink);border-radius:999px;padding:3px 9px;font-size:10px;font-weight:600}
.pimg .qr{position:absolute;inset-block-end:8px;inset-inline-end:8px;width:52px;height:52px;background:var(--paper);border-radius:6px;padding:2px}
.qr svg{width:100%%;height:100%%;display:block;shape-rendering:crispEdges}
.pttl{font-family:%(serif)s;font-weight:700;font-size:16px;line-height:1.25;margin-top:4px}
.psub{font-size:11px;line-height:1.45;color:var(--mute)}
.rate{display:flex;gap:8px;align-items:center;margin-top:2px}
.imdb{display:inline-flex;align-items:center;gap:5px}
.imdb-logo{background:#F5C518;color:#0B1A2E;font-weight:700;font-size:9px;padding:2px 5px;border-radius:3px;direction:ltr}
.imdb-v{font-family:%(serif)s;font-weight:900;font-size:15px;line-height:1}
.imdb-of{font-size:9px;color:var(--mute)}
.rt{display:inline-flex;align-items:center;gap:4px}
.rt-logo{background:var(--red);color:var(--paper);font-weight:700;font-size:8px;padding:2px 5px;border-radius:3px;direction:ltr}
.rt-v{font-size:11px}
.rnew{font-size:9px;color:var(--mute);border:1px solid var(--line);border-radius:999px;padding:2px 7px}
.fx{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:6px;padding:8px 0;border-top:1px solid var(--line)}
.fxt{display:flex;align-items:center;gap:6px;font-family:%(serif)s;font-weight:700;font-size:15px}
.fxt:last-of-type{justify-content:flex-end}
.fxt img{width:26px;height:26px;object-fit:contain}
.fxv{color:var(--gold);font-size:12px}
.fxw{grid-column:1 / -1;font-size:11px;color:var(--mute);text-align:center;margin-top:-2px}
.verse{background:var(--ink);color:var(--paper);border-radius:14px;padding:18px 18px 14px;text-align:center}
.verse .t{font-family:%(serif)s;font-weight:700;font-size:19px;line-height:1.8}
.verse .qm{color:var(--gold-2);font-weight:400}
.verse .r{font-size:11px;color:var(--gold-2);margin-top:6px;letter-spacing:.04em}
.say{text-align:center;padding:6px 10px}
.say .t{font-family:%(serif)s;font-weight:700;font-size:17px;line-height:1.6}
.say .b{font-size:11px;color:var(--mute);margin-top:4px}
.credit{font-size:9px;color:var(--mute);text-align:center}
.ftr{display:flex;justify-content:space-between;font-size:10px;color:var(--mute);border-top:1px solid var(--line);padding-top:10px;margin-top:4px}
""" % st


def build_poster(payload, art_map=None):
    sections = payload.get("sections") or []
    present = [s for s in sections if s.get("items")]
    pills = "".join("<span>%s</span>" % esc(PILLS.get(s["key"], s["key"])) for s in present)
    oc = payload.get("occasion") or {}
    blocks = []
    ev = _section(payload, "events")
    if ev:
        items = ev["items"]
        cards = "".join(_photo_card(it, "events", wide=(len(items) % 2 == 1 and i == 0)) for i, it in enumerate(items))
        blocks.append('<div class="block"><div class="bh">%s</div><div class="grid2">%s</div></div>' % (esc(ev["title"]), cards))
    ci = _section(payload, "cinema")
    if ci:
        cards = "".join(_photo_card(it, "cinema") for it in ci["items"])
        blocks.append('<div class="block"><div class="bh">%s</div><div class="grid3">%s</div></div>' % (esc(ci["title"]), cards))
    wo = _section(payload, "worth")
    po = _section(payload, "podcast")
    if wo or po:
        cards = "".join(_photo_card(s["items"][0], s["key"]) for s in (wo, po) if s)
        title = " · ".join(s["title"] for s in (wo, po) if s)
        blocks.append('<div class="block"><div class="bh">%s</div><div class="grid2">%s</div></div>' % (esc(title), cards))
    fx = _section(payload, "fixtures")
    if fx:
        blocks.append(_fixtures(fx))
    v = payload.get("verse") or {}
    if v.get("text"):
        blocks.append('<div class="verse"><div class="t"><span class="qm">﴿</span> %s <span class="qm">﴾</span></div><div class="r">%s</div></div>'
                      % (esc(v["text"]), esc(v.get("ref_ar", ""))))
    sy = payload.get("saying") or {}
    if sy.get("text"):
        blocks.append('<div class="say"><div class="t">%s</div><div class="b">%s</div></div>' % (esc(sy["text"]), esc(sy.get("by", ""))))
    credits = []
    for s in sections:
        for it in s.get("items") or []:
            cr = (it.get("art") or {}).get("credit")
            if cr and cr not in credits:
                credits.append(cr)
    return (
        '<!doctype html>' + NL + '<html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>poster</title>'
        '<style>' + NL + '%s' + NL + '%s' + NL + '%s' + NL + '</style></head><body>'
        '<div class="poster">'
        '<div class="hdr"><div class="brand">عوجا<small>OUJA RESIDENCE · الرياض</small></div><div class="datepill">%s</div></div>'
        '<h1 class="title">وش صاير بالرياض</h1>'
        '<div class="pills">%s</div>'
        '%s'
        '%s'
        '%s'
        '<div class="ftr"><span>العدد %s · كل رابط تحققنا منه قبل النشر</span><span dir="ltr">oujares.com</span></div>'
        '</div></body></html>'
    ) % (tokens.css_root(), fonts.font_faces(), css(), esc(payload.get("dateLabel", "")), pills,
         ('<div class="occ">%s</div>' % esc(oc["banner_ar"])) if oc.get("banner_ar") else "",
         "".join(blocks), ('<div class="credit">%s</div>' % esc(" · ".join(credits))) if credits else "",
         esc(payload.get("issue", "")))
