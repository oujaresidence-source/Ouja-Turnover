# -*- coding: utf-8 -*-
"""
rrdesk.evalset — grade the request detector on the golden set (122 real, redacted Sam
messages, hand-labelled: tests/fixtures/rrdesk/golden_requests.jsonl).

    baseline_table()       offline: the recorded heuristic baseline (no model) → precision table
    run_live(limit=None)   live: the real classifier (Haiku, same prompt as production) → the
                           table, the chosen threshold and mode; stored as «eval:last» for the
                           settings view. NEVER auto-applied — the owner decides.

The rule (brief §4.5): the lowest threshold with ≥ 95% precision on is_request ('auto'); else
≥ 90% ('confirm' — detected requests ask Sam first); else 'explicit' (only /rr-ask and 📌).
A false accusation is worse than a missed detection.
"""

import json
import os

from . import db, engine, translate

GOLDEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tests", "fixtures", "rrdesk", "golden_requests.jsonl")


def load(path=GOLDEN):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def baseline_table(rows=None):
    rows = rows if rows is not None else load()
    samples = [(r["baseline"]["confidence"], bool(r["baseline"]["is_request"]),
                bool(r["label"]["is_request"])) for r in rows]
    return engine.choose_threshold(samples)


def run_live(limit=None, poster=None):
    rows = load()[:limit] if limit else load()
    samples, misses = [], []
    for r in rows:
        try:
            out = translate.translate_text(r["text"], engine.direction(r["text"]) or "en2ar",
                                           classify=True, poster=poster)
        except translate.CapReached:
            break
        except Exception as e:
            misses.append({"id": r["id"], "error": str(e)[:120]})
            continue
        c = out.get("classify") or {}
        samples.append((c.get("confidence") or 0.0, bool(c.get("is_request")), bool(r["label"]["is_request"])))
    res = engine.choose_threshold(samples)
    res.update({"n": len(samples), "errors": misses[:10], "at": db.iso(db.now())})
    db.set_setting("eval:last", json.dumps(res, ensure_ascii=False, default=str), "eval")
    return res
