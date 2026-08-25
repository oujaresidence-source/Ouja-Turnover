"""
brain.recommend — "Today's Move". Computes (or loads) one recommendation per day from the
live signals, and runs the Approve -> hand-to-adapter flow. Phase 1 never sends live: the
active adapter is CSV export; Approve writes contact_log (status 'queued') + audit_log so
the Governor immediately accounts for everyone in the package.
"""

import json
from collections import Counter
from . import db, signals as sig_mod, campaigns, audience as aud_mod, governor, adapters, members, settings
from .util import now_iso, today_iso


def _mask_phone(p):
    p = p or ""
    return ("…" + p[-3:]) if len(p) > 3 else p


def _excluded_summary(excluded):
    by_reason = Counter(e.get("reason_en") or e.get("reason") or "other" for e in excluded)
    return {"total": len(excluded), "by_reason": dict(by_reason),
            "sample": [{"first_name": e.get("first_name"), "phone": _mask_phone(e.get("phone")),
                        "reason": e.get("reason"), "reason_en": e.get("reason_en")}
                       for e in excluded[:40]]}


def _latest_for_today():
    return db.q1("SELECT * FROM recommendations WHERE date=? ORDER BY id DESC LIMIT 1", (today_iso(),))


def _store(decision, aud, signals):
    silent = decision.get("silent")
    excluded = aud.get("excluded", []) if aud else []
    rec_id = db.execute(
        "INSERT INTO recommendations(date, campaign_code, audience, audience_size, "
        "projected_replies, projected_bookings, projected_revenue, rationale, signals_json, "
        "excluded_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (today_iso(), decision.get("code"),
         json.dumps(aud.get("audience_ids", []) if aud else []),
         aud.get("audience_size", 0) if aud else 0,
         (aud.get("projected", {}).get("replies", 0) if aud else 0),
         (aud.get("projected", {}).get("bookings", 0) if aud else 0),
         (aud.get("projected", {}).get("revenue", 0) if aud else 0),
         json.dumps({"ar": decision.get("reason"), "en": decision.get("reason_en")}, ensure_ascii=False),
         json.dumps(signals, ensure_ascii=False),
         json.dumps({**_excluded_summary(excluded),
                     "demand": (aud or {}).get("demand"), "adr": (aud or {}).get("adr")}, ensure_ascii=False),
         "silent" if silent else "proposed", now_iso()))
    db.audit("system", "recommendation_created",
             {"rec_id": rec_id, "code": decision.get("code"), "silent": bool(silent),
              "audience_size": aud.get("audience_size", 0) if aud else 0})
    return rec_id


def compute_today(force=False):
    """Ensure today's recommendation exists; return its id. Locked once approved/sent."""
    db.init_db()
    campaigns.seed_campaigns()
    members.ensure_seeded()
    existing = _latest_for_today()
    if existing and (existing["status"] in ("approved", "sent")):
        return existing["id"]
    if existing and not force:
        return existing["id"]
    if existing and force:
        db.execute("DELETE FROM recommendations WHERE id=? AND status IN ('proposed','silent')",
                   (existing["id"],))
    signals = sig_mod.compute_signals()
    decision = campaigns.select_campaign(signals)
    signals["nights_to_fill"] = decision.get("nights_to_fill", 0)   # the nights this move tries to fill
    aud = None if decision.get("silent") else aud_mod.build_audience(decision)
    return _store(decision, aud, signals)


def _row_view(row, include_signals=True):
    if row is None:
        return None
    d = dict(row)
    rationale = {}
    try:
        rationale = json.loads(d.get("rationale") or "{}")
    except (ValueError, TypeError):
        rationale = {"ar": d.get("rationale")}
    excluded = {}
    try:
        excluded = json.loads(d.get("excluded_json") or "{}")
    except (ValueError, TypeError):
        pass
    signals = {}
    if include_signals:
        try:
            signals = json.loads(d.get("signals_json") or "{}")
        except (ValueError, TypeError):
            pass
    ids = []
    try:
        ids = json.loads(d.get("audience") or "[]")
    except (ValueError, TypeError):
        pass
    camp = campaigns.get_campaign(d.get("campaign_code")) if d.get("campaign_code") else None
    token = settings.get("karzoum_name_token") or "{name}"
    paste_message = ((camp.get("message_template") or "").replace("{name}", token)) if camp else None
    preview = []
    if ids:
        mrows = {m["id"]: m for m in members.get_by_ids(ids[:60])}
        for mid in ids[:60]:
            m = mrows.get(mid)
            if m:
                preview.append({"first_name": m.get("first_name"), "tier": m.get("tier"),
                                "phone": _mask_phone(m.get("phone")), "stays": m.get("stays_count")})
    win = governor.send_window()
    # KPI / success bar — success = the targeted open nights actually book up (Faisal's call)
    import math
    ntf = int((signals or {}).get("nights_to_fill") or 0)
    conv = settings.get_float("expected_bookings_per_message")
    fill_pct = settings.get_int("success_fill_pct")
    asize = int(d.get("audience_size") or 0)
    kpi = {
        "audience": asize,
        "expected_bookings": round(asize * conv, 1),
        "conv_pct": round(conv * 100, 1),
        "nights_to_fill": ntf,
        "success_nights": math.ceil(ntf * fill_pct / 100) if ntf else 0,
        "success_pct": fill_pct,
    }
    return {
        "id": d.get("id"), "date": d.get("date"), "status": d.get("status"),
        "kpi": kpi,
        "silent": d.get("status") == "silent",
        "code": d.get("campaign_code"),
        "campaign": ({"code": camp.get("code"), "name": camp.get("name"), "offer": camp.get("offer"),
                      "lever": camp.get("lever"), "message_template": camp.get("message_template"),
                      "template_name": camp.get("template_name"), "footer": camp.get("footer"),
                      "image_prompt": camp.get("image_prompt"), "tier_targets": camp.get("tier_targets")}
                     if camp else None),
        "paste_message": paste_message,
        "audience_size": d.get("audience_size"),
        "audience_preview": preview,
        "projected": {"replies": d.get("projected_replies"), "bookings": d.get("projected_bookings"),
                      "revenue": d.get("projected_revenue")},
        "rationale": rationale.get("ar"), "rationale_en": rationale.get("en"),
        "excluded": excluded,
        "scheduled_time": win["scheduled_time"],
        "daily_cap": governor.effective_daily_cap(), "remaining_today": governor.remaining_today(),
        "signals": signals,
    }


def todays_view(force=False):
    rid = compute_today(force=force)
    return _row_view(db.q1("SELECT * FROM recommendations WHERE id=?", (rid,)))


def get_view(rec_id):
    return _row_view(db.q1("SELECT * FROM recommendations WHERE id=?", (rec_id,)))


# ---------------- approve / reject ----------------

def _build_package(rec_row):
    """Audience-only rows (Name/Phone/Tag) — Karzoum does the name merge in its own composer,
    so we do NOT pre-merge the message here."""
    ids = json.loads(rec_row["audience"] or "[]")
    return [{"member_id": m["id"], "first_name": m.get("first_name") or "",
             "phone": m.get("phone"), "tier": m.get("tier"),
             "campaign_code": rec_row["campaign_code"]} for m in members.get_by_ids(ids)]


def approve(rec_id, actor="owner"):
    """Build the package, hand it to the active adapter, write contact_log + audit_log.
    Phase 1: adapter = CSV export, status stays 'queued' (nothing dispatches live)."""
    row = db.q1("SELECT * FROM recommendations WHERE id=?", (rec_id,))
    if not row:
        return {"ok": False, "error": "recommendation_not_found"}
    if row["status"] == "silent":
        return {"ok": False, "error": "silent_day_nothing_to_send"}
    if row["status"] in ("approved", "sent"):
        return {"ok": False, "error": "already_%s" % row["status"]}

    pkg = _build_package(row)
    if not pkg:
        return {"ok": False, "error": "empty_audience"}

    adapter = adapters.get_active()
    result = adapter.deliver(pkg, row)

    sent_at = now_iso()
    db.executemany(
        "INSERT INTO contact_log(member_id, campaign_code, sent_at, status, replied) "
        "VALUES(?,?,?,?,0)",
        [(p["member_id"], p["campaign_code"], sent_at, "queued") for p in pkg])
    ids = [p["member_id"] for p in pkg]
    if ids:
        marks = ",".join("?" for _ in ids)
        db.execute("UPDATE members SET last_contacted=? WHERE id IN (%s)" % marks,
                   tuple([sent_at] + ids))
    db.execute("UPDATE recommendations SET status='approved' WHERE id=?", (rec_id,))
    db.audit(actor, "approve_recommendation",
             {"rec_id": rec_id, "campaign": row["campaign_code"], "count": len(pkg),
              "adapter": adapter.name, "result": {k: v for k, v in result.items() if k != "csv_text"}})
    return {"ok": True, "count": len(pkg), "adapter": adapter.name, **result}


def reject(rec_id, actor="owner"):
    row = db.q1("SELECT * FROM recommendations WHERE id=?", (rec_id,))
    if not row:
        return {"ok": False, "error": "not_found"}
    db.execute("UPDATE recommendations SET status='rejected' WHERE id=?", (rec_id,))
    db.audit(actor, "reject_recommendation", {"rec_id": rec_id})
    return {"ok": True}
