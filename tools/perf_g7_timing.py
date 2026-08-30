# -*- coding: utf-8 -*-
"""G7 — wall clock, measured not estimated.

Two measurements, both run identically on the base tree and the branch:

  WARM  p95 of 20 profile loads and 20 statement loads, no simulated latency.
        This is the gate: < 1.5 s and < 1.0 s.

  COLD  one profile load where every Hostaway call goes through the REAL
        _ha_throttle_acquire plus a fixed network cost. The production slowness is
        not compute, it is 11 calls / 10 s shared process-wide — so a cold number
        measured against an instant stub would be meaningless. Using the actual
        throttle keeps the comparison honest rather than inventing a latency model.

Usage: python3 tools/perf_g7_timing.py [--net 0.30]
"""
import os
import shutil
import sys
import time

NET_COST = 0.30
for i, a in enumerate(sys.argv):
    if a == "--net" and i + 1 < len(sys.argv):
        NET_COST = float(sys.argv[i + 1])

_STATE = "/tmp/ouja-g7-timing"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE
os.environ["RES_SPAN_ENABLED"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot                                        # noqa: E402
from finance import api as fapi, owners as OW     # noqa: E402

fapi.attach(bot)

LID = 701
OWNER = "مالك القياس"


def _rows():
    out, y, m = [], 2025, 1
    for i in range(30):
        mk = "%04d-%02d" % (y, m)
        for d, amt in ((5, 1000.0), (12, 1500.0), (20, 900.0)):
            out.append({"id": "r%d-%d" % (i, d), "listingMapId": LID, "status": "new",
                        "channelName": "Airbnb", "arrivalDate": "%s-%02d" % (mk, d),
                        "departureDate": "%s-28" % mk, "nights": 2,
                        "guestName": "G", "airbnbExpectedPayoutAmount": amt,
                        "totalPrice": amt + 200, "refundAmount": None})
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


ALL = _rows()
CALLS = [0]


def make_stub(throttled):
    def stub(path, params=None, _retry=0):
        CALLS[0] += 1
        if throttled:
            bot._ha_throttle_acquire()            # the REAL production throttle
            time.sleep(NET_COST)
        p = params or {}
        lo = p.get("arrivalStartDate") or "0000"
        hi = p.get("arrivalEndDate") or "9999"
        sel = [r for r in ALL if lo <= r["arrivalDate"][:10] <= hi]
        off, lim = int(p.get("offset") or 0), int(p.get("limit") or 200)
        return {"result": sel[off:off + lim]}
    return stub


def setup(throttled=False):
    OW._terms_cache["v"] = None
    OW._stmt_cache["v"] = None
    bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
    bot._save_json("owner_statements.json", {})
    bot._owner_registry.clear()
    bot._owner_registry[bot._owner_key("T1")] = {
        "apartment": "T1", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
        "cleaning": {"type": "ours", "amount": 0}}
    bot._owner_links.clear()
    bot._expenses.clear()
    bot.get_listings_map = lambda: {LID: "Ouja | T1"}
    bot.api_get = make_stub(throttled)
    clear()


def clear():
    bot._owner_portal_cache.clear()
    bot._owner_partial_cache.clear()
    bot._res_window_cache.clear()
    for d in (getattr(bot, "_res_span_cache", None),):
        if d is not None:
            d.clear()
    bot._res_window_degraded.clear()
    for c in (getattr(OW, "_stmt_payload_cache", None),
              getattr(OW, "_stmt_compare_cache", None)):
        if c is not None:
            c.clear()
    bot._ha_bucket_times.clear()
    bot._listings["map"] = {}
    bot._listings["ts"] = 0


def p95(xs):
    s = sorted(xs)
    return s[max(0, int(round(0.95 * len(s))) - 1)]


def warm_series(fn, n=20):
    fn()                                          # prime
    out = []
    for _ in range(n):
        t = time.time()
        fn()
        out.append(time.time() - t)
    return out


if __name__ == "__main__":
    mk = OW.api._month_key_or_prev(None)

    setup(throttled=False)
    prof = warm_series(lambda: OW.owner_profile(OWNER))
    stmt = warm_series(lambda: OW.statement_payload(OWNER, mk))
    print("WARM profile   p95 %.4fs  mean %.4fs  (budget 1.5s)"
          % (p95(prof), sum(prof) / len(prof)))
    print("WARM statement p95 %.4fs  mean %.4fs  (budget 1.0s)"
          % (p95(stmt), sum(stmt) / len(stmt)))

    setup(throttled=True)
    CALLS[0] = 0
    t = time.time()
    OW.owner_profile(OWNER)
    cold = time.time() - t
    print("COLD profile   %.2fs   hostaway calls: %d   (throttle real, net %.2fs/call)"
          % (cold, CALLS[0], NET_COST))
