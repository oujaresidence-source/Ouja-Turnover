# brain/playbook.py — Ouja Elite campaigns (v2: hooks + psychology)
# Each campaign: a HOOK (the opening line that earns attention) + an embedded,
# ethical persuasion principle, in warm "white tone" Najdi Arabic + English.
# Placeholders: {name} {unit} {date} {date_in} {date_out} {occasion} {nights}
# Tone rule: a message from a host who remembers you — never a sale.

CAMPAIGNS = {

# ---------- CALENDAR-TRIGGERED ----------
"TONIGHT": {
    "principle": "Immediacy + scarcity — a door open right now, not later",
    "tier_focus": "any (last-minute bookers first)",
    "ar": "{name}، لو يومك طوّل، Ouja | {unit} هادية وجاهزة الليلة. الباب مفتوح لك.",
    "en": "{name}, if today ran long, Ouja | {unit} is calm and ready tonight. The door's open.",
},
"TOMORROW": {
    "principle": "Anticipation + first-access — you hear before it's public",
    "tier_focus": "last-minute repeaters",
    "ar": "{name}، Ouja | {unit} فاضية بكرة ({date}) — حبيت تعرف أول واحد قبل لا تنعرض.",
    "en": "{name}, Ouja | {unit} is free tomorrow ({date}) — wanted you to know first, before it's listed.",
},
"ORPHAN-NIGHT": {
    "principle": "Reciprocity + first-access — 'thought of you first'",
    "tier_focus": "last-minute, local repeaters",
    "ar": "{name}، انفتحت ليلة وحدة في Ouja | {unit} وأول من خطر ببالي أنت. تبيها قبل لا تروح؟",
    "en": "{name}, a single night just opened at Ouja | {unit} and you were the first I thought of. Want it before it's gone?",
},
"MIDWEEK-2": {
    "principle": "Endowment + calm — already 'set aside for you'",
    "tier_focus": "Gold weekday regulars",
    "ar": "{name}، رتّبت لك ليلتين هادئتين وسط الأسبوع في Ouja | {unit}. لو يناسبك سكون يومين، أثبتها لك؟",
    "en": "{name}, I've set aside two quiet midweek nights at Ouja | {unit}. If two calm days suit you, shall I hold them?",
},
"LONG-GAP": {
    "principle": "Convenience + anchoring — the longer stay 'made easy'",
    "tier_focus": "long-stay history, corporate",
    "ar": "{name}، لو تحتاج كم يوم وسط الأسبوع، Ouja | {unit} متاحة {date_in}–{date_out} وأرتّب لك الإقامة الطويلة براحتك.",
    "en": "{name}, if you need a few midweek days, Ouja | {unit} is open {date_in}–{date_out} and I'll make the longer stay easy on you.",
},
"THIS-WEEK": {
    "principle": "Soft scarcity — a few quiet nights left",
    "tier_focus": "Gold + trusted repeaters",
    "ar": "{name}، عندنا ليالٍ هادية باقية هالأسبوع في Ouja | {unit}. أحجز لك وحدة؟",
    "en": "{name}, we have a few quiet nights left this week at Ouja | {unit}. Hold one for you?",
},
"LAST-CHANCE": {
    "principle": "Loss aversion — last call, then it closes",
    "tier_focus": "prior non-responders only",
    "ar": "{name}، آخر فرصة لـ Ouja | {unit} يوم {date} — بعدها نقفل الترتيب. تبيها؟",
    "en": "{name}, last call on Ouja | {unit} for {date} — after this I close it off. Want it?",
},

# ---------- GUEST-TRIGGERED ----------
"YOUR-UNIT-FREE": {
    "principle": "Endowment + recognition — 'your' apartment, told to you first",
    "tier_focus": "the repeater (any tier)",
    "ar": "{name}، شقتك Ouja | {unit} فاضية على أيامك المعتادة هالأسبوع. حسّيت إنه من حقك تعرف أول واحد.",
    "en": "{name}, your apartment — Ouja | {unit} — is free on your usual days this week. Felt wrong not to tell you first.",
},
"SIMILAR-UNIT": {
    "principle": "Continuity — same feel when the favourite is taken",
    "tier_focus": "repeater whose unit is booked",
    "ar": "{name}، وحدتك المعتادة محجوزة هالمرة، بس Ouja | {unit} بنفس الأجواء وفاضية وسط الأسبوع. تجرّبها؟",
    "en": "{name}, your usual is taken this time, but Ouja | {unit} has the same feel and is open midweek. Want to try it?",
},
"WELCOME-BACK": {
    "principle": "Belonging + warmth — we noticed you were away",
    "tier_focus": "dormant 60–120d, score ≥50",
    "ar": "{name}، صار لنا فترة ما شفناك ووحشتنا 🌿 لو يناسبك يوم هادي وسط الأسبوع، يشرّفنا نستقبلك من جديد.",
    "en": "{name}, it's been a little while and we've missed you 🌿 If a quiet midweek day suits, we'd love to host you again.",
},
"WIN-BACK": {
    "principle": "Reciprocity + belonging — one-time, personal",
    "tier_focus": "dormant 120–365d, score ≥50",
    "ar": "{name}، صدق وحشتنا 🤍 رجوعك يهمّنا — رتّبت لك ترتيب خاص في Ouja | {unit} لزيارتك الجاية. نجهّزها؟",
    "en": "{name}, we've genuinely missed you 🤍 Your return matters — I've set something special aside at Ouja | {unit}. Shall I prepare it?",
},
"WEEKDAY-REGULAR": {
    "principle": "Recognition + habit — 'I remember your pattern'",
    "tier_focus": "weekday_pattern, stays ≥3",
    "ar": "{name}، عارفين إنك تحب وسط الأسبوع الهادي 🤍 Ouja | {unit} فاضية هالأيام لو ودّك تمر علينا.",
    "en": "{name}, we know you like a quiet midweek 🤍 Ouja | {unit} is open these days if you'd like to come by.",
},
"POST-CHECKOUT": {
    "principle": "Peak-end + warmth — leave on a high, no ask",
    "tier_focus": "checked out ≤2d, happy",
    "ar": "نوّرتنا {name} 🤍 أي وقت يناسبك يوم هادي وسط الأسبوع، بيتك في Ouja جاهز لك.",
    "en": "It was a pleasure, {name} 🤍 Whenever a quiet midweek day suits, your Ouja home is ready for you.",
},
"UPGRADE-MIDWEEK": {
    "principle": "Reciprocity (a gift) + status — moved up, on us (NO price cut)",
    "tier_focus": "in-house / eligible; protected units upgrade-only",
    "ar": "بشارة {name} 🤍 رقّيتك لـ Ouja | {unit} — أرحب وأهدأ — هدية منّا لإقامتك وسط الأسبوع.",
    "en": "Good news {name} 🤍 I've moved you up to Ouja | {unit} — more space, more calm — on us for your midweek stay.",
},
"TURAIF-MIDWEEK": {
    "principle": "Exclusivity + scarcity — held for you, before anyone",
    "tier_focus": "Turaif only",
    "ar": "{name}، خصّيتك Ouja | {unit} وسط الأسبوع ورتّبتها باسمك قبل لا تنعرض لأحد. تشرّفنا؟",
    "en": "{name}, I've set Ouja | {unit} aside for you midweek and held it in your name before anyone else sees it. Shall we?",
},
"OCCASION-MIDWEEK": {
    "principle": "Personalization + occasion — a thoughtful, timely gift",
    "tier_focus": "repeaters; personalize if date known",
    "ar": "{name}، بما إن {occasion} يجي وسط الأسبوع، يشرّفني أستضيفك في Ouja | {unit} وأضيف لمسة تليق بالمناسبة.",
    "en": "{name}, with {occasion} falling midweek, I'd love to host you at Ouja | {unit} and add a little something to make it special.",
},
"LONG-STAY-MIDWEEK": {
    "principle": "Value framing + anchoring — longer stay, kinder rate",
    "tier_focus": "long-stay seekers",
    "ar": "{name}، عندي فترة حلوة وسط الأسبوع في Ouja | {unit}، {date_in}–{date_out}. للإقامة الطويلة أقدر أخفّف السعر. يناسبك؟",
    "en": "{name}, I have a good midweek stretch at Ouja | {unit}, {date_in}–{date_out}. For a longer stay I can make the rate kinder. Interested?",
},
"CORPORATE-WEEKDAY": {
    "principle": "Convenience + commitment — make their routine effortless",
    "tier_focus": "corporate_pattern",
    "ar": "{name}، لاحظت إقاماتك المتكررة بأيام العمل — أقدر أرتّب لك ولفريقك ترتيب شركات بأسعار ثابتة وأولوية حجز. أرتّبه؟",
    "en": "{name}, I've noticed your regular weekday stays — I can set up a simple corporate arrangement with fixed rates and priority for you and your team. Shall I?",
},
"ELITE-NUDGE": {
    "principle": "Status + consistency — 'you're a regular now'",
    "tier_focus": "Silver, 2 stays, not enrolled",
    "ar": "{name}، صرت من ضيوفنا الدائمين — أحب أضمّك لعائلة عوجا إيليت، بأولوية حجز وترحيب خاص وسط الأسبوع.",
    "en": "{name}, you're one of our regulars now — I'd like to welcome you into Ouja Elite, with booking priority and a standing midweek welcome.",
},
"REVIEW-TO-REBOOK": {
    "principle": "Reciprocity + commitment — your words matter, your next stay is easy",
    "tier_focus": "recent happy guests",
    "ar": "{name}، سعدنا بإقامتك 🌿 لو تشاركنا كلمة بسيطة عنها يهمّنا كثير — وأي وقت تبي يوم هادي وسط الأسبوع، نرتّبه لك بسهولة.",
    "en": "{name}, we loved hosting you 🌿 If you'd share a quick word about your stay it means a lot — and your next quiet midweek is easy to set up whenever you like.",
},
}
