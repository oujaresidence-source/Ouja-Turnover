# -*- coding: utf-8 -*-
"""«تدريب مساعد» — the Musaed training export.

The whole value of this feature is the AUTHORSHIP LABEL, and Hostaway does not record
authorship: it only says inbound(guest) vs outbound(us). bot.py rebuilds the rest from
our own send records, so these tests lock the exact thing that could quietly rot and
poison training data:

  - a message we can PROVE we sent is labelled by HOW it was sent (auto / approved /
    edited), and an edited one carries Musaed's original draft;
  - a signed message with no surviving record is «likely», not «Musaed»;
  - an outbound message with neither is UNKNOWN and must never be promoted to «Musaed»;
  - the rotating sign-off is stripped from the body (it is ours, not Musaed's answer);
  - every Musaed line keeps the guest message before it and the guest's next reply;
  - the export is READ-ONLY — it must never post to Hostaway.
"""
import unittest

import bot


def _msg(mid, body, incoming, date):
    return {"id": mid, "body": body, "isIncoming": 1 if incoming else 0, "date": date}


class TrainExport(unittest.TestCase):
    def setUp(self):
        self._api_get = bot.api_get
        self._api_post = bot.api_post
        self._listings = bot.get_listings_map
        self._pause = bot._TRAIN_PAUSE
        bot._TRAIN_PAUSE = 0
        self._learn = list(bot._learning_log)
        self._auto = list(bot._auto_replies)
        bot._learning_log.clear()
        bot._auto_replies.clear()
        bot._TRAIN_CACHE.clear()
        bot.get_listings_map = lambda: {77: "Ouja | Test Unit"}
        self.posted = []
        bot.api_post = lambda *a, **k: self.posted.append(a) or {}

    def tearDown(self):
        bot.api_get = self._api_get
        bot.api_post = self._api_post
        bot.get_listings_map = self._listings
        bot._TRAIN_PAUSE = self._pause
        bot._learning_log.clear()
        bot._learning_log.extend(self._learn)
        bot._auto_replies.clear()
        bot._auto_replies.extend(self._auto)
        bot._TRAIN_CACHE.clear()

    # ---- fixture ---------------------------------------------------------
    def _wire(self, msgs, latest="2999-01-01"):
        conv = {"id": 900, "listingMapId": 77, "recipientName": "فهد",
                "latestMessageDate": latest}

        def fake_get(path, params=None, **kw):
            if path == "/conversations":
                return {"result": [conv] if (params or {}).get("offset", 0) == 0 else []}
            if path == "/conversations/900/messages":
                return {"result": msgs}
            raise AssertionError("unexpected GET " + path)

        bot.api_get = fake_get

    def _codes(self, res):
        return [m["code"] for m in res["threads"][0]["messages"]]

    # ---- the five labels -------------------------------------------------
    def test_auto_reply_is_labelled_musaed_auto(self):
        bot._learning_log.append({"conversation_id": 900, "final_reply": "الرمز 4451",
                                  "bot_draft": "الرمز 4451", "via": "auto",
                                  "was_edited": False, "diff_ratio": 0.0})
        self._wire([_msg(1, "وش رمز الدخول؟", True, "2026-08-01 10:00:00"),
                    _msg(2, "الرمز 4451" + "\n\n" + bot.SIGNATURES_AR[0], False,
                         "2026-08-01 10:01:00")])
        res = bot._train_build(30, 0, 5, True, "")
        self.assertEqual(self._codes(res), ["guest", "musaed_auto"])

    def test_approved_as_is_and_edited_are_told_apart(self):
        bot._learning_log.append({"conversation_id": 900, "final_reply": "أبشر، جاهزة",
                                  "bot_draft": "أبشر، جاهزة", "via": "dashboard_send",
                                  "was_edited": False, "diff_ratio": 0.0})
        bot._learning_log.append({"conversation_id": 900, "final_reply": "الشقة بالدور الثالث",
                                  "bot_draft": "الشقة بالدور الثاني", "via": "dashboard_send",
                                  "was_edited": True, "diff_ratio": 0.4})
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "أبشر، جاهزة", False, "2026-08-01 10:01:00"),
                    _msg(3, "الشقة بالدور الثالث", False, "2026-08-01 10:02:00")])
        res = bot._train_build(30, 0, 5, True, "")
        self.assertEqual(self._codes(res), ["guest", "musaed_approved", "musaed_edited"])
        edited = res["threads"][0]["messages"][2]
        # the correction is the training signal — the draft must survive into the export
        self.assertEqual(edited["draft"], "الشقة بالدور الثاني")

    def test_signed_but_unlogged_is_still_his(self):
        """Owner rule, 2026-08-19: «دايم مساعد ينهي الرسالة باسمه». Audited — the sign-off
        list has not changed since 2026-05-26, so a signed line is his even when the
        bounded log no longer holds it."""
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "رد قديم" + "\n\n" + bot.SIGNATURES_AR[1], False,
                         "2026-08-01 10:01:00")])
        res = bot._train_build(30, 0, 5, False, "")
        self.assertEqual(self._codes(res), ["guest", "musaed_signed"])

    def test_a_retired_sign_off_wording_still_reads_as_his(self):
        """The fallback that makes the rule survive a reworded sign-off: the list is the
        first test, his NAME in a short closing block is the second."""
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "تم الحجز" + "\n\n" + "مع تحيات مساعد ✨", False,
                         "2026-08-01 10:01:00")])
        res = bot._train_build(30, 0, 5, False, "")
        self.assertEqual(self._codes(res), ["guest", "musaed_signed"])
        self.assertEqual(res["threads"][0]["messages"][1]["body"], "تم الحجز")

    def test_his_name_deep_inside_a_paragraph_is_not_a_signature(self):
        """Otherwise any message that merely mentions him would be credited to him."""
        long_tail = "بنرسل لك مساعد من الفريق يشوف الموضوع " * 6
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "تمام" + "\n\n" + long_tail, False, "2026-08-01 10:01:00")])
        res = bot._train_build(30, 0, 5, False, "")
        self.assertEqual(self._codes(res), ["guest", "unknown"])

    def test_unrecorded_outbound_is_never_promoted_to_musaed(self):
        """Somebody replied straight from the Airbnb app. We do not know who. Guessing
        here is what would poison the training set."""
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "رديت عليه من الجوال", False, "2026-08-01 10:01:00")])
        res = bot._train_build(30, 0, 5, False, "")
        self.assertEqual(self._codes(res), ["guest", "unknown"])
        c = res["threads"][0]["counts"]
        self.assertEqual((c["musaed"], c["unknown"]), (0, 1))

    # ---- body + context --------------------------------------------------
    def test_our_signature_is_stripped_from_the_body(self):
        bot._learning_log.append({"conversation_id": 900, "final_reply": "الرمز 4451",
                                  "bot_draft": "الرمز 4451", "via": "auto",
                                  "was_edited": False, "diff_ratio": 0.0})
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "الرمز 4451" + "\n\n" + bot.SIGNATURES_AR[3], False,
                         "2026-08-01 10:01:00")])
        res = bot._train_build(30, 0, 5, True, "")
        m = res["threads"][0]["messages"][1]
        self.assertEqual(m["body"], "الرمز 4451")
        self.assertEqual(m["sig"], bot.SIGNATURES_AR[3])

    def test_musaed_message_keeps_the_guest_before_and_after(self):
        bot._learning_log.append({"conversation_id": 900, "final_reply": "الرمز 4451",
                                  "bot_draft": "الرمز 4451", "via": "auto",
                                  "was_edited": False, "diff_ratio": 0.0})
        self._wire([_msg(1, "وش الرمز؟", True, "2026-08-01 10:00:00"),
                    _msg(2, "الرمز 4451", False, "2026-08-01 10:01:00"),
                    _msg(3, "تسلم يا بطل", True, "2026-08-01 10:05:00")])
        res = bot._train_build(30, 0, 5, True, "")
        m = res["threads"][0]["messages"][1]
        self.assertEqual(m["before"], "وش الرمز؟")
        self.assertEqual(m["after"], "تسلم يا بطل")

    # ---- filters + safety -------------------------------------------------
    def test_only_musaed_drops_threads_musaed_never_touched(self):
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "رد بشري", False, "2026-08-01 10:01:00")])
        self.assertEqual(bot._train_build(30, 0, 5, True, "")["threads"], [])
        self.assertEqual(len(bot._train_build(30, 0, 5, False, "")["threads"]), 1)

    def test_window_excludes_older_conversations(self):
        self._wire([_msg(1, "سؤال", True, "2020-01-01 10:00:00")], latest="2020-01-01")
        self.assertEqual(bot._train_build(30, 0, 5, False, "")["threads"], [])

    def test_search_matches_unit_or_guest(self):
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "رد", False, "2026-08-01 10:01:00")])
        self.assertEqual(len(bot._train_build(30, 0, 5, False, "test unit")["threads"]), 1)
        self.assertEqual(bot._train_build(30, 0, 5, False, "لا يوجد")["threads"], [])

    def test_export_is_read_only(self):
        bot._learning_log.append({"conversation_id": 900, "final_reply": "رد",
                                  "bot_draft": "رد", "via": "auto",
                                  "was_edited": False, "diff_ratio": 0.0})
        self._wire([_msg(1, "سؤال", True, "2026-08-01 10:00:00"),
                    _msg(2, "رد", False, "2026-08-01 10:01:00")])
        bot._train_build(30, 0, 5, True, "")
        self.assertEqual(self.posted, [], "the training export must never write to Hostaway")

    def test_hostaway_failure_reports_instead_of_pretending(self):
        def boom(path, params=None, **kw):
            raise RuntimeError("429")
        bot.api_get = boom
        self.assertIn("error", bot._train_build(30, 0, 5, True, ""))


class TrainChunking(unittest.TestCase):
    """Three months is several hundred conversations at one Hostaway call each. A single
    request would sit for ten minutes and the browser would cut it, so the pull is walked
    in chunks. These lock the cursor arithmetic — an off-by-one here silently SKIPS
    conversations, which looks exactly like 'we only have 30'."""

    def setUp(self):
        self._api_get = bot.api_get
        self._listings = bot.get_listings_map
        self._pause = bot._TRAIN_PAUSE
        bot._TRAIN_PAUSE = 0
        bot.get_listings_map = lambda: {77: "Ouja | Test Unit"}
        bot._TRAIN_CACHE.clear()
        self.convos = [{"id": 1000 + i, "listingMapId": 77, "recipientName": "ضيف %d" % i,
                        "latestMessageDate": "2999-01-01"} for i in range(60)]
        self.fetched = []

        def fake_get(path, params=None, **kw):
            if path == "/conversations":
                off = (params or {}).get("offset", 0)
                return {"result": self.convos[off:off + (params or {}).get("limit", 100)]}
            cid = int(path.split("/")[2])
            self.fetched.append(cid)
            return {"result": [
                {"id": 1, "body": "سؤال", "isIncoming": 1, "date": "2026-08-01 10:00:00"},
                {"id": 2, "body": "رد" + chr(10) * 2 + bot.SIGNATURES_AR[0],
                 "isIncoming": 0, "date": "2026-08-01 10:01:00"}]}

        bot.api_get = fake_get

    def tearDown(self):
        bot.api_get = self._api_get
        bot.get_listings_map = self._listings
        bot._TRAIN_PAUSE = self._pause
        bot._TRAIN_CACHE.clear()

    def test_walking_every_chunk_covers_each_conversation_exactly_once(self):
        offset, seen, rounds = 0, [], 0
        while rounds < 20:
            r = bot._train_build(30, offset, 25, False, "")
            seen += [t["cid"] for t in r["threads"]]
            offset = r["next_offset"]
            rounds += 1
            if r["exhausted"]:
                break
        self.assertEqual(len(seen), 60, "every conversation in the window must be reached")
        self.assertEqual(len(set(seen)), 60, "and none of them twice")
        self.assertEqual(seen, [c["id"] for c in self.convos], "in order, no gaps")

    def test_a_chunk_stops_at_its_scan_budget(self):
        r = bot._train_build(30, 0, 25, False, "")
        self.assertEqual(len(r["threads"]), 25)
        self.assertEqual(r["next_offset"], 25)
        self.assertFalse(r["exhausted"])

    def test_running_out_of_conversations_reports_exhausted(self):
        r = bot._train_build(30, 55, 25, False, "")
        self.assertTrue(r["exhausted"])
        self.assertEqual(len(r["threads"]), 5)

    def test_out_of_window_conversations_end_the_walk(self):
        for c in self.convos:
            c["latestMessageDate"] = "2020-01-01"
        r = bot._train_build(30, 0, 25, False, "")
        self.assertTrue(r["exhausted"])
        self.assertEqual(r["threads"], [])
        self.assertEqual(self.fetched, [], "a conversation outside the window is never fetched")


class TrainSinceMusaed(unittest.TestCase):
    """«من أول يوم رد فيه مساعد» must be DERIVED from the log, never a guessed number."""

    def setUp(self):
        self._learn = list(bot._learning_log)
        bot._learning_log.clear()

    def tearDown(self):
        bot._learning_log.clear()
        bot._learning_log.extend(self._learn)

    def test_days_come_from_the_oldest_logged_reply(self):
        from datetime import timedelta
        old = (bot.datetime.now(bot.TZ).date() - timedelta(days=45)).isoformat()
        bot._learning_log.append({"ts": old + " 09:00:00", "final_reply": "x", "via": "auto"})
        bot._learning_log.append({"ts": "2026-08-18 09:00:00", "final_reply": "y", "via": "auto"})
        self.assertEqual(bot._train_musaed_since_days(), 46)

    def test_an_empty_log_falls_back_to_a_bounded_number(self):
        self.assertEqual(bot._train_musaed_since_days(), 120)


class TrainWiring(unittest.TestCase):
    """The tab must be reachable AND gated — a page missing from the permission matrix
    leaks into every user's sidebar (the whitelist model denies unknown tabs)."""

    def test_tab_is_registered_everywhere_it_must_be(self):
        ids = [i["id"] for i in bot.NAV_DEF["items"]]
        self.assertIn("train", ids)
        self.assertIn("train", bot._USER_TABS)
        self.assertIn("train", bot.NAV_DEF["labels"]["ar"])
        self.assertIn("train", bot.NAV_DEF["labels"]["en"])
        self.assertIn(("/api/train/", "train"), bot._ROLE_READ_RULES)

    def test_the_view_exists_and_the_router_reaches_it(self):
        h = bot.DASHBOARD_HTML
        self.assertIn('id="view_train"', h)
        self.assertIn("function renderTrainAll(", h)
        self.assertIn("if(id==='train') renderTrainAll();", h)

    def test_no_backslash_escape_sneaked_into_the_new_js(self):
        """CLAUDE.md trap 1: DASHBOARD_HTML is a normal Python string, so a backslash
        escape typed into the embedded JS is eaten by Python and kills the login."""
        h = bot.DASHBOARD_HTML
        start = h.index("var TRAIN = {data:null")
        end = h.index("async function loadLearnings(")
        self.assertNotIn(chr(92), h[start:end])


if __name__ == "__main__":
    unittest.main()
