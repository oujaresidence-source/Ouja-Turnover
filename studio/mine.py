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

TARGET_QUALIFIED = 300      # owner spec: «the last ~300 real guest conversations»
PULL_CAP = 1500             # hard cap on raw conversations pulled (inquiries inflate this)
MIN_STORY_SCORE = 6         # triage score needed to pay for the premium story pass
MAX_PREMIUM = 80            # premium-call budget per scan run

PROGRESS = {"running": False}
_lock = threading.Lock()

TRIAGE_SYSTEM = """أنت محرر قصص لصانع محتوى تيك توك يملك شركة شقق مفروشة في الرياض (عوجا).
تقرأ محادثة حقيقية بين فريق الشركة وضيف، وتحكم: هل فيها «قصة» تستاهل تنحكى في فيديو؟

قصة = موقف فيه توتر أو غرابة أو تحول: طلب غريب، خطأ من الفريق وكيف انحل، ضيف زعلان صار مبسوط،
ضيف طلع زعلان، طوارئ (عطل، تسريب، قفل)، موقف مضحك، موقف إنساني مؤثر، خلاف/اعتراض، إلغاء بلحظة أخيرة،
أو تفصيلة تشغيلية تكشف «أسرار الصنعة».
مو قصة = أسئلة روتينية (الموقع، الكود، الشيك إن/آوت) وردود عادية بدون أي حدث.

أرجع JSON فقط بدون أي شرح:
{"story": true/false, "score": 0-10, "type": "weird_request|mistake_fixed|angry_to_happy|sad_exit|emergency|funny|heartwarming|operational_secret|conflict|cancellation|other", "one_line": "سطر واحد بالعربي يلخص الموقف"}
score = قوة القصة كفيديو (٠ = لا شيء، ١٠ = قصة استثنائية). كن صارم: أغلب المحادثات ٠-٣."""

STORY_SYSTEM = """أنت كاتب قصص لصانع محتوى تيك توك سعودي (شركة شقق مفروشة في الرياض).
تستلم محادثة حقيقية بين الفريق وضيف، وتستخرج منها «بطاقة قصة» جاهزة يبني عليها فيديو.

قواعد صارمة:
- عربي واضح بلمسة نجدية طبيعية.
- ممنوع نهائياً ذكر اسم الضيف أو رقم جواله أو أي معلومة تعرّف عليه — قل «الضيف» أو «ضيفة».
- الاقتباسات: انسخ جمل حرفية قصيرة من المحادثة (هي الذهب) لكن نظّفها من الأسماء.
- لا تخترع أحداث ما صارت. القصة قوتها إنها حقيقية.

أرجع JSON فقط:
{"title": "عنوان القصة بسطر جذاب",
 "summary": "القصة كاملة ٣-٦ جمل: وش صار بالضبط ومن سوى وش",
 "beats": ["تسلسل الأحداث نقطة نقطة (٣-٦ نقاط)"],
 "quotes": ["اقتباسات حرفية قصيرة من المحادثة بدون أسماء (١-٤)"],
 "emotion": "القوس العاطفي: من وش إلى وش",
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


def run_scan(target=TARGET_QUALIFIED, min_score=MIN_STORY_SCORE, max_premium=MAX_PREMIUM):
    """Blocking scan (called inside a daemon thread). Idempotent via studio_scanned."""
    api_get = HOST.require("api_get")
    claude_json = HOST.require("claude_json")
    model_fast = getattr(HOST, "model_fast", None)
    model_premium = getattr(HOST, "model_premium", None)
    listings = {}
    try:
        listings = HOST.listings() or {}
    except Exception:
        pass

    _p(running=True, phase="pull", pulled=0, scanned=0, qualified=0, stories=0,
       premium_used=0, errors=0, done=False, error="", started_at=_now_iso(),
       finished_at="", last_unit="", target=target)
    try:
        convos = _pull_conversations(PULL_CAP)
        seen = db.scanned_ids()
        _p(phase="scan")
        scanned = qualified = stories_n = premium = errors = 0

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

            ok, why = engine.qualifies(c, msgs)
            scanned += 1
            if not ok:
                db.mark_scanned(cid, lid, unit, guest, engine._res_status(c),
                                _stay_dates(c), len(msgs), "skipped_" + why, ts=ts)
                _p(scanned=scanned)
                continue

            qualified += 1
            _p(scanned=scanned, qualified=qualified, last_unit=unit)
            transcript = engine.build_transcript(msgs)
            triage = engine.parse_triage(claude_json(
                TRIAGE_SYSTEM, "المحادثة (شقة: %s):\n\n%s" % (unit, transcript),
                max_tokens=300, model=model_fast))
            if not triage:
                db.mark_scanned(cid, lid, unit, guest, engine._res_status(c),
                                _stay_dates(c), len(msgs), "error", ts=ts)
                errors += 1
                _p(errors=errors)
                continue

            verdict = "no_story"
            if triage["story"] and triage["score"] >= min_score and premium < max_premium:
                story = engine.parse_story(claude_json(
                    STORY_SYSTEM, "المحادثة (شقة: %s):\n\n%s" % (unit, transcript),
                    max_tokens=1200, model=model_premium))
                premium += 1
                _p(premium_used=premium)
                if story:
                    for k in ("title", "summary", "emotion", "lesson"):
                        story[k] = engine.scrub_names(story[k], guest)
                    story["beats"] = [engine.scrub_names(b, guest) for b in story["beats"]]
                    story["quotes"] = [engine.scrub_names(x, guest) for x in story["quotes"]]
                    db.add_story(cid, lid, unit, triage["score"], triage["type"], story, ts)
                    stories_n += 1
                    verdict = "story"
                    _p(stories=stories_n)
            elif triage["story"] and triage["score"] >= min_score:
                verdict = "story_over_budget"   # good story, premium budget spent

            db.mark_scanned(cid, lid, unit, guest, engine._res_status(c),
                            _stay_dates(c), len(msgs), verdict, triage["score"],
                            triage["type"], engine.scrub_names(triage["one_line"], guest), ts)

        _p(running=False, phase="done", done=True, finished_at=_now_iso())
        print("[studio] scan done: scanned=%s qualified=%s stories=%s premium=%s errors=%s"
              % (scanned, qualified, stories_n, premium, errors))
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


def start_scan_thread(**kw):
    """Kick a scan in a daemon thread. Returns False if one is already running."""
    with _lock:
        if PROGRESS.get("running"):
            return False
        PROGRESS["running"] = True
    t = threading.Thread(target=run_scan, kwargs=kw, name="studio-scan", daemon=True)
    t.start()
    return True
