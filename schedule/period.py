# -*- coding: utf-8 -*-
"""
schedule.period — PURE risk + rollup layer for «مخطط الإجازات والتغطية».

Given days that already carry their coverage board and their real workload, this decides which
days are dangerous and summarises the whole period. No DB, no clock, no network — the caller
(schedule.routes) does the impure work and hands the result in, exactly like schedule.engine.

Owner rulings encoded here (2026-08-18):
  * MINUTES are the primary overload signal; unit count is advisory only. Two caps that
    disagree is noise the owner learns to ignore, so the unit flag never fires when the
    minute flag already did.
  * caps are never guessed. They arrive from `observed_caps()` — the 90th percentile of this
    team's own daily history. When history is missing the caps are None and NO overload flag
    is raised at all: an invented red bar is worse than no bar.
  * a Saudi event (Eid, National Day, Riyadh Season…) is a LABEL, never a risk. Riyadh Season
    alone runs five months; letting an event flag would paint half the year red. The real
    signal is the turnover percentile inside the window being planned — `mark_peaks()`.
"""


def percentile(values, p):
    """Nearest-rank percentile — deterministic, no interpolation, no numpy. None when empty."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    import math
    k = max(1, min(len(vals), int(math.ceil((p / 100.0) * len(vals)))))
    return vals[k - 1]


def observed_caps(history, p=90):
    """Daily caps derived from what this team actually does.

    history: [{units, minutes}] — one entry per employee per day already worked.
    Returns {units, minutes, source} with source 'observed', or None/None/'unknown' when there
    is nothing to learn from (the UI then shows «غير محسوب» and raises no overload flags).
    """
    units = percentile([h.get("units") for h in history or []], p)
    minutes = percentile([h.get("minutes") for h in history or []], p)
    if units is None and minutes is None:
        return {"units": None, "minutes": None, "source": "unknown", "p": p, "n": 0}
    return {"units": units, "minutes": minutes, "source": "observed", "p": p,
            "n": len(history or [])}


def mark_peaks(days, p=90):
    """Flag the busiest days OF THIS WINDOW by turnover count (strictly above the p90), so the
    signal is relative to the period being planned rather than to a five-month season."""
    thr = percentile([d.get("total_turnovers", 0) for d in days], p)
    for d in days:
        d["peak"] = bool(thr is not None and d.get("total_turnovers", 0) > thr)
    return thr


def _r(code, severity, ar, en, employee_id=None):
    return {"code": code, "severity": severity, "ar": ar, "en": en, "employee_id": employee_id}


def _hm(mins):
    """420 -> «٧س ٠٠د» in plain digits: 7h00m. Kept ASCII so it renders anywhere."""
    try:
        mins = int(round(mins or 0))
    except (TypeError, ValueError):
        return "0:00"
    return "%d:%02d" % (mins // 60, mins % 60)


def day_risks(day, caps):
    """Every risk raised by ONE day, most severe first. severity: block | warn | info."""
    out = []
    emps = day.get("employees") or []
    off = day.get("off") or []
    date = day.get("date", "")
    cap_min = (caps or {}).get("minutes")
    cap_units = (caps or {}).get("units")

    if not emps:
        out.append(_r("nobody_working", "block",
                      "ما فيه أحد على الدوام يوم %s — لازم تعدّل الإجازة قبل الحفظ" % date,
                      "Nobody is working on %s — the leave must change before saving" % date))

    for e in emps:
        mins = e.get("est_minutes") or 0
        load = e.get("load") or 0
        if cap_min is not None and mins > cap_min:
            out.append(_r("overload", "warn",
                          "%s: %s ساعة شغل تقديري (%d شقة) — فوق المعتاد %s"
                          % (e.get("name"), _hm(mins), load, _hm(cap_min)),
                          "%s: ~%s of work (%d units) — above the usual %s"
                          % (e.get("name"), _hm(mins), load, _hm(cap_min)), e.get("id")))
        elif cap_units is not None and load > cap_units:
            # advisory only — the hours are fine, it is just a lot of doors
            out.append(_r("overload_units", "info",
                          "%s: %d شقة — أكثر من المعتاد %d، بس الساعات ضمن الحد"
                          % (e.get("name"), load, cap_units),
                          "%s: %d units — above the usual %d, but the hours are fine"
                          % (e.get("name"), load, cap_units), e.get("id")))
        if e.get("deep_cleans") and cap_min is not None and mins >= cap_min * 0.9:
            out.append(_r("deep_clean_clash", "warn",
                          "%s: عنده تنظيف عميق ويومه ممتلئ أصلاً (%s)"
                          % (e.get("name"), _hm(mins)),
                          "%s: has a deep clean on an already-full day (%s)"
                          % (e.get("name"), _hm(mins)), e.get("id")))
        districts = [d for d in (e.get("districts") or []) if d]
        if len(set(districts)) >= 3:
            out.append(_r("cross_district", "info",
                          "%s: شققه موزّعة على %d مجمعات — تنقّل كثير"
                          % (e.get("name"), len(set(districts))),
                          "%s: units spread across %d districts — a lot of driving"
                          % (e.get("name"), len(set(districts))), e.get("id")))

    if len(off) >= 2:
        who = "، ".join(o.get("name", "") for o in off)
        out.append(_r("double_absence", "warn",
                      "%d أشخاص برّا في نفس اليوم (%s)" % (len(off), who),
                      "%d people out on the same day (%s)" % (len(off), who)))

    un = day.get("unassigned") or []
    if un:
        out.append(_r("unassigned", "warn",
                      "%d شقة بلا مسؤول ثابت — التوزيع التلقائي بس يغطّيها" % len(un),
                      "%d units with no permanent owner — only the auto-spread covers them"
                      % len(un)))

    stale = day.get("skipped_date_overrides") or []
    if stale:
        out.append(_r("stale_override", "warn",
                      "%d تثبيت ما انطبق (الشخص المختار برّا هذا اليوم)" % len(stale),
                      "%d pin(s) did not apply — the chosen person is off that day" % len(stale)))

    if day.get("peak"):
        out.append(_r("peak_demand", "info",
                      "يوم ضغط: %d مغادرة — من أعلى أيام الفترة" % (day.get("total_turnovers") or 0),
                      "Peak day: %d checkouts — among the busiest in this period"
                      % (day.get("total_turnovers") or 0)))

    order = {"block": 0, "warn": 1, "info": 2}
    out.sort(key=lambda x: order.get(x["severity"], 9))
    return out


def summarize(days, baseline=None, caps=None):
    """Period-level rollup: totals, per-employee deltas vs the normal week, the worst day, and
    every risk raised, counted."""
    def _agg(src):
        acc = {}
        for d in src or []:
            for e in d.get("employees") or []:
                a = acc.setdefault(e["id"], {"id": e["id"], "name": e.get("name"),
                                             "color": e.get("color"), "emoji": e.get("emoji"),
                                             "load": 0, "minutes": 0, "turnovers": 0})
                a["load"] += e.get("load") or 0
                a["minutes"] += e.get("est_minutes") or 0
                a["turnovers"] += e.get("real_turnovers") or 0
        return acc

    plan = _agg(days)
    base = _agg(baseline)
    by_emp = []
    for eid in sorted(set(plan) | set(base)):
        p = plan.get(eid) or {}
        b = base.get(eid) or {}
        ref = p or b
        by_emp.append({
            "id": eid, "name": ref.get("name"), "color": ref.get("color"),
            "emoji": ref.get("emoji"),
            "baseline_load": b.get("load", 0), "plan_load": p.get("load", 0),
            "delta": p.get("load", 0) - b.get("load", 0),
            "baseline_minutes": b.get("minutes", 0), "plan_minutes": p.get("minutes", 0),
            "delta_minutes": p.get("minutes", 0) - b.get("minutes", 0),
            "turnovers": p.get("turnovers", 0),
        })

    counts, first = {}, {}
    for d in days or []:
        for r in d.get("risks") or []:
            counts[r["code"]] = counts.get(r["code"], 0) + 1
            first.setdefault(r["code"], r)
    order = {"block": 0, "warn": 1, "info": 2}
    risks = sorted(
        [{"code": c, "count": n, "severity": first[c]["severity"],
          "ar": first[c]["ar"], "en": first[c]["en"]} for c, n in counts.items()],
        key=lambda x: (order.get(x["severity"], 9), -x["count"]))

    def _weight(d):
        rs = d.get("risks") or []
        return (sum(1 for r in rs if r["severity"] == "block"),
                sum(1 for r in rs if r["severity"] == "warn"),
                sum(e.get("est_minutes") or 0 for e in d.get("employees") or []))
    worst = max(days, key=_weight) if days else None

    return {
        "days": len(days or []),
        "turnovers": sum(d.get("total_turnovers") or 0 for d in days or []),
        "checkins": sum(d.get("checkins") or 0 for d in days or []),
        "by_employee": by_emp,
        "risks": risks,
        "worst_day": (worst or {}).get("date"),
        "blocked": any(r["severity"] == "block" for r in risks),
        "caps": caps or {},
    }
