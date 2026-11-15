# -*- coding: utf-8 -*-
"""
«الأهداف ودفتر العملاء» — what each person can reach through the routes.

Locked here:
    * an employee's page carries their own money only: no Ouja fee, no contract percentage,
      no colleague's number, no pool and no hidden-group figure (one test per item)
    * a hidden guest appears in NO response an employee can reach — and the admin view shows
      hidden-group COUNTS, never identities
    * the admin view and every admin write refuse a non-admin; the team view refuses a plain employee
    * the WhatsApp route logs the contact and THEN redirects
    * no route inserts or back-dates a contact
    * the public consent box always answers the same, and is rate-limited
    * TG_ENABLED=0 hides the feature

Run: python3 -m unittest tests.test_targets_routes
"""

import asyncio
import inspect
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import targets                                                    # noqa: E402
from targets import book, db, engine, money, routes, score       # noqa: E402
from targets.host import HOST                                     # noqa: E402
from tests.test_targets_flow import AHOOD, Case, NORA             # noqa: E402

FORBIDDEN_KEYS = {"fee", "fee_pct", "avg_fee", "mgmt_pct", "pool", "uplift_fee", "holdout",
                  "holdout_bookings", "measure", "scale", "raw", "raw_total", "total_paid",
                  "incremental", "multiplier", "lines", "employees", "no_fee_units", "res_id",
                  "phone", "phone_key", "_key", "total"}


class Resp(object):
    def __init__(self, text="", status=200, headers=None, content_type="", charset=""):
        self.text, self.status, self.headers = text, status, dict(headers or {})


class Req(object):
    def __init__(self, user="", role="viewer", query=None, body=None, form=None, headers=None, ip="1.1.1.1"):
        self.user, self.role = user, role
        self.query = dict(query or {})
        self._body, self._form = body, dict(form or {})
        self.headers = dict(headers or {})
        self.remote = ip

    async def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    async def post(self):
        return self._form


def keys_of(x, out=None):
    out = set() if out is None else out
    if isinstance(x, dict):
        for k, v in x.items():
            out.add(k)
            keys_of(v, out)
    elif isinstance(x, list):
        for v in x:
            keys_of(v, out)
    return out


class RCase(Case):
    def setUp(self):
        super().setUp()

        async def web_thread(fn, *a, **kw):
            return fn(*a, **kw)
        HOST.web_thread = web_thread
        HOST.json_response = lambda data, status=200: (data, status)
        HOST.dash_auth = lambda r: bool(r.user)
        HOST.req_role = lambda r: r.role
        HOST.actor = lambda r: r.user
        HOST.user_id = lambda r: r.user
        HOST.users = lambda: [{"id": "u_nora", "name": "Nora login", "role": "ops"},
                              {"id": "u_ahood", "name": "Ahood login", "role": "ops"}]
        HOST.web = type("W", (), {"Response": Resp})
        db.set_link("u_nora", NORA, "owner", "now")
        db.set_link("u_ahood", AHOOD, "owner", "now")
        routes._consent_hits.clear()
        self.nora = Req("u_nora", "ops")
        self.ahood = Req("u_ahood", "ops")
        self.owner = Req("admin", "admin")

    def call(self, fn, req):
        return asyncio.run(fn(req))

    def money_scenario(self):
        """Both employees contact and convert, the stays complete, targets approved."""
        self.own[1]["employee"] = AHOOD                            # A2 -> عهود so she has a list too
        score.propose("2026-Q4", self.today())
        db.approve_targets("2026-Q4", "owner", "now")
        for emp in (NORA, AHOOD):
            for it in book.call_list(emp, self.today(), limit=0)["items"][:2]:
                self.assertTrue(book.log_contact(emp, it["g"])[0])
                g = book.guests()[it["_key"]]
                self.res("201", g["phone"], g["name"], "2026-11-20", "2026-11-22", created="2026-11-17")
        book.run_attribution()
        self.clock = self.clock.replace(month=12, day=20)


# ============================================================ employees see their own money only

class EmployeeSeesOwnOnly(RCase):
    def me(self, req=None):
        data, status = self.call(routes._safe(routes.api_me), req or self.nora)
        self.assertEqual(status, 200)
        return data

    def test_own_amount_is_there(self):
        self.money_scenario()
        d = self.me()
        self.assertEqual(d["employee"], NORA)
        self.assertEqual(d["money"]["amount"], money.month_sheet("2026-12", self.today())["total_paid"])
        d = self.me(Req("u_nora", "ops", query={"month": "2026-11"}))
        self.assertGreater(d["money"]["amount"], 0)
        self.assertEqual(len(d["money"]["bookings"]), 2)

    def test_no_ouja_fee(self):
        self.money_scenario()
        d = self.me(Req("u_nora", "ops", query={"month": "2026-11"}))
        self.assertFalse(keys_of(d) & {"fee", "fee_pct", "avg_fee", "uplift_fee", "total"})
        for b in d["money"]["bookings"]:                           # and no per-booking amount to divide
            self.assertEqual(set(b), {"guest", "unit_name", "nights", "state"})

    def test_no_contract_percentage(self):
        self.money_scenario()
        d = self.me(Req("u_nora", "ops", query={"month": "2026-11"}))
        self.assertFalse(keys_of(d) & {"mgmt_pct", "fee_pct"})
        self.assertNotIn("0.25", json.dumps(d))                    # B1's contract fee

    def test_no_colleagues_numbers(self):
        self.money_scenario()
        d = self.me(Req("u_nora", "ops", query={"month": "2026-11"}))
        self.assertNotIn(AHOOD, json.dumps(d, ensure_ascii=False))
        self.assertFalse(keys_of(d) & {"employees", "lines", "activity"})
        self.assertEqual({u["name"] for u in d["board"]["units"]}, {"A1"})

    def test_no_pool_and_no_hidden_group_figures(self):
        self.money_scenario()
        d = self.me(Req("u_nora", "ops", query={"month": "2026-11"}))
        self.assertFalse(keys_of(d) & FORBIDDEN_KEYS, keys_of(d) & FORBIDDEN_KEYS)

    def test_an_employee_cannot_ask_for_a_colleagues_page(self):
        self.money_scenario()
        d = self.me(Req("u_nora", "ops", query={"employee": AHOOD, "month": "2026-11"}))
        self.assertEqual(d["employee"], NORA)
        d = self.me(Req("admin", "admin", query={"employee": AHOOD, "month": "2026-11"}))
        self.assertEqual(d["employee"], AHOOD)                     # the owner can

    def test_unlinked_login_sees_nothing(self):
        d = self.me(Req("u_new", "ops"))
        self.assertFalse(d["linked"])
        self.assertFalse(keys_of(d) & {"board", "money", "employee"})
        d, _ = self.call(routes._safe(routes.api_book_list), Req("u_new", "ops"))
        self.assertFalse(keys_of(d) & {"list", "open"})

    def test_not_logged_in_is_401(self):
        for fn in (routes.api_me, routes.api_book_list, routes.api_team, routes.api_book_outcome):
            _, status = self.call(routes._safe(fn), Req(""))
            self.assertEqual(status, 401)

    def test_admin_view_refuses_everyone_but_the_owner(self):
        for fn in (routes.api_admin, routes.api_propose, routes.api_unit, routes.api_approve_quarter,
                   routes.api_link, routes.api_manager, routes.api_seed_upload, routes.api_sync,
                   routes.api_map_name, routes.api_approve_month):
            data, status = self.call(routes._admin(fn), self.nora)
            self.assertEqual(status, 403, fn.__name__)
            _, status = self.call(routes._admin(fn), Req(""))
            self.assertEqual(status, 401, fn.__name__)
        src = inspect.getsource(routes.register_routes)
        for line in src.splitlines():
            if "/api/targets/admin" in line:
                self.assertIn("_admin(", line)

    def test_team_view_is_for_the_manager_and_the_owner(self):
        _, status = self.call(routes._safe(routes.api_team), self.nora)
        self.assertEqual(status, 403)
        db.set_setting("manager", NORA)
        self.money_scenario()
        data, status = self.call(routes._safe(routes.api_team), Req("u_nora", "ops", query={"month": "2026-11"}))
        self.assertEqual(status, 200)
        self.assertEqual(set(data["activity"][0]), {"employee", "contacts", "bookings", "hit", "scored"})
        self.assertFalse(keys_of(data) & {"pool", "holdout", "fee_pct", "avg_fee", "raw", "paid", "measure"})


# ============================================================ the hidden group in responses

class HoldoutNeverLeaves(RCase):
    def needles(self):
        """Everything that could identify a hidden guest: phone, phone key, token, full name."""
        out = set()
        for key in self.hidden_keys():
            g = book.guests()[key]
            out |= {key, g["phone"], book.token(key), g["name"], book.first_name(g["name"])}
        self.assertTrue(out)
        return out

    def assertClean(self, payload):
        text = json.dumps(payload, ensure_ascii=False)
        for n in self.needles():
            self.assertNotIn(n, text)

    def test_not_in_any_employee_response(self):
        self.money_scenario()
        for req in (Req("u_nora", "ops", query={"month": "2026-11"}),
                    Req("u_ahood", "ops", query={"month": "2026-11"})):
            for fn in (routes.api_me, routes.api_book_list):
                data, _ = self.call(routes._safe(fn), req)
                self.assertClean(data)
        db.set_setting("manager", NORA)
        data, _ = self.call(routes._safe(routes.api_team), Req("u_nora", "ops", query={"month": "2026-11"}))
        self.assertClean(data)

    def test_admin_sees_counts_never_identities(self):
        self.money_scenario()
        data, status = self.call(routes._admin(routes.api_admin), Req("admin", "admin", query={"month": "2026-11"}))
        self.assertEqual(status, 200)
        self.assertGreater(data["sheet"]["measure"]["holdout"], 0)      # the count is there
        self.assertClean(data)                                           # the people are not

    def test_no_search_and_no_lookup_by_phone_exists(self):
        src = inspect.getsource(routes)
        paths = [ln.split('"')[1] for ln in inspect.getsource(routes.register_routes).splitlines() if '"/' in ln]
        self.assertFalse([p for p in paths if "search" in p or "guest" in p or "lookup" in p])
        self.assertNotIn("is_holdout", src)                              # routes never even ask who is hidden

    def test_wa_route_refuses_a_hidden_guests_token(self):
        for key in list(self.hidden_keys())[:3]:
            r = self.call(routes.api_book_wa, Req("u_nora", "ops", form={"g": book.token(key)}))
            self.assertEqual(r.status, 200)                              # an Arabic notice, not a redirect
            self.assertNotIn("Location", r.headers)
        self.assertEqual(db.contacts(), [])


# ============================================================ the WhatsApp route

class WhatsAppRoute(RCase):
    def test_logs_then_redirects(self):
        it = book.call_list(NORA, self.today(), limit=0)["items"][0]
        r = self.call(routes.api_book_wa, Req("u_nora", "ops", form={"g": it["g"]}))
        self.assertEqual(r.status, 302)
        self.assertEqual(r.headers["Location"], "https://wa.me/test?p=" + it["_key"])
        self.assertEqual(r.headers["Referrer-Policy"], "no-referrer")
        rows = db.contacts()
        self.assertEqual([(c["employee"], c["phone_key"], c["at"]) for c in rows],
                         [(NORA, it["_key"], "2026-11-15T10:00:00")])

    def test_a_date_or_phone_in_the_request_is_ignored(self):
        it = book.call_list(NORA, self.today(), limit=0)["items"][0]
        r = self.call(routes.api_book_wa, Req("u_nora", "ops", query={"at": "2026-01-01", "phone": "0500000000"},
                                              form={"g": it["g"], "at": "2026-01-01", "employee": AHOOD}))
        self.assertEqual(r.status, 302)
        c = db.contacts()[0]
        self.assertEqual((c["at"], c["employee"]), ("2026-11-15T10:00:00", NORA))

    def test_no_route_inserts_a_contact_except_the_press(self):
        posts = [ln.split('"')[1] for ln in inspect.getsource(routes.register_routes).splitlines()
                 if ln.strip().startswith("p(")]
        self.assertEqual(sorted(posts), sorted([
            "/api/tg-consent", "/api/targets/admin/propose", "/api/targets/admin/unit",
            "/api/targets/admin/approve-quarter", "/api/targets/admin/link",
            "/api/targets/admin/manager", "/api/targets/admin/seed-upload", "/api/targets/admin/sync",
            "/api/targets/admin/map-name", "/api/targets/admin/approve-month",
            "/api/book/wa", "/api/book/outcome"]))
        src = inspect.getsource(routes)
        self.assertEqual(src.count("log_contact"), 1)
        self.assertNotIn("insert_contact", src)

    def test_outcome_is_own_contacts_only(self):
        it = book.call_list(NORA, self.today(), limit=0)["items"][0]
        self.call(routes.api_book_wa, Req("u_nora", "ops", form={"g": it["g"]}))
        cid = db.contacts()[0]["id"]
        data, _ = self.call(routes._safe(routes.api_book_outcome), Req("u_ahood", "ops", body={"id": cid, "outcome": "booked"}))
        self.assertFalse(data["ok"])
        data, _ = self.call(routes._safe(routes.api_book_outcome), Req("u_nora", "ops", body={"id": cid, "outcome": "interested"}))
        self.assertTrue(data["ok"])
        data, _ = self.call(routes._safe(routes.api_book_list), self.nora)
        self.assertEqual([(c["id"], c["outcome"]) for c in data["open"]], [(cid, "interested")])
        self.assertFalse(keys_of(data) & {"phone", "phone_key", "_key"})


# ============================================================ consent box + switches

class ConsentAndSwitches(RCase):
    def test_consent_answers_the_same_for_everyone(self):
        self.res("101", "0507770001", "Air Guest", "2026-06-01", "2026-06-03", channel="airbnb")
        a = self.call(routes.api_consent, Req(body={"phone": "0507770001", "slug": "a1", "agree": True}))
        b = self.call(routes.api_consent, Req(body={"phone": "0599999999", "slug": "a1", "agree": True}))
        c = self.call(routes.api_consent, Req(body=None))
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertEqual(db.consents(), {engine.phone_key("0507770001")})

    def test_consent_needs_the_tick(self):
        self.res("101", "0507770001", "Air Guest", "2026-06-01", "2026-06-03", channel="airbnb")
        self.call(routes.api_consent, Req(body={"phone": "0507770001", "slug": "a1"}))
        self.assertEqual(db.consents(), set())

    def test_consent_is_rate_limited_per_address(self):
        for i in range(10):
            self.res("101", "05077700%02d" % i, "G%d" % i, "2026-06-01", "2026-06-03", channel="airbnb")
            self.call(routes.api_consent, Req(body={"phone": "05077700%02d" % i, "agree": True}, ip="9.9.9.9"))
        self.assertEqual(len(db.consents()), routes.CONSENT_PER_HOUR)

    def test_there_is_no_trial_mode_and_no_whatsapp_lock(self):
        """Owner's decision 2026-11-15: no dry run. The feature is live once it is switched on."""
        self.money_scenario()
        d, _ = self.call(routes._safe(routes.api_me), Req("u_nora", "ops", query={"month": "2026-11"}))
        self.assertFalse(keys_of(d) & {"flags", "shadow", "book_live"})
        a, _ = self.call(routes._admin(routes.api_admin), Req("admin", "admin", query={"month": "2026-11"}))
        self.assertEqual(set(a["flags"]), {"channels"})
        self.assertNotIn("shadow", a["sheet"])
        data, _ = self.call(routes._admin(routes.api_approve_month), Req("admin", "admin", body={"month": "2026-11"}))
        self.assertTrue(data["ok"], data)                         # the month is closed and every guest has left
        self.assertEqual(db.approval("2026-11")["total_paid"], a["sheet"]["total_paid"])
        with open(routes.STATIC_JS, encoding="utf-8") as f:
            js = f.read()
        host_py = os.path.join(os.path.dirname(os.path.dirname(routes.STATIC_JS)), "host.py")
        with open(host_py, encoding="utf-8") as f:
            host_src = f.read()
        for word in ("shadow", "book_live", "TG_PAYOUT_SHADOW", "TG_BOOK_LIVE"):
            self.assertNotIn(word, js)
            self.assertNotIn(word, host_src)
            self.assertFalse(hasattr(targets, word))

    def test_defaults_and_the_one_off_switch(self):
        for k in ("TG_ENABLED", "TG_POOL_CHANNELS"):
            os.environ.pop(k, None)
        self.assertTrue(targets.enabled())
        self.assertEqual(targets.pool_channels(), ("consented", "direct"))
        os.environ["TG_ENABLED"] = "0"
        self.assertFalse(targets.enabled())

    def test_nightly_runs_once_a_day_after_0330(self):
        import datetime as dt
        self.assertFalse(routes.nightly_due(dt.datetime(2026, 11, 15, 3, 29), ""))
        self.assertTrue(routes.nightly_due(dt.datetime(2026, 11, 15, 3, 30), "2026-11-14"))
        self.assertFalse(routes.nightly_due(dt.datetime(2026, 11, 15, 14, 0), "2026-11-15"))


if __name__ == "__main__":
    unittest.main()
