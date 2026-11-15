# -*- coding: utf-8 -*-
"""
«الأهداف ودفتر العملاء» end-to-end on a real (temporary) brain.db. No network, no Discord.

Locked here — each one is a rule that costs Ouja money or a guest's trust if it breaks:
    * the seed import matches a listing by exact name only; an unknown name is reported, never guessed
    * a guest in the hidden group reaches no call list and cannot be contacted
    * no consent, no call; «لا تتصل» is permanent and immediate
    * a contact is logged by the system: server clock, guest from the list, one per 45 days,
      first logger wins
    * commission counts completed stays only, with the unit's real fee; no fee on record -> 0
    * the month's total never exceeds the cap; no evidence of uplift -> nothing is paid
    * like with like: guests who would have come anyway add no uplift
    * a month is approved only after it closes and every counted guest has left; an approval
      is one row and nothing else
    * the scoreboard: baseline, tiers, the +2-point cap, units frozen at approval

Run: python3 -m unittest tests.test_targets_flow
"""

import datetime
import inspect
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                         # noqa: E402
from targets import book, db, engine, history, money, score        # noqa: E402
from targets.host import HOST                                       # noqa: E402

NORA, AHOOD = "نورة", "عهود"
ENV = ("TG_ENABLED", "TG_POOL_CHANNELS")


def D(s):
    return datetime.date.fromisoformat(s)


class Case(unittest.TestCase):
    """Three live units (A1, A2 -> نورة; B1 -> عهود), 60 past direct guests of A1."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tgtest_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        book._compound_memo.clear()
        self._env = {k: os.environ.get(k) for k in ENV}
        os.environ.update({"TG_ENABLED": "1", "TG_POOL_CHANNELS": "direct,consented"})
        self.clock = datetime.datetime(2026, 11, 15, 10, 0)
        self.fee = {"101": 0.20, "102": 0.20, "201": 0.25}
        self.own = [{"listing_id": 101, "name": "A1", "employee": NORA},
                    {"listing_id": 102, "name": "A2", "employee": NORA},
                    {"listing_id": 201, "name": "B1", "employee": AHOOD}]
        HOST.now = lambda: self.clock
        HOST.state_dir = self.tmp
        HOST.listings = lambda: {101: "A1", 102: "A2", 201: "B1"}
        HOST.ownership = lambda: list(self.own)
        HOST.unit_meta = lambda lid: {"compound": "ألف" if str(lid).startswith("1") else "باء"}
        HOST.floor = lambda lid: 0
        HOST.fee_pct = lambda lid, name, day: self.fee.get(str(lid))
        HOST.ops_multiplier = lambda emp, mk: 1.0
        HOST.vip_keys = lambda: set()
        HOST.wa_url = lambda phone, text: "https://wa.me/test?p=" + engine.phone_key(phone)
        HOST.fetch_window = lambda s, e: []
        HOST.calendar_days = None
        db.set_setting("holdout_secret", "test-secret")
        self.n = 0
        day = D("2026-01-05")
        for i in range(60):                      # one-night direct stays in A1, long lapsed
            a = day + datetime.timedelta(days=3 * i)
            self.res("101", self.phone(i), "ضيف%d فلان" % i, a.isoformat(),
                     (a + datetime.timedelta(days=1)).isoformat())

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # helpers ---------------------------------------------------------------
    def phone(self, i):
        return "05%08d" % (11000000 + i)

    def res(self, unit, phone, name, arrival, departure, channel="direct", status="new",
            total=1000.0, created=None):
        self.n += 1
        row = {"res_id": "R%d" % self.n, "unit": unit, "listing_name": "U" + unit,
               "phone_key": engine.phone_key(phone), "phone": phone, "guest_name": name,
               "channel": channel, "status": status, "arrival": arrival, "departure": departure,
               "created": created or arrival, "total": total, "source": "seed", "updated_at": "x"}
        db.upsert_res([row])
        return row["res_id"]

    def today(self):
        return self.clock.date()

    def full_list(self, emp=NORA):
        return book.call_list(emp, self.today(), limit=0)["items"]

    def hidden_keys(self):
        q = score.quarter_of(self.today())
        return {k for k in book.guests() if book.is_holdout(k, q)}


# ============================================================ seed import

SEED = """Guest name,Check-in date,Check-out date,Channel,Total price,Status,Reservation date,Listing,Phone,Hostaway reservation ID
Ali One,2026-03-01,2026-03-04,airbnbOfficial,900,new,2026-02-20,A1,+966501112233,9001
Sara Two,2026-03-10,2026-03-12,direct,700,modified,2026-03-01, a1 ,0502223344,9002
Old Guest,2025-05-01,2025-05-03,airbnbOfficial,500,new,2025-04-20,Gone Villa,0503334455,9003
Asked Only,2026-04-01,2026-04-02,airbnbOfficial,300,inquiry,2026-03-30,A1,0504445566,9004
CLOSED,2026-06-01,2026-06-04,customIcal,0,new,2026-05-30,A2,,9005
Owner,2026-07-01,2026-07-03,direct,0,ownerStay,2026-06-25,A2,,9006
"""


class SeedImport(Case):
    def test_exact_name_only_and_unknown_names_are_reported(self):
        rep = history.import_seed_text(SEED, "owner")
        self.assertEqual(rep["rows"], 3)                       # the inquiry and both blocks are not bookings
        self.assertEqual(rep["unmapped"], ["Gone Villa"])
        got = {r["res_id"]: r for r in db.res_by_ids(["9001", "9002", "9003"])}
        self.assertEqual(got["9001"]["unit"], "101")
        self.assertEqual(got["9002"]["unit"], "101")            # ' a1 ' is the same name
        self.assertEqual(got["9003"]["unit"], "n:gone villa")   # history only — not guessed onto a unit
        self.assertEqual(got["9002"]["channel"], "direct")
        self.assertEqual(got["9001"]["phone_key"], "501112233")
        self.assertEqual(history.unmapped(), [{"name": "gone villa", "shown": "Gone Villa"}])

    def test_blocks_become_blocked_nights_not_bookings(self):
        history.import_seed_text(SEED, "owner")
        self.assertEqual(db.blocked_dates("102", "2026-06-01", "2026-08-01"),
                         {"2026-06-01", "2026-06-02", "2026-06-03", "2026-07-01", "2026-07-02"})
        self.assertEqual(db.res_by_ids(["9005", "9006"]), [])

    def test_owner_decides_an_unknown_name(self):
        history.import_seed_text(SEED, "owner")
        ok, err = history.map_name("Gone Villa", "999", "owner")
        self.assertFalse(ok)                                    # not a real listing id
        ok, _ = history.map_name("Gone Villa", "201", "owner")
        self.assertTrue(ok)
        self.assertEqual(db.res_by_ids(["9003"])[0]["unit"], "201")
        self.assertEqual(history.unmapped(), [])

    def test_a_newer_api_row_is_not_overwritten_by_the_export(self):
        db.upsert_res([{"res_id": "9001", "unit": "101", "listing_name": "A1", "phone_key": "501112233",
                        "phone": "+966501112233", "guest_name": "Ali One", "channel": "airbnb",
                        "status": "cancelled", "arrival": "2026-03-01", "departure": "2026-03-04",
                        "created": "2026-02-20", "total": 900, "source": "api", "updated_at": "x"}])
        history.import_seed_text(SEED, "owner")
        self.assertEqual(db.res_by_ids(["9001"])[0]["status"], "cancelled")

    def test_nightly_sync_uses_the_window_fetch_month_by_month(self):
        asked = []

        def fake(start, end):
            asked.append((start.isoformat(), end.isoformat()))
            return [{"id": 777, "listingMapId": 102, "guestName": "New Guest", "phone": "0509990000",
                     "channelName": "direct", "status": "new", "arrivalDate": "2026-11-20",
                     "departureDate": "2026-11-22", "totalPrice": 800, "reservationDate": "2026-11-14 09:00:00"}]
        HOST.fetch_window = fake
        rep = history.nightly(self.today())
        self.assertEqual([a[0] for a in asked], ["2026-10-01", "2026-11-01", "2026-12-01", "2027-01-01"])
        self.assertEqual(db.res_by_ids(["777"])[0]["unit"], "102")
        self.assertEqual(set(rep["months"]), {"2026-10", "2026-11", "2026-12", "2027-01"})


# ============================================================ the hidden group

class HoldoutIsInvisible(Case):
    def test_the_split_is_real_and_stable(self):
        hidden = self.hidden_keys()
        self.assertTrue(3 <= len(hidden) <= 25, len(hidden))    # ~20% of 60
        self.assertEqual(hidden, self.hidden_keys())            # same answer every time this quarter

    def test_no_hidden_guest_in_any_employees_list(self):
        hidden = self.hidden_keys()
        for emp in (NORA, AHOOD):
            keys = {it["_key"] for it in self.full_list(emp)}
            self.assertFalse(keys & hidden)
        self.assertTrue(self.full_list(NORA))                    # and the list is not simply empty

    def test_a_hidden_guests_token_cannot_be_contacted(self):
        for key in self.hidden_keys():
            ok, err, out = book.log_contact(NORA, book.token(key))
            self.assertFalse(ok)
            self.assertIsNone(out)
        self.assertEqual(db.contacts(), [])

    def test_the_secret_decides_the_split_not_the_quarter_name_alone(self):
        a = self.hidden_keys()
        db.set_setting("holdout_secret", "another-secret")
        self.assertNotEqual(a, self.hidden_keys())


# ============================================================ consent / do-not-contact

class ConsentGatesThePool(Case):
    def test_airbnb_guest_without_consent_is_not_callable(self):
        self.res("101", "0507770001", "Air Guest", "2026-06-01", "2026-06-03", channel="airbnb")
        key = engine.phone_key("0507770001")
        self.assertNotIn(key, {g["key"] for g, _ in book.pool(self.today())})
        self.assertTrue(book.record_consent("+966 50 777 0001", "a1"))
        pool = {g["key"] for g, _ in book.pool(self.today())}
        self.assertEqual(key in pool, not book.is_holdout(key, "2026-Q4"))
        self.assertIn(key, db.consents())

    def test_a_strangers_number_is_ignored(self):
        self.assertFalse(book.record_consent("0599999999", "a1"))
        self.assertFalse(book.record_consent("123", "a1"))
        self.assertEqual(db.consents(), set())

    def test_do_not_contact_is_permanent_and_immediate(self):
        it = self.full_list()[0]
        ok, _, out = book.log_contact(NORA, it["g"])
        self.assertTrue(ok)
        ok, _ = book.set_outcome(NORA, out["contact_id"], "dnc")
        self.assertTrue(ok)
        self.assertIn(it["_key"], db.dnc())
        self.clock += datetime.timedelta(days=400)               # long after any cooldown
        for emp in (NORA, AHOOD):
            self.assertNotIn(it["_key"], {x["_key"] for x in self.full_list(emp)})
        src = inspect.getsource(db)
        self.assertNotIn("DELETE FROM tg_dnc", src)
        self.assertNotIn("UPDATE tg_dnc", src)

    def test_recent_guest_and_guest_with_a_booking_are_left_alone(self):
        self.res("101", "0507770002", "Recent", "2026-11-01", "2026-11-03")           # 12 days ago
        self.res("101", "0507770003", "Coming", "2026-05-01", "2026-05-03")
        self.res("102", "0507770003", "Coming", "2026-12-01", "2026-12-03", created="2026-11-01")
        pool = {g["key"] for g, _ in book.pool(self.today())}
        self.assertNotIn(engine.phone_key("0507770002"), pool)
        self.assertNotIn(engine.phone_key("0507770003"), pool)


# ============================================================ the logged contact

class ContactIsLoggedNotTyped(Case):
    def test_the_caller_supplies_no_date_and_no_phone(self):
        self.assertEqual(list(inspect.signature(book.log_contact).parameters), ["employee", "guest_token"])

    def test_one_insert_statement_in_the_whole_package(self):
        root = os.path.dirname(inspect.getsourcefile(db))
        hits = []
        for name in sorted(os.listdir(root)):
            if name.endswith(".py"):
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    if "INSERT INTO tg_contacts" in f.read():
                        hits.append(name)
        self.assertEqual(hits, ["db.py"])
        self.assertEqual(inspect.getsource(db).count("INSERT INTO tg_contacts"), 1)
        self.assertNotIn("UPDATE tg_contacts SET at", inspect.getsource(db))

    def test_press_stamps_the_server_clock_and_returns_the_phone(self):
        it = self.full_list()[0]
        ok, err, out = book.log_contact(NORA, it["g"])
        self.assertTrue(ok, err)
        c = db.contact(out["contact_id"])
        self.assertEqual(c["at"], "2026-11-15T10:00:00")
        self.assertEqual(c["employee"], NORA)
        self.assertEqual(engine.phone_key(out["phone"]), it["_key"])
        self.assertIn(NORA, out["text"])

    def test_one_contact_per_guest_per_45_days_and_first_logger_wins(self):
        self.own[2]["employee"] = NORA                           # give عهود a unit in the same compound
        self.own[1]["employee"] = AHOOD
        it = self.full_list(NORA)[0]
        self.assertTrue(book.log_contact(NORA, it["g"])[0])
        self.assertFalse(book.log_contact(NORA, it["g"])[0])     # gone from her own list
        self.assertFalse(book.log_contact(AHOOD, it["g"])[0])    # and a colleague cannot take it
        self.assertEqual(len(db.contacts()), 1)
        self.clock += datetime.timedelta(days=44)
        self.assertFalse(book.log_contact(AHOOD, it["g"])[0])
        self.clock += datetime.timedelta(days=1)                 # day 45
        self.assertTrue(book.log_contact(AHOOD, it["g"])[0])

    def test_unlinked_login_and_a_made_up_token_do_nothing(self):
        self.assertFalse(book.log_contact("", self.full_list()[0]["g"])[0])
        self.assertFalse(book.log_contact(NORA, "0" * 20)[0])
        self.assertEqual(db.contacts(), [])

    def test_outcome_only_by_the_one_who_logged_it(self):
        ok, _, out = book.log_contact(NORA, self.full_list()[0]["g"])
        self.assertFalse(book.set_outcome(AHOOD, out["contact_id"], "booked")[0])
        self.assertFalse(book.set_outcome(NORA, out["contact_id"], "paid")[0])
        self.assertTrue(book.set_outcome(NORA, out["contact_id"], "interested")[0])
        self.assertEqual(db.contact(out["contact_id"])["outcome"], "interested")

    def test_reasons_are_plain_arabic_and_no_phone_leaves(self):
        lst = book.public_items(book.call_list(NORA, self.today()))
        self.assertTrue(lst["items"])
        for it in lst["items"]:
            self.assertEqual(set(it), {"g", "name", "reason", "unit", "unit_name", "night", "stays", "score"})
            self.assertIn("سكن عندك", it["reason"])
            self.assertNotIn(" ", it["name"])                    # first name only


# ============================================================ money

class Money(Case):
    def contact_and_book(self, count=3, unit="102", total=1000.0, emp=NORA):
        """`count` guests are contacted today and book two days later (20-22 Nov)."""
        items = self.full_list(emp)[:count]
        for it in items:
            self.assertTrue(book.log_contact(emp, it["g"])[0])
        for it in items:
            g = book.guests()[it["_key"]]
            self.res(unit, g["phone"], g["name"], "2026-11-20", "2026-11-22", total=total,
                     created="2026-11-17")
        book.run_attribution()
        return items

    def test_commission_only_after_checkout(self):
        self.contact_and_book()
        sheet = money.month_sheet("2026-11", self.today())       # 15 Nov: nobody has stayed yet
        self.assertEqual(sheet["pending"], 3)
        self.assertEqual(sheet["raw_total"], 0.0)
        self.assertFalse(sheet["ready"])
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)
        sheet = money.month_sheet("2026-11", self.today())
        self.assertEqual(sheet["pending"], 0)
        self.assertEqual(sheet["raw_total"], 180.0)              # 3 x 1000 x 20% fee x 30% share
        self.assertTrue(sheet["ready"])

    def test_total_paid_never_exceeds_the_cap(self):
        self.contact_and_book()
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)
        sheet = money.month_sheet("2026-11", self.today())
        self.assertEqual(sheet["pool"], 300.0)                   # 50% x 3 added bookings x 200 fee
        self.assertEqual(sheet["total_paid"], 180.0)
        self.assertLessEqual(sheet["total_paid"], sheet["pool"])
        self.assertLessEqual(sheet["total_paid"], 0.5 * sheet["uplift_fee"])
        db.set_setting("manager", "مدير")
        sheet = money.month_sheet("2026-11", self.today())
        self.assertEqual(sheet["manager"]["amount"], 27.0)       # 15% on top, from the same pool
        self.assertLessEqual(sheet["total_paid"], sheet["pool"])

    def test_guests_who_would_have_come_anyway_pay_nothing(self):
        self.contact_and_book()
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)
        real = money.natural_rates
        money.natural_rates = lambda mk: {1: 1.0, 2: 1.0, 3: 1.0}   # history: they always rebook
        try:
            money._sheet_cache.clear()
            sheet = money.month_sheet("2026-11", self.today())
        finally:
            money.natural_rates = real
            money._sheet_cache.clear()
        self.assertEqual(sheet["raw_total"], 180.0)              # they still CLAIM it
        self.assertEqual(sheet["pool"], 0.0)
        self.assertEqual(sheet["total_paid"], 0.0)               # and the cap pays nothing

    def test_no_evidence_means_no_uplift(self):
        self.contact_and_book()
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)
        real = money.natural_rates
        money.natural_rates = lambda mk: {1: None, 2: None, 3: None}
        try:
            money._sheet_cache.clear()
            sheet = money.month_sheet("2026-11", self.today())
        finally:
            money.natural_rates = real
            money._sheet_cache.clear()
        self.assertEqual({b["rate_source"] for b in sheet["measure"]["buckets"]}, {"none"})
        self.assertEqual(sheet["total_paid"], 0.0)

    def test_like_with_like_uses_each_buckets_own_rate(self):
        for i in range(60):                                      # every guest gets a second past stay
            self.res("102", self.phone(i), "ضيف%d فلان" % i, "2025-06-01", "2025-06-02")
        items = self.contact_and_book(count=4)
        self.assertEqual({db.contacts()[0]["bucket"]}, {2})
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)
        real = money.natural_rates
        money.natural_rates = lambda mk: {1: 0.0, 2: 0.5, 3: 0.0}  # repeat guests rebook half the time
        try:
            money._sheet_cache.clear()
            sheet = money.month_sheet("2026-11", self.today())
        finally:
            money.natural_rates = real
            money._sheet_cache.clear()
        self.assertEqual(len(items), 4)
        self.assertEqual(sheet["measure"]["expected_natural"], 2.0)   # 4 contacted x 0.5
        self.assertEqual(sheet["incremental"], 2.0)                   # not 4
        self.assertEqual(sheet["pool"], 200.0)                        # 50% x 2 x 200

    def test_unit_with_no_fee_on_record_pays_zero_and_is_flagged(self):
        self.fee.pop("102")
        self.contact_and_book()
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)
        sheet = money.month_sheet("2026-11", self.today())
        self.assertEqual(sheet["raw_total"], 0.0)
        self.assertEqual(sheet["no_fee_units"], ["A2"])

    def test_a_cancelled_booking_earns_nothing(self):
        self.contact_and_book(count=1)
        rid = db.attrs()[0]["res_id"]
        db.execute("UPDATE tg_res SET status='cancelled' WHERE res_id=?", (rid,))
        book.run_attribution()
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)
        sheet = money.month_sheet("2026-11", self.today())
        self.assertEqual(sheet["lines"], [])
        self.assertEqual(sheet["total_paid"], 0.0)

    def test_a_booking_made_before_the_contact_is_not_attributed(self):
        it = self.full_list()[0]
        g = book.guests()[it["_key"]]
        self.assertTrue(book.log_contact(NORA, it["g"])[0])
        self.res("102", g["phone"], g["name"], "2026-12-20", "2026-12-22", created="2026-11-14")
        self.res("102", g["phone"], g["name"], "2027-01-20", "2027-01-22", created="2026-12-05")  # day 20
        self.assertEqual(book.run_attribution(), 0)

    def test_ops_multiplier_applies_before_the_cap(self):
        self.contact_and_book()
        HOST.ops_multiplier = lambda emp, mk: 0.9                # one active warning
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)
        sheet = money.month_sheet("2026-11", self.today())
        self.assertEqual(sheet["employees"][0]["paid"], 162.0)

    def test_approval_is_one_row_and_nothing_else(self):
        self.contact_and_book()
        self.assertFalse(money.approve_month("2026-11", "owner")[0])      # month not closed, guests not out
        self.clock = datetime.datetime(2026, 12, 20, 10, 0)

        def counts():
            return {t: db.q1("SELECT COUNT(*) AS n FROM %s" % t)["n"] for t in
                    ("tg_res", "tg_contacts", "tg_attr", "tg_targets", "tg_consent", "tg_dnc",
                     "tg_links", "tg_blocked", "tg_names")}
        before = counts()
        ok, err = money.approve_month("2026-11", "owner")
        self.assertTrue(ok, err)
        self.assertEqual(counts(), before)
        row = db.approval("2026-11")
        self.assertEqual((row["by"], row["total_paid"]), ("owner", 180.0))
        self.assertFalse(money.approve_month("2026-11", "owner")[0])      # once
        for mod in (money, book, score, history, db):
            src = inspect.getsource(mod)
            for word in ("api_post", "api_put", "payroll_", "erp_", "requests."):
                self.assertNotIn(word, src)


# ============================================================ scoreboard

class Scoreboard(Case):
    def fill(self, unit, month, nights, price=500.0):
        s, _ = engine.month_bounds(month)
        self.res(unit, "", "", s.isoformat(), (s + datetime.timedelta(days=nights)).isoformat(),
                 total=price * nights)

    def test_propose_then_approve_freezes_the_units(self):
        for mk, n in (("2026-07", 15), ("2026-08", 18), ("2026-09", 21)):
            self.fill("102", mk, n)
        rows = {r["unit"]: r for r in score.propose("2026-Q4", self.today())}
        self.assertEqual(score.quarter_state("2026-Q4"), "proposed")
        r = rows["102"]
        base = sum(n / d for n, d in ((15, 31), (18, 31), (21, 30))) / 3
        self.assertAlmostEqual(r["baseline"], base, places=3)
        t = engine.tiers(r["baseline"])
        self.assertAlmostEqual(r["bronze"], t["bronze"], places=3)
        self.assertEqual(r["employee"], NORA)
        self.assertEqual(r["ceiling_suggested"], 500)
        self.assertEqual(rows["201"]["basis"], "peers")           # no history: its peers' average
        self.assertEqual(db.edit_target("2026-Q4", "102", 300, 650), 1)
        self.assertEqual(db.approve_targets("2026-Q4", "owner", "now"), 3)
        self.assertEqual(db.edit_target("2026-Q4", "102", 1, 2), 0)      # bounds are fixed once approved
        self.own[1]["employee"] = AHOOD                                  # the calendar moves A2 mid-quarter
        score.propose("2026-Q4", self.today())
        self.assertEqual(db.target("2026-Q4", "102")["employee"], NORA)  # the board does not

    def test_a_unit_with_no_floor_gets_a_suggested_one_from_its_own_history(self):
        """2026-11-15: every floor showed 0 because none is set anywhere in the system."""
        s, _ = engine.month_bounds("2026-08")
        for i, price in enumerate([200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100]):
            a = s + datetime.timedelta(days=i)
            self.res("102", "", "", a.isoformat(), (a + datetime.timedelta(days=1)).isoformat(), total=price)
        r = {x["unit"]: x for x in score.propose("2026-Q4", self.today())}["102"]
        self.assertEqual(r["floor_suggested"], 200)                 # nine nights in ten sold above it
        self.assertEqual(r["floor"], 200)
        self.assertEqual(r["ceiling_suggested"], 900)
        self.assertGreater(r["ceiling"], r["floor"])
        db.edit_target("2026-Q4", "102", 350, 900)                  # the owner types his own
        r = {x["unit"]: x for x in score.propose("2026-Q4", self.today())}["102"]
        self.assertEqual((r["floor"], r["floor_suggested"]), (350, 200))   # recompute keeps it
        HOST.floor = lambda lid: 275                                # a floor set in the pricing engine wins
        db.execute("DELETE FROM tg_targets")
        r = {x["unit"]: x for x in score.propose("2026-Q4", self.today())}["102"]
        self.assertEqual((r["floor"], r["floor_suggested"]), (275, 200))

    def test_unit_with_no_history_has_no_invented_floor(self):
        r = {x["unit"]: x for x in score.propose("2026-Q4", self.today())}["201"]
        self.assertEqual((r["floor"], r["floor_suggested"], r["ceiling"]), (0, 0, 0))

    def test_an_older_table_gains_the_new_column(self):
        db.execute("DROP TABLE tg_targets")
        db.execute("CREATE TABLE tg_targets (quarter TEXT NOT NULL, unit TEXT NOT NULL, name TEXT, "
                   "employee TEXT, baseline REAL, bronze REAL, silver REAL, gold REAL, floor REAL, "
                   "ceiling REAL, ceiling_suggested REAL, typical REAL, basis TEXT, status TEXT, "
                   "approved_by TEXT, approved_at TEXT, PRIMARY KEY (quarter, unit))")
        db.reset_init_cache()
        self.assertEqual(len(score.propose("2026-Q4", self.today())), 3)
        self.assertIn("floor_suggested", db.targets("2026-Q4")[0])

    def test_baseline_rises_at_most_two_points_a_quarter(self):
        self.fill("102", "2026-04", 6)
        self.fill("102", "2026-05", 6)
        self.fill("102", "2026-06", 6)
        score.propose("2026-Q3", D("2026-06-24"))
        db.approve_targets("2026-Q3", "owner", "now")
        prev = db.target("2026-Q3", "102")["baseline"]
        for mk in ("2026-07", "2026-08", "2026-09"):
            self.fill("102", mk, 27)
        score.propose("2026-Q4", D("2026-09-24"))
        self.assertAlmostEqual(db.target("2026-Q4", "102")["baseline"], prev + 0.02, places=4)

    def test_board_gate_and_share(self):
        score.propose("2026-Q4", self.today())
        db.approve_targets("2026-Q4", "owner", "now")
        b = score.board(NORA, "2026-11", self.today())
        self.assertTrue(b["approved"])
        self.assertEqual((b["hit"], b["scored"], b["share"]), (0, 2, 0.30))
        self.fill("101", "2026-11", 30, price=1000.0)       # at A1's usual price: full nights
        self.fill("102", "2026-11", 30)
        b = score.board(NORA, "2026-11", self.today())
        self.assertEqual((b["hit"], b["scored"], b["share"]), (2, 2, 0.40))
        self.assertEqual(b["units"][0]["tier"], "gold")
        self.assertEqual(b["units"][0]["empty"], 0)

    def test_without_approved_targets_the_share_stays_at_base(self):
        self.fill("101", "2026-11", 30)
        b = score.board(NORA, "2026-11", self.today())
        self.assertFalse(b["approved"])
        self.assertEqual((b["scored"], b["share"]), (0, 0.30))

    def test_unit_blocked_most_of_the_month_is_left_out_not_scored_zero(self):
        score.propose("2026-Q4", self.today())
        db.approve_targets("2026-Q4", "owner", "now")
        db.add_blocked([("102", "2026-11-%02d" % d) for d in range(1, 21)], "test")
        b = score.board(NORA, "2026-11", self.today())
        self.assertEqual(b["scored"], 1)
        self.assertTrue([u for u in b["units"] if u["unit"] == "102"][0]["excluded"])

    def test_rescue_list_and_its_day_10_and_20_snapshots(self):
        score.propose("2026-Q4", self.today())
        db.approve_targets("2026-Q4", "owner", "now")
        names = [r["name"] for r in score.rescue("2026-11", self.today())]
        self.assertEqual(sorted(names), ["A1", "A2", "B1"])
        self.assertFalse(score.snapshot_rescue(D("2026-11-15")))
        self.assertTrue(score.snapshot_rescue(D("2026-11-20")))
        self.assertEqual([s["day"] for s in db.rescues("2026-11")], [20])


if __name__ == "__main__":
    unittest.main()
