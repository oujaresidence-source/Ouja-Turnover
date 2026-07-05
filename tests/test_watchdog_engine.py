# -*- coding: utf-8 -*-
"""watchdog.engine — TDD lock: code classifier, the Aseel automation rule, flag
computation + severities, phone-first renderers (line caps), scoreboard math."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watchdog import engine as E

NOW = datetime(2026, 7, 5, 13, 0)


def msg(body, incoming=0, sender="نورة", ts="2026-07-05T10:00:00"):
    m = {"body": body, "isIncoming": incoming, "date": ts}
    if sender:
        m["user"] = {"name": sender}
    return m


class TestCodeClassifier(unittest.TestCase):
    def test_finds_code_message(self):
        msgs = [msg("هلا! كود الباب 4512 حياك"), msg("welcome", sender="")]
        r = E.classify_code_send(msgs)
        self.assertTrue(r["found"])
        self.assertEqual(r["sender"], "نورة")
        self.assertEqual(r["sent_at"], "2026-07-05T10:00:00")

    def test_ignores_inbound_and_codeless(self):
        msgs = [msg("الكود وش هو؟ 4512", incoming=1), msg("أهلين بك")]
        self.assertFalse(E.classify_code_send(msgs)["found"])

    def test_number_without_keyword_not_code(self):
        self.assertFalse(E.classify_code_send([msg("السعر 4500 ريال")])["found"])

    def test_unknown_sender_still_found(self):
        r = E.classify_code_send([msg("door code 88123", sender="")])
        self.assertTrue(r["found"])
        self.assertEqual(r["sender"], "")

    def test_newest_wins(self):
        msgs = [msg("كود الباب 1111", ts="2026-07-04T09:00:00", sender="محمد"),
                msg("الكود الجديد 2222", ts="2026-07-05T08:00:00", sender="نورة")]
        r = E.classify_code_send(msgs)
        self.assertEqual(r["sender"], "نورة")


class TestAutomationFP(unittest.TestCase):
    def test_normalize_strips_digits_and_greeting_name(self):
        a = E.normalize_body("مرحبا أحمد، تسجيل الخروج الساعة 11 صباحاً غرفة 12")
        b = E.normalize_body("مرحبا سارة، تسجيل الخروج الساعة 11 صباحاً غرفة 7")
        self.assertEqual(a, b)
        self.assertTrue(a)

    def test_fp_stable(self):
        self.assertEqual(E.body_fp("Hello Ahmed, checkout at 11 AM"),
                         E.body_fp("Hello Omar, checkout at 11 AM"))

    def test_recurring_same_clock_is_automated(self):
        rec = {"n": 4, "convs": ["a", "b", "c", "d"], "minutes": [660, 662, 659, 661]}
        self.assertTrue(E.fp_is_automated(rec))

    def test_varied_or_single_conv_not_automated(self):
        self.assertFalse(E.fp_is_automated({"n": 2, "convs": ["a", "b"], "minutes": [600, 900]}))
        self.assertFalse(E.fp_is_automated({"n": 5, "convs": ["a"], "minutes": [660] * 5}))
        self.assertFalse(E.fp_is_automated({"n": 4, "convs": ["a", "b", "c", "d"],
                                            "minutes": [300, 660, 900, 1200]}))
        self.assertFalse(E.fp_is_automated(None))


def snap(**kw):
    base = {"arrivals": [], "escalations": [], "pending": [], "promises": [],
            "tickets": [], "cleaning_stale": [],
            "coverage": {"ok": True, "off_names": [], "imbalance": 0},
            "today": {"arr_n": 0, "dep_n": 0, "occupied": 0, "tight_n": 0},
            "codes_summary": {"manual_total": 0, "sent": 0},
            "health": {"disk_fallback": False, "api_ok": True},
            "errors": []}
    base.update(kw)
    return base


def arrival(**kw):
    a = {"unit": "Ouja | A", "guest": "خالد", "listing_id": "7", "hours_until": 2.0,
         "code_mode": "manual", "code_found": False, "code_sender": "",
         "cleaning_ok": True, "employee": "نورة", "arrival_date": "2026-07-05"}
    a.update(kw)
    return a


class TestFlags(unittest.TestCase):
    def test_manual_code_missing_soon_is_critical(self):
        flags = E.compute_flags(snap(arrivals=[arrival()]), NOW)
        crit = [f for f in flags if f["severity"] == "critical"]
        self.assertEqual(len(crit), 1)
        self.assertEqual(crit[0]["key"], "code:7:2026-07-05")
        self.assertIn("نورة", crit[0]["text"])
        self.assertEqual(crit[0]["mention_name"], "نورة")

    def test_manual_code_missing_later_is_warn(self):
        flags = E.compute_flags(snap(arrivals=[arrival(hours_until=8.0)]), NOW)
        f = [x for x in flags if x["key"].startswith("code:")][0]
        self.assertEqual(f["severity"], "warn")

    def test_manual_code_sent_no_flag(self):
        flags = E.compute_flags(snap(arrivals=[arrival(code_found=True, code_sender="نورة")]), NOW)
        self.assertEqual([f for f in flags if f["key"].startswith("code:")], [])

    def test_auto_code_never_flags(self):
        flags = E.compute_flags(snap(arrivals=[arrival(code_mode="auto")]), NOW)
        self.assertEqual([f for f in flags if f["key"].startswith("code:")], [])

    def test_cleaning_not_ready_soon_critical(self):
        flags = E.compute_flags(
            snap(arrivals=[arrival(code_mode="auto", cleaning_ok=False, hours_until=1.5)]), NOW)
        f = [x for x in flags if x["key"].startswith("clean:")][0]
        self.assertEqual(f["severity"], "critical")

    def test_escalation_thresholds(self):
        s = snap(escalations=[{"guest": "g", "unit": "u", "age_min": 130, "id": "9"}])
        f = [x for x in E.compute_flags(s, NOW) if x["key"] == "esc:9"][0]
        self.assertEqual(f["severity"], "critical")
        s2 = snap(escalations=[{"guest": "g", "unit": "u", "age_min": 50, "id": "9"}])
        f2 = [x for x in E.compute_flags(s2, NOW) if x["key"] == "esc:9"][0]
        self.assertEqual(f2["severity"], "warn")
        s3 = snap(escalations=[{"guest": "g", "unit": "u", "age_min": 10, "id": "9"}])
        self.assertEqual([x for x in E.compute_flags(s3, NOW) if x["key"] == "esc:9"], [])

    def test_promise_expired_critical_overdue_warn(self):
        s = snap(promises=[{"promised_by": "محمد", "apartment": "A", "id": "p1",
                            "expired": True, "overdue_h": 30.0},
                           {"promised_by": "سارة", "apartment": "B", "id": "p2",
                            "expired": False, "overdue_h": 2.0}])
        flags = E.compute_flags(s, NOW)
        self.assertEqual([x for x in flags if x["key"] == "prom:p1"][0]["severity"], "critical")
        self.assertEqual([x for x in flags if x["key"] == "prom:p2"][0]["severity"], "warn")

    def test_health_flags(self):
        s = snap(health={"disk_fallback": True, "api_ok": False})
        keys = {f["key"] for f in E.compute_flags(s, NOW)}
        self.assertIn("health:disk", keys)
        self.assertIn("health:api", keys)

    def test_critical_sorted_first(self):
        s = snap(arrivals=[arrival()],
                 escalations=[{"guest": "g", "unit": "u", "age_min": 50, "id": "9"}])
        flags = E.compute_flags(s, NOW)
        self.assertEqual(flags[0]["severity"], "critical")


class TestRender(unittest.TestCase):
    def test_green_summary_compact(self):
        txt = E.render_summary([], snap(
            today={"arr_n": 5, "dep_n": 3, "occupied": 41, "tight_n": 1},
            codes_summary={"manual_total": 2, "sent": 2}), "3:30 م")
        lines = txt.splitlines()
        self.assertLessEqual(len(lines), 6)
        self.assertIn("🟢", lines[0])
        self.assertIn("41", txt)
        self.assertIn("2/2", txt)

    def test_flag_summary_caps_and_header(self):
        flags = ([{"key": "k%d" % i, "severity": "critical",
                   "text": "🔑 كود ما انرسل: شقة %d" % i, "mention_name": ""} for i in range(10)])
        txt = E.render_summary(flags, snap(), "3:30 م")
        lines = txt.splitlines()
        self.assertIn("🔴", lines[0])
        self.assertLessEqual(len(lines), 12)
        self.assertIn("أخرى", txt)

    def test_warn_only_header_yellow(self):
        flags = [{"key": "k", "severity": "warn", "text": "🟡 تصعيد قديم", "mention_name": ""}]
        txt = E.render_summary(flags, snap(), "3:30 م")
        self.assertIn("🟡", txt.splitlines()[0])

    def test_unknown_section_rendered(self):
        txt = E.render_summary([], snap(errors=["cleaning"]), "3:30 م")
        self.assertIn("غير معروف", txt)


class TestScoreboard(unittest.TestCase):
    def test_board_math_and_exclusions(self):
        stats = [{"employee": "نورة", "replies": 30, "resp_min_sum": 300.0,
                  "resp_min_n": 30, "automations_skipped": 0},
                 {"employee": "أسيل", "replies": 20, "resp_min_sum": 400.0,
                  "resp_min_n": 20, "automations_skipped": 28}]
        sends = [{"sent_by": "نورة", "on_time": 1}, {"sent_by": "نورة", "on_time": 0},
                 {"sent_by": "", "on_time": 1}]
        promises = [{"promised_by": "نورة", "status": "done"},
                    {"promised_by": "نورة", "status": "expired"}]
        board = E.scoreboard(stats, sends, promises, [{"claimed_by_name": "أسيل"}])
        by = {b["name"]: b for b in board}
        self.assertEqual(by["نورة"]["replies"], 30)
        self.assertEqual(by["نورة"]["resp_avg"], 10)
        self.assertEqual(by["نورة"]["codes_on_time"], 1)
        self.assertEqual(by["نورة"]["codes_total"], 2)
        self.assertEqual(by["نورة"]["kept_pct"], 50)
        self.assertEqual(by["أسيل"]["automations_skipped"], 28)
        self.assertEqual(by["أسيل"]["esc_claims"], 1)
        self.assertNotIn("", by)  # unknown sender never gets a row

    def test_render_scoreboard_lines(self):
        board = E.scoreboard(
            [{"employee": "نورة", "replies": 3, "resp_min_sum": 30.0,
              "resp_min_n": 3, "automations_skipped": 0}], [], [], [])
        txt = E.render_scoreboard(board)
        self.assertIn("🏆", txt)
        self.assertIn("نورة", txt)


if __name__ == "__main__":
    unittest.main()
