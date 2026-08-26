# -*- coding: utf-8 -*-
"""
Lead v2 (plan Task 8): the reservation card's fields, the honeypot, and the
phone a Saudi guest actually types.

Run: python3 -m unittest tests.test_cp_lead_v2
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cp import routes  # noqa: E402
from tests.test_cp_admin import make_client, _Disk  # noqa: E402


class CleanLead(unittest.TestCase):
    def test_mode_and_slot_whitelisted(self):
        d = routes.clean_lead({"name": "خالد", "phone": "0551234567",
                               "mode": "office", "slot": "eve"})
        self.assertEqual(d["mode"], "office")
        self.assertEqual(d["slot"], "eve")

    def test_unknown_mode_slot_coerced_to_defaults(self):
        d = routes.clean_lead({"name": "خالد", "mode": "<script>", "slot": "3am"})
        self.assertEqual(d["mode"], "online")
        self.assertEqual(d["slot"], "am")

    def test_phone_normalises_arabic_indic_digits(self):
        d = routes.clean_lead({"name": "x", "phone": "٠٥٥١٢٣٤٥٦٧"})
        self.assertEqual(d["phone"], "966551234567")

    def test_phone_normalises_eastern_arabic_indic(self):
        d = routes.clean_lead({"name": "x", "phone": "۰۵۵۱۲۳۴۵۶۷"})
        self.assertEqual(d["phone"], "966551234567")

    def test_phone_leading_zero_becomes_966(self):
        d = routes.clean_lead({"name": "x", "phone": "0551234567"})
        self.assertEqual(d["phone"], "966551234567")

    def test_phone_with_country_code_kept(self):
        d = routes.clean_lead({"name": "x", "phone": "+966 55 123 4567"})
        self.assertEqual(d["phone"], "966551234567")

    def test_phone_too_short_dropped(self):
        d = routes.clean_lead({"name": "x", "phone": "12345"})
        self.assertNotIn("phone", d)

    def test_bare_9_digit_number_gets_country_code(self):
        d = routes.clean_lead({"name": "x", "phone": "551234567"})
        self.assertEqual(d["phone"], "966551234567")


class HttpSurface(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.notified = []
        self.disk = _Disk()
        self.client, _ = make_client(self.loop, disk=self.disk)
        # rewire notify to capture
        from cp.host import HOST
        HOST.notify = self.notified.append
        routes._recent.clear()

    def tearDown(self):
        self.loop.run_until_complete(self.client.close())
        self.loop.close()

    def post(self, payload):
        return self.loop.run_until_complete(
            self.client.post("/api/cp/lead", json=payload))

    def test_full_lead_stores_mode_and_slot(self):
        r = self.post({"name": "خالد", "phone": "٠٥٥١٢٣٤٥٦٧",
                       "audience": "investor", "mode": "office", "slot": "pm"})
        self.assertEqual(r.status, 200)
        lead = self.disk.data["cp_leads.json"]["leads"][0]
        self.assertEqual(lead["fields"]["mode"], "office")
        self.assertEqual(lead["fields"]["slot"], "pm")
        self.assertEqual(lead["fields"]["phone"], "966551234567")
        self.assertEqual(lead["status"], "new")

    def test_honeypot_pretends_success_and_stores_nothing(self):
        r = self.post({"name": "bot", "phone": "0551234567",
                       "company_url": "https://spam.example"})
        d = self.loop.run_until_complete(r.json())
        self.assertEqual(r.status, 200)
        self.assertTrue(d["ok"])
        self.assertNotIn("cp_leads.json", self.disk.data)
        self.assertEqual(self.notified, [])

    def test_discord_embed_carries_arabic_mode_slot_audience(self):
        self.post({"name": "خالد", "phone": "0551234567",
                   "audience": "owner", "mode": "office", "slot": "eve"})
        self.assertEqual(len(self.notified), 1)
        text = routes.lead_embed_text(self.notified[0])
        for needle in ("في مكتبنا", "مساءً", "تملك عقاراً", "خالد", "966551234567"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_online_morning_investor_embed(self):
        self.post({"name": "سارة", "phone": "0551234567",
                   "audience": "investor", "mode": "online", "slot": "am"})
        text = routes.lead_embed_text(self.notified[0])
        self.assertIn("عن بُعد", text)
        self.assertIn("صباحاً", text)
        self.assertIn("تدرس الاستثمار", text)


if __name__ == "__main__":
    unittest.main()
