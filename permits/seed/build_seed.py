# -*- coding: utf-8 -*-
"""
permits.seed.build_seed — Faisal's xlsx → permits_seed.normalized.json. Re-runnable.

    python3 -m permits.seed.build_seed            # from the repo root

Reads permits/seed/source/ouja_permits_official.xlsx (git-ignored: it holds owners'
national IDs), runs it through the SAME importer every future upload uses, stamps the
seed constants, adds the three reviewed «unit_mismatch» flags, and writes the JSON that
deploys. The JSON carries holder names, Drive links and ID LAST-4 only — never a full ID.

tests/test_permits_seed_real.py proves a fresh run equals the committed file.
"""

import datetime
import json
import os
import sys

if __package__ in (None, ""):                         # allow `python3 permits/seed/build_seed.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from permits import engine, importer                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "source", "ouja_permits_official.xlsx")
OUT = os.path.join(HERE, "permits_seed.normalized.json")

# Reviewed by hand (§2.4) — a hard-coded list, NOT a heuristic: names like «C118» (building 118,
# unit 3) would false-alarm under any general rule. Keyed by serial AND checked against the
# unit name, so a reordered spreadsheet cannot stamp the wrong row.
UNIT_MISMATCH = {
    1: ("101b", "اسم الوحدة 101b لكن رقم الوحدة بالتصريح 202"),
    43: ("202B", "اسم الوحدة 202B لكن الملف 201A ورقم الوحدة 201 والمبنى 7569"),
    19: ("101a", "اسم الوحدة 101a لكن رقم الوحدة بالتصريح 201"),
}

_KEEP = ("serial", "unit_text", "permit_no", "holder", "doc_name", "doc_url", "start_date",
         "start_date_raw", "end_date", "end_date_raw", "holder_id_last4", "district", "street",
         "building_no", "unit_no", "ownership_kind", "permit_type", "issuer", "scope", "source",
         "source_ref", "review_issues", "extra_json", "date_issue", "needs_data",
         "responsible_name", "renew_notes", "notes")


def build(path=SOURCE):
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    parsed = importer.parse(data, name, default_type=engine.SEED_TYPE, default_issuer=engine.SEED_ISSUER)
    rows = []
    for r in parsed["rows"]:
        r["permit_type"] = engine.SEED_TYPE
        r["issuer"] = engine.SEED_ISSUER
        r["scope"] = "unit"
        r["source"] = "seed"
        r["source_ref"] = "%s#%s" % (name, r.get("serial") or r["row_index"])
        mm = UNIT_MISMATCH.get(r.get("serial"))
        if mm and r.get("unit_text") == mm[0]:
            r["review_issues"].append({"code": "unit_mismatch", "text_ar": mm[1]})
        rows.append({k: r.get(k, "") for k in _KEEP})
    return {"source_file": name, "source_rows": len(rows), "header_row": parsed["header_row"],
            "built_at": datetime.datetime.utcnow().isoformat(timespec="seconds"), "rows": rows}


def main():
    out = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote %s — %d rows" % (OUT, out["source_rows"]))


if __name__ == "__main__":
    main()
