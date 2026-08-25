# Ouja Monthly Listing Readiness and Survey

**Date:** 25 August 2026

**Status:** Approved design

**Audience:** Ouja operations, content, pricing, and engineering

## Decision

Ouja will add an Arabic-first internal listing-readiness page for the monthly product. The page will prefill each apartment from existing trusted sources, let the team review and complete missing fields, and require an explicit approval before customer-facing data changes.

The page will not replace Monthly Lab. Monthly Lab remains the source for verified monthly prices and cached calendar coverage. The new page will connect those system facts with content, advertising details, commercial terms, and approved locations in one workflow.

## Problem and evidence

The public monthly interface can render the approved customer journey, but the publication snapshot has no complete source to publish:

- `bot.py::_monthly_public_refresh_snapshot()` exists but no startup, background, or save workflow calls it.
- `bot.py::_monthly_public_source_adapter()` reads required values from several independent stores.
- Titles, structured content, neighborhoods, and owner-declared facts live in `guest_overrides.json`.
- Advertising licence details live in the internal monthly database.
- Utilities and cleaning rules come from `MONTHLY_COMMERCIAL_TERMS` JSON.
- Approved destinations come from `MONTHLY_APPROVED_PLACES` JSON.
- Prices and calendars come from background monthly caches.
- `/monthly/ops` reports the blockers but gives the team no way to resolve listing data.

This split produces a functioning interface with an empty or heavily blocked catalog. Staff cannot see one apartment's full readiness or approve a complete record from one place.

## Goals

1. Give Ouja one page that shows every real apartment and its publication status.
2. Prefill trusted data so staff review instead of retyping.
3. Keep drafts away from customers until a staff member approves them.
4. Rebuild the last-known-good snapshot after approval and scheduled source refreshes.
5. Let staff maintain approved destinations and calculate proximity from verified coordinates.
6. Show the field, source, blocker, and next action for every missing requirement.
7. Keep public requests independent from Hostaway, the pricing provider, maps, and other external services.

## Non-goals

- The page will not push prices or apartment data to Hostaway.
- The page will not replace Monthly Lab pricing controls.
- The page will not generate customer claims from raw descriptions.
- The page will not publish exact apartment coordinates.
- The page will not display travel times from estimated road speeds.
- The page will not import Wi-Fi passwords, building codes, door instructions, staff phone numbers, or guide notes.
- The first release will not add bulk approval for apartment content.

## Considered approaches

### 1. Dedicated monthly readiness page

This approach gives the team one apartment workflow, keeps public-monthly data separate from `/stay`, and preserves Monthly Lab as the pricing source. It adds a focused persistent store and a small set of authenticated routes.

**Decision:** Use this approach.

### 2. Extend Monthly Lab

This approach reuses an existing page but mixes pricing decisions with bilingual content, advertising details, and location approval. The resulting page would become harder to scan and risk price actions while staff edit content.

### 3. Use a spreadsheet

A spreadsheet would reduce initial interface work. It would also weaken field validation, approval history, access control, and immediate publication feedback. Staff would need an import step before customers see changes.

## Users and access

- Administrators and monthly-operations roles can open the page.
- The page reuses the existing dashboard session and monthly-operations authorization.
- Unauthorized requests return the existing bilingual 401 or 403 experience.
- Staff can save drafts without changing the public catalog.
- Staff must use the final `اعتماد وتحديث الموقع` action to change approved monthly data.
- The audit log records the authenticated actor, action, listing ID, revision, changed field names, and timestamp. It does not store discarded field values or customer information.

## Routes and navigation

- Add `بيانات الشقق` to `/monthly/ops`.
- Serve the listing index and survey at `/monthly/ops/listings`.
- Preserve `/monthly/ops` for launch health, funnel reporting, and lead outcomes.
- Link price blockers to the matching apartment in Monthly Lab.
- Link licence, content, and terms blockers to the relevant survey section.

## Page structure

### Portfolio index

The index shows one row per received listing. Public counts continue to come from eligible inventory.

Each row shows:

- real listing ID and current source title;
- first approved public image;
- neighborhood and bedroom count;
- completion percentage based on required review fields;
- status: `تحتاج مراجعة`, `جاهزة للاعتماد`, `منشورة`, or `محجوبة من مصدر حي`;
- compact blocker summary;
- last draft save and last approval time;
- `مراجعة الشقة` action.

Staff can search by listing ID or title and filter by status, neighborhood, missing licence, missing price, missing calendar, or missing content. The page never duplicates a listing to represent Arabic and English versions.

### Global setup

The page puts shared values above the apartment list because staff should enter them once:

- Ouja WhatsApp number in international digits;
- working days, opening time, closing time, and Riyadh timezone;
- internet and maintenance inclusion;
- deposit amount and Arabic and English refund terms;
- approved payment methods;
- approved four-to-six-month review route.

The page stores global changes as a draft and validates both languages. An explicit approval updates the monthly settings used by new snapshots. `MONTHLY_SESSION_SECRET` remains an environment secret and stays outside the editor.

### Apartment survey

The survey handles one apartment at a time. A desktop view uses an apartment summary beside the active section. Mobile uses a single column. `التالي` saves the current section as a draft. The sticky footer shows `حفظ المسودة`, `معاينة الجاهزية`, and `اعتماد وتحديث الموقع`.

#### Section 1: Identity

- Arabic public title;
- English public title;
- visible for monthly stays;
- bedroom count displayed beside each title to catch conflicts;
- source and last-updated label for every prefilled value.

The page prefills titles from approved `/stay` overrides. It shows the Hostaway name as a reference and never publishes it as Arabic content.

#### Section 2: Space and verified facts

- bedrooms, sleeping beds, bathrooms, resident capacity, and floor area;
- owner-declared facts such as parking, elevator, workspace, kitchen, washer, private entrance, compound, accessibility, balcony, and pool;
- three states for each declared fact: yes, no, or unanswered.

Hostaway supplies room, bathroom, capacity, image, and amenity facts. Staff approval controls facts that Hostaway does not verify well enough for a customer claim.

#### Section 3: Location and nearby places

- approved Riyadh neighborhood;
- listing coordinate source and verification state;
- a map-pin field that accepts a coordinate pair or a full maps URL containing coordinates;
- nearby approved destinations calculated after validation;
- a warning when the system has only a guide match or a neighborhood centroid.

Valid Hostaway coordinates prefill as a verified source because they belong to the same listing ID and pass the Riyadh bounds check. Guide-derived coordinates prefill as `تحتاج مراجعة` when the guide match uses a title rather than the listing ID. Neighborhood centroids help staff orient themselves and never support a public proximity claim.

The customer API receives a distance label only when both the apartment and destination have approved coordinates. It returns straight-line kilometers with the source label. It does not return latitude, longitude, an estimated driving time, or a route promise.

#### Section 4: Arabic and English presentation

- short Arabic summary;
- short English summary;
- structured Arabic and English sections reused from `/stay`;
- grouped amenity preview after the approved translation map removes unknown values;
- customer image preview using the real connected public image URLs;
- content approval checkbox.

The page shows English and Arabic side by side on desktop and in separate tabs on mobile. Staff can edit imported text before approval. The server rejects mixed-language titles, missing language coverage, duplicate sections, unsupported fields, and raw descriptions presented as approved content.

#### Section 5: Monthly terms

- electricity and water mode: included, variable, or excluded;
- Arabic and English utility label;
- cleaning mode: included, optional, or unavailable;
- optional-cleaning amount when applicable;
- Arabic and English cleaning label;
- read-only preview of the global deposit, included services, and payment methods.

The apartment profile stores only per-listing exceptions. The approved global setup supplies internet, maintenance, deposit, payment, and long-stay review values.

#### Section 6: Advertising and source readiness

- advertising licence number and expiry date;
- image count and first three image previews;
- verified rating and review count when present;
- official monthly price coverage from Monthly Lab;
- calendar coverage, freshness, and missing unit state;
- a link to Monthly Lab when price coverage is missing.

Staff can edit licence details here. Price and calendar fields remain read-only because background systems own them. The page does not create a price, availability date, rating, or review count.

#### Section 7: Review and approval

The review screen groups findings into:

- staff fields ready for approval;
- staff fields that need an answer;
- background data that blocks publication;
- warnings that remove a claim but do not block the apartment.

Each error links to its field. The approval action requires a valid staff-controlled draft revision and an authenticated actor. Staff can approve their fields while price or calendar coverage remains blocked. The approved profile stays out of the public catalog until the background blockers clear. The API rejects stale revision numbers so one employee cannot overwrite another employee's newer review.

## Approved destinations

The global setup includes a destination catalog for work, treatment, family, and visit journeys. Each destination has:

- stable ID;
- Arabic and English label;
- purpose categories;
- verified coordinates;
- source note;
- active or inactive state;
- approval actor and time.

Staff enter one destination once. The matcher calculates its distance to all approved apartment coordinates. Removing a destination prevents new customer selection but keeps historical lead references readable.

## Prefill sources and precedence

The survey reads available values in this order and displays the source beside the field:

1. Current monthly draft.
2. Current approved monthly profile.
3. Approved `/stay` override for bilingual titles, structured content, neighborhood, and declared facts.
4. Hostaway listing cache for identity, rooms, capacity, coordinates, images, and amenities.
5. Monthly database for advertising licences.
6. Approved public review store for rating and review count.
7. Monthly Lab engine and calendar caches for price and availability coverage.

The server stores approved monthly fields separately from `/stay`. An approval changes the monthly product and does not rewrite `/stay`, Hostaway, guide content, or Monthly Lab. Existing environment values prefill global settings until staff approve a stored global record. The monthly profile copies an approved licence record so later Monthly Lab licence changes appear as a reviewable source change instead of changing the public apartment without approval.

## Persistence model

Create `monthly_catalog.sqlite3` under `STATE_DIR` with four append-safe areas:

### `monthly_catalog_profiles`

- `listing_id` primary key;
- `draft_json` and `approved_json`;
- `draft_revision` and `approved_revision`;
- `draft_updated_at`, `draft_updated_by`, `approved_at`, and `approved_by`.

### `monthly_catalog_settings`

- singleton draft and approved global settings;
- revision, actor, and timestamps.

### `monthly_catalog_places`

- stable place ID;
- draft and approved place records;
- revision, active state, actor, and timestamps.

### `monthly_catalog_audit`

- append-only action record;
- listing or global target;
- revision and changed field names;
- actor and timestamp.

SQLite uses short connections, rollback journaling, explicit transactions, and the existing `STATE_DIR` persistence rules. It does not use WAL on the Railway volume.

## API contracts

Authenticated operations routes:

- `GET /api/monthly/ops/listings`: portfolio rows, counts, filters, and source timestamps.
- `GET /api/monthly/ops/listing/{id}`: prefill, draft, approved profile, blockers, and revision.
- `POST /api/monthly/ops/listing/{id}/draft`: validate and save listed draft fields.
- `POST /api/monthly/ops/listing/{id}/approve`: approve the current revision and request a snapshot rebuild.
- `GET /api/monthly/ops/settings`: global draft, approved values, and blockers.
- `POST /api/monthly/ops/settings/draft`: save validated global draft fields.
- `POST /api/monthly/ops/settings/approve`: approve global settings and request a snapshot rebuild.
- `GET /api/monthly/ops/places`: approved and draft destination catalog.
- `POST /api/monthly/ops/places/draft`: save a destination draft.
- `POST /api/monthly/ops/places/approve`: approve, deactivate, or reactivate a destination.
- `POST /api/monthly/ops/refresh`: rebuild from cached sources and return the accepted generation summary.

All write contracts reject unknown fields, invalid coordinates, malformed currency values, stale revisions, unapproved listing IDs, and oversized text. Responses return stable bilingual error codes. No route accepts customer message content or a provider credential.

## Snapshot data flow

1. Background importers refresh the Hostaway listing cache, monthly price engine, and calendar cache.
2. The survey service reads those caches and approved monthly records without external calls.
3. Staff save a draft. Customers keep reading the current approved snapshot.
4. Staff approve all valid staff-controlled fields. Background blockers may remain visible.
5. The service builds one full source set and runs every publication validator.
6. The snapshot store atomically accepts a valid generation.
7. Customer catalog, matcher, listing page, quote, and WhatsApp handoff read that generation.

The system also requests a rebuild:

- after application startup, once required caches finish loading;
- after a successful listing, calendar, price, review, or licence background refresh;
- after staff approve global settings, a place, or an apartment;
- from the authenticated manual refresh action.

A failed rebuild records the error and keeps the last-known-good snapshot. Customer requests do not wait for a rebuild or call a provider.

## Publication behavior

- A draft never reaches the public site.
- An approved apartment appears only when publication validation passes.
- Missing or stale calendar data removes exact-match eligibility and displays the approved pending state.
- Missing official price, advertising details, bilingual content, required images, neighborhood, or commercial terms blocks the apartment.
- Unverified ratings, coordinates, and amenities remove those claims without inventing replacements.
- Public counts use the approved eligible catalog.
- Matcher ranking uses verified fit, calendar coverage, and approved proximity. Price does not receive a revenue-weighted ranking boost.

## Error handling

- A missing snapshot shows the existing customer-safe unavailable state and a red operations blocker.
- A stale draft approval returns `revision_conflict` and reloads the newer draft.
- A storage failure returns a retryable operations error and leaves approved data unchanged.
- A source refresh failure keeps the last-known-good generation.
- A broken image stays out of the approved image list. The apartment blocks when fewer than three valid public images remain.
- An invalid or expired licence blocks publication.
- Missing price links staff to Monthly Lab.
- Missing calendar coverage identifies the listing ID and waits for the next background refresh.
- Missing WhatsApp or session secret leaves lead creation blocked while browsing remains customer-safe.

## Security and privacy

- Dashboard authentication protects every editor and write route.
- The public API never exposes draft data, exact coordinates, actor names, or internal source notes.
- The prefill layer uses an allowlist. It excludes Wi-Fi values, access codes, guide notes, staff contacts, owner contacts, and internal operations instructions.
- The database stores no guest personal data or WhatsApp message content.
- The service escapes all rendered content and validates URLs before previewing images.
- Staff actions do not call Hostaway or send customer messages.
- The implementation logs field names and record IDs, not secret or sensitive values.

## Interface standards

- Arabic loads first and the page provides an English switch.
- The page uses Ouja's existing light cream and gold operations theme and IBM Plex Sans Arabic.
- The interface uses at most four status colors and pairs color with text and an icon.
- Form controls have 44-pixel touch targets, visible focus, error summaries, and field-level messages.
- The editor supports keyboard navigation, RTL and LTR text entry, reduced motion, and mobile widths from 320 pixels.
- The page uses an apartment list and a focused editor instead of nested card grids.
- Staff can leave and return without losing a saved draft.

## Testing

### Unit tests

- source precedence and allowlisted prefill;
- exclusion of Wi-Fi, access codes, contacts, and guide notes;
- draft and approved revision rules;
- global defaults and per-listing exceptions;
- coordinate parsing, Riyadh bounds, and straight-line distance;
- destination activation and historical reference behavior;
- snapshot refresh triggers and last-known-good retention;
- publication blocker mapping.

### API contract tests

- authenticated read and write routes;
- role enforcement;
- unknown-field rejection;
- stale revision conflict;
- bilingual validation errors;
- listing ID and URL validation;
- no provider call during read, draft, approve, or public customer requests.

### Integration tests

- Hostaway and `/stay` prefill into a draft;
- save, reload, approve, rebuild, and public listing appearance;
- global settings approval updates quote and WhatsApp readiness;
- approved destination appears in the matcher and ranks verified nearby apartments;
- missing price, stale calendar, expired licence, and failed refresh behavior;
- approved data survives a process restart.

### Browser and visual tests

- Arabic and English portfolio index;
- desktop and mobile apartment survey;
- keyboard-only completion;
- long titles, empty content, server errors, and revision conflicts;
- sticky actions, clipping, image loading, focus order, contrast, and reduced motion;
- customer journey from matcher to an approved listing and prepared WhatsApp handoff.

## Acceptance criteria

- Staff can open every received apartment from one authenticated page.
- The page prefills trusted fields and labels their source.
- The page imports no sensitive guide or operations values.
- Staff can save drafts without changing the public site.
- An approved apartment appears in the catalog after its staff fields and background source checks pass and the snapshot store accepts the rebuild.
- An incomplete apartment stays blocked with field-level reasons.
- Approved places create evidence-based proximity reasons without exposing exact coordinates or travel times.
- Background price and calendar refreshes request a snapshot rebuild.
- A failed rebuild preserves the last-known-good customer catalog.
- The customer path makes no external provider call.
- Public inventory counts contain no duplicate language copies.
- Automated, accessibility, performance, and visual checks pass or name an external environment limitation.

## Rollout and rollback

The first deployment creates the internal store and page. It does not approve a profile, modify Hostaway, send a message, or publish a draft. Staff can review prefills and approve apartments in controlled batches.

`MONTHLY_CATALOG_ADMIN=0` disables the editor routes. `MONTHLY_PUBLIC_V2=0` restores the previous public monthly handlers. Both switches leave profiles, places, audit records, leads, outcomes, analytics, and snapshots intact.
