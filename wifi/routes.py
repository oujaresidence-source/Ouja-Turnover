# -*- coding: utf-8 -*-
"""
wifi.routes — /api/wifi/* for «اشتراكات النت».

Every endpoint is a thin aiohttp wrapper around a `core_*` function that takes plain
dicts and an explicit `today`. The rules therefore live somewhere tests can reach
without a web server, and tests/test_wifi_lock.py drives those cores directly.

TWO DOORS, DELIBERATELY DIFFERENT
  • the dashboard door  — login + the `wifi` permission. Full power: log, renew, record
    an observation, mark dead, set assignee/billing.
  • the public door     — /api/wifi/fill + /api/wifi/fill-save, NO login and NO token,
    exactly like the /team-calendar share link. It may only ADD a remembered
    subscription for a unit that has none. It cannot close, edit, renew or delete
    anything — see core_fill_save and the test that reads its source to prove it.
"""

import datetime
import traceback

from . import db, engine, page
from .host import HOST

PROVIDERS = ("stc", "mobily", "zain", "salam", "other")
PROVIDER_AR = {"stc": "STC", "mobily": "موبايلي", "zain": "زين",
               "salam": "سلام", "other": "شركة ثانية"}
SOURCE_KINDS = ("first_party", "vendor")
PAY_METHODS = ("cash", "transfer", "float", "card")
LABEL_DAYS = (30, 60, 90)
CHECK_KINDS = engine.VALID_CHECK_KINDS
BILLED_TO = ("ouja", "owner", "")

_MONTH_AR = ["", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]

# Fields a later correction may touch. override_reason / override_by / is_backfill /
# created_by are NOT here on purpose: the stamp is permanent and cannot be laundered.
EDITABLE = ("provider", "source_kind", "source_name", "label_days", "amount_sar",
            "tax_invoice", "purchase_date", "activation_date", "stated_end",
            "paid_by", "pay_method", "apartment_name")


# ---------------- small helpers ----------------

def _today():
    try:
        return HOST.now().date().isoformat()
    except Exception:
        return datetime.date.today().isoformat()


def _date_or_none(v):
    """'' / None / rubbish all mean «ما أعرف». A wrong guess is worse than a blank, so
    nothing here ever substitutes today's date for a missing one."""
    s = str(v or "").strip()[:10]
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s).isoformat()
    except ValueError:
        return None


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _money(v):
    n = _num(v)
    return str(int(n)) if abs(n - int(n)) < 0.005 else ("%.2f" % n)


def _ar_date(iso):
    d = engine._d(iso)
    if not d:
        return "تاريخ غير معروف"
    return "%d %s" % (d.day, _MONTH_AR[d.month])


def _clean(payload):
    """One shape for a subscription, whichever door it came through."""
    return {
        "listing_id": int(payload.get("listing_id")),
        "apartment_name": str(payload.get("apartment_name") or "")[:120] or None,
        "provider": (str(payload.get("provider") or "other").strip().lower()
                     if str(payload.get("provider") or "").strip().lower() in PROVIDERS
                     else "other"),
        "source_kind": ("vendor" if str(payload.get("source_kind") or "").strip().lower()
                        == "vendor" else "first_party"),
        "source_name": str(payload.get("source_name") or "").strip()[:120] or None,
        "label_days": (int(payload.get("label_days"))
                       if str(payload.get("label_days") or "").strip().isdigit() else 30),
        "amount_sar": _num(payload.get("amount_sar")),
        "tax_invoice": 1 if payload.get("tax_invoice") else 0,
        "purchase_date": _date_or_none(payload.get("purchase_date")),
        "activation_date": _date_or_none(payload.get("activation_date")),
        "stated_end": _date_or_none(payload.get("stated_end")),
        "paid_by": str(payload.get("paid_by") or "").strip()[:80] or None,
        "pay_method": (str(payload.get("pay_method") or "").strip().lower()
                       if str(payload.get("pay_method") or "").strip().lower() in PAY_METHODS
                       else None),
        "status": "active",
    }


def _describe(sub, learned_map, today):
    if not sub:
        return None
    d = engine.describe(sub, learned_map.get(engine.learning_key(sub)), today)
    out = dict(sub)
    out.update(d)
    return out


def _block_message(existing):
    """The refusal has to say WHAT is running, HOW LONG is left, WHO logged it and for
    HOW MUCH — otherwise the person just overrides it blind."""
    prov = PROVIDER_AR.get(existing.get("provider") or "", "اشتراك")
    left = existing.get("days_left")
    who = existing.get("created_by") or existing.get("paid_by") or "أحد الفريق"
    when = _ar_date(existing.get("activation_date") or existing.get("purchase_date"))
    amount = _money(existing.get("amount_sar"))
    left_txt = ("باقي له %d يوم" % left) if left is not None else "وما نعرف متى ينتهي"
    return ("هذي الشقة عندها اشتراك %s شغّال، %s. %s سجّله في %s بـ %s ر.س."
            % (prov, left_txt, who, when, amount))


# ---------------- the cores (testable without a web server) ----------------

def core_log(payload, actor=None, today=None, is_backfill=0):
    """Create a subscription. THIS IS WHERE THE LOCK RUNS.

    1. no active sub                  -> insert                       (200, kind 'free')
    2. active sub, days_left > grace  -> refuse                       (409, needs reason)
    3. active sub, days_left <= grace -> renewal, no reason needed    (200, kind 'renewal')
       (an UNDATED active sub counts here too: we do not know it is alive, so we do not
        stand in the way of a real order)
    4. a non-blank override_reason    -> allowed, old row closed, reason stamped
                                         PERMANENTLY on the new one  (200, kind 'override')
    """
    today = today or _today()
    try:
        data = _clean(payload)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "listing_id مطلوب"}
    if data["activation_date"] is None:
        data["activation_date"] = data["purchase_date"]
    data["created_by"] = str(actor or "")[:80] or None
    data["is_backfill"] = 1 if is_backfill else 0

    reason = str(payload.get("override_reason") or "").strip()
    existing = _describe(db.active_sub(data["listing_id"]), db.learned_map(), today)
    allowed, kind = engine.lock_decision(existing, reason)
    if not allowed:
        return 409, {"ok": False, "blocked": True, "needs": "override_reason",
                     "message_ar": _block_message(existing),
                     "existing": existing}

    if kind == "override":
        data["override_reason"] = reason[:400]
        data["override_by"] = str(actor or "")[:80] or None

    if existing:
        new_id, closed_id = db.renew(data["listing_id"], data)
        return 200, {"ok": True, "kind": kind, "id": new_id, "closed_id": closed_id}
    return 200, {"ok": True, "kind": "free", "id": db.create_sub(data), "closed_id": None}


def core_edit(sub_id, patch, actor=None):
    """Fix a typo on an existing row. The override stamp is NOT editable — a mistake in
    a date is a mistake; the record that somebody overrode the lock is a decision."""
    row = db.sub(sub_id)
    if not row:
        return 404, {"ok": False, "error": "الاشتراك غير موجود"}
    fields = {}
    for k in EDITABLE:
        if k not in patch:
            continue
        v = patch[k]
        if k in ("purchase_date", "activation_date", "stated_end"):
            v = _date_or_none(v)
        elif k == "label_days":
            v = int(v) if str(v or "").strip().isdigit() else row.get("label_days")
        elif k == "amount_sar":
            v = _num(v)
        elif k == "tax_invoice":
            v = 1 if v else 0
        fields[k] = v
    if fields:
        db.update_sub(sub_id, **fields)
    return 200, {"ok": True, "id": int(sub_id), "changed": sorted(fields.keys()),
                 "actor": str(actor or "")}


def core_check(sub_id, payload, actor=None, today=None):
    """Record ONE observation. This is the only thing that ever teaches the system that a
    seller short-changes us."""
    today = today or _today()
    row = db.sub(sub_id)
    if not row:
        return 404, {"ok": False, "error": "الاشتراك غير موجود"}
    kind = str(payload.get("kind") or "").strip()
    if kind not in CHECK_KINDS:
        return 400, {"ok": False, "error": "نوع التحقق غير معروف"}
    observed = _date_or_none(payload.get("observed_on")) or today
    left = payload.get("days_left")
    left = int(left) if str(left or "").strip().lstrip("-").isdigit() else None
    end = _date_or_none(payload.get("end_date"))
    if kind in ("exact_expiry", "died") and not end:
        return 400, {"ok": False, "error": "لازم تكتب التاريخ"}
    if kind == "days_left" and left is None:
        return 400, {"ok": False, "error": "لازم تكتب كم يوم باقي"}

    cid = db.add_check(sub_id, kind, observed_on=observed, days_left=left, end_date=end,
                       note=str(payload.get("note") or "")[:400] or None, actor=actor)
    # An exact expiry read off the telco app is a near-fact: it beats our estimate from
    # now on. A death is a fact and also closes the subscription.
    if kind == "exact_expiry":
        db.update_sub(sub_id, stated_end=end)
    elif kind == "died":
        db.close_sub(sub_id, status="dead", real_end=end)
    return 200, {"ok": True, "check_id": cid,
                 "real_days": engine.real_days(db.sub(sub_id), db.checks_for(sub_id)[-1])}


def core_dead(sub_id, payload, actor=None, today=None):
    """Mark a subscription dead AND write the observation in one go — the death date is
    the single most valuable thing we learn about a seller."""
    today = today or _today()
    end = _date_or_none((payload or {}).get("end_date")) or today
    return core_check(sub_id, {"kind": "died", "end_date": end, "observed_on": today,
                               "note": (payload or {}).get("note")}, actor=actor, today=today)


def core_fill_save(payload, who=None, today=None):
    """THE PUBLIC DOOR. Adds a remembered subscription for a unit that has none.

    Deliberately narrow: it can only INSERT, it always stamps is_backfill=1, and a unit
    that already has an active subscription is reported back as already-known instead of
    being touched. There is no code path from here to closing, editing or deleting a row.
    """
    today = today or _today()
    try:
        lid = int(payload.get("listing_id"))
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "الشقة غير معروفة"}
    if db.active_sub(lid):
        return 200, {"ok": True, "kind": "exists",
                     "message_ar": "هذي الشقة مسجّل لها اشتراك — ما غيّرنا شي"}
    data = _clean(payload)
    if data["activation_date"] is None:
        data["activation_date"] = data["purchase_date"]
    data["created_by"] = str(who or "")[:80] or None
    data["is_backfill"] = 1
    return 200, {"ok": True, "kind": "added", "id": db.create_sub(data)}


# ---------------- read models ----------------

def _unit_master():
    """Every apartment we could possibly owe internet for, with its permanent owner.

    Hostaway is the master list (a unit that exists is a unit that needs internet); the
    Employee Calendar supplies who is responsible, via schedule.owners — one resolver,
    one answer, no second copy of the assignment here.
    """
    try:
        listings = HOST.listings() or {}
    except Exception:
        listings = {}
    owners = {}
    try:
        pm = HOST.permanent_map() if HOST.permanent_map else None
        for a in (pm or {}).get("apartments", []):
            if a.get("listing_id") is not None and a.get("owner_name"):
                owners[str(a["listing_id"])] = a["owner_name"]
    except Exception:
        pass

    stored = {str(u["listing_id"]): u for u in db.units()}
    out, seen = [], set()

    def _add(lid, name, inactive=False):
        key = str(lid)
        if key in seen:
            return
        seen.add(key)
        rec = stored.get(key) or {}
        row = {"listing_id": int(lid),
               "apartment_name": rec.get("apartment_name") or name or ("#" + key),
               "assignee": rec.get("assignee") or owners.get(key) or "",
               "billed_to": rec.get("billed_to") or "",
               "notes": rec.get("notes") or ""}
        if inactive:
            row["inactive"] = True
        out.append(row)

    for lid, name in listings.items():
        _add(lid, name)
    # A unit Hostaway no longer returns — deactivated, renamed, or synced later — must
    # still appear if we ever bought internet for it or set anything on it. Money is
    # attached to those rows; dropping them would hide a live subscription.
    for row in db.listing_ids_with_subs():
        _add(row["listing_id"], row.get("apartment_name"), inactive=True)
    for lid, rec in stored.items():
        _add(lid, rec.get("apartment_name"), inactive=True)
    return out


def _employees():
    """The team, straight from the Employee Calendar — id, name, emoji, colour.

    The emoji and colour are what make each person's fill page feel like THEIRS, and
    they already exist in schedule_employees. No second copy lives here: rename someone
    or change their colour in تقويم الموظفين and their link follows.
    """
    try:
        pm = HOST.permanent_map() if HOST.permanent_map else None
    except Exception:
        pm = None
    out = []
    for e in (pm or {}).get("employees", []):
        if not e.get("name"):
            continue
        out.append({"id": e.get("id"), "name": e["name"], "emoji": e.get("emoji") or "",
                    "color": e.get("color") or "", "sort_order": e.get("sort_order", 0)})
    return out


def _employee_by_id(eid):
    try:
        want = int(eid)
    except (TypeError, ValueError):
        return None
    for e in _employees():
        if e.get("id") == want:
            return e
    return None


def _sort_key(row):
    """Days left ascending — the thing about to die is row one. Never alphabetical.
    Unknowns go last: they are unmeasured, not urgent."""
    left = row.get("days_left")
    return (1 if left is None else 0, left if left is not None else 0,
            row.get("apartment_name") or "")


def core_list(today=None):
    today = today or _today()
    learned = db.learned_map()
    rows = []
    counters = {"dead": 0, "urgent": 0, "soon": 0, "ok": 0, "unknown": 0}
    for u in _unit_master():
        sub = _describe(db.active_sub(u["listing_id"]), learned, today)
        row = dict(u)
        row["sub"] = sub
        row["band"] = sub["band"] if sub else "unknown"
        row["days_left"] = sub["days_left"] if sub else None
        row["confidence"] = sub["confidence"] if sub else None
        row["end_date"] = sub["end_date"] if sub else None
        counters[row["band"]] = counters.get(row["band"], 0) + 1
        rows.append(row)
    rows.sort(key=_sort_key)
    # No spend total here on purpose: what internet actually costs is the accountant's
    # view, and that is Phase 3. This page answers "what is about to die", nothing else.
    return 200, {"ok": True, "today": today, "units": rows, "counters": counters,
                 "learned": [{"provider": k[0], "source_kind": k[1], "source_name": k[2],
                              "label_days": k[3], "learned_days": v,
                              "observations": db.observations_for_key(k)}
                             for k, v in sorted(learned.items())],
                 "providers": list(PROVIDERS), "provider_ar": PROVIDER_AR,
                 "pay_methods": list(PAY_METHODS), "label_days": list(LABEL_DAYS)}


def core_unit(listing_id, today=None):
    today = today or _today()
    learned = db.learned_map()
    lid = int(listing_id)
    master = {u["listing_id"]: u for u in _unit_master()}
    u = master.get(lid) or {"listing_id": lid, "apartment_name": "#" + str(lid),
                            "assignee": "", "billed_to": "", "notes": ""}
    history = []
    for s in db.subs_for(lid):
        d = _describe(s, learned, today)
        d["checks"] = db.checks_for(s["id"])
        history.append(d)
    return 200, {"ok": True, "today": today, "unit": u, "history": history,
                 "providers": list(PROVIDERS), "provider_ar": PROVIDER_AR,
                 "pay_methods": list(PAY_METHODS), "label_days": list(LABEL_DAYS)}


def core_fill(who=None, today=None, eid=None):
    """The backfill page's data: one employee's apartments and what we already know.

    Accepts either the short ?e=<employee id> link (what we send on WhatsApp — an Arabic
    name in a URL percent-encodes into something nobody trusts) or the older ?who=<name>
    form, which keeps working so links already sent do not die.

    An unknown id shows the name picker rather than somebody else's apartments: better to
    ask who you are than to hand you the wrong list.

    An apartment with nobody assigned is NOT hidden — it goes in a «بدون مسؤول» bucket,
    because an unassigned unit is exactly the one that gets forgotten.
    """
    today = today or _today()
    learned = db.learned_map()
    me = _employee_by_id(eid) if eid not in (None, "") else None
    who = me["name"] if me else str(who or "").strip()
    if me is None and who:
        for e in _employees():
            if e["name"] == who:
                me = e
                break
    people, rows = [], []
    for u in _unit_master():
        sub = _describe(db.active_sub(u["listing_id"]), learned, today)
        name = u.get("assignee") or ""
        if name and name not in people:
            people.append(name)
        if who and name != who:
            continue
        rows.append({"listing_id": u["listing_id"], "apartment_name": u["apartment_name"],
                     "assignee": name, "known": bool(sub),
                     "provider": (sub or {}).get("provider"),
                     "end_date": (sub or {}).get("end_date"),
                     "band": (sub or {}).get("band") or "unknown"})
    rows.sort(key=lambda r: (r["known"], r["apartment_name"] or ""))
    done = len([r for r in rows if r["known"]])
    for e in _employees():                       # everyone gets offered in the picker,
        if e["name"] not in people:              # including someone with nothing assigned
            people.append(e["name"])
    return 200, {"ok": True, "today": today, "who": who, "people": sorted(people),
                 "me": ({"id": me["id"], "name": me["name"], "emoji": me["emoji"],
                         "color": me["color"]} if me else None),
                 "units": rows, "done": done, "total": len(rows),
                 "remaining": len(rows) - done,
                 "providers": list(PROVIDERS), "provider_ar": PROVIDER_AR,
                 "label_days": list(LABEL_DAYS)}


def core_progress(today=None):
    """The owner's follow-up view: who has filled how many, furthest behind FIRST.

    «خلص» counts apartments that have a subscription recorded — including one saved with
    «ما أعرف» and no date. That row IS an answer: the employee looked and told us what
    they knew. Counting it as unanswered would push people to invent a date, which is
    the exact thing that button exists to prevent.
    """
    today = today or _today()
    active = {int(s["listing_id"]) for s in db.active_subs()}
    last_by = {}
    for r in db.q("SELECT created_by, MAX(created_at) AS t FROM wifi_subs "
                  "WHERE created_by IS NOT NULL AND created_by != '' GROUP BY created_by"):
        last_by[r["created_by"]] = r["t"]

    emps = {e["name"]: e for e in _employees()}
    buckets = {}
    for u in _unit_master():
        name = u.get("assignee") or ""
        b = buckets.setdefault(name, {"name": name, "total": 0, "done": 0})
        b["total"] += 1
        if u["listing_id"] in active:
            b["done"] += 1
    for name in emps:                    # an employee with nothing assigned still gets a row
        buckets.setdefault(name, {"name": name, "total": 0, "done": 0})

    rows = []
    for b in buckets.values():
        e = emps.get(b["name"]) or {}
        total, done = b["total"], b["done"]
        t = last_by.get(b["name"])
        rows.append({
            "id": e.get("id"), "name": b["name"], "emoji": e.get("emoji") or "",
            "color": e.get("color") or "", "total": total, "done": done,
            "remaining": total - done,
            "pct": int(done * 100 / total) if total else 100,
            "finished": total > 0 and done >= total,
            # The Z matters: a bare timestamp is read as LOCAL time by the browser and
            # lands three hours off in Riyadh, so «قبل ساعتين» would be a lie.
            "last_fill": (t + "Z") if t else None,
            "link": ("/wifi-fill?e=%d" % e["id"]) if e.get("id") is not None else None,
        })
    # Furthest behind, first — the row that needs you is row one. A finished person sinks
    # to the bottom; the unassigned bucket sorts on its own numbers like anyone else.
    rows.sort(key=lambda r: (r["pct"], -r["remaining"], r["name"] or "￿"))
    return 200, {"ok": True, "today": today, "rows": rows,
                 "done": sum(r["done"] for r in rows),
                 "total": sum(r["total"] for r in rows)}


# ---------------- aiohttp wrappers ----------------

def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def _actor(request):
    try:
        return HOST.actor(request) if HOST.actor else ""
    except Exception:
        return ""


def _safe(fn):
    """Login-required wrapper (dashboard door)."""
    async def _w(request):
        g = _guard(request)
        if g:
            return g
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _safe_public(fn):
    """PUBLIC wrapper — NO auth. Used ONLY by the /wifi-fill share link, exactly as
    /team-calendar does for the schedule day/week reads."""
    async def _w(request):
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


def _reply(pair):
    status, body = pair
    return HOST.json_response(body, status)


async def api_list(request):
    return _reply(core_list())


async def api_unit(request):
    return _reply(core_unit(request.match_info.get("listing_id")))


async def api_log(request):
    return _reply(core_log(await _body(request), actor=_actor(request)))


async def api_renew(request):
    """Renew is core_log with the same lock — a renewal IS a new subscription; the only
    difference is that the old row is closed in the same transaction, which core_log
    already does whenever one exists."""
    return _reply(core_log(await _body(request), actor=_actor(request)))


async def api_check(request):
    b = await _body(request)
    return _reply(core_check(b.get("sub_id"), b, actor=_actor(request)))


async def api_dead(request):
    b = await _body(request)
    return _reply(core_dead(b.get("sub_id"), b, actor=_actor(request)))


async def api_edit(request):
    b = await _body(request)
    return _reply(core_edit(b.get("sub_id"), b, actor=_actor(request)))


async def api_unit_settings(request):
    b = await _body(request)
    try:
        lid = int(b.get("listing_id"))
    except (TypeError, ValueError):
        return HOST.json_response({"ok": False, "error": "الشقة غير معروفة"}, 400)
    billed = str(b.get("billed_to") or "").strip().lower()
    fields = {"billed_to": billed if billed in BILLED_TO else ""}
    for k in ("assignee", "notes", "apartment_name"):
        if k in b:
            fields[k] = str(b.get(k) or "")[:200]
    return HOST.json_response({"ok": True,
                               "unit": db.upsert_unit(lid, actor=_actor(request), **fields)})


async def api_fill(request):
    q = request.rel_url.query
    return _reply(core_fill(who=q.get("who"), eid=q.get("e")))


async def api_progress(request):
    return _reply(core_progress())


async def api_fill_save(request):
    b = await _body(request)
    return _reply(core_fill_save(b, who=b.get("who")))


async def handle_page(request):
    return HOST.web.Response(text=page.HTML, content_type="text/html")


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    # PUBLIC — the shared /wifi-fill link opens with no login and no token.
    g("/api/wifi/fill", _safe_public(api_fill))
    p("/api/wifi/fill-save", _safe_public(api_fill_save))
    g("/wifi-fill", handle_page)
    # Dashboard door — login + the `wifi` permission (enforced in bot.py's middleware).
    g("/api/wifi/list", _safe(api_list))
    g("/api/wifi/progress", _safe(api_progress))
    g("/api/wifi/unit/{listing_id}", _safe(api_unit))
    p("/api/wifi/log", _safe(api_log))
    p("/api/wifi/renew", _safe(api_renew))
    p("/api/wifi/check", _safe(api_check))
    p("/api/wifi/dead", _safe(api_dead))
    p("/api/wifi/edit", _safe(api_edit))
    p("/api/wifi/unit-settings", _safe(api_unit_settings))
