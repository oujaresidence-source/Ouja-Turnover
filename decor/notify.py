# -*- coding: utf-8 -*-
"""
decor.notify — the Arabic wording, built here; delivery is HOST.notify (wired in bot.py),
DRY-RUN by default so the first deploy posts nothing (schedule/notify.py pattern).

The capability stamp is NOT re-worded here. It comes from engine.capability_stamp and is
pasted verbatim into the thread header and the vendor message, so a supervisor reading the
dashboard and a vendor reading WhatsApp read the same sentence.
"""

import os

from . import engine
from .host import HOST


def dryrun():
    return (os.environ.get("DECOR_DRYRUN", "1") or "1").strip() != "0"


def supervisor_role():
    return (os.environ.get("DECOR_SUPERVISOR_ROLE", "DEC") or "DEC").strip()


# ---------------- a guest tapped a button: interest only ----------------

def lead_line(lead, pack, cap=None):
    """What DEC sees when a guest taps «أنا مهتم». Says out loud that nothing was opened —
    so nobody goes looking for a ticket that does not exist."""
    name = pack.get("name_ar") if pack else lead.get("pack_id")
    apt = lead.get("apartment") or lead.get("slug")
    lines = ["🎈 اهتمام جديد — %s" % name,
             "الشقة: %s" % apt]
    if lead.get("guest_name"):
        lines.append("الضيف: %s" % lead["guest_name"])
    if lead.get("checkin_date"):
        lines.append("الدخول: %s" % lead["checkin_date"])
    if cap and cap.get("verdict") == "missing":
        lines.append("⚠️ هذي الشقة ما فيها %s" % " و".join(cap.get("missing_ar") or []))
    elif cap and cap.get("verdict") == "unknown":
        lines.append("⚠️ ما عندنا تأكيد إن هذي الشقة فيها %s" % " و".join(cap.get("missing_ar") or []))
    lines.append("ما انفتحت تذكرة وما أحد انكلّف — المشرف هو اللي يفتح الطلب.")
    return "\n".join(lines)


# ---------------- a supervisor opened a request ----------------

def thread_name(order, pack):
    apt = order.get("apartment") or order.get("slug") or ""
    return ("تنسيق — %s — %s" % (apt, (pack or {}).get("name_ar") or ""))[:95]


def thread_header(order, pack):
    lines = ["🎀 %s — %s" % ((pack or {}).get("name_ar") or "", order.get("apartment") or order.get("slug"))]
    if order.get("guest_name"):
        lines.append("الضيف: %s" % order["guest_name"])
    if order.get("deadline_at"):
        lines.append("الموعد النهائي: %s" % order["deadline_at"].replace("T", " "))
    if order.get("work_start_at"):
        lines.append("يبدأ الشغل: %s" % order["work_start_at"].replace("T", " "))
    if order.get("capability_stamp"):
        lines.append("")
        lines.append(order["capability_stamp"])
    lines.append("")
    lines.append("فتحه: %s" % (order.get("opened_by") or "—"))
    return "\n".join(lines)


def vendor_message(order, pack):
    """What the setup person receives. The stamp is near the top on purpose: whoever shows up
    with the balloons must know there is no pool BEFORE they arrive."""
    lines = ["السلام عليكم 🌿",
             "طلب تنسيق — %s" % ((pack or {}).get("name_ar") or ""),
             "الشقة: %s" % (order.get("apartment") or order.get("slug"))]
    if order.get("deadline_at"):
        lines.append("لازم يخلص قبل: %s" % order["deadline_at"].replace("T", " "))
    if order.get("capability_stamp"):
        lines.append("")
        lines.append(order["capability_stamp"])
    na = set(order.get("na_input_keys") or [])
    items = [str(i.get("item_ar") or "") for i in ((pack or {}).get("checklist") or [])]
    dropped = set(engine.affected_checklist_items(pack or {}, _missing_tokens(order)))
    if items:
        lines.append("")
        lines.append("المطلوب:")
        for i in items:
            lines.append(("— ~%s~ (ما ينطبق)" % i) if i in dropped else ("— %s" % i))
    vals = order.get("inputs") or {}
    given = [(e.get("label_ar") or e.get("key"), vals.get(e.get("key")))
             for e in ((pack or {}).get("requires_guest_input") or [])
             if str(e.get("key")) not in na and str(vals.get(e.get("key")) or "").strip()]
    if given:
        lines.append("")
        lines.append("من الضيف:")
        for label, val in given:
            lines.append("— %s: %s" % (label, val))
    return "\n".join(lines)


def _missing_tokens(order):
    """The order stores the stamp, not the tokens; recover them for the vendor checklist by
    asking the engine which requirement names appear in the stamp text."""
    stamp = order.get("capability_stamp") or ""
    if not stamp:
        return []
    out = []
    for token, ar in engine.FEATURE_AR.items():
        if ar in stamp:
            out.append(token)
    return out


# ---------------- late warnings ----------------

def late_warning(order, pack, kind="decor"):
    who = "<@&%s>" % supervisor_role() if supervisor_role().isdigit() else "@%s" % supervisor_role()
    apt = order.get("apartment") or order.get("slug")
    if kind == "cake":
        return ("🍰 %s تنبيه: كيك %s (%s) قرب موعده وما انطلب بعد."
                % (who, (pack or {}).get("name_ar") or "", apt))
    return ("⏰ %s تنبيه: تنسيق %s (%s) قرب موعده والحالة: %s."
            % (who, (pack or {}).get("name_ar") or "", apt, order.get("state")))


def fire(kind, payload):
    """Delivery is someone else's job. DRY-RUN prints and returns False so the first deploy
    is observable without posting anything to the team."""
    try:
        if dryrun():
            print("[decor] DRYRUN notify(%s): %s" % (kind, str(payload.get("text", ""))[:160]))
            return False
        notifier = getattr(HOST, "notify", None)
        if not notifier:
            return False
        notifier(dict(payload, kind=kind))
        return True
    except Exception as e:                                   # never break an order on a post
        print("[decor] notify failed (non-fatal):", e)
        return False
