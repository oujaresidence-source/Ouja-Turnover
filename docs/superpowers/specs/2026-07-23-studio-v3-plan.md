# Ouja Studio v3 — «مصنع الإشارات» (signal factory)

Date: 2026-07-23. Owner decision: build ALL stages in one pass.
Supersedes the v2 design (2026-07-08) *additively* — v2 code (miner, brand gate,
playbook, hook cleanliness) is REUSED, not replaced.

## Stage-0 diagnosis (why v2 output is weak)

1. Exactly ONE signal source: guest conversations. Occupancy, pricing, reviews, ops,
   seasonality, insider knowledge — all unused.
2. ZERO web search. No external/news awareness anywhere in `studio/` or `bot.py`
   (`claude_json` is a plain `/v1/messages` call, no tools).
3. The grounding fact (spec F3 SIGNAL) is never stored — `studio_ideas` has no
   signal column, so "every idea references a real signal" is unenforceable.
4. 5 triggers, not 7 (missing `authority`, `social_proof`, `news`).
5. Learn loop = `top_posted_archetypes()` by `story_type` only. No trigger / format /
   audience / source-family learning, and nothing shown to the owner (spec I4).
6. No manual signal input (spec E), no calendar (H1), no 3/day, no instant-idea
   button (H3), no repetition guard (H4).
7. Daily digest defaults to DRY-RUN so the owner sees nothing in Discord.

## The spine: a SIGNAL BUS

Everything that can ground an idea becomes a **Signal** row. Ideas hang off signals.
Guest stories keep their own table and emit a signal, so v2's mining pipeline is intact.

```
Signal = {
  sid          stable hash → dedup across runs
  family       internal | external | manual
  source       occupancy pricing reviews ops season insider guest_story   (internal)
               regulation market global_trend trend                        (external)
               manual                                                      (manual)
  title        short Arabic label
  fact         THE grounded fact (what the idea must reference) — required
  detail       extra context
  url          REQUIRED when family == external
  as_of        YYYY-MM-DD (freshness, spec F10)
  strength     0-100 content-worthiness
  status       new | used | hidden
}
```

**Anti-fabrication gate** (`engine.signal_ok`, fail-closed, TDD-locked): empty `fact`
→ reject; `family == external` without `url` or `as_of` → reject. Spec Section K
becomes machine-enforced, not a prompt suggestion.

## Stages

| S | What | Files |
|---|---|---|
| 1 | Signal contract, 7 triggers, 2 new formats, novelty/mix engine, learn math — all PURE + TDD | `studio/engine.py`, `studio/learn.py`, `studio/db.py` (v3 schema), tests |
| 2 | External signals via Anthropic server-side `web_search` (same API key, no new vendor) — 4 streams D7–D10, each fact must carry a URL + date or it's dropped | `bot.py` (`claude_search`), `studio/external.py`, tests |
| 3 | Internal signal collectors from live Hostaway data | `studio/internal.py`, tests |
| 4 | Ideas from ANY signal + 50-hook bank + strength scoring + manual input | `studio/ideas.py`, `studio/hooks.py`, `studio/playbook.py` |
| 5 | Daily plan / calendar (3/day, balanced, novelty-guarded) + instant idea | `studio/plan.py` |
| 6 | UI rebuild: signal feed, today's 3, week calendar, manual box, learn panel | `studio/routes.py` |
| 7 | Wire into `bot.py`, daily loop, verification, ONE push | `bot.py` |

## Non-negotiables carried from CLAUDE.md
- `studio/routes.py` page HTML is a normal triple-quoted string → **ZERO backslashes**
  in the embedded JS (`String.fromCharCode(10)` for newlines). esprima-parse after edits.
- brain.db rules: no WAL, `closing(connect())`, additive ALTER migrations only.
- Additive + reversible: studio failing must never take the bot down.
