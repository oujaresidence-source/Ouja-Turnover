# «اجتماع المالك» — Owner Meeting Room · build brief for Claude Code

> Paste this whole file into Claude Code at the root of the `Ouja-Turnover` repo.
> Files that come with it (put them in the repo exactly here before you start):
> - `docs/owner_meet/prototype.html` — the approved visual prototype (open it in a browser; it is the design reference, NOT code to copy blindly).
> - `tests/fixtures/owner_meet/host_opportunity_2026-10-04.tsv` — a real Airbnb «Host Opportunity Report v5 — Promotions» export (42 listings).
> - `docs/owner_meet/airbnb-plan-2026-10.pdf` — the action plan built from that report; its lever decisions are the defaults in §7.

---

## 0. How you work on this (read first — non-negotiable)

1. Read `CLAUDE.md` fully. Its **Owner approval protocol** governs this job: plan first, then STOP and wait. Do not edit, create, delete, commit or push before Faisal approves the plan. He has no coding background; talk to him in plain Najdi Arabic, and explain any technical word in the same sentence.
2. Use the installed skills the way CLAUDE.md says: **superpowers** for process (brainstorm → spec → plan → TDD → verify), **impeccable** for every screen (critique → audit → polish → harden), **emil-design-eng** for motion, **unlazy** for gates (no stubs, no TODOs, no "later").
3. This is an **architectural** change (a new package + a new tab + new public routes). So: write the spec to `docs/superpowers/specs/2026-10-06-owner-meet-design.md`, get his approval, write the plan to `docs/superpowers/plans/2026-10-06-owner-meet.md`, get his approval, then build slice by slice (§11). After each slice, stop and give him screenshots + "what to click to check it".
4. Before the plan, turn every requirement in this file into a numbered acceptance checklist in `owner_meet/GATES.md` (one observable outcome per gate, with a runnable `CHECK:` where possible). Verify every gate before saying a slice is done. Never claim something was tested unless it ran.
5. Prefer the smallest change that works. Additive and reversible. Never touch the money math (`compute_owner_report`, `build_owner_report`, `finance/owners.py`) — you only READ from it.

---

## 1. What Faisal wants, in his words → what it means

> "Weekly or monthly or whenever, I meet existing owners about their apartments: performance, what we can do, everything. Inside our system, I open a page for each apartment — beautiful, a link or a PDF — and share my screen. It shows how much the apartment made after expenses and after everything, compares it with the other apartments, what Airbnb told us, and also every reimbursement request we opened and the response, every maintenance ticket, every review. Literally everything."

So the product is a **meeting room**, not a report:

- **Before** the meeting: one click builds a frozen snapshot for one apartment (or one owner with several apartments) for a chosen period.
- **During** the meeting: a 16:9 presentation he walks through with the arrow keys while sharing that one browser tab. His private talking points open in a **second window** (or his phone) that he does not share.
- **During** the meeting he records what was decided ("approved new photos", "will send permit documents").
- **After** the meeting: one click sends the owner a read-only link + PDF of exactly what was shown, and the decisions.
- **Next** meeting opens with "what we promised last time → what happened", so every meeting builds on the last.

Named precedent (copy → adapt): hotel management companies (Marriott, Hilton, IHG) run a monthly **owner's report** and a quarterly **owner business review** for each hotel owner: P&L, a **competitive-set index** (STR's RevPAR index — 100 = the hotel gets its fair share versus its comp set), guest-satisfaction scores, capex needs, a forecast, and an action list. We do the same per apartment, with our own portfolio as the comp set and Airbnb's report as the guest-funnel source.

---

## 2. Hard rules (each one becomes a gate and a test)

### Privacy and what the owner may see (the meeting screen is SHARED)
- **R1 — never reveal how many units Ouja manages.** No count of listings, owners or apartments anywhere on owner-facing output: no "3 of 42", no rank, no dot-per-apartment charts (a viewer can count dots), no "n=" footnotes. Comparisons are **bands** only: lower quarter / middle half / upper quarter, the median tick, and "his" marker. Percentiles are rounded to the nearest 10 and only shown at ≥ 60 or as "أقل من أغلب الشقق المشابهة". If the peer group (same bedroom count) has fewer than 6 units, compare with the whole portfolio and say «بكل شققنا» without a number.
- **R2 — no other owner's data.** No other apartment names, owner names, addresses or figures. Peer statistics are computed server-side; only the band values reach the page.
- **R3 — no guest identity.** No guest names, phone numbers, reservation codes (e.g. `HM[A-Z0-9]{8}`), Hostaway reservation ids or emails on owner-facing output. Public review text may show the guest's first name as Airbnb shows it publicly. **Private feedback (`private_review`) is presenter-only.**
- **R4 — no staff names or staff performance** on owner-facing output (tickets show "فريق عوجا" / "الضيف" as the source, never a person).
- **R5 — no Ouja internal economics** on owner-facing output: no cost per turnover, cleaning-subscription cost, Ouja margin, other owners' fee rates. Only the owner's own management % from his contract terms.
- **R6 — numbers come only from existing stores, never invented.** Missing data = an honest empty state ("لا توجد تذاكر صيانة في هذه الفترة"), never a placeholder, never sample rows. The prototype's "مثال توضيحي" content must not exist in production code.
- A test (`tests/test_owner_meet_privacy.py`) renders the owner HTML and the PDF text for fixtures and greps for: any listing count, any other fixture owner/unit name, guest names from fixtures, reservation-code patterns, Saudi phone patterns (`05\d{8}`, `9665\d{8}`), staff names from fixtures, the word «مثال». Any hit fails the build.

### Money
- **M1 — one money truth.** The owner's money comes from `bot._owner_month_report(owner, mkey)` (same object `_owner_portal_data` uses), summed across months for longer periods. The meeting's "صافي المالك" for a period must equal the sum of `owner_net` of those months **to the halala** — a test asserts it. Never re-implement income, fee, cleaning or expense logic.
- **M2** — management % comes from the owner's effective-dated terms (`finance/owners.terms_on`), never a hard-coded 23%.
- **M3 — the guest-paid → owner-net waterfall** uses real fields only. If the reservations carry the gross guest total, VAT and Airbnb host fee (inspect a live Hostaway reservation payload and list the exact fields in the spec), show: ما دفعه الضيوف → الضريبة → عمولة Airbnb → صافي الحجوزات → رسوم عوجا → التنظيف (only if the owner pays it) → مصاريف الشقة → صافي المالك. If the gross/VAT fields are not reliable, start the waterfall at «صافي الحجوزات من Airbnb» (the statement's own income). **Never back-calculate with ÷1.15 or ×0.822 in production** — that was prototype-only.
- **M4** — a degraded pull (`rep["degraded"]`) blocks "إرسال للمالك" and shows a red banner on the presenter view.
- **M5** — expenses show with their receipt through the owner-scoped proxy (`/fin/receipt/<id>?t=<token>`), exactly as the owner portal already does.

### Platform traps (from CLAUDE.md — every one has bitten before)
- **P1** — new package `owner_meet/`; it **never** `import bot`. One bridge `owner_meet/host.py` with `wire(caps)` like `permits/host.py`. bot.py calls `owner_meet.wire({...})` + `owner_meet.register_routes(app)` in `start_web_server`.
- **P2** — every request handler uses `HOST.web_thread(...)`, **never** `asyncio.to_thread`. Add every public handler (the owner token page and its PDF) to `GUEST_HANDLERS` in `tests/test_web_lane.py`.
- **P3** — **zero backslashes** in every `owner_meet/*.py` that holds HTML/JS (structure test greps it). The tab JS is a real file `owner_meet/static/owner_meet_tab.js` (`node --check` clean); `DASHBOARD_HTML` gets only the section + a ≤ 15-line backslash-free stub.
- **P4** — sidebar: add `{"id": "meet", "ic": "finance", "tk": "meet"}` to `NAV_DEF["items"]`, put `"meet"` in `cat_finance` next to `ownrep`, and labels in **both** `labels.ar` («اجتماع المالك») and `labels.en` ("Owner meeting") — a missing label shows the word "undefined".
- **P5** — permissions: `("/api/meet/", "meet")` in `_ROLE_READ_RULES` and `_ROLE_WRITE_RULES`; non-admins see the tab only after Faisal ticks it in الصلاحيات. Public owner routes live OUTSIDE `/api/meet/` (e.g. `/m/{token}`, `/api/meet-t/{token}`) so the role rule never 403s the owner's phone.
- **P6** — reservations for any window come from `fetch_reservations_window` / `fetch_reservations_window_checked`, **never** `get_reservations_cached()` (truncates at ~6,000 rows — the 18,842-instead-of-48,114 owner-statement bug).
- **P7** — PMS independence: the package never calls Hostaway itself. Everything PMS-shaped comes through HOST caps implemented in bot.py, so the planned **Hostaway → StayHub** migration changes bot.py's caps only.
- **P8** — PDF via the shared Chromium (`ouja_render._pw_pool` / `_pw_print`, Python ≥ 3.12 on Railway). Any PDF failure falls back to the HTML link and never blocks the meeting. In PDF text, **dates are written in Arabic words** (an ISO date inside Arabic text is reordered by bidi — the ownerbill lesson).
- **P9** — speed: the owner pages were slow before (accountant reported multi-minute loads). Snapshot building runs in the background with a progress indicator, reuses `_owner_portal_cache` and the parallel month warm-up already in `_owner_portal_data`, and never blocks a request thread. Target: a snapshot for one apartment × 12 months in < 20 s warm, < 90 s cold; the presentation itself opens in < 1 s because it renders the frozen snapshot.
- **P10** — run the full CLAUDE.md VERIFICATION ROUTINE before every "done": py_compile, pyflakes, `node --check` on every JS file, the full unittest suite, the DASHBOARD_HTML esprima parse.
- **P11** — feature flag `OWNER_MEET_ENABLED` (default `1`); nothing is ever sent to an owner automatically — sending is a button Faisal presses.

---

## 3. Data sources (HOST caps — name them exactly in the spec; read-only)

| Chapter need | Store / function in bot.py (verify each before relying on it) |
|---|---|
| Owner, units, terms | `_owner_registry`, `_owner_lids(owner, listings)`, `_owner_info_by_lid(lid)`, `finance/owners.terms_on`, `contract_window` |
| Money per month | `_owner_month_report(owner, mkey)` → `total_income`, `ouja_fee`, `expenses`, `owner_net`, `resv_lines`, `exp_lines`, `degraded`, `computed_at` |
| Trend, occupancy, channel mix, net/night by day type, next month on the books, drivers | `_owner_portal_data(owner, mkey)` (already computed — reuse, don't duplicate) |
| Nights, occupancy, peers | `fetch_reservations_window(start, end)` + `_explode_nights(...)`, `events_for_date(d)` |
| Reviews (all, with text) | `_reviews` (`listing_id`, `rating`, `rating_raw` 10-point, `public_review`, `private_review` → presenter only, `date`, `raw.reviewCategory`/`reviewCategories` sub-scores). Use exact 10-point math like `reviewask` (avg > 4.75 ⇔ 2R > 19n); a 0/empty score is not a review. If the Hostaway payload carries the host's public response, store and show it; if not, show what `reviewask` recorded (message sent / call made / outcome) as «تابعنا مع الضيف». Do not invent a response. |
| Review follow-up | `reviewask` rv tables (rooms, presses, outcomes) for this unit's checkouts |
| Maintenance | `_dtk["tickets"]` records with `kind == "maint"` (`lid`, `unit`, `urgency`, `category`, `summary`, `status`, `created_at`, close time, `origin` e.g. `review_call`) **joined** with the dashboard tracker `_tickets` (`lid`, `category`, `priority`, `status`, `cost`, `vendor`, `log`) via `dash_id`; cost from linked expenses when present. Show: date, category, a **redacted** summary (strip names/phones), who found it (guest / Ouja team / review call), time to close in hours, cost. Stats: count, open now, median hours to close, total cost, share found by our team before a guest complained. |
| Purchases for the unit | `_dtk["tickets"]` `kind == "proc"` |
| Reimbursements (RR / AirCover) | `_dtk["tickets"]` `kind == "rr"`: `type` (Arabic label from `_RR_TYPES`), `items_raw` (via `_rr_item_lines`), `total_raw`, `status` (`_RR_STATUS`), `created_at`, departure date from the enrichment, `closeout` (`claimed`, `received`, `payer`, `at`, `less_reason`, `note`). Outcome from `_rr_outcome(claimed, received)`; Arabic wording of Airbnb's answer from `_rr_ar_texts(rec, co)` (reuse — it already translates the agent's English). Per-unit totals consistent with `_rr_summary`. Show the 14-day AirCover filing window for open claims. Never the reservation code or guest name. |
| Guest recovery calls | `recovery/` tables for the unit (calls made, outcome) |
| Price actions | `_price_log` entries for the unit's lids where `dry` is false |
| Permit | `permits` package: the unit's Ministry of Tourism permit, days left, renewal state (the permit is in the OWNER's name — this is a real meeting item) |
| Cleaning | oujact cleaning reports / quality scores for the unit if the store exists; otherwise the chapter omits that row (no placeholder) |
| Direct bookings | `directpay` rows for the unit (count + collected), only if any |
| Market | `cp/data/cp_market.json` (AirDNA Riyadh, dated) and `cp/data/cp_benchmarks.json` (each with value, as_of, source — render the source and date under the number) |
| Airbnb funnel & promotions | NEW: the Airbnb opportunity report importer (§6) |

---

## 4. Screens

### 4.1 Tab «اجتماع المالك» (dashboard, cat_finance)
- Pick owner → his units (or one unit) → period: this month / last month / quarter / year-to-date / **since last meeting** (default when one exists) / custom.
- «تجهيز الاجتماع» → background snapshot build with progress → shows readiness checks before presenting: degraded pull? missing management %? unmapped Airbnb listing? permit unknown? Each check is a line with a fix link, never a silent pass.
- List of past meetings per owner: date, period, decisions count, open commitments, sent status, owner opened the link (count, last opened).
- «استيراد تقرير Airbnb» (admin/ops): upload, preview, map, commit (§6).

### 4.2 Presentation `/meet/{meeting_id}` (login required — this is the tab he shares)
- 16:9 stage, 1280×720 design canvas scaled to the window with container-query units; one chapter visible at a time; ← next / → previous (RTL), Space/PageDown next, `F` full screen, `B` black screen, `N` opens the presenter window. Thin chapter progress line, no clutter. Opens in < 1 s from the snapshot.
- No admin chrome on the shared tab. Nothing internal is in the DOM of this page at all (R1–R5 apply to the HTML source, not just what is visible).

### 4.3 Presenter window `/meet/{meeting_id}/notes` (login required — never shared)
- Synced to the presentation through `BroadcastChannel` (same browser) with a short-poll fallback (phone): current chapter, next chapter title, elapsed time, talking points per chapter, the internal flags (private guest feedback, test-group membership, staff on the unit, any red readiness check), and the **decision recorder** (§8).

### 4.4 Owner link `/m/{token}` + PDF `/m/{token}.pdf` (public, read-only, web_thread, rate-limited)
- Exactly the frozen snapshot that was presented + the decisions, as a vertical page on a phone and the same 16:9 pages in the PDF. Token rules like the owner portal (`token_urlsafe(32)`, revocable, open count). No login. Wrong token → 404 identical to any other 404.

---

## 5. The chapters (owner-facing copy in simplified standard Arabic — NOT Najdi)

Tone (Faisal's standing rule for owner documents): written by an operator who already decided — «اكتشفنا… ونطبّق من الآن» — never asking permission, no apologies, no guarantees table. Forecasts are labelled «هدف، وليس وعداً». Close every meeting on «نلاحق كل ريال لشقتك.» Under **every** chart and number block: a one-line source with its date. Visual over text: the eye should read more than the words.

0. **ما وعدناك به في الاجتماع الماضي** (only when a previous meeting exists): each commitment → done / in progress / not done, with the date and evidence (ticket closed, photo uploaded, permit renewed).
1. **الغلاف** — apartment name, bedrooms, period, meeting date; three numbers: owner net for the period, guest rating, bookings.
2. **الخلاصة** — one generated headline sentence (rules in the spec; e.g. income percentile band + the most important weakness) + 4 KPIs (guest paid or booking income, owner net, rating, booked share of the next 14 nights) each with a band chip.
3. **أين ذهب كل ريال** — the waterfall (M3), right-to-left reading order, plus «من كل 100 ريال: X للمالك» and each deduction per 100.
4. **شهراً بشهر** — owner net per month (bars) and occupancy per month as a **second small chart** (never a dual axis). Shade Ramadan/Eid windows from the Hijri calendar; annotate known outages (e.g. the September 2026 operating pause until 16 Sep) from an admin-editable annotations list, not hard-coded.
5. **مكانك بين شققنا** — bands (R1) for: booking income, net per available night, occupancy, ADR, rating, and the **fair-share index** (unit RevPAR ÷ peer-median RevPAR × 100; 100 = fair share), plus the market line from AirDNA with its date and source. Peer group = same bedroom count, active in the whole period.
6. **كيف يصل إلينا الضيف** — from the latest Airbnb report: per 10,000 search appearances → views (search→booking ÷ view→booking) → bookings, his unit vs the peer median, side by side; Guest Favorite badge; the unit's promotion settings in plain words.
7. **سجلّ الشقة** — a single timeline of everything that happened in the period: maintenance tickets, purchases, reimbursement claims and answers, reviews, guest-recovery calls, price changes, permit events, direct bookings; counters on top.
8. **الصيانة** — the ticket table and stats from §3.
9. **طلبات التعويض** — recovery ring (received ÷ claimed for closed claims), claimed / received totals, each claim: type, items, claimed, received, outcome chip (استُلم كاملاً / جزئياً / رُفضت / قيد المراجعة), payer, Airbnb's answer in Arabic, and for open claims the AirCover deadline.
10. **ماذا قال الضيوف** — every review in the period with stars, date, first name, full public text, our response/follow-up; sub-score bars (cleanliness, accuracy, check-in, communication, location, value) from the review categories; rating trend vs the 4.75 target.
11. **ما اكتشفناه وما نطبّقه من الآن** — the action list from the engine (§7), each with the evidence number that triggered it and a date. Includes owner-side items (permit documents, approval needed for a spend with its SAR amount).
12. **الربع القادم** — before/after forecast in SAR from his own data: "على الوتيرة الحالية" = trailing three full months' owner net × 3 (seasonality-adjusted when a year of history exists), "الهدف" = base × (1 + Σ uplifts of the actions applied), each uplift listed beside it, all labelled targets. Next meeting date. «نلاحق كل ريال لشقتك.»

Multi-unit owner: a portfolio cover + his units side by side (his own units may be named and compared with each other — they are his), then chapters 2–12 per unit in order, with a unit switcher in the presenter window.

---

## 6. Airbnb opportunity report importer

- Accept the export as TSV/CSV/XLSX. Parse by **header names**, not column positions (the v5 file has a disclaimer row, a "Data As Of" row, two header rows, and duplicate header names like "Median Discount of Similar Listings" — disambiguate by the group header above). Read `Data As Of` and store it.
- Fields: listing id (inside "Title (Listing ID)"), bedrooms, opportunity rank, lifetime bookings, bookings L365, search→booking YTD, view→booking YTD, gross booking value YTD (USD → SAR at an admin-set rate, default 3.75, shown), GBV YoY, occupancy next 3 months (+YoY), lifetime rating, Guest Favorite, top-rated-guest discount eligibility, weekly/monthly/early-bird current vs similar-listing median, cleaning fee, non-refundable eligibility, new-listing-promotion eligibility, last-minute discount + lead days, available nights next 14 days. Blank ≠ zero: store `None`.
- Map Airbnb listing id → Hostaway listing: first check the live Hostaway listing payload for an Airbnb id/URL field and document it in the spec; otherwise auto-suggest by title similarity and let an admin confirm once (stored). Unmapped rows are shown, never dropped.
- Keep every import as a dated snapshot (never overwrite); the meeting uses the latest snapshot at or before the meeting date and shows its date.
- Test with `tests/fixtures/owner_meet/host_opportunity_2026-10-04.tsv`: 42 rows; opportunity rank 8 is absent in the file (must not crash); 8 rows have no "available nights next 14 days" because Airbnb only fills it inside the last-minute section; total GBV = USD 896,734; median lifetime rating 4.815; 15 listings below 4.75.

---

## 7. Action engine (pure functions, TDD, thresholds in an admin-editable JSON)

Inputs: the snapshot (money, reviews, tickets, claims, permit, Airbnb row, peers). Output: ordered actions `{key, owner_text, internal_note, evidence, due, role}`. Defaults (from the October 2026 plan):

| key | Trigger | Owner-facing text (gist) | Internal role |
|---|---|---|---|
| `rate` | lifetime or period rating < 4.75 | raise rating: contact every departing guest, fix the cause of the last sub-5 reviews | مدير الحساب |
| `new` | < 25 bookings in 365 days | build the first 10 reviews before any extra discount | مدير الحساب |
| `ctr` | views per 100 search appearances in the lowest quarter | new cover photo + title (Ouja naming rule: starts with «Ouja \|», mentions self-entry, < 50 characters) | المحتوى |
| `page` | view→booking in the lowest quarter AND income below the peer median | review price vs similar units + photo order | المنصة |
| `pace` | ≥ 13 of the next 14 nights open | daily price review for those nights | المنصة |
| `maint_open` | an open maintenance ticket | close it by a stated date, send the owner a photo | العمليات |
| `rr_open` | an open reimbursement claim | follow up until AirCover answers | التعويضات |
| `permit` | permit ≤ 90 days left or unknown | owner documents needed by a date | العمليات |
| `floor` | always, until a min price exists for the unit | a minimum nightly price protects the unit from stacked platform discounts | المنصة |
| `test` | unit in the promotions test group A | a measured 45-day discount trial with a day-21 stop rule (owner text only; group B never mentioned) | المنصة |

Promotion lever defaults (internal, shown in the presenter window, not to owners): weekly 10% and early-bird 10% at 60 days → test only; monthly → no (the new لائحة وحدة الضيافة الخاصة caps consecutive stays at 29 nights, and monthly guests belong to the direct monthly product); non-refundable → no unless cancelled nights > 8% of booked nights over 90 days; last-minute 1% → remove (below Airbnb's display threshold); new-listing promotion → yes for every new listing. Airbnb applies only one of new-listing / custom / length-of-stay / early-bird / last-minute per night (in that priority); top-rated-guest and non-refundable stack on top — the engine warns when a unit's combined worst-case discount exceeds an admin-set ceiling.

Uplift assumptions for chapter 12 live in the same JSON (defaults: rate +3%, ctr +4%, page +3%, pace +2%, test +3%, season +2%, total capped at +15%), each printed beside the target.

---

## 8. Meeting record (decisions and commitments)

- Tables in `brain.db` via `owner_meet/db.py` (`meet_meetings`, `meet_snapshots`, `meet_decisions`, `meet_commitments`, `meet_links`, `meet_events`). Snapshot = JSON + `sha256` + `data_as_of` + version; a sent snapshot is immutable (reopen = admin + reason → new version).
- Presenter window recorder: «قرار» (owner approved X, optional SAR amount), «التزام علينا» (what, role, due date), «التزام على المالك» (what, due date). Optional: a commitment can open a real maintenance ticket through the existing `_maint_open_ticket(..., origin="owner_meeting", origin_ref=<meeting id>)` path — old callers byte-for-byte unchanged (same pattern reviewask used).
- Chapter 0 of the next meeting reads these commitments and their evidence automatically.
- «إرسال للمالك» → freezes, creates the token link + PDF, and prepares a WhatsApp message with the link signed by Faisal (one-tap `wa.me` redirect like `/rv/<token>`); nothing is sent without his tap.

---

## 9. Design (match `docs/owner_meet/prototype.html`, then make it better with impeccable)

- Fonts: Thmanyah — `fonts/ThmanyahSans-{Regular,Medium,Bold}.woff2` for text, `fonts/ThmanyahSerifDisplay-{Bold,Black}.woff2` for headlines and big numbers (same files the digest uses). No Google fonts, no CDN.
- Colours: reuse `digest/render/tokens.py` (navy ink `#0B1A2E`, paper, gold accent `#C6A15B`/`#B8893E`, green = in the owner's favour, red = against, blue data series); paper slides with navy for the cover. Status colours always paired with a word or icon, never colour alone.
- Charts: hand-built SVG from pure Python functions in `owner_meet/charts.py` (one renderer for the web page and the PDF; deterministic so golden tests work). Zero-based bars, 4px rounded data ends, thin marks, direct labels on the few values that matter, recessive grid, no dual axis, no pie with more than 4 slices, bands instead of dots for peers (R1). Every chart has a text alternative.
- Layout: 1280×720 canvas, generous margins, one idea per chapter, numbers in tabular figures, Latin listing names isolated with `dir="ltr"`, Arabic text in SVG with explicit RTL handling (the prototype shows the anchor trap). Phone view of the owner link stacks chapters vertically with no horizontal scroll at 390 px.
- Motion: chapter cross-fade ≤ 280 ms `cubic-bezier(0.23,1,0.32,1)`, nothing else animates; respect `prefers-reduced-motion`.
- It must not look like PowerPoint or a generic AI dashboard: no card grids, no gradients, no emoji, no glass. Editorial, like a design-studio annual report.

---

## 10. Tests and gates (minimum)

- `tests/test_owner_meet_engine.py` — headline rules, bands/percentiles (rounding, < 6 peers fallback), fair-share index, action triggers on synthetic data, forecast math, uplift cap, discount-stack warning.
- `tests/test_owner_meet_money.py` — M1: meeting owner net == Σ `owner_net` of `_owner_month_report` for 1, 3 and 12-month periods on synthetic reservations/expenses; degraded flag blocks send.
- `tests/test_owner_meet_privacy.py` — R1–R6 greps on rendered HTML and PDF text (see §2).
- `tests/test_owner_meet_import.py` — the real TSV fixture facts in §6 + an XLSX round-trip + a malformed file refused with a clear Arabic message.
- `tests/test_owner_meet_ops.py` — maintenance/RR/review joins on fixtures: dedupe by `dash_id`, outcome chips match `_rr_outcome`, 14-day AirCover window, 0-score reviews ignored, private feedback never in owner HTML.
- `tests/test_owner_meet_structure.py` — no `import bot`, no `to_thread(`, zero backslashes, NAV labels in ar+en, role rules present, public handlers in `GUEST_HANDLERS`.
- Layout audit with Playwright: every chapter at 1280×720 has no overflow/clipped text; the owner link at 390 px has no horizontal scroll; PDF page count = chapter count.
- `node --check owner_meet/static/*.js`, and the whole CLAUDE.md routine.

---

## 11. Slices (stop for Faisal's screenshot review after each)

1. **S0** — spec + plan + GATES.md. Stop.
2. **S1** — package skeleton, HOST caps, snapshot builder (money, trend, peers) with tests; no UI. Prove M1.
3. **S2** — presentation + presenter window for chapters 1–6 on a real unit (dry: nothing sent). Screenshots desktop + phone.
4. **S3** — chapters 7–10 (timeline, maintenance, reimbursements, reviews) + privacy tests.
5. **S4** — Airbnb importer + mapping UI + action engine + chapters 11–12.
6. **S5** — meeting record, chapter 0, owner link + PDF + WhatsApp one-tap.
7. **S6** — impeccable critique → audit → polish → harden pass on every screen; performance check against P9; final verification routine.

Report after each slice in plain Najdi: what changed, files and line counts, how to undo in one step, what to click to see it.
