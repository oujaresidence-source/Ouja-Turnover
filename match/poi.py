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
