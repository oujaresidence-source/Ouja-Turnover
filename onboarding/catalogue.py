# -*- coding: utf-8 -*-
"""
onboarding.catalogue — the 7-stage account-management process, as data.

Build spec §5. A module-level constant, never a table: the catalogue is code, so a task that
changes shape ships with a deploy and a diff, not with a silent row edit. `key` is STABLE —
onb_tasks carries UNIQUE(project_id, catalogue_key) and the seeder is INSERT OR IGNORE, so
re-seeding an existing project can never duplicate or overwrite a human's resolution.

owner_role legend — am = account manager (judgment work), coordinator = repeatable operational
work, ceo = escalation, external = Baytonia / photographer / ops.

owner_role IS A LABEL, NEVER A RULE (build spec R7). It renders as a chip so the account manager
can see which steps are normally his own judgment; it NEVER restricts who may be assigned. There
is deliberately NO `delegable` field here and no route may consult owner_role when assigning —
the only assignment rule is that the person is on the project.
"""

STAGES = [
    ("lead",       "١ — وصول العميل"),
    ("discovery",  "٢ — الاستكشاف"),
    ("terms",      "٣ — الاستراتيجية والشروط والعقد"),
    ("furnishing", "٤ — التأثيث والتجهيز"),
    ("license",    "٥ — متطلبات التشغيل والرخصة"),
    ("photoshoot", "٦ — التصوير الاحترافي"),
    ("handover",   "٧ — التسليم لفريق العمليات"),
    ("ongoing",    "مستمر — غير مرتبط بوحدة"),
]

STAGE_ORDER = [s[0] for s in STAGES]
STAGE_LABEL = dict(STAGES)

# Stages whose tasks belong to a UNIT. `ongoing` is company work and is never seeded onto a
# project — it is shown on the page as a separate read-only panel.
UNIT_STAGES = [s for s in STAGE_ORDER if s != "ongoing"]

OWNER_ROLES = ("am", "coordinator", "ceo", "external")
OWNER_ROLE_AR = {
    "am": "مدير الحسابات",
    "coordinator": "المنسق",
    "ceo": "الرئيس التنفيذي",
    "external": "طرف خارجي",
}

# (key, stage, seq, title_ar, owner_role, gate)
CATALOGUE = [
    ("s1.1", "lead", 1, "متابعة كل القنوات يوميًا: واتساب، التواصل، الموقع، النموذج", "coordinator", 0),
    ("s1.2", "lead", 2, "أول رد خلال نفس يوم العمل", "coordinator", 1),
    ("s1.3", "lead", 3, "تسجيل الفرصة: الاسم، التواصل، القناة، التاريخ، وصف مبدئي للوحدة", "coordinator", 1),
    ("s1.4", "lead", 4, "تحديد نوع العميل", "coordinator", 1),
    ("s1.5", "lead", 5, "مشترٍ محتمل: شرح الحدود وعرض الاستشارة والاتفاق على الرسوم", "am", 0),
    ("s1.6", "lead", 6, "مستأجر: طلب عقد الإيجار وفحص بند التأجير من الباطن", "coordinator", 0),
    ("s1.7", "lead", 7, "مراجعة بند التأجير من الباطن وقرار المتابعة أو الاعتذار", "am", 1),
    ("s1.8", "lead", 8, "حجز مكالمة الاستكشاف أو الزيارة الأولى", "coordinator", 1),
    ("s2.1", "discovery", 1, "إرسال أو استعراض قائمة أسئلة الوحدة", "coordinator", 1),
    ("s2.2", "discovery", 2, "تسجيل الموقع والحي والمساحة وعدد الغرف", "coordinator", 1),
    ("s2.3", "discovery", 3, "تسجيل طبيعة الوحدة والمرافق: مسبح، حوش، سينما", "coordinator", 1),
    ("s2.4", "discovery", 4, "طلب صور وفيديو مبدئية من العميل", "coordinator", 1),
    ("s2.5", "discovery", 5, "فحص أنظمة البرج أو المجمع تجاه التأجير القصير", "coordinator", 1),
    ("s2.6", "discovery", 6, "الزيارة الميدانية الأولى وتقرير صور مختصر", "am", 1),
    ("s2.7", "discovery", 7, "تصنيف جودة الأثاث ومدى ملاءمته للضيوف", "am", 1),
    ("s2.8", "discovery", 8, "تقدير احتياج الترميم أو التعديل", "am", 0),
    ("s2.9", "discovery", 9, "تحديد ميزانية التأثيث والانفتاح على التأثيث مع عوجا ودورة التجديد", "am", 0),
    ("s2.10", "discovery", 10, "قرار: نكمل أو ننسحب — حسب المعايير الأربعة", "am", 1),
    ("s2.11", "discovery", 11, "وحدة على حافة المعايير: التصعيد مع توصية", "ceo", 0),
    ("s3.1", "terms", 1, "اختيار استراتيجية التأجير", "am", 1),
    ("s3.2", "terms", 2, "تقدير الإيراد ومقارنته بأفضل عرض سنوي وطرح هدف الـ30٪", "am", 1),
    ("s3.3", "terms", 3, "طرح النسبة واشتراك النظافة وشرح ما يغطيه كل بند", "am", 1),
    ("s3.4", "terms", 4, "إدارة التفاوض", "am", 0),
    ("s3.5", "terms", 5, "نسبة أقل من القياسي: تجهيز المبرر والتصعيد", "ceo", 0),
    ("s3.6", "terms", 6, "الرد على أسئلة بنود العقد", "am", 0),
    ("s3.7", "terms", 7, "تعديلات تمسّ جوهر الاتفاق: التصعيد قبل أي وعد", "ceo", 0),
    ("s3.8", "terms", 8, "إصدار العقد وإرساله للتوقيع ومتابعته", "coordinator", 1),
    ("s3.9", "terms", 9, "أرشفة العقد الموقّع وتسجيل الشروط المتفق عليها", "coordinator", 1),
    ("s3.10", "terms", 10, "فتح ملف الوحدة: صور، مستندات، تكاليف، مراسلات", "coordinator", 1),
    ("s4.1", "furnishing", 1, "إرسال بيانات الوحدة والمقاسات والميزانية لبيتونيا", "coordinator", 0),
    ("s4.2", "furnishing", 2, "إنتاج العرض وعروض الأسعار", "external", 0),
    ("s4.3", "furnishing", 3, "مراجعة اكتمال العرض قبل عرضه على العميل", "coordinator", 0),
    ("s4.4", "furnishing", 4, "عرضه على العميل بندًا بندًا", "am", 0),
    ("s4.5", "furnishing", 5, "جمع وتصنيف ملاحظات العميل: مقبول مقابل يحتاج بديل", "coordinator", 0),
    ("s4.6", "furnishing", 6, "تسعير البدائل من مصادر عوجا مع هامش 10٪", "am", 0),
    ("s4.7", "furnishing", 7, "تأكيد الخطة والميزانية النهائية مع العميل كتابيًا", "am", 0),
    ("s4.8", "furnishing", 8, "بناء جدول التسليم والتركيب ومتابعة الموردين أسبوعيًا", "coordinator", 0),
    ("s4.9", "furnishing", 9, "متابعة أعمال الدهان والكهرباء والستائر واللوحات", "coordinator", 0),
    ("s4.10", "furnishing", 10, "استلام الأصناف والتحقق مقابل الخطة المعتمدة وتسجيل النواقص", "coordinator", 0),
    ("s4.11", "furnishing", 11, "وحدة يؤثثها العميل: الفحص مقابل معيار عوجا وطلب التعديلات", "am", 0),
    ("s4.12", "furnishing", 12, "تسجيل التكاليف والدفعات لكل بند", "coordinator", 0),
    ("s4.13", "furnishing", 13, "متابعة مشروع التجهيز في «تجهيز الشقق»", "coordinator", 0),
    ("s5.1", "license", 1, "شراء المراتب حسب المواصفة", "coordinator", 1),
    ("s5.2", "license", 2, "شراء وتركيب واختبار الأجهزة الإلكترونية", "coordinator", 1),
    ("s5.3", "license", 3, "تركيب معدات السلامة وتصويرها", "coordinator", 1),
    ("s5.4", "license", 4, "تجميع مستندات الرخصة من العميل", "coordinator", 1),
    ("s5.5", "license", 5, "تقديم طلب رخصة وزارة السياحة", "coordinator", 1),
    ("s5.6", "license", 6, "متابعة الطلب وإغلاق أي نواقص", "coordinator", 1),
    ("s5.7", "license", 7, "تسجيل رقم الرخصة وتاريخ الانتهاء مع تذكير التجديد", "coordinator", 1),
    ("s6.1", "photoshoot", 1, "تشغيل قائمة الجاهزية قبل الحجز", "coordinator", 1),
    ("s6.2", "photoshoot", 2, "طلب تنظيف عميق", "coordinator", 1),
    ("s6.3", "photoshoot", 3, "حجز المصور وتنسيق الدخول", "coordinator", 1),
    ("s6.4", "photoshoot", 4, "تصوير الوحدة", "external", 1),
    ("s6.5", "photoshoot", 5, "الإشراف على التنسيق والتغطية أثناء التصوير", "am", 0),
    ("s6.6", "photoshoot", 6, "مراجعة الصور واعتمادها أو طلب إعادة", "am", 1),
    ("s6.7", "photoshoot", 7, "أرشفة الصور بتسمية موحّدة", "coordinator", 1),
    ("s7.1", "handover", 1, "تجهيز ملف التسليم", "coordinator", 1),
    ("s7.2", "handover", 2, "تسليم المفاتيح والدخول والواي فاي وقواعد المنزل وتفضيلات العميل", "coordinator", 1),
    ("s7.3", "handover", 3, "اجتماع تسليم قصير مع العمليات يشمل الوعود المفتوحة", "am", 1),
    ("s7.4", "handover", 4, "بناء الإعلانات ونشرها: الوصف، التسعير، التقويم", "external", 0),
    ("s7.5", "handover", 5, "مراجعة الإعلانات المنشورة مقابل ما وُعد به العميل", "am", 0),
    ("s7.6", "handover", 6, "إبلاغ العميل ببدء التشغيل وشكل التقارير المتوقعة", "am", 0),
    ("s7.7", "handover", 7, "ما بعد التسليم: الأداء، تجديد الأثاث، تجديد العقد والرخصة", "am", 0),
    ("o.1", "ongoing", 1, "تحديث متتبّع الفرص أسبوعيًا وإغلاق ما لم يتحرك", "coordinator", 0),
    ("o.2", "ongoing", 2, "متابعة العملاء المؤجلين وغير المتجاوبين", "coordinator", 0),
    ("o.3", "ongoing", 3, "مراجعة النسب وأسعار النظافة وترتيبات الشركاء عند تغيّرها", "am", 0),
    ("o.4", "ongoing", 4, "صيانة قائمة الموردين والأسعار المرجعية للبدائل", "am", 0),
    ("o.5", "ongoing", 5, "تدريب الموظفين الجدد مرحلة بمرحلة قبل إسناد وحدة كاملة", "am", 0),
]

# ---- conditional auto-resolution, build spec §5 "Seeding rules" ----------------------------
# Each entry: catalogue key -> (predicate over the project dict, Arabic reason).
# The seeder applies these ONLY to tasks that are still `open`, so a human resolution is never
# reopened or overwritten when the project's shape changes later.

REASON_NOT_TENANT = "العميل مالك، مو مستأجر"
REASON_NOT_PROSPECT = "العميل مو مشترٍ محتمل"
REASON_ARRIVED_FURNISHED = "الوحدة وصلت مفروشة وجاهزة"
REASON_NO_PMO = "ما فيه مشروع تجهيز مرتبط"

_FURNISHING_AUTO_NA = ["s4.%d" % i for i in range(1, 13)]      # s4.1 .. s4.12 — NOT s4.13


def auto_na_for(project):
    """{catalogue_key: reason} for every task this project's shape makes inapplicable.

    Pure: takes a plain project dict, returns a plain dict. The caller decides what to do with
    it, and only ever applies it to tasks still sitting at `open`.
    """
    out = {}
    ctype = (project or {}).get("client_type") or ""
    if ctype != "tenant":
        out["s1.6"] = REASON_NOT_TENANT
        out["s1.7"] = REASON_NOT_TENANT
    if ctype != "prospect":
        out["s1.5"] = REASON_NOT_PROSPECT
    if ((project or {}).get("furnish_state") or "") == "furnished":
        for k in _FURNISHING_AUTO_NA:
            out[k] = REASON_ARRIVED_FURNISHED
    if not (project or {}).get("pmo_project_id"):
        out["s4.13"] = REASON_NO_PMO
    return out


def rows_for_seed():
    """The unit tasks, in catalogue order. `ongoing` is company work — never seeded."""
    return [r for r in CATALOGUE if r[1] != "ongoing"]


def ongoing_rows():
    return [r for r in CATALOGUE if r[1] == "ongoing"]


def by_key(key):
    for r in CATALOGUE:
        if r[0] == key:
            return r
    return None
