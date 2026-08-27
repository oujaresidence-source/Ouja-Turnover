# Monthly Showcase Listing Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every showcase apartment its own reversible monthly price, let staff choose the cover from real member photos, and provide a truthful all-member internal preview.

**Architecture:** Extend the existing JSON showcase contract without changing the SQLite schema. Resolve cover and price values inside `ShowcaseService`, clone that service onto the existing read-only preview snapshot for staff preview, and keep `bot.py` as thin authenticated adapters. Reuse the current Arabic-first catalog and monthly page assets.

**Tech Stack:** Python 3, aiohttp, SQLite JSON records, vanilla JavaScript/CSS, Node syntax checks, Python `unittest`.

---

## File map

- Modify `monthly_public/showcase_contracts.py`: validate per-listing price rows and cover source IDs while preserving legacy fields.
- Modify `monthly_public/showcase_service.py`: resolve a price per member, validate cover provenance, and present per-home rates.
- Modify `monthly_public/catalog_service.py`: expose approved cached image options to the authenticated editor.
- Modify `monthly_public/preview.py`: attach a showcase service to the read-only preview snapshot and decorate incomplete group homes.
- Modify `monthly_public/routes.py`: apply only the selected listing's manual rate to listing, quote, and lead flows.
- Modify `monthly_public/static/monthly_catalog.js` and `.css`: visual cover chooser, per-listing price controls, and distinct preview/public actions.
- Modify `monthly_public/static/monthly.js`: preview showcase endpoint, per-home price display, and preview-safe return links.
- Modify `monthly_public/catalog_page.py` and `monthly_public/page.py`: asset cache versions and revised staff copy.
- Modify `bot.py`: authenticated group-preview page/API adapters and preview-service wiring.
- Modify focused `tests/test_monthly_showcase_*.py`, `tests/test_monthly_catalog_service.py`, and page/route tests.

### Task 1: Contract and service behavior

- [ ] Write failing tests proving two members can retain different enabled prices, disabled values are preserved, non-member price keys are rejected, and a cover source must be a selected member.
- [ ] Run `python3 -m unittest tests.test_monthly_showcase_contracts tests.test_monthly_showcase_service tests.test_monthly_showcase_routes -v` and confirm the new assertions fail because `listing_prices` and `image_listing_id` do not exist.
- [ ] Add `listing_prices` entries shaped as `{"monthly_rate_sar": 8000, "enabled": true}` and the optional `image_listing_id` to the allowlist.
- [ ] Add `ShowcaseService.manual_rate(group, listing_id)` with per-listing-first and legacy fallback behavior.
- [ ] Use that rate to clear only the matching member's `price_missing` blocker and to build the matching quote and lead.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Real-photo chooser contract

- [ ] Write a failing catalog-service test asserting the staff listing response returns `approved_image_options` from the validated approved listing, not private fields.
- [ ] Add the safe approved image list to `CatalogService.listing`.
- [ ] Write failing service tests that accept a selected member photo and reject a URL/source mismatch.
- [ ] Validate the cover against the cached inventory inside showcase draft creation, save, and approval.
- [ ] Re-run catalog and showcase service tests.

### Task 3: Read-only group preview

- [ ] Write failing tests for `/monthly/ops/preview/showcase/{showcase_slug}` and `/api/monthly/ops/preview/showcase`, including auth gates and all-member results.
- [ ] Clone `ShowcaseService` onto `build_preview_generation` inside `build_preview_app` without changing the public snapshot or store.
- [ ] Add `MonthlyPreviewApp.showcase` decoration so every group card carries preview completeness and missing-reason chips.
- [ ] Register the authenticated page/API before generic preview listing routes and set `PREVIEW_ENDPOINTS.showcase`.
- [ ] Re-run preview, bot-route, and public no-network tests.

### Task 4: Staff editor and customer rendering

- [ ] Write failing JavaScript/page contract tests for a member-level price switch, member-level amount, visual cover gallery, separate preview/public links, and per-home card prices.
- [ ] Replace the raw cover URL and group-wide price controls with a selected-home photo gallery and inline per-member pricing controls.
- [ ] Preserve the legacy rate in the submitted payload while forcing its old group switch off on new saves.
- [ ] Render `showcase_monthly_rate_sar` on the matching public card and keep official-price fallback for homes without an enabled manual rate.
- [ ] Add restrained responsive styles using the existing Ouja tokens, 44px controls, visible focus, and reduced-motion behavior.
- [ ] Bump both local asset versions and run Node syntax checks.

### Task 5: Full verification and release

- [ ] Run all monthly showcase, catalog, preview, pricing, route, page, security, and no-network tests.
- [ ] Run the repository verification routine: Python compile, pyflakes when available, Node checks, and full unit-test discovery.
- [ ] Launch a local server and inspect the Arabic editor plus group preview at desktop and mobile widths; verify photo selection, price toggles, missing-data chips, no clipping, and no console errors.
- [ ] Search the customer request path for external provider calls and the public assets for discount claims or placeholder data.
- [ ] Review the final diff against this plan, preserve unrelated files, commit intentional changes, fetch/merge safely if the remote advanced, and push once to `main`.

