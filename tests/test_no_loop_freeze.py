# -*- coding: utf-8 -*-
"""Discord code must never wait on Hostaway on the event loop.

2026-10-26: a cleaner tapped «📷 Submit for Review» in #4511-clean-checkin and got
"Ouja Turnovers didn't respond in time". The button itself defers on its first line —
the bot was FROZEN. Some async code called a plain (sync) helper that reaches Hostaway
(get_listings_map, unit_checkin_time, ...). On a cold cache that is a network call plus
the throttle's time.sleep (up to 10s) plus 429 backoff (up to 35s) — all on the one
thread that answers every Discord button. Nothing answers while it waits.

The rule this locks: inside an `async def`, a helper that can reach Hostaway is either
handed to a thread (asyncio.to_thread / get_listings_map_async), or — for listings-only
helpers — called right after `await get_listings_map_async()` warmed the cache, with a
`# loop-safe: listings prewarmed` marker on the line.

Older web/finance handlers still carry this debt; they are listed by name in KNOWN_DEBT
so the list can only shrink. Anything new fails here.

Run: python3 -m unittest tests.test_no_loop_freeze
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_SRC = (ROOT / "bot.py").read_text(encoding="utf-8")
LINES = BOT_SRC.splitlines()

MARKER = "# loop-safe: listings prewarmed"
PREWARM = "await get_listings_map_async()"

# Direct calls that block the calling thread on the network / a sleep.
_ROOT_CALLS = {"time.sleep", "requests.get", "requests.post", "requests.put",
               "requests.request", "_ha_session.request", "_ha_session.get"}
_ROOT_NAMES = {"_ha_throttle_acquire", "_api_request"}

# Pre-existing async functions that still block (web/finance pages, startup). They slow
# web pages, not Discord buttons. Fix one → delete its name here. Never add to this list.
KNOWN_DEBT = {
    "on_ready",
    "_exp_export_one", "_exp4_verify", "_exp4_export_one", "_exp4_reverify_verified",
    "_handle_invest", "_api_strategy", "_api_tickets_create", "_api_reviews_list",
    "_api_reviews_open_ticket", "_api_expenses_list", "_api_expenses_queue",
    "_api_expenses_summary", "_api_finance_owners", "_api_finance_adjust",
    "_api_finance_line_edit", "_api_expenses_update", "_api_expenses_post",
    "_api_expenses_verify_selected", "_api_expenses_archive_verified",
    "_api_expenses_repair_apply", "_api_expenses_resolve_apartment",
    "_api_expenses_discard", "_api_expenses_delete", "_api_exp4_edit", "_api_exp4_export",
    "_api_exp4_split_apply", "_api_expenses_sync_status", "_api_expenses_v2_repair_apply",
    "_api_fb_profit", "_api_listings_geocode",
}


def _call_name(call):
    f = call.func
    name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
    full = (f.value.id + "." + f.attr
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None)
    return name, full


def _direct_calls(fn):
    """Calls made by fn itself — nested defs/lambdas run elsewhere, so they don't count."""
    out = []

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Call):
                name, full = _call_name(child)
                out.append((name, full, child.lineno))
            walk(child)
    walk(fn)
    return out


def _scan():
    tree = ast.parse(BOT_SRC)
    sync, asyn = {}, {}
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            sync.setdefault(n.name, []).append(n)
        elif isinstance(n, ast.AsyncFunctionDef):
            asyn.setdefault(n.name, []).append(n)

    def is_root(name, full):
        return full in _ROOT_CALLS or name in _ROOT_NAMES

    callmap = {k: [c for f in fs for c in _direct_calls(f)] for k, fs in sync.items()}
    blocking, changed = set(), True
    while changed:                       # transitive closure over plain helpers
        changed = False
        for k, calls in callmap.items():
            if k in blocking:
                continue
            if any(is_root(n, f) or (n in blocking and n not in asyn) for n, f, _ in calls):
                blocking.add(k)
                changed = True

    hits = []                            # (async fn name, def line, call line, callee)
    for name, fns in asyn.items():
        for fn in fns:
            for n, full, ln in _direct_calls(fn):
                if is_root(n, full) or (n in blocking and n not in asyn):
                    hits.append((name, fn.lineno, ln, full or n))
    return hits


HITS = _scan()


class NoLoopFreezeTest(unittest.TestCase):

    def test_scanner_sees_the_known_helpers(self):
        """Sanity: if the scan stops recognising these, it would pass vacuously."""
        names = {h[0] for h in HITS}
        self.assertIn("_api_listings_geocode", names)     # requests.get on the loop (debt)

    def test_no_new_blocking_call_in_async_code(self):
        bad = []
        for name, def_ln, ln, callee in HITS:
            if name in KNOWN_DEBT:
                continue
            if MARKER in LINES[ln - 1]:
                continue
            bad.append("bot.py:%d async %s → %s" % (ln, name, callee))
        self.assertEqual(bad, [], "Hostaway-reaching call on the event loop — wrap it in "
                         "asyncio.to_thread (or prewarm listings + marker):\n" + "\n".join(bad))

    def test_marker_only_after_a_prewarm(self):
        """The marker is a promise the cache is warm — it must follow a prewarm in the same
        function, within the 3 lines above it (no awaits in between to let it expire)."""
        bad = []
        for name, def_ln, ln, callee in HITS:
            if MARKER not in LINES[ln - 1]:
                continue
            if callee.split(".")[-1] not in ("get_listings_map", "_tk_unit_name", "_tk_listings",
                              "_tk_find_listings", "_ticket_create", "_ticket_from_escalation",
                              "_oujact_find_cleaning_channel", "selected_units"):
                bad.append("bot.py:%d %s is not listings-only" % (ln, callee))
                continue
            window = LINES[max(def_ln - 1, ln - 4):ln - 1]
            if not any(PREWARM in w for w in window):
                bad.append("bot.py:%d marker without `%s` just above" % (ln, PREWARM))
        self.assertEqual(bad, [], "\n".join(bad))

    def test_debt_list_only_shrinks(self):
        """A name that no longer blocks must leave KNOWN_DEBT, so it can't hide a new one."""
        still = {h[0] for h in HITS}
        self.assertEqual(sorted(KNOWN_DEBT - still), [])


if __name__ == "__main__":
    unittest.main()
