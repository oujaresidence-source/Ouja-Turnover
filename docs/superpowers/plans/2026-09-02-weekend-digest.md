# Weekend Digest «وش صاير بالرياض» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `digest/` package that builds, verifies, renders and posts the weekly Thu–Sat Riyadh digest to Discord with approve / alternates / rephrase / drop / rebuild buttons, with nothing published without the owner's tap.

**Architecture:** Pure core (schema, guard, voice, dates, rank, render, notify) with all I/O behind `digest/host.py` DI mirroring `studio/host.py`; `brain.db` tables via `brain.db.connect()`; collectors tested against saved HTML fixtures; Chromium render to 810×1440 pt PDF + 1080×1920 PNG locked by a three-part frozen fingerprint; five additive insertions into `bot.py`.

**Tech Stack:** Python 3.9-compatible (local) / 3.13 (Railway), stdlib `html.parser`, `playwright~=1.61`, `PyMuPDF`, `Pillow`, `segno` (new), discord.py `ui.View`, aiohttp.

**Spec:** `docs/superpowers/specs/2026-09-02-weekend-digest-design.md`

## Global Constraints

- Work only in the worktree `/Users/faisalouja/ouja-wt-digest` on branch `feat/weekend-digest` (from `origin/main` @ 0e4e64f). Never the parked checkout on `feat/musaed-v2`.
- Python 3.9 syntax floor: no `match`, no `X | Y` type unions, no parenthesised multi-context `with`.
- No `requests`/`urllib`/`socket` import anywhere under `digest/` except `digest/net_live.py`.
- `digest/page.py`, `digest/notify.py`, `digest/render/html.py`: **zero backslash characters** in the file (the DASHBOARD_HTML trap). Use `chr(10)` / `String.fromCharCode(10)`.
- Colours only from `digest/render/tokens.py`. Titles ≤ 4 words, subs ≤ 10 words. Arabic-Indic numerals in prose, Western in tables. Banned phrases per `digest/voice.py: BANNED`.
- `DIGEST_DRYRUN=1` default. Never push to GitHub without the owner's explicit approval. Each phase ends at an approval stop; commit locally per task.
- Verification after every phase: `python3 -W error::SyntaxWarning -m py_compile bot.py && python3 -m pyflakes digest && node --check finance/static/erp.js && python3 -m unittest discover -s tests -p "test_*.py"`. Baseline on main is 3,811 tests with 2 pre-existing failures in `test_ops_capture.TestBackfill` (not ours; do not fix).
- Run tests with `python3 -m unittest tests.test_digest_x -v` (no pytest here). Never pipe the suite through `tail` (hides the exit code).

---

## Phase P1 — the pure core: dates, schedule, schema, voice, guard

### Task 1: package skeleton + host + db

**Files:**
- Create: `digest/__init__.py`, `digest/host.py`, `digest/db.py`
- Test: `tests/test_digest_db.py`

**Interfaces:**
- Produces: `digest.wire(caps) -> HOST`, `digest.register_routes(app)` (routes added in Task 15; until then `register_routes` is a no-op that imports lazily), `HOST.require(name)`, `db.q/q1/execute`, `db.reset_init_cache()`, `db.open_issue(week_of, issue_no) -> id`, `db.issue_for_week(week_of) -> row|None`, `db.set_issue(id, **cols)`, `db.add_candidates(issue_id, section, slot, ranked:list)`, `db.candidates(issue_id, section, slot) -> [row]`, `db.add_ruling(issue_id, who, action, section=None, slot=None, detail=None)`, `db.rulings(limit=500) -> [row]`, `db.issue_by_msg(msg_id) -> row|None`, `db.recent_issue_urls(n=6) -> set`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_digest_db.py
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain import db as bdb
from digest import db as ddb

class DigestDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="digesttest_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        ddb.reset_init_cache()

    def setUp(self):
        for t in ("digest_rulings", "digest_candidates", "digest_items", "digest_issues"):
            ddb.execute("DELETE FROM " + t)

    def test_issue_is_unique_per_week(self):
        a = ddb.open_issue("2026-09-03", 12)
        self.assertEqual(ddb.issue_for_week("2026-09-03")["id"], a)
        with self.assertRaises(Exception):
            ddb.open_issue("2026-09-03", 13)

    def test_candidates_round_trip_ranked(self):
        iid = ddb.open_issue("2026-09-03", 12)
        ddb.add_candidates(iid, "events", 0, [{"ttl": "أ", "score": 0.9}, {"ttl": "ب", "score": 0.7}])
        rows = ddb.candidates(iid, "events", 0)
        self.assertEqual([r["rank"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["cand"]["ttl"], "أ")

    def test_ruling_is_recorded_with_who_and_action(self):
        iid = ddb.open_issue("2026-09-03", 12)
        ddb.add_ruling(iid, "faisal", "drop", section="events", slot=1, detail={"why": "x"})
        r = ddb.rulings()[0]
        self.assertEqual((r["who"], r["action"], r["section"], r["slot"]), ("faisal", "drop", "events", 1))

    def test_issue_by_msg(self):
        iid = ddb.open_issue("2026-09-03", 12)
        ddb.set_issue(iid, msg_id=555, status="preview")
        self.assertEqual(ddb.issue_by_msg(555)["id"], iid)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails** — `python3 -m unittest tests.test_digest_db -v` → ImportError.

- [ ] **Step 3: Implement**

`digest/host.py` — copy `studio/host.py` verbatim, replace the attribute list with the spec §2.1 list (`state_path, load_json, save_json, dash_auth, req_role, json_response, web, claude_json, claude_search, http, listings, public_base, model_fast, model_premium, tz, now`), message `"digest used '%s' before digest.wire()"`.

`digest/db.py` — copy `studio/db.py`'s header, `_ensure`, `reset_init_cache`, `q/q1/execute` verbatim; SCHEMA:

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS digest_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_of TEXT NOT NULL UNIQUE, issue_no INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'building',
  payload TEXT NOT NULL DEFAULT '', html_sha TEXT NOT NULL DEFAULT '',
  msg_id INTEGER, channel_id INTEGER, rebuilds INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, published_at TEXT);
CREATE TABLE IF NOT EXISTS digest_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER NOT NULL,
  section TEXT NOT NULL, slot INTEGER NOT NULL, item TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'primary');
CREATE TABLE IF NOT EXISTS digest_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER NOT NULL,
  section TEXT NOT NULL, slot INTEGER NOT NULL, rank INTEGER NOT NULL,
  score REAL NOT NULL DEFAULT 0, cand TEXT NOT NULL, reasons TEXT NOT NULL DEFAULT '[]',
  used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS digest_rulings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, issue_id INTEGER NOT NULL,
  ts TEXT NOT NULL, who TEXT NOT NULL, action TEXT NOT NULL,
  section TEXT, slot INTEGER, detail TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS ix_digest_cand ON digest_candidates(issue_id, section, slot, rank);
"""
_MIGRATIONS = ()
```
Typed helpers as in Interfaces; JSON columns via `json.dumps(..., ensure_ascii=False)` and re-hydrated on read; `_now_iso()` uses `HOST.now` when wired else `datetime.now(timezone.utc)`.

`digest/__init__.py`:
```python
from .host import HOST, wire as _wire_host
from . import db  # noqa: F401
def bootstrap():
    try:
        db._ensure(); print("[digest] db ready")
    except Exception as e:
        print("[digest] bootstrap error:", e)
def wire(caps):
    _wire_host(caps); bootstrap(); return HOST
def register_routes(app):
    from . import routes
    routes.register(app)
```

- [ ] **Step 4: Run to verify it passes.**
- [ ] **Step 5: Commit** — `git add digest/__init__.py digest/host.py digest/db.py tests/test_digest_db.py && git commit -m "digest: package skeleton, host DI contract, brain.db tables"`

### Task 2: dates

**Files:** Create `digest/dates.py`; Test `tests/test_digest_dates.py`

**Interfaces:** Produces `Week` (namedtuple `thu, fri, sat, iso, label_ar`), `week_for(now: datetime) -> Week`, `label_ar(week) -> str`, `AR_MONTHS` (1..12 → «يناير»…), `ar_digits(s) -> str`.

- [ ] **Step 1: Failing test** — frozen clock for every weekday in `Asia/Riyadh`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from digest import dates
TZ = ZoneInfo("Asia/Riyadh")
class WeekFor(unittest.TestCase):
    def test_every_weekday_maps_to_the_right_thursday(self):
        # 2026-09-03 is a Thursday. Mon 08-31 .. Wed 09-02 -> that Thursday;
        # Thu 09-03, Fri 09-04, Sat 09-05 -> the SAME weekend (already in progress);
        # Sun 09-06 -> 09-10.
        cases = {"2026-08-31": "2026-09-03", "2026-09-01": "2026-09-03", "2026-09-02": "2026-09-03",
                 "2026-09-03": "2026-09-03", "2026-09-04": "2026-09-03", "2026-09-05": "2026-09-03",
                 "2026-09-06": "2026-09-10"}
        for today, thu in cases.items():
            with self.subTest(today=today):
                now = datetime.fromisoformat(today + "T13:00:00").replace(tzinfo=TZ)
                self.assertEqual(dates.week_for(now).iso, thu)
    def test_label_same_month_and_crossing(self):
        w = dates.week_for(datetime(2026, 9, 2, 13, tzinfo=TZ))
        self.assertEqual(w.label_ar, "٣–٥ سبتمبر")
        w2 = dates.week_for(datetime(2026, 10, 28, 13, tzinfo=TZ))   # Thu 10-29 .. Sat 10-31
        self.assertEqual(w2.label_ar, "٢٩–٣١ أكتوبر")
        w3 = dates.week_for(datetime(2026, 12, 30, 13, tzinfo=TZ))   # Thu 12-31 .. Sat 01-02
        self.assertEqual(w3.label_ar, "٣١ ديسمبر – ٢ يناير")
    def test_naive_datetime_is_refused(self):
        with self.assertRaises(ValueError):
            dates.week_for(datetime(2026, 9, 2, 13))
```

- [ ] **Step 2: Run, expect ImportError.**
- [ ] **Step 3: Implement**

```python
from collections import namedtuple
from datetime import timedelta
Week = namedtuple("Week", "thu fri sat iso label_ar")
AR_MONTHS = {1:"يناير",2:"فبراير",3:"مارس",4:"أبريل",5:"مايو",6:"يونيو",7:"يوليو",
             8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"}
_AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
def ar_digits(s): return str(s).translate(_AR)
def week_for(now):
    if now.tzinfo is None: raise ValueError("digest.dates.week_for needs a tz-aware datetime")
    d = now.date(); wd = d.weekday()          # Mon=0 .. Thu=3, Fri=4, Sat=5, Sun=6
    if wd in (3, 4, 5): thu = d - timedelta(days=wd - 3)
    else: thu = d + timedelta(days=(3 - wd) % 7)
    fri, sat = thu + timedelta(days=1), thu + timedelta(days=2)
    return Week(thu, fri, sat, thu.isoformat(), label_ar((thu, sat)))
def label_ar(span):
    a, b = span[0], span[-1]
    if a.month == b.month: return "%s–%s %s" % (ar_digits(a.day), ar_digits(b.day), AR_MONTHS[a.month])
    return "%s %s – %s %s" % (ar_digits(a.day), AR_MONTHS[a.month], ar_digits(b.day), AR_MONTHS[b.month])
```
(`week_for` returns `Week(..., label_ar((thu, sat)))` — `label_ar` accepts a Week or a pair.)

- [ ] **Step 4: Run, passes.** - [ ] **Step 5: Commit** `digest: dates — next Thu–Sat in Riyadh, frozen-clock tests`.

### Task 3: schedule decision (before the loop exists)

**Files:** Create `digest/schedule.py`; Test `tests/test_digest_schedule.py`

**Interfaces:** `should_fire(now, day=2, hour=13, existing_week_of=None) -> bool` — pure.

- [ ] **Step 1: Failing test**

```python
class ShouldFire(unittest.TestCase):
    def test_fires_only_wednesday_13(self):
        for day in range(7):
            for hour in range(24):
                now = datetime(2026, 8, 31 + 0, 0, tzinfo=TZ) + timedelta(days=day, hours=hour)
                want = (now.weekday() == 2 and now.hour == 13)
                self.assertEqual(schedule.should_fire(now), want, now.isoformat())
    def test_latch_blocks_a_second_run_same_week(self):
        now = datetime(2026, 9, 2, 13, 25, tzinfo=TZ)
        self.assertTrue(schedule.should_fire(now, existing_week_of=None))
        self.assertFalse(schedule.should_fire(now, existing_week_of="2026-09-03"))
        self.assertTrue(schedule.should_fire(now, existing_week_of="2026-08-27"))
    def test_env_day_hour_respected(self):
        now = datetime(2026, 9, 3, 15, tzinfo=TZ)   # Thursday 15:00
        self.assertTrue(schedule.should_fire(now, day=3, hour=15))
        self.assertFalse(schedule.should_fire(now, day=2, hour=13))
```
- [ ] **Step 3: Implement** — `from .dates import week_for`; `return now.weekday()==day and now.hour==hour and week_for(now).iso != (existing_week_of or "")`.
- [ ] **Step 5: Commit** `digest: schedule.should_fire — Wednesday-only, persisted latch (pure)`.

### Task 4: schema

**Files:** Create `digest/schema.py`; Test `tests/test_digest_schema.py`

**Interfaces:** `SECTIONS = {"events": {"title":"فعاليات ومعارض","min":2,"max":4}, "cinema": {"title":"جديد في السينما","min":0,"max":3,"exact":(0,3)}, "worth": {"title":"يستاهل الزيارة","min":0,"max":1}, "fixtures": {"title":"مباريات الأسبوع","min":0,"max":6}}`, `layout_for(section, n) -> str`, `validate(payload) -> [str]`, `assert_valid(payload)` (raises `SchemaError(ValueError)`), `word_count(s) -> int`, `empty_payload(week, issue_no, generated_at) -> dict`.

- [ ] **Step 1: Failing tests** (one per rule): good payload → `[]`; events with 1 item → error mentions `events`; cinema with 2 → error; title of 5 words → error naming the title; sub of 11 → error; url not `https://` → error; url not in `verified_urls` → error; `confidence 0.6` on a primary → error; `day` not in `thu|fri|sat` → error; `layout_for("events", 2) == "g2h"`, `3 → "g3v"`, `4 → "g2"`, `("cinema", 3) == "g3"`, `("worth", 1) == "g1"`, `("fixtures", n) == "fix"`; fixture item needs `home, away, when`.
  Put the good payload in `tests/fixtures/digest/payload_good.json` (hand-written now; also the frozen reference later).
- [ ] **Step 3: Implement** — plain loops over `payload["sections"]`, `word_count = len([w for w in re.split(r"\s+", s.strip()) if w])`, dates check `item["day"] in ("thu","fri","sat")`, `verified = set(payload.get("verified_urls", []))`.
- [ ] **Step 5: Commit** `digest: schema — the frozen content contract, validated`.

### Task 5: voice (pure half)

**Files:** Create `digest/voice.py`; Test `tests/test_digest_voice.py`

**Interfaces:** `BANNED: list[re.Pattern]`, `slop_hits(text) -> [str]`, `to_arabic_indic(text) -> str` (digits only; leaves `dir="ltr"` spans alone — takes already-extracted text), `title_ok(t)`, `sub_ok(s)`, `western_digits_in_prose(text) -> [str]`, `polish(item, kind, seed=0) -> item` (model half — Task 12), `PROMPT_SYSTEM` string.

- [ ] **Step 1: Failing tests** — each banned phrase from the brief §3.4 hits (parametrised subTests incl. «استمتع بالأجواء» via the `استمتع بـ` prefix pattern and «اكتشفوا»); a clean Najdi line has zero hits; `to_arabic_indic("الجمعة 9:00م") == "الجمعة ٩:٠٠م"`; `western_digits_in_prose("٣ سبتمبر")==[]` and `("3 سبتمبر")==["3"]`.
- [ ] **Step 3: Implement** — `BANNED = [re.compile(p) for p in ("اكتشف", "لا تفو+ت", "تجربة استثنائية", "لا مثيل لها", "وجهتك المثالية", "أجواء ساحرة", "على ب[عُ]د خطوات", "انغمس", "استمتع ب", "نقلة نوعية", "لا ي[فُ]و+ت", "سحر")]`.
- [ ] **Step 5: Commit** `digest: voice denylist + Arabic-Indic prose numerals`.

### Task 6: guard

**Files:** Create `digest/guard.py`; Test `tests/test_digest_guard.py`

**Interfaces:** `class DigestError(AssertionError)`, `scan(html, payload, week, now) -> [str]`, `assert_clean(html, payload, week, now)`. Imports `from cp.guard import fold_digits, visible_text`. `_prose_text(html)` extracts text of elements with classes `claim|sub|foot|ttl` and `<p>` via regex (no bs4).

- [ ] **Step 1: Failing tests** — nine tests, one per abort in spec §6 plus the good one. Build HTML with a tiny helper `_html(**kw)` in the test that wraps strings in `<div class="claim">…</div>`, `<td>…</td>`, `<a href=…>`. Examples:

```python
def test_stale_source_aborts(self):
    p = good(); p["sections"][0]["items"][0]["source"]["fetched_at"] = "2026-08-20T10:00:00+03:00"
    self.assertTrue(any("fetched_at" in e for e in guard.scan(HTML_OK, p, WEEK, NOW)))
def test_date_outside_window_aborts(self):
    self.assertTrue(any("خارج" in e or "window" in e for e in guard.scan(_html(claim="الأحد ٦ سبتمبر"), good(), WEEK, NOW)))
def test_western_digit_in_prose_aborts_but_table_is_fine(self):
    self.assertTrue(guard.scan(_html(claim="3 أفلام"), good(), WEEK, NOW))
    self.assertEqual([], guard.scan(_html(td="19,58"), good(), WEEK, NOW))
def test_unverified_url_aborts(self):
    self.assertTrue(guard.scan(_html(href="https://evil.example/x"), good(), WEEK, NOW))
def test_good_payload_passes(self):
    self.assertEqual([], guard.scan(HTML_OK, good(), WEEK, NOW))
```
Date detection: fold digits, regex `(\d{1,2})\s+(يناير|…|ديسمبر)` and `(الأحد|الاثنين|الثلاثاء|الأربعاء)` weekday names → abort; `الخميس|الجمعة|السبت` allowed.
- [ ] **Step 5: Commit** `digest: guard — eight abort conditions, cp.guard helpers reused`.

**→ P1 approval stop.** Report: files, line counts, test count delta, how to undo (`git revert` of the P1 commits or `git branch -D feat/weekend-digest`).

---

## Phase P2 — collectors on fixtures

### Task 7: net_live + links + fixtures harness

**Files:** Create `digest/net_live.py`, `digest/links.py`, `tests/fixtures/digest/README.md`, `tests/fixtures/digest/_fake_http.py`; Test `tests/test_digest_links.py`, `tests/test_digest_nonetwork.py` (first half)

**Interfaces:** `net_live.get_text/head/get_bytes` (spec §2.2). `links.verify(urls, http) -> dict[url -> final]`, `links.provenance_ok(url, seen) -> bool`, `links.same_origin(a, b) -> bool`. `_fake_http.FakeHttp(pages: dict[url -> (status, ctype, body)], heads=None)` with the same three methods, recording `.calls`.

- [ ] **Step 1: Failing tests** — `verify` keeps a 200 text/html, drops 404, drops 200 `application/pdf`, stores the redirect's final URL, HEAD 405 falls back to ranged GET; `provenance_ok` false for a URL never seen. `test_digest_nonetwork.py::test_only_net_live_touches_the_network` walks `digest/**/*.py` and asserts the four forbidden module names appear only in `net_live.py`.
- [ ] **Step 3: Implement** `net_live` with `requests.Session`, UA `OujaDigest/1.0 (+https://oujares.com)`, `allow_redirects=True`, 3 tries on 429/5xx (`time.sleep(1.5*n)`), `head()` → on 405/403 do `get(headers={"Range":"bytes=0-0"}, stream=True)` and close.
- [ ] **Step 5: Commit** `digest: net adapter (the only network file) + link verification`.

### Task 8: platinumlist collector

**Files:** Create `digest/collect/__init__.py`, `digest/collect/base.py` (`Candidate` factory `make(section, ttl, sub, chip, url, day, source_name, source_url, fetched_at, tags, og=None, raw_conf=1.0)`), `digest/collect/platinumlist.py`; fixture `tests/fixtures/digest/platinumlist-calendar-2026-09.html`; Test `tests/test_digest_collect_platinumlist.py`

**Interfaces:** `fetch(week, http, now) -> [Candidate]`; `parse(html, week, now, page_url) -> [Candidate]` (pure — this is what the fixture test hits); `category_of(title, tags) -> str` in `base.py` (exhibition/museum/season/family/concert/market/b2b/other by keyword lists, Arabic + English).

- [ ] **Step 0: Fetch the fixture ONCE** with `python3 -c "from digest import net_live; ..."` from the worktree and save it. If the page is a JS shell (no day headings in the HTML), record that in `tests/fixtures/digest/README.md` and switch this collector's primary to `claude_search` with `allowed_domains=["riyadh.platinumlist.net"]` (Task 11's shape). Report the outcome to the owner in the P2 report.
- [ ] **Step 1: Failing test** — parse the fixture: ≥ 1 candidate falls inside the week, each has `day ∈ {thu,fri,sat}`, `url` starts with `https://riyadh.platinumlist.net/`, `source.name == "Platinumlist"`, `chip` non-empty, `category_of` returns a known key; and a candidate dated outside the week is **not** returned.
- [ ] **Step 3: Implement** with `html.parser.HTMLParser` subclass collecting `(date_heading, anchor_href, anchor_text, venue_text)`.
- [ ] **Step 5: Commit**.

### Task 9: VOX cinema collector

Same shape as Task 8: fixtures `vox-comingsoon-<date>.html`, `vox-whatson-<date>.html`; `parse_comingsoon(html, week, now)` keeps films with `Release Date` ∈ [thu−6d, sat]; `sub` = `"%s · %s" % (ar_date, genre_ar)` via a small EN→AR genre map (`Action`→«أكشن», `Crime`→«جريمة», `Comedy`→«كوميدي», `Drama`→«دراما», `Horror`→«رعب», `Animation`→«أنيميشن», `Family`→«عائلي», `Thriller`→«إثارة»); `chip="سينما"`; `art_hint=None` (generated only). Test asserts exactly the films in-window, the sub format matches `^[٠-٩]{1,2} \S+ · .+$`, and that no `og` hint is emitted.

### Task 10: jdwel fixtures collector

Fixture `jdwel-fixtures-2026-27.html`; `parse(html, week) -> [fixture]` with `{"home","away","when","kickoff_iso","round","url"}`; `RIYADH_CLUBS = ("الهلال","النصر","الشباب","الرياض","الدرعية","الفيصلي")`; keep matches with either club in `RIYADH_CLUBS` **or** national team / continental tag; `when = "%s %s" % (AR_DAY[wd], ar_time)` with `ar_time` like «٩:٠٠م» (`٥:٣٠ع` is *not* used: keep «م» for PM and «ص» for AM). `cross_check(fixture, other) -> bool` compares folded home/away/kickoff; disagreement drops both. Tests: Riyadh filter, time format regex `^[٠-٩]{1,2}:[٠-٩]{2}[صم]$`, cross-check drop.

### Task 11: worth + secondary search + places + confidence

**Files:** `digest/collect/worth.py`, `digest/collect/search_secondary.py`, `digest/places.py`, `digest/data/venues.json`, `digest/data/worth.json`; Test `tests/test_digest_places.py`, `tests/test_digest_collect_secondary.py`, `tests/test_digest_confidence.py`

**Interfaces:** `places.district_for(venue, address="") -> str` (default «الرياض»), `places.coords_for(venue) -> (lat,lng)|None`, `places.COMPOUNDS = {"Al Majdiah": (lat,lng), "Gadh33": …, "Gadh44": …, "Dyar20": …, "Hue": …, "Al Ajlan": …}` (coordinates from `coverage_study/seed_locations.json` by slug — read at import through a tiny loader with a hard-coded fallback), `places.km_to_nearest_compound(latlng) -> float`. `search_secondary.fetch(section, week, search, allowed_domains) -> [Candidate]` — calls `HOST.claude_search` with a JSON-only system prompt; keeps an item only if its `url` ∈ returned url list (provenance). `confidence(cand, agreement, now) -> float` in `collect/base.py` (spec §5.4). `worth.fetch(week, http, load_json)` reads `$STATE_DIR/digest/worth.json` if present else `digest/data/worth.json`.

Tests: district table hits (Boulevard→حطين, unknown→الرياض); the six compounds have coordinates; secondary drops an item whose URL was not opened; confidence primary+agreement+fresh = 1.0, search-only stale-6-days ≈ 0.55+0.15+0.02.

**→ P2 approval stop** (report includes the live-fetch outcome per source and which fixtures were saved).

---

## Phase P3 — render

### Task 12: fonts + tokens

**Files:** copy the five woff2 files into `fonts/` (names in spec §3.2); Create `digest/render/__init__.py`, `tokens.py`, `fonts.py`; Test `tests/test_digest_fonts.py`

**Interfaces:** `tokens.TOKENS`, `tokens.css_root() -> ":root{--ink:#0B1A2E;…}"`, `tokens.PAGE_W_PT/PAGE_H_PT/STORY_W/STORY_H`; `fonts.FACES = [("Thmanyah Serif Display", 700, "ThmanyahSerifDisplay-Bold.woff2"), (…, 900, "…-Black.woff2"), ("Thmanyah Sans", 400, "ThmanyahSans-Regular.woff2"), (…,500,…), (…,700,…)]`, `fonts.font_faces() -> str` (`file://` urls), `fonts.path_for(file) -> Path`.

Test: every declared face resolves to a file that `is_file()` and starts with `b"wOF2"`; md5 of each copied file equals the `monthly_public/static/fonts/` original; `font_faces()` contains 5 `@font-face`.

- [ ] Commit `digest: Thmanyah faces (5) under fonts/, tokens single source`.

### Task 13: html.py + audit.py + build.py

**Files:** Create `digest/render/html.py`, `audit.py`, `build.py`, `digest/render/reference_payload.py` (= the good payload from Task 4 with `art.kind="generated"` everywhere and a fixed `generated_at`); Test `tests/test_digest_render.py`, `tests/test_digest_nonetwork.py` (second half), `tests/test_digest_page_geometry.py` (skips without Chromium)

**Interfaces:** `html.build_pages(payload, art_map) -> str`, `html.build_story(payload, art_map) -> str`, `html.qr_svg(url) -> str` (segno), `audit.audit_html(html) -> [str]`, `audit.assert_clean(html)`, `build.render(payload, art_map, out_dir, issue_no) -> {"pdf","png","json","html","story_html"}`.

Tests (offline): `build_pages` output contains no hex colour outside `TOKENS`; contains no `box-shadow`, no `left:`/`right:`/`padding-left`/`padding-right`/`margin-left`/`margin-right` in CSS; every page has exactly one `.eyebrow` and one `.foot`; a 2-item events payload uses `g2h` and a 3-item one `g3v`; the cinema page is absent when cinema is empty; zero backslashes in `html.py`; `qr_svg` returns an `<svg` string and is deterministic. Nonetwork: monkey-patch `socket.socket` to raise, import `digest.render.html`, `digest.notify`, build pages — passes. Geometry (Chromium): `render()` writes a PDF whose page 1 rect is `810×1440` (PyMuPDF), a PNG of exactly `1080×1920` (Pillow), and `audit.audit_html` returns `[]` for the reference.

Implementation notes: page.pdf kwargs `width="810pt", height="1440pt", print_background=True, prefer_css_page_size=True, margin={"top":"0","bottom":"0","left":"0","right":"0"}`; story via `context = browser.new_context(viewport={"width":540,"height":960}, device_scale_factor=2)` then `page.screenshot(path=png, type="png")`. Chromium pinned to a 1-worker `ThreadPoolExecutor` like `ouja_render.py` (module-level `_pool`, `_launch()` per build, closed in `finally`).

### Task 14: frozen fingerprint

**Files:** Create `digest/render/test_render_frozen.py`, `digest/render/golden_fingerprint.json`, `digest/render/golden/page-N.png`; Test `tests/test_digest_frozen.py`

`fingerprint(pdf_path, html_path) -> {"chromium": ver, "page_count": n, "pages": [{"n","text_md5","layout_md5","pixel_md5"}]}`; `compare(candidate, golden, golden_dir) -> [str]` implementing spec §8.4 (mean-abs-delta via Pillow `ImageChops.difference` → `ImageStat.Stat(...).mean`). `main()` with `--write-golden` flag that **refuses** to run if a golden already exists unless `--i-have-owner-approval` is also passed (and prints the rule). Test skips without Chromium.

**→ P3 approval stop.** Deliverable for the owner: `outputs/digest-preview/digest-0.pdf` and `.png` from the reference payload, sent as files, next to the memo. Golden is written **after** he says it looks right, then committed.

---

## Phase P4 — rank, art, alternates

### Task 15: rank

**Files:** Create `digest/rank.py`; Test `tests/test_digest_rank.py`

**Interfaces:** `score(cand, ctx) -> (float, dict parts)`, `choose(cands_by_section, ctx) -> {"primary": {section: [cand]}, "alternates": {"section.slot": [cand]}}`, `ctx = {"recent_urls": set, "recent_titles": set, "rulings": [row], "compounds": places.COMPOUNDS}`, `DECISION_PRIOR = {"exhibition":.9,"museum":.85,"season":.8,"family":.75,"concert":.7,"market":.6,"other":.4,"b2b":.1}`, `SPREAD_WEIGHT = 0.35`, `owner_history(cand, rulings) -> float` (−0.5 per drop on same district/source/category, +0.25 per approve, clamped to [−1, 1]).

Tests: weights sum to 1 and each part ∈ [0,1] (history ∈ [−1,1]); a b2b conference never beats an exhibition of equal confidence; novelty 0 for a URL in `recent_urls`; **spread**: three Boulevard concerts at 0.9 vs an exhibition (0.8, الدرعية) + market (0.7, العليا) → primaries are one concert + exhibition + market; a district dropped twice in rulings sinks below an otherwise equal candidate; alternates per slot = next 3, none of which equals a primary; stability (equal scores keep order).

### Task 16: art

**Files:** Create `digest/art.py`, `digest/art_generated.py`; Test `tests/test_digest_art.py`

**Interfaces:** `art_generated.svg(seed_text, glyph, kind, w=760, h=760) -> str` (LCG `x = (1103515245*x + 12345) % 2**31` seeded from `int(sha256(seed_text)[:8],16)`, 18 horizontal hairlines with amplitude ≤ 3px, navy field, gold rule, glyph in Serif Display Black — font referenced by family name, so it resolves inside the page), `art.resolve(item, section, issue_no, slot, http, load_owned) -> dict`, `art.og_image_url(html, page_url) -> str|None` (same origin only), `art.thumb_jpeg_b64(bytes) -> str` (Pillow steps from `unit_tiles`).

Tests: same seed → identical SVG, different slot → different; cinema/fixtures never call `http` (FakeHttp `.calls == []`) and always return `generated`; `og` rejected for cross-origin, for `image/*` under 800px (make a 300px PNG with Pillow), and for non-image content-type; fallback order owned→og→generated→none with a `FakeHttp` that 404s the og fetch; a real 900px JPEG passes and its sha256 is stable.

### Task 17: build orchestrator + alternates in db

**Files:** Create `digest/build.py`; Test `tests/test_digest_build.py`

**Interfaces:** `build_issue(now, http, search, load_json, dry_run=True, out_root=None) -> {"issue_id","issue_no","payload","files","dropped","errors"}`; `existing_week_of(now) -> str|None` (the `week_of` of an issue row for this week, else `None`), `already_built(now) -> bool` (= `existing_week_of(now) is not None`); `rebuild(issue_id, ...)` (rate-limited by `rebuilds < 3`); `apply_alternate(issue_id, section, slot, rank)`; `drop_slot(issue_id, section, slot, who)`; `rephrase(issue_id, seed)`; each re-renders via `render.build.render`. CLI: `python3 -m digest.build --dry-run --week 2026-09-03 [--fixtures]` — `--fixtures` wires `FakeHttp` from `tests/fixtures/digest/` so the command works offline from a cold start.

Tests use FakeHttp + a fake `search` returning `(None, [])` + a fake `HOST.claude_json` that echoes copy; assert: a dead link at render time removes the item and appears in `payload["dropped"]`; `already_built` true after one build; `rebuild` refused on the 4th call; `apply_alternate` swaps the item and writes a `digest_rulings` row with action `alt`; a payload that fails the guard leaves the issue in `status="failed"` with `error` set and produces no files.

**→ P4 approval stop.**

---

## Phase P5 — notify, approval, routes, page, bot.py

### Task 18: notify + approval (pure)

**Files:** Create `digest/notify.py`, `digest/approval.py`; Test `tests/test_digest_approval.py`, `tests/test_digest_notify.py`

`notify.build_message(payload, issue_no, dropped, base_url) -> str` (`nl = chr(10)`; sections as lines «🎨 فعاليات: …»; «حذفنا: … — السبب …»; «المصادر: Platinumlist · VOX · jdwel»; ends with the preview link `base_url + "/digest"`). `approval.transition(status, action) -> new_status|None` table: `preview+approve→approved`, `approved→published` only via `mark_published`, `preview+alt/rephrase/drop→preview`, `preview+rebuild→building`, anything on `published` → `None`. `approval.act(issue_id, action, who, section=None, slot=None, rank=None, sender=None) -> dict` calls the build functions and the injected `sender` (a callable recording calls in tests; `None` under dry-run → assert it is never called).

Tests: dry-run inertness — `act(..., sender=recorder)` with `dry_run=True` leaves `recorder.calls == []` and status unchanged; each button's transition; rulings rows written; `build_message` has zero backslashes and contains every primary title.

### Task 19: routes + page

**Files:** Create `digest/routes.py`, `digest/page.py`; Test `tests/test_digest_routes.py`, `tests/test_digest_page.py`

Routes as spec §9.3 with studio's `_safe` wrapper; `page.py` `DIGEST_PAGE_HTML` zero-backslash; test esprima-parses every `<script>`, checks brace/paren/backtick balance, asserts each `/api/digest/*` string in the page appears in `inspect.getsource(routes.register)`; a `_FakeRequest` (from `tests/test_kb_public.py`) drives `status` and `act` handlers with `HOST.dash_auth = lambda r: True/False` → 200 / 401.

### Task 20: bot.py insertions + DigestView

**Files:** Modify `bot.py` at (re-grep first): ~298 import block; ~6590 env block; ~7626 region (add `DigestView` after `DecorOrderView`'s neighbourhood); ~8044 add `digest_loop` after `studio_digest_loop`; ~61165/61195/61246 role rules; ~62370 wire block; ~70417 loop start + `bot.add_view(DigestView())` in the `on_ready` add_view block (~70200s); `CLAUDE.md` (skills section + a «weekend digest traps» block); `requirements.txt` (+ `segno~=1.6`, **its own approval**).

Insertions (verbatim targets):

```python
# ~298
try:
    import digest as _digest
    _HAS_DIGEST = True
except Exception as _digest_err:        # pragma: no cover
    print("[digest] import failed (digest disabled, bot unaffected):", _digest_err)
    _digest = None
    _HAS_DIGEST = False

# ~6590
DIGEST_ENABLED = os.environ.get("DIGEST_ENABLED", "1") == "1"
DIGEST_DRYRUN  = os.environ.get("DIGEST_DRYRUN", "1") in ("1", "true", "True", "yes")
DIGEST_CHANNEL = os.environ.get("DIGEST_CHANNEL", "نشرة-الاسبوع")
DIGEST_DAY     = int(os.environ.get("DIGEST_DAY", "2") or 2)      # 2 = Wednesday
DIGEST_HOUR    = int(os.environ.get("DIGEST_HOUR", "13") or 13)   # never before 13:00 (owner rule)

# ~8044
@tasks.loop(minutes=30)
async def digest_loop():
    """Weekend digest: Wednesday DIGEST_HOUR Riyadh only; latch persisted in digest_issues."""
    if not (DIGEST_ENABLED and _HAS_DIGEST):
        return
    now = now_riyadh()
    existing = await asyncio.to_thread(_digest.build.existing_week_of, now)
    if not _digest.schedule.should_fire(now, DIGEST_DAY, DIGEST_HOUR, existing):
        return
    try:
        rep = await asyncio.to_thread(_digest.build.build_issue, now, _digest.net_live,
                                      claude_search_json, _load_json, DIGEST_DRYRUN)
        body = _digest.notify.build_message(rep["payload"], rep["issue_no"], rep["dropped"], _dispatch_base_url())
        if DIGEST_DRYRUN:
            print("[digest] (dryrun) would post issue", rep["issue_no"], chr(10), body); return
        guild = bot.get_guild(GUILD_ID)
        if guild is None: return
        ch = await ensure_channel(guild, DIGEST_CHANNEL, await get_category(guild))
        if ch is None: return
        with open(rep["files"]["png"], "rb") as fh:
            f = discord.File(io.BytesIO(fh.read()), filename="digest-%s.png" % rep["issue_no"])
        msg = await ch.send(body[:1900], file=f, view=DigestView())
        await asyncio.to_thread(_digest.db.set_issue, rep["issue_id"], msg_id=msg.id, channel_id=ch.id, status="preview")
    except Exception as e:
        print("[digest] loop error:", e)
```
`DigestView(discord.ui.View)` with `timeout=None`, five buttons `ouja_dg_approve/alt/rephrase/drop/rebuild`; `_digest_may_press(interaction)` = admin role or `manage_guild`, **fails closed**; each handler: `issue = await asyncio.to_thread(_digest.db.issue_by_msg, interaction.message.id)`; `approve` → `defer(thinking=True)` → `_digest.approval.act(...)` in a thread → edit message «✅ تم النشر · العدد N» and `view=None`; `alt`/`drop` → `send_message(view=_DigestSlotPick(issue, action), ephemeral=True)` where `_DigestSlotPick` is a `timeout=900` view with one `Select` per section whose options are `db.candidates(...)`; after any non-approve action, re-attach the new PNG by editing the message (`attachments=[discord.File(...)]`).

Role rules: `("/api/digest/", "digest")` appended to `_ROLE_WRITE_RULES` and `_ROLE_READ_RULES`; the `NAV_DEF`/permissions tab entry `digest` (grep `NAV_DEF` and copy the `studio` row).

Tests: `tests/test_digest_bot_contract.py` — `import bot` (as other bot-boundary tests do), assert `bot._HAS_DIGEST`, `bot.DIGEST_DRYRUN is True` under a clean env, `bot.digest_loop` exists and is not running, `DigestView().children` custom_ids equal the five ids, `_digest_may_press` returns False for an interaction stub without roles.

Then the full verification routine + esprima over `DASHBOARD_HTML` (unchanged, but run it) + `node --check`.

**→ P5 approval stop.** Also the `segno` requirement approval.

---

## Phase P6 — live dry run + polish

### Task 21: first live run (DRYRUN=1) + impeccable pass

- `python3 -m digest.build --dry-run` **online** in the worktree (network on, Chromium on): saves fixtures for any source without one, produces `$STATE_DIR/digest/<n>/`; send the PDF + PNG + the would-be Discord text to the owner.
- Run `impeccable` audit/critique/polish on the pages; `stop-slop` on every Arabic string; fix in `html.py`/`voice.py` only; if the frozen fingerprint changes because the *design* changed on purpose, the golden is regenerated **once, with the owner's word, in the same commit as the design change**, never to make a red test green.
- CLAUDE.md: add the skills block (from the brief §1.1 table) and a "Weekend digest traps" block (latch, dryrun, net_live-only, zero-backslash files, frozen rule).
- Commit. **Push only on explicit approval.** Flipping `DIGEST_DRYRUN=0` is a Railway env change the owner makes himself.

---

## Self-review

- Spec coverage: §2 host/db → T1; §5.3 dates → T2; §9.1 timing → T3+T20; §4 → T4; §3.4 → T5+T12(model half in T17's voice.polish wiring); §6 → T6; §5.2 links → T7; §5.1 sources → T8–T11; §5.5 places → T11; §3.1–3.3 → T12–T13; §8.4 → T14; §10 → T15; §7 → T16; §9.2 → T18+T20; §9.3 → T19; §11 verification → every phase; fixtures on first live run → T21.
- No placeholders: every task names its test assertions and the functions it produces.
- Names used across tasks: `Week`, `week_for`, `should_fire`, `validate/assert_valid`, `slop_hits`, `DigestError`, `FakeHttp`, `verify`, `Candidate` dict, `confidence`, `district_for`, `COMPOUNDS`, `TOKENS`, `font_faces`, `build_pages/build_story`, `audit_html`, `render`, `fingerprint/compare`, `score/choose`, `resolve`, `build_issue/existing_week_of/already_built`, `build_message`, `transition/act`, `DigestView`, `_digest_may_press` — consistent above.
