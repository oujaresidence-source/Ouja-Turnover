# Ouja Studio v2 — Design Spec (2026-07-08)

Companion: [research brief](2026-07-08-studio-v2-research-brief.md). Approved by owner
2026-07-08 (all three forks → hero-arc, auto daily digest, purge & re-scan).

## Problem
Studio v1 (`studio/` package, /studio page) surfaces weak content: negative and cliché
story cards that would hurt the Ouja brand rather than showcase it. Root causes found in
code:
1. **The editorial prompt hunts for drama.** `mine.TRIAGE_SYSTEM` defines a "story" as
   tension/anger/conflict/emergency/cancellation. The system is *designed* to find negativity.
2. **No brand-impact filter.** A story that makes Ouja look bad ships identically to one that
   makes it look great.
3. **Idea cards never justify themselves** — no "why this will work" grounded in mechanics.
4. **Small + manual.** Scans only ~300 conversations, only on a button press. No daily rhythm.

## Goals
- Flip the lens to POSITIVE, brand-forward storytelling that proves Ouja does exceptional work.
- Ground every hook/idea in the verified 2025–26 research (see brief), and ban burned-out clichés.
- Scan the last ~2,000 real conversations; run a daily auto-scan + Discord digest.
- Add a "why it works" rationale to every idea card.
- Purge weak legacy cards and re-mine, preserving posted/filmed performance history.

## Non-goals (YAGNI)
- No new storage engine (reuse brain.db `studio_*`). No public exposure (stays login-gated).
- No video generation / posting to TikTok. No Hostaway writes (read-only, unchanged).
- No full analytics dashboard — the learn-loop stays a light prompt hint, not a new UI.

## Architecture (unchanged shape; same DI pattern)
`studio/` package: `engine.py` (pure), `playbook.py` (prompt asset), `mine.py` (miner +
prompts), `ideas.py` (idea generator), `db.py` (brain.db), `routes.py` (API + /studio page),
`host.py` (DI bridge). bot.py wires it and adds ONE daily loop.

### A. `playbook.py` — rewrite from the research brief
- `BRAND`: keep Faisal's identity + transparency law; **add the positive editorial mandate**
  ("prove Ouja does exceptional work; a problem is only ever the setup for the save").
- `HOOK_RULES`: replace with the verified working-list (Identity Call, Open Loop, Confession,
  Contrarian Strike, Proof-first, specific-pain question) + the burned-out **ban-list**
  (لن تصدق / انتظر للنهاية / greetings / cold "هل تعلم؟" / rage-bait / fake stats).
- `STORY_RULES`: keep the completion-first structure (hook ≤3s, foreshadow, but/therefore,
  pre-planned last line, rewatch loop, 21–34s golden / 30–60s ok), refresh citations to the
  verified TikTok-primary facts (completion is the top signal; follower count is not a factor;
  saves/shares > likes; on-screen text for mute; region favors Saudi creators).
- Add a `WHY_MECHANICS` string the ideas prompt uses to write the per-card "why it works".

### B. `engine.py` — pure logic (TDD-locked)
- **New taxonomy** `STORY_TYPES`: `hero_save, transformation, transparency_numbers,
  day_in_life, hospitality_wow, weird_delight, heartwarming, loyal_return, operational_craft,
  other`. (Removes the negative buckets.)
- **Brand gate** `brand_ok(triage) -> bool`: story qualifies for a premium/idea pass only if
  `triage["brand_safe"]` is true AND `triage["positive"]` is true AND type is in the new list.
  Deterministic; the *judgment* comes from the model flags, the *rule* is pure and tested.
- `parse_triage`: add required bool fields `brand_safe`, `positive` (default False when absent
  → fail closed). Keep score 0–10, one_line, type.
- `parse_story`: add `angle` (the positive/hero framing) — optional string.
- `parse_ideas`: add **`why_it_works`** (required non-empty, else card dropped) and a
  deterministic **hook ban-list check** `hook_is_clean(hook) -> bool`; a card whose
  `hook_spoken` or `visual_title` trips the ban-list is dropped.
- `BANNED_HOOK_PATTERNS`: substring list (Arabic + English) — لن تصدق، ما راح تصدق،
  انتظر للنهاية، شوف الآخر، هل تعلم، pov:, you won't believe, wait for it, etc.
- Keep unchanged: `qualifies*`, `build_transcript`, `scrub_names`, `is_stay`, `reservation_id`.

### C. `mine.py` — prompts + scale + incremental daily scan
- `TARGET_QUALIFIED` 300 → **2000** (deep backfill). `PULL_CAP` raised (e.g. 6000).
  `MAX_PREMIUM` per deep run raised to a safe budget (e.g. 250) — premium only on brand-safe
  high scorers, so real spend is far lower.
- `TRIAGE_SYSTEM` rewritten: judge "does this SHOW Ouja doing great work / would it make
  POSITIVE brand content?" Return `brand_safe`, `positive`, `score`, new-taxonomy `type`,
  `one_line`. Explicitly: a complaint/emergency scores high ONLY if it resolves into a win.
- `STORY_SYSTEM` rewritten: extract the positive/hero arc; add `angle`. Same privacy rules.
- New verdict `blocked_brand` for stories the gate rejects (visible in scan counts).
- **`run_daily_scan()`**: scans only NEW conversations since the cursor with a small premium
  budget (e.g. 40); returns the day's best 1–3 fresh stories for the digest. Idempotent via
  `studio_scanned`.
- **`reset_for_deep_scan()`** (called by the deep-scan button): delete `studio_stories` with
  status in (new,hidden), delete `studio_ideas` with status in (new,shortlisted,rejected),
  clear `studio_scanned` — but KEEP posted/filmed ideas + their stories.

### D. `ideas.py` — grounded generation + light learn-loop
- `IDEAS_SYSTEM` rewritten around the new playbook; each idea MUST include `why_it_works`.
- Before generating, if posted ideas with views exist, pass a one-line hint of the
  best-performing archetype(s) into the prompt (`db.top_posted_archetypes()`).

### E. `db.py`
- Add columns: `studio_stories.angle TEXT`, `studio_ideas.why_it_works TEXT` (ALTER-if-missing,
  additive; existing rows default empty).
- `top_posted_archetypes()` → list of (type, total_views) from posted ideas joined to stories.
- `reset_for_deep_scan()` deletes as in C. Keep all other helpers.

### F. `routes.py` — /studio page (NO backslashes; esprima-parsed)
- Idea card renders **"💡 ليش بيشتغل"** block from `why_it_works`.
- New positive `TYPE_AR` labels. Story card shows a green "hero-arc/brand-safe" tag.
- Second scan button **"🔄 مسح عميق (٢٠٠٠)"** → POST `/api/studio/deep-scan` (calls
  reset_for_deep_scan then the big scan). Keep the normal incremental scan button too.
- New API: `POST /api/studio/deep-scan`. All still `_safe` (login-gated).

### G. `bot.py` — one daily loop (mirrors `schedule_digest_loop`)
- Env: `STUDIO_DIGEST_HOUR` (default 9), `STUDIO_NOTIFY_DRYRUN` (default 1),
  `STUDIO_OPS_CHANNEL` (default a content channel name), reuse `STUDIO_ENABLED`.
- `@tasks.loop(time=…)` `studio_digest_loop`: run `run_daily_scan` in a thread, then if not
  dry-run post an embed to the channel with the day's best story title + spoken hook +
  why-it-works. Dry-run just logs. Started in the same place as `schedule_digest_loop`.
- A small `studio/notify.py` builds the digest embed (keep bot.py thin).

## Testing (TDD — write first)
`tests/test_studio_engine.py` (extend): new taxonomy accepted / old negative types normalize
to other; `brand_ok` truth table (brand_safe∧positive∧valid-type); triage fail-closed when
flags absent; `parse_ideas` drops cards missing `why_it_works`; `hook_is_clean` rejects each
banned pattern and passes clean hooks. Keep all existing qualify/transcript/scrub tests green.
`tests/test_studio_mine.py`: daily-scan picks only unseen convos; deep-scan reset keeps
posted/filmed. `tests/test_studio_db.py`: ALTER adds columns idempotently; reset semantics;
top_posted_archetypes. `tests/test_studio_contract.py`: /studio JS still esprima-parses; new
API route registered; no backslashes in page.

Plus a synthetic-data logic test: feed a fake "AC broke → fixed in 40 min → guest thrilled"
transcript and assert it triages positive+brand_safe as hero_save; feed a fake "guest furious,
left a 1-star, never resolved" and assert brand gate blocks it.

## Verification routine (before declaring done)
`py_compile bot.py`; `pyflakes bot.py finance/*.py studio/*.py`; `node --check
finance/static/erp.js`; `unittest discover tests`; esprima-parse `DASHBOARD_HTML` + the
/studio page `<script>` blocks; DASHBOARD_HTML brace/paren/backtick balance intact.

## Rollout
Additive + reversible. Daily loop ships in DRYRUN (no Discord posts until owner flips
`STUDIO_NOTIFY_DRYRUN=0`). Deep re-scan is owner-triggered (never auto-on-deploy). Commit +
push (Railway auto-deploy). Update the `ouja-studio-content-factory` memory.
