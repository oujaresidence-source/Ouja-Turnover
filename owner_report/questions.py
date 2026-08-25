# -*- coding: utf-8 -*-
"""
WIZARD QUESTION BANK  (spec §3, sections A–H)

Bilingual (AR/EN), gated, cannot be skipped. This is the DATA layer of the pre-flight
interrogation — the (deferred) dashboard wizard UI renders from it, and the audit log
stores the answers. Each question declares:

    id, section, kind, en/ar prompt, provenance tag it feeds (H/O/M/C), whether it is
    required (blocks render if unanswered), and — where relevant — the gate/warning code
    it maps to in validate.py, so the wizard can explain WHY a question matters.

`kind`: choice | number | percent | money | text | date | bool | list
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Q:
    id: str
    section: str          # A..H
    kind: str
    en: str
    ar: str
    tag: str = "O"        # provenance the answer feeds
    required: bool = True
    options: tuple = ()   # for choice kind: ((value, en, ar), ...)
    maps_to: str = ""     # gate / warning code in validate.py, if any
    note_en: str = ""
    note_ar: str = ""


SECTIONS = {
    "A": ("Scope", "النطاق"),
    "B": ("Availability integrity", "سلامة التوافر"),
    "C": ("Revenue definition", "تعريف الإيراد"),
    "D": ("Costs", "التكاليف"),
    "E": ("Long-term lease benchmark", "مرجع العقد السنوي"),
    "F": ("Comp set", "مجموعة المنافسين"),
    "G": ("Market & regulatory", "السوق والتنظيم"),
    "H": ("Projection", "التوقعات"),
}

_EXCL = (("exclude", "Exclude from available nights", "استبعادها من الليالي المتاحة"),
         ("vacant", "Count as vacant", "احتسابها كليالٍ شاغرة"))

QUESTIONS = [
    # ---- A. Scope ----
    Q("unit", "A", "choice", "Which unit?", "أي وحدة؟", tag="O"),
    Q("period_start", "A", "date", "Report period — start.", "بداية فترة التقرير."),
    Q("period_end", "A", "date", "Report period — end.", "نهاية فترة التقرير."),
    Q("full_period", "A", "bool",
      "Was the unit under management for the ENTIRE period?",
      "هل كانت الوحدة تحت الإدارة طوال الفترة بالكامل؟",
      note_en="If not, the period is truncated and stated on the cover.",
      note_ar="إن لم يكن، تُقصَّر الفترة ويُذكر ذلك على الغلاف."),
    # ---- B. Availability integrity ----
    Q("owner_blocked_nights", "B", "number",
      "Owner-blocked (personal-use) nights?", "ليالي حجز المالك (استخدام شخصي)؟"),
    Q("owner_blocked_treatment", "B", "choice",
      "Treat owner-blocked nights as…", "معاملة ليالي حجز المالك على أنها…",
      options=_EXCL, note_en="Default exclude; this swings occupancy 5–10 points.",
      note_ar="الافتراضي الاستبعاد؛ يغيّر الإشغال 5–10 نقاط."),
    Q("maint_blocked_nights", "B", "number",
      "Maintenance / renovation blocked nights?", "ليالي إيقاف للصيانة/التجديد؟", required=False),
    Q("maint_blocked_treatment", "B", "choice",
      "Treat maintenance blocks as…", "معاملة إيقاف الصيانة على أنها…", options=_EXCL, required=False),
    Q("listing_unpublished", "B", "bool",
      "Was the listing ever unpublished, snoozed, or delisted in the period?",
      "هل تم إيقاف الإعلان أو تعليقه أو حذفه خلال الفترة؟", required=False),
    # ---- C. Revenue definition ----
    Q("vat_basis", "C", "choice",
      "Do Hostaway's financial fields INCLUDE 15% VAT, or are they net of it?",
      "هل الحقول المالية في Hostaway شاملة ضريبة 15% أم صافية منها؟",
      options=(("net", "Net of VAT", "صافية من الضريبة"),
               ("inclusive", "Include VAT", "شاملة الضريبة")),
      maps_to="vat_resolved",
      note_en="Verify by reconciling one real reservation against its Airbnb payout.",
      note_ar="تحقّق بمطابقة حجز حقيقي مع تحويل Airbnb الفعلي."),
    Q("cleaning_fee_treatment", "C", "choice",
      "Cleaning fees: pass-through or retained?", "رسوم التنظيف: تمريرية أم محتجزة؟",
      options=(("passthrough", "Pass-through to guest", "تُمرَّر للضيف"),
               ("retained", "Retained", "محتجزة"))),
    Q("include_recoveries", "C", "bool",
      "Include damage-claim recoveries, resolution payouts, cancellation fees?",
      "تضمين تعويضات الأضرار ومدفوعات التسوية ورسوم الإلغاء؟", required=False),
    Q("manual_bookings", "C", "list",
      "Bookings taken OUTSIDE Hostaway (direct / WhatsApp / bank) to add manually?",
      "حجوزات تمّت خارج Hostaway (مباشر/واتساب/تحويل) تُضاف يدويًا؟",
      tag="O", required=False, maps_to="manual_bookings",
      note_en="Capture each with a reason; tagged as operator input.",
      note_ar="سجّل كل واحد مع السبب؛ يُوسم كمُدخَل مشغّل."),
    # ---- D. Costs ----
    Q("mgmt_fee_pct", "D", "percent", "Management fee %?", "نسبة رسوم الإدارة؟"),
    Q("mgmt_fee_basis", "D", "choice",
      "Management fee basis?", "أساس رسوم الإدارة؟",
      options=(("net", "Net rental revenue", "صافي إيراد الإيجار"),
               ("gross", "Gross revenue", "إجمالي الإيراد"))),
    Q("channel_fees_basis", "D", "choice",
      "Channel fees: actual per-reservation, or a blended estimate?",
      "رسوم القنوات: فعلية لكل حجز أم تقدير مدمج؟",
      options=(("actual", "Actual per-reservation", "فعلية لكل حجز"),
               ("blended", "Blended estimate", "تقدير مدمج"))),
    Q("opex_owner_borne", "D", "list",
      "From expenses: which line items are OWNER-borne (tick each)?",
      "من المصروفات: أي بنود يتحمّلها المالك (اختر كل بند)؟", tag="H"),
    Q("capex_in_period", "D", "list",
      "Any owner-approved capex in the period?", "أي نفقات رأسمالية معتمدة من المالك في الفترة؟",
      required=False),
    # ---- E. Long-term lease benchmark ----
    Q("purchase_price", "E", "money", "Purchase price (SAR)?", "سعر الشراء (ريال)؟",
      maps_to="purchase_price_present"),
    Q("ejar_annual_rent", "E", "money", "Ejar registered annual rent (SAR)?",
      "قيمة العقد السنوي المسجّل في إيجار (ريال)؟"),
    Q("ejar_is_single_contract", "E", "choice",
      "One contract, or a sample of comparables?", "عقد واحد أم عيّنة من المقارنات؟",
      options=(("single", "One contract (a baseline)", "عقد واحد (خط أساس)"),
               ("sample", "3+ comparables (use median + range)", "3+ مقارنات (استخدم الوسيط والمدى)")),
      maps_to="ejar_is_single_contract",
      note_en="A single contract is a BASELINE, never a benchmark.",
      note_ar="العقد الواحد خط أساس وليس مرجعًا."),
    Q("ejar_furnished", "E", "choice",
      "Is the Ejar comparable FURNISHED or UNFURNISHED?  (most important question)",
      "هل المقارنة في إيجار مفروشة أم غير مفروشة؟ (أهم سؤال)",
      options=(("furnished", "Furnished", "مفروشة"),
               ("unfurnished", "Unfurnished", "غير مفروشة")),
      maps_to="ejar_unfurnished_no_uplift",
      note_en="Comparing furnished STR to an unfurnished lease overstates the STR advantage.",
      note_ar="مقارنة التأجير قصير المفروش بعقد غير مفروش تبالغ في ميزة التأجير قصير الأجل."),
    Q("furnished_uplift_pct", "E", "percent",
      "If unfurnished: furnished-uplift % (Riyadh ~15–30%)?",
      "إن كانت غير مفروشة: نسبة زيادة الفرش (الرياض ~15–30%)؟", required=False),
    Q("delivered_furnished", "E", "bool",
      "Was the unit DELIVERED furnished, or did the owner fund the furnishing?",
      "هل سُلّمت الوحدة مفروشة أم موّل المالك الفرش؟",
      note_en="Delivered furnished -> no furnishing capex, capital = purchase price.",
      note_ar="سُلّمت مفروشة -> لا نفقات فرش، رأس المال = سعر الشراء."),
    Q("lease_costs", "E", "list",
      "Under an annual lease: brokerage %, vacancy %, owner maintenance, admin fees.",
      "تحت عقد سنوي: عمولة الوساطة %، نسبة الشغور %، صيانة المالك، رسوم إدارية.", required=False),
    # ---- F. Comp set ----
    Q("comp_units", "F", "list",
      "Which competitor units? For each: ADR, occupancy, source, as-of date.",
      "أي وحدات منافسة؟ لكل منها: متوسط السعر، الإشغال، المصدر، تاريخ الرصد.", tag="M"),
    Q("comp_observed", "F", "choice",
      "Comp data observed or estimated?", "بيانات المنافسين مرصودة أم مقدّرة؟",
      options=(("observed", "Observed", "مرصودة"), ("estimated", "Estimated", "مقدّرة")),
      tag="M", maps_to="comp_stale",
      note_en="Older than 90 days -> a dated warning prints in the PDF.",
      note_ar="أقدم من 90 يومًا -> تُطبع ملاحظة بالتاريخ."),
    # ---- G. Market & regulatory ----
    Q("yield_benchmarks", "G", "list",
      "Riyadh yield benchmarks + source + as-of date.",
      "مؤشرات العائد في الرياض + المصدر + تاريخ الرصد.", tag="M"),
    Q("rent_freeze", "G", "bool",
      "Rent freeze applicability + end date (REGA; currently Sept 2030)?",
      "انطباق تجميد الإيجارات وتاريخ انتهائه (الهيئة؛ حاليًا سبتمبر 2030)؟",
      note_en="Rent-freeze language carries a 'not legal advice' caveat.",
      note_ar="لغة تجميد الإيجارات مصحوبة بتنويه 'ليست استشارة قانونية'."),
    # ---- H. Projection ----
    Q("projection", "H", "list",
      "Scenario assumptions (low/base/high), growth rate, stated assumption list.",
      "فرضيات السيناريو (منخفض/أساسي/مرتفع)، معدل النمو، قائمة الفرضيات.", tag="C"),
]

BY_ID = {q.id: q for q in QUESTIONS}
BY_SECTION = {s: [q for q in QUESTIONS if q.section == s] for s in SECTIONS}
REQUIRED_IDS = [q.id for q in QUESTIONS if q.required]


def missing_required(answers: dict) -> list:
    """Return required question ids with no answer in `answers` (a {id: value} map)."""
    return [qid for qid in REQUIRED_IDS if qid not in answers or answers[qid] in (None, "")]
