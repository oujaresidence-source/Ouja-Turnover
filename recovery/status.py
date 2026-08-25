# -*- coding: utf-8 -*-
"""
recovery.status — everything the «استرداد التجربة» dashboard tab shows, in one payload.

Lives here rather than in bot.py so the tab's numbers come from the SAME functions the
engine uses to make decisions. A dashboard that computes the equity gap its own way is a
dashboard that can disagree with the thing it is reporting on.

Read-only. No writes, no Discord, no Hostaway.
"""

import datetime

from . import config, db, engine
from .host import call


def _owned_counts():
    """apartments-per-agent, straight from the Employee Calendar. Returns {} when the
    calendar is unavailable — the tab renders «—» rather than a wrong number."""
    try:
        from schedule import owners as _sowners
        pm = _sowners.permanent_map()
    except Exception:
        return {}, 0
    counts, total = {}, 0
    for ap in pm.get("apartments") or []:
        total += 1
        nm = ap.get("owner_name")
        if nm:
            counts[nm] = counts.get(nm, 0) + 1
    return counts, total


def _iso_days_ago(days):
    return (db.now_dt() - datetime.timedelta(days=days)).isoformat(timespec="seconds")


def agents_block(month_key=None):
    mk = month_key or db.month_key()
    stats = db.agent_stats(mk)
    owned, total_units = _owned_counts()
    rows = []
    for a in config.AGENTS:
        s = stats.get(a["id"], {})
        rows.append({
            "id": a["id"],
            "name": a["name"],
            "label": a.get("label") or "",
            "assigned": int(s.get("assigned_count") or 0),
            "contacted": int(s.get("contacted_count") or 0),
            "resolved": int(s.get("resolved_count") or 0),
            "breached": int(s.get("sla_breached_count") or 0),
            "conflict_debt": int(s.get("conflict_debt") or 0),
            "owns": owned.get(a["name"]),          # None = calendar unavailable
            "last_assigned_at": s.get("last_assigned_at"),
        })
    gap = engine.equity_gap(db.stats_map(mk), config.agent_ids())
    return {
        "rows": rows,
        "total_units": total_units,
        "gap": gap,
        "gap_alert_at": config.EQUITY_GAP_ALERT_THRESHOLD,
        "balanced": gap <= 2,
    }


def tickets_block(limit=40):
    rows = db.q(
        "SELECT id,reservation_id,guest_name,unit_name,score,severity,status,root_cause,"
        " headline_ar,assigned_agent_name,conflict_excluded_agent_name,in_house,"
        " created_at,due_at,contacted_at,resolved_at,sla_breached,call_attempts,"
        " call_link_opened_at,maintenance_ticket_id,physical_issue"
        " FROM recovery_tickets ORDER BY created_at DESC LIMIT ?", (int(limit),))
    open_states = ("OPEN", "ASSIGNED", "CONTACTED", "NO_ANSWER",
                   "MAINTENANCE_PENDING", "FOLLOWUP", "ESCALATED")
    return {
        "rows": rows,
        "open": sum(1 for r in rows if r.get("status") in open_states),
        "breached": sum(1 for r in rows if r.get("sla_breached")),
    }


def month_block(month_key=None):
    mk = month_key or db.month_key()
    rows = db.q("SELECT status,contacted_at,resolved_at,sla_breached,root_cause,created_at"
                " FROM recovery_tickets WHERE substr(created_at,1,7)=?", (mk,))
    total = len(rows)
    contacted = sum(1 for r in rows if r.get("contacted_at"))
    resolved = sum(1 for r in rows if r.get("resolved_at"))
    breached = sum(1 for r in rows if r.get("sla_breached"))
    causes = {}
    for r in rows:
        c = r.get("root_cause") or "—"
        causes[c] = causes.get(c, 0) + 1
    cost = db.month_cost(mk)

    def pct(n):
        return round(100.0 * n / total) if total else 0

    return {
        "month_key": mk,
        "total": total,
        "contacted": contacted, "contacted_pct": pct(contacted),
        "resolved": resolved, "resolved_pct": pct(resolved),
        "breached": breached,
        "root_causes": sorted(causes.items(), key=lambda kv: -kv[1]),
        "cost_sar": round(float(cost.get("sar") or 0), 2),
        "cost_tokens": int(cost.get("itok") or 0) + int(cost.get("otok") or 0),
        "cost_calls": int(cost.get("calls") or 0),
        "cost_escalations": int(cost.get("escalated") or 0),
        "analysed": int(cost.get("n") or 0),
    }


def repeat_units_block():
    """§9 — the apartments quietly costing reviews. The highest-value output here."""
    since = _iso_days_ago(config.REPEAT_UNIT_WINDOW_DAYS)
    rows = db.q(
        "SELECT listing_id, unit_name, COUNT(*) n, MAX(created_at) last_at"
        " FROM recovery_tickets WHERE created_at>=? AND listing_id IS NOT NULL"
        " GROUP BY listing_id HAVING n>=? ORDER BY n DESC, last_at DESC",
        (since, config.REPEAT_UNIT_THRESHOLD))
    return {"window_days": config.REPEAT_UNIT_WINDOW_DAYS,
            "threshold": config.REPEAT_UNIT_THRESHOLD,
            "rows": rows}


def skips_block(limit=25):
    """Why a guest did NOT get a ticket. Without this the tab can only say what happened,
    never what didn't."""
    rows = db.q("SELECT at,guest_name,unit_name,score,reason FROM recovery_skips"
                " ORDER BY id DESC LIMIT ?", (int(limit),))
    tally = {}
    for r in db.q("SELECT reason, COUNT(*) n FROM recovery_skips"
                  " WHERE at>=? GROUP BY reason", (_iso_days_ago(7),)):
        tally[r["reason"]] = r["n"]
    return {"rows": rows, "last7": sorted(tally.items(), key=lambda kv: -kv[1])}


def today_block():
    """Who is leaving today, and how many guests are inside an apartment right now.

    This is context, NOT the pipeline. A name appearing here does not mean a ticket is
    owed — a ticket needs a /guest score under the threshold, and most departures are
    perfectly happy. The tab labels it that way so nobody reads this list as a to-do.

    Every row is cross-checked against recovery_tickets so an existing ticket shows up
    beside the guest rather than the team wondering whether one was opened.
    """
    rows = call("todays_checkouts") or []
    ids = [str(r.get("reservation_id") or "") for r in rows if r.get("reservation_id")]
    have = {}
    if ids:
        marks = ",".join("?" * len(ids))
        for t in db.q("SELECT reservation_id,status,score,assigned_agent_name"
                      " FROM recovery_tickets WHERE reservation_id IN (%s)" % marks, ids):
            have[str(t["reservation_id"])] = t
    out = []
    for r in rows:
        t = have.get(str(r.get("reservation_id") or ""))
        out.append(dict(r,
                        ticket_status=(t or {}).get("status"),
                        ticket_score=(t or {}).get("score"),
                        ticket_agent=(t or {}).get("assigned_agent_name")))
    return {
        "date": db.now_dt().date().isoformat(),
        "checkouts": out,
        "checkouts_count": len(out),
        "no_phone": sum(1 for r in out if not r.get("has_phone")),
        "with_ticket": sum(1 for r in out if r.get("ticket_status")),
        "inhouse_count": call("inhouse_count"),      # None when bot.py did not inject it
        "available": bool(rows) or call("todays_checkouts") is not None,
    }


def state_block():
    ready, missing = config.ready_for_discord()
    if config.DRYRUN:
        mode, mode_ar = "dryrun", "تجريبي — يحسب ولا يرسل"
    elif not config.ENABLED:
        mode, mode_ar = "off", "مطفي"
    else:
        mode, mode_ar = "live", "شغّال"
    return {
        "enabled": bool(config.ENABLED),
        "dryrun": bool(config.DRYRUN),
        "mode": mode,
        "mode_ar": mode_ar,
        "ready_for_discord": ready,
        "missing": missing,
        "threshold": config.SCORE_THRESHOLD,
        "daily_cap": config.DAILY_TICKET_CAP,
        "window": "%s — %s" % (config.WINDOW_START, config.WINDOW_DEADLINE),
        "reminders": [config.REMINDER_1, config.REMINDER_2],
        "in_house_hours": config.IN_HOUSE_DEADLINE_HOURS,
    }


def payload(month_key=None):
    """The one object the tab renders. Every section is independently guarded: a failure
    in one block must not blank the whole page."""
    out = {"ok": True, "generated_at": db.now_iso()}
    for key, fn in (("state", state_block),
                    ("today", today_block),
                    ("agents", lambda: agents_block(month_key)),
                    ("tickets", tickets_block),
                    ("month", lambda: month_block(month_key)),
                    ("repeat_units", repeat_units_block),
                    ("skips", skips_block)):
        try:
            out[key] = fn()
        except Exception as e:
            out[key] = {"error": str(e)[:200]}
            out["ok"] = False
    return out
