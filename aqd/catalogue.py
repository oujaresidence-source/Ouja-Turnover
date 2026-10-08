# -*- coding: utf-8 -*-
"""
aqd.catalogue — THE survey. One source for every question, option, rule and Arabic label.

The dashboard tab renders these steps generically (GET /api/aqd/schema) and applies the same
declarative rules for inline errors; the server re-validates every answer with validate()
below, so the browser is never the only gate.

A field is a plain dict:
  key, type ('choice'|'text'|'number'|'date'|'picker'|'check'|'textarea'),
  label_ar, label_en, options [{v, ar, en}], required, default,
  show_if   {other_key: [values...]}  — every listed key must match (AND)
  cond      named condition evaluated identically in Python and JS ('many_same')
  norm      'digits' | 'mobile' | 'upper' | 'trim'
  re / re_by {field, map{value: re}}   msg_ar   — pattern rule (patterns avoid backslashes)
  min, max, step, min_words, not_past, unset_ok, help_ar, placeholder

Unit fields live under step 'units' -> 'unit_fields' and are answered once per unit
(answers['units'] is a list of dicts, one per unit, labelled A1, A2, … automatically).
"""

import datetime
import re

# a number field flagged unset_ok also takes «-» / «غير محدد» (owner ruling 2026-10-08)
UNSET_AR = "غير محدد"
UNSET_WORDS = ("-", "—", "–", UNSET_AR)
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def opt(v, ar, en=None):
    return {"v": v, "ar": ar, "en": en or ar}


# ------------------------------------------------------------------ step 1 — العميل
CLIENT = [
    {"key": "client_kind", "type": "choice", "label_ar": "نوع العميل", "label_en": "Client type",
     "required": True,
     "options": [opt("individual", "فرد", "Individual"), opt("company", "شركة / مؤسسة", "Company")]},
    {"key": "gender", "type": "choice", "label_ar": "الجنس", "label_en": "Gender", "required": True,
     "show_if": {"client_kind": ["individual"]},
     "options": [opt("m", "ذكر", "Male"), opt("f", "أنثى", "Female")]},
    {"key": "id_type", "type": "choice", "label_ar": "نوع الهوية", "label_en": "ID type",
     "required": True, "show_if": {"client_kind": ["individual"]},
     "options": [opt("nid", "هوية وطنية", "National ID"), opt("iqama", "إقامة", "Iqama"),
                 opt("other", "هوية خليجية / جواز", "GCC ID / passport")]},
    {"key": "full_name", "type": "text", "label_ar": "الاسم الكامل (رباعي كما في الهوية)",
     "label_en": "Full name (as on the ID)", "required": True, "norm": "trim", "min_words": 3,
     "show_if": {"client_kind": ["individual"]},
     "msg_ar": "اكتب الاسم رباعي (٣ كلمات على الأقل)"},
    {"key": "id_number", "type": "text", "label_ar": "رقم الهوية / الإقامة", "label_en": "ID number",
     "required": True, "norm": "digits", "show_if": {"client_kind": ["individual"]},
     "re_by": {"field": "id_type", "map": {"nid": "^1[0-9]{9}$", "iqama": "^2[0-9]{9}$",
                                             "other": "^[A-Za-z0-9]{5,20}$"}},
     "msg_by": {"nid": "الهوية الوطنية ١٠ أرقام وتبدأ بـ1", "iqama": "الإقامة ١٠ أرقام وتبدأ بـ2",
                "other": "من ٥ إلى ٢٠ حرف أو رقم (إنجليزي)"}},
    {"key": "company_name", "type": "text", "label_ar": "الاسم النظامي للشركة",
     "label_en": "Legal company name", "required": True, "norm": "trim",
     "show_if": {"client_kind": ["company"]}},
    {"key": "cr_number", "type": "text", "label_ar": "السجل التجاري / الرقم الموحد",
     "label_en": "CR / unified number", "required": True, "norm": "digits", "re": "^[0-9]{10}$",
     "msg_ar": "١٠ أرقام", "show_if": {"client_kind": ["company"]}},
    {"key": "rep_name", "type": "text", "label_ar": "اسم الممثل الموقّع", "label_en": "Signing representative",
     "required": True, "norm": "trim", "show_if": {"client_kind": ["company"]}},
    {"key": "rep_capacity", "type": "choice", "label_ar": "صفة الممثل", "label_en": "Capacity",
     "required": True, "show_if": {"client_kind": ["company"]},
     "options": [opt("manager", "مدير الشركة", "Company manager"),
                 opt("authorized", "مفوّض بالتوقيع", "Authorised signatory")]},
    {"key": "auth_ref", "type": "text", "label_ar": "سند التفويض (رقم / تاريخ)",
     "label_en": "Authorisation reference", "required": True, "norm": "trim",
     "show_if": {"client_kind": ["company"], "rep_capacity": ["authorized"]}},
    {"key": "signer", "type": "choice", "label_ar": "من سيوقّع؟", "label_en": "Who signs?",
     "required": True, "show_if": {"client_kind": ["individual"]}, "default": "self",
     "options": [opt("self", "المالك نفسه", "The owner"), opt("agent", "وكيل بوكالة", "An agent (power of attorney)")]},
    {"key": "agent_name", "type": "text", "label_ar": "اسم الوكيل", "label_en": "Agent name",
     "required": True, "norm": "trim", "min_words": 2, "msg_ar": "اكتب اسم الوكيل كامل",
     "show_if": {"client_kind": ["individual"], "signer": ["agent"]}},
    {"key": "agent_id", "type": "text", "label_ar": "هوية الوكيل", "label_en": "Agent ID",
     "required": True, "norm": "digits", "re": "^[12][0-9]{9}$", "msg_ar": "١٠ أرقام تبدأ بـ1 أو 2",
     "show_if": {"client_kind": ["individual"], "signer": ["agent"]}},
    {"key": "wakala_no", "type": "text", "label_ar": "رقم الوكالة", "label_en": "POA number",
     "required": True, "norm": "digits",
     "show_if": {"client_kind": ["individual"], "signer": ["agent"]}},
    {"key": "wakala_date", "type": "date", "label_ar": "تاريخ الوكالة", "label_en": "POA date",
     "required": True, "show_if": {"client_kind": ["individual"], "signer": ["agent"]}},
    {"key": "mobile", "type": "text", "label_ar": "رقم الجوال", "label_en": "Mobile", "required": True,
     "norm": "mobile", "re": "^[+]9665[0-9]{8}$", "msg_ar": "مثل 05XXXXXXXX", "placeholder": "05XXXXXXXX",
     "inputmode": "tel"},
    {"key": "email", "type": "text", "label_ar": "البريد الإلكتروني (اختياري)", "label_en": "Email (optional)",
     "required": False, "norm": "trim", "re": "^[^@ ]+@[^@ ]+[.][^@ ]+$", "msg_ar": "صيغة البريد غير صحيحة",
     "inputmode": "email"},
    {"key": "nat_address", "type": "text", "label_ar": "العنوان الوطني المختصر (اختياري)",
     "label_en": "Short national address (optional)", "required": False, "norm": "upper",
     "re": "^[A-Z]{4}[0-9]{4}$", "msg_ar": "٤ حروف إنجليزية + ٤ أرقام، مثل RRRD2929",
     "placeholder": "ABCD1234"},
]

# ------------------------------------------------------------------ step 2 — الضريبة
VAT = [
    {"key": "vat_registered", "type": "choice", "label_ar": "مسجّل في ضريبة القيمة المضافة؟",
     "label_en": "VAT registered?", "required": True,
     "help_ar": "إذا كان المالك مسجّل، المنصة تصدر له الكشوفات الضريبية باسمه",
     "options": [opt("yes", "نعم", "Yes"), opt("no", "لا", "No")]},
    {"key": "vat_number", "type": "text", "label_ar": "الرقم الضريبي", "label_en": "VAT number",
     "required": True, "norm": "digits", "re": "^3[0-9]{13}3$",
     "msg_ar": "١٥ رقم، يبدأ بـ3 وينتهي بـ3", "show_if": {"vat_registered": ["yes"]}},
    # R1 (owner rule 28/09/2026): a VAT-registered owner ALWAYS operates on his own account, so the
    # platform issues his tax statements in his name. The question is hidden for him and validate()
    # forces "owner" whatever was sent — the server is the authority, never the browser.
    {"key": "account_model", "type": "choice",
     "label_ar": "الوحدات تشتغل على حساب مين في المنصات؟", "label_en": "Whose platform account?",
     "required": True, "show_if": {"vat_registered": ["no"]},
     "options": [opt("owner", "حساب المالك (المالك مضيف رئيسي، وعوجا مضيف مشارك)", "Owner's account"),
                 opt("ouja", "حساب عوجا", "Ouja's account")],
     "help_ar": "إذا كان المالك مسجّل في الضريبة، لازم تشتغل الوحدات على حسابه هو، والمنصة تصدر له الكشوفات الضريبية باسمه"},
    {"key": "account_model_note", "type": "note", "label_ar": "تشتغل على حساب المالك (مسجّل في الضريبة)",
     "label_en": "Runs on the owner's account (VAT-registered)", "show_if": {"vat_registered": ["yes"]}},
]

# ------------------------------------------------------------------ step 3 — الوحدات
FEES = ("850", "950", "1050", "1250")
UNITS = [
    {"key": "units_count", "type": "choice", "label_ar": "كم وحدة في هذا العقد؟",
     "label_en": "How many units?", "required": True, "default": "1",
     "options": [opt("1", "1"), opt("2", "2"), opt("3", "3"), opt("4", "4"), opt("5", "5"),
                 opt("more", "أكثر", "More")]},
    {"key": "units_more", "type": "number", "label_ar": "العدد", "label_en": "Number",
     "required": True, "min": 6, "max": 20, "step": 1, "show_if": {"units_count": ["more"]}},
    {"key": "same_property", "type": "choice", "label_ar": "هل الوحدات في نفس العقار؟",
     "label_en": "Same building?", "required": True,
     "options": [opt("yes", "نعم", "Yes"), opt("no", "لا", "No")]},
]

UNIT_FIELDS = [
    {"key": "city", "type": "choice", "label_ar": "المدينة", "label_en": "City", "required": True,
     "default": "riyadh",
     "options": [opt("riyadh", "الرياض", "Riyadh"), opt("jeddah", "جدة", "Jeddah"),
                 opt("dammam", "الدمام/الخبر", "Dammam/Khobar"), opt("other", "أخرى", "Other")]},
    {"key": "city_other", "type": "text", "label_ar": "اسم المدينة", "label_en": "City name",
     "required": True, "norm": "trim", "show_if": {"city": ["other"]}},
    {"key": "district", "type": "text", "label_ar": "الحي", "label_en": "District", "required": True,
     "norm": "trim"},
    {"key": "unit_type", "type": "choice", "label_ar": "النوع", "label_en": "Type", "required": True,
     "options": [opt("apartment", "شقة", "Apartment"), opt("studio", "استوديو", "Studio"),
                 opt("floor", "دور", "Floor"), opt("villa", "فيلا", "Villa"),
                 opt("townhouse", "تاون هاوس", "Townhouse")]},
    {"key": "bedrooms", "type": "choice", "label_ar": "الغرف", "label_en": "Bedrooms", "required": True,
     "options": [opt("0", "استوديو", "Studio"), opt("1", "1"), opt("2", "2"), opt("3", "3"),
                 opt("4", "4"), opt("5", "5+")]},
    {"key": "deed_no", "type": "text", "label_ar": "رقم الصك", "label_en": "Deed number",
     "required": True, "norm": "digits"},
    {"key": "licence_status", "type": "choice", "label_ar": "ترخيص وحدة الضيافة الخاصة",
     "label_en": "Private-hospitality licence", "required": True,
     "options": [opt("issued", "صادر", "Issued"), opt("pending", "قيد الإصدار", "Pending"),
                 opt("not_applied", "لم يُقدَّم بعد", "Not applied yet")]},
    {"key": "licence_no", "type": "text", "label_ar": "رقم الترخيص", "label_en": "Licence number",
     "required": True, "norm": "upper", "re": "^[A-Z0-9/-]{3,30}$",
     "msg_ar": "حروف إنجليزية وأرقام و - أو / (من ٣ إلى ٣٠)", "show_if": {"licence_status": ["issued"]}},
    {"key": "licence_expiry", "type": "date", "label_ar": "تاريخ انتهاء الترخيص",
     "label_en": "Licence expiry", "required": True, "show_if": {"licence_status": ["issued"]}},
    {"key": "monthly_fee", "type": "choice", "label_ar": "رسوم التشغيل الشهرية",
     "label_en": "Monthly operating fee", "required": True, "default": "1050",
     "options": [opt("850", "850"), opt("950", "950"), opt("1050", "1,050"), opt("1250", "1,250"),
                 opt("other", "مبلغ آخر", "Other amount")]},
    {"key": "monthly_fee_other", "type": "number", "label_ar": "المبلغ (ريال)", "label_en": "Amount (SAR)",
     "required": True, "min": 300, "max": 5000, "step": 1, "show_if": {"monthly_fee": ["other"]}},
    {"key": "min_price", "type": "number", "label_ar": "الحد الأدنى لسعر الليلة (ريال)",
     "label_en": "Minimum nightly price (SAR)", "required": True, "min": 1, "max": 5000, "step": 1,
     "unset_ok": True, "placeholder": "مثل: 450 — أو اكتب غير محدد"},
    {"key": "blocked", "type": "choice", "label_ar": "أيام الحجب", "label_en": "Blocked days",
     "required": True, "default": "none",
     "options": [opt("none", "لا يوجد", "None"), opt("set", "تحديد", "Specify")]},
    {"key": "blocked_text", "type": "text", "label_ar": "الأيام المحجوبة", "label_en": "Which days",
     "required": True, "norm": "trim", "placeholder": "مثل: 1–10 ذو الحجة سنوياً",
     "show_if": {"blocked": ["set"]}},
    {"key": "delivery_date", "type": "date", "label_ar": "تاريخ تسليم الوحدة",
     "label_en": "Handover date", "required": True},
    {"key": "listing_id", "type": "picker", "label_ar": "ربط بشقة في Hostaway (اختياري — داخلي)",
     "label_en": "Link to a Hostaway listing (optional, internal)", "required": False},
]

# ------------------------------------------------------------------ step 4 — العقار والتشغيل
PROPERTY = [
    {"key": "jamiya", "type": "choice", "label_ar": "جمعية الملاك", "label_en": "Owners' association",
     "required": True,
     "options": [opt("none", "لا توجد جمعية ملاك مسجلة في منصة ملاك", "No association registered"),
                 opt("ok", "توجد، ونظامها لا يمنع التأجير اليومي", "Exists, allows daily rental"),
                 opt("unknown", "غير معروف", "Unknown")]},
    {"key": "furnishing", "type": "choice", "label_ar": "حالة التأثيث", "label_en": "Furnishing",
     "required": True,
     "options": [opt("ready", "مؤثثة وجاهزة", "Furnished"), opt("partial", "تحتاج استكمال", "Partly"),
                 opt("none", "غير مؤثثة", "Unfurnished")]},
    {"key": "airbnb_account", "type": "choice", "label_ar": "حساب Airbnb", "label_en": "Airbnb account",
     "required": True, "show_if": {"account_model": ["owner"]},
     "options": [opt("owner_has", "للمالك حساب باسمه", "Owner has one"),
                 opt("we_create", "ننشئه معه", "We create it together")]},
]

# ------------------------------------------------------------------ step 5 — الشروط
TERMS = [
    {"key": "op_pct", "type": "choice", "label_ar": "نسبة التشغيل", "label_en": "Operating share",
     "required": True, "default": "23",
     "options": [opt("20", "20%"), opt("22", "22%"), opt("23", "23%"), opt("25", "25%"),
                 opt("other", "أخرى", "Other")]},
    {"key": "op_pct_other", "type": "number", "label_ar": "النسبة %", "label_en": "Share %",
     "required": True, "min": 10, "max": 40, "step": 0.5, "show_if": {"op_pct": ["other"]}},
    {"key": "send_via", "type": "choice", "label_ar": "طريقة الإرسال", "label_en": "Send by",
     "required": True, "default": "whatsapp",
     "options": [opt("whatsapp", "واتساب", "WhatsApp"), opt("copy", "نسخ الرابط فقط", "Copy link only")]},
    {"key": "internal_note", "type": "textarea", "label_ar": "ملاحظة داخلية (اختياري — ما تنطبع)",
     "label_en": "Internal note (optional, never printed)", "required": False, "norm": "trim"},
]

STEPS = [
    {"id": "client", "label_ar": "العميل", "label_en": "Client", "fields": CLIENT},
    {"id": "vat", "label_ar": "الضريبة", "label_en": "VAT", "fields": VAT},
    {"id": "units", "label_ar": "الوحدات", "label_en": "Units", "fields": UNITS, "unit_fields": UNIT_FIELDS},
    {"id": "property", "label_ar": "العقار والتشغيل", "label_en": "Property", "fields": PROPERTY},
    {"id": "terms", "label_ar": "الشروط", "label_en": "Terms", "fields": TERMS},
    {"id": "review", "label_ar": "مراجعة", "label_en": "Review", "fields": []},
]

MAX_UNITS = 20
SAME_PROPERTY_CAP = 3

# Rule texts — one source for the server refusals, the tab cards and the tests.
MANY_SAME_BLOCK = ("اللائحة تسمح بـ3 تراخيص كحد أقصى للمرخَّص له في العقار المشترك الواحد (المادة 4/2) — "
                   "قسّم الوحدات على أكثر من مرخَّص له أو أكثر من عقد")
COMPANY_REASON = "عقود الشركات تحتاج نموذج معتمد من المكتب — ترخيص وحدة الضيافة الخاصة يصدر لشخص طبيعي فقط"
OUJA_REASON = "حساب عوجا يحتاج نموذج عقد ثاني معتمد من المكتب — احفظه كمسودة"
MODEL_MISSING_REASON = "حدّد الوحدات تشتغل على حساب مين — بعدها يتحدد نموذج العقد"
COMPANY_CARD = ("ترخيص وحدة الضيافة الخاصة يصدر لشخص طبيعي فقط (تعريف المرخَّص له في اللائحة). نقدر نحفظ "
                "العقد كمسودة، لكن ما يطلع له رابط توقيع إلا بعد اعتماد نموذج الشركات من المكتب")
UNROUTED_PREVIEW = "معاينة فقط — هذا النوع من العقود يحتاج نموذج معتمد"
WE_CREATE_TASK = "إنشاء حساب المالك وإضافة عوجا مضيف مشارك قبل التشغيل"

CITY_AR = {o["v"]: o["ar"] for o in UNIT_FIELDS[0]["options"]}
UNIT_TYPE_AR = {o["v"]: o["ar"] for o in UNIT_FIELDS[3]["options"]}
ID_KEYS = ("id_number", "agent_id", "cr_number")       # never stored whole in the DB


def schema():
    return {"steps": STEPS, "max_units": MAX_UNITS, "same_property_cap": SAME_PROPERTY_CAP,
            "texts": {"many_same": MANY_SAME_BLOCK, "company_card": COMPANY_CARD, "ouja": OUJA_REASON,
                      "we_create": WE_CREATE_TASK}}


# ------------------------------------------------------------------ normalisation

def normalize(kind, v):
    if v is None:
        return ""
    s = str(v).translate(DIGITS).strip()
    if kind == "digits":
        return re.sub(r"[\s-]", "", s)
    if kind == "mobile":
        s = re.sub(r"[\s()-]", "", s)
        if s.startswith("00"):
            s = "+" + s[2:]
        if re.fullmatch(r"05[0-9]{8}", s):
            return "+966" + s[1:]
        if re.fullmatch(r"5[0-9]{8}", s):
            return "+966" + s
        if re.fullmatch(r"9665[0-9]{8}", s):
            return "+" + s
        return s
    if kind == "upper":
        return re.sub(r"\s", "", s).upper()
    return re.sub(r"[ \t]+", " ", s)


def unit_count(a):
    c = str(a.get("units_count") or "")
    if c == "more":
        try:
            return int(float(a.get("units_more")))
        except (TypeError, ValueError):
            return 0
    try:
        return int(c)
    except ValueError:
        return 0


def cond(name, a):
    if name == "many_same":
        return str(a.get("same_property")) == "yes" and unit_count(a) > SAME_PROPERTY_CAP
    return True


def visible(field, a):
    for k, vals in (field.get("show_if") or {}).items():
        if str(a.get(k) if a.get(k) is not None else "") not in vals:
            return False
    if field.get("cond") and not cond(field["cond"], a):
        return False
    return True


def _blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "") or v is False


def _check_field(f, raw, a, today):
    """-> (clean_value, error_ar or None)."""
    t = f["type"]
    if t == "note":
        return None, None
    if t == "check":
        ok = raw in (True, 1, "1", "true", "on", "yes")
        if f.get("required") and not ok:
            return False, "لازم تأكيد «%s»" % f["label_ar"]
        return ok, None
    if f.get("unset_ok") and str(raw if raw is not None else "").strip() in UNSET_WORDS:
        return UNSET_AR, None
    if t == "number" and isinstance(raw, (int, float)) and not isinstance(raw, bool):
        v = raw
    else:
        v = normalize(f.get("norm") or ("digits" if t == "number" else "trim"), raw)
    if _blank(v):
        if f.get("default") is not None and t == "choice":
            v = f["default"]
        elif f.get("required"):
            return "", "مطلوب"
        else:
            return "", None
    if t == "choice":
        if str(v) not in [o["v"] for o in f["options"]]:
            return "", "اختر من الخيارات"
        return str(v), None
    if t == "number":
        try:
            n = float(str(v).translate(DIGITS))
        except ValueError:
            return "", "رقم فقط"
        if n < f.get("min", n) or n > f.get("max", n):
            return "", "بين %s و %s" % (_fmt(f["min"]), _fmt(f["max"]))
        step = f.get("step") or 0
        if step and abs(round(n / step) * step - n) > 1e-9:
            return "", "بخطوات %s" % _fmt(step)
        return (int(n) if float(n).is_integer() else n), None
    if t == "date":
        try:
            d = datetime.date.fromisoformat(str(v)[:10])
        except ValueError:
            return "", "تاريخ غير صحيح"
        if f.get("not_past") and today and d < today:
            return "", f.get("msg_ar") or "التاريخ في الماضي"
        return d.isoformat(), None
    if t == "picker":
        try:
            return int(v), None
        except (TypeError, ValueError):
            return "", None
    s = str(v)
    pat = f.get("re")
    msg = f.get("msg_ar")
    if f.get("re_by"):
        sel = str(a.get(f["re_by"]["field"]) or "")
        pat = f["re_by"]["map"].get(sel)
        msg = (f.get("msg_by") or {}).get(sel) or msg
    if pat and not re.fullmatch(pat, s):
        return s, msg or "الصيغة غير صحيحة"
    if f.get("min_words") and len(s.split()) < f["min_words"]:
        return s, msg or "ناقص"
    return s, None


def _fmt(n):
    return ("%g" % n)


def validate(answers, today=None):
    """-> (clean answers, {key: Arabic error}). Hidden fields are dropped; unit errors are keyed
    'units.<i>.<key>'. Never raises on junk input."""
    a = dict(answers or {}) if isinstance(answers, dict) else {}
    vat_yes = normalize("trim", a.get("vat_registered")) == "yes"
    if vat_yes:
        a["account_model"] = "owner"          # R1: decided here, whatever the browser sent
    clean, errors = {}, {}
    for step in STEPS:
        for f in step["fields"]:
            if not visible(f, dict(a, **clean)):
                continue
            if f["type"] == "note":
                continue
            v, err = _check_field(f, a.get(f["key"]), dict(a, **clean), today)
            clean[f["key"]] = v
            if err:
                errors[f["key"]] = err
    if vat_yes:
        clean["account_model"] = "owner"
        errors.pop("account_model", None)
    n = unit_count(clean)
    if n < 1 or n > MAX_UNITS:
        errors.setdefault("units_count", "عدد الوحدات غير صحيح")
        n = 0
    raw_units = a.get("units") if isinstance(a.get("units"), list) else []
    units = []
    for i in range(n):
        u = raw_units[i] if i < len(raw_units) and isinstance(raw_units[i], dict) else {}
        cu = {}
        for f in UNIT_FIELDS:
            if not visible(f, dict(u, **cu)):
                continue
            v, err = _check_field(f, u.get(f["key"]), dict(u, **cu), today)
            cu[f["key"]] = v
            if err:
                errors["units.%d.%s" % (i, f["key"])] = err
        cu["label"] = "A%d" % (i + 1)
        units.append(cu)
    clean["units"] = units
    return clean, errors


def send_blockers(clean):
    """Answers that may be SAVED but can never be SENT to a client."""
    from . import engine                      # local: engine imports this module at load
    out = []
    _name, why = engine.template_for(clean)
    if why:
        out.append(why)
    if cond("many_same", clean):
        out.append(MANY_SAME_BLOCK)           # R3: المادة 4(2) is a block, not a tick
    if clean.get("jamiya") == "unknown":
        out.append("لازم نتأكد من جمعية الملاك قبل إرسال العقد")
    return out


def warnings(clean):
    w = []
    for u in clean.get("units") or []:
        if u.get("licence_status") in ("pending", "not_applied"):
            w.append("الوحدة %s: الترخيص %s — لا يبدأ التشغيل قبل صدوره"
                     % (u.get("label"), "قيد الإصدار" if u["licence_status"] == "pending" else "لم يُقدَّم بعد"))
    if clean.get("jamiya") == "unknown":
        w.append("جمعية الملاك غير معروفة — ما ينرسل العقد قبل التأكد")
    return w


def op_pct_value(clean):
    v = clean.get("op_pct")
    if v == "other":
        v = clean.get("op_pct_other")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def fee_value(u):
    v = u.get("monthly_fee")
    if v == "other":
        v = u.get("monthly_fee_other")
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
