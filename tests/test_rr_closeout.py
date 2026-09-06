# -*- coding: utf-8 -*-
"""
RR close-out: the money comparison, the owner's WhatsApp message, and the close gate.

Three things are load-bearing here and each one has bitten this repo in another module:

1. THE NUMBERS ARE NEVER RE-INVENTED. The owner's message is a deterministic template;
   the model only supplies a one-line Arabic summary of the story. Every riyal in the
   text comes from the ticket record, so a hallucination cannot move money.
2. WHATSAPP IS NOT DISCORD. Bold is *one* star. A `**bold**` that renders fine in the
   ticket room reaches the owner as literal asterisks, and a message over the cap gets
   silently cut — so the cap trims the STORY, never the money lines.
3. ONLY FAISAL CLOSES. The close gate is checked at the moment of the press, and a
   ticket that was never closed out still cannot be closed by the team.

Run: python3 -m unittest tests.test_rr_closeout
"""

import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402


def ticket(**kw):
    """A realistic RR ticket record, post-enrichment."""
    base = {
        "kind": "rr", "seq": 7, "code": "HMABC123XY", "type": "damage",
        "evidence": ["photos", "quote"],
        "found_date": "2026-08-16",
        "narrative": "الضيف كسر شاشة التلفزيون وترك الشقة بحالة تحتاج تنظيف عميق.",
        "items_raw": "تلفزيون 55 بوصة - 1 - 1316\nتنظيف عميق - 1 - 300",
        "total_raw": "1616",
        "status": "new", "created_at": "2026-08-16T10:00:00",
        "lid": 4321, "unit": "Ouja | الملقا 1", "guest": "أحمد محمد",
        "arrival": "2026-08-12", "departure": "2026-08-15",
    }
    base.update(kw)
    return base


def closeout(**kw):
    base = {"payer": "ouja", "received": 1000.0, "received_raw": "1000",
            "date": "2026-08-20", "ref": "123456789",
            "less_reason": "احتسبوا قيمة استبدال أقل لأن التلفزيون مستعمل.",
            "note": "", "by": "sam#1", "by_id": 99, "at": "2026-08-20T12:00:00",
            "revision": 1, "outcome": "partial", "claimed": 1616.0}
    base.update(kw)
    return base


class FakePerms:
    def __init__(self, administrator=False, manage_guild=False):
        self.administrator = administrator
        self.manage_guild = manage_guild


class FakeUser:
    def __init__(self, uid, admin=False):
        self.id = uid
        self.guild_permissions = FakePerms(administrator=admin)


# --------------------------------------------------------------------------
class TestOutcome(unittest.TestCase):
    """Claimed vs received. 'Nearly equal' must count as full — a halala of float
    drift must never tell an owner we were short-changed."""

    def test_zero_received_is_denied(self):
        self.assertEqual(bot._rr_outcome(1616.0, 0.0), "denied")

    def test_less_is_partial(self):
        self.assertEqual(bot._rr_outcome(1616.0, 1000.0), "partial")

    def test_exact_is_full(self):
        self.assertEqual(bot._rr_outcome(1616.0, 1616.0), "full")

    def test_halala_drift_is_still_full(self):
        self.assertEqual(bot._rr_outcome(1616.0, 1615.7), "full")

    def test_more_than_claimed_is_over(self):
        self.assertEqual(bot._rr_outcome(1616.0, 1800.0), "over")

    def test_no_claim_recorded_is_received(self):
        self.assertEqual(bot._rr_outcome(None, 500.0), "received")

    def test_nothing_entered_is_unknown(self):
        self.assertEqual(bot._rr_outcome(1616.0, None), "unknown")


# --------------------------------------------------------------------------
class TestCloseoutParse(unittest.TestCase):
    TODAY = date(2026, 8, 22)

    def parse(self, **kw):
        args = {"rec": ticket(), "payer": "ouja", "received_raw": "1000",
                "when_raw": "", "ref_raw": "", "reason_raw": "", "note_raw": "",
                "actor": "sam#1", "actor_id": 99, "today": self.TODAY}
        args.update(kw)
        return bot._rr_closeout_parse(**args)

    def test_plain_amount(self):
        co, err = self.parse()
        self.assertIsNone(err)
        self.assertEqual(co["received"], 1000.0)
        self.assertEqual(co["claimed"], 1616.0)
        self.assertEqual(co["outcome"], "partial")

    def test_arabic_digits_and_currency_word(self):
        co, err = self.parse(received_raw="١٬٠٠٠ ر.س")
        self.assertIsNone(err)
        self.assertEqual(co["received"], 1000.0)

    def test_zero_is_valid_not_missing(self):
        co, err = self.parse(received_raw="0")
        self.assertIsNone(err)
        self.assertEqual(co["received"], 0.0)
        self.assertEqual(co["outcome"], "denied")

    def test_garbage_amount_is_refused(self):
        co, err = self.parse(received_raw="ما وصل شي")
        self.assertIsNone(co)
        self.assertTrue(err)

    def test_negative_amount_is_refused(self):
        co, err = self.parse(received_raw="-50")
        self.assertIsNone(co)
        self.assertTrue(err)

    def test_blank_date_falls_back_to_today(self):
        co, _ = self.parse(when_raw="")
        self.assertEqual(co["date"], "2026-08-22")

    def test_iso_date_is_kept(self):
        co, _ = self.parse(when_raw="2026-08-20")
        self.assertEqual(co["date"], "2026-08-20")

    def test_slash_date_is_understood(self):
        co, _ = self.parse(when_raw="20/08/2026")
        self.assertEqual(co["date"], "2026-08-20")

    def test_unparseable_date_keeps_the_words_and_uses_today(self):
        co, _ = self.parse(when_raw="يوم الخميس اللي راح")
        self.assertEqual(co["date"], "2026-08-22")
        self.assertEqual(co["date_raw"], "يوم الخميس اللي راح")

    def test_revision_increments_on_resubmit(self):
        rec = ticket(closeout=closeout(revision=1))
        co, _ = self.parse(rec=rec)
        self.assertEqual(co["revision"], 2)

    def test_unknown_payer_is_refused(self):
        co, err = self.parse(payer="somebody-else")
        self.assertIsNone(co)
        self.assertTrue(err)


# --------------------------------------------------------------------------
class TestOwnerMessage(unittest.TestCase):
    """The text that actually reaches the apartment owner."""

    def msg(self, rec=None, co=None, owner="أبو فهد", story="الضيف كسر التلفزيون.", cap=950):
        return bot._rr_wa_owner_msg(rec or ticket(), co or closeout(),
                                    owner_name=owner, story_line=story, cap=cap)

    # --- formatting: WhatsApp, not Discord ---
    def test_uses_single_star_bold_never_double(self):
        m = self.msg()
        self.assertNotIn("**", m)
        self.assertIn("*أبو فهد*", m)

    def test_no_markdown_links_or_backticks(self):
        m = self.msg()
        for bad in ("```", "](", "http://", "https://"):
            self.assertNotIn(bad, m)

    def test_no_empty_bold_when_owner_unknown(self):
        m = self.msg(owner="")
        self.assertNotIn("**", m)
        self.assertNotIn("* *", m)

    def test_never_leaves_a_triple_blank_line(self):
        m = self.msg(co=closeout(ref="", note="", less_reason=""))
        self.assertNotIn("\n\n\n", m)

    # --- the facts ---
    def test_carries_unit_guest_and_dates(self):
        m = self.msg()
        self.assertIn("Ouja | الملقا 1", m)
        self.assertIn("أحمد محمد", m)
        self.assertIn("12/08/2026", m)
        self.assertIn("15/08/2026", m)

    def test_carries_the_story_line(self):
        self.assertIn("الضيف كسر التلفزيون.", self.msg())

    def test_falls_back_to_the_teams_own_words_without_the_model(self):
        m = self.msg(story="")
        self.assertIn("كسر شاشة التلفزيون", m)

    def test_lists_the_damaged_items(self):
        m = self.msg()
        self.assertIn("تلفزيون 55 بوصة", m)
        self.assertIn("تنظيف عميق", m)

    # --- the money ---
    def test_partial_shows_claimed_received_difference_and_reason(self):
        m = self.msg()
        self.assertIn("1,616", m)          # claimed
        self.assertIn("1,000", m)          # received
        self.assertIn("616", m)            # the gap
        self.assertIn("الفرق", m)
        self.assertIn("قيمة استبدال أقل", m)

    def test_full_recovery_has_no_difference_line(self):
        m = self.msg(co=closeout(received=1616.0, outcome="full", less_reason=""))
        self.assertNotIn("الفرق", m)
        self.assertIn("1,616", m)

    def test_denied_says_so_and_gives_the_reason(self):
        m = self.msg(co=closeout(received=0.0, outcome="denied",
                                 less_reason="اعتبروا البلاغ متأخر."))
        self.assertIn("رفض", m)
        self.assertIn("اعتبروا البلاغ متأخر.", m)
        self.assertNotIn("الفرق", m)

    def test_no_claimed_total_recorded_skips_the_claimed_line(self):
        rec = ticket(total_raw="")
        m = self.msg(rec=rec, co=closeout(claimed=None, outcome="received"))
        self.assertNotIn("طالبنا", m)
        self.assertIn("1,000", m)

    # --- whose money is it (the trap the owner and I found while planning) ---
    def test_ouja_paid_never_promises_the_owner_money(self):
        m = self.msg(co=closeout(payer="ouja"))
        self.assertIn("على حساب عوجا", m)
        self.assertNotIn("من نصيبك", m)

    def test_owner_paid_says_the_money_is_his(self):
        m = self.msg(co=closeout(payer="owner"))
        self.assertIn("على حسابك", m)
        self.assertIn("من نصيبك", m)

    def test_no_repair_says_no_repair(self):
        m = self.msg(co=closeout(payer="none"))
        self.assertNotIn("على حساب عوجا", m)
        self.assertNotIn("على حسابك", m)

    def test_owner_paid_and_denied_promises_nothing(self):
        m = self.msg(co=closeout(payer="owner", received=0.0, outcome="denied"))
        self.assertNotIn("من نصيبك", m)

    # --- optional parts ---
    def test_case_reference_included_when_given(self):
        self.assertIn("123456789", self.msg())

    def test_case_reference_omitted_when_blank(self):
        m = self.msg(co=closeout(ref=""))
        self.assertNotIn("مرجع القضية", m)

    def test_note_is_passed_through(self):
        m = self.msg(co=closeout(note="بنركب تلفزيون جديد الأسبوع الجاي."))
        self.assertIn("بنركب تلفزيون جديد", m)

    def test_photos_line_only_when_we_actually_have_photos(self):
        self.assertIn("الصور", self.msg())
        self.assertNotIn("الصور", self.msg(rec=ticket(evidence=["chat"])))

    # --- the cap ---
    def test_long_story_and_many_items_stay_under_the_cap(self):
        rec = ticket(narrative="ت" * 1500,
                     items_raw="\n".join("بند رقم %d - 1 - 100" % i for i in range(12)))
        m = self.msg(rec=rec, co=closeout(note="ن" * 400,
                                          less_reason="س" * 300),
                     story="ق" * 600)
        self.assertLessEqual(len(m), 950)

    def test_the_money_lines_survive_the_trim(self):
        rec = ticket(narrative="ت" * 1500,
                     items_raw="\n".join("بند رقم %d - 1 - 100" % i for i in range(12)))
        m = self.msg(rec=rec, story="ق" * 900)
        self.assertIn("اللي استلمناه", m)
        self.assertIn("1,000", m)
        self.assertIn("1,616", m)

    def test_short_message_is_not_trimmed_at_all(self):
        m = self.msg()
        self.assertLess(len(m), 950)
        self.assertNotIn("…", m.split("*الأضرار:*")[0])


# --------------------------------------------------------------------------
class TestEnrichStamp(unittest.TestCase):
    """The enrichment used to be used and thrown away — the close-out needs the
    apartment and the owner behind it, months later, without a second lookup."""

    def test_stamps_unit_guest_and_dates(self):
        rec = {"kind": "rr"}
        bot._rr_stamp_enrich(rec, {"guest": "سارة", "unit": "Ouja | حطين",
                                   "arrival": "2026-08-01", "departure": "2026-08-04",
                                   "lid": 99})
        self.assertEqual(rec["unit"], "Ouja | حطين")
        self.assertEqual(rec["guest"], "سارة")
        self.assertEqual(rec["lid"], 99)

    def test_empty_enrichment_writes_nothing(self):
        rec = {"kind": "rr", "unit": "Ouja | حطين"}
        bot._rr_stamp_enrich(rec, {})
        self.assertEqual(rec["unit"], "Ouja | حطين")

    def test_never_overwrites_a_known_unit_with_a_blank(self):
        rec = {"kind": "rr", "unit": "Ouja | حطين"}
        bot._rr_stamp_enrich(rec, {"guest": "سارة", "unit": ""})
        self.assertEqual(rec["unit"], "Ouja | حطين")
        self.assertEqual(rec["guest"], "سارة")


# --------------------------------------------------------------------------
class TestOwnerContact(unittest.TestCase):
    def test_phone_found_through_the_listing_id(self):
        with mock.patch.object(bot, "_owner_info_by_lid",
                               return_value={"owner": "أبو فهد", "apartment": "101A"}), \
             mock.patch.object(bot, "_load_json",
                               return_value={"owners": {"أبو فهد": {"phone": "0501234567"}}}):
            name, phone = bot._rr_owner_contact(ticket())
        self.assertEqual(name, "أبو فهد")
        self.assertEqual(phone, "0501234567")

    def test_missing_phone_is_empty_not_a_crash(self):
        with mock.patch.object(bot, "_owner_info_by_lid",
                               return_value={"owner": "أبو فهد"}), \
             mock.patch.object(bot, "_load_json", return_value={"owners": {}}):
            name, phone = bot._rr_owner_contact(ticket())
        self.assertEqual(name, "أبو فهد")
        self.assertEqual(phone, "")

    def test_unknown_apartment_returns_blanks(self):
        with mock.patch.object(bot, "_owner_info_by_lid", return_value=None), \
             mock.patch.object(bot, "_owner_info", return_value=None), \
             mock.patch.object(bot, "_load_json", return_value={"owners": {}}):
            name, phone = bot._rr_owner_contact({"kind": "rr"})
        self.assertEqual(name, "")
        self.assertEqual(phone, "")

    def test_a_broken_registry_never_takes_the_closeout_down(self):
        with mock.patch.object(bot, "_owner_info_by_lid", side_effect=RuntimeError("boom")):
            name, phone = bot._rr_owner_contact(ticket())
        self.assertEqual((name, phone), ("", ""))


# --------------------------------------------------------------------------
class TestCloseGate(unittest.TestCase):
    def test_ordinary_team_member_cannot_close(self):
        with mock.patch.dict(os.environ, {"RR_CLOSE_IDS": ""}, clear=False):
            self.assertFalse(bot._rr_can_close(FakeUser(1234)))

    def test_admin_can_close(self):
        with mock.patch.dict(os.environ, {"RR_CLOSE_IDS": ""}, clear=False):
            self.assertTrue(bot._rr_can_close(FakeUser(1234, admin=True)))

    def test_named_id_can_close(self):
        with mock.patch.dict(os.environ, {"RR_CLOSE_IDS": "1234,5678"}, clear=False):
            self.assertTrue(bot._rr_can_close(FakeUser(5678)))

    def test_garbled_env_does_not_open_the_door_to_everyone(self):
        with mock.patch.dict(os.environ, {"RR_CLOSE_IDS": "؟؟؟, ,"}, clear=False):
            self.assertFalse(bot._rr_can_close(FakeUser(1234)))


# --------------------------------------------------------------------------
class TestSummary(unittest.TestCase):
    """The read-only strip on the dashboard. Money counts in the month it LANDED."""

    def store(self):
        return {
            "1": ticket(seq=1, unit="Ouja | الملقا 1", total_raw="1616", status="closed",
                        closeout=closeout(received=1000.0, at="2026-09-02T10:00:00",
                                          claimed=1616.0)),
            "2": ticket(seq=2, unit="Ouja | الملقا 1", total_raw="500", status="closed",
                        closeout=closeout(received=500.0, at="2026-09-05T10:00:00",
                                          claimed=500.0)),
            "3": ticket(seq=3, unit="Ouja | حطين", total_raw="900", status="new",
                        awaiting_close=True,
                        closeout=closeout(received=0.0, at="2026-09-06T10:00:00",
                                          claimed=900.0)),
            "4": ticket(seq=4, unit="Ouja | حطين", total_raw="700", status="closed",
                        closeout=closeout(received=700.0, at="2026-08-30T10:00:00",
                                          claimed=700.0)),
            "5": ticket(seq=5, unit="Ouja | النرجس", total_raw="200", status="new"),
            "9": {"kind": "maint", "seq": 9, "status": "new"},
        }

    def test_month_totals_only_count_that_month(self):
        s = bot._rr_summary(self.store(), month="2026-09")
        self.assertEqual(s["claimed"], 3016.0)      # 1616 + 500 + 900
        self.assertEqual(s["received"], 1500.0)     # 1000 + 500 + 0
        self.assertEqual(s["n"], 3)

    def test_recovery_rate(self):
        s = bot._rr_summary(self.store(), month="2026-09")
        self.assertAlmostEqual(s["rate"], 1500.0 / 3016.0 * 100, places=2)

    def test_open_and_awaiting_counts_ignore_maintenance_tickets(self):
        s = bot._rr_summary(self.store(), month="2026-09")
        self.assertEqual(s["open"], 2)              # tickets 3 and 5
        self.assertEqual(s["awaiting"], 1)          # ticket 3

    def test_per_apartment_breakdown(self):
        s = bot._rr_summary(self.store(), month="2026-09")
        by = {r["unit"]: r for r in s["by_unit"]}
        self.assertEqual(by["Ouja | الملقا 1"]["received"], 1500.0)
        self.assertEqual(by["Ouja | الملقا 1"]["n"], 2)
        self.assertEqual(by["Ouja | حطين"]["received"], 0.0)
        self.assertNotIn("Ouja | النرجس", by)       # no close-out, no money row

    def test_unknown_apartment_is_labelled_not_dropped(self):
        st = {"1": ticket(unit="", closeout=closeout(at="2026-09-02T10:00:00"))}
        s = bot._rr_summary(st, month="2026-09")
        self.assertEqual(s["by_unit"][0]["unit"], "غير محدد")

    def test_all_time_totals_span_every_month(self):
        s = bot._rr_summary(self.store(), month="2026-09")
        self.assertEqual(s["all"]["received"], 2200.0)   # + August's 700
        self.assertEqual(s["all"]["n"], 4)

    def test_empty_store_is_zeroes_not_a_crash(self):
        s = bot._rr_summary({}, month="2026-09")
        self.assertEqual((s["claimed"], s["received"], s["n"]), (0.0, 0.0, 0))
        self.assertEqual(s["rate"], 0.0)
        self.assertEqual(s["by_unit"], [])

    def test_a_corrupt_record_is_skipped_not_fatal(self):
        st = {"1": {"kind": "rr", "closeout": "not-a-dict"}, "2": None,
              "3": ticket(closeout=closeout(at="2026-09-02T10:00:00"))}
        s = bot._rr_summary(st, month="2026-09")
        self.assertEqual(s["n"], 1)


# --------------------------------------------------------------------------
class TestWiring(unittest.TestCase):
    """The parts that are invisible until they are missing in production."""

    def test_the_summary_endpoint_exists(self):
        self.assertTrue(callable(getattr(bot, "_api_rr_summary", None)))

    def test_the_summary_inherits_the_tickets_read_permission(self):
        prefixes = [p for p, _perm in bot._ROLE_READ_RULES]
        hit = next((p for p in prefixes if "/api/tickets/rr-summary".startswith(p)), None)
        self.assertIsNotNone(hit, "rr-summary is not covered by any read rule")
        perm = dict(bot._ROLE_READ_RULES)[hit]
        self.assertEqual(perm, "tickets")

    def test_the_dashboard_strip_and_its_loader_are_in_the_served_page(self):
        H = bot.DASHBOARD_HTML
        for needle in ('id="rrSummary"', "function loadRRSummary(",
                       "function _renderRRSummary(", "/api/tickets/rr-summary"):
            self.assertIn(needle, H, needle)

    def test_the_dashboard_string_is_still_balanced(self):
        H = bot.DASHBOARD_HTML
        self.assertEqual(H.count("{"), H.count("}"))
        self.assertEqual(H.count("("), H.count(")"))
        self.assertEqual(H.count("`") % 2, 0)

    def test_every_dashboard_script_block_still_parses(self):
        try:
            import esprima
        except ImportError:                      # dev-only dependency
            self.skipTest("esprima not installed")
        import re as _re
        blocks = _re.findall(r"<script>(.*?)</script>", bot.DASHBOARD_HTML, _re.S)
        self.assertTrue(blocks)
        for i, js in enumerate(blocks):
            with self.subTest(block=i):
                esprima.parseScript(js)

    def test_the_status_keys_the_old_ticket_door_listens_for_still_exist(self):
        # tickets opened before this feature reach the close-out ONLY through these two
        keys = {k for k, _lbl in bot._RR_STATUS}
        self.assertIn("paid", keys)
        self.assertIn("denied", keys)

    def test_the_card_buttons_keep_their_ids(self):
        ids = {getattr(c, "custom_id", None) for c in bot.RRTicketView().children}
        self.assertIn("rr_close", ids)      # unchanged id = the gate covers OLD cards too
        self.assertIn("rr_regen", ids)

    def test_recording_the_settlement_is_a_command_not_a_card_button(self):
        # A new card button would only ever appear on tickets opened after the deploy;
        # every claim already in flight would have no door. The command works in all of them.
        ids = {getattr(c, "custom_id", None) for c in bot.RRTicketView().children}
        self.assertNotIn("rr_closeout", ids)

    def test_the_slash_command_is_registered_with_its_payer_choices(self):
        cmd = bot.bot.tree.get_command("rr-close")
        self.assertIsNotNone(cmd, "/rr-close is not in the command tree")
        self.assertRegex(cmd.name, r"^[a-z0-9_-]+$")   # a rejected name fails the WHOLE sync
        opt = {p.name: p for p in getattr(cmd, "parameters", [])}.get("payer")
        self.assertIsNotNone(opt, "/rr-close has no payer option")
        self.assertEqual({c.value for c in opt.choices}, set(bot._RR_PAYER_KEYS))

    def test_the_form_she_fills_is_in_english(self):
        def arabic(s):
            return any("؀" <= c <= "ۿ" for c in s)
        modal = bot.RRCloseoutModal("ouja")
        labels = [str(c.label) for c in modal.children]
        self.assertEqual(len(labels), 5)                       # Discord's hard ceiling
        for lb in labels:
            self.assertFalse(arabic(lb), "form label is not English: " + lb)
            self.assertLessEqual(len(lb), 45)                  # Discord's label limit
        for c in modal.children:                               # placeholders too
            self.assertFalse(arabic(str(getattr(c, "placeholder", "") or "")))
        self.assertFalse(arabic(str(modal.title)))
        self.assertLessEqual(len(str(modal.title)), 45)

    def test_the_owner_message_buttons_are_persistent(self):
        view = bot.RRCloseoutView()
        ids = {getattr(c, "custom_id", None) for c in view.children}
        self.assertEqual(ids, {"rr_sent", "rr_approve_close", "rr_send_back"})
        self.assertIsNone(view.timeout)     # a redeploy must not orphan these buttons

    def test_the_story_writer_is_forbidden_from_touching_numbers(self):
        sys_prompt = bot._RR_STORY_SYSTEM
        self.assertIn("never add a number", sys_prompt)
        self.assertIn("NEVER say who paid", sys_prompt)


# --------------------------------------------------------------------------
class TestEnglishInArabicOut(unittest.TestCase):
    """She works the claim with Airbnb in English; the owner reads Arabic."""

    def test_the_translated_reason_replaces_the_english_one(self):
        co = closeout(less_reason="They valued the TV as used and paid a depreciated rate.")
        m = bot._rr_wa_owner_msg(ticket(), co, owner_name="أبو فهد", story_line="س",
                                 reason_ar="اعتبروا التلفزيون مستعملاً واحتسبوا قيمة أقل.")
        self.assertIn("اعتبروا التلفزيون مستعملاً", m)
        self.assertNotIn("depreciated", m)

    def test_the_translated_note_replaces_the_english_one(self):
        co = closeout(note="We will install the new TV next week.")
        m = bot._rr_wa_owner_msg(ticket(), co, owner_name="أبو فهد", story_line="س",
                                 note_ar="بنركب التلفزيون الجديد الأسبوع الجاي.")
        self.assertIn("بنركب التلفزيون الجديد", m)
        self.assertNotIn("next week", m)

    def test_english_survives_verbatim_when_translation_fails(self):
        # Worse than Arabic, far better than a blank line where her explanation was.
        co = closeout(less_reason="Filed outside the 14-day window.")
        m = bot._rr_wa_owner_msg(ticket(), co, owner_name="أبو فهد", story_line="س")
        self.assertIn("Filed outside the 14-day window.", m)

    def test_a_dead_model_returns_the_originals_and_says_so(self):
        with mock.patch.object(bot, "claude_json", side_effect=RuntimeError("down")):
            got = bot._rr_ar_texts(ticket(), closeout(less_reason="They refused.",
                                                      note="Sorry for the trouble."))
        self.assertFalse(got["ok"])
        self.assertEqual(got["reason"], "They refused.")
        self.assertEqual(got["note"], "Sorry for the trouble.")
        self.assertEqual(got["story"], "")

    def test_a_junk_model_answer_does_not_blank_her_words(self):
        with mock.patch.object(bot, "claude_json", return_value={"story": "", "reason": ""}):
            got = bot._rr_ar_texts(ticket(), closeout(less_reason="They refused."))
        self.assertEqual(got["reason"], "They refused.")

    def test_a_good_translation_is_used_and_marked_ok(self):
        with mock.patch.object(bot, "claude_json",
                               return_value={"story": "الضيف كسر التلفزيون.",
                                             "reason": "اعتبروا البلاغ متأخراً.",
                                             "note": "نعتذر عن الإزعاج."}):
            got = bot._rr_ar_texts(ticket(), closeout(less_reason="Filed late.",
                                                      note="Sorry."))
        self.assertTrue(got["ok"])
        self.assertEqual(got["story"], "الضيف كسر التلفزيون.")
        self.assertEqual(got["reason"], "اعتبروا البلاغ متأخراً.")
        self.assertEqual(got["note"], "نعتذر عن الإزعاج.")

    def test_nothing_to_translate_is_not_a_failure(self):
        with mock.patch.object(bot, "claude_json", side_effect=AssertionError("must not call")):
            got = bot._rr_ar_texts({"kind": "rr"}, closeout(less_reason="", note=""))
        self.assertTrue(got["ok"])


if __name__ == "__main__":
    unittest.main()
