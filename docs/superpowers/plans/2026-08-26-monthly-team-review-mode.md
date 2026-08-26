# Monthly Team Review Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give authenticated Ouja staff a two-way path between apartment data editing and an all-inventory customer preview while keeping incomplete apartments off public customer routes.

**Architecture:** The server authors a staff-review capability only after existing dashboard authentication and role checks. The public shell renders a staff-only entry action, the preview adds edit links, and the catalog survey saves a draft before navigating to that apartment's preview. Existing `CatalogService.preview_inventory()` remains the only preview data source and already overlays the latest valid draft without publication or provider calls.

**Tech Stack:** Python 3, aiohttp, server-rendered HTML, vanilla JavaScript, CSS, unittest

---

## File map

- `bot.py`: decide whether a public monthly request belongs to an authenticated `admin` or `ops` user.
- `monthly_public/page.py`: author safe page state and render the staff-review entry action.
- `monthly_public/static/monthly.js`: translate and route preview edit actions without leaking them into public mode.
- `monthly_public/catalog_page.py`: give the survey button its final team wording.
- `monthly_public/static/monthly_catalog.js`: save the draft, then open the same apartment in preview mode.
- `monthly_public/static/monthly.css`: style the staff-review strip and preview edit actions.
- `tests/test_monthly_public_page.py`: cover server-authored staff capability and public isolation.
- `tests/test_monthly_public_content.py`: cover preview-only navigation and absence from public behavior.
- `tests/test_monthly_catalog_page.py`: cover save-to-preview wording and behavior.
- `tests/test_monthly_preview.py`: prove the latest draft appears without approval or snapshot refresh.

### Task 1: Author the staff-review capability

**Files:**
- Modify: `tests/test_monthly_public_page.py`
- Modify: `monthly_public/page.py`
- Modify: `bot.py`

- [ ] **Step 1: Write failing page-state tests**

Add tests that call:

```python
page_state("home", staff_review_available=True)
render_monthly_page("home", staff_review_available=True)
render_monthly_page("home", staff_review_available=False)
```

Assert that the authorized state contains `"staff_review_available": True`, authorized HTML contains `id="staff-review-entry"` and `/monthly/ops/preview`, and ordinary public HTML contains neither.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_monthly_public_page
```

Expected: failure because `page_state()` and `render_monthly_page()` do not accept `staff_review_available`.

- [ ] **Step 3: Implement the minimal page contract**

Add the keyword to `page_state()` and `render_monthly_page()`. Store only a boolean in the JSON state. Render this strip only when the boolean is true:

```html
<aside id="staff-review-entry" class="staff-review-entry" role="note">
  <span data-copy="staffReviewHint">أنت تشاهد نسخة العملاء المعتمدة.</span>
  <a class="button button-primary" href="/monthly/ops/preview" data-copy="staffReviewAction">وضع المراجعة: عرض كل الشقق</a>
</aside>
```

In `_monthly_public_page_html()`, compute the value with the existing controls:

```python
staff_review_available = (
    _dash_auth(request) and _req_role(request) in ("admin", "ops")
)
```

Pass it to `_render_monthly_public_page()` for public monthly pages. Do not add it to preview pages because those already render their internal banner.

- [ ] **Step 4: Add route-level auth tests and verify GREEN**

Patch `_dash_auth` and `_req_role` in the existing public-page route tests. Assert `admin` and `ops` receive the entry, a guest role does not, and an unauthenticated request does not.

Run:

```bash
python3 -m unittest tests.test_monthly_public_page tests.test_monthly_public_no_network
```

Expected: all tests pass and no provider client is called.

- [ ] **Step 5: Commit**

```bash
git add bot.py monthly_public/page.py tests/test_monthly_public_page.py
git commit -m "feat(monthly): add staff review entry"
```

### Task 2: Add preview-to-editor navigation

**Files:**
- Modify: `tests/test_monthly_public_content.py`
- Modify: `monthly_public/static/monthly.js`
- Modify: `monthly_public/static/monthly.css`

- [ ] **Step 1: Write a failing static-contract test**

Assert the customer script contains Arabic and English copy for `editPreviewListing`, constructs `/monthly/ops/listings?id=` from an allowlisted listing ID, and adds the edit action only inside an explicit `runtime.preview` branch.

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python3 -m unittest tests.test_monthly_public_content
```

Expected: failure because the edit copy and preview editor link do not exist.

- [ ] **Step 3: Implement the preview edit action**

Add bilingual copy:

```javascript
editPreviewListing: "تعديل بيانات هذه الشقة"
editPreviewListing: "Edit this apartment's data"
```

Add an allowlisted helper:

```javascript
function previewEditorPath(listingId) {
  const value = String(listingId == null ? "" : listingId);
  if (!runtime.preview || !SAFE_ID_RE.test(value)) return "";
  return requestPath("/monthly/ops/listings", { id: value });
}
```

Render the action on preview catalog cards and the preview listing page only. The public card and listing functions must not render this link.

Style the action as a quiet outlined staff control with a 44px minimum touch target and existing cream, green, and gold tokens.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
python3 -m unittest tests.test_monthly_public_content tests.test_monthly_preview
node --check monthly_public/static/monthly.js
```

Expected: all tests pass and JavaScript syntax is valid.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/static/monthly.js monthly_public/static/monthly.css tests/test_monthly_public_content.py
git commit -m "feat(monthly): link preview to editor"
```

### Task 3: Save the draft and open its customer preview

**Files:**
- Modify: `tests/test_monthly_catalog_page.py`
- Modify: `monthly_public/catalog_page.py`
- Modify: `monthly_public/static/monthly_catalog.js`
- Modify: `monthly_public/static/monthly_catalog.css`

- [ ] **Step 1: Write failing survey-action tests**

Assert the catalog page contains `حفظ ومشاهدة كتجربة عميل` and `Save and view as customer`. Assert the script handles the preview button by calling `saveProfile(true)`, waits for the draft response, and navigates to `/monthly/ops/preview/id/` with the returned listing ID. Assert the approve API does not appear inside that save-and-preview branch.

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_page
```

Expected: failure because the current preview button stays on the approval step.

- [ ] **Step 3: Implement the save-to-preview loop**

Change the button copy and, after a successful `saveProfile(true)`, navigate with:

```javascript
window.location.assign(authPath(
  "/monthly/ops/preview/id/" + encodeURIComponent(refreshed.id),
  window.location.search
));
```

Keep failed saves on the survey. Keep the existing optimistic-revision and conflict recovery behavior. Do not call the approval endpoint.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
python3 -m unittest tests.test_monthly_catalog_page tests.test_monthly_catalog_routes
node --check monthly_public/static/monthly_catalog.js
```

Expected: all tests pass and JavaScript syntax is valid.

- [ ] **Step 5: Commit**

```bash
git add monthly_public/catalog_page.py monthly_public/static/monthly_catalog.js monthly_public/static/monthly_catalog.css tests/test_monthly_catalog_page.py
git commit -m "feat(monthly): preview saved drafts"
```

### Task 4: Prove draft reflection and complete the release

**Files:**
- Modify: `tests/test_monthly_preview.py`
- Modify: `docs/monthly-internal-preview-readiness-2026-08-26.md`

- [ ] **Step 1: Write a failing integration regression**

Save a draft with a changed allowlisted Arabic title through `CatalogService.save_profile_draft()`. Build a fresh preview app without approving the profile or refreshing the public snapshot. Assert the preview listing returns the draft title and the public snapshot remains unchanged.

- [ ] **Step 2: Run the test and verify the existing data flow**

Run:

```bash
python3 -m unittest tests.test_monthly_preview
```

Expected: the test passes if the existing draft overlay contract is intact. If it fails, change only `CatalogService.preview_inventory()` enough to restore the documented source, approved, draft precedence.

- [ ] **Step 3: Run full verification**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ouja-team-review-pycache python3 -m py_compile monthly_public/*.py bot.py
node --check monthly_public/static/monthly.js
node --check monthly_public/static/monthly_catalog.js
git diff --check
python3 -m unittest discover -s tests -p 'test_monthly*.py'
```

Expected: Python and JavaScript checks exit zero, formatting has no errors, and all monthly tests pass.

- [ ] **Step 4: Inspect browser journeys**

Verify Arabic and English on desktop and mobile:

- authenticated public monthly page shows the staff review entry;
- anonymous public page does not;
- data page saves a draft and opens the same apartment preview;
- preview shows all current source apartments and the saved draft;
- edit action returns to the same survey;
- public search still excludes incomplete apartments;
- no clipping, horizontal overflow, unnamed controls, or console errors.

- [ ] **Step 5: Update readiness and commit**

Record the staff workflow, current apartment count, test total, visual result, and remaining external blockers. Then commit:

```bash
git add tests/test_monthly_preview.py docs/monthly-internal-preview-readiness-2026-08-26.md
git commit -m "docs(monthly): report team review flow"
```

- [ ] **Step 6: Merge and push once**

Fast-forward local `main`, rerun the full monthly test command on the merged result, fetch `origin/main`, confirm it has not advanced, and push `main` once. Confirm Railway reports success, `/monthly` returns `200`, and anonymous `/monthly/ops/preview` returns `401`.

