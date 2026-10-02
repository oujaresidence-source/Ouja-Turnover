/* «رفع التقييم» — the Review Push tab of the Ouja dashboard.
 *
 * Served by reviewask/routes.py at /reviewask/static/reviewask_tab.js and loaded on first visit
 * by the tiny loadRvpush() stub inside DASHBOARD_HTML. A REAL file on purpose: DASHBOARD_HTML is
 * a Python string that eats backslashes (CLAUDE.md trap 1); this file is not.
 *
 * Five views: الشقق (+ owner pin) · التكتات الحية · الأداء · الأرشيف (kept forever, with the saved
 * room transcript) · نص الرسالة (the owner's editor, live preview).
 * Uses the dashboard's globals only: api, post, esc, labelText, toast, putHtml, emptyState,
 * errorState, openDrawer, setDrawerBody, setDrawerFoot, closeDrawer.
 * Every action is event-delegated through data-rv="…". Must pass `node --check`.
 * No money figure is ever shown here.
 */
(function () {
  'use strict';

  var S = { view: 'apts', sum: null, apts: null, live: null, perf: null, perfDays: 7,
            arch: null, tpl: null, draft: null, pvTimer: null, loading: false };

  var VIEWS = [
    ['apts', 'الشقق', 'Apartments'],
    ['live', 'التكتات الحية', 'Live tickets'],
    ['perf', 'الأداء', 'Performance'],
    ['arch', 'الأرشيف', 'Archive'],
    ['tpl', 'نص الرسالة', 'Message text']
  ];
  var PH = ['الاسم', 'الموظف', 'الشقة', 'رابط_التقييم'];

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
  function num(x) { x = Number(x); return isFinite(x) ? x : 0; }
  function stars(v) { return (v === null || v === undefined || v === '') ? '—' : '<bdi>' + (Math.round(num(v) * 100) / 100) + '★</bdi>'; }
  function day(s) { return s ? String(s).slice(0, 10) : '—'; }
  function hm(s) { return s ? String(s).slice(0, 16).replace('T', ' ') : '—'; }

  /* ---------- styles: scoped, token-only (the locked :root palette) ---------- */
  function css() {
    if (document.getElementById('rvCss')) return;
    var s = document.createElement('style');
    s.id = 'rvCss';
    s.textContent = [
      '.rv-seg{display:inline-flex;flex-wrap:wrap;gap:4px;padding:4px;border:1px solid var(--line);border-radius:10px;background:var(--surface);margin-bottom:14px}',
      '.rv-seg button{border:0;background:none;font:inherit;font-size:12.5px;font-weight:600;color:var(--text-2);padding:7px 12px;border-radius:7px;cursor:pointer;min-height:34px;transition:background .15s cubic-bezier(0.23,1,0.32,1),color .15s}',
      '.rv-seg button:active{transform:scale(.97)}',
      '.rv-seg button.on{background:var(--gold-tint);color:var(--gold)}',
      '.rv-banner{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;padding:11px 14px;border-radius:var(--r-md);border:1px solid var(--line);background:var(--surface);margin-bottom:14px;font-size:12.5px;color:var(--text-2)}',
      '.rv-banner.off{background:var(--yellow-soft);border-color:transparent}',
      '.rv-banner b{color:var(--text)}',
      '.rv-st{display:inline-flex;align-items:center;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
      '.rv-st.in{background:var(--red-soft);color:var(--red)}',
      '.rv-st.out{background:var(--green-soft);color:var(--green)}',
      '.rv-st.pin{box-shadow:inset 0 0 0 1px var(--gold);background:var(--gold-tint);color:var(--gold)}',
      '.rv-sub{display:block;font-size:11px;color:var(--mut);margin-top:2px}',
      '.rv-num{font-family:var(--font-mono);white-space:nowrap}',
      'table.data tr.rv-r{cursor:pointer}',
      '.rv-ed{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}',
      '@media (max-width:980px){.rv-ed{grid-template-columns:1fr}}',
      '.rv-ed label{display:block;font-size:12px;font-weight:700;color:var(--text);margin:12px 0 6px}',
      '.rv-ed textarea{width:100%;min-height:150px;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);font:inherit;font-size:13px;line-height:1.7;resize:vertical}',
      '.rv-ed textarea:focus{outline:none;border-color:var(--gold);box-shadow:0 0 0 2px var(--gold-tint)}',
      '.rv-ph{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}',
      '.rv-ph button{border:1px dashed var(--line-strong);background:var(--surface);color:var(--text-2);font:inherit;font-size:11.5px;padding:3px 8px;border-radius:6px;cursor:pointer}',
      '.rv-ph button:active{transform:scale(.97)}',
      '.rv-pv{white-space:pre-wrap;background:var(--surface-2);border-radius:10px;padding:12px 14px;font-size:13px;line-height:1.75;color:var(--text);min-height:60px}',
      '.rv-meta{font-size:11.5px;color:var(--mut);margin-top:6px}',
      '.rv-warn{color:var(--red);font-weight:700}',
      '.rv-ev{font-size:12.5px;color:var(--text-2);padding:6px 0;border-bottom:1px solid var(--line)}',
      '.rv-ev b{color:var(--text)}',
      '.rv-msg{font-size:12.5px;padding:8px 0;border-bottom:1px solid var(--line);white-space:pre-wrap;color:var(--text-2)}',
      '.rv-msg .a{font-weight:700;color:var(--text)}',
      '@media (prefers-reduced-motion:reduce){.rv-seg button{transition:none}}'
    ].join('');
    document.head.appendChild(s);
  }

  /* ---------- shell ---------- */
  function tabs() {
    putHtml('rvTabs', '<div class="rv-seg" role="tablist">' + VIEWS.map(function (v) {
      return '<button type="button" role="tab" data-rv="view" data-v="' + v[0] + '" class="' + (S.view === v[0] ? 'on' : '') + '" aria-selected="' + (S.view === v[0]) + '">' + esc(T(v[1], v[2])) + '</button>';
    }).join('') + '</div>');
  }

  function banner() {
    var s = S.sum;
    if (!s) return '';
    if (!s.live) {
      return '<div class="rv-banner off"><b>' + esc(T('النظام موقف', 'Switched off')) + '</b><span>' +
        esc(T('ما ينفتح شي ولا ينرسل شي لين تكتب /reviews-start في ديسكورد. جرّب /reviews-tomorrow يعرض لك وش بينفتح.',
              'Nothing opens or posts until /reviews-start in Discord. /reviews-tomorrow shows what would open.')) + '</span></div>';
    }
    return '<div class="rv-banner"><b>' + esc(T('شغال', 'Live')) + '</b><span>' +
      esc(T('تكتات مفتوحة: ', 'Open tickets: ')) + num(s.open) + ' · ' + esc(T('شقق تحت ', 'Apartments at or under ')) + esc(s.threshold) + ': ' + num(s.weak) + '</span></div>';
  }

  async function load(force) {
    css();
    if (!document.getElementById('rvCss')) return;
    tabs();
    if (S.loading) return;
    S.loading = true;
    try {
      if (force || !S.sum) S.sum = await api('/api/reviewask/summary').catch(function () { return null; });
      await show(force);
    } finally {
      S.loading = false;
    }
  }

  async function show(force) {
    tabs();
    putHtml('rvBody', banner() + '<div class="empty sk">…</div>');
    try {
      if (S.view === 'apts') { if (force || !S.apts) S.apts = await api('/api/reviewask/apartments'); renderApts(); }
      else if (S.view === 'live') { if (force || !S.live) S.live = await api('/api/reviewask/live'); renderLive(); }
      else if (S.view === 'perf') { if (force || !S.perf) S.perf = await api('/api/reviewask/performance?days=' + S.perfDays); renderPerf(); }
      else if (S.view === 'arch') { if (force || !S.arch) S.arch = await api('/api/reviewask/archive'); renderArch(); }
      else { if (force || !S.tpl) { S.tpl = await api('/api/reviewask/templates'); S.draft = null; } renderTpl(); }
    } catch (e) {
      putHtml('rvBody', banner() + errorState('loadRvpush(1)'));
    }
  }

  /* ---------- 1) apartments ---------- */
  function renderApts() {
    var d = S.apts || {};
    if (d.ok === false) { putHtml('rvBody', banner() + errorState('loadRvpush(1)', d.error_ar)); return; }
    var rows = arr(d.rows);
    if (!rows.length) { putHtml('rvBody', banner() + emptyState(T('ما فيه شقق بعد', 'No apartments yet'))); return; }
    var weak = rows.filter(function (r) { return r.in_program; }).length;
    var h = banner() + '<div class="card"><div class="rv-meta" style="margin:0 0 10px">' +
      esc(T('بالبرنامج: ' + weak + ' من ' + rows.length + ' — الحسبة من تقييمات الضيوف في Airbnb فقط (التقييم الصفر ما ينحسب). «ناقص» = كم تقييم ٥ نجوم عشان تتعدى ' + d.threshold + '.',
            'In the program: ' + weak + ' of ' + rows.length + ' — Airbnb guest reviews only (zero scores excluded). "Needed" = 5★ reviews to pass ' + d.threshold + '.')) +
      '</div><div style="overflow-x:auto"><table class="data"><thead><tr><th>' + esc(T('الشقة', 'Apartment')) + '</th><th>' + esc(T('التقييم', 'Rating')) +
      '</th><th>' + esc(T('عدد التقييمات', 'Reviews')) + '</th><th>' + esc(T('ناقص', 'Needed')) + '</th><th>' + esc(T('تكتات مفتوحة', 'Open tickets')) +
      '</th><th>' + esc(T('الحالة', 'Status')) + '</th>' + (d.is_admin ? '<th></th>' : '') + '</tr></thead><tbody>';
    rows.forEach(function (r) {
      var st = r.pinned ? ('<span class="rv-st pin">' + esc(r.pinned === 'in' ? T('مثبتة داخل', 'Pinned in') : T('مثبتة برا', 'Pinned out')) + '</span>' +
               '<span class="rv-sub">' + esc(T('حسبتنا: ', 'Computed: ') + (r.computed_in ? T('داخل', 'in') : T('برا', 'out')) + (r.pin_reason ? ' · ' + r.pin_reason : '')) + '</span>')
             : (r.in_program ? '<span class="rv-st in">' + esc(T('بالبرنامج', 'In program')) + '</span>' : '<span class="rv-st out">' + esc(T('فوق الخط', 'Above the line')) + '</span>');
      h += '<tr><td>' + esc(r.name) + '</td><td class="rv-num">' + (r.avg === null ? esc(T('بدون', 'none')) : stars(r.avg)) + '</td><td class="rv-num">' + num(r.n) +
        '</td><td class="rv-num">' + (r.needed ? num(r.needed) : '—') + '</td><td class="rv-num">' + (r.open_tickets ? num(r.open_tickets) : '—') + '</td><td>' + st + '</td>' +
        (d.is_admin ? '<td><button type="button" class="btn ghost xs" data-rv="pin" data-lid="' + num(r.lid) + '">' + esc(T('تثبيت', 'Pin')) + '</button></td>' : '') + '</tr>';
    });
    putHtml('rvBody', h + '</tbody></table></div></div>');
  }

  function pinDrawer(lid) {
    var r = arr((S.apts || {}).rows).filter(function (x) { return x.lid === lid; })[0];
    if (!r) return;
    openDrawer(T('تثبيت يدوي', 'Manual pin'), r.name);
    setDrawerBody('<div class="rv-meta" style="margin-bottom:12px">' + esc(T('استخدمه لما رقم Airbnb يختلف عن حسبتنا. حسبتنا الحين: ', 'Use when Airbnb shows a different number. Computed now: ')) +
      stars(r.avg) + ' · ' + esc(r.computed_in ? T('داخل البرنامج', 'in the program') : T('برا البرنامج', 'out')) + '</div>' +
      '<label class="rv-meta" for="rvPinMode">' + esc(T('الاختيار', 'Choice')) + '</label>' +
      '<select id="rvPinMode" class="input" style="width:100%;min-height:36px;margin-bottom:10px">' +
      '<option value="in"' + (r.pinned === 'in' ? ' selected' : '') + '>' + esc(T('دخّلها البرنامج', 'Force in')) + '</option>' +
      '<option value="out"' + (r.pinned === 'out' ? ' selected' : '') + '>' + esc(T('طلّعها من البرنامج', 'Force out')) + '</option>' +
      '<option value="clear"' + (!r.pinned ? ' selected' : '') + '>' + esc(T('بدون تثبيت — حسب الحسبة', 'No pin — follow the numbers')) + '</option></select>' +
      '<label class="rv-meta" for="rvPinReason">' + esc(T('السبب', 'Reason')) + '</label>' +
      '<input id="rvPinReason" class="input" style="width:100%;min-height:36px" maxlength="300" value="' + esc(r.pin_reason || '') + '" placeholder="' + esc(T('مثال: Airbnb يعرض 4.68', 'e.g. Airbnb shows 4.68')) + '">');
    setDrawerFoot('<button type="button" class="btn primary sm" data-rv="pin-save" data-lid="' + lid + '">' + esc(T('حفظ', 'Save')) + '</button>');
  }

  async function pinSave(lid, btn) {
    var mode = (document.getElementById('rvPinMode') || {}).value || 'clear';
    var reason = ((document.getElementById('rvPinReason') || {}).value || '').trim();
    if (btn) btn.disabled = true;
    var r = await post('/api/reviewask/pin', { lid: lid, mode: mode, reason: reason });
    if (btn) btn.disabled = false;
    if (!r || !r.ok) { toast((r && r.error_ar) || T('ما انحفظ', 'Not saved')); return; }
    closeDrawer();
    toast(T('انحفظ', 'Saved'));
    S.apts = null; S.sum = null;
    load(true);
  }

  /* ---------- 2) live tickets ---------- */
  function ticketRow(r, archive) {
    return '<tr class="rv-r" data-rv="ticket" data-id="' + num(r.id) + '"><td>' + esc(r.unit) + '<span class="rv-sub">' + esc(r.guest) + '</span></td><td class="rv-num">' + esc(day(r.day)) +
      '</td><td>' + esc(r.mode_ar) + '</td><td>' + esc(r.state_ar) + (r.review_stars ? ' · ' + stars(r.review_stars) : '') + (r.state_by ? '<span class="rv-sub">' + esc(r.state_by) + '</span>' : '') +
      '</td><td>' + esc(r.responsible || '—') + '</td><td>' + (archive ? esc(day(r.closed_at)) : (r.room_url ? '<a href="' + esc(r.room_url) + '" target="_blank" rel="noopener">' + esc(T('الغرفة', 'Room')) + '</a>' : '—')) + '</td></tr>';
  }

  function ticketTable(rows, archive) {
    return '<div style="overflow-x:auto"><table class="data"><thead><tr><th>' + esc(T('الشقة / الضيف', 'Apartment / guest')) + '</th><th>' + esc(T('الخروج', 'Checkout')) +
      '</th><th>' + esc(T('الوضع', 'Mode')) + '</th><th>' + esc(T('الحالة', 'State')) + '</th><th>' + esc(T('المسؤول', 'Owner')) + '</th><th>' + esc(archive ? T('انقفلت', 'Closed') : '') +
      '</th></tr></thead><tbody>' + rows.map(function (r) { return ticketRow(r, archive); }).join('') + '</tbody></table></div>';
  }

  function renderLive() {
    var rows = arr((S.live || {}).rows);
    if (!rows.length) { putHtml('rvBody', banner() + emptyState(T('ما فيه تكتات مفتوحة', 'No open tickets'), T('تنفتح الغرف ١٢:٠٥ كل ليلة لخروج اليوم.', 'Rooms open at 00:05 for that day’s checkouts.'))); return; }
    putHtml('rvBody', banner() + '<div class="card">' + ticketTable(rows, false) + '<div class="rv-meta">' +
      esc(T('التقييم يوصلنا من Airbnb بعد ما نقيّم الضيف أو بعد ١٤ يوم — إذا قال الضيف إنه قيّم، الزر «قيّم» يحفظها.', 'Airbnb releases a review after we review the guest or after 14 days — «قيّم» records the guest’s word.')) + '</div></div>');
  }

  /* ---------- 3) performance ---------- */
  function rate(done, due) { return due ? (done + '/' + due + ' (' + Math.round(100 * done / due) + '٪)') : '—'; }

  function renderPerf() {
    var d = S.perf || {};
    var seg = '<div class="rv-seg">' + [7, 30].map(function (n) {
      return '<button type="button" data-rv="days" data-d="' + n + '" class="' + (S.perfDays === n ? 'on' : '') + '">' + esc(n === 7 ? T('آخر ٧ أيام', 'Last 7 days') : T('آخر ٣٠ يوم', 'Last 30 days')) + '</button>';
    }).join('') + '</div>';
    var people = arr(d.people), apts = arr(d.apartments);
    var h = banner() + seg;
    if (!people.length && !apts.length) { putHtml('rvBody', h + emptyState(T('ما فيه نشاط في هذي الفترة', 'No activity in this period'))); return; }
    h += '<div class="card"><div style="overflow-x:auto"><table class="data"><thead><tr><th>' + esc(T('الموظف', 'Person')) + '</th><th>' + esc(T('رسائل الواتساب', 'WhatsApp sent')) + '</th><th>' +
      esc(T('المكالمات', 'Calls')) + '</th><th>' + esc(T('تقييمات جت', 'Reviews gained')) + '</th><th>' + esc(T('متوسطها', 'Avg stars')) + '</th><th>' + esc(T('فوات', 'Misses')) + '</th></tr></thead><tbody>';
    people.forEach(function (p) {
      h += '<tr><td>' + esc(p.name) + '</td><td class="rv-num">' + rate(num(p.wa_done), num(p.wa_due)) + '</td><td class="rv-num">' + rate(num(p.calls_done), num(p.calls_due)) +
        '</td><td class="rv-num">' + num(p.reviews) + '</td><td class="rv-num">' + stars(p.avg_stars) + '</td><td class="rv-num">' + (p.misses ? '<span class="rv-warn">' + num(p.misses) + '</span>' : '0') + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
    if (apts.length) {
      h += '<div class="card"><div style="overflow-x:auto"><table class="data"><thead><tr><th>' + esc(T('الشقة', 'Apartment')) + '</th><th>' + esc(T('كانت', 'Then')) + '</th><th>' + esc(T('الحين', 'Now')) + '</th><th>' + esc(T('ناقص', 'Needed')) + '</th></tr></thead><tbody>';
      apts.forEach(function (a) {
        h += '<tr><td>' + esc(a.unit) + '</td><td class="rv-num">' + stars(a.then) + '</td><td class="rv-num">' + stars(a.now) + '</td><td class="rv-num">' + num(a.needed) + '</td></tr>';
      });
      h += '</tbody></table></div></div>';
    }
    putHtml('rvBody', h);
  }

  /* ---------- 4) archive ---------- */
  function renderArch() {
    var rows = arr((S.arch || {}).rows);
    if (!rows.length) { putHtml('rvBody', banner() + emptyState(T('الأرشيف فاضي', 'Archive is empty'), T('كل تكت ينقفل يظهر هنا للأبد — حتى بعد ما تنحذف غرفته.', 'Every closed ticket stays here forever — even after its room is deleted.'))); return; }
    putHtml('rvBody', banner() + '<div class="card">' + ticketTable(rows, true) + '</div>');
  }

  async function ticketDrawer(id) {
    openDrawer(T('سجل التكت', 'Ticket record'), '');
    setDrawerBody('<div class="empty sk">…</div>');
    setDrawerFoot('');
    var r = await api('/api/reviewask/ticket?id=' + num(id)).catch(function () { return null; });
    if (!r || !r.ok) { setDrawerBody(errorState('')); return; }
    var t = r.ticket;
    var h = '<div class="rv-meta" style="margin-bottom:10px">' + esc(t.unit + ' · ' + t.guest + ' · ' + day(t.day) + ' · ' + t.state_ar) + (t.close_note ? ' · ' + esc(t.close_note) : '') + '</div>';
    h += '<div style="font-weight:700;margin:6px 0">' + esc(T('الأحداث', 'Events')) + '</div>';
    h += arr(r.events).map(function (e) {
      return '<div class="rv-ev"><span class="rv-num">' + esc(hm(e.at)) + '</span> · <b>' + esc(e.kind) + '</b>' + (e.actor ? ' · ' + esc(e.actor) : '') + (e.detail ? '<span class="rv-sub">' + esc(e.detail) + '</span>' : '') + '</div>';
    }).join('') || '<div class="rv-meta">—</div>';
    var tr = r.transcript;
    h += '<div style="font-weight:700;margin:14px 0 6px">' + esc(T('محادثة الغرفة', 'Room transcript')) + '</div>';
    if (tr && arr(tr.messages).length) {
      h += arr(tr.messages).map(function (m) {
        var body = [m.content].concat(arr(m.embeds)).concat(arr(m.attachments)).filter(function (x) { return x; }).join(String.fromCharCode(10));
        return '<div class="rv-msg"><span class="a">' + esc(m.author) + '</span> <span class="rv-num rv-sub" style="display:inline">' + esc(hm(m.at)) + '</span>' + String.fromCharCode(10) + esc(body) + '</div>';
      }).join('');
    } else {
      h += '<div class="rv-meta">' + esc(t.deleted_at ? T('ما انحفظت محادثة', 'No transcript saved') : T('الغرفة لسا موجودة في ديسكورد — تنحفظ محادثتها قبل ما تنحذف بعد ٧ أيام من القفل.', 'The room still exists — its transcript is saved before deletion, 7 days after closing.')) + '</div>';
    }
    setDrawerBody(h);
  }

  /* ---------- 5) the owner's text (R4) ---------- */
  function draft() {
    if (!S.draft) {
      var t = (S.tpl || {}).templates || {};
      S.draft = { ar: t.ar || '', en: t.en || '', call_script: t.call_script || '' };
    }
    return S.draft;
  }

  function pvBlock(p, label) {
    p = p || {};
    var unk = arr(p.unknown);
    return '<label>' + esc(label) + '</label><div class="rv-pv">' + esc(p.text || '—') + '</div>' +
      '<div class="rv-meta">' + (p.url_len ? esc(T('طول رابط الواتساب: ', 'WhatsApp link length: ')) + num(p.url_len) + ' · ' : '') +
      (unk.length ? '<span class="rv-warn">' + esc(T('كلمات ما نعرفها وبتطلع للضيف كما هي: ', 'Unknown placeholders, sent as typed: ')) + esc(unk.map(function (u) { return '{' + u + '}'; }).join(' ')) + '</span>' : esc(T('كل الكلمات معروفة', 'All placeholders known'))) + '</div>';
  }

  function renderTpl() {
    var d = S.tpl || {};
    if (d.ok === false) { putHtml('rvBody', banner() + errorState('loadRvpush(1)', d.error_ar)); return; }
    var dr = draft(), pv = d.preview || {}, max = num(d.max) || 4000;
    var admin = !!(S.apts && S.apts.is_admin);
    var phs = '<div class="rv-ph">' + PH.map(function (p) { return '<button type="button" data-rv="ph" data-p="' + esc(p) + '">{' + esc(p) + '}</button>'; }).join('') + '</div>';
    var hist = arr(d.history);
    var last = (d.templates || {}).updated_by ? esc(T('آخر تعديل: ', 'Last edit: ') + (d.templates.updated_by || '') + ' · ' + hm(d.templates.updated_at)) : '';
    var h = banner() + '<div class="card"><div class="rv-meta" style="margin:0 0 4px">' +
      esc(T('هذا النص يطلع للضيف لما الموظف يضغط «فتح واتساب» — بإسم الموظف المسؤول. الكلمات بين { } تتبدل تلقائي. النص كله لك: ما فيه أي عرض أو خصم مكتوب في البرنامج.',
            'This is what the guest receives when staff tap «فتح واتساب», signed with the responsible person. {placeholders} fill in automatically. The text is entirely yours.')) +
      '</div><div class="rv-meta">' + last + (hist.length ? ' · ' + esc(T('النسخ السابقة محفوظة: ', 'Previous versions kept: ')) + hist.length : '') + '</div>' +
      '<div class="rv-ed"><div>' +
      '<label for="rvAr">' + esc(T('رسالة الواتساب — عربي (أرقام ٩٦٦)', 'WhatsApp — Arabic (966 numbers)')) + '</label><textarea id="rvAr" data-rv="txt" data-k="ar" maxlength="' + max + '" dir="rtl">' + esc(dr.ar) + '</textarea>' + phs +
      '<label for="rvEn">' + esc(T('رسالة الواتساب — إنجليزي (باقي الأرقام · فاضي = العربي)', 'WhatsApp — English (other numbers · empty = Arabic)')) + '</label><textarea id="rvEn" data-rv="txt" data-k="en" maxlength="' + max + '" dir="ltr">' + esc(dr.en) + '</textarea>' + phs +
      '<label for="rvCs">' + esc(T('نص المكالمة (يطلع للموظف بس)', 'Call script (staff only)')) + '</label><textarea id="rvCs" data-rv="txt" data-k="call_script" maxlength="' + max + '" dir="rtl">' + esc(dr.call_script) + '</textarea>' + phs +
      '<div style="margin-top:12px;display:flex;gap:8px;align-items:center">' +
      (admin ? '<button type="button" class="btn primary sm" data-rv="tpl-save">' + esc(T('حفظ', 'Save')) + '</button>' : '<span class="rv-meta">' + esc(T('الحفظ للمدير بس', 'Saving is admin-only')) + '</span>') +
      '<button type="button" class="btn ghost sm" data-rv="tpl-reset">' + esc(T('تراجع عن تعديلاتي', 'Discard my edits')) + '</button></div>' +
      '</div><div id="rvPv">' + pvHtml(pv) + '</div></div></div>';
    putHtml('rvBody', h);
  }

  function pvHtml(pv) {
    return pvBlock(pv.ar, T('المعاينة — ضيف سعودي (سارة، المسؤول أصيل)', 'Preview — Saudi guest')) +
      pvBlock(pv.en, T('المعاينة — ضيف أجنبي', 'Preview — foreign guest')) +
      pvBlock(pv.call_script, T('نص المكالمة', 'Call script'));
  }

  function schedulePreview() {
    clearTimeout(S.pvTimer);
    S.pvTimer = setTimeout(async function () {
      var r = await post('/api/reviewask/preview', draft()).catch(function () { return null; });
      if (r && r.ok) putHtml('rvPv', pvHtml(r.preview));
      else if (r && r.error_ar) putHtml('rvPv', '<div class="rv-warn">' + esc(r.error_ar) + '</div>');
    }, 350);
  }

  async function tplSave(btn) {
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    var r = await post('/api/reviewask/templates', draft()).catch(function () { return null; });
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    if (!r || !r.ok) { toast((r && r.error_ar) || T('ما انحفظ', 'Not saved')); return; }
    toast(T('انحفظ النص — من الحين كل رسالة تطلع فيه', 'Saved — every new message uses it'));
    S.tpl = null; S.draft = null;
    show(true);
  }

  function insertPh(btn) {
    var wrap = btn.closest('.rv-ph');
    var ta = wrap && wrap.previousElementSibling;
    if (!ta || ta.tagName !== 'TEXTAREA') return;
    var token = '{' + btn.getAttribute('data-p') + '}';
    var a = ta.selectionStart || ta.value.length, b = ta.selectionEnd || a;
    ta.value = ta.value.slice(0, a) + token + ta.value.slice(b);
    ta.focus();
    ta.selectionStart = ta.selectionEnd = a + token.length;
    draft()[ta.getAttribute('data-k')] = ta.value;
    schedulePreview();
  }

  /* ---------- events (delegated) ---------- */
  function onClick(ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-rv]') : null;
    if (!el) return;
    var view = document.getElementById('view_rvpush'), drawer = document.getElementById('drawer');
    if (!((view && view.contains(el)) || (drawer && drawer.contains(el)))) return;
    var a = el.getAttribute('data-rv');
    if (a === 'view') {
      S.view = el.getAttribute('data-v');
      if (S.view === 'tpl' && !S.apts) { api('/api/reviewask/apartments').then(function (r) { S.apts = r; if (S.view === 'tpl') renderTpl(); }).catch(function () {}); }
      show(false);
    } else if (a === 'pin') { pinDrawer(num(el.getAttribute('data-lid'))); }
    else if (a === 'pin-save') { pinSave(num(el.getAttribute('data-lid')), el); }
    else if (a === 'ticket') { ticketDrawer(el.getAttribute('data-id')); }
    else if (a === 'days') { S.perfDays = num(el.getAttribute('data-d')) || 7; S.perf = null; show(true); }
    else if (a === 'ph') { insertPh(el); }
    else if (a === 'tpl-save') { tplSave(el); }
    else if (a === 'tpl-reset') { S.draft = null; renderTpl(); }
  }

  function onInput(ev) {
    var el = ev.target;
    if (!el || el.getAttribute('data-rv') !== 'txt') return;
    draft()[el.getAttribute('data-k')] = el.value;
    schedulePreview();
  }

  if (!window.__rvBound) {
    window.__rvBound = 1;
    document.addEventListener('click', onClick);
    document.addEventListener('input', onInput);
  }

  window.RvTab = { load: load };
})();
