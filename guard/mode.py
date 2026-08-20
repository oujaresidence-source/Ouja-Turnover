"""ASSISTANT_MODE — shadow · canary · full, resolved at RUNTIME.

    stored file on the volume   >   env var   >   "shadow"

WHY NOT JUST AN ENV VAR
A module-scope constant read once at import is not a kill switch. Changing a Railway
variable restarts the container, which means the fastest way to stop the assistant would
be a redeploy — and a redeploy of THIS bot is itself a known hazard (the auto-send spam
incident of 2026-06-20 came from rapid redeploys). §4/T1 is explicit: "If it needs a
redeploy, it is not a kill switch — fix it."

So the stored value wins and is re-read whenever the file changes, exactly like
ops/switch.py does for the ops phases: a flip takes effect on the very next send, with
no restart, and it SURVIVES a redeploy (an env var winning would silently re-enable
sending on the next deploy and nobody would notice).

DIRECTION IS NOT SYMMETRIC. Going quieter (full → canary → shadow) is always allowed.
Going louder is a deliberate act and the caller must say who did it and why.
"""

import json
import os
import threading
import time

SHADOW, CANARY, FULL = "shadow", "canary", "full"
VALID = (SHADOW, CANARY, FULL)

# quieter is lower. A move DOWN this ladder is always safe.
_RANK = {SHADOW: 0, CANARY: 1, FULL: 2}

_FILENAME = "assistant_mode.json"
_LOCK = threading.Lock()
_CACHE = {"mtime": None, "data": None}


def _state_dir():
    return os.environ.get("STATE_DIR", "/data")


def path():
    return os.path.join(_state_dir(), _FILENAME)


def _stored():
    """Re-read only when the file actually changed (mtime), so this is cheap enough to
    call on every single send. A broken edit keeps serving the last good copy."""
    try:
        mtime = os.path.getmtime(path())
    except Exception:
        return None
    if _CACHE["mtime"] == mtime:
        return _CACHE["data"]
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or data.get("mode") not in VALID:
            return _CACHE["data"]
        _CACHE["mtime"], _CACHE["data"] = mtime, data
        return data
    except Exception:
        return _CACHE["data"]          # last good copy


def _env_mode():
    m = (os.environ.get("ASSISTANT_MODE") or "").strip().lower()
    return m if m in VALID else None


def current():
    """The mode in force RIGHT NOW. Defaults to shadow: the safe value."""
    st = _stored()
    if st:
        return st.get("mode")
    return _env_mode() or SHADOW


def canary_listing_ids():
    """Listing ids allowed to send while in canary. Stored value wins, same as the mode."""
    st = _stored()
    raw = (st or {}).get("canary_listing_ids")
    if raw is None:
        raw = os.environ.get("CANARY_LISTING_IDS", "")
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    else:
        parts = [str(p).strip() for p in (raw or [])]
    return {p for p in parts if p}


def in_canary(listing_id):
    return str(listing_id or "") in canary_listing_ids()


def set_mode(mode, *, actor, reason="", canary_listing_ids=None):
    """Write the stored override. Returns the new mode.

    Going LOUDER (towards full) requires a reason — not because a string protects
    anybody, but because the record of who turned sending back on is the first thing
    anyone will want after an incident.
    """
    mode = (mode or "").strip().lower()
    if mode not in VALID:
        raise ValueError(f"mode must be one of {VALID}, got {mode!r}")
    if _RANK[mode] > _RANK[current()] and not str(reason or "").strip():
        raise ValueError("turning the assistant louder requires a reason")
    payload = {"mode": mode, "actor": str(actor or "")[:80],
               "reason": str(reason or "")[:300], "at": time.time()}
    if canary_listing_ids is not None:
        payload["canary_listing_ids"] = [str(x) for x in canary_listing_ids]
    else:
        st = _stored() or {}
        if st.get("canary_listing_ids"):
            payload["canary_listing_ids"] = st["canary_listing_ids"]
    with _LOCK:
        os.makedirs(_state_dir(), exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, path())         # atomic: never serve a half-written mode
        _CACHE["mtime"] = None          # force a re-read on the next call
    return mode


def reset_for_tests():
    with _LOCK:
        _CACHE["mtime"] = _CACHE["data"] = None
