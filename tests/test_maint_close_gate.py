# -*- coding: utf-8 -*-
"""Only three named people may close a صيانة ticket, and not without proof.

Before this, ANY member who could see the room could press «✅ إغلاق التذكرة» and the
ticket locked — no invoice, no photo, no trace of who decided it was done.

Asserted here:
  * the three ids from the owner are the closers; a random member is refused
  * server admins keep the carve-out (owner-approved)
  * a garbled MAINT_CLOSE_IDS falls back to the three, never to "everybody"
  * proof = any attachment from anyone in the room; a history hiccup never traps a ticket
  * the shared confirm view re-checks at the press — and RR/proc, which pass no guard,
    behave exactly as they did before
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot as B

OWNER_IDS = [1449076419316682812, 1486735916767903915, 288811937662238720]


class FakePerms:
    def __init__(self, administrator=False, manage_guild=False):
        self.administrator, self.manage_guild = administrator, manage_guild


class FakeUser:
    def __init__(self, uid, admin=False):
        self.id = uid
        self.guild_permissions = FakePerms(administrator=admin)


class FakeMsg:
    def __init__(self, attachments=()):
        self.attachments = list(attachments)


class FakeChannel:
    """history() is an async iterator, like discord.py's."""

    def __init__(self, msgs=(), boom=False):
        self._msgs, self._boom = list(msgs), boom

    def history(self, limit=100):
        msgs, boom = self._msgs[:limit], self._boom

        class _It:
            def __aiter__(self_inner):
                self_inner._i = 0
                return self_inner

            async def __anext__(self_inner):
                if boom:
                    raise RuntimeError("discord is having a moment")
                if self_inner._i >= len(msgs):
                    raise StopAsyncIteration
                self_inner._i += 1
                return msgs[self_inner._i - 1]

        return _It()


def run(coro):
    # asyncio.run, not get_event_loop: under `unittest discover` a sibling test may have
    # already closed the ambient loop, and these tests would error instead of running.
    return asyncio.run(coro)


class TestWhoMayClose(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("MAINT_CLOSE_IDS", None)

    def test_the_three_may_close(self):
        for uid in OWNER_IDS:
            self.assertTrue(B._maint_can_close(FakeUser(uid)), uid)

    def test_a_random_member_may_not(self):
        self.assertFalse(B._maint_can_close(FakeUser(999000111222333444)))

    def test_admin_carve_out(self):
        self.assertTrue(B._maint_can_close(FakeUser(555, admin=True)))

    def test_env_override_replaces_the_list(self):
        os.environ["MAINT_CLOSE_IDS"] = "777, 888"
        self.assertEqual(B._maint_close_ids(), [777, 888])
        self.assertTrue(B._maint_can_close(FakeUser(777)))
        self.assertFalse(B._maint_can_close(FakeUser(OWNER_IDS[0])))

    def test_garbled_env_falls_back_to_the_three_not_to_everyone(self):
        for junk in ("", "   ", "faisal, ahmed", ",,,"):
            os.environ["MAINT_CLOSE_IDS"] = junk
            self.assertEqual(B._maint_close_ids(), OWNER_IDS, junk)
            self.assertFalse(B._maint_can_close(FakeUser(424242)), junk)


class TestProofRequirement(unittest.TestCase):
    def test_no_files_means_no_proof(self):
        ch = FakeChannel([FakeMsg(), FakeMsg(), FakeMsg()])
        self.assertFalse(run(B._maint_has_proof(ch)))

    def test_a_file_from_anyone_counts(self):
        ch = FakeChannel([FakeMsg(), FakeMsg(["invoice.pdf"]), FakeMsg()])
        self.assertTrue(run(B._maint_has_proof(ch)))

    def test_empty_room_has_no_proof(self):
        self.assertFalse(run(B._maint_has_proof(FakeChannel())))

    def test_history_failure_never_traps_a_ticket_open(self):
        self.assertTrue(run(B._maint_has_proof(FakeChannel(boom=True))))


class FakeResponse:
    def __init__(self):
        self.edited, self.sent, self.modal = [], [], []

    async def edit_message(self, content=None, view=None):
        self.edited.append(content)

    async def send_message(self, content=None, **kw):
        self.sent.append(content)

    async def send_modal(self, modal):
        self.modal.append(modal)


class FakeInteraction:
    def __init__(self, user):
        self.user, self.response = user, FakeResponse()
        self.channel = FakeChannel()
        self.channel_id = 1


class TestConfirmWindowRechecks(unittest.TestCase):
    """The «متأكد؟» window lives 120 seconds — permission is re-checked at the press."""

    def setUp(self):
        self.closed = []
        self._real = B._tk_close

        async def spy(interaction):
            self.closed.append(interaction.user.id)

        B._tk_close = spy

    def tearDown(self):
        B._tk_close = self._real

    def _press_yes(self, view, user):
        it = FakeInteraction(user)
        run(view.yes.callback(it))          # discord.py binds the view into the callback
        return it

    def test_guarded_confirm_refuses_an_outsider(self):
        v = B._TkCloseConfirm(guard=B._maint_can_close, refuse_msg="no")
        it = self._press_yes(v, FakeUser(12345))
        self.assertEqual(self.closed, [])
        self.assertEqual(it.response.edited, ["no"])

    def test_guarded_confirm_lets_a_closer_through(self):
        v = B._TkCloseConfirm(guard=B._maint_can_close)
        self._press_yes(v, FakeUser(OWNER_IDS[0]))
        self.assertEqual(self.closed, [OWNER_IDS[0]])

    def test_unguarded_confirm_is_unchanged_for_rr_and_proc(self):
        v = B._TkCloseConfirm()
        self._press_yes(v, FakeUser(12345))
        self.assertEqual(self.closed, [12345])


class TestRRAndProcUntouched(unittest.TestCase):
    """The owner asked for maintenance only — RR must not inherit the gate."""

    def test_rr_close_button_opens_an_unguarded_confirm(self):
        self.assertIsNone(getattr(B._TkCloseConfirm(), "guard"))


if __name__ == "__main__":
    unittest.main()
