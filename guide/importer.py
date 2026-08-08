# -*- coding: utf-8 -*-
"""Import the Supabase `listings` export (supabase_export_listings.csv, 64 rows,
confirmed schema 2026-07-02) into guide_units, mirror the Google-Drive photos
into STATE_DIR/guide_media/{slug}/, and best-effort match each row to a
Hostaway listing. Idempotent — safe to re-run; produces an owner-readable
report of media/match failures. The Netlify site keeps working regardless."""

import csv
import json
import os
import re

from . import db

CSV_FIELDS = ("listing_name", "map_link",
              "complex_pic", "complex_caption", "building_pic", "building_caption",
              "elevator_pic", "elevator_caption", "door_pic", "door_caption",
              "wifi_name", "wifi_pass", "notes")
PIC_FIELDS = ("complex_pic", "building_pic", "elevator_pic", "door_pic")
MAX_MEDIA_BYTES = 15 * 1024 * 1024

_DRIVE_RX = (re.compile(r"drive\.google\.com/file/d/([^/?#]+)"),
             re.compile(r"drive\.google\.com/(?:open|uc)\?(?:export=\w+&)?id=([^&]+)"))


def drive_direct(url):
    """Google-Drive share link → direct-download form; other URLs unchanged."""
    for rx in _DRIVE_RX:
        m = rx.search(url or "")
        if m:
            return "https://drive.google.com/uc?export=download&id=" + m.group(1)
    return url or ""


def _norm_name(s):
    """Listing-name normalizer for Hostaway matching (brand word + non-alnum out)."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9؀-ۿ]+", " ", s)
    toks = [t for t in s.split() if t not in ("ouja", "عوجا")]
    return " ".join(toks)


def match_listing(name, listings_map):
    """CSV listing_name → Hostaway listing id. Exact normalized equality only —
    a wrong match would hang the wrong photos on a unit. None if ambiguous."""
    want = _norm_name(name)
    if not want:
        return None
    hits = [lid for lid, nm in (listings_map or {}).items() if _norm_name(nm) == want]
    return hits[0] if len(set(hits)) == 1 else None


# ---------------------------------------------------------------------------
#  NEW APARTMENTS FROM HOSTAWAY
#  The CSV above was a ONE-SHOT export (July 2026). Every apartment added to
#  Hostaway afterwards had no way into the guide at all — this is that way.
#  Pure functions: the route layer only feeds them the Hostaway rows and the
#  current guide units, so the whole rule set is testable without a network.
# ---------------------------------------------------------------------------
SLUG_MAX = 40


def slugify_name(name, max_len=SLUG_MAX):
    """Listing name → the public '/guide/{slug}' id, in the style the existing
    slugs already use ('spacious-mid-century-apt-self-entry'). Truncates on a
    word boundary; returns '' when the name carries no usable ASCII (Arabic-only
    names fall back to the listing id in suggest_slug)."""
    parts = [p for p in re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).split("-")
             if p and p != "ouja"]
    out = ""
    for p in parts:
        nxt = (out + "-" + p) if out else p
        if len(nxt) > max_len:
            break
        out = nxt
    return out


def suggest_slug(name, lid, taken):
    """A free slug for this listing. NEVER returns one already in `taken` — the
    slug is the public guest link, and a collision would overwrite a live page."""
    base = slugify_name(name)
    for cand in (base, ("%s-%s" % (base, lid)) if base else "", "ha-%s" % lid):
        if cand and cand not in taken:
            return cand
    n = 2
    while ("ha-%s-%d" % (lid, n)) in taken:
        n += 1
    return "ha-%s-%d" % (lid, n)


def _ha_names(L):
    """Every name a Hostaway listing record answers to (store shape + raw API)."""
    return [L.get("internal_name") or L.get("internalListingName") or "",
            L.get("public_name") or L.get("name") or ""]


def new_from_hostaway(listings, units):
    """Which LIVE Hostaway listings have no row in the guide yet.

    Returns {"new": [{lid, name, address, slug}], "in_guide": n,
             "unlinked": [{lid, name, slug}], "skipped_inactive": n}

    An apartment the guide already carries is NEVER offered — not by Hostaway
    id, and not by an exactly-matching name. A second row for the same
    apartment would split its photos across two guest pages, and the guest
    would land on whichever one we happened to link. Name matches that are
    missing the Hostaway id come back as `unlinked` (informational: those are
    the «غير مرتبطة» rows, fixed from the unit's own edit page)."""
    have_ids = set()
    by_name = {}
    taken = set()
    for u in (units or []):
        taken.add((u.get("slug") or "").strip().lower())
        try:
            if u.get("listing_id") is not None:
                have_ids.add(int(u["listing_id"]))
        except (TypeError, ValueError):
            pass
        nm = _norm_name(u.get("listing_name"))
        if nm:
            by_name.setdefault(nm, u.get("slug"))
    out = {"new": [], "in_guide": 0, "unlinked": [], "skipped_inactive": 0}
    for L in (listings or []):
        try:
            lid = int(L.get("id"))
        except (TypeError, ValueError):
            continue
        names = [n for n in _ha_names(L) if n]
        name = names[0] if names else ("#%d" % lid)
        if not L.get("active", True):
            out["skipped_inactive"] += 1
            continue
        if lid in have_ids:
            out["in_guide"] += 1
            continue
        hit = next((by_name[_norm_name(n)] for n in names if _norm_name(n) in by_name), None)
        if hit:
            out["unlinked"].append({"lid": lid, "name": name, "slug": hit})
            continue
        slug = suggest_slug(name, lid, taken)
        taken.add(slug)
        out["new"].append({"lid": lid, "name": name,
                           "address": (L.get("address") or L.get("city") or "").strip(),
                           "slug": slug})
    out["new"].sort(key=lambda r: r["name"].lower())
    return out


def _fetch_media(url, dest, http_get, url_cache=None):
    """Download one image; True on success. Refuses HTML (private/dead Drive
    links serve an HTML interstitial) and oversized files. `url_cache` dedupes
    across units — the Nuzha buildings share the SAME Drive photos, so 209
    links are only ~164 unique downloads."""
    direct = drive_direct(url)
    if url_cache is not None and direct in url_cache:
        src = url_cache[direct]
        if src is False:
            return False                 # known-dead link — don't wait again
        import shutil
        shutil.copyfile(src, dest)
        return True
    try:
        r = http_get(direct, timeout=12)
        ctype = (r.headers.get("content-type") or "").lower()
        body = r.content or b""
        ok = (r.status_code == 200 and "text/html" not in ctype
              and body and len(body) <= MAX_MEDIA_BYTES)
    except Exception:
        ok = False
    if not ok:
        if url_cache is not None:
            url_cache[direct] = False
        return False
    with open(dest, "wb") as f:
        f.write(body)
    if url_cache is not None:
        url_cache[direct] = dest
    return True


def _ext_for(url, default=".jpg"):
    m = re.search(r"\.(jpe?g|png|webp|gif|avif)(?:\?|$)", (url or "").lower())
    return ("." + m.group(1)) if m else default


def import_csv(path, media_dir=None, http_get=None, listings_map=None,
               fetch_media=True, progress=None):
    """Run the import. Returns the owner report:
    {units, created, updated, matched, unmatched:[names], media_ok,
     media_failed:[{slug,field,url}], media_skipped}.
    `progress(done, total, slug)` is called after each unit (background-job UI)."""
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    report = {"units": len(rows), "created": 0, "updated": 0,
              "matched": 0, "unmatched": [],
              "media_ok": 0, "media_failed": [], "media_skipped": 0}
    if fetch_media and http_get is None:
        import requests
        http_get = requests.get
    url_cache = {}                       # direct-url → local path | False (dead)
    done = 0
    for r in rows:
        slug = (r.get("id") or "").strip().lower()
        if not slug:
            continue
        existing = db.get_unit(slug)
        fields = {k: (r.get(k) or "").strip() for k in CSV_FIELDS}
        lid = match_listing(fields["listing_name"], listings_map)
        if lid is not None:
            fields["listing_id"] = int(lid)
            report["matched"] += 1
        else:
            report["unmatched"].append(fields["listing_name"] or slug)
        media = db.media_map(existing) if existing else {}
        if fetch_media:
            os.makedirs(os.path.join(media_dir or ".", slug), exist_ok=True)
            for pf in PIC_FIELDS:
                url = fields.get(pf) or ""
                if not url.startswith("http"):
                    continue
                fname = pf + _ext_for(url)
                dest = os.path.join(media_dir or ".", slug, fname)
                if media.get(pf) and os.path.exists(dest):
                    report["media_skipped"] += 1     # already mirrored — idempotent
                    continue
                try:
                    if _fetch_media(url, dest, http_get, url_cache):
                        media[pf] = fname
                        report["media_ok"] += 1
                    else:
                        report["media_failed"].append({"slug": slug, "field": pf, "url": url})
                except Exception:
                    report["media_failed"].append({"slug": slug, "field": pf, "url": url})
        fields["media_local"] = json.dumps(media, ensure_ascii=False)
        fields["active"] = 1
        db.upsert_unit(slug, **fields)
        report["created" if existing is None else "updated"] += 1
        done += 1
        if progress:
            try:
                progress(done, len(rows), slug)
            except Exception:
                pass
    return report
