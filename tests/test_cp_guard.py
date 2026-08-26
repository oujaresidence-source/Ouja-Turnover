# -*- coding: utf-8 -*-
"""
The disclosure guard (seeds §0, §3, §11).

This is the test the whole /cp build hangs on: a figure tagged WITHHOLD must not
be able to reach a rendered page, ever, by any route — including a future edit by
someone who never read the seeds file. So the guard is a unit, tested on its own,
and the page tests then run every rendered edition through it.

Scanning rules that matter:
  * <style>/<script>/comments are stripped first, so `width:72px` is not a
    "72 units" leak. CSS is full of numbers; visible copy is what we police.
  * meta description/og content and alt text ARE scanned — they are published text.
  * Arabic-Indic digits are folded to ASCII first, so ٧٬٣١١ cannot smuggle 7,311.
  * ADR 582/654 and RevPAR 451/485 are whitelisted (seeds §3, published on purpose).
"""
import unittest

from cp import guard


CLEAN = """<!doctype html><html><head>
<meta name="description" content="8,114 reservations, 13,093 guest nights, 76.9% occupancy.">
<style>.led{width:72px;height:455px;flex:0 0 60px}</style>
</head><body>
<h1>74 residences</h1>
<p>4.77 out of 5 across 2,633 published reviews.</p>
<p>ADR 582 SAR, 654 over the last 90 days. RevPAR 451, 485 on active residences.</p>
<img src="x.jpg" alt="Ouja | a two-bedroom residence at Al Majdiah">
</body></html>"""


class VisibleText(unittest.TestCase):
    def test_strips_style_and_script(self):
        txt = guard.visible_text(CLEAN)
        self.assertNotIn("width:72px", txt)
        self.assertNotIn("455px", txt)

    def test_keeps_meta_and_alt(self):
        txt = guard.visible_text(CLEAN)
        self.assertIn("13,093", txt)
        self.assertIn("Al Majdiah", txt)

    def test_folds_arabic_indic_digits(self):
        self.assertIn("7311", guard.visible_text("<p>٧٣١١</p>").replace(",", ""))


class CleanPagePasses(unittest.TestCase):
    def test_no_violations(self):
        self.assertEqual(guard.scan(CLEAN), [])

    def test_assert_clean_is_quiet(self):
        guard.assert_clean(CLEAN)  # must not raise

    def test_published_figures_never_trip(self):
        for ok in ("8,114", "13,093", "76.9%", "4.77", "2,633", "74 residences",
                   "87.6%", "37%", "933", "94%", "42%", "67%", "26%", "78.6%",
                   "22 people", "200 residences", "2.3 minutes", "152,177"):
            with self.subTest(ok=ok):
                self.assertEqual(guard.scan("<p>%s</p>" % ok), [])

    def test_whitelisted_money_never_trips(self):
        for ok in ("582", "654", "451", "485"):
            with self.subTest(ok=ok):
                self.assertEqual(guard.scan("<p>ADR %s SAR</p>" % ok), [])


class WithheldFiguresTrip(unittest.TestCase):
    """Seeds §3 — every one of these must fail the build."""

    CASES = [
        "7,669,457 SAR",          # all-time gross revenue
        "7669457",
        "275,199",                # 2024 revenue
        "2,528,801",              # 2025 revenue
        "4,865,456",              # 2026 revenue
        "2,001,914",              # last 90 days revenue
        "1,859 reservations of revenue",  # only a leak in a revenue context
        "14,731 SAR",             # revenue per active residence
        "2,412,347",              # stopped-residence revenue
        "945 SAR",                # average booking value
        "median 606",             # median booking value
        "455 unsigned",           # unsigned rental agreements
        "53 active",              # active/stopped split
        "19 stopped",
        "7,836 reservations",     # Airbnb channel volume
        "278 direct",             # direct channel volume
        "H8 VLG",                 # named best/worst residences
        "11B Royal",
    ]

    def test_each_case_trips(self):
        for bad in self.CASES:
            with self.subTest(bad=bad):
                self.assertTrue(guard.scan("<p>%s</p>" % bad),
                                "guard let a WITHHOLD figure through: %r" % bad)

    def test_assert_clean_raises(self):
        with self.assertRaises(guard.DisclosureError):
            guard.assert_clean("<p>All-time revenue 7,669,457 SAR</p>")

    def test_error_names_the_figure(self):
        try:
            guard.assert_clean("<p>7,669,457</p>")
        except guard.DisclosureError as e:
            self.assertIn("7,669,457", str(e))
        else:
            self.fail("expected DisclosureError")


class RetiredFiguresTrip(unittest.TestCase):
    """Seeds §11 — stale numbers that are live somewhere in the codebase today."""

    CASES = ["7,311", "11,307", "14,000+ turnovers", "100+ listings",
             "49,000 lines", "45,000 lines", "57,600 lines", "70+ residences",
             "60+ units", "67 listings", "71 units", "72 residences"]

    def test_each_case_trips(self):
        for bad in self.CASES:
            with self.subTest(bad=bad):
                self.assertTrue(guard.scan("<p>%s</p>" % bad),
                                "guard let a RETIRED figure through: %r" % bad)

    def test_rating_4_8_trips(self):
        self.assertTrue(guard.scan("<p>rated 4.8 or above</p>"))
        self.assertEqual(guard.scan("<p>rated 4.77</p>"), [])

    def test_arabic_indic_smuggling_trips(self):
        self.assertTrue(guard.scan("<p>٧٬٣١١ إقامة</p>"))


if __name__ == "__main__":
    unittest.main()


class LiveMetricsCannotKillThePage(unittest.TestCase):
    """A growing live figure must be able to pass through the withheld small
    numbers without tripping the guard — repeat_guests is 933 today and will
    innocently reach 945; a bare match here once meant the page dying the
    night that happened."""

    def test_bare_small_numbers_pass_without_their_context(self):
        for ok in ("945 ضيفاً عادوا", "606 حجزاً هذا الشهر", "455 ليلة",
                   "278 مراجعة جديدة", "1,859 حجز منفّذ"):
            with self.subTest(ok=ok):
                self.assertEqual(guard.scan("<p>%s</p>" % ok), [],
                                 "guard killed an innocent live figure: %r" % ok)

    def test_the_same_numbers_still_trip_in_context(self):
        for bad in ("متوسط قيمة الحجز 945 ريال", "median booking 606 SAR",
                    "455 عقداً غير موقّع", "278 حجزاً مباشراً"):
            with self.subTest(bad=bad):
                self.assertTrue(guard.scan("<p>%s</p>" % bad))


class PublishedRatiosSurvive(unittest.TestCase):
    """Seeds §3 «The ratios that ARE publishable» — regression lock.

    A looser fee pattern once flagged the long-stay line because it ends in
    "of revenue". These sentences are cleared for publication; if the guard ever
    rejects one again, the guard is wrong, not the copy.
    """

    LINES = [
        "Stays of four nights or more: 6% of bookings, 26% of revenue",
        "إقامات أربع ليالٍ فأكثر: 6% من الحجوزات، و26% من الإيراد",
        "Average nightly rate up 22% across the same period",
        "Released residences were running at 78.6% occupancy when they left",
        "Direct guests stay 3.7 nights against a 1.6-night portfolio average",
        "2026's first eight months delivered nearly twice the volume of all of 2025",
        "19 residences released, at 78.6% occupancy",
        "the longer the payout interval, the lower the fee",
    ]

    def test_publishable_ratios_pass(self):
        for line in self.LINES:
            with self.subTest(line=line[:48]):
                self.assertEqual(guard.scan("<p>%s</p>" % line), [],
                                 "guard rejected a PUBLISHABLE line: %r" % line)

    def test_the_real_fee_disclosure_still_trips(self):
        self.assertTrue(guard.scan("<p>A management fee of 18% on collected revenue</p>"))
        self.assertTrue(guard.scan("<p>quarterly payout at 12%</p>"))


class RealDocumentsAreClean(unittest.TestCase):
    """The Arabic edition we are porting must itself pass the guard."""

    def test_arabic_edition_has_no_leak(self):
        """The v1 source document lives outside the repo, so it may be absent
        OR unreadable depending on how the suite is invoked — neither is a
        guard failure. The in-repo v6 mock is the version this test suite
        actually owns (see MockApprovedFiguresSurvive)."""
        import os
        path = os.path.expanduser("~/Downloads/ouja-cp-ar.html")
        try:
            with open(path, encoding="utf-8") as fh:
                markup = fh.read()
        except OSError:
            self.skipTest("v1 source document not readable here")
        self.assertEqual(guard.scan(markup), [])


class IdentityDocumentsAreBlocked(unittest.TestCase):
    """Seeds §1 — publishable in the PDF and the ministry file, never on the page."""

    def test_commercial_registration_trips(self):
        self.assertTrue(guard.scan("<p>Commercial registration 7050158810</p>"))

    def test_fal_licence_number_trips(self):
        self.assertTrue(guard.scan("<p>فال 1200050611</p>"))

    def test_the_soft_fal_wording_passes(self):
        self.assertEqual(
            guard.scan("<p>operating under a فال real-estate licence</p>"), [])

    def test_facility_management_licence_is_unmentionable(self):
        self.assertTrue(guard.scan("<p>tourism facility-management licence</p>"))
        self.assertTrue(guard.scan("<p>رخصة إدارة المرافق السياحية</p>"))

    def test_per_residence_tourism_permits_still_publishable(self):
        for ok in ("Every residence carries its own tourism permit",
                   "تصريح سياحي لكل وحدة، باسم المالك"):
            with self.subTest(ok=ok):
                self.assertEqual(guard.scan("<p>%s</p>" % ok), [])


class DataSeedFiguresTrip(unittest.TestCase):
    """v2 (seeds-2026-08): docs/cp/data-seed-2026-08.md is internal-only; every
    figure in it that is not explicitly mock-approved must fail the build."""

    BARE = [
        "762,810",            # July 2026 revenue
        "583,867", "494,330", "480,434", "712,470",
        "674,651", "592,635", "564,259",             # 2026 monthly revenues
    ]

    CONTEXTUAL = [
        "رسوم الإدارة 20%",                     # the management fee
        "a 20% management fee",
        "Airbnb takes ~24%",                     # channel take
        "تأخذ المنصة 24%",
        "1BR ADR 426",                           # per-type ADR
        "متوسط سعر الليلة لغرفتين 765",
        "RevPAR for 3BR is 483",
        "4BR revenue 963 per available night",   # per-type RevPAR
        "23 units of 1BR",                       # unit counts per type
        "17 وحدة من ثلاث غرف",
        "top unit made 404K", "F2 346K",         # unit revenues
        "284 دفعة خارج النظام",                  # unknown payments
        "284 payments show Unknown",
        "a 7.5x revenue multiple",
    ]

    NAMED_UNITS = ["H8 VLG", "11B Royal", "HUE 9", "C2 NFL", "9B HTN", "4511",
                   "103 NRJS", "E5MLQ", "13 JOOD", "101-Narjs", "TWN 13B",
                   "القيروان-D7"]

    def test_bare_figures_trip(self):
        for bad in self.BARE:
            with self.subTest(bad=bad):
                self.assertTrue(guard.scan("<p>%s</p>" % bad),
                                "seed figure passed: %r" % bad)

    def test_contextual_figures_trip(self):
        for bad in self.CONTEXTUAL:
            with self.subTest(bad=bad):
                self.assertTrue(guard.scan("<p>%s</p>" % bad),
                                "seed figure passed: %r" % bad)

    def test_named_units_trip(self):
        for bad in self.NAMED_UNITS:
            with self.subTest(bad=bad):
                self.assertTrue(guard.scan("<p>%s</p>" % bad),
                                "named unit passed: %r" % bad)

    def test_short_unit_codes_trip_with_word_context(self):
        # deliberately narrow: bare F2/D7/201a/202B/FD1/C204/3BMJ only leak
        # beside unit/occupancy/revenue words — a hex hash must not trip them
        for bad in ("وحدة F2", "unit D7", "201a occupancy", "202B 58.6%",
                    "FD1 left in July", "C204 churned", "3BMJ وحدة"):
            with self.subTest(bad=bad):
                self.assertTrue(guard.scan("<p>%s</p>" % bad))

    def test_the_seed_document_itself_lights_up(self):
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "docs", "cp", "data-seed-2026-08.md")
        with open(path, encoding="utf-8") as fh:
            hits = guard.scan("<p>" + fh.read() + "</p>")
        self.assertGreater(len(hits), 15,
                           "the internal seed should trip the guard massively")


class MockApprovedFiguresSurvive(unittest.TestCase):
    """Everything on the approved v6 mock is publishable and regression-locked."""

    LINES = [
        "الشقق المخدومة في الرياض 59.3%",         # MoT benchmark
        "فنادق المملكة 63.4% · العائد لكل ليلة متاحة 478 ريال",  # Knight Frank
        "متوسط سعر الليلة 754 · 206",
        "سعر الليلة في نهاية الأسبوع مقابل وسطه 644 · 554",
        "الإشغال +24.1%، والسعر −11.8%، وعدد الوحدات −8%",
        "من 2,900 إلى 23,000 شهرياً",
        "تراوح بين 53.8% (يونيو) و82.6% (يناير)",
        "إقامة مباشرة · متوسط الليالي 3.7",
        "أعلى ضيف عائد 49",
        "22 موظفاً · قرابة 200 وحدة · 66,000 سطر",
        "152,177 رسالة · 2.3 دقيقة · ~1,000 تذكرة",
    ]

    def test_approved_lines_pass(self):
        for line in self.LINES:
            with self.subTest(line=line[:40]):
                self.assertEqual(guard.scan("<p>%s</p>" % line), [],
                                 "guard rejected mock-approved copy: %r" % line)

    def test_the_whole_v6_mock_is_clean(self):
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "docs", "cp", "v6-mock.html")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(guard.scan(fh.read()), [])
