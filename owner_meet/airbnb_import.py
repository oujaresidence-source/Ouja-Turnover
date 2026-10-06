# -*- coding: utf-8 -*-
"""
owner_meet.airbnb_import — Airbnb «Host Opportunity Report v5 — Promotions» → rows. PURE.

Columns are found by HEADER NAME, never by position. The v5 export carries a disclaimer row, a
"Data As Of" row, a group-header row («Listing Details», «Weekly Discount Opportunities», …), a
counts row and the real header row — and repeats header names ("Median Discount of Similar
Listings", "Listing Eligible") under different groups, so a column is keyed by (group, header).

Blank is NOT zero: an empty cell is stored as None. Airbnb leaves "Your Available Nights Next 14
Days" empty outside the last-minute section, and "Opportunity Rank" can skip a number (rank 8 is
absent in the 2026-10-04 file) — neither is an error.
"""

import csv
import io
import re

MAX_BYTES = 5 * 1024 * 1024
TAB = chr(9)                      # no backslash escapes anywhere in this package (brief P3)

ERR_NOT_REPORT = "الملف لا يشبه تقرير فرص المضيف من Airbnb — ما لقينا عمود Title (Listing ID)"
ERR_EMPTY = "الملف فاضي أو ما فيه صفوف شقق"
ERR_TOO_BIG = "الملف أكبر من 5 ميغا"

# field -> (group, header, kind). group None = header is unique, match it anywhere.
FIELDS = (
    ("title", "Listing Details", "Title (Listing ID)", "text"),
    ("bedrooms", "Listing Details", "Bedrooms", "int"),
    ("url", "Listing Details", "URL", "text"),
    ("rank", None, "Opportunity Rank", "int"),
    ("lifetime_bookings", None, "Lifetime Bookings", "int"),
    ("bookings_l365", None, "Total Bookings L365", "int"),
    ("search_to_booking", None, "Search Results to Bookings YTD", "pct"),
    ("view_to_booking", None, "Listing Views to Bookings YTD", "pct"),
    ("gbv_usd", None, "Gross Booking Value YTD (USD)", "money"),
    ("gbv_yoy", None, "Gross Booking Value YTD (YoY)", "pct"),
    ("occ_n3m", None, "Airbnb Occupancy N3 Months", "pct"),
    ("occ_n3m_yoy", None, "Airbnb Occupancy N3 Months (YoY)", "pct"),
    ("rating", None, "Lifetime Overall Rating", "rating"),
    ("guest_favorite", None, "Guest Favorite", "yesno"),
    ("trg_eligible", "Top Rated Guest Discount", "Listing Eligible", "yesno"),
    ("weekly_current", "Weekly Discount Opportunities", "Your Current Weekly Discount", "pct"),
    ("weekly_similar", "Weekly Discount Opportunities", "Median Discount of Similar Listings", "range"),
    ("monthly_current", "Monthly Discount Opportunities", "Your Current Monthly Discount", "pct"),
    ("monthly_similar", "Monthly Discount Opportunities", "Median Discount of Similar Listings", "range"),
    ("cleaning_fee", "Cleaning Fee Opportunities", "Current Airbnb Cleaning Fee (Local Currency)", "money"),
    ("cleaning_similar", "Cleaning Fee Opportunities", "Similar Listing Comparison", "text"),
    ("early_bird_current", "Early Bird Opportunities", "Your Current Early Bird Discount", "pct"),
    ("early_bird_similar", "Early Bird Opportunities", "Median Discount of Similar Listings", "range"),
    ("nonref_eligible", "Non-Refundable Option", "Listing Eligible", "yesno"),
    ("new_listing_eligible", "New Listing Promotion", "Listing Eligible for Promotion", "yesno"),
    ("last_minute_current", "Last Minute Discount", "Your Current Last Minute Discount", "pct"),
    ("last_minute_lead_days", "Last Minute Discount", "Your Current Lead Day Threshold", "int"),
    ("avail_14", "Last Minute Discount", "Your Available Nights Next 14 Days", "int"),
)
REQUIRED = ("title", "bedrooms", "rank")

_ID_IN_TITLE = re.compile("[(]([0-9]{6,})[)][ ]*$")
_ID_IN_URL = re.compile("rooms/([0-9]{6,})")
_NUM = re.compile("-?[0-9]+(?:[.][0-9]+)?")


def _norm(s):
    return " ".join(str(s or "").split()).lower()


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# ---------------------------------------------------------------- reading
def read_table(data, filename=""):
    """bytes -> list of rows (lists of str). TSV / CSV / XLSX."""
    if len(data) > MAX_BYTES:
        raise ValueError(ERR_TOO_BIG)
    name = (filename or "").lower()
    if name.endswith(".xlsx") or data[:2] == b"PK":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        best = None
        for ws in wb.worksheets:
            rows = [[_cell(v) for v in r] for r in ws.iter_rows(values_only=True)]
            if any(_norm(c) == _norm("Title (Listing ID)") for r in rows for c in r):
                best = rows
                break
            if best is None:
                best = rows
        wb.close()
        return best or []
    text = None
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(ERR_NOT_REPORT)
    head = text[:4096]
    delim = TAB if (name.endswith(".tsv") or head.count(TAB) > head.count(",")) else ","
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]


# ---------------------------------------------------------------- values
def _pct(s):
    m = _NUM.search(s.replace(",", ""))
    return round(float(m.group(0)) / 100.0, 10) if m else None


def _value(raw, kind):
    s = (raw or "").strip()
    if s == "":
        return None
    if kind == "text":
        return s
    if kind == "int":
        m = _NUM.search(s.replace(",", ""))
        return int(float(m.group(0))) if m else None
    if kind == "money":
        m = _NUM.search(s.replace(",", "").replace("$", ""))
        return float(m.group(0)) if m else None
    if kind == "rating":
        m = _NUM.search(s)
        return float(m.group(0)) if m else None
    if kind == "pct":
        if "%" not in s:                                   # an xlsx cell may hold 0.0007 as a number
            m = _NUM.search(s)
            return float(m.group(0)) if m else None
        return _pct(s)
    if kind == "yesno":
        low = s.lower()
        return True if low in ("yes", "y", "true", "1") else (False if low in ("no", "n", "false", "0") else None)
    if kind == "range":
        nums = _NUM.findall(s.replace(",", ""))
        if not nums:
            return None
        lo, hi = float(nums[0]) / 100.0, float(nums[-1]) / 100.0
        return {"lo": round(lo, 10), "hi": round(hi, 10)}
    return s


# ---------------------------------------------------------------- parsing
def _find_header(rows):
    want = _norm("Title (Listing ID)")
    for i, r in enumerate(rows):
        if any(_norm(c) == want for c in r):
            return i
    return None


def _group_row(rows, hi):
    for i in range(hi - 1, -1, -1):
        if any(_norm(c) == _norm("Listing Details") for c in rows[i]):
            return rows[i]
    return None


def _data_as_of(rows, hi):
    for r in rows[:hi]:
        for j, c in enumerate(r):
            if _norm(c) == "data as of":
                for v in r[j + 1:]:
                    if str(v).strip():
                        return str(v).strip()[:10]
    return None


def _columns(header, group_row):
    """(group_norm, header_norm) -> index, plus header_norm -> [indexes]."""
    by_pair, by_head = {}, {}
    grp = ""
    for j, h in enumerate(header):
        if group_row is not None and j < len(group_row) and str(group_row[j]).strip():
            grp = _norm(group_row[j])
        hn = _norm(h)
        if not hn:
            continue
        by_pair[(grp, hn)] = j
        by_head.setdefault(hn, []).append(j)
    return by_pair, by_head


def airbnb_id_of(title, url=None):
    m = _ID_IN_TITLE.search((title or "").strip())
    if m:
        return m.group(1)
    m = _ID_IN_URL.search(url or "")
    return m.group(1) if m else None


def parse(data, filename=""):
    """bytes -> {"data_as_of", "rows", "missing"}; raises ValueError(arabic) on a non-report file."""
    rows = read_table(data, filename)
    hi = _find_header(rows)
    if hi is None:
        raise ValueError(ERR_NOT_REPORT)
    header = rows[hi]
    by_pair, by_head = _columns(header, _group_row(rows, hi))
    idx, missing = {}, []
    for field, group, head, _kind in FIELDS:
        hn = _norm(head)
        j = by_pair.get((_norm(group), hn)) if group else None
        if j is None:
            cand = by_head.get(hn) or []
            j = cand[0] if (cand and (group is None or len(cand) == 1)) else None
        if j is None:
            missing.append(field)
        idx[field] = j
    if any(f in missing for f in REQUIRED):
        raise ValueError(ERR_NOT_REPORT)
    kinds = {f: k for f, _g, _h, k in FIELDS}
    out = []
    for r in rows[hi + 1:]:
        if not any(str(c).strip() for c in r):
            continue
        rec = {}
        for field, j in idx.items():
            raw = r[j] if (j is not None and j < len(r)) else ""
            rec[field] = _value(_cell(raw), kinds[field])
        if not rec.get("title"):
            continue
        rec["airbnb_id"] = airbnb_id_of(rec["title"], rec.get("url"))
        rec["title_clean"] = _ID_IN_TITLE.sub("", rec["title"]).strip()
        out.append(rec)
    if not out:
        raise ValueError(ERR_EMPTY)
    return {"data_as_of": _data_as_of(rows, hi), "rows": out, "missing": missing}
