# -*- coding: utf-8 -*-
"""
The owner's remote control — «التحكم» on /compliance.

The rules that matter here are safety rules, not features:
    * a flip made on the page SURVIVES A REDEPLOY (stored value beats the Railway env var)
    * turning something ON needs a typed confirmation; turning it OFF never does
    * one button silences all three at once, with no confirmation at all
    * every change records who made it

Run: python3 -m unittest tests.test_ops_switch
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                   # noqa: E402
from ops import db, switch, notify, turnover, scorecard       # noqa: E402


class SwitchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="opsswitch_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        switch.invalidate()
        self._saved = {}
        for key, (env, _d, _l, _e) in switch.SWITCHES.items():
            self._saved[env] = os.environ.get(env)
            os.environ.pop(env, None)

    def tearDown(self):
        for env, v in self._saved.items():
            if v is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = v
        switch.invalidate()


class TestDefaultsAreSilent(SwitchCase):

    def test_everything_starts_in_dry_run(self):
        for key in switch.SWITCHES:
            self.assertTrue(switch.is_dry(key), key)
        self.assertTrue(switch.panel()["all_quiet"])

    def test_the_env_var_is_the_boot_default(self):
        os.environ["OPS_WARN_DRYRUN"] = "0"
        switch.invalidate()
        self.assertFalse(switch.is_dry("warn_dryrun"))
        self.assertEqual(switch.source("warn_dryrun"), "railway")


class TestTheFlipSurvivesARedeploy(SwitchCase):
    """If the env var won, Railway would silently re-silence the system on the next deploy
    and nobody would notice for weeks."""

    def test_the_stored_value_beats_the_env_var(self):
        os.environ["OPS_WARN_DRYRUN"] = "1"          # Railway still says «silent»
        switch.set_value("warn_dryrun", dry=False, by="فيصل", confirm=switch.CONFIRM_WORD)
        self.assertFalse(switch.is_dry("warn_dryrun"))
        self.assertEqual(switch.source("warn_dryrun"), "page")

    def test_it_is_still_set_after_the_process_forgets_everything(self):
        switch.set_value("nudge_dryrun", dry=False, by="فيصل", confirm=switch.CONFIRM_WORD)
        switch.invalidate()
        db.reset_init_cache()                        # as if the container restarted
        self.assertFalse(switch.is_dry("nudge_dryrun"))

    def test_every_phase_reads_through_the_one_resolver(self):
        self.assertTrue(notify.dryrun())
        self.assertTrue(turnover.dryrun())
        self.assertTrue(scorecard.dryrun())
        for key in switch.SWITCHES:
            switch.set_value(key, dry=False, by="فيصل", confirm=switch.CONFIRM_WORD)
        self.assertFalse(notify.dryrun())
        self.assertFalse(turnover.dryrun())
        self.assertFalse(scorecard.dryrun())


class TestStartingIsHarderThanStopping(SwitchCase):

    def test_going_live_without_the_word_is_refused(self):
        r = switch.set_value("warn_dryrun", dry=False, by="فيصل", confirm="")
        self.assertFalse(r["ok"])
        self.assertTrue(r["need_confirm"])
        self.assertTrue(switch.is_dry("warn_dryrun"))

    def test_a_wrong_word_is_refused(self):
        self.assertFalse(switch.set_value("warn_dryrun", dry=False, by="ف", confirm="نعم")["ok"])
        self.assertTrue(switch.is_dry("warn_dryrun"))

    def test_the_refusal_says_what_going_live_would_do(self):
        r = switch.set_value("warn_dryrun", dry=False, by="ف", confirm="")
        self.assertIn("العمولة", r["effect"])

    def test_stopping_never_needs_a_word(self):
        switch.set_value("warn_dryrun", dry=False, by="فيصل", confirm=switch.CONFIRM_WORD)
        r = switch.set_value("warn_dryrun", dry=True, by="فيصل")     # no confirm at all
        self.assertTrue(r["ok"])
        self.assertTrue(switch.is_dry("warn_dryrun"))

    def test_the_big_red_button_silences_everything_at_once(self):
        for key in switch.SWITCHES:
            switch.set_value(key, dry=False, by="فيصل", confirm=switch.CONFIRM_WORD)
        self.assertFalse(switch.panel()["all_quiet"])
        r = switch.stop_everything("فيصل")
        self.assertTrue(r["ok"])
        self.assertTrue(switch.panel()["all_quiet"])

    def test_an_unknown_key_is_refused(self):
        self.assertFalse(switch.set_value("nonsense", dry=False, by="ف",
                                          confirm=switch.CONFIRM_WORD)["ok"])


class TestItRecordsWhoDidIt(SwitchCase):
    """«who turned the warnings on» is a question that WILL be asked."""

    def test_the_panel_shows_who_changed_each_switch(self):
        switch.set_value("warn_dryrun", dry=False, by="فيصل", confirm=switch.CONFIRM_WORD)
        row = next(s for s in switch.panel()["switches"] if s["key"] == "warn_dryrun")
        self.assertEqual(row["changed_by"], "فيصل")
        self.assertTrue(row["changed_at"])
        self.assertFalse(row["dry"])

    def test_the_panel_names_the_effect_of_every_switch(self):
        for s in switch.panel()["switches"]:
            self.assertTrue(s["label"].strip())
            self.assertTrue(s["effect"].strip())


class TestABrokenDatabaseCannotTurnThingsOn(SwitchCase):
    """The fail-safe direction is silence."""

    def test_a_read_failure_falls_back_to_the_env_default(self):
        original = db.switch_all

        def boom():
            raise RuntimeError("db down")
        db.switch_all = boom
        try:
            switch.invalidate()
            self.assertTrue(switch.is_dry("warn_dryrun"))     # default '1' = silent
        finally:
            db.switch_all = original
            switch.invalidate()


if __name__ == "__main__":
    unittest.main()
