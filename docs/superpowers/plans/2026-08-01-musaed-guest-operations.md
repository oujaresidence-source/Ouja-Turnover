# MUSAED Guest Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MUSAED decide early-check-in and apartment-search conversations from verified Hostaway facts, add two-step manager decisions, and give every in-house guest an evidence-based 0–10 score.

**Architecture:** Keep the live integration in `bot.py`, but introduce small pure helpers for intent, state, qualification, scoring, and rendering. Hostaway functions produce explicit `free`, `occupied`, `blocked`, or `unknown` facts; Discord handlers consume stored decision records; Claude only drafts language from those facts. Tests call the pure seams with synthetic data before any production edit.

**Tech Stack:** Python 3.9, `discord.py`, Hostaway REST API, Anthropic Messages API, `unittest`, persisted JSON state.

---

## File map

- Modify `bot.py`: MUSAED pure helpers, Hostaway fact collection, decision-card lifecycle, model routing, off-hours, guest scoring, `/guest` alias.
- Modify `golden_set.seed.jsonl`: replace old early-check-in expectations and add qualification/off-hours cases.
- Create `tests/test_musaed_early_checkin.py`: intent, calendar state, context, decision and privacy cases.
- Create `tests/test_musaed_apartment_search.py`: shopping detection, requirement extraction, missing-field prompt, verified match filtering.
- Create `tests/test_guest_score.py`: score normalization, objective caps, failure state, whole-stay prompt facts.
- Modify `tests/test_ops_commands_render.py`: 0–10 rendering, ordering, compact perfect scores.

### Task 1: Early-check-in intent and Hostaway facts

**Files:**
- Create: `tests/test_musaed_early_checkin.py`
- Modify: `bot.py:1819-1901`

- [ ] **Step 1: Write failing intent and state tests**

```python
import unittest
from unittest import mock
from datetime import date
import bot


class TestEarlyCheckinIntent(unittest.TestCase):
    def test_natural_time_requests_are_detected(self):
        cases = {
            "أقدر أدخل الساعة 10 الصبح بدل 3؟": 600,
            "هل أقدر أدخل الساعة 12؟": 720,
            "ممكن التشيك ان الساعة ١٢ الظهر؟": 720,
            "Can I check in at 12 pm?": 720,
            "Can I arrive at noon?": 720,
        }
        for text, minutes in cases.items():
            with self.subTest(text=text):
                self.assertEqual(bot._early_checkin_request(text)["requested_minutes"], minutes)

    def test_latest_guest_message_scopes_the_intent(self):
        history = "Guest: Can I check in early?\nHost: Official time is 3 PM\nGuest: Thanks"
        self.assertIsNone(bot._early_checkin_request(bot._latest_guest_line(history)))


class TestCalendarNightState(unittest.TestCase):
    def test_states_do_not_conflate_failure_with_occupancy(self):
        samples = [
            ({"result": [{"isAvailable": 1}]}, "free"),
            ({"result": [{"isAvailable": 0, "reservationId": 99}]}, "occupied"),
            ({"result": [{"isAvailable": 0}]}, "blocked"),
            ({"result": []}, "unknown"),
        ]
        for payload, expected in samples:
            with self.subTest(expected=expected), mock.patch.object(bot, "api_get", return_value=payload):
                self.assertEqual(bot._calendar_night_state(7, date(2026, 8, 4)), expected)

    def test_api_error_is_unknown(self):
        with mock.patch.object(bot, "api_get", side_effect=RuntimeError("down")):
            self.assertEqual(bot._calendar_night_state(7, date(2026, 8, 4)), "unknown")
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_musaed_early_checkin -v`

Expected: failures because `_early_checkin_request` and `_calendar_night_state` do not exist.

- [ ] **Step 3: Add minimal intent and state helpers**

```python
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_OFFICIAL_CHECKIN_MINUTES = 15 * 60


def _early_checkin_request(text):
    raw = (text or "").translate(_AR_DIGITS)
    low = raw.lower()
    explicit = any(h in low for h in _EARLY_CHECKIN_HINTS)
    checkin_words = any(x in low for x in (
        "ادخل", "أدخل", "ندخل", "دخول", "تشيك ان", "تشيك إن",
        "check in", "check-in", "arrive", "arrival"))
    requested = None
    if "noon" in low or "الظهر" in low:
        requested = 12 * 60
    else:
        match = re.search(r"(?:الساعة|الساعه|at)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|صباح|الصبح|ظهر|الظهر|مساء)?", low)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            marker = match.group(3) or ""
            if marker in ("pm", "مساء", "ظهر", "الظهر") and hour < 12:
                hour += 12
            if marker in ("am", "صباح", "الصبح") and hour == 12:
                hour = 0
            requested = hour * 60 + minute
    if not explicit and not (checkin_words and requested is not None
                              and requested < _OFFICIAL_CHECKIN_MINUTES):
        return None
    return {"requested_minutes": requested,
            "requested_label": _format_guest_time(requested) if requested is not None else ""}


def _calendar_night_state(listing_id, night_date):
    try:
        iso = night_date.isoformat()
        days = (api_get(f"/listings/{listing_id}/calendar",
                        params={"startDate": iso, "endDate": iso}) or {}).get("result") or []
    except Exception as exc:
        print(f"_calendar_night_state error ({listing_id}, {night_date}):", exc)
        return "unknown"
    if not days:
        return "unknown"
    day = days[0]
    if day.get("reservationId"):
        return "occupied"
    if int(day.get("isAvailable", 0) or 0) == 1:
        return "free"
    return "blocked"
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_musaed_early_checkin -v`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Add neighbor and alternative tests, then implement the context**

Add synthetic reservations around an arrival and assert `_early_checkin_context_from_rows(...)` returns only the previous and next reservations for the same listing. Patch `fetch_reservations_window`, `_calendar_night_state`, and `unit_availability_price` in `early_checkin_context`; assert `unknown` never becomes a denial and alternatives require both `previous_night_state == "free"` and `available is True`.

Implementation interface:

```python
def _early_checkin_context_from_rows(listing_id, reservation_id, arrival, departure, rows):
    relevant = [r for r in rows if str(r.get("listingMapId")) == str(listing_id)
                and str(r.get("id")) != str(reservation_id)
                and _res_realized(r)]
    previous = max((r for r in relevant if _parse_date(r.get("departureDate")) <= arrival),
                   key=lambda r: _parse_date(r.get("departureDate")), default=None)
    following = min((r for r in relevant if _parse_date(r.get("arrivalDate")) >= departure),
                    key=lambda r: _parse_date(r.get("arrivalDate")), default=None)
    return {"previous": _stay_summary(previous), "next": _stay_summary(following)}
```

- [ ] **Step 6: Commit Task 1**

```bash
git add bot.py tests/test_musaed_early_checkin.py
git commit -m "fix(musaed): verify early check-in facts"
```

### Task 2: Manager decision lifecycle

**Files:**
- Modify: `tests/test_musaed_early_checkin.py`
- Modify: `bot.py:9118-9212, 9967-10167, 52808-53010, 59641-59644`

- [ ] **Step 1: Write failing pure decision tests**

```python
class TestEarlyDecision(unittest.TestCase):
    def setUp(self):
        bot._early_checkin_decisions.clear()

    def test_first_decision_wins(self):
        bot._early_checkin_decisions[44] = {"status": "pending"}
        first = bot._decide_early_checkin(44, "approve", "Faisal")
        second = bot._decide_early_checkin(44, "reject", "Noura", "staff unavailable")
        self.assertEqual(first["status"], "approved")
        self.assertEqual(second["status"], "approved")
        self.assertEqual(second["decided_by"], "Faisal")

    def test_rejection_requires_reason(self):
        bot._early_checkin_decisions[45] = {"status": "pending"}
        self.assertIsNone(bot._decide_early_checkin(45, "reject", "Faisal", ""))

    def test_guest_reply_never_contains_neighbor_name(self):
        record = {"guest": "A", "previous": {"guest": "PRIVATE NAME"},
                  "requested_label": "12:00 PM", "unit": "Ouja | Test"}
        self.assertNotIn("PRIVATE NAME", bot._early_guest_reply(record, "approve"))
```

- [ ] **Step 2: Run and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_musaed_early_checkin.TestEarlyDecision -v`

Expected: missing decision store and helpers.

- [ ] **Step 3: Implement stored atomic decisions**

```python
_early_checkin_decisions = {}
_early_decision_lock = threading.Lock()


def _decide_early_checkin(message_id, decision, actor, reason=""):
    with _early_decision_lock:
        row = _early_checkin_decisions.get(int(message_id))
        if not row:
            return None
        if row.get("status") in ("approved", "rejected"):
            return row
        if decision == "reject" and not reason.strip():
            return None
        row.update({"status": "approved" if decision == "approve" else "rejected",
                    "reason": reason.strip()[:500], "decided_by": actor[:80],
                    "decided_at": datetime.now(TZ).isoformat(timespec="seconds")})
        return row
```

Persist `early_checkin_decisions.json` in `load_state()` and `persist_state()`.

- [ ] **Step 4: Add Discord views**

Add `EarlyCheckinDecisionView`, `EarlyRejectReasonSelect`, and `EarlyDecisionConfirmView` with persistent custom IDs. The first click only opens an ephemeral confirmation. The confirmation calls `_decide_early_checkin`, sends `_early_guest_reply` through `send_guest_message`, records `sent_at`, disables the card, and reports the existing decision on duplicate clicks.

Register the persistent view beside `ClaimView()` in `on_ready`:

```python
bot.add_view(EarlyCheckinDecisionView())
```

- [ ] **Step 5: Route verified early-check-in results before generic drafting**

In `process_assistant_item`, call a new `handle_early_checkin_item(it, channel)` before `claude_draft`. Return `True` when the message was fully handled. The handler posts a decision card for `free`, sends verified alternatives for `occupied` or `blocked`, and creates a manual escalation for `unknown`.

- [ ] **Step 6: Run early-check-in tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_musaed_early_checkin -v`

Expected: all pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add bot.py tests/test_musaed_early_checkin.py
git commit -m "feat(musaed): add early check-in decisions"
```

### Task 3: Apartment qualification and verified direct matches

**Files:**
- Create: `tests/test_musaed_apartment_search.py`
- Modify: `bot.py:7544-7667, 7880-8090, 10220-10288`

- [ ] **Step 1: Write failing qualification tests**

```python
class TestApartmentQualification(unittest.TestCase):
    def test_generic_shopping_messages_trigger(self):
        for text in ("أبي شقة اليوم", "أبحث عن سكن بالرياض", "I need an apartment tonight"):
            self.assertTrue(bot._is_apartment_search(text), text)

    def test_extracts_complete_requirements(self):
        history = ("Guest: من 5 إلى 8 أغسطس، 4 ضيوف، غرفتين، الملقا، ميزانيتي 700 بالليلة، "
                   "لازم موقف وواي فاي")
        got = bot._apartment_requirements(history)
        self.assertEqual(got["guests"], 4)
        self.assertEqual(got["beds"], 2)
        self.assertEqual(got["area"], "الملقا")
        self.assertEqual(got["budget_max"], 700)
        self.assertEqual(set(got["tags"]), {"parking", "wifi"})

    def test_missing_fields_are_asked_together(self):
        got = bot._apartment_requirements("Guest: أبي شقة في الملقا")
        prompt = bot._qualification_question(got, arabic=True)
        self.assertIn("الدخول والمغادرة", prompt)
        self.assertIn("عدد الضيوف", prompt)
        self.assertIn("الميزانية", prompt)
```

- [ ] **Step 2: Run and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_musaed_apartment_search -v`

Expected: missing helper failures.

- [ ] **Step 3: Implement qualification helpers**

Add `_is_apartment_search`, `_apartment_requirements`, `_missing_apartment_requirements`, and `_qualification_question`. Reuse `_criteria_from_text`, Arabic digit normalization, and date parsing. Recognize explicit `no preference` and `ما يهم` values so optional preferences become complete instead of being asked forever.

- [ ] **Step 4: Write verified-match tests**

Patch `_catalog_units` and `unit_availability_price`. Assert `_verified_apartment_matches` excludes `False` and `None` availability, respects capacity and budget, and returns at most three rows with `total` and `avg`.

```python
def test_only_verified_available_units_are_returned(self):
    with mock.patch.object(bot, "_catalog_units", self.units), \
         mock.patch.object(bot, "unit_availability_price", side_effect=self.availability):
        rows = bot._verified_apartment_matches(self.complete_requirements())
    self.assertTrue(rows)
    self.assertTrue(all(r["available"] is True for r in rows))
    self.assertLessEqual(len(rows), 3)
```

- [ ] **Step 5: Implement direct response routing**

Before generic `claude_draft`, detect current shopping intent or an active qualification conversation. Ask all missing fields once. When complete, render the verified matches and return `True` after direct send. On any unknown lookup, create a manual escalation and send the off-hours-aware apology instead of catalog prices.

- [ ] **Step 6: Run qualification tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_musaed_apartment_search -v`

Expected: all pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add bot.py tests/test_musaed_apartment_search.py
git commit -m "feat(musaed): qualify apartment searches"
```

### Task 4: Off-hours and Sonnet 5 routing

**Files:**
- Modify: `tests/test_musaed_early_checkin.py`
- Modify: `bot.py:351-358, 8240-8335, 10070-10096, 10712-10895`

- [ ] **Step 1: Write failing work-hours tests**

```python
def test_midnight_is_off_hours(self):
    self.assertFalse(bot.is_within_working_hours(datetime(2026, 8, 2, 0, 1, tzinfo=bot.TZ)))
    self.assertTrue(bot.is_within_working_hours(datetime(2026, 8, 1, 23, 59, tzinfo=bot.TZ)))

def test_return_time_is_11_am(self):
    got = bot.next_work_start(datetime(2026, 8, 2, 0, 1, tzinfo=bot.TZ))
    self.assertEqual((got.hour, got.minute), (11, 0))
```

- [ ] **Step 2: Change the default work end and verify**

Set `WORK_END_HOUR` default to `24` and `WORK_END_MIN` default to `0`. Run the focused tests and confirm midnight is outside the window.

- [ ] **Step 3: Write and implement model-payload tests**

Add `GUEST_ANALYSIS_MODEL = os.environ.get("GUEST_ANALYSIS_MODEL", "claude-sonnet-5")` and change `GUEST_DRAFT_MODEL` default to `claude-sonnet-5`. Add `_claude_thinking(model)` returning `{"type": "disabled"}` for Sonnet 5 guest JSON calls. Patch `requests.post` and assert MUSAED sends `thinking: {type: disabled}` with `max_tokens >= 1000`.

- [ ] **Step 4: Make the off-hours acknowledgment specific and deduplicated**

Use the existing `_offhours_acked_convos` set. Human-required replies after midnight state that operations returns at 11:00 AM. A second unresolved message in the same off-hours window keeps the escalation updated but does not send the same holding message again.

- [ ] **Step 5: Run focused tests and commit**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_musaed_early_checkin -v`

```bash
git add bot.py tests/test_musaed_early_checkin.py
git commit -m "fix(musaed): close operations at midnight"
```

### Task 5: Evidence-based 0–10 guest scoring

**Files:**
- Create: `tests/test_guest_score.py`
- Modify: `tests/test_ops_commands_render.py`
- Modify: `bot.py:2818-3072, 57115-57157`

- [ ] **Step 1: Write failing score-cap tests**

```python
class TestGuestScore(unittest.TestCase):
    def test_open_escalation_caps_score_at_six(self):
        raw = {"score": 9, "reason": "", "quote": "", "resolved": False,
               "confidence": 0.9}
        got = bot._normalize_guest_score(raw, {"open_escalation": True})
        self.assertEqual(got["score"], 6)

    def test_severe_open_complaint_caps_score_at_three(self):
        raw = {"score": 8, "severity": "angry", "resolved": False,
               "reason": "مشكلة دخول", "quote": "ما قدرت أدخل", "confidence": 0.9}
        got = bot._normalize_guest_score(raw, {"open_complaint": True})
        self.assertEqual(got["score"], 3)

    def test_failed_analysis_is_unknown(self):
        got = bot._normalize_guest_score(None, {})
        self.assertIsNone(got["score"])
        self.assertEqual(got["evidence_state"], "unknown")
```

- [ ] **Step 2: Run and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_guest_score -v`

Expected: `_normalize_guest_score` is missing.

- [ ] **Step 3: Implement scoring facts and model contract**

Replace `_GUEST_MOOD_SYSTEM` with a strict score JSON schema containing `score`, `severity`, `reason`, `quote`, `resolved`, and `confidence`. Build objective facts from open promises, open escalations, inbound messages after the last host reply, and response timing. Pass `GUEST_ANALYSIS_MODEL` explicitly. `_normalize_guest_score` clamps 0–10 and applies the objective caps.

- [ ] **Step 4: Rewrite renderer tests before renderer code**

In `tests/test_ops_commands_render.py`, replace mood-count assertions with:

```python
def test_lowest_score_is_first(self):
    text = bot.render_guests([
        {"guest": "Perfect", "unit": "A", "score": 10},
        {"guest": "Needs help", "unit": "B", "score": 3,
         "reason": "مشكلة دخول", "quote": "ما قدرت أدخل", "resolved": False,
         "staff": "ناصر", "phone": "0500000000"},
    ], "اليوم")
    self.assertLess(text.index("Needs help"), text.index("Perfect"))

def test_below_ten_has_reason_and_status(self):
    text = bot.render_guests([self.scored(8)], "اليوم")
    self.assertIn("8/10", text)
    self.assertIn("ليش", text)
    self.assertIn("لسه مفتوحة", text)
```

- [ ] **Step 5: Implement the Arabic-first renderer and command alias**

Render score bands and detailed sub-10 cards. Keep 10/10 guests as compact lines. Add a `/guest` slash command that delegates to the same `_run_guests_report(interaction)` function as `/guests`; keep text aliases unchanged.

- [ ] **Step 6: Run guest tests and commit**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_guest_score tests.test_ops_commands_render -v`

```bash
git add bot.py tests/test_guest_score.py tests/test_ops_commands_render.py
git commit -m "feat(guests): score current stays out of ten"
```

### Task 6: Evaluation set and full verification

**Files:**
- Modify: `golden_set.seed.jsonl`
- Modify: `bot.py` only if verification exposes a scoped defect.

- [ ] **Step 1: Replace old early-check-in golden expectations**

Change `early-01` and `early-02` so they no longer reward “usually another guest” guesses or a generic follow-up promise. Add cases for explicit noon wording, occupied original with verified alternatives, no alternatives, Hostaway unknown, qualification fields, and midnight human escalation. Expected actions must match the deterministic route.

- [ ] **Step 2: Run the no-network evaluation self-test**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 eval_musaed.py --selftest`

Expected: all harness checks pass.

- [ ] **Step 3: Run focused regression tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_musaed_early_checkin \
  tests.test_musaed_apartment_search \
  tests.test_guest_score \
  tests.test_ops_commands_render -v
```

Expected: all pass with no unexpected warnings from the changed logic.

- [ ] **Step 4: Run the repository verification routine**

```bash
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py finance/*.py
node --check finance/static/erp.js
python3 -m unittest discover -s tests -p "test_*.py"
```

Expected: compile, JavaScript parse, and all tests pass. Existing `pyflakes` unused-import findings may be reported separately only if unchanged from baseline.

- [ ] **Step 5: Inspect the final diff and state files**

Run:

```bash
git diff --check
git status --short
git diff --stat HEAD~5..HEAD
```

Confirm no unrelated untracked file is staged and no secret or live state file appears in the diff.

- [ ] **Step 6: Commit any final evaluation-only change**

```bash
git add golden_set.seed.jsonl
git commit -m "test(musaed): lock guest operations behavior"
```

- [ ] **Step 7: Push the verified main branch**

Run: `git push origin main`

Expected: GitHub accepts the new commits and Railway begins its automatic deployment.
