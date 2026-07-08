# -*- coding: utf-8 -*-
"""studio.mine — the conversation miner.

Pulls the most-recent Hostaway conversations, qualifies them (engine.qualifies:
no inquiries, no dead-after-5-messages threads), triages each qualifying thread
with the CHEAP model («فيه قصة؟ كم قوتها؟»), and only sends high scorers to the
PREMIUM model for the full story card. Every looked-at conversation lands in
studio_scanned so a re-run never re-pays for the same thread.

Runs in a plain daemon thread (requests + sqlite only — no event loop needed);
routes.py starts it and polls the module-level PROGRESS dict."""

import threading
import traceback

from . import db, engine
from .host import HOST

TARGET_QUALIFIED = 2000     # owner spec v2: scan the last ~2000 real guest conversations
PULL_CAP = 6000             # hard cap on raw conversations pulled (inquiries inflate this)
MIN_STORY_SCORE = 6         # triage score needed to pay for the premium story pass
MAX_PREMIUM = 250           # premium-call budget per deep scan (only brand-safe high scorers)

DAILY_TARGET = 400          # daily loop: qualify at most this many FRESH convos
DAILY_MAX_PREMIUM = 40      # daily loop premium budget (cheap; only the day's best)

PROGRESS = {"running": False}
_lock = threading.Lock()

TRIAGE_SYSTEM = """أنت محرر محتوى لصانع تيك توك يملك شركة شقق مفروشة راقية في الرياض (عوجا).
تقرأ محادثة حقيقية بين فريق الشركة وضيف، وتحكم: هل فيها «قصة إيجابية» تُثبت إن عوجا تشتغل شغل استثنائي؟

الهدف محتوى إيجابي يخلّي الناس يقولون «هذولا محترفين». القصة القوية وحدة من هذي الأنواع الإيجابية:
- hero_save: صار خطأ/عطل/موقف صعب والفريق حلّه بسرعة واحتراف والضيف انبهر (المشكلة مسموحة فقط بهالشكل).
- transformation: تحوّل/قبل-بعد، شقة أو تجربة صارت أفضل.
- transparency_numbers: أرقام حقيقية (إشغال، تقييم، مدة رد، دخل) تكشف احتراف الشغل.
- day_in_life: كواليس إدارة العملية اليومية.
- hospitality_wow: لمسة ضيافة/اهتمام فوق التوقع.
- weird_delight: طلب غريب لكنه لطيف وانتهى بابتسامة.
- heartwarming: موقف إنساني مؤثر بشكل إيجابي.
- loyal_return: ضيف رجع/كرّر الحجز أو مدح بصدق.
- operational_craft: سر من أسرار الصنعة يبيّن الاحتراف.

مهم جداً — الحكم على السلامة البراندية:
- brand_safe = true فقط إذا القصة تخلّي عوجا تطلع بصورة ممتازة (حتى لو فيها مشكلة، لأنها انحلّت باحتراف).
- brand_safe = false إذا القصة تخلّي عوجا تطلع سيئة، أو شكوى ما انحلّت، أو دراما/لوم/سلبية بدون حل،
  أو تسريب مشكلة داخلية. هذي تُرفض.
- positive = true إذا القوس ينتهي إيجابي (كفاءة/رضا/تحوّل). المحادثة الروتينية أو المفتوحة بسلبية = false.
مو قصة = أسئلة روتينية (الموقع، الكود، الشيك إن/آوت) وردود عادية بدون أي حدث.

أرجع JSON فقط بدون أي شرح:
{"story": true/false, "brand_safe": true/false, "positive": true/false, "score": 0-10, "type": "hero_save|transformation|transparency_numbers|day_in_life|hospitality_wow|weird_delight|heartwarming|loyal_return|operational_craft|other", "one_line": "سطر واحد بالعربي يلخص الموقف الإيجابي"}
score = قوة القصة كفيديو إيجابي (٠ = لا شيء، ١٠ = استثنائية). كن صارم: أغلب المحادثات ٠-٣."""

STORY_SYSTEM = """أنت كاتب قصص لصانع محتوى تيك توك سعودي (شركة شقق مفروشة راقية في الرياض — عوجا).
تستلم محادثة حقيقية بين الفريق وضيف، وتستخرج منها «بطاقة قصة» إيجابية تُثبت احتراف عوجا.

قواعد صارمة:
- عربي واضح بلمسة نجدية طبيعية.
- الزاوية إيجابية دايماً: تنتهي بكفاءة عوجا/رضا الضيف/تحوّل. إذا فيها مشكلة، خلّ البطل هو حلّ الفريق لها.
- ممنوع نهائياً ذكر اسم الضيف أو رقم جواله أو أي معلومة تعرّف عليه — قل «الضيف» أو «ضيفة».
- الاقتباسات: انسخ جمل حرفية قصيرة من المحادثة (هي الذهب) لكن نظّفها من الأسماء.
- لا تخترع أحداث ما صارت. القصة قوتها إنها حقيقية.

أرجع JSON فقط:
{"title": "عنوان القصة بسطر جذاب إيجابي",
 "angle": "الزاوية الإيجابية بسطر: ليش هالقصة تخلّي عوجا تطلع محترفة",
 "summary": "القصة كاملة ٣-٦ جمل: وش صار بالضبط وكيف تصرّف الفريق",
 "beats": ["تسلسل الأحداث نقطة نقطة (٣-٦ نقاط) ينتهي بالحل/الرضا"],
 "quotes": ["اقتباسات حرفية قصيرة من المحادثة بدون أسماء (١-٤)"],
 "emotion": "القوس العاطفي: من وش إلى وش (ينتهي إيجابي)",
 "lesson": "الدرس التشغيلي أو الإنساني بسطر"}"""


def _p(**kw):
    with _lock:
        PROGRESS.update(kw)


def snapshot():
    with _lock:
        d = dict(PROGRESS)
    d["counts"] = db.scan_counts()
    return d


def _now_iso():
    try:
        return HOST.require("now")().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _pull_conversations(cap):
    api_get = HOST.require("api_get")
    convos, offset, page = [], 0, 100
    while len(convos) < cap:
        try:
            data = api_get("/conversations",
                           params={"limit": page, "offset": offset, "includeResources": 1})
        except Exception as e:
            print("[studio] /conversations fetch error at offset %s: %s" % (offset, e))
            break
        batch = (data or {}).get("result", []) or []
        if not batch:
            break
        convos.extend(batch)
        _p(pulled=len(convos))
        if len(batch) < page:
            break
        offset += page
    return convos[:cap]


def _stay_dates(c):
    r = c.get("reservation") if isinstance(c.get("reservation"), dict) else {}
    a, d = r.get("arrivalDate") or "", r.get("departureDate") or ""
    return ("%s → %s" % (a, d)) if a or d else ""


def _guest_name(c):
    r = c.get("reservation") if isinstance(c.get("reservation"), dict) else {}
    return r.get("guestName") or c.get("recipientName") or ""


def _resolve_status(c, cache):
    """Reservation status for a conversation. Live Hostaway conversations usually
    do NOT embed a reservation object (the 2026-07-06 all-skipped bug), so when
    the embedded status is missing we ask /reservations/{id} — the authority.
    Returns '' when the conversation has no reservation at all (true inquiry chat)."""
    st = engine._res_status(c)
    if st:
        return st
    rid = engine.reservation_id(c)
    if not rid:
        return ""
    if rid in cache:
        return cache[rid]
    st = ""
    try:
        data = HOST.require("api_get")("/reservations/%s" % rid)
        st = str(((data or {}).get("result") or {}).get("status") or "").strip()
    except Exception as e:
        print("[studio] reservation %s status fetch error: %s" % (rid, e))
    cache[rid] = st
    return st


def run_scan(target=TARGET_QUALIFIED, min_score=MIN_STORY_SCORE, max_premium=MAX_PREMIUM,
             pull_cap=PULL_CAP):
    """Blocking scan (called inside a daemon thread). Idempotent via studio_scanned.
    Returns the list of story-ids created THIS run (empty on error)."""
    api_get = HOST.require("api_get")
    claude_json = HOST.require("claude_json")
    model_fast = getattr(HOST, "model_fast", None)
    model_premium = getattr(HOST, "model_premium", None)
    listings = {}
    try:
        listings = HOST.listings() or {}
    except Exception:
        pass

    created_ids = []
    _p(running=True, phase="pull", pulled=0, scanned=0, qualified=0, stories=0,
       blocked=0, premium_used=0, errors=0, done=False, error="", started_at=_now_iso(),
       finished_at="", last_unit="", target=target)
    try:
        # One-time heal (2026-07-06): the first live scan mis-labelled everything
        # 'skipped_inquiry' because conversations don't embed a reservation object.
        # Purge that legacy verdict so those conversations get re-evaluated; the
        # fixed code writes 'skip_inquiry' (different name → never purged again).
        healed = db.execute("DELETE FROM studio_scanned WHERE verdict='skipped_inquiry'")
        if healed:
            print("[studio] healed %s legacy skipped_inquiry rows" % healed)

        convos = _pull_conversations(pull_cap)
        seen = db.scanned_ids()
        _p(phase="scan")
        scanned = qualified = stories_n = blocked = premium = errors = 0
        res_cache = {}

        for c in convos:
            if qualified >= target:
                break
            cid = c.get("id")
            if not cid or str(cid) in seen:
                continue
            lid = c.get("listingMapId") or ""
            unit = listings.get(lid) or c.get("listingName") or ("unit-%s" % lid)
            guest = _guest_name(c)
            ts = _now_iso()

            try:
                data = api_get("/conversations/%s/messages" % cid)
                msgs = (data or {}).get("result", []) or []
            except Exception as e:
                print("[studio] convo %s messages error: %s" % (cid, e))
                errors += 1
                _p(errors=errors)
                continue

            scanned += 1
            # cheap thread filter FIRST (no extra API call), then resolve the
            # reservation status (may cost one /reservations/{id} call).
            ok, why = engine.qualifies_msgs(msgs)
            res_status = ""
            if ok:
                res_status = _resolve_status(c, res_cache)
                if not engine.is_stay(res_status):
                    ok, why = False, "inquiry"
            if not ok:
                db.mark_scanned(cid, lid, unit, guest, res_status,
                                _stay_dates(c), len(msgs),
                                ("skip_" + why) if why == "inquiry" else ("skipped_" + why),
                                ts=ts)
                _p(scanned=scanned)
                continue

            qualified += 1
            _p(scanned=scanned, qualified=qualified, last_unit=unit)
            transcript = engine.build_transcript(msgs)
            triage = engine.parse_triage(claude_json(
                TRIAGE_SYSTEM, "المحادثة (شقة: %s):\n\n%s" % (unit, transcript),
                max_tokens=300, model=model_fast))
            if not triage:
                db.mark_scanned(cid, lid, unit, guest, res_status,
                                _stay_dates(c), len(msgs), "error", ts=ts)
                errors += 1
                _p(errors=errors)
                continue

            verdict = "no_story"
            score_ok = triage["score"] >= min_score
            gate_ok = engine.brand_ok(triage)
            if score_ok and not gate_ok:
                # a high-score story that would hurt the brand (or isn't positive):
                # never becomes content. This is the v2 filter the owner asked for.
                verdict = "blocked_brand"
                blocked += 1
                _p(blocked=blocked)
            elif score_ok and gate_ok and premium < max_premium:
                story = engine.parse_story(claude_json(
                    STORY_SYSTEM, "المحادثة (شقة: %s):\n\n%s" % (unit, transcript),
                    max_tokens=1200, model=model_premium))
                premium += 1
                _p(premium_used=premium)
                if story:
                    for k in ("title", "summary", "angle", "emotion", "lesson"):
                        story[k] = engine.scrub_names(story.get(k, ""), guest)
                    story["beats"] = [engine.scrub_names(b, guest) for b in story["beats"]]
                    story["quotes"] = [engine.scrub_names(x, guest) for x in story["quotes"]]
                    sid = db.add_story(cid, lid, unit, triage["score"], triage["type"], story, ts)
                    if sid:
                        created_ids.append(sid)
                    stories_n += 1
                    verdict = "story"
                    _p(stories=stories_n)
            elif score_ok and gate_ok:
                verdict = "story_over_budget"   # good story, premium budget spent

            db.mark_scanned(cid, lid, unit, guest, res_status,
                            _stay_dates(c), len(msgs), verdict, triage["score"],
                            triage["type"], engine.scrub_names(triage["one_line"], guest), ts)

        _p(running=False, phase="done", done=True, finished_at=_now_iso())
        print("[studio] scan done: scanned=%s qualified=%s stories=%s blocked=%s premium=%s errors=%s"
              % (scanned, qualified, stories_n, blocked, premium, errors))
    except Exception as e:
        traceback.print_exc()
        _p(running=False, phase="error", done=True, error="%s: %s" % (type(e).__name__, e),
           finished_at=_now_iso())
    finally:
        try:
            if HOST.save_json:
                HOST.save_json("studio_scan.json", snapshot())
        except Exception:
            pass
    return created_ids


def start_scan_thread(deep=False, **kw):
    """Kick a scan in a daemon thread. Returns False if one is already running.
    deep=True first re-mines under the v2 lens (clears weak legacy cards + cursor)."""
    with _lock:
        if PROGRESS.get("running"):
            return False
        PROGRESS["running"] = True

    def _target():
        if deep:
            try:
                cleared = db.reset_for_deep_scan()
                print("[studio] deep-scan reset:", cleared)
            except Exception as e:
                print("[studio] deep-scan reset failed:", e)
        run_scan(**kw)

    t = threading.Thread(target=_target, name="studio-scan", daemon=True)
    t.start()
    return True


def run_daily_scan():
    """Synchronous daily pass over FRESH conversations (small budget). Returns the db
    rows of stories created today (best first) for the morning digest. Skips if a scan
    is already running so it never collides with a manual/deep scan."""
    with _lock:
        if PROGRESS.get("running"):
            return []
        PROGRESS["running"] = True
    ids = run_scan(target=DAILY_TARGET, min_score=MIN_STORY_SCORE,
                   max_premium=DAILY_MAX_PREMIUM, pull_cap=800)
    rows = []
    for sid in ids:
        r = db.story(sid)
        if r:
            rows.append(r)
    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    return rows
