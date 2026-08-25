# نموذج مصاريف الميدان — دليل الإعداد / Field-Expense Form — Setup Guide

ربط **Google Form ← → نظام عوجا ← → Hostaway**. اتبع الخطوات بالترتيب. ما يحتاج خبرة برمجة.
Wire **Google Form ⇄ Ouja system ⇄ Hostaway**. Follow in order. No coding needed.

> النتيجة: الموظف يعبّي النموذج من جواله → المصروف يدخل النظام تلقائياً → النظيف يترحّل لـHostaway،
> والمشكوك فيه يروح لطابور المراجعة بالداشبورد.
> Result: employee fills the form on the phone → expense enters the system automatically →
> clean ones post to Hostaway, questionable ones land in the dashboard review queue.

---

## ⭐ الطريقة الموصى بها (بدون أي كود) — Pull-based, no Apps Script

النظام **يسحب** الشيت بنفسه كل بضع دقائق ويستورد الصفوف الجديدة. ما تحتاج Apps Script ولا مشغّلات
ولا تسجيل دخول Google للبرمجة. **خطوتين فقط:**

1. **شارك الشيت للقراءة:** افتح الشيت → **Share / مشاركة** → غيّر إلى **"Anyone with the link →
   Viewer / أي شخص لديه الرابط → مُشاهد"** → انسخ الرابط.
2. **أضف متغيّر واحد على Railway:** Variables → أضف:
   - الاسم: `EXPENSE_SHEET_CSV_URL`
   - القيمة: رابط الشيت اللي نسخته (النظام يحوّله تلقائياً لصيغة CSV).
   - (اختياري) `EXPENSE_SHEET_POLL_MIN` = كل كم دقيقة يسحب (الافتراضي 3).

خلاص — بعد إعادة تشغيل Railway، أي صف جديد بالشيت يدخل تلقائياً خلال دقائق، يمرّ على نفس الفحوصات،
وغير المطابق بالشقة يُحجَز للمراجعة (كما طلبت). الشقق تُطابَق مع Hostaway تلقائياً.

> ملاحظات: هذي الطريقة لا تكتب الحالة رجوع في الشيت ولا تزامن قوائم النموذج (راجع الداشبورد كمرجع
> أساسي). لو تبي هذي الميزتين، استخدم طريقة Apps Script بالأسفل بدلاً منها.
>
> Two steps only: share the sheet "Anyone with link → Viewer", then add `EXPENSE_SHEET_CSV_URL`
> on Railway. The bot pulls new rows automatically. (No sheet status write-back / no dropdown
> auto-sync — use the Apps Script method below if you want those.)

---

## الطريقة البديلة (Apps Script) — gives status write-back + dropdown sync

---

## الخطوة 0 — متغيّر السر على Railway / Step 0 — Secret on Railway

1. افتح Railway → الخدمة (worker) → تبويب **Variables**.
2. أضف متغيّر جديد:
   - الاسم: `EXPENSE_INGEST_SECRET`
   - القيمة: أي كلمة سر طويلة من اختيارك (مثال: `ouja-exp-9f3k2p7q`). احفظها — بتلصقها بالسكربت.
3. (اختياري الآن، لاحقاً للترحيل الفعلي) `EXPENSE_POST_DRYRUN=0` يخلّي الترحيل لـHostaway **حقيقي**.
   خلّيه `1` (الوضع الافتراضي) للتجربة بدون كتابة فعلية على Hostaway.

> Add `EXPENSE_INGEST_SECRET` (any long secret) on Railway Variables. Keep `EXPENSE_POST_DRYRUN=1`
> while testing; set it to `0` only when you're ready for real Hostaway writes.

---

## الخطوة 1 — نموذجك موجود مسبقاً / Step 1 — Your form already exists

النموذج والشيت موجودين عندك. `Code.gs` **معدّل مسبقاً** ليطابق أعمدة شيتك الحالي:

| العمود في شيتك | يروح إلى النظام كـ |
|---|---|
| `اسم المشرف \| Supervisor Name` | اسم المُرسِل (submitter) |
| `تاريخ الصيانه \| Maintenance Date` | تاريخ المصروف (expense_date) |
| `اسم الشقه؟` | الشقة (apartment) — تُطابَق مع Hostaway |
| `نوع الصيانه \| Maintenance Type` | نوع الصيانة (يصير اسم المصروف في Hostaway) |
| `وصف العمل` + `ملاحظات إضافيه` + سؤال الضريبة | يُدمجون في حقل الملاحظة (note) |
| `التكلفه بالريال \| Cost in SAR` | المبلغ (amount) |
| `اسم الموّرد \| Vendor Name` | المورّد (vendor) |
| `رفع الفاتوره \| Upload Invoice` | رابط الفاتورة (receipt_link) — رابط Drive فقط |
| `اذا مافي فاتوره، اكتب السبب` | سبب عدم وجود فاتورة (no_receipt_reason) |

**نقطتان لازم تتأكد منهما / Two things to check:**

1. **سؤال `اسم الشقه؟` لازم يكون نوعه "قائمة منسدلة" (Dropdown) — مو إجابة قصيرة.**
   لأن: (أ) المواصفات تمنع الكتابة الحرة في الشقة (A.1)، (ب) السكربت يعبّي القائمة تلقائياً بأسماء عوجا من
   Hostaway. لو هو الحين "إجابة قصيرة"، حوّله إلى Dropdown (الأسماء بتنعبّي تلقائياً بالخطوة 4 — خلّه فاضي).
   > The `اسم الشقه؟` question MUST be a **Dropdown** (not short-answer). Leave its options empty —
   > the script fills them from Hostaway. Free-typed apartment names will not match and will be held.

2. **سؤال رفع الفاتورة غير إلزامي**، ولو ما فيه فاتورة يكتب الموظف السبب في سؤال "اذا مافي فاتوره" —
   والنظام يحجزه للمراجعة (A.3). الفاتورة تنحفظ بـDrive والنظام يخزّن الرابط فقط (قاعدة #6).

**ملاحظتان عن الفروقات / Two notes about your form:**
- **ما فيه سؤال "فئة المصروف"** — النموذج كله صيانة، فالسكربت يرسل الفئة الافتراضية
  `صيانة وإصلاحات` (= `Maintenance & Repairs` في Hostaway). لو تبي تفصّل الفئات لاحقاً نضيف سؤال.
- **سؤال الضريبة (VAT)** يُسجّل داخل الملاحظة (مثلاً «الضريبة/VAT: نعم») عشان ما يضيع.

---

## الخطوة 2 — تأكد إن الشيت مربوط / Step 2 — Confirm the responses Sheet

شيت الردود موجود عندك (هذا اللي عطيتني عناوينه). افتحه — هنا بيشتغل السكربت.

---

## الخطوة 3 — الصق السكربت / Step 3 — Paste the script

1. من **الشيت** (مو النموذج): **Extensions → Apps Script**.
2. امسح أي كود موجود، والصق كامل محتوى ملف **`Code.gs`** (الموجود بنفس هذا المجلد بالريبو).
3. عدّل أول 3 سطور إعدادات بأعلى الملف:
   - `BASE_URL` — رابط النظام (موجود جاهز: `https://worker-production-5d63.up.railway.app`).
   - `INGEST_SECRET` — الصق نفس قيمة `EXPENSE_INGEST_SECRET` من الخطوة 0.
   - `FORM_ID` — من رابط تعديل النموذج: `https://docs.google.com/forms/d/`**`<هذا الجزء>`**`/edit`.
4. **Save** (أيقونة الحفظ).

---

## الخطوة 4 — ركّب المشغّلات / Step 4 — Install triggers

1. في محرّر Apps Script، من القائمة المنسدلة فوق اختر الدالة **`installTriggers`** → اضغط **Run**.
2. أول مرة بيطلب صلاحيات: **Review permissions → اختر حسابك → Advanced → Go to … (unsafe) → Allow**.
   (طبيعي — هذا سكربتك أنت.)
3. بعد ما يخلص:
   - يركّب مشغّل **عند كل إرسال نموذج** (يدفع للنظام + يكتب الحالة بالشيت).
   - يركّب مشغّل **كل ساعة** يحدّث قوائم النموذج (الشقق/الأنواع/الفئات/الموظفين/طرق الدفع).
   - يسوي **أول تحديث للقوائم الحين** — فروح للنموذج وتأكد إن قائمة `الشقة` انعبّت بأسماء عوجا.

> Run `installTriggers` once, grant permissions, done. It wires the submit trigger, an hourly
> dropdown-sync trigger, and runs a first sync immediately.

---

## الخطوة 5 — جرّب / Step 5 — Test

1. افتح النموذج (Preview 👁) واملأ مصروف تجريبي على شقة حقيقية بمبلغ بسيط.
2. تحقق:
   - **الشيت:** ظهر عمود `الحالة (تلقائي)` وفيه نتيجة مثل `OJ-EXP-0001 · ⏳ بانتظار المراجعة`.
   - **الداشبورد → تبويب المصاريف:** المصروف ظهر (بالطابور إذا فيه ملاحظة، أو مُرحّل إذا نظيف
     و`EXPENSE_POST_DRYRUN=0`).
3. جرّب الحالات: بدون فاتورة → يروح للطابور؛ اسم شقة فيه شبه باسمين → "الشقة تحتاج تأكيد"؛ نفس المبلغ
   ونفس الشقة ونفس اليوم مرتين → "تكرار محتمل".

---

## ملاحظات / Notes

- **القوائم تظل محدّثة تلقائياً:** أي شقة جديدة/محذوفة في Hostaway تنعكس على النموذج خلال ساعة، أو فوراً
  لو شغّلت `syncDropdowns` يدوياً من المحرّر. (المتطلب A.2)
- **ما يتكرر الإرسال:** كل صف له `submission_id` ثابت، فلو انضغط مرتين ما يتسجّل مصروفين. (قاعدة #7)
- **المصاريف الشهرية الثابتة (~70%)** لا تدخل عبر هذا النموذج — تنضبط مرة وحدة في
  **Hostaway → Recurring Expenses** وتتكرر تلقائياً. هذا النموذج فقط للمصاريف المتغيّرة الميدانية (~30%).
  (الجزء F)
- لو تغيّر رابط النظام مستقبلاً، حدّث `BASE_URL` بالسكربت فقط.
