# Cleaning Dispatch → WhatsApp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each day auto-post one ready-to-send WhatsApp message per cleaning crew into a new Discord `dispatch` channel, listing that crew's apartments to clean (checkout time, next check-in, early-departure flag), with a tap-to-send button; plus a `!ouja dispatch` command and a crew-less safety net.

**Architecture:** Purely additive to `bot.py`. Reuses `fetch_oujact_turnovers()` (today+tomorrow turnovers, filtered by `checkout_date`), the existing `cleaning_team` field + `_cleaning_teams` map, `schedule/coverage.py` for the ops-owner emoji (Discord card only), and `PUBLIC_BASE_URL` for an absolute Discord link button. The button points at a short `/d/{token}` redirect that rebuilds the WhatsApp deep link server-side (dodges Discord's 512-char button URL limit and always reflects fresh data). No auto-send, no new data model, no changes to the midnight OujaCT builder.

**Tech Stack:** Python 3, discord.py (`commands.Bot`, `tasks.loop`, `discord.ui.View`/link `Button`), aiohttp (`web.HTTPFound` redirect), the repo's `unittest` suite (no pytest).

**Design spec:** [docs/superpowers/specs/2026-07-21-cleaning-dispatch-whatsapp-design.md](../specs/2026-07-21-cleaning-dispatch-whatsapp-design.md)

---

## File map

- **Modify `bot.py`** — all new backend code. New section "Cleaning Dispatch" placed right after `post_oujact_schedule` (~line 3870). Config constants added near `OUJACT_SCHEDULE_CHANNEL` (~line 280). Loop start added in `on_ready` (~line 55613). Command added near other `@bot.command`s (~line 52942). Crew-phone edits in `_ct_team_view` (~736) and `_api_cleaning_teams` (~43765) and the dashboard JS (~25231).
- **Create `tests/test_dispatch.py`** — unit tests for every pure function.

### Naming (locked — use these exact names everywhere)
`DISPATCH_ENABLED`, `DISPATCH_CHANNEL`, `DISPATCH_HOUR`, `DISPATCH_DRYRUN`, `_AR_WEEKDAYS`,
`_dispatch_fmt_date`, `_dispatch_fmt_time`, `_dispatch_resolve_date`, `_dispatch_wa_text`,
`_dispatch_embed_lines`, `_dispatch_embed`, `_wa_send_url`, `_dispatch_group`, `_dispatch_jobs`,
`_dispatch_state`, `_dispatch_load_state`, `post_dispatch`, `_handle_d_redirect`,
`dispatch_daily_loop`, `cmd_dispatch`.

---

## Task 0: Config constants + urllib import

**Files:**
- Modify: `bot.py` near line 280 (beside `OUJACT_SCHEDULE_CHANNEL`) and the top-level imports.

- [ ] **Step 1: Add a module-level `import urllib.parse`.** Near the other top-of-file imports (the `import` block around lines 1–40), add:

```python
import urllib.parse
```

(`urllib.parse` is currently only imported locally at bot.py:48685 — a module-level import is safe and idempotent.)

- [ ] **Step 2: Add the dispatch config constants.** Right after the `OUJACT_SCHEDULE_CHANNEL = ...` line (~bot.py:280):

```python
# ---- Cleaning Dispatch (WhatsApp) config ----
DISPATCH_ENABLED = os.environ.get("DISPATCH_ENABLED", "1") == "1"
DISPATCH_CHANNEL = os.environ.get("DISPATCH_CHANNEL", "dispatch")
DISPATCH_HOUR    = int(os.environ.get("DISPATCH_HOUR", "21"))   # Riyadh hour for the nightly auto-post
DISPATCH_DRYRUN  = os.environ.get("DISPATCH_DRYRUN", "0") == "1"
```

- [ ] **Step 3: Verify it still compiles.**

Run: `cd /Users/faisalouja/Ouja-Turnover && rm -rf __pycache__ && python3 -m py_compile bot.py`
Expected: no output (clean compile).

- [ ] **Step 4: Commit.**

```bash
git add bot.py
git commit -m "feat(dispatch): config constants + urllib import"
```

---

## Task 1: Arabic date/time formatters (pure)

**Files:**
- Modify: `bot.py` — add new section after `post_oujact_schedule` (~line 3870).
- Test: `tests/test_dispatch.py`

- [ ] **Step 1: Write the failing test.** Create `tests/test_dispatch.py`:

```python
import unittest
from datetime import datetime
import bot


class TestDispatchFormatters(unittest.TestCase):
    def test_fmt_date_arabic_weekday(self):
        # 2026-07-22 is a Wednesday
        self.assertEqual(bot._dispatch_fmt_date("2026-07-22"), "الأربعاء 22/7")

    def test_fmt_time_am_pm(self):
        noon = datetime(2026, 7, 22, 12, 0, tzinfo=bot.TZ)
        morning = datetime(2026, 7, 22, 9, 5, tzinfo=bot.TZ)
        afternoon = datetime(2026, 7, 22, 15, 30, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_fmt_time(noon), "12:00 م")
        self.assertEqual(bot._dispatch_fmt_time(morning), "9:05 ص")
        self.assertEqual(bot._dispatch_fmt_time(afternoon), "3:30 م")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: FAIL — `AttributeError: module 'bot' has no attribute '_dispatch_fmt_date'`.

- [ ] **Step 3: Implement the formatters.** In `bot.py`, right after `post_oujact_schedule` ends (~line 3870), start the new section:

```python
# ==================== Cleaning Dispatch → WhatsApp (الإرسال) ====================
# Additive, isolated. Reuses fetch_oujact_turnovers() + the cleaning_team field.

# Python's date.weekday(): Monday=0 .. Sunday=6
_AR_WEEKDAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

def _dispatch_fmt_date(date_iso):
    """'2026-07-22' -> 'الأربعاء 22/7'. Pure."""
    d = datetime.strptime(date_iso, "%Y-%m-%d").date()
    return f"{_AR_WEEKDAYS[d.weekday()]} {d.day}/{d.month}"

def _dispatch_fmt_time(dt):
    """datetime -> '3:30 م' / '9:05 ص' (12-hour, Arabic AM/PM). Pure."""
    ap = "ص" if dt.hour < 12 else "م"
    h12 = dt.hour % 12 or 12
    return f"{h12}:{dt.minute:02d} {ap}"
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit.**

```bash
git add bot.py tests/test_dispatch.py
git commit -m "feat(dispatch): Arabic date/time formatters + tests"
```

---

## Task 2: Date resolution (`_dispatch_resolve_date`)

**Files:**
- Modify: `bot.py` (dispatch section)
- Test: `tests/test_dispatch.py`

- [ ] **Step 1: Write the failing test.** Append to `tests/test_dispatch.py`:

```python
class TestDispatchResolveDate(unittest.TestCase):
    def test_auto_before_noon_is_today(self):
        now = datetime(2026, 7, 21, 9, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date(None, now=now), "2026-07-21")

    def test_auto_after_noon_is_tomorrow(self):
        now = datetime(2026, 7, 21, 14, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date(None, now=now), "2026-07-22")

    def test_explicit_today_tomorrow(self):
        now = datetime(2026, 7, 21, 14, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date("today", now=now), "2026-07-21")
        self.assertEqual(bot._dispatch_resolve_date("tomorrow", now=now), "2026-07-22")

    def test_explicit_iso_date(self):
        now = datetime(2026, 7, 21, 14, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date("2026-08-01", now=now), "2026-08-01")

    def test_garbage_falls_back_to_auto(self):
        now = datetime(2026, 7, 21, 9, 0, tzinfo=bot.TZ)
        self.assertEqual(bot._dispatch_resolve_date("banana", now=now), "2026-07-21")
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: FAIL — `_dispatch_resolve_date` not defined.

- [ ] **Step 3: Implement.** In the dispatch section (after the formatters):

```python
def _dispatch_resolve_date(mode=None, now=None):
    """Resolve the target cleaning day as 'YYYY-MM-DD'. Pure (inject `now` for tests).
      - None/''/'auto' : today if before 12:00 noon, else tomorrow
      - 'today'        : today
      - 'tomorrow'     : tomorrow
      - 'YYYY-MM-DD'   : that exact date
      - anything else  : falls back to auto (never raises)."""
    now = now or datetime.now(TZ)
    today = now.date()
    m = (mode or "").strip().lower()
    if m == "today":
        target = today
    elif m == "tomorrow":
        target = today + timedelta(days=1)
    elif m in ("", "auto"):
        target = today if now.hour < 12 else today + timedelta(days=1)
    else:
        try:
            target = datetime.strptime(m, "%Y-%m-%d").date()
        except ValueError:
            target = today if now.hour < 12 else today + timedelta(days=1)
    return target.isoformat()
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: all PASS.

- [ ] **Step 5: Commit.**

```bash
git add bot.py tests/test_dispatch.py
git commit -m "feat(dispatch): smart date resolution (before/after noon) + tests"
```

---

## Task 3: WhatsApp text + Discord card lines (pure)

**Files:**
- Modify: `bot.py` (dispatch section)
- Test: `tests/test_dispatch.py`

Note on the item shape: turnover items come from `fetch_oujact_turnovers()` and carry
`lid`, `listing`, `checkout` (datetime), `checkout_date` (str), `checkin_today` (bool),
`checkin_dt` (datetime|None), `early_departure` (bool). The tests build minimal dicts with
those keys.

- [ ] **Step 1: Write the failing test.** Append:

```python
class TestDispatchText(unittest.TestCase):
    def _items(self):
        return [
            {"lid": 1, "listing": "Ouja | الملقا 1",
             "checkout": datetime(2026, 7, 22, 12, 0, tzinfo=bot.TZ),
             "checkin_today": True, "checkin_dt": datetime(2026, 7, 22, 15, 0, tzinfo=bot.TZ),
             "early_departure": False},
            {"lid": 2, "listing": "Ouja | جود 13",
             "checkout": datetime(2026, 7, 22, 11, 0, tzinfo=bot.TZ),
             "checkin_today": False, "checkin_dt": None,
             "early_departure": True},
        ]

    def test_wa_text_structure(self):
        txt = bot._dispatch_wa_text("الملقا", "2026-07-22", self._items())
        self.assertIn("تنظيف — فريق الملقا", txt)
        self.assertIn("عدد الشقق: 2", txt)
        self.assertIn("الأربعاء 22/7", txt)
        self.assertIn("Ouja | الملقا 1", txt)
        self.assertIn("دخول اليوم 3:00 م (عاجل)", txt)   # same-day check-in flagged
        self.assertIn("الضيف طلع بدري", txt)             # early departure flagged
        self.assertIn("الرجاء تأكيد الاستلام", txt)

    def test_wa_text_empty(self):
        txt = bot._dispatch_wa_text("X", "2026-07-22", [])
        self.assertIn("عدد الشقق: 0", txt)

    def test_embed_lines_include_owner(self):
        covers = {1: {"name": "ناصر", "emoji": "🟢"}, 2: {"name": "عهود", "emoji": "🟡"}}
        lines = bot._dispatch_embed_lines(self._items(), covers)
        self.assertEqual(len(lines), 2)
        self.assertIn("ناصر", lines[0])
        self.assertIn("🔴", lines[0])   # same-day check-in marker on the card
        self.assertIn("⚡", lines[1])    # early-departure marker on the card
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: FAIL — `_dispatch_wa_text` / `_dispatch_embed_lines` not defined.

- [ ] **Step 3: Implement.** In the dispatch section:

```python
def _dispatch_wa_text(team_name, date_iso, items):
    """Crew-facing WhatsApp message (Arabic, clean — NO internal ops names). Pure.
    `items` must already be priority-sorted (fetch_oujact_turnovers order)."""
    lines = [f"تنظيف — فريق {team_name}",
             f"{_dispatch_fmt_date(date_iso)} · عدد الشقق: {len(items)}", ""]
    for i, it in enumerate(items, 1):
        parts = [f"{i}. {it['listing']} — خروج {_dispatch_fmt_time(it['checkout'])}"]
        if it.get("checkin_today") and it.get("checkin_dt"):
            parts.append(f"دخول اليوم {_dispatch_fmt_time(it['checkin_dt'])} (عاجل)")
        else:
            parts.append("لا يوجد دخول اليوم")
        if it.get("early_departure"):
            parts.append("الضيف طلع بدري")
        lines.append("، ".join(parts))
    lines += ["", "الرجاء تأكيد الاستلام"]
    return "\n".join(lines)

def _dispatch_embed_lines(items, covers=None):
    """Discord-card lines (dispatcher-facing) — includes the responsible ops owner
    (name + emoji) which is deliberately hidden from the crew's WhatsApp text. Pure.
    `covers` = {lid: {name, emoji}} or None."""
    covers = covers or {}
    out = []
    for i, it in enumerate(items, 1):
        seg = f"**{i}.** {it['listing']} — خروج {_dispatch_fmt_time(it['checkout'])}"
        if it.get("checkin_today"):
            seg += " 🔴 دخول اليوم"
        if it.get("early_departure"):
            seg += " ⚡"
        cov = covers.get(it["lid"]) or {}
        tag = ((cov.get("emoji") or "") + " " + (cov.get("name") or "")).strip()
        if tag:
            seg += f"  · {tag}"
        out.append(seg)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: all PASS.

- [ ] **Step 5: Commit.**

```bash
git add bot.py tests/test_dispatch.py
git commit -m "feat(dispatch): WhatsApp text + Discord card lines + tests"
```

---

## Task 4: WhatsApp send-URL builder (`_wa_send_url`)

**Files:**
- Modify: `bot.py` (dispatch section)
- Test: `tests/test_dispatch.py`

`_wa_from_phone(phone)` (bot.py:2767) already returns a scheme-less `wa.me/<intl>` (KSA
`05…` → `9665…`), or `""` if the number is too short.

- [ ] **Step 1: Write the failing test.** Append:

```python
class TestWaSendUrl(unittest.TestCase):
    def test_with_phone(self):
        url = bot._wa_send_url("0501234567", "مرحبا")
        self.assertTrue(url.startswith("https://wa.me/966501234567?text="))
        self.assertIn("%D9%85", url)   # arabic is percent-encoded

    def test_without_phone_uses_contact_picker(self):
        url = bot._wa_send_url("", "hello world")
        self.assertTrue(url.startswith("https://api.whatsapp.com/send?text="))
        self.assertNotIn(" ", url)     # spaces encoded

    def test_newlines_encoded(self):
        url = bot._wa_send_url("", "line1\nline2")
        self.assertIn("line1%0Aline2", url)
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: FAIL — `_wa_send_url` not defined.

- [ ] **Step 3: Implement.** In the dispatch section:

```python
def _wa_send_url(phone, text):
    """Build a WhatsApp deep link. With a phone → direct chat; without → contact picker. Pure."""
    enc = urllib.parse.quote(text, safe="")
    wa = _wa_from_phone(phone)                         # 'wa.me/<intl>' or ''
    if wa:
        return "https://" + wa + "?text=" + enc
    return "https://api.whatsapp.com/send?text=" + enc
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: all PASS.

- [ ] **Step 5: Commit.**

```bash
git add bot.py tests/test_dispatch.py
git commit -m "feat(dispatch): WhatsApp send-url builder + tests"
```

---

## Task 5: Grouping by crew + safety net (`_dispatch_group`, `_dispatch_jobs`)

**Files:**
- Modify: `bot.py` (dispatch section)
- Test: `tests/test_dispatch.py`

- [ ] **Step 1: Write the failing test.** Append:

```python
class TestDispatchGroup(unittest.TestCase):
    def test_group_and_unassigned(self):
        items = [
            {"lid": 1, "listing": "A"},
            {"lid": 2, "listing": "B"},
            {"lid": 3, "listing": "C"},  # no crew -> unassigned
        ]
        team_of = {1: "t1", 2: "t2", 3: ""}
        jobs = bot._dispatch_group(items, team_of)
        self.assertEqual([it["lid"] for it in jobs["teams"]["t1"]], [1])
        self.assertEqual([it["lid"] for it in jobs["teams"]["t2"]], [2])
        self.assertEqual([it["lid"] for it in jobs["unassigned"]], [3])

    def test_group_preserves_order_within_team(self):
        items = [{"lid": 1, "listing": "A"}, {"lid": 2, "listing": "B"}]
        team_of = {1: "t1", 2: "t1"}
        jobs = bot._dispatch_group(items, team_of)
        self.assertEqual([it["lid"] for it in jobs["teams"]["t1"]], [1, 2])
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: FAIL — `_dispatch_group` not defined.

- [ ] **Step 3: Implement both.** In the dispatch section:

```python
def _dispatch_group(items, team_of_lid):
    """Group priority-sorted turnover items by crew id. Items whose crew is '' land in
    'unassigned' (the miss-proofing bucket). Pure. Preserves input order within each crew."""
    teams, unassigned = {}, []
    for it in items:
        tid = str(team_of_lid.get(it["lid"]) or "")
        if tid:
            teams.setdefault(tid, []).append(it)
        else:
            unassigned.append(it)
    return {"teams": teams, "unassigned": unassigned}

def _dispatch_jobs(date_iso):
    """Thin wrapper: fetch today+tomorrow turnovers, keep only `date_iso`, group by crew.
    Returns {'date', 'teams': {tid: [items]}, 'unassigned': [items]}."""
    items = [it for it in fetch_oujact_turnovers() if it.get("checkout_date") == date_iso]
    listings = _ls_get()["listings"]
    team_of = {}
    for it in items:
        rec = listings.get(str(it["lid"])) or {}
        team_of[it["lid"]] = rec.get("cleaning_team") or ""
    grouped = _dispatch_group(items, team_of)
    grouped["date"] = date_iso
    return grouped
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: all PASS.

- [ ] **Step 5: Commit.**

```bash
git add bot.py tests/test_dispatch.py
git commit -m "feat(dispatch): crew grouping + unassigned safety net + tests"
```

---

## Task 6: Discord embed + `post_dispatch` (I/O — no unit test, dry-run verified)

**Files:**
- Modify: `bot.py` (dispatch section)

This is Discord I/O; correctness of the message *content* is already covered by Task 3's tests.
Here we assemble the embed and post one message per crew.

- [ ] **Step 1: Implement `_dispatch_embed` (thin wrapper over the tested `_dispatch_embed_lines`).**

```python
def _dispatch_embed(team_name, date_iso, items, covers=None):
    e = discord.Embed(title=f"🧹 تنظيف — فريق {team_name}",
                      description=f"{_dispatch_fmt_date(date_iso)} · {len(items)} شقة",
                      color=GOLD)
    body = "\n".join(_dispatch_embed_lines(items, covers)) or "—"
    e.add_field(name="الشقق", value=body[:1024], inline=False)
    e.set_footer(text="اضغط الزر لإرسال القائمة عبر واتساب لهذا الفريق.")
    return e
```

- [ ] **Step 2: Implement `post_dispatch`.**

```python
async def post_dispatch(date_iso):
    """Post one message per crew (with a Send-on-WhatsApp button) to the dispatch channel,
    plus a safety-net message for crew-less apartments. Honors DISPATCH_DRYRUN."""
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    jobs = await asyncio.to_thread(_dispatch_jobs, date_iso)
    category = await get_category(guild)
    ch = await ensure_channel(guild, DISPATCH_CHANNEL, category)
    if ch is None:
        return
    base = (os.environ.get("PUBLIC_BASE_URL") or "").rstrip("/")
    posted = 0
    for tid, items in jobs["teams"].items():
        team = _cleaning_teams.get(tid) or {"id": tid, "name": "؟", "token": ""}
        covers = {}
        for it in items:
            covers[it["lid"]] = _oujact_cover_info(it["listing"], date_iso, it["lid"])
        embed = _dispatch_embed(team.get("name", ""), date_iso, items, covers)
        view = None
        if base and team.get("token"):
            url = base + "/d/" + team["token"] + "?date=" + date_iso
            view = discord.ui.View(timeout=None)
            view.add_item(discord.ui.Button(label="📲 أرسل عبر واتساب",
                                            style=discord.ButtonStyle.link, url=url))
        else:
            # Graceful fallback when PUBLIC_BASE_URL is unset: paste the copyable text.
            txt = _dispatch_wa_text(team.get("name", ""), date_iso, items)
            embed.add_field(name="الرسالة (انسخها لواتساب)",
                            value="```\n" + txt[:1000] + "\n```", inline=False)
        if DISPATCH_DRYRUN:
            print(f"[dispatch DRYRUN] {team.get('name')}: {len(items)} apts, date={date_iso}")
        else:
            await ch.send(embed=embed, view=view)
        posted += 1
    if jobs["unassigned"]:
        names = "\n".join(f"• {it['listing']} — خروج {_dispatch_fmt_time(it['checkout'])}"
                          for it in jobs["unassigned"])
        warn = discord.Embed(
            title="⚠️ شقق تحتاج تنظيف — غير معيّنة لأي فريق",
            description=(f"{_dispatch_fmt_date(date_iso)}\n{names}\n\n"
                        "عيّن لها فريق تنظيف حتى تنرسل تلقائياً.")[:4000],
            color=0xC0392B)
        if DISPATCH_DRYRUN:
            print(f"[dispatch DRYRUN] UNASSIGNED: {len(jobs['unassigned'])} apts")
        else:
            await ch.send(embed=warn)
    if posted == 0 and not jobs["unassigned"] and not DISPATCH_DRYRUN:
        await ch.send(f"لا يوجد تنظيف — {_dispatch_fmt_date(date_iso)} 🎉")
```

- [ ] **Step 3: Verify it compiles.**

Run: `cd /Users/faisalouja/Ouja-Turnover && rm -rf __pycache__ && python3 -m py_compile bot.py`
Expected: clean compile.

- [ ] **Step 4: Verify no regression in the suite.**

Run: `cd /Users/faisalouja/Ouja-Turnover && python3 -m unittest tests.test_dispatch -v`
Expected: all Task 1–5 tests still PASS.

- [ ] **Step 5: Commit.**

```bash
git add bot.py
git commit -m "feat(dispatch): Discord embed + post_dispatch (per-crew + safety net)"
```

---

## Task 7: `/d/{token}` redirect endpoint + robots

**Files:**
- Modify: `bot.py` — handler in the dispatch section; route registration (~49094); robots (~46042).

- [ ] **Step 1: Implement the redirect handler.** In the dispatch section:

```python
async def _handle_d_redirect(request):
    """Short link the Discord button points at. Rebuilds the crew's WhatsApp message fresh
    (dodges Discord's 512-char button-URL limit) and 302-redirects to the WhatsApp deep link."""
    token = request.match_info.get("token", "")
    team = _ct_team_by_token(token)
    if team is None:
        raise web.HTTPNotFound()
    date_iso = request.query.get("date") or _dispatch_resolve_date(None)
    jobs = await asyncio.to_thread(_dispatch_jobs, date_iso)
    items = jobs["teams"].get(team["id"], [])
    text = _dispatch_wa_text(team.get("name", ""), date_iso, items)
    raise web.HTTPFound(_wa_send_url(team.get("phone", ""), text))
```

- [ ] **Step 2: Register the route.** In the route block (~bot.py:49094, next to the other cleaning routes) add:

```python
        app.router.add_get("/d/{token}", _handle_d_redirect)   # WhatsApp dispatch redirect
```

- [ ] **Step 3: Disallow it for robots.** In `_handle_robots` (~bot.py:46042), add one line to the concatenated string (after the `/oujact-route` line):

```python
           "Disallow: /d/\n"
```

- [ ] **Step 4: Verify it compiles.**

Run: `cd /Users/faisalouja/Ouja-Turnover && rm -rf __pycache__ && python3 -m py_compile bot.py`
Expected: clean compile.

- [ ] **Step 5: Commit.**

```bash
git add bot.py
git commit -m "feat(dispatch): /d/{token} WhatsApp redirect + robots disallow"
```

---

## Task 8: Nightly auto-post loop

**Files:**
- Modify: `bot.py` — loop def (dispatch section), state loader, loop start in `on_ready` (~55613).

- [ ] **Step 1: Add the persisted once-per-day guard state.** In the dispatch section:

```python
_dispatch_state = None   # lazily loaded {'last_auto': 'YYYY-MM-DD'}

def _dispatch_load_state():
    global _dispatch_state
    if _dispatch_state is None:
        _dispatch_state = _load_json("dispatch_state.json", {}) or {}
    return _dispatch_state
```

- [ ] **Step 2: Add the loop.** In the dispatch section:

```python
@tasks.loop(time=dt_time(hour=DISPATCH_HOUR, minute=0, tzinfo=TZ))
async def dispatch_daily_loop():
    """Each night at DISPATCH_HOUR (default 21:00 Riyadh): post TOMORROW's cleaning dispatch."""
    await bot.wait_until_ready()
    if not DISPATCH_ENABLED:
        return
    try:
        date_iso = _dispatch_resolve_date("tomorrow")
        st = _dispatch_load_state()
        if st.get("last_auto") == date_iso:      # redeploy near 21:00 shouldn't double-post
            return
        await post_dispatch(date_iso)
        st["last_auto"] = date_iso
        _save_json("dispatch_state.json", st)
    except Exception as e:
        print("dispatch_daily_loop error:", e)
```

- [ ] **Step 3: Start the loop in `on_ready`.** Next to the other `if not X.is_running(): X.start()` lines (~bot.py:55613, beside `oujact_daily_loop`):

```python
    if not dispatch_daily_loop.is_running():
        dispatch_daily_loop.start()      # 21:00: WhatsApp cleaning dispatch for tomorrow
```

- [ ] **Step 4: Verify it compiles.**

Run: `cd /Users/faisalouja/Ouja-Turnover && rm -rf __pycache__ && python3 -m py_compile bot.py`
Expected: clean compile.

- [ ] **Step 5: Commit.**

```bash
git add bot.py
git commit -m "feat(dispatch): nightly 9PM auto-post loop (tomorrow) with idempotency guard"
```

---

## Task 9: `!ouja dispatch` command

**Files:**
- Modify: `bot.py` — near the other `@bot.command`s (~52942).

- [ ] **Step 1: Add the command.** Near `cmd_deepclean_resume` (~bot.py:52942):

```python
@bot.command(name="dispatch", aliases=["إرسال", "ارسال", "توزيع"])
async def cmd_dispatch(ctx, when: str = None):
    """!ouja dispatch [today|tomorrow|YYYY-MM-DD] — post the cleaning dispatch now (admins only).
    Default: today's list before noon, tomorrow's after noon."""
    if not _can_delete_channels(ctx.author):
        await ctx.reply("🚫 هذا الأمر للإدارة فقط.")
        return
    date_iso = _dispatch_resolve_date(when)
    await post_dispatch(date_iso)
    await ctx.reply(f"✅ نشرت دِسباتش التنظيف لتاريخ {_dispatch_fmt_date(date_iso)} في #{DISPATCH_CHANNEL}.")
```

- [ ] **Step 2: Verify it compiles.**

Run: `cd /Users/faisalouja/Ouja-Turnover && rm -rf __pycache__ && python3 -m py_compile bot.py`
Expected: clean compile.

- [ ] **Step 3: Commit.**

```bash
git add bot.py
git commit -m "feat(dispatch): !ouja dispatch command (smart day + override)"
```

---

## Task 10: Optional crew phone number (backend)

**Files:**
- Modify: `bot.py` — `_ct_team_view` (~736), `_api_cleaning_teams` POST (~43765).

- [ ] **Step 1: Expose `phone` in `_ct_team_view`.** Change (~bot.py:736):

```python
def _ct_team_view(t):
    lids = _ct_team_lids(t["id"])
    return {"id": t["id"], "name": t.get("name", ""), "token": t.get("token", ""),
            "phone": t.get("phone", ""),
            "link": "/oujact-route?token=" + (t.get("token") or ""),
            "apartments": len(lids), "lids": sorted(lids)}
```

- [ ] **Step 2: Persist `phone` on create + edit in `_api_cleaning_teams`.** In the rename/edit branch (~bot.py:43779) add a phone line, and add `phone` to the create dict (~bot.py:43787):

```python
    if tid and tid in _cleaning_teams:
        if b.get("regen"):
            _cleaning_teams[tid]["token"] = _ct_new_token()
        if (b.get("name") or "").strip():
            _cleaning_teams[tid]["name"] = b["name"].strip()[:60]
        if "phone" in b:
            _cleaning_teams[tid]["phone"] = (b.get("phone") or "").strip()[:20]
        _ct_save()
        return _json({"ok": True, "team": _ct_team_view(_cleaning_teams[tid])})
    name = (b.get("name") or "").strip() or ("فريق " + str(len(_cleaning_teams) + 1))
    nid = _ct_new_id()
    _cleaning_teams[nid] = {"id": nid, "name": name[:60], "token": _ct_new_token(),
                            "phone": (b.get("phone") or "").strip()[:20], "created_at": _ct_now()}
    _ct_save()
    return _json({"ok": True, "team": _ct_team_view(_cleaning_teams[nid])})
```

- [ ] **Step 3: Verify it compiles.**

Run: `cd /Users/faisalouja/Ouja-Turnover && rm -rf __pycache__ && python3 -m py_compile bot.py`
Expected: clean compile.

- [ ] **Step 4: Commit.**

```bash
git add bot.py
git commit -m "feat(dispatch): optional crew WhatsApp phone (backend)"
```

---

## Task 11: Crew phone input in the dashboard

**Files:**
- Modify: `bot.py` — `DASHBOARD_HTML` JS: team card (~25231) + a `ctSetPhone` fn (~25258).

⚠️ **`DASHBOARD_HTML` trap:** it is a normal (non-raw) triple-quoted Python string. Do **NOT**
put any backslash escape (`\n`, `\t`, …) inside the JS you add — Python eats it and kills the
login. Build strings with `String.fromCharCode(10)` if a newline is ever needed (not needed here).

- [ ] **Step 1: Add a phone button to the team card header.** In `renderCleanTeams` where the
action buttons render (~bot.py:25231), add a button alongside rename/regen/delete:

```javascript
'<button class="btn ghost sm" onclick="ctSetPhone(\''+t.id+'\')">☎️ '+(t.phone?('واتساب: '+t.phone):'أضف رقم واتساب')+'</button>'
```

- [ ] **Step 2: Add the `ctSetPhone` function.** Next to `ctRename`/`ctRegen` (~bot.py:25259):

```javascript
async function ctSetPhone(id){ var p=prompt('رقم واتساب الفريق (مثال 0501234567، اتركه فاضي للإلغاء):'); if(p===null) return; await post('/api/cleaning/teams',{id:id,phone:p}); loadCleanTeams(); }
```

- [ ] **Step 3: Verify the embedded JS still parses (CRITICAL — a bad token kills login).**

Run:
```bash
cd /Users/faisalouja/Ouja-Turnover && python3 -c "
import bot, re
try:
    import esprima
    for js in re.findall(r'<script>(.*?)</script>', bot.DASHBOARD_HTML, re.S):
        esprima.parseScript(js)
    print('esprima OK')
except ImportError:
    print('esprima not installed; run: pip install esprima')
"
```
Expected: `esprima OK` (if esprima missing, `pip install esprima` first — pure-Python, offline).

- [ ] **Step 4: Verify it compiles + brace/paren/backtick balance of DASHBOARD_HTML.**

Run: `cd /Users/faisalouja/Ouja-Turnover && rm -rf __pycache__ && python3 -m py_compile bot.py`
Expected: clean compile.

- [ ] **Step 5: Commit.**

```bash
git add bot.py
git commit -m "feat(dispatch): crew WhatsApp phone input in dashboard"
```

---

## Task 12: Full verification + docs + memory

**Files:**
- Modify: `MEMORY.md` + new `memory/*.md`; possibly `CLAUDE.md` note.

- [ ] **Step 1: Run the FULL CLAUDE.md verification routine.**

```bash
cd /Users/faisalouja/Ouja-Turnover
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py schedule/*.py 2>&1 | grep -v "imported but unused" || true
node --check finance/static/erp.js
python3 -m unittest discover -s tests -p "test_*.py"
```
Expected: compile clean; pyflakes shows nothing new for the dispatch code; `node --check` clean; the whole test suite (incl. `tests.test_dispatch`) passes.

- [ ] **Step 2: Esprima-parse the served dashboard JS again (belt-and-suspenders).**

Run the Step-3 esprima snippet from Task 11. Expected: `esprima OK`.

- [ ] **Step 3: Manual smoke (documented for the operator, not automated):**
  - Set `DISPATCH_DRYRUN=1`, run `!ouja dispatch tomorrow` in Discord → confirm the log prints per-crew counts and any unassigned bucket, and NOTHING posts.
  - Set `PUBLIC_BASE_URL`, flip `DISPATCH_DRYRUN=0`, run `!ouja dispatch` → confirm the `dispatch` channel gets one embed per crew with a working «📲 أرسل عبر واتساب» button that opens WhatsApp with the pre-filled Arabic message.
  - Add a crew phone in the dashboard → the button now opens that crew's chat directly.

- [ ] **Step 4: Write the memory file.** Create `memory/cleaning-dispatch-whatsapp.md` (frontmatter + body per the memory format) summarizing: new `dispatch` Discord channel; nightly 21:00 → tomorrow; `!ouja dispatch` smart day; `/d/{token}` redirect; optional crew `phone`; env vars `DISPATCH_ENABLED/CHANNEL/HOUR/DRYRUN` + needs `PUBLIC_BASE_URL`; tests in `tests/test_dispatch.py`. Add a one-line pointer in `MEMORY.md`.

- [ ] **Step 5: Final commit + push (triggers Railway deploy).**

```bash
git add -A
git commit -m "docs(dispatch): memory + notes for Cleaning Dispatch to WhatsApp"
git push
```
Then tell the owner in plain language: new `dispatch` channel, posts nightly at 9PM for tomorrow, tap the green button to WhatsApp each crew, `!ouja dispatch` for on-demand, add crew phone numbers in the dashboard for one-tap. Start with `DISPATCH_DRYRUN=1` to preview.

---

## Self-review notes (author)

- **Spec coverage:** delivery=Discord `dispatch` (T6), tap-to-send button (T6/T7), per-crew grouping (T5), nightly 21:00→tomorrow (T8), `!ouja dispatch` smart-day + override (T2/T9), ops-owner on card only (T3 `_dispatch_embed_lines`), optional crew phone (T10/T11), safety net (T5/T6), no auto-send / no data-model change (respected), env vars + `PUBLIC_BASE_URL` graceful fallback (T0/T6), tests (T1–T5, T12). All spec sections map to a task.
- **Placeholder scan:** none — every code step has complete code; test steps have full assertions.
- **Type consistency:** `_dispatch_jobs` returns `{teams: {tid:[items]}, unassigned:[items], date}`; consumed identically in `post_dispatch` (T6) and `_handle_d_redirect` (T7). `_dispatch_wa_text`/`_dispatch_embed_lines`/`_wa_send_url`/`_dispatch_resolve_date` signatures match every call site. Item keys (`lid, listing, checkout, checkout_date, checkin_today, checkin_dt, early_departure`) match `fetch_oujact_turnovers` (bot.py:1054-1064).
