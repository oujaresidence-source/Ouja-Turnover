# -*- coding: utf-8 -*-
"""The money gate: who may close a collection room.

The owner's rule, verbatim: only he and Aseel — the people with **administrator** on in
Discord. So:
  * administrator closes; a user with ONLY manage_guild cannot (that is why _tk_is_admin
    is not reused here — it accepts manage_guild)
  * a plain member cannot; an id in DIRECTPAY_CLOSE_IDS can
  * DIRECTPAY_CLOSE_IDS="  ,,غلط," ⇒ administrators only, NEVER everybody
  * a refused attempt writes a directpay_events row naming the user

Run: python3 -m unittest tests.test_directpay_gate
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                       # noqa: E402
from directpay import config, db, engine, host, service   # noqa: E402


class FakePerms:
    def __init__(self, administrator=False, manage_guild=False):
        self.administrator, self.manage_guild = administrator, manage_guild


class FakeUser:
    def __init__(self, uid, admin=False, manage=False, name="عضو"):
        self.id = uid
        self.guild_permissions = FakePerms(administrator=admin, manage_guild=manage)
        self.display_name = name
        self.name = name


class TestCloseIdsParsing(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("DIRECTPAY_CLOSE_IDS", None)

    def test_empty_means_no_extra_ids(self):
        os.environ.pop("DIRECTPAY_CLOSE_IDS", None)
        self.assertEqual(config.close_ids(), [])

    def test_arabic_comma_tolerated(self):
        os.environ["DIRECTPAY_CLOSE_IDS"] = "111،222, 333"
        self.assertEqual(config.close_ids(), [111, 222, 333])

    def test_garbled_falls_back_to_nobody_extra(self):
        for junk in ("  ,,غلط,", "faisal, aseel", ",,,", "   "):
            os.environ["DIRECTPAY_CLOSE_IDS"] = junk
            self.assertEqual(config.close_ids(), [], junk)


class TestEngineGate(unittest.TestCase):
    def test_administrator_closes(self):
        self.assertTrue(engine.can_close(FakeUser(1, admin=True), []))

    def test_manage_guild_alone_does_not(self):
        self.assertFalse(engine.can_close(FakeUser(2, manage=True), []))

    def test_plain_member_does_not(self):
        self.assertFalse(engine.can_close(FakeUser(3), []))

    def test_listed_id_closes(self):
        self.assertTrue(engine.can_close(FakeUser(444), [444]))
        self.assertFalse(engine.can_close(FakeUser(445), [444]))

    def test_no_permissions_object_fails_closed(self):
        class Bare:
            id = 9
        self.assertFalse(engine.can_close(Bare(), []))
        self.assertFalse(engine.can_close(None, []))
        self.assertFalse(engine.can_close(object(), [1]))


class TestBotGate(unittest.TestCase):
    """The predicate bot.py actually wires to the buttons — written fresh, never _tk_is_admin."""
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="dpgate_state_"))
        import bot as B
        cls.B = B

    def tearDown(self):
        os.environ.pop("DIRECTPAY_CLOSE_IDS", None)

    def test_admin_yes_manage_guild_no_member_no(self):
        B = self.B
        self.assertTrue(B._dp_can_close(FakeUser(1, admin=True)))
        self.assertFalse(B._dp_can_close(FakeUser(2, manage=True)))
        self.assertFalse(B._dp_can_close(FakeUser(3)))

    def test_env_ids_add_closers(self):
        os.environ["DIRECTPAY_CLOSE_IDS"] = "424242"
        self.assertTrue(self.B._dp_can_close(FakeUser(424242)))
        self.assertFalse(self.B._dp_can_close(FakeUser(424243)))

    def test_garbled_env_is_admins_only_never_everybody(self):
        for junk in ("  ,,غلط,", "faisal, aseel", ",,,", ""):
            os.environ["DIRECTPAY_CLOSE_IDS"] = junk
            self.assertFalse(self.B._dp_can_close(FakeUser(424242)), junk)
            self.assertFalse(self.B._dp_can_close(FakeUser(5, manage=True)), junk)
            self.assertTrue(self.B._dp_can_close(FakeUser(6, admin=True)), junk)

    def test_it_is_not_tk_is_admin(self):
        # the loose predicate says yes to manage_guild; ours must not be it
        self.assertTrue(self.B._tk_is_admin(FakeUser(2, manage=True)))
        self.assertFalse(self.B._dp_can_close(FakeUser(2, manage=True)))


class TestRefusalIsLogged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="dpgate_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        db.reset_init_cache()
        host.wire({"notify": None, "log_event": None, "state_dir": cls.tmp})

    def test_refused_attempt_names_the_user(self):
        t = db.open_ticket(reservation_id="8001", total_sar=500.0, created_at="2026-09-10T09:00:00")
        service.refuse(t["id"], "ناصر", "777", "close")
        ev = [e for e in db.events(t["id"]) if e["kind"] == "refused"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["actor"], "ناصر")
        self.assertEqual(ev[0]["actor_id"], "777")
        self.assertIn("close", ev[0]["detail"])
        self.assertEqual(db.ticket(t["id"])["status"], "open")     # nothing else moved


if __name__ == "__main__":
    unittest.main()
