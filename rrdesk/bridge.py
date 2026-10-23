# -*- coding: utf-8 -*-
"""
rrdesk.bridge — the ONLY file in this package that touches discord.py objects.

bot.py hands over the bot and the discord module through HOST (no `import bot`), registers
five listeners that call into here, a one-minute loop that calls tick_once(), and slash /
prefix commands that call the cmd_* coroutines. Everything blocking runs on rrdesk's own pool
(outbox.run_blocking) — never asyncio.to_thread, never the event loop.

Every listener swallows its own errors and logs an event: a bug here must never stop the bot.
"""

from . import db, flow, outbox, study, texts, translate
from .host import HOST

NL = chr(10)
PIN = "📌"
MODAL_KINDS = ("not_what", "cancel", "reassign", "excuse", "unavailable")
CID_TO_KIND = {"rd:ack": "ack", "rd:deliver": "deliver", "rd:gotit": "got_it",
               "rd:notwhat": "not_what", "rd:cancel": "cancel", "rd:reassign": "reassign",
               "rd:qyes": "q_yes", "rd:qno": "q_no", "rd:img": "image", "rd:excuse": "excuse",
               "rd:unavail": "unavailable"}


def _d():
    return HOST.require("discord")


def _bot():
    return HOST.require("bot")


def _tz_now():
    return HOST.now() if HOST.now else db.now()


def _local(dt):
    try:
        return dt.astimezone(_tz_now().tzinfo)
    except Exception:
        return _tz_now()


# ------------------------------------------------------------------ message → dict

def _is_rr_channel(ch):
    """Cheap pre-filter on the event loop: a dict lookup in bot.py's ticket store."""
    try:
        if HOST.rr_record and HOST.rr_record(str(ch.id)):
            return True
        pid = getattr(ch, "parent_id", None)
        return bool(pid and HOST.rr_record and HOST.rr_record(str(pid)))
    except Exception:
        return False


def message_dict(message):
    ch = message.channel
    me = getattr(_bot(), "user", None)
    me_id = getattr(me, "id", None)
    embeds = []
    for e in message.embeds or []:
        try:
            embeds.append({"title": e.title or "", "description": e.description or "",
                           "fields": [{"name": f.name or "", "value": f.value or ""} for f in e.fields],
                           "footer": (e.footer.text if e.footer else "") or ""})
        except Exception:
            continue
    ref_author = None
    try:
        res = message.reference.resolved if message.reference else None
        if res is not None and getattr(res, "author", None) is not None and not res.author.bot:
            ref_author = str(res.author.id)
    except Exception:
        ref_author = None
    voice = False
    try:
        voice = bool(getattr(message.flags, "voice", False))
    except Exception:
        voice = False
    return {"id": str(message.id), "channel_id": str(ch.id),
            "parent_id": str(ch.parent_id) if getattr(ch, "parent_id", None) else None,
            "author_id": str(message.author.id),
            "author_name": getattr(message.author, "display_name", "") or str(message.author),
            "is_bot": bool(message.author.bot), "is_self": message.author.id == me_id,
            "text": message.content or "", "embeds": embeds,
            "media": [{"url": a.url, "content_type": a.content_type or "", "filename": a.filename or ""}
                      for a in (message.attachments or [])],
            "voice": voice,
            "mention_ids": [str(u.id) for u in (message.mentions or []) if not getattr(u, "bot", False)],
            "role_mentioned": bool(message.role_mentions) or bool(message.mention_everyone),
            "reference_author_id": ref_author, "bot_ids": [str(me_id)] if me_id else [],
            "at": _local(message.created_at)}


# ------------------------------------------------------------------ listeners

async def drain():
    try:
        return await outbox.drain(execute, flow.delivered)
    except Exception as e:
        print("[rrdesk] drain failed:", e)
        return 0, 0


async def on_message(message):
    try:
        if message.guild is None or not _is_rr_channel(message.channel):
            return
        if getattr(message, "type", None) not in (None, _d().MessageType.default, _d().MessageType.reply):
            return                                   # joins, pins, thread notices
        d = message_dict(message)
        await outbox.run_blocking(flow.on_message, d)
        await drain()
    except Exception as e:
        print("[rrdesk] on_message failed:", e)
        _log_async("error", message, {"where": "on_message", "e": str(e)[:300]})


async def on_raw_message_edit(payload):
    try:
        data = payload.data or {}
        if "content" not in data and "embeds" not in data:
            return
        ch = _bot().get_channel(payload.channel_id)
        if ch is None or not _is_rr_channel(ch):
            return
        a = data.get("author") or {}
        me = getattr(_bot().user, "id", None)
        d = {"id": str(payload.message_id), "channel_id": str(payload.channel_id),
             "parent_id": str(ch.parent_id) if getattr(ch, "parent_id", None) else None,
             "author_id": str(a.get("id") or ""), "author_name": a.get("username") or "",
             "is_bot": bool(a.get("bot")), "is_self": str(a.get("id") or "") == str(me),
             "text": data.get("content") or "",
             "embeds": [{"title": e.get("title") or "", "description": e.get("description") or "",
                         "fields": [{"name": f.get("name") or "", "value": f.get("value") or ""}
                                    for f in e.get("fields") or []],
                         "footer": ((e.get("footer") or {}).get("text") or "")}
                        for e in data.get("embeds") or []],
             "media": [], "voice": False, "mention_ids": [], "role_mentioned": False,
             "reference_author_id": None, "at": _tz_now()}
        await outbox.run_blocking(flow.on_edit, d)
        await drain()
    except Exception as e:
        print("[rrdesk] edit hook failed:", e)


async def on_raw_message_delete(payload):
    try:
        n = await outbox.run_blocking(flow.on_delete, str(payload.channel_id), str(payload.message_id))
        if n:
            await drain()
    except Exception as e:
        print("[rrdesk] delete hook failed:", e)


async def on_raw_reaction_add(payload):
    try:
        if str(payload.emoji) != PIN:
            return
        ch = _bot().get_channel(payload.channel_id)
        if ch is None or not _is_rr_channel(ch):
            return
        msg = await ch.fetch_message(payload.message_id)
        req = await outbox.run_blocking(
            flow.on_pin, str(ch.id), str(ch.parent_id) if getattr(ch, "parent_id", None) else None,
            str(msg.id), str(payload.user_id), str(msg.author.id), msg.content or "",
            _local(msg.created_at), _tz_now())
        if req:
            await drain()
    except Exception as e:
        print("[rrdesk] pin hook failed:", e)


def _log_async(kind, message, detail):
    """Fire-and-forget on rrdesk's pool — never a database call on the event loop."""
    try:
        outbox._pool.submit(db.log, kind, None, getattr(message.channel, "id", None),
                            getattr(message, "id", None), None, detail)
    except Exception:
        pass


# ------------------------------------------------------------------ buttons + modals

def _presser(interaction):
    u = interaction.user
    admin = False
    try:
        admin = bool(HOST.is_admin(u)) if HOST.is_admin else False
    except Exception:
        admin = False
    return {"did": str(u.id), "name": getattr(u, "display_name", "") or str(u), "is_admin": admin}


async def _reply(interaction, text):
    try:
        if interaction.response.is_done():
            await interaction.followup.send((text or "تم")[:1990], ephemeral=True)
        else:
            await interaction.response.send_message((text or "تم")[:1990], ephemeral=True)
    except Exception as e:
        print("[rrdesk] reply failed:", e)


def _modal(kind, message_id):
    d = _d()
    titles = {"not_what": "Not what I asked", "cancel": "Cancel request",
              "reassign": "نقل الطلب · Reassign", "excuse": "عذر · Excuse",
              "unavailable": "ما عندنا · Not available"}

    class _M(d.ui.Modal):
        def __init__(self):
            super().__init__(title=titles[kind], timeout=600)
            self.who = None
            if kind == "reassign":
                self.who = d.ui.TextInput(label="لمين؟ (منشن أو الاسم)", max_length=100, required=True)
                self.add_item(self.who)
            labels = {"not_what": "What is missing? (one line)", "cancel": "Reason",
                      "reassign": "السبب", "excuse": "السبب (١٠ أحرف على الأقل)",
                      "unavailable": "ليش ما هو متوفر؟ (يوصل لسام بالإنجليزي)"}
            self.box = d.ui.TextInput(label=labels[kind], max_length=500, required=True,
                                      min_length=10 if kind == "excuse" else 2,
                                      style=d.TextStyle.paragraph)
            self.add_item(self.box)

        async def on_submit(self, interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            v = str(self.box.value or "").strip()
            extra = {"note": v, "reason": v}
            if self.who is not None:
                w = str(self.who.value or "").strip()
                extra.update({"to_did": "".join(c for c in w if c.isdigit()), "to_name": w})
            now = _local(interaction.created_at)
            ok, text = await outbox.run_blocking(flow.press, kind, message_id, _presser(interaction),
                                                 extra, now)
            await drain()
            await _reply(interaction, text)
    return _M()


async def _proof(interaction, message_id):
    """True / False / None (history unreadable → the press is allowed and flagged)."""
    known = await outbox.run_blocking(flow.proof_known, message_id)
    if known:
        return True
    req = await outbox.run_blocking(db.request_by_card, message_id)
    if not req:
        return None
    try:
        since = db.parse(req["asked_at"])
        ids = await outbox.run_blocking(flow._thread_ids, req["channel_id"])
        sams = set(flow.sam_ids())
        for cid in ids:
            ch = _bot().get_channel(int(cid)) or await _bot().fetch_channel(int(cid))
            async for m in ch.history(limit=200, after=since):
                if m.attachments and str(m.author.id) not in sams:
                    await outbox.run_blocking(db.record_file, str(m.id), str(cid), str(m.author.id),
                                              len(m.attachments), _local(m.created_at))
                    return True
        return False
    except Exception as e:
        print("[rrdesk] proof history read failed (allowing, flagged):", e)
        return None


async def _image(interaction, message_id):
    tr = await outbox.run_blocking(db.translation_by_our_message, message_id)
    if not tr:
        return "Not found."
    ch = _bot().get_channel(int(tr["channel_id"])) or await _bot().fetch_channel(int(tr["channel_id"]))
    src = await ch.fetch_message(int(tr["source_message_id"]))
    att = next((a for a in src.attachments
                if (a.content_type or "").startswith("image/") or "pdf" in (a.content_type or "")
                or (a.filename or "").lower().endswith(".pdf")), None)
    if att is None:
        return "No image or PDF on that message."
    try:
        out = await outbox.run_blocking(translate.translate_media, att.url, att.content_type or "")
    except translate.CapReached:
        return "Daily translation limit reached — try after midnight."
    except Exception as e:
        await outbox.run_blocking(db.log, "tr_failed", None, tr["channel_id"], str(src.id), None,
                                  {"where": "image", "e": str(e)[:200]})
        return "Could not read that file. Try again in a minute."
    await outbox.run_blocking(flow.image_done, message_id, out["translation"], out)
    await drain()
    return "Done — the English text is posted under the file."


async def on_interaction(interaction):
    """«طلبات سام» buttons. A LISTENER with static custom_ids: the row is found by the message
    id, so a press on a message posted before the last redeploy still works."""
    try:
        if interaction.type != _d().InteractionType.component:
            return
        cid = (interaction.data or {}).get("custom_id") or ""
        kind = CID_TO_KIND.get(cid)
        if not kind:
            return
        mid = str(getattr(interaction.message, "id", "") or "")
        if kind in MODAL_KINDS:
            await interaction.response.send_modal(_modal(kind, mid))     # a modal must be FIRST
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        now = _local(interaction.created_at)
        if kind == "image":
            ok, text = await outbox.run_blocking(flow.press, kind, mid, _presser(interaction), {}, now)
            if ok:
                text = await _image(interaction, mid)
            await _reply(interaction, text)
            return
        extra = {}
        if kind == "deliver":
            extra["proof"] = await _proof(interaction, mid)
        ok, text = await outbox.run_blocking(flow.press, kind, mid, _presser(interaction), extra, now)
        await drain()
        await _reply(interaction, text)
    except Exception as e:
        print("[rrdesk] button error:", e)
        try:
            await _reply(interaction, "صار خطأ — جرب مرة ثانية.")
        except Exception:
            pass


# ------------------------------------------------------------------ the outbox executor

def _embed(e):
    d = _d()
    em = d.Embed(title=(e.get("title") or None) and e["title"][:256],
                 description=(e.get("description") or "")[:4096] or None,
                 color=int(e.get("color") or 0x8A8580))
    for f in (e.get("fields") or [])[:25]:
        em.add_field(name=(f.get("name") or "·")[:256], value=(f.get("value") or "·")[:1024],
                     inline=bool(f.get("inline")))
    if e.get("footer"):
        em.set_footer(text=e["footer"][:2048])
    return em


def _view(buttons):
    if not buttons:
        return None
    d = _d()
    styles = {"success": d.ButtonStyle.success, "danger": d.ButtonStyle.danger,
              "primary": d.ButtonStyle.primary, "secondary": d.ButtonStyle.secondary}
    v = d.ui.View(timeout=None)
    for b in buttons[:20]:
        v.add_item(d.ui.Button(label=b["label"][:80], custom_id=b["custom_id"],
                               style=styles.get(b.get("style"), d.ButtonStyle.secondary)))
    return v


def _mentions(spec):
    d = _d()
    if spec == "none" or not spec:
        return d.AllowedMentions.none()
    return d.AllowedMentions(everyone=False, roles=False, replied_user=False,
                             users=[d.Object(id=int(x)) for x in spec if str(x).isdigit()])


async def _channel(cid):
    b = _bot()
    return b.get_channel(int(cid)) or await b.fetch_channel(int(cid))


def _named(name):
    guild = _bot().get_guild(int(HOST.guild_id or 0))
    if guild is None:
        return None
    return _d().utils.get(guild.text_channels, name=name)


async def execute(kind, p):
    """One outbox row → one Discord action. Raises on failure (the outbox backs off)."""
    d = _d()
    if kind == "post":
        ch = await _channel(p["channel_id"])
        kw = {"allowed_mentions": _mentions(p.get("mentions"))}
        if p.get("embeds"):
            kw["embeds"] = [_embed(e) for e in p["embeds"][:10]]
        v = _view(p.get("buttons"))
        if v is not None:
            kw["view"] = v
        if p.get("reply_to"):
            kw["reference"] = d.MessageReference(message_id=int(p["reply_to"]), channel_id=ch.id,
                                                 fail_if_not_exists=False)
            kw["mention_author"] = False
        m = await ch.send(content=(p.get("content") or None) and p["content"][:2000], **kw)
        return {"message_ids": [str(m.id)]}
    if kind == "edit":
        ch = await _channel(p["channel_id"])
        pm = ch.get_partial_message(int(p["message_id"]))
        kw = {}
        if "content" in p:
            kw["content"] = (p.get("content") or "")[:2000] or None
        if "embeds" in p:
            kw["embeds"] = [_embed(e) for e in (p.get("embeds") or [])[:10]]
        if "buttons" in p:
            kw["view"] = _view(p.get("buttons"))
        await pm.edit(**kw)
        return {"message_ids": [str(p["message_id"])]}
    if kind == "delete":
        ch = await _channel(p["channel_id"])
        try:
            await ch.get_partial_message(int(p["message_id"])).delete()
        except d.NotFound:
            pass
        return {}
    if kind == "react":
        ch = await _channel(p["channel_id"])
        await ch.get_partial_message(int(p["message_id"])).add_reaction(p.get("emoji") or "⚠️")
        return {}
    if kind == "dm":
        b = _bot()
        u = b.get_user(int(p["did"])) or await b.fetch_user(int(p["did"]))
        kw = {}
        v = _view(p.get("buttons"))
        if v is not None:
            kw["view"] = v
        m = await u.send(p["text"][:1990], **kw)
        return {"message_ids": [str(m.id)]}
    if kind in ("room", "board"):
        ch = _named(p["channel_name"])
        if ch is None:
            raise RuntimeError("channel #%s missing" % p["channel_name"])
        if kind == "board" and p.get("message_id"):
            try:
                await ch.get_partial_message(int(p["message_id"])).edit(content=p["content"][:2000])
                return {"message_ids": [str(p["message_id"])]}
            except d.NotFound:
                pass                                   # deleted by hand → post a new one
        kw = {"allowed_mentions": d.AllowedMentions.none() if kind == "board" else
              d.AllowedMentions(everyone=False, roles=False, users=False)}
        v = _view(p.get("buttons"))
        if v is not None:
            kw["view"] = v
        m = await ch.send(p["content"][:2000], **kw)
        return {"message_ids": [str(m.id)]}
    raise RuntimeError("unknown outbox kind %s" % kind)


# ------------------------------------------------------------------ the loop

async def tick_once():
    rep = await outbox.run_blocking(flow.tick)
    await drain()
    if await outbox.run_blocking(db.setting, "study_due") == "1":
        await outbox.run_blocking(db.set_setting, "study_due", "0", "tick")
        try:
            await run_study(post=True)
        except Exception as e:
            print("[rrdesk] monthly study failed:", e)
    return rep


# ------------------------------------------------------------------ the in-bot study (read-only)

async def collect_rooms(limit_rooms=None):
    """Every RR-history room the bot can read (§4.2), as the study's plain dicts. READ ONLY:
    channel.history and nothing else."""
    guild = _bot().get_guild(int(HOST.guild_id or 0))
    if guild is None:
        return []
    out = []
    cats = {c.id: c.name for c in guild.categories}
    for ch in guild.text_channels:
        cat = cats.get(ch.category_id, "")
        if not study.is_history_room(ch.name, ch.topic or "", cat):
            continue
        msgs = []
        try:
            async for m in ch.history(limit=None, oldest_first=True):
                msgs.append(_study_msg(m))
            for th in list(getattr(ch, "threads", []) or []):
                async for m in th.history(limit=None, oldest_first=True):
                    msgs.append(_study_msg(m))
        except Exception as e:
            out.append({"room": {"id": str(ch.id), "name": ch.name, "cat": cat}, "err": str(e), "msgs": []})
            continue
        msgs.sort(key=lambda x: int(x["mid"]))
        out.append({"room": {"id": str(ch.id), "name": ch.name, "cat": cat}, "topic": ch.topic or "",
                    "msgs": msgs, "complete": True})
        if limit_rooms and len(out) >= limit_rooms:
            break
    return out


def _study_msg(m):
    return {"mid": str(m.id), "who": getattr(m.author, "display_name", "") or str(m.author),
            "whoid": str(m.author.id), "isbot": bool(m.author.bot),
            "at": m.created_at.isoformat(), "txt": (m.content or "")[:900],
            "media": len(m.attachments or []), "files": 0,
            "voice": bool(getattr(m.flags, "voice", False)),
            "ments": [str(u.id) for u in m.mentions or []],
            "rep_whoid": (str(m.reference.resolved.author.id)
                          if m.reference and getattr(m.reference, "resolved", None) is not None
                          and getattr(m.reference.resolved, "author", None) is not None else None),
            "emb": [(e.title or "") + NL + (e.description or "") for e in m.embeds or []]}


async def run_study(post=True, grade=True):
    rooms = await collect_rooms()
    sams = flow.sam_ids()
    rep = await outbox.run_blocking(study.analyze, rooms, sams)
    await outbox.run_blocking(study.store_suggestions, rep)
    if grade:
        # grade the real classifier on the golden set (~120 calls, a few cents). The result is a
        # SUGGESTION in the settings view — detection mode is only ever changed by the owner.
        try:
            from . import evalset
            ev = await outbox.run_blocking(evalset.run_live)
            rep["eval"] = {k: ev.get(k) for k in ("mode", "threshold", "n")}
        except Exception as e:
            print("[rrdesk] golden eval failed:", e)
    if post:
        await outbox.run_blocking(db.enqueue, "study:%s" % _tz_now().isoformat(timespec="minutes"), "room",
                                  {"channel_name": flow._watchdog(), "content": study.report_text(rep)})
        await drain()
    return rep


# ------------------------------------------------------------------ commands

def _admin(user):
    try:
        return bool(HOST.is_admin(user)) if HOST.is_admin else False
    except Exception:
        return False


def _parent(ch):
    return str(ch.parent_id) if getattr(ch, "parent_id", None) else None


async def cmd_ask(interaction, what, who=None, urgent=False):
    if not (flow.is_sam(interaction.user.id) or _admin(interaction.user)):
        await _reply(interaction, "Only Sam (or an admin) can open a request this way.")
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    ch = interaction.channel
    ok, text = await outbox.run_blocking(
        flow.ask_command, str(ch.id), _parent(ch), str(interaction.user.id),
        getattr(interaction.user, "display_name", ""), what, str(who.id) if who else None,
        bool(urgent), _local(interaction.created_at), str(interaction.id))
    await drain()
    await _reply(interaction, text)


async def cmd_translate(interaction, on):
    await interaction.response.defer(ephemeral=True, thinking=True)
    ch = interaction.channel
    ok, text = await outbox.run_blocking(flow.set_translate, str(ch.id), _parent(ch), bool(on),
                                         str(interaction.user.id),
                                         getattr(interaction.user, "display_name", ""),
                                         _admin(interaction.user))
    await _reply(interaction, text)


async def cmd_why(interaction):
    """Disciplinary detail (owners, verdicts, excuses) — admins and the ops lead only."""
    if not (_admin(interaction.user) or flow.is_lead(interaction.user.id)):
        await _reply(interaction, "🚫 للإدارة وقائد العمليات فقط. · Admins and the ops lead only.")
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    ch = interaction.channel
    lines = await outbox.run_blocking(flow.why, str(ch.id), _parent(ch))
    chunk = ""
    for ln in lines:
        if len(chunk) + len(ln) + 1 > 1900:
            await interaction.followup.send("```" + NL + chunk + "```", ephemeral=True)
            chunk = ""
        chunk += ln + NL
    if chunk:
        await interaction.followup.send("```" + NL + chunk + "```", ephemeral=True)


async def cmd_sam(interaction, user):
    await interaction.response.defer(ephemeral=True, thinking=True)
    if not _admin(interaction.user):
        await _reply(interaction, "🚫 للإدارة فقط.")
        return
    await outbox.run_blocking(db.set_setting, "sam_ids", str(user.id), str(interaction.user))
    await outbox.run_blocking(db.log, "sam_set", None, None, None, str(interaction.user), {"id": str(user.id)})
    await _reply(interaction, "✅ Sam = %s" % user.mention)


async def cmd_switch(interaction, name, on):
    await interaction.response.defer(ephemeral=True, thinking=True)
    if not _admin(interaction.user):
        await _reply(interaction, "🚫 للإدارة فقط.")
        return
    if name == "warn_live" and on:
        await _reply(interaction, "استخدم /rrdesk-warnings-on — يحتاج كلمة تأكيد.")
        return
    await outbox.run_blocking(flow.set_switch, name, bool(on), str(interaction.user))
    await _reply(interaction, "✅ %s: %s" % (texts.SWITCH_NAMES.get(name, name), "شغال" if on else "موقف"))


async def cmd_warnings(interaction, on, confirm=""):
    await interaction.response.defer(ephemeral=True, thinking=True)
    if not _admin(interaction.user):
        await _reply(interaction, "🚫 للإدارة فقط.")
        return
    if on and (confirm or "").strip() != texts.WARN_ON_CONFIRM:
        await _reply(interaction, texts.WARN_ON_PROMPT)
        return
    await outbox.run_blocking(flow.set_switch, "warn_live", bool(on), str(interaction.user))
    await _reply(interaction, "✅ إنذارات طلبات سام: " + ("فعلية — تنقص العمولة." if on else "تجربة فقط (dry-run)."))


async def cmd_study(interaction):
    if not _admin(interaction.user):
        await _reply(interaction, "🚫 للإدارة فقط.")
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    rep = await run_study(post=True)
    await _reply(interaction, "✅ الدراسة خلصت — %d غرفة، %d طلب من سام. التقرير في غرفة المراقبة."
                 % (rep.get("rooms", 0), rep.get("requests", 0)))


async def cmd_setup(interaction):
    """Create the board room under the RR category (same permissions). Admin, never automatic."""
    await interaction.response.defer(ephemeral=True, thinking=True)
    if not _admin(interaction.user):
        await _reply(interaction, "🚫 للإدارة فقط.")
        return
    guild = interaction.guild
    name = flow.board_channel()
    ex = _d().utils.get(guild.text_channels, name=name)
    if ex is not None:
        await _reply(interaction, "✅ موجودة: %s" % ex.mention)
        return
    cat = next((c for c in guild.categories if c.name == (HOST.rr_category_name or "RR")), None)
    ch = await guild.create_text_channel(name, category=cat,
                                         overwrites=dict(cat.overwrites) if cat is not None else {})
    await outbox.run_blocking(db.set_setting, "board_hash", "", "setup")
    await _reply(interaction, "✅ انفتحت %s — اللوحة تتحدث كل دقيقة." % ch.mention)

