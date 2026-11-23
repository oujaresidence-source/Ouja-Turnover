# -*- coding: utf-8 -*-
"""
contracting.engine — the PURE rules of «المقاولات». No database, no Discord, no clock of its
own: every function takes `now` / `today` as an argument so the tests can pin time.

Times here are Riyadh wall-clock NAIVE datetimes (the host converts once at the edge).
"""

import datetime as dt
import re

# reminder clock (owner plan 2026-11-23)
HEADS_UP_DAYS = 2
HEADS_UP_HOUR = 9
ASK_HOUR = 16          # «خلص؟» on the due day
LEAD_HOUR = 19         # unanswered → Asil
BOSS_HOUR = 9          # still unanswered next morning → Faisal
SUMMARY_HOUR = 8
BLOCKED_BOSS_HOURS = 24
FRIDAY = 4             # date.weekday(): Monday=0 … Friday=4

# how long after its moment a reminder may still go out (a restart inside the window still
# sends it; a restart after it drops it — a late «خلص؟» at midnight helps nobody)
WINDOW_H = {"heads_up": 10, "ask": 3, "esc_lead": 12, "esc_boss": 12, "blocked_boss": 12}

KIND_AR = {"heads_up": "تنبيه قبل يومين", "ask": "سؤال «خلص؟»", "esc_lead": "تصعيد لأصيل",
           "esc_boss": "تصعيد لفيصل", "blocked_boss": "واقف من يوم — لفيصل", "summary": "ملخص الصباح"}

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
_AMOUNT_RX = re.compile(r"^(.*?)[\s\-–—:|]*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:ر\.?س|ريال|sar)?\s*$",
                        re.IGNORECASE)


# ---------------------------------------------------------------- parsing

def parse_lines(text):
    """Pasted quote table → [{name, amount}]. One line per row: «الاسم   المبلغ».
    The amount is the LAST number on the line; a line without one keeps amount None."""
    out = []
    for raw in str(text or "").splitlines():
        line = raw.translate(_AR_DIGITS).strip()
        if not line:
            continue
        m = _AMOUNT_RX.match(line)
        if m and m.group(1).strip():
            name, amt = m.group(1).strip(" \t-–—:|"), m.group(2)
            try:
                amount = float(amt.replace(",", ""))
            except ValueError:
                name, amount = line, None
        else:
            name, amount = line, None
        if name:
            out.append({"name": name[:160], "amount": amount})
    return out


def parse_date(s, today):
    """'2026-12-01' · '1/12/2026' · '1-12' · '٥/١٢' → ISO date, or None.
    Day/month without a year: this year, unless that is more than 60 days past (then next year)."""
    s = str(s or "").translate(_AR_DIGITS).strip()
    if not s:
        return None
    try:
        if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", s):
            y, m, d = (int(x) for x in s.split("-"))
            return dt.date(y, m, d).isoformat()
        parts = re.split(r"[/\-.]", s)
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            d, m, y = (int(x) for x in parts)
            if y < 100:
                y += 2000
            return dt.date(y, m, d).isoformat()
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            d, m = (int(x) for x in parts)
            cand = dt.date(today.year, m, d)
            # a date a little in the past stays this year (so «فات» can be said);
            # one long past means next year (typing 3/1 in November)
            if (today - cand).days > 60:
                cand = dt.date(today.year + 1, m, d)
            return cand.isoformat()
    except ValueError:
        return None
    return None


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _t(s):
    try:
        return dt.datetime.fromisoformat(str(s)[:19])
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- the gate

def order_problems(items):
    """{item_id: Arabic reason} for every line with no date or a date before the line above."""
    out, prev = {}, None
    for it in sorted(items, key=lambda x: x.get("pos", 0)):
        d = _d(it.get("due"))
        if d is None:
            out[it["id"]] = "حط تاريخ"
            continue
        if prev is not None and d < prev:
            out[it["id"]] = "قبل البند اللي فوقه — رتّب التاريخ"
        prev = d if prev is None or d > prev else prev
    return out


def start_check(project, items):
    why = []
    if not str(project.get("owner") or "").strip():
        why.append("اسم المالك")
    if not str(project.get("unit") or "").strip():
        why.append("الوحدة")
    if not str(project.get("supervisor") or "").strip():
        why.append("مشرف الموقع")
    if not project.get("signed"):
        why.append("توقيع المالك")
    if not project.get("paid"):
        why.append("الدفعة")
    if not items:
        why.append("بنود المشروع")
    elif order_problems(items):
        why.append("ترتيب التواريخ")
    return {"ok": not why, "why": why}


# ---------------------------------------------------------------- the clock

def _skip_friday(d, forward=True):
    while d.weekday() == FRIDAY:
        d += dt.timedelta(days=1 if forward else -1)
    return d


def handover_due(dues):
    ds = [x for x in (_d(s) for s in dues) if x]
    if not ds:
        return ""
    return _skip_friday(max(ds) + dt.timedelta(days=2)).isoformat()


def schedule_for(due):
    """[(kind, at, window_hours)] for one line's due date. Nothing ever lands on a Friday."""
    d = _d(due)
    if d is None:
        return []
    heads = _skip_friday(d - dt.timedelta(days=HEADS_UP_DAYS), forward=False)
    ask_day = _skip_friday(d)
    boss_day = _skip_friday(ask_day + dt.timedelta(days=1))
    at = lambda day, h: dt.datetime(day.year, day.month, day.day, h, 0)  # noqa: E731
    return [("heads_up", at(heads, HEADS_UP_HOUR), WINDOW_H["heads_up"]),
            ("ask", at(ask_day, ASK_HOUR), WINDOW_H["ask"]),
            ("esc_lead", at(ask_day, LEAD_HOUR), WINDOW_H["esc_lead"]),
            ("esc_boss", at(boss_day, BOSS_HOUR), WINDOW_H["esc_boss"])]


def reminder_key(item_id, due, kind):
    """A new due date (a «تأخر») makes new keys, so the moved line gets a fresh schedule."""
    return "%s|%s|%s" % (item_id, str(due)[:10], kind)


_CHAIN = {"esc_lead": "ask", "esc_boss": "esc_lead"}


def due_reminders(items, now, sent_keys, started_at, landed_keys=None):
    """Reminders to send at `now`. Rules:
       - done lines are silent; blocked lines get only the 24-hour «واقف» note to Faisal
       - a reminder planned before the project started is never sent
       - outside its window it is dropped, never sent late
       - an escalation needs the step before it to have LANDED (nobody is accused about a
         question that never reached them). `sent_keys` = everything claimed (dedupe);
         `landed_keys` = what actually arrived (defaults to sent_keys)."""
    landed = sent_keys if landed_keys is None else landed_keys
    start = _t(started_at)
    out = []
    for it in sorted(items, key=lambda x: x.get("pos", 0)):
        st = it.get("status") or "open"
        if st == "done":
            continue
        if st == "blocked":
            b = _t(it.get("blocked_at"))
            if b is None:
                continue
            at = b + dt.timedelta(hours=BLOCKED_BOSS_HOURS)
            k = reminder_key(it["id"], it.get("blocked_at", "")[:19].replace(":", ""), "blocked_boss")
            if at <= now < at + dt.timedelta(hours=WINDOW_H["blocked_boss"]) and k not in sent_keys:
                out.append({"item_id": it["id"], "kind": "blocked_boss", "key": k, "at": at})
            continue
        for kind, at, win in schedule_for(it.get("due")):
            k = reminder_key(it["id"], it.get("due"), kind)
            if k in sent_keys:
                continue
            if start is not None and at < start:
                continue
            if not (at <= now < at + dt.timedelta(hours=win)):
                continue
            need = _CHAIN.get(kind)
            if need and reminder_key(it["id"], it.get("due"), need) not in landed:
                continue
            out.append({"item_id": it["id"], "kind": kind, "key": k, "at": at})
    return out


def summary_key(day):
    return "summary|%s" % day.isoformat()


def summary_due(now, sent_keys, any_active):
    if not any_active or now.weekday() == FRIDAY:
        return False
    if not (SUMMARY_HOUR <= now.hour < SUMMARY_HOUR + 4):
        return False
    return summary_key(now.date()) not in sent_keys


# ---------------------------------------------------------------- reading a project

def health(items, today):
    its = sorted(items, key=lambda x: x.get("pos", 0))
    done = [i for i in its if i.get("status") == "done"]
    open_ = [i for i in its if i.get("status") != "done"]
    late = [i for i in open_ if _d(i.get("due")) and _d(i.get("due")) < today]
    blocked = [i for i in open_ if i.get("status") == "blocked"]
    nxt = open_[0] if open_ else None
    state = "done" if not open_ and its else ("blocked" if blocked else ("late" if late else "ok"))
    return {"done": len(done), "total": len(its), "late": late, "blocked": blocked,
            "next": nxt, "state": state}


def check_new_due(new_due, today):
    """A «تأخر» date must be a real date, today or later, and not a Friday."""
    d = _d(new_due)
    if d is None:
        return "التاريخ مو مفهوم — اكتبه مثل 5/12"
    if d < today:
        return "التاريخ فات — اختر اليوم أو بعده"
    if d.weekday() == FRIDAY:
        return "هذا يوم جمعة — اختر يوم ثاني"
    return ""
