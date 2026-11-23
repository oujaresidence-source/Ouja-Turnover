# -*- coding: utf-8 -*-
"""
«حملات عوجا» cards — the bot.py side: the REAL CampaignCardView / _camp_view / _cw_embed turn
a campaigns.cards card into Discord objects with exactly the card's buttons (relabelled,
restyled), its link buttons, and an embed Discord accepts. Also: the persistent view has a
fixed custom_id on every button (or a restart would orphan every card), and the host wiring
passes a card through and offers send_guest.

Run: python3 -m unittest tests.test_campaign_cards_bot
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-camp")
os.makedirs("/tmp/ouja-test-state-camp", exist_ok=True)

import bot  # noqa: E402
sys.stdout.flush()
import discord  # noqa: E402
from campaigns import cards  # noqa: E402


def _alert(kind, ctx, state="open", **kw):
    a = {"id": 1, "kind": kind, "state": state, "ctx": ctx, "claimed_by": None, "actor": None,
         "action": None, "acted_at": None, "note": None}
    a.update(kw)
    return a


CW = {"guest": "سارة", "first": "سارة", "unit": "HUE 103", "phrase": "عرض نص", "title": "الليلة الثانية بنص",
      "booked": False, "res_status": "inquiry", "who": "نوف", "mins": 15, "by": "1:29 م",
      "offer": {"night1": "2026-11-29", "night1_weekday": "الأحد", "night2": "2026-11-30",
                "night2_free": True, "total": 630, "night1_price": 420, "night2_price": 210,
                "eligible": True, "offer_checkin": "2026-11-29"},
      "links": [["https://app.hostaway.com/inbox/1", "💬 Hostaway"], ["https://airbnb.com/x", "Airbnb"]],
      "conversation_id": 9}


class ViewTests(unittest.TestCase):
    def build(self, card):
        async def go():
            return bot._camp_view(card), bot._cw_embed(card["embed"])
        return asyncio.run(go())

    def test_persistent_view_has_fixed_ids(self):
        async def go():
            return bot.CampaignCardView()
        v = asyncio.run(go())
        self.assertTrue(v.is_persistent())
        ids = sorted(c.custom_id for c in v.children)
        self.assertEqual(ids, sorted("camp_" + a for a in
                                     ("send", "decline", "called", "noanswer", "notint", "claim", "done")))

    def test_codeword_card_becomes_buttons_and_links(self):
        ctx = dict(CW)
        ctx["reply"] = cards.codeword_reply(ctx)
        card = cards.render(_alert("codeword", ctx))
        v, e = self.build(card)
        btn = [c for c in v.children if c.custom_id]
        self.assertEqual([c.custom_id for c in btn], ["camp_send", "camp_claim", "camp_done"])
        self.assertEqual(btn[0].label, "② أرسلت العرض — بلّغ الضيف")
        self.assertEqual(btn[0].style, discord.ButtonStyle.success)
        links = [c for c in v.children if getattr(c, "url", None)]
        self.assertEqual(len(links), 2)
        self.assertTrue(links[0].label.startswith("①"))
        self.assertIn("سارة", e.title)
        self.assertLessEqual(len(e), 6000)                    # Discord's embed size limit

    def test_closed_card_has_no_action_buttons(self):
        card = cards.render(_alert("owner_call", {"guest": "أبو فهد", "last4": "3355", "label": "إيه، كلموني",
                                                  "template": "ouja_owner_recontact_img"},
                                   state="done", actor="فيصل", action="called",
                                   acted_at="2026-11-29T08:10:00"))
        v, e = self.build(card)
        self.assertEqual([c for c in v.children if c.custom_id], [])
        self.assertIn("فيصل", e.footer.text)
        self.assertIn("11:10 ص", e.footer.text)               # UTC 08:10 → Riyadh

    def test_wiring(self):
        caps = bot._campaigns_caps()
        self.assertIn("send_guest", caps)
        import inspect
        self.assertIn("card", inspect.signature(caps["post"]).parameters)


if __name__ == "__main__":
    unittest.main()
