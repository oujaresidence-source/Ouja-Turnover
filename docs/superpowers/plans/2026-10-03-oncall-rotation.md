# «المناوبة» Evening On-Call Rotation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fair, auto-published 17:00–24:00 on-call rotation. It proves presence with a «✋ موجود» button every 15 minutes, alerts اسيل on the first miss, issues a commission-cutting ops warning on the second miss, and gives every escalation or maintenance ticket opened during a slot a named owner until it is resolved.

**Architecture:** A new `oncall/` package follows the same dependency-injection shape as `schedule/`, `ops/` and `reviewask/`:
- `engine.py` holds pure rules.
- `db.py` stores `oncall_*` tables in brain.db.
- `notify.py` runs a minute tick plus the button and hook handlers.
- `routes.py` serves `/api/oncall/*` plus a static tab script.

`bot.py` only delivers to Discord, registers one listener, one loop and four hooks, and adds the dashboard tab stub. Missed checks reuse ops' existing `ops_obligations` / `ops_warnings` / appeal / commission machinery: kind `oc`, period `OC-YYYY-MM-DD`.

**Tech Stack:** Python 3.9+ (local is 3.9.6, so no `X | Y` types and no `match`), discord.py ≥ 2.4, aiohttp, SQLite via `brain.db`, `unittest` (no pytest), Node `~/.local/node/bin/node` for `node --check`, `esprima` for the DASHBOARD_HTML parse.

**Spec:** `docs/superpowers/specs/2026-10-03-oncall-rotation-design.md` (owner-approved 2026-10-03, including the 5 assumptions in §12).

**Provenance:** Every code block below was run before this plan was written. A scratch copy of `oncall/` plus a patched copy of `bot.py` were built and checked:
- 67 new tests pass, and the existing 57 `test_ops_flow` tests still pass.
- `py_compile` is clean.
- pyflakes reports zero new warnings.
- esprima parses all 3 DASHBOARD_HTML scripts.
- `node --check` passes on the tab JS.

Copy the blocks exactly.

## Global Constraints

- Work in the worktree `/Users/faisalouja/ouja-wt-oncall` on branch `feat/oncall` (made from origin/main fd01739). Never switch the main checkout's branch.
- **Never push.** Pushing deploys to the live business. The owner approves the push separately after seeing screenshots.
- Stage files **by name**, never with `git add -A`. Other sessions share this `.git`.
- Times are Riyadh: window 17:00–24:00, a check every **15** min, **10** min to answer, publish **12:00** the day before, lock **15:00** on the day, claim within **10** min, stale after **30** min.
- The supervisor is **اسيل**, spelled with س. The default roster is نورة · ناصر · محمد اليامي · عهود · مآثر, which are the Employee Calendar's own spellings.
- The master switch defaults **ON**. The owner ruled: live from day one, and he never edits Railway.
- On-call warnings **do** cut commission. They are the same `ops_warnings` rows and the same appeal path as today.
- brain.db rules: no WAL, `with closing(connect())`, one short connection per call.
- Request handlers use `HOST.web_thread` (bot.web_thread), never `asyncio.to_thread`. Calls from the tick, listeners and hooks use `asyncio.to_thread`.
- No backslash anywhere in `DASHBOARD_HTML` additions. The tab JS lives in a real file (`oncall/static/oncall_tab.js`) and must pass `node --check`.
- All user-facing Arabic comes from `oncall/texts.py`. Don't scatter strings.

## Review Focus

These are the five inputs the spec implies that are most likely to bite a real person. Each is pinned by a test in the task named.
1. **Bot redeploy mid-shift:** a 19-minute tick gap must void the checks it spans, never count a miss or issue a warning. Pinned by `test_bot_downtime_voids_and_never_warns` (Task 2).
2. **Name spellings across files:** the escalation picker says «نوره/ماثر/محمد», but the calendar says «نورة/مآثر/محمد اليامي». Ownership, helper detection and "your own slot" must still match. Pinned by `test_claim_picker_names_match_calendar` (Task 1), `test_outside_claimer_is_helper_owner_stays` and `test_own_slot_refused` (Task 2).
3. **Half-day leave is inverted for evenings:** a MORNING half-day is available tonight, and an EVENING half-day is not. This is the opposite of the cleaning board's `affects_coverage` flag. Pinned by `test_leave_respected_but_morning_half_day_still_on_tonight` (Task 2).
4. **An unlinked person (عهود today):** never scheduled, never warned, and the supervisor is told at publish time. Pinned by `test_unlinked_person_is_left_out_and_supervisor_told` (Task 2).
5. **A maintenance ticket waiting days for a vendor:** the stale alert fires at most once per night, never every 30 minutes, and never after midnight. Pinned by `test_stale_once_per_night_and_never_after_midnight` (Task 1) and `test_stale_after_slot_end_once` (Task 2).

---

## File Structure

| Path | Responsibility |
|---|---|
| `oncall/__init__.py` | Package doc and exports (`wire`, `HOST`, `register_routes`) |
| `oncall/engine.py` | PURE rules: rotation, check times, verdict, miss ladder, ownership, stale, swaps, names |
| `oncall/db.py` | `oncall_*` schema plus thin helpers. Idempotency comes from UNIQUE constraints and status flips |
| `oncall/host.py` | The bridge to bot.py (`now`, `send`, web/auth callables) |
| `oncall/roster.py` | Who can work on a date (calendar + leave + ops Discord ids) and the supervisor |
| `oncall/texts.py` | Every Arabic message |
| `oncall/notify.py` | Minute `tick`, button handlers, issue hooks, and the ONLY `ops.db.issue_warning` call |
| `oncall/routes.py` | `/api/oncall/*`, plus serving `/oncall/static/oncall_tab.js` |
| `oncall/static/oncall_tab.js` | Dashboard tab UI |
| `ops/notify.py` (modify `_retirement`) | A week with a missed on-call night is not clean |
| `bot.py` (21 anchored edits) | Import, delivery, views, listener, loop, command, 4 hooks, wiring, role rules, NAV, tab stub |
| `tests/test_oncall_engine.py` | Engine invariants (31 tests) |
| `tests/test_oncall_flow.py` | End-to-end on a temp brain.db (23 tests) |
| `tests/test_oncall_retirement.py` | ops retirement × on-call (1 test) |
| `tests/test_oncall_routes.py` | Dashboard state plus the accusation invariant (4 tests) |
| `tests/test_oncall_wiring.py` | bot.py wiring, read as text (8 tests) |

---

### Task 1: The pure engine

**Files:**
- Create: `oncall/__init__.py` (interim)
- Create: `oncall/engine.py`
- Test: `tests/test_oncall_engine.py`

**Interfaces:**
- Consumes: nothing.
- Produces (used by every later task):
  - Constants: `WINDOW_START_HOUR=17`, `WINDOW_MINUTES=420`, `CHECK_EVERY_MIN=15`, `ANSWER_WINDOW_MIN=10`, `CLAIM_WITHIN_MIN=10`, `STALE_AFTER_MIN=30`, `PUBLISH_HOUR=12`, `LOCK_HOUR=15`, `REMIND_BEFORE_MIN=15`, `SEND_GRACE_MIN=2`, `DOWNTIME_GAP_SEC=120`, `HANDOVER_GRACE_MIN=5`, `MISS_ALERT`, `MISS_WARN`, `MISS_ALERT_AGAIN`.
  - Time helpers:
    - `sun_weekday(date)->int`
    - `night_start(date,tz)->datetime`
    - `at_minute(date,minute,tz)->datetime`
    - `night_minute(datetime)->(date|None, int|None)`
    - `hm(minute)->'7:15'`
  - Rotation and ownership:
    - `build_night(date, available:[str], history:[{date,slots}])->[{employee,start_min,end_min}]`
    - `owner_at(slots, minute)->slot|None`
  - Checks:
    - `check_minutes(start,end,every=15)->[int]`
    - `overlaps(a0,a1,b0,b1)->bool`
    - `check_verdict(due_at, now, delivered:bool, answered_at|None, downtimes:[(dt,dt)])->(status, void_reason)`
    - `miss_decision(nth)->str`
  - Issues:
    - `claim_overdue(opened_at, claimed_at|None, now, already_alerted)->bool`
    - `stale_due(slot_end_at, last_update_at, now, alerted_tonight)->bool`
  - Swaps: `swap_decision(night_status, requester, target_slot, requester_slot|None, requester_ok, target_ok, pending_exists)->(ok, kind, reason_ar)`
  - Names:
    - `norm(name)->str`
    - `same_person(a,b)->bool`

- [ ] **Step 1: Write the failing test**

Create `tests/test_oncall_engine.py`:

```python
# -*- coding: utf-8 -*-
"""
«المناوبة» engine invariants — pure functions, no database, no Discord.

Run: python3 -m unittest tests.test_oncall_engine
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oncall import engine as E   # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))
FIVE = ["ناصر", "مآثر", "نورة", "محمد اليامي", "عهود"]
OFF = {"ناصر": 2, "مآثر": 0, "نورة": 1, "محمد اليامي": 3, "عهود": 6}   # the real seed
D0 = datetime.date(2026, 10, 4)                                        # a Sunday


def hours(slots):
    return sorted((s["end_min"] - s["start_min"]) // 60 for s in slots)


def simulate(nights, available_fn):
    hist = []
    for i in range(nights):
        d = D0 + datetime.timedelta(days=i)
        slots = E.build_night(d, available_fn(d), hist[-7:])
        hist.append({"date": d.isoformat(), "slots": slots})
    return hist


def totals(hist):
    t = {}
    for h in hist:
        for s in h["slots"]:
            t[s["employee"]] = t.get(s["employee"], 0) + (s["end_min"] - s["start_min"]) // 60
    return t


class Rotation(unittest.TestCase):
    def test_five_people_split_2_2_1_1_1(self):
        self.assertEqual(hours(E.build_night(D0, FIVE, [])), [1, 1, 1, 2, 2])

    def test_lengths_for_every_headcount(self):
        want = {1: [7], 2: [3, 4], 3: [2, 2, 3], 4: [1, 2, 2, 2], 5: [1, 1, 1, 2, 2]}
        for n, exp in want.items():
            self.assertEqual(hours(E.build_night(D0, FIVE[:n], [])), exp, n)

    def test_contiguous_17_to_24_no_gaps(self):
        for n in range(1, 6):
            s = E.build_night(D0, FIVE[:n], [])
            self.assertEqual(s[0]["start_min"], 0)
            self.assertEqual(s[-1]["end_min"], 420)
            for a, b in zip(s, s[1:]):
                self.assertEqual(a["end_min"], b["start_min"])

    def test_nobody_available_means_uncovered(self):
        self.assertEqual(E.build_night(D0, [], []), [])

    def test_deterministic(self):
        h = simulate(3, lambda d: FIVE)
        self.assertEqual(E.build_night(D0 + datetime.timedelta(days=3), FIVE, h),
                         E.build_night(D0 + datetime.timedelta(days=3), FIVE, h))

    def test_first_week_fair_within_one_hour(self):
        t = totals(simulate(7, lambda d: FIVE))
        self.assertLessEqual(max(t.values()) - min(t.values()), 1, t)

    def test_four_weeks_with_real_days_off_fair_within_one_hour(self):
        t = totals(simulate(28, lambda d: [p for p in FIVE if OFF[p] != E.sun_weekday(d)]))
        self.assertLessEqual(max(t.values()) - min(t.values()), 1, t)

    def test_last_slot_never_twice_running(self):
        h = simulate(28, lambda d: [p for p in FIVE if OFF[p] != E.sun_weekday(d)])
        for a, b in zip(h, h[1:]):
            self.assertNotEqual(a["slots"][-1]["employee"], b["slots"][-1]["employee"], b["date"])

    def test_start_time_rotates_when_everyone_works(self):
        h = simulate(14, lambda d: FIVE)
        for a, b in zip(h, h[1:]):
            prev = {s["employee"]: s["start_min"] for s in a["slots"]}
            for s in b["slots"]:
                self.assertNotEqual(prev[s["employee"]], s["start_min"], (b["date"], s))

    def test_unavailable_never_scheduled(self):
        s = E.build_night(D0, ["ناصر", "نورة"], [])
        self.assertEqual({x["employee"] for x in s}, {"ناصر", "نورة"})

    def test_owner_at_boundaries(self):
        s = E.build_night(D0, FIVE, [])
        self.assertIsNone(E.owner_at(s, None))
        self.assertEqual(E.owner_at(s, 0)["employee"], s[0]["employee"])
        self.assertEqual(E.owner_at(s, 419)["employee"], s[-1]["employee"])
        self.assertEqual(E.owner_at(s, s[0]["end_min"])["employee"], s[1]["employee"])
        self.assertIsNone(E.owner_at(s, 420))

    def test_night_minute(self):
        self.assertEqual(E.night_minute(datetime.datetime(2026, 10, 4, 16, 59, tzinfo=TZ)),
                         (None, None))
        self.assertEqual(E.night_minute(datetime.datetime(2026, 10, 4, 17, 0, tzinfo=TZ)),
                         (D0, 0))
        self.assertEqual(E.night_minute(datetime.datetime(2026, 10, 4, 23, 59, tzinfo=TZ)),
                         (D0, 419))
        self.assertEqual(E.night_minute(datetime.datetime(2026, 10, 5, 0, 0, tzinfo=TZ)),
                         (None, None))

    def test_sun_weekday(self):
        self.assertEqual(E.sun_weekday(D0), 0)                       # Sunday
        self.assertEqual(E.sun_weekday(D0 + datetime.timedelta(days=6)), 6)


class Checks(unittest.TestCase):
    def test_two_hour_slot_has_eight_checks(self):
        self.assertEqual(E.check_minutes(0, 120), [0, 15, 30, 45, 60, 75, 90, 105])

    def test_one_hour_slot_has_four_checks(self):
        self.assertEqual(E.check_minutes(360, 420), [360, 375, 390, 405])

    def _v(self, **kw):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        args = dict(due_at=due, now=due + datetime.timedelta(minutes=11), delivered=True,
                    answered_at=None, downtimes=[])
        args.update(kw)
        return E.check_verdict(**args)

    def test_answered_in_window(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        self.assertEqual(self._v(answered_at=due + datetime.timedelta(minutes=10))[0], "answered")

    def test_pending_inside_window(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        self.assertEqual(self._v(now=due + datetime.timedelta(minutes=9))[0], "pending")

    def test_missed_after_window(self):
        self.assertEqual(self._v()[0], "missed")

    def test_late_answer_is_still_a_miss(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        self.assertEqual(self._v(answered_at=due + datetime.timedelta(minutes=11))[0], "missed")

    def test_not_delivered_is_void_never_a_miss(self):
        self.assertEqual(self._v(delivered=False), ("voided", "not_delivered"))

    def test_downtime_inside_window_is_void(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        dt = [(due + datetime.timedelta(minutes=3), due + datetime.timedelta(minutes=6))]
        self.assertEqual(self._v(downtimes=dt), ("voided", "bot_down"))

    def test_downtime_elsewhere_does_not_void(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        dt = [(due - datetime.timedelta(minutes=30), due - datetime.timedelta(minutes=20))]
        self.assertEqual(self._v(downtimes=dt)[0], "missed")

    def test_miss_ladder(self):
        self.assertEqual(E.miss_decision(1), E.MISS_ALERT)
        self.assertEqual(E.miss_decision(2), E.MISS_WARN)
        self.assertEqual(E.miss_decision(3), E.MISS_ALERT_AGAIN)
        self.assertEqual(E.miss_decision(7), E.MISS_ALERT_AGAIN)


class Issues(unittest.TestCase):
    T0 = datetime.datetime(2026, 10, 4, 18, 0, tzinfo=TZ)

    def test_claim_overdue_after_ten_minutes_once(self):
        t = self.T0
        self.assertFalse(E.claim_overdue(t, None, t + datetime.timedelta(minutes=9), False))
        self.assertTrue(E.claim_overdue(t, None, t + datetime.timedelta(minutes=10), False))
        self.assertFalse(E.claim_overdue(t, None, t + datetime.timedelta(minutes=30), True))
        self.assertFalse(E.claim_overdue(t, t, t + datetime.timedelta(minutes=30), False))

    def test_stale_only_after_slot_end(self):
        end = self.T0 + datetime.timedelta(hours=1)
        upd = self.T0
        self.assertFalse(E.stale_due(end, upd, end - datetime.timedelta(minutes=1), False))
        self.assertTrue(E.stale_due(end, upd, end, False))

    def test_stale_needs_thirty_quiet_minutes(self):
        end = self.T0
        upd = end + datetime.timedelta(minutes=10)
        self.assertFalse(E.stale_due(end, upd, upd + datetime.timedelta(minutes=29), False))
        self.assertTrue(E.stale_due(end, upd, upd + datetime.timedelta(minutes=30), False))

    def test_stale_once_per_night_and_never_after_midnight(self):
        end, upd = self.T0, self.T0
        self.assertFalse(E.stale_due(end, upd, end + datetime.timedelta(hours=2), True))
        after_midnight = datetime.datetime(2026, 10, 5, 0, 30, tzinfo=TZ)
        self.assertFalse(E.stale_due(end, upd, after_midnight, False))


class Swaps(unittest.TestCase):
    SLOT = {"id": 1, "employee": "نورة", "start_min": 0, "end_min": 120}

    def test_exchange_and_takeover(self):
        ok, kind, _ = E.swap_decision("published", "ناصر", self.SLOT, {"id": 2}, True, True, False)
        self.assertEqual((ok, kind), (True, "exchange"))
        ok, kind, _ = E.swap_decision("published", "ناصر", self.SLOT, None, True, True, False)
        self.assertEqual((ok, kind), (True, "takeover"))

    def test_refusals(self):
        cases = [("locked", "ناصر", True, True, False),
                 ("published", "نوره", True, True, False),          # own slot, other spelling
                 ("published", "ناصر", False, True, False),
                 ("published", "ناصر", True, False, False),
                 ("published", "ناصر", True, True, True)]
        for st, who, rok, tok, pend in cases:
            ok, _k, why = E.swap_decision(st, who, self.SLOT, None, rok, tok, pend)
            self.assertFalse(ok, (st, who))
            self.assertTrue(why)


class Names(unittest.TestCase):
    def test_claim_picker_names_match_calendar(self):
        self.assertTrue(E.same_person("نوره", "نورة"))
        self.assertTrue(E.same_person("ماثر", "مآثر"))
        self.assertTrue(E.same_person("محمد", "محمد اليامي"))
        self.assertFalse(E.same_person("ناصر", "نورة"))
        self.assertFalse(E.same_person("", "نورة"))

    def test_hm(self):
        self.assertEqual(E.hm(0), "5:00")
        self.assertEqual(E.hm(420), "12:00")
        self.assertEqual(E.hm(135), "7:15")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd /Users/faisalouja/ouja-wt-oncall && python3 -m unittest tests.test_oncall_engine`
Expected: `ModuleNotFoundError: No module named 'oncall'`

- [ ] **Step 3: Write the implementation**

Create `oncall/__init__.py` (interim, extended in Tasks 2 and 4):

```python
# -*- coding: utf-8 -*-
"""oncall — «المناوبة», the evening on-call rotation (17:00-24:00). See Task 4 for the full doc."""

from . import engine  # noqa: F401
```

Create `oncall/engine.py`:

```python
# -*- coding: utf-8 -*-
"""
oncall.engine — the PURE rules of «المناوبة». No I/O, no clock reads, no database.

Every function takes what it needs and returns plain data, so the tests can feed a fake
week and assert numbers. notify.py is the only caller that touches the world.

The night of date D runs 17:00 -> 24:00 Riyadh time on D. Inside a night, time is counted
in MINUTES AFTER 17:00 (0..420), so a slot is the half-open range [start_min, end_min).
"""

import datetime

WINDOW_START_HOUR = 17          # 5 PM
WINDOW_MINUTES = 7 * 60         # 17:00 -> 24:00
CHECK_EVERY_MIN = 15            # «موجود؟» cadence (owner decision)
ANSWER_WINDOW_MIN = 10          # time to press before it is a miss (owner decision)
CLAIM_WITHIN_MIN = 10           # an escalation must be claimed within this
STALE_AFTER_MIN = 30            # no update this long after the owner's slot ended -> supervisor
PUBLISH_HOUR = 12               # tomorrow's night is published at 12:00
LOCK_HOUR = 15                  # tonight locks at 15:00
REMIND_BEFORE_MIN = 15          # «مناوبتك تبدأ …» DM
SEND_GRACE_MIN = 2              # a check not sent within this of its time is void (bot was down)
DOWNTIME_GAP_SEC = 120          # a tick gap longer than this is recorded as bot downtime
HANDOVER_GRACE_MIN = 5          # handover posted within this after a slot ends, else skipped

MISS_ALERT = "alert"            # 1st miss of the night: employee + supervisor
MISS_WARN = "warn"              # 2nd miss: formal warning (ops_warnings) + supervisor
MISS_ALERT_AGAIN = "alert_again"  # 3rd+: supervisor only, never a second warning


# ----------------------------------------------------------------- time helpers

def sun_weekday(d):
    """Python Monday=0 -> the Employee Calendar's convention, 0=الأحد .. 6=السبت."""
    return (d.weekday() + 1) % 7


def night_start(d, tzinfo):
    """17:00 on date d, tz-aware."""
    return datetime.datetime(d.year, d.month, d.day, WINDOW_START_HOUR, 0, tzinfo=tzinfo)


def at_minute(d, minute, tzinfo):
    return night_start(d, tzinfo) + datetime.timedelta(minutes=int(minute))


def night_minute(now):
    """(night_date, minute 0..419) when `now` is inside 17:00-24:00, else (None, None)."""
    if now.hour < WINDOW_START_HOUR:
        return None, None
    return now.date(), (now.hour - WINDOW_START_HOUR) * 60 + now.minute


def hm(minute):
    """Minutes after 17:00 -> '5:00' .. '12:00' (12-hour clock, the way the team talks)."""
    h = WINDOW_START_HOUR + int(minute) // 60
    m = int(minute) % 60
    h12 = h - 12 if h > 12 else h
    return "%d:%02d" % (h12, m)


# ----------------------------------------------------------------- the rotation

def _rot(available, d):
    """Roster order rotated by the calendar day, so ties never favour the same person."""
    n = len(available)
    k = d.toordinal() % n
    return {p: (i - k) % n for i, p in enumerate(available)}


def build_night(d, available, history):
    """The night of date d, auto-distributed and fair.

    available: names, in roster order, who can work tonight (already filtered for weekly day
               off, recorded leave and a linked Discord account).
    history:   [{date: 'YYYY-MM-DD', slots: [{employee, start_min, end_min}]}] — the
               trailing nights before d (7 is what notify passes).

    Rules:
      * 7 hours split into contiguous whole hours: 7 // n each, the 7 % n remainder hours
        to whoever has the FEWEST trailing hours (ties: fewer long slots, then rotation).
      * the LAST slot (ends 24:00) goes to whoever held it least recently.
      * the rest are rotated so nobody starts at the same time as yesterday when avoidable.
    Deterministic: same inputs -> same night. Returns [{employee, start_min, end_min}]."""
    available = list(dict.fromkeys(available or []))
    n = len(available)
    if n == 0:
        return []
    rot = _rot(available, d)
    hours = {p: 0 for p in available}
    longs = {p: 0 for p in available}
    last_late = {p: "" for p in available}
    yday = {}
    yiso = (d - datetime.timedelta(days=1)).isoformat()
    for night in sorted(history or [], key=lambda h: h["date"]):
        for s in night.get("slots") or []:
            p = s["employee"]
            if p not in hours:
                continue
            ln = (int(s["end_min"]) - int(s["start_min"])) // 60
            hours[p] += ln
            if ln >= 2:
                longs[p] += 1
            if int(s["end_min"]) == WINDOW_MINUTES:
                last_late[p] = night["date"]
            if night["date"] == yiso:
                yday[p] = int(s["start_min"])

    base, extra_n = divmod(WINDOW_MINUTES // 60, n)
    ranked = sorted(available, key=lambda p: (hours[p], longs[p], rot[p]))
    extra = set(ranked[:extra_n])
    length = {p: (base + (1 if p in extra else 0)) * 60 for p in available}

    late = min(available, key=lambda p: (last_late[p], rot[p]))
    rest = [p for p in available if p != late]
    rest.sort(key=lambda p: (yday.get(p, -1), rot[p]))

    best = None
    for shift in list(range(1, len(rest))) + [0]:
        order = rest[shift:] + rest[:shift] + [late]
        out, t = [], 0
        for p in order:
            out.append({"employee": p, "start_min": t, "end_min": t + length[p]})
            t += length[p]
        clashes = sum(1 for s in out if yday.get(s["employee"]) == s["start_min"])
        if best is None or clashes < best[0]:
            best = (clashes, out)
        if clashes == 0:
            break
    return best[1]


def owner_at(slots, minute):
    """Who is on duty at `minute` (0..419) — the slot whose [start,end) contains it."""
    if minute is None:
        return None
    for s in slots or []:
        if int(s["start_min"]) <= minute < int(s["end_min"]):
            return s
    return None


# ----------------------------------------------------------------- presence checks

def check_minutes(start_min, end_min, every=CHECK_EVERY_MIN):
    """The first check fires the moment the slot starts, then every 15 minutes.
    A 2-hour slot from 0 -> [0, 15, 30, 45, 60, 75, 90, 105]."""
    return list(range(int(start_min), int(end_min), int(every)))


def overlaps(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


def check_verdict(due_at, now, delivered, answered_at, downtimes, window=ANSWER_WINDOW_MIN):
    """('pending'|'answered'|'missed'|'voided', void_reason).

    The employee never pays for the bot: a check that never reached them, or whose
    window was spanned by bot downtime, is VOID — never a miss."""
    deadline = due_at + datetime.timedelta(minutes=window)
    if answered_at is not None and answered_at <= deadline:
        return "answered", ""
    if now < deadline:
        return "pending", ""
    if not delivered:
        return "voided", "not_delivered"
    for d0, d1 in downtimes or []:
        if overlaps(d0, d1, due_at, deadline):
            return "voided", "bot_down"
    return "missed", ""


def miss_decision(nth_miss_tonight):
    """1st -> alert, 2nd -> formal warning, 3rd+ -> alert again (one warning per night)."""
    n = int(nth_miss_tonight or 0)
    if n <= 1:
        return MISS_ALERT
    if n == 2:
        return MISS_WARN
    return MISS_ALERT_AGAIN


# ----------------------------------------------------------------- issue ownership

def claim_overdue(opened_at, claimed_at, now, already_alerted, within=CLAIM_WITHIN_MIN):
    if claimed_at is not None or already_alerted:
        return False
    return now - opened_at >= datetime.timedelta(minutes=within)


def stale_due(slot_end_at, last_update_at, now, alerted_tonight, after=STALE_AFTER_MIN):
    """After the owner's slot has ended, and only while it is still 17:00-24:00, no update for
    30 minutes -> alert the supervisor, at most ONCE per issue per night."""
    if alerted_tonight:
        return False
    nd, _m = night_minute(now)
    if nd is None:
        return False
    if now < slot_end_at:
        return False
    return now - last_update_at >= datetime.timedelta(minutes=after)


# ----------------------------------------------------------------- swaps

def swap_decision(night_status, requester, target_slot, requester_slot, requester_ok,
                  target_ok, pending_exists):
    """(ok, kind, reason_ar). kind: 'exchange' (requester has a slot tonight) or 'takeover'."""
    if night_status not in ("published",):
        return False, "", "الجدول مقفل — التعديل الحين من اسيل بس."
    if not target_slot:
        return False, "", "ما لقيت السلوت."
    if same_person(target_slot["employee"], requester):
        return False, "", "هذا سلوتك أنت."
    if not requester_ok:
        return False, "", "ما تقدر تاخذ مناوبة الليلة (إجازة أو حسابك مو مربوط)."
    if not target_ok:
        return False, "", "صاحب السلوت ما نقدر نوصله الحين."
    if pending_exists:
        return False, "", "فيه طلب تبديل على هذا السلوت ينتظر رد."
    return True, ("exchange" if requester_slot else "takeover"), ""


# ----------------------------------------------------------------- names

def norm(name):
    """Arabic-tolerant key: the escalation picker says «نوره»/«ماثر»/«محمد», the calendar
    says «نورة»/«مآثر»/«محمد اليامي». Same rules as ops.notify._norm."""
    s = (name or "").strip()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
                 ("ة", "ه"), ("ى", "ي"), ("ـ", "")):
        s = s.replace(a, b)
    return " ".join("".join(ch for ch in s if ch not in "ًٌٍَُِّْ").split())


def same_person(a, b):
    """Equal after normalising, or one is the other's first name («محمد» ~ «محمد اليامي»)."""
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    return x == y or x.split(" ")[0] == y or y.split(" ")[0] == x
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python3 -m unittest tests.test_oncall_engine`
Expected: `Ran 31 tests … OK`

- [ ] **Step 5: Commit**

```bash
git add oncall/__init__.py oncall/engine.py tests/test_oncall_engine.py
git commit -m "feat(oncall): pure engine — fair rotation, check verdicts, miss ladder, ownership

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Storage, roster, texts and the minute tick

**Files:**
- Create: `oncall/db.py`
- Create: `oncall/host.py`
- Create: `oncall/roster.py`
- Create: `oncall/texts.py`
- Create: `oncall/notify.py`
- Modify: `oncall/__init__.py`
- Test: `tests/test_oncall_flow.py`

**Interfaces:**
- Consumes: everything from Task 1. Also:
  - `brain.db.connect/db_path/set_db_path_for_tests`
  - `schedule.owners.permanent_map()` → `{employees:[{id,name,off_day,…}]}`
  - `schedule.db.absences_recorded_on(date_iso)` → rows with `employee_id,type,shift`
  - `ops.notify.employees()` → `[{name,did,…}]`, plus `ops.notify.lead_id()`, `ar_num()`, `hr_channel()` and `_appeal_link(token)`
  - `ops.db.ensure_obligation/set_status/issue_warning/recompute_commission/obligation/warnings_for/counts`
  - `ops.engine.month_key/tz`
- Produces:
  - `HOST` fields: `now`, `send`, `dash_auth`, `req_role`, `actor`, `json_response`, `web`, `web_thread`, and `oncall.host.wire(caps)`.
  - The send payload, `dict` with keys:
    - `kind`
    - `dm:[{did,text}]`
    - `channel_text`
    - `mentions`
    - `view` (`''|'here'|'swap_ask'|'schedule'`)
    - `slots:[{id,label,locked}]`
    - `edit_message_id`
    - `hr_channel`
    - `hr_text`
    - `report:{what:'check'|'swap'|'schedule'|'issue_note', id}`
  - Tick and switch:
    - `notify.tick(now=None)->dict`
    - `notify.enabled()->bool`
    - `notify.set_enabled(on,by,at)`
    - `notify.channel_name()->str`
  - Delivery report: `notify.delivered(report, dm_ok, dm_mid, ch_ok, ch_mid)`.
  - Button handlers:
    - `notify.answer_check(message_id, presser_did, now=None)->(code, text)`
    - `notify.request_swap(slot_id, presser_did, now=None)->(ok,text)`
    - `notify.answer_swap(message_id, presser_did, accept, now=None)->(ok,text)`
    - `notify.edit_slot(slot_id, employee, by, reason, now=None)->(ok,err)`
    - `notify.resolve_press(note_message_id, presser_did, is_admin, now=None)->(ok,text)`
  - Ownership and issue hooks:
    - `notify.owner_now(now)->slot|None`
    - `notify.on_issue_opened(kind, ref, title, now=None)->{owner,owner_did,text}|None`
    - `notify.on_escalation_claimed(ref, by_name, now=None)`
    - `notify.on_issue_resolved(ref, by, now=None)`
    - `notify.on_ticket_message(ref, author_did, now=None)`
  - Roster:
    - `roster.roster_names()`
    - `roster.availability(date)->[{name,did,ok,why}]`
    - `roster.name_for_did(did)`
    - `roster.did_for(name)`
    - `roster.supervisor()->{name,did}`
  - `db.*` helpers as listed in the file.

- [ ] **Step 1: Write the failing test**

Create `tests/test_oncall_flow.py`:

```python
# -*- coding: utf-8 -*-
"""
«المناوبة» end-to-end on a real (temporary) brain.db with the real Employee Calendar seed.
No Discord, no network — HOST.send is a list and delivery is reported back by hand.

Locked here (the rules that cost somebody money or a guest if they break):
    * tomorrow is published at 12:00, once; weekly days off and leave are respected
    * a night that was never published produces no check and no miss
    * the check button only counts from the person on duty, within 10 minutes
    * 1st miss = alert, 2nd = ONE formal warning in ops_warnings (kind 'oc'), 3rd = alert only
    * an undelivered check, or one spanned by bot downtime, is void — never a miss
    * swaps: only the target answers; accepted = slots rewritten; 15:00 lock expires requests
    * an issue opened 17-24 belongs to whoever is on duty; a claimer from outside is a helper
    * stale / claim-overdue alerts fire once
    * switch OFF = the tick sends nothing
(The ops retirement rule lives in tests/test_oncall_retirement.py.)

Run: python3 -m unittest tests.test_oncall_flow
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                      # noqa: E402
from schedule import db as sdb, seed as sseed    # noqa: E402
from ops import db as odb, engine as oeng         # noqa: E402
from ops.host import HOST as OPS_HOST            # noqa: E402
from oncall import db, notify                    # noqa: E402
from oncall.host import HOST                     # noqa: E402

RIYADH = oeng.tz()
IDS = {"ناصر": "101", "ماذر": "102", "نورة": "103", "محمد اليامي": "104", "عهود": "105"}
SUP = "900"
SAT = datetime.date(2026, 10, 3)     # publish day
SUN = datetime.date(2026, 10, 4)     # the night under test — مآثر's weekly day off (0)


def at(d, hh, mm=0):
    return datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=RIYADH)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="oncalltest_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        sdb.reset_init_cache()
        odb.reset_init_cache()
        db.reset_init_cache()
        sseed.seed_if_empty()
        self._env = {k: os.environ.get(k) for k in ("OPS_DISCORD_IDS", "OPS_NAME_ALIASES",
                                                     "OPS_LEAD_ID")}
        os.environ.update({"OPS_DISCORD_IDS": "", "OPS_NAME_ALIASES": "", "OPS_LEAD_ID": ""})
        OPS_HOST.discord_ids = lambda: dict(IDS)
        OPS_HOST.public_base = lambda: "https://ouja.test"
        self.sent = []
        self.clock = at(SAT, 11, 0)
        HOST.send = self.sent.append
        HOST.now = lambda: self.clock
        db.config_set("supervisor_did", SUP)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # helpers ---------------------------------------------------------------
    def tick(self, when):
        self.clock = when
        return notify.tick(when)

    def walk(self, start, end):
        """Tick every minute from start to end inclusive, like the real loop (a jump longer
        than 2 minutes between ticks IS bot downtime and voids checks)."""
        t = start
        while t <= end:
            self.tick(t)
            self.deliver_all()
            t += datetime.timedelta(minutes=1)

    def kinds(self):
        return [p["kind"] for p in self.sent]

    def deliver_all(self):
        """Pretend Discord delivered every reported payload, in order, with fake ids."""
        for i, p in enumerate(self.sent):
            r = p.get("report")
            if r and not p.get("_done"):
                notify.delivered(r, True, "dm%d" % i, True, "ch%d" % i)
                p["_done"] = True

    def publish_sunday(self):
        self.tick(at(SAT, 12, 0))
        self.deliver_all()
        return db.slots_for(SUN.isoformat())


class Publish(Case):
    def test_nothing_before_noon(self):
        self.tick(at(SAT, 11, 59))
        self.assertIsNone(db.night(SUN.isoformat()))

    def test_noon_publishes_tomorrow_once_without_the_day_off(self):
        slots = self.publish_sunday()
        names = [s["employee"] for s in slots]
        self.assertEqual(len(slots), 4)
        self.assertNotIn("مآثر", names)                   # Sunday is her weekly day off
        self.assertEqual(sorted((s["end_min"] - s["start_min"]) // 60 for s in slots), [1, 2, 2, 2])
        self.tick(at(SAT, 12, 1))
        self.assertEqual(self.kinds().count("schedule"), 1)
        self.assertEqual(db.night(SUN.isoformat())["message_id"], "ch0")

    def test_unlinked_person_is_left_out_and_supervisor_told(self):
        del IDS["عهود"]
        try:
            slots = self.publish_sunday()
        finally:
            IDS["عهود"] = "105"
        self.assertNotIn("عهود", [s["employee"] for s in slots])
        sup = [p for p in self.sent if p["kind"] == "supervisor"]
        self.assertEqual(sup[0]["dm"][0]["did"], SUP)
        self.assertIn("عهود", sup[0]["dm"][0]["text"])

    def test_leave_respected_but_morning_half_day_still_on_tonight(self):
        emps = {e["name"]: e["id"] for e in sdb.employees()}
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "shift,affects_coverage) VALUES(?,?,?,?,?,?,?)",
                    (emps["ناصر"], SUN.isoformat(), SUN.isoformat(), "annual", "approved", None, 1))
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "shift,affects_coverage) VALUES(?,?,?,?,?,?,?)",
                    (emps["نورة"], SUN.isoformat(), SUN.isoformat(), "half_day", "approved",
                     "morning", 1))
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "shift,affects_coverage) VALUES(?,?,?,?,?,?,?)",
                    (emps["عهود"], SUN.isoformat(), SUN.isoformat(), "half_day", "approved",
                     "evening", 0))
        names = [s["employee"] for s in self.publish_sunday()]
        self.assertNotIn("ناصر", names)
        self.assertNotIn("عهود", names)
        self.assertIn("نورة", names)


class Checks(Case):
    def first_slot(self):
        return self.publish_sunday()[0]

    def test_no_night_no_checks(self):
        self.tick(at(SUN, 17, 0))
        self.assertEqual(db.checks_on(SUN.isoformat()), [])

    def test_check_at_slot_start_and_answer(self):
        s = self.first_slot()
        self.tick(at(SUN, 17, 0))
        self.assertEqual(self.kinds().count("check"), 1)
        self.deliver_all()
        c = db.checks_on(SUN.isoformat())[0]
        code, _t = notify.answer_check(c["dm_message_id"], "999", at(SUN, 17, 2))
        self.assertEqual(code, "not_yours")
        code, _t = notify.answer_check(c["ch_message_id"], s["employee_did"], at(SUN, 17, 3))
        self.assertEqual(code, "answered")
        self.tick(at(SUN, 17, 11))
        self.assertEqual(db.check(c["id"])["status"], "answered")
        self.assertNotIn("miss", self.kinds())

    def test_reminder_fifteen_minutes_before(self):
        self.first_slot()
        self.tick(at(SUN, 16, 45))
        self.tick(at(SUN, 16, 46))
        self.assertEqual(self.kinds().count("reminder"), 1)

    def _miss_one(self, hh, mm):
        self.walk(at(SUN, hh, mm), at(SUN, hh, mm + 10))

    def test_two_misses_one_warning_three_misses_still_one(self):
        s = self.first_slot()
        self.assertEqual(s["end_min"] - s["start_min"], 120)        # 17:00-19:00
        self._miss_one(17, 0)
        self.assertEqual(odb.counts()["ops_warnings"], 0)
        self.assertEqual(self.kinds().count("miss"), 1)
        self._miss_one(17, 15)
        ws = odb.warnings_for(s["employee"], "active")
        self.assertEqual(len(ws), 1)
        self.assertEqual(odb.obligation(ws[0]["obligation_id"])["kind"], "oc")
        self.assertIn("warning", self.kinds())
        led = odb.q1("SELECT * FROM ops_commission_ledger WHERE employee=?", (s["employee"],))
        self.assertEqual(led["multiplier"], 0.9)
        self._miss_one(17, 30)
        self.assertEqual(len(odb.warnings_for(s["employee"])), 1)
        self.assertEqual(self.kinds().count("miss"), 3)

    def test_late_press_is_still_a_miss(self):
        s = self.first_slot()
        self._miss_one(17, 0)
        c = db.checks_on(SUN.isoformat())[0]
        code, _t = notify.answer_check(c["dm_message_id"], s["employee_did"], at(SUN, 17, 12))
        self.assertEqual(code, "late")
        self.assertEqual(db.check(c["id"])["status"], "late")

    def test_undelivered_check_is_void(self):
        self.first_slot()
        self.tick(at(SUN, 17, 0))                  # never delivered
        self.tick(at(SUN, 17, 1))
        self.tick(at(SUN, 17, 11))
        c = db.checks_on(SUN.isoformat())[0]
        self.assertEqual((c["status"], c["void_reason"]), ("voided", "not_delivered"))
        self.assertNotIn("miss", self.kinds())

    def test_bot_downtime_voids_and_never_warns(self):
        self.first_slot()
        self.tick(at(SUN, 17, 0))
        self.deliver_all()
        self.tick(at(SUN, 17, 1))
        self.tick(at(SUN, 17, 20))                # 19 minutes of silence = a redeploy
        rows = {c["due_at"][11:16]: c for c in db.checks_on(SUN.isoformat())}
        self.assertEqual(rows["17:00"]["status"], "voided")
        self.assertEqual(rows["17:00"]["void_reason"], "bot_down")
        self.assertEqual(rows["17:15"]["status"], "voided")        # never sent at all
        self.assertNotIn("miss", self.kinds())

    def test_switch_off_sends_nothing(self):
        self.first_slot()
        notify.set_enabled(False, "tester", at(SUN, 16, 0))
        n = len(self.sent)
        self.tick(at(SUN, 17, 0))
        self.assertEqual(len(self.sent), n)


class Swaps(Case):
    def setUp(self):
        super().setUp()
        self.slots = self.publish_sunday()
        self.a, self.b = self.slots[0], self.slots[1]

    def test_exchange_accept(self):
        ok, _t = notify.request_swap(self.a["id"], self.b["employee_did"], at(SAT, 13, 0))
        self.assertTrue(ok)
        self.deliver_all()
        sw = db.q1("SELECT * FROM oncall_swaps")
        ok, _t = notify.answer_swap(sw["message_id"], "999", True, at(SAT, 13, 5))
        self.assertFalse(ok)                                   # only the target answers
        ok, _t = notify.answer_swap(sw["message_id"], self.a["employee_did"], True, at(SAT, 13, 6))
        self.assertTrue(ok)
        self.assertEqual(db.slot(self.a["id"])["employee"], self.b["employee"])
        self.assertEqual(db.slot(self.b["id"])["employee"], self.a["employee"])
        self.assertIn("schedule_edit", self.kinds())

    def test_own_slot_refused(self):
        ok, _t = notify.request_swap(self.a["id"], self.a["employee_did"], at(SAT, 13, 0))
        self.assertFalse(ok)

    def test_lock_expires_pending_and_refuses_new(self):
        notify.request_swap(self.a["id"], self.b["employee_did"], at(SAT, 13, 0))
        self.tick(at(SUN, 15, 0))
        self.assertEqual(db.night(SUN.isoformat())["status"], "locked")
        self.assertEqual(db.q1("SELECT status FROM oncall_swaps")["status"], "expired")
        ok, _t = notify.request_swap(self.a["id"], self.b["employee_did"], at(SUN, 15, 1))
        self.assertFalse(ok)

    def test_editor_reassign_needs_reason(self):
        ok, err = notify.edit_slot(self.a["id"], "مآثر", "اسيل", "", at(SUN, 16, 0))
        self.assertFalse(ok)
        ok, err = notify.edit_slot(self.a["id"], "مآثر", "اسيل", "تغطية", at(SUN, 16, 0))
        self.assertTrue(ok, err)
        self.assertEqual(db.slot(self.a["id"])["employee"], "مآثر")


class Issues(Case):
    def setUp(self):
        super().setUp()
        self.slots = self.publish_sunday()
        self.first = self.slots[0]                             # 17:00-19:00

    def test_outside_window_nobody_owns(self):
        self.assertIsNone(notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 16, 30)))

    def test_owner_is_whoever_is_on_duty(self):
        r = notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        self.assertEqual(r["owner"], self.first["employee"])
        self.assertIsNone(notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 31)))

    def test_outside_claimer_is_helper_owner_stays(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        notify.on_escalation_claimed("m1", "اسيل", at(SUN, 17, 35))
        i = db.issue_by_ref("m1")
        self.assertEqual((i["owner"], i["helper"]), (self.first["employee"], "اسيل"))

    def test_claim_overdue_alert_once(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        self.tick(at(SUN, 17, 40))
        self.tick(at(SUN, 17, 41))
        self.assertEqual(self.kinds().count("claim_overdue"), 1)

    def test_stale_after_slot_end_once(self):
        notify.on_issue_opened("maint", "ch9", "تسريب", at(SUN, 18, 0))
        self.tick(at(SUN, 18, 50))
        self.assertNotIn("stale", self.kinds())
        self.tick(at(SUN, 19, 0))
        self.tick(at(SUN, 19, 40))
        self.assertEqual(self.kinds().count("stale"), 1)

    def test_resolve_permissions(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        notify.delivered({"what": "issue_note", "id": "m1"}, False, "", True, "note1")
        ok, _t = notify.resolve_press("note1", "999", False, at(SUN, 17, 50))
        self.assertFalse(ok)
        ok, _t = notify.resolve_press("note1", self.first["employee_did"], False, at(SUN, 17, 51))
        self.assertTrue(ok)
        self.assertIsNotNone(db.issue_by_ref("m1")["resolved_at"])

    def test_handover_and_summary(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        self.tick(at(SUN, 19, 0))
        ho = [p for p in self.sent if p["kind"] == "handover"]
        self.assertEqual(len(ho), 1)
        self.assertIn("ضيف", ho[0]["channel_text"])
        self.tick(at(SUN + datetime.timedelta(days=1), 0, 5))
        self.tick(at(SUN + datetime.timedelta(days=1), 0, 6))
        self.assertEqual(self.kinds().count("summary"), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python3 -m unittest tests.test_oncall_flow`
Expected: `ImportError: cannot import name 'db' from 'oncall'` (or `No module named 'oncall.host'`)

- [ ] **Step 3: Write the implementation**

Create `oncall/host.py`:

```python
# -*- coding: utf-8 -*-
"""
oncall.host — the ONE bridge between this package and bot.py (schedule/ops/reviewask pattern).
bot.py calls oncall.wire({...}) once at web-server start. This package NEVER does
`import bot`: bot.py runs as __main__, so importing it by name would boot a second bot.
"""


class _Host:
    # --- web / auth ---
    dash_auth = None         # (request) -> bool
    req_role = None          # (request) -> role string
    actor = None             # (request) -> display name of the logged-in user
    json_response = None     # (data, status=200) -> web.Response
    web = None               # aiohttp web module
    web_thread = None        # async (fn, *a) -> result   (bot.web_thread — never to_thread)

    # --- clock ---
    now = None               # () -> tz-aware Riyadh datetime

    # --- delivery ---
    # send(payload) -> None. bot.py schedules the Discord work from ANY thread and, when it
    # is done, calls oncall.notify.delivered(report, dm_ok, dm_mid, ch_ok, ch_mid).
    send = None

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("oncall used '%s' before oncall.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
```

Create `oncall/db.py`:

```python
# -*- coding: utf-8 -*-
"""
oncall.db — «المناوبة» storage inside the SAME brain.db every other package uses.

Connection rules are brain.db's (no WAL, journal_mode=DELETE, one short connection per call
via `with closing(connect())`) — read brain/db.py before changing anything here.

THREE RULES ARE ENFORCED BY THE SCHEMA, NOT BY CAREFUL CODE
  1. One check per (slot, time) — UNIQUE(slot_id, due_at). A double tick cannot ping twice.
  2. One issue per Discord reference — UNIQUE(ref). A re-fired hook cannot double-own.
  3. One slot per start time per night — UNIQUE(date, start_min).
Every table is prefixed `oncall_`.
"""

import datetime
import json
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS oncall_config (
    key     TEXT PRIMARY KEY,
    value   TEXT,
    set_by  TEXT,
    set_at  TEXT
);
CREATE TABLE IF NOT EXISTS oncall_nights (
    date          TEXT PRIMARY KEY,           -- 'YYYY-MM-DD' (the evening)
    status        TEXT NOT NULL,              -- published | locked
    published_at  TEXT,
    locked_at     TEXT,
    message_id    TEXT,                       -- the schedule post in «المناوبة»
    roster_json   TEXT,                       -- [{name, ok, why}] as decided at publish time
    summary_at    TEXT
);
CREATE TABLE IF NOT EXISTS oncall_slots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    employee     TEXT NOT NULL,
    employee_did TEXT,
    start_min    INTEGER NOT NULL,
    end_min      INTEGER NOT NULL,
    source       TEXT NOT NULL DEFAULT 'auto',  -- auto | swap | edit
    edited_by    TEXT,
    edit_reason  TEXT,
    reminded_at  TEXT,
    handover_at  TEXT,
    UNIQUE(date, start_min)
);
CREATE TABLE IF NOT EXISTS oncall_swaps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    slot_id     INTEGER NOT NULL,
    requester   TEXT NOT NULL,
    requester_did TEXT,
    target      TEXT NOT NULL,
    target_did  TEXT,
    kind        TEXT NOT NULL,               -- exchange | takeover
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|accepted|declined|expired
    created_at  TEXT,
    decided_at  TEXT,
    message_id  TEXT                          -- the DM that carries «موافق / لا»
);
CREATE TABLE IF NOT EXISTS oncall_checks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id       INTEGER NOT NULL,
    date          TEXT NOT NULL,
    employee      TEXT NOT NULL,
    employee_did  TEXT,
    due_at        TEXT NOT NULL,
    sent_at       TEXT,
    dm_ok         INTEGER DEFAULT 0,
    channel_ok    INTEGER DEFAULT 0,
    dm_message_id TEXT,
    ch_message_id TEXT,
    answered_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending|answered|missed|late|voided
    void_reason   TEXT,
    decided_at    TEXT,
    UNIQUE(slot_id, due_at)
);
CREATE TABLE IF NOT EXISTS oncall_issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,            -- escalation | maint
    ref             TEXT NOT NULL UNIQUE,     -- escalation card message id | ticket channel id
    title           TEXT,
    owner           TEXT NOT NULL,
    owner_did       TEXT,
    slot_id         INTEGER,
    date            TEXT,
    opened_at       TEXT NOT NULL,
    claimed_at      TEXT,
    claimed_by      TEXT,
    helper          TEXT,
    resolved_at     TEXT,
    resolved_by     TEXT,
    last_update_at  TEXT,
    claim_alerted_at TEXT,
    stale_alerted_night TEXT,
    note_message_id TEXT                      -- our «المناوب المسؤول» line (carries «انحلّت»)
);
CREATE TABLE IF NOT EXISTS oncall_events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       TEXT NOT NULL,
    kind     TEXT NOT NULL,
    employee TEXT,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS oncall_checks_date ON oncall_checks(date, employee);
CREATE INDEX IF NOT EXISTS oncall_events_kind ON oncall_events(kind, at);
"""

_inited = set()
_init_lock = threading.Lock()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()


def iso(dt):
    return dt.isoformat(timespec="seconds") if dt is not None else None


def parse(s):
    return datetime.datetime.fromisoformat(s) if s else None


# ------------------------------------------------------------------ thin sql helpers

def q(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        return [dict(r) for r in cx.execute(sql, args).fetchall()]


def q1(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute(sql, args).fetchone()
        return dict(r) if r else None


def execute(sql, args=()):
    """Returns (lastrowid, rowcount)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid, cur.rowcount


@contextmanager
def transaction():
    _ensure()
    with closing(_bdb.connect()) as cx:
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise


def counts():
    out = {}
    for t in ("oncall_config", "oncall_nights", "oncall_slots", "oncall_swaps",
              "oncall_checks", "oncall_issues", "oncall_events"):
        out[t] = (q1("SELECT COUNT(*) c FROM %s" % t) or {}).get("c", 0)
    return out


# ------------------------------------------------------------------ config

def config_get(key, default=""):
    r = q1("SELECT value FROM oncall_config WHERE key=?", (key,))
    v = (r or {}).get("value")
    return default if v is None else v


def config_set(key, value, by="", at=""):
    execute("INSERT INTO oncall_config(key,value,set_by,set_at) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, set_by=excluded.set_by, "
            "set_at=excluded.set_at", (key, value, by or "", at or ""))


def config_row(key):
    return q1("SELECT * FROM oncall_config WHERE key=?", (key,))


# ------------------------------------------------------------------ events

def log(kind, at, employee="", detail=None):
    execute("INSERT INTO oncall_events(at,kind,employee,detail) VALUES(?,?,?,?)",
            (iso(at) if not isinstance(at, str) else at, kind, employee or "",
             json.dumps(detail, ensure_ascii=False) if not isinstance(detail, str) else detail))


def events(kind=None, limit=200):
    if kind:
        return q("SELECT * FROM oncall_events WHERE kind=? ORDER BY id DESC LIMIT ?",
                 (kind, int(limit)))
    return q("SELECT * FROM oncall_events ORDER BY id DESC LIMIT ?", (int(limit),))


def downtimes(since):
    """[(start, end)] bot-down windows recorded by the heartbeat, newest first."""
    out = []
    for r in q("SELECT detail FROM oncall_events WHERE kind='downtime' AND at>=? ORDER BY id DESC",
               (iso(since),)):
        try:
            d = json.loads(r["detail"] or "{}")
            out.append((parse(d["from"]), parse(d["to"])))
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ nights + slots

def night(date_iso):
    return q1("SELECT * FROM oncall_nights WHERE date=?", (date_iso,))


def publish_night(date_iso, slots, roster, at):
    """Write a night and its slots in ONE transaction. Returns False if it already exists
    (a second tick, or a restart mid-publish, can never rebuild a published night)."""
    with transaction() as cx:
        cur = cx.execute("INSERT OR IGNORE INTO oncall_nights(date,status,published_at,roster_json)"
                         " VALUES(?,?,?,?)",
                         (date_iso, "published", iso(at), json.dumps(roster, ensure_ascii=False)))
        if cur.rowcount != 1:
            return False
        for s in slots:
            cx.execute("INSERT INTO oncall_slots(date,employee,employee_did,start_min,end_min,source)"
                       " VALUES(?,?,?,?,?, 'auto')",
                       (date_iso, s["employee"], s.get("employee_did") or "",
                        int(s["start_min"]), int(s["end_min"])))
    return True


def set_night_message(date_iso, message_id):
    execute("UPDATE oncall_nights SET message_id=? WHERE date=?", (str(message_id), date_iso))


def lock_night(date_iso, at):
    """published -> locked. Returns True only for the tick that actually flipped it."""
    _rid, n = execute("UPDATE oncall_nights SET status='locked', locked_at=? "
                      "WHERE date=? AND status='published'", (iso(at), date_iso))
    return n == 1


def mark_summary(date_iso, at):
    _rid, n = execute("UPDATE oncall_nights SET summary_at=? WHERE date=? AND summary_at IS NULL",
                      (iso(at), date_iso))
    return n == 1


def slots_for(date_iso):
    return q("SELECT * FROM oncall_slots WHERE date=? ORDER BY start_min", (date_iso,))


def slot(slot_id):
    return q1("SELECT * FROM oncall_slots WHERE id=?", (int(slot_id),))


def set_slot_employee(slot_id, employee, did, source, by="", reason=""):
    execute("UPDATE oncall_slots SET employee=?, employee_did=?, source=?, edited_by=?, "
            "edit_reason=?, reminded_at=NULL WHERE id=?",
            (employee, did or "", source, by or "", reason or "", int(slot_id)))
    return slot(slot_id)


def mark_slot(slot_id, field, at):
    """reminded_at | handover_at, set once. True only for the first caller."""
    assert field in ("reminded_at", "handover_at")
    _rid, n = execute("UPDATE oncall_slots SET %s=? WHERE id=? AND %s IS NULL" % (field, field),
                      (iso(at), int(slot_id)))
    return n == 1


def history(before_date_iso, nights=7):
    """[{date, slots}] for the `nights` published nights before the given date."""
    dates = [r["date"] for r in q("SELECT date FROM oncall_nights WHERE date<? "
                                  "ORDER BY date DESC LIMIT ?", (before_date_iso, int(nights)))]
    return [{"date": d, "slots": slots_for(d)} for d in sorted(dates)]


# ------------------------------------------------------------------ swaps

def create_swap(date_iso, slot_id, requester, requester_did, target, target_did, kind, at):
    rid, _n = execute("INSERT INTO oncall_swaps(date,slot_id,requester,requester_did,target,"
                      "target_did,kind,status,created_at) VALUES(?,?,?,?,?,?,?, 'pending', ?)",
                      (date_iso, int(slot_id), requester, requester_did or "", target,
                       target_did or "", kind, iso(at)))
    return swap(rid)


def swap(swap_id):
    return q1("SELECT * FROM oncall_swaps WHERE id=?", (int(swap_id),))


def swap_by_message(message_id):
    return q1("SELECT * FROM oncall_swaps WHERE message_id=?", (str(message_id),))


def set_swap_message(swap_id, message_id):
    execute("UPDATE oncall_swaps SET message_id=? WHERE id=?", (str(message_id), int(swap_id)))


def pending_swap_for_slot(slot_id):
    return q1("SELECT * FROM oncall_swaps WHERE slot_id=? AND status='pending'", (int(slot_id),))


def pending_swaps_on(date_iso):
    return q("SELECT * FROM oncall_swaps WHERE date=? AND status='pending'", (date_iso,))


def decide_swap(swap_id, status, at):
    """pending -> status. True only for the press that actually decided it."""
    _rid, n = execute("UPDATE oncall_swaps SET status=?, decided_at=? WHERE id=? AND status='pending'",
                      (status, iso(at), int(swap_id)))
    return n == 1


# ------------------------------------------------------------------ checks

def claim_check(slot_row, due_at, status="pending", void_reason=""):
    """INSERT OR IGNORE: returns the new row, or None when this (slot, time) already exists."""
    rid, n = execute("INSERT OR IGNORE INTO oncall_checks(slot_id,date,employee,employee_did,due_at,"
                     "status,void_reason) VALUES(?,?,?,?,?,?,?)",
                     (int(slot_row["id"]), slot_row["date"], slot_row["employee"],
                      slot_row.get("employee_did") or "", iso(due_at), status, void_reason))
    return check(rid) if n == 1 else None


def check(check_id):
    return q1("SELECT * FROM oncall_checks WHERE id=?", (int(check_id),))


def check_by_message(message_id):
    m = str(message_id)
    return q1("SELECT * FROM oncall_checks WHERE dm_message_id=? OR ch_message_id=?", (m, m))


def set_check_delivery(check_id, dm_ok, channel_ok, dm_mid, ch_mid, at):
    execute("UPDATE oncall_checks SET sent_at=?, dm_ok=?, channel_ok=?, dm_message_id=?, "
            "ch_message_id=? WHERE id=?",
            (iso(at), 1 if dm_ok else 0, 1 if channel_ok else 0,
             str(dm_mid or ""), str(ch_mid or ""), int(check_id)))


def pending_checks():
    return q("SELECT * FROM oncall_checks WHERE status='pending' ORDER BY due_at")


def decide_check(check_id, status, at, void_reason="", answered_at=None):
    """pending -> status. True only for whoever decided it first (button vs tick race)."""
    _rid, n = execute("UPDATE oncall_checks SET status=?, decided_at=?, void_reason=?, "
                      "answered_at=COALESCE(?, answered_at) WHERE id=? AND status='pending'",
                      (status, iso(at), void_reason or "", iso(answered_at), int(check_id)))
    return n == 1


def mark_late(check_id, at):
    execute("UPDATE oncall_checks SET status='late', answered_at=? WHERE id=? AND status='missed'",
            (iso(at), int(check_id)))


def misses_on(employee, date_iso):
    return (q1("SELECT COUNT(*) c FROM oncall_checks WHERE employee=? AND date=? "
               "AND status IN ('missed','late')", (employee, date_iso)) or {}).get("c", 0)


def checks_on(date_iso):
    return q("SELECT * FROM oncall_checks WHERE date=? ORDER BY due_at", (date_iso,))


def last_answered(employee, date_iso):
    return q1("SELECT * FROM oncall_checks WHERE employee=? AND date=? AND status='answered' "
              "ORDER BY due_at DESC LIMIT 1", (employee, date_iso))


def recent_problems(limit=60):
    return q("SELECT * FROM oncall_checks WHERE status IN ('missed','late','voided') "
             "ORDER BY due_at DESC LIMIT ?", (int(limit),))


# ------------------------------------------------------------------ issues

def open_issue(kind, ref, title, owner, owner_did, slot_id, date_iso, at):
    """Returns the issue row, or None if this ref already has one (the hook fired twice)."""
    rid, n = execute("INSERT OR IGNORE INTO oncall_issues(kind,ref,title,owner,owner_did,slot_id,"
                     "date,opened_at,last_update_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (kind, str(ref), title or "", owner, owner_did or "", slot_id, date_iso,
                      iso(at), iso(at)))
    return issue_by_ref(ref) if n == 1 else None


def issue_by_ref(ref):
    return q1("SELECT * FROM oncall_issues WHERE ref=?", (str(ref),))


def issue_by_note(message_id):
    return q1("SELECT * FROM oncall_issues WHERE note_message_id=?", (str(message_id),))


def set_issue_note(ref, message_id):
    execute("UPDATE oncall_issues SET note_message_id=? WHERE ref=?", (str(message_id), str(ref)))


def claim_issue(ref, by, helper, at):
    execute("UPDATE oncall_issues SET claimed_at=COALESCE(claimed_at, ?), "
            "claimed_by=COALESCE(claimed_by, ?), helper=COALESCE(helper, ?), last_update_at=? "
            "WHERE ref=? AND resolved_at IS NULL",
            (iso(at), by, helper, iso(at), str(ref)))


def touch_issue(ref, at):
    execute("UPDATE oncall_issues SET last_update_at=? WHERE ref=? AND resolved_at IS NULL",
            (iso(at), str(ref)))


def resolve_issue(ref, by, at):
    _rid, n = execute("UPDATE oncall_issues SET resolved_at=?, resolved_by=? "
                      "WHERE ref=? AND resolved_at IS NULL", (iso(at), by, str(ref)))
    return n == 1


def open_issues():
    return q("SELECT * FROM oncall_issues WHERE resolved_at IS NULL ORDER BY opened_at")


def recent_issues(limit=60):
    return q("SELECT * FROM oncall_issues ORDER BY id DESC LIMIT ?", (int(limit),))


def mark_issue(ref, field, value):
    assert field in ("claim_alerted_at", "stale_alerted_night")
    execute("UPDATE oncall_issues SET %s=? WHERE ref=?" % field, (value, str(ref)))
```

Create `oncall/roster.py`:

```python
# -*- coding: utf-8 -*-
"""
oncall.roster — WHO can be on duty on a date, and who the supervisor is.

Nothing here keeps its own copy of the team:
  * people, weekly day off  -> the Employee Calendar (schedule.owners.permanent_map)
  * recorded leave          -> schedule.db.absences_recorded_on
  * Discord ids             -> ops.notify.employees()  (typed > env > assignments.json)
Only the LIST of on-call names (default the five) and the supervisor live in oncall_config.
"""

import json

from . import db, engine

DEFAULT_ROSTER = ["نورة", "ناصر", "محمد اليامي", "عهود", "مآثر"]
DEFAULT_SUPERVISOR = "اسيل"

WHY_OFF_DAY = "يوم إجازته الأسبوعية"
WHY_LEAVE = "إجازة مسجّلة في تقويم الموظفين"
WHY_NO_DISCORD = "حسابه مو مربوط بديسكورد"
WHY_NOT_IN_CALENDAR = "مو موجود في تقويم الموظفين"


def roster_names():
    raw = db.config_get("roster", "")
    try:
        names = json.loads(raw) if raw else None
    except Exception:
        names = None
    return [n for n in (names or DEFAULT_ROSTER) if (n or "").strip()]


def _calendar():
    from schedule import owners as _sowners
    return (_sowners.permanent_map() or {}).get("employees", [])


def _ids():
    from ops import notify as _onotify
    return {e["name"]: e.get("did") or "" for e in _onotify.employees()}


def _leave_ids(date_iso):
    """Employee ids NOT available in the EVENING of date_iso.

    Inverse of the cleaning board's rule on purpose: a MORNING half-day is back by 17:00
    (available tonight), an EVENING half-day is not. Every other approved absence = away."""
    from schedule import db as _sdb
    away = set()
    for a in _sdb.absences_recorded_on(date_iso):
        if (a.get("type") or "") == "half_day" and (a.get("shift") or "") == "morning":
            continue
        away.add(a.get("employee_id"))
    return away


def availability(d):
    """[{name, did, ok, why}] in roster order for the evening of date d."""
    cal = _calendar()
    ids = _ids()
    away = _leave_ids(d.isoformat())
    sw = engine.sun_weekday(d)
    out = []
    for name in roster_names():
        emp = next((e for e in cal if engine.norm(e["name"]) == engine.norm(name)), None)
        did = next((v for k, v in ids.items() if engine.norm(k) == engine.norm(name)), "")
        if emp is None:
            out.append({"name": name, "did": did, "ok": False, "why": WHY_NOT_IN_CALENDAR})
        elif emp.get("off_day") is not None and int(emp["off_day"]) == sw:
            out.append({"name": name, "did": did, "ok": False, "why": WHY_OFF_DAY})
        elif emp.get("id") in away:
            out.append({"name": name, "did": did, "ok": False, "why": WHY_LEAVE})
        elif not did:
            out.append({"name": name, "did": "", "ok": False, "why": WHY_NO_DISCORD})
        else:
            out.append({"name": name, "did": did, "ok": True, "why": ""})
    return out


def name_for_did(did):
    did = str(did or "")
    if not did:
        return None
    ids = _ids()
    for name in roster_names():
        for k, v in ids.items():
            if engine.norm(k) == engine.norm(name) and str(v) == did:
                return name
    return None


def did_for(name):
    ids = _ids()
    return next((v for k, v in ids.items() if engine.norm(k) == engine.norm(name)), "")


def supervisor():
    """{name, did}. Typed in the tab > ops lead (the first appeal approver) > nothing."""
    did = (db.config_get("supervisor_did", "") or "").strip()
    if not did:
        try:
            from ops import notify as _onotify
            did = _onotify.lead_id() or ""
        except Exception:
            did = ""
    return {"name": db.config_get("supervisor_name", "") or DEFAULT_SUPERVISOR, "did": did}
```

Create `oncall/texts.py`:

```python
# -*- coding: utf-8 -*-
"""
oncall.texts — every Arabic word «المناوبة» sends. Najdi, short, phone-first.
One place, so the Discord post, the DM and the dashboard can never drift apart.
"""

from .engine import hm

DAYS_AR = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]

NOT_FOUND = "ما لقيت هالسؤال — يمكن انتهى."
NOT_YOURS = "هذي مو مناوبتك 🙂"
ALREADY = "مسجّل من قبل ✅"
THANKS = "تمام، مسجّل إنك موجود ✅"
LATE = "تأخرت عن العشر دقايق — انحسبت غياب. إذا عندك عذر كلّم اسيل."
NOT_ROSTER = "أنت مو من فريق المناوبة."
SWAP_SENT = "وصل طلبك لـ{who} — إذا وافق يتعدّل الجدول تلقائياً."
SWAP_GONE = "انتهى وقت التبديل — الجدول مقفل."
SWAP_CHANGED = "السلوت تغيّر صاحبه من بعد الطلب — الطلب لاغي."
RESOLVE_NOT_ALLOWED = "«انحلّت» لصاحب المشكلة أو اللي ساعده أو الأدمن بس."
RESOLVED = "تمام، انقفلت المشكلة ✅"


def day_label(d):
    from .engine import sun_weekday
    return "%s %s" % (DAYS_AR[sun_weekday(d)], d.strftime("%d/%m"))


def slot_label(s):
    return "%s – %s" % (hm(s["start_min"]), hm(s["end_min"]))


def schedule_text(d, slots, unavailable, locked):
    lines = ["🌙 **مناوبة ليلة %s** (٥ العصر – ١٢ الليل)" % day_label(d), ""]
    if not slots:
        lines.append("⚠️ ما فيه أحد متاح الليلة — اسيل بتتصرف.")
    for s in slots:
        mention = ("<@%s>" % s["employee_did"]) if s.get("employee_did") else s["employee"]
        lines.append("• %s ← %s" % (slot_label(s), mention))
    if unavailable:
        lines.append("")
        lines.append("مو موجودين: " + "، ".join("%s (%s)" % (u["name"], u["why"]) for u in unavailable))
    lines.append("")
    if locked:
        lines.append("🔒 الجدول مقفل — أي تغيير من اسيل.")
    else:
        lines.append("🔁 تبي تبدّل؟ اضغط على سلوت زميلك — التبديل لين ٣ العصر يوم المناوبة.")
    return "\n".join(lines)


def supervisor_roster_alert(d, unavailable, empty):
    head = ("⚠️ ليلة %s ما فيها أحد متاح للمناوبة!" % day_label(d)) if empty else \
           ("للعلم — جدول مناوبة %s نزل، وهذولي مو فيه:" % day_label(d))
    return "\n".join([head] + ["• %s — %s" % (u["name"], u["why"]) for u in unavailable])


def reminder(s):
    return "⏰ مناوبتك تبدأ %s وتخلص %s. أول سؤال «موجود؟» يوصلك أول ما تبدأ." % (
        hm(s["start_min"]), hm(s["end_min"]))


def check_text(due_label):
    return "✋ **موجود؟** (%s) — اضغط الزر خلال ١٠ دقايق." % due_label


def miss_dm(nth):
    if nth <= 1:
        return ("⚠️ ما ضغطت «موجود» خلال ١٠ دقايق. اسيل انبلغت وبتغطي لين ترجع. "
                "ترى المرة الثانية الليلة = إنذار رسمي.")
    if nth == 2:
        return "⚠️ ثاني غياب الليلة — انسجل عليك إنذار رسمي (التفاصيل والاعتراض في رسالة ثانية)."
    return "⚠️ ما ضغطت «موجود» مرة ثانية. اسيل انبلغت."


def supervisor_miss(employee, nth, slot):
    tail = " — وانسجل عليه إنذار رسمي." if nth == 2 else ""
    return "🚨 %s ما ردّ على «موجود؟» (مرة %d الليلة، سلوت %s). غطّي المناوبة لين يرجع%s" % (
        employee, nth, slot_label(slot), tail)


def warning_reason(date_label):
    return "غياب عن المناوبة مرتين ليلة %s (ما ضغط «موجود» خلال ١٠ دقايق)." % date_label


def warning_dm(date_label, pct, link):
    return "\n".join([
        "⚠️ انسجل إنذار — المناوبة (%s)" % date_label,
        "ما ضغطت «موجود» مرتين خلال مناوبتك.",
        "",
        "عمولتك لهذا الشهر صارت %s." % pct,
        "",
        "إذا تشوف إن الإنذار غلط، قدّم اعتراضك من هنا وبيوصل مباشرة للمسؤولين:",
        link])


def hr_line(employee, date_label, pct):
    return "\n".join(["⚠️ إنذار تلقائي — " + employee,
                      "المناوبة: " + date_label,
                      "السبب: غياب مرتين عن «موجود؟»",
                      "العمولة بعد الإنذار: " + pct])


def swap_ask(requester, target_slot, requester_slot, kind):
    if kind == "exchange":
        body = "%s يبي يبدّل معك: ياخذ سلوتك %s وتاخذ سلوته %s." % (
            requester, slot_label(target_slot), slot_label(requester_slot))
    else:
        body = "%s يبي ياخذ سلوتك %s (وأنت ترتاح)." % (requester, slot_label(target_slot))
    return "🔁 طلب تبديل مناوبة\n" + body + "\nموافق؟"


def swap_result(accepted, target, slot):
    if accepted:
        return "✅ %s وافق — السلوت %s صار لك." % (target, slot_label(slot))
    return "❌ %s رفض التبديل على %s." % (target, slot_label(slot))


def swap_fyi(requester, target, slot, kind):
    what = "بدّلوا" if kind == "exchange" else "أخذ السلوت"
    return "للعلم: %s و%s %s — %s." % (requester, target, what, slot_label(slot))


def swap_expired(slot):
    return "⌛ طلب التبديل على %s انتهى — الجدول تقفل الساعة ٣." % slot_label(slot)


def slot_edited_new(slot, by):
    return "📌 %s حطّتك في مناوبة الليلة %s." % (by, slot_label(slot))


def slot_edited_old(slot, by):
    return "📌 %s شالتك من مناوبة الليلة %s." % (by, slot_label(slot))


def issue_note(kind, owner_did, owner):
    who = ("<@%s>" % owner_did) if owner_did else owner
    if kind == "maint":
        return "🌙 متابع المناوبة: %s — التذكرة باسمه لين تتقفل." % who
    return ("🌙 المناوب المسؤول: %s — استلم خلال ١٠ دقايق (🙋 فوق)، وإذا خلصت اضغط ✅ انحلّت."
            % who)


def claim_overdue(issue):
    return "⏰ تصعيد «%s» عند %s ما انستلم من ١٠ دقايق — تابعيه." % (
        issue.get("title") or "—", issue["owner"])


def stale(issue):
    return "🕰️ مشكلة «%s» (صاحبها %s) ما تحدّثت من ٣٠ دقيقة وهو خلّص مناوبته — تابعيها." % (
        issue.get("title") or "—", issue["owner"])


def handover(slot, nxt, issues):
    who = ("<@%s>" % nxt["employee_did"]) if nxt.get("employee_did") else nxt["employee"]
    lines = ["🔄 تسليم %s: %s خلّص — دورك %s (%s)." % (
        hm(slot["end_min"]), slot["employee"], who, slot_label(nxt))]
    if issues:
        lines.append("مشاكل مفتوحة (تبقى باسم أصحابها):")
        lines += ["• %s — %s" % (i.get("title") or "—", i["owner"]) for i in issues]
    else:
        lines.append("ما فيه مشاكل مفتوحة 👌")
    return "\n".join(lines)


def night_summary(d, per, warnings, open_issues):
    lines = ["🌙 ملخص مناوبة %s" % day_label(d)]
    for p in per:
        lines.append("• %s: ردّ %d من %d%s" % (
            p["name"], p["answered"], p["total"],
            (" — غياب %d" % p["missed"]) if p["missed"] else ""))
    if warnings:
        lines.append("إنذارات: " + "، ".join(warnings))
    lines.append("مشاكل للحين مفتوحة: %d" % len(open_issues))
    return "\n".join(lines)
```

Create `oncall/notify.py`:

```python
# -*- coding: utf-8 -*-
"""
oncall.notify — the minute tick and every Discord-facing decision of «المناوبة».

tick(now) runs once a minute from bot.py (off the event loop). Each step is idempotent by a
database fact, so a double tick or a restart mid-tick can never ping twice:
    publish  12:00  tomorrow's night            (oncall_nights PK)
    lock     15:00  tonight                     (status flip published -> locked)
    remind   slot - 15 min                      (oncall_slots.reminded_at)
    checks   slot start, then every 15 min      (UNIQUE(slot_id, due_at))
    judge    10 min after each check            (status flip pending -> …)
    issues   claim overdue / stale              (claim_alerted_at / stale_alerted_night)
    handover at each slot end                   (oncall_slots.handover_at)
    summary  after midnight                     (oncall_nights.summary_at)

THE PRINCIPLE (shared with ops/): the system accuses, humans only forgive. The ONLY call to
ops.db.issue_warning in this package is in _warn(), reached only from the judge step.
"""

import datetime
import os

from . import db, engine, roster, texts
from .host import HOST

OC_KIND = "oc"                     # ops_obligations.kind for an on-call night


def channel_name():
    return os.environ.get("ONCALL_CHANNEL", "المناوبة")


def enabled():
    """Stored switch. Default ON (owner ruling: live from day one; he never edits Railway)."""
    return (db.config_get("enabled", "1") or "1") == "1"


def set_enabled(on, by, at):
    db.config_set("enabled", "1" if on else "0", by, db.iso(at))
    db.log("switch", at, by, {"on": bool(on)})


def _now():
    return HOST.require("now")()


def _send(payload):
    try:
        if HOST.send:
            HOST.send(payload)
            return True
    except Exception as e:
        print("[oncall] send failed:", e)
    return False


def _pct(mult):
    from ops import notify as _onotify
    return _onotify.ar_num(round(float(mult) * 100)) + "٪"


def _date(s):
    return datetime.date.fromisoformat(s)


# ------------------------------------------------------------------ THE TICK

def heartbeat(now):
    """A gap longer than DOWNTIME_GAP_SEC since the last tick is recorded as bot downtime;
    checks whose window it spans are voided (the employee never pays for a restart)."""
    last = db.parse(db.config_get("last_tick", ""))
    if last is not None and (now - last).total_seconds() > engine.DOWNTIME_GAP_SEC:
        db.log("downtime", now, "", {"from": db.iso(last), "to": db.iso(now)})
    db.config_set("last_tick", db.iso(now))


def tick(now=None):
    now = now or _now()
    if not enabled():
        db.config_set("last_tick", db.iso(now))
        return {"skipped": "off"}
    heartbeat(now)
    rep = {}
    for name, step in (("published", publish_due), ("locked", lock_due),
                       ("reminded", remind_due), ("checks", checks_due),
                       ("judged", judge_due), ("issues", issues_due),
                       ("handover", handover_due), ("summary", summary_due)):
        try:
            rep[name] = step(now)
        except Exception as e:                    # one broken step must not stop the others
            print("[oncall] %s step failed: %s" % (name, e))
            rep[name] = "error: %s" % e
    return rep


# ------------------------------------------------------------------ publish / lock

def _schedule_payload(date_iso, edit=False):
    n = db.night(date_iso)
    d = _date(date_iso)
    slots = db.slots_for(date_iso)
    roster_rows = []
    try:
        import json
        roster_rows = json.loads((n or {}).get("roster_json") or "[]")
    except Exception:
        pass
    unavailable = [r for r in roster_rows if not r.get("ok")]
    locked = (n or {}).get("status") != "published"
    return {"kind": "schedule_edit" if edit else "schedule",
            "channel_text": texts.schedule_text(d, slots, unavailable, locked),
            "view": "schedule",
            "slots": [{"id": s["id"], "label": texts.slot_label(s) + " · " + s["employee"],
                       "locked": locked} for s in slots],
            "edit_message_id": ((n or {}).get("message_id") or "") if edit else "",
            "report": {"what": "schedule", "id": date_iso} if not edit else None}


def publish_due(now):
    if now.hour < engine.PUBLISH_HOUR:
        return None
    d = now.date() + datetime.timedelta(days=1)
    di = d.isoformat()
    if db.night(di):
        return None
    av = roster.availability(d)
    names = [a["name"] for a in av if a["ok"]]
    dids = {a["name"]: a["did"] for a in av}
    slots = engine.build_night(d, names, db.history(di, 7))
    for s in slots:
        s["employee_did"] = dids.get(s["employee"], "")
    if not db.publish_night(di, slots, av, now):
        return None
    db.log("publish", now, "", {"date": di, "slots": len(slots)})
    _send(_schedule_payload(di))
    unavailable = [a for a in av if not a["ok"]]
    if unavailable or not slots:
        sup = roster.supervisor()
        _send({"kind": "supervisor", "dm": [{"did": sup["did"],
                                             "text": texts.supervisor_roster_alert(d, unavailable, not slots)}]})
    return di


def lock_due(now):
    if now.hour < engine.LOCK_HOUR:
        return None
    di = now.date().isoformat()
    n = db.night(di)
    if not n or n["status"] != "published" or not db.lock_night(di, now):
        return None
    for sw in db.pending_swaps_on(di):
        if db.decide_swap(sw["id"], "expired", now):
            s = db.slot(sw["slot_id"])
            _send({"kind": "swap_expired",
                   "dm": [{"did": sw["requester_did"], "text": texts.swap_expired(s)},
                          {"did": sw["target_did"], "text": texts.swap_expired(s)}]})
    _send(_schedule_payload(di, edit=True))
    db.log("lock", now, "", {"date": di})
    return di


# ------------------------------------------------------------------ reminders + checks

def _live_night(d):
    n = db.night(d.isoformat())
    return n if n and n["status"] in ("published", "locked") else None


def remind_due(now):
    d = now.date()
    if not _live_night(d):
        return 0
    sent = 0
    for s in db.slots_for(d.isoformat()):
        start = engine.at_minute(d, s["start_min"], now.tzinfo)
        if start - datetime.timedelta(minutes=engine.REMIND_BEFORE_MIN) <= now < start \
                and s["employee_did"] and db.mark_slot(s["id"], "reminded_at", now):
            _send({"kind": "reminder", "dm": [{"did": s["employee_did"], "text": texts.reminder(s)}]})
            sent += 1
    return sent


def checks_due(now):
    nd, _m = engine.night_minute(now)
    if nd is None or not _live_night(nd):
        return 0               # safety net 3: a night never published can never produce a miss
    sent = 0
    for s in db.slots_for(nd.isoformat()):
        for cm in engine.check_minutes(s["start_min"], s["end_min"]):
            due = engine.at_minute(nd, cm, now.tzinfo)
            if due > now:
                break
            if now - due > datetime.timedelta(minutes=engine.SEND_GRACE_MIN):
                db.claim_check(s, due, status="voided", void_reason="bot_down")
                continue
            row = db.claim_check(s, due)
            if row is None:
                continue
            if not s["employee_did"]:
                db.decide_check(row["id"], "voided", now, "unreachable")
                continue
            _send({"kind": "check",
                   "dm": [{"did": s["employee_did"], "text": texts.check_text(engine.hm(cm))}],
                   "channel_text": "<@%s> %s" % (s["employee_did"], texts.check_text(engine.hm(cm))),
                   "mentions": [s["employee_did"]],
                   "view": "here",
                   "report": {"what": "check", "id": row["id"]}})
            sent += 1
    return sent


def delivered(report, dm_ok, dm_mid, ch_ok, ch_mid):
    """bot.py calls this after the Discord work (from a worker thread)."""
    if not report:
        return
    now = _now()
    what, rid = report.get("what"), report.get("id")
    if what == "check":
        db.set_check_delivery(rid, dm_ok, ch_ok, dm_mid, ch_mid, now)
    elif what == "swap":
        db.set_swap_message(rid, dm_mid)
    elif what == "schedule":
        db.set_night_message(rid, ch_mid)
    elif what == "issue_note":
        db.set_issue_note(rid, ch_mid)


def _judge_one(c, now, downs):
    """Decide one pending check. Returns the new status or 'pending'."""
    due = db.parse(c["due_at"])
    if c["sent_at"] is None and now < due + datetime.timedelta(minutes=engine.ANSWER_WINDOW_MIN):
        return "pending"
    verdict, reason = engine.check_verdict(due, now, bool(c["dm_ok"] or c["channel_ok"]),
                                           db.parse(c["answered_at"]), downs)
    if verdict == "pending":
        return "pending"
    if verdict == "voided":
        db.decide_check(c["id"], "voided", now, reason)
        return "voided"
    if verdict == "answered":
        db.decide_check(c["id"], "answered", now)
        return "answered"
    if db.decide_check(c["id"], "missed", now):
        _on_miss(c, now)
    return "missed"


def judge_due(now):
    downs = db.downtimes(now - datetime.timedelta(days=1))
    n = 0
    for c in db.pending_checks():
        if _judge_one(c, now, downs) != "pending":
            n += 1
    return n


def _on_miss(c, now):
    nth = db.misses_on(c["employee"], c["date"])
    decision = engine.miss_decision(nth)
    s = db.slot(c["slot_id"]) or {"start_min": 0, "end_min": 0}
    sup = roster.supervisor()
    sup_text = texts.supervisor_miss(c["employee"], nth, s)
    _send({"kind": "miss",
           "dm": [{"did": c["employee_did"], "text": texts.miss_dm(nth)},
                  {"did": sup["did"], "text": sup_text}],
           "channel_text": (("<@%s> " % sup["did"]) if sup["did"] else "") + sup_text,
           "mentions": [sup["did"]] if sup["did"] else []})
    db.log("miss", now, c["employee"], {"check": c["id"], "nth": nth, "decision": decision})
    if decision == engine.MISS_WARN:
        _warn(c["employee"], c["employee_did"], c["date"], now)


def _warn(employee, did, date_iso, now):
    """THE ONLY ops.db.issue_warning CALL IN THIS PACKAGE. One per employee per night,
    by ops' own UNIQUE(kind, employee, period_key) + UNIQUE(obligation_id)."""
    from ops import db as odb, engine as oeng, notify as onotify
    label = texts.day_label(_date(date_iso))
    ob = odb.ensure_obligation(OC_KIND, employee, did, "OC-" + date_iso, now)
    odb.set_status(ob["id"], "missed")
    w = odb.issue_warning(ob, texts.warning_reason(label))
    led = odb.recompute_commission(employee, oeng.month_key(now.date()))
    link = onotify._appeal_link(w["appeal_token"])
    _send({"kind": "warning",
           "dm": [{"did": did, "text": texts.warning_dm(label, _pct(led["multiplier"]), link)}],
           "hr_channel": onotify.hr_channel(),
           "hr_text": texts.hr_line(employee, label, _pct(led["multiplier"]))})
    db.log("warning", now, employee, {"date": date_iso, "warning_id": w["id"]})
    return w


def answer_check(message_id, presser_did, now=None):
    """The «✋ موجود» button. Returns (code, text_ar)."""
    now = now or _now()
    c = db.check_by_message(message_id)
    if not c:
        return "unknown", texts.NOT_FOUND
    if str(presser_did or "") != str(c["employee_did"] or ""):
        return "not_yours", texts.NOT_YOURS
    if c["status"] == "pending":
        due = db.parse(c["due_at"])
        if now <= due + datetime.timedelta(minutes=engine.ANSWER_WINDOW_MIN):
            if db.decide_check(c["id"], "answered", now, answered_at=now):
                return "answered", texts.THANKS
        else:
            _judge_one(c, now, db.downtimes(now - datetime.timedelta(days=1)))
        c = db.check(c["id"])
    if c["status"] == "answered":
        return "already", texts.ALREADY
    if c["status"] in ("missed", "late"):
        db.mark_late(c["id"], now)
        return "late", texts.LATE
    return "void", texts.THANKS


# ------------------------------------------------------------------ swaps

def request_swap(slot_id, presser_did, now=None):
    now = now or _now()
    s = db.slot(slot_id)
    requester = roster.name_for_did(presser_did)
    if not requester:
        return False, texts.NOT_ROSTER
    if not s:
        return False, "ما لقيت السلوت."
    n = db.night(s["date"]) or {}
    mine = next((x for x in db.slots_for(s["date"])
                 if engine.same_person(x["employee"], requester)), None)
    av = {a["name"]: a for a in roster.availability(_date(s["date"]))}
    ok, kind, why = engine.swap_decision(
        n.get("status"), requester, s, mine, bool((av.get(requester) or {}).get("ok")),
        bool(s["employee_did"]), bool(db.pending_swap_for_slot(s["id"])))
    if not ok:
        return False, why
    sw = db.create_swap(s["date"], s["id"], requester, str(presser_did), s["employee"],
                        s["employee_did"], kind, now)
    _send({"kind": "swap_ask", "view": "swap_ask",
           "dm": [{"did": s["employee_did"], "text": texts.swap_ask(requester, s, mine, kind)}],
           "report": {"what": "swap", "id": sw["id"]}})
    db.log("swap_request", now, requester, {"swap": sw["id"], "slot": s["id"], "kind": kind})
    return True, texts.SWAP_SENT.format(who=s["employee"])


def answer_swap(message_id, presser_did, accept, now=None):
    now = now or _now()
    sw = db.swap_by_message(message_id)
    if not sw:
        return False, texts.NOT_FOUND
    if str(presser_did or "") != str(sw["target_did"] or ""):
        return False, texts.NOT_YOURS
    n = db.night(sw["date"]) or {}
    s = db.slot(sw["slot_id"])
    if n.get("status") != "published":
        db.decide_swap(sw["id"], "expired", now)
        return False, texts.SWAP_GONE
    if not s or not engine.same_person(s["employee"], sw["target"]):
        db.decide_swap(sw["id"], "expired", now)
        return False, texts.SWAP_CHANGED
    if not db.decide_swap(sw["id"], "accepted" if accept else "declined", now):
        return False, texts.ALREADY
    if not accept:
        _send({"kind": "swap_declined",
               "dm": [{"did": sw["requester_did"], "text": texts.swap_result(False, sw["target"], s)}]})
        return True, "تم — رفضت الطلب."
    mine = next((x for x in db.slots_for(sw["date"])
                 if engine.same_person(x["employee"], sw["requester"])), None)
    db.set_slot_employee(s["id"], sw["requester"], sw["requester_did"], "swap", sw["target"])
    if sw["kind"] == "exchange" and mine:
        db.set_slot_employee(mine["id"], sw["target"], sw["target_did"], "swap", sw["target"])
    sup = roster.supervisor()
    _send({"kind": "swap_accepted",
           "dm": [{"did": sw["requester_did"], "text": texts.swap_result(True, sw["target"], s)},
                  {"did": sup["did"], "text": texts.swap_fyi(sw["requester"], sw["target"], s, sw["kind"])}]})
    _send(_schedule_payload(sw["date"], edit=True))
    db.log("swap_accepted", now, sw["target"], {"swap": sw["id"]})
    return True, "تم — الجدول تعدّل ✅"


def edit_slot(slot_id, employee, by, reason, now=None):
    """Dashboard reassignment by an editor (اسيل / admin). Works on a locked night too."""
    now = now or _now()
    s = db.slot(slot_id)
    if not s:
        return False, "ما لقيت السلوت."
    if not (reason or "").strip():
        return False, "اكتب سبب التغيير."
    if employee not in roster.roster_names():
        return False, "الاسم مو من فريق المناوبة."
    did = roster.did_for(employee)
    if not did:
        return False, "حساب %s مو مربوط بديسكورد — ما نقدر نسأله «موجود؟»." % employee
    old = dict(s)
    s = db.set_slot_employee(slot_id, employee, did, "edit", by, reason)
    _send({"kind": "slot_edit",
           "dm": [{"did": did, "text": texts.slot_edited_new(s, by)},
                  {"did": old["employee_did"], "text": texts.slot_edited_old(old, by)}]})
    _send(_schedule_payload(s["date"], edit=True))
    db.log("slot_edit", now, by, {"slot": s["id"], "from": old["employee"], "to": employee,
                                  "reason": reason})
    return True, ""


# ------------------------------------------------------------------ issue ownership (hooks)

def owner_now(now):
    nd, m = engine.night_minute(now)
    if nd is None or not _live_night(nd):
        return None
    return engine.owner_at(db.slots_for(nd.isoformat()), m)


def on_issue_opened(kind, ref, title, now=None):
    """Escalation card posted / maintenance ticket opened. Returns the note payload text for
    bot.py to post under it, or None when nobody is on duty (outside 17-24 or no night)."""
    now = now or _now()
    if not enabled():
        return None
    s = owner_now(now)
    if not s:
        return None
    row = db.open_issue(kind, ref, title, s["employee"], s["employee_did"], s["id"], s["date"], now)
    if not row:
        return None
    db.log("issue_open", now, s["employee"], {"kind": kind, "ref": str(ref)})
    return {"owner": s["employee"], "owner_did": s["employee_did"],
            "text": texts.issue_note(kind, s["employee_did"], s["employee"])}


def on_escalation_claimed(ref, by_name, now=None):
    now = now or _now()
    i = db.issue_by_ref(ref)
    if not i:
        return
    helper = None if engine.same_person(by_name, i["owner"]) else by_name
    db.claim_issue(ref, by_name, helper, now)


def on_issue_resolved(ref, by, now=None):
    now = now or _now()
    if db.resolve_issue(ref, by, now):
        db.log("issue_resolved", now, by, {"ref": str(ref)})


def on_ticket_message(ref, author_did, now=None):
    i = db.issue_by_ref(ref)
    if i and not i["resolved_at"] and str(author_did) == str(i["owner_did"] or ""):
        db.touch_issue(ref, now or _now())


def resolve_press(note_message_id, presser_did, is_admin, now=None):
    now = now or _now()
    i = db.issue_by_note(note_message_id)
    if not i:
        return False, texts.NOT_FOUND
    if i["resolved_at"]:
        return False, texts.ALREADY
    who = roster.name_for_did(presser_did) or ""
    allowed = (str(presser_did) == str(i["owner_did"] or "") or is_admin
               or (i["helper"] and engine.same_person(who, i["helper"])))
    if not allowed:
        return False, texts.RESOLVE_NOT_ALLOWED
    on_issue_resolved(i["ref"], who or str(presser_did), now)
    return True, texts.RESOLVED


def issues_due(now):
    if engine.night_minute(now)[0] is None:
        return 0
    sup = roster.supervisor()
    tonight = now.date().isoformat()
    n = 0
    for i in db.open_issues():
        opened = db.parse(i["opened_at"])
        if i["kind"] == "escalation" and engine.claim_overdue(
                opened, db.parse(i["claimed_at"]), now, bool(i["claim_alerted_at"])):
            db.mark_issue(i["ref"], "claim_alerted_at", db.iso(now))
            _send({"kind": "claim_overdue", "dm": [{"did": sup["did"], "text": texts.claim_overdue(i)}]})
            n += 1
        s = db.slot(i["slot_id"]) if i["slot_id"] else None
        if not s:
            continue
        slot_end = engine.at_minute(_date(s["date"]), s["end_min"], now.tzinfo)
        last = max(t for t in (opened, db.parse(i["claimed_at"]), db.parse(i["last_update_at"]))
                   if t is not None)
        if engine.stale_due(slot_end, last, now, i["stale_alerted_night"] == tonight):
            db.mark_issue(i["ref"], "stale_alerted_night", tonight)
            _send({"kind": "stale", "dm": [{"did": sup["did"], "text": texts.stale(i)}]})
            n += 1
    return n


# ------------------------------------------------------------------ handover + summary

def handover_due(now):
    d = now.date()
    if not _live_night(d):
        return 0
    slots = db.slots_for(d.isoformat())
    n = 0
    for s in slots:
        if s["end_min"] >= engine.WINDOW_MINUTES:
            continue
        end = engine.at_minute(d, s["end_min"], now.tzinfo)
        if not (end <= now < end + datetime.timedelta(minutes=engine.HANDOVER_GRACE_MIN)):
            continue
        if not db.mark_slot(s["id"], "handover_at", now):
            continue
        nxt = next((x for x in slots if x["start_min"] == s["end_min"]), None)
        if not nxt:
            continue
        _send({"kind": "handover",
               "channel_text": texts.handover(s, nxt, db.open_issues()),
               "mentions": [nxt["employee_did"]] if nxt["employee_did"] else []})
        n += 1
    return n


def summary_due(now):
    if now.hour >= engine.PUBLISH_HOUR:
        return None
    d = now.date() - datetime.timedelta(days=1)
    di = d.isoformat()
    if not db.night(di) or not db.mark_summary(di, now):
        return None
    checks = db.checks_on(di)
    per = []
    for s in db.slots_for(di):
        mine = [c for c in checks if c["slot_id"] == s["id"]]
        per.append({"name": s["employee"],
                    "answered": sum(1 for c in mine if c["status"] == "answered"),
                    "total": sum(1 for c in mine if c["status"] != "voided"),
                    "missed": sum(1 for c in mine if c["status"] in ("missed", "late"))})
    warned = [e["employee"] for e in db.events("warning", 50)
              if '"date": "%s"' % di in (e["detail"] or "")]
    text = texts.night_summary(d, per, warned, db.open_issues())
    sup = roster.supervisor()
    _send({"kind": "summary", "dm": [{"did": sup["did"], "text": text}], "channel_text": text})
    return di
```

Replace `oncall/__init__.py` (interim, routes come in Task 4):

```python
# -*- coding: utf-8 -*-
"""oncall — «المناوبة», the evening on-call rotation (17:00-24:00). See Task 4 for the full doc."""

from . import engine, db, roster, texts, notify  # noqa: F401
from .host import HOST, wire  # noqa: F401
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest tests.test_oncall_engine tests.test_oncall_flow`
Expected: `Ran 54 tests … OK`. The `[oncall]` / `[ops]` print lines are normal.

- [ ] **Step 5: Commit**

```bash
git add oncall/__init__.py oncall/host.py oncall/db.py oncall/roster.py oncall/texts.py oncall/notify.py tests/test_oncall_flow.py
git commit -m "feat(oncall): storage, roster, Arabic texts and the minute tick — publish/lock/checks/ladder/issues

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: A missed on-call night breaks the clean-week streak (ops)

**Files:**
- Modify: `ops/notify.py`, inside `_retirement(name)` (the `rows = db.obligations_for_employee(name, WEEKLY_KIND, limit=12)` block, about line 710)
- Test: `tests/test_oncall_retirement.py`

**Interfaces:**
- Consumes: ops obligations of kind `oc` with period `OC-YYYY-MM-DD` (written by Task 2's `_warn`), and `ops.engine.iso_week_key`.
- Produces: no new API. `_retirement` now treats any ISO week containing a missed `oc` obligation as not clean.

- [ ] **Step 1: Write the failing test**

Create `tests/test_oncall_retirement.py`:

```python
# -*- coding: utf-8 -*-
"""
ops «4 clean weeks retire the oldest warning» x «المناوبة»: a week in which somebody missed an
on-call night is NOT clean (owner-approved assumption 1 in the spec).

Run: python3 -m unittest tests.test_oncall_retirement
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import db as odb                     # noqa: E402
from tests.test_oncall_flow import Case       # noqa: E402


class Retirement(Case):
    def test_week_with_oncall_warning_is_not_clean(self):
        from ops import notify as onotify
        name = "ناصر"
        for wk in ("2026-W36", "2026-W37", "2026-W38", "2026-W39"):
            ob = odb.ensure_obligation("wr", name, "101", wk, "2026-10-01T23:59:00+03:00")
            odb.set_status(ob["id"], "done")
        oc = odb.ensure_obligation("oc", name, "101", "OC-2026-09-29", "2026-09-29T19:10:00+03:00")
        odb.set_status(oc["id"], "missed")
        odb.issue_warning(oc, "test")
        os.environ["OPS_WARN_DRYRUN"] = "0"
        try:
            from ops import switch as osw
            osw.invalidate()
            r = onotify._retirement(name)
        finally:
            os.environ.pop("OPS_WARN_DRYRUN", None)
        self.assertIsNone(r)                      # W40 (29 Sep) had the on-call warning
        self.assertEqual(len(odb.warnings_for(name, "active")), 1)




if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python3 -m unittest tests.test_oncall_retirement`
Expected: `AssertionError: {'employee': 'ناصر', 'warning_id': 'wn_ناصر_OC-2026-09-29', 'through': '2026-W39'} is not None`. Four clean report weeks BEFORE the warning would retire it the moment it was issued.

- [ ] **Step 3: Write the implementation**

In `ops/notify.py`, replace exactly:

```python
    rows = db.obligations_for_employee(name, WEEKLY_KIND, limit=12)
    weeks = [{"period_key": r["period_key"],
              "clean": r["status"] in ("done", "waived", "excused")}
             for r in sorted(rows, key=lambda r: r["period_key"])
             if r["status"] != "pending"]
```

with:

```python
    rows = db.obligations_for_employee(name, WEEKLY_KIND, limit=12)
    by_week = {r["period_key"]: r["status"] in ("done", "waived", "excused")
               for r in rows if r["status"] != "pending"}
    # «المناوبة»: a week in which the person missed an on-call night ('OC-YYYY-MM-DD') is
    # NOT clean, even if the weekly report was on time — otherwise four clean report weeks
    # BEFORE an on-call warning would retire it the minute it was issued.
    for r in db.obligations_for_employee(name, "oc", limit=200):
        if r["status"] == "missed":
            by_week[engine.iso_week_key(r["period_key"][3:])] = False
    weeks = [{"period_key": k, "clean": v} for k, v in sorted(by_week.items())]
```

- [ ] **Step 4: Run the tests and confirm they pass, ops included**

Run: `python3 -m unittest tests.test_oncall_retirement tests.test_ops_flow`
Expected: `Ran 58 tests … OK`. The 57 existing ops tests are unchanged.

- [ ] **Step 5: Commit**

```bash
git add ops/notify.py tests/test_oncall_retirement.py
git commit -m "fix(ops): a week with a missed on-call night is not a clean week

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Dashboard endpoints and the tab script

**Files:**
- Create: `oncall/routes.py`
- Create: `oncall/static/oncall_tab.js`
- Modify: `oncall/__init__.py` (final)
- Test: `tests/test_oncall_routes.py`

**Interfaces:**
- Consumes:
  - Task 2's `notify.*`, `roster.*` and `db.*`.
  - `HOST.dash_auth/req_role/actor/json_response/web/web_thread/now`.
  - Dashboard JS globals `api, post, esc, labelText, toast, putHtml, emptyState, errorState`.
- Produces:
  - `routes.register_routes(app)`
  - `routes.js_version()->str`
  - `routes.state_payload(now)->dict`
  - `routes._save_settings(body, by, now)->(ok,err)`
  - Endpoints: `GET /api/oncall/state`, `POST /api/oncall/slot|switch|settings`, `GET /oncall/static/oncall_tab.js`
  - `window.OncallTab.load(force)` in the browser

- [ ] **Step 1: Write the failing test**

Create `tests/test_oncall_routes.py`:

```python
# -*- coding: utf-8 -*-
"""
«المناوبة» dashboard data + the accountability invariant.

Run: python3 -m unittest tests.test_oncall_routes
"""

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oncall import notify, routes                   # noqa: E402
from tests.test_oncall_flow import Case, SUN, at     # noqa: E402


class State(Case):
    def test_state_before_and_during_a_night(self):
        s = routes.state_payload(at(SUN, 12, 0))
        self.assertEqual(s["tonight"]["status"], "none")
        self.publish_sunday()
        s = routes.state_payload(at(SUN, 17, 20))
        self.assertTrue(s["in_window"])
        self.assertEqual(s["tonight"]["status"], "published")
        self.assertEqual(len(s["tonight"]["slots"]), 4)
        self.assertEqual(s["now"]["employee"], s["tonight"]["slots"][0]["employee"])
        self.assertEqual(s["now"]["next_check"], "5:30")
        self.assertEqual(s["settings"]["supervisor_name"], "اسيل")

    def test_settings_refuse_an_empty_roster(self):
        ok, err = routes._save_settings({"roster": []}, "tester", at(SUN, 12, 0))
        self.assertFalse(ok)
        ok, _ = routes._save_settings({"supervisor_did": "<@123>"}, "tester", at(SUN, 12, 0))
        self.assertTrue(ok)
        from oncall import db
        self.assertEqual(db.config_get("supervisor_did"), "123")


class Invariant(unittest.TestCase):
    """The system accuses, humans only forgive — same rule as ops/."""

    def test_no_route_can_reach_a_warning(self):
        self.assertNotIn("issue_warning", inspect.getsource(routes))

    def test_one_warning_call_site(self):
        self.assertEqual(inspect.getsource(notify).count("odb.issue_warning("), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python3 -m unittest tests.test_oncall_routes`
Expected: `ImportError: cannot import name 'routes' from 'oncall'`

- [ ] **Step 3: Write the implementation**

Create `oncall/routes.py`:

```python
# -*- coding: utf-8 -*-
"""
oncall.routes — «المناوبة» endpoints.

    GET  /oncall/static/oncall_tab.js   PUBLIC code, no data (the dashboard tab)
    GET  /api/oncall/state              login + «oncall» read (bot.py _ROLE_READ_RULES)
    POST /api/oncall/slot               reassign a slot (reason required)
    POST /api/oncall/switch             master ON/OFF
    POST /api/oncall/settings           roster + supervisor
Every write: login + «oncall» write (bot.py _ROLE_WRITE_RULES) AND role in admin/ops here.
There is deliberately NO endpoint that issues, voids or forgives a warning — forgiveness is
ops' appeal flow at /compliance, unchanged.
"""

import datetime
import json
import os
import traceback

from . import db, engine, notify, roster, texts
from .host import HOST

EDIT_ROLES = ("admin", "ops")
STATIC_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "oncall_tab.js")
_js_cache = {"mtime": None, "text": ""}


def can_edit(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in EDIT_ROLES
    except Exception:
        return False


def _actor(request):
    try:
        return (HOST.actor(request) if HOST.actor else "") or "غير معروف"
    except Exception:
        return "غير معروف"


def _json(data, status=200):
    return HOST.json_response(data, status)


async def _run(fn, *a, **kw):
    return await HOST.web_thread(fn, *a, **kw)


def _safe(fn):
    async def _w(request):
        if not HOST.dash_auth(request):
            return _json({"ok": False, "error": "unauthorized"}, 401)
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return _json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _deny():
    return _json({"ok": False, "error": "غير مصرّح لك بالتعديل"}, 403)


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


# ------------------------------------------------------------------ the state

def _night_view(d):
    di = d.isoformat()
    n = db.night(di)
    if not n:
        return {"date": di, "label": texts.day_label(d), "status": "none", "slots": [],
                "unavailable": []}
    try:
        roster_rows = json.loads(n.get("roster_json") or "[]")
    except Exception:
        roster_rows = []
    checks = db.checks_on(di)
    slots = []
    for s in db.slots_for(di):
        mine = [c for c in checks if c["slot_id"] == s["id"]]
        slots.append({"id": s["id"], "employee": s["employee"], "linked": bool(s["employee_did"]),
                      "from": engine.hm(s["start_min"]), "to": engine.hm(s["end_min"]),
                      "source": s["source"], "edited_by": s["edited_by"] or "",
                      "edit_reason": s["edit_reason"] or "",
                      "answered": sum(1 for c in mine if c["status"] == "answered"),
                      "missed": sum(1 for c in mine if c["status"] in ("missed", "late")),
                      "voided": sum(1 for c in mine if c["status"] == "voided")})
    return {"date": di, "label": texts.day_label(d), "status": n["status"], "slots": slots,
            "unavailable": [r for r in roster_rows if not r.get("ok")]}


def state_payload(now):
    today = now.date()
    cur = notify.owner_now(now)
    nd, m = engine.night_minute(now)
    on_now = None
    if cur:
        last = db.last_answered(cur["employee"], cur["date"])
        nxt = next((x for x in engine.check_minutes(cur["start_min"], cur["end_min"]) if x > m), None)
        on_now = {"employee": cur["employee"], "from": engine.hm(cur["start_min"]),
                  "to": engine.hm(cur["end_min"]),
                  "last_answered": (last or {}).get("answered_at") or "",
                  "next_check": engine.hm(nxt) if nxt is not None else ""}
    sup = roster.supervisor()
    issues = []
    for i in db.open_issues() + [x for x in db.recent_issues(30) if x["resolved_at"]]:
        issues.append({"kind": i["kind"], "title": i["title"] or "", "owner": i["owner"],
                       "helper": i["helper"] or "", "opened_at": i["opened_at"],
                       "claimed_at": i["claimed_at"] or "", "resolved_at": i["resolved_at"] or "",
                       "resolved_by": i["resolved_by"] or ""})
    problems = [{"employee": c["employee"], "date": c["date"], "due_at": c["due_at"],
                 "status": c["status"], "void_reason": c["void_reason"] or ""}
                for c in db.recent_problems(60)]
    warnings = [{"employee": e["employee"], "at": e["at"], "detail": e["detail"]}
                for e in db.events("warning", 30)]
    return {"ok": True, "enabled": notify.enabled(), "in_window": nd is not None,
            "now": on_now,
            "tonight": _night_view(today),
            "tomorrow": _night_view(today + datetime.timedelta(days=1)),
            "issues": issues, "problems": problems, "warnings": warnings,
            "settings": {"roster": roster.roster_names(), "supervisor_name": sup["name"],
                         "supervisor_linked": bool(sup["did"]),
                         "supervisor_did": db.config_get("supervisor_did", ""),
                         "every_min": engine.CHECK_EVERY_MIN,
                         "window_min": engine.ANSWER_WINDOW_MIN,
                         "channel": notify.channel_name()},
            "availability_tomorrow": roster.availability(today + datetime.timedelta(days=1))}


async def api_state(request):
    now = HOST.now()
    data = await _run(state_payload, now)
    data["can_edit"] = can_edit(request)
    return _json(data)


async def api_slot(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    ok, err = await _run(notify.edit_slot, int(b.get("slot_id") or 0),
                         (b.get("employee") or "").strip(), _actor(request),
                         (b.get("reason") or "").strip())
    return _json({"ok": ok, "error": err})


async def api_switch(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    await _run(notify.set_enabled, bool(b.get("on")), _actor(request), HOST.now())
    return _json({"ok": True, "enabled": bool(b.get("on"))})


def _save_settings(b, by, now):
    if "roster" in b:
        names = [str(n).strip() for n in (b.get("roster") or []) if str(n).strip()]
        if not names:
            return False, "لازم يبقى شخص واحد على الأقل في المناوبة."
        db.config_set("roster", json.dumps(names, ensure_ascii=False), by, db.iso(now))
    if "supervisor_did" in b:
        did = "".join(ch for ch in str(b.get("supervisor_did") or "") if ch.isdigit())
        db.config_set("supervisor_did", did, by, db.iso(now))
    db.log("settings", now, by, {k: b.get(k) for k in ("roster", "supervisor_did") if k in b})
    return True, ""


async def api_settings(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    ok, err = await _run(_save_settings, b, _actor(request), HOST.now())
    return _json({"ok": ok, "error": err})


# ------------------------------------------------------------------ the tab script

def js_version():
    try:
        return str(int(os.path.getmtime(STATIC_JS)))
    except OSError:
        return "0"


def _js_text():
    m = os.path.getmtime(STATIC_JS)
    if _js_cache["mtime"] != m:
        with open(STATIC_JS, encoding="utf-8") as f:
            _js_cache["text"] = f.read()
        _js_cache["mtime"] = m
    return _js_cache["text"]


async def handle_static_js(request):
    text = await _run(_js_text)
    return HOST.web.Response(text=text, content_type="application/javascript",
                             headers={"Cache-Control": "no-cache"})


def register_routes(app):
    g, p = app.router.add_get, app.router.add_post
    g("/oncall/static/oncall_tab.js", handle_static_js)
    g("/api/oncall/state", _safe(api_state))
    p("/api/oncall/slot", _safe(api_slot))
    p("/api/oncall/switch", _safe(api_switch))
    p("/api/oncall/settings", _safe(api_settings))
```

Create `oncall/static/oncall_tab.js`:

```javascript
/* «المناوبة» — the evening on-call tab of the Ouja dashboard.
 *
 * Served by oncall/routes.py at /oncall/static/oncall_tab.js and loaded on first visit by the
 * tiny loadOncall() stub inside DASHBOARD_HTML. A REAL file on purpose: DASHBOARD_HTML is a
 * Python string that eats backslashes (CLAUDE.md trap 1); this file is not.
 *
 * Sections: الحين · الليلة · بكرة · المشاكل · السجل · الإعدادات.
 * Uses the dashboard's globals only: api, post, esc, labelText, toast, putHtml, emptyState,
 * errorState. Every action is event-delegated through data-oc="…". Must pass `node --check`.
 */
(function () {
  'use strict';

  var S = { data: null, loading: false, editing: null };

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
  function hm(s) { return s ? String(s).slice(11, 16) : '—'; }

  var STATUS = { none: ['ما نزل', 'Not published'], published: ['منشور — التبديل مفتوح', 'Published — swaps open'],
                 locked: ['مقفل', 'Locked'] };
  var CHECK = { missed: ['غياب', 'Missed'], late: ['غياب (ضغط متأخر)', 'Missed (late press)'],
                voided: ['ملغي', 'Void'] };
  var VOID = { not_delivered: ['ما وصله السؤال', 'Not delivered'], bot_down: ['البوت كان متوقف', 'Bot was down'],
               unreachable: ['حسابه مو مربوط', 'Not linked'] };

  function css() {
    if (document.getElementById('ocCss')) return;
    var s = document.createElement('style');
    s.id = 'ocCss';
    s.textContent = [
      '.oc-banner{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;justify-content:space-between;padding:11px 14px;border-radius:var(--r-md);border:1px solid var(--line);background:var(--surface);margin-bottom:14px;font-size:12.5px;color:var(--text-2)}',
      '.oc-banner.off{background:var(--red-soft);border-color:transparent;color:var(--red)}',
      '.oc-banner b{color:var(--text)}',
      '.oc-now{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}',
      '.oc-h{font-size:13px;font-weight:700;color:var(--text);margin:0 0 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}',
      '.oc-st{display:inline-flex;align-items:center;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
      '.oc-st.bad{background:var(--red-soft);color:var(--red)}',
      '.oc-st.ok{background:var(--green-soft);color:var(--green)}',
      '.oc-st.gold{background:var(--gold-tint);color:var(--gold)}',
      '.oc-sub{display:block;font-size:11px;color:var(--mut);margin-top:2px}',
      '.oc-num{font-family:var(--font-mono);white-space:nowrap}',
      '.oc-edit{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px}',
      '.oc-edit select,.oc-edit input,.oc-set input{min-height:34px;padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--text);font:inherit;font-size:12.5px}',
      '.oc-edit input{flex:1;min-width:140px}',
      '.oc-set{display:grid;gap:10px;max-width:520px}',
      '.oc-set label{font-size:12px;font-weight:700;color:var(--text)}',
      '.oc-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid var(--line);border-radius:999px;font-size:12px;margin:0 0 6px 6px}',
      '.oc-chip button{border:0;background:none;color:var(--mut);cursor:pointer;font:inherit;padding:0}',
      '.oc-wrap{overflow-x:auto}',
      '.btn:active{transform:scale(.97)}',
      '@media (prefers-reduced-motion:reduce){.btn:active{transform:none}}'
    ].join('');
    document.head.appendChild(s);
  }

  async function load(force) {
    css();
    if (S.loading) return;
    S.loading = true;
    if (force || !S.data) putHtml('ocBody', '<div class="empty sk">…</div>');
    try {
      var d = await api('/api/oncall/state');
      if (!d || d.ok === false) { putHtml('ocBody', errorState('loadOncall(1)', d && d.error)); return; }
      S.data = d;
      render();
    } catch (e) {
      putHtml('ocBody', errorState('loadOncall(1)'));
    } finally {
      S.loading = false;
    }
  }

  function banner(d) {
    var on = !!d.enabled;
    var btn = d.can_edit
      ? '<button class="btn ' + (on ? 'ghost' : 'primary') + ' sm" data-oc="switch" data-on="' + (on ? '0' : '1') + '">' +
        (on ? T('إيقاف النظام كامل', 'Stop everything') : T('تشغيل النظام', 'Turn on')) + '</button>'
      : '';
    var txt = on
      ? T('النظام شغّال — «موجود؟» كل ', 'Running — check every ') + '<b class="oc-num">' + d.settings.every_min +
        '</b>' + T(' دقيقة، و', ' min, ') + '<b class="oc-num">' + d.settings.window_min + '</b>' +
        T(' دقايق للرد. المشرفة: ', ' min to answer. Supervisor: ') + '<b>' + esc(d.settings.supervisor_name) + '</b>' +
        (d.settings.supervisor_linked ? '' : ' <span class="oc-st bad">' + T('حسابها مو مربوط', 'not linked') + '</span>')
      : '<b>' + T('النظام موقّف', 'Stopped') + '</b> — ' + T('ما فيه أسئلة ولا تنبيهات ولا إنذارات.', 'no checks, alerts or warnings.');
    return '<div class="oc-banner' + (on ? '' : ' off') + '"><span>' + txt + '</span>' + btn + '</div>';
  }

  function nowCards(d) {
    var n = d.now;
    if (!d.in_window) {
      return '<div class="oc-now"><div class="kpi"><div class="kpi-val">—</div><div class="kpi-lbl">' +
        T('خارج وقت المناوبة (٥ العصر – ١٢ الليل)', 'Outside on-call hours (5 PM – 12 AM)') + '</div></div></div>';
    }
    if (!n) {
      return '<div class="oc-now"><div class="kpi"><div class="kpi-val">⚠</div><div class="kpi-lbl">' +
        T('ما فيه مناوب الحين — الليلة ما لها جدول', 'Nobody on duty — no schedule tonight') + '</div></div></div>';
    }
    function k(v, l) { return '<div class="kpi"><div class="kpi-val">' + v + '</div><div class="kpi-lbl">' + l + '</div></div>'; }
    return '<div class="oc-now">' +
      k(esc(n.employee), T('المناوب الحين', 'On duty now') + ' · <span class="oc-num">' + esc(n.from) + '–' + esc(n.to) + '</span>') +
      k('<span class="oc-num">' + hm(n.last_answered) + '</span>', T('آخر «موجود»', 'Last check-in')) +
      k('<span class="oc-num">' + esc(n.next_check || '—') + '</span>', T('السؤال الجاي', 'Next check')) +
      k('<span class="oc-num">' + arr(d.issues).filter(function (i) { return !i.resolved_at; }).length + '</span>',
        T('مشاكل مفتوحة', 'Open issues')) +
      '</div>';
  }

  function nightCard(title, nv, d) {
    var st = STATUS[nv.status] || STATUS.none;
    var h = '<div class="card"><div class="oc-h">' + title + ' · ' + esc(nv.label) +
      ' <span class="oc-st ' + (nv.status === 'locked' ? 'gold' : '') + '">' + T(st[0], st[1]) + '</span></div>';
    if (!nv.slots.length) {
      h += emptyState(nv.status === 'none' ? T('الجدول ينزل الساعة ١٢ الظهر قبلها بيوم', 'Published at 12 PM the day before')
                                           : T('ما فيه أحد متاح', 'Nobody available'));
    } else {
      h += '<div class="oc-wrap"><table class="data"><thead><tr><th>' + T('الوقت', 'Time') + '</th><th>' + T('المناوب', 'On duty') +
        '</th><th>' + T('ردود', 'Answered') + '</th><th>' + T('غياب', 'Missed') + '</th><th></th></tr></thead><tbody>';
      nv.slots.forEach(function (s) {
        var src = s.source === 'swap' ? T('تبديل', 'swap') : (s.source === 'edit' ? T('تعديل: ', 'edit: ') + esc(s.edited_by) : '');
        h += '<tr><td class="oc-num">' + esc(s.from) + '–' + esc(s.to) + '</td><td>' + esc(s.employee) +
          (src ? '<span class="oc-sub">' + src + (s.edit_reason ? ' — ' + esc(s.edit_reason) : '') + '</span>' : '') +
          (s.linked ? '' : ' <span class="oc-st bad">' + T('مو مربوط', 'not linked') + '</span>') + '</td>' +
          '<td class="oc-num">' + s.answered + '</td><td class="oc-num">' +
          (s.missed ? '<span class="oc-st bad">' + s.missed + '</span>' : '0') + '</td><td>' +
          (d.can_edit ? '<button class="btn ghost sm" data-oc="edit" data-id="' + s.id + '">' + T('تغيير', 'Change') + '</button>' : '') +
          '</td></tr>';
        if (S.editing === s.id) {
          h += '<tr><td colspan="5"><div class="oc-edit"><select data-oc-f="emp">' +
            arr(d.settings.roster).map(function (r) {
              return '<option' + (r === s.employee ? ' selected' : '') + '>' + esc(r) + '</option>';
            }).join('') + '</select><input data-oc-f="reason" placeholder="' + T('السبب (إلزامي)', 'Reason (required)') + '">' +
            '<button class="btn primary sm" data-oc="save-slot" data-id="' + s.id + '">' + T('حفظ', 'Save') + '</button>' +
            '<button class="btn ghost sm" data-oc="cancel">' + T('إلغاء', 'Cancel') + '</button></div></td></tr>';
        }
      });
      h += '</tbody></table></div>';
    }
    if (nv.unavailable && nv.unavailable.length) {
      h += '<div class="oc-sub" style="margin-top:8px">' + T('مو موجودين: ', 'Not available: ') +
        nv.unavailable.map(function (u) { return esc(u.name) + ' (' + esc(u.why) + ')'; }).join('، ') + '</div>';
    }
    return h + '</div>';
  }

  function issuesCard(d) {
    var rows = arr(d.issues);
    var h = '<div class="card"><div class="oc-h">' + T('المشاكل وأصحابها', 'Issues and owners') + '</div>';
    if (!rows.length) return h + emptyState(T('ما فيه مشاكل للحين', 'No issues yet')) + '</div>';
    h += '<div class="oc-wrap"><table class="data"><thead><tr><th>' + T('المشكلة', 'Issue') + '</th><th>' + T('الصاحب', 'Owner') +
      '</th><th>' + T('فتحت', 'Opened') + '</th><th>' + T('الحالة', 'Status') + '</th></tr></thead><tbody>';
    rows.forEach(function (i) {
      var st = i.resolved_at ? '<span class="oc-st ok">' + T('انحلّت', 'Resolved') + '</span>'
        : (i.claimed_at ? '<span class="oc-st gold">' + T('مستلمة', 'Claimed') + '</span>'
                        : '<span class="oc-st bad">' + T('ما انستلمت', 'Unclaimed') + '</span>');
      h += '<tr><td>' + (i.kind === 'maint' ? '🛠️ ' : '🚨 ') + esc(i.title || '—') + '</td><td>' + esc(i.owner) +
        (i.helper ? '<span class="oc-sub">' + T('ساعده: ', 'Helped by: ') + esc(i.helper) + '</span>' : '') +
        '</td><td class="oc-num">' + esc(String(i.opened_at || '').slice(5, 16).replace('T', ' ')) + '</td><td>' + st + '</td></tr>';
    });
    return h + '</tbody></table></div></div>';
  }

  function logCard(d) {
    var rows = arr(d.problems);
    var h = '<div class="card"><div class="oc-h">' + T('سجل الغياب والإلغاء', 'Misses and voids') + '</div>';
    if (!rows.length) return h + emptyState(T('ما فيه غياب مسجّل', 'No misses recorded')) + '</div>';
    h += '<div class="oc-wrap"><table class="data"><thead><tr><th>' + T('الموظف', 'Employee') + '</th><th>' + T('الوقت', 'When') +
      '</th><th>' + T('النتيجة', 'Result') + '</th></tr></thead><tbody>';
    rows.forEach(function (c) {
      var lbl = CHECK[c.status] || [c.status, c.status];
      var why = VOID[c.void_reason];
      h += '<tr><td>' + esc(c.employee) + '</td><td class="oc-num">' + esc(c.date) + ' ' + hm(c.due_at) + '</td><td>' +
        '<span class="oc-st ' + (c.status === 'voided' ? '' : 'bad') + '">' + T(lbl[0], lbl[1]) + '</span>' +
        (why ? '<span class="oc-sub">' + T(why[0], why[1]) + '</span>' : '') + '</td></tr>';
    });
    h += '</tbody></table></div>';
    if (arr(d.warnings).length) {
      h += '<div class="oc-sub" style="margin-top:8px">' + T('الإنذارات الرسمية والاعتراضات في صفحة ', 'Formal warnings and appeals live on ') +
        '<a href="/compliance" target="_blank" rel="noopener">/compliance</a></div>';
    }
    return h + '</div>';
  }

  function settingsCard(d) {
    if (!d.can_edit) return '';
    var st = d.settings;
    return '<div class="card"><div class="oc-h">' + T('الإعدادات', 'Settings') + '</div><div class="oc-set">' +
      '<label>' + T('فريق المناوبة', 'On-call team') + '</label><div>' +
      arr(st.roster).map(function (r) {
        return '<span class="oc-chip">' + esc(r) + '<button data-oc="rm" data-n="' + esc(r) + '" aria-label="remove">✕</button></span>';
      }).join('') + '</div>' +
      '<div class="oc-edit"><input data-oc-f="add" placeholder="' + T('اسم كما في تقويم الموظفين', 'Name as in the employee calendar') + '">' +
      '<button class="btn ghost sm" data-oc="add">' + T('إضافة', 'Add') + '</button></div>' +
      '<label>' + T('ديسكورد المشرفة (رقم الحساب)', 'Supervisor Discord ID') + '</label>' +
      '<div class="oc-edit"><input data-oc-f="sup" inputmode="numeric" value="' + esc(st.supervisor_did || '') + '" placeholder="' +
      T('فاضي = نفس مسؤول الاعتراضات في /compliance', 'Empty = the /compliance appeal lead') + '">' +
      '<button class="btn ghost sm" data-oc="sup">' + T('حفظ', 'Save') + '</button></div>' +
      '<div class="oc-sub">' + T('روم ديسكورد: #', 'Discord room: #') + esc(st.channel) + '</div></div></div>';
  }

  function render() {
    var d = S.data;
    putHtml('ocBody', banner(d) + nowCards(d) + nightCard(T('الليلة', 'Tonight'), d.tonight, d) +
      nightCard(T('بكرة', 'Tomorrow'), d.tomorrow, d) + issuesCard(d) + logCard(d) + settingsCard(d));
  }

  function field(name) {
    var el = document.querySelector('#view_oncall [data-oc-f="' + name + '"]');
    return el ? el.value : '';
  }

  async function act(path, body, el) {
    if (el) el.setAttribute('aria-busy', 'true');
    try {
      var r = await post(path, body);
      if (!r || r.ok === false) { toast((r && r.error) || T('ما انحفظ', 'Not saved')); return false; }
      return true;
    } finally {
      if (el) el.removeAttribute('aria-busy');
    }
  }

  async function onClick(ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-oc]') : null;
    if (!el) return;
    var view = document.getElementById('view_oncall');
    if (!view || !view.contains(el)) return;
    var a = el.getAttribute('data-oc');
    var d = S.data;
    if (a === 'edit') { S.editing = Number(el.getAttribute('data-id')); render(); }
    else if (a === 'cancel') { S.editing = null; render(); }
    else if (a === 'save-slot') {
      var reason = field('reason').trim();
      if (!reason) { toast(T('اكتب السبب', 'Write a reason')); return; }
      if (await act('/api/oncall/slot', { slot_id: Number(el.getAttribute('data-id')), employee: field('emp'), reason: reason }, el)) {
        S.editing = null; toast(T('تم — وصلهم خبر بديسكورد', 'Saved — both were told on Discord')); load(true);
      }
    } else if (a === 'switch') {
      if (await act('/api/oncall/switch', { on: el.getAttribute('data-on') === '1' }, el)) load(true);
    } else if (a === 'rm' || a === 'add') {
      var names = arr(d.settings.roster).slice();
      if (a === 'rm') names = names.filter(function (n) { return n !== el.getAttribute('data-n'); });
      else { var nn = field('add').trim(); if (!nn) return; if (names.indexOf(nn) < 0) names.push(nn); }
      if (await act('/api/oncall/settings', { roster: names }, el)) load(true);
    } else if (a === 'sup') {
      if (await act('/api/oncall/settings', { supervisor_did: field('sup').trim() }, el)) { toast(T('انحفظ', 'Saved')); load(true); }
    }
  }

  if (!window.__ocBound) {
    window.__ocBound = 1;
    document.addEventListener('click', onClick);
  }

  window.OncallTab = { load: load };
})();
```

Replace `oncall/__init__.py` (final):

```python
# -*- coding: utf-8 -*-
"""
oncall — «المناوبة», the evening on-call rotation (17:00-24:00).

Spec: docs/superpowers/specs/2026-10-03-oncall-rotation-design.md

    engine.py — PURE rules: the fair rotation, check times, miss ladder, ownership, swaps
    db.py     — oncall_* tables inside brain.db (idempotency by UNIQUE, not by care)
    roster.py — who can work tonight (Employee Calendar + ops Discord ids) and the supervisor
    texts.py  — every Arabic word the feature sends
    notify.py — the minute tick + button/hook handlers; the ONLY ops warning call site
    routes.py — /api/oncall/* (login + «oncall» permission; writes re-check admin/ops)
    static/oncall_tab.js — the dashboard tab (a real file: no DASHBOARD_HTML backslash trap)
"""

from . import engine, db, roster, texts, notify, routes  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401
```

- [ ] **Step 4: Run the tests and confirm they pass, and that the JS parses**

Run: `python3 -m unittest tests.test_oncall_routes tests.test_oncall_flow tests.test_oncall_engine && ~/.local/node/bin/node --check oncall/static/oncall_tab.js && echo JS-OK`
Expected: `Ran 58 tests … OK` then `JS-OK`

- [ ] **Step 5: Commit**

```bash
git add oncall/routes.py oncall/static/oncall_tab.js oncall/__init__.py tests/test_oncall_routes.py
git commit -m "feat(oncall): /api/oncall/* endpoints and the «المناوبة» dashboard tab script

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Wire it into bot.py (21 anchored edits)

**Files:**
- Modify: `bot.py` (each edit is anchored on text that appears exactly once; line numbers are approximate on origin/main fd01739)
- Test: `tests/test_oncall_wiring.py`

**Interfaces:**
- Consumes: everything above. Existing bot.py names:
  - `now_riyadh`, `_dash_auth`, `_req_role`, `_req_actor`, `_json`, `web`, `web_thread`
  - `_HAS_BRAIN`, `_state_path`, `GUILD_ID`, `_cw_reply`, `_can_delete_channels`, `OPS_CATEGORY_NAME`
  - `_loop_guard`, `_pending`, `ensure_channel`
  - The escalation flow (`post_assistant_card` → `msg`, `target`, `g`, `item`), `NameSelect.callback`, `_resolve_escalation(mid, esc, reason)`, `_maint_open_ticket` (`ch`, `msg`, `unit_name`, `summary`) and `_tk_close` (`ch`, `rec`, `interaction`).
- Produces:
  - Discord buttons `oc_here`, `oc_swap:<slot_id>`, `oc_swap_yes`, `oc_swap_no`, `oc_resolved`
  - The command `!ouja oncall-setup`
  - `oncall_loop`
  - The tab `oncall` in NAV_DEF, with labels «المناوبة» / «On-call»

- [ ] **Step 1: Write the failing test**

Create `tests/test_oncall_wiring.py`:

```python
# -*- coding: utf-8 -*-
"""
«المناوبة» wiring inside bot.py — read as TEXT (importing bot.py boots a Discord bot).

Each assertion is a past outage class in this repo: a tab id without a label renders
«undefined»; an /api/ prefix missing from the role rules is either open to everyone or a
401 for everyone; a listener never registered is a button that "does nothing".

Run: python3 -m unittest tests.test_oncall_wiring
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src():
    with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
        return f.read()


class Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = src()

    def test_import_is_optional(self):
        self.assertIn("import oncall as _oncall", self.s)
        self.assertIn("_HAS_ONCALL = False", self.s)

    def test_role_rules_read_and_write(self):
        self.assertEqual(self.s.count('("/api/oncall/", "oncall")'), 2)

    def test_nav_item_and_both_labels(self):
        self.assertIn('{"id": "oncall", "ic": "calendar", "tk": "oncall"}', self.s)
        self.assertIn('"rvpush", "oncall", "listings"', self.s)
        self.assertIn('"oncall": "المناوبة"', self.s)
        self.assertIn('"oncall": "On-call"', self.s)

    def test_dashboard_view_loader_and_version(self):
        self.assertIn('id="view_oncall"', self.s)
        self.assertIn("if(id==='oncall') loadOncall();", self.s)
        self.assertIn("function loadOncall(force){", self.s)
        self.assertIn('"__ONCALL_JS_V__", (_oncall.routes.js_version()', self.s)

    def test_no_backslash_in_the_dashboard_additions(self):
        i = self.s.index('<section class="view" id="view_oncall">')
        j = self.s.index("</section>", i)
        self.assertNotIn(chr(92), self.s[i:j])
        k = self.s.index("function loadOncall(force){")
        m = self.s.index("document.head.appendChild(s);", k)
        self.assertNotIn(chr(92), self.s[k:m])

    def test_listeners_loop_and_routes(self):
        self.assertIn('bot.add_listener(_oc_interaction, "on_interaction")', self.s)
        self.assertIn('bot.add_listener(_oc_on_message, "on_message")', self.s)
        self.assertIn("_pending.append(oncall_loop)", self.s)
        self.assertIn('_loop_guard(oncall_loop, "oncall_loop")', self.s)
        self.assertIn("_oncall.register_routes(app)", self.s)

    def test_all_four_issue_hooks(self):
        self.assertIn('_oncall.notify.on_issue_opened, "escalation"', self.s)
        self.assertIn('_oncall.notify.on_issue_opened, "maint"', self.s)
        self.assertIn("_oncall.notify.on_escalation_claimed", self.s)
        self.assertEqual(len(re.findall(r"_oncall\.notify\.on_issue_resolved", self.s)), 2)

    def test_thread_safe_delivery(self):
        i = self.s.index("def _oc_send(payload):")
        self.assertIn("run_coroutine_threadsafe", self.s[i:i + 900])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python3 -m unittest tests.test_oncall_wiring`
Expected: `FAILED (failures=6, errors=2)`

- [ ] **Step 3: Apply the edits**

Use the Edit tool for each one. Every anchor below appears **exactly once** in bot.py. Re-read the anchor region before each edit (CLAUDE.md trap 5).

**Edit 1 — import.** Find this anchor:

```python
    _reviewask = None
    _HAS_REVIEWASK = False
```

and insert IMMEDIATELY AFTER it:

```python

# «المناوبة» evening on-call rotation — 17:00-24:00 slots, «موجود؟» every 15 minutes, issue
# ownership. Spec: docs/superpowers/specs/2026-10-03-oncall-rotation-design.md. Additive.
try:
    import oncall as _oncall
    _HAS_ONCALL = True
except Exception as _oc_err:            # pragma: no cover
    print("[oncall] import failed (on-call disabled, bot unaffected):", _oc_err)
    _oncall = None
    _HAS_ONCALL = False
```

**Edit 2 — block before RvTemplateModal.** Find this anchor:

```python
class RvTemplateModal(discord.ui.Modal, title="نص رسالة التقييم"):
```

and insert IMMEDIATELY BEFORE it:

```python
# ======================= «المناوبة» evening on-call (oncall/ package) =======================
# Discord side only: the package decides, this block delivers. Buttons are handled by ONE
# listener with static custom_ids (the row is found by message id / slot id), so a press still
# works on a message posted before the last redeploy.

ONCALL_HERE_ID = "oc_here"
ONCALL_SWAP_PREFIX = "oc_swap:"
ONCALL_SWAP_YES, ONCALL_SWAP_NO = "oc_swap_yes", "oc_swap_no"
ONCALL_RESOLVED_ID = "oc_resolved"


def _oc_wire():
    if not _HAS_ONCALL:
        return False
    _oncall.wire({"now": now_riyadh, "send": _oc_send,
                  "dash_auth": _dash_auth, "req_role": _req_role, "actor": _req_actor,
                  "json_response": _json, "web": web, "web_thread": web_thread})
    return True


def _oc_ready():
    """Usable the moment Discord is — BEFORE start_web_server runs. Hand brain.db its folder,
    then wire. Same boot-window fix as _cw_ready (the 2026-09-26 «before brain.wire()» trap)."""
    if not _HAS_ONCALL:
        return False
    if _HAS_BRAIN:
        try:
            from brain.host import HOST as _brain_host
            if _brain_host.state_path is None:
                _brain_host.state_path = _state_path
        except Exception as e:
            print("[oncall] brain path hand-over failed:", e)
    if _oncall.HOST.send is None:
        _oc_wire()
    return True


class OcHereView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="✋ موجود", style=discord.ButtonStyle.success,
                                        custom_id=ONCALL_HERE_ID))


class OcSwapAskView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="✅ موافق", style=discord.ButtonStyle.success,
                                        custom_id=ONCALL_SWAP_YES))
        self.add_item(discord.ui.Button(label="❌ لا", style=discord.ButtonStyle.danger,
                                        custom_id=ONCALL_SWAP_NO))


class OcScheduleView(discord.ui.View):
    """One «🔁» button per slot; the custom_id carries the slot id. Disabled once locked."""

    def __init__(self, slots):
        super().__init__(timeout=None)
        for s in (slots or [])[:25]:
            self.add_item(discord.ui.Button(label=("🔁 " + s["label"])[:80],
                                            style=discord.ButtonStyle.secondary,
                                            custom_id=ONCALL_SWAP_PREFIX + str(s["id"]),
                                            disabled=bool(s.get("locked"))))


class OcResolveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="✅ انحلّت", style=discord.ButtonStyle.success,
                                        custom_id=ONCALL_RESOLVED_ID))


def _oc_view(payload, where):
    v = payload.get("view") or ""
    if v == "here":
        return OcHereView()
    if v == "swap_ask" and where == "dm":
        return OcSwapAskView()
    if v == "schedule" and where == "channel":
        return OcScheduleView(payload.get("slots"))
    return None


def _oc_send(payload):
    """HOST.send — called from the minute tick's WORKER THREAD and from request handlers.
    run_coroutine_threadsafe is the only correct call from a thread (the _ops_notify lesson:
    create_task there silently drops every message)."""
    if not _HAS_ONCALL:
        return
    coro = _oc_deliver(payload)
    try:
        loop = getattr(bot, "loop", None)
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
            return
    except Exception as e:
        print("[oncall] cross-thread delivery failed:", e)
    try:
        asyncio.create_task(coro)
    except RuntimeError:
        print("[oncall] no event loop — message NOT delivered:", payload.get("kind"))


def _oc_channel(guild):
    if guild is None:
        return None
    return discord.utils.get(guild.text_channels, name=_oncall.notify.channel_name())


async def _oc_deliver(payload):
    """One payload -> DMs, the «المناوبة» room (post or edit), the private HR room. Reports
    what actually landed back to the package — that report is how a check knows it was
    delivered, and an undelivered check can never become a miss."""
    guild = bot.get_guild(GUILD_ID)
    dm_ok, dm_mid, ch_ok, ch_mid = False, "", False, ""
    try:
        for i, d in enumerate(payload.get("dm") or []):
            did = str(d.get("did") or "").strip()
            if not did.isdigit() or not d.get("text"):
                continue
            try:
                user = bot.get_user(int(did)) or await bot.fetch_user(int(did))
                view = _oc_view(payload, "dm") if i == 0 else None
                m = await user.send(d["text"], **({"view": view} if view else {}))
                if i == 0:
                    dm_ok, dm_mid = True, str(m.id)
            except Exception as e:
                print("[oncall] dm failed (%s): %s" % (did, e))
        text = payload.get("channel_text") or ""
        ch = _oc_channel(guild) if text else None
        if text and ch is None:
            print("[oncall] channel #%s missing — run !ouja oncall-setup"
                  % _oncall.notify.channel_name())
        if ch is not None:
            view = _oc_view(payload, "channel")
            if payload.get("edit_message_id"):
                try:
                    m = await ch.fetch_message(int(payload["edit_message_id"]))
                    await m.edit(content=text, view=view)
                    ch_ok, ch_mid = True, str(m.id)
                except Exception as e:
                    print("[oncall] schedule edit failed:", e)
            else:
                m = await ch.send(text, **({"view": view} if view else {}),
                                  allowed_mentions=discord.AllowedMentions(users=True))
                ch_ok, ch_mid = True, str(m.id)
        if payload.get("hr_channel") and payload.get("hr_text") and guild is not None:
            hr = discord.utils.get(guild.text_channels, name=payload["hr_channel"])
            if hr is not None:
                await hr.send(payload["hr_text"])
            else:
                print("[oncall] HR channel missing:", payload["hr_channel"])
    except Exception as e:
        print("[oncall] deliver failed:", e)
    if payload.get("report"):
        try:
            await asyncio.to_thread(_oncall.notify.delivered, payload["report"],
                                    dm_ok, dm_mid, ch_ok, ch_mid)
        except Exception as e:
            print("[oncall] delivery report failed:", e)


async def _oc_post_note(channel, card_msg, kind, ref, note):
    """The «🌙 المناوب المسؤول» line under an escalation card / inside a maintenance room.
    Escalations carry «✅ انحلّت»; a ticket's ownership ends when the room is closed."""
    try:
        kw = {"allowed_mentions": discord.AllowedMentions(users=True)}
        if kind == "escalation":
            kw["view"] = OcResolveView()
            kw["reference"] = discord.MessageReference(message_id=card_msg.id,
                                                       channel_id=channel.id,
                                                       fail_if_not_exists=False)
        m = await channel.send(note["text"], **kw)
        await asyncio.to_thread(_oncall.notify.delivered, {"what": "issue_note", "id": ref},
                                False, "", True, str(m.id))
    except Exception as e:
        print("[oncall] note post failed:", e)


async def _oc_finish(interaction, text):
    """Replace the pressed message's buttons with the outcome; fall back to a private reply."""
    try:
        body = (interaction.message.content or "") + chr(10) + text
        await interaction.response.edit_message(content=body[:2000], view=None)
    except Exception:
        await _cw_reply(interaction, text)


async def _oc_interaction(interaction):
    """«المناوبة» buttons. A LISTENER, not a bound view."""
    try:
        if not _HAS_ONCALL or interaction.type != discord.InteractionType.component:
            return
        cid = (interaction.data or {}).get("custom_id") or ""
        if not (cid in (ONCALL_HERE_ID, ONCALL_SWAP_YES, ONCALL_SWAP_NO, ONCALL_RESOLVED_ID)
                or cid.startswith(ONCALL_SWAP_PREFIX)):
            return
        _oc_ready()
        n = _oncall.notify
        mid = str(getattr(interaction.message, "id", "") or "")
        uid = str(interaction.user.id)
        if cid == ONCALL_HERE_ID:
            code, text = await asyncio.to_thread(n.answer_check, mid, uid)
            if code in ("answered", "already"):
                await _oc_finish(interaction, "✅ " + text)
            else:
                await _cw_reply(interaction, text)
        elif cid.startswith(ONCALL_SWAP_PREFIX):
            _ok, text = await asyncio.to_thread(n.request_swap,
                                                int(cid[len(ONCALL_SWAP_PREFIX):]), uid)
            await _cw_reply(interaction, text)
        elif cid in (ONCALL_SWAP_YES, ONCALL_SWAP_NO):
            ok, text = await asyncio.to_thread(n.answer_swap, mid, uid, cid == ONCALL_SWAP_YES)
            if ok:
                await _oc_finish(interaction, text)
            else:
                await _cw_reply(interaction, text)
        else:
            ok, text = await asyncio.to_thread(n.resolve_press, mid, uid,
                                               _can_delete_channels(interaction.user))
            if ok:
                await _oc_finish(interaction, "✅ " + text)
            else:
                await _cw_reply(interaction, text)
    except Exception as e:
        print("[oncall] button error:", e)
        try:
            await _cw_reply(interaction, "صار خطأ — جرب مرة ثانية.")
        except Exception:
            pass


async def _oc_on_message(message):
    """A message from the on-call owner inside a maintenance room counts as an update."""
    try:
        if not _HAS_ONCALL or message.author.bot or message.guild is None:
            return
        if "ouja-ticket:maint" not in (getattr(message.channel, "topic", "") or ""):
            return
        _oc_ready()
        await asyncio.to_thread(_oncall.notify.on_ticket_message, str(message.channel.id),
                                str(message.author.id))
    except Exception as e:
        print("[oncall] ticket message hook failed:", e)


@tasks.loop(minutes=1)
async def oncall_loop():
    """«المناوبة» — one tick a minute: publish 12:00, lock 15:00, «موجود؟» every 15 minutes
    17:00-24:00, the miss ladder, issue watch, handover, the night summary. Idempotent by
    database facts (oncall/db.py), so a restart mid-tick can never ping twice."""
    if not _HAS_ONCALL:
        return
    await bot.wait_until_ready()
    try:
        _oc_ready()
        rep = await asyncio.to_thread(_oncall.notify.tick)
        if any(rep.get(k) for k in ("published", "locked", "checks", "judged", "issues",
                                    "summary")):
            print("[oncall] tick:", rep)
    except Exception as e:
        print("[oncall] loop error:", e)
```

**Edit 3 — command before ops-channels command.** Find this anchor:

```python
@bot.command(name="ops-channels", aliases=["رومات-الالتزام", "غرف-الالتزام"])
```

and insert IMMEDIATELY BEFORE it:

```python
@bot.command(name="oncall-setup", aliases=["روم-المناوبة"])
async def cmd_oncall_setup(ctx):
    """!ouja oncall-setup — create the private «المناوبة» room: the on-call team, the
    supervisor and the admins. An owner decision, never automatic. Re-running is safe — an
    existing room is left exactly as it is."""
    if not _can_delete_channels(ctx.author):
        await ctx.reply("🚫 هذا الأمر للإدارة فقط.")
        return
    if not _HAS_ONCALL:
        await ctx.reply("🚫 نظام المناوبة مو مفعّل.")
        return
    _oc_ready()
    guild = ctx.guild
    name = _oncall.notify.channel_name()
    existing = discord.utils.get(guild.text_channels, name=name)
    if existing is not None:
        await ctx.reply("✅ الروم موجودة من قبل: %s" % existing.mention)
        return
    me = guild.me
    if not me.guild_permissions.manage_channels or not (
            me.guild_permissions.manage_roles or me.guild_permissions.administrator):
        await ctx.reply("🚫 البوت ناقصه صلاحية «إدارة الرومات» أو «إدارة الأدوار» — ما انفتحت "
                        "الروم، عشان ما تطلع روم المناوبة للكل.")
        return
    dids = []
    for nm in await asyncio.to_thread(_oncall.roster.roster_names):
        did = await asyncio.to_thread(_oncall.roster.did_for, nm)
        if did:
            dids.append(did)
    sup = await asyncio.to_thread(_oncall.roster.supervisor)
    if sup.get("did"):
        dids.append(sup["did"])
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                  me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                  embed_links=True, read_message_history=True)}
    missing = []
    for did in dict.fromkeys(dids):
        try:
            m = guild.get_member(int(did)) or await guild.fetch_member(int(did))
            overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                        read_message_history=True)
        except Exception:
            missing.append(did)
    cat = next((c for c in guild.categories if c.name == OPS_CATEGORY_NAME), None)
    ch = await guild.create_text_channel(name, category=cat, overwrites=overwrites,
                                         topic="ouja-oncall — جدول المناوبة المسائية و«موجود؟»")
    tail = (chr(10) + "⚠️ ما قدرت أضيف: " + "، ".join(missing)) if missing else ""
    await ctx.reply("✅ انفتحت %s — جدول بكرة ينزل فيها الساعة ١٢ الظهر.%s" % (ch.mention, tail))
```

**Edit 4 — escalation hook.** Find this anchor:

```python
            # Open a linked maintenance ticket so the issue lives in the
            # dashboard's ticket log too
```

and insert IMMEDIATELY BEFORE it:

```python
            # «المناوبة»: whoever is on duty now owns this escalation, even after their slot.
            if _HAS_ONCALL:
                try:
                    _oc_ready()
                    _oc_note = await asyncio.to_thread(
                        _oncall.notify.on_issue_opened, "escalation", str(msg.id),
                        f"{g} · {item['unit']}")
                    if _oc_note:
                        await _oc_post_note(target, msg, "escalation", str(msg.id), _oc_note)
                except Exception as _oce2:
                    print("[oncall] escalation hook skipped:", _oce2)
```

**Edit 5 — claim hook.** Find this anchor:

```python
                    _ops.capture.on_escalation_taken(self.target_message_id, name)
            except Exception as _oct:
                print("[ops.capture] escalation take skipped:", _oct)
```

and insert IMMEDIATELY AFTER it:

```python
            if _HAS_ONCALL:
                try:
                    await asyncio.to_thread(_oncall.notify.on_escalation_claimed,
                                            str(self.target_message_id), name)
                except Exception as _occ:
                    print("[oncall] claim hook skipped:", _occ)
```

**Edit 6 — auto-resolve hook.** Find this anchor:

```python
    _escalations.pop(mid, None)
    metric_bump("escalations_resolved")
```

and insert IMMEDIATELY AFTER it:

```python
    if _HAS_ONCALL:
        try:
            await asyncio.to_thread(_oncall.notify.on_issue_resolved, str(mid),
                                    "تلقائي — " + reason)
        except Exception as _ocr:
            print("[oncall] resolve hook skipped:", _ocr)
```

**Edit 7 — maint ticket open hook.** Find this anchor:

```python
    msg = await ch.send(content=content, embeds=embeds, view=MaintTicketView(),
                        allowed_mentions=discord.AllowedMentions(users=True, roles=True))
    rec["card_msg_id"] = msg.id
    _dtk_save()
    try:
        await msg.pin()
    except Exception:
        pass
```

and insert IMMEDIATELY AFTER it:

```python
    if _HAS_ONCALL:
        try:
            _oc_ready()
            _oc_note = await asyncio.to_thread(_oncall.notify.on_issue_opened, "maint",
                                               str(ch.id), f"{unit_name} — {summary[:60]}")
            if _oc_note:
                await _oc_post_note(ch, msg, "maint", str(ch.id), _oc_note)
        except Exception as _ocm:
            print("[oncall] ticket hook skipped:", _ocm)
```

**Edit 8 — ticket close hook.** Find this anchor:

```python
        rec["closed_at"] = now.isoformat(timespec="seconds")
        _dtk_save()
```

and insert IMMEDIATELY AFTER it:

```python
        if rec.get("kind") == "maint" and _HAS_ONCALL:
            try:
                await asyncio.to_thread(_oncall.notify.on_issue_resolved, str(ch.id),
                                        str(interaction.user))
            except Exception as _ock:
                print("[oncall] close hook skipped:", _ock)
```

**Edit 9 — listeners on_ready.** Find this anchor:

```python
    if _HAS_REVIEWASK and not getattr(bot, "_rv_listener", False):
        # «رفع التقييم» buttons: one listener, static custom_ids, row found by message id
        bot.add_listener(_rv_interaction, "on_interaction")
        bot._rv_listener = True
```

and insert IMMEDIATELY AFTER it:

```python
    if _HAS_ONCALL and not getattr(bot, "_oc_listener", False):
        # «المناوبة» buttons + the maintenance-room update hook: listeners, static custom_ids
        bot.add_listener(_oc_interaction, "on_interaction")
        bot.add_listener(_oc_on_message, "on_message")
        bot._oc_listener = True
```

**Edit 10 — loop.** Find this anchor:

```python
    if _HAS_OPS and _ops.turnover.enabled() and not ops_turnover_loop.is_running():
        _pending.append(ops_turnover_loop)      # «القفل»: private turnover nudges (dry-run by default)
```

and insert IMMEDIATELY AFTER it:

```python
    if _HAS_ONCALL and not oncall_loop.is_running():
        if not getattr(oncall_loop, "_error_guarded", False):
            _loop_guard(oncall_loop, "oncall_loop")
            oncall_loop._error_guarded = True
        _pending.append(oncall_loop)            # «المناوبة»: publish/lock/«موجود؟»/ladder, every minute
```

**Edit 11 — web wiring.** Find this anchor:

```python
        # ---- Ops Watchdog «الرقيب التشغيلي» — additive; reuses brain.db + existing auth ----
```

and insert IMMEDIATELY BEFORE it:

```python
        # ---- «المناوبة» evening on-call — additive; reuses brain.db + ops warnings ----
        if _HAS_ONCALL:
            try:
                _oc_wire()
                _oncall.register_routes(app)
                print("[oncall] wired + routes registered (/api/oncall/*) — enabled=%s"
                      % _oncall.notify.enabled())
            except Exception as _oce:
                print("[oncall] wiring failed (on-call disabled, bot unaffected):", _oce)
```

**Edit 12 — role rules.** Find this anchor:

```python
    ("/api/reviewask/", "rvpush"),           # «رفع التقييم» — pins + template editor re-check admin inside
```

and insert IMMEDIATELY AFTER it:

```python
    ("/api/oncall/", "oncall"),              # «المناوبة» — writes re-check admin/ops inside
```

**Edit 13 — role rules.** Find this anchor:

```python
    # /rv/<token> (outside /api/) and the tab script /reviewask/static/ — neither matches here.
    ("/api/reviewask/", "rvpush"),
```

and insert IMMEDIATELY AFTER it:

```python
    # «المناوبة»: who missed a check-in, warnings. The tab script is /oncall/static/ (outside /api/).
    ("/api/oncall/", "oncall"),
```

**Edit 14 — NAV_DEF.** Replace this text (it appears once):

```python
"cleanteams", "coverage", "wifi", "permits", "rvpush", "listings", "quality", "onb", "mot", "pmo", "design"]},
```

with:

```python
"cleanteams", "coverage", "wifi", "permits", "rvpush", "oncall", "listings", "quality", "onb", "mot", "pmo", "design"]},
```

**Edit 15 — NAV_DEF.** Find this anchor:

```python
        {"id": "rvpush", "ic": "reviews", "tk": "rvpush"},                          # «رفع التقييم»
```

and insert IMMEDIATELY AFTER it:

```python
        {"id": "oncall", "ic": "calendar", "tk": "oncall"},                         # «المناوبة»
```

**Edit 16 — NAV_DEF.** Find this anchor:

```python
"listings": "الشقق", "tickets": "الصيانة", "schedule": "تقويم الموظفين",
```

and insert IMMEDIATELY AFTER it:

```python
 "oncall": "المناوبة",
```

**Edit 17 — NAV_DEF.** Find this anchor:

```python
"listings": "Listings", "tickets": "Maintenance", "schedule": "Team Calendar",
```

and insert IMMEDIATELY AFTER it:

```python
 "oncall": "On-call",
```

**Edit 18 — DASHBOARD_HTML section + loader + showView + version.** Find this anchor:

```python
      <!-- ============ KB — قاعدة المعرفة (who owns what · who pays the cleaning · when the owner is paid) ============ -->
```

and insert IMMEDIATELY BEFORE it:

```python
      <!-- ============ «المناوبة» evening on-call (5 PM – 12 AM rotation · «موجود؟» · issue owners) ============ -->
      <section class="view" id="view_oncall">
        <div class="page-head">
          <div>
            <div class="page-title">🌙 المناوبة</div>
            <div class="page-sub">٥ العصر – ١٢ الليل · «موجود؟» كل ربع ساعة · كل مشكلة لها صاحب</div>
          </div>
          <div class="page-tools">
            <button class="btn ghost sm" onclick="loadOncall(1)">↻ تحديث</button>
          </div>
        </div>
        <div id="ocBody"><div class="empty sk">—</div></div>
      </section>
```

**Edit 19 — DASHBOARD_HTML section + loader + showView + version.** Find this anchor:

```python
  if(id==='rvpush') loadRvpush();
```

and insert IMMEDIATELY AFTER it:

```python
  if(id==='oncall') loadOncall();
```

**Edit 20 — DASHBOARD_HTML section + loader + showView + version.** Find this anchor:

```python
/* PERMITS «التصاريح» — the tab's code is the real file /permits/static/permits_tab.js (no backslash trap here) */
```

and insert IMMEDIATELY BEFORE it:

```python
/* «المناوبة» — the tab's code is the real file /oncall/static/oncall_tab.js (no backslash trap here) */
function loadOncall(force){
  if(window.__ocJs){ return window.OncallTab.load(force); }
  if(window.__ocLoading){ return; }
  window.__ocLoading=1;
  var s=document.createElement('script');
  s.src='/oncall/static/oncall_tab.js?v=__ONCALL_JS_V__';
  s.onload=function(){ window.__ocJs=1; window.OncallTab.load(force); };
  s.onerror=function(){ window.__ocLoading=0; putHtml('ocBody', errorState('loadOncall(1)')); };
  document.head.appendChild(s);
}
```

**Edit 21 — DASHBOARD_HTML section + loader + showView + version.** Find this anchor:

```python
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "__REVIEWASK_JS_V__", (_reviewask.routes.js_version() if _reviewask is not None else "0"), 1)
```

and insert IMMEDIATELY AFTER it:

```python
# «المناوبة»: same pattern — the tab script lives in oncall/static/, ?v= is its mtime.
DASHBOARD_HTML = DASHBOARD_HTML.replace(
    "__ONCALL_JS_V__", (_oncall.routes.js_version() if _oncall is not None else "0"), 1)
```


- [ ] **Step 4: Run the wiring test and the bot.py gates**

Run:
```bash
python3 -m unittest tests.test_oncall_wiring
rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py && echo COMPILE-OK
git show HEAD:bot.py > "$TMPDIR/oc_base_bot.py"
python3 -m pyflakes "$TMPDIR/oc_base_bot.py" 2>&1 | grep -v "imported but unused" | sed 's/^[^:]*:[0-9]*:[0-9]*:* //' | sort > "$TMPDIR/oc_base.txt"
python3 -m pyflakes bot.py 2>&1 | grep -v "imported but unused" | sed 's/^[^:]*:[0-9]*:[0-9]*:* //' | sort > "$TMPDIR/oc_new.txt"
diff "$TMPDIR/oc_base.txt" "$TMPDIR/oc_new.txt" && echo NO-NEW-PYFLAKES
python3 -c "
import re, bot, esprima
h = bot.DASHBOARD_HTML
assert '__ONCALL_JS_V__' not in h and '\"oncall\"' in bot._NAV_DEF_JSON
for js in re.findall(r'<script>(.*?)</script>', h, re.S): esprima.parseScript(js)
print('ESPRIMA-OK', bot._HAS_ONCALL)
"
```
Expected:
- `Ran 8 tests … OK`
- `COMPILE-OK`
- `NO-NEW-PYFLAKES`
- `ESPRIMA-OK True`

The import prints boot warnings such as `assignments.json` and `/data` read-only. Those are normal locally.

- [ ] **Step 5: Commit**

```bash
git add bot.py tests/test_oncall_wiring.py
git commit -m "feat(oncall): wire «المناوبة» into the bot — delivery, buttons, loop, hooks, tab

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Full verification and evidence for the owner (no push)

**Files:**
- No source changes, unless a check fails. A failure goes back to the owning task.
- Create: `outputs/oncall/` screenshots (git-ignored scratch; the `outputs/` folder is already untracked in the repo)

- [ ] **Step 1: The CLAUDE.md verification routine**

Run from `/Users/faisalouja/ouja-wt-oncall`:
```bash
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py finance/*.py oncall/*.py | grep -v "imported but unused"
~/.local/node/bin/node --check finance/static/erp.js
~/.local/node/bin/node --check oncall/static/oncall_tab.js
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | tail -5; echo "exit=${PIPESTATUS[0]}"
```
Expected: compile clean, and no pyflakes lines for `oncall/`.

The full suite may contain failures that **already exist on main** (memory: date-dependent tests expire). Prove that none of the failures are new:
```bash
git worktree add -q ../ouja-wt-mainref origin/main
(cd ../ouja-wt-mainref && python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(FAIL|ERROR):" | sort) > "$TMPDIR/oc_main_fail.txt"
python3 -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^(FAIL|ERROR):" | sort > "$TMPDIR/oc_branch_fail.txt"
comm -13 "$TMPDIR/oc_main_fail.txt" "$TMPDIR/oc_branch_fail.txt"
git worktree remove ../ouja-wt-mainref
```
Expected: `comm -13` prints nothing, meaning no failure exists on this branch that main doesn't also have.

- [ ] **Step 2: Boot the real web server locally and load the tab**

Follow the Playwright harness from memory (`playwright-dashboard-login-harness`): boot `python3 bot.py` with a throwaway `STATE_DIR` and `DASHBOARD_TOKEN=test`, and no `DISCORD_TOKEN` (the web server still starts). Then:
- `GET /oncall/static/oncall_tab.js` → 200, `application/javascript`
- `GET /api/oncall/state` with `X-Token: test` → `{"ok": true, "enabled": true, …}`
- Open `/dashboard`, click «المناوبة» in the operations section, and screenshot it at desktop and 375 px width into `outputs/oncall/`.
- Seed a published night by calling `oncall.notify.tick` at a fake 12:00 against the throwaway DB, reload, and screenshot again.

Expected: the tab shows the banner, «الحين», «الليلة», «بكرة», «المشاكل وأصحابها», «سجل الغياب والإلغاء» and «الإعدادات», with no `undefined` and no console errors.

- [ ] **Step 3: Render the Discord messages for the owner**

Run, and save the output to `outputs/oncall/messages.txt`:
```bash
python3 -c "
import datetime
from oncall import texts, engine
d = datetime.date(2026, 10, 4)
slots = [dict(s, employee_did='') for s in engine.build_night(d, ['نورة','ناصر','محمد اليامي','عهود'], [])]
print(texts.schedule_text(d, slots, [{'name':'مآثر','why':'يوم إجازته الأسبوعية'}], False)); print('---')
print(texts.check_text('7:15')); print('---'); print(texts.miss_dm(1)); print('---')
print(texts.supervisor_miss('نورة', 1, slots[0])); print('---')
print(texts.warning_dm('الأحد 04/10', '٩٠٪', 'https://…/appeal/xxxx')); print('---')
print(texts.handover(slots[0], slots[1], [])); print('---')
print(texts.issue_note('escalation', '', 'نورة'))
"
```

- [ ] **Step 4: Report to the owner and STOP**

Send the screenshots and `messages.txt` with SendUserFile. In plain Arabic, report:
- what was built;
- the files and line counts touched (`git diff --stat origin/main...feat/oncall`);
- how to undo it in one step: revert the branch, or switch the system off with «إيقاف النظام كامل» in the tab;
- what the owner must do after a push:
  1. type `!ouja oncall-setup` once to create the room;
  2. tick «المناوبة» for اسيل in الصلاحيات;
  3. type اسيل's Discord ID in the tab, unless the /compliance appeal lead is already her;
  4. check that عهود has a Discord ID linked.

**Do not push.** Ask for the push in its own message. Pushing deploys immediately, and the first live night is the day after the first 12:00 publish.

- [ ] **Step 5: Save memory**

Write `oncall-rotation.md` in the memory dir, with a pointer line in `MEMORY.md`. Record:
- the branch and status;
- the boot-window `_oc_ready` fix;
- that missed checks feed ops warnings (kind `oc`) and cut commission;
- the inverted half-day rule;
- that a check is only a miss if delivered and the bot was up.
