# -*- coding: utf-8 -*-
"""
«متابعة الخروج» — the PURE rules: the clock, the late-exit cap, risk levels and the wording.

Everything here runs with an injected `now`, no database, no Discord, no network.

Run: python3 -m unittest tests.test_checkout_watch_engine
"""

import datetime
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from checkout import engine, texts   # noqa: E402

TZ = engine.tz()
DAY = "2026-09-26"


def at(hh, mm=0, day=26):
    return datetime.datetime(2026, 9, day, hh, mm, tzinfo=TZ)


def row(**kw):
    base = {"work_key": "101:" + DAY, "day": DAY, "unit": "Ouja | الملقا 1",
            "guest": "Sara Ahmed", "responsible": "ناصر", "responsible_did": "111",
            "checkout_at": engine.iso(at(12)), "checkin_at": None, "clean_minutes": 40,
            "state": engine.WAITING, "remind_count": 0, "airbnb_sent": 0}
    base.update(kw)
    return base


DL = engine.deadline_at(DAY, "17:00")


class TestTheClock(unittest.TestCase):

    def test_ping_exactly_at_checkout_not_before(self):
        r = row()
        self.assertIsNone(engine.due_action(r, at(11, 59)))
        self.assertEqual(engine.due_action(r, at(12, 0)), "ping")
        self.assertEqual(engine.due_action(row(state=engine.ASKING), at(12, 0)), "ping")

    def test_no_second_ping(self):
        r = row(state=engine.ASKING, pinged_at=engine.iso(at(12)),
                next_action_at=engine.iso(at(12, 30)))
        self.assertIsNone(engine.due_action(r, at(12, 29)))

    def test_reminders_every_thirty_minutes_after_no_answer(self):
        r = row(state=engine.NO_ANSWER, pinged_at=engine.iso(at(12)),
                next_action_at=engine.iso(at(12, 40)))
        self.assertIsNone(engine.due_action(r, at(12, 39)))
        self.assertEqual(engine.due_action(r, at(12, 40)), "remind")
        r["next_action_at"] = engine.iso(at(13, 10))          # the flow moves it +30
        self.assertIsNone(engine.due_action(r, at(13, 9)))
        self.assertEqual(engine.due_action(r, at(13, 10)), "remind")

    def test_nothing_after_an_answer(self):
        for st in (engine.OUT, engine.CLEANED, engine.APPROVED):
            r = row(state=st, pinged_at=engine.iso(at(12)), next_action_at=engine.iso(at(12, 30)))
            for t in (at(12, 30), at(13), at(16)):
                self.assertIsNone(engine.due_action(r, t), (st, t))

    def test_quiet_hours_23_to_08(self):
        r = row(state=engine.NO_ANSWER, pinged_at=engine.iso(at(12)),
                next_action_at=engine.iso(at(22, 50)))
        self.assertEqual(engine.due_action(r, at(22, 59)), "remind")
        self.assertIsNone(engine.due_action(r, at(23, 0)))
        self.assertIsNone(engine.due_action(r, at(3, 0, day=27)))
        self.assertIsNone(engine.due_action(r, at(7, 59, day=27)))
        self.assertEqual(engine.due_action(r, at(8, 0, day=27)), "remind")
        self.assertTrue(engine.in_quiet(at(23, 30)))
        self.assertFalse(engine.in_quiet(at(12, 0)))

    def test_demo_ignores_quiet_hours(self):
        r = row(state=engine.WAITING, checkout_at=engine.iso(at(23, 10)))
        self.assertIsNone(engine.due_action(r, at(23, 30)))
        self.assertEqual(engine.due_action(r, at(23, 30), demo=True), "ping")

    def test_reask_at_expected_exit(self):
        r = row(state=engine.INSIDE, pinged_at=engine.iso(at(12)),
                expected_out_at=engine.iso(at(14)), reason_code="packing")
        self.assertIsNone(engine.due_action(r, at(13, 59)))
        self.assertEqual(engine.due_action(r, at(14, 0)), "reask")

    def test_surprise_inside_without_time_is_reminded(self):
        r = row(state=engine.INSIDE, pinged_at=engine.iso(at(12)), reason_code="surprise",
                next_action_at=engine.iso(at(13)))
        self.assertEqual(engine.due_action(r, at(13)), "remind")

    def test_initial_state(self):
        self.assertEqual(engine.initial_state(at(12), at(9)), engine.WAITING)
        self.assertEqual(engine.initial_state(at(12), at(12, 5)), engine.ASKING)


class TestTheCap(unittest.TestCase):

    def test_latest_ok_exit_with_checkin(self):
        self.assertEqual(engine.latest_ok_exit(at(15), DL, 40), at(14, 20))

    def test_latest_ok_exit_checkin_after_deadline_uses_17(self):
        self.assertEqual(engine.latest_ok_exit(at(20), DL, 40), at(16, 20))

    def test_latest_ok_exit_without_checkin(self):
        self.assertEqual(engine.latest_ok_exit(None, DL, 60), at(16, 0))

    def test_red_cap_flag(self):
        self.assertTrue(engine.red_cap(at(15, 30), at(16), DL, 40))     # 15:30 > 15:20
        self.assertFalse(engine.red_cap(at(15, 20), at(16), DL, 40))
        self.assertFalse(engine.red_cap(None, at(16), DL, 40))
        r = row(state=engine.INSIDE, checkin_at=engine.iso(at(16)),
                expected_out_at=engine.iso(at(15, 30)), reason_code="late_ask")
        line = texts.cap_line(r, DL)
        self.assertIn("15:20", line)
        self.assertIn("🔴", line)
        self.assertEqual(texts.cap_line(dict(r, expected_out_at=engine.iso(at(14))), DL), "")

    def test_expected_exit_is_validated_never_guessed(self):
        now = at(13, 7)
        self.assertEqual(engine.expected_from_choice("1h", now), (at(14, 7), None))
        self.assertEqual(engine.expected_from_choice("custom", now, "15:30"), (at(15, 30), None))
        self.assertEqual(engine.expected_from_choice("custom", now, "١٥:٣٠"), (at(15, 30), None))
        self.assertEqual(engine.expected_from_choice("custom", now, "12:00")[1], "past")
        self.assertEqual(engine.expected_from_choice("custom", now, "3pm")[1], "format")
        self.assertEqual(engine.expected_from_choice("custom", now, "25:00")[1], "format")
        self.assertEqual(engine.expected_from_choice("3h", at(22, 0))[1], "tomorrow")
        self.assertEqual(engine.expected_from_choice("bogus", now)[1], "choice")


class TestRisk(unittest.TestCase):

    def lvl(self, r, now, **kw):
        return engine.risk(r, now, DL, **kw)

    def test_red_inside_with_checkin(self):
        r = row(state=engine.INSIDE, checkin_at=engine.iso(at(16)),
                expected_out_at=engine.iso(at(13)))
        self.assertEqual(self.lvl(r, at(12, 30)), (engine.RED, "inside_checkin"))

    def test_red_noanswer_with_checkin(self):
        r = row(state=engine.NO_ANSWER, checkin_at=engine.iso(at(16)))
        self.assertEqual(self.lvl(r, at(12, 30)), (engine.RED, "noanswer_checkin"))

    def test_red_slack_negative(self):
        # out at 14:50, check-in 15:00, 40 min cleaning → −30
        r = row(state=engine.OUT, checkin_at=engine.iso(at(15)))
        self.assertEqual(self.lvl(r, at(14, 50)), (engine.RED, "slack_negative"))

    def test_red_after_17(self):
        r = row(state=engine.OUT)
        self.assertEqual(self.lvl(r, at(17, 0)), (engine.RED, "past_deadline"))

    def test_red_surprise(self):
        r = row(state=engine.OUT)
        self.assertEqual(self.lvl(r, at(12, 30), surprise_today=True), (engine.RED, "surprise"))

    def test_orange_unconfirmed_after_checkout_with_checkin(self):
        r = row(state=engine.ASKING, pinged_at=engine.iso(at(12)), checkin_at=engine.iso(at(16)))
        self.assertEqual(self.lvl(r, at(12, 10)), (engine.ORANGE, "unconfirmed_checkin"))

    def test_orange_slack_under_60(self):
        # no check-in; out now at 15:40 → 17:00 − 15:40 − 40 = 40 min
        r = row(state=engine.OUT)
        self.assertEqual(self.lvl(r, at(15, 40)), (engine.ORANGE, "slack_low"))

    def test_orange_early_checkin_approved(self):
        r = row(state=engine.OUT)
        self.assertEqual(self.lvl(r, at(12, 10), early_checkin=True),
                         (engine.ORANGE, "early_checkin"))

    def test_green(self):
        self.assertEqual(self.lvl(row(state=engine.OUT), at(12, 10)), (engine.GREEN, "ok"))
        self.assertEqual(self.lvl(row(), at(9)), (engine.GREEN, "ok"))

    def test_done(self):
        self.assertEqual(self.lvl(row(state=engine.APPROVED), at(18)), (engine.DONE, "done"))


class TestReport(unittest.TestCase):

    def test_person_report(self):
        items = [row(work_key="1:" + DAY, responsible="ناصر"),
                 row(work_key="2:" + DAY, responsible="ناصر"),
                 row(work_key="3:" + DAY, responsible="نورة")]
        ev = [
            {"work_key": "1:" + DAY, "at": engine.iso(at(12, 10)), "kind": "yes", "actor": "ناصر", "detail": ""},
            {"work_key": "1:" + DAY, "at": engine.iso(at(15)), "kind": "approved", "actor": "", "detail": ""},
            {"work_key": "2:" + DAY, "at": engine.iso(at(12, 30)), "kind": "noanswer", "actor": "ناصر", "detail": ""},
            {"work_key": "2:" + DAY, "at": engine.iso(at(13)), "kind": "remind", "actor": "", "detail": ""},
            {"work_key": "2:" + DAY, "at": engine.iso(at(13, 30)), "kind": "remind", "actor": "", "detail": ""},
            {"work_key": "3:" + DAY, "at": engine.iso(at(12, 5)), "kind": "yes", "actor": "نورة", "detail": ""},
            {"work_key": "3:" + DAY, "at": engine.iso(at(13)), "kind": "surprise", "actor": "خالد", "detail": "نورة"},
            {"work_key": "3:" + DAY, "at": engine.iso(at(18)), "kind": "approved", "actor": "", "detail": ""},
        ]
        rep = {r["name"]: r for r in engine.person_report(items, ev, lambda d: DL)}
        self.assertEqual(rep["ناصر"]["turnovers"], 2)
        self.assertEqual(rep["ناصر"]["median_answer_min"], 20)          # 10 and 30
        self.assertEqual(rep["ناصر"]["noanswer"], 1)
        self.assertEqual(rep["ناصر"]["reminders"], 2)
        self.assertEqual(rep["ناصر"]["on_time_pct"], 50)
        self.assertEqual(rep["نورة"]["surprises"], 1)                   # attributed to the ✅ presser
        self.assertEqual(rep["نورة"]["on_time_pct"], 0)                  # approved 18:00


class TestTexts(unittest.TestCase):

    GUESTS = ("Sara Ahmed", "محمد 2231", "Guest 4455 | Airbnb", "", None, "٣٣ خالد")

    def test_guest_bodies_have_no_digits(self):
        for g in self.GUESTS:
            for body in (texts.airbnb_body(g), texts.airbnb_body(g, second=True),
                         texts.wa_text(g, "ناصر"), texts.wa_text(g, "Agent 007")):
                self.assertFalse(any(c.isdigit() for c in body), (g, body))

    def test_second_airbnb_body_differs(self):
        self.assertNotEqual(texts.airbnb_body("Sara"), texts.airbnb_body("Sara", second=True))

    def test_guest_bodies_have_no_readiness_words(self):
        for body in (texts.airbnb_body("Sara"), texts.wa_text("Sara", "ناصر")):
            for w in ("جاهز", "ready", "نظيفة", "مرتبة", "is clean"):
                self.assertNotIn(w, body.lower())

    def _all_team_strings(self):
        rows = [row(state=s, state_by="ناصر", state_at=engine.iso(at(12, 40)),
                    pinged_at=engine.iso(at(12)), checkin_at=engine.iso(at(16)),
                    expected_out_at=engine.iso(at(15, 30)), reason_code=c, reason_text="ملاحظة",
                    airbnb_note=texts.airbnb_failed("firewall_blocked"), channel_id="555")
                for s in engine.STATES for c in (engine.REASON_CODES + ("surprise",))]
        out = []
        for r in rows:
            c = texts.card(r, DL, hint=True)
            out += [texts.embed_text(c), texts.ping(r), texts.remind(r, 2, 60),
                    texts.reask(r), texts.reask_now(r), texts.surprise_post(r),
                    texts.board_line(r), texts.state_line(r), texts.reply_taken(r)]
            for k in ("yes", "noanswer", "no", "surprise"):
                out.append(texts.reply_saved(k, r))
            for lvl, code in (("red", "inside_checkin"), ("orange", "slack_low"), ("green", "ok")):
                out.append(texts.risk_line(r, lvl, code, DL))
        out += [texts.YES_POST, texts.BEFORE_OUT, texts.board_header(at(12)), texts.BOARD_EMPTY,
                texts.summary(5, 3, ["A", "B"]), texts.summary(2, 2, []),
                texts.risk_header(5, 2, {"red": 1}), texts.start_summary(3, 1, 1, ["X"]),
                texts.STOP_REPLY, texts.ADMIN_ONLY, texts.WA_REPLY, texts.WA_NO_PHONE,
                texts.WA_DEMO, texts.REPLY_NOT_FOUND, texts.REPLY_NOANSWER_AGAIN,
                texts.airbnb_sent_line(1), texts.airbnb_sent_line(2),
                texts.demo_airbnb_preview(texts.airbnb_body("x"))]
        out += list(texts.REASONS_AR.values()) + list(texts.EXPECT_AR.values())
        out += list(texts.EXPECT_ERRORS.values()) + list(texts.BUTTON_LABELS.values())
        out.append(texts.DEMO_READY)
        return out

    def test_team_strings_carry_no_money(self):
        for s in self._all_team_strings():
            for w in ("ريال", "ر.س", "SAR"):
                self.assertNotIn(w, s, s)

    def test_demo_card_looks_exactly_like_a_real_card(self):
        real = texts.card(row(), DL)
        demo = texts.card(row(demo=1), DL)
        self.assertEqual(real, demo)
        self.assertNotIn("تجربة", demo["title"])

    def test_demo_rooms_do_not_give_away_the_scenario(self):
        for name, _scen, _unit in texts.DEMO_CHANNELS:
            for w in ("طلع", "رد", "مفاجأة"):
                self.assertNotIn(w, name or "")

    def test_card_uses_the_turnover_card_layout(self):
        r = row(checkin_at=engine.iso(at(16)), responsible_emoji="🟡", responsible="عهود")
        c = texts.card(r, DL)
        self.assertEqual(c["title"], "🚪 متابعة الخروج")
        names = [f["name"] for f in c["fields"]]
        self.assertEqual(names, ["الضيف", "الخروج", "الدخول", "المسؤول", "الحالة"])
        self.assertEqual([f["inline"] for f in c["fields"]], [True, True, True, False, False])
        vals = {f["name"]: f["value"] for f in c["fields"]}
        self.assertEqual(vals["الخروج"], "12:00 PM")
        self.assertEqual(vals["الدخول"], "🔴 04:00 PM")
        self.assertEqual(vals["المسؤول"], "🟡 عهود")
        self.assertEqual(c["footer"]["text"], texts.CARD_FOOTER)
        self.assertEqual(texts.card(row(), DL)["fields"][2]["value"], "ما فيه دخول اليوم")

    def test_plan_and_alert_boxes_only_when_needed(self):
        inside = row(state=engine.INSIDE, checkin_at=engine.iso(at(16)), reason_code="late_ask",
                     expected_out_at=engine.iso(at(15, 30)), state_by="ناصر")
        f = {x["name"]: x["value"] for x in texts.card(inside, DL)["fields"]}
        self.assertIn("أقصى تأخير نقدر نعطيه 15:20", f["الخطة"])
        self.assertIn("🔴 لو طلع 15:30", f["الخطة"])
        self.assertNotIn("تنبيه", f)
        alerted = texts.card(row(airbnb_note="⚠️ x"), DL, hint=True)
        f = {x["name"]: x["value"] for x in alerted["fields"]}
        self.assertIn("💡", f["تنبيه"])
        self.assertIn("⚠️ x", f["تنبيه"])
        self.assertNotIn("footer", texts.card(row(state=engine.APPROVED), DL))

    def test_field_values_are_never_empty_or_too_long(self):
        for st in engine.STATES:
            for fld in texts.card(row(state=st, guest="", responsible="", reason_code="other",
                                      reason_text="x" * 2000), DL)["fields"]:
                self.assertTrue(fld["value"].strip())
                self.assertLessEqual(len(fld["value"]), 1024)

    def test_state_line_names_who_and_when(self):
        r = row(state=engine.OUT, state_by="ناصر", state_at=engine.iso(at(12, 40)))
        self.assertIn("أكده ناصر 12:40", texts.state_line(r))
        self.assertIn("الشقة جاهزة للتنظيف", texts.embed_text(texts.card(r, DL)))

    def test_mentions(self):
        self.assertEqual(texts.who(row(responsible_did="111")), "<@111>")
        self.assertEqual(texts.who(row(responsible_did="role:9")), "<@&9>")
        self.assertEqual(texts.who(row(responsible_did="", responsible="ناصر")), "ناصر")

    def test_ping_text(self):
        t = texts.ping(row(guest="Sara"))
        self.assertTrue(t.startswith("<@111> 🚪 وقت خروج **Sara**"))
        self.assertIn("(12:00). طلع الضيف؟", t)

    def test_wa_link_encodes(self):
        u = texts.wa_link("wa.me/966501234567", texts.wa_text("Sara", "ناصر"))
        self.assertTrue(u.startswith("https://wa.me/966501234567?text="))
        self.assertNotIn(" ", u)
        self.assertTrue(texts.wa_link("", "hi").startswith("https://wa.me/?text="))

    def test_no_backslash_escapes_in_long_literals(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "checkout", "texts.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertEqual(len(re.findall(r"\\n", src)), 1)       # only NL = "\n"


def tearDownModule():
    # bot.py prints at import; flush before unittest writes its summary so the LAST line of
    # the run is the verdict (GATES.md G3 reads only that line).
    sys.stdout.flush()


if __name__ == "__main__":
    unittest.main()
