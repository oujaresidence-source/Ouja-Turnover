# -*- coding: utf-8 -*-
"""
targets.book — «دفتر العملاء»: who may be called, who is hidden, and the logged contact.

THREE THINGS THIS FILE GUARANTEES
  1. THE HOLDOUT IS INVISIBLE. `call_list` is the only way a guest reaches an employee, and it
     drops holdout guests before anything is ranked. A guest is addressed by an opaque token;
     `log_contact` resolves a token only against that employee's own current list, so a holdout
     guest (or any guest outside the list) can never be contacted through this package.
  2. CONSENT GATES THE POOL. Default pool = direct-booking guests + guests who ticked the
     consent box. An Airbnb guest without consent is not callable. «لا تتصل» is permanent.
  3. A CONTACT IS LOGGED, NOT TYPED. `log_contact` takes no date and no phone: the time is
     the server clock and the guest comes from the list.
"""

import datetime as dt
import hashlib
import hmac
import secrets

from . import db, engine, history, score
from . import host as _host
from .host import HOST

HORIZON_DAYS = 14
OUTCOMES = ("booked", "interested", "declined", "dnc")
_cache = {"v": None, "guests": {}}


# ------------------------------------------------------------------ secrets / tokens

def _secret():
    s = db.setting("holdout_secret")
    if not s:
        s = secrets.token_hex(16)
        db.set_setting("holdout_secret", s, "system", "")
        s = db.setting("holdout_secret")      # two racers converge on whichever landed
    return s


def is_holdout(phone_key, quarter):
    """Stable for the whole quarter and unguessable without the server's secret."""
    return engine.in_holdout(phone_key, _secret() + ":" + str(quarter))


def token(phone_key):
    return hmac.new(_secret().encode("utf-8"), phone_key.encode("utf-8"), hashlib.sha256).hexdigest()[:20]


# ------------------------------------------------------------------ the guest book

def is_guest_row(r):
    return bool(r.get("phone_key")) and "CLOSED" not in (r.get("guest_name") or "").upper()


def guests():
    """{phone_key: guest} built from the stored history. Cached until the next write."""
    v = db.version()
    if _cache["v"] == v:
        return _cache["guests"]
    out = {}
    for r in db.q("SELECT res_id, unit, listing_name, phone_key, phone, guest_name, channel, "
                  "status, arrival, departure, created FROM tg_res "
                  "WHERE phone_key<>'' AND status IN ('new','modified')"):
        if not is_guest_row(r):
            continue
        g = out.setdefault(r["phone_key"], {"key": r["phone_key"], "phone": "", "name": "",
                                            "stays": [], "channels": set(), "_latest": ""})
        g["stays"].append(r)
        g["channels"].add(r["channel"])
        if r["arrival"] >= g["_latest"]:
            g["_latest"] = r["arrival"]
            g["phone"] = r["phone"] or g["phone"]
            g["name"] = r["guest_name"] or g["name"]
    _cache.update(v=v, guests=out)
    return out


def first_name(name):
    parts = str(name or "").split()
    return parts[0] if parts else "ضيفنا"


def past_stays(g, on_iso):
    """Stays that had ended, and were already booked, before `on_iso`."""
    return [s for s in g["stays"] if s["departure"] < on_iso and s["created"] < on_iso]


def bucket_of(n_past):
    return min(max(int(n_past), 1), 3)


def consent_ok(g, consents, channels):
    if "all" in channels:
        return True
    if "direct" in channels and "direct" in g["channels"]:
        return True
    return "consented" in channels and g["key"] in consents


def as_callable(g, on, consents, dnc, last_contacts, channels):
    """(ok, reason, past) for one guest on one date — the engine's rule, fed from storage."""
    on_iso = on.isoformat()
    past = past_stays(g, on_iso)
    guest = {"phone": g["key"],
             "last_checkout": max((s["departure"] for s in past), default=None),
             "has_future_booking": any(s["created"] <= on_iso and s["departure"] >= on_iso
                                       for s in g["stays"]),
             "do_not_contact": g["key"] in dnc,
             "consent": consent_ok(g, consents, channels),
             "last_contact": (last_contacts.get(g["key"]) or "")[:10] or None}
    ok, why = engine.callable_guest(guest, on)
    return ok, why, past


def pool(today):
    """Every guest an employee may be shown today: callable AND not in the holdout."""
    quarter = score.quarter_of(today)
    consents, dnc, last = db.consents(), db.dnc(), db.last_contacts()
    channels = _host.pool_channels()
    out = []
    for g in guests().values():
        ok, _why, past = as_callable(g, today, consents, dnc, last, channels)
        if ok and not is_holdout(g["key"], quarter):
            out.append((g, past))
    return out


# ------------------------------------------------------------------ the call list

def _months_ago(iso, today):
    d = dt.date.fromisoformat(iso)
    return max(0, (today.year - d.year) * 12 + today.month - d.month)


def _ago_text(n):
    if n <= 0:
        return "هالشهر"
    if n == 1:
        return "قبل شهر"
    if n == 2:
        return "قبل شهرين"
    if n <= 10:
        return "قبل %d شهور" % n
    return "قبل %d شهر" % n


def _open_nights(employee, today):
    """{unit: [empty dates]} for the employee's units over the next HORIZON_DAYS."""
    end = today + dt.timedelta(days=HORIZON_DAYS)
    out = {}
    for u in score.owned_units():
        if u["employee"] != employee:
            continue
        nights = score.empty_nights(u["unit"], today, end)
        if nights:
            out[u["unit"]] = {"name": u["name"], "nights": nights,
                              "compound": _compound(u["unit"])}
    return out


_compound_memo = {}


def _compound(unit):
    """Compound of a unit, remembered for the life of the process (it does not change)."""
    if unit.startswith("n:"):
        return ""
    if unit not in _compound_memo:
        _compound_memo[unit] = (HOST.call("unit_meta", {}, unit) or {}).get("compound") or ""
    return _compound_memo[unit]


def _rank(g, past, open_units, today, vip):
    """(score, reason, unit, night) or None when nothing ties this guest to an empty night."""
    best = None
    stayed = {}
    for s in past:
        stayed[s["unit"]] = max(stayed.get(s["unit"], ""), s["departure"])
    compounds = {}
    if any(o["compound"] for o in open_units.values()):
        for s in past:
            c = _compound(s["unit"])
            if c:
                compounds[c] = max(compounds.get(c, ""), s["departure"])
    for unit, o in open_units.items():
        pts, why = 0, ""
        if unit in stayed:
            pts, why = 100, "سكن عندك في %s %s" % (o["name"], _ago_text(_months_ago(stayed[unit], today)))
        elif o["compound"] and o["compound"] in compounds:
            pts, why = 60, "سكن بنفس المجمع %s" % _ago_text(_months_ago(compounds[o["compound"]], today))
        night = o["nights"][0]
        nd = dt.date.fromisoformat(night)
        for s in past:
            a = dt.date.fromisoformat(s["arrival"])
            if a.month == nd.month and a.year < nd.year:
                pts += 20
                why = why or "جا بنفس هالشهر السنة الماضية"
                break
            if abs(a.day - nd.day) <= 4:
                pts += 20
                why = why or "يجي غالباً بهالوقت من الشهر"
                break
        if pts and (best is None or pts > best[0]):
            best = (pts, why, unit, night)
    if g["key"] in vip:
        if best is None and open_units:
            unit = sorted(open_units)[0]
            best = (10, "ضيف مميز (VIP)", unit, open_units[unit]["nights"][0])
        elif best is not None:
            best = (best[0] + 10, best[1] + " · VIP", best[2], best[3])
    if best is None:
        return None
    return (best[0] + min(len(past), 5), best[1], best[2], best[3])


def call_list(employee, today, limit=40):
    """The employee's ranked list for today. Items carry a token, never a phone number."""
    open_units = _open_nights(employee, today) if employee else {}
    if not open_units:
        return {"open_units": 0, "open_nights": 0, "items": []}
    vip = set(HOST.call("vip_keys", set()) or ())
    items = []
    for g, past in pool(today):
        r = _rank(g, past, open_units, today, vip)
        if r is None:
            continue
        pts, why, unit, night = r
        items.append({"g": token(g["key"]), "name": first_name(g["name"]), "reason": why,
                      "unit": unit, "unit_name": open_units[unit]["name"], "night": night,
                      "stays": len(past), "score": pts, "_key": g["key"]})
    items.sort(key=lambda x: (-x["score"], x["name"]))
    return {"open_units": len(open_units),
            "open_nights": sum(len(o["nights"]) for o in open_units.values()),
            "items": items[:limit] if limit else items}


def public_items(lst):
    """Strip the internal key before anything leaves the server."""
    return dict(lst, items=[{k: v for k, v in it.items() if not k.startswith("_")}
                            for it in lst["items"]])


# ------------------------------------------------------------------ the logged contact

def message_for(employee, guest_name, night):
    d = dt.date.fromisoformat(night)
    return ("هلا %s 👋 معك %s من عوجا ريزيدنس.\n"
            "عندنا شقة فاضية يوم %d/%d وحبيت أبلغك قبل الكل.\n"
            "تبي أحجزها لك؟" % (first_name(guest_name), employee, d.day, d.month))


def log_contact(employee, guest_token):
    """Press of the WhatsApp button. Returns (ok, error, {phone, text, contact_id}).
    No date and no phone come from the caller: the clock is the server's, the guest is
    whoever that token means inside THIS employee's list right now."""
    if not employee:
        return False, "حسابك مو مربوط بموظف", None
    now = HOST.require("now")()
    today = now.date()
    hit = next((it for it in call_list(employee, today, limit=0)["items"]
                if hmac.compare_digest(it["g"], str(guest_token or ""))), None)
    if hit is None:
        return False, "الضيف مو في قائمتك اليوم", None
    g = guests().get(hit["_key"])
    if not g or not g.get("phone"):
        return False, "ما فيه رقم لهالضيف", None
    since = (today - dt.timedelta(days=engine.CONTACT_COOLDOWN_DAYS - 1)).isoformat()
    cid = db.insert_contact(g["key"], g["name"], employee, now.isoformat(timespec="seconds"),
                            score.quarter_of(today), hit["unit"], hit["night"],
                            bucket_of(hit["stays"]), since)
    if cid is None:
        return False, "انتصل على هالضيف قبل، ينتظر 45 يوم", None
    return True, "", {"phone": g["phone"], "contact_id": cid,
                      "text": message_for(employee, g["name"], hit["night"])}


def set_outcome(employee, contact_id, outcome):
    if outcome not in OUTCOMES:
        return False, "نتيجة غير معروفة"
    c = db.contact(contact_id)
    if not c or c["employee"] != employee:
        return False, "هالاتصال مو لك"
    now = HOST.require("now")().isoformat(timespec="seconds")
    db.set_outcome(contact_id, employee, outcome, now)
    if outcome == "dnc":
        db.add_dnc(c["phone_key"], employee, now)       # permanent and immediate
    return True, ""


def open_contacts(employee, today):
    """My contacts whose 14-day window is still running, or that have no outcome yet."""
    since = (today - dt.timedelta(days=60)).isoformat()
    booked = {a["contact_id"] for a in db.attrs()}
    out = []
    for c in db.contacts(employee=employee, since=since):
        gap = (today - dt.date.fromisoformat(c["at"][:10])).days
        left = engine.ATTRIBUTION_DAYS - gap
        if left < 0 and c["outcome"]:
            continue
        out.append({"id": c["id"], "name": first_name(c["guest_name"]), "at": c["at"][:10],
                    "days_left": max(0, left), "outcome": c["outcome"] or "",
                    "booked": c["id"] in booked})
    out.sort(key=lambda x: (x["outcome"] != "", -x["days_left"]))
    return out


# ------------------------------------------------------------------ consent (public guide box)

def record_consent(phone, slug):
    """A guest ticks the box on the guide page. Stored only when the number belongs to someone
    who has actually booked with Ouja — a stranger's number is silently ignored. The caller
    always answers the same thing, so the form cannot be used to test who is a guest."""
    key = engine.phone_key(phone)
    if not key or key not in guests():
        return False
    db.add_consent(key, "guide", str(slug or "")[:80], HOST.require("now")().isoformat(timespec="seconds"))
    return True


# ------------------------------------------------------------------ attribution

def run_attribution():
    """Match every confirmed booking to the logged contact that earned it (engine rule:
    created within 14 days of the contact, same phone, the earliest logger wins)."""
    contacts = [{"id": c["id"], "employee": c["employee"], "phone": c["phone_key"], "at": c["at"][:10]}
                for c in db.contacts()]
    if not contacts:
        db.replace_attr([], "")
        return 0
    phones = {c["phone"] for c in contacts}
    bookings = [{"id": r["res_id"], "phone": r["phone_key"], "created": r["created"]}
                for r in db.q("SELECT res_id, phone_key, created, guest_name FROM tg_res "
                              "WHERE status IN ('new','modified') AND phone_key<>''")
                if r["phone_key"] in phones and is_guest_row(r) and r["created"]]
    got = engine.attribute(contacts, bookings)
    now = HOST.require("now")().isoformat(timespec="seconds")
    db.replace_attr([(rid, c["id"], c["employee"]) for rid, c in got.items()], now)
    return len(got)


def nightly(today=None):
    today = today or HOST.require("now")().date()
    rep = history.nightly(today)
    rep["attributed"] = run_attribution()
    rep["rescue_snapshot"] = score.snapshot_rescue(today)
    return rep
