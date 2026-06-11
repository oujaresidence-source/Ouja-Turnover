/* Ouja Finance ERP v2 — front-end.
   Slice 1: shell + اليوم. Slice 2: البنك (upload → preview → confirm, full
   register with server pagination, real-Daftra-chart classification, keyboard
   flow, bulk select). Architecture rules R1–R8 from the build prompt. */
(function () {
  'use strict';

  /* ---------------- tiny helpers ---------------- */
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtAmt(x) {
    var n = Number(x);
    if (!isFinite(n)) return esc(x);
    return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  var store = {
    lang: (function () { try { return localStorage.getItem('erp_lang') || 'ar'; } catch (e) { return 'ar'; } })(),
    token: (new URLSearchParams(location.search)).get('token') || '',
    view: 'today',
    D: {},                     // per-view data cache
    chart: null,               // Daftra chart cache {accounts, cost_centers, units, byId}
    pendingFile: null,
    sel: {}                    // bank bulk selection {id:true}
  };

  /* ---------------- i18n ---------------- */
  var T = {
    ar: {
      dir: 'rtl', app: 'المركز المالي',
      ws_today: 'اليوم', ws_bank: 'البنك', ws_match: 'المطابقة', ws_exp: 'المصاريف',
      ws_custody: 'العهد', ws_owners: 'الملاك', ws_close: 'الإقفال', ws_stmts: 'القوائم',
      ws_budget: 'الميزانية', ws_setup: 'الإعدادات',
      soon: 'قريبًا', slice: 'شريحة',
      health: 'صحة البيانات', health_steps: 'خطوة جاهزة',
      bank_today: 'آخر استيراد بنك: اليوم', bank_days_1: 'آخر استيراد بنك: قبل يوم',
      bank_days_n: 'آخر استيراد بنك: قبل {n} أيام', bank_never: 'ما فيه استيراد بنك بعد',
      next_best: 'الإجراء الأهم الحين',
      g_approvals: 'تحتاج اعتماد فيصل (≥ 3000)', g_approvals_hint: 'مبالغ طالعة كبيرة — تتحرك بس بقرارك',
      g_unclassified: 'حركات بنك بدون تصنيف', g_unclassified_hint: 'افتحها من «البنك» وصنّفها بالكيبورد',
      g_suggested: 'مطابقات مقترحة من دافترة', g_suggested_hint: 'القرار النهائي يفتح في «المطابقة» (شريحة ٤)',
      g_contracts: 'عقود بدون مركز تكلفة', g_contracts_hint: 'اربطها من «الإعدادات»',
      g_imports: 'استيرادات متعثرة أو قديمة', g_imports_hint: '',
      more: 'غيرها', open_bank: 'افتح البنك',
      approve: 'اعتماد', reject: 'رفض', clarify: 'استيضاح',
      reject_reason: 'سبب الرفض (إلزامي)…', clarify_reason: 'وش تبي يوضّحون؟ (اختياري)…',
      confirm_reject: 'تأكيد الرفض', confirm_clarify: 'إرسال الاستيضاح', cancel: 'إلغاء',
      waiting_faisal: 'بانتظار فيصل',
      approved_ok: 'تم الاعتماد ✓', rejected_ok: 'تم الرفض', clarified_ok: 'أُرسل طلب الاستيضاح',
      act_failed: 'ما صار شي — حاول مرة ثانية',
      empty_today: 'قائمة الشغل صافية — ما عليك شي اليوم ✓',
      empty_today_sub: 'كل الموافقات والتصنيفات والمطابقات خالصة.',
      load_err: 'تعذّر تحميل البيانات', retry: 'حاول مرة ثانية',
      conf: 'تطابق', journal: 'قيد', sar: 'ر.س',
      stale: 'قديم', failed: 'فشل', src_bank: 'البنك', src_daftra: 'دافترة', src_contracts: 'العقود',
      /* --- bank --- */
      bk_upload: 'استيراد كشف الراجحي', bk_drop: 'اسحب ملف الكشف هنا أو اضغط للاختيار',
      bk_refresh_chart: 'تحديث دليل الحسابات', refreshing: 'يحدّث من دافترة…',
      chart_done: 'تحدّث الدليل ✓', bk_search: 'بحث بالوصف أو المرجع أو المبلغ…',
      f_all: 'الكل', f_needs: 'تحتاج تصنيف', f_done: 'تمت', f_unmatched: 'غير مطابق', f_ge3000: '3000+',
      th_date: 'التاريخ', th_desc: 'الوصف', th_amount: 'المبلغ', th_pipe: 'المسار', th_class: 'التصنيف',
      chip_classified: 'مُصنّف', chip_verified: 'مُتحقق', chip_migrated: 'مُرحّل',
      classify: 'صنّف', edit_class: 'تعديل', clear_class: 'إزالة التصنيف',
      acc_search: 'ابحث في دليل الحسابات (الاسم أو الكود)…',
      acc_none: 'ما لقينا حساب يطابق — الدليل المستورد فقط (النص الحر مرفوض)',
      cc_label: 'مركز التكلفة (اختياري)', cp_label: 'الطرف الآخر', unit_label: 'الوحدة (اختياري)',
      save: 'حفظ', none: 'بدون',
      classified_ok: 'صُنّفت ✓', classified_n: 'صُنّفت {n} حركة ✓', uncls_ok: 'انشالت — رجعت «تحتاج تصنيف»',
      prev_title: 'معاينة الاستيراد', prev_new: 'جديدة', prev_dups: 'مكررة (محمية)', prev_rows: 'صف مقروء',
      prev_file: 'الملف', confirm_import: 'تأكيد الاستيراد', import_ok: 'تم: {n} جديدة · {d} مكررة',
      kbd_hint: '↑↓ تنقّل · Enter صنّف · 1-3 اقتراح · S تخطٍّ · X تحديد',
      bulk_selected: 'محدد', bulk_classify: 'صنّف المحدد', bulk_clear: 'إلغاء التحديد',
      page: 'صفحة', of: 'من', rows_total: 'حركة',
      empty_bank: 'ما فيه حركات تطابق الفلتر', empty_bank_all: 'السجل فاضي — ابدأ باستيراد كشف البنك',
      sugg: 'اقتراح',
      /* --- rules + setup --- */
      mk_rule: 'طبّق على المشابهة (قاعدة)', rule_contains: 'الوصف يحتوي…',
      rule_dir_any: 'أي اتجاه', rule_dir_out: 'طالع فقط', rule_dir_in: 'داخل فقط',
      rule_created: 'انحفظت القاعدة وطبّقت على {n} حركة', rule_created_0: 'انحفظت القاعدة ✓',
      auto_chip: 'صُنّف تلقائيًا — قاعدة', undo: 'تراجع',
      undo_ok: 'رجعناها «تحتاج تصنيف» وضعّفنا القاعدة',
      rules_applied_toast: 'القواعد صنّفت {n} حركة تلقائيًا',
      setup_rules: 'قواعد التصنيف', setup_rules_hint: 'تنطبق تلقائيًا على كل استيراد — ومبالغ ٣٠٠٠+ تظل تحتاج اعتماد فيصل دايمًا',
      setup_contracts: 'ربط العقود بمراكز التكلفة', setup_contracts_hint: 'العقد بدون مركز تكلفة ما يدخل في ربحية الوحدة',
      rl_matcher: 'الشرط', rl_target: 'الحساب', rl_hits: 'تطبيقات', rl_strength: 'القوة',
      rl_on: 'فعّالة', rl_off: 'موقوفة', rl_delete: 'حذف', rl_empty: 'ما فيه قواعد بعد — أنشئها من شاشة البنك عند التصنيف',
      precision_btn: 'قِس دقة القواعد', precision_hint: 'إعادة تشغيل القواعد على المصنّف يدويًا',
      pr_matched: 'طابقت', pr_agree: 'اتفقت', pr_precision: 'الدقة', pr_pending: 'بتُطبّق على',
      pr_overall: 'الدقة الإجمالية', pr_ground: 'أساس القياس: {n} حركة مصنّفة يدويًا',
      link_cc: 'اربط', linked_ok: 'انربط ✓', pick_cc: 'اختر مركز التكلفة…',
      all_linked: 'كل العقود مربوطة بمراكز تكلفة ✓', unlinked_n: '{n} بدون مركز تكلفة',
      open_setup: 'افتح الإعدادات',
      /* --- matching --- */
      me_all: 'الكل', me_daftra: 'دافترة', me_exp: 'مصاريف', me_founder: 'مؤسس وبطاقات',
      me_hostaway: 'Hostaway', me_none: 'بدون مرشح',
      m_accept: 'اعتماد', m_reject: 'رفض', m_split: 'تقسيم', m_nocp: 'ما له مقابل',
      m_kbd: '↑↓ تنقّل · ←→ اختيار مرشح · A اعتماد · R رفض · S تقسيم/تفاصيل · N ما له مقابل',
      m_accepted: 'انربطت ✓', m_rejected: 'انشال الترشيح', m_promoted: 'انعمل قيد داخلي (مسودة) ✓',
      m_empty: 'ما فيه حركات بدون مقابل — المطابقة خالصة ✓',
      m_approx: 'تقريبي', m_score: 'تطابق',
      m_drawer_title: 'قيود دافترة المقترحة', m_lines_sum: 'مجموع المحدد', m_txn_amt: 'مبلغ الحركة',
      m_link_sel: 'اربط المحدد', m_not_dup: 'مو نفس القيد', m_ignore: 'تجاهل الحركة',
      m_consumed: 'مستهلك', m_no_sugg: 'ما فيه قيود مقترحة لهالحركة',
      m_promote_confirm: 'ينشئ قيد داخلي «مسودة» لهالحركة — يترحّل لدافترة فقط عبر الترحيل. متأكد؟',
      m_blocked: 'محجوبة: ', m_decision_log: 'سجل القرارات',
      m_sum_mismatch: 'المجموع لازم يساوي مبلغ الحركة',
      /* --- expenses + custody --- */
      x_pending: 'قيد الاعتماد', x_approved: 'معتمدة', x_exported: 'مصدّرة',
      x_verified: 'متحققة', x_needs_action: 'تحتاج إجراء',
      x_search: 'بحث بالشقة أو الفئة أو المرسل…',
      x_approve: 'اعتماد', x_reject: 'رفض', x_edit: 'تعديل', x_export: 'تصدير', x_recheck: 'تحقق الآن',
      x_receipt: 'الفاتورة', x_no_receipt: 'بدون فاتورة مرفقة',
      x_bank_ok: 'مرتبط بالبنك ✓', x_bank_no: 'بدون ربط بنكي',
      x_approved_ok: 'اعتُمدت ✓', x_approved_n: 'اعتُمدت {n} ✓', x_blocked_n: '{n} محجوبة',
      x_rejected_ok: 'رُفضت', x_exported_ok: 'أُرسلت للتصدير', x_export_skip: '{n} تخطّيناها',
      x_verified_ok: 'اتحققت ✓', x_not_found: 'ما لقيناها في Hostaway',
      x_saved: 'انحفظ التعديل ✓', x_more: 'تحميل المزيد',
      x_empty: 'ما فيه مصاريف في هالتبويب',
      x_dryrun: 'وضع التجربة فعّال — التصدير ملف فقط',
      x_missing: 'ناقص: ', x_by: 'من', x_open_match: 'افتح المطابقة',
      x_amount: 'المبلغ', x_date: 'التاريخ', x_apartment: 'الشقة', x_category: 'الفئة',
      x_vendor: 'المورد', x_note: 'ملاحظة', x_reject_reason: 'سبب الرفض (إلزامي)…',
      x_timeline: 'السجل الزمني', x_payload: 'اللي بينرسل لـ Hostaway',
      /* custody */
      c_title: 'العهد — السلف المفتوحة',
      c_explain: 'العهدة = مبلغ يُعطى للموظف ثم يُقفل بالفواتير. التحويل يثبتها: مدين عهدة الموظف / دائن البنك. الفواتير تقفلها: مدين مصاريف متعددة / دائن عهدة الموظف — بدون حركة بنك جديدة، لذلك لا تتكرر كمصروف بنكي.',
      c_outstanding_note: 'الرصيد القائم = ما صُرف − ما أُقفل بالفواتير. صفر = العهدة مكتملة.',
      c_employee: 'الموظف / حساب العهدة', c_issued: 'صُرف', c_settled: 'أُقفل',
      c_outstanding: 'القائم', c_entries: 'قيود',
      c_total: 'إجمالي القائم', c_open: 'عهد مفتوحة', c_done: 'مكتملة ✓',
      c_empty: 'ما فيه حسابات عهد في قيود دافترة المستوردة',
      c_settle_cta: 'طابق تسويات البنك (مؤسس وبطاقات)',
      /* --- owners --- */
      o_title: 'الملاك — كشوفات وروابط',
      o_hint: 'لكل مالك رابط واحد لكل وحداته — يفتح الكشف الحي بدون تسجيل دخول',
      o_units: 'وحدة', o_no_link: 'ما انعمل رابط', o_active: 'نشط', o_revoked: 'موقوف',
      o_opens: 'فتحات', o_last_open: 'آخر فتح', o_never: 'ما انفتح بعد',
      o_copy: 'نسخ الرابط', o_copied: 'انتسخ ✓', o_preview: 'معاينة كمالك',
      o_regen: 'تجديد الرابط', o_revoke: 'إيقاف', o_create: 'إنشاء رابط',
      o_regen_confirm: 'تجديد الرابط يقتل الرابط القديم نهائيًا — المالك يحتاج الرابط الجديد. نكمل؟',
      o_revoke_confirm: 'إيقاف الرابط يمنع المالك من فتح كشفه. نكمل؟',
      o_done: 'تم ✓', o_empty: 'ما فيه ملاك في السجل — أضفهم من كشوفات الملاك',
      o_mgmt: 'نسبة الإدارة',
      /* --- statement diagnosis (slice 0b) --- */
      o_diag: 'تشخيص', dg_back: '← رجوع للملاك', dg_title: 'تشخيص الكشف',
      dg_month: 'الشهر', dg_now: 'صافي الكشف الحين', dg_prefix: 'الرقم قبل الإصلاح (محاكاة)',
      dg_fixed: 'الصافي بعد الإصلاح', dg_lost_tr: 'دخل كان ضايع بسبب الكاش المبتور',
      dg_lost_unit: 'دخل وحدة ما كانت مسجّلة', dg_units: 'الوحدات',
      dg_rows: 'كل الحجوزات المرشحة — حجز بحجز', dg_included: 'محسوب', dg_excluded: 'مستبعد',
      dg_cache_miss: 'ما يشوفه النظام القديم', dg_unit_fix: 'وحدة أُضيفت بالإصلاح',
      dg_field_hist: 'الحقول الموجودة فعليًا على حجوزات الشهر',
      dg_empty: 'ما فيه حجوزات مرشحة في هالفترة', dg_ref: 'مرجع',
      dg_excl_total: 'قيمة مستبعدة بانتظار تأكيد', dg_lid_missing: 'بدون ربط Hostaway!',
      rsn_missing_payout: 'ما وصل payout من Airbnb', rsn_missing_base: 'بدون مبلغ أساس',
      rsn_needs_channel_rule: 'قناة بدون قاعدة', rsn_cancelled_refunded: 'ملغي — مسترد',
      rsn_unpaid_yet: 'غير مدفوع بعد', rsn_out_of_period: 'خارج الفترة',
      rsn_missing_paid_amount: 'مدفوع جزئيًا بدون مبلغ', rsn_status: 'حالة غير مؤكدة',
      rsn_outside_contract: 'وحدة خارج فترة العقد',
      /* --- owner manager (slice 1) --- */
      o_manage: 'إدارة', om_title: 'إدارة المالك', om_phone: 'الجوال (واتساب)',
      om_notes: 'ملاحظات', om_active: 'نشط', om_paused: 'موقوف', om_save: 'حفظ البيانات',
      om_saved: 'انحفظت ✓', om_units: 'الشقق', om_add_unit: 'أضف شقة',
      om_search_listing: 'ابحث في الشقق (الاسم)…', om_taken: 'مسجلة لـ',
      om_code: 'كود الشقة بالكشف', om_from: 'بداية العقد', om_to: 'نهاية العقد',
      om_open_ended: 'مفتوح', om_mgmt: 'نسبة الإدارة %', om_cleaning: 'النظافة',
      om_cl_ours: 'على عوجا', om_cl_owner: 'يدفعها المالك (شهري)', om_cl_amount: 'مبلغ النظافة/شهر',
      om_add_do: 'إضافة الشقة', om_added: 'انضافت ✓',
      om_terms_btn: 'تعديل الشروط', om_terms_title: 'تغيير بتاريخ سريان',
      om_terms_from: 'يسري من تاريخ', om_terms_hint: 'التغيير ما يلمس الشهور الماضية — كل شهر يقرأ الشروط اللي كانت سارية فيه',
      om_terms_save: 'حفظ التغيير', om_terms_saved: 'انحفظ — يسري من {d}',
      om_remove_btn: 'إنهاء العقد', om_remove_title: 'إنهاء عقد الشقة',
      om_remove_hint: 'إزالة ناعمة: الشهور الماضية تظل تنحسب — والشهور بعد التاريخ تستبعدها',
      om_reason: 'السبب (إلزامي)…', om_remove_do: 'تأكيد الإنهاء', om_removed: 'انتهى العقد',
      om_history: 'سجل التغييرات', om_no_changes: 'ما فيه تغييرات بعد',
      om_contract: 'العقد', om_terms_n: 'تغييرات الشروط', om_now: 'الحالي',
      /* --- statement editor (slice 2) --- */
      o_stmt: 'الكشف', se_title: 'محرر الكشف', se_pub: 'نشر النسخة للمالك',
      se_pub_confirm: 'بينشر هالأرقام للمالك (الرابط الحي + PDF سوا) ويرفع رقم النسخة. نتأكد؟',
      se_pubd: 'نُشرت نسخة {v} ✓', se_ver: 'نسخة', se_never_pub: 'ما انشرت بعد',
      se_recompute: 'أعد الحساب', se_diff_title: 'فرق إعادة الحساب (المنشور ← الجديد)',
      se_diff_none: 'ما تغيّر شي — المنشور مطابق للحساب الجديد ✓',
      se_diff_apply: 'انشر النسخة الجديدة', se_why: 'ليش؟',
      se_income: 'الدخل', se_fees: 'رسوم الإدارة', se_expenses: 'المصاريف',
      se_cleaning: 'النظافة', se_adjust: 'التسويات', se_net: 'الصافي',
      se_resv: 'الحجوزات', se_excluded: 'المستبعدة', se_exclude: 'استبعد',
      se_include: 'احسبه', se_amount_req: 'المبلغ المستلم فعليًا (إلزامي للإدراج)',
      se_reason_req: 'السبب (إلزامي)…', se_manual_chip: 'تسوية يدوية',
      se_exp_edit: 'تعديل', se_exp_del: 'حذف', se_exp_add: 'أضف مصروف يدوي',
      se_adj_add: 'أضف تسوية (±)', se_adj_label: 'وصف التسوية', se_amount: 'المبلغ',
      se_date: 'التاريخ', se_desc: 'الوصف', se_save: 'حفظ', se_saved: 'انحفظ ✓',
      se_audit: 'سجل التعديلات', se_audit_empty: 'ما فيه تعديلات على هالكشف',
      se_tab_stmt: 'الكشف', se_tab_audit: 'السجل',
      se_excl_chip_manual: 'مستبعد يدويًا', se_incl_chip: 'مُدرج يدويًا',
      se_pct: 'النسبة', se_fee_grp: 'أساس {b} × {p}٪',
      se_footnotes: 'ملاحظات العقد', se_open_page: 'افتح صفحة المالك',
      se_asof: 'آخر تحديث للبيانات',
      /* --- monthly cycle board (slice 3) --- */
      cy_title: 'دورة الشهر', cy_month: 'الشهر',
      cy_ready: 'جاهز', cy_sent: 'أُرسل', cy_opened: 'انفتح', cy_flagged: 'يحتاج مراجعة',
      cy_portfolio: 'صافي المحفظة', cy_done: 'الشهر مكتمل — كل الكشوفات أُرسلت ✓',
      cy_review_first: 'راجع هذي قبل الإرسال',
      cy_s_draft: 'مسودة', cy_s_ready: 'جاهز للمراجعة', cy_s_reviewed: 'راجعتها',
      cy_s_sent: 'أُرسلت', cy_s_opened: 'فتحها المالك',
      cy_wa: 'أرسل واتساب', cy_wa_no_phone: 'أضف جوال المالك من «إدارة» أول',
      cy_wa_sent: 'انفتح واتساب — وعلّمناها «أُرسلت» ✓',
      cy_bulk_to: 'انقل المحدد إلى', cy_selected: 'محدد',
      cy_regen_all: 'جدّد كل الروابط', cy_regen_confirm: 'بيموت كل رابط قديم عند كل الملاك — لازم ترسل الروابط الجديدة للجميع. متأكد؟',
      cy_regen_done: 'تجدّدت {n} روابط — انسخها وأرسلها',
      cy_copy_all: 'انسخ كل الروابط', cy_copied_n: 'انتسخت {n} روابط ✓',
      cy_template: 'قالب الواتساب', cy_template_hint: 'المتغيرات: {owner} {month} {net} {link}',
      cy_template_saved: 'انحفظ القالب ✓', cy_no_link: 'بدون رابط نشط',
      cy_all: 'الكل', cy_anom_none: 'سليم ✓',
      /* --- v2.2 slice 1: the month must never lie --- */
      mm_running: 'شهر جاري — اليوم {d} من {n}', mm_sofar: 'حتى الآن',
      mm_proj: 'متوقع بنهاية الشهر', mm_est: 'تقديري — وتيرة خطية',
      mm_final: 'نهائي', mm_cur: 'جاري',
      mm_cmp: 'أول {d} يوم من {pm}: {a} — {cm}: {b}',
      mnames: ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'],
      /* --- today: budget group --- */
      g_budget: 'تنبيهات الميزانية', g_budget_hint: 'حسابات وصلت ٩٠٪ أو تعدّت ميزانية الشهر',
      /* --- statements --- */
      st_month: 'الشهر', st_export_x: 'Excel', st_export_p: 'PDF',
      st_bs: 'قائمة المركز المالي', st_is: 'قائمة الدخل', st_eq: 'قائمة التغير في حقوق الملكية',
      st_cf: 'قائمة التدفقات النقدية (مباشرة)',
      st_assets: 'الأصول', st_liab: 'الخصوم', st_equity: 'حقوق الملكية',
      st_untyped: 'غير مصنّف النوع', st_earn: 'أرباح جارية',
      st_balanced: 'متوازنة ✓', st_gap: 'فيه فجوة — ما نتظاهر بالتوازن:',
      st_income: 'الإيرادات', st_expenses: 'المصروفات', st_net: 'صافي الدخل',
      st_prior: 'الفترة السابقة', st_by_cc: 'حسب مركز التكلفة / الوحدة',
      st_opening: 'الرصيد الافتتاحي', st_net_inc: 'صافي الدخل', st_contrib: 'إضافات الملاك',
      st_withdraw: 'مسحوبات', st_closing: 'الرصيد الختامي', st_ties: 'تطابق المركز المالي ✓',
      st_cf_income: 'من الإيرادات', st_cf_expense: 'مصروفات', st_cf_asset: 'أصول',
      st_cf_liability: 'التزامات', st_cf_equity: 'حقوق/مالك', st_cf_untyped: 'غير مصنّف',
      st_net_cash: 'صافي التدفق', st_open_cash: 'نقد افتتاحي', st_close_cash: 'نقد ختامي',
      st_bank_delta: 'حركة سجل البنك', st_bank_tie: 'مطابق لسجل البنك ✓', st_bank_gap: 'فرق عن سجل البنك:',
      st_coverage: 'حساب بنوع من دافترة', st_untyped_n: '{n} حساب بدون نوع — كمّل أنواعها في دافترة ثم حدّث الدليل',
      st_drill_empty: 'ما فيه حركات لهالحساب في الفترة',
      /* --- close --- */
      cl_title: 'إقفال الشهر', cl_checks: 'قائمة الإقفال',
      ck_bank_classified: 'كل حركات البنك مصنّفة', ck_matching_done: 'المطابقة ١٠٠٪',
      ck_expenses_approved: 'المصاريف معتمدة', ck_owners_balanced: 'كشوفات الملاك متوازنة',
      ck_approvals_clear: 'ما فيه موافقات معلّقة',
      cl_close_btn: 'إقفال الشهر (نهائي)', cl_closed: 'الشهر مقفول ✓',
      cl_confirm: 'الإقفال نهائي وما ينعكس — ينشئ لقطة ثابتة ويفتح الترحيل لدافترة. متأكد؟',
      cl_closed_at: 'أُقفل', cl_by: 'بواسطة',
      cl_remaining: 'باقي', cl_item: 'بند',
      mg_title: 'الترحيل إلى دافترة', mg_hint: 'يفتح بعد الإقفال — معاينة أولًا، والتأكيد يدفع مرة واحدة فقط (مفاتيح المصدر تمنع التكرار)',
      mg_preview: 'معاينة (Dry-run)', mg_confirm: 'ترحيل فعلي', mg_locked: 'مقفول لين تقفل الشهر',
      mg_disabled: 'الترحيل معطّل (DAFTRA_POST_ENABLED=0) — المعاينة شغالة والدفع الفعلي محجوب',
      mg_entries: 'قيد جاهز', mg_none: 'ما فيه قيود جاهزة للترحيل',
      mg_confirm_q: 'بيدفع {n} قيد لدافترة (مرة واحدة، بمفاتيح مصدر). نكمل؟',
      mg_done: 'تم الترحيل ✓', mg_dry_done: 'معاينة فقط — ما انكتب شي',
      mg_log: 'سجل الترحيلات', mg_issues: 'ملاحظات',
      /* --- budget --- */
      bg_title: 'ميزانية الشهر', bg_add: 'أضف حساب…', bg_amount: 'مبلغ الشهر',
      bg_weekly: 'تقسيم أسبوعي', bg_actual: 'الفعلي', bg_remaining: 'المتبقي',
      bg_used: 'استُخدم', bg_copy_last: 'انسخ الشهر الماضي', bg_avg3: 'اقتراح: متوسط ٣ أشهر',
      bg_saved: 'انحفظت ✓', bg_deleted: 'انشالت', bg_empty: 'ما فيه ميزانية لهالشهر — ابدأ بإضافة حساب أو انسخ الشهر الماضي',
      bg_weekly_err: 'مجموع الأسابيع لازم يساوي الشهر', bg_over: 'تجاوز', bg_warn: '٩٠٪+',
      bg_del_confirm: 'نشيل ميزانية هالحساب؟'
    },
    en: {
      dir: 'ltr', app: 'Finance Center',
      ws_today: 'Today', ws_bank: 'Bank', ws_match: 'Matching', ws_exp: 'Expenses',
      ws_custody: 'Custody', ws_owners: 'Owners', ws_close: 'Close', ws_stmts: 'Statements',
      ws_budget: 'Budget', ws_setup: 'Setup',
      soon: 'soon', slice: 'slice',
      health: 'Data health', health_steps: 'steps ready',
      bank_today: 'Last bank import: today', bank_days_1: 'Last bank import: 1 day ago',
      bank_days_n: 'Last bank import: {n} days ago', bank_never: 'No bank import yet',
      next_best: 'Next best action',
      g_approvals: 'Needs Faisal approval (≥ 3000)', g_approvals_hint: 'Large outgoing amounts — they move only on your decision',
      g_unclassified: 'Unclassified bank transactions', g_unclassified_hint: 'Open Bank and classify with the keyboard',
      g_suggested: 'Suggested Daftra matches', g_suggested_hint: 'Final decision opens in Matching (slice 4)',
      g_contracts: 'Contracts missing cost center', g_contracts_hint: 'Link them in Setup',
      g_imports: 'Stale or failed imports', g_imports_hint: '',
      more: 'more', open_bank: 'Open Bank',
      approve: 'Approve', reject: 'Reject', clarify: 'Clarify',
      reject_reason: 'Rejection reason (required)…', clarify_reason: 'What needs clarifying? (optional)…',
      confirm_reject: 'Confirm rejection', confirm_clarify: 'Send clarification', cancel: 'Cancel',
      waiting_faisal: 'Waiting for Faisal',
      approved_ok: 'Approved ✓', rejected_ok: 'Rejected', clarified_ok: 'Clarification requested',
      act_failed: 'Nothing changed — try again',
      empty_today: 'Work queue is clear ✓',
      empty_today_sub: 'Approvals, classification and matching are all done.',
      load_err: 'Could not load the data', retry: 'Try again',
      conf: 'match', journal: 'journal', sar: 'SAR',
      stale: 'stale', failed: 'failed', src_bank: 'Bank', src_daftra: 'Daftra', src_contracts: 'Contracts',
      bk_upload: 'Import Al Rajhi statement', bk_drop: 'Drop the statement file here or click to choose',
      bk_refresh_chart: 'Refresh chart of accounts', refreshing: 'Refreshing from Daftra…',
      chart_done: 'Chart refreshed ✓', bk_search: 'Search description, reference or amount…',
      f_all: 'All', f_needs: 'Needs classification', f_done: 'Done', f_unmatched: 'Unmatched', f_ge3000: '3000+',
      th_date: 'Date', th_desc: 'Description', th_amount: 'Amount', th_pipe: 'Pipeline', th_class: 'Classification',
      chip_classified: 'Classified', chip_verified: 'Verified', chip_migrated: 'Posted',
      classify: 'Classify', edit_class: 'Edit', clear_class: 'Clear classification',
      acc_search: 'Search the chart (name or code)…',
      acc_none: 'No matching account — imported chart only (free text rejected)',
      cc_label: 'Cost center (optional)', cp_label: 'Counterparty', unit_label: 'Unit (optional)',
      save: 'Save', none: 'None',
      classified_ok: 'Classified ✓', classified_n: 'Classified {n} txns ✓', uncls_ok: 'Cleared — back to needs-classification',
      prev_title: 'Import preview', prev_new: 'new', prev_dups: 'duplicates (blocked)', prev_rows: 'rows parsed',
      prev_file: 'File', confirm_import: 'Confirm import', import_ok: 'Done: {n} new · {d} duplicates',
      kbd_hint: '↑↓ move · Enter classify · 1-3 suggestion · S skip · X select',
      bulk_selected: 'selected', bulk_classify: 'Classify selected', bulk_clear: 'Clear selection',
      page: 'Page', of: 'of', rows_total: 'transactions',
      empty_bank: 'No transactions match this filter', empty_bank_all: 'Register is empty — start by importing a bank statement',
      sugg: 'suggestion',
      mk_rule: 'Apply to similar (rule)', rule_contains: 'Description contains…',
      rule_dir_any: 'Any direction', rule_dir_out: 'Outgoing only', rule_dir_in: 'Incoming only',
      rule_created: 'Rule saved and applied to {n} txns', rule_created_0: 'Rule saved ✓',
      auto_chip: 'Auto-classified — rule', undo: 'Undo',
      undo_ok: 'Back to needs-classification; rule weakened',
      rules_applied_toast: 'Rules auto-classified {n} txns',
      setup_rules: 'Classification rules', setup_rules_hint: 'Auto-apply on every import — 3000+ still always needs Faisal approval',
      setup_contracts: 'Link contracts to cost centers', setup_contracts_hint: 'A contract without a cost center is excluded from unit profitability',
      rl_matcher: 'Matcher', rl_target: 'Account', rl_hits: 'Hits', rl_strength: 'Strength',
      rl_on: 'Active', rl_off: 'Disabled', rl_delete: 'Delete', rl_empty: 'No rules yet — create them from the Bank screen while classifying',
      precision_btn: 'Measure rule precision', precision_hint: 'Replay rules against the human-classified rows',
      pr_matched: 'Matched', pr_agree: 'Agreed', pr_precision: 'Precision', pr_pending: 'Would apply to',
      pr_overall: 'Overall precision', pr_ground: 'Ground truth: {n} human-classified txns',
      link_cc: 'Link', linked_ok: 'Linked ✓', pick_cc: 'Pick a cost center…',
      all_linked: 'Every contract is linked to a cost center ✓', unlinked_n: '{n} without a cost center',
      open_setup: 'Open Setup',
      me_all: 'All', me_daftra: 'Daftra', me_exp: 'Expenses', me_founder: 'Founder & cards',
      me_hostaway: 'Hostaway', me_none: 'No candidate',
      m_accept: 'Accept', m_reject: 'Reject', m_split: 'Split', m_nocp: 'No counterpart',
      m_kbd: '↑↓ move · ←→ pick candidate · A accept · R reject · S split/details · N no counterpart',
      m_accepted: 'Matched ✓', m_rejected: 'Candidate dismissed', m_promoted: 'Internal DRAFT entry created ✓',
      m_empty: 'Nothing unmatched — matching is done ✓',
      m_approx: 'approx.', m_score: 'match',
      m_drawer_title: 'Suggested Daftra journals', m_lines_sum: 'Selected total', m_txn_amt: 'Txn amount',
      m_link_sel: 'Link selected', m_not_dup: 'Not the same entry', m_ignore: 'Ignore txn',
      m_consumed: 'consumed', m_no_sugg: 'No suggested journals for this txn',
      m_promote_confirm: 'Creates an internal DRAFT entry for this txn — it reaches Daftra only via migration. Sure?',
      m_blocked: 'Blocked: ', m_decision_log: 'Decision log',
      m_sum_mismatch: 'Selected lines must sum to the txn amount',
      x_pending: 'Pending', x_approved: 'Approved', x_exported: 'Exported',
      x_verified: 'Verified', x_needs_action: 'Needs action',
      x_search: 'Search apartment, category or submitter…',
      x_approve: 'Approve', x_reject: 'Reject', x_edit: 'Edit', x_export: 'Export', x_recheck: 'Verify now',
      x_receipt: 'Receipt', x_no_receipt: 'No receipt attached',
      x_bank_ok: 'Bank-matched ✓', x_bank_no: 'No bank match',
      x_approved_ok: 'Approved ✓', x_approved_n: 'Approved {n} ✓', x_blocked_n: '{n} blocked',
      x_rejected_ok: 'Rejected', x_exported_ok: 'Queued for export', x_export_skip: '{n} skipped',
      x_verified_ok: 'Verified ✓', x_not_found: 'Not found in Hostaway',
      x_saved: 'Edit saved ✓', x_more: 'Load more',
      x_empty: 'No expenses in this tab',
      x_dryrun: 'Dry-run is ON — export is file-only',
      x_missing: 'Missing: ', x_by: 'by', x_open_match: 'Open Matching',
      x_amount: 'Amount', x_date: 'Date', x_apartment: 'Apartment', x_category: 'Category',
      x_vendor: 'Vendor', x_note: 'Note', x_reject_reason: 'Rejection reason (required)…',
      x_timeline: 'Timeline', x_payload: 'Hostaway payload',
      c_title: 'Custody — open advances',
      c_explain: 'An advance is money given to an employee then settled by invoices. Issue: Dr employee custody / Cr bank. Settlement: Dr expenses / Cr custody — no new bank line, so it is never double-counted as a bank expense.',
      c_outstanding_note: 'Outstanding = issued − settled by invoices. Zero = advance fully settled.',
      c_employee: 'Employee / custody account', c_issued: 'Issued', c_settled: 'Settled',
      c_outstanding: 'Outstanding', c_entries: 'Entries',
      c_total: 'Total outstanding', c_open: 'open advances', c_done: 'Settled ✓',
      c_empty: 'No custody accounts in the imported Daftra journals',
      c_settle_cta: 'Match bank settlements (founder & cards)',
      o_title: 'Owners — statements & links',
      o_hint: 'One link per owner for all their units — opens the live statement without a login',
      o_units: 'units', o_no_link: 'No link yet', o_active: 'Active', o_revoked: 'Revoked',
      o_opens: 'opens', o_last_open: 'Last open', o_never: 'Never opened',
      o_copy: 'Copy link', o_copied: 'Copied ✓', o_preview: 'Preview as owner',
      o_regen: 'Regenerate', o_revoke: 'Revoke', o_create: 'Create link',
      o_regen_confirm: 'Regenerating kills the old link permanently — the owner needs the new one. Continue?',
      o_revoke_confirm: 'Revoking blocks the owner from opening their statement. Continue?',
      o_done: 'Done ✓', o_empty: 'No owners in the registry — add them from owner statements',
      o_mgmt: 'Mgmt %',
      o_diag: 'Diagnose', dg_back: '← Back to owners', dg_title: 'Statement diagnosis',
      dg_month: 'Month', dg_now: 'Statement net (now)', dg_prefix: 'Pre-fix number (simulated)',
      dg_fixed: 'Net after the fix', dg_lost_tr: 'Income lost to the truncated cache',
      dg_lost_unit: 'Income of an unregistered unit', dg_units: 'Units',
      dg_rows: 'Every candidate reservation — line by line', dg_included: 'Included', dg_excluded: 'Excluded',
      dg_cache_miss: 'Invisible to the old pull', dg_unit_fix: 'Unit added by the fix',
      dg_field_hist: 'Fields actually present on this month’s reservations',
      dg_empty: 'No candidate reservations in this period', dg_ref: 'reference',
      dg_excl_total: 'Excluded value awaiting confirmation', dg_lid_missing: 'No Hostaway match!',
      rsn_missing_payout: 'Airbnb payout missing', rsn_missing_base: 'No base amount',
      rsn_needs_channel_rule: 'Channel without a rule', rsn_cancelled_refunded: 'Cancelled — refunded',
      rsn_unpaid_yet: 'Not paid yet', rsn_out_of_period: 'Outside the period',
      rsn_missing_paid_amount: 'Partially paid, amount unknown', rsn_status: 'Unconfirmed status',
      rsn_outside_contract: 'Unit outside the contract window',
      o_manage: 'Manage', om_title: 'Owner manager', om_phone: 'Phone (WhatsApp)',
      om_notes: 'Notes', om_active: 'Active', om_paused: 'Paused', om_save: 'Save profile',
      om_saved: 'Saved ✓', om_units: 'Apartments', om_add_unit: 'Add apartment',
      om_search_listing: 'Search listings (name)…', om_taken: 'belongs to',
      om_code: 'Statement code', om_from: 'Contract start', om_to: 'Contract end',
      om_open_ended: 'open', om_mgmt: 'Management %', om_cleaning: 'Cleaning',
      om_cl_ours: 'On Ouja', om_cl_owner: 'Owner pays (monthly)', om_cl_amount: 'Cleaning amount/month',
      om_add_do: 'Add apartment', om_added: 'Added ✓',
      om_terms_btn: 'Change terms', om_terms_title: 'Effective-dated change',
      om_terms_from: 'Effective from', om_terms_hint: 'Past months are untouched — each month reads the terms that were active then',
      om_terms_save: 'Save change', om_terms_saved: 'Saved — effective {d}',
      om_remove_btn: 'End contract', om_remove_title: 'End this apartment’s contract',
      om_remove_hint: 'Soft removal: past months keep computing — months after the date exclude it',
      om_reason: 'Reason (required)…', om_remove_do: 'Confirm end', om_removed: 'Contract ended',
      om_history: 'Change history', om_no_changes: 'No changes yet',
      om_contract: 'Contract', om_terms_n: 'Term changes', om_now: 'now',
      o_stmt: 'Statement', se_title: 'Statement editor', se_pub: 'Publish to owner',
      se_pub_confirm: 'Publishes these numbers to the owner (live link + PDF together) and bumps the version. Continue?',
      se_pubd: 'Published version {v} ✓', se_ver: 'Version', se_never_pub: 'Not published yet',
      se_recompute: 'Recompute', se_diff_title: 'Recompute diff (published ← fresh)',
      se_diff_none: 'Nothing changed — published matches the fresh compute ✓',
      se_diff_apply: 'Publish the new version', se_why: 'Why?',
      se_income: 'Income', se_fees: 'Management fee', se_expenses: 'Expenses',
      se_cleaning: 'Cleaning', se_adjust: 'Adjustments', se_net: 'Net',
      se_resv: 'Reservations', se_excluded: 'Excluded', se_exclude: 'Exclude',
      se_include: 'Include', se_amount_req: 'Amount actually received (required to include)',
      se_reason_req: 'Reason (required)…', se_manual_chip: 'manual adjustment',
      se_exp_edit: 'Edit', se_exp_del: 'Delete', se_exp_add: 'Add manual expense',
      se_adj_add: 'Add adjustment (±)', se_adj_label: 'Adjustment label', se_amount: 'Amount',
      se_date: 'Date', se_desc: 'Description', se_save: 'Save', se_saved: 'Saved ✓',
      se_audit: 'Edit log', se_audit_empty: 'No edits on this statement',
      se_tab_stmt: 'Statement', se_tab_audit: 'Log',
      se_excl_chip_manual: 'Manually excluded', se_incl_chip: 'Manually included',
      se_pct: 'Rate', se_fee_grp: 'base {b} × {p}%',
      se_footnotes: 'Contract notes', se_open_page: 'Open owner page',
      se_asof: 'Data last updated',
      cy_title: 'Month cycle', cy_month: 'Month',
      cy_ready: 'Ready', cy_sent: 'Sent', cy_opened: 'Opened', cy_flagged: 'Needs review',
      cy_portfolio: 'Portfolio net', cy_done: 'Month complete — every statement sent ✓',
      cy_review_first: 'Review these before sending',
      cy_s_draft: 'Draft', cy_s_ready: 'Ready for review', cy_s_reviewed: 'Reviewed',
      cy_s_sent: 'Sent', cy_s_opened: 'Owner opened',
      cy_wa: 'Send WhatsApp', cy_wa_no_phone: 'Add the owner’s phone in Manage first',
      cy_wa_sent: 'WhatsApp opened — marked as Sent ✓',
      cy_bulk_to: 'Move selected to', cy_selected: 'selected',
      cy_regen_all: 'Regenerate ALL links', cy_regen_confirm: 'Every owner’s old link dies — you must resend the new ones to everyone. Continue?',
      cy_regen_done: '{n} links regenerated — copy and send them',
      cy_copy_all: 'Copy all links', cy_copied_n: 'Copied {n} links ✓',
      cy_template: 'WhatsApp template', cy_template_hint: 'Variables: {owner} {month} {net} {link}',
      cy_template_saved: 'Template saved ✓', cy_no_link: 'No active link',
      cy_all: 'All', cy_anom_none: 'Clean ✓',
      /* --- v2.2 slice 1: the month must never lie --- */
      mm_running: 'Month in progress — day {d} of {n}', mm_sofar: 'so far',
      mm_proj: 'Projected month-end', mm_est: 'estimate — linear pace',
      mm_final: 'final', mm_cur: 'in progress',
      mm_cmp: 'First {d} days of {pm}: {a} — {cm}: {b}',
      mnames: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
      g_budget: 'Budget alerts', g_budget_hint: 'Accounts at 90%+ or over this month’s budget',
      st_month: 'Month', st_export_x: 'Excel', st_export_p: 'PDF',
      st_bs: 'Balance sheet', st_is: 'Income statement', st_eq: 'Changes in equity',
      st_cf: 'Cash flow (direct)',
      st_assets: 'Assets', st_liab: 'Liabilities', st_equity: 'Equity',
      st_untyped: 'Untyped', st_earn: 'Current earnings',
      st_balanced: 'Balanced ✓', st_gap: 'There is a gap — we do not pretend:',
      st_income: 'Income', st_expenses: 'Expenses', st_net: 'Net income',
      st_prior: 'Prior period', st_by_cc: 'By cost center / unit',
      st_opening: 'Opening balance', st_net_inc: 'Net income', st_contrib: 'Owner contributions',
      st_withdraw: 'Withdrawals', st_closing: 'Closing balance', st_ties: 'Ties to balance sheet ✓',
      st_cf_income: 'From revenue', st_cf_expense: 'Expenses', st_cf_asset: 'Assets',
      st_cf_liability: 'Liabilities', st_cf_equity: 'Equity/owner', st_cf_untyped: 'Untyped',
      st_net_cash: 'Net cash', st_open_cash: 'Opening cash', st_close_cash: 'Closing cash',
      st_bank_delta: 'Bank register delta', st_bank_tie: 'Ties to bank register ✓', st_bank_gap: 'Gap vs bank register:',
      st_coverage: 'accounts typed by Daftra', st_untyped_n: '{n} accounts untyped — set their types in Daftra then refresh the chart',
      st_drill_empty: 'No lines for this account in the period',
      cl_title: 'Month close', cl_checks: 'Close checklist',
      ck_bank_classified: 'All bank txns classified', ck_matching_done: 'Matching 100%',
      ck_expenses_approved: 'Expenses approved', ck_owners_balanced: 'Owner statements balanced',
      ck_approvals_clear: 'No pending approvals',
      cl_close_btn: 'Close month (final)', cl_closed: 'Month closed ✓',
      cl_confirm: 'Closing is final and irreversible — it snapshots the month and unlocks Daftra migration. Sure?',
      cl_closed_at: 'Closed', cl_by: 'by',
      cl_remaining: 'remaining', cl_item: 'items',
      mg_title: 'Migrate to Daftra', mg_hint: 'Unlocks after close — preview first; confirm pushes ONCE (source keys prevent duplicates)',
      mg_preview: 'Preview (dry-run)', mg_confirm: 'Migrate for real', mg_locked: 'Locked until the month closes',
      mg_disabled: 'Posting disabled (DAFTRA_POST_ENABLED=0) — preview works, the real push is blocked',
      mg_entries: 'entries ready', mg_none: 'No entries ready to migrate',
      mg_confirm_q: 'Pushes {n} entries to Daftra (once, source-keyed). Continue?',
      mg_done: 'Migrated ✓', mg_dry_done: 'Dry-run only — nothing was written',
      mg_log: 'Migration log', mg_issues: 'Issues',
      bg_title: 'Month budget', bg_add: 'Add account…', bg_amount: 'Month amount',
      bg_weekly: 'Weekly split', bg_actual: 'Actual', bg_remaining: 'Remaining',
      bg_used: 'used', bg_copy_last: 'Copy last month', bg_avg3: 'Suggest: 3-month average',
      bg_saved: 'Saved ✓', bg_deleted: 'Removed', bg_empty: 'No budget for this month — add an account or copy last month',
      bg_weekly_err: 'Weeks must sum to the month', bg_over: 'over', bg_warn: '90%+',
      bg_del_confirm: 'Remove this account’s budget?'
    }
  };
  function t(k) { var v = T[store.lang][k]; return v === undefined ? (T.ar[k] || k) : v; }

  /* ---------------- API ---------------- */
  function api(path, opts) {
    var o = opts || {};
    var headers = { 'X-Token': store.token };
    var body;
    if (o.form) { body = o.form; }
    else if (o.body) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(o.body); }
    return fetch(path, { method: o.method || 'GET', headers: headers, body: body })
      .then(function (r) {
        return r.json().catch(function () { return null; }).then(function (j) {
          if (!r.ok) throw { status: r.status, body: j };
          return j;
        });
      });
  }

  /* ---------------- toasts ---------------- */
  function toast(msg, kind) {
    var box = $('#toasts');
    var el = document.createElement('div');
    el.className = 'toast ' + (kind || 'ok');
    el.textContent = msg;
    box.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('show'); });
    setTimeout(function () {
      el.classList.remove('show');
      setTimeout(function () { el.remove(); }, 250);
    }, 3500);
  }
  function srvMsg(e) {
    var b = e && e.body;
    return (b && (store.lang === 'ar' ? b.message_ar : b.message_en)) || (b && b.detail) || null;
  }

  /* ---------------- workspaces + router (R2) ---------------- */
  var WORKSPACES = [
    { id: 'today', built: true },
    { id: 'bank', built: true },
    { id: 'match', built: true },
    { id: 'exp', built: true },
    { id: 'custody', built: true },
    { id: 'owners', built: true },
    { id: 'close', built: true },
    { id: 'stmts', built: true },
    { id: 'budget', built: true },
    { id: 'setup', built: true }
  ];

  function parseHash() {
    var h = (location.hash || '#today').slice(1);
    var qi = h.indexOf('?');
    var view = qi < 0 ? h : h.slice(0, qi);
    var params = new URLSearchParams(qi < 0 ? '' : h.slice(qi + 1));
    return { view: view || 'today', params: params };
  }

  function renderNav() {
    var el = $('#wsnav');
    el.innerHTML = WORKSPACES.map(function (w) {
      var label = t('ws_' + w.id);
      if (w.built) {
        var on = store.view === w.id;
        return '<a class="ws' + (on ? ' on' : '') + '" href="#' + w.id + '"' +
               (on ? ' aria-current="page"' : '') + '>' + esc(label) + '</a>';
      }
      return '<span class="ws soon" title="' + esc(t('slice') + ' ' + w.slice) + '">' +
             esc(label) + '<em>' + esc(t('soon')) + '</em></span>';
    }).join('');
  }

  function saveScroll() {
    try { sessionStorage.setItem('erp_scroll_' + store.view, String(window.scrollY || 0)); } catch (e) {}
  }
  function restoreScroll(view) {
    var y = 0;
    try { y = Number(sessionStorage.getItem('erp_scroll_' + view) || 0); } catch (e) {}
    window.scrollTo(0, y);
  }

  function route() {
    var ph = parseHash();
    var ws = null;
    for (var i = 0; i < WORKSPACES.length; i++) if (WORKSPACES[i].id === ph.view) ws = WORKSPACES[i];
    if (!ws || !ws.built) { location.replace('#today'); return; }
    store.view = ph.view;
    renderNav();
    renderGSide();
    document.title = t('ws_' + ph.view) + ' · ' + t('app');
    VIEWS[ph.view].show(ph.params);
  }

  /* ---------------- shared render bits (R4) ---------------- */
  function skeleton(rows) {
    var s = '<div class="card sk-card">';
    for (var i = 0; i < (rows || 5); i++) s += '<div class="sk sk-row"></div>';
    return s + '</div>';
  }
  function errorCard(retryAct, detail) {
    return '<div class="card state-card"><div class="state-ico">⚠️</div>' +
      '<div class="state-h">' + esc(t('load_err')) + '</div>' +
      (detail ? '<div class="state-sub">' + esc(detail) + '</div>' : '') +
      '<button class="btn primary" data-act="' + retryAct + '">' + esc(t('retry')) + '</button></div>';
  }

  /* ================= اليوم Today ================= */
  var GROUP_META = {
    approvals: { icon: '🔏' }, budget: { icon: '📉' }, unclassified: { icon: '🏦' },
    suggested: { icon: '🔗' }, contracts: { icon: '📄' }, imports: { icon: '⬇️' }
  };

  function headerMeta(d) {
    var pct = d.health ? d.health.pct : 0;
    var arc = $('#healthArc');
    if (arc) arc.setAttribute('stroke-dasharray', (97.4 * pct / 100).toFixed(1) + ' 97.4');
    $('#healthPct').textContent = pct + '%';
    $('#healthLbl').textContent = t('health');
    var wrap = $('#healthWrap');
    if (wrap && d.health) wrap.title = d.health.done + '/' + d.health.total + ' ' + t('health_steps');
    var chip = $('#bankAge');
    if (chip) {
      var txt;
      if (d.bank_age_days === null || d.bank_age_days === undefined) txt = t('bank_never');
      else if (d.bank_age_days === 0) txt = t('bank_today');
      else if (d.bank_age_days === 1) txt = t('bank_days_1');
      else txt = t('bank_days_n').replace('{n}', d.bank_age_days);
      chip.textContent = txt;
      chip.hidden = false;
      chip.className = 'chip' + (d.bank_age_days >= 3 ? ' warn' : '');
    }
  }

  function rowApproval(it, canHigh) {
    var dirCls = it.direction === 'credit' ? 'in' : 'out';
    return '<div class="wq-row" id="wq_' + esc(it.id) + '">' +
      '<div class="wq-main">' +
        '<div class="wq-top"><span class="amt ' + dirCls + '">' + fmtAmt(it.amount) + ' <i>' + esc(t('sar')) + '</i></span>' +
        (it.apartment ? '<span class="tag">' + esc(it.apartment) + '</span>' : '') +
        (it.chip_ar ? '<span class="tag soft">' + esc(store.lang === 'ar' ? it.chip_ar : (it.chip_en || it.chip_ar)) + '</span>' : '') +
        '</div>' +
        '<div class="wq-desc">' + esc(it.desc) + '</div>' +
        '<div class="wq-sub"><code>' + esc(it.date || '') + '</code>' + (it.category ? ' · ' + esc(it.category) : '') + '</div>' +
      '</div>' +
      (canHigh
        ? '<div class="wq-actions">' +
            '<button class="btn primary sm" data-act="approve" data-id="' + esc(it.id) + '">' + esc(t('approve')) + '</button>' +
            '<button class="btn danger-ghost sm" data-act="reject" data-id="' + esc(it.id) + '">' + esc(t('reject')) + '</button>' +
            '<button class="btn ghost sm" data-act="clarify" data-id="' + esc(it.id) + '">' + esc(t('clarify')) + '</button>' +
          '</div>'
        : '<div class="wq-actions"><span class="tag soft">' + esc(t('waiting_faisal')) + '</span></div>') +
      '<div class="wq-reason" hidden></div>' +
    '</div>';
  }

  function rowInfo(main, sub) {
    return '<div class="wq-row info"><div class="wq-main"><div class="wq-top">' + main + '</div>' +
      (sub ? '<div class="wq-sub">' + sub + '</div>' : '') + '</div></div>';
  }

  function renderToday(d) {
    headerMeta(d);
    var total = 0;
    d.groups.forEach(function (g) { total += g.count; });
    var html = '';
    if (!total) {
      $('#view').innerHTML = '<div class="card state-card"><div class="state-ico ok">✓</div>' +
        '<div class="state-h">' + esc(t('empty_today')) + '</div>' +
        '<div class="state-sub">' + esc(t('empty_today_sub')) + '</div></div>';
      return;
    }
    if (d.next_best) {
      html += '<div class="next-best" data-target="grp_' + esc(d.next_best) + '">' +
        '<span class="nb-lbl">' + esc(t('next_best')) + '</span>' +
        '<span class="nb-txt">' + esc(t('g_' + d.next_best)) + '</span><span class="nb-arrow">←</span></div>';
    }
    d.groups.forEach(function (g) {
      if (!g.count) return;
      var meta = GROUP_META[g.key] || {};
      html += '<section class="card grp" id="grp_' + esc(g.key) + '">' +
        '<header class="grp-h"><span class="grp-ico">' + (meta.icon || '') + '</span>' +
        '<h2>' + esc(t('g_' + g.key)) + '</h2>' +
        '<span class="cnt" id="cnt_' + esc(g.key) + '">' + g.count + '</span></header>' +
        (t('g_' + g.key + '_hint') ? '<div class="grp-hint">' + esc(t('g_' + g.key + '_hint')) + '</div>' : '');
      if (g.key === 'approvals') {
        html += '<div class="grp-list" id="list_approvals">' +
          g.items.map(function (it) { return rowApproval(it, d.can_high); }).join('') + '</div>';
      } else if (g.key === 'unclassified') {
        html += '<div class="grp-list">' + g.items.map(function (it) {
          var amtCls = it.dir === 'in' ? 'in' : 'out';
          return rowInfo(
            '<span class="amt ' + amtCls + '">' + fmtAmt(it.amount) + ' <i>' + esc(t('sar')) + '</i></span>' +
              (it.card ? '<span class="tag">💳 ' + esc(it.card) + '</span>' : ''),
            esc(it.desc) + ' · <code>' + esc(it.date || '') + '</code>');
        }).join('') + '</div>' +
        '<div class="grp-cta"><a class="btn primary sm" href="#bank?f=needs_review">' + esc(t('open_bank')) + '</a></div>';
      } else if (g.key === 'suggested') {
        html += '<div class="grp-list">' + g.items.map(function (it) {
          return rowInfo(
            '<span class="amt">' + fmtAmt(it.amount) + ' <i>' + esc(t('sar')) + '</i></span>' +
              '<span class="tag soft">' + it.conf + '% ' + esc(t('conf')) + '</span>' +
              (it.journal_no ? '<span class="tag">' + esc(t('journal')) + ' #' + esc(it.journal_no) + '</span>' : ''),
            esc(store.lang === 'ar' ? (it.reason_ar || it.desc) : (it.reason_en || it.desc)) +
              ' · <code>' + esc(it.date || '') + '</code>');
        }).join('') + '</div>';
      } else if (g.key === 'contracts') {
        html += '<div class="grp-list">' + g.items.map(function (it) {
          return rowInfo('<b>' + esc(it.name) + '</b>', it.owner ? esc(it.owner) : '');
        }).join('') + '</div>' +
        '<div class="grp-cta"><a class="btn primary sm" href="#setup">' + esc(t('open_setup')) + '</a></div>';
      } else if (g.key === 'budget') {
        html += '<div class="grp-list">' + g.items.map(function (it) {
          return rowInfo(
            '<b>' + esc(it.name) + '</b><span class="tag ' + (it.alert === 'over' ? 'bad' : 'warnt') + '">' +
              it.pct + '%</span>',
            fmtAmt(it.actual) + ' / ' + fmtAmt(it.budget) + ' ' + esc(t('sar')));
        }).join('') + '</div>' +
        '<div class="grp-cta"><a class="btn primary sm" href="#budget">' + esc(t('ws_budget')) + '</a></div>';
      } else if (g.key === 'imports') {
        html += '<div class="grp-list">' + g.items.map(function (it) {
          var lbl = it.status === 'failed' ? t('failed') : t('stale');
          return rowInfo(
            '<b>' + esc(t('src_' + it.source) || it.source) + '</b><span class="tag ' +
              (it.status === 'failed' ? 'bad' : 'warnt') + '">' + esc(lbl) + '</span>',
            (it.file ? esc(it.file) + ' · ' : '') + '<code>' + esc(it.when || '') + '</code>' +
              (it.error ? ' — ' + esc(it.error) : ''));
        }).join('') + '</div>';
      }
      if (g.count > g.items.length) {
        html += '<div class="grp-more">+' + (g.count - g.items.length) + ' ' + esc(t('more')) + '</div>';
      }
      html += '</section>';
    });
    $('#view').innerHTML = html;
    restoreScroll('today');
  }

  function loadToday() {
    $('#view').innerHTML = skeleton(6);
    api('/erp/api/work-queue').then(function (d) {
      store.D.today = d;
      renderToday(d);
    }).catch(function (e) {
      $('#view').innerHTML = errorCard('retry_today', srvMsg(e));
    });
  }

  function setRowBusy(row, busy) {
    row.classList.toggle('busy', !!busy);
    $$('button', row).forEach(function (b) { b.disabled = !!busy; });
  }
  function patchCounters(c) {
    if (!c) return;
    ['approvals', 'unclassified', 'suggested', 'contracts'].forEach(function (k) {
      var el = $('#cnt_' + k);
      if (el && c[k] !== undefined) el.textContent = c[k];
    });
  }
  function removeRow(row) {
    var next = row.nextElementSibling;
    row.style.maxHeight = row.offsetHeight + 'px';
    requestAnimationFrame(function () { row.classList.add('leaving'); });
    setTimeout(function () {
      var list = row.parentElement;
      row.remove();
      if (next && next.querySelector) {
        var btn = next.querySelector('button');
        if (btn) btn.focus();
      }
      if (list && !list.children.length) {
        var grp = list.closest('.grp');
        if (grp) grp.remove();
      }
    }, 200);
  }
  function decide(id, decision, reason) {
    var row = document.getElementById('wq_' + id);
    if (!row) return;
    setRowBusy(row, true);
    api('/erp/api/approve', { method: 'POST', body: { id: id, decision: decision, reason: reason || '' } })
      .then(function (r) {
        patchCounters(r.counters);
        removeRow(row);
        toast(decision === 'approve' ? t('approved_ok') : decision === 'reject' ? t('rejected_ok') : t('clarified_ok'),
              decision === 'approve' ? 'ok' : 'warn');
      })
      .catch(function (e) {
        setRowBusy(row, false);
        toast(srvMsg(e) || t('act_failed'), 'err');
      });
  }
  function openReason(row, id, kind) {
    var box = row.querySelector('.wq-reason');
    if (!box) return;
    if (!box.hidden) { box.hidden = true; box.innerHTML = ''; return; }
    box.hidden = false;
    box.innerHTML =
      '<textarea class="reason-in" rows="2" placeholder="' +
        esc(kind === 'reject' ? t('reject_reason') : t('clarify_reason')) + '"></textarea>' +
      '<div class="reason-btns">' +
        '<button class="btn ' + (kind === 'reject' ? 'danger' : 'primary') + ' sm" data-act="confirm-' + kind +
          '" data-id="' + esc(id) + '">' + esc(kind === 'reject' ? t('confirm_reject') : t('confirm_clarify')) + '</button>' +
        '<button class="btn ghost sm" data-act="cancel-reason">' + esc(t('cancel')) + '</button>' +
      '</div>';
    box.querySelector('textarea').focus();
  }

  /* ================= البنك Bank ================= */
  var bankP = { f: 'all', q: '', from: '', to: '', p: 1 };

  function bankHash() {
    var ps = new URLSearchParams();
    if (bankP.f && bankP.f !== 'all') ps.set('f', bankP.f);
    if (bankP.q) ps.set('q', bankP.q);
    if (bankP.from) ps.set('from', bankP.from);
    if (bankP.to) ps.set('to', bankP.to);
    if (bankP.p > 1) ps.set('p', String(bankP.p));
    var qs = ps.toString();
    return '#bank' + (qs ? '?' + qs : '');
  }
  function pushBankHash() {
    var h = bankHash();
    if (location.hash !== h) location.hash = h;   // route() re-renders from state (R2)
    else loadBankData();
  }

  function ensureChart() {
    if (store.chart) return Promise.resolve(store.chart);
    return api('/erp/api/accounts').then(function (d) {
      var byId = {};
      d.accounts.forEach(function (a) { byId[a.id] = a; });
      store.chart = { accounts: d.accounts, cost_centers: d.cost_centers, units: d.units, byId: byId };
      return store.chart;
    });
  }

  function bankLayout() {
    return '' +
    '<div class="card bank-bar">' +
      '<div class="bb-row">' +
        '<button class="btn primary sm" data-act="bk-upload-btn">⬆ ' + esc(t('bk_upload')) + '</button>' +
        '<button class="btn ghost sm" data-act="bk-refresh-chart" id="bkRefreshChart">⟳ ' + esc(t('bk_refresh_chart')) + '</button>' +
        '<input id="bkSearch" class="in search" type="search" placeholder="' + esc(t('bk_search')) + '" value="' + esc(bankP.q) + '">' +
        '<input id="bkFrom" class="in date" type="date" value="' + esc(bankP.from) + '">' +
        '<input id="bkTo" class="in date" type="date" value="' + esc(bankP.to) + '">' +
      '</div>' +
      '<input id="bkFile" type="file" accept=".xlsx,.xls" hidden>' +
      '<div id="bkDrop" class="dropzone" hidden>' + esc(t('bk_drop')) + '</div>' +
      '<div class="bb-chips" id="bkChips"></div>' +
      '<div class="kbd-hint">' + esc(t('kbd_hint')) + '</div>' +
    '</div>' +
    '<div id="bkPreview"></div>' +
    '<div id="bkTableWrap">' + skeleton(8) + '</div>' +
    '<div class="bulkbar" id="bkBulk" hidden></div>';
  }

  function chipHtml(key, label, n, on) {
    return '<button class="fchip' + (on ? ' on' : '') + '" data-act="bk-filter" data-f="' + key + '">' +
      esc(label) + (n !== undefined ? ' <b>' + n + '</b>' : '') + '</button>';
  }

  function renderBankChips(counts) {
    var c = counts || {};
    $('#bkChips').innerHTML =
      chipHtml('all', t('f_all'), c.all, bankP.f === 'all') +
      chipHtml('needs_review', t('f_needs'), c.needs_review, bankP.f === 'needs_review') +
      chipHtml('done', t('f_done'), c.done, bankP.f === 'done') +
      chipHtml('unmatched', t('f_unmatched'), c.unmatched, bankP.f === 'unmatched') +
      chipHtml('ge3000', t('f_ge3000'), c.ge3000, bankP.f === 'ge3000');
  }

  function pipeChips(r) {
    var h = '';
    h += '<span class="pchip' + (r.classified ? ' on-blue' : '') + '">' + esc(t('chip_classified')) + '</span>';
    h += '<span class="pchip' + (r.verified ? ' on-green' : '') + '">' + esc(t('chip_verified')) + '</span>';
    h += '<span class="pchip' + (r.migrated ? ' on-purple' : '') + '">' + esc(t('chip_migrated')) +
         (r.migrated && r.journal_no ? ' #' + esc(r.journal_no) : '') + '</span>';
    if (r.dup === 'strong_possible_duplicate' || r.dup === 'possible_duplicate') {
      h += '<span class="pchip warn">' + (r.dup_conf || '') + '%</span>';
    }
    return h;
  }

  function classCell(r) {
    if (r.cls && r.cls.account_id) {
      return '<div class="cls-done"><b>' + esc(r.cls.name) + '</b>' +
        (r.cls.code ? ' <code>' + esc(r.cls.code) + '</code>' : '') +
        (r.cls.cost_center ? '<span class="tag">' + esc(r.cls.cost_center) + '</span>' : '') +
        (r.cls.unit ? '<span class="tag">' + esc(r.cls.unit) + '</span>' : '') +
        (r.cls.auto ? '<span class="tag warnt">' + esc(t('auto_chip')) + '</span>' +
          '<button class="btn ghost xs" data-act="bk-undo-rule" data-id="' + esc(r.id) + '">' + esc(t('undo')) + '</button>' : '') +
        '<button class="btn ghost xs" data-act="bk-open-cls" data-id="' + esc(r.id) + '">' + esc(t('edit_class')) + '</button></div>';
    }
    var h = '<div class="cls-todo">';
    (r.suggestions || []).slice(0, 3).forEach(function (s, i) {
      h += '<button class="sugg" data-act="bk-sugg" data-id="' + esc(r.id) + '" data-acc="' + esc(s.account_id) + '"' +
        ' title="' + esc(store.lang === 'ar' ? s.why_ar : s.why_en) + '">' +
        '<kbd>' + (i + 1) + '</kbd> ' + esc(s.name) + '</button>';
    });
    h += '<button class="btn primary xs" data-act="bk-open-cls" data-id="' + esc(r.id) + '">' + esc(t('classify')) + '</button>';
    return h + '</div>';
  }

  function bankRowHtml(r) {
    var amtCls = r.dir === 'in' ? 'in' : 'out';
    var checked = store.sel[r.id] ? ' checked' : '';
    return '<tr class="brow" tabindex="0" data-id="' + esc(r.id) + '">' +
      '<td class="c-sel"><input type="checkbox" data-act="bk-sel" data-id="' + esc(r.id) + '"' + checked + '></td>' +
      '<td class="c-date"><code>' + esc(r.date) + '</code></td>' +
      '<td class="c-desc"><div class="d1">' + esc(r.desc) + '</div>' +
        '<div class="d2">' + (r.ref ? '#' + esc(r.ref) + ' · ' : '') + (r.card ? '💳' + esc(r.card) + ' · ' : '') + esc(r.category) + '</div></td>' +
      '<td class="c-amt"><span class="amt ' + amtCls + '">' + (r.dir === 'in' ? '+' : '−') + fmtAmt(r.amount) + '</span></td>' +
      '<td class="c-pipe">' + pipeChips(r) + '</td>' +
      '<td class="c-cls">' + classCell(r) + '</td>' +
    '</tr>';
  }

  function renderBankTable(d) {
    store.D.bank = d;
    renderBankChips(d.counts);
    var w = $('#bkTableWrap');
    if (!d.rows.length) {
      var allEmpty = d.counts.all === 0 && !bankP.q && !bankP.from && !bankP.to;
      w.innerHTML = '<div class="card state-card"><div class="state-ico">🏦</div>' +
        '<div class="state-h">' + esc(allEmpty ? t('empty_bank_all') : t('empty_bank')) + '</div>' +
        (allEmpty ? '<button class="btn primary" data-act="bk-upload-btn">⬆ ' + esc(t('bk_upload')) + '</button>' : '') +
        '</div>';
      return;
    }
    var rows = d.rows.map(bankRowHtml).join('');
    var pager = '';
    if (d.pages > 1) {
      pager = '<div class="pager">' +
        '<button class="btn ghost sm" data-act="bk-page" data-p="' + (d.page - 1) + '"' + (d.page <= 1 ? ' disabled' : '') + '>‹</button>' +
        '<span class="pg-info">' + esc(t('page')) + ' <b>' + d.page + '</b> ' + esc(t('of')) + ' ' + d.pages +
        ' · ' + d.total + ' ' + esc(t('rows_total')) + '</span>' +
        '<button class="btn ghost sm" data-act="bk-page" data-p="' + (d.page + 1) + '"' + (d.page >= d.pages ? ' disabled' : '') + '>›</button>' +
      '</div>';
    }
    w.innerHTML = '<div class="card table-card"><table class="btable"><thead><tr>' +
      '<th class="c-sel"></th><th>' + esc(t('th_date')) + '</th><th>' + esc(t('th_desc')) + '</th>' +
      '<th>' + esc(t('th_amount')) + '</th><th>' + esc(t('th_pipe')) + '</th><th>' + esc(t('th_class')) + '</th>' +
      '</tr></thead><tbody id="bkBody">' + rows + '</tbody></table></div>' + pager;
    updateBulkBar();
    restoreScroll('bank');
  }

  function loadBankData() {
    var ps = new URLSearchParams();
    ps.set('f', bankP.f); ps.set('p', String(bankP.p));
    if (bankP.q) ps.set('q', bankP.q);
    if (bankP.from) ps.set('from', bankP.from);
    if (bankP.to) ps.set('to', bankP.to);
    api('/erp/api/bank?' + ps.toString()).then(renderBankTable).catch(function (e) {
      $('#bkTableWrap').innerHTML = errorCard('retry_bank', srvMsg(e));
    });
  }

  /* ----- classification panel ----- */
  function closeCls() {
    var ex = $('#clsPanelRow');
    if (ex) ex.remove();
  }

  function openCls(ids, anchorRow) {
    closeCls();
    var seedContains = '';
    if (anchorRow) {
      var d1 = anchorRow.querySelector('.c-desc .d1');
      var words = ((d1 && d1.textContent) || '').trim().split(/\s+/).filter(function (w) { return w.length > 1; });
      seedContains = words.slice(0, 2).join(' ').slice(0, 40);
    }
    ensureChart().then(function (chart) {
      var tr = document.createElement('tr');
      tr.id = 'clsPanelRow';
      var ccOpts = '<option value="">' + esc(t('none')) + '</option>' + chart.cost_centers.map(function (c) {
        return '<option value="' + esc(c.id) + '">' + esc(c.name) + '</option>';
      }).join('');
      var unitList = chart.units.map(function (u) { return '<option value="' + esc(u) + '">'; }).join('');
      tr.innerHTML = '<td colspan="6"><div class="cls-panel" data-ids="' + esc(ids.join(',')) + '">' +
        '<div class="cp-grid">' +
          '<div class="cp-acc">' +
            '<input id="clsAccIn" class="in" type="text" placeholder="' + esc(t('acc_search')) + '" autocomplete="off">' +
            '<input id="clsAccId" type="hidden">' +
            '<div id="clsAccList" class="acc-list"></div>' +
          '</div>' +
          '<label class="cp-f"><span>' + esc(t('cc_label')) + '</span><select id="clsCc" class="in">' + ccOpts + '</select></label>' +
          '<label class="cp-f"><span>' + esc(t('cp_label')) + '</span><input id="clsCp" class="in" type="text" maxlength="120"></label>' +
          '<label class="cp-f"><span>' + esc(t('unit_label')) + '</span><input id="clsUnit" class="in" type="text" list="unitsDl" maxlength="80">' +
            '<datalist id="unitsDl">' + unitList + '</datalist></label>' +
        '</div>' +
        '<div class="cp-rule">' +
          '<label class="cp-check"><input type="checkbox" id="clsMkRule"> ' + esc(t('mk_rule')) + '</label>' +
          '<span id="clsRuleFields" hidden>' +
            '<input id="clsRuleContains" class="in" type="text" placeholder="' + esc(t('rule_contains')) + '" value="' + esc(seedContains) + '" maxlength="60">' +
            '<select id="clsRuleDir" class="in">' +
              '<option value="out">' + esc(t('rule_dir_out')) + '</option>' +
              '<option value="any">' + esc(t('rule_dir_any')) + '</option>' +
              '<option value="in">' + esc(t('rule_dir_in')) + '</option>' +
            '</select>' +
          '</span>' +
        '</div>' +
        '<div class="cp-btns">' +
          '<button class="btn primary sm" data-act="bk-save-cls">' + esc(t('save')) + '</button>' +
          '<button class="btn ghost sm" data-act="bk-cancel-cls">' + esc(t('cancel')) + '</button>' +
          (ids.length === 1 ? '<button class="btn danger-ghost sm" data-act="bk-clear-cls" data-id="' + esc(ids[0]) + '">' + esc(t('clear_class')) + '</button>' : '') +
        '</div></div></td>';
      if (anchorRow && anchorRow.parentElement) anchorRow.parentElement.insertBefore(tr, anchorRow.nextSibling);
      else { var body = $('#bkBody'); if (body) body.insertBefore(tr, body.firstChild); }
      var inp = $('#clsAccIn');
      renderAccList('');
      inp.addEventListener('input', function () { renderAccList(inp.value); });
      var mk = $('#clsMkRule');
      if (mk) mk.addEventListener('change', function () { $('#clsRuleFields').hidden = !mk.checked; });
      inp.focus();
    }).catch(function (e) { toast(srvMsg(e) || t('load_err'), 'err'); });
  }

  function renderAccList(q) {
    var box = $('#clsAccList');
    if (!box || !store.chart) return;
    var qq = (q || '').trim().toLowerCase();
    var hits = store.chart.accounts.filter(function (a) {
      if (!qq) return true;
      return (a.name || '').toLowerCase().indexOf(qq) >= 0 || (a.code || '').toLowerCase().indexOf(qq) >= 0;
    }).slice(0, 12);
    if (!hits.length) { box.innerHTML = '<div class="acc-none">' + esc(t('acc_none')) + '</div>'; return; }
    box.innerHTML = hits.map(function (a) {
      return '<button class="acc-opt" data-act="bk-pick-acc" data-acc="' + esc(a.id) + '">' +
        (a.code ? '<code>' + esc(a.code) + '</code> ' : '') + esc(a.name) + '</button>';
    }).join('');
  }

  function postClassify(ids, payload, opts) {
    var body = Object.assign({ ids: ids }, payload);
    return api('/erp/api/bank/classify', { method: 'POST', body: body }).then(function (r) {
      (r.rows || []).forEach(patchBankRow);
      adjustBankCounts(r.rows ? r.rows.length : 0, payload.clear);
      patchCounters(r.counters);
      toast(payload.clear ? t('uncls_ok') :
        (ids.length > 1 ? t('classified_n').replace('{n}', ids.length) : t('classified_ok')));
      if (!(opts && opts.keepSel)) { store.sel = {}; updateBulkBar(); }
    }).catch(function (e) { toast(srvMsg(e) || t('act_failed'), 'err'); throw e; });
  }

  function patchBankRow(r) {
    var tr = document.querySelector('.brow[data-id="' + r.id + '"]');
    if (!tr) return;
    var leavingFilter =
      (bankP.f === 'needs_review' && r.status !== 'needs_review') ||
      (bankP.f === 'done' && r.status !== 'reviewed');
    tr.querySelector('.c-pipe').innerHTML = pipeChips(r);
    tr.querySelector('.c-cls').innerHTML = classCell(r);
    if (leavingFilter) {
      var next = tr.nextElementSibling;
      tr.classList.add('leaving-tr');
      setTimeout(function () {
        tr.remove();
        if (next && next.classList && next.classList.contains('brow')) next.focus();
      }, 220);
    }
  }

  function adjustBankCounts(n, cleared) {
    var d = store.D.bank;
    if (!d || !d.counts || !n) return;
    if (cleared) { d.counts.needs_review += n; d.counts.done -= n; }
    else { d.counts.needs_review = Math.max(0, d.counts.needs_review - n); d.counts.done += n; }
    renderBankChips(d.counts);
  }

  /* ----- upload flow ----- */
  function uploadBank(file, save) {
    var fd = new FormData();
    fd.append('file', file, file.name);
    if (save) fd.append('save', '1');
    return api('/erp/api/bank/upload', { method: 'POST', form: fd });
  }

  function showPreview(p, file) {
    store.pendingFile = file;
    var box = $('#bkPreview');
    var sample = (p.rows || []).slice(0, 6).map(function (r) {
      return '<tr><td><code>' + esc(r.date) + '</code></td><td>' + esc((r.desc || '').slice(0, 60)) + '</td>' +
        '<td class="c-amt">' + esc(r.debit !== '0.00' ? r.debit : r.credit) + '</td>' +
        '<td>' + (r.duplicate ? '<span class="tag bad">' + esc(t('prev_dups')) + '</span>' : '<span class="tag soft">' + esc(t('prev_new')) + '</span>') + '</td></tr>';
    }).join('');
    box.innerHTML = '<div class="card prev-card">' +
      '<div class="grp-h"><h2>' + esc(t('prev_title')) + '</h2><span class="cnt">' + esc(p.filename || '') + '</span></div>' +
      '<div class="prev-stats">' +
        '<span class="pstat ok"><b>' + p.new + '</b> ' + esc(t('prev_new')) + '</span>' +
        '<span class="pstat warn"><b>' + p.dups + '</b> ' + esc(t('prev_dups')) + '</span>' +
        '<span class="pstat"><b>' + p.count + '</b> ' + esc(t('prev_rows')) + '</span>' +
      '</div>' +
      '<table class="btable mini"><tbody>' + sample + '</tbody></table>' +
      '<div class="cp-btns">' +
        '<button class="btn primary" data-act="bk-confirm-import"' + (p.new ? '' : ' disabled') + '>' + esc(t('confirm_import')) + '</button>' +
        '<button class="btn ghost" data-act="bk-cancel-import">' + esc(t('cancel')) + '</button>' +
      '</div></div>';
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ----- bulk bar ----- */
  function selectedIds() { return Object.keys(store.sel).filter(function (k) { return store.sel[k]; }); }
  function updateBulkBar() {
    var ids = selectedIds();
    var bar = $('#bkBulk');
    if (!bar) return;
    if (!ids.length) { bar.hidden = true; bar.innerHTML = ''; return; }
    bar.hidden = false;
    bar.innerHTML = '<b>' + ids.length + '</b> ' + esc(t('bulk_selected')) +
      ' <button class="btn primary sm" data-act="bk-bulk-cls">' + esc(t('bulk_classify')) + '</button>' +
      ' <button class="btn ghost sm" data-act="bk-bulk-clear">' + esc(t('bulk_clear')) + '</button>';
  }

  /* ----- bank keyboard flow ----- */
  function focusedBankRow() {
    var a = document.activeElement;
    return a && a.classList && a.classList.contains('brow') ? a : null;
  }
  function moveFocus(delta) {
    var rows = $$('.brow');
    if (!rows.length) return;
    var cur = focusedBankRow();
    var i = cur ? rows.indexOf(cur) + delta : (delta > 0 ? 0 : rows.length - 1);
    if (i < 0) i = 0;
    if (i >= rows.length) i = rows.length - 1;
    rows[i].focus();
    rows[i].scrollIntoView({ block: 'nearest' });
  }
  function focusedMatchItem() {
    var a = document.activeElement;
    return a && a.classList && a.classList.contains('mitem') ? a : null;
  }
  function moveMatchFocus(delta) {
    var rows = $$('.mitem');
    if (!rows.length) return;
    var cur = focusedMatchItem();
    var i = cur ? rows.indexOf(cur) + delta : 0;
    if (i < 0) i = 0;
    if (i >= rows.length) i = rows.length - 1;
    rows[i].focus();
    rows[i].scrollIntoView({ block: 'nearest' });
  }
  document.addEventListener('keydown', function (ev) {
    if (store.view !== 'match') return;
    var tag = (ev.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    var item = focusedMatchItem();
    if (ev.key === 'ArrowDown') { ev.preventDefault(); moveMatchFocus(1); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); moveMatchFocus(-1); }
    else if (ev.key === 'Escape') { var drw = $('#mDrawer'); if (drw) { drw.hidden = true; drw.innerHTML = ''; } }
    else if (item && (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft')) {
      ev.preventDefault();
      var pills = $$('.cand', item);
      if (!pills.length) return;
      var cur = Number(item.getAttribute('data-sel') || 0);
      var dirStep = (ev.key === 'ArrowRight' ? 1 : -1) * (store.lang === 'ar' ? -1 : 1);
      var nxt = Math.max(0, Math.min(pills.length - 1, cur + dirStep));
      item.setAttribute('data-sel', String(nxt));
      pills.forEach(function (p, i) { p.classList.toggle('sel', i === nxt); });
    }
    else if (item && (ev.key === 'a' || ev.key === 'A' || ev.key === 'ش')) { ev.preventDefault(); matchAccept(item); }
    else if (item && (ev.key === 'r' || ev.key === 'R' || ev.key === 'ق')) { ev.preventDefault(); matchReject(item); }
    else if (item && (ev.key === 's' || ev.key === 'S' || ev.key === 'س')) { ev.preventDefault(); var md = matchItemData(item); if (md) openMatchDrawer(item, md); }
    else if (item && (ev.key === 'n' || ev.key === 'N' || ev.key === 'ى')) { ev.preventDefault(); matchPromote(item); }
  });
  document.addEventListener('keydown', function (ev) {
    if (store.view !== 'bank') return;
    var tag = (ev.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      if (ev.key === 'Escape') { closeCls(); }
      return;
    }
    var row = focusedBankRow();
    if (ev.key === 'ArrowDown') { ev.preventDefault(); moveFocus(1); }
    else if (ev.key === 'ArrowUp') { ev.preventDefault(); moveFocus(-1); }
    else if (ev.key === 'Enter' && row) { ev.preventDefault(); openCls([row.getAttribute('data-id')], row); }
    else if (ev.key === 'Escape') { closeCls(); }
    else if ((ev.key === 's' || ev.key === 'S' || ev.key === 'س') && row) { ev.preventDefault(); moveFocus(1); }
    else if ((ev.key === 'x' || ev.key === 'X' || ev.key === '؛') && row) {
      ev.preventDefault();
      var id = row.getAttribute('data-id');
      store.sel[id] = !store.sel[id];
      var cb = row.querySelector('input[type=checkbox]');
      if (cb) cb.checked = !!store.sel[id];
      updateBulkBar();
    }
    else if (['1', '2', '3'].indexOf(ev.key) >= 0 && row) {
      var idx = Number(ev.key) - 1;
      var sugg = $$('.sugg', row)[idx];
      if (sugg) { ev.preventDefault(); postClassify([row.getAttribute('data-id')], { account_id: sugg.getAttribute('data-acc') }); }
    }
  });

  /* ---------------- event delegation ---------------- */
  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act');
    var id = el.getAttribute('data-id');
    var row = el.closest('.wq-row');

    /* --- today --- */
    if (act === 'retry_today') loadToday();
    else if (act === 'approve') decide(id, 'approve');
    else if (act === 'reject') openReason(row, id, 'reject');
    else if (act === 'clarify') openReason(row, id, 'clarify');
    else if (act === 'cancel-reason') { var bx = row.querySelector('.wq-reason'); bx.hidden = true; bx.innerHTML = ''; }
    else if (act === 'confirm-reject' || act === 'confirm-clarify') {
      var ta = row.querySelector('.reason-in');
      var reason = ta ? ta.value.trim() : '';
      if (act === 'confirm-reject' && !reason) { ta.classList.add('need'); ta.focus(); return; }
      decide(id, act === 'confirm-reject' ? 'reject' : 'clarify', reason);
    }

    /* --- bank --- */
    else if (act === 'retry_bank') loadBankData();
    else if (act === 'bk-filter') { bankP.f = el.getAttribute('data-f'); bankP.p = 1; pushBankHash(); }
    else if (act === 'bk-page') { var p = Number(el.getAttribute('data-p')); if (p >= 1) { bankP.p = p; pushBankHash(); } }
    else if (act === 'bk-upload-btn') { var fi = $('#bkFile'); if (fi) fi.click(); }
    else if (act === 'bk-confirm-import') {
      if (!store.pendingFile) return;
      el.disabled = true;
      uploadBank(store.pendingFile, true).then(function (r) {
        var s = r.saved || {};
        $('#bkPreview').innerHTML = '';
        store.pendingFile = null;
        toast(t('import_ok').replace('{n}', s.saved).replace('{d}', s.duplicates));
        if (r.rules_applied) toast(t('rules_applied_toast').replace('{n}', r.rules_applied));
        loadBankData();
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'bk-cancel-import') { $('#bkPreview').innerHTML = ''; store.pendingFile = null; }
    else if (act === 'bk-open-cls') {
      var tr = el.closest('.brow');
      openCls([id], tr);
    }
    else if (act === 'bk-pick-acc') {
      var accId = el.getAttribute('data-acc');
      $('#clsAccId').value = accId;
      var a = store.chart.byId[accId];
      $('#clsAccIn').value = (a ? (a.code ? a.code + ' — ' : '') + a.name : accId);
      $('#clsAccList').innerHTML = '';
      var cc = $('#clsCc'); if (cc) cc.focus();
    }
    else if (act === 'bk-save-cls') {
      var panel = el.closest('.cls-panel');
      var ids = panel.getAttribute('data-ids').split(',').filter(Boolean);
      var accSel = $('#clsAccId').value;
      if (!accSel) { $('#clsAccIn').classList.add('need'); $('#clsAccIn').focus(); return; }
      var mkRule = $('#clsMkRule') && $('#clsMkRule').checked;
      el.disabled = true;
      if (mkRule) {
        var contains = ($('#clsRuleContains').value || '').trim();
        if (contains.length < 2) { $('#clsRuleContains').classList.add('need'); $('#clsRuleContains').focus(); el.disabled = false; return; }
        api('/erp/api/rules', { method: 'POST', body: {
          account_id: accSel, cost_center_id: $('#clsCc').value,
          counterparty: $('#clsCp').value.trim(), unit: $('#clsUnit').value.trim(),
          contains: contains, direction: $('#clsRuleDir').value, apply_now: 1
        } }).then(function (r) {
          (r.rows || []).forEach(patchBankRow);
          adjustBankCounts(r.rows ? r.rows.length : 0, false);
          patchCounters(r.counters);
          toast(r.applied ? t('rule_created').replace('{n}', r.applied) : t('rule_created_0'));
          closeCls();
        }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
        return;
      }
      postClassify(ids, {
        account_id: accSel,
        cost_center_id: $('#clsCc').value,
        counterparty: $('#clsCp').value.trim(),
        unit: $('#clsUnit').value.trim()
      }).then(closeCls).catch(function () { el.disabled = false; });
    }
    else if (act === 'bk-undo-rule') {
      el.disabled = true;
      api('/erp/api/rules/undo', { method: 'POST', body: { txn_id: id } }).then(function (r) {
        patchBankRow(r.row);
        adjustBankCounts(1, true);
        patchCounters(r.counters);
        toast(t('undo_ok'), 'warn');
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'bk-cancel-cls') closeCls();
    else if (act === 'bk-clear-cls') {
      el.disabled = true;
      postClassify([id], { clear: 1 }).then(closeCls).catch(function () { el.disabled = false; });
    }
    else if (act === 'bk-sugg') {
      postClassify([id], { account_id: el.getAttribute('data-acc') });
    }
    else if (act === 'bk-bulk-cls') openCls(selectedIds(), null);
    else if (act === 'bk-bulk-clear') { store.sel = {}; $$('.brow input[type=checkbox]').forEach(function (c) { c.checked = false; }); updateBulkBar(); }
    else if (act === 'bk-refresh-chart') {
      el.disabled = true;
      var old = el.textContent;
      el.textContent = t('refreshing');
      api('/erp/api/accounts/refresh', { method: 'POST', body: {} }).then(function (r) {
        store.chart = null;
        toast(t('chart_done') + ' (' + (r.chart && r.chart.accounts) + ')');
      }).catch(function (e) { toast(srvMsg(e) || t('act_failed'), 'err'); })
        .then(function () { el.disabled = false; el.textContent = old; });
    }

    /* --- matching --- */
    else if (act === 'retry_match') loadMatch();
    else if (act === 'm-filter') { matchP.engine = el.getAttribute('data-e'); matchP.p = 1; pushMatchHash(); }
    else if (act === 'm-page') { var mp = Number(el.getAttribute('data-p')); if (mp >= 1) { matchP.p = mp; pushMatchHash(); } }
    else if (act === 'm-pick') {
      var item = el.closest('.mitem');
      item.setAttribute('data-sel', String(el.getAttribute('data-idx')));
      $$('.cand', item).forEach(function (c) { c.classList.remove('sel'); });
      el.classList.add('sel');
    }
    else if (act === 'm-accept') matchAccept(el.closest('.mitem'));
    else if (act === 'm-reject') matchReject(el.closest('.mitem'));
    else if (act === 'm-promote') matchPromote(el.closest('.mitem'));
    else if (act === 'm-drawer') { var mi = el.closest('.mitem'); var md = matchItemData(mi); if (md) openMatchDrawer(mi, md); }
    else if (act === 'm-drawer-close') { var drw = $('#mDrawer'); drw.hidden = true; drw.innerHTML = ''; }
    else if (act === 'm-link-sel') {
      var sugg = el.closest('.dsugg');
      var lids = $$('input[type=checkbox]:checked', sugg).map(function (c) { return c.getAttribute('data-lid'); });
      if (!lids.length) { toast(t('m_sum_mismatch'), 'err'); return; }
      el.disabled = true;
      api('/erp/api/match/daftra', { method: 'POST', body: {
        action: 'link_distributed', id: id,
        daftra: { journal_id: sugg.getAttribute('data-eid'), line_ids: lids,
                  journal_number: sugg.getAttribute('data-num'),
                  confidence: Number(sugg.getAttribute('data-conf')) || 90 }
      } }).then(function () {
        var drw = $('#mDrawer'); drw.hidden = true; drw.innerHTML = '';
        var item = document.querySelector('.mitem[data-id="' + id + '"]');
        if (item) removeMatchItem(item, t('m_accepted'));
      }).catch(function (e) {
        el.disabled = false;
        var b = e && e.body;
        toast((b && (b.error_ar || b.error)) || srvMsg(e) || t('act_failed'), 'err');
      });
    }
    else if (act === 'm-notdup' || act === 'm-ignore') {
      el.disabled = true;
      api('/erp/api/match/daftra', { method: 'POST', body: {
        action: act === 'm-notdup' ? 'not_duplicate' : 'ignore', id: id, reason: ''
      } }).then(function () {
        var drw = $('#mDrawer'); drw.hidden = true; drw.innerHTML = '';
        var item = document.querySelector('.mitem[data-id="' + id + '"]');
        if (item) {
          if (act === 'm-ignore') removeMatchItem(item, t('m_rejected'));
          else { item.classList.remove('busy'); loadMatch(); }
        }
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }

    /* --- expenses --- */
    else if (act === 'retry_exp') loadExp();
    else if (act === 'x-tab') { expP.tab = el.getAttribute('data-tab'); expP.o = 0; pushExpHash(); }
    else if (act === 'x-more') { expP.o += EXP_LIMIT; loadExp(true); }
    else if (act === 'x-modal-close') { var xm = $('#xModal'); if (xm) { xm.hidden = true; xm.innerHTML = ''; } }
    else if (act === 'x-receipt') { ev.stopPropagation(); expReceiptLightbox(el.getAttribute('data-url')); }
    else if (act === 'x-detail') expDetail(el.getAttribute('data-id'));
    else if (act === 'x-edit') expEditDrawer(id);
    else if (act === 'x-edit-save') {
      el.disabled = true;
      var fields = { amount: $('#xe_amount').value, expense_date: $('#xe_expense_date').value,
                     apartment: $('#xe_apartment').value, category: $('#xe_category').value,
                     vendor: $('#xe_vendor').value, note: $('#xe_note').value };
      api('/erp/api/exp/edit', { method: 'POST', body: { id: id, fields: fields } }).then(function () {
        var xm = $('#xModal'); xm.hidden = true; xm.innerHTML = '';
        toast(t('x_saved'));
        loadExp();
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'x-approve') {
      el.disabled = true;
      api('/erp/api/exp/approve', { method: 'POST', body: { id: id } }).then(function (r) {
        if ((r.approved || []).length) { expRemoveRow(id, t('x_approved_ok')); }
        else {
          el.disabled = false;
          var why = ((r.blocked || [])[0] || {}).reason || t('act_failed');
          toast(why, 'err');
        }
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'x-reject') {
      var xrow = el.closest('.xrow');
      openReason(xrow, id, 'reject');
      var cbtn = xrow.querySelector('[data-act="confirm-reject"]');
      if (cbtn) cbtn.setAttribute('data-act', 'x-confirm-reject');
    }
    else if (act === 'x-confirm-reject') {
      var xr = el.closest('.xrow');
      var ta2 = xr.querySelector('.reason-in');
      var rsn = ta2 ? ta2.value.trim() : '';
      if (!rsn) { ta2.classList.add('need'); ta2.focus(); return; }
      el.disabled = true;
      api('/erp/api/exp/reject', { method: 'POST', body: { id: id, reason: rsn } }).then(function () {
        expRemoveRow(id, t('x_rejected_ok'));
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'x-export') {
      el.disabled = true;
      api('/erp/api/exp/export', { method: 'POST', body: { id: id } }).then(function (r) {
        if ((r.queued || []).length) expRemoveRow(id, t('x_exported_ok'));
        else { el.disabled = false; toast(((r.skipped || [])[0] || {}).reason || t('act_failed'), 'err'); }
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'x-recheck') {
      el.disabled = true;
      api('/erp/api/exp/recheck', { method: 'POST', body: { id: id } }).then(function (r) {
        if ((r.verified || []).length) expRemoveRow(id, t('x_verified_ok'));
        else { el.disabled = false; toast(t('x_not_found'), 'warn'); }
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'x-bulk-approve' || act === 'x-bulk-export') {
      var xids = expSelectedIds();
      if (!xids.length) return;
      el.disabled = true;
      var ep = act === 'x-bulk-approve' ? '/erp/api/exp/approve' : '/erp/api/exp/export';
      api(ep, { method: 'POST', body: { ids: xids } }).then(function (r) {
        var okIds = (r.approved || r.queued || []).map(function (o) { return o.id; });
        okIds.forEach(function (i) { expRemoveRow(i); });
        var blocked = (r.blocked || r.skipped || []).length;
        toast((act === 'x-bulk-approve' ? t('x_approved_n') : t('x_exported_ok')).replace('{n}', okIds.length) +
              (blocked ? ' · ' + t('x_blocked_n').replace('{n}', blocked) : ''),
              blocked ? 'warn' : 'ok');
        var xb = $('#xBulk'); if (xb) { xb.hidden = true; xb.innerHTML = ''; }
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'x-bulk-clear') {
      $$('.xrow input[type=checkbox]').forEach(function (c) { c.checked = false; });
      updateExpBulk();
    }

    /* --- custody --- */
    else if (act === 'retry_custody') loadCustody();

    /* --- statements --- */
    else if (act === 'retry_stmts') loadStmts();
    else if (act === 'st-drill') {
      var did = el.getAttribute('data-id');
      var dr2 = $('#stDrill');
      if (!dr2) return;
      dr2.hidden = false;
      dr2.innerHTML = '<div class="drawer-card card"><div class="grp-h"><h2><code>' + esc(did) + '</code></h2>' +
        '<button class="btn ghost xs" data-act="st-drill-close">✕</button></div><div class="drawer-body">' + skeleton(3) + '</div></div>';
      api('/erp/api/stmts/account?id=' + encodeURIComponent(did) + '&m=' + encodeURIComponent(stP.m || nowMonth()))
        .then(function (r) {
          var lines = (r.rows || []).map(function (l) {
            return '<div class="st-row"><span class="st-name"><code>' + esc(l.date) + '</code> ' + esc(l.description) +
              (l.cost_center ? ' <span class="tag">' + esc(l.cost_center) + '</span>' : '') +
              ' <code>#' + esc(l.number || l.entry_id) + '</code></span>' +
              '<code class="st-prior">' + (l.credit ? fmtAmt(l.credit) + '−' : '') + '</code>' +
              '<code class="st-amt">' + (l.debit ? fmtAmt(l.debit) : '') + '</code></div>';
          }).join('');
          dr2.querySelector('.drawer-body').innerHTML = lines ||
            '<div class="state-sub">' + esc(t('st_drill_empty')) + '</div>';
        })
        .catch(function (e) { dr2.querySelector('.drawer-body').innerHTML = errorCard('st-drill-close', srvMsg(e)); });
    }
    else if (act === 'st-drill-close') { var sd = $('#stDrill'); if (sd) { sd.hidden = true; sd.innerHTML = ''; } }

    /* --- close + migrate --- */
    else if (act === 'retry_close') loadClose();
    else if (act === 'cl-close') {
      if (!window.confirm(t('cl_confirm'))) return;
      el.disabled = true;
      api('/erp/api/close', { method: 'POST', body: { month: clP.m || nowMonth() } })
        .then(function () { toast(t('cl_closed')); loadClose(); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'mg-preview') {
      el.disabled = true;
      api('/erp/api/migrate', { method: 'POST', body: { month: clP.m || nowMonth() } })
        .then(function (r) { el.disabled = false; renderMgDraft(r); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'mg-run') {
      var dcl = store.D.close || {};
      if (!window.confirm(t('mg_confirm_q').replace('{n}', dcl.migratable_entries || 0))) return;
      el.disabled = true;
      api('/erp/api/migrate', { method: 'POST', body: { month: clP.m || nowMonth(), confirm: 1 } })
        .then(function (r) {
          toast(r.disabled ? t('mg_disabled') : t('mg_done'), r.disabled ? 'warn' : 'ok');
          loadClose();
        })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }

    /* --- budget --- */
    else if (act === 'retry_budget') loadBudget();
    else if (act === 'bg-pick-acc') {
      var ba = el.getAttribute('data-acc');
      $('#bgAccId').value = ba;
      var ac = store.chart.byId[ba];
      $('#bgAccIn').value = ac ? ((ac.code ? ac.code + ' — ' : '') + ac.name) : ba;
      $('#bgAccList').innerHTML = '';
      var d3 = (store.D.budget || {}).avg3_actuals || {};
      if (d3[ba] && !$('#bgAmtIn').value) $('#bgAmtIn').value = d3[ba];
      $('#bgAmtIn').focus();
    }
    else if (act === 'bg-add') {
      var aid2 = $('#bgAccId').value;
      var amt2 = Number($('#bgAmtIn').value);
      if (!aid2) { $('#bgAccIn').classList.add('need'); $('#bgAccIn').focus(); return; }
      if (!(amt2 > 0)) { $('#bgAmtIn').classList.add('need'); $('#bgAmtIn').focus(); return; }
      el.disabled = true;
      api('/erp/api/budget', { method: 'POST', body: { month: bgP.m || nowMonth(), account_id: aid2, amount: amt2 } })
        .then(function (r) { toast(t('bg_saved')); renderBudget(r); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'bg-save') {
      var rowB = el.closest('.wq-row');
      var amtIn = rowB.querySelector('.bg-amt');
      el.disabled = true;
      api('/erp/api/budget', { method: 'POST', body: { month: bgP.m || nowMonth(), account_id: el.getAttribute('data-aid'), amount: Number(amtIn.value) } })
        .then(function (r) { toast(t('bg_saved')); renderBudget(r); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'bg-del') {
      if (!window.confirm(t('bg_del_confirm'))) return;
      el.disabled = true;
      api('/erp/api/budget', { method: 'POST', body: { month: bgP.m || nowMonth(), action: 'delete', account_id: el.getAttribute('data-aid') } })
        .then(function (r) { toast(t('bg_deleted'), 'warn'); renderBudget(r); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'bg-copy-last') {
      el.disabled = true;
      api('/erp/api/budget', { method: 'POST', body: { month: bgP.m || nowMonth(), action: 'copy_last' } })
        .then(function (r) { toast(t('bg_saved')); renderBudget(r); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }

    /* --- owners --- */
    else if (act === 'retry_owners') loadOwners();
    else if (act === 'o-copy') {
      var absUrl = location.origin + el.getAttribute('data-url');
      (navigator.clipboard && navigator.clipboard.writeText
        ? navigator.clipboard.writeText(absUrl)
        : Promise.reject()
      ).then(function () { toast(t('o_copied')); })
       .catch(function () { window.prompt('URL', absUrl); });
    }
    else if (act === 'o-create') {
      el.disabled = true;
      ownerLinkAct(el.getAttribute('data-owner'), 'create')
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'o-regen') {
      if (!window.confirm(t('o_regen_confirm'))) return;
      el.disabled = true;
      ownerLinkAct(el.getAttribute('data-owner'), 'regenerate')
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'o-revoke') {
      if (!window.confirm(t('o_revoke_confirm'))) return;
      el.disabled = true;
      ownerLinkAct(el.getAttribute('data-owner'), 'revoke')
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }

    /* --- monthly cycle board (slice 3) --- */
    else if (act === 'cy-filter') { cyUI.filter = el.getAttribute('data-f'); renderOwners(null); }
    else if (act === 'cy-sel') { cyUI.sel[el.getAttribute('data-owner')] = el.checked; renderOwners(null); }
    else if (act === 'cy-tpl') { cyUI.tplOpen = !cyUI.tplOpen; renderOwners(null); }
    else if (act === 'cy-tpl-save') {
      el.disabled = true;
      api('/erp/api/owners/cycle/template', { method: 'POST', body: { text: $('#cyTpl').value } })
        .then(function (r) {
          if (store.D.cycle) store.D.cycle.wa_template = r.wa_template;
          cyUI.tplOpen = false;
          toast(t('cy_template_saved'));
          renderOwners(null);
        }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'cy-status') {
      el.disabled = true;
      api('/erp/api/owners/cycle/status', { method: 'POST', body: {
        owner: el.getAttribute('data-owner'), m: cyUI.m, to: el.getAttribute('data-to') } })
        .then(function () { return loadCycle(); })
        .then(function () { toast(t('o_done')); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'cy-bulk') {
      var ownersSel = Object.keys(cyUI.sel).filter(function (k) { return cyUI.sel[k]; });
      if (!ownersSel.length) return;
      el.disabled = true;
      api('/erp/api/owners/cycle/status', { method: 'POST', body: {
        owners: ownersSel, m: cyUI.m, to: el.getAttribute('data-to') } })
        .then(function () { cyUI.sel = {}; return loadCycle(); })
        .then(function () { toast(t('o_done')); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'cy-wa') {
      var cyd = store.D.cycle || {};
      var rw = (cyd.rows || []).filter(function (x) { return x.owner === el.getAttribute('data-owner'); })[0];
      if (!rw) return;
      window.open(cyWaLink(rw, cyd), '_blank', 'noopener');
      api('/erp/api/owners/cycle/status', { method: 'POST', body: { owner: rw.owner, m: cyUI.m, to: 'sent' } })
        .then(function () { return loadCycle(); })
        .then(function () { toast(t('cy_wa_sent')); })
        .catch(function (e) { toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'cy-copy-all') {
      el.disabled = true;
      api('/erp/api/owners/cycle/links', { method: 'POST', body: { action: 'copy_all' } })
        .then(function (r) {
          el.disabled = false;
          var txt = (r.links || []).map(function (l) { return l.owner + ': ' + location.origin + l.url; }).join(String.fromCharCode(10));
          return (navigator.clipboard && navigator.clipboard.writeText
            ? navigator.clipboard.writeText(txt) : Promise.reject(txt))
            .then(function () { toast(t('cy_copied_n').replace('{n}', (r.links || []).length)); })
            .catch(function () { window.prompt('Links', txt); });
        })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'cy-regen-all') {
      if (!window.confirm(t('cy_regen_confirm'))) return;
      el.disabled = true;
      api('/erp/api/owners/cycle/links', { method: 'POST', body: { action: 'regen_all' } })
        .then(function (r) {
          toast(t('cy_regen_done').replace('{n}', r.regenerated || 0), 'warn');
          return loadCycle();
        })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }

    /* --- statement editor (slice 2) --- */
    else if (act === 'se-tab') { seUI.tab = el.getAttribute('data-tab'); seRerender(store.D.stmtEd); }
    else if (act === 'se-why') {
      var wk = el.getAttribute('data-key');
      seUI.explain = (seUI.explain === wk ? '' : wk);
      seRerender(store.D.stmtEd);
    }
    else if (act === 'se-x-open' || act === 'se-i-open' || act === 'se-xe-open' || act === 'se-xd-open') {
      var rowS = el.closest('.wq-row');
      var formKey = { 'se-x-open': 'se-x', 'se-i-open': 'se-i', 'se-xe-open': 'se-xe', 'se-xd-open': 'se-xd' }[act];
      rowS.querySelectorAll('.se-inline').forEach(function (f) { f.hidden = f.getAttribute('data-need') !== formKey || !f.hidden; });
      if (act === 'se-i-open') {
        var amtF = rowS.querySelector('.se-amt');
        if (amtF) amtF.hidden = el.getAttribute('data-needamt') !== '1';
      }
      var vis = rowS.querySelector('.se-inline:not([hidden]) .se-reason');
      if (vis) vis.focus();
    }
    else if (act === 'se-x-go') {
      var rowX = el.closest('.wq-row');
      var rX = rowX.querySelector('.se-inline[data-need="se-x"] .se-reason').value.trim();
      if (!rX) { rowX.querySelector('.se-inline[data-need="se-x"] .se-reason').classList.add('need'); return; }
      seEdit({ op: 'resv_exclude', id: rowX.getAttribute('data-rid'), reason: rX }, el);
    }
    else if (act === 'se-i-go') {
      var rowI = el.closest('.wq-row');
      var box = rowI.querySelector('.se-inline[data-need="se-i"]');
      var rI = box.querySelector('.se-reason').value.trim();
      var aF = box.querySelector('.se-amt');
      if (!rI) { box.querySelector('.se-reason').classList.add('need'); return; }
      var bodyI = { op: 'resv_include', id: rowI.getAttribute('data-rid'), reason: rI };
      if (aF && !aF.hidden) {
        if (!(Number(aF.value) > 0)) { aF.classList.add('need'); aF.focus(); return; }
        bodyI.amount = Number(aF.value);
      }
      seEdit(bodyI, el);
    }
    else if (act === 'se-xe-go') {
      var rowE = el.closest('.wq-row');
      var boxE = rowE.querySelector('.se-inline[data-need="se-xe"]');
      var rE = boxE.querySelector('.se-reason').value.trim();
      if (!rE) { boxE.querySelector('.se-reason').classList.add('need'); return; }
      seEdit({ op: 'exp_override', id: rowE.getAttribute('data-xid'), reason: rE,
               amount: boxE.querySelector('.se-e-amt').value,
               date: boxE.querySelector('.se-e-date').value,
               description: boxE.querySelector('.se-e-desc').value }, el);
    }
    else if (act === 'se-xd-go') {
      var rowD = el.closest('.wq-row');
      var rD = rowD.querySelector('.se-inline[data-need="se-xd"] .se-reason').value.trim();
      if (!rD) { rowD.querySelector('.se-inline[data-need="se-xd"] .se-reason').classList.add('need'); return; }
      seEdit({ op: 'exp_delete', id: rowD.getAttribute('data-xid'), reason: rD }, el);
    }
    else if (act === 'se-man-del') {
      seEdit({ op: 'exp_manual_del', id: el.closest('.wq-row').getAttribute('data-xid'), reason: '-' }, el);
    }
    else if (act === 'se-man-add') {
      var mr = $('#seManReason').value.trim();
      if (!(Number($('#seManAmt').value) > 0)) { $('#seManAmt').classList.add('need'); return; }
      if (!mr) { $('#seManReason').classList.add('need'); return; }
      seEdit({ op: 'exp_manual_add', amount: Number($('#seManAmt').value),
               date: $('#seManDate').value, description: $('#seManDesc').value, reason: mr }, el);
    }
    else if (act === 'se-adj-add') {
      var ar2 = $('#seAdjReason').value.trim();
      var av = Number($('#seAdjAmt').value);
      if (!av) { $('#seAdjAmt').classList.add('need'); return; }
      if (!ar2) { $('#seAdjReason').classList.add('need'); return; }
      seEdit({ op: 'adj_add', amount: av, label: $('#seAdjLabel').value, reason: ar2 }, el);
    }
    else if (act === 'se-adj-del') {
      seEdit({ op: 'adj_del', id: el.closest('.wq-row').getAttribute('data-aid'), reason: '-' }, el);
    }
    else if (act === 'se-publish') {
      if (!window.confirm(t('se_pub_confirm'))) return;
      var dP = store.D.stmtEd || {};
      el.disabled = true;
      api('/erp/api/owners/statement/publish', { method: 'POST', body: { owner: dP.owner, m: dP.month } })
        .then(function (r) {
          toast(t('se_pubd').replace('{v}', r.version));
          loadStmtEd(dP.owner, dP.month);
        })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'se-diff') {
      var dD = store.D.stmtEd || {};
      el.disabled = true;
      api('/erp/api/owners/statement/diff?owner=' + encodeURIComponent(dD.owner) + '&m=' + encodeURIComponent(dD.month))
        .then(function (r) {
          el.disabled = false;
          var box2 = $('#seDiffBox');
          if (!box2) return;
          if (!r.changed) {
            box2.innerHTML = '<div class="wq-row info" style="margin:8px 16px"><div class="wq-main"><div class="wq-top">' + esc(t('se_diff_none')) + '</div></div></div>';
            return;
          }
          var ks = ['total_income', 'ouja_fee', 'expenses', 'cleaning', 'adjustments', 'owner_net'];
          var lbl = { total_income: t('se_income'), ouja_fee: t('se_fees'), expenses: t('se_expenses'),
                      cleaning: t('se_cleaning'), adjustments: t('se_adjust'), owner_net: t('se_net') };
          box2.innerHTML = '<div class="om-form" style="margin:8px 16px"><b>' + esc(t('se_diff_title')) + '</b>' +
            ks.map(function (kk) {
              var dl = (r.delta || {})[kk];
              return '<div class="foot-line"><span>' + esc(lbl[kk]) + '</span><span><code>' +
                fmtAmt((r.published || {})[kk]) + '</code> ← <code>' + fmtAmt((r.fresh || {})[kk]) + '</code>' +
                (dl ? (' <b style="color:' + (dl > 0 ? 'var(--green)' : 'var(--red)') + '">' + (dl > 0 ? '+' : '') + fmtAmt(dl) + '</b>') : '') +
                '</span></div>';
            }).join('') +
            '<button class="btn primary sm" data-act="se-publish">' + esc(t('se_diff_apply')) + '</button></div>';
        })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }

    /* --- owner manager (slice 1) --- */
    else if (act === 'om-save') {
      el.disabled = true;
      api('/erp/api/owners/save', { method: 'POST', body: {
        owner: el.getAttribute('data-owner'),
        phone: $('#omPhone').value, notes: $('#omNotes').value,
        active: $('#omActive').value === '1'
      } }).then(function () { el.disabled = false; toast(t('om_saved')); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'om-toggle-form') {
      var rowM = el.closest('.wq-row');
      var f = rowM && rowM.querySelector('.om-form[data-form="' + el.getAttribute('data-form') + '"]');
      if (f) {
        var show = f.hidden;
        rowM.querySelectorAll('.om-form').forEach(function (x) { x.hidden = true; });
        f.hidden = !show;
      }
    }
    else if (act === 'om-terms-save') {
      var rowT = el.closest('.wq-row');
      var frm = rowT.querySelector('.om-t-from').value;
      var reasonT = rowT.querySelector('.om-t-reason').value.trim();
      if (!frm) { rowT.querySelector('.om-t-from').classList.add('need'); return; }
      el.disabled = true;
      api('/erp/api/owners/unit-terms', { method: 'POST', body: {
        apartment: el.getAttribute('data-apt'), from: frm,
        mgmt_pct: rowT.querySelector('.om-t-mgmt').value,
        cleaning: { type: rowT.querySelector('.om-t-cltype').value,
                    amount: Number(rowT.querySelector('.om-t-clamt').value || 0) },
        reason: reasonT
      } }).then(function () {
        toast(t('om_terms_saved').replace('{d}', frm));
        loadManage(((store.D.manage || {}).owner) || '');
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'om-remove-do') {
      var rowR = el.closest('.wq-row');
      var toD = rowR.querySelector('.om-r-to').value;
      var reasonR = rowR.querySelector('.om-r-reason').value.trim();
      if (!toD) { rowR.querySelector('.om-r-to').classList.add('need'); return; }
      if (!reasonR) { rowR.querySelector('.om-r-reason').classList.add('need'); rowR.querySelector('.om-r-reason').focus(); return; }
      el.disabled = true;
      api('/erp/api/owners/unit-remove', { method: 'POST', body: {
        apartment: el.getAttribute('data-apt'), to: toD, reason: reasonR
      } }).then(function () {
        toast(t('om_removed'), 'warn');
        loadManage(((store.D.manage || {}).owner) || '');
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'om-pick-listing') {
      $('#omAddForm').hidden = false;
      $('#omAddLid').value = el.getAttribute('data-lid');
      var nm = el.getAttribute('data-name') || '';
      var code = nm.split('|').pop().trim();
      if (!$('#omAddApt').value) $('#omAddApt').value = code;
      $('#omLResults').innerHTML = '<div class="wq-sub">✓ ' + esc(nm) + ' <code>#' + esc(el.getAttribute('data-lid')) + '</code></div>';
      $('#omAddApt').focus();
    }
    else if (act === 'om-unit-add') {
      var aptA = $('#omAddApt').value.trim();
      if (!aptA) { $('#omAddApt').classList.add('need'); $('#omAddApt').focus(); return; }
      el.disabled = true;
      api('/erp/api/owners/unit-add', { method: 'POST', body: {
        owner: el.getAttribute('data-owner'), apartment: aptA,
        lid: $('#omAddLid').value || null,
        from: $('#omAddFrom').value || '',
        mgmt_pct: $('#omAddMgmt').value,
        cleaning: { type: $('#omAddClType').value, amount: Number($('#omAddClAmt').value || 0) }
      } }).then(function () {
        toast(t('om_added'));
        loadManage(((store.D.manage || {}).owner) || '');
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }

    /* --- setup --- */
    else if (act === 'retry_setup') loadSetup();
    else if (act === 'st-rule-toggle') {
      el.disabled = true;
      api('/erp/api/rules/toggle', { method: 'POST', body: { id: id, enabled: el.getAttribute('data-en') === '1' } })
        .then(function () { loadSetup(); })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'st-rule-del') {
      el.disabled = true;
      api('/erp/api/rules/delete', { method: 'POST', body: { id: id } })
        .then(function () {
          var tr = el.closest('tr');
          if (tr) tr.remove();
          toast(t('rl_delete') + ' ✓', 'warn');
        })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'st-precision') {
      el.disabled = true;
      api('/erp/api/rules/precision').then(function (r) {
        el.disabled = false;
        var box = $('#precisionOut');
        if (!box) return;
        var rows = (r.rules || []).map(function (x) {
          return '<tr><td>«' + esc(x.contains || '') + '»</td><td>' + esc(x.account || '') + '</td>' +
            '<td class="c-amt"><code>' + x.matched_human + '</code></td>' +
            '<td class="c-amt"><code>' + x.agree + '</code></td>' +
            '<td class="c-amt"><code>' + (x.precision === null ? '—' : x.precision + '%') + '</code></td>' +
            '<td class="c-amt"><code>' + x.would_apply_now + '</code></td></tr>';
        }).join('');
        box.innerHTML = '<div class="prev-stats" style="padding:0 20px">' +
          '<span class="pstat ok"><b>' + (r.overall_precision === null ? '—' : r.overall_precision + '%') + '</b>' + esc(t('pr_overall')) + '</span>' +
          '<span class="pstat"><b>' + r.ground_truth_rows + '</b>' + esc(t('pr_ground').replace('{n}', r.ground_truth_rows)) + '</span></div>' +
          (rows ? '<div class="table-card" style="border:none;box-shadow:none"><table class="btable mini"><thead><tr>' +
            '<th>' + esc(t('rl_matcher')) + '</th><th>' + esc(t('rl_target')) + '</th><th>' + esc(t('pr_matched')) + '</th>' +
            '<th>' + esc(t('pr_agree')) + '</th><th>' + esc(t('pr_precision')) + '</th><th>' + esc(t('pr_pending')) + '</th>' +
            '</tr></thead><tbody>' + rows + '</tbody></table></div>' : '');
      }).catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (act === 'st-link-cc') {
      var rowEl = el.closest('.wq-row');
      var sel = rowEl.querySelector('.ct-cc');
      var ccv = sel ? sel.value : '';
      if (!ccv) { if (sel) { sel.classList.add('need'); sel.focus(); } return; }
      el.disabled = true;
      api('/erp/api/contracts/link', { method: 'POST', body: { key: el.getAttribute('data-key'), cost_center_id: ccv } })
        .then(function (r) {
          patchCounters(r.counters);
          toast(t('linked_ok'));
          var c = r.row;
          rowEl.outerHTML = '<div class="wq-row info"><div class="wq-main"><div class="wq-top"><b>' + esc(c.name) + '</b>' +
            '<span class="tag soft">' + esc(c.cc_name || '') + '</span></div>' +
            (c.owner ? '<div class="wq-sub">' + esc(c.owner) + '</div>' : '') + '</div></div>';
          var cnt = $('#ctUnlinked');
          if (cnt && r.counters) cnt.textContent = r.counters.contracts ? t('unlinked_n').replace('{n}', r.counters.contracts) : '0';
        })
        .catch(function (e) { el.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
  });

  document.addEventListener('change', function (ev) {
    var el = ev.target;
    if (el.id === 'bkFile' && el.files && el.files[0]) {
      var f = el.files[0];
      el.value = '';
      uploadBank(f, false).then(function (r) { showPreview(r.preview, f); })
        .catch(function (e) { toast(srvMsg(e) || t('act_failed'), 'err'); });
    }
    else if (el.matches && el.matches('[data-act="bk-sel"]')) {
      store.sel[el.getAttribute('data-id')] = el.checked;
      updateBulkBar();
    }
    else if (el.id === 'bkFrom') { bankP.from = el.value; bankP.p = 1; pushBankHash(); }
    else if (el.id === 'bkTo') { bankP.to = el.value; bankP.p = 1; pushBankHash(); }
    else if (el.matches && el.matches('.dln input[type=checkbox]')) {
      var sg = el.closest('.dsugg');
      if (sg) updateDrawerSum(sg);
    }
    else if (el.matches && el.matches('[data-act="x-sel"]')) updateExpBulk();
    else if (el.id === 'stMonth') { stP.m = el.value; location.hash = '#stmts?m=' + el.value; }
    else if (el.id === 'clMonth') { clP.m = el.value; location.hash = '#close?m=' + el.value; }
    else if (el.id === 'bgMonth') { bgP.m = el.value; location.hash = '#budget?m=' + el.value; }
  });

  document.addEventListener('input', (function () {
    var tmr = null;
    return function (ev) {
      if (ev.target.id === 'bkSearch') {
        clearTimeout(tmr);
        var v = ev.target.value;
        tmr = setTimeout(function () { bankP.q = v.trim(); bankP.p = 1; pushBankHash(); }, 350);
      } else if (ev.target.id === 'xSearch') {
        clearTimeout(tmr);
        var v2 = ev.target.value;
        tmr = setTimeout(function () { expP.q = v2.trim(); expP.o = 0; pushExpHash(); }, 350);
      }
    };
  })());

  /* drag-drop upload */
  document.addEventListener('dragover', function (ev) {
    if (store.view !== 'bank') return;
    ev.preventDefault();
    var dz = $('#bkDrop'); if (dz) dz.hidden = false;
  });
  document.addEventListener('dragleave', function (ev) {
    if (ev.target.id === 'bkDrop') ev.target.hidden = true;
  });
  document.addEventListener('drop', function (ev) {
    if (store.view !== 'bank') return;
    ev.preventDefault();
    var dz = $('#bkDrop'); if (dz) dz.hidden = true;
    var f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
    if (f) uploadBank(f, false).then(function (r) { showPreview(r.preview, f); })
      .catch(function (e) { toast(srvMsg(e) || t('act_failed'), 'err'); });
  });

  document.addEventListener('click', function (ev) {
    var nb = ev.target.closest('.next-best');
    if (!nb) return;
    var target = document.getElementById(nb.getAttribute('data-target'));
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  // clicking the dark backdrop closes any drawer (the card itself stays interactive)
  document.addEventListener('click', function (ev) {
    if (ev.target.classList && ev.target.classList.contains('drawer')) {
      ev.target.hidden = true;
      ev.target.innerHTML = '';
    }
  });

  /* ================= المطابقة Matching ================= */
  var matchP = { engine: 'all', p: 1 };
  var ENGINE_ICONS = { daftra: '📒', exp: '🧾', founder: '👤', hostaway: '🌐' };

  function matchHash() {
    var ps = new URLSearchParams();
    if (matchP.engine !== 'all') ps.set('engine', matchP.engine);
    if (matchP.p > 1) ps.set('p', String(matchP.p));
    var qs = ps.toString();
    return '#match' + (qs ? '?' + qs : '');
  }
  function pushMatchHash() {
    var h = matchHash();
    if (location.hash !== h) location.hash = h;
    else loadMatch();
  }

  function candPill(c, idx, selected) {
    var lbl = (store.lang === 'ar' ? c.label : (c.label_en || c.label)) || '';
    var sub = (store.lang === 'ar' ? c.sub : (c.sub_en || c.sub)) || '';
    return '<button class="cand' + (selected ? ' sel' : '') + '" data-act="m-pick" data-idx="' + idx + '">' +
      '<span class="cand-eng">' + (ENGINE_ICONS[c.engine] || '') + '</span>' +
      '<span class="cand-main"><b>' + esc(lbl) + '</b>' +
      (sub ? '<i>' + esc(sub) + '</i>' : '') + '</span>' +
      '<span class="cand-meta">' +
        (c.amount ? '<code>' + fmtAmt(c.amount) + '</code>' : '') +
        (c.date ? '<code>' + esc(c.date) + '</code>' : '') +
        '<em class="cand-score">' + c.score + '%</em>' +
        (c.approx ? '<em class="tag warnt">' + esc(t('m_approx')) + '</em>' : '') +
      '</span></button>';
  }

  function matchItemHtml(it) {
    var amtCls = it.dir === 'in' ? 'in' : 'out';
    var cands = (it.cands || []).map(function (c, i) { return candPill(c, i, i === 0); }).join('');
    return '<div class="mitem card" tabindex="0" data-id="' + esc(it.id) + '" data-sel="0">' +
      '<div class="mi-head">' +
        '<span class="amt ' + amtCls + '">' + (it.dir === 'in' ? '+' : '−') + fmtAmt(it.amount) + ' <i>' + esc(t('sar')) + '</i></span>' +
        '<code>' + esc(it.date) + '</code>' +
        '<span class="tag">' + esc(it.category) + '</span>' +
        (it.card ? '<span class="tag">💳 ' + esc(it.card) + '</span>' : '') +
      '</div>' +
      '<div class="mi-desc">' + esc(it.desc) + '</div>' +
      (cands ? '<div class="mi-cands">' + cands + '</div>' : '') +
      '<div class="mi-actions">' +
        (it.cands && it.cands.length
          ? '<button class="btn primary sm" data-act="m-accept">' + esc(t('m_accept')) + ' <kbd>A</kbd></button>' +
            '<button class="btn ghost sm" data-act="m-reject">' + esc(t('m_reject')) + ' <kbd>R</kbd></button>'
          : '') +
        '<button class="btn ghost sm" data-act="m-drawer">' + esc(t('m_split')) + ' <kbd>S</kbd></button>' +
        '<button class="btn danger-ghost sm" data-act="m-promote">' + esc(t('m_nocp')) + ' <kbd>N</kbd></button>' +
      '</div>' +
      '<div class="mi-note" hidden></div>' +
    '</div>';
  }

  function renderMatch(d) {
    store.D.match = d;
    var chips =
      [['all', 'me_all', d.counts.all], ['daftra', 'me_daftra', d.counts.daftra],
       ['exp', 'me_exp', d.counts.exp], ['founder', 'me_founder', d.counts.founder],
       ['hostaway', 'me_hostaway', d.counts.hostaway], ['none', 'me_none', d.counts.none]]
      .map(function (c) {
        return '<button class="fchip' + (matchP.engine === c[0] ? ' on' : '') + '" data-act="m-filter" data-e="' + c[0] + '">' +
          esc(t(c[1])) + ' <b>' + c[2] + '</b></button>';
      }).join('');
    var pager = '';
    if (d.pages > 1) {
      pager = '<div class="pager">' +
        '<button class="btn ghost sm" data-act="m-page" data-p="' + (d.page - 1) + '"' + (d.page <= 1 ? ' disabled' : '') + '>‹</button>' +
        '<span class="pg-info">' + esc(t('page')) + ' <b>' + d.page + '</b> ' + esc(t('of')) + ' ' + d.pages + ' · ' + d.total + '</span>' +
        '<button class="btn ghost sm" data-act="m-page" data-p="' + (d.page + 1) + '"' + (d.page >= d.pages ? ' disabled' : '') + '>›</button></div>';
    }
    var body = d.items.length
      ? d.items.map(matchItemHtml).join('') + pager
      : '<div class="card state-card"><div class="state-ico ok">✓</div><div class="state-h">' + esc(t('m_empty')) + '</div></div>';
    $('#view').innerHTML =
      '<div class="card bank-bar"><div class="bb-chips" style="margin-top:0">' + chips + '</div>' +
      '<div class="kbd-hint">' + esc(t('m_kbd')) + '</div></div>' + body +
      '<div id="mDrawer" class="drawer" hidden></div>';
    restoreScroll('match');
  }

  function loadMatch() {
    $('#view').innerHTML = skeleton(6);
    var ps = new URLSearchParams();
    if (matchP.engine !== 'all') ps.set('engine', matchP.engine);
    ps.set('p', String(matchP.p));
    api('/erp/api/match?' + ps.toString()).then(renderMatch).catch(function (e) {
      $('#view').innerHTML = errorCard('retry_match', srvMsg(e));
    });
  }

  function matchItemData(el) {
    var id = el.getAttribute('data-id');
    var d = store.D.match;
    if (!d) return null;
    for (var i = 0; i < d.items.length; i++) if (d.items[i].id === id) return d.items[i];
    return null;
  }

  function removeMatchItem(el, okMsg) {
    var next = el.nextElementSibling;
    el.classList.add('leaving');
    setTimeout(function () {
      el.remove();
      if (next && next.classList && next.classList.contains('mitem')) next.focus();
    }, 200);
    if (okMsg) toast(okMsg);
  }

  function matchAccept(el) {
    var it = matchItemData(el);
    if (!it || !it.cands.length) return;
    var idx = Number(el.getAttribute('data-sel') || 0);
    var c = it.cands[Math.min(idx, it.cands.length - 1)];
    if (c.engine === 'daftra') { daftraQuickLink(el, it); return; }
    el.classList.add('busy');
    api('/erp/api/match/accept', { method: 'POST', body: {
      id: it.id, engine: c.engine, key: c.key, flow: c.flow || '', employee: c.employee || '',
      label: c.label || '', suggested: it.cands
    } }).then(function (r) {
      patchCounters(r.counters);
      removeMatchItem(el, t('m_accepted'));
    }).catch(function (e) { el.classList.remove('busy'); toast(srvMsg(e) || t('act_failed'), 'err'); });
  }

  function daftraQuickLink(el, it) {
    el.classList.add('busy');
    api('/erp/api/match/daftra?txn=' + encodeURIComponent(it.id)).then(function (d) {
      var s = (d.suggestions || [])[0];
      if (!s) { el.classList.remove('busy'); openMatchDrawer(el, it); return; }
      var body;
      if (s.match_type === 'distributed_subset_match' && (s.selected_line_ids || []).length) {
        body = { action: 'link_distributed', id: it.id,
                 daftra: { journal_id: s.entry_id, line_ids: s.selected_line_ids,
                           journal_number: s.number, confidence: s.confidence } };
      } else {
        body = { action: 'link', id: it.id,
                 daftra: { source_type: 'journal_entry', id: s.entry_id } };
      }
      return api('/erp/api/match/daftra', { method: 'POST', body: body }).then(function () {
        removeMatchItem(el, t('m_accepted'));
      });
    }).catch(function (e) {
      el.classList.remove('busy');
      var b = e && e.body;
      toast((b && (b.error_ar || b.error)) || srvMsg(e) || t('act_failed'), 'err');
    });
  }

  function matchReject(el) {
    var it = matchItemData(el);
    if (!it || !it.cands.length) return;
    var idx = Number(el.getAttribute('data-sel') || 0);
    var c = it.cands[Math.min(idx, it.cands.length - 1)];
    el.classList.add('busy');
    api('/erp/api/match/reject', { method: 'POST', body: { id: it.id, engine: c.engine, suggested: it.cands } })
      .then(function (r) {
        patchCounters(r.counters);
        var remaining = it.cands.filter(function (x) { return x.engine !== c.engine; });
        it.cands = remaining;
        if (matchP.engine !== 'all' || !remaining.length) removeMatchItem(el, t('m_rejected'));
        else {
          el.classList.remove('busy');
          el.setAttribute('data-sel', '0');
          var box = el.querySelector('.mi-cands');
          if (box) box.innerHTML = remaining.map(function (cc, i) { return candPill(cc, i, i === 0); }).join('');
          toast(t('m_rejected'), 'warn');
        }
      })
      .catch(function (e) { el.classList.remove('busy'); toast(srvMsg(e) || t('act_failed'), 'err'); });
  }

  function matchPromote(el) {
    var it = matchItemData(el);
    if (!it) return;
    if (!window.confirm(t('m_promote_confirm'))) return;
    el.classList.add('busy');
    api('/erp/api/match/promote', { method: 'POST', body: { action: 'promote', id: it.id } })
      .then(function () { removeMatchItem(el, t('m_promoted')); })
      .catch(function (e) {
        el.classList.remove('busy');
        var b = e && e.body;
        if (b && b.error === 'dup_blocked') {
          var note = el.querySelector('.mi-note');
          var msgs = (b.blockers || []).map(function (p) { return esc(store.lang === 'ar' ? p[0] : p[1]); }).join(' · ');
          note.hidden = false;
          note.innerHTML = '⚠️ ' + esc(t('m_blocked')) + msgs;
        } else toast(srvMsg(e) || t('act_failed'), 'err');
      });
  }

  /* ----- daftra drawer (details + split) ----- */
  function openMatchDrawer(el, it) {
    var dr = $('#mDrawer');
    if (!dr) return;
    dr.hidden = false;
    dr.innerHTML = '<div class="drawer-card card"><div class="grp-h"><h2>' + esc(t('m_drawer_title')) + '</h2>' +
      '<button class="btn ghost xs" data-act="m-drawer-close">✕</button></div><div class="drawer-body">' + skeleton(3) + '</div></div>';
    api('/erp/api/match/daftra?txn=' + encodeURIComponent(it.id)).then(function (d) {
      var body = dr.querySelector('.drawer-body');
      var amount = Number(it.amount);
      if (!(d.suggestions || []).length) {
        body.innerHTML = '<div class="state-sub">' + esc(t('m_no_sugg')) + '</div>' +
          '<div class="cp-btns">' +
          '<button class="btn ghost sm" data-act="m-notdup" data-id="' + esc(it.id) + '">' + esc(t('m_not_dup')) + '</button>' +
          '<button class="btn danger-ghost sm" data-act="m-ignore" data-id="' + esc(it.id) + '">' + esc(t('m_ignore')) + '</button></div>';
        return;
      }
      body.innerHTML = d.suggestions.slice(0, 5).map(function (s, si) {
        var lines = (s.lines || []).map(function (ln, li) {
          var amt = Number(ln.debit) > 0 ? ln.debit : ln.credit;
          var pre = (s.selected_line_ids || []).indexOf(String(ln.line_id)) >= 0;
          var consumed = ln.consumed || ln.fully_consumed;
          return '<label class="dln' + (consumed ? ' consumed' : '') + '">' +
            '<input type="checkbox" data-amt="' + esc(amt) + '" data-lid="' + esc(ln.line_id) + '"' +
            (pre ? ' checked' : '') + (consumed ? ' disabled' : '') + '>' +
            '<span class="dln-acc">' + esc(ln.account_name || '') + '</span>' +
            '<span class="dln-desc">' + esc((ln.description || '').slice(0, 50)) + '</span>' +
            '<code>' + fmtAmt(amt) + '</code>' +
            (consumed ? '<em class="tag bad">' + esc(t('m_consumed')) + '</em>' : '') +
          '</label>';
        }).join('');
        return '<div class="dsugg" data-eid="' + esc(s.entry_id) + '" data-num="' + esc(s.number || '') + '" data-conf="' + (s.confidence || 0) + '">' +
          '<div class="dsugg-h"><b>#' + esc(s.number || s.entry_id) + '</b><code>' + esc(s.date || '') + '</code>' +
          '<em class="cand-score">' + (s.confidence || 0) + '%</em>' +
          '<span class="wq-sub">' + esc(store.lang === 'ar' ? (s.reason_ar || '') : (s.reason_en || '')) + '</span></div>' +
          '<div class="wq-sub">' + esc((s.description || '').slice(0, 90)) + '</div>' +
          '<div class="dlines">' + lines + '</div>' +
          '<div class="dsum"><span>' + esc(t('m_lines_sum')) + ': <code class="dsum-val">0.00</code></span>' +
          '<span>' + esc(t('m_txn_amt')) + ': <code>' + fmtAmt(amount) + '</code></span>' +
          '<button class="btn primary sm" data-act="m-link-sel" data-id="' + esc(it.id) + '">' + esc(t('m_link_sel')) + '</button></div>' +
        '</div>';
      }).join('') +
      '<div class="cp-btns" style="margin-top:14px">' +
        '<button class="btn ghost sm" data-act="m-notdup" data-id="' + esc(it.id) + '">' + esc(t('m_not_dup')) + '</button>' +
        '<button class="btn danger-ghost sm" data-act="m-ignore" data-id="' + esc(it.id) + '">' + esc(t('m_ignore')) + '</button>' +
      '</div>';
      $$('.dsugg', body).forEach(updateDrawerSum);
    }).catch(function (e) {
      dr.querySelector('.drawer-body').innerHTML = errorCard('m-drawer-noop', srvMsg(e));
    });
  }

  function updateDrawerSum(sugg) {
    var sum = 0;
    $$('input[type=checkbox]:checked', sugg).forEach(function (c) { sum += Number(c.getAttribute('data-amt')) || 0; });
    var out = sugg.querySelector('.dsum-val');
    if (out) out.textContent = fmtAmt(sum);
  }

  /* ================= المصاريف Expenses (V4 re-shell) ================= */
  var expP = { tab: 'pending', q: '', o: 0 };
  var EXP_LIMIT = 60;

  function expHash() {
    var ps = new URLSearchParams();
    if (expP.tab !== 'pending') ps.set('tab', expP.tab);
    if (expP.q) ps.set('q', expP.q);
    if (expP.o > 0) ps.set('o', String(expP.o));
    var qs = ps.toString();
    return '#exp' + (qs ? '?' + qs : '');
  }
  function pushExpHash() {
    var h = expHash();
    if (location.hash !== h) location.hash = h;
    else loadExp();
  }

  function expSelectedIds() {
    return $$('.xrow input[data-act="x-sel"]:checked').map(function (c) { return c.getAttribute('data-id'); });
  }

  function expRowHtml(r) {
    var tab = expP.tab;
    var acts = '';
    if (tab === 'pending' || tab === 'needs_action') {
      acts = '<button class="btn primary xs" data-act="x-approve" data-id="' + esc(r.expense_id) + '">' + esc(t('x_approve')) + '</button>' +
             '<button class="btn danger-ghost xs" data-act="x-reject" data-id="' + esc(r.expense_id) + '">' + esc(t('x_reject')) + '</button>' +
             '<button class="btn ghost xs" data-act="x-edit" data-id="' + esc(r.expense_id) + '">' + esc(t('x_edit')) + '</button>';
    } else if (tab === 'approved') {
      acts = '<button class="btn primary xs" data-act="x-export" data-id="' + esc(r.expense_id) + '">' + esc(t('x_export')) + '</button>';
    } else if (tab === 'exported') {
      acts = '<button class="btn ghost xs" data-act="x-recheck" data-id="' + esc(r.expense_id) + '">' + esc(t('x_recheck')) + '</button>';
    }
    var missing = (r.missing_fields || []).length
      ? '<span class="tag bad">' + esc(t('x_missing')) + esc((r.missing_fields || []).join('، ')) + '</span>' : '';
    var bank = r.bank_txn_id
      ? '<a class="tag soft" href="#match">' + esc(t('x_bank_ok')) + '</a>'
      : '<a class="tag" href="#match" title="' + esc(t('x_open_match')) + '">' + esc(t('x_bank_no')) + '</a>';
    var receipt = r.receipt_url
      ? '<button class="btn ghost xs" data-act="x-receipt" data-url="' + esc(r.receipt_url) + '">🧾 ' + esc(t('x_receipt')) + '</button>'
      : '<span class="tag">' + esc(t('x_no_receipt')) + '</span>';
    return '<div class="wq-row xrow" data-id="' + esc(r.expense_id) + '">' +
      '<div class="c-sel"><input type="checkbox" data-act="x-sel" data-id="' + esc(r.expense_id) + '"></div>' +
      '<div class="wq-main" data-act="x-detail" data-id="' + esc(r.expense_id) + '" style="cursor:pointer">' +
        '<div class="wq-top"><span class="amt out">' + fmtAmt(r.amount_sar) + ' <i>' + esc(t('sar')) + '</i></span>' +
        (r.apartment ? '<span class="tag">' + esc(r.apartment) + '</span>' : '') +
        '<span class="tag soft">' + esc(r.concept || r.category || '') + '</span>' + missing + bank + '</div>' +
        '<div class="wq-sub"><code>' + esc(r.expense_date || '') + '</code> · ' + esc(t('x_by')) + ' ' + esc(r.submitter || '—') +
        (r.ouja_reference ? ' · <code>' + esc(r.ouja_reference) + '</code>' : '') +
        (r.last_error_message ? ' · <span class="tag bad">' + esc(r.last_error_message.slice(0, 60)) + '</span>' : '') + '</div>' +
      '</div>' +
      '<div class="wq-actions">' + receipt + acts + '</div>' +
      '<div class="wq-reason" hidden></div>' +
    '</div>';
  }

  function renderExp(d, append) {
    store.D.exp = d;
    var tabs = d.tabs || {};
    var chips = ['pending', 'approved', 'exported', 'verified', 'needs_action'].map(function (k) {
      return '<button class="fchip' + (expP.tab === k ? ' on' : '') + '" data-act="x-tab" data-tab="' + k + '">' +
        esc(t('x_' + k)) + (tabs[k] !== undefined ? ' <b>' + tabs[k] + '</b>' : '') + '</button>';
    }).join('');
    var rowsHtml = (d.rows || []).map(expRowHtml).join('');
    var moreBtn = (d.total > expP.o + (d.rows || []).length)
      ? '<div class="grp-more"><button class="btn ghost sm" data-act="x-more">' + esc(t('x_more')) +
        ' (' + (d.total - expP.o - (d.rows || []).length) + ')</button></div>' : '';
    if (append) {
      var list = $('#xList');
      if (list) { list.insertAdjacentHTML('beforeend', rowsHtml); var gm = $('#xMore'); if (gm) gm.outerHTML = '<div id="xMore">' + moreBtn + '</div>'; }
      return;
    }
    $('#view').innerHTML =
      '<div class="card bank-bar">' +
        '<div class="bb-row">' +
          '<input id="xSearch" class="in search" type="search" placeholder="' + esc(t('x_search')) + '" value="' + esc(expP.q) + '">' +
          (d.dryrun_on ? '<span class="tag warnt">' + esc(t('x_dryrun')) + '</span>' : '') +
        '</div>' +
        '<div class="bb-chips">' + chips + '</div>' +
      '</div>' +
      '<div class="card grp"><div class="grp-list" id="xList">' +
        (rowsHtml || '<div class="state-card"><div class="state-h">' + esc(t('x_empty')) + '</div></div>') +
      '</div><div id="xMore">' + moreBtn + '</div></div>' +
      '<div class="bulkbar" id="xBulk" hidden></div>';
    restoreScroll('exp');
  }

  function loadExp(append) {
    if (!append) $('#view').innerHTML = skeleton(6);
    var ps = new URLSearchParams();
    ps.set('tab', expP.tab); ps.set('limit', String(EXP_LIMIT)); ps.set('offset', String(expP.o));
    if (expP.q) ps.set('q', expP.q);
    api('/erp/api/exp?' + ps.toString()).then(function (d) { renderExp(d, append); })
      .catch(function (e) { $('#view').innerHTML = errorCard('retry_exp', srvMsg(e)); });
  }

  function updateExpBulk() {
    var ids = expSelectedIds();
    var bar = $('#xBulk');
    if (!bar) return;
    if (!ids.length) { bar.hidden = true; bar.innerHTML = ''; return; }
    bar.hidden = false;
    var btn = expP.tab === 'approved'
      ? '<button class="btn primary sm" data-act="x-bulk-export">' + esc(t('x_export')) + '</button>'
      : '<button class="btn primary sm" data-act="x-bulk-approve">' + esc(t('x_approve')) + '</button>';
    bar.innerHTML = '<b>' + ids.length + '</b> ' + esc(t('bulk_selected')) + ' ' + btn +
      ' <button class="btn ghost sm" data-act="x-bulk-clear">' + esc(t('bulk_clear')) + '</button>';
  }

  function expRemoveRow(id, msg) {
    var row = document.querySelector('.xrow[data-id="' + id + '"]');
    if (row) removeRow(row);
    if (msg) toast(msg);
  }

  function expReceiptLightbox(url) {
    var m = $('#xModal');
    if (!m) return;
    var img;
    if (url.indexOf('/fin/receipt/') === 0) {
      img = url;                       // owner-scoped proxy serves the bytes directly
    } else {
      var driveId = (url.match(/[-\w]{25,}/) || [])[0];
      img = driveId ? 'https://drive.google.com/thumbnail?id=' + driveId + '&sz=w1200' : url;
    }
    m.hidden = false;
    m.innerHTML = '<div class="drawer-card card"><div class="grp-h"><h2>' + esc(t('x_receipt')) + '</h2>' +
      '<a class="btn ghost xs" href="' + esc(url) + '" target="_blank" rel="noopener">↗</a>' +
      '<button class="btn ghost xs" data-act="x-modal-close">✕</button></div>' +
      '<div class="drawer-body" style="text-align:center">' +
      '<img id="xRcImg" src="' + esc(img) + '" alt="receipt" style="max-width:100%;border-radius:10px">' +
      '</div></div>';
    var im = $('#xRcImg');
    if (im) im.addEventListener('error', function () {
      im.outerHTML = '<div class="state-sub" style="padding:20px 0">' + esc(t('x_no_receipt')) +
        ' — <a href="' + esc(url) + '" target="_blank" rel="noopener">↗</a></div>';
    });
  }

  function expDetail(id) {
    var m = $('#xModal');
    if (!m) return;
    m.hidden = false;
    m.innerHTML = '<div class="drawer-card card"><div class="drawer-body">' + skeleton(4) + '</div></div>';
    api('/erp/api/exp/detail?id=' + encodeURIComponent(id)).then(function (d) {
      var v = d.view || {};
      var tl = (d.timeline || []).slice(-12).reverse().map(function (ev) {
        return '<div class="wq-sub"><code>' + esc((ev.at || '').slice(0, 16)) + '</code> ' + esc(ev.label_ar || ev.label || ev.kind || '') + '</div>';
      }).join('');
      m.innerHTML = '<div class="drawer-card card"><div class="grp-h"><h2>' + esc(v.concept || v.category || '') + '</h2>' +
        '<button class="btn ghost xs" data-act="x-modal-close">✕</button></div><div class="drawer-body">' +
        '<div class="wq-top" style="margin-bottom:8px"><span class="amt out">' + fmtAmt(v.amount_sar) + ' <i>' + esc(t('sar')) + '</i></span>' +
        '<span class="tag">' + esc(v.apartment || '—') + '</span><code>' + esc(v.expense_date || '') + '</code>' +
        (d.bank_txn_id ? '<a class="tag soft" href="#match">' + esc(t('x_bank_ok')) + '</a>' : '<span class="tag">' + esc(t('x_bank_no')) + '</span>') + '</div>' +
        (v.description ? '<div class="wq-desc">' + esc(v.description) + '</div>' : '') +
        '<div class="wq-sub">' + esc(t('x_by')) + ' ' + esc(v.submitter || '—') +
          (v.ouja_reference ? ' · <code>' + esc(v.ouja_reference) + '</code>' : '') +
          (v.hostaway_expense_id ? ' · HA <code>' + esc(v.hostaway_expense_id) + '</code>' : '') + '</div>' +
        (v.receipt_url ? '<div style="margin:10px 0"><button class="btn ghost sm" data-act="x-receipt" data-url="' + esc(v.receipt_url) + '">🧾 ' + esc(t('x_receipt')) + '</button></div>' : '') +
        '<h3 style="font-size:12.5px;margin:14px 0 4px">' + esc(t('x_timeline')) + '</h3>' + (tl || '<div class="wq-sub">—</div>') +
        '</div></div>';
    }).catch(function (e) {
      m.innerHTML = '<div class="drawer-card card"><div class="drawer-body">' + errorCard('x-modal-close', srvMsg(e)) + '</div></div>';
    });
  }

  function expEditDrawer(id) {
    var d = store.D.exp;
    var r = null;
    (d && d.rows || []).forEach(function (x) { if (String(x.expense_id) === String(id)) r = x; });
    if (!r) return;
    var m = $('#xModal');
    m.hidden = false;
    function f(label, key, val, type) {
      return '<label class="cp-f"><span>' + esc(label) + '</span><input class="in" id="xe_' + key + '" type="' + (type || 'text') + '" value="' + esc(val == null ? '' : val) + '"></label>';
    }
    m.innerHTML = '<div class="drawer-card card"><div class="grp-h"><h2>' + esc(t('x_edit')) + '</h2>' +
      '<button class="btn ghost xs" data-act="x-modal-close">✕</button></div><div class="drawer-body">' +
      '<div class="cp-grid" style="grid-template-columns:1fr 1fr">' +
      f(t('x_amount'), 'amount', r.amount_sar, 'number') +
      f(t('x_date'), 'expense_date', r.expense_date, 'date') +
      f(t('x_apartment'), 'apartment', r.apartment) +
      f(t('x_category'), 'category', r.category) +
      f(t('x_vendor'), 'vendor', r.vendor) +
      f(t('x_note'), 'note', r.description) +
      '</div><div class="cp-btns">' +
      '<button class="btn primary sm" data-act="x-edit-save" data-id="' + esc(id) + '">' + esc(t('save')) + '</button>' +
      '<button class="btn ghost sm" data-act="x-modal-close">' + esc(t('cancel')) + '</button>' +
      '</div></div></div>';
  }

  /* ================= العهد Custody ================= */
  function renderCustody(d) {
    var rows = (d.employees || []).map(function (e) {
      var open = Number(e.outstanding) > 0;
      return '<tr><td><b>' + esc(e.account) + '</b></td>' +
        '<td class="c-amt"><code>' + fmtAmt(e.issued) + '</code></td>' +
        '<td class="c-amt"><code>' + fmtAmt(e.settled) + '</code></td>' +
        '<td class="c-amt">' + (open ? '<code class="amt out">' + fmtAmt(e.outstanding) + '</code>'
                                      : '<span class="tag soft">' + esc(t('c_done')) + '</span>') + '</td>' +
        '<td class="c-amt"><code>' + (e.entries || 0) + '</code></td></tr>';
    }).join('');
    $('#view').innerHTML =
      '<section class="card grp">' +
        '<header class="grp-h"><span class="grp-ico">🧰</span><h2>' + esc(t('c_title')) + '</h2>' +
        '<span class="cnt">' + (d.open || 0) + ' ' + esc(t('c_open')) + '</span></header>' +
        '<div class="grp-hint" style="padding-bottom:10px">' + esc(t('c_explain')) + '</div>' +
        (rows
          ? '<div class="table-card" style="border:none;box-shadow:none"><table class="btable"><thead><tr>' +
            '<th>' + esc(t('c_employee')) + '</th><th>' + esc(t('c_issued')) + '</th><th>' + esc(t('c_settled')) + '</th>' +
            '<th>' + esc(t('c_outstanding')) + '</th><th>' + esc(t('c_entries')) + '</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
            '<div class="prev-stats" style="padding:0 20px 6px"><span class="pstat warn"><b>' + fmtAmt(d.outstanding_total || 0) + '</b>' + esc(t('c_total')) + '</span></div>'
          : '<div class="state-card"><div class="state-h">' + esc(t('c_empty')) + '</div></div>') +
        '<div class="grp-hint" style="padding-bottom:8px">' + esc(t('c_outstanding_note')) + '</div>' +
        '<div class="grp-cta"><a class="btn primary sm" href="#match?engine=founder">' + esc(t('c_settle_cta')) + '</a></div>' +
      '</section>';
    restoreScroll('custody');
  }

  function loadCustody() {
    $('#view').innerHTML = skeleton(4);
    api('/erp/api/custody').then(function (d) { store.D.custody = d; renderCustody(d); })
      .catch(function (e) { $('#view').innerHTML = errorCard('retry_custody', srvMsg(e)); });
  }

  /* ================= القوائم المالية Statements ================= */
  var stP = { m: '' };

  function monthInput(id, val) {
    return '<input id="' + id + '" class="in date" type="month" value="' + esc(val) + '">';
  }
  function nowMonth() { return new Date().toISOString().slice(0, 7); }

  function stRows(rows) {
    return (rows || []).map(function (r) {
      return '<div class="st-row" data-act="st-drill" data-id="' + esc(r.account_id) + '">' +
        '<code class="st-code">' + esc(r.code) + '</code><span class="st-name">' + esc(r.name) + '</span>' +
        (r.prior !== null && r.prior !== undefined ? '<code class="st-prior">' + fmtAmt(r.prior) + '</code>' : '<code class="st-prior"></code>') +
        '<code class="st-amt">' + fmtAmt(r.amount) + '</code></div>';
    }).join('');
  }

  function renderStmts(d) {
    store.D.stmts = d;
    var bs = d.balance_sheet;
    var inc = d.income;
    var eq = d.equity;
    var cf = d.cash_flow;
    var cov = d.coverage;
    var covBanner = cov.untyped
      ? '<div class="mi-note" style="margin:0 0 12px">' +
        esc(t('st_untyped_n').replace('{n}', cov.untyped)) + ' · ' + cov.pct + '% ' + esc(t('st_coverage')) + '</div>'
      : '';
    function totalLine(lbl, v, cls) {
      return '<div class="st-row total ' + (cls || '') + '"><span class="st-name">' + esc(lbl) + '</span>' +
        '<code class="st-prior"></code><code class="st-amt">' + fmtAmt(v) + '</code></div>';
    }
    var html =
      '<div class="card bank-bar"><div class="bb-row">' +
        '<span class="grp-hint" style="padding:0">' + esc(t('st_month')) + '</span>' + monthInput('stMonth', d.month) +
        '<a class="btn ghost sm" href="/erp/api/stmts/export.xlsx?m=' + esc(d.month) + '&token=' + encodeURIComponent(store.token) + '">⬇ ' + esc(t('st_export_x')) + '</a>' +
        '<a class="btn ghost sm" href="/erp/api/stmts/export.pdf?m=' + esc(d.month) + '&token=' + encodeURIComponent(store.token) + '">⬇ ' + esc(t('st_export_p')) + '</a>' +
      '</div><div class="grp-hint" style="padding:8px 0 0">' + esc(store.lang === 'ar' ? d.provenance_ar : d.provenance_en) + '</div></div>' +
      covBanner +

      '<section class="card grp st-card"><header class="grp-h"><h2>' + esc(t('st_bs')) + '</h2>' +
        (bs.balanced ? '<span class="tag soft">' + esc(t('st_balanced')) + '</span>'
                     : '<span class="tag bad">' + esc(t('st_gap')) + ' ' + fmtAmt(bs.totals.gap) + '</span>') + '</header>' +
        '<div class="st-body">' +
        '<h3>' + esc(t('st_assets')) + '</h3>' + stRows(bs.rows.asset) + totalLine(t('st_assets'), bs.totals.assets) +
        '<h3>' + esc(t('st_liab')) + '</h3>' + stRows(bs.rows.liability) + totalLine(t('st_liab'), bs.totals.liabilities) +
        '<h3>' + esc(t('st_equity')) + '</h3>' + stRows(bs.rows.equity) +
          totalLine(t('st_earn'), bs.totals.current_earnings) + totalLine(t('st_equity'), bs.totals.equity) +
        (bs.rows.untyped.length ? '<h3>' + esc(t('st_untyped')) + '</h3>' + stRows(bs.rows.untyped) +
          totalLine(t('st_untyped'), bs.totals.untyped_net_debit) : '') +
        '</div></section>' +

      '<section class="card grp st-card"><header class="grp-h"><h2>' + esc(t('st_is')) + '</h2>' +
        '<span class="cnt">' + esc(t('st_prior')) + ' ←</span></header><div class="st-body">' +
        '<h3>' + esc(t('st_income')) + '</h3>' + stRows(inc.income_rows) + totalLine(t('st_income'), inc.totals.income) +
        '<h3>' + esc(t('st_expenses')) + '</h3>' + stRows(inc.expense_rows) + totalLine(t('st_expenses'), inc.totals.expenses) +
        totalLine(t('st_net'), inc.totals.net, inc.totals.net >= 0 ? 'pos' : 'neg') +
        (inc.by_cost_center.length
          ? '<h3>' + esc(t('st_by_cc')) + '</h3>' + inc.by_cost_center.slice(0, 20).map(function (c) {
              return '<div class="st-row"><span class="st-name">' + esc(c.name || c.cost_center_id) + '</span>' +
                '<code class="st-prior">' + fmtAmt(c.expense) + '−</code><code class="st-amt">' + fmtAmt(c.net) + '</code></div>';
            }).join('')
          : '') +
        '</div></section>' +

      '<section class="card grp st-card"><header class="grp-h"><h2>' + esc(t('st_eq')) + '</h2>' +
        (eq.ties_to_balance_sheet ? '<span class="tag soft">' + esc(t('st_ties')) + '</span>'
                                  : '<span class="tag bad">' + esc(t('st_gap')) + ' ' + fmtAmt(eq.gap) + '</span>') +
        '</header><div class="st-body">' +
        totalLine(t('st_opening'), eq.opening) + totalLine(t('st_net_inc'), eq.net_income) +
        totalLine(t('st_contrib'), eq.contributions) + totalLine(t('st_withdraw'), eq.withdrawals) +
        totalLine(t('st_closing'), eq.closing) + '</div></section>' +

      '<section class="card grp st-card"><header class="grp-h"><h2>' + esc(t('st_cf')) + '</h2>' +
        (cf.ties_bank_register === true ? '<span class="tag soft">' + esc(t('st_bank_tie')) + '</span>'
          : cf.ties_bank_register === false ? '<span class="tag warnt">' + esc(t('st_bank_gap')) + ' ' + fmtAmt(cf.gap_vs_bank) + '</span>' : '') +
        '</header><div class="st-body">' +
        ['income', 'expense', 'asset', 'liability', 'equity', 'untyped'].map(function (k) {
          return totalLine(t('st_cf_' + k), cf.groups[k]);
        }).join('') +
        totalLine(t('st_net_cash'), cf.net_cash, cf.net_cash >= 0 ? 'pos' : 'neg') +
        totalLine(t('st_open_cash'), cf.opening_cash) + totalLine(t('st_close_cash'), cf.closing_cash) +
        totalLine(t('st_bank_delta'), cf.bank_register_delta === null ? 0 : cf.bank_register_delta) +
        '</div></section>' +
      '<div id="stDrill" class="drawer" hidden></div>';
    $('#view').innerHTML = html;
    restoreScroll('stmts');
  }

  function loadStmts() {
    $('#view').innerHTML = skeleton(8);
    api('/erp/api/stmts?m=' + encodeURIComponent(stP.m || nowMonth()))
      .then(renderStmts)
      .catch(function (e) { $('#view').innerHTML = errorCard('retry_stmts', srvMsg(e)); });
  }

  /* ================= الإقفال Close ================= */
  var clP = { m: '' };

  function renderClose(d) {
    store.D.close = d;
    var checks = (d.checks || []).map(function (c) {
      return '<div class="wq-row info"><div class="wq-main"><div class="wq-top">' +
        (c.ok ? '<span class="tag soft">✓</span>' : '<span class="tag bad">' + c.count + ' ' + esc(t('cl_item')) + '</span>') +
        '<b>' + esc(t('ck_' + c.key)) + '</b>' +
        ((c.owners || []).length ? '<span class="wq-sub">' + esc(c.owners.join('، ')) + '</span>' : '') +
        '</div></div></div>';
    }).join('');
    var closedBlock = d.closed
      ? '<div class="mi-note" style="background:var(--green-soft);color:var(--green)">' + esc(t('cl_closed')) +
        ' — ' + esc(t('cl_closed_at')) + ' <code>' + esc((d.snapshot || {}).closed_at || '') + '</code> ' +
        esc(t('cl_by')) + ' ' + esc((d.snapshot || {}).closed_by || '') + '</div>'
      : '<div class="grp-cta"><button class="btn danger sm" data-act="cl-close"' + (d.all_ok ? '' : ' disabled') + '>' +
        esc(t('cl_close_btn')) + '</button></div>';
    var migs = (d.migrations || []).map(function (m) {
      return '<div class="wq-sub"><code>' + esc((m.at || '').slice(0, 16)) + '</code> ' + esc(m.by || '') +
        ' · ' + (m.entry_ids || []).length + ' ' + esc(t('mg_entries')) +
        (m.disabled ? ' · <span class="tag warnt">dry</span>' : (m.result_ok ? ' · ✓' : ' · ✗')) + '</div>';
    }).join('');
    $('#view').innerHTML =
      '<div class="card bank-bar"><div class="bb-row">' +
        '<span class="grp-hint" style="padding:0">' + esc(t('st_month')) + '</span>' + monthInput('clMonth', d.month) +
      '</div></div>' +
      '<section class="card grp"><header class="grp-h"><span class="grp-ico">🔒</span><h2>' +
        esc(t('cl_title')) + ' — <code>' + esc(d.month) + '</code></h2></header>' +
        '<div class="grp-list">' + checks + '</div>' + closedBlock + '</section>' +
      '<section class="card grp"><header class="grp-h"><span class="grp-ico">📤</span><h2>' + esc(t('mg_title')) + '</h2>' +
        '<span class="cnt">' + d.migratable_entries + ' ' + esc(t('mg_entries')) + '</span></header>' +
        '<div class="grp-hint">' + esc(t('mg_hint')) + '</div>' +
        (!d.post_enabled ? '<div class="mi-note" style="margin:8px 20px">' + esc(t('mg_disabled')) + '</div>' : '') +
        '<div class="grp-cta">' +
          '<button class="btn ghost sm" data-act="mg-preview">' + esc(t('mg_preview')) + '</button>' +
          (d.closed
            ? '<button class="btn primary sm" data-act="mg-run">' + esc(t('mg_confirm')) + '</button>'
            : '<span class="tag">' + esc(t('mg_locked')) + '</span>') +
        '</div><div id="mgOut" style="padding:0 20px 14px"></div>' +
        (migs ? '<div style="padding:0 20px 14px"><h3 style="font-size:12px;margin:6px 0">' + esc(t('mg_log')) + '</h3>' + migs + '</div>' : '') +
      '</section>';
    restoreScroll('close');
  }

  function loadClose() {
    $('#view').innerHTML = skeleton(6);
    api('/erp/api/close?m=' + encodeURIComponent(clP.m || nowMonth()))
      .then(renderClose)
      .catch(function (e) { $('#view').innerHTML = errorCard('retry_close', srvMsg(e)); });
  }

  function renderMgDraft(d) {
    var out = $('#mgOut');
    if (!out) return;
    var draft = d.draft || {};
    var lines = (draft.lines || []).slice(0, 30).map(function (l) {
      return '<div class="st-row"><span class="st-name">' + esc(l.account || '') +
        (l.cost_center ? ' <span class="tag">' + esc(l.cost_center) + '</span>' : '') + '</span>' +
        '<code class="st-prior">' + esc(l.side || '') + '</code><code class="st-amt">' + fmtAmt(l.amount) + '</code></div>';
    }).join('');
    out.innerHTML = '<div class="mi-note" style="margin:8px 0;background:var(--blue-soft);color:var(--blue)">' +
      esc(d.dry_run ? t('mg_dry_done') : t('mg_done')) + ' · ' + (d.entry_ids || []).length + ' ' + esc(t('mg_entries')) + '</div>' +
      (lines || '<div class="wq-sub">' + esc(t('mg_none')) + '</div>') +
      ((draft.issues || []).length ? '<div class="mi-note">' + esc(t('mg_issues')) + ': ' +
        esc((draft.issues || []).map(function (i) { return i && (i.ar || i[0] || i); }).join(' · ')) + '</div>' : '');
  }

  /* ================= الميزانية Budget ================= */
  var bgP = { m: '' };

  function bgRowHtml(r) {
    var bar = r.pct === null ? '' :
      '<div class="bg-bar"><i style="width:' + Math.min(100, r.pct) + '%" class="' +
      (r.alert === 'over' ? 'over' : r.alert === 'warn' ? 'warn' : '') + '"></i></div>';
    return '<div class="wq-row" data-aid="' + esc(r.account_id) + '">' +
      '<div class="wq-main"><div class="wq-top"><b>' + esc(r.name) + '</b>' +
      (r.code ? '<code>' + esc(r.code) + '</code>' : '') +
      (r.alert ? '<span class="tag ' + (r.alert === 'over' ? 'bad' : 'warnt') + '">' +
        esc(r.alert === 'over' ? t('bg_over') : t('bg_warn')) + '</span>' : '') + '</div>' +
      bar +
      '<div class="wq-sub">' + esc(t('bg_actual')) + ' <code>' + fmtAmt(r.actual) + '</code> / <code>' + fmtAmt(r.budget) + '</code>' +
      (r.pct !== null ? ' · ' + r.pct + '% ' + esc(t('bg_used')) : '') +
      ' · ' + esc(t('bg_remaining')) + ' <code>' + fmtAmt(r.remaining) + '</code>' +
      (r.weekly && r.weekly.length ? ' · ' + esc(t('bg_weekly')) + ' <code>' + r.weekly.map(fmtAmt).join(' | ') + '</code>' : '') +
      '</div></div>' +
      '<div class="wq-actions">' +
        '<input class="in bg-amt" type="number" step="0.01" value="' + esc(r.budget) + '" style="width:110px">' +
        '<button class="btn primary xs" data-act="bg-save" data-aid="' + esc(r.account_id) + '">' + esc(t('save')) + '</button>' +
        '<button class="btn danger-ghost xs" data-act="bg-del" data-aid="' + esc(r.account_id) + '">✕</button>' +
      '</div></div>';
  }

  function renderBudget(d) {
    store.D.budget = d;
    var rows = (d.rows || []).map(bgRowHtml).join('');
    $('#view').innerHTML =
      '<div class="card bank-bar"><div class="bb-row">' +
        '<span class="grp-hint" style="padding:0">' + esc(t('st_month')) + '</span>' + monthInput('bgMonth', d.month) +
        '<button class="btn ghost sm" data-act="bg-copy-last">' + esc(t('bg_copy_last')) + '</button>' +
      '</div>' +
      '<div class="bb-row" style="margin-top:8px">' +
        '<input id="bgAccIn" class="in search" type="text" placeholder="' + esc(t('bg_add')) + '" autocomplete="off">' +
        '<input id="bgAccId" type="hidden">' +
        '<input id="bgAmtIn" class="in" type="number" step="0.01" placeholder="' + esc(t('bg_amount')) + '" style="width:130px">' +
        '<button class="btn primary sm" data-act="bg-add">' + esc(t('save')) + '</button>' +
      '</div><div id="bgAccList" class="acc-list" style="max-width:480px"></div></div>' +
      '<section class="card grp"><header class="grp-h"><span class="grp-ico">📊</span><h2>' +
        esc(t('bg_title')) + ' — <code>' + esc(d.month) + '</code></h2>' +
        '<span class="cnt">' + (d.rows || []).length + '</span></header>' +
        '<div class="grp-list">' +
        (rows || '<div class="state-card"><div class="state-h">' + esc(t('bg_empty')) + '</div></div>') +
        '</div></section>';
    var inp = $('#bgAccIn');
    if (inp) {
      ensureChart().then(function () {
        inp.addEventListener('input', function () { renderBgAccList(inp.value); });
      }).catch(function () {});
    }
    restoreScroll('budget');
  }

  function renderBgAccList(q) {
    var box = $('#bgAccList');
    if (!box || !store.chart) return;
    var qq = (q || '').trim().toLowerCase();
    if (!qq) { box.innerHTML = ''; return; }
    var hits = store.chart.accounts.filter(function (a) {
      return (a.name || '').toLowerCase().indexOf(qq) >= 0 || (a.code || '').toLowerCase().indexOf(qq) >= 0;
    }).slice(0, 10);
    var d = store.D.budget || {};
    box.innerHTML = hits.map(function (a) {
      var s3 = (d.avg3_actuals || {})[a.id];
      return '<button class="acc-opt" data-act="bg-pick-acc" data-acc="' + esc(a.id) + '">' +
        (a.code ? '<code>' + esc(a.code) + '</code> ' : '') + esc(a.name) +
        (s3 ? ' <span class="tag soft">' + esc(t('bg_avg3')) + ' ' + fmtAmt(s3) + '</span>' : '') + '</button>';
    }).join('');
  }

  function loadBudget() {
    $('#view').innerHTML = skeleton(5);
    api('/erp/api/budget?m=' + encodeURIComponent(bgP.m || nowMonth()))
      .then(renderBudget)
      .catch(function (e) { $('#view').innerHTML = errorCard('retry_budget', srvMsg(e)); });
  }

  /* ----- v2.2 slice 1: month-state helpers — the month must never lie ----- */
  function curMonthKey() {
    var n = new Date();
    return n.getFullYear() + '-' + ('0' + (n.getMonth() + 1)).slice(-2);
  }
  function monthState(m) {
    var c = curMonthKey();
    return m === c ? 'running' : (m < c ? 'closed' : 'future');
  }
  function mName(m) {
    var i = parseInt(String(m).slice(5, 7), 10) - 1;
    var arr = t('mnames');
    return (arr && arr[i] ? arr[i] : m) + ' ' + String(m).slice(0, 4);
  }
  function monthOptions(list, selected) {
    return list.map(function (m) {
      var st = monthState(m);
      var mark = st === 'running' ? (' — ' + t('mm_cur')) : (st === 'closed' ? ' — ' + t('mm_final') + ' ✓' : '');
      return '<option value="' + m + '"' + (m === selected ? ' selected' : '') + '>' + esc(m + mark) + '</option>';
    }).join('');
  }
  function lastNMonths(n) {
    var out = [], now = new Date();
    for (var i = 0; i < n; i++) {
      var dt = new Date(now.getFullYear(), now.getMonth() - i, 1);
      out.push(dt.getFullYear() + '-' + ('0' + (dt.getMonth() + 1)).slice(-2));
    }
    return out;
  }
  function mmStrip(meta) {
    /* the prominent running-month strip: badge + projection + same-days compare */
    if (!meta || meta.state !== 'running') return '';
    var h = '<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:2px 16px 8px">' +
      '<span class="tag warnt" style="font-weight:700">⏳ ' +
      esc(t('mm_running').replace('{d}', meta.day_of_month).replace('{n}', meta.days_in_month)) + '</span>';
    if (meta.projection != null) {
      h += '<span class="tag">' + esc(t('mm_proj')) + ': ~<code>' + fmtAmt(meta.projection) + '</code> <span style="color:var(--mut)">(' + esc(t('mm_est')) + ')</span></span>';
    }
    var c = meta.compare;
    if (c && c.prev_net != null && c.cur_net != null) {
      var dl = c.cur_net - c.prev_net;
      h += '<span class="tag soft">' + esc(
        t('mm_cmp').replace('{d}', c.days).replace('{pm}', mName(c.prev_month))
          .replace('{cm}', mName(meta.month)).replace('{a}', fmtAmt(c.prev_net)).replace('{b}', fmtAmt(c.cur_net))) +
        ' <b style="color:' + (dl >= 0 ? 'var(--green)' : 'var(--red)') + '">' + (dl >= 0 ? '+' : '−') + fmtAmt(Math.abs(dl)) + '</b></span>';
    }
    return h + '</div>';
  }

  /* ================= الملاك Owners ================= */
  function ownerRowHtml(r) {
    var lk = r.link || {};
    var state = !lk.exists ? '<span class="tag">' + esc(t('o_no_link')) + '</span>'
      : lk.active ? '<span class="tag soft">' + esc(t('o_active')) + '</span>'
                  : '<span class="tag bad">' + esc(t('o_revoked')) + '</span>';
    var opened = lk.opened_at
      ? esc(t('o_last_open')) + ': <code>' + esc(lk.opened_at.slice(0, 16)) + '</code> · ' + lk.opens + ' ' + esc(t('o_opens'))
      : esc(t('o_never'));
    var acts = '<a class="btn ghost xs" href="#owners?stmt=' + encodeURIComponent(r.owner) + '">' + esc(t('o_stmt')) + '</a>' +
      '<a class="btn ghost xs" href="#owners?manage=' + encodeURIComponent(r.owner) + '">' + esc(t('o_manage')) + '</a>' +
      '<a class="btn ghost xs" href="#owners?diag=' + encodeURIComponent(r.owner) + '">' + esc(t('o_diag')) + '</a>';
    if (lk.exists && lk.active) {
      acts += '<button class="btn primary xs" data-act="o-copy" data-url="' + esc(lk.url) + '">' + esc(t('o_copy')) + '</button>' +
        '<a class="btn ghost xs" href="' + esc(lk.url) + '" target="_blank" rel="noopener">' + esc(t('o_preview')) + '</a>' +
        '<button class="btn ghost xs" data-act="o-regen" data-owner="' + esc(r.owner) + '">' + esc(t('o_regen')) + '</button>' +
        '<button class="btn danger-ghost xs" data-act="o-revoke" data-owner="' + esc(r.owner) + '">' + esc(t('o_revoke')) + '</button>';
    } else {
      acts += '<button class="btn primary xs" data-act="o-create" data-owner="' + esc(r.owner) + '">' + esc(t('o_create')) + '</button>';
    }
    var mgmt = (r.mgmt_pct === null || r.mgmt_pct === undefined) ? ''
      : '<span class="tag">' + esc(t('o_mgmt')) + ' ' + esc(Array.isArray(r.mgmt_pct) ? r.mgmt_pct.join('/') : r.mgmt_pct) + '%</span>';
    return '<div class="wq-row" id="ow_' + esc(r.owner) + '">' +
      '<div class="wq-main"><div class="wq-top"><b>' + esc(r.owner) + '</b>' +
      '<span class="tag soft">' + r.units + ' ' + esc(t('o_units')) + '</span>' + mgmt + state + '</div>' +
      '<div class="wq-sub">' + esc((r.apartments || []).join(' · ')) + '</div>' +
      '<div class="wq-sub">' + opened + '</div></div>' +
      '<div class="wq-actions">' + acts + '</div></div>';
  }

  /* ----- slice 3: دورة الشهر — the monthly cycle board ----- */
  var cyUI = { m: '', filter: 'all', sel: {}, tplOpen: false };

  function cyWaLink(r, d) {
    var msg = (d.wa_template || '')
      .split('{owner}').join(r.owner)
      .split('{month}').join(d.month)
      .split('{net}').join(r.net != null ? fmtAmt(r.net) : '—')
      .split('{link}').join(location.origin + ((r.link || {}).url || ''));
    var phone = (r.phone || '').replace(/[^0-9]/g, '');
    return 'https://wa.me/' + phone + '?text=' + encodeURIComponent(msg);
  }

  function cyPills(r) {
    var order = ['draft', 'ready', 'reviewed', 'sent', 'opened'];
    var idx = order.indexOf(r.status);
    return '<div class="cy-pills">' + order.map(function (s, i) {
      return '<button class="cy-pill' + (i <= idx ? ' on' : '') + (s === r.status ? ' cur' : '') + '"' +
        ' data-act="cy-status" data-owner="' + esc(r.owner) + '" data-to="' + s + '"' +
        ' title="' + esc(t('cy_s_' + s)) + '">' + esc(t('cy_s_' + s)) + '</button>';
    }).join('<span class="cy-arrow">›</span>') + '</div>';
  }

  function cyRowHtml(r, d) {
    var anoms = r.flagged
      ? (r.anomalies || []).map(function (a) {
          return '<span class="tag ' + (a.sev === 'bad' ? 'bad' : '') + '">' +
            esc(store.lang === 'ar' ? a.ar : (a.en || a.ar)) + '</span>';
        }).join(' ')
      : '<span class="tag soft">' + esc(t('cy_anom_none')) + '</span>';
    var hasLink = (r.link || {}).url;
    var wa = (r.phone && hasLink)
      ? '<button class="btn primary xs" data-act="cy-wa" data-owner="' + esc(r.owner) + '">' + esc(t('cy_wa')) + '</button>'
      : '<button class="btn ghost xs" disabled title="' + esc(r.phone ? t('cy_no_link') : t('cy_wa_no_phone')) + '">' + esc(t('cy_wa')) + '</button>';
    return '<div class="wq-row' + (r.flagged ? '' : ' info') + '" data-owner="' + esc(r.owner) + '">' +
      '<label class="cy-check"><input type="checkbox" data-act="cy-sel" data-owner="' + esc(r.owner) + '"' +
      (cyUI.sel[r.owner] ? ' checked' : '') + '></label>' +
      '<div class="wq-main"><div class="wq-top"><b>' + esc(r.owner) + '</b>' +
      '<span class="tag soft">' + r.units + ' ' + esc(t('o_units')) + '</span>' +
      (r.net != null ? '<span class="tag"><code>' + fmtAmt(r.net) + '</code></span>' : '') +
      (r.published_version ? '<span class="tag soft">' + esc(t('se_ver')) + ' ' + r.published_version + '</span>' : '') +
      '</div>' +
      '<div class="wq-sub">' + anoms + '</div>' +
      cyPills(r) + '</div>' +
      '<div class="wq-actions">' + wa +
      '<a class="btn ghost xs" href="#owners?stmt=' + encodeURIComponent(r.owner) + '&m=' + esc(d.month) + '">' + esc(t('o_stmt')) + '</a>' +
      '<a class="btn ghost xs" href="#owners?manage=' + encodeURIComponent(r.owner) + '">' + esc(t('o_manage')) + '</a>' +
      (hasLink ? '<button class="btn ghost xs" data-act="o-copy" data-url="' + esc(r.link.url) + '">' + esc(t('o_copy')) + '</button>' : '') +
      '</div></div>';
  }

  function cycleBoardHtml(d) {
    var c = d.counts || {};
    function chip(key, label, n) {
      return '<button class="chip-f' + (cyUI.filter === key ? ' on' : '') + '" data-act="cy-filter" data-f="' + key + '">' +
        esc(label) + ' <code>' + n + '</code></button>';
    }
    var months = lastNMonths(13);
    var rows = (d.rows || []).filter(function (r) {
      if (cyUI.filter === 'flagged') return r.flagged;
      if (cyUI.filter === 'ready') return r.status === 'ready' || r.status === 'reviewed';
      if (cyUI.filter === 'sent') return r.status === 'sent' || r.status === 'opened';
      if (cyUI.filter === 'opened') return r.status === 'opened';
      return true;
    });
    var nsel = Object.keys(cyUI.sel).filter(function (k) { return cyUI.sel[k]; }).length;
    var bulk = nsel
      ? '<div class="cy-bulk"><b>' + nsel + ' ' + esc(t('cy_selected')) + '</b> · ' + esc(t('cy_bulk_to')) + ': ' +
        ['ready', 'reviewed', 'sent'].map(function (s) {
          return '<button class="btn ghost xs" data-act="cy-bulk" data-to="' + s + '">' + esc(t('cy_s_' + s)) + '</button>';
        }).join(' ') + '</div>'
      : '';
    return '<section class="card grp">' +
      '<header class="grp-h"><span class="grp-ico">📆</span><h2>' + esc(t('cy_title')) + '</h2>' +
      '<span style="margin-inline-start:auto;display:flex;gap:6px;align-items:center;flex-wrap:wrap">' +
      '<select class="in" id="cyMonth">' + monthOptions(months, d.month) + '</select>' +
      '<button class="btn ghost xs" data-act="cy-copy-all">' + esc(t('cy_copy_all')) + '</button>' +
      '<button class="btn danger-ghost xs" data-act="cy-regen-all">' + esc(t('cy_regen_all')) + '</button>' +
      '<button class="btn ghost xs" data-act="cy-tpl">' + esc(t('cy_template')) + '</button>' +
      '</span></header>' +
      mmStrip(d.month_meta) +
      (cyUI.tplOpen
        ? '<div class="om-form" style="margin:0 16px 10px"><div class="grp-hint" style="padding:0">' + esc(t('cy_template_hint')) + '</div>' +
          '<textarea class="in" id="cyTpl" rows="4" style="resize:vertical">' + esc(d.wa_template || '') + '</textarea>' +
          '<button class="btn primary xs" data-act="cy-tpl-save">' + esc(t('se_save')) + '</button></div>'
        : '') +
      '<div class="cy-chips">' +
      chip('all', t('cy_all'), c.total || 0) +
      chip('ready', t('cy_ready'), (c.ready || 0) + '/' + (c.total || 0)) +
      chip('sent', t('cy_sent'), c.sent || 0) +
      chip('opened', t('cy_opened'), c.opened || 0) +
      chip('flagged', t('cy_flagged'), c.flagged || 0) +
      '<span class="tag soft" style="margin-inline-start:auto">' + esc(t('cy_portfolio')) + ' <code>' + fmtAmt(d.portfolio_net) + '</code></span>' +
      '</div>' +
      (d.done ? '<div class="wq-row info" style="margin:0 16px 10px"><div class="wq-main"><div class="wq-top">' + esc(t('cy_done')) + '</div></div></div>' : '') +
      ((c.flagged && cyUI.filter === 'all') ? '<div class="grp-hint">' + esc(t('cy_review_first')) + '</div>' : '') +
      bulk +
      '<div class="grp-list">' + rows.map(function (r) { return cyRowHtml(r, d); }).join('') + '</div>' +
      '</section>';
  }

  function renderOwners(d) {
    if (d) store.D.owners = d;
    d = store.D.owners || {};
    var cy = store.D.cycle;
    var y = window.scrollY;
    $('#view').innerHTML =
      (cy ? cycleBoardHtml(cy) : '') +
      '<section class="card grp">' +
        '<header class="grp-h"><span class="grp-ico">🏠</span><h2>' + esc(t('o_title')) + '</h2>' +
        '<span class="cnt">' + (d.total || 0) + '</span></header>' +
        '<div class="grp-hint">' + esc(t('o_hint')) + '</div>' +
        '<div class="grp-list">' +
        ((d.rows || []).length ? d.rows.map(ownerRowHtml).join('')
          : '<div class="state-card"><div class="state-h">' + esc(t('o_empty')) + '</div></div>') +
        '</div></section>';
    var sel = $('#cyMonth');
    if (sel) sel.addEventListener('change', function () {
      cyUI.m = sel.value;
      cyUI.sel = {};
      loadCycle();
    });
    window.scrollTo(0, y);
  }

  function loadCycle() {
    return api('/erp/api/owners/cycle' + (cyUI.m ? '?m=' + encodeURIComponent(cyUI.m) : ''))
      .then(function (c) { store.D.cycle = c; cyUI.m = c.month; renderOwners(null); })
      .catch(function () { /* board absent; the owners list still renders */ });
  }

  function loadOwners() {
    $('#view').innerHTML = skeleton(5);
    Promise.all([
      api('/erp/api/owners'),
      api('/erp/api/owners/cycle' + (cyUI.m ? '?m=' + encodeURIComponent(cyUI.m) : '')).catch(function () { return null; })
    ]).then(function (rs) {
      store.D.cycle = rs[1];
      if (rs[1]) cyUI.m = rs[1].month;
      renderOwners(rs[0]);
      restoreScroll('owners');
    }).catch(function (e) { $('#view').innerHTML = errorCard('retry_owners', srvMsg(e)); });
  }

  /* ----- slice 0b: statement diagnosis (line-by-line reconciliation) ----- */
  function rsnLabel(reason) {
    if (!reason) return '';
    if (reason.indexOf('status_') === 0) return t('rsn_status') + ' (' + esc(reason.slice(7)) + ')';
    var k = 'rsn_' + reason;
    var v = T[store.lang][k] || T.ar[k];
    return v || esc(reason);
  }

  function diagRowHtml(r) {
    var inc = r.verdict === 'included';
    var amt = inc ? ('<b>' + fmtAmt(r.amount) + '</b>')
      : (r.reference != null ? ('<span class="tag">' + esc(t('dg_ref')) + ' ' + fmtAmt(r.reference) + '</span>') : '—');
    var flags = '';
    if (!r.in_history_cache) flags += ' <span class="tag bad">' + esc(t('dg_cache_miss')) + '</span>';
    if (r.unit_added_by_fix) flags += ' <span class="tag soft">' + esc(t('dg_unit_fix')) + '</span>';
    return '<tr class="' + (inc ? '' : 'off') + '">' +
      '<td>' + esc(r.apartment || '') + '</td>' +
      '<td><b>' + esc(r.guest || '—') + '</b><div class="wq-sub">' + esc(r.channel || '') + ' · ' + esc(r.status || '') + '</div></td>' +
      '<td><code>' + esc(r.checkin || '') + '</code> ← <code>' + esc(r.checkout || '') + '</code></td>' +
      '<td>' + (inc ? '<span class="tag soft">' + esc(t('dg_included')) + '</span>'
                    : '<span class="tag bad">' + esc(t('dg_excluded')) + '</span> ' + rsnLabel(r.reason)) + flags + '</td>' +
      '<td class="c-amt">' + amt + '</td></tr>';
  }

  function renderDiag(d) {
    store.D.diag = d;
    var tt = d.totals || {};
    function stat(label, val, cls) {
      return '<div class="stat ' + (cls || '') + '"><span>' + esc(label) + '</span><b>' +
        (val == null ? '—' : fmtAmt(val)) + '</b></div>';
    }
    var months = [];
    var now = new Date();
    for (var i = 0; i < 13; i++) {
      var dt = new Date(now.getFullYear(), now.getMonth() - i, 1);
      months.push(dt.getFullYear() + '-' + ('0' + (dt.getMonth() + 1)).slice(-2));
    }
    var monthSel = '<select class="in" id="dgMonth">' + months.map(function (m) {
      return '<option value="' + m + '"' + (m === d.month ? ' selected' : '') + '>' + m + '</option>';
    }).join('') + '</select>';
    var unitsHtml = (d.units || []).map(function (u) {
      return '<div class="wq-row' + (u.added_by_fix ? '' : ' info') + '"><div class="wq-main"><div class="wq-top"><b>' + esc(u.apartment) + '</b>' +
        '<span class="tag soft">' + esc(u.listing || '') + '</span>' +
        (u.mgmt_pct != null ? '<span class="tag">' + esc(t('o_mgmt')) + ' ' + u.mgmt_pct + '%</span>' : '') +
        (u.added_by_fix ? '<span class="tag bad">' + esc(t('dg_unit_fix')) + '</span>' : '') +
        (u.lid_unresolved ? '<span class="tag bad">' + esc(t('dg_lid_missing')) + '</span>' : '') + '</div>' +
        '<div class="wq-sub">' + esc(t('st_income')) + ' ' + fmtAmt(u.income) + ' · ' + esc(t('st_net')) + ' ' + fmtAmt(u.net) + '</div></div></div>';
    }).join('');
    var fields = Object.keys(d.field_histogram || {}).sort().map(function (k) {
      return '<span class="tag"><code>' + esc(k) + '</code> × ' + d.field_histogram[k] + '</span>';
    }).join(' ');
    var exs = d.excluded_summary || {};
    $('#view').innerHTML =
      '<a class="btn ghost sm" href="#owners">' + esc(t('dg_back')) + '</a>' +
      '<section class="card grp"><header class="grp-h"><span class="grp-ico">🔬</span>' +
      '<h2>' + esc(t('dg_title')) + ' — ' + esc(d.owner) + '</h2>' +
      '<span style="margin-inline-start:auto">' + esc(t('dg_month')) + ' ' + monthSel + '</span></header>' +
      '<div class="stat-row">' +
      stat(t('dg_now'), tt.statement_net_now) +
      stat(t('dg_prefix'), tt.pre_fix_net_estimate, 'bad') +
      stat(t('dg_fixed'), tt.fixed_net, 'ok') +
      stat(t('dg_lost_tr'), tt.lost_to_truncation_income) +
      stat(t('dg_lost_unit'), tt.lost_to_missing_unit_income) +
      (exs.needs_review ? stat(t('dg_excl_total') + ' (' + exs.needs_review + ')', exs.needs_review_reference, 'bad') : '') +
      '</div>' +
      '<div class="grp-hint">' + esc(t('dg_units')) + '</div><div class="grp-list">' + unitsHtml + '</div>' +
      '<div class="grp-hint">' + esc(t('dg_rows')) + ' · ' + (d.rows || []).length + '</div>' +
      ((d.rows || []).length
        ? '<div class="table-card" style="border:none;box-shadow:none;overflow-x:auto"><table class="btable"><thead><tr>' +
          '<th>' + esc(t('unit_label')) + '</th><th>' + esc(t('th_desc')) + '</th><th>' + esc(t('th_date')) + '</th>' +
          '<th>' + esc(t('th_pipe')) + '</th><th>' + esc(t('th_amount')) + '</th></tr></thead><tbody>' +
          (d.rows || []).map(diagRowHtml).join('') + '</tbody></table></div>'
        : '<div class="state-card"><div class="state-h">' + esc(t('dg_empty')) + '</div></div>') +
      '<div class="grp-hint">' + esc(t('dg_field_hist')) + '</div>' +
      '<div style="padding:0 16px 16px;display:flex;flex-wrap:wrap;gap:6px">' + (fields || '—') + '</div>' +
      '</section>';
    var sel = $('#dgMonth');
    if (sel) sel.addEventListener('change', function () {
      location.hash = 'owners?diag=' + encodeURIComponent(d.owner) + '&m=' + sel.value;
    });
  }

  function loadDiag(owner, m) {
    $('#view').innerHTML = skeleton(6);
    api('/erp/api/owners/diagnose?owner=' + encodeURIComponent(owner) + (m ? '&m=' + encodeURIComponent(m) : ''))
      .then(renderDiag)
      .catch(function (e) { $('#view').innerHTML = errorCard('retry_owners', srvMsg(e)); });
  }

  /* ----- slice 1: owner & apartment manager (effective-dated) ----- */
  function clTxt(cl) {
    cl = cl || {};
    return cl.type === 'owner' ? (t('om_cl_owner') + ' · ' + fmtAmt(cl.amount)) : t('om_cl_ours');
  }

  function manageUnitHtml(u) {
    var win = (u.contract_from || '—') + ' ← ' + (u.contract_to || t('om_open_ended'));
    var terms = (u.terms || []).map(function (x) {
      return '<div class="wq-sub"><code>' + esc(x.from || '∅') + '</code> → ' +
        (x.mgmt_pct != null ? (t('om_mgmt') + ' ' + x.mgmt_pct + '%') : '') +
        (x.cleaning ? (' · ' + clTxt(x.cleaning)) : '') + '</div>';
    }).join('');
    return '<div class="wq-row" data-apt="' + esc(u.apartment) + '">' +
      '<div class="wq-main"><div class="wq-top"><b>' + esc(u.apartment) + '</b>' +
      '<span class="tag soft">' + esc(u.listing || '') + '</span>' +
      (u.lid == null ? '<span class="tag bad">' + esc(t('dg_lid_missing')) + '</span>' : '') +
      '<span class="tag">' + esc(t('om_now')) + ': ' + (u.mgmt_now != null ? u.mgmt_now + '%' : '—') +
      ' · ' + clTxt(u.cleaning_now) + '</span></div>' +
      '<div class="wq-sub">' + esc(t('om_contract')) + ': <code>' + esc(win) + '</code></div>' +
      (terms ? ('<div class="wq-sub"><b>' + esc(t('om_terms_n')) + ':</b></div>' + terms) : '') +
      '<div class="om-forms">' +
      /* terms form */
      '<div class="om-form" data-form="terms" hidden>' +
        '<b>' + esc(t('om_terms_title')) + '</b><div class="grp-hint" style="padding:0">' + esc(t('om_terms_hint')) + '</div>' +
        '<div class="om-grid">' +
        '<label>' + esc(t('om_terms_from')) + '<input type="date" class="in om-t-from"></label>' +
        '<label>' + esc(t('om_mgmt')) + '<input type="number" step="0.5" min="0" max="60" class="in om-t-mgmt" value="' + (u.mgmt_now != null ? u.mgmt_now : '') + '"></label>' +
        '<label>' + esc(t('om_cleaning')) + '<select class="in om-t-cltype"><option value="ours"' + ((u.cleaning_now || {}).type !== 'owner' ? ' selected' : '') + '>' + esc(t('om_cl_ours')) + '</option><option value="owner"' + ((u.cleaning_now || {}).type === 'owner' ? ' selected' : '') + '>' + esc(t('om_cl_owner')) + '</option></select></label>' +
        '<label>' + esc(t('om_cl_amount')) + '<input type="number" step="1" min="0" class="in om-t-clamt" value="' + ((u.cleaning_now || {}).amount || 0) + '"></label>' +
        '</div><input class="in om-t-reason" placeholder="' + esc(t('om_reason')) + '">' +
        '<button class="btn primary sm" data-act="om-terms-save" data-apt="' + esc(u.apartment) + '">' + esc(t('om_terms_save')) + '</button>' +
      '</div>' +
      /* remove form */
      '<div class="om-form" data-form="remove" hidden>' +
        '<b>' + esc(t('om_remove_title')) + '</b><div class="grp-hint" style="padding:0">' + esc(t('om_remove_hint')) + '</div>' +
        '<div class="om-grid">' +
        '<label>' + esc(t('om_to')) + '<input type="date" class="in om-r-to"></label>' +
        '</div><input class="in om-r-reason" placeholder="' + esc(t('om_reason')) + '">' +
        '<button class="btn danger-ghost sm" data-act="om-remove-do" data-apt="' + esc(u.apartment) + '">' + esc(t('om_remove_do')) + '</button>' +
      '</div>' +
      '</div></div>' +
      '<div class="wq-actions">' +
      '<button class="btn ghost xs" data-act="om-toggle-form" data-form="terms">' + esc(t('om_terms_btn')) + '</button>' +
      '<button class="btn danger-ghost xs" data-act="om-toggle-form" data-form="remove">' + esc(t('om_remove_btn')) + '</button>' +
      '</div></div>';
  }

  function renderManage(d) {
    store.D.manage = d;
    var p = d.profile || {};
    var vers = (d.versions || []).map(function (v) {
      return '<div class="wq-sub"><code>' + esc((v.at || '').slice(0, 16)) + '</code> · ' + esc(v.by || '') +
        ' · <b>' + esc(v.what || '') + '</b> · ' + esc(v.target || '') +
        (v.reason ? (' — ' + esc(v.reason)) : '') + '</div>';
    }).join('');
    $('#view').innerHTML =
      '<a class="btn ghost sm" href="#owners">' + esc(t('dg_back')) + '</a>' +
      '<section class="card grp"><header class="grp-h"><span class="grp-ico">👤</span>' +
      '<h2>' + esc(t('om_title')) + ' — ' + esc(d.owner) + '</h2></header>' +
      '<div class="om-grid" style="padding:0 16px 8px">' +
      '<label>' + esc(t('om_phone')) + '<input class="in" id="omPhone" dir="ltr" placeholder="9665xxxxxxxx" value="' + esc(p.phone || '') + '"></label>' +
      '<label>' + esc(t('om_notes')) + '<input class="in" id="omNotes" value="' + esc(p.notes || '') + '"></label>' +
      '<label>' + esc(t('om_active')) + '<select class="in" id="omActive"><option value="1"' + (p.active !== false ? ' selected' : '') + '>' + esc(t('om_active')) + '</option><option value="0"' + (p.active === false ? ' selected' : '') + '>' + esc(t('om_paused')) + '</option></select></label>' +
      '</div><div style="padding:0 16px 14px"><button class="btn primary sm" data-act="om-save" data-owner="' + esc(d.owner) + '">' + esc(t('om_save')) + '</button></div>' +
      '</section>' +
      '<section class="card grp"><header class="grp-h"><span class="grp-ico">🏠</span><h2>' + esc(t('om_units')) + '</h2>' +
      '<span class="cnt">' + (d.units || []).length + '</span></header>' +
      '<div class="grp-list">' + (d.units || []).map(manageUnitHtml).join('') + '</div>' +
      '<div style="padding:12px 16px 16px;border-top:1px solid var(--line)">' +
      '<b>' + esc(t('om_add_unit')) + '</b>' +
      '<input class="in" id="omLSearch" placeholder="' + esc(t('om_search_listing')) + '" style="margin:8px 0 4px">' +
      '<div id="omLResults"></div>' +
      '<div id="omAddForm" hidden>' +
      '<div class="om-grid">' +
      '<label>' + esc(t('om_code')) + '<input class="in" id="omAddApt"></label>' +
      '<label>' + esc(t('om_from')) + '<input type="date" class="in" id="omAddFrom"></label>' +
      '<label>' + esc(t('om_mgmt')) + '<input type="number" step="0.5" min="0" max="60" class="in" id="omAddMgmt" value="20"></label>' +
      '<label>' + esc(t('om_cleaning')) + '<select class="in" id="omAddClType"><option value="ours">' + esc(t('om_cl_ours')) + '</option><option value="owner">' + esc(t('om_cl_owner')) + '</option></select></label>' +
      '<label>' + esc(t('om_cl_amount')) + '<input type="number" step="1" min="0" class="in" id="omAddClAmt" value="0"></label>' +
      '</div><input type="hidden" id="omAddLid">' +
      '<button class="btn primary sm" data-act="om-unit-add" data-owner="' + esc(d.owner) + '">' + esc(t('om_add_do')) + '</button>' +
      '</div></div>' +
      '</section>' +
      '<section class="card grp"><header class="grp-h"><span class="grp-ico">🗂️</span><h2>' + esc(t('om_history')) + '</h2></header>' +
      '<div style="padding:0 16px 16px">' + (vers || ('<div class="grp-hint" style="padding:0">' + esc(t('om_no_changes')) + '</div>')) + '</div>' +
      '</section>';
    var ls = $('#omLSearch');
    if (ls) {
      var tmr = null;
      ls.addEventListener('input', function () {
        clearTimeout(tmr);
        tmr = setTimeout(function () {
          var q = ls.value.trim();
          if (q.length < 2) { $('#omLResults').innerHTML = ''; return; }
          api('/erp/api/owners/listings-search?q=' + encodeURIComponent(q)).then(function (r) {
            $('#omLResults').innerHTML = (r.rows || []).map(function (x) {
              return '<button class="acc-opt" data-act="om-pick-listing" data-lid="' + x.lid + '" data-name="' + esc(x.name) + '"' +
                (x.owner ? ' disabled title="' + esc(t('om_taken') + ' ' + x.owner) + '"' : '') + '>' +
                esc(x.name) + (x.owner ? ' <span class="tag bad">' + esc(t('om_taken')) + ' ' + esc(x.owner) + '</span>' : '') + '</button>';
            }).join('');
          }).catch(function () {});
        }, 250);
      });
    }
  }

  function loadManage(owner) {
    $('#view').innerHTML = skeleton(5);
    api('/erp/api/owners/detail?owner=' + encodeURIComponent(owner))
      .then(renderManage)
      .catch(function (e) { $('#view').innerHTML = errorCard('retry_owners', srvMsg(e)); });
  }

  /* ----- slice 2: statement editor + «ليش هالرقم؟» + audit trail ----- */
  var seUI = { tab: 'stmt', explain: '' };

  function seReasonRow(cls, extra) {
    return '<div class="om-form se-inline" data-need="' + cls + '" hidden>' + (extra || '') +
      '<input class="in se-reason" placeholder="' + esc(t('se_reason_req')) + '">' +
      '<button class="btn primary xs" data-act="' + cls + '-go">' + esc(t('se_save')) + '</button></div>';
  }

  function seResvRow(l, kind) {
    var chips = '';
    if (l.manual_included) chips += '<span class="tag soft">' + esc(t('se_incl_chip')) + '</span>';
    if (l.manual_excluded) chips += '<span class="tag bad">' + esc(t('se_excl_chip_manual')) + '</span>';
    if (!l.manual_excluded && l.exclude_reason) chips += '<span class="tag bad">' + rsnLabel(l.exclude_reason) + '</span>';
    if (l.edit_reason) chips += '<span class="tag">' + esc(t('se_manual_chip')) + ': ' + esc(l.edit_reason) + '</span>';
    var amt = (l.income != null) ? ('<b>' + fmtAmt(l.income) + '</b>')
      : (l.reference_total != null ? ('<span class="tag">' + esc(t('dg_ref')) + ' ' + fmtAmt(l.reference_total) + '</span>') : '—');
    var pct = (l.mgmt_pct_applied != null) ? ('<span class="tag soft">' + l.mgmt_pct_applied + '%</span>') : '';
    var act = '';
    if (kind === 'in') {
      act = '<button class="btn danger-ghost xs" data-act="se-x-open">' + esc(t('se_exclude')) + '</button>';
    } else {
      var needAmt = (l.income == null && !l.manual_excluded);
      act = '<button class="btn ghost xs" data-act="se-i-open" data-needamt="' + (needAmt ? '1' : '0') + '">' + esc(t('se_include')) + '</button>';
    }
    return '<div class="wq-row" data-rid="' + esc(String(l.id)) + '">' +
      '<div class="wq-main"><div class="wq-top"><b>' + esc(l.guest || '—') + '</b>' +
      '<span class="tag soft">' + esc(l.apartment || '') + '</span>' + pct + chips + '</div>' +
      '<div class="wq-sub"><code>' + esc(l.checkin || '') + '</code> ← <code>' + esc(l.checkout || '') + '</code> · ' +
      esc(l.channel || '') + (l.nights ? (' · ' + l.nights) : '') + '</div>' +
      seReasonRow('se-x') +
      seReasonRow('se-i', '<input type="number" step="0.01" class="in se-amt" placeholder="' + esc(t('se_amount_req')) + '" hidden>') +
      '</div><div class="wq-actions"><span class="c-amt">' + amt + '</span>' + act + '</div></div>';
  }

  function seExpRow(x) {
    var chips = (x.manual ? '<span class="tag soft">' + esc(t('se_manual_chip')) + '</span>' : '') +
      (x.edited ? '<span class="tag">' + esc(t('se_exp_edit')) + ' ✓</span>' : '') +
      (x.edit_reason ? '<span class="tag">' + esc(x.edit_reason) + '</span>' : '') +
      (x.receipt_url
        ? ' <button class="btn ghost xs" data-act="x-receipt" data-url="' + esc(x.receipt_url) + '">🧾 ' + esc(t('x_receipt')) + '</button>'
        : (x.manual ? '' : ' <span class="tag">' + esc(t('x_no_receipt')) + '</span>'));
    return '<div class="wq-row" data-xid="' + esc(String(x.id)) + '" data-manual="' + (x.manual ? '1' : '0') + '">' +
      '<div class="wq-main"><div class="wq-top"><b>' + esc(x.description || x.category || '—') + '</b>' + chips + '</div>' +
      '<div class="wq-sub"><code>' + esc(x.date || '') + '</code>' + (x.apartment ? (' · ' + esc(x.apartment)) : '') + '</div>' +
      '<div class="om-form se-inline" data-need="se-xe" hidden>' +
      '<div class="om-grid">' +
      '<label>' + esc(t('se_amount')) + '<input type="number" step="0.01" class="in se-e-amt" value="' + esc(String(x.amount != null ? x.amount : '')) + '"></label>' +
      '<label>' + esc(t('se_date')) + '<input type="date" class="in se-e-date" value="' + esc((x.date || '').slice(0, 10)) + '"></label>' +
      '<label>' + esc(t('se_desc')) + '<input class="in se-e-desc" value="' + esc(x.description || '') + '"></label>' +
      '</div><input class="in se-reason" placeholder="' + esc(t('se_reason_req')) + '">' +
      '<button class="btn primary xs" data-act="se-xe-go">' + esc(t('se_save')) + '</button></div>' +
      seReasonRow('se-xd') +
      '</div><div class="wq-actions"><span class="c-amt"><b>−' + fmtAmt(x.amount) + '</b></span>' +
      (x.manual
        ? '<button class="btn danger-ghost xs" data-act="se-man-del">' + esc(t('se_exp_del')) + '</button>'
        : '<button class="btn ghost xs" data-act="se-xe-open">' + esc(t('se_exp_edit')) + '</button>' +
          '<button class="btn danger-ghost xs" data-act="se-xd-open">' + esc(t('se_exp_del')) + '</button>') +
      '</div></div>';
  }

  function seExplainHtml(key, ex) {
    var e = (ex || {})[key];
    if (!e) return '';
    var rule = store.lang === 'ar' ? e.rule_ar : (e.rule_en || e.rule_ar);
    var rows = '';
    if (key === 'income') {
      rows = (e.lines || []).map(function (l) {
        return '<div class="foot-line"><span>' + esc(l.guest || l.id) + ' · ' + esc(l.apartment || '') +
          ' · <code>' + esc(l.checkin || '') + '</code>' + (l.manual_included ? ' <span class="tag soft">' + esc(t('se_incl_chip')) + '</span>' : '') +
          '</span><b>' + fmtAmt(l.amount) + '</b></div>';
      }).join('');
    } else if (key === 'fees') {
      rows = (e.groups || []).map(function (g) {
        return '<div class="foot-line"><span>' + esc(t('se_fee_grp').replace('{b}', fmtAmt(g.base)).replace('{p}', g.pct)) +
          '</span><b>' + fmtAmt(g.fee) + '</b></div>';
      }).join('');
    } else if (key === 'expenses') {
      rows = (e.lines || []).map(function (l) {
        return '<div class="foot-line"><span><code>' + esc(l.date || '') + '</code> ' + esc(l.description || '') +
          (l.manual ? ' <span class="tag soft">' + esc(t('se_manual_chip')) + '</span>' : '') + '</span><b>−' + fmtAmt(l.amount) + '</b></div>';
      }).join('');
    } else if (key === 'adjustments') {
      rows = (e.lines || []).map(function (a) {
        return '<div class="foot-line"><span>' + esc(a.label || '') + ' — ' + esc(a.reason || '') + '</span><b>' +
          (a.amount >= 0 ? '+' : '−') + fmtAmt(Math.abs(a.amount)) + '</b></div>';
      }).join('');
    } else if (key === 'net') {
      var v = e.values || {};
      rows = ['income', 'fees', 'expenses', 'cleaning', 'adjustments'].map(function (kk) {
        return '<div class="foot-line"><span>' + esc(t('se_' + (kk === 'fees' ? 'fees' : kk))) + '</span><b>' +
          (kk === 'income' || kk === 'adjustments' ? '' : '−') + fmtAmt(v[kk]) + '</b></div>';
      }).join('');
    } else if (key === 'cleaning') {
      rows = '<div class="foot-line"><span>' + esc(clTxt({ type: e.type, amount: e.amount })) +
        (e.prorated_days ? (' · ' + e.prorated_days + 'd') : '') + '</span><b>−' + fmtAmt(e.total) + '</b></div>';
    }
    return '<div class="se-explain"><div class="grp-hint" style="padding:0 0 6px">' + esc(rule || '') + '</div>' + rows + '</div>';
  }

  function renderStmt(d) {
    store.D.stmtEd = d;
    var s = d.statement || {};
    var inLines = (s.resv_lines || []).filter(function (l) { return l.income != null; });
    var nrLines = (s.resv_lines || []).filter(function (l) { return l.income == null; });
    var exLines = (s.contract_excluded_lines || []).concat(s.manual_excluded_lines || [])
      .concat((s.refunded_lines || []).map(function (l) {
        return Object.assign({}, l, { exclude_reason: 'cancelled_refunded' });
      }))
      .concat((s.unpaid_lines || []).map(function (l) {
        return Object.assign({}, l, { exclude_reason: 'unpaid_yet', reference_total: l.expected });
      }));
    function statBtn(key, label, val, neg) {
      var on = seUI.explain === key;
      return '<button class="stat tap' + (on ? ' on' : '') + '" data-act="se-why" data-key="' + key + '">' +
        '<span>' + esc(label) + ' · <i style="font-style:normal;color:var(--accent)">' + esc(t('se_why')) + '</i></span>' +
        '<b>' + (neg ? '−' : '') + fmtAmt(val) + '</b></button>';
    }
    var months = lastNMonths(13);
    var mm = d.month_meta || {};
    var running = mm.state === 'running';
    var pub = d.published;
    var foots = (s.footnotes || []).map(function (f) {
      return '<span class="tag">' + esc(store.lang === 'ar' ? f.text_ar : (f.text_en || f.text_ar)) + '</span>';
    }).join(' ');
    var auditRows = (d.audit || []).map(function (a) {
      return '<div class="wq-sub"><code>' + esc((a.at || '').slice(0, 16)) + '</code> · ' + esc(a.by || '') +
        ' · <b>' + esc(a.action || '') + '</b> · ' + esc(a.target || '') +
        (a.reason ? (' — ' + esc(a.reason)) : '') + '</div>';
    }).join('');
    $('#view').innerHTML =
      '<a class="btn ghost sm" href="#owners">' + esc(t('dg_back')) + '</a>' +
      '<section class="card grp"><header class="grp-h"><span class="grp-ico">🧾</span>' +
      '<h2>' + esc(t('se_title')) + ' — ' + esc(d.owner) + '</h2>' +
      '<span style="margin-inline-start:auto;display:flex;gap:6px;align-items:center;flex-wrap:wrap">' +
      '<select class="in" id="seMonth">' + monthOptions(months, d.month) + '</select>' +
      '<span class="tag' + (pub ? ' soft' : '') + '">' + (pub ? (esc(t('se_ver')) + ' ' + pub.version + ' · ' + esc((pub.at || '').slice(0, 10))) : esc(t('se_never_pub'))) + '</span>' +
      '<button class="btn ghost sm" data-act="se-diff">' + esc(t('se_recompute')) + '</button>' +
      '<button class="btn primary sm" data-act="se-publish">' + esc(t('se_pub')) + '</button>' +
      '</span></header>' +
      mmStrip(mm) +
      (d.computed_at ? '<div class="grp-hint" style="padding-top:0">' + esc(t('se_asof')) + ': <code>' + esc(String(d.computed_at).slice(0, 16)) + '</code></div>' : '') +
      '<div class="wsnav" style="position:static;border:none;padding:4px 16px">' +
      '<a class="ws' + (seUI.tab === 'stmt' ? ' on' : '') + '" data-act="se-tab" data-tab="stmt">' + esc(t('se_tab_stmt')) + '</a>' +
      '<a class="ws' + (seUI.tab === 'audit' ? ' on' : '') + '" data-act="se-tab" data-tab="audit">' + esc(t('se_tab_audit')) + ' (' + (d.audit || []).length + ')</a>' +
      '</div>' +
      (seUI.tab === 'audit'
        ? ('<div style="padding:4px 16px 16px">' + (auditRows || ('<div class="grp-hint" style="padding:0">' + esc(t('se_audit_empty')) + '</div>')) + '</div>')
        : (
          '<div id="seDiffBox"></div>' +
          '<div class="stat-row">' +
          statBtn('income', t('se_income') + (running ? ' (' + t('mm_sofar') + ')' : ''), s.total_income) +
          statBtn('fees', t('se_fees'), s.ouja_fee, true) +
          statBtn('expenses', t('se_expenses'), s.expenses, true) +
          statBtn('cleaning', t('se_cleaning'), (s.cleaning || {}).total, true) +
          statBtn('adjustments', t('se_adjust'), s.adjustments_total || 0) +
          statBtn('net', t('se_net') + (running ? ' (' + t('mm_sofar') + ')' : ''), s.owner_net) +
          '</div>' +
          (seUI.explain ? ('<div style="padding:0 16px 10px">' + seExplainHtml(seUI.explain, d.explain) + '</div>') : '') +
          (foots ? ('<div style="padding:0 16px 10px"><b style="font-size:12px">' + esc(t('se_footnotes')) + ':</b> ' + foots + '</div>') : '') +
          '<div class="grp-hint">' + esc(t('se_resv')) + ' · ' + inLines.length + '</div>' +
          '<div class="grp-list">' + inLines.map(function (l) { return seResvRow(l, 'in'); }).join('') + '</div>' +
          ((nrLines.length + exLines.length)
            ? ('<div class="grp-hint">' + esc(t('se_excluded')) + ' · ' + (nrLines.length + exLines.length) + '</div>' +
               '<div class="grp-list">' +
               nrLines.map(function (l) { return seResvRow(l, 'ex'); }).join('') +
               exLines.map(function (l) { return seResvRow(l, 'ex'); }).join('') + '</div>')
            : '') +
          '<div class="grp-hint">' + esc(t('se_expenses')) + ' · ' + (s.exp_lines || []).length + '</div>' +
          '<div class="grp-list">' + (s.exp_lines || []).map(seExpRow).join('') + '</div>' +
          '<div style="padding:10px 16px"><div class="om-grid">' +
          '<label>' + esc(t('se_amount')) + '<input type="number" step="0.01" class="in" id="seManAmt"></label>' +
          '<label>' + esc(t('se_date')) + '<input type="date" class="in" id="seManDate"></label>' +
          '<label>' + esc(t('se_desc')) + '<input class="in" id="seManDesc"></label>' +
          '</div><input class="in" id="seManReason" placeholder="' + esc(t('se_reason_req')) + '" style="margin-top:6px">' +
          '<button class="btn ghost sm" data-act="se-man-add" style="margin-top:6px">' + esc(t('se_exp_add')) + '</button></div>' +
          '<div style="padding:0 16px 16px;border-top:1px solid var(--line)"><div class="om-grid" style="margin-top:10px">' +
          '<label>' + esc(t('se_amount')) + ' (±)<input type="number" step="0.01" class="in" id="seAdjAmt"></label>' +
          '<label>' + esc(t('se_adj_label')) + '<input class="in" id="seAdjLabel"></label>' +
          '</div><input class="in" id="seAdjReason" placeholder="' + esc(t('se_reason_req')) + '" style="margin-top:6px">' +
          '<button class="btn ghost sm" data-act="se-adj-add" style="margin-top:6px">' + esc(t('se_adj_add')) + '</button>' +
          ((s.adjust_lines || []).length
            ? ('<div class="grp-list" style="margin-top:8px">' + (s.adjust_lines || []).map(function (a) {
                return '<div class="wq-row" data-aid="' + esc(a.id) + '"><div class="wq-main"><div class="wq-top"><b>' +
                  esc(a.label || '') + '</b><span class="tag">' + esc(a.reason || '') + '</span></div></div>' +
                  '<div class="wq-actions"><span class="c-amt"><b>' + (a.amount >= 0 ? '+' : '−') + fmtAmt(Math.abs(a.amount)) + '</b></span>' +
                  '<button class="btn danger-ghost xs" data-act="se-adj-del">' + esc(t('se_exp_del')) + '</button></div></div>';
              }).join('') + '</div>')
            : '') +
          '</div>'
        )) +
      '</section>';
    var sel = $('#seMonth');
    if (sel) sel.addEventListener('change', function () {
      location.hash = 'owners?stmt=' + encodeURIComponent(d.owner) + '&m=' + sel.value;
    });
  }

  function seRerender(payload) {
    var y = window.scrollY;
    renderStmt(payload);
    window.scrollTo(0, y);
  }

  function loadStmtEd(owner, m) {
    $('#view').innerHTML = skeleton(6);
    api('/erp/api/owners/statement?owner=' + encodeURIComponent(owner) + (m ? '&m=' + encodeURIComponent(m) : ''))
      .then(renderStmt)
      .catch(function (e) { $('#view').innerHTML = errorCard('retry_owners', srvMsg(e)); });
  }

  function seEdit(body, btn) {
    var d = store.D.stmtEd || {};
    body.owner = d.owner;
    body.m = d.month;
    if (btn) btn.disabled = true;
    return api('/erp/api/owners/statement/edit', { method: 'POST', body: body })
      .then(function (r) { toast(t('se_saved')); seRerender(r); })
      .catch(function (e) { if (btn) btn.disabled = false; toast(srvMsg(e) || t('act_failed'), 'err'); });
  }

  function ownerLinkAct(owner, action) {
    return api('/erp/api/owners/link', { method: 'POST', body: { owner: owner, action: action } })
      .then(function () { return api('/erp/api/owners'); })
      .then(function (d) {
        store.D.owners = d;
        var fresh = null;
        (d.rows || []).forEach(function (r) { if (r.owner === owner) fresh = r; });
        var rowEl = document.getElementById('ow_' + owner);
        if (rowEl && fresh) rowEl.outerHTML = ownerRowHtml(fresh);
        toast(t('o_done'));
      });
  }

  /* ================= الإعدادات Setup ================= */
  function ruleRowHtml(r, isAdmin) {
    var m = r.matcher || {};
    var s = r.set || {};
    var matcher = (m.desc_contains ? '«' + esc(m.desc_contains) + '»' : '') +
      (m.direction && m.direction !== 'any' ? ' · ' + esc(m.direction === 'out' ? t('rule_dir_out') : t('rule_dir_in')) : '');
    return '<tr class="rl-row' + (r.enabled ? '' : ' off') + '" data-id="' + esc(r.id) + '">' +
      '<td>' + matcher + '</td>' +
      '<td><b>' + esc(s.account_name || '') + '</b>' + (s.unit ? ' <span class="tag">' + esc(s.unit) + '</span>' : '') + '</td>' +
      '<td class="c-amt"><code>' + (r.hits || 0) + '</code></td>' +
      '<td class="c-amt"><code>' + (r.strength || 0) + '</code></td>' +
      '<td><button class="btn ghost xs" data-act="st-rule-toggle" data-id="' + esc(r.id) + '" data-en="' + (r.enabled ? '0' : '1') + '">' +
        (r.enabled ? esc(t('rl_on')) + ' ✓' : esc(t('rl_off'))) + '</button>' +
        (isAdmin ? ' <button class="btn danger-ghost xs" data-act="st-rule-del" data-id="' + esc(r.id) + '">' + esc(t('rl_delete')) + '</button>' : '') +
      '</td></tr>';
  }

  function renderSetup(d) {
    var rulesRows = (d.rules || []).map(function (r) { return ruleRowHtml(r, d.is_admin); }).join('');
    var html =
      '<section class="card grp">' +
        '<header class="grp-h"><span class="grp-ico">⚙️</span><h2>' + esc(t('setup_rules')) + '</h2>' +
        '<span class="cnt">' + (d.rules || []).length + '</span></header>' +
        '<div class="grp-hint">' + esc(t('setup_rules_hint')) + '</div>' +
        ((d.rules || []).length
          ? '<div class="table-card" style="border:none;box-shadow:none"><table class="btable"><thead><tr>' +
            '<th>' + esc(t('rl_matcher')) + '</th><th>' + esc(t('rl_target')) + '</th><th>' + esc(t('rl_hits')) + '</th>' +
            '<th>' + esc(t('rl_strength')) + '</th><th></th></tr></thead><tbody>' + rulesRows + '</tbody></table></div>'
          : '<div class="grp-hint" style="padding-bottom:16px">' + esc(t('rl_empty')) + '</div>') +
        '<div class="grp-cta"><button class="btn ghost sm" data-act="st-precision">' + esc(t('precision_btn')) + '</button>' +
        ' <span class="grp-hint" style="padding:0">' + esc(t('precision_hint')) + '</span></div>' +
        '<div id="precisionOut"></div>' +
      '</section>' +
      '<section class="card grp" id="setupContracts">' +
        '<header class="grp-h"><span class="grp-ico">📄</span><h2>' + esc(t('setup_contracts')) + '</h2>' +
        '<span class="cnt" id="ctUnlinked">…</span></header>' +
        '<div class="grp-hint">' + esc(t('setup_contracts_hint')) + '</div>' +
        '<div class="grp-list" id="ctList">' + skeleton(3).replace('card sk-card', 'sk-inline') + '</div>' +
      '</section>';
    $('#view').innerHTML = html;
    loadSetupContracts();
    restoreScroll('setup');
  }

  function contractRowHtml(c, ccOpts) {
    if (c.cc_id) {
      return '<div class="wq-row info" data-key="' + esc(c.key) + '"><div class="wq-main"><div class="wq-top"><b>' + esc(c.name) + '</b>' +
        '<span class="tag soft">' + esc(c.cc_name || c.cc_id) + '</span></div>' +
        (c.owner ? '<div class="wq-sub">' + esc(c.owner) + '</div>' : '') + '</div></div>';
    }
    return '<div class="wq-row" data-key="' + esc(c.key) + '"><div class="wq-main"><div class="wq-top"><b>' + esc(c.name) + '</b>' +
      '<span class="tag bad">' + esc(t('f_needs')) + '</span></div>' +
      (c.owner ? '<div class="wq-sub">' + esc(c.owner) + '</div>' : '') + '</div>' +
      '<div class="wq-actions"><select class="in ct-cc">' + ccOpts + '</select>' +
      '<button class="btn primary sm" data-act="st-link-cc" data-key="' + esc(c.key) + '">' + esc(t('link_cc')) + '</button></div></div>';
  }

  function loadSetupContracts() {
    Promise.all([api('/erp/api/contracts'), ensureChart()]).then(function (rs) {
      var d = rs[0], chart = rs[1];
      var box = $('#ctList');
      if (!box) return;
      $('#ctUnlinked').textContent = d.unlinked ? t('unlinked_n').replace('{n}', d.unlinked) : '0';
      var ccOpts = '<option value="">' + esc(t('pick_cc')) + '</option>' + chart.cost_centers.map(function (c) {
        return '<option value="' + esc(c.id) + '">' + esc(c.name) + '</option>';
      }).join('');
      if (!d.rows.length) { box.innerHTML = '<div class="grp-hint" style="padding-bottom:14px">—</div>'; return; }
      if (!d.unlinked) {
        box.innerHTML = '<div class="wq-row info"><div class="wq-main"><div class="wq-top">' + esc(t('all_linked')) + '</div></div></div>' +
          d.rows.slice(0, 8).map(function (c) { return contractRowHtml(c, ccOpts); }).join('');
        return;
      }
      box.innerHTML = d.rows.map(function (c) { return contractRowHtml(c, ccOpts); }).join('');
    }).catch(function (e) {
      var box = $('#ctList');
      if (box) box.innerHTML = errorCard('retry_setup', srvMsg(e));
    });
  }

  function loadSetup() {
    $('#view').innerHTML = skeleton(5);
    api('/erp/api/rules').then(function (d) {
      store.D.setup = d;
      renderSetup(d);
    }).catch(function (e) {
      $('#view').innerHTML = errorCard('retry_setup', srvMsg(e));
    });
  }

  /* ---------------- views registry ---------------- */
  var VIEWS = {
    today: { show: function () { loadToday(); } },
    setup: { show: function () { loadSetup(); } },
    match: {
      show: function (params) {
        matchP.engine = params.get('engine') || 'all';
        matchP.p = Math.max(1, Number(params.get('p') || 1));
        loadMatch();
      }
    },
    exp: {
      show: function (params) {
        expP.tab = params.get('tab') || 'pending';
        expP.q = params.get('q') || '';
        expP.o = Math.max(0, Number(params.get('o') || 0));
        loadExp();
      }
    },
    custody: { show: function () { loadCustody(); } },
    owners: {
      show: function (params) {
        var diag = params && params.get('diag');
        var manage = params && params.get('manage');
        var stmt = params && params.get('stmt');
        if (diag) loadDiag(diag, params.get('m') || '');
        else if (manage) loadManage(manage);
        else if (stmt) { seUI.tab = 'stmt'; seUI.explain = ''; loadStmtEd(stmt, params.get('m') || ''); }
        else loadOwners();
      }
    },
    stmts: { show: function (params) { stP.m = params.get('m') || nowMonth(); loadStmts(); } },
    close: { show: function (params) { clP.m = params.get('m') || nowMonth(); loadClose(); } },
    budget: { show: function (params) { bgP.m = params.get('m') || nowMonth(); loadBudget(); } },
    bank: {
      show: function (params) {
        bankP.f = params.get('f') || 'all';
        bankP.q = params.get('q') || '';
        bankP.from = params.get('from') || '';
        bankP.to = params.get('to') || '';
        bankP.p = Math.max(1, Number(params.get('p') || 1));
        store.sel = {};
        $('#view').innerHTML = bankLayout();
        renderBankChips((store.D.bank || {}).counts);
        loadBankData();
        ensureChart().catch(function () {});   // warm the chart cache for the classifier
      }
    }
  };

  /* ============ global sidebar — the SHARED nav (slice 0a v2.1) ============
     Structure + labels come from GET /api/nav (bot.py's NAV_DEF — the same
     definition the dashboard renders). Icons are a local copy (cosmetic). */
  var GICN = (function () {
    var S = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">';
    return {
      home: S + '<path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M9 21v-7h6v7"/></svg>',
      inbox: S + '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>',
      calendar: S + '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/></svg>',
      clean_center: S + '<circle cx="12" cy="12" r="9"/><path d="m14.8 9.2-2.2 5.6-5.6 2.2 2.2-5.6z"/></svg>',
      pricing: S + '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
      plab: S + '<path d="M9 3h6M10 3v6.5L5.2 18A2 2 0 0 0 7 21h10a2 2 0 0 0 1.8-3L14 9.5V3"/></svg>',
      strat: S + '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>',
      clean: S + '<path d="m12 3 1.6 4.8L18 9l-4.4 1.2L12 15l-1.6-4.8L6 9l4.4-1.2z"/><path d="M18 15.5l.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8z"/></svg>',
      cleanteams: S + '<circle cx="9" cy="8" r="3"/><path d="M15 5.2a3 3 0 0 1 0 5.6M3 20a6 6 0 0 1 12 0M16 14a6 6 0 0 1 5 6"/></svg>',
      listings: S + '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 8h.01M15 8h.01M9 12h.01M15 12h.01M9 16h6"/></svg>',
      tickets: S + '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.3 2.3-2-2z"/></svg>',
      reviews: S + '<path d="m12 3 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.8 6.8 19.2l1-5.8L3.5 9.2l5.9-.9z"/></svg>',
      users: S + '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
      quote: S + '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>',
      weekly: S + '<path d="M3 3v18h18"/><path d="M7 15v-3M12 15V8M17 15v-6"/></svg>',
      design: S + '<path d="M5 11V8a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v3"/><path d="M4 11a2 2 0 0 1 2 2v2h12v-2a2 2 0 0 1 2-2 2 2 0 0 1 2 2v5H2v-5a2 2 0 0 1 2-2z"/></svg>',
      pmo: S + '<path d="M3 21h18M6 21V11l6-3 6 3v10M10 21v-5h4v5"/></svg>',
      expenses: S + '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>',
      finance: S + '<path d="M5 3v18l2-1 2 1 2-1 2 1 2-1 2 1V3l-2 1-2-1-2 1-2-1-2 1z"/><path d="M9 8h6M9 12h6"/></svg>',
      fb: S + '<rect x="5" y="6" width="14" height="12" rx="3"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M2 9h3M2 14h3M19 9h3M19 14h3"/></svg>',
      guests: S + '<circle cx="12" cy="8" r="4"/><path d="M5 21a7 7 0 0 1 14 0"/></svg>',
      gw: S + '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10.5 18h3"/></svg>',
      quality: S + '<path d="M12 3l7.5 3v6c0 4.5-3 7.5-7.5 9-4.5-1.5-7.5-4.5-7.5-9V6z"/><path d="m9 12 2 2 4-4"/></svg>',
      rev: S + '<path d="M3 17l6-6 4 4 7-8"/><path d="M17 7h4v4"/></svg>',
      learn: S + '<path d="M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z"/><path d="M4 19a2 2 0 0 0 2 2h12v-4"/></svg>',
      log: S + '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>'
    };
  })();

  function gnavLabel(tk) {
    var nav = store.gnav && store.gnav.nav;
    if (!nav) return tk;
    var L = (nav.labels || {})[store.lang] || (nav.labels || {}).ar || {};
    return L[tk] || ((nav.labels || {}).ar || {})[tk] || tk;
  }
  function _gCollapsed() {
    try { return JSON.parse(localStorage.getItem('erp:navCollapsed') || '{}') || {}; } catch (e) { return {}; }
  }
  function dashUrl(id) {
    return '/dashboard' + (store.token ? '?token=' + encodeURIComponent(store.token) : '') + '#' + id;
  }

  function renderGSide() {
    var box = $('#gsideNav');
    if (!box || !store.gnav || !store.gnav.nav) return;
    var nav = store.gnav.nav;
    var role = store.gnav.role || 'admin';
    var erpTargets = nav.erp_targets || {};
    var byId = {};
    (nav.items || []).forEach(function (n) { byId[n.id] = n; });
    var collapsed = _gCollapsed();
    function itemHtml(n) {
      var on = n.id === 'erp';
      var target = erpTargets[n.id];
      var href = target ? ('#' + target) : dashUrl(n.id);
      var h = '<a class="item' + (on ? ' on' : '') + '" href="' + esc(href) + '"' +
        (on ? ' aria-current="page"' : '') + '><span class="ic">' + (GICN[n.ic] || '') + '</span>' +
        '<span>' + esc(gnavLabel(n.tk)) + '</span></a>';
      if (on) {
        h += '<div class="ws-sub">' + WORKSPACES.map(function (w) {
          return '<a href="#' + w.id + '" class="' + (store.view === w.id ? 'on' : '') + '">' +
            esc(t('ws_' + w.id)) + '</a>';
        }).join('') + '</div>';
      }
      return h;
    }
    box.innerHTML = (nav.cats || []).map(function (cat) {
      var items = (cat.ids || []).map(function (id) { return byId[id]; })
        .filter(function (n) { return n && !(n.adminOnly && role !== 'admin'); });
      if (!items.length) return '';
      var activeHere = items.some(function (n) { return n.id === 'erp'; });
      var isCollapsed = !!collapsed[cat.tk] && !activeHere;
      return '<div class="nav-group' + (isCollapsed ? ' collapsed' : '') + '">' +
        '<button class="nav-group-h" type="button" data-cat="' + esc(cat.tk) + '" aria-expanded="' + (isCollapsed ? 'false' : 'true') + '">' +
        '<span class="nav-cat-label">' + esc(gnavLabel(cat.tk)) + '</span>' +
        '<span class="nav-caret" aria-hidden="true">⌄</span></button>' +
        '<div class="nav-group-items">' + items.map(itemHtml).join('') + '</div></div>';
    }).join('');
  }

  function loadGNav() {
    api('/api/nav').then(function (d) {
      if (d && d.ok) { store.gnav = d; renderGSide(); }
    }).catch(function () { /* nav stays absent; the wsnav strip still navigates */ });
  }

  /* sidebar interactions: category collapse + burger (mobile overlay / desktop hide) */
  document.addEventListener('click', function (ev) {
    var h = ev.target.closest ? ev.target.closest('.gside .nav-group-h') : null;
    if (h) {
      var c = _gCollapsed();
      c[h.getAttribute('data-cat')] = !c[h.getAttribute('data-cat')];
      try { localStorage.setItem('erp:navCollapsed', JSON.stringify(c)); } catch (e) {}
      renderGSide();
    }
  });
  function gsideMobileOpen(open) {
    document.body.classList.toggle('gside-open', open);
    var bg = $('#gsideBg');
    if (bg) bg.hidden = !open;
  }
  (function () {
    var btn = $('#burger');
    if (btn) btn.addEventListener('click', function () {
      if (window.matchMedia('(min-width:1024px)').matches) {
        var off = document.body.classList.toggle('gside-off');
        try { localStorage.setItem('erp_gside_off', off ? '1' : '0'); } catch (e) {}
      } else {
        gsideMobileOpen(!document.body.classList.contains('gside-open'));
      }
    });
    var x = $('#gsideClose');
    if (x) x.addEventListener('click', function () { gsideMobileOpen(false); });
    var bg = $('#gsideBg');
    if (bg) bg.addEventListener('click', function () { gsideMobileOpen(false); });
    try { if (localStorage.getItem('erp_gside_off') === '1') document.body.classList.add('gside-off'); } catch (e) {}
    // navigating inside the SPA from the overlay should close it
    window.addEventListener('hashchange', function () { gsideMobileOpen(false); });
  })();

  /* ---------------- language ---------------- */
  function applyLang() {
    document.documentElement.lang = store.lang;
    document.documentElement.dir = t('dir');
    $('#appTitle').textContent = t('app');
    $('#langBtn').textContent = store.lang === 'ar' ? 'EN' : 'ع';
    $('#healthLbl').textContent = t('health');
    renderNav();
    renderGSide();
    if (store.view === 'today' && store.D.today) renderToday(store.D.today);
    else if (store.view === 'bank') { var ph = parseHash(); VIEWS.bank.show(ph.params); }
    else if (store.view === 'setup') loadSetup();
    else if (store.view === 'match' && store.D.match) renderMatch(store.D.match);
    else if (store.view === 'exp' && store.D.exp) renderExp(store.D.exp);
    else if (store.view === 'custody' && store.D.custody) renderCustody(store.D.custody);
    else if (store.view === 'owners' && store.D.owners) renderOwners(store.D.owners);
    else if (store.view === 'stmts' && store.D.stmts) renderStmts(store.D.stmts);
    else if (store.view === 'close' && store.D.close) renderClose(store.D.close);
    else if (store.view === 'budget' && store.D.budget) renderBudget(store.D.budget);
  }
  $('#langBtn').addEventListener('click', function () {
    store.lang = store.lang === 'ar' ? 'en' : 'ar';
    try { localStorage.setItem('erp_lang', store.lang); } catch (e) {}
    applyLang();
    document.title = t('ws_' + store.view) + ' · ' + t('app');
  });

  /* ---------------- boot ---------------- */
  window.addEventListener('hashchange', route);
  window.addEventListener('scroll', (function () {
    var tmr = null;
    return function () { clearTimeout(tmr); tmr = setTimeout(saveScroll, 120); };
  })(), { passive: true });
  applyLang();
  loadGNav();
  route();
})();
