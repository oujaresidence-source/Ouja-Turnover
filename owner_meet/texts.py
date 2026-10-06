# -*- coding: utf-8 -*-
"""
owner_meet.texts — every owner-facing Arabic word in one place, plus number and date formatting.

Owner copy is simplified STANDARD Arabic (not Najdi): written by an operator who has already
decided. Dates are always words («6 أكتوبر 2026»), never ISO — an ISO date inside Arabic text is
reordered by the bidi algorithm (the ownerbill lesson). No backslashes in this file (brief P3).
"""

import datetime

MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر",
          "أكتوبر", "نوفمبر", "ديسمبر")
BEDROOMS = {0: "استوديو", 1: "غرفة نوم واحدة", 2: "غرفتا نوم", 3: "ثلاث غرف نوم", 4: "أربع غرف نوم",
            5: "خمس غرف نوم"}

CH = {
    "portfolio": "شققك معاً",
    "cover": "الغلاف",
    "summary": "الخلاصة",
    "money": "أين ذهب كل ريال",
    "monthly": "شهراً بشهر",
    "peers": "مكانك بين شققنا",
    "funnel": "كيف يصل إلينا الضيف",
    "log": "سجلّ الشقة",
    "maint": "الصيانة",
    "claims": "طلبات التعويض",
    "reviews": "ماذا قال الضيوف",
    "plan": "ما اكتشفناه وما نطبّقه من الآن",
    "forecast": "الربع القادم",
    "promises": "ما وعدناك به في الاجتماع الماضي",
    "agreed": "ما اتفقنا عليه اليوم",
}

UPLIFT = {"rate": "رفع التقييم", "ctr": "صورة وعنوان جديدان", "page": "مراجعة السعر وترتيب الصور",
          "pace": "مراجعة يومية لسعر الأسبوعين القادمين", "test": "تجربة الخصم المدروسة", "season": "موسم الربع القادم"}
LEVER_AR = {"weekly": "خصم الأسبوع", "early_bird": "خصم الحجز المبكر", "monthly": "خصم الشهر",
            "non_refundable": "خيار غير قابل للاسترداد", "last_minute": "خصم اللحظة الأخيرة", "new_listing": "عرض الإعلان الجديد"}
DECISION_AR = {"test": "اختبار فقط", "no": "لا", "remove": "يُلغى", "yes": "نعم"}

WATERFALL = {"income": "صافي الحجوزات", "fee": "رسوم عوجا", "cleaning": "التنظيف",
             "expenses": "مصاريف الشقة", "adjustments": "تعديلات الكشف", "net": "صافي المالك"}
PER100 = {"fee": "رسوم عوجا", "cleaning": "التنظيف", "expenses": "مصاريف الشقة", "owner": "للمالك"}

METRIC = {
    "income": ("قيمة الحجوزات", "ما دفعه الضيوف للفترة"),
    "net_per_night": ("صافي الليلة المتاحة", "صافي المالك ÷ أيام الفترة"),
    "occupancy": ("الإشغال", "الليالي المحجوزة من أيام الفترة"),
    "adr": ("متوسط سعر الليلة", "قيمة الحجوزات ÷ الليالي"),
    "rating": ("تقييم الضيوف", "متوسط كل التقييمات من 5"),
    "next14": ("المحجوز من الأسبوعين القادمين", "من 14 ليلة تبدأ اليوم"),
}

CHIP = {"top": "أعلى من %d٪", "mid": "ضمن الوسط", "low": "أقل من الأغلب"}

SEASON = {"ramadan": "رمضان", "eid_fitr": "عيد الفطر", "eid_adha": "عيد الأضحى"}

EMPTY = {
    "monthly": "لا توجد أشهر في هذه الفترة",
    "peers": "لا توجد شقق مشابهة كافية للمقارنة في هذه الفترة",
    "funnel": "لا يوجد تقرير Airbnb مربوط بهذه الشقة بعد — نضيفه في الاجتماع القادم",
    "money": "تعذّر رسم التوزيع لأن بنود الكشف لا تطابق الصافي — هذه إجماليات الكشف كما هي",
    "log": "لا توجد أحداث مسجّلة لهذه الشقة في هذه الفترة",
    "maint": "لا توجد تذاكر صيانة في هذه الفترة",
    "claims": "لم نفتح طلبات تعويض لهذه الشقة في هذه الفترة",
    "reviews": "لا توجد تقييمات في هذه الفترة",
    "plan": "لا توجد إجراءات جديدة لهذه الشقة — نستمر على الخطة الحالية",
    "forecast": "نحتاج ثلاثة أشهر كاملة من بيانات الشقة لنضع هدفاً",
}

SRC_OPS = "المصدر: تذاكر عوجا (ديسكورد ولوحة التحكم)"
SRC_RR = "المصدر: طلبات التعويض في عوجا وردود Airbnb"
SRC_REVIEWS = "المصدر: تقييمات Airbnb كما تصل إلى Hostaway"

SRC_STATEMENT = "المصدر: كشف المالك الشهري في نظام عوجا"
SRC_PEERS = "المصدر: حجوزات شقق عوجا المشابهة في الفترة نفسها، دون أي بيانات لمالك آخر"
CLOSING = "نلاحق كل ريال لشقتك."


# ------------------------------------------------------------------ numbers
def num(x, nd=0):
    """Latin digits with thousands separators — the page isolates them with class .n (dir=ltr)."""
    if x is None:
        return "—"
    v = round(float(x), nd)
    if nd == 0:
        return "{:,}".format(int(round(v)))
    return ("{:,.%df}" % nd).format(v)


def money(x):
    return num(x, 0)


def compact(x):
    """1234 -> 1.2k, 87000 -> 87k, 1234567 -> 1.2M (chart labels only)."""
    if x is None:
        return "—"
    v = float(x)
    a = abs(v)
    if a >= 1000000:
        s = "%.1fM" % (v / 1000000.0)
    elif a >= 10000:
        s = "%dk" % int(round(v / 1000.0))
    elif a >= 1000:
        s = "%.1fk" % (v / 1000.0)
    else:
        s = "%d" % int(round(v))
    return s.replace(".0k", "k").replace(".0M", "M")


def pct(x, nd=0):
    if x is None:
        return "—"
    return num(float(x) * 100.0, nd) + "٪"


# ------------------------------------------------------------------ dates
def _d(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    return datetime.date.fromisoformat(str(v)[:10])


def date_ar(v):
    d = _d(v)
    return "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)


def day_month_ar(v):
    d = _d(v)
    return "%d %s" % (d.day, MONTHS[d.month - 1])


def month_ar(mk, year=False):
    y, m = int(mk[:4]), int(mk[5:7])
    return MONTHS[m - 1] + ((" %d" % y) if year else "")


def range_ar(start, end):
    a, b = _d(start), _d(end)
    if a.year == b.year:
        if a.month == b.month:
            return "من %d إلى %d %s %d" % (a.day, b.day, MONTHS[a.month - 1], a.year)
        return "من %d %s إلى %d %s %d" % (a.day, MONTHS[a.month - 1], b.day, MONTHS[b.month - 1], b.year)
    return "من %s إلى %s" % (date_ar(a), date_ar(b))


EN_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
             "october", "november", "december")


def source_date_ar(text):
    """«July 2026» (as the cp data files store it) -> «يوليو 2026»; an ISO date -> words; else as-is."""
    t = (text or "").strip()
    if not t:
        return ""
    try:
        return date_ar(t)
    except ValueError:
        pass
    words = t.split()
    if len(words) == 2 and words[0].lower() in EN_MONTHS:
        return "%s %s" % (MONTHS[EN_MONTHS.index(words[0].lower())], words[1])
    return t


def bedrooms(n):
    if n is None:
        return ""
    return BEDROOMS.get(int(n), "%d غرف نوم" % int(n))


def chip(band):
    if not band or not band.get("tone"):
        return None
    t = band["tone"]
    if t == "top":
        return CHIP["top"] % min(band.get("pct10") or 60, 90)
    return CHIP[t]
