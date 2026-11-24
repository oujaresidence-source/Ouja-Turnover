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

from . import db, engine, photos
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
    foot = ("ارفع صور الشغل هنا أي وقت، والبوت يسألك لأي بند · البند يقفل بـ%d صور · "
            "«تأخر» يطلب السبب والموعد الجديد · سؤال «خلص؟» يوم الموعد 4 العصر" % db.PHOTOS_NEEDED)
    return {"title": str(p.get("title") or "")[:250], "description": NL.join(lines)[:4000],
            "color": CARD_COLOR, "fields": fields, "footer": {"text": foot}}


CARD_VERSION = 2                 # bump → every card is edited once (v2: the «ملف للمالك» button)


def card_hash(embed):
    return hashlib.sha1((str(CARD_VERSION) + json.dumps(embed, ensure_ascii=False, sort_keys=True))
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


def group_text(kind, p, its, ch_ref=""):
    """Several lines due together → ONE message (owner 2026-11-24: three «خلص؟» in a row
    for the same afternoon read as noise)."""
    if len(its) == 1:
        return reminder_text(kind, p, its[0], ch_ref)
    who = _who_for(p, its[0])
    dues = {str(i.get("due") or "")[:10] for i in its}
    one_day = len(dues) == 1
    where = "%s %s" % (p["title"], ch_ref) if ch_ref else p["title"]
    bullets = NL.join("%d. «%s»%s" % (i["pos"], i["name"],
                                      "" if one_day else " — " + fmt_date(i.get("due")))
                      for i in its)
    if kind == "heads_up":
        when = (" (%s)" % fmt_date(its[0].get("due"))) if one_day else ""
        return NL.join(["⏰ %s، بعد يومين%s موعد هالبنود:" % (mention(who), when), bullets,
                        "كل شيء جاهز؟ إذا فيه شي بيأخرها، قله الحين هنا."])
    if kind == "ask":
        return NL.join(["%s، هالبنود موعدها اليوم:" % mention(who), bullets,
                        "خلصت؟ كل بند له أزراره تحت."])
    if kind == "esc_lead":
        rows = []
        for i in its:
            why = "انضغط «خلص» وما انرفعت الصور" if i.get("status") == "awaiting_photos" \
                else "ما انرد على سؤال الساعة 4"
            rows.append("• «%s»: %s" % (i["name"], why))
        return NL.join(["🟠 %s — في %s، المسؤول %s:" % (_role_mentions("lead"), where, who)] + rows)
    if kind == "esc_boss":
        return NL.join(["🔴 %s — في %s للحين بدون رد من أمس:" % (_role_mentions("boss"), where),
                        bullets, "وصل أصيل أمس الساعة 7."])
    return NL.join(reminder_text(kind, p, i, ch_ref) for i in its)


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


def _askview_due(p):
    """A «خلص؟» message whose lines changed (one closed) → its buttons are redrawn: a done
    line shows a grey «✅ خلص» instead of live buttons nobody should press again."""
    out, by_msg = [], {}
    for it in p["items"]:
        if it.get("ask_msg_id"):
            by_msg.setdefault(str(it["ask_msg_id"]), []).append(it)
    for msg, its in by_msg.items():
        done = ",".join(sorted(i["id"] for i in its if i.get("status") == "done"))
        if done == (db.meta("askv|" + msg) or ""):
            continue
        db.set_meta("askv|" + msg, done)
        out.append({"kind": "askview", "key": "askv|" + msg, "project_id": p["id"],
                    "channel_id": p.get("channel_id"), "msg_id": msg,
                    "ask_items": [{"id": i["id"], "pos": i["pos"], "name": i["name"],
                                   "done": i.get("status") == "done"}
                                  for i in sorted(its, key=lambda x: x.get("pos", 0))]})
    return out


OWNERPDF_WEEKDAY = 3                     # Thursday
OWNERPDF_HOURS = (12, 20)


def _ownerpdf_due(p, now, claimed):
    """The owner's file, to #مقاولات-الإدارة: every Thursday afternoon while the project runs,
    and once when it finishes (the handover file)."""
    if p["status"] == "done":
        key, reason = "ownerpdf|%s|final" % p["id"], "final"
    elif (p["status"] == "active" and now.weekday() == OWNERPDF_WEEKDAY
          and OWNERPDF_HOURS[0] <= now.hour < OWNERPDF_HOURS[1]
          and str(p.get("started_at") or "")[:10] < now.date().isoformat()):
        key, reason = "ownerpdf|%s|%s" % (p["id"], now.date().isoformat()), "weekly"
    else:
        return None
    if key in claimed or not db.claim(key, "ownerpdf", p["id"], text=p["title"]):
        return None
    return ownerpdf_payload(p["id"], reason, key)


def ownerpdf_payload(project_id, reason, key=""):
    return {"kind": "ownerpdf", "key": key or "ownerpdf|%s|ask" % project_id,
            "project_id": project_id, "reason": reason, "category": category_name(),
            "admin_channel": admin_channel_name()}


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
        groups = {}                      # (kind, who) → reminders due together, one message
        for r in engine.due_reminders(p["items"], now, claimed, p.get("started_at"), landed):
            it = byid[r["item_id"]]
            kind = r["kind"]
            gk = (kind, _who_for(p, it), r["key"] if kind == "blocked_boss" else "")
            groups.setdefault(gk, []).append((r, it))
        for gk in [k for k in groups if k[0] == "ask" and len(groups[k]) > 5]:
            rows = groups.pop(gk)        # Discord: 5 button rows a message → 5 lines a message
            for n in range(0, len(rows), 5):
                groups[(gk[0], gk[1], "part%d" % n)] = rows[n:n + 5]
        for (kind, _who, _solo), rows in groups.items():
            its = [it for _r, it in rows]
            text = group_text(kind, p, its, ch_ref)
            got = [(r, it) for r, it in rows
                   if db.claim(r["key"], kind, p["id"], it["id"], text, dryrun=not live)]
            if not got:
                continue
            if len(got) != len(rows):
                its = [it for _r, it in got]
                text = group_text(kind, p, its, ch_ref)
            first_r, first_it = got[0]
            if kind in ("heads_up", "ask"):
                pl = _post(first_r["key"], kind, p, first_it, text, "project",
                           view="ask" if kind == "ask" else None,
                           mention_ids=[x for x in [did_for(_who_for(p, first_it))] if x])
            else:
                role = "lead" if kind == "esc_lead" else "boss"
                pl = _post(first_r["key"], kind, p, first_it, text, "admin",
                           mention_ids=_role_ids(role))
            pl["keys"] = [r["key"] for r, _it in got]
            pl["item_ids"] = [it["id"] for _r, it in got]
            pl["ask_items"] = [{"id": it["id"], "pos": it["pos"], "name": it["name"], "done": False}
                               for _r, it in got]
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
                for pl in _askview_due(p):
                    _send(pl)
                    rep["cards"] += 1
                pl = _ownerpdf_due(p, now, claimed)
                if pl:
                    _send(pl)
                    rep["sent"] += 1
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
    if key.startswith("askv|"):
        return
    keys = report.get("keys") or [key]
    for k in keys:
        db.delivered(k, ok, report.get("msg_id") or "", report.get("error") or "")
    if ok and report.get("type") == "ask" and report.get("item_ids"):
        for iid in report["item_ids"]:
            db.set_ask_msg(iid, report.get("msg_id") or "")
        return
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
    """«خلص». The instruction to upload photos goes ONLY to the presser (ephemeral) — the
    channel sees the result, not the paperwork. A line that already has its photos (they
    came first, through the picker) closes right here."""
    it = db.item(item_id)
    if not it:
        return {"ok": False, "text": "ما لقيت البند."}
    if it["status"] == "done":
        return {"ok": False, "text": "«%s» خالص من قبل." % it["name"]}
    db.press_done(item_id, actor)
    have = len(it.get("photos") or [])
    if have >= db.PHOTOS_NEEDED:
        p = db.project(it["project_id"])
        r = _attach(p, db.item(item_id), [], actor)
        return {"ok": True, "done": True, "text": r["text"]}
    text = "📸 ارفع %d صور «بعد» لـ«%s» هنا في القناة. البند يقفل بالصور." % (
        max(db.PHOTOS_NEEDED - have, 1), it["name"])
    if any(not b.get("choice") for b in db.batches(it["project_id"])):
        text += " وإذا رفعتها قبل، اختر هالبند من قائمة «لأي بند؟» فوق."
    return {"ok": True, "done": False, "ephemeral": True, "text": text}


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


def _photo_dicts(urls, project_id, message_id="", keep_copy=True):
    out = []
    for u in urls or []:
        d = dict(u) if isinstance(u, dict) else {"url": u}
        raw = d.pop("raw", None)
        if keep_copy and not d.get("file"):
            d["file"] = photos.keep(d.get("url"), project_id, raw)
        if message_id:
            d.setdefault("msg", str(message_id))
        if d.get("url") or d.get("file"):
            out.append(d)
    return out


def _attach(p, it, ph, actor):
    """Photos onto one line that is waiting for them. → {done, text}."""
    it2, done = db.add_photos(it["id"], ph, actor)
    n = len(it2.get("photos") or [])
    if not done:
        return {"done": False, "text": "📸 %d من %d صور لـ«%s»." % (n, db.PHOTOS_NEEDED, it["name"])}
    finished = db.finish_if_complete(p["id"])
    rest = [i for i in db.items(p["id"]) if i["status"] != "done"]
    tail = ("🎉 خلص المشروع كله." if finished else
            "الجاي: «%s» %s" % (rest[0]["name"], fmt_date(rest[0].get("due"))) if rest else "")
    return {"done": True, "text": "✅ خلص «%s» — %d صور. %s" % (it["name"], n, tail)}


PICK_MAX_LINES = 23                      # Discord: 25 options a menu, two are ours


def picker(p, b, note=""):
    """The «لأي بند؟» menu for one batch of photos."""
    its = [i for i in p["items"] if i.get("status") != "done"]
    its.sort(key=lambda i: (0 if i.get("status") == "awaiting_photos" else 1, i.get("pos", 0)))
    opts = []
    for i in its[:PICK_MAX_LINES]:
        if i.get("status") == "awaiting_photos":
            desc = "ينتظر الصور (%d من %d)" % (len(i.get("photos") or []), db.PHOTOS_NEEDED)
        else:
            desc = "موعده " + fmt_date(i.get("due"))
        opts.append({"value": i["id"], "label": ("%d. %s" % (i["pos"], i["name"]))[:100],
                     "description": desc[:100]})
    opts.append({"value": "progress", "label": "📷 صور شغل جاري — مو بند خالص",
                 "description": "تنحفظ لملف المالك، وما تقفل بند"})
    opts.append({"value": "ignore", "label": "✖ مو صور شغل", "description": "ما تنحسب"})
    n = len(b["photos"])
    head = note or ("📸 %s — وصلت %s. لأي بند؟" % (b.get("by") or "", "صورة" if n == 1 else "%d صور" % n))
    text = head + NL + "اختيار البند يعني إنه خلص، ويقفل لما توصل %d صور." % db.PHOTOS_NEEDED
    first = next((x.get("url") for x in b["photos"] if x.get("url")), "")
    return {"batch_id": b["id"], "text": text, "options": opts, "image_url": first}


def on_photos(channel_id, urls, actor, message_id="", keep_copy=True):
    """Photos dropped in a project channel. None = not a project channel.
    Exactly one line waiting → they count for it. Otherwise (none waiting, or several) they
    are held and the channel gets a «لأي بند؟» menu — nothing is ever silently dropped
    (owner 2026-11-24: Abo Amen's photos came before the question and vanished)."""
    p = db.project_by_channel(channel_id)
    if not p or not urls or p["status"] != "active":
        return None
    ph = _photo_dicts(urls, p["id"], message_id, keep_copy)
    if not ph:
        return None
    waiting = db.awaiting_items(p["id"])
    if len(waiting) == 1:
        return _attach(p, waiting[0], ph, actor)
    b = db.new_batch(p["id"], ph, actor, message_id)
    return {"done": False, "pick": picker(p, b)}


def picker_posted(batch_id, msg_id):
    db.set_batch_picker(batch_id, msg_id)


def on_pick(batch_id, choice, actor):
    """Someone chose a line (or «شغل جاري» / «مو صور شغل») for a held batch.
    → {ok, final (the menu message becomes this), done, text (error, to the presser only)}"""
    b = db.batch(batch_id)
    if not b:
        return {"ok": False, "text": "ما لقيت الصور."}
    if b.get("choice"):
        return {"ok": False, "text": "انحسبت من قبل (%s)." % (b.get("resolved_by") or "")}
    p = db.project(b["project_id"])
    n = len(b["photos"])
    if choice in ("progress", "ignore"):
        if not db.resolve_batch(batch_id, choice, actor):
            return {"ok": False, "text": "انحسبت من قبل."}
        if choice == "progress":
            db.event(p["id"], "progress_photos", actor, "%d صور" % n)
            return {"ok": True, "done": False,
                    "final": "📷 %d صور شغل جاري — انحفظت لملف المالك. (%s)" % (n, actor)}
        return {"ok": True, "done": False, "final": "✖ ما انحسبت. (%s)" % actor}
    it = db.item(choice)
    if not it or it["project_id"] != b["project_id"]:
        return {"ok": False, "text": "ما لقيت البند."}
    if it["status"] == "done":
        return {"ok": False, "text": "«%s» خالص من قبل — اختر بند ثاني." % it["name"]}
    if not db.resolve_batch(batch_id, it["id"], actor):
        return {"ok": False, "text": "انحسبت من قبل."}
    if it["status"] != "awaiting_photos":
        db.press_done(it["id"], actor)
    r = _attach(p, db.item(it["id"]), b["photos"], actor)
    if r["done"]:
        return {"ok": True, "done": True, "final": r["text"]}
    have = len(db.item(it["id"]).get("photos") or [])
    return {"ok": True, "done": False,
            "final": "📸 %d من %d صور لـ«%s» — ارفع الباقي هنا. (%s)" % (
                have, db.PHOTOS_NEEDED, it["name"], actor)}


def backfill_candidates(channel_id, messages):
    """Photos posted in a project channel BEFORE this feature existed (or while the bot was
    down). `messages` = [{id, by, urls:[...]}] oldest first. Each photo not counted anywhere
    becomes its own one-photo batch, so each can go to a different line.
    → [picker dicts] (empty when nothing is new). Runs once per project (meta flag)."""
    p = db.project_by_channel(channel_id)
    if not p or p["status"] != "active":
        return []
    flag = "backfill|" + p["id"]
    if db.meta(flag):
        return []
    db.set_meta(flag, local_now().isoformat(timespec="seconds"))
    known = db.known_photo_msgs(p["id"])
    out = []
    for m in messages or []:
        if str(m.get("id")) in known:
            continue
        for u in m.get("urls") or []:
            ph = _photo_dicts([u], p["id"], m.get("id"))
            if not ph:
                continue
            b = db.new_batch(p["id"], ph, m.get("by") or "", m.get("id"))
            out.append(picker(p, b, note="📸 صورة نزلت قبل من %s — لأي بند؟" % (m.get("by") or "")))
    return out


# ---------------------------------------------------------------- the owner's file

def owner_pdf(project_id, reason="ask", by=""):
    """Build the owner's PDF (contracting.ownerpdf). → {ok, path, name, caption, error}.
    The bot posts it to #مقاولات-الإدارة; Faisal forwards it — never sent to the owner here."""
    from . import ownerpdf
    today = local_now().date()
    path, name, p = ownerpdf.render(project_id, reason, today)
    if not p:
        return {"ok": False, "error": "المشروع مو موجود"}
    label = {"weekly": "تقرير الخميس", "final": "ملف التسليم 🎉"}.get(
        reason, "نسخة طلبها %s" % by if by else "نسخة محدثة")
    if not path:
        return {"ok": False, "error": "ما قدرت أطلع ملف «%s» — جرب من الداشبورد بعد شوي." % p["title"]}
    owner = (" (%s)" % p["owner"]) if p.get("owner") else ""
    cap = "📄 ملف المالك — **%s** · %s. حوّله للمالك%s على الواتساب." % (p["title"], label, owner)
    return {"ok": True, "path": path, "name": name, "caption": cap}
