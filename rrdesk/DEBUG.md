# RR Desk «طلبات سام» — debugging runbook

Start every investigation with three reads, in this order:

1. **`GET /rrdesk/health`** (public, counts only) — switches, last tick + lag, translations
   today, failures in the last hour, cache hit rate, cap remaining, open requests, Sam
   resolved, outbox backlog / failed, last error class.
2. **`/rrdesk-why`** typed inside the room (only you see it) — every request there with its
   owner rule, dues, each ladder step (sent / not yet / waiting for working hours / switched
   off) and the last events.
3. **`rrdesk_events`** (dashboard → طلبات سام → السجل, or SQL on brain.db) — append-only, every
   decision with who/what/why.

To reproduce a room offline: export it (`tools/rr_history_export.py export`, or the browser
study), redact with `rrdesk.study.redact`, save under `tests/fixtures/rrdesk/rooms_replay/`, then
`python3 -m rrdesk.replay <room>.json` and read the timeline.

| Symptom | Where to look | Likely cause | Fix |
|---|---|---|---|
| No translation appears | health `switches`, `/rrdesk-why` (translate here?), events `tr_skipped` / `tr_failed` / `cap_hit` | room toggled off (`/translate off`), `translate` or `force_off` switch, daily cap hit, the message matched a skip rule (emoji / code block / bot English), room not RR (no `_dtk` record and not in the RR category family) | `/translate on`, `/rrdesk-switch translate on`, `/rrdesk-on`; raise the cap in الإعدادات; skips are by design |
| ⚠️ reaction under a message | events `tr_failed` (detail.e) | Haiku timeout (12 s, one retry) or no `ANTHROPIC_API_KEY` | transient: edit the message (re-translates) — the claim was released; persistent: check the key / Anthropic status |
| Double translations after a deploy | `rrdesk_translations` (UNIQUE source id), `rrdesk_outbox` refs `tr:<id>` | two refs for one message = impossible by schema; a second reply means one was posted by an OLD code path or by hand | check `once_claim` markers under `$STATE_DIR/once_locks`; look for a second listener registration (`bot._rd_listener` must guard) |
| A request didn't open | `/rrdesk-why`, events for the message (`translated` detail.classify), settings `detect_mode` | detection is in **confirm** mode (Sam must press «Yes»), classifier said not a request / confidence < threshold, it was merged (`merged`) or a re-ask (`sam_reask`) of an open one, Sam id unresolved | `/rr-ask` or 📌 always work; `/rrdesk-sam @Sam`; after `/rrdesk-study` grades the classifier, switch detection to auto in الإعدادات |
| Wrong owner | events `owner_chosen` (rule 1-5, covered_for) | rule order: Sam's mention → role mention → opener in the calendar → apartment's responsible today → lead (unowned) | press **Reassign** (lead/admin) — the new owner gets a fresh clock, the old owner's miss (if any) stops counting |
| A ladder step didn't fire | `/rrdesk-why` line for the step | outside working hours (11:00 → 01:30 — waits), `ladder` switch off, state no longer open/acknowledged, a LATER step was already sent (never goes backwards) | by design; turn `ladder` back on |
| A ladder step fired twice | `rrdesk_ladder` UNIQUE(request_id, step) | cannot happen for one generation; `R1#2` after a reassign is the NEW owner's ladder | — |
| A miss looks unfair | dashboard السجل for the request; `rrdesk_misses.eligible`; events `miss` (admin / leave / unowned flags) | late acknowledgement counted in working minutes, a request that should have been «ما عندنا», a burst of lines Sam sent in > 15 minutes | lead/admin: **عذر · Excuse** on the watchdog line (≤ 48 h, reason ≥ 10 chars) or POST `/api/rrdesk/excuse`; an issued warning → the ops appeal link (أصيل → ريم → فيصل) |
| A warning didn't issue in live mode | settings `sw:warn_live`, `ops_dryrun_log` (kind `rr_warning`), events `judged` / `would_warn` / `warning` | warn_live still off (dry-run), the 2nd miss was in a different ISO week, a miss was excused, owner on leave / admin / unowned | `/rrdesk-warnings-on` + «تشغيل» — only the owner decides |
| The cost spiked | dashboard الترجمة (today / month, calls vs cap), events `translated` detail.source | a chatty room, cache misses after a glossary edit (the glossary version is in the cache key), image-text button presses | lower the cap (الإعدادات), turn translation off in that room |
| Dashboard tab says «undefined» | NAV_DEF labels in bot.py | the tab id lacks a label in `labels.ar` or `labels.en` | add both; `python3 -m rrdesk.tools_dash_check` |
| Tab shows the error state | browser console, `node --check rrdesk/static/rrdesk_tab.js`, `/api/rrdesk/state` | a JS syntax error, or the user lacks the «rrdesk» permission (401/403) | fix + `node --check`; tick «طلبات سام» in الصلاحيات |
| A button is "thinking…" forever | bot logs `[rrdesk] button error`, events `press_refused` | an exception before the reply, or the pool is jammed | every press defers first and always answers; restart clears the pool; the press can be retried — rows are found by message id |
| Board message missing / not updating | health `outbox_failed`, outbox rows `board:*` | the room «متابعة-طلبات-سام» does not exist | `/rrdesk-setup` (admin) creates it under RR |
| Everything must stop NOW | — | — | `/rrdesk-off` (force_off). `/rrdesk-on` undoes it. Code undo: `git revert` the merge commit |

Log lines are all prefixed `[rrdesk]` with channel / message / request ids — never a token or a
phone number.
