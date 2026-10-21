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

    def test_view_custom_ids_are_persistent(self):
        v = bot.CodegateView()
        ids = sorted(c.custom_id for c in v.children)
        self.assertEqual(ids, ["cg_release", "cg_undo"])
        self.assertIsNone(v.timeout)

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
        v = bot._cg_view(["release"])
        self.assertIsInstance(v, bot.CodegateView)
        self.assertEqual([c.custom_id for c in v.children], ["cg_release"])
        # decorator buttons carry an INSTANCE callback; a bare Button keeps the base no-op
        self.assertIn("callback", vars(v.children[0]))
        self.assertEqual(v.children[0].callback.callback.__name__, "release")
        self.assertIsNone(v.timeout)
        u = bot._cg_view(["undo"])
        self.assertEqual([c.custom_id for c in u.children], ["cg_undo"])
        self.assertEqual(sorted(c.custom_id for c in bot._cg_view(["release", "undo"]).children),
                         ["cg_release", "cg_undo"])
        self.assertEqual(list(bot._cg_view([]).children), [])

    def test_click_dispatches_to_real_callback(self):
        import asyncio
        import discord
        from types import SimpleNamespace as NS
        from discord.ui.view import ViewStore

        async def go():
            store = ViewStore(NS())
            store.add_view(bot.CodegateView(), None)        # bot.add_view at boot
            store.add_view(bot._cg_view(["release"]), 111)  # what ch.send(view=) does
            key = (discord.ComponentType.button.value, "cg_release")
            item = store._views.get(111, {}).get(key) or store._views.get(None, {}).get(key)
            return item

        item = asyncio.new_event_loop().run_until_complete(go())
        self.assertIsNotNone(item)
        self.assertIsInstance(item.view, bot.CodegateView)
        self.assertIn("callback", vars(item))
        self.assertEqual(item.callback.callback.__name__, "release")

    def test_button_labels_match_engine(self):
        v = bot.CodegateView()
        labels = {c.custom_id: c.label for c in v.children}
        self.assertEqual(labels["cg_release"], bot._codegate.engine.LABEL_RELEASE)
        self.assertEqual(labels["cg_undo"], bot._codegate.engine.LABEL_UNDO)

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
            async def send(self, *a, **k):
                log.append(("followup", k.get("ephemeral")))

        msg = type("M", (), {"id": 4242})()
        return type("I", (), {"response": Resp(), "followup": Follow(), "message": msg,
                              "user": None, "guild": None})()

    def _run(self, coro_fn):
        import asyncio
        log = []
        flow = bot._codegate.flow
        saved = (flow.run_blocking, flow.press_release, flow.press_undo)

        async def rb(fn, *a, **k):
            log.append(("thread",))
            return {"name": "x", "did": "1", "is_admin": True, "is_ops": False}

        async def press(*a, **k):
            return True, "ok"
        flow.run_blocking, flow.press_release, flow.press_undo = rb, press, press
        try:
            asyncio.run(coro_fn(self._interaction(log)))
        finally:
            flow.run_blocking, flow.press_release, flow.press_undo = saved
        return log

    def test_yes_defers_first(self):
        view_cls = bot.CodegateConfirmView

        async def go(i):
            v = view_cls(4242)
            await view_cls.yes(v, i, None)
        log = self._run(go)
        self.assertEqual(log[0], ("defer", True))
        self.assertEqual(log[1], ("thread",))
        self.assertEqual(log[-1], ("followup", True))

    def test_undo_defers_first(self):
        async def go(i):
            v = bot.CodegateView()
            await bot.CodegateView.undo(v, i, None)
        log = self._run(go)
        self.assertEqual(log[0], ("defer", True))
        self.assertEqual(log[1], ("thread",))
        self.assertEqual(log[-1], ("followup", True))


if __name__ == "__main__":
    unittest.main()
