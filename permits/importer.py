# -*- coding: utf-8 -*-
"""
permits.importer — CSV / XLSX / JSON bytes → preview rows → (later, on an explicit click)
stored permits.

THE RULES IT EXISTS TO KEEP
---------------------------
1. NOTHING IS DROPPED. Row count in == row count out. An unreadable end date makes a
   `needs_data` row (shown red in the digest every day), never a skipped one.
2. NATIONAL IDs NEVER LAND. Any column whose header looks like an ID (هوية / سجل مدني /
   إقامة / national id / iqama / id number) keeps the LAST 4 DIGITS ONLY, and any 10-digit
   number starting 1 or 2 found in any other cell is masked before it is stored (§2.3).
3. NO GUESSING IN SILENCE. Ambiguous dates, guessed columns and duplicate permit numbers
   are flagged on the row and shown in the preview.
4. preview() stores NOTHING. commit() RE-PARSES the same upload server-side — the browser's
   copy of a date is never trusted.

openpyxl TRAP: `read_only=True` does NOT load hyperlinks, and the seed's Drive links live
in cell hyperlinks. XLSX files are therefore opened with read_only=False (capped at 5 MB).
"""

import csv
import io
import json
import re

from . import dates, db, engine

MAX_BYTES = 5 * 1024 * 1024
_NATIONAL_ID = re.compile(r"\b[12][0-9]{9}\b")


class ImportError_(ValueError):
    """A file we cannot read at all (wrong type, too big, empty). Carries Arabic text."""


def mask_ids(text):
    """Any national-ID-shaped number becomes «••••1234». Belt and braces for free-text cells."""
    return _NATIONAL_ID.sub(lambda m: "••••" + m.group(0)[-4:], str(text))


def last4(value):
    digits = re.sub(r"\D", "", dates.clean_text(value))
    return digits[-4:] if len(digits) >= 4 else ""


def _cell_text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return dates.clean_text(v)


# ---------------- reading the file ----------------

def _decode(data):
    for enc in ("utf-8-sig", "utf-8", "cp1256"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ImportError_("ما قدرنا نقرأ ترميز الملف — احفظه CSV UTF-8 وجرّب مرة ثانية")


def read_table(data, filename):
    """-> (rows: [[cell, ...]], links: {(r, c): url}, kind). Raw cells, no interpretation."""
    if not data:
        raise ImportError_("الملف فاضي")
    if len(data) > MAX_BYTES:
        raise ImportError_("الملف أكبر من ٥ ميجا")
    name = str(filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm") or data[:2] == b"PK":
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=False, data_only=True)
        except Exception as e:
            raise ImportError_("ما قدرنا نفتح ملف الإكسل: %s" % type(e).__name__)
        best = None
        for ws in wb.worksheets:                 # the sheet with the most header hits wins
            rows, links = [], {}
            for r_i, row in enumerate(ws.iter_rows()):
                vals = []
                for c_i, cell in enumerate(row):
                    vals.append(cell.value)
                    hl = getattr(cell, "hyperlink", None)
                    target = getattr(hl, "target", None) if hl is not None else None
                    if target:
                        links[(r_i, c_i)] = str(target)
                rows.append(vals)
            hits = 0
            if rows:
                h = engine.detect_header_row(rows)
                hits = sum(1 for c in rows[h] if c is not None and engine.map_header(c)[0])
            if best is None or hits > best[0]:
                best = (hits, rows, links)
        return best[1], best[2], "xlsx"
    if name.endswith(".json") or data.lstrip()[:1] in (b"[", b"{"):
        try:
            obj = json.loads(_decode(data))
        except ValueError:
            raise ImportError_("ملف JSON غير صالح")
        items = obj.get("rows") if isinstance(obj, dict) else obj
        if not isinstance(items, list) or not items:
            raise ImportError_("ملف JSON ما فيه صفوف")
        if all(isinstance(x, dict) for x in items):
            headers = []
            for x in items:
                for k in x:
                    if k not in headers:
                        headers.append(k)
            return [headers] + [[x.get(h) for h in headers] for x in items], {}, "json"
        return [list(x) if isinstance(x, (list, tuple)) else [x] for x in items], {}, "json"
    text = _decode(data)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)], {}, "csv"


# ---------------- interpreting it ----------------

_TEXT_FIELDS = ("unit_text", "permit_no", "holder", "district", "street", "building_no",
                "unit_no", "ownership_kind", "permit_type", "issuer", "responsible",
                "renew_notes", "notes")


def parse(data, filename, default_type=None, default_issuer=""):
    """-> {"rows": [row, ...], "header_row": i, "columns": [...], "source_rows": n,
           "kind": 'xlsx'|'csv'|'json'}. Stores nothing."""
    table, links, kind = read_table(data, filename)
    if not table:
        raise ImportError_("الملف ما فيه بيانات")
    h_idx = engine.detect_header_row(table)
    headers = table[h_idx]
    columns = []                                 # [{index, header, field, hint, is_id}]
    taken = set()
    for i, h in enumerate(headers):
        htext = _cell_text(h)
        field, hint = engine.map_header(htext) if htext else (None, None)
        is_id = bool(htext) and (field == "holder_id" or engine.is_id_header(htext))
        if is_id:
            field = "holder_id"
        if field in taken and field not in (None,):
            field = None                          # a second "notes" column goes to extra_json
        if field:
            taken.add(field)
        columns.append({"index": i, "header": htext, "field": field, "hint": hint, "is_id": is_id})

    body = [r for r in table[h_idx + 1:]]
    body_idx = list(range(h_idx + 1, len(table)))
    # drop only TRULY empty rows (every cell blank) — a row with anything in it is kept
    kept = [(ri, r) for ri, r in zip(body_idx, body) if any(_cell_text(c) for c in (r or []))]

    guessed = set()
    if "end_date" not in taken:
        cand = [c["index"] for c in columns if not c["field"]]
        s_col, e_col = engine.guess_date_columns([r for _ri, r in kept], cand)
        for col, fld in ((e_col, "end_date"), (s_col, "start_date")):
            if col is not None and fld not in taken:
                columns[col]["field"] = fld
                guessed.add(fld)
                taken.add(fld)

    rows = []
    for ri, raw in kept:
        cells = list(raw or []) + [None] * (len(columns) - len(raw or []))
        row = {"row_index": ri + 1, "extra": {}, "review_issues": [], "issues": []}
        for col in columns:
            v = cells[col["index"]] if col["index"] < len(cells) else None
            fld = col["field"]
            if col["is_id"]:
                row["holder_id_last4"] = last4(v)          # the full number stops HERE
                continue
            if fld in ("start_date", "end_date"):
                p = dates.parse_date(v, col["hint"])
                row[fld] = p["iso"]
                row[fld + "_raw"] = mask_ids(_cell_text(v))
                row["_" + fld + "_issue"] = p["issue"]
                continue
            if fld == "doc":
                txt = _cell_text(v)
                url = links.get((ri, col["index"]), "")
                if not url and re.match(r"^https?://", txt):
                    url = txt
                row["doc_name"] = mask_ids(txt)
                row["doc_url"] = url
                continue
            if fld == "serial":
                t = _cell_text(v)
                row["serial"] = int(float(t)) if re.fullmatch(r"\d+(\.0+)?", t) else None
                continue
            if fld:
                row[fld] = mask_ids(_cell_text(v))
                continue
            txt = _cell_text(v)
            if txt and col["header"]:
                row["extra"][col["header"]] = mask_ids(txt)
            elif txt:
                row["extra"]["عمود %d" % (col["index"] + 1)] = mask_ids(txt)
        _finish(row, filename, default_type, default_issuer, guessed)
        rows.append(row)

    _flag_duplicates(rows)
    return {"rows": rows, "header_row": h_idx + 1, "source_rows": len(rows), "kind": kind,
            "columns": [{k: c[k] for k in ("header", "field", "hint")} for c in columns]}


def _finish(row, filename, default_type, default_issuer, guessed):
    row["permit_no"] = re.sub(r"\.0+$", "", row.get("permit_no") or "")
    row["permit_type"] = row.get("permit_type") or default_type or engine.SEED_TYPE
    row["issuer"] = row.get("issuer") or default_issuer or engine.type_default(row, "issuer")
    row["scope"] = "unit" if row.get("unit_text") else ("building" if row.get("building_no") else "other")
    row["responsible_name"] = row.pop("responsible", "") or ""
    row["source_ref"] = "%s#%s" % (filename or "upload", row.get("serial") or row["row_index"])
    end_issue = row.pop("_end_date_issue", "")
    start_issue = row.pop("_start_date_issue", "")
    issue = end_issue or start_issue
    if "end_date" in guessed and not issue:
        issue = "guessed_column"
    row["date_issue"] = issue
    row["needs_data"] = 0 if row.get("end_date") else 1
    row.setdefault("start_date", None)
    row.setdefault("end_date", None)
    row["extra_json"] = row.pop("extra")
    if row["needs_data"]:
        row["issues"].append({"code": "needs_data", "text_ar": "تاريخ الانتهاء غير مقروء — بيتسجّل «ناقص بيانات»"})
    elif issue == "ambiguous_day_month":
        row["issues"].append({"code": issue, "text_ar": "التاريخ يحتمل يوم/شهر — قرأناه: " + dates.words_ar(row["end_date"])})
    elif issue == "guessed_column":
        row["issues"].append({"code": issue, "text_ar": "ما فيه عمود «تاريخ الانتهاء» — خمّنا العمود، راجعه"})
    row["preview"] = {"end_words": dates.words_ar(row.get("end_date")),
                      "end_hijri": dates.to_hijri_str(row.get("end_date"))}


def _flag_duplicates(rows):
    """dup_permit_no on EVERY row sharing a normalised number. Both stay; both get tracked."""
    by = {}
    for r in rows:
        n = norm_no(r.get("permit_no"))
        if n:
            by.setdefault(n, []).append(r)
    for group in by.values():
        if len(group) < 2:
            continue
        for r in group:
            others = ", ".join(str(o.get("serial") or o["row_index"]) for o in group if o is not r)
            issue = {"code": "dup_permit_no", "text_ar": "رقم التصريح مكرر مع صف %s — واحد منهم غلط" % others}
            r["review_issues"].append(issue)
            r["issues"].append(issue)


def norm_no(v):
    return re.sub(r"[\s\-_/]", "", dates.clean_text(v)).lower()


# ---------------- onboarding (read-only) ----------------

def from_onboarding(reader, default_type=None):
    """Rows from «ضم الوحدات» projects that carry a licence. `reader` is a READ-ONLY callable
    from bot.py; nothing here ever writes to onb_*."""
    rows = []
    for i, p in enumerate(reader() or []):
        no, exp = _cell_text(p.get("license_no")), _cell_text(p.get("license_expiry"))
        if not (no or exp):
            continue
        d = dates.parse_date(exp)
        row = {"row_index": i + 1, "serial": None, "unit_text": _cell_text(p.get("unit_name")),
               "permit_no": no, "district": _cell_text(p.get("district")),
               "end_date": d["iso"], "end_date_raw": exp, "start_date": None, "start_date_raw": "",
               "listing_id": p.get("listing_id"), "review_issues": [], "issues": [],
               "extra": {}, "holder": "", "doc_name": "", "doc_url": "", "holder_id_last4": "",
               "_end_date_issue": d["issue"]}
        _finish(row, "onboarding", default_type, "", set())
        row["source_ref"] = "onboarding#%s" % (p.get("id") or i + 1)
        rows.append(row)
    _flag_duplicates(rows)
    return {"rows": rows, "header_row": 0, "source_rows": len(rows), "kind": "onboarding", "columns": []}


# ---------------- marking what already exists ----------------

def mark_existing(preview):
    """Annotate each preview row with `exists_id` when its permit number is already held
    by a LIVE permit (shown «موجود» — skipped unless the person ticks «حدّث الموجود»)."""
    live = {}
    for p in db.permits("active"):
        n = norm_no(p.get("permit_no"))
        if n:
            live.setdefault(n, p["id"])
    for r in preview["rows"]:
        r["exists_id"] = live.get(norm_no(r.get("permit_no")))
    return preview


# ---------------- commit ----------------

_STORE = ("permit_type", "permit_no", "scope", "unit_text", "issuer", "holder", "start_date",
          "end_date", "start_date_raw", "end_date_raw", "district", "street", "building_no",
          "unit_no", "ownership_kind", "holder_id_last4", "doc_name", "doc_url", "serial",
          "date_issue", "responsible_name", "renew_notes", "notes", "needs_data", "source_ref")


def commit(preview, actor, source="import", decisions=None, extra_fields=None):
    """Store a (server-side re-parsed) preview. `decisions` = {row_index: 'skip'|'update'}.

    Existence is decided against the DB as it was BEFORE this commit, so two rows of the
    same file that share a number are BOTH inserted (and both flagged) — never one
    swallowing the other. -> {"inserted", "updated", "skipped", "needs_data", "ids"}."""
    decisions = {int(k): v for k, v in (decisions or {}).items()}
    mark_existing(preview)
    out = {"inserted": 0, "updated": 0, "skipped": 0, "needs_data": 0, "ids": []}
    with db.transaction() as cx:
        for r in preview["rows"]:
            choice = decisions.get(int(r["row_index"]), "")
            data = {k: r.get(k) for k in _STORE}
            data["review_issues"] = r.get("review_issues") or []
            data["extra_json"] = r.get("extra_json") or {}
            data["source"] = source
            if r.get("listing_id"):
                data["listing_id"] = int(r["listing_id"])
                data["listing_link_kind"] = "auto"
            data.update(extra_fields or {})
            if choice == "skip":
                out["skipped"] += 1
                continue
            if r.get("exists_id"):
                if choice != "update":
                    out["skipped"] += 1
                    continue
                old = db.q1("SELECT * FROM permits_permits WHERE id=?", (r["exists_id"],))
                patch = {k: v for k, v in data.items() if v not in (None, "", [], {})
                         and k not in ("source", "review_issues", "extra_json")}
                db.update_permit(r["exists_id"], patch, actor, cx=cx)
                db.log_event("import_update", r["exists_id"], payload={
                    "source_ref": r.get("source_ref"), "old_end": (old or {}).get("end_date"),
                    "new_end": data.get("end_date")}, actor=actor, cx=cx)
                out["updated"] += 1
                out["ids"].append(r["exists_id"])
                continue
            pid = db.insert_permit(data, actor, cx=cx)
            db.log_event("imported", pid, payload={"source_ref": r.get("source_ref"), "source": source},
                         actor=actor, cx=cx)
            out["inserted"] += 1
            out["needs_data"] += 1 if data.get("needs_data") else 0
            out["ids"].append(pid)
    return out
