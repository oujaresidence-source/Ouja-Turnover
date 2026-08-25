# -*- coding: utf-8 -*-
"""Turn the map links we already have into coordinates — once — and remember them.

Most of the pins in the guest guide are shortened `maps.app.goo.gl` links, which carry
no coordinates at all. Following the redirect yields a real street address; that address
then goes through Google's geocoder using the key already set on Railway.

Everything is cached to STATE_DIR and never fetched twice. A link that fails is cached
as a failure too, with the reason, so a broken pin shows up in the tab as a broken pin
instead of hammering Google on every page load.
"""

import re
import time
import urllib.parse

from .host import HOST

CACHE_FILE = "coverage_geo.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DEFAULT_BATCH = 40          # per request, so a page load can never hang on Google
SLEEP_S = 0.25


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def load_cache():
    fn = getattr(HOST, "load_json", None)
    if not callable(fn):
        return {}
    return fn(CACHE_FILE, {}) or {}


def save_cache(cache):
    fn = getattr(HOST, "save_json", None)
    if callable(fn):
        fn(CACHE_FILE, cache)


def _parse_effective(url):
    """(address, latlng) out of a resolved Google Maps URL."""
    try:
        q = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(q.query)
    except Exception:
        return "", None
    addr = (qs.get("q") or qs.get("query") or [""])[0]
    m = re.match(r"^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$", addr)
    if m:
        return "", (float(m.group(1)), float(m.group(2)))
    m = re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", url or "")
    if m:
        return addr, (float(m.group(1)), float(m.group(2)))
    return addr, None


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# OSM's policy demands an identifying User-Agent and at most one request a second.
NOMINATIM_UA = "OujaResidence-CoverageMap/1.0 (+https://oujares.com; ops@oujares.com)"
NOMINATIM_SLEEP_S = 1.1


def _geocode_osm(addr, session, out):
    """Street address -> coordinates via OpenStreetMap. Free, no key.

    The fallback when there is no Google key, which is the normal case here — the owner
    chose not to register one. Coverage in Riyadh is good for named streets and
    districts and poorer for plot codes, so a miss is recorded as a miss.
    """
    try:
        r = session.get(NOMINATIM_URL,
                        params={"q": addr, "format": "json", "limit": 1,
                                "countrycodes": "sa", "accept-language": "ar"},
                        timeout=20, headers={"User-Agent": NOMINATIM_UA})
        r.raise_for_status()
        res = r.json()
    except Exception as e:
        out["error"] = "osm geocode failed: %s" % str(e)[:120]
        return out
    finally:
        time.sleep(NOMINATIM_SLEEP_S)          # rate limit, always — even on failure
    if not res:
        out["error"] = "osm geocode: no result for this address"
        return out
    try:
        out.update(lat=float(res[0]["lat"]), lng=float(res[0]["lon"]),
                   address=res[0].get("display_name") or addr, source="osm")
    except (KeyError, TypeError, ValueError):
        out["error"] = "osm geocode: unreadable result"
    return out


def _geocode(addr, api_key, session, out):
    """Street address -> coordinates. Google when a key exists, OpenStreetMap when not."""
    if not api_key:
        return _geocode_osm(addr, session, out)
    try:
        g = session.get("https://maps.googleapis.com/maps/api/geocode/json",
                        params={"address": addr, "key": api_key, "region": "sa"}, timeout=20)
        data = g.json()
    except Exception as e:
        out["error"] = "geocode failed: %s" % str(e)[:120]
        return out
    if (data.get("status") or "") != "OK" or not data.get("results"):
        out["error"] = "geocode: %s" % (data.get("status") or "no result")
        return out
    loc = ((data["results"][0].get("geometry") or {}).get("location") or {})
    if loc.get("lat") is None or loc.get("lng") is None:
        out["error"] = "geocode returned no location"
        return out
    out.update(lat=float(loc["lat"]), lng=float(loc["lng"]),
               address=data["results"][0].get("formatted_address") or addr,
               source="geocode")
    return out


def resolve_link(url, api_key="", session=None):
    """One target -> {lat, lng, address, source, error}. Network. Call off the loop.

    The target is EITHER a Google Maps link OR a plain street address — most live
    apartments have an address on the listing but no pin, so both must work.
    """
    from . import engine
    out = {"lat": None, "lng": None, "address": "", "source": "", "error": "",
            "resolved_at": _now(), "link": url}

    direct = engine.extract_latlng(url)
    if direct:
        out.update(lat=direct[0], lng=direct[1], source="link")
        return out

    try:
        import requests
    except ImportError:
        out["error"] = "requests unavailable"
        return out

    s = session or requests

    # Not a URL at all → it is an address; skip the redirect hop entirely.
    if not str(url or "").lower().startswith(("http://", "https://")):
        out["address"] = str(url or "")
        if not out["address"].strip():
            out["error"] = "nothing to resolve"
            return out
        return _geocode(out["address"], api_key, s, out)

    try:
        r = s.get(url, allow_redirects=True, timeout=20, headers={"User-Agent": UA})
        effective = r.url or ""
    except Exception as e:
        out["error"] = "redirect failed: %s" % str(e)[:120]
        return out

    addr, ll = _parse_effective(effective)
    out["address"] = addr
    if ll:
        out.update(lat=ll[0], lng=ll[1], source="redirect")
        return out
    if not addr:
        out["error"] = "no address in resolved link"
        return out
    return _geocode(addr, api_key, s, out)


def resolve_missing(links, api_key="", batch=DEFAULT_BATCH, force=False):
    """Fill in whatever is not cached yet, up to `batch`. Returns (cache, report).

    Bounded on purpose: a request resolves at most `batch` links and reports how many
    are still pending, rather than blocking for minutes on a first run.
    """
    cache = load_cache()
    # RETRY FAILURES. Only a SUCCESS is permanent. The first version cached misses too,
    # so the very first press — made before the offline decoders existed — poisoned every
    # entry, and every press afterwards resolved nothing and reported "0 located" with no
    # hint why (owner, 2026-08-02).
    todo = [ln for ln in dict.fromkeys(l for l in links if l)
            if force or ln not in cache or cache[ln].get("lat") is None]
    done, failed = 0, 0
    for ln in todo[:batch]:
        rec = resolve_link(ln, api_key=api_key)
        cache[ln] = rec
        if rec.get("lat") is None:
            failed += 1
        else:
            done += 1
        time.sleep(SLEEP_S)
    if todo[:batch]:
        save_cache(cache)
    return cache, {"resolved": done, "failed": failed,
                   "pending": max(0, len(todo) - batch),
                   "cached_total": len(cache),
                   "have_key": bool(api_key)}


def apply_to_units(units, cache):
    """Fill coordinates on units that still have none, from the geo cache. Mutates rows.

    Only ever fills a BLANK — a coordinate already on the listing record wins, because
    that is the one the dispatch and ETA code uses.
    """
    n = 0
    for u in units:
        if u.get("has_location"):
            continue
        # geo_key is the map link when there is one, otherwise the street address.
        rec = cache.get(u.get("geo_key") or u.get("map_link") or "")
        if not rec or rec.get("lat") is None:
            continue
        u["lat"], u["lng"] = rec["lat"], rec["lng"]
        u["has_location"] = True
        u["coord_source"] = "geo:" + (rec.get("source") or "cache")
        if not u.get("district") and rec.get("address"):
            u["district"] = rec["address"]
        n += 1
    return n
