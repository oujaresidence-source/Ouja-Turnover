# -*- coding: utf-8 -*-
"""The ticket-close lock actually locks (bot.py `_tk_lock_channel`).

The bug this guards: closing a ticket only denied @everyone. Discord resolves a
role-level ALLOW above an @everyone DENY, so «مغلقة-صيانة-070-unit» collected 48
messages and «مغلقة-rr-008» 44 in the 30 days AFTER they were closed.

Asserted here: after a close, send_messages is denied for @everyone AND for every
non-admin role that could previously write — while admins (Discord lets them bypass
channel overwrites, full stop) and the bot's own roles are deliberately left alone.
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot as B


class FakeOverwrite:
    """Mimics discord.PermissionOverwrite enough for a merge-then-write."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, item):
        return None


class FakePerms:
    def __init__(self, send_messages=False, administrator=False):
        self.send_messages, self.administrator = send_messages, administrator


class FakeRole:
    def __init__(self, rid, name, can_send=True, admin=False, managed=False):
        self.id, self.name, self.managed = rid, name, managed
        self.can_send = can_send
        self.permissions = FakePerms(send_messages=can_send, administrator=admin)


class FakeChannel:
    def __init__(self, guild, existing=None):
        self.guild = guild
        self.name = "صيانة-070-unit"
        self._existing = existing or {}     # role -> FakeOverwrite already on the channel
        self.written = {}                   # role.name -> overwrite that was saved
        self.write_order = []

    def permissions_for(self, role):
        # what the role can do here today: its own send flag, unless already denied here
        ov = self._existing.get(role)
        if ov is not None and getattr(ov, "send_messages", None) is False:
            return FakePerms(send_messages=False)
        return FakePerms(send_messages=getattr(role, "can_send", False))

    def overwrites_for(self, role):
        src = self._existing.get(role)
        return FakeOverwrite(**dict(src.__dict__)) if src is not None else FakeOverwrite()

    async def set_permissions(self, target, overwrite=None, **kw):
        assert overwrite is not None, "must merge an existing overwrite, never pass kwargs"
        assert not kw, "kwargs replace the whole overwrite — that would wipe view_channel"
        self.written[target.name] = overwrite
        self.write_order.append(target.name)
        self._existing[target] = overwrite


class FakeGuild:
    def __init__(self, roles, me_roles=()):
        self.default_role = FakeRole(0, "@everyone", can_send=True)
        self.roles = [self.default_role] + list(roles)
        self.me = type("Me", (), {"roles": list(me_roles)})()


class CloseLockTests(unittest.TestCase):
    def setUp(self):
        self._pause = B._TK_LOCK_PAUSE
        B._TK_LOCK_PAUSE = 0            # no real sleeping in tests

    def tearDown(self):
        B._TK_LOCK_PAUSE = self._pause

    def _guild(self):
        self.ops = FakeRole(1, "Operation", can_send=True)
        self.mgmt = FakeRole(2, "Managment", can_send=True)
        self.pd = FakeRole(3, "PD", can_send=True)
        self.acct = FakeRole(4, "Accounting", can_send=True)
        self.back = FakeRole(5, "Back Office", can_send=True)
        self.head = FakeRole(6, "Head of Operation", can_send=True, admin=True)
        self.guest = FakeRole(7, "Guest", can_send=False)
        self.botrole = FakeRole(8, "Ouja Bot", can_send=True, managed=True)
        return FakeGuild([self.ops, self.mgmt, self.pd, self.acct, self.back,
                          self.head, self.guest, self.botrole],
                         me_roles=[self.botrole])

    def test_everyone_and_every_non_admin_writer_is_denied(self):
        guild = self._guild()
        ch = FakeChannel(guild)
        locked, admins = asyncio.run(B._tk_lock_channel(ch))

        self.assertIs(ch.written["@everyone"].send_messages, False,
                      "@everyone must still be denied (the original behaviour)")
        for role in ("Operation", "Managment", "PD", "Accounting", "Back Office"):
            self.assertIn(role, ch.written, "%s could write here and was not denied" % role)
            self.assertIs(ch.written[role].send_messages, False)
        self.assertEqual(sorted(locked),
                         sorted(["@everyone", "Operation", "Managment", "PD",
                                 "Accounting", "Back Office"]))

    def test_admin_roles_are_reported_not_pretended_away(self):
        guild = self._guild()
        ch = FakeChannel(guild)
        _locked, admins = asyncio.run(B._tk_lock_channel(ch))
        self.assertEqual(admins, ["Head of Operation"])
        self.assertNotIn("Head of Operation", ch.written,
                         "denying an admin is pointless — Discord lets them bypass overwrites")

    def test_bot_and_managed_roles_keep_writing(self):
        guild = self._guild()
        ch = FakeChannel(guild)
        asyncio.run(B._tk_lock_channel(ch))
        self.assertNotIn("Ouja Bot", ch.written,
                         "the bot must still be able to post and pin the closing notice")

    def test_roles_that_already_cannot_write_are_left_alone(self):
        guild = self._guild()
        ch = FakeChannel(guild)
        asyncio.run(B._tk_lock_channel(ch))
        self.assertNotIn("Guest", ch.written)

    def test_existing_overwrites_are_merged_not_wiped(self):
        """A private ticket hides itself with view_channel=False on @everyone. Writing
        send_messages=False as a keyword would replace that overwrite and expose the
        room to the whole server."""
        guild = self._guild()
        hidden = FakeOverwrite(view_channel=False)
        ch = FakeChannel(guild, existing={guild.default_role: hidden})
        asyncio.run(B._tk_lock_channel(ch))
        saved = ch.written["@everyone"]
        self.assertIs(saved.send_messages, False)
        self.assertIs(saved.view_channel, False, "the private-ticket hide must survive the close")

    def test_no_guild_is_survivable(self):
        ch = type("C", (), {"guild": None})()
        self.assertEqual(asyncio.run(B._tk_lock_channel(ch)), ([], []))


if __name__ == "__main__":
    unittest.main()
