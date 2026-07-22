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

    # ---- Added to cover the remaining bot.RIYADH_NEIGHBORHOODS keys (previously
    # only 35/93 were mapped, so units in any of the other 58 silently lost
    # proximity scoring). Approximate district centres from general knowledge of
    # Riyadh geography, grouped by confidence — see the commit/report for which
    # entries are lower-confidence and worth a human spot-check.

    # -- higher confidence (well-known, major districts)
    "al_falah":       (24.7550, 46.6100),
    "al_dirah":       (24.6293, 46.7127),
    "al_batha":       (24.6420, 46.7180),
    "al_murabba":     (24.6480, 46.7160),
    "manfuhah":       (24.6050, 46.7250),
    "al_suwaidi":     (24.6100, 46.6550),
    "al_badiah":      (24.6400, 46.6200),
    "namar":          (24.5750, 46.6100),
    "tuwaiq":         (24.5550, 46.5850),
    "dirab":          (24.4700, 46.6200),
    "dhahrat_laban":  (24.6050, 46.5600),
    "al_naseem":      (24.7350, 46.7700),
    "al_rimal":       (24.7750, 46.8350),
    "al_andalus":     (24.7550, 46.7500),
    "al_khaleej":     (24.7450, 46.7650),
    "ishbiliyah":     (24.7700, 46.8200),
    "al_hamra":       (24.8100, 46.7800),
    "al_shimaisi":    (24.6520, 46.7000),
    "al_wusham":      (24.6550, 46.6850),
    "al_rabi":        (24.8180, 46.6550),

    # -- medium confidence
    "al_wizarat":     (24.6550, 46.7100),
    "al_futah":       (24.6600, 46.7080),
    "al_morabba":     (24.6850, 46.6650),
    "al_mathar_north": (24.6950, 46.6680),
    "al_jaradiyah":   (24.6480, 46.6750),
    "al_oud":         (24.6150, 46.7350),
    "al_qadisiyah":   (24.7550, 46.8100),
    "al_uraija":      (24.6300, 46.6000),
    "al_hazm":        (24.6550, 46.6100),
    "shubra":         (24.6200, 46.6350),
    "laban":          (24.5900, 46.5750),
    "al_shifa":       (24.5700, 46.7300),
    "al_faisaliyah":  (24.5600, 46.7200),
    "al_aziziyah":    (24.5550, 46.7100),
    "al_munisiyah":   (24.8250, 46.8050),
    "al_yarmuk":      (24.7650, 46.7950),
    "al_nahdah":      (24.7500, 46.8050),
    "al_fayha":       (24.7350, 46.7900),

    # -- lower confidence (smaller/less-documented districts — a human should
    # spot-check these against a map before relying on them for anything but
    # rough ranking)
    "al_qadisiyah_e": (24.7450, 46.8150),  # غبيرة / Ghubairah
    "al_salam":       (24.7350, 46.8250),
    "al_jazirah":     (24.7450, 46.8350),
    "al_manar":       (24.7200, 46.8150),
    "al_rajhi":       (24.7100, 46.8300),  # الرجاء / Al Raja
    "al_wurud2":      (24.7600, 46.8400),  # المروة / Al Marwah
    "al_raid":        (24.8050, 46.8100),
    "al_rawabi":      (24.8150, 46.8300),
    "al_mahdiyah":    (24.6150, 46.5900),
    "al_dar_al_baida": (24.5450, 46.7250),
    "badr":           (24.5350, 46.7150),
    "al_mansouriyah": (24.5500, 46.6950),
    "al_rayyan":      (24.5650, 46.6950),
    "al_quds":        (24.7900, 46.8500),
    "al_maizilah":    (24.7100, 46.8100),
    "al_iskan":       (24.6100, 46.7850),
    "al_difa":        (24.6000, 46.7950),
    "al_marqab":      (24.5950, 46.7550),
    "al_doha":        (24.5750, 46.7450),
    "al_wadi2":       (24.5850, 46.7700),  # النموذجية / Al Namudhajiyah
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


def _is_real_coord_pair(pt):
    """True only for an actual 2-element tuple/list of real numbers. A string
    like "24" is length-2 but NOT a coordinate pair — indexing it would silently
    fabricate (2.0, 4.0), a nonsense point in the Atlantic. Reject it here."""
    if not isinstance(pt, (tuple, list)) or len(pt) != 2:
        return False
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pt)


def resolve_point(unit, geo):
    """(lat, lng) for a unit. Exact coords when known, else the centroid of its
    assigned neighborhood, else None. Never raises, and never fabricates a
    coordinate from malformed input — falls through to the centroid (then
    None) instead."""
    if not isinstance(unit, dict):
        return None
    pt = geo.get(unit.get("id")) if isinstance(geo, dict) else None
    if _is_real_coord_pair(pt):
        return (float(pt[0]), float(pt[1]))
    centroid = NEIGHBOURHOOD_CENTROIDS.get(unit.get("neighborhood") or "")
    if centroid is None:
        return None
    return (float(centroid[0]), float(centroid[1]))


def minutes_to(km):
    """Approximate drive minutes for a straight-line distance. The 1.35 factor
    accounts for road routing versus the crow-flies line."""
    return max(1, int(round((km * 1.35) / _AVG_KMH * 60)))
