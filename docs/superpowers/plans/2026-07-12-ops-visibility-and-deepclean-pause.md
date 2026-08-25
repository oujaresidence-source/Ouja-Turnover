# Deep-Clean Pause + On-Demand Ops Commands — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pause the deep-clean calendar-blocker and free the dates it blocked (only those), and add two on-demand Discord commands — `/update` (today's check-ins: cleaned / code sent / agreement signed) and `/guests` (in-house guest mood via Claude, with issue + solved/not).

**Architecture:** Three additive slices in the live `bot.py`. Each has a **pure, TDD-locked core** (an eligibility predicate + two message renderers) plus thin wiring (Hostaway/Discord/Claude) that mirrors existing patterns (the watchdog, the deep-clean scheduler, the `!ouja` command family). No existing behavior is rewritten; the deep-clean pause is a reversible layer on top of the existing `DEEPCLEAN_ENABLED` switch.

**Tech Stack:** Python 3, discord.py, aiohttp, Hostaway REST (`api_get`/`api_put`), Anthropic Messages API (`claude_json`, Haiku), SQLite promises ledger (`_pk.db`), `unittest`.

**Key facts the executor must know (verified against the code):**
- `DASHBOARD_HTML` / `schedule/page.py` / `finance/static/erp.js` have a backslash trap. **None of this plan edits those files** — all new code is plain Python at module scope in `bot.py`, where normal `"\n"` is fine.
- Deep-clean blocks are uniquely `isAvailable==0` + no `reservationId` + `note=="deep-clean"` (`bot.py:2286`).
- Tests import the whole bot via `import bot` after setting `STATE_DIR` to a temp dir (see any existing `tests/test_*` that imports bot). `import bot` does **not** require live tokens.
- Guards/handles that already exist: `_HAS_WATCHDOG`/`_watchdog.engine.classify_code_send`, `_HAS_PK`/`_pk.db.open_rows()`, `get_category`/`ensure_channel`, `WATCHDOG_CHANNEL`, `GUILD_ID`, `_can_delete_channels(user)`, `compute_arrivals_with_status`, `_unit_requires_agreement`, `_wd_cleaning_ok`, `fetch_inhouse`, `_res_realized`, `_msg_is_inbound`, `_msg_sort_key`, `claude_json`, `get_listings_map`, `now_riyadh`/`TZ`, `_save_json`/`_load_json`, `persist_state`, `_dash_auth`, `_json`.

**Verification routine (run at the end of every task that changes `bot.py`, and fully in Task 8):**
```
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py finance/*.py
node --check finance/static/erp.js
python3 -m unittest discover -s tests -p "test_*.py"
```

---

### Task 1: Deep-clean block-eligibility predicate (pure, TDD)

The one load-bearing safety check: given a Hostaway calendar-day dict, is it a block THIS feature created (and therefore safe to unblock)?

**Files:**
- Create: `tests/test_deepclean_unblock.py`
- Modify: `bot.py` (add `_deep_clean_block_eligible` right after `_dc_calendar_day_free`, ~`bot.py:2094`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_deepclean_unblock.py`:
```python
# -*- coding: utf-8 -*-
"""Deep-clean unblock safety: _deep_clean_block_eligible must return True ONLY for
our own 'deep-clean' calendar blocks — never a guest booking or a manual hold."""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-deepclean"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ.setdefault("STATE_DIR", _STATE)

import bot  # noqa: E402


class TestBlockEligible(unittest.TestCase):
    def test_true_for_deep_clean_block(self):
        self.assertTrue(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": None, "note": "deep-clean"}))

    def test_false_for_guest_reservation(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": 12345, "note": "deep-clean"}))

    def test_false_for_manual_block_other_note(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": None, "note": "owner hold"}))

    def test_false_for_available_day(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": 1, "reservationId": None, "note": "deep-clean"}))

    def test_false_for_empty_note(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": None, "note": ""}))

    def test_handles_string_isavailable_and_empty_resid(self):
        self.assertTrue(bot._deep_clean_block_eligible(
            {"isAvailable": "0", "reservationId": "", "note": "deep-clean"}))

    def test_false_for_non_dict(self):
        self.assertFalse(bot._deep_clean_block_eligible(None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_deepclean_unblock -v`
Expected: FAIL — `AttributeError: module 'bot' has no attribute '_deep_clean_block_eligible'`.

- [ ] **Step 3: Write minimal implementation**

In `bot.py`, immediately after `_dc_calendar_day_free` (ends ~line 2094), add:
```python
def _deep_clean_block_eligible(day):
    """True iff this Hostaway calendar-day dict is a block THIS feature created:
    unavailable + no guest reservation + our 'deep-clean' note sentinel. Anything
    else (a booking, a manual hold with a different/empty note, an available day)
    returns False so the unblock sweep can never free a date it didn't create."""
    if not isinstance(day, dict):
        return False
    try:
        avail = int(day.get("isAvailable", 1) or 0)
    except Exception:
        avail = 1
    if avail != 0:
        return False
    if day.get("reservationId"):
        return False
    return str(day.get("note") or "").strip().lower() == "deep-clean"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_deepclean_unblock -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_deepclean_unblock.py bot.py
git commit -m "feat(deepclean): add _deep_clean_block_eligible safety predicate (TDD)"
```

---

### Task 2: Deep-clean pause state + one-time unblock sweep

Persisted pause flag (starts **paused**), the unblock sweep that uses Task 1's predicate, and the pause checks wired into every scheduling entry point.

**Files:**
- Modify: `bot.py` — add `_dc_pause` global near `_deep_clean_state` (~`bot.py:8793`); add `_deep_clean_is_paused`, `unblock_all_deep_clean_dates`, `_dc_unblock_report_text` near `mark_deep_clean_done` (~`bot.py:2511`); add pause guards in `schedule_deep_cleans` (~2123), `confirm_tomorrow_deepcleans` (~2259), `deepclean_lookahead_check` (~2300); load in `load_state` (~48930); save in `persist_state` (~49104).

- [ ] **Step 1: Add the persisted pause state global**

In `bot.py`, right after `_deep_clean_state = {}` (line 8793), add:
```python
# Owner paused the deep-clean auto-blocker (2026-07-12). Persisted so it survives
# redeploys WITHOUT needing a Railway env edit. Defaults to paused on first boot;
# `!ouja deepclean-resume` (or the API) flips it back on. `unblocked_once` guards
# the one-time boot sweep that frees already-blocked dates.
_dc_pause = {"paused": True, "unblocked_once": False}


def _deep_clean_is_paused():
    return bool(_dc_pause.get("paused"))
```

- [ ] **Step 2: Add the unblock sweep + report text**

In `bot.py`, immediately after `mark_deep_clean_done` (ends ~line 2511), add:
```python
def unblock_all_deep_clean_dates():
    """Free every calendar date THIS deep-clean feature blocked, and ONLY those.
    Candidate set = units whose state says next_status=='blocked' with a date
    (fast — no full-calendar scan). For each, re-read Hostaway and unblock only if
    _deep_clean_block_eligible confirms it's our own 'deep-clean' block. Idempotent:
    re-running frees nothing because the day is already available. Returns a report."""
    freed, skipped = [], []
    listings = get_listings_map() or {}
    for lid, s in list(_deep_clean_state.items()):
        if s.get("next_status") != "blocked":
            continue
        iso = s.get("next_scheduled")
        if not iso:
            continue
        name = listings.get(lid, str(lid))
        try:
            cal = api_get(f"/listings/{lid}/calendar",
                          params={"startDate": iso, "endDate": iso})
            days = cal.get("result") or []
            day = days[0] if days else None
        except Exception as e:
            print(f"unblock cal read error ({lid},{iso}):", e)
            skipped.append({"name": name, "date": iso, "reason": "read-error"})
            continue
        if day and _deep_clean_block_eligible(day):
            try:
                api_put(f"/listings/{lid}/calendar",
                        {"startDate": iso, "endDate": iso, "isAvailable": 1})
                s["next_scheduled"] = None
                s["next_status"] = "unscheduled"
                freed.append({"lid": lid, "name": name, "date": iso})
            except Exception as e:
                print(f"unblock write error ({lid},{iso}):", e)
                skipped.append({"name": name, "date": iso, "reason": "write-error"})
        else:
            skipped.append({"name": name, "date": iso, "reason": "not-eligible"})
    return {"freed": freed, "count": len(freed), "skipped": skipped}


def _dc_unblock_report_text(rep):
    """Plain-Arabic summary of an unblock sweep for the ops channel."""
    NL = "\n"
    n = rep.get("count", 0)
    if not n:
        return "✅ حجب التنظيف العميق متوقف. ما فيه أي تاريخ محجوز حالياً."
    lines = ["✅ حجب التنظيف العميق متوقف. فكّيت %d تاريخ كان محجوز:" % n]
    for f in rep.get("freed", [])[:40]:
        lines.append("• %s — %s" % (f.get("name"), f.get("date")))
    if n > 40:
        lines.append("… +%d غيرها" % (n - 40))
    return NL.join(lines)
```

- [ ] **Step 3: Add pause guards to the three scheduling entry points**

In `schedule_deep_cleans` (line 2123), change:
```python
    if not DEEPCLEAN_ENABLED:
        return
```
to:
```python
    if not DEEPCLEAN_ENABLED or _deep_clean_is_paused():
        return
```

In `confirm_tomorrow_deepcleans` (line 2259), change:
```python
    if not DEEPCLEAN_ENABLED:
        return
```
to:
```python
    if not DEEPCLEAN_ENABLED or _deep_clean_is_paused():
        return
```

In `deepclean_lookahead_check` (line 2300), change:
```python
    if not DEEPCLEAN_ENABLED:
        return 0
```
to:
```python
    if not DEEPCLEAN_ENABLED or _deep_clean_is_paused():
        return 0
```

- [ ] **Step 4: Load + persist the pause state**

In `load_state`, right after the `_dc_anchor_date = _load_json("dc_anchor.json", None) or None` line (~48930), add:
```python
        _dc_pause.clear()
        _dc_pause.update(_load_json("deep_clean_pause.json",
                                    {"paused": True, "unblocked_once": False}))
```

In `persist_state`, right after `_save_json("dc_anchor.json", _dc_anchor_date)` (~49104), add:
```python
    _save_json("deep_clean_pause.json", dict(_dc_pause))
```

- [ ] **Step 5: Verify compile + existing tests still pass**

Run:
```bash
rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py && python3 -m pyflakes bot.py && python3 -m unittest tests.test_deepclean_unblock -v
```
Expected: clean compile, no pyflakes errors (other than pre-existing "imported but unused"), tests PASS.

- [ ] **Step 6: Commit**

```bash
git add bot.py
git commit -m "feat(deepclean): persisted pause flag + idempotent unblock sweep + pause guards"
```

---

### Task 3: Deep-clean pause wiring — boot sweep, commands, endpoints

Make the pause take effect on deploy (one-time sweep), and give the owner resume/pause controls.

**Files:**
- Modify: `bot.py` — `deepclean_schedule_loop` (~48673); add two API handlers near `_api_cleaning_reschedule` (~34868) and register them (~48338); add two `!ouja` commands near the delete-command family (~52145). Depends on `_post_ops_to_watchdog` from Task 6 — if executing strictly in order, define a temporary local post in this task OR reorder so Task 6's helper exists. **To avoid a forward reference, add the `_post_ops_to_watchdog`/`_send_long_to_channel` helpers here (Step 0) and Task 6 will reuse them.**

- [ ] **Step 0: Add the shared channel-post helpers (used here and by /update, /guests)**

In `bot.py`, immediately before `async def _watchdog_post` (~line 54268), add:
```python
async def _send_long_to_channel(ch, text):
    """Send text to a Discord channel in <=1900-char chunks (2000 is the hard limit)."""
    NL = "\n"
    buf = ""
    for ln in (text or "").split(NL):
        if len(buf) + len(ln) + 1 > 1900:
            if buf:
                await ch.send(buf)
            buf = ln
        else:
            buf = (buf + NL + ln) if buf else ln
    if buf:
        await ch.send(buf)


async def _post_ops_to_watchdog(text):
    """Post an on-demand ops summary to the watchdog room (غرفة-المراقبة). Best-effort."""
    if not text:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    try:
        cat = await get_category(guild)
        ch = await ensure_channel(guild, WATCHDOG_CHANNEL, cat)
        if ch:
            await _send_long_to_channel(ch, text)
    except Exception as e:
        print("ops channel post error:", e)
```

- [ ] **Step 1: Boot-time one-shot unblock sweep in the schedule loop**

Replace the body of `deepclean_schedule_loop` (lines 48673-48686) with:
```python
@tasks.loop(hours=4)
async def deepclean_schedule_loop():
    """Top up the deep-clean schedule for any unit that doesn't have a next date,
    then sweep the next 7 days for booking conflicts (early re-planning). Also runs
    the one-time unblock sweep the first boot after the owner paused the feature."""
    try:
        if _deep_clean_is_paused() and not _dc_pause.get("unblocked_once"):
            rep = await asyncio.to_thread(unblock_all_deep_clean_dates)
            _dc_pause["unblocked_once"] = True
            await asyncio.to_thread(persist_state)
            try:
                await _post_ops_to_watchdog(_dc_unblock_report_text(rep))
            except Exception as e:
                print("deepclean unblock report post error:", e)
            print(f"deepclean: one-time unblock freed {rep['count']} date(s)")
    except Exception as e:
        print("deepclean unblock sweep error:", e)
    try:
        await asyncio.to_thread(schedule_deep_cleans)
    except Exception as e:
        print("deepclean_schedule_loop error:", e)
    try:
        moved = await asyncio.to_thread(deepclean_lookahead_check)
        if moved:
            await asyncio.to_thread(persist_state)
    except Exception as e:
        print("deepclean lookahead error:", e)
```

- [ ] **Step 2: Add resume/pause API handlers**

In `bot.py`, immediately after `_api_cleaning_reschedule` (ends ~line 34868), add:
```python
async def _api_cleaning_resume_blocking(request):
    """Turn deep-clean auto-blocking back on."""
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    _dc_pause["paused"] = False
    await asyncio.to_thread(persist_state)
    return _json({"ok": True, "paused": False})


async def _api_cleaning_pause_blocking(request):
    """Pause deep-clean auto-blocking AND free every date it had blocked."""
    if not _dash_auth(request):
        return _json({"error": "unauthorized"}, 401)
    _dc_pause["paused"] = True
    rep = await asyncio.to_thread(unblock_all_deep_clean_dates)
    _dc_pause["unblocked_once"] = True
    await asyncio.to_thread(persist_state)
    return _json({"ok": True, "paused": True, "freed": rep["count"], "report": rep})
```

- [ ] **Step 3: Register the two routes**

In `start_web_server`, right after `app.router.add_post("/api/cleaning/reschedule-from", _api_cleaning_reschedule_from)` (line 48338), add:
```python
        app.router.add_post("/api/cleaning/pause-blocking", _api_cleaning_pause_blocking)
        app.router.add_post("/api/cleaning/resume-blocking", _api_cleaning_resume_blocking)
```

- [ ] **Step 4: Add the two `!ouja` commands**

In `bot.py`, immediately after `cmd_delete_this_channel` (ends ~line 52143), add:
```python
@bot.command(name="deepclean-resume", aliases=["تشغيل-التنظيف-العميق", "استئناف-الحجب"])
async def cmd_deepclean_resume(ctx):
    """!ouja deepclean-resume — turn deep-clean auto-blocking back on (admins only)."""
    if not _can_delete_channels(ctx.author):
        await ctx.reply("🚫 هذا الأمر للإدارة فقط.")
        return
    _dc_pause["paused"] = False
    await asyncio.to_thread(persist_state)
    await ctx.reply("✅ رجّعت حجب مواعيد التنظيف العميق يشتغل. من الليلة بيحجز مواعيد التنظيف مثل قبل.")


@bot.command(name="deepclean-pause", aliases=["ايقاف-التنظيف-العميق", "ايقاف-الحجب"])
async def cmd_deepclean_pause(ctx):
    """!ouja deepclean-pause — pause auto-blocking AND free its blocked dates (admins only)."""
    if not _can_delete_channels(ctx.author):
        await ctx.reply("🚫 هذا الأمر للإدارة فقط.")
        return
    await ctx.reply("⏳ أوقف الحجب وأفكّ التواريخ المحجوزة للتنظيف العميق…")
    _dc_pause["paused"] = True
    rep = await asyncio.to_thread(unblock_all_deep_clean_dates)
    _dc_pause["unblocked_once"] = True
    await asyncio.to_thread(persist_state)
    await ctx.send(_dc_unblock_report_text(rep))
```

- [ ] **Step 5: Verify compile + pyflakes**

Run:
```bash
rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py && python3 -m pyflakes bot.py
```
Expected: clean (ignore pre-existing "imported but unused").

- [ ] **Step 6: Commit**

```bash
git add bot.py
git commit -m "feat(deepclean): boot unblock sweep + resume/pause commands + API + ops-post helpers"
```

---

### Task 4: `/update` renderer (pure, TDD)

**Files:**
- Create: `tests/test_ops_commands_render.py`
- Modify: `bot.py` — add `render_update` and the `_AR_WEEKDAYS`/`_ar_today_label` helper near `compute_arrivals_with_status` (~`bot.py:2650`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_ops_commands_render.py`:
```python
# -*- coding: utf-8 -*-
"""Pure renderers for /update and /guests — deterministic text, no I/O."""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-opscmd"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ.setdefault("STATE_DIR", _STATE)

import bot  # noqa: E402


class TestRenderUpdate(unittest.TestCase):
    def test_empty(self):
        out = bot.render_update([], "الاثنين")
        self.assertIn("ما فيه تسجيلات دخول اليوم", out)

    def test_rows_and_agreement_states(self):
        rows = [
            {"unit": "Ouja | A", "guest": "سعد", "time_label": "15:00",
             "cleaned": True, "code_sent": False, "agreement": "signed"},
            {"unit": "Ouja | B", "guest": "نورة", "time_label": "18:00",
             "cleaned": False, "code_sent": True, "agreement": "not_signed"},
            {"unit": "Ouja | C", "guest": "John", "time_label": "",
             "cleaned": True, "code_sent": True, "agreement": "not_required"},
        ]
        out = bot.render_update(rows, "")
        self.assertIn("Ouja | A", out)
        self.assertIn("سعد", out)
        self.assertIn("موقّع", out)          # signed
        self.assertIn("غير موقّع", out)      # not_signed
        self.assertIn("لا يحتاج", out)       # not_required
        self.assertIn("3", out)              # count in header

    def test_sorted_by_time(self):
        rows = [
            {"unit": "B", "guest": "b", "time_label": "20:00",
             "cleaned": True, "code_sent": True, "agreement": "signed"},
            {"unit": "A", "guest": "a", "time_label": "09:00",
             "cleaned": True, "code_sent": True, "agreement": "signed"},
        ]
        out = bot.render_update(rows, "")
        self.assertLess(out.index("09:00"), out.index("20:00"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ops_commands_render -v`
Expected: FAIL — `module 'bot' has no attribute 'render_update'`.

- [ ] **Step 3: Write minimal implementation**

In `bot.py`, immediately after `compute_arrivals_with_status` (ends ~line 2649), add:
```python
_AR_WEEKDAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]  # Mon..Sun


def _ar_today_label():
    d = datetime.now(TZ).date()
    return "%s %s" % (_AR_WEEKDAYS[d.weekday()], d.isoformat())


def render_update(rows, date_label=""):
    """Pure Arabic-first renderer for today's check-ins. `rows` items:
    {unit, guest, time_label, cleaned(bool), code_sent(bool), agreement}
    where agreement in {'signed','not_signed','not_required'}."""
    NL = "\n"
    rows = sorted(rows or [], key=lambda x: x.get("time_label") or "")
    title = ("📋 تسجيلات الدخول اليوم %s" % date_label).strip()
    if not rows:
        return title + NL + "ما فيه تسجيلات دخول اليوم ✅"
    AGR = {"signed": "موقّع ✅", "not_signed": "غير موقّع ❌", "not_required": "لا يحتاج"}
    ok = lambda b: "✅" if b else "❌"
    out = ["%s — %d" % (title, len(rows))]
    for r in rows:
        head = "🏠 %s — %s" % (r.get("unit") or "-", r.get("guest") or "ضيف")
        if r.get("time_label"):
            head += " — 🕐 %s" % r["time_label"]
        out.append("")
        out.append(head)
        out.append("🧹 نظّفت: %s  ·  🔑 الكود: %s  ·  📝 العقد: %s" % (
            ok(r.get("cleaned")), ok(r.get("code_sent")),
            AGR.get(r.get("agreement"), "؟")))
    return NL.join(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ops_commands_render -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_ops_commands_render.py bot.py
git commit -m "feat(update): render_update pure renderer + Arabic date label (TDD)"
```

---

### Task 5: `/guests` renderer (pure, TDD)

**Files:**
- Modify: `tests/test_ops_commands_render.py` (add `TestRenderGuests`); `bot.py` — add `render_guests` right after `render_update` (~`bot.py:2695`).

- [ ] **Step 1: Add the failing test class**

Append to `tests/test_ops_commands_render.py`, before the `if __name__` block:
```python
class TestRenderGuests(unittest.TestCase):
    def test_empty(self):
        self.assertIn("ما فيه ضيوف", bot.render_guests([], ""))

    def test_sad_shows_issue_and_open_status(self):
        rows = [{"guest": "سعد", "unit": "Ouja | A", "mood": "sad",
                 "issue": "المكيف ما يبرد", "resolved": False}]
        out = bot.render_guests(rows, "")
        self.assertIn("☹️", out)
        self.assertIn("المكيف ما يبرد", out)
        self.assertIn("لسه مفتوحة", out)

    def test_sad_resolved_status(self):
        rows = [{"guest": "x", "unit": "y", "mood": "sad", "issue": "z", "resolved": True}]
        self.assertIn("تم الحل", bot.render_guests(rows, ""))

    def test_happy_hides_issue_line(self):
        rows = [{"guest": "نورة", "unit": "Ouja | B", "mood": "happy",
                 "issue": "", "resolved": True}]
        out = bot.render_guests(rows, "")
        self.assertIn("🙂", out)
        self.assertNotIn("المشكلة", out)

    def test_header_counts(self):
        rows = [
            {"guest": "a", "unit": "u", "mood": "happy", "issue": "", "resolved": True},
            {"guest": "b", "unit": "u", "mood": "normal", "issue": "", "resolved": True},
            {"guest": "c", "unit": "u", "mood": "sad", "issue": "i", "resolved": False},
        ]
        out = bot.render_guests(rows, "")
        self.assertIn("🙂 1", out)
        self.assertIn("😐 1", out)
        self.assertIn("☹️ 1", out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ops_commands_render -v`
Expected: FAIL — `module 'bot' has no attribute 'render_guests'`.

- [ ] **Step 3: Write minimal implementation**

In `bot.py`, immediately after `render_update` (from Task 4), add:
```python
def render_guests(rows, date_label=""):
    """Pure Arabic-first renderer for the in-house guest mood snapshot. `rows` items:
    {guest, unit, mood in {'happy','normal','sad'}, issue, resolved(bool)}.
    The issue + solved/open line shows ONLY for sad guests."""
    NL = "\n"
    EM = {"happy": "🙂", "normal": "😐", "sad": "☹️"}
    rows = rows or []
    title = ("🧑‍🤝‍🧑 حالة الضيوف %s" % date_label).strip()
    if not rows:
        return title + NL + "ما فيه ضيوف حاليًا"
    happy = sum(1 for r in rows if r.get("mood") == "happy")
    normal = sum(1 for r in rows if r.get("mood") == "normal")
    sad = sum(1 for r in rows if r.get("mood") == "sad")
    out = ["%s — 🙂 %d · 😐 %d · ☹️ %d" % (title, happy, normal, sad)]
    order = {"sad": 0, "normal": 1, "happy": 2}
    for r in sorted(rows, key=lambda x: order.get(x.get("mood"), 1)):
        out.append("")
        out.append("%s %s — %s" % (EM.get(r.get("mood"), "😐"),
                                   r.get("guest") or "ضيف", r.get("unit") or "-"))
        if r.get("mood") == "sad":
            issue = (r.get("issue") or "").strip() or "—"
            status = "✅ تم الحل" if r.get("resolved") else "⏳ لسه مفتوحة"
            out.append("   ⚠️ المشكلة: %s  ·  الحالة: %s" % (issue, status))
    return NL.join(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_ops_commands_render -v`
Expected: PASS (all TestRenderUpdate + TestRenderGuests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_ops_commands_render.py bot.py
git commit -m "feat(guests): render_guests pure renderer (TDD)"
```

---

### Task 6: `/update` data builder + command wiring

**Files:**
- Modify: `bot.py` — add `build_update_rows` near `render_update` (~`bot.py:2700`); add the slash + prefix commands near the deep-clean commands from Task 3 (~`bot.py:52180`). Uses `_post_ops_to_watchdog` (added in Task 3, Step 0).

- [ ] **Step 1: Add the data builder**

In `bot.py`, immediately after `render_guests` (from Task 5), add:
```python
def build_update_rows():
    """Assemble today's check-ins with cleaned / code-sent / agreement status.
    Reuses the watchdog's own signals. Runs sync (Hostaway calls) — call via
    asyncio.to_thread. 'cleaned' reflects what the system knows (no turnover
    record = treated as ready), same as the watchdog."""
    today = datetime.now(TZ).date()
    today_iso = today.isoformat()
    try:
        arrivals = compute_arrivals_with_status(window_hours=36, lookback_hours=24)
    except Exception as e:
        print("build_update_rows arrivals error:", e)
        arrivals = []
    rows = []
    for a in arrivals:
        ci = a.get("checkin_iso") or ""
        if ci[:10] != today_iso:
            continue
        lid = a.get("listing_id")
        # agreement: distinguish 'not needed' from 'not signed'
        try:
            if not _unit_requires_agreement(lid):
                agr = "not_required"
            elif a.get("signed"):
                agr = "signed"
            else:
                agr = "not_signed"
        except Exception:
            agr = "signed" if a.get("signed") else "not_signed"
        # door code sent? (reuse the watchdog classifier on the conversation)
        code_sent = False
        cid = a.get("conversation_id")
        if cid and _HAS_WATCHDOG and _watchdog:
            try:
                msgs = (api_get(f"/conversations/{cid}/messages") or {}).get("result") or []
                code_sent = bool(_watchdog.engine.classify_code_send(msgs)["found"])
            except Exception as e:
                print(f"build_update_rows code scan error ({cid}):", e)
        rows.append({
            "unit": a.get("unit"), "guest": a.get("guest"),
            "time_label": ci[11:16] if len(ci) >= 16 else "",
            "cleaned": _wd_cleaning_ok(lid, today_iso),
            "code_sent": code_sent,
            "agreement": agr,
        })
    return rows
```

- [ ] **Step 2: Add the slash + prefix commands**

In `bot.py`, immediately after `cmd_deepclean_pause` (from Task 3), add:
```python
@bot.tree.command(name="update", description="ملخص تسجيلات الدخول اليوم (نظافة/كود/عقد)")
async def slash_update(interaction: discord.Interaction):
    if not _can_delete_channels(interaction.user):
        await interaction.response.send_message("🚫 هذا الأمر للإدارة فقط.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        pass
    try:
        rows = await asyncio.to_thread(build_update_rows)
        text = render_update(rows, _ar_today_label())
    except Exception as e:
        print("/update error:", e)
        await interaction.followup.send("⚠️ صار خطأ وأنا أجهّز الملخص.", ephemeral=True)
        return
    await _post_ops_to_watchdog(text)
    tail = ("\n… (كامل التقرير في #%s)" % WATCHDOG_CHANNEL) if len(text) > 1900 else ""
    await interaction.followup.send(text[:1900] + tail, ephemeral=True)


@bot.command(name="update", aliases=["تحديث", "الوصول", "تسجيلات"])
async def cmd_update(ctx):
    """!ouja update — today's check-ins: cleaned / code / agreement (admins only)."""
    if not _can_delete_channels(ctx.author):
        await ctx.reply("🚫 هذا الأمر للإدارة فقط.")
        return
    try:
        rows = await asyncio.to_thread(build_update_rows)
        text = render_update(rows, _ar_today_label())
    except Exception as e:
        print("!ouja update error:", e)
        await ctx.reply("⚠️ صار خطأ وأنا أجهّز الملخص.")
        return
    await _post_ops_to_watchdog(text)
    await ctx.reply(text[:1900])
```

- [ ] **Step 3: Verify compile + pyflakes + existing tests**

Run:
```bash
rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py && python3 -m pyflakes bot.py && python3 -m unittest tests.test_ops_commands_render -v
```
Expected: clean compile, tests PASS.

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat(update): /update + !ouja update — today's check-ins summary to owner + غرفة-المراقبة"
```

---

### Task 7: `/guests` data builder (Claude) + command wiring

**Files:**
- Modify: `bot.py` — add `_GUEST_MOOD_SYSTEM`, `_guest_history_text`, `_classify_one_guest`, `build_guests_rows` near `build_update_rows` (~`bot.py:2760`); add the slash + prefix commands after the `/update` commands (~`bot.py:52240`).

- [ ] **Step 1: Add the Claude prompt + per-guest classifier + builder**

In `bot.py`, immediately after `build_update_rows` (from Task 6), add:
```python
_GUEST_MOOD_SYSTEM = (
    "أنت محلل خدمة ضيوف لشركة عوجا للشقق المخدومة في الرياض. تقرأ محادثة ضيف حالي "
    "وتقيّم مزاجه من آخر الرسائل. أعِد JSON فقط بدون أي شرح أو أسوار كود:\n"
    '{"mood":"happy|normal|sad","issue":"","resolved":true}\n'
    "happy = راضٍ/شاكر/مبسوط. normal = محايد/استفسار عادي/لوجستي. "
    "sad = منزعج/يشتكي/عنده مشكلة أو تذمّر.\n"
    "issue: إذا كان sad فقط — جملة قصيرة بالعربي (≤ 12 كلمة) تلخّص المشكلة، وإلا اتركها فارغة.\n"
    "resolved: true إذا كانت آخر الرسائل تدل أن المشكلة عولجت/انتهت، false إذا لسه مفتوحة."
)


def _guest_history_text(cid, limit=14):
    try:
        msgs = (api_get(f"/conversations/{cid}/messages") or {}).get("result") or []
    except Exception as e:
        print(f"guest history error ({cid}):", e)
        return ""
    seq = sorted(msgs, key=_msg_sort_key)[-limit:]
    lines = []
    for m in seq:
        body = (m.get("body") or "").strip()
        if body:
            who = "الضيف" if _msg_is_inbound(m) else "عوجا"
            lines.append("%s: %s" % (who, body))
    return "\n".join(lines)


def _classify_one_guest(item):
    """One guest → {guest, unit, mood, issue, resolved, conversation_id}. Degrades to
    'normal' if there's no conversation or Claude fails — never raises."""
    cid = item.get("conversation_id")
    mood, issue, resolved = "normal", "", True
    if cid:
        hist = _guest_history_text(cid)
        if hist:
            d = claude_json(_GUEST_MOOD_SYSTEM, hist, max_tokens=200) or {}
            m = str(d.get("mood") or "").lower()
            if m in ("happy", "normal", "sad"):
                mood = m
            issue = str(d.get("issue") or "").strip()
            resolved = bool(d.get("resolved", True))
    return {"guest": item.get("guest"), "unit": item.get("unit"),
            "mood": mood, "issue": issue if mood == "sad" else "",
            "resolved": resolved, "conversation_id": str(cid or "")}


def build_guests_rows():
    """Enumerate current in-house guests, classify each with Claude (concurrent),
    and cross-check the promises ledger so a sad guest with an OPEN promise is shown
    as still-open regardless of the model's read. Runs sync — call via to_thread."""
    from concurrent.futures import ThreadPoolExecutor
    today = datetime.now(TZ).date()
    listings = get_listings_map() or {}
    res = fetch_inhouse(today)
    items, seen = [], set()
    for r in res:
        if not _res_realized(r):
            continue
        key = (r.get("listingMapId"), r.get("id"))
        if key in seen:
            continue
        seen.add(key)
        lid = r.get("listingMapId")
        items.append({
            "guest": r.get("guestName") or "Guest",
            "unit": listings.get(lid) or r.get("listingName") or ("unit-%s" % lid),
            "conversation_id": r.get("conversationId"),
        })
    # open promises → force sad guests to "still open"
    open_cids = set()
    if _HAS_PK and _pk:
        try:
            for p in _pk.db.open_rows():
                if p.get("conversation_id"):
                    open_cids.add(str(p["conversation_id"]))
        except Exception as e:
            print("guests promises lookup error:", e)
    rows = []
    if items:
        with ThreadPoolExecutor(max_workers=6) as ex:
            rows = list(ex.map(_classify_one_guest, items))
    for row in rows:
        if row.get("mood") == "sad" and row.get("conversation_id") in open_cids:
            row["resolved"] = False
    return rows
```

- [ ] **Step 2: Add the slash + prefix commands**

In `bot.py`, immediately after `cmd_update` (from Task 6), add:
```python
@bot.tree.command(name="guests", description="حالة الضيوف الحاليين (سعيد/عادي/زعلان) عبر Claude")
async def slash_guests(interaction: discord.Interaction):
    if not _can_delete_channels(interaction.user):
        await interaction.response.send_message("🚫 هذا الأمر للإدارة فقط.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
    except Exception:
        pass
    try:
        rows = await asyncio.to_thread(build_guests_rows)
        text = render_guests(rows, _ar_today_label())
    except Exception as e:
        print("/guests error:", e)
        await interaction.followup.send("⚠️ صار خطأ وأنا أجهّز حالة الضيوف.", ephemeral=True)
        return
    await _post_ops_to_watchdog(text)
    tail = ("\n… (كامل التقرير في #%s)" % WATCHDOG_CHANNEL) if len(text) > 1900 else ""
    await interaction.followup.send(text[:1900] + tail, ephemeral=True)


@bot.command(name="guests", aliases=["الضيوف", "حالة-الضيوف", "المزاج"])
async def cmd_guests(ctx):
    """!ouja guests — in-house guest mood summary via Claude (admins only)."""
    if not _can_delete_channels(ctx.author):
        await ctx.reply("🚫 هذا الأمر للإدارة فقط.")
        return
    try:
        rows = await asyncio.to_thread(build_guests_rows)
        text = render_guests(rows, _ar_today_label())
    except Exception as e:
        print("!ouja guests error:", e)
        await ctx.reply("⚠️ صار خطأ وأنا أجهّز حالة الضيوف.")
        return
    await _post_ops_to_watchdog(text)
    await ctx.reply(text[:1900])
```

- [ ] **Step 3: Verify compile + pyflakes + existing tests**

Run:
```bash
rm -rf __pycache__ && python3 -W error::SyntaxWarning -m py_compile bot.py && python3 -m pyflakes bot.py && python3 -m unittest tests.test_ops_commands_render -v
```
Expected: clean compile, tests PASS.

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat(guests): /guests + !ouja guests — in-house mood summary via Claude, promises cross-check"
```

---

### Task 8: Full verification + DASHBOARD_HTML integrity + push

**Files:** none (verification + deploy only).

- [ ] **Step 1: Run the full repo verification routine**

Run:
```bash
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py finance/*.py
node --check finance/static/erp.js
python3 -m unittest discover -s tests -p "test_*.py"
```
Expected: py_compile clean; pyflakes shows only pre-existing "imported but unused"; `node --check` clean; **all** tests pass (including the two new files).

- [ ] **Step 2: Confirm DASHBOARD_HTML embedded JS still parses (untouched, but the routine mandates it)**

Run:
```bash
python3 -c "import bot, esprima, re; [esprima.parseScript(js) for js in re.findall(r'<script>(.*?)</script>', bot.DASHBOARD_HTML, re.S)]; print('DASHBOARD_HTML JS OK')"
```
Expected: `DASHBOARD_HTML JS OK`. (If `esprima` is missing: `pip install esprima` — pure-Python, offline.)

- [ ] **Step 3: Sanity-check the whole module imports and the new symbols exist**

Run:
```bash
STATE_DIR=/tmp/ouja-verify python3 -c "import bot; print(all(hasattr(bot,n) for n in ['_deep_clean_block_eligible','unblock_all_deep_clean_dates','_deep_clean_is_paused','render_update','render_guests','build_update_rows','build_guests_rows']))"
```
Expected: `True`.

- [ ] **Step 4: Push (triggers the Railway redeploy) — single push, no rapid re-deploys**

```bash
git push origin main
```

- [ ] **Step 5: Post-deploy owner check (plain language)**

Tell the owner to verify:
1. In غرفة-المراقبة a message appears listing the deep-clean dates that were freed (or "no dates blocked").
2. Type `/update` in Discord → get today's check-ins with 🧹 / 🔑 / 📝 status (private reply + a copy in غرفة-المراقبة).
3. Type `/guests` → get each current guest as 🙂/😐/☹️, with the issue + solved/open line for anyone unhappy.
4. Deep-clean auto-blocking stays off until `!ouja deepclean-resume`.

---

## Notes on testing philosophy (why the wiring isn't unit-tested)
Following the repo's established split (watchdog: pure `engine` is TDD-locked, the Hostaway/Discord wiring is not), the **pure cores** — `_deep_clean_block_eligible`, `render_update`, `render_guests` — carry the tests, because they hold the load-bearing logic (safety of unblocking; correctness of what the owner reads). The builders and commands are thin adapters over already-proven helpers (`compute_arrivals_with_status`, `_watchdog.engine.classify_code_send`, `_wd_cleaning_ok`, `_unit_requires_agreement`, `fetch_inhouse`, `claude_json`, `_pk.db.open_rows`) and are validated by compile + pyflakes + the post-deploy owner check.

## Known limitations (surface honestly, do not hide)
- `/update` "cleaned ✅" means *the system has no open turnover record* — if a cleaner didn't log, it can read ✅. Same signal the watchdog uses.
- `/guests` mood depends on the guest actually having a conversation thread with messages; no thread → shown as 😐 normal.
- `/guests` "solved/open" is forced to open when a matching **open promise** exists; otherwise it trusts Claude's read of the latest messages.
