# -*- coding: utf-8 -*-
"""studio.external — the LIVE-WEB signal collector (spec D7–D10).

Four search streams (regulation / market / global_trend / trend) each ask Claude
with Anthropic's server-side web-search tool for TIMELY, QUOTABLE facts that a
Riyadh short-term-rental owner could turn into a video today.

The anti-fabrication contract lives in engine.parse_signals: an external signal
with no real http(s) url or no YYYY-MM-DD date is dropped before it is ever
stored. This module never patches a missing url in from the citation list — a
fact the model couldn't attribute is a fact we don't make content from.

Runs in a plain daemon thread (requests + sqlite only), exactly like studio.mine:
routes.py starts it and polls the module-level PROGRESS dict."""

import threading
import traceback

from . import db, engine
from .host import HOST

PER_STREAM = 4           # how many signals we keep from one stream per run
MAX_TOKENS = 3000
SEARCH_MAX_USES = 6      # server-side searches allowed per stream
PRUNE_KEEP = 400

PROGRESS = {"running": False}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# prompts. Arabic, because the ideas that grow out of these signals are Najdi
# Arabic. The rules below are identical in every stream — only the beat changes.
# ---------------------------------------------------------------------------

_RULES = """أنت باحث أخبار لصانع محتوى تيك توك سعودي يملك شركة شقق مفروشة راقية في الرياض (عوجا، ٥٣ شقة).
مهمتك: تبحث في الويب الآن، وترجع حقائق حقيقية طازجة تنفع تنقال قدّام الكاميرا اليوم.

قواعد ما تنكسر أبداً:
- ممنوع منعاً باتاً تخترع أو تخمّن أي رقم أو تاريخ أو خبر. كل حقيقة لازم تكون شفتها فعلياً في نتيجة بحث.
- كل حقيقة تجي معها: رابط المصدر الحقيقي (http/https) + تاريخ نشر المصدر بصيغة YYYY-MM-DD.
- إذا ما لقيت رابط أو ما تأكدت من التاريخ — احذف الحقيقة. رجوع قائمة فاضية جواب صحيح ومقبول.
- ما تعيد صياغة ذاكرتك ولا معلومات عامة: لو ما جات من بحث حي، لا ترجعها.
- الأولوية للأحدث: آخر ٦٠ يوم أفضل بكثير من خبر عمره سنة.
- «fact» = جملة واحدة محددة تقدر تنقال حرفياً في الفيديو، وفيها الرقم أو التاريخ داخلها.
- «detail» = ليش صاحب شقة مفروشة في الرياض يهمّه هالخبر (أثر مباشر على شغله).

أرجع JSON فقط بدون أي شرح ولا تعليق:
{"signals": [{"source": "%s", "title": "عنوان قصير بالعربي", "fact": "الحقيقة بجملة وحدة فيها الرقم/التاريخ", "detail": "ليش تهم صاحب الشقة في الرياض", "url": "https://…", "as_of": "YYYY-MM-DD", "strength": 0-100}]}
strength = قوة الحقيقة كمحتوى (١٠٠ = خبر يقلب السوق ويستاهل فيديو اليوم، ٢٠ = معلومة باردة)."""

# Owner-supplied memory. UNVERIFIED on purpose — the model must confirm or correct
# each one against a real source, or drop it. Never asserted to the model as fact.
_SEED_REGULATION = """معلومات من الذاكرة غير مؤكدة — تحقق منها ببحث حي وصحّحها أو احذفها، ولا تعتمدها كما هي:
- يقال إن فيه مسودة نظام سعودي (يونيو ٢٠٢٦) تمنع استضافة نفس الضيف أكثر من ٢٩ يوم متواصل في الوحدة السياحية.
- يقال إن رخصة الضيافة السياحية تكلف تقريباً ١١٠٠ ريال سنوياً.
تأكد من الوضع الحالي: هل صدر النظام؟ متى؟ وش رقم المادة؟ وش الغرامات؟"""

_SEED_MARKET = """معلومات من الذاكرة غير مؤكدة — تحقق منها ببحث حي وصحّحها أو احذفها:
- يقال إن عدد السياح في السعودية بالربع الأول ٢٠٢٦ وصل تقريباً ٣٧٫٢ مليون.
ابحث عن أحدث أرقام رسمية (وزارة السياحة، الهيئة العامة للإحصاء، رؤية ٢٠٣٠) وخصوصاً الرياض."""

_SEED_GLOBAL = """معلومات من الذاكرة غير مؤكدة — تحقق منها ببحث حي وصحّحها أو احذفها:
- يقال إن حجم سوق الإيجار قصير المدى عالمياً بين ١٣٨ و١٥٤ مليار دولار وينمو تقريباً ١٠٪ سنوياً.
- يقال إن رسوم Airbnb بنظام الرسوم الموحّدة تقارب ١٥٫٥٪ على المضيف مقابل ٣٪ في النظام المقسّم."""

_SEED_TREND = """لا تعتمد على ذاكرتك في أي خبر — كل شيء ترجعه لازم يكون من بحث حي بتاريخ نشر واضح."""


def _stream(key, label, focus, seed):
    return {"key": key, "label": label,
            "system": _RULES % key,
            "focus": focus, "seed": seed}


STREAMS = (
    # D7 — the highest-value stream: owner-facing "newsjacking". A rule change is
    # the one thing every Riyadh apartment owner stops scrolling for.
    _stream(
        "regulation", "أنظمة وتراخيص",
        """ابحث عن آخر تغييرات الأنظمة والتراخيص التي تخص الوحدات السكنية المفروشة
        والضيافة السياحية في السعودية: قرارات وزارة السياحة، شروط ورسوم الترخيص، اشتراطات البلدية،
        نظام الإيجار السكني/إيجار، ضريبة القيمة المضافة والفوترة الإلكترونية (زاتكا)،
        الغرامات والمخالفات، وأي مسودة نظام تحت التطبيق.""",
        _SEED_REGULATION),
    # D8 — Saudi market numbers. Ammunition for «أرقام» / data_reveal videos.
    _stream(
        "market", "سوق السياحة السعودي",
        """ابحث عن أحدث أرقام السياحة والضيافة في السعودية: عدد السياح، الإنفاق السياحي،
        نسب الإشغال الفندقي، متوسط السعر الليلي، نمو الرياض تحديداً، مستهدفات ومنجزات
        رؤية ٢٠٣٠، موسم الرياض والفعاليات الكبيرة وأثرها على الطلب على السكن.""",
        _SEED_MARKET),
    # D9 — global STR moves. Gives the owner an "outsider" angle nobody else posts.
    _stream(
        "global_trend", "اتجاهات عالمية للإيجار قصير المدى",
        """ابحث عن أحدث تحركات سوق الإيجار قصير المدى عالمياً: حجم السوق ونموه، قرارات
        وسياسات Airbnb وBooking، نماذج الرسوم على المضيفين، العرض والطلب، تغيّر نافذة
        الحجز ومدة الإقامة، تنظيمات المدن الكبرى، وسلوك المسافرين الجديد.""",
        _SEED_GLOBAL),
    # D10 — today's news. Short shelf life on purpose: react within a day or skip.
    _stream(
        "trend", "خبر اليوم",
        """ابحث عن أخبار عاجلة خلال آخر ٧ أيام تخص السياحة أو العقار أو السكن أو الفعاليات
        في السعودية والرياض، وأي موضوع متداول الآن يستاهل فيديو ردة فعل خلال ٢٤ ساعة.
        ركّز على الطازج جداً: الخبر اللي عمره أسبوع ميت.""",
        _SEED_TREND),
)

STREAM_KEYS = tuple(s["key"] for s in STREAMS)
_BY_KEY = {s["key"]: s for s in STREAMS}


def _p(**kw):
    with _lock:
        PROGRESS.update(kw)


def snapshot():
    with _lock:
        return dict(PROGRESS)


def _now():
    try:
        return HOST.require("now")()
    except Exception:
        return None


def _now_iso():
    n = _now()
    return n.strftime("%Y-%m-%d %H:%M:%S") if n else ""


def _today():
    n = _now()
    return n.strftime("%Y-%m-%d") if n else ""


def build_user(stream, per_stream=PER_STREAM, today=""):
    """The user message for one stream: today's date, the beat, the unverified
    seed memory, and a hard cap on how many facts we want back."""
    parts = []
    if today:
        parts.append("تاريخ اليوم: %s" % today)
    parts.append(stream["focus"].strip())
    if stream.get("seed"):
        parts.append(stream["seed"].strip())
    parts.append("رجّع على الأكثر %d حقائق، الأقوى أولاً. الجودة أهم من العدد — "
                 "حقيقة وحدة مؤكدة أفضل من أربع مخترعة." % max(1, int(per_stream)))
    return "\n\n".join(parts)


def collect(streams=None, per_stream=PER_STREAM):
    """Blocking collection pass (call inside a thread). Runs each stream's live
    search, keeps only grounded + novel signals, stores them, prunes the feed, and
    returns the list of NEW signal dicts. One stream blowing up never stops the
    others — its error is counted and the run continues."""
    search = HOST.require("claude_search")
    model = getattr(HOST, "model_premium", None)
    keys = [k for k in (streams or STREAM_KEYS) if k in _BY_KEY]
    today, ts = _today(), _now_iso()

    _p(running=True, phase="search", stream="", found=0, kept=0, dropped=0,
       errors=0, done=False, error="", started_at=ts, finished_at="",
       streams=list(keys))

    try:
        recent = list(db.signal_nkeys())
    except Exception:
        recent = []

    new_signals, found = [], 0
    dropped = errors = 0
    per_stream = max(1, int(per_stream or 1))

    for key in keys:
        st = _BY_KEY[key]
        _p(phase="search", stream=key)
        try:
            got = search(st["system"], build_user(st, per_stream, today),
                         max_tokens=MAX_TOKENS, model=model,
                         max_uses=SEARCH_MAX_USES)
            # tolerate a bare None / a non-pair return instead of (data, urls)
            if isinstance(got, tuple) and len(got) == 2:
                data, urls = got
            else:
                data, urls = got, []
        except Exception as e:
            print("[studio.external] %s search failed: %s: %s" % (key, type(e).__name__, e))
            errors += 1
            _p(errors=errors)
            continue

        try:
            # parse_signals is the gate: no url / no YYYY-MM-DD as_of -> dropped here.
            sigs = engine.parse_signals(data, "external", default_source=key)
            raw_n = len((data or {}).get("signals") or []) if isinstance(data, dict) else 0
            found += raw_n
            dropped += max(0, raw_n - len(sigs))

            for sig in sigs[:per_stream]:
                nkey = engine.novelty_key("%s %s" % (sig.get("title", ""), sig.get("fact", "")))
                if not engine.is_novel(nkey, recent):
                    dropped += 1
                    continue
                try:
                    db.add_signal(sig, nkey=nkey, ts=ts)
                except Exception as e:
                    print("[studio.external] store failed (%s): %s" % (key, e))
                    errors += 1
                    continue
                recent.append(nkey)
                new_signals.append(sig)
            _p(found=found, kept=len(new_signals), dropped=dropped, errors=errors,
               last_urls=list(urls or [])[:8])
        except Exception as e:
            traceback.print_exc()
            print("[studio.external] %s parse failed: %s" % (key, e))
            errors += 1
            _p(errors=errors)
            continue

    try:
        db.prune_signals(PRUNE_KEEP)
    except Exception as e:
        print("[studio.external] prune failed:", e)

    _p(running=False, phase="done", done=True, kept=len(new_signals),
       finished_at=_now_iso())
    print("[studio.external] collect done: found=%s kept=%s dropped=%s errors=%s"
          % (found, len(new_signals), dropped, errors))
    try:
        if HOST.save_json:
            HOST.save_json("studio_external.json", snapshot())
    except Exception:
        pass
    return new_signals


def start_collect_thread(streams=None, per_stream=PER_STREAM):
    """Kick a collection pass in a daemon thread. False if one is already running."""
    with _lock:
        if PROGRESS.get("running"):
            return False
        PROGRESS["running"] = True

    def _target():
        try:
            collect(streams=streams, per_stream=per_stream)
        except Exception as e:
            traceback.print_exc()
            _p(running=False, phase="error", done=True,
               error="%s: %s" % (type(e).__name__, e), finished_at=_now_iso())

    t = threading.Thread(target=_target, name="studio-external", daemon=True)
    t.start()
    return True
