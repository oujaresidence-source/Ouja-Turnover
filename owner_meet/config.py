# -*- coding: utf-8 -*-
"""
owner_meet.config — env flags (read at CALL time) and the owner-editable rules file.

Rules: the repo seed `owner_meet/rules.seed.json` is the default; `$STATE_DIR/owner_meet_rules.json`
wins key-by-key at the top level when present (decor_packs.json pattern). The file is re-read when
its mtime changes, and a broken edit keeps serving the last good copy — a typo in a threshold must
never take the meeting room down.
"""

import copy
import json
import os
import threading

from .host import HOST

SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.seed.json")
STATE_NAME = "owner_meet_rules.json"

_lock = threading.Lock()
_cache = {"key": None, "rules": None}


def _env(name, default):
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    return str(v).strip()


def enabled():
    """OWNER_MEET_ENABLED (default 1). 0 = no routes, no tab code path."""
    return _env("OWNER_MEET_ENABLED", "1") == "1"


def state_dir():
    return HOST.state_dir or _env("STATE_DIR", "/data")


def state_rules_path():
    return os.path.join(state_dir(), STATE_NAME)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _read(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("rules file is not an object")
    return data


def rules():
    """The effective rules dict (a deep copy — callers may not mutate the cache)."""
    sp = state_rules_path()
    key = (_mtime(SEED_PATH), _mtime(sp))
    with _lock:
        if _cache["key"] == key and _cache["rules"] is not None:
            return copy.deepcopy(_cache["rules"])
        merged = _read(SEED_PATH)
        if key[1] is not None:
            try:
                over = _read(sp)
                for k, v in over.items():
                    if not k.startswith("_"):
                        merged[k] = v
            except Exception as e:                       # broken edit -> keep the last good copy
                print("[owner_meet] rules file unreadable, keeping last good copy:", e)
                if _cache["rules"] is not None:
                    return copy.deepcopy(_cache["rules"])
        _cache["key"], _cache["rules"] = key, merged
        return copy.deepcopy(merged)
