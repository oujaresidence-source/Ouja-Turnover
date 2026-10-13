# -*- coding: utf-8 -*-
"""
site_home.content — every public sentence on oujares.com, Arabic first, English mirror.

Rules (owner brief, 2026-10-12):
  * Modern Standard Arabic — never Najdi on public pages.
  * No booking and no payment happen on this site; booking and payment happen inside
    Airbnb. Never "book direct", never "book now".
  * Never state how many apartments we manage. No invented facts, numbers, reviews,
    awards or partner logos.

Values that come from the register ({legal}, {cr}, {email} ...) are filled in by
render.py from SITE_IDENTITY, so a sentence here can never drift from the register.
Strings are trusted static copy; render.py escapes every identity value it inserts.
"""

UPDATED = {"ar": "12 أكتوبر 2026", "en": "12 October 2026"}

COMMON = {
    "ar": {
        "skip": "تخطَّ إلى المحتوى",
        "nav_label": "التنقل الرئيسي",
        "nav_contact": "التواصل",
        "switch": "English",
        "switch_lang": "en",
        "notice": "لا يتم أي حجز أو دفع عبر هذا الموقع. الحجز والدفع يتمّان داخل منصة Airbnb.",
        "foot_pages": "الصفحات",
        "foot_contact": "التواصل",
        "privacy": "سياسة الخصوصية",
        "terms": "الشروط والأحكام",
        "contact": "التواصل والشكاوى",
        "home": "الرئيسية",
        "cr": "السجل التجاري",
        "na": "العنوان الوطني",
        "riyadh": "الرياض، المملكة العربية السعودية",
        "rights": "جميع الحقوق محفوظة.",
        "travel_licence": "ترخيص وزارة السياحة",
        "category": "الفئة",
        "licence_no": "رقم الترخيص",
        "badge_alt": "شارة توثيق المتجر الإلكتروني من المركز السعودي للأعمال",
        "badge_text": "متجر موثَّق لدى المركز السعودي للأعمال",
        "email": "البريد الإلكتروني",
        "whatsapp": "واتساب",
        "mobile": "الجوال",
        "support": "خدمة العملاء",
        "follow": "حساباتنا",
        "tiktok": "تيك توك",
        "instagram": "إنستغرام",
        "x": "إكس",
        "snapchat": "سناب شات",
        "updated": "آخر تحديث",
        "logo_alt": "شعار عوجا ريزيدنس",
    },
    "en": {
        "skip": "Skip to content",
        "nav_label": "Main navigation",
        "nav_contact": "Contact",
        "switch": "العربية",
        "switch_lang": "ar",
        "notice": "No booking or payment takes place on this website. Booking and payment take place inside Airbnb.",
        "foot_pages": "Pages",
        "foot_contact": "Contact",
        "privacy": "Privacy Policy",
        "terms": "Terms and Conditions",
        "contact": "Contact and Complaints",
        "home": "Home",
        "cr": "Commercial Registration",
        "na": "National Address",
        "riyadh": "Riyadh, Saudi Arabia",
        "rights": "All rights reserved.",
        "travel_licence": "Ministry of Tourism licence",
        "category": "Category",
        "licence_no": "Licence No.",
        "badge_alt": "Saudi Business Center e-commerce verification badge",
        "badge_text": "Verified store — Saudi Business Center",
        "email": "Email",
        "whatsapp": "WhatsApp",
        "mobile": "Mobile",
        "support": "Customer support",
        "follow": "Our accounts",
        "tiktok": "TikTok",
        "instagram": "Instagram",
        "x": "X",
        "snapchat": "Snapchat",
        "updated": "Last updated",
        "logo_alt": "Ouja Residence logo",
    },
}

# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
HOME = {
    "ar": {
        "title": "عوجا ريزيدنس · شقق مفروشة وإدارة أملاك في الرياض",
        "desc": "عوجا ريزيدنس علامة تجارية لشركة أحمد مساعد بن نصار: شقق مفروشة للإقامة القصيرة والشهرية في الرياض، وإدارة أملاك للملاك. الحجز والدفع عبر Airbnb.",
        "h1": "شقق مفروشة وإدارة أملاك في الرياض",
        "lede": "عوجا ريزيدنس علامة تجارية تابعة لـ{legal}. نقدّم شققًا مفروشة للإقامة القصيرة والشهرية في مدينة الرياض، ونتولّى تشغيل الوحدات السكنية وإدارتها نيابةً عن ملّاكها.",
        "services_h": "ماذا نقدّم",
        "services": [
            ("/apartments", "الإقامة القصيرة",
             "تصفّح شققنا المفروشة في الرياض واطّلع على تفاصيل كل شقة. يتم الحجز والدفع داخل Airbnb.",
             "تصفّح الشقق"),
            ("/monthly", "الإقامة الشهرية",
             "شقق مفروشة للإقامات الطويلة، مع إمكانية الاستفسار عن التوفر والشروط قبل أي التزام.",
             "الإقامة الشهرية"),
            ("/business", "للشركات والجهات",
             "إقامات مفروشة لموظفي الشركات والجهات وضيوفها، وتعريف بخدماتنا لقطاع الأعمال.",
             "خدمات الشركات"),
        ],
        "owners_h": "لملّاك العقارات",
        "owners": "ندير الوحدات السكنية المفروشة نيابةً عن ملّاكها: التشغيل اليومي، والنظافة والصيانة، وخدمة الضيوف، وإعداد كشوف دورية للمالك. للاستفسار راسلنا على {email_link}.",
        "id_h": "بيانات المنشأة",
        "id_sub": "مطابقة لبيانات السجل التجاري",
        "f_brand": "العلامة التجارية",
        "f_legal": "الاسم النظامي",
        "f_cr": "رقم السجل التجاري (الرقم الموحد)",
        "f_na": "العنوان الوطني المختصر",
        "f_addr": "العنوان",
        "f_email": "البريد الإلكتروني",
        "lic_h": "التراخيص",
        "lic_fal_mkt": "رخصة فال للتسويق العقاري",
        "lic_fal_mgmt": "رخصة فال لإدارة الأملاك",
        "lic_rega": "الهيئة العامة للعقار",
        "lic_mot": "وزارة السياحة",
        "contact_h": "تواصل معنا",
        "contact_p": "نستقبل الاستفسارات والشكاوى على مدار الساعة.",
        "contact_cta": "التواصل والشكاوى",
    },
    "en": {
        "title": "Ouja Residence · Furnished apartments and property management in Riyadh",
        "desc": "Ouja Residence is a brand of AHMED MUSAED NASSAR Company: furnished apartments for short and monthly stays in Riyadh, and property management for owners. Booking and payment through Airbnb.",
        "h1": "Furnished apartments and property management in Riyadh",
        "lede": "Ouja Residence is a brand of {legal}. We offer furnished apartments for short and monthly stays in Riyadh, and we operate and manage residential units on behalf of their owners.",
        "services_h": "What we offer",
        "services": [
            ("/apartments", "Short stays",
             "Browse our furnished apartments in Riyadh and see the details of each one. Booking and payment take place inside Airbnb.",
             "Browse apartments"),
            ("/monthly", "Monthly stays",
             "Furnished apartments for longer stays, with the option to ask about availability and terms before any commitment.",
             "Monthly stays"),
            ("/business", "For companies",
             "Furnished stays for the employees and guests of companies and organisations, and an overview of our business services.",
             "Business services"),
        ],
        "owners_h": "For property owners",
        "owners": "We manage furnished residential units on behalf of their owners: day-to-day operations, cleaning and maintenance, guest service, and periodic owner statements. To enquire, write to {email_link}.",
        "id_h": "Company details",
        "id_sub": "As listed in the commercial register",
        "f_brand": "Brand",
        "f_legal": "Legal name",
        "f_cr": "Commercial Registration (Unified No.)",
        "f_na": "Short national address",
        "f_addr": "Address",
        "f_email": "Email",
        "lic_h": "Licences",
        "lic_fal_mkt": "FAL licence: Real estate marketing",
        "lic_fal_mgmt": "FAL licence: Property management",
        "lic_rega": "Real Estate General Authority",
        "lic_mot": "Ministry of Tourism",
        "contact_h": "Get in touch",
        "contact_p": "We receive enquiries and complaints around the clock.",
        "contact_cta": "Contact and complaints",
    },
}

# ---------------------------------------------------------------------------
# Legal pages — each is (title, description, h1, intro, [(h2, [block, ...]), ...]).
# A block is a paragraph string, or ("ul", [items]) / ("ol", [items]).
# ---------------------------------------------------------------------------
PRIVACY = {
    "ar": {
        "title": "سياسة الخصوصية · عوجا ريزيدنس",
        "desc": "كيف تجمع عوجا ريزيدنس بياناتك الشخصية وتستخدمها وتحميها، ومدة الاحتفاظ بها، وكيف تطلب حذفها.",
        "h1": "سياسة الخصوصية",
        "intro": "تشرح هذه السياسة كيف تتعامل {legal} (عوجا ريزيدنس) مع بياناتك الشخصية عند استخدامك لهذا الموقع أو تواصلك معنا، وفق نظام حماية البيانات الشخصية في المملكة العربية السعودية ونظام التجارة الإلكترونية.",
        "sections": [
            ("الجهة المسؤولة عن بياناتك", [
                "{legal}، سجل تجاري رقم {cr}، العنوان الوطني {na}، الرياض. للتواصل في كل ما يخص بياناتك: {email_link}.",
            ]),
            ("البيانات التي نجمعها", [
                ("ul", [
                    "ما ترسله إلينا بنفسك عبر البريد الإلكتروني أو واتساب: اسمك، ووسيلة التواصل معك، ومحتوى رسالتك.",
                    "ما تُدخله في نماذج الاستفسار في صفحات الإقامة الشهرية وخدمات الشركات: الاسم، ورقم الجوال، والبريد الإلكتروني، وتفاصيل طلبك.",
                    "بيانات استخدام أساسية: الصفحات التي تزورها وتفاعلات التصفح بصورة مجمّعة، إضافة إلى السجلات التقنية التي يسجلها الخادم تلقائيًا (مثل عنوان IP ووقت الطلب) لأغراض الأمان.",
                ]),
                "لا نجمع أي بيانات دفع؛ فلا يتم أي دفع عبر هذا الموقع. ولا نستخدم أدوات تتبع إعلانية من جهات خارجية.",
            ]),
            ("لماذا نستخدم بياناتك", [
                ("ul", [
                    "للرد على استفساراتك وشكاواك ومتابعتها.",
                    "لتنظيم إقامتك وخدمتك بعد حجزك عبر Airbnb.",
                    "لتحسين الموقع وحمايته من إساءة الاستخدام.",
                    "للوفاء بالتزاماتنا النظامية.",
                ]),
                "لا نستخدم بياناتك لغير هذه الأغراض، ولا نبيعها لأي جهة.",
            ]),
            ("مع من نشارك بياناتك", [
                "نشارك الحد الأدنى اللازم فقط مع مزوّدي الخدمات الذين يعملون لصالحنا (مثل الاستضافة والبريد الإلكتروني وأنظمة إدارة الحجوزات)، ومع الجهات الحكومية المختصة عند وجود طلب نظامي.",
            ]),
            ("مدة الاحتفاظ بالبيانات", [
                "نحتفظ برسائل التواصل والاستفسارات مدة لا تتجاوز سنتين من آخر تواصل، ما لم يتطلب النظام مدة أطول، ثم نحذفها.",
            ]),
            ("حقوقك", [
                "يحق لك وفق نظام حماية البيانات الشخصية:",
                ("ul", [
                    "العلم بكيفية جمع بياناتك واستخدامها.",
                    "الوصول إلى بياناتك والحصول على نسخة منها.",
                    "طلب تصحيح بياناتك أو تحديثها.",
                    "طلب حذف بياناتك متى انتفت الحاجة إليها.",
                    "الرجوع عن موافقتك على معالجة بياناتك.",
                ]),
                "لتقديم أي طلب، ومنها طلب الحذف، راسلنا على {email_link} مع ذكر وسيلة التواصل التي استخدمتها معنا. نرد على طلبك خلال مدة لا تتجاوز 30 يومًا.",
            ]),
            ("حماية البيانات", [
                "نتخذ إجراءات تنظيمية وتقنية معقولة لحماية بياناتك من الوصول غير المصرح به، منها تشفير الاتصال بالموقع وتقييد الوصول إلى البيانات على المختصين من فريقنا.",
            ]),
            ("التخزين في المتصفح", [
                "قد يستخدم الموقع التخزين المحلي في متصفحك لأغراض وظيفية فقط، مثل تذكّر اللغة. ولا نستخدم ملفات تعريف ارتباط إعلانية.",
            ]),
            ("الشكوى إلى الجهة المختصة", [
                "إذا رأيت أن بياناتك عولجت بما يخالف النظام، فيحق لك تقديم شكوى إلى الهيئة السعودية للبيانات والذكاء الاصطناعي (سدايا)، ونرحب بتواصلك معنا أولًا لمعالجة الأمر.",
            ]),
            ("تحديث هذه السياسة", [
                "قد نحدّث هذه السياسة، ونوضح تاريخ آخر تحديث أعلى الصفحة.",
            ]),
        ],
    },
    "en": {
        "title": "Privacy Policy · Ouja Residence",
        "desc": "How Ouja Residence collects, uses and protects your personal data, how long it is kept, and how to request its deletion.",
        "h1": "Privacy Policy",
        "intro": "This policy explains how {legal} (Ouja Residence) handles your personal data when you use this website or contact us, in line with the Saudi Personal Data Protection Law and the E-Commerce Law.",
        "sections": [
            ("Who is responsible for your data", [
                "{legal}, Commercial Registration No. {cr}, National Address {na}, Riyadh. For anything about your data: {email_link}.",
            ]),
            ("What we collect", [
                ("ul", [
                    "What you send us yourself by email or WhatsApp: your name, how to reach you, and the content of your message.",
                    "What you enter in the enquiry forms on the monthly-stay and business pages: name, mobile number, email, and the details of your request.",
                    "Basic usage data: the pages you visit and browsing interactions in aggregate, plus technical logs the server records automatically (such as IP address and request time) for security.",
                ]),
                "We collect no payment data, because no payment takes place on this website. We use no third-party advertising trackers.",
            ]),
            ("Why we use it", [
                ("ul", [
                    "To answer and follow up on your enquiries and complaints.",
                    "To arrange your stay and serve you after you book through Airbnb.",
                    "To improve the website and protect it from misuse.",
                    "To meet our legal obligations.",
                ]),
                "We do not use your data for any other purpose, and we never sell it.",
            ]),
            ("Who we share it with", [
                "Only the minimum needed, with service providers working on our behalf (such as hosting, email and reservation-management systems), and with competent government authorities when legally required.",
            ]),
            ("How long we keep it", [
                "We keep contact messages and enquiries for no longer than two years from the last contact, unless the law requires a longer period, and then delete them.",
            ]),
            ("Your rights", [
                "Under the Personal Data Protection Law you have the right to:",
                ("ul", [
                    "Know how your data is collected and used.",
                    "Access your data and receive a copy of it.",
                    "Ask for your data to be corrected or updated.",
                    "Request deletion of your data once it is no longer needed.",
                    "Withdraw your consent to its processing.",
                ]),
                "To make any request, including a deletion request, write to {email_link} and mention the contact method you used with us. We answer within 30 days at most.",
            ]),
            ("How we protect it", [
                "We take reasonable organisational and technical measures to protect your data from unauthorised access, including an encrypted connection to the website and limiting access to the members of our team who need it.",
            ]),
            ("Browser storage", [
                "The website may use local storage in your browser for functional purposes only, such as remembering your language. We do not use advertising cookies.",
            ]),
            ("Complaints to the authority", [
                "If you believe your data was processed unlawfully, you may complain to the Saudi Data and AI Authority (SDAIA). We would welcome the chance to resolve it with you first.",
            ]),
            ("Changes to this policy", [
                "We may update this policy; the date of the latest update appears at the top of this page.",
            ]),
        ],
    },
}

TERMS = {
    "ar": {
        "title": "الشروط والأحكام · عوجا ريزيدنس",
        "desc": "شروط استخدام موقع عوجا ريزيدنس: موقع تعريفي للتصفح فقط، والحجز والدفع والإلغاء والاسترداد عبر Airbnb.",
        "h1": "الشروط والأحكام",
        "intro": "يملك هذا الموقع ويديره {legal} (عوجا ريزيدنس)، سجل تجاري رقم {cr}. باستخدامك للموقع فإنك توافق على هذه الشروط.",
        "sections": [
            ("طبيعة الموقع", [
                "هذا الموقع تعريفي للتصفح فقط. لا يتم أي حجز أو دفع عبر هذا الموقع، ولا نطلب منك أي بيانات دفع.",
                "يتم الحجز والدفع داخل منصة Airbnb، وتخضع عملية الحجز لشروط Airbnb وقواعد الإقامة المذكورة في إعلان كل شقة.",
            ]),
            ("الأسعار", [
                "أي سعر يظهر في صفحات الموقع استرشادي فقط. السعر النهائي الملزم، شاملًا جميع الرسوم والضرائب، هو السعر الذي تعرضه منصة Airbnb قبل تأكيد الحجز.",
            ]),
            ("الإلغاء والاسترداد", [
                "يخضع الإلغاء والاسترداد لسياسة الإلغاء المطبقة على حجزك في Airbnb كما تظهر في إعلان الشقة وتأكيد الحجز، ويتم الاسترداد عبر Airbnb.",
                "أي اتفاق إقامة يتم خارج Airbnb يخضع لعقد مكتوب مستقل يحدد شروطه، ولا يُبرم عبر هذا الموقع.",
            ]),
            ("دقة المعلومات", [
                "نحرص على دقة الصور والأوصاف، لكنها للتوضيح، وقد يختلف التوفر والتفاصيل من وقت لآخر. المرجع هو ما يظهر في إعلان الشقة على Airbnb لحظة الحجز.",
            ]),
            ("الملكية الفكرية", [
                "اسم عوجا ريزيدنس وشعارها ومحتوى هذا الموقع مملوكة لـ{legal}، ولا يجوز نسخها أو استخدامها دون إذن كتابي.",
            ]),
            ("الروابط الخارجية", [
                "يحتوي الموقع على روابط لمنصات أخرى مثل Airbnb وواتساب، وتخضع هذه المنصات لشروطها وسياسات الخصوصية الخاصة بها.",
            ]),
            ("الخصوصية", [
                "نتعامل مع بياناتك وفق {privacy_link}.",
            ]),
            ("الشكاوى", [
                "يمكنك تقديم أي شكوى في أي وقت عبر صفحة {contact_link}.",
            ]),
            ("النظام الواجب التطبيق", [
                "تخضع هذه الشروط لأنظمة المملكة العربية السعودية، وتختص الجهات القضائية في مدينة الرياض بالنظر في أي نزاع ينشأ عنها.",
            ]),
        ],
    },
    "en": {
        "title": "Terms and Conditions · Ouja Residence",
        "desc": "Terms of use for the Ouja Residence website: an information site for browsing only; booking, payment, cancellation and refunds go through Airbnb.",
        "h1": "Terms and Conditions",
        "intro": "This website is owned and operated by {legal} (Ouja Residence), Commercial Registration No. {cr}. By using the website you agree to these terms.",
        "sections": [
            ("What this website is", [
                "This is an information website for browsing only. No booking or payment takes place on this website, and we never ask you for payment details.",
                "Booking and payment take place inside Airbnb, and every booking is subject to Airbnb's terms and the house rules stated in each apartment's listing.",
            ]),
            ("Prices", [
                "Any price shown on this website is indicative only. The final binding price, including all fees and taxes, is the price Airbnb shows before you confirm the booking.",
            ]),
            ("Cancellation and refunds", [
                "Cancellation and refunds follow the cancellation policy that applies to your Airbnb booking, as shown in the listing and the booking confirmation; refunds are made through Airbnb.",
                "Any stay agreed outside Airbnb is governed by a separate written contract that sets its own terms, and is never concluded through this website.",
            ]),
            ("Accuracy", [
                "We take care that photos and descriptions are accurate, but they are illustrative, and availability and details can change. What the Airbnb listing shows at the time of booking prevails.",
            ]),
            ("Intellectual property", [
                "The Ouja Residence name, logo and the content of this website belong to {legal} and may not be copied or used without written permission.",
            ]),
            ("External links", [
                "The website links to other platforms such as Airbnb and WhatsApp, which are governed by their own terms and privacy policies.",
            ]),
            ("Privacy", [
                "We handle your data according to our {privacy_link}.",
            ]),
            ("Complaints", [
                "You can raise a complaint at any time through our {contact_link} page.",
            ]),
            ("Governing law", [
                "These terms are governed by the laws of the Kingdom of Saudi Arabia, and the competent courts in Riyadh have jurisdiction over any dispute arising from them.",
            ]),
        ],
    },
}

CONTACT = {
    "ar": {
        "title": "التواصل والشكاوى · عوجا ريزيدنس",
        "desc": "تواصل مع عوجا ريزيدنس أو قدّم شكوى. نستقبل الشكاوى على مدار الساعة ونرد خلال 24 ساعة كحد أقصى.",
        "h1": "التواصل والشكاوى",
        "intro": "نستقبل رسائلك على مدار الساعة طوال أيام الأسبوع، سواء كانت استفسارًا أو ملاحظة أو شكوى.",
        "channels_h": "قنوات التواصل",
        "addr_h": "العنوان",
        "complaints_h": "تقديم شكوى",
        "complaints_promise": "نستقبل الشكاوى على مدار الساعة طوال أيام الأسبوع، ونرد عليها خلال 24 ساعة كحد أقصى.",
        "complaints_how": "أرسل شكواك إلى {email_link} بعنوان «شكوى»، واذكر فيها قدر الإمكان:",
        "complaints_fields": [
            "اسمك ووسيلة التواصل معك.",
            "رقم الحجز في Airbnb إن وُجد، واسم الشقة وتاريخ الإقامة.",
            "وصفًا للمشكلة، وما تتوقعه منا لحلها.",
        ],
        "steps_h": "ماذا يحدث بعد ذلك",
        "steps": [
            "نؤكد استلام شكواك.",
            "يراجعها المختص في فريقنا ويتواصل معك إن احتاج إلى تفاصيل إضافية.",
            "نرد عليك بالحل أو الإجراء المتخذ خلال 24 ساعة كحد أقصى.",
        ],
        "escalate": "إذا كانت الشكوى تتعلق بحجز تم عبر Airbnb، فيمكنك أيضًا التواصل مع دعم Airbnb. ويحق لك رفع شكواك إلى الجهات الرسمية المختصة.",
        "mail_subject": "شكوى",
    },
    "en": {
        "title": "Contact and Complaints · Ouja Residence",
        "desc": "Contact Ouja Residence or make a complaint. We receive complaints around the clock and reply within 24 hours at most.",
        "h1": "Contact and Complaints",
        "intro": "We receive your messages around the clock, seven days a week — whether it is a question, a note or a complaint.",
        "channels_h": "How to reach us",
        "addr_h": "Address",
        "complaints_h": "Making a complaint",
        "complaints_promise": "We receive complaints around the clock, seven days a week, and reply within 24 hours at most.",
        "complaints_how": "Send your complaint to {email_link} with the subject “Complaint”, and include as much as you can of:",
        "complaints_fields": [
            "Your name and how to reach you.",
            "Your Airbnb booking number if you have one, the apartment name and the dates of your stay.",
            "A description of the problem, and what you expect from us to resolve it.",
        ],
        "steps_h": "What happens next",
        "steps": [
            "We confirm that we received your complaint.",
            "The responsible member of our team reviews it and contacts you if more detail is needed.",
            "We reply with the resolution or the action taken within 24 hours at most.",
        ],
        "escalate": "If your complaint concerns a booking made through Airbnb, you can also contact Airbnb support. You also have the right to take your complaint to the competent official authorities.",
        "mail_subject": "Complaint",
    },
}
