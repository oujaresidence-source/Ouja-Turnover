# «لقّطني» — Stay Match quiz (`/stay/match`) — design

Date: 2026-07-22
Status: approved (owner said GO 2026-07-22), not yet implemented
Owner-facing name: المطابقة / «محتار؟»

---

## 1. Problem

The `/stay` landing asks a guest to answer four things before they see a single
apartment: check-in, check-out, guest count, **and a neighborhood picked from a
dropdown built off the 85-entry `RIYADH_NEIGHBORHOODS` registry**
(`bot.py` `viewLanding`).

Two concrete failures follow from that form:

1. **The neighborhood dropdown is a geography exam.** A guest from Jeddah,
   Dammam, Kuwait or abroad cannot answer "الملقا or النرجس؟". They can answer
   "I want to be near the Boulevard". We ask the question they cannot answer and
   never ask the one they can.

2. **The search is an AND filter, so being specific is punished.** `_gw_search`
   requires a unit to carry *every* selected tag (`if not all(t in _tk for t in
   tag_list): continue`). The reward for engaging with the filters is the empty
   state `ما لقينا وحدات بنفس الاختيارات` — a dead end at the highest-intent
   moment on the site.

## 2. The core idea

> Search **filters** and can return zero. The quiz **scores** and can never
> return zero.

The quiz is not a shortcut around the search form. It is a different engine with
different semantics, sharing the same inventory. Everything in this spec follows
from that one sentence.

## 3. Scope of v1

In scope:

- New route `/stay/match`, rendered as a fourth view inside the existing
  `STAY_HTML` SPA.
- Four-screen quiz (~10 seconds on a phone).
- Pure scoring engine in a new `match/` package, TDD-locked.
- Proximity scoring via haversine to a curated POI table, with a
  neighborhood-centroid fallback.
- Scored results page: top 3 + «قريبة كمان», each card carrying computed
  reasons and one honest tradeoff.
- Entry points: landing page button, zero-results state on `/stay/search`.
- Analytics events through the existing `/api/stay/event` pipeline.
- Dashboard panel: completion funnel + unmet-demand table.

Explicitly out of scope for v1:

- WhatsApp opt-in capture at the end of the quiz (designed for, built in v2).
- Any write to Hostaway. This feature is strictly read-only.
- English UI. The quiz ships Arabic-only, matching `/stay`, which is
  Arabic-only today.

## 4. Placement decisions (owner-approved)

| Decision | Chosen | Rejected alternative |
| --- | --- | --- |
| Where it lives | Own route `/stay/match` | Overlay on `/stay` (not shareable, not a campaign destination) |
| Where it ends | Own scored results view | Redirect into `/stay/search` (re-inherits the zero-results dead end, loses reasoning) |
| Budget question | Included, with live price bands | Omitting it (it is the "calculator" the owner asked for) |
| Proximity | Included, with neighborhood-centroid fallback | Coords-only (silently drops units); zone-grouping only (loses the best signal) |

`/stay/match` being its own URL is what lets Musaed send it in a WhatsApp
reply, and what lets it be a TikTok-bio and ad destination.

## 5. The four questions

Design rule: **if an answer does not change the ranking, the question is cut.**
All four change the ranking.

### Q1 — «مين معك؟»

Party shape, not a raw number. Options: `أنا بس` · `أنا وشريكي` ·
`عائلة وأطفال` · `شلة أصدقاء` · `سفر عمل`.

Yields headcount hint + bedroom expectation + audience weighting in one tap.
Followed by a small +/− stepper for the exact count (defaulted from the shape).

### Q2 — «كيف تبون تنامون؟»

**Conditional: shown only when party size >= 3.**

Options: `غرفة وحدة تكفينا` · `غرفة لكل ثنين` · `كل واحد غرفته`.

Maps to `required_bedrooms`. This is the highest-signal question in the quiz:
`bedroomsNumber` is the cleanest field Hostaway gives us, and five people in one
bedroom versus five people in three bedrooms is completely different inventory.
No competitor search box asks this.

### Q3 — «وش جايبك الرياض؟»

Options: `البوليفارد وموسم الرياض` · `عمل واجتماعات` · `علاج` · `زيارة أهل` ·
`تسوق وسياحة` · `بس أبي أرتاح`.

Drives both the POI selection for proximity scoring and the amenity weighting
(work → workspace/wifi; family → kitchen/washer; rest → pool/balcony).
Replaces the neighborhood dropdown with a question every guest can answer.

### Q4 — dates + budget band

Dates reuse the same validation as the landing form (`validateDates`, and
server-side `_gw_valid_dates`). Budget is a slider whose labels are derived from
our own calendar medians, not invented ranges.

Concretely: `/api/stay/config` gains a `price_bands` object holding the p25,
median and p75 nightly price across visible units, computed from `price_base`
and cached on the same TTL as the rest of the guest-site config. The slider
renders three labelled stops from those percentiles
(`اقتصادي` / `متوسط` / `مميز`) rather than hardcoded SAR figures, so the bands
track real inventory as pricing changes. If `price_bands` is missing or the
sample is too thin (fewer than 5 priced units), the budget screen is skipped
entirely rather than showing invented numbers — budget then scores neutral for
every unit.

### The علاج register

When Q3 = `علاج`, the results view switches tone: no celebratory copy, no
emoji-led header, no upsell strip. It leads with distance to the medical
facility and quiet check-in. Someone booking near King Faisal Specialist is
having the worst week of their year, and the default celebratory register is
actively wrong for them. This is a deliberate, tested copy branch, not a
nice-to-have.

## 6. Engine

Location: `match/engine.py`. Pure and deterministic — no I/O, no network, no
clock reads. Mirrors the `schedule/engine.py` pattern already trusted in this
repo.

Signature:

```
score(answers: dict, units: list[dict], geo: dict, poi_table: dict) -> list[dict]
```

`units` are the public listing dicts already produced by `_gw_listing_public`.
The engine never calls Hostaway itself; `bot.py` supplies units, availability
and prices.

### Hard gates

Only physically-true constraints eliminate a unit:

1. `capacity >= party_size`
2. availability for the requested dates, when dates were given

That is the complete list.

### Soft scoring

| Signal | Weight | Source field |
| --- | --- | --- |
| Bedroom fit | 30 | `beds` vs `required_bedrooms` from Q1+Q2 |
| Proximity | 25 | coords → haversine → POI implied by Q3 |
| Budget fit | 20 | live nightly price vs Q4 band |
| Purpose amenities | 15 | `amenities` vs Q3 |
| Quality | 10 | `rating` + `reviews_count`, Bayesian-smoothed |

Bedroom fit: exact match scores full. **Over-provisioned scores slightly lower**
(the guest pays for space they said they don't need). Under-provisioned takes a
steep penalty but is never eliminated — it surfaces with a tradeoff string.

Quality must use Bayesian smoothing toward the portfolio mean. A raw average
lets 5.0★ from 3 reviews outrank 4.8★ from 90, which would put barely-reviewed
units at the top of every quiz result.

Failing a soft signal lowers the score. It never removes the unit. This is what
makes a zero-result response structurally impossible.

### Reasons and tradeoffs

Each scoring component emits, alongside its score, either a **reason** (when it
scored well) or a **tradeoff** (when it scored poorly). Every string contains
the real computed number:

- `٣ غرف نوم — كل واحد له غرفته`
- `١٢ دقيقة عن البوليفارد`
- `٤.٩ ★ من ٦٧ تقييم`
- `أغلى ١٥٠ ريال بالليلة من الميزانية اللي حطيتها`

A result card renders the top 2–3 reasons and **the single largest tradeoff**.
Three cards that all look perfect read as a machine; one card that admits a
tradeoff reads as someone who knows the units. This is also the primary defense
against the whole feature feeling AI-generated.

When the top score falls below a confidence threshold, the results header states
that honestly (`ما عندنا وحدة تطابق كل شي، هذي الأقرب`) rather than presenting a
weak match as a strong one.

### Locked invariants (`tests/test_match_engine.py`)

Written and passing **before** any UI code:

1. Never returns zero results when at least one unit **passes the hard gates**.
2. Capacity gate is absolute — never recommends a unit that cannot physically
   fit the party.

   Invariants 1 and 2 are in tension, and the resolution matters. A party of 20
   against a portfolio whose largest unit sleeps 8 is a genuine physical
   impossibility, and it is the **only** legitimate zero. The engine returns it
   as a distinct `impossible: True` state carrying `max_capacity`, and the UI
   says so plainly — «أكبر وحدة عندنا تستوعب ٨ ضيوف» — rather than showing a
   generic "no results" screen. Every other zero is a bug.
3. Exact bedroom match outranks over-provisioned, all else equal.
4. Every returned unit carries at least one reason.
5. A unit failing a soft criterion still appears, carrying a tradeoff string.
6. Deterministic — identical input yields identical order, with a stable
   tiebreak on unit id.
7. Proximity falls back to neighborhood centroid when coords are missing, and
   is never null.
8. 5.0★ with 3 reviews ranks below 4.8★ with 90 reviews.

## 7. Proximity

Location: `match/poi.py`.

Coordinates come from the already-cached `_elite_geo_points` path
(`bot.py:47436`), which resolves per-listing lat/lng from the in-house guide DB
by name match. No new data source, no new network call.

POI table (~10, hand-curated, owner-verifiable):
Boulevard City / موسم الرياض, KAFD, King Khalid International Airport,
Diriyah, King Fahad Medical City, King Faisal Specialist Hospital,
King Saud Medical City, Riyadh Front, the university cluster,
the exhibition/conference centre.

Distance is haversine, surfaced to the guest as approximate drive minutes.

**Fallback:** any unit whose name does not match a guide record falls back to a
centroid for its assigned `neighborhood` key. A `NEIGHBOURHOOD_CENTROIDS` table
covers the neighborhoods that actually hold units. Proximity is therefore never
null, satisfying invariant 7.

**Unverified assumption:** guide-coordinate coverage across our units cannot be
measured from a local checkout — the guide DB lives on the Railway volume. The
first implementation step is a coverage check on Railway. If coverage is thin,
the centroid fallback carries more weight than planned; the feature still works,
with less precise distances.

Privacy: `_elite_geo_points` already applies stable per-listing jitter (~330m)
plus rounding before exposing coordinates publicly. The quiz reuses that same
approximation and never exposes an exact building location.

## 8. UI

A fourth view inside `STAY_HTML`, dispatched alongside `viewLanding` /
`viewSearch` / `viewListing` (`bot.py:46269`):

```
else if(path==='/stay/match'){viewMatch();}
```

This inherits the header, fonts, design tokens, `track()` analytics and the
existing `card()` renderer with no design drift and no new stylesheet.

Motion: one question per screen, forward/back with a short horizontal
transform+opacity transition (<300ms, `cubic-bezier(0.23,1,0.32,1)`), a progress
indicator, and a `prefers-reduced-motion` crossfade alternative. Results reveal
must enhance an already-visible default — content is never gated behind a
class-triggered transition.

Entry points:

1. Landing, directly under the search form: «محتار؟ جاوبنا بأربع أسئلة — ١٠ ثواني».
   (Not "٣ أسئلة": Q2 is conditional, so a solo or couple traveller sees three
   screens and a group sees four. The copy must not promise a count the flow
   can exceed.)
2. The `/stay/search` zero-results state, replacing the current dead end.
3. The bare `/stay/match` link, for Musaed, WhatsApp, TikTok bio and ads.

Answers are held in the URL query string so a partially-completed quiz is
back-button-safe and shareable, consistent with how `/stay/search` already
carries its state.

## 9. Server surface

| Route | Auth | Purpose |
| --- | --- | --- |
| `GET /stay/match` | public | renders `STAY_HTML` with route `match` |
| `GET /api/stay/match` | public | answers in query → scored results JSON |

**Route-order footgun:** `/stay/{slug}` is a catch-all registered at
`bot.py:49081`. aiohttp matches in registration order, so `/stay/match` **must**
be registered with the specific routes near `bot.py:49059`. Registered after the
catch-all, it is swallowed as a slug lookup and 404s.

`GET /api/stay/match` reuses `_gw_visible_snaps` for inventory and
`unit_availability_price` for live availability and pricing, then delegates
ranking to `match.engine.score`. It performs no Hostaway writes.

## 10. Analytics and the owner's payoff

Events through the existing `/api/stay/event` pipeline:
`match_start`, `match_answer` (with question id), `match_abandon`,
`match_results` (with top score), `match_click` (with rank).

Dashboard panel `المطابقة` in the guest-site tab:

- **Completion funnel** — per question, showing exactly where people drop.
- **Unmet-demand table** — the answer combinations that produced only weak
  matches. For example: *"31% of guests wanting 3 bedrooms near the Boulevard
  left with a top score under threshold."*

The unmet-demand table is the highest-value output of this feature. It converts
guest intent we currently cannot see into a leasing, pricing and acquisition
input. The conversion lift is real, but this report is worth more.

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| Guide-coordinate coverage unknown | Coverage check is implementation step 1; centroid fallback guarantees non-null proximity |
| `/stay/match` swallowed by `/stay/{slug}` | Register before the catch-all; assert with a route test |
| Broken JS kills the whole `/stay` SPA | esprima-parse every `STAY_HTML` script block, per the repo verification routine |
| Quiz cannibalises the working search | Quiz is additive; the search form is unchanged and remains the default path |
| Scoring weights feel wrong on live data | Weights live in one dict in `match/engine.py`, tunable without touching UI or tests |

Lower risk than the dashboard: `STAY_HTML` is a **raw** string (`r"""` at
`bot.py:45908`), unlike `DASHBOARD_HTML`. The backslash-escape trap that has
twice killed dashboard login does not apply to this surface. esprima parsing is
still required.

## 12. Verification

Standard repo routine, plus:

```
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py match/*.py
python3 -m unittest discover -s tests -p "test_*.py"
```

Plus, specific to this feature:

- esprima-parse every `<script>` block of the served `STAY_HTML`.
- Synthetic-data logic test: feed fabricated units through `match.engine.score`
  and assert the ranking, before trusting it against live inventory.
- Manual pass at 375px width, and with `prefers-reduced-motion` enabled.

## 13. Build order

1. Guide-coordinate coverage check on Railway.
2. `match/poi.py` + tests (haversine, centroid fallback).
3. `match/engine.py` + `tests/test_match_engine.py` — all eight invariants green
   before any UI exists.
4. `GET /api/stay/match` wired to the engine; route-order test.
5. `viewMatch()` in `STAY_HTML`; esprima gate.
6. Entry points on the landing and the zero-results state.
7. Analytics events.
8. Dashboard `المطابقة` panel.
