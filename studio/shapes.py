# -*- coding: utf-8 -*-
"""studio.shapes — a small library of distinct script SHAPES. PURE.

The single biggest reason every card looked identical was that the generator was
asked for one skeleton. A creator posting 3/day cannot post 3 identically-shaped
videos. So a card now carries a SHAPE, chosen by (source, trigger, audience), and the
daily set is spread so no two of today's cards share one.

A shape is NOT a template with fixed beats — it is an angle of attack described in one
Najdi line the generator writes *in his own voice* around. The timing grid is gone;
the shape is what makes two cards on two different facts feel like two different videos.
"""

# key       stable id (stored on the card, used for daily-set spread)
# name      Arabic label shown to the owner
# guide     one Najdi line handed to the generator: how this shape opens and moves
# triggers  triggers this shape fits best (a hint for pick_shape, not a hard rule)
# audience  '' = fits both; else the audience it leans toward
SHAPES = (
    {"key": "cold_number", "name": "رقم مفتوح",
     "guide": "افتح بالرقم نفسه كأول كلمة تنطقها، بدون مقدمة، وبعدها فسّر وش يعنيه هالرقم عملياً.",
     "triggers": ("social_proof", "authority"), "audience": ""},
    {"key": "myth_bust", "name": "كسر اعتقاد",
     "guide": "ابدأ باعتقاد شائع غلط عند الناس، بعدها اقلبه بالرقم/الحقيقة الحقيقية من تجربتك.",
     "triggers": ("provocation", "authority"), "audience": "niche"},
    {"key": "quote_reaction", "name": "رد على موقف",
     "guide": "ابدأ باقتباس/موقف حقيقي قصير صار، وبعدها ردّة فعلك عليه والدرس منه.",
     "triggers": ("curiosity", "emotion"), "audience": "escape"},
    {"key": "before_after", "name": "قبل وبعد",
     "guide": "صوّر الوضع قبل، بعدها التحوّل، خلّ الرقم أو النتيجة هي البرهان على الفرق.",
     "triggers": ("authority", "social_proof"), "audience": ""},
    {"key": "half_of_us", "name": "أغلب ضيوفنا",
     "guide": "ابدأ بسلوك يسويه أغلب الضيوف/الملّاك (بالرقم)، وبعدها ليش هذا يغيّر تفكيرك.",
     "triggers": ("social_proof", "identity"), "audience": ""},
    {"key": "owner_question", "name": "سؤال للمالك",
     "guide": "ابدأ بسؤال مباشر يخاطب صاحب الشقة («كم تحسب…؟»)، وبعدها اكشف الجواب بالرقم.",
     "triggers": ("identity", "loss"), "audience": "niche"},
    {"key": "list_of_three", "name": "ثلاث نقاط",
     "guide": "ابدأ بوعد بثلاث نقاط سريعة مبنية على الحقيقة، وسرد بإيقاع سريع بدون حشو.",
     "triggers": ("authority", "curiosity"), "audience": ""},
    {"key": "news_react", "name": "رد على خبر",
     "guide": "ابدأ بالخبر/النظام الجديد بتاريخه، وبعدها وش يعني بالضبط لصاحب الشقة اليوم.",
     "triggers": ("news",), "audience": "niche"},
)

_BY_KEY = {s["key"]: s for s in SHAPES}
SHAPE_KEYS = tuple(s["key"] for s in SHAPES)

# The natural fit for a signal source — the first shape we reach for. Not a cage:
# pick_shape rotates away from it when that shape is already used in the set.
SOURCE_SHAPE = {
    "occupancy": ("half_of_us", "cold_number", "owner_question"),
    "pricing": ("cold_number", "myth_bust", "owner_question"),
    "reviews": ("quote_reaction", "cold_number", "before_after"),
    "ops": ("before_after", "list_of_three", "quote_reaction"),
    "season": ("owner_question", "half_of_us", "list_of_three"),
    "insider": ("myth_bust", "list_of_three", "before_after"),
    "guest_story": ("quote_reaction", "before_after", "half_of_us"),
    "regulation": ("news_react", "owner_question", "myth_bust"),
    "market": ("news_react", "cold_number", "half_of_us"),
    "global_trend": ("news_react", "myth_bust", "cold_number"),
    "trend": ("news_react", "quote_reaction", "curiosity"),
    "manual": ("quote_reaction", "before_after", "list_of_three"),
}


def get(key):
    return _BY_KEY.get(key)


def label(key):
    s = _BY_KEY.get(key)
    return s["name"] if s else ""


def pick_shape(source, trigger="", audience="", exclude=()):
    """Choose a shape for a signal, preferring its source's natural fit and the
    trigger, while avoiding shapes already used in the current set (`exclude`)."""
    exclude = set(exclude or ())
    order = []
    for k in SOURCE_SHAPE.get(source, ()):
        if k not in order:
            order.append(k)
    # then any shape matching the trigger
    for s in SHAPES:
        if trigger and trigger in s["triggers"] and s["key"] not in order:
            order.append(s["key"])
    # then the rest, stable
    for k in SHAPE_KEYS:
        if k not in order:
            order.append(k)
    # honour audience lean when there's a clean choice
    if audience:
        aud_first = [k for k in order
                     if not _BY_KEY[k]["audience"] or _BY_KEY[k]["audience"] == audience]
        order = aud_first + [k for k in order if k not in aud_first]
    for k in order:
        if k not in exclude:
            return k
    return order[0] if order else "cold_number"


def candidate_shapes(source, trigger="", audience="", n=3):
    """The n distinct shapes worth trying for this signal, best fit first — the
    generator writes one candidate per shape so we can keep the strongest."""
    out = []
    ex = set()
    for _ in range(max(1, n)):
        k = pick_shape(source, trigger, audience, exclude=ex)
        out.append(k)
        ex.add(k)
    return out


def guide_block(shapes):
    """The prompt fragment naming the shapes this call may use, with their guides."""
    lines = ["الأشكال المسموحة لهالفكرة (اكتب كل فكرة بشكل مختلف — ممنوع نفس الشكل مرتين):"]
    for k in shapes:
        s = _BY_KEY.get(k)
        if s:
            lines.append("• [%s] %s — %s" % (k, s["name"], s["guide"]))
    return "\n".join(lines)
