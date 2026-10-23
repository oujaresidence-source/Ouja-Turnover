# RR Desk «طلبات سام» — design (2026-10-24)

Source of requirements: the owner's one-pass brief ("RR Desk — translation + Sam's requests +
SLAs + warnings"), pre-approved in full. This file turns it into an architecture; every
"why" below is an owner rule from that brief or a trap already paid for in this repo.

## 1. What it does

1. **Translation.** Every human message in an open RR room (and its threads) gets one reply
   with a grey embed in the other language. Bot messages in Arabic (cards, nudges, status
   lines) get an English one for Sam. English bot messages, code blocks (the WhatsApp copy
   block), our own messages and empty/emoji/number/link-only lines are skipped.
2. **Requests.** A message from Sam becomes a tracked request by one of four paths:
   `/rr-ask`, a 📌 he puts on his own message, the classifier above the calibrated
   threshold, or Sam pressing «Yes» on the «Is this a request?» question.
3. **Ownership + SLA.** Every request is owned by one person (frozen, five-rule order), has
   a response due and a delivery due counted in working minutes (11:00 → 01:30), and walks
   a ladder R1 → R2 → D1 → D2 → D3 (miss).
4. **Accountability.** A miss is recorded; the 2nd miss in an ISO week becomes ONE ops
   warning (kind `rr`, period `RR-YYYY-Www`) through `ops.db` — the same table, multiplier,
   appeal chain and HR room every other warning uses. Money is dry-run until the owner types
   `/rrdesk-warnings-on` + «تشغيل».
5. **KPIs + surfaces.** Dashboard tab «طلبات سام», a board channel edited in place, the
   watchdog room, Sam's 13:00 English digest, everyone's Sunday DM with their own numbers.
6. **Debug kit.** `rrdesk_events`, `/rrdesk-why`, `/rrdesk/health`, offline replay, kill
   switches, `rrdesk/DEBUG.md`, a CLAUDE.md section.

## 2. Architecture

```
bot.py  ──wire({...})──▶  rrdesk.host.HOST   (capabilities only; rrdesk never imports bot)
   │                         ▲
   │ listeners (5) ─────────▶ rrdesk.bridge   async: Discord objects → plain dicts, outbox
   │ rrdesk_loop (1 min) ───▶ rrdesk.flow.tick  (on rrdesk's own pool) → rrdesk.outbox.drain
   │                                              │
   ▼                                              ▼
rrdesk.engine (PURE)  ◀── rrdesk.flow ──▶ rrdesk.db (brain.db, rrdesk_*)   rrdesk.translate
                                     └──▶ ops.db (_warn only)              (Haiku via HTTP)
```

* **engine.py** — pure: language share/direction, skip rules, phrase table, state machine,
  working-minute arithmetic (`add_work_minutes` is the inverse of `ops.engine.worked_minutes`
  and is tested against it), ladder timetable + `due_step` (latest step only — no backlog
  burst), judge verdicts, eligibility, owner rule order, KPI maths, time formatting.
* **db.py** — the nine `rrdesk_*` tables; every idempotency rule is a UNIQUE constraint.
* **translate.py** — prompt, glossary selection, cache, phrase table, daily cap, cost
  accounting, the HTTP call (12 s timeout, one retry after 3 s). It makes its own call
  instead of `claude_json` because the brief needs real token usage and a 12-second budget;
  `claude_json` returns neither and retries for up to ~60 s per attempt.
* **flow.py** — sync orchestration: message/edit/delete/reaction/press handlers, the tick
  (open → ladder → judge → digests → board), and `_warn()` — the package's ONLY
  `ops.db.issue_warning` call.
* **outbox.py** — every Discord side effect is a row with a UNIQUE `ref`, claimed atomically
  (`UPDATE … WHERE state='queued'`), retried 1/5/15/60 min. Two overlapping bot copies during
  a Railway redeploy can never double-post.
* **bridge.py** — the only file that touches discord.py objects. It receives the `discord`
  module and the bot through HOST (no import of bot.py), converts messages to dicts, runs
  flow on the pool, drains the outbox, renders buttons and modals.
* **routes.py / static/rrdesk_tab.js** — the tab, `/api/rrdesk/*` (login + «rrdesk»
  permission; writes admin-only, re-checked), `/rrdesk/health` (public, counts only).
* **study.py / tools/rr_history_export.py** — read-only study; `replay.py` — offline replay.

## 3. Key decisions (and the rule each protects)

| Decision | Why |
|---|---|
| Buttons are handled by one `on_interaction` listener with static `custom_id`s (`rd:*`), the row found by message id | Survives redeploys with no per-message view registration (checkout/reviewask pattern). |
| Our posts carry an invisible marker (`chr(0x2063)`) + footer | `on_message` for our own post can arrive before the outbox has stored its id; the marker is checked first. |
| A translation is claimed before the model call (`UNIQUE(source_message_id)` + `once_claim`) and released on failure | Two bot copies → one translation. A failure does not burn the claim. |
| Detected requests ship in **confirm** mode until the in-bot golden eval proves ≥95% precision | No API key existed where this was built, so the threshold could not be measured offline; a false accusation is worse than a missed detection. |
| Only explicit / confirmed / measured-detected requests can produce a miss | The brief's detection-safety rule. |
| Reassign bumps `gen`; ladder steps are keyed `step` + `gen` | The new owner gets a fresh clock and the old owner's sent steps never block the new ones. |
| Rework keeps the ORIGINAL delivery due | Brief §5.B.4. |
| Judge counts non-excused misses per owner per ISO week of the miss | 1st = private notice, 2nd = one warning, later = KPI only. |
| No route/button/command can create a miss or warning | "The system accuses. Humans only forgive." Structure test greps it. |
| Board/watchdog/DM split | Per-person numbers never in shared rooms. |

## 4. Data

`rrdesk_rooms`, `rrdesk_translations`, `rrdesk_cache`, `rrdesk_requests`, `rrdesk_ladder`,
`rrdesk_misses`, `rrdesk_events`, `rrdesk_outbox`, `rrdesk_settings`, plus `rrdesk_files`
(attachments seen in RR rooms — the «سلّمت» proof check) and `rrdesk_voice`. See db.py.

## 5. Failure behaviour

* Model timeout/failure → ⚠️ reaction + event; tracking continues.
* Tracking failure → translation continues (separate try blocks, separate claims).
* Daily cap hit → translation pauses until Riyadh midnight, one watchdog line, detection
  becomes explicit-only for the rest of the day.
* `force_off` → every listener returns before doing anything; the tick only heartbeats.
* `_tk_close` hook is wrapped: rrdesk raising can never block a ticket close.

## 6. Tests

engine, translate, flow, warn, golden, replay, structure, bot wiring — see the plan.
