# -*- coding: utf-8 -*-
"""digest.render.html — pure: payload -> HTML. No network, no host, no db.

One idea per screen (the memo's rule): cover, events, cinema, fixtures, worth, back.
A section with no items is simply not a page. Every page has one .eyebrow (the only
decoration budget: a 2px gold rule) one .claim (a sentence, not a label) and one .foot
(where it came from / when it was checked). Colours come from tokens.py only; fonts from
fonts.py; artwork of kind 'generated' from digest.art_generated (deterministic).

THIS FILE CONTAINS ZERO BACKSLASH CHARACTERS (the DASHBOARD_HTML trap)."""

import html as _html
import re

from .. import art_generated
from ..dates import AR_DAY, RIYADH, ar_date, ar_digits
from . import fonts, tokens

SITE_LABEL = "oujares.com"
_ARABIC = re.compile("[؀-ۿ]")
_LATIN = re.compile("[A-Za-z]")
NL = chr(10)


def esc(s):
    return _html.escape(str(s if s is not None else ""), quote=True)


def bidi(s):
    """Latin-only runs sit inside <span dir=ltr>; Arabic (or mixed) stays native RTL."""
    t = str(s or "")
    if _LATIN.search(t) and not _ARABIC.search(t):
        return '<span dir="ltr">%s</span>' % esc(t)
    return esc(t)


def qr_svg(url):
    """Offline QR (segno): navy modules, error correction M, quiet zone 4, as inline SVG
    with a viewBox so CSS decides the printed size (>= 22 mm)."""
    import segno                       # lazy: a missing library fails the BUILD, not the routes
    q = segno.make(url, error="m")
    w, h = q.symbol_size(scale=1, border=4)
    s = q.svg_inline(scale=1, border=4, dark=tokens.TOKENS["ink"], light=None)
    s = s.replace("<svg ", '<svg viewBox="0 0 %d %d" ' % (w, h), 1)
    return '<div class="qr" data-url="%s">%s</div>' % (esc(url), s)


def _ratio_style(art, fallback):
    """The box takes the IMAGE's ratio (owner rule 2026-09-03: never crop). Falls back
    to the layout's default ratio when the payload carries no size."""
    w, h = int(art.get("w") or 0), int(art.get("h") or 0)
    if w > 0 and h > 0:
        return ' style="aspect-ratio:%d/%d"' % (w, h)
    return ' style="aspect-ratio:%s"' % fallback


def _art(item, section_key, issue, slot, art_map):
    """-> inner HTML for the card's artwork, or '' for a type-only card."""
    art = item.get("art") or {}
    kind = art.get("kind") or "none"
    override = (art_map or {}).get((section_key, slot))
    if override and override.get("kind") in ("owned", "og", "poster") and override.get("src"):
        art = dict(art, **override)
        kind = override["kind"]
    if kind in ("owned", "og", "poster") and art.get("src"):
        cls = "art art-photo" + (" art-poster" if kind == "poster" else "")
        return '<div class="%s"%s><img src="%s" alt=""></div>' % (cls, _ratio_style(art, "2/3" if kind == "poster" else "16/9"), esc(art["src"]))
    if kind == "generated":
        seed = "%s|%s|%s" % (issue, section_key, slot)
        shape = "portrait" if section_key == "cinema" else "square"
        w, h = art_generated.KINDS[shape]
        return '<div class="art art-%s" style="aspect-ratio:%d/%d">%s</div>' % (shape, w, h, art_generated.svg(seed, item.get("ttl", ""), shape, label=item.get("ttl", "")))
    return ""


def _ratings(item):
    r = item.get("ratings") or {}
    bits = []
    if r.get("imdb") is not None:
        bits.append('<span class="rk">IMDb</span> <span class="rv">%s</span>' % esc(ar_digits("%.1f" % float(r["imdb"])).replace(".", "٫")))
    if r.get("rt") is not None:
        bits.append('<span class="rk">RT</span> <span class="rv">%s٪</span>' % esc(ar_digits(str(int(r["rt"])))))
    if not bits:
        return ""
    return '<div class="rate">%s</div>' % " · ".join(bits)


def _card(item, section_key, issue, slot, art_map, big=False):
    """[art][body: ttl, sub, row(meta + qr)] — CSS decides whether art sits above
    (grid cards) or beside (list cards) the body."""
    parts = ['<div class="card%s">' % (" card-big" if big else "")]
    parts.append(_art(item, section_key, issue, slot, art_map))
    parts.append('<div class="body">')
    parts.append('<div class="ttl">%s</div>' % bidi(item.get("ttl", "")))
    if item.get("sub"):
        parts.append('<div class="sub%s">%s</div>' % (" big-sub" if big else "", bidi(item.get("sub", ""))))
    parts.append(_ratings(item))
    if big and item.get("hook"):
        parts.append('<div class="hook">%s</div>' % bidi(item.get("hook", "")))
    parts.append('<div class="row"><div class="meta"><span class="chip">%s</span><span class="day">%s</span></div>%s</div>'
                 % (esc(item.get("chip", "")), esc(AR_DAY.get(item.get("day", ""), "")), qr_svg(item.get("url", ""))))
    parts.append("</div></div>")
    return "".join(parts)


def _foot(sources, checked_label, page_no, extra=""):
    src = " · ".join(sorted(set(s for s in sources if s))) or "عوجا"
    return ('<div class="foot"><span>المصدر: %s · آخر تحقق من الروابط %s%s</span><span class="pn">%s</span></div>'
            % (esc(src), esc(checked_label), (" · " + esc(extra)) if extra else "", ar_digits("%02d" % page_no)))


def _sources_of(section):
    return [(it.get("source") or {}).get("name", "") for it in section.get("items") or []]


def _checked_label(payload):
    ts = payload.get("generated_at") or ""
    try:
        from datetime import datetime
        d = datetime.fromisoformat(ts).astimezone(RIYADH)
        return "%s %s" % ({0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس", 4: "الجمعة", 5: "السبت", 6: "الأحد"}[d.weekday()], ar_date(d.date()))
    except Exception:
        return "قبل الطباعة"


def _section(payload, key):
    for s in payload.get("sections") or []:
        if s.get("key") == key and s.get("items"):
            return s
    return None


# ---------------- pages ----------------

def page_cover(payload, checked, n, contents=()):
    issue = payload.get("issue", "")
    toc = "".join('<div><span>%s</span><span class="n">%s</span></div>' % (esc(t), ar_digits("%02d" % pn)) for t, pn in contents)
    return (
        '<section class="page navy cover">'
        '<div class="eyebrow">عوجا · نشرة نهاية الأسبوع · العدد %s</div>'
        '<div class="num">%s</div>'
        '<h1 class="claim">وش صاير بالرياض</h1>'
        '<div class="lede">فعاليات، سينما، مباريات، ومكان يستاهل. كل رابط فيه تحققنا منه قبل الطباعة.</div>'
        '<div class="toc">%s</div>'
        '%s</section>'
    ) % (esc(issue), esc(payload.get("dateLabel", "")), toc, _foot(["عوجا"], checked, n, extra="امسح أي رمز وتوصل للصفحة الرسمية"))


def page_events(payload, sec, issue, checked, n, art_map):
    items = sec["items"]
    layout = sec.get("layout") or "g2"
    lead = items[0]
    claim = sec.get("claim") or "%s: %s" % (AR_DAY.get(lead.get("day", ""), ""), lead.get("ttl", ""))
    cards = "".join(_card(it, "events", issue, i, art_map) for i, it in enumerate(items))
    return (
        '<section class="page events"><div class="eyebrow">%s</div>'
        '<h1 class="claim">%s</h1>'
        '<div class="grid %s">%s</div>%s</section>'
    ) % (esc(sec.get("title", "")), bidi(claim), esc(layout), cards, _foot(_sources_of(sec), checked, n))


def page_cinema(payload, sec, issue, checked, n, art_map):
    items = sec["items"]
    claim = sec.get("claim") or "ثلاثة أفلام على الشاشة هالأسبوع"
    cards = "".join(_card(it, "cinema", issue, i, art_map) for i, it in enumerate(items))
    return (
        '<section class="page cinema"><div class="eyebrow">%s</div>'
        '<h1 class="claim">%s</h1>'
        '<div class="grid g3">%s</div>%s</section>'
    ) % (esc(sec.get("title", "")), bidi(claim), cards,
         _foot(_sources_of(sec), checked, n, extra="التقييمات من IMDb وRotten Tomatoes كما فُتحت وقت الطباعة" if any((it.get("ratings") or {}).get("sources") for it in items) else "التذاكر من صفحة الفيلم"))


def page_fixtures(payload, sec, issue, checked, n, art_map):
    items = sec["items"]
    head = next((it for it in items if it.get("in_riyadh")), items[0])
    claim = sec.get("claim") or "%s: %s و%s" % (head.get("when", ""), head.get("home", ""), head.get("away", ""))
    lg = head.get("logos") or {}
    if lg.get("home") and lg.get("away"):
        band = ('<div class="lband"><div class="club"><img src="%s" alt=""><span>%s</span></div>'
                '<span class="vsbig">×</span><div class="club"><img src="%s" alt=""><span>%s</span></div></div>'
                % (esc(lg["home"]), esc(head.get("home", "")), esc(lg["away"]), esc(head.get("away", ""))))
    else:
        band = '<div class="band">%s</div>' % art_generated.svg("%s|fixtures|band" % issue, (head.get("home", ""), head.get("away", "")), "band",
                                                                label="%s – %s" % (head.get("home", ""), head.get("away", "")))
    rows = []
    for it in items:
        l2 = it.get("logos") or {}
        home = ('<img class="tl" src="%s" alt="">' % esc(l2["home"]) if l2.get("home") else "") + esc(it.get("home", ""))
        away = esc(it.get("away", "")) + ('<img class="tl" src="%s" alt="">' % esc(l2["away"]) if l2.get("away") else "")
        rows.append('<tr><td class="when">%s</td><td class="teams">%s <span class="vs">×</span> %s</td><td class="where">%s</td></tr>'
                    % (esc(it.get("when", "")), home, away, esc(it.get("stadium", "") or it.get("city", "") or "")))
    return (
        '<section class="page fixtures"><div class="eyebrow">%s · %s</div>'
        '<h1 class="claim">%s</h1>'
        '%s'
        '<table class="fix"><thead><tr><th>متى</th><th>المباراة</th><th>وين</th></tr></thead><tbody>%s</tbody></table>'
        '<div class="row end">%s<div class="hint">جدول الجولة كامل على صفحة الاتحاد السعودي</div></div>%s</section>'
    ) % (esc(sec.get("title", "")), esc(sec.get("comp", "")), bidi(claim), band, "".join(rows),
         qr_svg(head.get("url", "")), _foot(_sources_of(sec), checked, n, extra="التوقيت بتوقيت الرياض"))


def page_worth(payload, sec, issue, checked, n, art_map):
    it = sec["items"][0]
    claim = sec.get("claim") or it.get("ttl", "")
    return (
        '<section class="page worth"><div class="eyebrow">%s</div>'
        '<h1 class="claim">%s</h1>'
        '<div class="grid g1">%s</div>%s</section>'
    ) % (esc(sec.get("title", "")), bidi(claim),
         _card(it, "worth", issue, 0, art_map, big=True), _foot(_sources_of(sec), checked, n))


def page_back(payload, checked, n):
    srcs = []
    seen = set()
    for s in payload.get("sections") or []:
        for it in s.get("items") or []:
            src = it.get("source") or {}
            key = (src.get("name"), src.get("url"))
            if src.get("name") and key not in seen:
                seen.add(key)
                srcs.append('<div class="src"><span class="sname">%s</span><span dir="ltr" class="surl">%s</span></div>'
                            % (esc(src["name"]), esc(src.get("url", ""))))
    dropped = payload.get("dropped") or []
    drops = "".join('<div class="drop"><span class="dttl">%s</span><span class="dwhy">%s</span></div>'
                    % (bidi(d.get("ttl", "")), esc(d.get("reason", ""))) for d in dropped)
    site = payload.get("site_url") or ""
    return (
        '<section class="page navy back"><div class="eyebrow">وين جبنا الكلام</div>'
        '<h1 class="claim">كل سطر فوق له صفحة رسمية</h1>'
        '<div class="lede">إذا ما لقينا مصدر موثوق لشي، ما كتبناه. هذي الصفحات اللي رجعنا لها، واللي حذفناه وليش.</div>'
        '<div class="srcs">%s</div>'
        '%s'
        '<div class="row end">%s<div class="hint">شققنا وعروض الأسبوع على موقع عوجا</div></div>%s</section>'
    ) % (srcs and "".join(srcs) or "", ('<div class="drops"><div class="h">حذفناه</div>%s</div>' % drops) if drops else "",
         qr_svg(site) if site else "", _foot(["عوجا"], checked, n, extra=SITE_LABEL))


def css_pages():
    st = fonts.stacks()
    return """
@page{size:810pt 1440pt;margin:0}
html,body{margin:0;padding:0;background:var(--paper)}
body{font-family:%(sans)s;color:var(--ink);direction:rtl;-webkit-print-color-adjust:exact;print-color-adjust:exact}
*{box-sizing:border-box}
.page{position:relative;width:810pt;height:1440pt;overflow:hidden;padding:84pt 60pt 96pt;page-break-after:always;background:var(--paper);display:flex;flex-direction:column}
.page:last-child{page-break-after:auto}
.page.navy{background:linear-gradient(180deg,var(--ink-2) 0%%,var(--ink) 100%%);color:var(--paper)}
.eyebrow{align-self:flex-start;font-weight:500;font-size:15pt;line-height:1;letter-spacing:.12em;color:var(--mute);padding-block-end:10pt;border-block-end:2.5px solid var(--gold);margin-block-end:34pt}
.navy .eyebrow{color:var(--gold-2)}
.claim{font-family:%(serif)s;font-weight:900;font-size:62pt;line-height:1.16;margin:0 0 22pt;letter-spacing:-.005em}
.cover .claim{font-size:84pt;margin-block-start:6pt}
.cover .num{font-family:%(serif)s;font-weight:900;font-size:150pt;line-height:1;margin-block-start:150pt;color:var(--gold-2)}
.lede{font-weight:400;font-size:22pt;line-height:1.6;color:var(--mute);max-width:600pt;margin:0 0 36pt}
.navy .lede{color:var(--paper);opacity:.82}
.toc{margin-block-start:auto;display:flex;flex-direction:column;gap:0;padding-block-end:30pt}
.toc div{display:flex;justify-content:space-between;align-items:baseline;padding-block:14pt;border-block-start:1px solid var(--ink-3);font-size:20pt}
.toc .n{font-family:%(serif)s;font-weight:700;color:var(--gold-2);font-size:24pt}
.grid{display:grid;gap:22pt;align-content:start;flex:1 1 auto;min-height:0}
.g2{grid-template-columns:1fr 1fr}
.g2h{grid-template-columns:1fr}
.g2h .card .art{width:auto;height:260pt;max-width:100%%;align-self:flex-start}
.g2h .card{padding-block-end:8mm}
.g3v,.g3,.g1{grid-template-columns:1fr}
.g1{grid-auto-rows:max-content;align-items:start;flex:0 0 auto}
.card{background:var(--white);border:1px solid var(--line);border-radius:3mm;padding:6mm;display:flex;flex-direction:column;gap:14pt;min-height:0}
.card .body{display:flex;flex-direction:column;gap:10pt;flex:1 1 auto;min-height:0}
.g3v .card,.g3 .card{flex-direction:row;align-items:stretch;gap:26pt}
.g3v .card .art{flex:0 0 210pt;width:210pt;height:210pt}
.g3v .card .art-photo{flex:0 0 260pt;width:260pt;height:auto;align-self:flex-start}
.g3 .card .art{flex:0 0 180pt;width:180pt;height:240pt}
.g3 .card .art-poster{flex:0 0 170pt;width:170pt;height:auto;align-self:flex-start}
.g2 .card .art{width:100%%}
.card-big{padding:10mm}
.card-big .ttl{font-size:64pt;line-height:1.1}
.card-big .big-sub{font-size:26pt;line-height:1.55;margin-block-start:6pt;max-width:520pt}
.card-big .row{margin-block-start:34pt}
.card-big .qr{width:38mm;height:38mm;flex-basis:38mm}
.card-big .art{aspect-ratio:4/3}
.art{border-radius:2mm;overflow:hidden;background:var(--ink);aspect-ratio:1/1;flex:0 0 auto}
.art-portrait{aspect-ratio:3/4}
.art svg,.art img{width:100%%;height:100%%;display:block;object-fit:contain}
.art-photo{background:var(--ink)}
.g3v .card .art-photo,.g3 .card .art-poster{height:auto}
.rate{display:flex;gap:10pt;font-size:15pt;color:var(--mute);letter-spacing:.02em}
.rate .rk{font-weight:700;color:var(--gold)}
.rate .rv{font-weight:500;color:var(--ink)}
.hook{font-size:22pt;line-height:1.5;color:var(--mute);max-width:560pt}
.lband{display:flex;align-items:center;justify-content:space-around;gap:20pt;background:var(--white);border:1px solid var(--line);border-radius:3mm;padding:26pt 20pt;margin-block-end:30pt}
.lband .club{display:flex;flex-direction:column;align-items:center;gap:12pt;font-family:%(serif)s;font-weight:700;font-size:30pt}
.lband .club img{width:170pt;height:170pt;object-fit:contain}
.lband .vsbig{font-size:36pt;color:var(--gold)}
.fix .tl{width:26pt;height:26pt;object-fit:contain;vertical-align:middle;margin-inline:6pt}
.ttl{font-family:%(serif)s;font-weight:700;font-size:36pt;line-height:1.2}
.sub{font-weight:400;font-size:19pt;line-height:1.5;color:var(--ink)}
.row{display:flex;justify-content:space-between;align-items:flex-end;margin-block-start:auto;gap:12pt}
.row.end{justify-content:flex-start;margin-block-start:26pt;align-items:center;gap:18pt}
.row.end .hint{font-size:15pt;color:var(--mute);max-width:300pt;line-height:1.5}
.meta{display:flex;gap:10pt;align-items:center;font-weight:500;font-size:14pt;letter-spacing:.06em;color:var(--mute)}
.chip{border:1px solid var(--line);border-radius:999pt;padding:5pt 12pt}
.qr{width:30mm;height:30mm;flex:0 0 30mm;background:var(--paper);border-radius:1.5mm;padding:0}
.qr svg{width:100%%;height:100%%;display:block;shape-rendering:crispEdges}
.navy .qr{background:var(--paper)}
.band{border-radius:3mm;overflow:hidden;aspect-ratio:2/1;margin-block-end:30pt;background:var(--ink);flex:0 0 auto}
.band svg{width:100%%;height:100%%;display:block}
table.fix{width:100%%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.fix th{font-weight:500;font-size:14pt;letter-spacing:.1em;color:var(--mute);text-align:start;padding:8pt 8pt 12pt;border-block-end:2.5px solid var(--gold)}
.fix td{padding:22pt 8pt;border-block-end:1px solid var(--line);font-size:20pt;vertical-align:middle}
.fix .teams{font-family:%(serif)s;font-weight:700;font-size:30pt;white-space:nowrap}
.fix .vs{color:var(--gold);font-family:%(sans)s;font-weight:400;font-size:18pt;margin-inline:8pt}
.fix .when{font-weight:500;white-space:nowrap;width:210pt}
.fix .where{color:var(--mute);font-size:16pt}
.srcs{display:flex;flex-direction:column;gap:14pt;margin-block-end:34pt}
.src{display:flex;flex-direction:column;gap:4pt;padding-block-end:12pt;border-block-end:1px solid var(--ink-3)}
.sname{font-weight:700;font-size:22pt}
.surl{font-size:14pt;color:var(--gold-2);word-break:break-all;text-align:start}
.drops .h{font-weight:500;font-size:14pt;letter-spacing:.12em;color:var(--gold-2);margin-block-end:12pt}
.drop{display:flex;gap:16pt;font-size:19pt;padding-block:7pt;flex-wrap:wrap}
.dwhy{color:var(--gold-2)}
.foot{position:absolute;inset-inline:60pt;inset-block-end:40pt;display:flex;justify-content:space-between;gap:16pt;font-size:12pt;line-height:1.5;color:var(--mute);border-block-start:1px solid var(--line);padding-block-start:12pt}
.navy .foot{border-color:var(--ink-3);color:var(--gold-2)}
.pn{font-variant-numeric:tabular-nums}
""" % st


def build_pages(payload, art_map=None):
    """The printable document: one <section class=page> per screen."""
    issue = payload.get("issue_no", payload.get("issue", ""))
    checked = _checked_label(payload)
    order = (("events", page_events), ("cinema", page_cinema), ("fixtures", page_fixtures), ("worth", page_worth))
    present = [(key, fn, _section(payload, key)) for key, fn in order]
    present = [(k, f, sec) for k, f, sec in present if sec]
    contents = [(sec.get("title", ""), i + 2) for i, (k, f, sec) in enumerate(present)]
    contents.append(("وين جبنا الكلام", len(present) + 2))
    pages = [page_cover(payload, checked, 1, contents)]
    n = 1
    for key, fn, sec in present:
        n += 1
        pages.append(fn(payload, sec, issue, checked, n, art_map))
    n += 1
    pages.append(page_back(payload, checked, n))
    return (
        '<!doctype html>' + NL + '<html lang="ar" dir="rtl"><head><meta charset="utf-8">'
        '<title>وش صاير بالرياض · %s</title>'
        '<style>' + NL + '%s' + NL + '%s' + NL + '%s' + NL + '</style></head><body>%s</body></html>'
    ) % (esc(payload.get("dateLabel", "")), tokens.css_root(), fonts.font_faces(), css_pages(), "".join(pages))


# ---------------- the story (1080×1920) ----------------

def css_story():
    st = fonts.stacks()
    return """
html,body{margin:0;padding:0;background:var(--ink)}
body{font-family:%(sans)s;color:var(--paper);direction:rtl;-webkit-print-color-adjust:exact;print-color-adjust:exact}
*{box-sizing:border-box}
.story{position:relative;width:540px;height:960px;overflow:hidden;padding:64px 44px 56px;background:linear-gradient(180deg,var(--ink-2) 0%%,var(--ink) 100%%);display:flex;flex-direction:column}
.eyebrow{align-self:flex-start;font-weight:500;font-size:11px;letter-spacing:.14em;color:var(--gold-2);padding-block-end:6px;border-block-end:2px solid var(--gold);margin-block-end:18px}
.num{font-family:%(serif)s;font-weight:900;font-size:64px;line-height:1;color:var(--gold-2);margin-block-end:6px}
.claim{font-family:%(serif)s;font-weight:900;font-size:40px;line-height:1.15;margin:0 0 26px}
.item{display:flex;flex-direction:column;gap:3px;padding-block:14px;border-block-start:1px solid var(--ink-3)}
.item .k{font-weight:500;font-size:10px;letter-spacing:.12em;color:var(--gold-2)}
.item .t{font-family:%(serif)s;font-weight:700;font-size:24px;line-height:1.2}
.item .s{font-size:13px;line-height:1.5;opacity:.85}
.foot{margin-block-start:auto;display:flex;justify-content:space-between;align-items:flex-end;font-size:10px;color:var(--gold-2);border-block-start:1px solid var(--ink-3);padding-block-start:10px}
""" % st


def build_story(payload, art_map=None):
    items = []
    ev = _section(payload, "events")
    if ev:
        it = ev["items"][0]
        items.append(("فعاليات", it.get("ttl", ""), it.get("sub", "")))
    ci = _section(payload, "cinema")
    if ci:
        items.append(("سينما", " · ".join(x.get("ttl", "") for x in ci["items"][:3]), ci["items"][0].get("sub", "")))
    fx = _section(payload, "fixtures")
    if fx:
        head = next((x for x in fx["items"] if x.get("in_riyadh")), fx["items"][0])
        items.append(("مباريات", "%s × %s" % (head.get("home", ""), head.get("away", "")), head.get("when", "")))
    wo = _section(payload, "worth")
    if wo:
        it = wo["items"][0]
        items.append(("يستاهل الزيارة", it.get("ttl", ""), it.get("sub", "")))
    rows = "".join('<div class="item"><div class="k">%s</div><div class="t">%s</div><div class="s">%s</div></div>'
                   % (esc(k), bidi(t), bidi(s)) for k, t, s in items)
    return (
        '<!doctype html>' + NL + '<html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>story</title>'
        '<style>' + NL + '%s' + NL + '%s' + NL + '%s' + NL + '</style></head><body>'
        '<div class="story"><div class="eyebrow">عوجا · وش صاير بالرياض</div>'
        '<div class="num">%s</div><h1 class="claim">خطة نهاية الأسبوع، جاهزة</h1>%s'
        '<div class="foot"><span>العدد %s · النشرة كاملة عند الاستقبال وفي الشقة</span><span dir="ltr">%s</span></div>'
        '</div></body></html>'
    ) % (tokens.css_root(), fonts.font_faces(), css_story(), esc(payload.get("dateLabel", "")), rows,
         esc(payload.get("issue", "")), esc(SITE_LABEL))
