# رفع التقييم — Review Push · implementation plan

Spec: `docs/superpowers/specs/2026-10-03-review-push-design.md` (owner-approved 2026-10-03; the spec wins).
Gates: `reviewask/GATES.md`. Branch: `feat/review-push` (worktree `~/ouja-wt-review`, from origin/main 7c422cb). Not pushed.

## Owner decisions taken at «ابدأ» (2026-10-03)

1. **Slash command names are ASCII, descriptions Arabic.** bot.py's own rule: a rejected name fails
   the WHOLE tree sync and every slash command goes down, and Discord has no Arabic name
   localisation. Slash: `/reviews-tomorrow` `/reviews-today` `/reviews-start` `/reviews-stop`
   `/review-message` `/reviews-report`. The `!ouja` prefix commands keep the Arabic names from the
   spec (`تقييمات-بكرة` … like `تشغيل-الخروج`), with the ASCII names as aliases.
2. **A review whose score is 0 / empty / None is excluded completely** — from the CSV seed and from
   Hostaway alike. It is not a review and does not count in n. (143 such rows in the seed.)
   Locked by `test_reviewask_engine` (10 + 0 → average from the 10 only).

## Decisions the spec left open (recorded here, each one tested)

- **Seed reviews have no `type`.** `reviews_seed.json` (2,473 rows, Airbnb's own guest-review export)
  carries no `raw` at all → treated as guest-to-host. A seed row and a live row for the same
  reservation count once (the live one wins), matching `refresh_reviews`.
- **Type / channel filter** (G12 pending the live print): a row with `raw.type` counts only when it
  is the guest-to-host value; a row with no `type` counts. Channel = Airbnb by the normalised
  `channel` / `raw.channelName` (case-insensitive substring), or `raw.channelId == 2018`.
  The two constants live at the top of `engine.py` so the G12 values can be dropped in.
- **«الضيف رد» is a choice view, not a modal** (and the complaint urgency is a select in a view
  before the text modal): Railway pins `discord.py>=2.4`; selects inside modals need 2.6+.
- **Care mode after «راضي»** joins the review ladder at the WhatsApp step (wa_due now, the call
  the next evening if no review) — the spec says «راضي» "unlocks the WhatsApp stage".
- **«ما فيه رقم»** keeps the spec's state list: → `wa_sent` with `wa_note='no_phone'`; the card says
  «ما فيه رقم» and offers the Airbnb conversation link; the call stage still opens.
- **Button rows.** Card and prompts carry the CURRENT stage's buttons; an older prompt's buttons are
  disabled when a new prompt is posted (Checkout Watch pattern). Waiting / promised: no buttons.
- **Message → ticket** needs one table the spec list does not name: `rv_messages`
  (message_id → ticket_id), exactly `cw_messages`.
- **`/rv/<token>`** lives in `reviewask/routes.py` on `HOST.web_thread`. `tests/test_web_lane.py`
  is outside `OWNS:` and scans bot.py only, so `test_reviewask_structure` asserts the same rule
  for the package handler (no to_thread, uses web_thread). Flagged to the owner.
- **Catch-up opening** (the 00:05 rule): every tick after 00:05 opens anything missing for today
  and yesterday (yesterday covers a day the bot was down); `/reviews-tomorrow` and
  `/reviews-today` open on demand.
- **Cancellation.** One departure-window read (today−14 … tomorrow, 10-min cache). A row is
  cancelled only on positive evidence — the reservation comes back non-confirmed or with another
  departure date; up to 5 rows missing from the window are re-read by id per tick. A failed read
  never cancels anything.

## State machine (engine.next_action — PURE)

Fields on `rv_tickets`: `state`, `mode` (review|care), `day` (D), `stage_due_at` (when the current
prompt's window opened), `pinged_at`, `remind_count`, `missed_at`, `next_due_at`, `calls_used`,
`later_used`, `care_ok`.

```
waiting      ─ D WA_AT, not quiet ─▶ wa_due (review) | care_due (care)     + ping
wa_due       ─ reminders 18:00, 19:30 (after stage) ─ 22:00 no press ▶ staff miss (logged once)
             ─ next_due_at = call_time(stage day + 1) ─▶ call_due + ping
wa_sent      ─ next_due_at ─▶ call_due + ping
call_retry   ─ next_due_at ─▶ call_due | care_due (care, not yet «راضي») + ping
care_due / call_due ─ reminders (+45 min, 21:30) ─ 22:00 no press ▶ staff miss, SAME attempt rolls to
             call_time(next day): stage_due_at moves, remind_count=0, re-ping there
any open     ─ D+13 23:59 ─▶ expired (promised → promised_expired)
any open     ─ review matched ─▶ reviewed      ·  Hostaway cancel/move ─▶ cancelled
```
Presses (first-final-wins, conditional UPDATE under a lock): sent → wa_sent · replied →
promised/declined/complaint/wa_sent(note) · no_phone → wa_sent(note) · rated/promise → promised ·
noanswer → calls_used+1 → call_retry or no_answer_final at MAX_CALLS · later → call_retry once, then
= noanswer · complaint → complaint · decline → declined · wrong → wrong_number · satisfied →
wa_due (care_ok=1). Pings and reminders never fire 22:00–13:00; the silent card, staff-miss
logging, expiry and closes may.

## Build order (each: tests first, then code, then its gate)

1. G0 baseline ✅ (4,733 tests; 4 failures already on main: test_mot_flow.TestClose,
   2 × test_ops_capture.TestBackfill, test_train_export.TrainSinceMusaed).
2. G12 script handed to the owner (`~/Downloads/g12_reviews_peek.py`, read-only).
3. `engine.py` + `config.py` + `texts.py` → `test_reviewask_engine` (G3).
4. `db.py` + `flow.py` + `host.py` → `test_reviewask_flow` (G4), fake HOST, temp brain.db.
5. `flow.sweep_closed` → `test_reviewask_delete` (G5), refusal tests first.
6. bot.py wiring (spec §15 only) + `_maint_open_ticket(origin=…, origin_room=…)` →
   `test_reviewask_bot` (G6).
7. `test_reviewask_structure` (G7).
8. `ops_tidy_rules.classify_channel`: `ouja-rv:` topic or the «طلبات التقييم» family → keep →
   `test_ops_tidy_rules` (G8; the 196/24/94 audit numbers unchanged).
9. `routes.py` + `static/reviewask_tab.js` + ≤15-line stub (G10).
10. G1 G2 G9 G10 G11, CLAUDE.md section, commit (G15). No push.
