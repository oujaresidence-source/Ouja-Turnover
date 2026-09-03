# -*- coding: utf-8 -*-
"""«يستاهل الزيارة» — read from the Riyadh dataset (digest/data/riyadh.json; a copy under
$STATE_DIR/digest/ wins) under the owner's rules (2026-09-03, after King Salman Park
slipped in as a guess):

  1. status == "open"  AND  url present  AND  verified_on within MAX_AGE_DAYS  → eligible
  2. status == "seasonal" → only inside its calendar window, and only if the window is confirmed
  3. not_open / unknown / expected / anything else → NEVER

The card line is facts, in order: day+date · district · price."""

import json
import os
from datetime import date, datetime

from . import base
from ..dates import AR_DAY, ar_date

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(os.path.dirname(HERE), "data", "riyadh.json")
SOURCE = "Ouja"
MAX_AGE_DAYS = 90
SEARCH_DOMAINS = ("visitsaudi.com", "moc.gov.sa", "diriyah.sa", "kafd.sa", "rcrc.gov.sa", "riyadh.sa")


def load(override_path=None):
    """-> the dataset dict {calendar, places} (empty structures when unreadable)."""
    for p in (override_path, SEED):
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
                if isinstance(d.get("places"), list):
                    d.setdefault("calendar", [])
                    return d
            except Exception:
                continue
    return {"calendar": [], "places": []}


def _parse_day(s):
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def season_window(calendar, key):
    for c in calendar or []:
        if c.get("key") == key:
            w = c.get("window")
            if not (w and len(w) == 2 and c.get("confirmed")):
                return None
            a, b = _parse_day(w[0]), _parse_day(w[1])
            return (a, b) if a and b else None
    return None


def why_ineligible(place, today, calendar=None):
    """'' when the place may render, else a short reason (Arabic, for the report)."""
    st = place.get("status")
    if st == "seasonal":
        win = season_window(calendar, place.get("season"))
        if not win:
            return "موسم غير مؤكد"
        if not (win[0] <= today <= win[1]):
            return "خارج موسمه"
    elif st != "open":
        return {"not_open": "مو مفتوح", "unknown": "حالته غير مؤكدة"}.get(st, "حالته غير معروفة")
    if not (place.get("url") or "").strip():
        return "بدون صفحة رسمية"
    v = _parse_day(place.get("verified_on"))
    if not v:
        return "بدون تاريخ تحقق"
    if (today - v).days > MAX_AGE_DAYS:
        return "التحقق قديم"
    return ""


def facts_line(place, week, day_key="fri"):
    d = {"thu": week.thu, "fri": week.fri, "sat": week.sat}[day_key]
    return " · ".join(x for x in ("%s %s" % (AR_DAY[day_key], ar_date(d)), place.get("district") or "الرياض",
                                  place.get("price") or "حسب التذكرة") if x)


def candidates(week, now, dataset=None, resolved_urls=None):
    """Pure: dataset → Candidates + the dropped list (with reasons). `resolved_urls`
    = {slug: url} found by the search step for open places whose url was empty."""
    ds = dataset if dataset is not None else load()
    today = now.date() if isinstance(now, datetime) else now
    resolved_urls = resolved_urls or {}
    out, dropped = [], []
    fetched = base.now_iso(now)
    for p in ds.get("places") or []:
        p2 = dict(p)
        if not (p2.get("url") or "").strip() and p2.get("slug") in resolved_urls:
            p2["url"] = resolved_urls[p2["slug"]]
        why = why_ineligible(p2, today, ds.get("calendar"))
        if why:
            dropped.append({"ttl": p2.get("ttl", p2.get("slug", "")), "reason": why, "slug": p2.get("slug")})
            continue
        out.append(base.make(
            "worth", p2.get("ttl", ""), facts_line(p2, week), p2.get("district") or "الرياض",
            p2["url"], "fri", SOURCE, p2["url"], fetched,
            category=p2.get("category") or "other", district=p2.get("district") or "",
            raw_conf=base.TIER_PRIMARY,
            extra={"slug": p2.get("slug"), "venue": p2.get("ttl", ""), "hook": p2.get("hook", ""),
                   "commons_query": p2.get("commons_query", ""),
                   "hours": p2.get("hours", ""), "price": p2.get("price", ""),
                   "latlng": (p2["lat"], p2["lng"]) if p2.get("lat") is not None else None,
                   "audience": list(p2.get("audience") or []), "verified_on": p2.get("verified_on", "")}))
    return out, dropped
