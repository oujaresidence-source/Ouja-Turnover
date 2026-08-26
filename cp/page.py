# -*- coding: utf-8 -*-
"""
cp.page — renders /cp/ar from the approved document plus live figures.

The template is a real file (cp/templates/ar.html), not a Python string, and
that is deliberate. Every serious outage this codebase has had on a rendered
page came from the same place: HTML living inside a normal triple-quoted string,
where Python eats a backslash before the browser ever sees it — a single stray
escape in a `//` comment has twice taken a whole page down to a blank login. A
file removes that failure mode completely, and the substitution model is exactly
the one the other packages use: plain .replace() of __TOKENS__, never .format()
and never an f-string, so the CSS and JS braces stay literal.

The copy is byte-for-byte the approved Arabic edition. It was ported by
cp/tools/tokenise_source.py, which refuses to run if any substitution matches a
different number of times than recorded — so the template cannot silently drift
from the document, and nobody has to trust that the Arabic was retyped correctly.

Figures come from cp.stats as cells carrying value + source + as_of, and the
rendered page is run through cp.guard before it is returned. A withheld figure
therefore cannot be served even if every test were skipped.
"""
import html
import json
import os

from . import guard, stats

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES = os.path.join(_HERE, "templates")
_DATA = os.path.join(_HERE, "data")

# The placeholder number in the seeds file. If it ever reaches a href it would
# render a live-looking WhatsApp button that goes to nobody (seeds §13).
_PLACEHOLDER_WA = "966500000000"

_AR_MONTHS = {1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
              7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"}


def _read(path, default=""):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return default


def _read_json(name, default):
    try:
        with open(os.path.join(_DATA, name), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return data


TEMPLATE_AR = _read(os.path.join(_TEMPLATES, "ar.html"))
COPY_AR = _read_json("cp_copy_ar.json", {})
ROUTES_AR = _read_json("cp_routes_ar.json", [])


def _e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def _ar_month_year(iso):
    """2026-08-26 -> أغسطس 2026. Seeds §10: Western numerals, Arabic month name."""
    try:
        year, month = int(str(iso)[:4]), int(str(iso)[5:7])
        return "%s %d" % (_AR_MONTHS.get(month, ""), year)
    except (TypeError, ValueError):
        return str(iso)


def _pct_width(value, top, scale):
    """Bar width, as the document draws them: the row's largest bar sits at
    `scale`, everything else is proportional to it. Clamped so a future figure
    cannot push a fill outside its track."""
    try:
        if not top:
            return "0"
        w = float(value) / float(top) * float(scale)
    except (TypeError, ValueError, ZeroDivisionError):
        return "0"
    return ("%.1f" % max(0.0, min(100.0, w))).rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# blocks rebuilt from data
# --------------------------------------------------------------------------- #
def build_routes(routes):
    """Five audience doors (seeds §12). Three are the document's, two are ours."""
    out = []
    for r in routes:
        out.append(
            '<div class="route"><h3>%s</h3>\n        <p>%s</p>\n        '
            '<a class="go" href="%s">%s</a></div>'
            % (r.get("h3", ""), r.get("p", ""), _e(r.get("href", "#meet")), r.get("cta", "")))
    return '<div class="routes">\n      ' + "\n      ".join(out) + "\n    </div>"


def build_occupancy_table(cells, market):
    """Occupancy by residence type, with the multiple computed rather than typed.

    Seeds §2 permits occupancy per type and nothing else per type — no unit
    counts, no ADR, no revenue — so this table has exactly three columns.
    """
    labels = [("1br", "غرفة نوم واحدة"), ("2br", "غرفتا نوم"), ("3br", "ثلاث غرف نوم"),
              ("4br_plus", "أربع غرف فأكثر"), ("portfolio", "إجمالي المحفظة")]
    by_type = cells["occupancy_by_type"]["value"] or {}
    mkt = float(market.get("occupancy_pct") or 0) or None
    rows = []
    for key, label in labels:
        value = by_type.get(key)
        if value is None:
            continue
        multiple = ("%.1f×" % (float(value) / mkt)) if mkt else "—"
        rows.append(
            '<tr><td class="k">%s</td><td class="hi">%s%%</td><td class="vs">%s</td></tr>'
            % (label, stats.fmt("occupancy_pct", value), multiple))
    return "<tbody>\n            " + "\n            ".join(rows) + "\n          </tbody>"


def build_voices(reviews, copy):
    """Six guest reviews, verbatim, or six visible blanks.

    Seeds §15: verbatim only, never paraphrased or tidied; an Arabic review keeps
    its original text; first name plus last initial; month and year only. Five
    real reviews beat six with one invented, so an unfilled slot renders as the
    document's own coloured blank rather than being quietly dropped or filled.
    """
    briefs = [
        "مراجعة منشورة حقيقية — اختر واحدة تذكر اسم أحد الموظفين.",
        "مراجعة حقيقية عن تسجيل الدخول أو رمز الباب.",
        "مراجعة حقيقية عن مشكلة عالجناها بسرعة.",
        "مراجعة حقيقية من ضيف عائد.",
        "مراجعة حقيقية تذكر السائق أو الحلّاق أو الخدمات الخاصة.",
        "مراجعة ناقدة — وأبقِها كما هي.",
    ]
    out = []
    for i, brief in enumerate(briefs):
        r = reviews[i] if i < len(reviews) else None
        if not r or not (r.get("text_original") or "").strip():
            out.append(
                '<div class="voice"><blockquote>&ldquo;<span class="fillin">[ %s ]</span>'
                '&rdquo;</blockquote><p class="src"><b class="fillin">[ اسم الضيف ]</b> '
                '&middot; <span class="fillin">[ الوحدة ]</span> &middot; '
                '<span class="fillin">[ الشهر والسنة ]</span></p></div>' % brief)
            continue

        body = '&ldquo;%s&rdquo;' % _e(r["text_original"])
        # An English review on the Arabic edition keeps its own words and gains a
        # clearly-marked translation beneath. Never translated in place.
        if r.get("translation_ar"):
            body += ('<span class="tr"><b>%s:</b> %s</span>'
                     % (_e(copy.get("review_translation_label", "الترجمة")),
                        _e(r["translation_ar"])))
        response = ""
        if r.get("our_response"):
            response = ('<p class="reply"><b>%s:</b> %s</p>'
                        % (_e(copy.get("our_response_label", "ردّنا")), _e(r["our_response"])))
        out.append(
            '<div class="voice"><blockquote%s>%s</blockquote>%s'
            '<p class="src"><b>%s</b> &middot; %s &middot; %s</p></div>'
            % (' lang="en" dir="ltr"' if r.get("language") == "en" else "",
               body, response, _e(r.get("guest_name", "")),
               "<bdi>%s</bdi>" % _e(r.get("listing_name", "")), _e(r.get("date", ""))))
    return '<div class="voices">\n      ' + "\n      ".join(out) + "\n    </div>"


def build_units(units, copy):
    """Six residences. A missing listing or a failed image renders the document's
    dashed placeholder — never a broken image (superprompt §6)."""
    out = []
    for i in range(6):
        u = units[i] if i < len(units) else None
        if not u or not (u.get("name_ar") or "").strip():
            out.append(
                '<div class="unit"><div class="ph"><span>%s</span></div>'
                '<h3><span class="fillin">[ اسم الوحدة ]</span></h3>'
                '<p class="meta"><span class="fillin">[ عدد الغرف ]</span> &middot; '
                '<span class="fillin">[ المجمّع ]</span></p>'
                '<p><span class="fillin">[ سطر واحد: ما الذي يميّز هذه الوحدة. ]</span></p></div>'
                % _e(copy.get("unit_photo_placeholder", "صورة")))
            continue
        alt = "%s — %s" % (u.get("name_ar", ""), u.get("compound_ar", ""))
        if u.get("photo_srcset"):
            media = ('<img src="%s" srcset="%s" sizes="(max-width:700px) 100vw, 33vw" '
                     'alt="%s" loading="lazy" decoding="async" width="1024" height="683">'
                     % (_e(u.get("photo", "")), _e(u["photo_srcset"]), _e(alt)))
        elif u.get("photo"):
            media = ('<img src="%s" alt="%s" loading="lazy" decoding="async" '
                     'width="1024" height="683">' % (_e(u["photo"]), _e(alt)))
        else:
            media = '<div class="ph"><span>%s</span></div>' % _e(
                copy.get("unit_photo_placeholder", "صورة"))
        rooms = u.get("bedrooms_label_ar") or ""
        out.append(
            '<div class="unit">%s<h3>%s</h3><p class="meta">%s &middot; %s</p><p>%s</p></div>'
            % (media, _e(u["name_ar"]), _e(rooms), _e(u.get("compound_ar", "")),
               _e(u.get("line_ar", ""))))
    return '<div class="units">\n      ' + "\n      ".join(out) + "\n    </div>"


def build_ask(ask):
    """The three «what we are looking for» fields (seeds §14 blank 6)."""
    fields = [("ما الذي نسعى لجمعه", "amount",
               'مبلغ أو نطاق — أو "شريك استراتيجي بدل رأس المال"'),
              ("فيمَ يُصرف", "use", "مثال: رأس مال تأثيث للوصول إلى 200 وحدة"),
              ("ماذا يحصل عليه الشريك", "offer",
               "حصة ملكية، أو مشاركة إيراد، أو استثمار مشترك لكل وحدة")]
    out = []
    for label, key, blank in fields:
        value = (ask or {}).get(key)
        if value:
            out.append('<div><span class="q">%s</span><p class="a">%s</p></div>'
                       % (label, _e(value)))
        else:
            out.append('<div><span class="q">%s</span><p class="a fillin">[ %s ]</p></div>'
                       % (label, blank))
    return '<div class="ask">\n      ' + "\n      ".join(out) + "\n    </div>"


def build_head_extra(base, lang="ar"):
    """Canonical, alternates and a share card. This link is forwarded on WhatsApp
    constantly, so the preview card is the first thing most readers ever see."""
    b = (base or "").rstrip("/")
    bits = [
        "<style>"
        ".voice .tr{display:block;margin-top:10px;padding-top:10px;"
        "border-top:1px dashed var(--rule);color:var(--ink-soft);font-size:.92em;"
        "direction:rtl;text-align:right}"
        ".voice .reply{margin-top:10px;padding:10px 14px;background:var(--paper-deep);"
        "border-inline-start:2px solid var(--ochre-text);color:var(--ink-soft);"
        "font-size:.92em}"
        ".voice .src bdi{unicode-bidi:isolate}"
        # the approved document only styles the dashed .ph placeholder — a real
        # photo is renderer-emitted markup, so its constraint ships from here
        # (an unconstrained 1024px <img> measured 495px of horizontal overflow)
        ".unit img{display:block;width:100%;height:auto;aspect-ratio:4/3;"
        "object-fit:cover;background:var(--paper-deep)}"
        "</style>",
        '<link rel="canonical" href="%s/cp/%s">' % (_e(b), lang),
        '<link rel="alternate" hreflang="x-default" href="%s/cp/ar">' % _e(b),
        '<meta property="og:url" content="%s/cp/%s">' % (_e(b), lang),
        '<meta property="og:site_name" content="Ouja Residence">',
        '<meta name="twitter:card" content="summary_large_image">',
        '<meta name="robots" content="index,follow">',
    ]
    if b:
        bits.append('<meta property="og:image" content="%s/cp/share.png">' % _e(b))
        bits.append('<meta name="twitter:image" content="%s/cp/share.png">' % _e(b))
        bits.append('<link rel="icon" href="%s/cp/icon.png" type="image/png">' % _e(b))
    return "\n".join(bits)


def build_contacts(links, copy):
    """Defect §8.1: on /business the contact is a Gmail mailto and the WhatsApp
    button also opens email. Both become configuration here, and an unset
    WhatsApp number renders a DISABLED button — never a dead wa.me link."""
    email = (links or {}).get("email") or ""
    wa = "".join(ch for ch in str((links or {}).get("wa") or "") if ch.isdigit())
    if wa == _PLACEHOLDER_WA:
        wa = ""

    subject = "%D8%B7%D9%84%D8%A8%20%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%20-%20%D8%B9%D9%88%D8%AC%D8%A7"
    if email:
        meet_href = 'href="mailto:%s?subject=%s"' % (_e(email), subject)
        plain_href = 'href="mailto:%s"' % _e(email)
    else:
        meet_href = plain_href = 'href="#meet"'

    if wa:
        text = "%D8%A3%D8%B1%D8%BA%D8%A8%20%D8%A8%D8%AD%D8%AC%D8%B2%20%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%20%D9%85%D8%B9%20%D8%B9%D9%88%D8%AC%D8%A7"
        dark = ('<a class="btn" style="border-color:var(--rule-dark);background:transparent;'
                'color:var(--on-dark)" href="https://wa.me/%s?text=%s">واتساب</a>' % (wa, text))
        footer = '<p><a href="https://wa.me/%s">واتساب</a></p>' % wa
    else:
        unavailable = _e(copy.get("wa_unavailable", "رقم الواتساب غير مُعدّ بعد"))
        dark = ('<span class="btn is-disabled" aria-disabled="true" title="%s" '
                'style="border-color:var(--rule-dark);background:transparent;'
                'color:var(--on-dark-soft);cursor:not-allowed">واتساب</span>' % unavailable)
        footer = '<p><span class="off">واتساب &middot; %s</span></p>' % unavailable
    return meet_href, plain_href, dark, footer


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
# Navigation the page offers only when the thing behind it actually exists.
# The brief's rule is that no dead link is reachable; advertising an English
# edition or a PDF that 404s is the same defect as a dead wa.me link.
_OPTIONAL_LINKS = {
    "english": ('<a class="lang" href="/cp/en" lang="en">English</a>',
                '<p><a href="/cp/en" lang="en">English version</a></p>',
                # the alternate advertises the edition to search engines too,
                # so it goes with the visible links rather than pointing at a
                # URL that only redirects back here
                '<link rel="alternate" hreflang="en" href="__BASE__/cp/en">'),
    "pdf": ('<a class="lang" href="/cp.pdf">PDF</a>',
            '<p><a href="/cp.pdf">حمّله بصيغة PDF</a></p>'),
}


def drop_unavailable_links(markup, english=False, pdf=False):
    """Remove the nav entries whose destination is not being served."""
    out = markup
    for key, present in (("english", english), ("pdf", pdf)):
        if present:
            continue
        for anchor in _OPTIONAL_LINKS[key]:
            out = out.replace(anchor, "")
    return out


def render_ar(snapshot=None, base="", links=None, reviews=None, units=None,
              ask=None, template=None, check=True, english=False, pdf=False):
    """The Arabic edition. `check` runs the disclosure guard on the result."""
    out = template if template is not None else TEMPLATE_AR
    cells = stats.load(snapshot=snapshot)
    market = stats.MARKET
    copy = COPY_AR

    def v(field):
        return cells[field]["value"]

    def f(field):
        return stats.fmt(field, v(field))

    stamp = stats.sync_stamp(snapshot=snapshot)
    as_of_ar = _ar_month_year(stamp["as_of"])
    sync_key = "sync_live" if stamp["live"] else "sync_static"
    sync_line = copy.get(sync_key, "").replace("__AS_OF_AR__", as_of_ar)

    meet_href, plain_href, wa_dark, wa_footer = build_contacts(links, copy)
    cat = v("category_scores") or {}
    adr_top = max(v("adr_sar"), v("adr_90d_sar"), market.get("adr_sar") or 0)
    rev_top = max(v("revpar_sar"), v("revpar_active_sar"), market.get("revpar_sar") or 0)
    occ_top = max(v("occupancy_pct"), market.get("occupancy_pct") or 0)

    # Blocks go in FIRST, so the figure placeholders they contain resolve below.
    blocks = {
        "__ROUTES__": build_routes(ROUTES_AR),
        "__ROUTES_HEADING__": copy.get("routes_heading", ""),
        "__OCC_TABLE__": build_occupancy_table(cells, market),
        "__VOICES__": build_voices(reviews or [], copy),
        "__VOICES_NOTE__": '<p class="note" style="margin-top:22px">%s</p>' % (
            copy.get("voices_note_live" if (reviews or []) else "voices_note_pending", "")),
        "__UNITS__": build_units(units or [], copy),
        "__ASK__": build_ask(ask),
        "__HEAD_EXTRA__": build_head_extra(base),
        "__SYNC_STAMP__": '<p class="asof">%s</p>' % sync_line,
    }
    for token, value in blocks.items():
        out = out.replace(token, value)

    figures = {
        "__RESERVATIONS__": f("reservations_total"), "__NIGHTS__": f("nights_total"),
        "__REVIEWS__": f("reviews_total"), "__RATING__": f("rating_avg"),
        "__OCC__": f("occupancy_pct"), "__PERFECT__": f("perfect_ten_pct"),
        "__ADR__": f("adr_sar"), "__ADR90__": f("adr_90d_sar"),
        "__REVPAR__": f("revpar_sar"), "__REVPAR_ACTIVE__": f("revpar_active_sar"),
        "__RESIDENCES__": f("residences_total"), "__CAPACITY__": f("designed_capacity_residences"),
        "__REPEAT_GUESTS__": f("repeat_guests"), "__REPEAT_PCT__": f("repeat_booking_pct"),
        "__TOP_GUEST__": f("top_guest_stays"), "__SAUDI__": f("saudi_guest_pct"),
        "__SAMEDAY__": f("same_day_booking_pct"), "__THUFRI__": f("thu_fri_arrival_pct"),
        "__LONGSTAY_BOOK__": f("long_stay_booking_pct"),
        "__LONGSTAY_REV__": f("long_stay_revenue_pct"),
        "__ADR_GROWTH__": f("adr_growth_pct"), "__CHURN_OCC__": f("released_occupancy_pct"),
        "__MESSAGES__": f("messages_total"), "__MSG_START__": f("messages_monthly_start"),
        "__MSG_NOW__": f("messages_monthly_now"), "__MAINT__": f("maintenance_closed_in_sla"),
        "__RESPONSE__": f("median_response_minutes"),
        "__PER_PERSON__": f("residences_per_person_per_day"),
        "__LOC__": f("platform_lines_of_code"),
        "__DAYS_FURN__": f("days_to_live_furnished"),
        "__DAYS_UNFURN__": f("days_to_live_unfurnished"),
        "__CAT_COMM__": stats.fmt("rating_avg", cat.get("communication")),
        "__CAT_CHECKIN__": stats.fmt("rating_avg", cat.get("check_in")),
        "__CAT_ACCURACY__": stats.fmt("rating_avg", cat.get("accuracy")),
        "__CAT_LOCATION__": stats.fmt("rating_avg", cat.get("location")),
        "__CAT_CLEAN__": stats.fmt("rating_avg", cat.get("cleanliness")),
        "__CAT_VALUE__": stats.fmt("rating_avg", cat.get("value")),

        "__MKT_OCC__": stats.fmt("repeat_booking_pct", market.get("occupancy_pct")),
        "__MKT_ADR__": stats.fmt("adr_sar", market.get("adr_sar")),
        "__MKT_REVPAR__": stats.fmt("revpar_sar", market.get("revpar_sar")),
        "__MKT_LISTINGS__": stats.fmt("reservations_total", market.get("active_listings")),
        "__MKT_LISTINGS_ROUND__": stats.fmt(
            "reservations_total", int(float(market.get("active_listings") or 0) / 1000) * 1000),
        "__FX__": str(market.get("fx_sar_per_usd", "")),
        "__MKT_DATE_AR__": _ar_month_year_label(market.get("source_date", "")),
        "__X_OCC__": (market.get("multiples") or {}).get("occupancy", "").rstrip("x"),
        "__X_ADR__": (market.get("multiples") or {}).get("adr", "").rstrip("x"),
        "__X_REVPAR__": (market.get("multiples") or {}).get("revpar", "").rstrip("x"),

        "__W_OCC__": _pct_width(v("occupancy_pct"), occ_top, 96),
        "__W_MKT_OCC__": _pct_width(market.get("occupancy_pct"), occ_top, 96),
        "__W_ADR__": _pct_width(v("adr_sar"), adr_top, 93.5),
        "__W_MKT_ADR__": _pct_width(market.get("adr_sar"), adr_top, 93.5),
        "__W_REVPAR__": _pct_width(v("revpar_sar"), rev_top, 93.5),
        "__W_MKT_REVPAR__": _pct_width(market.get("revpar_sar"), rev_top, 93.5),
        "__W_FULL__": "93.5",
        "__W_CAPACITY__": _pct_width(v("residences_total"),
                                     v("designed_capacity_residences"), 100),
        "__WC_COMM__": _pct_width(cat.get("communication"), 10, 100),
        "__WC_CHECKIN__": _pct_width(cat.get("check_in"), 10, 100),
        "__WC_ACCURACY__": _pct_width(cat.get("accuracy"), 10, 100),
        "__WC_LOCATION__": _pct_width(cat.get("location"), 10, 100),
        "__WC_CLEAN__": _pct_width(cat.get("cleanliness"), 10, 100),
        "__WC_VALUE__": _pct_width(cat.get("value"), 10, 100),

        "__AS_OF_AR__": as_of_ar,
        "__BASE__": (base or "").rstrip("/"),
        "__TIKTOK__": "https://tiktok.com/@oujares",
        "__EMAIL_MEET_HREF__": meet_href, "__EMAIL_HREF__": plain_href,
        "__WA_BUTTON_DARK__": wa_dark, "__WA_FOOTER__": wa_footer,
    }
    out = drop_unavailable_links(out, english=english, pdf=pdf)

    for token, value in figures.items():
        out = out.replace(token, str(value))

    if check:
        guard.assert_clean(out, label="/cp/ar")
    return out


_EN_MONTHS = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
              "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
              "December": 12}


def _ar_month_year_label(text):
    """«July 2026» (as the market config states it) -> «يوليو 2026»."""
    parts = str(text or "").split()
    if len(parts) == 2 and parts[0] in _EN_MONTHS:
        return "%s %s" % (_AR_MONTHS[_EN_MONTHS[parts[0]]], parts[1])
    return str(text or "")


def remaining_placeholders(markup):
    """Any __TOKEN__ left unfilled. A rendered page must have none."""
    import re
    return sorted(set(re.findall(r"__[A-Z0-9_]+__", markup or "")))
