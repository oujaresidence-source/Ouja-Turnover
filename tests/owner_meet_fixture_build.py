# -*- coding: utf-8 -*-
"""Regenerate tests/fixtures/owner_meet/snapshot_full.json and snapshot_multi.json.

They are SYNTHETIC test data built through the REAL statement path (the same harness as
tests/test_owner_meet_money.py: only api_get is stubbed), so the render / chart / layout tests run
against exactly the shape production builds. Not shipped to any owner; not a sample in the product.

Run: python3 tests/owner_meet_fixture_build.py
"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_owner_meet_money as H  # noqa: E402  (sets STATE_DIR, wires bot + brain.db)

OUT = ROOT / "tests" / "fixtures" / "owner_meet"


def _reviews():
    """Ratings so chapter 2/5 have something real to compare (10-point scale, 0 = not a review)."""
    rv = {}
    scores = {H.L1: [10, 10, 9, 10, 8, 10, 10, 9], H.L2: [10, 9, 10]}
    for k, lid in enumerate(H.PEERS):
        scores[lid] = [10, 9, 9, 10, 8 + (k % 3)]
    n = 0
    for lid, ss in scores.items():
        for s in ss:
            n += 1
            rv["r%d" % n] = {"id": "r%d" % n, "listing_id": lid, "rating_raw": s, "rating": round(s / 2)}
    return rv


# Planted on purpose: identities that must NEVER reach an owner page. tests/test_owner_meet_privacy.py
# greps the rendered fixture for every one of them.
PLANTED = {"guest_full": "Fahad Alqahtani", "guest_2": "Noura Alharbi", "phone": "0551234567",
           "code": "HMXK29ABCD", "staff": ["khalid.ops", "Majed Ops", "Reem RR"]}


def _ops_records():
    T = "+03:00"
    dtk = {
        "c1": {"kind": "maint", "seq": 1, "lid": H.L1, "unit": "Ouja | M1", "urgency": "urgent", "category": "تكييف",
               "summary": "الضيف Fahad Alqahtani يقول المكيف ما يبرد، رقمه 0551234567", "opener": "khalid.ops",
               "assignee": "Majed Ops", "dash_id": "tk_1", "status": "closed",
               "created_at": "2026-08-03T10:00:00" + T, "closed_at": "2026-08-03T16:30:00" + T, "closed_by": "Majed Ops"},
        "c2": {"kind": "maint", "seq": 2, "lid": H.L1, "unit": "Ouja | M1", "urgency": "normal", "category": "سباكة",
               "summary": "من مكالمة تقييم: ضغط الدش ضعيف", "opener": "khalid.ops", "dash_id": "tk_2",
               "status": "open", "origin": "review_call", "origin_ref": "rv:900001",
               "created_at": "2026-09-20T18:00:00" + T},
        "c3": {"kind": "rr", "seq": 3, "code": PLANTED["code"], "type": "damage", "unit": "Ouja | M1",
               "guest": PLANTED["guest_full"], "narrative": "الضيف كسر الطاولة",
               "items_raw": "كنب متسخ 300" + chr(10) + "طاولة مكسورة 450 " + PLANTED["code"], "total_raw": "750",
               "status": "paid", "opener": "Reem RR", "created_at": "2026-08-05T12:00:00" + T,
               "departure": "2026-08-04",
               "closeout": {"payer": "owner", "claimed": 750, "received": 450, "less_reason": "Partial: wear and tear",
                            "note": "", "at": "2026-08-20T10:00:00" + T, "by": "Reem RR"}},
        "c4": {"kind": "rr", "seq": 4, "code": "HMQQ11ZZYY", "type": "missing", "lid": H.L1, "unit": "Ouja | M1",
               "items_raw": "مناشف 120", "total_raw": "120", "status": "submitted", "opener": "Reem RR",
               "created_at": "2026-09-28T09:00:00" + T, "departure": "2026-09-27"},
        "c5": {"kind": "proc", "seq": 5, "unit_ids": [H.L1], "units": ["Ouja | M1"], "items": "ستائر غرفة النوم",
               "amount_raw": "640", "status": "closed", "opener": "khalid.ops", "created_at": "2026-07-22T11:00:00" + T},
    }
    dash = [
        {"id": "tk_1", "lid": H.L1, "category": "maintenance", "status": "fixed", "cost": 350, "source": "manual",
         "title": "مكيف", "created_at": "2026-08-03T10:00:00" + T, "assignee": "Majed Ops"},
        {"id": "tk_2", "lid": H.L1, "category": "maintenance", "status": "open", "source": "review",
         "title": "دش", "created_at": "2026-09-20T18:00:00" + T},
        {"id": "tk_3", "lid": H.L1, "category": "maintenance", "status": "fixed", "cost": 120, "source": "escalation",
         "guest": PLANTED["guest_2"], "title": "تسريب مغسلة — بلاغ من Noura Alharbi",
         "created_at": "2026-07-15T09:00:00" + T, "log": [{"ts": "2026-07-16T09:00:00" + T, "who": "Majed Ops", "what": "fixed"}]},
    ]
    reviews = {
        "rv1": {"id": "rv1", "listing_id": H.L1, "rating_raw": 10, "guest_name": "Sara Almutairi", "date": "2026-08-12",
                "public_review": "شقة نظيفة والتواصل ممتاز، وKhalid ساعدنا بسرعة.", "private_review": "المخدة قاسية شوي",
                "reservation_id": "900001",
                "raw": {"reviewCategory": [{"category": "cleanliness", "rating": 10}, {"category": "communication", "rating": 10},
                                           {"category": "value", "rating": 8}]}},
        "rv2": {"id": "rv2", "listing_id": H.L1, "rating_raw": 8, "guest_name": "Omar", "date": "2026-09-02",
                "public_review": "الموقع ممتاز لكن الدش ضعيف.", "private_review": "",
                "raw": {"reviewCategory": [{"category": "cleanliness", "rating": 8}, {"category": "value", "rating": 8}]}},
        "rv0": {"id": "rv0", "listing_id": H.L1, "rating_raw": 0, "guest_name": "Zero", "date": "2026-09-03",
                "public_review": "لا يُحسب"},
    }
    return dtk, dash, reviews


class _Gen(H._Fixture):
    def runTest(self):
        bot = H.bot
        saved = (dict(bot._dtk.get("tickets") or {}), list(bot._tickets), dict(bot._price_log),
                 dict(bot._cleaning_feedback), dict(bot._users), bot._rr_ar_texts)
        dtk, dash, rv = _ops_records()
        bot._reviews.clear()
        bot._reviews.update(_reviews())
        bot._reviews.update(rv)
        bot._dtk.setdefault("tickets", {}).update(dtk)
        bot._tickets[:0] = dash
        bot._price_log["%d|2026-09-10" % H.L1] = [{"ts": "2026-09-01T10:00:00+03:00", "old": 600, "new": 560, "dry": False}]
        bot._price_log["%d|2026-09-11" % H.L1] = [{"ts": "2026-09-01T10:00:00+03:00", "old": 600, "new": 560, "dry": True}]
        bot._cleaning_feedback["tok1"] = {"lid": H.L1, "score": 5, "ts_done": "2026-08-10T12:00:00+03:00"}
        bot._users["u1"] = {"name": "Majed Ops"}
        bot._rr_ar_texts = lambda rec, co: {"ok": True, "story": "", "reason": "دفعت Airbnb جزءاً لأنها اعتبرت بعض الضرر استهلاكاً طبيعياً.", "note": ""}
        from owner_meet import abnb, airbnb_import
        tsv = (ROOT / "tests" / "fixtures" / "owner_meet" / "host_opportunity_2026-10-04.tsv").read_bytes()
        abnb.import_file(tsv, "host_opportunity_2026-10-04.tsv", "fixture")
        rows = {r["rank"]: r["airbnb_id"] for r in airbnb_import.parse(tsv, "x.tsv")["rows"]}
        abnb.confirm(rows[12], H.L1, "fixture")      # a 2-bedroom row in test group A
        abnb.confirm(rows[36], H.L2, "fixture")      # a 1-bedroom row
        try:
            _p, full = self._build("2025-10", "2026-09", lids=[H.L1])
            _p, multi = self._build("2026-07", "2026-09")
        finally:
            bot._reviews.clear()
            bot._dtk["tickets"] = saved[0]
            bot._tickets[:] = saved[1]
            bot._price_log.clear(); bot._price_log.update(saved[2])
            bot._cleaning_feedback.clear(); bot._cleaning_feedback.update(saved[3])
            bot._users.clear(); bot._users.update(saved[4])
            bot._rr_ar_texts = saved[5]
        for name, snap in (("snapshot_full.json", full), ("snapshot_multi.json", multi)):
            (OUT / name).write_text(json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            print("wrote", name)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    r = unittest.TextTestRunner(verbosity=0).run(_Gen())
    sys.exit(0 if r.wasSuccessful() else 1)
