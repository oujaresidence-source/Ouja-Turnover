# -*- coding: utf-8 -*-
"""studio.pipeline — «سوّ كل شي»: one call, the whole studio, one file at the end.

Every other entry point does one step. This does all of them in the only order that
makes sense — you cannot generate ideas from signals you haven't collected, and you
cannot plan a day from ideas that don't exist yet:

    1. اقرأ بيانات عوجا      internal signals   (cheap, no model calls)
    2. ابحث بالويب           external signals   (live search, costs money, skippable)
    3. امسح المحادثات        fresh guest stories
    4. ولّد من كل شي          factory sweep      (the expensive step)
    5. رتّب اليوم             today's set
    6. اطبع الملف            one Markdown document

Design rules learned the hard way in this repo:
  * every step is individually guarded — step 2 failing must not cost him steps 3-6
  * a step that produced nothing is recorded as `0`, never as a failure
  * the report says what each step actually did, so "خلصت" is never a guess
"""

import threading
import traceback

PROGRESS = {"running": False}
_lock = threading.Lock()

STEPS = (
    ("internal", "🏠 يقرأ بيانات عوجا"),
    ("external", "🌍 يبحث بالويب عن أنظمة وأخبار"),
    ("mine", "💬 يمسح محادثات الضيوف"),
    ("factory", "🏭 يولّد الأفكار من كل شي"),
    ("plan", "📅 يرتّب خطة اليوم"),
    ("export", "📄 يجهّز الملف"),
)


def _p(**kw):
    with _lock:
        PROGRESS.update(kw)


def snapshot():
    with _lock:
        return dict(PROGRESS)


def _now():
    from .host import HOST
    try:
        return HOST.require("now")().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _step(key, fn, report, default=0):
    """Run one stage. A stage never raises upward: a broken web search must not cost
    him the guest stories, the generation, the plan, or the file."""
    _p(step=key, phase=dict(STEPS).get(key, key))
    try:
        return fn()
    except Exception as e:
        print("[studio.pipeline] step %s failed: %s" % (key, e))
        traceback.print_exc()
        report.setdefault("failed", []).append(key)
        return default


def run(budget=None, web_search=True):
    """Blocking full run. Returns a report dict including the finished document."""
    from . import export, external, factory, internal, mine, plan

    report = {"internal": 0, "external": 0, "stories": 0, "cards": 0,
              "sources": 0, "left": 0, "planned": 0, "failed": [],
              "started_at": _now(), "finished_at": "", "doc": "", "filename": ""}
    _p(running=True, step="", phase="", started_at=report["started_at"],
       finished_at="", error="")
    try:
        new_int = _step("internal", lambda: internal.collect() or [], report, [])
        report["internal"] = len(new_int)
        _p(internal=report["internal"])

        if web_search:
            new_ext = _step("external", lambda: external.collect() or [], report, [])
            report["external"] = len(new_ext)
        else:
            report["skipped_external"] = True
        _p(external=report["external"])

        stories = _step("mine", lambda: mine.run_daily_scan() or [], report, [])
        report["stories"] = len(stories)
        _p(stories=report["stories"])

        def _factory():
            pending = factory.pending_sources()
            report["sources"] = len(pending)
            b = budget if budget is not None else factory.DEFAULT_BUDGET
            return factory.run(budget=b, sources=pending)
        fac = _step("factory", _factory, report, {}) or {}
        report["cards"] = fac.get("cards", 0)
        report["left"] = fac.get("left", 0)
        report["empty"] = fac.get("empty", 0)
        _p(cards=report["cards"], left=report["left"])

        planned = _step("plan", lambda: plan.build_day(None, plan.DAILY_N, True) or [],
                        report, [])
        report["planned"] = len(planned)
        _p(planned=report["planned"])

        doc, name = _step("export", export.document, report, ("", "ouja-studio.md"))
        report["doc"], report["filename"] = doc, name

        report["finished_at"] = _now()
        _p(running=False, step="done", phase="خلص", finished_at=report["finished_at"])
        print("[studio.pipeline] done:", {k: v for k, v in report.items()
                                          if k not in ("doc",)})
    except Exception as e:
        traceback.print_exc()
        report["finished_at"] = _now()
        _p(running=False, step="error", error="%s: %s" % (type(e).__name__, e),
           finished_at=report["finished_at"])
    return report


def summary_ar(report):
    """The Discord message. Says what each step DID — including what it didn't reach."""
    nl = chr(10)
    L = ["✅ **خلصت — سويت كل شي**", ""]
    L.append("🏠 %s إشارة من بيانات عوجا" % report.get("internal", 0))
    if report.get("skipped_external"):
        L.append("🌍 البحث الخارجي متخطّى")
    else:
        L.append("🌍 %s خبر/نظام جديد موثّق" % report.get("external", 0))
    L.append("💬 %s قصة جديدة من المحادثات" % report.get("stories", 0))
    L.append("🏭 %s بطاقة فكرة جديدة (من %s مصدر)"
             % (report.get("cards", 0), report.get("sources", 0)))
    L.append("📅 %s أفكار بخطة اليوم" % report.get("planned", 0))
    if report.get("left"):
        L.append("⚠️ باقي **%s** مصدر ما وصلت لهم (الميزانية خلصت) — شغّل الأمر مرة ثانية"
                 % report["left"])
    failed = report.get("failed") or []
    if failed:
        names = dict(STEPS)
        L.append("⚠️ خطوات ما زبطت: %s" % "، ".join(names.get(f, f) for f in failed))
    return nl.join(L)


def start_thread(budget=None, web_search=True, on_done=None):
    with _lock:
        if PROGRESS.get("running"):
            return False
        PROGRESS["running"] = True

    def _target():
        rep = run(budget=budget, web_search=web_search)
        if on_done:
            try:
                on_done(rep)
            except Exception as e:
                print("[studio.pipeline] on_done failed:", e)

    threading.Thread(target=_target, name="studio-pipeline", daemon=True).start()
    return True
