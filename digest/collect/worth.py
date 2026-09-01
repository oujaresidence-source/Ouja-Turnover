# -*- coding: utf-8 -*-
"""«يستاهل الزيارة» — Ouja's own curated list (digest/data/worth.json; a copy under
$STATE_DIR/digest/ wins). A place is eligible only with a url that passes the link
check. Entries without a url are resolved through the search tool (Task: search_secondary)
restricted to official domains, and stay ineligible when nothing verifiable comes back."""

import json
import os

from . import base

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(os.path.dirname(HERE), "data", "worth.json")
SOURCE = "Ouja"
SEARCH_DOMAINS = ("visitsaudi.com", "moc.gov.sa", "diriyah.sa", "kafd.sa", "rcrc.gov.sa", "riyadh.sa")


def load(override_path=None):
    for p in (override_path, SEED):
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
                if isinstance(d.get("places"), list):
                    return d["places"]
            except Exception:
                continue
    return []


def candidates(week, now, places_list=None, resolved_urls=None):
    """Pure: seed entries → Candidates. `resolved_urls` = {slug: url} found by the
    search step for entries whose seed url is empty."""
    out = []
    fetched = base.now_iso(now)
    resolved_urls = resolved_urls or {}
    for p in places_list if places_list is not None else load():
        url = (p.get("url") or "").strip() or resolved_urls.get(p.get("slug"), "")
        if not url:
            continue
        out.append(base.make(
            "worth", p.get("ttl", ""), p.get("sub", ""), p.get("district") or "الرياض",
            url, "fri", SOURCE, url, fetched,
            category=p.get("category") or "other", district=p.get("district") or "",
            raw_conf=base.TIER_PRIMARY,
            extra={"slug": p.get("slug"), "venue": p.get("venue", ""),
                   "latlng": (p["lat"], p["lng"]) if p.get("lat") is not None else None,
                   "audience": list(p.get("audience") or [])}))
    return out
