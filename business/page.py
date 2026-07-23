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
        "hero_sub": "Ouja Residence operates short-stay residences in Riyadh — 100+ branded units, one in-house team, one operating system.",
        "strip": ["{stays} stays", "{nights} nights", "{guests} guests", "{reviews} reviews", "{rating}★"],
        "as_of_prefix": "as of", "source": "source", "method": "method",
        "src_hostaway": "Hostaway · Airbnb channel", "src_internal": "internal",
        "router_title": "What brings you here?",
        "router": [
            ("platforms", "You run a booking platform", "Supply, quality, pipeline"),
            ("corporate", "You need housing for your people", "Inventory, rates, invoicing"),
            ("suppliers", "You want to sell to or work with us", "Scale, procurement, contact"),
        ],
        "what_title": "What Ouja is",
        "what_body": [
            "Founded 2024. Riyadh. Short-stay residences under a single brand across managed compounds.",
            "It operates on a revenue-share model with owners, with an in-house cleaning team, an in-house technology platform, and a licensed Saudi entity behind it.",
            "The name comes from the old name of Diriyah — the winding valley of Wadi Hanifa.",
        ],
        "record_title": "The record",
        "dist_title": "Rating distribution",
        "dist_perfect": "10 / 10", "dist_rest": "9 / 10 or below",
        "cat_title": "Category sub-scores (out of 10)",
        "cat_note": "Communication and check-in score highest — the two categories most correlated with guest-support escalations.",
        "growth_title": "Growth against rating",
        "growth_cap": "We grew 12× in eight quarters. The rating did not move.",
        "growth_axis_reviews": "Published reviews per quarter", "growth_axis_rating": "Average rating",
        "repeat_line": "{pct} of our stays are guests who came back.",
        "repeat_note": "Repeat rate is the one metric that cannot be bought with marketing spend.",
        "reviews_title": "Reviews as evidence",
        "reviews_intro": "Every review below is a real published Airbnb review from a verified stay. {more} more where these came from.",
        "verified_badge": "Airbnb · verified stay",
        "filter_all": "All",
        "themes": {"cleanliness": "Cleanliness", "checkin": "Check-in", "design": "Design",
                   "communication": "Communication", "location": "Location", "value": "Value",
                   "accuracy": "Accuracy", "repeat": "Returning guest"},
        "os_title": "The operating system",
        "os_items": [
            ("Trusted PMS", "Full API integration across the portfolio.", "Calendar accuracy and one source of truth."),
            ("Proprietary platform", "~49,000 lines, purpose-built: turnover scheduling, staff assignment with absence-driven redistribution, dynamic pricing with per-date explainability, append-only audit logs, vendor ticketing, expense reconciliation, automated owner reporting.", "Predictable quality at scale, verifiable reporting."),
            ("OujaCT", "In-house cleaning team, not outsourced. ~14,000 turnovers.", "Why cleanliness holds at 9.57 across 100+ listings."),
            ("Musaed", "In-house AI guest assistant, pre-booking communication in Arabic and English.", "Faster response, fewer escalations."),
            ("Ouja Elite", "4,500+ member loyalty database.", "The mechanism behind the repeat rate."),
            ("Reach", "100M+ views, 70,000+ followers across TikTok and Snapchat.", "New listings launch to a warm audience, not a cold start."),
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
        "brand": "عوجا الريزيدنس",
        "title": "عوجا الريزيدنس — السجل التشغيلي",
        "meta_desc": "عوجا الريزيدنس تُشغّل وحدات الإقامة القصيرة في الرياض. سنتان، {stays} إقامة، {rating} من ٥.",
        "hero_line": "سنتان. {stays} إقامة. {rating} من ٥.",
        "hero_sub": "عوجا الريزيدنس تُشغّل وحدات الإقامة القصيرة في الرياض — أكثر من ١٠٠ وحدة تحت علامة واحدة، وفريق داخلي واحد، ونظام تشغيل واحد.",
        "strip": ["{stays} إقامة", "{nights} ليلة", "{guests} ضيف", "{reviews} تقييم", "{rating}★"],
        "as_of_prefix": "حتى", "source": "المصدر", "method": "الطريقة",
        "src_hostaway": "هوستاوي · قناة Airbnb", "src_internal": "داخلي",
        "router_title": "ما الذي يهمّك هنا؟",
        "router": [
            ("platforms", "تُدير منصة حجوزات", "العرض، الجودة، خط النمو"),
            ("corporate", "تحتاج سكنًا لفريقك", "الوحدات، الأسعار، الفوترة"),
            ("suppliers", "ترغب بالبيع لنا أو العمل معنا", "الحجم، المشتريات، التواصل"),
        ],
        "what_title": "ما هي عوجا",
        "what_body": [
            "تأسّست عام ٢٠٢٤. الرياض. وحدات إقامة قصيرة تحت علامة واحدة عبر مجمّعات تديرها.",
            "تعمل بنموذج مشاركة في الإيراد مع الملاك، مع فريق تنظيف داخلي، ومنصة تقنية داخلية، وكيان سعودي مُرخّص.",
            "الاسم مأخوذ من الاسم القديم للدرعية — وادي حنيفة المتعرّج.",
        ],
        "record_title": "السجل",
        "dist_title": "توزع التقييمات",
        "dist_perfect": "١٠ / ١٠", "dist_rest": "٩ / ١٠ أو أقل",
        "cat_title": "التقييمات الفرعية (من ١٠)",
        "cat_note": "التواصل وتسجيل الدخول الأعلى — وهما أكثر فئتين ارتباطًا بتصعيد دعم الضيوف.",
        "growth_title": "النمو مقابل التقييم",
        "growth_cap": "نمونا ١٢ ضعفًا في ثمانية أرباع. التقييم لم يتحرّك.",
        "growth_axis_reviews": "التقييمات المنشورة لكل ربع", "growth_axis_rating": "متوسط التقييم",
        "repeat_line": "{pct} من إقاماتنا ضيوف عادوا.",
        "repeat_note": "معدل العودة هو المقياس الوحيد الذي لا يُشترى بإنفاق التسويق.",
        "reviews_title": "التقييمات كدليل",
        "reviews_intro": "كل تقييم أدناه حقيقي ومنشور على Airbnb من إقامة موثّقة. يوجد {more} غيرها.",
        "verified_badge": "Airbnb · إقامة موثّقة",
        "filter_all": "الكل",
        "themes": {"cleanliness": "النظافة", "checkin": "تسجيل الدخول", "design": "التصميم",
                   "communication": "التواصل", "location": "الموقع", "value": "القيمة",
                   "accuracy": "الدقة", "repeat": "ضيف عائد"},
        "os_title": "نظام التشغيل",
        "os_items": [
            ("نظام إدارة موثوق", "تكامل كامل عبر واجهة برمجية لكل المحفظة.", "دقة في التقويم ومصدر واحد للحقيقة."),
            ("منصة خاصة", "نحو ٤٩ألف سطر، مبنية لغرضها: جدولة التجهيز، توزيع المهام مع إعادة التوزيع عند الغياب، تسعير ديناميكي قابل للتفسير لكل تاريخ، سجلات تدقيق غير قابلة للتعديل، تذاكر موردين، تسوية مصروفات، تقارير ملاك آلية.", "جودة ثابتة على نطاق واسع، وتقارير قابلة للتحقق."),
            ("OujaCT", "فريق تنظيف داخلي غير مُسند. نحو ١٤ألف عملية تجهيز.", "لهذا تبقى النظافة عند ٩٫٥٧ عبر أكثر من ١٠٠ وحدة."),
            ("مساعد", "مساعد ضيوف بالذكاء الاصطناعي، تواصل قبل الحجز بالعربية والإنجليزية.", "استجابة أسرع وتصعيد أقل."),
            ("عوجا إيليت", "قاعدة ولاء تضم أكثر من ٤٬٥٠٠ عضو.", "الآلية خلف معدل العودة."),
            ("الانتشار", "أكثر من ١٠٠ مليون مشاهدة، وأكثر من ٧٠ألف متابع عبر تيك توك وسناب شات.", "الوحدات الجديدة تنطلق لجمهور جاهز، لا من الصفر."),
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
def _stat(value, lang):
    return value  # already localized upstream


def build_hero(t, m, lang):
    stays = render.fmt_int(m.get("reservations_total", 0), lang)
    nights = render.fmt_int(m.get("guest_nights", 0), lang)
    guests = render.fmt_int(m.get("unique_guests", 0), lang)
    reviews = render.fmt_int(m.get("reviews_published", 0), lang)
    rating = render.fmt_dec(m.get("rating_avg_5", 0), lang)
    line = t["hero_line"].replace("{stays}", stays).replace("{rating}", rating)
    chips = "".join(
        '<span class="chip">%s</span>' % _e(s
             .replace("{stays}", stays).replace("{nights}", nights)
             .replace("{guests}", guests).replace("{reviews}", reviews)
             .replace("{rating}", rating))
        for s in t["strip"]
    )
    return (
        '<section class="hero" id="content">'
        '<p class="eyebrow">%s</p>'
        '<h1 class="hero-line num">%s</h1>'
        '<p class="hero-sub">%s</p>'
        '<div class="strip">%s</div>'
        '</section>'
    ) % (_e(t["brand"]), _e(line), _e(t["hero_sub"]), chips)


def build_router(t):
    cards = ""
    for tid, label, desc in t["router"]:
        cards += (
            '<a class="router-card" href="#%s" data-track="%s">'
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
    body = "".join("<p>%s</p>" % _e(p) for p in t["what_body"])
    return (
        '<section class="block"><h2>%s</h2><div class="prose">%s</div></section>'
    ) % (_e(t["what_title"]), body)


# ---- charts (inline SVG, server-rendered, with text equivalents) ---------- #
def _svg_open(w, h, label):
    return ('<svg viewBox="0 0 %d %d" role="img" aria-label="%s" '
            'preserveAspectRatio="xMidYMid meet" class="chart">' % (w, h, _e(label)))


def build_distribution(t, m, lang):
    dist = m.get("rating_distribution") or {}
    rows = []
    if len(dist) > 1:
        total = sum(dist.values()) or 1
        for score in range(10, 0, -1):
            c = dist.get(str(score), 0)
            if c:
                rows.append((str(score) + "/10", c / total, render.fmt_int(c, lang)))
    else:
        perfect = m.get("perfect_share", 0)
        rows = [(t["dist_perfect"], perfect, render.fmt_pct(perfect, lang)),
                (t["dist_rest"], max(0.0, 1 - perfect), render.fmt_pct(max(0.0, 1 - perfect), lang))]
    bars = ""
    y = 8
    rh, gap, maxw, x0 = 30, 14, 300, 150
    for label, frac, val in rows:
        w = max(2, int(round(frac * maxw)))
        bars += (
            '<text x="%d" y="%d" class="c-lab" text-anchor="end">%s</text>'
            '<rect x="%d" y="%d" width="%d" height="16" rx="4" class="c-bar"></rect>'
            '<text x="%d" y="%d" class="c-val">%s</text>'
        ) % (x0 - 10, y + 13, _e(label), x0, y, w, x0 + w + 8, y + 13, _e(val))
        y += rh + gap
    svg = _svg_open(480, y + 4, t["dist_title"]) + bars + "</svg>"
    alt = " · ".join("%s: %s" % (lab, val) for lab, _, val in rows)
    return '<figure class="fig">%s<figcaption>%s</figcaption></figure>' % (
        svg, _e(alt))


def build_categories(t, m, lang):
    cats = m.get("category_avgs") or {}
    order = ["communication", "checkin", "accuracy", "location", "cleanliness", "value"]
    items = [(c, cats[c]) for c in order if c in cats]
    rh, gap, maxw, x0 = 26, 12, 240, 150
    bars = ""
    y = 8
    for c, v in items:  # track first, then bar on top (correct layering)
        w = max(2, int(round((v / 10.0) * maxw)))
        bars += (
            '<text x="%d" y="%d" class="c-lab" text-anchor="end">%s</text>'
            '<rect x="%d" y="%d" width="%d" height="14" rx="7" class="c-track"></rect>'
            '<rect x="%d" y="%d" width="%d" height="14" rx="7" class="c-bar"></rect>'
            '<text x="%d" y="%d" class="c-val">%s</text>'
        ) % (x0 - 10, y + 12, _e(t["themes"].get(c, c)),
             x0, y, maxw, x0, y, w,
             x0 + maxw + 8, y + 12, _e(render.fmt_dec(v, lang)))
        y += rh + gap
    svg = _svg_open(440, y + 4, t["cat_title"]) + bars + "</svg>"
    alt = " · ".join("%s %s" % (t["themes"].get(c, c), render.fmt_dec(v, lang)) for c, v in items)
    return '<figure class="fig">%s<figcaption>%s</figcaption></figure>' % (svg, _e(alt))


def build_growth(t, m, lang):
    q = m.get("reviews_by_quarter") or []
    if not q:
        return ""
    counts = [row.get("count", 0) for row in q]
    maxc = max(counts) or 1
    W, H = 560, 300
    padL, padR, padT, padB = 40, 40, 30, 46
    plotW = W - padL - padR
    plotH = H - padT - padB
    n = len(q)
    slot = plotW / n
    bw = slot * 0.5
    bars, xlabels = "", ""
    for i, row in enumerate(q):
        c = row.get("count", 0)
        bh = (c / maxc) * plotH
        x = padL + i * slot + (slot - bw) / 2
        yb = padT + plotH - bh
        bars += '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" class="g-bar"></rect>' % (x, yb, bw, bh)
        bars += '<text x="%.1f" y="%.1f" class="g-cnt" text-anchor="middle">%s</text>' % (
            x + bw / 2, yb - 5, _e(render.fmt_int(c, lang)))
        xlabels += '<text x="%.1f" y="%.1f" class="g-x" text-anchor="middle">%s</text>' % (
            padL + i * slot + slot / 2, H - padB + 18, _e(render.localize_digits(row.get("q", ""), lang)))
    # rating line, zoomed to 4.0-5.0 to show flatness honestly (labeled on axis)
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
        line = '<path d="%s" class="g-line" fill="none"></path>' % d
        for px, py in pts:
            line += '<circle cx="%.1f" cy="%.1f" r="3" class="g-dot"></circle>' % (px, py)
    axis = ('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" class="g-axis"></line>'
            % (padL, padT + plotH, W - padR, padT + plotH))
    svg = _svg_open(W, H, t["growth_title"]) + axis + bars + line + xlabels + "</svg>"
    first, last = q[0], q[-1]
    alt = "%s: %s → %s" % (
        t["growth_axis_reviews"],
        render.fmt_int(first.get("count", 0), lang),
        render.fmt_int(last.get("count", 0), lang))
    return ('<figure class="fig fig-hero">%s'
            '<figcaption class="growth-cap">%s</figcaption>'
            '<p class="sr-only">%s</p></figure>') % (svg, _e(t["growth_cap"]), _e(alt))


def build_record(t, m, lang):
    repeat = t["repeat_line"].replace("{pct}", render.fmt_pct(m.get("repeat_guest_share", 0), lang))
    return (
        '<section class="block record"><h2>%s</h2>'
        '<div class="record-grid">'
        '<div class="card"><h3>%s</h3>%s</div>'
        '<div class="card"><h3>%s</h3>%s<p class="note">%s</p></div>'
        '</div>'
        '<div class="card card-wide"><h3>%s</h3>%s</div>'
        '<div class="repeat"><p class="repeat-line num">%s</p><p class="note">%s</p></div>'
        '</section>'
    ) % (
        _e(t["record_title"]),
        _e(t["dist_title"]), build_distribution(t, m, lang),
        _e(t["cat_title"]), build_categories(t, m, lang), _e(t["cat_note"]),
        _e(t["growth_title"]), build_growth(t, m, lang),
        _e(repeat), _e(t["repeat_note"]),
    )


def build_reviews(t, reviews, lang):
    more = render.fmt_int(2633 - len(reviews), lang)
    intro = t["reviews_intro"].replace("{more}", more)
    # theme filter chips (only themes we render)
    theme_keys = ["cleanliness", "checkin", "design", "communication", "location", "value", "repeat"]
    chips = '<button class="tfilter on" data-theme="all" type="button">%s</button>' % _e(t["filter_all"])
    for k in theme_keys:
        chips += '<button class="tfilter" data-theme="%s" type="button">%s</button>' % (k, _e(t["themes"][k]))
    cards = ""
    for r in reviews:
        rlang = r.get("lang", "en")
        rdir = "rtl" if rlang == "ar" else "ltr"
        themes = " ".join(r.get("themes", []))
        cards += (
            '<article class="review" data-themes="%s" lang="%s" dir="%s">'
            '<p class="r-text">%s</p>'
            '<div class="r-meta">'
            '<span class="r-name">%s</span>'
            '<span class="r-dot">·</span>'
            '<span class="r-date">%s</span>'
            '<bdi class="r-listing">%s</bdi>'
            '<span class="r-badge">%s</span>'
            '</div></article>'
        ) % (
            _e(themes), _e(rlang), rdir,
            _e(r.get("text", "")),
            _e(r.get("name", "")),
            _e(render.localize_digits(r.get("date", ""), lang)),
            _e(r.get("listing", "")),
            _e(t["verified_badge"]),
        )
    return (
        '<section class="block reviews" id="reviews"><h2>%s</h2>'
        '<p class="intro">%s</p>'
        '<div class="tfilters" role="group" aria-label="filter">%s</div>'
        '<div class="review-wall">%s</div>'
        '</section>'
    ) % (_e(t["reviews_title"]), _e(intro), chips, cards)


def build_os(t):
    items = ""
    for name, what, means in t["os_items"]:
        items += (
            '<div class="os-item"><h3>%s</h3><p>%s</p><p class="means">%s</p></div>'
        ) % (_e(name), _e(what), _e(means))
    return '<section class="block"><h2>%s</h2><div class="os-grid">%s</div></section>' % (
        _e(t["os_title"]), items)


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
        '<section class="block close" id="close"><h2>%s</h2>'
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
__HEAD_EXTRA__
<style>
:root{
  --cream:#F6F2EA; --paper:#FFFDF8; --ink:#211E19; --ink-2:#5A554C; --ink-3:#8A8477;
  --line:#E7E0D3; --line-2:#D8CFBE; --gold:#B0863C; --gold-2:#8A6A2E; --gold-soft:#F0E6D2;
  --ok:#4C7A52; --warn:#B0863C; --bad:#A5503C; --info:#4A6B86;
  --r:14px; --rs:9px; --mx:1080px;
  --ease:cubic-bezier(0.23,1,0.32,1);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--cream);color:var(--ink);
  font-family:"IBM Plex Sans Arabic",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:17px;line-height:1.65;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}
html[dir=rtl] body{line-height:1.9}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1;letter-spacing:-0.01em}
.wrap{max-width:var(--mx);margin:0 auto;padding:0 22px}
a{color:inherit}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);border:0}
.skip{position:absolute;inset-inline-start:12px;top:-60px;background:var(--ink);color:var(--paper);
  padding:10px 16px;border-radius:8px;z-index:50;transition:top .2s var(--ease)}
.skip:focus{top:12px}
:focus-visible{outline:2px solid var(--gold);outline-offset:3px;border-radius:4px}

.topbar{position:sticky;top:0;z-index:40;background:color-mix(in srgb,var(--cream) 88%,transparent);
  backdrop-filter:saturate(1.2) blur(8px);border-bottom:1px solid var(--line)}
.topbar .wrap{display:flex;align-items:center;justify-content:space-between;height:58px}
.brand-mark{font-weight:700;letter-spacing:.02em}
.lang-toggle{font-size:14px;font-weight:600;color:var(--ink-2);text-decoration:none;
  border:1px solid var(--line-2);padding:6px 13px;border-radius:999px;transition:all .2s var(--ease)}
.lang-toggle:hover{border-color:var(--gold);color:var(--gold-2)}

.hero{padding:74px 0 30px}
.eyebrow{margin:0 0 20px;font-size:13px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--gold-2)}
.hero-line{font-size:clamp(34px,7vw,68px);line-height:1.04;margin:0;font-weight:700;letter-spacing:-0.02em}
.hero-sub{max-width:640px;margin:22px 0 0;font-size:18px;color:var(--ink-2)}
.strip{display:flex;flex-wrap:wrap;gap:8px;margin-top:30px}
.chip{font-size:14px;font-weight:600;color:var(--ink-2);background:var(--paper);
  border:1px solid var(--line);border-radius:999px;padding:7px 15px;font-variant-numeric:tabular-nums}

section{scroll-margin-top:72px}
.block{padding:44px 0;border-top:1px solid var(--line)}
.block>h2,.record>h2,.reviews>h2,.close>h2{font-size:clamp(22px,3.4vw,30px);margin:0 0 26px;font-weight:700;letter-spacing:-0.01em}
.prose{max-width:660px}
.prose p{margin:0 0 14px;color:var(--ink-2)}

.router{padding:34px 0 6px}
.router-title{font-size:15px;font-weight:600;letter-spacing:.02em;color:var(--ink-3);margin:0 0 16px}
.router-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.router-card{display:flex;flex-direction:column;gap:4px;padding:20px;background:var(--paper);
  border:1px solid var(--line);border-radius:var(--r);text-decoration:none;position:relative;
  transition:transform .25s var(--ease),border-color .25s var(--ease),box-shadow .25s var(--ease)}
.router-card:hover{transform:translateY(-2px);border-color:var(--line-2);box-shadow:0 10px 30px -18px rgba(33,30,25,.4)}
.router-card.active{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold) inset}
.rc-label{font-weight:600;font-size:17px}
.rc-desc{font-size:14px;color:var(--ink-3)}
.rc-go{position:absolute;inset-inline-end:18px;top:20px;color:var(--gold);opacity:0;transform:translateX(-4px);
  transition:all .25s var(--ease)}
html[dir=rtl] .rc-go{transform:scaleX(-1) translateX(-4px)}
.router-card:hover .rc-go{opacity:1;transform:translateX(0)}
html[dir=rtl] .router-card:hover .rc-go{transform:scaleX(-1) translateX(0)}

.record-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);padding:22px}
.card h3{margin:0 0 14px;font-size:15px;font-weight:600;color:var(--ink-2)}
.card-wide{margin-top:16px}
.note{font-size:14px;color:var(--ink-3);margin:12px 0 0}
.fig{margin:0}
.fig .chart{width:100%;height:auto;overflow:visible}
.fig-hero .chart{max-width:620px}
figcaption{font-size:14px;color:var(--ink-3);margin-top:10px}
.growth-cap{font-size:16px;color:var(--ink);font-weight:600;margin-top:14px}
.c-lab{font-size:13px;fill:var(--ink-2)}
.c-val{font-size:13px;fill:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
.c-track{fill:var(--gold-soft)}
.c-bar{fill:var(--gold)}
.g-bar{fill:var(--gold-soft)}
.g-cnt{font-size:11px;fill:var(--ink-3);font-variant-numeric:tabular-nums}
.g-x{font-size:11px;fill:var(--ink-3)}
.g-line{stroke:var(--gold);stroke-width:2.5}
.g-dot{fill:var(--paper);stroke:var(--gold);stroke-width:2}
.g-axis{stroke:var(--line-2);stroke-width:1}
.repeat{margin-top:24px;padding:24px;background:var(--ink);color:var(--paper);border-radius:var(--r)}
.repeat-line{font-size:clamp(20px,3vw,26px);font-weight:700;margin:0}
.repeat .note{color:color-mix(in srgb,var(--paper) 70%,transparent)}

.reviews .intro{max-width:660px;color:var(--ink-2);margin:0 0 20px}
.tfilters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}
.tfilter{font:inherit;font-size:13px;font-weight:600;color:var(--ink-2);background:var(--paper);
  border:1px solid var(--line);border-radius:999px;padding:6px 13px;cursor:pointer;
  transition:all .18s var(--ease)}
.tfilter:hover{border-color:var(--line-2)}
.tfilter.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.review-wall{columns:3 280px;column-gap:16px}
.review{break-inside:avoid;margin:0 0 16px;background:var(--paper);border:1px solid var(--line);
  border-radius:var(--rs);padding:18px;transition:opacity .25s var(--ease)}
.review.hide{display:none}
.r-text{margin:0 0 12px;font-size:15px;line-height:1.7}
.r-meta{display:flex;flex-wrap:wrap;align-items:center;gap:7px;font-size:12.5px;color:var(--ink-3)}
.r-name{font-weight:600;color:var(--ink-2)}
.r-listing{flex-basis:100%;color:var(--ink-3)}
.r-badge{flex-basis:100%;color:var(--gold-2);font-weight:600}

.os-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
.os-item{background:var(--paper);border:1px solid var(--line);border-radius:var(--r);padding:20px}
.os-item h3{margin:0 0 8px;font-size:16px}
.os-item p{margin:0;font-size:14.5px;color:var(--ink-2)}
.os-item .means{margin-top:10px;color:var(--gold-2);font-weight:600;font-size:13.5px}
.compliance{list-style:none;padding:0;margin:0;display:grid;gap:10px;max-width:680px}
.compliance li{padding-inline-start:20px;position:relative;color:var(--ink-2)}
.compliance li::before{content:"";position:absolute;inset-inline-start:0;top:11px;width:7px;height:7px;
  border-radius:2px;background:var(--gold)}

.tracks{padding:8px 0 0}
.track{border-top:1px solid var(--line);padding:36px 0;scroll-margin-top:72px;
  opacity:.62;transition:opacity .35s var(--ease)}
.track.lit,.track:target{opacity:1}
.track-h{font-size:22px;margin:0 0 12px;font-weight:700}
.track-angle{max-width:660px;color:var(--ink-2);margin:0 0 16px;font-size:17px}
.track-points{margin:0 0 20px;padding-inline-start:20px;display:grid;gap:8px;max-width:680px}
.track-points li{color:var(--ink-2)}
.btn{display:inline-block;background:var(--gold);color:#fff;font-weight:600;font-size:15px;
  text-decoration:none;border:1px solid var(--gold);border-radius:10px;padding:12px 22px;cursor:pointer;
  transition:transform .18s var(--ease),background .2s var(--ease)}
.btn:hover{background:var(--gold-2)}
.btn:active{transform:scale(.97)}
.btn.ghost{background:transparent;color:var(--gold-2)}
.btn.ghost:hover{background:var(--gold-soft)}
.lead-form{margin-top:8px;max-width:720px}
.f-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.f-field{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:600;color:var(--ink-2)}
.f-wide{grid-column:1/-1}
.f-field input,.f-field textarea{font:inherit;font-size:15px;font-weight:400;color:var(--ink);
  background:var(--paper);border:1px solid var(--line-2);border-radius:9px;padding:11px 13px}
.f-field input:focus,.f-field textarea:focus{border-color:var(--gold);outline:none}
.f-err{color:var(--bad);font-size:14px;font-weight:600;margin:0 0 12px}
.f-ok{color:var(--ok);font-size:15px;font-weight:600;margin:12px 0 0}

.contact{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:16px}
.contact-meta{color:var(--ink-3);font-size:14px;font-variant-numeric:tabular-nums}
.foot{border-top:1px solid var(--line);padding:28px 0 60px;color:var(--ink-3);font-size:13px}
.foot .as{font-variant-numeric:tabular-nums}

@media(max-width:720px){
  .router-grid,.record-grid,.os-grid,.f-grid{grid-template-columns:1fr}
  .review-wall{columns:1}
  .hero{padding:48px 0 24px}
}
@media(prefers-reduced-motion:reduce){
  *{transition:none!important;animation:none!important}
}
.reveal{opacity:0;transform:translateY(14px)}
.reveal.in{opacity:1;transform:none;transition:opacity .5s var(--ease),transform .5s var(--ease)}
</style>
</head>
<body>
<a class="skip" href="#content">__SKIP__</a>
<header class="topbar"><div class="wrap">
  <span class="brand-mark">__BRAND__</span>
  <a class="lang-toggle" href="__ALT_HREF__" hreflang="__ALT_LANG__">__ALT_LABEL__</a>
</div></header>
<main class="wrap">
__BODY__
</main>
<footer class="foot"><div class="wrap"><p class="as">__FOOTER__</p></div></footer>
<script>
(function(){
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // scroll reveal
  var blocks = document.querySelectorAll(".block, .router, .tracks");
  if (!reduce && "IntersectionObserver" in window){
    blocks.forEach(function(b){ b.classList.add("reveal"); });
    var io = new IntersectionObserver(function(ents){
      ents.forEach(function(en){ if(en.isIntersecting){ en.target.classList.add("in"); io.unobserve(en.target); } });
    }, {rootMargin: "0px 0px -8% 0px"});
    blocks.forEach(function(b){ io.observe(b); });
    // belt-and-suspenders: nothing may stay hidden if the observer never fires.
    setTimeout(function(){ blocks.forEach(function(b){ b.classList.add("in"); }); }, 1600);
  }
  // router: light the chosen track, mark active card
  function lightTrack(id){
    document.querySelectorAll(".track").forEach(function(tr){ tr.classList.toggle("lit", tr.id === id); });
    document.querySelectorAll(".router-card").forEach(function(c){ c.classList.toggle("active", c.getAttribute("data-track") === id); });
  }
  document.querySelectorAll(".router-card").forEach(function(c){
    c.addEventListener("click", function(){ lightTrack(c.getAttribute("data-track")); });
  });
  function fromHash(){ var h = location.hash.replace("#",""); if(h){ lightTrack(h); } }
  window.addEventListener("hashchange", fromHash);
  fromHash();
  // lead / proposal forms -> POST to existing ticketing (no new inbox)
  document.querySelectorAll(".lead-form").forEach(function(form){
    form.addEventListener("submit", function(ev){
      ev.preventDefault();
      var kind = form.getAttribute("data-kind");
      var data = {};
      form.querySelectorAll("input, textarea").forEach(function(el){
        data[el.getAttribute("name")] = el.value.trim();
      });
      var err = form.querySelector(".f-err");
      var ok = form.querySelector(".f-ok");
      var btn = form.querySelector("button[type=submit]");
      if (!data.email && !data.phone){ if(err){ err.hidden = false; } return; }
      if (err){ err.hidden = true; }
      if (btn){ btn.disabled = true; }
      fetch("/api/business/" + kind, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(data)
      }).then(function(r){ return r.ok ? r.json() : Promise.reject(r); })
        .then(function(){
          var grid = form.querySelector(".f-grid");
          if (grid){ grid.style.display = "none"; }
          if (btn){ btn.style.display = "none"; }
          if (ok){ ok.hidden = false; }
        })
        .catch(function(){
          if (btn){ btn.disabled = false; }
          if (err){ err.hidden = false; err.textContent = form.getAttribute("data-retry") || "Please try again."; }
        });
    });
  });
  // review theme filter
  var filters = document.querySelectorAll(".tfilter");
  var cards = document.querySelectorAll(".review");
  filters.forEach(function(f){
    f.addEventListener("click", function(){
      var theme = f.getAttribute("data-theme");
      filters.forEach(function(x){ x.classList.toggle("on", x === f); });
      cards.forEach(function(card){
        var themes = (card.getAttribute("data-themes") || "").split(" ");
        var show = theme === "all" || themes.indexOf(theme) !== -1;
        card.classList.toggle("hide", !show);
      });
    });
  });
})();
</script>
</body>
</html>"""


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
    body = (
        build_hero(t, m, lang)
        + build_router(t)
        + build_what(t)
        + build_record(t, m, lang)
        + build_reviews(t, blob["reviews"], lang)
        + build_os(t)
        + build_compliance(t, cr, lang)
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
