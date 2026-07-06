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
    # Owner rule 2026-07-05: the unit door code is ANY digits ending with «#».
    # A code marked «خارجي» is the building/gate code — NOT the unit code.
    def test_finds_hash_code(self):
        msgs = [msg("هلا! كود الدخول 4512# حياك"), msg("welcome", sender="")]
        r = E.classify_code_send(msgs)
        self.assertTrue(r["found"])
        self.assertEqual(r["sender"], "نورة")
        self.assertEqual(r["sent_at"], "2026-07-05T10:00:00")

    def test_hash_code_without_keyword_still_counts(self):
        self.assertTrue(E.classify_code_send([msg("اهلا فيك: 88123#")])["found"])

    def test_digits_without_hash_not_code(self):
        self.assertFalse(E.classify_code_send([msg("كود الباب 4512 حياك")])["found"])
        self.assertFalse(E.classify_code_send([msg("السعر 4500 ريال")])["found"])

    def test_external_code_alone_not_counted(self):
        self.assertFalse(E.classify_code_send([msg("الكود الخارجي 1234#")])["found"])
        self.assertFalse(E.classify_code_send([msg("كود البوابة الخارجية: 9999#")])["found"])

    def test_external_plus_unit_code_counts(self):
        r = E.classify_code_send([msg("الكود الخارجي 1234# وكود الشقة 5678#")])
        self.assertTrue(r["found"])

    def test_ignores_inbound(self):
        msgs = [msg("وش الكود؟ 4512#", incoming=1), msg("أهلين بك")]
        self.assertFalse(E.classify_code_send(msgs)["found"])

    def test_unknown_sender_still_found(self):
        r = E.classify_code_send([msg("door code 88123#", sender="")])
        self.assertTrue(r["found"])
        self.assertEqual(r["sender"], "")

    def test_newest_wins(self):
        msgs = [msg("كود الباب 1111#", ts="2026-07-04T09:00:00", sender="محمد"),
                msg("الكود الجديد 2222#", ts="2026-07-05T08:00:00", sender="نورة")]
        r = E.classify_code_send(msgs)
        self.assertEqual(r["sender"], "نورة")

    def test_hash_before_digits_rtl_order(self):
        # RTL typing stores «#335533» though the phone DISPLAYS «335533#»
        self.assertTrue(E.classify_code_send([msg("كود دخول الشقة: #335533")])["found"])

    def test_bidi_control_chars_between_digits_and_hash(self):
        # Airbnb inserts invisible direction marks (RLM/LRM) around the «#»
        body = "كود دخول الشقة: 335533" + chr(0x200F) + "#"
        self.assertTrue(E.classify_code_send([msg(body)])["found"])

    def test_noura_real_message_c08(self):
        # The literal C08 MJ message the watchdog missed live (2026-07-05, IMG_7095)
        body = ("أهلاً وسهلاً بك في بيتك الثاني 🏡\n\n"
                "المبنى C\n"
                "كود المبنى الخارجي:\n"
                "9999#111111\n\n"
                "كود دخول الشقة:\n\n"
                "335533#\n\n"
                "نتمنى لك إقامة مريحة\n\n"
                "Wi-Fi: Ouja residence\n"
                "Password: Ouja1234")
        r = E.classify_code_send([msg(body, sender="Noura")])
        self.assertTrue(r["found"])
        self.assertEqual(r["sender"], "Noura")

    def test_noura_message_rtl_logical_variant(self):
        # same message if the stored logical order flips both codes
        body = ("المبنى C\n"
                "كود المبنى الخارجي:\n"
                "111111#9999\n\n"
                "كود دخول الشقة:\n\n"
                "#335533")
        self.assertTrue(E.classify_code_send([msg(body)])["found"])

    def test_external_only_still_excluded_both_orders(self):
        self.assertFalse(E.classify_code_send([msg("كود المبنى الخارجي: #9999")])["found"])
        self.assertFalse(E.classify_code_send([msg("كود المبنى الخارجي: 9999#")])["found"])


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

    def test_arrived_guest_missing_code_text_and_severity(self):
        flags = E.compute_flags(snap(arrivals=[arrival(hours_until=-4.5, arrived=True)]), NOW)
        f = [x for x in flags if x["key"].startswith("code:")][0]
        self.assertEqual(f["severity"], "critical")
        self.assertIn("واصل من", f["text"])

    def test_late_sent_code_no_flag_but_tagged_in_embeds(self):
        s = snap(arrivals=[arrival(code_found=True, code_sender="نورة", code_late=True,
                                   hours_until=-2.0, arrived=True)])
        flags = E.compute_flags(s, NOW)
        self.assertEqual([f for f in flags if f["key"].startswith("code:")], [])
        embeds = E.render_embeds(flags, s, "10:00 م")
        arr = [e for e in embeds if "وصول" in e["title"]][0]
        self.assertIn("متأخر", arr["desc"])

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

    def test_escalation_kind_labels(self):
        s = snap(escalations=[
            {"guest": "g1", "unit": "u1", "age_min": 130, "id": "b", "kind": "booking"},
            {"guest": "g2", "unit": "u2", "age_min": 130, "id": "i", "kind": "inquiry"},
            {"guest": "g3", "unit": "u3", "age_min": 130, "id": "x"}])
        flags = {f["key"]: f for f in E.compute_flags(s, NOW)}
        self.assertIn("حجز مؤكد", flags["esc:b"]["text"])
        self.assertEqual(flags["esc:b"]["kind"], "booking")
        self.assertIn("استفسار", flags["esc:i"]["text"])
        self.assertEqual(flags["esc:i"]["kind"], "inquiry")
        self.assertNotIn("استفسار", flags["esc:x"]["text"])
        self.assertNotIn("حجز مؤكد", flags["esc:x"]["text"])
        self.assertEqual(flags["esc:x"]["kind"], "")

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


def arrival_full(**kw):
    a = arrival()
    a.update({"time_label": "15:00", "nights": 3, "price": 1450, "signed": True,
              "open_tickets": 1})
    a.update(kw)
    return a


class TestStaleFilter(unittest.TestCase):
    def test_stale_pending_excluded_from_flags(self):
        s = snap(pending=[{"id": "old", "guest": "g", "unit": "u", "age_min": 58265},
                          {"id": "new", "guest": "g2", "unit": "u2", "age_min": 90}])
        keys = {f["key"] for f in E.compute_flags(s, NOW)}
        self.assertNotIn("pend:old", keys)
        self.assertIn("pend:new", keys)

    def test_stale_escalation_excluded(self):
        s = snap(escalations=[{"id": "old", "guest": "g", "unit": "u", "age_min": 9000}])
        self.assertEqual([f for f in E.compute_flags(s, NOW) if f["key"].startswith("esc:")], [])


class TestEmbeds(unittest.TestCase):
    def full_snap(self):
        return snap(
            arrivals=[arrival_full()],
            today={"arr_n": 1, "dep_n": 2, "occupied": 27, "tight_n": 0},
            departures=[{"unit": "Ouja | B", "guest": "سعد", "employee": "أسيل"}],
            coverage={"ok": True, "off_names": ["مها"], "imbalance": 1,
                      "working": [{"name": "نورة", "emoji": "🦁", "n": 14}]},
            pending=[{"id": "old", "guest": "g", "unit": "u", "age_min": 58265}],
            codes_summary={"manual_total": 1, "sent": 0})

    def test_embeds_structure_and_header(self):
        s = self.full_snap()
        flags = E.compute_flags(s, NOW)
        embeds = E.render_embeds(flags, s, "6:30 م")
        self.assertLessEqual(len(embeds), 10)
        for e in embeds:
            self.assertIn(e["color"], ("red", "gold", "green", "gray"))
            self.assertLessEqual(len(e["desc"]), 3900)
        self.assertEqual(embeds[0]["color"], "red")   # manual code missing at 2h → critical

    def test_arrival_line_has_everything(self):
        s = self.full_snap()
        embeds = E.render_embeds(E.compute_flags(s, NOW), s, "6:30 م")
        arr = [e for e in embeds if "وصول" in e["title"]][0]
        d = arr["desc"]
        for needle in ("خالد", "Ouja | A", "15:00", "نورة", "3 ليال", "1450", "تذكرة"):
            self.assertIn(needle, d)

    def test_archive_line_present(self):
        s = self.full_snap()
        embeds = E.render_embeds(E.compute_flags(s, NOW), s, "6:30 م")
        conv = [e for e in embeds if "محادثات" in e["title"]][0]
        self.assertIn("أرشيف قديم: 1", conv["desc"])

    def test_pending_dup_count_rendered(self):
        s = snap(pending=[{"id": "a", "guest": "Ghada", "unit": "FD1",
                           "age_min": 90, "n": 7}])
        embeds = E.render_embeds(E.compute_flags(s, NOW), s, "6:30 م")
        conv = [e for e in embeds if "محادثات" in e["title"]][0]
        self.assertIn("7 رسائل", conv["desc"])

    def test_conversation_lines_capped(self):
        many = [{"id": str(i), "guest": "g%d" % i, "unit": "u", "age_min": 100}
                for i in range(30)]
        s = snap(pending=many)
        embeds = E.render_embeds(E.compute_flags(s, NOW), s, "6:30 م")
        conv = [e for e in embeds if "محادثات" in e["title"]][0]
        self.assertLessEqual(len(conv["desc"].splitlines()), 16)
        self.assertIn("أخرى", conv["desc"])

    def test_coverage_and_departure_embeds(self):
        s = self.full_snap()
        embeds = E.render_embeds(E.compute_flags(s, NOW), s, "6:30 م")
        cov = [e for e in embeds if "توزيع" in e["title"]][0]
        self.assertIn("نورة", cov["desc"])
        self.assertIn("14", cov["desc"])
        self.assertIn("مها", cov["desc"])
        dep = [e for e in embeds if "مغادرات" in e["title"]][0]
        self.assertIn("أسيل", dep["desc"])

    def test_green_snap_single_status_color(self):
        s = snap(today={"arr_n": 0, "dep_n": 0, "occupied": 30, "tight_n": 0})
        embeds = E.render_embeds([], s, "6:30 م")
        self.assertEqual(embeds[0]["color"], "green")

    def test_errors_detail_surfaced(self):
        s = snap(errors=["promises"], errors_detail={"promises": "database is locked"})
        embeds = E.render_embeds([], s, "6:30 م")
        joined = " ".join(e["desc"] for e in embeds)
        self.assertIn("غير معروف", joined)
        self.assertIn("database is locked", joined)


class TestCompact(unittest.TestCase):
    def test_compact_short_with_top_criticals_and_link(self):
        s = snap(arrivals=[arrival()],
                 today={"arr_n": 15, "dep_n": 24, "occupied": 28, "tight_n": 11},
                 codes_summary={"manual_total": 8, "sent": 3})
        flags = E.compute_flags(s, NOW)
        c = E.render_compact(flags, s, "6:56 م", "https://oujares.com/watchdog")
        self.assertEqual(c["color"], "red")
        lines = c["desc"].splitlines()
        self.assertLessEqual(len(lines), 10)
        self.assertIn("15", c["desc"])
        self.assertIn("كود ما انرسل", c["desc"])
        self.assertIn("oujares.com/watchdog", c["desc"])

    def test_compact_green(self):
        s = snap(today={"arr_n": 2, "dep_n": 1, "occupied": 30, "tight_n": 0})
        c = E.render_compact([], s, "9:00 ص", "")
        self.assertEqual(c["color"], "green")
        self.assertIn("كل شي تمام", c["title"])

    def test_compact_caps_criticals_at_three(self):
        flags = [{"key": "k%d" % i, "severity": "critical",
                  "text": "🔴 مشكلة %d" % i, "mention_name": ""} for i in range(9)]
        c = E.render_compact(flags, snap(), "6:00 م", "")
        self.assertIn("+6", c["desc"])


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
