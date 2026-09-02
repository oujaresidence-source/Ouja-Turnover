# -*- coding: utf-8 -*-
"""The bot.py boundary for the weekend digest: the guarded import, the env defaults
(DRYRUN on), the loop exists and is not running, the five persistent button ids, the
press guard fails CLOSED, the role rules map /api/digest/, and the nav knows the tab.
`import bot` is heavy but other boundary tests already do it."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.pop("DIGEST_DRYRUN", None)      # the clean-env default is what we assert
import bot  # noqa: E402


class _Perms(object):
    def __init__(self, admin=False, manage=False):
        self.administrator, self.manage_guild = admin, manage


class _User(object):
    def __init__(self, perms=None, name="x"):
        self.guild_permissions = perms
        self.display_name = name
        self.roles = []


class _Interaction(object):
    def __init__(self, user):
        self.user = user


class Contract(unittest.TestCase):
    def test_import_and_flags(self):
        self.assertTrue(bot._HAS_DIGEST)
        # Owner ruling 2026-09-03: live by default — the Wednesday post carries the buttons and
        # NOTHING publishes without his tap (digest.approval gates it). DIGEST_DRYRUN=1 still works.
        self.assertFalse(bot.DIGEST_DRYRUN)
        self.assertEqual(bot.DIGEST_DAY, 2)
        self.assertEqual(bot.DIGEST_HOUR, 13)
        self.assertEqual(bot.DIGEST_CHANNEL, "نشرة-الاسبوع")

    def test_loop_exists_and_is_not_running(self):
        self.assertTrue(hasattr(bot, "digest_loop"))
        self.assertFalse(bot.digest_loop.is_running())
        self.assertEqual(bot.digest_loop.minutes, 30)

    def test_five_persistent_buttons(self):
        v = bot.DigestView()
        self.assertIsNone(v.timeout)
        ids = sorted(getattr(c, "custom_id", "") for c in v.children)
        self.assertEqual(ids, sorted(["ouja_dg_approve", "ouja_dg_alt", "ouja_dg_rephrase", "ouja_dg_drop", "ouja_dg_rebuild"]))

    def test_press_guard_fails_closed(self):
        self.assertFalse(bot._digest_may_press(_Interaction(_User(None))))
        self.assertFalse(bot._digest_may_press(_Interaction(_User(_Perms()))))
        self.assertTrue(bot._digest_may_press(_Interaction(_User(_Perms(admin=True)))))
        self.assertTrue(bot._digest_may_press(_Interaction(_User(_Perms(manage=True)))))
        self.assertFalse(bot._digest_may_press(object()))

    def test_role_rules_and_nav(self):
        self.assertIn(("/api/digest/", "digest"), bot._ROLE_WRITE_RULES)
        self.assertIn(("/api/digest/", "digest"), bot._ROLE_READ_RULES)
        self.assertIn("digest", bot._USER_TABS)

    def test_pick_select_enumerates_alternates_and_slots(self):
        issue = {"payload": {"sections": [{"key": "events", "title": "فعاليات ومعارض", "items": [{"ttl": "أ"}, {"ttl": "ب"}]}],
                             "alternates": {"events.0": [{"ttl": "ج"}, {"ttl": "د"}], "events.1": []}}}
        alt = bot._DigestPickSelect(issue, "alt")
        self.assertEqual([o.value for o in alt.options], ["events|0|1", "events|0|2"])
        drop = bot._DigestPickSelect(issue, "drop")
        self.assertEqual([o.value for o in drop.options], ["events|0|0", "events|1|0"])


if __name__ == "__main__":
    unittest.main()
