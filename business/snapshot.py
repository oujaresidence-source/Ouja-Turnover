# -*- coding: utf-8 -*-
"""
business.snapshot — the nightly job (superprompt §3).

    Hostaway API ─► fetch_snapshot ─► compute_metrics ─► write metrics_snapshot.json
                                                     └─► archive metrics_snapshot_YYYY-MM-DD.json
                                                     └─► prune archives older than 400 days

The route never calls Hostaway; it reads the latest snapshot. This module is what
keeps that snapshot fresh. Orchestration is dependency-injected so it's testable
without a network or a disk.
"""
import datetime
import os
import re

from .metrics import compute_metrics, fetch_snapshot, write_snapshot

CURRENT_NAME = "metrics_snapshot.json"
RETAIN_DAYS = 400
_ARCHIVE_RE = re.compile(r"^metrics_snapshot_(\d{4}-\d{2}-\d{2})\.json$")


def archive_name(day):
    return "metrics_snapshot_%s.json" % day.isoformat()


def archives_to_prune(names, today, retain_days=RETAIN_DAYS):
    """Return archive filenames older than retain_days. Ignores non-archive names."""
    cutoff = today - datetime.timedelta(days=retain_days)
    out = []
    for name in names:
        m = _ARCHIVE_RE.match(name)
        if not m:
            continue
        try:
            d = datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < cutoff:
            out.append(name)
    return out


def build_and_write(today=None, fetch=fetch_snapshot, compute=compute_metrics,
                    save_json=None, list_archives=None, delete=None,
                    fetch_kwargs=None):
    """Fetch -> compute -> write current + dated archive -> prune stale archives.

    Injected: save_json(name, obj)->bool, list_archives()->[names], delete(name).
    Defaults hit the real STATE_DIR via business.metrics.write_snapshot / os.
    Returns a small result dict (never raises for a transient fetch/write hiccup).
    """
    today = today or datetime.date.today()
    result = {"ok": False, "written": [], "pruned": [], "error": None}
    try:
        raw = fetch(**(fetch_kwargs or {}))
        metrics = compute(raw)

        def _save(name, obj):
            if save_json is not None:
                return bool(save_json(name, obj))
            return write_snapshot(obj, name=name)

        _save(CURRENT_NAME, metrics)
        arch = archive_name(today)
        _save(arch, metrics)
        result["written"] = [CURRENT_NAME, arch]

        names = list_archives() if list_archives is not None else _default_list_archives()
        for name in archives_to_prune(names, today=today):
            (delete or _default_delete)(name)
            result["pruned"].append(name)

        result["ok"] = True
    except Exception as exc:  # nightly job must not crash the bot
        result["error"] = repr(exc)
    return result


def _state_dir():
    return os.environ.get("STATE_DIR", "/data")


def _default_list_archives():
    try:
        return os.listdir(_state_dir())
    except OSError:
        return []


def _default_delete(name):
    try:
        os.remove(os.path.join(_state_dir(), name))
    except OSError:
        pass
