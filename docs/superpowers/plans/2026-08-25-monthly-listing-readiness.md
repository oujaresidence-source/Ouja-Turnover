# Monthly Listing Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an authenticated Arabic-first apartment survey that prefills trusted Ouja data, stores drafts and approvals, resolves publication blockers, and refreshes the public monthly catalog from approved records.

**Architecture:** Add a focused catalog store, pure profile contracts, and an orchestration service under `monthly_public/`. Keep `bot.py` as an adapter for existing caches, authorization, and route registration. Customer routes continue to read the atomic snapshot and never call a provider.

**Tech Stack:** Python 3.9, SQLite rollback journaling, `aiohttp` route adapters, vanilla HTML/CSS/JavaScript, `unittest`, existing monthly publication and matcher modules.

---

## File structure

### New files

- `monthly_public/catalog_store.py`: SQLite revisions, approved records, places, global settings, and audit events.
- `monthly_public/catalog_profiles.py`: allowlisted profile, settings, destination, coordinate, and prefill validation.
- `monthly_public/catalog_service.py`: portfolio status, draft/approval workflow, source merge, and snapshot refresh requests.
- `monthly_public/catalog_page.py`: authenticated page shell and asset paths.
- `monthly_public/static/monthly_catalog.css`: responsive Ouja operations styling.
- `monthly_public/static/monthly_catalog.js`: index, survey, global setup, place editor, draft, preview, and approval interactions.
- `tests/test_monthly_catalog_store.py`: persistence and revision tests.
- `tests/test_monthly_catalog_profiles.py`: validation, prefill, coordinate, and sensitive-field exclusion tests.
- `tests/test_monthly_catalog_service.py`: portfolio, draft, approval, and source merge tests.
- `tests/test_monthly_catalog_routes.py`: authenticated route contracts and thin `bot.py` adapter tests.
- `tests/test_monthly_catalog_page.py`: markup, JavaScript, accessibility, and content safety tests.
- `tests/test_monthly_catalog_integration.py`: approve-to-public and last-known-good workflows.

### Modified files

- `monthly_public/routes.py`: atomically replace runtime settings and destination registry.
- `monthly_public/ops_page.py`: add the apartment-data navigation link.
- `monthly_public/static/monthly_ops.js`: preserve the dashboard token in the new link.
- `monthly_public/__init__.py`: export catalog services used by `bot.py`.
- `bot.py`: instantiate the catalog services, provide allowlisted source callbacks, merge approved records, serve assets, register authenticated routes, and trigger snapshot refreshes.
- `tests/test_monthly_public_routes.py`: runtime configuration replacement contract.
- `tests/test_monthly_public_ops_page.py`: navigation and asset route coverage.
- `tests/test_monthly_public_no_network.py`: prove catalog and public requests make no provider calls.
- `docs/monthly-launch-readiness-2026-08-25.md`: add the new data-completion workflow and updated launch checks.

---

### Task 1: Lock the catalog persistence contract

**Files:**
- Create: `monthly_public/catalog_store.py`
- Create: `tests/test_monthly_catalog_store.py`

- [ ] **Step 1: Write failing store tests**

Add tests for rollback journaling, empty records, monotonic revisions, stale writes, approval copies, destination deactivation, global settings, audit rows, and restart persistence.

```python
class CatalogStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "monthly_catalog.sqlite3")
        self.store = CatalogStore(self.path, clock=lambda: NOW)

    def test_draft_does_not_change_approved_profile(self):
        saved = self.store.save_profile_draft(
            "101", {"name_ar": "شقة عوجا"}, expected_revision=0, actor="ops"
        )
        self.assertEqual(saved["draft_revision"], 1)
        self.assertIsNone(self.store.profile("101")["approved"])

    def test_approval_rejects_a_stale_revision(self):
        self.store.save_profile_draft("101", {"name_ar": "أ"}, 0, "ops-a")
        with self.assertRaises(RevisionConflict):
            self.store.approve_profile("101", revision=0, actor="ops-b")

    def test_sqlite_uses_delete_journal_mode(self):
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "delete")
```

- [ ] **Step 2: Run the tests and confirm the red state**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_store -v
```

Expected: import failure for `monthly_public.catalog_store`.

- [ ] **Step 3: Implement the SQLite store**

Implement these public types and methods:

```python
class RevisionConflict(ValueError):
    pass

class CatalogStore:
    def __init__(self, path: str, clock: Callable[[], dt.datetime] = _utc_now): ...
    def profile(self, listing_id: str) -> Dict[str, Any]: ...
    def save_profile_draft(self, listing_id: str, value: Mapping[str, Any],
                           expected_revision: int, actor: str) -> Dict[str, Any]: ...
    def approve_profile(self, listing_id: str, revision: int,
                        actor: str) -> Dict[str, Any]: ...
    def approved_profiles(self) -> Dict[str, Dict[str, Any]]: ...
    def settings(self) -> Dict[str, Any]: ...
    def save_settings_draft(self, value: Mapping[str, Any],
                            expected_revision: int, actor: str) -> Dict[str, Any]: ...
    def approve_settings(self, revision: int, actor: str) -> Dict[str, Any]: ...
    def places(self) -> Dict[str, Dict[str, Any]]: ...
    def save_place_draft(self, place_id: str, value: Mapping[str, Any],
                         expected_revision: int, actor: str) -> Dict[str, Any]: ...
    def approve_place(self, place_id: str, revision: int, active: bool,
                      actor: str) -> Dict[str, Any]: ...
    def audit(self, target: Optional[str] = None, limit: int = 100) -> list[Dict[str, Any]]: ...
    def probe(self) -> Dict[str, Any]: ...
```

Use `PRAGMA journal_mode=DELETE`, `PRAGMA busy_timeout=5000`, short connections, explicit `BEGIN IMMEDIATE`, canonical JSON, and an append-only audit insert inside each successful transaction. Validate listing and place IDs before opening a write transaction.

- [ ] **Step 4: Run store tests**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_store -v
```

Expected: all catalog-store tests pass.

- [ ] **Step 5: Commit the persistence milestone**

```bash
git add monthly_public/catalog_store.py tests/test_monthly_catalog_store.py
git commit -m "feat(monthly): store catalog approvals"
```

---

### Task 2: Define safe profile and prefill contracts

**Files:**
- Create: `monthly_public/catalog_profiles.py`
- Create: `tests/test_monthly_catalog_profiles.py`

- [ ] **Step 1: Write failing validation tests**

Cover allowed fields, unknown-field rejection, Arabic and English titles, three-state facts, commercial terms, map coordinates, Riyadh bounds, destination purposes, and source precedence. Add an explicit payload containing `wifi_pass`, `door_code`, `notes`, `staff_phone`, and `owner_phone`; assert that no returned prefill contains those keys or values.

```python
def test_prefill_drops_sensitive_guide_and_operations_values(self):
    source = {
        "id": 101,
        "name": "Ouja | Unit 101",
        "lat": 24.80,
        "lng": 46.65,
        "wifi_pass": "secret-wifi",
        "door_code": "1234",
        "notes": "call 0500000000",
    }
    prefill = build_prefill(source, stay={}, licence=None, rating=None)
    rendered = json.dumps(prefill, ensure_ascii=False)
    for forbidden in ("secret-wifi", "1234", "0500000000", "wifi_pass", "door_code"):
        self.assertNotIn(forbidden, rendered)

def test_hostaway_coordinates_prefill_as_verified(self):
    value = build_prefill({"id": 101, "lat": 24.80, "lng": 46.65}, {}, None, None)
    self.assertEqual(value["coordinates"]["source"], "hostaway_listing")
    self.assertTrue(value["coordinates"]["verified"])
```

- [ ] **Step 2: Verify the tests fail**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_profiles -v
```

Expected: import failure for `monthly_public.catalog_profiles`.

- [ ] **Step 3: Implement pure contracts**

Provide these functions and exception:

```python
class CatalogContractError(ValueError):
    def __init__(self, field: str, code: str, message_ar: str, message_en: str): ...
    def as_dict(self) -> Dict[str, str]: ...

def parse_profile(value: Any) -> Dict[str, Any]: ...
def parse_global_settings(value: Any) -> Dict[str, Any]: ...
def parse_place(value: Any) -> Dict[str, Any]: ...
def parse_coordinates(value: Any) -> Optional[Dict[str, Any]]: ...
def build_prefill(hostaway: Mapping[str, Any], stay: Mapping[str, Any],
                  licence: Any, rating: Any,
                  approved: Optional[Mapping[str, Any]] = None,
                  draft: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]: ...
def apply_approved_profile(base: Mapping[str, Any],
                           approved: Optional[Mapping[str, Any]]) -> Dict[str, Any]: ...
def completion(profile: Mapping[str, Any]) -> Dict[str, Any]: ...
```

Use an explicit allowlist. Accept Hostaway coordinates only when the same listing row supplies them and they fall inside `24.0 <= lat <= 25.6` and `46.0 <= lng <= 47.6`. Mark title-matched guide coordinates as `verified=False`. Keep coordinates in operations responses but remove them from public presentation payloads.

- [ ] **Step 4: Run profile and existing publication tests**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_profiles tests.test_monthly_public_publication -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the profile contract milestone**

```bash
git add monthly_public/catalog_profiles.py tests/test_monthly_catalog_profiles.py
git commit -m "feat(monthly): validate catalog profiles"
```

---

### Task 3: Build catalog orchestration and portfolio status

**Files:**
- Create: `monthly_public/catalog_service.py`
- Create: `tests/test_monthly_catalog_service.py`

- [ ] **Step 1: Write failing service tests**

Test one row per listing, draft precedence, approved precedence over source defaults, publication blockers, system blockers, approval with a missing price, revision conflicts, global settings fallback, active places, and failed snapshot retention.

```python
def test_approval_keeps_background_blockers_separate(self):
    service = self.service(source=[source_listing(official_prices={})])
    saved = service.save_profile_draft("101", valid_profile(), 0, "ops")
    result = service.approve_profile("101", saved["draft_revision"], "ops")
    self.assertTrue(result["approved"])
    self.assertFalse(result["published"])
    self.assertIn("price_missing", result["background_blockers"])

def test_portfolio_never_duplicates_language_versions(self):
    rows = self.service(source=[source_listing(id=101)]).portfolio()["listings"]
    self.assertEqual([row["id"] for row in rows], ["101"])
```

- [ ] **Step 2: Run the tests and confirm failure**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_service -v
```

Expected: import failure for `monthly_public.catalog_service`.

- [ ] **Step 3: Implement the service**

Inject every host dependency:

```python
class CatalogService:
    def __init__(self, store: CatalogStore,
                 source_provider: Callable[[], Mapping[str, Any]],
                 settings_fallback: Callable[[], Mapping[str, Any]],
                 snapshot_refresh: Callable[[], Mapping[str, Any]],
                 clock: Callable[[], dt.datetime]): ...
    def portfolio(self) -> Dict[str, Any]: ...
    def listing(self, listing_id: str) -> Dict[str, Any]: ...
    def save_profile_draft(self, listing_id: str, value: Any,
                           revision: int, actor: str) -> Dict[str, Any]: ...
    def approve_profile(self, listing_id: str, revision: int,
                        actor: str) -> Dict[str, Any]: ...
    def settings(self) -> Dict[str, Any]: ...
    def save_settings_draft(self, value: Any, revision: int,
                            actor: str) -> Dict[str, Any]: ...
    def approve_settings(self, revision: int, actor: str) -> Dict[str, Any]: ...
    def places(self) -> Dict[str, Any]: ...
    def save_place_draft(self, place_id: str, value: Any,
                         revision: int, actor: str) -> Dict[str, Any]: ...
    def approve_place(self, place_id: str, revision: int, active: bool,
                      actor: str) -> Dict[str, Any]: ...
    def refresh(self) -> Dict[str, Any]: ...
    def approved_profiles(self) -> Dict[str, Dict[str, Any]]: ...
    def approved_settings_values(self) -> Mapping[str, Any]: ...
    def approved_places(self) -> Mapping[str, Any]: ...
```

Return staff-controlled blockers and background blockers in separate arrays. Approve valid staff fields even when the price, calendar, or rating source remains incomplete. Call `snapshot_refresh` after approval and return the accepted generation status without discarding the approved revision on refresh failure.

- [ ] **Step 4: Run service tests**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_service -v
```

Expected: all service tests pass.

- [ ] **Step 5: Commit the service milestone**

```bash
git add monthly_public/catalog_service.py tests/test_monthly_catalog_service.py
git commit -m "feat(monthly): orchestrate listing readiness"
```

---

### Task 4: Make public runtime configuration replaceable

**Files:**
- Modify: `monthly_public/routes.py:622-700`
- Modify: `tests/test_monthly_public_routes.py`

- [ ] **Step 1: Write a failing runtime replacement test**

```python
def test_replace_configuration_updates_settings_and_places_together(self):
    new_settings = valid_settings(whatsapp_number="966500000001")
    self.app.replace_configuration(new_settings, {"hospital": approved_place()})
    config = self.app.config("ar")
    self.assertTrue(config["contact"]["enabled"])
    self.assertEqual(config["places"][0]["id"], "hospital")
```

- [ ] **Step 2: Verify the test fails**

Run:

```bash
python3 -m unittest tests.test_monthly_public_routes.MonthlyPublicRoutesTest.test_replace_configuration_updates_settings_and_places_together -v
```

Expected: `MonthlyPublicApp` has no `replace_configuration` method.

- [ ] **Step 3: Add immutable runtime replacement**

Add a lock and replace both references inside it:

```python
def replace_configuration(self, settings: MonthlySettings,
                          approved_places: Mapping[str, Any]) -> None:
    prepared = self._prepare_places(approved_places)
    with self._configuration_lock:
        self.settings = settings
        self.approved_places = prepared
```

Add `_configuration()` to copy the settings reference and immutable place registry under the same lock. Pin those references beside the clock and generation at the start of each customer request, then pass them to configuration, place, matching, and handoff helpers. Do not mutate the active place dictionary.

- [ ] **Step 4: Run public route tests**

Run:

```bash
python3 -m unittest tests.test_monthly_public_routes -v
```

Expected: all route tests pass.

- [ ] **Step 5: Commit the runtime configuration milestone**

```bash
git add monthly_public/routes.py tests/test_monthly_public_routes.py
git commit -m "refactor(monthly): replace public config safely"
```

---

### Task 5: Merge approved records into the cached source adapter

**Files:**
- Modify: `bot.py:57958-58175`
- Modify: `monthly_public/__init__.py`
- Create: `tests/test_monthly_catalog_integration.py`

- [ ] **Step 1: Write failing adapter tests**

Test that an approved profile supplies `content_verified`, bilingual content, neighborhood, terms, licence, facts, and verified coordinates; a draft supplies none of them to the public adapter. Assert that engine and calendar values remain source-owned.

```python
def test_only_approved_profile_reaches_public_source(self):
    self.catalog.save_profile_draft("101", valid_profile(), 0, "ops")
    draft_source = self.bot._monthly_public_source_adapter()["listings"][0]
    self.assertFalse(draft_source["content_verified"])
    self.catalog.approve_profile("101", 1, "ops")
    approved_source = self.bot._monthly_public_source_adapter()["listings"][0]
    self.assertTrue(approved_source["content_verified"])
    self.assertEqual(approved_source["name_ar"], "شقة عوجا")
```

- [ ] **Step 2: Verify the test fails**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_integration -v
```

Expected: catalog objects or approved merge are unavailable.

- [ ] **Step 3: Wire store, service, and source merge**

Initialize `CatalogStore(_state_path("monthly_catalog.sqlite3"))` beside the existing public stores. Add `_monthly_catalog_prefill_source()` that returns an allowlisted row with source labels from `_gw_cache`, `_gw_overrides`, monthly licence DB, ratings, `_mengine`, and `_mcal`.

In `_monthly_public_source_adapter()`:

```python
approved = (_monthly_catalog_service.approved_profiles().get(lid)
            if _monthly_catalog_service else None)
row = _monthly_catalog_apply_approved_profile(row, approved)
```

In `_monthly_public_refresh_snapshot()`, load approved global settings and places, call `load_settings`, replace the app configuration, then build the snapshot. Keep environment values as fallback until staff approve stored global settings.

- [ ] **Step 4: Run integration and publication tests**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_integration tests.test_monthly_public_publication tests.test_monthly_public_snapshot -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the source integration milestone**

```bash
git add bot.py monthly_public/__init__.py tests/test_monthly_catalog_integration.py
git commit -m "feat(monthly): publish approved profiles"
```

---

### Task 6: Add authenticated catalog API adapters

**Files:**
- Modify: `bot.py:58950-59120`
- Create: `tests/test_monthly_catalog_routes.py`

- [ ] **Step 1: Write failing route tests**

Cover every GET and POST route, dashboard authorization, operations role, malformed bodies, unknown fields, listing existence, stale revision, actor propagation, and safe error payloads.

```python
async def test_profile_draft_requires_monthly_operations_access(self):
    request = FakeRequest(json={"revision": 0, "profile": valid_profile()})
    with patch.object(self.bot, "_monthly_ops_gate", return_value=forbidden_response()):
        response = await self.bot._api_monthly_catalog_profile_draft(request)
    self.assertEqual(response.status, 403)

async def test_revision_conflict_is_409(self):
    self.service.save_profile_draft("101", valid_profile(), 0, "ops")
    response = await self.post_draft("101", revision=0)
    self.assertEqual(response.status, 409)
    self.assertEqual(self.json(response)["error"], "revision_conflict")
```

- [ ] **Step 2: Run route tests and confirm failure**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_routes -v
```

Expected: route handlers are missing.

- [ ] **Step 3: Implement thin handlers and registration**

Add handlers for the routes defined in the approved design. Each handler must:

```python
denied = _monthly_ops_gate(request)
if denied is not None:
    return denied
try:
    payload = await _read_body(request)
    result = _monthly_catalog_service.save_profile_draft(
        request.match_info["id"], payload.get("profile"),
        payload.get("revision"), _req_actor(request)
    )
    return _json({"ok": True, "result": result})
except _CatalogRevisionConflict:
    return _json({"error": "revision_conflict"}, 409)
except _CatalogContractError as error:
    return _json({"error": "invalid_request", "issue": error.as_dict()}, 400)
```

Use the existing operations authorization and token transport. Do not log request bodies.

- [ ] **Step 4: Run route tests**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_routes tests.test_monthly_public_ops_page -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the API milestone**

```bash
git add bot.py tests/test_monthly_catalog_routes.py
git commit -m "feat(monthly): expose catalog operations API"
```

---

### Task 7: Build the Arabic-first page shell and navigation

**Files:**
- Create: `monthly_public/catalog_page.py`
- Create: `monthly_public/static/monthly_catalog.css`
- Modify: `monthly_public/ops_page.py`
- Modify: `monthly_public/static/monthly_ops.js`
- Modify: `bot.py:58950-59120`
- Create: `tests/test_monthly_catalog_page.py`

- [ ] **Step 1: Write failing page and accessibility tests**

Assert Arabic-first HTML, English switch, skip link, semantic headings, status text, labels, `aria-live`, 44-pixel controls, focus visibility, RTL/LTR support, reduced motion, no inline customer data, and token-preserving navigation.

```python
def test_page_is_arabic_first_and_form_controls_are_labelled(self):
    html = render_monthly_catalog_page()
    self.assertIn('<html lang="ar" dir="rtl">', html)
    self.assertIn('href="#catalog-main"', html)
    self.assertIn('id="catalog-language"', html)
    self.assertNotIn("wifi", html.lower())

def test_css_has_touch_focus_and_reduced_motion_rules(self):
    css = CSS_FILE.read_text("utf-8")
    self.assertIn("min-height: 44px", css)
    self.assertIn(":focus-visible", css)
    self.assertIn("prefers-reduced-motion: reduce", css)
```

- [ ] **Step 2: Verify the page tests fail**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_page -v
```

Expected: page module and assets are missing.

- [ ] **Step 3: Implement the shell and styles**

Create a page with:

```html
<main id="catalog-main">
  <section id="catalog-summary" aria-live="polite"></section>
  <section id="global-setup" aria-labelledby="global-title"></section>
  <section id="portfolio" aria-labelledby="portfolio-title">
    <form id="portfolio-filters" role="search"></form>
    <div id="listing-table"></div>
  </section>
  <section id="survey" hidden aria-labelledby="survey-title"></section>
  <section id="places" hidden aria-labelledby="places-title"></section>
</main>
```

Use the existing operations tokens and IBM Plex Sans Arabic. Keep the desktop layout to a list plus focused editor. Use four status tones: neutral, warning, ready, and blocked. Do not add wide shadows, oversized radii, gradient text, or nested card grids.

- [ ] **Step 4: Serve the page and assets behind operations access**

Register `/monthly/ops/listings`, `/monthly/ops/catalog.css`, and `/monthly/ops/catalog.js`. Preserve the dashboard token in both directions. Return 401 or 403 before rendering the page when access fails.

- [ ] **Step 5: Run page and ops navigation tests**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_page tests.test_monthly_public_ops_page -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit the page shell milestone**

```bash
git add monthly_public/catalog_page.py monthly_public/static/monthly_catalog.css monthly_public/ops_page.py monthly_public/static/monthly_ops.js bot.py tests/test_monthly_catalog_page.py
git commit -m "feat(monthly): add listing readiness page"
```

---

### Task 8: Implement the survey, global setup, and place interactions

**Files:**
- Create: `monthly_public/static/monthly_catalog.js`
- Modify: `tests/test_monthly_catalog_page.py`
- Modify: `tests/test_monthly_catalog_routes.py`

- [ ] **Step 1: Write failing JavaScript contract tests**

Use the existing Node test pattern to cover safe token paths, status filters, draft payload construction, revision updates, three-state facts, bilingual fields, conditional cleaning amount, global settings, place coordinates, revision conflicts, and error summaries.

```javascript
assert.deepStrictEqual(buildFactValue("yes"), true);
assert.deepStrictEqual(buildFactValue("no"), false);
assert.deepStrictEqual(buildFactValue("unknown"), null);
assert.throws(() => buildProfilePayload({name_ar: "English only"}), /name_ar/);
assert.deepStrictEqual(parseCoordinatePair("24.80, 46.65"), {lat: 24.8, lng: 46.65});
```

- [ ] **Step 2: Run page tests and confirm the JavaScript failures**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_page -v
```

Expected: exported JavaScript helpers or interaction copy are missing.

- [ ] **Step 3: Implement API and state helpers**

Expose pure helpers under `module.exports` before the DOM guard:

```javascript
module.exports = {
  authPath, buildProfilePayload, buildSettingsPayload, buildPlacePayload,
  parseCoordinatePair, buildFactValue, filterListings, completionPercent
};
```

Use `textContent`, `setAttribute`, and element construction for API values. Do not insert API content with `innerHTML`.

- [ ] **Step 4: Implement the portfolio and seven survey sections**

Load the portfolio once, render search and filters, then load one apartment on selection. `التالي` saves the active section draft. Keep revision numbers in state and show a saved timestamp. The final approval button submits the current revision, then reloads the apartment and portfolio row.

Render source labels for each prefilled field. Separate staff blockers from price, calendar, and other background blockers. Add links to the existing Monthly Lab route for price actions.

- [ ] **Step 5: Implement global setup and destination catalog**

Build working-hour rows, deposit and payment controls, and the four-to-six-month route. Build a place editor with stable ID, bilingual labels, purposes, coordinates, source note, and active state. Preview straight-line distances only after the API accepts both coordinate records.

- [ ] **Step 6: Handle failures without losing drafts**

Map 401, 403, 409, 400, and 503 responses to bilingual page states. A 409 reloads the server draft, preserves the user's unsaved fields in memory, and asks them to compare before saving. A refresh failure shows that the approved record exists while the last-known-good public snapshot remains active.

- [ ] **Step 7: Run page and API tests**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_page tests.test_monthly_catalog_routes -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit the interaction milestone**

```bash
git add monthly_public/static/monthly_catalog.js tests/test_monthly_catalog_page.py tests/test_monthly_catalog_routes.py
git commit -m "feat(monthly): complete catalog survey"
```

---

### Task 9: Connect approved destinations to matching

**Files:**
- Modify: `monthly_public/catalog_profiles.py`
- Modify: `monthly_public/catalog_service.py`
- Modify: `monthly_public/matching.py`
- Modify: `monthly_public/routes.py`
- Modify: `tests/test_monthly_catalog_service.py`
- Modify: `tests/test_monthly_public_matching.py`
- Modify: `tests/test_monthly_public_routes.py`

- [ ] **Step 1: Write failing proximity tests**

```python
def test_approved_place_ranks_verified_nearby_apartment(self):
    places = {"hospital": approved_place(lat=24.70, lng=46.65, purposes=["treatment"])}
    generation = valid_generation(
        listings=[
            valid_listing(id="far", coordinates=verified_coords(24.85, 46.80)),
            valid_listing(id="near", coordinates=verified_coords(24.701, 46.651)),
        ]
    )
    result = rank(generation, request(place="hospital"), "ar", now=NOW, places=places)
    self.assertEqual(result["top"][0]["listing"]["id"], "near")
    self.assertIn("place_verified_distance", result["top"][0]["reason_codes"])

def test_public_listing_never_exposes_coordinates(self):
    payload = self.app.listing("near")
    rendered = json.dumps(payload)
    self.assertNotIn('"lat"', rendered)
    self.assertNotIn('"lng"', rendered)
```

- [ ] **Step 2: Verify the tests fail for stored destinations**

Run:

```bash
python3 -m unittest tests.test_monthly_public_matching tests.test_monthly_public_routes tests.test_monthly_catalog_service -v
```

Expected: the stored destination registry is not connected.

- [ ] **Step 3: Feed active approved places into the public app**

Map stored purpose categories to the existing `destination` contract. Reuse the pure Haversine calculation. Return a localized `distance_km` reason only when both coordinate sources are approved. Keep neighborhood matching unchanged.

- [ ] **Step 4: Run proximity tests**

Run:

```bash
python3 -m unittest tests.test_monthly_public_matching tests.test_monthly_public_routes tests.test_monthly_catalog_service -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the proximity milestone**

```bash
git add monthly_public/catalog_profiles.py monthly_public/catalog_service.py monthly_public/matching.py monthly_public/routes.py tests/test_monthly_catalog_service.py tests/test_monthly_public_matching.py tests/test_monthly_public_routes.py
git commit -m "feat(monthly): approve nearby destinations"
```

---

### Task 10: Wire refresh triggers and prove last-known-good behavior

**Files:**
- Modify: `bot.py:57440-57580`
- Modify: `bot.py:60940-60985`
- Modify: `bot.py:68600-68640`
- Modify: `tests/test_monthly_catalog_integration.py`
- Modify: `tests/test_monthly_public_no_network.py`

- [ ] **Step 1: Write failing trigger tests**

Cover application startup, calendar success, engine success, listing-cache refresh, licence refresh, approval refresh, manual refresh, and failed refresh retention. Assert that public GET and POST routes never invoke refresh callbacks.

```python
def test_failed_refresh_keeps_current_generation(self):
    before = self.snapshot.current.generation_id
    self.source_provider.side_effect = RuntimeError("source unavailable")
    result = self.service.refresh()
    self.assertFalse(result["accepted"])
    self.assertEqual(self.snapshot.current.generation_id, before)

def test_customer_request_does_not_refresh_or_call_provider(self):
    with patch.object(self.bot, "_monthly_public_refresh_snapshot") as refresh:
        self.call_public_browse()
    refresh.assert_not_called()
```

- [ ] **Step 2: Verify the new trigger tests fail**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_integration tests.test_monthly_public_no_network -v
```

Expected: one or more refresh boundaries are missing.

- [ ] **Step 3: Add background-only refresh requests**

Keep existing calendar and engine loop calls. Add a refresh after a successful guest-listing cache update and application startup after caches become readable. Coalesce repeated requests with one lock and pending flag so simultaneous sources build one next generation.

```python
def _monthly_public_request_refresh(reason):
    if not _monthly_public_refresh_lock.acquire(False):
        _monthly_public_refresh_pending.set()
        return {"accepted": False, "pending": True, "reason": reason}
    try:
        return _monthly_public_refresh_snapshot()
    finally:
        _monthly_public_refresh_lock.release()
```

Run a second pass when the pending flag was set during the first pass. Limit this to one extra pass per call so a broken source cannot create a tight loop.

- [ ] **Step 4: Run integration and no-network tests**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_integration tests.test_monthly_public_no_network -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the reliability milestone**

```bash
git add bot.py tests/test_monthly_catalog_integration.py tests/test_monthly_public_no_network.py
git commit -m "fix(monthly): refresh approved catalog safely"
```

---

### Task 11: Complete operations evidence and launch documentation

**Files:**
- Modify: `monthly_public/health.py`
- Modify: `monthly_public/ops_page.py`
- Modify: `monthly_public/static/monthly_ops.js`
- Modify: `tests/test_monthly_public_health.py`
- Modify: `tests/test_monthly_public_ops_page.py`
- Modify: `docs/monthly-launch-readiness-2026-08-25.md`

- [ ] **Step 1: Write failing health and link tests**

Assert that health reports approved profile count, drafts awaiting review, profile completion, stored settings, active destinations, catalog database write probe, and direct links to the affected survey section.

```python
def test_health_names_catalog_readiness(self):
    health = build_health(self.generation, self.settings, catalog=self.catalog_health)
    self.assertEqual(health["catalog"]["approved_profiles"], 12)
    self.assertEqual(health["catalog"]["drafts_waiting"], 3)
    self.assertTrue(health["catalog"]["write_probe"])
```

- [ ] **Step 2: Verify health tests fail**

Run:

```bash
python3 -m unittest tests.test_monthly_public_health tests.test_monthly_public_ops_page -v
```

Expected: catalog health fields are missing.

- [ ] **Step 3: Add catalog evidence to operations health**

Add a catalog section without exposing draft content. Update blocker rows with safe `action_url` values that point to `/monthly/ops/listings?id=<listing>&section=<section>`. Preserve the current launch decision and count definitions.

- [ ] **Step 4: Update the launch-readiness report**

Record the new workflow, test totals, visual evidence paths, confirmed current blockers, and the difference between staff-approved and publicly published apartments. Keep the launch recommendation tied to live health, not the presence of code.

- [ ] **Step 5: Run health and ops tests**

Run:

```bash
python3 -m unittest tests.test_monthly_public_health tests.test_monthly_public_ops_page -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit the operations milestone**

```bash
git add monthly_public/health.py monthly_public/ops_page.py monthly_public/static/monthly_ops.js tests/test_monthly_public_health.py tests/test_monthly_public_ops_page.py docs/monthly-launch-readiness-2026-08-25.md
git commit -m "feat(monthly): report catalog readiness"
```

---

### Task 12: Final automated, visual, and content verification

**Files:**
- Modify only files needed to fix reproduced defects.
- Test: all monthly catalog and public suites.

- [ ] **Step 1: Run the new feature suite**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_monthly_catalog*.py'
```

Expected: all new catalog tests pass.

- [ ] **Step 2: Run all monthly public tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_monthly_public*.py'
```

Expected: all monthly-public tests pass.

- [ ] **Step 3: Run legacy monthly compatibility tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_monthly*.py'
```

Expected: all non-browser tests pass. Record the two existing Chromium sandbox errors separately if the environment still blocks those PDF tests.

- [ ] **Step 4: Run compile, whitespace, and source-boundary checks**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ouja-monthly-catalog-pycache python3 -m py_compile bot.py monthly_public/*.py
git diff --check origin/main..HEAD
rg -n 'requests\.|aiohttp\.Client|Hostaway|unit_availability_price' monthly_public/catalog_*.py monthly_public/static/monthly_catalog.js
```

Expected: compile and whitespace checks exit zero. The source scan contains no provider client or customer-request call.

- [ ] **Step 5: Run the sensitive-content scan**

Search the catalog modules, page, and API fixtures for Wi-Fi credentials, access-code fields, staff phone labels, placeholder values, discount language, raw coordinates in public payloads, and duplicate listing IDs.

```bash
rg -ni 'wifi_pass|door_code|access_code|staff_phone|owner_phone|up to 30%|حتى 30|lorem|placeholder' monthly_public/catalog_*.py monthly_public/static/monthly_catalog.* tests/test_monthly_catalog*.py
```

Expected: only explicit rejection-test fixtures match sensitive field names. No page or public response renders their values.

- [ ] **Step 6: Launch a local preview with safe real-source prefills**

Use the existing cached listing and image sources. Do not use test prices, fake licences, fake ratings, or fake destinations in the deliverable preview. The page may show truthful blockers when local state lacks production values.

- [ ] **Step 7: Inspect Arabic and English desktop and mobile journeys**

Test:

- portfolio search and blocker filters;
- one apartment prefill and source labels;
- draft save and reload;
- global settings draft;
- destination draft and distance preview;
- approval with a background price blocker;
- revision conflict;
- keyboard navigation and focus order;
- 320, 390, 768, and 1440 pixel widths;
- no clipping, mixed direction, broken images, or hidden sticky actions.

Save screenshots under a non-committed QA output directory and link them from the launch report.

- [ ] **Step 8: Run a focused independent review**

Review the branch diff for data leakage, missing authorization, public provider calls, SQLite volume compatibility, stale-revision handling, and source-precedence errors. Fix only reproduced defects and rerun their targeted tests.

- [ ] **Step 9: Run final verification after fixes**

Repeat Steps 1 through 5. Record exact passed, failed, skipped, and environment-limited counts in the launch report.

- [ ] **Step 10: Commit verified fixes and report updates**

```bash
git add bot.py monthly_public tests docs/monthly-launch-readiness-2026-08-25.md
git commit -m "fix(monthly): harden catalog readiness"
```

Do not push, merge, deploy, modify Railway variables, approve apartment data, or alter live sources without a separate explicit production instruction.
