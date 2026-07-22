# Ouja Studio v3 — HANDOFF

**Date:** 2026-07-23 · **Branch:** `main` · **Head:** `8adb80c` · **Deployed & verified live on Railway**
**Read first:** `/CLAUDE.md`, then `docs/superpowers/specs/2026-07-23-studio-v3-plan.md`

---

## 1. What this was

Ouja Studio is the TikTok content-idea engine for Ouja Residence (Riyadh short-term rentals,
~53 units). The owner, Faisal, is a Saudi creator posting ~3 TikToks/day; the recurring
problem is «وش أصوّر اليوم؟».

**Before this work (v2):** the studio had exactly ONE signal source — guest conversations
from Hostaway — and zero web awareness. The grounding fact behind an idea was never stored,
so "every idea must reference a real signal" was unenforceable. 5 triggers instead of the
spec's 7. The learn loop only aggregated by `story_type` and showed the owner nothing. No
calendar, no manual input, no instant idea, no repetition guard.

**After:** a signal bus with 11 sources, live web search, a research-backed structural audit,
a ranked phone page, full Discord control, and one command that runs everything and hands back
one file.

---

## 2. Shipped, in order

| Commit | What |
|---|---|
| `fb179c4` | Signal contract, 7 triggers, novelty fingerprint, learn engine (pure + TDD) |
| `d6c3e1d` | The signal factory: external web search + internal Hostaway collectors + hook bank + plan + UI |
| `753c0a4` | Discord commands + the ranked phone page `/s/{token}` |
| `cc25930` | Slash commands, mass-generation factory, research-backed virality audit |
| `8adb80c` | `/everything` — one command, whole pipeline, one ready `.md` file |

---

## 3. Architecture — the signal bus

Everything that can ground an idea becomes a **Signal** row (`studio_signals`). Ideas hang off
signals. Guest stories keep their own table and behave as one source among many, so the v2
mining pipeline is intact and untouched.

```
Signal = { sid, family, source, title, fact, detail, url, as_of, strength, status }
  family  internal | external | manual
  source  occupancy pricing reviews ops season insider guest_story   (internal)
          regulation market global_trend trend                        (external)
          manual                                                      (manual)
```

**The anti-fabrication gate is `engine.signal_ok()` and it FAILS CLOSED.** Empty `fact` →
rejected. `family == "external"` without a valid `http(s)` url or a `YYYY-MM-DD` `as_of` →
rejected. This is the single most important invariant in the system: it is what makes
"never fabricate" a property of the code rather than a hope about a prompt. Do not soften it.

`sid` is content-addressed (sha1 over the normalized fact), so re-collecting the same fact
refreshes rather than duplicates.

### Module map (`studio/`, 5.5k lines)

| File | Role | Pure? |
|---|---|---|
| `engine.py` | Signal contract, triggers/formats, novelty fingerprint, model-output parsing | ✅ |
| `learn.py` | Per-dimension performance stats, lift, insights, `strength_of()` | ✅ |
| `virality.py` | Research-backed structural audit + concrete fixes | ✅ |
| `rank.py` | Blends history + craft + signal + freshness + prior → 0-100 | ✅ |
| `plan.py` | Daily 3 + week calendar + `instant()` | mostly |
| `hooks.py` | 50-hook bank by trigger, per-source trigger hints | ✅ |
| `export.py` | `render()` the single Markdown file | `render()` ✅ |
| `internal.py` | Ouja's own Hostaway data → signals | computations ✅ |
| `external.py` | Live web search → signals (4 streams) | no |
| `factory.py` | Mass sweep: every unused story + signal → cards | no |
| `pipeline.py` | The 6-stage `/everything` run | no |
| `ideas.py` | Story→cards and Signal→cards generation | no |
| `mine.py` | v2 conversation miner (unchanged) | no |
| `db.py` | `studio_*` tables in `brain.db` | no |
| `mobile.py` | Phone page `/s/{token}` + its API | no |
| `routes.py` | `/studio` dashboard page + `/api/studio/*` | no |
| `notify.py` | Morning digest text | ✅ |

---

## 4. The ranking, and what it is not

`rank.score()` returns 0-100, blended from five ingredients in **descending trustworthiness**:

1. **History** (`learn`) — what actually earned views on *his* account. Weighted to **exactly
   zero** until `MIN_SAMPLE=3` posts exist for a value. This is the only ingredient allowed to
   dominate, and only once earned.
2. **Craft** (`virality`) — is the card *built* the way the research says short-form must be built.
3. **Signal strength** — the collector's judgment of the underlying fact.
4. **Freshness** — dated external signals decay over a 7-day window.
5. **Prior** — the playbook's read on trigger/format. Deliberately weak: it's a guess about
   TikTok in general, while (1) is a fact about Faisal.

`studio/virality.py` is a **structural audit, not a view predictor**. Nobody can predict views
from a script, and a number that pretends to is worse than none. 8 factors, each traced to the
verified 2026-07-08 research pass and **tiered by evidence quality**:

- **VERIFIED (weight 1.0):** completion is the top ranking signal · the first 3s decide ·
  saves/shares outweigh likes · negative feedback SUPPRESSES · specificity beats generality.
- **DIRECTIONAL (weight 0.5):** the 21-34s completion band · a pattern interrupt every ~4s.
- **REFUTED and deliberately NOT scored:** "rage gets amplified regardless of sentiment".
  The research killed it. Do not reintroduce it.

Every weak factor returns a concrete Arabic fix («خلّ آخر جملة ترجع للهوك»), shown on the phone
card as «وش تعدّل قبل ما تصوّر» and written into the export file. A score without a fix is a grade,
not a tool.

---

## 5. Surfaces

### Discord (the owner's primary surface — he does NOT use the dashboard)

Channel `#ouja-studio` (`STUDIO_OPS_CHANNEL`). The help card is pinned **only into an empty
channel** (`_studio_ensure_channel` checks history first) — a redeploy must be silent. See the
Musaed rapid-redeploy spam incident.

| Slash | Does |
|---|---|
| `/everything [count] [web]` | The full 6-stage run; posts summary + **attaches the file** |
| `/file` | Same document instantly, no generation, no cost |
| `/today` `/idea` `/ideas` | Plan / instant / shelf, ranked |
| `/factory [count]` | Mass sweep only |
| `/signals` `/news` | Collect internal / run the live web search |
| `/posted <id> <views>` | Log a video — **this is the learn loop's only input** |
| `/studio` | The command card |

`!ouja` prefix twins still exist (`اليوم فكرة أفكار إشارات أخبار نشرت كل-شي`).

> **Slash-command names MUST stay ASCII lowercase.** Discord permits Arabic names, but ONE
> rejected name fails the whole `bot.tree.sync()` and takes down every slash command in the bot,
> including `/update` and `/guests`. Arabic goes in `description=`. Locked by
> `tests/test_studio_mobile.py::TestSlashCommands`.

### Phone page — `/s/{token}`

Token-gated, no login (a login form on a phone is the friction this removes). Token persisted in
`studio_link.json` and **must not rotate** — a rotating token silently breaks every link already
sitting in Discord. One column, ranked, thumb-sized filter chips (audience / source family /
trigger / format), full script, one-tap copy, and «صوّرته / نشرته + المشاهدات» logging in place.

`GET /s/{token}/export.md` — the same single file, always current, bookmarkable.

### Dashboard — `/studio`

Still works (signal feed, today, manual box, learning panel). No longer the way in.

---

## 6. Environment

| Var | Default | Meaning |
|---|---|---|
| `STUDIO_ENABLED` | `1` | Master switch |
| `STUDIO_WEB_SEARCH` | `1` | Live web search. **Costs money per run** — one run/day in the digest |
| `STUDIO_NOTIFY_DRYRUN` | `1` | **Still dry-run.** Flip to `0` for the 09:00 Discord digest |
| `STUDIO_DIGEST_HOUR` | `9` | Riyadh |
| `STUDIO_OPS_CHANNEL` | `ouja-studio` | |
| `STUDIO_DAILY_SIGNAL_IDEAS` | `4` | Signals turned into cards in the daily loop |
| `WEB_SEARCH_MAX_USES` | `6` | Searches per `claude_search_json` call |

Web search runs on Anthropic's **server-side `web_search_20250305` tool** via
`bot.claude_search_json()` — same `ANTHROPIC_API_KEY`, no new vendor, no new key.

Host caps wired in `bot.py`'s `_studio.wire({...})`: `claude_search`, `inhouse`, `res_window`,
`forward_calendar`, `reviews`, `public_base` (callable). Without these four data taps
`internal.gather()` logs failed taps and returns nothing — silently, by design.

---

## 7. Verification routine

```bash
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py studio/*.py finance/*.py      # ignore "imported but unused"
node --check finance/static/erp.js
python3 -m unittest discover -s tests -p "test_*.py"     # 986 green at handoff
```

Then the three embedded page strings — `DASHBOARD_HTML`, `STUDIO_PAGE_HTML`, `MOBILE_HTML`:

> **TRAP, cost real time on 2026-07-23:** do NOT regex-slice the *raw source text* and parse it.
> Python escapes (`\'`) have not been evaluated yet, so you get **false** syntax errors. Extract
> the **evaluated** string (`ast` Constant, or `import bot`) before `node --check`/esprima.

```python
import ast, re
tree = ast.parse(open("bot.py", encoding="utf-8").read())
# ... find the Assign whose target is DASHBOARD_HTML, take node.value.value
# then node --check each <script> block
```

All three page strings must hold: balanced braces/parens, and **zero backslashes** in
`STUDIO_PAGE_HTML` and `MOBILE_HTML` (they are normal triple-quoted strings — a `\n` typed into
the JS becomes a real newline in Python and kills the whole script, so the page won't even load).
Use `String.fromCharCode(10)`.

---

## 8. State: what is done, what is not

### Done and verified
- 986 tests green. 16 studio test files.
- All three page JS bundles parse under `node --check` (evaluated strings).
- Deploys confirmed live by probing route status transitions (404 → 502 → 401/403), not by assumption.
- End-to-end synthetic runs: signal → grounded card → plan → learn; factory sweep; full pipeline → real document.

### NOT verified — the honest list
1. **The live web search has never run against the real API.** Every test uses a fake. The first
   real execution happens on Railway when someone runs `/news` or `/everything`. If it returns
   nothing twice in a row, read the logs before assuming it's broken — signals without a source
   URL are *supposed* to be dropped.
2. **No formal `/impeccable` or `/ui-ux-pro-max` critique pass** was run on the pages. The
   documented rules from CLAUDE.md were applied by hand (locked tokens, `cubic-bezier(0.23,1,0.32,1)`,
   `scale(.97)` press, `prefers-reduced-motion`). A real visual critique pass is still open work.
3. **The learn loop is empty** and stays empty until Faisal logs posted videos with view counts
   (`/posted` or the phone page). Until then `history_points` is exactly 0 and ranking runs on
   craft + signal + freshness + prior. This is correct behaviour, not a bug.
4. **The morning digest is still `STUDIO_NOTIFY_DRYRUN=1`.** Nothing posts to Discord at 09:00
   until the owner flips it.

### Open / obvious next
- Owner-facing control over the factory budget from the phone page (currently Discord-only).
- TikTok API pull to replace manual view logging (spec I1 called it optional).
- A `/whatsapp` share of the export file (he lives in WhatsApp too).
- The signal feed grows unbounded aside from `prune_signals(400)` — revisit if `brain.db` grows.

---

## 9. Landmines inherited from this repo

1. `DASHBOARD_HTML` / `STUDIO_PAGE_HTML` / `MOBILE_HTML` are **normal** triple-quoted strings.
   Zero backslashes. Parse the evaluated string, never the raw source.
2. `brain.db`: no WAL, `closing(connect())`, `journal_mode=DELETE`, additive `ALTER` migrations only.
3. Reservation history pagination truncates (~6,000 rows). Use `fetch_reservations_window()` /
   `fetch_inhouse()`, never `get_reservations_cached()`.
4. `@tasks.loop` first iteration runs on **every deploy** — guard anything that posts.
5. Never rapid-redeploy this bot (the Musaed auto-send spam incident).
6. Railway deploys from `main` **only**. Verify with an `/api/` route on `oujares.com` — a `/stay`
   path hits a catch-all and returns 200 regardless.
7. `bot.py` is ~57k lines. Make minimal targeted edits and re-read surrounding code before the
   next edit; never edit from memory.

---

## 10. First things to do next session

1. Ask whether `/everything` has actually been run, and whether the web search returned real
   sourced facts. That is the one unverified path.
2. If it returned nothing twice, check Railway logs for `claude_search_json` errors before
   touching `external.py` — the drop-unsourced-facts behaviour looks identical to a failure.
3. If the owner has started logging views, check `learn.insights_ar()` output — the first real
   findings are the moment the ranking stops being generic.
