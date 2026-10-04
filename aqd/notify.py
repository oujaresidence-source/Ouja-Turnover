# -*- coding: utf-8 -*-
"""
aqd.notify — the Arabic texts and their delivery through HOST.notify (bot.py posts to the
Discord channel AQD_CHANNEL, created on first use under «ضم الوحدات»).

NEVER an ID number or a phone in any of these texts. The latch columns
(notified_signed_at / notified_completed_at) are a LEDGER: stamped only after HOST.notify
returned without raising, so a Discord outage is retried on the next /api/aqd/list call instead
of silently swallowing the ping. Delivery failure never fails the request that caused it.
"""

import datetime

from . import db, engine
from .host import HOST


def _mention(created_by):
    try:
        ids = HOST.discord_ids() if HOST.discord_ids else {}
    except Exception:
        ids = {}
    did = str((ids or {}).get(created_by or "") or "")
    return ("<@%s> " % did) if did.isdigit() else ""


def signed_text(row):
    a = db.answers(row)
    who = "%s %s" % (engine.honorific(a), row.get("client_name") or "")
    pct = engine.pct(row.get("op_pct"))
    return ("%s✍️ وقّع %s عقد %s — %s وحدة، نسبة %s%% · بانتظار توقيع المشغّل"
            % (_mention(row.get("created_by")), who.strip(), row.get("ref") or "",
               row.get("units_count") or 0, pct))


def completed_text(row):
    return "✅ اكتمل العقد %s" % (row.get("ref") or "")


def attempts_cap_text(row):
    """R5. No name, no ID, no phone — the ref is the only number in it."""
    return "🔒 رابط العقد %s توقف بعد محاولات تحقق خاطئة كثيرة — أرسل للعميل رابط جديد من التبويب" % (row.get("ref") or "")


def attempts_cap(row):
    try:
        return _send("attempts_cap", attempts_cap_text(row), row)
    except Exception as e:
        print("[aqd] attempts_cap notify failed (non-fatal):", e)
        return False


def _send(kind, text, row):
    if not HOST.notify:
        return False
    HOST.notify({"kind": kind, "text": text, "contract_id": row.get("id"), "ref": row.get("ref")})
    return True


def _claim(cid, col):
    """Compare-and-set the latch to a claim BEFORE sending, so a sign request and a retry tick
    racing each other can never both post. A claim older than 10 minutes (a crash mid-send)
    is reclaimable."""
    stale = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(minutes=10)).replace(microsecond=0).isoformat()
    _i, n = db.execute("UPDATE aqd_contracts SET %s=? WHERE id=? AND (%s IS NULL OR (%s LIKE 'claim:%%' AND %s < ?))"
                       % (col, col, col, col), ("claim:" + db.now_iso(), int(cid), "claim:" + stale))
    return n == 1


def _deliver(row, col, kind, text):
    if not _claim(row["id"], col):
        return False
    try:
        if not _send(kind, text, row):
            raise RuntimeError("notify not wired")
    except Exception as e:
        print("[aqd] %s notify failed (will retry):" % kind, e)
        db.execute("UPDATE aqd_contracts SET %s=NULL WHERE id=?" % col, (int(row["id"]),))
        return False
    db.execute("UPDATE aqd_contracts SET %s=? WHERE id=?" % col, (db.now_iso(), int(row["id"])))
    return True


def signed(row):
    """Once per contract. -> True when this call delivered (and stamped) it."""
    row = db.get(row["id"]) or row
    if row.get("status") not in ("signed_owner", "completed"):
        return False
    return _deliver(row, "notified_signed_at", "signed", signed_text(row))


def completed(row):
    row = db.get(row["id"]) or row
    if row.get("status") != "completed":
        return False
    return _deliver(row, "notified_completed_at", "completed", completed_text(row))


def retry_pending():
    """The retry tick: called from the tab's list poll. Cheap when nothing is pending."""
    n = 0
    for r in db.pending_signed_notify():
        n += 1 if signed(r) else 0
    for r in db.pending_completed_notify():
        n += 1 if completed(r) else 0
    return n
