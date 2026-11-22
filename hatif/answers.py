# -*- coding: utf-8 -*-
"""
hatif.answers — the approved answer bank the WhatsApp reader is allowed to send.

The bot never writes an answer itself: the AI only PICKS an id from this bank, and the text is
sent word for word. The repo seed (answers_seed.json) is the default; an owner-edited copy at
$STATE_DIR/hatif_answers.json wins and is re-read when its mtime changes. A broken edit keeps
serving the last good copy (decor_packs.json pattern) — the bank never goes empty.
"""
import json
import os
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(_HERE, "answers_seed.json")
KINDS = ("final", "collect", "human")

_lock = threading.Lock()
_cache = {"key": None, "bank": None}


def _override_path():
    d = os.environ.get("STATE_DIR", "").strip()
    return os.path.join(d, "hatif_answers.json") if d else ""


def validate(raw):
    """{id: entry} with only well-formed entries. Raises ValueError when nothing usable."""
    items = (raw or {}).get("answers") if isinstance(raw, dict) else None
    if not isinstance(items, dict):
        raise ValueError("no 'answers' object")
    out = {}
    for k, v in items.items():
        if not isinstance(v, dict):
            continue
        text = str(v.get("text") or "").strip()
        kind = v.get("kind") if v.get("kind") in KINDS else "final"
        if not text:
            continue
        out[str(k)] = {"kind": kind, "text": text, "about": str(v.get("about") or ""),
                       "team": str(v.get("team") or ""), "urgent": bool(v.get("urgent"))}
    if "human" not in out:
        raise ValueError("bank must keep the 'human' answer")
    return out


def _read(path):
    with open(path, encoding="utf-8") as f:
        return validate(json.load(f))


def bank():
    """The live bank. Override file if present and valid, else the seed."""
    ov = _override_path()
    paths = [p for p in (ov, SEED) if p and os.path.isfile(p)]
    key = tuple((p, os.path.getmtime(p)) for p in paths)
    with _lock:
        if _cache["bank"] is not None and _cache["key"] == key:
            return _cache["bank"]
        for p in paths:
            try:
                b = _read(p)
                _cache.update(key=key, bank=b)
                return b
            except Exception as e:
                print("[hatif] answer bank %s unreadable, keeping last good: %s" % (os.path.basename(p), e))
                if _cache["bank"] is not None:      # a broken owner edit never falls back to stale seed
                    return _cache["bank"]
        raise RuntimeError("hatif answer bank missing")


def reset_for_tests():
    with _lock:
        _cache.update(key=None, bank=None)
