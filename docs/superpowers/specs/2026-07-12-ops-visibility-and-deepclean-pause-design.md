# Design — Deep-Clean Pause + On-Demand Ops Visibility Commands

**Date:** 2026-07-12
**Author:** Faisal + Claude
**Status:** Approved for planning

Three small, independent, additive changes to the live Ouja Residence bot (`bot.py` +
subpackages). Nothing here rewrites existing systems; every piece is built on helpers and
data that already exist. All work follows the repo verification routine before push.

---

## Feature ① — Pause the deep-clean date-blocker + unblock its dates

### Problem
`confirm_tomorrow_deepcleans()` (`bot.py:2255-2293`) runs nightly at 9pm Riyadh and blocks
tomorrow's calendar date in Hostaway for any apartment due a deep clean, via
`PUT /listings/{id}/calendar {isAvailable:0, note:"deep-clean"}` (`bot.py:2284-2286`). The
owner wants this **paused now** and every date it already blocked **freed** — touching
**only** dates this feature blocked.

### The load-bearing safety marker
Every deep-clean block carries the literal calendar note `"deep-clean"` (`bot.py:2286`). A
deep-clean block is uniquely identifiable as:

```
isAvailable == 0  AND  reservationId is empty/null  AND  note == "deep-clean"
```

A guest reservation has a `reservationId`; a manually-blocked date has a different/empty
note. This triple is the definitive discriminator. Second confirmation: the bot's own
`/data/deep_clean.json` state, where blocked units have `next_status == "blocked"` and a
`next_scheduled` date.

### Design

1. **Persisted global pause flag** — a new saved value `deep_clean_paused` (persisted like
   the existing `paused_units.json` / `dc_anchor.json` via `_save_json`/`_load_json` under
   `STATE_DIR`). It defaults to **paused = True** on this deploy (so the pause takes effect
   the moment the container restarts — no Railway env editing required by the owner).
   - Every deep-clean write/schedule entry point (`schedule_deep_cleans` `bot.py:2121`,
     `confirm_tomorrow_deepcleans` `bot.py:2259`, `deepclean_lookahead_check` `bot.py:2300`)
     gains an early `if _deep_clean_is_paused(): return`, in addition to the existing
     `DEEPCLEAN_ENABLED` check. Pause and the env kill-switch are independent; either one
     off = no blocking.

2. **One-time unblock sweep** — `unblock_all_deep_clean_dates()`:
   - Reads `/data/deep_clean.json` for units with `next_status == "blocked"` to get the
     candidate (listing_id, date) set (fast, no full calendar scan).
   - For each candidate, fetches that listing's calendar for that date window and confirms
     the day matches the safety triple (`isAvailable==0` + no `reservationId` +
     `note=="deep-clean"`) before writing.
   - Frees confirmed days with `PUT /listings/{id}/calendar {isAvailable:1}` and resets that
     unit's state to `unscheduled` (mirrors the existing `mark_deep_clean_done()`
     `bot.py:2490-2511`, which is the built-in single-unit undo).
   - Returns a structured report: `[{apartment, listing_id, date}], count, skipped`.
   - **Idempotent:** re-running is a safe no-op — once a day is `isAvailable:1` it no longer
     matches the triple.

3. **Trigger + resume controls:**
   - Runs **once automatically on deploy** while paused, guarded by a persisted
     `deep_clean_unblocked_once` marker so it doesn't re-sweep every restart. (Even if it
     did, it's idempotent.) Reports the freed list to the ops channel / log.
   - **Resume** later: a `POST /api/cleaning/resume-blocking` endpoint + a Discord command
     `!ouja deepclean-resume` (admin/ops only) that clears the pause flag. A matching
     `!ouja deepclean-pause` re-pauses + re-sweeps on demand.

### Pure logic to TDD-lock
`_deep_clean_block_eligible(day_obj) -> bool` — given one Hostaway calendar-day dict, returns
True iff it matches the safety triple. Unit tests: guest booking (has reservationId) → False;
manual block (note != "deep-clean") → False; available day → False; true deep-clean block →
True; missing/empty note → False.

### Owner-facing behavior
On the next deploy the blocker is off and the owner receives, in the watchdog channel, a
plain-language message: "Deep-clean auto-blocking is paused. Freed N dates: …" with the list.

---

## Feature ② — `/update` : today's check-ins at a glance

### Command
- Slash `/update` (paired prefix `!ouja update`, Arabic alias `!ouja الوصول`), registered
  next to existing command defs (~`bot.py:52106`); picked up by the existing `on_ready`
  `bot.tree.sync` (`bot.py:54609-54617`) automatically.
- Gated to admin/ops (reuse existing role check). Defers, builds, then replies **ephemerally
  to the caller AND posts to the watchdog channel `غرفة-المراقبة`**.

### Data (all pre-existing)
- Today's arrivals: `compute_arrivals_with_status(...)` (`bot.py:2602-2649`), called with a
  window covering today's calendar day in Riyadh (the watchdog's `window_hours=36,
  lookback_hours=4` is a working reference; the plan will pin the exact values so the set is
  precisely "checking in today") → per-arrival `guest, unit, listing_id, checkin_label,
  signed, conversation_id, nights, …`.
- Cleaned/ready: `_wd_cleaning_ok(...)` (`bot.py:53963`).
- Door code sent: `_watchdog.engine.classify_code_send(msgs)` on the arrival's conversation
  (same detection the watchdog uses).
- Agreement: `signed` field already returned; combined with `_unit_requires_agreement(lid)`
  (`bot.py:1668`) to distinguish **not signed** from **not needed**.

### Output (Arabic-first, phone-friendly), one block per check-in
```
🏠 Ouja | <apartment> — <Guest> — 🕐 <check-in time>
🧹 نظّفت: ✅/❌   ·   🔑 الكود: ✅/❌   ·   📝 العقد: موقّع / غير موقّع / لا يحتاج
```
Empty state: a plain "ما فيه تسجيلات دخول اليوم" line. Header shows the count + date.

### Pure logic to TDD-lock
`render_update(arrivals) -> str` — pure renderer over a list of assembled arrival dicts.
Tests: the three agreement states render correctly; empty list → empty-state text; ordering
by check-in time; ✅/❌ mapping.

---

## Feature ③ — `/guests` : in-house guest mood summary (Claude API)

### Command
- Slash `/guests` (paired prefix `!ouja guests`, Arabic alias `!ouja الضيوف`), same
  registration + role gating as `/update`. Defers (work is a few seconds), then **ephemeral
  reply to caller AND post to `غرفة-المراقبة`**.

### Data flow
1. Enumerate current guests: `fetch_inhouse(today)` (`bot.py:26172`) → one row per occupied
   unit (guestName, listingMapId, reservation id).
2. For each guest, resolve the conversation (match `reservationId`/`listingMapId` against
   `/conversations`, reusing the `_conv_to_item` mapping shape `bot.py:6753`) and fetch
   messages via `api_get(f"/conversations/{cid}/messages")`.
3. Classify with **Claude Haiku** (`claude_json(system, user, model=CLAUDE_MODEL)`
   `bot.py:6315`), one call per guest, run **concurrently** (`asyncio.gather` +
   `asyncio.to_thread`, capped with a semaphore, e.g. 6, to respect rate limits). Prompt
   returns strict JSON: `{"mood": "happy|normal|sad", "issue": "<≤1 line, empty if none>"}`.
4. "Solved or not" is **not** guessed by the model — it's read from the existing promises
   ledger (`promises.db.list_rows` / `open_rows()`; `status` in `open|done|expired`) keyed by
   the guest's `conversation_id`. If a guest has an open promise/issue → "still open"; if all
   done / none → "solved" / no issue.

### Output (Arabic-first), one block per guest
```
🙂/😐/☹️ <Guest> — Ouja | <apartment>
      (only when sad/upset:) ⚠️ المشكلة: <one line>   ·   الحالة: ✅ تم الحل / ⏳ لسه مفتوحة
```
Header: happy/normal/sad counts. Empty state: "ما فيه ضيوف حاليًا".

### Cost / latency
Haiku, concurrent, in-house only (bounded set, typically ≤ ~50). Deferred interaction so
Discord never times out. Failure of one guest's classification degrades gracefully to
😐 normal + a note, never blocks the whole summary.

### Pure logic to TDD-lock
`render_guests(rows) -> str` — pure renderer over assembled `{guest, apartment, mood, issue,
resolved}` dicts. Tests: sad guest shows issue + status; happy/normal hide the issue line;
mood→emoji mapping; counts in header; empty → empty-state text. (The Claude call itself is
mocked in tests; only the deterministic assembly + rendering is asserted.)

---

## Cross-cutting

- **Where code lives:** small additions in `bot.py` for the three commands + the deep-clean
  pause/unblock; pure renderers/eligibility either as local helpers in `bot.py` or (preferred
  for `/update` + `/guests` render + code classification reuse) alongside the watchdog engine
  so they're import-testable. Final placement decided in the implementation plan.
- **No new heavy dependencies.** Reuses `api_get/api_post/api_put`, `claude_json`,
  `fetch_inhouse`, `compute_arrivals_with_status`, watchdog engine, promises db.
- **Verification (mandatory before push):**
  `py_compile` → `pyflakes bot.py finance/*.py` → `node --check finance/static/erp.js` →
  `python3 -m unittest discover -s tests`. New tests: `test_deepclean_unblock.py`,
  `test_ops_commands_render.py` (or folded into an existing watchdog test module).
- **Live-safety:** deep-clean pause defaults on; unblock is idempotent + marker-gated; the
  two commands are **read-only** (no Hostaway writes) except the deep-clean unblock. Push
  triggers Railway redeploy — one clean push, no rapid re-deploys (per the known
  auto-send-spam lesson).

## Out of scope (YAGNI)
- No new dashboard tab/UI (commands are Discord-first; the watchdog page already exists if a
  button is wanted later).
- No historical mood trends / storage — `/guests` is a live snapshot.
- No changes to how Musaed replies, escalates, or to the agreement-signing flow itself.
- No permanent deletion of `DEEPCLEAN_ENABLED`; pause is an additive, reversible layer.
