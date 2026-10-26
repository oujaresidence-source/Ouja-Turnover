# «نسبة التنظيف» بدل الرسوم الشهرية — نظام العقود (aqd/)

التاريخ: 2026-10-26 · الحالة: معتمد من المالك ومنفَّذ على الفرع feat/aqd-clean-pct (غير مرفوع)

## الملخص بكلام بسيط

- لما تسوي عقد جديد، أول ما تدخل خطوة «الوحدات» تختار طريقة وحدة من اثنتين:
  **«رسوم تشغيل شهرية»** (مثل اليوم بالضبط) أو **«نسبة تنظيف»**.
- لو اخترت «نسبة تنظيف»:
  - تنشال خانة الرسوم الشهرية من كل الوحدات.
  - في خطوة «الشروط» تطلع خانة «نسبة التنظيف» جنب «نسبة التشغيل».
  - العقد يطلع بالنص اللي اعتمدته، وصدره يقول: «23% ثابتة من صافي الإيرادات + نسبة التنظيف 5% من صافي الإيرادات».
- العقود اللي فيها رسوم شهرية **ما يتغير فيها ولا حرف**. ملفاتها تبقى زي ما هي، واعتمادها يبقى زي ما هو.
- نموذجي «نسبة التنظيف» يطلعون **غير معتمدين**، مثل أي نموذج جديد. ما ينرسل منهم رابط توقيع لين تعتمدهم أنت من الإعدادات (تكتب «اعتماد»)، وكل نموذج يتعتمد لحاله.

## القرارات (معتمدة من المالك)

| # | القرار |
|---|---|
| D1 | الطريقة للعقد كله: «رسوم شهرية» أو «نسبة تنظيف». ما يجتمعون في عقد واحد. |
| D2 | نص المادة ١٢ الجديد معتمد كما هو مكتوب تحت (النص الحرفي، T5). |
| D3 | رسوم التنظيف اللي يدفعها الضيف عبر المنصة (المادة ١٠ فقرة ٢) تبقى للمشغّل. |
| D4 | الاستخدام الشخصي فوق 30 يوم يُحسب عليه نسبة التشغيل بس، بدون نسبة التنظيف. يعني المادة اللي فيها هالبند ما تتغير. |
| D5 | ينطبق على النموذجين: (أ) حساب المالك و(ب) حساب عوجا. |

## أجوبة المالك (2026-10-26)

- **Q1:** الاختيارات 3% / **5%** (الافتراضي) / 7% / «نسبة أخرى» من 1% إلى 15% بخطوات نص بالمية — معتمد.
- **Q2:** نضيف «ونسبة التنظيف» لكشف الحساب في نموذج (أ) — معتمد.

## Design (technical)

### Why two new template files, not slots in the 2.2 files
Each contract freezes the bytes of its template, the hash covers those bytes, and approval is stored
per template name (`approval_key`). If we added slots to `operating_v2_2` / `operating_ouja_v2_2`, the
approved monthly text would change, so those templates would need a version bump and re-approval,
and contracts already sent would carry a version label whose text no longer matches the file.
Shipping two new files keeps the monthly path byte-identical. It costs duplicated legal text: four
files to keep in sync from now on. That trade-off is acceptable here, because the text changes only
when the law firm changes it.

- `aqd/templates/operating_pct_v2_2.html` is a copy of `operating_v2_2.html` with edits T1–T8.
- `aqd/templates/operating_ouja_pct_v2_2.html` is a copy of `operating_ouja_v2_2.html` with the same edits.
- With these names, `template_model()` still returns 'owner' / 'ouja' from the prefix,
  `template_version()` returns "2.2", and `known_templates()` picks both files up.
- New `TEMPLATE_LABELS` entries: «نموذج (أ) — حساب المالك 2.2 — نسبة تنظيف» and «نموذج (ب) — حساب عوجا 2.2 — نسبة تنظيف».

### Routing — `aqd/config.py`, `aqd/engine.py`
- `TEMPLATES_PCT = {("individual","owner"): "operating_pct_v2_2", ("individual","ouja"): "operating_ouja_pct_v2_2"}`.
- New helper `template_fee_model(name)` returns 'pct' when `"_pct_"` is in the name, else 'monthly'.
- `template_for_key(kind, model, fee_model="monthly")` reads `TEMPLATES_PCT` when `fee_model == "pct"`.
  The `AQD_TEMPLATE` override still applies only to the monthly owner route.
- `active_templates()` lists both maps, so Settings shows the two new templates as waiting for approval.
- `engine.template_for(clean)` passes `clean.get("fee_model") or "monthly"`. Old drafts have no
  `fee_model`, so they stay on monthly.
- `engine.template_fits(clean, sent_name)` additionally requires the same fee model. Without that,
  editing a sent monthly contract's answers to pct, or the reverse, could make a frozen text signable
  under the other model's answers.

### Survey — `aqd/catalogue.py`
- New contract-level field in the UNITS step, before `units_count`:
  `fee_model` (choice, required, default "monthly"). Options: «رسوم تشغيل شهرية لكل وحدة» /
  «نسبة تنظيف بدل الرسوم الشهرية».
- New fields in TERMS, right after `op_pct_other`:
  - `clean_pct` (choice 3/5/7/other, default 5, `show_if fee_model=[pct]`).
  - `clean_pct_other` (number 1–15, step 0.5, `show_if fee_model=[pct], clean_pct=[other]`).
- `validate()`: when `clean["fee_model"] == "pct"`, the unit loop skips `monthly_fee` and
  `monthly_fee_other`, so they are neither validated nor stored. Unit `show_if` only sees the unit
  dict, so this needs an explicit skip and can't be done through `show_if`.
- New `clean_pct_value(clean)`, a mirror of `op_pct_value`.

### Rendering — `aqd/engine.py`
- Add `"clean_pct"` to `EXTRA_KEYS`. `build_context` sets `h(pct(clean_pct_value(a)))`, or "—" when absent.
- `unit_rows(a)` omits the fee cell when `fee_model == "pct"`, so it emits 8 cells to match the pct
  templates' 8-column header.

### Exact text edits in the two pct templates (T1–T8)
- **T1, header row:** `{{op_pct}}% ثابتة من صافي الإيرادات + نسبة التنظيف {{clean_pct}}% من صافي الإيرادات`
- **T2, unit table:** drop the «رسوم التشغيل الشهرية» `<th>`.
- **T3, Art. 10 ¶2:** «وهي غير ما تقابله رسوم التشغيل الشهرية وفق الفقرة (1)…» → «وهي غير ما تقابله نسبة التنظيف وفق الفقرة (1)…».
- **T4, Art. 10 ¶3:**
  - (أ): «تستحق للمشغّل نسبة التنظيف المبيّنة في صدر العقد من صافي إيرادات كل حجز وفق المادة الثانية عشرة.»
  - (ب): the same sentence, ending «…وفق المادة الثانية عشرة، والمصروفات المؤيدة بفواتيرها وفق المادة الثالثة عشرة.»
- **T5, Art. 12, whole article replaced (approved wording):**
  > **المادة الثانية عشرة: نسبة التنظيف**
  > ١. يستحق المشغّل نسبة التنظيف المبيّنة في صدر العقد من صافي إيرادات كل حجز يدخل في فترة المحاسبة، وتقابل: أعمال التنظيف بين الإقامات، واستقبال السياح ومغادرتهم، والتنظيف العميق الدوري كل (45) يوماً، دون أي مقابل إضافي. ولا تشمل ما تقابله رسوم التنظيف وفق الفقرة (2) من المادة العاشرة.
  > ٢. تُحتسب نسبة التنظيف مع نسبة التشغيل في كشف فترة المحاسبة وتُفوتر معها، ولا تُستحق عن الوحدات رسوم تشغيل شهرية.
- **T6, Art. 10 statement list:**
  - (ب): «ورسوم التشغيل الشهرية» → «ونسبة التنظيف».
  - (أ): add «ونسبة التنظيف» after «ونسبة التشغيل» (Q2 approved).
- **T7, compensation table (early termination):** «(نسبة التشغيل ورسوم التشغيل الشهرية)» →
  «(نسبة التشغيل ونسبة التنظيف)», and «بعد نسبة التشغيل ورسوم التشغيل الشهرية» → «بعد نسبة التشغيل ونسبة التنظيف».
- **T8, Annex (د):** the row «رسوم التشغيل الشهرية | | الفواتير الشهرية» → «نسبة التنظيف ({{clean_pct}}%) | | —».

Guard: after these edits, the two pct files contain **zero** occurrences of «رسوم التشغيل الشهرية»
outside the T5 sentence «ولا تُستحق عن الوحدات رسوم تشغيل شهرية». A test enforces this.

### Tab and sign page — `aqd/static/aqd_tab.js`, `aqd/static/sign.js`, `aqd/routes.py`
- The tab renders fields from the schema, so the new fields appear without new markup. The unit
  form must also hide the fee fields when `a.fee_model === 'pct'`, mirroring the server skip.
- Review card: show «نسبة التنظيف X%». Fix the fees summary at line ~629 so it does not run when the model is pct.
- Sign page summary: add a «نسبة التنظيف» item next to «نسبة التشغيل» when present
  (`routes._summary_fields` returns `clean_pct`, read from the answers. No DB column, because
  `answers_json` already holds it).

### Tests (TDD, written first) — `tests/test_aqd_engine.py`, `tests/test_aqd_routes.py`
1. Routing: pct + owner → `operating_pct_v2_2`; pct + ouja → `operating_ouja_pct_v2_2`; no `fee_model` → monthly (old drafts).
2. `template_fits` is False across fee models and True within one.
3. Validation: in pct mode, unit fees are absent from clean and invalid fees raise no error. `clean_pct` rejects 0 and 16, and accepts 2.5.
4. Render: a pct contract contains «نسبة التنظيف 5%» and the approved Art. 12 text verbatim,
   has no «رسوم التشغيل الشهرية» (except the T5 phrase), its unit rows have 8 cells, and no `{{` is left.
5. Monthly regression: `git diff` of the two 2.2 files is empty, and a monthly contract renders byte-identical to before (hash pinned in the test).
6. Approval: the new templates start unapproved; sending is refused until approved; approving one does not approve the other.
7. Then the full CLAUDE.md verification routine, plus `node --check` on both aqd JS files, plus a
   Playwright pass of the tab at 390×844 and 1280×860 (create a pct draft, preview, sign page).

### Where the work happens
New worktree `../ouja-wt-aqdpct`, branch `feat/aqd-clean-pct`, cut from `origin/main`. This checkout
stays untouched, because it is parked on feat/musaed-v2. No push until the owner says so. A push to main
deploys to Railway, and even then pct contracts cannot be sent until the owner approves the two new
templates in Settings.

**Undo:** one `git revert` of the merge commit. Monthly contracts are unaffected either way.
