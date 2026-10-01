# Permit tracker «التصاريح» — implementation plan

Spec: `docs/superpowers/specs/2026-10-01-permits-tracker-design.md`. Gates: `permits/GATES.md`.
Branch `feat/permits` in worktree `../ouja-wt-permits` (off `origin/main`). Every step is TDD:
the test file first (red), then the module (green), then a re-read.

## 0. Safety first
1. `.gitignore` += `permits/seed/source/`; commit it alone; copy the xlsx in; `git check-ignore`.
2. Record the full-suite baseline on untouched main → `permits/.baseline.txt` (G0) and write
   `permits/tools_compare_baseline.py` (G4).
3. Write `permits/GATES.md`, lint it, run every check once before code exists to prove it can fail;
   tighten any that pass on nothing (G2 needs the package, G3 needs ≥ 100 tests).

## 1. Pure core (no DB, no Discord)
4. `tests/test_permits_dates.py` → `permits/dates.py`: ISO / day-first / Arabic + Persian digits /
   Excel serial / datetime / Hijri (Umm al-Qura) / ambiguity flag / invalid / words_ar / to_hijri_str.
5. `tests/test_permits_engine.py` → `permits/engine.py`: `band()` (lead 10 / 2 / 45), `counts()`,
   `plan()` (≤ lead, live ticket, unknown, window, go-live sweep), `reminder_due`, `summary_due`,
   `reminder_mentions`, the card (25 fields / 1024 / 6000, no ID digits), the digest (all-clear line,
   blocks, ≤ 2000 per message, mentions only expired/urgent), header synonyms, `guess_date_columns`,
   `match_unit` (unique-or-nothing, hints), `cfg()` read at call time.

## 2. Storage + import
6. `permits/db.py`: the schema (partial unique index on live tickets, unique outbox ref, no unique
   permit_no), settings, events, outbox claim.
7. `tests/test_permits_importer.py` → `permits/importer.py`: CSV (utf-8-sig, cp1256), XLSX (header on
   row 3, hyperlinks via read_only=False), JSON; nothing dropped; needs_data; in-file duplicates both
   kept + flagged; existing numbers skipped unless «حدّث الموجود»; commit re-parses; ID columns →
   last 4, ID-shaped numbers elsewhere masked; onboarding read-only.
8. `tests/fixtures/permits/expected_seed.csv` (oracle) + `tests/test_permits_seed_real.py` →
   `permits/seed/build_seed.py` (+ the reviewed unit_mismatch list) → commit
   `permits_seed.normalized.json`; `permits/seed/seed.py` (`seed_if_empty`, `link_units`).

## 3. Orchestration
9. `permits/port.py` (DiscordPort contract) + `tests/permits_fakes.py` (FakePort with failure
   injection: fail_create / fail_exists / fail_post / crash_after_create / crash_before_card).
10. `tests/test_permits_service.py` (DryDefaultTest, OpenTest, RaceTest, FailureTest, ReminderTest,
    DigestTest, RenewTest, CancelTest, CorrectTest) → `permits/service.py`: mode, plan, would_open,
    open_ticket_row, enqueue_*, record_dry, reconcile (stale claims, stale opening → adopt +
    ensure_card, lost channels, never "can't check" = deleted), drain_outbox (claim, backoff, digest
    latch after success), tick, renew / cancel / update / claim / link / review_clear.

## 4. Web door
11. `permits/host.py`, `permits/routes.py` (core_* + `_safe` + `HOST.web_thread`; docs by id only;
    import preview/commit; export CSV; parse-date), `permits/__init__.py` (wire / bootstrap /
    register_routes).
12. `tests/test_permits_routes_gating.py`: every route gated, NAV_DEF + _USER_TABS, viewer 403 on
    writes, admin-only cancel/mode/review, typed word, docs cannot escape, no to_thread.

## 5. Dashboard
13. `permits/static/permits_tab.js` (banner, heartbeat, KPI filters, 12-month strip, table → phone
    cards, drawer with every field + actions, add / edit / renew / cancel / link / upload / review,
    import preview → commit, export, go-live drawer with the typed word). `node --check`.
14. bot.py DASHBOARD_HTML: the section, the ≤ 15-line zero-backslash loader stub, `go()` line, badge
    lines, `loadAll()` badge refresh, `__PERMITS_JS_V__` replacement.
15. `tests/test_permits_dashboard.py`: esprima on every script, stub source has no backslash,
    placeholder replaced, go()/badge wired, node --check, cleanup jobs ignore `ouja-permit:` rooms.
16. Browser check on a local test copy (desktop + 375 px), fix what only a browser shows.

## 6. Discord glue (bot.py, one banner block)
17. Import guard; NAV_DEF item + cat_ops + labels; read/write role rules; wiring in
    `start_web_server`; `_permits_caps`; `_PermitsDiscordPort` (spill via `_tk_make_channel`, adopt +
    ensure_card, exists raises on can't-check, close = note + disable buttons + lock + rename);
    `PermitTicketView` + renew modal + confirm (re-check at press) + cancel modal; `permits_loop`
    (5 min, persisted latches, `_loop_guard`, staggered start); `bot.add_view`; `/permits`.

## 7. Docs + verification
18. CLAUDE.md section + trap 2 fix; requirements `hijridate~=2.6`; this plan + the spec.
19. `permits/tools_smoke.py` (G11), `permits/tools_privacy_scan.py` (G13, with a planted positive
    control).
20. Fresh-subagent code review against the spec; fix findings; re-run every gate with `--reverify`;
    commit on the branch. Push only if `PUSH_AFTER_GATES = YES` (it is NO).
