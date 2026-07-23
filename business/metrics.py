# -*- coding: utf-8 -*-
"""
business.metrics — the verified operating record behind /business.

Three parts, one boundary:

  fetch_snapshot()  -> raw     LIVE I/O. Pulls listings, reservations, reviews from
                               Hostaway (reusing bot's client) and NORMALIZES them
                               into the `raw` contract below. Not unit-tested against
                               live; it only shapes data.
  compute_metrics(raw) -> dict PURE. The entire business logic. Fully unit-tested,
                               golden-locked. The numbers here get quoted in
                               negotiations, so a silent change is a commercial
                               regression, not a UI bug (superprompt §3).
  write_snapshot(dict)         Atomic write to STATE_DIR (tmp + os.replace).

The `raw` contract (what fetch_snapshot produces and compute_metrics consumes):

    {
      "as_of":   "YYYY-MM-DD",
      "channel": "airbnb",
      "window":  {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
      "listings": [
        {"id", "name", "created": "YYYY-MM-DD", "active": bool,
         "district": str|None, "bedrooms": int|None, "property_type": str|None}, ...
      ],
      "reservations": [
        {"id", "guest_key": str, "arrival": "YYYY-MM-DD", "departure": "YYYY-MM-DD",
         "listing_id", "status", "channel"}, ...
      ],
      "reviews": [
        {"id", "listing_id", "rating10": 0..10, "categories": {name: 0..10, ...},
         "text": str, "date": "YYYY-MM-DD", "lang": "ar"|"en"|None,
         "channel", "public": bool}, ...
      ],
    }

Keeping compute_metrics pure over this normalized contract is what lets the golden
regression test assert exact numbers without touching the network.
"""
from collections import Counter, defaultdict
from datetime import date, datetime

# Airbnb's six guest-review sub-scores, in the order the page renders them.
CATEGORY_ORDER = ("communication", "checkin", "accuracy", "location", "cleanliness", "value")

# Hostaway confirmed-reservation statuses.
CONFIRMED_STATUSES = ("new", "modified")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _parse_date(s):
    """'YYYY-MM-DD' (or an ISO datetime prefix) -> date, else None."""
    if not s:
        return None
    if isinstance(s, (date, datetime)):
        return s.date() if isinstance(s, datetime) else s
    txt = str(s).strip()
    if not txt:
        return None
    try:
        return datetime.strptime(txt[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _quarter_key(d):
    """date -> (year, quarter_int)."""
    return (d.year, (d.month - 1) // 3 + 1)


def _quarter_label(yq):
    year, q = yq
    return "Q%d'%02d" % (q, year % 100)


def _iter_quarters(start, end):
    """Inclusive walk of (year, quarter) tuples from start to end."""
    y, q = start
    ey, eq = end
    out = []
    while (y, q) <= (ey, eq):
        out.append((y, q))
        q += 1
        if q > 4:
            q = 1
            y += 1
    return out


def _is_arabic(text):
    """True if the string carries any Arabic-script character."""
    return any("؀" <= ch <= "ۿ" for ch in (text or ""))


def _share(n, d, places=4):
    return round(n / d, places) if d else 0.0


# --------------------------------------------------------------------------- #
# the pure core
# --------------------------------------------------------------------------- #
def compute_metrics(raw):
    """Normalized raw payload -> the metrics dict rendered by /business.

    Pure. No I/O, no clock, no globals. Same input -> byte-identical output.
    """
    listings = raw.get("listings") or []
    reservations = raw.get("reservations") or []
    reviews = raw.get("reviews") or []
    as_of = raw.get("as_of")

    out = {
        "as_of": as_of,
        "channel": raw.get("channel"),
        "window": raw.get("window"),
    }

    # ---- reservations ---------------------------------------------------- #
    nights_per_res = []
    guest_counter = Counter()
    for r in reservations:
        guest_counter[r.get("guest_key")] += 1
        a = _parse_date(r.get("arrival"))
        d = _parse_date(r.get("departure"))
        nights_per_res.append((d - a).days if a and d else 0)

    total_res = len(reservations)
    guest_nights = sum(nights_per_res)
    returning = {g for g, c in guest_counter.items() if c >= 2}
    stays_by_returning = sum(c for g, c in guest_counter.items() if c >= 2)
    single_night = sum(1 for n in nights_per_res if n == 1)

    out["reservations_total"] = total_res
    out["guest_nights"] = guest_nights
    out["unique_guests"] = len(guest_counter)
    out["returning_guests"] = len(returning)
    out["repeat_guest_share"] = _share(stays_by_returning, total_res)
    out["avg_los"] = round(guest_nights / total_res, 2) if total_res else 0.0
    out["single_night_share"] = _share(single_night, total_res)

    # ---- reviews (published = has written text AND public) --------------- #
    published = [
        v for v in reviews
        if (v.get("text") or "").strip() and v.get("public", True)
    ]
    n_pub = len(published)

    ratings10 = [v.get("rating10") for v in published if v.get("rating10") is not None]
    out["reviews_published"] = n_pub
    out["rating_avg_5"] = round(sum(ratings10) / len(ratings10) / 2, 2) if ratings10 else 0.0
    out["perfect_share"] = _share(sum(1 for x in ratings10 if x == 10), len(ratings10))
    out["review_rate"] = _share(n_pub, total_res)

    # honest rating distribution (§5 A4.1) — counts per 10-scale score, published only
    dist = Counter(str(x) for x in ratings10)
    out["rating_distribution"] = dict(dist)

    # category sub-scores, only categories that actually appear
    cat_sum, cat_n = defaultdict(float), defaultdict(int)
    for v in published:
        for name, score in (v.get("categories") or {}).items():
            if score is None:
                continue
            cat_sum[name] += score
            cat_n[name] += 1
    ordered = [c for c in CATEGORY_ORDER if c in cat_sum] + \
              [c for c in cat_sum if c not in CATEGORY_ORDER]
    out["category_avgs"] = {c: round(cat_sum[c] / cat_n[c], 2) for c in ordered}

    # language split over published reviews (detect when not tagged)
    lang_counter = Counter()
    for v in published:
        lang = v.get("lang")
        if lang not in ("ar", "en"):
            lang = "ar" if _is_arabic(v.get("text")) else "en"
        lang_counter[lang] += 1
    out["review_lang_split"] = {
        "ar": _share(lang_counter.get("ar", 0), n_pub),
        "en": _share(lang_counter.get("en", 0), n_pub),
    }

    # reviews per quarter — continuous, zero-filled, with per-quarter rating
    q_count, q_rsum, q_rn = Counter(), defaultdict(int), defaultdict(int)
    review_quarters = []
    for v in published:
        d = _parse_date(v.get("date"))
        if not d:
            continue
        qk = _quarter_key(d)
        review_quarters.append(qk)
        q_count[qk] += 1
        if v.get("rating10") is not None:
            q_rsum[qk] += v["rating10"]
            q_rn[qk] += 1
    by_quarter = []
    if review_quarters:
        as_of_d = _parse_date(as_of)
        start_q = min(review_quarters)
        end_q = max(review_quarters)
        if as_of_d:
            end_q = max(end_q, _quarter_key(as_of_d))
        for qk in _iter_quarters(start_q, end_q):
            avg5 = round(q_rsum[qk] / q_rn[qk] / 2, 2) if q_rn[qk] else None
            by_quarter.append({"q": _quarter_label(qk), "count": q_count.get(qk, 0),
                               "rating_avg_5": avg5})
    out["reviews_by_quarter"] = by_quarter

    # ---- listings -------------------------------------------------------- #
    out["listings_active"] = sum(1 for l in listings if l.get("active"))

    created_years = [
        _parse_date(l.get("created")).year
        for l in listings if _parse_date(l.get("created"))
    ]
    listings_by_year = {}
    if created_years:
        as_of_d = _parse_date(as_of)
        start_y = min(created_years)
        end_y = max(created_years)
        if as_of_d:
            end_y = max(end_y, as_of_d.year)
        for y in range(start_y, end_y + 1):
            listings_by_year[str(y)] = sum(1 for cy in created_years if cy <= y)
    out["listings_by_year"] = listings_by_year

    out["districts_covered"] = len({
        (l.get("district") or "").strip() for l in listings if (l.get("district") or "").strip()
    })

    bed_counter = Counter()
    for l in listings:
        b = l.get("bedrooms")
        if b is not None:
            bed_counter[str(b)] += 1
    out["unit_type_mix"] = dict(bed_counter)

    return out


# --------------------------------------------------------------------------- #
# live I/O boundary  (not unit-tested; it only shapes data)
# --------------------------------------------------------------------------- #
def _norm_guest_key(res):
    key = (res.get("guestName") or res.get("guestFirstName") or "").strip().lower()
    return key or ("res#" + str(res.get("id")))


_CAT_ALIASES = {
    "communication": "communication", "check_in": "checkin", "checkin": "checkin",
    "check-in": "checkin", "accuracy": "accuracy", "location": "location",
    "cleanliness": "cleanliness", "value": "value",
}


def _norm_review(v):
    raw = v.get("raw") or {}
    rating10 = v.get("rating_raw")
    if rating10 is None and v.get("rating") is not None:
        rating10 = round(v["rating"] * 2)
    cats = {}
    for c in (raw.get("reviewCategory") or raw.get("categories") or []):
        name = _CAT_ALIASES.get(str(c.get("category", "")).lower())
        if name and c.get("rating") is not None:
            cats[name] = c["rating"]
    text = v.get("public_review") or ""
    return {
        "id": v.get("id"),
        "listing_id": v.get("listing_id"),
        "rating10": rating10,
        "categories": cats,
        "text": text,
        "date": (v.get("date") or "")[:10],
        "lang": "ar" if _is_arabic(text) else "en",
        "channel": v.get("channel"),
        "public": v.get("is_public", True),
    }


def fetch_snapshot(as_of=None, window_start=None, window_end=None,
                   api_get=None, fetch_reservations_window=None,
                   fetch_reviews=None, get_listings=None):
    """Pull live Hostaway data and normalize it into the `raw` contract.

    Dependencies are injected (the wire({...}) pattern) so this stays decoupled
    from bot internals; they lazy-default to the bot module when omitted.
    """
    if api_get is None or fetch_reservations_window is None or fetch_reviews is None:
        import bot  # lazy: avoid importing the whole app at module load
        api_get = api_get or bot.api_get
        fetch_reservations_window = fetch_reservations_window or bot.fetch_reservations_window
        fetch_reviews = fetch_reviews or bot.fetch_reviews_from_hostaway

    today = _parse_date(as_of) or datetime.utcnow().date()
    as_of = today.isoformat()
    end = window_end or as_of
    start = window_start or today.replace(year=today.year - 2).isoformat()

    # listings
    listings = []
    try:
        resp = api_get("/listings", params={"limit": 500}) if api_get else {}
        for l in (resp.get("result") or []):
            listings.append({
                "id": l.get("id"),
                "name": l.get("internalListingName") or l.get("name"),
                "created": (str(l.get("insertedOn") or l.get("createdOn") or "")[:10]) or None,
                "active": bool(l.get("active", True)),
                "district": (l.get("city") or None),
                "bedrooms": l.get("bedroomsNumber"),
                "property_type": l.get("propertyType"),
            })
    except Exception:
        listings = []

    # reservations (confirmed only)
    reservations = []
    try:
        for r in (fetch_reservations_window(start, end) or []):
            if r.get("status") not in CONFIRMED_STATUSES:
                continue
            reservations.append({
                "id": r.get("id"),
                "guest_key": _norm_guest_key(r),
                "arrival": (r.get("arrivalDate") or "")[:10],
                "departure": (r.get("departureDate") or "")[:10],
                "listing_id": r.get("listingMapId"),
                "status": r.get("status"),
                "channel": r.get("channelName"),
            })
    except Exception:
        reservations = []

    # reviews
    reviews = []
    try:
        reviews = [_norm_review(v) for v in (fetch_reviews() or [])]
    except Exception:
        reviews = []

    return {
        "as_of": as_of,
        "channel": "airbnb",
        "window": {"start": start, "end": end},
        "listings": listings,
        "reservations": reservations,
        "reviews": reviews,
    }


def write_snapshot(metrics, save_json=None, name="metrics_snapshot.json"):
    """Atomically persist the computed metrics dict. Reuses bot._save_json when
    injected (tmp + os.replace under STATE_DIR); otherwise does the same itself."""
    if save_json is not None:
        return bool(save_json(name, metrics))
    import json
    import os
    state_dir = os.environ.get("STATE_DIR", "/data")
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return True
