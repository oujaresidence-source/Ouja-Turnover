# -*- coding: utf-8 -*-
"""Fixtures cross-check — kooora's Roshn League page carries JSON-LD SportsEvent
entries (name «A vs B», startDate in UTC, location). Every SAFF fixture is compared
against these; a counterpart at a different kickoff means both are dropped and the drop
is reported. No counterpart → agreement unknown (lower confidence, still eligible)."""

import json
import re
from datetime import datetime, timedelta, timezone

from ..dates import RIYADH

SOURCE = "kooora"
PAGE_URL = ("https://www.kooora.com/كرة-القدم/مسابقة/دوري-روشن-السعودي/ea0h6cf3bhl698hkxhpulh2zz")

_LD_RX = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_VS_RX = re.compile(r"^\s*(.+?)\s+vs\s+(.+?)\s*$", re.I)
_AL = re.compile(r"^(ال)")


def _norm(team):
    return _AL.sub("", (team or "").strip()).replace(" ", "")


def parse(html):
    """-> [{home, away, kickoff_local (datetime, Riyadh), venue}] from the JSON-LD."""
    out = []
    for m in _LD_RX.finditer(html):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        items = d if isinstance(d, list) else [d]
        for x in items:
            if not isinstance(x, dict) or x.get("@type") != "SportsEvent":
                continue
            nm = _VS_RX.match(x.get("name") or "")
            if not nm:
                continue
            start = x.get("startDate") or ""
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            loc = x.get("location")
            venue = loc.get("name", "") if isinstance(loc, dict) else ""
            out.append({"home": nm.group(1).strip(), "away": nm.group(2).strip(),
                        "kickoff_local": dt.astimezone(RIYADH), "venue": venue})
    return out


def cross_check(fixture, events, tolerance_min=10):
    """True = a kooora event agrees (same pair, kickoff within tolerance);
    False = a counterpart exists but disagrees; None = no counterpart found."""
    h, a = _norm(fixture.get("home")), _norm(fixture.get("away"))
    try:
        ko = datetime.fromisoformat(fixture["kickoff_iso"])
    except Exception:
        return None
    found = None
    for e in events:
        eh, ea = _norm(e["home"]), _norm(e["away"])
        if {eh, ea} != {h, a}:
            continue
        found = e
        if abs(e["kickoff_local"] - ko) <= timedelta(minutes=tolerance_min):
            return True
    return False if found else None


def fetch(http):
    status, final, ctype, html = http.get_text(PAGE_URL)
    if status != 200 or not html:
        return [], ""
    return parse(html), html
