# -*- coding: utf-8 -*-
"""
site_home.render — pure functions from (page, lang, identity) to a complete HTML page.

No I/O, no network, no database, no thread: every call is string assembly over
SITE_IDENTITY + content.py, so "/" answers in microseconds even when Hostaway is
throttled (CLAUDE.md trap 6). Every identity value is HTML-escaped on the way in.

Visual world = the /apartments guest site (warm sand + gold) set in the Thmanyah
faces /monthly already serves. No JavaScript at all.
"""
import datetime
import html
import json

from . import content
from .identity import SITE_IDENTITY

try:   # the self-hosted Thmanyah faces /monthly already serves — no new CDN
    from monthly_public.fonts import FONT_CSS_PATH, PRELOAD_FONT_PATH
except Exception:  # pragma: no cover — the monthly package is part of the repo
    FONT_CSS_PATH = PRELOAD_FONT_PATH = ""

# page key -> (Arabic path, English path)
PATHS = {
    "home": ("/", "/en"),
    "privacy": ("/privacy", "/en/privacy"),
    "terms": ("/terms", "/en/terms"),
    "contact": ("/contact", "/en/contact"),
}

_FALLBACK = {"email": "", "whatsapp": ""}   # filled by site_home.wire()


def set_fallbacks(email="", whatsapp=""):
    _FALLBACK["email"] = email or ""
    _FALLBACK["whatsapp"] = whatsapp or ""


def _e(s):
    return html.escape(str(s or ""), quote=True)


def _pct(s):
    """Percent-encode for a mailto: query (no urllib — this package stays import-light)."""
    safe = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~")
    return "".join(chr(b) if b in safe else "%%%02X" % b for b in str(s).encode("utf-8"))


def _ident():
    """SITE_IDENTITY plus the resolved contact values."""
    d = dict(SITE_IDENTITY)
    d["email"] = (d.get("email") or _FALLBACK["email"] or "").strip()
    phone = "".join(c for c in str(d.get("phone") or _FALLBACK["whatsapp"] or "") if c.isdigit())
    d["phone"] = phone
    return d


def _phone_display(digits):
    if digits.startswith("966") and len(digits) == 12:
        return "+966 %s %s %s" % (digits[3:5], digits[5:8], digits[8:])
    return "+" + digits


def path_for(page, lang):
    ar, en = PATHS[page]
    return en if lang == "en" else ar


# ---------------------------------------------------------------------------
# Icons — one authored set: 24px grid, 1.6 stroke, round caps.
# ---------------------------------------------------------------------------
_ICON = {
    "arrow": '<path d="M5 12h13M13 6l6 6-6 6"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M4 7l8 6 8-6"/>',
    "chat": '<path d="M4 19.5l1.4-4.1A8 8 0 1 1 8.6 18.6L4 19.5z"/><path d="M9 10.5h6M9 13.5h4"/>',
    "pin": '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.6v.2"/>',
    "seal": '<path d="M12 3l2.2 1.6 2.7-.1.8 2.6 2.2 1.6-.9 2.6.9 2.6-2.2 1.6-.8 2.6-2.7-.1L12 21l-2.2-1.6-2.7.1-.8-2.6-2.2-1.6.9-2.6-.9-2.6 2.2-1.6.8-2.6 2.7.1z"/><path d="M9 12.2l2 2 4-4.2"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 2"/>',
    "instagram": '<rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="4"/><path d="M17.2 6.8v.1"/>',
    "tiktok": '<path d="M14 4v10.5a3.5 3.5 0 1 1-3.5-3.5"/><path d="M14 4c.4 2.6 2.2 4.4 5 4.6"/>',
}


def _icon(name, cls="ic"):
    return ('<svg class="%s" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" '
            'focusable="false" fill="none" stroke="currentColor" stroke-width="1.6" '
            'stroke-linecap="round" stroke-linejoin="round">%s</svg>' % (cls, _ICON[name]))


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
_CSS = """
:root{
  color-scheme:light;
  --bg:#F7F1E6;--surface:#FFFDF8;--ink:#2F241B;--mut:#6B5B49;
  --gold:#B88935;--gold-ink:#7E5A1E;--line:#E5D8C4;--line-2:#D6C4A6;--sand:#EFE5D3;
  --foot:#2A211A;--foot-ink:#F7F1E6;--foot-mut:#CDBFA8;--foot-line:#4A3B2E;--foot-gold:#D4B27C;
  --ease:cubic-bezier(.23,1,.32,1);
  --sans:"Thmanyah Sans","IBM Plex Sans Arabic","Segoe UI",Tahoma,sans-serif;
  --display:"Thmanyah Serif Display","Thmanyah Sans","IBM Plex Sans Arabic",serif;
  --page:1160px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:17px;line-height:1.75;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
[lang=en] body{line-height:1.65}
::selection{background:#E9D6AE;color:var(--ink)}
img{max-width:100%;height:auto}
a{color:var(--gold-ink);text-decoration-line:underline;text-decoration-thickness:1px;
  text-underline-offset:.28em;text-decoration-color:var(--line-2)}
a:hover{text-decoration-color:currentColor}
:focus-visible{outline:2px solid var(--gold-ink);outline-offset:3px;border-radius:4px}
.wrap{max-width:var(--page);margin:0 auto;padding:0 20px}
.ltr{direction:ltr;unicode-bidi:isolate}
.num{font-variant-numeric:tabular-nums lining-nums;letter-spacing:.01em}
.ic{flex:none;width:20px;height:20px}
[dir=rtl] .ic-flip{transform:scaleX(-1)}
.skip{position:absolute;inset-inline-start:12px;top:-60px;background:var(--ink);color:var(--surface);
  padding:10px 14px;border-radius:8px;z-index:10;text-decoration:none}
.skip:focus{top:12px}

/* header */
.site-head{border-bottom:1px solid var(--line)}
.site-head .wrap{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:76px}
.brand{display:flex;align-items:center;gap:12px;text-decoration:none;color:var(--ink)}
.brand img{width:40px;height:auto;display:block}
.brand b{font-family:var(--display);font-weight:700;font-size:1.15rem;line-height:1.2}
.nav{display:flex;align-items:center;gap:6px}
.nav a{display:inline-flex;align-items:center;min-height:44px;padding:0 12px;border-radius:999px;
  color:var(--ink);text-decoration:none;font-weight:500;font-size:.95rem;
  transition:background-color .18s var(--ease)}
.nav a:hover{background:var(--sand)}
.nav .lang{border:1px solid var(--line-2)}

/* home */
.home{display:grid;gap:56px;padding:48px 0 80px}
.intro h1{font-family:var(--display);font-weight:700;font-size:clamp(2rem,1.35rem + 2.7vw,3.4rem);
  line-height:1.2;letter-spacing:-.01em;margin:0 0 20px;text-wrap:balance;max-width:16ch}
[lang=en] .intro h1{letter-spacing:-.02em;max-width:18ch}
.intro p{margin:0;max-width:60ch;color:var(--mut);font-size:1.1rem}
h2{font-family:var(--display);font-weight:700;font-size:1.55rem;line-height:1.3;margin:0 0 18px;text-wrap:balance}
.services ul{list-style:none;margin:0;padding:0;border-top:1px solid var(--line-2)}
.services li{border-bottom:1px solid var(--line-2)}
.row{display:grid;grid-template-columns:1fr;gap:6px;padding:22px 4px;text-decoration:none;color:var(--ink);
  transition:background-color .2s var(--ease)}
.row h3{margin:0;font-family:var(--display);font-weight:700;font-size:1.3rem;line-height:1.35}
.row p{margin:0;color:var(--mut);max-width:52ch}
.row .go{display:inline-flex;align-items:center;gap:8px;color:var(--gold-ink);font-weight:600;font-size:.95rem;margin-top:6px}
.row .go .ic{transition:transform .2s var(--ease)}
.row:hover{background:var(--surface)}
.row:hover .go .ic{transform:translateX(4px)}
[dir=rtl] .row:hover .go .ic{transform:scaleX(-1) translateX(4px)}
.owners p,.reach p{margin:0 0 14px;max-width:62ch;color:var(--mut)}

/* the official card */
.official{background:var(--surface);border:1px solid var(--line-2);border-radius:14px;
  box-shadow:0 1px 0 rgba(47,36,27,.04),0 14px 34px -18px rgba(47,36,27,.22);overflow:hidden;align-self:start}
.official header{padding:22px 24px 18px;border-bottom:1px solid var(--line);
  background:linear-gradient(to bottom,#FBF6EC,var(--surface))}
.official header .seal{display:flex;align-items:center;gap:10px;color:var(--gold-ink)}
.official h2{margin:0;font-size:1.3rem}
.official header p{margin:4px 0 0;color:var(--mut);font-size:.9rem}
.official dl{margin:0;padding:6px 24px 10px}
.official dl > div{display:grid;grid-template-columns:1fr;gap:2px;padding:12px 0;border-bottom:1px dashed var(--line)}
.official dl > div:last-child{border-bottom:0}
.official dt{color:var(--mut);font-size:.86rem}
.official dd{margin:0;font-weight:600;overflow-wrap:break-word}
.official dd a{word-break:keep-all;overflow-wrap:normal}
.official dd .sub{display:block;font-weight:400;color:var(--mut);font-size:.92rem}
.official .big{font-size:1.2rem;letter-spacing:.02em}
.official h3{margin:0;padding:16px 24px 4px;font-family:var(--sans);font-size:.86rem;font-weight:600;
  color:var(--gold-ink);border-top:1px solid var(--line-2)}
.official .lic{list-style:none;margin:0;padding:4px 24px 18px}
.official .lic li{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding:10px 0;
  border-bottom:1px dashed var(--line)}
.official .lic li:last-child{border-bottom:0}
.official .lic span{display:block;color:var(--mut);font-size:.86rem;font-weight:400}
.official .lic strong{font-weight:600}
.official .lic .num{font-weight:600;white-space:nowrap}

.notice{display:flex;gap:12px;align-items:flex-start;padding:16px 18px;border-radius:12px;
  background:var(--sand);color:var(--ink);font-weight:500;max-width:72ch}
.notice .ic{color:var(--gold-ink);margin-top:3px}
.btn{display:inline-flex;align-items:center;gap:10px;min-height:48px;padding:0 22px;border-radius:999px;
  background:var(--ink);color:var(--surface);text-decoration:none;font-weight:600;
  transition:transform .16s var(--ease),background-color .2s var(--ease)}
.btn:hover{background:#45362A}
.btn:active{transform:scale(.97)}
.btn:focus-visible{outline-color:var(--gold-ink)}

/* legal pages */
.doc{padding:48px 0 80px;max-width:74ch}
.doc h1{font-family:var(--display);font-weight:700;font-size:clamp(1.9rem,1.4rem + 1.8vw,2.7rem);
  line-height:1.25;margin:0 0 10px;text-wrap:balance}
.doc .stamp{color:var(--mut);font-size:.9rem;margin:0 0 26px}
.doc .lead{font-size:1.1rem;margin:0 0 30px}
.doc section{margin-top:38px}
.doc h2{font-size:1.3rem;margin-bottom:10px}
.doc h3{font-family:var(--sans);font-size:1.02rem;font-weight:600;margin:24px 0 8px}
.doc p{margin:0 0 12px}
.doc ul,.doc ol{margin:0 0 14px;padding-inline-start:1.3em}
.doc li{margin:0 0 6px}
.doc li::marker{color:var(--gold)}
.doc .notice{margin-top:40px}
.doc .channels{list-style:none;margin:0;padding:0;border-top:1px solid var(--line-2)}
.channels li{display:flex;gap:14px;align-items:flex-start;padding:16px 2px;border-bottom:1px solid var(--line-2)}
.channels .ic{color:var(--gold-ink);margin-top:4px}
.channels b{display:block;font-weight:600}
.channels span{color:var(--mut)}
.promise{display:flex;gap:12px;align-items:flex-start;margin:0 0 18px;padding:18px 20px;border-radius:12px;
  background:var(--surface);border:1px solid var(--line-2);font-weight:600;font-size:1.05rem}
.promise .ic{color:var(--gold-ink);margin-top:4px}

/* footer */
.site-foot{background:var(--foot);color:var(--foot-ink);font-size:.95rem;line-height:1.7}
.site-foot a{color:var(--foot-ink);text-decoration-color:var(--foot-line)}
.site-foot a:hover{text-decoration-color:currentColor}
.site-foot :focus-visible{outline-color:var(--foot-gold)}
.foot-grid{display:grid;gap:34px;padding:52px 0 34px}
.foot-brand img{width:46px;height:auto;filter:invert(1) brightness(1.6);opacity:.92;display:block;margin-bottom:14px}
.foot-brand b{display:block;font-family:var(--display);font-size:1.15rem;font-weight:700}
.foot-brand p{margin:6px 0 0;color:var(--foot-mut)}
.foot-brand .ltr{color:var(--foot-ink)}
.site-foot h2{font-family:var(--sans);font-size:.82rem;font-weight:600;color:var(--foot-gold);margin:0 0 10px;letter-spacing:.02em}
.site-foot ul{list-style:none;margin:0;padding:0}
.site-foot li{margin:0 0 6px}
.foot-contact li{display:flex;gap:10px;align-items:center}
.foot-contact .ic{color:var(--foot-gold)}
.social{display:flex;gap:8px;margin-top:12px}
.social a{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:999px;
  border:1px solid var(--foot-line);transition:border-color .2s var(--ease)}
.social a:hover{border-color:var(--foot-gold)}
.foot-legal{border-top:1px solid var(--foot-line);padding:22px 0;display:grid;gap:14px}
.licence-travel{margin:0;color:var(--foot-ink)}
.licence-travel .num{color:var(--foot-gold)}
.badge-bsa{display:inline-flex;align-items:center;gap:10px;text-decoration:none}
.badge-bsa img{height:56px;width:auto;background:#fff;border-radius:8px;padding:4px}
.badge-bsa .ic{color:var(--foot-gold)}
.foot-base{border-top:1px solid var(--foot-line);padding:18px 0 26px;color:var(--foot-mut);font-size:.88rem;
  display:flex;flex-wrap:wrap;gap:6px 20px;justify-content:space-between}
.foot-base p{margin:0}

@media (min-width:760px){
  .row{grid-template-columns:minmax(180px,1fr) 2fr auto;align-items:center;gap:24px;padding:26px 8px}
  .row .go{margin-top:0}
  .official dl > div{grid-template-columns:220px 1fr;gap:16px;align-items:baseline}
  .foot-grid{grid-template-columns:1.4fr 1fr 1fr}
}
@media (min-width:1000px){
  .home{grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);column-gap:64px;row-gap:56px;
    grid-template-areas:"intro card" "services card" "owners card" "reach card";padding-top:64px}
  .intro{grid-area:intro}.services{grid-area:services}.owners{grid-area:owners}.reach{grid-area:reach}
  .official{grid-area:card;position:sticky;top:24px}
  .official dl > div{grid-template-columns:1fr;gap:2px}
}
@media (max-width:420px){
  body{font-size:16px}
  .wrap{padding:0 16px}
  .brand b{font-size:1rem}
  .nav a{padding:0 10px}
  .official header,.official dl,.official .lic,.official h3{padding-inline:18px}
  .official .lic li{flex-direction:column;gap:2px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
@media print{.site-head nav,.skip{display:none}.site-foot{background:none;color:#000}}
"""


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------
def _fill(text, d, lang):
    """Insert register values (escaped) and in-copy links into a content.py sentence."""
    c = content.COMMON[lang]
    email = d["email"]
    vals = {
        "legal": _e(d["legal_name_en"] if lang == "en" else d["legal_name_ar"]),
        "cr": '<span class="ltr num">%s</span>' % _e(d["cr_number"]),
        "na": '<span class="ltr num">%s</span>' % _e(d["national_address_short"]),
        "email_link": ('<a class="ltr" href="mailto:%s">%s</a>' % (_e(email), _e(email))) if email else _e(c["contact"]),
        "privacy_link": '<a href="%s">%s</a>' % (path_for("privacy", lang), _e(c["privacy"])),
        "contact_link": '<a href="%s">%s</a>' % (path_for("contact", lang), _e(c["contact"])),
    }
    return text.format(**vals)


def _travel_line(d, lang):
    no = (d.get("travel_licence_no") or "").strip()
    if not no:
        return ""
    c = content.COMMON[lang]
    brand = d["brand_en"] if lang == "en" else d["brand_ar"]
    cat = d["travel_licence_category_en"] if lang == "en" else d["travel_licence_category_ar"]
    return ('<p class="licence-travel">%s · %s: <span class="ltr num">%s</span> · %s: %s</p>'
            % (_e(brand), _e(c["travel_licence"]), _e(no), _e(c["category"]), _e(cat)))


def _badge(d, lang):
    cert = (d.get("business_sa_cert_url") or "").strip()
    img = (d.get("business_sa_badge_img") or "").strip()
    if not cert.startswith("https://"):
        return ""
    c = content.COMMON[lang]
    if img.startswith("https://"):
        inner = ('<img src="%s" alt="%s" width="120" height="56" loading="lazy" referrerpolicy="no-referrer">'
                 % (_e(img), _e(c["badge_alt"])))
    else:
        inner = _icon("seal") + "<span>%s</span>" % _e(c["badge_text"])
    return ('<a class="badge-bsa" href="%s" target="_blank" rel="noopener">%s</a>' % (_e(cert), inner))


def _header(page, lang):
    c = content.COMMON[lang]
    other = c["switch_lang"]
    return (
        '<a class="skip" href="#main">%s</a>'
        '<header class="site-head"><div class="wrap">'
        '<a class="brand" href="%s"><img src="/site/logo.png" alt="%s" width="40" height="47">'
        '<b>%s</b></a>'
        '<nav class="nav" aria-label="%s">'
        '<a href="%s">%s</a>'
        '<a class="lang" href="%s" hreflang="%s" lang="%s">%s</a>'
        '</nav></div></header>'
    ) % (_e(c["skip"]), path_for("home", lang), _e(c["logo_alt"]),
         _e(SITE_IDENTITY["brand_en"] if lang == "en" else SITE_IDENTITY["brand_ar"]),
         _e(c["nav_label"]), path_for("contact", lang), _e(c["nav_contact"]),
         path_for(page, other), other, other, _e(c["switch"]))


def _footer(d, lang):
    c = content.COMMON[lang]
    en = lang == "en"
    contact = []
    if d["email"]:
        contact.append('<li>%s<a class="ltr" href="mailto:%s">%s</a></li>'
                       % (_icon("mail"), _e(d["email"]), _e(d["email"])))
    if d["phone"]:
        contact.append('<li>%s<a class="ltr num" href="https://wa.me/%s" rel="noopener">%s</a></li>'
                       % (_icon("chat"), _e(d["phone"]), _e(_phone_display(d["phone"]))))
    contact.append('<li>%s<span>%s</span></li>' % (_icon("pin"), _e(c["riyadh"])))
    social = []
    for key in ("tiktok", "instagram"):
        url = (d.get(key + "_url") or "").strip()
        if url.startswith("https://"):
            social.append('<a href="%s" rel="noopener me" aria-label="%s">%s</a>'
                          % (_e(url), _e(c[key]), _icon(key)))
    social_html = ('<div class="social">%s</div>' % "".join(social)) if social else ""
    legal_extra = _travel_line(d, lang) + _badge(d, lang)
    year = datetime.date.today().year
    return (
        '<footer class="site-foot"><div class="wrap">'
        '<div class="foot-grid">'
        '<div class="foot-brand"><img src="/site/logo.png" alt="" width="46" height="54">'
        '<b>%s</b><p>%s<br>%s <span class="ltr num">%s</span><br>%s <span class="ltr num">%s</span></p></div>'
        '<div><h2>%s</h2><ul>'
        '<li><a href="%s">%s</a></li><li><a href="%s">%s</a></li>'
        '<li><a href="%s">%s</a></li><li><a href="%s">%s</a></li></ul></div>'
        '<div class="foot-contact"><h2>%s</h2><ul>%s</ul>%s</div>'
        '</div>'
        '%s'
        '<div class="foot-base"><p>© %d %s. %s</p><p>%s</p></div>'
        '</div></footer>'
    ) % (_e(d["brand_en"] if en else d["brand_ar"]),
         _e(d["legal_name_en"] if en else d["legal_name_ar"]),
         _e(c["cr"]), _e(d["cr_number"]), _e(c["na"]), _e(d["national_address_short"]),
         _e(c["foot_pages"]),
         path_for("home", lang), _e(c["home"]), path_for("privacy", lang), _e(c["privacy"]),
         path_for("terms", lang), _e(c["terms"]), path_for("contact", lang), _e(c["contact"]),
         _e(c["foot_contact"]), "".join(contact), social_html,
         ('<div class="foot-legal">%s</div>' % legal_extra) if legal_extra else "",
         year, _e(d["legal_name_en"] if en else d["legal_name_ar"]), _e(c["rights"]),
         _e(c["notice"]))


def _jsonld(d, lang):
    org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": d["brand_en"] if lang == "en" else d["brand_ar"],
        "alternateName": d["brand_ar"] if lang == "en" else d["brand_en"],
        "legalName": d["legal_name_en"] if lang == "en" else d["legal_name_ar"],
        "url": d["site_url"] + "/",
        "logo": d["site_url"] + "/site/logo.png",
        "identifier": {"@type": "PropertyValue", "propertyID": "CR", "value": d["cr_number"]},
        "address": {"@type": "PostalAddress", "streetAddress": d["address_en"] if lang == "en" else d["address_ar"],
                    "addressLocality": "Riyadh", "postalCode": "12314", "addressCountry": "SA"},
    }
    if d["email"]:
        org["email"] = d["email"]
    return json.dumps(org, ensure_ascii=False).replace("</", "<\\/")


def _page(page, lang, title, desc, body, d):
    site = d["site_url"]
    ar_path, en_path = PATHS[page]
    canonical = site + path_for(page, lang)
    rtl = lang == "ar"
    fonts = ""
    if FONT_CSS_PATH:
        fonts = ('<link rel="preload" href="%s" as="font" type="font/woff2" crossorigin>'
                 '<link rel="stylesheet" href="%s">' % (PRELOAD_FONT_PATH, FONT_CSS_PATH))
    head = (
        '<!doctype html><html lang="%s" dir="%s"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>%s</title><meta name="description" content="%s">'
        '<link rel="canonical" href="%s">'
        '<link rel="alternate" hreflang="ar" href="%s">'
        '<link rel="alternate" hreflang="en" href="%s">'
        '<link rel="alternate" hreflang="x-default" href="%s">'
        '<meta property="og:type" content="website"><meta property="og:site_name" content="%s">'
        '<meta property="og:title" content="%s"><meta property="og:description" content="%s">'
        '<meta property="og:url" content="%s"><meta property="og:image" content="%s/site/share.png">'
        '<meta property="og:locale" content="%s"><meta name="twitter:card" content="summary_large_image">'
        '<meta name="theme-color" content="#F7F1E6">'
        '<link rel="icon" href="/pwa/icons/favicon-32.png" sizes="32x32" type="image/png">'
        '<link rel="apple-touch-icon" href="/pwa/icons/apple-touch-icon.png">'
        '%s<style>%s</style>'
        '<script type="application/ld+json">%s</script>'
        '</head><body>'
    ) % (lang, "rtl" if rtl else "ltr", _e(title), _e(desc), canonical,
         site + ar_path, site + en_path, site + ar_path,
         _e(d["brand_en"] if lang == "en" else d["brand_ar"]), _e(title), _e(desc),
         canonical, site, "en_US" if lang == "en" else "ar_SA",
         fonts, _CSS, _jsonld(d, lang))
    return head + _header(page, lang) + '<main id="main">' + body + "</main>" + _footer(d, lang) + "</body></html>"


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def _official_card(d, lang):
    h = content.HOME[lang]
    en = lang == "en"
    rows = [
        (h["f_brand"], _e(d["brand_en"] if en else d["brand_ar"])),
        (h["f_legal"], _e(d["legal_name_en"] if en else d["legal_name_ar"])),
        (h["f_cr"], '<span class="ltr num big">%s</span>' % _e(d["cr_number"])),
        (h["f_na"], '<span class="ltr num big">%s</span>' % _e(d["national_address_short"])),
        (h["f_addr"], '%s<span class="sub">%s</span>' % (
            _e(d["address_en"] if en else d["address_ar"]),
            _e(d["address_unit_en"] if en else d["address_unit_ar"]))),
    ]
    if d["email"]:
        rows.append((h["f_email"], '<a class="ltr" href="mailto:%s">%s</a>' % (_e(d["email"]), _e(d["email"]))))
    if d["phone"]:
        rows.append((h["f_phone"], '<a class="ltr num" href="https://wa.me/%s" rel="noopener">%s</a>'
                     % (_e(d["phone"]), _e(_phone_display(d["phone"])))))
    dl = "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (_e(k), v) for k, v in rows)
    lic = [
        (h["lic_fal_mkt"], h["lic_rega"], d["fal_marketing_no"]),
        (h["lic_fal_mgmt"], h["lic_rega"], d["fal_management_no"]),
    ]
    if (d.get("travel_licence_no") or "").strip():
        cat = d["travel_licence_category_en"] if en else d["travel_licence_category_ar"]
        lic.append((cat, h["lic_mot"], d["travel_licence_no"].strip()))
    lis = "".join('<li><strong>%s<span>%s</span></strong><span class="ltr num">%s</span></li>'
                  % (_e(n), _e(issuer), _e(no)) for n, issuer, no in lic)
    return (
        '<section class="official" id="company" aria-labelledby="company-h">'
        '<header><div class="seal">%s<h2 id="company-h">%s</h2></div><p>%s</p></header>'
        '<dl>%s</dl><h3>%s</h3><ul class="lic">%s</ul></section>'
    ) % (_icon("seal"), _e(h["id_h"]), _e(h["id_sub"]), dl, _e(h["lic_h"]), lis)


def _notice(lang):
    return '<p class="notice">%s<span>%s</span></p>' % (_icon("info"), _e(content.COMMON[lang]["notice"]))


def render_home(lang, d=None):
    d = d or _ident()
    h = content.HOME[lang]
    rows = "".join(
        '<li><a class="row" href="%s"><h3>%s</h3><p>%s</p><span class="go">%s%s</span></a></li>'
        % (href, _e(t), _e(p), _e(go), _icon("arrow", "ic ic-flip"))
        for href, t, p, go in h["services"])
    body = (
        '<div class="wrap home">'
        '<section class="intro"><h1>%s</h1><p>%s</p></section>'
        '%s'
        '<section class="services" aria-labelledby="services-h"><h2 id="services-h">%s</h2><ul>%s</ul></section>'
        '<section class="owners" aria-labelledby="owners-h"><h2 id="owners-h">%s</h2><p>%s</p></section>'
        '<section class="reach" aria-labelledby="reach-h"><h2 id="reach-h">%s</h2><p>%s</p>'
        '<p><a class="btn" href="%s">%s%s</a></p>%s</section>'
        '</div>'
    ) % (_e(h["h1"]), _fill(_e(h["lede"]), d, lang),
         _official_card(d, lang),
         _e(h["services_h"]), rows,
         _e(h["owners_h"]), _fill(_e(h["owners"]), d, lang),
         _e(h["contact_h"]), _e(h["contact_p"]), path_for("contact", lang), _e(h["contact_cta"]),
         _icon("arrow", "ic ic-flip"), _notice(lang))
    return _page("home", lang, h["title"], h["desc"], body, d)


def _blocks(blocks, d, lang):
    out = []
    for b in blocks:
        if isinstance(b, tuple):
            tag, items = b
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % _fill(_e(i), d, lang) for i in items), tag))
        else:
            out.append("<p>%s</p>" % _fill(_e(b), d, lang))
    return "".join(out)


def _render_doc(page, src, lang, d=None):
    d = d or _ident()
    p = src[lang]
    c = content.COMMON[lang]
    secs = "".join("<section><h2>%s</h2>%s</section>" % (_e(h2), _blocks(blocks, d, lang))
                   for h2, blocks in p["sections"])
    body = ('<div class="wrap"><article class="doc"><h1>%s</h1><p class="stamp">%s: %s</p>'
            '<p class="lead">%s</p>%s%s</article></div>') % (
        _e(p["h1"]), _e(c["updated"]), _e(content.UPDATED[lang]),
        _fill(_e(p["intro"]), d, lang), secs, _notice(lang))
    return _page(page, lang, p["title"], p["desc"], body, d)


def render_privacy(lang, d=None):
    return _render_doc("privacy", content.PRIVACY, lang, d)


def render_terms(lang, d=None):
    return _render_doc("terms", content.TERMS, lang, d)


def render_contact(lang, d=None):
    d = d or _ident()
    p = content.CONTACT[lang]
    c = content.COMMON[lang]
    h = content.HOME[lang]
    en = lang == "en"
    ch = []
    if d["email"]:
        subj = _pct(p["mail_subject"])
        ch.append('<li>%s<div><b>%s</b><a class="ltr" href="mailto:%s?subject=%s">%s</a></div></li>'
                  % (_icon("mail"), _e(c["email"]), _e(d["email"]), subj, _e(d["email"])))
    if d["phone"]:
        ch.append('<li>%s<div><b>%s</b><a class="ltr num" href="https://wa.me/%s" rel="noopener">%s</a></div></li>'
                  % (_icon("chat"), _e(c["whatsapp"]), _e(d["phone"]), _e(_phone_display(d["phone"]))))
    ch.append('<li>%s<div><b>%s</b><span>%s<br>%s<br>%s <span class="ltr num">%s</span></span></div></li>'
              % (_icon("pin"), _e(p["addr_h"]), _e(d["address_en"] if en else d["address_ar"]),
                 _e(d["address_unit_en"] if en else d["address_unit_ar"]),
                 _e(h["f_na"]), _e(d["national_address_short"])))
    fields = "".join("<li>%s</li>" % _e(x) for x in p["complaints_fields"])
    steps = "".join("<li>%s</li>" % _e(x) for x in p["steps"])
    body = (
        '<div class="wrap"><article class="doc"><h1>%s</h1><p class="lead">%s</p>'
        '<section aria-labelledby="ch-h"><h2 id="ch-h">%s</h2><ul class="channels">%s</ul></section>'
        '<section id="complaints" aria-labelledby="cp-h"><h2 id="cp-h">%s</h2>'
        '<p class="promise">%s<span>%s</span></p>'
        '<p>%s</p><ul>%s</ul>'
        '<h3>%s</h3><ol>%s</ol><p>%s</p></section>'
        '%s</article></div>'
    ) % (_e(p["h1"]), _e(p["intro"]), _e(p["channels_h"]), "".join(ch),
         _e(p["complaints_h"]), _icon("clock"), _e(p["complaints_promise"]),
         _fill(_e(p["complaints_how"]), d, lang), fields,
         _e(p["steps_h"]), steps, _e(p["escalate"]), _notice(lang))
    return _page("contact", lang, p["title"], p["desc"], body, d)


RENDERERS = {"home": render_home, "privacy": render_privacy,
             "terms": render_terms, "contact": render_contact}


def render(page, lang):
    return RENDERERS[page](lang)
