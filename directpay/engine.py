# -*- coding: utf-8 -*-
"""
directpay.engine — the PURE rules. No HOST, no I/O, no discord, no network, no sqlite.
Everything here is a function of its arguments, so the routes, the Discord buttons and the
poller all call the SAME code and cannot drift. This is where the TDD lives
(tests/test_directpay_engine.py).

The state machine:

              +----------------> verified     (proof + amount + reference — the normal close)
   open ------+
              +----------------> written_off  (admin override, PERMANENT RED, never disappears)
              +----------------> void         (not a direct booking / cancelled — reason required)

   verified --> open   ONLY on a price increase after close

There is no 'closed' state and no plain 'close anyway'. Every terminal state carries a reason
and a name.
"""
import datetime

STATUSES = ("open", "verified", "written_off", "void")
TERMINAL = ("written_off", "void")
REF_MIN, REF_MAX = 3, 64
NOTE_MAX = 400
VARIANCE_REASON_MIN, VARIANCE_REASON_MAX = 10, 400
WRITEOFF_REASON_MIN, WRITEOFF_REASON_MAX = 20, 400
VOID_REASON_MIN = 3

_ARABIC_DIGITS = {"٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
                  "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
                  "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
                  "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9"}

_PROOF_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".heif", ".bmp", ".pdf")


# ---------------- reading a Hostaway reservation ----------------

def raw_channel(r):
    """The raw channelName, verbatim — stored on the row and printed on the card."""
    v = (r or {}).get("channelName")
    if v is None:
        v = (r or {}).get("channel")
    return "" if v is None else str(v)


def booked_date(r):
    """'YYYY-MM-DD' of the booking timestamp (reservationDate), or None."""
    v = (r or {}).get("reservationDate")
    if not v:
        return None
    s = str(v).strip()
    if len(s) < 10:
        return None
    d = s[:10]
    try:
        datetime.date(int(d[0:4]), int(d[5:7]), int(d[8:10]))
    except (TypeError, ValueError):
        return None
    return d


def is_direct(r, finance_channel, extra_channels=()):
    """bot._finance_channel decides; DIRECTPAY_EXTRA_CHANNELS adds substrings on top of it.
    The classifier is injected, never copied — two would drift."""
    try:
        if finance_channel(r) == "direct":
            return True
    except Exception:
        return False
    ch = raw_channel(r).strip().lower()
    if ch and extra_channels:
        return any(x and x in ch for x in extra_channels)
    return False


def is_cancelled(status):
    return "cancel" in str(status or "").lower()


def eligibility(r, finance_channel, confirmed_statuses, start_date, extra_channels=(), known_ids=()):
    """(ok, reason). A reservation opens a ticket when ALL hold:
         1. direct (or an extra channel)     2. status confirmed
         3. booked ON or AFTER start_date     4. no ticket for this id yet
    Reason codes are stable — the poller counts them and prints the tally."""
    rid = (r or {}).get("id")
    if rid is None or str(rid).strip() == "":
        return False, "no_id"
    if str(rid) in {str(k) for k in (known_ids or ())}:
        return False, "duplicate"
    if not is_direct(r, finance_channel, extra_channels):
        return False, "not_direct"
    st = str((r or {}).get("status") or "").strip().lower()
    if st not in {str(s).lower() for s in (confirmed_statuses or ())}:
        return False, "status"
    bd = booked_date(r)
    if not bd:
        return False, "no_booked_at"
    if isinstance(start_date, datetime.datetime):
        start_date = start_date.date()
    if isinstance(start_date, datetime.date) and bd < start_date.isoformat():
        return False, "before_start"
    if isinstance(start_date, str) and start_date and bd < start_date[:10]:
        return False, "before_start"
    return True, "ok"


def select_openable(candidates, max_per_tick):
    """The per-tick cap. Returns (take, waiting) — the remainder is REPORTED, never dropped."""
    cap = max(0, int(max_per_tick or 0))
    take = list(candidates)[:cap]
    return take, max(0, len(list(candidates)) - len(take))


# ---------------- money ----------------

def _num(v, default=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:                       # NaN
        return default
    return f


def parse_amount(s):
    """A positive SAR amount typed by a human: Arabic-Indic digits, thousands commas, a stray
    'ر.س'. None when it is not a positive number."""
    t = str(s or "").strip()
    if not t:
        return None
    t = "".join(_ARABIC_DIGITS.get(c, c) for c in t)
    t = t.replace(",", "").replace("٫", ".").replace("٬", "")
    if t.startswith("-") or t.startswith("−"):
        return None
    keep = []
    for c in t:
        if c.isdigit() or c == ".":
            keep.append(c)
        elif keep:
            break
    t = "".join(keep)
    if not t or t == ".":
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return v if v > 0 else None


def variance(received, total, abs_tol=1.0, pct_tol=0.01):
    """variance = received - total; tolerance = max(abs_tol, total * pct_tol)."""
    rec, tot = _num(received), _num(total)
    tol = max(_num(abs_tol), abs(tot) * _num(pct_tol))
    v = round(rec - tot, 2)
    return {"variance": v, "tolerance": round(tol, 2), "ok": abs(v) <= tol,
            "received": rec, "total": tot}


def _fmt(v):
    v = _num(v)
    return ("%d" % v) if float(v).is_integer() else ("%.2f" % v)


# ---------------- the state machine ----------------

def transition(row, target, ctx):
    """(ok, reason_ar, patch). On success `patch` is the dict of columns to write. On refusal
    `patch` is an info dict with a stable `code`:
        terminal | already | unknown | no_proof | amount | ref | variance | reason | no_increase
    """
    row, ctx = dict(row or {}), dict(ctx or {})
    cur = str(row.get("status") or "open")
    if target not in STATUSES:
        return False, "حالة غير معروفة", {"code": "unknown"}
    if cur in TERMINAL:
        return False, "التذكرة مقفلة نهائيًا (%s) وما تنفتح." % _status_ar(cur), {"code": "terminal"}
    if cur == target:
        return True, "", {}

    if target == "verified":
        if cur != "open":
            return False, "ما تقدر تعتمد تحصيل تذكرة حالتها %s." % _status_ar(cur), {"code": "already"}
        if not str(ctx.get("proof_path") or "").strip():
            return False, "ما فيه إثبات مرفوع. ارفع صورة أو PDF من StayHub أول.", {"code": "no_proof"}
        amt = _num(ctx.get("received_sar"), None)
        if amt is None or amt <= 0:
            return False, "المبلغ المستلم لازم يكون رقم أكبر من صفر.", {"code": "amount"}
        ref = str(ctx.get("stayhub_ref") or "").strip()
        if not (REF_MIN <= len(ref) <= REF_MAX):
            return False, "رقم العملية في StayHub لازم يكون بين %d و %d حرف." % (REF_MIN, REF_MAX), {"code": "ref"}
        total = row.get("total_sar_current")
        if total is None:
            total = row.get("total_sar")
        v = variance(amt, total, ctx.get("abs_tol", 1.0), ctx.get("pct_tol", 0.01))
        vreason = str(ctx.get("variance_reason") or "").strip()
        if not v["ok"] and not (VARIANCE_REASON_MIN <= len(vreason) <= VARIANCE_REASON_MAX):
            why = ("المبلغ ما يطابق: الحجز %s ر.س والمستلم %s ر.س (الفرق %s ر.س). "
                   "إذا الفرق صحيح (استرجاع، خصم، دفعة جزئية) اضغط «إغلاق مع فرق» واكتب السبب."
                   % (_fmt(v["total"]), _fmt(v["received"]), _fmt(v["variance"])))
            return False, why, {"code": "variance", "variance": v["variance"],
                                "tolerance": v["tolerance"], "total": v["total"], "received": amt}
        note = str(ctx.get("note") or "").strip()[:NOTE_MAX]
        patch = {"status": "verified", "received_sar": amt, "stayhub_ref": ref,
                 "proof_path": ctx.get("proof_path"), "proof_meta": ctx.get("proof_meta"),
                 "variance_sar": v["variance"], "variance_reason": vreason or None,
                 "closed_by": ctx.get("by") or "", "closed_by_id": str(ctx.get("by_id") or ""),
                 "closed_at": ctx.get("now"), "close_note": note or None}
        return True, "", patch

    if target == "written_off":
        if cur != "open":
            return False, "ما ينشطب إلا تذكرة مفتوحة.", {"code": "already"}
        reason = str(ctx.get("reason") or "").strip()
        if not (WRITEOFF_REASON_MIN <= len(reason) <= WRITEOFF_REASON_MAX):
            return False, ("الإغلاق بدون إثبات يحتاج سبب واضح (%d حرف على الأقل)."
                           % WRITEOFF_REASON_MIN), {"code": "reason"}
        return True, "", {"status": "written_off", "close_note": reason,
                          "closed_by": ctx.get("by") or "", "closed_by_id": str(ctx.get("by_id") or ""),
                          "closed_at": ctx.get("now")}

    if target == "void":
        if cur != "open":
            return False, "ما تنلغى إلا تذكرة مفتوحة.", {"code": "already"}
        reason = str(ctx.get("reason") or "").strip()
        if len(reason) < VOID_REASON_MIN:
            return False, "اكتب السبب.", {"code": "reason"}
        return True, "", {"status": "void", "void_reason": reason[:NOTE_MAX],
                          "closed_by": ctx.get("by") or "", "closed_by_id": str(ctx.get("by_id") or ""),
                          "closed_at": ctx.get("now")}

    if target == "open":
        if cur != "verified":
            return False, "ما تنفتح من هذي الحالة.", {"code": "already"}
        new_total = _num(ctx.get("total_sar_current"), None)
        old_total = _num(row.get("total_sar_current"), None)
        if old_total is None:
            old_total = _num(row.get("total_sar"), None)
        if new_total is None or old_total is None or new_total <= old_total + 0.005:
            return False, "ما تنفتح إلا لو زاد المبلغ بعد الإغلاق.", {"code": "no_increase"}
        return True, "", {"status": "open", "total_sar_current": new_total}

    return False, "حالة غير معروفة", {"code": "unknown"}


def _status_ar(s):
    return {"open": "مفتوحة", "verified": "تم التحصيل", "written_off": "إغلاق بدون إثبات",
            "void": "ملغاة"}.get(str(s or ""), str(s or ""))


def status_ar(s):
    return _status_ar(s)


# ---------------- aging + totals ----------------

def _date_of(iso):
    s = str(iso or "")[:10]
    try:
        return datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except (TypeError, ValueError):
        return None


def age_days(row, today):
    if isinstance(today, datetime.datetime):
        today = today.date()
    d = _date_of((row or {}).get("created_at"))
    if d is None or today is None:
        return 0
    return max(0, (today - d).days)


def row_amount(row):
    """The debt right now: total_sar_current when refreshed, else the open-time total."""
    cur = (row or {}).get("total_sar_current")
    if cur is not None:
        return _num(cur)
    return _num((row or {}).get("total_sar"))


def bucket_key(age):
    if age <= 2:
        return "b0_2"
    if age <= 7:
        return "b3_7"
    if age <= 14:
        return "b8_14"
    return "b15p"


def aging_buckets(rows, today):
    out = {k: {"count": 0, "sar": 0.0} for k in ("b0_2", "b3_7", "b8_14", "b15p")}
    for r in rows or []:
        if str(r.get("status")) != "open":
            continue
        k = bucket_key(age_days(r, today))
        out[k]["count"] += 1
        out[k]["sar"] = round(out[k]["sar"] + row_amount(r), 2)
    return out


def outstanding_total(rows):
    return round(sum(row_amount(r) for r in (rows or []) if str(r.get("status")) == "open"), 2)


def written_off_total(rows):
    return round(sum(row_amount(r) for r in (rows or []) if str(r.get("status")) == "written_off"), 2)


# ---------------- clocks ----------------

def _dt_of(iso):
    s = str(iso or "")
    if len(s) < 16:
        return None
    try:
        return datetime.datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]))
    except (TypeError, ValueError):
        return None


def nudge_due(row, now, after_days, every_days):
    """One nudge once the room is older than after_days, then one per every_days window."""
    if str((row or {}).get("status")) != "open":
        return False
    if isinstance(now, datetime.datetime) and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    if age_days(row, now) < int(after_days or 0):
        return False
    last = _dt_of((row or {}).get("last_nudge_at"))
    if int((row or {}).get("nudge_count") or 0) > 0 and last is not None:
        if (now - last) < datetime.timedelta(days=int(every_days or 1)):
            return False
    return True


def summary_due(now, last_date, hour):
    """Once per Riyadh day, from `hour` onward; `last_date` is the PERSISTED latch."""
    if now.hour < int(hour):
        return False
    return now.date().isoformat() != str(last_date or "")


# ---------------- proof + gate ----------------

def is_proof_type(content_type, filename=""):
    """Only an image or a PDF is evidence. A .txt is not an invoice."""
    ct = str(content_type or "").lower().strip()
    if ct.startswith("image/") or ct.startswith("application/pdf"):
        return True
    if ct and not ct.startswith("application/octet-stream"):
        return False
    fn = str(filename or "").lower()
    return any(fn.endswith(ext) for ext in _PROOF_EXT)


def can_close(user, extra_ids):
    """The owner's rule, verbatim: only people with **administrator** on in Discord, plus any
    id explicitly listed. manage_guild does NOT count. No permissions object ⇒ no."""
    if user is None:
        return False
    p = getattr(user, "guild_permissions", None)
    if p is not None and bool(getattr(p, "administrator", False)):
        return True
    uid = getattr(user, "id", None)
    try:
        return uid is not None and int(uid) in {int(x) for x in (extra_ids or ())}
    except (TypeError, ValueError):
        return False
