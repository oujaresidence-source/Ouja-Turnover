# Ouja Monthly Rental Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Ouja's current monthly page with the approved Arabic-first guided and browse experience, backed by publish-safe cached data, official monthly pricing, WhatsApp lead handoff, operations health, and measurable lead outcomes.

**Architecture:** A new `monthly_public/` package owns the public monthly product. `bot.py` remains the process host and supplies already-cached listing, calendar, price, licence, authentication, and state-path adapters; customer requests read one validated last-known-good snapshot and never contact Hostaway or a pricing provider. The existing URLs stay in place through thin route adapters, with the old implementation retained behind a local rollback switch until verification finishes.

**Tech Stack:** Python 3 standard library, aiohttp, SQLite, vanilla JavaScript, semantic HTML, local IBM Plex fonts, `unittest`, the existing Playwright/browser runtime, and Git.

**Approved specification:** `/Users/faisalouja/Documents/Codex/2026-08-25/i-have-zero-coding-experience-and/outputs/Ouja-Monthly-Rental-Design-Spec.md`

---

## Verified baseline and constraints

- `bot.py` has 68,016 lines. The new monthly UI and business rules will not be added to that file.
- The live public catalog returned 57 homes on 2026-08-25. Cached calendar data covered 56. Listing `536998`, titled `9- Al Nada`, had no calendar coverage.
- The public quote path can return a displayed percentage above the configured 30% ceiling because `monthly/live.py` replaces the public price and recomputes the percentage without clamping it. The replacement product removes percentages and comparison prices altogether.
- The live public monthly configuration returned no WhatsApp number.
- The Arabic page currently falls back to raw English Hostaway titles, descriptions, and amenities. Ratings reach the API but the page does not display them.
- The customer search and quote path already reads local memory. Hostaway and the pricing engine refresh only in background tasks.
- Baseline test run: 2,924 passed; two existing monthly-PDF layout tests could not start Chromium under the filesystem sandbox. No product assertion failed.
- `supabase_export_listings.csv` contains Wi-Fi credentials. It is ignored by Git and must never be read for public content except through an explicit public-field allowlist. It must never be committed.

## Requirements-to-code map

| Approved requirement | Current source | Planned change | Proof |
| --- | --- | --- | --- |
| Hybrid entry route | Monthly SPA in `bot.py:57897-58346` | New `monthly_public/static/monthly.js` landing with guided and browse entries | Browser journey chooses both routes in Arabic and English |
| One-question adaptive matcher | Reusable ideas in `match/engine.py`; no monthly matcher | `monthly_public/matching.py` plus stateful client flow with purpose branches and preserved back navigation | Unit branch matrix and browser back/change-answer tests |
| Three matches, alternatives, full eligible catalog | Current exact filters/static sort in `bot.py:57719-57833` | Hard publication/availability gates, deterministic fit ranking, price-only tie-break | Ranking tests prove price cannot outrank stronger fit and counts equal eligible IDs |
| Arabic-first structured listing | `/stay` structured data from `_gw_listing_public`; monthly ignores it | `monthly_public/presentation.py` uses bilingual structured fields, mapped amenity groups, deduplicated media, ratings, and licence proof | Content tests reject mixed Arabic pages, duplicate descriptions, blank alt text, and unverified claims |
| Official price without discount theatre | `monthly_quote()` and `monthly/live.py` expose before/after/percentage | `monthly_public/pricing.py` returns rate, total, terms, and no comparison fields | Contract/content tests reject `pct`, `before`, crossed prices, or discount copy |
| Configured terms and WhatsApp | `MONTHLY_WHATSAPP` can be empty and falls back to stay config | Required validated monthly config, explicit blocked state, response-window calculation, and prepared lead message | Missing/invalid config tests plus encoded-message field test |
| Last-known-good data | Catalog, calendar, and engine have independent stores | Atomic `monthly_public/snapshot.py` generation; invalid refresh cannot replace a good generation | 57/56 reconciliation and failed-refresh preservation tests |
| Publication checks | Licence storage exists in `monthly/db.py`; no unified gate | `monthly_public/publication.py` validates licence, language, title/bedrooms, neighbourhood, images, price, calendar, amenities, and terms | One regression test per blocker and stale-calendar pending behavior |
| Operations readiness | `/api/monthly/admin` returns partial health but UI ignores it | `monthly_public/health.py` and an authenticated operations view with red blockers and exact IDs | Health contract tests and rendered dashboard check |
| Monthly funnel and outcomes | Shared event endpoint drops some monthly context and has no monthly funnel | SQLite event/lead stores, controlled outcomes, and funnel aggregation in `monthly_public/analytics.py` | Funnel linkage, privacy, analytics-failure, and lost-reason tests |
| No request-time providers | Existing monthly search reads local dictionaries | Providers run only in the background snapshot adapter; public handlers receive an immutable snapshot | Tests inject providers that raise if called and source scan proves no outbound imports in handlers |
| Accessible, responsive luxury UI | Existing Arabic page has blank image alt text and no async live regions | Local fonts, RTL/LTR, focus states, 44px targets, live regions, reduced motion, responsive imagery, lazy loading | Keyboard/a11y scan, mobile/desktop screenshots, and performance timing |

## File structure

| File | Responsibility |
| --- | --- |
| `monthly_public/contracts.py` | Validate matcher, browse, listing, lead, analytics, and outcome inputs; define stable JSON shapes. |
| `monthly_public/settings.py` | Validate WhatsApp, working hours, commercial terms, and four-to-six-month route; calculate response copy. |
| `monthly_public/publication.py` | Normalize and validate each home; emit blocker and warning codes without inventing data. |
| `monthly_public/snapshot.py` | Build an immutable generation and retain the last good generation after refresh failures. |
| `monthly_public/pricing.py` | Select cached official monthly rates and calculate duration totals and preliminary long-stay labels. |
| `monthly_public/matching.py` | Apply hard eligibility gates, fit scoring, explanations, tradeoffs, alternatives, and truthful empty states. |
| `monthly_public/presentation.py` | Produce bilingual structured listing cards/pages, amenity groups, media, ratings, location proof, and licence details. |
| `monthly_public/analytics.py` | Store minimal anonymous events, leads, responses, and controlled outcomes; aggregate the monthly funnel. |
| `monthly_public/leads.py` | Create idempotent lead references and transient encoded WhatsApp messages. |
| `monthly_public/health.py` | Produce launch blockers, source coverage, conflicts, expiry warnings, and funnel health. |
| `monthly_public/routes.py` | aiohttp handlers that use prepared state only and preserve existing public URLs. |
| `monthly_public/page.py` | Serve the HTML shell, safe boot configuration, and local static assets. |
| `monthly_public/static/monthly.css` | Quiet Riyadh luxury design tokens, responsive layouts, focus, RTL/LTR, and reduced motion. |
| `monthly_public/static/monthly.js` | Landing, matcher, results, browse, listing, lead handoff, language switch, and analytics UI. |
| `monthly_public/preview.py` | Standalone staff-preview server using an explicitly allowlisted real public data export. |
| `bot.py` | Thin cached-data adapters, background snapshot refresh, route wiring, and rollback switch only. |
| `tests/monthly_public_fixtures.py` | Small verified fixtures for deterministic tests; no credentials or copied guest data. |
| `tests/test_monthly_public_*.py` | Unit, contract, integration, content, privacy, and source-boundary tests. |

## Stable internal contracts

`SnapshotStore.refresh(source, settings, now)` accepts a source dictionary with `listings`, `calendar`, `prices`, `licences`, `content`, and source timestamps. It returns a health result, but it changes `current` only when the generation-level schema is valid. Individual invalid homes remain in `blocked` for staff preview and never enter `published`.

`quote_for(listing, request, now)` returns only:

```python
{
    "monthly_rate_sar": 12000,
    "stay_total_sar": 24000,
    "months": 2,
    "move_in": "2026-09-01",
    "move_out": "2026-11-01",
    "currency": "SAR",
    "included": ["internet", "maintenance"],
    "utilities": {"mode": "variable", "label_ar": "...", "label_en": "..."},
    "cleaning": {"mode": "optional", "amount_sar": 300, "label_ar": "...", "label_en": "..."},
    "deposit": {"amount_sar": 2000, "refund_ar": "...", "refund_en": "..."},
    "payment_methods": [{"ar": "...", "en": "..."}],
    "preliminary_contract": False,
}
```

No public response contains `before`, `saved`, `pct`, `ceiling`, or a reference price.

`rank(snapshot, request, lang)` returns `top` (at most three), `alternatives`, `catalog`, `exact_count`, and an `empty_state`. Each top result has two to four fact-backed reasons and at most one fact-backed tradeoff. It never outputs travel time.

## Task 1: Lock public settings and input contracts

**Files:**
- Create: `monthly_public/__init__.py`
- Create: `monthly_public/contracts.py`
- Create: `monthly_public/settings.py`
- Create: `tests/test_monthly_public_contracts.py`
- Create: `tests/test_monthly_public_settings.py`

- [ ] **Step 1: Write failing tests** for invalid dates, duration outside one-to-six months, every purpose branch, E.164-like WhatsApp digits, missing hours, missing commercial terms, missing long-stay route, in-hours copy, and next-response-window copy. Tests use this exact request shape:

```python
request = {
    "purpose": "work",
    "place": {"kind": "destination", "id": "kafd", "label": "KAFD"},
    "residents": 2,
    "sleeping": "one_bedroom",
    "move_in": "2026-09-01",
    "duration_months": 2,
    "flexibility": "fixed",
}
```

- [ ] **Step 2: Run** `python3 -m unittest tests.test_monthly_public_contracts tests.test_monthly_public_settings -v` and confirm failures are missing-module failures.
- [ ] **Step 3: Implement** `parse_match_request`, `parse_browse_query`, `parse_listing_request`, `parse_event`, `parse_outcome`, `load_settings`, and `response_window`. Reject unknown fields that can alter business behavior, preserve safe UTM-free anonymous context, and return field-specific bilingual errors.
- [ ] **Step 4: Re-run** the two test modules and confirm all tests pass.
- [ ] **Step 5: Commit** `feat(monthly): lock public contracts`.

## Task 2: Build publication validation and structured presentation

**Files:**
- Create: `monthly_public/publication.py`
- Create: `monthly_public/presentation.py`
- Create: `tests/monthly_public_fixtures.py`
- Create: `tests/test_monthly_public_publication.py`
- Create: `tests/test_monthly_public_presentation.py`

- [ ] **Step 1: Write failing tests** that block inactive homes, absent/expired licences, missing official prices, missing Arabic or English content, title/bedroom conflicts, generic Riyadh neighbourhoods, fewer than three distinct images, and missing commercial terms. Add tests that keep stale calendars as `availability_pending`, show only source-backed ratings/reviews, omit unknown Arabic amenities, group known amenities bilingually, deduplicate descriptions/images, and never create travel times.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_monthly_public_publication tests.test_monthly_public_presentation -v` and confirm missing-module failures.
- [ ] **Step 3: Implement** `validate_listing(raw, settings, now)`, `title_bedroom_conflict(title, bedrooms)`, `clean_images(images)`, `present_card`, and `present_listing`. Use blocker codes such as `licence_missing`, `licence_expired`, `price_missing`, `arabic_content_missing`, `title_bedroom_conflict`, `neighbourhood_missing`, `images_missing`, and `commercial_terms_missing`. Use warnings `calendar_stale`, `calendar_missing`, `rating_unavailable`, and `untranslated_amenity`.
- [ ] **Step 4: Re-run** both modules and confirm all tests pass, then scan responses for raw English amenity leakage in Arabic mode.
- [ ] **Step 5: Commit** `feat(monthly): validate publishable homes`.

## Task 3: Add official cached pricing and atomic last-known-good snapshots

**Files:**
- Create: `monthly_public/pricing.py`
- Create: `monthly_public/snapshot.py`
- Create: `tests/test_monthly_public_pricing.py`
- Create: `tests/test_monthly_public_snapshot.py`

- [ ] **Step 1: Write failing tests** for one-to-six-month totals, explicit move-out validation, missing month coverage, no legacy fallback price, internet and maintenance inclusions, listing-specific utilities/cleaning, deposits/payment methods, four-to-six-month preliminary text, 57/56 ID reconciliation, stale calendar state, generation-level refresh failure, and preservation of the last good generation.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_monthly_public_pricing tests.test_monthly_public_snapshot -v` and confirm missing-module failures.
- [ ] **Step 3: Implement** `add_months`, `quote_for`, `build_generation`, and `SnapshotStore`. A duration quote uses the verified cached rate approved for the selected start month and duration. It returns no quote when required cached coverage is missing. `SnapshotStore.current` changes by one assignment only after the full generation validates.
- [ ] **Step 4: Re-run** both modules and confirm all tests pass. Assert serialized customer results contain none of `before`, `saved`, `pct`, `ceiling`, `discount`, or `خصم`.
- [ ] **Step 5: Commit** `feat(monthly): keep a safe pricing snapshot`.

## Task 4: Implement deterministic monthly matching

**Files:**
- Create: `monthly_public/matching.py`
- Create: `tests/test_monthly_public_matching.py`

- [ ] **Step 1: Write failing tests** for work, family, treatment, and visit branches; capacity/sleep/date/price hard gates; verified-neighbourhood and verified-coordinate place scoring; no unverified POI score; quality tie-breaks; price-only tie-breaks; top-three/alternatives/catalog partitioning; reason/tradeoff provenance; plus-or-minus-seven-day near matches; and honest empty states.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_monthly_public_matching -v` and confirm a missing-module failure.
- [ ] **Step 3: Implement** `rank(generation, request, lang)`. Use a 100-point fit score with date, place, space, need, and quality blocks. Sort by full fit score, then lower official rate, then stable listing ID. Store reason codes and interpolate only verified listing/request facts. Never output a driving-time estimate.
- [ ] **Step 4: Re-run** the module and confirm all tests pass, including the invariant that a higher-priced stronger fit stays above a cheaper weaker fit.
- [ ] **Step 5: Commit** `feat(monthly): rank verified home matches`.

## Task 5: Create lead, analytics, outcome, and health stores

**Files:**
- Create: `monthly_public/analytics.py`
- Create: `monthly_public/leads.py`
- Create: `monthly_public/health.py`
- Create: `tests/test_monthly_public_analytics.py`
- Create: `tests/test_monthly_public_leads.py`
- Create: `tests/test_monthly_public_health.py`

- [ ] **Step 1: Write failing tests** for lead-reference uniqueness and 30-minute idempotency, all prepared-message fields, no stored message body, event whitelist/context minimization, session-to-lead linkage, analytics failure not blocking lead creation, team response time, booked/lost outcomes, controlled lost reasons, funnel stage counts, exact health coverage, licence expiry, content conflicts, WhatsApp/hours/contract-route blockers, and zero-red-blocker readiness.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_monthly_public_analytics tests.test_monthly_public_leads tests.test_monthly_public_health -v` and confirm missing-module failures.
- [ ] **Step 3: Implement** SQLite schema and `EventStore.record`, `LeadStore.create`, `LeadStore.mark_response`, `LeadStore.set_outcome`, `build_whatsapp_handoff`, `funnel_summary`, and `build_health`. Store the approved structured request and shown price, but never a name, phone number, identity document, WhatsApp message body, or free-form lost reason.
- [ ] **Step 4: Re-run** all three modules and inspect the SQLite rows in a temporary database to prove message content and personal fields are absent.
- [ ] **Step 5: Commit** `feat(monthly): connect leads to outcomes`.

## Task 6: Add stable APIs and bot adapters

**Files:**
- Create: `monthly_public/routes.py`
- Create: `tests/test_monthly_public_routes.py`
- Create: `tests/test_monthly_public_no_network.py`
- Modify: `bot.py` at the monthly import, source-adapter, background-loop, and route-registration boundaries only

- [ ] **Step 1: Write failing contract tests** for config, browse/search, match, listing, quote, lead creation, analytics event, operations health, team response, and outcome endpoints. Add provider spies that raise on any customer-request call. Add source tests that limit `bot.py` monthly-public edits to adapters and route registration.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_monthly_public_routes tests.test_monthly_public_no_network -v` and confirm endpoint/adapter failures.
- [ ] **Step 3: Implement** `MonthlyPublicApp` handlers and bot adapters. Keep `/monthly`, `/monthly/search`, `/monthly/id/{id}`, `/monthly/{slug}`, and the existing `/api/monthly/*` entry points. Add `/api/monthly/match`, `/api/monthly/lead`, `/api/monthly/event`, and authenticated `/api/monthly/ops/*`. Run source refresh in the background and supply only in-memory snapshots to public handlers.
- [ ] **Step 4: Re-run** contract/no-network tests plus the existing monthly wiring, calendar, switch, and nonblocking suites.
- [ ] **Step 5: Commit** `refactor(monthly): isolate public request path`.

## Task 7: Build the Arabic-first customer experience

**Files:**
- Create: `monthly_public/page.py`
- Create: `monthly_public/static/monthly.css`
- Create: `monthly_public/static/monthly.js`
- Create: `tests/test_monthly_public_page.py`
- Create: `tests/test_monthly_public_content.py`
- Modify: `bot.py` only to bind the new page/static handlers and rollback switch

- [ ] **Step 1: Write failing source and DOM tests** for the approved hero copy, both entry actions, one-question screens, automatic progression, purpose branches, back-state retention, dates/flexibility, top-three/alternatives/catalog headings, browse filters, listing content order, price terms, four-to-six-month sentence, Arabic/English dictionaries, live regions, focus states, 44-pixel targets, reduced motion, responsive image attributes, lazy loading, and blocked/empty/error states. Reject discount phrases, crossed prices, blank detail-image alt text, Google Fonts, mixed-language amenity fallback, duplicate description rendering, placeholder values, and hard-coded property counts.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_monthly_public_page tests.test_monthly_public_content -v` and confirm missing asset/page failures.
- [ ] **Step 3: Implement** the semantic HTML shell, locally hosted fonts, quiet Riyadh luxury tokens, client state machine, API rendering, locale switch, focus management, nonblocking analytics, and prepared WhatsApp action. The browser creates the lead before opening `wa.me`; it never sends the message itself.
- [ ] **Step 4: Parse every inline/module script, run the page/content tests, and confirm the legacy public monthly UI no longer receives traffic when the feature switch is enabled.
- [ ] **Step 5: Commit** `feat(monthly): build guided luxury journey`.

## Task 8: Build the staff operations view and real-data preview

**Files:**
- Extend: `monthly_public/page.py`
- Extend: `monthly_public/static/monthly.css`
- Extend: `monthly_public/static/monthly.js`
- Create: `monthly_public/preview.py`
- Create: `tests/test_monthly_public_ops_page.py`
- Create: `tests/test_monthly_public_preview.py`

- [ ] **Step 1: Write failing tests** for received/valid/blocked/published counts, exact missing calendar and price IDs, refresh timestamps, WhatsApp/hours state, content conflicts, licence expiry, long-stay readiness, red launch blockers, funnel conversion, response time, outcomes, and staff-only blocked-home preview.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_monthly_public_ops_page tests.test_monthly_public_preview -v` and confirm failures.
- [ ] **Step 3: Implement** the authenticated operations screen and preview server. The preview importer allowlists only public listing IDs, titles, area/neighbourhood, facts, rating/count, public image URLs, structured content, and dated official quote fields. It drops descriptions that fail language validation and every credential/operational field. Missing licences and terms stay visibly blocked in staff preview.
- [ ] **Step 4: Re-run** tests and inspect the preview export keys to prove that Wi-Fi, access, guest, and operational fields cannot enter the snapshot.
- [ ] **Step 5: Commit** `feat(monthly): expose launch health`.

## Task 9: Verify journeys, accessibility, visuals, and performance

**Files:**
- Create: `docs/monthly-launch-readiness-2026-08-25.md`
- Create: `artifacts/monthly-qa/` screenshots and machine-readable QA summaries, ignored where generated
- Modify: customer or operations files only for reproduced defects

- [ ] **Step 1: Run** all new unit/contract/integration tests, existing monthly tests, full repository tests, Python compilation/static checks, JavaScript parsing, and source/content scans. Record exact passed, failed, and environment-blocked counts.
- [ ] **Step 2: Launch** the local staff preview with the allowlisted real Ouja public catalog. Run Arabic and English journeys on mobile and desktop for work/relocation, flexible family, treatment/hospital, visit/venue, full browse, four-to-six months, stale calendar, missing price, missing WhatsApp, outside hours, and back/changed answers.
- [ ] **Step 3: Inspect** screenshots for clipping, spacing, RTL/LTR, source image quality, loading/error states, focus, sticky actions, and empty states. Measure response timing from prepared data and confirm analytics cannot delay navigation. Add a failing regression test before each reproducible correction.
- [ ] **Step 4: Review** the final diff against every acceptance criterion, run the security/privacy scan, and obtain an independent code review. Fix all confirmed high- or medium-risk defects, then repeat the relevant verification.
- [ ] **Step 5: Write** the launch-readiness report with passed checks, exact live-data gaps, external business/configuration blockers, preview location, launch recommendation, and rollback steps.
- [ ] **Step 6: Commit** `docs(monthly): report launch readiness` after fresh verification.

## Rollback design

`MONTHLY_PUBLIC_V2=0` keeps the existing public route adapters available locally while the new version is reviewed. A rollback changes the route binding only; it does not delete leads, outcomes, analytics, snapshots, or the old page. No deployment, production configuration change, customer message, or live-data write belongs to this plan.

## Final self-review

- The nine tasks cover all sixteen sections and twelve acceptance criteria in the approved specification.
- Customer behavior that depends on missing business values remains explicitly blocked: WhatsApp number, working hours, commercial terms, licence import, and the four-to-six-month contract route.
- Public handlers depend only on `SnapshotStore.current`, `LeadStore`, and best-effort local analytics. No handler receives a Hostaway or pricing-provider client.
- Price and listing responses have one naming scheme across pricing, matching, presentation, leads, and routes.
- Every implementation step has a named behavior, file, proof, and commit boundary. The plan contains no fake listing, fake availability, or production action.
