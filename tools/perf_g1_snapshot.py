# -*- coding: utf-8 -*-
"""G1 — the veto gate. Dump a full owner-month statement as canonical JSON.

Run this on the BASE tree and on the branch and diff the two outputs. If a single
figure moves, the branch is wrong no matter how fast it got: this is a money
surface, and a fast wrong number is worse than a slow right one.

The fixture is synthetic and fully deterministic — a real Hostaway pull would
differ between the two runs for reasons that have nothing to do with the code.
Only `computed_at`-style wall-clock stamps are stripped, and they are listed in
VOLATILE so the exclusion is visible rather than quietly convenient.

Usage: python3 tools/perf_g1_snapshot.py > snapshot.json
"""
import json
import os
import shutil
import sys

_STATE = "/tmp/ouja-g1-snapshot"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE
os.environ.pop("HOSTAWAY_API_KEY", None)          # keep the span layer off on both trees
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot                                        # noqa: E402
from finance import api as fapi, owners as OW     # noqa: E402

fapi.attach(bot)

LID_A, LID_B = 501, 502
OWNER = "مالك الاختبار"
MK = "2026-06"
VOLATILE = ("computed_at", "generated_at", "built_at", "at", "stale",
            "refreshing", "stale_age_s")


def _resv(rid, lid, payout, arrival, nights, channel, total=None):
    return {"id": rid, "listingMapId": lid, "status": "new", "channelName": channel,
            "arrivalDate": arrival, "departureDate": arrival, "nights": nights,
            "guestName": "ضيف " + str(rid),
            "airbnbExpectedPayoutAmount": payout,
            "totalPrice": total if total is not None else (payout or 0) + 300,
            "refundAmount": None}


ROWS = [
    _resv("a1", LID_A, 3200.0, "2026-06-02", 3, "Airbnb"),
    _resv("a2", LID_A, 1850.5, "2026-06-11", 2, "Airbnb"),
    _resv("a3", LID_A, None, "2026-06-19", 4, "Airbnb"),        # missing payout
    _resv("b1", LID_B, 2400.0, "2026-06-04", 2, "Direct", total=2400.0),
    _resv("b2", LID_B, 990.25, "2026-06-21", 1, "Booking.com"),
    _resv("c1", LID_A, 5000.0, "2026-05-28", 6, "Airbnb"),      # spans into June
]


def build():
    OW._terms_cache["v"] = None
    OW._stmt_cache["v"] = None
    bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
    bot._save_json("owner_statements.json", {})
    bot._owner_registry.clear()
    bot._owner_registry[bot._owner_key("G1A")] = {
        "apartment": "G1A", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID_A,
        "cleaning": {"type": "ours", "amount": 150}}
    bot._owner_registry[bot._owner_key("G1B")] = {
        "apartment": "G1B", "owner": OWNER, "mgmt_pct": 15.0, "lid": LID_B,
        "cleaning": {"type": "owner", "amount": 200}}
    bot._owner_links.clear()
    bot._expenses.clear()
    bot._expenses["E1"] = {
        "id": "E1", "apartment": "G1A", "listing_id": LID_A, "amount": 450.75,
        "expense_date": "2026-06-08", "hostaway_verified": True,
        "hostaway_expense_id": "H1", "category": "صيانة", "note": "مكيف"}
    bot._expenses["E2"] = {
        "id": "E2", "apartment": "G1B", "listing_id": LID_B, "amount": 120.0,
        "expense_date": "2026-06-14", "hostaway_verified": True,
        "hostaway_expense_id": "H2", "category": "نظافة", "note": "مستلزمات"}
    bot.fetch_reservations_window = lambda s, e, pad_days=45: list(ROWS)
    bot.get_listings_map = lambda: {LID_A: "Ouja | G1A", LID_B: "Ouja | G1B"}


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in sorted(o.items()) if k not in VOLATILE}
    if isinstance(o, list):
        return [strip(x) for x in o]
    return o


if __name__ == "__main__":
    build()
    stmt = OW.compute_owner_statement(OWNER, MK)
    if stmt is None:
        print("G1-ERROR: no statement computed")
        sys.exit(1)
    print(json.dumps(strip(stmt), ensure_ascii=False, indent=1, sort_keys=True))
