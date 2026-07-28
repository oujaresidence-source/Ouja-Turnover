# -*- coding: utf-8 -*-
"""
ops.notify — THE LADDER: who gets nudged, when, in what words, and what happens at the
deadline. The Arabic is written here; the actual Discord delivery is HOST.notify, and it is
DRY-RUN by default so the first deploy posts absolutely nothing (schedule/decor pattern).

THE LADDER (all Riyadh)
    Sun 18:00  L1  gentle
    Mon 10:00  L2  + one-tap link to the form
    Mon 16:00  L3  countdown
    Mon 20:00  L4  final, and the LEADER gets «عذر مسبق»
    Mon 23:59      the system issues the warning — no human presses anything

ONE OBLIGATION = AT MOST ONE WARNING, EVER. A second miss on the same report is a reminder,
never a second warning. That is enforced in db.issue_warning by a UNIQUE constraint, not here.

DELIVERY CHAIN, every message
    DM  ->  (Forbidden)  the person's own private channel  ->  (failure)  DM the lead
bot.py walks that chain and calls db.record_ladder() with the road that worked. Two failed
DMs for one person surface at /compliance: an employee nobody can reach is an invisible hole
in the whole system, and — see engine.deadline_decision — they are never warned.

DRY-RUN IS A FIRST-CLASS MODE. With OPS_WARN_DRYRUN=1 the tick computes every obligation,
every nudge, every verdict and every multiplier and writes them to ops_dryrun_log for the
owner to read, while sending zero messages and inserting zero warning rows.
"""

import datetime
import json
import os

from . import db, engine
from .host import HOST

WEEKLY_KIND = "wr"

# assignments.json spells one name differently from the Employee Calendar. This is a known
# typo in the ID file, not something a normalizer can honestly fix (ث and ذ are different
# letters), so it is stated out loud instead of hidden inside a fuzzy match. The owner can
# add to this without a deploy via OPS_NAME_ALIASES.
NAME_ALIASES = {"ماذر": "مآثر"}


# ------------------------------------------------------------------ env

def _env(name, default=""):
    return (os.environ.get(name, default) or default).strip()


def _int(name, default):
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


def enabled():
    return _env("OPS_ACCOUNTABILITY_ENABLED", "1") == "1"


def dryrun():
    """DEFAULT ON. Flipped either from the remote control on /compliance (which survives a
    redeploy) or with OPS_WARN_DRYRUN=0 in Railway. The page wins — see ops/switch.py."""
    from . import switch
    return switch.is_dry("warn_dryrun")


def due_hour():
    return _int("OPS_WEEKLY_DUE_HOUR", 23)


def due_minute():
    return _int("OPS_WEEKLY_DUE_MINUTE", 59)


def due_dow_offset():
    """0 = Monday (the spec). Days added to the ISO week's Monday."""
    return max(0, min(6, _int("OPS_WEEKLY_DUE_DOW", 0)))


def free_passes_per_quarter():
    return _int("OPS_FREE_PASS_PER_QUARTER", 1)


def appeal_sla_hours():
    return _int("OPS_APPEAL_SLA_HOURS", 24)


def hr_channel():
    return _env("OPS_HR_CHANNEL", "الالتزام-خاص")


def public_channel():
    return _env("OPS_PUBLIC_CHANNEL", "غرفة-المراقبة")


def approver_ids():
    """The appeal chain: أصيل -> ريم -> فيصل. Set in Railway, so the people can change
    without a deploy. A stage with nobody set auto-escalates instead of swallowing the
    appeal."""
    return {"s1": _env("OPS_APPEAL_S1_ID"), "s2": _env("OPS_APPEAL_S2_ID"),
            "s3": _env("OPS_APPEAL_S3_ID")}


APPROVER_NAMES = {"s1": "أصيل", "s2": "ريم", "s3": "فيصل"}


def lead_id():
    """Who gets the fallback message when a person cannot be reached, and the «عذر مسبق»
    button at L4. Defaults to the first appeal approver."""
    return _env("OPS_LEAD_ID") or approver_ids().get("s1") or ""


def base_url():
    try:
        return (HOST.public_base() if HOST.public_base else "") or ""
    except Exception:
        return ""


# ------------------------------------------------------------------ the roster

def _norm(name):
    """Arabic-tolerant key for matching a name across two files: alef forms unified, ta
    marbuta -> ha, alef maqsura -> ya, diacritics and spacing dropped."""
    s = (name or "").strip()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
                 ("ة", "ه"), ("ى", "ي"), ("ـ", "")):
        s = s.replace(a, b)
    return "".join(ch for ch in s if not ch.isspace() and ch not in "ًٌٍَُِّْ")


def _aliases():
    out = dict(NAME_ALIASES)
    try:
        extra = json.loads(_env("OPS_NAME_ALIASES", "") or "{}")
        if isinstance(extra, dict):
            out.update({str(k): str(v) for k, v in extra.items()})
    except Exception:
        pass
    return out


# Where an id came from, weakest first. Whatever the owner typed always wins: assignments.json
# is import-generated and has already been wrong once (عهود missing, مآثر spelled ماذر), so a
# later re-import must never silently overwrite a correction made by hand.
ID_SOURCES = ("assignments", "env", "typed")


def _id_map():
    """{normalized name -> (discord id, source)}.

    Order: assignments.json  <  OPS_DISCORD_IDS env  <  what the owner typed in /compliance
    (or set with «!ouja اربط»). The people themselves still come only from the Employee
    Calendar — this map answers 'how do we reach them', never 'who works here'."""
    layered = []
    try:
        layered.append(("assignments", HOST.discord_ids() or {}))
    except Exception:
        pass
    try:
        extra = json.loads(_env("OPS_DISCORD_IDS", "") or "{}")
        if isinstance(extra, dict):
            layered.append(("env", extra))
    except Exception:
        pass
    try:
        layered.append(("typed", db.identity_map()))
    except Exception as e:
        print("[ops] identity table unavailable:", e)

    alias = _aliases()
    out = {}
    for source, raw in layered:
        for name, did in (raw or {}).items():
            did = str(did or "").strip()
            key = _norm(alias.get((name or "").strip(), name))
            if not did:
                if source == "typed":
                    out.pop(key, None)      # the owner emptied the box: deliberately no route
                continue
            out[key] = (did, source)
    return out


ID_SOURCE_AR = {"assignments": "من ملف التعيينات", "env": "من إعدادات Railway",
                "typed": "مضاف يدوياً"}


def employees():
    """THE one employee list: the Employee Calendar (schedule_employees). This package does
    not keep a second copy of who works here — it only attaches the Discord id.

    Returns [{name, did, reachable, source, source_ar}]. reachable=False means we have no way
    to message them; they still appear everywhere (so the hole stays visible) but can never
    be warned."""
    names = []
    try:
        from schedule import owners as _sowners
        names = [e["name"] for e in (_sowners.permanent_map() or {}).get("employees", [])]
    except Exception as e:
        print("[ops] employee calendar unavailable:", e)
        return []
    ids = _id_map()
    out = []
    for n in names:
        did, source = ids.get(_norm(n), ("", ""))
        out.append({"name": n, "did": did, "reachable": bool(did),
                    "source": source, "source_ar": ID_SOURCE_AR.get(source, "")})
    return out


def on_leave(name, day):
    """Approved leave from the Employee Calendar — the same absence data the roster uses."""
    try:
        from schedule import db as _sdb, owners as _sowners
        emp = next((e for e in (_sowners.permanent_map() or {}).get("employees", [])
                    if e["name"] == name), None)
        if not emp:
            return False
        return any(a.get("employee_id") == emp["id"]
                   for a in _sdb.absences_on(day.isoformat()))
    except Exception:
        return False


# ------------------------------------------------------------------ the week

def current_period(now):
    """The obligation in play right now.

    The report is due at the START of an ISO week (that week's Monday 23:59), so once
    Monday night passes the next week's obligation becomes the live one — and the first
    nudge for it goes out the following Sunday evening."""
    monday = now.date() - datetime.timedelta(days=now.date().weekday())
    key = engine.iso_week_key(monday)
    if now > due_at(key):
        key = engine.iso_week_key(monday + datetime.timedelta(days=7))
    return key


def due_at(period_key):
    base = engine.due_at_for_week(period_key, hour=due_hour(), minute=due_minute())
    return base + datetime.timedelta(days=due_dow_offset())


def report_window(period_key):
    """The 7 days a report may be dated to count for this obligation: the week of work that
    just finished, ending on the deadline day itself."""
    end = due_at(period_key).date()
    return end - datetime.timedelta(days=7), end


def report_done(employee, period_key, reports=None):
    """Did this person file the weekly report for this week?

    Deliberately generous — either the report's own date or the day it was saved may fall in
    the window, and names are matched Arabic-tolerantly. A false 'not done' costs somebody
    real money, so every tie goes to the employee."""
    if reports is None:
        try:
            reports = HOST.weekly_reports() or []
        except Exception as e:
            print("[ops] weekly reports unavailable:", e)
            return None                      # unknown, NOT 'missed' — see tick()
    start, end = report_window(period_key)
    want = _norm(employee)
    for r in reports:
        if _norm(r.get("employee")) != want:
            continue
        for field in ("date", "created_at", "updated_at"):
            v = (r.get(field) or "")[:10]
            if not v:
                continue
            try:
                d = datetime.date.fromisoformat(v)
            except Exception:
                continue
            if start <= d <= end:
                return True
    return False


# ------------------------------------------------------------------ Arabic wording

_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def ar_num(n):
    return "".join(_AR_DIGITS[int(c)] if c.isdigit() else c for c in str(n))


def _weekly_link():
    b = base_url()
    return (b + "/dashboard#weekly") if b else ""


def _appeal_link(token):
    b = base_url()
    return (b + "/appeal/" + token) if b else ("/appeal/" + token)


def _pct(mult):
    """Arabic-Indic, like every other number in these messages. A DM that says «قبل ١١:٥٩»
    and then «90٪» in the same breath reads like two different systems wrote it."""
    return ar_num(round(float(mult) * 100)) + "٪"


def ladder_text(level, employee, period_key):
    """One message per level, warmer at the top and shorter at the bottom. Never sarcastic,
    never public, and every one of them says how to make it go away."""
    link = _weekly_link()
    nl = "\n"
    if level == "L1":
        t = ["مساك الله بالخير يا " + employee + " 👋",
             "تذكير ودّي: تقرير هذا الأسبوع ينحتاج قبل بكرة الاثنين ١١:٥٩ بالليل.",
             "إذا خلصته، تجاهل الرسالة ✅"]
    elif level == "L2":
        t = ["صباح الخير ☀️",
             "اليوم آخر يوم للتقرير الأسبوعي — الموعد الساعة ١١:٥٩ بالليل.",
             ("تعبيه من هنا: " + link) if link else "تعبيه من صفحة «التقرير الأسبوعي» في اللوحة."]
    elif level == "L3":
        t = ["⏳ باقي ٨ ساعات على موعد التقرير الأسبوعي.",
             "لو تحتاج شي أو فيه عذر، كلّم المسؤول الحين قبل ما يخلص الوقت.",
             ("رابط التقرير: " + link) if link else ""]
    elif level == "L4":
        t = ["🔴 آخر تذكير — باقي ٤ ساعات.",
             "بعد الساعة ١١:٥٩ بينسجل إنذار تلقائي وينقص من العمولة.",
             ("رابط التقرير: " + link) if link else ""]
    else:
        t = ["تذكير: التقرير الأسبوعي."]
    return nl.join(x for x in t if x)


def leader_excuse_prompt(employee, period_key):
    """What the LEADER sees at L4. The only three things a human may do in this system are
    on this card: excuse, waive, or later accept an appeal."""
    nl = "\n"
    return nl.join([
        "🔴 " + employee + " ما سلّم التقرير الأسبوعي وباقي ٤ ساعات (" + period_key + ").",
        "إذا عنده عذر تعرفه، اضغط «عذر مسبق» قبل ١١:٥٩ ويلغى الإنذار قبل ما ينسجل.",
    ])


def warning_dm(employee, period_key, multiplier, token, reason_ar=""):
    """The warning itself. Private, to the person, with the new commission number IN THE
    SAME message — finding out about your money later, from somebody else, is the part that
    actually breaks trust — and with the appeal link at the end, always."""
    nl = "\n"
    lines = ["⚠️ انسجل إنذار — التقرير الأسبوعي (" + period_key + ")",
             reason_ar or "ما تم تسليم التقرير الأسبوعي قبل الموعد.",
             "",
             "عمولتك لهذا الشهر صارت " + _pct(multiplier) + ".",
             "",
             "إذا تشوف إن الإنذار غلط، قدّم اعتراضك من هنا وبيوصل مباشرة للمسؤولين:",
             _appeal_link(token)]
    return nl.join(lines)


def hr_line(employee, period_key, multiplier, reason_ar=""):
    """The private HR record. NEVER a public channel."""
    nl = "\n"
    return nl.join(["⚠️ إنذار تلقائي — " + employee,
                    "الأسبوع: " + period_key,
                    "السبب: " + (reason_ar or "ما تم تسليم التقرير الأسبوعي"),
                    "العمولة بعد الإنذار: " + _pct(multiplier)])


def mercy_dm(verdict, employee, period_key, reason_ar):
    """Every form of forgiveness that the person should hear about. Approved leave is the
    one exception: it is silent on purpose — nobody should be told they were nearly punished
    for a day off the company itself approved."""
    nl = "\n"
    if verdict == "free_pass":
        return nl.join(["استخدمنا لك السماح الفصلي — ما انسجل إنذار ✅",
                        "التقرير الأسبوعي (" + period_key + ") ما وصل، بس هذي أول مرة هالربع.",
                        "خلّها آخر مرة 🙏"])
    if verdict == "excused":
        return nl.join(["✅ انعذرت عن التقرير الأسبوعي (" + period_key + ") — ما انسجل إنذار.",
                        (reason_ar or "")])
    return ""


def retired_dm(employee, through):
    nl = "\n"
    return nl.join(["🎉 ٤ أسابيع نظيفة متتالية — انشال أقدم إنذار عنك.",
                    "عمولتك رجعت تعلى. استمر."])


def appeal_stage_dm(stage, employee, action, reason, outcome=None):
    """The employee hears something at EVERY stage transition, with the reason. An appeal
    dying in silence damages trust more than the warning did."""
    nl = "\n"
    who = APPROVER_NAMES.get(stage, "المسؤول")
    if action == "accepted":
        return nl.join(["✅ اعتراضك انقبل — انلغى الإنذار ورجعت عمولتك.",
                        "القرار من: " + who,
                        "السبب: " + (reason or "")])
    if action == "rejected":
        return nl.join(["اعتراضك انرفض من " + who + ".",
                        "السبب: " + (reason or ""),
                        "الإنذار باقي كما هو."])
    if action == "escalated":
        return nl.join(["اعتراضك انتقل إلى " + who + " للمراجعة.",
                        (("السبب: " + reason) if reason else "")])
    if action == "auto":
        return nl.join(["اعتراضك ما انرد عليه خلال ٢٤ ساعة، فانتقل تلقائياً إلى " + who + ".",
                        "ما راح ينسى — الوقت يمشي لصالحك."])
    return ""


def appeal_notice(stage, employee, warning_id, text):
    nl = "\n"
    return nl.join(["📩 اعتراض على إنذار — " + employee,
                    "المرحلة: " + APPROVER_NAMES.get(stage, stage),
                    "نص الاعتراض: " + (text or "")[:600],
                    "لازم قرار خلال ٢٤ ساعة، وإلا ينتقل تلقائياً للي بعدك.",
                    "الرفض لازم معه سبب مكتوب."])


def public_summary_text(counts, month_key):
    """THE ONLY PUBLIC OUTPUT. Counts, never names. Hard-coded shape with no flag anywhere
    that could ever add a name to it — see engine.public_summary_counts, whose return value
    has no employee field to leak."""
    return ("📊 التزام الفريق · " + month_key + " — "
            "التقارير الأسبوعية: " + ar_num(counts["done"]) + "/" + ar_num(counts["total"]) +
            " · إنذارات: " + ar_num(counts["warnings"]) +
            " · ألغيت بعد الاعتراض: " + ar_num(counts["voided"]) +
            " · متوسط العمولة: " + ar_num(counts["avg_commission_pct"]) + "٪")


def channel_name(employee):
    """One private channel per person: «#اسم-اليوم». It holds ONE pinned message that gets
    EDITED all day — never a stream of new posts. Phase 2 reuses this exact channel."""
    return (employee.replace(" ", "-") + "-اليوم")[:95]


def pinned_text(employee, period_key, status, multiplier, active_warnings, open_items=None):
    """The single pinned message in that channel. Built to be extended: Phase 2 adds its
    turnover lines under «مهام اليوم» without a second message."""
    nl = "\n"
    state = {"pending": "⏳ ما وصل بعد", "done": "✅ تم", "waived": "🟦 إجازة معتمدة",
             "excused": "🟦 معذور", "missed": "⚠️ ما وصل"}.get(status, status)
    lines = ["👤 " + employee, "",
             "📋 التقرير الأسبوعي (" + period_key + "): " + state,
             "💰 العمولة الحالية: " + _pct(multiplier),
             "⚠️ إنذارات فعّالة: " + ar_num(active_warnings)]
    for item in (open_items or []):
        lines.append("• " + str(item))
    lines.append("")
    lines.append("هذي الروم خاصة فيك — ما أحد يشوفها غيرك والمسؤول.")
    return nl.join(lines)


# ------------------------------------------------------------------ delivery

def _send(payload):
    """Hand one message to bot.py. In dry-run nothing leaves the process: the message is
    written to the log the owner reads and the ladder step is marked 'dryrun'."""
    if dryrun():
        db.dry_log(payload.get("kind", "message"), employee=payload.get("employee"),
                   period_key=payload.get("period_key"),
                   detail=(payload.get("text") or "")[:400], payload=payload)
        if payload.get("obligation_id") and payload.get("level"):
            db.record_ladder(payload["obligation_id"], payload.get("employee"),
                             payload["level"], "dryrun", "(dryrun) ما انرسل شي")
        return "dryrun"
    # Claim the step BEFORE handing it over. If Discord is slow, or bot.py never reports
    # back, the level is already spent and the next tick will not send it again — 40 pings
    # is how people learn to mute the bot, and then the whole system dies silently.
    if payload.get("obligation_id") and payload.get("level"):
        db.record_ladder(payload["obligation_id"], payload.get("employee"),
                         payload["level"], "queued", "")
    try:
        if HOST.notify:
            HOST.notify(payload)
            return "queued"
    except Exception as e:
        print("[ops] notify failed:", e)
        if payload.get("obligation_id") and payload.get("level"):
            db.set_ladder_path(payload["obligation_id"], payload["level"], "failed", str(e)[:200])
    return "failed"


# ------------------------------------------------------------------ THE TICK

def tick(now=None):
    """One pass of the ladder. Safe to call every 5 minutes, and safe to call twice.

    Three phases, in this order:
      1. open this week's obligations,
      2. SETTLE every pending obligation whose deadline has passed — including old ones.
         The settle phase is not an edge case: if the container restarts across Monday
         midnight, or the loop is down for a day, the obligation must still reach a verdict
         instead of sitting 'pending' forever and quietly forgiving a real miss (or, worse,
         being settled weeks later against the wrong week's data),
      3. nudge the obligations that are still ahead of their deadline.

    Returns a report dict (also what the tests assert on). Never raises into the caller: a
    Discord or Hostaway problem must not stop the loop that also runs the business."""
    if not enabled():
        return {"skipped": "disabled"}
    now = now or db.now_dt()
    dry = dryrun()
    period = current_period(now)
    deadline = due_at(period)
    roster = employees()
    if not roster:
        return {"skipped": "no employees", "period": period}

    try:
        reports = HOST.weekly_reports() or []
    except Exception as e:
        print("[ops] weekly reports unavailable:", e)
        reports = None

    out = {"period": period, "due_at": deadline.isoformat(timespec="minutes"),
           "dryrun": dry, "now": now.isoformat(timespec="minutes"),
           "nudged": [], "done": [], "verdicts": [], "retired": [], "unreachable": []}

    # ---- 1. this week's obligations exist
    by_name = {}
    for emp in roster:
        if not emp["reachable"]:
            out["unreachable"].append(emp["name"])
        by_name[emp["name"]] = emp
        db.ensure_obligation(WEEKLY_KIND, emp["name"], emp["did"], period, deadline)

    # ---- 2 + 3. walk every pending obligation for a current employee
    pending = [o for o in db.q("SELECT * FROM ops_obligations WHERE status='pending' AND kind=?",
                               (WEEKLY_KIND,)) if o["employee"] in by_name]
    for ob in sorted(pending, key=lambda o: o["period_key"]):
        name = ob["employee"]
        did = by_name[name]["did"]
        pk = ob["period_key"]
        try:
            ob_due = datetime.datetime.fromisoformat(ob["due_at"])
        except Exception:
            ob_due = due_at(pk)

        # filed? checked every tick, so a late-but-before-deadline report still lands
        filed = report_done(name, pk, reports)
        if filed is True:
            db.set_status(ob["id"], "done", done_at=db.now_iso())
            out["done"].append(name)
            if dry:
                db.dry_log("verdict", name, pk, "تم تسليم التقرير — لا إنذار")
            continue

        if now < ob_due:
            if not did:
                # Nobody to send to. Four dead nudges would just mean four pointless DMs to
                # the lead, so it is ONE alert per week instead — and the 'failed' row is
                # what makes the deadline verdict 'unreachable' rather than a warning.
                if "noroute" not in db.sent_levels(ob["id"]):
                    db.record_ladder(ob["id"], name, "noroute", "failed", "ما فيه Discord ID")
                    _send({"kind": "alert", "employee": name, "period_key": pk,
                           "lead_id": lead_id(),
                           "lead_text": ("⚠️ " + name + " ما عنده Discord ID — ما يوصله أي "
                                         "تذكير وما ينسجل عليه إنذار أبداً إلى أن ينضبط.")})
                continue
            # --- before the deadline: at most ONE nudge, the latest level that is due
            step = engine.due_step(ob_due, now, db.sent_levels(ob["id"]))
            if step and step["level"] != "issue":
                _send({"kind": "ladder", "level": step["level"], "employee": name,
                       "employee_did": did, "obligation_id": ob["id"], "period_key": pk,
                       "text": ladder_text(step["level"], name, pk),
                       "lead_id": lead_id() if step["level"] == "L4" else "",
                       "lead_text": (leader_excuse_prompt(name, pk)
                                     if step["level"] == "L4" else ""),
                       "channel": channel_name(name)})
                out["nudged"].append({"employee": name, "level": step["level"]})
            continue

        if filed is None:
            # the reports could not be read at all: never accuse on missing evidence
            db.dry_log("verdict", name, pk, "تعذّر قراءة التقارير — ما انسجل شي")
            continue

        # --- the deadline has passed: the ONE place a miss is decided
        quarter = engine.quarter_key(ob_due.date())
        verdict, reason = engine.deadline_decision(
            done=False,
            on_leave=on_leave(name, ob_due.date()),
            excused=False,                                  # an excuse sets status directly
            free_pass_available=(free_passes_per_quarter() > 0
                                 and not db.free_pass_used(name, quarter)),
            prior_misses=db.prior_misses(name, quarter, before_period=pk),
            reachable=db.is_reachable(ob["id"], did, dry=dry))
        out["verdicts"].append({"employee": name, "verdict": verdict, "reason": reason})
        _apply_verdict(ob, name, did, pk, quarter, verdict, reason, dry)

    # --- earned back: 4 consecutive clean weeks retire the oldest active warning
    for emp in roster:
        r = _retirement(emp["name"])
        if r:
            out["retired"].append(r)
    return out


def _apply_verdict(ob, name, did, period, quarter, verdict, reason, dry):
    """Carry out one deadline verdict. In dry-run this writes to the log and NOTHING else —
    no warning row, no message, no free pass spent."""
    if dry:
        db.dry_log("verdict", name, period,
                   "لو كان النظام شغّال: %s — %s" % (verdict, reason),
                   {"verdict": verdict, "reason": reason})
        if verdict == "missed":
            n = db.active_warning_count(name) + 1
            db.dry_log("warning", name, period,
                       "كان بينسجل إنذار · العمولة تصير %s" % _pct(engine.compute_multiplier(n)),
                       {"would_issue": True, "multiplier": engine.compute_multiplier(n)})
        return

    if verdict == "waived":
        db.set_status(ob["id"], "waived", waived_by="system", waived_reason=reason)
        return                                            # SILENT — zero messages, by design
    if verdict == "free_pass":
        db.set_status(ob["id"], "waived", waived_by="system", waived_reason=reason)
        db.spend_free_pass(name, quarter, ob["id"])
        _send({"kind": "mercy", "employee": name, "employee_did": did, "period_key": period,
               "text": mercy_dm("free_pass", name, period, reason),
               "channel": channel_name(name)})
        return
    if verdict == "unreachable":
        db.set_status(ob["id"], "waived", waived_by="system", waived_reason=reason)
        _send({"kind": "alert", "employee": name, "period_key": period, "lead_id": lead_id(),
               "lead_text": ("⚠️ ما نقدر نوصل " + name + " نهائياً — ما انسجل إنذار. "
                             "لازم نضبط الديسكورد حقه قبل ما يشتغل النظام.")})
        return
    if verdict == "missed":
        db.set_status(ob["id"], "missed")
        w = db.issue_warning(ob, reason)
        led = db.recompute_commission(name, engine.month_key(db.now_dt().date()))
        _send({"kind": "warning", "employee": name, "employee_did": did, "period_key": period,
               "text": warning_dm(name, period, led["multiplier"], w["appeal_token"], reason),
               "hr_channel": hr_channel(),
               "hr_text": hr_line(name, period, led["multiplier"], reason),
               "channel": channel_name(name)})


def _retirement(name):
    """4 consecutive clean weeks -> the oldest active warning is retired. Nothing to retire
    means nothing happens (and no message)."""
    if not db.warnings_for(name, "active"):
        return None
    rows = db.obligations_for_employee(name, WEEKLY_KIND, limit=12)
    weeks = [{"period_key": r["period_key"],
              "clean": r["status"] in ("done", "waived", "excused")}
             for r in sorted(rows, key=lambda r: r["period_key"])
             if r["status"] != "pending"]
    r = engine.retirement_check(name, weeks)
    if not r["retire"] or db.retirement_claimed(name, r["through"]):
        return None
    if dryrun():
        if not db.dry_logged("retire", name, r["through"]):
            db.dry_log("retire", name, r["through"], "كان بينشال أقدم إنذار (٤ أسابيع نظيفة)")
        return None
    w = db.retire_oldest_active(name, r["through"])
    if not w:
        return None
    db.recompute_commission(name, engine.month_key(db.now_dt().date()))
    _send({"kind": "retire", "employee": name, "employee_did": w.get("employee_did"),
           "text": retired_dm(name, r["through"]), "channel": channel_name(name)})
    return {"employee": name, "warning_id": w["id"], "through": r["through"]}


# ------------------------------------------------------------------ appeals clock

def appeal_tick(now=None):
    """AUTO-ESCALATE at 24h. Not optional: an appeal dying in silence damages trust more
    than the warning did."""
    if not enabled():
        return {"skipped": "disabled"}
    now = now or db.now_dt()
    moved = []
    for a in db.open_appeals():
        try:
            due = datetime.datetime.fromisoformat(a["stage_due_at"]) if a.get("stage_due_at") else None
        except Exception:
            due = None
        if not engine.appeal_overdue(due, now):
            continue
        nxt = engine.next_stage(a["stage"])
        db.add_decision(a["id"], a["stage"], "auto_escalated", "system",
                        "ما صار رد خلال ٢٤ ساعة")
        db.move_appeal(a["id"], nxt, appeal_sla_hours())
        w = db.warning(a["warning_id"]) or {}
        if nxt == "closed":
            # nobody decided at any stage. The warning is NOT quietly upheld by silence:
            # it goes to the owner as an open item at /compliance.
            db.dry_log("appeal", w.get("employee"), None,
                       "اعتراض وصل لآخر مرحلة بدون قرار — محتاج قرار فيصل")
        else:
            _send({"kind": "appeal", "employee": w.get("employee"),
                   "employee_did": w.get("employee_did"),
                   "text": appeal_stage_dm(nxt, w.get("employee"), "auto", ""),
                   "approver_id": approver_ids().get(nxt, ""),
                   "approver_text": appeal_notice(nxt, w.get("employee"), a["warning_id"],
                                                  a.get("employee_text"))})
        moved.append({"appeal": a["id"], "to": nxt})
    return {"moved": moved}


# ------------------------------------------------------------------ monthly public post

def monthly_summary(month_key=None, post=False):
    """Counts with NO names. Returns the text; posts only when asked AND not in dry-run."""
    mk = month_key or engine.month_key(db.now_dt().date())
    obs = [o for o in db.q("SELECT * FROM ops_obligations WHERE substr(due_at,1,7)=?", (mk,))]
    total = len(obs)
    done = sum(1 for o in obs if o["status"] in ("done", "waived", "excused"))
    ws = db.q("SELECT * FROM ops_warnings WHERE month_key=?", (mk,))
    voided = sum(1 for w in ws if w["status"] == "voided")
    mults = [c["multiplier"] for c in db.commission_month(mk)]
    counts = engine.public_summary_counts(done, total, len(ws), voided, mults)
    text = public_summary_text(counts, mk)
    if post:
        _send({"kind": "public_summary", "text": text, "public_channel": public_channel()})
    return {"month_key": mk, "counts": counts, "text": text}
