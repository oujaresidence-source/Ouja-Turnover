# Stay Match («لقّطني») Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/stay/match`, a four-screen Arabic quiz on the guest site that *ranks* Ouja apartments by fit instead of filtering them, so a guest can never hit a zero-results dead end.

**Architecture:** A new `match/` package holds a pure, deterministic scoring engine (`engine.py`) and a proximity table (`poi.py`) with no I/O — mirroring the `schedule/engine.py` pattern already trusted in this repo. `bot.py` supplies inventory, availability and coordinates, then delegates ranking. The UI is a fourth view inside the existing `STAY_HTML` SPA, not a new page, so it inherits the header, design tokens, analytics and card renderer.

**Tech Stack:** Python 3 stdlib only (no new dependencies), aiohttp routes in `bot.py`, vanilla JS inside `STAY_HTML`, `unittest` for tests.

**Spec:** `docs/superpowers/specs/2026-07-22-stay-match-design.md`

---

## Context an engineer needs before starting

Read these before Task 1. They are the traps this codebase has actually been bitten by.

1. **`bot.py` is ~56,000 lines.** Make minimal, targeted edits. After any edit, re-read the surrounding code before the next edit — never edit from memory.
2. **`STAY_HTML` is a RAW string** (`r"""` at `bot.py:45908`). Unlike `DASHBOARD_HTML`, backslashes are safe here. You may write `\n` in JS string literals. Do **not** copy the `String.fromCharCode(10)` workaround from the dashboard — it is not needed on this surface.
3. **Route order matters.** `/stay/{slug}` is a catch-all at `bot.py:49081`. Any new `/stay/*` route registered *after* it is swallowed as a slug lookup and 404s. Register `/stay/match` next to `/stay/search` at `bot.py:49059`.
4. **There is no pytest here.** Tests run with `python3 -m unittest discover -s tests -p "test_*.py"`.
5. **Verification routine** (run before claiming any task done):
   ```
   rm -rf __pycache__
   python3 -W error::SyntaxWarning -m py_compile bot.py
   python3 -m pyflakes bot.py match/*.py     # ignore "imported but unused"
   node --check finance/static/erp.js
   python3 -m unittest discover -s tests -p "test_*.py"
   ```
6. **This feature is strictly read-only.** It never writes to Hostaway.

### Existing functions you will call (do not reimplement)

| Function | Location | Returns |
| --- | --- | --- |
| `_gw_visible_snaps()` | `bot.py:45762` | `[(snap, override), ...]` for publicly visible units |
| `_gw_listing_public(snap, ov)` | `bot.py:45645` | public dict: `id, slug, name_ar, beds, baths, capacity, area, neighborhood, amenities, rating, reviews_count, price_base, cover, ...` |
| `unit_availability_price(id, ci, co)` | `bot.py:6109` | `{available, nights, total, avg}` or `None` |
| `_gw_valid_dates(ci, co)` | `bot.py:45455` | bool — checkout strictly after checkin |
| `_elite_geo_refresh()` / `_elite_geo_cache` | `bot.py:47424` | cached `{normalized_name: (lat, lng)}` |
| `_elite_geo_norm(s)` | `bot.py:47388` | normalized name key for the above |
| `_gw_track(ev)` | `bot.py:45869` | records a guest-site analytics event |
| `_json(obj, status=200)` | `bot.py` | aiohttp JSON response |

---

## File Structure

| File | Responsibility |
| --- | --- |
| `match/__init__.py` (create) | Package marker; re-exports `score`. |
| `match/poi.py` (create) | POI table, neighborhood centroids, haversine, `resolve_point`, `minutes_to`. Pure. |
| `match/engine.py` (create) | `score()` — hard gates, weighted scoring, reasons/tradeoffs. Pure. No I/O, no clock. |
| `tests/test_match_poi.py` (create) | Distance math + centroid fallback. |
| `tests/test_match_engine.py` (create) | The eight locked invariants. |
| `bot.py` (modify) | `price_bands` in config; `/api/stay/match` handler; route registration; `viewMatch()` in `STAY_HTML`; event whitelist; dashboard panel. |

---

## Data contract (referenced by every task)

**`answers` dict** — produced by the UI, consumed by `engine.score`:

```python
{
  "party_size": 4,            # int >= 1
  "sleep_pref": "pairs",      # "together" | "pairs" | "each" | None (None when party_size < 3)
  "purpose": "boulevard",     # key from match.poi.PURPOSE_POI, or "rest"/"family" (no POI)
  "budget_max": 900,          # int SAR per night, or None if the budget screen was skipped
  "check_in": "2026-08-01",   # str or None
  "check_out": "2026-08-04",  # str or None
}
```

**`unit` dict** — whatever `_gw_listing_public` returns, optionally enriched by `bot.py` with
`est_avg` (int nightly), `est_total`, `nights`, `available`.

**`score()` return**:

```python
{
  "top": [scored_unit, ...],       # up to `top` items, best first
  "near": [scored_unit, ...],      # next few, best first
  "confident": True,               # False when the best score is below CONFIDENCE_FLOOR
  "impossible": False,             # True only when NO unit can physically fit the party
  "max_capacity": 8,               # largest capacity in inventory (for the impossible copy)
}
```

Each `scored_unit` is the input unit dict plus:
`match_score` (int 0-100), `reasons` (list of Arabic strings), `tradeoff` (Arabic string or `None`).

---

## Task 1: POI table and distance math

**Files:**
- Create: `match/__init__.py`
- Create: `match/poi.py`
- Test: `tests/test_match_poi.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_match_poi.py`:

```python
import unittest
from match import poi


class TestHaversine(unittest.TestCase):
    def test_zero_distance_for_same_point(self):
        self.assertEqual(poi.haversine_km((24.7, 46.7), (24.7, 46.7)), 0.0)

    def test_known_riyadh_distance(self):
        # Kingdom Centre -> Boulevard City, roughly 11 km apart.
        d = poi.haversine_km((24.7114, 46.6745), (24.7660, 46.6210))
        self.assertGreater(d, 7.0)
        self.assertLess(d, 15.0)

    def test_symmetric(self):
        a, b = (24.71, 46.67), (24.80, 46.60)
        self.assertAlmostEqual(poi.haversine_km(a, b), poi.haversine_km(b, a), places=6)


class TestResolvePoint(unittest.TestCase):
    def test_prefers_exact_coords(self):
        unit = {"id": 1, "neighborhood": "al_malqa"}
        pt = poi.resolve_point(unit, {1: (24.80, 46.60)})
        self.assertEqual(pt, (24.80, 46.60))

    def test_falls_back_to_neighborhood_centroid(self):
        unit = {"id": 2, "neighborhood": "al_malqa"}
        pt = poi.resolve_point(unit, {})
        self.assertIsNotNone(pt)
        self.assertEqual(pt, poi.NEIGHBOURHOOD_CENTROIDS["al_malqa"])

    def test_returns_none_when_nothing_known(self):
        self.assertIsNone(poi.resolve_point({"id": 3, "neighborhood": ""}, {}))


class TestMinutes(unittest.TestCase):
    def test_minutes_scale_with_distance(self):
        self.assertLess(poi.minutes_to(2.0), poi.minutes_to(20.0))

    def test_minutes_is_positive_int(self):
        m = poi.minutes_to(5.0)
        self.assertIsInstance(m, int)
        self.assertGreater(m, 0)


class TestPurposeMapping(unittest.TestCase):
    def test_boulevard_purpose_maps_to_a_poi(self):
        self.assertIn("boulevard", poi.PURPOSE_POI)
        key = poi.PURPOSE_POI["boulevard"]
        self.assertIn(key, poi.POIS)

    def test_rest_purpose_has_no_poi(self):
        self.assertIsNone(poi.PURPOSE_POI.get("rest"))

    def test_every_mapped_poi_exists(self):
        for purpose, key in poi.PURPOSE_POI.items():
            if key is not None:
                self.assertIn(key, poi.POIS, f"{purpose} -> {key} missing from POIS")

    def test_every_centroid_key_is_a_real_neighborhood(self):
        import bot
        valid = {k for (k, _ar, _en) in bot.RIYADH_NEIGHBORHOODS}
        for key in poi.NEIGHBOURHOOD_CENTROIDS:
            self.assertIn(key, valid, f"{key} is not in RIYADH_NEIGHBORHOODS")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_poi -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'match'`

- [ ] **Step 3: Write the implementation**

Create `match/__init__.py`:

```python
"""Stay Match — pure scoring engine for the /stay/match guest quiz.

Nothing in this package performs I/O, network calls, or clock reads. bot.py
supplies inventory, availability, prices and coordinates; this package only
ranks. That keeps the whole thing unit-testable with fabricated data.
"""

from .engine import score  # noqa: F401
```

Create `match/poi.py`:

```python
"""Proximity data and math for Stay Match. Pure — no I/O, no network.

Coordinates for POIs are approximate landmark centres, accurate enough to rank
units by "which is closer to the Boulevard", which is all we claim.
"""

import math

# ---- Points of interest a guest actually names when asked why they're in Riyadh.
# (ar, en, lat, lng). Keep this list short and owner-verifiable.
POIS = {
    "boulevard":  ("بوليفارد سيتي وموسم الرياض", "Boulevard City", 24.7660, 46.6210),
    "kafd":       ("المركز المالي (كافد)", "KAFD", 24.7649, 46.6408),
    "airport":    ("مطار الملك خالد", "King Khalid Airport", 24.9576, 46.6988),
    "diriyah":    ("الدرعية", "Diriyah", 24.7370, 46.5760),
    "riyadh_front": ("واجهة الرياض", "Riyadh Front", 24.8290, 46.7090),
    "expo":       ("مركز المعارض والمؤتمرات", "Exhibition & Conference Centre", 24.7720, 46.7360),
    "kfmc":       ("مدينة الملك فهد الطبية", "King Fahad Medical City", 24.6890, 46.7100),
    "kfsh":       ("مستشفى الملك فيصل التخصصي", "King Faisal Specialist Hospital", 24.7040, 46.6580),
    "ksmc":       ("مدينة الملك سعود الطبية", "King Saud Medical City", 24.6420, 46.7130),
    "ksu":        ("جامعة الملك سعود", "King Saud University", 24.7220, 46.6190),
}

# ---- Which POI each quiz purpose points at. None = purpose has no location signal,
# so proximity scores neutral and never penalises a unit.
PURPOSE_POI = {
    "boulevard": "boulevard",
    "work": "kafd",
    "medical": "kfmc",
    "family": None,
    "shopping": "riyadh_front",
    "rest": None,
}

# ---- Fallback when a unit has no resolved coordinates. Keys MUST exist in
# bot.RIYADH_NEIGHBORHOODS (a test enforces this). Approximate district centres.
NEIGHBOURHOOD_CENTROIDS = {
    "hittin":         (24.7690, 46.5960),
    "al_malqa":       (24.8020, 46.6230),
    "al_yasmin":      (24.8290, 46.6420),
    "al_narjis":      (24.8560, 46.6540),
    "al_aqiq":        (24.7780, 46.6300),
    "al_sahafah":     (24.8130, 46.6480),
    "al_ghadir":      (24.7850, 46.6640),
    "al_wadi":        (24.7960, 46.6760),
    "al_nakheel":     (24.7480, 46.6320),
    "al_rahmaniyah":  (24.7420, 46.6180),
    "al_muruj":       (24.7420, 46.6560),
    "al_mughrizat":   (24.7660, 46.6900),
    "al_izdihar":     (24.7770, 46.7160),
    "al_qirawan":     (24.8480, 46.6180),
    "al_arid":        (24.8830, 46.6660),
    "al_nada":        (24.8350, 46.6870),
    "al_taawun":      (24.7580, 46.6870),
    "al_wuroud":      (24.7280, 46.6720),
    "al_nuzha":       (24.7480, 46.6980),
    "al_muhammadiyah": (24.7370, 46.6280),
    "kafd":           (24.7649, 46.6408),
    "al_olaya":       (24.6960, 46.6820),
    "al_sulimaniyah": (24.7130, 46.6960),
    "al_khuzama":     (24.6890, 46.6480),
    "al_rabwah":      (24.7060, 46.7420),
    "al_rawdah":      (24.7480, 46.7690),
    "al_safarat":     (24.6810, 46.6180),
    "qurtubah":       (24.8060, 46.7660),
    "ghirnatah":      (24.7830, 46.7740),
    "irqah":          (24.7060, 46.5610),
    "umm_al_hamam_west": (24.7000, 46.6320),
    "umm_al_hamam_east": (24.7040, 46.6480),
    "al_malaz":       (24.6720, 46.7370),
    "al_masif":       (24.7620, 46.6640),
    "al_mursalat":    (24.7550, 46.6740),
}

EARTH_RADIUS_KM = 6371.0

# Riyadh arterial average, deliberately conservative. We surface "about N minutes",
# never a promise.
_AVG_KMH = 42.0


def haversine_km(a, b):
    """Great-circle distance in km between two (lat, lng) pairs."""
    lat1, lng1 = a
    lat2, lng2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def resolve_point(unit, geo):
    """(lat, lng) for a unit. Exact coords when known, else the centroid of its
    assigned neighborhood, else None. Never raises."""
    try:
        pt = (geo or {}).get(unit.get("id"))
    except (TypeError, AttributeError):
        pt = None
    if pt and len(pt) == 2:
        return (float(pt[0]), float(pt[1]))
    return NEIGHBOURHOOD_CENTROIDS.get(unit.get("neighborhood") or "")


def minutes_to(km):
    """Approximate drive minutes for a straight-line distance. The 1.35 factor
    accounts for road routing versus the crow-flies line."""
    return max(1, int(round((km * 1.35) / _AVG_KMH * 60)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_poi -v`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```bash
git add match/__init__.py match/poi.py tests/test_match_poi.py
git commit -m "feat(match): POI table, haversine, neighborhood centroid fallback"
```

Note: `match/__init__.py` imports `engine`, which does not exist yet. If Step 4 fails on
that import, temporarily leave `match/__init__.py` empty and restore the re-export in Task 2.

---

## Task 2: Engine skeleton — hard gates, never-zero, determinism

**Files:**
- Create: `match/engine.py`
- Test: `tests/test_match_engine.py`

This task locks invariants 1, 2 and 6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_match_engine.py`:

```python
import unittest
from match import engine


def unit(uid, beds=2, capacity=4, rating=4.7, reviews=40,
         neighborhood="al_malqa", amenities=None, est_avg=700):
    """Fabricated public-listing dict, shaped like _gw_listing_public output."""
    return {
        "id": uid, "slug": f"unit-{uid}", "name_ar": f"عوجا | وحدة {uid}",
        "beds": beds, "baths": 2, "capacity": capacity,
        "neighborhood": neighborhood, "area": "الملقا",
        "amenities": amenities if amenities is not None else ["Wifi", "Kitchen"],
        "rating": rating, "reviews_count": reviews,
        "est_avg": est_avg, "available": True,
    }


BASE = {"party_size": 2, "sleep_pref": None, "purpose": "rest",
        "budget_max": None, "check_in": None, "check_out": None}


class TestNeverZero(unittest.TestCase):
    def test_returns_results_when_inventory_exists(self):
        out = engine.score(BASE, [unit(1), unit(2), unit(3)])
        self.assertGreater(len(out["top"]), 0)

    def test_returns_results_even_when_every_soft_signal_fails(self):
        answers = dict(BASE, party_size=2, purpose="boulevard", budget_max=100)
        out = engine.score(answers, [unit(1, est_avg=5000, rating=3.0, reviews=2)])
        self.assertEqual(len(out["top"]), 1)
        self.assertFalse(out["confident"])

    def test_empty_inventory_returns_empty_not_crash(self):
        out = engine.score(BASE, [])
        self.assertEqual(out["top"], [])
        self.assertFalse(out["impossible"])


class TestCapacityGate(unittest.TestCase):
    def test_never_recommends_a_unit_that_cannot_fit(self):
        answers = dict(BASE, party_size=6)
        out = engine.score(answers, [unit(1, capacity=4), unit(2, capacity=8)])
        ids = [u["id"] for u in out["top"] + out["near"]]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)

    def test_physically_impossible_party_is_flagged_honestly(self):
        answers = dict(BASE, party_size=20)
        out = engine.score(answers, [unit(1, capacity=4), unit(2, capacity=8)])
        self.assertEqual(out["top"], [])
        self.assertTrue(out["impossible"])
        self.assertEqual(out["max_capacity"], 8)

    def test_unit_with_unknown_capacity_is_not_gated_out(self):
        u = unit(1)
        u["capacity"] = None
        out = engine.score(dict(BASE, party_size=6), [u])
        self.assertEqual(len(out["top"]), 1)


class TestAvailabilityGate(unittest.TestCase):
    def test_unavailable_units_are_excluded_when_dates_given(self):
        a = unit(1); a["available"] = False
        b = unit(2); b["available"] = True
        answers = dict(BASE, check_in="2026-08-01", check_out="2026-08-04")
        out = engine.score(answers, [a, b])
        ids = [u["id"] for u in out["top"] + out["near"]]
        self.assertEqual(ids, [2])

    def test_availability_ignored_when_no_dates(self):
        a = unit(1); a["available"] = False
        out = engine.score(BASE, [a])
        self.assertEqual(len(out["top"]), 1)


class TestDeterminism(unittest.TestCase):
    def test_identical_input_gives_identical_order(self):
        units = [unit(i) for i in (5, 3, 9, 1)]
        first = [u["id"] for u in engine.score(BASE, units)["top"]]
        second = [u["id"] for u in engine.score(BASE, list(units))["top"]]
        self.assertEqual(first, second)

    def test_ties_break_on_id_ascending(self):
        units = [unit(9), unit(2), unit(7)]
        out = engine.score(BASE, units)
        ids = [u["id"] for u in out["top"]]
        self.assertEqual(ids, sorted(ids))

    def test_does_not_mutate_the_caller_list(self):
        units = [unit(3), unit(1)]
        engine.score(BASE, units)
        self.assertEqual([u["id"] for u in units], [3, 1])


class TestTopAndNearSplit(unittest.TestCase):
    def test_top_capped_at_three_rest_goes_to_near(self):
        out = engine.score(BASE, [unit(i) for i in range(1, 8)])
        self.assertEqual(len(out["top"]), 3)
        self.assertEqual(len(out["near"]), 4)

    def test_scores_are_descending_across_top_then_near(self):
        out = engine.score(BASE, [unit(i, beds=i) for i in range(1, 7)])
        scores = [u["match_score"] for u in out["top"] + out["near"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'match.engine'`

- [ ] **Step 3: Write the implementation**

Create `match/engine.py`:

```python
"""Stay Match scoring engine. PURE — no I/O, no network, no clock reads.

The contract that makes this feature work: search FILTERS and can return zero;
this engine SCORES and returns the best available fit. Only physically-true
constraints eliminate a unit. Everything else lowers a score and produces an
honest tradeoff string the UI shows to the guest.
"""

from . import poi

# Weights sum to 100. Tunable here without touching the UI or the tests that
# lock behaviour (the tests assert orderings, never absolute scores).
WEIGHTS = {
    "bedrooms": 30,
    "proximity": 25,
    "budget": 20,
    "amenities": 15,
    "quality": 10,
}

# Below this, we tell the guest the truth instead of dressing up a weak match.
CONFIDENCE_FLOOR = 55

TOP_N = 3


def required_bedrooms(party_size, sleep_pref):
    """How many bedrooms the guest's own answers imply."""
    if party_size <= 2:
        return 1
    if sleep_pref == "together":
        return 1
    if sleep_pref == "each":
        return party_size
    # "pairs" and the None default: two per room, rounded up.
    return max(1, -(-party_size // 2))


def _passes_hard_gates(u, answers, dated):
    """Only physically-true constraints. Unknown data never eliminates a unit."""
    cap = u.get("capacity")
    if cap:
        try:
            if int(cap) < int(answers.get("party_size") or 1):
                return False
        except (TypeError, ValueError):
            pass
    if dated and u.get("available") is False:
        return False
    return True


def score(answers, units, geo=None, top=TOP_N):
    """Rank units by fit. See the plan's data contract for shapes."""
    answers = answers or {}
    units = list(units or [])
    dated = bool(answers.get("check_in") and answers.get("check_out"))

    eligible = [u for u in units if _passes_hard_gates(u, answers, dated)]

    if not eligible:
        caps = []
        for u in units:
            try:
                caps.append(int(u.get("capacity") or 0))
            except (TypeError, ValueError):
                continue
        return {"top": [], "near": [], "confident": False,
                "impossible": bool(units), "max_capacity": (max(caps) if caps else 0)}

    scored = []
    for u in eligible:
        total, reasons, tradeoffs = _score_one(u, answers, geo or {})
        item = dict(u)
        item["match_score"] = int(round(total))
        item["reasons"] = reasons[:3]
        item["tradeoff"] = (tradeoffs[0] if tradeoffs else None)
        scored.append(item)

    # Stable, deterministic: best score first, ties broken by id ascending.
    scored.sort(key=lambda x: (-x["match_score"], x.get("id") or 0))

    best = scored[0]["match_score"] if scored else 0
    return {"top": scored[:top], "near": scored[top:],
            "confident": best >= CONFIDENCE_FLOOR,
            "impossible": False,
            "max_capacity": 0}


def _score_one(u, answers, geo):
    """Returns (total_0_to_100, reasons, tradeoffs). Filled in across Tasks 3-6."""
    total = 0.0
    reasons, tradeoffs = [], []
    return total, reasons, tradeoffs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: PASS.

Note: `test_scores_are_descending_across_top_then_near` passes trivially while every
score is 0 (all equal). Task 3 gives it teeth.

- [ ] **Step 5: Restore the package re-export**

Ensure `match/__init__.py` contains the `from .engine import score` line from Task 1.

Run: `python3 -c "import match; print(match.score)"`
Expected: prints a function reference, no error.

- [ ] **Step 6: Commit**

```bash
git add match/engine.py match/__init__.py tests/test_match_engine.py
git commit -m "feat(match): engine skeleton — hard gates, never-zero, deterministic order"
```

---

## Task 3: Bedroom fit scoring, reasons and tradeoffs

**Files:**
- Modify: `match/engine.py` (`_score_one`)
- Test: `tests/test_match_engine.py` (append)

Locks invariants 3, 4, 5.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_match_engine.py`, above the `if __name__` block:

```python
class TestRequiredBedrooms(unittest.TestCase):
    def test_solo_and_couple_need_one(self):
        self.assertEqual(engine.required_bedrooms(1, None), 1)
        self.assertEqual(engine.required_bedrooms(2, None), 1)

    def test_together_means_one_room(self):
        self.assertEqual(engine.required_bedrooms(5, "together"), 1)

    def test_each_means_one_room_per_person(self):
        self.assertEqual(engine.required_bedrooms(4, "each"), 4)

    def test_pairs_rounds_up(self):
        self.assertEqual(engine.required_bedrooms(5, "pairs"), 3)
        self.assertEqual(engine.required_bedrooms(4, "pairs"), 2)


class TestBedroomFit(unittest.TestCase):
    def test_exact_match_outranks_over_provisioned(self):
        answers = dict(BASE, party_size=4, sleep_pref="pairs")   # needs 2
        out = engine.score(answers, [unit(1, beds=5, capacity=10),
                                     unit(2, beds=2, capacity=6)])
        self.assertEqual(out["top"][0]["id"], 2)

    def test_under_provisioned_still_appears_with_a_tradeoff(self):
        answers = dict(BASE, party_size=6, sleep_pref="each")    # needs 6
        out = engine.score(answers, [unit(1, beds=2, capacity=8)])
        self.assertEqual(len(out["top"]), 1)
        self.assertIsNotNone(out["top"][0]["tradeoff"])

    def test_exact_match_produces_a_reason(self):
        answers = dict(BASE, party_size=4, sleep_pref="pairs")
        out = engine.score(answers, [unit(1, beds=2, capacity=6)])
        self.assertTrue(out["top"][0]["reasons"])

    def test_every_returned_unit_has_at_least_one_reason(self):
        answers = dict(BASE, party_size=2)
        out = engine.score(answers, [unit(i) for i in range(1, 6)])
        for u in out["top"] + out["near"]:
            self.assertTrue(u["reasons"], f"unit {u['id']} has no reason")

    def test_reason_contains_the_real_bedroom_number(self):
        answers = dict(BASE, party_size=4, sleep_pref="pairs")
        out = engine.score(answers, [unit(1, beds=2, capacity=6)])
        self.assertTrue(any("2" in r for r in out["top"][0]["reasons"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: FAIL — `test_exact_match_outranks_over_provisioned` and the reason tests fail
(all scores are still 0, no reasons produced).

- [ ] **Step 3: Write the implementation**

In `match/engine.py`, replace `_score_one` entirely and add `_score_bedrooms` above it:

```python
def _score_bedrooms(u, answers):
    """0.0-1.0 fit, plus a reason or a tradeoff. Exact match wins; over-provisioned
    is slightly worse (the guest pays for space they said they don't need);
    under-provisioned is heavily penalised but NEVER eliminated."""
    need = required_bedrooms(int(answers.get("party_size") or 1),
                             answers.get("sleep_pref"))
    try:
        have = int(u.get("beds") or 0)
    except (TypeError, ValueError):
        have = 0
    if not have:
        return 0.5, None, None                      # unknown data scores neutral
    if have == need:
        return 1.0, f"{have} غرف نوم — بالضبط اللي طلبته", None
    if have > need:
        over = have - need
        return max(0.6, 1.0 - 0.12 * over), f"{have} غرف نوم — فيها زيادة راحة", None
    short = need - have
    return max(0.1, 0.55 - 0.18 * short), None, f"{have} غرف نوم بس — طلبت {need}"


def _score_one(u, answers, geo):
    """Returns (total_0_to_100, reasons, tradeoffs)."""
    total = 0.0
    reasons, tradeoffs = [], []

    fit, reason, tradeoff = _score_bedrooms(u, answers)
    total += fit * WEIGHTS["bedrooms"]
    if reason:
        reasons.append(reason)
    if tradeoff:
        tradeoffs.append(tradeoff)

    return total, reasons, tradeoffs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: FAIL on `test_every_returned_unit_has_at_least_one_reason` — a unit scoring
neutral (unknown beds) still has no reason. This is correct: Task 4 adds the quality
reason that guarantees every unit says something. Confirm all *other* tests pass, then
proceed to Task 4 before committing.

If any test other than `test_every_returned_unit_has_at_least_one_reason` fails, stop and fix.

---

## Task 4: Quality scoring with Bayesian smoothing

**Files:**
- Modify: `match/engine.py`
- Test: `tests/test_match_engine.py` (append)

Locks invariant 8, and completes invariant 4.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_match_engine.py`:

```python
class TestQualitySmoothing(unittest.TestCase):
    def test_perfect_rating_with_few_reviews_loses_to_strong_rating_with_many(self):
        out = engine.score(BASE, [unit(1, rating=5.0, reviews=3),
                                  unit(2, rating=4.8, reviews=90)])
        self.assertEqual(out["top"][0]["id"], 2)

    def test_unrated_unit_is_not_eliminated(self):
        u = unit(1, rating=None, reviews=0)
        out = engine.score(BASE, [u])
        self.assertEqual(len(out["top"]), 1)

    def test_high_rating_produces_a_reason_with_the_number(self):
        out = engine.score(BASE, [unit(1, rating=4.9, reviews=67)])
        joined = " ".join(out["top"][0]["reasons"])
        self.assertIn("4.9", joined)
        self.assertIn("67", joined)

    def test_reason_guarantee_holds_for_unknown_data_units(self):
        u = unit(1, rating=None, reviews=0)
        u["beds"] = None
        out = engine.score(BASE, [u])
        self.assertTrue(out["top"][0]["reasons"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: FAIL on `test_perfect_rating_with_few_reviews_loses_to_strong_rating_with_many`
(scores are tied, so id 1 wins the tiebreak).

- [ ] **Step 3: Write the implementation**

In `match/engine.py`, add these constants next to `CONFIDENCE_FLOOR`:

```python
# Bayesian prior for ratings. A raw average lets 5.0 from 3 reviews outrank 4.8
# from 90, which would put barely-reviewed units at the top of every result.
PRIOR_RATING = 4.6
PRIOR_WEIGHT = 12
```

Add `_score_quality` above `_score_one`:

```python
def _score_quality(u):
    """0.0-1.0 from rating, shrunk toward the portfolio prior by review count."""
    try:
        rating = float(u.get("rating") or 0)
        n = int(u.get("reviews_count") or 0)
    except (TypeError, ValueError):
        return 0.5, None
    if rating <= 0 or n <= 0:
        return 0.5, None                            # unrated scores neutral, never punished
    smoothed = ((rating * n) + (PRIOR_RATING * PRIOR_WEIGHT)) / (n + PRIOR_WEIGHT)
    fit = max(0.0, min(1.0, (smoothed - 3.5) / 1.5))
    reason = None
    if rating >= 4.7 and n >= 10:
        reason = f"{rating} ★ من {n} تقييم"
    return fit, reason
```

In `_score_one`, insert before the `return`:

```python
    qfit, qreason = _score_quality(u)
    total += qfit * WEIGHTS["quality"]
    if qreason:
        reasons.append(qreason)

    # Reason guarantee (invariant 4): a unit with nothing notable still says
    # something true rather than showing a bare card.
    if not reasons:
        cap = u.get("capacity")
        reasons.append(f"تستوعب {cap} ضيوف" if cap else "متاحة للحجز")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: PASS — all tests including `test_every_returned_unit_has_at_least_one_reason`.

- [ ] **Step 5: Commit**

```bash
git add match/engine.py tests/test_match_engine.py
git commit -m "feat(match): bedroom fit + Bayesian-smoothed quality, reasons and tradeoffs"
```

---

## Task 5: Proximity scoring

**Files:**
- Modify: `match/engine.py`
- Test: `tests/test_match_engine.py` (append)

Locks invariant 7.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_match_engine.py`:

```python
class TestProximity(unittest.TestCase):
    def test_closer_unit_to_the_boulevard_outranks_farther(self):
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        near = (blvd[0] + 0.01, blvd[1])
        far = (blvd[0] + 0.30, blvd[1])
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [unit(1), unit(2)], geo={1: far, 2: near})
        self.assertEqual(out["top"][0]["id"], 2)

    def test_close_unit_gets_a_minutes_reason(self):
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [unit(1)], geo={1: (blvd[0] + 0.01, blvd[1])})
        joined = " ".join(out["top"][0]["reasons"])
        self.assertIn("دقيقة", joined)

    def test_missing_coords_fall_back_to_centroid_not_null(self):
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [unit(1, neighborhood="al_malqa")], geo={})
        self.assertEqual(len(out["top"]), 1)
        self.assertGreater(out["top"][0]["match_score"], 0)

    def test_purpose_without_a_poi_scores_neutral_for_everyone(self):
        answers = dict(BASE, purpose="rest")
        out = engine.score(answers, [unit(1, neighborhood="al_malqa"),
                                     unit(2, neighborhood="al_malaz")], geo={})
        self.assertEqual(out["top"][0]["match_score"], out["top"][1]["match_score"])

    def test_unlocatable_unit_is_not_eliminated(self):
        u = unit(1, neighborhood="")
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [u], geo={})
        self.assertEqual(len(out["top"]), 1)

    def test_far_unit_gets_a_distance_tradeoff(self):
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [unit(1)], geo={1: (blvd[0] + 0.40, blvd[1])})
        self.assertIsNotNone(out["top"][0]["tradeoff"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: FAIL — proximity is not scored, so `test_closer_unit_...` ties and id 1 wins.

- [ ] **Step 3: Write the implementation**

In `match/engine.py`, add `_score_proximity` above `_score_one`:

```python
# Minutes at which proximity stops helping. Beyond this a unit is "across town".
_NEAR_MIN, _FAR_MIN = 10, 35


def _score_proximity(u, answers, geo):
    """0.0-1.0 by drive time to the POI implied by the guest's purpose.
    Neutral (never punishing) when the purpose has no POI or the unit cannot be
    located — invariant 7 means this never returns None."""
    poi_key = poi.PURPOSE_POI.get(answers.get("purpose") or "")
    if not poi_key:
        return 0.5, None, None
    target = poi.POIS.get(poi_key)
    if not target:
        return 0.5, None, None
    point = poi.resolve_point(u, geo)
    if not point:
        return 0.5, None, None

    label = target[0]
    mins = poi.minutes_to(poi.haversine_km(point, (target[2], target[3])))
    if mins <= _NEAR_MIN:
        return 1.0, f"{mins} دقيقة عن {label}", None
    if mins >= _FAR_MIN:
        return 0.1, None, f"بعيدة عن {label} — حوالي {mins} دقيقة"
    span = _FAR_MIN - _NEAR_MIN
    fit = 1.0 - ((mins - _NEAR_MIN) / span) * 0.9
    reason = f"{mins} دقيقة عن {label}" if mins <= 20 else None
    return fit, reason, None
```

In `_score_one`, insert after the bedroom block and before the quality block:

```python
    pfit, preason, ptradeoff = _score_proximity(u, answers, geo)
    total += pfit * WEIGHTS["proximity"]
    if preason:
        reasons.append(preason)
    if ptradeoff:
        tradeoffs.append(ptradeoff)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add match/engine.py tests/test_match_engine.py
git commit -m "feat(match): proximity scoring with centroid fallback"
```

---

## Task 6: Budget and purpose-amenity scoring

**Files:**
- Modify: `match/engine.py`
- Test: `tests/test_match_engine.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_match_engine.py`:

```python
class TestBudget(unittest.TestCase):
    def test_within_budget_outranks_over_budget(self):
        answers = dict(BASE, budget_max=800)
        out = engine.score(answers, [unit(1, est_avg=1400), unit(2, est_avg=700)])
        self.assertEqual(out["top"][0]["id"], 2)

    def test_over_budget_unit_still_appears_with_a_tradeoff(self):
        answers = dict(BASE, budget_max=500)
        out = engine.score(answers, [unit(1, est_avg=900)])
        self.assertEqual(len(out["top"]), 1)
        self.assertIsNotNone(out["top"][0]["tradeoff"])

    def test_tradeoff_states_the_real_gap(self):
        answers = dict(BASE, budget_max=500)
        out = engine.score(answers, [unit(1, est_avg=650)])
        self.assertIn("150", out["top"][0]["tradeoff"])

    def test_no_budget_answer_scores_neutral_for_everyone(self):
        answers = dict(BASE, budget_max=None)
        out = engine.score(answers, [unit(1, est_avg=300), unit(2, est_avg=3000)])
        self.assertEqual(out["top"][0]["match_score"], out["top"][1]["match_score"])

    def test_unpriced_unit_is_not_eliminated(self):
        u = unit(1); u["est_avg"] = None; u["price_base"] = None
        out = engine.score(dict(BASE, budget_max=500), [u])
        self.assertEqual(len(out["top"]), 1)


class TestPurposeAmenities(unittest.TestCase):
    def test_workspace_helps_a_work_trip(self):
        answers = dict(BASE, purpose="work")
        withws = unit(1, amenities=["Wifi", "Dedicated workspace", "Kitchen"])
        without = unit(2, amenities=["Kitchen"])
        out = engine.score(answers, [withws, without], geo={})
        self.assertEqual(out["top"][0]["id"], 1)

    def test_washer_helps_a_family_trip(self):
        answers = dict(BASE, purpose="family")
        withw = unit(1, amenities=["Kitchen", "Washer"])
        without = unit(2, amenities=["Wifi"])
        out = engine.score(answers, [withw, without], geo={})
        self.assertEqual(out["top"][0]["id"], 1)

    def test_missing_amenities_list_does_not_crash(self):
        u = unit(1); u["amenities"] = None
        out = engine.score(dict(BASE, purpose="work"), [u])
        self.assertEqual(len(out["top"]), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: FAIL on the budget and amenity ordering tests.

- [ ] **Step 3: Write the implementation**

In `match/engine.py`, add above `_score_one`:

```python
# Amenity keywords that genuinely matter per purpose. Matched case-insensitively
# as substrings against the raw Hostaway amenity names.
PURPOSE_AMENITIES = {
    "work":      [("workspace", "مكتب للشغل"), ("wifi", "واي فاي"), ("desk", "مكتب")],
    "family":    [("kitchen", "مطبخ كامل"), ("washer", "غسالة"), ("crib", "سرير أطفال")],
    "rest":      [("pool", "مسبح"), ("balcony", "بلكونة"), ("jacuzzi", "جاكوزي")],
    "medical":   [("kitchen", "مطبخ كامل"), ("elevator", "مصعد"), ("parking", "موقف")],
    "boulevard": [("parking", "موقف سيارة"), ("wifi", "واي فاي")],
    "shopping":  [("parking", "موقف سيارة"), ("elevator", "مصعد")],
}


def _score_budget(u, answers):
    """0.0-1.0 by nightly price against the guest's band. Unpriced scores neutral."""
    budget = answers.get("budget_max")
    if not budget:
        return 0.5, None, None
    price = u.get("est_avg") or u.get("price_base")
    try:
        price = int(price)
    except (TypeError, ValueError):
        return 0.5, None, None
    if price <= 0:
        return 0.5, None, None
    budget = int(budget)
    if price <= budget:
        return 1.0, f"{price} ريال بالليلة — داخل ميزانيتك", None
    gap = price - budget
    if gap <= budget * 0.25:
        return 0.5, None, f"أغلى {gap} ريال بالليلة من ميزانيتك"
    return 0.15, None, f"أغلى {gap} ريال بالليلة من ميزانيتك"


def _score_amenities(u, answers):
    """0.0-1.0 by how many purpose-relevant amenities the unit actually has."""
    wanted = PURPOSE_AMENITIES.get(answers.get("purpose") or "")
    if not wanted:
        return 0.5, None
    have = " ".join(str(a).lower() for a in (u.get("amenities") or []))
    hits = [ar for (kw, ar) in wanted if kw in have]
    if not hits:
        return 0.2, None
    fit = min(1.0, len(hits) / len(wanted))
    return fit, " · ".join(hits[:2])
```

In `_score_one`, insert before the quality block:

```python
    bfit, breason, btradeoff = _score_budget(u, answers)
    total += bfit * WEIGHTS["budget"]
    if breason:
        reasons.append(breason)
    if btradeoff:
        tradeoffs.append(btradeoff)

    afit, areason = _score_amenities(u, answers)
    total += afit * WEIGHTS["amenities"]
    if areason:
        reasons.append(areason)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_engine -v`
Expected: PASS, all tests.

- [ ] **Step 5: Run the whole suite and the linters**

```bash
python3 -m pyflakes match/*.py | grep -v "imported but unused"
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(OK|FAILED|Ran )"
```
Expected: no pyflakes output; `OK` with the run count up from 587.

- [ ] **Step 6: Commit**

```bash
git add match/engine.py tests/test_match_engine.py
git commit -m "feat(match): budget and purpose-amenity scoring — engine complete"
```

---

## Task 7: Price bands in the guest-site config

**Files:**
- Modify: `bot.py` (add `_gw_price_bands`, wire into `_stay_render` and `_api_stay_config`)
- Test: `tests/test_match_api.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_match_api.py`:

```python
import unittest
import bot


class TestPriceBands(unittest.TestCase):
    def test_thin_sample_returns_none(self):
        self.assertIsNone(bot._gw_price_bands([100, 200]))

    def test_returns_ascending_percentiles(self):
        prices = [200, 300, 400, 500, 600, 700, 800, 900]
        b = bot._gw_price_bands(prices)
        self.assertIsNotNone(b)
        self.assertLessEqual(b["p25"], b["median"])
        self.assertLessEqual(b["median"], b["p75"])

    def test_ignores_non_positive_prices(self):
        prices = [0, -5, None, 400, 500, 600, 700, 800]
        b = bot._gw_price_bands(prices)
        self.assertIsNotNone(b)
        self.assertGreater(b["p25"], 0)

    def test_all_values_are_ints(self):
        b = bot._gw_price_bands([100, 200, 300, 400, 500, 600])
        for k in ("p25", "median", "p75"):
            self.assertIsInstance(b[k], int)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_api -v`
Expected: FAIL with `AttributeError: module 'bot' has no attribute '_gw_price_bands'`

- [ ] **Step 3: Write the implementation**

In `bot.py`, insert immediately **before** `def _gw_search(` (currently `bot.py:45795`):

```python
_GW_PRICE_MIN_SAMPLE = 5

def _gw_price_bands(prices):
    """p25/median/p75 nightly price across visible units, for the Stay Match
    budget slider. Returns None on a thin sample so the UI skips the budget
    screen rather than showing invented numbers."""
    vals = []
    for p in (prices or []):
        try:
            v = int(p)
        except (TypeError, ValueError):
            continue
        if v > 0:
            vals.append(v)
    if len(vals) < _GW_PRICE_MIN_SAMPLE:
        return None
    vals.sort()
    def _pct(q):
        return int(vals[min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))])
    return {"p25": _pct(0.25), "median": _pct(0.50), "p75": _pct(0.75)}

def _gw_visible_prices():
    """Nightly base prices of every visible unit (input to _gw_price_bands)."""
    return [s.get("price_base") for s, _ov in _gw_visible_snaps()]
```

In `_stay_render` (`bot.py:46332`), add `price_bands` to the config dict. Change:

```python
                       "rating_overall": _gw_ratings_overall()}}
```

to:

```python
                       "rating_overall": _gw_ratings_overall(),
                       "price_bands": _gw_price_bands(_gw_visible_prices())}}
```

In `_api_stay_config` (`bot.py:46390`), change the body to:

```python
    return _json({"ok": True, "noo": _gw_noo_options(),
                  "neighborhoods": _gw_neighborhoods_with_counts(),
                  "price_bands": _gw_price_bands(_gw_visible_prices())})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_api -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add bot.py tests/test_match_api.py
git commit -m "feat(stay): price_bands in guest config for the Match budget slider"
```

---

## Task 8: The `/api/stay/match` endpoint and route registration

**Files:**
- Modify: `bot.py`
- Test: `tests/test_match_api.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_match_api.py`, above the `if __name__` block:

```python
class TestMatchAnswers(unittest.TestCase):
    def test_parses_query_into_the_answers_contract(self):
        a = bot._match_answers({"party": "5", "sleep": "pairs", "purpose": "boulevard",
                                "budget": "900", "check_in": "2026-08-01",
                                "check_out": "2026-08-04"})
        self.assertEqual(a["party_size"], 5)
        self.assertEqual(a["sleep_pref"], "pairs")
        self.assertEqual(a["purpose"], "boulevard")
        self.assertEqual(a["budget_max"], 900)

    def test_defaults_are_safe_on_empty_query(self):
        a = bot._match_answers({})
        self.assertEqual(a["party_size"], 1)
        self.assertIsNone(a["budget_max"])
        self.assertIsNone(a["check_in"])

    def test_party_size_is_clamped(self):
        self.assertEqual(bot._match_answers({"party": "999"})["party_size"], 16)
        self.assertEqual(bot._match_answers({"party": "0"})["party_size"], 1)
        self.assertEqual(bot._match_answers({"party": "junk"})["party_size"], 1)

    def test_unknown_sleep_pref_becomes_none(self):
        self.assertIsNone(bot._match_answers({"sleep": "hammock"})["sleep_pref"])

    def test_unknown_purpose_falls_back_to_rest(self):
        self.assertEqual(bot._match_answers({"purpose": "spelunking"})["purpose"], "rest")

    def test_dates_only_kept_when_both_valid(self):
        a = bot._match_answers({"check_in": "2026-08-01"})
        self.assertIsNone(a["check_in"])
        b = bot._match_answers({"check_in": "2026-08-04", "check_out": "2026-08-01"})
        self.assertIsNone(b["check_in"])


class TestMatchRouteOrder(unittest.TestCase):
    def test_match_route_is_registered_before_the_slug_catchall(self):
        """/stay/{slug} is a catch-all. Registered after it, /stay/match 404s."""
        src = open("bot.py", encoding="utf-8").read()
        i_match = src.index('add_get("/stay/match"')
        i_slug = src.index('add_get("/stay/{slug}"')
        self.assertLess(i_match, i_slug,
                        "/stay/match must be registered before /stay/{slug}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_api -v`
Expected: FAIL with `AttributeError: module 'bot' has no attribute '_match_answers'`

- [ ] **Step 3: Write the implementation**

Near the top of `bot.py`, beside the other optional-package imports (search for
`_HAS_GUIDE` to find the block), add:

```python
try:
    import match as _match
    _HAS_MATCH = True
except Exception as _e:
    _match = None
    _HAS_MATCH = False
    print("match package unavailable:", _e)
```

In `bot.py`, insert immediately **before** `async def _api_stay_config(` (`bot.py:46390`):

```python
_MATCH_SLEEP = ("together", "pairs", "each")

def _match_answers(q):
    """Query params -> the engine's answers contract. Defensive: junk input can
    never raise, it degrades to a neutral answer."""
    try:
        party = int(q.get("party") or 1)
    except (TypeError, ValueError):
        party = 1
    party = max(1, min(16, party))
    sleep = q.get("sleep") if q.get("sleep") in _MATCH_SLEEP else None
    purpose = q.get("purpose") or "rest"
    if _HAS_MATCH and purpose not in _match.poi.PURPOSE_POI:
        purpose = "rest"
    try:
        budget = int(q.get("budget")) if q.get("budget") else None
    except (TypeError, ValueError):
        budget = None
    ci, co = q.get("check_in"), q.get("check_out")
    if not (ci and co and _gw_valid_dates(ci, co)):
        ci = co = None
    return {"party_size": party, "sleep_pref": sleep, "purpose": purpose,
            "budget_max": budget, "check_in": ci, "check_out": co}

def _match_geo_points():
    """{listing_id: (lat, lng)} from the cached guide coordinates. Cache-only —
    no network here. Missing units fall back to a neighborhood centroid inside
    the engine, so a thin cache degrades precision, never correctness."""
    gmap = _elite_geo_cache.get("map") or {}
    pts = {}
    for s, _ov in _gw_visible_snaps():
        nm = _elite_geo_norm(s.get("name") or "")
        if nm and nm in gmap:
            pts[s.get("id")] = gmap[nm]
    return pts

def _match_run(q):
    """BLOCKING — executor only. Builds inventory, prices it, delegates ranking."""
    if not _HAS_MATCH:
        return {"top": [], "near": [], "confident": False,
                "impossible": False, "max_capacity": 0}
    answers = _match_answers(q)
    _elite_geo_refresh()
    units = []
    for s, ov in _gw_visible_snaps():
        pub = _gw_listing_public(s, ov)
        if answers["check_in"] and answers["check_out"]:
            av = unit_availability_price(s.get("id"), answers["check_in"],
                                         answers["check_out"])
            if av:
                pub["available"] = av.get("available")
                pub["nights"] = av.get("nights")
                pub["est_total"] = av.get("total")
                pub["est_avg"] = av.get("avg")
        units.append(pub)
    out = _match.score(answers, units, geo=_match_geo_points())
    out["answers"] = answers
    return out

async def _api_stay_match(request):
    out = await asyncio.to_thread(_match_run, dict(request.query))
    return _json({"ok": True, **out})

async def _handle_stay_match(request):
    return web.Response(text=_stay_render("match", base=str(request.url.origin())),
                        content_type="text/html")
```

In `_stay_render` (`bot.py:46322`), add the match route to the path map. Change:

```python
    path = {"landing": "/stay", "search": "/stay/search", "listing": "/stay"}.get(route, "/stay")
```

to:

```python
    path = {"landing": "/stay", "search": "/stay/search",
            "match": "/stay/match", "listing": "/stay"}.get(route, "/stay")
```

In `start_web_server`, immediately after the `/stay/search` line (`bot.py:49059`) — this
placement is what keeps it ahead of the `/stay/{slug}` catch-all:

```python
        app.router.add_get("/stay/match", _handle_stay_match)
        app.router.add_get("/api/stay/match", _api_stay_match)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_api -v`
Expected: PASS, 11 tests.

- [ ] **Step 5: Verify the module compiles and nothing regressed**

```bash
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py && echo "PY OK"
python3 -m pyflakes bot.py match/*.py | grep -v "imported but unused"
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(OK|FAILED|Ran )"
```
Expected: `PY OK`, no pyflakes output, `OK`.

- [ ] **Step 6: Commit**

```bash
git add bot.py tests/test_match_api.py
git commit -m "feat(stay): /stay/match route + /api/stay/match scored endpoint"
```

---

## Task 9: The quiz UI

**Files:**
- Modify: `bot.py` — `STAY_HTML` (add `viewMatch()`, extend the router at `bot.py:46269`)

Remember: `STAY_HTML` is a **raw** string. Backslashes in JS are safe here.

- [ ] **Step 1: Add the view and router entry**

In `STAY_HTML`, find the router (`bot.py:46269`):

```javascript
  if(path==='/stay'||path==='/stay/'){viewLanding();}
  else if(path==='/stay/search'){viewSearch();}
```

Insert a match branch after the search branch:

```javascript
  else if(path==='/stay/match'){viewMatch();}
```

Then add `viewMatch()` inside the same `<script>` block, immediately before `viewSearch`:

```javascript
var MQ={party:1,sleep:null,purpose:null,budget:null,ci:'',co:'',step:0};

function mqSteps(){
  // Q2 is conditional: parties under 3 never see the sleeping question.
  var s=['who'];
  if(MQ.party>=3)s.push('sleep');
  s.push('purpose');
  var pb=((STAY&&STAY.config&&STAY.config.price_bands)||null);
  s.push(pb?'when_budget':'when');
  return s;
}

function mqProgress(){
  var st=mqSteps(),n=st.length,i=Math.min(MQ.step,n-1);
  var dots='';for(var k=0;k<n;k++){dots+='<span class="mq-dot'+(k<=i?' on':'')+'"></span>';}
  return '<div class="mq-prog" role="progressbar" aria-valuenow="'+(i+1)+'" aria-valuemin="1" aria-valuemax="'+n+'">'+dots+'</div>';
}

var MQ_WHO=[['solo','أنا بس',1],['couple','أنا وشريكي',2],['family','عائلة وأطفال',4],['friends','شلة أصدقاء',4],['work','سفر عمل',1]];
var MQ_SLEEP=[['together','غرفة وحدة تكفينا'],['pairs','غرفة لكل ثنين'],['each','كل واحد غرفته']];
var MQ_PURPOSE=[['boulevard','البوليفارد وموسم الرياض'],['work','عمل واجتماعات'],['medical','علاج'],['family','زيارة أهل'],['shopping','تسوق وسياحة'],['rest','بس أبي أرتاح']];

function mqRender(){
  var st=mqSteps(),key=st[Math.min(MQ.step,st.length-1)],body='',title='';
  if(key==='who'){
    title='مين معك؟';
    body='<div class="mq-opts">'+MQ_WHO.map(function(o){
      return '<button type="button" class="mq-opt" data-who="'+he(o[0])+'" data-n="'+o[2]+'">'+he(o[1])+'</button>';
    }).join('')+'</div>'
    +'<div class="mq-count"><span>كم عددكم؟</span><button type="button" class="mq-pm" data-pm="-1" aria-label="أقل">−</button>'
    +'<b id="mqN">'+MQ.party+'</b><button type="button" class="mq-pm" data-pm="1" aria-label="أكثر">+</button></div>';
  } else if(key==='sleep'){
    title='كيف تبون تنامون؟';
    body='<div class="mq-opts">'+MQ_SLEEP.map(function(o){
      return '<button type="button" class="mq-opt" data-sleep="'+he(o[0])+'">'+he(o[1])+'</button>';
    }).join('')+'</div>';
  } else if(key==='purpose'){
    title='وش جايبك الرياض؟';
    body='<div class="mq-opts">'+MQ_PURPOSE.map(function(o){
      return '<button type="button" class="mq-opt" data-purpose="'+he(o[0])+'">'+he(o[1])+'</button>';
    }).join('')+'</div>';
  } else {
    title='متى تجي؟';
    var pb=((STAY&&STAY.config&&STAY.config.price_bands)||null);
    body='<div class="row2"><div class="field"><label>تاريخ الدخول</label><input type="date" id="mqCi"></div>'
        +'<div class="field"><label>تاريخ الخروج</label><input type="date" id="mqCo"></div></div>'
        +'<div id="mqErr" class="err"></div>';
    if(pb){
      body+='<div class="field"><label>كم تبي تصرف بالليلة؟ <b id="mqBv">'+pb.median+'</b> ريال</label>'
          +'<input type="range" id="mqB" min="'+pb.p25+'" max="'+(pb.p75*2)+'" step="50" value="'+pb.median+'"></div>';
    }
    body+='<button class="btn block" id="mqGo">شوف اللي يناسبك</button>'
        +'<button type="button" class="mq-skip" id="mqSkipDates">ما حددت التواريخ بعد</button>';
  }
  var back=MQ.step>0?'<button type="button" class="mq-back" id="mqBack" aria-label="رجوع">← رجوع</button>':'';
  V.innerHTML='<div class="mq-wrap">'+mqProgress()+back
    +'<h1 class="mq-q">'+he(title)+'</h1><div class="mq-body">'+body+'</div></div>';
  mqBind(key);
}

function mqBind(key){
  var wrap=V.querySelector('.mq-wrap');if(!wrap)return;
  var back=document.getElementById('mqBack');
  if(back)back.onclick=function(){MQ.step=Math.max(0,MQ.step-1);mqRender();};
  wrap.addEventListener('click',function(e){
    var b=e.target.closest('button');if(!b)return;
    if(b.hasAttribute('data-pm')){
      MQ.party=Math.max(1,Math.min(16,MQ.party+parseInt(b.getAttribute('data-pm'),10)));
      var n=document.getElementById('mqN');if(n)n.textContent=MQ.party;return;
    }
    if(b.hasAttribute('data-who')){
      MQ.party=parseInt(b.getAttribute('data-n'),10)||MQ.party;
      if(b.getAttribute('data-who')==='work')MQ.purpose='work';
      track('match_answer',{type:'who'});MQ.step++;mqRender();return;
    }
    if(b.hasAttribute('data-sleep')){
      MQ.sleep=b.getAttribute('data-sleep');
      track('match_answer',{type:'sleep'});MQ.step++;mqRender();return;
    }
    if(b.hasAttribute('data-purpose')){
      MQ.purpose=b.getAttribute('data-purpose');
      track('match_answer',{type:'purpose'});MQ.step++;mqRender();return;
    }
  });
  if(key==='when'||key==='when_budget'){
    var ci=document.getElementById('mqCi'),co=document.getElementById('mqCo');
    var t=new Date(),iso=function(d){return d.toISOString().slice(0,10);};
    ci.min=iso(t);co.min=iso(new Date(t.getTime()+86400000));
    ci.onchange=function(){var d=ci.value?new Date(ci.value):t;co.min=iso(new Date(d.getTime()+86400000));};
    var bs=document.getElementById('mqB'),bv=document.getElementById('mqBv');
    if(bs&&bv)bs.oninput=function(){bv.textContent=bs.value;};
    var submit=function(withDates){
      if(withDates){
        var ev=validateDates(ci.value,co.value);
        if(ev){var er=document.getElementById('mqErr');er.textContent=ev;er.classList.add('on');return;}
        MQ.ci=ci.value;MQ.co=co.value;
      } else {MQ.ci='';MQ.co='';}
      if(bs)MQ.budget=bs.value;
      mqSubmit();
    };
    document.getElementById('mqGo').onclick=function(){submit(true);};
    document.getElementById('mqSkipDates').onclick=function(){submit(false);};
  }
}

function mqSubmit(){
  var q='?party='+encodeURIComponent(MQ.party)+'&purpose='+encodeURIComponent(MQ.purpose||'rest');
  if(MQ.sleep)q+='&sleep='+encodeURIComponent(MQ.sleep);
  if(MQ.budget)q+='&budget='+encodeURIComponent(MQ.budget);
  if(MQ.ci&&MQ.co)q+='&check_in='+MQ.ci+'&check_out='+MQ.co;
  history.replaceState(null,'','/stay/match'+q);
  mqResults(q);
}

function viewMatch(){
  track('match_start',{});
  var p=qs();
  if(p.get('party')){                 // returning via a shared/back-button URL
    MQ.party=parseInt(p.get('party'),10)||1;MQ.sleep=p.get('sleep');
    MQ.purpose=p.get('purpose');MQ.budget=p.get('budget');
    MQ.ci=p.get('check_in')||'';MQ.co=p.get('check_out')||'';
    mqResults(location.search);return;
  }
  MQ.step=0;mqRender();
}
```

- [ ] **Step 2: Add the styles**

In `STAY_HTML`'s `<style>` block, append:

```css
.mq-wrap{max-width:560px;margin:0 auto;padding:22px 4px 40px}
.mq-prog{display:flex;gap:6px;justify-content:center;margin-bottom:22px}
.mq-dot{width:26px;height:3px;border-radius:2px;background:var(--border);transition:background .25s cubic-bezier(.23,1,.32,1)}
.mq-dot.on{background:var(--ink)}
.mq-back{background:none;border:0;color:var(--muted);font:inherit;font-size:13px;cursor:pointer;padding:4px 0;margin-bottom:6px}
.mq-q{font-size:26px;line-height:1.35;margin:0 0 20px;color:var(--ink);text-wrap:balance}
.mq-opts{display:flex;flex-direction:column;gap:9px}
.mq-opt{width:100%;text-align:right;padding:16px 18px;font:inherit;font-size:16px;color:var(--ink);
  background:var(--surface);border:1px solid var(--border);border-radius:13px;cursor:pointer;
  transition:border-color .18s cubic-bezier(.23,1,.32,1),transform .12s cubic-bezier(.23,1,.32,1)}
.mq-opt:hover{border-color:var(--ink)}
.mq-opt:active{transform:scale(.985)}
.mq-count{display:flex;align-items:center;gap:14px;justify-content:center;margin-top:20px;
  color:var(--muted);font-size:14px}
.mq-count b{font-size:20px;color:var(--ink);min-width:28px;text-align:center}
.mq-pm{width:44px;height:44px;border-radius:50%;border:1px solid var(--border);background:var(--surface);
  color:var(--ink);font-size:20px;cursor:pointer;line-height:1}
.mq-pm:active{transform:scale(.95)}
.mq-skip{display:block;width:100%;margin-top:12px;background:none;border:0;color:var(--muted);
  font:inherit;font-size:13.5px;cursor:pointer;padding:8px;text-decoration:underline}
.mq-why{display:flex;flex-direction:column;gap:5px;margin:8px 0 2px;font-size:13.5px}
.mq-why span{display:flex;gap:7px;align-items:flex-start;color:var(--ink)}
.mq-trade{display:flex;gap:7px;align-items:flex-start;font-size:13px;color:var(--muted);margin-top:6px}
.mq-head{margin:0 0 6px;font-size:21px;color:var(--ink)}
.mq-sub{margin:0 0 18px;color:var(--muted);font-size:14px}
@media (prefers-reduced-motion: reduce){
  .mq-dot,.mq-opt{transition:none}
  .mq-opt:active,.mq-pm:active{transform:none}
}
```

- [ ] **Step 3: Verify the SPA still parses (this gate is non-negotiable)**

```bash
python3 -c "
import bot, esprima, re
n=0
for js in re.findall(r'<script>(.*?)</script>', bot.STAY_HTML, re.S):
    esprima.parseScript(js); n+=1
print('parsed', n, 'script blocks OK')
"
```
Expected: `parsed N script blocks OK`. If esprima is missing: `pip install esprima`.
A parse error here means the entire `/stay` site is dead — fix before continuing.

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat(stay): Match quiz UI — four conditional screens in the STAY_HTML SPA"
```

---

## Task 10: The results view

**Files:**
- Modify: `bot.py` — `STAY_HTML` (add `mqResults`, `mqCard`)

- [ ] **Step 1: Add the results renderer**

Add to the same `<script>` block, after `mqSubmit`:

```javascript
function mqCard(l){
  var why=(l.reasons||[]).map(function(r){return '<span>✓ '+he(r)+'</span>';}).join('');
  var tr=l.tradeoff?('<div class="mq-trade">⚠︎ '+he(l.tradeoff)+'</div>'):'';
  var img=l.cover?('<img loading="lazy" width="600" height="400" alt="'+he(l.name_ar)+'" src="'+he(l.cover)+'">'):'<div class="noimg">صورة غير متوفرة</div>';
  var price=(l.est_total!=null&&l.nights>0)
    ?('<div class="price"><b>من '+money(l.est_avg)+' / الليلة</b> · الإجمالي التقريبي '+money(l.est_total)+'</div>')
    :'<div class="price soft">السعر يظهر داخل Airbnb</div>';
  return '<a class="card lc" href="/stay/'+he(l.slug)+'">'
    +'<div class="ph">'+img+'</div><div class="bd">'
    +'<h3 class="clamp2">'+he(l.name_ar||l.name_en)+'</h3>'
    +(l.area?('<div class="meta">📍 '+he(l.area)+'</div>'):'')
    +'<div class="mq-why">'+why+'</div>'+tr+price
    +'<div class="cta-row" style="margin-top:auto;padding-top:8px"><span class="btn block sm">شوف التفاصيل</span></div>'
    +'</div></a>';
}

function mqResults(q){
  V.innerHTML='<div class="mq-wrap"><div class="sk" style="height:20px;width:55%;margin-bottom:16px"></div>'
    +'<div class="sk" style="height:200px;border-radius:14px"></div></div>';
  fetch('/api/stay/match'+q).then(function(r){return r.json();}).then(function(d){
    var top=(d&&d.top)||[],near=(d&&d.near)||[];
    var medical=(d&&d.answers&&d.answers.purpose==='medical');

    if(d&&d.impossible){
      V.innerHTML='<div class="mq-wrap"><h2 class="mq-head">ما عندنا وحدة تكفي هالعدد</h2>'
        +'<p class="mq-sub">أكبر وحدة عندنا تستوعب '+he(String(d.max_capacity||0))+' ضيوف. لو تبون تقسمون على وحدتين نقدر نساعدكم.</p>'
        +'<a class="btn block" href="/stay">تصفح كل الوحدات</a></div>';
      track('match_results',{count:0});return;
    }
    if(!top.length){
      V.innerHTML='<div class="mq-wrap"><h2 class="mq-head">ما لقينا وحدات متاحة بهذي التواريخ</h2>'
        +'<p class="mq-sub">جرّب تواريخ ثانية، أو تصفح الوحدات بدون تحديد تاريخ.</p>'
        +'<a class="btn block" href="/stay">تصفح الوحدات</a></div>';
      track('match_results',{count:0});return;
    }

    // The علاج path drops the celebratory register: no emoji, no upsell, distance first.
    var head,sub;
    if(medical){
      head='هذي أقرب وحداتنا';sub='رتبناها حسب قربها من المستشفى. دخول ذاتي، بدون استقبال.';
    } else if(d.confident){
      head='لقينا لك '+top.length+' وحدات تناسبك';sub='مرتبة حسب الأقرب لطلبك.';
    } else {
      head='ما عندنا وحدة تطابق كل شي';sub='هذي الأقرب لطلبك — شفنا لك أفضل الموجود بصراحة.';
    }

    var html='<div class="mq-wrap"><h2 class="mq-head">'+he(head)+'</h2><p class="mq-sub">'+he(sub)+'</p>'
      +'<div class="grid">'+top.map(mqCard).join('')+'</div>';
    if(near.length){
      html+='<h3 class="mq-head" style="font-size:17px;margin:26px 0 10px">قريبة كمان</h3>'
        +'<div class="grid">'+near.slice(0,3).map(mqCard).join('')+'</div>';
    }
    html+='<button type="button" class="mq-skip" id="mqAgain">جاوب من جديد</button></div>';
    V.innerHTML=html;
    var again=document.getElementById('mqAgain');
    if(again)again.onclick=function(){location.href='/stay/match';};
    // guests + type are already whitelisted by _api_stay_event; count + weak are
    // added in Task 12. Together these four make the unmet-demand table possible.
    track('match_results',{count:top.length,guests:MQ.party,
                           type:(MQ.purpose||'rest'),weak:(d.confident?0:1)});
  }).catch(function(){
    V.innerHTML='<div class="mq-wrap"><h2 class="mq-head">صار خلل بسيط</h2>'
      +'<p class="mq-sub">جرّب مرة ثانية، أو تصفح الوحدات مباشرة.</p>'
      +'<a class="btn block" href="/stay">تصفح الوحدات</a></div>';
  });
}
```

- [ ] **Step 2: Verify the SPA parses**

```bash
python3 -c "
import bot, esprima, re
for js in re.findall(r'<script>(.*?)</script>', bot.STAY_HTML, re.S): esprima.parseScript(js)
print('STAY_HTML JS OK')
"
```
Expected: `STAY_HTML JS OK`

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat(stay): Match results — reasons, honest tradeoff, quiet medical register"
```

---

## Task 11: Entry points

**Files:**
- Modify: `bot.py` — `STAY_HTML` (`viewLanding`, `viewSearch` zero-results state)

- [ ] **Step 1: Add the landing entry**

In `viewLanding`, find the credibility line:

```javascript
    +'<div class="cred"><span>إقامات عوجا في الرياض</span>·<span>الحجز داخل Airbnb</span>'
```

Insert a match entry immediately **before** that line:

```javascript
    +'<a class="mq-entry" href="/stay/match">محتار؟ جاوبنا بأربع أسئلة ونختار لك — ١٠ ثواني</a>'
```

- [ ] **Step 2: Replace the zero-results dead end**

In `viewSearch`, find the empty state (`bot.py:46166`) containing
`ما لقينا وحدات بنفس الاختيارات`. Replace its action block. Change:

```javascript
<div style="margin-top:14px"><a class="btn" href="/stay'+location.search+'">عدّل البحث</a></div>
```

to:

```javascript
<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;justify-content:center"><a class="btn" href="/stay/match">خلّنا نختار لك</a><a class="btn ghost" href="/stay'+location.search+'">عدّل البحث</a></div>
```

- [ ] **Step 3: Add the entry style**

Append to the `<style>` block:

```css
.mq-entry{display:block;text-align:center;padding:14px 16px;margin:10px 0 14px;
  background:var(--surface);border:1px solid var(--border);border-radius:12px;
  color:var(--ink);text-decoration:none;font-size:14.5px;
  transition:border-color .18s cubic-bezier(.23,1,.32,1)}
.mq-entry:hover{border-color:var(--ink)}
```

- [ ] **Step 4: Verify and commit**

```bash
python3 -c "
import bot, esprima, re
for js in re.findall(r'<script>(.*?)</script>', bot.STAY_HTML, re.S): esprima.parseScript(js)
print('STAY_HTML JS OK')
"
git add bot.py
git commit -m "feat(stay): Match entry points on the landing and the zero-results state"
```

---

## Task 12: Analytics

**Files:**
- Modify: `bot.py` — `_api_stay_event` key whitelist
- Test: `tests/test_match_api.py` (append)

`_api_stay_event` (`bot.py:46420`) whitelists the keys it records. Match events carry
`type` and `count`, which would currently be silently dropped.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_match_api.py`:

```python
class TestMatchEventKeys(unittest.TestCase):
    def test_event_whitelist_carries_match_fields(self):
        src = open("bot.py", encoding="utf-8").read()
        i = src.index("async def _api_stay_event")
        block = src[i:i + 1200]
        for key in ('"type"', '"guests"', '"count"', '"weak"'):
            self.assertIn(key, block, f"{key} missing from the event whitelist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_match_api.TestMatchEventKeys -v`
Expected: FAIL — `"count"` and `"weak"` are absent from the whitelist.

- [ ] **Step 3: Write the implementation**

In `_api_stay_event` (`bot.py:46425`), change:

```python
        ev = {k: b.get(k) for k in ("event", "session", "route", "referrer", "listing_id",
                                    "check_in", "check_out", "guests", "type",
                                    "utm_source", "utm_medium", "utm_campaign", "utm_content") if b.get(k) is not None}
```

to:

```python
        ev = {k: b.get(k) for k in ("event", "session", "route", "referrer", "listing_id",
                                    "check_in", "check_out", "guests", "type",
                                    "count", "weak",
                                    "utm_source", "utm_medium", "utm_campaign", "utm_content") if b.get(k) is not None}
```

Note `guests` and `type` are already whitelisted. The Match results event reuses them
(`guests` = party size, `type` = purpose), which is what makes the unmet-demand table in
Task 14 possible without inventing new fields.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_match_api -v`
Expected: PASS.

- [ ] **Step 5: Add the abandon event**

In `STAY_HTML`, inside `viewMatch`, after `MQ.step=0;mqRender();`, add:

```javascript
  window.addEventListener('pagehide',function(){
    if(MQ.step>0&&!location.search)track('match_abandon',{type:mqSteps()[MQ.step]||''});
  },{once:true});
```

- [ ] **Step 6: Verify and commit**

```bash
python3 -c "
import bot, esprima, re
for js in re.findall(r'<script>(.*?)</script>', bot.STAY_HTML, re.S): esprima.parseScript(js)
print('STAY_HTML JS OK')
"
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(OK|FAILED|Ran )"
git add bot.py tests/test_match_api.py
git commit -m "feat(stay): Match analytics — funnel events through the guest event pipeline"
```

---

## Task 13: Guide-coordinate coverage check (ops, on Railway)

This is the assumption the spec flags as unverifiable locally: the guide DB lives on the
Railway volume. Run this **after deploying**, before trusting proximity precision.

**Files:**
- Modify: `bot.py` — extend the existing guest-website diagnostics response

- [ ] **Step 1: Add the coverage number to diagnostics**

In `bot.py:48511`, find the diagnostics dict containing `"unmapped_tags"`. Add a
`match_geo` key alongside it:

```python
                  "match_geo": (lambda p, t: {"with_coords": len(p), "total": t})(
                      _match_geo_points(), len(_gw_visible_snaps())),
```

- [ ] **Step 2: Verify locally**

```bash
python3 -W error::SyntaxWarning -m py_compile bot.py && echo "PY OK"
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(OK|FAILED)"
```
Expected: `PY OK` and `OK`. Locally `with_coords` will read 0 (no guide DB in a local
checkout) — that is expected and is exactly why this check has to run on Railway.

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "chore(stay): surface Match geo coverage in guest-website diagnostics"
```

- [ ] **Step 4: After deploy, read the number**

Open the dashboard Guest Website tab and read `match_geo`. Interpretation:

| `with_coords / total` | Action |
| --- | --- |
| > 70% | Proximity is precise. Nothing to do. |
| 30-70% | Working, less precise. Add centroids for any neighborhood holding uncovered units. |
| < 30% | Proximity is effectively neighborhood-level. Tell the owner plainly; consider raising the `bedrooms` weight and lowering `proximity` in `WEIGHTS`. |

---

## Task 14: Dashboard «المطابقة» panel

**Files:**
- Modify: `bot.py` — guest-website dashboard view + a stats endpoint

- [ ] **Step 1: Add the stats aggregator**

In `bot.py`, immediately before `async def _api_stay_match`, add:

There is no generic event reader in `bot.py`. Events live in the `_gw_analytics["events"]`
list, each stamped with an ISO `ts`, and `_gw_analytics_summary` (`bot.py:45880`) filters
them inline against a cutoff. `_match_stats` follows that exact pattern:

```python
def _match_stats(days=30):
    """Quiz funnel + unmet demand from the guest analytics store. Read-only.
    Returns zeros rather than raising when there is no data yet.

    The unmet-demand table is the highest-value output of this feature: it names
    the (purpose, party size) combinations we keep failing to serve."""
    cutoff = (datetime.now(TZ) - timedelta(days=days)).isoformat(timespec="seconds")
    evs = [e for e in _gw_analytics.get("events", []) if (e.get("ts") or "") >= cutoff]

    funnel = {"start": 0, "who": 0, "sleep": 0, "purpose": 0, "results": 0, "abandon": 0}
    demand = {}          # (purpose, party) -> {"asked": n, "weak": n}
    for e in evs:
        name = e.get("event") or ""
        if name == "match_start":
            funnel["start"] += 1
        elif name == "match_answer":
            k = e.get("type") or ""
            if k in funnel:
                funnel[k] += 1
        elif name == "match_abandon":
            funnel["abandon"] += 1
        elif name == "match_results":
            funnel["results"] += 1
            try:
                party = int(e.get("guests") or 0)
            except (TypeError, ValueError):
                party = 0
            key = (str(e.get("type") or "rest"), party)
            d = demand.setdefault(key, {"asked": 0, "weak": 0})
            d["asked"] += 1
            if e.get("weak") or not e.get("count"):
                d["weak"] += 1

    unmet = [{"purpose": p, "party": n, "asked": d["asked"], "weak": d["weak"],
              "weak_pct": round(100.0 * d["weak"] / d["asked"], 1) if d["asked"] else 0.0}
             for (p, n), d in demand.items() if d["weak"]]
    unmet.sort(key=lambda r: (-r["weak"], -r["asked"]))

    return {"funnel": funnel, "unmet": unmet[:12],
            "completion": (round(100.0 * funnel["results"] / funnel["start"], 1)
                           if funnel["start"] else 0.0)}
```

- [ ] **Step 2: Expose it**

Add beside the other stay API handlers:

```python
async def _api_stay_match_stats(request):
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    return _json({"ok": True, **_match_stats(30)})
```

Register it with the **authenticated** dashboard API routes (not the public `/api/stay/*`
group):

```python
        app.router.add_get("/api/stay/match-stats", _api_stay_match_stats)
```

- [ ] **Step 3: Render the panel**

In the dashboard's Guest Website view (`gwGo` / the `gw` tab), add a «المطابقة» button
that fetches `/api/stay/match-stats` and renders two blocks, using the existing
`fbCard()` / `fbChip()` helpers already used in that view:

1. **Funnel** — `start → who → sleep → purpose → results`, plus the completion percentage
   and the abandon count. Shows exactly which question loses people.
2. **جدول الطلب غير الملبّى** — one row per `unmet` entry:
   `الغرض · عدد الضيوف · كم مرة انطلبت · كم مرة ما لقينا` with `weak_pct`. Sorted worst
   first. This is the row the owner acts on ("31% of guests wanting X left with nothing").

Render an explicit empty state when `unmet` is `[]` — «ما فيه طلبات ما قدرنا نلبيها» —
rather than an empty table, which reads as broken.

**`DASHBOARD_HTML` is NOT a raw string.** Never write a backslash escape inside its JS —
use `String.fromCharCode(10)` for newlines. See the CLAUDE.md trap list.

- [ ] **Step 4: Verify — both HTML surfaces**

```bash
python3 -c "
import bot, esprima, re
for name in ('DASHBOARD_HTML','STAY_HTML'):
    for js in re.findall(r'<script>(.*?)</script>', getattr(bot,name), re.S):
        esprima.parseScript(js)
    print(name, 'JS OK')
"
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(OK|FAILED|Ran )"
```
Expected: both `JS OK` lines, and `OK`.

- [ ] **Step 5: Commit**

```bash
git add bot.py
git commit -m "feat(dashboard): المطابقة panel — Match funnel and completion rate"
```

---

## Final verification before push

- [ ] **Run the complete routine**

```bash
cd /Users/faisalouja/Ouja-Turnover
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py && echo "PY_COMPILE OK"
python3 -m pyflakes bot.py finance/*.py match/*.py | grep -v "imported but unused"
node --check finance/static/erp.js && echo "NODE OK"
python3 -c "
import bot, esprima, re
for name in ('DASHBOARD_HTML','STAY_HTML'):
    for js in re.findall(r'<script>(.*?)</script>', getattr(bot,name), re.S):
        esprima.parseScript(js)
    print(name,'JS OK')
"
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(OK|FAILED|Ran )"
```

All must pass. `Ran` should be roughly 587 + 45 new tests.

- [ ] **Manual pass** (start the server locally or check on Railway after deploy)

  - `/stay/match` loads and is **not** swallowed by `/stay/{slug}`
  - Solo traveller sees 3 screens; a party of 5 sees 4 (the sleeping question appears)
  - Results always show at least one unit, or the honest impossible/no-dates state
  - Every card shows at least one reason
  - `purpose=medical` shows the quiet register (no celebratory copy)
  - Back button returns to the quiz, not out of the site
  - 375px width: no horizontal scroll, buttons at least 44px tall
  - `prefers-reduced-motion` enabled: no transforms or transitions fire

- [ ] **Push** — only after every box above is checked, and confirm the target branch
      with the owner first (currently `deploy-teampur`, not `main`). Pushing triggers a
      Railway redeploy. Never rapid-redeploy this bot (see the Musaed spam incident).
