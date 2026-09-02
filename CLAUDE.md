# CLAUDE.md — Ouja Residence Bot

> Read this fully at the start of every session. It encodes how this project works
> and the specific traps that have caused real bugs. Follow the verification routine
> before ever saying a change is "done."

## Owner approval protocol

The owner has no coding background and reviews by screenshot and plain language.
Follow this on EVERY task, without being asked:

**1. Plan before touching anything.** Before the first edit, reply with: what you
understood the task to be; exactly which files you will change and roughly which
lines; what could break if you get it wrong; anything you are unsure about. Then
STOP and wait. Do not edit, create, delete, commit, or push until the owner approves.

**2. Plain language only.** No jargon addressed to the owner. If a technical term is
unavoidable, explain it in the same sentence. Arabic (Najdi) or English, matching
whatever the owner used.

**3. Never without explicit approval:** delete any file, channel, or data; push to
GitHub (auto-deploys to Railway and hits the live business); change anything outside
the files named in the approved plan; "while I was in there" improvements.

**4. Report after.** What changed in plain words; the exact files and line counts
touched; how to undo it in one step; what the owner should click or type to verify.

**5. If the plan changes mid-task, stop and re-ask.** Discovering the job is bigger
than expected is a reason to come back, not a reason to keep going.

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
   (`fetch_inhouse`) rather than scanning all history. **Owner statements/financial
   reports must use `fetch_reservations_window(start, end)` — NEVER
   `get_reservations_cached()`** (the truncation silently dropped the newest months and
   produced a wrong owner statement: the 18,842-instead-of-48,114 bug, fixed 2026-06-10).
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
python3 -m pyflakes bot.py finance/*.py                     # finance package too; ignore "imported but unused"
node --check finance/static/erp.js                          # the ERP SPA JS MUST parse (one bad token = dead login)
python3 -m unittest discover -s tests -p "test_*.py"        # all tests incl. V4 lifecycle + ERP contract (no pytest here)
```
> For `finance/static/erp.js`, `node --check` is the authority — do NOT gate on raw paren
> balance: the file has unmatched `)` inside Arabic/English string literals (e.g. `(≥ 3000)`),
> so the count is legitimately offset. Brace/backtick balance still hold and may be checked.
Then verify the embedded dashboard string is intact (extract `DASHBOARD_HTML` and check):
- `count("{") == count("}")`, `count("(") == count(")")`, `count("`") is even`.
- Every `tb` tab `id` has a label key in both `T.ar` and `T.en`.
- **PARSE THE EMBEDDED JS — brace-balance is NOT enough.** A single bad token kills the whole
  script so the dashboard **won't even log in** (this has bitten twice). `pip install esprima`
  (pure-Python, works offline), then parse every `<script>` block of the *served* HTML:
  ```
  import bot, esprima, re
  for js in re.findall(r"<script>(.*?)</script>", bot.DASHBOARD_HTML, re.S):
      esprima.parseScript(js)        # raises on the offending Line/Col
  ```
  **The #1 cause:** `DASHBOARD_HTML` is a normal (non-raw) triple-quoted string, so any
  `\n`/`\t`/`\u…`/`\s` you type in the JS is consumed by **Python** first. A `\n` inside a
  JS string literal (e.g. `.join('\n')`, a `confirm()` body, even a `//` comment) becomes a
  REAL newline → unterminated string → dead login. Use `String.fromCharCode(10)` for newlines;
  never put a backslash-escape inside the embedded JS.
And run a quick **synthetic-data logic test** for any new computation (e.g. feed fake
reservations into the new function and assert the numbers) before trusting it on live data.

## Employee Schedule & Coverage Calendar (تقويم الموظفين) — the `schedule/` package
The team-leader-spec'd coverage calendar (it SUPERSEDED the earlier `roster/` package — do not
reintroduce roster). A pure, deterministic engine (`schedule/engine.py` — `compute_day`) is the
SINGLE source of truth; the dashboard tab (`view_schedule` + `loadSchedule`/`renderSched*` in
`DASHBOARD_HTML`), the standalone page (`schedule/page.py` → `/team-calendar`), and the optional
morning ops summary all render from it. Storage REUSES `brain.db` via `schedule/db.py` (tables
`schedule_*`). Wired in `start_web_server` via `schedule.wire({...})` + `register_routes(app)`.
- **Model:** each employee owns base apartments + has ONE weekly `off_day` (0=الأحد..6=السبت);
  on an off-day their apartments auto-distribute (count-balanced) to whoever's working; recurring
  per-weekday OVERRIDES pin a unit to a chosen coverer. PLUS an Ouja add-on: ad-hoc date-specific
  LEAVE (`schedule_absences`) treated as an extra day off. Thu/Fri = nobody off = base only.
- **Engine invariants are TDD-locked** (`tests/test_schedule_engine.py`): Sunday 13/13/13/14=53,
  Thu/Fri base 11/12/9/11/10, balance (max−min≤1), override pin, stale-override skip, leave. Run
  before any UI edit. The 53-apartment seed (incl. عهود) is `schedule/seed.py`, owner-editable in
  the Manage tab; «إعادة تعيين للوضع الافتراضي» (POST `/api/schedule/reset`) restores it.
- **`schedule/page.py` has the SAME backslash trap as `DASHBOARD_HTML`** (normal triple-quoted
  string). ZERO backslashes — real newlines + event delegation, no inline-onclick quote-building.
  esprima-parse it (and every DASHBOARD_HTML `<script>`) after edits.
- **Editing** is gated on `can_edit_schedule(request)` = multi-user role in (admin, ops); viewers
  see Today + Weekly but no controls; every write endpoint re-checks it.
- **Share link = `/team-calendar`, read-only, NO login/token.** `GET /api/schedule/day` + `/week`
  are PUBLIC (`_safe_public`, no auth) so the ops team opens the link with nothing — don't re-gate
  them. `manage` + ALL writes stay behind `_safe` (login) AND `can_edit_schedule` (double-gated).
  The dashboard Manage tab has a «رابط فريق العمليات» copy panel (`location.origin + /team-calendar`).
- Env vars: `SCHEDULE_ENABLED`(1), `SCHEDULE_NOTIFY_DRYRUN`(1 — flip to 0 to post the morning
  ops summary), `SCHEDULE_DIGEST_HOUR`(8), `SCHEDULE_OPS_CHANNEL`(team-calendar).

## Design skills are INSTALLED and MUST be used every session
**Superpowers + Impeccable + emil-design-eng** live in `.claude/skills/` and govern all work:
Superpowers = the PROCESS (brainstorm → plan → TDD → build → verify, no skipping); Impeccable =
audit → critique → polish → harden every view (kill AI-slop); emil-design-eng = the FEEL
(micro-interactions, motion, the drawer/transition craft). Use them on every UI change.

## Decoration orders «تنسيق الحفلات» — the `decor/` package
Guests tap «أنا مهتم» on one of the five Ouja Moments packages in `/guide/{slug}`; the button
POSTs to `/api/decor/inquire` **and** opens WhatsApp exactly as before.
- **THE OWNER RULE (2026-07-26), absolute:** a guest's tap creates an **interest and nothing
  else** — no ticket, no thread, no task, no assignment, nobody notified but the DEC
  supervisor. **Only the supervisor opens a request.** Enforced structurally, not by
  discipline: `decor_leads` and `decor_orders` are separate tables (the lead table has no
  assignee/deadline/thread columns), `db.open_order` is the only insert into orders and is
  unreachable from the public endpoint, and `tests/test_decor_flow.py` +
  `tests/test_decor_routes.py` count every other table before/after a tap. Do not "simplify"
  the two tables into one.
- **Capability gate is a STOP, not a wall.** Diamond needs a pool, Signature Silver a jacuzzi,
  Silver a jacuzzi *or* bathtub (`jacuzzi_or_bathtub`, split on `_or_`). Missing → the
  supervisor is refused *unless* they pass an override: `correction` (our sheet was wrong →
  writes the feature, clean order) or `accept_gap` (feature really absent → order is
  **stamped** forever). Unknown unit ≠ missing feature — `db.unit_features` returns `None` vs
  `[]` on purpose; never collapse them. Every override records who + why or it is refused.
- **One stamp, three surfaces.** `engine.capability_stamp` is the ONLY producer of that Arabic
  warning; the thread header, the dashboard row and the vendor message all render it so they
  cannot drift. `accept_gap` also marks feature-bound guest questions «ما ينطبق»
  (`na_input_keys`) — without it, Signature Silver on a jacuzzi-less unit waits forever for
  «عبارة الجاكوزي» and can never dispatch.
- **Cake = its own job** (`decor_cake_tasks`): every pack but Bronze, due `cake.lead_hours`
  (24h, read from the JSON) before the decoration deadline, own state and own escalation.
- **Two prices:** `price_from_sar` is advertising and is NEVER revenue; only the supervisor's
  `final_price_sar` counts.
- `decor_packs.json` is owner-editable **live**: `$STATE_DIR/decor_packs.json` wins over the
  repo seed and is re-read on mtime change; a broken edit keeps serving the last good copy.
- Env: `DECOR_ENABLED`(1), `DECOR_DRYRUN`(**1** — posts nothing; flip to 0 for real Discord
  threads), `DECOR_SUPERVISOR_ROLE`(DEC), `DECOR_OPS_CHANNEL`(تنسيق-الحفلات). Orders open
  Discord **threads**, not channels — deliberately, because ticket channels already hit the
  50-per-category cap once.
- `/api/decor/inquire` is in `_ROLE_EXEMPT_WRITES` (public guest). Every other `/api/decor/*`
  is double-gated: login + `decor` permission. **Existing non-admin users see the tab only
  after the owner ticks it in الصلاحيات** — the whitelist model denies unknown tabs.

## Finance ERP (المركز المالي) traps — mirror of the dashboard traps
The ERP SPA is `finance/static/erp.js` (~4.7k lines, hand-written, NO build step). Same class
of outage as `DASHBOARD_HTML`: one bad token kills the whole SPA so the page **won't even log
in** — `node --check finance/static/erp.js` is now part of the routine, and `tests/` has two
guards (`test_exp4_lifecycle.py`, `test_erp_exp_contract.py`).
1. **Contract drift:** erp.js must read the SHAPE `bot.py` returns. The expense tab badges are
   `{count, sar}` objects — read `.count` (stringifying the object renders `[object Object]`;
   this reached the owner). Every other counter in the ERP is a scalar — don't confuse them.
2. **Optimistic UI must reconcile:** never `removeRow` + success-toast on assumption. Remove only
   the ids the server actually returned (`approved`/`queued`/`verified`); show `blocked` with a
   reason; patch chip counts from `r.tabs`. A no-op that looks like success is the worst kind.
3. **Terminal-state affordances:** `_exp4_tab` gives export-status precedence, so "approving" a
   verified/exported/failed/duplicate/split expense is a silent no-op. `_exp4_approve` refuses
   these with a reason; the bulk bar + per-row both read `expBulkAction(tab)` (approve only on
   pending/needs_action). Never offer an action the state machine can't honor.
4. **Dry-run:** `EXPENSE_POST_DRYRUN` makes export file-only — items legitimately stop at
   `exported` and never auto-verify. Surface it (the `x_dryrun` tag); never read it as a failure.

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

## «مساعد» v3 — the outbound firewall and the risk gate
Musaed's language was already solved; its **governance** was not. Nearly every failure was a rule
that existed only as prose in `ASSISTANT_RULES` with nothing in code enforcing it. v3 converts the
rules that matter into controls. **A prompt is a preference; code is a control.**
- **`outbound_firewall(body, item)` lives in `send_guest_message` (bot.py), above the dedup claim.**
  That is the ONLY point both auto-send channels converge — `post_assistant_card` (the LLM path) and
  `handle_early_checkin_item` (a DETERMINISTIC path that sends directly, with no confidence gate).
  Putting a guard anywhere else guards half the traffic. Six rules: CODE_LEAK, READINESS_CLAIM,
  PLACEHOLDER, LANG_MISMATCH, WRONG_UNIT block; DOUBLE_SIGN strips; dialect only WARNS.
  It **fails CLOSED** — an exception blocks. Blocked drafts return `SEND_FIREWALL_BLOCKED` and drain
  to Discord via `firewall_block_drain` as a red card + an approval card. Never a silent no-op.
- **The readiness carve-out is load-bearing.** A readiness word blocks only when a unit referent
  (`وحدتك/شقتك/your unit/…`) is in the SAME sentence, so a general turnover explanation still sends.
  Do not "simplify" that to a plain word match — it would gag every honest explanation.
- **Auto-send is gated on blast radius, not confidence:** `action == "auto"` is honoured, plus the
  `AUTO_SAFE_INTENTS` ALLOW-list (a deny-list fails open on new intents) and `_is_risk_class()`,
  which reads the RAW guest text and never trusts the model's own intent label. Off-hours no longer
  forces auto-send — it now pings ops instead. 15% of would-be auto-sends divert to a human to
  harvest an edit; that sample is the ONLY signal `record_learning` ever gets.
- **Times are read per-listing** (`unit_checkin_time` / `unit_checkout_time`, 6h cache) and injected
  into the draft prompt. `_OFFICIAL_CHECKIN_MINUTES` is deleted — do not reintroduce a hardcoded
  check-in time; a test asserts it stays out of the source.
- **00:00–05:59 with an AM/dawn marker is `late_night_arrival`, not an early check-in.** An unmarked
  small hour ("check in is at 3") is AMBIGUOUS and yields no time at all. Never invent a time: a
  missing hour makes Musaed ASK (the old `or "الوقت المطلوب"` fallback reached real guests).
- **Auto-sent promises now enter the EXISTING `promises/` ledger** tagged `source="musaed_auto"`,
  attributed to `MUSAED_AUTO_PROMISER`, rate-limited to one per conversation per 6h. This AMENDS the
  old rule in `promises/__init__.py` at the owner's direction — Musaed promised anyway, and an
  untracked promise is worse than a tracked one. `promises/` itself is unmodified; v3 only calls it.
- **Inquiry pricing:** `_dates_from_text()` parses dates from what the guest TYPED, because `dates`
  came from a reservation an inquiry does not have. Unparseable → `(None, None, "low")` and Musaed
  asks. Never guess a date — a guessed date is a wrong price. Pre-booking privacy is UNCHANGED.
- **TWO switches, not one (v3.1).** `MUSAED_V3_GATE=0` turns off only the review gate — v2 auto-send
  behaviour returns, **the firewall keeps running**. `MUSAED_V3=0` turns off EVERYTHING including the
  firewall. When someone says "too many cards", the answer is the GATE flag; `MUSAED_V3=0` is not a
  volume control. Boot prints both switches, `ASSISTANT_AUTO`, and a plain sentence for the posture —
  and that sentence must never claim the firewall is up when it is not.
- **R6 matches standalone tokens, min length 4, longest-first**, skips names contained in the guest's
  own unit, and requires a unit cue (شقة/وحدة/رقم/apartment/unit) before a bare-numeric name — «22»,
  «F2», «4511» are real unit names AND real fragments of ordinary replies. Its catalogue is persisted
  to STATE_DIR; on an API blip R6 runs on the last good copy (`fw_units_degraded`), never on nothing.
- **The debounce is skipped for `_is_risk_class()`** — a fire or a lockout must not wait 12 seconds.
- **The quality sample rides QUEUED high-confidence drafts, not the auto path** (the gate had narrowed
  auto to greetings, so sampling it harvested «حياك الله» and taught nobody anything).
  `v3_quality_sample_edited` counts only samples a human actually reshaped — zero means the loop is
  still dead. **Never move the sample back onto the auto path.**
- **Env (every default is correct — nothing to set in Railway):** `MUSAED_V3=1`, `MUSAED_V3_GATE=1`,
  `ASSISTANT_REVIEW_SAMPLE_PCT=15`, `ASSISTANT_DEBOUNCE_SEC=12`, `MUSAED_PROMISE_COOLDOWN_H=6`,
  `MUSAED_NIGHTLY_EVAL=1` (03:20 — 03:00 is the business snapshot), `MUSAED_EVAL_NIGHTLY_N=60`
  + `MUSAED_EVAL_MIN_ROTATE=10` (weeknights run every `v3_*` case + a rotating slice; Saturday runs
  all 163), `MUSAED_SURGE_CARDS=60`/`MUSAED_SURGE_HOURS=6`, `MUSAED_VOLUME_HOUR=23`.
- **Verify with:** `python3 -m unittest discover -s tests -p "test_*.py"` (2,856 tests, ALL GREEN —
  if you see failures, they are yours) **and**
  `python3 eval_musaed.py --selftest`. `bot`'s firewall and `eval_musaed`'s gates are pinned to the
  same verdicts by `TestDetectorParity` — change one, change both.

## Weekend digest «وش صاير بالرياض» — the `digest/` package
A Wednesday 13:00 (Riyadh) poster: events, cinema, Roshn fixtures, one «يستاهل الزيارة»,
rendered to an 810×1440 pt PDF + 1080×1920 story PNG + JSON in the KAFD memo's design system,
posted to Discord with approve / alternates / rephrase / drop / rebuild buttons. Spec:
`docs/superpowers/specs/2026-09-02-weekend-digest-design.md`.
- **Nothing publishes without the owner's tap.** The Wednesday post is a PREVIEW with buttons;
  `digest.approval` is the only path to «published». `DIGEST_DRYRUN` defaults to `0` (owner ruling
  2026-09-03 — he does not want to touch Railway); set `1` to build silently and print instead of
  posting. `tests/test_digest_approval.py` proves the publisher is never called in dry-run.
- **The loop is a 30-minute tick + `digest.schedule.should_fire`** (Wednesday, `DIGEST_HOUR`
  clamped to ≥13, and a latch PERSISTED in `digest_issues.week_of UNIQUE`). Do not turn it into a
  `@tasks.loop(time=…)` — a redeploy re-runs a loop's first iteration.
- **Only `digest/net_live.py` opens a socket**, wired as `HOST.http`; every collector, the link
  verifier and the artwork fetcher take it as an argument, and `tests/test_digest_nonetwork.py`
  greps the package to keep it that way. The identity is
  `Mozilla/5.0 (compatible; OujaDigest/1.0; +https://oujares.com)` — honest, never a spoofed
  browser; sites behind a challenge page (jdwel, timeoutriyadh) are simply not sources.
- **Sources that actually work (verified 2026-09-02):** Platinumlist `/ar/calendar/this-weekend`,
  elcinema `/now/sa/` (VOX is unreachable), saff.com.sa `championship.php?id=415` (cp1256 despite
  its utf-8 header) cross-checked against kooora's JSON-LD. Fixtures in `tests/fixtures/digest/`.
- **Every url is verified twice** (collection + right before render) and must have appeared in a
  fetched page or the search tool's opened-pages list — never constructed. A dead link drops the
  item and is reported; the QR is printed from the FINAL url.
- **The guard runs before Chromium** (`digest/guard.py`): stale source, a date outside Thu–Sat in
  prose (a film released before Thursday must say «يعرض حاليًا», not its date), a Western numeral in
  Arabic prose (Latin runs keep theirs), >4-word title, >10-word sub, a banned phrase
  (`digest/voice.py: BANNED`), an unverified url, a section over its cap, an empty/placeholder card.
- **The look is FROZEN** by `digest/render/golden_fingerprint.json` (text md5 + browser-measured
  geometry md5 + pixels with ≤3/255 tolerance; owner approved 2026-09-02). If
  `tests/test_digest_frozen.py` fails, revert the change — never regenerate the golden to pass.
  Regeneration needs the owner's word and `--write-golden --i-have-owner-approval`.
- **Every `_digest.<name>` bot.py touches must resolve on the package** (2026-09-03 outage: the
  wiring did `_digest.net_live` but `digest/__init__` never imported it → AttributeError → caught →
  every /digest route silently gone while the bot ran). Light modules are imported eagerly, the
  build chain via PEP 562 `__getattr__`; `tests/test_digest_bot_contract.py` greps bot.py for the names.
- **Zero-backslash files** (same trap as `DASHBOARD_HTML`): `digest/page.py`, `digest/notify.py`,
  `digest/render/html.py`, `digest/render/audit.py`, `digest/art_generated.py`. Tests enforce it.
- Colours only from `digest/render/tokens.py`; fonts from `fonts/Thmanyah{Sans,SerifDisplay}-*.woff2`
  (byte-identical to `monthly_public/static/fonts/`; NOT the older `ThmanyahDisplay-*` cut).
- Offline cold start: `python3 -m digest.build --dry-run --week 2026-09-03 --fixtures`.
- Env: `DIGEST_ENABLED`(1), `DIGEST_DRYRUN`(**0**), `DIGEST_CHANNEL`(نشرة-الاسبوع), `DIGEST_DAY`(2),
  `DIGEST_HOUR`(13). Buttons: admins / manage_guild only, fail CLOSED. `/api/digest/*` is behind
  login + the «digest» permission tab; `/digest/file/{n}/{pdf|png|json}` serves the outputs.

## Session skills installed for the digest work (2026-09-02) — when each fires
All live in `.claude/skills/` (gitignored — re-clone if missing; see the brief in the spec):
- `superpowers` — the process: brainstorm → plan → TDD → build → verify; every phase.
- `one-skill-to-rule-them-all` — orchestration; session start and each phase boundary.
- `ui-ux-pro-max` — the poster/PDF visual system; any commit touching `digest/render/*`.
- `impeccable` — audit → critique → polish → harden; after the first render of every surface.
- `stop-slop` — kills marketing copy; on every generated Arabic string (`digest/voice.py` is its code form).
- `unlazy` — no stubs, no TODOs, no partial implementations; every commit.
- `marketingskills` — the ranking model (`digest/rank.py`) and story caption craft.
- `claude-mem` — persists rulings (palette, tone, rejected candidates) across sessions.
- `vercel-labs/skills` — skill discovery plumbing, once at setup.
The earlier "Design skills are INSTALLED" blocks above still apply (impeccable, emil-design-eng, superpowers).
