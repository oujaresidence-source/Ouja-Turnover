# «اجتماع المالك» — Owner Meeting Room · design spec

Brief: `docs/owner_meet/PROMPT.md` (Faisal, 2026-10-06). Design reference: `docs/owner_meet/prototype.html`.
Lever defaults: `docs/owner_meet/airbnb-plan-2026-10.pdf`. Package: `owner_meet/`. Tables: `meet_*` in brain.db.
Branch `feat/owner-meet`, worktree `~/ouja-wt-meet`, from origin/main `950c9ee`. **Not pushed.**
Status: DRAFT, awaiting Faisal's approval (S0). The brief wins wherever this spec is silent. Where this
spec differs from the brief, the difference is listed in §14 with the reason.

Baseline before any edit (`.unlazy-baseline-meet.txt`): 5,126 tests, **3 failures already on main**
(`test_ops_capture.TestBackfill` ×2, `test_train_export.TrainSinceMusaed` — date-dependent, not ours).
"No new failures" is measured against that file.

---

## 1. Goal

A per-apartment **meeting room** Faisal opens before an owner meeting:

1. **Before.** One click builds a frozen snapshot for one apartment (or one owner's units) for a period. The build runs in the background with progress, followed by readiness checks.
2. **During.** He shares one browser tab with a 16:9 presentation and drives it with the arrow keys. His talking points and the decision recorder sit in a second window that he does not share.
3. **After.** One button freezes the snapshot. It creates a read-only owner link and a PDF of exactly what was shown, plus the decisions. It then prepares a WhatsApp message that Faisal sends with his own tap.
4. **Next time.** Chapter 0 opens with what we promised last time and what happened.

Precedent: the hotel-management **owner's report / owner business review** (P&L, comp-set index, guest scores, action list). We follow it per apartment, with our own portfolio as the comp set.

## 2. Owner rules (absolute — each is a gate in `owner_meet/GATES.md`)

| # | Rule | How it is enforced (structure, not discipline) |
|---|---|---|
| R1 | Never reveal how many units Ouja manages. No counts, ranks, dots, or "n=". | Peer arrays never leave `engine.peer_bands()`. The snapshot's owner part holds only `{p25,p50,p75,value,label}`. Percentiles are rounded to 10. A privacy scan fails closed. |
| R2 | No other owner's data (names, units, addresses, figures). | Same as R1. Peer stats are reduced server-side. The owner renderer only ever receives `snapshot["owner"]`. |
| R3 | No guest identity. Public review text may carry the first name Airbnb shows publicly. `private_review` is presenter-only. | `redact.py` removes these at build time. `privacy.scan()` checks for `HM[A-Z0-9]{8}`, `05\d{8}`, `9665\d{8}`, emails, Hostaway reservation ids, and the full names of the unit's guests in the period. |
| R4 | No staff names or staff performance. | The ticket source is one of «الضيف» / «فريق عوجا» / «مكالمة تقييم». Every `*_by`, `opener`, `assignee`, `claimed_by`, `closeout.by`, `trail` field is dropped by `redact.py`. Roster names go into the scan list. |
| R5 | No Ouja internal economics. Only this owner's own management %. | The owner part has no per-turnover cost, subscription cost, margin, or other fee rates. The scan list includes the words for these. |
| R6 | Numbers come only from real stores. Missing data = an honest empty state. No «مثال». | The renderer has an empty-state string per block. A structure test asserts «مثال توضيحي» appears in no `owner_meet/*.py` / static file. |
| M1 | One money truth. | §5. Tested to the halala. |
| M2 | Management % comes from `finance/owners.terms_on`. | Read through a HOST cap. It is never a literal. |
| M3 | The waterfall uses real fields only. There is no ÷1.15 or ×0.822 in production. | §5.2. A structure test greps for `1.15` / `0.822` / `/ 1.15`. |
| M4 | A degraded pull blocks «إرسال للمالك» and shows a red banner. | `meeting.can_send()` refuses. Tested. |
| M5 | Receipts go through `/fin/receipt/{id}?t=<owner portal token>`. | Same proxy the owner portal uses. |
| P1–P11 | Platform traps from the brief. | §11 and the structure test. |
| — | Nothing is sent to an owner automatically. | No scheduler in the package. «إرسال» only builds the link. WhatsApp opens only on Faisal's tap. |
| — | Never touch the money math. | Gates diff `compute_owner_report`, `build_owner_report`, `finance/owners.py` and `_maint_open_ticket` against origin/main. They must be byte-for-byte unchanged. |

## 3. Architecture

```
owner_meet/
  __init__.py      wire(caps), bootstrap(), register_routes(app), enabled()
  host.py          _Host + HOST + wire() + require()       (copy of permits/host.py)
  config.py        env flags; rules loader (repo seed ← $STATE_DIR/owner_meet_rules.json, mtime re-read, last-good on a broken edit)
  rules.seed.json  thresholds, uplifts, lever defaults, discount ceiling, fx, test-group list, seasons fallback
  db.py            brain.db tables (§9), closing(connect()), journal DELETE, _ensure() once per path
  periods.py       PURE: period → month keys + exact date window; "since last meeting"
  money.py         PURE over cap output: Σ months, per-unit slice, waterfall rows, per-100 split
  engine.py        PURE: percentiles/bands, fair-share, headline, actions, forecast, discount stack
  ops.py           PURE joins: maintenance, purchases, RR, reviews, recovery, price actions, permit, directpay, cleaning
  redact.py        PURE: strip names/phones/codes/staff from free text; first-name rule
  privacy.py       PURE: scan(text, forbidden) → hits; forbidden-list builder
  airbnb_import.py PURE parser (TSV/CSV/XLSX by header names) + mapping suggestions
  snapshot.py      builder: calls HOST caps, then the pure modules → {"owner": …, "presenter": …, "meta": …}
  jobs.py          background build pool (2 workers, own executor, never the web lane), progress dict
  charts.py        PURE SVG renderers (deterministic → golden tests)
  texts.py         all owner-facing Arabic copy, headline templates, empty states
  render.py        HTML for: presentation, presenter window, owner link (phone), PDF pages — ZERO backslashes
  pdf.py           16:9 PDF through the shared Chromium pool (§10)
  routes.py        every handler; HOST.web_thread; rate limiter; font route
  static/owner_meet_tab.js   dashboard tab (node --check)
  static/stage.js            presentation keys, scaling, BroadcastChannel (node --check)
  static/notes.js            presenter window + recorder (node --check)
  GATES.md
```

The package **never** `import bot` and never calls Hostaway. Everything PMS-shaped arrives as a HOST cap that bot.py implements (`_owner_meet_caps()`, same pattern as `_permits_caps()`). This way the Hostaway → StayHub migration only changes bot.py.

**bot.py edits (additive only):**
- the import guard (`import owner_meet as _owner_meet`, `_HAS_OWNER_MEET = OWNER_MEET_ENABLED=="1"`)
- `_owner_meet_caps()`
- the wire/bootstrap/register block in `start_web_server`
- `NAV_DEF` item + `cat_finance` + `labels.ar`/`labels.en`
- `_ROLE_READ_RULES`/`_ROLE_WRITE_RULES` entries
- the `view_meet` section + a ≤15-line stub + the `go()` line + the `__OWNER_MEET_JS_V__` cache-buster

## 4. HOST caps (bot.py → package). Read-only unless marked.

Every cap is a thin wrapper over an existing function. Nothing is re-implemented.

| Cap | Wraps (verified on origin/main 950c9ee) | Returns |
|---|---|---|
| `owners()` | `_owner_registry` grouped by owner | `[{owner, units:[{apartment, lid}]}]` |
| `owner_lids(owner)` | `_owner_lids(owner, get_listings_map())` | `[int]` |
| `unit_info(lid)` | `_owner_info_by_lid` + listings store `bedrooms` (Hostaway `bedroomsNumber`; **not** `bedsNumber`) + `get_listings_map()` name | `{lid, name, bedrooms, owner, apartment}` |
| `terms_on(lid, date)` | `finance.owners.terms_on(apartment, date, registry_rec)` with the rec from `_owner_info_by_lid` (terms_on reads its base values from that record) | `{mgmt_pct, cleaning:{type, amount}}` |
| `contract_window(apartment)` | `finance.owners.contract_window` | `(from, to)` |
| `month_report(owner, mkey)` | `_owner_month_report` (SWR + single-flight + `_owner_portal_cache`) | the statement dict (keys in §5.1) |
| `unit_month(owner, mkey, lid)` | `finance.owners.unit_slice(_owner_month_report(owner, mkey), lid)` | the same dict shape for one apartment |
| `listings_meta()` | `_ls_get()["listings"]` (local store, no Hostaway call) | `{lid: {name, bedrooms, active}}` |
| `cached_unit_nets(mkeys)` | `apartments[]` of reports already in `_owner_portal_cache` (never computes) | `{lid: {mkey: owner_net}}` |
| `portal_data(owner, mkey)` | `_owner_portal_data` | trend / occupancy / channel_mix / adr_daytype / next_month / drivers |
| `owner_portal_token(owner)` | `_owner_links[owner]` if active, else `None` (it never creates one) | str or None |
| `reservations_window(start, end)` | `fetch_reservations_window_checked` — **never** `get_reservations_cached()` | `(rows, degraded)` |
| `explode_nights(rows)` | `_explode_nights` | `(nights, arrivals)` |
| `season_windows(start, end)` | `_DNA_SEASONS` table (Umm al-Qura based, 2024–2027). Beyond 2027, `hijridate` when importable. Otherwise `[]` plus a presenter note. | `[{kind, start, end}]` |
| `reviews_for(lids)` | `_reviews` values (seed + live), raw kept | list |
| `review_followups(lids, start, end)` | reviewask `rv_tickets` + `rv_events` (state, mode, close_note) | list |
| `maint_tickets(lids)` | `_dtk["tickets"]` kind `maint` + `_dash_ticket(dash_id)` | list (raw — redacted in the package) |
| `proc_tickets(lids)` | `_dtk["tickets"]` kind `proc` where `unit_ids` ∩ lids | list |
| `rr_tickets(lids, unit_names)` | `_dtk["tickets"]` kind `rr` (`lid` is filled only after `_rr_stamp_enrich`, so the fallback match is on `unit`) | list |
| `rr_outcome(claimed, received)` | `_rr_outcome` | `unknown|denied|received|over|full|partial` |
| `rr_ar_texts(rec)` | `_rr_ar_texts(rec, rec["closeout"])` — **build time only**, cached in the snapshot (it calls Claude) | `{story, reason, note, ok}` |
| `rr_item_lines(items_raw)` | `_rr_item_lines` | `(lines, hidden)` |
| `rr_types()` / `rr_status()` | `_RR_TYPES` / `_RR_STATUS` | label maps |
| `recovery_for(lids, start, end)` | `recovery_tickets` (status, contact_outcome, resolved_at, compensation_sar) | list |
| `price_actions(lids, start, end)` | `_price_log` keys `lid\|date`, entries with `dry` false | list `{date, old, new, source, ts}` |
| `permit_for(lid)` | `permits.db.permits("active")` filtered on `listing_id` + `permits.engine.describe` + `live_ticket` | `{end_date, days_left, band, renewal_state}` or `None` (unknown) |
| `directpay_for(lids, start, end)` | `directpay_tickets` (status, `received_sar` when `verified`) | list |
| `cleaning_feedback(lids, start, end)` | `_cleaning_feedback` (guest score 1–5) | list `{lid, score, ts_done}` |
| `airbnb_room_id(lid)` | `_airbnb_link(listing)` (regex over the live listing payload, already in production) | str or None |
| `min_price(lid)` | the pricing floor, if a per-listing floor store exists (to verify in S4, see §14) | int or None |
| `staff_names()` | assignments / schedule roster names (privacy forbidden list only) | `[str]` |
| `market()` | `cp/data/cp_market.json` + `cp_benchmarks.json` (value, as_of/source_date, source) | dict |
| `dash_auth`, `req_role`, `actor`, `tab_allowed(request,"meet")`, `json_response`, `web`, `web_thread`, `tz`, `now`, `state_dir`, `link_base` | as for permits/reviewask | — |

## 5. Money (M1–M5)

### 5.1 Source
`month_report(owner, mkey)` returns the dict built by `_finance_aggregate` plus `compute_owner_statement` / the published snapshot.

Keys used:
- `total_income`, `income_airbnb`, `income_direct`, `extras`, `manual_income`, `ouja_fee`, `management_pct`
- `cleaning{type,total}`, `expenses`, `owner_net`
- `apartments[{lid, total_income, ouja_fee, expenses, cleaning, owner_net}]`
- `resv_lines`, `exp_lines`, `adjustments_total`
- `degraded`, `computed_at`, `statement_status`, `published_version`

### 5.2 Rules
- **Period → months.** Money always uses whole statement months (`YYYY-MM`). The current month is included as "حتى تاريخه" and labelled. Operational chapters (tickets, reviews, claims) use the exact date window. A custom period snaps to months for money, and the snap is printed under the number.
- **Owner-level net** = Σ `owner_net` over the months.
- **Unit-level net** = Σ `unit_slice(month_report(owner, m), lid).owner_net` over the months (§14 item 9).
  - When the owner's units don't sum to the owner total, the presenter window shows «بنود على مستوى المالك لا تتبع شقة: X ريال».
  - The meeting for ALL of an owner's units uses the owner-level `owner_net`.
- **Test (M1).** Synthetic reservations/expenses run through the real `_owner_month_report` path (the test_owner_perf_budget harness: stubbed `api_get`, no mocks of money code) for 1, 3 and 12 months, at owner and unit level.
  - The meeting's net must equal Σ `owner_net` of `_owner_month_report` / `unit_slice` to the halala, using `Decimal` quantize on 0.01.
  - It must also equal a figure computed independently from the fixture's own payouts, fee % and expenses (positive control).
- **Waterfall (M3), default — no new Hostaway fields.** The rows are:
  1. «صافي الحجوزات من Airbnb والحجز المباشر» (`total_income`)
  2. − «رسوم عوجا (X٪)» (`ouja_fee`, with % from `management_pct` / `terms_on`)
  3. − «التنظيف» (only when `cleaning.type == "owner"`)
  4. − «مصاريف الشقة» (`expenses`)
  5. ± «تعديلات الكشف» (`adjustments_total`, only when non-zero)
  6. = «صافي المالك»

  The rows must reconcile to `owner_net` within 0.01. If they don't, the chapter falls back to the statement's own totals with no waterfall, plus a red readiness line. A wrong picture is never drawn.
- **No extended waterfall in this version** (Faisal, 2026-10-06). Today bot.py reads **no** VAT, host-fee or channel-commission field from Hostaway (`airbnbListingHostFee`, `hostChannelFee`, `channelCommissionAmount`, `taxAmount` = zero hits), and no deploy will be made to inspect them. The waterfall therefore starts at «صافي الحجوزات». A later version may add guest-paid rows only after a live field audit approved by Faisal.
- **Per 100.** «من كل 100 ريال: X للمالك» uses the same rows. Rounding is largest-remainder, so the parts sum to 100 exactly.
- **Degraded (M4).** If any month has `degraded`, or `reservations_window` returned degraded=True: a red banner shows in the presenter window, `can_send()` = False, and the readiness check names the month.
- **Receipts (M5).** Each expense line links `/fin/receipt/{id}?t=<owner_portal_token>`. If the owner has no active portal token, the line shows without a receipt link and a readiness line says «رابط بوابة المالك غير مفعّل — الإيصالات لن تظهر». The package never creates a portal token.

## 6. Peers and comparisons (R1)

- **Peer group.** Units with the same bedroom count, **active the whole period**: at least one realized night in every calendar month of the period, from the same `reservations_window` + `explode_nights` pull. The unit itself is excluded from its own peer list. If the group has fewer than 6 units, use the whole portfolio, and the copy says «بكل شققنا» without a number.
- **Metrics per unit**, all from the one reservations pull:
  - booking income: gross nightly `_res_revenue`, which is what `_explode_nights` carries
  - occupancy: booked nights ÷ days in window
  - ADR
  - RevPAR = income ÷ days
  - lifetime rating: exact 10-point mean from `_reviews`, excluding 0/empty, same as reviewask `review_score`
- **Net per available night.** `apartments[lid].owner_net` ÷ days, across every owner's `month_report`. These are read **from cache only** (the 20-minute warmer keeps 5 months warm). A peer whose month isn't cached is excluded from this one band, and the presenter window says how many were excluded (presenter only). If fewer than 6 remain, the band falls back to the portfolio. If still too few, the band is omitted with an honest line.
- **Band** = `{p25, p50, p75, value, label}`. Nothing else leaves `engine.peer_bands()`.
- **Percentile** = (peers below + ½ ties) ÷ peers. Rounded to the nearest 10.
  - ≥ 60 → «أعلى من X٪ من الشقق المشابهة»
  - ≤ 30 → «أقل من أغلب الشقق المشابهة»
  - otherwise → «ضمن النصف الأوسط»
- **Fair-share index** = unit RevPAR ÷ peer-median RevPAR × 100, as an integer. 100 = fair share.
- **Market line.** From `cp_market.json`: occupancy %, ADR SAR, and «المصدر: AirDNA · يوليو 2026». From `cp_benchmarks.json`: each value with its `as_of` and `source`.

## 7. Chapters

Owner copy is in simplified standard Arabic. The tone is an operator who has already decided («اكتشفنا… ونطبّق من الآن»). Forecasts are «هدف، وليس وعداً». Every number block has a source and date line. The meeting closes on «نلاحق كل ريال لشقتك.»

| # | Chapter | Content | Empty state |
|---|---|---|---|
| 0 | ما وعدناك به في الاجتماع الماضي | Each commitment from the previous meeting: done / in progress / not done + date + evidence. Evidence is automatic when a ticket is linked (its close date) or the permit was renewed (`replaced_by_id`); otherwise Faisal's note. | Chapter omitted when there is no previous meeting. |
| 1 | الغلاف | Name (`dir="ltr"` isolated), bedrooms, period, meeting date; owner net, rating, bookings. | — |
| 2 | الخلاصة | Headline (§8.1) + 4 KPIs, each with a band chip: booking income, owner net, rating, booked share of the next 14 nights. | — |
| 3 | أين ذهب كل ريال | Waterfall (§5.2), right-to-left reading order, per-100 split. | Fallback totals. |
| 4 | شهراً بشهر | Owner net bars + a second small occupancy chart (never a dual axis). Ramadan/Eid shading from `season_windows`. Annotations from `meet_annotations`; the seed is the Sept 2026 pause until 16 Sep. | «لا توجد أشهر مكتملة في هذه الفترة» |
| 5 | مكانك بين شققنا | Bands (§6): income, net/available night, occupancy, ADR, rating, fair-share; market line. | A band is omitted with a reason. |
| 6 | كيف يصل إلينا الضيف | Latest Airbnb import ≤ meeting date. Per 10,000 search appearances → views = 10,000·s/v → bookings = 10,000·s, side by side with the peer median. Guest Favorite. Promotion settings in words. The import date is shown. | «لا يوجد تقرير Airbnb مربوط بهذه الشقة» |
| 7 | سجلّ الشقة | One timeline: maintenance, purchases, claims, reviews, recovery calls, price changes (count per week, not every night), permit events, direct bookings, guest cleaning scores. Counters on top. | Per-type empty line. |
| 8 | الصيانة | Table: date, category, redacted summary, source (الضيف / فريق عوجا / مكالمة تقييم), hours to close, cost (`_tickets.cost` or linked expense). Stats: count, open now, median hours, total cost, share found by our team. | «لا توجد تذاكر صيانة في هذه الفترة» |
| 9 | طلبات التعويض | Recovery ring (received ÷ claimed, closed claims only), totals, each claim: type label, item lines, claimed, received, chip (استُلم كاملاً / جزئياً / رُفضت / قيد المراجعة from `_rr_outcome`), payer, Airbnb's answer in Arabic (`_rr_ar_texts`, frozen at build), AirCover deadline (departure + 14 days) for open claims. Never the code or guest. | «لم نفتح طلبات تعويض لهذه الشقة في هذه الفترة» |
| 10 | ماذا قال الضيوف | Every review with a score > 0 in the period: stars, date, first name, full public text, follow-up from reviewask («تابعنا مع الضيف» + outcome). There is no host-response field in our store (verified), so none is invented. Sub-score bars from `reviewCategory`. Trend vs 4.75. `private_review` goes to the presenter window only. | «لا توجد تقييمات في هذه الفترة» |
| 11 | ما اكتشفناه وما نطبّقه من الآن | Actions from §8.2 with evidence number + date; owner-side items (permit documents, approvals with SAR). | — |
| 12 | الربع القادم | Forecast §8.3; next meeting date; closing line. | — |

**Multi-unit owner:**
- a portfolio cover that names his own units and compares them side by side (they are his)
- then chapters 2–12 per unit
- a unit switcher in the presenter window

## 8. Engine (pure, TDD)

### 8.1 Headline
The first matching rule, in order:
1. A degraded pull → no headline (presenter red).
2. A band ≥ 60 on income + a weakness → «شقتك من أعلى X٪ دخلاً، والتقييم أول ما نعمل عليه».
3. Below the median on income → «دخل شقتك أقل من أغلب الشقق المشابهة، وهذه الأسباب الثلاثة».
4. The fallback is the strongest metric.

The ranking of "weakness" is: rating < 4.75 → ctr → page → pace. Each template is in `texts.py` and tested.

### 8.2 Actions
Thresholds are in `rules.seed.json`, admin-editable via `$STATE_DIR/owner_meet_rules.json`. Output per action: `{key, owner_text, internal_note, evidence, due, role}`, ordered by the seed order.

| key | Trigger |
|---|---|
| `rate` | lifetime or period rating < 4.75 |
| `new` | < 25 bookings in 365 days |
| `ctr` | views per 100 search appearances in the lowest quarter |
| `page` | view→booking in the lowest quarter AND income below the peer median |
| `pace` | ≥ 13 of the next 14 nights open |
| `maint_open` | an open maintenance ticket |
| `rr_open` | an open claim |
| `permit` | ≤ 90 days left or unknown |
| `floor` | `min_price(lid)` is None |
| `test` | the unit's Airbnb id is in `rules.promo_test_group_a.airbnb_ids` **and** the list is confirmed by Faisal (§14 item 4). |

**Lever defaults** (presenter window only):
- weekly 10% and early-bird 10% at 60 days → test only
- monthly → no
- non-refundable → no unless cancelled nights > 8% over 90 days
- last-minute 1% → remove
- new-listing promotion → yes

**Discount stack warning.** Worst-case combined discount = one of (new-listing / custom / length-of-stay / early-bird / last-minute), in that priority, stacked with top-rated-guest and non-refundable. A warning fires when this exceeds `rules.discount_ceiling_pct`.

### 8.3 Forecast
- **Base** = trailing 3 full months owner net × 3 (labelled «على الوتيرة الحالية»).
- **With ≥ 12 months of history:** base = Σ last year's same 3 months × (trailing 3 ÷ the same trailing 3 a year earlier).
- **Target** = base × (1 + Σ uplifts of the triggered actions). The cap is `total_cap` (+15%). Each uplift is printed beside it, labelled «هدف، وليس وعداً».
- With fewer than 3 full months: no forecast, «نحتاج ثلاثة أشهر كاملة لنضع هدفاً».

## 9. Storage — brain.db `meet_*`

| Table | Columns (key ones) |
|---|---|
| `meet_meetings` | id, owner, lids (json), period_from, period_to, months (json), meeting_date, state (`draft|building|ready|presented|sent|reopened`), build_progress, build_error, created_by, created_at, updated_at |
| `meet_snapshots` | id, meeting_id, version, sha256, data_as_of, schema_version, json, frozen (0/1), reopen_reason, reopened_by, created_at — UNIQUE(meeting_id, version) |
| `meet_decisions` | id, meeting_id, text, amount_sar, lid, created_by, at |
| `meet_commitments` | id, meeting_id, side (`ouja|owner`), text, role, due, status (`open|done|in_progress|not_done`), evidence, linked_ticket (dtk channel id or dash id), updated_by, updated_at |
| `meet_links` | token (token_urlsafe 32), meeting_id, snapshot_version, active, opens, last_opened_at, created_by, created_at, revoked_at |
| `meet_events` | id, meeting_id, kind (`built|presented|sent|opened|pdf|wa_opened|reopened|revoked`), detail, actor, at |
| `meet_abnb_imports` | id, data_as_of, filename, sha256, rows, fx_sar_per_usd, uploaded_by, at |
| `meet_abnb_rows` | import_id, airbnb_id, json (None ≠ 0) |
| `meet_abnb_map` | airbnb_id PK, lid, method (`payload|title|manual`), confirmed_by, at |
| `meet_annotations` | id, start_date, end_date, text_ar, created_by, at (seeded once: the Sept 2026 pause) |

- A sent snapshot is immutable: no UPDATE path exists on a frozen row.
- Reopening needs an admin + a reason, and creates version + 1. Links keep pointing to the version they were made for.

## 10. Screens

1. **Tab «اجتماع المالك»** (`cat_finance`, next to `ownrep`):
   - owner → units → period (this month / last month / quarter / YTD / since last meeting = default when one exists / custom months)
   - «تجهيز الاجتماع» → progress bar → readiness list. Each line has a fix link: degraded month, missing mgmt %, no Airbnb mapping, permit unknown, unit/owner net mismatch, no portal token.
   - past meetings: date, period, decisions, open commitments, sent, opens + last opened
   - «استيراد تقرير Airbnb» (admin/ops): upload → preview → map → commit
   - rules JSON editor (admin)
   - annotations list (admin)
2. **Presentation `/meet/{id}`** (login + `meet` permission):
   - server-rendered from `snapshot["owner"]` only, so nothing internal is in the DOM
   - a 1280×720 canvas scaled with container-query units
   - keys: ← next / → previous (RTL), Space/PageDown next, `F` fullscreen, `B` black, `N` notes
   - a thin progress line
   - cross-fade ≤ 280 ms `cubic-bezier(0.23,1,0.32,1)`, off under `prefers-reduced-motion`
   - target: opens in < 1 s
3. **Presenter `/meet/{id}/notes`** (login + `meet`):
   - BroadcastChannel sync with a 2-second short-poll fallback (phone) through `/api/meet/{id}/cursor`
   - current/next chapter, timer, talking points, internal flags (private feedback, test group, the unit's coverer, red readiness)
   - the recorder (§11)
4. **Owner link `/m/{token}` + `/m/{token}.pdf`** (public, read-only, web_thread, rate-limited 30/IP/min + 10/token/min like aqd's `_Limiter`):
   - vertical chapters on a phone (no horizontal scroll at 390 px)
   - the PDF is the same 16:9 pages
   - a wrong or revoked token returns the same bytes as any other 404
5. **Fonts:** `/meet/font/{name}` serves an allow-list of the five Thmanyah files (cp pattern). The PDF uses `file://` like digest.

**Design.** Match the prototype, then run impeccable critique → audit → polish → harden.
- **Colours:** `digest/render/tokens.py` — ink #0B1A2E, paper #F7F4EE, gold #C6A15B, green #1F6F55 (favour), red #B23A34 (against), and **Diriyah mud brown #8B5A3C (soft #EBDCCB) for data series** (Faisal 2026-10-06, replacing blue). Status always comes with a word.
- **Type:** Thmanyah Sans for text, Thmanyah Serif Display for headlines and big numbers, tabular figures.
- **Charts** (`charts.py`): zero-based, 4px rounded data ends, recessive grid, direct labels. Bands, never dots. Every chart carries a `<title>` + text alternative. Arabic SVG text uses an explicit `direction="rtl"` + `text-anchor` (the prototype's anchor trap).
- **Not allowed:** card grids, gradients, emoji, glass.

**PDF.** `pdf.py` submits **its own** print function to `ouja_render._pw_pool` and uses `_pw_browser()` under `_pw_lock`. It prints 1280×720 px pages; the shared `_pw_print` is A4-only and is not modified. Dates in PDF text are written in Arabic words («٦ أكتوبر ٢٠٢٦»). Any failure falls back to the HTML link and never blocks the meeting.

## 11. Meeting record and sending

- **Recorder:**
  - «قرار» (text + optional SAR)
  - «التزام علينا» (text, role, due)
  - «التزام على المالك» (text, due)
  - all saved instantly via `/api/meet/{id}/record`
- **A commitment can be linked to an existing ticket** (a dtk channel id or a dash id). Chapter 0 then reads its close date automatically.
- **Opening a NEW maintenance ticket from the recorder is out of scope** (Faisal, 2026-10-06, see §14). `_maint_open_ticket` requires a Discord interaction, and changing it means editing a live function, so it stays byte-for-byte unchanged.
- **«إرسال للمالك»** (admin): refused while `degraded` or a red readiness line is open. It then:
  1. freezes the snapshot
  2. creates a `meet_links` token
  3. renders the PDF (non-blocking)
  4. returns the link + `/api/meet/{id}/wa`, which is a login-gated 302 to `wa.me/<owner phone>?text=<link + Faisal's signature>` and logs `wa_opened`

  Nothing leaves the building until Faisal taps WhatsApp himself.
- **Open tracking:** each `/m/{token}` hit increments `opens` and logs `opened`.

## 12. Airbnb opportunity report importer

- **Formats:** TSV/CSV/XLSX (openpyxl, already a dependency). Columns are found by **header name**. The first row whose cells include `Title (Listing ID)` is the header row. Duplicate names (e.g. `Median Discount of Similar Listings`) are disambiguated by the group header row above. `Data As Of` is read from its row.
- **Fields:** the brief's list. Blank → `None`. `★5.0` → 5.0. `$2,041` → 2041. `%` → fraction.
- **Units:** GBV is in USD, converted to SAR at `rules.fx_sar_per_usd` (3.75), and the rate is shown.
- **Mapping:**
  1. `airbnb_room_id(lid)` from the live listing payload (`_airbnb_link`, already in production)
  2. else title similarity as a suggestion, which an admin confirms once (stored with `method`)

  Unmapped rows are shown, never dropped.
- **Every import is a dated snapshot.** A meeting uses the latest one at or before its meeting date.
- **Fixture facts** (independently measured 2026-10-06 from the file): 42 rows; rank 8 absent; 8 rows with no "Your Available Nights Next 14 Days"; Σ GBV = USD 896,734; median lifetime rating 4.815; 15 below 4.75; `Data As Of` = 2026-10-04.
- **Malformed file** → refused with «الملف لا يشبه تقرير فرص المضيف من Airbnb — ما لقينا عمود Title (Listing ID)».

## 13. Performance (P9)

- **The build runs in `jobs.py`'s own 2-worker pool**, never on the web lane. Progress is polled from the tab.
- **Money:** `month_report` per month, reusing the SWR cache, with ≤ 4 parallel cold months (same as `_owner_portal_data`).
- **Reservations:** one `reservations_window(period)` pull serves the unit, the peers and the timeline.
- **Targets:**
  - 1 unit × 12 months: < 20 s warm, < 90 s cold
  - presentation open: < 1 s, because it renders the frozen JSON

  The cold target is measured live (manual gate). The < 1 s render is measured locally on a fixture snapshot (runnable gate).

## 14. Owner decisions (Faisal, 2026-10-06) and differences from the brief

**Decided:**

1. **Commitment → maintenance ticket: NOT built.** A commitment can be **linked to an existing ticket**, and chapter 0 reads its close date (§11). `_maint_open_ticket` needs a Discord interaction and stays byte-for-byte unchanged. *Approved.*
2. **Waterfall starts at «صافي الحجوزات» in this version.**
   - No deploy to look at live Hostaway data.
   - No guest-paid / VAT / Airbnb-fee rows, and no code path for them.
   - G21 is rewritten as a structure check. *Faisal's ruling.*
3. **Tab is Faisal's only** until he ticks «اجتماع المالك» for someone in الصلاحيات. `OWNER_MEET_ENABLED` defaults to 1. *Approved.*
4. **Test group A is computed, not left empty.**
   - **Method** (the plan PDF's, p.11): group the TSV rows by bedroom count, in ascending bedroom order. Inside each group, sort by Gross Booking Value YTD, highest first, and alternate A/B. The starting letter flips with each successive bedroom group (1-bed starts A, 2-bed starts B, 3-bed starts A, 4-bed starts B).
   - **Result:** this reproduces the PDF's 21/21 split exactly (A ≈ SAR 1.58M, B ≈ 1.78M), and a test locks that.
   - **Storage:** the list is stored by Airbnb listing id in `rules.seed.json` with `confirmed_by: null`.
   - **Until confirmed:** the `test` action **does not fire** until Faisal confirms the list once, which must happen before 5 November 2026. **Confirmed by Faisal on 2026-10-06** («اتأكد») and recorded in the seed. Group B is never mentioned to an owner.

**Differences from the brief:**

5. **`GUEST_HANDLERS`** in `tests/test_web_lane.py` only takes bot.py function names. Package public handlers are asserted by `test_owner_meet_structure` instead (reviewask precedent): `web_thread(` present, `to_thread` absent.
6. **Min price floor** (`floor` action): a per-listing minimum-price store is to be verified in S4. If none exists, the action shows for every unit, which matches the brief's "until a min price exists".
7. **Ramadan/Eid shading** uses the existing `_DNA_SEASONS` table (2024–2027) rather than a new conversion. Beyond 2027 it uses `hijridate` when importable (Railway 3.13; local 3.9 skips it).
8. **Extra tables** beyond the brief's six: `meet_abnb_imports`, `meet_abnb_rows`, `meet_abnb_map`, `meet_annotations`. Each is needed by a brief requirement.
9. **Unit-level money** uses the existing `finance.owners.unit_slice(rep, lid)`, the same per-apartment view the range report and apartment PDF use, over `_owner_month_report`.
   - Owner-level manual lines with no apartment legitimately stay out of the units, so a unit's months can sum to less than the owner total.
   - When that happens it is a presenter-only note, never an error.
10. **The local machine runs Python 3.9.** The real-PDF and Playwright layout gates run under a scratch Python 3.13 venv with playwright + Chromium installed there (nothing installed into the repo).
11. **Airbnb parsing is pulled forward into S1** (`airbnb_import.parse`), because group A must be computed from the TSV now.
