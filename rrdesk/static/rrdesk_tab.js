/* «طلبات سام» — the RR Desk tab of the Ouja dashboard.
 *
 * Served by rrdesk/routes.py at /rrdesk/static/rrdesk_tab.js and loaded on first visit by the
 * tiny loadRrdesk() stub inside DASHBOARD_HTML. A REAL file on purpose: DASHBOARD_HTML is a
 * Python string that eats backslashes (CLAUDE.md trap 1); this file is not — but it still uses
 * none, so the structure test can hold the whole package to one rule.
 *
 * Views: المفتوحة · الأداء · السجل · الترجمة · الإعدادات.
 * Uses the dashboard's globals only: api, post, esc, labelText, toast, putHtml, errorState.
 * Every action is event-delegated through data-rd="…". Must pass `node --check`.
 * Numbers are fixed published targets, never a ranking: people are listed by name.
 */
(function () {
  'use strict';

  var S = { view: 'open', state: null, perf: null, period: 'week', offset: 0, req: null,
            reqId: null, tr: null, loading: false };

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
  function num(v) { return '<span class="rd-num">' + esc(v) + '</span>'; }
  function pct(v) { return v == null ? '—' : Math.round(v * 100) + '%'; }
  function hm(s) {
    if (!s) return '—';
    var h = Number(String(s).slice(11, 13)), m = String(s).slice(14, 16);
    if (!isFinite(h) || !m) return '—';
    return (h % 12 || 12) + ':' + m + ' ' + (h < 12 ? T('ص', 'AM') : T('م', 'PM'));
  }
  function day(s) { return s ? String(s).slice(5, 10) : ''; }
  function age(min) {
    var m = Math.max(0, Math.round(min || 0));
    if (m < 60) return m + T('د', 'm');
    if (m < 2880) return Math.floor(m / 60) + T('س', 'h');
    return Math.floor(m / 1440) + T('ي', 'd');
  }

  var STATE = {
    open: ['ينتظر', 'Waiting', 'warn'], acknowledged: ['قيد التنفيذ', 'On it', 'info'],
    delivered: ['تم التسليم', 'Delivered', 'ok'], confirmed: ['تأكد', 'Confirmed', 'ok'],
    confirmed_auto: ['تأكد تلقائياً', 'Auto-confirmed', 'ok'], cancelled: ['ملغي', 'Cancelled', ''],
    closed_with_ticket: ['انقفل مع التذكرة', 'Closed with ticket', '']
  };
  var ASK = { photos: ['صور', 'Photos'], video: ['فيديو', 'Video'], invoice: ['فاتورة', 'Invoice'],
              quote: ['عرض سعر', 'Quote'], guest_chat: ['محادثة الضيف', 'Guest chat'],
              airbnb_screens: ['سكرينات Airbnb', 'Airbnb screens'], ops_report: ['تقرير', 'Ops report'],
              receipt: ['إيصال', 'Receipt'], info: ['معلومة', 'Info'], action: ['إجراء', 'Action'],
              other: ['طلب', 'Other'] };
  var PATH = { command: ['/rr-ask', '/rr-ask'], pin: ['📌', '📌'], detected: ['تلقائي', 'Detected'],
               confirmed: ['سام أكّد', 'Sam confirmed'] };
  var RULE = { 0: ['نقل يدوي', 'Reassigned'], 1: ['سام منشنه', 'Sam mentioned'],
               2: ['المسؤول عن الشقة (منشن فريق)', 'Unit owner (role mention)'],
               3: ['فاتح التذكرة', 'Ticket opener'], 4: ['المسؤول عن الشقة اليوم', 'Unit owner today'],
               5: ['قائد العمليات — بدون مسؤول', 'Ops lead — unowned'] };
  var EV = { request_opened: ['انفتح الطلب', 'Request opened'], owner_chosen: ['تحدد المسؤول', 'Owner chosen'],
             acknowledged: ['استلم', 'Acknowledged'], ack: ['استلمت', 'On it'], deliver: ['سلّمت', 'Delivered'],
             got_it: ['سام أكّد', 'Sam confirmed'], not_what: ['مو المطلوب', 'Not what I asked'],
             cancel: ['ألغي', 'Cancelled'], reassigned: ['انتقل', 'Reassigned'], covered: ['غطّاه زميل', 'Covered'],
             ladder_R1: ['تذكير ١', 'Reminder R1'], ladder_R2: ['تذكير ٢ + رسالة خاصة', 'Reminder R2 + DM'],
             ladder_D1: ['تذكير التسليم', 'Delivery reminder D1'], ladder_D2: ['فات موعد التسليم', 'Delivery overdue D2'],
             ladder_MISS: ['تأخير', 'Miss'], miss: ['انسجّل تأخير', 'Miss recorded'], judged: ['الحكم', 'Judged'],
             excused: ['انعذر', 'Excused'], press_refused: ['ضغطة مرفوضة', 'Refused press'],
             confirmed_auto: ['تأكد تلقائياً', 'Auto-confirmed'], closed_with_ticket: ['انقفل مع التذكرة', 'Closed with ticket'],
             source_deleted: ['رسالة سام انحذفت', 'Source deleted'] };

  function lab(map, k) { var v = map[k]; return v ? T(v[0], v[1]) : esc(k); }
  function asks(a) { return arr(a).map(function (k) { return lab(ASK, k); }).join('، '); }
  function chip(state, late) {
    var v = STATE[state] || [state, state, ''];
    if (late) return '<span class="rd-st bad">' + T('متأخر', 'Overdue') + '</span>';
    return '<span class="rd-st ' + v[2] + '">' + T(v[0], v[1]) + '</span>';
  }

  function css() {
    if (document.getElementById('rdCss')) return;
    var s = document.createElement('style');
    s.id = 'rdCss';
    s.textContent = [
      '.rd-tabs{display:flex;gap:4px;flex-wrap:wrap;margin:0 0 14px;padding:3px;border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface-2);width:fit-content;max-width:100%}',
      '.rd-tabs button{border:0;background:none;padding:7px 12px;border-radius:7px;font:inherit;font-size:12.5px;font-weight:600;color:var(--text-2);cursor:pointer;min-height:34px;transition:background-color .16s cubic-bezier(.23,1,.32,1),color .16s cubic-bezier(.23,1,.32,1)}',
      '.rd-tabs button[aria-selected="true"]{background:var(--surface);color:var(--text);box-shadow:0 1px 2px rgba(60,40,20,.08)}',
      '.rd-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:10px;margin-bottom:14px}',
      '.rd-kpi{padding:12px 14px;border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface)}',
      '.rd-kpi .k{font-size:11.5px;color:var(--text-2);font-weight:600}',
      '.rd-kpi .v{font-family:var(--font-mono);font-size:22px;font-weight:700;color:var(--text);margin-top:4px;line-height:1.1}',
      '.rd-kpi.bad{border-color:transparent;background:var(--red-soft)}.rd-kpi.bad .v{color:var(--red)}',
      '.rd-kpi .s{font-size:11px;color:var(--mut);margin-top:3px}',
      '.rd-list{display:grid;gap:8px}',
      '.rd-row{display:grid;grid-template-columns:auto 1fr auto;gap:6px 14px;align-items:start;padding:12px 14px;border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface)}',
      '.rd-row.late{border-color:var(--red)}',
      '.rd-row .t{font-size:13px;color:var(--text);font-weight:600;line-height:1.5}',
      '.rd-row .m{font-size:11.5px;color:var(--text-2);display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:4px}',
      '.rd-row .side{display:flex;flex-direction:column;align-items:flex-end;gap:6px}',
      '.rd-st{display:inline-flex;align-items:center;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
      '.rd-st.warn{background:var(--gold-tint);color:var(--gold)}.rd-st.bad{background:var(--red-soft);color:var(--red)}',
      '.rd-st.ok{background:var(--green-soft);color:var(--green)}.rd-st.info{background:var(--surface-2);color:var(--text)}',
      '.rd-num{font-family:var(--font-mono);white-space:nowrap}',
      '.rd-sub{font-size:11px;color:var(--mut)}',
      '.rd-h{font-size:13px;font-weight:700;color:var(--text);margin:18px 0 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}',
      '.rd-note{font-size:12px;color:var(--text-2);line-height:1.6;margin:0 0 12px}',
      '.rd-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface)}',
      '.rd-tbl{width:100%;border-collapse:collapse;font-size:12.5px}',
      '.rd-tbl th{font-size:11px;color:var(--text-2);font-weight:700;text-align:start;padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap}',
      '.rd-tbl td{padding:9px 10px;border-bottom:1px solid var(--line);color:var(--text);white-space:nowrap}',
      '.rd-tbl tr:last-child td{border-bottom:0}',
      '.rd-tbl td.ok{color:var(--green)}.rd-tbl td.bad{color:var(--red);font-weight:700}.rd-tbl td.na{color:var(--mut)}',
      '.rd-tl{display:grid;gap:0;border-inline-start:2px solid var(--line);margin-inline-start:6px;padding-inline-start:14px}',
      '.rd-ev{position:relative;padding:6px 0;font-size:12.5px;color:var(--text)}',
      '.rd-ev:before{content:"";position:absolute;inset-inline-start:-19px;top:12px;width:8px;height:8px;border-radius:50%;background:var(--gold)}',
      '.rd-ev .w{font-family:var(--font-mono);font-size:11px;color:var(--mut);margin-inline-end:8px}',
      '.rd-ev .d{display:block;font-size:11px;color:var(--text-2);margin-top:2px;white-space:normal;word-break:break-word}',
      '.rd-form{display:grid;gap:10px;max-width:560px}',
      '.rd-form label{font-size:12px;font-weight:700;color:var(--text);display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}',
      '.rd-form label span{font-weight:500;color:var(--mut)}',
      '.rd-in{min-height:36px;padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--text);font:inherit;font-size:12.5px;width:100%;box-sizing:border-box}',
      '.rd-line{display:flex;gap:6px;align-items:center;flex-wrap:wrap}',
      '.rd-line .rd-in{flex:1;min-width:110px;width:auto}',
      '.rd-sw{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface)}',
      '.rd-sw.money{border-color:var(--gold)}',
      '.rd-sug{font-size:11.5px;color:var(--gold);font-weight:600}',
      '.rd-row .btn,.rd-tabs button{-webkit-tap-highlight-color:transparent}',
      '.btn:active,.rd-tabs button:active{transform:scale(.97)}',
      '@media (max-width:560px){.rd-row{grid-template-columns:1fr}.rd-row .side{flex-direction:row;align-items:center;justify-content:space-between}.rd-kpi .v{font-size:19px}}',
      '@media (prefers-reduced-motion:reduce){.btn:active,.rd-tabs button:active{transform:none}.rd-tabs button{transition:none}}'
    ].join('');
    document.head.appendChild(s);
  }

  // ---------------------------------------------------------------- data

  async function fetchFor(view, force) {
    if (view === 'open' || view === 'log') {
      if (force || !S.state) S.state = await api('/api/rrdesk/state');
    }
    if (view === 'perf' && (force || !S.perf || S.perf.period !== S.period || S.perf._off !== S.offset)) {
      S.perf = await api('/api/rrdesk/perf?period=' + S.period + '&offset=' + S.offset);
      if (S.perf) S.perf._off = S.offset;
    }
    if ((view === 'tr' || view === 'set') && (force || !S.tr)) S.tr = await api('/api/rrdesk/translation');
    if (view === 'log' && S.reqId && (force || !S.req || (S.req.request && S.req.request.id !== S.reqId))) {
      S.req = await api('/api/rrdesk/request?id=' + S.reqId);
    }
  }

  async function load(force) {
    css();
    if (S.loading) return;
    S.loading = true;
    if (force || !S.state) putHtml('rdBody', tabs() + '<div class="empty sk">…</div>');
    try {
      await fetchFor(S.view, force);
      var bad = [S.state, S.perf, S.tr].filter(function (x) { return x && x.ok === false; })[0];
      if (bad && bad.error === 'unauthorized') { putHtml('rdBody', errorState('loadRrdesk(1)', bad.error)); return; }
      render();
    } catch (e) {
      putHtml('rdBody', tabs() + errorState('loadRrdesk(1)'));
    } finally {
      S.loading = false;
    }
  }

  // ---------------------------------------------------------------- views

  function tabs() {
    var v = [['open', 'المفتوحة', 'Open'], ['perf', 'الأداء', 'Performance'], ['log', 'السجل', 'Timeline'],
             ['tr', 'الترجمة', 'Translation'], ['set', 'الإعدادات', 'Settings']];
    return '<div class="rd-tabs" role="tablist">' + v.map(function (x) {
      return '<button role="tab" data-rd="view" data-v="' + x[0] + '" aria-selected="' + (S.view === x[0]) + '">' +
        T(x[1], x[2]) + '</button>';
    }).join('') + '</div>';
  }

  function kpi(k, v, sub, bad) {
    return '<div class="rd-kpi' + (bad ? ' bad' : '') + '"><div class="k">' + k + '</div><div class="v">' + v +
      '</div>' + (sub ? '<div class="s">' + sub + '</div>' : '') + '</div>';
  }

  function banner(h) {
    if (!h) return '';
    var sw = h.switches || {};
    var bits = [];
    if (sw.force_off) bits.push(T('⛔ النظام موقف بالكامل (/rrdesk-on يرجعه)', '⛔ Fully muted (/rrdesk-on to resume)'));
    if (!sw.warn_live) bits.push(T('الإنذارات تجربة فقط — ما تنقص العمولة', 'Warnings are dry-run — no commission effect'));
    if (!h.sam_resolved) bits.push(T('⚠️ ما عرفنا حساب سام — حدده بـ /rrdesk-sam', '⚠️ Sam is not identified — use /rrdesk-sam'));
    if (h.detect_mode !== 'auto') bits.push(T('الطلبات المكتشفة تسأل سام أول («هل هذا طلب؟»)', 'Detected requests ask Sam first'));
    return bits.length ? '<p class="rd-note">' + bits.join(' · ') + '</p>' : '';
  }

  function viewOpen() {
    var d = S.state || {};
    var t = d.team || {};
    var rows = arr(d.rows);
    var html = banner(d.health) + '<div class="rd-kpis">' +
      kpi(T('مفتوحة', 'Open'), num(t.open || 0), T('تنتظر رد أو تسليم', 'awaiting reply or delivery')) +
      kpi(T('متأخرة', 'Overdue'), num(t.late || 0), '', (t.late || 0) > 0) +
      kpi(T('خطر AirCover', 'AirCover risk'), num(t.aircover_risk || 0), T('مهلة ≤ ٣ أيام', 'deadline ≤ 3 days'), (t.aircover_risk || 0) > 0) +
      kpi(T('أقدم طلب', 'Oldest'), num(age(t.oldest_min)), T('بوقت العمل', 'working time')) +
      kpi(T('بدون مسؤول', 'Unowned'), num(t.unowned || 0), '', (t.unowned || 0) > 0) +
      kpi(T('ينتظر تأكيد سام', 'Awaiting Sam'), num(t.awaiting_sam || 0)) +
      kpi(T('تكلفة الترجمة اليوم', 'Translation today'), num((t.cost_today_sar || 0).toFixed(2)) + ' ' + T('ر.س', 'SAR'),
          T('الشهر: ', 'Month: ') + (t.cost_month_sar || 0).toFixed(2)) +
      '</div>';
    if (!rows.length) {
      return html + '<div class="empty">' + T('ما فيه طلبات مفتوحة من سام ✅', 'No open requests from Sam ✅') + '</div>';
    }
    return html + '<div class="rd-list">' + rows.map(function (r) {
      var due = r.state === 'open' ? r.resp_due : r.deliv_due;
      return '<div class="rd-row' + (r.late ? ' late' : '') + '">' +
        '<div>' + chip(r.state, r.late) + '</div>' +
        '<div><div class="t">' + (r.urgent ? '⚡ ' : '') + 'RR #' + esc(r.seq || '?') + ' — ' + esc(r.summary_ar || r.summary_en) + '</div>' +
        '<div class="m"><span>' + asks(r.asks) + '</span><span>' + T('المسؤول: ', 'Owner: ') + esc(r.owner || '—') +
        (r.unowned ? ' ⚠️' : '') + '</span><span>' + lab(PATH, r.path) + '</span>' +
        (r.rework ? '<span>' + T('إعادة شغل ', 'Rework ') + num(r.rework) + '</span>' : '') + '</div></div>' +
        '<div class="side"><span class="rd-num">' + age(r.age_min) + '</span>' +
        (due && r.state !== 'delivered' ? '<span class="rd-sub">' + T('قبل ', 'due ') + hm(due) + ' ' + day(due) + '</span>' : '') +
        '<span class="rd-line">' + (r.link ? '<a class="btn ghost sm" href="' + esc(r.link) + '" target="_blank" rel="noopener">' + T('ديسكورد', 'Discord') + '</a>' : '') +
        '<button class="btn ghost sm" data-rd="open-req" data-id="' + r.id + '">' + T('السجل', 'Timeline') + '</button></span></div>' +
        '</div>';
    }).join('') + '</div>';
  }

  function cell(v, ok, fmt) {
    if (v == null) return '<td class="na">—</td>';
    return '<td class="' + (ok === true ? 'ok' : ok === false ? 'bad' : '') + '">' + num(fmt(v)) + '</td>';
  }

  function viewPerf() {
    var p = S.perf || {};
    var people = arr(p.people);
    var tg = p.targets || {};
    var sla = tg.sla || {};
    var head = '<div class="rd-line" style="margin-bottom:12px">' +
      '<div class="rd-tabs" style="margin:0"><button data-rd="period" data-p="week" aria-selected="' + (S.period === 'week') + '">' + T('أسبوع', 'Week') + '</button>' +
      '<button data-rd="period" data-p="month" aria-selected="' + (S.period === 'month') + '">' + T('شهر', 'Month') + '</button></div>' +
      '<button class="btn ghost sm" data-rd="shift" data-d="1">' + T('السابق', 'Previous') + '</button>' +
      '<span class="rd-num">' + esc(p.label || '') + '</span>' +
      (S.offset > 0 ? '<button class="btn ghost sm" data-rd="shift" data-d="-1">' + T('التالي', 'Next') + '</button>' : '') + '</div>' +
      '<p class="rd-note">' + T('أهداف ثابتة ومعلنة — مو ترتيب بين الموظفين. أقل من ٣ طلبات = «بيانات ناقصة».',
        'Fixed published targets — not a ranking. Fewer than 3 requests = “not enough data”.') + '</p>';
    if (!people.length) return head + '<div class="empty">' + T('ما فيه طلبات بهالفترة.', 'No requests in this period.') + '</div>';
    var th = [T('الموظف', 'Person'), T('الطلبات', 'Owned'), T('رد بوقته', 'Response on time') + ' ≥' + pct(tg.resp_on_time),
              T('وسيط أول رد', 'Median response') + ' ≤' + (sla.resp_min || 60) + T('د', 'm'),
              T('سلّم بوقته', 'Delivery on time') + ' ≥' + pct(tg.deliv_on_time),
              T('وسيط التسليم', 'Median delivery') + ' ≤' + Math.round((sla.deliv_min || 480) / 60) + T('س', 'h'),
              T('إعادة شغل', 'Rework') + ' ≤' + pct(tg.rework), T('تأخيرات', 'Misses'), T('فويس', 'Voice')];
    return head + '<div class="rd-wrap"><table class="rd-tbl"><thead><tr>' + th.map(function (x) { return '<th>' + x + '</th>'; }).join('') +
      '</tr></thead><tbody>' + people.map(function (k) {
        var m = k.meets || {};
        if (k.insufficient) {
          return '<tr><td>' + esc(k.name) + '</td><td>' + num(k.owned) + '</td><td class="na" colspan="5">' +
            T('بيانات ناقصة', 'Not enough data') + '</td>' + cell(k.misses, k.misses === 0, String) + cell(k.voice, k.voice === 0, String) + '</tr>';
        }
        return '<tr><td>' + esc(k.name) + '</td><td>' + num(k.owned) + '</td>' +
          cell(k.resp_on_time, m.resp_on_time, pct) + cell(k.median_resp_min, m.median_resp_min, function (v) { return v + T('د', 'm'); }) +
          cell(k.deliv_on_time, m.deliv_on_time, pct) + cell(k.median_deliv_h, m.median_deliv_h, function (v) { return v + T('س', 'h'); }) +
          cell(k.rework_rate, m.rework_rate, pct) + cell(k.misses, m.misses, String) + cell(k.voice, m.voice, String) + '</tr>';
      }).join('') + '</tbody></table></div>';
  }

  function detailText(d) {
    if (!d || typeof d !== 'object') return '';
    var keep = ['why', 'reason', 'note', 'rule', 'name', 'from', 'to', 'verdict', 'nth', 'week', 'eligible', 'path', 'confidence', 'key'];
    return keep.filter(function (k) { return d[k] !== undefined && d[k] !== null && d[k] !== ''; })
      .map(function (k) { return k + ': ' + (typeof d[k] === 'object' ? JSON.stringify(d[k]) : d[k]); }).join(' · ');
  }

  function viewLog() {
    var rows = arr((S.state || {}).recent);
    var pick = '<div class="rd-line" style="margin-bottom:12px"><select class="rd-in" data-rd-f="req" style="max-width:420px">' +
      '<option value="">' + T('اختر طلب…', 'Pick a request…') + '</option>' + rows.map(function (r) {
        return '<option value="' + r.id + '"' + (r.id === S.reqId ? ' selected' : '') + '>#' + r.id + ' · RR ' + esc(r.seq || '?') + ' · ' +
          esc((r.summary_en || '').slice(0, 50)) + '</option>';
      }).join('') + '</select><button class="btn ghost sm" data-rd="show-req">' + T('اعرض', 'Show') + '</button></div>';
    var q = S.req;
    if (!S.reqId || !q) return pick + '<p class="rd-note">' + T('كل قرار يتسجل: من فتح الطلب، ليش هذا المسؤول، كل تذكير، كل ضغطة (حتى المرفوضة).',
      'Every decision is logged: who opened it, why this owner, each reminder, each press — refused ones too.') + '</p>';
    if (q.ok === false) return pick + '<div class="empty">' + esc(q.error || '') + '</div>';
    var r = q.request;
    var head = '<div class="rd-row"><div>' + chip(r.state) + '</div><div><div class="t">RR #' + esc(r.seq || '?') + ' — ' + esc(r.summary_en) +
      '</div><div class="m"><span>' + esc(r.summary_ar) + '</span><span>' + T('المسؤول: ', 'Owner: ') + esc(r.owner || '—') + ' (' + lab(RULE, r.owner_rule) + ')</span>' +
      '<span>' + T('الرد قبل ', 'Response due ') + hm(r.resp_due) + ' ' + day(r.resp_due) + '</span><span>' + T('التسليم قبل ', 'Delivery due ') + hm(r.deliv_due) + ' ' + day(r.deliv_due) + '</span></div></div>' +
      '<div class="side">' + (r.link ? '<a class="btn ghost sm" href="' + esc(r.link) + '" target="_blank" rel="noopener">' + T('ديسكورد', 'Discord') + '</a>' : '') + '</div></div>';
    var miss = arr(q.misses).map(function (m) {
      return '<div class="rd-note">' + T('تأخير', 'Miss') + ' · ' + esc(m.week) + ' · ' + (m.eligible ? T('ينحسب', 'counts') : T('ما ينحسب', 'does not count')) +
        (m.excused_by ? ' · ' + T('معذور: ', 'excused: ') + esc(m.excused_reason || '') : '') +
        (m.eligible && !m.excused_by ? ' <button class="btn ghost sm" data-rd="excuse" data-id="' + r.id + '">' + T('عذر', 'Excuse') + '</button>' : '') + '</div>';
    }).join('');
    var tl = '<div class="rd-h">' + T('التسلسل', 'Timeline') + '</div><div class="rd-tl">' + arr(q.events).map(function (e) {
      return '<div class="rd-ev"><span class="w">' + esc(String(e.at).slice(5, 16).replace('T', ' ')) + '</span>' + lab(EV, e.kind) +
        (e.actor ? ' · ' + esc(e.actor) : '') + '<span class="d">' + esc(detailText(e.detail)) + '</span></div>';
    }).join('') + '</div>';
    return pick + head + miss + tl;
  }

  function viewTr() {
    var d = S.tr || {};
    var a = d.today || {}, m = d.month || {};
    var html = '<div class="rd-kpis">' +
      kpi(T('اليوم', 'Today'), num((a.sar || 0).toFixed(2)) + ' ' + T('ر.س', 'SAR'), num('$' + (a.usd || 0).toFixed(3)) + ' · ' + num(a.done || 0) + T(' ترجمة', ' translations')) +
      kpi(T('هالشهر', 'This month'), num((m.sar || 0).toFixed(2)) + ' ' + T('ر.س', 'SAR'), num('$' + (m.usd || 0).toFixed(3))) +
      kpi(T('مجاني (جدول + كاش)', 'Free (phrases + cache)'), num(pct(a.cache_hit_rate)), T('اليوم', 'today')) +
      kpi(T('مكالمات اليوم', 'Calls today'), num((d.calls_today || 0) + ' / ' + (d.cap || 0)), T('الحد اليومي', 'daily cap'), (d.calls_today || 0) >= (d.cap || 1)) +
      kpi(T('فشل', 'Failures'), num(a.failed || 0), T('اليوم', 'today'), (a.failed || 0) > 0) +
      '</div><p class="rd-note">' + T('السعر: ', 'Price: ') + num('$' + d.price_in + '/M in · $' + d.price_out + '/M out') +
      T(' — Haiku 4.5، السعر الرسمي المنشور.', ' — Haiku 4.5, Anthropic’s published price.') + '</p>';
    if (arr(d.failures).length) {
      html += '<div class="rd-h">' + T('آخر الأخطاء', 'Recent failures') + '</div><div class="rd-wrap"><table class="rd-tbl"><tbody>' +
        arr(d.failures).map(function (f) { return '<tr><td class="rd-num">' + esc(String(f.at).slice(5, 16)) + '</td><td>' + esc(f.where) + '</td><td>' + esc(f.error) + '</td></tr>'; }).join('') +
        '</tbody></table></div>';
    }
    var can = !!d.can_edit;
    html += '<div class="rd-h">' + T('القاموس', 'Glossary') + ' <span class="rd-st">' + num(arr(d.glossary).length) + '</span></div>' +
      '<p class="rd-note">' + T('كل مصطلح هنا يترجم دايماً بنفس الطريقة (AirCover، فاتورة، …).', 'Each term here is always translated the same way.') + '</p>' +
      '<div class="rd-wrap"><table class="rd-tbl"><thead><tr><th>عربي</th><th>English</th><th>' + T('ملاحظة', 'Note') + '</th>' + (can ? '<th></th>' : '') + '</tr></thead><tbody>' +
      arr(d.glossary).map(function (g, i) {
        return '<tr><td>' + esc(g.term_ar) + '</td><td dir="ltr">' + esc(g.term_en) + '</td><td>' + esc(g.note || '') + '</td>' +
          (can ? '<td><button class="btn ghost sm" data-rd="g-del" data-i="' + i + '">' + T('حذف', 'Remove') + '</button></td>' : '') + '</tr>';
      }).join('') + '</tbody></table></div>' +
      (can ? '<div class="rd-line" style="margin-top:10px"><input class="rd-in" data-rd-f="g-ar" placeholder="عربي"><input class="rd-in" dir="ltr" data-rd-f="g-en" placeholder="English">' +
        '<input class="rd-in" data-rd-f="g-note" placeholder="' + T('ملاحظة (اختياري)', 'Note (optional)') + '"><button class="btn primary sm" data-rd="g-add">' + T('إضافة', 'Add') + '</button></div>' : '');
    return html;
  }

  function viewSet() {
    var d = S.tr || {};
    var s = d.settings || {};
    var can = !!d.can_edit;
    var sla = s.sla || {};
    var sug = (s.suggested || {}).calibration || null;
    function f(key, label, val, sugv, unit) {
      return '<label>' + label + (sugv != null ? '<span class="rd-sug">' + T('الدراسة تقترح: ', 'Study suggests: ') + esc(sugv) + ' ' + unit + '</span>' : '') + '</label>' +
        '<input class="rd-in" inputmode="numeric" data-rd-f="' + key + '" value="' + esc(val) + '"' + (can ? '' : ' disabled') + '>';
    }
    var sw = s.switches || {};
    function swRow(k, ar, en, money) {
      return '<div class="rd-sw' + (money ? ' money' : '') + '"><span>' + T(ar, en) + ' — <b>' + (sw[k] ? T('شغال', 'on') : T('موقف', 'off')) + '</b></span>' +
        (can ? '<button class="btn ghost sm" data-rd="sw" data-k="' + k + '" data-on="' + (sw[k] ? '0' : '1') + '">' + (sw[k] ? T('إيقاف', 'Turn off') : T('تشغيل', 'Turn on')) + '</button>' : '') + '</div>';
    }
    return '<p class="rd-note">' + (can ? T('التعديل للإدارة. كل تغيير يتسجل باسمك.', 'Admins edit; every change is logged with your name.')
      : T('عرض فقط — التعديل للإدارة.', 'Read-only — admins edit.')) + '</p>' +
      '<div class="rd-form">' +
      '<div class="rd-h">' + T('أوقات الرد والتسليم (دقائق عمل، ١١ الصبح – ١:٣٠ الليل)', 'Response / delivery times (working minutes, 11:00–01:30)') + '</div>' +
      f('resp_min', T('الرد — عادي', 'Response — normal'), sla.resp_min, sug ? sug.resp_min : null, T('دقيقة', 'min')) +
      f('deliv_min', T('التسليم — عادي', 'Delivery — normal'), sla.deliv_min, sug ? sug.deliv_min : null, T('دقيقة', 'min')) +
      f('urg_resp_min', T('الرد — مستعجل', 'Response — urgent'), sla.urg_resp_min, null, '') +
      f('urg_deliv_min', T('التسليم — مستعجل', 'Delivery — urgent'), sla.urg_deliv_min, null, '') +
      '<div class="rd-h">' + T('سام والاكتشاف', 'Sam & detection') + '</div>' +
      '<label>' + T('حساب سام (أرقام ديسكورد)', 'Sam’s Discord id(s)') + '<span>' + esc(s.sam_source || '') + '</span></label>' +
      '<input class="rd-in" dir="ltr" data-rd-f="sam_ids" value="' + esc(arr(s.sam_ids).join(',')) + '"' + (can ? '' : ' disabled') + '>' +
      '<label>' + T('الطلبات المكتشفة تلقائياً', 'Detected requests') + '</label>' +
      '<select class="rd-in" data-rd-f="detect_mode"' + (can ? '' : ' disabled') + '>' +
      [['confirm', 'تسأل سام أول «هل هذا طلب؟» (الافتراضي)', 'Ask Sam first (default)'], ['auto', 'تنفتح تلقائياً فوق الحد', 'Open automatically above the threshold'],
       ['explicit', 'بس /rr-ask و📌', 'Only /rr-ask and 📌']].map(function (o) {
        return '<option value="' + o[0] + '"' + (s.detect_mode === o[0] ? ' selected' : '') + '>' + T(o[1], o[2]) + '</option>';
      }).join('') + '</select>' +
      f('threshold', T('حد الثقة للفتح التلقائي', 'Auto-open confidence threshold'), s.threshold, null, '') +
      f('daily_calls', T('الحد اليومي لمكالمات الترجمة', 'Daily translation call cap'), s.daily_calls, null, '') +
      (can ? '<button class="btn primary sm" data-rd="save" style="justify-self:start">' + T('حفظ', 'Save') + '</button>' : '') +
      '<div class="rd-h">' + T('المفاتيح', 'Switches') + '</div>' +
      swRow('translate', 'الترجمة', 'Translation') + swRow('requests', 'تتبع الطلبات', 'Request tracking') +
      swRow('ladder', 'التذكيرات', 'Reminder ladder') + swRow('force_off', 'الإيقاف الكامل (طوارئ)', 'Emergency mute') +
      swRow('warn_live', 'الإنذارات الفعلية (تنقص العمولة)', 'Real warnings (cut commission)', true) +
      '</div>';
  }

  function render() {
    var body = S.view === 'perf' ? viewPerf() : S.view === 'log' ? viewLog() : S.view === 'tr' ? viewTr()
      : S.view === 'set' ? viewSet() : viewOpen();
    putHtml('rdBody', tabs() + body);
  }

  // ---------------------------------------------------------------- actions

  function field(name) {
    var el = document.querySelector('#view_rrdesk [data-rd-f="' + name + '"]');
    return el ? el.value : '';
  }

  async function act(path, body, el) {
    if (el) el.setAttribute('aria-busy', 'true');
    try {
      var r = await post(path, body);
      if (!r || r.ok === false) { toast((r && (r.error || r.message)) || T('ما انحفظ', 'Not saved')); return null; }
      return r;
    } finally {
      if (el) el.removeAttribute('aria-busy');
    }
  }

  async function onClick(ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-rd]') : null;
    if (!el) return;
    var view = document.getElementById('view_rrdesk');
    if (!view || !view.contains(el)) return;
    var a = el.getAttribute('data-rd');
    if (a === 'view') { S.view = el.getAttribute('data-v'); load(false); }
    else if (a === 'period') { S.period = el.getAttribute('data-p'); S.offset = 0; load(false); }
    else if (a === 'shift') { S.offset = Math.max(0, S.offset + Number(el.getAttribute('data-d'))); load(false); }
    else if (a === 'open-req') { S.reqId = Number(el.getAttribute('data-id')); S.view = 'log'; load(false); }
    else if (a === 'show-req') { var v = Number(field('req')); if (v) { S.reqId = v; load(true); } }
    else if (a === 'excuse') {
      var reason = window.prompt(T('سبب العذر (١٠ أحرف على الأقل):', 'Reason (10+ characters):')) || '';
      if (reason.trim().length < 10) { toast(T('السبب قصير', 'Reason too short')); return; }
      var r = await act('/api/rrdesk/excuse', { request_id: Number(el.getAttribute('data-id')), reason: reason }, el);
      if (r) { toast(r.message || T('تم', 'Done')); load(true); }
    } else if (a === 'save') {
      var body = { resp_min: Number(field('resp_min')), deliv_min: Number(field('deliv_min')),
                   urg_resp_min: Number(field('urg_resp_min')), urg_deliv_min: Number(field('urg_deliv_min')),
                   sam_ids: field('sam_ids'), detect_mode: field('detect_mode'), threshold: Number(field('threshold')),
                   daily_calls: Number(field('daily_calls')) };
      if (await act('/api/rrdesk/settings', body, el)) { toast(T('انحفظ', 'Saved')); S.tr = null; load(true); }
    } else if (a === 'sw') {
      var k = el.getAttribute('data-k'), on = el.getAttribute('data-on') === '1', sw = {};
      sw[k] = on;
      var payload = { switches: sw };
      if (k === 'warn_live' && on) {
        payload.confirm = window.prompt(T('هذا يخلّي التأخيرات إنذارات فعلية تنقص العمولة. اكتب «تشغيل» للتأكيد:',
          'This makes misses real warnings that cut commission. Type تشغيل to confirm:')) || '';
      }
      if (await act('/api/rrdesk/settings', payload, el)) { S.tr = null; load(true); }
    } else if (a === 'g-add' || a === 'g-del') {
      var terms = arr((S.tr || {}).glossary).slice();
      if (a === 'g-add') {
        var ar = field('g-ar').trim(), en = field('g-en').trim();
        if (!ar || !en) { toast(T('اكتب الكلمتين', 'Fill both terms')); return; }
        terms.push({ term_ar: ar, term_en: en, note: field('g-note').trim() });
      } else {
        var g = terms[Number(el.getAttribute('data-i'))];
        if (!g) return;
        terms = terms.filter(function (t) { return t !== g; });
        terms.push({ term_ar: g.term_ar, term_en: g.term_en, deleted: true });   // also hides a seed term
      }
      if (await act('/api/rrdesk/glossary', { terms: terms }, el)) { S.tr = null; load(true); }
    }
  }

  if (!window.__rdBound) {
    window.__rdBound = 1;
    document.addEventListener('click', onClick);
  }

  window.RrdeskTab = { load: load };
})();
