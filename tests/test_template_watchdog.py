"""guard.watchdog — catching a broken template on send #1, not send #14.

The empty door-code template shipped 14 times out of 26. It is a Hostaway automation and
Python cannot fix it — but it can notice, and it must notice ONCE, not forty times.
"""

import os
import tempfile
import unittest

from guard import watchdog
from guard.outbound import check_outbound

T085_i15 = "Your door code:  then #"
OFFHOURS = "We are available every day from 12:00 AM to 12:00 AM"


def host(body):
    return {"isIncoming": 0, "body": body}


def guest(body):
    return {"isIncoming": 1, "body": body}


def is_outbound(m):
    return not m.get("isIncoming")


def scan(msgs, listing_id="101", day="2026-08-20"):
    return watchdog.scan(msgs, listing_id=listing_id, check_outbound=check_outbound,
                         is_outbound=is_outbound, day=day)


class WatchdogTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("STATE_DIR")
        os.environ["STATE_DIR"] = self._tmp.name
        watchdog.reset_for_tests()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = self._old
        self._tmp.cleanup()

    def test_the_empty_door_code_template_raises_exactly_one_finding(self):
        found = scan([host(T085_i15)])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["code"], "UNRENDERED")

    def test_feeding_it_twice_still_raises_only_one(self):
        self.assertEqual(len(scan([host(T085_i15)])), 1)
        self.assertEqual(len(scan([host(T085_i15)])), 0, "a broken template must not spam")

    def test_the_same_break_in_a_different_unit_is_its_own_finding(self):
        self.assertEqual(len(scan([host(T085_i15)], listing_id="101")), 1)
        self.assertEqual(len(scan([host(T085_i15)], listing_id="202")), 1)

    def test_a_different_rule_in_the_same_unit_is_its_own_finding(self):
        self.assertEqual(len(scan([host(T085_i15)])), 1)
        self.assertEqual(len(scan([host("كود الدخول: 7256172263#")])), 1)

    def test_a_new_day_can_raise_again(self):
        self.assertEqual(len(scan([host(T085_i15)], day="2026-08-20")), 1)
        self.assertEqual(len(scan([host(T085_i15)], day="2026-08-21")), 1,
                         "still broken tomorrow is worth saying again")

    def test_the_midnight_to_midnight_template_is_caught(self):
        found = scan([host(OFFHOURS)])
        self.assertEqual(found[0]["code"], "UNRENDERED")

    def test_guest_messages_are_never_scanned(self):
        # A guest quoting their own code back at us is not our template breaking.
        self.assertEqual(scan([guest("الكود اللي وصلني 4821#")]), [])

    def test_healthy_templates_raise_nothing(self):
        self.assertEqual(scan([host("حياك الله 🤍 نورت عوجا"), host("Checkout is at 12:00")]), [])

    def test_it_never_raises_on_junk(self):
        self.assertEqual(watchdog.scan(None, listing_id="1", check_outbound=check_outbound,
                                       is_outbound=is_outbound), [])
        self.assertEqual(scan([{}, {"body": None}]), [])

    def test_a_finding_carries_enough_to_open_a_useful_ticket(self):
        f = scan([host(T085_i15)])[0]
        for key in ("code", "detail", "matched", "body", "listing_id", "key"):
            self.assertIn(key, f)
        self.assertTrue(f["detail"].strip(), "the ticket needs plain Arabic for the team")


class WiringTest(unittest.TestCase):

    def test_the_scan_runs_inside_conv_to_item(self):
        import inspect, bot
        src = inspect.getsource(bot._conv_to_item)
        self.assertIn("_template_watchdog_scan", src)

    def test_it_runs_after_ops_capture_so_it_can_never_skip_it(self):
        import inspect, bot
        src = inspect.getsource(bot._conv_to_item)
        self.assertLess(src.index("_ops_capture_conversation"),
                        src.index("_template_watchdog_scan"))

    def test_the_ticket_says_the_fix_is_not_in_this_repo(self):
        import inspect, bot
        src = inspect.getsource(bot._template_watchdog_scan)
        self.assertIn("Hostaway", src)
        self.assertIn("source_ref", src)      # deduped at the ticket layer too


if __name__ == "__main__":
    unittest.main()
