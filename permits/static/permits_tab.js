/* «التصاريح» — the Permits tab of the Ouja dashboard.
 *
 * Served by permits/routes.py at /permits/static/permits_tab.js and loaded on first visit by
 * the tiny loadPermits() stub inside DASHBOARD_HTML. It lives in a REAL file on purpose:
 * DASHBOARD_HTML is a Python string that eats backslashes (CLAUDE.md trap 1), this file is not.
 *
 * Uses the dashboard's globals only: api, post, tok, esc, labelText, L, toast, putHtml,
 * emptyState, errorState, openDrawer, setDrawerBody, setDrawerFoot, closeDrawer, D, buildSideNav.
 * Every action is event-delegated through data-pa="…" (no inline onclick string-building).
 * Must pass `node --check` (tests/test_permits_dashboard.py).
 */
(function () {
  'use strict';

  var S = { data: null, months: null, loading: false, f: { band: '', q: '', type: '', scope: '' },
            monthOpen: '', item: null, view: 'detail', imp: null, timer: null };

  var BAND = {
    expired:  { ar: 'منتهي',       en: 'Expired' },
    urgent:   { ar: 'عاجل',        en: 'Urgent' },
    due:      { ar: 'يحتاج تجديد', en: 'Renew now' },
    upcoming: { ar: 'قريب',        en: 'Coming up' },
    ok:       { ar: 'سليم',        en: 'Healthy' },
    unknown:  { ar: 'ناقص بيانات', en: 'Missing data' }
  };

  function T(ar, en) { return labelText(ar, en); }
  function n(x) { x = Number(x); return isFinite(x) ? x : 0; }
  function arr(x) { return Array.isArray(x) ? x : []; }

  /* ---------- styles: scoped, token-only (the locked :root palette) ---------- */
  function css() {
    if (document.getElementById('pmCss')) return;
    var s = document.createElement('style');
    s.id = 'pmCss';
    s.textContent = [
      '.pm-banner{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;border-radius:var(--r-md);padding:12px 14px;margin-bottom:14px;border:1px solid var(--line);background:var(--surface)}',
      '.pm-banner.dry{background:var(--yellow-soft);border-color:transparent}',
      '.pm-banner.forced{background:var(--red-soft);border-color:transparent}',
      '.pm-banner .t{font-weight:700;color:var(--text);font-size:13.5px}',
      '.pm-banner .s{color:var(--text-2);font-size:12.5px;flex:1 1 260px}',
      '.pm-would{display:flex;flex-wrap:wrap;gap:6px;width:100%}',
      '.pm-beat{font-size:12px;color:var(--mut);display:inline-flex;align-items:center;gap:6px}',
      '.pm-beat.stale{color:var(--red);font-weight:700}',
      '.pm-dot{width:8px;height:8px;border-radius:50%;background:var(--mut);display:inline-block;flex-shrink:0}',
      '.pm-dot.expired,.pm-dot.urgent{background:var(--red)}',
      '.pm-dot.due{background:var(--yellow)}',
      '.pm-dot.upcoming{background:var(--yellow);opacity:.55}',
      '.pm-dot.ok{background:var(--green)}',
      '.pm-dot.unknown{background:transparent;box-shadow:inset 0 0 0 1.5px var(--red)}',
      '.pm-band{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;white-space:nowrap}',
      '.pm-band.expired{background:var(--red-soft);color:var(--red)}',
      '.pm-band.urgent{background:var(--red);color:var(--surface)}',
      '.pm-band.due{background:var(--yellow-soft);color:var(--yellow)}',
      '.pm-band.upcoming{background:var(--surface-2);color:var(--yellow)}',
      '.pm-band.ok{background:var(--green-soft);color:var(--green)}',
      '.pm-band.unknown{background:transparent;color:var(--red);box-shadow:inset 0 0 0 1px var(--red)}',
      '.pm-kpi{cursor:pointer;text-align:start;font:inherit;transition:transform .12s cubic-bezier(0.23,1,0.32,1),box-shadow .12s}',
      '.pm-kpi:active{transform:scale(.97)}',
      '.pm-kpi.on{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}',
      '.pm-months{display:grid;grid-template-columns:repeat(12,1fr);gap:6px;align-items:end;height:118px;padding-top:6px}',
      '.pm-m{display:flex;flex-direction:column;align-items:center;gap:4px;height:100%;justify-content:flex-end;cursor:pointer;background:none;border:0;font:inherit;padding:0;color:var(--text-2)}',
      '.pm-m .c{font-family:var(--font-mono);font-size:11.5px;font-weight:700;color:var(--text)}',
      '.pm-m .b{width:100%;max-width:34px;border-radius:5px 5px 2px 2px;background:var(--surface-3);min-height:3px}',
      '.pm-m.has .b{background:var(--accent)}',
      '.pm-m.on .b{background:var(--gold-2)}',
      '.pm-m .l{font-size:10.5px;color:var(--mut);white-space:nowrap}',
      '.pm-mlist{margin-top:10px;font-size:12.5px;color:var(--text-2);display:flex;flex-wrap:wrap;gap:6px}',
      '.pm-filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}',
      '.pm-filters input,.pm-filters select{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);font:inherit;font-size:12.5px;min-height:36px}',
      '.pm-filters input{flex:1 1 220px}',
      '.pm-chip{display:inline-flex;align-items:center;gap:4px;padding:1px 7px;border-radius:5px;font-size:10.5px;font-weight:600;background:var(--surface-2);color:var(--mut);margin-inline-start:6px;white-space:nowrap}',
      '.pm-chip.warn{background:var(--yellow-soft);color:var(--yellow)}',
      '.pm-chip.bad{background:var(--red-soft);color:var(--red)}',
      'table.data tr.pm-r{cursor:pointer}',
      '.pm-sub{display:block;font-size:11px;color:var(--mut);margin-top:2px}',
      '.pm-left{font-weight:700;white-space:nowrap}',
      '.pm-num{font-family:var(--font-mono);white-space:nowrap;font-size:12.5px}',
      '.pm-type{white-space:nowrap}',
      '@media (max-width:1180px){table.pm-t .pm-md{display:none}}',
      '.pm-left.expired,.pm-left.urgent,.pm-left.unknown{color:var(--red)}',
      '.pm-left.due{color:var(--yellow)}',
      '.pm-wrap{overflow-x:auto}',
      '.pm-sec{margin:18px 0 8px;font-size:12px;font-weight:700;color:var(--mut)}',
      '.pm-kv{display:grid;grid-template-columns:minmax(110px,34%) 1fr;gap:6px 12px;font-size:13px;margin-bottom:6px}',
      '.pm-kv .k{color:var(--mut)}',
      '.pm-kv .v{color:var(--text);word-break:break-word}',
      '.pm-issue{background:var(--yellow-soft);border-radius:8px;padding:9px 11px;margin-bottom:8px;font-size:12.5px;color:var(--text)}',
      '.pm-ev{font-size:12px;color:var(--text-2);padding:7px 0;border-bottom:1px solid var(--line)}',
      '.pm-ev .w{color:var(--mut);font-size:11px}',
      '.pm-preview{font-size:12px;color:var(--text-2);margin-top:5px;min-height:16px}',
      '.pm-preview.bad{color:var(--red)}',
      '.pm-warn{font-size:12px;color:var(--yellow);margin-top:4px}',
      '.pm-err{background:var(--red-soft);color:var(--red);border-radius:8px;padding:9px 11px;font-size:12.5px;margin-bottom:10px}',
      '.pm-imp td,.pm-imp th{font-size:12px}',
      '.pm-imp tr.dup td{background:var(--yellow-soft)}',
      '.pm-imp tr.bad td{background:var(--red-soft)}',
      '.pm-row-actions{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}',
      '@media (max-width:767px){',
      '  .pm-months{gap:3px;height:96px}.pm-m .l{font-size:9px}',
      '  table.pm-t thead{display:none}',
      '  table.pm-t tr.pm-r{display:block;border:1px solid var(--line);border-radius:var(--r-md);margin-bottom:8px;background:var(--surface)}',
      '  table.pm-t tr.pm-r td{display:flex;justify-content:space-between;gap:10px;border:0;padding:6px 12px}',
      '  table.pm-t tr.pm-r td::before{content:attr(data-l);color:var(--mut);font-size:11px;font-weight:600}',
      '  table.pm-t tr.pm-r td.pm-md{display:none}',
      '  .pm-kv{grid-template-columns:1fr}',
      '}',
      '@media (prefers-reduced-motion:reduce){.pm-kpi{transition:none}.pm-kpi:active{transform:none}}'
    ].join('\n');
    document.head.appendChild(s);
  }

  /* ---------- small helpers ---------- */
  function bandPill(b) {
    var m = BAND[b] || BAND.unknown;
    return '<span class="pm-band ' + esc(b) + '"><span class="pm-dot ' + esc(b) + '" aria-hidden="true"></span>' + esc(T(m.ar, m.en)) + '</span>';
  }

  function nDays(x) {
    x = Math.abs(n(x));
    if (L !== 'ar') return x + (x === 1 ? ' day' : ' days');
    if (x === 1) return 'يوم واحد';
    if (x === 2) return 'يومين';
    if (x >= 3 && x <= 10) return x + ' أيام';
    return x + ' يوم';
  }

  function leftText(d) {
    if (d === null || d === undefined) return T('التاريخ غير معروف', 'Date unknown');
    if (d === 0) return T('ينتهي اليوم', 'Ends today');
    if (d < 0) return T('منتهي من ' + nDays(d), 'Expired ' + nDays(d) + ' ago');
    return T('باقي ' + nDays(d), nDays(d) + ' left');
  }

  function ago(iso) {
    if (!iso) return null;
    var t = Date.parse(iso + (/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? '' : 'Z'));
    if (!isFinite(t)) return null;
    return Math.max(0, Math.round((Date.now() - t) / 60000));
  }

  async function sendForm(path, fd) {
    var r = await fetch(path, { method: 'POST', headers: { 'X-Token': tok() }, body: fd });
    return r.json().catch(function () { return {}; });
  }

  async function blobOpen(path, download) {
    var r = await fetch(path, { headers: { 'X-Token': tok() } });
    if (!r.ok) { toast(T('ما قدرنا نفتح الملف', 'Could not open the file')); return; }
    var b = await r.blob();
    var url = URL.createObjectURL(b);
    if (download) {
      var a = document.createElement('a');
      a.href = url; a.download = download; document.body.appendChild(a); a.click(); a.remove();
    } else {
      window.open(url, '_blank', 'noopener');
    }
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }

  function errText(r) { return (r && (L === 'ar' ? r.error_ar : r.error_en)) || (r && r.error_ar) || T('صار خطأ — جرّب مرة ثانية', 'Something went wrong'); }

  /* ---------- load ---------- */
  async function load(force) {
    css();
    if (S.loading) return;
    S.loading = true;
    if (force || !S.data) putHtml('pmBody', '<div class="empty sk">—</div>');
    try {
      var r = await Promise.all([api('/api/permits/list'), api('/api/permits/months').catch(function () { return null; })]);
      if (!r[0] || !r[0].ok) throw 'bad';
      S.data = r[0];
      S.months = (r[1] && r[1].ok) ? r[1].months : null;
      try { D.permits = { counts: S.data.counts, mode: S.data.mode, last_tick_at: S.data.last_tick_at, ok: true }; buildSideNav(); } catch (_) {}
      render();
    } catch (e) {
      putHtml('pmTop', '');
      putHtml('pmKpis', '');
      putHtml('pmBody', errorState('loadPermits(1)', T('ما قدرنا نجيب التصاريح', 'Could not load permits')));
    }
    S.loading = false;
  }

  /* ---------- render ---------- */
  function render() {
    var d = S.data; if (!d) return;
    Array.prototype.forEach.call(document.querySelectorAll('#view_permits [data-edit]'), function (b) { b.hidden = !d.can_edit; });
    renderTop(d);
    renderKpis(d);
    renderBody(d);
  }

  function renderTop(d) {
    var m = d.mode || {}, h = '';
    var mins = ago(d.last_tick_at);
    var stale = mins === null || mins > 30;
    var beat = '<span class="pm-beat' + (stale ? ' stale' : '') + '"><span class="pm-dot ' + (stale ? 'expired' : 'ok') + '"></span>'
      + esc(mins === null ? T('ما صار فحص للحين', 'No check yet') : T('آخر فحص: قبل ' + mins + ' دقيقة', 'Last check: ' + mins + ' min ago'))
      + (stale && mins !== null ? esc(T(' — المراقب متوقف؟', ' — is the watcher down?')) : '') + '</span>';
    if (m.forced) {
      h += '<div class="pm-banner forced"><div class="t">' + esc(T('التنبيهات موقوفة من Railway (PERMITS_FORCE_DRY=1)', 'Alerts forced off from Railway (PERMITS_FORCE_DRY=1)')) + '</div>'
        + '<div class="s">' + esc(T('مفتاح الطوارئ شغّال — ولا شي يوصل ديسكورد مهما كان الوضع هنا.', 'The emergency switch is on — nothing reaches Discord.')) + '</div>' + beat + '</div>';
    } else if (m.mode === 'dry') {
      var w = arr(d.would_open);
      h += '<div class="pm-banner dry"><div class="t">' + esc(T('التنبيهات متوقفة (وضع التجربة)', 'Alerts are off (dry mode)')) + '</div>'
        + '<div class="s">' + esc(T('لو شغّلتها الحين بينفتح ' + w.length + ' تذكرة تحت «صيانه».', 'Going live now would open ' + w.length + ' ticket(s) under «صيانه».')) + '</div>'
        + beat
        + (d.is_admin ? '<button class="btn primary sm" data-pa="golive">' + esc(T('تشغيل التنبيهات', 'Turn alerts on')) + '</button>' : '');
      if (w.length) {
        h += '<div class="pm-would">' + w.map(function (x) {
          return '<span class="pill muted">' + esc(x.unit) + ' · ' + esc(leftText(x.days_left)) + '</span>';
        }).join('') + '</div>';
      }
      h += '</div>';
    } else {
      h += '<div class="pm-banner"><div class="t">' + esc(T('التنبيهات شغّالة', 'Alerts are live')) + '</div>'
        + '<div class="s">' + esc(T('التذاكر تنفتح تحت «صيانه» عند ' + d.lead_days + ' أيام، والتقرير اليومي الساعة ١ الظهر.', 'Tickets open under «صيانه» at ' + d.lead_days + ' days; daily digest at 1 PM.'))
        + (m.changed_by ? esc(T(' — شغّلها ' + m.changed_by, ' — turned on by ' + m.changed_by)) : '') + '</div>'
        + beat
        + (d.is_admin ? '<button class="btn ghost sm" data-pa="godry">' + esc(T('رجّعها وضع التجربة', 'Back to dry mode')) + '</button>' : '')
        + '</div>';
    }
    putHtml('pmTop', h);
  }

  function kpi(key, val, lbl, cls) {
    var on = S.f.band === key ? ' on' : '';
    return '<button class="kpi pm-kpi' + on + '" data-pa="band" data-v="' + esc(key) + '" aria-pressed="' + (on ? 'true' : 'false') + '">'
      + '<div class="kpi-val ' + (cls || '') + '">' + n(val) + '</div><div class="kpi-lbl">' + esc(lbl) + '</div></button>';
  }

  function renderKpis(d) {
    var c = d.counts || {};
    putHtml('pmKpis',
      kpi('expired', c.expired, T('منتهية', 'Expired'), n(c.expired) ? 'red' : '')
      + kpi('renew', n(c.urgent) + n(c.due), T('تحتاج تجديد (≤' + d.lead_days + ')', 'Renew now (≤' + d.lead_days + ')'), (n(c.urgent) + n(c.due)) ? 'red' : '')
      + kpi('upcoming', c.upcoming, T('قريبة (≤' + d.headsup_days + ')', 'Coming up (≤' + d.headsup_days + ')'), '')
      + kpi('unknown', c.unknown, T('ناقصة بيانات', 'Missing data'), n(c.unknown) ? 'red' : '')
      + kpi('ok', c.ok, T('سليمة', 'Healthy'), 'green')
      + kpi('', c.total, T('المجموع', 'Total'), ''));
  }

  function monthsHtml() {
    var ms = arr(S.months);
    if (!ms.length) return '';
    var max = 1;
    ms.forEach(function (m) { if (m.count > max) max = m.count; });
    var h = '<div class="card"><div class="card-head"><span class="card-title">' + esc(T('الانتهاءات خلال ١٢ شهر', 'Expiries over the next 12 months'))
      + '</span><span class="card-sub">' + esc(T('اضغط الشهر تشوف تصاريحه', 'Tap a month to list it')) + '</span></div><div class="pm-months">';
    ms.forEach(function (m) {
      var pct = Math.round(m.count / max * 72);
      var tip = m.items.map(function (x) { return x.unit + ' — ' + x.end_date; }).join(' · ');
      h += '<button class="pm-m' + (m.count ? ' has' : '') + (S.monthOpen === m.key ? ' on' : '') + '" data-pa="month" data-v="' + esc(m.key) + '" title="' + esc(tip) + '" aria-label="' + esc(m.label_ar + ' ' + m.year + ': ' + m.count) + '">'
        + '<span class="c">' + (m.count || '') + '</span><span class="b" style="height:' + Math.max(3, pct) + 'px"></span>'
        + '<span class="l">' + esc(L === 'ar' ? m.label_ar : m.key.slice(5) + '/' + String(m.year).slice(2)) + '</span></button>';
    });
    h += '</div>';
    var open = ms.filter(function (m) { return m.key === S.monthOpen; })[0];
    if (open) {
      h += '<div class="pm-mlist">' + (open.items.length ? open.items.map(function (x) {
        return '<button class="pill muted" data-pa="open" data-id="' + n(x.id) + '">' + esc(x.unit) + ' · ' + esc(x.end_date) + '</button>';
      }).join('') : esc(T('ما فيه انتهاءات بهالشهر', 'Nothing ends this month'))) + '</div>';
    }
    return h + '</div>';
  }

  function matches(r) {
    var f = S.f;
    if (f.band === 'renew' && r.band !== 'due' && r.band !== 'urgent') return false;
    if (f.band && f.band !== 'renew' && r.band !== f.band) return false;
    if (f.type && r.permit_type !== f.type) return false;
    if (f.scope && r.scope !== f.scope) return false;
    if (f.q) {
      var q = f.q.toLowerCase();
      var hay = [r.permit_type, r.permit_no, r.unit, r.unit_text, r.building, r.district, r.holder].join(' ').toLowerCase();
      if (hay.indexOf(q) < 0) return false;
    }
    return true;
  }

  function ticketCell(r, d) {
    var t = r.ticket;
    if (t) {
      var lbl = '#' + String(t.id).padStart(3, '0');
      if (t.url) return '<a href="' + esc(t.url) + '" target="_blank" rel="noopener" data-pa="stop">' + esc(lbl) + '</a>';
      if (t.last_error) return '<span class="pm-chip bad" title="' + esc(t.last_error) + '">' + esc(lbl + ' ' + T('تعذّر الفتح — يعيد المحاولة', 'failed — retrying')) + '</span>';
      return esc(lbl + ' ' + T('(قيد الفتح)', '(opening)'));
    }
    if (r.band === 'unknown') return '<span class="pm-sub">' + esc(T('كمّل التاريخ', 'Fill the date')) + '</span>';
    if (r.opens_in > 0) return '<span class="pm-sub">' + esc(T('تنفتح بعد ' + nDays(r.opens_in), 'Opens in ' + nDays(r.opens_in))) + '</span>';
    if ((d.mode || {}).mode !== 'live') return '<span class="pill warn">' + esc(T('وضع التجربة', 'Dry mode')) + '</span>';
    return '<span class="pm-sub">' + esc(T('تنفتح بأقرب فحص', 'Opens on the next check')) + '</span>';
  }

  function unitCell(r) {
    var h = '<span class="strong">' + esc(r.unit) + '</span>';
    if (r.scope === 'unit' && !r.linked) h += '<span class="pm-chip warn">' + esc(T('غير مربوطة', 'Not linked')) + '</span>';
    if (r.listing_active === false) h += '<span class="pm-chip bad">' + esc(T('الشقة غير نشطة', 'Unit inactive')) + '</span>';
    if (r.review_open) h += '<span class="pm-chip warn">' + esc(T('تحتاج مراجعة', 'Needs review')) + '</span>';
    return h;
  }

  function renderBody(d) {
    var rows = arr(d.rows);
    var tools = '<div class="pm-filters">'
      + '<input id="pmQ" type="search" placeholder="' + esc(T('ابحث: النوع، الرقم، الشقة، المبنى…', 'Search: type, number, unit, building…')) + '" value="' + esc(S.f.q) + '" aria-label="' + esc(T('بحث', 'Search')) + '">'
      + '<select id="pmType" aria-label="' + esc(T('النوع', 'Type')) + '"><option value="">' + esc(T('كل الأنواع', 'All types')) + '</option>'
      + uniq(rows.map(function (r) { return r.permit_type; })).map(function (x) { return '<option' + (S.f.type === x ? ' selected' : '') + '>' + esc(x) + '</option>'; }).join('') + '</select>'
      + '<select id="pmScope" aria-label="' + esc(T('النطاق', 'Scope')) + '"><option value="">' + esc(T('كل النطاقات', 'All scopes')) + '</option>'
      + [['unit', 'شقة', 'Unit'], ['building', 'مبنى', 'Building'], ['company', 'الشركة', 'Company'], ['other', 'أخرى', 'Other']].map(function (s) {
        return '<option value="' + s[0] + '"' + (S.f.scope === s[0] ? ' selected' : '') + '>' + esc(T(s[1], s[2])) + '</option>';
      }).join('') + '</select></div>';
    if (!rows.length) {
      putHtml('pmBody', monthsHtml() + emptyState(T('ما فيه تصاريح مسجّلة', 'No permits yet'),
        T('أضف تصريح أو استورد ملف من الأزرار فوق.', 'Add a permit or import a file using the buttons above.'), '📄'));
      return;
    }
    var shown = rows.filter(matches);
    var head = ['', T('النوع', 'Type'), T('الرقم', 'Number'), T('الشقة/المبنى', 'Unit / building'), T('جهة الإصدار', 'Issuer'),
      T('البداية', 'Start'), T('النهاية', 'End'), T('المتبقي', 'Left'), T('التذكرة', 'Ticket'), T('المسؤول', 'Owner')];
    var h = monthsHtml() + '<div class="card">' + tools
      + '<div class="pm-wrap"><table class="data pm-t"><thead><tr>' + head.map(function (x, i) { return '<th' + (i === 4 || i === 5 ? ' class="pm-md"' : '') + '>' + esc(x) + '</th>'; }).join('') + '</tr></thead><tbody>';
    shown.forEach(function (r) {
      h += '<tr class="pm-r" data-pa="open" data-id="' + n(r.id) + '" tabindex="0">'
        + '<td data-l="' + esc(T('الحالة', 'Status')) + '">' + bandPill(r.band) + '</td>'
        + '<td data-l="' + esc(head[1]) + '" class="pm-type" title="' + esc(r.permit_type) + '">' + esc(r.type_short || r.permit_type) + '</td>'
        + '<td data-l="' + esc(head[2]) + '" class="pm-num">' + esc(r.permit_no || '—') + '</td>'
        + '<td data-l="' + esc(head[3]) + '">' + unitCell(r) + '</td>'
        + '<td data-l="' + esc(head[4]) + '" class="pm-md">' + esc(r.issuer || '—') + '</td>'
        + '<td data-l="' + esc(head[5]) + '" class="pm-num pm-md">' + esc(r.start_date || '—') + '</td>'
        + '<td data-l="' + esc(head[6]) + '" class="pm-num">' + esc(r.end_date || (r.end_date_raw ? '«' + r.end_date_raw + '»' : '—'))
        + (r.end_hijri ? '<span class="pm-sub">' + esc(r.end_hijri) + '</span>' : '') + '</td>'
        + '<td data-l="' + esc(head[7]) + '"><span class="pm-left ' + esc(r.band) + '">' + esc(leftText(r.days_left)) + '</span></td>'
        + '<td data-l="' + esc(head[8]) + '">' + ticketCell(r, d) + '</td>'
        + '<td data-l="' + esc(head[9]) + '">' + esc(r.responsible || '—') + '</td></tr>';
    });
    h += '</tbody></table></div>';
    if (!shown.length) h += '<div class="empty" style="margin-top:10px">' + esc(T('ما فيه نتائج لهالفلتر', 'Nothing matches this filter')) + '</div>';
    h += '<div class="pm-sub" style="margin-top:8px">' + esc(T(shown.length + ' من ' + rows.length, shown.length + ' of ' + rows.length)) + '</div></div>';
    putHtml('pmBody', h);
  }

  function uniq(a) { var o = []; a.forEach(function (x) { if (x && o.indexOf(x) < 0) o.push(x); }); return o; }

  /* ---------- the drawer ---------- */
  async function openItem(id, view) {
    S.view = view || 'detail';
    openDrawer(T('جاري التحميل…', 'Loading…'), '');
    setDrawerBody('<div class="empty sk">—</div>'); setDrawerFoot('');
    var r = await api('/api/permits/item?id=' + n(id)).catch(function () { return null; });
    if (!r || !r.ok) { setDrawerBody('<div class="empty">' + esc(errText(r)) + '</div>'); return; }
    S.item = r;
    renderItem();
  }

  function kv(k, v) { return '<div class="k">' + esc(k) + '</div><div class="v">' + (v === '' || v === null || v === undefined ? '—' : v) + '</div>'; }

  var EV = {
    seeded: ['انضاف من البذرة', 'Seeded'], imported: ['انضاف من الاستيراد', 'Imported'], created: ['انضاف يدوياً', 'Created'],
    linked: ['انربط بشقة', 'Linked to a unit'], ticket_queued: ['تذكرة بالطابور', 'Ticket queued'], ticket_opened: ['انفتحت التذكرة', 'Ticket opened'],
    ticket_adopted: ['انربطت تذكرة موجودة', 'Existing ticket adopted'], ticket_lost: ['انحذفت روم التذكرة', 'Ticket room deleted'],
    ticket_closed: ['انقفلت التذكرة', 'Ticket closed'], claimed: ['أحد استلمها', 'Claimed'], renewed: ['تجدّد', 'Renewed'],
    renewal_created: ['دورة جديدة', 'New term'], cancelled: ['لن يُجدَّد', 'Won’t renew'], corrected: ['تصحيح تاريخ', 'Date corrected'],
    edited: ['تعديل', 'Edited'], doc_uploaded: ['رفع مستند', 'Document uploaded'], review_cleared: ['تمت المراجعة', 'Reviewed'],
    import_update: ['تحديث من الاستيراد', 'Updated by import'], mode_changed: ['تغيير الوضع', 'Mode changed']
  };

  function renderItem() {
    var r = S.item; if (!r) return;
    var p = r.permit, row = r.row;
    openDrawer(row.unit, (row.type_short || p.permit_type) + (p.permit_no ? ' · #' + p.permit_no : '') + ' · ' + leftText(row.days_left));
    if (S.view === 'edit') return renderEdit(p);
    if (S.view === 'renew') return renderRenew(p);
    if (S.view === 'cancel') return renderCancel(p);
    var h = '<div style="margin-bottom:12px">' + bandPill(row.band) + '</div>';
    arr(p.review_issues).forEach(function (it) {
      if (it.cleared_at) return;
      h += '<div class="pm-issue"><b>' + esc(T('تحتاج مراجعة: ', 'Needs review: ')) + '</b>' + esc(it.text_ar || it.code)
        + (r.is_admin ? '<div style="display:flex;gap:6px;margin-top:8px"><input id="pmRv_' + esc(it.code) + '" placeholder="' + esc(T('وش طلع الصح؟ (ملاحظة المراجعة)', 'What is correct? (review note)')) + '" style="flex:1;padding:7px 9px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--text);font:inherit;font-size:12.5px">'
          + '<button class="btn ghost sm" data-pa="review" data-v="' + esc(it.code) + '">' + esc(T('تمت المراجعة', 'Reviewed')) + '</button></div>' : '') + '</div>';
    });
    if (row.scope === 'unit' && !row.linked) {
      h += '<div class="pm-issue">' + esc(T('هذا التصريح غير مربوط بشقة في Hostaway — اربطه عشان يعرف النظام مين مسؤول الصيانة.', 'Not linked to a Hostaway unit — link it so the maintenance owner is known.')) + '</div>';
    }
    h += '<div class="pm-kv">'
      + kv(T('النوع', 'Type'), esc(p.permit_type))
      + kv(T('الرقم', 'Number'), esc(p.permit_no))
      + kv(T('الشقة/المبنى', 'Unit / building'), esc(row.unit) + (p.unit_text && p.unit_text !== row.unit ? '<span class="pm-sub">' + esc(T('بالملف: ', 'In the file: ') + p.unit_text) + '</span>' : ''))
      + kv(T('جهة الإصدار', 'Issuer'), esc(row.issuer))
      + kv(T('باسم', 'Holder'), esc(p.holder) + (p.holder_id_masked ? '<span class="pm-sub">' + esc(T('الهوية: ', 'ID: ') + p.holder_id_masked) + '</span>' : ''))
      + kv(T('العنوان', 'Address'), esc([p.district, p.street, p.building_no ? T('مبنى ', 'bldg ') + p.building_no : '', p.unit_no ? T('وحدة ', 'unit ') + p.unit_no : ''].filter(Boolean).join(' · ')))
      + kv(T('نوع العقار', 'Ownership'), esc(p.ownership_kind))
      + kv(T('البداية', 'Start'), esc(p.start_date || '') + (p.start_date_raw ? '<span class="pm-sub">' + esc(T('كما كُتب: ', 'As written: ') + p.start_date_raw) + '</span>' : '') + (p.start_hijri ? '<span class="pm-sub">' + esc(p.start_hijri) + '</span>' : ''))
      + kv(T('النهاية', 'End'), esc(p.end_date || '') + (p.end_date_raw ? '<span class="pm-sub">' + esc(T('كما كُتب: ', 'As written: ') + p.end_date_raw) + '</span>' : '') + (row.end_hijri ? '<span class="pm-sub">' + esc(row.end_hijri) + '</span>' : ''))
      + kv(T('المتبقي', 'Left'), '<span class="pm-left ' + esc(row.band) + '">' + esc(leftText(row.days_left)) + '</span>')
      + kv(T('التنبيه قبل', 'Alert at'), esc(nDays(row.lead)))
      + kv(T('المسؤول', 'Responsible'), esc(row.responsible))
      + kv(T('التكلفة', 'Cost'), p.cost_sar !== null && p.cost_sar !== undefined && p.cost_sar !== '' ? esc(n(p.cost_sar).toLocaleString('en-US') + ' ' + T('ر.س', 'SAR')) : '')
      + kv(T('طريقة التجديد', 'How to renew'), esc(p.renew_notes || p.renew_notes_default || ''))
      + kv(T('ملاحظات', 'Notes'), esc(p.notes));
    var ex = p.extra || {};
    Object.keys(ex).forEach(function (k) { h += kv(k, esc(ex[k])); });
    h += '</div>';
    h += '<div class="pm-row-actions">';
    if (p.doc_url) h += '<a class="btn ghost sm" href="' + esc(p.doc_url) + '" target="_blank" rel="noopener">' + esc(T('افتح التصريح', 'Open the permit')) + '</a>';
    if (p.has_doc) h += '<button class="btn ghost sm" data-pa="doc">' + esc(T('المستند المرفوع', 'Uploaded document')) + '</button>';
    var t = row.ticket;
    if (t && t.url) h += '<a class="btn ghost sm" href="' + esc(t.url) + '" target="_blank" rel="noopener">' + esc(T('افتح التذكرة #', 'Open ticket #') + String(t.id).padStart(3, '0')) + '</a>';
    h += '</div>';
    if (r.can_edit) {
      var opts = '<option value="">' + esc(T('— بدون ربط —', '— not linked —')) + '</option>' + arr((S.data || {}).listings).map(function (l) {
        return '<option value="' + n(l.id) + '"' + (n(l.id) === n(p.listing_id) ? ' selected' : '') + '>' + esc(l.name) + '</option>';
      }).join('');
      h += '<div class="wf-fld"><label for="pmLink">' + esc(T('اربطها بشقة', 'Link to a unit')) + '</label>'
        + '<input id="pmLinkQ" type="search" placeholder="' + esc(T('دوّر بالاسم…', 'Filter by name…')) + '" style="margin-bottom:6px">'
        + '<select id="pmLink" style="width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);font:inherit">' + opts + '</select>'
        + '<button class="btn ghost sm" style="margin-top:6px" data-pa="link">' + esc(T('احفظ الربط', 'Save link')) + '</button></div>';
      h += '<div class="wf-fld"><label for="pmDocFile">' + esc(T('رفع مستند (PDF أو صورة)', 'Upload a document (PDF or image)')) + '</label>'
        + '<input id="pmDocFile" type="file" accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,application/pdf,image/*">'
        + '<button class="btn ghost sm" style="margin-top:6px" data-pa="upload">' + esc(T('ارفع', 'Upload')) + '</button></div>';
    }
    var chain = arr(r.chain);
    if (chain.length > 1) {
      h += '<div class="pm-sec">' + esc(T('دورات التصريح (الأحدث أول)', 'Terms (newest first)')) + '</div>';
      chain.forEach(function (c) {
        h += '<div class="pm-ev">' + esc((c.permit_no || '—') + ' · ' + (c.start_date || '…') + ' → ' + (c.end_date || '…')) + ' <span class="pill muted">' + esc(c.status) + '</span></div>';
      });
    }
    var evs = arr(r.events);
    if (evs.length) {
      h += '<div class="pm-sec">' + esc(T('السجل', 'History')) + '</div>';
      evs.slice(0, 30).forEach(function (e) {
        var lb = EV[e.kind] || [e.kind, e.kind];
        var extra = e.payload && (e.payload.reason || e.payload.note || e.payload.new_end || e.payload.mode || '');
        h += '<div class="pm-ev">' + esc(T(lb[0], lb[1])) + (extra ? ' — ' + esc(extra) : '') + '<div class="w">' + esc((e.at || '').replace('T', ' ').slice(0, 16) + ' UTC · ' + (e.actor || '')) + '</div></div>';
      });
    }
    setDrawerBody(h);
    var foot = '<button class="btn ghost" data-pa="close">' + esc(T('إغلاق', 'Close')) + '</button>';
    if (r.can_edit && p.status === 'active') {
      foot += '<button class="btn ghost" data-pa="view" data-v="edit">' + esc(T('تعديل', 'Edit')) + '</button>';
      if (r.is_admin) foot += '<button class="btn ghost" data-pa="view" data-v="cancel">' + esc(T('لن يُجدَّد', 'Won’t renew')) + '</button>';
      foot += '<button class="btn primary" data-pa="view" data-v="renew">' + esc(T('تجديد', 'Renew')) + '</button>';
    }
    setDrawerFoot(foot);
    wireLinkFilter();
  }

  function wireLinkFilter() {
    var q = document.getElementById('pmLinkQ'), sel = document.getElementById('pmLink');
    if (!q || !sel) return;
    q.addEventListener('input', function () {
      var v = q.value.trim().toLowerCase();
      Array.prototype.forEach.call(sel.options, function (o, i) { if (i) o.hidden = v && o.textContent.toLowerCase().indexOf(v) < 0; });
    });
  }

  function fld(id, label, value, opts) {
    opts = opts || {};
    var input = opts.area
      ? '<textarea id="' + id + '" rows="' + (opts.rows || 3) + '">' + esc(value || '') + '</textarea>'
      : '<input id="' + id + '" type="' + (opts.type || 'text') + '" value="' + esc(value === null || value === undefined ? '' : value) + '"'
        + (opts.list ? ' list="' + opts.list + '"' : '') + (opts.ph ? ' placeholder="' + esc(opts.ph) + '"' : '') + (opts.date ? ' data-date="1"' : '') + '>';
    return '<div class="wf-fld"><label for="' + id + '">' + esc(label) + '</label>' + input
      + (opts.date ? '<div class="pm-preview" id="' + id + '_pv"></div>' : '') + (opts.hint ? '<div class="pm-sub">' + esc(opts.hint) + '</div>' : '') + '</div>';
  }

  function typeList() {
    return '<datalist id="pmTypes">' + arr((S.data || {}).type_suggestions).map(function (x) { return '<option value="' + esc(x) + '">'; }).join('') + '</datalist>';
  }

  var DATE_PH = '2027-10-11 · 11/10/2027 · 01/05/1449';

  function formHtml(p, isNew) {
    p = p || {};
    return '<div id="pmFormErr"></div>' + typeList()
      + fld('pf_type', T('نوع التصريح', 'Permit type'), p.permit_type || '', { list: 'pmTypes' })
      + fld('pf_no', T('رقم التصريح', 'Permit number'), p.permit_no)
      + fld('pf_unit', T('الشقة / الوحدة (كما تكتبونها)', 'Unit (as you write it)'), p.unit_text)
      + fld('pf_building', T('المبنى (لو التصريح للمبنى)', 'Building (if building-level)'), p.building)
      + fld('pf_issuer', T('جهة الإصدار', 'Issuer'), p.issuer)
      + fld('pf_holder', T('باسم (صاحب التصريح)', 'Issued to'), p.holder)
      + fld('pf_start', T('تاريخ البداية', 'Start date'), p.start_date_raw || p.start_date, { date: 1, ph: DATE_PH })
      + fld('pf_end', T('تاريخ الانتهاء', 'End date'), p.end_date_raw || p.end_date, { date: 1, ph: DATE_PH })
      + (isNew ? '' : fld('pf_reason', T('سبب تغيير تاريخ الانتهاء (مطلوب لو تغيّر)', 'Reason for changing the end date (required if it changes)'), ''))
      + fld('pf_lead', T('أيام التنبيه قبل الانتهاء (فاضي = ١٠)', 'Alert days before expiry (blank = 10)'), p.lead_days, { type: 'number' })
      + fld('pf_cost', T('التكلفة (ر.س)', 'Cost (SAR)'), p.cost_sar, { type: 'number' })
      + fld('pf_resp', T('المسؤول (فاضي = مسؤول صيانة الشقة)', 'Responsible (blank = the unit’s maintenance owner)'), p.responsible_name)
      + fld('pf_resp_id', T('رقم ديسكورد للمسؤول (اختياري)', 'Responsible Discord id (optional)'), p.responsible_discord_id)
      + fld('pf_renew', T('طريقة التجديد', 'How to renew'), p.renew_notes, { area: 1, rows: 2 })
      + fld('pf_notes', T('ملاحظات', 'Notes'), p.notes, { area: 1 });
  }

  function val(id) { var e = document.getElementById(id); return e ? e.value.trim() : ''; }

  function formPayload() {
    return { permit_type: val('pf_type'), permit_no: val('pf_no'), unit_text: val('pf_unit'), building: val('pf_building'),
      issuer: val('pf_issuer'), holder: val('pf_holder'), start_date: val('pf_start'), end_date: val('pf_end'),
      lead_days: val('pf_lead'), cost_sar: val('pf_cost'), responsible_name: val('pf_resp'),
      responsible_discord_id: val('pf_resp_id'), renew_notes: val('pf_renew'), notes: val('pf_notes') };
  }

  function showErr(r) { putHtml('pmFormErr', '<div class="pm-err">' + esc(errText(r)) + '</div>'); }

  function renderEdit(p) {
    setDrawerBody(formHtml(p, false));
    setDrawerFoot('<button class="btn ghost" data-pa="view" data-v="detail">' + esc(T('رجوع', 'Back')) + '</button>'
      + '<button class="btn primary" data-pa="save">' + esc(T('حفظ', 'Save')) + '</button>');
    wireDates();
  }

  function renderNew() {
    S.item = null;
    openDrawer(T('تصريح جديد', 'New permit'), T('يتسجّل ويتابعه النظام من اليوم', 'It is tracked from today'));
    setDrawerBody(formHtml({ permit_type: '' }, true));
    setDrawerFoot('<button class="btn ghost" data-pa="close">' + esc(T('إلغاء', 'Cancel')) + '</button>'
      + '<button class="btn primary" data-pa="create">' + esc(T('أضف', 'Add')) + '</button>');
    wireDates();
  }

  function renderRenew(p) {
    var h = '<div id="pmFormErr"></div>'
      + '<div class="pm-sub" style="margin-bottom:12px">' + esc(T('ينتهي الحالي: ', 'Current end: ') + (p.end_date || '—')) + '</div>'
      + fld('rn_end', T('تاريخ الانتهاء الجديد', 'New end date'), '', { date: 1, ph: DATE_PH })
      + fld('rn_start', T('تاريخ البداية الجديد (اختياري)', 'New start date (optional)'), '', { date: 1, ph: DATE_PH })
      + fld('rn_no', T('رقم التصريح الجديد (فاضي = نفس الرقم)', 'New permit number (blank = same)'), '')
      + fld('rn_notes', T('ملاحظات', 'Notes'), '', { area: 1, rows: 2 })
      + '<div class="wf-fld"><label for="rn_file">' + esc(T('مستند التصريح المجدَّد (مطلوب)', 'Renewed permit document (required)')) + '</label>'
      + '<input id="rn_file" type="file" accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,application/pdf,image/*"></div>'
      + (S.item && S.item.is_admin ? fld('rn_override', T('أو: سبب التجاوز بدون مستند (للمدير)', 'Or: admin override reason (no document)'), '') : '')
      + '<div class="pm-sub">' + esc(T('بعد الحفظ تنقفل التذكرة في ديسكورد خلال دقائق وتبدأ دورة جديدة.', 'After saving, the Discord ticket closes within minutes and a new term begins.')) + '</div>';
    setDrawerBody(h);
    setDrawerFoot('<button class="btn ghost" data-pa="view" data-v="detail">' + esc(T('رجوع', 'Back')) + '</button>'
      + '<button class="btn primary" data-pa="renew">' + esc(T('سجّل التجديد', 'Record renewal')) + '</button>');
    wireDates();
  }

  function renderCancel(p) {
    setDrawerBody('<div id="pmFormErr"></div><div class="pm-issue">'
      + esc(T('«لن يُجدَّد» يوقف متابعة هذا التصريح نهائياً ويقفل تذكرته. استخدمه بس إذا فعلاً ما نبي نجدده (مثلاً الشقة طلعت من عوجا).', '«Won’t renew» stops tracking this permit for good and closes its ticket. Only use it when we really will not renew.'))
      + '</div>' + fld('cn_reason', T('السبب (٥ إلى ٤٠٠ حرف)', 'Reason (5–400 characters)'), '', { area: 1 }));
    setDrawerFoot('<button class="btn ghost" data-pa="view" data-v="detail">' + esc(T('رجوع', 'Back')) + '</button>'
      + '<button class="btn primary" data-pa="cancel">' + esc(T('تأكيد: لن يُجدَّد', 'Confirm: won’t renew')) + '</button>');
  }

  function wireDates() {
    Array.prototype.forEach.call(document.querySelectorAll('#drwBody input[data-date]'), function (inp) {
      inp.addEventListener('input', function () { previewDate(inp); });
      if (inp.value) previewDate(inp);
    });
  }

  function previewDate(inp) {
    var out = document.getElementById(inp.id + '_pv'); if (!out) return;
    clearTimeout(inp._t);
    var v = inp.value.trim();
    if (!v) { out.textContent = ''; out.className = 'pm-preview'; return; }
    inp._t = setTimeout(async function () {
      var r = await api('/api/permits/parse-date?v=' + encodeURIComponent(v)).catch(function () { return null; });
      if (!r || !r.ok || inp.value.trim() !== v) return;
      if (!r.iso) { out.className = 'pm-preview bad'; out.textContent = T('ما قدرنا نقرأ هالتاريخ', 'Could not read this date'); return; }
      var txt = r.words + (r.hijri ? ' · ' + r.hijri : '') + ' — ' + leftText(r.days_left);
      if (r.issue === 'ambiguous_day_month') txt += ' · ' + T('(قرأناه يوم/شهر — تأكد)', '(read as day/month — check)');
      out.className = 'pm-preview';
      out.textContent = txt;
      var warn = '';
      var s = document.getElementById('pf_start'), e = document.getElementById('pf_end');
      if (inp.id === 'pf_end' || inp.id === 'rn_end') {
        if (r.days_left !== null && r.days_left > 5 * 366) warn = T('تنبيه: الانتهاء بعد أكثر من ٥ سنين — متأكد؟', 'Heads-up: more than 5 years away — sure?');
      }
      if (s && e && s.value && e.value && inp.id === 'pf_end') {
        var rs = await api('/api/permits/parse-date?v=' + encodeURIComponent(s.value.trim())).catch(function () { return null; });
        if (rs && rs.iso && r.iso < rs.iso) warn = T('تنبيه: الانتهاء قبل البداية', 'Heads-up: the end is before the start');
      }
      if (warn) out.innerHTML = esc(txt) + '<div class="pm-warn">' + esc(warn) + '</div>';
    }, 300);
  }

  /* ---------- import ---------- */
  function renderImport() {
    S.imp = { file: null, preview: null, decisions: {}, source: 'file' };
    openDrawer(T('استيراد تصاريح', 'Import permits'), T('ملف CSV أو Excel أو JSON — ما ينحفظ شي قبل ما تضغط «استيراد»', 'CSV, Excel or JSON — nothing is stored until you press Import'));
    setDrawerBody('<div id="pmFormErr"></div>' + typeList()
      + fld('im_type', T('النوع الافتراضي (للصفوف بدون نوع)', 'Default type (rows without a type)'), (S.data && S.data.type_suggestions || [''])[0], { list: 'pmTypes' })
      + '<div class="wf-fld"><label for="im_file">' + esc(T('الملف', 'File')) + '</label><input id="im_file" type="file" accept=".csv,.xlsx,.json,text/csv,application/json"></div>'
      + '<div class="pm-row-actions"><button class="btn ghost sm" data-pa="imp-file">' + esc(T('اعرض المعاينة', 'Preview')) + '</button>'
      + '<button class="btn ghost sm" data-pa="imp-onb">' + esc(T('من مشاريع التشغيل', 'From onboarding projects')) + '</button></div>'
      + '<div id="pmImp"></div>');
    setDrawerFoot('<button class="btn ghost" data-pa="close">' + esc(T('إغلاق', 'Close')) + '</button>');
  }

  function impForm(extra) {
    var fd = new FormData();
    fd.append('source', S.imp.source);
    fd.append('default_type', val('im_type'));
    if (S.imp.file) fd.append('file', S.imp.file, S.imp.file.name);
    Object.keys(extra || {}).forEach(function (k) { fd.append(k, extra[k]); });
    return fd;
  }

  async function impPreview(source) {
    S.imp.source = source;
    if (source === 'file') {
      var f = document.getElementById('im_file');
      S.imp.file = f && f.files && f.files[0] ? f.files[0] : null;
      if (!S.imp.file) { showErr({ error_ar: 'اختر ملف أول', error_en: 'Pick a file first' }); return; }
    } else { S.imp.file = null; }
    putHtml('pmFormErr', '');
    putHtml('pmImp', '<div class="empty sk">—</div>');
    var r = await sendForm('/api/permits/import/preview', impForm());
    if (!r || !r.ok) { putHtml('pmImp', ''); showErr(r); return; }
    S.imp.preview = r.preview;
    S.imp.decisions = {};
    renderImpPreview();
  }

  function renderImpPreview() {
    var pv = S.imp.preview, rows = arr(pv.rows);
    var news = rows.filter(function (x) { return !x.exists_id; }).length;
    var h = '<div class="pm-sub" style="margin:10px 0">' + esc(T('الصف ' + pv.header_row + ' هو العناوين · ' + rows.length + ' صف · جديد ' + news + ' · موجود ' + (rows.length - news),
      'Header row ' + pv.header_row + ' · ' + rows.length + ' rows · new ' + news + ' · existing ' + (rows.length - news))) + '</div>'
      + '<div class="pm-wrap"><table class="data pm-imp"><thead><tr><th>#</th><th>' + esc(T('الشقة', 'Unit')) + '</th><th>' + esc(T('الرقم', 'Number')) + '</th><th>'
      + esc(T('النهاية', 'End')) + '</th><th>' + esc(T('ملاحظات', 'Issues')) + '</th><th></th></tr></thead><tbody>';
    rows.forEach(function (x) {
      var cls = x.needs_data ? 'bad' : ((x.issues || []).length || x.exists_id ? 'dup' : '');
      var iss = arr(x.issues).map(function (i) { return i.text_ar; });
      if (x.exists_id) iss.unshift(T('موجود', 'Exists'));
      h += '<tr class="' + cls + '"><td>' + n(x.serial || x.row_index) + '</td><td>' + esc(x.unit_text || x.building || '—') + '</td><td class="pm-num">' + esc(x.permit_no || '—') + '</td>'
        + '<td>' + esc(x.end_date || ('«' + (x.end_date_raw || '') + '»')) + '<span class="pm-sub">' + esc((x.preview || {}).end_words || '') + ((x.preview || {}).end_hijri ? ' · ' + esc(x.preview.end_hijri) : '') + '</span></td>'
        + '<td>' + esc(iss.join(' · ')) + '</td><td>'
        + (x.exists_id ? '<label class="pm-sub"><input type="checkbox" data-pa="imp-upd" data-v="' + n(x.row_index) + '"> ' + esc(T('حدّث الموجود', 'Update existing')) + '</label>' : '')
        + '</td></tr>';
    });
    h += '</tbody></table></div>';
    putHtml('pmImp', h);
    setDrawerFoot('<button class="btn ghost" data-pa="close">' + esc(T('إغلاق', 'Close')) + '</button>'
      + '<button class="btn primary" data-pa="imp-commit">' + esc(T('استيراد ' + news, 'Import ' + news)) + '</button>');
  }

  async function impCommit() {
    var r = await sendForm('/api/permits/import/commit', impForm({ decisions: JSON.stringify(S.imp.decisions) }));
    if (!r || !r.ok) { showErr(r); return; }
    setDrawerBody('<div class="pm-issue" style="background:var(--green-soft)">' + esc(T(
      'انضاف ' + r.inserted + ' · تحدّث ' + r.updated + ' · تخطّينا ' + r.skipped + (r.needs_data ? ' · ناقصة بيانات ' + r.needs_data : ''),
      'Added ' + r.inserted + ' · updated ' + r.updated + ' · skipped ' + r.skipped + (r.needs_data ? ' · missing data ' + r.needs_data : ''))) + '</div>');
    setDrawerFoot('<button class="btn primary" data-pa="close">' + esc(T('تمام', 'Done')) + '</button>');
    load(1);
  }

  /* ---------- actions (one delegated listener) ---------- */
  async function act(el, ev) {
    var a = el.getAttribute('data-pa'), v = el.getAttribute('data-v'), id = el.getAttribute('data-id');
    var it = S.item, pid = it && it.permit ? it.permit.id : null;
    if (a === 'stop') { ev.stopPropagation(); return; }
    if (a === 'band') { S.f.band = (S.f.band === v ? '' : v); renderKpis(S.data); renderBody(S.data); return; }
    if (a === 'month') { S.monthOpen = (S.monthOpen === v ? '' : v); renderBody(S.data); return; }
    if (a === 'open') { openItem(id); return; }
    if (a === 'close') { closeDrawer(); return; }
    if (a === 'view') { S.view = v; renderItem(); return; }
    if (a === 'new') { renderNew(); return; }
    if (a === 'import') { renderImport(); return; }
    if (a === 'export') { blobOpen('/api/permits/export.csv', 'permits.csv'); return; }
    if (a === 'doc') { blobOpen('/api/permits/doc?id=' + n(pid)); return; }
    if (a === 'imp-file') { impPreview('file'); return; }
    if (a === 'imp-onb') { impPreview('onboarding'); return; }
    if (a === 'imp-upd') { if (el.checked) S.imp.decisions[v] = 'update'; else delete S.imp.decisions[v]; return; }
    if (a === 'imp-commit') { el.disabled = true; await impCommit(); el.disabled = false; return; }
    if (a === 'golive') { goLive(); return; }
    if (a === 'golive-confirm') { el.disabled = true; await goLiveConfirm(); el.disabled = false; return; }
    if (a === 'godry') {
      var rd = await post('/api/permits/mode', { mode: 'dry' });
      toast(rd && rd.ok ? T('رجع وضع التجربة', 'Back to dry mode') : errText(rd)); load(1); return;
    }
    el.disabled = true;
    try {
      var r;
      if (a === 'create') {
        r = await post('/api/permits/create', formPayload());
        if (r && r.ok) { toast(T('انضاف ✓', 'Added ✓')); closeDrawer(); load(1); openItem(r.id); } else showErr(r);
      } else if (a === 'save') {
        var b = formPayload(); b.id = pid; b.reason = val('pf_reason');
        r = await post('/api/permits/update', b);
        if (r && r.ok) { toast(r.ticket_closed ? T('انحفظ — والتذكرة بتنقفل في ديسكورد خلال دقائق', 'Saved — the Discord ticket closes within minutes') : T('انحفظ ✓', 'Saved ✓')); load(1); openItem(pid); } else showErr(r);
      } else if (a === 'renew') {
        var fd = new FormData();
        fd.append('id', pid); fd.append('end_date', val('rn_end')); fd.append('start_date', val('rn_start'));
        fd.append('permit_no', val('rn_no')); fd.append('notes', val('rn_notes')); fd.append('override_reason', val('rn_override'));
        var f = document.getElementById('rn_file');
        if (f && f.files && f.files[0]) fd.append('file', f.files[0], f.files[0].name);
        r = await sendForm('/api/permits/renew', fd);
        if (r && r.ok) { toast(T('تجدّد ✓ — ديسكورد بيتحدّث خلال دقائق', 'Renewed ✓ — Discord updates within minutes')); load(1); openItem(r.new_id); } else showErr(r);
      } else if (a === 'cancel') {
        r = await post('/api/permits/cancel', { id: pid, reason: val('cn_reason') });
        if (r && r.ok) { toast(T('انحفظ — لن يُجدَّد', 'Saved — won’t renew')); closeDrawer(); load(1); } else showErr(r);
      } else if (a === 'link') {
        r = await post('/api/permits/link', { id: pid, listing_id: val('pmLink') });
        if (r && r.ok) { toast(T('انحفظ الربط ✓', 'Link saved ✓')); load(1); openItem(pid); } else toast(errText(r));
      } else if (a === 'upload') {
        var df = document.getElementById('pmDocFile');
        if (!df || !df.files || !df.files[0]) { toast(T('اختر ملف أول', 'Pick a file first')); return; }
        var fu = new FormData(); fu.append('id', pid); fu.append('file', df.files[0], df.files[0].name);
        r = await sendForm('/api/permits/doc-upload', fu);
        if (r && r.ok) { toast(T('انرفع ✓', 'Uploaded ✓')); openItem(pid); } else toast(errText(r));
      } else if (a === 'review') {
        var note = val('pmRv_' + v);
        if (note.length < 3) { toast(T('اكتب ملاحظة المراجعة أول', 'Write the review note first')); return; }
        r = await post('/api/permits/review-clear', { id: pid, code: v, note: note });
        if (r && r.ok) { toast(T('تمت المراجعة ✓', 'Reviewed ✓')); load(1); openItem(pid); } else toast(errText(r));
      }
    } finally { el.disabled = false; }
  }

  async function goLive() {
    S.item = null;
    openDrawer(T('تشغيل التنبيهات', 'Turn alerts on'), T('من هنا ورايح تنفتح التذاكر وتنزل التذكيرات في ديسكورد', 'From now on tickets open and reminders post in Discord'));
    setDrawerBody('<div class="empty sk">—</div>'); setDrawerFoot('');
    var pv = await api('/api/permits/preview-live').catch(function () { return null; });
    if (!pv || !pv.ok) { setDrawerBody('<div class="pm-err">' + esc(errText(pv)) + '</div>'); return; }
    var word = (pv.mode && pv.mode.confirm_word) || 'تشغيل';
    var h = '<div id="pmFormErr"></div><div class="pm-issue">'
      + esc(T('أول ما تشغّلها بينفتح الحين ' + pv.count + ' تذكرة تحت «صيانه»، وكل يوم الساعة ١ الظهر ينزل التقرير اليومي.',
              pv.count + ' ticket(s) open right away under «صيانه», and the daily digest posts every day at 1 PM.')) + '</div>';
    if (pv.count) {
      h += '<div class="pm-sec">' + esc(T('التذاكر اللي بتنفتح', 'Tickets that will open')) + '</div>';
      arr(pv.items).forEach(function (x) {
        h += '<div class="pm-ev">' + bandPill(x.band) + ' <b>' + esc(x.unit) + '</b> · ' + esc(x.permit_no || '') + ' · ' + esc(leftText(x.days_left)) + '</div>';
      });
    }
    h += fld('pmGoWord', T('للتأكيد اكتب «' + word + '»', 'To confirm, type «' + word + '»'), '');
    setDrawerBody(h);
    setDrawerFoot('<button class="btn ghost" data-pa="close">' + esc(T('إلغاء', 'Cancel')) + '</button>'
      + '<button class="btn primary" data-pa="golive-confirm">' + esc(T('شغّل التنبيهات', 'Turn alerts on')) + '</button>');
  }

  async function goLiveConfirm() {
    var r = await post('/api/permits/mode', { mode: 'live', confirm: val('pmGoWord') });
    if (!r || !r.ok) { showErr(r); return; }
    toast(T('التنبيهات شغّالة ✓', 'Alerts are live ✓'));
    closeDrawer();
    load(1);
  }

  function onClick(ev) {
    var el = ev.target.closest ? ev.target.closest('[data-pa]') : null;
    if (!el) return;
    var inTab = el.closest('#view_permits') || el.closest('#drawer');   /* data-pa is used by this tab only */
    if (!inTab) return;
    if (el.tagName === 'A' && el.getAttribute('data-pa') === 'stop') { ev.stopPropagation(); return; }
    if (el.tagName === 'INPUT' && el.type === 'checkbox') { act(el, ev); return; }
    ev.preventDefault();
    act(el, ev);
  }

  function onKey(ev) {
    if (ev.key !== 'Enter') return;
    var el = ev.target;
    if (el && el.classList && el.classList.contains('pm-r')) { openItem(el.getAttribute('data-id')); }
  }

  function onInput(ev) {
    var id = ev.target && ev.target.id;
    if (id === 'pmQ') {
      clearTimeout(S.timer);
      S.timer = setTimeout(function () {
        S.f.q = ev.target.value.trim();
        var pos = ev.target.selectionStart;
        renderBody(S.data);
        var q = document.getElementById('pmQ'); if (q) { q.focus(); try { q.setSelectionRange(pos, pos); } catch (_) {} }
      }, 200);
    }
    if (id === 'pmType') { S.f.type = ev.target.value; renderBody(S.data); }
    if (id === 'pmScope') { S.f.scope = ev.target.value; renderBody(S.data); }
  }

  if (!window.__permitsWired) {
    window.__permitsWired = 1;
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    document.addEventListener('input', onInput);
    document.addEventListener('change', onInput);
  }

  window.PermitsTab = { load: load, open: openItem };
})();
