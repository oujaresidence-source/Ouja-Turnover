# Pricing Lab (مختبر التسعير) — Stage 1 Audit & Implementation Plan

> Phase 1: Ouja's own Hostaway data only · manual apply only · never auto-write ·
> immutable baseline · sync-verified apply/revert · full audit. Sits **beside** the old
> pricing tab (additive, reversible).

## A. What already exists (audited in `bot.py`)

### Pricing views / nav
- `view_pricing` (id `pricing`, ~L11895) + `view_strat` (id `strat`, ~L11941) + hash page
  `#apartment/<lid>` (`_api_apartment`, `/api/apartment/{lid}`). NAV at ~L14050/14074,
  categories `NAV_CATS` `cat_pricing` ids `['pricing','strat','rev','quote']` (~L14121).

### Engine (`_pe_*`, all reusable — read-only consumption)
- `_pe_build_dataset` (L24043) · `_pe_band` (L24130) · `_pe_resolve_band` (L24229) ·
  `_pe_group_key` (L24001) · `_pe_lead_bucket` (L23995) · `_pe_date_type` (L24023, uses
  `SAUDI_EVENTS`) · `_pe_learn_models` (L24143) · `_pe_reco_for_night` (L24255) ·
  `_pe_get_recs` (L24424) · `_pe_night_detail` (L24847) · `_pe_options` (Safe/Balanced/Push,
  L24830) · `_pe_compute_recommendations` (L24359) · `_pe_backtest` (L25393).
- Constants: `PE_MIN_UNIT`=8, `PE_HORIZON`, `PE_POOL_STRETCH`, `_pe_floor_overrides`
  (**manual floor already exists**), `pe_lean`/`set_pe_lean`.

### The SAFE writer (reuse — do NOT rewrite)
- `_pe_apply_night(lid, date, price, source, reason, old)` (L24993):
  - honors `PRICE_APPLY_DRYRUN`;
  - **reads the live price BEFORE writing** (`api_get /listings/{lid}/calendar`);
  - writes via `api_put /listings/{lid}/calendar {startDate,endDate,isAvailable:1,price}`;
  - **reads back after write** (`chk = api_get …`) → computes `confirmed`;
  - logs to learning log + `log_price_change`. → **Sync verification already lives here.**

### Baseline (exists, but UNSAFE for a true revert)
- `_pricing_baseline` (`pricing_baseline.json`) `{ "lid|date": {baseline, ouja_wrote, ts} }`.
- `_pe_baseline_observe` (L24657) freezes live on first sight; **refreshes `baseline` whenever
  live ≠ `ouja_wrote`** (external change). `_pe_baseline_record_write` (L24681).
- **Why unsafe:** (1) `baseline` is **mutable** and gets overwritten by external changes, so it
  is "last external price," not the immutable original before Ouja first touched the night;
  (2) it is a **single value per (lid,date)** — no per-apply history, no revert-to-exact-prior.
  A polluted baseline → revert sends the price to the wrong value. The Hostaway note
  `ouja-orig:<n>` (L1058) is only a last-minute-discount helper, not a reliable source.

### Central audit + endpoints
- `log_price_change(lid,date,old,new,source,reason,dry,confirmed)` (L24507) → append-only
  `price_change_log.json`. Reuse for every Lab apply/revert.
- Pricing endpoints (L33378+): `/api/pricing`, `/api/pricing2/{recs,night,apply}`,
  `/api/pricing/{changelog,strategy-toggles,month-preview,apply-month,analytics,apply-unit,
  activate,lean,bulk,…}`, `/api/strategies`, `/api/apartment/{lid}`. **All stay unchanged.**

### Saudi context (reuse)
- `SAUDI_EVENTS` (L1299) + `_events_combined` (L1324). Salary-cycle crunch in the revenue
  report (`_crunch`, L24242/34296): arrivals-per-day-of-month, weak/strong windows.

## B. Plan — reuse / replace / new

**Reuse (no rewrite):** calendar `api_get`/`api_put`; `_pe_apply_night` (wrap it);
`log_price_change`; `_pe_band`/`_pe_resolve_band`/`_pe_group_key`/`_pe_lead_bucket`/
`_pe_date_type`/`_pe_learn_models`/`_pe_reco_for_night`/`_pe_options`; `_pe_floor_overrides`
(manual floor); `SAUDI_EVENTS`/`_events_combined`; `CONFIRMED_STATUSES`/`_REPORT_CANCELLED`;
dashboard tokens, drawer/`t()`/`NAV`/`go()` patterns.

**New (`_plab_*` namespace, additive):**
- Data: `_plab_dataset()` (Stage 3) · `_plab_salary()` (Stage 4) · `_plab_apartment(lid)`
  (Stage 5) · `_plab_comparables(lid)` (Stage 7) · `_plab_recommend(lid)` 45-day (Stage 8) ·
  `_plab_ladder(lid,date)` (Stage 9) · `_plab_outcomes()` (Stage 14) ·
  `_plab_decision_board()` (Stage 15).
- Profile + score: `pricing_unit_profiles.json` + `_plab_unit_score()` (Stage 6).
- **Immutable safety:** `pricing_lab_snapshots.json` (Stage 10) — append-only, captures
  `original_hostaway_price` read live BEFORE the first write, **never overwritten**.
- Apply/Revert (Stage 11/12): `_plab_apply()` = snapshot → `_pe_apply_night` → store
  `requested/verified/apply_status`; `_plab_revert()` = write snapshot's
  `original_hostaway_price` back → read-back verify → status. Both `log_price_change`.
- Settings: `pricing_lab_settings.json` (Stage 16) — salary window 27→1, horizon 45,
  own-vs-comparable weight, min-data threshold, per-apartment manual floor (routes to
  `_pe_floor_overrides`).
- UI: new tab `view_plab` (`plab`) under `cat_pricing`, 6 sub-views (Decision Board /
  Apartment Lab / 45-Day Calendar / Unit Profile / Apply&Revert Log / Saudi Settings),
  `loadPlab()`+sub-loaders, i18n keys in BOTH `T.ar`/`T.en`.

**Backwards-compatible (must remain):** old `view_pricing`/`view_strat`/`#apartment` and ALL
`/api/pricing*` endpoints unchanged; `_pe_*` engine unmodified (Lab consumes it); DRYRUN honored.

**State files added:** `pricing_lab_cache.json`, `pricing_unit_profiles.json`,
`pricing_lab_snapshots.json` (source of truth), `pricing_lab_settings.json`
(+ outcomes folded into snapshots). All via existing `_load_json`/`_save_json`/`persist_state`.

## C. Safety invariants (enforced every stage)
1. No automatic Hostaway writes — apply/revert are explicit, scoped, confirmed.
2. `original_hostaway_price` captured once (live read before first write) → immutable.
3. Revert uses the snapshot original, never the current/changed price.
4. Every apply AND revert reads the Hostaway calendar back and shows true sync status.
5. Failed sync never shows success. No faked numbers. Thin data → "low confidence" shown.
6. Recommendations never below manual floor; every rec carries a reason (AR+EN).

## D. Verification plan (Stage 18 — CLAUDE.md routine)
`rm -rf __pycache__ && py_compile` · `pyflakes` · esprima every `<script>` · `{}`/`()` balanced,
backticks even · i18n parity for every new key (both langs) · **no backslash escapes in the
embedded JS** (`String.fromCharCode(10)` for newlines). Synthetic: realized ADR excludes
cancelled/inquiry · salary window classifies 27–1 · lead buckets correct · unit score with
missing fields · comparables not bedroom-only · recs respect floor · low-data→low-confidence ·
apply writes snapshot BEFORE Hostaway · apply/revert read-back status · revert uses snapshot
original · failed sync ≠ success · outcome marking.

## E. Stage commits (push ONCE at the very end)
S1 audit (this file) → S2 nav → S3 dataset → S4 salary → S5 apartment lab → S6 profile →
S7 comparables → S8 reco → S9 ladder → S10 snapshots → S11 apply → S12 revert → S13 log →
S14 outcomes → S15 decision board → S16 settings → S17 polish → S18 verify + push.
