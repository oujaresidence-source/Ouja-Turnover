# -*- coding: utf-8 -*-
"""
ops.switch — the owner's remote control for all three phases.

WHY THIS EXISTS
    Every phase ships silent (dry-run) and the only way to turn it on was editing a Railway
    variable. That is three trips into a developer console for a person who reviews work by
    screenshot, and — worse — it means the ONE action that starts taking money off people
    happens in a place with no confirmation, no record of who did it, and no way to undo it
    from a phone.

THE RESOLUTION ORDER, and why the database wins
    switch in brain.db   >   Railway env var   >   built-in default
The stored value wins because a flip made from the page has to SURVIVE A REDEPLOY. If the env
var won, Railway would silently re-silence the system on the next deploy and nobody would
notice for weeks. The env var stays as the boot-time default so nothing changes for anyone who
never touches the page.

DIRECTION IS NOT SYMMETRIC
    Turning something OFF is one click, always allowed, and takes effect within seconds.
    Turning something ON (live) needs the admin role AND a typed confirmation.
Making it easy to stop and deliberate to start is the whole safety model here.
"""

import os
import time

from . import db

# key -> (env var, built-in default, Arabic label, what going live actually does)
SWITCHES = {
    "warn_dryrun": (
        "OPS_WARN_DRYRUN", "1", "نظام الالتزام — الإنذارات",
        "بيرسل التذكيرات للموظفين وبيسجل إنذارات تنقص من العمولة"),
    "clean_check_dryrun": (
        "CLEAN_CHECK_DRYRUN", "1", "القفل — سؤال التنظيف",
        "بيسأل المسؤول «هل تم تنظيف الشقة؟» بعد ما يعدّي وقت الدخول"),
    "scorecard_dryrun": (
        "SCORECARD_DRYRUN", "1", "كرت التقييم الشهري",
        "بيسمح باعتماد الكروت وإرسالها للموظفين"),
}

# A renamed switch must carry its old setting across. «nudge_dryrun» (the five-level ladder)
# became «clean_check_dryrun» (one question). The owner had already deliberately turned the
# old one ON; dropping that on the floor would silently re-enable the PUBLIC shared-room
# nagging they asked us to remove, which is the opposite of what they chose. The new feature
# sends strictly fewer messages than the one they authorised, so carrying the choice over is
# the conservative direction, not the reckless one.
LEGACY_KEYS = {"clean_check_dryrun": "nudge_dryrun"}

CONFIRM_WORD = "تشغيل"        # must be TYPED to take a system live

_cache = {"at": 0.0, "vals": {}}
_TTL = 3.0                    # seconds; a kill switch must land fast, reads must stay cheap


def _stored():
    now = time.time()
    if now - _cache["at"] < _TTL:
        return _cache["vals"]
    try:
        vals = db.switch_all()
    except Exception as e:
        print("[ops.switch] read failed, falling back to env:", e)
        vals = {}
    _cache["at"], _cache["vals"] = now, vals
    return vals


def invalidate():
    _cache["at"] = 0.0


def _stored_value(key):
    vals = _stored()
    v = vals.get(key)
    if v in ("0", "1"):
        return v
    legacy = LEGACY_KEYS.get(key)
    if legacy:
        v = vals.get(legacy)
        if v in ("0", "1"):
            return v
    return None


def value(key):
    """'1' = silent (dry-run), '0' = live. Stored value wins over the env var."""
    env_name, default = SWITCHES[key][0], SWITCHES[key][1]
    stored = _stored_value(key)
    if stored is not None:
        return stored
    return (os.environ.get(env_name, default) or default).strip()


def source(key):
    return "page" if _stored_value(key) is not None else "railway"


def is_dry(key):
    return value(key) == "1"


def set_value(key, dry, by, confirm=""):
    """Flip one switch. Going LIVE requires the typed confirmation word; going quiet never
    does — stopping must never be harder than starting."""
    if key not in SWITCHES:
        return {"ok": False, "error": "مفتاح غير معروف"}
    going_live = not dry
    if going_live and (confirm or "").strip() != CONFIRM_WORD:
        return {"ok": False, "error": "اكتب كلمة «%s» عشان تشغّله فعلياً" % CONFIRM_WORD,
                "need_confirm": True, "key": key,
                "effect": SWITCHES[key][3]}
    db.switch_set(key, "1" if dry else "0", by)
    invalidate()
    return {"ok": True, "key": key, "dry": dry, "by": by,
            "message": ("وقفناه — رجع وضع التجربة ✅" if dry
                        else "شغّال فعلياً الحين ⚠️ — %s" % SWITCHES[key][3])}


def stop_everything(by):
    """One button that silences all three at once. No confirmation, ever: the moment somebody
    wants this, they want it NOW."""
    for key in SWITCHES:
        db.switch_set(key, "1", by)
    invalidate()
    return {"ok": True, "message": "وقّفنا كل شي — الأنظمة الثلاثة رجعت وضع التجربة ✅"}


def panel():
    """What the remote control renders."""
    out = []
    for key, (env_name, default, label, effect) in SWITCHES.items():
        row = db.switch_row(key) or {}
        out.append({
            "key": key, "label": label, "effect": effect,
            "dry": is_dry(key), "source": source(key),
            "env": env_name,
            "changed_by": row.get("set_by") or "", "changed_at": row.get("set_at") or "",
        })
    return {"switches": out, "confirm_word": CONFIRM_WORD,
            "all_quiet": all(is_dry(k) for k in SWITCHES)}
