# Same-day price keeper «حارس سعر الليلة» — design

Date: 2026-11-02 · Owner-approved in chat (Parts 1–3) · Replaces the one-shot 3/6/8 PM ladder (4c4d528 + 936eaf9)

## Why

The live ladder works but has five holes, all seen or provable on 1–2 Nov:

1. **Hidden, jumping floor.** `_lm_floor_for` = max(global, manual, DNA cell floor / tier_min). On 1 Nov
   (right after the 18:22 deploy) A5 MLQ was allowed to 418; on 2 Nov it was held at 572 — above its
   weekday median of 530. The owner cannot see this number and it is not the Hostaway «Min price».
2. **No retry.** A step is marked done even when units hit `api_error` or `not_confirmed`.
3. **Restart loses a step.** Catch-up only covers 90 min after each fire time.
4. **Pending units are skipped once and never revisited.**
5. **No daily report.** `post_discount_summary` posts only changed units, per step; nothing says what was
   skipped, what got booked, or what it earned.

## Owner decisions (2026-11-02)

| Question | Answer |
|---|---|
| Minimum price | Lowest price each apartment actually sold at for the same night |
| Report time | 12 AM — right after the window closes |
| Failures | Retry every 5 min; ping only if still not dropped after 30 min |
| Approach | A — a self-checking keeper (desired state), not patched one-shot steps |

## Part 1 — the keeper

**Loop:** one `@tasks.loop(minutes=5)`; acts only 15:00–23:59 Riyadh for tonight
(`pricing_target_date_riyadh`). All Hostaway calls run in `asyncio.to_thread` (see the
discord-loop-freeze lesson).

**Step now:** `<15:00 → 0` · `15:00–17:59 → 10%` · `18:00–19:59 → 20%` · `20:00–23:59 → 30%`.
Hours/percents keep the existing env names `LM_STEP{1,2,3}_{HOUR,PERCENT}`.

**Per unit, per tick:**
1. Skip (no write, no retry): global last-minute toggle off, `lm_unit_enabled(lid)` false,
   `is_unit_skipped(lid)`, discounts paused.
2. Read tonight's calendar day. Booked / blocked / no price → done for tonight.
3. Pending guest (`_pending_lids_for_date`) → wait; re-check next tick.
4. `original` = existing `_lm_baseline` (state → `ouja-orig:` note → price log → current price).
5. `target = max(round(original × (1 − step%)), minimum)`.
6. `current <= target` → nothing to do (never raise a price someone set lower).
7. Otherwise PUT `{price: target, note: "ouja-orig:<original>"}`, read back. Not stuck → retry next tick.

**Call budget** (Hostaway rate-limit lesson, ~12 calls/min ceiling): a unit confirmed at the
current step's target is not re-read until the next step boundary. Expected ≈ 3 calls × ~50 units ×
3 steps per evening, plus retries — the same burst shape as today, through the existing throttle.

**Minimum price ("lowest that sold"):**
- Rebuilt once a night (and on boot if missing) from `fetch_reservations_window(today−180, today)` —
  never `get_reservations_cached()` (CLAUDE.md trap #4).
- A booking is "same-night" when its `reservationDate` (UTC → +3h Riyadh) falls on its `arrivalDate`.
  Confirmed statuses only (`new`/`modified`).
- Nightly price = (`totalPrice` − `cleaningFee` − tax) ÷ `nights`.
- Per unit: drop prices below 50% of that unit's same-night median (data errors / family stays), then
  `minimum = lowest remaining − 10%` (`LM_MINIMUM_MARGIN`). Owner decision 2026-11-02 after the
  backtest: the bare lowest gave F2 a 908 minimum although it sold at 608 after the drop on 1 Nov
  (HUE 202: 467 vs 304) — it would block, and never learn, cheaper sales. The −30% ladder still
  bounds every drop.
- Fewer than 5 same-night bookings → no sold-minimum (the unit may go the full −30%).
- An owner-set manual floor in the dashboard (`_pe_floor_overrides`) still wins if it is higher —
  it is the owner's explicit choice. The DNA/tier_min floor is **not** used by the keeper.
- Saved to `$STATE_DIR/lm_minimums.json` with the sample size, so the report can show it.

**Removed:** `discount_tier1/2/3_loop`, `discount_weekend_loop`, `discount_catchup_loop` and the
"step done" flags for scheduling. `apply_discount_tier` stays for any manual dashboard trigger.
The `#pricing-log` per-step embed is replaced by the nightly report.

## Part 2 — 12 AM report + alerts

**When/where:** 00:00 Riyadh, for the night that just ended, in `#pricing-log` (`DISCOUNT_CHANNEL`).
Arabic-first. Saved to `$STATE_DIR/lm_reports/<date>.json` for accounting.

**Sections:**
1. 📉 Empty at 15:00 / reached by a drop
2. ✅ Booked after the drop — unit, booking time, price paid, price before drop, step at booking;
   totals: income and discount given. A booking counts only if made **after** that unit's first drop
   write that day.
3. 🏠 Still empty at midnight — final price and its minimum (shows where the minimum stopped it)
4. ⚠️ Didn't drop, and why — paused, pending all evening, Hostaway error, minimum ≥ price
5. 📊 This week (Sun–Sat): same-day bookings made after 15:00 vs target 43 (baseline 37)

**Alert:** an empty, eligible unit whose price is still above target 30 min after the step began →
one Discord ping to the owner. Max one ping per unit per night.

## Part 3 — testing + going live

- Tests (`tests/test_lm_keeper.py`, fake Hostaway, no network):
  restart mid-evening still converges · failed write fixed next tick · pending unit drops after
  the guest resolves · minimum stops the drop · price never raised · booked unit untouched ·
  step boundaries 14:59/15:00/17:59/18:00/19:59/20:00 · minimum builder (same-night detection,
  UTC→Riyadh, outlier cut, <5 samples → none) · report attribution (13 JOOD 17:22 = not ours) ·
  one alert per unit per night.
- Full CLAUDE.md verification routine; existing `tests/test_lm_ladder.py` updated.
- Built in the `ouja-wt-lmladder` worktree on a new branch; nothing live changes until tests pass and
  the owner OKs the push to `main`.
- First night: check the 12 AM report with the owner.
- Off switch unchanged: `LM_DRY_RUN=1` on Railway, or the dashboard pause.

## Out of scope

Changing Hostaway's own «Min price» column (the owner is reviewing it by hand); Thu/Fri extra step
(stays off); any change to future-night pricing strategies.
