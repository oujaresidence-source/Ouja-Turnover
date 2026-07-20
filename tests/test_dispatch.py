import unittest
from datetime import datetime
import bot


class TestDispatchFormatters(unittest.TestCase):
    def test_fmt_date_arabic_weekday(self):
        # 2026-07-22 is a Wednesday
        self.assertEqual(bot._dispatch_fmt_date("2026-07-22"), "الأربعاء 22/7")

    def test_fmt_time_am_pm(self):
        noon = datetime(2026, 7, 22, 12, 0, tzinfo=bot.TZ)
        morning = datetime(2026, 7, 22, 9, 5, tzinfo=bot.TZ)
        afternoon = datetime(2026, 7, 22, 15, 30, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_fmt_time(noon), "12:00 م")
        self.assertEqual(bot._dispatch_fmt_time(morning), "9:05 ص")
        self.assertEqual(bot._dispatch_fmt_time(afternoon), "3:30 م")


class TestDispatchResolveDate(unittest.TestCase):
    def test_auto_before_noon_is_today(self):
        now = datetime(2026, 7, 21, 9, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date(None, now=now), "2026-07-21")

    def test_auto_after_noon_is_tomorrow(self):
        now = datetime(2026, 7, 21, 14, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date(None, now=now), "2026-07-22")

    def test_explicit_today_tomorrow(self):
        now = datetime(2026, 7, 21, 14, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date("today", now=now), "2026-07-21")
        self.assertEqual(bot._dispatch_resolve_date("tomorrow", now=now), "2026-07-22")

    def test_explicit_iso_date(self):
        now = datetime(2026, 7, 21, 14, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date("2026-08-01", now=now), "2026-08-01")

    def test_garbage_falls_back_to_auto(self):
        now = datetime(2026, 7, 21, 9, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date("banana", now=now), "2026-07-21")


class TestDispatchText(unittest.TestCase):
    def _items(self):
        return [
            {"lid": 1, "listing": "Ouja | الملقا 1",
             "checkout": datetime(2026, 7, 22, 12, 0, tzinfo=bot.TZ),
             "checkin_today": True, "checkin_dt": datetime(2026, 7, 22, 15, 0, tzinfo=bot.TZ),
             "early_departure": False},
            {"lid": 2, "listing": "Ouja | جود 13",
             "checkout": datetime(2026, 7, 22, 11, 0, tzinfo=bot.TZ),
             "checkin_today": False, "checkin_dt": None,
             "early_departure": True},
        ]

    def test_wa_text_structure(self):
        txt = bot._dispatch_wa_text("الملقا", "2026-07-22", self._items())
        self.assertIn("تنظيف — فريق الملقا", txt)
        self.assertIn("عدد الشقق: 2", txt)
        self.assertIn("الأربعاء 22/7", txt)
        self.assertIn("Ouja | الملقا 1", txt)
        self.assertIn("دخول اليوم 3:00 م (عاجل)", txt)   # same-day check-in flagged
        self.assertIn("الضيف طلع بدري", txt)             # early departure flagged
        self.assertIn("الرجاء تأكيد الاستلام", txt)

    def test_wa_text_empty(self):
        txt = bot._dispatch_wa_text("X", "2026-07-22", [])
        self.assertIn("عدد الشقق: 0", txt)

    def test_embed_lines_include_owner(self):
        covers = {1: {"name": "ناصر", "emoji": "🟢"}, 2: {"name": "عهود", "emoji": "🟡"}}
        lines = bot._dispatch_embed_lines(self._items(), covers)
        self.assertEqual(len(lines), 2)
        self.assertIn("ناصر", lines[0])
        self.assertIn("🔴", lines[0])   # same-day check-in marker on the card
        self.assertIn("⚡", lines[1])    # early-departure marker on the card


class TestWaSendUrl(unittest.TestCase):
    def test_with_phone(self):
        url = bot._wa_send_url("0501234567", "مرحبا")
        self.assertTrue(url.startswith("https://wa.me/966501234567?text="))
        self.assertIn("%D9%85", url)   # arabic is percent-encoded

    def test_without_phone_uses_contact_picker(self):
        url = bot._wa_send_url("", "hello world")
        self.assertTrue(url.startswith("https://api.whatsapp.com/send?text="))
        self.assertNotIn(" ", url)     # spaces encoded

    def test_newlines_encoded(self):
        url = bot._wa_send_url("", "line1\nline2")
        self.assertIn("line1%0Aline2", url)


class TestDispatchGroup(unittest.TestCase):
    def test_group_and_unassigned(self):
        items = [
            {"lid": 1, "listing": "A"},
            {"lid": 2, "listing": "B"},
            {"lid": 3, "listing": "C"},  # no crew -> unassigned
        ]
        team_of = {1: "t1", 2: "t2", 3: ""}
        jobs = bot._dispatch_group(items, team_of)
        self.assertEqual([it["lid"] for it in jobs["teams"]["t1"]], [1])
        self.assertEqual([it["lid"] for it in jobs["teams"]["t2"]], [2])
        self.assertEqual([it["lid"] for it in jobs["unassigned"]], [3])

    def test_group_preserves_order_within_team(self):
        items = [{"lid": 1, "listing": "A"}, {"lid": 2, "listing": "B"}]
        team_of = {1: "t1", 2: "t1"}
        jobs = bot._dispatch_group(items, team_of)
        self.assertEqual([it["lid"] for it in jobs["teams"]["t1"]], [1, 2])


if __name__ == "__main__":
    unittest.main()
