# -*- coding: utf-8 -*-
"""
«رفع التقييم» — the bot.py side (G6): _maint_open_ticket stays byte-for-byte the same for every
existing caller, the review-call ticket says where it came from (R3), the commands are
registered, the nav label exists in BOTH languages, the permission rules cover the API, and the
HOST bridge is fully wired.

Run: python3 -m unittest tests.test_reviewask_bot
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-rv")
os.makedirs("/tmp/ouja-test-state-rv", exist_ok=True)

import bot  # noqa: E402
sys.stdout.flush()
import discord  # noqa: E402
from reviewask import texts as RT  # noqa: E402
from reviewask.host import HOST  # noqa: E402

# The function exactly as it stood on main before Review Push (7c422cb). Frozen here so the
# new keyword arguments can be proven not to change a single byte for the old callers.
ORIGINAL_MAINT_OPEN = r'''
async def _maint_open_ticket(interaction, lid, unit_name, urgency, category,
                             summary, details, location, access):
    guild = interaction.guild
    lid = int(lid)
    ukey, ulbl, uprio, ucolor = _urgency_rec(urgency)
    seq = _next_counter("maint_ticket")
    slug = re.sub(r"^ouja-", "", channel_name(unit_name))[:40]
    ch = await _tk_make_channel(
        guild, "maint", f"صيانة-{seq:03d}-{slug}",
        f"ouja-ticket:maint lid:{lid} seq:{seq}")
    aname, aid = maint_assignee_for(lid)
    today = datetime.now(TZ).date()
    # the same ticket lands in the dashboard tracker (one source of truth)
    desc = details
    if location:
        desc += f"\n\n📍 الموقع: {location}"
    if access:
        desc += f"\n🚪 الدخول: {access}"
    desc += f"\n\n(فُتحت من ديسكورد — روم التذكرة: #{ch.name})"
    dash = _ticket_create(summary, description=desc, lid=lid, priority=uprio,
                          category=category, source="manual", source_ref=f"discord:{ch.id}",
                          created_by=str(interaction.user), assignee=aname)
    try:
        _save_json("tickets.json", _tickets[:1000])
    except Exception:
        pass
    dup_ch = None                       # another OPEN ticket on the same unit? warn, don't block
    for cid, r in _dtk["tickets"].items():
        if r.get("kind") == "maint" and r.get("lid") == lid and r.get("status") != "closed":
            dup_ch = cid
            break
    rec = {"kind": "maint", "seq": seq, "lid": lid, "unit": unit_name,
           "urgency": ukey, "category": category, "summary": summary[:200],
           "opener_id": interaction.user.id, "opener": str(interaction.user),
           "assignee": aname, "assignee_id": aid, "dash_id": dash["id"],
           "status": "open", "created_at": datetime.now(TZ).isoformat(timespec="seconds")}
    _dtk["tickets"][str(ch.id)] = rec
    _dtk_save()
    card = discord.Embed(title=f"🛠️ تذكرة صيانة #{seq:03d} — {ulbl}"[:256],
                         description=f"**{summary}**\n\n{details}"[:4000], color=ucolor)
    card.add_field(name="🏠 الشقة", value=unit_name[:1024], inline=True)
    card.add_field(name="🗂️ التصنيف", value=category, inline=True)
    card.add_field(name="🙋 فاتح التذكرة", value=interaction.user.mention, inline=True)
    if location:
        card.add_field(name="📍 الموقع داخل الشقة", value=location[:1024], inline=True)
    if access:
        card.add_field(name="🚪 ملاحظات الدخول", value=access[:1024], inline=False)
    card.add_field(name="👷 المسؤول", value=_tk_mention(aname, aid), inline=False)
    if dup_ch:
        card.add_field(name="⚠️ تنبيه",
                       value=f"فيه تذكرة ثانية مفتوحة لنفس الشقة: <#{dup_ch}>", inline=False)
    card.set_footer(text="افحصوا الإشغال 🔍 قبل ما تروحون للشقة — وارفعوا صور المشكلة هنا 📎")
    embeds = [card]
    rows = await asyncio.to_thread(_avail_rows, lid, today)   # occupancy snapshot at open
    if rows is not None:
        embeds.append(_avail_embed(unit_name, _avail_classify(rows, lid, today), today))
    mentions = [interaction.user.mention]
    if aid:
        mentions.append(f"<@{int(aid)}>")
    content = " ".join(mentions) + " — تذكرة صيانة جديدة"
    if ukey == "urgent":
        if MAINT_URGENT_ROLE_ID:
            content = f"<@&{MAINT_URGENT_ROLE_ID}> " + content
        content = "🚨 **عاجل** · " + content
    msg = await ch.send(content=content, embeds=embeds, view=MaintTicketView(),
                        allowed_mentions=discord.AllowedMentions(users=True, roles=True))
    rec["card_msg_id"] = msg.id
    _dtk_save()
    try:
        await msg.pin()
    except Exception:
        pass
    return ch

'''


class FakeMsg:
    def __init__(self, mid):
        self.id = mid

    async def pin(self):
        return None


class FakeChannel:
    def __init__(self):
        self.id = 777001
        self.name = "صيانة-007-unit-1"
        self.sent = []

    async def send(self, content=None, embeds=None, view=None, allowed_mentions=None):
        self.sent.append({"content": content, "embeds": [e.to_dict() for e in embeds or []],
                          "view": type(view).__name__})
        return FakeMsg(555)


class FakeUser:
    id = 4242
    mention = "<@4242>"

    def __str__(self):
        return "faisal#0001"


class FakeInteraction:
    def __init__(self):
        self.guild = object()
        self.user = FakeUser()


class Patch:
    """Every outside effect of _maint_open_ticket, faked and restored."""

    def __enter__(self):
        self.saved = {}
        self.ch = FakeChannel()
        ch = self.ch

        async def make_channel(guild, kind, name, topic):
            ch.topic = topic
            return ch
        fakes = {
            "_tk_make_channel": make_channel,
            "_next_counter": lambda name: 7,
            "maint_assignee_for": lambda lid: ("نورة", 222),
            "_avail_rows": lambda lid, today: None,
            "_save_json": lambda *a, **k: None,
            "_dtk_save": lambda: None,
            "get_listings_map": lambda: {},
            "_new_ticket_id": lambda: "T-1",
        }
        for k, v in fakes.items():
            self.saved[k] = getattr(bot, k)
            setattr(bot, k, v)
        self.saved["_dtk"] = bot._dtk
        bot._dtk = {"panels": {}, "tickets": {}}
        self.saved["_tickets"] = list(bot._tickets)
        del bot._tickets[:]
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            if k == "_tickets":
                del bot._tickets[:]
                bot._tickets.extend(v)
            else:
                setattr(bot, k, v)


def _strip_volatile(d):
    d = dict(d)
    d.pop("created_at", None)
    return d


def run_open(fn, **kw):
    with Patch() as p:
        ch = asyncio.run(fn(FakeInteraction(), 1, "Ouja | Unit 1", "normal", "صيانة",
                            "المكيف ما يبرد", "الضيف قال المكيف ضعيف", "الصالة", "", **kw))
        rec = _strip_volatile(bot._dtk["tickets"][str(ch.id)])
        dash = _strip_volatile(bot._tickets[0])
        return p.ch.sent, rec, dash


class TestMaintOpenTicket(unittest.TestCase):
    def original(self):
        ns = {}
        exec(compile(ORIGINAL_MAINT_OPEN, "original_maint", "exec"), bot.__dict__, ns)
        return ns["_maint_open_ticket"]

    def test_old_callers_are_byte_for_byte_unchanged(self):
        old = run_open(self.original())
        new = run_open(bot._maint_open_ticket)
        self.assertEqual(old[0], new[0])            # the message: content + every embed
        self.assertEqual(old[1], new[1])            # the Discord ticket record
        self.assertEqual(old[2], new[2])            # the dashboard ticket
        self.assertEqual(new[2]["source"], "manual")

    def test_review_call_ticket_says_where_it_came_from(self):
        sent, rec, dash = run_open(bot._maint_open_ticket, origin="review_call",
                                   origin_ref="rv:555", origin_room="9911")
        card = sent[0]["embeds"][0]
        self.assertTrue(card["title"].startswith("🛠️ من مكالمة تقييم"))
        src = [f for f in card["fields"] if "المصدر" in f["name"]]
        self.assertEqual(len(src), 1)
        self.assertIn("مكالمة تقييم", src[0]["value"])
        self.assertIn("<#9911>", src[0]["value"])
        self.assertEqual(dash["source"], "review")
        self.assertEqual(dash["source_ref"], "rv:555")
        self.assertEqual(rec["origin"], "review_call")

    def test_summary_and_details_carry_the_words_and_the_caller(self):
        s = RT.maint_summary("Ouja | Narjis 101", "Sara Ali 123")
        self.assertTrue(s.startswith("من مكالمة تقييم — Narjis 101 — Sara"))
        self.assertLessEqual(len(s), 120)
        d = RT.maint_details("المكيف ما يبرد أبد", "أصيل", "555", "2026-10-14")
        for part in ("المكيف ما يبرد أبد", "اتصل: أصيل", "رقم الحجز: 555", "تاريخ الخروج: 2026-10-14"):
            self.assertIn(part, d)


class TestWiring(unittest.TestCase):
    def test_slash_and_prefix_commands_registered(self):
        names = {c.name for c in bot.bot.tree.get_commands()}
        for n in ("reviews-tomorrow", "reviews-today", "reviews-start", "reviews-stop",
                  "review-message", "reviews-report"):
            self.assertIn(n, names)
            self.assertTrue(n.isascii(), "slash names stay ASCII (owner ruling 2026-10-03)")
        for n in ("تقييمات-بكرة", "تقييمات-اليوم", "تقييمات-تشغيل", "تقييمات-ايقاف",
                  "رسالة-التقييم", "تقرير-التقييمات", "reviews-tomorrow", "reviews-start"):
            self.assertIsNotNone(bot.bot.get_command(n), n)

    def test_nav_label_in_both_languages(self):
        labels = bot.NAV_DEF["labels"]
        self.assertEqual(labels["ar"]["rvpush"], "رفع التقييم")
        self.assertTrue(labels["en"]["rvpush"])
        self.assertTrue(any(it["id"] == "rvpush" and it["tk"] == "rvpush" for it in bot.NAV_DEF["items"]))
        ops = [c for c in bot.NAV_DEF["cats"] if c["tk"] == "cat_ops"][0]
        self.assertIn("rvpush", ops["ids"])
        self.assertIn("rvpush", bot._USER_TABS)

    def test_permission_rules_cover_the_api_not_the_public_link(self):
        self.assertIn(("/api/reviewask/", "rvpush"), bot._ROLE_READ_RULES)
        self.assertIn(("/api/reviewask/", "rvpush"), bot._ROLE_WRITE_RULES)
        for prefix, _tab in bot._ROLE_READ_RULES + bot._ROLE_WRITE_RULES:
            self.assertFalse("/rv/abcdefghijklmnop".startswith(prefix), prefix)

    def test_dashboard_stub_and_section(self):
        html = bot.DASHBOARD_HTML
        self.assertIn('id="view_rvpush"', html)
        self.assertIn("if(id==='rvpush') loadRvpush();", html)
        self.assertNotIn("__REVIEWASK_JS_V__", html)
        start = html.index("function loadRvpush(force){")
        stub = html[start:html.index("function loadPermits(force){", start)]
        self.assertLessEqual(len(stub.strip().splitlines()), 15)
        self.assertNotIn(chr(92), stub)

    def test_host_bridge_fully_wired(self):
        bot._rv_wire()
        for attr in ("now", "departures", "reservation", "reviews", "open_ticket_counts",
                     "maint_tickets", "has_recovery", "cover", "wa_number", "guest_links",
                     "listings", "open_room", "known_rooms", "post", "edit", "room_info",
                     "fetch_transcript", "delete_room", "board_channel", "monitor_channel",
                     "link_base", "once_claim", "once_release", "dash_auth", "req_role", "actor",
                     "json_response", "web", "web_thread"):
            self.assertIsNotNone(getattr(HOST, attr), attr)
        self.assertIs(HOST.web_thread, bot.web_thread)

    def test_listener_ids_and_buttons_are_text_only(self):
        self.assertEqual(set(bot._RV_IDS), {"rv_" + k for k in bot._RV_KINDS})
        for k in bot._RV_KINDS:
            self.assertIn(k, RT.BUTTON_LABELS)

        async def build():
            return bot._rv_view(["sent", "replied", ("link", RT.BUTTON_LABELS["wa"], "https://x.test/rv/t")])
        v = asyncio.run(build())
        ids = [getattr(i, "custom_id", None) for i in v.children]
        self.assertEqual(ids[:2], ["rv_sent", "rv_replied"])
        self.assertEqual(v.children[2].style, discord.ButtonStyle.link)


class TestReservationShape(unittest.TestCase):
    def test_departures_use_the_targeted_window(self):
        seen = {}

        def window(ps, pe, s, e):
            seen.update(ps=ps, pe=pe, s=s, e=e)
            return [{"id": 9, "listingMapId": 3, "guestName": "Sara", "phone": "0501112222",
                     "status": "new", "channelName": "Airbnb", "arrivalDate": "2026-10-10",
                     "departureDate": "2026-10-14", "conversationId": 77}]
        saved = (bot._ha_reservations_window, bot.get_listings_map)
        bot._ha_reservations_window = window
        bot.get_listings_map = lambda: {3: "Ouja | Yasmin 3"}
        try:
            rows = bot._rv_departures("2026-10-14", "2026-10-14")
        finally:
            bot._ha_reservations_window, bot.get_listings_map = saved
        self.assertEqual((seen["ps"], seen["pe"]), ("departureStartDate", "departureEndDate"))
        r = rows[0]
        self.assertEqual((r["res_id"], r["lid"], r["unit"], r["channel"], r["departure"]),
                         ("9", 3, "Ouja | Yasmin 3", "airbnb", "2026-10-14"))

    def test_known_rooms_scans_the_family_and_the_archive(self):
        class Ch:
            def __init__(self, cid, topic):
                self.id, self.topic = cid, topic

        class Cat:
            def __init__(self, name, chans):
                self.name, self.text_channels = name, chans

        class G:
            categories = [Cat("طلبات التقييم", [Ch(1, "ouja-rv:11 lid:1 seq:1")]),
                          Cat("طلبات التقييم ٢", [Ch(2, "ouja-rv:12 lid:1 seq:2")]),
                          Cat("📦 أرشيف ١", [Ch(3, "ouja-rv:13 lid:1 seq:3"), Ch(4, "ouja-dp:5 seq:1")]),
                          Cat("صيانه", [Ch(5, "ouja-rv:99 lid:1 seq:9")])]
        saved = bot.bot.get_guild
        bot.bot.get_guild = lambda gid: G()
        try:
            rooms = bot._rv_known_rooms()
        finally:
            bot.bot.get_guild = saved
        self.assertEqual(rooms, {"11": "1", "12": "2", "13": "3"})


if __name__ == "__main__":
    unittest.main()
