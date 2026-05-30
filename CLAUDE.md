# CLAUDE.md — Ouja Residence Bot

> Read this fully at the start of every session. It encodes how this project works
> and the specific traps that have caused real bugs. Follow the verification routine
> before ever saying a change is "done."

## What this is
A 24/7 Python bot for **Ouja Residence** (عوجا) — a Riyadh-based short-term-rental /
property-management company running ~49–69 branded units across premium compounds,
on **Hostaway** (PMS, account ID 147296) + **Airbnb**. The bot runs Discord automation
(turnover cleaning channels, escalations, an AI guest-message assistant called المساعد/فيصل,
knowledge base) **and** serves a bilingual web **Dashboard / Control Center** with live
Hostaway data, revenue reports, dynamic-pricing, and a strategies tracker.

## Stack & layout
- **Language:** Python 3 (discord.py >= 2.4, aiohttp >= 3.9, requests, tzdata).
- **Almost everything lives in one file: `bot.py`** (~4,000 lines). Other files:
  `requirements.txt`, `Procfile` (`web: python bot.py`), `assignments.json`.
- **The web dashboard is a single large HTML/CSS/JS string** assigned to
  `DASHBOARD_HTML` inside `bot.py`, served by an aiohttp web server the bot runs.

## How it deploys (IMPORTANT)
- GitHub repo: **Ouja-Turnover** under account **oujaresidence-source**.
- **Pushing to GitHub auto-deploys on Railway** (the "worker" service). There is no
  separate build step. After a push, Railway restarts the container.
- The owner has **no coding background** and reviews results by screenshot/video, in
  Arabic + English. Keep explanations plain. Prefer changing **only `bot.py`** unless a
  dependency genuinely changed (then also `requirements.txt`).
- Public dashboard URL pattern: `https://worker-production-*.up.railway.app/dashboard`
  (token-gated via `DASHBOARD_TOKEN`).

## Owner / product conventions
- **Bilingual everywhere:** Arabic (Najdi dialect, اللهجة النجدية) + English. Team-facing
  UI is Arabic-first; the dashboard has an AR/EN toggle.
- **Currency:** Saudi Riyals (SAR / ر.س).
- **Tone:** casual, natural, not robotic or corporate.
- **Apartment names always start with `Ouja |`** and stay short (<50 chars), feature
  "self-entry," and read clearly for Saudi guests.
- **Saudi context matters:** weekend is **Thursday–Friday / Fri–Sat**; demand spikes at
  **Eid al-Fitr, Eid al-Adha, National Day, Founding Day, Riyadh Season**; end-of-month
  **salary cycle** lifts demand. Target occupancy ~95% (excluding Ramadan).

## KEY ENV VARS
Required: `HOSTAWAY_ACCOUNT_ID=147296`, `HOSTAWAY_API_KEY`, `DISCORD_TOKEN`,
`DISCORD_GUILD_ID`, `ANTHROPIC_API_KEY`, `DASHBOARD_TOKEN`, `STATE_DIR=/data`.
Behavior flags:
- `PRICE_APPLY_DRYRUN` — if `1`, pricing/strategy **computes but does NOT write** to
  Hostaway. Set `0` for real price writes. (Frequent source of "it didn't work" confusion.)
- `ASSISTANT_AUTO` — if `1`, the assistant auto-sends high-confidence replies; default `0`
  means everything queues for human approval (so the auto-replies log stays empty until on).
- `ASSISTANT_AUTO_CONF=0.85`, `ESCALATE_BELOW=0.55`.
- `PRICING_STRATEGY_ENABLED=1`, `PRICING_STRATEGY_MIN=10`, `PRICE_OPP_HORIZON=45`.
- `DASH_REFRESH_MIN=7`, `REVENUE_MAX_PAGES=60`, `REVENUE_DEBUG=1`.

## TRAPS THAT HAVE CAUSED REAL BUGS — read before editing
1. **`DASHBOARD_HTML` is a plain triple-quoted string, NOT an f-string.** All `{ }` are
   literal CSS/JS braces. Do **not** introduce Python `{var}` interpolation into it. Inside
   the JS, don't use raw `\n` / `\s` escape sequences in string literals that get mangled —
   prior code used `String.fromCharCode(10)` and ` *` regex instead.
2. **Tab labels resolve via `t()[id]`.** The tab bar is built from a `tb` array of
   `[id, emoji]`. Each tab `id` (today, ov, inbox, rev, pr, strat, auto, log) **must have a
   matching i18n key of the same name in BOTH `T.ar` and `T.en`.** A mismatch renders the
   literal word **"undefined"** in the tab. (This exact bug happened with `strat`.)
3. **Panels are shown via `showPanel()` / JS classes** — do not hardcode `class="panel on"`
   in the HTML for more than the default panel; it caused a panel-mismatch bug.
4. **Reservation history pagination truncates (~6,000 rows).** Counting current occupancy
   from the full history undercounts in-house stays. For "tonight"/occupancy, use a
   **targeted Hostaway query** that filters by arrival/departure date window
   (`fetch_inhouse`) rather than scanning all history.
5. **Editing this huge file is error-prone.** Make minimal, targeted edits. After ANY edit,
   re-view the surrounding code before the next edit (don't edit from stale memory).

## Hostaway API notes (confirmed working)
- Auth: `POST /v1/accessTokens` (client_credentials) → bearer token. Helpers `api_get` /
  `api_post` / `api_put` include 403/429 retry with backoff.
- Reservations: `status` `new`/`modified` = confirmed; fields `arrivalDate`,
  `departureDate`, `nights`, `totalPrice`, `listingMapId`, `guestName`. Date filters work:
  `arrivalStartDate` / `arrivalEndDate` / `departureStartDate` / `departureEndDate`. Use
  `limit` (≤ ~200 per page typical) + `offset`.
- Calendar: `GET /listings/{id}/calendar?startDate&endDate` → days with `isAvailable`,
  `price`, `reservationId`. Write a price: `PUT /listings/{id}/calendar`
  `{startDate,endDate,isAvailable:1,price:<int>}`.
- Messages: `GET /conversations/{id}/messages`; `isIncoming`(1=guest), `body`, `id`, `date`.
  Send: `POST /conversations/{id}/messages` `{body, communicationType}`.

## VERIFICATION ROUTINE — run before declaring any change done
From the repo root:
```
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py        # must compile clean
python3 -m pyflakes bot.py                                  # ignore "imported but unused"
```
Then verify the embedded dashboard string is intact (extract `DASHBOARD_HTML` and check):
- `count("{") == count("}")`, `count("(") == count(")")`, `count("`") is even`.
- Every `tb` tab `id` has a label key in both `T.ar` and `T.en`.
And run a quick **synthetic-data logic test** for any new computation (e.g. feed fake
reservations into the new function and assert the numbers) before trusting it on live data.

## Design skills installed — USE THEM EVERY SESSION
Three design skills live in `.claude/skills/` and MUST be applied to any UI work:
- **impeccable** (`.claude/skills/impeccable/`) — design-quality language + references
  (typeset, colorize, layout, animate, interaction-design, adapt, clarify) and a `critique`/
  `audit`/`polish` process. Anti-patterns to avoid: pure #000/#888 (tint neutrals instead),
  gradient text, glassmorphism-as-decoration, cards-nested-in-cards, gray text on color,
  bounce easing, generic Inter-for-everything. (Its `detect.mjs` needs Node, absent locally —
  apply the rules by hand.)
- **emil-design-eng** (`.claude/skills/emil-design-eng/`) — micro-interaction craft: custom
  ease-out `cubic-bezier(0.23,1,0.32,1)`, scale(.97) on press, never scale(0), transform/opacity
  only, <300ms UI motion, don't animate frequently-seen/auto-refreshed elements, respect
  prefers-reduced-motion.
- **superpowers** (methodology only — NOT installed as a plugin; can't self-install the
  marketplace plugin from inside a session): plan → build → verify, evidence over claims,
  simplicity, no skipping.
The locked design system already lives in `DASHBOARD_HTML`'s `:root` (tinted warm neutrals +
gold accent scale, IBM Plex Sans Arabic / Inter / JetBrains Mono). Reuse those tokens; don't
invent per-view colors.

## Working style for this repo
- **Audit before changing.** When asked for something big, first read the relevant code and
  state the plan; don't rewrite broadly.
- Keep the bot **stable** — it runs the live business. Prefer additive, reversible changes.
- After changes pass verification, **commit with a clear message and push** (this triggers
  the Railway redeploy). Tell the owner in plain language what changed and what to check.
