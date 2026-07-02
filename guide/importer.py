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


def _fetch_media(url, dest, http_get):
    """Download one image; True on success. Refuses HTML (private/dead Drive
    links serve an HTML interstitial) and oversized files."""
    r = http_get(drive_direct(url), timeout=30)
    ctype = (r.headers.get("content-type") or "").lower()
    body = r.content or b""
    if r.status_code != 200 or "text/html" in ctype or not body:
        return False
    if len(body) > MAX_MEDIA_BYTES:
        return False
    with open(dest, "wb") as f:
        f.write(body)
    return True


def _ext_for(url, default=".jpg"):
    m = re.search(r"\.(jpe?g|png|webp|gif|avif)(?:\?|$)", (url or "").lower())
    return ("." + m.group(1)) if m else default


def import_csv(path, media_dir=None, http_get=None, listings_map=None,
               fetch_media=True):
    """Run the import. Returns the owner report:
    {units, created, updated, matched, unmatched:[names], media_ok,
     media_failed:[{slug,field,url}], media_skipped}."""
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    report = {"units": len(rows), "created": 0, "updated": 0,
              "matched": 0, "unmatched": [],
              "media_ok": 0, "media_failed": [], "media_skipped": 0}
    if fetch_media and http_get is None:
        import requests
        http_get = requests.get
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
                    if _fetch_media(url, dest, http_get):
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
    return report
