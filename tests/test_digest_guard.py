# -*- coding: utf-8 -*-
"""digest.guard — the truth/disclosure guard that runs on the ASSEMBLED HTML before a
single page renders. Each abort condition from the spec (§6) fires on its own, and the
good payload + a clean page pass with an empty list. Reuses cp.guard's fold_digits and
visible_text (owner-approved 2026-09-02) rather than copying them."""
import copy
import json
import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import guard, dates

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.join(HERE, "fixtures", "digest", "payload_good.json")
TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime(2026, 9, 2, 13, 0, tzinfo=TZ)
WEEK = dates.week_for(NOW)


def good():
    with open(GOOD, encoding="utf-8") as fh:
        return json.load(fh)


def section(p, key):
    return [s for s in p["sections"] if s["key"] == key][0]


def html_for(p, extra=""):
    """A minimal but honest page: every primary as a card with the classes the guard
    reads, every url as an href, a foot line, plus whatever `extra` markup the test
    wants to smuggle in."""
    parts = ['<html dir="rtl"><head><style>.x{left:0;width:455px}</style></head><body>']
    for s in p["sections"]:
        parts.append('<section class="page"><div class="eyebrow">%s</div>' % s["title"])
        for it in s["items"]:
            if s["key"] == "fixtures":
                parts.append('<div class="row"><td>%s</td><td>%s</td><td class="when">%s</td>'
                             '<a href="%s">x</a></div>' % (it["home"], it["away"], it["when"], it["url"]))
            else:
                parts.append('<div class="card"><div class="ttl">%s</div><div class="sub">%s</div>'
                             '<span class="chip">%s</span><a href="%s">x</a></div>'
                             % (it["ttl"], it["sub"], it["chip"], it["url"]))
        parts.append('<div class="foot">المصدر: %s · آخر تحقق الأربعاء</div></section>'
                     % ((s["items"][0].get("source") or {}).get("name", "—") if s["items"] else "—"))
    parts.append(extra)
    parts.append("</body></html>")
    return "".join(parts)


class GoodPasses(unittest.TestCase):
    def test_good_payload_and_page_pass(self):
        p = good()
        self.assertEqual(guard.scan(html_for(p), p, WEEK, NOW), [])
        guard.assert_clean(html_for(p), p, WEEK, NOW)      # must not raise

    def test_css_numbers_are_not_prose(self):
        # the style block carries 455px and left:0 — visible_text strips it, so no hit.
        p = good()
        self.assertEqual(guard.scan(html_for(p), p, WEEK, NOW), [])

    def test_table_cells_may_use_western_digits(self):
        p = good()
        html = html_for(p, '<table><tr><td class="num">19,58</td></tr></table>')
        self.assertEqual(guard.scan(html, p, WEEK, NOW), [])


class Aborts(unittest.TestCase):
    def _hit(self, errs, needle):
        self.assertTrue(any(needle in e for e in errs), "expected %r in %r" % (needle, errs))

    def test_missing_source_aborts(self):
        p = good(); section(p, "events")["items"][0]["source"] = {}
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "source")

    def test_stale_source_aborts(self):
        p = good(); section(p, "events")["items"][0]["source"]["fetched_at"] = "2026-08-20T10:00:00+03:00"
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "fetched_at")

    def test_date_outside_window_in_copy_aborts(self):
        p = good()
        html = html_for(p, '<div class="sub">يبدأ الأحد ٦ سبتمبر</div>')
        errs = guard.scan(html, p, WEEK, NOW)
        self._hit(errs, "window")
        # a weekday name outside Thu–Sat is enough on its own
        html2 = html_for(p, '<div class="sub">كل ثلاثاء</div>')
        self._hit(guard.scan(html2, p, WEEK, NOW), "window")

    def test_dates_inside_window_are_fine(self):
        p = good()
        html = html_for(p, '<div class="sub">الخميس ٣ سبتمبر والجمعة ٤ سبتمبر والسبت ٥ سبتمبر</div>')
        self.assertEqual(guard.scan(html, p, WEEK, NOW), [])

    def test_western_digit_in_prose_aborts(self):
        p = good()
        self._hit(guard.scan(html_for(p, '<div class="claim">3 أفلام جديدة</div>'), p, WEEK, NOW), "numeral")
        self._hit(guard.scan(html_for(p, '<p>يفتح 9 المساء</p>'), p, WEEK, NOW), "numeral")

    def test_ltr_spans_are_exempt_from_the_numeral_rule(self):
        p = good()
        html = html_for(p, '<div class="sub">قرب <span dir="ltr">KAFD 2</span></div>')
        self.assertEqual(guard.scan(html, p, WEEK, NOW), [])

    def test_title_over_four_words_in_rendered_text_aborts(self):
        p = good()
        html = html_for(p, '<div class="card"><div class="ttl">نور الرياض يرجع مرة ثانية</div><div class="sub">x</div></div>')
        self._hit(guard.scan(html, p, WEEK, NOW), "4 words")

    def test_sub_over_ten_words_aborts(self):
        p = good()
        html = html_for(p, '<div class="card"><div class="ttl">x</div><div class="sub">%s</div></div>' % " ".join(["كلمة"] * 11))
        self._hit(guard.scan(html, p, WEEK, NOW), "10 words")

    def test_banned_phrase_aborts(self):
        p = good()
        html = html_for(p, '<div class="sub">لا تفوّت العرض</div>')
        self._hit(guard.scan(html, p, WEEK, NOW), "لا تفوّت")

    def test_unverified_url_in_html_aborts(self):
        p = good()
        html = html_for(p, '<a href="https://evil.example/x">y</a>')
        self._hit(guard.scan(html, p, WEEK, NOW), "verified")

    def test_qr_payload_is_checked_too(self):
        p = good()
        html = html_for(p, '<svg class="qr" data-url="https://evil.example/qr"></svg>')
        self._hit(guard.scan(html, p, WEEK, NOW), "verified")

    def test_section_over_cap_aborts(self):
        p = good(); s = section(p, "events"); s["items"] = s["items"] + [copy.deepcopy(s["items"][0])] * 2
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "events")

    def test_placeholder_card_aborts(self):
        p = good()
        self._hit(guard.scan(html_for(p, '<div class="card"><div class="ttl"></div></div>'), p, WEEK, NOW), "empty")
        self._hit(guard.scan(html_for(p, '<div class="card"><div class="ttl">قريباً</div></div>'), p, WEEK, NOW), "placeholder")

    def test_every_card_needs_day_place_price(self):
        p = good(); section(p, "events")["items"][0]["sub"] = "أعمال ضوئية في سبع مناطق"
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "اليوم والتاريخ")
        p = good(); section(p, "events")["items"][0]["sub"] = "٣ سبتمبر · حطين · مجاني"
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "start with the day")
        p = good(); section(p, "events")["items"][0]["sub"] = "الخميس ٣ سبتمبر · حطين · بالليل"
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "no price")

    def test_extreme_image_ratio_and_unsourced_rating_and_unverified_place(self):
        p = good(); section(p, "events")["items"][0]["art"].update({"kind": "og", "src": "data:image/jpeg;base64,x", "w": 2400, "h": 600})
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "crop")
        p = good(); section(p, "cinema")["items"][0]["ratings"] = {"imdb": 7.0, "rt": None, "sources": []}
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "rating without")
        p = good(); del section(p, "worth")["items"][0]["verified_on"]
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "verified_on")

    def test_saying_only_from_the_list_and_verse_only_fetched(self):
        p = good(); p["saying"] = {"id": "s02", "text": "كلام مخترع", "by": "مثل"}
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "sayings.json")
        p = good(); p["saying"] = {"id": "zz", "text": "الطيب ما يضيع", "by": "مثل"}
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "sayings.json")
        p = good(); p["verse"]["source"]["fetched_at"] = ""
        self._hit(guard.scan(html_for(p), p, WEEK, NOW), "fetch timestamp")

    def test_assert_clean_raises_digest_error_naming_every_hit(self):
        p = good(); section(p, "events")["items"][0]["source"] = {}
        with self.assertRaises(guard.DigestError) as cm:
            guard.assert_clean(html_for(p, '<div class="sub">لا تفوّت</div>'), p, WEEK, NOW)
        msg = str(cm.exception)
        self.assertIn("source", msg)
        self.assertIn("لا تفوّت", msg)
        self.assertTrue(issubclass(guard.DigestError, AssertionError))


if __name__ == "__main__":
    unittest.main()
