# -*- coding: utf-8 -*-
"""«تسليم الرموز» engine — pure decisions. Run: python3 -m unittest tests.test_codegate_engine"""
import datetime
import json
import os
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

    def test_verdict_yes_variants(self):
        for t in ("أوافق على قواعد الشقة", "اوافق", "موافق 👍", "I agree", "agreed!", "ok agree"):
            self.assertEqual(self.v(t), "yes", t)

    def test_verdict_diacritics_and_tatweel_folded(self):
        self.assertEqual(self.v("أُوَافِقُ"), "yes")
        self.assertEqual(self.v("مـــوافق"), "yes")

    def test_verdict_negations_are_unclear(self):
        for t in ("ما أوافق", "لا اوافق", "I don't agree", "not agree", "disagree"):
            self.assertEqual(self.v(t), "unclear", t)

    def test_verdict_unclear(self):
        for t in ("IGR RA", "ok", "what rules?"):
            self.assertEqual(self.v(t), "unclear", t)

    def test_verdict_none(self):
        self.assertEqual(engine.agree_verdict([]), "none")

    def test_any_reply_can_carry_the_yes(self):
        self.assertEqual(self.v("what rules?", "ok I agree"), "yes")
        self.assertEqual(self.v("ما أوافق", "طيب أوافق"), "yes")

    def test_negation_must_be_in_the_same_reply(self):
        self.assertEqual(self.v("لا", "أوافق"), "yes")


class TestSendTexts(unittest.TestCase):
    def test_code_message_has_code_twice_and_hash(self):
        m = engine.code_message("1234")
        self.assertIn("1234 ثم #", m)
        self.assertIn("1234 then #", m)

    def test_code_message_strips_code(self):
        self.assertIn("🔑 كود الدخول: 99 ثم #", engine.code_message(" 99 "))

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

    def test_deprecated_names_keep_old_text_until_r3(self):
        # bot.py (revision 1) still imports these and hardcodes the old button label; R3 deletes both
        self.assertEqual(engine.LABEL_RELEASE, "✅ وافق وأرسلت الرمز")
        self.assertTrue(engine.CONFIRM_TEXT)


class TestTexts(unittest.TestCase):
    def test_header_and_alerts(self):
        self.assertIn("٣", engine.header_text("<@1>", "نورة", 3))
        self.assertIn("<@1>", engine.alert_text("2h", {"unit": "C3", "guest": "A",
                                                        "checkin_at": at(16)}, "<@1>"))
        self.assertIn("حلّ موعد الدخول", engine.alert_text("late", {"unit": "C3", "guest": "A",
                                                                      "checkin_at": at(16)}, ""))


if __name__ == "__main__":
    unittest.main()
