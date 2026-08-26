# Monthly Internal Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a staff-only customer-journey preview that displays every real monthly listing without publishing incomplete homes or mutating existing catalog data.

**Architecture:** A new preview builder converts trusted prefills and current drafts into an immutable, explicitly non-public preview generation. A preview request facade reuses the public presentation contracts but disables leads and labels missing evidence. Authenticated preview routes render the existing Arabic-first monthly shell with a preview banner and route all data calls to gated preview APIs.

**Tech Stack:** Python 3, aiohttp route handlers, SQLite-backed catalog reads, vanilla JavaScript, existing monthly CSS, `unittest`, Node syntax checks.

---

## File structure

- Create `monthly_public/preview.py`: build immutable preview generations and the read-only preview facade.
- Modify `monthly_public/catalog_service.py`: expose one read-only trusted preview inventory snapshot.
- Modify `monthly_public/page.py`: render authenticated preview page state and banner without embedding listing data or tokens.
- Modify `monthly_public/static/monthly.js`: switch endpoints and navigation when page state says preview, preserve the auth token only in URLs, and render preview labels.
- Modify `monthly_public/static/monthly.css`: add restrained preview banner and missing-data chip styles.
- Modify `monthly_public/catalog_page.py`: add the staff action that opens the customer preview.
- Modify `monthly_public/static/monthly_catalog.js`: preserve the dashboard token when opening preview.
- Modify `bot.py`: register gated preview pages and APIs.
- Create `tests/test_monthly_preview.py`: preview contracts, matching degradation, and data preservation.
- Modify `tests/test_monthly_public_page.py`, `tests/test_monthly_catalog_page.py`, and `tests/test_monthly_wiring.py`: shell, auth, route, and public-regression coverage.

### Task 1: Immutable preview generation

**Files:**
- Create: `tests/test_monthly_preview.py`
- Modify: `monthly_public/catalog_service.py`
- Create: `monthly_public/preview.py`

- [ ] **Step 1: Write the failing preservation and inventory tests**

```python
def test_preview_includes_incomplete_inventory_without_mutating_store(self):
    before = snapshot_store_records(store)
    generation = build_preview_generation(service.preview_inventory(), settings, NOW)
    self.assertEqual([row.listing["id"] for row in generation.published], ["101", "202"])
    self.assertIn("licence_missing", generation.published[0].listing["preview_missing"])
    self.assertEqual(snapshot_store_records(store), before)
```

- [ ] **Step 2: Run the new test and verify RED**

Run: `python3 -m unittest tests.test_monthly_preview -v`

Expected: failure because `preview_inventory` and `build_preview_generation` do not exist.

- [ ] **Step 3: Implement the minimal read-only preview builder**

`CatalogService.preview_inventory()` reads one source snapshot, merges trusted prefills with saved drafts, strips source annotations, and returns copied mappings only. `build_preview_generation()` calls the existing validator for sanitization, keeps all validation issues as `preview_missing`, supplies only neutral ID-based fallback labels, and marks the in-memory preview results visible without persisting them.

- [ ] **Step 4: Run preview tests and verify GREEN**

Run: `python3 -m unittest tests.test_monthly_preview -v`

Expected: all preview generation and preservation tests pass.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/catalog_service.py monthly_public/preview.py tests/test_monthly_preview.py
git commit -m "feat(monthly): build read-only preview inventory"
```

### Task 2: Preview customer contracts and approved temporary settings

**Files:**
- Modify: `monthly_public/preview.py`
- Modify: `tests/test_monthly_preview.py`

- [ ] **Step 1: Write failing facade tests**

```python
def test_preview_config_uses_daily_ten_to_ten_and_blocks_contact(self):
    config = app.config("ar")
    self.assertTrue(config["preview"])
    self.assertEqual(config["eligible_count"], 2)
    self.assertEqual(config["deposit_range_sar"], {"minimum": 500, "maximum": 2500})
    self.assertTrue(any(row["code"] == "whatsapp_missing" for row in config["blockers"]))

def test_preview_match_keeps_every_home_in_complete_catalog(self):
    result = app.match(valid_match_request(), "ar")
    self.assertEqual(len(result["catalog"]), 2)
    self.assertTrue(all(row["preview"] for row in result["catalog"]))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m unittest tests.test_monthly_preview.MonthlyPreviewAppTest -v`

Expected: failure because the preview facade is missing.

- [ ] **Step 3: Implement the read-only preview facade**

Use seven `10:00` to `22:00` intervals in `Asia/Riyadh`, keep WhatsApp and session issuance disabled, attach the SAR 500–2,500 indicative range, and return all preview cards in the complete catalog. Exact top recommendations remain restricted to homes whose verified capacity, price, and calendar satisfy the request. Missing evidence is rendered as a tradeoff, never a positive claim.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python3 -m unittest tests.test_monthly_preview -v`

Expected: all preview facade tests pass.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/preview.py tests/test_monthly_preview.py
git commit -m "feat(monthly): add internal preview contracts"
```

### Task 3: Authenticated preview routes

**Files:**
- Modify: `bot.py`
- Modify: `tests/test_monthly_wiring.py`

- [ ] **Step 1: Write failing route and authorization tests**

```python
def test_preview_api_requires_ops_auth(self):
    response = run(bot._api_monthly_preview_config(FakeRequest()))
    self.assertEqual(response.status, 401)

def test_preview_routes_are_registered_before_monthly_slug_catchall(self):
    self.assertIn("/monthly/ops/preview", registered_paths)
    self.assertIn("/api/monthly/ops/preview/search", registered_paths)
```

- [ ] **Step 2: Run route tests and verify RED**

Run: `python3 -m unittest tests.test_monthly_wiring -v`

Expected: failure because preview handlers and routes are absent.

- [ ] **Step 3: Implement gated page and API handlers**

Register home, matcher, browse, ID, and slug preview pages plus config, search, match, and listing APIs. Every handler calls `_monthly_catalog_gate`; no preview lead, event, save, approve, refresh, or provider endpoint is registered.

- [ ] **Step 4: Run route tests and verify GREEN**

Run: `python3 -m unittest tests.test_monthly_wiring -v`

Expected: preview routes pass auth and registration tests; existing public wiring remains green.

- [ ] **Step 5: Commit**

```bash
git add bot.py tests/test_monthly_wiring.py
git commit -m "feat(monthly): gate internal preview routes"
```

### Task 4: Reuse the customer shell in explicit preview mode

**Files:**
- Modify: `monthly_public/page.py`
- Modify: `monthly_public/static/monthly.js`
- Modify: `monthly_public/static/monthly.css`
- Modify: `tests/test_monthly_public_page.py`

- [ ] **Step 1: Write failing shell and JavaScript contract tests**

```python
def test_preview_shell_is_noindex_and_visibly_internal(self):
    html = render_monthly_page("home", preview=True)
    self.assertIn("noindex,nofollow,noarchive", html)
    self.assertIn("تجربة داخلية", html)
    self.assertIn('"preview":true', html)

def test_public_shell_does_not_enable_preview(self):
    self.assertNotIn('"preview":true', render_monthly_page("home"))
```

The JS contract also checks for gated preview endpoint prefixes, token-preserving URL helpers, disabled preview lead/event calls, and syntax validity.

- [ ] **Step 2: Run page tests and verify RED**

Run: `python3 -m unittest tests.test_monthly_public_page -v`

Expected: failure because preview page state and navigation are absent.

- [ ] **Step 3: Implement preview mode in the existing shell**

Add a persistent bilingual banner, change the copy to clearly label incomplete facts, route API calls to `/api/monthly/ops/preview/*`, and map internal navigation under `/monthly/ops/preview`. The auth token is read from the current URL and appended only to staff preview requests and paths; it is never embedded in HTML or stored in session state.

- [ ] **Step 4: Run page and Node tests and verify GREEN**

Run: `python3 -m unittest tests.test_monthly_public_page -v && node --check monthly_public/static/monthly.js`

Expected: all page tests pass and JavaScript syntax exits 0.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/page.py monthly_public/static/monthly.js monthly_public/static/monthly.css tests/test_monthly_public_page.py
git commit -m "feat(monthly): render safe customer preview"
```

### Task 5: Preview entry from apartment readiness

**Files:**
- Modify: `monthly_public/catalog_page.py`
- Modify: `monthly_public/static/monthly_catalog.js`
- Modify: `tests/test_monthly_catalog_page.py`

- [ ] **Step 1: Write the failing entry-action test**

```python
def test_readiness_page_links_to_customer_preview_with_auth_helper(self):
    self.assertIn('id="preview-customer-journey"', render_monthly_catalog_page())
    self.assertIn('authPath("/monthly/ops/preview"', JS_FILE.read_text("utf-8"))
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 -m unittest tests.test_monthly_catalog_page -v`

Expected: failure because the preview action is absent.

- [ ] **Step 3: Add the safe entry action**

Place `معاينة رحلة العميل` beside refresh with the explanation `يعرض كل الشقق داخليًا ولا ينشر أي شقة`. Preserve the current dashboard token through the existing `authPath` helper.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `python3 -m unittest tests.test_monthly_catalog_page -v`

Expected: all readiness page tests pass.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/catalog_page.py monthly_public/static/monthly_catalog.js tests/test_monthly_catalog_page.py
git commit -m "feat(monthly): link readiness to customer preview"
```

### Task 6: Full verification and visual inspection

**Files:**
- Modify only if a reproduced defect requires a focused fix with a new failing test.

- [ ] **Step 1: Run the monthly regression suite**

Run: `python3 -m unittest discover -s tests -p 'test_monthly*.py'`

Expected: 0 failures and 0 errors.

- [ ] **Step 2: Run static safety checks**

Run: `python3 -m py_compile monthly_public/*.py bot.py`

Run: `node --check monthly_public/static/monthly.js && node --check monthly_public/static/monthly_catalog.js`

Run: `git diff --check`

Expected: every command exits 0.

- [ ] **Step 3: Prove data preservation and public isolation**

Run the preview safety test again, then run the public snapshot and public contract tests. Search registered preview paths to prove there is no POST route for preview save, approve, lead, event, or refresh.

- [ ] **Step 4: Inspect Arabic and English desktop/mobile preview**

Start the local server, open the authenticated preview from the readiness workspace, and inspect landing, matcher, results, browse, listing, missing price, missing calendar, and disabled WhatsApp. Verify the persistent preview banner, RTL/LTR layout, images, no clipping, and edit links.

- [ ] **Step 5: Commit any verified visual correction**

Only if a defect was reproduced and fixed with a regression test, stage only the exact preview source and test files changed, then commit with `fix(monthly): polish internal preview`.
