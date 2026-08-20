"""The shadow log — what the assistant WOULD have said, and why.

In shadow mode every decision runs for real and nothing reaches a guest. This file is the
entire evidence base for the rollout gates in §7 and §8: without it there is no way to
answer "did v2 beat v1", which today has no metric at all.

One JSON object per line on the volume. Append-only, never rolled: the replay tool
(tools/shadow_replay.py) joins these against what actually happened next in the thread.
Never raises — a logging failure must not take down a reply path.
"""

import json
import os
import threading
import time

_LOCK = threading.Lock()
_FILENAME = "shadow_log.jsonl"

FIELDS = ("ts", "conversation_id", "listing_id", "guest_text", "gate_decision", "action",
          "confidence", "guard_verdict", "would_send_body", "commitment_detected",
          "incident_tier", "used_memory", "latency_ms", "cost_usd", "reason", "mode")


def _state_dir():
    return os.environ.get("STATE_DIR", "/data")


def path():
    return os.path.join(_state_dir(), _FILENAME)


def log(conversation_id, body, *, reason="", **kw):
    """Record one would-be send. Extra keys are accepted and stored as-is."""
    rec = {f: None for f in FIELDS}
    rec.update({
        "ts": time.time(),
        "conversation_id": str(conversation_id or ""),
        "would_send_body": body or "",
        "reason": reason or "",
    })
    for k, v in (kw or {}).items():
        rec[k] = v
    try:
        with _LOCK:
            os.makedirs(_state_dir(), exist_ok=True)
            with open(path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print("[shadow] append failed:", e)
    return rec


def read_all(limit=None):
    """Every logged decision, oldest first. Torn lines are skipped, not fatal."""
    out = []
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        return []
    except Exception as e:
        print("[shadow] read failed:", e)
    return out[-limit:] if limit else out
