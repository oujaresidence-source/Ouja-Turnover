# -*- coding: utf-8 -*-
"""
rrdesk.flow — the orchestration of «طلبات سام». Synchronous on purpose: bot.py / bridge run it
on rrdesk's own pool, and tests call it directly with a fake HOST, a temp brain.db and `now`.

Entry points
    on_message(m)            a message in an RR room (dict built by bridge.message_dict)
    on_edit(m) / on_delete(channel_id, message_id)
    on_pin(channel_id, message_id, reactor_did, author_did, text, at)
    ask_command(...)         /rr-ask
    press(kind, message_id, presser, extra, now)   every button, one door
    ticket_closed(channel_id, at)                  from bot.py _tk_close
    tick(now)                the minute loop: auto-confirm, leave check, ladder, judge,
                             digests, board, heartbeat
    delivered(row, result)   the outbox reporting what actually landed

THE PRINCIPLE (shared with ops/): the system accuses, humans only forgive. The ONLY call to
ops.db.issue_warning in this package is in _warn(), reached only from the judge in tick().
No route, button or command creates a miss or a warning (tests/test_rrdesk_structure.py).

A translation failure never blocks request tracking and a tracking failure never blocks a
translation: each half of on_message runs in its own try block.
"""

import datetime
import hashlib
import json
import os

from . import db, engine, texts, translate
from .host import HOST
from .outbox import enqueue

NL = chr(10)
LOG = "[rrdesk]"

# ------------------------------------------------------------------ switches + settings

SWITCH_DEFAULTS = {"translate": "1", "requests": "1", "ladder": "1", "warn_live": "0",
                   "force_off": "0"}


def switch(name):
    """Stored switch wins over env (the owner never edits Railway); defaults are correct as
    shipped: everything on except real money (warn_live) and the emergency mute."""
    v = db.setting("sw:" + name)
    if v is None:
        v = os.environ.get("RRDESK_" + name.upper(), SWITCH_DEFAULTS[name])
    return str(v).strip() == "1"


def set_switch(name, on, by):
    if name not in SWITCH_DEFAULTS:
        raise ValueError("unknown switch")
    db.set_setting("sw:" + name, "1" if on else "0", by)
    db.log("switch", actor=by, detail={"name": name, "on": bool(on)})


def active(name):
    return switch(name) and not switch("force_off")


# The history study's numbers (docs/rrdesk/history_study.md §Calibration, 2026-10-24): p60 of
# 234 first replies = 90.6 working minutes → 90; p60 of 218 deliveries = 115.5 → 2 h → the 4 h
# floor. Urgent stays 30 min / 3 h by rule. The dashboard settings override these.
CALIBRATED_SLA = {"resp_min": 90, "deliv_min": 240, "urg_resp_min": 30, "urg_deliv_min": 180}


def sla_cfg():
    out = dict(CALIBRATED_SLA)
    for k in engine.DEFAULT_SLA:
        v = db.setting("sla:" + k)
        if v is not None:
            out[k] = v
    return engine.sla(out)


DEFAULT_SAM_IDS = ("1494059651032158409",)   # Sam1989 — found by the 2026-10-24 history study


def sam_ids():
    """Explicit setting (/rrdesk-sam) > env RRDESK_SAM_IDS > the RR close-out majority the
    tick derives from discord_tickets.json > the study default."""
    for raw in (db.setting("sam_ids"), os.environ.get("RRDESK_SAM_IDS"), db.setting("sam_ids_auto")):
        ids = [x.strip() for x in str(raw or "").replace("،", ",").split(",") if x.strip().isdigit()]
        if ids:
            return ids
    return list(DEFAULT_SAM_IDS)


def is_sam(did):
    return str(did or "") in set(sam_ids())


def detect_mode():
    v = (db.setting("detect_mode") or os.environ.get("RRDESK_DETECT_MODE") or "confirm").strip()
    return v if v in ("auto", "confirm", "explicit") else "confirm"


def threshold():
    try:
        return max(0.40, min(0.99, float(db.setting("threshold") or 0.85)))
    except ValueError:
        return 0.85


QUESTION_FLOOR = 0.40


def _now():
    return HOST.now() if HOST.now else db.now()


def _call(name, *a, default=None):
    fn = getattr(HOST, name, None)
    if fn is None:
        return default
    try:
        return fn(*a)
    except Exception as e:
        print("%s HOST.%s failed: %s" % (LOG, name, e))
        return default


def _link(channel_id, message_id=None):
    g = HOST.guild_id or ""
    if not g or not channel_id:
        return ""
    return "https://discord.com/channels/%s/%s%s" % (g, channel_id, ("/" + str(message_id)) if message_id else "")


def _watchdog():
    return _call("watchdog_channel", default="غرفة-المراقبة") or "غرفة-المراقبة"


# ------------------------------------------------------------------ people

def _employees():
    return _call("employees", default=[]) or []


def name_for(did):
    d = str(did or "")
    for e in _employees():
        if str(e.get("did") or "") == d and d:
            return e.get("name") or ""
    return ""


def did_for(name):
    for e in _employees():
        if (e.get("name") or "") == (name or ""):
            return str(e.get("did") or "")
    return ""


def is_lead(did):
    return bool(did) and str(did) == str(_call("lead_id", default="") or "")


def owner_is_admin_did(did):
    """Faisal / server admins are tracked and reminded, never warned. bridge records who is an
    admin as it sees them; the stored list is the fallback for the tick (no member objects)."""
    ids = [x.strip() for x in str(db.setting("admin_ids") or "").split(",") if x.strip()]
    ids += [str(x) for x in (_call("admin_ids", default=[]) or []) if x]
    return bool(did) and str(did) in ids


def remember_admin(did, is_admin):
    if not did:
        return
    ids = [x.strip() for x in str(db.setting("admin_ids") or "").split(",") if x.strip()]
    d = str(did)
    if is_admin and d not in ids:
        ids.append(d)
    elif not is_admin and d in ids:
        ids.remove(d)
    else:
        return
    db.set_setting("admin_ids", ",".join(ids), "bridge")


# ------------------------------------------------------------------ rooms

def ticket_for(m):
    """(room_channel_id, ticket) for a message in an RR room or one of its threads; None when
    this is not an open RR room (closed / archived rooms are ignored until reopened)."""
    for cid in (m.get("parent_id"), m.get("channel_id")):
        if not cid:
            continue
        rec = _call("rr_record", str(cid))
        if rec and rec.get("kind") == "rr":
            if (rec.get("status") or "") == "closed":
                return None
            return str(cid), rec
    return None


def _thread_ids(room_id):
    ids = db.loads(db.setting("threads:" + str(room_id)), []) or []
    return [str(room_id)] + [str(x) for x in ids]


def _note_thread(room_id, channel_id):
    if str(room_id) == str(channel_id):
        return
    ids = db.loads(db.setting("threads:" + str(room_id)), []) or []
    if str(channel_id) not in ids:
        ids.append(str(channel_id))
        db.set_setting("threads:" + str(room_id), json.dumps(ids), "flow")


# ------------------------------------------------------------------ messages

def on_message(m):
    """Everything one message causes. Returns a short report (for logs and tests)."""
    rep = {"room": None}
    if switch("force_off"):
        rep["skipped"] = "force_off"
        return rep
    hit = ticket_for(m)
    if not hit:
        return rep
    room_id, rec = hit
    rep["room"] = room_id
    _note_thread(room_id, m["channel_id"])
    at = m.get("at") or _now()
    try:
        db.touch_room(room_id)
        if m.get("media"):
            db.record_file(m["id"], m["channel_id"], m.get("author_id"), len(m["media"]), at)
    except Exception as e:
        print(LOG, "file record failed:", e)
    human = not m.get("is_bot")
    sam = human and is_sam(m.get("author_id"))
    # --- tracking half: a team message acknowledges what Sam asked before it ---
    if human and not sam:
        try:
            rep["acked"] = _team_message(room_id, m, at)
        except Exception as e:
            print(LOG, "ack hook failed:", e)
            db.log("error", channel_id=room_id, message_id=m["id"], detail={"where": "ack", "e": str(e)})
    # --- voice notes: one polite reply, a KPI, no transcription ---
    if human and m.get("voice"):
        try:
            if db.record_voice(m["id"], room_id, m.get("author_id"), m.get("author_name"), at) and not sam:
                enqueue("voice:" + m["id"], "post", {
                    "channel_id": m["channel_id"], "content": texts.VOICE_REPLY,
                    "reply_to": m["id"], "mentions": "none"})
                db.log("voice", channel_id=room_id, message_id=m["id"], actor=m.get("author_name"))
        except Exception as e:
            print(LOG, "voice hook failed:", e)
        rep["voice"] = True
        return rep
    if sam:
        try:
            remember_context(m["id"], m)
        except Exception as e:
            print(LOG, "context save failed:", e)
    # --- translation half ---
    classify = None
    try:
        classify = _translate_message(room_id, m, at, sam, rep)
    except Exception as e:
        print(LOG, "translate hook failed:", e)
        db.log("error", channel_id=room_id, message_id=m["id"], detail={"where": "translate", "e": str(e)})
    # --- translation off / failed must not blind request tracking: classify on its own ---
    if sam and classify is None and rep.get("translation") == "off" and active("requests"):
        try:
            classify = _classify_only(room_id, m, at, rep)
        except Exception as e:
            print(LOG, "classify-only failed:", e)
    # --- Sam nudging an earlier ask: logged on every open request in the room (KPI + timeline) ---
    if sam:
        try:
            from . import study as _study
            if _study.is_followup(m.get("text")):
                for r in db.live_requests(room_id):
                    if r["state"] in engine.LIVE:
                        db.log("sam_followup", r["id"], room_id, m["id"], "Sam",
                               {"text": (m.get("text") or "")[:120]})
                rep["followup"] = True
        except Exception as e:
            print(LOG, "follow-up hook failed:", e)
    # --- request half (Sam only) ---
    if sam and active("requests"):
        try:
            _maybe_request(room_id, rec, m, at, classify, rep)
        except Exception as e:
            print(LOG, "request hook failed:", e)
            db.log("error", channel_id=room_id, message_id=m["id"], detail={"where": "request", "e": str(e)})
    return rep


def _classify_only(room_id, m, at, rep):
    """Sam's message got no translation (room/switch off, or the call failed): one classification
    call so detection keeps working. If Sam must confirm, the «Is this a request?» question is
    posted on its own. Respects the cap (cap = explicit-only, by rule)."""
    if detect_mode() == "explicit" or translate.cap_reached(at):
        return None
    text = m.get("text") or ""
    if engine.meaningful_letters(text) < 2:
        return None
    r = translate.translate_text(text, engine.direction(text) or "en2ar", classify=True, now=at)
    c = r.get("classify") or {}
    rep["classified"] = True
    if not c.get("is_request"):
        return c
    conf = c.get("confidence") or 0.0
    if detect_mode() == "auto" and conf >= threshold():
        return c
    if conf < QUESTION_FLOOR:
        return c
    if db.translation(m["id"]) is None and not db.claim_translation(m["id"], room_id, m.get("author_id"),
                                                                     False, "classify", at):
        return c
    db.update_translation(m["id"], state="done", source="none", question="asked", classify_json=c,
                          tokens_in=r.get("tokens_in", 0), tokens_out=r.get("tokens_out", 0),
                          cost_usd=r.get("cost_usd", 0.0))
    enqueue("q:" + m["id"], "post", {
        "channel_id": m["channel_id"], "content": "📌?" + engine.INVISIBLE_MARK, "reply_to": m["id"],
        "buttons": [_btn("q_yes", "success"), _btn("q_no", "secondary")], "mentions": "none",
        "on_done": {"type": "translation", "source": m["id"]}})
    return c


def _team_message(room_id, m, at):
    prev = db.parse(db.setting("teamat:" + str(room_id)))
    if prev is None or at > prev:
        db.set_setting("teamat:" + str(room_id), db.iso(at), "flow")
    n = 0
    for r in db.live_requests(room_id):
        if r["state"] != engine.OPEN:
            continue
        if db.parse(r["asked_at"]) and db.parse(r["asked_at"]) >= at:
            continue
        moved, row = db.move_request(r["id"], [engine.OPEN], engine.ACK, acked_at=at,
                                     acked_by=m.get("author_name") or m.get("author_id"))
        if moved:
            n += 1
            db.log("acknowledged", r["id"], room_id, m["id"], m.get("author_name"),
                   {"how": "team_message"})
            _refresh_card(row)
    return n


def _embeds_text(embeds):
    parts = []
    for e in embeds or []:
        parts.append(e.get("title") or "")
        parts.append(e.get("description") or "")
        for f in e.get("fields") or []:
            parts.append(f.get("name") or "")
            parts.append(f.get("value") or "")
    return NL.join(p for p in parts if p)


def _is_ours(m):
    if not m.get("is_self"):
        return False
    if engine.INVISIBLE_MARK in (m.get("text") or ""):
        return True
    return any((e.get("footer") or "") in texts.OUR_FOOTERS for e in m.get("embeds") or [])


def _translate_message(room_id, m, at, sam, rep, once_suffix=""):
    """Post the translation reply. Returns Sam's classification (or None)."""
    if not active("translate") or not db.translate_on(room_id):
        rep["translation"] = "off"
        return None
    text = m.get("text") or ""
    embeds = list(m.get("embeds") or [])
    ours = _is_ours(m)
    emb_text = _embeds_text(embeds) if m.get("is_bot") else ""
    reason = engine.skip_reason(text, is_bot=m.get("is_bot"), is_ours=ours, has_embeds=bool(emb_text))
    media = [a for a in (m.get("media") or []) if _translatable_media(a)]
    if reason == "embeds_only" and m.get("is_bot") and engine.direction(emb_text) == "ar2en":
        reason = None
    if reason:
        rep["translation"] = "skip:" + reason
        if media and not m.get("is_bot") and not ours:
            _media_button_only(room_id, m, at)
        if reason not in ("own",):
            db.log("tr_skipped", channel_id=room_id, message_id=m["id"], detail={"reason": reason})
        return dict(translate.NOT_A_REQUEST) if sam else None
    dir_ = engine.direction(text) if engine.meaningful_letters(text) >= 2 else engine.direction(emb_text)
    if not dir_:
        return None
    if m.get("is_bot") and dir_ == "en2ar":
        rep["translation"] = "skip:bot_english"
        return None
    if not db.claim_translation(m["id"], room_id, m.get("author_id"), m.get("is_bot"), dir_, at):
        rep["translation"] = "claimed_elsewhere"
        tr = db.translation(m["id"])
        return (tr or {}).get("classify") or None
    once = _call("once_claim", "rrdesk:tr:" + m["id"] + once_suffix, default=True)
    if once is False:
        db.release_translation(m["id"])        # never leave a row stuck in 'claimed'
        rep["translation"] = "claimed_elsewhere"
        return None
    try:
        out_embeds, meta, classify = _do_translate(text, embeds if m.get("is_bot") else [], dir_, sam, at)
    except translate.CapReached:
        db.update_translation(m["id"], state="skipped", skip_reason="cap")
        _cap_hit(at)
        rep["translation"] = "cap"
        return None
    except Exception as e:
        db.release_translation(m["id"])
        enqueue("warn:" + m["id"], "react", {"channel_id": m["channel_id"], "message_id": m["id"],
                                             "emoji": "⚠️"})
        db.log("tr_failed", channel_id=room_id, message_id=m["id"], detail={"e": str(e)[:300]})
        rep["translation"] = "failed"
        return None
    buttons = []
    question = None
    if sam and classify and classify.get("is_request"):
        conf = classify.get("confidence") or 0.0
        mode = detect_mode()
        auto = mode == "auto" and conf >= threshold() and not translate.cap_reached(at)
        if not auto and mode in ("auto", "confirm") and conf >= QUESTION_FLOOR:
            question = "asked"
            buttons += [_btn("q_yes", "success"), _btn("q_no", "secondary")]
    if media and not m.get("is_bot"):
        buttons.append(_btn("image", "secondary"))
    db.update_translation(m["id"], state="done", source=meta["source"], chars=len(text) + len(_embeds_text(embeds)),
                          tokens_in=meta["tokens_in"], tokens_out=meta["tokens_out"],
                          cost_usd=meta["cost_usd"], question=question,
                          classify_json=classify or {}, has_media=1 if media else 0)
    enqueue("tr:" + m["id"], "post", {
        "channel_id": m["channel_id"], "content": engine.INVISIBLE_MARK, "embeds": out_embeds,
        "reply_to": m["id"], "buttons": buttons, "mentions": "none",
        "on_done": {"type": "translation", "source": m["id"]}})
    db.log("translated", channel_id=room_id, message_id=m["id"],
           detail={"dir": dir_, "source": meta["source"], "usd": meta["cost_usd"],
                   "classify": classify, "question": question})
    rep["translation"] = meta["source"]
    return classify


def _btn(key, style):
    label, cid = texts.BTN[key]
    return {"label": label, "custom_id": cid, "style": style}


def _translatable_media(a):
    ct = (a.get("content_type") or "").lower()
    fn = (a.get("filename") or "").lower()
    return ct.startswith("image/") or "pdf" in ct or fn.endswith(".pdf")


def _media_button_only(room_id, m, at):
    """A photo/PDF with no words: a tiny text-only button so Sam can still read an Arabic
    invoice. One per message (the claim row is the latch)."""
    if not db.claim_translation(m["id"], room_id, m.get("author_id"), False, "media", at):
        return
    db.update_translation(m["id"], state="done", source="none", has_media=1)
    enqueue("media:" + m["id"], "post", {
        "channel_id": m["channel_id"], "content": "📎" + engine.INVISIBLE_MARK,
        "reply_to": m["id"], "buttons": [_btn("image", "secondary")], "mentions": "none",
        "on_done": {"type": "translation", "source": m["id"]}})


def _footer(dir_):
    return texts.FOOTER_AR2EN if dir_ == "ar2en" else texts.FOOTER_EN2AR


def _do_translate(text, embeds, dir_, sam, at):
    """(embeds to post, cost meta, classification or None)."""
    pieces, meta = [], {"source": "phrase", "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
    classify = None

    def add(m2):
        meta["tokens_in"] += m2.get("tokens_in", 0)
        meta["tokens_out"] += m2.get("tokens_out", 0)
        meta["cost_usd"] = round(meta["cost_usd"] + m2.get("cost_usd", 0.0), 6)
        rank = {"phrase": 0, "cache": 1, "model": 2}
        if rank.get(m2.get("source"), 0) > rank.get(meta["source"], 0):
            meta["source"] = m2["source"]
    if engine.meaningful_letters(text) >= 2:
        r = translate.translate_text(text, dir_, classify=sam, now=at)
        add(r)
        classify = r.get("classify")
        for chunk in translate.split_for_embeds(r["translation"]):
            pieces.append({"description": chunk, "footer": _footer(dir_), "color": 0x8A8580})
    for e in embeds or []:
        if engine.direction(_embeds_text([e])) != "ar2en":
            continue
        te, m2 = translate.translate_embed(e, "ar2en", now=at)
        add(m2)
        pieces.append({"title": te.get("title") or "", "description": (te.get("description") or "")[:4000],
                       "fields": te.get("fields") or [], "footer": _footer("ar2en"), "color": 0x8A8580})
    if not pieces:
        raise translate.TranslateFailed("nothing to translate")
    return pieces[:10], meta, classify


def _cap_hit(at):
    if db.latch("cap:" + at.date().isoformat(), at):
        cap = translate.daily_cap()
        enqueue("cap:" + at.date().isoformat(), "room", {"channel_name": _watchdog(),
                                                         "content": texts.cap_hit_line(cap)})
        db.log("cap_hit", detail={"cap": cap})


# ------------------------------------------------------------------ edits + deletes

def on_edit(m):
    """The original was edited → re-translate into the SAME reply (edit, never a new post)."""
    if switch("force_off") or not active("translate"):
        return None
    tr = db.translation(m["id"])
    hit = ticket_for(m)
    if not hit:
        return None
    room_id, _rec = hit
    text_key = ":" + hashlib.sha256((m.get("text") or "").encode("utf-8")).hexdigest()[:10]
    if tr is None:
        # the first try failed and released its claim: the edit is the retry (DEBUG.md). The
        # once-key carries the text so the first attempt's 6-hour marker does not block it.
        rep = {}
        _translate_message(room_id, m, m.get("at") or _now(), False, rep, once_suffix=text_key)
        db.log("tr_retried_on_edit", channel_id=room_id, message_id=m["id"], detail=rep)
        return rep.get("translation")
    if (tr["state"] == "done" and tr.get("source") == "none" and not tr.get("has_media")
            and engine.meaningful_letters(m.get("text") or "") >= 2 and active("translate")
            and db.translate_on(room_id)):
        return _translate_late(room_id, m, tr, text_key)
    if tr["state"] != "done" or not tr["our_message_ids"] or tr.get("source") == "none":
        return None
    text = m.get("text") or ""
    if engine.skip_reason(text, is_bot=m.get("is_bot"), is_ours=_is_ours(m),
                          has_embeds=bool(m.get("embeds"))) and not m.get("is_bot"):
        return None
    dir_ = engine.direction(text) or tr.get("direction")
    try:
        embeds, meta, _c = _do_translate(text, m.get("embeds") if m.get("is_bot") else [], dir_,
                                         False, m.get("at") or _now())
    except Exception as e:
        db.log("tr_edit_failed", channel_id=room_id, message_id=m["id"], detail={"e": str(e)[:200]})
        return None
    h = hashlib.sha256(json.dumps(embeds, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    enqueue("tredit:%s:%s" % (m["id"], h), "edit", {
        "channel_id": m["channel_id"], "message_id": tr["our_message_ids"][0], "embeds": embeds})
    db.update_translation(m["id"], tokens_in=(tr.get("tokens_in") or 0) + meta["tokens_in"],
                          tokens_out=(tr.get("tokens_out") or 0) + meta["tokens_out"],
                          cost_usd=round((tr.get("cost_usd") or 0) + meta["cost_usd"], 6))
    db.log("tr_edited", channel_id=room_id, message_id=m["id"])
    return h


def _translate_late(room_id, m, tr, text_key):
    """A message that only got the «Is this a request?» question (translation was off or failed)
    is edited: post its translation now, as a new reply, once per text."""
    text = m.get("text") or ""
    dir_ = engine.direction(text) or "en2ar"
    try:
        embeds, meta, _c = _do_translate(text, [], dir_, False, m.get("at") or _now())
    except Exception as e:
        db.log("tr_edit_failed", channel_id=room_id, message_id=m["id"], detail={"e": str(e)[:200]})
        return None
    enqueue("trlate:%s%s" % (m["id"], text_key), "post", {
        "channel_id": m["channel_id"], "content": engine.INVISIBLE_MARK, "embeds": embeds,
        "reply_to": m["id"], "mentions": "none", "on_done": {"type": "translation", "source": m["id"]}})
    db.update_translation(m["id"], source=meta["source"], tokens_in=(tr.get("tokens_in") or 0) + meta["tokens_in"],
                          tokens_out=(tr.get("tokens_out") or 0) + meta["tokens_out"],
                          cost_usd=round((tr.get("cost_usd") or 0) + meta["cost_usd"], 6))
    db.log("tr_late", channel_id=room_id, message_id=m["id"])
    return meta["source"]


def on_delete(channel_id, message_id):
    """The original was deleted → delete OUR reply (our own messages only, by stored id)."""
    tr = db.translation(message_id)
    n = 0
    for mid in (tr or {}).get("our_message_ids") or []:
        enqueue("del:" + str(mid), "delete", {"channel_id": str(channel_id), "message_id": str(mid)})
        n += 1
    if n:
        db.log("tr_deleted", channel_id=channel_id, message_id=message_id, detail={"n": n})
    req = db.request_by_source(message_id)
    if req and req["state"] in engine.LIVE:
        db.log("source_deleted", req["id"], channel_id, message_id)
    return n


# ------------------------------------------------------------------ requests

def _maybe_request(room_id, rec, m, at, classify, rep):
    c = classify or {}
    if not c.get("is_request"):
        return
    if detect_mode() != "auto" or translate.cap_reached(at):
        return
    if (c.get("confidence") or 0) < threshold():
        return
    if _reask(room_id, c, m["id"], m.get("text")):
        rep["reask"] = True
        return
    if _merge_burst(room_id, c, m["id"], m.get("text"), at):
        rep["merged"] = True
        return
    req, created = open_request(room_id, rec, m["id"], m["channel_id"], at, engine.PATH_DETECTED,
                                m.get("text") or "", c, m)
    rep["request"] = req["id"] if req else None


def _merge_burst(room_id, c, message_id, text, at):
    """Sam's second line within 15 minutes joins the open request it continues: its asks are
    added to that request (one owner, one clock, one possible miss) and the card is refreshed."""
    live = [(r["id"], db.parse(r["asked_at"]), r["state"]) for r in db.live_requests(room_id)]
    rid = engine.burst_of(at, live)
    if not rid:
        return None
    r = db.request(rid)
    asks = list(dict.fromkeys([a for a in (r["asks"] or []) + list(c.get("asks") or []) if a != "other"]
                              or ["other"]))
    extra = (c.get("summary_en") or text or "")[:160]
    db.update_request(rid, asks_json=json.dumps(asks), summary_en=((r.get("summary_en") or "") + " · " + extra)[:300],
                      summary_ar=((r.get("summary_ar") or "") + (" · " + c["summary_ar"] if c.get("summary_ar") else ""))[:300])
    db.log("merged", rid, room_id, message_id, "Sam", {"asks": asks, "text": (text or "")[:160]})
    _refresh_card(db.request(rid))
    return rid


def _reask(room_id, c, message_id, text):
    """Sam asked again for what an open request already asks → a re-ask event on THAT request
    (KPI + timeline + the card's owner pinged again), never a second request."""
    live = [(r["id"], r["asks"], r["state"]) for r in db.live_requests(room_id)]
    rid = engine.reask_of(c.get("asks"), live)
    if not rid:
        return None
    db.log("sam_reask", rid, room_id, message_id, "Sam", {"text": (text or "")[:160]})
    return rid


def _enrich(rec):
    """Hostaway enrichment for urgency, cached per ticket for 6 hours (it is a network call)."""
    code = rec.get("code") or ""
    key = "enrich:" + code
    hit = db.loads(db.setting(key), None)
    now = _now()
    if hit and hit.get("_at") and (now - db.parse(hit["_at"])).total_seconds() < 6 * 3600:
        return hit
    e = _call("enrich", code, default={}) or {}
    e = {k: e.get(k) for k in ("days_left", "deadline_passed", "lid", "unit", "deadline")}
    e["_at"] = db.iso(now)
    db.set_setting(key, json.dumps(e, ensure_ascii=False, default=str), "flow")
    return e


def _choose_owner(rec, m, enrich, today):
    lid = rec.get("lid") or enrich.get("lid")
    resp = _call("responsible_for", lid, today, default=("", "", "unknown")) if lid else ("", "", "unknown")
    resp_pair = (resp[1], resp[0]) if resp and resp[1] else None
    emps = _employees()
    cal = [str(e.get("did") or "") for e in emps if e.get("did")]
    opener = str(rec.get("opener_id") or "")
    lead = str(_call("lead_id", default="") or "")
    excluded = set(sam_ids()) | {str(x) for x in (m.get("bot_ids") or [])}
    # rule 1 only names people in the Employee Calendar: a mention of Faisal, an outsider or an
    # unknown account must never make them the owner (they cannot be judged fairly)
    mentioned = [str(x) for x in (m.get("mention_ids") or []) if str(x) in set(cal)]
    replied = m.get("reference_author_id") if str(m.get("reference_author_id") or "") in set(cal) else None
    choice = engine.choose_owner(mentioned=mentioned,
                                 replied=replied,
                                 role_mentioned=bool(m.get("role_mentioned")),
                                 opener=(opener, name_for(opener)) if opener else None,
                                 responsible=resp_pair, lead=(lead, name_for(lead)),
                                 excluded=excluded, calendar_dids=cal)
    choice["name"] = choice.get("name") or name_for(choice["did"])
    skipped = [x for x in (m.get("mention_ids") or []) if str(x) not in set(cal) and str(x) not in excluded]
    if skipped:
        choice["skipped_mentions"] = skipped
        if not mentioned:
            # Sam asked Faisal / an outsider: nobody on the team was asked, so nobody on the team
            # can be late — the lead holds it as UNOWNED (routing, never a warning)
            choice = {"did": lead, "name": name_for(lead), "rule": 5, "unowned": True,
                      "skipped_mentions": skipped}
            return choice
    # off today / on leave → the apartment's coverer (responsible_for already resolves cover)
    if not choice["unowned"] and choice["name"] and _call("off_today", choice["name"], today, default=False):
        if resp_pair and resp_pair[0] != choice["did"]:
            choice = {"did": resp_pair[0], "name": resp_pair[1], "rule": choice["rule"],
                      "unowned": False, "covered_for": choice["name"]}
        else:
            choice = {"did": lead, "name": name_for(lead), "rule": 5, "unowned": True,
                      "covered_for": choice["name"]}
    return choice


def open_request(room_id, rec, source_id, channel_id, asked_at, path, text, classify, m,
                 urgent_flag=False, who_did=None, opened_at=None):
    """`asked_at` is when Sam asked; `opened_at` when it became a request (a 📌 or a «Yes» can
    come hours later). The clock starts at the LATER of the two — nobody is late for a request
    that did not exist yet — and a team reply already in the room counts as acknowledged."""
    c = classify or {}
    clock = max(asked_at, opened_at or asked_at)
    enrich = _enrich(rec)
    urgent = engine.is_urgent(urgent_flag or c.get("urgent"), enrich)
    why = "flag" if (urgent_flag or c.get("urgent")) else ("aircover" if urgent else None)
    m = dict(m or {})
    if who_did:
        m["mention_ids"] = [str(who_did)]
    owner = _choose_owner(rec, m, enrich, engine.work_day(clock))
    rdue, ddue = engine.dues(clock, urgent, sla_cfg())
    team_at = db.parse(db.setting("teamat:" + str(room_id)))
    state, acked = engine.OPEN, None
    if team_at is not None and team_at > asked_at:
        state, acked = engine.ACK, team_at
    fields = {"ticket_seq": str(rec.get("seq") or ("عام" if rec.get("general") else "")),
              "ticket_code": rec.get("code") or "",
              "lid": str(rec.get("lid") or enrich.get("lid") or ""), "text": (text or "")[:2000],
              "summary_en": c.get("summary_en") or (text or "")[:200],
              "summary_ar": c.get("summary_ar") or "", "asks_json": c.get("asks") or ["other"],
              "urgent": 1 if urgent else 0, "urgent_why": why, "confidence": c.get("confidence"),
              "owner_did": owner["did"], "owner_name": owner["name"], "owner_rule": owner["rule"],
              "unowned": 1 if owner["unowned"] else 0, "clock_at": clock,
              "resp_due": rdue, "deliv_due": ddue, "state": state}
    if acked is not None:
        fields.update({"acked_at": acked, "acked_by": "team (before it was opened)"})
    req, created = db.open_request(source_id, room_id, asked_at, path, fields)
    if not created:
        return req, False
    db.log("request_opened", req["id"], room_id, source_id, "Sam",
           {"path": path, "confidence": c.get("confidence"), "asks": c.get("asks"),
            "urgent": urgent, "why": why})
    db.log("owner_chosen", req["id"], room_id, source_id, "flow",
           {"did": owner["did"], "name": owner["name"], "rule": owner["rule"],
            "unowned": owner["unowned"], "covered_for": owner.get("covered_for"),
            "skipped_mentions": owner.get("skipped_mentions")})
    content, embed = texts.card(req, clock)
    payload = {"channel_id": str(channel_id or room_id), "content": content, "embeds": [embed],
               "buttons": texts.card_buttons(req["state"]),
               "mentions": [owner["did"]] if owner["did"] else "none",
               "on_done": {"type": "card", "request_id": req["id"]}}
    if not str(source_id).startswith("cmd:"):
        payload["reply_to"] = str(source_id)
    enqueue("card:%d" % req["id"], "post", payload)
    return req, True


def ask_command(channel_id, parent_id, presser_did, presser_name, what, who_did, urgent, at,
                interaction_id):
    """/rr-ask — always a request, typed by Sam (or an admin on his behalf)."""
    m = {"channel_id": str(channel_id), "parent_id": parent_id}
    hit = ticket_for(m)
    if not hit:
        return False, "Run this inside an RR ticket room."
    if not active("requests"):
        return False, "Request tracking is switched off right now."
    room_id, rec = hit
    c = {"summary_en": (what or "")[:200], "asks": _guess_asks(what), "confidence": 1.0}
    try:
        tr = translate.translate_text(what, "en2ar", classify=True, now=at)
        cl = tr.get("classify") or {}
        c["summary_ar"] = cl.get("summary_ar") or tr["translation"][:200]
        c["summary_en"] = cl.get("summary_en") or c["summary_en"]
        if cl.get("asks") and cl["asks"] != ["other"]:
            c["asks"] = cl["asks"]
    except Exception as e:
        db.log("tr_failed", channel_id=room_id, detail={"where": "rr-ask", "e": str(e)[:200]})
    req, created = open_request(room_id, rec, "cmd:" + str(interaction_id), channel_id, at,
                                engine.PATH_COMMAND, what, c, {}, urgent_flag=bool(urgent),
                                who_did=who_did)
    return True, ("Request #%d opened — owner: %s" % (req["id"], req.get("owner_name") or "ops lead")
                  if created else "Already tracked as request #%d." % req["id"])


def _guess_asks(text):
    t = (text or "").lower()
    table = (("photo", "photos"), ("pic", "photos"), ("video", "video"), ("invoice", "invoice"),
             ("quote", "quote"), ("receipt", "receipt"), ("chat", "guest_chat"),
             ("screenshot", "airbnb_screens"), ("report", "ops_report"))
    out = [v for k, v in table if k in t]
    return list(dict.fromkeys(out)) or ["other"]


def on_pin(channel_id, parent_id, message_id, reactor_did, author_did, text, at, opened_at=None):
    """📌 by Sam on his own message → always a request."""
    if switch("force_off") or not active("requests"):
        return None
    if not (is_sam(reactor_did) and str(reactor_did) == str(author_did)):
        return None
    hit = ticket_for({"channel_id": str(channel_id), "parent_id": parent_id})
    if not hit:
        return None
    room_id, rec = hit
    tr = db.translation(message_id) or {}
    c = dict(tr.get("classify") or {})
    if not c.get("is_request") or not c.get("asks"):
        # the model judged it «not a request», so its asks are noise — read the words instead
        c["asks"] = _guess_asks(text)
        c.setdefault("summary_en", (text or "")[:200])
    c["confidence"] = 1.0
    req, _created = open_request(room_id, rec, str(message_id), channel_id, at, engine.PATH_PIN,
                                 text, c, db.loads(db.setting("msgctx:" + str(message_id)), {}) or {},
                                 opened_at=opened_at or at)
    return req


# ------------------------------------------------------------------ the card

def _refresh_card(req):
    if not req or not req.get("card_message_id"):
        return
    content, embed = texts.card(req, _now())
    enqueue("cardedit:%d:%s:%s:%s:%s" % (req["id"], req["state"], req.get("gen") or 1,
                                         req.get("rework") or 0, req.get("owner_did") or ""),
            "edit", {"channel_id": str(_card_channel(req)), "message_id": req["card_message_id"],
                     "content": content, "embeds": [embed],
                     "buttons": texts.card_buttons(req["state"])})


def _card_channel(req):
    ob = db.outbox("card:%d" % req["id"])
    return ((ob or {}).get("payload") or {}).get("channel_id") or req["channel_id"]


# ------------------------------------------------------------------ presses (one door)

def press(kind, message_id, presser, extra=None, now=None):
    """Every button. presser = {did, name, is_admin}. Returns (ok, reply_text). Refused
    presses are logged with who tried — that log is how a dispute is settled later."""
    now = now or _now()
    extra = extra or {}
    did, name = str(presser.get("did") or ""), presser.get("name") or ""
    admin = bool(presser.get("is_admin"))
    remember_admin(did, admin)
    if switch("force_off"):
        return False, texts.REFUSE["off"]
    if kind in ("q_yes", "q_no", "image"):
        return _press_translation(kind, message_id, did, name, admin, now)
    if kind == "excuse":
        return excuse(message_id, did, name, admin, extra.get("reason") or "", now)
    req = db.request_by_card(message_id)
    if not req:
        return False, texts.REFUSE["gone"]
    rid = req["id"]

    def refuse(why, text):
        db.log("press_refused", rid, req["channel_id"], message_id, name,
               {"kind": kind, "why": why, "did": did})
        return False, text
    sam = is_sam(did)
    if kind in ("ack", "deliver", "unavailable"):
        if sam and not admin:
            return refuse("sam_cannot", texts.REFUSE["not_owner"])
    elif kind in ("got_it", "not_what", "cancel"):
        if not (sam or admin):
            return refuse("not_sam", texts.REFUSE["not_sam"])
    elif kind == "reassign":
        if not (admin or is_lead(did)):
            return refuse("not_lead", texts.REFUSE["not_lead"])
    else:
        return refuse("unknown", texts.REFUSE["gone"])
    if req["state"] in engine.TERMINAL:
        return refuse("terminal", texts.REFUSE["closed"])
    if kind == "ack":
        moved, row = db.move_request(rid, [engine.OPEN], engine.ACK, acked_at=now, acked_by=name)
    elif kind == "deliver":
        if req["state"] not in (engine.OPEN, engine.ACK):
            return refuse("state", _already(req))
        proof = extra.get("proof")
        if set(req["asks"]) & engine.FILE_ASKS and proof is False:
            return refuse("no_file", texts.REFUSE["need_file"])
        f = {"delivered_at": now, "delivered_by": name,
             "proof_unchecked": 1 if (set(req["asks"]) & engine.FILE_ASKS and proof is None) else 0}
        if not req.get("acked_at"):
            f.update({"acked_at": now, "acked_by": name})
        moved, row = db.move_request(rid, [engine.OPEN, engine.ACK], engine.DELIVERED, **f)
    elif kind == "unavailable":
        note = (extra.get("note") or extra.get("reason") or "").strip()
        if len(note) < 3:
            return refuse("no_note", "اكتب سطر: ليش ما هو متوفر؟")
        f = {"delivered_at": now, "delivered_by": name, "delivered_note": note[:500]}
        if not req.get("acked_at"):
            f.update({"acked_at": now, "acked_by": name})
        moved, row = db.move_request(rid, [engine.OPEN, engine.ACK], engine.DELIVERED, **f)
    elif kind == "got_it":
        moved, row = db.move_request(rid, [engine.DELIVERED], engine.CONFIRMED, confirmed_at=now,
                                     confirmed_by=name)
    elif kind == "not_what":
        note = (extra.get("note") or "").strip()
        if not note:
            return refuse("no_note", "Please write one line: what is missing?")
        # the original delivery due stays (brief §5.B.4); a new ladder generation means the next
        # thing the owner hears is a reminder, and a miss can only follow it (MISS_GRACE_MIN)
        moved, row = db.move_request(rid, [engine.DELIVERED], engine.ACK,
                                     rework=int(req.get("rework") or 0) + 1, rework_note=note[:500],
                                     delivered_at=None, delivered_by=None, delivered_note=None,
                                     gen=int(req.get("gen") or 1) + 1)
    elif kind == "cancel":
        reason = (extra.get("reason") or "").strip()
        if not reason:
            return refuse("no_reason", "Please give a reason.")
        moved, row = db.move_request(rid, list(engine.LIVE) + [engine.DELIVERED], engine.CANCELLED,
                                     cancel_reason=reason[:500], cancelled_by=name)
    else:   # reassign
        return reassign(req, extra.get("to_did"), extra.get("to_name"), extra.get("reason"), did, name, now)
    if not moved:
        return refuse("lost_race", _already(row))
    db.log(kind, rid, req["channel_id"], message_id, name,
           {"did": did, "note": extra.get("note"), "reason": extra.get("reason"),
            "proof": extra.get("proof")})
    _refresh_card(row)
    line = texts.done_line(kind, name)
    if kind == "unavailable":
        line = line.replace(engine.INVISIBLE_MARK, "") + NL + "> " + _for_sam(row.get("delivered_note")) + engine.INVISIBLE_MARK
    enqueue("line:%d:%s:%s" % (rid, kind, db.iso(now)), "post", {
        "channel_id": str(_card_channel(row)), "content": line,
        "reply_to": row.get("card_message_id"), "mentions": "none"})
    return True, texts.done_line(kind, name).replace(engine.INVISIBLE_MARK, "")


def _for_sam(note):
    """The staff's reason, with an English line under it when it is Arabic (our own posts are
    never auto-translated, so this one is translated here, once)."""
    note = (note or "").strip()
    if engine.direction(note) != "ar2en":
        return note
    try:
        return note + " — " + translate.translate_text(note, "ar2en")["translation"]
    except Exception:
        return note


def _already(row):
    r = row or {}
    who = (r.get("confirmed_by") or r.get("delivered_by") or r.get("acked_by")
           or r.get("cancelled_by") or "شخص ثاني")
    return texts.REFUSE["already"].format(who=who)


def reassign(req, to_did, to_name, reason, by_did, by_name, now):
    reason = (reason or "").strip()
    if len(reason) < 3:
        return False, "اكتب سبب النقل."
    to_did = "".join(ch for ch in str(to_did or "") if ch.isdigit())
    if not to_did and to_name:
        to_did = did_for(to_name.strip())
    if not to_did:
        return False, "ما عرفت الشخص — اكتب منشن أو الاسم كما في تقويم الموظفين."
    if to_did == req.get("owner_did"):
        return False, "هو نفسه المسؤول الحالي."
    gen = int(req.get("gen") or 1) + 1
    rdue, ddue = engine.dues(now, bool(req.get("urgent")), sla_cfg())
    db.update_request(req["id"], owner_did=to_did, owner_name=name_for(to_did) or to_name or "",
                      owner_rule=0, unowned=0, gen=gen, clock_at=now, resp_due=rdue, deliv_due=ddue)
    # the old owner's miss (if any) for this request stops counting — reassignment is routing
    for ms in db.misses_for(req["id"]):
        if not ms.get("excused_at"):
            db.excuse_miss(req["id"], ms["gen"], by_name, "reassigned: " + reason, now)
    row = db.request(req["id"])
    db.log("reassigned", req["id"], req["channel_id"], None, by_name,
           {"from": req.get("owner_did"), "to": to_did, "gen": gen, "reason": reason})
    _refresh_card(row)
    enqueue("reassign:%d:%d" % (req["id"], gen), "post", {
        "channel_id": str(_card_channel(row)),
        "content": "🔁 %s صار مسؤول عن طلب سام (%s).%s" % (texts.mention(to_did), texts.asks_ar(row["asks"]),
                                                          engine.INVISIBLE_MARK),
        "reply_to": row.get("card_message_id"), "mentions": [to_did]})
    return True, "تم النقل."


def _press_translation(kind, message_id, did, name, admin, now):
    tr = db.translation_by_our_message(message_id)
    if not tr:
        return False, texts.REFUSE["gone"]
    if not (is_sam(did) or admin):
        db.log("press_refused", None, tr["channel_id"], message_id, name, {"kind": kind, "did": did})
        return False, texts.REFUSE["not_sam"]
    if kind == "image":
        return True, "image"              # bridge runs the vision call (it holds the attachment)
    if tr.get("question") in ("yes", "no"):
        return False, "Already answered: %s." % tr["question"]
    db.update_translation(tr["source_message_id"], question="yes" if kind == "q_yes" else "no")
    db.log("question_" + ("yes" if kind == "q_yes" else "no"), None, tr["channel_id"],
           tr["source_message_id"], name)
    if kind == "q_no":
        return True, "OK — not tracked."
    hit = ticket_for({"channel_id": tr["channel_id"]})
    if not hit:
        return False, texts.REFUSE["gone"]
    room_id, rec = hit
    src_at = db.parse(tr.get("created_at")) or now
    c = dict(tr.get("classify") or {})
    again = _reask(room_id, c, tr["source_message_id"], c.get("summary_en"))
    if again:
        return True, "Already tracked as request #%d — logged as a follow-up." % again
    req, _created = open_request(room_id, rec, tr["source_message_id"], tr["channel_id"], src_at,
                                 engine.PATH_CONFIRMED, c.get("summary_en") or "", c,
                                 db.loads(db.setting("msgctx:" + tr["source_message_id"]), {}) or {},
                                 opened_at=now)
    return True, "Tracked as request #%d." % req["id"]


def remember_context(message_id, m):
    """Mentions/reply of a Sam message, kept for the «Yes» press that may come later."""
    ctx = {k: m.get(k) for k in ("mention_ids", "reference_author_id", "role_mentioned")}
    db.set_setting("msgctx:" + str(message_id), json.dumps(ctx), "flow")


def image_done(message_id, translation_text, meta):
    tr = db.translation_by_our_message(message_id)
    if not tr:
        return
    db.update_translation(tr["source_message_id"],
                          tokens_in=(tr.get("tokens_in") or 0) + meta.get("tokens_in", 0),
                          tokens_out=(tr.get("tokens_out") or 0) + meta.get("tokens_out", 0),
                          cost_usd=round((tr.get("cost_usd") or 0) + meta.get("cost_usd", 0), 6))
    for i, chunk in enumerate(translate.split_for_embeds(translation_text)):
        enqueue("img:%s:%d" % (message_id, i), "post", {
            "channel_id": tr["channel_id"], "content": engine.INVISIBLE_MARK,
            "embeds": [{"title": "📎 Text in the file" if i == 0 else "", "description": chunk,
                        "footer": texts.FOOTER_AR2EN, "color": 0x8A8580}],
            "reply_to": str(message_id), "mentions": "none"})
    db.log("image_translated", None, tr["channel_id"], tr["source_message_id"], None,
           {"usd": meta.get("cost_usd")})


def proof_known(req_message_id):
    """True when a file was SEEN in the room or its threads after the ask; None when we have not
    seen one (bridge then reads the history — and a failed read fails open with a flag)."""
    req = db.request_by_card(req_message_id)
    if not req:
        return None
    if not (set(req["asks"]) & engine.FILE_ASKS):
        return True
    n = db.files_since(_thread_ids(req["channel_id"]), db.parse(req["asked_at"]), sam_ids())
    return True if n else None


# ------------------------------------------------------------------ mercy

def excuse(message_id, did, name, admin, reason, now):
    ms = db.miss_by_line(message_id)
    if not ms:
        return False, texts.REFUSE["gone"]
    if not (admin or is_lead(did)):
        db.log("press_refused", ms["request_id"], None, message_id, name, {"kind": "excuse", "did": did})
        return False, texts.REFUSE["not_lead"]
    if len((reason or "").strip()) < 10:
        return False, texts.REFUSE["excuse_short"]
    if now - db.parse(ms["missed_at"]) > datetime.timedelta(hours=48):
        return False, texts.REFUSE["excuse_late"]
    if not db.excuse_miss(ms["request_id"], ms["gen"], name, reason.strip()[:500], now):
        return False, "معذور من قبل."
    db.log("excused", ms["request_id"], None, message_id, name, {"reason": reason[:300], "gen": ms["gen"]})
    return True, "✅ انعذر — هالتأخير ما ينحسب."


# ------------------------------------------------------------------ ticket closed

def ticket_closed(channel_id, at=None):
    at = at or _now()
    n = 0
    for r in db.live_requests(channel_id):
        moved, row = db.move_request(r["id"], [engine.OPEN, engine.ACK, engine.DELIVERED],
                                     engine.CLOSED_WITH_TICKET)
        if moved:
            n += 1
            db.log("closed_with_ticket", r["id"], channel_id, None, "ticket")
            _refresh_card(row)
    return n


def set_translate(channel_id, parent_id, on, presser_did, presser_name, is_admin):
    hit = ticket_for({"channel_id": str(channel_id), "parent_id": parent_id})
    if not hit:
        return False, "Run this inside an RR ticket room."
    if not (is_admin or is_sam(presser_did) or is_lead(presser_did)):
        return False, "Only Sam, the ops lead or an admin can switch translation here."
    db.set_room_translate(hit[0], on, presser_name)
    db.log("room_translate", channel_id=hit[0], actor=presser_name, detail={"on": bool(on)})
    return True, ("Translation is ON in this room. · الترجمة شغالة بهالروم." if on
                  else "Translation is OFF in this room. · الترجمة موقفة بهالروم.")


# ------------------------------------------------------------------ the tick

def tick(now=None):
    now = now or _now()
    rep = {}
    prev = db.parse(db.setting("last_tick"))
    db.set_setting("last_tick", db.iso(now), "tick")
    if prev:
        db.set_setting("tick_gap_s", str(int((now - prev).total_seconds())), "tick")
    if switch("force_off"):
        rep["skipped"] = "force_off"
        return rep
    for name, step in (("sam", _derive_sam), ("auto_confirm", _auto_confirm),
                       ("leave", _leave_check), ("rooms", _reconcile_rooms), ("ladder", _ladder),
                       ("judge", _judge), ("digests", _digests), ("board", _board),
                       ("janitor", _janitor)):
        try:
            rep[name] = step(now)
        except Exception as e:                  # one broken step must not stop the others
            print("%s %s step failed: %s" % (LOG, name, e))
            db.log("error", detail={"where": "tick:" + name, "e": str(e)[:300]})
            rep[name] = "error: %s" % e
    return rep


def _derive_sam(now):
    recs = _call("rr_records", default={}) or {}
    ids = [str(((r or {}).get("closeout") or {}).get("by_id") or "") for r in recs.values()
           if isinstance(r, dict) and r.get("kind") == "rr"]
    best = engine.majority([i for i in ids if i])
    if best and db.setting("sam_ids_auto") != best:
        db.set_setting("sam_ids_auto", best, "tick")
        db.log("sam_derived", detail={"id": best, "votes": ids.count(best)})
    return best


def _auto_confirm(now):
    n = 0
    for r in db.live_requests():
        if r["state"] == engine.DELIVERED and engine.auto_confirm_due(db.parse(r["delivered_at"]), now):
            moved, row = db.move_request(r["id"], [engine.DELIVERED], engine.CONFIRMED_AUTO,
                                         confirmed_at=now, confirmed_by="auto")
            if moved:
                n += 1
                db.log("confirmed_auto", r["id"], r["channel_id"])
                _refresh_card(row)
    return n


def _leave_check(now):
    """Once a working day per request: an owner who is off / on leave today hands it to the
    apartment's coverer (the request's clock does NOT restart — routing, not a new ask)."""
    wday = engine.work_day(now)
    today = wday.isoformat()
    n = 0
    for r in db.live_requests():
        if r["state"] not in engine.LIVE or r.get("leave_checked_day") == today or r.get("unowned"):
            continue
        db.update_request(r["id"], leave_checked_day=today)
        if not r.get("owner_name") or not _call("off_today", r["owner_name"], wday, default=False):
            continue
        resp = (_call("responsible_for", r.get("lid"), wday, default=("", "", "unknown"))
                if r.get("lid") else ("", "", "unknown"))
        to_did, to_name = (resp[1], resp[0]) if resp and resp[1] else ("", "")
        rule, unowned = 4, 0
        if not to_did or to_did == r.get("owner_did"):
            # nobody covers this apartment today: the lead holds it as UNOWNED (never warned)
            to_did = str(_call("lead_id", default="") or "")
            to_name, rule, unowned = name_for(to_did), 5, 1
        if not to_did:
            continue
        # a hand-over is a reassignment: the coverer gets a fresh clock and a fresh ladder
        gen = int(r.get("gen") or 1) + 1
        rdue, ddue = engine.dues(now, bool(r.get("urgent")), sla_cfg())
        db.update_request(r["id"], owner_did=to_did, owner_name=to_name, owner_rule=rule,
                          unowned=unowned, gen=gen, clock_at=now, resp_due=rdue, deliv_due=ddue)
        db.log("covered", r["id"], r["channel_id"], None, "tick",
               {"from": r["owner_name"], "to": to_name, "why": "off_or_leave", "gen": gen})
        _refresh_card(db.request(r["id"]))
        n += 1
    return n


def _reconcile_rooms(now):
    """A request whose room is closed, deleted or archived ends with it (never a miss) — the
    _tk_close hook is time-boxed and may not have run, so the tick re-checks every minute."""
    if HOST.rr_record is None:
        return 0
    n = 0
    for r in db.live_requests():
        try:
            rec = HOST.rr_record(str(r["channel_id"]))
        except Exception:
            continue                       # cannot tell → leave it alone
        if not rec:
            continue                       # unknown (empty store, cache not warm) → never close on a guess
        if (rec.get("status") or "") != "closed" and not rec.get("gone"):
            continue
        moved, row = db.move_request(r["id"], [engine.OPEN, engine.ACK, engine.DELIVERED],
                                     engine.CLOSED_WITH_TICKET)
        if moved:
            n += 1
            db.log("closed_with_ticket", r["id"], r["channel_id"], None, "tick", {"why": "room gone or closed"})
            _refresh_card(row)
    return n


def _gen_sent(rid, gen):
    out = set()
    for s in db.ladder_sent(rid):
        base, _sep, g = s.partition("#")
        if int(g or 1) == int(gen or 1):
            out.add(base)
    return out


def _ladder(now):
    if not active("ladder") or not engine.in_work_hours(now):
        return 0
    n = 0
    cfg = sla_cfg()
    for r in db.live_requests():
        if r["state"] not in engine.LIVE:
            continue
        if HOST.rr_record is not None:
            try:
                if not HOST.rr_record(str(r["channel_id"])):
                    continue               # room unknown right now: never remind or accuse blind
            except Exception:
                continue
        gen = int(r.get("gen") or 1)
        step = engine.due_step(r["state"], db.parse(r["clock_at"]), bool(r["urgent"]), now,
                               _gen_sent(r["id"], gen), cfg)
        if not step:
            continue
        name = step["step"]
        if name == "MISS":
            name = _miss_or_reminder(r, gen, now)
            if not name:
                continue
        key = engine.step_key(name, gen)
        if not db.record_step(r["id"], key, r.get("owner_did"), now):
            continue
        n += 1
        _fire(name, r, gen, key, now)
    return n


def _miss_or_reminder(r, gen, now):
    """Nobody's first notice is a miss. After a restart, an un-mute, a late-opened request or a
    rework, the ladder may jump straight to MISS — then the owner gets the 100% reminder first,
    and the miss only follows MISS_GRACE_MIN working minutes after it."""
    rows = [x for x in db.ladder_rows(r["id"])
            if int((x["step"].partition("#")[2]) or 1) == gen and not x["step"].startswith("MISS")]
    last = max([db.parse(x["sent_at"]) for x in rows if x.get("sent_at")] or [None], key=lambda t: t or now)
    if last is None:
        sub = "R2" if r["state"] == engine.OPEN else "D2"
        return sub if engine.step_key(sub, gen) not in db.ladder_sent(r["id"]) else None
    if engine.worked_minutes(last, now) < engine.MISS_GRACE_MIN:
        return None
    return "MISS"


def _fire(step, r, gen, key, now):
    link = _link(_card_channel(r), r.get("card_message_id"))
    ch = str(_card_channel(r))
    owner = r.get("owner_did") or ""
    mentions = [owner] if owner else "none"
    db.log("ladder_" + step, r["id"], r["channel_id"], None, "tick", {"key": key, "owner": owner})
    if step != "MISS":
        enqueue("ladder:%d:%s" % (r["id"], key), "post", {
            "channel_id": ch, "content": texts.ladder_room(step, r),
            "reply_to": r.get("card_message_id"), "mentions": mentions})
        if step == "R2" and owner:
            enqueue("ladderdm:%d:%s" % (r["id"], key), "dm", {"did": owner, "text": texts.ladder_dm("R2", r, link)})
        if step == "D2":
            enqueue("ladderwd:%d:%s" % (r["id"], key), "room", {"channel_name": _watchdog(),
                                                               "content": texts.watchdog_d2(r, link)})
        return
    # --- MISS ---
    wday = engine.work_day(now)
    admin = owner_is_admin_did(owner)
    leave = bool(r.get("owner_name")) and bool(_call("on_leave", r["owner_name"], wday, default=False))
    repeat = any(str(x.get("owner_did") or "") == str(owner) for x in db.misses_for(r["id"]))
    eligible = (engine.miss_eligible(r["path"], r["state"], owner, bool(r.get("unowned")), admin, leave)
                and bool(r.get("owner_name")) and not repeat)
    db.record_miss(r["id"], gen, r.get("owner_name"), owner, engine.week_key(wday), now, eligible)
    db.log("miss", r["id"], r["channel_id"], None, "tick",
           {"eligible": eligible, "admin": admin, "leave": leave, "unowned": bool(r.get("unowned")),
            "path": r["path"], "gen": gen, "repeat_for_owner": repeat, "named": bool(r.get("owner_name"))})
    # no line in the shared room: a miss names a person, and names go to DMs / غرفة-المراقبة only
    if owner:
        enqueue("missdm:%d:%d" % (r["id"], gen), "dm", {"did": owner, "text": texts.ladder_dm("MISS", r, link)})
    lead = str(_call("lead_id", default="") or "")
    if lead and lead != owner:
        enqueue("misslead:%d:%d" % (r["id"], gen), "dm", {"did": lead, "text": texts.lead_miss_dm(r, link)})
    enqueue("misswd:%d:%d" % (r["id"], gen), "room", {
        "channel_name": _watchdog(), "content": texts.watchdog_miss(r, link, eligible),
        "buttons": [_btn("excuse", "secondary")] if eligible else [],
        "on_done": {"type": "miss_line", "request_id": r["id"], "gen": gen}})


# ------------------------------------------------------------------ the judge

def _judge(now):
    n = 0
    for ms in db.unjudged_misses():
        missed = db.parse(ms["missed_at"])
        if not ms.get("excused_at") and missed and now - missed < datetime.timedelta(hours=engine.EXCUSE_WINDOW_H):
            continue                       # «عذر» can still be pressed — judge after the window
        if not ms.get("owner_name"):
            db.set_miss(ms["request_id"], ms["gen"], verdict="unnamed", judged_at=now)
            continue
        if ms.get("excused_at"):
            db.set_miss(ms["request_id"], ms["gen"], verdict="excused", judged_at=now)
            continue
        week = ms["week"]
        rows = db.misses_in_week(ms["owner_name"], week)
        ids = [(x["request_id"], x["gen"]) for x in rows]
        nth = ids.index((ms["request_id"], ms["gen"])) + 1 if (ms["request_id"], ms["gen"]) in ids else len(ids)
        verdict = engine.judge(nth)
        db.set_miss(ms["request_id"], ms["gen"], verdict=verdict, judged_at=now)
        db.log("judged", ms["request_id"], None, None, "judge",
               {"owner": ms["owner_name"], "week": week, "nth": nth, "verdict": verdict})
        n += 1
        if verdict == engine.NOTICE and ms.get("owner_did"):
            enqueue("notice:%s:%s" % (ms["owner_name"], week), "dm",
                    {"did": ms["owner_did"], "text": texts.notice_dm(week)})
        elif verdict == engine.WARN:
            reqs = [db.request(rid) for rid, _g in ids[:2]]
            _warn(ms["owner_name"], ms.get("owner_did") or "", week, [r for r in reqs if r], now)
    return n


def _warn(employee, did, week, reqs, now):
    """THE ONLY ops.db.issue_warning CALL IN THIS PACKAGE — a line-for-line mirror of
    oncall/notify.py::_warn. One per employee per ISO week, by ops' own
    UNIQUE(kind, employee, period_key) + UNIQUE(obligation_id). Money is dry-run until the
    owner types /rrdesk-warnings-on + «تشغيل»: then ops_dryrun_log says what WOULD happen."""
    from ops import db as odb, engine as oeng, notify as onotify
    period = "RR-" + week
    reason = texts.warning_reason(reqs)
    if not switch("warn_live"):
        mult = oeng.compute_multiplier(odb.active_warning_count(employee) + 1)
        pct = engine.ar_num(int(round(mult * 100))) + "٪"
        if not odb.dry_logged("rr_warning", employee, period):
            odb.dry_log("rr_warning", employee, period, texts.dry_warning_detail(employee, week, pct),
                        {"reason_ar": reason, "requests": [r["id"] for r in reqs], "multiplier": mult})
        db.log("would_warn", detail={"employee": employee, "week": week, "multiplier": mult})
        return None
    ob = odb.ensure_obligation("rr", employee, did, period, now)
    odb.set_status(ob["id"], "missed")
    w = odb.issue_warning(ob, reason)
    led = odb.recompute_commission(employee, oeng.month_key(now.date()))
    pct = engine.ar_num(int(round(float(led["multiplier"]) * 100))) + "٪"
    link = onotify._appeal_link(w["appeal_token"])
    if did:
        enqueue("warn:%s:%s" % (employee, week), "dm", {"did": did, "text": texts.warning_dm(reason, pct, link)})
    enqueue("warnhr:%s:%s" % (employee, week), "room", {"channel_name": onotify.hr_channel(),
                                                         "content": texts.hr_line(employee, week, pct)})
    db.log("warning", detail={"employee": employee, "week": week, "warning_id": w["id"],
                              "multiplier": led["multiplier"]})
    return w


# ------------------------------------------------------------------ digests + KPIs

def _age_rows(rows, now):
    out = []
    for r in rows:
        r = dict(r)
        r["_age_min"] = engine.worked_minutes(db.parse(r["asked_at"]), now)
        dd = db.parse(r.get("deliv_due"))
        r["_late"] = bool(dd and dd <= now and r["state"] in engine.LIVE)
        out.append(r)
    return out


def person_kpis(since, until, now):
    """[{name, did, ...kpis}] for everyone who owned a request in the window."""
    reqs = db.requests_in(since, until)
    misses = db.misses_between(since, until)
    voice = db.voice_counts(since, until)
    by = {}
    for r in reqs:
        if r.get("unowned"):
            continue
        by.setdefault(r.get("owner_name") or r.get("owner_did") or "?", []).append(r)
    out = []
    for name, rows in sorted(by.items()):
        did = rows[0].get("owner_did") or ""
        m = len([x for x in misses if x["owner_name"] == name and x["eligible"] and not x["excused_at"]])
        k = engine.kpis(rows, now, voice_count=voice.get(did, 0), misses=m, cfg=sla_cfg())
        k.update({"name": name, "did": did, "meets": engine.meets(k, sla_cfg())})
        out.append(k)
    return out


def _digests(now):
    rep = {}
    if now.hour >= 13:
        day = now.date().isoformat()
        if db.latch("sam_digest:" + day, now):
            rows = _age_rows(db.live_requests(), now)
            base = _call("public_base", default="") or ""
            for sid in sam_ids()[:1]:
                enqueue("samdigest:" + day, "dm", {"did": sid, "text": texts.sam_digest(
                    rows, now, (base + "/dashboard#rrdesk") if base else "")})
            rep["sam"] = len(rows)
        if db.latch("wd_daily:" + day, now):
            y = now.date() - datetime.timedelta(days=1)
            start = datetime.datetime(y.year, y.month, y.day, tzinfo=now.tzinfo)
            people = person_kpis(start, start + datetime.timedelta(days=1), now)
            for p in people:
                p.setdefault("owned", 0)
            enqueue("wddaily:" + day, "room", {"channel_name": _watchdog(),
                                               "content": texts.watchdog_daily(y.isoformat(), people)})
            rep["watchdog"] = len(people)
        if now.weekday() == 6:              # Sunday
            week = engine.week_key(now.date() - datetime.timedelta(days=1))
            if db.latch("weekly:" + week, now):
                end = datetime.datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
                start = end - datetime.timedelta(days=7)
                for p in person_kpis(start, end, now):
                    if p.get("did"):
                        enqueue("weekly:%s:%s" % (week, p["name"]), "dm",
                                {"did": p["did"], "text": texts.weekly_dm(p["name"], p, week)})
                rep["weekly"] = True
        if now.day == 1 and db.latch("study:" + now.strftime("%Y-%m"), now):
            db.set_setting("study_due", "1", "tick")
            rep["study"] = True
    return rep


def _board(now):
    rows = _age_rows([r for r in db.live_requests() if r["state"] in engine.LIVE], now)
    sig = json.dumps([(r["id"], r["state"], r.get("owner_did"), int(r["_age_min"] // 60)) for r in rows])
    h = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:12]
    if db.setting("board_hash") == h:
        return 0
    db.set_setting("board_hash", h, "tick")
    mid = db.setting("board_mid") or ""
    ref = ("board:%s:%d" % (h, db.incr("board_seq"))) if mid else "board:first"
    enqueue(ref, "board", {"channel_name": board_channel(), "content": texts.board(rows, now),
                                    "message_id": db.setting("board_mid") or "",
                                    "on_done": {"type": "board"}})
    return 1


def board_channel():
    return os.environ.get("RRDESK_BOARD_CHANNEL", "متابعة-طلبات-سام")


def _janitor(now):
    if db.latch("janitor:" + now.date().isoformat(), now):
        db.janitor(now)
        return 1
    return 0


# ------------------------------------------------------------------ outbox results

def delivered(row, result):
    od = (row.get("payload") or {}).get("on_done") or {}
    mids = (result or {}).get("message_ids") or []
    t = od.get("type")
    if t == "translation" and mids:
        for mid in mids:
            db.add_our_message(od["source"], mid)
    elif t == "card" and mids:
        db.update_request(od["request_id"], card_message_id=str(mids[0]))
    elif t == "miss_line" and mids:
        db.set_miss(od["request_id"], od.get("gen") or 1, line_message_id=str(mids[0]))
    elif t == "board" and mids:
        db.set_setting("board_mid", str(mids[0]), "outbox")


# ------------------------------------------------------------------ /rrdesk-why + health

def why(channel_id, parent_id=None, now=None):
    now = now or _now()
    hit = ticket_for({"channel_id": str(channel_id), "parent_id": parent_id})
    room = hit[0] if hit else str(parent_id or channel_id)
    reqs = db.requests_for_channel(room)
    out = ["RR Desk — why (room %s)" % room,
           "switches: " + " ".join("%s=%s" % (k, "on" if switch(k) else "off") for k in SWITCH_DEFAULTS),
           "Sam ids: %s · detect: %s @ %.2f · translate here: %s"
           % (",".join(sam_ids()) or "UNRESOLVED", detect_mode(), threshold(),
              "on" if db.translate_on(room) else "off")]
    if not reqs:
        out.append("No requests tracked in this room.")
    cfg = sla_cfg()
    for r in reqs:
        out.append("")
        out.append("#%d [%s] path=%s conf=%s owner=%s (rule %s%s) gen=%s urgent=%s"
                   % (r["id"], r["state"], r["path"], r.get("confidence"), r.get("owner_name") or r.get("owner_did"),
                      r.get("owner_rule"), ", unowned" if r.get("unowned") else "", r.get("gen"),
                      r.get("urgent_why") or "no"))
        out.append("  asked %s · resp due %s · deliv due %s" % (r["asked_at"], r.get("resp_due"), r.get("deliv_due")))
        sent = {x["step"]: x["sent_at"] for x in db.ladder_rows(r["id"])}
        for s in engine.ladder(r["state"], db.parse(r["clock_at"]), bool(r["urgent"]), cfg):
            key = engine.step_key(s["step"], r.get("gen") or 1)
            if key in sent:
                st = "sent " + sent[key]
            elif s["at"] > now:
                st = "not yet"
            elif not engine.in_work_hours(now):
                st = "waiting for working hours"
            elif not active("ladder"):
                st = "ladder switched off"
            else:
                st = "due — next tick"
            out.append("  %s @ %s → %s" % (key, s["at"].isoformat(timespec="minutes"), st))
        if r["state"] not in engine.LIVE:
            out.append("  ladder: none (state %s)" % r["state"])
        for ms in db.misses_for(r["id"]):
            out.append("  miss gen %s: eligible=%s verdict=%s excused=%s"
                       % (ms["gen"], bool(ms["eligible"]), ms.get("verdict"), ms.get("excused_by") or "no"))
        for ev in reversed(db.events(request_id=r["id"], limit=12)):
            out.append("  · %s %s %s" % (ev["at"][11:16], ev["kind"], ev.get("actor") or ""))
    return out


def health(now=None):
    """Counts only — no names, no text (it is public)."""
    now = now or _now()
    since_day = datetime.datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
    st = db.translation_stats(since_day)
    backlog, failed = db.outbox_backlog()
    last = db.parse(db.setting("last_tick"))
    errs = db.events(kinds=["error", "tr_failed"], limit=1)
    return {
        "ok": True,
        "switches": {k: switch(k) for k in SWITCH_DEFAULTS},
        "last_tick": db.iso(last),
        "tick_lag_s": int((now - last).total_seconds()) if last else None,
        "tick_gap_s": int(db.setting("tick_gap_s") or 0),
        "translations_today": st["done"],
        "translation_failures_1h": db.count_events("tr_failed", now - datetime.timedelta(hours=1)),
        "cache_hit_rate": st["cache_hit_rate"],
        "calls_today": translate.calls_today(now),
        "cap_remaining": max(0, translate.daily_cap() - translate.calls_today(now)),
        "open_requests": len([r for r in db.live_requests() if r["state"] in engine.LIVE]),
        "sam_resolved": bool(sam_ids()),
        "detect_mode": detect_mode(),
        "outbox_backlog": backlog,
        "outbox_failed": failed,
        "last_error_class": ((errs[0].get("detail") or {}).get("where") or errs[0]["kind"]) if errs else None,
    }
