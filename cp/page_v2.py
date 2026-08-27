# -*- coding: utf-8 -*-
"""
cp.page_v2 — renders the approved v6 design from templates/ar_v2.html.

The template set is produced by cp/tools/tokenise_v2.py and is never edited by
hand. Three inputs meet here:

  * figures — cp.stats cells (value + source + as_of), exactly v1's layer;
  * the admin overlay — contacts, copy overrides, benchmarks, showcase units,
    chosen reviews, uploaded shots (cp.admin_store);
  * the block DEFAULTS — the mock's own markup, captured verbatim at port
    time. A block renders pixel-identical to the approved design until the
    dashboard actually configures it. Nothing here authors default copy.

Every render — the page and each /cp/ar/more/<key> — passes through cp.guard
before it is returned, same contract as v1.
"""
import html
import json
import os
import re

from . import guard, stats

_HERE = os.path.dirname(os.path.abspath(__file__))
_TPL = os.path.join(_HERE, "templates")
_DATA = os.path.join(_HERE, "data")

DRAWER_KEYS = ("compare", "system", "stay", "guests", "units", "owners", "gov")

# The mock's success line, verbatim (its literal became the __RESV_OK__ slot so
# the JS can compose the mode onto it; the default text itself is unchanged).
DEFAULT_RESV_OK = ("نؤكد الموعد على جوالك خلال يوم عمل. "
                   "وإن كان عاجلاً، فالواتساب يصل إلى الفريق مباشرة.")

# the mock's placeholder roofline — the fallback when no logo is installed
FALLBACK_MARK = (
    '<svg viewBox="0 0 34 22" aria-hidden="true">'
    '<path d="M1 21 L17 3 L33 21" fill="none" stroke="currentColor" '
    'stroke-width="2.4" stroke-linejoin="round"/>'
    '<path d="M8 21 L17 11 L26 21" fill="none" stroke="currentColor" '
    'stroke-width="2.4" stroke-linejoin="round"/></svg>')


def logo_mark(has_logo, height=21):
    """The brand mark. A real logo is a plain <img> with explicit height so it
    cannot shift the header while it loads (CLS is 0 and stays 0)."""
    if not has_logo:
        return FALLBACK_MARK
    return ('<img src="/cp/logo.png" alt="" aria-hidden="true" '
            'style="height:%dpx;width:auto;flex:none" '
            'height="%d" decoding="async">' % (height, height))


def _read(path, default=""):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return default


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return data


TEMPLATE = _read(os.path.join(_TPL, "ar_v2.html"))
SCRIPT = _read(os.path.join(_TPL, "v2.js"))
COPY_DEFAULTS = _read_json(os.path.join(_DATA, "cp_copy_v2_ar.json"), {})
BENCH_DEFAULTS = _read_json(os.path.join(_DATA, "cp_benchmarks.json"), {})
DEFAULT_BLOCKS = {name: _read(os.path.join(_TPL, "defaults", name + ".html"))
                  for name in ("doors", "trust", "page_quotes", "units_grid", "shots",
                               "bench", "occ_types", "drawer_reviews",
                               "drawer_units")}
MORE = {key: _read(os.path.join(_TPL, "more", key + ".html"))
        for key in DRAWER_KEYS}


def _e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def _fmt(field, value):
    return stats.fmt(field, value)


def _bench_value(overlay_bench, key):
    entry = (overlay_bench or {}).get(key) or BENCH_DEFAULTS.get(key) or {}
    return entry.get("value", "")


def _pct_width(value, top, scale=100.0):
    try:
        w = float(value) / float(top) * float(scale)
    except (TypeError, ValueError, ZeroDivisionError):
        return "0"
    return ("%.1f" % max(0.0, min(100.0, w))).rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- #
# blocks rebuilt when the overlay configures them
# --------------------------------------------------------------------------- #
def build_units_grid(units, photos):
    tiles = []
    for u in units:
        if u.get("hidden") or u.get("inactive"):
            continue
        shot = photos.get(str(u.get("listing_id"))) or {}
        if shot.get("photo"):
            ph = ('<img src="%s" srcset="%s" sizes="(max-width:700px) 100vw, 33vw" '
                  'alt="%s" loading="lazy" decoding="async" width="1200" height="900" '
                  'onerror="this.closest(&quot;.ph&quot;)&amp;&amp;'
                  'this.remove()">' % (_e(shot["photo"]), _e(shot.get("srcset", "")),
                                       _e(u.get("name_ar", ""))))
            ph = '<div class="ph">%s</div>' % ph
        else:
            ph = '<div class="ph"><span class="lab">صورة الوحدة</span></div>'
        tiles.append(
            '<a class="unit" href="/cp/ar/more/units" data-drawer="units">%s'
            '<div class="b"><h3>%s</h3><div class="sp">%s · %s</div></div></a>'
            % (ph, _e(u.get("name_ar", "")), _e(u.get("bedrooms_label_ar", "")),
               _e(u.get("line_ar", ""))))
    return ('<div class="units">\n      ' + "\n      ".join(tiles) + "\n    </div>") \
        if tiles else DEFAULT_BLOCKS["units_grid"]


def build_drawer_units(units):
    rows = []
    for u in units:
        if u.get("hidden") or u.get("inactive"):
            continue
        rows.append('<li><div><b>%s</b><span>%s. %s</span></div></li>'
                    % (_e(u.get("name_ar", "")), _e(u.get("bedrooms_label_ar", "")),
                       _e(u.get("line_ar", ""))))
    return ("<ol>\n        " + "\n        ".join(rows) + "\n      </ol>") \
        if rows else DEFAULT_BLOCKS["drawer_units"]


CHECK_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
              'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
              '<path d="M20 6L9 17l-5-5"/></svg>')


def build_trust(copy, social=None):
    """The hero's trust chips. Four come from editable copy keys; a fifth is
    added only when the reach figures carry a value, a date and a source — the
    same gate every other hand-entered figure passes. Reach is distribution
    evidence for a company whose guests arrive from TikTok, so it sits beside
    the operating claims rather than in a marketing box of its own."""
    items = [copy.get("trust_%d" % i) for i in (1, 2, 3, 4)]
    items = [t for t in items if t]
    if social:
        items.append(social)
    return ('<div class="trust">\n      '
            + "\n      ".join('<span>%s%s</span>' % (CHECK_ICON, t) for t in items)
            + "\n    </div>")


def build_page_quotes(reviews):
    out = []
    for r in reviews[:3]:
        crit = ' crit' if r.get("critical") else ''
        tail = " · " + _e(r["tag"]) if r.get("tag") else ""
        out.append('<div class="q%s"><q>%s</q><div class="who"><span class="av">%s</span>'
                   '<div><b>%s</b> · %s · %s%s</div></div></div>'
                   % (crit, _e(r.get("text", "")),
                      _e((r.get("name") or "؟")[:1]), _e(r.get("name", "")),
                      _e(r.get("label", "")), _e(r.get("date", "")), tail))
    return '<div class="quotes">\n      ' + "\n      ".join(out) + "\n    </div>"


def build_drawer_reviews(reviews):
    out = ["<h4>%s مراجعات، كما كُتبت</h4>" % ("ست" if len(reviews) == 6
                                               else str(len(reviews)))]
    for r in reviews:
        attrs = ' lang="en" dir="ltr" style="font-family:Georgia,serif"' \
            if r.get("lang") == "en" else ""
        tail = " · نُشرت كما هي" if r.get("critical") else ""
        out.append('<q%s>%s</q><div class="who">%s · %s · %s%s</div>'
                   % (attrs, _e(r.get("text", "")), _e(r.get("name", "")),
                      _e(r.get("label", "")), _e(r.get("date", "")), tail))
    return "\n      ".join(out)


def build_shots(shots):
    if not shots:
        return DEFAULT_BLOCKS["shots"]
    out = []
    for sh in shots[:3]:
        out.append('<div class="shot"><img src="/cp/shot/%s" alt="%s" '
                   'loading="lazy" decoding="async"><span class="cap">%s</span></div>'
                   % (_e(sh.get("id", "")), _e(sh.get("caption_ar", "")),
                      _e(sh.get("caption_ar", ""))))
    return '<div class="shots">\n      ' + "\n      ".join(out) + "\n    </div>"


def build_head_extra(base):
    b = (base or "").rstrip("/")
    ld = {"@context": "https://schema.org",
          "@graph": [
              {"@type": "Organization", "name": "Ouja Residence",
               "alternateName": "عوجا للأملاك",
               "url": (b + "/cp/ar") if b else "/cp/ar",
               "sameAs": ["https://tiktok.com/@oujares"]},
              {"@type": "LocalBusiness", "name": "عوجا للأملاك",
               "address": {"@type": "PostalAddress", "addressLocality": "Riyadh",
                           "addressCountry": "SA"}}]}
    bits = [
        '<meta name="description" content="نُشغّل وحدات مفروشة في الرياض على نظام بنيناه بأنفسنا. الملف التعريفي الكامل، بأرقام لها مصدر وتاريخ.">',
        '<meta property="og:title" content="عوجا للأملاك — الملف التعريفي">',
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="ar_SA">',
        '<meta name="robots" content="index,follow">',
        '<link rel="canonical" href="%s/cp/ar">' % _e(b) if b else
        '<link rel="canonical" href="/cp/ar">',
        '<link rel="icon" href="/cp/icon.png" type="image/png" sizes="64x64">',
        '<link rel="apple-touch-icon" href="/cp/icon-192.png">',
        '<link rel="preload" href="/cp/font/ThmanyahDisplay-500.woff2" as="font" type="font/woff2" crossorigin>',
        '<link rel="preload" href="/cp/font/Almarai-400.woff2" as="font" type="font/woff2" crossorigin>',
        "__FONT_FACES__",
    ]
    if b:
        bits += ['<meta property="og:url" content="%s/cp/ar">' % _e(b),
                 '<meta property="og:image" content="%s/cp/share.png">' % _e(b),
                 '<meta property="og:image:width" content="1200">',
                 '<meta property="og:image:height" content="630">']
    bits.append('<script type="application/ld+json">%s</script>'
                % json.dumps(ld, ensure_ascii=False))
    return "\n".join(bits)


_FONT_FACES = _read(os.path.join(_TPL, "fonts.css"))


def _contacts_blocks(contacts):
    wa = re.sub(r"\D", "", str((contacts or {}).get("whatsapp") or ""))
    email = str((contacts or {}).get("email") or "").strip()
    text = "%D8%A3%D8%B1%D8%BA%D8%A8%20%D8%A8%D8%AD%D8%AC%D8%B2%20%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%20%D9%85%D8%B9%20%D8%B9%D9%88%D8%AC%D8%A7"
    subject = "%D8%AD%D8%AC%D8%B2%20%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9"
    return {
        "__WA_HREF__": ("https://wa.me/%s?text=%s" % (wa, text)) if wa else "#meet",
        "__WA_PLAIN__": ("https://wa.me/%s" % wa) if wa else "#meet",
        "__MAIL_HREF__": ("mailto:%s?subject=%s" % (email, subject)) if email else "#meet",
        "__MAIL_PLAIN__": ("mailto:%s" % email) if email else "#meet",
        "__EMAIL_TEXT__": email or "—",
    }


def _apply_modes(out, contacts):
    """The meeting-mode and slot radios follow the admin config. The store
    guarantees ≥1 mode stays on."""
    modes = (contacts or {}).get("booking_modes") or {"online": True, "office": True}
    office_label = (contacts or {}).get("office_label_ar") or "في مكتبنا · الرياض"
    out = out.replace(
        '<label><input type="radio" name="mode" value="office"><span>في مكتبنا · الرياض</span></label>',
        ('<label><input type="radio" name="mode" value="office"><span>%s</span></label>'
         % _e(office_label)) if modes.get("office") else "")
    if not modes.get("online"):
        out = out.replace(
            '<label><input type="radio" name="mode" value="online" checked><span>عن بُعد · اتصال مرئي</span></label>',
            "")
        out = out.replace('name="mode" value="office"><span>',
                          'name="mode" value="office" checked><span>')
    slots = (contacts or {}).get("slots") or ["am", "pm", "eve"]
    slot_html = {
        "am": '<label><input type="radio" name="slot" value="am" checked><span>صباحاً</span></label>',
        "pm": '<label><input type="radio" name="slot" value="pm"><span>بعد الظهر</span></label>',
        "eve": '<label><input type="radio" name="slot" value="eve"><span>مساءً</span></label>',
    }
    for key, markup in slot_html.items():
        if key not in slots:
            out = out.replace(markup, "")
    return out


def render_v2(sections=None, snapshot=None, base="", photos=None, reviews=None,
              check=True, more_key=None, has_logo=False):
    """The v2 page (or one /more page when more_key is given).

    `sections` is an overlay-sections dict (published or working). `photos`
    maps listing_id -> {photo, srcset} resolved by the caller through the
    /stay pipeline. `reviews` is the resolved chosen-review rows (or None to
    keep the mock's verbatim defaults).
    """
    sections = sections or {}
    contacts = sections.get("contacts") or {}
    copy_overrides = sections.get("copy") or {}
    bench = sections.get("benchmarks") or {}
    showcase = (sections.get("showcase") or {}).get("units") or []
    shots = sections.get("shots") or []

    out = TEMPLATE if more_key is None else _more_shell(more_key)
    cells = stats.load(snapshot=snapshot)
    market = stats.MARKET

    def v(f):
        return cells[f]["value"]

    def f(field):
        return _fmt(field, v(field))

    cat = v("category_scores") or {}
    stamp = stats.sync_stamp(snapshot=snapshot)

    # Reach chip — rendered ONLY when both figures came through the manual
    # gate (source == "manual" means they carried a value, a date and a
    # source). An incomplete entry falls back to "seeds" and is not reported,
    # exactly like every other hand-entered number on this page.
    social_chip = ""
    followers, views = cells.get("tiktok_followers"), cells.get("tiktok_views")
    if (followers and views
            and followers["source"] == "manual" and views["source"] == "manual"
            and followers["value"] and views["value"]):
        social_chip = (
            '<a href="https://tiktok.com/@oujares" target="_blank" rel="noopener" '
            'style="color:inherit;text-decoration:none">%s مشاهدة و%s متابع على '
            'تيك توك</a>' % (_ar_millions(views["value"]),
                             _fmt("messages_total", followers["value"])))

    blocks = {
        "__DOORS__": DEFAULT_BLOCKS["doors"],
        "__TRUST__": build_trust({k: (copy_overrides.get(k) or COPY_DEFAULTS.get(k))
                                  for k in ("trust_1", "trust_2", "trust_3", "trust_4")},
                                 social_chip),
        "__PAGE_QUOTES__": build_page_quotes(reviews) if reviews
        else DEFAULT_BLOCKS["page_quotes"],
        "__DRAWER_REVIEWS__": build_drawer_reviews(reviews) if reviews
        else DEFAULT_BLOCKS["drawer_reviews"],
        "__UNITS_GRID__": build_units_grid(showcase, photos or {})
        if showcase else DEFAULT_BLOCKS["units_grid"],
        "__DRAWER_UNITS__": build_drawer_units(showcase)
        if showcase else DEFAULT_BLOCKS["drawer_units"],
        "__SHOTS__": build_shots(shots),
        "__BENCH__": DEFAULT_BLOCKS["bench"],
        "__OCC_TYPES__": DEFAULT_BLOCKS["occ_types"],
        "__HEAD_EXTRA__": build_head_extra(base),
        "__SCRIPT__": "<script>" + SCRIPT + "</script>",
        "__BOOKING_BUTTON__": (
            '<div class="f"><a class="btn btn-line" href="%s" target="_blank" '
            'rel="noopener">اختر الوقت من التقويم</a></div>'
            % _e(contacts.get("booking_link"))) if contacts.get("booking_link") else "",
    }
    for token, markup in blocks.items():
        out = out.replace(token, markup)

    resv_ok = copy_overrides.get("resv_ok") or DEFAULT_RESV_OK
    figures = {
        "__RESERVATIONS__": f("reservations_total"), "__NIGHTS__": f("nights_total"),
        "__REVIEWS__": f("reviews_total"), "__RATING__": f("rating_avg"),
        "__OCC__": f("occupancy_pct"), "__PERFECT__": f("perfect_ten_pct"),
        "__ADR__": f("adr_sar"), "__ADR90__": f("adr_90d_sar"),
        "__REVPAR__": f("revpar_sar"), "__REVPAR_ACT__": f("revpar_active_sar"),
        "__SAUDI__": f("saudi_guest_pct"), "__SAMEDAY__": f("same_day_booking_pct"),
        "__WITHIN24__": f("within_24h_pct"), "__THUFRI__": f("thu_fri_arrival_pct"),
        "__WKND_HIGH__": _fmt("adr_sar", v("weekend_adr_sar")
                              if "weekend_adr_sar" in cells else 644),
        "__WKND_LOW__": _fmt("adr_sar", v("midweek_adr_sar")
                             if "midweek_adr_sar" in cells else 554),
        "__REPEAT_GUESTS__": f("repeat_guests"), "__REPEAT_PCT__": f("repeat_booking_pct"),
        "__TOP_GUEST__": f("top_guest_stays"),
        "__SOLO__": f("solo_guest_pct"), "__COUPLE__": f("couple_guest_pct"),
        "__CAT_COMM__": _fmt("rating_avg", cat.get("communication")),
        "__CAT_CHECKIN__": _fmt("rating_avg", cat.get("check_in")),
        "__CAT_ACCURACY__": _fmt("rating_avg", cat.get("accuracy")),
        "__CAT_LOCATION__": _fmt("rating_avg", cat.get("location")),
        "__CAT_CLEAN__": _fmt("rating_avg", cat.get("cleanliness")),
        "__CAT_VALUE__": _fmt("rating_avg", cat.get("value")),
        "__RESPONSE__": f("median_response_minutes"),
        "__PER_PERSON__": f("residences_per_person_per_day"),
        "__LOC__": f("platform_lines_of_code"), "__MESSAGES__": f("messages_total"),
        "__MAINT__": f("maintenance_closed_in_sla"),
        "__MSG_START__": f("messages_monthly_start"), "__MSG_NOW__": f("messages_monthly_now"),
        "__OCC_LOW__": "53.8", "__OCC_HIGH__": "82.6",
        "__CHURN_OCC__": f("released_occupancy_pct"),
        "__RESIDENCES__": f("residences_total"),
        "__DAYS_FURN__": f("days_to_live_furnished"),
        "__DAYS_UNFURN__": f("days_to_live_unfurnished"),

        "__MKT_LISTINGS__": _fmt("reservations_total", market.get("active_listings")),
        "__MKT_ROUND__": _fmt("reservations_total",
                              int(float(market.get("active_listings") or 0) / 1000) * 1000),
        "__MKT_OCC__": _fmt("repeat_booking_pct", market.get("occupancy_pct")),
        "__MKT_ADR__": _fmt("adr_sar", market.get("adr_sar")),
        "__MKT_REVPAR__": _fmt("revpar_sar", market.get("revpar_sar")),
        "__FX__": str(market.get("fx_sar_per_usd", "")),

        "__MOT_OCC__": _bench_value(bench, "mot_occupancy"),
        "__MOT_ADR__": _bench_value(bench, "mot_adr"),
        "__KF_OCC__": _bench_value(bench, "kf_occupancy"),
        "__KF_ADR__": _bench_value(bench, "kf_adr"),
        "__KF_REVPAR__": _bench_value(bench, "kf_revpar"),
        "__YOY_OCC__": _bench_value(bench, "airdna_yoy_occupancy"),
        "__YOY_ADR__": _bench_value(bench, "airdna_yoy_adr"),
        "__YOY_SUPPLY__": _bench_value(bench, "airdna_yoy_supply"),

        "__W_OCC_M__": _pct_width(market.get("occupancy_pct"), v("occupancy_pct")),
        "__W_ADR_M__": _pct_width(market.get("adr_sar"), v("adr_sar")),
        "__W_REVPAR_M__": _pct_width(market.get("revpar_sar"), v("revpar_sar")),
        "__WC_COMM__": _pct_width(cat.get("communication"), 10),
        "__WC_CHECKIN__": _pct_width(cat.get("check_in"), 10),
        "__WC_ACCURACY__": _pct_width(cat.get("accuracy"), 10),
        "__WC_LOCATION__": _pct_width(cat.get("location"), 10),
        "__WC_CLEAN__": _pct_width(cat.get("cleanliness"), 10),
        "__WC_VALUE__": _pct_width(cat.get("value"), 10),

        "__ASOF_LINE__": "حتى " + _ar_month_year(stamp["as_of"]),
        "__RESV_OK__": _e(resv_ok),
        "__FONT_FACES__": "<style>" + _FONT_FACES + "</style>" if _FONT_FACES else "",
        "__LOGO_MARK__": logo_mark(has_logo, 21),
        "__LOGO_MARK_FOOT__": logo_mark(has_logo, 19),
    }
    figures.update(_contacts_blocks(contacts))
    for token, value in figures.items():
        out = out.replace(token, str(value))

    out = _apply_modes(out, contacts)

    # copy overrides: default string -> override, only when the overlay says so
    for key, override in copy_overrides.items():
        default = COPY_DEFAULTS.get(key)
        if default and override and override != default:
            filled_default = default
            for token, value in figures.items():
                filled_default = filled_default.replace(token, str(value))
            out = out.replace(filled_default, _e(override))

    if check:
        guard.assert_clean(out, label=("/cp/ar v2" if more_key is None
                                       else "/cp/ar/more/" + more_key))
    return out


def _ar_millions(n):
    """100000000 -> «100 مليون». Arabic reads a round reach figure as a word,
    not as a wall of zeros."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    if n >= 1000000:
        v = n / 1000000.0
        return ("%d مليون" % round(v)) if abs(v - round(v)) < 0.05 \
            else ("%.1f مليون" % v)
    return stats.fmt("messages_total", n)


_AR_MONTHS = {1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو",
              6: "يونيو", 7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر",
              11: "نوفمبر", 12: "ديسمبر"}


def _ar_month_year(iso):
    try:
        return "%s %d" % (_AR_MONTHS.get(int(str(iso)[5:7]), ""), int(str(iso)[:4]))
    except (TypeError, ValueError):
        return str(iso)


_STYLE_RE = re.compile(r"<style>.*?</style>", re.S)


def _more_shell(key):
    """A /more page: the drawer body inside a minimal shell that reuses the
    page's own stylesheet, so the standalone route looks like the drawer."""
    frag = MORE.get(key, "")
    m = re.match(r"<!-- title: ([^>]*) -->\n", frag)
    title = m.group(1).strip() if m else "المزيد"
    body = frag[m.end():] if m else frag
    style = _STYLE_RE.search(TEMPLATE)
    return (
        '<!doctype html>\n<html lang="ar" dir="rtl">\n<head>\n'
        '<title>%s — عوجا للأملاك</title>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '__HEAD_EXTRA__\n'
        '%s\n</head>\n'
        '<body style="background:var(--white)">\n'
        '<main id="main" class="wrap" style="max-width:640px;padding:40px 0 80px">\n'
        '<p class="eyebrow"><a href="/cp/ar" style="text-decoration:none">← عوجا للأملاك</a></p>\n'
        '<h2 style="margin-bottom:20px">%s</h2>\n'
        '<div class="db"><div class="dsec on">%s</div></div>\n'
        '</main>\n</body>\n</html>\n'
        % (title, style.group(0) if style else "", title, body))


def remaining_placeholders(markup):
    return sorted(set(re.findall(r"__[A-Z0-9_]+__", markup or "")))
