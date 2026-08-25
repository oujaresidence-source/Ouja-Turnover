# Monthly Priority Places Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import 25 approved priority destinations once, show each apartment's nearest five verified destinations, and make the apartment readiness screen explain the exact invalid field consistently.

**Architecture:** A focused `priority_places` module owns the versioned seed contract, coordinate math, and nearest-place projection. `CatalogStore` applies the seed atomically and idempotently, while `CatalogService` exposes staff-safe destination evidence and nearest-five data through existing operations APIs. The existing catalog page renders the new data and calculates local readiness from the current form so it cannot disagree with the displayed blocker list.

**Tech Stack:** Python 3.9, SQLite, aiohttp route adapters, vanilla JavaScript, CSS, `unittest`, and the existing monthly snapshot/publication contracts.

---

### Task 1: Add the vetted priority-place dataset and contract

**Files:**
- Create: `monthly_public/data/priority_places_2026_08_25.json`
- Create: `monthly_public/priority_places.py`
- Create: `tests/test_monthly_priority_places.py`
- Modify: `monthly_public/catalog_profiles.py`

- [ ] **Step 1: Write the failing dataset tests**

Add tests that import `PRIORITY_PLACE_MIGRATION_ID`, `load_priority_places`, and `nearest_places`. Assert that loading returns exactly 25 unique rows, no ID begins with `edu_`, the category counts are five each, all coordinates are within the Riyadh bounds, all evidence URLs are HTTPS, and purposes equal the approved mappings:

```python
def test_vetted_dataset_contains_only_the_approved_25_places(self):
    rows = load_priority_places()
    self.assertEqual(len(rows), 25)
    self.assertFalse(any(row["id"].startswith("edu_") for row in rows))
    self.assertEqual(
        Counter(row["category_id"] for row in rows),
        Counter({"business_hubs": 5, "hospitals": 5, "family_retail": 5,
                 "riyadh_season": 5, "events": 5}),
    )
```

Add a parser test proving staff metadata is accepted but unknown keys still fail:

```python
place = parse_place({
    "label_ar": "كافد", "label_en": "KAFD", "purposes": ["work"],
    "coordinates": {"lat": 24.7656964, "lng": 46.6407087,
                    "source": "priority_places_2026_08_25", "verified": True},
    "source_note": "موقع رسمي + OpenStreetMap",
    "category_id": "business_hubs", "category_ar": "مراكز الأعمال والتوظيف",
    "category_en": "Business & employment hubs", "priority": 1,
    "address_ar": "العقيق، الرياض", "address_en": "Al Aqiq, Riyadh",
    "district_ar": "العقيق", "district_en": "Al Aqiq",
    "map_url": "https://www.google.com/maps/search/?api=1&query=24.7656964%2C46.6407087",
    "official_source_url": "https://www.kafd.sa/en/faq/",
    "coordinate_source_url": "https://www.openstreetmap.org/way/1220645868",
    "verified_at": "2026-08-25", "review_interval_ar": "سنوي",
    "reason_ar": "مركز أعمال رئيسي.", "operations_note_ar": "نقطة مركزية موثقة.",
})
self.assertEqual(place["category_id"], "business_hubs")
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_priority_places tests.test_monthly_catalog_profiles`

Expected: import failure for `monthly_public.priority_places` and contract rejection for metadata fields.

- [ ] **Step 3: Add the immutable JSON source and focused loader**

Extract workbook rows `الوجهات!A6:V35` and join `المصادر!A6:H35` by `place_id`. Exclude the five `universities` rows. Store only the 25 approved rows with the exact workbook names, coordinates, addresses, evidence URLs, review dates, reasons, and notes. Map purposes by category as specified in the design.

Implement these public functions:

```python
PRIORITY_PLACE_MIGRATION_ID = "priority_places_2026_08_25_v1"

def load_priority_places() -> list[dict[str, Any]]:
    """Return fresh validated canonical place records from the package JSON."""

def distance_km(origin: Mapping[str, Any], destination: Mapping[str, Any]) -> Optional[float]:
    """Return Haversine distance only for verified coordinate pairs."""

def nearest_places(coordinates: Any, places: Mapping[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    """Return stable staff-safe nearest destinations ordered by distance and priority."""
```

`nearest_places` must return `id`, bilingual labels and categories, `distance_km` rounded to one decimal, priority, map URL, coordinate-source URL, verification date, and review cadence. It must return `[]` for unverified apartment coordinates.

- [ ] **Step 4: Extend `parse_place` with strict metadata validation**

Accept only the metadata fields listed in the design. Validate safe category IDs, priority 1–100, bilingual labels, HTTPS URLs, ISO verification date, and maximum lengths. Preserve the existing public fields and Riyadh coordinate validation.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_priority_places tests.test_monthly_catalog_profiles`

Expected: all tests pass and the dataset count is exactly 25.

- [ ] **Step 6: Commit**

```bash
git add monthly_public/data/priority_places_2026_08_25.json monthly_public/priority_places.py monthly_public/catalog_profiles.py tests/test_monthly_priority_places.py tests/test_monthly_catalog_profiles.py
git commit -m "feat(monthly): add priority place data"
```

### Task 2: Apply the dataset once and preserve staff changes

**Files:**
- Modify: `monthly_public/catalog_store.py`
- Modify: `tests/test_monthly_catalog_store.py`

- [ ] **Step 1: Write failing migration tests**

Cover one atomic method:

```python
result = store.seed_approved_places_once(
    "priority_places_2026_08_25_v1", places, "system:priority_places"
)
self.assertEqual(result["imported"], 25)
self.assertEqual(result["skipped_existing"], 0)
self.assertTrue(all(row["active"] for row in store.places().values()))
```

Add tests proving a second call returns `already_applied=True` without new revisions, an existing staff-edited place is skipped unchanged, and an invalid record rolls back all writes and does not record the migration.

- [ ] **Step 2: Run the store tests and verify RED**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_catalog_store`

Expected: `CatalogStore` has no `seed_approved_places_once` method.

- [ ] **Step 3: Add migration persistence and atomic insertion**

Add this table in `_initialize`:

```sql
CREATE TABLE IF NOT EXISTS monthly_catalog_migrations (
    migration_id TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    applied_by TEXT NOT NULL
);
```

Implement `seed_approved_places_once(migration_id, places, actor)`. Validate and JSON-encode every row before entering `_write()`. Inside one transaction, return the stored result if the migration exists; otherwise insert only missing `place_id` rows with draft and approved revision 1, `active=1`, and matching audit entries. Insert the migration result last. Do not update existing rows.

- [ ] **Step 4: Run the store tests and verify GREEN**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_catalog_store`

Expected: all tests pass, including rollback and restart idempotency.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/catalog_store.py tests/test_monthly_catalog_store.py
git commit -m "feat(monthly): seed approved places once"
```

### Task 3: Wire the migration, nearest five, and health reporting

**Files:**
- Modify: `monthly_public/catalog_service.py`
- Modify: `bot.py`
- Modify: `tests/test_monthly_catalog_service.py`
- Modify: `tests/test_monthly_catalog_integration.py`
- Modify: `tests/test_monthly_public_ops_workflow.py`

- [ ] **Step 1: Write failing service and integration tests**

Add service tests proving:

```python
result = service.seed_priority_places()
self.assertEqual(result["imported"], 25)
listing = service.listing("101")
self.assertEqual(len(listing["nearest_places"]), 5)
self.assertEqual(
    [row["distance_km"] for row in listing["nearest_places"]],
    sorted(row["distance_km"] for row in listing["nearest_places"]),
)
```

Add cases for unverified apartment coordinates (`nearest_places == []`), fewer than five eligible destinations, and health counts for five categories plus apartments with and without verified coordinates. Add a bot integration assertion that seeding occurs after the service is constructed and before public configuration replacement.

- [ ] **Step 2: Run and verify RED**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_catalog_service tests.test_monthly_catalog_integration tests.test_monthly_public_ops_workflow`

Expected: missing seed and nearest-place members.

- [ ] **Step 3: Implement service orchestration**

Add `CatalogService.seed_priority_places()` to parse all loaded rows before calling the store migration. Cache only the migration result, not computed distances. In `listing`, compute nearest places from the effective prefill coordinates and `approved_places()`. In `places`, add grouped category counts without changing the existing `places` or `active` keys. In `health`, expose migration state, category counts, and verified/missing apartment-coordinate counts.

In `bot.py`, call the seed once immediately after `_MonthlyCatalogService(...)` succeeds. A seed error must log one concise launch blocker, leave existing places untouched, and keep the service available for staff repair. Then run the existing public configuration refresh path.

- [ ] **Step 4: Run and verify GREEN**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_catalog_service tests.test_monthly_catalog_integration tests.test_monthly_public_ops_workflow`

Expected: all tests pass and existing approved-place/public snapshot tests remain unchanged.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/catalog_service.py bot.py tests/test_monthly_catalog_service.py tests/test_monthly_catalog_integration.py tests/test_monthly_public_ops_workflow.py
git commit -m "feat(monthly): connect apartment proximity"
```

### Task 4: Repair the contradictory readiness screen

**Files:**
- Modify: `monthly_public/static/monthly_catalog.js`
- Modify: `tests/test_monthly_catalog_page.py`
- Modify: `tests/test_monthly_catalog_profiles.py`

- [ ] **Step 1: Write failing regression tests for the screenshot**

Add page-script assertions for a pure `profileReadiness(profile)` function that returns both `percent` and translated blocker codes from current form values. Add assertions that `surveyError` reads `issue.field`, resolves its visible label, and focuses the matching control. Verify all blocker codes have Arabic and English copy.

Add profile tests proving the API error retains `field="name_ar"` and `code="language_mismatch"` for an English Arabic-title value.

- [ ] **Step 2: Run and verify RED**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_catalog_page tests.test_monthly_catalog_profiles`

Expected: missing `profileReadiness`, missing field focus, and untranslated blocker-copy assertions.

- [ ] **Step 3: Make current form state the single displayed readiness source**

Replace `completionPercent` with `profileReadiness`. Mirror the server's 13 readiness checks and add non-counted language validity warnings using Arabic/Latin character tests. `renderApproval` and `updateCompletion` must both use the same returned object. Render blocker labels through bilingual copy; do not display internal codes.

Update `surveyError` to show `«<field label>»: <message>` when the API includes an issue field, switch to the containing survey step, focus the control, and add `aria-invalid=true`. Keep the generic summary only when the field cannot be resolved.

- [ ] **Step 4: Run and verify GREEN**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_catalog_page tests.test_monthly_catalog_profiles`

Expected: all tests pass and the screenshot scenario identifies the exact language field without showing stale blockers.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/static/monthly_catalog.js tests/test_monthly_catalog_page.py tests/test_monthly_catalog_profiles.py
git commit -m "fix(monthly): align readiness feedback"
```

### Task 5: Render the destination summary and nearest-five panel

**Files:**
- Modify: `monthly_public/catalog_page.py`
- Modify: `monthly_public/static/monthly_catalog.js`
- Modify: `monthly_public/static/monthly_catalog.css`
- Modify: `tests/test_monthly_catalog_page.py`

- [ ] **Step 1: Write failing UI contract tests**

Assert the page includes an accessible `places-summary` live region. Assert the script renders category, review cadence, verification date, distance text, map/source links, and a no-apartment-pin empty state. Assert external links use `target="_blank"` with `rel="noopener noreferrer"`.

- [ ] **Step 2: Run and verify RED**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_catalog_page`

Expected: missing summary and nearest-place UI contracts.

- [ ] **Step 3: Implement the Arabic-first interface**

Add a compact category summary above the places list. Extend place rows with category, verification date, and review cadence. In `renderLocation`, add five quiet-luxury cards after the apartment coordinate field. Each card shows bilingual destination/category, one-decimal straight-line kilometres, and staff evidence links. Render a clear prompt to verify the apartment pin when `nearest_places` is empty because coordinates are unavailable.

Add responsive styles using the existing cream/gold/green tokens, 44px touch targets, RTL/LTR-safe alignment, and no new status colors. Increment the catalog asset version.

- [ ] **Step 4: Run and verify GREEN**

Run: `env PYTHONPATH=. python3 -m unittest tests.test_monthly_catalog_page`

Expected: all page, accessibility, asset-route, and size-gate tests pass.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/catalog_page.py monthly_public/static/monthly_catalog.js monthly_public/static/monthly_catalog.css tests/test_monthly_catalog_page.py
git commit -m "feat(monthly): show nearest five places"
```

### Task 6: Verify the customer and operations journeys

**Files:**
- Modify: `docs/monthly-launch-readiness-2026-08-25.md`
- Test: `tests/test_monthly_priority_places.py`
- Test: `tests/test_monthly_catalog_store.py`
- Test: `tests/test_monthly_catalog_service.py`
- Test: `tests/test_monthly_catalog_page.py`
- Test: `tests/test_monthly_public_no_network.py`

- [ ] **Step 1: Run focused feature tests**

Run:

```bash
env PYTHONPATH=. python3 -m unittest \
  tests.test_monthly_priority_places \
  tests.test_monthly_catalog_store \
  tests.test_monthly_catalog_profiles \
  tests.test_monthly_catalog_service \
  tests.test_monthly_catalog_integration \
  tests.test_monthly_catalog_page \
  tests.test_monthly_public_ops_workflow
```

Expected: all pass.

- [ ] **Step 2: Run the public journey suite**

Run: `env PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_monthly_public_*.py'`

Expected: all pass, including no-network customer-path tests.

- [ ] **Step 3: Run static and content checks**

Run Python compilation with `PYTHONPYCACHEPREFIX=/private/tmp/ouja-priority-pyc`, pyflakes on `monthly_public`, JavaScript syntax checks, `git diff --check`, discount-language scans, and provider-call scans. Expected: no product errors or forbidden content.

- [ ] **Step 4: Render Arabic and English desktop/mobile journeys**

Start a local authenticated QA preview from the isolated worktree. Inspect the places summary, one apartment with a verified pin, one without a pin, exact field-error focus, RTL/LTR layout, mobile sticky actions, spacing, clipping, and evidence-link safety. Fix only reproducible defects and rerun relevant tests.

- [ ] **Step 5: Update the readiness report**

Record the 25 imported destinations, five excluded universities, exact test counts, visual evidence, and any remaining production blockers. Do not call the live migration complete until the deployed health response confirms the migration version.

- [ ] **Step 6: Commit**

```bash
git add docs/monthly-launch-readiness-2026-08-25.md
git commit -m "docs(monthly): report place readiness"
```
