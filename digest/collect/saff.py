# -*- coding: utf-8 -*-
"""Fixtures — saff.com.sa/championship.php?id=415, the Saudi FA's own Roshn League
schedule (KSA kickoff, stadium with the city in parentheses). The page declares utf-8
but serves cp1256; net_live's decoder handles that, and the fixture on disk is the
raw bytes. Rows: a date cell <a href='calendar.php?calendar_date=YYYY-MM-DD'> spans the
day's matches; each match has cells id="fixture_td_{1..5}_{matchId}" = time, home,
score, away, stadium. jdwel.com is behind a Cloudflare challenge and is not used."""

import re
from datetime import date

from . import base
from .. import places
from ..dates import AR_DAY, ar_time, day_key

SOURCE = "الاتحاد السعودي لكرة القدم"
SCHEDULE_URL = "https://saff.com.sa/championship.php?id=415"
COMP = "دوري روشن السعودي"
RIYADH_CLUBS = ("الهلال", "النصر", "الشباب", "الرياض", "الدرعية", "الفيصلي")

_TOKEN_RX = re.compile(
    r"calendar_date=(\d{4}-\d{2}-\d{2})"
    r"|<td id=\"fixture_td_(\d)_(\d+)\"[^>]*>(.*?)</td>", re.S)
_CLUB_RX = re.compile(r"team\.php\?id=(\d+)'[^>]*><img src=\"(uploadcenter/[^\"]+\.png)\"[^>]*><br>([^<]+)</a>")
LOGO_BASE = "https://saff.com.sa/"
_CITY_RX = re.compile(r"\(([^()]+)\)\s*$")


def _cell(inner):
    t = inner
    if "<br>" in t:
        t = t.split("<br>")[-1]
    return base.text(t)


def club_logos(html):
    """-> {club name: {"id": str, "logo": absolute url}} from the schedule page (the FA's
    own 400×400 PNGs — the owner's rule 2026-09-03: logos, not typographic bands)."""
    out = {}
    for tid, path, name in _CLUB_RX.findall(html or ""):
        name = base.text(name)
        if name and name not in out:
            out[name] = {"id": tid, "logo": LOGO_BASE + path}
    return out


def parse(html, week, now, page_url=SCHEDULE_URL):
    """-> (fixtures, dropped). Fixture = {home, away, when, day, kickoff_iso, stadium,
    city, url, source, home_logo, away_logo, ...} filtered to the week and to
    Riyadh-region interest."""
    fetched = base.now_iso(now)
    logos = club_logos(html)
    rows = {}
    order = []
    current_date = None
    for m in _TOKEN_RX.finditer(html):
        if m.group(1):
            current_date = m.group(1)
            continue
        col, mid, inner = int(m.group(2)), m.group(3), m.group(4)
        r = rows.get(mid)
        if r is None:
            r = rows[mid] = {"date": current_date}
            order.append(mid)
        r[col] = _cell(inner)
    out, dropped = [], []
    seen = set()
    for mid in order:
        r = rows[mid]
        home, away, tm, stadium = r.get(2, ""), r.get(4, ""), r.get(1, ""), r.get(5, "")
        if not (home and away and tm and r.get("date")):
            continue
        try:
            d = date.fromisoformat(r["date"])
        except ValueError:
            continue
        dk = day_key(week, d)
        if not dk:
            continue
        key = (d, home, away)
        if key in seen:
            continue
        seen.add(key)
        city = ""
        cm = _CITY_RX.search(stadium)
        if cm:
            city = cm.group(1).strip()
        riyadh_club = home in RIYADH_CLUBS or away in RIYADH_CLUBS
        if not (riyadh_club or city == "الرياض"):
            continue
        hm = re.match(r"(\d{1,2}):(\d{2})", tm)
        if not hm:
            dropped.append({"ttl": "%s – %s" % (home, away), "reason": "بدون وقت"})
            continue
        h, mi = int(hm.group(1)), int(hm.group(2))
        district = places.district_for(stadium) if city == "الرياض" else ""
        out.append({
            "section": "fixtures",
            "home": home, "away": away,
            "when": "%s %s" % (AR_DAY[dk], ar_time(h, mi)),
            "day": dk,
            "kickoff_iso": "%sT%02d:%02d:00+03:00" % (d.isoformat(), h, mi),
            "stadium": stadium, "city": city,
            "in_riyadh": city == "الرياض",
            "url": page_url,
            "source": {"name": SOURCE, "url": page_url, "fetched_at": fetched},
            "tags": {"category": "sport", "district": district},
            "comp": COMP,
            "raw_conf": base.TIER_PRIMARY,
            "match_id": mid,
            "home_logo": (logos.get(home) or {}).get("logo", ""),
            "away_logo": (logos.get(away) or {}).get("logo", ""),
        })
    out.sort(key=lambda f: f["kickoff_iso"])
    return out, dropped


def fetch(week, http, now):
    status, final, ctype, html = http.get_text(SCHEDULE_URL)
    if status != 200 or not html:
        return [], [{"ttl": SOURCE, "reason": "الصفحة ما ردت (%s)" % status}], ""
    fx, dropped = parse(html, week, now, final or SCHEDULE_URL)
    return fx, dropped, html
