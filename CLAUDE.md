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
2. **Tab labels resolve via `t()[tk]`.** There is no `tb` array any more: the sidebar is
   built from **`NAV_DEF`** in bot.py (`cats` → ids per section, `items` → `{id, ic, tk, badge}`,
   `labels.ar` / `labels.en`), merged into `T.ar` / `T.en` at boot. Every item's `tk` **must
   have a label in BOTH `labels.ar` and `labels.en`** or the sidebar shows the literal word
   **"undefined"** (this exact bug happened with `strat`). NAV ids auto-join `_USER_TABS`.
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
6. **Request handlers use `web_thread(...)`, NEVER `asyncio.to_thread(...)`.** `to_thread` runs
   on the ONE default pool that every bot job shares (Hostaway scans, throttle sleeps, PDF renders).
   When that pool is full a web handler queues behind it and never answers — the page HTML still
   serves in 0.7s but the data behind it never arrives, and the guest sees «جارٍ التحميل» forever
   (guide/h8-vlg on 2026-08-23, guide/b13-twn on 2026-09-05 because the fix sat unmerged).
   The guide serves `data.json` from its own 2-thread pool + RAM cache (`guide/routes.py`).
   `tests/test_web_lane.py` fails the build if any guest handler touches `to_thread`; add every
   NEW guest-facing handler to its `GUEST_HANDLERS` list. `GET /api/health/threads` shows which
   pool is jammed. Rule of thumb when a page hangs: compare a to_thread endpoint against a
   loop-only one (e.g. `/team-calendar`) — if only the first hangs, it is this.

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

## Permits «التصاريح» — the `permits/` package
Every dated permit/licence Ouja holds (today: the 45 Ministry of Tourism «تصريح مرافق الضيافة
السياحية الخاصة», one per apartment, one year, issued in the OWNER's name). THE GUARANTEE: **no
permit expires without a ticket.** At `days_left <= lead` (10; per-permit `lead_days` overrides —
`<=`, so a missed day is caught up) a ticket channel opens under «صيانه» (`_tk_make_channel`, spills
into «صيانه ٢…٨»), nudges daily at 13:00 and escalates; it closes ONLY by renewal (new date + proof
in the room / an upload in the dashboard), an authorised «لن يُجدَّد» with a reason, or a date
correction that moves it out of the window. There is no snooze, by design.
- **Invariants (tests/test_permits_*.py):** one live ticket per permit is a partial UNIQUE INDEX
  (`idx_permits_one_live_ticket`); every Discord side effect goes through `permits_outbox` (unique
  `ref`, atomic claim, backoff 1/5/15/60 min) so overlapping bot copies cannot double-post; the
  digest + reminder latches are PERSISTED dates; a deleted room → `lost` + a replacement; "couldn't
  check" is never "deleted". **No unique index on `permit_no`** — the seed has a real duplicate
  (serials 19/44): it is a review flag, never a reason to drop a row. Review flags never block tickets.
- **Ships DRY.** `permits_settings.mode` defaults to `dry`: no Discord output, no ticket rows, only
  `state='dry'` would-open rows. An admin types «تشغيل» in the tab to go live (ops/switch CONFIRM_WORD).
- **Privacy (PDPL):** national IDs are stored as the **last 4 digits only** (`holder_id_last4`),
  never in Discord, shown masked to admin/ops only. The raw `permits/seed/source/*.xlsx` is
  **git-ignored** — only `permits_seed.normalized.json` is committed; `permits/tools_privacy_scan.py`
  greps every changed file for `\b[12][0-9]{9}\b`. Rebuild the seed: `python3 -m permits.seed.build_seed`.
- **Dates:** stored ISO Gregorian, shown both; Hijri via `hijridate` (Umm al-Qura, needs 3.10+ —
  locally `pip install --user hijridate==2.5.0` on 3.9). Ambiguous / unreadable dates are FLAGGED
  (`date_issue`, `needs_data`), never guessed; an unknown date never opens a ticket but is red daily.
- **Tab JS lives in `permits/static/permits_tab.js`** (a real file, `node --check`); DASHBOARD_HTML holds
  only the section + a ≤15-line backslash-free stub. Handlers use `HOST.web_thread` — never `to_thread`.
  Topic prefix `ouja-permit:` (never `ouja-ticket:` / `ouja-watchman:`). Gates: `permits/GATES.md`.
- Env (read at call time): `PERMITS_ENABLED`(1), `PERMITS_LEAD_DAYS`(10), `PERMITS_HEADSUP_DAYS`(30),
  `PERMITS_DAILY_HOUR`(13), `PERMITS_OPEN_FROM`/`TO`(9/22), `PERMITS_TICK_MIN`(5),
  `PERMITS_DIGEST_CHANNEL`(تنبيهات-التصاريح), `PERMITS_PING_ROLE_ID`(0), `PERMITS_ESCALATE_IDS`
  (= MAINT_CLOSE_IDS), `PERMITS_FORCE_DRY`(0 — the emergency mute).

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

## Direct-booking collection «التحصيل» — the `directpay/` package
A debt ledger with a human attestation gate, NOT an integration. Direct (non-Airbnb) bookings
are paid through **StayHub**, which is not connected to this bot and never will be — this code
never calls StayHub, has no credentials and no URL for it; `stayhub_ref` is free text for a
future reconciliation. Every confirmed direct reservation (classified by the ONE classifier
`_finance_channel` — never copy it; `DIRECTPAY_EXTRA_CHANNELS` adds substrings on top) opens
its own Discord room under «تحصيل الحجوزات المباشرة» (topic `ouja-dp:<res_id> seq:<n> lid:<id>`).
- **THE OWNER RULE (2026-09-10), absolute:** a room closes ONLY when an **administrator** (him
  and Aseel — Discord `administrator`, NOT `manage_guild`; `_dp_can_close` is written fresh, do
  not swap in `_tk_is_admin`) uploads an image/PDF proving the money is in StayHub AND types the
  amount + the StayHub reference. `DIRECTPAY_CLOSE_IDS` adds ids; a garbled value ⇒ admins only,
  never everybody. Every refused press is a `directpay_events` row naming who tried.
- **State machine** (`engine.transition`, the ONLY place; buttons + routes both call it):
  `open → verified` (proof + amount + ref, variance inside `max(1 SAR, 1%)` or a 10–400-char
  reason) · `open → written_off` («إغلاق بدون إثبات», 20–400-char reason, **permanent red**,
  counted forever, in the daily summary all month) · `open → void` («ليست حجز مباشر» / cancelled,
  reason required, records the raw channel so the owner can tune EXTRA_CHANNELS) ·
  `verified → open` ONLY on a price increase after close. No `closed` state, no "close anyway".
- **Traps closed structurally — do not simplify:** (1) `DIRECTPAY_START_DATE` = first-boot date,
  persisted in `directpay_settings`, never recomputed — without it the first tick opens a room
  for every historical booking; (2) `DIRECTPAY_DRYRUN` — was 1 for the first deploy, **0 (live) since 2026-09-13 by owner
  ruling, changed in code because he never edits Railway vars**; set 1 to silence; rooms
  backfill 5/tick for rows recorded during dry-run; (3) three anti-duplicate
  layers: `UNIQUE(reservation_id)` + `_once_claim("directpay:open:<id>")` (released on failure)
  + rebuild from channel topics across `_category_family` every tick; (4) rooms via
  `_make_channel_spill` only (50-per-category cap is a certainty here); (5) the proof scan
  **fails CLOSED** (`proof.find_proof` → «ما قدرت أقرأ الملفات») — the opposite of
  `_maint_has_proof`, on purpose; (6) proof BYTES re-hosted under `$STATE_DIR/directpay/<id>/`
  (a Discord attachment URL is signed and expires); (7) a Hostaway cancellation posts a note +
  «إلغاء الغرفة» button — the bot never auto-voids (paid-then-cancelled = refund decision);
  (8) no web close endpoint — `/api/directpay/*` is board/ticket/note only; (9) hourly loop +
  persisted `summary_date` latch, never `@tasks.loop(time=…)`.
- **Detection:** `directpay_poll_loop` (10 min, guarded + staggered) pulls a targeted arrival
  window today−3 → today+400 in 120-day slices via `_ha_reservations_window` — NEVER
  `get_reservations_cached()` — and filters `reservationDate` in Python; the webhook adds
  `_bg_task(_directpay_on_hook(rid))` as a latency shortcut only (`WEBHOOK_SECRET` may be
  random-per-boot). `service.process_reservations` is the single path for both.
- Dashboard tab `dpay` («التحصيل», cat_ops) is a `_ROLE_READ_RULES`/`_ROLE_WRITE_RULES`
  permission tab — existing non-admin users see it only after the owner ticks it in الصلاحيات.
- Tests: `tests/test_directpay_{engine,db,gate,proof,startdate,structure}.py` (the structure
  test greps the rules above; zero backslashes in `directpay/*.py`).
- Env: `DIRECTPAY_ENABLED`(1), `DIRECTPAY_DRYRUN`(**0** since 2026-09-13), `DIRECTPAY_START_DATE`(first boot),
  `DIRECTPAY_CATEGORY`(تحصيل الحجوزات المباشرة), `DIRECTPAY_SUMMARY_CHANNEL`(تحصيل-الملخص),
  `DIRECTPAY_CLOSE_IDS`(empty), `DIRECTPAY_PING_ROLE_ID`(empty), `DIRECTPAY_POLL_MIN`(10),
  `DIRECTPAY_LOOKBACK_DAYS`(3), `DIRECTPAY_MAX_OPEN_PER_TICK`(5), `DIRECTPAY_NUDGE_AFTER_DAYS`(2),
  `DIRECTPAY_NUDGE_EVERY_DAYS`(2), `DIRECTPAY_SUMMARY_HOUR`(13), `DIRECTPAY_VARIANCE_SAR`(1.0),
  `DIRECTPAY_VARIANCE_PCT`(0.01), `DIRECTPAY_PROOF_MAX_MB`(12), `DIRECTPAY_WATCH_DAYS`(30),
  `DIRECTPAY_EXTRA_CHANNELS`(empty).

## Checkout Watch «متابعة الخروج» — the `checkout/` package
Hotel front-desk "due-out" control inside every turnover room: at checkout time the bot mentions
the responsible person «طلع الضيف؟» on a Checkout Card with ✅ طلع / 📵 ما رد / ⛔ ما طلع /
📱 واتساب الضيف / 🚨 وصلنا والضيف داخل. It exists so the ops manager (أصيل) stops tracking every
checkout in her head. **Ships OFF** — nothing posts until an admin runs `/checkout-start`.
- **THE OWNER RULES, absolute:** (1) **no escalation to أصيل or the owner** — the only places it
  writes are the apartment's own room and ONE board channel (`متابعة-الخروج`); (2) **warning only,
  never block** — cleaners are warned via the oujact state + the card, and a cleaning submit before
  ✅ gets one extra line «⚠️ انتبهوا: ما تأكدنا إن الضيف طلع قبل الدخول», never a refusal;
  (3) **the presser is accountable** — every answer stores who pressed it (`state_by`, `cw_events`),
  and a 🚨 surprise is logged against whoever pressed ✅; (4) **the demo is isolated** — `demo=1`
  rows never call Hostaway, never write `oujact_checkout.json`, never reach the board / 17:00
  summary / report / risk (all readers filter `demo=0`); the demo lives in its own category;
  (5) **the demo is a clean stage the owner narrates himself** (owner ruling 2026-09-26): each
  demo room is a REAL turnover room plus the add-on — card 1 = the Turnover card built by
  bot.py's own `_oujact_card_embed` (via `HOST.turnover_card`), card 2 = the Checkout Watch card;
  rooms named by `_oujact_channel`. No pinned script, no 🎬 badge, no ⏩ button. Time moves with
  `/checkout-demo-next` typed in the room (reply private to him). The demo's «📷 Submit for
  Review» is `cw_demo_submit`, NOT `ouja_cleaning_done`: it acts the outcome out and never
  touches the cleaning-report store.
- **One family of cards:** the Checkout Watch card uses the Turnover card's boxed-fields layout
  in Arabic (الضيف · الخروج · الدخول / المسؤول with the calendar emoji / الحالة, + الخطة and
  تنبيه only when needed, times as "12:00 PM"). Cards are plain dicts in Discord's shape
  (`fields`, `footer`); bot.py draws them with `discord.Embed.from_dict`.
  `cw_items.responsible_emoji` was added after the first live deploy — `db._LATE_COLUMNS`
  adds it to the existing table at boot (CREATE TABLE IF NOT EXISTS never alters one).
- **State machine** (`engine.py`, PURE): `waiting → asking → out | no_answer | inside →
  cleaned_pending → approved`. Ping once at the reservation's checkOutTime; a reminder every
  `CHECKOUT_REMIND_MIN` after «ما رد» (and after an unanswered ping) until ✅/⛔; re-ask at the
  exit time promised under ⛔; silence 23:00–08:00. First-final-wins via `db.transition`
  (conditional UPDATE under a lock) — a late press is told «انحفظت قبلك من …». Late-exit cap:
  `latest_ok_exit = min(check-in, 17:00) − clean_max` → red line on the card when exceeded.
- **Airbnb message:** on the first «ما رد» and with the 3rd reminder, never more than 2; the two
  bodies DIFFER (send_guest_message de-dups identical bodies); NO DIGITS (firewall R1); a
  `SEND_*` block or exception is logged `airbnb_failed` once and never retried.
- **Oujact wiring (the cleaners' warning):** ✅ → `guest_confirmed` (+ status `guest_out`),
  ⛔ late_ok/late_ask → `late_checkout`, other ⛔ → `inside`, ما رد → **`no_answer`** (new state in
  `OUJACT_CHECKOUT_STATES`, `_OUJACT_REASON`, tier 90 in `_oujact_priority`), 🚨 → `inside`.
- **30-min report → «غرفة-المراقبة»** (owner request 2026-09-26, `flow.maybe_watch_report`): a NEW
  message every `CHECKOUT_REPORT_MIN` (30) while live — counts, «⏰ لسا ما جاوبوا» (unit + the
  RESPONSIBLE person's name + minutes since checkout), «🔴 تحتاج تصرف», and every answer since the
  previous report. It names people ON PURPOSE: it goes to the watchdog's room (WATCHDOG_CHANNEL),
  never the team board. Slot claimed in `cw_settings.watch_report_slot` before posting (no double
  post on redeploy); «since» = `watch_report_at`, strictly after. Silent 23:00–08:00, on empty
  days, and once all approved and nothing moved. Separate from the watchdog's own summary.
- **Switch precedence:** stored `cw_settings.live` > env `CHECKOUT_WATCH_LIVE` > `0`, read through a
  3-second cache, so `/checkout-stop` lands within seconds and survives redeploys. Stopped = the
  tick returns at once; buttons STILL record answers.
- **Commands** (slash + `!ouja` fallback, admin = `_can_delete_channels`): `/checkout-start`
  (`تشغيل-الخروج`: switch on, `sync_oujact_turnovers('today')`, sweep every room of today in the
  Turnovers family incl. overflow, list departures with no room), `/checkout-stop`
  (`ايقاف-الخروج`), `/checkout-risk` (`خطر-اليوم`, in-channel; inside the demo risk room it reads
  demo rows only), `/checkout-demo` (`تجربة-الخروج`), `/checkout-demo-next` (`قدم-التجربة`, the
  typed prefix command is deleted), `/checkout-demo-end` (`انهاء-التجربة`),
  `/checkout-report` (`تقرير-الخروج`, ephemeral; prefix version DMs the invoker — per-person
  numbers stay OUT of every shared room).
- **📱 WhatsApp = ONE tap** (owner ruling 2026-09-26): a Discord LINK button → our short link
  `/cw/<token>` (`cw_links`) → 302 to wa.me with the message typed, signed with the RESPONSIBLE
  person's name (a link button can't know who pressed). Why the redirect: Discord caps a button
  URL at **512 chars** and the bilingual message is ~730 encoded — the first version put it in a
  button, Discord refused the reply, and the error was swallowed → «thinking…» forever. No phone
  → the card links the Airbnb chat instead. `_cw_reply` now retries as plain text on any refusal.
- **Own thread pool (`flow.run_blocking`), never `asyncio.to_thread`:** the shared default pool
  jams for minutes after a deploy (Hostaway work), and every button press queued behind it —
  the first live `/checkout-demo` sat on «thinking…» for minutes. Slash commands go through
  `_cw_answer`, which always answers, error or not.
- **Mechanics:** one listener `_cw_interaction` for static ids `cw_yes/cw_noanswer/cw_no/
  cw_surprise` (+ legacy `cw_wa/cw_demo_ff` on cards posted before 2026-09-26), row found by
  message id (`cw_items.card_message_id` or `cw_messages`), so buttons survive redeploys. `checkout_watch_loop` every 2 min; Hostaway read once per 5 min
  (`_cw_today_turnovers` = targeted departure + arrival windows, never the truncated cache).
  `work_key` PRIMARY KEY = one card per apartment+day; `cw_daily` = the 17:00 summary latch.
- Env (all defaults correct — the owner never opens Railway): `CHECKOUT_WATCH_LIVE`(0),
  `CHECKOUT_WATCH_AIRBNB`(1), `CHECKOUT_REMIND_MIN`(30), `CHECKOUT_DEADLINE`(17:00),
  `CHECKOUT_QUIET_FROM`(23:00), `CHECKOUT_QUIET_TO`(08:00), `CHECKOUT_BOARD_CHANNEL`(متابعة-الخروج),
  `CHECKOUT_DEMO_CATEGORY`(🎬 تجربة الخروج).
- Tests: `tests/test_checkout_watch_engine.py` (clock, cap, risk, report, texts),
  `tests/test_checkout_watch_flow.py` (idempotency, Airbnb, oujact, demo isolation, WhatsApp,
  board, 17:00), `tests/test_checkout_watch_bot.py` (REAL firewall, tier 90, overflow sweep,
  synthetic Hostaway rows, wiring). Run them before any edit here.

## ترتيب ديسكورد — `!ouja-tidy` (`ops_tidy.py` + `ops_tidy_rules.py`)
Owner-approved 2026-10-02 (spec: `docs/superpowers/specs/2026-10-02-discord-tidy-design.md`).
`!ouja-tidy plan` (READ-ONLY: summary + `tidy_plan_<date>.json` + `tidy_people_<date>.csv` «مين
يفقد وش») → `!ouja-tidy run` (word **نفّذ**, or **نفّذ بدون تقرير** when there is no people
report; plan must be < 24h old) → `!ouja-tidy undo` (word **رجّع**) / `!ouja-tidy status`. Owner
(`OWNER_DISCORD_ID`) or a guild admin only; diacritics are ignored in the words.
- **Split:** `ops_tidy_rules.py` is the PURE brain (no discord import), pinned by
  `tests/test_ops_tidy_rules.py` against the REAL 2026-10-02 audit (196 archive / 24 restrict /
  94 keep). Don't change its behaviour to make the Discord layer pass. `ops_tidy.py` only
  executes the plan; wired like ops_audit/ops_archive (`setup(bot, host)`, never `import bot`).
- **The 4 rules:** (1) ticket-opening rooms («فتح/افتح/تكت», the 3 `*_PANEL_CHANNEL`s,
  `rr-tickets` — also when renamed «مغلقة-…») are NEVER written; (2) nothing is deleted or
  renamed (gate G12 greps for it); (3) the archive «📦 أرشيف N» (50 per category) is hidden from
  @everyone and **read-only for Managment** (`TIDY_ARCHIVE_ROLE`), the bot keeps view/send/history;
  (4) only the 3 leaks are locked — overflow categories copy their parent, «تحصيل الحجوزات
  المباشرة» is locked (Accounting + Managment + `DIRECTPAY_PING_ROLE_ID` + `DIRECTPAY_CLOSE_IDS`),
  the 4 price/revenue channels become Managment-only (the bot's own member overwrite goes in
  FIRST so it never locks itself out). Live Turnovers/صيانه/مشتريات permissions are not touched.
- **Run safety:** the snapshot is saved AND posted as an attachment BEFORE the first write
  (Railway's disk can be wiped — undo accepts the attachment); every row is re-checked right
  before its write (gone / moved / reopened / panel → «تجاوزت»); Forbidden is counted, never
  fatal (re-run plan → run picks up only the rest); one op at a time; `TIDY_PAUSE` (1.0 s)
  between writes. Undo restores categories FIRST, then channels in reverse order.
- **Auto-archive on close** (`archive_closed_channel`, called at the end of `_tk_close`,
  `_directpay_finalize_close` and the permits `close_channel` — a test asserts every
  `"مغلقة-" +` rename site is followed by it): OFF until the first successful `run` writes
  `tidy_state.json {"auto_archive": true}`; `undo` turns it off again. `TIDY_AUTO_ARCHIVE=0/1`
  forces it. Never raises. A reopened collection room (`price_up`) moves back out of the archive.
- **TRAP — `_directpay_known_rooms` must scan the archive categories too.** Closed collection
  rooms live in «📦 أرشيف N» after a run; if the scan only looked at the collection category the
  poller would open a SECOND room for an already-handled reservation. Same rule for any future
  code that finds rooms by topic inside a category.
- **TRAP — never put `manage_permissions`/`manage_channels` in the bot's OWN overwrite.** Only a
  guild Administrator may set Manage Permissions inside a channel overwrite; the bot is admin only
  during the owner's run, so every later archive/collection-category create would 403. Moves also
  pass `overwrites=dict(dest.overwrites)` next to `sync_permissions=True` — discord.py's sync reads
  the category from the gateway CACHE, which lags a just-created category.
- **TRAP — never set `intents.members = True` without the env gate.** It is
  `os.environ.get("MEMBERS_INTENT","0") == "1"`: with the portal's «Server Members Intent» OFF a
  hard True makes the whole bot fail to log in. Order: portal toggle first, then `MEMBERS_INTENT=1`.
- Env: `MEMBERS_INTENT`(0), `TIDY_AUTO_ARCHIVE`(unset = follow the first run), `TIDY_ARCHIVE_ROLE`
  (Managment), `TIDY_PAUSE`(1.0). The bot needs **temporary Administrator** during `run` to reach
  the ~47 channels it cannot read today; remove it afterwards.

## رفع التقييم — the `reviewask/` package (Review Push)
Owner-approved 2026-10-03 (spec: `docs/superpowers/specs/2026-10-03-review-push-design.md`, gates
`reviewask/GATES.md`, plan `docs/superpowers/plans/2026-10-03-review-push.md`). Goal: every apartment
above 4.75 on Airbnb. Every checkout from a weak apartment gets its own Discord ROOM under «طلبات
التقييم» (spills «… ٢»), topic `ouja-rv:<res_id> lid:<lid> seq:<n>`; a WhatsApp step on checkout
day and a call the next evening; every press recorded against the presser; the review closes it.
**ON by default since 2026-10-03 03:10** (owner: «Make it on but make sure the mistake never
happens again»); `/reviews-stop` still wins. The **circuit breaker** `REVIEWASK_MAX_ROOMS_PER_DAY`
(20): a day that would open more rooms opens NONE and posts one alert in «متابعة-التقييمات».
One-off: on 2026-10-03 only, tomorrow's rooms opened at once (`EARLY_OPEN_DAY`, latched
`early_open_done`); after that, 20:00 the evening before. INCIDENT 2026-10-03 01:48: a default-ON push opened **60 rooms**
because the live bot held ONLY the May CSV seed (2,473 reviews, no `raw`) — Hostaway's review pull
had never landed — so 50 of 82 apartments looked weak, plus a «yesterday» catch-up and care-mode
rooms, all visible to the whole Operation team. Rolled back to OFF; the owner approved deleting
those 60 (`flow.maybe_purge_mistake`, window 01:00–02:30, latched `purge_2026_10_03_done`, same
fence as the sweep). Owner rulings after it: **weak apartments ONLY** (no care-mode rooms),
**rooms open the evening before at 20:00** (`REVIEWASK_OPEN_AT`; today's are a catch-up only,
never yesterday), **rooms PRIVATE** to the responsible manager + admins + bot (the room carries
its own overwrites — `_rv_private_overwrites`; a later day's manager is added by `_rv_grant`).
**Freshness lock:** `plan_day` refuses unless a review that came from Hostaway itself (`raw`) is
dated within `REVIEWASK_FRESH_DAYS` (30) — and refuses on a review `type` it does not know.
`GET /reviewask/health` (PUBLIC, counts only) shows switch, type/channel counts, newest live
review, the last Hostaway review pull (`review_pull` = bot.py `_reviews_fetch_status`: at, n,
pages, error) and purge progress — read it instead of asking the owner for a Hostaway key.
- **THE OWNER RULES, absolute (spec §2 R1–R10):** rooms not threads; **button labels carry text
  only, never an emoji** (meaning = label + colour; embeds/guest text may keep emoji); a
  maintenance ticket from a call says «من مكالمة تقييم» + field «المصدر» linking the review room;
  the WhatsApp text + call script are the OWNER's (rv_settings, seeded once from
  `templates.seed.json`) — **no discount or offer is ever hard-coded** (the 10% lives only in his
  template); closed review rooms are deleted 7 days after closing and NOTHING else is.
- **Which apartments:** guest-to-host Airbnb reviews only, exact integer math on Hostaway's
  10-point `rating_raw` (avg > 4.75 ⇔ 2R > 19n — never the rounded `rating`); fewer than 3 reviews
  = in; `reviews_needed = 19n − 2R + 1`. **A 0 / empty / None score is not a review** (owner
  ruling 2026-10-03; the CSV seed has 143 of them) — not in R, not in n. Seed rows have no `type`
  → guest reviews; one review per reservation (live beats seed). Admin pins (`rv_overrides`)
  win, both numbers shown. Care mode (a maintenance ticket during the stay → a care call) still
  exists in the engine but **no longer opens rooms** — owner ruling 2026-10-03: weak apartments only.
- **State machine** (`engine.next_action` / `engine.press`, PURE, TDD-locked):
  `waiting → wa_due → wa_sent → call_due ⇄ call_retry` (+ `care_due`, `promised`); terminal
  `reviewed · promised_expired · declined · wrong_number · no_answer_final · complaint · expired ·
  cancelled · void`. WhatsApp at 17:00 (reminders 18:00, 19:30); call at `call_time` = 20:00 Sep–Apr,
  20:45 May–Aug, 21:30 in Ramadan (hijridate, else `REVIEWASK_RAMADAN`), env HH:MM wins; reminders
  +45 min and 21:30. **Staff misses never burn a guest attempt** — at 22:00 with no press the
  miss is logged against the responsible person and the SAME attempt rolls to the next call
  time. 2nd «ما رد» closes; «كلمني بعدين» is free once. **Nothing guest-facing 22:00–13:00.**
  D+13 23:59 → expired. First-final-wins = `db.transition` (conditional UPDATE under a lock).
- **Anti-duplicate (directpay's three layers):** `UNIQUE(reservation_id)` + `_once_claim
  ("reviewask:open:<id>")` released on failure + `_rv_known_rooms` reads every `ouja-rv:` topic
  across `_category_family` AND the archive. Detection reads `_ha_reservations_window` —
  never `get_reservations_cached()`. A cancellation needs POSITIVE evidence (status or a moved
  departure, re-read by id when missing); a failed read cancels nothing.
- **Deletion (R7) is fenced:** `flow.sweep_closed` is the only caller of `HOST.delete_room`
  (`_rv_delete_room`, the only `.delete(` in the block): terminal + closed ≥ 7 days + fetched by
  the stored id + topic carries THE SAME reservation (else `delete_refused`, never retried) +
  transcript saved to `rv_transcripts` and read back → delete; NotFound → «كانت محذوفة»; any other
  error = "could not check" = kept. Max 10/run, hourly. `ops_tidy_rules.is_review_room` keeps
  every such room out of `!ouja-tidy` (above the stale/closed/dead rules); never call
  `archive_closed_channel` from here.
- **Wiring (bot.py, one block «رفع التقييم» after the Checkout Watch commands):** `_rv_wire` /
  `_rv_ready` (brain path hand-over, like `_cw_ready`), listener `_rv_interaction` (static ids
  `rv_<kind>`, row by message id via `rv_messages`), `reviewask_loop` (2 min) +
  `reviewask_reviews_loop` (30-min 2-page review pull through `_reviews_merge`, the merge
  `refresh_reviews` now shares), both guarded and staggered and silent while off.
  `_maint_open_ticket(..., origin="review_call", origin_ref, origin_room)` — old callers are
  byte-for-byte unchanged (`tests/test_reviewask_bot.py` replays the frozen original).
  «الضيف رد» and the complaint urgency are ephemeral VIEWS, not modal selects (Railway pins
  discord.py ≥ 2.4; selects in modals need 2.6).
- **WhatsApp = one tap** on `/rv/<token>` (public, 16-char token, 30 hits/IP/min, `web_thread`) →
  302 wa.me with the owner's text rendered (966… → ar, else en, empty en → ar), signed with the
  RESPONSIBLE person (a link button cannot know who pressed); «أرسلت الرسالة» records the presser.
- **Commands** — slash names ASCII (owner ruling: a rejected Arabic name kills the whole tree
  sync), Arabic `!ouja` names: `/reviews-tomorrow` (`تقييمات-بكرة`, lists would-open + skip reasons
  while off), `/reviews-today` (`تقييمات-اليوم`) — admins + `REVIEWASK_LEAD_ROLES` (Managment);
  `/reviews-start` (`تقييمات-تشغيل`), `/reviews-stop` (`تقييمات-ايقاف`), `/review-message`
  (`رسالة-التقييم`, the modal; prefix replies with a button that opens it), `/reviews-report`
  (`تقرير-التقييمات`, ephemeral / DM). Tracking: board «متابعة-التقييمات» (edited in place),
  30-min report → «غرفة-المراقبة» 17:00–22:00 naming people, 22:00 summary (persisted latches).
- **Dashboard tab `rvpush` «رفع التقييم»** (cat_ops, `_ROLE_READ_RULES`/`_ROLE_WRITE_RULES`
  permission tab — non-admins see it after the owner ticks it in الصلاحيات): real file
  `reviewask/static/reviewask_tab.js` + ≤15-line stub; views الشقق (+ pin) · التكتات الحية · الأداء ·
  الأرشيف (events + saved transcript, forever) · نص الرسالة (the editor; both editors write through
  `db.save_templates`, which keeps every previous version in `rv_template_history`).
- **Zero backslashes in `reviewask/*.py`**; never `import bot`; never `to_thread(`; no money figure
  in any staff room. Tests: `tests/test_reviewask_{engine,flow,delete,bot,structure}.py` +
  `tests/test_ops_tidy_rules.py` (review rooms untouched).
- Env (defaults correct): `REVIEWASK_ENABLED`(1), `REVIEWASK_LIVE`(1 — the stored switch wins), `REVIEWASK_FRESH_DAYS`(30),
  `REVIEWASK_MAX_ROOMS_PER_DAY`(20),
  `REVIEWASK_THRESHOLD`(4.75), `REVIEWASK_MIN_REVIEWS`(3), `REVIEWASK_WA_AT`(17:00),
  `REVIEWASK_CALL_AT`(auto), `REVIEWASK_MAX_CALLS`(2), `REVIEWASK_WINDOW_DAYS`(14),
  `REVIEWASK_QUIET_FROM`/`TO`(22:00/13:00), `REVIEWASK_DELETE_AFTER_DAYS`(7),
  `REVIEWASK_CATEGORY`(طلبات التقييم), `REVIEWASK_BOARD_CHANNEL`(متابعة-التقييمات),
  `REVIEWASK_REVIEW_URL`(https://www.airbnb.com/users/reviews — if the phone test lands wrong, use
  https://www.airbnb.com/trips), `REVIEWASK_RAMADAN`(empty), `REVIEWASK_OPEN_AT`(20:00, the evening before),
  `REVIEWASK_LEAD_ROLES`(Managment), `REVIEWASK_REPORT_MIN`(30).

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
