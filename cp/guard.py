# -*- coding: utf-8 -*-
"""
cp.guard — the disclosure guard (seeds §0 «THE THREE-BUCKET RULE», §3, §11).

This page goes to investors and to a government ministry. Some figures are real,
material, and must never be published; others are simply stale and wrong. Neither
class can be kept off the page by discipline alone — a future edit by someone who
never opened the seeds file would reintroduce them silently.

So the rule is enforced structurally: every rendered edition is scanned, and a
withheld or retired figure raises DisclosureError, which fails the build.

HOW IT SCANS — the details are the whole safety of it:
  * <style>, <script> and comments are removed FIRST. CSS is full of innocent
    numbers (width:72px) and flagging them would only teach someone to switch
    the guard off. We police published copy, not stylesheets.
  * meta `content` and image `alt` ARE published copy, so they are scanned.
  * Arabic-Indic digits and the ٬ ٫ separators fold to ASCII before matching,
    so ٧٬٣١١ cannot smuggle a retired 7,311 past a Western-numeral pattern.
  * Numbers are TOKENISED, not substring-matched. "1,606" does not contain a
    forbidden 606; "606" does. Substring matching produced false positives that
    made an earlier version of this idea unusable.

TWO CLASSES OF FIGURE, because they need different treatment:
  * BARE — distinctive enough that their mere presence is a leak (7,669,457).
  * CONTEXTUAL — the number alone is innocent and often published on purpose.
    Seeds §7 publishes "19 residences released"; seeds §3 withholds the
    "53 active / 19 stopped" split. So 19 is only a leak next to "stopped".
    Same for 72/71/67/60/70/100, which are retired UNIT COUNTS, not retired
    numbers — "100%" must keep working.

Whitelisted on purpose (seeds §3): ADR 582 / 654 and RevPAR 451 / 485.
"""
import html as _html
import re

# --------------------------------------------------------------------------- #
# digit folding
# --------------------------------------------------------------------------- #
_FOLD = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_FOLD.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})  # extended Arabic-Indic
_FOLD[0x066C] = ","   # ٬ arabic thousands separator
_FOLD[0x066B] = "."   # ٫ arabic decimal separator


def fold_digits(text):
    """Arabic-Indic digits and separators -> ASCII, so one pattern set covers both."""
    return (text or "").translate(_FOLD)


# --------------------------------------------------------------------------- #
# visible text extraction
# --------------------------------------------------------------------------- #
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
_ATTR = re.compile(r"""\b(?:content|alt|title|aria-label)\s*=\s*["']([^"']*)["']""", re.I)
_TAG = re.compile(r"<[^>]+>")


def visible_text(markup):
    """Everything a reader (or a diligence analyst with ctrl-F) can actually see."""
    s = _COMMENT.sub(" ", markup or "")
    s = _BLOCK.sub(" ", s)
    # attribute copy is published copy — lift it into the text stream before
    # the tags are stripped, or a leak in an alt or an og:description walks free.
    attrs = " ".join(_ATTR.findall(s))
    s = _TAG.sub(" ", s)
    s = _html.unescape(s + " " + attrs)
    return fold_digits(re.sub(r"\s+", " ", s))


# --------------------------------------------------------------------------- #
# what may never appear
# --------------------------------------------------------------------------- #
# Published deliberately despite being financial (seeds §3).
WHITELIST = {582.0, 654.0, 451.0, 485.0}

# Seeds §3 (withheld) + §11 (retired) — distinctive enough to flag on sight.
BARE = {
    7669457: "all-time gross revenue (seeds §3)",
    275199: "2024 revenue (seeds §3)",
    2528801: "2025 revenue (seeds §3)",
    4865456: "2026 revenue (seeds §3)",
    2001914: "last-90-days revenue (seeds §3)",
    14731: "revenue per active residence (seeds §3)",
    2412347: "stopped-residence revenue (seeds §3)",
    7836: "Airbnb channel reservation count (seeds §3)",
    # 2026 monthly revenue table (data-seed-2026-08 — internal only)
    583867: "January 2026 revenue (data-seed)", 494330: "February 2026 revenue (data-seed)",
    480434: "March 2026 revenue (data-seed)", 712470: "April 2026 revenue (data-seed)",
    674651: "May 2026 revenue (data-seed)", 592635: "June 2026 revenue (data-seed)",
    762810: "July 2026 revenue (data-seed)", 564259: "August 2026 revenue (data-seed)",
    592000: "direct channel revenue (seeds §3)",
    7080000: "Airbnb gross (seeds §3)",
    5360000: "Airbnb payout (seeds §3)",
    2860000: "1BR revenue by type (seeds §3)",
    3190000: "2BR revenue by type (seeds §3)",
    1350000: "3BR revenue by type (seeds §3)",
    7311: "RETIRED stay count — correct figure is 8,114 (seeds §11)",
    11307: "RETIRED night count — correct figure is 13,093 (seeds §11)",
    14000: "RETIRED turnover count (seeds §11)",
    49000: "RETIRED lines of code — correct figure is ~66,000 (seeds §11)",
    45000: "RETIRED lines of code (seeds §11)",
    57600: "RETIRED lines of code (seeds §11)",
    4.8: "RETIRED rating — the real average is 4.77 (seeds §11)",
    # Identity documents (seeds §1). Both are 🟢 in the PDF and the ministry file
    # and 🔴 on the public page, so they are blocked here and nowhere else.
    7050158810: "commercial registration number — PDF and ministry file only (seeds §1)",
    1200050611: "فال licence number — the page may say only that we operate under one (seeds §1)",
}

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

# The number alone is innocent; the pairing is the leak.
_UNIT_WORD = r"(?:residence|residences|listing|listings|unit|units|apartment|apartments|وحدة|وحدات|عقار|عقارات|شقة|شقق)"
# Small numbers from the withheld table (945, 606, 455, 278, 1859) are NOT
# matched bare: a live metric can innocently reach them — repeat_guests is 933
# today and passes 945 within weeks, and a bare match would kill the page the
# night it happens. They are leaks only in their own context: money for the
# booking values, agreements for the 455, channel words for the counts.
_MONEY = r"(?:SAR|ريال|ر\.س)"
CONTEXTUAL = [
    (re.compile(r"\b945\b[^.\n]{0,16}" + _MONEY, re.I),
     "average booking value (seeds §3)"),
    (re.compile(_MONEY + r"[^.\n]{0,16}\b945\b", re.I),
     "average booking value (seeds §3)"),
    (re.compile(r"\b606\b[^.\n]{0,16}" + _MONEY, re.I),
     "median booking value (seeds §3)"),
    (re.compile(r"(?:median|الوسيط|وسيط)[^.\n]{0,20}\b606\b", re.I),
     "median booking value (seeds §3)"),
    (re.compile(r"\b455\b[^.\n]{0,30}(?:unsigned|agreement|عقد|عقود|اتفاق)", re.I),
     "unsigned rental agreements — internal only (seeds §3)"),
    (re.compile(r"(?:unsigned|غير موقعة?)[^.\n]{0,30}\b455\b", re.I),
     "unsigned rental agreements — internal only (seeds §3)"),
    (re.compile(r"\b278\b[^.\n]{0,24}(?:direct|مباشر)", re.I),
     "direct channel reservation count (seeds §3)"),
    (re.compile(r"(?:direct|المباشر|مباشر)[^.\n]{0,24}\b278\b", re.I),
     "direct channel reservation count (seeds §3)"),
    (re.compile(r"\b1,?859\b[^.\n]{0,30}(?:revenue|إيراد|" + _MONEY + ")", re.I),
     "90-day reservation count paired with revenue (seeds §3)"),

    # ---- data-seed-2026-08 additions (v2) --------------------------------- #
    # the management fee percentage, any phrasing
    (re.compile(r"(?:fee|رسوم|أتعاب|نسبة الإدارة|الإدارة)[^.\n]{0,30}\b20\s*%", re.I),
     "management fee percentage (data-seed)"),
    (re.compile(r"\b20\s*%[^.\n]{0,30}(?:fee|رسوم|أتعاب|management|إدارة)", re.I),
     "management fee percentage (data-seed)"),
    # the Airbnb take rate
    (re.compile(r"(?:airbnb|المنصة|منصة الحجز)[^.\n]{0,30}\b~?24\s*%", re.I),
     "Airbnb take rate (data-seed)"),
    (re.compile(r"\b~?24\s*%[^.\n]{0,30}(?:take|عمولة|تأخذ|يأخذ)", re.I),
     "Airbnb take rate (data-seed)"),
    # per-type ADR / RevPAR — the numbers are only leaks beside a unit-type or
    # rate word (426 alone could be an innocent live figure one day)
    (re.compile(r"\b(?:426|765|675|1,?170|682|345|574|483|963|533)\b[^.\n]{0,40}"
                r"(?:BR|غرف|غرفة|نوم|type|نوع)", re.I),
     "per-type ADR/RevPAR (data-seed)"),
    (re.compile(r"(?:BR|غرف|غرفة|نوم|ADR|RevPAR|سعر الليلة|العائد)[^.\n]{0,40}"
                r"\b(?:426|765|675|1,?170|682|345|574|483|963|533)\b", re.I),
     "per-type ADR/RevPAR (data-seed)"),
    # unit counts per type
    (re.compile(r"\b(?:23|29|17)\b[^.\n]{0,24}(?:units?|وحدة|وحدات)[^.\n]{0,16}"
                r"(?:BR|غرف|غرفة|نوم)", re.I),
     "unit count per type (data-seed)"),
    (re.compile(r"\b(?:23|29|17)\s*(?:units? of|وحدة من)", re.I),
     "unit count per type (data-seed)"),
    # per-unit revenues in K
    (re.compile(r"\b(?:404|346|276|271|211)\s*K\b", re.I),
     "named-unit revenue (data-seed)"),
    # unknown/off-system payments
    (re.compile(r"\b284\b[^.\n]{0,40}(?:unknown|مجهول|خارج النظام|payments?|دفع)", re.I),
     "off-system payment count (data-seed — internal only)"),
    (re.compile(r"(?:unknown|مجهول|خارج النظام)[^.\n]{0,30}\b284\b", re.I),
     "off-system payment count (data-seed — internal only)"),
    (re.compile(r"\b(?:60|67|70|71|72|100)\s*\+?\s*" + _UNIT_WORD, re.I),
     "RETIRED residence count — the published figure is 74 (seeds §2, §11)"),
    (re.compile(r"\b53\b[^.\n]{0,24}\b(?:active|نشط|نشطة|تعمل)", re.I),
     "active/stopped portfolio split (seeds §3)"),
    (re.compile(r"\b(?:active|نشط|نشطة)\b[^.\n]{0,24}\b53\b", re.I),
     "active/stopped portfolio split (seeds §3)"),
    (re.compile(r"\b19\b[^.\n]{0,24}\b(?:stopped|paused|متوقف|متوقفة)", re.I),
     "active/stopped portfolio split (seeds §3)"),
    (re.compile(r"\b(?:2\.86|3\.19|1\.35|7\.08|5\.36|1\.7)\s*M\b", re.I),
     "revenue by unit type / channel economics (seeds §3)"),
    (re.compile(r"\b(?:152|119|592)\s*K\b", re.I),
     "revenue by unit type / channel revenue (seeds §3)"),
    (re.compile(r"\b(?:11\.4|17\.1|15\.3|29\.3|16\.2)\s*K\b", re.I),
     "per-unit monthly revenue (seeds §3)"),
    (re.compile(r"\b7\.[56]\s*[x×]", re.I),
     "revenue-per-listing multiple — reverse-engineers per-residence revenue (seeds §4)"),
    (re.compile(r"(?:management fee|رسوم الإدارة|نسبة الإدارة)[^.\n]{0,40}\d{1,2}(?:\.\d+)?\s*%", re.I),
     "management fee percentage (seeds §3, §7)"),
    # NB: the trailing phrase must name the FEE, not merely revenue. Seeds §3
    # publishes "6% of bookings, 26% of revenue" for long stays — an earlier,
    # looser version of this pattern flagged that published line.
    (re.compile(r"\d{1,2}(?:\.\d+)?\s*%[^.\n]{0,40}(?:management fee|رسوم الإدارة|of collected revenue|من الإيراد المحصّل|من الإيراد المحصل)", re.I),
     "management fee percentage (seeds §3, §7)"),
    (re.compile(r"(?:payout|التوزيع|الدفعات)[^.\n]{0,30}\d{1,2}(?:\.\d+)?\s*%", re.I),
     "payout-programme rate (seeds §7 — mechanism only, never the percentages)"),
    (re.compile(r"\d{1,2}(?:\.\d+)?\s*%[^.\n]{0,30}(?:take rate|commission|عمولة)", re.I),
     "channel take rate (seeds §3)"),
    # Seeds §1: "Tourism facility-management licence status — Do not mention at
    # all. Removed by decision." Per-residence tourism PERMITS stay publishable,
    # so this matches the facility-management licence only.
    (re.compile(r"(?:tourism\s+)?facility[- ]management\s+licen|رخصة\s+إدارة\s+المرافق|إدارة\s+المرافق\s+السياحية", re.I),
     "tourism facility-management licence — must not be mentioned at all (seeds §1)"),
    (re.compile(r"\bH8\s*VLG\b", re.I),
     "named best/worst residence — internal only (seeds §3)"),
    (re.compile(r"\b11B\s+Royal\b", re.I),
     "named best/worst residence — internal only (seeds §3)"),
    # data-seed named units. Long codes match bare; SHORT codes (F2, D7, 201a,
    # 202B, FD1, C204, 3BMJ) only beside unit/occupancy/revenue words so an id
    # in a hash can never trip them.
    (re.compile(r"\b(?:HUE\s*9|C2\s*NFL|9B\s*HTN|103\s*NRJS|E5MLQ|13\s*JOOD|"
                r"101-?Narjs|TWN\s*13B|4511)\b", re.I),
     "named best/worst residence (data-seed — internal only)"),
    (re.compile(r"القيروان-?\s?D7", re.I),
     "named residence (data-seed — internal only)"),
    (re.compile(r"(?:وحدة|unit|شقة)[^.\n]{0,12}\b(?:F2|D7|201a|202B|FD1|C204|3BMJ)\b"
                r"|\b(?:F2|D7|201a|202B|FD1|C204|3BMJ)\b[^\n]{0,24}?"
                r"(?:occupancy|إشغال|revenue|إيراد|churn|left|خرجت|وحدة|K\b|%)", re.I),
     "named residence (data-seed — internal only)"),
]


class DisclosureError(AssertionError):
    """A withheld or retired figure reached a rendered page."""


def scan(markup):
    """Return a list of {figure, why} for everything that must not be published."""
    text = visible_text(markup)
    found = []

    for raw in _NUMBER.findall(text):
        token = raw.rstrip(",")
        try:
            value = float(token.replace(",", ""))
        except ValueError:
            continue
        if value in WHITELIST:
            continue
        why = BARE.get(int(value) if value.is_integer() else value)
        if why:
            found.append({"figure": token, "why": why})

    for pattern, why in CONTEXTUAL:
        for m in pattern.finditer(text):
            found.append({"figure": m.group(0).strip(), "why": why})

    return found


def assert_clean(markup, label=""):
    """Raise DisclosureError naming every offending figure. Used by the tests
    and by the render path, so a leak cannot ship even if a test is skipped."""
    hits = scan(markup)
    if not hits:
        return
    lines = ["%s must not be published — %s" % (h["figure"], h["why"]) for h in hits]
    where = (" in %s" % label) if label else ""
    raise DisclosureError(
        "disclosure guard failed%s (seeds §0):\n  " % where + "\n  ".join(lines))
