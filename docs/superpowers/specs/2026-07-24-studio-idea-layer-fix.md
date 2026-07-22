# Ouja Studio — fix the Signal→card layer (the ideas are slop)

Date: 2026-07-24. Scope: `ideas.py`, `plan.py`, `factory.py`, `virality.py` (fix output only),
`engine.parse_ideas` (sanitize only), the phone card. **Do NOT touch** the signal bus,
collectors (`internal.py`/`external.py`/`mine.py`), the learn loop, or the ranking blend.

---

## STAGE 0 — DIAGNOSIS (no code changed)

### 0.1 The "children / baby / «is there a problem?»" anecdote — traced

**Finding: it is NOT invented, and it is NOT backed by a signal `sid`.**

- It comes from the **guest-story path**, not the signal path. `mine.py` mines Hostaway
  conversations into `studio_stories` rows (keyed by `convo_id`), and `ideas.generate_for_story`
  turns one story into cards.
- Those cards get **`signal_sid = ""`** — hard-coded at `ideas.py:110`. They are grounded on the
  story's *angle/title text*, not on a signal.
- `v=signals` reads the `studio_signals` table. Stories live in `studio_stories` — a different
  table. So the anecdote **correctly appears nowhere in the feed**: it was never a signal.
- The connective framing ("«is there a problem?»", "not appropriate for children") is the model's
  **paraphrase of a conversation**, produced with no gate binding the script to verifiable content.
  This is the fabrication surface: not invented numbers, but invented *framing* around a real chat.
- **Root of "one anecdote → 3 cards":** `generate_for_story` calls `_stamp(parse_ideas(raw), …)`
  with **no per-source cap**. `parse_ideas` returns up to 6 cards; `_stamp` keeps every one whose
  **title+angle** fingerprint is novel (`ideas.py:123`). Three differently-worded cards on the same
  story all pass, because novelty is measured over *wording*, never over *source*.

Verdict for the plan: the story path is a real data source but it **breaches the grounding
contract** (no `sid`, unverified connective claims, N-cards-per-source). Fix = mint a real
`guest_story` signal from the story before generating, ground the card on that `sid`, and cap to one.

### 0.2 The generation template (`ideas.py`) — the beat-sheet is REQUESTED

Both `IDEAS_SYSTEM` (line 28) and `SIGNAL_IDEAS_RULES` (line 64) literally ask the model for:

    "script": ["نقاط السيناريو بالترتيب مع توقيت تقريبي مثل (٠-٣ث)"]

The rigid `(٠-٣ث)` timestamp grid is **prompted for by name**. Every card is identical-shaped
because we ask for one shape. This is defect #1's root cause, in one line.

### 0.3 Novelty fingerprint — over wording, not grounding

`ideas.py:123` and `plan.py:50` both compute the key as
`novelty_key(visual_title + " " + angle)`. Nothing keys on `signal_sid`. So the same fact yields
multiple cards (defect #2) and the daily set reuses a few signals (defect #5). `signal_id()` exists
and is content-addressed over the fact — the right handle is already there, just unused for dedup.

### 0.4 Virality "fix" text — the same list, and it flags what we just caused

`virality.audit` (line 269-280) collects **every** factor under `WEAK=0.6` and returns them all,
sorted by weight. Because every card shares one shape and buries its number, every card fails the
same factors → the identical "حط الرقم في أول جملة" + "زد الانعطافات" pair on nearly all cards
(defect #4). And `specificity`'s fix — "put the number first" — fires because the generator itself
never puts it first (defect #3): we produce the flaw, then flag it.

### 0.5 Daily selection — spread exists, but not over the grounding fact or audience

`plan.choose` spreads over audience / signal_family / trigger (`_card_keys`, line 23) and rewards
variety — but **not over `signal_sid` and not over shape**, and there is **no escape-niche
guarantee**. Two cards on the same fact can co-exist in a set as long as their titles differ.

### 0.6 Map: defect → root → fix

| # | Defect | Root cause | Stage |
|---|--------|-----------|-------|
| 1 | One rigid template | prompt asks for the `(٠-٣ث)` grid | 3 |
| 2 | One anecdote → 3 cards | novelty over wording, not `sid`; story cap missing | 2 |
| 3 | Hooks bury the number | no number-first constraint in the generator | 3 |
| 4 | Boilerplate fixes | `audit` returns all weak factors; every card fails the same ones | 4 |
| 5 | No diversity control | spread ignores `sid`/shape/audience-balance | 5 |
| 6 | Not the owner's voice | prompt is an AI beat-sheet, not a Najdi talking spec | 3 |

---

## BUILD PLAN

- **S1 grounding:** every card resolves to a real `sid` or does not render. Mint a `guest_story`
  signal from a story so story cards get a real, feed-visible `sid`. Script may reference only the
  signal's fact/quote. Test: ungrounded card rejected.
- **S2 one sid = one card:** dedup fingerprint = `signal_sid`. `generate_for_signal` skips a sid that
  already has a live card and persists exactly one. Test: one sid → one card.
- **S3 kill the grid:** new `shapes.py` (7 shapes). Prompt rewritten → flowing first-person Najdi,
  number-first, hook/interrupt/loop as constraints not a printed scaffold. `parse_ideas` strips any
  `(N-Mث)` tokens (defense in depth). Number-first enforced by candidate selection. Test: number-first
  + no timestamp grid.
- **S4 one fix:** `audit` returns the single weakest factor's fix, suppressed when satisfied.
- **S5 daily diversity:** `choose` blocks duplicate `sid` in a set, spreads shape, guarantees ≥1
  escape when available. Test: no duplicate sid in a set.
- **S6 UI:** phone card /critique + /polish — prominent الإشارة block, flowing script, one fix, tags.

Synthetic e2e: real signals → daily set → assert ≥3 shapes, ≥3 sids, ≥1 escape, number-first, no
`(N-Mث)` anywhere, zero ungrounded cards.
