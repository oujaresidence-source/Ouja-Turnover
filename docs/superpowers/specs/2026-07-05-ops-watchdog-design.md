# «الرقيب التشغيلي» — Operations Watchdog (ops-watchdog) — Design

Date: 2026-07-05 · Status: approved by owner (Discord delivery, 30-min cadence,
instant critical pings, dashboard code-mode editor, 4 scoreboard metrics,
**output must be phone-readable in Discord**).

## Problem

The owner has no single indicator telling him whether operations are going right.
Operational truth is scattered across schedule coverage, cleaning turnover channels,
escalations, pending Musaed replies, promises, tickets, and Hostaway arrivals.
Two specific gaps have no machine check at all:

1. **Manual door codes** — some apartments' door codes auto-release via Hostaway
   (after agreement signing); others must be sent manually by an employee. There is
   no per-apartment flag distinguishing them, no log of who sent which code, and no
   flag when a manual code is missing before an arrival.
2. **Employee performance** — no per-employee reply metrics exist, and platform
   automations (e.g. Aseel's 11 AM checkout message) would pollute any naive count.

## Golden rule — proven data only

Every line in every summary traces to a verified source (targeted Hostaway query,
brain.db table, persisted state file). Anything unprovable renders as «غير معروف»
and is **excluded from scores**. No guesses. Owner-statement trap applies: any
reservation data uses targeted window queries (`fetch_inhouse`-style), never
`get_reservations_cached()`.

## Architecture

New **`watchdog/` package** (pattern: `schedule/`, `promises/`):

- `watchdog/engine.py` — PURE deterministic functions, no I/O, TDD-locked:
  - `compute_flags(snapshot, now)` → list of flags `{key, severity, text, employee,
    listing, age_min}`. Severity: `critical` | `warn` | `info`.
  - `is_automated_message(msg, history)` — the Aseel rule (below).
  - `scoreboard(events, days)` — per-employee metrics.
  - `render_summary(flags, today, lang)` / `render_critical(flag)` — Discord text,
    phone-first format (below).
- `watchdog/db.py` — brain.db (rules from memory: DELETE journal, busy_timeout,
  `closing(connect())`, NO WAL). Tables:
  - `watchdog_code_mode(listing_id PK, mode TEXT 'auto'|'manual', updated_at, updated_by)`
  - `watchdog_code_sends(id PK, listing_id, reservation_id, guest_name, sent_by,
    sent_at, arrival_ts, on_time INT, detected_at)` — permanent audit log.
  - `watchdog_flag_state(flag_key PK, first_seen, last_seen, pinged_at, resolved_at)`
    — instant-ping dedup + flag lifecycle.
  - `watchdog_msg_stats(id PK, day, employee, replies, avg_response_min, automations_skipped)`
    — daily rollup for the scoreboard.
- `watchdog/routes.py` — aiohttp routes under `/api/watchdog/*`:
  - `GET /api/watchdog/status` (login-gated) — current snapshot for the dashboard.
  - `GET/POST /api/watchdog/code-mode` (login + can-edit gated) — the code-mode editor
    data + writes.
- `bot.py` wiring (additive, minimal):
  - `watchdog.wire({...})` in `start_web_server` passing READ-ONLY accessors:
    `_escalations`, `_pending_replies`, `_tickets`, `fetch_inhouse`,
    `compute_arrivals_with_status`, schedule `compute_day`/coverage, promises db,
    OujaCT state dicts, `api_get` (for conversation reads), storage block.
  - `@tasks.loop(minutes=WATCHDOG_INTERVAL_MIN)` watchdog loop. **Deploy trap**:
    first iteration fires on every deploy → persisted last-run guard (skip if last
    summary < interval ago) exactly like the `_oujact_opened` idempotency lesson.
  - Discord posting into channel `WATCHDOG_CHANNEL` (default `غرفة-المراقبة`,
    auto-created like other bot channels).
- Dashboard: **code-mode editor** panel. To avoid DASHBOARD_HTML risk, the editor is
  a small section added following existing view/i18n conventions (`tb` key + `T.ar`
  + `T.en` + `showPanel` rules), listing all apartments with a تلقائي/يدوي toggle.
  Default mode for every apartment: `auto` (watchdog only monitors `manual` ones,
  so default is silent-safe).

## Checks (every cycle)

| # | Check | Source | Critical when |
|---|---|---|---|
| 1 | Manual code sent before arrival | code_mode + Hostaway conversation scan | arrival ≤ 3h and no code message found |
| 2 | Cleaning before check-in | OujaCT state + arrivals | arrival ≤ 3h, turnover not approved |
| 3 | Stale cleaning channels | `_oujact_opened` vs `_oujact_done` | open > 36h without report |
| 4 | Escalations unclaimed | `_escalations` | unclaimed > 2h (warn > 45min) |
| 5 | Pending replies aging | `_pending_replies` | oldest > 2h (warn > 30min) |
| 6 | Promises overdue/expired | promise_ledger | any expired (warn: overdue) |
| 7 | Tickets unassigned / stale | `_tickets` | — (warn only) |
| 8 | Coverage today | schedule compute_day | imbalance > 1 or uncovered unit (warn) |
| 9 | Today numbers | fetch_inhouse + arrivals | info line only |
| 10 | System health | storage block, Hostaway auth ok, digest fired | disk fallback / API dead |

Code-send detection (check 1): scan the reservation's Hostaway conversation for an
outgoing message containing a 4–8 digit code near code keywords (reuses the
`_was_code_sent_recently` heuristic family); on hit, record sender via
`_wm_sender_name` into `watchdog_code_sends` with `on_time = sent_at < arrival_ts`.
Sender unknown (typed in Airbnb app) → sender = «غير معروف», still logged, excluded
from per-employee credit. Responsible employee for a missing code = today's coverage
employee for that apartment (schedule coverage map), fallback «غير معروف».

## The Aseel rule — automation filter

A human reply is counted ONLY if it fails all of:
1. AI signature match (`_wm_is_ai_message` — existing).
2. `_looks_automated` marker match (existing).
3. **Recurrence fingerprint (new)**: normalized body (strip guest name/digits/
   whitespace) seen ≥ 3 times across ≥ 3 different conversations, with send
   clock-time within a ±20-min window (e.g. 11:00 AM daily checkout blast) →
   automation. Fingerprints accumulate in a persisted store; matching is retroactive
   for the current day's stats.
Excluded messages increment `automations_skipped` (visible, so exclusion is proven,
not silent).

## Discord output — PHONE-FIRST format

Hard rules: max ~12 short lines per summary; one line per fact; no tables; no code
blocks; emoji status prefix; Arabic (Najdi) primary. All-green cycles post the
compact form only.

All-green summary (edits/replaces the previous summary message to avoid scroll spam;
one summary message per cycle, channel keeps only recent history):

```
🟢 كل شي تمام — ٣:٣٠ م
🏠 اليوم: ٥ وصول · ٣ مغادرة · ٤١ ساكن
🧹 نظافة: ٣/٣ جاهزة · 🔑 أكواد يدوية: ٢/٢ مرسلة
📩 معلق: ٠ تصعيد · ٠ رد ينتظر · ٠ وعد متأخر
```

Flags summary (red/yellow) — each flag ONE line: emoji + what + apartment + who +
how long:

```
🔴 وضع يحتاج تدخل — ٣:٣٠ م
🔴 كود ما انرسل: Ouja | برج الياسمين ٧ — 👤 نورة — الضيف يوصل خلال ساعتين
🟡 تصعيد بدون استلام من ساعة ونص — ضيف شقة ١٢
🟢 الباقي تمام: نظافة ٣/٣ · وعود ٠ متأخر
```

Critical instant ping — separate message (not an edit), mentions owner +
responsible employee's Discord id (via WATCHMAN name map), sent once per flag_key
(dedup via `watchdog_flag_state`; re-ping only if still unresolved after
`WATCHDOG_REPING_HOURS`, default 2).

Weekly scoreboard (Sunday morning, same channel): per employee, 4 proven metrics,
one employee per line block, ≤ 4 lines each:

```
🏆 لوحة الأسبوع
👤 نورة — وعود ٩٤٪ ✅ · ردود ٣٤ (متوسط ١٢د) · أكواد ٨/٨ باكر · تصعيدات ٥ (أسرع استلام)
👤 أسيل — وعود ٨٨٪ · ردود ٢١ (متوسط ١٨د) · أكواد ٥/٦ · تصعيدات ٣
   (استبعدنا ٢٨ رسالة أتمتة — ما تنحسب)
```

## Env flags

- `WATCHDOG_ENABLED` (default 1)
- `WATCHDOG_DRYRUN` (default 1 — log-only until owner flips to 0)
- `WATCHDOG_INTERVAL_MIN` (default 30)
- `WATCHDOG_CHANNEL` (default `غرفة-المراقبة`)
- `WATCHDOG_REPING_HOURS` (default 2)
- `WATCHDOG_CODE_LOOKAHEAD_H` (default 12 — how far ahead arrivals are checked)

## Error handling

- Every collector wrapped: one failing source degrades to «غير معروف» line, never
  kills the cycle.
- Hostaway conversation scans budget-capped per cycle (only today's + lookahead
  arrivals for manual-mode apartments — small N).
- Loop exceptions logged, next cycle continues; no retry storms (Musaed spam lesson).
- Read-only guarantee: package never calls `api_post`/`api_put`, never messages
  guests.

## Testing (TDD, before wiring)

`tests/test_watchdog_engine.py`:
- flag computation per check (synthetic snapshots: missing code → critical with
  correct employee; cleaning stale; escalation aging thresholds).
- automation fingerprint: Aseel-style 11 AM recurring body → excluded; genuine
  varied replies → counted.
- scoreboard math incl. unknown-sender exclusion and automations_skipped surfacing.
- render: phone format line-count caps, all-green vs flags variants, Arabic digits.
- dedup: same flag never double-pings; resolved flag clears; re-ping after window.

Verification routine per CLAUDE.md (py_compile, pyflakes, node --check erp.js,
unittest, DASHBOARD_HTML esprima parse if touched) before any "done" claim.

## Out of scope (v1)

- Live sending of anything to guests (never).
- Phone-call / WhatsApp business-line monitoring (owner mentioned "phones" — needs
  a data source that doesn't exist yet; revisit when one does).
- Dashboard live watchdog tab beyond the code-mode editor (v2 candidate).
