# -*- coding: utf-8 -*-
"""
contracting.notify — what the bot says, and when.

`tick(now)` runs every couple of minutes from bot.py's loop (in a worker thread). It reads the
database, asks engine.due_reminders, CLAIMS each key (db.claim — one key, one message, ever)
and hands a payload to HOST.send. bot.py posts it and reports back through `delivered()`.

LIVE by default since 2026-11-24 (the owner's call). CONTRACTING_DRYRUN=1 in Railway puts it
back in rehearsal: every message is written to the log the tab shows and NOTHING reaches
Discord — no channel is opened, nobody is mentioned. Live or not, nothing is sent for a
project until someone presses «ابدأ» (tick only reads status='active').

The button handlers (`on_*`) are called by bot.py when someone presses «خلص» / «تأخر» /
«واقف» or drops photos in a project channel; they return the Arabic text to post.
"""

import datetime as dt
import hashlib
import json
import os
import re

from . import db, engine
from .host import HOST

AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس",
             "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
NL = chr(10)


def _env(k, d):
    return (os.environ.get(k) or d).strip()


def enabled():
    return _env("CONTRACTING_ENABLED", "1") == "1"


def dryrun():
    return _env("CONTRACTING_DRYRUN", "0") == "1"


def category_name():
    return _env("CONTRACTING_CATEGORY", "المقاولات")


def admin_channel_name():
    return _env("CONTRACTING_ADMIN_CHANNEL", "مقاولات-الإدارة")


def local_now(now=None):
    n = now or (HOST.now() if HOST.now else dt.datetime.now())
    return n.replace(tzinfo=None) if getattr(n, "tzinfo", None) else n


# ---------------------------------------------------------------- words

def fmt_date(s):
    try:
        d = dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return "بدون تاريخ"
    return "%s %d %s" % (AR_DAYS[d.weekday()], d.day, AR_MONTHS[d.month - 1])


def money(v):
    try:
        return "{:,.2f}".format(float(v)).replace(".00", "")
    except (TypeError, ValueError):
        return "—"


def did_for(name):
    p = db.person(name)
    if p and p.get("did"):
        return p["did"]
    try:
        return str((HOST.lookup_did(name) if HOST.lookup_did else "") or "")
    except Exception:
        return ""


def mention(name):
    did = did_for(name)
    return ("<@%s>" % did) if did else ("@" + str(name or "؟"))


def _role_mentions(role):
    names = db.names_with_role(role)
    return " ".join(mention(n) for n in names) or ("@أصيل" if role == "lead" else "@فيصل")


def _role_ids(role):
    return [d for d in (did_for(n) for n in db.names_with_role(role)) if d]


def channel_name(project):
    base = re.sub(r"[^0-9A-Za-z؀-ۿ]+", "-", str(project.get("title") or "مشروع"))
    return ("مقاولات-" + base.strip("-")).lower()[:90]


def _who_for(project, it):
    """The handover line is asked of the lead, every other line of the site supervisor."""
    if it.get("is_handover"):
        leads = db.names_with_role("lead")
        return leads[0] if leads else (project.get("supervisor") or "")
    return project.get("supervisor") or ""


def header_text(p):
    lines = ["**%s**" % p["title"],
             "المالك: %s · الوحدة: %s" % (p.get("owner") or "—", p.get("unit") or "—"),
             "مشرف الموقع: %s" % mention(p.get("supervisor")),
             "المبلغ المعتمد: %s ر.س" % money(p.get("total_sar")), "", "**البنود:**"]
    for it in p["items"]:
        lines.append("%d. %s — %s" % (it["pos"], it["name"], fmt_date(it.get("due"))))
    lines += ["", "كل بند: تنبيه قبل موعده بيومين، ويوم الموعد الساعة 4 العصر يجي سؤال «خلص؟».",
              "«خلص» يقفل البند بـ%d صور على الأقل تنرفع هنا. «تأخر» يطلب السبب والموعد الجديد."
              % db.PHOTOS_NEEDED]
    return NL.join(lines)


# ---------------------------------------------------------------- the pinned card
# One Discord embed per project channel, pinned, EDITED in place by the tick whenever what it
# shows changes (a line closes, moves, stops, or a date passes). Owner 2026-11-24: «ما يمدينا
# نحسنه؟» — the plain-text header was read once and went stale.

CARD_COLOR = 0xA57A2C            # --gold-logo: Ouja's brand gold, a mark (the embed's side bar)


def _words(s):
    return {w for w in re.split(r"[\W_]+", str(s or "").lower())
            if w and w != "وحدة"}


def _unit_is_in_title(p):
    u = _words(p.get("unit"))
    return bool(u) and u <= _words(p.get("title"))


def _line_mark(it, today):
    st = it.get("status")
    if st == "done":
        return "✅", ""
    if st == "blocked":
        return "⛔", " — واقف"
    if st == "awaiting_photos":
        return "📸", " — ينتظر الصور"
    try:
        late = dt.date.fromisoformat(str(it.get("due"))[:10]) < today
    except (TypeError, ValueError):
        late = False
    return ("🔴", " — فات موعده") if late else ("⏳", "")


def card_embed(p, today):
    h = engine.health(p["items"], today)
    state = {"ok": "على الخطة", "late": "🔴 فيه بند متأخر", "blocked": "⛔ فيه بند واقف",
             "done": "✅ خلص المشروع"}[h["state"]]
    lines = ["**%d من %d خلصت** · %s" % (h["done"], h["total"], state)]
    last = object()
    for it in sorted(p["items"], key=lambda x: x.get("pos", 0)):
        day = str(it.get("due") or "")[:10]
        if day != last:
            lines += ["", "**%s**" % fmt_date(day)]
            last = day
        mark, tail = _line_mark(it, today)
        name = "%d. %s" % (it["pos"], it["name"])
        lines.append("%s %s%s" % (mark, ("~~%s~~" % name) if mark == "✅" else name, tail))
    fields = [{"name": "المالك", "value": p.get("owner") or "—", "inline": True}]
    if p.get("unit") and not _unit_is_in_title(p):
        fields.append({"name": "الوحدة", "value": p["unit"], "inline": True})
    fields += [{"name": "مشرف الموقع", "value": mention(p.get("supervisor")), "inline": True},
               {"name": "المبلغ المعتمد", "value": "%s ر.س" % money(p.get("total_sar")),
                "inline": True}]
    foot = ("«خلص» يقفل البند بـ%d صور ترفعها هنا · «تأخر» يطلب السبب والموعد الجديد · "
            "تنبيه قبل الموعد بيومين، وسؤال «خلص؟» يوم الموعد 4 العصر" % db.PHOTOS_NEEDED)
    return {"title": str(p.get("title") or "")[:250], "description": NL.join(lines)[:4000],
            "color": CARD_COLOR, "fields": fields, "footer": {"text": foot}}


def card_hash(embed):
    return hashlib.sha1(json.dumps(embed, ensure_ascii=False, sort_keys=True)
                        .encode("utf-8")).hexdigest()[:16]


def card_payload(p, today):
    e = card_embed(p, today)
    return {"kind": "card", "key": "card|" + p["id"], "project_id": p["id"],
            "channel_id": p.get("channel_id"), "embed": e, "hash": card_hash(e),
            "msg_id": db.meta("card_msg|" + p["id"])}


CARD_RETRY_SEC = 600             # a card sent but not yet reported back is not re-sent for 10 min


def _card_due(p, today, now):
    pl = card_payload(p, today)
    if pl["hash"] == db.meta("card_hash|" + p["id"]):
        return None
    tried = str(db.meta("card_try|" + p["id"]) or "")
    if tried.startswith(pl["hash"] + "@"):
        try:
            at = dt.datetime.fromisoformat(tried.split("@", 1)[1])
            if (now - at).total_seconds() < CARD_RETRY_SEC:
                return None
        except ValueError:
            pass
    db.set_meta("card_try|" + p["id"], "%s@%s" % (pl["hash"], now.isoformat(timespec="seconds")))
    return pl


def reminder_text(kind, p, it, ch_ref=""):
    who = _who_for(p, it)
    nm = "«%s»" % it["name"]
    where = "%s %s" % (p["title"], ch_ref) if ch_ref else p["title"]
    if kind == "heads_up":
        return "⏰ %s، %s موعده %s (بعد يومين). كل شيء جاهز؟ إذا فيه شي بيأخره، قله الحين هنا." % (
            mention(who), nm, fmt_date(it["due"]))
    if kind == "ask":
        return "%s، %s موعده اليوم. خلص؟" % (mention(who), nm)
    if kind == "esc_lead":
        why = "انضغط «خلص» وما انرفعت الصور" if it.get("status") == "awaiting_photos" \
            else "ما انرد على سؤال الساعة 4"
        return "🟠 %s — %s في %s: %s. المسؤول: %s." % (_role_mentions("lead"), nm, where, why, who)
    if kind == "esc_boss":
        return "🔴 %s — %s في %s للحين بدون رد من أمس. وصل أصيل أمس الساعة 7." % (
            _role_mentions("boss"), nm, where)
    if kind == "blocked_boss":
        return "🔴 %s — %s في %s واقف من يوم كامل. السبب: %s" % (
            _role_mentions("boss"), nm, where, it.get("blocked_reason") or "—")
    return ""


def summary_text(projects, today):
    lines = ["☀️ **ملخص المقاولات — %s**" % fmt_date(today.isoformat())]
    for p in projects:
        h = engine.health(p["items"], today)
        state = {"ok": "على الخطة", "late": "🔴 متأخر", "blocked": "⛔ فيه بند واقف",
                 "done": "✅ خلص"}[h["state"]]
        lines += ["", "**%s** — %d من %d · %s" % (p["title"], h["done"], h["total"], state)]
        if h["next"]:
            lines.append("الجاي: «%s» %s" % (h["next"]["name"], fmt_date(h["next"].get("due"))))
        for it in h["late"]:
            if it.get("status") != "blocked":
                lines.append("متأخر: «%s» كان موعده %s" % (it["name"], fmt_date(it.get("due"))))
        for it in h["blocked"]:
            lines.append("واقف: «%s» — %s" % (it["name"], it.get("blocked_reason") or "—"))
    return NL.join(lines)


# ---------------------------------------------------------------- the tick

def _post(key, kind, p, it, text, target, view=None, mention_ids=None):
    return {"kind": "post", "key": key, "type": kind, "project_id": p["id"] if p else None,
            "item_id": it["id"] if it else None, "target": target,
            "channel_id": (p or {}).get("channel_id"), "category": category_name(),
            "admin_channel": admin_channel_name(), "text": text, "view": view,
            "mention_ids": mention_ids or []}


def open_text(p):
    return "%s — هذا مشروعك. الكرت المثبّت تحت يتحدث لحاله كل ما خلص بند أو تغيّر موعد." % (
        mention(p.get("supervisor")))


def open_payload(p):
    e = card_embed(p, local_now().date())
    return {"kind": "open", "key": "open|" + p["id"], "project_id": p["id"],
            "category": category_name(), "admin_channel": admin_channel_name(),
            "channel_name": channel_name(p), "text": open_text(p), "embed": e,
            "hash": card_hash(e)}


def _send(payload):
    if HOST.send is None:
        print("[contracting] HOST.send missing — not delivered:", payload.get("key"))
        return
    HOST.send(payload)


def tick(now=None):
    rep = {"enabled": enabled(), "dryrun": dryrun(), "opened": 0, "sent": 0, "logged": 0,
           "cards": 0}
    if not enabled():
        return rep
    now = local_now(now)
    live = not dryrun()
    active = db.projects(["active"])
    claimed, landed = db.sent_keys(dryrun=not live)
    for p in active:
        if live and not p.get("channel_id"):
            pl = open_payload(p)
            if pl["key"] not in claimed and db.claim(pl["key"], "open", p["id"], text=pl["channel_name"]):
                _send(pl)
                rep["opened"] += 1
            continue                     # reminders wait for the project's own channel
        ch_ref = ("<#%s>" % p["channel_id"]) if p.get("channel_id") else ""
        byid = {i["id"]: i for i in p["items"]}
        for r in engine.due_reminders(p["items"], now, claimed, p.get("started_at"), landed):
            it = byid[r["item_id"]]
            kind = r["kind"]
            text = reminder_text(kind, p, it, ch_ref)
            if kind in ("heads_up", "ask"):
                pl = _post(r["key"], kind, p, it, text, "project",
                           view="ask" if kind == "ask" else None,
                           mention_ids=[x for x in [did_for(_who_for(p, it))] if x])
            else:
                role = "lead" if kind == "esc_lead" else "boss"
                pl = _post(r["key"], kind, p, it, text, "admin", mention_ids=_role_ids(role))
            if db.claim(r["key"], kind, p["id"], it["id"], text, dryrun=not live):
                if live:
                    _send(pl)
                    rep["sent"] += 1
                else:
                    rep["logged"] += 1
    if live:                             # the pinned card: post once, then edit on change
        for p in active + db.projects(["done"]):
            if p.get("channel_id"):
                pl = _card_due(p, now.date(), now)
                if pl:
                    _send(pl)
                    rep["cards"] += 1
    if engine.summary_due(now, claimed, bool(active)):
        k = engine.summary_key(now.date())
        text = summary_text(active, now.date())
        if db.claim(k, "summary", text=text, dryrun=not live):
            if live:
                _send(_post(k, "summary", None, None, text, "admin"))
                rep["sent"] += 1
            else:
                rep["logged"] += 1
    return rep


def kick_open(project_id):
    """Right after «ابدأ» — open the channel now instead of waiting for the next tick."""
    if not enabled() or dryrun():
        return False
    p = db.project(project_id)
    if not p or p["status"] != "active" or p.get("channel_id"):
        return False
    pl = open_payload(p)
    if db.claim(pl["key"], "open", p["id"], text=pl["channel_name"]):
        _send(pl)
        return True
    return False


def delivered(report):
    """bot.py → package: what actually landed."""
    key = report.get("key") or ""
    ok = bool(report.get("ok"))
    if key.startswith("card|"):
        pid = key.split("|", 1)[1]
        if ok and report.get("msg_id"):
            db.set_meta("card_msg|" + pid, str(report["msg_id"]))
            db.set_meta("card_hash|" + pid, str(report.get("hash") or ""))
        return
    db.delivered(key, ok, report.get("msg_id") or "", report.get("error") or "")
    if key.startswith("open|"):
        pid = key.split("|", 1)[1]
        if ok and report.get("card_msg_id"):
            db.set_meta("card_msg|" + pid, str(report["card_msg_id"]))
            db.set_meta("card_hash|" + pid, str(report.get("hash") or ""))
        if ok and report.get("channel_id"):
            db.set_channel(pid, report["channel_id"])
        elif not ok:
            db.set_channel_error(pid, report.get("error") or "ما قدرت أفتح القناة")
    elif ok and report.get("type") == "ask" and report.get("item_id"):
        db.set_ask_msg(report["item_id"], report.get("msg_id") or "")


def retry_open(project_id):
    db.unclaim("open|" + project_id)
    db.execute("UPDATE contracting_projects SET channel_error=NULL WHERE id=?", (project_id,))
    return kick_open(project_id)


# ---------------------------------------------------------------- the buttons

def on_done_press(item_id, actor):
    it = db.item(item_id)
    if not it:
        return {"ok": False, "text": "ما لقيت البند."}
    if it["status"] == "done":
        return {"ok": False, "text": "«%s» خالص من قبل." % it["name"]}
    db.press_done(item_id, actor)
    have = len(it.get("photos") or [])
    return {"ok": True, "text": "📸 %s: ارفع %d صور «بعد» لـ«%s» هنا في القناة. البند يقفل بالصور." % (
        actor, max(db.PHOTOS_NEEDED - have, 1), it["name"])}


def on_delay(item_id, actor, reason, new_date_text, now=None):
    now = local_now(now)
    it = db.item(item_id)
    if not it:
        return {"ok": False, "error": "ما لقيت البند."}
    reason = str(reason or "").strip()
    if not reason:
        return {"ok": False, "error": "اكتب سبب التأخير."}
    new_due = engine.parse_date(new_date_text, now.date())
    err = engine.check_new_due(new_due, now.date()) if new_due else "التاريخ مو مفهوم — اكتبه مثل 5/12"
    if err:
        return {"ok": False, "error": err}
    p = db.project(it["project_id"], with_items=False)
    db.set_due(item_id, new_due, actor, reason, kind="delay")
    ch = "⏳ «%s» تأخر من %s إلى **%s**. السبب: %s — %s" % (
        it["name"], fmt_date(it.get("due")), fmt_date(new_due), reason, actor)
    adm = "⏳ %s: «%s» تأخر إلى %s. السبب: %s (%s)" % (
        p["title"], it["name"], fmt_date(new_due), reason, actor)
    return {"ok": True, "channel_text": ch, "admin_text": adm, "new_due": new_due}


def on_block(item_id, actor, what, now=None):
    now = local_now(now)
    it = db.item(item_id)
    if not it:
        return {"ok": False, "error": "ما لقيت البند."}
    what = str(what or "").strip()
    if not what:
        return {"ok": False, "error": "اكتب وش اللي موقف الشغل."}
    p = db.project(it["project_id"], with_items=False)
    db.block(item_id, actor, what, now.isoformat(timespec="seconds"))
    ch = "⛔ «%s» واقف: %s — %s. وصل أصيل." % (it["name"], what, actor)
    ref = ("<#%s>" % p["channel_id"]) if p.get("channel_id") else ""
    adm = "⛔ %s — «%s» في %s %s واقف: %s (%s)" % (
        _role_mentions("lead"), it["name"], p["title"], ref, what, actor)
    return {"ok": True, "channel_text": ch, "admin_text": adm, "admin_ids": _role_ids("lead")}


def on_photos(channel_id, urls, actor):
    """Photos dropped in a project channel → the line waiting for proof. None = not ours."""
    p = db.project_by_channel(channel_id)
    if not p or not urls:
        return None
    it = db.awaiting_photo_item(p["id"])
    if not it:
        return None
    it2, done = db.add_photos(it["id"], urls, actor)
    n = len(it2.get("photos") or [])
    if not done:
        return {"done": False, "text": "📸 %d من %d صور لـ«%s»." % (n, db.PHOTOS_NEEDED, it["name"])}
    finished = db.finish_if_complete(p["id"])
    rest = [i for i in db.items(p["id"]) if i["status"] != "done"]
    tail = ("🎉 خلص المشروع كله." if finished else
            "الجاي: «%s» %s" % (rest[0]["name"], fmt_date(rest[0].get("due"))) if rest else "")
    return {"done": True, "text": "✅ خلص «%s» — %d صور. %s" % (it["name"], n, tail)}
