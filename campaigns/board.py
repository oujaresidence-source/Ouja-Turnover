# -*- coding: utf-8 -*-
"""
campaigns.board — «الحملات», the owner's one page for every WhatsApp campaign (2026-11-24:
«كيف اتابع كل الحملات؟ … ومتى تبدا ومين تستهدف وكم المتوقع العائد وكيف نحسب العايد»).

Hatif has NO campaign API, so the campaign list is a mirror: campaigns/board_seed.json
($STATE_DIR/campaign_board.json wins when it parses; re-read on mtime change). What Hatif shows
only on its own page (sent / delivered / read) is typed in by an admin; everything else is
measured here:

    taps      campaign_taps (the Hatif webhook) matched to the campaign by the person's phone key
    bookings  confirmed Hostaway reservations CREATED inside the campaign's window by a person
              who got it (phone key only — names are transliterated and would lie)
    baseline  how many of those people book in the same window with NO message: the group's
              back-tested rate (seed «baseline») scaled to the time measured so far. For «الليلة
              الثانية بنص» a real comparison group (role «holdout», never messaged) is shown too.
    lift      bookings − baseline: what the message itself brought.

compute() is PURE (no I/O): tests feed it fake reservations and assert every number.
"""
import datetime
import json
import os
import threading
import time
import traceback

from . import db
from .host import HOST

RIYADH = datetime.timezone(datetime.timedelta(hours=3))
SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "board_seed.json")
_CONFIRMED = ("new", "modified", "confirmed", "ownerstay")
_OWNER_KINDS = ("owner_call", "owner_later")


# ---------------------------------------------------------------- the campaign list
_seed_cache = {"path": None, "mtime": None, "data": None}
_seed_lock = threading.Lock()


def _state_path():
    d = os.environ.get("STATE_DIR", "")
    return os.path.join(d, "campaign_board.json") if d else ""


def _valid(d):
    return (isinstance(d, dict) and isinstance(d.get("campaigns"), list)
            and isinstance(d.get("groups"), dict))


def load_seed():
    """The live file when it parses, else the repo seed. A broken edit keeps the last good copy."""
    with _seed_lock:
        for path in (_state_path(), SEED):
            if not path or not os.path.exists(path):
                continue
            try:
                m = os.path.getmtime(path)
                if _seed_cache["path"] == path and _seed_cache["mtime"] == m:
                    return _seed_cache["data"]
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                if not _valid(d):
                    raise ValueError("shape")
                _seed_cache.update(path=path, mtime=m, data=d)
                return d
            except Exception:
                traceback.print_exc()
                if _seed_cache["data"] is not None:
                    return _seed_cache["data"]
        return {"campaigns": [], "groups": {}, "msg_cost_sar": 0.25}


# ---------------------------------------------------------------- time helpers
def to_utc(local_iso):
    """'2026-11-25T11:00' (Riyadh when no offset) → naive UTC datetime."""
    t = datetime.datetime.fromisoformat(str(local_iso).strip().replace(" ", "T"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=RIYADH)
    return t.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def _parse_dt(v):
    s = str(v or "").strip().replace("T", " ")
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return datetime.datetime.strptime(s[:n], fmt)
        except ValueError:
            continue
    return None


def _base_tpl(t):
    t = str(t or "")
    return t[:-4] if t.endswith("_img") else t


def _num(v):
    try:
        return None if v is None or v == "" else int(v)
    except (TypeError, ValueError):
        return None


def _r(x, n=1):
    return round(float(x), n)


# ---------------------------------------------------------------- the pure part
def compute(seed, numbers, audiences, taps, bookings, now_utc):
    """seed: board_seed dict · numbers: db.board_numbers() · audiences: db.audiences() ·
    taps: [{created_at, template, kind, phone_key}] · bookings: [{id, made (naive UTC dt),
    pkey, total, nights}] confirmed only · now_utc: naive UTC datetime.  → the board dict."""
    groups = seed.get("groups") or {}
    cost_each = float(seed.get("msg_cost_sar") or 0.25)
    camps = []
    for c in seed.get("campaigns") or []:
        n = numbers.get(c["id"]) or {}
        send_local = n.get("send_at") or c["send_at"]
        try:
            send = to_utc(send_local)
        except Exception:
            continue
        camps.append((c, n, send_local, send))

    # a tap with no audience match goes to the campaign of its template sent most recently before it
    by_tpl = {}
    for c, n, _, send in camps:
        if (n.get("status") or "") != "cancelled":
            by_tpl.setdefault(_base_tpl(c.get("template")), []).append((send, c["id"]))
    for v in by_tpl.values():
        v.sort()
    key_owner = {}
    for cid, roles in audiences.items():
        for pk, _ in roles.get("sent", []):
            key_owner.setdefault(pk, cid)
    tap_for = {}
    for t in taps:
        if t.get("kind") == "opt_out":
            k = "opt_out"
        else:
            k = t.get("kind") or "other"
        at = _parse_dt(t.get("created_at"))
        if at is None:
            continue
        cid = key_owner.get(t.get("phone_key") or "")
        if cid is None:
            for send, c_id in by_tpl.get(_base_tpl(t.get("template")), []):
                if send <= at:
                    cid = c_id
        if cid is not None:
            d = tap_for.setdefault(cid, {})
            d[k] = d.get(k, 0) + 1

    out, holdout = [], None
    tot = {"cost": 0.0, "people_sent": 0, "bookings": 0, "revenue": 0.0, "baseline": 0.0,
           "owner_replies": 0, "owner_signed": 0, "owner_monthly": 0.0, "taps": 0, "opt_out": 0,
           "campaigns_sent": 0, "campaigns_total": 0}
    for c, n, send_local, send in camps:
        g = groups.get(c.get("group")) or {}
        kind = g.get("kind") or "guest"
        win = int(g.get("window_days") or 14)
        end = send + datetime.timedelta(days=win)
        if (n.get("status") or "") == "cancelled":
            status = "cancelled"
        elif now_utc < send:
            status = "scheduled"
        elif now_utc < end:
            status = "measuring"
        else:
            status = "done"
        aud = audiences.get(c["id"], {}).get("sent", [])
        people = _num(n.get("sent")) or len(aud) or int(c.get("people") or 0)
        expect = [_r(people * float(x)) for x in (g.get("expect") or [0, 0, 0])]
        value = float(g.get("value") or 0)
        row = {
            "id": c["id"], "group": c.get("group"), "group_name": g.get("name") or c.get("group"),
            "title": c.get("title"), "who": c.get("who"), "habit": c.get("habit") or "",
            "kind": kind, "send_at": send_local, "send_utc": send.isoformat(),
            "window_days": win, "window_end_utc": end.isoformat(), "status": status,
            "people": people, "people_planned": int(c.get("people") or 0),
            "audience_loaded": len(aud), "unit": g.get("unit") or "", "value": value,
            "value_note": g.get("value_note") or "", "baseline_note": g.get("baseline_note") or "",
            "baseline_rate": g.get("baseline"),
            "expected": {"count": expect, "sar": [_r(x * value, 0) for x in expect]},
            "numbers": {k: _num(n.get(k)) for k in ("sent", "delivered", "read_n", "replied", "signed")},
            "note": n.get("note") or "", "taps": tap_for.get(c["id"], {}),
            "cost": _r(people * cost_each, 2) if status in ("measuring", "done") else 0.0,
            "cost_planned": _r(people * cost_each, 2),
        }
        tot["campaigns_total"] += 1 if status != "cancelled" else 0
        if status in ("measuring", "done"):
            tot["campaigns_sent"] += 1
            tot["people_sent"] += people
            tot["cost"] += row["cost"]
            tot["taps"] += sum(v for k, v in row["taps"].items() if k != "opt_out")
            tot["opt_out"] += row["taps"].get("opt_out", 0)
            upto = min(now_utc, end)
            frac = max(0.0, min(1.0, (upto - send).total_seconds() / (win * 86400.0)))
            row["measured_days"] = _r((upto - send).total_seconds() / 86400.0)
            if kind == "owner":
                replies = sum(row["taps"].get(k, 0) for k in _OWNER_KINDS)
                signed = _num(n.get("signed")) or 0
                row["actual"] = {"replies": replies, "signed": signed, "sar": _r(signed * value, 0)}
                tot["owner_replies"] += replies
                tot["owner_signed"] += signed
                tot["owner_monthly"] += signed * value
            else:
                keys = {pk for pk, _ in aud if pk}
                hit_people, revenue, nights, ids = set(), 0.0, 0, []
                for b in bookings:
                    if b.get("pkey") in keys and b.get("made") and send <= b["made"] < upto:
                        hit_people.add(b["pkey"])
                        revenue += float(b.get("total") or 0)
                        nights += int(b.get("nights") or 0)
                        ids.append(str(b.get("id")))
                rate = g.get("baseline")
                base = None if rate is None else _r(people * float(rate) * frac, 3)
                row["actual"] = {"bookings": len(hit_people), "sar": _r(revenue, 0), "nights": nights,
                                 "reservation_ids": ids[:50], "matched_by": "phone" if keys else "none"}
                row["baseline"] = base
                row["lift"] = None if base is None else _r(len(hit_people) - base, 3)
                tot["bookings"] += len(hit_people)
                tot["revenue"] += revenue
                tot["baseline"] += base or 0.0
        out.append(row)

    # the comparison group of «الليلة الثانية بنص»: never messaged, same 14 days as the first send
    hold = []
    for cid, roles in audiences.items():
        hold += roles.get("holdout", [])
    b1 = sorted((send for c, n, _, send in camps if c.get("group") == "B1"
                 and (n.get("status") or "") != "cancelled"))
    if hold and b1 and now_utc >= b1[0]:
        start = b1[0]
        upto = min(now_utc, start + datetime.timedelta(days=14))
        keys = {pk for pk, _ in hold if pk}
        booked = {b["pkey"] for b in bookings if b.get("pkey") in keys and b.get("made")
                  and start <= b["made"] < upto}
        holdout = {"group": "B1", "people": len(keys), "booked": len(booked),
                   "rate": _r(100.0 * len(booked) / len(keys), 1) if keys else 0.0,
                   "since_utc": start.isoformat()}

    nxt = sorted((r for r in out if r["status"] == "scheduled"), key=lambda r: r["send_utc"])
    nxt_at = nxt[0]["send_utc"] if nxt else None
    tot["cost"] = _r(tot["cost"], 2)
    tot["revenue"] = _r(tot["revenue"], 0)
    tot["baseline"] = _r(tot["baseline"], 1)
    tot["lift"] = _r(tot["bookings"] - tot["baseline"], 1)
    tot["roi"] = _r(tot["revenue"] / tot["cost"], 1) if tot["cost"] else None
    tot["cost_planned"] = _r(sum(r["cost_planned"] for r in out if r["status"] != "cancelled"), 2)
    tot["expected_sar"] = [_r(sum(r["expected"]["sar"][i] for r in out
                                  if r["status"] != "cancelled" and r["kind"] != "owner"), 0) for i in range(3)]
    return {"campaigns": out, "totals": tot, "holdout": holdout,
            "next": [r["id"] for r in nxt if r["send_utc"] == nxt_at],
            "groups": {k: {"name": v.get("name"), "kind": v.get("kind")} for k, v in groups.items()},
            "msg_cost_sar": cost_each, "now_utc": now_utc.replace(microsecond=0).isoformat()}


# ---------------------------------------------------------------- the I/O part
_bk_cache = {"key": None, "at": 0.0, "rows": []}
_bk_lock = threading.Lock()
BOOKINGS_TTL = 600


def _bookings(start_utc, now_utc):
    """Confirmed Hostaway reservations (targeted arrival windows — CLAUDE.md trap #4), shaped for
    compute(). Cached 10 minutes: the board is opened often, Hostaway's budget is shared."""
    key = start_utc.date().isoformat()
    with _bk_lock:
        if _bk_cache["key"] == key and time.time() - _bk_cache["at"] < BOOKINGS_TTL:
            return _bk_cache["rows"]
    fn = getattr(HOST, "reservations", None)
    rows = []
    if fn:
        try:
            rows = fn(start_utc.date(), now_utc.date()) or []
        except Exception:
            traceback.print_exc()
            return []
    from . import engine
    salt = db.salt()
    out = []
    for r in rows:
        if str(r.get("status") or "").lower() not in _CONFIRMED:
            continue
        out.append({"id": r.get("id"), "made": _parse_dt(r.get("reservationDate") or r.get("insertedOn")),
                    "pkey": engine.phone_key(r.get("phone") or r.get("guestPhone"), salt),
                    "total": r.get("totalPrice") or 0, "nights": r.get("nights") or 0})
    with _bk_lock:
        _bk_cache.update(key=key, at=time.time(), rows=out)
    return out


def board(now_utc=None):
    now_utc = now_utc or datetime.datetime.utcnow()
    seed = load_seed()
    numbers = db.board_numbers()
    audiences = db.audiences()
    sends = []
    for c in seed.get("campaigns") or []:
        n = numbers.get(c.get("id")) or {}
        if (n.get("status") or "") == "cancelled":
            continue
        try:
            sends.append(to_utc(n.get("send_at") or c["send_at"]))
        except Exception:
            continue
    started = [s for s in sends if s <= now_utc]
    bookings = _bookings(min(started), now_utc) if (started and audiences) else []
    res = compute(seed, numbers, audiences, db.taps_all(), bookings, now_utc)
    res["audiences"] = {cid: {k: len(v) for k, v in roles.items()} for cid, roles in audiences.items()}
    res["bookings_checked"] = len(bookings)
    return res


def load_audience(campaign, phones, role="sent", replace=False):
    """ADMIN upload: phone numbers in, salted keys stored, numbers dropped. → {"added", "bad"}."""
    from . import engine
    if role not in ("sent", "holdout"):
        raise ValueError("role")
    ids = {c.get("id") for c in load_seed().get("campaigns") or []}
    if campaign not in ids and not (role == "holdout" and campaign == "B1-holdout"):
        raise ValueError("unknown campaign")
    salt = db.salt()
    keys, bad = [], 0
    for p in phones or []:
        k = engine.phone_key(p, salt)
        if k:
            keys.append((k, ""))
        else:
            bad += 1
    if replace:
        db.audience_clear(campaign)
    return {"added": db.audience_add(campaign, keys, role), "bad": bad}


def set_numbers(campaign, fields, who=""):
    ids = {c.get("id") for c in load_seed().get("campaigns") or []}
    if campaign not in ids:
        raise ValueError("unknown campaign")
    clean = {}
    for k in ("sent", "delivered", "read_n", "replied", "signed"):
        if k in fields:
            v = fields[k]
            clean[k] = None if v in (None, "") else max(0, int(v))
    if "send_at" in fields:
        v = str(fields["send_at"] or "").strip()
        if v:
            to_utc(v)                                 # raises on a bad date
        clean["send_at"] = v or None
    if "status" in fields:
        v = str(fields["status"] or "").strip()
        if v not in ("", "cancelled"):
            raise ValueError("status")
        clean["status"] = v or None
    if "note" in fields:
        clean["note"] = str(fields["note"] or "")[:200] or None
    db.set_board_numbers(campaign, clean, who)
    return True
