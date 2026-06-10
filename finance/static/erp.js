/* Ouja Finance ERP v2 — front-end.
   Slice 1: shell (flat nav, hash routing, AR/EN, build stamp) + اليوم work queue.
   Architecture rules R1–R8 from the build prompt:
   - mutations patch DOM nodes, never re-render the app (R1/R1b)
   - the URL hash carries full state (R2)
   - a button either works or does not exist (R3)
   - skeleton → data → honest empty → error-with-retry (R4)
   - optimistic-feel with server-confirmed removal + rollback on error (R6)
   - Arabic-first + EN toggle, RTL, SAR, never fake data (R8) */
(function () {
  'use strict';

  /* ---------------- tiny helpers ---------------- */
  var $ = function (s, el) { return (el || document).querySelector(s); };
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
    D: {}                      // per-view data cache
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
      g_unclassified: 'حركات بنك بدون تصنيف', g_unclassified_hint: 'التصنيف الكامل يفتح في «البنك» (شريحة ٢)',
      g_suggested: 'مطابقات مقترحة من دافترة', g_suggested_hint: 'القرار النهائي يفتح في «المطابقة» (شريحة ٤)',
      g_contracts: 'عقود بدون مركز تكلفة', g_contracts_hint: 'الربط يفتح مع إدارة العقود (شريحة ٣)',
      g_imports: 'استيرادات متعثرة أو قديمة', g_imports_hint: '',
      more: 'غيرها', items_word: 'عنصر',
      approve: 'اعتماد', reject: 'رفض', clarify: 'استيضاح',
      reject_reason: 'سبب الرفض (إلزامي)…', clarify_reason: 'وش تبي يوضّحون؟ (اختياري)…',
      confirm_reject: 'تأكيد الرفض', confirm_clarify: 'إرسال الاستيضاح', cancel: 'إلغاء',
      waiting_faisal: 'بانتظار فيصل',
      approved_ok: 'تم الاعتماد ✓', rejected_ok: 'تم الرفض', clarified_ok: 'أُرسل طلب الاستيضاح',
      act_failed: 'ما صار شي — حاول مرة ثانية',
      empty_today: 'قائمة الشغل صافية — ما عليك شي اليوم ✓',
      empty_today_sub: 'كل الموافقات والتصنيفات والمطابقات خالصة.',
      load_err: 'تعذّر تحميل البيانات', retry: 'حاول مرة ثانية',
      conf: 'تطابق', journal: 'قيد', out: 'طالع', inn: 'داخل',
      sar: 'ر.س', stale: 'قديم', failed: 'فشل', src_bank: 'البنك', src_daftra: 'دافترة', src_contracts: 'العقود'
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
      g_unclassified: 'Unclassified bank transactions', g_unclassified_hint: 'Full classification opens in Bank (slice 2)',
      g_suggested: 'Suggested Daftra matches', g_suggested_hint: 'Final decision opens in Matching (slice 4)',
      g_contracts: 'Contracts missing cost center', g_contracts_hint: 'Linking opens with contract management (slice 3)',
      g_imports: 'Stale or failed imports', g_imports_hint: '',
      more: 'more', items_word: 'items',
      approve: 'Approve', reject: 'Reject', clarify: 'Clarify',
      reject_reason: 'Rejection reason (required)…', clarify_reason: 'What needs clarifying? (optional)…',
      confirm_reject: 'Confirm rejection', confirm_clarify: 'Send clarification', cancel: 'Cancel',
      waiting_faisal: 'Waiting for Faisal',
      approved_ok: 'Approved ✓', rejected_ok: 'Rejected', clarified_ok: 'Clarification requested',
      act_failed: 'Nothing changed — try again',
      empty_today: 'Work queue is clear ✓',
      empty_today_sub: 'Approvals, classification and matching are all done.',
      load_err: 'Could not load the data', retry: 'Try again',
      conf: 'match', journal: 'journal', out: 'out', inn: 'in',
      sar: 'SAR', stale: 'stale', failed: 'failed', src_bank: 'Bank', src_daftra: 'Daftra', src_contracts: 'Contracts'
    }
  };
  function t(k) { var v = T[store.lang][k]; return v === undefined ? (T.ar[k] || k) : v; }

  /* ---------------- API ---------------- */
  function api(path, opts) {
    var o = opts || {};
    var headers = { 'X-Token': store.token };
    if (o.body) headers['Content-Type'] = 'application/json';
    return fetch(path, {
      method: o.method || 'GET',
      headers: headers,
      body: o.body ? JSON.stringify(o.body) : undefined
    }).then(function (r) {
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

  /* ---------------- workspaces + router (R2) ---------------- */
  var WORKSPACES = [
    { id: 'today', built: true },
    { id: 'bank', slice: 2 },
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
  function errorCard(retryFnName, detail) {
    return '<div class="card state-card"><div class="state-ico">⚠️</div>' +
      '<div class="state-h">' + esc(t('load_err')) + '</div>' +
      (detail ? '<div class="state-sub">' + esc(detail) + '</div>' : '') +
      '<button class="btn primary" data-act="' + retryFnName + '">' + esc(t('retry')) + '</button></div>';
  }

  /* ---------------- اليوم Today ---------------- */
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
    return '<div class="wq-row" id="wq_' + esc(it.id) + '" data-amount="' + esc(it.amount) + '">' +
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

  function rowInfo(main, sub, side) {
    return '<div class="wq-row info">' +
      '<div class="wq-main"><div class="wq-top">' + main + '</div>' +
      (sub ? '<div class="wq-sub">' + sub + '</div>' : '') + '</div>' +
      (side ? '<div class="wq-side">' + side + '</div>' : '') +
    '</div>';
  }

  function renderToday(d) {
    headerMeta(d);
    var total = 0;
    d.groups.forEach(function (g) { total += g.count; });
    var html = '';
    if (!total) {
      html = '<div class="card state-card"><div class="state-ico ok">✓</div>' +
        '<div class="state-h">' + esc(t('empty_today')) + '</div>' +
        '<div class="state-sub">' + esc(t('empty_today_sub')) + '</div></div>';
      $('#view').innerHTML = html;
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
            esc(it.desc) + ' · <code>' + esc(it.date || '') + '</code>', '');
        }).join('') + '</div>';
      } else if (g.key === 'suggested') {
        html += '<div class="grp-list">' + g.items.map(function (it) {
          return rowInfo(
            '<span class="amt">' + fmtAmt(it.amount) + ' <i>' + esc(t('sar')) + '</i></span>' +
              '<span class="tag soft">' + it.conf + '% ' + esc(t('conf')) + '</span>' +
              (it.journal_no ? '<span class="tag">' + esc(t('journal')) + ' #' + esc(it.journal_no) + '</span>' : ''),
            esc(store.lang === 'ar' ? (it.reason_ar || it.desc) : (it.reason_en || it.desc)) +
              ' · <code>' + esc(it.date || '') + '</code>', '');
        }).join('') + '</div>';
      } else if (g.key === 'contracts') {
        html += '<div class="grp-list">' + g.items.map(function (it) {
          return rowInfo('<b>' + esc(it.name) + '</b>', it.owner ? esc(it.owner) : '', '');
        }).join('') + '</div>';
      } else if (g.key === 'imports') {
        html += '<div class="grp-list">' + g.items.map(function (it) {
          var lbl = it.status === 'failed' ? t('failed') : t('stale');
          return rowInfo(
            '<b>' + esc(t('src_' + it.source) || it.source) + '</b><span class="tag ' +
              (it.status === 'failed' ? 'bad' : 'warnt') + '">' + esc(lbl) + '</span>',
            (it.file ? esc(it.file) + ' · ' : '') + '<code>' + esc(it.when || '') + '</code>' +
              (it.error ? ' — ' + esc(it.error) : ''), '');
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
      var detail = e && e.body && (e.body.detail || e.body.error);
      $('#view').innerHTML = errorCard('retry_today', detail);
    });
  }

  /* ---------------- approvals: inline decisions (R1b, R6) ---------------- */
  function setRowBusy(row, busy) {
    row.classList.toggle('busy', !!busy);
    row.querySelectorAll('button').forEach(function (b) { b.disabled = !!busy; });
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
        var b = e && e.body;
        var msg = b && (store.lang === 'ar' ? b.message_ar : b.message_en);
        toast(msg || t('act_failed'), 'err');
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

  /* ---------------- event delegation ---------------- */
  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act');
    var id = el.getAttribute('data-id');
    var row = el.closest('.wq-row');
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
  });
  document.addEventListener('click', function (ev) {
    var nb = ev.target.closest('.next-best');
    if (!nb) return;
    var target = document.getElementById(nb.getAttribute('data-target'));
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  /* ---------------- views registry ---------------- */
  var VIEWS = {
    today: { show: function () { loadToday(); } }
  };

  /* ---------------- language ---------------- */
  function applyLang() {
    document.documentElement.lang = store.lang;
    document.documentElement.dir = t('dir');
    $('#appTitle').textContent = t('app');
    $('#langBtn').textContent = store.lang === 'ar' ? 'EN' : 'ع';
    $('#healthLbl').textContent = t('health');
    renderNav();
    if (store.D.today && store.view === 'today') renderToday(store.D.today);
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
