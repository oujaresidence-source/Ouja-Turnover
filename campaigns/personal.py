# -*- coding: utf-8 -*-
"""
campaigns.personal — the per-person sender (owner, 2026-11-23: «كل واحد بالوقت الصح، بصورة شقته»).

A Hatif campaign has ONE send time and ONE header picture for everyone. This sends one
Meta-approved template per person (Hatif `sendTemplate`), at THAT person's time, with a photo
of the apartment THEY usually book (43 % of returning guests rebook the same unit).

    load(batch, rows)   validate + queue. rows: {phone, campaign, template, values[], image_url,
                        send_at (ISO, Riyadh if no offset), lang}. One campaign per person, ever
                        (UNIQUE(campaign, phone_key)): re-loading a list never sends twice.
    tick(now)           the due rows, at most CAMPAIGN_PERSONAL_PER_MIN, through every gate.
    cancel(batch)       stop what has not gone yet.
    summary()           counts per batch / campaign / state.

Gates, in this order, for every single send:
    CAMPAIGN_PERSONAL=1 · CAMPAIGN_PERSONAL_DRYRUN=0 (default 1: nothing goes) · Hatif keys ·
    HATIF_CHANNEL_ID · HATIF_TEST_NUMBERS (when set, ONLY those numbers go; the rest wait) ·
    the opt-out list («إيقاف العروض», typed «ايقاف») → state «suppressed».
A 429 puts the row back and ends the tick (Hatif's 120/min limit is shared with the reader).
The phone number is erased the moment a row is sent, suppressed or failed.
"""
import datetime
import traceback

from . import config, db, engine

RIYADH = datetime.timezone(datetime.timedelta(hours=3))


def _hatif():
    try:
        from hatif import client as hc, config as hcfg
    except Exception:
        return None, None
    return (hc if hcfg.configured() else None), hcfg


def _utc(send_at):
    """ISO (Riyadh when it has no offset) → naive-UTC ISO, the queue's clock."""
    t = datetime.datetime.fromisoformat(str(send_at).strip().replace(" ", "T"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=RIYADH)
    return t.astimezone(datetime.timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()


def load(batch, rows):
    """→ {"queued", "duplicate", "rejected": [(index, why)]}. Never raises on a bad row."""
    batch = str(batch or "").strip()[:60]
    out = {"queued": 0, "duplicate": 0, "rejected": []}
    if not batch:
        out["rejected"].append((-1, "batch name missing"))
        return out
    salt = db.salt()
    for i, r in enumerate(rows or []):
        try:
            phone = engine.normalize_phone((r or {}).get("phone"))
            if not phone:
                raise ValueError("phone")
            for k in ("campaign", "template", "send_at"):
                if not str(r.get(k) or "").strip():
                    raise ValueError(k)
            img = str(r.get("image_url") or "").strip()
            if img and not img.startswith("https://"):
                raise ValueError("image_url must be https")
            row = {"batch": batch, "campaign": str(r["campaign"])[:60], "template": str(r["template"])[:80],
                   "lang": str(r.get("lang") or "ar")[:8], "phone": phone,
                   "phone_key": engine.phone_key(phone, salt), "last4": engine.last4(phone),
                   "vals": [str(v)[:200] for v in (r.get("values") or [])][:6],
                   "image_url": img or None, "send_at": _utc(r["send_at"])}
        except Exception as e:
            out["rejected"].append((i, str(e)[:40] or type(e).__name__))
            continue
        if db.queue_add(row):
            out["queued"] += 1
        else:
            out["duplicate"] += 1
    return out


def tick(now=None):
    try:
        return _tick(now or datetime.datetime.now(datetime.timezone.utc))
    except Exception as e:
        traceback.print_exc()
        return {"outcome": "error", "error": type(e).__name__}


def _tick(now):
    if not config.personal_enabled():
        return {"outcome": "off"}
    now_utc = (now.astimezone(datetime.timezone.utc).replace(tzinfo=None) if now.tzinfo else now)
    due = db.queue_due(now_utc.replace(microsecond=0).isoformat(), config.personal_per_tick())
    if not due:
        return {"outcome": "idle"}
    if config.personal_dryrun():
        return {"outcome": "dryrun", "due": len(due)}
    hc, hcfg = _hatif()
    if hc is None or hcfg is None:
        return {"outcome": "no_keys", "due": len(due)}
    from .service import is_suppressed, known_channel
    channel = hcfg.channel_id() or known_channel()          # learned from the first inbound event
    if not channel:
        return {"outcome": "no_channel", "due": len(due)}
    allow = hcfg.test_numbers()
    sent = suppressed = failed = waiting = 0
    for r in due:
        if allow and r["phone"] not in allow:
            waiting += 1
            continue                                     # test mode: only the allowed numbers go
        if not db.queue_claim(r["id"]):
            continue                                     # another bot copy has it
        if is_suppressed(phone=r["phone"]):
            db.queue_finish(r["id"], "suppressed")
            suppressed += 1
            continue
        try:
            hc.send_template(channel, r["phone"], r["template"], r["lang"], r["vals"], r["image_url"])
        except Exception as e:
            status = getattr(e, "status", None)
            if status == 429:
                db.queue_finish(r["id"], "queued")       # back in line; stop this tick
                break
            db.queue_finish(r["id"], "failed", "%s %s" % (type(e).__name__, status or ""))
            failed += 1
            continue
        db.queue_finish(r["id"], "sent")
        sent += 1
    return {"outcome": "ran", "sent": sent, "suppressed": suppressed, "failed": failed,
            "waiting_test_mode": waiting}


def cancel(batch):
    return db.queue_cancel(batch)


def summary():
    return {"enabled": config.personal_enabled(), "dryrun": config.personal_dryrun(),
            "per_min": config.personal_per_tick(), "batches": db.queue_summary()}
