/* «العقود» — the Contracts tab of the Ouja dashboard.
 *
 * Served by aqd/routes.py at /aqd/static/aqd_tab.js and loaded on first visit by the tiny
 * loadAqd() stub inside DASHBOARD_HTML. A REAL file on purpose: DASHBOARD_HTML is a Python
 * string that eats backslashes (CLAUDE.md trap 1); this file is not.
 *
 * Uses the dashboard's globals only: api, post, tok, esc, labelText, L, D, toast, putHtml,
 * emptyState, errorState, openDrawer, setDrawerBody, setDrawerFoot, closeDrawer, canRead,
 * buildSideNav. Every action is event-delegated through data-aq="…" (no inline onclick
 * string-building). The survey is rendered generically from GET /api/aqd/schema and the
 * server re-validates everything with the same catalogue. Must pass `node --check`.
 */
(function () {
  'use strict';

  var S = { data: null, schema: null, loading: false, f: { status: '', q: '' }, item: null,
            wz: null, poll: null, seenSigned: null, settings: null, timer: null };

  var STATUS = {
    draft:        { ar: 'مسودة',         en: 'Draft',          ic: '✎' },
    sent:         { ar: 'أُرسل',          en: 'Sent',           ic: '↗' },
    opened:       { ar: 'فُتح',           en: 'Opened',         ic: '◉' },
    verified:     { ar: 'تحقّق العميل',   en: 'Verified',       ic: '◉' },
    signed_owner: { ar: 'وقّع العميل',    en: 'Client signed',  ic: '✍' },
    completed:    { ar: 'مكتمل',         en: 'Completed',      ic: '✓' },
    expired:      { ar: 'منتهي',         en: 'Expired',        ic: '⌛' },
    void:         { ar: 'ملغى',          en: 'Void',           ic: '✕' }
  };
  var EVENTS = {
    created: 'أُنشئ العقد', saved: 'تعديل المسودة', sent: 'أُرسل رابط التوقيع', opened: 'فتح العميل الرابط',
    verified: 'تحقّق العميل من هويته', locked: 'قفل مؤقت — محاولات خاطئة', signed: 'وقّع العميل',
    countersigned: 'وقّع المشغّل — اكتمل العقد', void: 'أُلغي العقد', resent: 'رابط جديد', expired: 'انتهى الرابط'
  };
  var CHIPS = ['signed_owner', 'draft', 'sent', 'opened', 'completed', 'expired', 'void'];
  var DIG = '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹';

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
  function n(x) { x = Number(x); return isFinite(x) ? x : 0; }
  function pct(x) { return (x === null || x === undefined || x === '') ? '—' : (Math.round(Number(x) * 10) / 10) + '%'; }

  /* ---------- styles: scoped, token-only ---------- */
  function css() {
    if (document.getElementById('aqCss')) return;
    var s = document.createElement('style');
    s.id = 'aqCss';
    s.textContent = [
      '.aq-banner{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;border-radius:var(--r-md);padding:12px 14px;margin-bottom:14px;background:var(--yellow-soft)}',
      '.aq-banner .t{font-weight:700;color:var(--text);font-size:13.5px}',
      '.aq-banner .s{color:var(--text-2);font-size:12.5px;flex:1 1 260px}',
      '.aq-chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}',
      '.aq-chip{display:inline-flex;align-items:center;gap:7px;min-height:36px;padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--text-2);font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;transition:transform .12s cubic-bezier(0.23,1,0.32,1)}',
      '.aq-chip:active{transform:scale(.97)}',
      '.aq-chip .c{font-family:var(--font-mono);font-size:12px;color:var(--text)}',
      '.aq-chip.on{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft);color:var(--text)}',
      '.aq-chip.hot{background:var(--yellow-soft);border-color:transparent;color:var(--text)}',
      '.aq-chip.hot .c{color:var(--yellow);font-weight:700}',
      '.aq-tools{display:flex;gap:8px;margin-bottom:10px}',
      '.aq-tools input{flex:1 1 240px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);font:inherit;font-size:12.5px;min-height:36px}',
      '.aq-wrap{overflow-x:auto}',
      'table.data tr.aq-r{cursor:pointer}',
      '.aq-st{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
      '.aq-dot{width:7px;height:7px;border-radius:50%;background:currentColor;flex:none}',
      '.aq-st.draft .aq-dot{background:transparent;box-shadow:inset 0 0 0 1.5px currentColor}',
      '.aq-st.signed_owner{background:var(--yellow-soft);color:var(--yellow)}',
      '.aq-st.completed{background:var(--green-soft);color:var(--green)}',
      '.aq-st.void,.aq-st.expired{background:var(--red-soft);color:var(--red)}',
      '.aq-n{font-family:var(--font-mono);white-space:nowrap;font-size:12.5px}',
      '.aq-sub{display:block;font-size:11px;color:var(--mut);margin-top:2px}',
      '.aq-sec{margin:18px 0 8px;font-size:12px;font-weight:700;color:var(--mut)}',
      '.aq-kv{display:grid;grid-template-columns:minmax(110px,34%) 1fr;gap:6px 12px;font-size:13px}',
      '.aq-kv .k{color:var(--mut)}.aq-kv .v{color:var(--text);word-break:break-word}',
      '.aq-link{display:flex;gap:8px;align-items:center;background:var(--surface-2);border-radius:10px;padding:8px 10px;font-family:var(--font-mono);font-size:11.5px;direction:ltr;word-break:break-all;margin-bottom:8px}',
      '.aq-actions{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}',
      '.aq-ev{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;font-size:12.5px;padding:8px 0;border-bottom:1px solid var(--line)}',
      '.aq-ev .w{color:var(--mut);font-size:11px;grid-column:2}',
      '.aq-ev .d{width:8px;height:8px;border-radius:50%;background:var(--accent);margin-top:6px}',
      '.aq-err{background:var(--red-soft);color:var(--red);border-radius:8px;padding:9px 11px;font-size:12.5px;margin-bottom:10px}',
      '.aq-warn{background:var(--yellow-soft);color:var(--text);border-radius:8px;padding:9px 11px;font-size:12.5px;margin-bottom:8px}',
      '.aq-ok{background:var(--green-soft);color:var(--green);border-radius:8px;padding:9px 11px;font-size:12.5px;margin-bottom:8px}',
      '#drawer.aq-wide{width:min(880px,100vw)}',
      '.aq-steps{display:grid;grid-template-columns:repeat(6,1fr);gap:4px;margin-bottom:16px;list-style:none;padding:0}',
      '.aq-steps li{display:flex;flex-direction:column;gap:5px;font-size:11px;color:var(--mut);text-align:center}',
      '.aq-steps li .b{height:4px;border-radius:4px;background:var(--line)}',
      '.aq-steps li.done .b,.aq-steps li.on .b{background:var(--accent)}',
      '.aq-steps li.on{color:var(--text);font-weight:700}',
      '.aq-steps li .nn{font-family:var(--font-mono)}',
      '.aq-f{margin-bottom:16px}',
      '.aq-f>.l{display:block;font-weight:600;color:var(--text);font-size:13px;margin-bottom:6px}',
      '.aq-f .h{font-size:12px;color:var(--mut);margin:-2px 0 6px}',
      '.aq-f input[type=text],.aq-f input[type=number],.aq-f input[type=date],.aq-f select,.aq-f textarea{width:100%;min-height:44px;padding:9px 11px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);font:inherit;font-size:13.5px}',
      '.aq-f textarea{min-height:80px;resize:vertical}',
      '.aq-f input:focus,.aq-f select:focus,.aq-f textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}',
      '.aq-f.bad input,.aq-f.bad select{border-color:var(--red)}',
      '.aq-f .e{color:var(--red);font-size:12px;margin-top:5px}',
      '.aq-opts{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px}',
      '.aq-opts.wide{grid-template-columns:1fr}',
      '.aq-opt{min-height:44px;padding:10px 12px;border-radius:10px;border:1.5px solid var(--line);background:var(--surface);color:var(--text);font:inherit;font-size:13px;font-weight:600;text-align:start;cursor:pointer;transition:transform .12s cubic-bezier(0.23,1,0.32,1),border-color .12s}',
      '.aq-opt:active{transform:scale(.97)}',
      '.aq-opt[aria-checked="true"]{border-color:var(--accent);background:var(--accent-soft)}',
      '.aq-check{display:flex;gap:10px;align-items:flex-start;padding:12px;border-radius:10px;background:var(--yellow-soft);cursor:pointer;font-size:13px;color:var(--text)}',
      '.aq-check input{width:20px;height:20px;margin:1px 0 0;flex:none}',
      '.aq-unit{border:1px solid var(--line);border-radius:var(--r-md);padding:14px;margin-top:6px}',
      '.aq-unit-h{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px}',
      '.aq-unit-h b{font-size:14px;color:var(--text)}',
      '.aq-prev{border:1px solid var(--line);border-radius:var(--r-md);overflow:hidden;background:#fff}',
      '.aq-prev iframe{display:block;width:100%;height:60vh;border:0}',
      '.aq-prev.big iframe{height:auto}',
      '.aq-sum{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}',
      '.aq-sum div{background:var(--surface-2);border-radius:10px;padding:10px}',
      '.aq-sum b{display:block;color:var(--text);font-size:15px}',
      '.aq-sum span{font-size:11.5px;color:var(--mut)}',
      '.aq-img{display:block;max-width:220px;max-height:90px;border:1px dashed var(--line);border-radius:8px;margin-top:6px;background:#fff}',
      '@media (max-width:767px){',
      '  table.aq-t thead{display:none}',
      '  table.aq-t tr.aq-r{display:block;border:1px solid var(--line);border-radius:var(--r-md);margin-bottom:8px;background:var(--surface)}',
      '  table.aq-t tr.aq-r td{display:flex;justify-content:space-between;gap:10px;border:0;padding:6px 12px}',
      '  table.aq-t tr.aq-r td::before{content:attr(data-l);color:var(--mut);font-size:11px;font-weight:600}',
      '  .aq-kv{grid-template-columns:1fr}.aq-sum{grid-template-columns:repeat(2,1fr)}',
      '  .aq-steps li .t{display:none}',
      '}',
      '@media (prefers-reduced-motion:reduce){.aq-chip,.aq-opt{transition:none}.aq-chip:active,.aq-opt:active{transform:none}}'
    ].join('\n');
    document.head.appendChild(s);
  }

  /* ---------- helpers ---------- */
  function statusPill(st) {
    var m = STATUS[st] || { ar: st, en: st, ic: '•' };
    return '<span class="aq-st ' + esc(st) + '"><span class="aq-dot" aria-hidden="true"></span>' + esc(T(m.ar, m.en)) + '</span>';
  }
  function utcMs(iso) { var t = Date.parse(String(iso || '') + (/[zZ]$/.test(String(iso || '')) ? '' : 'Z')); return isFinite(t) ? t : null; }
  function ago(iso) {
    var t = utcMs(iso); if (t === null) return '—';
    var m = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (m < 1) return T('الحين', 'just now');
    if (m < 60) return T('قبل ' + m + ' دقيقة', m + ' min ago');
    var h = Math.round(m / 60); if (h < 24) return T('قبل ' + h + ' ساعة', h + ' h ago');
    var d = Math.round(h / 24); return T('قبل ' + d + ' يوم', d + ' d ago');
  }
  function riyadh(iso) {
    var t = utcMs(iso); if (t === null) return '—';
    try { return new Date(t).toLocaleString(L === 'ar' ? 'ar-SA-u-nu-latn-ca-gregory' : 'en-GB', { timeZone: 'Asia/Riyadh', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
    catch (_) { return String(iso).replace('T', ' ').slice(0, 16); }
  }
  function todayRiyadh() {
    try { return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Riyadh' }); } catch (_) { return new Date().toISOString().slice(0, 10); }
  }
  function errText(r) { return (r && r.error) || T('صار خطأ — جرّب مرة ثانية', 'Something went wrong'); }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast(T('انسخ الرابط ✓', 'Link copied ✓')); }
    catch (_) { window.prompt(T('انسخ الرابط', 'Copy the link'), text); }
  }
  async function blobOpen(path, filename) {
    var r = await fetch(path, { headers: { 'X-Token': tok() } });
    var ct = r.headers.get('Content-Type') || '';
    if (!r.ok || ct.indexOf('application/json') === 0) { toast(T('الملف غير متاح', 'File not available')); return; }
    var b = await r.blob(); var url = URL.createObjectURL(b);
    var a = document.createElement('a'); a.href = url; a.download = filename || 'contract'; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
  }
  function inView() { var v = document.getElementById('view_aqd'); return !!(v && v.offsetParent !== null); }

  /* ---------- load + poll ---------- */
  async function load(force) {
    css();
    if (S.loading) return;
    S.loading = true;
    if (force || !S.data) putHtml('aqBody', '<div class="empty sk">—</div>');
    try {
      var r = await api('/api/aqd/list');
      if (!r || !r.ok) throw r;
      S.data = r;
      noticeSigned(r);
      try { D.aqd = { awaiting: r.awaiting_countersign || 0 }; buildSideNav(); } catch (_) {}
      render();
    } catch (e) {
      putHtml('aqTop', ''); putHtml('aqChips', '');
      putHtml('aqBody', errorState('loadAqd(1)', (e && e.error) || T('ما قدرنا نجيب العقود', 'Could not load contracts')));
    }
    S.loading = false;
    if (!S.poll) {
      S.poll = setInterval(function () { if (inView() && !document.hidden) refreshQuiet(); }, 60000);
    }
  }

  async function refreshQuiet() {
    try {
      var r = await api('/api/aqd/list');
      if (!r || !r.ok) return;
      S.data = r;
      noticeSigned(r);
      try { D.aqd = { awaiting: r.awaiting_countersign || 0 }; buildSideNav(); } catch (_) {}
      renderTop(r); renderChips(r);
      if (!document.getElementById('aqQ') || document.activeElement !== document.getElementById('aqQ')) renderBody(r);
    } catch (_) {}
  }

  function noticeSigned(r) {
    var now = {};
    arr(r.rows).forEach(function (x) { if (x.status === 'signed_owner') now[x.id] = x; });
    if (S.seenSigned) {
      Object.keys(now).forEach(function (id) {
        if (!S.seenSigned[id]) toast(T('وقّع العميل ' + (now[id].client_name || '') + ' العقد ' + (now[id].ref || ''), 'Client signed ' + (now[id].ref || '')));
      });
    }
    S.seenSigned = now;
  }

  /* ---------- render ---------- */
  function render() {
    var d = S.data; if (!d) return;
    Array.prototype.forEach.call(document.querySelectorAll('#view_aqd [data-edit]'), function (b) { b.hidden = !d.can_edit; });
    Array.prototype.forEach.call(document.querySelectorAll('#view_aqd [data-admin]'), function (b) { b.hidden = !d.is_admin; });
    renderTop(d); renderChips(d); renderBody(d);
  }

  function renderTop(d) {
    var ap = d.approval || {};
    if (ap.approved) { putHtml('aqTop', ''); return; }
    putHtml('aqTop', '<div class="aq-banner" role="status"><div class="t">' + esc(T('النموذج ' + (ap.version || '') + ' غير معتمد للتوقيع بعد — اعتمده من الإعدادات بعد موافقة المكتب',
      'Template ' + (ap.version || '') + ' is not approved for signing yet — approve it in Settings after the law firm signs off')) + '</div>'
      + '<div class="s">' + esc(T('الروابط تنرسل والعميل يقرأ العقد، لكن زر التوقيع مقفل لين الاعتماد.', 'Links work and clients can read; signing stays locked until approval.')) + '</div>'
      + (d.is_admin ? '<button class="btn ghost sm" data-aq="settings">' + esc(T('الإعدادات', 'Settings')) + '</button>' : '') + '</div>');
  }

  function chip(key, count, label, hot) {
    var on = S.f.status === key;
    return '<button class="aq-chip' + (on ? ' on' : '') + (hot && count ? ' hot' : '') + '" data-aq="chip" data-v="' + esc(key) + '" aria-pressed="' + (on ? 'true' : 'false') + '">'
      + esc(label) + ' <span class="c">' + n(count) + '</span></button>';
  }

  function renderChips(d) {
    var c = d.counts || {};
    var h = '<div class="aq-chips" role="group" aria-label="' + esc(T('تصفية بالحالة', 'Filter by status')) + '">';
    h += chip('signed_owner', c.signed_owner, T('وقّع العميل — بانتظار توقيعك', 'Signed — waiting for you'), true);
    CHIPS.slice(1).forEach(function (k) {
      var cnt = k === 'opened' ? n(c.opened) + n(c.verified) : c[k];
      h += chip(k, cnt, T(STATUS[k].ar, STATUS[k].en), false);
    });
    h += chip('', d.total, T('الكل', 'All'), false);
    putHtml('aqChips', h + '</div>');
  }

  function matches(r) {
    var st = S.f.status;
    if (st === 'opened' && r.status !== 'opened' && r.status !== 'verified') return false;
    if (st && st !== 'opened' && r.status !== st) return false;
    if (S.f.q) {
      var q = S.f.q.toLowerCase();
      if ([r.ref, r.client_name, r.created_by].join(' ').toLowerCase().indexOf(q) < 0) return false;
    }
    return true;
  }

  function renderBody(d) {
    var rows = arr(d.rows);
    if (!rows.length) {
      putHtml('aqBody', emptyState(T('ما فيه عقود للحين', 'No contracts yet'),
        T('اضغط «+ عقد جديد» وعبّي الاستبيان، ياخذ 3 دقايق.', 'Press «+ New contract» and fill the survey — about 3 minutes.'), '📝'));
      return;
    }
    var list = rows.filter(matches);
    var h = '<div class="aq-tools"><input id="aqQ" type="search" value="' + esc(S.f.q) + '" placeholder="' + esc(T('ابحث: المرجع، العميل، الموظف…', 'Search: ref, client, employee…')) + '" aria-label="' + esc(T('بحث', 'Search')) + '"></div>';
    if (!list.length) {
      putHtml('aqBody', h + emptyState(T('ما فيه عقود بهالتصفية', 'Nothing matches'), T('غيّر التصفية أو البحث.', 'Change the filter or search.'), '—'));
      return;
    }
    h += '<div class="card aq-wrap" style="padding:0"><table class="data aq-t"><thead><tr>'
      + ['المرجع', 'العميل', 'الوحدات', 'النسبة', 'الحالة', 'آخر حدث', 'أنشأه'].map(function (x, i) {
        return '<th>' + esc(T(x, ['Ref', 'Client', 'Units', 'Share', 'Status', 'Last event', 'Created by'][i])) + '</th>';
      }).join('') + '</tr></thead><tbody>';
    list.forEach(function (r) {
      h += '<tr class="aq-r" tabindex="0" data-aq="open" data-id="' + n(r.id) + '">'
        + '<td data-l="' + esc(T('المرجع', 'Ref')) + '"><span class="aq-n strong">' + esc(r.ref) + '</span></td>'
        + '<td data-l="' + esc(T('العميل', 'Client')) + '"><span class="strong">' + esc(r.client_name || '—') + '</span></td>'
        + '<td data-l="' + esc(T('الوحدات', 'Units')) + '"><span class="aq-n">' + n(r.units_count) + '</span></td>'
        + '<td data-l="' + esc(T('النسبة', 'Share')) + '"><span class="aq-n">' + esc(pct(r.op_pct)) + '</span></td>'
        + '<td data-l="' + esc(T('الحالة', 'Status')) + '">' + statusPill(r.status) + '</td>'
        + '<td data-l="' + esc(T('آخر حدث', 'Last event')) + '"><span title="' + esc(riyadh(r.last_event_at)) + '">' + esc(ago(r.last_event_at)) + '</span>'
        + (r.last_event ? '<span class="aq-sub">' + esc(EVENTS[r.last_event] || r.last_event) + '</span>' : '') + '</td>'
        + '<td data-l="' + esc(T('أنشأه', 'Created by')) + '">' + esc(r.created_by || '—') + '</td></tr>';
    });
    putHtml('aqBody', h + '</tbody></table></div>');
  }

  /* ---------- the contract drawer ---------- */
  function wide(on) { var d = document.getElementById('drawer'); if (d) d.classList.toggle('aq-wide', !!on); }

  async function openItem(id) {
    S.wz = null; wide(false);
    openDrawer(T('العقد', 'Contract'), '');
    setDrawerBody('<div class="empty sk">—</div>'); setDrawerFoot('');
    var r = await api('/api/aqd/get?id=' + encodeURIComponent(id)).catch(function () { return null; });
    if (!r || !r.ok) { setDrawerBody('<div class="aq-err">' + esc(errText(r)) + '</div>'); return; }
    S.item = r;
    var c = r.contract, a = r.answers || {};
    openDrawer(c.ref || T('العقد', 'Contract'), (c.client_name || '') + ' · ' + T((STATUS[c.status] || {}).ar || c.status, (STATUS[c.status] || {}).en || c.status));
    var h = '<div id="aqFormErr"></div>';
    if (c.status === 'signed_owner') h += '<div class="aq-warn">' + esc(T('العميل وقّع — العقد ينتظر توقيع المشغّل.', 'The client signed — waiting for the operator.')) + '</div>';
    if (c.status === 'completed') h += '<div class="aq-ok">' + esc(T('العقد مكتمل ومحفوظ.', 'Contract completed and stored.')) + '</div>';
    h += '<div class="aq-kv">'
      + kv(T('الحالة', 'Status'), statusPill(c.status), true)
      + kv(T('العميل', 'Client'), (c.client_kind === 'company' ? T('شركة: ', 'Company: ') : '') + (c.client_name || '—'))
      + kv(T('الهوية / السجل', 'ID / CR'), '<span dir="ltr">' + esc(c.id_masked || '—') + '</span>', true)
      + kv(T('الجوال', 'Mobile'), '<span dir="ltr">' + esc(c.mobile || '—') + '</span>', true)
      + kv(T('الوحدات', 'Units'), String(n(c.units_count)))
      + kv(T('نسبة التشغيل', 'Operating share'), pct(c.op_pct))
      + kv(T('أنشأه', 'Created by'), (c.created_by || '—') + ' · ' + riyadh(c.created_at))
      + (c.expires_at && ['sent', 'opened', 'verified'].indexOf(c.status) >= 0 ? kv(T('ينتهي الرابط', 'Link expires'), riyadh(c.expires_at)) : '')
      + (c.signed_at ? kv(T('وقّع العميل', 'Client signed'), riyadh(c.signed_at) + (c.signer_typed_name ? ' · ' + c.signer_typed_name : '')) : '')
      + (c.countersigned_at ? kv(T('وقّع المشغّل', 'Operator signed'), (c.countersigned_by || '') + ' · ' + riyadh(c.countersigned_at)) : '')
      + (c.void_reason ? kv(T('سبب الإلغاء', 'Void reason'), c.void_reason + ' — ' + (c.voided_by || '')) : '')
      + (c.doc_sha256 ? kv(T('بصمة المستند', 'Document hash'), '<span class="aq-n">' + esc(String(c.doc_sha256).slice(0, 16)) + '…</span>', true) : '')
      + '</div>';
    if (a.internal_note) h += '<div class="aq-sec">' + esc(T('ملاحظة داخلية', 'Internal note')) + '</div><div class="aq-warn">' + esc(a.internal_note) + '</div>';
    arr(r.warnings).forEach(function (w) { h += '<div class="aq-warn">' + esc(w) + '</div>'; });
    if (r.link) {
      h += '<div class="aq-sec">' + esc(T('رابط التوقيع', 'Signing link')) + '</div><div class="aq-link">' + esc(r.link) + '</div>'
        + '<div class="aq-actions"><button class="btn ghost sm" data-aq="copy">' + esc(T('نسخ الرابط', 'Copy link')) + '</button>'
        + '<a class="btn ghost sm" href="' + esc(r.wa_url) + '" target="_blank" rel="noopener">' + esc(T('إرسال واتساب', 'Send on WhatsApp')) + '</a></div>';
    }
    h += '<div class="aq-sec">' + esc(T('السجل', 'Timeline')) + '</div>';
    arr(r.events).slice().reverse().forEach(function (e) {
      h += '<div class="aq-ev"><span class="d" aria-hidden="true"></span><span>' + esc(EVENTS[e.kind] || e.kind)
        + (e.detail && e.detail.reason ? ' — ' + esc(e.detail.reason) : '') + '</span><span class="w">' + esc(e.actor || '') + ' · ' + esc(riyadh(e.at)) + '</span></div>';
    });
    if (r.can.void) {
      h += '<div class="aq-sec">' + esc(T('إلغاء العقد', 'Void')) + '</div>'
        + '<div class="aq-f"><input type="text" id="aqVoidR" placeholder="' + esc(T('سبب الإلغاء (مطلوب)', 'Reason (required)')) + '" aria-label="' + esc(T('سبب الإلغاء', 'Void reason')) + '"></div>';
    }
    setDrawerBody(h);
    var foot = '';
    var fk = c.status === 'completed' ? 'final' : (c.status === 'signed_owner' ? 'signed' : 'draft');
    foot += '<button class="btn ghost" data-aq="pdf" data-v="' + fk + '">' + esc(T('تحميل PDF', 'Download PDF')) + '</button>';
    if (r.can.edit) foot += '<button class="btn ghost" data-aq="resume">' + esc(T('متابعة التعبئة', 'Continue editing')) + '</button>';
    if (r.can.resend) foot += '<button class="btn ghost" data-aq="resend">' + esc(T('رابط جديد', 'New link')) + '</button>';
    if (r.can.void) foot += '<button class="btn ghost" data-aq="void">' + esc(T('إلغاء العقد', 'Void')) + '</button>';
    if (r.can.countersign) foot += '<button class="btn primary" data-aq="countersign">' + esc(T('توقيع المشغّل', 'Countersign')) + '</button>';
    setDrawerFoot(foot);
  }

  function kv(k, v, raw) { return '<div class="k">' + esc(k) + '</div><div class="v">' + (raw ? v : esc(v)) + '</div>'; }

  /* ---------- the survey (wizard) ---------- */
  var DEFAULTS_DONE = {};

  function normv(kind, v) {
    var s = (v === null || v === undefined) ? '' : String(v);
    s = s.replace(/[٠-٩۰-۹]/g, function (ch) { return String(DIG.indexOf(ch) % 10); }).trim();
    if (kind === 'digits') return s.replace(/[\s-]/g, '');
    if (kind === 'mobile') {
      s = s.replace(/[ ()-]/g, '');
      if (s.indexOf('00') === 0) s = '+' + s.slice(2);
      if (/^05[0-9]{8}$/.test(s)) return '+966' + s.slice(1);
      if (/^5[0-9]{8}$/.test(s)) return '+966' + s;
      if (/^9665[0-9]{8}$/.test(s)) return '+' + s;
      return s;
    }
    if (kind === 'upper') return s.replace(/ /g, '').toUpperCase();
    return s.replace(/ +/g, ' ');
  }

  function unitCount(a) {
    if (a.units_count === 'more') { var m = parseInt(a.units_more, 10); return isFinite(m) ? m : 0; }
    var x = parseInt(a.units_count, 10); return isFinite(x) ? x : 0;
  }
  function cond(name, a) {
    if (name === 'many_same') return String(a.same_property) === 'yes' && unitCount(a) > ((S.schema && S.schema.same_property_cap) || 3);
    return true;
  }
  function visible(f, a) {
    var si = f.show_if || {};
    for (var k in si) { if (si.hasOwnProperty(k) && si[k].indexOf(String(a[k] === undefined || a[k] === null ? '' : a[k])) < 0) return false; }
    if (f.cond && !cond(f.cond, a)) return false;
    return true;
  }
  function fieldError(f, raw, a) {
    if (f.type === 'check') return (f.required && !raw) ? 'لازم تأكيد «' + f.label_ar + '»' : '';
    var v = f.type === 'choice' || f.type === 'picker' ? (raw === undefined || raw === null ? '' : String(raw)) : normv(f.norm || (f.type === 'number' ? 'digits' : 'trim'), raw);
    if (v === '') return (f.required && !(f.type === 'choice' && f.default !== undefined)) ? 'مطلوب' : '';
    if (f.type === 'choice') return arr(f.options).some(function (o) { return o.v === v; }) ? '' : 'اختر من الخيارات';
    if (f.type === 'number') {
      var x = Number(v);
      if (!isFinite(x)) return 'رقم فقط';
      if ((f.min !== undefined && x < f.min) || (f.max !== undefined && x > f.max)) return 'بين ' + f.min + ' و ' + f.max;
      if (f.step && Math.abs(Math.round(x / f.step) * f.step - x) > 1e-9) return 'بخطوات ' + f.step;
      return '';
    }
    if (f.type === 'date') {
      if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(v)) return 'تاريخ غير صحيح';
      if (f.not_past && v < todayRiyadh()) return f.msg_ar || 'التاريخ في الماضي';
      return '';
    }
    if (f.type === 'picker') return '';
    var pat = f.re, msg = f.msg_ar;
    if (f.re_by) { var sel = String(a[f.re_by.field] || ''); pat = f.re_by.map[sel]; msg = (f.msg_by || {})[sel] || msg; }
    if (pat && !(new RegExp(pat)).test(v)) return msg || 'الصيغة غير صحيحة';
    if (f.min_words && v.split(' ').filter(Boolean).length < f.min_words) return msg || 'ناقص';
    return '';
  }

  function stepFields(step) { return arr(step.fields); }

  function ensureUnits() {
    var a = S.wz.a, cnt = Math.max(0, Math.min(20, unitCount(a)));
    if (!Array.isArray(a.units)) a.units = [];
    while (a.units.length < cnt) a.units.push({});
    if (a.units.length > cnt) a.units.length = cnt;
    if (S.wz.u >= cnt) S.wz.u = Math.max(0, cnt - 1);
  }

  function applyDefaults(fields, obj) {
    fields.forEach(function (f) { if (f.default !== undefined && (obj[f.key] === undefined || obj[f.key] === '')) obj[f.key] = f.default; });
  }

  function stepErrors(i) {
    var st = S.schema.steps[i], a = S.wz.a, errs = {};
    stepFields(st).forEach(function (f) {
      if (!visible(f, a)) return;
      var e = fieldError(f, a[f.key], a); if (e) errs[f.key] = e;
    });
    if (st.unit_fields) {
      var cnt = unitCount(a);
      if (cnt < 1 || cnt > 20) errs.units_count = errs.units_count || 'عدد الوحدات غير صحيح';
      arr(a.units).forEach(function (u, ui) {
        st.unit_fields.forEach(function (f) {
          if (!visible(f, u)) return;
          var e = fieldError(f, u[f.key], u); if (e) errs['units.' + ui + '.' + f.key] = e;
        });
      });
    }
    return errs;
  }

  async function ensureSchema() {
    if (S.schema) return S.schema;
    var r = await api('/api/aqd/schema');
    if (!r || !r.ok) throw r;
    S.schema = r;
    return r;
  }

  async function newContract(draft, id) {
    try { await ensureSchema(); } catch (e) { toast(errText(e)); return; }
    S.item = null;
    S.wz = { i: 0, a: draft || {}, u: 0, id: id || null, touched: {}, preview: null, big: false, result: null, saving: false };
    applyDefaults(S.schema.steps[0].fields, S.wz.a);
    wide(true);
    openDrawer(id ? T('متابعة المسودة', 'Continue draft') : T('عقد جديد', 'New contract'), T('استبيان قصير — اختيارات في الغالب', 'A short survey — mostly choices'));
    wz();
  }

  function stepBar() {
    var h = '<ol class="aq-steps" aria-label="' + esc(T('خطوات الاستبيان', 'Survey steps')) + '">';
    S.schema.steps.forEach(function (st, i) {
      var cls = i < S.wz.i ? 'done' : (i === S.wz.i ? 'on' : '');
      h += '<li class="' + cls + '"' + (i === S.wz.i ? ' aria-current="step"' : '') + '><span class="b"></span><span><span class="nn">' + (i + 1) + '</span> <span class="t">' + esc(T(st.label_ar, st.label_en)) + '</span></span></li>';
    });
    return h + '</ol>';
  }

  function fieldHtml(f, obj, prefix, errs) {
    if (!visible(f, obj)) return '';
    var key = prefix + f.key, val = obj[f.key];
    var err = (S.wz.touched[key] || S.wz.tried) ? (errs[key] || '') : '';
    var id = 'aqf_' + key.replace(/[^a-z0-9_]/gi, '_');
    var u = prefix ? ' data-u="' + S.wz.u + '"' : '';
    var h = '<div class="aq-f' + (err ? ' bad' : '') + '">';
    if (f.type === 'check') {
      h += '<label class="aq-check"><input type="checkbox" id="' + id + '" data-k="' + esc(f.key) + '"' + u + (val ? ' checked' : '') + '><span><b>' + esc(f.label_ar) + '</b>' + (f.help_ar ? ' — ' + esc(f.help_ar) : '') + '</span></label>';
    } else {
      h += '<span class="l" id="' + id + '_l">' + esc(T(f.label_ar, f.label_en)) + '</span>';
      if (f.help_ar) h += '<div class="h">' + esc(f.help_ar) + '</div>';
      if (f.type === 'choice') {
        var long = arr(f.options).some(function (o) { return o.ar.length > 18; });
        h += '<div class="aq-opts' + (long ? ' wide' : '') + '" role="radiogroup" aria-labelledby="' + id + '_l">';
        arr(f.options).forEach(function (o) {
          var on = String(val) === o.v;
          h += '<button type="button" class="aq-opt" role="radio" aria-checked="' + (on ? 'true' : 'false') + '" data-aq="pick" data-k="' + esc(f.key) + '" data-v="' + esc(o.v) + '"' + u + '>' + esc(T(o.ar, o.en)) + '</button>';
        });
        h += '</div>';
      } else if (f.type === 'picker') {
        h += '<select id="' + id + '" data-k="' + esc(f.key) + '"' + u + ' aria-labelledby="' + id + '_l"><option value="">' + esc(T('— بدون ربط —', '— not linked —')) + '</option>'
          + arr(S.schema.listings).map(function (x) { return '<option value="' + n(x.id) + '"' + (String(val) === String(x.id) ? ' selected' : '') + '>' + esc(x.name) + '</option>'; }).join('') + '</select>';
      } else if (f.type === 'textarea') {
        h += '<textarea id="' + id + '" data-k="' + esc(f.key) + '"' + u + ' aria-labelledby="' + id + '_l">' + esc(val || '') + '</textarea>';
      } else {
        var t = f.type === 'number' ? 'number' : (f.type === 'date' ? 'date' : 'text');
        var im = f.inputmode || (f.norm === 'digits' ? 'numeric' : (f.type === 'number' ? 'decimal' : ''));
        h += '<input type="' + t + '" id="' + id + '" data-k="' + esc(f.key) + '"' + u + ' value="' + esc(val === undefined || val === null ? '' : val) + '"'
          + (im ? ' inputmode="' + im + '"' : '') + (f.placeholder ? ' placeholder="' + esc(f.placeholder) + '"' : '')
          + (f.min !== undefined ? ' min="' + f.min + '"' : '') + (f.max !== undefined ? ' max="' + f.max + '"' : '') + (f.step ? ' step="' + f.step + '"' : '')
          + (f.not_past ? ' min="' + todayRiyadh() + '"' : '')
          + ' aria-labelledby="' + id + '_l"' + (err ? ' aria-invalid="true" aria-describedby="' + id + '_e"' : '') + '>';
      }
    }
    if (err) h += '<div class="e" id="' + id + '_e">' + esc(err) + '</div>';
    return h + '</div>';
  }

  function wz() {
    var w = S.wz, st = S.schema.steps[w.i], a = w.a;
    if (w.result) return wzResult();
    applyDefaults(stepFields(st), a);
    if (st.unit_fields) { ensureUnits(); a.units.forEach(function (u) { applyDefaults(st.unit_fields, u); }); }
    var errs = stepErrors(w.i);
    var h = stepBar() + '<div id="aqFormErr"></div>';
    if (st.id === 'review') { h += reviewHtml(); setDrawerBody(h); wzFoot(errs); loadPreview(); return; }
    stepFields(st).forEach(function (f) { h += fieldHtml(f, a, '', errs); });
    if (st.unit_fields) {
      ensureUnits();
      var cnt = a.units.length;
      if (cnt) {
        var u = a.units[w.u];
        applyDefaults(st.unit_fields, u);
        h += '<div class="aq-unit"><div class="aq-unit-h"><b>' + esc(T('الوحدة ' + (w.u + 1) + ' من ' + cnt + ' — A' + (w.u + 1), 'Unit ' + (w.u + 1) + ' of ' + cnt)) + '</b><span>'
          + (w.u > 0 ? '<button class="btn ghost sm" data-aq="uprev">' + esc(T('السابقة', 'Previous')) + '</button> ' : '')
          + (w.u < cnt - 1 ? '<button class="btn ghost sm" data-aq="unext">' + esc(T('التالية', 'Next unit')) + '</button>' : '') + '</span></div>';
        var uerr = {};
        Object.keys(errs).forEach(function (k) { var p = 'units.' + w.u + '.'; if (k.indexOf(p) === 0) uerr['u.' + k.slice(p.length)] = errs[k]; });
        st.unit_fields.forEach(function (f) { h += fieldHtml(f, u, 'u.', uerr); });
        var bad = Object.keys(errs).filter(function (k) { return k.indexOf('units.') === 0; }).map(function (k) { return Number(k.split('.')[1]) + 1; });
        bad = bad.filter(function (x, i) { return bad.indexOf(x) === i && x !== w.u + 1; });
        if (bad.length) h += '<div class="aq-warn" style="margin-top:10px">' + esc(T('وحدات ناقصة: ', 'Units incomplete: ') + bad.map(function (x) { return 'A' + x; }).join('، ')) + '</div>';
        h += '</div>';
      }
    }
    setDrawerBody(h);
    wzFoot(errs);
  }

  function wzFoot(errs) {
    var w = S.wz, last = w.i === S.schema.steps.length - 1, valid = !Object.keys(errs).length;
    var f = '<button class="btn ghost" data-aq="back"' + (w.i === 0 ? ' disabled' : '') + '>' + esc(T('رجوع', 'Back')) + '</button>'
      + '<button class="btn ghost" data-aq="savedraft">' + esc(T('حفظ كمسودة', 'Save draft')) + '</button>';
    if (!last) f += '<button class="btn primary" data-aq="next"' + (valid ? '' : ' disabled aria-disabled="true"') + '>' + esc(T('التالي', 'Next')) + '</button>';
    else f += '<button class="btn primary" data-aq="create"' + ((w.preview && !arr(w.preview.blockers).length && !Object.keys(w.preview.errors || {}).length) ? '' : ' disabled') + '>' + esc(T('إنشاء رابط التوقيع', 'Create signing link')) + '</button>';
    setDrawerFoot(f);
  }

  function refreshStep() {
    /* re-render keeping focus on the field being typed in */
    var ae = document.activeElement, k = ae && ae.getAttribute && ae.getAttribute('data-k'), u = ae && ae.getAttribute && ae.getAttribute('data-u');
    var pos = null; try { pos = ae.selectionStart; } catch (_) {}
    wz();
    if (k) {
      var sel = '#drwBody [data-k="' + k + '"]' + (u !== null && u !== undefined ? '[data-u="' + u + '"]' : ':not([data-u])');
      var el = document.querySelector(sel);
      if (el && el.tagName !== 'BUTTON') { el.focus(); try { if (pos !== null) el.setSelectionRange(pos, pos); } catch (_) {} }
    }
  }

  function setVal(el, v) {
    var k = el.getAttribute('data-k'), u = el.getAttribute('data-u');
    var obj = (u !== null && u !== undefined) ? S.wz.a.units[Number(u)] : S.wz.a;
    obj[k] = v;
    return (u !== null && u !== undefined ? 'u.' : '') + k;
  }

  function summary() {
    var a = S.wz.a;
    var who = a.client_kind === 'company' ? a.company_name : a.full_name;
    var p = a.op_pct === 'other' ? a.op_pct_other : a.op_pct;
    var fees = arr(a.units).map(function (u) { return u.monthly_fee === 'other' ? u.monthly_fee_other : u.monthly_fee; }).filter(Boolean);
    return '<div class="aq-sum">'
      + '<div><b>' + esc(who || '—') + '</b><span>' + esc(T('العميل', 'Client')) + '</span></div>'
      + '<div><b>' + n(arr(a.units).length) + '</b><span>' + esc(T('وحدات', 'Units')) + '</span></div>'
      + '<div><b>' + esc(pct(p)) + '</b><span>' + esc(T('نسبة التشغيل', 'Share')) + '</span></div>'
      + '<div><b>' + esc(fees.length ? fees.map(function (x) { return Number(x).toLocaleString('en-US'); }).join(' / ') : '—') + '</b><span>' + esc(T('الرسوم الشهرية (ريال)', 'Monthly fee (SAR)')) + '</span></div>'
      + '</div>';
  }

  function reviewHtml() {
    var p = S.wz.preview;
    var h = summary() + '<div id="aqRevMsgs">';
    if (p) {
      arr(p.blockers).forEach(function (x) { h += '<div class="aq-err">' + esc(x) + '</div>'; });
      var ek = Object.keys(p.errors || {});
      if (ek.length) h += '<div class="aq-err">' + esc(T('فيه ' + ek.length + ' خانة ناقصة أو غير صحيحة — ارجع للخطوات السابقة.', ek.length + ' field(s) need fixing — go back.')) + '</div>';
      arr(p.warnings).forEach(function (x) { h += '<div class="aq-warn">' + esc(x) + '</div>'; });
    }
    h += '</div><div class="aq-actions"><span class="aq-sec" style="margin:0;flex:1">' + esc(T('معاينة العقد المعبّى', 'Filled contract preview')) + '</span>'
      + '<button class="btn ghost sm" data-aq="zoom" aria-pressed="' + (S.wz.big ? 'true' : 'false') + '">' + esc(S.wz.big ? T('تصغير', 'Shrink') : T('تكبير', 'Expand')) + '</button></div>'
      + '<div class="aq-prev' + (S.wz.big ? ' big' : '') + '" id="aqPrev">' + (p ? '' : '<div class="empty sk" style="height:300px">—</div>') + '</div>';
    return h;
  }

  async function loadPreview() {
    var w = S.wz;
    if (w.preview && w.previewFor === JSON.stringify(w.a)) { mountPreview(); return; }
    var r = await post('/api/aqd/preview', { answers: w.a, id: w.id });
    if (S.wz !== w) return;
    if (!r || !r.ok) { putHtml('aqFormErr', '<div class="aq-err">' + esc(errText(r)) + '</div>'); return; }
    w.preview = r; w.previewFor = JSON.stringify(w.a);
    wz();
  }

  function mountPreview() {
    var box = document.getElementById('aqPrev'); if (!box || !S.wz.preview) return;
    var f = document.createElement('iframe');
    f.title = T('معاينة العقد', 'Contract preview');
    f.setAttribute('sandbox', 'allow-same-origin');
    f.addEventListener('load', function () {
      if (!S.wz || !S.wz.big) return;
      try { f.style.height = (f.contentDocument.documentElement.scrollHeight + 10) + 'px'; } catch (_) {}
    });
    f.srcdoc = S.wz.preview.html.replace('</head>', '<style>@media screen{body{padding:20px 22px}}</style></head>');
    box.innerHTML = ''; box.appendChild(f);
  }

  async function saveDraft(quiet) {
    var w = S.wz;
    if (w.saving) return null;
    w.saving = true;
    var r = await post('/api/aqd/save', { id: w.id, answers: w.a });
    w.saving = false;
    if (!r || !r.ok) { putHtml('aqFormErr', '<div class="aq-err">' + esc(errText(r)) + '</div>'); return null; }
    w.id = r.id;
    if (!quiet) { toast(T('انحفظت المسودة ✓ ' + r.ref, 'Draft saved ✓ ' + r.ref)); load(1); }
    return r;
  }

  async function createLink(btn) {
    var w = S.wz;
    btn.disabled = true; btn.textContent = T('جاري الإنشاء…', 'Creating…');
    var s = await saveDraft(true);
    if (!s) { btn.disabled = false; btn.textContent = T('إنشاء رابط التوقيع', 'Create signing link'); return; }
    var r = await post('/api/aqd/send', { id: w.id });
    if (!r || !r.ok) {
      putHtml('aqFormErr', '<div class="aq-err">' + esc(errText(r)) + '</div>');
      btn.disabled = false; btn.textContent = T('إنشاء رابط التوقيع', 'Create signing link');
      return;
    }
    w.result = r;
    load(1);
    wz();
  }

  function wzResult() {
    var r = S.wz.result;
    setDrawerBody('<div class="aq-ok">' + esc(T('انشأ رابط التوقيع للعقد ' + r.ref + ' ✓', 'Signing link created for ' + r.ref + ' ✓')) + '</div>'
      + (r.approved ? '' : '<div class="aq-warn">' + esc(T('النموذج غير معتمد بعد: العميل يقدر يفتح ويقرأ، والتوقيع مقفل لين تعتمده من الإعدادات.', 'Template not approved yet: the client can read, signing stays locked.')) + '</div>')
      + '<div class="aq-sec">' + esc(T('الرابط', 'Link')) + '</div><div class="aq-link">' + esc(r.link) + '</div>'
      + '<div class="aq-actions"><button class="btn ghost" data-aq="copylink">' + esc(T('نسخ الرابط', 'Copy link')) + '</button>'
      + '<a class="btn primary" href="' + esc(r.wa_url) + '" target="_blank" rel="noopener">' + esc(T('إرسال واتساب', 'Send on WhatsApp')) + '</a></div>');
    setDrawerFoot('<button class="btn ghost" data-aq="close">' + esc(T('تم', 'Done')) + '</button>'
      + '<button class="btn ghost" data-aq="open-res">' + esc(T('فتح العقد', 'Open contract')) + '</button>');
  }

  /* ---------- settings (admin) ---------- */
  var SETTING_LABELS = [
    ['op_rep_name', 'اسم ممثل المشغّل (الموقّع عن الشركة)', 'Operator representative'],
    ['op_wakala_no', 'رقم الوكالة (ناجز)', 'POA number (Najiz)'],
    ['op_wakala_date', 'تاريخ الوكالة', 'POA date'],
    ['op_cr_expiry', 'تاريخ انتهاء السجل التجاري', 'CR expiry'],
    ['op_fal_no', 'رقم رخصة فال', 'FAL licence number'],
    ['op_fal_expiry', 'تاريخ انتهاء رخصة فال', 'FAL licence expiry'],
    ['platform_proof', 'ما يثبت ترخيص منصات الحجز', 'Booking-platform proof'],
    ['brand_name', 'اسم العلامة التجارية', 'Brand name'],
    ['brand_reg', 'تسجيل العلامة', 'Brand registration'],
    ['link_ttl_days', 'مدة صلاحية الرابط (أيام) — فاضي = الافتراضي', 'Link lifetime (days) — blank = default']
  ];

  async function openSettings() {
    S.wz = null; S.item = null; wide(false);
    openDrawer(T('إعدادات العقود', 'Contract settings'), T('بيانات المشغّل، التوقيع والختم، واعتماد النموذج', 'Operator details, signature & stamp, template approval'));
    setDrawerBody('<div class="empty sk">—</div>'); setDrawerFoot('');
    var r = await api('/api/aqd/settings').catch(function () { return null; });
    if (!r || !r.ok) { setDrawerBody('<div class="aq-err">' + esc(errText(r)) + '</div>'); return; }
    S.settings = r; S.upload = {};
    var ap = r.approval || {};
    var h = '<div id="aqFormErr"></div>';
    h += '<div class="aq-sec">' + esc(T('اعتماد النموذج ' + r.template_version, 'Template ' + r.template_version + ' approval')) + '</div>';
    if (ap.approved) {
      h += '<div class="aq-ok">' + esc(T('معتمد للتوقيع — اعتمده ' + (ap.by || '') + ' · ' + riyadh(ap.at), 'Approved by ' + (ap.by || '') + ' · ' + riyadh(ap.at))) + '</div>'
        + '<div class="aq-actions"><button class="btn ghost sm" data-aq="unapprove">' + esc(T('إيقاف الاعتماد', 'Withdraw approval')) + '</button></div>';
    } else {
      h += '<div class="aq-warn">' + esc(T('غير معتمد: العملاء يقرون العقد لكن ما يقدرون يوقّعون. اعتمده بعد موافقة المكتب.', 'Not approved: clients can read but not sign. Approve after the law firm signs off.')) + '</div>'
        + '<div class="aq-f"><span class="l">' + esc(T('للاعتماد اكتب «' + r.confirm_word + '»', 'To approve, type «' + r.confirm_word + '»')) + '</span>'
        + '<input type="text" id="aqApprove" aria-label="' + esc(T('كلمة التأكيد', 'Confirm word')) + '"></div>'
        + '<div class="aq-actions"><button class="btn primary sm" data-aq="approve">' + esc(T('اعتماد النموذج', 'Approve template')) + '</button></div>';
    }
    h += '<div class="aq-sec">' + esc(T('توقيع المشغّل والختم (PNG، حد أقصى 300 KB)', 'Operator signature & stamp (PNG, max 300 KB)')) + '</div>';
    [['op_sig_png', 'sig_png', 'توقيع المشغّل', 'Operator signature'], ['op_stamp_png', 'stamp_png', 'ختم الشركة', 'Company stamp']].forEach(function (x) {
      h += '<div class="aq-f"><span class="l">' + esc(T(x[2], x[3])) + '</span><input type="file" accept="image/png" data-aq-file="' + x[0] + '" aria-label="' + esc(T(x[2], x[3])) + '">'
        + '<span id="aqImg_' + x[0] + '">' + (r[x[1]] ? '<img class="aq-img" alt="' + esc(T(x[2], x[3])) + '" src="data:image/png;base64,' + r[x[1]] + '">' : '') + '</span></div>';
    });
    h += '<div class="aq-sec">' + esc(T('بيانات المشغّل في العقد', 'Operator details printed in the contract')) + '</div>';
    SETTING_LABELS.forEach(function (x) {
      h += '<div class="aq-f"><span class="l" id="aqS_' + x[0] + '_l">' + esc(T(x[1], x[2])) + '</span><input type="text" id="aqS_' + x[0] + '" value="' + esc((r.values || {})[x[0]] || '') + '" aria-labelledby="aqS_' + x[0] + '_l"'
        + (x[0] === 'link_ttl_days' ? ' inputmode="numeric" placeholder="' + esc(String(r.env_ttl_days)) + '"' : '') + '></div>';
    });
    h += '<p class="aq-sub">' + esc(T('التنبيهات تنزل في روم «' + r.channel + '» بديسكورد.', 'Notifications post in the «' + r.channel + '» Discord room.')) + '</p>';
    setDrawerBody(h);
    setDrawerFoot('<button class="btn ghost" data-aq="close">' + esc(T('إغلاق', 'Close')) + '</button><button class="btn primary" data-aq="savesettings">' + esc(T('حفظ', 'Save')) + '</button>');
  }

  async function saveSettings(extra) {
    var vals = {};
    SETTING_LABELS.forEach(function (x) { var el = document.getElementById('aqS_' + x[0]); if (el) vals[x[0]] = el.value; });
    var body = { values: vals };
    Object.keys(S.upload || {}).forEach(function (k) { body[k] = S.upload[k]; });
    if (extra) Object.keys(extra).forEach(function (k) { body[k] = extra[k]; });
    var r = await post('/api/aqd/settings', body);
    if (!r || !r.ok) { putHtml('aqFormErr', '<div class="aq-err">' + esc(errText(r)) + '</div>'); return false; }
    toast(T('انحفظت الإعدادات ✓', 'Settings saved ✓'));
    load(1);
    openSettings();
    return true;
  }

  /* ---------- actions ---------- */
  async function act(el) {
    var a = el.getAttribute('data-aq'), v = el.getAttribute('data-v');
    if (a === 'new') return newContract();
    if (a === 'settings') return openSettings();
    if (a === 'close') { S.wz = null; wide(false); closeDrawer(); return; }
    if (a === 'chip') { S.f.status = v || ''; renderChips(S.data); renderBody(S.data); return; }
    if (a === 'open') return openItem(el.getAttribute('data-id'));
    if (a === 'open-res') { var rid = S.wz && S.wz.id; S.wz = null; return openItem(rid); }
    if (a === 'copy' && S.item && S.item.link) return copy(S.item.link);
    if (a === 'copylink' && S.wz && S.wz.result) return copy(S.wz.result.link);
    if (a === 'pdf' && S.item) return blobOpen('/api/aqd/file?id=' + encodeURIComponent(S.item.contract.id) + '&kind=' + encodeURIComponent(v), (S.item.contract.ref || 'contract') + '-' + v);
    /* wizard */
    if (S.wz && a === 'pick') {
      var key = setVal(el, v); S.wz.touched[key] = 1;
      if (el.getAttribute('data-k') === 'units_count' || el.getAttribute('data-k') === 'same_property') ensureUnits();
      S.wz.preview = null; refreshStep(); return;
    }
    if (S.wz && a === 'next') {
      if (Object.keys(stepErrors(S.wz.i)).length) { S.wz.tried = true; wz(); return; }
      S.wz.tried = false; S.wz.i++; S.wz.u = 0; wz(); var b = document.getElementById('drwBody'); if (b) b.scrollTop = 0; return;
    }
    if (S.wz && a === 'back') { if (S.wz.i > 0) { S.wz.i--; S.wz.tried = false; wz(); } return; }
    if (S.wz && a === 'unext') { S.wz.u++; wz(); return; }
    if (S.wz && a === 'uprev') { S.wz.u--; wz(); return; }
    if (S.wz && a === 'zoom') { S.wz.big = !S.wz.big; wz(); return; }
    if (S.wz && a === 'savedraft') { el.disabled = true; await saveDraft(false); el.disabled = false; return; }
    if (S.wz && a === 'create') return createLink(el);
    /* contract drawer */
    if (a === 'resume' && S.item) {
      var g = await api('/api/aqd/get?id=' + encodeURIComponent(S.item.contract.id) + '&edit=1').catch(function () { return null; });
      if (!g || !g.ok) { toast(errText(g)); return; }
      return newContract(g.draft_answers || {}, S.item.contract.id);
    }
    if (a === 'resend' && S.item) {
      el.disabled = true;
      var rs = await post('/api/aqd/resend', { id: S.item.contract.id });
      el.disabled = false;
      if (rs && rs.ok) { toast(T('انشأ رابط جديد ✓', 'New link created ✓')); load(1); openItem(S.item.contract.id); } else putHtml('aqFormErr', '<div class="aq-err">' + esc(errText(rs)) + '</div>');
      return;
    }
    if (a === 'void' && S.item) {
      var reason = (document.getElementById('aqVoidR') || {}).value || '';
      if (reason.trim().length < 3) { putHtml('aqFormErr', '<div class="aq-err">' + esc(T('اكتب سبب الإلغاء تحت أول', 'Write the reason below first')) + '</div>'); var vr = document.getElementById('aqVoidR'); if (vr) vr.focus(); return; }
      if (!window.confirm(T('أكيد تلغي العقد ' + S.item.contract.ref + '؟ الرابط بيوقف عند العميل.', 'Void ' + S.item.contract.ref + '? The client link stops working.'))) return;
      el.disabled = true;
      var rv = await post('/api/aqd/void', { id: S.item.contract.id, reason: reason });
      el.disabled = false;
      if (rv && rv.ok) { toast(T('انلغى العقد', 'Contract voided')); load(1); openItem(S.item.contract.id); } else putHtml('aqFormErr', '<div class="aq-err">' + esc(errText(rv)) + '</div>');
      return;
    }
    if (a === 'countersign' && S.item) {
      if (!window.confirm(T('بتوقيعك يصير العقد نهائي ويتحفظ ويوصل العميل نسخته. نكمل؟', 'Signing makes the contract final, stores it and gives the client their copy. Continue?'))) return;
      el.disabled = true; el.textContent = T('جاري التوقيع…', 'Signing…');
      var rc = await post('/api/aqd/countersign', { id: S.item.contract.id });
      if (rc && rc.ok) { toast(T('اكتمل العقد ✓', 'Contract completed ✓')); load(1); openItem(S.item.contract.id); }
      else { el.disabled = false; el.textContent = T('توقيع المشغّل', 'Countersign'); putHtml('aqFormErr', '<div class="aq-err">' + esc(errText(rc)) + '</div>'); }
      return;
    }
    /* settings */
    if (a === 'savesettings') { el.disabled = true; await saveSettings(); el.disabled = false; return; }
    if (a === 'approve') { el.disabled = true; await saveSettings({ approve: true, confirm: (document.getElementById('aqApprove') || {}).value || '' }); el.disabled = false; return; }
    if (a === 'unapprove') {
      if (!window.confirm(T('إيقاف الاعتماد يقفل التوقيع عند كل العملاء. نكمل؟', 'Withdrawing approval locks signing for every client. Continue?'))) return;
      el.disabled = true; await saveSettings({ approve: false }); el.disabled = false; return;
    }
  }

  function inTab(el) { return el.closest('#view_aqd') || el.closest('#drawer'); }

  function onClick(ev) {
    var el = ev.target.closest ? ev.target.closest('[data-aq]') : null;
    if (!el || !inTab(el)) return;
    if (el.tagName === 'A') return;
    ev.preventDefault();
    act(el);
  }

  function onKey(ev) {
    var el = ev.target;
    if ((ev.key === 'Enter' || ev.key === ' ') && el && el.classList && el.classList.contains('aq-r')) { ev.preventDefault(); openItem(el.getAttribute('data-id')); }
  }

  function onInput(ev) {
    var el = ev.target;
    if (!el || !el.getAttribute) return;
    if (el.id === 'aqQ') {
      clearTimeout(S.timer);
      S.timer = setTimeout(function () {
        S.f.q = el.value.trim();
        var pos = el.selectionStart;
        renderBody(S.data);
        var q = document.getElementById('aqQ'); if (q) { q.focus(); try { q.setSelectionRange(pos, pos); } catch (_) {} }
      }, 200);
      return;
    }
    if (el.getAttribute('data-aq-file') && ev.type === 'change') { readPng(el); return; }
    if (!S.wz || !el.getAttribute('data-k') || !el.closest('#drawer')) return;
    var v = el.type === 'checkbox' ? !!el.checked : el.value;
    var key = setVal(el, v);
    S.wz.preview = null;
    /* a checkbox / select is the click itself: re-render (visibility may change) */
    if (el.type === 'checkbox' || el.tagName === 'SELECT') { S.wz.touched[key] = 1; refreshStep(); return; }
    if (ev.type === 'change') {
      S.wz.touched[key] = 1;
      if (el.getAttribute('data-k') === 'units_more') { setTimeout(function () { if (S.wz) refreshStep(); }, 0); return; }
    }
    /* typing: never re-render under the caret — patch this field's message + the footer */
    if (S.wz.touched[key]) fieldMsg(el);
    wzFoot(stepErrors(S.wz.i));
  }

  function fieldDef(el) {
    var st = S.schema.steps[S.wz.i], k = el.getAttribute('data-k'), u = el.getAttribute('data-u');
    var list = (u !== null && u !== undefined) ? arr(st.unit_fields) : stepFields(st);
    for (var i = 0; i < list.length; i++) { if (list[i].key === k) return list[i]; }
    return null;
  }

  function fieldMsg(el) {
    var f = fieldDef(el); if (!f) return;
    var u = el.getAttribute('data-u');
    var obj = (u !== null && u !== undefined) ? S.wz.a.units[Number(u)] : S.wz.a;
    var err = fieldError(f, obj[f.key], obj);
    var box = el.closest('.aq-f'); if (!box) return;
    box.classList.toggle('bad', !!err);
    var e = box.querySelector('.e');
    if (err) {
      if (!e) { e = document.createElement('div'); e.className = 'e'; e.id = el.id + '_e'; box.appendChild(e); }
      e.textContent = err;
      el.setAttribute('aria-invalid', 'true'); el.setAttribute('aria-describedby', e.id);
    } else {
      if (e) e.remove();
      el.removeAttribute('aria-invalid'); el.removeAttribute('aria-describedby');
    }
  }

  function onBlur(ev) {
    var el = ev.target;
    if (!S.wz || !el || !el.getAttribute || !el.getAttribute('data-k') || !el.closest('#drawer')) return;
    if (el.tagName === 'BUTTON') return;
    var u = el.getAttribute('data-u');
    S.wz.touched[(u !== null && u !== undefined ? 'u.' : '') + el.getAttribute('data-k')] = 1;
    fieldMsg(el);
  }

  function readPng(el) {
    var f = el.files && el.files[0];
    if (!f) return;
    if (f.type !== 'image/png') { toast(T('الملف لازم يكون PNG', 'PNG only')); el.value = ''; return; }
    if (f.size > 300 * 1024) { toast(T('الصورة أكبر من 300 KB', 'Over 300 KB')); el.value = ''; return; }
    var rd = new FileReader();
    rd.onload = function () {
      S.upload = S.upload || {};
      S.upload[el.getAttribute('data-aq-file')] = rd.result;
      var box = document.getElementById('aqImg_' + el.getAttribute('data-aq-file'));
      if (box) { var img = document.createElement('img'); img.className = 'aq-img'; img.alt = ''; img.src = rd.result; box.innerHTML = ''; box.appendChild(img); }
    };
    rd.readAsDataURL(f);
  }

  if (!window.__aqdWired) {
    window.__aqdWired = 1;
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    document.addEventListener('input', onInput);
    document.addEventListener('change', onInput);
    document.addEventListener('focusout', onBlur);
  }

  window.AqdTab = { load: load, open: openItem, newContract: newContract };
})();
