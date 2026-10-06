# -*- coding: utf-8 -*-
"""owner_meet.ops + the bot.py caps that feed it (gate G11).

Run: python3 -m unittest tests.test_owner_meet_ops
"""
import datetime
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="ouja-meet-ops-"))

import bot  # noqa: E402
from owner_meet import ops, redact  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))
NOW = datetime.datetime(2026, 10, 6, 12, 0, tzinfo=TZ)
S, E = datetime.date(2026, 7, 1), datetime.date(2026, 9, 30)
NOOP = redact.Redactor()


def maint(**kw):
    base = {"kind": "maint", "lid": 77, "category": "تكييف", "summary": "المكيف", "status": "closed",
            "created_at": "2026-08-01T10:00:00+03:00", "closed_at": "2026-08-01T14:00:00+03:00"}
    base.update(kw)
    return base


class Maintenance(unittest.TestCase):
    def test_a_ticket_and_its_dashboard_twin_count_once(self):
        rows, st = ops.maintenance([maint(dash_id="tk_1"), maint(dash_id="tk_1")],
                                   [{"id": "tk_1", "lid": 77, "cost": 300, "status": "fixed", "created_at": "2026-08-01T10:00:00+03:00"}],
                                   S, E, NOW, NOOP)
        self.assertEqual(st["count"], 1)
        self.assertEqual(rows[0]["cost"], 300.0)
        self.assertEqual(rows[0]["hours"], 4.0)

    def test_source_is_a_role_never_a_person(self):
        rows, st = ops.maintenance(
            [maint(dash_id="a", opener="khalid"), maint(dash_id="b", origin="review_call")],
            [{"id": "a", "source": "manual"}, {"id": "b", "source": "review"},
             {"id": "c", "lid": 77, "source": "escalation", "guest": "Noura", "status": "fixed",
              "created_at": "2026-08-02T10:00:00+03:00", "title": "تسريب"}], S, E, NOW, NOOP)
        self.assertEqual(sorted(r["source"] for r in rows), ["guest", "review", "team"])
        self.assertTrue(all(r["source_ar"] in ("الضيف", "فريق عوجا", "مكالمة تقييم") for r in rows))
        self.assertEqual(st["team_share"], 33)

    def test_an_open_ticket_from_before_the_period_is_carried(self):
        rows, st = ops.maintenance([maint(created_at="2026-05-01T10:00:00+03:00", status="open", closed_at=None)],
                                   [], S, E, NOW, NOOP)
        self.assertEqual((st["count"], st["open_now"]), (1, 1))
        rows, _ = ops.maintenance([maint(created_at="2026-05-01T10:00:00+03:00")], [], S, E, NOW, NOOP)
        self.assertEqual(rows, [], "a ticket closed before the period is history, not this meeting")

    def test_cancelled_dashboard_tickets_are_left_out_and_english_keys_become_arabic(self):
        rows, _ = ops.maintenance([], [{"id": "x", "lid": 77, "status": "cancelled", "created_at": "2026-08-01"},
                                       {"id": "y", "lid": 77, "status": "fixed", "category": "maintenance",
                                        "created_at": "2026-08-01"}], S, E, NOW, NOOP)
        self.assertEqual([r["category"] for r in rows], ["صيانة"])


class Claims(unittest.TestCase):
    def _one(self, claimed, received, status="paid"):
        rec = {"kind": "rr", "type": "damage", "items_raw": "كنب", "total_raw": str(claimed), "status": status,
               "created_at": "2026-08-05T12:00:00+03:00", "departure": "2026-08-04",
               "closeout": ({"claimed": claimed, "received": received, "payer": "owner", "at": "2026-08-20"}
                            if status != "submitted" else {})}
        rows, ring, _n = ops.claims([rec], S, E, NOW, bot._rr_outcome, bot._rr_item_lines, lambda r: {"ok": True},
                                    {"damage": "🔨 تلفيات", "other": "أخرى"}, NOOP)
        return rows[0], ring

    def test_chips_follow_rr_outcome_exactly(self):
        for claimed, received, chip in ((750, 750, "full"), (750, 800, "full"), (750, 450, "partial"),
                                        (750, 0, "denied")):
            row, _ = self._one(claimed, received)
            self.assertEqual(bot._rr_outcome(claimed, received) in ("full", "over") and "full" or bot._rr_outcome(claimed, received),
                             row["chip"], (claimed, received))
            self.assertEqual(row["chip"], chip)

    def test_the_ring_counts_closed_claims_only(self):
        _row, ring = self._one(750, 450)
        self.assertEqual((ring["claimed"], ring["received"], ring["rate"]), (750.0, 450.0, 0.6))

    def test_open_claim_carries_the_aircover_deadline_closed_does_not(self):
        row, ring = self._one(120, None, status="submitted")
        self.assertEqual(row["chip"], "open")
        self.assertEqual(row["deadline"]["date"], "2026-08-18")
        self.assertEqual(ring["open"], 1)
        row, _ = self._one(750, 450)
        self.assertIsNone(row["deadline"])

    def test_labels_lose_their_emoji(self):
        row, _ = self._one(750, 450)
        self.assertEqual(row["type_ar"], "تلفيات")

    def test_an_untranslated_answer_is_withheld_and_flagged(self):
        rec = {"kind": "rr", "type": "damage", "status": "paid", "created_at": "2026-08-05", "total_raw": "100",
               "closeout": {"claimed": 100, "received": 50, "less_reason": "wear and tear", "at": "2026-08-20"}}
        rows, _r, notes = ops.claims([rec], S, E, NOW, bot._rr_outcome, bot._rr_item_lines,
                                     lambda r: {"ok": False, "reason": "wear and tear"}, {}, NOOP)
        self.assertIsNone(rows[0]["answer_ar"], "English never reaches the owner as «Airbnb's answer»")
        self.assertEqual(notes[0]["key"], "rr_translation")


class Reviews(unittest.TestCase):
    RV = [{"listing_id": 77, "rating_raw": 10, "guest_name": "Sara Almutairi", "date": "2026-08-12",
           "public_review": "ممتاز", "private_review": "المخدة قاسية", "reservation_id": "9",
           "raw": {"reviewCategory": [{"category": "cleanliness", "rating": 9}]}},
          {"listing_id": 77, "rating_raw": 0, "guest_name": "Zero", "date": "2026-08-13", "public_review": "x"},
          {"listing_id": 77, "rating_raw": "", "guest_name": "Empty", "date": "2026-08-14"},
          {"listing_id": 78, "rating_raw": 6, "guest_name": "Other", "date": "2026-08-15"}]

    def test_zero_and_empty_scores_are_not_reviews(self):
        rows, sm, _p = ops.reviews(self.RV, 77, S, E, set(), NOOP)
        self.assertEqual(sm["count"], 1)
        self.assertEqual(sm["mean"], 5.0)

    def test_first_name_only_private_feedback_apart_followup_shown(self):
        rows, sm, private = ops.reviews(self.RV, 77, S, E, {"9"}, NOOP)
        self.assertEqual(rows[0]["first_name"], "Sara")
        self.assertNotIn("private", rows[0])
        self.assertNotIn("المخدة", str(rows))
        self.assertEqual(private[0]["text"], "المخدة قاسية")
        self.assertEqual(rows[0]["followed"], "تابعنا مع الضيف بعد المغادرة")
        self.assertEqual(sm["subscores"], [{"key": "cleanliness", "label": "النظافة", "value": 4.5}])


class Redaction(unittest.TestCase):
    def test_names_phones_codes_emails_go(self):
        r = redact.Redactor(["Fahad Alqahtani", "نورة الحربي"], ["khalid.ops"])
        out = r("Fahad Alqahtani اتصل 0551234567 و+966551234567 HMAB12CD34 a@b.co ولنورة شكر وKhalid ساعد")
        for bad in ("Fahad", "Alqahtani", "0551234567", "966", "HMAB12CD34", "a@b.co", "نورة", "Khalid"):
            self.assertNotIn(bad, out, bad)
        self.assertIn("فريق عوجا", out)

    def test_ordinary_words_survive(self):
        r = redact.Redactor(["Ali Hassan"], ["Majed Ops"])
        self.assertEqual(r("Opsis Alive"), "Opsis Alive")


class BotCaps(unittest.TestCase):
    def setUp(self):
        self.saved = (dict(bot._dtk.get("tickets") or {}), dict(bot._price_log))

    def tearDown(self):
        bot._dtk["tickets"] = self.saved[0]
        bot._price_log.clear()
        bot._price_log.update(self.saved[1])

    def test_rr_without_lid_is_matched_by_unit_name(self):
        bot._dtk.setdefault("tickets", {}).update({
            "x1": {"kind": "rr", "unit": "Ouja | M1"}, "x2": {"kind": "rr", "unit": "Ouja | M9"},
            "x3": {"kind": "rr", "lid": 77}, "x4": {"kind": "maint", "lid": 77}})
        got = bot._om_dtk("rr", [77], ["Ouja | M1"])
        self.assertEqual(sorted(r["_channel"] for r in got), ["x1", "x3"])

    def test_price_actions_exclude_dry_entries(self):
        bot._price_log["77|2026-09-10"] = [{"dry": False, "old": 1, "new": 2}, {"dry": True, "old": 2, "new": 3}]
        bot._price_log["78|2026-09-10"] = [{"dry": False}]
        got = bot._om_price_actions([77], S, E)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["new"], 2)


if __name__ == "__main__":
    unittest.main()
