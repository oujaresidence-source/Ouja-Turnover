# -*- coding: utf-8 -*-
"""Open Location Code (Google Plus Code) decoder — pure, offline, no API, no key.

Many Ouja apartments carry a Plus Code in their Hostaway address ("QJVM+4MM, King Fahd
Rd, As Sahafah, Riyadh"). A Plus Code IS a coordinate written in text, so it decodes to
an exact position with no geocoder at all — which is the whole point here: the owner
does not want to register a Maps key, and address geocoding in Riyadh is unreliable for
plot-coded streets.

Implements the published Open Location Code spec (pairs section + grid refinement, and
short-code recovery against a reference point). Locked by tests/test_pluscode.py.
"""

import re

ALPHABET = "23456789CFGHJMPQRVWX"
BASE = len(ALPHABET)
SEPARATOR = "+"
SEPARATOR_POSITION = 8
PADDING = "0"
PAIR_LENGTH = 10
GRID_ROWS = 5
GRID_COLS = 4
MAX_LENGTH = 15

# A code sitting inside a longer address string: 2-8 chars, '+', then 2-3 more.
_RX = re.compile(r"\b([" + ALPHABET + PADDING + r"]{2,8}\+[" + ALPHABET + r"]{2,3})\b",
                 re.IGNORECASE)
# Google sometimes writes the code with a SPACE where the '+' belongs
# ("QH9H 8R الماجدية 84, Hittin") — six of Ouja's own addresses are like this.
# Anchored to the start of the string (or just after a comma) because four unanchored
# letters are far likelier to be a coincidence than a location.
_RX_SPACE = re.compile(r"(?:^|,)\s*([" + ALPHABET + r"]{4})[  ]([" + ALPHABET + r"]{2,3})\b",
                       re.IGNORECASE)


def find_in(text):
    """First Plus Code inside a free-text address, or None. Handles the '+' form and
    the space-instead-of-plus form Google sometimes emits."""
    s = (text or "").upper()
    m = _RX.search(s)
    if m:
        return m.group(1)
    m = _RX_SPACE.search(s)
    return (m.group(1) + SEPARATOR + m.group(2)) if m else None


def _clean(code):
    return (code or "").upper().replace(SEPARATOR, "").rstrip(PADDING)


def is_full(code):
    """A full code carries the separator at position 8 (e.g. 8FVC2222+22)."""
    c = (code or "").upper()
    return SEPARATOR in c and c.index(SEPARATOR) == SEPARATOR_POSITION


def encode(lat, lng, length=PAIR_LENGTH):
    """(lat, lng) -> full Plus Code. Only the pairs section is needed here — it is used
    to build the prefix that recovers a short code."""
    lat = min(89.999999, max(-90.0, float(lat)))
    lng = float(lng)
    while lng < -180:
        lng += 360
    while lng >= 180:
        lng -= 360
    if lat >= 90:
        lat = 89.999999

    # Mirror of decode(): both axes step through the SAME resolutions —
    # 20°, 1°, 1/20°, 1/400°, 1/8000° — latitude simply never uses the top digits.
    out = []
    lat_val = lat + 90.0
    lng_val = lng + 180.0
    res = 20.0
    for _ in range(length // 2):
        d_lat = min(BASE - 1, max(0, int(lat_val / res)))
        d_lng = min(BASE - 1, max(0, int(lng_val / res)))
        out.append(ALPHABET[d_lat])
        out.append(ALPHABET[d_lng])
        lat_val -= d_lat * res
        lng_val -= d_lng * res
        res /= BASE
    code = "".join(out)
    return code[:SEPARATOR_POSITION] + SEPARATOR + code[SEPARATOR_POSITION:]


def decode(code):
    """Full Plus Code -> (lat, lng) of the CENTRE of the code's box. None if unusable."""
    c = _clean(code)
    if len(c) < 2:
        return None
    if any(ch not in ALPHABET for ch in c):
        return None

    lat, lng = -90.0, -180.0
    lat_res, lng_res = 400.0, 400.0
    pairs = min(len(c), PAIR_LENGTH)
    for i in range(0, pairs - 1, 2):
        lat_res /= BASE
        lng_res /= BASE
        lat += ALPHABET.index(c[i]) * lat_res
        lng += ALPHABET.index(c[i + 1]) * lng_res

    lat_hi, lng_hi = lat_res, lng_res          # box size after the pairs section
    if len(c) > PAIR_LENGTH:
        for i in range(PAIR_LENGTH, min(len(c), MAX_LENGTH)):
            d = ALPHABET.index(c[i])
            lat_hi /= GRID_ROWS
            lng_hi /= GRID_COLS
            lat += (d // GRID_COLS) * lat_hi
            lng += (d % GRID_COLS) * lng_hi

    return (lat + lat_hi / 2.0, lng + lng_hi / 2.0)


def recover(short_code, ref_lat, ref_lng):
    """Short code ('QJVM+4MM') -> (lat, lng), using a nearby reference point.

    A short code drops its leading characters; they are recovered from the reference
    (for Ouja that is central Riyadh), then nudged to the nearest matching box so a
    code near a boundary does not land a grid-cell away.
    """
    c = (short_code or "").upper()
    if SEPARATOR not in c:
        return None
    if is_full(c):
        return decode(c)
    sep = c.index(SEPARATOR)
    padding = SEPARATOR_POSITION - sep
    if padding <= 0 or padding % 2:
        return None
    resolution = 20.0 ** (2 - (padding / 2.0))
    half = resolution / 2.0

    ref = encode(ref_lat, ref_lng).replace(SEPARATOR, "")
    full = ref[:padding] + c.replace(SEPARATOR, "")
    full = full[:SEPARATOR_POSITION] + SEPARATOR + full[SEPARATOR_POSITION:]
    got = decode(full)
    if not got:
        return None
    lat, lng = got
    if ref_lat + half < lat and lat - resolution >= -90:
        lat -= resolution
    elif ref_lat - half > lat and lat + resolution <= 90:
        lat += resolution
    if ref_lng + half < lng and lng - resolution >= -180:
        lng -= resolution
    elif ref_lng - half > lng and lng + resolution <= 180:
        lng += resolution
    return (lat, lng)


def from_address(text, ref_lat, ref_lng):
    """Pull a Plus Code out of a free-text address and turn it into (lat, lng)."""
    code = find_in(text)
    if not code:
        return None
    return decode(code) if is_full(code) else recover(code, ref_lat, ref_lng)
