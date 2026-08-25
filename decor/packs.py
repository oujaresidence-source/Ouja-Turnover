# -*- coding: utf-8 -*-
"""
decor.packs — loads decor_packs.json.

The owner edits this file. Its own _note promises "the bot reloads it on every use, no
redeploy needed", so we honour that literally: STATE_DIR/decor_packs.json (the Railway
volume — editable live) wins over the repo seed, and both are re-read whenever the file's
mtime changes. A broken edit never takes the module down; the last good copy stays in use
and the error is surfaced through `status()`.
"""

import json
import os
import threading
from pathlib import Path

_REPO_SEED = Path(__file__).resolve().parent.parent / "decor_packs.json"
_lock = threading.Lock()
_cache = {"data": None, "path": None, "mtime": None, "error": ""}


def _candidate_paths():
    state = os.environ.get("STATE_DIR") or ""
    out = []
    if state:
        out.append(Path(state) / "decor_packs.json")
    out.append(_REPO_SEED)
    return out


def _validate(data):
    if not isinstance(data, dict):
        raise ValueError("decor_packs.json must be an object")
    packs = data.get("packs")
    if not isinstance(packs, list) or not packs:
        raise ValueError("decor_packs.json has no packs")
    seen = set()
    for p in packs:
        pid = str(p.get("id") or "").strip()
        if not pid:
            raise ValueError("a pack has no id")
        if pid in seen:
            raise ValueError("duplicate pack id: %s" % pid)
        seen.add(pid)
    return data


def load(force=False):
    """The whole file, cached until its mtime changes."""
    with _lock:
        for path in _candidate_paths():
            try:
                if not path.is_file():
                    continue
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if (not force and _cache["data"] is not None
                    and _cache["path"] == str(path) and _cache["mtime"] == mtime):
                return _cache["data"]
            try:
                data = _validate(json.loads(path.read_text("utf-8")))
            except Exception as e:
                # Keep serving the last good copy — a typo in a live edit must not stop
                # the ops floor from opening orders.
                _cache["error"] = "%s: %s" % (path.name, e)
                if _cache["data"] is not None:
                    return _cache["data"]
                continue
            _cache.update({"data": data, "path": str(path), "mtime": mtime, "error": ""})
            return data
        if _cache["data"] is not None:
            return _cache["data"]
        raise RuntimeError("decor_packs.json not found (looked in %s)"
                           % ", ".join(str(p) for p in _candidate_paths()))


def all_packs():
    return list(load().get("packs") or [])


def get(pack_id):
    pid = str(pack_id or "").strip()
    for p in all_packs():
        if str(p.get("id")) == pid:
            return p
    return None


def cake_lead_hours():
    try:
        return int((load().get("cake") or {}).get("lead_hours") or 24)
    except (TypeError, ValueError):
        return 24


def seed_unit_features():
    """The unit_features map from the JSON, with the `_note`/`_example` documentation keys
    stripped. Only ever used to SEED the table — the sheet the owner fills is authoritative."""
    raw = (load().get("unit_features") or {})
    out = {}
    for slug, feats in raw.items():
        if str(slug).startswith("_") or not isinstance(feats, list):
            continue
        out[str(slug).strip().lower()] = [str(f).strip().lower() for f in feats if str(f).strip()]
    return out


def status():
    load_error = ""
    try:
        load()
    except Exception as e:
        load_error = str(e)
    return {"path": _cache["path"], "packs": len(_cache["data"].get("packs") or []) if _cache["data"] else 0,
            "error": _cache["error"] or load_error,
            "cake_lead_hours": cake_lead_hours() if _cache["data"] else None}


def reset_cache():
    with _lock:
        _cache.update({"data": None, "path": None, "mtime": None, "error": ""})
