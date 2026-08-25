# Finance Chat «مساعد المركز المالي» — Design

**Date:** 2026-07-05
**Status:** Approved by owner
**Approach:** A (KB + Haiku→Sonnet), with C (live-data tools) as a later bolt-on phase.

## Problem

The accounting team asks the owner 10–20 questions per day about the Finance Center
(/erp): how to use screens, policy/process rules, where numbers live, and broken
things. Questions arrive in Arabic, often badly phrased. The owner wants an in-ERP
chatbot that answers with references and direct links, escalates real bugs to him,
costs almost nothing in tokens, and — critically — never requires a Railway redeploy
to update its knowledge.

## Decisions made with the owner

- **Scope v1:** knowledge-base answering only. NO live-data reads. Live-number
  questions get pointed to the right ERP screen with a deep link. Live-data tool
  use is phase C, bolted onto the same chat later.
- **Runtime models:** Haiku answers everything; low confidence triggers one Sonnet
  retry; still low → escalate. Models: `claude-haiku-4-5-20251001`,
  `claude-sonnet-5` (env-overridable).
- **Escalation:** BOTH a Discord ping (@owner mention in a finance channel) and a
  persistent inbox inside the ERP.
- **KB growth:** learn-loop (answered escalation → one click saves as FAQ) PLUS an
  admin KB editor screen in the ERP. All edits at runtime in brain.db — zero
  redeploys.
- **UI:** floating chat bubble on every ERP screen opening a drawer (RTL,
  Arabic-first), plus admin views for KB editor and escalation inbox.
- **KB sources:** generated this session by Fable from (1) the finance/ code and
  bot.py finance routes, (2) CLAUDE.md + memory files, (3) past Claude Code session
  transcripts mined for the team's real questions, (4) owner-dictated top questions.
  Target ~300–800 sharp entries — quality over count (the "100k FAQs" idea is
  replaced by comprehensive coverage of everything the ERP can actually do).

## Architecture

New additive package `finchat/`, following the `schedule/` / `watchdog/` pattern.
bot.py changes are wiring only (~10 lines in `start_web_server`: `finchat.wire({...})`
+ `finchat.register_routes(app)` + env flags).

```
finchat/
  __init__.py   # wire({...}) DI + register_routes(app)
  db.py         # brain.db tables; closing(connect()) per call; journal_mode=DELETE
  kb.py         # Arabic normalization + in-memory retrieval scoring + seed import
  answer.py     # Haiku→Sonnet pipeline; reuses bot.py's existing Anthropic HTTP helper
  routes.py     # /api/finchat/* aiohttp endpoints
  seed_kb.json  # one-time generated seed (committed once)
```

Frontend: additive section in `finance/static/erp.js` (chat bubble + drawer +
2 admin views). No build step; `node --check` + esprima remain the gate.

## Data model (brain.db)

All tables prefixed `finchat_`. SQLite rules from memory apply: NO WAL, NO
EXCLUSIVE locking, `closing(connect())`, `journal_mode=DELETE`.

- `finchat_kb(id, q_ar, q_norm, answer_ar, links_json, tags, source, enabled,
  created_at, updated_at)` — `source` ∈ {seed, learned, manual}. `links_json` is a
  list of `{label_ar, route}` where `route` is an ERP SPA route/hash.
- `finchat_msgs(id, username, role, text, kb_ids_json, model, confidence, ts)` —
  per-user chat history; `role` ∈ {user, bot, owner}.
- `finchat_esc(id, username, question, context_json, status, answer, answered_at,
  saved_as_kb, discord_msg_id, created_at)` — `status` ∈ {open, answered}.

Seed import: on boot, if `finchat_kb` is empty, import `seed_kb.json`. Never
re-import over existing rows (DB is the source of truth after first boot).

## Answer pipeline

1. **Normalize** the question: strip tashkeel/tatweel, unify أ/إ/آ→ا, ة→ه, ى→ي,
   lowercase Latin, collapse whitespace.
2. **Retrieve**: score all enabled KB entries in memory (token overlap on
   `q_norm` + answer text, tag boost). A few hundred entries — no FTS engine
   needed. Take top 8.
3. **Haiku call**: system prompt = short Najdi persona + hard rules (never invent
   numbers, answer only from provided knowledge, always give links when a screen is
   referenced, reply in Arabic) + compact static ERP screen-map (~1k tokens).
   User content = question + top-8 candidates. Forced-JSON reply:
   `{answer, confidence (0–1), links, needs_escalation}`.
4. **Fallback**: `confidence < FINCHAT_CONF` → one Sonnet retry with top 16
   candidates. Still low → bot replies «ما عندي جواب أكيد» + visible escalate button.
5. **Guardrails**: live-number questions answered with WHERE to look + deep link
   (never a number). Per-user daily message cap. `FINCHAT_ENABLED=0` kills the
   feature (bubble hidden, endpoints 404).

Estimated cost: ~3k input / 500 output tokens per Haiku answer → roughly
$0.10–0.30/month at 20 questions/day.

## Escalation flow

- User taps escalate (or bot offers it) → `POST /api/finchat/escalate` →
  row in `finchat_esc` + Discord message in `FINCHAT_ESC_CHANNEL` with owner
  @mention, question, asker, and a link to the ERP inbox.
- ERP «صندوق التصعيد» (admin/owner-gated): list of open escalations; owner types an
  answer → it is appended to the asker's chat thread (role=owner) and the row
  flips to answered. A checkbox «احفظ كسؤال شائع» (default on) also inserts a new
  `finchat_kb` row with `source=learned`.

## ERP UI

- **Bubble + drawer**: floating button bottom corner of every ERP screen (RTL).
  Drawer holds the chat thread (history from `finchat_msgs`), input, and link
  buttons that navigate the SPA directly to the referenced screen. Reuses erp.css
  design tokens; motion follows emil-design-eng rules (transform/opacity,
  ≤300ms, reduced-motion respected).
- **KB editor** (admin): searchable table of entries; add/edit/disable; fields for
  question, answer, links, tags. Write endpoints role-gated via the existing role
  middleware map (new write routes MUST be added to the map).
- **Inbox** (admin): escalations list as above.
- Contract discipline (per Finance-ERP traps): erp.js reads exactly the shapes the
  API returns; optimistic UI reconciles against server responses; no action offered
  that the state machine can't honor.

## Env vars

- `FINCHAT_ENABLED=1`
- `FINCHAT_MODEL_FAST=claude-haiku-4-5-20251001`
- `FINCHAT_MODEL_SMART=claude-sonnet-5`
- `FINCHAT_CONF=0.6`
- `FINCHAT_DAILY_CAP=80`
- `FINCHAT_ESC_CHANNEL=finance-help` (Discord channel for escalation pings;
  created if missing, overridable)
- Reuses existing `ANTHROPIC_API_KEY`.

## KB build (this session, no API cost)

1. Mine past Claude Code session transcripts for real accounting-team questions.
2. Read finance/ package + bot.py finance routes + CLAUDE.md + memory files.
3. Write `seed_kb.json` (~300–800 Arabic entries, each with answer + deep links +
   tags) and the compact ERP screen-map used in the system prompt.
4. Owner dictates top recurring questions; they get priority entries.

## Testing (TDD)

- `tests/test_finchat_kb.py` — normalization cases (tashkeel, alef variants,
  mixed AR/EN), retrieval scoring (right entry wins, top-k ordering).
- `tests/test_finchat_answer.py` — confidence routing with a mocked API client:
  high conf → Haiku only; low → Sonnet retry; still low → escalation offer;
  daily cap; kill switch.
- `tests/test_finchat_esc.py` — escalation lifecycle: open → answered → thread
  append → learned KB row; no double-answer.
- ERP contract test extension for the new endpoints' response shapes.
- Full repo verification routine (py_compile, pyflakes, node --check erp.js,
  esprima on DASHBOARD_HTML scripts, unittest) before declaring done.

## Phase C (later, not in this build)

Same chat gains read-only tools (statement totals, expense status, balances) via
tool-use on Sonnet. The pipeline, UI, escalation, and KB all stay unchanged —
tools slot into `answer.py`.

## Rollout

Additive and reversible: feature flag default on but killable via env. Ship →
owner checks bubble on /erp, asks a few real questions, flips nothing on Railway.
KB edits and learning need no redeploys.
