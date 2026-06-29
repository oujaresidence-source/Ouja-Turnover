# brain/playbook.py
# Ouja Elite — 20 WhatsApp campaign templates (Meta/Karzoun-ready, bilingual).
# Copy is verbatim from the OUJA WhatsApp Conversion & Template Playbook (research).
# Variables: {{1}}=first name  {{2}}=unit/tier  {{3}}=night/date  {{4}}=access/upgrade/value  {{5}}=hold-until
# Rules baked in: zero emoji default, one *bold* element, one quick-reply button, opt-out footer on Marketing.
# F1/F2 protected (UPGRADE-MIDWEEK, TURAIF-MIDWEEK): access/upgrade only — never a price cut.
#
# ENGINE NOTE (Weekday-Gap Engine): the bilingual *copy* and the Meta-template metadata
# (template_name / category / ar/en blocks / samples / approval_note / protected / utility_variant)
# live in CAMPAIGNS below — this file is the single source of truth for the message text.
# The structural fields the decision engine reads (filter / offer_mode / fires_on / why / display
# names / tier_focus) are merged on at import time from _STRUCT, so brain.cards keeps reading
# playbook.CAMPAIGNS[code] exactly as before — only the message body now carries the {{1}}..{{5}}
# Karzoun variables instead of the old {name}/{unit}/{dates} tokens.

OPT_OUT_AR = "للإيقاف أرسل: إيقاف"
OPT_OUT_EN = "Reply STOP to opt out"

CAMPAIGNS = {

"TONIGHT": {
    "template_name": "tonight_unit_quiet",
    "category": "MARKETING",
    "principle": "Honest scarcity + liking",
    "ar": {"header": "ليلة هادئة الليلة",
            "body": "هلا {{1}}، شفت إن *{{2}}* فاضية الليلة فحبيت أخبرك أول واحد. خليناها لك بسعر هادئ خاص لو ودك تمر علينا الليلة بس. أقولهم يجهزونها؟",
            "footer": OPT_OUT_AR, "button": "جهزوها لي"},
    "en": {"header": "A quiet night tonight",
            "body": "Hi {{1}}, *{{2}}* happens to be free tonight, so I wanted you to hear it first. We've kept a quiet rate on it for you, just for tonight. Want me to have it ready?",
            "footer": OPT_OUT_EN, "button": "Hold it for me"},
    "sample_ar": {"1": "نورة", "2": "شقة تريف ٢"},
    "sample_en": {"1": "Noura", "2": "Turaif Apt 2"},
    "approval_note": "Single marketing intent, name + context, opt-out present, no banner language.",
},

"TOMORROW": {
    "template_name": "tomorrow_unit_open",
    "category": "MARKETING",
    "principle": "Anticipation / timeliness",
    "ar": {"header": "بكرة عندنا مكان لك",
            "body": "هلا {{1}}، بكرة *{{3}}* عندنا *{{2}}* جاهزة لك لو حابب تنام عندنا ليلة وسط الأسبوع. حجزتها باسمك مبدئياً لين {{5}}. أثبّتها؟",
            "footer": OPT_OUT_AR, "button": "أثبّتها"},
    "en": {"header": "We've got space for you tomorrow",
            "body": "Hi {{1}}, for *{{3}}* tomorrow we have *{{2}}* ready for you if you'd like a midweek night with us. I've pencilled it in under your name until {{5}}. Lock it in?",
            "footer": OPT_OUT_EN, "button": "Lock it in"},
    "sample_ar": {"1": "فهد", "2": "شقة العليا", "3": "الإثنين", "5": "الساعة ٦ مساءً"},
    "sample_en": {"1": "Fahad", "2": "Olaya Apt", "3": "Monday", "5": "6 PM"},
    "approval_note": "One intent, fixed context around variables, ends on static text.",
},

"ORPHAN-NIGHT": {
    "template_name": "orphan_single_night",
    "category": "MARKETING",
    "principle": "Reciprocity",
    "ar": {"header": "ليلة وحدة بقت لنا",
            "body": "هلا {{1}}، عندنا ليلة وحدة بس *{{3}}* في *{{2}}* قبل ما ترجع محجوزة. حبيناها تكون لك بسعر ودّي بدل ما تبقى فاضية. تبيها؟",
            "footer": OPT_OUT_AR, "button": "إيه تكفى"},
    "en": {"header": "One night left with us",
            "body": "Hi {{1}}, we have just one night open, *{{3}}*, in *{{2}}* before it books up again. We'd rather it went to you at a friendly rate than sit empty. Yours?",
            "footer": OPT_OUT_EN, "button": "Yes please"},
    "sample_ar": {"1": "سارة", "2": "شقة الياسمين", "3": "الثلاثاء"},
    "sample_en": {"1": "Sara", "2": "Yasmin Apt", "3": "Tuesday"},
    "approval_note": "Genuine single-night scarcity, no false urgency, opt-out present.",
},

"MIDWEEK-2": {
    "template_name": "midweek_two_nights",
    "category": "MARKETING",
    "principle": "Consistency",
    "ar": {"header": "ليلتينك المعتادتين",
            "body": "هلا {{1}}، عادتك تنام عندنا ليلتين وسط الأسبوع، و*{{2}}* فاضية *{{3}}*. جهزتها لك ليلتين متواصلتين لو يناسبك. أرتّبها؟",
            "footer": OPT_OUT_AR, "button": "رتّبها لي"},
    "en": {"header": "Your usual two nights",
            "body": "Hi {{1}}, you usually take two midweek nights with us, and *{{2}}* is open *{{3}}*. I've set it up as your two-night stay if it suits. Shall I arrange it?",
            "footer": OPT_OUT_EN, "button": "Arrange it"},
    "sample_ar": {"1": "عبدالله", "2": "شقة الملقا", "3": "الأحد والإثنين"},
    "sample_en": {"1": "Abdullah", "2": "Malqa Apt", "3": "Sun–Mon"},
    "approval_note": "Personalized to past pattern, single offer, ends on static text.",
},

"LONG-GAP": {
    "template_name": "long_gap_stretch",
    "category": "MARKETING",
    "principle": "Reciprocity / value",
    "ar": {"header": "فترة هادئة تناسبك",
            "body": "هلا {{1}}، عندنا فترة هادئة في *{{2}}* من *{{3}}*، ولو حابب تمددها أكثر من ليلة سوّينا لك سعر أهدى للفترة كلها. أحسبها لك؟",
            "footer": OPT_OUT_AR, "button": "احسبها لي"},
    "en": {"header": "A quiet stretch for you",
            "body": "Hi {{1}}, there's a quiet stretch in *{{2}}* from *{{3}}*, and if you'd like more than a night we've made the whole stretch a softer rate for you. Want me to price it?",
            "footer": OPT_OUT_EN, "button": "Price it for me"},
    "sample_ar": {"1": "ريم", "2": "شقة قرطبة", "3": "الأحد إلى الأربعاء"},
    "sample_en": {"1": "Reem", "2": "Qurtuba Apt", "3": "Sun–Wed"},
    "approval_note": "One offer, no exclamation/banner, opt-out present.",
},

"THIS-WEEK": {
    "template_name": "this_week_midweek",
    "category": "MARKETING",
    "principle": "Timeliness / availability",
    "ar": {"header": "مكان لك هالأسبوع",
            "body": "هلا {{1}}، لو ناوي تغيّر جوّك ليلة وسط هالأسبوع، *{{2}}* فاضية *{{3}}* وجاهزة لك. أحجزها باسمك؟",
            "footer": OPT_OUT_AR, "button": "احجزها لي"},
    "en": {"header": "A spot for you this week",
            "body": "Hi {{1}}, if you fancy a change of scene midweek, *{{2}}* is free *{{3}}* and ready for you. Shall I book it under your name?",
            "footer": OPT_OUT_EN, "button": "Book it for me"},
    "sample_ar": {"1": "ماجد", "2": "شقة النخيل", "3": "الثلاثاء أو الأربعاء"},
    "sample_en": {"1": "Majed", "2": "Nakheel Apt", "3": "Tue or Wed"},
    "approval_note": "Simple, single-intent invite, opt-out present.",
},

"LAST-CHANCE": {
    "template_name": "last_chance_tonight",
    "category": "MARKETING",
    "principle": "Honest scarcity (real cut-off)",
    "ar": {"header": "قبل ما نقفل الليلة",
            "body": "هلا {{1}}، *{{2}}* لسة محجوزة لك لين {{5}} الليلة، وبعدها نفتحها لغيرك. ما ودي تفوتك لو كنت ناوي. أثبّتها لك؟",
            "footer": OPT_OUT_AR, "button": "أثبّتها"},
    "en": {"header": "Before we release it tonight",
            "body": "Hi {{1}}, *{{2}}* is still held for you until {{5}} tonight, after which we open it to others. I didn't want you to miss it if you were planning to come. Lock it in?",
            "footer": OPT_OUT_EN, "button": "Lock it in"},
    "sample_ar": {"1": "نوف", "2": "شقة الورود", "5": "الساعة ٩ مساءً"},
    "sample_en": {"1": "Nouf", "2": "Wurood Apt", "5": "9 PM"},
    "approval_note": "Deadline real and softly worded, one intent, opt-out.",
},

"YOUR-UNIT-FREE": {
    "template_name": "your_usual_unit_free",
    "category": "MARKETING",
    "principle": "Endowment / personalization",
    "ar": {"header": "وحدتك المعتادة فاضية",
            "body": "هلا {{1}}، *{{2}}*، اللي تحبها، فاضية *{{3}}*. عرفت إنك ترتاح فيها أكثر فخليتها لك. أجهزها على ذوقك؟",
            "footer": OPT_OUT_AR, "button": "جهزها لي"},
    "en": {"header": "Your usual place is open",
            "body": "Hi {{1}}, *{{2}}*, the one you like, is free *{{3}}*. I know you settle in best there, so I kept it for you. Set it up just the way you like?",
            "footer": OPT_OUT_EN, "button": "Set it up"},
    "sample_ar": {"1": "خالد", "2": "شقة الياسمين ٥", "3": "الإثنين"},
    "sample_en": {"1": "Khalid", "2": "Yasmin Apt 5", "3": "Monday"},
    "approval_note": "Anticipatory + personal, single offer, opt-out.",
},

"SIMILAR-UNIT": {
    "template_name": "similar_unit_suggestion",
    "category": "MARKETING",
    "principle": "Liking / social proof",
    "ar": {"header": "وحدة قريبة من ذوقك",
            "body": "هلا {{1}}، *{{4}}* محجوزة *{{3}}*، بس عندي *{{2}}* قريبة منها بنفس الجو والموقع وضيوفنا يحبونها. أرتّبها لك بدالها؟",
            "footer": OPT_OUT_AR, "button": "أرتّبها"},
    "en": {"header": "One close to your taste",
            "body": "Hi {{1}}, *{{4}}* is taken *{{3}}*, but I have *{{2}}* nearby with the same feel and location, and our guests love it. Shall I set that one up for you instead?",
            "footer": OPT_OUT_EN, "button": "Set it up"},
    "sample_ar": {"1": "لمى", "2": "شقة العليا ٣", "3": "الثلاثاء", "4": "شقتك المعتادة"},
    "sample_en": {"1": "Lama", "2": "Olaya Apt 3", "3": "Tuesday", "4": "your usual apartment"},
    "approval_note": "One alternative offer, honest social proof, opt-out.",
},

"WELCOME-BACK": {
    "template_name": "welcome_back_member",
    "category": "MARKETING",
    "principle": "Liking / belonging",
    "ar": {"header": "نورتنا من جديد",
            "body": "هلا {{1}}، وحشتنا والله. لو ناوي تمر علينا ليلة وسط الأسبوع، *{{2}}* جاهزة لك وعلى راسنا. تبي أرتّب لك *{{3}}*؟",
            "footer": OPT_OUT_AR, "button": "رتّب لي"},
    "en": {"header": "Good to have you back",
            "body": "Hi {{1}}, we've genuinely missed having you. If you fancy a midweek night, *{{2}}* is ready and you're always welcome. Want me to set up *{{3}}* for you?",
            "footer": OPT_OUT_EN, "button": "Set it up"},
    "sample_ar": {"1": "طلال", "2": "شقة الملقا", "3": "الأحد"},
    "sample_en": {"1": "Talal", "2": "Malqa Apt", "3": "Sunday"},
    "approval_note": "Warm re-engagement (Marketing), single soft offer, opt-out.",
},

"WIN-BACK": {
    "template_name": "win_back_lapsed",
    "category": "MARKETING",
    "principle": "Reciprocity + gentle curiosity",
    "ar": {"header": "صار لنا فترة ما شفناك",
            "body": "هلا {{1}}، صار لنا زمن ما نوّرتنا. حبيت بس أطمّن عليك وأقولك إن بابنا مفتوح لك في أي ليلة وسط الأسبوع، وجهزنا لك *{{2}}* لو تحب ترجع. أرتّب لك ليلة؟",
            "footer": OPT_OUT_AR, "button": "رتّب لي ليلة"},
    "en": {"header": "It's been a while",
            "body": "Hi {{1}}, it's been a while since you stayed with us, and I just wanted to check in. Our door's open any midweek night, and I've kept *{{2}}* ready in case you'd like to come back. Set a night up for you?",
            "footer": OPT_OUT_EN, "button": "Set a night up"},
    "sample_ar": {"1": "هند", "2": "شقة قرطبة"},
    "sample_en": {"1": "Hind", "2": "Qurtuba Apt"},
    "approval_note": "Re-engagement = Marketing; warm, no pressure, opt-out.",
},

"WEEKDAY-REGULAR": {
    "template_name": "weekday_regular_recognition",
    "category": "MARKETING",
    "principle": "Consistency / recognition",
    "ar": {"header": "لك دلّتك عندنا",
            "body": "هلا {{1}}، إنت من أوفى ضيوفنا وسط الأسبوع، ودايم نحب نشوفك. *{{2}}* فاضية *{{3}}* وحجزناها لك أول، تقديراً لك. أثبّتها؟",
            "footer": OPT_OUT_AR, "button": "أثبّتها"},
    "en": {"header": "You're one of our regulars",
            "body": "Hi {{1}}, you're one of our most loyal midweek guests and we always love having you. *{{2}}* is free *{{3}}*, and we held it for you first, as a thank-you. Lock it in?",
            "footer": OPT_OUT_EN, "button": "Lock it in"},
    "sample_ar": {"1": "بدر", "2": "شقة النخيل ٢", "3": "الإثنين"},
    "sample_en": {"1": "Badr", "2": "Nakheel Apt 2", "3": "Monday"},
    "approval_note": "Recognition + single offer, opt-out.",
},

"POST-CHECKOUT": {
    "template_name": "post_checkout_thanks_offer",      # default (Marketing)
    "template_name_utility": "post_checkout_thanks",     # Utility variant
    "category": "MARKETING",
    "utility_variant": True,
    "principle": "Reciprocity / gratitude (fond farewell)",
    # default = Marketing variant
    "ar": {"header": "شكراً لإقامتك",
            "body": "هلا {{1}}، شكراً إنك اخترت أوجا في *{{2}}*. إن حبيت ليلة هادئة وسط الأسبوع المرة الجاية، خلنا نعرف ونجهز لك مكانك. تشرفنا فيك.",
            "footer": OPT_OUT_AR, "button": "ليلة وسط الأسبوع"},
    "en": {"header": "Thank you for staying",
            "body": "Hi {{1}}, thank you for choosing Ouja at *{{2}}*. Whenever you'd like a quiet midweek night again, just say the word and we'll have your place ready. It was a pleasure having you.",
            "footer": OPT_OUT_EN, "button": "A midweek night"},
    "ar_utility": {"header": "شكراً لإقامتك",
            "body": "هلا {{1}}، شكراً إنك اخترت أوجا في إقامتك بـ*{{2}}* اللي خلصت *{{3}}*. إن احتجت أي شي بعد مغادرتك إحنا حاضرين. نتمنى نشوفك قريب.",
            "footer": None, "button": None},
    "en_utility": {"header": "Thank you for staying",
            "body": "Hi {{1}}, thank you for choosing Ouja for your stay at *{{2}}*, which ended *{{3}}*. If you need anything after checkout, we're here. We hope to see you again soon.",
            "footer": None, "button": None},
    "sample_ar": {"1": "علي", "2": "شقة العليا", "3": "اليوم"},
    "sample_en": {"1": "Ali", "2": "Olaya Apt", "3": "today"},
    "approval_note": "Utility variant: specific completed stay, no offer. Marketing variant: soft nudge + opt-out.",
},

"UPGRADE-MIDWEEK": {  # F1/F2 protected — upgrade/access only, never a price cut
    "template_name": "upgrade_midweek_access",
    "category": "MARKETING",
    "protected": True,
    "principle": "Reciprocity + exclusivity-by-access",
    "ar": {"header": "ترقية لك على حسابنا",
            "body": "هلا {{1}}، حجزك وسط الأسبوع يعطينا فرصة نرقّيك. نقدر ننقلك إلى *{{4}}* بدون أي فرق بالسعر، هدية منّا، لو حابب *{{3}}*. تبي أرتّب لك الترقية؟",
            "footer": OPT_OUT_AR, "button": "أبي الترقية"},
    "en": {"header": "An upgrade, on us",
            "body": "Hi {{1}}, your midweek stay gives us a chance to treat you. We'd love to move you up to *{{4}}* at no extra cost, our gift, if you'd like *{{3}}*. Shall I arrange the upgrade?",
            "footer": OPT_OUT_EN, "button": "Yes, upgrade me"},
    "sample_ar": {"1": "منيرة", "3": "الأحد", "4": "وحدة F2 المميزة"},
    "sample_en": {"1": "Munira", "3": "Sunday", "4": "our premium F2 unit"},
    "approval_note": "Complimentary upgrade, no price-cut language, one intent, opt-out.",
},

"TURAIF-MIDWEEK": {  # top tier; F1/F2 access — no price cut
    "template_name": "turaif_midweek_access",
    "category": "MARKETING",
    "protected": True,
    "principle": "Exclusivity / status-by-access",
    "ar": {"header": "خاص لضيوف تريف",
            "body": "هلا {{1}}، لأنك من ضيوف تريف، حجزنا لك دخول مبكر ووحدتنا المميزة *{{4}}* وسط الأسبوع، واختر وقت دخولك اللي يناسبك. كل هذا بدون أي فرق بالسعر. أرتّب لك *{{3}}*؟",
            "footer": OPT_OUT_AR, "button": "رتّب لي"},
    "en": {"header": "For our Turaif guests",
            "body": "Hi {{1}}, as a Turaif guest we've set aside early check-in, our premium *{{4}}* midweek, and your choice of arrival time, all at no change to your rate. Shall I arrange *{{3}}* for you?",
            "footer": OPT_OUT_EN, "button": "Arrange it"},
    "sample_ar": {"1": "فيصل", "3": "الإثنين", "4": "وحدة F1"},
    "sample_en": {"1": "Faisal", "3": "Monday", "4": "F1 unit"},
    "approval_note": "Status framed as access, zero discount on protected unit, single intent, opt-out.",
},

"OCCASION-MIDWEEK": {
    "template_name": "occasion_midweek",
    "category": "MARKETING",
    "principle": "Anticipatory service",
    "ar": {"header": "مناسبتك تستاهل",
            "body": "هلا {{1}}، قربت *{{4}}*، مبارك لك مقدماً. لو حابب تحتفل بهدوء وسط الأسبوع، نجهز لك *{{2}}* ولمسة بسيطة على ذوقك. أرتّب لك *{{3}}*؟",
            "footer": OPT_OUT_AR, "button": "أرتّب لك"},
    "en": {"header": "Your occasion deserves it",
            "body": "Hi {{1}}, *{{4}}* is coming up, congratulations in advance. If you'd like to mark it quietly midweek, we'll have *{{2}}* ready with a small touch we think you'll like. Shall I arrange *{{3}}*?",
            "footer": OPT_OUT_EN, "button": "Please arrange"},
    "sample_ar": {"1": "أحمد", "2": "شقة الياسمين", "3": "الثلاثاء", "4": "مناسبتك"},
    "sample_en": {"1": "Ahmed", "2": "Yasmin Apt", "3": "Tuesday", "4": "your occasion"},
    "approval_note": "Personal, single invitation, no banner, opt-out.",
},

"LONG-STAY-MIDWEEK": {
    "template_name": "long_stay_midweek",
    "category": "MARKETING",
    "principle": "Reciprocity / value",
    "ar": {"header": "إقامة أطول، راحة أكثر",
            "body": "هلا {{1}}، لو ناوي تطوّل عندنا وسط الأسبوع، نقدر نجهز لك *{{2}}* من *{{3}}* مع ترتيب أهدى للإقامة كاملة وراحة إضافية. أحسبها لك؟",
            "footer": OPT_OUT_AR, "button": "احسبها لي"},
    "en": {"header": "A longer, easier stay",
            "body": "Hi {{1}}, if you'd like to settle in for a longer midweek stay, we can set up *{{2}}* from *{{3}}* with a softer arrangement across the whole stay and a little extra comfort. Want me to price it?",
            "footer": OPT_OUT_EN, "button": "Price it"},
    "sample_ar": {"1": "وليد", "2": "شقة الملقا", "3": "الأحد إلى الأربعاء"},
    "sample_en": {"1": "Waleed", "2": "Malqa Apt", "3": "Sun–Wed"},
    "approval_note": "Single multi-night offer, no shouting, opt-out.",
},

"CORPORATE-WEEKDAY": {
    "template_name": "corporate_weekday",
    "category": "MARKETING",
    "principle": "Authority / utility framing",
    "ar": {"header": "لرحلات العمل وسط الأسبوع",
            "body": "هلا {{1}}، لرحلات العمل وسط الأسبوع، نقدر نثبّت لك *{{2}}* بترتيب ثابت للشركة وفاتورة واضحة ودخول مرن. لو عندك ليالي *{{3}}*، نرتّبها لك بسهولة. أبدأ معك؟",
            "footer": OPT_OUT_AR, "button": "ابدأ معي"},
    "en": {"header": "For midweek work trips",
            "body": "Hi {{1}}, for midweek business trips we can hold *{{2}}* for you with a steady corporate arrangement, clear invoicing and flexible check-in. If you have *{{3}}* nights, we'll set them up easily. Shall I start?",
            "footer": OPT_OUT_EN, "button": "Let's start"},
    "sample_ar": {"1": "أستاذ سعود", "2": "شقة العليا", "3": "الأحد–الأربعاء"},
    "sample_en": {"1": "Mr. Saud", "2": "Olaya Apt", "3": "Sun–Wed"},
    "approval_note": "Promotional B2B offer = Marketing; single intent, clear value, opt-out.",
},

"ELITE-NUDGE": {
    "template_name": "elite_member_nudge",
    "category": "MARKETING",
    "principle": "Belonging / unity",
    "ar": {"header": "بابك المباشر معنا",
            "body": "هلا {{1}}، لأنك من ضيوف أوجا المميزين، الحجز المباشر معنا يوفّر لك رسوم المنصّات ويخليك أقرب لنا. عندنا *{{2}}* فاضية *{{3}}* لو تحب نجهزها لك مباشرة. أرتّبها؟",
            "footer": OPT_OUT_AR, "button": "أرتّبها مباشرة"},
    "en": {"header": "Your direct line to us",
            "body": "Hi {{1}}, as one of our Elite guests, booking direct with us saves the platform fees and keeps you closer to us. *{{2}}* is open *{{3}}* if you'd like us to set it up directly. Shall I arrange it?",
            "footer": OPT_OUT_EN, "button": "Book direct"},
    "sample_ar": {"1": "دانة", "2": "شقة قرطبة", "3": "الإثنين"},
    "sample_en": {"1": "Dana", "2": "Qurtuba Apt", "3": "Monday"},
    "approval_note": "Direct/platform-fee-saving framing; single intent, opt-out.",
},

"REVIEW-TO-REBOOK": {
    "template_name": "review_to_rebook",                 # default (Marketing)
    "template_name_utility": "review_specific_stay",      # Utility variant
    "category": "MARKETING",
    "utility_variant": True,
    "principle": "Consistency + reciprocity",
    "ar": {"header": "شكراً على كلامك الطيب",
            "body": "هلا {{1}}، سعدنا بكلامك الطيب عن *{{2}}*. لو حابب ترجع لنا ليلة هادئة وسط الأسبوع، نجهزها لك بنفس المكان أو وحدة قريبة. أرتّب لك *{{3}}*؟",
            "footer": OPT_OUT_AR, "button": "أرتّب لي"},
    "en": {"header": "Thank you for your kind words",
            "body": "Hi {{1}}, we loved your kind words about *{{2}}*. If you'd like to come back for a quiet midweek night, we'll set up the same place or one nearby. Shall I arrange *{{3}}*?",
            "footer": OPT_OUT_EN, "button": "Arrange it"},
    "ar_utility": {"header": "كيف كانت إقامتك؟",
            "body": "هلا {{1}}، كيف كانت إقامتك في *{{2}}* يوم *{{3}}*؟ رأيك يهمنا ويساعدنا نخدمك أحسن. لو في أي ملاحظة، إحنا نسمع لك.",
            "footer": None, "button": None},
    "en_utility": {"header": "How was your stay?",
            "body": "Hi {{1}}, how was your stay at *{{2}}* on *{{3}}*? Your feedback genuinely helps us serve you better, and if anything was off, we want to hear it.",
            "footer": None, "button": None},
    "sample_ar": {"1": "يوسف", "2": "شقة النخيل", "3": "السبت الماضي"},
    "sample_en": {"1": "Yousef", "2": "Nakheel Apt", "3": "last Saturday"},
    "approval_note": "Utility variant: stay-specific, no offer. Marketing variant: rebook + opt-out.",
},

}


# ===========================================================================
# ENGINE SCAFFOLDING — structural metadata the Weekday-Gap decision engine reads.
# This is NOT message copy (the copy lives in CAMPAIGNS above); these are the per-campaign
# targeting filter, offer mode, gap-class trigger, display names, the why-line template and the
# audience tier_focus. Merged onto each CAMPAIGNS record below so brain.cards keeps reading
# playbook.CAMPAIGNS[code] unchanged. Keys match CAMPAIGNS 1:1 (see _selftest at bottom).
#
# Targeting filter keys (interpreted by brain.cards; absent signals degrade to no-op):
#   tier_min / tier_only / weekday_pattern / days_since_max/min / score_min / stays_min /
#   nights_min / preferred_match / preferred_boost / corporate / prospect_ok
# offer_mode: relationship (no discount) | value_add (≤ceiling% direct) | deeper | upgrade
#   (protected units: access/upgrade, never a price cut — a protected unit ALWAYS forces upgrade).
# ===========================================================================
_STRUCT = {
    "TONIGHT": {
        "name_ar": "الليلة", "name_en": "Tonight",
        "fires_on": ["TONIGHT"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver", "days_since_max": 120},
        "tier_focus": "any (last-minute bookers first)",
        "why_ar": "فاضية الليلة في {unit}؛ {n} ضيوف منتظمين يحجزون بسرعة وما تواصلنا معهم من {d} يوم.",
        "why_en": "Empty tonight on {unit}; {n} last-minute midweek regulars, not contacted in {d}d.",
    },
    "TOMORROW": {
        "name_ar": "بكرة", "name_en": "Tomorrow",
        "fires_on": ["TOMORROW"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver", "days_since_max": 150},
        "tier_focus": "last-minute repeaters",
        "why_ar": "فاضية بكرة في {unit}؛ نعرضها أول على {n} من أسرع الضيوف ردًّا.",
        "why_en": "Free tomorrow on {unit}; offering first to {n} fast-responders.",
    },
    "ORPHAN-NIGHT": {
        "name_ar": "ليلة يتيمة", "name_en": "Orphan night",
        "fires_on": ["ORPHAN-NIGHT"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver", "preferred_boost": True, "days_since_max": 150},
        "tier_focus": "last-minute, local repeaters",
        "why_ar": "ليلة {wd} وحيدة بين حجزين في {unit}؛ {n} منتظمين غالبًا ياخذونها.",
        "why_en": "Single {wd} night between two bookings on {unit}; {n} regulars likely to grab it.",
    },
    "MIDWEEK-2": {
        "name_ar": "ليلتين منتصف الأسبوع", "name_en": "Midweek two-night",
        "fires_on": ["MIDWEEK-2"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver"},
        "tier_focus": "Gold weekday regulars",
        "why_ar": "فجوة ليلتين منتصف الأسبوع في {unit}؛ {n} ضيوف ذهبيين منتظمين بالأيام العادية.",
        "why_en": "Two-night midweek gap on {unit}; {n} Gold weekday regulars.",
    },
    "LONG-GAP": {
        "name_ar": "فجوة طويلة", "name_en": "Long gap",
        "fires_on": ["LONG-GAP"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver", "nights_min": 3},
        "tier_focus": "long-stay history, corporate",
        "why_ar": "فترة {nights} ليالٍ منتصف الأسبوع في {unit}؛ {n} ضيوف إقامات طويلة.",
        "why_en": "{nights}-night midweek stretch on {unit}; {n} long-stay guests.",
    },
    "THIS-WEEK": {
        "name_ar": "هالأسبوع", "name_en": "This week",
        "fires_on": ["THIS-WEEK"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver"},
        "tier_focus": "Gold + trusted repeaters",
        "why_ar": "ليالي منتصف الأسبوع مفتوحة في {unit}؛ {n} منتظمين موثوقين.",
        "why_en": "Open midweek nights on {unit}; {n} trusted regulars.",
    },
    "LAST-CHANCE": {
        "name_ar": "آخر فرصة", "name_en": "Last chance",
        "fires_on": ["LAST-CHANCE"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver"},
        "tier_focus": "prior non-responders only",
        "why_ar": "نداء أخير على {unit} {wd}؛ {n} ما ردّوا بعد.",
        "why_en": "Final call on {unit} {wd}; {n} who didn't reply yet.",
    },
    "YOUR-UNIT-FREE": {
        "name_ar": "شقتك المفضلة فاضية", "name_en": "Your unit is free",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"preferred_match": True},
        "tier_focus": "the repeater (any tier)",
        "why_ar": "شقتهم المفضّلة {unit} فاضية يوم {wd} المعتاد؛ {n} أوفياء — علاقة بدون خصم.",
        "why_en": "Their favourite {unit} is open on their usual {wd}; {n} loyalists — relationship, no discount.",
    },
    "SIMILAR-UNIT": {
        "name_ar": "شقة مشابهة", "name_en": "Similar unit",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"tier_min": "Silver"},
        "tier_focus": "repeater whose unit is booked",
        "why_ar": "شقتهم المعتادة محجوزة؛ {unit} قريبة منها بنفس المنطقة وفاضية منتصف الأسبوع.",
        "why_en": "Their usual is taken; {unit} is a close match and open midweek.",
    },
    "WELCOME-BACK": {
        "name_ar": "وحشتنا", "name_en": "Welcome back",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"days_since_min": 60, "days_since_max": 120, "score_min": 50, "prospect_ok": True},
        "tier_focus": "dormant 60–120d, score ≥50",
        "why_ar": "{n} ضيوف طيبين هدّوا من شهرين لأربعة؛ دعوة لطيفة منتصف الأسبوع.",
        "why_en": "{n} good guests quiet 2–4 months; gentle midweek invite.",
    },
    "WIN-BACK": {
        "name_ar": "نرجّعك", "name_en": "Win back",
        "fires_on": ["ANY"], "offer_mode": "value_add",
        "filter": {"days_since_min": 120, "days_since_max": 365, "score_min": 50, "prospect_ok": True},
        "tier_focus": "dormant 120–365d, score ≥50",
        "why_ar": "{n} ضيوف طيبين غابوا من ٤ شهور لسنة؛ دعوة أقوى لمرة وحدة منتصف الأسبوع.",
        "why_en": "{n} lapsed good guests; stronger one-time midweek invite.",
    },
    "WEEKDAY-REGULAR": {
        "name_ar": "منتظم منتصف الأسبوع", "name_en": "Weekday regular",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"weekday_pattern": True, "stays_min": 3},
        "tier_focus": "weekday_pattern, stays ≥3",
        "why_ar": "{n} يحجزون دائمًا منتصف الأسبوع؛ {unit} فاضية {wd}.",
        "why_en": "{n} who always book midweek; {unit} open {wd}.",
    },
    "POST-CHECKOUT": {
        "name_ar": "بعد المغادرة", "name_en": "Post-checkout",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"days_since_max": 2, "score_min": 50},
        "tier_focus": "checked out ≤2d, happy",
        "why_ar": "ضيوف غادروا للتو ومبسوطين؛ دعوة لطيفة «ارجع منتصف الأسبوع».",
        "why_en": "Just-departed happy guests; soft 'come back midweek'.",
    },
    "UPGRADE-MIDWEEK": {
        "name_ar": "ترقية منتصف الأسبوع", "name_en": "Midweek upgrade",
        "fires_on": ["PROTECTED"], "offer_mode": "upgrade",
        "filter": {"tier_min": "Gold"},
        "tier_focus": "in-house / eligible; protected units upgrade-only",
        "why_ar": "{unit} (محميّة) فاضية {wd}؛ نعرض ترقية، بدون أي تخفيض سعر.",
        "why_en": "{unit} (protected) empty {wd}; offer upgrade, never a price cut.",
    },
    "TURAIF-MIDWEEK": {
        "name_ar": "تُرَيف منتصف الأسبوع", "name_en": "Turaif midweek",
        "fires_on": ["PROTECTED", "PREMIUM"], "offer_mode": "upgrade",
        "filter": {"tier_only": "Turaif"},
        "tier_focus": "Turaif only",
        "why_ar": "فجوة {wd} مميّزة في {unit}؛ ترتيب هادئ خاص لـ {n} من ضيوف تُرَيف.",
        "why_en": "Premium {wd} gap on {unit}; private quiet rate for {n} Turaif.",
    },
    "OCCASION-MIDWEEK": {
        "name_ar": "مناسبة منتصف الأسبوع", "name_en": "Occasion midweek",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"tier_min": "Silver"},
        "tier_focus": "repeaters; personalize if date known",
        "why_ar": "مناسبة تصادف منتصف الأسبوع؛ دعوة مخصّصة لـ {n} منتظمين.",
        "why_en": "An occasion falls midweek; themed invite to {n} regulars.",
    },
    "LONG-STAY-MIDWEEK": {
        "name_ar": "إقامة طويلة منتصف الأسبوع", "name_en": "Long-stay midweek",
        "fires_on": ["LONG-GAP"], "offer_mode": "value_add",
        "filter": {"nights_min": 3, "stays_min": 2},
        "tier_focus": "long-stay seekers",
        "why_ar": "فجوة طويلة منتصف الأسبوع في {unit}؛ ترتيب إقامة طويلة لـ {n} ضيوف.",
        "why_en": "Long midweek gap on {unit}; long-stay rate to {n}.",
    },
    "CORPORATE-WEEKDAY": {
        "name_ar": "شركات منتصف الأسبوع", "name_en": "Corporate weekday",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"corporate": True, "stays_min": 3},
        "tier_focus": "corporate_pattern",
        "why_ar": "{n} ضيوف بنمط أعمال؛ ترتيب أيام أسبوع ثابت.",
        "why_en": "{n} business-pattern guests; fixed weekday arrangement.",
    },
    "ELITE-NUDGE": {
        "name_ar": "ترحيب إيليت", "name_en": "Elite nudge",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"tier_only": "Silver", "stays_min": 2},
        "tier_focus": "Silver, 2 stays, not enrolled",
        "why_ar": "{n} منتظمين جدد نرحّب فيهم بنادي إيليت (مكانة، بدون خصم).",
        "why_en": "{n} new-ish regulars to welcome into Elite (status, no discount).",
    },
    "REVIEW-TO-REBOOK": {
        "name_ar": "تقييم ثم حجز", "name_en": "Review to rebook",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"days_since_max": 3, "score_min": 50},
        "tier_focus": "recent happy guests",
        "why_ar": "ضيوف غادروا للتو ومبسوطين؛ طلب تقييم + إعادة حجز منتصف الأسبوع بسهولة.",
        "why_en": "Recent happy guests; review request + easy midweek rebook.",
    },
}

# Merge the structural metadata + the {{1}}..{{5}} message body onto each campaign record so the
# engine reads playbook.CAMPAIGNS[code] exactly as before (msg_ar/msg_en/filter/offer_mode/why/…).
for _code, _st in _STRUCT.items():
    _c = CAMPAIGNS.get(_code)
    if _c is None:
        continue
    for _k, _v in _st.items():
        _c[_k] = _v                       # struct fields never collide with catalogue keys
    # message body the engine merges + sends comes from the Marketing AR/EN block (default variant)
    _c["msg_ar"] = (_c.get("ar") or {}).get("body", "")
    _c["msg_en"] = (_c.get("en") or {}).get("body", "")


# Tier ordering for tier_min comparisons.
TIER_RANK = {"Prospect": 0, "Silver": 1, "Gold": 2, "Turaif": 3, "Quarantine": -1}

# Gap class -> the campaign pushed by default (build spec §4 spine).
CLASS_PRIMARY = {
    "TONIGHT": "TONIGHT", "TOMORROW": "TOMORROW", "ORPHAN-NIGHT": "ORPHAN-NIGHT",
    "MIDWEEK-2": "MIDWEEK-2", "LONG-GAP": "LONG-GAP", "THIS-WEEK": "THIS-WEEK",
}


def get(code):
    return CAMPAIGNS.get(code)


def primary_code(gap, pace_mode="normal"):
    """Pick the campaign for a gap. Protected units are upgrade-only; a 'full' portfolio swaps a
    discount campaign for the no-discount relationship one (build spec §4 offer-by-calendar-state)."""
    if gap.get("protected"):
        return "UPGRADE-MIDWEEK"
    code = CLASS_PRIMARY.get(gap.get("gap_class"), "THIS-WEEK")
    if pace_mode == "full" and CAMPAIGNS.get(code, {}).get("offer_mode") in ("value_add", "deeper"):
        return "YOUR-UNIT-FREE"            # relationship-only when we're nearly sold out
    return code


# ---------------------------------------------------------------------------
# Karzoun / Meta one-time template submission catalogue (build spec §3).
# Each of the 20 campaigns exports both languages of its Marketing variant, plus both languages of
# the Utility variant for the two campaigns that carry one (POST-CHECKOUT, REVIEW-TO-REBOOK) — the
# RAW header/body/footer/button with {{1}}..{{5}} INTACT (this is the text the owner pastes into
# Meta once), its sample values, and the approval note. ~44 rows total.
# ---------------------------------------------------------------------------
TEMPLATE_CSV_COLUMNS = ["template_name", "category", "language", "header", "body",
                        "footer", "button", "sample_values", "approval_note"]


def _sample_str(sample):
    """Serialize a sample dict {"1": "نورة", "2": "…"} -> "1=نورة; 2=…" (variable order)."""
    if not sample:
        return ""
    return "; ".join("%s=%s" % (k, sample[k]) for k in sorted(sample, key=lambda x: str(x)))


def _tpl_rows(code, camp):
    """Yield the export rows for one campaign: Marketing AR + EN, then (if any) Utility AR + EN."""
    rows = []
    note = camp.get("approval_note", "")
    # Marketing variant (default)
    for lang, block, sample in (("ar", camp.get("ar") or {}, camp.get("sample_ar")),
                                ("en", camp.get("en") or {}, camp.get("sample_en"))):
        rows.append([camp.get("template_name", code), "MARKETING", lang,
                     block.get("header") or "", block.get("body") or "",
                     block.get("footer") or "", block.get("button") or "",
                     _sample_str(sample), note])
    # Utility variant, when present (Meta UTILITY category — no offer, no opt-out footer/button)
    if camp.get("utility_variant"):
        tn_util = camp.get("template_name_utility") or camp.get("template_name", code)
        for lang, block, sample in (("ar", camp.get("ar_utility") or {}, camp.get("sample_ar")),
                                    ("en", camp.get("en_utility") or {}, camp.get("sample_en"))):
            rows.append([tn_util, "UTILITY", lang,
                         block.get("header") or "", block.get("body") or "",
                         block.get("footer") or "", block.get("button") or "",
                         _sample_str(sample), note])
    return rows


def build_templates_csv():
    """All 20 campaigns (44 rows incl. both utility variants) as a Meta-submission CSV.
    Returns (filename, text). Read-only; this is the one-time template text, not a send list."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEMPLATE_CSV_COLUMNS)
    for code, camp in CAMPAIGNS.items():
        for row in _tpl_rows(code, camp):
            w.writerow(row)
    return "ouja_meta_templates.csv", buf.getvalue()
