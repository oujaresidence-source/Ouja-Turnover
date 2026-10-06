# «اجتماع المالك» — Owner Meeting Room · implementation plan

Spec: `docs/superpowers/specs/2026-10-06-owner-meet-design.md` (the spec wins). Gates: `owner_meet/GATES.md`.
Branch `feat/owner-meet`, worktree `~/ouja-wt-meet`, from origin/main `950c9ee`. Not pushed.
Baseline: `.unlazy-baseline-meet.txt` — 5,126 tests, 3 failures already on main.

**Rhythm for every slice:**
1. tests first (red)
2. code until green
3. re-read as a domain expert and replace the cheap parts
4. full routine (G1–G7)
5. screenshots + "what to click"
6. STOP for Faisal

A slice that turns out bigger than written here stops and comes back. It does not keep going.

## S0 — documents (this slice)

- [x] Worktree from origin/main; brief files placed in `docs/owner_meet/` and `tests/fixtures/owner_meet/`.
- [x] Baseline suite captured.
- [x] Every cap in spec §4 verified to exist on origin/main (file:line in the session notes).
- [x] Fixture facts measured independently from the TSV.
- [x] Spec, GATES.md (lint OK), this plan.
- [x] Faisal approved (2026-10-06): link-to-existing-ticket, tab admin-only, waterfall from «صافي الحجوزات» with no live Hostaway look, group A computed by the plan PDF's method and shown for one confirmation before 5 Nov.
- [x] The 3 baseline failures named; none touches owner statements or money (two ops_capture backfill tests with July-2026 fixtures outside the window, one Musaed training "days since" count).

## S1 — package skeleton, caps, snapshot money/trend/peers, group A (no UI) → G1–G8, G21, G22

Files: `owner_meet/{__init__,host,config,db,periods,money,engine(bands only),snapshot,jobs}.py`, `owner_meet/rules.seed.json`, bot.py `_owner_meet_caps()` + the wire block, `tests/test_owner_meet_{structure,money}.py`, part of `tests/test_owner_meet_engine.py` (bands).

1. `test_owner_meet_structure` first:
   - no `import bot`, no `to_thread`/`run_in_executor`, zero backslashes, py3.9 AST
   - no «مثال توضيحي», no `1.15`/`0.822`
   - no `create_task`/`tasks.loop`/scheduler
2. `test_owner_meet_money`, built on a synthetic fixture through the **real** `_finance_aggregate` path (the same harness style as the existing statement tests — find and reuse it, never mock the money):
   - 1 / 3 / 12 months
   - owner and unit level
   - `Decimal` to 0.01
   - waterfall reconciles or falls back
   - mgmt % from `terms_on` (change the term → the label changes)
   - degraded → `can_send` False
3. `periods.py`, `money.py`, `engine.peer_bands` / `percentile_label` / `fair_share`, `airbnb_import.parse` + `engine.promo_split` (group A, tested against the PDF's list).
4. `db.py` schema (all `meet_*` tables, `_ensure` once per path, `closing(connect())`).
5. `snapshot.build(meeting)`. It calls the caps and writes `{"owner","presenter","meta"}`, `schema_version=1`, `sha256`. `jobs.py`: 2-worker pool, progress dict.
6. bot.py: import guard, `_owner_meet_caps()`, the wire/bootstrap/register try-block (failure prints and leaves the bot unaffected). **No NAV/UI yet.**
7. Evidence for G22. A real-owner check can't run locally because there is no Hostaway key on this machine. The first time Faisal approves a deploy, a snapshot for one real owner is put beside «الملاك» for the same months. Until then G22 stays pending and is reported as pending — never claimed.

STOP: report M1 test output + the per-month table from the synthetic fixture.

**S1 log (2026-10-06):**
- Built: host / config / rules.seed.json / db / periods / money / engine / airbnb_import / snapshot / jobs, the bot.py import guard + `_owner_meet_caps()` + wiring block, and 3 test files (65 tests: engine 34, money 17, structure 14).
- Gates met with automatic evidence: G0 G1 G2 G4 G5 G6 G7 G8 G21 G30. G22 stays pending: a real-owner comparison needs the first approved deploy.
- Found while building, and fixed:
  - `finance.owners.terms_on` reads its base values from the registry record. The cap now passes the record, which is why it takes a lid and not an apartment name.
  - One failing month becomes a red line, not a dead build.
  - A stale (SWR) month becomes a yellow line.
  - A build interrupted by a restart is failed at boot.
  - Owner-facing ratios and money are rounded (no 17-digit floats).
- Gate honesty: G6's title had promised the NAV/role checks that only S2 can test. Those moved to G13/G15, and a new G30 covers S1's pure rules. G9 now points at S4's `test_owner_meet_actions`.

## S2 — presentation + presenter, chapters 1–6 → G13, G15, G16, G17, G23

Files: `owner_meet/{charts,texts,render,routes}.py`, `static/{stage,notes,owner_meet_tab}.js`, bot.py (NAV item + `cat_finance` + labels ar/en + role rules + `view_meet` section + stub + `go()` line + cache-buster), `tests/test_owner_meet_{routes,dashboard,charts,render}.py`.

1. Tests first:
   - routes gating
   - 404 sameness
   - rate limit
   - flag off → no routes
   - dashboard stub rules
   - chart determinism goldens
   - render < 1 s on a 12-month fixture
2. `charts.py`: bars, small occupancy chart, band row, waterfall, funnel pair, ring, sub-score bars. Each ends in `<title>` + a text alternative.
3. `render.py`: canvas 1280×720 + container-query scaling; chapters 1–6; empty states from `texts.py`. Thmanyah via `/meet/font/{name}` (allow-list).
4. `stage.js`: keys, F/B/N, BroadcastChannel, reduced motion. `notes.js`: sync + short-poll fallback + talking points + flags.
5. Tab: owner/unit/period pickers, «تجهيز الاجتماع» with progress, readiness list, past meetings.
6. Screenshots in the built-in browser: desktop 1280×720 for each chapter, phone 390 px, and the presenter window beside the stage.

STOP: screenshots + «افتح اجتماع المالك ← اختر مالك ← تجهيز ← عرض».

**S2 log (2026-10-06):**
- Built: texts / charts / render / routes, static/stage.js + notes.js + owner_meet_tab.js, the bot.py NAV item + labels + role rules + view_meet + stub + go() + cache-buster, and `_GRANT_ONLY_TABS` so no role default ever grants «meet».
- Tests: 4 new files (charts, render, routes, dashboard) + a fixture generator (`tests/owner_meet_fixture_build.py`) that builds the snapshots through the real statement path.
- Gates met: G3 G13 G15 G16 G17 (and every S1 gate re-verified). G23 is pending Faisal's review of the screenshots.
- Screenshots are of SYNTHETIC data (no Hostaway key on this machine, and no deploy by Faisal's ruling). A real unit needs the first approved deploy.
- Found while building, and fixed:
  - The monthly and peers chapters overflowed the 16:9 canvas.
  - A season label collided with the value labels.
  - A zero expense showed «−0».
  - Number + Arabic unit inside one LTR box reversed «4.75 من 5». Now only the number is isolated.
  - The progress bars animated `width`; they now use `transform`.
  - Em-dash saturation in the notes window.
  - The stage ignored a hash change.
  - The new tab would have been granted by role defaults to every future non-admin user.
  - The loader stub sat inside reviewask's measured stub region.
  - Two older tests (page_permissions, reviewask_bot) caught those last two; both are fixed in the code, not in the tests.
- Learned: headless Chromium (playwright) works under the local Python 3.9, so G18/G19 can run locally in S5 (CHECK uses OUJA_PY313 to pick the interpreter).

## S3 — chapters 7–10 + privacy → G11, G12, G24

Files: `owner_meet/{ops,redact,privacy}.py`, `render.py` (chapters 7–10), `tests/test_owner_meet_{ops,privacy}.py`, fixtures with planted names/phones/codes/staff.

1. `test_owner_meet_privacy` first. The **positive control** plants each leak class and asserts the scanner sees it.
2. `ops.py` joins, per spec §7 rows 7–10:
   - maintenance via `dash_id`
   - RR via `lid` or `unit`
   - `_rr_ar_texts` frozen at build time
   - reviews > 0 only
   - reviewask follow-ups
   - recovery
   - price actions (non-dry, weekly counts)
   - permit
   - directpay
   - cleaning feedback
3. `redact.py` runs on every free-text field. `privacy.scan` runs on the owner HTML at render AND at send (fail closed).

STOP: screenshots of 7–10 on a unit that has tickets, a claim and reviews.

**S3 log (2026-10-06):**
- Faisal's S2 review: «كويسه الصور» + the data colour changed from blue to Diriyah mud brown (#8B5A3C / soft #EBDCCB). The chart golden test caught the change, and the goldens were then refreshed on purpose.
- Built:
  - `ops.py`: maintenance deduped by dash_id, purchases, claims + recovery ring + AirCover deadline, reviews + sub-scores + private feedback kept apart, and the unit log.
  - `redact.py`: script-aware name boundaries, Arabic prefixes «و/ل/ب…».
  - `privacy.py`: a fail-closed scan; a hit becomes a red readiness line that blocks send.
  - Chapters 7–10 with continuation slides, so every review and ticket is shown.
  - 14 read-only bot caps over `_dtk`, `_tickets`, `_price_log`, reviewask, recovery, directpay, permits, cleaning feedback and staff names.
- Tests: `test_owner_meet_ops`, `test_owner_meet_privacy`. The fixture PLANTS a guest full name + phone in a ticket, a reservation code in a claim, staff names everywhere, and a staff first name inside a review.
- Gates met: G11 G12 (+ all earlier gates re-verified, 18 met).
- Found by the planted data and fixed:
  - A guest's full name in a dashboard ticket title leaked: guests were collected from reservations only.
  - «وKhalid» and «ولنورة» slipped past word boundaries.
  - Emoji in RR type labels.
  - An English dashboard category.
  - Bidi jumbles: review header, AirCover line, block-level numbers drifting off their labels.
  - Score-bar numbers sat on the bars.
  - The ★ glyph was replaced by «4 من 5».

## S4 — Airbnb importer + mapping + action engine + chapters 11–12 → G9, G10, G21, G25

Files: `owner_meet/airbnb_import.py`, `engine.py` (headline, actions, forecast, discount stack), `render.py` (chapters 6 funnel data, 11, 12), tab import UI, `tests/test_owner_meet_{import,engine}.py`, an XLSX fixture generated in-test from the TSV.

1. Import tests on the real TSV:
   - 42 / rank 8 absent / 8 blank / USD 896,734 / 4.815 / 15
   - XLSX round-trip
   - malformed → Arabic refusal
   - snapshots never overwrite
2. Mapping:
   - `airbnb_room_id(lid)` first
   - then title suggestion
   - admin confirm stored
   - unmapped listed
3. Engine tests for every trigger, the forecast math and the cap.
4. (No extended waterfall in this version — Faisal 2026-10-06. Nothing is deployed to look at Hostaway data.)
5. Verify the min-price store for the `floor` action (spec §14 item 5) and record the answer here.

STOP: the real report imported + mapping screen + chapters 11–12.

**S4 log (2026-10-06):**
- The min-price store (spec §14 item 5) exists: `_pe_floor_overrides` {lid: SAR floor}, the pricing engine's per-unit floor. The `floor` action fires only when a unit has none.
- The Airbnb id of each unit comes from the guest-website snapshot (`_gw_cache` + `_gw_airbnb_url`, i.e. Hostaway's own channel data) → mapping method «payload», needing nobody.
- Built:
  - `abnb.py`: dated imports, sha256 de-dup, latest-at-or-before, and mapping (payload > confirmed > title suggestion, one unit per suggestion).
  - Engine funnel / funnel_peers / actions / forecast / discount_stack. The headline weakness now includes the funnel actions.
  - Chapters 6, 11, 12, plus presenter points (funnel sample size, lever decisions, discount-stack warning, test-group note).
  - Three routes: GET /api/meet/airbnb, POST import, POST map.
  - The import + mapping panel in the tab.
  - Caps: airbnb_room_ids, listing_titles, min_price.
- Tests: `test_owner_meet_import` (every fact re-measured independently from the raw TSV, XLSX round-trip, malformed → Arabic, snapshots never overwritten, latest-at-or-before, unmapped listed, one suggestion per unit) and `test_owner_meet_actions`.
- Gates met: G9 G10 (20 met in total).
- Found and fixed:
  - An ISO date inside the test-action evidence.
  - The same unit suggested for two report rows.
  - «16.0» bookings.
  - A redundant label on every action.
- The forecast's base is the SUM of the last three full months (the prototype's «متوسط آخر ثلاثة أشهر × 3»).
- The season uplift applies when the coming quarter touches Riyadh Season months (Oct–Mar) or an Eid.

## S5 — meeting record, chapter 0, owner link + PDF + WhatsApp → G14, G18, G19, G26

Files: `owner_meet/pdf.py`, `owner_meet/tools_layout_audit.py`, `routes.py` (record/send/link/pdf/wa), `notes.js` recorder, `render.py` (chapter 0 + phone layout), `tests/test_owner_meet_record.py`, `tests/fixtures/owner_meet/snapshot_full.json`.

1. Record tests:
   - frozen immutability
   - sha256
   - reopen admin + reason → v+1
   - links keep their version
   - chapter 0 evidence
2. `pdf.py`: its own print fn on `ouja_render._pw_pool` using `_pw_browser()` under `_pw_lock`; 1280×720 px pages; HTML fallback.
3. `tools_layout_audit.py` (Python 3.13 + playwright venv in the scratchpad, `OUJA_PY313`): overflow, phone horizontal scroll, PDF pages = chapters, ratio 16:9, no ISO dates.
4. Send: freeze → token → PDF (non-blocking) → wa link. Nothing auto-sends.

STOP: Faisal sends one test meeting to his own phone number.

**S5 log (2026-10-06, Faisal: «موافق وابدا في كل شي وخلصه» — S5 and S6 run without a stop between them):**
- Built:
  - The record in the presenter window: decision + SAR amount, «علينا» with role / due / linked ticket, «على المالك», delete, and «انتهى الاجتماع».
  - The send button (admin): it re-runs the readiness + privacy scan, freezes a new version carrying «ما اتفقنا عليه», creates a `token_urlsafe(32)` link, and prints the PDF on the build pool. Nothing is sent: WhatsApp opens with the text ready and Faisal presses send himself.
  - Reopen (admin + reason → version+1), link revoke, and open counting.
  - Chapter 0 from the previous presented/sent meeting. A linked ticket that closed is the evidence.
  - Statement expense lines with receipts through `/fin/receipt/{id}?t=<portal token>` (M5), on the owner page only. The portal token is read at render time and never stored in the snapshot.
  - The owner page: 16:9 on a wide screen, flowing text at 390 px.
  - `pdf.py`, and `tools_layout_audit.py`. Its positive control was proven: a planted overflow is caught.
- Caps: owner_phone, ticket_status.
- Tests: `test_owner_meet_record` (G14), `test_owner_meet_links` (G31). The privacy test now also scans the owner page.
- Found and fixed:
  - `_safe` turned a deliberate redirect (wa.me) into a 500.
  - Chapter 11 silently dropped any action past the 8th; it now continues on a second slide.
  - Cramped portfolio table + oversized headline on a phone.
  - ISO dates in the notes record list.

**S6 log — impeccable critique → audit → polish → harden (2026-10-06):**
- Critique (the committed world is the approved prototype): editorial paper + navy cover, Thmanyah Serif Display for numbers, no cards/gradients/emoji/glass, one idea per chapter, a source line under every block.
  - Kept the folio as a running header (not an eyebrow).
  - Removed the ★ glyph and the emoji in RR labels.
- Audit:
  - The design detector runs clean on the stage, notes, owner page and all three JS files. It flagged a navy-tinted «glow» shadow, now a neutral offset shadow.
  - WCAG contrast measured for every text/background pair. Gold text 4.44 → 5.66 (#7F5A1C), the partial chip 4.12 → 5.25, the notes placeholder 3.56 → 5.55. Everything else ≥ 5.2.
  - Keyboard: ← → Space PageUp/Down Home End F B N on the stage, arrows in the notes window, focus-visible ring in gold.
  - Touch targets ≥ 44 px in the presenter window.
  - prefers-reduced-motion stops the slide fade and the progress bar.
  - Motion: opacity fade ≤ 280 ms with cubic-bezier(.23,1,.32,1); progress bars animate `transform`, never width; press = scale(.97).
- Harden:
  - Every source that fails becomes a presenter note + an honest empty chapter, never a dead build.
  - A restart mid-build fails the build at boot.
  - `OWNER_MEET_ENABLED=0` removes the routes AND the menu item.
  - A refused send creates no link.
  - The PDF falls back to the page.
  - Unknown or revoked links are a plain 404.
  - Public pages are rate-limited (30/IP/min, 20/token/min).
- Performance: the presentation renders from a 12-month snapshot in well under 1 s (G17). Live build time on Railway (P9 / G27) can only be measured after an approved deploy — pending, not claimed.

## S6 — impeccable pass + performance + final routine → G20, G27 (+ every routine gate)

1. impeccable critique → audit → polish → harden on: the tab, the stage, the presenter window, the phone page, the PDF. Record the findings + fixes in an S6 log appended here.
2. emil-design-eng motion check (≤ 280 ms, transform/opacity only, reduced-motion).
3. Live P9 numbers (warm/cold/open) after an approved deploy.
4. Full routine. Final gate report with met / unmet / abandoned counts.

## Push policy

- No push at any slice without Faisal's explicit word for that push (G28).
- When he says push: merge onto main-based work, push main, verify through an `/api/meet/` route on Railway (not a page — the catch-all returns 200).
- Memory rule: a branch that is "not pushed" is not live.
