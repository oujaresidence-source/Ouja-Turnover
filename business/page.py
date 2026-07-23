# -*- coding: utf-8 -*-
"""
business.page — server-rendered /business (EN) and /business/ar (AR, full RTL).

Everything is rendered in Python from the assembled snapshot blob (business.render):
no client-side Hostaway calls, real SSR for SEO + screen readers, charts as inline
SVG with text equivalents. The template shell is a NORMAL triple-quoted string with
ZERO backslashes; data is injected via .replace() placeholders (never .format / f-string,
so CSS/JS braces stay literal). The tiny interaction script is backslash-free by design.

Voice (superprompt §7): an operator talking to a professional. Calm, precise, numbers
carry the argument. EN and AR are each written natively — AR is clean confident MSA,
not a translation and not the Najdi guest voice.
"""
import html
import json

from . import render

# --------------------------------------------------------------------------- #
# copy — both languages written natively (§6, §7)
# --------------------------------------------------------------------------- #
COPY = {
    "en": {
        "dir": "ltr", "lang": "en", "alt_href": "/business/ar", "alt_label": "العربية",
        "brand": "Ouja Residence",
        "title": "Ouja Residence — operating record",
        "meta_desc": "Ouja Residence operates short-stay residences in Riyadh. Two years, {stays} stays, {rating} out of 5. The verified operating record.",
        "hero_line": "Two years. {stays} stays. {rating} out of 5.",
        "hero_sub": "Ouja Residence operates short-stay residences across Riyadh: 100+ branded units, one in-house team, one operating system built for them.",
        "strip": ["{stays} stays", "{nights} nights", "{turnovers} turnovers", "{guests} guests", "{reviews} reviews", "{rating}★"],
        "as_of_prefix": "as of", "source": "source", "method": "method",
        "src_hostaway": "Hostaway · Airbnb channel", "src_internal": "internal",
        "hero_eyebrow": "Operating record · Riyadh · since 2024",
        "ledger_labels": ["stays delivered", "guest nights", "turnovers prepared",
                          "unique guests", "published reviews", "average rating"],
        "src_line": "as of {date} · Airbnb channel · refreshed nightly",
        "kick_what": "The company", "kick_record": "Quality, measured",
        "kick_reviews": "The evidence", "kick_os": "The machine behind it",
        "src_reviews": "Airbnb · verified stays",
        "router_title": "What brings you here?",
        "router": [
            ("platforms", "You run a booking platform", "Supply, quality, pipeline"),
            ("corporate", "You need housing for your people", "Inventory, rates, invoicing"),
            ("suppliers", "You want to sell to or work with us", "Scale, procurement, contact"),
        ],
        "what_title": "What Ouja is",
        "what_body": [
            "Founded in 2024 in Riyadh, Ouja operates furnished short-stay residences under a single brand across managed compounds, from studios to three-bedroom apartments.",
            "Owners keep their asset and share the revenue. Ouja takes the rest: furnishing, photography, listing, pricing, guest communication, cleaning, inspection, maintenance, and monthly reporting, all run by one in-house team on one platform we built ourselves.",
            "That platform is the difference. Every unit is priced by date, prepared to a checklist, inspected before each arrival, and reported on down to the last riyal. Nothing is left to a spreadsheet or a WhatsApp group.",
            "Ouja is the old name of Diriyah, the winding valley of Wadi Hanifa where Riyadh began.",
        ],
        "record_title": "The record",
        "dist_title": "Rating distribution",
        "dist_perfect": "rated 10 / 10", "dist_rest": "9 / 10 or below",
        "dist_foot": "{avg} average across {n} published reviews, low scores included",
        "cat_title": "Category sub-scores (out of 10)",
        "cat_note": "Communication and check-in score highest — the two categories most correlated with guest-support escalations.",
        "growth_title": "Growth against rating",
        "growth_cap": "We grew 12× in eight quarters. The rating did not move.",
        "growth_axis_reviews": "Published reviews per quarter", "growth_axis_rating": "Average rating",
        "repeat_line": "{pct} of our stays are guests who came back.",
        "repeat_note": "Repeat rate is the one metric that cannot be bought with marketing spend.",
        "reviews_title": "Reviews as evidence",
        "reviews_intro": "Every card below is a real, published Airbnb review from a verified stay, shown verbatim. These are {shown} of {total}.",
        "verified_badge": "Airbnb · verified stay",
        "filter_all": "All",
        "show_all": "Show all {total} reviews",
        "themes": {"cleanliness": "Cleanliness", "checkin": "Check-in", "design": "Design",
                   "communication": "Communication", "location": "Location", "value": "Value",
                   "accuracy": "Accuracy", "service": "Service", "quiet": "Quiet",
                   "space": "Spacious", "family": "Family", "cinema": "Cinema",
                   "returning_guest": "Returning guest"},
        "os_title": "The operating system",
        "os_intro": "Most operators run on a spreadsheet and a phone. Ouja runs on infrastructure we built ourselves, and a standard we hold on every single unit.",
        "os_items": [
            ("Inspection before every arrival", "Cleaning is a mix of in-house crews and vetted third parties, but the standard is not. Ouja's own team inspects each unit against a checklist before the guest walks in, every time, whoever cleaned it.", "This is why cleanliness holds at 9.57 across 100+ listings, not who holds the mop."),
            ("A trusted PMS, fully integrated", "Every unit lives on a professional property-management system with full API integration: one calendar, one guest inbox, real-time channel sync, and no double-bookings across Airbnb and direct.", "One source of truth for every reservation, price, and message."),
            ("Our own platform, ~49,000 lines", "Purpose-built and running the business daily: turnover scheduling, staff assignment that redistributes on the fly when someone is off, dynamic pricing with a written reason for every date, append-only audit logs, vendor ticketing, expense reconciliation, and automated owner reporting.", "Predictable quality at scale, and reporting an owner can actually check."),
            ("Musaed, the in-house assistant", "An AI guest assistant that handles pre-booking questions in Arabic and English around the clock, and hands off to a person the moment it should.", "Faster answers, fewer escalations, nothing lost overnight."),
            ("Reach that arrives before the booking", "100M+ views and 70,000+ followers across TikTok and Snapchat, aimed at Saudi travellers in Arabic.", "A new listing opens to a warm audience, not a cold start."),
            ("Ouja Elite", "A small, invite-only tier for our most valued guests, under 1% of everyone who stays.", "Not a mass loyalty scheme; a short list, looked after closely."),
        ],
        "compliance_title": "Standing",
        "compliance": [
            "A registered Saudi company",
            "VAT-registered operations",
            "A two-year operating track record",
        ],
        "tracks_title": "Tracks",
        "tracks": {
            "platforms": {
                "h": "Booking platforms",
                "angle": "Most operators ask platforms for demand. Ouja arrives with its own — 100M+ views and 70,000+ followers in the Saudi short-stay niche, reaching Saudi travellers in Arabic before they open a booking app.",
                "points": [
                    "New listings launch to a warm audience instead of a cold start",
                    "Content aimed at specific inventory, seasons, or campaigns",
                    "A growth pipeline: units live now, more contracted for the next 12 months",
                    "A quality profile that lowers support load: 9.77 communication, 9.74 check-in",
                    "One operator, one account, 100+ listings — one relationship instead of many",
                    "Event capacity: Riyadh Season, Formula 1, Expo 2030 build-up",
                ],
                "cta": "Talk to us about supply", "form": None,
            },
            "corporate": {
                "h": "Companies that need housing",
                "angle": "A hotel gives you a room. Ouja gives you a serviced residence with a kitchen, a living room, and an invoice your finance team accepts.",
                "points": [
                    "Inventory by district with a 1BR-to-3BR unit mix, near business districts",
                    "Multi-unit and long-stay allocation; monthly rates on request",
                    "VAT-compliant invoicing under a registered Saudi entity",
                    "One account contact, one reporting line, one point of escalation",
                    "Self-entry check-in at any hour — for arriving staff and shift workers",
                    "24/7 guest support in Arabic and English",
                ],
                "cta": "Request availability and rates", "form": "lead",
            },
            "owners": {
                "h": "Owners & developers",
                "angle": "We already do this for 100+ units. Here is the record, the model, and the reporting.",
                "points": [
                    "Revenue-share model (80/20), management agreements or master lease",
                    "Automated bilingual owner performance reporting",
                    "Dynamic pricing with per-date explainability, not guesswork",
                    "Furnishing, branding, photography, listing creation handled in-house",
                    "A two-year record: growing to 100+ listings without the rating dropping",
                ],
                "cta": "Bring us your building", "form": None,
            },
            "suppliers": {
                "h": "Vendors, suppliers & service providers",
                "angle": "This track exists to save both sides time. Most inbound pitches fail because they do not know the shape of the operation.",
                "points": [
                    "Scale: 100+ listings, ~14,000 turnovers, 11,307 guest nights",
                    "Recurring categories: insurance, laundry, furniture and FF&E, consumables, maintenance, fintech and payments, PropTech and software",
                    "What a first message needs: category, pricing model, minimum commitment, Saudi entity status, existing clients at similar scale",
                ],
                "cta": "Send a proposal", "form": "proposal",
            },
        },
        "form_company": "Company", "form_contact": "Contact name", "form_email": "Email",
        "form_phone": "Phone / WhatsApp", "form_dates": "Dates", "form_units": "Units needed",
        "form_city": "City", "form_category": "Category", "form_pricing": "Pricing model",
        "form_min": "Minimum commitment", "form_entity": "Saudi entity status",
        "form_clients": "Existing clients at similar scale", "form_message": "Message",
        "send_lead": "Request availability", "sent_lead": "Request sent",
        "send_proposal": "Send proposal", "sent_proposal": "Proposal sent",
        "form_err": "Please add a contact so we can reply.",
        "close_title": "Contact",
        "contact_cr": "Commercial Registration", "contact_addr": "Riyadh, Saudi Arabia",
        "wa": "WhatsApp", "email_l": "Email", "book": "Book a stay",
        "footer_sync": "Figures refresh nightly from our property management system. Last sync: {sync}.",
        "skip": "Skip to content",
    },
    "ar": {
        "dir": "rtl", "lang": "ar", "alt_href": "/business", "alt_label": "English",
        "brand": "عوجا ريزيدنس",
        "title": "عوجا ريزيدنس — السجل التشغيلي",
        "meta_desc": "عوجا ريزيدنس تُشغّل وحدات الإقامة القصيرة في الرياض. سنتان، {stays} إقامة، {rating} من ٥.",
        "hero_line": "سنتان. {stays} إقامة. {rating} من ٥.",
        "hero_sub": "عوجا ريزيدنس تُشغّل وحدات الإقامة القصيرة في الرياض: أكثر من ١٠٠ وحدة تحت علامة واحدة، وفريق داخلي واحد، ونظام تشغيل بنيناه لها.",
        "strip": ["{stays} إقامة", "{nights} ليلة", "{turnovers} تجهيز", "{guests} ضيف", "{reviews} تقييم", "{rating}★"],
        "as_of_prefix": "حتى", "source": "المصدر", "method": "الطريقة",
        "src_hostaway": "هوستاوي · قناة Airbnb", "src_internal": "داخلي",
        "hero_eyebrow": "السجل التشغيلي · الرياض · منذ ٢٠٢٤",
        "ledger_labels": ["إقامة مُنجزة", "ليلة ضيف", "تجهيز مُنفّذ",
                          "ضيف فريد", "تقييم منشور", "متوسط التقييم"],
        "src_line": "حتى {date} · قناة Airbnb · تتحدّث ليليًا",
        "kick_what": "الشركة", "kick_record": "الجودة، بالقياس",
        "kick_reviews": "الدليل", "kick_os": "الآلة خلف ذلك",
        "src_reviews": "Airbnb · إقامات موثّقة",
        "router_title": "ما الذي يهمّك هنا؟",
        "router": [
            ("platforms", "تُدير منصة حجوزات", "العرض، الجودة، خط النمو"),
            ("corporate", "تحتاج سكنًا لفريقك", "الوحدات، الأسعار، الفوترة"),
            ("suppliers", "ترغب بالبيع لنا أو العمل معنا", "الحجم، المشتريات، التواصل"),
        ],
        "what_title": "ما هي عوجا",
        "what_body": [
            "تأسّست عوجا في الرياض عام ٢٠٢٤، وتُشغّل وحدات إقامة قصيرة مفروشة تحت علامة واحدة عبر مجمّعات تديرها، من الاستوديو إلى شقق بثلاث غرف.",
            "المالك يحتفظ بأصله ويشاركنا الإيراد، ونتولّى نحن الباقي: التأثيث والتصوير والإعلان والتسعير والتواصل مع الضيوف والتنظيف والفحص والصيانة والتقارير الشهرية، يديرها فريق داخلي واحد على منصة بنيناها بأنفسنا.",
            "هذه المنصة هي الفرق. كل وحدة تُسعَّر بحسب التاريخ، وتُجهَّز وفق قائمة تحقّق، وتُفحَص قبل كل وصول، ويُرفَع عنها تقرير حتى آخر ريال. لا شيء متروك لجدول أو مجموعة واتساب.",
            "«عوجا» هو الاسم القديم للدرعية، وادي حنيفة المتعرّج حيث بدأت الرياض.",
        ],
        "record_title": "السجل",
        "dist_title": "توزع التقييمات",
        "dist_perfect": "بتقييم ١٠ / ١٠", "dist_rest": "٩ / ١٠ أو أقل",
        "dist_foot": "متوسط {avg} عبر {n} تقييمًا منشورًا، والدرجات المنخفضة مشمولة",
        "cat_title": "التقييمات الفرعية (من ١٠)",
        "cat_note": "التواصل وتسجيل الدخول الأعلى — وهما أكثر فئتين ارتباطًا بتصعيد دعم الضيوف.",
        "growth_title": "النمو مقابل التقييم",
        "growth_cap": "نمونا ١٢ ضعفًا في ثمانية أرباع. التقييم لم يتحرّك.",
        "growth_axis_reviews": "التقييمات المنشورة لكل ربع", "growth_axis_rating": "متوسط التقييم",
        "repeat_line": "{pct} من إقاماتنا ضيوف عادوا.",
        "repeat_note": "معدل العودة هو المقياس الوحيد الذي لا يُشترى بإنفاق التسويق.",
        "reviews_title": "التقييمات كدليل",
        "reviews_intro": "كل بطاقة أدناه تقييم حقيقي منشور على Airbnb من إقامة موثّقة، منقول كما هو. هذه {shown} من {total}.",
        "verified_badge": "Airbnb · إقامة موثّقة",
        "filter_all": "الكل",
        "show_all": "عرض كل التقييمات ({total})",
        "themes": {"cleanliness": "النظافة", "checkin": "تسجيل الدخول", "design": "التصميم",
                   "communication": "التواصل", "location": "الموقع", "value": "القيمة",
                   "accuracy": "الدقة", "service": "الخدمة", "quiet": "الهدوء",
                   "space": "الاتساع", "family": "العائلة", "cinema": "سينما",
                   "returning_guest": "ضيف عائد"},
        "os_title": "نظام التشغيل",
        "os_intro": "معظم المُشغّلين يعملون بجدول وهاتف. عوجا تعمل ببنية بنيناها بأنفسنا، وبمعيار نلتزم به على كل وحدة دون استثناء.",
        "os_items": [
            ("فحص قبل كل وصول", "التنظيف مزيج من فرق داخلية وأخرى خارجية موثوقة، لكن المعيار واحد لا يتغير: فريق عوجا نفسه يفحص كل وحدة وفق قائمة تحقّق قبل دخول الضيف، في كل مرة، أيًّا كان من نظّفها.", "لهذا تبقى النظافة عند ٩٫٥٧ عبر أكثر من ١٠٠ وحدة، لا لمن يمسك الممسحة."),
            ("نظام إدارة موثوق ومتكامل", "كل وحدة على نظام إدارة أملاك احترافي بتكامل كامل عبر واجهة برمجية: تقويم واحد، صندوق رسائل واحد، مزامنة فورية للقنوات، وبلا حجوزات مزدوجة بين Airbnb والحجز المباشر.", "مصدر واحد للحقيقة لكل حجز وسعر ورسالة."),
            ("منصتنا الخاصة، نحو ٤٩ألف سطر", "مبنية لغرضها وتدير العمل يوميًا: جدولة التجهيز، توزيع المهام الذي يعيد التوزيع فورًا عند غياب أحد، تسعير ديناميكي بسبب مكتوب لكل تاريخ، سجلات تدقيق غير قابلة للتعديل، تذاكر موردين، تسوية مصروفات، وتقارير ملاك آلية.", "جودة ثابتة على نطاق واسع، وتقارير يستطيع المالك التحقق منها فعلًا."),
            ("مساعد، مساعدنا الداخلي", "مساعد ضيوف بالذكاء الاصطناعي يجيب على أسئلة ما قبل الحجز بالعربية والإنجليزية على مدار الساعة، ويحوّل لموظف فور أن يلزم.", "إجابات أسرع، تصعيد أقل، ولا شيء يضيع في الليل."),
            ("انتشار يسبق الحجز", "أكثر من ١٠٠ مليون مشاهدة وأكثر من ٧٠ألف متابع عبر تيك توك وسناب شات، موجّهة للمسافر السعودي بالعربية.", "الوحدة الجديدة تنطلق لجمهور جاهز، لا من الصفر."),
            ("عوجا إيليت", "فئة محدودة بالدعوة لأكثر ضيوفنا قيمة، أقل من ١٪ ممن يقيمون معنا.", "ليست برنامج ولاء جماهيري؛ قائمة قصيرة نعتني بها عن قرب."),
        ],
        "compliance_title": "المكانة",
        "compliance": [
            "شركة سعودية مُسجّلة",
            "منشأة مسجّلة في ضريبة القيمة المضافة",
            "سجل تشغيلي يمتد سنتين",
        ],
        "tracks_title": "المسارات",
        "tracks": {
            "platforms": {
                "h": "منصات الحجوزات",
                "angle": "معظم المُشغّلين يطلبون الطلب من المنصات. عوجا تأتي بطلبها الخاص — أكثر من ١٠٠ مليون مشاهدة وأكثر من ٧٠ألف متابع في قطاع الإقامة القصيرة السعودي، تصل للمسافر السعودي بالعربية قبل أن يفتح تطبيق حجز.",
                "points": [
                    "الوحدات الجديدة تنطلق لجمهور جاهز لا من الصفر",
                    "محتوى موجّه لوحدات أو مواسم أو حملات محددة",
                    "خط نمو: وحدات قائمة الآن، وأخرى متعاقد عليها للأشهر ال١٢ القادمة",
                    "ملف جودة يخفّض عبء الدعم: ٩٫٧٧ تواصل، ٩٫٧٤ تسجيل دخول",
                    "مُشغّل واحد، حساب واحد، أكثر من ١٠٠ وحدة — علاقة واحدة بدل الكثير",
                    "قدرة على الفعاليات: موسم الرياض، فورمولا ١، التحضير لإكسبو ٢٠٣٠",
                ],
                "cta": "تحدّث معنا عن العرض", "form": None,
            },
            "corporate": {
                "h": "الشركات التي تحتاج سكنًا",
                "angle": "الفندق يعطيك غرفة. عوجا تعطيك وحدة مخدومة بمطبخ وصالة وفاتورة يقبلها قسمك المالي.",
                "points": [
                    "وحدات حسب الحي بتنوّع من غرفة إلى ثلاث، قريبة من مراكز الأعمال",
                    "تخصيص متعدد الوحدات وإقامات طويلة؛ أسعار شهرية عند الطلب",
                    "فوترة مطابقة لضريبة القيمة المضافة تحت كيان سعودي مُسجّل",
                    "جهة اتصال واحدة، خط تقارير واحد، نقطة تصعيد واحدة",
                    "دخول ذاتي في أي ساعة — مناسب للموظفين والورديات",
                    "دعم ضيوف على مدار الساعة بالعربية والإنجليزية",
                ],
                "cta": "اطلب التوفر والأسعار", "form": "lead",
            },
            "owners": {
                "h": "الملاك والمطوّرون",
                "angle": "نفعل هذا فعلًا لأكثر من ١٠٠ وحدة. هذا هو السجل والنموذج والتقارير.",
                "points": [
                    "نموذج مشاركة في الإيراد (٨٠/٢٠)، اتفاقية إدارة أو إيجار رئيسي",
                    "تقارير أداء للملاك آلية ثنائية اللغة",
                    "تسعير ديناميكي قابل للتفسير لكل تاريخ، لا تخمين",
                    "تأثيث وعلامة وتصوير وإنشاء إعلانات داخليًا",
                    "سجل سنتين: النمو إلى أكثر من ١٠٠ وحدة دون أن ينخفض التقييم",
                ],
                "cta": "قدّم مبناك", "form": None,
            },
            "suppliers": {
                "h": "الموردون ومقدّمو الخدمات",
                "angle": "هذا المسار موجود لتوفير وقت الطرفين. معظم العروض تفشل لأنها لا تعرف شكل العملية.",
                "points": [
                    "الحجم: أكثر من ١٠٠ وحدة، نحو ١٤ألف عملية تجهيز، ١١٬٣٠٧ ليلة",
                    "فئات متكررة: تأمين، غسيل، أثاث، مستهلكات، صيانة، مدفوعات، تقنية عقارات وبرمجيات",
                    "ما يحتاجه أول تواصل: الفئة، نموذج التسعير، الحد الأدنى للالتزام، وضع الكيان السعودي، عملاء بحجم مماثل",
                ],
                "cta": "أرسل عرضًا", "form": "proposal",
            },
        },
        "form_company": "الشركة", "form_contact": "اسم جهة الاتصال", "form_email": "البريد",
        "form_phone": "الهاتف / واتساب", "form_dates": "التواريخ", "form_units": "عدد الوحدات",
        "form_city": "المدينة", "form_category": "الفئة", "form_pricing": "نموذج التسعير",
        "form_min": "الحد الأدنى للالتزام", "form_entity": "وضع الكيان السعودي",
        "form_clients": "عملاء بحجم مماثل", "form_message": "الرسالة",
        "send_lead": "اطلب التوفر", "sent_lead": "تم إرسال الطلب",
        "send_proposal": "أرسل العرض", "sent_proposal": "تم إرسال العرض",
        "form_err": "أضف وسيلة تواصل حتى نرد عليك.",
        "close_title": "التواصل",
        "contact_cr": "السجل التجاري", "contact_addr": "الرياض، السعودية",
        "wa": "واتساب", "email_l": "البريد", "book": "احجز إقامة",
        "footer_sync": "تتحدّث الأرقام ليليًا من نظام إدارة الأملاك. آخر مزامنة: {sync}.",
        "skip": "تخطّ إلى المحتوى",
    },
}


def _e(s):
    return html.escape(str(s), quote=True)


# --------------------------------------------------------------------------- #
# section builders
# --------------------------------------------------------------------------- #
def _count(raw, formatted, lang, dec=0, suffix=""):
    """A number that counts up from 0 on reveal. SSR renders the final value, so it
    stays correct with JS off; the client animates from 0 to `raw`."""
    return ('<span class="count num" data-to="%s" data-dec="%d" data-suffix="%s" '
            'data-lang="%s">%s</span>') % (raw, dec, _e(suffix), lang, _e(formatted))


def build_hero(t, m, lang, turnovers, as_of):
    stays_r = m.get("reservations_total", 0)
    rating_r = m.get("rating_avg_5", 0)
    stays = _count(stays_r, render.fmt_int(stays_r, lang), lang)
    rating = _count(rating_r, render.fmt_dec(rating_r, lang), lang, dec=2)
    line = t["hero_line"].replace("{stays}", stays).replace("{rating}", rating)

    # ledger: (raw target, SSR-formatted, decimals, suffix appended by the count-up)
    led_vals = [
        (stays_r, render.fmt_int(stays_r, lang), 0, ""),
        (m.get("guest_nights", 0), render.fmt_int(m.get("guest_nights", 0), lang), 0, ""),
        (14000, turnovers, 0, "+"),
        (m.get("unique_guests", 0), render.fmt_int(m.get("unique_guests", 0), lang), 0, ""),
        (m.get("reviews_published", 0), render.fmt_int(m.get("reviews_published", 0), lang), 0, ""),
        (rating_r, render.fmt_dec(rating_r, lang), 2, ""),
    ]
    labels = t["ledger_labels"]
    led = ""
    for i, (raw, fmt, dec, suf) in enumerate(led_vals):
        led += (
            '<div class="led"><div class="led-n num">%s</div>'
            '<div class="led-l">%s</div></div>'
        ) % (_count(raw, fmt, lang, dec=dec, suffix=suf), _e(labels[i]))
    src = t["src_line"].replace("{date}", render.localize_digits(as_of or "", lang))
    return (
        '<section class="hero" id="content">'
        '<p class="eyebrow mono">%s</p>'
        '<h1 class="hero-line">%s</h1>'
        '<p class="hero-sub">%s</p>'
        '<div class="ledger">%s</div>'
        '<p class="stamp" style="margin-top:16px">%s</p>'
        '</section>'
    ) % (_e(t["hero_eyebrow"]), line, _e(t["hero_sub"]), led, _e(src))


def build_router(t):
    cards = ""
    for tid, label, desc in t["router"]:
        cards += (
            '<a class="router-card" href="#%s" data-track="%s">'
            '<span class="rc-num mono">→</span>'
            '<span class="rc-label">%s</span>'
            '<span class="rc-desc">%s</span>'
            '<span class="rc-go" aria-hidden="true">→</span>'
            '</a>'
        ) % (tid, tid, _e(label), _e(desc))
    return (
        '<section class="router" aria-label="%s">'
        '<h2 class="router-title">%s</h2>'
        '<div class="router-grid">%s</div>'
        '</section>'
    ) % (_e(t["router_title"]), _e(t["router_title"]), cards)


def build_what(t):
    paras = t["what_body"]
    body = ""
    for i, p in enumerate(paras):
        cls = ' class="last"' if i == len(paras) - 1 else ""
        body += "<p%s>%s</p>" % (cls, _e(p))
    return (
        '<section class="block"><p class="kicker">%s</p>'
        '<h2 class="h2">%s</h2><div class="prose">%s</div></section>'
    ) % (_e(t["kick_what"]), _e(t["what_title"]), body)


# ---- charts (inline SVG, server-rendered, with text equivalents) ---------- #
def _svg_open(w, h, label):
    return ('<svg viewBox="0 0 %d %d" role="img" aria-label="%s" '
            'preserveAspectRatio="xMidYMid meet" class="chart">' % (w, h, _e(label)))


def build_distribution(t, m, lang):
    perfect = m.get("perfect_share", 0)
    rest = max(0.0, 1 - perfect)
    pct = render.fmt_pct(perfect, lang)
    dist = m.get("rating_distribution") or {}

    # If a full live distribution exists, draw every score honestly; otherwise the
    # honest two-segment split from perfect_share. Either way, big number up top.
    if len(dist) > 1:
        total = sum(dist.values()) or 1
        segs = []
        for score in range(10, 0, -1):
            c = dist.get(str(score), 0)
            if c:
                segs.append((c / total, "%s/10" % score, render.fmt_int(c, lang)))
    else:
        segs = [(perfect, t["dist_perfect"], pct),
                (rest, t["dist_rest"], render.fmt_pct(rest, lang))]

    seg_html = ""
    for i, (frac, lab, val) in enumerate(segs):
        seg_html += (
            '<span class="dist-seg dist-seg-%d" style="flex:%d 1 0" '
            'title="%s: %s"></span>'
        ) % (0 if i == 0 else 1, max(1, int(round(frac * 1000))), _e(lab), _e(val))

    legend = ""
    for i, (frac, lab, val) in enumerate(segs[:4]):
        legend += ('<li><span class="dot dot-%d"></span>%s <b>%s</b></li>'
                   % (0 if i == 0 else 1, _e(lab), _e(val)))

    avg = render.fmt_dec(m.get("rating_avg_5", 0), lang)
    nrev = render.fmt_int(m.get("reviews_published", 0), lang)
    alt = "%s %s · %s %s" % (t["dist_perfect"], pct, t["dist_rest"], render.fmt_pct(rest, lang))
    foot = t["dist_foot"].replace("{avg}", avg).replace("{n}", nrev)
    perfect_pct100 = round(perfect * 100, 1)
    big = _count(perfect_pct100, pct, lang, dec=1, suffix="%")
    return (
        '<div class="panel">'
        '<div class="panel-head"><h3>%s</h3><span class="src">%s</span></div>'
        '<span class="dist-big num">%s</span>'
        '<p class="dist-cap">%s</p>'
        '<div class="dist-bar" role="img" aria-label="%s">%s</div>'
        '<ul class="dist-legend">%s</ul>'
        '<p class="dist-foot">%s</p>'
        '</div>'
    ) % (_e(t["dist_title"]), _e(t["src_reviews"]), big, _e(t["dist_perfect"]),
         _e(alt), seg_html, legend, _e(foot))


def build_categories(t, m, lang):
    cats = m.get("category_avgs") or {}
    order = ["communication", "checkin", "accuracy", "location", "cleanliness", "value"]
    items = [(c, cats[c]) for c in order if c in cats]
    rows = ""
    for c, v in items:
        val = _count(v, render.fmt_dec(v, lang), lang, dec=2)
        rows += (
            '<div class="cat">'
            '<span class="cat-l">%s</span>'
            '<span class="cat-track"><span class="cat-fill" style="--v:%.3f"></span></span>'
            '<span class="cat-v num">%s</span>'
            '</div>'
        ) % (_e(t["themes"].get(c, c)), v / 10.0, val)
    return (
        '<div class="panel">'
        '<div class="panel-head"><h3>%s</h3><span class="src">%s</span></div>'
        '<div class="cats">%s</div>'
        '<p class="cat-note">%s</p>'
        '</div>'
    ) % (_e(t["cat_title"]), _e(t["src_reviews"]), rows, _e(t["cat_note"]))


def build_growth(t, m, lang):
    q = m.get("reviews_by_quarter") or []
    if not q:
        return ""
    counts = [row.get("count", 0) for row in q]
    maxc = max(counts) or 1
    W, H = 900, 320
    padL, padR, padT, padB = 20, 20, 34, 48
    plotW = W - padL - padR
    plotH = H - padT - padB
    n = len(q)
    slot = plotW / n
    bw = slot * 0.5
    def readout(row):
        return "%s · <b>%s</b> · <b>%s</b>★" % (
            render.localize_digits(row.get("q", ""), lang),
            render.fmt_int(row.get("count", 0), lang),
            render.fmt_dec(row.get("rating_avg_5") or 0, lang))

    bars, xlabels = "", ""
    for i, row in enumerate(q):
        c = row.get("count", 0)
        bh = (c / maxc) * plotH
        x = padL + i * slot + (slot - bw) / 2
        yb = padT + plotH - bh
        aria = "%s: %s reviews, rating %s" % (
            row.get("q", ""), render.fmt_int(c, lang),
            render.fmt_dec(row.get("rating_avg_5") or 0, lang))
        bars += ('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" class="g-bar" '
                 'tabindex="0" role="img" aria-label="%s" data-read="%s"></rect>') % (
            x, yb, bw, bh, _e(aria), _e(readout(row)))
        bars += '<text x="%.1f" y="%.1f" class="g-cnt" text-anchor="middle">%s</text>' % (
            x + bw / 2, yb - 8, _e(render.fmt_int(c, lang)))
        xlabels += '<text x="%.1f" y="%.1f" class="g-x" text-anchor="middle">%s</text>' % (
            padL + i * slot + slot / 2, H - padB + 20, _e(render.localize_digits(row.get("q", ""), lang)))
    # rating line, zoomed to 4.0-5.0 to show flatness honestly
    pts = []
    lo, hi = 4.0, 5.0
    for i, row in enumerate(q):
        r = row.get("rating_avg_5")
        if r is None:
            continue
        rr = min(hi, max(lo, r))
        y = padT + plotH - ((rr - lo) / (hi - lo)) * plotH
        pts.append((padL + i * slot + slot / 2, y))
    line = ""
    if len(pts) >= 2:
        d = "M " + " L ".join("%.1f %.1f" % p for p in pts)
        line = '<path d="%s" pathLength="1" class="g-line" fill="none"></path>' % d
        for px, py in pts:
            line += '<circle cx="%.1f" cy="%.1f" r="3.4" class="g-dot"></circle>' % (px, py)
    axis = ('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="g-axis"></line>'
            % (padL, padT + plotH, W - padR, padT + plotH))
    rlabel = '<text x="%d" y="%.1f" class="g-rlabel">%s 5.0</text>' % (
        W - padR, padT + 4, _e(t["growth_axis_rating"]))
    svg = _svg_open(W, H, t["growth_title"]) + axis + bars + line + rlabel + xlabels + "</svg>"
    first, last = q[0], q[-1]
    alt = "%s: %s → %s" % (
        t["growth_axis_reviews"],
        render.fmt_int(first.get("count", 0), lang),
        render.fmt_int(last.get("count", 0), lang))
    return (
        '<div class="growth">'
        '<div class="growth-top">'
        '<p class="growth-cap">%s</p>'
        '<div class="g-readout mono" aria-hidden="true">%s</div>'
        '</div>'
        '%s'
        '<p class="sr-only">%s</p></div>'
    ) % (_e(t["growth_cap"]), readout(last), svg, _e(alt))


def build_record(t, m, lang):
    rep_r = m.get("repeat_guest_share", 0)
    rep_big = _count(round(rep_r * 100, 1), render.fmt_pct(rep_r, lang), lang, dec=1, suffix="%")
    rep_line = t["repeat_line"].replace("{pct} ", "").replace("{pct}", "")
    return (
        '<section class="block record">'
        '<p class="kicker">%s</p><h2 class="h2">%s</h2>'
        '<div class="record-grid">%s%s</div>'
        '%s'
        '<div class="repeat"><div class="repeat-big num">%s</div>'
        '<p class="repeat-line">%s</p><p class="repeat-note">%s</p></div>'
        '</section>'
    ) % (
        _e(t["kick_record"]), _e(t["record_title"]),
        build_distribution(t, m, lang), build_categories(t, m, lang),
        build_growth(t, m, lang),
        rep_big, _e(rep_line), _e(t["repeat_note"]),
    )


def build_reviews(t, reviews, lang):
    total_published = 2633
    shown = render.fmt_int(len(reviews), lang)
    total = render.fmt_int(total_published, lang)
    intro = t["reviews_intro"].replace("{shown}", shown).replace("{total}", total)

    # theme chips — only themes that actually occur, in a sensible order, most-covered first
    present = set()
    for r in reviews:
        present.update(r.get("themes", []))
    preferred = ["cleanliness", "communication", "location", "design", "checkin",
                 "value", "returning_guest", "service", "quiet", "space", "family", "cinema"]
    theme_keys = [k for k in preferred if k in present and k in t["themes"]]
    chips = '<button class="tfilter on" data-theme="all" type="button">%s</button>' % _e(t["filter_all"])
    for k in theme_keys:
        chips += '<button class="tfilter" data-theme="%s" type="button">%s</button>' % (k, _e(t["themes"][k]))

    # featured first are the default-visible set; the rest load on demand
    ordered = sorted(reviews, key=lambda r: (not r.get("featured", False),))
    n_featured = sum(1 for r in reviews if r.get("featured"))
    initial = n_featured or 30
    cards = ""
    for i, r in enumerate(ordered):
        rlang = r.get("lang", "en")
        rdir = "rtl" if rlang == "ar" else "ltr"
        extra = " extra" if i >= initial else ""
        cards += (
            '<article class="review%s" data-themes="%s" lang="%s" dir="%s">'
            '<p class="r-text">%s</p>'
            '<div class="r-meta">'
            '<span class="r-name">%s</span>'
            '<span class="r-dot" aria-hidden="true">·</span>'
            '<span class="r-date">%s</span>'
            '<bdi class="r-listing">%s</bdi>'
            '<span class="r-badge">%s</span>'
            '</div></article>'
        ) % (
            extra, _e(" ".join(r.get("themes", []))), _e(rlang), rdir,
            _e(r.get("text", "")),
            _e(r.get("name", "")),
            _e(render.localize_digits(r.get("date", ""), lang)),
            _e(r.get("listing", "")),
            _e(t["verified_badge"]),
        )
    show_all = t["show_all"].replace("{total}", shown)
    more_btn = ""
    if len(ordered) > initial:
        more_btn = ('<div class="reviews-more"><button class="btn ghost" type="button" '
                    'data-show-all>%s</button></div>') % _e(show_all)
    return (
        '<section class="block reviews" id="reviews">'
        '<p class="kicker">%s</p><h2 class="h2">%s</h2>'
        '<p class="lead">%s</p>'
        '<div class="tfilters" role="group" aria-label="filter">%s</div>'
        '<div class="review-wall collapsed">%s</div>'
        '%s'
        '</section>'
    ) % (_e(t["kick_reviews"]), _e(t["reviews_title"]), _e(intro), chips, cards, more_btn)


def build_os(t):
    items = ""
    for name, what, means in t["os_items"]:
        items += (
            '<div class="os-item"><h3>%s</h3><p>%s</p><p class="means">%s</p></div>'
        ) % (_e(name), _e(what), _e(means))
    intro = '<p class="lead">%s</p>' % _e(t["os_intro"]) if t.get("os_intro") else ""
    return ('<section class="block"><p class="kicker">%s</p><h2 class="h2">%s</h2>'
            '%s<div class="os-grid">%s</div></section>') % (
        _e(t["kick_os"]), _e(t["os_title"]), intro, items)


def build_compliance(t, cr, lang):
    rows = ""
    for line in t["compliance"]:
        rows += '<li>%s</li>' % _e(line.replace("{cr}", render.localize_digits(cr, lang)))
    return '<section class="block"><h2>%s</h2><ul class="compliance">%s</ul></section>' % (
        _e(t["compliance_title"]), rows)


def _form_fields(t, kind):
    if kind == "lead":
        keys = ["form_company", "form_contact", "form_email", "form_phone",
                "form_dates", "form_units", "form_city", "form_message"]
        submit, sent = t["send_lead"], t["sent_lead"]
    else:
        keys = ["form_company", "form_contact", "form_email", "form_phone",
                "form_category", "form_pricing", "form_min", "form_entity",
                "form_clients", "form_message"]
        submit, sent = t["send_proposal"], t["sent_proposal"]
    fields = ""
    for k in keys:
        name = k.replace("form_", "")
        big = name in ("message", "clients")
        if big:
            fields += ('<label class="f-field f-wide"><span>%s</span>'
                       '<textarea name="%s" rows="3"></textarea></label>') % (_e(t[k]), name)
        else:
            typ = "email" if name == "email" else "text"
            fields += ('<label class="f-field"><span>%s</span>'
                       '<input type="%s" name="%s"></label>') % (_e(t[k]), typ, name)
    return fields, submit, sent


def build_tracks(t, cr, lang):
    out = '<section class="tracks" id="tracks"><h2 class="sr-only">%s</h2>' % _e(t["tracks_title"])
    for tid in ("platforms", "corporate", "suppliers"):  # owners track hidden for now
        tr = t["tracks"][tid]
        points = "".join("<li>%s</li>" % _e(p) for p in tr["points"])
        # Forms are hidden for now (owner request) — every track's CTA points to
        # the contact block. The form builder stays in place for when they return.
        cta_html = '<a class="btn" href="#close">%s</a>' % _e(tr["cta"])
        out += (
            '<article class="track" id="%s" data-track-panel="%s">'
            '<h3 class="track-h">%s</h3>'
            '<p class="track-angle">%s</p>'
            '<ul class="track-points">%s</ul>'
            '%s</article>'
        ) % (tid, tid, _e(tr["h"]), _e(tr["angle"]), points, cta_html)
    out += "</section>"
    return out


def build_close(t, cr, lang, links):
    return (
        '<section class="block close" id="close"><h2 class="h2">%s</h2>'
        '<div class="contact">'
        '<a class="btn" href="%s">%s</a>'
        '<a class="btn ghost" href="%s">%s</a>'
        '<a class="btn ghost" href="mailto:%s">%s</a>'
        '</div>'
        '<p class="contact-meta">%s</p>'
        '</section>'
    ) % (
        _e(t["close_title"]),
        _e(links["book"]), _e(t["book"]),
        _e(links["wa"]), _e(t["wa"]),
        _e(links["email"]), _e(t["email_l"]),
        _e(t["contact_addr"]),
    )


# --------------------------------------------------------------------------- #
# SEO / structured data
# --------------------------------------------------------------------------- #
def build_head_extra(t, m, lang, base, desc):
    jsonld = {
        "@context": "https://schema.org",
        "@type": ["Organization", "LocalBusiness"],
        "name": "Ouja Residence",
        "url": base + ("/business/ar" if lang == "ar" else "/business"),
        "areaServed": "Riyadh, Saudi Arabia",
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": m.get("rating_avg_5", 0),
            "bestRating": 5,
            "reviewCount": m.get("reviews_published", 0),
        },
    }
    og = (
        '<meta property="og:title" content="%s">'
        '<meta property="og:description" content="%s">'
        '<meta property="og:type" content="website">'
        '<meta property="og:locale" content="%s">'
    ) % (_e(t["title"]), _e(desc), "ar_SA" if lang == "ar" else "en_US")
    hreflang = (
        '<link rel="alternate" hreflang="en" href="%s/business">'
        '<link rel="alternate" hreflang="ar" href="%s/business/ar">'
        '<link rel="alternate" hreflang="x-default" href="%s/business">'
    ) % (base, base, base)
    return (og + hreflang +
            '<script type="application/ld+json">%s</script>'
            % json.dumps(jsonld, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# the shell — NORMAL triple-quoted string, ZERO backslashes, .replace() only
# --------------------------------------------------------------------------- #
SHELL = """<!doctype html>
<html lang="__LANG__" dir="__DIR__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<meta name="theme-color" content="#0E0D0B">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
__HEAD_EXTRA__
<style>
:root{
  --bg:#0E0D0B; --bg-2:#141210; --panel:#1A1611; --panel-2:#221C15; --panel-lift:#2A2318;
  --ivory:#F4EEE0; --ivory-2:#CDC4AF; --muted:#948B76; --faint:#5F5847;
  --gold:#CBA05A; --gold-2:#E7C983; --gold-deep:#8E6C31;
  --line:rgba(203,160,90,0.20); --line-2:rgba(244,238,224,0.09); --hair:rgba(244,238,224,0.06);
  --glow:0 0 40px rgba(203,160,90,0.22); --glow-soft:0 0 24px rgba(203,160,90,0.14);
  --ok:#82B07F; --bad:#C77B63;
  --mx:1140px; --rad:16px; --rad-s:11px;
  --e1:cubic-bezier(0.22,1,0.36,1); --e2:cubic-bezier(0.16,1,0.3,1);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ivory);
  font-family:"IBM Plex Sans Arabic",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:17px;line-height:1.6;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased;
  overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:
    radial-gradient(1100px 620px at 72% -6%, rgba(203,160,90,0.14), transparent 60%),
    radial-gradient(760px 520px at 8% 8%, rgba(203,160,90,0.06), transparent 55%),
    radial-gradient(1200px 900px at 50% 120%, rgba(203,160,90,0.05), transparent 60%)}
.grain{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.5;mix-blend-mode:overlay;
  background-image:radial-gradient(rgba(255,255,255,.02) 1px, transparent 1px);background-size:3px 3px}
main,header,footer{position:relative;z-index:1}
.wrap{max-width:var(--mx);margin:0 auto;padding:0 24px}
a{color:inherit;text-decoration:none}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1;letter-spacing:-0.02em}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.serif{font-family:"Fraunces","IBM Plex Sans Arabic",serif}
html[dir=rtl] .serif{font-family:"IBM Plex Sans Arabic",serif}
html[dir=rtl] body{line-height:1.85}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);border:0}
.skip{position:absolute;inset-inline-start:16px;top:-64px;background:var(--gold);color:#171307;
  padding:11px 18px;border-radius:9px;z-index:60;font-weight:600;transition:top .25s var(--e1)}
.skip:focus{top:14px}
:focus-visible{outline:2px solid var(--gold-2);outline-offset:3px;border-radius:5px}
::selection{background:rgba(203,160,90,.28);color:#fff}

/* topbar */
.topbar{position:sticky;top:0;z-index:40;
  background:linear-gradient(to bottom, rgba(14,13,11,0.86), rgba(14,13,11,0.5));
  backdrop-filter:saturate(1.3) blur(12px);border-bottom:1px solid var(--hair)}
.topbar .wrap{display:flex;align-items:center;justify-content:space-between;height:64px}
.brand-mark{font-weight:600;letter-spacing:.04em;font-size:16px}
.brand-mark b{color:var(--gold-2);font-weight:600}
.lang-toggle{font-family:"IBM Plex Mono",monospace;font-size:12.5px;font-weight:500;letter-spacing:.06em;
  color:var(--ivory-2);border:1px solid var(--line);padding:7px 14px;border-radius:999px;
  transition:all .28s var(--e1)}
.lang-toggle:hover{border-color:var(--gold);color:var(--gold-2);box-shadow:var(--glow-soft)}

/* hero */
.hero{padding:clamp(60px,11vh,120px) 0 44px;position:relative}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:12px;font-weight:500;letter-spacing:.22em;
  text-transform:uppercase;color:var(--gold);margin:0 0 26px;display:flex;align-items:center;gap:12px}
.eyebrow::before{content:"";width:30px;height:1px;background:var(--gold);opacity:.7}
.hero-line{font-family:"Fraunces","IBM Plex Sans Arabic",serif;font-weight:500;
  font-size:clamp(40px,8.2vw,104px);line-height:1.02;margin:0;letter-spacing:-0.025em;color:var(--ivory)}
html[dir=rtl] .hero-line{font-family:"IBM Plex Sans Arabic",serif;font-weight:700}
.hero-line .count{color:var(--gold-2);font-family:"IBM Plex Sans Arabic",sans-serif;font-weight:700;
  text-shadow:0 0 44px rgba(203,160,90,.35)}
.hero-sub{max-width:600px;margin:30px 0 0;font-size:clamp(16px,1.8vw,19px);color:var(--ivory-2);line-height:1.6}
.stamp{font-family:"IBM Plex Mono",monospace;font-size:11.5px;letter-spacing:.04em;color:var(--faint)}

/* ledger strip */
.ledger{display:grid;grid-template-columns:repeat(6,1fr);gap:0;margin-top:52px;
  border-top:1px solid var(--line)}
.led{padding:20px 18px 18px;border-inline-end:1px solid var(--hair);position:relative}
.led:last-child{border-inline-end:0}
.led-n{font-size:clamp(22px,2.6vw,30px);font-weight:700;color:var(--ivory);line-height:1}
.led-n .count{color:var(--ivory)}
.led-l{font-size:12.5px;color:var(--muted);margin-top:9px}
.led-s{font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.04em;color:var(--faint);margin-top:5px}

/* sections */
section{scroll-margin-top:84px}
.block{padding:clamp(48px,8vh,88px) 0;border-top:1px solid var(--hair)}
.kicker{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.2em;text-transform:uppercase;
  color:var(--gold);margin:0 0 16px}
.h2{font-family:"Fraunces","IBM Plex Sans Arabic",serif;font-weight:500;
  font-size:clamp(28px,4.4vw,46px);letter-spacing:-0.02em;margin:0 0 30px;color:var(--ivory)}
html[dir=rtl] .h2{font-family:"IBM Plex Sans Arabic",serif;font-weight:700}
.lead{max-width:680px;font-size:clamp(17px,2vw,21px);line-height:1.62;color:var(--ivory-2)}
.prose{max-width:680px}
.prose p{margin:0 0 20px;font-size:clamp(16px,1.9vw,20px);line-height:1.66;color:var(--ivory-2)}
.prose p:first-child{color:var(--ivory);font-size:clamp(18px,2.2vw,23px)}
.prose .last{color:var(--gold-2);font-family:"Fraunces","IBM Plex Sans Arabic",serif;font-style:italic}
html[dir=rtl] .prose .last{font-family:"IBM Plex Sans Arabic",serif;font-style:normal}

/* router */
.router{padding:clamp(40px,6vh,64px) 0 8px;border-top:1px solid var(--hair)}
.router-title{font-family:"Fraunces","IBM Plex Sans Arabic",serif;font-size:clamp(20px,2.4vw,26px);
  color:var(--ivory);margin:0 0 22px;font-weight:500}
html[dir=rtl] .router-title{font-family:"IBM Plex Sans Arabic",serif;font-weight:600}
.router-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.router-card{display:flex;flex-direction:column;gap:7px;padding:26px 24px;border-radius:var(--rad);
  background:linear-gradient(180deg,var(--panel),var(--bg-2));border:1px solid var(--line-2);
  position:relative;overflow:hidden;transition:transform .4s var(--e1),border-color .4s var(--e1),box-shadow .4s var(--e1)}
.router-card::after{content:"";position:absolute;inset:0;border-radius:var(--rad);
  background:radial-gradient(400px 200px at 50% -40%,rgba(203,160,90,.16),transparent 70%);
  opacity:0;transition:opacity .4s var(--e1)}
.router-card:hover{transform:translateY(-4px);border-color:var(--line);box-shadow:0 24px 60px -30px rgba(0,0,0,.8),var(--glow-soft)}
.router-card:hover::after{opacity:1}
.router-card.active{border-color:var(--gold)}
.rc-num{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.14em;color:var(--gold);opacity:.8}
.rc-label{font-weight:600;font-size:18px;color:var(--ivory);position:relative}
.rc-desc{font-size:13.5px;color:var(--muted);position:relative}
.rc-go{position:absolute;inset-inline-end:22px;top:26px;color:var(--gold);opacity:0;transform:translateX(-6px);transition:all .4s var(--e1)}
html[dir=rtl] .rc-go{transform:scaleX(-1) translateX(-6px)}
.router-card:hover .rc-go{opacity:1;transform:translateX(0)}
html[dir=rtl] .router-card:hover .rc-go{transform:scaleX(-1) translateX(0)}

/* the record */
.record-grid{display:grid;grid-template-columns:1.05fr 1fr;gap:18px}
.panel{background:linear-gradient(180deg,var(--panel),var(--bg-2));border:1px solid var(--line-2);
  border-radius:var(--rad);padding:28px}
.panel-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:20px}
.panel-head h3{margin:0;font-size:14px;font-weight:600;color:var(--ivory-2);letter-spacing:.01em}
.panel .src{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.03em;color:var(--faint)}
/* distribution */
.dist-big{font-size:clamp(56px,9vw,92px);font-weight:700;line-height:.92;color:var(--gold-2);
  letter-spacing:-0.04em;text-shadow:var(--glow);display:block}
.dist-cap{font-size:15px;color:var(--ivory-2);margin:8px 0 22px;font-weight:500}
.dist-bar{display:flex;height:20px;border-radius:10px;overflow:hidden;gap:3px;background:rgba(244,238,224,.05)}
.dist-seg{display:block;height:100%;border-radius:3px}
.dist-seg-0{background:linear-gradient(90deg,var(--gold-deep),var(--gold-2));box-shadow:var(--glow-soft)}
.dist-seg-1{background:rgba(244,238,224,.12)}
.dist-legend{list-style:none;margin:20px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:9px 22px;font-size:13.5px;color:var(--ivory-2)}
.dist-legend li{display:flex;align-items:center;gap:8px}
.dist-legend b{font-variant-numeric:tabular-nums;color:var(--ivory)}
.dot{width:10px;height:10px;border-radius:3px;flex:none}
.dot-0{background:var(--gold-2)}
.dot-1{background:rgba(244,238,224,.2)}
.dist-foot{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--faint);margin:18px 0 0;letter-spacing:.02em}
/* category bars */
.cats{display:flex;flex-direction:column;gap:15px}
.cat{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:14px}
.cat-l{font-size:14px;color:var(--ivory-2);white-space:nowrap}
.cat-track{height:9px;border-radius:6px;background:rgba(244,238,224,.06);overflow:hidden}
.cat-fill{height:100%;border-radius:6px;transform:scaleX(0);transform-origin:inline-start;
  background:linear-gradient(90deg,var(--gold-deep),var(--gold-2));box-shadow:var(--glow-soft);
  transition:transform 1.1s var(--e2)}
.in .cat-fill{transform:scaleX(var(--v))}
.cat-v{font-variant-numeric:tabular-nums;font-weight:700;color:var(--gold-2);font-size:15px;min-width:44px;text-align:end}
.cat-note{font-size:13.5px;color:var(--muted);margin:20px 0 0;line-height:1.55}

/* growth — the signature */
.growth{margin-top:18px;background:
    radial-gradient(700px 300px at 78% 0%,rgba(203,160,90,.08),transparent 65%),
    linear-gradient(180deg,var(--panel),var(--bg-2));
  border:1px solid var(--line);border-radius:var(--rad);padding:30px clamp(20px,3vw,36px) 26px;position:relative}
.growth-top{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:8px}
.growth-cap{font-family:"Fraunces","IBM Plex Sans Arabic",serif;font-size:clamp(19px,2.4vw,27px);
  font-weight:500;color:var(--ivory);letter-spacing:-0.01em;max-width:520px;line-height:1.18;margin:0}
html[dir=rtl] .growth-cap{font-family:"IBM Plex Sans Arabic",serif;font-weight:600}
.g-readout{font-family:"IBM Plex Mono",monospace;font-size:12.5px;color:var(--gold-2);
  border:1px solid var(--line);border-radius:9px;padding:9px 13px;white-space:nowrap;
  transition:opacity .2s var(--e1)}
.g-readout b{color:var(--ivory)}
.chart{width:100%;height:auto;display:block;overflow:visible}
.g-bar{fill:url(#goldbar);transition:opacity .2s;cursor:pointer}
.g-bar:hover,.g-bar.hot{opacity:1}
.g-bar.dim{opacity:.4}
.g-cnt{font-family:"IBM Plex Mono",monospace;font-size:12px;fill:var(--ivory-2);font-variant-numeric:tabular-nums}
.g-x{font-family:"IBM Plex Mono",monospace;font-size:11px;fill:var(--muted)}
.g-line{stroke:var(--gold-2);stroke-width:2.5;filter:drop-shadow(0 0 6px rgba(231,201,131,.5));
  stroke-dasharray:1;stroke-dashoffset:1}
.in .g-line{stroke-dashoffset:0;transition:stroke-dashoffset 1.5s var(--e2) .2s}
.g-dot{fill:var(--bg);stroke:var(--gold-2);stroke-width:2}
.g-axis{stroke:var(--line);stroke-width:1}
.g-rlabel{font-family:"IBM Plex Mono",monospace;font-size:10px;fill:var(--faint)}

/* repeat — dramatic full-width */
.repeat{margin-top:18px;padding:clamp(30px,5vw,52px);border-radius:var(--rad);text-align:center;
  background:radial-gradient(600px 300px at 50% 0%,rgba(203,160,90,.14),transparent 70%),var(--panel);
  border:1px solid var(--line)}
.repeat-big{font-size:clamp(52px,10vw,110px);font-weight:700;color:var(--gold-2);line-height:1;
  letter-spacing:-0.04em;text-shadow:var(--glow)}
.repeat-line{font-family:"Fraunces","IBM Plex Sans Arabic",serif;font-size:clamp(19px,2.6vw,28px);
  color:var(--ivory);margin:16px 0 0;font-weight:500}
html[dir=rtl] .repeat-line{font-family:"IBM Plex Sans Arabic",serif;font-weight:600}
.repeat-note{color:var(--muted);font-size:14.5px;margin:12px auto 0;max-width:520px}

/* reviews */
.reviews .lead{margin:0 0 26px}
.tfilters{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:26px}
.tfilter{font:inherit;font-size:13px;font-weight:500;color:var(--ivory-2);
  background:var(--panel);border:1px solid var(--line-2);border-radius:999px;padding:8px 15px;cursor:pointer;
  transition:all .25s var(--e1)}
.tfilter:hover{border-color:var(--line);color:var(--ivory)}
.tfilter.on{background:var(--gold);color:#171307;border-color:var(--gold);font-weight:600;box-shadow:var(--glow-soft)}
.review-wall{columns:3 300px;column-gap:18px}
.review{break-inside:avoid;margin:0 0 18px;background:linear-gradient(180deg,var(--panel),var(--bg-2));
  border:1px solid var(--line-2);border-radius:var(--rad-s);padding:22px;
  transition:border-color .3s var(--e1),transform .3s var(--e1)}
.review:hover{border-color:var(--line);transform:translateY(-2px)}
.review.hide{display:none}
.review-wall.collapsed .review.extra{display:none}
.r-text{margin:0 0 14px;font-size:14.5px;line-height:1.72;color:var(--ivory)}
.r-meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
.r-name{font-weight:600;color:var(--ivory-2)}
.r-listing{flex-basis:100%;color:var(--muted)}
.r-badge{flex-basis:100%;font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.04em;color:var(--gold);margin-top:2px}
.reviews-more{margin-top:14px;text-align:center}

/* operating system */
.os-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin-top:8px}
.os-item{background:linear-gradient(180deg,var(--panel),var(--bg-2));border:1px solid var(--line-2);
  border-radius:var(--rad);padding:26px;transition:border-color .3s var(--e1),transform .3s var(--e1)}
.os-item:hover{border-color:var(--line);transform:translateY(-3px)}
.os-item h3{margin:0 0 11px;font-size:17px;color:var(--ivory);font-weight:600}
.os-item p{margin:0;font-size:14.5px;color:var(--ivory-2);line-height:1.6}
.os-item .means{margin-top:13px;padding-top:13px;border-top:1px solid var(--hair);
  color:var(--gold-2);font-weight:500;font-size:13.5px}

/* tracks */
.tracks{padding:8px 0 0}
.track{border-top:1px solid var(--hair);padding:clamp(30px,5vh,48px) 0;scroll-margin-top:84px;
  opacity:.5;transition:opacity .5s var(--e1)}
.track.lit,.track:target{opacity:1}
.track-h{font-family:"Fraunces","IBM Plex Sans Arabic",serif;font-size:clamp(22px,3vw,30px);
  margin:0 0 14px;font-weight:500;color:var(--ivory)}
html[dir=rtl] .track-h{font-family:"IBM Plex Sans Arabic",serif;font-weight:600}
.track-angle{max-width:680px;color:var(--ivory-2);margin:0 0 20px;font-size:clamp(16px,1.9vw,19px);line-height:1.6}
.track-points{margin:0 0 24px;padding:0;list-style:none;display:grid;gap:11px;max-width:700px}
.track-points li{color:var(--ivory-2);padding-inline-start:22px;position:relative;font-size:15px}
.track-points li::before{content:"";position:absolute;inset-inline-start:0;top:11px;width:6px;height:6px;
  border-radius:50%;background:var(--gold);box-shadow:var(--glow-soft)}
.btn{display:inline-flex;align-items:center;gap:9px;background:var(--gold);color:#171307;font-weight:600;
  font-size:15px;border:1px solid var(--gold);border-radius:11px;padding:13px 24px;cursor:pointer;
  transition:transform .2s var(--e1),box-shadow .3s var(--e1),background .3s var(--e1)}
.btn:hover{box-shadow:var(--glow);background:var(--gold-2)}
.btn:active{transform:scale(.97)}
.btn.ghost{background:transparent;color:var(--gold-2);border-color:var(--line)}
.btn.ghost:hover{background:rgba(203,160,90,.08);box-shadow:none;border-color:var(--gold)}

/* close + footer */
.contact{display:flex;flex-wrap:wrap;gap:13px;margin:8px 0 20px}
.contact-meta{font-family:"IBM Plex Mono",monospace;color:var(--muted);font-size:13px;letter-spacing:.02em}
.foot{border-top:1px solid var(--line);padding:34px 0 70px;color:var(--faint);font-size:12.5px;
  font-family:"IBM Plex Mono",monospace;letter-spacing:.02em}
.foot .dot-live{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--ok);
  margin-inline-end:8px;box-shadow:0 0 8px var(--ok);animation:pulse 2.4s var(--e1) infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}

/* motion */
.reveal-init{opacity:0;transform:translateY(22px)}
.reveal-init.in{opacity:1;transform:none;transition:opacity .7s var(--e2),transform .7s var(--e2)}
@media(max-width:820px){
  .record-grid{grid-template-columns:1fr}
  .ledger{grid-template-columns:repeat(3,1fr)}
  .led:nth-child(3n){border-inline-end:0}
  .led:nth-child(-n+3){border-bottom:1px solid var(--hair)}
}
@media(max-width:560px){
  .review-wall{columns:1}
  .ledger{grid-template-columns:repeat(2,1fr)}
  .led:nth-child(3n){border-inline-end:1px solid var(--hair)}
  .led:nth-child(2n){border-inline-end:0}
}
@media(prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *{transition:none!important;animation:none!important}
  .reveal-init{opacity:1;transform:none}
  .cat-fill{transform:scaleX(var(--v))}
  .g-line{stroke-dashoffset:0}
  .foot .dot-live{animation:none}
}
</style>
</head>
<body>
<a class="skip" href="#content">__SKIP__</a>
<div class="grain" aria-hidden="true"></div>
<header class="topbar"><div class="wrap">
  <span class="brand-mark">__BRAND__</span>
  <a class="lang-toggle" href="__ALT_HREF__" hreflang="__ALT_LANG__">__ALT_LABEL__</a>
</div></header>
<main class="wrap">
__BODY__
</main>
<footer class="foot"><div class="wrap"><p><span class="dot-live" aria-hidden="true"></span>__FOOTER__</p></div></footer>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <linearGradient id="goldbar" x1="0" y1="1" x2="0" y2="0">
    <stop offset="0" stop-color="#8E6C31"></stop><stop offset="1" stop-color="#E7C983"></stop>
  </linearGradient>
</defs></svg>
<script>
(function(){
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var AR = "٠١٢٣٤٥٦٧٨٩";
  function fmtNum(v, lang, dec){
    var s = Math.abs(v).toFixed(dec);
    var parts = s.split(".");
    var intp = parts[0], out = "", c = 0;
    for (var i = intp.length - 1; i >= 0; i--){
      out = intp.charAt(i) + out; c++;
      if (c % 3 === 0 && i > 0){ out = (lang === "ar" ? "٬" : ",") + out; }
    }
    var res = out;
    if (dec > 0){ res = res + (lang === "ar" ? "٫" : ".") + parts[1]; }
    if (lang === "ar"){
      var m = "";
      for (var j = 0; j < res.length; j++){
        var d = "0123456789".indexOf(res.charAt(j));
        m += (d >= 0 ? AR.charAt(d) : res.charAt(j));
      }
      res = m;
    }
    return res;
  }
  function countUp(el){
    if (el.getAttribute("data-done")) return;
    el.setAttribute("data-done", "1");
    var to = parseFloat(el.getAttribute("data-to"));
    var dec = parseInt(el.getAttribute("data-dec") || "0", 10);
    var lang = el.getAttribute("data-lang") || "en";
    var suf = el.getAttribute("data-suffix") || "";
    if (reduce || !isFinite(to)){ el.textContent = fmtNum(to, lang, dec) + suf; return; }
    var dur = 1200, start = null;
    function step(ts){
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - p, 4);
      el.textContent = fmtNum(to * eased, lang, dec) + suf;
      if (p < 1){ requestAnimationFrame(step); }
      else { el.textContent = fmtNum(to, lang, dec) + suf; }
    }
    requestAnimationFrame(step);
  }
  // hero counts immediately
  document.querySelectorAll(".hero .count").forEach(countUp);
  // reveal + count on scroll
  var io = null;
  if ("IntersectionObserver" in window && !reduce){
    document.querySelectorAll(".block, .router, .tracks").forEach(function(b){ b.classList.add("reveal-init"); });
    io = new IntersectionObserver(function(ents){
      ents.forEach(function(en){
        if (en.isIntersecting){
          en.target.classList.add("in");
          en.target.querySelectorAll(".count").forEach(countUp);
          io.unobserve(en.target);
        }
      });
    }, {rootMargin:"0px 0px -8% 0px"});
    document.querySelectorAll(".block, .router, .tracks").forEach(function(b){ io.observe(b); });
    setTimeout(function(){
      document.querySelectorAll(".block, .router, .tracks").forEach(function(b){ b.classList.add("in"); });
      document.querySelectorAll(".count").forEach(countUp);
    }, 2600);
  } else {
    document.querySelectorAll(".count").forEach(countUp);
    document.querySelectorAll(".block, .router, .tracks").forEach(function(b){ b.classList.add("in"); });
  }
  // growth chart readout
  var readout = document.querySelector(".g-readout");
  var bars = document.querySelectorAll(".g-bar");
  function showBar(b){
    if (!readout) return;
    bars.forEach(function(x){ x.classList.toggle("dim", x !== b); x.classList.toggle("hot", x === b); });
    readout.innerHTML = b.getAttribute("data-read");
  }
  function clearBars(){ bars.forEach(function(x){ x.classList.remove("dim"); x.classList.remove("hot"); }); }
  bars.forEach(function(b){
    b.addEventListener("mouseenter", function(){ showBar(b); });
    b.addEventListener("focus", function(){ showBar(b); });
  });
  var gwrap = document.querySelector(".growth");
  if (gwrap){ gwrap.addEventListener("mouseleave", clearBars); }
  // router
  function lightTrack(id){
    document.querySelectorAll(".track").forEach(function(tr){ tr.classList.toggle("lit", tr.id === id); });
    document.querySelectorAll(".router-card").forEach(function(c){ c.classList.toggle("active", c.getAttribute("data-track") === id); });
  }
  document.querySelectorAll(".router-card").forEach(function(c){
    c.addEventListener("click", function(){ lightTrack(c.getAttribute("data-track")); });
  });
  function fromHash(){ var h = location.hash.replace("#",""); if(h){ lightTrack(h); } }
  window.addEventListener("hashchange", fromHash); fromHash();
  // reviews filter + show all
  var wall = document.querySelector(".review-wall");
  var filters = document.querySelectorAll(".tfilter");
  var cards = document.querySelectorAll(".review");
  var moreBtn = document.querySelector("[data-show-all]");
  var expanded = false;
  if (moreBtn){
    moreBtn.addEventListener("click", function(){
      expanded = true;
      if (wall){ wall.classList.remove("collapsed"); }
      if (moreBtn.parentNode){ moreBtn.parentNode.style.display = "none"; }
    });
  }
  filters.forEach(function(f){
    f.addEventListener("click", function(){
      var theme = f.getAttribute("data-theme");
      filters.forEach(function(x){ x.classList.toggle("on", x === f); });
      if (wall){ wall.classList.toggle("collapsed", theme === "all" && !expanded); }
      if (moreBtn && moreBtn.parentNode){ moreBtn.parentNode.style.display = (theme === "all" && !expanded) ? "" : "none"; }
      cards.forEach(function(card){
        var themes = (card.getAttribute("data-themes") || "").split(" ");
        card.classList.toggle("hide", !(theme === "all" || themes.indexOf(theme) !== -1));
      });
    });
  });
})();
</script>
</body>
</html>
"""


def render_page(lang, base="", links=None):
    lang = "ar" if lang == "ar" else "en"
    t = COPY[lang]
    blob = render.assemble(lang)
    m = blob["metrics"]
    cr = (blob["manual"].get("commercial_registration") or {}).get("value", "7050158810")
    links = links or {}
    links = {
        "book": links.get("book", "#"),
        "wa": links.get("wa", "#"),
        "email": links.get("email", "oujaresidence@gmail.com"),
    }
    turnovers = "14,000+"
    if lang == "ar":
        turnovers = render.localize_digits(turnovers.replace(",", "٬"), "ar")
    as_of = blob.get("as_of") or m.get("as_of")
    body = (
        build_hero(t, m, lang, turnovers, as_of)
        + build_router(t)
        + build_what(t)
        + build_record(t, m, lang)
        + build_reviews(t, blob["reviews"], lang)
        + build_os(t)
        + build_tracks(t, cr, lang)
        + build_close(t, cr, lang, links)
    )
    sync = render.localize_digits(blob.get("as_of") or "", lang)
    footer = t["footer_sync"].replace("{sync}", sync)
    stays = render.fmt_int(m.get("reservations_total", 0), lang)
    rating = render.fmt_dec(m.get("rating_avg_5", 0), lang)
    desc = t["meta_desc"].replace("{stays}", stays).replace("{rating}", rating)
    head_extra = build_head_extra(t, m, lang, base, desc)
    return (SHELL
            .replace("__LANG__", t["lang"])
            .replace("__DIR__", t["dir"])
            .replace("__TITLE__", _e(t["title"]))
            .replace("__DESC__", _e(desc))
            .replace("__HEAD_EXTRA__", head_extra)
            .replace("__SKIP__", _e(t["skip"]))
            .replace("__BRAND__", _e(t["brand"]))
            .replace("__ALT_HREF__", _e(t["alt_href"]))
            .replace("__ALT_LANG__", "ar" if lang == "en" else "en")
            .replace("__ALT_LABEL__", _e(t["alt_label"]))
            .replace("__FOOTER__", _e(footer))
            .replace("__BODY__", body))
