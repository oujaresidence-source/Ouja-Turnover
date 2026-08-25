# -*- coding: utf-8 -*-
"""studio.hooks — the hook bank, categorised by psychological trigger (spec Section G).

These are SHAPES, not scripts. The generator picks the trigger that fits the signal,
then fills the shape with the real number/fact — that's what keeps a hook grounded
instead of generic. Written in Najdi so the fill reads like Faisal talking, not like
a translated caption.

Every entry uses «…» where the real signal goes. A hook that reaches camera with the
placeholder still in it is a bug, not a hook.

Growing the bank: add to the right trigger list. Keep each one under ~10 words —
the playbook caps the spoken hook at 3 seconds.
"""

from . import engine

HOOK_BANK = {
    # Open a loop the viewer has to close.
    "curiosity": [
        "فيه شي بشقتنا محد ينتبه له… وهو «…»",
        "ليش «…»؟ الجواب غيّر طريقة شغلنا كلها",
        "سألوني كثير: كيف «…»؟ خلني أوريك",
        "هذا الرقم «…» — وأنا بشرح لك من وين جاء",
        "أغرب شي صار لنا هالأسبوع: «…»",
        "تعرف وش يصير بالشقة قبل ما توصلها بساعتين؟",
        "فيه سبب إن «…» — وما أحد يقوله بصوت عالي",
    ],
    # What they lose by not knowing. Never fake urgency — the loss must be real.
    "loss": [
        "انت تخسر فلوس كل شهر وانت ما تدري — «…»",
        "لو شقتك فاضية اليوم فأنت تدفع «…» من جيبك",
        "الغلط اللي كلّفنا «…» أول سنة",
        "أغلب الملاك يفوّتون «…» — وهذي أغلى غلطة",
        "إذا ما سويت «…» قبل الشتاء بتندم",
        "كل ليلة فاضية ما ترجع — وهذا حسابها بالضبط",
    ],
    # "If you are X, this is for you." The strongest opener per the research.
    "identity": [
        "لو عندك شقة في الرياض، هذا الفيديو لك",
        "لو انت صاحب عقار وتفكر تأجره يومي — اسمعني دقيقة",
        "لو تبي تدخل مجال الشقق المفروشة، ابدأ من هنا",
        "لو انت مستثمر صغير وما عندك رأس مال كبير — «…»",
        "لو شقتك بالرياض وما تدري تسعّرها كم، هذا الرقم لك",
        "للي يشتغل بالإيجار قصير المدى: «…» تغيّر عليك كل شي",
        "لو تدير شقة وحدة بس — هذي أهم معلومة لك اليوم",
    ],
    # Challenge a belief — but from real experience, never empty provocation.
    "provocation": [
        "تأجير الشقق مو ربح سهل — وهذي الحقيقة اللي عشتها",
        "كل اللي يقولون «…» غلطانين، وعندي الرقم",
        "أنا ضد «…» — وأشرح لك ليش بالتجربة",
        "أكثر نصيحة منتشرة بالمجال وهي أسوأ شي تسويه",
        "بطّل تسوي «…» — جربناها وطلعت خسارة",
        "الشقة الحلوة ما تكفي — وهذا اللي فعلاً يفرق",
    ],
    # Insider authority: the thing only an operator at scale knows.
    "authority": [
        "أنا أشغّل «…» شقة بالرياض، وهذا اللي تعلمته",
        "بعد «…» حجز، صار عندي قاعدة وحدة",
        "أسرار الصنعة: كيف نحوّل شقة عادية لتجربة فندق",
        "هذا اللي يصير خلف الكواليس وما يشوفه الضيف أبداً",
        "من داخل غرفة العمليات: «…»",
        "شركات إنتاج تحجز شققنا للتصوير — والسبب «…»",
        "أنا أقرأ «…» رسالة ضيف بالشهر، وهذي أكثر جملة تتكرر",
    ],
    # Real results, real numbers. This is where internal data shines.
    "social_proof": [
        "«…» من ضيوفنا يسوون هالشي — والرقم صدمني",
        "تقييمنا «…» من «…» تقييم — وهذي الطريقة",
        "هالشقة انحجزت «…» مرة هالشهر. ليش هي بالذات؟",
        "من فاضية إلى محجوزة خلال «…» — قدام عينك",
        "«…» — هذا مو كلام، هذي أرقام حسابنا",
        "ضيف رجع لنا «…» مرة. سألته ليش، قال «…»",
    ],
    # Timeliness — pairs with the external signal streams. Film these FAST.
    "news": [
        "نزل نظام جديد «…» — وهذا معناه لشقتك",
        "خبر اليوم يخص كل صاحب شقة بالرياض: «…»",
        "السعودية طلعت برقم «…» — وهذي فرصتك فيه",
        "تغيّر شي بالسوق هالأسبوع، وأغلب الملاك ما انتبهوا",
        "قرار جديد بيأثر على تسعيرك — بشرحه بأربعين ثانية",
        "العالم كله يتجه لـ«…» — واحنا بالرياض نسويها من زمان",
    ],
}

# What each trigger is FOR — goes into the generator prompt so the model picks
# a trigger on purpose instead of defaulting to curiosity every time.
TRIGGER_PURPOSE = {
    "curiosity": "افتح حلقة ناقصة لازم يكملها عشان يعرف الجواب",
    "loss": "ورّه وش يخسر إذا ما عرف — والخسارة لازم تكون حقيقية مو تخويف",
    "identity": "نادِ الشريحة بالاسم: «لو انت …» — أقوى افتتاحية مثبتة",
    "provocation": "اكسر اعتقاد سائد، لكن من تجربة حقيقية مو استفزاز فاضي",
    "authority": "تكلّم من داخل العملية — الشي اللي ما يعرفه إلا اللي يشغّل فعلاً",
    "social_proof": "ارمِ الرقم الحقيقي مباشرة — الأرقام تشتري الثقة",
    "news": "اربطها بخبر/نظام جديد بتاريخه — والسرعة هنا جزء من الفكرة",
}

# The trigger that naturally fits each signal source. A hint, not a cage — the
# generator may pick another when the signal genuinely calls for it.
SOURCE_TRIGGER_HINT = {
    "occupancy": ("social_proof", "authority"),
    "pricing": ("loss", "authority"),
    "reviews": ("social_proof", "identity"),
    "ops": ("authority", "curiosity"),
    "season": ("loss", "identity"),
    "insider": ("authority", "provocation"),
    "guest_story": ("curiosity", "emotion"),
    "regulation": ("news", "loss"),
    "market": ("news", "social_proof"),
    "global_trend": ("news", "authority"),
    "trend": ("news", "curiosity"),
    "manual": ("curiosity", "authority"),
}


def bank_size():
    return sum(len(v) for v in HOOK_BANK.values())


def for_trigger(trigger):
    return list(HOOK_BANK.get(trigger, ()))


def suggest(source, n=6):
    """Hook shapes worth offering for a signal from `source`, best-fit trigger first."""
    order = list(SOURCE_TRIGGER_HINT.get(source, ()))
    order += [t for t in engine.TRIGGERS if t not in order]
    out = []
    for t in order:
        for h in HOOK_BANK.get(t, ()):
            out.append({"trigger": t, "shape": h})
            if len(out) >= n:
                return out
    return out


def prompt_block(source):
    """The hook-bank slice that rides inside a generation call for this source."""
    picks = suggest(source, n=8)
    lines = ["بنك الهوكات (أشكال جاهزة — املأ «…» بالحقيقة نفسها، ولا تترك المكان فاضي):"]
    seen = set()
    for p in picks:
        if p["trigger"] not in seen:
            seen.add(p["trigger"])
            lines.append("• [%s] %s" % (p["trigger"], TRIGGER_PURPOSE.get(p["trigger"], "")))
        lines.append("   - %s" % p["shape"])
    return "\n".join(lines)
