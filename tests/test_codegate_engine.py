# -*- coding: utf-8 -*-
"""«تسليم الرموز» engine — pure decisions. Run: python3 -m unittest tests.test_codegate_engine"""
import datetime
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from codegate import engine  # noqa: E402

TZ = engine.tz()


def at(hh, mm=0, day=21):
    return datetime.datetime(2026, 10, day, hh, mm, tzinfo=TZ)


RULES_EN = "Hi Sara,\nPlease reply to this message with: \"I agree to the house rules\""
RULES_AR = "فضلاً رد على هالرسالة بـ: «أوافق على قواعد الشقة»"


def msg(inbound, body, hh, mm=0):
    return {"inbound": inbound, "body": body, "at": at(hh, mm)}


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class TestUnits(unittest.TestCase):
    def test_repo_file_has_35(self):
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "codegate", "units.json")
        self.assertEqual(len(engine.load_units(here, None)), 35)

    def test_state_file_wins_when_valid(self):
        d = tempfile.mkdtemp()
        repo, state = os.path.join(d, "r.json"), os.path.join(d, "s.json")
        _write(repo, json.dumps({"listing_ids": [1, 2]}))
        _write(state, json.dumps({"listing_ids": [3]}))
        self.assertEqual(engine.load_units(repo, state), {3})

    def test_broken_state_file_falls_back_to_repo(self):
        d = tempfile.mkdtemp()
        repo, state = os.path.join(d, "r.json"), os.path.join(d, "s.json")
        _write(repo, json.dumps({"listing_ids": [1, 2]}))
        _write(state, "{not json")
        self.assertEqual(engine.load_units(repo, state), {1, 2})

    def test_missing_files_give_empty_set(self):
        self.assertEqual(engine.load_units("/nope/a.json", "/nope/b.json"), set())


class TestReplies(unittest.TestCase):
    def test_rules_marker_both_languages_case_insensitive(self):
        self.assertTrue(engine.is_rules_message(RULES_EN.upper()))
        self.assertTrue(engine.is_rules_message(RULES_AR))
        self.assertFalse(engine.is_rules_message("Your door code: 1234 then #"))

    def test_replies_after_latest_rules_message_only(self):
        r = engine.guest_replies([
            msg(True, "is parking free?", 9),
            msg(False, RULES_EN, 10),
            msg(True, "i agre", 10, 5),
            msg(True, "IGR RA", 10, 6),
        ])
        self.assertEqual(r["rules_at"], at(10))
        self.assertEqual([x["text"] for x in r["replies"]], ["i agre", "IGR RA"])

    def test_outbound_never_quoted(self):
        r = engine.guest_replies([msg(False, RULES_EN, 10), msg(False, RULES_AR, 10, 1)])
        self.assertEqual(r["replies"], [])

    def test_host_quote_of_agree_not_a_reply(self):
        r = engine.guest_replies([msg(False, RULES_EN, 10),
                                  msg(False, 'Thanks! You wrote "I agree" — noted', 10, 9)])
        self.assertEqual(r["replies"], [])

    def test_no_rules_message_quotes_last_inbound(self):
        r = engine.guest_replies([msg(True, "a", 8), msg(True, "b", 9), msg(True, "c", 9, 1),
                                  msg(True, "d", 9, 2)])
        self.assertIsNone(r["rules_at"])
        self.assertEqual([x["text"] for x in r["replies"]], ["b", "c", "d"])

    def test_long_reply_truncated_and_at_most_three(self):
        r = engine.guest_replies([msg(False, RULES_EN, 10)] +
                                 [msg(True, "x" * 900, 11, i) for i in range(5)])
        self.assertEqual(len(r["replies"]), 3)
        self.assertLessEqual(len(r["replies"][0]["text"]), engine.QUOTE_CHARS + 1)

    def test_messages_without_time_sorted_last_and_kept(self):
        r = engine.guest_replies([msg(False, RULES_EN, 10),
                                  {"inbound": True, "body": "ok", "at": None}])
        self.assertEqual([x["text"] for x in r["replies"]], ["ok"])


class TestAlerts(unittest.TestCase):
    def item(self, **kw):
        base = {"checkin_at": at(16), "released_at": None, "cancelled": 0,
                "alert_2h_at": None, "alert_late_at": None}
        base.update(kw)
        return base

    def test_nothing_before_two_hours(self):
        self.assertIsNone(engine.alert_due(self.item(), at(13, 59)))

    def test_two_hours(self):
        self.assertEqual(engine.alert_due(self.item(), at(14, 0)), "2h")

    def test_two_hours_only_once(self):
        self.assertIsNone(engine.alert_due(self.item(alert_2h_at="x"), at(15)))

    def test_late_at_checkin(self):
        self.assertEqual(engine.alert_due(self.item(alert_2h_at="x"), at(16)), "late")

    def test_late_booking_one_alert(self):
        # first seen after check-in: one "late", and the 2h is considered covered by it
        self.assertEqual(engine.alert_due(self.item(), at(17)), "late")
        self.assertIsNone(engine.alert_due(self.item(alert_late_at="x"), at(18)))

    def test_released_or_cancelled_never_alerts(self):
        self.assertIsNone(engine.alert_due(self.item(released_at="x"), at(17)))
        self.assertIsNone(engine.alert_due(self.item(cancelled=1), at(17)))


class TestPermission(unittest.TestCase):
    def test_matrix(self):
        self.assertTrue(engine.may_release("1", "1", "", False, False))     # coverer
        self.assertTrue(engine.may_release("2", "1", "2", False, False))    # permanent owner
        self.assertTrue(engine.may_release("9", "1", "2", True, False))     # admin
        self.assertTrue(engine.may_release("9", "1", "2", False, True))     # ops role
        self.assertFalse(engine.may_release("9", "1", "2", False, False))   # anyone else
        self.assertFalse(engine.may_release("", "", "", False, False))      # empty never matches


class TestCard(unittest.TestCase):
    def base(self, **kw):
        it = {"unit": "C2 NFL", "guest": "Sara", "checkin_at": at(16), "cover_name": "نورة",
              "rules_at": at(10), "replies": [{"at": at(10, 5), "text": "I agree"}],
              "released_at": None, "released_by": None, "cancelled": 0,
              "alert_2h_at": None, "alert_late_at": None, "code_warned_at": None}
        it.update(kw)
        return it

    def test_waiting_card_quotes_reply_and_names_coverer(self):
        e = engine.card(self.base(), at(11))
        blob = json.dumps(e, ensure_ascii=False)
        self.assertIn("C2 NFL", e["title"])
        self.assertIn("> I agree", blob)
        self.assertIn("نورة", blob)
        self.assertIn("16:00", blob)
        self.assertEqual(e["color"], engine.COLOR_WAIT)

    def test_card_shows_verdict_field(self):
        def field(it):
            e = engine.card(it, at(11))
            names = [f["name"] for f in e["fields"]]
            i = names.index("ما كتبه الضيف")
            self.assertLess(i, names.index("ردود الضيف (حرفياً)"))
            return e["fields"][i]["value"]
        self.assertEqual(field(self.base()), engine.VERDICT_LABEL["yes"])
        self.assertEqual(field(self.base(replies=[{"at": at(10), "text": "IGR"}])),
                         engine.VERDICT_LABEL["unclear"])
        self.assertEqual(field(self.base(replies=[])), engine.VERDICT_LABEL["none"])

    def test_card_description_and_footer(self):
        e = engine.card(self.base(), at(11))
        self.assertIn("اضغط «✅ وافق — أرسل الرمز»", e["description"])
        self.assertIn("📝 أرسلته يدوياً", e["description"])
        self.assertEqual(e["footer"]["text"],
                         "«تسليم الرموز» · البوت يقرأ الرد ويرسل الرمز فقط لما تضغط الزر")

    def test_no_reply_yet(self):
        e = engine.card(self.base(replies=[]), at(11))
        self.assertIn("لا يوجد رد بعد", json.dumps(e, ensure_ascii=False))

    def test_missing_rules_message_flagged(self):
        e = engine.card(self.base(rules_at=None), at(11))
        self.assertIn("ما لقيت رسالة القواعد", json.dumps(e, ensure_ascii=False))

    def test_released_green_with_who_and_when(self):
        e = engine.card(self.base(released_at=at(14, 5).isoformat(), released_by="نورة"), at(15))
        self.assertEqual(e["color"], engine.COLOR_DONE)
        self.assertIn("14:05", json.dumps(e, ensure_ascii=False))

    def test_alert_fired_red_cancelled_grey(self):
        self.assertEqual(engine.card(self.base(alert_2h_at="x"), at(14, 30))["color"],
                         engine.COLOR_ALERT)
        self.assertEqual(engine.card(self.base(cancelled=1), at(14))["color"], engine.COLOR_OFF)

    def test_status_two_hour_vs_late(self):
        two = json.dumps(engine.card(self.base(alert_2h_at="x"), at(14, 30)), ensure_ascii=False)
        self.assertIn("قرب الدخول", two)
        self.assertNotIn("متأخر", two)
        late = json.dumps(engine.card(self.base(alert_2h_at="x", alert_late_at="y"), at(16, 5)),
                          ensure_ascii=False)
        self.assertIn("متأخر", late)

    def test_hostaway_link_field(self):
        e = engine.card(self.base(res_id="555123"), at(11))
        link = [f for f in e["fields"] if "dashboard.hostaway.com/reservations/555123" in f["value"]]
        self.assertEqual(len(link), 1)
        self.assertFalse(any("hostaway.com/reservations" in f["value"]
                             for f in engine.card(self.base(), at(11))["fields"]))

    def test_soak_note_only_in_soak(self):
        soak = json.dumps(engine.card(self.base(), at(11), soak=True), ensure_ascii=False)
        live = json.dumps(engine.card(self.base(), at(11)), ensure_ascii=False)
        self.assertIn(engine.SOAK_NAME, soak)
        self.assertIn(engine.SOAK_TEXT, soak)
        self.assertNotIn(engine.SOAK_NAME, live)

    def test_soak_description_has_no_press_instruction(self):
        e = engine.card(self.base(), at(11), soak=True)
        self.assertEqual(e["description"],
                         "🧪 وضع التجربة — الرمز يُرسل تلقائياً من Hostaway، ما فيه أزرار حالياً.")
        self.assertNotIn("اضغط", e["description"])
        self.assertIn("اضغط «✅ وافق — أرسل الرمز»", engine.card(self.base(), at(11))["description"])

    def test_title_clipped_to_discord_limit(self):
        e = engine.card(self.base(unit="U" * 200, guest="G" * 200), at(11))
        self.assertLessEqual(len(e["title"]), 256)
        self.assertTrue(e["title"].endswith("…"))

    def test_code_warning_shown(self):
        e = engine.card(self.base(released_at=at(14).isoformat(), released_by="نورة",
                                  code_warned_at=at(14, 20).isoformat()), at(15))
        self.assertIn("ما شفت رسالة الرمز", json.dumps(e, ensure_ascii=False))

    def test_hash_changes_with_content(self):
        a = engine.content_hash(engine.card(self.base(), at(11)))
        b = engine.content_hash(engine.card(self.base(replies=[]), at(11)))
        self.assertNotEqual(a, b)
        self.assertEqual(a, engine.content_hash(engine.card(self.base(), at(11))))


class TestVerdict(unittest.TestCase):
    def v(self, *texts):
        return engine.agree_verdict([{"at": at(10), "text": t} for t in texts])

    def assertAll(self, expected, texts):
        for t in texts:
            self.assertEqual(self.v(t), expected, t)

    def test_verdict_yes_variants(self):
        self.assertAll("yes", ("أوافق على قواعد الشقة", "اوافق", "موافق 👍", "I agree",
                               "agreed!", "ok agree"))

    def test_verdict_diacritics_and_tatweel_folded(self):
        self.assertAll("yes", ("أُوَافِقُ", "مـــوافق"))

    def test_verdict_negations_are_unclear(self):
        self.assertAll("unclear", ("ما أوافق", "لا اوافق", "I don't agree", "not agree",
                                   "disagree"))

    def test_verdict_unclear(self):
        self.assertAll("unclear", ("IGR RA", "ok", "what rules?"))

    def test_verdict_none(self):
        self.assertEqual(engine.agree_verdict([]), "none")

    def test_negation_must_be_in_the_same_reply(self):
        self.assertEqual(self.v("لا", "أوافق"), "yes")

    # 2. more negations
    def test_english_contractions_negate(self):
        self.assertAll("unclear", ("can't agree", "cannot agree", "won't agree",
                                   "wouldn't agree", "doesn’t agree", "isn't agree",
                                   "no I agree", "cant agree"))

    # 3. questions
    def test_questions_are_not_agreement(self):
        self.assertAll("unclear", ("هل لازم أوافق؟", "Do I need to agree?", "وش اوافق عليه؟",
                                   "اوافق؟", "agree?", "هل اوافق", "what do I agree to",
                                   "how do I agree"))

    # 4. quoted text
    def test_quoted_rules_message_is_not_a_yes(self):
        quoted = "What rules?\n\n> Please reply: I agree to the house rules"
        self.assertEqual(self.v(quoted), "unclear")
        # _clip flattens newlines before the engine sees a reply
        self.assertEqual(self.v("What rules? > Please reply: I agree to the house rules"),
                         "unclear")

    def test_attribution_line_cuts_everything_after(self):
        self.assertEqual(self.v("What rules?\nOn Mon, Oct 21, 2026 at 10:00 AM Ouja <a@b.c> "
                                "wrote:\nPlease reply I agree to the house rules"), "unclear")
        self.assertEqual(self.v("ايش القواعد\nفي الاثنين، ٢١ أكتوبر ٢٠٢٦ في ١٠:٠٠ ص، كتب Ouja "
                                "<a@b.c>:\nأوافق على قواعد الشقة"), "unclear")

    def test_real_reply_above_the_quote_still_counts(self):
        self.assertEqual(self.v("I agree\n\nOn Mon, Oct 21 at 10:00 Ouja wrote:\n> I agree to "
                                "the house rules"), "yes")
        self.assertEqual(self.v("أوافق\n> أوافق على قواعد الشقة"), "yes")

    # 5. latest mention wins
    def test_later_withdrawal_wins(self):
        self.assertEqual(self.v("أوافق", "ما أوافق"), "unclear")
        self.assertEqual(self.v("I agree", "wait, do I need to agree?"), "unclear")

    def test_latest_mention_ignores_replies_without_a_token(self):
        self.assertEqual(self.v("I agree", "what time is check-in"), "yes")
        self.assertEqual(self.v("what rules?", "ok I agree"), "yes")
        self.assertEqual(self.v("ما أوافق", "طيب أوافق"), "yes")

    def test_no_reply_mentions_a_token(self):
        self.assertEqual(self.v("ok", "thanks"), "unclear")

    # 6. agreeing idioms are not negations
    def test_agreeing_idioms_are_yes(self):
        self.assertAll("yes", ("لا بأس، أوافق", "لا مشكلة أوافق", "لا تقلق أوافق",
                               "ما فيه مشكلة موافق", "ما عندي مشكلة أوافق",
                               "ما عندنا اعتراض، موافقين", "no problem I agree",
                               "no worries, agreed"))

    def test_negation_further_than_two_words_back_is_ignored(self):
        self.assertEqual(self.v("ما عندي مشكلة وانا أوافق"), "yes")
        self.assertEqual(self.v("ما أبي أوافق"), "unclear")

    # 7. prefixed / plural / elongated
    def test_prefixed_plural_and_elongated_forms(self):
        self.assertAll("yes", ("وأوافق", "فموافق", "موافقين", "نوافق", "موافقون",
                               "أوافقققق", "agreeeee", "مووووافق"))

    # 8. invisible characters
    def test_zero_width_bidi_and_underscore_are_stripped(self):
        self.assertAll("yes", ("أوا\u200bفق", "\u202bأوافق\u202c", "أوافق_", "_agree_",
                               "\u2066I agree\u2069"))
        self.assertEqual(self.v("ما\u200f أوافق"), "unclear")


    # round 2, 1: a leading و/ف glued to a negation
    def test_prefixed_negations_are_unclear(self):
        self.assertAll("unclear", ("ولا أوافق", "وما أوافق", "فلا اوافق", "ومو موافق",
                                   "ولا اوافق ابد"))

    # round 2, 2: more negations, and far negations through filler words
    def test_more_negations_and_far_negations(self):
        self.assertAll("unclear", ("ماني موافق", "مانيب موافق", "مقدر اوافق", "ماقدر اوافق",
                                   "مستحيل اوافق", "ابد ما اوافق", "أبد أوافق", "never agree",
                                   "not going to agree", "I am not gonna agree",
                                   "I do not want to agree", "ما اقدر اقول اوافق",
                                   "ما راح اوافق", "ما بـ اوافق"))

    def test_fillers_alone_do_not_negate_and_idioms_still_work(self):
        self.assertAll("yes", ("going to agree", "راح اوافق", "اقدر اوافق", "لا بأس، أوافق",
                               "no problem, I'm going to agree"))

    # round 2, 3: short elongation of a negation
    def test_elongated_negation(self):
        self.assertAll("unclear", ("noo agree", "nooo agree", "لاا اوافق", "مااا اوافق"))

    # round 2, 4: quote marks stuck to a word
    def test_quote_marks_on_word_edges(self):
        self.assertAll("yes", ("Reply 'I agree'", "'agree'", "\"agree\"", "«أوافق»", "‹أوافق›",
                               "ok 'agreed'"))
        self.assertAll("unclear", ("I don't agree", "I can't agree", "I 'don't' agree",
                                   "I don’t agree"))


    # round 3: negations that were still missing
    def test_remaining_negations_are_unclear(self):
        words = ("didnt", "shouldnt", "couldnt", "wouldnt", "havent", "arent", "isnt", "wasnt",
                 "wont", "cant", "dont", "doesnt", "refuse", "refused", "unable", "ابدا", "ابداً",
                 "مابي", "مابغى", "مابغي", "ماابي", "dis")
        for w in words:
            self.assertEqual(self.v("i %s agree" % w), "unclear", w)
            self.assertEqual(self.v("%s اوافق" % w), "unclear", w)
        self.assertEqual(self.v("i dis agree"), "unclear")


class TestSendTexts(unittest.TestCase):
    WATCHDOG = r"\d{3,10}\s*#|#\s*\d{3,10}"   # watchdog/engine.py:43

    @staticmethod
    def codegate_honesty_sees_a_code(text):
        # codegate's honesty rule: a 4-6 digit number AND a "code" keyword in the same text
        return bool(re.search(r"\b\d{4,6}\b", text)) and \
            bool(re.search("كود|code", text, re.I))

    def test_code_message_keeps_hash_right_after_the_digits(self):
        m = engine.code_message("1234")
        self.assertIn("🔑 كود الدخول: 1234#", m)
        self.assertIn("🔑 Door code: 1234#", m)
        self.assertEqual(m.count("1234"), 2)

    def test_code_message_is_seen_by_the_watchdog(self):
        self.assertTrue(re.search(self.WATCHDOG, engine.code_message("1234")))
        self.assertTrue(re.search(self.WATCHDOG, engine.code_message("987654")))

    def test_code_message_is_seen_by_the_codegate_honesty_check(self):
        for c in ("1234", "56789", "987654"):
            self.assertTrue(self.codegate_honesty_sees_a_code(engine.code_message(c)), c)

    def test_code_message_normalises_the_code(self):
        self.assertEqual(engine.code_message("1234#").count("1234#"), 2)
        self.assertNotIn("##", engine.code_message("1234#"))
        self.assertEqual(engine.code_message(" 12 34 "), engine.code_message("1234"))
        self.assertIn("(اكتب الرقم ثم اضغط #)", engine.code_message("1234"))
        self.assertIn("(enter the digits, then press #)", engine.code_message("1234"))

    def test_code_message_refuses_an_empty_code(self):
        for bad in ("", "   ", "#", None):
            with self.assertRaises(ValueError):
                engine.code_message(bad)

    def test_labels_verbatim(self):
        self.assertEqual(engine.LABEL_SEND, "✅ وافق — أرسل الرمز")
        self.assertEqual(engine.LABEL_MANUAL, "📝 أرسلته يدوياً")
        self.assertEqual(engine.LABEL_UNDO, "↩️ تراجع")
        self.assertEqual(engine.VERDICT_LABEL, {"yes": "✅ كتب «أوافق»",
                                                "unclear": "⚠️ رد بس مو واضح",
                                                "none": "⏳ ما رد بعد"})
        self.assertEqual(engine.CONFIRM_SEND,
                         "يرسل البوت الرمز للضيف الحين من Hostaway. متأكد إنه كتب «أوافق»؟")
        self.assertEqual(engine.CONFIRM_MANUAL, "سجّل إنك أرسلت الرمز بنفسك من Hostaway؟")
        self.assertTrue(engine.CONFIRM_SEND_UNCLEAR.startswith("⚠️ ما لقيت «أوافق» واضحة"))

    def test_deprecated_names_removed(self):
        # R3 rewired bot.py to LABEL_SEND / CONFIRM_SEND*, so the revision-1 names are gone
        self.assertFalse(hasattr(engine, "LABEL_RELEASE"))
        self.assertFalse(hasattr(engine, "CONFIRM_TEXT"))


class TestTexts(unittest.TestCase):
    def test_header_and_alerts(self):
        self.assertIn("٣", engine.header_text("<@1>", "نورة", 3))
        self.assertIn("<@1>", engine.alert_text("2h", {"unit": "C3", "guest": "A",
                                                        "checkin_at": at(16)}, "<@1>"))
        self.assertIn("حلّ موعد الدخول", engine.alert_text("late", {"unit": "C3", "guest": "A",
                                                                      "checkin_at": at(16)}, ""))


if __name__ == "__main__":
    unittest.main()
