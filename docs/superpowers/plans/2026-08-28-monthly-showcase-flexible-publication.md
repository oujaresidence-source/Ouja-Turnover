# Monthly Showcase Flexible Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show selected homes on an approved public showcase when each has a valid advertising licence, one real image, and an approved monthly price, without inventing missing optional content.

**Architecture:** Keep the general catalog publication result strict. Add a showcase-only eligibility adapter that converts optional publication blockers to warnings after checking the approved three-item minimum. Present neutral localized titles when a title is missing or conflicts with verified room data, and expose gap counts only to staff.

**Tech Stack:** Python 3, immutable `PublicationResult` contracts, vanilla JavaScript, `unittest`/pytest.

---

### Task 1: Showcase-only eligibility gate

**Files:**
- Modify: `monthly_public/showcase_service.py`
- Test: `tests/test_monthly_showcase_service.py`

- [ ] **Step 1: Write failing minimum-gate tests**

Add tests that build a listing with missing descriptions, titles, room facts,
neighborhood, commercial terms, and calendar data. Give it one HTTPS image, a
valid licence, and an enabled per-listing showcase price. Assert that it appears
in `public_by_slug()`. Add separate assertions that no image, no valid licence,
or no manual/official price still excludes the home.

```python
public = service.public_by_slug("one-building", "ar")
self.assertEqual([row.listing["id"] for row in public["results"]], ["104"])
```

- [ ] **Step 2: Run the tests and verify the new case fails**

Run:
`python3 -m pytest -q tests/test_monthly_showcase_service.py`

Expected: the optional-content case fails because the strict snapshot blockers
still exclude the listing.

- [ ] **Step 3: Implement the showcase adapter**

Add a focused helper in `ShowcaseService` that:

```python
hard_codes = {
    "listing_id_missing", "inactive_listing", "licence_missing",
    "licence_expiry_missing", "licence_expiry_invalid", "licence_expired",
}
```

It must require at least one sanitized image and either `manual_rate(...)` or a
non-empty verified `official_prices` map. When those checks pass, move all other
blockers into warnings and return a publishable replacement result. Use this
helper only from showcase eligibility; do not change `publication.py` or the
general catalog.

- [ ] **Step 4: Run the service tests and verify they pass**

Run:
`python3 -m pytest -q tests/test_monthly_showcase_service.py`

Expected: all showcase service tests pass.

- [ ] **Step 5: Commit the eligibility change**

```bash
git add monthly_public/showcase_service.py tests/test_monthly_showcase_service.py
git commit -m "feat(monthly): relax showcase publication"
```

### Task 2: Safe incomplete-home presentation and staff status

**Files:**
- Modify: `monthly_public/showcase_service.py`
- Modify: `monthly_public/static/monthly_catalog.js`
- Test: `tests/test_monthly_showcase_service.py`
- Test: `tests/test_monthly_catalog_page.py`

- [ ] **Step 1: Write failing presentation and staff tests**

Assert that a relaxed Arabic home without an Arabic title is presented as
`شقة عوجا · <listing ID>`, the English equivalent is `Ouja home · <listing ID>`,
unsupported facts remain absent, and the staff group record reports the count of
eligible homes that still have optional gaps.

```python
self.assertEqual(ar_home["title"], "شقة عوجا · 104")
self.assertEqual(staff["eligible_with_gaps_count"], 1)
```

Assert that the staff JavaScript includes bilingual copy for “published with
missing details” and renders the count without exposing blocker details to the
public showcase payload.

- [ ] **Step 2: Run the tests and verify they fail for missing behavior**

Run:
`python3 -m pytest -q tests/test_monthly_showcase_service.py tests/test_monthly_catalog_page.py`

Expected: fallback-title and staff-gap assertions fail.

- [ ] **Step 3: Add safe fallback and gap reporting**

When a relaxed result has `arabic_title_missing`, `english_title_missing`, or
`title_bedroom_conflict`, replace only the unsafe localized title with the
neutral listing-ID label. Add `eligible_with_gaps_count` to authenticated staff
records and render it with Arabic and English labels in the showcase list.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:
`python3 -m pytest -q tests/test_monthly_showcase_service.py tests/test_monthly_catalog_page.py`

Expected: all focused tests pass.

- [ ] **Step 5: Commit the presentation change**

```bash
git add monthly_public/showcase_service.py monthly_public/static/monthly_catalog.js tests/test_monthly_showcase_service.py tests/test_monthly_catalog_page.py
git commit -m "feat(monthly): label showcase content gaps"
```

### Task 3: Regression, live verification, and release

**Files:**
- Modify only if a regression test exposes a defect.

- [ ] **Step 1: Run monthly regression tests**

Run the showcase, route, page, contract, no-network, catalog, accessibility, and
content-scan suites. Expected: zero failures.

- [ ] **Step 2: Run static checks**

Run JavaScript syntax checks, Python compilation, `pyflakes`, and
`git diff --check`. Expected: zero errors or warnings introduced by this change.

- [ ] **Step 3: Verify the public customer URL locally**

Open an approved showcase in Arabic and English. Confirm eligible incomplete
homes render with image, monthly price, neutral labels, pending-availability
copy, no raw missing values, and no console errors.

- [ ] **Step 4: Push once and verify Railway**

Push `main` once. Confirm `https://oujares.com/monthly/showcase/nuzha` serves the
new asset version and its public showcase API returns only homes that pass the
three-item minimum.

- [ ] **Step 5: Report any remaining minimum blockers**

If production still returns zero homes, report whether the selected homes lack
a valid advertising licence, one real image, or a manual/official monthly price.
Do not bypass or invent any of those values.
