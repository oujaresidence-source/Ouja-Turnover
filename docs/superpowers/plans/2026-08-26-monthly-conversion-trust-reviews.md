# Monthly Conversion, Trust, and Reviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add price-priority matching, verified listing-specific review proof, and full-journey trust polish to the existing Ouja monthly product without provider calls on customer requests.

**Architecture:** Keep routes and the last-known-good snapshot intact. Add a focused review projection module that receives cached normalized reviews from the thin `bot.py` source adapter, then expose its privacy-safe result through presentation. Extend the existing matcher, analytics contract, customer renderer, and operations readiness view without moving unrelated code.

**Tech Stack:** Python 3 standard library, SQLite, aiohttp route adapters, vanilla JavaScript, CSS, `unittest`, Node-based JavaScript contract tests.

---

## File Structure

- Create `monthly_public/reviews.py`: normalize cached reviews, isolate by listing ID, shorten names, sort latest ten, and compute deterministic topic mentions.
- Create `tests/test_monthly_public_reviews.py`: privacy, ordering, aggregation, source isolation, and conflict tests.
- Modify `monthly_public/contracts.py`: add price-priority and analytics event contracts.
- Modify `monthly_public/matching.py`: apply approved sort modes after hard eligibility and fit scoring.
- Modify `monthly_public/presentation.py`: expose the prepared public review object on listing pages only.
- Modify `bot.py`: thin cached-source adapter call that injects prepared review projections; no provider calls.
- Modify `monthly_public/static/monthly.js`: matcher question, functional emojis, review UI, price-value framing, and analytics.
- Modify `monthly_public/static/monthly.css`: responsive trust, review, and price-card polish.
- Modify `monthly_public/catalog_service.py`: surface review readiness in the staff portfolio and listing workspace payloads.
- Modify `monthly_public/static/monthly_ops.js`: show review coverage and direct preview evidence.
- Modify focused monthly tests for contracts, matching, presentation, analytics, page assets, and ops payloads.

### Task 1: Price-priority contract and ranking

**Files:**
- Modify: `monthly_public/contracts.py`
- Modify: `monthly_public/matching.py`
- Test: `tests/test_monthly_public_contracts.py`
- Test: `tests/test_monthly_public_matching.py`

- [ ] **Step 1: Write failing contract tests**

```python
def test_match_request_requires_approved_price_priority(self):
    parsed = parse_match_request(request(price_priority="value"))
    self.assertEqual(parsed["price_priority"], "value")
    with self.assertRaises(ContractError):
        parse_match_request(request(price_priority="premium_revenue"))
```

- [ ] **Step 2: Run the focused contract test**

Run: `python -m unittest tests.test_monthly_public_contracts -v`  
Expected: FAIL because `price_priority` is not accepted.

- [ ] **Step 3: Add the stable contract**

```python
PRICE_PRIORITIES = ("experience", "value", "lowest_suitable")

# Add "price_priority" to MATCHER_QUESTIONS and parse_match_request's allowlist.
result["price_priority"] = _choice(
    data.get("price_priority"), "price_priority", PRICE_PRIORITIES
)
```

- [ ] **Step 4: Write failing ranking tests**

```python
def test_lowest_suitable_prioritizes_price_after_hard_gates(self):
    ranked = rank(
        generation(listing(1001, rate=18000), listing(1002, rate=9000)),
        request(price_priority="lowest_suitable"), "en", now=NOW,
    )
    self.assertEqual(ranked["top"][0]["id"], "1002")

def test_experience_keeps_verified_fit_ahead_of_price(self):
    ranked = rank(
        generation(
            listing(1001, rate=18000, facts={"workspace": True}),
            listing(1002, rate=9000),
        ),
        request(price_priority="experience"), "en", now=NOW,
    )
    self.assertEqual(ranked["top"][0]["id"], "1001")
```

- [ ] **Step 5: Implement the approved sort modes**

```python
def _sort(items, price_priority):
    if price_priority == "lowest_suitable":
        key = lambda item: (
            item["quote"]["stay_total_sar"], -item["fit_score"], _id_sort(item["id"])
        )
    elif price_priority == "value":
        key = lambda item: (
            -(item["fit_score"] / max(1, item["quote"]["stay_total_sar"])),
            -item["fit_score"], item["quote"]["stay_total_sar"], _id_sort(item["id"])
        )
    else:
        key = lambda item: (
            -item["fit_score"], item["quote"]["stay_total_sar"], _id_sort(item["id"])
        )
    return tuple(sorted(items, key=key))
```

Call `_sort(items, parsed["price_priority"])` for exact and near matches. Keep availability, price coverage, capacity, and sleeping checks unchanged.

- [ ] **Step 6: Run contract and matching tests**

Run: `python -m unittest tests.test_monthly_public_contracts tests.test_monthly_public_matching -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add monthly_public/contracts.py monthly_public/matching.py tests/test_monthly_public_contracts.py tests/test_monthly_public_matching.py
git commit -m "feat(monthly): add price-priority matching"
```

### Task 2: Privacy-safe review projection

**Files:**
- Create: `monthly_public/reviews.py`
- Create: `tests/test_monthly_public_reviews.py`

- [ ] **Step 1: Write failing projection tests**

```python
def test_review_projection_is_listing_specific_latest_and_private_safe(self):
    projection = build_review_projections(
        [
            review("r1", "1001", "2026-05-01", "نظيف وواسع", "Faisal Nassar"),
            review("r2", "1001", "2026-05-02", "ممتاز", "Sara Ahmed"),
            review("r3", "1002", "2026-05-03", "different home", "Other Guest"),
        ]
    )["1001"]
    self.assertEqual([row["id"] for row in projection["latest_reviews"]], ["r2", "r1"])
    self.assertEqual(projection["latest_reviews"][0]["guest_name"], "Sara A.")
    payload = json.dumps(projection)
    self.assertNotIn("private_review", payload)
    self.assertNotIn("reservation_id", payload)
    self.assertNotIn("different home", payload)
```

- [ ] **Step 2: Run the new test**

Run: `python -m unittest tests.test_monthly_public_reviews -v`  
Expected: FAIL because `monthly_public.reviews` does not exist.

- [ ] **Step 3: Implement the focused module**

```python
TOPICS = {
    "cleanliness": ("نظاف", "نظيف", "clean", "spotless"),
    "space": ("واسع", "مساح", "spacious", "roomy"),
    "service": ("استجاب", "متعاون", "مرن", "responsive", "support"),
    "location": ("موقع", "قريب", "location", "easy access"),
    "accuracy": ("مطابق", "الصور", "accurate", "photos"),
    "value": ("سعر", "قيمة", "price", "value"),
}

def build_review_projections(rows):
    grouped = {}
    for raw in rows or ():
        review = _eligible_review(raw)
        if review is None:
            continue
        grouped.setdefault(review["listing_id"], []).append(review)
    return {listing_id: _project(items) for listing_id, items in grouped.items()}
```

`_eligible_review` must validate listing ID, public flag, ISO date, rating 1–5, and public text. `_project` computes aggregate rating/count, text count, deterministic mention counts, and latest ten. The returned review rows contain only `id`, `rating`, shortened `guest_name`, `text`, `language`, `translation`, `translation_label`, `channel`, and `date`.

- [ ] **Step 4: Add conflict and boundary tests**

```python
def test_invalid_and_private_reviews_are_omitted(self):
    result = build_review_projections([
        review("private", "1001", "2026-05-01", "hidden", "Guest", is_public=False),
        review("zero", "1001", "2026-05-01", "bad rating", "Guest", rating=0),
    ])
    self.assertEqual(result, {})

def test_latest_reviews_are_capped_at_ten(self):
    rows = [review(str(i), "1001", "2026-05-%02d" % i, "نظيف", "Guest Name") for i in range(1, 13)]
    self.assertEqual(len(build_review_projections(rows)["1001"]["latest_reviews"]), 10)
```

- [ ] **Step 5: Run review tests**

Run: `python -m unittest tests.test_monthly_public_reviews -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add monthly_public/reviews.py tests/test_monthly_public_reviews.py
git commit -m "feat(monthly): project verified public reviews"
```

### Task 3: Cached source and listing presentation integration

**Files:**
- Modify: `bot.py`
- Modify: `monthly_public/presentation.py`
- Modify: `tests/test_monthly_public_presentation.py`
- Modify: `tests/test_monthly_public_no_network.py`

- [ ] **Step 1: Write failing presentation tests**

```python
def test_listing_exposes_safe_prepared_review_projection(self):
    source = valid_listing(public_reviews={
        "rating_value": 5.0,
        "rating_count": 16,
        "text_review_count": 16,
        "topic_mentions": [{"key": "cleanliness", "count": 7, "total": 16}],
        "latest_reviews": [{"id": "r1", "rating": 5, "guest_name": "Sara A.", "text": "نظيف", "language": "ar", "channel": "Airbnb", "date": "2026-05-01"}],
    })
    payload = present_listing(self._result(**source), "ar")
    self.assertEqual(payload["reviews"]["latest_reviews"][0]["text"], "نظيف")
```

- [ ] **Step 2: Run presentation test**

Run: `python -m unittest tests.test_monthly_public_presentation -v`  
Expected: FAIL because the listing payload omits the review projection.

- [ ] **Step 3: Inject reviews only at the cached adapter boundary**

```python
from monthly_public.reviews import build_review_projections as _monthly_review_projections

def _monthly_public_source_adapter(include_approved=True):
    review_map = _monthly_review_projections(_reviews.values())
    # Existing cached listing loop:
    prepared["public_reviews"] = copy.deepcopy(review_map.get(lid))
```

The adapter must not call `fetch_reviews_from_hostaway`, `api_get`, or another provider function. Add `reviews` to `source_timestamps` using the existing in-memory last-fetch time when present.

- [ ] **Step 4: Expose only the already-safe projection**

```python
def _reviews(listing):
    value = listing.get("public_reviews")
    return dict(value) if isinstance(value, Mapping) else {
        "rating_value": None,
        "rating_count": 0,
        "text_review_count": 0,
        "topic_mentions": (),
        "category_scores": (),
        "latest_reviews": (),
    }

# Add to present_listing return value:
"reviews": _reviews(listing),
```

- [ ] **Step 5: Add no-network proof**

Assert that public `listing`, `browse`, and `match` request methods continue to operate from a prepared snapshot while provider functions are patched to raise.

- [ ] **Step 6: Run integration tests**

Run: `python -m unittest tests.test_monthly_public_presentation tests.test_monthly_public_no_network -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add bot.py monthly_public/presentation.py tests/test_monthly_public_presentation.py tests/test_monthly_public_no_network.py
git commit -m "feat(monthly): attach reviews to cached listings"
```

### Task 4: Customer matcher and listing trust UI

**Files:**
- Modify: `monthly_public/static/monthly.js`
- Modify: `monthly_public/static/monthly.css`
- Modify: `tests/test_monthly_public_page.py`
- Modify: `tests/test_monthly_public_content.py`

- [ ] **Step 1: Add failing JavaScript/source contract tests**

```python
def test_price_priority_and_review_ui_are_present(self):
    source = Path("monthly_public/static/monthly.js").read_text(encoding="utf-8")
    self.assertIn('steps.concat(["residents", "sleeping", "price_priority", "dates", "flexibility"])', source)
    self.assertIn('track("price_priority_selected"', source)
    self.assertIn('track("review_section_view"', source)
    self.assertIn("function renderReviews", source)
```

- [ ] **Step 2: Run page tests**

Run: `python -m unittest tests.test_monthly_public_page tests.test_monthly_public_content -v`  
Expected: FAIL because the new matcher step and review UI are absent.

- [ ] **Step 3: Add approved bilingual copy and matcher step**

```javascript
pricePriorityTitle: "وش الأهم لك في ترتيب الخيارات؟",
pricePriorityHint: "هذا يغيّر ترتيب البيوت المناسبة فقط، ولا يغيّر السعر الرسمي.",
experiencePriority: "💎 أفضل تجربة",
valuePriority: "⚖️ أفضل توازن بين القيمة والسعر",
lowestPriority: "💰 الأقل سعرًا الذي يناسبني",
reviewsTitle: "تجارب ضيوف هذه الشقة",
latestReviews: "أحدث 10 مراجعات",
```

Add `price_priority` to `buildSteps`, `buildMatchRequest`, persisted state, listing query context, and the direct listing form with a default of `value` only when the customer did not arrive from the matcher.

- [ ] **Step 4: Render the review trust section**

```javascript
function renderReviews(listing) {
  const reviews = listing.reviews || {};
  const section = element("section", "reviews-section");
  section.appendChild(element("h2", "", copy("reviewsTitle")));
  // Render aggregate proof, topic mentions, and the latest review cards.
  // Use textContent through element(); never use innerHTML for review text.
  section.addEventListener("focusin", function once() {
    section.removeEventListener("focusin", once);
    track("review_section_view", { listing_id: String(listing.id) });
  });
  return section;
}
```

Display original-language labels and background translation labels from the payload. Clamp long text visually with an accessible show-more button. Do not alter the stored text.

- [ ] **Step 5: Add functional emojis and value framing**

Add emojis only to purpose and price-priority choice labels plus trust chips. Keep price, deposit, payment, license, and contract copy emoji-free. Add “what is included” context before the price CTA and fire `price_breakdown_open` only when the customer expands the full breakdown.

- [ ] **Step 6: Add responsive CSS**

```css
.review-summary { display:grid; grid-template-columns:minmax(8rem,.35fr) 1fr; gap:var(--space-4); }
.review-grid { display:grid; gap:var(--space-3); }
.review-card { border:1px solid var(--line); border-radius:var(--radius-lg); background:var(--surface); padding:var(--space-4); }
.review-text[aria-expanded="false"] { display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; overflow:hidden; }
@media (max-width: 720px) { .review-summary { grid-template-columns:1fr; } }
@media (prefers-reduced-motion: reduce) { .review-card, .choice { transition:none; } }
```

- [ ] **Step 7: Run page and content tests**

Run: `python -m unittest tests.test_monthly_public_page tests.test_monthly_public_content -v`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add monthly_public/static/monthly.js monthly_public/static/monthly.css tests/test_monthly_public_page.py tests/test_monthly_public_content.py
git commit -m "feat(monthly): add trust-first customer journey"
```

### Task 5: Analytics contract and funnel reporting

**Files:**
- Modify: `monthly_public/contracts.py`
- Modify: `monthly_public/analytics.py`
- Modify: `tests/test_monthly_public_contracts.py`
- Modify: `tests/test_monthly_public_analytics.py`

- [ ] **Step 1: Add failing event-contract tests**

```python
def test_new_trust_events_accept_only_safe_context(self):
    event = parse_event(public_event("review_section_view", {"listing_id": "1001"}))
    self.assertEqual(event["context"]["listing_id"], "1001")
    with self.assertRaises(ContractError):
        parse_event(public_event("review_section_view", {"review_text": "private"}))
```

- [ ] **Step 2: Run contract and analytics tests**

Run: `python -m unittest tests.test_monthly_public_contracts tests.test_monthly_public_analytics -v`  
Expected: FAIL because the new event names are unsupported.

- [ ] **Step 3: Extend allowlisted events and contexts**

Add `price_priority_selected`, `no_match`, `review_section_view`, and `price_breakdown_open` to `PUBLIC_EVENT_NAMES`. Allow `price_priority` only from `PRICE_PRIORITIES`. Keep review text, guest name, message content, email, and phone outside every public event contract.

- [ ] **Step 4: Extend funnel output**

```python
FUNNEL_ORDER = (
    "landing_view", "entry_route_choice", "matcher_start", "matcher_completion",
    "results_view", "listing_view", "review_section_view", "price_breakdown_open",
    "whatsapp_click", "lead_created", "team_response", "booked",
)
```

Add the new stages without changing existing lead lifecycle integrity or lost-reason controls.

- [ ] **Step 5: Run analytics tests**

Run: `python -m unittest tests.test_monthly_public_contracts tests.test_monthly_public_analytics -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add monthly_public/contracts.py monthly_public/analytics.py tests/test_monthly_public_contracts.py tests/test_monthly_public_analytics.py
git commit -m "feat(monthly): extend trust funnel analytics"
```

### Task 6: Operations review readiness

**Files:**
- Modify: `monthly_public/catalog_service.py`
- Modify: `monthly_public/static/monthly_ops.js`
- Modify: `monthly_public/static/monthly_ops.css`
- Modify: `tests/test_monthly_public_ops_workflow.py`
- Modify: `tests/test_monthly_public_ops_page.py`

- [ ] **Step 1: Write failing operations payload tests**

```python
def test_portfolio_reports_review_coverage_without_review_text(self):
    portfolio = service.portfolio()
    row = portfolio["listings"][0]
    self.assertEqual(row["review_count"], 16)
    self.assertTrue(row["review_ready"])
    self.assertNotIn("latest_reviews", row)
    self.assertEqual(portfolio["counts"]["review_covered"], 1)
```

- [ ] **Step 2: Run operations tests**

Run: `python -m unittest tests.test_monthly_public_ops_workflow tests.test_monthly_public_ops_page -v`  
Expected: FAIL because review readiness is absent.

- [ ] **Step 3: Add allowlisted readiness fields**

```python
reviews = publication.get("public_reviews") if isinstance(publication.get("public_reviews"), Mapping) else {}
review_count = int(reviews.get("rating_count") or 0)
row_payload.update({"review_count": review_count, "review_ready": review_count > 0})
counts["review_covered"] = sum(row["review_ready"] for row in listings)
```

The portfolio does not include review text or guest names. The individual authenticated listing payload may show the safe latest-ten projection for preview.

- [ ] **Step 4: Render review coverage and actions**

Add a review coverage card, a row chip, and a direct internal-preview link. Keep technical blocker codes translated to Arabic actions. Do not add an “approve anyway” bypass.

- [ ] **Step 5: Run operations tests**

Run: `python -m unittest tests.test_monthly_public_ops_workflow tests.test_monthly_public_ops_page -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add monthly_public/catalog_service.py monthly_public/static/monthly_ops.js monthly_public/static/monthly_ops.css tests/test_monthly_public_ops_workflow.py tests/test_monthly_public_ops_page.py
git commit -m "feat(monthly): show review readiness in ops"
```

### Task 7: Full verification and visual inspection

**Files:**
- Modify if defects are found: focused files from Tasks 1–6
- Create: `docs/monthly-conversion-trust-launch-readiness-2026-08-26.md`

- [ ] **Step 1: Run focused monthly tests**

Run: `python -m unittest discover -s tests -p 'test_monthly_public_*.py' -v`  
Expected: all tests PASS.

- [ ] **Step 2: Run syntax and static checks**

Run: `python -m py_compile bot.py monthly_public/*.py`  
Expected: exit 0.

Run: `node --check monthly_public/static/monthly.js`  
Expected: exit 0.

- [ ] **Step 3: Prove no public provider calls**

Run: `python -m unittest tests.test_monthly_public_no_network -v`  
Expected: all tests PASS with provider clients patched to fail.

- [ ] **Step 4: Run content scans**

Run: `rg -n -i 'up to 30%|maximum discount|أقصى خصم|خصم يصل|line-through|private_review|reservation_id|lorem ipsum' monthly_public`  
Expected: no public presentation hit; contract/privacy guards may contain field names only in tests or allowlist rejection code.

- [ ] **Step 5: Launch local preview and inspect**

Inspect Arabic and English at mobile and desktop widths for home, matcher, results, browse, a listing with ten reviews, a listing without reviews, missing price, stale calendar, missing WhatsApp, outside hours, and four-to-six months. Check keyboard focus, clipping, long text, image crops, sticky actions, and reduced motion.

- [ ] **Step 6: Run accessibility and performance checks**

Use the available browser audit tooling against the local pages. Record the observed accessibility issues, performance limitations, and any untestable external dependency in the launch-readiness report.

- [ ] **Step 7: Write the plain-English report**

The report lists passed checks, exact automated test totals, visual routes inspected, the missing WhatsApp number blocker, and a launch recommendation that distinguishes “safe to preview” from “production-ready.”

- [ ] **Step 8: Commit verified fixes and report**

```bash
git add monthly_public tests docs/monthly-conversion-trust-launch-readiness-2026-08-26.md bot.py
git commit -m "docs(monthly): report trust upgrade readiness"
```

### Task 8: Final review, push, and deployment verification

**Files:**
- No new product files unless verification finds a reproducible defect.

- [ ] **Step 1: Review intentional diff**

Run: `git status --short && git diff origin/main...HEAD --stat && git log --oneline origin/main..HEAD`  
Expected: only the approved spec, plan, monthly implementation, tests, and launch report are present; `.superpowers/` remains untracked and uncommitted.

- [ ] **Step 2: Run final verification once**

Run: `python -m unittest discover -s tests -p 'test_monthly_public_*.py' -v && python -m py_compile bot.py monthly_public/*.py && node --check monthly_public/static/monthly.js`  
Expected: exit 0.

- [ ] **Step 3: Push once**

Run: `git push origin main`  
Expected: the verified commits are accepted by the remote.

- [ ] **Step 4: Verify deployment and public behavior**

Check Railway deployment status and `https://oujares.com/monthly`. Confirm the shell loads, the release assets match the pushed commit, and incomplete homes remain excluded from public publication. Do not alter production data or configuration.

- [ ] **Step 5: Handoff**

Report the customer outcome, tests passed/failed, preview and public URLs, remaining external blockers, recommendation, commit list, and rollback by reverting the upgrade commits.
