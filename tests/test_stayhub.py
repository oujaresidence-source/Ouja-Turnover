# -*- coding: utf-8 -*-
"""StayHub channel-partner integration — offline tests against a fake StayHub.

The fake answers in the shapes of StayHub's Postman collections (Phase 1-3 / 4-8) and their
written answers of 5 Nov 2026. Locked here:
  * engine: phone normalisation, snapshot ONLY from the probe, plan(), eligibility, HMAC check
  * client: token cached + refreshed on 401, 429 backoff, {"data":…} unwrapped, secret never echoed
  * sync: bootstrap fills the catalog, cursor saved, CURSOR_EXPIRED ⇒ rebootstrap, suspension
  * push: unmapped / direct / started ⇒ nothing sent; happy path probe→hold→confirm with the
    Airbnb total + Airbnb code + Hostaway id; second tick sends nothing; price race ⇒ one
    re-probe; availability refusal ⇒ rejected + ONE Discord line; amount change ⇒ financial
    modify rev 2; date change ⇒ modify with snapshot; cancel ⇒ cancel rev+1; dry-run ⇒ no hold;
    lost ledger ⇒ adopt the existing StayHub booking instead of failing
  * probe: answers bookings / availability / rates from the cache
  * privacy: no guest name or phone in the ledger, the events or any Discord line

Run: python3 -m unittest tests.test_stayhub
"""
import datetime
import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                          # noqa: E402
from stayhub import client, db, engine, host, probe, push, recon, routes, sync  # noqa: E402

NOW = datetime.datetime(2026, 11, 10, 12, 0)
PID, RP = "prop_a1", "rp_1"
GUEST = "Ahmed Test"
PHONE = "0551234567"


class Resp:
    def __init__(self, status, body, headers=None):
        self.status_code, self._b, self.headers = status, body, headers or {}

    def json(self):
        if self._b is None:
            raise ValueError("no json")
        return self._b


class FakeStayHub:
    """Minimal StayHub: one property, nightly rate 500, rooms 1 unless booked/blocked."""

    def __init__(self):
        self.calls, self.tokens, self.blocked = [], 0, set()
        self.rate, self.version = 500, 7
        self.res, self.holds = {}, {}
        self.fail_next = []          # [(path_substring, status, code)]
        self.sync_pages = None
        self.expire_cursor = False

    # --- requests.Session API ---
    def post(self, url, data=None, timeout=None):
        self.tokens += 1
        if data.get("client_secret") != "s3cret":
            return Resp(401, {"error": "invalid_client"})
        return Resp(200, {"access_token": "tok%d" % self.tokens, "expires_in": 300, "token_type": "Bearer"})

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.split("/api/v2/connectivity", 1)[-1]
        self.calls.append((method, path, params, json))
        for i, (frag, st, code) in enumerate(self.fail_next):
            if frag in path:
                self.fail_next.pop(i)
                return Resp(st, {"success": False, "error": {"code": code, "detail": {"date": "2026-12-02"}}},
                            {"Retry-After": "0"})
        if headers.get("Authorization") != "Bearer tok%d" % self.tokens:
            return Resp(401, {"error": {"code": "AUTH_EXPIRED_TOKEN"}})
        return self._route(method, path, params or {}, json or {})

    def _taken(self, date, exclude=None):
        if date in self.blocked:
            return True
        for rid, r in self.res.items():
            if rid != exclude and r["status"] == "confirmed" and r["checkIn"] <= date < r["checkOut"]:
                return True
        return False

    def _ok(self, data):
        return Resp(200, {"success": True, "data": data}, {"X-Trace-Id": "tr_%d" % len(self.calls)})

    def _route(self, m, p, q, b):
        if p == "/sync":
            if self.expire_cursor and q.get("since") not in ("null", None):
                self.expire_cursor = False
                return Resp(400, {"error": {"code": "CURSOR_EXPIRED"}})
            if self.sync_pages:
                return self._ok(self.sync_pages.pop(0))
            return self._ok({"newAuthorizations": [], "deauthorizations": [], "propertyChanges": [],
                             "rateChanges": [], "availabilityChanges": [], "restrictionChanges": [],
                             "suspensions": [], "resumptions": [], "nextCursor": "cur_x", "hasMore": False})
        if p.startswith("/properties/") and p.endswith("/availability"):
            a = datetime.date.fromisoformat(q["from"])
            z = datetime.date.fromisoformat(q["to"])
            days = []
            while a <= z:
                d = a.isoformat()
                days.append({"date": d, "roomsAvailable": 0 if self._taken(d) else 1, "rate": self.rate})
                a += datetime.timedelta(days=1)
            return self._ok({"propertyId": PID, "ratePlanId": RP, "currency": "SAR",
                             "propertyVersion": self.version, "days": days})
        if p == "/reservations/hold":
            snap = b["partnerSnapshot"]
            if snap["propertyVersion"] != self.version:
                return Resp(409, {"error": {"code": "PROPERTY_VERSION_OUTDATED"}})
            for d in snap["days"]:
                if d["rate"] != self.rate:
                    return Resp(409, {"error": {"code": "SNAPSHOT_PRICE_MISMATCH"}})
                if self._taken(d["date"]) or d["roomsAvailable"] > 1:
                    return Resp(409, {"error": {"code": "SNAPSHOT_AVAILABILITY_MISMATCH"}})
            hid = "hold_%d" % (len(self.holds) + 1)
            self.holds[hid] = b
            return self._ok({"holdId": hid, "expiresAt": "2026-11-10T09:05:00Z",
                             "totalAmount": snap["totalAmount"], "currency": "SAR"})
        if p == "/reservations/confirm":
            for rid, r in self.res.items():
                if r["externalReservationId"] == b["externalReservationId"]:
                    if r["externalRevision"] == b["externalRevision"]:
                        return self._ok({"reservationId": rid, "status": "confirmed", "idempotent": True})
                    return Resp(409, {"error": {"code": "IDEMPOTENCY_CONFLICT"}})
            h = self.holds.pop(b["holdId"], None)
            if not h:
                return Resp(410, {"error": {"code": "HOLD_EXPIRED"}})
            rid = "res_%d" % (len(self.res) + 1)
            self.res[rid] = {"reservationId": rid, "propertyId": h["propertyId"], "checkIn": h["checkIn"],
                             "checkOut": h["checkOut"], "status": "confirmed",
                             "externalReservationId": b["externalReservationId"],
                             "externalRevision": b["externalRevision"], "financial": b["financial"],
                             "guest": b["guest"], "paymentReference": b["paymentReference"]}
            return self._ok({"reservationId": rid, "externalReservationId": b["externalReservationId"],
                             "status": "confirmed"})
        if p == "/reservations" and m == "GET":
            return self._ok({"reservations": list(self.res.values()), "pagination": {"page": 1, "pages": 1}})
        if p.startswith("/reservations/") and p.endswith("/modify"):
            rid = p.split("/")[2]
            r = self.res[rid]
            if b["externalRevision"] <= r["externalRevision"]:
                return Resp(409, {"error": {"code": "IDEMPOTENCY_CONFLICT"}})
            if "checkIn" in b:
                if "partnerSnapshot" not in b:
                    return Resp(400, {"error": {"code": "VALIDATION_ERROR"}})
                r["checkIn"], r["checkOut"] = b["checkIn"], b["checkOut"]
            if "financial" in b:
                r["financial"] = b["financial"]
            r["externalRevision"] = b["externalRevision"]
            return self._ok({"reservationId": rid, "status": "confirmed"})
        if p.startswith("/reservations/") and p.endswith("/cancel"):
            rid = p.split("/")[2]
            r = self.res[rid]
            if b["externalRevision"] <= r["externalRevision"]:
                return Resp(409, {"error": {"code": "IDEMPOTENCY_CONFLICT"}})
            r["status"], r["externalRevision"] = "cancelled", b["externalRevision"]
            return self._ok({"reservationId": rid, "status": "cancelled"})
        if p.startswith("/reservations/") and m == "GET":
            return self._ok(self.res[p.split("/")[2]])
        if p == "/reconciliation/report":
            return self._ok({"summary": {"reservationsChecked": len(b["reservations"]), "statusMismatches": 0,
                                         "availabilityMismatches": 0},
                             "details": {"missingOnPartner": [], "missingOnUs": []}})
        return Resp(404, {"error": {"code": "NOT_FOUND"}})

    def posts(self, frag):
        return [c for c in self.calls if c[0] == "POST" and frag in c[1]]


def ha_res(rid=101, lid=900, channel="Airbnb", status="new", arrive="2026-12-01", depart="2026-12-04",
           total=1834.5, code="HMABC123", phone=PHONE):
    return {"id": rid, "listingMapId": lid, "channelName": channel, "status": status,
            "arrivalDate": arrive, "departureDate": depart, "totalPrice": total, "currency": "SAR",
            "channelReservationId": code, "guestName": GUEST, "phone": phone, "numberOfGuests": 2,
            "reservationDate": "2026-11-09 10:00:00"}


def finance_channel(r):
    ch = (r.get("channelName") or "").lower()
    return "airbnb" if "airbnb" in ch else ("direct" if (not ch or "direct" in ch) else "other")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stayhub_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        for k in list(os.environ):
            if k.startswith("STAYHUB_"):
                os.environ.pop(k)
        os.environ.update({"STAYHUB_CLIENT_ID": "client_x", "STAYHUB_CLIENT_SECRET": "s3cret"})
        self.sh = FakeStayHub()
        client.set_session_for_tests(self.sh)
        client._sleep = lambda s: None
        self.msgs = []
        self.ha = {}
        host.wire({
            "now": lambda: NOW, "listings": lambda: {900: "Ouja | B14", 901: "Ouja | C2"},
            "notify": lambda t: self.msgs.append(t), "log_event": lambda c, t: None,
            "finance_channel": finance_channel, "confirmed_statuses": lambda: {"new", "modified"},
            "ha_reservations_window": lambda a, b, s, e: [r for r in self.ha.values() if s <= r["arrivalDate"] <= e],
            "ha_reservation": lambda rid: self.ha.get(int(rid)),
            "background": None,
        })
        db.upsert_property(PID, "B14", 7, [RP], "active")

    def map900(self):
        db.set_map(900, PID, RP, "test")

    def put(self, r):
        self.ha[r["id"]] = r
        return r


class EngineTests(unittest.TestCase):
    def test_phone(self):
        self.assertEqual(engine.normalize_phone("0551234567"), "966551234567")
        self.assertEqual(engine.normalize_phone("551234567"), "966551234567")
        self.assertEqual(engine.normalize_phone("+966 55 123 4567"), "966551234567")
        self.assertEqual(engine.normalize_phone("00966551234567"), "966551234567")
        self.assertEqual(engine.normalize_phone("+9660551234567"), "966551234567")
        self.assertEqual(engine.normalize_phone("+44 7700 900123"), "447700900123")
        self.assertEqual(engine.normalize_phone("٠٥٥١٢٣٤٥٦٧"), "966551234567")
        self.assertIsNone(engine.normalize_phone("12"))
        self.assertIsNone(engine.normalize_phone(""))

    def test_snapshot_only_from_probe(self):
        probe_ = {"propertyVersion": 4, "currency": "SAR", "days": [
            {"date": "2026-12-01", "rate": 450, "roomsAvailable": 1},
            {"date": "2026-12-02", "rate": 480, "roomsAvailable": 1},
            {"date": "2026-12-03", "rate": 999, "roomsAvailable": 1}]}
        snap, why = engine.snapshot_from_probe(probe_, "2026-12-01", "2026-12-03")
        self.assertEqual(why, "ok")
        self.assertEqual(snap["totalAmount"], 930)
        self.assertEqual([d["date"] for d in snap["days"]], ["2026-12-01", "2026-12-02"])
        probe_["days"][1]["roomsAvailable"] = 0
        snap, why = engine.snapshot_from_probe(probe_, "2026-12-01", "2026-12-03")
        self.assertIsNone(snap)
        self.assertTrue(why.startswith("night_full"))

    def test_plan(self):
        v = {"check_in": "2026-12-01", "check_out": "2026-12-04", "total": 100.0}
        self.assertEqual(engine.plan(v, None, False), "create")
        self.assertIsNone(engine.plan(v, None, True))
        row = {"status": "confirmed", "sh_reservation_id": "r", "pushed_check_in": "2026-12-01",
               "pushed_check_out": "2026-12-04", "pushed_total": 100.0}
        self.assertIsNone(engine.plan(v, row, False))
        self.assertEqual(engine.plan(dict(v, total=120.0), row, False), "modify_amount")
        self.assertEqual(engine.plan(dict(v, check_out="2026-12-05"), row, False), "modify_dates")
        self.assertEqual(engine.plan(v, row, True), "cancel")
        self.assertEqual(engine.plan(v, dict(row, status="pending"), True), "skip_cancel")

    def test_signature(self):
        body, key, ts = b'{"event":"x"}', "k3y", "1714132800"
        h = hmac.new(b"k3y", body, hashlib.sha256).hexdigest()
        self.assertTrue(engine.verify_signature([key], body, "sha256=" + h, ts, now_ts=1714132810))
        h2 = hmac.new(b"k3y", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        self.assertTrue(engine.verify_signature([key], body, h2, ts, now_ts=1714132810))
        self.assertFalse(engine.verify_signature([key], body, "sha256=" + h, ts, now_ts=1714132800 + 9999))
        self.assertFalse(engine.verify_signature([], body, "sha256=" + h))
        self.assertFalse(engine.verify_signature(["other"], body, "sha256=" + h))
        self.assertFalse(engine.verify_signature([key], body, "sha256=zz"))


class ClientTests(Base):
    def test_token_cached_and_refreshed_on_401(self):
        client.call("GET", "/sync", params={"since": "null"})
        client.call("GET", "/sync", params={"since": "null"})
        self.assertEqual(self.sh.tokens, 1)
        self.sh.tokens += 1                      # server rotates — our cached token is now stale
        data, _ = client.call("GET", "/sync", params={"since": "null"})
        self.assertEqual(data["nextCursor"], "cur_x")
        self.assertEqual(self.sh.tokens, 3)

    def test_rate_limited_backoff(self):
        self.sh.fail_next.append(("/sync", 429, "RATE_LIMITED"))
        data, _ = client.call("GET", "/sync")
        self.assertIn("nextCursor", data)

    def test_bad_secret(self):
        os.environ["STAYHUB_CLIENT_SECRET"] = "wrong"
        client.reset_token()
        with self.assertRaises(client.StayHubError) as cm:
            client.token()
        self.assertNotIn("wrong", str(cm.exception))

    def test_not_configured(self):
        os.environ.pop("STAYHUB_CLIENT_SECRET")
        self.assertEqual(sync.run_sync(), {"skipped": "not_configured"})
        self.assertEqual(push.tick(NOW), {"skipped": "not_configured"})


class SyncTests(Base):
    def test_bootstrap_and_cursor(self):
        self.sh.sync_pages = [
            {"newAuthorizations": [{"property": {"id": "prop_b", "title": "C2", "connectivityVersion": 3},
                                    "ratePlans": [{"id": "rp_b"}],
                                    "availability": [{"date": "2026-12-01", "roomsAvailable": 1, "rate": 300}]}],
             "nextCursor": "cur_1", "hasMore": True},
            {"availabilityChanges": [{"propertyId": "prop_b", "days": [{"date": "2026-12-01", "roomsAvailable": 0}]}],
             "suspensions": [{"propertyId": PID, "reason": "stale"}], "nextCursor": "cur_2", "hasMore": False}]
        out = sync.run_sync()
        self.assertEqual(out["pages"], 2)
        self.assertEqual(db.setting_get("cursor"), "cur_2")
        p = db.property_row("prop_b")
        self.assertEqual((p["title"], p["version"]), ("C2", 3))
        d = db.days("prop_b", "2026-12-01", "2026-12-01")[0]
        self.assertEqual((d["rooms"], d["rate"]), (0, 300))
        self.assertEqual(db.property_row(PID)["status"], "suspended")
        self.assertTrue(any("أوقف" in m for m in self.msgs))

    def test_cursor_expired_rebootstraps(self):
        db.setting_set("cursor", "cur_old")
        self.sh.expire_cursor = True
        out = sync.run_sync()
        self.assertNotIn("error", out)
        self.assertEqual(db.setting_get("cursor"), "cur_x")
        sinces = [c[2]["since"] for c in self.sh.calls if c[1] == "/sync"]
        self.assertEqual(sinces, ["cur_old", "null"])


class PushTests(Base):
    def test_nothing_without_mapping(self):
        self.put(ha_res())
        self.assertEqual(push.tick(NOW), {"skipped": "no_units_mapped"})
        self.assertEqual(self.sh.calls, [])

    def test_direct_and_started_never_pushed(self):
        self.map900()
        self.put(ha_res(rid=1, channel="Direct"))
        self.put(ha_res(rid=2, arrive="2026-11-09", depart="2026-11-12"))
        push.tick(NOW)
        self.assertEqual(self.sh.posts("/reservations/hold"), [])
        self.assertIsNone(db.booking(1))

    def test_happy_path_and_idempotent_tick(self):
        self.map900()
        self.put(ha_res())
        out = push.tick(NOW)
        self.assertEqual(out["actions"], {"create": 1})
        hold = self.sh.posts("/reservations/hold")[0][3]
        self.assertEqual(hold["partnerSnapshot"]["totalAmount"], 1500)          # StayHub's rate, not Airbnb's
        self.assertEqual(hold["partnerSnapshot"]["propertyVersion"], 7)
        self.assertEqual(hold["occupancy"], {"adults": 2})
        conf = self.sh.posts("/reservations/confirm")[0][3]
        self.assertEqual(conf["financial"], {"total": 1834.5, "currency": "SAR"})  # the Airbnb amount
        self.assertEqual(conf["externalReservationId"], "HMABC123")
        self.assertEqual(conf["paymentReference"], "101")
        self.assertEqual(conf["externalRevision"], 1)
        self.assertEqual(conf["guest"]["phone"], "966551234567")
        row = db.booking(101)
        self.assertEqual((row["status"], row["sh_reservation_id"], row["revision"]), ("confirmed", "res_1", 1))
        n = len(self.sh.calls)
        push.tick(NOW)
        self.assertEqual(len(self.sh.calls), n)                               # nothing re-sent

    def test_price_race_reprobes_once(self):
        self.map900()
        self.put(ha_res())
        self.sh.fail_next.append(("/reservations/hold", 409, "SNAPSHOT_PRICE_MISMATCH"))
        push.tick(NOW)
        self.assertEqual(len(self.sh.posts("/reservations/hold")), 2)
        self.assertEqual(db.booking(101)["status"], "confirmed")

    def test_refused_dates_rejected_and_reported_once(self):
        self.map900()
        self.put(ha_res())
        self.sh.blocked.add("2026-12-02")
        push.tick(NOW)
        row = db.booking(101)
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["last_code"], "NO_AVAILABILITY")
        self.assertEqual(self.sh.posts("/reservations/hold"), [])              # never held a full night
        self.assertEqual(len([m for m in self.msgs if "رفض" in m]), 1)
        push.tick(NOW)                                                           # not due yet
        self.assertEqual(len([m for m in self.msgs if "رفض" in m]), 1)
        self.sh.blocked.clear()
        later = NOW + datetime.timedelta(hours=7)
        push.tick(later)
        self.assertEqual(db.booking(101)["status"], "confirmed")

    def test_amount_then_dates_then_cancel(self):
        self.map900()
        r = self.put(ha_res())
        push.tick(NOW)
        r["totalPrice"] = 1900
        push.tick(NOW)
        mod = self.sh.posts("/modify")[-1][3]
        self.assertEqual(mod, {"externalRevision": 2, "financial": {"total": 1900, "currency": "SAR"}})
        r["departureDate"] = "2026-12-05"
        push.tick(NOW)
        mod = self.sh.posts("/modify")[-1][3]
        self.assertEqual(mod["externalRevision"], 3)
        self.assertEqual(mod["checkOut"], "2026-12-05")
        self.assertIn("partnerSnapshot", mod)
        self.assertEqual(self.sh.res["res_1"]["checkOut"], "2026-12-05")
        r["status"] = "cancelled"
        push.tick(NOW)
        canc = self.sh.posts("/cancel")[-1][3]
        self.assertEqual(canc["externalRevision"], 4)
        self.assertEqual(db.booking(101)["status"], "cancelled")
        self.assertEqual(self.sh.res["res_1"]["status"], "cancelled")

    def test_dryrun_sends_no_hold(self):
        os.environ["STAYHUB_DRYRUN"] = "1"
        self.map900()
        self.put(ha_res())
        push.tick(NOW)
        self.assertEqual(self.sh.posts("/reservations/"), [])
        self.assertEqual(db.booking(101)["dryrun"], 1)

    def test_lost_ledger_adopts_existing(self):
        self.map900()
        self.put(ha_res())
        push.tick(NOW)
        db.x("DELETE FROM stayhub_bookings")                                    # volume wiped
        push.tick(NOW)                                                           # nights look full: it is OUR booking
        row = db.booking(101)
        self.assertEqual((row["status"], row["sh_reservation_id"], row["revision"]), ("confirmed", "res_1", 1))
        self.assertEqual(len(self.sh.posts("/reservations/confirm")), 1)       # never booked twice
        self.assertEqual([m for m in self.msgs if "رفض" in m], [])

    def test_conflict_on_confirm_adopts(self):
        self.map900()
        self.put(ha_res())
        push.tick(NOW)
        # simulate a lost ledger where the nights look free again (e.g. StayHub calendar shows 1 room)
        db.x("DELETE FROM stayhub_bookings")
        self.sh.res["res_1"]["status"] = "confirmed"
        saved = self.sh._taken
        self.sh._taken = lambda d, exclude=None: False
        push.tick(NOW)
        self.sh._taken = saved
        row = db.booking(101)
        self.assertEqual((row["status"], row["sh_reservation_id"]), ("confirmed", "res_1"))

    def test_hostaway_cancel_before_push_is_skipped(self):
        self.map900()
        r = self.put(ha_res())
        self.sh.blocked.add("2026-12-02")
        push.tick(NOW)
        r["status"] = "cancelled"
        push.tick(NOW)
        self.assertEqual(db.booking(101)["status"], "skipped")

    def test_privacy(self):
        self.map900()
        self.put(ha_res())
        self.sh.blocked.add("2026-12-02")
        push.tick(NOW)
        self.sh.blocked.clear()
        push.tick(NOW + datetime.timedelta(hours=7))
        dump = json.dumps(db.q("SELECT * FROM stayhub_bookings") + db.events(limit=500), ensure_ascii=False)
        for secret in (GUEST, PHONE, "966551234567"):
            self.assertNotIn(secret, dump)
            for m in self.msgs:
                self.assertNotIn(secret, m)


class ProbeAndReconTests(Base):
    def test_probe_answer(self):
        self.map900()
        self.put(ha_res())
        push.tick(NOW)
        db.put_days(PID, RP, [{"date": "2026-12-01", "rooms": 0, "rate": 500}])
        ans = probe.answer({"probeId": "prb_1", "propertyId": PID, "scope": "all",
                            "window": {"from": "2026-11-30", "to": "2026-12-10"}}, "2026-11-10T12:00:00", NOW.date())
        self.assertEqual(ans["probeId"], "prb_1")
        self.assertEqual(ans["bookings"][0]["externalReservationId"], "HMABC123")
        self.assertEqual(ans["availability"]["days"], [{"date": "2026-12-01", "roomsAvailable": 0}])
        self.assertEqual(ans["rates"]["days"][0]["rate"], 500)
        self.assertEqual(ans["properties"]["version"], 7)
        only = probe.answer({"propertyId": PID, "scope": "bookings"}, "2026-11-10T12:00:00", NOW.date())
        self.assertNotIn("availability", only)

    def test_recon_once_a_day(self):
        self.map900()
        self.put(ha_res())
        push.tick(NOW)
        s = recon.run(NOW.date())
        self.assertEqual(s["confirmed"], 1)
        body = self.sh.posts("/reconciliation/report")[0][3]
        self.assertEqual(body["reservations"][0]["externalReservationId"], "HMABC123")
        self.assertEqual(recon.run(NOW.date()), {"skipped": "already_today"})
        self.assertTrue(any("مطابقة ستاي هب" in m for m in self.msgs))

    def test_status_payload_suggests_by_name(self):
        db.upsert_property("prop_c2", "Ouja | C2", 1, ["rp_c"], "active")
        st = routes.status_payload()
        c2 = [p for p in st["catalog"] if p["property_id"] == "prop_c2"][0]
        self.assertEqual(c2["suggest"][0]["listing_id"], 901)
        self.assertTrue(st["configured"])


class StructureTests(unittest.TestCase):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _pkg(self):
        d = os.path.join(self.ROOT, "stayhub")
        out = {}
        for fn in os.listdir(d):
            if fn.endswith(".py"):
                with open(os.path.join(d, fn), encoding="utf-8") as fh:
                    out[fn] = fh.read()
        return out

    def test_package_never_imports_bot_or_discord(self):
        for fn, src in self._pkg().items():
            self.assertNotRegex(src, r"(?m)^\s*(import|from)\s+(bot|discord)\b", fn)
            if fn != "client.py":
                self.assertNotRegex(src, r"(?m)^\s*import\s+requests\b", "%s: only client.py touches the network" % fn)

    def test_no_credentials_in_the_repo(self):
        leaked = "d7ac59dc" + "10e33a10"          # the sandbox secret's prefix, split so this file never matches
        for root, _dirs, files in os.walk(self.ROOT):
            if ".git" in root:
                continue
            for fn in files:
                if fn.endswith((".py", ".md", ".json", ".toml", ".txt")):
                    with open(os.path.join(root, fn), encoding="utf-8", errors="ignore") as fh:
                        self.assertNotIn(leaked, fh.read(), fn)

    def test_bot_references_resolve(self):
        import re
        import stayhub
        with open(os.path.join(self.ROOT, "bot.py"), encoding="utf-8") as fh:
            src = fh.read()
        for name in sorted(set(re.findall(r"_stayhub\.([a-z_]+)", src))):
            self.assertTrue(hasattr(stayhub, name), "bot.py uses _stayhub.%s which does not exist" % name)
        for loop in ("stayhub_sync_loop", "stayhub_push_loop", "stayhub_recon_loop"):
            self.assertIn('(%s, "%s")' % (loop, loop), src)          # loop guard
            self.assertIn("_pending.append(%s)" % loop, src)          # staggered start
        self.assertIn('_bg_task(_stayhub_on_hook(rid), "hook:stayhub")', src)
        self.assertIn("_stayhub.register_routes(app)", src)


class RouteTests(Base):
    def _app(self):
        from aiohttp import web
        host.wire({"json_response": lambda d, status=200: web.json_response(d, status=status),
                   "dash_auth": lambda r: r.headers.get("X-T") == "ok",
                   "req_role": lambda r: "admin", "req_actor": lambda r: "Faisal", "run": None})
        app = web.Application()
        routes.register_routes(app)
        return app

    def _run(self, coro_fn):
        import asyncio
        from aiohttp.test_utils import TestClient, TestServer

        async def go():
            async with TestClient(TestServer(self._app())) as c:
                return await coro_fn(c)
        return asyncio.run(go())

    def _sig(self, body, key="whsec"):
        ts = str(int(__import__("time").time()))
        return ts, "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()

    def test_webhook_signature_gate(self):
        os.environ["STAYHUB_WEBHOOK_SECRET"] = "whsec"
        body = json.dumps({"event": "availability.changed", "payload": {"propertyId": PID}}).encode()
        ts, sig = self._sig(body)

        async def go(c):
            bad = await c.post("/stayhub/webhook", data=body, headers={"X-StayHub-Signature": "sha256=" + "0" * 64,
                                                                       "X-StayHub-Timestamp": ts})
            none = await c.post("/stayhub/webhook", data=body)
            good = await c.post("/stayhub/webhook", data=body, headers={"X-StayHub-Signature": sig,
                                                                        "X-StayHub-Timestamp": ts,
                                                                        "X-StayHub-Event": "availability.changed"})
            return bad.status, none.status, good.status
        self.assertEqual(self._run(go), (401, 401, 200))
        self.assertTrue(any(e["kind"] == "webhook" for e in db.events(limit=10)))

    def test_sync_probe_answers_signed(self):
        os.environ["STAYHUB_WEBHOOK_SECRET"] = "whsec"
        body = json.dumps({"probeId": "prb_9", "propertyId": PID, "scope": "properties"}).encode()
        ts, sig = self._sig(body)

        async def go(c):
            r = await c.post("/stayhub/sync-probe", data=body, headers={"X-StayHub-Probe-Signature": sig,
                                                                         "X-StayHub-Probe-Timestamp": ts})
            return r.status, await r.json()
        st, js = self._run(go)
        self.assertEqual(st, 200)
        self.assertEqual((js["probeId"], js["properties"]["version"]), ("prb_9", 7))

    def test_dashboard_api_needs_login_and_maps(self):
        async def go(c):
            anon = await c.get("/api/stayhub/status")
            m = await c.post("/api/stayhub/map", json={"listing_id": 900, "property_id": PID}, headers={"X-T": "ok"})
            bad = await c.post("/api/stayhub/map", json={"listing_id": 901, "property_id": "nope"}, headers={"X-T": "ok"})
            st = await c.get("/api/stayhub/status", headers={"X-T": "ok"})
            return anon.status, m.status, bad.status, await st.json()
        anon, m, bad, js = self._run(go)
        self.assertEqual((anon, m, bad), (401, 200, 400))
        self.assertEqual(db.map_for_listing(900)["rate_plan_id"], RP)
        self.assertEqual(js["mapped"], 1)


if __name__ == "__main__":
    unittest.main()
