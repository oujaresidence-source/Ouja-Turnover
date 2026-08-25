# -*- coding: utf-8 -*-
"""«نزّل كل البيانات» — the coverage study as a briefing file plus a raw data file.

Two renderers over ONE snapshot:

  render_markdown(study) -> str    a readable briefing, every number labelled with its
                                   source, meant to be handed to a person (or another
                                   Claude session) that has never seen this dashboard.
  render_payload(study)  -> dict   the complete untouched snapshot plus a provenance
                                   map and an explicit list of what is missing.

Why provenance is the whole point: once printed, a number the owner typed by hand and a
number Hostaway measured look identical. A hiring decision built on a hand-typed
placeholder mistaken for measured fact is the exact failure this file exists to prevent.

Pure — hand it a dict, get text back. No network, no files, no clock unless asked.
This module never imports bot.
"""

import datetime

MISSING = "غير متوفرة / unavailable"
DASH = "—"

# The one caveat that must never be lost in a hand-off: the log stores who pressed
# «تم», and the owner confirmed (2026-08-02) those are SUPERVISORS, not the people
# doing the cleaning. Every per-person rate in here is downstream of that.
SUPERVISOR_CAVEAT = (
    "النظام ما يسجّل مين نظّف — يسجّل مين ضغط «تم»، وهم **المشرفون** مو العمّال. "
    "فأي رقم «لكل شخص» في هذا الملف محسوب من مغادرات شققنا ÷ عدد عمّالنا، مو من السجل نفسه. "
    "/ The log records who pressed «تم» (a supervisor), never who cleaned; the "
    "per-cleaner rate is derived from our own apartments' checkouts divided by the "
    "cleaners we employ."
)


# ------------------------------------------------------------------ small helpers

def _g(d, path, default=None):
    """Safe nested get: _g(study, 'capacity.headcount.gap')."""
    node = d
    for part in str(path).split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return default if node is None else node


def _n(v, suffix=""):
    """A number for reading. None becomes an em dash, never a zero."""
    if v is None or v == "":
        return DASH
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (int, float)):
        return "{:,}".format(v) + suffix
    return str(v) + suffix


def _cell(v):
    """A table cell. Pipes would tear a markdown table apart."""
    return str(v if v is not None else DASH).replace("|", "/").replace("\n", " ")


def _yn(v):
    return "نعم / yes" if v else "لا / no"


def _median_min(value, n):
    """A median with nothing behind it is not a zero — it is «we never measured this»."""
    if not value:
        return "غير مقاس / not measured"
    return "وسيط " + _n(value) + " دقيقة (n=" + _n(n) + ")"


# ------------------------------------------------------------------ provenance map

# path -> what it is, in both languages. Every path is checked against a real snapshot
# by tests/test_coverage_brief.py, so this map can never point at data we do not export.
PROVENANCE = {
    "typed_by_hand": [
        {"path": "settings.cleaners_count", "ar": "عدد العمّال الحاليين", "en": "cleaners on payroll now"},
        {"path": "settings.supervisors_count", "ar": "عدد المشرفين", "en": "supervisors"},
        {"path": "settings.cleaner_cost_sar", "ar": "تكلفة العامل بالشهر (ريال)", "en": "cleaner cost SAR/month"},
        {"path": "settings.supervisor_cost_sar", "ar": "تكلفة المشرف بالشهر (ريال)", "en": "supervisor cost SAR/month"},
        {"path": "settings.days_per_week", "ar": "أيام الدوام بالأسبوع", "en": "working days per week"},
        {"path": "settings.days_off_per_year", "ar": "أيام الإجازة بالسنة", "en": "days off per year"},
        {"path": "settings.apartment_price_sar", "ar": "سعر كل شقة بالشهر عند الشركة", "en": "vendor price per apartment per month"},
        {"path": "settings.non_cleaners", "ar": "أسماء ما تُحسب كعمّال تنظيف", "en": "actors excluded from the cleaner rate"},
        {"path": "units.rows", "ar": "ربط كل شقة بشركة تنظيف + روابط المواقع الملصوقة يدوياً", "en": "apartment→crew tags and hand-pasted map links"},
    ],
    "hostaway_api": [
        {"path": "units.total", "ar": "الشقق المفعّلة", "en": "active apartments"},
        {"path": "units.rows", "ar": "اسم الشقة وعدد الغرف والحي والإحداثيات", "en": "name, bedrooms, district, coordinates"},
        {"path": "turns.rows", "ar": "كل مغادرة + الوصول اللي بعدها (T0/T1/T2)", "en": "every checkout joined to the next check-in"},
        {"path": "turns.by_date", "ar": "المغادرات يوم بيوم", "en": "turns per calendar day"},
        {"path": "turns.window", "ar": "الفترة اللي قرأناها من Hostaway", "en": "the reservation window read"},
        {"path": "turns.skipped", "ar": "حجوزات تخطيناها والسبب", "en": "reservations skipped and why"},
        {"path": "capacity.demand_per_day", "ar": "الطلب اليومي", "en": "demand per day"},
        {"path": "capacity.demand_source", "ar": "مصدر رقم الطلب", "en": "where the demand figure came from"},
        {"path": "week.days", "ar": "شكل الأسبوع — أي يوم أثقل", "en": "shape of the week"},
    ],
    "ops_log": [
        {"path": "oujact.started_on", "ar": "أول يوم مسجّل", "en": "first logged day"},
        {"path": "oujact.total_cleans", "ar": "مجموع مرات «تم»", "en": "total logged cleans"},
        {"path": "oujact.per_day_avg", "ar": "متوسط ما يُسجّل باليوم", "en": "logged per day"},
        {"path": "oujact.people", "ar": "كل شخص ضغط «تم» وكم مرة", "en": "per-person press counts"},
        {"path": "oujact.daily", "ar": "يوم بيوم", "en": "day by day"},
        {"path": "oujact.work_days", "ar": "كل يوم عمل لكل شخص وأي شقق", "en": "each person-day and its apartments"},
        {"path": "cycle.median_min", "ar": "الوقت بين تنظيفة والثانية", "en": "gap between consecutive cleans"},
        {"path": "throughput.median", "ar": "كم شقة يسجّلها الشخص باليوم", "en": "apartments logged per person-day"},
        {"path": "photo_time.median_min", "ar": "زمن جلسة التصوير (مو زمن التنظيف)", "en": "photo session time, NOT cleaning time"},
    ],
    "computed": [
        {"path": "cleaner.per_cleaner_best", "ar": "شقق لكل عامل باليوم — أقصى يوم", "en": "apartments per cleaner, their best day"},
        {"path": "cleaner.per_cleaner_typical", "ar": "شقق لكل عامل باليوم — اليوم العادي", "en": "apartments per cleaner, typical day"},
        {"path": "capacity.headcount", "ar": "كم شخص نحتاج (بالدوام/على الكشف/بالذروة/الناقص)", "en": "head count: on shift, on payroll, at peak, gap"},
        {"path": "cost.inhouse_monthly", "ar": "تكلفة التنظيف داخلياً بالشهر", "en": "in-house monthly cost"},
        {"path": "cost.saving_monthly", "ar": "الفرق بين الوضع الحالي والداخلي", "en": "monthly saving or loss"},
        {"path": "vendors.total_monthly", "ar": "فاتورة الشركات بالشهر", "en": "vendor monthly total"},
        {"path": "reconcile.unlogged_per_day", "ar": "تنظيف يصير وما ينسجّل", "en": "cleans happening but never logged"},
        {"path": "clusters.rows", "ar": "الشقق المتلاصقة في نفس المبنى", "en": "apartments stacked in one building"},
        {"path": "teams", "ar": "كل شركة وكم شقة عندها", "en": "crew rollup"},
        {"path": "geo.have_key", "ar": "هل نقدر نحوّل عنوان لإحداثيات", "en": "can we geocode at all"},
    ],
}


def sources(study):
    """Which of the four wells actually produced data this run."""
    return {
        "hostaway_reservations": bool(_g(study, "turns.rows")),
        "hostaway_listings": bool(_g(study, "units.rows")),
        "ops_log": bool(_g(study, "oujact.total_cleans")),
        "typed_settings": bool(_g(study, "settings")),
    }


def gaps(study):
    """Everything we do NOT know, stated out loud.

    A silent gap is the dangerous kind: an apartment with no price entered would make
    in-housing look free, which is the single most expensive mistake available here.
    """
    out = []
    rows = _g(study, "units.rows", []) or []

    no_loc = [u.get("name") for u in rows if not u.get("has_location")]
    if no_loc:
        out.append({"kind": "no_location", "count": len(no_loc), "apartments": no_loc,
                    "ar": "شقق ما نعرف موقعها بالضبط",
                    "en": "apartments with no coordinates"})

    no_team = [u.get("name") for u in rows if not (u.get("team_id") or "")]
    if no_team:
        out.append({"kind": "no_crew", "count": len(no_team), "apartments": no_team,
                    "ar": "شقق ما لها فريق تنظيف مسجّل",
                    "en": "apartments with no cleaning crew tagged"})

    missing_prices = _g(study, "vendors.missing_prices", []) or []
    if missing_prices:
        out.append({"kind": "no_price", "count": len(missing_prices),
                    "apartments": missing_prices,
                    "ar": "شقق عند شركات وما كُتب لها سعر شهري — محسوبة صفر بالغلط لو تجاهلناها",
                    "en": "vendor apartments with no monthly price typed"})

    skipped = _g(study, "turns.skipped", []) or []
    if skipped:
        out.append({"kind": "skipped_reservations", "count": len(skipped),
                    "rows": skipped,
                    "ar": "حجوزات ما دخلت الحساب",
                    "en": "reservations excluded from the turn count"})

    if not sources(study)["hostaway_reservations"]:
        out.append({"kind": "no_hostaway", "count": 0,
                    "ar": "بيانات الحجوزات من Hostaway غير متوفرة في هذه النسخة — "
                          "كل ما يعتمد عليها (المواعيد، شكل الأسبوع، عدد الموظفين، التكلفة) فاضي",
                    "en": "Hostaway reservations were unavailable for this export"})

    if _g(study, "capacity.demand_source") != "hostaway_30d":
        out.append({"kind": "estimated_demand", "count": 0,
                    "ar": "رقم الطلب اليومي تقديري من السجل، مو مقروء من Hostaway",
                    "en": "the daily demand figure is estimated from the log, not measured"})

    if _g(study, "cleaner.likely_underused"):
        out.append({"kind": "underused", "count": 0,
                    "ar": "الفريق يبدو ناقص شغل — معدّل اليوم العادي منخفض، فالمعدّل المستخدم "
                          "هو أقصى يوم وصلوا له",
                    "en": "the team looks under-loaded; the rate used is their best day"})

    if not _g(study, "geo.have_key"):
        out.append({"kind": "no_maps_key", "count": 0,
                    "ar": "ما فيه مفتاح خرائط — العناوين ما تنقلب إحداثيات تلقائياً",
                    "en": "no maps key: addresses cannot be turned into coordinates"})
    return out


# ------------------------------------------------------------------ the JSON file

def render_payload(study, generated_at=None):
    study = study if isinstance(study, dict) else {}
    return {
        "file": "ouja-coverage-data",
        "about_ar": "كل البيانات الخام لصفحة «تغطية التنظيف» — بدون أي اختصار",
        "about_en": "the complete raw snapshot behind the Cleaning Coverage page",
        "generated_at": generated_at or study.get("generated_at") or _now(),
        "caveat": SUPERVISOR_CAVEAT,
        "sources": sources(study),
        "provenance": PROVENANCE,
        "gaps": gaps(study),
        "study": study,
    }


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ the briefing

def _turns_per_unit(study):
    counts = {}
    for r in _g(study, "turns.rows", []) or []:
        lid = r.get("lid")
        c = counts.setdefault(lid, {"total": 0, "T0": 0})
        c["total"] += 1
        if r.get("kind") == "T0":
            c["T0"] += 1
    return counts


def _decision(study, L):
    hc = _g(study, "capacity.headcount")
    cost = _g(study, "cost")
    if not hc:
        L.append("> " + MISSING + " — ما نقدر نعطي جواب توظيف بدون بيانات الحجوزات.")
        L.append("")
        return
    gap = hc.get("gap")
    L.append("- **الناقص من الموظفين / staffing gap:** " + _n(gap) +
             "  (على الكشف نحتاج " + _n(hc.get("payroll")) +
             " · بالدوام اليومي " + _n(hc.get("on_shift_avg")) +
             " · بيوم الذروة " + _n(hc.get("on_shift_peak")) +
             " · عندنا الآن " + _n(hc.get("current_people")) + ")")
    L.append("- **المعدّل المستخدم / rate used:** " + _n(hc.get("rate")) +
             " شقة لكل عامل باليوم — " +
             "أقصى يوم وصلوا له / their best observed day")
    if hc.get("reason"):
        L.append("- **ملاحظة:** " + str(hc.get("reason")))
    if cost:
        L.append("- **بالريال / in money:** داخلياً " + _n(cost.get("inhouse_monthly"), " ر.س") +
                 " بالشهر · الوضع الحالي " + _n(cost.get("current_monthly"), " ر.س") +
                 " · الفرق " + _n(cost.get("saving_monthly"), " ر.س") +
                 " (موجب = نوفّر لو نظّفنا بأنفسنا / positive means in-house is cheaper)")
        if cost.get("reason"):
            L.append("- **ليش ما فيه جواب بالريال:** " + str(cost.get("reason")))
    L.append("")


def render_markdown(study, generated_at=None):
    study = study if isinstance(study, dict) else {}
    when = generated_at or study.get("generated_at") or _now()
    src = sources(study)
    L = []

    L.append("# تغطية التنظيف — كل البيانات / Ouja Cleaning Coverage — full data export")
    L.append("")
    L.append("- **تاريخ التصدير / generated:** " + str(when))
    L.append("- **الشركة:** Ouja Residence (عوجا) — الرياض · Hostaway account 147296")
    L.append("- **السؤال اللي الصفحة موجودة عشانه:** نوظّف عمّال تنظيف إضافيين، ولا ننقل "
             "شقق من الشركات الخارجية لفريقنا، ولا نخلّي الوضع مثل ما هو؟")
    L.append("")
    L.append("> **اقرأ هذا أول / read this first:** " + SUPERVISOR_CAVEAT)
    L.append("")
    L.append("**المصادر في هذه النسخة / sources present in this export**")
    L.append("")
    L.append("| المصدر / source | متوفر؟ |")
    L.append("|---|---|")
    L.append("| Hostaway — الشقق / listings | " + _yn(src["hostaway_listings"]) + " |")
    L.append("| Hostaway — الحجوزات والمغادرات / reservations | " + _yn(src["hostaway_reservations"]) + " |")
    L.append("| سجل العمليات «تم» / ops log | " + _yn(src["ops_log"]) + " |")
    L.append("| أرقام مكتوبة بيد المالك / typed settings | " + _yn(src["typed_settings"]) + " |")
    L.append("")

    # ---------------------------------------------------------------- 1
    L.append("## 1. القرار — الجواب الحالي / the decision as it stands")
    L.append("")
    _decision(study, L)

    # ---------------------------------------------------------------- 2
    L.append("## 2. من وين جت كل رقم / where every number comes from")
    L.append("")
    titles = [("typed_by_hand", "كتبناها بأيدينا / typed by hand"),
              ("hostaway_api", "من Hostaway مباشرة / straight from the Hostaway API"),
              ("ops_log", "من سجل العمليات عندنا / from our own ops log"),
              ("computed", "حسبها النظام من الاثنين / computed by the system")]
    for key, title in titles:
        L.append("**" + title + "**")
        L.append("")
        for f in PROVENANCE[key]:
            L.append("- `" + f["path"] + "` — " + f["ar"] + " / " + f["en"])
        L.append("")

    # ---------------------------------------------------------------- 3
    L.append("## 3. الأرقام اللي كتبناها بأيدينا / the hand-typed inputs")
    L.append("")
    L.append("لا أحد قاسها — المالك كتبها في الصفحة. أي واحد منها غلط يغيّر الجواب كامل.")
    L.append("")
    st = _g(study, "settings", {}) or {}
    L.append("| الرقم / input | القيمة |")
    L.append("|---|---|")
    for key, ar in (("cleaners_count", "عدد العمّال الحاليين / cleaners now"),
                    ("supervisors_count", "عدد المشرفين / supervisors"),
                    ("cleaner_cost_sar", "تكلفة العامل بالشهر / cleaner cost SAR"),
                    ("supervisor_cost_sar", "تكلفة المشرف بالشهر / supervisor cost SAR"),
                    ("days_per_week", "أيام الدوام بالأسبوع / working days per week"),
                    ("days_off_per_year", "إجازات بالسنة / days off per year")):
        L.append("| " + ar + " | " + _n(st.get(key)) + " |")
    L.append("| معامل الكشف / roster factor | " + _n(st.get("roster_factor")) + " |")
    L.append("| معامل الغياب / absence factor | " + _n(st.get("absence_factor")) + " |")
    L.append("")
    nc = st.get("non_cleaners") or []
    L.append("**ما يُحسبون عمّال تنظيف / not counted as cleaners:** " +
             (", ".join(str(x) for x in nc) if nc else DASH) +
             " — تنظيفاتهم تُحسب طلباً، بس ما تخفّض معدّل العامل.")
    L.append("")
    prices = st.get("apartment_price_sar") or {}
    L.append("**سعر كل شقة بالشهر عند الشركة / typed vendor price per apartment** — " +
             _n(len(prices)) + " شقة مسعّرة")
    L.append("")
    names = {}
    for u in _g(study, "units.rows", []) or []:
        names[str(u.get("lid"))] = u.get("name") or str(u.get("lid"))
    if prices:
        for lid, val in sorted(prices.items(), key=lambda kv: -float(kv[1] or 0)):
            L.append("- " + str(names.get(str(lid), lid)) + " · " + _n(val, " ر.س بالشهر") +
                     " · (lid " + str(lid) + ")")
    else:
        L.append("- " + DASH + " ما كُتب أي سعر / no prices typed")
    L.append("")

    # ---------------------------------------------------------------- 4
    L.append("## 4. من Hostaway / measured by Hostaway")
    L.append("")
    if not src["hostaway_reservations"]:
        L.append("**بيانات الحجوزات " + MISSING + "** — " +
                 str(_g(study, "capacity.demand_note") or "") )
        L.append("")
        L.append("كل ما يعتمد عليها فاضي في هذه النسخة: المواعيد الحرجة، شكل الأسبوع، "
                 "معدّل العامل، عدد الموظفين المطلوب، ومقارنة التكلفة.")
        L.append("")
    else:
        w = _g(study, "turns.window", {}) or {}
        counts = _g(study, "turns.counts", {}) or {}
        L.append("- **الفترة المقروءة / window:** " + str(w.get("start") or DASH) + " → " +
                 str(w.get("end") or DASH) + " (" + _n(w.get("weeks")) + " أسابيع)")
        L.append("- **المغادرات باليوم / checkouts per day:** " +
                 _n(_g(study, "turns.checkouts_per_day")))
        L.append("- **الطلب المستخدم في الحساب / demand used:** " +
                 _n(_g(study, "capacity.demand_per_day")) + " · مصدره `" +
                 str(_g(study, "capacity.demand_source") or DASH) + "` · " +
                 str(_g(study, "capacity.demand_note") or ""))
        L.append("- **تصنيف المغادرات / turn classes:** " +
                 "T0 (وصول نفس اليوم — موعد حرج) " + _n(counts.get("T0")) + " · " +
                 "T1 (وصول بكرة) " + _n(counts.get("T1")) + " · " +
                 "T2 (بعدين أو ما فيه حجز) " + _n(counts.get("T2")))
        L.append("")
        L.append("**شكل الأسبوع / shape of the week**")
        L.append("")
        L.append("| اليوم | متوسط المغادرات | منها نفس اليوم (T0) | أيام مرصودة |")
        L.append("|---|---|---|---|")
        for d in _g(study, "week.days", []) or []:
            L.append("| " + _cell(d.get("ar")) + " (" + _cell(d.get("en")) + ") | " +
                     _n(d.get("total")) + " | " + _n(d.get("T0")) + " | " +
                     _n(d.get("observed_days")) + " |")
        busiest = _g(study, "week.busiest", {}) or {}
        L.append("")
        L.append("- **أثقل يوم / busiest day:** " + _cell(busiest.get("ar")) + " — " +
                 _n(busiest.get("total")) + " مغادرة · نسبته للمتوسط " +
                 _n(_g(study, "week.peak_ratio")) + "×")
        L.append("- **المتوسط / mean per day:** " + _n(_g(study, "week.mean_per_day")) +
                 " · **p70:** " + _n(_g(study, "week.p70_per_day")))
        L.append("")
        L.append("**المغادرات يوم بيوم / turns per day**")
        L.append("")
        L.append("| اليوم | T0 | T1 | T2 | الكل |")
        L.append("|---|---|---|---|---|")
        by_date = _g(study, "turns.by_date", {}) or {}
        for date_iso in sorted(by_date.keys()):
            r = by_date[date_iso]
            L.append("| " + _cell(date_iso) + " | " + _n(r.get("T0")) + " | " +
                     _n(r.get("T1")) + " | " + _n(r.get("T2")) + " | " +
                     _n(r.get("total")) + " |")
        L.append("")
        skipped = _g(study, "turns.skipped", []) or []
        L.append("**حجوزات ما دخلت الحساب / skipped reservations:** " + _n(len(skipped)))
        for s in skipped[:60]:
            L.append("- listing " + str(s.get("lid")) + " — " + str(s.get("reason")))
        L.append("")

    # ---------------------------------------------------------------- 5
    L.append("## 5. من سجل العمليات / from our own ops log")
    L.append("")
    oj = _g(study, "oujact", {}) or {}
    L.append("- **أول يوم مسجّل / first logged day:** " + str(oj.get("started_on") or DASH) +
             " · **من تاريخ / counted since:** " + str(oj.get("since") or DASH))
    L.append("- **أيام فيها شغل / days worked:** " + _n(oj.get("days_worked")) +
             " · **مجموع «تم» / total logged cleans:** " + _n(oj.get("total_cleans")) +
             " · **باليوم / per day:** " + _n(oj.get("per_day_avg")))
    L.append("- **أشخاص ظهروا في السجل / people seen in the log:** " +
             _n(oj.get("active_people")))
    L.append("- **الوقت بين تنظيفة والثانية / gap between consecutive cleans:** " +
             _median_min(_g(study, "cycle.median_min"), _g(study, "cycle.n")))
    L.append("- **شقق لكل شخص باليوم في السجل / apartments per person-day:** وسيط " +
             _n(_g(study, "throughput.median")) + " (n=" + _n(_g(study, "throughput.n")) + ")")
    L.append("- **زمن جلسة التصوير / photo session:** " +
             _median_min(_g(study, "photo_time.median_min"), _g(study, "photo_time.n")) +
             " — **هذا زمن التصوير، مو زمن التنظيف / this is the photo session, NOT the "
             "cleaning time**")
    L.append("")
    people = oj.get("people") or []
    if people:
        L.append("**كل شخص ضغط «تم» / everyone who pressed «تم»**")
        L.append("")
        L.append("| الشخص | أيام | تنظيفات | باليوم | محسوب كعامل؟ |")
        L.append("|---|---|---|---|---|")
        for p in people:
            L.append("| " + _cell(p.get("person")) + " | " + _n(p.get("days")) + " | " +
                     _n(p.get("cleans")) + " | " + _n(p.get("per_day")) + " | " +
                     _yn(p.get("counted")) + " |")
        L.append("")
    daily = oj.get("daily") or []
    if daily:
        L.append("**يوم بيوم / day by day** (" + _n(len(daily)) + " يوم)")
        L.append("")
        L.append("| اليوم | تنظيفات مسجّلة | أشخاص |")
        L.append("|---|---|---|")
        for d in daily:
            L.append("| " + _cell(d.get("date")) + " | " + _n(d.get("count")) + " | " +
                     _n(d.get("people")) + " |")
        L.append("")

    # ---------------------------------------------------------------- 6
    L.append("## 6. الحسابات — وبأي مدخلات / the computed models and their inputs")
    L.append("")
    cl = _g(study, "cleaner")
    L.append("**معدّل العامل / apartments per cleaner per day**")
    L.append("")
    if cl:
        L.append("- شققنا / our own apartments: " + _n(cl.get("own_units")) +
                 " · عمّالنا / cleaners: " + _n(cl.get("cleaners")) +
                 " · الفترة / window: " + _n(cl.get("window_days")) + " يوم")
        L.append("- مغادرات شققنا / checkouts on our own units: " +
                 _n(cl.get("own_checkouts")) + " · باليوم " + _n(cl.get("own_per_day")) +
                 " · أقصى يوم " + _n(cl.get("busiest_day")))
        L.append("- **اليوم العادي / typical:** " + _n(cl.get("per_cleaner_typical")) +
                 " لكل عامل · **أقصى يوم / best:** " + _n(cl.get("per_cleaner_best")) +
                 " لكل عامل ← **هذا المستخدم في القرار**")
        L.append("- الفريق ناقص شغل؟ / under-loaded: " + _yn(cl.get("likely_underused")))
        if cl.get("reason"):
            L.append("- ملاحظة: " + str(cl.get("reason")))
    else:
        L.append("- " + MISSING)
    L.append("")

    hc = _g(study, "capacity.headcount")
    L.append("**عدد الموظفين المطلوب / head count**")
    L.append("")
    if hc:
        L.append("| المخرج | القيمة | كيف انحسب |")
        L.append("|---|---|---|")
        L.append("| بالدوام اليومي / on shift | " + _n(hc.get("on_shift_avg")) +
                 " | الطلب " + _n(hc.get("demand_per_day")) + " ÷ المعدّل " +
                 _n(hc.get("rate")) + " |")
        L.append("| على الكشف / on payroll | " + _n(hc.get("payroll")) +
                 " | × معامل الكشف " + _n(hc.get("roster_factor")) + " × (1 + غياب " +
                 _n(hc.get("absence_factor")) + ") |")
        L.append("| بيوم الذروة / at peak | " + _n(hc.get("on_shift_peak")) +
                 " | ذروة " + _n(hc.get("peak_per_day")) + " ÷ المعدّل |")
        L.append("| الناقص / gap | " + _n(hc.get("gap")) + " | على الكشف − الموجود " +
                 _n(hc.get("current_people")) + " |")
    else:
        L.append("- " + MISSING)
    L.append("")

    cost = _g(study, "cost")
    L.append("**التكلفة / cost comparison**")
    L.append("")
    if cost:
        L.append("- عمّال مطلوبين لو نظّفنا كل شيء بأنفسنا / cleaners needed in-house: " +
                 _n(cost.get("cleaners_needed")))
        L.append("- تكلفة داخلية بالشهر / in-house monthly: " +
                 _n(cost.get("inhouse_monthly"), " ر.س") + " · للتنظيفة الواحدة " +
                 _n(cost.get("inhouse_per_clean"), " ر.س"))
        L.append("- فاتورة الشركات بالشهر / vendors monthly: " +
                 _n(cost.get("vendor_monthly"), " ر.س") + " · للتنظيفة الواحدة " +
                 _n(cost.get("vendor_per_clean"), " ر.س"))
        L.append("- الوضع الحالي بالشهر / current monthly: " +
                 _n(cost.get("current_monthly"), " ر.س"))
        L.append("- **الفرق / difference:** " + _n(cost.get("saving_monthly"), " ر.س"))
        if cost.get("reason"):
            L.append("- ملاحظة: " + str(cost.get("reason")))
    else:
        L.append("- " + MISSING)
    L.append("")

    vn = _g(study, "vendors")
    L.append("**الشركات الخارجية / the outside companies**")
    L.append("")
    if vn:
        L.append("- شقق عند شركات / vendor apartments: " + _n(vn.get("apartments")) +
                 " · مسعّرة " + _n(vn.get("priced_count")) +
                 " · **بدون سعر مكتوب " + _n(vn.get("missing_count")) + "**")
        L.append("- المجموع الشهري / monthly total: " + _n(vn.get("total_monthly"), " ر.س") +
                 " — يشمل فقط الشقق المسعّرة")
        for t in vn.get("by_team") or []:
            L.append("  - " + _cell(t.get("name")) + ": " + _n(t.get("monthly"), " ر.س"))
        L.append("")
        L.append("**كل شقة عند شركة / per vendor apartment**")
        L.append("")
        for r in vn.get("rows") or []:
            L.append("- " + str(r.get("name")) + " · " + _cell(r.get("team_name")) +
                     " · " + _n(r.get("bedrooms")) + " غرف · " +
                     (_n(r.get("monthly"), " ر.س بالشهر") if r.get("monthly") is not None
                      else "**بدون سعر مكتوب / no price typed**") +
                     " · تنظيفات بالشهر " + _n(r.get("cleans_per_month")) +
                     " · للتنظيفة " + _n(r.get("per_clean"), " ر.س"))
        miss = vn.get("missing_prices") or []
        if miss:
            L.append("")
            L.append("**بدون سعر / no price typed:** " + ", ".join(str(m) for m in miss))
    else:
        L.append("- " + MISSING)
    L.append("")

    rc = _g(study, "reconcile")
    L.append("**فحص المطابقة / reconciliation**")
    L.append("")
    if rc:
        L.append("- مسجّل باليوم / logged per day: " + _n(rc.get("logged_per_day")) +
                 " · مغادرات فعلية باليوم / real checkouts: " +
                 _n(rc.get("checkouts_per_day")))
        L.append("- **تنظيف يصير وما ينسجّل / unlogged per day: " +
                 _n(rc.get("unlogged_per_day")) + "**" +
                 (" — فيه فجوة" if rc.get("has_gap") else ""))
        L.append("- تنظيفات على شقق بدون فريق / cleans on untagged apartments: " +
                 _n(rc.get("untagged_cleans")))
        L.append("")
        L.append("| الفريق | شقق مربوطة | تنظيفات مسجّلة | الرقم منطقي؟ |")
        L.append("|---|---|---|---|")
        for c in rc.get("crews") or []:
            L.append("| " + _cell(c.get("name")) + " | " + _n(c.get("units")) + " | " +
                     _n(c.get("cleans")) + " | " +
                     ("**لا — مستحيل** / implausible" if c.get("implausible") else "نعم") +
                     " |")
    else:
        L.append("- " + MISSING)
    L.append("")

    cs = _g(study, "clusters", {}) or {}
    L.append("**التجمّعات / stacked apartments:** " + _n(cs.get("total")) + " تجمّع · " +
             _n(cs.get("multi")) + " فيها أكثر من شقة · " + _n(cs.get("stacked_units")) +
             " شقة متلاصقة · أكبر تجمّع " + _n(cs.get("biggest")) + " شقق")
    L.append("")

    # ---------------------------------------------------------------- 7
    L.append("## 7. الشقق — وحدة وحدة / every apartment")
    L.append("")
    un = _g(study, "units", {}) or {}
    L.append("**" + _n(un.get("total")) + " شقة مفعّلة** · فريقنا " + _n(un.get("in_house")) +
             " · شركات " + _n(un.get("third_party")) + " · بدون فريق " +
             _n(un.get("unassigned")) + " · موقعها معروف " + _n(un.get("located")) +
             " · بدون موقع " + _n(un.get("missing_location")))
    L.append("")
    L.append("الاسم يحتوي على الرمز `|` فما نقدر نحطه في جدول — كل شقة سطر.")
    L.append("")
    turns_u = _turns_per_unit(study)
    prices = (_g(study, "settings.apartment_price_sar", {}) or {})
    for u in _g(study, "units.rows", []) or []:
        lid = u.get("lid")
        t = turns_u.get(lid) or {}
        price = prices.get(str(lid), prices.get(lid))
        who = (u.get("team_name") or "").strip()
        if u.get("in_house"):
            who = "فريقنا / in-house (" + (who or "OujaCT") + ")"
            price_txt = "لا ينطبق — شقتنا / n/a, ours"
        elif u.get("team_id"):
            who = "شركة / vendor: " + who
            price_txt = "**ما كُتب لها سعر / no price typed**"
        else:
            who = "**بدون فريق / no crew**"
            price_txt = "لا ينطبق — ما لها شركة / n/a, no vendor"
        if price not in (None, ""):
            price_txt = _n(price, " ر.س")
        L.append("- **" + str(u.get("name")) + "** · lid " + str(lid) +
                 " · " + _n(u.get("bedrooms")) + " غرف" +
                 " · " + (str(u.get("district")) or DASH) +
                 " · " + who +
                 " · الموقع: " + ("معروف (" + str(u.get("coord_source") or "?") + ")"
                                  if u.get("has_location") else "**غير معروف**") +
                 " · السعر الشهري: " + price_txt +
                 " · مغادرات بالفترة: " + _n(t.get("total") or 0) +
                 " (منها نفس اليوم " + _n(t.get("T0") or 0) + ")")
    L.append("")

    tm = _g(study, "teams", []) or []
    if tm:
        L.append("**الفرق / crews**")
        L.append("")
        L.append("| الفريق | شقق | موقعها معروف | فريقنا؟ |")
        L.append("|---|---|---|---|")
        for t in tm:
            L.append("| " + _cell(t.get("name") or "بدون فريق") + " | " +
                     _n(t.get("apartments")) + " | " + _n(t.get("located")) + " | " +
                     _yn(t.get("in_house")) + " |")
        L.append("")

    # ---------------------------------------------------------------- 8
    L.append("## 8. الناقص وما لا نعرفه / gaps and unknowns")
    L.append("")
    gl = gaps(study)
    if not gl:
        L.append("- ما فيه نواقص مرصودة / nothing missing was detected")
    for g in gl:
        line = "- **" + g["ar"] + " / " + g["en"] + "**"
        if g.get("count"):
            line += " — " + _n(g["count"])
        L.append(line)
        for nm in (g.get("apartments") or [])[:80]:
            L.append("  - " + str(nm))
        for r in (g.get("rows") or [])[:60]:
            L.append("  - listing " + str(r.get("lid")) + " — " + str(r.get("reason")))
    L.append("")

    # ---------------------------------------------------------------- 9
    L.append("## 9. على ماذا يجاوب هذا الملف / what this file can and cannot answer")
    L.append("")
    L.append("**يقدر يجاوب / can answer**")
    L.append("")
    L.append("- كم شقة عندنا، وين، ومين ينظفها الآن")
    L.append("- كم مغادرة تصير كل يوم، وأي يوم أثقل، وكم منها موعدها حرج (وصول نفس اليوم)")
    L.append("- كم يكلّفنا التنظيف الآن مقابل لو سوّيناه بأنفسنا — للشقق المسعّرة فقط")
    L.append("- كم شخص ناقصنا لو غطّينا كل شيء داخلياً")
    L.append("")
    L.append("**ما يقدر يجاوب / cannot answer**")
    L.append("")
    L.append("- كم دقيقة تاخذ التنظيفة الواحدة فعلياً — ما فيه بداية ونهاية مسجّلة، "
             "الموجود فقط الوقت بين ضغطة «تم» والثانية")
    L.append("- مين العامل اللي نظّف شقة معيّنة — السجل يعرف المشرف اللي ضغط فقط")
    L.append("- جودة التنظيف أو رضا الضيف — مو في هذا الملف")
    L.append("- أسعار الشركات للشقق اللي ما كُتب لها سعر")
    L.append("")
    L.append("---")
    L.append("")
    L.append("ملف البيانات الخام كامل موجود بجانب هذا الملف باسم "
             "`ouja-coverage-data-<التاريخ>.json` — نفس اللقطة بدون أي اختصار.")
    return "\n".join(L)


# ------------------------------------------------------------------ file names

def filename(kind, day=None):
    """`ouja-coverage-brief-2026-08-05.md` — a date that is not a date cannot get in."""
    safe = "".join(ch for ch in str(day or "") if ch.isdigit() or ch == "-")[:10]
    if len(safe) != 10:
        safe = datetime.date.today().isoformat()
    if kind == "json":
        return "ouja-coverage-data-" + safe + ".json"
    return "ouja-coverage-brief-" + safe + ".md"
