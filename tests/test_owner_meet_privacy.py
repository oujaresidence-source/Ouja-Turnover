# -*- coding: utf-8 -*-
"""R1–R6 on the rendered owner-facing HTML (gate G12). The PDF text gets the same scan in S5 (G19).

The fixture (tests/owner_meet_fixture_build.py) PLANTS identities inside the raw records — a guest's
full name and phone in a maintenance summary, a reservation code inside a claim's items, staff
names as openers/assignees, a staff first name inside a public review, other owners' units in the
listings. Every one must be gone from the shared presentation's HTML SOURCE, and the scanner must
see each kind when it IS planted (the positive control — an absence check that cannot fail proves
nothing).

Run: python3 -m unittest tests.test_owner_meet_privacy
"""
import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from owner_meet import privacy, render  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "owner_meet"
FULL = json.loads((FX / "snapshot_full.json").read_text(encoding="utf-8"))
MULTI = json.loads((FX / "snapshot_multi.json").read_text(encoding="utf-8"))
PLANTED = {"guest_full": "Fahad Alqahtani", "guest_2": "Noura Alharbi", "phone": "0551234567",
           "code": "HMXK29ABCD", "staff": ["khalid.ops", "Majed Ops", "Reem RR"]}


class OwnerPagesAreClean(unittest.TestCase):
    def _html(self, snap):
        return render.presentation_html(snap, 1)

    def test_planted_identities_never_reach_the_presentation_source(self):
        for snap in (FULL, MULTI):
            html = self._html(snap)
            for v in (PLANTED["guest_full"], "Alqahtani", PLANTED["guest_2"], "Alharbi", PLANTED["phone"],
                      PLANTED["code"], "HMQQ11ZZYY", "Khalid", "khalid", "Majed", "Reem", "Sara Almutairi", "Almutairi"):
                self.assertNotIn(v, html, v)

    def test_no_other_unit_or_owner_and_no_count(self):
        html = self._html(FULL)
        for lid in range(901, 909):
            self.assertNotIn("Peer Unit %d" % lid, html)
        self.assertNotIn("Ouja | M2", html, "a one-unit meeting names no other unit, even the owner's own")
        self.assertIsNone(re.search("[0-9]+ ?(?:شقة|شقق|وحدة|وحدات)", re.sub("<style.*?</style>", "", html, flags=re.S)))

    def test_the_owners_own_link_page_is_clean_too(self):
        for snap in (FULL, MULTI):
            html = render.owner_page_html(snap, "tok", "portal")
            for v in (PLANTED["guest_full"], PLANTED["phone"], PLANTED["code"], "Majed", "Khalid", "المخدة قاسية"):
                self.assertNotIn(v, html, v)
            self.assertEqual(privacy.scan(html, snap["presenter"]["forbidden"]), [])

    def test_the_scanner_finds_nothing_on_the_real_render(self):
        for snap in (FULL, MULTI):
            self.assertEqual(privacy.scan(self._html(snap), snap["presenter"]["forbidden"]), [])

    def test_the_build_recorded_no_privacy_hit(self):
        self.assertIsNone(FULL["meta"].get("privacy_hits"))
        self.assertNotIn("privacy", [c["key"] for c in FULL["presenter"]["readiness"]])

    def test_private_feedback_only_in_the_presenter_window(self):
        self.assertNotIn("المخدة قاسية", self._html(FULL))
        self.assertIn("المخدة قاسية", render.notes_html(FULL, 1))

    def test_no_emoji_on_the_owner_pages(self):
        html = self._html(FULL)
        self.assertIsNone(re.search("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]", html))


class ScannerPositiveControl(unittest.TestCase):
    """Plant each leak kind into a clean page — the scanner must name every one."""

    BASE = render.presentation_html(FULL, 1)
    FORBID = FULL["presenter"]["forbidden"]

    def _kinds(self, extra):
        return {h["kind"] for h in privacy.scan(self.BASE.replace("</main>", extra + "</main>"), self.FORBID)}

    def test_each_kind_is_caught(self):
        cases = {
            "reservation_code": "<p>HMZZ99YYXX</p>", "phone": "<p>0559876543</p>", "email": "<p>x@y.com</p>",
            "unit_count": "<p>من 42 شقة</p>", "n_equals": "<p>n=6</p>", "sample": "<p>مثال توضيحي</p>",
            "internal_economics": "<p>هامش عوجا</p>", "other_units": "<p>Peer Unit 903</p>",
            "guest_full_names": "<p>Fahad Alqahtani</p>", "staff": "<p>Majed Ops</p>", "staff_tokens": "<p>وKhalid</p>",
        }
        for kind, html in cases.items():
            self.assertIn(kind, self._kinds(html), kind)

    def test_a_hit_becomes_a_red_line_that_blocks_send(self):
        from owner_meet import money
        snap = copy.deepcopy(FULL)
        line = privacy.readiness_line([{"kind": "phone", "where": ""}])
        snap["presenter"]["readiness"].append(line)
        self.assertEqual(line["level"], "red")
        self.assertFalse(money.can_send(snap)[0])
        self.assertNotIn("0559876543", line["text_ar"], "the line names the KIND, never the value")


if __name__ == "__main__":
    unittest.main()
