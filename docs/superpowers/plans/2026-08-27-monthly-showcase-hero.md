# Monthly Showcase Hero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one centered, wide, real Ouja image above each public showcase's apartment cards.

**Architecture:** Keep image choice in the existing public UI layer because the approved showcase response already contains the optional group image and public apartment images. A small pure helper selects the safe image source, while the current hero renderer and design tokens provide responsive layout and failure fallback.

**Tech Stack:** Existing JavaScript UI, CSS, Python `unittest`, local browser inspection.

---

### Task 1: Safe hero image selection

**Files:**
- Modify: `tests/test_monthly_showcase_page.py`
- Modify: `monthly_public/static/monthly.js`

- [ ] **Step 1: Write the failing helper test**

Add a Node-backed test that proves an approved HTTPS group image wins, the first safe apartment image is the fallback, and unsafe or missing sources return an empty string.

- [ ] **Step 2: Run the test and verify the expected failure**

Run: `python3 -m unittest tests.test_monthly_showcase_page.MonthlyShowcasePageTest.test_showcase_hero_uses_only_approved_or_real_home_images`

Expected: FAIL because `showcaseHeroImage` is not exported yet.

- [ ] **Step 3: Implement the pure selector**

Add `showcaseHeroImage(showcase, homes)` using the existing `safeImageUrl` function. Check `showcase.image_url` first, then each public home's `image`, returning `""` when no safe source exists. Export the helper for regression testing.

- [ ] **Step 4: Run the focused test**

Run the same command and expect one passing test.

### Task 2: Centered visual hero

**Files:**
- Modify: `monthly_public/static/monthly.js`
- Modify: `monthly_public/static/monthly.css`
- Modify: `monthly_public/page.py`

- [ ] **Step 1: Render the selected image before showcase copy**

Build the public `homes` array before the hero, call `showcaseHeroImage`, and prepend a semantic figure and image when a safe source exists. Give the image localized alt text based on the approved showcase name. Hide the figure on image load failure without affecting the rest of the page.

- [ ] **Step 2: Apply the approved responsive composition**

Make the showcase hero a centered one-column section. Give the media a wide landscape ratio, restrained radius, centered crop, ivory fallback background, and mobile-safe sizing. Keep title and price copy outside the image.

- [ ] **Step 3: Bump the static asset version**

Update the monthly public asset version so browsers receive the new JavaScript and CSS immediately.

- [ ] **Step 4: Run focused automated checks**

Run the showcase page tests, public content tests, JavaScript syntax check, and formatting check. Expect zero failures.

### Task 3: Visual verification and commit

**Files:**
- Modify: `docs/monthly-showcase-readiness-2026-08-27.md`

- [ ] **Step 1: Reload the local showcase**

Open the current internal showcase URL and confirm the fallback uses a real apartment image.

- [ ] **Step 2: Inspect desktop and mobile**

Check Arabic and English, image crop, title hierarchy, card position, loading failure behavior, horizontal overflow, accessible names, and browser errors.

- [ ] **Step 3: Run the full monthly suite**

Run: `python3 -m unittest discover -s tests -p 'test_monthly*.py' -q`

Expected: all monthly tests pass with zero failures.

- [ ] **Step 4: Record evidence and commit**

Update the readiness report with the hero result, stage only the intentional files, and create one focused local commit. Do not push or deploy.
