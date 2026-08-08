# -*- coding: utf-8 -*-
"""The retired Netlify guide must never reach a guest.

oujaguide.netlify.app was the guest guide until it came in-house; the site is
GONE. On 2026-08-08 a real guest tapped .../a2 from the Airbnb app and got
Netlify's "Site not found". A leftover link in a Hostaway custom field is
therefore not a cosmetic leftover — it is a broken arrival for a guest standing
outside the building.

These tests lock the rule: an old Netlify link is either rewritten to the page we
actually serve, or it counts as NO link at all. It is never handed out as-is.

Run: python3 -m unittest tests.test_guide_dead_netlify_link
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-deadlink")
os.makedirs("/tmp/ouja-test-state-deadlink", exist_ok=True)

from brain import db as bdb        # noqa: E402
from guide import db as gdb        # noqa: E402
import bot  # noqa: E402

OLD = "https://oujaguide.netlify.app"


def _cf(value, name="Listing Internal Name", cf_id=77):
    return {"customFieldId": cf_id, "value": value,
            "customField": {"id": cf_id, "name": name}}


def _listing(*values):
    return {"id": 1, "internalListingName": "Ouja | A2",
            "listingCustomFieldValues": [_cf(v) for v in values]}


class DeadNetlifyLinkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="deadlink_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        gdb.reset_init_cache()
        gdb.upsert_unit("a2", listing_name="Ouja | A2", active=1)
        gdb.upsert_unit("hidden-one", listing_name="Not published yet", active=0)
        cls.OURS = bot.GUIDE_PUBLIC_BASE + "/guide/"

    def setUp(self):
        self._flag = bot.GUIDE_ENABLED
        bot.GUIDE_ENABLED = True

    def tearDown(self):
        bot.GUIDE_ENABLED = self._flag

    # ---- the rewrite itself ------------------------------------------------
    def test_old_path_link_becomes_our_page(self):
        self.assertEqual(bot.inhouse_guide_url(OLD + "/a2"), self.OURS + "a2")

    def test_old_query_link_becomes_our_page(self):
        self.assertEqual(bot.inhouse_guide_url(OLD + "/?id=a2"), self.OURS + "a2")

    def test_trailing_slash_and_case_still_resolve(self):
        self.assertEqual(bot.inhouse_guide_url("HTTPS://OujaGuide.netlify.app/A2/"),
                         self.OURS + "a2")

    def test_a_slug_we_do_not_serve_is_no_link_at_all(self):
        self.assertIsNone(bot.inhouse_guide_url(OLD + "/never-existed"))

    def test_a_hidden_unit_is_no_link_at_all(self):
        """Its page renders empty for the guest — worse than sending nothing."""
        self.assertIsNone(bot.inhouse_guide_url(OLD + "/hidden-one"))

    def test_the_bare_old_domain_is_no_link_at_all(self):
        self.assertIsNone(bot.inhouse_guide_url(OLD))
        self.assertIsNone(bot.inhouse_guide_url(OLD + "/"))

    def test_any_other_url_is_untouched(self):
        for u in ("https://maps.app.goo.gl/xyz", "https://oujares.com/guide/a2",
                  "https://example.com/a2"):
            self.assertEqual(bot.inhouse_guide_url(u), u)

    def test_a_lookalike_domain_is_not_rewritten(self):
        """Only the retired site — not every URL with 'netlify' in it."""
        u = "https://oujaguide.netlify.app.evil.example/a2"
        self.assertEqual(bot.inhouse_guide_url(u), u)

    # ---- what the listings store stores -----------------------------------
    def test_directions_prefers_our_guide_over_a_stale_netlify_field(self):
        url, _ = bot._extract_directions(_listing(OLD + "/a2", "https://oujares.com/guide/a2"))
        self.assertEqual(url, "https://oujares.com/guide/a2")

    def test_a_stale_netlify_field_is_rewritten_not_passed_on(self):
        url, field = bot._extract_directions(_listing(OLD + "/a2"))
        self.assertEqual(url, self.OURS + "a2")
        self.assertEqual(field, "Listing Internal Name")

    def test_an_unserveable_netlify_field_yields_nothing(self):
        self.assertEqual(bot._extract_directions(_listing(OLD + "/never-existed")),
                         (None, None))

    def test_an_unserveable_netlify_field_never_beats_a_real_link(self):
        url, _ = bot._extract_directions(_listing(OLD + "/never-existed",
                                                  "https://maps.app.goo.gl/xyz"))
        self.assertEqual(url, "https://maps.app.goo.gl/xyz")

    def test_no_custom_fields_at_all_is_still_no_link(self):
        self.assertEqual(bot._extract_directions({"id": 1}), (None, None))

    # ---- what the assistant sends a guest ----------------------------------
    def _with_api(self, listing):
        real = bot.api_get
        bot.api_get = lambda path, params=None: {"result": listing}
        bot._guide_cache.clear()
        self.addCleanup(setattr, bot, "api_get", real)
        self.addCleanup(bot._guide_cache.clear)

    def test_guest_link_is_rewritten(self):
        self._with_api(_listing(OLD + "/a2"))
        self.assertEqual(bot.get_guide_url(1), self.OURS + "a2")

    def test_guest_is_never_sent_the_dead_page(self):
        self._with_api(_listing(OLD + "/never-existed"))
        self.assertIsNone(bot.get_guide_url(1))

    def test_guest_link_falls_through_a_dead_field_to_a_live_one(self):
        self._with_api(_listing(OLD + "/never-existed", "https://oujares.com/guide/a2"))
        self.assertEqual(bot.get_guide_url(1), "https://oujares.com/guide/a2")

    def test_the_whole_listing_fallback_scan_is_rewritten_too(self):
        """The old link hiding in a description, not in a custom field."""
        self._with_api({"id": 1, "description": "الدليل: " + OLD + "/a2"})
        self.assertEqual(bot.get_guide_url(1), self.OURS + "a2")

    def test_the_whole_listing_fallback_scan_drops_a_dead_link(self):
        self._with_api({"id": 1, "description": "الدليل: " + OLD + "/never-existed"})
        self.assertIsNone(bot.get_guide_url(1))


if __name__ == "__main__":
    unittest.main()
