# Conversation Watchman «الرقيب» — Design Spec

**Date:** 2026-06-28
**Status:** Approved design (pending spec review → implementation plan)
**Owner:** Faisal (non-technical; reviews by screenshot/Arabic+English)
**Scope:** Additive feature in `bot.py`. No changes to live reply behavior.

---

## 1. Problem

The bot already runs an AI assistant (`claude_draft`) that drafts/handles guest
replies on Hostaway. But **nobody re-reads a finished conversation** to catch two
recurring failures:

1. **Guide gaps** — guests ask things their apartment's directions/guide page should
   already answer (parking, wifi, AC, checkout…). We answer in chat, but the guide
   stays incomplete, so the *next* guest asks the same thing.
2. **Forgotten promises** — a team member promises a guest something ("technician at
   5pm", "we'll refund you", "late checkout till 2") and then forgets. There is no
   tracking or accountability.

The Watchman is a background watcher that re-reads each conversation **after it goes
quiet** and opens tickets for both.

---

## 2. Goals / Non-goals

**Goals**
- Detect info we gave a guest that is **missing from that apartment's guide page**, and
  open a **guide-gap ticket** with the exact text to add.
- Detect **concrete promises** (action / money / timing), attribute them to the
  **employee who sent that reply**, open a **promise ticket** that @mentions them, and
  **chase it to completion** (deadline → nudge → manager escalation).
- Ship safely behind a **watch-only (dry-run)** switch, like the rest of this bot.

**Non-goals (v1)**
- No mid-conversation / live ticketing (we batch after quiet period).
- No auto-editing of the guide page (we only say what to add; a human edits).
- No auto-closing promises by guessing fulfillment from later messages.
- No new hosting/service — everything lives in `bot.py`.

---

## 3. Decisions (locked with owner)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Reply channels in reality | **Hostaway inbox + Airbnb app directly** (mixed) |
| 2 | Promise attribution | Use the **responder name Hostaway shows**, matched to Discord. Unknown sender → unassigned ticket in promises channel (never dropped) |
| 3 | "Source of truth" for missing-info | **Read the page behind the apartment's directions link** (it's a link, not a file); fallback `#knowledge` + AI judgment when a page can't be read |
| 4 | Timing | **Quiet period** — analyze a conversation once its last message is ~30–60 min old |
| 5 | Promise follow-up | **Track until "Done" + nudge**; escalate to manager if still ignored |
| 6 | What counts as a promise | **Action**, **Money**, **Timing** commitments. **Skip** vague pleasantries |
| 7 | Missing-info routing | **New "guide gaps" channel**, @mention guide owner/manager (separate from physical maintenance) |
| 8 | Rollout | **Watch-only (dry-run) first** — log what it *would* ticket, post nothing, until owner flips it on |

---

## 4. Step 0 — Verify before trusting (this repo's rule: evidence over claims)

Two assumptions must be proven on **live** data before the real logic is built. A
**read-only diagnostic** (temporary, like prior `/diag` tools) confirms:

- **0a — Responder identity:** For several real conversations, dump the raw Hostaway
  message objects and confirm whether each **outgoing** message carries an individual
  sender (e.g. a `userId` / user name field), and whether that holds for **both**
  Hostaway-inbox replies **and** Airbnb-app replies. Current code only labels outgoing
  messages `"Host:"` (see `fetch_new_guest_messages` / history builder around
  `bot.py:6454`) — it never reads a sender today, so this is unproven.
- **0b — Directions link format:** For a sample of apartments, fetch the URL from
  `_extract_directions` / `directions_url` (`bot.py:757`, `bot.py:4887`) and confirm the
  content is **readable text** (hosted guidebook / web page) vs. an un-parseable target
  (map pin, app deep-link, login-walled doc).

**The real logic is built on what the probe proves, not on assumptions.** If 0a shows
some messages have no sender → those promises route to the unassigned promises channel.
If 0b shows some links unreadable → those apartments use the `#knowledge` fallback.

---

## 5. Architecture

A new background task in `bot.py`, reusing existing infrastructure:

- **Hostaway:** existing `api_get` for `/conversations/{id}/messages`.
- **AI:** existing Claude call path used by `claude_draft`.
- **Discord:** existing channel-posting + a button view like the maintenance ticket flow.
- **Directions:** existing `_extract_directions` / `directions_url`.
- **Knowledge fallback:** existing `_knowledge_apartment_facts` / `_knowledge_text`.

### 5.1 The watch loop
- Runs on a timer (`@tasks.loop`, every few minutes).
- **Guard:** `@tasks.loop` runs its first iteration on every Railway deploy — must be
  idempotent (see CLAUDE.md trap). It only acts on conversations not already analyzed.
- Finds conversations whose **last message age ≥ `WATCHMAN_QUIET_MIN`** (default 45) and
  whose **last-analyzed marker is older than the last message** (so new messages
  re-open analysis, nothing re-analyzed needlessly).
- For each, runs **one** AI pass → returns a structured result: `{ guide_gaps[],
  promises[] }`. One AI call per conversation per quiet window (cost control).

### 5.2 The AI pass (single structured call)
Input: full conversation text (guest + host turns, with responder names when available),
apartment id, the **fetched guide-page text** (or `#knowledge` fallback).
Output (strict JSON, validated):
- `guide_gaps`: list of `{ topic, guest_question, our_answer, suggested_guide_text,
  confidence, in_guide:false }`. Only items **provably absent** from the guide text.
- `promises`: list of `{ type: action|money|timing, summary, due_hint, responder_name,
  source_message_id }`. Concrete only; pleasantries excluded by prompt rule.
Bilingual / Najdi-aware (reuse the dialect guidance already in `claude_draft`).

### 5.3 State stores (JSON in `STATE_DIR`, matching existing pattern)
- `watchman_seen.json` — per-conversation last-analyzed message id (idempotency).
- `watchman_gaps.json` — open guide-gap tickets, keyed by `apartment + normalized topic`
  (for dedup / "+1 guest hit this").
- `watchman_promises.json` — open promise tickets with lifecycle state (`open`,
  `done`, `nudged`, `escalated`), deadline, assignee, source.

---

## 6. Guide-gap tickets

- For each `guide_gap`, dedup against `watchman_gaps.json` by `apartment + topic`:
  - **New** → post a card in the **guide-gaps channel** (`WATCHMAN_GAPS_CHANNEL`),
    @mention `WATCHMAN_GUIDE_OWNER` (role or user). Card shows: apartment, guest
    question, our answer, **exact suggested sentence to add**, confidence, link to convo.
  - **Already open** → don't duplicate; increment a "guests affected" counter on the
    existing card.
- Confidence: items built from a **read** guide page = normal; items from the
  `#knowledge` fallback = tagged **"lower confidence (guide page unreadable)."**
- Resolution: a **"Added to guide"** button closes it (removes from `watchman_gaps.json`).

---

## 7. Promise tickets

- For each `promise`, resolve assignee:
  - `responder_name` → Discord id via **`WATCHMAN_NAME_MAP`** (Hostaway-name →
    Discord-id). Match found → ticket **@mentions that person**.
  - No name / no match → ticket posts **unassigned** in the promises channel for a
    manager to claim. (Never dropped.)
- Post a card in the **promises channel** (`WATCHMAN_PROMISES_CHANNEL`): the promise text,
  guest + apartment, who promised, **deadline**, and a **"Done ✅"** button.
- **Deadline** by type:
  - `timing` → the promised time itself (parsed from `due_hint`); fallback +12h.
  - `action` → `WATCHMAN_ACTION_DUE_H` (default 6h).
  - `money` → `WATCHMAN_MONEY_DUE_H` (default 24h).
- **Lifecycle (loop checks open promises each tick):**
  - Past deadline + not done → **nudge** the assignee (re-ping), mark `nudged`.
  - Past deadline + `WATCHMAN_ESCALATE_AFTER_H` (default 3h) still not done → **escalate**
    to `WATCHMAN_MANAGER_ROLE`, mark `escalated`.
  - **"Done"** button → mark `done`, stop nudging.
- Nudge cadence respects the **anti-spam** lesson (no rapid re-pings; one nudge per
  overdue check, capped).

---

## 8. Guardrails

- **No double-ticketing** with the existing escalation system (`_post_system_escalation`,
  `claude_escalation_ack`): if a conversation was already escalated for the same issue,
  the Watchman defers (track escalation ids; skip overlapping promises).
- **Watch-only / dry-run:** `WATCHMAN_DRYRUN=1` (default ON at launch) → the loop runs,
  logs every ticket it *would* open to a log/preview, posts **nothing** to channels.
  Owner flips to `0` to go live. (Mirrors `PRICE_APPLY_DRYRUN`.)
- **Cost:** one AI call per conversation per quiet window; skip conversations with no
  new activity; cap conversations processed per tick.
- **Idempotency on deploy:** first `@tasks.loop` iteration must not re-open closed
  tickets (persisted markers).
- **Bilingual** cards (AR primary / EN), Najdi tone.

---

## 9. New env vars

| Var | Default | Purpose |
|-----|---------|---------|
| `WATCHMAN_ENABLED` | `0` | Master on/off for the whole feature |
| `WATCHMAN_DRYRUN` | `1` | Watch-only; log would-be tickets, post nothing |
| `WATCHMAN_QUIET_MIN` | `45` | Minutes of silence before a convo is analyzed |
| `WATCHMAN_GAPS_CHANNEL` | — | Discord channel id for guide-gap tickets |
| `WATCHMAN_PROMISES_CHANNEL` | — | Discord channel id for promise tickets |
| `WATCHMAN_GUIDE_OWNER` | — | Role/user id @mentioned on guide-gap tickets |
| `WATCHMAN_MANAGER_ROLE` | — | Role id for promise escalation |
| `WATCHMAN_NAME_MAP` | — | JSON: Hostaway responder name → Discord user id |
| `WATCHMAN_ACTION_DUE_H` | `6` | Hours until an "action" promise is overdue |
| `WATCHMAN_MONEY_DUE_H` | `24` | Hours until a "money" promise is overdue |
| `WATCHMAN_ESCALATE_AFTER_H` | `3` | Hours overdue before escalating to manager |

---

## 10. Testing & verification

- **Step 0 probe** results recorded before building real logic.
- **Synthetic conversation tests** (this repo's rule): feed fake conversations into the
  AI-pass parser + ticket logic and assert: a planted gap → one gap ticket; a planted
  promise → one promise ticket attributed correctly; pleasantries → nothing; duplicate
  gap → "+1" not a second ticket; unknown sender → unassigned.
- **Lifecycle test:** overdue → nudge → escalate → Done stops it.
- **Dry-run test:** with `WATCHMAN_DRYRUN=1`, zero channel posts.
- Standard repo gates: `py_compile`, `pyflakes`, `unittest`.

---

## 11. Rollout

1. Land Step 0 probe; run on Railway; record findings.
2. Build the loop + AI pass + stores + both ticket types, **`WATCHMAN_DRYRUN=1`**.
3. Owner watches the preview/log for a few days; tune prompts, deadlines, name map.
4. Flip `WATCHMAN_DRYRUN=0` to go live.

---

## 12. Open items to confirm during planning

- Exact `WATCHMAN_NAME_MAP` contents (depends on Step 0a).
- Which apartments have readable guide pages (depends on Step 0b).
- Whether guide-gap tickets should also notify the owner directly, or only the channel.
