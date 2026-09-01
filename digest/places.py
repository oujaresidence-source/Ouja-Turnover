# -*- coding: utf-8 -*-
"""digest.places — district chips and proximity WITHOUT Google Places (the repo has no
Places tooling and the owner declined a Maps key). A curated venue→district table
(digest/data/venues.json, owner-editable via $STATE_DIR) plus the district centroids
match/poi.py already holds. Unknown venue → «الرياض», never a guess.

Proximity is measured to the nearest Ouja unit pin (coverage_study/seed_locations.json,
36 real coordinates) rather than to hand-typed compound centres: the pins are the
truth we already have. Pure once loaded (file reads happen at import, guarded)."""

import json
import os

from match.poi import NEIGHBOURHOOD_CENTROIDS, haversine_km

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
_SEED = os.path.join(HERE, "data", "venues.json")
_PINS = os.path.join(ROOT, "coverage_study", "seed_locations.json")

DEFAULT_DISTRICT = "الرياض"

# Fallback when the pin file is missing: three compound centres verified from the pins
# on 2026-09-02 (Dyar20, Hue, Al Majdiah).
FALLBACK_POINTS = ((24.8284, 46.5932), (24.8094, 46.5951), (24.7600, 46.6635))


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _venues(override_path=None):
    for p in (override_path, _SEED):
        if p and os.path.exists(p):
            d = _load_json(p)
            if d and isinstance(d.get("venues"), list):
                return d["venues"]
    return []


VENUES = _venues()


def reload(override_path=None):
    """Re-read the table (the owner may edit $STATE_DIR/digest/venues.json)."""
    global VENUES
    VENUES = _venues(override_path)
    return len(VENUES)


def _match(blob):
    blob = (blob or "").lower()
    if not blob:
        return None
    generic = None
    for v in VENUES:
        for k in v.get("keys") or []:
            if k.lower() in blob:
                if v["district"] == DEFAULT_DISTRICT:
                    generic = generic or v
                else:
                    return v
    return generic


def district_for(venue, address=""):
    """Only a district the text confirms; otherwise «الرياض»."""
    v = _match(" ".join(x for x in (venue, address) if x))
    if v:
        return v["district"]
    for slug, (lat, lng) in NEIGHBOURHOOD_CENTROIDS.items():
        name = slug.replace("_", " ")
        if name and name in (venue or "").lower():
            return slug
    return DEFAULT_DISTRICT


def coords_for(venue, address=""):
    v = _match(" ".join(x for x in (venue, address) if x))
    if v and v.get("lat") is not None and v["district"] != DEFAULT_DISTRICT:
        return (float(v["lat"]), float(v["lng"]))
    return None


def ouja_points():
    d = _load_json(_PINS)
    pts = []
    if isinstance(d, dict):
        for v in d.values():
            try:
                pts.append((float(v["lat"]), float(v["lng"])))
            except Exception:
                continue
    return pts or list(FALLBACK_POINTS)


OUJA_POINTS = ouja_points()


def km_to_nearest_ouja(latlng, points=None):
    if not latlng:
        return None
    pts = points or OUJA_POINTS
    return min(haversine_km(latlng, p) for p in pts)


def proximity_score(latlng, points=None, horizon_km=25.0):
    """1.0 at the door, 0 at horizon_km and beyond; None location → 0.35 (unknown,
    neither rewarded nor punished hard)."""
    km = km_to_nearest_ouja(latlng, points)
    if km is None:
        return 0.35
    return max(0.0, 1.0 - km / horizon_km)
