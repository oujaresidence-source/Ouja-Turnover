# -*- coding: utf-8 -*-
"""
stayhub.notify — the Arabic lines posted to Discord. Delivery is HOST.notify(text) (bot.py
posts to STAYHUB_CHANNEL). NEVER a guest name, phone or email — the unit, the dates and the
Airbnb code are enough for the team to act.
"""
from .host import HOST

REASON_AR = {
    "SNAPSHOT_AVAILABILITY_MISMATCH": "التواريخ مو متاحة في تقويم ستاي هب",
    "INVENTORY_RACE": "انحجزت نفس التواريخ في ستاي هب بنفس اللحظة",
    "INVENTORY_TAKEN": "التواريخ محجوزة في ستاي هب",
    "SNAPSHOT_PRICE_MISMATCH": "السعر تغيّر في ستاي هب أثناء الحجز",
    "PROPERTY_VERSION_OUTDATED": "بيانات الوحدة تغيّرت في ستاي هب",
    "PROPERTY_SUSPENDED_STALE_SYNC": "ستاي هب موقف الوحدة مؤقتاً",
    "FORBIDDEN_PROPERTY": "المالك سحب صلاحية عوجا على الوحدة",
    "FORBIDDEN_INSUFFICIENT_ROLE": "صلاحيات حساب عوجا في ستاي هب ناقصة",
    "IDEMPOTENCY_CONFLICT": "رقم المراجعة ما تطابق مع ستاي هب",
    "SNAPSHOT_CURRENCY_MISMATCH": "العملة مختلفة",
    "VALIDATION_ERROR": "ستاي هب رفض البيانات المرسلة",
    "NO_AVAILABILITY": "ليلة أو أكثر مقفلة أو بدون سعر في تقويم ستاي هب",
    "NO_PHONE": "رقم جوال الضيف ناقص — ستاي هب ما يقدر يرسل له رابط التحقق",
}


def reason_ar(code):
    return REASON_AR.get(str(code or "").upper(), str(code or "خطأ غير معروف"))


def _unit(listing_id):
    try:
        m = HOST.listings() if getattr(HOST, "listings", None) else {}
    except Exception:
        m = {}
    if not listing_id:
        return "—"
    return (m or {}).get(listing_id) or (m or {}).get(str(listing_id)) or "وحدة %s" % listing_id


def send(text):
    fn = getattr(HOST, "notify", None)
    if fn:
        try:
            fn(text)
            return True
        except Exception as e:
            print("[stayhub] notify failed (non-fatal):", e)
    print("[stayhub] " + text.replace("\n", " · "))
    return False


def rejected_text(row, code, detail=""):
    return ("⚠️ **ستاي هب رفض حجز Airbnb**\n"
            "الوحدة: %s · من %s إلى %s · كود Airbnb: `%s`\n"
            "السبب: %s%s\n"
            "المطلوب: افتحوا تقويم الوحدة في ستاي هب وتأكدوا إن الليالي مفتوحة وفيها سعر. "
            "النظام يعيد المحاولة تلقائياً كل كم ساعة."
            % (_unit(row.get("listing_id")), row.get("check_in"), row.get("check_out"),
               row.get("external_id") or "—", reason_ar(code), (" (%s)" % detail) if detail else ""))


def failed_text(row, code):
    return ("🛑 **حجز ما وصل ستاي هب ويحتاج تدخل**\n"
            "الوحدة: %s · من %s إلى %s · كود Airbnb: `%s`\n"
            "السبب: %s — ما راح يعيد المحاولة لحاله."
            % (_unit(row.get("listing_id")), row.get("check_in"), row.get("check_out"),
               row.get("external_id") or "—", reason_ar(code)))


def no_phone_text(row):
    return ("📵 حجز وصل ستاي هب **بدون رقم جوال صالح** — الوحدة %s · كود `%s`. "
            "أرسلوا رابط ما قبل الوصول يدوياً أو أضيفوا الرقم في ستاي هب."
            % (_unit(row.get("listing_id")), row.get("external_id") or "—"))


def cancel_failed_text(row, code):
    return ("⚠️ **إلغاء ما انعكس في ستاي هب** — الوحدة %s · كود `%s` · السبب: %s. "
            "ألغوه يدوياً من ستاي هب عشان ما تبقى الليالي مقفلة."
            % (_unit(row.get("listing_id")), row.get("external_id") or "—", reason_ar(code)))


def property_text(pid, what, mapping):
    unit = _unit((mapping or {}).get("listing_id")) if mapping else "وحدة غير مربوطة"
    if what == "deauthorized":
        return ("🔌 **مالك سحب صلاحية عوجا في ستاي هب** — %s (`%s`). "
                "الحجوزات الجديدة لهذي الوحدة ما راح توصل ستاي هب لين يرجع يعطي الصلاحية." % (unit, pid))
    return ("⏸️ **ستاي هب أوقف الوحدة مؤقتاً** (تأخر المزامنة) — %s (`%s`). "
            "النظام يعيد المزامنة تلقائياً." % (unit, pid))


def daily_text(summary):
    lines = ["📋 **مطابقة ستاي هب اليومية**"]
    lines.append("مؤكد: %(confirmed)s · بانتظار: %(pending)s · مرفوض: %(rejected)s · يحتاج تدخل: %(failed)s" % summary)
    if summary.get("mismatches"):
        lines.append("اختلافات المطابقة: %s (التفاصيل في لوحة ستاي هب)" % summary["mismatches"])
    for r in summary.get("rejected_rows", [])[:10]:
        lines.append("• %s · %s→%s · `%s` · %s" % (_unit(r.get("listing_id")), r.get("check_in"), r.get("check_out"),
                                                   r.get("external_id") or "—", reason_ar(r.get("last_code"))))
    return "\n".join(lines)
