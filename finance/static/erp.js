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
      g_contracts: 'عقود بدون مركز تكلفة', g_contracts_hint: 'الربط يفتح مع إدارة العقود (شريحة ٣)',
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
      sugg: 'اقتراح'
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
      g_contracts: 'Contracts missing cost center', g_contracts_hint: 'Linking opens with contract management (slice 3)',
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
      sugg: 'suggestion'
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
    { id: 'match', slice: 4 },
    { id: 'exp', slice: 5 },
    { id: 'custody', slice: 5 },
    { id: 'owners', slice: 6 },
    { id: 'close', slice: 7 },
    { id: 'stmts', slice: 7 },
    { id: 'budget', slice: 7 },
    { id: 'setup', slice: 3 }
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
        }).join('') + '</div>';
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
      el.disabled = true;
      postClassify(ids, {
        account_id: accSel,
        cost_center_id: $('#clsCc').value,
        counterparty: $('#clsCp').value.trim(),
        unit: $('#clsUnit').value.trim()
      }).then(closeCls).catch(function () { el.disabled = false; });
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

  /* ---------------- views registry ---------------- */
  var VIEWS = {
    today: { show: function () { loadToday(); } },
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
