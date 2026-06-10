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
      m_sum_mismatch: 'المجموع لازم يساوي مبلغ الحركة'
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
      m_sum_mismatch: 'Selected lines must sum to the txn amount'
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
    { id: 'exp', slice: 5 },
    { id: 'custody', slice: 5 },
    { id: 'owners', slice: 6 },
    { id: 'close', slice: 7 },
    { id: 'stmts', slice: 7 },
    { id: 'budget', slice: 7 },
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
    approvals: { icon: '🔏' }, unclassified: { icon: '🏦' }, suggested: { icon: '🔗' },
    contracts: { icon: '📄' }, imports: { icon: '⬇️' }
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
  });

  document.addEventListener('input', (function () {
    var tmr = null;
    return function (ev) {
      if (ev.target.id !== 'bkSearch') return;
      clearTimeout(tmr);
      var v = ev.target.value;
      tmr = setTimeout(function () { bankP.q = v.trim(); bankP.p = 1; pushBankHash(); }, 350);
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

  /* ---------------- language ---------------- */
  function applyLang() {
    document.documentElement.lang = store.lang;
    document.documentElement.dir = t('dir');
    $('#appTitle').textContent = t('app');
    $('#langBtn').textContent = store.lang === 'ar' ? 'EN' : 'ع';
    $('#healthLbl').textContent = t('health');
    renderNav();
    if (store.view === 'today' && store.D.today) renderToday(store.D.today);
    else if (store.view === 'bank') { var ph = parseHash(); VIEWS.bank.show(ph.params); }
    else if (store.view === 'setup') loadSetup();
    else if (store.view === 'match' && store.D.match) renderMatch(store.D.match);
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
  route();
})();
