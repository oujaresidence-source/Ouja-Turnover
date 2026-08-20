"""Catch what we cannot prevent.

The four worst templates are NOT in this repo. Grepped across all 407 Python files:
«Agreement signed», «Your door code», «الرجاء استخدام الكود التالي», «caught us just
outside», «A small gift» — zero hits. They are Hostaway-side automations, and Python
cannot fix them.

What Python CAN do is notice. _conv_to_item already fetches every message of every
scanned conversation, so running the same guard rules over OUTBOUND messages costs one
loop and no extra API call. The empty door-code template shipped 14 times out of 26; this
is how it gets caught on send #1 instead of send #14.

Read-only and deduped: ONE ticket per (listing_id, rule_code, day). A broken template
fires on every guest in that unit; the team needs one alert, not forty.
"""

import json
import os
import time

_FILENAME = "template_watchdog.json"
_KEEP_DAYS = 14


def _state_dir():
    return os.environ.get("STATE_DIR", "/data")


def path():
    return os.path.join(_state_dir(), _FILENAME)


def _read():
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write(d):
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        tmp = path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
        os.replace(tmp, path())
    except Exception as e:
        print("[watchdog] persist failed:", e)


def _prune(seen, today):
    """Keep the file small; a key older than _KEEP_DAYS can never dedup anything again."""
    cutoff = time.time() - _KEEP_DAYS * 86400
    return {k: v for k, v in seen.items() if float(v.get("at", 0) or 0) >= cutoff}


def scan(msgs, *, listing_id, check_outbound, is_outbound, day=None, body_of=None):
    """Run the content guard over OUTBOUND messages and return the findings that are new
    today. Each finding: {code, detail, matched, body, listing_id, key}.

    Returns [] rather than raising, always: this runs in the live guest path.
    """
    out = []
    try:
        day = day or time.strftime("%Y-%m-%d")
        body_of = body_of or (lambda m: (m.get("body") or ""))
        seen = _prune(_read(), day)
        dirty = False
        for m in (msgs or []):
            if not is_outbound(m):
                continue
            body = body_of(m)
            if not (body or "").strip():
                continue
            v = check_outbound(body)
            if not v.blocked:
                continue
            # ONE ticket per (unit, rule, day). A broken template hits every guest in
            # that unit — the team needs one alert, not forty.
            key = f"{listing_id}:{v.code}:{day}"
            if key in seen:
                continue
            seen[key] = {"at": time.time(), "code": v.code,
                         "listing_id": str(listing_id or ""), "sample": body[:300]}
            dirty = True
            out.append({"code": v.code, "detail": v.detail, "matched": list(v.matched),
                        "body": body, "listing_id": listing_id, "key": key})
        if dirty:
            _write(seen)
    except Exception as e:
        print("[watchdog] scan failed:", e)
        return []
    return out


def reset_for_tests():
    try:
        os.remove(path())
    except Exception:
        pass
