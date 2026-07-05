# -*- coding: utf-8 -*-
"""finchat.answer — KB-grounded answering. Haiku first; low confidence → one Sonnet retry;
still low → escalation offer. Never invents numbers (prompt-enforced + KB-grounded)."""
import json
import re

from . import db as _db
from . import kb as _kb
from .erpmap import ERP_MAP_AR

CFG = {
    "claude": None,            # bot.py's claude_text(system, user, max_tokens, model)
    "conf": 0.6,
    "model_fast": "claude-haiku-4-5-20251001",
    "model_smart": "claude-sonnet-5",
    "daily_cap": 80,
    "enabled": True,
}

SYSTEM_AR = """أنت «مساعد المركز المالي» لفريق محاسبة عوجا ريزيدنس. ترد بالعربي (لهجة نجدية خفيفة، مهني وودود).
قوانينك الصارمة:
1) جاوب فقط من المعرفة المرفقة + خريطة الشاشات. لا تخترع خطوات أو أزرار غير مذكورة.
2) لا تذكر أي رقم مالي أبداً — الأرقام الحية مكانها الشاشات؛ دلّ السائل على الشاشة الصحيحة برابطها.
3) لو السؤال خارج معرفتك أو تشك، خفّض confidence تحت 0.5 بصراحة — لا تخمن.
4) الروابط: استخدم فقط الراوتات المذكورة في الخريطة أو المعرفة (تبدأ بـ #).
رد حصراً بـ JSON واحد بالشكل:
{"answer": "الجواب بالعربي", "confidence": 0.0-1.0, "links": [{"label_ar": "اسم الشاشة", "route": "#..."}]}"""


def _parse(text):
    if not text:
        return None
    t = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _user_block(question, cands):
    parts = [ERP_MAP_AR, "", "المعرفة (أسئلة شائعة مع أجوبتها):"]
    for e in cands:
        links = " ".join(l.get("route", "") for l in (e.get("links") or []))
        parts.append("- س: %s\n  ج: %s %s" % (e["q_ar"], e["answer_ar"], ("(" + links + ")") if links else ""))
    if len(parts) == 3:
        parts.append("(لا توجد معرفة مطابقة — غالباً هذا سؤال يحتاج فيصل)")
    parts += ["", "سؤال المحاسب: " + question, "", "رد بالـ JSON فقط."]
    return "\n".join(parts)


def _call(question, cands, model):
    raw = CFG["claude"](SYSTEM_AR, _user_block(question, cands), max_tokens=700, model=model)
    p = _parse(raw)
    if not isinstance(p, dict) or not p.get("answer"):
        return None
    try:
        p["confidence"] = max(0.0, min(1.0, float(p.get("confidence", 0))))
    except Exception:
        p["confidence"] = 0.0
    p["links"] = [l for l in (p.get("links") or [])
                  if isinstance(l, dict) and str(l.get("route", "")).startswith("#")]
    return p


def answer_question(username, question):
    """Sync (call via asyncio.to_thread from routes). Returns the /ask contract shape."""
    if not CFG.get("enabled"):
        return {"error": "disabled"}
    if _db.msgs_today_count(username) >= CFG["daily_cap"]:
        return {"error": "daily_cap",
                "message_ar": "وصلت الحد اليومي للأسئلة — كلم فيصل لو الموضوع مستعجل."}
    entries = _db.kb_all(enabled_only=True)
    cands = _kb.retrieve(question, entries, k=8)
    _db.msg_add(username, "user", question)

    p = _call(question, cands, CFG["model_fast"])
    model = CFG["model_fast"]
    if p is None or p["confidence"] < CFG["conf"]:
        cands16 = _kb.retrieve(question, entries, k=16)
        p2 = _call(question, cands16, CFG["model_smart"])
        if p2 is not None and (p is None or p2["confidence"] >= p["confidence"]):
            p, model = p2, CFG["model_smart"]
    if p is None:
        return {"error": "api_error",
                "message_ar": "تعذر الاتصال بالمساعد — جرب بعد شوي أو صعّد لفيصل."}

    esc_offer = p["confidence"] < CFG["conf"]
    kb_ids = [e["id"] for e in cands]
    msg_id = _db.msg_add(username, "bot", p["answer"], kb_ids=kb_ids, model=model,
                         confidence=p["confidence"], links=p["links"])
    return {"ok": True, "answer": p["answer"], "links": p["links"], "model": model,
            "confidence": p["confidence"], "esc_offer": esc_offer, "msg_id": msg_id}
