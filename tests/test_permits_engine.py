# -*- coding: utf-8 -*-
"""
permits.engine — the pure rules. No database, no Discord, no clock.

What is locked here:
  * ONE band function, and its boundaries for lead 10 / 2 / 45.
  * plan(): ≤ lead (catch-up), never with a live ticket, never for an unknown date, only
    inside the open window, and the go-live sweep that lets expired permits through once.
  * reminders: once per day, at/after the hour, never twice.
  * the digest + card stay inside Discord's limits even with 300 permits and long text.
  * header mapping (Arabic / English / mixed / unknown → extra) and the unit matcher's
    unique-or-nothing rule.

Run: python3 -m unittest tests.test_permits_engine
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from permits import engine  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))


def at(iso, hour, minute=0):
    d = datetime.date.fromisoformat(iso)
    return datetime.datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ)


def cfg(**over):
    c = engine.cfg({})
    c.update(over)
    return c


def permit(pid, end, **over):
    p = {"id": pid, "permit_type": engine.SEED_TYPE, "permit_no": "5000%04d" % pid,
         "unit_text": "U%d" % pid, "end_date": end, "status": "active", "needs_data": 0,
         "lead_days": None, "holder": "مالك %d" % pid}
    p.update(over)
    return p


class TestBands(unittest.TestCase):

    def test_lead_10(self):
        want = {-1: "expired", 0: "urgent", 3: "urgent", 4: "due", 10: "due", 11: "upcoming",
                30: "upcoming", 31: "ok", None: "unknown"}
        for n, b in want.items():
            self.assertEqual(engine.band(n, 10, 30), b, n)

    def test_lead_2_has_no_due_band(self):
        want = {-1: "expired", 0: "urgent", 3: "urgent", 4: "upcoming", 10: "upcoming",
                11: "upcoming", 30: "upcoming", 31: "ok", None: "unknown"}
        for n, b in want.items():
            self.assertEqual(engine.band(n, 2, 30), b, n)

    def test_lead_45_swallows_upcoming(self):
        want = {-1: "expired", 0: "urgent", 3: "urgent", 4: "due", 10: "due", 11: "due",
                30: "due", 31: "due", 45: "due", 46: "ok", None: "unknown"}
        for n, b in want.items():
            self.assertEqual(engine.band(n, 45, 30), b, n)

    def test_needs_data_is_unknown_whatever_the_date(self):
        d = engine.describe(permit(1, "2026-10-05", needs_data=1), "2026-10-01", cfg())
        self.assertEqual(d["band"], "unknown")

    def test_alert_count(self):
        rows = [engine.describe(permit(i, e), "2026-10-01", cfg()) for i, e in enumerate(
            ["2026-09-20", "2026-10-02", "2026-10-08", "2026-10-20", "2027-01-01", None])]
        c = engine.counts(rows)
        self.assertEqual((c["expired"], c["urgent"], c["due"], c["upcoming"], c["ok"], c["unknown"]),
                         (1, 1, 1, 1, 1, 1))
        self.assertEqual(c["alert"], 4)
        self.assertEqual(c["total"], 6)

    def test_history_rows_are_not_counted(self):
        rows = [engine.describe(permit(1, "2026-09-01", status="renewed"), "2026-10-01", cfg())]
        self.assertEqual(engine.counts(rows)["total"], 0)

    def test_per_permit_lead_overrides(self):
        p = permit(1, "2026-10-21", lead_days=30)
        self.assertEqual(engine.describe(p, "2026-10-01", cfg())["band"], "due")
        self.assertTrue(engine.should_open(p, "2026-10-01", cfg()))


class TestPlan(unittest.TestCase):

    def plan(self, permits, now, live=(), **kw):
        return engine.plan(permits, set(live), now, cfg(), **kw)

    def test_opens_at_exactly_lead(self):
        p = self.plan([permit(1, "2026-10-12")], at("2026-10-02", 13))
        self.assertEqual(p["open"], [1])

    def test_does_not_open_at_lead_plus_one(self):
        p = self.plan([permit(1, "2026-10-12")], at("2026-10-01", 13))
        self.assertEqual(p["open"], [])

    def test_catch_up_opens_an_expired_permit(self):
        p = self.plan([permit(1, "2026-09-26")], at("2026-10-01", 13))
        self.assertEqual(p["open"], [1])

    def test_never_opens_with_a_live_ticket(self):
        p = self.plan([permit(1, "2026-10-05")], at("2026-10-01", 13), live=[1])
        self.assertEqual(p["open"], [])

    def test_unknown_dates_never_open(self):
        p = self.plan([permit(1, None, needs_data=1), permit(2, None)], at("2026-10-01", 13))
        self.assertEqual(p["open"], [])
        self.assertEqual(sorted(p["unknown"]), [1, 2])

    def test_history_rows_never_open(self):
        p = self.plan([permit(1, "2026-10-05", status="renewed"),
                       permit(2, "2026-10-05", status="cancelled")], at("2026-10-01", 13))
        self.assertEqual(p["open"], [])

    def test_quiet_hours_hold_then_release(self):
        ps = [permit(1, "2026-10-05")]
        night = self.plan(ps, at("2026-10-01", 23, 30))
        self.assertEqual(night["open"], [])
        self.assertEqual(night["waiting"], [1])
        early = self.plan(ps, at("2026-10-02", 8, 55))
        self.assertEqual(early["open"], [])
        morning = self.plan(ps, at("2026-10-02", 9, 0))
        self.assertEqual(morning["open"], [1])

    def test_go_live_sweep_lets_expired_through_quiet_hours_once(self):
        ps = [permit(1, "2026-09-20"), permit(2, "2026-10-05")]
        p = self.plan(ps, at("2026-10-01", 23), golive_sweep=True)
        self.assertEqual(p["open"], [1])         # expired only — the due one still waits
        self.assertEqual(p["waiting"], [2])

    def test_catch_up_at_23_59_and_00_01(self):
        ps = [permit(1, "2026-10-12")]
        self.assertEqual(self.plan(ps, at("2026-10-01", 23, 59))["open"], [])
        self.assertEqual(self.plan(ps, at("2026-10-02", 0, 1))["waiting"], [1])


class TestReminders(unittest.TestCase):

    def test_once_per_day_at_or_after_the_hour(self):
        c = cfg()
        t = {"id": 7, "state": "open", "last_reminder_date": None}
        self.assertFalse(engine.reminder_due(t, at("2026-10-01", 12, 59), c))
        self.assertTrue(engine.reminder_due(t, at("2026-10-01", 13, 0), c))
        t["last_reminder_date"] = "2026-10-01"
        self.assertFalse(engine.reminder_due(t, at("2026-10-01", 20), c))
        self.assertFalse(engine.reminder_due(t, at("2026-10-02", 12), c))
        self.assertTrue(engine.reminder_due(t, at("2026-10-02", 13), c))

    def test_only_open_tickets(self):
        for st in ("opening", "closed", "lost"):
            self.assertFalse(engine.reminder_due({"state": st}, at("2026-10-01", 14), cfg()))

    def test_summary_due_latch(self):
        self.assertFalse(engine.summary_due(at("2026-10-01", 12), None, 13))
        self.assertTrue(engine.summary_due(at("2026-10-01", 13), None, 13))
        self.assertFalse(engine.summary_due(at("2026-10-01", 18), "2026-10-01", 13))
        self.assertTrue(engine.summary_due(at("2026-10-02", 13), "2026-10-01", 13))

    def test_escalation_mentions_by_band(self):
        c = cfg(ping_role_id=555, escalate_ids=[9, 10])
        self.assertEqual(engine.reminder_mentions("due", "42", c), (["42"], []))
        self.assertEqual(engine.reminder_mentions("urgent", "42", c), (["42"], ["555"]))
        self.assertEqual(engine.reminder_mentions("expired", "42", c), (["42", "9", "10"], []))
        self.assertEqual(engine.reminder_mentions("urgent", "", cfg(ping_role_id=0)), ([], []))

    def test_reminder_tone(self):
        c = cfg()
        p = permit(1, "2026-10-07")
        t = {"id": 3, "claimed_by": "", "claimed_at": None}
        self.assertIn("باقي 6 أيام", engine.reminder_text(p, t, "2026-10-01", c, "U1"))
        self.assertIn("ينتهي **اليوم**", engine.reminder_text(permit(1, "2026-10-01"), t, "2026-10-01", c, "U1"))
        self.assertIn("🔴 منتهي من 3 أيام", engine.reminder_text(permit(1, "2026-09-28"), t, "2026-10-01", c, "U1"))

    def test_a_claim_is_shown_but_never_silences(self):
        t = {"id": 3, "claimed_by": "ناصر", "claimed_at": "2026-09-29T10:00:00"}
        txt = engine.reminder_text(permit(1, "2026-10-07"), t, "2026-10-01", cfg(), "U1")
        self.assertIn("ناصر", txt)
        self.assertIn("وش وضع التجديد", txt)


class TestDayWords(unittest.TestCase):

    def test_left_text(self):
        self.assertEqual(engine.left_text(10), "باقي 10 أيام")
        self.assertEqual(engine.left_text(1), "باقي يوم واحد")
        self.assertEqual(engine.left_text(2), "باقي يومين")
        self.assertEqual(engine.left_text(21), "باقي 21 يوم")
        self.assertEqual(engine.left_text(0), "ينتهي اليوم")
        self.assertEqual(engine.left_text(-3), "منتهي من 3 أيام")
        self.assertEqual(engine.left_text(None), "تاريخ الانتهاء غير معروف")


class TestChannelNaming(unittest.TestCase):

    def test_name_and_topic(self):
        self.assertEqual(engine.channel_name(7, "Ouja | Hue 9"), "تصريح-007-hue-9")
        self.assertEqual(engine.topic(12, 7, "2026-10-12"), "ouja-permit: pid:12 tid:7 end:2026-10-12")
        self.assertEqual(engine.parse_topic("ouja-permit: pid:12 tid:7 end:2026-10-12"), (12, 7))
        self.assertIsNone(engine.parse_topic("ouja-ticket:maint lid:5"))

    def test_arabic_only_names_keep_arabic_and_stay_short(self):
        n = engine.channel_name(3, "العارض ـ ابو ماجد")
        self.assertTrue(n.startswith("تصريح-003-"))
        self.assertIn("العارض", n)
        self.assertLessEqual(len(n.split("-", 2)[2]), 40)

    def test_empty_slug_falls_back(self):
        self.assertEqual(engine.channel_name(3, "|||"), "تصريح-003-permit")


class TestCard(unittest.TestCase):

    def test_core_fields_and_footer(self):
        p = permit(4, "2026-10-12", doc_url="https://drive.google.com/x", district="العليا",
                   street="الامير", building_no="7813", unit_no="2", ownership_kind="ملكية شخصية",
                   issuer="وزارة السياحة", start_date="2025-10-12", holder_id_last4="1234")
        card = engine.ticket_card(p, 9, "2026-10-02", cfg(), unit_name="Ouja | F2",
                                  responsible="<@1>", dashboard_url="https://x/dashboard#permits")
        names = [f[0] for f in card["fields"]]
        for want in ("🏷️ النوع", "🔢 الرقم", "🏠 الشقة/المبنى", "👤 باسم", "📍 العنوان",
                     "📎 التصريح الحالي", "📅 النهاية", "⏳ المتبقي", "🛠️ طريقة التجديد",
                     "👷 المسؤول", "🔗 الداشبورد"):
            self.assertIn(want, names)
        self.assertEqual(card["footer"], "permit:4 · ticket:9")
        self.assertIn("#009", card["title"])
        blob = repr(card)
        self.assertNotIn("1234", blob, "the ID last-4 must never reach Discord")
        self.assertIn("نفاذ", blob)                  # the type default renewal note shows

    def test_urgent_content_prefix(self):
        card = engine.ticket_card(permit(4, "2026-10-02"), 9, "2026-10-01", cfg(),
                                  responsible="<@1>")
        self.assertTrue(card["content"].startswith("🚨 **عاجل** ·"))

    def test_limits_with_many_extras_and_long_text(self):
        extras = {("حقل %d" % i): ("ق" * 3000) for i in range(40)}
        import json
        p = permit(4, "2026-10-12", notes="ن" * 5000, renew_notes="ر" * 5000,
                   extra_json=json.dumps(extras, ensure_ascii=False))
        card = engine.ticket_card(p, 9, "2026-10-02", cfg(), responsible="<@1>",
                                  dashboard_url="https://x")
        self.assertLessEqual(len(card["fields"]), 25)
        for name, value, _inline in card["fields"]:
            self.assertLessEqual(len(name), 256)
            self.assertLessEqual(len(value), 1024)
        self.assertIn("معلومات إضافية", [f[0] for f in card["fields"]])
        self.assertEqual(card["fields"][-1][0], "🔗 الداشبورد")   # never pushed out
        self.assertLessEqual(engine.embed_size(card), 6000)

    def test_review_issues_show(self):
        import json
        p = permit(4, "2026-10-12", review_issues=json.dumps(
            [{"code": "dup_permit_no", "text_ar": "رقم التصريح مكرر"},
             {"code": "x", "text_ar": "تمت", "cleared_at": "2026-10-01"}], ensure_ascii=False))
        card = engine.ticket_card(p, 9, "2026-10-02", cfg())
        vals = dict((f[0], f[1]) for f in card["fields"])
        self.assertIn("رقم التصريح مكرر", vals["⚠️ تحتاج مراجعة"])
        self.assertNotIn("تمت", vals["⚠️ تحتاج مراجعة"])

    def test_replacement_note(self):
        card = engine.ticket_card(permit(4, "2026-10-12"), 9, "2026-10-02", cfg(), replaced_tid=5)
        self.assertIn("#005 انحذفت", card["description"])


class TestDigest(unittest.TestCase):

    def row(self, pid, end, ticket=None, **over):
        r = engine.describe(permit(pid, end, **over), "2026-10-01", cfg())
        r["unit_name"] = "Ouja | U%d" % pid
        r["ticket"] = ticket
        r["resp_name"] = "مسؤول"
        r["resp_id"] = "77%d" % pid
        return r

    def test_all_clear_is_one_line(self):
        chunks, mentions = engine.digest_messages([self.row(1, "2026-12-01"), self.row(2, "2027-01-01")],
                                                  "2026-10-01", cfg())
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].count("\n"), 0)
        self.assertIn("✅ كل التصاريح سليمة", chunks[0])
        self.assertIn("بعد 61 يوم", chunks[0])
        self.assertEqual(mentions, [])

    def test_mixed_blocks_and_mentions_only_for_expired_and_urgent(self):
        rows = [self.row(1, "2026-09-28", ticket={"id": 4, "channel_id": "900", "state": "open",
                                                  "claimed_by": "فهد"}),
                self.row(2, "2026-10-02", ticket={"id": 5, "channel_id": "901", "state": "open"}),
                self.row(3, "2026-10-07", ticket={"id": 6, "channel_id": "902", "state": "open"}),
                self.row(4, "2026-10-22"),
                self.row(5, None, needs_data=1, end_date_raw="١٥/١٣/١٤٤٨"),
                self.row(6, "2027-05-01")]
        chunks, mentions = engine.digest_messages(
            rows, "2026-10-01", cfg(),
            problems=[{"tid": 9, "error": "Missing Permissions"}],
            renewed=[{"permit_type": "رخصة بلدية", "unit_name": "Ouja | X", "by": "ناصر"}])
        text = "\n".join(chunks)
        self.assertIn("📋 تقرير التصاريح اليومي — الخميس 1 أكتوبر 2026", text)
        self.assertIn("🔴 منتهية: 1", text)
        self.assertIn("🟠 تحتاج تجديد (≤10 أيام): 2", text)
        self.assertIn("🟡 قريبة (≤30): 1", text)
        self.assertIn("⚪ ناقصة بيانات: 1", text)
        self.assertIn("🟢 سليمة: 1", text)
        self.assertIn("<#900>", text)
        self.assertIn("مستلمة من فهد", text)
        self.assertIn("لم يستلمها أحد", text)
        self.assertIn("«١٥/١٣/١٤٤٨»", text)
        self.assertIn("Missing Permissions", text)
        self.assertIn("✅ تجدّد أمس", text)
        self.assertEqual(sorted(mentions), ["771", "772"])     # expired + urgent only
        self.assertIn("<@771>", text)
        self.assertNotIn("<@773>", text)                        # due → name only, no ping

    def test_300_permits_split_under_2000(self):
        rows = [self.row(i, "2026-10-%02d" % (2 + i % 25), notes="x" * 50,
                         permit_type="نوع طويل " * 5) for i in range(300)]
        chunks, _m = engine.digest_messages(rows, "2026-10-01", cfg())
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 2000)
        self.assertEqual(sum(c.count("\n• ") + c.startswith("• ") for c in chunks), 300)


class TestHeaders(unittest.TestCase):

    def test_seed_headers(self):
        hs = ["م", "اسم الوحدة", "ملف التصريح", "رقم التصريح", "اسم المصرح له",
              "تاريخ الإصدار (هجري)", "تاريخ الإنتهاء (هجري)", "رقم الهوية", "الحي", "الشارع",
              "رقم المبنى", "رقم الوحدة", "نوع العقار"]
        got = [engine.map_header(h) for h in hs]
        self.assertEqual([g[0] for g in got],
                         ["serial", "unit_text", "doc", "permit_no", "holder", "start_date",
                          "end_date", "holder_id", "district", "street", "building_no",
                          "unit_no", "ownership_kind"])
        self.assertEqual(got[5][1], "hijri")
        self.assertEqual(got[6][1], "hijri")

    def test_english_and_mixed(self):
        self.assertEqual(engine.map_header("Expiry")[0], "end_date")
        self.assertEqual(engine.map_header("Valid From")[0], "start_date")
        self.assertEqual(engine.map_header("Licence No")[0], "permit_no")
        self.assertEqual(engine.map_header("Iqama")[0], "holder_id")
        self.assertEqual(engine.map_header("تاريخ الانتهاء (ميلادي)"), ("end_date", "gregorian"))
        self.assertEqual(engine.map_header("Apartment")[0], "unit_text")

    def test_unknown_header_is_none(self):
        self.assertEqual(engine.map_header("لون الباب")[0], None)

    def test_detect_header_row_skips_a_title(self):
        rows = [["شركة عوجا — تصاريح", None, None],
                ["م", "اسم الوحدة", "تاريخ الإنتهاء (هجري)"],
                [1, "F2", "01/05/1448"]]
        self.assertEqual(engine.detect_header_row(rows), 1)

    def test_id_headers(self):
        for h in ("رقم الهوية", "السجل المدني", "الإقامة", "National ID", "iqama", "ID Number"):
            self.assertTrue(engine.is_id_header(h), h)
        self.assertFalse(engine.is_id_header("رقم الوحدة"))

    def test_guessed_end_column(self):
        rows = [["F2", "2025-10-12", "2026-10-12"], ["A5", "2025-11-24", "2026-11-24"]]
        self.assertEqual(engine.guess_date_columns(rows, [0, 1, 2]), (1, 2))
        self.assertEqual(engine.guess_date_columns([["a", "b"]], [0, 1]), (None, None))


class TestUnitMatch(unittest.TestCase):
    L = [
        {"id": 1, "internal_name": "Ouja | Hue 9", "public_name": "Lovely flat", "active": True},
        {"id": 2, "internal_name": "Ouja | F2", "public_name": "", "active": True},
        {"id": 3, "internal_name": "C2 NFL", "public_name": "", "active": True},
        {"id": 4, "internal_name": "C2 Arid", "public_name": "", "active": True},
        {"id": 5, "internal_name": "A5 MLQ", "public_name": "", "active": True},
        {"id": 6, "internal_name": "عرقة E15", "public_name": "", "active": True},
        {"id": 7, "internal_name": "Old unit", "public_name": "", "active": False},
    ]

    def test_exact(self):
        self.assertEqual(engine.match_unit("F2", self.L)[0], 2)

    def test_brand_prefix_and_spacing(self):
        self.assertEqual(engine.match_unit("hue  9", self.L)[0], 1)
        self.assertEqual(engine.match_unit("Ouja | Hue-9", self.L)[0], 1)

    def test_reordered_words_still_match_one_unit(self):
        self.assertEqual(engine.match_unit("E15 عرقه", self.L)[0], 6)

    def test_unique_contains(self):
        lid, how = engine.match_unit("Hue", self.L)[:2]
        self.assertEqual((lid, how), (1, "contains"))

    def test_ambiguous_is_no_match(self):
        lid, how, cands = engine.match_unit("C2", self.L, hint="")
        self.assertIsNone(lid)
        self.assertEqual(sorted(cands), [3, 4])

    def test_the_seed_hint_settles_c2_al_nafl(self):
        """«C2» alone is two apartments; the reviewed hint (c2-nfl) picks the one in النفل."""
        self.assertEqual(engine.match_unit("C2", self.L), (3, "hint", [3]))

    def test_hint_only_when_unique(self):
        self.assertEqual(engine.match_unit("A5", self.L, hint="a5-mlq")[0], 5)
        self.assertIsNone(engine.match_unit("Zz", self.L, hint="c2")[0])

    def test_inactive_listings_are_not_candidates(self):
        self.assertIsNone(engine.match_unit("Old unit", self.L)[0])

    def test_norm(self):
        self.assertEqual(engine.norm_unit("Ouja | العارض ـ أبو ماجد"), "العارض ابو ماجد")
        self.assertEqual(engine.slug_unit("Hue 9"), "hue-9")


class TestConfig(unittest.TestCase):

    def test_defaults(self):
        c = engine.cfg({})
        self.assertEqual((c["lead_days"], c["headsup_days"], c["daily_hour"], c["open_from"],
                          c["open_to"], c["tick_min"]), (10, 30, 13, 9, 22, 5))
        self.assertEqual(c["digest_channel"], "تنبيهات-التصاريح")
        self.assertFalse(c["force_dry"])
        self.assertIsNone(c["escalate_ids"])

    def test_garbled_ints_fall_back(self):
        c = engine.cfg({"PERMITS_LEAD_DAYS": "ten", "PERMITS_DAILY_HOUR": "99",
                        "PERMITS_ESCALATE_IDS": "12, x ,34", "PERMITS_FORCE_DRY": "1"})
        self.assertEqual(c["lead_days"], 10)
        self.assertEqual(c["daily_hour"], 13)
        self.assertEqual(c["escalate_ids"], [12, 34])
        self.assertTrue(c["force_dry"])

    def test_env_is_read_at_call_time(self):
        os.environ["PERMITS_LEAD_DAYS"] = "14"
        try:
            self.assertEqual(engine.cfg()["lead_days"], 14)
        finally:
            del os.environ["PERMITS_LEAD_DAYS"]
        self.assertEqual(engine.cfg()["lead_days"], 10)


if __name__ == "__main__":
    unittest.main()
