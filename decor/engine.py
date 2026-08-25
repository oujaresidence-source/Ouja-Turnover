# -*- coding: utf-8 -*-
"""
decor.engine — the PURE decision layer for «تنسيق الحفلات» orders. No I/O, no db, no
Discord, no clock of its own: every function takes what it needs and returns a value, so
the whole rulebook is testable in milliseconds (schedule/engine.py is the model).

Everything the ops floor is allowed to do is decided here and NOWHERE else:
  * capability_check   — can this apartment physically deliver this pack?
  * capability_stamp   — the exact Arabic warning an overridden order carries forever
  * missing_inputs     — what we still need from the guest
  * dispatch_check     — may this order go to the setup person yet?
  * cake_task_for      — the separate cake job and its own earlier deadline

OWNER RULES ENCODED HERE (2026-07-26):
  1. A guest tapping «أنا مهتم» creates NOTHING. That rule lives in routes/db (there is
     simply no order-building path on the public endpoint) — the engine never invents one.
  2. A missing apartment feature STOPS the supervisor but does not refuse forever: they may
     override. A `correction` override says our record was wrong (clean order). An
     `accept_gap` override says the feature really is absent and we're proceeding anyway —
     that order is STAMPED, and the stamp travels to the thread, the dashboard and the
     vendor message from this one function so the three can never drift apart.
  3. An accept_gap override marks the guest questions that depend on the missing feature as
     «ما ينطبق» — otherwise Signature Silver on a unit with no jacuzzi would wait forever
     for «عبارة الجاكوزي», a question nobody can answer, and never dispatch.
"""

import datetime

# --- feature vocabulary -------------------------------------------------------------
# The pack file speaks in tokens ("pool", "jacuzzi_or_bathtub"); the owner, the team and the
# checklist lines speak Arabic. This map is the only bridge, and it is deliberately small.
FEATURE_AR = {"pool": "مسبح", "jacuzzi": "جاكوزي", "bathtub": "بانيو"}
FEATURE_KEYWORDS = {
    "pool":    ("مسبح", "المسبح", "pool"),
    "jacuzzi": ("جاكوزي", "الجاكوزي", "jacuzzi"),
    "bathtub": ("بانيو", "البانيو", "حوض الاستحمام", "bathtub"),
}
_OR = "_or_"

OVERRIDE_KINDS = ("correction", "accept_gap")


def alternatives(token):
    """'jacuzzi_or_bathtub' -> ['jacuzzi', 'bathtub'];  'pool' -> ['pool'].
    A requirement is satisfied when the unit has ANY alternative (Silver accepts a bathtub)."""
    return [p for p in str(token or "").split(_OR) if p]


def token_ar(token):
    """Arabic name of a requirement, keeping the 'or': 'جاكوزي أو بانيو'."""
    return " أو ".join(FEATURE_AR.get(a, a) for a in alternatives(token))


def _keywords(tokens):
    out = []
    for t in tokens:
        for a in alternatives(t):
            out.extend(FEATURE_KEYWORDS.get(a, (a,)))
    return out


# --- 1. capability ------------------------------------------------------------------

def capability_check(pack, unit_features):
    """Can this apartment deliver this pack?

    `unit_features` is a list/set of feature tokens the unit HAS, or None when the unit is
    not in the features table at all. None is NOT treated as "no features" — not knowing and
    knowing-it's-absent are different answers and the supervisor sees different wording.

    Returns {verdict, missing, missing_ar, required} where verdict is:
        'ok'      — nothing required, or every requirement satisfied
        'missing' — we know this unit and it lacks something (names what)
        'unknown' — this unit isn't in the sheet yet; we refuse to guess
    """
    required = list(pack.get("requires_unit_features") or [])
    if not required:
        return {"verdict": "ok", "missing": [], "missing_ar": [], "required": []}
    if unit_features is None:
        return {"verdict": "unknown", "missing": list(required),
                "missing_ar": [token_ar(t) for t in required], "required": list(required)}
    have = {str(f).strip().lower() for f in unit_features if str(f).strip()}
    missing = [t for t in required if not any(a in have for a in alternatives(t))]
    return {"verdict": "missing" if missing else "ok", "missing": missing,
            "missing_ar": [token_ar(t) for t in missing], "required": list(required)}


def affected_checklist_items(pack, missing_tokens):
    """Which lines of THIS pack's own checklist mention the missing feature.

    A keyword scan over data the owner edits, so it is offered to the supervisor as a
    pre-ticked suggestion, never as the last word. If the owner rewrites a line and the
    keyword disappears, the worst case is an empty list — the stamp still names the feature.
    """
    if not missing_tokens:
        return []
    kws = _keywords(missing_tokens)
    out = []
    for item in pack.get("checklist") or []:
        txt = str(item.get("item_ar") or "")
        if any(k in txt for k in kws):
            out.append(txt)
    return out


def affected_input_keys(pack, missing_tokens):
    """Guest questions that only make sense when the feature exists (Signature Silver's
    `jacuzzi_text`). On an accept_gap override these become «ما ينطبق» so the order can
    still dispatch — see rule 3 in the module docstring."""
    if not missing_tokens:
        return []
    kws = _keywords(missing_tokens)
    names = [a for t in missing_tokens for a in alternatives(t)]
    out = []
    for entry in pack.get("requires_guest_input") or []:
        key = str(entry.get("key") or "")
        label = str(entry.get("label_ar") or "")
        if any(n in key for n in names) or any(k in label for k in kws):
            out.append(key)
    return out


def capability_stamp(pack, missing_tokens, overridden_by="", overridden_at="", verdict="missing"):
    """The permanent Arabic warning an overridden order carries. ONE source of this text:
    the Discord thread header, the dashboard row and the vendor dispatch message all call
    this, so a person reading any of the three reads the same sentence."""
    if not missing_tokens:
        return ""
    name = pack.get("name_ar") or pack.get("name_en") or pack.get("id") or ""
    feats = " و".join(token_ar(t) for t in missing_tokens)
    if verdict == "unknown":
        head = "⚠️ %s تحتاج %s، وما عندنا تأكيد إن هذي الشقة فيها %s." % (name, feats, feats)
    else:
        head = "⚠️ %s فيها تنسيق %s، وهذي الشقة ما فيها %s." % (name, feats, feats)
    lines = [head]
    items = affected_checklist_items(pack, missing_tokens)
    if items:
        lines.append("البنود المتأثرة: " + " · ".join("«%s»" % i for i in items))
    if overridden_by or overridden_at:
        lines.append("تجاوزه: %s — %s" % (overridden_by or "—", overridden_at or "—"))
    return "\n".join(lines)


def open_check(pack, unit_features, override_kind=None, overridden_by="", reason=""):
    """May the supervisor open this request? Default-deny with an opt-in override.

    Returns {allowed, verdict, missing, stamp, na_input_keys, learn_features, error}.
      * no override + verdict missing/unknown  -> allowed False, and the caller is told what
        would need to be overridden (this is the "tells us it's blocked" half).
      * override 'correction' -> allowed, NO stamp, and `learn_features` lists what to write
        into the features sheet so the same apartment never asks again.
      * override 'accept_gap' -> allowed, STAMPED, and the questions that depend on the
        missing feature come back in `na_input_keys`.
    An override with no named supervisor or no reason is refused: nobody pushes a package
    through anonymously.
    """
    cap = capability_check(pack, unit_features)
    if cap["verdict"] == "ok":
        return {"allowed": True, "verdict": "ok", "missing": [], "stamp": "",
                "na_input_keys": [], "learn_features": [], "error": ""}
    if not override_kind:
        return {"allowed": False, "verdict": cap["verdict"], "missing": cap["missing"],
                "stamp": "", "na_input_keys": [], "learn_features": [],
                "error": "capability"}
    if override_kind not in OVERRIDE_KINDS:
        return {"allowed": False, "verdict": cap["verdict"], "missing": cap["missing"],
                "stamp": "", "na_input_keys": [], "learn_features": [], "error": "bad_override"}
    if not str(overridden_by or "").strip() or not str(reason or "").strip():
        return {"allowed": False, "verdict": cap["verdict"], "missing": cap["missing"],
                "stamp": "", "na_input_keys": [], "learn_features": [],
                "error": "override_needs_who_and_why"}
    if override_kind == "correction":
        # "our sheet was wrong" — the unit really does have it. Nothing is missing, so
        # nothing is stamped, and we remember it: first alternative of each requirement.
        learn = [alternatives(t)[0] for t in cap["missing"] if alternatives(t)]
        return {"allowed": True, "verdict": "corrected", "missing": [], "stamp": "",
                "na_input_keys": [], "learn_features": learn, "error": ""}
    return {"allowed": True, "verdict": "accepted_gap", "missing": cap["missing"],
            "stamp": capability_stamp(pack, cap["missing"], overridden_by,
                                      "", cap["verdict"]),
            "na_input_keys": affected_input_keys(pack, cap["missing"]),
            "learn_features": [], "error": ""}


# --- 2. guest input -----------------------------------------------------------------

def missing_inputs(pack, values, na_keys=()):
    """Required guest details still empty, in the pack's own order, with the Arabic label the
    guest will actually be asked for. `na_keys` are the «ما ينطبق» ones an accept_gap
    override cancelled."""
    na = {str(k) for k in (na_keys or ())}
    vals = values or {}
    out = []
    for entry in pack.get("requires_guest_input") or []:
        key = str(entry.get("key") or "")
        if not key or key in na:
            continue
        if not str(vals.get(key) or "").strip():
            row = {"key": key, "label_ar": entry.get("label_ar") or key}
            if entry.get("count"):
                row["count"] = entry["count"]
            out.append(row)
    return out


def dispatch_check(pack, order):
    """May this order go to the setup person? Never on a partial order — the vendor cannot
    work without the phrases. Returns the reasons, not just a no."""
    miss = missing_inputs(pack, order.get("inputs") or {}, order.get("na_input_keys") or ())
    try:
        price = float(order.get("final_price_sar") or 0)
    except (TypeError, ValueError):
        price = 0.0
    needs_price = price <= 0
    return {"ok": (not miss) and not needs_price, "missing_inputs": miss,
            "needs_price": needs_price}


def ask_guest_message(pack, missing, lang="ar"):
    """The WhatsApp text that asks the guest for EXACTLY what's missing, by name — never a
    vague 'we need some details'."""
    if not missing:
        return ""
    name = pack.get("name_ar") if lang == "ar" else (pack.get("name_en") or pack.get("name_ar"))
    if lang == "ar":
        head = "مساكم الله بالخير 🌿 عشان نجهّز %s، ناقصنا:" % name
        tail = "أرسلوا لنا التفاصيل ونبدأ التجهيز 🤍"
    else:
        head = "Hello! To prepare your %s we still need:" % name
        tail = "Send these over and we'll start preparing."
    lines = [head]
    for m in missing:
        label = m.get("label_ar") or m.get("key")
        lines.append("• %s" % label)
    lines.append(tail)
    return "\n".join(lines)


# --- 3. deadlines & the cake --------------------------------------------------------

DEFAULT_CHECKIN_HOUR = 15


def default_deadline(checkin_date, hour=DEFAULT_CHECKIN_HOUR):
    """No event time set → the decoration must be finished by check-in."""
    if isinstance(checkin_date, datetime.datetime):
        return checkin_date
    return datetime.datetime.combine(checkin_date, datetime.time(hour, 0))


def deadlines(pack, deadline, cake_lead_hours=24):
    """Everything that hangs off the decoration deadline. `work_start` is the deadline minus
    the pack's own setup time, so a 150-minute Diamond is flagged late long before 3 PM."""
    setup = int(pack.get("setup_minutes") or 0)
    out = {"deadline": deadline, "work_start": deadline - datetime.timedelta(minutes=setup)}
    if pack.get("includes_cake"):
        out["cake_due"] = deadline - datetime.timedelta(hours=int(cake_lead_hours or 0))
    return out


CAKE_INPUT_KEYS = ("cake_flavor", "cake_writing")


def cake_task_for(pack, deadline, cake_lead_hours=24):
    """The cake is a SEPARATE job: outside bakery, perishable, its own earlier deadline and
    its own escalation. Bronze includes no cake and gets none — asserted in the tests."""
    if not pack.get("includes_cake"):
        return None
    return {"due_at": deadline - datetime.timedelta(hours=int(cake_lead_hours or 0)),
            "needs": [k for k in CAKE_INPUT_KEYS
                      if any(str(e.get("key")) == k for e in (pack.get("requires_guest_input") or []))],
            "state": "pending"}


def cake_ready(pack, order):
    """The cake can't be ordered from the bakery until the guest has chosen flavour+writing."""
    task = cake_task_for(pack, datetime.datetime(2000, 1, 1))
    if not task:
        return {"applies": False, "ok": False, "missing": []}
    vals = order.get("inputs") or {}
    missing = [k for k in task["needs"] if not str(vals.get(k) or "").strip()]
    return {"applies": True, "ok": not missing, "missing": missing}


# --- 4. running late ----------------------------------------------------------------

WARN_DECOR_HOURS = 3      # before work must START (deadline minus the pack's setup time)
WARN_CAKE_HOURS = 6       # before the cake's own, earlier deadline

def _dt(v):
    if isinstance(v, datetime.datetime):
        return v
    try:
        return datetime.datetime.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def warn_due(order, cake, now, decor_hours=WARN_DECOR_HOURS, cake_hours=WARN_CAKE_HOURS):
    """Which warnings does this order deserve RIGHT NOW? Pure — the clock passes `now` in.

    A late cake and a late decoration are different failures, so they are decided and
    escalated separately, and each is returned at most once (the caller stamps `escalated`).
    A dispatched decoration is not late; an ordered/delivered cake is not late.
    """
    out = []
    if (order or {}).get("state") in ("done", "cancelled"):
        return out
    if cake and not cake.get("escalated") and cake.get("state") == "pending":
        due = _dt(cake.get("due_at"))
        if due and now >= due - datetime.timedelta(hours=cake_hours):
            out.append({"kind": "cake", "due_at": cake.get("due_at"),
                        "overdue": now >= due, "cake_id": cake.get("id")})
    if order and not order.get("escalated") and order.get("state") not in ("dispatched",):
        start = _dt(order.get("work_start_at")) or _dt(order.get("deadline_at"))
        if start and now >= start - datetime.timedelta(hours=decor_hours):
            out.append({"kind": "decor", "due_at": order.get("work_start_at") or order.get("deadline_at"),
                        "overdue": now >= start, "order_id": order.get("id")})
    return out


# --- 5. money -----------------------------------------------------------------------

def order_money(pack, order):
    """`price_from_sar` is advertising («تبدأ من») and is NEVER revenue. Only the
    supervisor's `final_price_sar` counts, and margin needs the vendor cost of THIS order."""
    def num(v):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0
    final = num(order.get("final_price_sar"))
    cost = num(order.get("vendor_cost_sar"))
    return {"from_sar": num(pack.get("price_from_sar")), "final_sar": final,
            "vendor_cost_sar": cost, "margin_sar": (final - cost) if final else 0.0,
            "counts_as_revenue": final > 0}
