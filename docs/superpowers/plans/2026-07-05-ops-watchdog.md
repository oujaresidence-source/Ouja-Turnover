# Ops Watchdog «الرقيب التشغيلي» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read-only operations watchdog that posts a phone-readable Discord status every 30 min, pings instantly on critical flags (manual door-code missing before arrival, cleaning not ready, aged escalations), keeps a permanent code-send log, and builds a proven per-employee scoreboard with platform automations excluded.

**Architecture:** New `watchdog/` package mirroring `schedule/`+`promises/`: pure deterministic `engine.py` (TDD-locked, no I/O), `db.py` on brain.db (NO WAL / DELETE journal / closing(connect())), `host.py` DI bridge, `routes.py` API + `/watchdog` standalone editor page (ZERO backslashes — schedule/page.py trap). bot.py gets additive wiring + one `@tasks.loop` with a persisted last-run guard (the `@tasks.loop`-fires-on-deploy trap).

**Tech Stack:** Python 3, aiohttp, discord.py, sqlite (brain.db), unittest (NO pytest).

**Spec:** `docs/superpowers/specs/2026-07-05-ops-watchdog-design.md`

---

## File map

- Create: `watchdog/__init__.py` — wire()/register_routes()/bootstrap
- Create: `watchdog/host.py` — DI bridge (copy of schedule/host.py pattern)
- Create: `watchdog/db.py` — tables `watchdog_code_mode`, `watchdog_code_sends`, `watchdog_flag_state`, `watchdog_msg_stats`, `watchdog_fp`
- Create: `watchdog/engine.py` — pure: code-message classifier, automation fingerprint, flag computation, ping dedup decision, scoreboard, Discord renderers
- Create: `watchdog/routes.py` — `/api/watchdog/status`, `/api/watchdog/code-mode` (GET/POST), `/watchdog` editor page
- Create: `tests/test_watchdog_engine.py`, `tests/test_watchdog_db.py`
- Modify: `bot.py` — env block, import guard, wire in `start_web_server` (after schedule block ~47865), collector + loop + Discord posting (new section after promise-keeper code), loop start in `on_ready` (~53791)

Employee responsibility chain for a missing code: `schedule.coverage.cover_map(date_iso)` (today's covering employee per listing) → fallback «غير معروف». Discord mention via existing `_wm_resolve_id(name)`.

---

### Task 1: watchdog/db.py (+ package skeleton)

**Files:** Create `watchdog/__init__.py`, `watchdog/host.py`, `watchdog/db.py`, Test `tests/test_watchdog_db.py`

- [ ] **Step 1: failing test**

```python
# tests/test_watchdog_db.py
# -*- coding: utf-8 -*-
import os, tempfile, unittest

os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="wdtest_"))

from brain import db as bdb
from watchdog_pkg_guard import *  # noqa  (nothing — placeholder removed in impl)


class TestWatchdogDb(unittest.TestCase):
    def setUp(self):
        import watchdog.db as wdb
        self.wdb = wdb
        wdb.reset_init_cache()

    def test_code_mode_default_auto(self):
        self.assertEqual(self.wdb.code_mode("999111"), "auto")

    def test_code_mode_set_and_list(self):
        self.wdb.set_code_mode("999111", "manual", by="faisal")
        self.assertEqual(self.wdb.code_mode("999111"), "manual")
        rows = self.wdb.manual_listing_ids()
        self.assertIn("999111", rows)

    def test_code_send_log(self):
        self.wdb.log_code_send({"listing_id": "1", "reservation_id": "r1",
                                "guest_name": "g", "sent_by": "نورة",
                                "sent_at": "2026-07-05T10:00:00",
                                "arrival_ts": "2026-07-05T15:00:00", "on_time": 1})
        # idempotent per reservation
        self.wdb.log_code_send({"listing_id": "1", "reservation_id": "r1",
                                "guest_name": "g", "sent_by": "نورة",
                                "sent_at": "2026-07-05T10:00:00",
                                "arrival_ts": "2026-07-05T15:00:00", "on_time": 1})
        rows = self.wdb.code_sends_since("2026-06-28")
        self.assertEqual(len(rows), 1)

    def test_flag_state_ping_once(self):
        first = self.wdb.claim_ping("code:1:2026-07-05", "2026-07-05T10:00:00")
        again = self.wdb.claim_ping("code:1:2026-07-05", "2026-07-05T10:05:00")
        self.assertTrue(first)
        self.assertFalse(again)

    def test_fp_accumulate(self):
        for c in ("c1", "c2", "c3"):
            self.wdb.fp_bump("abc", conv=c, minute=660)
        rec = self.wdb.fp_get("abc")
        self.assertEqual(rec["n"], 3)
        self.assertEqual(len(rec["convs"]), 3)


if __name__ == "__main__":
    unittest.main()
```

(Implementation note: drop the placeholder import line; it exists only to show the file must import cleanly on its own.)

- [ ] **Step 2: run — must fail** `python3 -m unittest tests.test_watchdog_db -v` → ImportError (no watchdog package)

- [ ] **Step 3: implement**

`watchdog/host.py` — exact copy of schedule/host.py pattern, attrs:
```python
class _Host:
    state_path = None; load_json = None; save_json = None
    dash_auth = None; req_role = None; json_response = None; web = None
    listings = None          # () -> {lid:int -> name} (get_listings_map)
    resolve_discord = None   # (name) -> discord id string ('' unknown)
    tz = None; now = None
    _wired = False
    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("watchdog used '%s' before watchdog.wire()" % attr)
        return v
HOST = _Host()
def wire(caps):
    for k, v in (caps or {}).items(): setattr(HOST, k, v)
    HOST._wired = True
    return HOST
```

`watchdog/db.py` — same skeleton as promises/db.py (`_ensure`/`q`/`q1`/`execute` via `brain.db.connect`, `closing`, threading lock, `reset_init_cache`). SCHEMA:
```sql
CREATE TABLE IF NOT EXISTS watchdog_code_mode (
    listing_id TEXT PRIMARY KEY, mode TEXT NOT NULL DEFAULT 'auto',
    updated_at TEXT, updated_by TEXT);
CREATE TABLE IF NOT EXISTS watchdog_code_sends (
    id INTEGER PRIMARY KEY AUTOINCREMENT, listing_id TEXT, reservation_id TEXT,
    guest_name TEXT, sent_by TEXT, sent_at TEXT, arrival_ts TEXT,
    on_time INTEGER NOT NULL DEFAULT 0, detected_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wd_send_res ON watchdog_code_sends(reservation_id);
CREATE TABLE IF NOT EXISTS watchdog_flag_state (
    flag_key TEXT PRIMARY KEY, first_seen TEXT, last_seen TEXT,
    pinged_at TEXT, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS watchdog_msg_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, employee TEXT,
    replies INTEGER DEFAULT 0, resp_min_sum REAL DEFAULT 0,
    resp_min_n INTEGER DEFAULT 0, automations_skipped INTEGER DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wd_stats ON watchdog_msg_stats(day, employee);
CREATE TABLE IF NOT EXISTS watchdog_fp (
    fp TEXT PRIMARY KEY, n INTEGER DEFAULT 0, convs TEXT DEFAULT '[]',
    minutes TEXT DEFAULT '[]', last_seen TEXT);
CREATE TABLE IF NOT EXISTS watchdog_seen_msgs (
    conv_id TEXT, msg_id TEXT, PRIMARY KEY(conv_id, msg_id));
```
Functions: `code_mode(lid)->'auto'|'manual'` (default auto), `set_code_mode(lid, mode, by)`, `all_code_modes()->{lid:mode}`, `manual_listing_ids()->set`, `log_code_send(rec)` (INSERT OR IGNORE by reservation_id), `code_sends_since(day_iso)`, `claim_ping(key, now_iso)` (INSERT flag row if new; returns True and stamps pinged_at only when pinged_at IS NULL — atomic via `UPDATE ... WHERE flag_key=? AND pinged_at IS NULL` rowcount), `reping_due(key, now_iso, hours)`, `resolve_flag(key, now_iso)`, `bump_stat(day, employee, resp_min=None, automated=False)` (UPSERT), `stats_since(day_iso)`, `fp_bump(fp, conv, minute)` (append conv/minute distinct, cap lists at 12), `fp_get(fp)`.

`watchdog/__init__.py`:
```python
from .host import HOST, wire as _wire_host
from . import db, engine, routes  # noqa: F401
__all__ = ["wire", "register_routes", "HOST", "engine", "db"]
def wire(caps):
    _wire_host(caps)
    try:
        db._ensure()
        print("[watchdog] db ready")
    except Exception as e:
        print("[watchdog] bootstrap error:", e)
    return HOST
def register_routes(app):
    routes.register(app)
```
(routes.py stub `def register(app): pass` until Task 4.)

- [ ] **Step 4: run — pass** `python3 -m unittest tests.test_watchdog_db -v`
- [ ] **Step 5: commit** `git add watchdog tests/test_watchdog_db.py && git commit -m "feat(watchdog): package skeleton + brain.db tables (code mode/sends, flag dedup, msg stats, fingerprints)"`

---

### Task 2: engine — code classifier + automation fingerprint

**Files:** Create `watchdog/engine.py`, Test `tests/test_watchdog_engine.py`

- [ ] **Step 1: failing tests**

```python
# tests/test_watchdog_engine.py
# -*- coding: utf-8 -*-
import unittest
from datetime import datetime, timedelta
from watchdog import engine as E

NOW = datetime(2026, 7, 5, 13, 0)


def msg(body, incoming=0, sender="نورة", ts="2026-07-05T10:00:00"):
    return {"body": body, "isIncoming": incoming,
            "user": {"name": sender} if sender else None, "date": ts}


class TestCodeClassifier(unittest.TestCase):
    def test_finds_code_message(self):
        msgs = [msg("هلا! كود الباب 4512 حياك"), msg("welcome", sender="")]
        r = E.classify_code_send(msgs)
        self.assertTrue(r["found"])
        self.assertEqual(r["sender"], "نورة")
        self.assertEqual(r["sent_at"], "2026-07-05T10:00:00")

    def test_ignores_inbound_and_codeless(self):
        msgs = [msg("الكود وش هو؟", incoming=1), msg("أهلين بك")]
        self.assertFalse(E.classify_code_send(msgs)["found"])

    def test_unknown_sender_still_found(self):
        r = E.classify_code_send([msg("door code 88123", sender="")])
        self.assertTrue(r["found"])
        self.assertEqual(r["sender"], "")


class TestAutomationFP(unittest.TestCase):
    def test_normalize_strips_digits_names(self):
        a = E.normalize_body("مرحبا أحمد، تسجيل الخروج 11 صباحاً غرفة 12")
        b = E.normalize_body("مرحبا سارة، تسجيل الخروج 11 صباحاً غرفة 7")
        self.assertEqual(a, b)

    def test_recurring_same_clock_is_automated(self):
        rec = {"n": 4, "convs": ["a", "b", "c", "d"],
               "minutes": [660, 662, 659, 661]}
        self.assertTrue(E.fp_is_automated(rec))

    def test_varied_replies_not_automated(self):
        self.assertFalse(E.fp_is_automated({"n": 2, "convs": ["a", "b"],
                                            "minutes": [600, 900]}))
        self.assertFalse(E.fp_is_automated({"n": 5, "convs": ["a"],
                                            "minutes": [660] * 5}))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: run — fail** `python3 -m unittest tests.test_watchdog_engine -v`

- [ ] **Step 3: implement in `watchdog/engine.py`** (pure, stdlib only)

```python
_CODE_KW_AR = ("كود", "رمز", "كلمة المرور", "كلمة مرور", "الباسوورد", "باسوورد", "رمز الدخول")
_CODE_KW_EN = ("code", "access code", "door code", "passcode", "password")

def _is_inbound(m):
    for k in ("isIncoming", "incoming"):
        try:
            if int(m.get(k) or 0) == 1: return True
        except Exception: pass
    return False

def _sender(m):  # mirror of bot._wm_sender_name, kept pure/local
    u = m.get("user")
    if isinstance(u, dict):
        nm = (u.get("name") or " ".join(str(x) for x in (u.get("firstName"), u.get("lastName")) if x)).strip()
        if nm: return nm
    for k in ("userName", "agentName", "sentBy", "fromName", "senderName", "authorName"):
        v = str(m.get(k) or "").strip()
        if v: return v
    return ""

def classify_code_send(msgs):
    """Newest matching outgoing code-bearing message → {found, sender, sent_at}."""
    best = None
    for m in msgs or []:
        if _is_inbound(m): continue
        body = (m.get("body") or "")
        if not re.search(r"\b\d{4,8}\b", body): continue
        low = body.lower()
        if not (any(k in low for k in _CODE_KW_EN) or any(k in body for k in _CODE_KW_AR)):
            continue
        ts = str(m.get("date") or m.get("insertedOn") or "")
        if best is None or ts > best["sent_at"]:
            best = {"found": True, "sender": _sender(m), "sent_at": ts}
    return best or {"found": False, "sender": "", "sent_at": ""}

def normalize_body(body):
    t = re.sub(r"\d+", "#", str(body or ""))
    t = re.sub(r"[ـ]|[^\w\s#؀-ۿ]", " ", t)
    words = [w for w in t.split() if len(w) > 1]
    # drop likely-name 2nd token after greeting words (مرحبا/هلا/hi/hello/dear)
    out, skip = [], False
    GREET = {"مرحبا", "مرحباً", "هلا", "أهلا", "اهلا", "hi", "hello", "dear", "عزيزي", "عزيزتي"}
    for w in words:
        if skip: skip = False; continue
        if w.lower() in GREET: out.append(w.lower()); skip = True; continue
        out.append(w.lower())
    return " ".join(out)

def body_fp(body):
    return hashlib.sha1(normalize_body(body).encode("utf-8")).hexdigest()[:16]

def fp_is_automated(rec):
    """≥3 sightings across ≥3 conversations, clock times within a 40-min band."""
    if not rec or int(rec.get("n") or 0) < 3: return False
    if len(set(rec.get("convs") or [])) < 3: return False
    mins = rec.get("minutes") or []
    return bool(mins) and (max(mins) - min(mins)) <= 40
```

- [ ] **Step 4: run — pass**
- [ ] **Step 5: commit** `git commit -m "feat(watchdog): pure engine — code-send classifier + automation fingerprint (the Aseel rule)"`

---

### Task 3: engine — flags, ping dedup decision, renderers, scoreboard

**Files:** Modify `watchdog/engine.py`, Test append `tests/test_watchdog_engine.py`

- [ ] **Step 1: failing tests (append)**

```python
class TestFlags(unittest.TestCase):
    def snap(self, **kw):
        base = {"arrivals": [], "escalations": [], "pending": [], "promises": [],
                "tickets": [], "cleaning_stale": [],
                "coverage": {"ok": True, "off_names": [], "imbalance": 0},
                "today": {"arr_n": 0, "dep_n": 0, "occupied": 0, "tight_n": 0},
                "codes_summary": {"manual_total": 0, "sent": 0},
                "health": {"disk_fallback": False, "api_ok": True}}
        base.update(kw)
        return base

    def test_manual_code_missing_soon_is_critical(self):
        s = self.snap(arrivals=[{"unit": "Ouja | A", "guest": "خالد", "listing_id": "7",
                                 "hours_until": 2.0, "code_mode": "manual",
                                 "code_found": False, "code_sender": "",
                                 "cleaning_ok": True, "employee": "نورة",
                                 "arrival_date": "2026-07-05"}])
        flags = E.compute_flags(s, NOW)
        crit = [f for f in flags if f["severity"] == "critical"]
        self.assertEqual(len(crit), 1)
        self.assertEqual(crit[0]["key"], "code:7:2026-07-05")
        self.assertIn("نورة", crit[0]["text"])

    def test_auto_code_never_flags(self):
        s = self.snap(arrivals=[{"unit": "Ouja | A", "guest": "خالد", "listing_id": "7",
                                 "hours_until": 1.0, "code_mode": "auto",
                                 "code_found": False, "code_sender": "",
                                 "cleaning_ok": True, "employee": "",
                                 "arrival_date": "2026-07-05"}])
        self.assertEqual([f for f in E.compute_flags(s, NOW) if f["key"].startswith("code:")], [])

    def test_escalation_thresholds(self):
        s = self.snap(escalations=[{"guest": "g", "unit": "u", "age_min": 130, "id": "9"}])
        f = [x for x in E.compute_flags(s, NOW) if x["key"] == "esc:9"][0]
        self.assertEqual(f["severity"], "critical")
        s2 = self.snap(escalations=[{"guest": "g", "unit": "u", "age_min": 50, "id": "9"}])
        f2 = [x for x in E.compute_flags(s2, NOW) if x["key"] == "esc:9"][0]
        self.assertEqual(f2["severity"], "warn")

    def test_green_summary_is_compact(self):
        txt = E.render_summary([], self.snap(
            today={"arr_n": 5, "dep_n": 3, "occupied": 41, "tight_n": 1},
            codes_summary={"manual_total": 2, "sent": 2}), "3:30 م")
        self.assertLessEqual(len(txt.splitlines()), 6)
        self.assertIn("🟢", txt)
        self.assertIn("41", txt)

    def test_flag_summary_one_line_per_flag(self):
        flags = [{"key": "k1", "severity": "critical", "text": "كود ما انرسل: A — نورة", "mention": ""},
                 {"key": "k2", "severity": "warn", "text": "تصعيد بدون استلام من ساعة", "mention": ""}]
        txt = E.render_summary(flags, self.snap(), "3:30 م")
        self.assertIn("🔴", txt)
        self.assertLessEqual(len(txt.splitlines()), 12)


class TestScoreboard(unittest.TestCase):
    def test_board_math_and_exclusions(self):
        stats = [{"employee": "نورة", "replies": 30, "resp_min_sum": 300.0,
                  "resp_min_n": 30, "automations_skipped": 0},
                 {"employee": "أسيل", "replies": 20, "resp_min_sum": 400.0,
                  "resp_min_n": 20, "automations_skipped": 28}]
        sends = [{"sent_by": "نورة", "on_time": 1}, {"sent_by": "نورة", "on_time": 0}]
        promises = [{"promised_by": "نورة", "status": "done"},
                    {"promised_by": "نورة", "status": "expired"}]
        board = E.scoreboard(stats, sends, promises, [])
        nora = [b for b in board if b["name"] == "نورة"][0]
        self.assertEqual(nora["replies"], 30)
        self.assertEqual(nora["resp_avg"], 10)
        self.assertEqual(nora["codes_on_time"], 1)
        self.assertEqual(nora["codes_total"], 2)
        self.assertEqual(nora["kept_pct"], 50)
        aseel = [b for b in board if b["name"] == "أسيل"][0]
        self.assertEqual(aseel["automations_skipped"], 28)
```

- [ ] **Step 2: run — fail**
- [ ] **Step 3: implement** — thresholds as module consts:

```python
CODE_CRIT_H = 3.0          # arrival ≤3h + manual code missing → critical
CODE_WARN_H = 12.0
CLEAN_CRIT_H = 3.0         # arrival ≤3h + cleaning not approved → critical
ESC_CRIT_MIN = 120; ESC_WARN_MIN = 45
PEND_CRIT_MIN = 120; PEND_WARN_MIN = 30
STALE_CLEAN_H = 36
```

`compute_flags(snap, now)` builds flags list `{key, severity, text, mention_name, listing}`; order critical→warn→info. Per check exactly as spec table; code check ONLY when `code_mode == "manual"`. Text lines are single-line Arabic: `"🔑 كود ما انرسل: {unit} — 👤 {employee} — الضيف يوصل خلال {h} ساعة"` etc.

`render_summary(flags, snap, ts_label)`:
- no flags → 4 lines: `🟢 كل شي تمام — {ts}` / `🏠 اليوم: {arr} وصول · {dep} مغادرة · {occ} ساكن` / `🧹 نظافة: … · 🔑 أكواد يدوية: {sent}/{manual_total}` / `📩 معلق: {esc} تصعيد · {pend} رد · {ov} وعد متأخر`
- flags → header `🔴 وضع يحتاج تدخل — {ts}` (or `🟡` if no criticals), one line per flag (cap 8 flags + `+N أخرى`), tail line `🟢 الباقي تمام…`. Hard cap 12 lines.

`render_critical(flag)` → 2 lines: flag text + `{mention}` placeholder line (bot substitutes real mention strings).

`scoreboard(stats, sends, promises, esc_claims)` → per-employee dict: `replies`, `resp_avg` (round min), `codes_on_time/codes_total`, `kept_pct` (done/(done+expired)), `esc_claims`, `automations_skipped`; sort by kept_pct desc then replies desc. `render_scoreboard(board)` — `🏆 لوحة الأسبوع` + ≤2 lines per employee.

- [ ] **Step 4: run — pass** (all engine tests)
- [ ] **Step 5: commit** `git commit -m "feat(watchdog): flags + phone-first renderers + proven scoreboard"`

---### Task 4: routes + /watchdog editor page

**Files:** Modify `watchdog/routes.py`, Test append `tests/test_watchdog_db.py` (route-less logic only; page checked by esprima in verification)

- [ ] **Step 1:** implement `routes.py`:
- `GET /api/watchdog/status` — `HOST.dash_auth` gated → latest snapshot JSON (stored by the bot cycle into `HOST._last_snapshot`).
- `GET /api/watchdog/code-mode` — gated; returns `[{lid, name, mode}]` from `HOST.listings()` merged with `db.all_code_modes()`.
- `POST /api/watchdog/code-mode` — gated + role in (admin, ops); body `{lid, mode}`; validates mode in ("auto","manual"); writes `db.set_code_mode`.
- `GET /watchdog` — gated HTML page (triple-quoted, **ZERO backslashes**, real newlines, event delegation — schedule/page.py trap). Simple list: apartment name + two-state toggle تلقائي/يدوي, saves via fetch POST, optimistic UI reconciled from response (finance lesson: patch from server truth, no fake success). Reuse dashboard token colors, IBM Plex Sans Arabic, RTL, 44px touch targets.
- [ ] **Step 2:** esprima-parse every `<script>` in the page string (same recipe as DASHBOARD_HTML), `python3 -m py_compile watchdog/routes.py`.
- [ ] **Step 3: commit** `git commit -m "feat(watchdog): /watchdog code-mode editor page + status/code-mode API"`

---

### Task 5: bot.py wiring — env, import, wire, routes

**Files:** Modify `bot.py` (env block near other WATCHMAN_* envs; import guard near `_HAS_SCHEDULE`; wire block after schedule wiring ~line 47865)

- [ ] **Step 1:** env vars:
```python
WATCHDOG_ENABLED  = os.getenv("WATCHDOG_ENABLED", "1") == "1"
WATCHDOG_DRYRUN   = os.getenv("WATCHDOG_DRYRUN", "1") == "1"
WATCHDOG_INTERVAL_MIN   = int(os.getenv("WATCHDOG_INTERVAL_MIN", "30"))
WATCHDOG_CHANNEL        = os.getenv("WATCHDOG_CHANNEL", "غرفة-المراقبة")
WATCHDOG_REPING_HOURS   = float(os.getenv("WATCHDOG_REPING_HOURS", "2"))
WATCHDOG_CODE_LOOKAHEAD_H = float(os.getenv("WATCHDOG_CODE_LOOKAHEAD_H", "12"))
```
- [ ] **Step 2:** import guard:
```python
try:
    import watchdog as _watchdog
    _HAS_WATCHDOG = True
except Exception as _we:
    _HAS_WATCHDOG = False
    print("[watchdog] package not importable:", _we)
```
- [ ] **Step 3:** wire in `start_web_server` (after guide block, mirrors schedule wiring try/except so a failure never kills the bot):
```python
if _HAS_WATCHDOG and WATCHDOG_ENABLED:
    try:
        _watchdog.wire({
            "state_path": _state_path, "load_json": _load_json, "save_json": _save_json,
            "dash_auth": _dash_auth, "req_role": _req_role, "json_response": _json, "web": web,
            "listings": get_listings_map, "resolve_discord": _wm_resolve_id,
            "tz": TZ, "now": now_riyadh,
        })
        _watchdog.register_routes(app)
        print("[watchdog] wired + routes registered (/watchdog, /api/watchdog/*)")
    except Exception as _wde:
        print("[watchdog] wiring failed (watchdog disabled, bot unaffected):", _wde)
```
- [ ] **Step 4:** verify: `python3 -W error::SyntaxWarning -m py_compile bot.py && python3 -m pyflakes bot.py watchdog/*.py | grep -v "imported but unused"`
- [ ] **Step 5: commit** `git commit -m "feat(watchdog): bot.py wiring — env flags + DI + routes (additive, guarded)"`

---

### Task 6: bot.py collector + 30-min loop + Discord posting

**Files:** Modify `bot.py` — new section `# ====== Ops Watchdog «الرقيب التشغيلي» ======` placed after the promise-keeper loop code; loop start in `on_ready` next to `promise_keeper_loop` (~53791)

- [ ] **Step 1:** collector `_watchdog_snapshot()` (sync, runs in `asyncio.to_thread`):
  - arrivals: `compute_arrivals_with_status(window_hours=WATCHDOG_CODE_LOOKAHEAD_H)`; for each: `code_mode = _watchdog.db.code_mode(str(lid))`; if manual → fetch conversation messages once (`api_get(f"/conversations/{cid}/messages")`), `engine.classify_code_send(msgs)`; on found → `db.log_code_send(...)` with `on_time = sent_at <= checkin_iso`; employee via `_schedule.coverage.cover_map(today)` name for lid (guarded `_HAS_SCHEDULE`); `cleaning_ok = not _oujact_pending_for(lid)` (helper reading `_oujact_opened`/`_oujact_done` for today's key).
  - escalations/pending: reuse `compute_urgent_now()` items (kinds `escalation`, `pending_reply`).
  - promises: `_pk_db.open_rows()` + `promises.engine.is_expired` overdue calc (already imported for promise keeper).
  - tickets: `_tickets` open unassigned count (info/warn only).
  - coverage: `_schedule.routes.schedule_day(today)` → `balanced`, off names.
  - today: `_compute_today()` subset (`arr n/dep n/occupied/tight`).
  - health: brain `db.STORAGE["is_fallback"]`, api ok = arrivals fetch didn't throw.
  - Every sub-collector in its own try/except → on failure the section becomes `{"error": True}` and renderer prints `«غير معروف»` line (golden rule).
  - Message-stats side pass (same cycle, only conversations already fetched): for each outgoing human msg not in `watchdog_seen_msgs`: skip if `_wm_is_ai_message(m)`; `fp_bump`; if `fp_is_automated` → `bump_stat(automated=True)` else `bump_stat(resp_min=latency)` where latency = minutes from previous inbound msg. Mark seen.
- [ ] **Step 2:** loop + posting:
```python
@tasks.loop(minutes=max(5, WATCHDOG_INTERVAL_MIN))
async def watchdog_loop():
    if not (_HAS_WATCHDOG and WATCHDOG_ENABLED):
        return
    meta = _load_json("watchdog_meta.json", {})
    last = meta.get("last_run_ts", 0)
    if time.time() - last < (WATCHDOG_INTERVAL_MIN * 60) - 90:
        return                      # deploy-restart guard (the @tasks.loop trap)
    try:
        snap = await asyncio.to_thread(_watchdog_snapshot)
        flags = _watchdog.engine.compute_flags(snap, now_riyadh())
        ts_label = now_riyadh().strftime("%-I:%M %p").replace("AM", "ص").replace("PM", "م")
        text = _watchdog.engine.render_summary(flags, snap, ts_label)
        meta["last_run_ts"] = time.time()
        if WATCHDOG_DRYRUN:
            print("[watchdog] (dryrun) summary:\n" + text)
            for f in flags:
                if f["severity"] == "critical":
                    print("[watchdog] (dryrun) critical:", f["key"], f["text"])
        else:
            await _watchdog_post(text, flags, meta)
        _save_json("watchdog_meta.json", meta)
    except Exception as e:
        print("[watchdog] cycle error:", e)
```
  `_watchdog_post(text, flags, meta)`: ensure channel (`get_category` + `ensure_channel(guild, WATCHDOG_CHANNEL, cat)`); summary → try edit message id `meta["summary_msg_id"]`, else send new and store id; criticals → for each flag where `_watchdog.db.claim_ping(key, now_iso)` OR `reping_due(...)` → send separate message `flag.text + mentions` (owner id from `OWNER_DISCORD_ID` if set + `_wm_mention(_wm_resolve_id(name))`); non-critical resolved keys → `resolve_flag`.
  Weekly scoreboard: inside loop, if Sunday and `meta.get("board_week") != isocalendar week` → build from `db.stats_since(7d)`, `db.code_sends_since(7d)`, `promises db rows(7d)` → `engine.scoreboard` + `render_scoreboard` → send; stamp week.
- [ ] **Step 3:** `on_ready` start (next to promise_keeper block, with `_loop_guard`):
```python
if _HAS_WATCHDOG and WATCHDOG_ENABLED and not watchdog_ops_loop_started():
    _loop_guard(watchdog_loop, "watchdog_loop")   # follow existing guard pattern
    watchdog_loop.start()
```
  (NOTE: the existing conversation auditor is named `watchman_loop` — the new loop MUST be `watchdog_loop`, distinct name, no collision; grep first.)
- [ ] **Step 4:** synthetic-data logic test: feed `_watchdog_snapshot`-shaped fake dict through `compute_flags` + `render_summary` in a REPL-style scratch script; assert counts (per CLAUDE.md synthetic-data rule). Then full verification routine.
- [ ] **Step 5: commit** `git commit -m "feat(watchdog): 30-min ops cycle → Discord summary + instant critical pings + weekly scoreboard"`

---

### Task 7: full verification + push

- [ ] **Step 1:** the CLAUDE.md routine:
```
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py finance/*.py watchdog/*.py
node --check finance/static/erp.js
python3 -m unittest discover -s tests -p "test_*.py"
```
plus esprima parse of DASHBOARD_HTML scripts (untouched, but run anyway) and of the `/watchdog` page scripts.
- [ ] **Step 2:** `git push` (Railway auto-deploy). Watch log lines `[watchdog] wired` + first `(dryrun) summary`.
- [ ] **Step 3:** plain-language owner handoff (Arabic+English): what shipped, the `/watchdog` editor link, DRYRUN flip instruction.

## Self-review notes
- Spec coverage: checks 1–10 → Task 3 flags + Task 6 collectors; code registry/editor → Tasks 1+4; Aseel rule → Task 2 + Task 6 stats pass; scoreboard → Tasks 3+6; phone format → Task 3 renderers (line caps asserted in tests); dryrun/env → Task 5; deploy-trap guard → Task 6 Step 2. Editor ships as standalone `/watchdog` page (safer than DASHBOARD_HTML edit) — deviation from "dashboard editor" answer, surfaced to owner in handoff; dashboard tab is a v2 candidate.
- Name collision checked: existing loop = `watchman_loop`; new = `watchdog_loop`. Package name `watchdog` does not collide with any import in bot.py (verify with grep before Task 5).
- Types consistent: engine consumes plain dicts/ISO strings only; db returns dicts.
