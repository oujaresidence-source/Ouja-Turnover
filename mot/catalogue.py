# -*- coding: utf-8 -*-
"""
mot.catalogue — the Ministry of Tourism unit standards, as CODE.

A regulator's standard is the kind of thing that must never rewrite the past: a round
inspected in September against 61 components must still read as 61 components next year,
even after the ministry adds a criterion. So this file is a module-level constant with a
CATALOGUE_VERSION, and every round freezes the version and the denominator it was taken
under. Keys are stable forever — never renumbered, never reused. Add; never edit in place.

Format (mirrors onboarding/catalogue.py):
    (key, section, criterion_no, criterion_ar, label_ar, kind, default_billed_to, unit_hint)

kind:
    product     a thing you buy                    -> the owner quote, priced x qty
    works       a contractor / technician          -> a maintenance ticket; its own group in the quote
    document    paper, sticker, board, procedure   -> onboarding license-stage tasks (s5.8-s5.10)
    structural  cannot be fixed by purchase        -> BLOCKS the unit; never a quote line

unit_hint drives the default quantity: per_unit=1, per_bedroom, per_bed, per_bathroom.
description_ar is deliberately EMPTY until the official ministry wording arrives from
Faisal — a paraphrased standard in a document that goes to the ministry is worse than a blank.
"""

CATALOGUE_VERSION = "2026-09c"

KINDS = ("product", "works", "document", "structural")
BILLED = ("ouja", "owner")
HINTS = ("per_unit", "per_bedroom", "per_bed", "per_bathroom")

SECTIONS = [
    ("s1", "المبنى والوصول"),
    ("s2", "الوحدة العامة"),
    ("s3", "الراحة والتجهيزات"),
    ("s4", "غرفة النوم والاستديو"),
    ("s5", "دورة المياه"),
    ("s6", "المطبخ"),
    ("s7", "السلامة والاستدامة"),
    ("s8", "معايير المسبح"),
]
SECTION_LABEL = dict(SECTIONS)
POOL_SECTION = "s8"

# (key, section, criterion_no, criterion_ar, label_ar, kind, default_billed_to, unit_hint)
CATALOGUE = [
    # --- s1 المبنى والوصول (1-4)
    ("c01.suitability", "s1", 1, "ملاءمة العقار", "ملاءمة العقار للنشاط", "structural", "owner", "per_unit"),
    ("c02.lighting", "s1", 2, "الإضاءة", "إنارة المداخل والممرات", "works", "owner", "per_unit"),
    ("c03.elevator", "s1", 3, "المصعد", "المصعد", "structural", "owner", "per_unit"),
    ("c04.price_board", "s1", 4, "قائمة الأسعار", "لوحة قائمة الأسعار المعروضة", "product", "ouja", "per_unit"),
    # --- s2 الوحدة العامة (5-9)
    ("c05.condition", "s2", 5, "حالة الوحدة", "حالة الوحدة العامة", "works", "owner", "per_unit"),
    ("c06.rules_board", "s2", 6, "الإرشادات العامة", "لوحة الإرشادات العامة", "product", "ouja", "per_unit"),
    ("c07.smart_lock", "s2", 7, "الدخول والأمان", "قفل ذكي / وسيلة دخول آمنة", "product", "owner", "per_unit"),
    ("c08.broom", "s2", 8, "أدوات التنظيف", "مكنسة ومماسح", "product", "owner", "per_unit"),
    ("c08.detergents", "s2", 8, "أدوات التنظيف", "مواد ومنظفات", "product", "ouja", "per_unit"),
    ("c08.gloves", "s2", 8, "أدوات التنظيف", "قفازات تنظيف", "product", "ouja", "per_unit"),
    ("c09.bin", "s2", 9, "سلال المهملات", "سلة مهملات", "product", "owner", "per_bedroom"),
    # --- s3 الراحة والتجهيزات (10-19)
    ("c10.iron", "s3", 10, "الكي", "مكواة وطاولة كي", "product", "owner", "per_unit"),
    ("c11.qr_saudi", "s3", 11, "QR روح السعودية", "ملصق QR «روح السعودية»", "document", "ouja", "per_unit"),
    ("c12.prayer_rug", "s3", 12, "سجادة الصلاة", "سجادة صلاة", "product", "owner", "per_unit"),
    ("c12.qibla", "s3", 12, "سجادة الصلاة", "علامة اتجاه القبلة على السقف", "product", "ouja", "per_unit"),
    ("c13.wifi", "s3", 13, "الإنترنت", "راوتر / اشتراك واي فاي", "product", "owner", "per_unit"),
    ("c14.door_cam", "s3", 14, "عدسة/كاميرا الباب", "عدسة أو كاميرا باب", "product", "owner", "per_unit"),
    ("c15.bedroom_seat", "s3", 15, "جلسة غرفة النوم", "كرسي / جلسة غرفة النوم", "product", "owner", "per_bedroom"),
    ("c16.tv", "s3", 16, "التلفزيون", "تلفزيون", "product", "owner", "per_unit"),
    ("c17.kettle", "s3", 17, "القهوة والشاي", "غلاية كهربائية", "product", "owner", "per_unit"),
    ("c17.cups", "s3", 17, "القهوة والشاي", "أكواب وفناجين", "product", "owner", "per_unit"),
    ("c17.water", "s3", 17, "القهوة والشاي", "مياه شرب معبأة", "product", "ouja", "per_unit"),
    ("c18.dishes", "s3", 18, "أواني الطعام", "صحون وأطباق تقديم", "product", "owner", "per_unit"),
    ("c18.cutlery", "s3", 18, "أواني الطعام", "أدوات مائدة (ملاعق · شوك · سكاكين)", "product", "owner", "per_unit"),
    ("c19.living_vent", "s3", 19, "تهوية غرفة المعيشة", "تهوية غرفة المعيشة", "works", "owner", "per_unit"),
    # --- s4 غرفة النوم والاستديو (20-25)
    ("c20.room_size", "s4", 20, "مساحة الغرفة/الاستديو", "مساحة الغرفة أو الاستديو", "structural", "owner", "per_unit"),
    ("c21.mattress", "s4", 21, "الأسرة والمفارش", "مراتب", "product", "owner", "per_bed"),
    ("c21.pillows", "s4", 21, "الأسرة والمفارش", "وسائد", "product", "owner", "per_bed"),
    ("c21.linen", "s4", 21, "الأسرة والمفارش", "مفارش وأغطية", "product", "owner", "per_bed"),
    ("c21.protector", "s4", 21, "الأسرة والمفارش", "غطاء عازل للمرتبة", "product", "owner", "per_bed"),
    ("c22.nightstand", "s4", 22, "طاولة بجانب السرير", "طاولة جانبية", "product", "owner", "per_bed"),
    ("c23.wardrobe", "s4", 23, "دولاب الملابس", "خزانة / دولاب", "product", "owner", "per_bedroom"),
    ("c23.shelves", "s4", 23, "دولاب الملابس", "رفوف داخلية", "product", "owner", "per_unit"),
    ("c23.mirror", "s4", 23, "دولاب الملابس", "مرآة الدولاب", "product", "owner", "per_unit"),
    ("c23.hangers", "s4", 23, "دولاب الملابس", "علاقات ملابس (٦ كحد أدنى)", "product", "ouja", "per_unit"),
    ("c24.blackout", "s4", 24, "الستائر والتعتيم", "ستائر تعتيم", "product", "owner", "per_bedroom"),
    ("c25.master_vent", "s4", 25, "تهوية غرفة النوم الرئيسية", "تهوية غرفة النوم الرئيسية", "works", "owner", "per_unit"),
    # --- s5 دورة المياه (26-33)
    ("c26.bathroom", "s5", 26, "دورة المياه", "دورة المياه", "structural", "owner", "per_unit"),
    ("c27.toilet", "s5", 27, "المرحاض والشطاف", "مرحاض وشطاف", "works", "owner", "per_unit"),
    ("c28.shower", "s5", 28, "منطقة الاستحمام", "حوض استحمام / دش", "works", "owner", "per_unit"),
    ("c28.glass_door", "s5", 28, "منطقة الاستحمام", "باب زجاجي", "product", "owner", "per_unit"),
    ("c28.antislip", "s5", 28, "منطقة الاستحمام", "أرضية مانعة للانزلاق", "product", "owner", "per_unit"),
    ("c29.sink_mirror", "s5", 29, "حوض الحمام والمرآة", "مغسلة ومرآة", "product", "owner", "per_bathroom"),
    ("c30.hand_soap", "s5", 30, "مستلزمات النظافة الشخصية", "صابون اليدين", "product", "ouja", "per_bathroom"),
    ("c30.body_soap", "s5", 30, "مستلزمات النظافة الشخصية", "صابون الجسم", "product", "ouja", "per_bathroom"),
    ("c30.shampoo", "s5", 30, "مستلزمات النظافة الشخصية", "شامبو", "product", "ouja", "per_bathroom"),
    ("c31.towel_rack", "s5", 31, "حامل المناشف", "حامل مناشف", "product", "owner", "per_bathroom"),
    ("c32.bath_mat", "s5", 32, "سجادة الحمام", "سجادة حمام", "product", "owner", "per_bathroom"),
    ("c33.bath_vent", "s5", 33, "تهوية الحمام", "تهوية الحمام", "works", "owner", "per_unit"),
    # --- s6 المطبخ (34-36)
    ("c34.microwave", "s6", 34, "الميكروويف", "ميكروويف", "product", "owner", "per_unit"),
    ("c35.cookware", "s6", 35, "أدوات الطبخ", "قدور ومقالي", "product", "owner", "per_unit"),
    ("c35.prep_tools", "s6", 35, "أدوات الطبخ", "أدوات تحضير الطبخ (سكاكين · لوح تقطيع · مصفاة)", "product", "owner", "per_unit"),
    ("c35.dinner_set", "s6", 35, "أدوات الطبخ", "طقم مائدة لشخصين (صحون · ملاعق · شوك · سكاكين)", "product", "owner", "per_bedroom"),
    ("c36.hood", "s6", 36, "شفاط المطبخ", "شفاط المطبخ", "works", "owner", "per_unit"),
    # --- s7 السلامة والاستدامة (37-41)
    ("c37.extinguisher", "s7", 37, "تجهيزات السلامة", "طفاية حريق", "product", "owner", "per_unit"),
    ("c37.fire_blanket", "s7", 37, "تجهيزات السلامة", "غطاء إخماد الحريق", "product", "owner", "per_unit"),
    ("c37.smoke_detector", "s7", 37, "تجهيزات السلامة", "كاشف دخان", "product", "owner", "per_unit"),
    ("c37.first_aid", "s7", 37, "تجهيزات السلامة", "حقيبة إسعافات أولية", "product", "owner", "per_unit"),
    ("c38.electrical", "s7", 38, "السلامة الكهربائية", "السلامة الكهربائية", "works", "owner", "per_unit"),
    ("c39.evac_plan", "s7", 39, "خطة الإخلاء", "لوحة خطة الإخلاء", "document", "ouja", "per_unit"),
    ("c40.eco_stickers", "s7", 40, "الاستدامة", "ملصقات ترشيد الاستهلاك", "document", "ouja", "per_unit"),
    ("c41.hospitality", "s7", 41, "الأطعمة والمشروبات", "ركن ضيافة (ماء · قهوة · تمر)", "product", "ouja", "per_unit"),
    # --- s8 معايير المسبح (42-47) — counted ONLY when the unit has a pool
    ("c42.pool_ladder", "s8", 42, "سلالم المسبح", "سلالم المسبح", "works", "owner", "per_unit"),
    ("c43.pool_rails", "s8", 43, "مقابض المسبح", "مقابض المسبح", "works", "owner", "per_unit"),
    ("c44.pool_floor", "s8", 44, "أرضية المسبح", "أرضية مانعة للانزلاق حول المسبح", "works", "owner", "per_unit"),
    ("c45.pool_fence", "s8", 45, "حواجز حماية المسبح", "حواجز حماية", "works", "owner", "per_unit"),
    ("c46.pool_rescue", "s8", 46, "وسائل الإنقاذ", "طوق نجاة وعصا إنقاذ", "product", "owner", "per_unit"),
    ("c47.pool_electric", "s8", 47, "كهرباء وإنارة المسبح", "كهرباء وإنارة المسبح", "works", "owner", "per_unit"),
]

# Components RETIRED from new rounds (key -> the version that retired them). A key is never
# deleted or reused: a round taken under an older version still renders and scores with it.
RETIRED = {
    # owner ruling 2026-09-08: everything kitchen lives under criterion 35; criterion 18 is
    # reported as «مغطّى ضمن المعيار ٣٥» (MERGED_INTO) so the ministry still sees all 47.
    "c18.dishes": "2026-09c",
    "c18.cutlery": "2026-09c",
}

# criterion -> the criterion whose components cover it. Counted, reported, never inspected twice.
MERGED_INTO = {18: 35}

# Official ministry wording per criterion number — as sent by Faisal on 2026-09-08. Rendered
# verbatim on the inspector page, the manager page and the evidence file. Never paraphrased.
DESCRIPTION_AR = {
    1: "أن يكون العقار مناسبًا لاستقبال الضيوف، وألا يكون مثل غرفة سائق أو مبنى سكن عمالة.",
    2: "توفير إضاءة كافية وموزعة في المدخل الرئيسي والممرات والسلالم، تعمل طوال فترة الإقامة ومطابقة لاشتراطات السلامة الكهربائية.",
    3: "توفير مصعد يعمل بكفاءة إذا كان المبنى من 3 طوابق أو أكثر، مطابق لاشتراطات السلامة ويحمل شهادة فحص سارية.",
    4: "توفير قائمة أسعار باللغتين العربية والإنجليزية للخدمات الإضافية المدفوعة داخل الوحدة، إن وجدت.",
    5: "الأرضيات والجدران بتشطيب مناسب وكامل وبحالة جيدة، وخالية من التشققات والكسور والتقشر والرطوبة والعفن.",
    6: "إبراز إرشادات استخدام الوحدة في مكان ظاهر، وتشمل المرافق، النفايات، السلوكيات المحظورة، أرقام الطوارئ وخدمة العملاء.",
    7: "نظام دخول آمن لكل وحدة يتيح للضيف إغلاقها وفتحها بإحكام ويضمن الخصوصية.",
    8: "توفير أدوات ومستلزمات التنظيف اللازمة للوحدة بجميع مكوناتها، كاملة وصالحة للاستخدام وبعيدة عن متناول الأطفال.",
    9: "توفير سلال مهملات مناسبة في غرفة المعيشة وجميع الغرف، مزودة بأكياس مع توفير عدد كافٍ من الأكياس البديلة.",
    10: "توفير مكواة كهربائية وطاولة كي أو كواية بخار لكل وحدة، تعمل بكفاءة وبحالة جيدة.",
    11: "وضع رمز الاستجابة السريعة QR الخاص ببرنامج «روح السعودية» في مكان ظاهر وواضح داخل كل وحدة.",
    12: "توفير سجادة صلاة نظيفة وبحالة جيدة لكل وحدة، مع توضيح اتجاه القبلة بعلامة ظاهرة على السقف.",
    13: "خدمة Wi-Fi بتغطية كاملة داخل الوحدة وبسرعة لا تقل عن 5 ميجابت/ثانية، مع تزويد الضيف ببيانات الدخول.",
    14: "توفير عدسة باب أو كاميرا باب لكل وحدة تتيح للضيف رؤية الخارج قبل فتح الباب، وتكون الرؤية واضحة وبحالة جيدة.",
    15: "توفير أريكة أو كرسيين بذراعين يتسعان لشخصين لكل غرفة نوم أو استديو، بحالة جيدة ونظيفة وسليمة القماش والحشوة.",
    16: "تلفزيون ذكي لكل وحدة بحجم لا يقل عن 32 بوصة، يعمل بكفاءة ومتصل بالإنترنت ويتيح تطبيقات البث.",
    17: "توفير أدوات تحضير القهوة والشاي لكل وحدة، وتشمل الغلاية والأكواب والمستلزمات الأساسية، بالإضافة إلى مياه شرب معبأة كافية.",
    18: "توفير أواني طعام نظيفة وكاملة تكفي عدد الضيوف المصرح به، مع أدوات مائدة سليمة وصالحة للاستخدام.",
    19: "توفير نظام تهوية فعال يجدد الهواء ويصرف الرطوبة والروائح ويمنع تراكمها.",
    20: "مساحة غرفة النوم لا تقل عن 12 م²، ومساحة الاستديو لا تقل عن 24 م²، محسوبة من صافي المساحة الداخلية.",
    21: "أسرة مزودة بمراتب ووسائد وأغطية نظيفة وغطاء عازل للمرتبة، ويتم استبدالها بين الضيوف. الحد الأدنى لمقاس السرير المزدوج 1.60 × 1.90 م والفردي 0.90 × 1.90 م.",
    22: "توفير مساحة تخزين بجانب كل سرير، مثل طاولة جانبية أو ما يماثلها، بحالة جيدة ونظيفة.",
    23: "خزانة أو دولاب ملابس لكل غرفة مزود برفوف ومرآة وما لا يقل عن 6 علاقات ملابس، بحالة جيدة ونظيفة.",
    24: "توفير ستائر أو وسيلة تعتيم لجميع نوافذ الوحدة، تغطيها بالكامل وتحجب الرؤية والضوء الخارجي بفعالية.",
    25: "نظام تهوية فعال لتجديد الهواء وتصريف الرطوبة والروائح ومنع تراكمها، مع نظافة وسلامة منافذ التهوية.",
    26: "وجود دورة مياه مستقلة داخل الوحدة مجهزة بالأدوات الصحية الأساسية ونظيفة وصالحة للاستخدام.",
    27: "مقعد مرحاض بغطاء وشطاف يدوي لكل دورة مياه رئيسية، يعملان بكفاءة وبحالة جيدة ونظيفة.",
    28: "منطقة استحمام أو حوض استحمام مزود بدش وباب زجاجي، صالح للاستخدام، مع أرضية مانعة للانزلاق.",
    29: "حوض لغسل اليدين لكل دورة مياه مزود بصنابير مياه ساخنة وباردة ومرآة، بحالة جيدة وصالح للاستخدام.",
    30: "توفير صابون اليدين وصابون الجسم والشامبو كحد أدنى، وتكون جديدة أو معبأة بالكامل ونظيفة.",
    31: "توفير حامل مناشف لكل دورة مياه، مثبت بإحكام وبحالة جيدة ونظيف.",
    32: "توفير Bath Rug لكل دورة مياه، مانعة للانزلاق ونظيفة وخالية من البقع والروائح، ويتم استبدالها بين الضيوف.",
    33: "نظام تهوية فعال في كل دورة مياه يضمن تصريف الروائح والرطوبة إلى خارج المبنى.",
    34: "توفير جهاز ميكروويف يعمل بكفاءة في المطبخ أو منطقة التحضير ويكون متاحًا للضيف طوال إقامته.",
    35: "توفير طقم متكامل من أدوات الطبخ، يشمل أواني الطبخ وأدوات التحضير والتقديم، مع طقم مائدة لعدد شخصين لكل غرفة نوم.",
    36: "توفير مروحة شفط تعمل بكفاءة في المطبخ أو منطقة التحضير لتصريف الروائح والأبخرة، وتكون سليمة ونظيفة.",
    37: "توفير تجهيزات سلامة سارية الصلاحية تشمل: طفاية حريق، غطاء إخماد الحريق، كاشف دخان، وأدوات الإسعافات الأولية.",
    38: "جميع الأدوات والتجهيزات الكهربائية داخل الوحدة بحالة جيدة وسليمة ومطابقة لاشتراطات السلامة الكهربائية المعتمدة.",
    39: "وضع تعليمات السلامة وخطة الإخلاء في مكان واضح خلف باب مدخل الوحدة، وتشمل مسارات الإخلاء، المخارج، نقاط التجمع وأرقام الطوارئ.",
    40: "توفير ملصقات إرشادية لترشيد الاستهلاك والاستدامة داخل الوحدة، وتشمل المياه والكهرباء وإعادة التدوير وفصل النفايات.",
    41: "في حال توفيرها للضيف، يجب أن تكون سارية الصلاحية وصالحة للاستهلاك الآدمي ومحفوظة بطريقة سليمة ومطابقة لاشتراطات السلامة الغذائية.",
    42: "تكون ممتدة وواصلة إلى قاع المسبح بشكل آمن، ومزودة بدرابزين ثابت على كلا الجانبين مصنوع من مواد مقاومة للصدأ والانزلاق.",
    43: "توفير مقابض يدوية ممتدة على كافة جوانب المسبح، مثبتة على ارتفاع 15 سم فوق مستوى الماء ومن مواد مقاومة للصدأ والانزلاق.",
    44: "تكون أرضية المسبح والمناطق المحيطة نظيفة وخالية من العوائق وغير مسببة للانزلاق.",
    45: "توفير حواجز أمان تمنع دخول الأطفال دون إشراف، مزودة ببوابة ذاتية الإغلاق ومفتاح على ارتفاع بعيد عن متناول الأطفال.",
    46: "توفير وسائل إنقاذ ومعدات طفو فوق الماء، مثل أطواق النجاة، بالقرب من المسبح وفي مكان ظاهر وسهل الوصول.",
    47: "التمديدات الكهربائية ووحدات الإضاءة في المسبح ومحيطه تكون معزولة بطريقة آمنة ومطابقة لاشتراطات المسابح المعتمدة.",
}

# The one component another subsystem answers for us: an active row in wifi_subs.
WIFI_KEY = "c13.wifi"

# document-kind components -> the onboarding license-stage task that fixes them.
DOCUMENT_TASK_KEY = {
    "c11.qr_saudi": "s5.8",
    "c39.evac_plan": "s5.9",
    "c40.eco_stickers": "s5.10",
}

FIELDS = ("key", "section", "criterion_no", "criterion_ar", "label_ar", "kind",
          "billed_to", "unit_hint")


def as_dict(row):
    d = dict(zip(FIELDS, row))
    d["section_ar"] = SECTION_LABEL.get(d["section"], d["section"])
    d["description_ar"] = DESCRIPTION_AR.get(d["criterion_no"], "")
    d["pool_only"] = d["section"] == POOL_SECTION
    return d


def _live(key, version):
    """A retired key stays live for rounds taken under a version older than its retirement."""
    ret = RETIRED.get(key)
    if not ret:
        return True
    return bool(version) and str(version) < ret


def components(has_pool, version=None):
    """The components a round is measured against. Pool section only when has_pool; a
    retired component only when `version` (the round's frozen catalogue_version) predates
    its retirement."""
    return [as_dict(r) for r in CATALOGUE
            if (has_pool or r[1] != POOL_SECTION) and _live(r[0], version)]


def by_key(key):
    for r in CATALOGUE:
        if r[0] == key:
            return as_dict(r)
    return None


def criteria_count(has_pool, version=None):
    """Criteria the ministry counts: every criterion with a live component PLUS every merged
    criterion whose target is live (18 is covered by 35, still one of the 47)."""
    live = {c["criterion_no"] for c in components(has_pool, version)}
    return len(live | {k for k, v in MERGED_INTO.items() if v in live})
