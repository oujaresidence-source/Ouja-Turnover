# -*- coding: utf-8 -*-
"""studio.factory — «ولّد كل شي»: sweep EVERY story and EVERY signal into idea cards.

The per-item buttons answer "give me an idea from this". This answers the different
question the owner actually has: **fill the shelf**. It walks everything that has
never produced a card, generates from each, and keeps going until the sources run out
or the budget does.

Deliberately budgeted, not literally infinite. Every generation is a premium model
call against a live business's API key, so an unbounded loop is a bill, not a feature.
The budget is explicit, reported, and the run tells you exactly what it did NOT get to
so "finished" never quietly means "gave up".

Threading + PROGRESS mirror studio/mine.py so the page and Discord poll it the same way.
"""

import threading
import traceback

from . import db, ideas as ideas_mod, learn, rank
from .host import HOST

DEFAULT_BUDGET = 60          # premium generations per run
HARD_CAP = 400               # nothing the owner can type may exceed this

PROGRESS = {"running": False}
_lock = threading.Lock()


def _p(**kw):
    with _lock:
        PROGRESS.update(kw)


def snapshot():
    with _lock:
        return dict(PROGRESS)


def _now():
    try:
        return HOST.require("now")().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def pending_sources(limit=500):
    """Everything that could still become a card, best-first, without paying anything.

    A signal or story that already produced ideas is skipped — re-generating it would
    spend money to make near-duplicates the novelty guard then throws away."""
    used_stories = set()
    used_signals = set()
    try:
        for r in db.q("SELECT DISTINCT story_id FROM studio_ideas WHERE story_id > 0"):
            used_stories.add(int(r["story_id"]))
        for r in db.q("SELECT DISTINCT signal_sid FROM studio_ideas "
                      "WHERE signal_sid <> ''"):
            used_signals.add(r["signal_sid"])
    except Exception as e:
        print("[studio.factory] pending scan error:", e)

    out = []
    try:
        for s in db.signals(limit=limit):
            if s.get("status") == "hidden" or s["sid"] in used_signals:
                continue
            out.append({"kind": "signal", "id": s["sid"],
                        "label": (s.get("fact") or "")[:80],
                        "weight": int(s.get("strength") or 50)})
    except Exception as e:
        print("[studio.factory] signal scan error:", e)
    try:
        for st in db.stories(limit=limit):
            if st.get("status") == "hidden" or int(st["id"]) in used_stories:
                continue
            out.append({"kind": "story", "id": int(st["id"]),
                        "label": (st.get("title") or "")[:80],
                        # stories score 0-10; put them on the same 0-100 scale
                        "weight": int(st.get("score") or 0) * 10})
    except Exception as e:
        print("[studio.factory] story scan error:", e)
    out.sort(key=lambda x: -x["weight"])
    return out


def run(budget=DEFAULT_BUDGET, sources=None):
    """Blocking sweep. Returns a report dict. Never raises — a factory run that dies
    silently mid-way is worse than one that reports a partial result."""
    budget = max(1, min(int(budget or DEFAULT_BUDGET), HARD_CAP))
    todo = sources if sources is not None else pending_sources()
    _p(running=True, phase="run", total=len(todo), done=0, made=0, empty=0,
       errors=0, budget=budget, started_at=_now(), finished_at="", error="",
       last="", remaining=len(todo))
    made, empty, errors, done = 0, 0, 0, 0
    new_cards = []
    try:
        for item in todo:
            if done >= budget:
                break
            done += 1
            _p(done=done, last=item.get("label", ""),
               remaining=max(0, len(todo) - done))
            try:
                if item["kind"] == "signal":
                    cards = ideas_mod.generate_for_signal(item["id"])
                else:
                    cards = ideas_mod.generate_for_story(item["id"])
            except Exception as e:
                print("[studio.factory] generate failed for %s %s: %s"
                      % (item["kind"], item["id"], e))
                errors += 1
                _p(errors=errors)
                continue
            if cards:
                made += len(cards)
                new_cards.extend(cards)
                _p(made=made)
            else:
                # not an error: the brand gate or the novelty guard did its job
                empty += 1
                _p(empty=empty)
        left = max(0, len(todo) - done)
        _p(running=False, phase="done", finished_at=_now(), remaining=left)
        print("[studio.factory] done: sources=%s used=%s cards=%s empty=%s errors=%s left=%s"
              % (len(todo), done, made, empty, errors, left))
    except Exception as e:
        traceback.print_exc()
        _p(running=False, phase="error", error="%s: %s" % (type(e).__name__, e),
           finished_at=_now())
    return {"sources": len(todo), "used": done, "cards": made, "empty": empty,
            "errors": errors, "left": max(0, len(todo) - done),
            "new": new_cards}


def top_new(cards, n=3):
    """The best of what the run just produced, ranked — what to report back."""
    try:
        stats = learn.stats(db.learn_rows())
    except Exception:
        stats = {"n": 0, "mean": 0, "dims": {}}
    today = _now()[:10]
    return rank.rank(cards or [], stats, today)[:n]


def start_thread(budget=DEFAULT_BUDGET, on_done=None):
    """Kick a sweep in a daemon thread. False if one is already running."""
    with _lock:
        if PROGRESS.get("running"):
            return False
        PROGRESS["running"] = True

    def _target():
        rep = run(budget)
        if on_done:
            try:
                on_done(rep)
            except Exception as e:
                print("[studio.factory] on_done failed:", e)

    threading.Thread(target=_target, name="studio-factory", daemon=True).start()
    return True
