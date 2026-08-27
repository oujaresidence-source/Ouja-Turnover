# Monthly Thmanyah Typography Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the supplied Thmanyah family across Ouja Monthly without changing apartment data or customer behavior.

**Architecture:** A focused `monthly_public/fonts.py` module owns the versioned font contract and allow-list. The existing monthly page modules link one shared font stylesheet, while `bot.py` serves that stylesheet and only the approved WOFF2 files. Customer pages pair Serif Display headings with Sans body text; staff tools use Sans throughout.

**Tech Stack:** Python/aiohttp route handlers, static HTML/CSS, WOFF2 assets, Python unittest.

---

### Task 1: Lock the font contract with failing tests

**Files:**
- Create: `tests/test_monthly_fonts.py`
- Modify: `tests/test_monthly_public_page.py`

- [ ] **Step 1: Write the failing contract tests**

Add assertions that the three page shells link the same fingerprinted font stylesheet, the public shell preloads the Sans Regular WOFF2 file, all copied assets begin with the `wOF2` signature, the font stylesheet declares `font-display: swap`, and the public/operations styles use the approved family roles.

- [ ] **Step 2: Run the tests and confirm the missing module/assets fail**

Run: `python -m unittest tests.test_monthly_fonts tests.test_monthly_public_page -v`

Expected: FAIL because `monthly_public.fonts`, page links, and font assets do not exist yet.

### Task 2: Add the immutable font asset boundary

**Files:**
- Create: `monthly_public/fonts.py`
- Create: `monthly_public/static/monthly_fonts.v20260827a.css`
- Create: `monthly_public/static/fonts/thmanyah-sans-{regular,medium,bold,black}.v20260827a.woff2`
- Create: `monthly_public/static/fonts/thmanyah-serif-display-{bold,black}.v20260827a.woff2`
- Modify: `monthly_public/page.py`
- Modify: `monthly_public/ops_page.py`
- Modify: `monthly_public/catalog_page.py`
- Modify: `bot.py`

- [ ] **Step 1: Copy only the required WOFF2 files from the supplied archive**

Validate every copied file begins with `wOF2` and keep the source ZIP unchanged.

- [ ] **Step 2: Define the versioned routes and allow-list**

Expose one shared CSS route, one critical preload route, and six filename-to-route mappings from `monthly_public/fonts.py`.

- [ ] **Step 3: Serve the shared CSS and WOFF2 files**

Register explicit GET routes while Monthly V2 is enabled. Return `font/woff2`, `Cache-Control: public, max-age=31536000, immutable`, and 404 for any path outside the allow-list.

- [ ] **Step 4: Link the shared font stylesheet from all three shells**

Place the font stylesheet before page-specific CSS and preload only Sans Regular on the public customer shell.

- [ ] **Step 5: Run the focused tests**

Run: `python -m unittest tests.test_monthly_fonts tests.test_monthly_public_page tests.test_monthly_public_ops_page tests.test_monthly_catalog_page -v`

Expected: PASS.

### Task 3: Apply the typography roles and preserve hierarchy

**Files:**
- Modify: `monthly_public/static/monthly.css`
- Modify: `monthly_public/static/monthly_ops.css`
- Modify: `monthly_public/static/monthly_catalog.css`
- Modify: `monthly_public/page.py`
- Modify: `monthly_public/ops_page.py`
- Modify: `monthly_public/catalog_page.py`

- [ ] **Step 1: Add semantic family tokens**

Use `--font-sans` and `--font-display` with complete local fallback stacks and kerning enabled.

- [ ] **Step 2: Apply the public pairing**

Use Thmanyah Sans for body text, controls, subtitles, navigation, prices, and metadata. Use Thmanyah Serif Display only for `h1`, `h2`, and `h3` on the customer site.

- [ ] **Step 3: Apply the operations family**

Use Thmanyah Sans for every role on `/monthly/ops` and `/monthly/ops/listings`; preserve the current weight declarations and layout dimensions.

- [ ] **Step 4: Bump all page-specific asset versions**

Update the three version constants so browsers cannot retain the old Apple/system-first CSS.

- [ ] **Step 5: Run focused tests again**

Run: `python -m unittest tests.test_monthly_fonts tests.test_monthly_public_content tests.test_monthly_public_ops_page tests.test_monthly_catalog_page -v`

Expected: PASS.

### Task 4: Verify, inspect, commit, and push

**Files:**
- Modify: `docs/monthly-launch-readiness.md` only if the existing report tracks this release.

- [ ] **Step 1: Run the complete monthly suite**

Run: `python -m unittest discover -s tests -p 'test_monthly*.py' -v`

Expected: all tests PASS with zero failures.

- [ ] **Step 2: Run syntax, content, and asset checks**

Run Python compilation, JavaScript syntax checks, the no-external-font scan, WOFF2 signature checks, and `git diff --check`.

Expected: zero errors, no third-party font URL, and no accidental apartment-data changes.

- [ ] **Step 3: Inspect rendered Arabic and English pages**

Check customer home, matcher, listing, operations, and listing-data pages at mobile and desktop sizes. Confirm no clipped Arabic, fallback font, layout shift, or broken bold hierarchy.

- [ ] **Step 4: Commit intentional files**

Stage only the typography assets, monthly code/tests, and this documentation. Do not stage `.superpowers/`, caches, screenshots, credentials, or data files.

- [ ] **Step 5: Push once**

Push `main` to its configured upstream and verify the remote commit and public asset responses.
