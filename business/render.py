# -*- coding: utf-8 -*-
"""
business.render — locale formatting + page-data assembly for /business.

Numerals switch with language (superprompt §6): one utility, never a per-string
decision. The page and the PDF both read the assembled blob, so they can never
disagree (§9). Rendering reads the latest metrics_snapshot.json; if none exists
it falls back to the verified §4 numbers so layout work uses real figures.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")

# Western -> Arabic-Indic digit map, plus Arabic separators.
_AR_DIGITS = {str(i): d for i, d in enumerate("٠١٢٣٤٥٦٧٨٩")}
_AR_THOUSANDS = "٬"  # ٬ ARABIC THOUSANDS SEPARATOR
_AR_DECIMAL = "٫"    # ٫ ARABIC DECIMAL SEPARATOR
_AR_PERCENT = "٪"    # ٪ ARABIC PERCENT SIGN


def localize_digits(s, lang):
    """Swap ASCII digits for Arabic-Indic in AR; pass through in EN."""
    if lang != "ar":
        return s
    return "".join(_AR_DIGITS.get(ch, ch) for ch in str(s))


def fmt_int(n, lang):
    western = "{:,}".format(int(round(n)))  # 7,311
    if lang != "ar":
        return western
    return localize_digits(western.replace(",", _AR_THOUSANDS), lang)


def fmt_dec(n, lang, places=2):
    western = ("{:,.%df}" % places).format(float(n))  # 4.77
    if lang != "ar":
        return western
    western = western.replace(",", _AR_THOUSANDS).replace(".", _AR_DECIMAL)
    return localize_digits(western, lang)


def fmt_pct(fraction, lang, places=1):
    western = ("{:.%df}" % places).format(float(fraction) * 100)  # 87.6
    if lang != "ar":
        return western + "%"
    return localize_digits(western.replace(".", _AR_DECIMAL), lang) + _AR_PERCENT


# --------------------------------------------------------------------------- #
# emoji detection (§6 CI check — applied to OUR chrome, never to verbatim reviews)
# --------------------------------------------------------------------------- #
# Typographic symbols the design uses on purpose (not colorful emoji).
# ★ appears in the brief's own hero strip spec ("4.77★", superprompt §A1).
_EMOJI_WHITELIST = {0x2605, 0x2606}


def contains_emoji(text):
    """True if the string carries a pictographic emoji. Deliberately does NOT
    flag Arabic script, the ٪٫٬ separators, the ★ rating glyph, or punctuation."""
    for ch in (text or ""):
        cp = ord(ch)
        if cp in _EMOJI_WHITELIST:
            continue
        if (0x1F000 <= cp <= 0x1FAFF        # symbols & pictographs, emoji, symbols-ext
                or 0x2600 <= cp <= 0x27BF    # misc symbols + dingbats
                or cp in (0x2764, 0x2B50, 0x2705, 0x2714, 0x2728)
                or 0x2190 <= cp <= 0x21FF and cp in (0x2194, 0x2195)
                or cp == 0xFE0F              # variation selector-16 (emoji presentation)
                or 0x1F1E6 <= cp <= 0x1F1FF):  # regional indicators
            return True
    return False


# --------------------------------------------------------------------------- #
# data assembly
# --------------------------------------------------------------------------- #
def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def load_metrics(state_dir=None):
    """Latest metrics_snapshot.json from STATE_DIR, else the verified §4 fallback."""
    state_dir = state_dir or os.environ.get("STATE_DIR", "/data")
    snap = _load_json(os.path.join(state_dir, "metrics_snapshot.json"), None)
    # A zero/empty snapshot means the live fetch failed — NEVER show zeros to a
    # diligence reader. Fall back to the verified §4 numbers instead.
    if isinstance(snap, dict) and snap.get("reservations_total"):
        return snap
    return _load_json(os.path.join(_DATA, "verified_fallback.json"), {})


def load_reviews():
    return _load_json(os.path.join(_DATA, "reviews_curated.json"), [])


def load_manual():
    # import here to avoid a cycle at module import time
    from .manual import load_manual_metrics
    return load_manual_metrics(path=os.path.join(_HERE, "manual_metrics.json"))


def assemble(lang, state_dir=None):
    """The single blob the page and PDF both render from."""
    metrics = load_metrics(state_dir=state_dir)
    return {
        "lang": lang,
        "as_of": metrics.get("as_of"),
        "metrics": metrics,
        "manual": load_manual(),
        "reviews": load_reviews(),
    }
