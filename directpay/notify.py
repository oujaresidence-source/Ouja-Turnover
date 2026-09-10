# -*- coding: utf-8 -*-
"""
directpay.notify — the Arabic wording, built here; delivery is HOST.notify (wired in bot.py),
DRY-RUN by default so the first deploy posts nothing (decor/notify.py pattern).

Every builder returns plain text lines. bot.py turns the card into an embed and does the
pinging; the words live here so the room, the dashboard and the daily summary say the same
thing. StayHub is never called — this ledger is a human attestation, and the copy says so.
"""
from . import config, engine
from .host import HOST

RULE_LINE = "هذي غرفة تحصيل. ما تنقفل إلا بعد ما يوصل المبلغ في StayHub وترفع صورة/فاتورة تثبت ذلك."


def dryrun():
    """ON by default — read live from the environment so a Railway flip needs no deploy."""
    return config.dryrun()


def fmt_sar(v):
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return "—"
    return ("{:,.0f}".format(f) if f.is_integer() else "{:,.2f}".format(f)) + " ر.س"


def channel_name(seq, slug):
    return "تحصيل-%03d-%s" % (int(seq or 0), str(slug or "unit"))[:95]


def topic(ticket):
    return "ouja-dp:%s seq:%s lid:%s" % (ticket.get("reservation_id"), ticket.get("seq") or 0,
                                         ticket.get("listing_id") or 0)


def payment_line(ticket):
    """Printed WITH the field names it read — _payment_signal harvests, it infers nothing,
    and the card must not pretend otherwise."""
    fields = str(ticket.get("ha_payment_fields") or "").strip()
    st = ticket.get("ha_payment_status")
    paid = ticket.get("ha_paid_amount")
    rem = ticket.get("ha_remaining")
    if not fields and st is None and paid is None and rem is None:
        return "حالة الدفع في Hostaway: ما فيه أي حقل دفع على الحجز (هذا مو دليل بشي)."
    bits = []
    if st:
        bits.append("الحالة: %s" % st)
    if paid is not None:
        bits.append("المدفوع: %s" % fmt_sar(paid))
    if rem is not None:
        bits.append("المتبقي: %s" % fmt_sar(rem))
    src = " (من الحقول: %s)" % fields if fields else ""
    return "حالة الدفع في Hostaway: " + (" · ".join(bits) if bits else "—") + src + " — للاستئناس، مو إثبات."


def card_fields(ticket, res_url=""):
    """[(name, value)] for the pinned card, in the owner's order."""
    dates = "%s ← %s" % (ticket.get("arrival") or "—", ticket.get("departure") or "—")
    if ticket.get("nights"):
        dates += " (%s ليالي)" % ticket.get("nights")
    ch = ticket.get("channel_raw")
    ch = "«فارغ» — Hostaway ما حط قناة، وهذا يعتبر مباشر" if not str(ch or "").strip() else str(ch)
    out = [("الوحدة", ticket.get("unit_name") or "—"),
           ("الضيف", ticket.get("guest_name") or "—"),
           ("التواريخ", dates),
           ("المبلغ الإجمالي", fmt_sar(ticket.get("total_sar_current") if ticket.get("total_sar_current") is not None else ticket.get("total_sar"))),
           ("القناة (كما في Hostaway)", ch),
           ("رقم الحجز", "%s · كود %s" % (ticket.get("reservation_id"), ticket.get("confirmation_code") or "—")),
           ("تاريخ الحجز", str(ticket.get("booked_at") or "—")[:16]),
           ("الدفع في Hostaway", payment_line(ticket))]
    if res_url:
        out.append(("رابط الحجز", res_url))
    return out


def card_status_line(ticket):
    st = ticket.get("status") or "open"
    if st == "open":
        return "⏳ مفتوحة — بانتظار تأكيد وصول المبلغ في StayHub"
    if st == "verified":
        return "✅ تم التحصيل — %s · مرجع StayHub: %s · بواسطة %s" % (
            fmt_sar(ticket.get("received_sar")), ticket.get("stayhub_ref") or "—", ticket.get("closed_by") or "—")
    if st == "written_off":
        return "🔴 إغلاق بدون إثبات — %s" % (ticket.get("close_note") or "")
    if st == "void":
        return "⚪ ملغاة — %s" % (ticket.get("void_reason") or "")
    return st


def open_text(ticket):
    return "💰 حجز مباشر جديد — %s · %s · %s" % (ticket.get("unit_name") or "—",
                                                  ticket.get("guest_name") or "—",
                                                  fmt_sar(ticket.get("total_sar")))


def nudge_text(ticket, age):
    return ("⏰ هذي الغرفة مفتوحة من %d يوم والمبلغ %s ما انأكد وصوله في StayHub. "
            "إذا وصل: ارفع الإثبات واضغط «تم التحصيل ✅»." % (int(age), fmt_sar(engine.row_amount(ticket))))


def close_text(ticket):
    v = ticket.get("variance_sar")
    lines = ["✅ **تم التحصيل** — %s في StayHub · المرجع: %s" % (fmt_sar(ticket.get("received_sar")),
                                                                 ticket.get("stayhub_ref") or "—"),
             "اعتمدها: %s" % (ticket.get("closed_by") or "—")]
    try:
        if v is not None and abs(float(v)) > 0.005:
            lines.append("فرق عن مبلغ الحجز: %s — السبب: %s" % (fmt_sar(v), ticket.get("variance_reason") or "—"))
    except (TypeError, ValueError):
        pass
    if ticket.get("close_note"):
        lines.append("ملاحظة: %s" % ticket.get("close_note"))
    lines.append("الغرفة صارت للقراءة فقط — الإثبات محفوظ عندنا (مو رابط ديسكورد).")
    return chr(10).join(lines)


def writeoff_text(ticket):
    return chr(10).join([
        "🔴 **إغلاق بدون إثبات** — %s" % fmt_sar(engine.row_amount(ticket)),
        "قرار: %s" % (ticket.get("closed_by") or "—"),
        "السبب: %s" % (ticket.get("close_note") or "—"),
        "هذي ما تختفي: تبقى ظاهرة بالأحمر في لوحة التحصيل وفي الملخص اليومي."])


def void_text(ticket):
    return chr(10).join([
        "⚪ **أُلغيت الغرفة** — %s" % (ticket.get("void_reason") or "—"),
        "بواسطة: %s · القناة في Hostaway كانت: «%s»" % (ticket.get("closed_by") or "—", ticket.get("channel_raw") or "")])


def price_up_text(ticket, old_total, new_total):
    return ("📈 **المبلغ زاد بعد الإغلاق** · الفرق %s (كان %s وصار %s). الغرفة رجعت مفتوحة — "
            "لازم يوصل الفرق في StayHub ويترفع إثباته." % (fmt_sar(float(new_total) - float(old_total)),
                                                       fmt_sar(old_total), fmt_sar(new_total)))


def price_changed_text(old_total, new_total):
    return "ℹ️ تغيّر مبلغ الحجز في Hostaway: كان %s وصار %s. الغرفة باقية مفتوحة على المبلغ الجديد." % (
        fmt_sar(old_total), fmt_sar(new_total))


def cancelled_text():
    return ("⚠️ **الحجز أُلغي في Hostaway.** ما أقفل الغرفة بنفسي — إذا الضيف دفع، القرار قرار استرجاع "
            "وليس تنظيف. لو ما فيه مبلغ مستحق اضغط «إلغاء الغرفة» واكتب السبب.")


def summary_text(board, room_link=None):
    """One message: open count, outstanding SAR, the four aging buckets, the five oldest with
    links, and the written-off block if any exist this month. Nothing else."""
    t = board.get("totals") or {}
    a = board.get("aging") or {}
    lines = ["📋 **ملخص التحصيل — %s**" % board.get("date", ""),
             "غرف مفتوحة: %d · إجمالي غير محصّل: **%s**" % (int(t.get("open_count") or 0), fmt_sar(t.get("outstanding_sar")))]

    def b(k):
        x = a.get(k) or {}
        return "%d (%s)" % (int(x.get("count") or 0), fmt_sar(x.get("sar")))
    lines.append("العمر: ٠–٢ يوم %s · ٣–٧ %s · ٨–١٤ %s · ١٥+ %s" % (b("b0_2"), b("b3_7"), b("b8_14"), b("b15p")))
    oldest = board.get("oldest") or []
    if oldest:
        lines.append("الأقدم:")
        for r in oldest[:config.summary_bucket_examples()]:
            link = room_link(r.get("channel_id")) if (room_link and r.get("channel_id")) else ""
            lines.append("— %s · %s · %s · %d يوم %s" % (r.get("unit_name") or "—", r.get("guest_name") or "—",
                                                       fmt_sar(engine.row_amount(r)), int(r.get("age_days") or 0), link))
    wo = board.get("written_off_month") or []
    if wo:
        lines.append("🔴 إغلاق بدون إثبات هذا الشهر: %d · %s" % (len(wo), fmt_sar(t.get("written_off_month_sar"))))
        for r in wo[:5]:
            lines.append("— %s · %s · %s · %s · %s" % (r.get("unit_name") or "—", r.get("guest_name") or "—",
                                                   fmt_sar(engine.row_amount(r)), r.get("closed_by") or "—",
                                                   (r.get("close_note") or "")[:80]))
    if board.get("dryrun"):
        lines.append("(وضع التجربة: ما ينفتح غرف ولا ينرسل شي)")
    return chr(10).join(lines)


def fire(kind, payload):
    """Delivery is someone else's job. DRY-RUN prints and returns False so the first deploy is
    observable without posting anything to the team. Every failure is swallowed — a Discord
    problem must never break the ledger."""
    try:
        if dryrun():
            print("[directpay] DRYRUN notify(%s): %s" % (kind, str(payload.get("text", payload.get("ticket_id", "")))[:160]))
            return False
        notifier = getattr(HOST, "notify", None)
        if not notifier:
            return False
        notifier(dict(payload, kind=kind))
        return True
    except Exception as e:
        print("[directpay] notify failed (non-fatal):", e)
        return False
