# -*- coding: utf-8 -*-
"""
stayhub.engine — PURE rules. No I/O, no clock reads, no HOST. Everything here is unit-tested.

    normalize_phone     guest mobile → full international digits (9665XXXXXXXX)
    reservation_view    a Hostaway reservation → the fields we push (no side effects)
    eligibility         should this reservation be in StayHub at all?
    plan                what to do for one reservation given its ledger row: create / modify
                        dates / modify amount / cancel / nothing
    snapshot_from_probe the partnerSnapshot built ONLY from StayHub's own probe answer
    action_for_error    the per-code playbook from the integration guide (certification)
    verify_signature    HMAC-SHA256 check for StayHub's webhooks and sync probe
"""
import datetime
import hashlib
import hmac
import re

# ---- booking-row statuses ----
PENDING = "pending"          # waiting for its first push (or for a free slot this tick)
HELD = "held"                # hold placed, confirm not yet accepted
CONFIRMED = "confirmed"      # StayHub has it (sh_reservation_id set)
RETRY = "retry"              # a transient failure — retried after next_try_at
REJECTED = "rejected"        # StayHub refused it (dates not free there) — retried slowly, reported daily
CANCELLED = "cancelled"      # cancelled in StayHub after Hostaway cancelled
SKIPPED = "skipped"          # cancelled in Hostaway before it ever reached StayHub
FAILED = "failed"            # a hard failure that needs a human (role / conflict) — never auto-retried
STATUSES = (PENDING, HELD, CONFIRMED, RETRY, REJECTED, CANCELLED, SKIPPED, FAILED)
LIVE = (HELD, CONFIRMED)

STATUS_AR = {
    PENDING: "بانتظار الإرسال", HELD: "محجوز مؤقتاً", CONFIRMED: "مؤكد في ستاي هب",
    RETRY: "بيعيد المحاولة", REJECTED: "رفضه ستاي هب", CANCELLED: "ملغي في ستاي هب",
    SKIPPED: "ألغي قبل الإرسال", FAILED: "يحتاج تدخل",
}

# ---- the error playbook (guide slide 12) ----
# action: "refresh_token" | "resync_retry" | "reject" | "hard_fail" | "deauthorized"
#         | "suspended" | "rebootstrap" | "restart_hold" | "conflict" | "backoff" | "retry"
ERROR_ACTIONS = {
    "AUTH_INVALID_TOKEN": "refresh_token",
    "AUTH_EXPIRED_TOKEN": "refresh_token",
    "AUTH_MISSING_TOKEN": "refresh_token",
    "FORBIDDEN_INSUFFICIENT_ROLE": "hard_fail",
    "FORBIDDEN_PROPERTY": "deauthorized",
    "INVENTORY_RACE": "reject",
    "INVENTORY_TAKEN": "reject",
    "SNAPSHOT_AVAILABILITY_MISMATCH": "reject",
    "SNAPSHOT_PRICE_MISMATCH": "resync_retry",
    "SNAPSHOT_CURRENCY_MISMATCH": "hard_fail",
    "PROPERTY_VERSION_OUTDATED": "resync_retry",
    "PROPERTY_SUSPENDED_STALE_SYNC": "suspended",
    "CURSOR_EXPIRED": "rebootstrap",
    "HOLD_EXPIRED": "restart_hold",
    "IDEMPOTENCY_CONFLICT": "conflict",
    "RATE_LIMITED": "backoff",
    "INTERNAL_ERROR": "retry",
    "VALIDATION_ERROR": "hard_fail",
    "RESERVATION_NOT_FOUND": "hard_fail",
    "NO_AVAILABILITY": "reject",         # ours: the probe showed a closed / unpriced night
}


def action_for_error(code, http_status=None):
    a = ERROR_ACTIONS.get(str(code or "").upper())
    if a:
        return a
    if http_status in (401,):
        return "refresh_token"
    if http_status == 429:
        return "backoff"
    if http_status is None or http_status >= 500:
        return "retry"           # network error / 5xx — transient
    return "hard_fail"


# ---- dates ----

def parse_date(s):
    s = str(s or "").strip()[:10]
    if len(s) != 10:
        return None
    try:
        return datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except (TypeError, ValueError):
        return None


def nights(check_in, check_out):
    """['YYYY-MM-DD', …] for every night from check_in up to (not including) check_out."""
    a, b = parse_date(check_in), parse_date(check_out)
    if not a or not b or b <= a:
        return []
    return [(a + datetime.timedelta(days=i)).isoformat() for i in range((b - a).days)]


# ---- guest phone ----

def normalize_phone(raw):
    """Full international number, digits only, as StayHub asked (9665XXXXXXXX). Saudi local
    forms (05…, 5…, 009665…) are completed with 966. Anything too short to be a real number
    returns None — StayHub then has no WhatsApp route and the row says so."""
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    elif s.startswith("+"):
        pass
    elif len(digits) == 10 and digits.startswith("05"):
        digits = "966" + digits[1:]
    elif len(digits) == 9 and digits.startswith("5"):
        digits = "966" + digits
    if digits.startswith("9660"):
        digits = "966" + digits[4:]
    if len(digits) < 8 or len(digits) > 15:
        return None
    return digits


# ---- the Hostaway side ----

def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def is_cancelled(status):
    s = str(status or "").lower()
    return "cancel" in s or s in ("declined", "expired", "inquirydenied", "denied")


def guest_name(r):
    n = (r or {}).get("guestName")
    if not n:
        n = " ".join(x for x in ((r or {}).get("guestFirstName"), (r or {}).get("guestLastName")) if x)
    n = str(n or "").strip()
    return n or "Guest"


_CONFIRMATION = re.compile(r"confirmation-([A-Za-z0-9]+)$")


def booking_code(r):
    """The Airbnb code (HM…) of a Hostaway reservation. Once booked, channelReservationId reads
    "<listing>-guest-<guest id>-confirmation-HM…" — only the tail is the code, and the guest id
    must not leave Ouja. An inquiry's "…-thread-…" value is not a code at all."""
    for key in ("confirmationCode", "channelReservationId"):
        raw = str((r or {}).get(key) or "").strip()
        m = _CONFIRMATION.search(raw)
        if m:
            return m.group(1)
        if raw and "-guest-" not in raw and "-thread-" not in raw:
            return raw
    v = (r or {}).get("hostawayReservationId")
    return str(v).strip() if v else None


def reservation_view(r, default_currency="SAR"):
    """The fields that matter for StayHub, from one raw Hostaway reservation."""
    r = r or {}
    lid = r.get("listingMapId") or r.get("listingId")
    try:
        lid = int(lid) if lid is not None else None
    except (TypeError, ValueError):
        lid = None
    adults = r.get("adults") or r.get("numberOfGuests") or r.get("guests") or 1
    try:
        adults = max(1, int(adults))
    except (TypeError, ValueError):
        adults = 1
    code = booking_code(r)
    return {
        "ha_reservation_id": str(r.get("id") or "").strip(),
        "external_id": code,
        "listing_id": lid,
        "status": str(r.get("status") or "").strip().lower(),
        "check_in": (str(r.get("arrivalDate") or "")[:10]) or None,
        "check_out": (str(r.get("departureDate") or "")[:10]) or None,
        "adults": adults,
        "total": _num(r.get("totalPrice")),
        "currency": str(r.get("currency") or default_currency).strip().upper() or default_currency,
        "booked_at": str(r.get("reservationDate") or "")[:19] or None,
    }


def eligibility(view, channel, push_channels, confirmed_statuses, mapped, today):
    """(ok, reason). A reservation belongs in StayHub when ALL hold:
         1. it has an id, dates and an external code     2. its channel is pushed (airbnb)
         3. its listing is mapped by an admin           4. it is confirmed in Hostaway
         5. it has not started yet (StayHub cannot hold past nights)
    Reason codes are stable — the push tick counts them and prints the tally."""
    if not view.get("ha_reservation_id"):
        return False, "no_id"
    if not view.get("check_in") or not view.get("check_out") or not nights(view["check_in"], view["check_out"]):
        return False, "no_dates"
    if (channel or "").lower() not in push_channels:
        return False, "channel"
    if not mapped:
        return False, "unmapped"
    if view.get("status") not in {str(s).lower() for s in (confirmed_statuses or ())}:
        return False, "status"
    if not view.get("external_id"):
        return False, "no_code"
    if isinstance(today, datetime.datetime):
        today = today.date()
    if view["check_in"] < today.isoformat():
        return False, "started"
    return True, "ok"


def plan(view, row, cancelled_now, today=None):
    """What to do for one reservation. row = its stayhub_bookings row or None.
    Returns one of: "create" | "modify_dates" | "modify_amount" | "cancel" | "skip_cancel" | None.
    An amount-only change after check-in is ignored: Hostaway's total grows when an RR claim is
    paid, and that money is not what the guest paid for the stay."""
    if row is None:
        return None if cancelled_now else "create"
    st = row.get("status")
    if cancelled_now:
        if st == CONFIRMED and row.get("sh_reservation_id"):
            return "cancel"
        if st in (PENDING, RETRY, REJECTED, HELD, FAILED):
            return "skip_cancel"
        return None
    if st in (CANCELLED, SKIPPED):
        # re-instated in Hostaway after a cancel — book it again
        return "create"
    if st != CONFIRMED:
        return None              # the retry path owns it
    if (view.get("check_in"), view.get("check_out")) != (row.get("pushed_check_in"), row.get("pushed_check_out")):
        return "modify_dates"
    if today is not None and str(view.get("check_in") or "") < today.isoformat():
        return None
    t_new, t_old = view.get("total"), row.get("pushed_total")
    if t_new is not None and (t_old is None or abs(float(t_new) - float(t_old)) > 0.005):
        return "modify_amount"
    return None


# ---- the snapshot ----

def snapshot_from_probe(probe, check_in, check_out, own_nights=()):
    """partnerSnapshot built ONLY from StayHub's own pre-booking probe (their answer to Q1:
    never from the Airbnb price). Returns (snapshot, reason) — snapshot None when the probe
    shows a night that is missing or not free. `own_nights` (a date change on a booking StayHub
    already holds) may show 0 rooms — those nights are taken BY THIS booking; the value is sent
    back exactly as StayHub reported it."""
    want = nights(check_in, check_out)
    if not want:
        return None, "no_nights"
    own = set(own_nights or ())
    by_date = {}
    for d in (probe or {}).get("days") or []:
        date = str(d.get("date") or "")[:10]
        if date:
            by_date[date] = d
    out_days, total = [], 0.0
    for date in want:
        d = by_date.get(date)
        if d is None:
            return None, "night_missing:%s" % date
        rooms = d.get("roomsAvailable")
        rate = d.get("rate")
        if rooms is None or rate is None:
            return None, "night_incomplete:%s" % date
        if int(rooms) < 1 and date not in own:
            return None, "night_full:%s" % date
        out_days.append({"date": date, "rate": rate, "roomsAvailable": rooms})
        total += float(rate)
    snap = {
        "propertyVersion": (probe or {}).get("propertyVersion"),
        "currency": (probe or {}).get("currency") or "SAR",
        "totalAmount": round(total, 2) if total != int(total) else int(total),
        "days": out_days,
    }
    return snap, "ok"


# ---- webhook signatures ----

def _hexes(secret, body, ts):
    key = secret.encode("utf-8")
    yield hmac.new(key, body, hashlib.sha256).hexdigest()
    if ts:
        yield hmac.new(key, str(ts).encode("utf-8") + b"." + body, hashlib.sha256).hexdigest()
        yield hmac.new(key, str(ts).encode("utf-8") + body, hashlib.sha256).hexdigest()


def verify_signature(secrets, body, signature, timestamp=None, now_ts=None, max_age_s=300):
    """True when `signature` ("sha256=<hex>" or bare hex) is an HMAC-SHA256 of the raw body —
    or of "<timestamp>.<body>" — under one of `secrets`. StayHub has not documented which
    string they sign, so the accepted forms are listed here explicitly and nothing else.
    A timestamp older than max_age_s is refused (replay). No secret ⇒ refused."""
    if not secrets or not signature:
        return False
    sig = str(signature).strip()
    if sig.lower().startswith("sha256="):
        sig = sig[7:]
    sig = sig.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sig):
        return False
    if timestamp not in (None, "") and now_ts is not None:
        try:
            if abs(float(now_ts) - float(timestamp)) > max_age_s:
                return False
        except (TypeError, ValueError):
            return False
    body = body if isinstance(body, (bytes, bytearray)) else str(body or "").encode("utf-8")
    for s in secrets:
        for h in _hexes(s, bytes(body), timestamp):
            if hmac.compare_digest(h, sig):
                return True
    return False
