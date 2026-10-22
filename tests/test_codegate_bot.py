# -*- coding: utf-8 -*-
"""«تسليم الرموز» — bot.py side. Run: python3 -m unittest tests.test_codegate_bot"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-cg")
os.makedirs("/tmp/ouja-test-state-cg", exist_ok=True)

import bot  # noqa: E402
sys.stdout.flush()

_REAL_API_REQUEST = bot._api_request
# sha1 of inspect.getsource(outbound_firewall) + inspect.getsource(send_guest_message) +
# repr(_FW_CODE_CTX), taken from the firewall as it stood at 7bd6cc0 (before R3): the code sender
# must not change the firewall by a single byte
FIREWALL_SHA1 = "bfd8901481bf17204e4d55776f4cd0b7f9fd1e12"
NET_CALLS = []


def _no_network(method, path, *a, **k):
    NET_CALLS.append(path)
    raise RuntimeError("network blocked in tests: %s %s" % (method, path))


def setUpModule():
    bot._api_request = _no_network      # nothing in this file may reach api.hostaway.com


def tearDownModule():
    bot._api_request = _REAL_API_REQUEST


class _Live:
    """Patch the stored soak switch for one test case (default: live)."""
    LIVE = True

    def patch_live(self):
        flow = bot._codegate.flow
        orig = flow.live
        flow.live = lambda: self.LIVE
        self.addCleanup(lambda: setattr(flow, "live", orig))


class TestWiring(unittest.TestCase):
    def setUp(self):
        # Sibling codegate tests leave HOST wired to their own temp STATE_DIR (a unit list that
        # outranks the repo seed). Re-wire to this process's real wiring so order can't matter.
        self.assertTrue(bot._cg_wire())

    def test_package_imported_and_wired(self):
        self.assertTrue(bot._HAS_CODEGATE)
        self.assertTrue(bot._cg_wire())
        self.assertIsNotNone(bot._codegate.HOST.today_arrivals)
        self.assertIsNotNone(bot._codegate.HOST.escalate)

    def test_view_has_send_manual_undo(self):
        v = bot.CodegateView()
        ids = sorted(c.custom_id for c in v.children)
        self.assertEqual(ids, ["cg_manual", "cg_send", "cg_undo"])
        self.assertIsNone(v.timeout)
        styles = {c.custom_id: c.style for c in v.children}
        self.assertEqual(styles["cg_send"], bot.discord.ButtonStyle.success)
        self.assertEqual(styles["cg_manual"], bot.discord.ButtonStyle.secondary)
        self.assertEqual(styles["cg_undo"], bot.discord.ButtonStyle.secondary)

    def test_wiring_has_every_r2_cap_and_no_channel(self):
        H = bot._codegate.HOST
        self.assertIs(H.find_room, bot._cg_find_room)
        self.assertIs(H.create_code_room, bot._cg_create_code_room)
        self.assertIs(H.departures_today, bot._cg_departures_today)
        self.assertIs(H.send_code, bot._cg_send_code)
        self.assertIs(H.delete_room, bot._cg_delete_room)
        self.assertIs(H.log_review, bot._ready_log_review)
        self.assertIs(H.release_send_claim, bot._cg_release_send_claim)
        self.assertIs(H.room_exists, bot._cg_room_exists)
        self.assertFalse(hasattr(bot, "_cg_channel"))

    def test_gated_helpers(self):
        self.assertTrue(bot._cg_gated(461328))       # C2 NFL
        self.assertTrue(bot._cg_gated("526697"))     # 103 NRJS (owner decision)
        self.assertFalse(bot._cg_gated(999999))
        self.assertFalse(bot._cg_gated(None))

    def test_messages_shape(self):
        orig = bot.api_get
        bot.api_get = lambda path, params=None: {"result": [
            {"isIncoming": 1, "body": "I agree", "date": "2026-10-21 10:05:00"},
            {"isIncoming": 0, "body": "rules", "date": "2026-10-21 10:00:00"}]}
        try:
            rows = bot._cg_messages("c1")
        finally:
            bot.api_get = orig
        self.assertEqual(rows[0]["inbound"], True)
        self.assertEqual(rows[0]["at"].hour, 10)
        self.assertEqual(rows[1]["inbound"], False)

    def test_messages_fetch_error_raises(self):
        orig = bot.api_get

        def boom(path, params=None):
            raise RuntimeError("hostaway 500")
        bot.api_get = boom
        try:
            with self.assertRaises(RuntimeError):
                bot._cg_messages("c1")
        finally:
            bot.api_get = orig

    def test_code_sent_raises_on_error_and_reads_code(self):
        self.assertIs(bot._codegate.HOST.code_sent, bot._cg_code_sent)
        orig = bot.api_get
        now = bot.datetime.now(bot.TZ).strftime("%Y-%m-%d %H:%M:%S")

        def boom(path, params=None):
            raise RuntimeError("hostaway 500")
        try:
            bot.api_get = boom
            with self.assertRaises(RuntimeError):
                bot._cg_code_sent("c1")
            self.assertFalse(bot._was_code_sent_recently("c1"))   # old callers unchanged
            bot.api_get = lambda path, params=None: {"result": [
                {"isIncoming": 0, "body": "كود الدخول: 4821 ثم #", "date": now}]}
            self.assertTrue(bot._cg_code_sent("c1"))
            self.assertTrue(bot._was_code_sent_recently("c1"))
            bot.api_get = lambda path, params=None: {"result": [
                {"isIncoming": 1, "body": "my code 4821?", "date": now}]}
            self.assertFalse(bot._cg_code_sent("c1"))
        finally:
            bot.api_get = orig
        self.assertFalse(bot._cg_code_sent(""))

    def test_code_sent_in_is_pure(self):
        now = bot.datetime.now(bot.TZ)
        old = (now - bot.timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S")
        fresh = now.strftime("%Y-%m-%d %H:%M:%S")
        self.assertTrue(bot._code_sent_in([{"isIncoming": 0, "body": "door code 123456",
                                            "date": fresh}]))
        self.assertFalse(bot._code_sent_in([{"isIncoming": 0, "body": "door code 123456",
                                             "date": old}], since_hours=24))
        self.assertFalse(bot._code_sent_in([]))
        self.assertFalse(bot._code_sent_in(None))

    def test_today_arrivals_keeps_minutes_and_uses_tick_day(self):
        orig_ci, orig_lm = bot.unit_checkin_minutes, bot.get_listings_map
        bot.unit_checkin_minutes = lambda lid: 15 * 60 + 30
        bot.get_listings_map = lambda: {461328: "C2 NFL"}
        self.addCleanup(lambda: setattr(bot, "unit_checkin_minutes", orig_ci))
        self.addCleanup(lambda: setattr(bot, "get_listings_map", orig_lm))
        asked = []
        day = "2026-10-23"
        orig = bot._ha_reservations_window

        def win(a, b, s_, e_):
            asked.append((s_, e_))
            return [{"id": 1, "status": "new", "arrivalDate": day, "listingMapId": 461328},
                    {"id": 2, "status": "new", "arrivalDate": day, "listingMapId": 461328,
                     "checkInTime": 17},
                    {"id": 3, "status": "new", "arrivalDate": day, "listingMapId": 461328,
                     "checkInTime": "14:45"}]
        bot._ha_reservations_window = win
        try:
            rows = bot._cg_today_arrivals(day)
        finally:
            bot._ha_reservations_window = orig
        self.assertEqual(asked, [(day, day)])
        got = {r["res_id"]: r["checkin_at"] for r in rows}
        self.assertEqual(got["1"], day + "T15:30:00+03:00")    # listing minutes kept
        self.assertEqual(got["2"], day + "T17:00:00+03:00")    # reservation hour wins
        self.assertEqual(got["3"], day + "T14:45:00+03:00")
        self.assertTrue(all(r["day"] == day for r in rows))

    def test_today_arrivals_filters_and_shapes(self):
        orig_ci, orig_lm = bot.unit_checkin_minutes, bot.get_listings_map
        bot.unit_checkin_minutes = lambda lid: 15 * 60
        bot.get_listings_map = lambda: {461328: "C2 NFL"}
        self.addCleanup(lambda: setattr(bot, "unit_checkin_minutes", orig_ci))
        self.addCleanup(lambda: setattr(bot, "get_listings_map", orig_lm))
        orig = bot._ha_reservations_window
        bot._ha_reservations_window = lambda *a: [
            {"id": 1, "status": "new", "arrivalDate": bot.now_riyadh().date().isoformat(),
             "listingMapId": 461328, "guestName": "Sara", "conversationId": 7, "checkInTime": 16},
            {"id": 2, "status": "cancelled", "arrivalDate": bot.now_riyadh().date().isoformat(),
             "listingMapId": 461328}]
        try:
            rows = bot._cg_today_arrivals()
        finally:
            bot._ha_reservations_window = orig
        self.assertEqual([r["res_id"] for r in rows], ["1"])
        self.assertTrue(rows[0]["checkin_at"].endswith("16:00:00+03:00"))
        self.assertEqual(rows[0]["conversation_id"], "7")


    def test_card_view_has_real_callbacks(self):
        # discord.py dispatches a click on a card to the view stored for THAT message id before
        # the bot.add_view() one, so a card's view must itself carry the callbacks.
        v = bot._cg_view(["send", "manual"])
        self.assertIsInstance(v, bot.CodegateView)
        self.assertEqual(sorted(c.custom_id for c in v.children), ["cg_manual", "cg_send"])
        # decorator buttons carry an INSTANCE callback; a bare Button keeps the base no-op
        for c in v.children:
            self.assertIn("callback", vars(c))
        self.assertEqual({c.custom_id: c.callback.callback.__name__ for c in v.children},
                         {"cg_send": "send", "cg_manual": "manual"})
        self.assertIsNone(v.timeout)
        u = bot._cg_view(["undo"])
        self.assertEqual([c.custom_id for c in u.children], ["cg_undo"])
        self.assertEqual(list(bot._cg_view([]).children), [])
        self.assertEqual(list(bot._cg_view(["release"]).children), [])   # unknown: nothing

    def _dispatch(self, custom_id, buttons):
        import asyncio
        import discord
        from types import SimpleNamespace as NS
        from discord.ui.view import ViewStore

        async def go():
            store = ViewStore(NS())
            store.add_view(bot.CodegateView(), None)        # bot.add_view at boot
            store.add_view(bot._cg_view(buttons), 111)      # what ch.send(view=) does
            key = (discord.ComponentType.button.value, custom_id)
            return store._views.get(111, {}).get(key) or store._views.get(None, {}).get(key)

        return asyncio.new_event_loop().run_until_complete(go())

    def test_click_dispatches_send(self):
        item = self._dispatch("cg_send", ["send", "manual"])
        self.assertIsNotNone(item)
        self.assertIsInstance(item.view, bot.CodegateView)
        self.assertIn("callback", vars(item))
        self.assertEqual(item.callback.callback.__name__, "send")

    def test_click_dispatches_manual_and_undo(self):
        self.assertEqual(self._dispatch("cg_manual", ["send", "manual"]).callback.callback
                         .__name__, "manual")
        self.assertEqual(self._dispatch("cg_undo", ["undo"]).callback.callback.__name__, "undo")

    def test_button_labels_match_engine(self):
        v = bot.CodegateView()
        labels = {c.custom_id: c.label for c in v.children}
        E = bot._codegate.engine
        self.assertEqual(labels, {"cg_send": E.LABEL_SEND, "cg_manual": E.LABEL_MANUAL,
                                  "cg_undo": E.LABEL_UNDO})

    def test_tick_minutes_survives_garbage(self):
        old = os.environ.get("CODEGATE_TICK_MIN")
        self.addCleanup(lambda: os.environ.pop("CODEGATE_TICK_MIN", None) if old is None
                        else os.environ.__setitem__("CODEGATE_TICK_MIN", old))
        for raw, want in (("abc", 10), ("", 10), ("0", 1), ("5", 5)):
            os.environ["CODEGATE_TICK_MIN"] = raw
            self.assertEqual(bot._cg_tick_minutes(), want, raw)

    def test_ungated_arrival_skipped_without_checkin_lookup(self):
        calls = []
        orig_ci, orig_lm = bot.unit_checkin_minutes, bot.get_listings_map
        bot.unit_checkin_minutes = lambda lid: calls.append(lid) or 15 * 60
        bot.get_listings_map = lambda: {461328: "C2 NFL", 999999: "Other"}
        self.addCleanup(lambda: setattr(bot, "unit_checkin_minutes", orig_ci))
        self.addCleanup(lambda: setattr(bot, "get_listings_map", orig_lm))
        orig = bot._ha_reservations_window
        today = bot.now_riyadh().date().isoformat()
        bot._ha_reservations_window = lambda *a: [
            {"id": 1, "status": "new", "arrivalDate": today, "listingMapId": 999999},
            {"id": 2, "status": "new", "arrivalDate": today, "listingMapId": 461328}]
        try:
            rows = bot._cg_today_arrivals()
        finally:
            bot._ha_reservations_window = orig
        self.assertEqual([r["res_id"] for r in rows], ["2"])
        self.assertEqual(calls, [461328])


class TestGatedBehaviour(_Live, unittest.TestCase):
    def setUp(self):
        self.patch_live()
        self.sent = []
        self._send = bot.send_guest_message
        bot.send_guest_message = lambda cid, body, kind="email": self.sent.append(body)
        self._req = bot._unit_requires_agreement
        bot._unit_requires_agreement = lambda lid: True
        self._url = bot.find_agreement_url
        bot.find_agreement_url = lambda cid: "https://sign.example/x"
        self._lm = bot.get_listings_map
        bot.get_listings_map = lambda: {}
        if bot.datetime.now(bot.TZ).hour >= 23:
            self.skipTest("needs a check-in hour later today")

    def tearDown(self):
        bot.send_guest_message = self._send
        bot._unit_requires_agreement = self._req
        bot.find_agreement_url = self._url
        bot.get_listings_map = self._lm

    def res(self, lid):
        now = bot.datetime.now(bot.TZ)
        return {"id": 77, "status": "new", "arrivalDate": now.date().isoformat(),
                "listingMapId": lid, "guestName": "Sara", "conversationId": 5,
                "checkInTime": min(now.hour + 1, 23), "reservationAgreement": "not_signed"}

    def test_old_reminder_skips_gated_units(self):
        bot._agreement_reminded.discard(77)
        self.assertFalse(bot._check_agreement_for_one(self.res(461328), bot.datetime.now(bot.TZ)))
        self.assertEqual(self.sent, [])

    def test_old_reminder_unchanged_for_other_units(self):
        bot._agreement_reminded.discard(77)
        bot._check_agreement_for_one(self.res(999999), bot.datetime.now(bot.TZ))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("https://sign.example/x", self.sent[0])
        bot._agreement_reminded.discard(77)

    def test_soak_old_reminder_still_sent_for_gated_unit(self):
        self.LIVE = False
        bot._agreement_reminded.discard(77)
        bot._check_agreement_for_one(self.res(461328), bot.datetime.now(bot.TZ))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("https://sign.example/x", self.sent[0])
        bot._agreement_reminded.discard(77)

    def test_live_gated_needs_both(self):
        self.assertTrue(bot._cg_live_gated(461328))
        self.assertFalse(bot._cg_live_gated(999999))
        self.LIVE = False
        self.assertFalse(bot._cg_live_gated(461328))
        flow = bot._codegate.flow

        def boom():
            raise RuntimeError("db gone")
        flow.live = boom
        self.assertFalse(bot._cg_live_gated(461328))     # never raises

    def test_rule_escalates_after_checkin_without_release(self):
        for hrs in (0, -0.5, -3):
            txt = bot._cg_code_rule(released=False, hrs=hrs)
            self.assertIn("action='escalate'", txt)
            self.assertNotIn("action='reply'", txt)
            self.assertIn("اعتذر", txt)
            self.assertIn("الفريق يتابع إرسال الرمز", txt)
            self.assertNotIn("الحين", txt)          # no time word next to «لا تحدد وقت»
            for bad in ("العقد", "توقيع", "شاف"):
                self.assertNotIn(bad, txt)
        before = bot._cg_code_rule(released=False, hrs=2)
        self.assertIn("action='reply'", before)
        self.assertNotIn("escalate", before)
        self.assertNotIn("شاف", before)
        self.assertIn("اشكره", before)

    def test_code_in_reuses_fetched_chat_with_the_honesty_rule(self):
        import datetime
        tz = bot.TZ
        now = datetime.datetime.now(tz)
        code = {"inbound": False, "body": "كود الدخول 4821", "at": now - datetime.timedelta(hours=2)}
        self.assertTrue(bot._cg_code_in([code]))
        self.assertFalse(bot._cg_code_in([dict(code, inbound=True)]))          # guest's own words
        self.assertFalse(bot._cg_code_in([dict(code, at=now - datetime.timedelta(hours=30))]))
        self.assertFalse(bot._cg_code_in([dict(code, body="هلا وسهلا")]))
        self.assertFalse(bot._cg_code_in([]))
        self.assertTrue(bot._cg_code_in([dict(code, at=None)]))                # no timestamp ≠ old

    def test_musaed_prompt_mentions_agree_rule(self):
        self.assertIn("أوافق", bot.SYSTEM_PROMPT_ANTI_NAG_GATED)

    def test_musaed_gated_block_wording(self):
        txt = bot._cg_code_rule(released=False, hrs=3)
        self.assertIn("أوافق", txt)
        self.assertNotIn("العقد", txt)
        self.assertNotIn("توقيع", txt)
        self.assertIn("action='reply'", txt)
        done = bot._cg_code_rule(released=True, hrs=3)
        self.assertIn("أرسل الرمز", done)

    def test_rule_covers_guest_who_already_agreed(self):
        txt = bot._cg_code_rule(released=False, hrs=3)
        self.assertIn("ولا تطلبها منه مرة ثانية", txt)
        self.assertNotIn("العقد", txt)
        self.assertNotIn("توقيع", txt)


class TestGatedStatusScreens(_Live, unittest.TestCase):
    def setUp(self):
        self.patch_live()
        self.saved = {n: getattr(bot, n) for n in (
            "compute_arrivals_with_status", "_unit_requires_agreement", "_wd_cleaning_ok",
            "_cg_gated", "compute_pricing_alerts")}
        bot._unit_requires_agreement = lambda lid: False     # Hostaway flag OFF
        bot._wd_cleaning_ok = lambda lid, d: True
        bot._cg_gated = lambda lid: lid == 461328
        bot.compute_pricing_alerts = lambda: []              # its forward calendar is Hostaway

    def tearDown(self):
        for n, v in self.saved.items():
            setattr(bot, n, v)

    def arrivals(self, signed):
        iso = bot.datetime.now(bot.TZ).date().isoformat() + "T15:00"
        bot.compute_arrivals_with_status = lambda **k: [
            {"checkin_iso": iso, "listing_id": 461328, "unit": "G", "guest": "A",
             "signed": signed, "conversation_id": None},
            {"checkin_iso": iso, "listing_id": 999999, "unit": "N", "guest": "B",
             "signed": False, "conversation_id": None}]

    def test_update_rows_gated_beats_not_required(self):
        self.arrivals(False)
        rows = {r["unit"]: r["agreement"] for r in bot.build_update_rows()}
        self.assertEqual(rows["G"], "awaiting_agree")
        self.assertEqual(rows["N"], "not_required")      # non-gated unchanged
        self.arrivals(True)
        rows = {r["unit"]: r["agreement"] for r in bot.build_update_rows()}
        self.assertEqual(rows["G"], "code_released")

    def test_update_render_labels(self):
        txt = bot.render_update([
            {"unit": "G", "agreement": "code_released"},
            {"unit": "H", "agreement": "awaiting_agree"},
            {"unit": "N", "agreement": "not_required"}], "d")
        self.assertIn("الرمز أُرسل ✅", txt)
        self.assertIn("بانتظار «أوافق» ⏳", txt)
        self.assertIn("📝 العقد: لا يحتاج", txt)

    def test_urgent_skips_gated_unsigned(self):
        self.arrivals(False)
        base = {"guest": "A", "unit": "x", "reservation_id": 1, "hours_until": 1.0,
                "checkin_label": "t", "signed": False}
        bot.compute_arrivals_with_status = lambda **k: [
            dict(base, listing_id=461328, reservation_id=1),
            dict(base, listing_id=999999, reservation_id=2)]
        items = [i for i in bot.compute_urgent_now() if i["kind"] == "unsigned_agreement"]
        self.assertEqual([i["id"] for i in items], ["2"])

    def test_soak_screens_behave_as_non_gated(self):
        self.LIVE = False
        self.arrivals(False)
        rows = {r["unit"]: r["agreement"] for r in bot.build_update_rows()}
        self.assertEqual(rows["G"], "not_required")      # as before the feature
        base = {"guest": "A", "unit": "x", "reservation_id": 1, "hours_until": 1.0,
                "checkin_label": "t", "signed": False}
        bot.compute_arrivals_with_status = lambda **k: [
            dict(base, listing_id=461328, reservation_id=1),
            dict(base, listing_id=999999, reservation_id=2)]
        items = [i for i in bot.compute_urgent_now() if i["kind"] == "unsigned_agreement"]
        self.assertEqual(sorted(i["id"] for i in items), ["1", "2"])


class TestTaskFiveSitesUseLiveGate(unittest.TestCase):
    """Every behaviour change outside the list itself must ask _cg_live_gated, so the soak
    leaves gated units exactly as today. _cg_gated is allowed only in the list's own code."""
    ALLOWED = {"_cg_gated", "_cg_live_gated", "_cg_today_arrivals"}

    def test_cg_gated_only_in_list_code(self):
        import re
        with open(bot.__file__, encoding="utf-8") as fh:
            src = fh.read().splitlines()
        current, offenders = None, []
        for line in src:
            m = re.match(r"\s*(?:async\s+)?def\s+(\w+)", line)
            if m and not line.startswith((" " * 8)):
                current = m.group(1)
            if "_cg_gated(" in line and current not in self.ALLOWED:
                offenders.append((current, line.strip()))
        self.assertEqual(offenders, [])

    def test_live_gate_sites_present(self):
        with open(bot.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertGreaterEqual(src.count("_cg_live_gated("), 7)   # def + 6 sites


class _Ctx:
    def __init__(self, admin=True):
        self.author = type("U", (), {"id": 5, "display_name": "Faisal"})()
        self.admin = admin
        self.replies = []

    async def reply(self, text):
        self.replies.append(text)


class TestSwitchCommands(unittest.TestCase):
    def setUp(self):
        import tempfile
        from brain import db as bdb
        self.tmp = tempfile.mkdtemp(prefix="cgcmd_")
        self._bdb_path = bdb._DB_PATH_OVERRIDE
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        bot._codegate.db.reset_init_cache()
        bot._codegate.flow._live_cache.update({"v": None, "at": 0.0})
        self._admin = bot._tk_is_admin
        self.addCleanup(self.restore)

    def restore(self):
        from brain import db as bdb
        bot._tk_is_admin = self._admin
        bdb.set_db_path_for_tests(self._bdb_path)
        bot._codegate.db.reset_init_cache()
        bot._codegate.flow._live_cache.update({"v": None, "at": 0.0})

    def call(self, cmd, admin=True, **kw):
        import asyncio
        bot._tk_is_admin = lambda u: admin
        ctx = _Ctx(admin)
        asyncio.run(cmd.callback(ctx, **kw))
        return ctx.replies[-1]

    def test_live_needs_admin(self):
        txt = self.call(bot.codegate_live_cmd, admin=False, confirm="تشغيل")
        self.assertIn("للمشرفين", txt)
        self.assertFalse(bot._codegate.flow.live())

    def test_live_needs_typed_confirm(self):
        txt = self.call(bot.codegate_live_cmd, confirm="")
        self.assertIn("!ouja رموز-تشغيل تشغيل", txt)
        self.assertFalse(bot._codegate.flow.live())
        self.call(bot.codegate_live_cmd, confirm="yes")
        self.assertFalse(bot._codegate.flow.live())

    def test_live_confirm_ignores_invisible_direction_marks(self):
        for i, junk in enumerate(("\u200fتشغيل", "تشغيل\u200e", "\u061cتشغيل\u200b ", " \u200eتشغ\u200bيل\u200f ")):
            bot._codegate.flow.set_live(False, "t")
            self.call(bot.codegate_live_cmd, confirm=junk)
            self.assertTrue(bot._codegate.flow.live(), "case %d" % i)
        bot._codegate.flow.set_live(False, "t")
        self.call(bot.codegate_live_cmd, confirm="تشغيلا")          # a real typo still refuses
        self.assertFalse(bot._codegate.flow.live())

    def test_status_reports_live_since_when_live(self):
        orig = bot._codegate.flow.tick

        async def fake_tick(**k):
            return {"live": 1, "seen": 0}
        bot._codegate.flow.tick = fake_tick
        self.addCleanup(lambda: setattr(bot._codegate.flow, "tick", orig))
        self.assertNotIn("live_since", self.call(bot.codegate_cmd))
        self.call(bot.codegate_live_cmd, confirm="تشغيل")
        stamp = bot._codegate.db.get_setting("live_since")
        self.assertTrue(stamp)
        self.assertIn(stamp[:16].replace("T", " "), self.call(bot.codegate_cmd))

    def test_live_on_then_off(self):
        txt = self.call(bot.codegate_live_cmd, confirm="تشغيل")
        self.assertIn("مباشر", txt)
        self.assertTrue(bot._codegate.flow.live())
        self.assertEqual(bot._codegate.db.get_setting("live"), "1")
        self.assertIn("للمشرفين", self.call(bot.codegate_soak_cmd, admin=False))
        self.assertTrue(bot._codegate.flow.live())
        txt = self.call(bot.codegate_soak_cmd)
        self.assertIn("تجربة", txt)
        self.assertFalse(bot._codegate.flow.live())

    def _seed_today(self):
        db = bot._codegate.db
        today = bot.now_riyadh().date().isoformat()
        base = {"lid": 461328, "day": today, "unit": "C2", "guest": "G", "conversation_id": "c",
                "checkin_at": today + "T16:00:00+03:00", "cover_name": "", "cover_did": "",
                "cover_role_id": "", "owner_did": ""}
        for rid in ("71", "72", "73", "74"):
            db.upsert_arrival(dict(base, res_id=rid))
        db.set_room("71", "500", "turnover")
        db.set_room("72", "501", "code")
        db.mark_cancelled(today, {"71", "72", "73"})              # 74 cancelled: not counted

    def test_status_reports_placement_and_code_available_never_the_code(self):
        orig_tick, orig_get = bot._codegate.flow.tick, bot.api_get

        async def fake_tick(**k):
            return {"live": 1, "seen": 3}
        asked = []

        def get(path, params=None):
            asked.append(path)
            door = {"/reservations/71": "987654", "/reservations/72": " # ",
                    "/reservations/73": "135791"}
            if path == "/reservations/73":
                raise RuntimeError("hostaway 500 135791")
            return {"result": {"doorCode": door.get(path)}}
        bot._codegate.flow.tick = fake_tick
        bot.api_get = get
        self.addCleanup(lambda: setattr(bot._codegate.flow, "tick", orig_tick))
        self.addCleanup(lambda: setattr(bot, "api_get", orig_get))
        self._seed_today()
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            txt = self.call(bot.codegate_cmd)
        self.assertIn("turnover=1", txt)
        self.assertIn("code=1", txt)
        self.assertIn("waiting=1", txt)
        self.assertIn("code_available=1/3", txt)
        self.assertIn("code_errors=1", txt)
        self.assertEqual(sorted(asked), ["/reservations/71", "/reservations/72",
                                         "/reservations/73"])
        for code in ("987654", "135791"):
            self.assertNotIn(code, txt)
            self.assertNotIn(code, out.getvalue())

    def test_status_counts_run_off_the_event_loop(self):
        flow = bot._codegate.flow
        orig_tick, orig_rb = flow.tick, flow.run_blocking
        hopped = []

        async def fake_tick(**k):
            return {"live": 0, "seen": 0}

        async def rb(fn, *a, **k):
            hopped.append(getattr(fn, "__name__", ""))
            return fn(*a, **k)
        flow.tick, flow.run_blocking = fake_tick, rb
        self.addCleanup(lambda: setattr(flow, "tick", orig_tick))
        self.addCleanup(lambda: setattr(flow, "run_blocking", orig_rb))
        self.call(bot.codegate_cmd)
        self.assertIn("_cg_status_counts", hopped)

    def test_status_command_reports_mode(self):
        import asyncio
        orig = bot._codegate.flow.tick

        async def fake_tick(**k):
            return {"live": 0, "seen": 0}
        bot._codegate.flow.tick = fake_tick
        self.addCleanup(lambda: setattr(bot._codegate.flow, "tick", orig))
        self.assertIn("تجربة", self.call(bot.codegate_cmd))
        asyncio.run(bot._codegate.flow.run_blocking(bot._codegate.flow.set_live, True, "t"))
        self.assertIn("مباشر", self.call(bot.codegate_cmd))


class _Fx:
    """Swap bot attributes for one test."""

    def swap(self, name, value, owner=None):
        owner = owner or bot
        orig = getattr(owner, name)
        setattr(owner, name, value)
        self.addCleanup(lambda: setattr(owner, name, orig))


class TestSendCode(_Fx, unittest.TestCase):
    """The ONLY code sender. It must never print or log the body or the code."""

    def setUp(self):
        import tempfile
        self.state = tempfile.mkdtemp(prefix="cgsend_")
        self.swap("_state_path", lambda name: os.path.join(self.state, name))
        self.swap("ASSISTANT_SEND_KILL", False)
        self.gets, self.posts, self.events = [], [], []
        self.door = "1234"
        self.status = "new"
        self.listing = 461328
        self.post_error = None

        def get(path, params=None):
            self.gets.append(path)
            return {"result": {"id": 77, "doorCode": self.door, "status": self.status,
                               "listingMapId": self.listing}}

        def post(path, body):
            if self.post_error is not None:
                raise self.post_error
            self.posts.append((path, body))
            return {"status": "success"}
        self.swap("api_get", get)
        self.swap("api_post", post)
        self.swap("log_event", lambda cat, text: self.events.append((cat, text)))

    def send(self, res_id="77", cid="c77", lid=461328):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            res = bot._cg_send_code(res_id, cid, lid)
        self.printed = out.getvalue()
        return res

    def test_send_code_happy_path(self):
        self.assertEqual(self.send(), (True, "sent"))
        self.assertEqual(self.gets, ["/reservations/77"])            # a FRESH read
        self.assertEqual(len(self.posts), 1)
        path, body = self.posts[0]
        self.assertEqual(path, "/conversations/c77/messages")
        self.assertIn("1234#", body["body"])
        self.assertIn("الرقم ثم اضغط #", body["body"])
        self.assertEqual(body["communicationType"], "email")
        self.assertNotIn("1234", self.printed)                       # never printed
        self.assertNotIn("1234", repr(self.events))                  # never logged

    def test_send_code_empty_doorcode(self):
        for door in ("", None, "   ", "#", " # "):
            self.door = door
            self.assertEqual(self.send(res_id="r-%r" % (door,)), (False, "no_code"), door)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.posts, [])

    def test_missing_conversation_has_its_own_reason(self):
        self.assertEqual(self.send(cid=""), (False, "no_conversation"))
        self.assertEqual((self.gets, self.posts), ([], []))         # not even a read

    def test_booking_cancelled_in_hostaway_gets_no_code(self):
        for status in ("cancelled", "inquiry", "", None):
            self.status = status
            self.assertEqual(self.send(res_id="s-%r" % (status,)), (False, "cancelled"), status)
        self.assertEqual(self.posts, [])
        self.status = "modified"
        self.assertEqual(self.send(), (True, "sent"))

    def test_booking_moved_to_another_unit_gets_no_code(self):
        self.listing = 526697
        self.assertEqual(self.send(), (False, "moved"))
        self.assertEqual(self.posts, [])
        self.listing = "461328"                                    # same unit, as a string
        self.assertEqual(self.send(), (True, "sent"))

    def test_unit_check_skipped_when_unknown(self):
        self.listing = None
        self.assertEqual(self.send(res_id="a"), (True, "sent"))
        self.listing = 526697
        self.assertEqual(self.send(res_id="b", lid=None), (True, "sent"))

    def test_timeout_after_post_keeps_claim_and_says_unknown(self):
        import requests
        self.post_error = requests.exceptions.ReadTimeout("read timed out 1234")
        self.assertEqual(self.send(), (False, "unknown"))
        self.assertNotIn("1234", self.printed)
        self.post_error = None
        self.assertEqual(self.send(), (False, "duplicate"))         # claim kept: no 2nd send
        self.assertEqual(self.posts, [])

    def test_connect_timeout_never_reached_hostaway_releases_claim(self):
        import requests
        self.post_error = requests.exceptions.ConnectTimeout("connect timed out")
        self.assertEqual(self.send(), (False, "error"))
        self.post_error = None
        self.assertEqual(self.send(), (True, "sent"))

    def test_empty_code_takes_no_claim(self):
        self.door = ""
        self.send()
        self.door = "1234"
        self.assertEqual(self.send(), (True, "sent"))                # not "duplicate"

    def test_sender_honours_kill_switch_and_dedupe(self):
        bot.ASSISTANT_SEND_KILL = True
        self.assertEqual(self.send(), (False, "killed"))
        self.assertEqual((self.gets, self.posts), ([], []))
        bot.ASSISTANT_SEND_KILL = False
        self.assertEqual(self.send(), (True, "sent"))
        self.assertEqual(self.send(), (False, "duplicate"))
        self.assertEqual(len(self.posts), 1)

    def test_send_failure_releases_claim(self):
        self.post_error = RuntimeError("hostaway 500 body=1234")
        self.assertEqual(self.send(), (False, "error"))
        self.assertIn("RuntimeError", self.printed)
        self.assertNotIn("1234", self.printed)                       # type name only
        self.post_error = None
        self.assertEqual(self.send(), (True, "sent"))                # the retry goes through

    def test_reservation_read_failure_is_error(self):
        def boom(path, params=None):
            raise RuntimeError("hostaway down 1234")
        bot.api_get = boom
        self.assertEqual(self.send(), (False, "error"))
        self.assertEqual(self.posts, [])
        self.assertNotIn("1234", self.printed)

    def test_undo_claim_release_allows_resend(self):
        self.assertEqual(self.send(), (True, "sent"))
        bot._cg_release_send_claim("77")
        self.assertEqual(self.send(), (True, "sent"))
        self.assertEqual(len(self.posts), 2)

    def test_firewall_untouched(self):
        """Every other path still blocks a door code: send_guest_message is unchanged."""
        self.swap("_once_claim", lambda *a, **k: True)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            res = bot.send_guest_message("c77", bot._codegate.engine.code_message("4821"))
        self.assertEqual(res, bot.SEND_FIREWALL_BLOCKED)
        self.assertEqual(self.posts, [])

    def test_firewall_source_unchanged(self):
        import hashlib
        import inspect
        src = "".join(inspect.getsource(f) for f in (bot.outbound_firewall,
                                                      bot.send_guest_message))
        src += repr(bot._FW_CODE_CTX)
        self.assertEqual(hashlib.sha1(src.encode("utf-8")).hexdigest(), FIREWALL_SHA1,
                         "the outbound firewall changed — re-verify that codegate's "
                         "_cg_send_code is still the only code-sending exemption, then update "
                         "FIREWALL_SHA1")


def _http_error(cls, status):
    from types import SimpleNamespace as NS
    return cls(NS(status=status, reason="x"), "boom")


class _FakeMsg:
    def __init__(self, error=None):
        self.error = error
        self.edits = []

    async def edit(self, **kw):
        if self.error is not None:
            raise self.error
        self.edits.append(kw)


class _FakeChannel:
    def __init__(self, cid=900, topic="", name="room", error=None, msg_error=None):
        self.id = cid
        self.topic = topic
        self.name = name
        self.error = error
        self.deleted = []
        self.sent = []
        self.msg = _FakeMsg(msg_error)

    def get_partial_message(self, mid):
        return self.msg

    async def delete(self, reason=None):
        if self.error is not None:
            raise self.error
        self.deleted.append(reason)

    async def send(self, content=None, **kw):
        self.sent.append(content)


def _arun(coro):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro)


class TestDiscordCaps(_Fx, unittest.TestCase):
    def channel(self, ch):
        async def get(cid):
            if isinstance(ch, Exception):
                raise ch
            return ch
        self.swap("_cw_channel", get)

    def test_edit_ok(self):
        ch = _FakeChannel()
        self.channel(ch)
        self.assertTrue(_arun(bot._cg_edit("900", "5", embed={"title": "t"}, buttons=["undo"])))
        self.assertEqual(len(ch.msg.edits), 1)

    def test_edit_false_only_when_gone(self):
        import discord
        self.channel(_http_error(discord.NotFound, 404))             # the room is gone
        self.assertIs(_arun(bot._cg_edit("900", "5")), False)
        self.channel(_FakeChannel(msg_error=_http_error(discord.NotFound, 404)))   # the card
        self.assertIs(_arun(bot._cg_edit("900", "5")), False)
        self.channel(_FakeChannel(msg_error=_http_error(discord.Forbidden, 403)))  # no access
        self.assertIs(_arun(bot._cg_edit("900", "5")), False)

    def test_edit_other_errors_raise(self):
        import discord
        self.channel(_FakeChannel(msg_error=_http_error(discord.HTTPException, 503)))
        with self.assertRaises(discord.HTTPException):
            _arun(bot._cg_edit("900", "5"))
        self.channel(_FakeChannel(msg_error=TimeoutError()))
        with self.assertRaises(TimeoutError):
            _arun(bot._cg_edit("900", "5"))
        self.channel(RuntimeError("fetch failed"))
        with self.assertRaises(RuntimeError):
            _arun(bot._cg_edit("900", "5"))

    def test_post_none_when_room_gone_so_alert_still_escalates(self):
        """flow posts an alert into the card's room and THEN escalates: a hand-deleted room must
        answer None (the contract's "no message"), not raise past the escalation."""
        import discord
        for err in (_http_error(discord.NotFound, 404), _http_error(discord.Forbidden, 403)):
            self.channel(err)
            self.assertIsNone(_arun(bot._cg_post("900", "hi")))
        self.channel(_http_error(discord.HTTPException, 503))
        with self.assertRaises(discord.HTTPException):
            _arun(bot._cg_post("900", "hi"))

    def test_delete_room(self):
        import contextlib
        import io
        import discord
        ch = _FakeChannel()
        self.channel(ch)
        self.assertIs(_arun(bot._cg_delete_room("900", "codegate: code sent")), True)
        self.assertEqual(ch.deleted, ["codegate: code sent"])
        self.channel(_http_error(discord.NotFound, 404))             # already gone = closed
        self.assertIs(_arun(bot._cg_delete_room("900", "r")), True)
        self.channel(_FakeChannel(error=_http_error(discord.NotFound, 404)))
        self.assertIs(_arun(bot._cg_delete_room("900", "r")), True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.channel(_FakeChannel(error=_http_error(discord.Forbidden, 403)))
            self.assertIs(_arun(bot._cg_delete_room("900", "r")), False)
            self.channel(_FakeChannel(error=_http_error(discord.HTTPException, 500)))
            self.assertIs(_arun(bot._cg_delete_room("900", "r")), False)
            self.channel(RuntimeError("x"))
            self.assertIs(_arun(bot._cg_delete_room("900", "r")), False)

    def test_room_exists_is_a_cache_lookup(self):
        known = {900: object()}
        self.swap("get_channel", lambda cid: known.get(cid), owner=bot.bot)
        self.swap("get_guild", lambda gid: object(), owner=bot.bot)
        self.assertTrue(bot._cg_room_exists("900"))
        self.assertFalse(bot._cg_room_exists("901"))
        self.assertTrue(bot._cg_room_exists("garbage"))           # unsure = exists
        self.swap("get_guild", lambda gid: None, owner=bot.bot)   # guild not loaded: unsure
        self.assertTrue(bot._cg_room_exists("901"))
        unavailable = type("G", (), {"unavailable": True})()
        self.swap("get_guild", lambda gid: unavailable, owner=bot.bot)
        self.assertTrue(bot._cg_room_exists("901"))

    def test_find_room_uses_turnover_key(self):
        self.swap("_cw_channels_in", lambda guild: [
            {"channel_id": "51", "key": "461328:2026-10-21", "review": False},
            {"channel_id": "52", "key": "461328:2026-10-22", "review": True},
            {"channel_id": "53", "key": "526697:2026-10-22", "review": False}])
        self.assertEqual(bot._cg_find_room(461328, "2026-10-22"), "52")
        self.assertEqual(bot._cg_find_room("526697", "2026-10-22"), "53")
        self.assertIsNone(bot._cg_find_room(461328, "2026-10-23"))

    def test_departures_today(self):
        asked = []

        def win(a, b, s_, e_):
            asked.append((a, b, s_, e_))
            return [{"status": "new", "departureDate": "2026-10-22", "listingMapId": 461328},
                    {"status": "modified", "departureDate": "2026-10-22", "listingMapId": "7"},
                    {"status": "cancelled", "departureDate": "2026-10-22", "listingMapId": 8},
                    {"status": "new", "departureDate": "2026-10-23", "listingMapId": 9},
                    {"status": "new", "departureDate": "2026-10-22", "listingMapId": None}]
        self.swap("_ha_reservations_window", win)
        self.assertEqual(bot._cg_departures_today("2026-10-22"), {461328, 7})
        self.assertEqual(asked, [("departureStartDate", "departureEndDate",
                                  "2026-10-22", "2026-10-22")])


class _Cat:
    def __init__(self, name, channels=()):
        self.name = name
        self.text_channels = list(channels)
        self.overwrites = {}


class _Guild:
    def __init__(self, cats, loose=()):
        self.categories = cats
        self.loose = list(loose)

    @property
    def text_channels(self):
        out = [c for cat in self.categories for c in cat.text_channels] + self.loose
        return out


class TestCodeRoom(_Fx, unittest.TestCase):
    ITEM = {"res_id": "77", "unit": "Ouja | C2 NFL", "lid": 461328}

    def setUp(self):
        self.made, self.alerts = [], []
        self.cat = _Cat(bot.CATEGORY_NAME)
        self.overflow = _Cat(bot.CATEGORY_NAME + " ٢")
        self.guild = _Guild([self.cat, self.overflow])
        self.swap("get_guild", lambda gid: self.guild, owner=bot.bot)

        async def cat(guild):
            return self.cat

        async def make(guild, category, name, topic=None, overwrites=None):
            self.made.append((category.name, name, topic))
            return _FakeChannel(cid=4242, topic=topic, name=name)

        async def alert(guild, unit, err):
            self.alerts.append((unit, type(err).__name__))
        self.swap("get_category", cat)
        self.swap("_make_channel_spill", make)
        self.swap("_turnover_create_failed_alert", alert)

    def test_code_room_name_and_topic(self):
        self.assertEqual(_arun(bot._cg_create_code_room(self.ITEM)), "4242")
        self.assertEqual(self.made, [(bot.CATEGORY_NAME, "ouja-c2-nfl-code",
                                      "codegate-room:1 codegate-res:77")])

    def test_long_unit_name_is_cut_before_suffix(self):
        _arun(bot._cg_create_code_room(dict(self.ITEM, unit="Ouja | " + "x" * 120)))
        name = self.made[0][1]
        self.assertTrue(name.endswith("-code"))
        self.assertEqual(len(name), 65)

    def test_existing_room_for_same_booking_and_unit_reused(self):
        self.overflow.text_channels.append(_FakeChannel(
            cid=31, topic="codegate-room:1 codegate-res:77", name="ouja-c2-nfl-code"))
        self.assertEqual(_arun(bot._cg_create_code_room(self.ITEM)), "31")
        self.assertEqual(self.made, [])

    def test_room_named_for_another_unit_never_reused(self):
        self.cat.text_channels.append(_FakeChannel(
            cid=32, topic="codegate-room:1 codegate-res:77", name="ouja-b209-code"))
        self.cat.text_channels.append(_FakeChannel(
            cid=33, topic="codegate-room:1 codegate-res:777", name="ouja-c2-nfl-code"))
        self.assertEqual(_arun(bot._cg_create_code_room(self.ITEM)), "4242")
        self.assertEqual(len(self.made), 1)

    def test_create_failure_alerts_and_returns_none(self):
        async def boom(*a, **k):
            raise RuntimeError("30013")
        bot._make_channel_spill = boom
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(_arun(bot._cg_create_code_room(self.ITEM)))
        self.assertEqual(self.alerts, [("Ouja | C2 NFL", "RuntimeError")])


class TestDeleteGuard(_Fx, unittest.TestCase):
    KEY_TOPIC = "oujact:1 oujact-key:461328:2026-10-22 hostaway-res:5"

    def setUp(self):
        flow = bot._codegate.flow
        self.calls = []
        self.hold, self.recorded = True, True

        def should_hold(lid, day):
            self.calls.append(("should_hold", str(lid), day))
            return self.hold

        def defer_close(lid, day, channel_id=None):
            self.calls.append(("defer_close", str(lid), day, channel_id))
            return self.recorded
        self.swap("should_hold", should_hold, owner=flow)
        self.swap("defer_close", defer_close, owner=flow)
        self.swap("is_gated", lambda lid: str(lid) in ("461328", "526697"), owner=flow)

    def test_delete_guard_holds_and_records(self):
        ch = _FakeChannel(cid=900, topic=self.KEY_TOPIC)
        self.assertTrue(_arun(bot._cg_hold_room(ch, 999, "2026-01-01")))
        # the ROOM's own key wins over the caller's lid/date; the room id is passed explicitly
        self.assertEqual(self.calls, [("should_hold", "461328", "2026-10-22"),
                                      ("defer_close", "461328", "2026-10-22", "900")])
        self.assertEqual(len(ch.sent), 1)
        self.assertIn("رمز الدخول", ch.sent[0])

    def test_guard_releases_when_defer_records_nothing(self):
        self.recorded = False                    # the code went out between check and record
        ch = _FakeChannel(cid=900, topic=self.KEY_TOPIC)
        self.assertFalse(_arun(bot._cg_hold_room(ch, 461328, "2026-10-22")))
        self.assertEqual(ch.sent, [])

    def test_delete_guard_off_for_non_gated(self):
        ch = _FakeChannel(cid=900, topic="oujact:1 oujact-key:999999:2026-10-22")
        self.assertFalse(_arun(bot._cg_hold_room(ch, 999999, "2026-10-22")))
        self.assertEqual(self.calls, [])          # not even a pool hop
        self.hold = False
        ch = _FakeChannel(cid=900, topic=self.KEY_TOPIC)
        self.assertFalse(_arun(bot._cg_hold_room(ch, 461328, "2026-10-22")))
        self.assertEqual([c[0] for c in self.calls], ["should_hold"])

    def test_guard_falls_back_to_caller_lid_and_date(self):
        ch = _FakeChannel(cid=901, topic="")
        self.assertTrue(_arun(bot._cg_hold_room(ch, 461328, "2026-10-22 00:00")))
        self.assertEqual(self.calls[-1], ("defer_close", "461328", "2026-10-22", "901"))

    def test_guard_never_raises(self):
        def boom(lid, day):
            raise RuntimeError("db gone")
        bot._codegate.flow.should_hold = boom
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(_arun(bot._cg_hold_room(_FakeChannel(topic=self.KEY_TOPIC),
                                                     461328, "2026-10-22")))
        self.assertFalse(_arun(bot._cg_hold_room(None, 461328, "2026-10-22")))

    def test_guard_readies_codegate_before_the_list_check(self):
        order = []
        flow = bot._codegate.flow
        gated = flow.is_gated
        self.swap("_cg_ready", lambda: order.append("ready") or True)
        self.swap("is_gated", lambda lid: order.append("gated") or gated(lid), owner=flow)
        _arun(bot._cg_hold_room(_FakeChannel(topic=self.KEY_TOPIC), 461328, "2026-10-22"))
        self.assertEqual(order[:2], ["ready", "gated"])

    def test_guard_uses_codegate_pool_not_to_thread(self):
        import asyncio
        orig = asyncio.to_thread

        async def banned(*a, **k):
            raise AssertionError("asyncio.to_thread used")
        asyncio.to_thread = banned
        try:
            self.assertTrue(_arun(bot._cg_hold_room(_FakeChannel(topic=self.KEY_TOPIC),
                                                    461328, "2026-10-22")))
        finally:
            asyncio.to_thread = orig

    # ---- the three automatic delete sites ----

    def test_ready_close_site_guarded(self):
        ch = _FakeChannel(cid=900, topic=self.KEY_TOPIC)
        _arun(bot._ready_close_channel(None, 461328, "2026-10-22", "OujaCT: ready", ch))
        self.assertEqual(ch.deleted, [])
        self.recorded = False
        _arun(bot._ready_close_channel(None, 461328, "2026-10-22", "OujaCT: ready", ch))
        self.assertEqual(ch.deleted, ["OujaCT: ready"])

    def test_ready_close_site_guards_looked_up_room(self):
        tch = _FakeChannel(cid=902, topic=self.KEY_TOPIC)

        async def find(guild, lid, date_iso):
            return tch
        self.swap("_oujact_find_turnover_channel", find)
        _arun(bot._ready_close_channel(None, 461328, "2026-10-22", "r", _FakeChannel(topic="")))
        self.assertEqual(tch.deleted, [])
        self.assertEqual(self.calls[-1], ("defer_close", "461328", "2026-10-22", "902"))

    def _report(self):
        return {"status": "manager_approved", "apartment_id": 461328, "date": "2026-10-22",
                "report_id": "rp1"}

    def _approve_patches(self):
        self.swap("_cleanproof_find_by_discord_message", lambda mid: self._report())
        self.swap("_cleanproof_decide", lambda report, *a, **k: report)
        self.swap("_cleanproof_discord_embed", lambda report: None)

        async def summary(*a, **k):
            return None

        async def no_offer(*a, **k):
            return False
        self.swap("_cleanproof_send_approval_summary", summary)
        self.swap("_ready_offer", no_offer)
        self.swap("_oujact_mark_done", lambda key: None)

    def _interaction(self, ch):
        class Resp:
            async def edit_message(self, **k):
                pass

            async def send_message(self, *a, **k):
                pass

        class Follow:
            sent = []

            async def send(self, *a, **k):
                self.sent.append(a)
        return type("I", (), {"response": Resp(), "followup": Follow(), "channel": ch,
                              "guild": None, "user": "mgr",
                              "message": type("M", (), {"id": 1})()})()

    def test_discord_approve_site_guarded(self):
        self._approve_patches()
        ch = _FakeChannel(cid=900, topic=self.KEY_TOPIC)
        v = bot.CleaningProofReviewView()
        _arun(bot.CleaningProofReviewView.approve(v, self._interaction(ch), None))
        self.assertEqual(ch.deleted, [])
        self.assertEqual(self.calls[-1], ("defer_close", "461328", "2026-10-22", "900"))
        self.hold = False
        _arun(bot.CleaningProofReviewView.approve(v, self._interaction(ch), None))
        self.assertEqual(len(ch.deleted), 1)

    def test_discord_approve_site_guards_looked_up_room(self):
        self._approve_patches()
        tch = _FakeChannel(cid=903, topic=self.KEY_TOPIC)

        async def find(guild, lid, date_iso):
            return tch
        self.swap("_oujact_find_turnover_channel", find)
        v = bot.CleaningProofReviewView()
        _arun(bot.CleaningProofReviewView.approve(v, self._interaction(_FakeChannel(topic="")),
                                                  None))
        self.assertEqual(tch.deleted, [])
        self.assertEqual(self.calls[-1], ("defer_close", "461328", "2026-10-22", "903"))

    def test_dashboard_approve_site_guarded(self):
        self._approve_patches()
        tch = _FakeChannel(cid=904, topic=self.KEY_TOPIC)

        async def find(guild, lid, date_iso):
            return tch

        async def body(request):
            return {"report_id": "rp1", "decision": "approve", "by": "mgr"}
        self.swap("_oujact_find_turnover_channel", find)
        self.swap("_dash_auth", lambda request: True)
        self.swap("_read_body", body)
        self.swap("_cleanproof_report_view", lambda report: {})
        bot._cleaning_reports["rp1"] = self._report()
        self.addCleanup(lambda: bot._cleaning_reports.pop("rp1", None))
        _arun(bot._api_cleaning_report_decision(object()))
        self.assertEqual(tch.deleted, [])
        self.assertEqual(self.calls[-1], ("defer_close", "461328", "2026-10-22", "904"))
        self.hold = False
        _arun(bot._api_cleaning_report_decision(object()))
        self.assertEqual(len(tch.deleted), 1)


class TestDeferFirst(unittest.TestCase):
    """I4: answer Discord inside 3 s — defer before the thread-pool hop."""

    def _interaction(self, log):
        class Resp:
            done = False

            def is_done(self):
                return self.done

            async def defer(self, ephemeral=False, **k):
                log.append(("defer", ephemeral))
                self.done = True

            async def send_message(self, *a, **k):
                log.append(("send_message",))

        class Follow:
            def __init__(self):
                self.texts = []

            async def send(self, *a, **k):
                self.texts.append(a[0] if a else None)
                log.append(("followup", k.get("ephemeral")))

        msg = type("M", (), {"id": 4242})()
        return type("I", (), {"response": Resp(), "followup": Follow(), "message": msg,
                              "user": None, "guild": None})()

    def _run(self, coro_fn, item=None):
        import asyncio
        log = []
        flow = bot._codegate.flow
        saved = (flow.run_blocking, flow.press_send, flow.press_manual, flow.press_undo)

        async def rb(fn, *a, **k):
            log.append(("thread", getattr(fn, "__name__", "")))
            if fn is bot._codegate.db.item_by_message:
                return item
            return {"name": "x", "did": "1", "is_admin": True, "is_ops": False}

        def press(name):
            async def p(*a, **k):
                log.append(("press", name))
                return True, "ok"
            return p
        flow.run_blocking = rb
        flow.press_send, flow.press_manual, flow.press_undo = (press("send"), press("manual"),
                                                               press("undo"))
        try:
            asyncio.run(coro_fn(self._interaction(log)))
        finally:
            flow.run_blocking, flow.press_send, flow.press_manual, flow.press_undo = saved
        return log

    def test_confirm_send_defers_first(self):
        async def go(i):
            v = bot.CodegateConfirmView(4242, "send")
            await bot.CodegateConfirmView.yes(v, i, None)
        log = self._run(go)
        self.assertEqual(log[0], ("defer", True))
        self.assertEqual(log[1][0], "thread")
        self.assertEqual(log[2], ("press", "send"))
        self.assertEqual(log[-1], ("followup", True))

    def test_confirm_manual_defers_first(self):
        async def go(i):
            v = bot.CodegateConfirmView(4242, "manual")
            await bot.CodegateConfirmView.yes(v, i, None)
        log = self._run(go)
        self.assertEqual(log[0], ("defer", True))
        self.assertEqual(log[2], ("press", "manual"))
        self.assertEqual(log[-1], ("followup", True))

    def test_callbacks_always_answer(self):
        import asyncio
        flow = bot._codegate.flow
        cases = [("yes", lambda: bot.CodegateConfirmView.yes(bot.CodegateConfirmView(1, "send"),
                                                             self.i, None), "press_send"),
                 ("undo", lambda: bot.CodegateView.undo(bot.CodegateView(), self.i, None),
                  "press_undo"),
                 ("send", lambda: bot.CodegateView.send(bot.CodegateView(), self.i, None),
                  None)]
        for name, call, press in cases:
            with self.subTest(name=name):
                log = []
                self.i = self._interaction(log)
                saved = (flow.run_blocking, flow.press_send, flow.press_undo)

                async def rb(fn, *a, **k):
                    raise RuntimeError("secret 1234")

                async def ok_press(*a, **k):
                    return True, "ok"
                flow.run_blocking = rb
                flow.press_send = flow.press_undo = ok_press
                import contextlib
                import io
                out = io.StringIO()
                try:
                    with contextlib.redirect_stdout(out):
                        asyncio.run(call())
                finally:
                    flow.run_blocking, flow.press_send, flow.press_undo = saved
                self.assertEqual(log[0], ("defer", True))
                self.assertEqual(log[-1], ("followup", True))
                self.assertEqual(self.i.followup.texts[-1], "صار خطأ — جرّب مرة ثانية")
                self.assertIn("RuntimeError", out.getvalue())
                self.assertNotIn("1234", out.getvalue())

    def test_undo_defers_first(self):
        async def go(i):
            v = bot.CodegateView()
            await bot.CodegateView.undo(v, i, None)
        log = self._run(go)
        self.assertEqual(log[0], ("defer", True))
        self.assertEqual(log[1][0], "thread")
        self.assertEqual(log[2], ("press", "undo"))
        self.assertEqual(log[-1], ("followup", True))

    def _send_click(self, replies):
        texts = []
        orig = bot._cw_reply

        async def reply(interaction, message, view=None):
            texts.append((message, view))
        bot._cw_reply = reply
        try:
            async def go(i):
                await bot.CodegateView.send(bot.CodegateView(), i, None)
            log = self._run(go, item={"res_id": "r1", "replies": replies})
        finally:
            bot._cw_reply = orig
        return log, texts

    def test_send_click_reads_item_off_loop_and_asks_to_confirm(self):
        E = bot._codegate.engine
        log, texts = self._send_click([{"at": None, "text": "I agree"}])
        self.assertEqual(log[0], ("defer", True))
        self.assertEqual(log[1], ("thread", "item_by_message"))
        self.assertNotIn(("press", "send"), log)          # nothing sent before the confirm
        self.assertEqual(texts[0][0], E.CONFIRM_SEND)
        self.assertIsInstance(texts[0][1], bot.CodegateConfirmView)
        self.assertEqual(texts[0][1].kind, "send")

    def test_send_click_warns_when_verdict_not_yes(self):
        E = bot._codegate.engine
        for replies in ([], [{"at": None, "text": "what is the code?"}]):
            _, texts = self._send_click(replies)
            self.assertEqual(texts[0][0], E.CONFIRM_SEND_UNCLEAR)

    def test_manual_click_asks_to_confirm(self):
        texts = []
        orig = bot._cw_reply

        async def reply(interaction, message, view=None):
            texts.append((message, view))
        bot._cw_reply = reply
        try:
            async def go(i):
                await bot.CodegateView.manual(bot.CodegateView(), i, None)
            log = self._run(go)
        finally:
            bot._cw_reply = orig
        self.assertEqual(texts[0][0], bot._codegate.engine.CONFIRM_MANUAL)
        self.assertEqual(texts[0][1].kind, "manual")
        self.assertNotIn(("press", "manual"), log)


if __name__ == "__main__":
    unittest.main()
