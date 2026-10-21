# «تسليم الرموز» House-rules "I agree" + Manual Code Release — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On 35 gated listings, guests reply "I agree" to a house-rules message and the employee covering that unit that day releases the door code by hand. The bot gives them a daily Discord list, a «✅ وافق وأرسلت الرمز» button and alerts. It never decides agreement and never sends a code.

**Architecture:** A new package `codegate/` in the established shape of `checkout/`: a pure `engine.py` (all decisions and wording), `db.py` (two tables inside the existing brain.db), `host.py` (the only bridge to bot.py), and `flow.py` (the tick and the button actions). bot.py adds a thin layer: Hostaway reads, Discord post/edit, one persistent view, one loop and one admin command. It also changes the three existing places that talk about the agreement, for gated units only. The Hostaway switch is a separate, owner-approved, step-by-step task done in Chrome after the bot is live.

**Tech Stack:** Python 3, discord.py ≥ 2.4, brain.db SQLite (no WAL), unittest (no pytest in this repo).

**Spec:** `docs/superpowers/specs/2026-10-21-house-rules-code-release-design.md` (APPROVED 2026-10-21).

## Global Constraints

- Work only in worktree `/Users/faisalouja/ouja-wt-agree`, branch `feat/agree-gate` (cut from `origin/main` 3308eb9). Never touch `/Users/faisalouja/Ouja-Turnover`, which is parked on `feat/musaed-v2`.
- **No push without the owner's explicit OK.** Pushing to `main` deploys to the live business.
- **No Hostaway write without the owner's OK for that specific change** (Task 8).
- The bot never sends a door code and never classifies a guest reply as agreement. The outbound firewall (`outbound_firewall`, `_FW_CODE_CTX`) is not modified.
- Every non-gated unit behaves exactly as today.
- brain.db rules: `from brain import db as _bdb`; `with closing(_bdb.connect())`; no WAL; no EXCLUSIVE locking.
- Packages never `import bot` (bot.py runs as `__main__`); bot.py fills `codegate.HOST` via `codegate.wire({...})`.
- Riyadh time everywhere (`zoneinfo.ZoneInfo("Asia/Riyadh")`).
- Gated listing count: **35** (the 34 on automation 288752 + 103 NRJS 526697).
- Daily list starts **09:00**; alerts at **check-in − 120 min** and **at check-in**; honesty check **15 min** after a press.
- Channel name `تسليم-الرموز`; fallback `#escalations` (`ESCALATION_CHANNEL`) if Discord refuses to create it.
- Button labels, verbatim: `✅ وافق وأرسلت الرمز` and `↩️ تراجع`.
- Confirm question, verbatim: `الضيف كتب «أوافق» في المحادثة، وأرسلت له الرمز من Hostaway؟`
- Rules-message markers, verbatim, case-insensitive: `I agree to the house rules` and `أوافق على قواعد الشقة`.
- `CODEGATE_ENABLED` defaults to `"1"` in code (the owner never edits Railway).
- Verification routine (CLAUDE.md) must pass before any push: `py_compile` with `-W error::SyntaxWarning`, `pyflakes bot.py finance/*.py codegate/*.py`, `node --check finance/static/erp.js`, the full unittest suite.

## Review Focus

1. **The rules message is missing from the chat** (old-flow bookings, a Hostaway hiccup, or a guest who booked before the switch). Expected: the card says «ما لقيت رسالة القواعد في المحادثة ⚠️» and still quotes the guest's last messages, never a blank card. Test in Task 1 (`test_no_rules_message_quotes_last_inbound`).
2. **Our own outbound message contains the words "I agree to the house rules"**, and a host reply may quote the guest. Expected: only inbound messages are ever quoted as guest replies. Tests in Task 1 (`test_outbound_never_quoted`, `test_host_quote_of_agree_not_a_reply`).
3. **Same-day booking made after the 2-hour mark or after check-in.** Expected: exactly one alert on first sight ("late" when check-in already passed, which also stamps the 2-hour alert), never two. Test in Task 1 (`test_late_booking_one_alert`) and Task 3 (`test_tick_late_booking_alerts_once`).
4. **A redeploy mid-day.** Expected: no second card, no second header, no second alert, and the button on the old card still works (lookup by message id). Test in Task 3 (`test_tick_twice_and_restart_is_idempotent`).
5. **A booking cancelled after its card was posted, or two people pressing at once.** Expected: the card turns grey «الحجز ملغي», no alerts, the button refuses. First press wins, the second gets «أُرسل من قبل». Tests in Task 3 (`test_cancelled_after_card`, `test_double_press_first_wins`).

---

## File Structure

| File | Responsibility |
|---|---|
| `codegate/__init__.py` | Package exports + `bootstrap()` |
| `codegate/units.json` | The 35 gated Hostaway listing ids (repo seed) |
| `codegate/engine.py` | PURE: unit list loading, reply extraction, alert decisions, permission, card/header/alert wording |
| `codegate/db.py` | `codegate_items` + `codegate_events` + `codegate_headers` in brain.db |
| `codegate/host.py` | `HOST` bridge filled by bot.py |
| `codegate/flow.py` | `tick()`, `press_release()`, `press_undo()`, `is_gated()`, `released()` |
| `bot.py` | Import block, `_cg_*` bridge functions, `CodegateView` + confirm view, `codegate_loop`, `!ouja رموز`, and the three gated-unit edits |
| `tests/test_codegate_engine.py` | Engine unit tests |
| `tests/test_codegate_flow.py` | Flow tests against fake host + temp brain.db |
| `tests/test_codegate_bot.py` | bot.py wiring and gated-unit regressions |

---

### Task 1: Pure engine + gated-unit list

**Files:**
- Create: `codegate/units.json`
- Create: `codegate/engine.py`
- Test: `tests/test_codegate_engine.py`

**Interfaces:**
- Consumes: nothing.
- Produces (exact names later tasks use):
  - `tz() -> ZoneInfo`
  - `load_units(repo_path: str, state_path: str | None) -> set[int]`
  - `is_rules_message(body: str) -> bool`
  - `guest_replies(messages: list[dict]) -> dict`: input items `{"inbound": bool, "body": str, "at": datetime | None}`; returns `{"rules_at": datetime | None, "replies": [{"at": datetime | None, "text": str}]}`
  - `alert_due(item: dict, now: datetime) -> str | None`, returning `"2h"`, `"late"` or `None`; item keys `checkin_at` (aware datetime), `released_at`, `cancelled`, `alert_2h_at`, `alert_late_at`
  - `may_release(presser_did: str, cover_did: str, owner_did: str, is_admin: bool, is_ops: bool) -> bool`
  - `card(item: dict, now: datetime) -> dict`: Discord-shaped embed dict (`title`, `description`, `color`, `fields`, `footer`)
  - `header_text(mention: str, name: str, n: int) -> str`
  - `alert_text(kind: str, item: dict, mention: str) -> str`
  - `content_hash(embed: dict) -> str`
  - Constants `MARKERS`, `ALERT_LEAD_MIN = 120`, `CODE_CHECK_MIN = 15`, `START_HOUR = 9`, `LABEL_RELEASE`, `LABEL_UNDO`, `CONFIRM_TEXT`

- [ ] **Step 1: Collect the 35 listing ids into `codegate/units.json`**

These ids were read from Hostaway on 2026-10-21:
`383921` H8 VLG, `385091` HUE 9, `437215` HUE 103, `441826` F2, `441858` 11 MLQ, `456602` C08 MJ, `457230` 1 MLQ, `457287` A5 MLQ, `461328` C2 NFL, `462594` DYAR20, `483841` العارض A11, `485203` 13 JOOD, `503713` A2 - التعاون, `513034` الغدير- B10, `522603` B03, `523916` B02, `526697` 103 NRJS, `535903` TWN 13B, `535907` 11B Royal, `576627` 101 -Narjs, `589273` i04.

The other 14 (الياسمين 8, Calma 90, F1, B14, HUE 202, شقة 7 - الماجديه, C3, C2 - العارض, Jood12, E5MLQ, Qurtuba-B20, القيروان-D7, 4511, 4101): open `https://dashboard.hostaway.com/messages/automations/288752` in Chrome (read only, never press Save). Scroll the **Listings** picker with "Show selected only" on; each row reads `Name  (id)`. Run in the page:

```js
[...document.querySelectorAll('input[type=checkbox]')].filter(i=>i.checked).map(i=>{let p=i;for(let k=0;k<4&&p;k++){p=p.parentElement;if((p.innerText||'').trim().length>2)break}return (p.innerText||'').trim()}).filter(s=>/\(\d+\)/.test(s))
```

The list is virtualised, so scroll and re-run until all 34 are seen. Then write:

```json
{
  "_doc": "Listings where the guest must reply «أوافق» and staff release the door code by hand. $STATE_DIR/codegate_units.json overrides this file. Owner decision 2026-10-21: the 34 of Hostaway automation 288752 + 103 NRJS.",
  "listing_ids": [383921, 385091, 437215, 441826, 441858, 456602, 457230, 457287, 461328, 462594,
                  483841, 485203, 503713, 513034, 522603, 523916, 526697, 535903, 535907, 576627,
                  589273]
}
```

(followed by the 14 collected ids appended to `listing_ids`, 35 in total). Check the count:

```bash
python3 -c "import json;print(len(json.load(open('codegate/units.json'))['listing_ids']))"
```

Expected: `35`

- [ ] **Step 2: Write the failing engine tests**

```python
# tests/test_codegate_engine.py
# -*- coding: utf-8 -*-
"""«تسليم الرموز» engine — pure decisions. Run: python3 -m unittest tests.test_codegate_engine"""
import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from codegate import engine  # noqa: E402

TZ = engine.tz()


def at(hh, mm=0, day=21):
    return datetime.datetime(2026, 10, day, hh, mm, tzinfo=TZ)


RULES_EN = "Hi Sara,\nPlease reply to this message with: \"I agree to the house rules\""
RULES_AR = "فضلاً رد على هالرسالة بـ: «أوافق على قواعد الشقة»"


def msg(inbound, body, hh, mm=0):
    return {"inbound": inbound, "body": body, "at": at(hh, mm)}


class TestUnits(unittest.TestCase):
    def test_repo_file_has_35(self):
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "codegate", "units.json")
        self.assertEqual(len(engine.load_units(here, None)), 35)

    def test_state_file_wins_when_valid(self):
        d = tempfile.mkdtemp()
        repo, state = os.path.join(d, "r.json"), os.path.join(d, "s.json")
        json.dump({"listing_ids": [1, 2]}, open(repo, "w"))
        json.dump({"listing_ids": [3]}, open(state, "w"))
        self.assertEqual(engine.load_units(repo, state), {3})

    def test_broken_state_file_falls_back_to_repo(self):
        d = tempfile.mkdtemp()
        repo, state = os.path.join(d, "r.json"), os.path.join(d, "s.json")
        json.dump({"listing_ids": [1, 2]}, open(repo, "w"))
        open(state, "w").write("{not json")
        self.assertEqual(engine.load_units(repo, state), {1, 2})

    def test_missing_files_give_empty_set(self):
        self.assertEqual(engine.load_units("/nope/a.json", "/nope/b.json"), set())


class TestReplies(unittest.TestCase):
    def test_rules_marker_both_languages_case_insensitive(self):
        self.assertTrue(engine.is_rules_message(RULES_EN.upper()))
        self.assertTrue(engine.is_rules_message(RULES_AR))
        self.assertFalse(engine.is_rules_message("Your door code: 1234 then #"))

    def test_replies_after_latest_rules_message_only(self):
        r = engine.guest_replies([
            msg(True, "is parking free?", 9),
            msg(False, RULES_EN, 10),
            msg(True, "i agre", 10, 5),
            msg(True, "IGR RA", 10, 6),
        ])
        self.assertEqual(r["rules_at"], at(10))
        self.assertEqual([x["text"] for x in r["replies"]], ["i agre", "IGR RA"])

    def test_outbound_never_quoted(self):
        r = engine.guest_replies([msg(False, RULES_EN, 10), msg(False, RULES_AR, 10, 1)])
        self.assertEqual(r["replies"], [])

    def test_host_quote_of_agree_not_a_reply(self):
        r = engine.guest_replies([msg(False, RULES_EN, 10),
                                  msg(False, 'Thanks! You wrote "I agree" — noted', 10, 9)])
        self.assertEqual(r["replies"], [])

    def test_no_rules_message_quotes_last_inbound(self):
        r = engine.guest_replies([msg(True, "a", 8), msg(True, "b", 9), msg(True, "c", 9, 1),
                                  msg(True, "d", 9, 2)])
        self.assertIsNone(r["rules_at"])
        self.assertEqual([x["text"] for x in r["replies"]], ["b", "c", "d"])

    def test_long_reply_truncated_and_at_most_three(self):
        r = engine.guest_replies([msg(False, RULES_EN, 10)] +
                                 [msg(True, "x" * 900, 11, i) for i in range(5)])
        self.assertEqual(len(r["replies"]), 3)
        self.assertLessEqual(len(r["replies"][0]["text"]), engine.QUOTE_CHARS + 1)

    def test_messages_without_time_sorted_last_and_kept(self):
        r = engine.guest_replies([msg(False, RULES_EN, 10),
                                  {"inbound": True, "body": "ok", "at": None}])
        self.assertEqual([x["text"] for x in r["replies"]], ["ok"])


class TestAlerts(unittest.TestCase):
    def item(self, **kw):
        base = {"checkin_at": at(16), "released_at": None, "cancelled": 0,
                "alert_2h_at": None, "alert_late_at": None}
        base.update(kw)
        return base

    def test_nothing_before_two_hours(self):
        self.assertIsNone(engine.alert_due(self.item(), at(13, 59)))

    def test_two_hours(self):
        self.assertEqual(engine.alert_due(self.item(), at(14, 0)), "2h")

    def test_two_hours_only_once(self):
        self.assertIsNone(engine.alert_due(self.item(alert_2h_at="x"), at(15)))

    def test_late_at_checkin(self):
        self.assertEqual(engine.alert_due(self.item(alert_2h_at="x"), at(16)), "late")

    def test_late_booking_one_alert(self):
        # first seen after check-in: one "late", and the 2h is considered covered by it
        self.assertEqual(engine.alert_due(self.item(), at(17)), "late")
        self.assertIsNone(engine.alert_due(self.item(alert_late_at="x"), at(18)))

    def test_released_or_cancelled_never_alerts(self):
        self.assertIsNone(engine.alert_due(self.item(released_at="x"), at(17)))
        self.assertIsNone(engine.alert_due(self.item(cancelled=1), at(17)))


class TestPermission(unittest.TestCase):
    def test_matrix(self):
        self.assertTrue(engine.may_release("1", "1", "", False, False))     # coverer
        self.assertTrue(engine.may_release("2", "1", "2", False, False))    # permanent owner
        self.assertTrue(engine.may_release("9", "1", "2", True, False))     # admin
        self.assertTrue(engine.may_release("9", "1", "2", False, True))     # ops role
        self.assertFalse(engine.may_release("9", "1", "2", False, False))   # anyone else
        self.assertFalse(engine.may_release("", "", "", False, False))      # empty never matches


class TestCard(unittest.TestCase):
    def base(self, **kw):
        it = {"unit": "C2 NFL", "guest": "Sara", "checkin_at": at(16), "cover_name": "نورة",
              "rules_at": at(10), "replies": [{"at": at(10, 5), "text": "I agree"}],
              "released_at": None, "released_by": None, "cancelled": 0,
              "alert_2h_at": None, "alert_late_at": None, "code_warned_at": None}
        it.update(kw)
        return it

    def test_waiting_card_quotes_reply_and_names_coverer(self):
        e = engine.card(self.base(), at(11))
        blob = json.dumps(e, ensure_ascii=False)
        self.assertIn("C2 NFL", e["title"])
        self.assertIn("> I agree", blob)
        self.assertIn("نورة", blob)
        self.assertIn("16:00", blob)
        self.assertEqual(e["color"], engine.COLOR_WAIT)

    def test_no_reply_yet(self):
        e = engine.card(self.base(replies=[]), at(11))
        self.assertIn("لا يوجد رد بعد", json.dumps(e, ensure_ascii=False))

    def test_missing_rules_message_flagged(self):
        e = engine.card(self.base(rules_at=None), at(11))
        self.assertIn("ما لقيت رسالة القواعد", json.dumps(e, ensure_ascii=False))

    def test_released_green_with_who_and_when(self):
        e = engine.card(self.base(released_at=at(14, 5).isoformat(), released_by="نورة"), at(15))
        self.assertEqual(e["color"], engine.COLOR_DONE)
        self.assertIn("14:05", json.dumps(e, ensure_ascii=False))

    def test_alert_fired_red_cancelled_grey(self):
        self.assertEqual(engine.card(self.base(alert_2h_at="x"), at(14, 30))["color"],
                         engine.COLOR_ALERT)
        self.assertEqual(engine.card(self.base(cancelled=1), at(14))["color"], engine.COLOR_OFF)

    def test_code_warning_shown(self):
        e = engine.card(self.base(released_at=at(14).isoformat(), released_by="نورة",
                                  code_warned_at=at(14, 20).isoformat()), at(15))
        self.assertIn("ما شفت رسالة الرمز", json.dumps(e, ensure_ascii=False))

    def test_hash_changes_with_content(self):
        a = engine.content_hash(engine.card(self.base(), at(11)))
        b = engine.content_hash(engine.card(self.base(replies=[]), at(11)))
        self.assertNotEqual(a, b)
        self.assertEqual(a, engine.content_hash(engine.card(self.base(), at(11))))


class TestTexts(unittest.TestCase):
    def test_header_and_alerts(self):
        self.assertIn("٣", engine.header_text("<@1>", "نورة", 3))
        self.assertIn("<@1>", engine.alert_text("2h", {"unit": "C3", "guest": "A",
                                                        "checkin_at": at(16)}, "<@1>"))
        self.assertIn("حلّ موعد الدخول", engine.alert_text("late", {"unit": "C3", "guest": "A",
                                                                      "checkin_at": at(16)}, ""))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to confirm they fail**

Run: `cd /Users/faisalouja/ouja-wt-agree && python3 -m unittest tests.test_codegate_engine -v`
Expected: ERROR `ModuleNotFoundError: No module named 'codegate'`

- [ ] **Step 4: Write `codegate/engine.py` (and an empty `codegate/__init__.py` for now)**

```python
# codegate/engine.py
# -*- coding: utf-8 -*-
"""
codegate.engine — PURE. Every decision and every word of «تسليم الرموز».

The owner's rule (2026-10-21): a HUMAN releases the door code after the guest writes «أوافق».
So nothing here decides whether a reply is agreement — replies are quoted word for word — and
nothing here ever sees a code. No I/O except load_units (two small JSON files).
"""

import hashlib
import json
import os
import unicodedata
from datetime import timedelta
from zoneinfo import ZoneInfo

MARKERS = ("i agree to the house rules", "أوافق على قواعد الشقة")
ALERT_LEAD_MIN = 120
CODE_CHECK_MIN = 15
START_HOUR = 9
MAX_QUOTES = 3
QUOTE_CHARS = 300

LABEL_RELEASE = "✅ وافق وأرسلت الرمز"
LABEL_UNDO = "↩️ تراجع"
CONFIRM_TEXT = "الضيف كتب «أوافق» في المحادثة، وأرسلت له الرمز من Hostaway؟"

COLOR_WAIT = 0xC9A227    # the dashboard gold
COLOR_DONE = 0x2E8B57
COLOR_ALERT = 0xD64545
COLOR_OFF = 0x8A8580

_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def tz():
    return ZoneInfo("Asia/Riyadh")


def _ids(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(x) for x in (raw.get("listing_ids") or [])}


def load_units(repo_path, state_path):
    """The gated listing ids. A readable $STATE_DIR copy wins; a broken one is ignored (the
    repo seed keeps serving) — the decor_packs.json rule."""
    for p in (state_path, repo_path):
        if p and os.path.exists(p):
            try:
                return _ids(p)
            except Exception as e:
                print("[codegate] unit list unreadable (%s): %s" % (p, e))
    return set()


def _fold(s):
    return unicodedata.normalize("NFKC", str(s or "")).casefold()


def is_rules_message(body):
    low = _fold(body)
    return any(_fold(m) in low for m in MARKERS)


def _key(m):
    a = m.get("at")
    return (a is None, a.timestamp() if a is not None else 0)


def _clip(text):
    t = " ".join(str(text or "").split())
    return t if len(t) <= QUOTE_CHARS else t[:QUOTE_CHARS] + "…"


def guest_replies(messages):
    """The guest's words since our LATEST house-rules message (inbound only — our own message
    contains the very words "I agree to the house rules"). No rules message → the last few
    inbound messages, and rules_at None so the card can say so."""
    ordered = sorted(messages or [], key=_key)
    found, rules_at, start = False, None, 0
    for i, m in enumerate(ordered):
        if not m.get("inbound") and is_rules_message(m.get("body")):
            found, rules_at, start = True, m.get("at"), i + 1
    pool = ordered[start:] if found else ordered
    inbound = [m for m in pool if m.get("inbound") and str(m.get("body") or "").strip()]
    return {"rules_at": rules_at,
            "replies": [{"at": m.get("at"), "text": _clip(m.get("body"))}
                        for m in inbound[-MAX_QUOTES:]]}


def alert_due(item, now):
    if item.get("released_at") or item.get("cancelled"):
        return None
    ci = item["checkin_at"]
    if now >= ci:
        return None if item.get("alert_late_at") else "late"
    if now >= ci - timedelta(minutes=ALERT_LEAD_MIN) and not item.get("alert_2h_at"):
        return "2h"
    return None


def may_release(presser_did, cover_did, owner_did, is_admin, is_ops):
    if is_admin or is_ops:
        return True
    p = str(presser_did or "")
    return bool(p) and p in {str(cover_did or ""), str(owner_did or "")} - {""}


def _hhmm(v):
    if not v:
        return ""
    if isinstance(v, str):
        return v[11:16]
    return v.strftime("%H:%M")


def ar_num(n):
    return str(n).translate(_AR_DIGITS)


def card(item, now):
    replies = item.get("replies") or []
    if replies:
        quoted = "\n".join("> " + r["text"] + ("  · " + _hhmm(r.get("at")) if r.get("at") else "")
                           for r in replies)
    else:
        quoted = "لا يوجد رد بعد ⏳"
    rules = ("وصلت للضيف ✅ " + _hhmm(item.get("rules_at"))) if item.get("rules_at") \
        else "ما لقيت رسالة القواعد في المحادثة ⚠️"
    if item.get("cancelled"):
        status, color = "🚫 الحجز ملغي", COLOR_OFF
    elif item.get("released_at"):
        status = "أُرسل الرمز ✅ — %s %s" % (item.get("released_by") or "", _hhmm(item["released_at"]))
        color = COLOR_DONE
    elif item.get("alert_2h_at") or item.get("alert_late_at"):
        status, color = "⏰ متأخر — ما أُرسل الرمز بعد", COLOR_ALERT
    else:
        status, color = "⏳ بانتظار «أوافق» ثم إرسال الرمز", COLOR_WAIT
    fields = [
        {"name": "الدخول", "value": _hhmm(item.get("checkin_at")) or "—", "inline": True},
        {"name": "المسؤول اليوم", "value": item.get("cover_name") or "— (فريق العمليات)",
         "inline": True},
        {"name": "رسالة القواعد", "value": rules, "inline": False},
        {"name": "ردود الضيف (حرفياً)", "value": quoted[:1024], "inline": False},
        {"name": "الحالة", "value": status, "inline": False},
    ]
    if item.get("code_warned_at"):
        fields.append({"name": "⚠️ تنبيه", "inline": False,
                       "value": "ضُغط الزر بس ما شفت رسالة الرمز في المحادثة — تأكد إنها انرسلت."})
    return {"title": "🔑 %s — %s" % (item.get("unit") or "", item.get("guest") or ""),
            "description": "الرمز يُرسل بعد ما يكتب الضيف «أوافق» في المحادثة — "
                           "استخدم الرد الجاهز «🔑 كود الدخول» في Hostaway.",
            "color": color, "fields": fields,
            "footer": {"text": "تسليم الرموز · البوت ما يقرّر الموافقة ولا يرسل الرمز"}}


def header_text(mention, name, n):
    who = mention or name or "فريق العمليات"
    return "🔑 %s — عندك %s وصول اليوم يحتاج «أوافق» قبل الرمز." % (who, ar_num(n))


def alert_text(kind, item, mention):
    base = "**%s** — %s · الدخول %s" % (item.get("unit") or "", item.get("guest") or "",
                                        _hhmm(item.get("checkin_at")))
    if kind == "2h":
        head = "⏰ باقي ساعتين على الدخول وما أُرسل الرمز."
    else:
        head = "🚨 حلّ موعد الدخول وما أُرسل الرمز."
    tail = "اقرأ رد الضيف؛ لو ما رد اتصل فيه واطلب منه يكتب «أوافق» في المحادثة، ثم أرسل الرمز."
    return " ".join(x for x in (mention, head) if x) + "\n" + base + "\n" + tail


def content_hash(embed):
    return hashlib.sha1(json.dumps(embed, ensure_ascii=False, sort_keys=True)
                        .encode("utf-8")).hexdigest()
```

`codegate/__init__.py` for now:

```python
# -*- coding: utf-8 -*-
"""codegate — «تسليم الرموز». Filled in by Task 3."""
```

- [ ] **Step 5: Run the tests to confirm they pass**

Run: `cd /Users/faisalouja/ouja-wt-agree && python3 -m unittest tests.test_codegate_engine -v`
Expected: all tests `ok`.

- [ ] **Step 6: Commit**

```bash
cd /Users/faisalouja/ouja-wt-agree
git add codegate/__init__.py codegate/engine.py codegate/units.json tests/test_codegate_engine.py
git commit -m "feat(codegate): pure engine + the 35 gated listings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Storage in brain.db

**Files:**
- Create: `codegate/db.py`
- Test: `tests/test_codegate_db.py`

**Interfaces:**
- Consumes: `brain.db.connect`, `brain.db.db_path`, `brain.db.set_db_path_for_tests`.
- Produces:
  - `_ensure()`, `reset_init_cache()`
  - `upsert_arrival(row: dict) -> None`: keys `res_id, lid, day, unit, guest, conversation_id, checkin_at (iso), cover_name, cover_did, cover_role_id, owner_did`. Sets `cancelled=0`. Never touches release, alert or card columns.
  - `mark_cancelled(day: str, keep_res_ids: set[str]) -> list[str]`: rows of `day` not in `keep_res_ids` become `cancelled=1`; returns those res_ids
  - `get(res_id) -> dict | None`, `item_by_message(message_id) -> dict | None`, `day_items(day) -> list[dict]`
  - `set_card(res_id, channel_id, message_id, card_hash)`, `set_hash(res_id, card_hash)`
  - `set_replies(res_id, rules_at_iso: str | None, replies: list[dict])`: replies stored as JSON with iso times; `get()` returns `replies` as a list of `{"at": iso|None, "text": str}`
  - `release(res_id, by_name, by_did, at_iso) -> bool`: first wins
  - `undo(res_id, by_name, at_iso) -> bool`
  - `stamp(res_id, column, at_iso)`: column ∈ `STAMP_COLUMNS = ("alert_2h_at", "alert_late_at", "code_check_at", "code_warned_at")`
  - `set_code_seen(res_id, seen: bool)`
  - `header_posted(day, key) -> bool`, `mark_header(day, key, message_id)`
  - `event(res_id, kind, actor="", detail="")`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_codegate_db.py
# -*- coding: utf-8 -*-
"""«تسليم الرموز» storage. Run: python3 -m unittest tests.test_codegate_db"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain import db as bdb  # noqa: E402
from codegate import db  # noqa: E402

DAY = "2026-10-21"


def row(res_id="r1", **kw):
    r = {"res_id": res_id, "lid": 461328, "day": DAY, "unit": "C2 NFL", "guest": "Sara",
         "conversation_id": "c1", "checkin_at": DAY + "T16:00:00+03:00", "cover_name": "نورة",
         "cover_did": "11", "cover_role_id": "", "owner_did": "22"}
    r.update(kw)
    return r


class TestDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cg_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()

    def test_upsert_is_one_row_and_keeps_release(self):
        db.upsert_arrival(row())
        self.assertTrue(db.release("r1", "نورة", "11", DAY + "T14:00:00+03:00"))
        db.upsert_arrival(row(guest="Sara A."))
        it = db.get("r1")
        self.assertEqual(it["guest"], "Sara A.")
        self.assertEqual(it["released_by"], "نورة")
        self.assertEqual(len(db.day_items(DAY)), 1)

    def test_release_first_wins_and_undo_reopens(self):
        db.upsert_arrival(row())
        self.assertTrue(db.release("r1", "نورة", "11", "t1"))
        self.assertFalse(db.release("r1", "ناصر", "33", "t2"))
        self.assertEqual(db.get("r1")["released_by"], "نورة")
        self.assertTrue(db.undo("r1", "admin", "t3"))
        self.assertIsNone(db.get("r1")["released_at"])
        self.assertTrue(db.release("r1", "ناصر", "33", "t4"))

    def test_card_lookup_by_message(self):
        db.upsert_arrival(row())
        db.set_card("r1", "900", "555", "h")
        self.assertEqual(db.item_by_message("555")["res_id"], "r1")
        self.assertIsNone(db.item_by_message("556"))

    def test_replies_roundtrip(self):
        db.upsert_arrival(row())
        db.set_replies("r1", DAY + "T10:00:00+03:00",
                       [{"at": DAY + "T10:05:00+03:00", "text": "I agree"}])
        it = db.get("r1")
        self.assertEqual(it["replies"][0]["text"], "I agree")
        self.assertEqual(it["rules_at"], DAY + "T10:00:00+03:00")

    def test_stamp_whitelist(self):
        db.upsert_arrival(row())
        db.stamp("r1", "alert_2h_at", "t")
        self.assertEqual(db.get("r1")["alert_2h_at"], "t")
        with self.assertRaises(ValueError):
            db.stamp("r1", "released_by", "evil")

    def test_mark_cancelled_and_revive(self):
        db.upsert_arrival(row("r1"))
        db.upsert_arrival(row("r2"))
        self.assertEqual(db.mark_cancelled(DAY, {"r1"}), ["r2"])
        self.assertEqual(db.get("r2")["cancelled"], 1)
        db.upsert_arrival(row("r2"))
        self.assertEqual(db.get("r2")["cancelled"], 0)

    def test_header_latch(self):
        self.assertFalse(db.header_posted(DAY, "11"))
        db.mark_header(DAY, "11", "777")
        self.assertTrue(db.header_posted(DAY, "11"))
        db.reset_init_cache()                      # a "restart"
        self.assertTrue(db.header_posted(DAY, "11"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm failure**

Run: `python3 -m unittest tests.test_codegate_db -v`
Expected: ERROR `cannot import name 'db' from 'codegate'`

- [ ] **Step 3: Write `codegate/db.py`**

```python
# codegate/db.py
# -*- coding: utf-8 -*-
"""
codegate.db — «تسليم الرموز» storage inside the SAME brain.db (brain/db.py rules: no WAL,
journal_mode=DELETE, one short-lived connection per call, always closed).

WHAT THE SCHEMA ENFORCES
  * One booking = one row (res_id PRIMARY KEY): a double tick or a redeploy never posts a
    second card.
  * First press wins: release() only updates a row whose released_at IS NULL.
  * One header per person per day (codegate_headers PRIMARY KEY (day, key)).
"""

import datetime
import json
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS codegate_items (
    res_id           TEXT PRIMARY KEY,
    lid              INTEGER,
    day              TEXT,
    unit             TEXT,
    guest            TEXT,
    conversation_id  TEXT,
    checkin_at       TEXT,
    cover_name       TEXT,
    cover_did        TEXT,
    cover_role_id    TEXT,
    owner_did        TEXT,
    channel_id       TEXT,
    card_message_id  TEXT,
    card_hash        TEXT,
    rules_at         TEXT,
    replies_json     TEXT,
    released_by      TEXT,
    released_by_did  TEXT,
    released_at      TEXT,
    code_seen        INTEGER,
    code_check_at    TEXT,
    code_warned_at   TEXT,
    alert_2h_at      TEXT,
    alert_late_at    TEXT,
    cancelled        INTEGER NOT NULL DEFAULT 0,
    undone_by        TEXT,
    undone_at        TEXT,
    created_at       TEXT,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_codegate_day  ON codegate_items(day);
CREATE INDEX IF NOT EXISTS idx_codegate_card ON codegate_items(card_message_id);
CREATE TABLE IF NOT EXISTS codegate_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    res_id  TEXT NOT NULL,
    at      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    actor   TEXT,
    detail  TEXT
);
CREATE TABLE IF NOT EXISTS codegate_headers (
    day         TEXT NOT NULL,
    key         TEXT NOT NULL,
    message_id  TEXT,
    PRIMARY KEY (day, key)
);
"""

STAMP_COLUMNS = ("alert_2h_at", "alert_late_at", "code_check_at", "code_warned_at")
_SNAPSHOT = ("lid", "day", "unit", "guest", "conversation_id", "checkin_at", "cover_name",
             "cover_did", "cover_role_id", "owner_did")

_inited = set()
_init_lock = threading.Lock()
_write_lock = threading.Lock()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


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


def _q(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cols = [d[0] for d in cur.description or []]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _x(sql, args=()):
    _ensure()
    with _write_lock, closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.rowcount


def _shape(r):
    if r is None:
        return None
    try:
        r["replies"] = json.loads(r.get("replies_json") or "[]")
    except Exception:
        r["replies"] = []
    return r


def upsert_arrival(row):
    now = _now()
    vals = [str(row["res_id"])] + [row.get(k) for k in _SNAPSHOT]
    sets = ", ".join("%s=excluded.%s" % (k, k) for k in _SNAPSHOT)
    _x("INSERT INTO codegate_items(res_id, %s, cancelled, created_at, updated_at) "
       "VALUES (?, %s, 0, ?, ?) "
       "ON CONFLICT(res_id) DO UPDATE SET %s, cancelled=0, updated_at=excluded.updated_at"
       % (", ".join(_SNAPSHOT), ", ".join("?" * len(_SNAPSHOT)), sets),
       vals + [now, now])


def mark_cancelled(day, keep_res_ids):
    keep = {str(x) for x in keep_res_ids or ()}
    gone = [r["res_id"] for r in _q("SELECT res_id FROM codegate_items WHERE day=? "
                                    "AND cancelled=0", (day,)) if r["res_id"] not in keep]
    for rid in gone:
        _x("UPDATE codegate_items SET cancelled=1, updated_at=? WHERE res_id=?", (_now(), rid))
    return gone


def get(res_id):
    rows = _q("SELECT * FROM codegate_items WHERE res_id=?", (str(res_id),))
    return _shape(rows[0]) if rows else None


def item_by_message(message_id):
    rows = _q("SELECT * FROM codegate_items WHERE card_message_id=?", (str(message_id),))
    return _shape(rows[0]) if rows else None


def day_items(day):
    return [_shape(r) for r in _q("SELECT * FROM codegate_items WHERE day=? "
                                  "ORDER BY checkin_at, res_id", (day,))]


def set_card(res_id, channel_id, message_id, card_hash):
    _x("UPDATE codegate_items SET channel_id=?, card_message_id=?, card_hash=?, updated_at=? "
       "WHERE res_id=?", (str(channel_id), str(message_id), card_hash, _now(), str(res_id)))


def set_hash(res_id, card_hash):
    _x("UPDATE codegate_items SET card_hash=? WHERE res_id=?", (card_hash, str(res_id)))


def set_replies(res_id, rules_at_iso, replies):
    blob = json.dumps([{"at": r.get("at"), "text": r.get("text")} for r in replies or []],
                      ensure_ascii=False)
    _x("UPDATE codegate_items SET rules_at=?, replies_json=?, updated_at=? WHERE res_id=?",
       (rules_at_iso, blob, _now(), str(res_id)))


def release(res_id, by_name, by_did, at_iso):
    n = _x("UPDATE codegate_items SET released_by=?, released_by_did=?, released_at=?, "
           "code_seen=NULL, code_check_at=NULL, code_warned_at=NULL, updated_at=? "
           "WHERE res_id=? AND released_at IS NULL AND cancelled=0",
           (by_name, str(by_did or ""), at_iso, _now(), str(res_id)))
    return n == 1


def undo(res_id, by_name, at_iso):
    n = _x("UPDATE codegate_items SET released_by=NULL, released_by_did=NULL, released_at=NULL, "
           "code_seen=NULL, code_check_at=NULL, code_warned_at=NULL, undone_by=?, undone_at=?, "
           "updated_at=? WHERE res_id=? AND released_at IS NOT NULL",
           (by_name, at_iso, _now(), str(res_id)))
    return n == 1


def stamp(res_id, column, at_iso):
    if column not in STAMP_COLUMNS:
        raise ValueError("codegate.db.stamp: column not allowed: %r" % column)
    _x("UPDATE codegate_items SET %s=?, updated_at=? WHERE res_id=?" % column,
       (at_iso, _now(), str(res_id)))


def set_code_seen(res_id, seen):
    _x("UPDATE codegate_items SET code_seen=? WHERE res_id=?", (1 if seen else 0, str(res_id)))


def header_posted(day, key):
    return bool(_q("SELECT 1 FROM codegate_headers WHERE day=? AND key=?", (day, str(key))))


def mark_header(day, key, message_id):
    _x("INSERT OR IGNORE INTO codegate_headers(day, key, message_id) VALUES (?,?,?)",
       (day, str(key), str(message_id or "")))


def event(res_id, kind, actor="", detail=""):
    _x("INSERT INTO codegate_events(res_id, at, kind, actor, detail) VALUES (?,?,?,?,?)",
       (str(res_id), _now(), kind, actor or "", detail or ""))
```

- [ ] **Step 4: Run to confirm it passes**

Run: `python3 -m unittest tests.test_codegate_db -v`
Expected: all `ok`.

- [ ] **Step 5: Commit**

```bash
git add codegate/db.py tests/test_codegate_db.py
git commit -m "feat(codegate): brain.db storage — one row per booking, first press wins

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Host bridge + flow (tick, press, undo)

**Files:**
- Create: `codegate/host.py`, `codegate/flow.py`
- Modify: `codegate/__init__.py`
- Test: `tests/test_codegate_flow.py`

**Interfaces:**
- Consumes: everything from Task 1 (`engine.*`) and Task 2 (`db.*`).
- Produces:
  - `HOST` with attributes, all filled by bot.py:
    - `now` `() -> aware datetime`
    - `state_path` `(name) -> str`
    - `today_arrivals` BLOCKING `() -> [{res_id, lid, day, unit, guest, conversation_id, checkin_at(iso)}]`, confirmed only
    - `messages` BLOCKING `(conversation_id) -> [{"inbound", "body", "at"}]`
    - `code_sent` BLOCKING `(conversation_id) -> bool`
    - `cover` BLOCKING `(lid, day) -> {name, did, role_id, owner_did}`
    - `channel` async `() -> channel id`
    - `post` async `(channel_id, text, embed=None, buttons=None) -> message id | None`
    - `edit` async `(channel_id, message_id, embed=None, buttons=None) -> bool`
    - `escalate` async `(title, detail) -> None`
  - `wire(caps: dict)`
  - `flow.enabled() -> bool`, `flow.is_gated(lid) -> bool`, `flow.released(res_id) -> bool`
  - `async flow.tick(now_=None, force=False) -> dict` (keys `seen, posted, edited, alerts, headers, cancelled, warned`)
  - `async flow.press_release(message_id, presser: dict) -> (bool, str)`: presser keys `name, did, is_admin, is_ops`
  - `async flow.press_undo(message_id, presser: dict) -> (bool, str)`
  - `async flow.run_blocking(fn, *args)`
  - Button keys used in `buttons=`: `"release"` and `"undo"`

- [ ] **Step 1: Write the failing flow tests**

```python
# tests/test_codegate_flow.py
# -*- coding: utf-8 -*-
"""«تسليم الرموز» flow against a fake Discord + fake Hostaway, a temp brain.db, injected now.
Run: python3 -m unittest tests.test_codegate_flow"""
import asyncio
import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain import db as bdb  # noqa: E402
from codegate import db, engine, flow  # noqa: E402
from codegate.host import HOST  # noqa: E402

TZ = engine.tz()
DAY = "2026-10-21"
GATED, OPEN = 461328, 999


def at(hh, mm=0):
    return datetime.datetime(2026, 10, 21, hh, mm, tzinfo=TZ)


def run(c):
    return asyncio.run(c)


class Fake:
    def __init__(self):
        self.posts, self.edits, self.escalations = [], [], []
        self.arrivals = [self.arr("r1", GATED), self.arr("r9", OPEN)]
        self.msgs = {"c-r1": [{"inbound": False, "at": at(8),
                               "body": 'Please reply "I agree to the house rules"'},
                              {"inbound": True, "at": at(8, 30), "body": "I agree"}]}
        self.code = {}
        self._mid = 1000

    @staticmethod
    def arr(rid, lid, hh=16):
        return {"res_id": rid, "lid": lid, "day": DAY, "unit": "U%s" % lid, "guest": "G" + rid,
                "conversation_id": "c-" + rid,
                "checkin_at": at(hh).isoformat(timespec="seconds")}

    async def post(self, ch, text, embed=None, buttons=None):
        self._mid += 1
        self.posts.append({"id": str(self._mid), "text": text, "embed": embed, "buttons": buttons})
        return str(self._mid)

    async def edit(self, ch, mid, embed=None, buttons=None):
        self.edits.append({"id": mid, "embed": embed, "buttons": buttons})
        return True

    async def escalate(self, title, detail):
        self.escalations.append(title)

    async def channel(self):
        return "900"


class FlowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cgf_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        units = os.path.join(self.tmp, "codegate_units.json")
        json.dump({"listing_ids": [GATED]}, open(units, "w"))
        self.f = Fake()
        self.now = at(9, 5)
        flow.wire_for_tests({
            "now": lambda: self.now,
            "state_path": lambda name: os.path.join(self.tmp, name),
            "today_arrivals": lambda: list(self.f.arrivals),
            "messages": lambda cid: list(self.f.msgs.get(cid, [])),
            "code_sent": lambda cid: bool(self.f.code.get(cid)),
            "cover": lambda lid, day: {"name": "نورة", "did": "11", "role_id": "",
                                       "owner_did": "22"},
            "channel": self.f.channel, "post": self.f.post, "edit": self.f.edit,
            "escalate": self.f.escalate,
        })

    def cards(self):
        return [p for p in self.f.posts if p["buttons"]]


class TestTick(FlowCase):
    def test_only_gated_units_get_cards(self):
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
        self.assertIn("U%s" % GATED, self.cards()[0]["embed"]["title"])
        self.assertIsNone(db.get("r9"))

    def test_nothing_posted_before_nine_unless_forced(self):
        self.now = at(8, 30)
        run(flow.tick())
        self.assertEqual(self.f.posts, [])
        run(flow.tick(force=True))
        self.assertEqual(len(self.cards()), 1)

    def test_header_mentions_coverer_once(self):
        run(flow.tick())
        headers = [p for p in self.f.posts if not p["buttons"]]
        self.assertEqual(len(headers), 1)
        self.assertIn("<@11>", headers[0]["text"])

    def test_tick_twice_and_restart_is_idempotent(self):
        run(flow.tick())
        db.reset_init_cache()                              # simulated redeploy
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
        self.assertEqual(len([p for p in self.f.posts if not p["buttons"]]), 1)
        self.assertEqual(self.f.edits, [])                 # unchanged content → no edit

    def test_new_reply_edits_card(self):
        run(flow.tick())
        self.f.msgs["c-r1"].append({"inbound": True, "at": at(9, 10), "body": "see you"})
        self.now = at(9, 20)
        run(flow.tick())
        self.assertEqual(len(self.f.edits), 1)
        self.assertIn("see you", json.dumps(self.f.edits[0]["embed"], ensure_ascii=False))

    def test_two_hour_then_late_alerts_once_each(self):
        run(flow.tick())
        self.now = at(14, 1)
        run(flow.tick())
        run(flow.tick())
        self.now = at(16, 2)
        run(flow.tick())
        run(flow.tick())
        self.assertEqual(len(self.f.escalations), 2)

    def test_tick_late_booking_alerts_once(self):
        self.now = at(17)
        self.f.arrivals = [self.f.arr("r2", GATED, hh=16)]
        run(flow.tick())
        run(flow.tick())
        self.assertEqual(len(self.f.escalations), 1)
        it = db.get("r2")
        self.assertTrue(it["alert_2h_at"] and it["alert_late_at"])

    def test_cancelled_after_card(self):
        run(flow.tick())
        self.f.arrivals = []
        self.now = at(14, 5)
        run(flow.tick())
        self.assertEqual(db.get("r1")["cancelled"], 1)
        self.assertEqual(self.f.escalations, [])
        self.assertEqual(self.f.edits[-1]["embed"]["color"], engine.COLOR_OFF)

    def test_disabled_does_nothing(self):
        os.environ["CODEGATE_ENABLED"] = "0"
        try:
            self.assertEqual(run(flow.tick()), {"skipped": "off"})
        finally:
            os.environ.pop("CODEGATE_ENABLED")


class TestPress(FlowCase):
    def setUp(self):
        super().setUp()
        run(flow.tick())
        self.mid = self.cards()[0]["id"]

    def p(self, did="11", admin=False, ops=False, name="نورة"):
        return {"name": name, "did": did, "is_admin": admin, "is_ops": ops}

    def test_coverer_releases_card_turns_green(self):
        ok, msg = run(flow.press_release(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(self.f.edits[-1]["embed"]["color"], engine.COLOR_DONE)
        self.assertEqual(db.get("r1")["released_by"], "نورة")

    def test_stranger_refused(self):
        ok, msg = run(flow.press_release(self.mid, self.p(did="77", name="x")))
        self.assertFalse(ok)
        self.assertIsNone(db.get("r1")["released_at"])

    def test_double_press_first_wins(self):
        run(flow.press_release(self.mid, self.p()))
        ok, msg = run(flow.press_release(self.mid, self.p(did="22", name="ناصر")))
        self.assertFalse(ok)
        self.assertIn("أُرسل من قبل", msg)

    def test_unknown_message(self):
        ok, msg = run(flow.press_release("424242", self.p()))
        self.assertFalse(ok)

    def test_release_stops_alerts(self):
        run(flow.press_release(self.mid, self.p()))
        self.now = at(16, 30)
        run(flow.tick())
        self.assertEqual(self.f.escalations, [])

    def test_honesty_warning_when_code_not_seen(self):
        self.now = at(13)
        run(flow.press_release(self.mid, self.p()))
        self.now = at(13, 20)
        run(flow.tick())
        warns = [p for p in self.f.posts if p["text"] and "ما شفت رسالة الرمز" in p["text"]]
        self.assertEqual(len(warns), 1)
        self.assertIn("<@11>", warns[0]["text"])
        run(flow.tick())
        self.assertEqual(len([p for p in self.f.posts
                              if p["text"] and "ما شفت رسالة الرمز" in p["text"]]), 1)

    def test_no_warning_when_code_seen(self):
        self.now = at(13)
        run(flow.press_release(self.mid, self.p()))
        self.f.code["c-r1"] = True
        self.now = at(13, 20)
        run(flow.tick())
        self.assertEqual(db.get("r1")["code_seen"], 1)
        self.assertFalse(any(p["text"] and "ما شفت" in p["text"] for p in self.f.posts))

    def test_undo_admin_only(self):
        run(flow.press_release(self.mid, self.p()))
        ok, _ = run(flow.press_undo(self.mid, self.p()))
        self.assertFalse(ok)
        ok, _ = run(flow.press_undo(self.mid, self.p(did="5", admin=True, name="Faisal")))
        self.assertTrue(ok)
        self.assertIsNone(db.get("r1")["released_at"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm failure**

Run: `python3 -m unittest tests.test_codegate_flow -v`
Expected: ERROR `cannot import name 'flow' from 'codegate'`

- [ ] **Step 3: Write `codegate/host.py`**

```python
# codegate/host.py
# -*- coding: utf-8 -*-
"""codegate.host — the ONE bridge to bot.py (checkout/host.py pattern). This package never
does `import bot`. BLOCKING hooks run on the package's own pool; Discord hooks are coroutines."""


class _Host:
    now = None             # () -> aware Riyadh datetime
    state_path = None      # (name) -> absolute path inside STATE_DIR
    today_arrivals = None  # BLOCKING () -> [{res_id, lid, day, unit, guest, conversation_id, checkin_at}]
    messages = None        # BLOCKING (conversation_id) -> [{inbound, body, at}]
    code_sent = None       # BLOCKING (conversation_id) -> bool   (bot.py's _was_code_sent_recently)
    cover = None           # BLOCKING (lid, day) -> {name, did, role_id, owner_did}
    channel = None         # async () -> channel id of «تسليم-الرموز» (fallback #escalations)
    post = None            # async (channel_id, text, embed=None, buttons=None) -> message id | None
    edit = None            # async (channel_id, message_id, embed=None, buttons=None) -> bool
    escalate = None        # async (title, detail) -> None   (bot.py's _post_system_escalation)


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        if not hasattr(HOST, k):
            raise AttributeError("codegate.wire: unknown capability %r" % k)
        setattr(HOST, k, v)
```

- [ ] **Step 4: Write `codegate/flow.py`**

```python
# codegate/flow.py
# -*- coding: utf-8 -*-
"""
codegate.flow — the tick and the two buttons of «تسليم الرموز».

The bot LISTS, RECORDS and ALERTS. It never decides that a guest agreed and never sends a code:
a person reads the quoted reply, sends the code from Hostaway's saved reply, and presses
«✅ وافق وأرسلت الرمز».
"""

import asyncio
import concurrent.futures
import datetime
import functools
import os

from . import db, engine
from .host import HOST, wire

_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="codegate")
_locks = {}
_units_cache = {"key": None, "ids": set()}
_REPO_UNITS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "units.json")


def wire_for_tests(caps):
    _units_cache.update({"key": None, "ids": set()})
    wire(caps)


def enabled():
    return os.environ.get("CODEGATE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def _state_units_path():
    try:
        return HOST.state_path("codegate_units.json") if HOST.state_path else None
    except Exception:
        return None


def units():
    """Gated listing ids, re-read when either file's mtime changes."""
    paths = [p for p in (_state_units_path(), _REPO_UNITS) if p]
    key = tuple((p, os.path.getmtime(p)) for p in paths if os.path.exists(p))
    if key != _units_cache["key"]:
        _units_cache.update({"key": key, "ids": engine.load_units(_REPO_UNITS,
                                                                   _state_units_path())})
    return _units_cache["ids"]


def is_gated(lid):
    try:
        return int(lid) in units()
    except (TypeError, ValueError):
        return False


def released(res_id):
    it = db.get(res_id) if res_id else None
    return bool(it and it.get("released_at"))


async def run_blocking(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_pool, functools.partial(fn, *args, **kwargs))


def _lock(name):
    if name not in _locks:
        _locks[name] = asyncio.Lock()
    return _locks[name]


def _dt(iso):
    if not iso:
        return None
    d = datetime.datetime.fromisoformat(str(iso))
    return d if d.tzinfo else d.replace(tzinfo=engine.tz())


def _view_item(it):
    """A db row in the shape engine.card/alert_due expect (datetimes, parsed replies)."""
    v = dict(it)
    v["checkin_at"] = _dt(it.get("checkin_at"))
    v["rules_at"] = _dt(it.get("rules_at"))
    v["replies"] = [{"at": _dt(r.get("at")), "text": r.get("text") or ""}
                    for r in (it.get("replies") or [])]
    return v


def _mention(it):
    if it.get("cover_did"):
        return "<@%s>" % it["cover_did"]
    if it.get("cover_role_id"):
        return "<@&%s>" % it["cover_role_id"]
    return ""


def _buttons(it):
    if it.get("cancelled"):
        return []
    return ["undo"] if it.get("released_at") else ["release"]


async def _render(it, now_, channel_id):
    """Post the card if it has none; edit it only when its content changed."""
    view = _view_item(it)
    embed = engine.card(view, now_)
    h = engine.content_hash({"e": embed, "b": _buttons(it)})
    if not it.get("card_message_id"):
        mid = await HOST.post(channel_id, _mention(it) or None, embed=embed, buttons=_buttons(it))
        if mid:
            await run_blocking(db.set_card, it["res_id"], channel_id, mid, h)
            await run_blocking(db.event, it["res_id"], "card_posted")
            return "posted"
        return None
    if h != it.get("card_hash"):
        ok = await HOST.edit(it.get("channel_id") or channel_id, it["card_message_id"],
                             embed=embed, buttons=_buttons(it))
        if ok:
            await run_blocking(db.set_hash, it["res_id"], h)
            return "edited"
    return None


async def tick(now_=None, force=False):
    if not enabled():
        return {"skipped": "off"}
    async with _lock("tick"):
        now_ = now_ or HOST.now()
        day = now_.date().isoformat()
        rep = {"seen": 0, "posted": 0, "edited": 0, "alerts": 0, "headers": 0,
               "cancelled": 0, "warned": 0}
        gated = await run_blocking(units)
        arrivals = await run_blocking(HOST.today_arrivals) or []
        keep = set()
        for a in arrivals:
            if str(a.get("day")) != day or not is_gated(a.get("lid")):
                continue
            cov = await run_blocking(HOST.cover, a["lid"], day) or {}
            await run_blocking(db.upsert_arrival, dict(a, res_id=str(a["res_id"]),
                                                       cover_name=cov.get("name") or "",
                                                       cover_did=cov.get("did") or "",
                                                       cover_role_id=cov.get("role_id") or "",
                                                       owner_did=cov.get("owner_did") or ""))
            keep.add(str(a["res_id"]))
        rep["seen"] = len(keep)
        rep["cancelled"] = len(await run_blocking(db.mark_cancelled, day, keep))
        if not gated or (not force and now_.hour < engine.START_HOUR):
            return rep
        channel_id = await HOST.channel()
        items = await run_blocking(db.day_items, day)
        # one header per person, before their first card
        groups = {}
        for it in items:
            if not it.get("cancelled"):
                k = it.get("cover_did") or it.get("cover_role_id") or it.get("cover_name") or "ops"
                groups.setdefault(k, []).append(it)
        for k, rows in groups.items():
            if await run_blocking(db.header_posted, day, k):
                continue
            mid = await HOST.post(channel_id, engine.header_text(_mention(rows[0]),
                                                                 rows[0].get("cover_name"),
                                                                 len(rows)))
            await run_blocking(db.mark_header, day, k, mid)
            rep["headers"] += 1
        for it in items:
            rid = it["res_id"]
            if not it.get("cancelled") and it.get("conversation_id"):
                msgs = await run_blocking(HOST.messages, it["conversation_id"]) or []
                r = engine.guest_replies(msgs)
                await run_blocking(
                    db.set_replies, rid,
                    r["rules_at"].isoformat(timespec="seconds") if r["rules_at"] else None,
                    [{"at": x["at"].isoformat(timespec="seconds") if x["at"] else None,
                      "text": x["text"]} for x in r["replies"]])
            it = await run_blocking(db.get, rid)
            # honesty check: pressed, but is the code really in the chat?
            if it.get("released_at") and it.get("code_seen") is None and not it.get("cancelled"):
                rel = _dt(it["released_at"])
                if rel and now_ >= rel + datetime.timedelta(minutes=engine.CODE_CHECK_MIN):
                    seen = await run_blocking(HOST.code_sent, it.get("conversation_id"))
                    await run_blocking(db.set_code_seen, rid, seen)
                    await run_blocking(db.stamp, rid, "code_check_at",
                                       now_.isoformat(timespec="seconds"))
                    if not seen and not it.get("code_warned_at"):
                        who = ("<@%s>" % it["released_by_did"]) if it.get("released_by_did") else ""
                        await HOST.post(channel_id, (who + " " if who else "") +
                                        "⚠️ ضُغط الزر على **%s** بس ما شفت رسالة الرمز في "
                                        "المحادثة — تأكد إنها انرسلت." % (it.get("unit") or ""))
                        await run_blocking(db.stamp, rid, "code_warned_at",
                                           now_.isoformat(timespec="seconds"))
                        rep["warned"] += 1
                    it = await run_blocking(db.get, rid)
            kind = engine.alert_due(_view_item(it), now_)
            if kind:
                stamp = now_.isoformat(timespec="seconds")
                await run_blocking(db.stamp, rid, "alert_late_at" if kind == "late"
                                   else "alert_2h_at", stamp)
                if kind == "late" and not it.get("alert_2h_at"):
                    await run_blocking(db.stamp, rid, "alert_2h_at", stamp)
                text = engine.alert_text(kind, _view_item(it), _mention(it))
                await HOST.post(channel_id, text)
                await HOST.escalate(("🔑 باقي ساعتين وما أُرسل الرمز · " if kind == "2h"
                                     else "🚨 حلّ الدخول وما أُرسل الرمز · ") + (it.get("unit") or ""),
                                    text)
                await run_blocking(db.event, rid, "alert_" + kind)
                rep["alerts"] += 1
                it = await run_blocking(db.get, rid)
            res = await _render(it, now_, channel_id)
            if res:
                rep[res] += 1
        return rep


async def _rerender(res_id):
    it = await run_blocking(db.get, res_id)
    if it:
        await _render(it, HOST.now(), it.get("channel_id"))


async def press_release(message_id, presser):
    it = await run_blocking(db.item_by_message, message_id)
    if not it:
        return False, "ما لقيت هذا الحجز في السجل."
    if it.get("cancelled"):
        return False, "الحجز ملغي — ما يحتاج رمز."
    if it.get("released_at"):
        return False, "أُرسل من قبل — %s %s" % (it.get("released_by") or "",
                                                str(it["released_at"])[11:16])
    if not engine.may_release(presser.get("did"), it.get("cover_did"), it.get("owner_did"),
                              presser.get("is_admin"), presser.get("is_ops")):
        return False, "هذي الشقة على %s اليوم — هو أو المشرف يضغط الزر." % (
            it.get("cover_name") or "فريق العمليات")
    now_ = HOST.now().isoformat(timespec="seconds")
    if not await run_blocking(db.release, it["res_id"], presser.get("name") or "",
                              presser.get("did") or "", now_):
        fresh = await run_blocking(db.get, it["res_id"])
        return False, "أُرسل من قبل — %s" % ((fresh or {}).get("released_by") or "")
    await run_blocking(db.event, it["res_id"], "released", presser.get("name") or "")
    await _rerender(it["res_id"])
    return True, "تم ✅ — سجّلت إنك أرسلت الرمز."


async def press_undo(message_id, presser):
    if not presser.get("is_admin"):
        return False, "التراجع للمشرفين فقط."
    it = await run_blocking(db.item_by_message, message_id)
    if not it or not it.get("released_at"):
        return False, "ما فيه تسليم أتراجع عنه."
    await run_blocking(db.undo, it["res_id"], presser.get("name") or "",
                       HOST.now().isoformat(timespec="seconds"))
    await run_blocking(db.event, it["res_id"], "undone", presser.get("name") or "")
    await _rerender(it["res_id"])
    return True, "تم التراجع — رجعت البطاقة بانتظار التسليم."
```

- [ ] **Step 5: Fill in `codegate/__init__.py`**

```python
# -*- coding: utf-8 -*-
"""
codegate — «تسليم الرموز». On gated listings the guest replies «أوافق» to the house-rules
message and the employee covering the unit that day releases the door code BY HAND.

    engine.py — PURE: replies, alerts, permission, every word
    db.py     — codegate_* tables in brain.db
    host.py   — HOST bridge filled by bot.py (codegate.wire)
    flow.py   — tick + the two buttons

The bot never decides agreement and never sends a code (owner ruling 2026-10-21).
"""

from . import engine, db, flow  # noqa: F401
from .host import HOST, wire  # noqa: F401

__all__ = ["engine", "db", "flow", "HOST", "wire", "bootstrap"]


def bootstrap():
    try:
        db._ensure()
        print("[codegate] enabled=%s units=%d" % (int(flow.enabled()), len(flow.units())))
    except Exception as e:
        print("[codegate] bootstrap error:", e)
```

- [ ] **Step 6: Run the flow, db and engine tests**

Run: `python3 -m unittest tests.test_codegate_engine tests.test_codegate_db tests.test_codegate_flow -v`
Expected: all `ok`.

- [ ] **Step 7: Commit**

```bash
git add codegate/ tests/test_codegate_flow.py
git commit -m "feat(codegate): daily list tick, release/undo buttons, alerts, honesty check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: bot.py wiring: Hostaway reads, Discord, view, loop, command

**Files:**
- Modify: `bot.py`. Each insertion point is named by an anchor string; re-read the surrounding lines right before each edit (CLAUDE.md trap 5):
  - import block: right after the `checkout` import block (anchor `import checkout as _checkout`, ~line 335)
  - bridge functions + view + loop + command: right after `async def checkout_watch_loop():` and its body (~9394–9409)
  - `bot.add_view(CodegateView())`: right after `bot.add_view(ReadyNotifyConfirmView())` (~75653)
  - loop start: right after the `checkout_watch_loop` append (~75815)
- Test: `tests/test_codegate_bot.py`

**Interfaces:**
- Consumes: `codegate.wire`, `codegate.flow.tick/press_release/press_undo/run_blocking/is_gated/released`, `codegate.engine.LABEL_RELEASE/LABEL_UNDO/CONFIRM_TEXT`. Existing bot.py helpers: `_ha_reservations_window`, `CONFIRMED_STATUSES`, `get_listings_map`, `parse_hour`, `unit_checkin_minutes`, `api_get`, `_msg_is_inbound`, `_msg_time`, `_parse_msg_dt`, `_was_code_sent_recently`, `_cw_cover`, `_ops_did_for`, `_schedule`, `_HAS_SCHEDULE`, `_HAS_OPS`, `_cw_embed`, `_cw_channel`, `_cw_presser_name`, `_cw_reply`, `_tk_is_admin`, `find_operation_role`, `ensure_channel`, `get_assistant_category`, `ESCALATION_CHANNEL`, `_post_system_escalation`, `_state_path`, `now_riyadh`, `GUILD_ID`, `_HAS_BRAIN`.
- Produces: `_HAS_CODEGATE`, `_codegate`, `_cg_gated(lid) -> bool`, `_cg_released(res_id) -> bool` (used by Task 5), `CodegateView`, `codegate_loop`.

- [ ] **Step 1: Write the failing bot tests**

```python
# tests/test_codegate_bot.py
# -*- coding: utf-8 -*-
"""«تسليم الرموز» — bot.py side. Run: python3 -m unittest tests.test_codegate_bot"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-cg")
os.makedirs("/tmp/ouja-test-state-cg", exist_ok=True)

import bot  # noqa: E402
sys.stdout.flush()


class TestWiring(unittest.TestCase):
    def test_package_imported_and_wired(self):
        self.assertTrue(bot._HAS_CODEGATE)
        self.assertTrue(bot._cg_wire())
        self.assertIsNotNone(bot._codegate.HOST.today_arrivals)
        self.assertIsNotNone(bot._codegate.HOST.escalate)

    def test_view_custom_ids_are_persistent(self):
        v = bot.CodegateView()
        ids = sorted(c.custom_id for c in v.children)
        self.assertEqual(ids, ["cg_release", "cg_undo"])
        self.assertIsNone(v.timeout)

    def test_gated_helpers(self):
        self.assertTrue(bot._cg_gated(461328))       # C2 NFL
        self.assertTrue(bot._cg_gated("526697"))     # 103 NRJS (owner decision)
        self.assertFalse(bot._cg_gated(999999))
        self.assertFalse(bot._cg_gated(None))

    def test_messages_shape(self):
        orig = bot.api_get
        bot.api_get = lambda path, params=None: {"result": [
            {"isIncoming": 1, "body": "I agree", "date": "2026-10-21 10:05:00"},
            {"isIncoming": 0, "body": "rules", "date": "2026-10-21 10:00:00"}]}
        try:
            rows = bot._cg_messages("c1")
        finally:
            bot.api_get = orig
        self.assertEqual(rows[0]["inbound"], True)
        self.assertEqual(rows[0]["at"].hour, 10)
        self.assertEqual(rows[1]["inbound"], False)

    def test_today_arrivals_filters_and_shapes(self):
        orig_ci, orig_lm = bot.unit_checkin_minutes, bot.get_listings_map
        bot.unit_checkin_minutes = lambda lid: 15 * 60
        bot.get_listings_map = lambda: {461328: "C2 NFL"}
        self.addCleanup(lambda: setattr(bot, "unit_checkin_minutes", orig_ci))
        self.addCleanup(lambda: setattr(bot, "get_listings_map", orig_lm))
        orig = bot._ha_reservations_window
        bot._ha_reservations_window = lambda *a: [
            {"id": 1, "status": "new", "arrivalDate": bot.now_riyadh().date().isoformat(),
             "listingMapId": 461328, "guestName": "Sara", "conversationId": 7, "checkInTime": 16},
            {"id": 2, "status": "cancelled", "arrivalDate": bot.now_riyadh().date().isoformat(),
             "listingMapId": 461328}]
        try:
            rows = bot._cg_today_arrivals()
        finally:
            bot._ha_reservations_window = orig
        self.assertEqual([r["res_id"] for r in rows], ["1"])
        self.assertTrue(rows[0]["checkin_at"].endswith("16:00:00+03:00"))
        self.assertEqual(rows[0]["conversation_id"], "7")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm failure**

Run: `python3 -m unittest tests.test_codegate_bot -v`
Expected: FAIL/ERROR `module 'bot' has no attribute '_HAS_CODEGATE'`

- [ ] **Step 3: Add the import block right after the checkout import block**

```python
# «تسليم الرموز» — on gated listings the guest replies «أوافق» to the house-rules message and
# the employee covering the unit that day releases the door code BY HAND. The bot lists,
# records and alerts; it never decides agreement and never sends a code. Additive; brain.db.
try:
    import codegate as _codegate
    _HAS_CODEGATE = True
except Exception as _cg_err:            # pragma: no cover
    print("[codegate] import failed (code release list disabled, bot unaffected):", _cg_err)
    _codegate = None
    _HAS_CODEGATE = False
```

- [ ] **Step 4: Add the bridge, view, loop and command right after `checkout_watch_loop`'s body**

```python
# ---------------- «تسليم الرموز» — bot.py side of the codegate package ----------------

def _cg_gated(lid):
    """True when this listing is on the manual code-release list. Never raises."""
    if not _HAS_CODEGATE or lid in (None, ""):
        return False
    try:
        return _codegate.flow.is_gated(lid)
    except Exception:
        return False


def _cg_released(res_id):
    if not _HAS_CODEGATE or not res_id:
        return False
    try:
        return _codegate.flow.released(res_id)
    except Exception:
        return False


def _cg_today_arrivals():
    """Every CONFIRMED arrival today from a targeted arrival-window query (never the truncated
    cache — CLAUDE.md trap 4). BLOCKING."""
    today = datetime.now(TZ).date()
    iso = today.isoformat()
    listings = get_listings_map() or {}
    out, seen = [], set()
    for r in _ha_reservations_window("arrivalStartDate", "arrivalEndDate", iso, iso) or []:
        if (r.get("status") or "").lower() not in CONFIRMED_STATUSES:
            continue
        if str(r.get("arrivalDate") or "")[:10] != iso or r.get("id") in seen:
            continue
        seen.add(r.get("id"))
        lid = r.get("listingMapId")
        if not lid:
            continue
        try:
            default_h = unit_checkin_minutes(lid) // 60
        except Exception:
            default_h = 16
        hour = parse_hour(r.get("checkInTime"), default_h)
        ci = datetime(today.year, today.month, today.day, min(hour, 23), 0, tzinfo=TZ)
        out.append({"res_id": str(r.get("id")), "lid": lid, "day": iso,
                    "unit": listings.get(lid) or r.get("listingName") or "unit-%s" % lid,
                    "guest": r.get("guestName") or r.get("guestFirstName") or "ضيف",
                    "conversation_id": str(r.get("conversationId") or ""),
                    "checkin_at": ci.isoformat(timespec="seconds")})
    return out


def _cg_messages(conversation_id):
    """The chat as {inbound, body, at} for codegate.engine.guest_replies. BLOCKING."""
    if not conversation_id:
        return []
    try:
        data = api_get(f"/conversations/{conversation_id}/messages")
    except Exception as e:
        print("[codegate] messages fetch failed:", e)
        return []
    return [{"inbound": _msg_is_inbound(m), "body": m.get("body") or "",
             "at": _parse_msg_dt(_msg_time(m))} for m in (data.get("result") or [])]


def _cg_cover(lid, day):
    """Today's coverer (Employee Calendar → room topic → assignments → ops role, via _cw_cover)
    plus the permanent owner's Discord id, who may also press the button."""
    c = _cw_cover(lid, day)
    owner_did = ""
    if _HAS_SCHEDULE and _schedule and _HAS_OPS:
        try:
            owner = _schedule.owners.owner_for(listing_id=lid)
            owner_did = _ops_did_for(owner) if owner else ""
        except Exception as e:
            print("[codegate] owner lookup failed:", e)
    return {"name": c.get("name") or "", "did": c.get("did") or "",
            "role_id": c.get("role_id") or "", "owner_did": owner_did or ""}


async def _cg_channel():
    """«تسليم-الرموز»; #escalations if Discord refuses a new channel (the 500-channel cap)."""
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return None
    category = await get_assistant_category(guild)
    ch = None
    try:
        ch = await ensure_channel(guild, "تسليم-الرموز", category)
    except Exception as e:
        print("[codegate] channel create refused, falling back to escalations:", e)
    if ch is None:
        ch = await ensure_channel(guild, ESCALATION_CHANNEL, category)
    return str(ch.id) if ch is not None else None


_CG_LABEL = {"release": ("cg_release", discord.ButtonStyle.success),
             "undo": ("cg_undo", discord.ButtonStyle.secondary)}


def _cg_view(buttons):
    v = discord.ui.View(timeout=None)
    for b in buttons or []:
        cid, style = _CG_LABEL[b]
        label = _codegate.engine.LABEL_RELEASE if b == "release" else _codegate.engine.LABEL_UNDO
        v.add_item(discord.ui.Button(label=label, style=style, custom_id=cid))
    return v


async def _cg_post(channel_id, text, embed=None, buttons=None):
    if not channel_id:
        return None
    ch = await _cw_channel(channel_id)
    kw = {}
    if embed:
        kw["embed"] = _cw_embed(embed)
    if buttons:
        kw["view"] = _cg_view(buttons)
    msg = await ch.send(content=text, allowed_mentions=discord.AllowedMentions(
        users=True, roles=True, everyone=False), **kw)
    return str(msg.id)


async def _cg_edit(channel_id, message_id, embed=None, buttons=None):
    try:
        ch = await _cw_channel(channel_id)
        kw = {"view": _cg_view(buttons) if buttons else None}
        if embed is not None:
            kw["embed"] = _cw_embed(embed)
        await ch.get_partial_message(int(message_id)).edit(**kw)
        return True
    except (discord.NotFound, discord.Forbidden):
        return False
    except Exception as e:
        print("[codegate] edit failed:", e)
        return False


async def _cg_escalate(title, detail):
    await _post_system_escalation(title=title, detail=detail, severity="high")


def _cg_wire():
    if not _HAS_CODEGATE:
        return False
    _codegate.wire({
        "now": now_riyadh,
        "state_path": _state_path,
        "today_arrivals": _cg_today_arrivals,
        "messages": _cg_messages,
        "code_sent": (lambda cid: _was_code_sent_recently(cid, since_hours=24)),
        "cover": _cg_cover,
        "channel": _cg_channel,
        "post": _cg_post,
        "edit": _cg_edit,
        "escalate": _cg_escalate,
    })
    return True


def _cg_ready():
    """Usable the moment Discord is (brain.db folder hand-over — the _cw_ready lesson)."""
    if not _HAS_CODEGATE:
        return False
    if _HAS_BRAIN:
        try:
            from brain.host import HOST as _brain_host
            if _brain_host.state_path is None:
                _brain_host.state_path = _state_path
        except Exception as e:
            print("[codegate] brain path hand-over failed:", e)
    if _codegate.HOST.today_arrivals is None:
        _cg_wire()
    return True


def _cg_presser(interaction):
    user = interaction.user
    guild = interaction.guild
    role = find_operation_role(guild) if guild is not None else None
    roles = getattr(user, "roles", None) or []
    return {"name": _cw_presser_name(user), "did": str(user.id),
            "is_admin": _tk_is_admin(user),
            "is_ops": bool(role is not None and any(r.id == role.id for r in roles))}


class CodegateConfirmView(discord.ui.View):
    """The ask-again step: a written «أوافق» in the chat AND the code sent from Hostaway."""

    def __init__(self, message_id):
        super().__init__(timeout=120)
        self.message_id = str(message_id)

    @discord.ui.button(label="نعم، كتب «أوافق» وأرسلت الرمز", style=discord.ButtonStyle.success)
    async def yes(self, interaction, button):
        ok, msg = await _codegate.flow.press_release(self.message_id, _cg_presser(interaction))
        await _cw_reply(interaction, msg)

    @discord.ui.button(label="لا، رجوع", style=discord.ButtonStyle.secondary)
    async def no(self, interaction, button):
        await _cw_reply(interaction, "تمام، ما سجّلت شي. لو الضيف رد بالتلفون اطلب منه يكتب "
                                     "«أوافق» في المحادثة أولاً.")


class CodegateView(discord.ui.View):
    """Persistent card buttons. The card's message id IS the key (looked up in codegate.db),
    so one registration serves every card across redeploys."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ وافق وأرسلت الرمز", style=discord.ButtonStyle.success,
                       custom_id="cg_release")
    async def release(self, interaction, button):
        if not _cg_ready():
            return await _cw_reply(interaction, "الميزة مو شغالة الحين.")
        await _cw_reply(interaction, _codegate.engine.CONFIRM_TEXT,
                        view=CodegateConfirmView(interaction.message.id))

    @discord.ui.button(label="↩️ تراجع", style=discord.ButtonStyle.secondary,
                       custom_id="cg_undo")
    async def undo(self, interaction, button):
        if not _cg_ready():
            return await _cw_reply(interaction, "الميزة مو شغالة الحين.")
        ok, msg = await _codegate.flow.press_undo(interaction.message.id, _cg_presser(interaction))
        await _cw_reply(interaction, msg)


@tasks.loop(minutes=int(os.environ.get("CODEGATE_TICK_MIN", "10")))
async def codegate_loop():
    """Every 10 min: today's gated arrivals → header + cards (from 09:00), reply refresh,
    2-hour / check-in alerts, the honesty check after a press."""
    if not _HAS_CODEGATE:
        return
    await bot.wait_until_ready()
    try:
        _cg_ready()
        rep = await _codegate.flow.tick()
        if rep.get("posted") or rep.get("alerts") or rep.get("warned"):
            print("[codegate] tick:", rep)
    except Exception as e:
        print("[codegate] loop error:", e)


@bot.command(name="رموز", aliases=["codegate"])
async def codegate_cmd(ctx):
    """!ouja رموز — admin: run one pass now (ignores the 09:00 start) and report."""
    if not _tk_is_admin(ctx.author):
        return await ctx.reply("للمشرفين فقط.")
    if not _cg_ready():
        return await ctx.reply("تسليم الرموز مو مفعّل.")
    rep = await _codegate.flow.tick(force=True)
    await ctx.reply("تسليم الرموز · " + ", ".join("%s=%s" % kv for kv in rep.items()))
```

The command decorator follows the existing convention (`@bot.command(name="تشغيل-الخروج", aliases=["checkout-start"])`, bot.py ~9592).

- [ ] **Step 5: Register the view and start the loop**

Right after `bot.add_view(ReadyNotifyConfirmView())`:

```python
    if _HAS_CODEGATE:
        bot.add_view(CodegateView())     # «تسليم الرموز» release/undo (message id = key)
```

Right after the `checkout_watch_loop` append:

```python
    if _HAS_CODEGATE and not codegate_loop.is_running():
        _pending.append(codegate_loop)          # «تسليم الرموز»: list from 09:00, alerts
```

- [ ] **Step 6: Run the bot tests and the compile check**

Run:
```bash
cd /Users/faisalouja/ouja-wt-agree
python3 -W error::SyntaxWarning -m py_compile bot.py && python3 -m unittest tests.test_codegate_bot -v
```
Expected: compile silent; all tests `ok`.

- [ ] **Step 7: Commit**

```bash
git add bot.py tests/test_codegate_bot.py
git commit -m "feat(codegate): wire into bot.py — Hostaway reads, channel, persistent buttons, loop, !ouja رموز

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Existing agreement behaviour, gated units only

**Files:**
- Modify: `bot.py`. Re-read each spot before editing:
  - `_check_agreement_for_one` (anchor `def _check_agreement_for_one(r, now):`, ~3025)
  - `compute_arrivals_with_status` (anchor `"signed": _is_agreement_signed(r),`, ~3824)
  - Musaed code context (anchor `needs_agr = _unit_requires_agreement(listing_id) if listing_id else True`, ~12890, and the `if needs_agr and not signed:` branch ~12955)
  - Musaed system prompt ANTI-NAG (anchor `the rental-agreement status: if it is already SIGNED`, ~11155)
- Test: `tests/test_codegate_bot.py` (append)

**Interfaces:**
- Consumes: `_cg_gated(lid)`, `_cg_released(res_id)` from Task 4.
- Produces: nothing new.

- [ ] **Step 1: Append the failing regression tests**

```python
class TestGatedBehaviour(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._send = bot.send_guest_message
        bot.send_guest_message = lambda cid, body, kind="email": self.sent.append(body)
        self._req = bot._unit_requires_agreement
        bot._unit_requires_agreement = lambda lid: True
        self._url = bot.find_agreement_url
        bot.find_agreement_url = lambda cid: "https://sign.example/x"
        self._lm = bot.get_listings_map
        bot.get_listings_map = lambda: {}
        if bot.datetime.now(bot.TZ).hour >= 23:
            self.skipTest("needs a check-in hour later today")

    def tearDown(self):
        bot.send_guest_message = self._send
        bot._unit_requires_agreement = self._req
        bot.find_agreement_url = self._url
        bot.get_listings_map = self._lm

    def res(self, lid):
        now = bot.datetime.now(bot.TZ)
        return {"id": 77, "status": "new", "arrivalDate": now.date().isoformat(),
                "listingMapId": lid, "guestName": "Sara", "conversationId": 5,
                "checkInTime": min(now.hour + 1, 23), "reservationAgreement": "not_signed"}

    def test_old_reminder_skips_gated_units(self):
        bot._agreement_reminded.discard(77)
        self.assertFalse(bot._check_agreement_for_one(self.res(461328), bot.datetime.now(bot.TZ)))
        self.assertEqual(self.sent, [])

    def test_old_reminder_unchanged_for_other_units(self):
        bot._agreement_reminded.discard(77)
        bot._check_agreement_for_one(self.res(999999), bot.datetime.now(bot.TZ))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("https://sign.example/x", self.sent[0])
        bot._agreement_reminded.discard(77)

    def test_musaed_prompt_mentions_agree_rule(self):
        self.assertIn("أوافق", bot.SYSTEM_PROMPT_ANTI_NAG_GATED)

    def test_musaed_gated_block_wording(self):
        txt = bot._cg_code_rule(released=False, hrs=3)
        self.assertIn("أوافق", txt)
        self.assertNotIn("العقد", txt)
        self.assertNotIn("توقيع", txt)
        self.assertIn("action='reply'", txt)
        done = bot._cg_code_rule(released=True, hrs=3)
        self.assertIn("أرسل الرمز", done)
```

Before writing the last two tests, check the real system-prompt constant name: `grep -n "ANTI-NAG (important)" bot.py`, and the variable that holds that prompt. Insert `SYSTEM_PROMPT_ANTI_NAG_GATED` as a new module-level constant (Step 3c). Do not rename anything that exists.

- [ ] **Step 2: Run to confirm failure**

Run: `python3 -m unittest tests.test_codegate_bot -v`
Expected: `test_old_reminder_skips_gated_units` FAILS (one message sent); the two Musaed tests ERROR (missing names).

- [ ] **Step 3a: `_check_agreement_for_one`: early return for gated units**

Directly after the `if not res_id: return False` lines:

```python
    if _cg_gated(r.get("listingMapId")):
        return False    # «تسليم الرموز» owns gated units: «أوافق» + manual code, its own alerts
```

- [ ] **Step 3b: `compute_arrivals_with_status`: release status replaces "signed" for gated units**

Replace the line `"signed": _is_agreement_signed(r),` with:

```python
            "signed": (_cg_released(r.get("id")) if _cg_gated(lid)
                       else _is_agreement_signed(r)),
```

(`lid` is already defined in that loop; confirm by reading the lines above the edit.) The monitoring room (`"signed": bool(a.get("signed"))`) and `/update` (`agr = "signed" if a.get("signed")`) inherit it unchanged.

- [ ] **Step 3c: Musaed wording**

Add the module-level helper and constant near `_check_agreement_for_one`:

```python
SYSTEM_PROMPT_ANTI_NAG_GATED = (
    "For units where the context says the guest must reply «أوافق» to the house-rules message, "
    "never mention a contract, a signature or a signing link: ask them (once) to reply «أوافق» "
    "to the house-rules message in this chat, and say the team sends the code after that.")


def _cg_code_rule(released, hrs):
    """Musaed's code-question rule on a «تسليم الرموز» unit. Never a contract, never a time
    promise, never a code."""
    if released:
        return ("- الفريق سجّل إنه أرسل الرمز ✅. وجّه الضيف يشوف آخر رسائل الفريق في المحادثة؛ "
                "لو ما لقاه **action='escalate'** عشان الفريق يعيد الإرسال.")
    return ("- هذي الوحدة: الرمز يرسله الفريق **بعد** ما يرد الضيف على رسالة قواعد الشقة بكلمة "
            "«أوافق». لو ما رد، اطلب منه بلطف يرد عليها بـ«أوافق على قواعد الشقة» هنا في المحادثة، "
            "وقل إن الفريق يرسل الرمز بعدها. لا تطلب منه أي شي ثاني ولا تحدد وقت. action='reply'.")
```

Append `SYSTEM_PROMPT_ANTI_NAG_GATED` to the prompt text right after the existing ANTI-NAG bullet (keep the old bullet; non-gated units still use it), following the prompt's own string-joining style.

In the Musaed code-question block, right after `needs_agr = ...`, add:

```python
            gated = _cg_gated(listing_id)
```

Change the status line inside `code_block` from

```python
                    f"- " + ("هذه الوحدة **لا تتطلّب** عقد توقيع." if not needs_agr
                            else ("العقد موقّع ✅" if signed else "العقد غير موقّع ❌")) + "\n"
```

to

```python
                    f"- " + (("الضيف لازم يرد «أوافق» على رسالة القواعد؛ "
                              + ("الفريق أرسل الرمز ✅" if _cg_released(reservation_id)
                                 else "الفريق ما سجّل إرسال الرمز بعد ⏳")) if gated
                             else "هذه الوحدة **لا تتطلّب** عقد توقيع." if not needs_agr
                             else ("العقد موقّع ✅" if signed else "العقد غير موقّع ❌")) + "\n"
```

and put a gated branch first in the how-to-reply chain:

```python
                if gated:
                    code_block += _cg_code_rule(_cg_released(reservation_id), hrs)
                elif needs_agr and not signed:
```

(the old `if needs_agr and not signed:` becomes `elif`; the rest of the chain is unchanged).

- [ ] **Step 4: Run all codegate tests + the existing firewall and Musaed tests**

Run:
```bash
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m unittest tests.test_codegate_bot tests.test_codegate_flow tests.test_codegate_db tests.test_codegate_engine -v
ls tests | grep -i -E "firewall|musaed|agreement|watchdog"
```
Then run every file that the `ls` lists with `python3 -m unittest tests.<name> -v`.
Expected: all `ok`.

- [ ] **Step 5: Commit**

```bash
git add bot.py tests/test_codegate_bot.py
git commit -m "feat(codegate): gated units leave the e-sign flow — no signing reminders, Musaed asks for «أوافق», status shows release

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Full verification, then ask the owner to deploy

**Files:** none new.

- [ ] **Step 1: Run the CLAUDE.md routine (do not pipe unittest through `tail`; it hides the exit code)**

```bash
cd /Users/faisalouja/ouja-wt-agree
rm -rf __pycache__
python3 -W error::SyntaxWarning -m py_compile bot.py
python3 -m pyflakes bot.py finance/*.py codegate/*.py
PATH="$HOME/.local/node/bin:$PATH" node --check finance/static/erp.js
python3 -m unittest discover -s tests -p "test_*.py"; echo "EXIT=$?"
```

Expected: compile silent; pyflakes shows no new warnings in `codegate/` and none new in bot.py (compare with `git stash`-free baseline: `git diff origin/main --stat` lists only our files); `node --check` silent; `EXIT=0`. If a test unrelated to codegate fails, run the same test on a clean `origin/main` checkout to prove it was already red (the date-dependent-tests memory), and report it to the owner instead of "fixing" it.

- [ ] **Step 2: Synthetic-data run (CLAUDE.md asks for one for any new computation)**

```bash
python3 -m unittest tests.test_codegate_flow -v
```

Expected: all `ok`. These tests feed fake reservations and chats through the real flow and assert the numbers.

- [ ] **Step 3: Show the owner the diff summary and ask for the push**

```bash
git log --oneline origin/main..HEAD
git diff --stat origin/main..HEAD
```

Tell the owner in plain words what goes live: a new channel «تسليم-الرموز», a morning list from 09:00, buttons, alerts. No guest message changes until Task 8. Ask: "Push now?" **Wait for an explicit yes.**

- [ ] **Step 4: On yes, push to main**

```bash
git fetch origin
git rebase origin/main
python3 -m unittest discover -s tests -p "test_*.py"; echo "EXIT=$?"
git push origin HEAD:main
```

Expected: `EXIT=0` before the push. If the rebase pulled in new commits, re-run Step 1 fully first.

- [ ] **Step 5: Live check after Railway restarts**

In Discord run `!ouja رموز`. Expected reply: `تسليم الرموز · seen=<n>, posted=<n>, …` with no error, and the channel «تسليم-الرموز» exists (or the cards appear in #escalations, with the fallback noted to the owner). Each card shows today's gated arrivals tagged to the right person; the owner confirms the names.

---

### Task 7: Soak day with the old flow still on

**Files:** none.

- [ ] **Step 1:** For 1–2 days, Hostaway still sends the old agreement and auto-code messages. The cards will mostly show «ما لقيت رسالة القواعد» (expected: the new message isn't live yet) and the honesty check will see the auto-sent codes.
- [ ] **Step 2:** Each morning, check with the owner that every card landed on the right person and that no card is missing compared with Hostaway's arrivals for the 35 units. Fix calendar or `units.json` mismatches before Task 8.

---

### Task 8: The Hostaway switch (Chrome extension, owner approves each change)

**Files:** none in the repo. All changes in `dashboard.hostaway.com`. Before each **Save**, show the owner a screenshot of exactly what will be saved and wait for "yes".

- [ ] **Step 1: Saved reply «🔑 كود الدخول / Door code».** Message Templates → new template. Body:

```
🔑 كود الدخول: {{door_code}} ثم #
يشتغل الكود من وقت الدخول — لو احتجت أي شي حنا هنا 🤍

🔑 Door code: {{door_code}} then #
The code works from check-in time — anything you need, we're right here 🤍
```

Test on one real arriving gated booking with the owner watching: insert the template in its chat and check the code fills in before sending. If `{{door_code}}` comes out empty, stop and tell the owner (the code may live in the smart-lock integration instead).

- [ ] **Step 2: Rewrite automation 288752** (`/messages/automations/288752`):
  - Name: `house rules – I agree`; Subject: `house rules`.
  - Default message: the full bilingual text from spec §4.1, verbatim.
  - Event trigger: **At Reservation** (owner decision).
  - Listings: keep the 34 and **add 103 NRJS (526697)**.
  - Channels unchanged. Screenshot → owner yes → Save.
- [ ] **Step 3: Turn off 438108** ("arrival is less than an hour away"): toggle on the Automations list → owner yes.
- [ ] **Step 4: Turn off 427132** ("Doorcodera"): toggle → owner yes. From this moment, codes on these units go out by hand.
- [ ] **Step 5: House rules field** on each of the 35 listings (Listings → listing → Edit → House rules): replace with the Airbnb-safe text (spec §4.1 step 5 / the Requests text agreed earlier), without the fine or the contract line; also remove the fine sentence from C2 NFL's description. One listing first, owner yes, then the rest. Report the count done.
- [ ] **Step 6: End-to-end test on one booking:** rules message arrives → the guest replies → the card quotes it → the employee sends the saved reply → presses the button → the card turns green → 15 minutes later there's no warning.
- [ ] **Step 7: Write the undo note for the owner:** turn 438108 and 427132 back on; restore 288752's old text (saved copy in `docs/superpowers/specs/2026-10-21-house-rules-code-release-design.md` §3 + the screenshots); set `CODEGATE_ENABLED=0` or revert the codegate commits.

---

## Self-Review Notes

- Spec coverage: §4.1 → Task 8; §4.2 units/list/coverer/refresh/button/honesty/alerts/storage/switch → Tasks 1–4; §4.3 → Task 5; §5 rollout → Tasks 6–8; §6 decisions → units.json (103 NRJS), Task 8 Step 2 (At Reservation), confirm text (typed «أوافق»); §7 tests → Tasks 1–5.
- Names are consistent across tasks: `is_gated`, `released`, `press_release`, `press_undo`, `tick(force=)`, `set_code_seen`, `STAMP_COLUMNS`, button keys `release` and `undo`, custom ids `cg_release` and `cg_undo`.
- One named lookup is left to the implementer: the variable that holds Musaed's system prompt (Task 5 Step 1, `grep -n "ANTI-NAG (important)" bot.py`), so the new constant is appended in that prompt's own string style.
