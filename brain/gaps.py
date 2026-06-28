"""
brain.gaps — find every empty Sunday–Wednesday night in the next 7 days, per unit, and
classify it. This is the inventory half of the Weekday-Gap Engine (the decision half is
brain.cards). It NEVER hits Hostaway directly: the one inventory source is the host's cached
tape-chart grid (_compute_calendar_grid), exactly the data the dashboard already shows.

HARD RULE #1 (weekends never touched): only nights whose own weekday is Sun/Mon/Tue/Wed are
eligible. In Python's weekday() Mon=0..Sun=6, so the eligible set is {6,0,1,2}; Thu=3, Fri=4 and
Sat=5 are never surfaced. Because a weekend night is never eligible, a run of empties is
automatically split at every weekend — so "Wed empty, then the weekend, then next Sun empty"
yields two separate single-night gaps, not one four-night gap.

A "gap" here = a maximal run of CONSECUTIVE eligible empty nights for one unit. We classify the
run (TONIGHT/TOMORROW/ORPHAN/MIDWEEK-2/LONG-GAP/THIS-WEEK) and assign a priority; premium/
protected units get +1 priority (build spec §3). The grid cell already carries the `orphan`
flag (1–2 empties wedged between two bookings) and the nightly `price`, so we read those off
rather than recomputing them.

Everything here is a PURE function of the grid + clock + the protected set, so the synthetic
tests can feed a fake grid and assert the classification without any network or wiring.
"""

from .host import HOST

# Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6.
WEEKDAY_NIGHTS = frozenset({6, 0, 1, 2})          # Sun, Mon, Tue, Wed
_WD_ABBR = {6: "Sun", 0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat"}
_MON_ABBR = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

# Class -> base priority. Premium/protected bumps P2->P1 and P3->P2 (never past P1).
TONIGHT, TOMORROW, ORPHAN = "TONIGHT", "TOMORROW", "ORPHAN-NIGHT"
MIDWEEK2, LONGGAP, THISWEEK = "MIDWEEK-2", "LONG-GAP", "THIS-WEEK"


def _label(day_iso, weekday):
    """'2026-06-30' + weekday int -> 'Mon 30 Jun' (the card's human gap label)."""
    try:
        y, m, d = (int(x) for x in str(day_iso)[:10].split("-"))
        return "%s %02d %s" % (_WD_ABBR.get(weekday, "?"), d, _MON_ABBR.get(m, "?"))
    except (ValueError, TypeError, AttributeError):
        return str(day_iso)


def _eligible(cell, day):
    """A night counts as a weekday gap iff it is empty (available, not booked/blocked/owner-
    restricted/missing) AND its own weekday is Sun–Wed."""
    return (cell or {}).get("status") == "empty" and (day or {}).get("weekday") in WEEKDAY_NIGHTS


def _classify(run, days):
    """run = list of (idx, day, cell), all eligible & consecutive. Returns (class, priority,
    days_out) BEFORE the protected bump. `days` is the grid's day list (for today/tomorrow)."""
    n = len(run)
    first_idx = run[0][0]
    days_out = first_idx                                   # 0 = a night that starts today
    is_today = first_idx == 0
    is_tomorrow = first_idx == 1
    orphan = any((c or {}).get("orphan") for _, _, c in run) and n <= 2

    if n == 1:
        if is_today:
            cls = TONIGHT
        elif is_tomorrow:
            cls = TOMORROW
        elif orphan:
            cls = ORPHAN
        else:
            cls = THISWEEK
    elif n == 2:
        # A 2-night run that includes tonight/tomorrow is still a midweek pair, but orphan
        # (single night between two bookings) only applies to length 1.
        cls = MIDWEEK2
    else:
        cls = LONGGAP

    if cls in (TONIGHT, TOMORROW, ORPHAN):
        prio = 1
    elif cls == MIDWEEK2 and days_out <= 3:
        prio = 2
    else:
        prio = 3                                           # LONG-GAP / THIS-WEEK / far MIDWEEK-2
    return cls, prio, days_out


def _runs(unit_cells, days, horizon):
    """Yield maximal runs of consecutive eligible empty nights within the horizon."""
    run = []
    for idx in range(min(horizon, len(days), len(unit_cells))):
        day = days[idx]
        cell = unit_cells[idx]
        if _eligible(cell, day):
            run.append((idx, day, cell))
        elif run:
            yield run
            run = []
    if run:
        yield run


def detect_gaps(grid, protected_lids=None, horizon_days=7):
    """PURE: turn a calendar grid into a list of weekday-gap dicts, sorted by priority then
    revenue-at-risk. `protected_lids` = set of listing ids (str) that are no-discount/premium
    (gets the +1 priority bump and the upgrade-only flag). Nothing here decides a campaign or an
    audience — that's brain.cards.

    Each gap:
      {lid, unit, protected, gap_class, priority, days_out, gap_dates[iso], gap_labels[str],
       weekdays[int], prices[int|None], at_risk(int), nights(int)}
    """
    protected_lids = {str(x) for x in (protected_lids or set())}
    days = (grid or {}).get("days") or []
    units = (grid or {}).get("units") or []
    horizon = max(1, int(horizon_days or 7))
    out = []
    for u in units:
        lid = str(u.get("lid"))
        name = u.get("name") or lid
        cells = u.get("cells") or []
        is_prot = lid in protected_lids
        for run in _runs(cells, days, horizon):
            cls, prio, days_out = _classify(run, days)
            if is_prot and prio > 1:
                prio -= 1                                  # premium/protected +1 priority (§3)
            prices = [(c or {}).get("price") for _, _, c in run]
            at_risk = sum(p for p in prices if isinstance(p, (int, float)))
            out.append({
                "lid": lid,
                "unit": name,
                "protected": is_prot,
                "gap_class": cls,
                "priority": prio,
                "priority_label": "P%d" % prio,
                "days_out": days_out,
                "nights": len(run),
                "gap_dates": [d.get("date") for _, d, _ in run],
                "gap_labels": [_label(d.get("date"), d.get("weekday")) for _, d, _ in run],
                "weekdays": [d.get("weekday") for _, d, _ in run],
                "prices": [int(round(p)) if isinstance(p, (int, float)) else None for p in prices],
                "at_risk": int(round(at_risk)),
            })
    # P1 first; within a priority the biggest revenue-at-risk, then the soonest gap.
    out.sort(key=lambda g: (g["priority"], -g["at_risk"], g["days_out"], g["unit"]))
    return out


# ---------------------------------------------------------------------------
# Thin host-backed wrappers (used in production; the tests call detect_gaps directly).
# ---------------------------------------------------------------------------

def pull_grid(days=8):
    """The units×nights grid, cache-first (mirrors brain.signals._grid): reuse the dashboard's
    warm 'calendar_grid' cache when present — it covers far more than our 7-day horizon — and only
    compute live if the cache is cold, warming it for next time. Keeps us off the Hostaway API on
    every gaps-tab load."""
    try:
        g = HOST.cache_get("calendar_grid") if HOST.cache_get else None
        if g and isinstance(g, dict) and g.get("units"):
            return g
    except Exception:
        pass
    try:
        if HOST.kick_compute and HOST.compute_calendar_grid:
            HOST.kick_compute("calendar_grid", HOST.compute_calendar_grid)
    except Exception:
        pass
    fn = HOST.require("compute_calendar_grid")
    return fn(days=max(days, 30))


def gaps_today(protected_lids=None, horizon_days=7):
    """Production entry point: pull the live grid and detect this week's weekday gaps."""
    grid = pull_grid(days=max(8, horizon_days + 1))
    return detect_gaps(grid, protected_lids=protected_lids, horizon_days=horizon_days)
