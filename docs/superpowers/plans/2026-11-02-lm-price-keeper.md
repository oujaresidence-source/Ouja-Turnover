# Same-day Price Keeper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-shot 3/6/8 PM ladder with a 5-minute self-correcting keeper, a "lowest that sold" minimum, a 12 AM Discord report and a 30-minute stuck alert.

**Architecture:** All decisions live in a new PURE module `lm_keeper.py` (no bot import, no network) so they are unit-testable. `bot.py` only wires I/O: one `@tasks.loop(minutes=5)` that runs `lm_keeper_tick` in a thread (Hostaway reads/writes), sends the 12 AM report once per night and pings once per stuck unit. State lives in `$STATE_DIR/lm_keeper.json` and `lm_minimums.json`.

**Tech Stack:** Python 3, discord.py `tasks.loop`, Hostaway public API via existing `api_get`/`api_put`, unittest (no pytest).

**Spec:** `docs/superpowers/specs/2026-11-02-lm-price-keeper-design.md`

## Global Constraints

- Steps: 15:00 −10% · 18:00 −20% · 20:00 −30% (env `LM_STEP{1,2,3}_{HOUR,PERCENT}`, already parsed into `DISCOUNT_TIER*`).
- Window 15:00–23:59 Riyadh; target night = `pricing_target_date_riyadh(now)`.
- Never raise a price. Never touch a booked/blocked night.
- Minimum = max(sold-minimum, `_pe_floor_overrides[lid]`, `DISCOUNT_FLOOR`). The DNA/tier_min floor is NOT used.
- Sold-minimum: same-night bookings (reservationDate UTC+3 date == arrivalDate), last 180 days, confirmed (`new`/`modified`), accommodation-only nightly (strip `cleaningFee`,`totalTax`,`cityTax`,`securityDepositFee`), drop < 50% of the unit median, need ≥ 5 samples else no minimum.
- Reservations come from `fetch_reservations_window` — never `get_reservations_cached()` (CLAUDE.md trap #4).
- Hostaway calls only inside `asyncio.to_thread` (discord-loop-freeze lesson).
- Report: once per night, first tick at/after 00:00, `#pricing-log` (`DISCOUNT_CHANNEL`), Arabic, ≤1,900 chars per message.
- Alert: one ping per unit per night, when an eligible empty unit is still not at target ≥ 30 min (`LM_ALERT_AFTER_MIN`) after its step began. Mention = `LM_ALERT_MENTION` else `FINCHAT_OWNER_MENTION`.
- Dry-run (`LM_DRY_RUN=1`): compute + record "would write", never PUT, never mark a unit confirmed.
- No backslash-escape traps apply (no DASHBOARD_HTML edits).

---

### Task 1: Pure rules — step, target, decide

**Files:**
- Create: `lm_keeper.py`
- Test: `tests/test_lm_keeper_rules.py`

**Interfaces — Produces:**
- `step_pct(now: datetime, steps: list[tuple[int, float]]) -> float`
- `step_started_at(now, steps) -> datetime | None`
- `target_price(original: float, pct: float, minimum: int = 0) -> int`
- `decide(day: dict, original: float, pct: float, minimum: int, pending: bool) -> dict` with keys
  `action` ∈ {`booked`,`wait_pending`,`hold`,`write`}, `target`, `current`, `floor_blocked`.

- [ ] Step 1: write tests — boundaries 14:59→0, 15:00→10, 17:59→10, 18:00→20, 19:59→20, 20:00→30, 23:59→30;
  `target_price(431,30)==302`, `target_price(431,30,350)==350`; decide: booked row → `booked`; pct 0 → `hold`;
  pending → `wait_pending`; current 431 pct 10 → `write` 388; current 300 orig 431 pct 20 → `hold` (never raise);
  minimum 400 orig 431 pct 30 current 400 → `hold`, `floor_blocked` True.
- [ ] Step 2: run `python3 -m unittest tests.test_lm_keeper_rules -v` → FAIL (no module).
- [ ] Step 3: implement (code in `lm_keeper.py`, section "step/target/decide").
- [ ] Step 4: run → PASS. Step 5: commit `feat(lm-keeper): pure step/target/decide rules`.

### Task 2: Pure rules — "lowest that sold" minimum

**Files:** Modify `lm_keeper.py`; Test `tests/test_lm_keeper_rules.py`

**Interfaces — Produces:**
- `booked_at_riyadh(res: dict) -> datetime | None` (reservationDate "YYYY-MM-DD HH:MM:SS" UTC → +03:00)
- `nightly_price(res: dict) -> float | None`
- `is_same_night(res: dict) -> bool`
- `build_minimums(reservations: list[dict], min_samples: int = 5) -> dict[str, dict]` → `{lid: {"min","n","median"}}`

- [ ] Step 1: tests — 2026-11-01 17:39:00 UTC → 20:39 Riyadh same night for arrival 2026-11-01;
  21:30 UTC on 11-01 → 00:30 on 11-02 → NOT same night for arrival 11-01; fees stripped
  (total 774.18, cleaning 0, totalTax 100.98, nights 2 → 336.6); outlier 100 among [400..520] dropped;
  4 samples → no entry; cancelled ignored.
- [ ] Step 2: run → FAIL. Step 3: implement. Step 4: PASS. Step 5: commit `feat(lm-keeper): sold-minimum builder`.

### Task 3: Pure rules — report

**Files:** Modify `lm_keeper.py`; Test `tests/test_lm_keeper_rules.py`

**Interfaces — Produces:**
- `night_bookings(reservations, night: str, units: dict[str, dict], steps) -> list[dict]`
  (each: `lid,name,booked_at,price,total,orig,pct,from_drop`)
- `week_start(d: date) -> date` (Sunday on/before d)
- `week_count(reservations, start: str, end: str, after_hour: int = 15) -> int`
- `render_report(night, units, bookings, week, target=43, baseline=37) -> str`
- `chunk(text: str, limit: int = 1900) -> list[str]`

- [ ] Step 1: tests — the real night of 2026-11-01: F2 20:39, E5MLQ 20:50, HUE 202 20:50, 1 MLQ 21:30
  with first drop at 20:00 → 4 `from_drop`; 13 JOOD 17:22 with no drop → not from drop; report text
  contains "انحجزت بعد النزول: 4" and the week line; `week_start(date(2026,11,2)) == date(2026,11,1)`;
  `chunk` keeps every line and each piece ≤ limit.
- [ ] Step 2–4: FAIL → implement → PASS. Step 5: commit `feat(lm-keeper): nightly report rules`.

### Task 4: bot.py — keeper tick + minimum refresh

**Files:** Modify `bot.py` (new block after `discount_catchup_loop`, ~line 6790; `import lm_keeper` near the
other top-level imports); Test `tests/test_lm_keeper_bot.py`

**Interfaces:**
- Consumes: Task 1–2 functions; `api_get`, `api_put`, `get_listings_map`, `lm_unit_enabled`,
  `is_unit_skipped`, `is_discount_paused`, `_pending_lids_for_date`, `_lm_orig_from_note`,
  `_lm_baseline_from_log`, `_pe_floor_overrides`, `DISCOUNT_FLOOR`, `DISCOUNT_DRY_RUN`,
  `fetch_reservations_window`, `log_price_change`, `_load_json`, `_save_json`.
- Produces: `lm_keeper_steps()`, `lm_minimums(now, refresh=False) -> dict`, `lm_keeper_tick(now) -> dict`
  (tonight's record `{"units": {lid: {...}}, ...}`), state file `lm_keeper.json`.

Per-unit record fields: `name, seen_empty, orig, minimum, current, final, pct, confirmed_pct, status
(ok|booked|waiting|error|skipped|dry_run), reason, first_drop_at (iso), writes [[iso, price, pct]], alerted`.

- [ ] Step 1: tests with a FakeHostaway (pattern of `tests/test_lm_ladder.py`): restart mid-evening converges
  (20:30, fresh state, price 431 → 302); failed PUT then fixed next tick; pending unit waits then drops;
  minimum stops at 350; already-lower price untouched; booked untouched; confirmed unit not re-read in the
  same step (GET count); dry-run never PUTs and never confirms; unit toggle off → skipped.
- [ ] Step 2–4: FAIL → implement → PASS. Step 5: commit `feat(lm-keeper): 5-minute self-correcting tick`.

### Task 5: bot.py — loop, 12 AM report, 30-min alert, retire old loops

**Files:** Modify `bot.py` (keeper block; startup list ~76890–76927); Test `tests/test_lm_keeper_bot.py`

**Interfaces — Produces:** `lm_keeper_loop` (`@tasks.loop(minutes=5)`), `lm_report_text(night) -> str`,
`lm_due_alerts(rec, now) -> list[dict]`.

- [ ] Step 1: tests — `lm_due_alerts`: unit `error` at 15:31 → due; same unit again → not due (alerted);
  at 15:20 → not due; booked/ok → never. `lm_report_text` with a fake `fetch_reservations_window` returns
  text with the night's bookings.
- [ ] Step 2–4: FAIL → implement → PASS.
- [ ] Step 5: startup: start `lm_keeper_loop` (guarded by `_loop_guard`); stop starting
  `discount_tier1/2/3_loop`, `discount_weekend_loop`, `discount_catchup_loop` (definitions stay, unstarted).
- [ ] Step 6: commit `feat(lm-keeper): loop + 12 AM report + stuck alert; retire one-shot steps`.

### Task 6: Verification

- [ ] `rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py lm_keeper.py`
- [ ] `python3 -m pyflakes bot.py lm_keeper.py finance/*.py | grep -v "imported but unused"` → no new findings
- [ ] `node --check finance/static/erp.js`
- [ ] `python3 -m unittest discover -s tests -p "test_*.py"` → no failures beyond the 3 known date-expired ones
  (test_ops_capture ×2, test_train_export ×1)
- [ ] esprima parse of every DASHBOARD_HTML `<script>` (untouched, but required by the routine)
- [ ] Report to owner; push to `main` ONLY after the owner's OK.
