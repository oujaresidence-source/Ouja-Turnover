# Monthly Showcase Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Ouja group real apartments under one permanent public URL and optionally apply one reversible, audited fixed monthly price only to customers entering through that group.

**Architecture:** Add strict showcase contracts, a revision-safe SQLite store, and a focused showcase service beside the existing monthly catalog service. The authenticated catalog manages groups; the public app resolves approved groups from cached state, signs group context, and applies a server-side fixed price without changing engine or Hostaway prices. Existing monthly pages remain the renderer, with one explicit showcase route and small UI additions.

**Tech Stack:** Python 3.9, aiohttp, SQLite, HMAC-SHA256, server-rendered HTML, vanilla JavaScript/CSS, `unittest`, Playwright browser checks.

---

## File Map

- Create `monthly_public/showcase_contracts.py`: strict group payload validation and signed public context.
- Create `monthly_public/showcase_store.py`: draft, approval, slug uniqueness, revision control, and append-only audit.
- Create `monthly_public/showcase_service.py`: staff workflows, public group resolution, membership, and health.
- Modify `monthly_public/pricing.py`: accept a server-resolved full-month fixed rate without touching source prices.
- Modify `monthly_public/routes.py`: public showcase endpoint, context-aware listing/lead pricing, and analytics.
- Modify `monthly_public/contracts.py`: allow the signed showcase context and controlled showcase event names.
- Modify `monthly_public/page.py`: add the explicit permanent showcase page route and safe embedded slug.
- Modify `monthly_public/static/monthly.js`: render the group page, preserve context, and show the fixed-price label.
- Modify `monthly_public/static/monthly.css`: group hero, chips, price notice, empty state, and responsive layout.
- Modify `monthly_public/catalog_page.py`: add the authenticated groups tab and group filter.
- Modify `monthly_public/static/monthly_catalog.js`: group editor, multi-select, approval, toggle, and filtering.
- Modify `monthly_public/static/monthly_catalog.css`: group management layout and mobile states.
- Modify `monthly_public/health.py`: expose group readiness and red blockers.
- Modify `bot.py`: instantiate services and register thin authenticated/public routes.
- Modify `monthly_public/local_preview.py`: allow a read-only group preview using explicit local fixture state.
- Create focused tests under `tests/test_monthly_showcase_*.py`; update existing route, page, analytics, lead, and no-network tests.
- Create `docs/monthly-showcase-launch-readiness.md`: plain-English verification and rollback record.

### Task 1: Strict showcase contracts and signed context

**Files:**
- Create: `monthly_public/showcase_contracts.py`
- Create: `tests/test_monthly_showcase_contracts.py`

- [ ] **Step 1: Write failing payload-contract tests**

```python
SECRET = b"s" * 32

def valid_group(**overrides):
    value = {
        "name_ar": "مساكن الملقا",
        "name_en": "Ouja Al Malqa Residences",
        "slug": "al-malqa-residences",
        "description_ar": "ثمان شقق عوجا في مبنى واحد.",
        "description_en": "Eight Ouja homes in one building.",
        "image_url": "https://images.example/building.jpg",
        "listing_ids": ["101"],
        "fixed_monthly_rate_sar": 12500,
        "fixed_price_enabled": True,
    }
    value.update(overrides)
    return value

class ShowcaseContractTest(unittest.TestCase):
    def test_normalizes_one_approved_group_without_losing_members(self):
        value = parse_showcase({
            "name_ar": "مساكن الملقا",
            "name_en": "Ouja Al Malqa Residences",
            "slug": "al-malqa-residences",
            "description_ar": "ثمان شقق عوجا في مبنى واحد.",
            "description_en": "Eight Ouja homes in one building.",
            "image_url": "https://images.example/building.jpg",
            "listing_ids": ["101", "102", "103"],
            "fixed_monthly_rate_sar": 12500,
            "fixed_price_enabled": True,
        }, known_listing_ids={"101", "102", "103"})
        self.assertEqual(value["listing_ids"], ["101", "102", "103"])
        self.assertEqual(value["fixed_monthly_rate_sar"], 12500)

    def test_rejects_unknown_duplicate_or_empty_membership(self):
        for members in ([], ["101", "101"], ["999"]):
            with self.subTest(members=members), self.assertRaises(ShowcaseContractError):
                parse_showcase(valid_group(listing_ids=members), {"101"})

    def test_fixed_price_is_required_only_when_enabled(self):
        self.assertIsNone(parse_showcase(
            valid_group(fixed_price_enabled=False, fixed_monthly_rate_sar=None), {"101"}
        )["fixed_monthly_rate_sar"])
        with self.assertRaises(ShowcaseContractError):
            parse_showcase(
                valid_group(fixed_price_enabled=True, fixed_monthly_rate_sar=None), {"101"}
            )
```

- [ ] **Step 2: Run the contract test and verify the red state**

Run: `python3 -m unittest tests.test_monthly_showcase_contracts -v`

Expected: FAIL because `monthly_public.showcase_contracts` does not exist.

- [ ] **Step 3: Implement strict group parsing**

```python
SHOWCASE_FIELDS = frozenset({
    "name_ar", "name_en", "slug", "description_ar", "description_en",
    "image_url", "listing_ids", "fixed_monthly_rate_sar", "fixed_price_enabled",
})
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

def parse_showcase(value, known_listing_ids):
    raw = _mapping(value, "showcase")
    _reject_unknown(raw, SHOWCASE_FIELDS)
    listing_ids = _listing_ids(raw.get("listing_ids"), known_listing_ids)
    enabled = _bool(raw.get("fixed_price_enabled"), "fixed_price_enabled")
    rate = _optional_integer(raw.get("fixed_monthly_rate_sar"), 1, 1_000_000)
    if enabled and rate is None:
        raise _error("fixed_monthly_rate_sar", "required", "أدخل السعر الشهري الثابت.", "Enter the fixed monthly price.")
    return {
        "name_ar": _language_text(raw.get("name_ar"), "name_ar", "ar", 180),
        "name_en": _language_text(raw.get("name_en"), "name_en", "en", 180),
        "slug": _slug(raw.get("slug")),
        "description_ar": _optional_language_text(raw.get("description_ar"), "description_ar", "ar", 500),
        "description_en": _optional_language_text(raw.get("description_en"), "description_en", "en", 500),
        "image_url": _optional_https_url(raw.get("image_url"), "image_url"),
        "listing_ids": listing_ids,
        "fixed_monthly_rate_sar": rate,
        "fixed_price_enabled": enabled,
    }
```

- [ ] **Step 4: Add failing signed-context tests**

```python
def test_context_contains_no_price_and_rejects_tampering(self):
    token = issue_showcase_context(SECRET, "showcase_ab12", 4)
    self.assertNotIn("12500", token)
    self.assertEqual(
        verify_showcase_context(token, SECRET),
        {"group_id": "showcase_ab12", "revision": 4},
    )
    with self.assertRaises(ShowcaseContextError):
        verify_showcase_context(token[:-1] + "x", SECRET)
```

- [ ] **Step 5: Implement the separate HMAC context**

```python
_CONTEXT = b"ouja-monthly-showcase:v1:"
_TOKEN_RE = re.compile(r"^sc_([A-Za-z0-9_-]{8,80})\.([0-9]{1,9})\.([A-Za-z0-9_-]{43})$")

def issue_showcase_context(secret, group_id, revision):
    body = "%s.%d" % (_group_id(group_id), _revision(revision))
    digest = hmac.new(_secret(secret), _CONTEXT + body.encode("ascii"), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return "sc_%s.%s" % (body, signature)

def verify_showcase_context(token, secret):
    match = _TOKEN_RE.fullmatch(str(token or ""))
    if not match:
        raise ShowcaseContextError("invalid showcase context")
    group_id, revision, supplied = match.groups()
    expected = issue_showcase_context(secret, group_id, int(revision)).rsplit(".", 1)[1]
    if not hmac.compare_digest(supplied, expected):
        raise ShowcaseContextError("invalid showcase signature")
    return {"group_id": group_id, "revision": int(revision)}
```

- [ ] **Step 6: Run tests and commit**

Run: `python3 -m unittest tests.test_monthly_showcase_contracts -v`

Expected: all contract and signature tests PASS.

Commit: `feat(monthly): add showcase contracts`

### Task 2: Revision-safe, non-destructive showcase storage

**Files:**
- Create: `monthly_public/showcase_store.py`
- Create: `tests/test_monthly_showcase_store.py`

- [ ] **Step 1: Write failing persistence tests**

```python
class ShowcaseStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ShowcaseStore(Path(self.tmp.name) / "showcases.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def _approve(self, group_id, value):
        draft = self.store.save_draft(group_id, value, 0, "faisal")
        return self.store.approve(group_id, draft["draft_revision"], "faisal")

    def test_draft_approval_and_toggle_preserve_price_and_members(self):
        group = valid_group(listing_ids=["101", "102"])
        draft = self.store.save_draft("showcase_a1", group, 0, "faisal")
        approved = self.store.approve("showcase_a1", draft["draft_revision"], "faisal")
        toggled = self.store.set_price_enabled(
            "showcase_a1", False, approved["approved_revision"], "faisal"
        )
        self.assertFalse(toggled["approved"]["fixed_price_enabled"])
        self.assertEqual(toggled["approved"]["fixed_monthly_rate_sar"], 12500)
        self.assertEqual(toggled["approved"]["listing_ids"], group["listing_ids"])

    def test_first_approved_slug_is_immutable_and_unique(self):
        self._approve("showcase_a1", valid_group(slug="one-building"))
        with self.assertRaises(ImmutableShowcaseSlug):
            self.store.save_draft("showcase_a1", valid_group(slug="renamed"), 1, "faisal")
        with self.assertRaises(DuplicateShowcaseSlug):
            self._approve("showcase_b2", valid_group(slug="one-building"))

    def test_store_has_no_delete_method_and_audit_is_append_only(self):
        self.assertFalse(hasattr(self.store, "delete"))
        self.assertEqual([row["action"] for row in self.store.audit("showcase_a1")], [
            "price_disabled", "approved", "draft_saved",
        ])
```

- [ ] **Step 2: Run the store test and verify the red state**

Run: `python3 -m unittest tests.test_monthly_showcase_store -v`

Expected: FAIL because `ShowcaseStore` is not implemented.

- [ ] **Step 3: Create the SQLite schema and record methods**

```sql
CREATE TABLE IF NOT EXISTS monthly_showcase_groups (
  group_id TEXT PRIMARY KEY,
  draft_slug TEXT,
  approved_slug TEXT UNIQUE,
  draft_json TEXT,
  approved_json TEXT,
  draft_revision INTEGER NOT NULL DEFAULT 0,
  approved_revision INTEGER NOT NULL DEFAULT 0,
  draft_updated_at TEXT,
  draft_updated_by TEXT,
  approved_at TEXT,
  approved_by TEXT
);
CREATE TABLE IF NOT EXISTS monthly_showcase_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id TEXT NOT NULL,
  action TEXT NOT NULL,
  revision INTEGER NOT NULL,
  changed_fields_json TEXT NOT NULL,
  actor TEXT NOT NULL,
  occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_monthly_showcase_audit
ON monthly_showcase_audit(group_id, id DESC);
```

Implement `record`, `list_records`, `by_approved_slug`, `save_draft`, `approve`,
`set_price_enabled`, and `audit` using short connections, `BEGIN IMMEDIATE`,
canonical JSON, expected revisions, and no hard-delete operation.

- [ ] **Step 4: Run store tests and commit**

Run: `python3 -m unittest tests.test_monthly_showcase_store -v`

Expected: all persistence, uniqueness, conflict, restart, and audit tests PASS.

Commit: `feat(monthly): store showcase groups`

### Task 3: Showcase service and truthful inventory membership

**Files:**
- Create: `monthly_public/showcase_service.py`
- Create: `tests/test_monthly_showcase_service.py`

- [ ] **Step 1: Write failing service tests**

```python
def published(listing_id):
    return PublicationResult(
        listing=MappingProxyType({"id": listing_id, "slug": "home-" + listing_id}),
        blockers=(), warnings=(), availability_status="confirmed",
        publishable=True, exact_match_eligible=True,
    )

def blocked(listing_id, code):
    return PublicationResult(
        listing=MappingProxyType({"id": listing_id, "slug": "home-" + listing_id}),
        blockers=(PublicationIssue(code=code, message_ar=code, message_en=code),),
        warnings=(), availability_status="confirmed",
        publishable=False, exact_match_eligible=False,
    )

def service_with(approved, results):
    store = FakeShowcaseStore("showcase_a1", approved)
    generation = SimpleNamespace(
        results=tuple(results.values()),
        published=tuple(row for row in results.values() if row.publishable),
    )
    return ShowcaseService(
        store=store,
        inventory_provider=lambda: {"listings": [{"id": key} for key in ("101", "102", "103")]},
        snapshot_provider=lambda: generation,
        session_secret=b"s" * 32,
        clock=lambda: NOW,
    )

def test_public_group_counts_only_current_published_members(self):
    service = service_with(
        approved=valid_group(listing_ids=["101", "102", "103"]),
        published={"101": published("101"), "103": published("103")},
    )
    public = service.public_by_slug("one-building", "ar")
    self.assertEqual(public["configured_count"], 3)
    self.assertEqual(public["eligible_count"], 2)
    self.assertEqual([row.listing["id"] for row in public["results"]], ["101", "103"])

def test_context_resolves_latest_approved_state_not_client_revision(self):
    token = service.context_for_slug("one-building")["context"]
    service.set_price_enabled("showcase_a1", False, revision=1, actor="faisal")
    resolved = service.resolve_context(token)
    self.assertFalse(resolved["group"]["fixed_price_enabled"])

def test_blocked_members_stay_in_staff_record(self):
    staff = service.group("showcase_a1")
    self.assertEqual(staff["configured_count"], 3)
    self.assertEqual(staff["blocked_listing_ids"], ["102"])

def test_active_group_price_satisfies_only_the_price_blocker(self):
    service = service_with(
        approved=valid_group(
            listing_ids=["101", "102", "103"],
            fixed_price_enabled=True,
        ),
        results={
            "101": published("101"),
            "102": blocked("102", "price_missing"),
            "103": blocked("103", "licence_missing"),
        },
    )
    public = service.public_by_slug("one-building", "ar")
    self.assertEqual([row.listing["id"] for row in public["results"]], ["101", "102"])
```

- [ ] **Step 2: Run the service tests and verify the red state**

Run: `python3 -m unittest tests.test_monthly_showcase_service -v`

Expected: FAIL because `ShowcaseService` is not implemented.

- [ ] **Step 3: Implement the service boundary**

```python
class ShowcaseService:
    def __init__(self, store, inventory_provider, snapshot_provider, session_secret, clock):
        self.store = store
        self.inventory_provider = inventory_provider
        self.snapshot_provider = snapshot_provider
        self.session_secret = session_secret
        self.clock = clock

    def public_by_slug(self, slug, lang="ar"):
        record = self.store.by_approved_slug(slug)
        if record is None:
            raise ShowcaseNotFound(slug)
        group = copy.deepcopy(record["approved"])
        eligible = self._eligible_by_id(group)
        results = tuple(eligible[lid] for lid in group["listing_ids"] if lid in eligible)
        return {
            "group_id": record["group_id"],
            "revision": record["approved_revision"],
            "group": group,
            "results": results,
            "configured_count": len(group["listing_ids"]),
            "eligible_count": len(results),
            "context": issue_showcase_context(
                self.session_secret, record["group_id"], record["approved_revision"]
            ),
        }
```

Add `create_draft`, `save_draft`, `approve`, `set_price_enabled`, `portfolio`,
`group`, `memberships`, `public_by_slug`, `resolve_context`, and `health`.
Generate group IDs server-side as `showcase_` plus 16 URL-safe characters. Resolve
listing IDs only from the cached inventory provider. Determine eligibility from
the current revalidated publication snapshot. An active approved fixed price may
remove only a `price_missing` blocker for its own group; every other blocker
remains enforced. Add `eligible_result(group, listing_id)` so listing, quote, and
lead requests use the same rule instead of the normal published-only lookup.

Add `present_showcase(public, lang)` in the same focused module. It returns only
the approved bilingual identity, fixed-price mode and amount, signed context,
truthful counts, and `present_listing(result, lang)` output for eligible results.

- [ ] **Step 4: Run service tests and commit**

Run: `python3 -m unittest tests.test_monthly_showcase_service -v`

Expected: all staff, public count, current revision, and blocker tests PASS.

Commit: `feat(monthly): add showcase service`

### Task 4: Server-resolved fixed monthly pricing

**Files:**
- Modify: `monthly_public/pricing.py`
- Create: `tests/test_monthly_showcase_pricing.py`

- [ ] **Step 1: Write failing fixed-price tests**

```python
NOW = dt.datetime(2026, 9, 1, 12, tzinfo=dt.timezone.utc)

def listing_with_request_quote():
    listing = valid_listing()
    listing["official_request_quotes"] = {
        "2026-09-01|2026-10-15": {
            "monthly_rate_sar": 14000,
            "stay_total_sar": 20500,
            "currency": "SAR",
            "source": "engine_verified",
            "verified_at": NOW.isoformat(),
        }
    }
    return listing

def test_fixed_rate_replaces_only_full_month_quote(self):
    listing = valid_listing()
    original = copy.deepcopy(listing["official_prices"])
    quote = quote_for(
        listing,
        {"move_in": "2026-09-01", "duration_months": 2},
        NOW,
        fixed_monthly_rate_sar=12500,
    )
    self.assertEqual(quote["monthly_rate_sar"], 12500)
    self.assertEqual(quote["stay_total_sar"], 25000)
    self.assertEqual(listing["official_prices"], original)

def test_fixed_rate_can_supply_the_only_missing_price(self):
    listing = valid_listing(official_prices={})
    quote = quote_for(
        listing,
        {"move_in": "2026-09-01", "duration_months": 1},
        NOW,
        fixed_monthly_rate_sar=12500,
    )
    self.assertEqual(quote["monthly_rate_sar"], 12500)

def test_fixed_rate_does_not_prorate_partial_months(self):
    listing = listing_with_request_quote()
    quote = quote_for(
        listing,
        {"move_in": "2026-09-01", "move_out": "2026-10-15"},
        NOW,
        fixed_monthly_rate_sar=12500,
    )
    self.assertEqual(quote["monthly_rate_sar"], 14000)

def test_four_month_fixed_quote_keeps_preliminary_warning(self):
    quote = quote_for(
        valid_listing(),
        {"move_in": "2026-09-01", "duration_months": 4},
        NOW,
        fixed_monthly_rate_sar=12500,
    )
    self.assertTrue(quote["preliminary_contract"])
    self.assertEqual(quote["preliminary_label_ar"], PRELIMINARY_AR)
```

- [ ] **Step 2: Run the pricing test and verify the red state**

Run: `python3 -m unittest tests.test_monthly_showcase_pricing -v`

Expected: FAIL because `quote_for` does not accept the server-side override.

- [ ] **Step 3: Add the narrow override argument**

```python
def quote_for(listing, request, now, *, fixed_monthly_rate_sar=None):
    # Existing request validation remains unchanged.
    if fixed_monthly_rate_sar is not None:
        if isinstance(fixed_monthly_rate_sar, bool) or not isinstance(fixed_monthly_rate_sar, (int, float)):
            return None
        if not 1 <= float(fixed_monthly_rate_sar) <= 1_000_000:
            return None
    # For duration_months only, the approved override supplies the monthly
    # amount before the normal official-price lookup.
    if months is not None and fixed_monthly_rate_sar is not None:
        price = {
            "monthly_rate_sar": fixed_monthly_rate_sar,
            "stay_total_sar": fixed_monthly_rate_sar * months,
        }
```

Do not mutate `listing`, `official_prices`, engine state, calendar state, or any
provider. Keep exact-date request quotes on their existing verified path.

- [ ] **Step 4: Run pricing tests and commit**

Run: `python3 -m unittest tests.test_monthly_showcase_pricing tests.test_monthly_public_pricing -v`

Expected: fixed-price and existing public pricing tests PASS.

Commit: `feat(monthly): price showcase stays`

### Task 5: Public API, listing context, leads, and analytics

**Files:**
- Modify: `monthly_public/contracts.py`
- Modify: `monthly_public/routes.py`
- Modify: `monthly_public/leads.py`
- Modify: `monthly_public/analytics.py`
- Create: `tests/test_monthly_showcase_routes.py`
- Modify: `tests/test_monthly_public_leads.py`
- Modify: `tests/test_monthly_public_analytics.py`

- [ ] **Step 1: Write failing public-route and tampering tests**

```python
def test_showcase_endpoint_returns_only_approved_eligible_members(self):
    result = app.showcase({"slug": "one-building", "lang": "ar"})
    self.assertTrue(result["ok"])
    self.assertEqual(result["showcase"]["eligible_count"], 2)
    self.assertNotIn("configured_listing_ids", result["showcase"])

def test_listing_uses_server_price_and_rejects_tampered_context(self):
    token = showcases.context_for_slug("one-building")["context"]
    good = app.listing(listing_request("101", showcase_context=token))
    self.assertEqual(good["quote"]["monthly_rate_sar"], 12500)
    bad = app.listing(listing_request("101", showcase_context=token + "x"))
    self.assertEqual(bad["error"]["code"], "invalid_showcase_context")

def test_context_cannot_price_a_non_member(self):
    result = app.listing(listing_request("999", showcase_context=token))
    self.assertEqual(result["error"]["code"], "showcase_listing_mismatch")
```

- [ ] **Step 2: Run route tests and verify the red state**

Run: `python3 -m unittest tests.test_monthly_showcase_routes -v`

Expected: FAIL because the public showcase API and context parsing are absent.

- [ ] **Step 3: Add controlled contracts and app methods**

Add `showcase_context` as an optional field to listing, quote, and lead request
contracts with a 256-character maximum. Add these public event names:

```python
PUBLIC_EVENT_NAMES += (
    "showcase_view",
    "showcase_listing_impression",
    "showcase_listing_view",
    "showcase_whatsapp_click",
)
TRUSTED_LIFECYCLE_EVENT_NAMES += ("showcase_lead_created",)
```

Extend `MonthlyPublicApp.__init__` with optional `showcase_service`. Implement:

```python
def showcase(self, value):
    request = parse_showcase_request(value)
    public = self.showcase_service.public_by_slug(request["slug"], request["lang"])
    return {"ok": True, "showcase": present_showcase(public, request["lang"])}

def _showcase_price(self, token, listing_id):
    if not token:
        return None, None
    resolved = self.showcase_service.resolve_context(token)
    if listing_id not in resolved["group"]["listing_ids"]:
        raise ContractError("showcase_context", "showcase_listing_mismatch", "الشقة ليست ضمن هذه المجموعة.", "The home is not in this showcase.")
    rate = resolved["group"].get("fixed_monthly_rate_sar") if resolved["group"].get("fixed_price_enabled") else None
    return resolved, rate
```

Call `_showcase_price` immediately before `quote_for` in listing and again in
lead creation. Never accept a client price. Add the resolved group ID, revision,
slug, and price mode to the lead record and prepared message; do not persist the
message body. Resolve a valid showcase context before the normal published-only
listing lookup and call `showcase_service.eligible_result(...)`; this lets the
approved group price satisfy only `price_missing`. Requests without showcase
context keep the existing publication behavior unchanged.

- [ ] **Step 4: Run lead and analytics tests**

Run: `python3 -m unittest tests.test_monthly_showcase_routes tests.test_monthly_public_leads tests.test_monthly_public_analytics -v`

Expected: all public, lead, privacy, and funnel tests PASS.

- [ ] **Step 5: Commit**

Commit: `feat(monthly): carry showcase context`

### Task 6: Permanent Arabic-first showcase page

**Files:**
- Modify: `monthly_public/page.py`
- Modify: `monthly_public/static/monthly.js`
- Modify: `monthly_public/static/monthly.css`
- Create: `tests/test_monthly_showcase_page.py`
- Modify: `tests/test_monthly_public_page.py`
- Modify: `tests/test_monthly_public_content.py`

- [ ] **Step 1: Write failing page-state and content tests**

```python
def test_explicit_showcase_route_precedes_listing_catchall(self):
    self.assertEqual(PAGE_ROUTES["/monthly/showcase/{showcase_slug}"], "showcase")
    html = render_monthly_page("showcase", showcase_slug="one-building")
    state = page_json(html)
    self.assertEqual(state["showcase_slug"], "one-building")

def test_page_has_no_discount_or_crossed_out_price_language(self):
    combined = JS_FILE.read_text("utf-8") + CSS_FILE.read_text("utf-8")
    for forbidden in ("up to 30%", "حتى 30%", "line-through"):
        self.assertNotIn(forbidden, combined)
```

- [ ] **Step 2: Run page tests and verify the red state**

Run: `python3 -m unittest tests.test_monthly_showcase_page -v`

Expected: FAIL because `showcase` is not a page route.

- [ ] **Step 3: Extend safe page state and route detection**

```python
PAGE_ROUTES = {
    "/monthly": "home",
    "/monthly/": "home",
    "/monthly/search": "browse",
    "/monthly/match": "match",
    "/monthly/showcase/{showcase_slug}": "showcase",
    "/monthly/id/{lid}": "listing",
    "/monthly/{slug}": "listing",
}
_ROUTES = frozenset({"home", "match", "browse", "listing", "showcase"})
```

Add a `showcase_slug` argument to `page_state` and `render_monthly_page`; accept
it only for the showcase route and validate it with the lowercase slug pattern.

- [ ] **Step 4: Render the group page in JavaScript**

Add `ENDPOINTS.showcase`, `renderShowcase`, and `showcaseHref`. The renderer must
show the approved name, optional description/image, truthful eligible count,
fixed-price label when active, original-price mode when inactive, and a calm
empty state. Every listing link carries only `sc=<signed context>`; never carry
an amount.

```javascript
function showcaseHref(listing, context) {
  const params = new URLSearchParams();
  if (context) params.set("sc", context);
  const target = listing.slug ? "/monthly/" + encodeURIComponent(listing.slug)
    : "/monthly/id/" + encodeURIComponent(listing.id);
  return target + (params.toString() ? "?" + params.toString() : "");
}
```

Preserve `sc` through language switching, quote refreshes, back navigation, and
WhatsApp lead creation. Add emoji only as restrained supporting labels, never as
replacement controls or unverified claims.

- [ ] **Step 5: Add responsive, accessible styling**

Add `.showcase-hero`, `.showcase-price-notice`, `.showcase-grid`,
`.showcase-chip`, and `.showcase-empty`. Use existing cream, green, gold,
Thmanyah typography, 44px minimum touch targets, visible focus, RTL/LTR logical
properties, and `prefers-reduced-motion` behavior.

- [ ] **Step 6: Run page tests and commit**

Run: `python3 -m unittest tests.test_monthly_showcase_page tests.test_monthly_public_page tests.test_monthly_public_content -v`

Expected: route, bilingual copy, context preservation, accessibility, and
forbidden-discount tests PASS.

Commit: `feat(monthly): add showcase page`

### Task 7: Group management and apartment filtering

**Files:**
- Modify: `monthly_public/catalog_page.py`
- Modify: `monthly_public/static/monthly_catalog.js`
- Modify: `monthly_public/static/monthly_catalog.css`
- Create: `tests/test_monthly_showcase_catalog.py`

- [ ] **Step 1: Write failing staff UI contract tests**

```python
def test_catalog_has_groups_tab_filter_and_editor(self):
    html = render_monthly_catalog_page()
    for element_id in (
        "tab-showcases", "showcases", "showcase-filter", "showcase-list",
        "showcase-form", "showcase-members", "showcase-price-enabled",
        "showcase-fixed-price", "approve-showcase",
    ):
        self.assertIn('id="%s"' % element_id, html)

def test_filter_matches_group_membership_without_duplicates(self):
    rows = run_js("filterListings", LISTINGS, {"showcase": "showcase_a1"}, MEMBERSHIPS)
    self.assertEqual([row["id"] for row in rows], ["101", "102"])
```

- [ ] **Step 2: Run staff UI tests and verify the red state**

Run: `python3 -m unittest tests.test_monthly_showcase_catalog -v`

Expected: FAIL because the groups tab and filter do not exist.

- [ ] **Step 3: Add the staff page structure**

Add the groups tab, list, editor form, apartment search, selected-member count,
published/blocked summary, fixed rate field, price-enabled switch, draft save,
preview, approval, and immediate price-mode action. Keep the existing apartment
survey unchanged.

- [ ] **Step 4: Add client behavior and API calls**

Implement these requests through the existing authenticated `api` wrapper:

```javascript
GET  /api/monthly/ops/showcases
POST /api/monthly/ops/showcases/draft
GET  /api/monthly/ops/showcase/{group_id}
POST /api/monthly/ops/showcase/{group_id}/draft
POST /api/monthly/ops/showcase/{group_id}/approve
POST /api/monthly/ops/showcase/{group_id}/price-mode
```

The price-mode action sends only `{enabled, revision}` and displays a final
confirmation immediately before changing public behavior. Render group chips in
apartment rows and add `showcase` to `currentFilters`. Preserve selected listing
IDs when search text changes.

- [ ] **Step 5: Add mobile and desktop styles**

Use the existing catalog tokens. Desktop uses a two-column group editor with a
sticky selected-members summary; mobile uses one column and a sticky save bar.
Use only existing ready, warning, blocked, and neutral status colors.

- [ ] **Step 6: Run staff UI tests and commit**

Run: `python3 -m unittest tests.test_monthly_showcase_catalog tests.test_monthly_catalog_page -v`

Expected: page, filter, multi-select, bilingual, and safe-toggle tests PASS.

Commit: `feat(monthly): manage showcase groups`

### Task 8: Thin bot adapters, route order, and health

**Files:**
- Modify: `bot.py`
- Modify: `monthly_public/health.py`
- Modify: `monthly_public/local_preview.py`
- Create: `tests/test_monthly_showcase_integration.py`
- Modify: `tests/test_monthly_public_no_network.py`
- Modify: `tests/test_monthly_public_health.py`

- [ ] **Step 1: Write failing wiring and no-network tests**

```python
def test_showcase_routes_are_registered_before_listing_catchall(self):
    routes = registered_monthly_routes()
    self.assertLess(
        routes.index(("GET", "/monthly/showcase/{showcase_slug}")),
        routes.index(("GET", "/monthly/{slug}")),
    )

def test_customer_showcase_handlers_make_no_provider_call(self):
    with provider_calls_forbidden():
        self.assertEqual(run(bot._api_monthly_showcase(request("one-building"))).status, 200)
        self.assertEqual(run(bot._api_monthly_v2_listing(request_with_context())).status, 200)

def test_missing_showcase_store_is_a_red_ops_blocker(self):
    health = health_payload(showcase={"configured": False, "write_probe": False})
    self.assertIn("showcase_store_unavailable", health["launch_blockers"])
```

- [ ] **Step 2: Run integration tests and verify the red state**

Run: `python3 -m unittest tests.test_monthly_showcase_integration -v`

Expected: FAIL because services and routes are not wired.

- [ ] **Step 3: Instantiate isolated services**

In the monthly optional import block, import showcase modules with closed
fallback values. When monthly is enabled, create:

```python
_monthly_showcase_store = _MonthlyShowcaseStore(
    _state_path("monthly_showcases.sqlite3")
)
_monthly_showcase_service = _MonthlyShowcaseService(
    store=_monthly_showcase_store,
    inventory_provider=_monthly_catalog_prefill_source,
    snapshot_provider=lambda: _monthly_public_snapshot.current if _monthly_public_snapshot else None,
    session_secret=_monthly_public_session_secret,
    clock=lambda: datetime.now(TZ),
)
_monthly_public_app.showcase_service = _monthly_showcase_service
```

Initialization failure must leave the public group route closed and report a red
ops blocker without affecting existing monthly pages.

- [ ] **Step 4: Add thin authenticated and public handlers**

Each handler authenticates through the existing monthly ops guard, parses JSON,
passes the staff actor, calls exactly one showcase service method, and translates
`ShowcaseContractError`, revision conflict, and not-found errors to stable JSON.
Register the explicit public page route before `/monthly/{slug}`.

- [ ] **Step 5: Extend health and local preview**

Add received/approved group counts, fixed-price enabled count, blocked members,
store write probe, and missing session-secret blocker. The local preview accepts
an optional in-memory approved group fixture and serves the same public route
without save, approve, toggle, lead, or external refresh endpoints.

- [ ] **Step 6: Run integration and no-network tests**

Run: `python3 -m unittest tests.test_monthly_showcase_integration tests.test_monthly_public_no_network tests.test_monthly_public_health tests.test_monthly_local_preview -v`

Expected: all route order, fail-closed, health, and no-provider-call tests PASS.

- [ ] **Step 7: Commit**

Commit: `feat(monthly): wire showcase groups`

### Task 9: End-to-end verification and visual polish

**Files:**
- Modify only files with a reproduced defect.
- Create: `docs/monthly-showcase-launch-readiness.md`

- [ ] **Step 1: Run focused showcase tests**

Run: `python3 -m unittest discover -s tests -p 'test_monthly_showcase*.py' -v`

Expected: all showcase tests PASS with zero failures and zero errors.

- [ ] **Step 2: Run the complete monthly suite**

Run: `PYTHONPYCACHEPREFIX=/private/tmp/ouja-pycache python3 -m unittest discover -s tests -p 'test_monthly*.py'`

Expected: all monthly tests PASS with zero failures and zero errors.

- [ ] **Step 3: Run static and source-boundary checks**

Run:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/ouja-pycache python3 -m py_compile bot.py monthly_public/showcase_contracts.py monthly_public/showcase_store.py monthly_public/showcase_service.py monthly_public/pricing.py monthly_public/routes.py monthly_public/page.py
node --check monthly_public/static/monthly.js
node --check monthly_public/static/monthly_catalog.js
git diff --check
rg -n "Hostaway|pricing provider|requests\.|aiohttp\.ClientSession" monthly_public/showcase_*.py monthly_public/routes.py
rg -n -i "up to 30%|حتى 30%|line-through|maximum discount|خصم" monthly_public tests/test_monthly_showcase_*.py
```

Expected: compilation and JavaScript checks exit 0; diff check is clean; source
review confirms public handlers read only cached services; forbidden discount
language is absent from the customer UI.

- [ ] **Step 4: Launch the read-only local preview with real Ouja public data**

Run:

```bash
python3 -m monthly_public.local_preview --source /private/tmp/ouja-stay-search-20260826.json --port 8766
```

Expected: loopback preview serves the approved showcase fixture and current real
public apartment rows without any write or provider route.

- [ ] **Step 5: Inspect Arabic and English desktop journeys**

At 1440×900 verify: groups tab creation and multi-select; apartment group filter;
public group URL; fixed-price label; listing page; one-, two-, and four-month
quotes; WhatsApp preview; price disabled fallback; blocked-member omission;
empty group state; English switch; visible focus; no clipping or layout shift.

- [ ] **Step 6: Inspect Arabic and English mobile journeys**

At 390×844 verify the same journeys plus sticky actions, 44px touch targets,
keyboard navigation, RTL direction, image quality, no horizontal overflow, and
back navigation preserving the signed group context.

- [ ] **Step 7: Run accessibility and performance checks**

Run Lighthouse or the available equivalent against the group page at mobile and
desktop. Record accessibility violations, first contentful paint, largest
contentful paint, cumulative layout shift, and total transferred assets. Fix
only reproduced defects and rerun the affected focused tests.

- [ ] **Step 8: Write the launch-readiness report**

Record passed checks, exact passed/failed counts, preview URL, current blockers,
data preservation proof, no-provider-call proof, and the rollback commit. State
that the feature is pushed but not live until Railway deployment is directly
verified.

- [ ] **Step 9: Commit verified polish and report**

Commit: `docs(monthly): report showcase readiness`

### Task 10: Final integration and push

**Files:**
- No new product files unless verification finds a reproducible defect.

- [ ] **Step 1: Fetch and integrate concurrent remote work safely**

Run:

```bash
git fetch origin main
git rebase origin/main
```

Expected: the showcase commits replay without overwriting unrelated changes. If
a conflict occurs, resolve only overlapping monthly lines, then rerun Task 9.

- [ ] **Step 2: Re-run the complete monthly suite after integration**

Run: `PYTHONPYCACHEPREFIX=/private/tmp/ouja-pycache python3 -m unittest discover -s tests -p 'test_monthly*.py'`

Expected: all monthly tests PASS with zero failures and zero errors.

- [ ] **Step 3: Verify intentional version-control scope**

Run:

```bash
git status --short
git log --oneline origin/main..HEAD
git diff origin/main..HEAD --check
```

Expected: only showcase code, tests, and documents are committed; no secrets,
database files, caches, test output, source data, or `.superpowers/` files are
included.

- [ ] **Step 4: Push once and verify the remote commit**

Run:

```bash
git push
git rev-parse HEAD
git rev-parse origin/main
```

Expected: push succeeds and both commit hashes match.

- [ ] **Step 5: Verify deployment without changing production data**

Read the live page and new static/API routes. Confirm the deployed asset version
and that the permanent showcase route returns the expected safe empty/not-found
state before any real group is approved. Do not create a production group or
change a live price without explicit approval.
