/* «أهدافي» + «دفتر العملاء» — two tabs of the Ouja dashboard, and the two phone pages.
 *
 * Served by targets/routes.py at /targets/static/targets_tab.js and loaded on first visit by
 * the tiny __tgLoad() stub that targets.routes.patch_dashboard splices into the dashboard.
 * A REAL file on purpose: DASHBOARD_HTML is a Python string that eats backslashes.
 *
 * Uses the host page's globals only: api, post, esc, labelText, toast, putHtml, emptyState,
 * errorState, tok. The phone pages (targets/page.py) define the same seven. Every action is
 * event-delegated through data-tg="…". Must pass `node --check`.
 *
 * WHAT THIS FILE MAY SHOW AN EMPLOYEE: their own board, their own amount, their own list.
 * The admin sections render only from /api/targets/admin, which the server gives the owner alone.
 */
(function () {
  'use strict';

  var S = { me: null, admin: null, team: null, book: null, month: '', quarter: '', pane: 'me', busy: false, opened: false, grown: false };

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
  /* A unit name like '1 MLQ' flips to 'MLQ 1' inside right-to-left text. <bdi> keeps it as written. */
  function nm(x) { return '<bdi>' + esc(x) + '</bdi>'; }
  function num(x) { return '<span class="tg-num">' + esc(x) + '</span>'; }
  function pct(x) { return x == null ? '—' : num(Math.round(Number(x) * 100) + '%'); }
  function sar(x) { return num(Math.round(Number(x) || 0).toLocaleString('en-US')) + ' ' + T('ر.س', 'SAR'); }
  function day(iso) { var p = String(iso || '').split('-'); return p.length === 3 ? Number(p[2]) + '/' + Number(p[1]) : '—'; }

  function css() {
    if (document.getElementById('tgCss')) return;
    var s = document.createElement('style');
    s.id = 'tgCss';
    s.textContent = [
      '.tg-num{font-family:var(--font-mono);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate;display:inline-block;white-space:nowrap}',
      '.tg-banner{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;padding:10px 14px;border-radius:var(--r-md);background:var(--gold-tint);color:var(--text);font-size:13px;font-weight:700;margin-bottom:12px}',
      '.tg-banner.lock{background:var(--red-soft);color:var(--red)}',
      '.tg-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;margin-bottom:12px}',
      '.tg-seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;background:var(--surface)}',
      '.tg-seg button{border:0;background:none;padding:8px 14px;font:inherit;font-size:13px;font-weight:700;color:var(--text-2);cursor:pointer;min-height:38px}',
      '.tg-seg button.on{background:var(--gold-tint);color:var(--text)}',
      '.tg-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}',
      '.tg-kpi{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);padding:12px 14px}',
      '.tg-kpi b{display:block;font-size:20px;color:var(--text);line-height:1.3}',
      '.tg-kpi>span{display:block;font-size:12px;color:var(--mut);margin-top:2px}',
      '.tg-box{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);padding:14px;margin-bottom:14px}',
      '.tg-h{font-size:14px;font-weight:800;color:var(--text);margin:0 0 10px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between}',
      '.tg-sub{display:block;font-size:12px;color:var(--mut);font-weight:400;margin-top:2px}',
      '.tg-wrap{overflow-x:auto}',
      '.tg-t{width:100%;border-collapse:collapse;font-size:13px}',
      '.tg-t th{text-align:start;font-size:11.5px;color:var(--mut);font-weight:700;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}',
      '.tg-t td{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:middle}',
      '.tg-t tr:last-child td{border-bottom:0}',
      '@media (max-width:620px){.tg-t.stack thead{display:none}.tg-t.stack tr{display:block;padding:10px 0;border-bottom:1px solid var(--line)}.tg-t.stack tr:last-child{border-bottom:0}.tg-t.stack td{display:block;border:0;padding:3px 0}.tg-t.stack .tg-meter{max-width:260px}}',
      '.tg-st{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:6px;font-size:11.5px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
      '.tg-st.ok{background:var(--green-soft);color:var(--green)}',
      '.tg-st.bad{background:var(--red-soft);color:var(--red)}',
      '.tg-st.gold{background:var(--gold-tint);color:var(--text)}',
      '.tg-meter{position:relative;height:8px;border-radius:5px;background:var(--surface-2);min-width:120px;margin-top:5px}',
      '.tg-meter i{position:absolute;inset-block:0;inset-inline-start:0;border-radius:5px;background:var(--gold)}',
      '.tg-meter u{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--text-2);opacity:.55}',
      '.tg-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:38px;padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--surface);color:var(--text);font:inherit;font-size:13px;font-weight:700;cursor:pointer;transition:transform .12s cubic-bezier(0.23,1,0.32,1),background .15s}',
      '.tg-btn:active{transform:scale(.97)}',
      '.tg-btn.go{background:var(--gold);border-color:var(--gold);color:#fff}',
      '.tg-btn.wa{background:var(--green);border-color:var(--green);color:#fff;min-height:44px}',
      '.tg-btn.sm{min-height:32px;padding:5px 10px;font-size:12px}',
      '.tg-btn:disabled{opacity:.5;cursor:not-allowed;transform:none}',
      '.tg-in{min-height:36px;padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--text);font:inherit;font-size:13px;max-width:100%}',
      '.tg-in.n{width:92px;font-family:var(--font-mono);direction:ltr}',
      '.tg-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}',
      '.tg-call{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--line)}',
      '.tg-call:last-child{border-bottom:0}',
      '.tg-call b{font-size:15px;color:var(--text)}',
      '.tg-call form{margin:0}',
      '.tg-note{font-size:12.5px;color:var(--mut);margin:8px 0 0}',
      /* «يومي» — the employee's day, in sections: each one a titled block of its own, so
         nothing runs into the next. The money sits on the one dark block of the page. */
      '.tg-day{max-width:680px;margin-inline:auto;display:grid;gap:18px}',
      '.tg-hero{background:#292925;color:#F4EFE6;border-radius:18px;padding:22px 20px 18px}',
      '.tg-hero>p:first-child{margin:0;font-size:13.5px;font-weight:700;color:#CFC6B4}',
      '.tg-hero .big{display:flex;align-items:baseline;gap:8px;margin:2px 0 14px;color:#E3C27A;font-weight:800;font-size:clamp(44px,14vw,64px);line-height:1.05;letter-spacing:-.02em}',
      '.tg-hero .big .tg-num{font-family:inherit}',
      '.tg-hero .big small{font-size:16px;font-weight:700;color:#CFC6B4;letter-spacing:0}',
      '.tg-road{position:relative;height:12px;border-radius:6px;background:#45413A;overflow:hidden}',
      '.tg-road i{position:absolute;inset-block:0;inset-inline-start:0;border-radius:6px;background:#E3C27A}',
      '.tg-road.go i{animation:tgGrow .8s cubic-bezier(0.23,1,0.32,1) both}',
      '@keyframes tgGrow{from{inline-size:0}}',
      '.tg-hero .tg-ends{color:#CFC6B4}.tg-hero .tg-ends b{color:#F4EFE6}',
      '.tg-ends{display:flex;justify-content:space-between;gap:10px;margin-top:7px;font-size:12.5px;color:var(--text-2)}',
      '.tg-ends b{color:var(--text)}',
      '.tg-hero .fine{margin:8px 0 0;font-size:11.5px;color:#A79F8F}',
      '.tg-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px;padding-top:14px;border-top:1px solid #45413A}',
      '.tg-chips>span{display:inline-block;padding:6px 12px;border-radius:9px;background:#3A362F;font-size:12.5px;color:#CFC6B4}',
      '.tg-chips b{color:#F4EFE6;font-size:14px}',
      '.tg-chips .first{background:#E3C27A;color:#292925}.tg-chips .first b{color:#292925}',
      '.tg-sx{background:var(--surface);border:1px solid var(--line);border-radius:16px;overflow:hidden}',
      '.tg-sx>header{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;justify-content:space-between;padding:13px 16px;background:var(--surface-2);border-bottom:1px solid var(--line)}',
      '.tg-sx>header h3{margin:0;font-size:16px;font-weight:800;color:var(--text)}',
      '.tg-sx>header span{font-size:12px;color:var(--text-2)}',
      '.tg-sx>.in{padding:2px 16px 6px}',
      '.tg-sx>footer{padding:11px 16px;border-top:1px solid var(--line);font-size:12.5px;color:var(--text-2);background:var(--surface)}',
      '.tg-sx>footer b{color:var(--text)}',
      '.tg-race{display:grid;grid-template-columns:auto 1fr auto;gap:4px 12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line)}',
      '.tg-race:last-child{border-bottom:0}',
      '.tg-race .pl{width:34px;height:34px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:15px;background:var(--surface-2);color:var(--text-2)}',
      '.tg-race.p1 .pl{background:var(--gold);color:#fff}',
      '.tg-race .who{font-weight:800;color:var(--text);font-size:14.5px;display:flex;gap:8px;align-items:center}',
      '.tg-race .pc{font-weight:800;color:var(--text);font-size:15px}',
      '.tg-race .tg-meter{grid-column:2 / 4;margin:0;height:8px;min-width:0}',
      '.tg-race.me{margin-inline:-16px;padding-inline:16px;background:var(--gold-tint)}',
      '.tg-hot{padding:16px 0;border-bottom:1px solid var(--line)}',
      '.tg-hot:last-child{border-bottom:0}',
      '.tg-hot h4{margin:0;font-size:17px;color:var(--text);display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between}',
      '.tg-hot .say{margin:8px 0 10px;font-size:14px;color:var(--text-2);line-height:1.6}',
      '.tg-hot .say b{display:block;font-size:19px;color:var(--green);line-height:1.4}',
      '.tg-hot .tg-meter{height:10px;max-width:none}',
      '.tg-hot .who{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}',
      '.tg-hot .who form{margin:0}',
      '.tg-win{display:flex;gap:10px;align-items:baseline;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--line);font-size:14px;color:var(--text)}',
      '.tg-win:last-child{border-bottom:0}',
      '.tg-win em{font-style:normal;font-weight:800;color:var(--green);white-space:nowrap}',
      '.tg-win em.z{color:var(--text-2);font-weight:700;font-size:12.5px}',
      '.tg-rec{display:flex;align-items:flex-end;gap:10px;height:132px;padding:14px 0 6px}',
      '.tg-rec div{flex:1;min-width:0;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:5px;height:100%}',
      '.tg-rec i{display:block;width:100%;max-width:54px;min-height:3px;border-radius:5px 5px 2px 2px;background:var(--surface-2);border:1px solid var(--line)}',
      '.tg-rec i.fin{background:var(--gold);border-color:var(--gold)}',
      '.tg-rec i.now{background:var(--gold-tint);border-color:var(--gold)}',
      '.tg-rec b{font-size:12px;color:var(--text)}',
      '.tg-rec span{font-size:11px;color:var(--text-2)}',
      '.tg-cheer{padding:14px 16px;border-radius:16px;background:var(--green-soft);color:var(--green);font-weight:800;font-size:15px;animation:tgCheer .5s cubic-bezier(0.23,1,0.32,1) both}',
      '.tg-cheer>span{display:block;font-weight:400;font-size:13px;color:var(--text);margin-top:2px}',
      '@keyframes tgCheer{from{opacity:0;transform:translateY(8px) scale(.98)}}',
      '.tg-sx summary{cursor:pointer;padding:13px 16px;font-weight:800;color:var(--text);font-size:16px;min-height:48px;background:var(--surface-2)}',
      '.tg-sx[open] summary{border-bottom:1px solid var(--line)}',
      '.tg-sx summary:focus-visible,.tg-btn:focus-visible,.tg-in:focus-visible{outline:2px solid var(--gold);outline-offset:2px}',
      '.tg-day ::selection{background:var(--gold-tint)}',
      '@media (prefers-reduced-motion:reduce){.tg-btn{transition:none}.tg-btn:active{transform:none}.tg-road.go i,.tg-cheer{animation:none}}'
    ].join('');
    document.head.appendChild(s);
  }

  function shiftMonth(mk, by) {
    var y = Number(mk.slice(0, 4)), m = Number(mk.slice(5, 7)) - 1 + by;
    var d = new Date(Date.UTC(y, m, 1));
    return d.getUTCFullYear() + '-' + ('0' + (d.getUTCMonth() + 1)).slice(-2);
  }
  function monthBar() {
    return '<div class="tg-row"><button class="tg-btn sm" data-tg="month" data-by="-1">‹</button>' +
      '<b class="tg-num">' + esc(S.month) + '</b>' +
      '<button class="tg-btn sm" data-tg="month" data-by="1">›</button></div>';
  }

  /* ---------------------------------------------------------------- «أهدافي» */

  var NOTE = { pending: ['ملاحظتك عند المشرف', 'Your note is with the supervisor'], approved: ['المشرف قبل الملاحظة — انحسبت', 'Supervisor accepted — counted'], rejected: ['المشرف ما قبل الملاحظة', 'Supervisor did not accept'] };

  function unitRow(u, canNote) {
    var has = u.target > 0, w = has ? Math.min(100, Math.round(100 * u.revenue / u.target)) : 0;
    var state = !has ? '<span class="tg-st">—</span>'
      : u.over > 0 ? '<span class="tg-st ok">' + esc(T('فوق الهدف بـ ', 'Above by ')) + sar(u.over) + '</span>'
        : '<span class="tg-st">' + esc(T('باقي ', 'To go ')) + sar(u.target - u.revenue) + '</span>';
    var rate = u.rating == null ? '<span class="tg-sub">' + esc(T('ما فيه تقييم هالشهر', 'No rating this month')) + '</span>'
      : num(Number(u.rating).toFixed(2)) + ' <span class="tg-sub">' + num(u.reviews) + ' ' + esc(T('تقييم', 'reviews')) + '</span>';
    var extra = '';
    if (u.rating_blocked) {
      extra += '<span class="tg-st bad">' + esc(T('التقييم تحت 4.75 — الشقة ما تنحسب هالشهر', 'Rated under 4.75 — this unit does not count this month')) + '</span>';
    }
    if (u.note) {
      extra += '<span class="tg-sub">' + esc(T(NOTE[u.note.status][0], NOTE[u.note.status][1])) + '</span>';
    } else if (u.rating_blocked && canNote) {
      extra += '<div class="tg-row" style="margin-top:6px"><input class="tg-in" data-note-unit="' + esc(u.unit) + '" maxlength="400" placeholder="' +
        esc(T('السبب مو بيدك؟ اكتبه (مثال: عيب من المطور)', 'Not in your hands? Say why (e.g. a developer defect)')) + '">' +
        '<button class="tg-btn sm" data-tg="note" data-unit="' + esc(u.unit) + '">' + esc(T('ارفع ملاحظة للمشرف', 'Send note to supervisor')) + '</button></div>';
    }
    return '<tr><td><b>' + nm(u.name) + '</b></td>' +
      '<td>' + sar(u.revenue) + ' <span class="tg-sub">' + esc(T('الهدف ', 'Target ')) + (has ? sar(u.target) : '—') + '</span>' +
      '<div class="tg-meter"><i style="width:' + w + '%"></i></div></td>' +
      '<td>' + state + '</td><td>' + rate + extra + '</td></tr>';
  }

  var MON = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  var MON_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function monName(mk) { var k = Number(String(mk).slice(5, 7)) - 1; return T(MON[k] || mk, MON_EN[k] || mk); }
  function nights(n) { return n === 1 ? T('ليلة وحدة', '1 night') : n === 2 ? T('ليلتين', '2 nights') : num(n) + ' ' + T(n <= 10 ? 'ليالي' : 'ليلة', 'nights'); }

  /* Which apartments were above target last time this employee looked — to cheer a new one once. */
  function newlyAbove(d) {
    var key = 'tgAbove:' + (d.employee || '') + ':' + (d.month || ''), now = [], fresh = [], seen = null;
    arr(d.day && d.day.units).forEach(function (u) { if (u.over > 0) now.push(u.unit); });
    try { seen = JSON.parse(localStorage.getItem(key) || 'null'); localStorage.setItem(key, JSON.stringify(now)); } catch (e) { seen = null; }
    if (!seen) return [];
    arr(d.day.units).forEach(function (u) { if (u.over > 0 && seen.indexOf(u.unit) < 0) fresh.push(u); });
    return fresh;
  }

  function hotRow(u, guests, action) {
    var w = u.target > 0 ? Math.min(100, Math.round(100 * u.revenue / u.target)) : 0, say;
    if (u.over > 0) {
      say = esc(T('فوق الهدف. كل ليلة زيادة تنباع:', 'Above target. Every extra night sold:')) + '<b>≈ ' + sar(u.night_value) + esc(T(' لك', ' for you')) + '</b>';
    } else {
      say = esc(T('باقي ', 'Needs ')) + sar(u.gap) + ' (' + nights(u.nights_to_target) + ')' + esc(T(' وتوصل الهدف. بعدها كل ليلة:', ' to reach target. After that every night:')) +
        '<b>≈ ' + sar(u.night_value) + esc(T(' لك', ' for you')) + '</b>';
    }
    var h = '<div class="tg-hot"><h4>' + nm(u.name) +
      (u.over > 0 ? '<span class="tg-st ok">' + esc(T('كسبت منها ', 'Earned ')) + sar(u.mine) + '</span>' : '<span class="tg-st gold">' + esc(T('قريبة من الهدف', 'Close to target')) + '</span>') + '</h4>' +
      '<p class="say">' + say + '</p>' +
      '<div class="tg-meter"><i style="width:' + w + '%"></i></div>' +
      '<div class="tg-ends"><span>' + sar(u.revenue) + ' ' + esc(T('من', 'of')) + ' ' + sar(u.target) + '</span><span>' + nights(u.empty) + ' ' + esc(T('فاضية', 'empty')) +
      (u.next_empty ? ' · ' + esc(T('أقربها ', 'next ')) + num(day(u.next_empty)) : '') + '</span></div><div class="who">';
    if (!guests.length) {
      h += '<span class="tg-sub">' + esc(T('ما فيه ضيف مناسب لها اليوم بالقائمة. افتح «دفتر العملاء» أو ارجع بكرة.', 'No matching guest for it today. Open the client book or come back tomorrow.')) + '</span>';
    }
    h += '</div>';
    guests.forEach(function (it) {
      h += '<div class="tg-call" style="padding:10px 0"><div><b>' + esc(it.name) + '</b>' + lastStay(it) + '</div>' +
        '<form method="POST" action="' + esc(action) + '" target="_blank" rel="noopener" data-tg-form="wa"><input type="hidden" name="g" value="' + esc(it.g) + '">' +
        '<button type="submit" class="tg-btn wa">' + esc(T('راسل ', 'Message ')) + esc(it.name) + '</button></form></div>';
    });
    return h + '</div>';
  }

  function sx(title, hint, body, foot) {
    return '<section class="tg-sx"><header><h3>' + esc(title) + '</h3>' + (hint ? '<span>' + hint + '</span>' : '') + '</header><div class="in">' + body + '</div>' +
      (foot ? '<footer>' + foot + '</footer>' : '') + '</section>';
  }

  function meView(d) {
    if (!d.linked && d.is_admin) {
      return emptyState(T('هالصفحة للموظف', 'This page is the employee’s view'),
        T('حسابك حساب مالك وما له شقق. شغلك كله تحت «الإدارة» فوق.', 'Yours is an owner login with no units. Your work is under “Admin” above.'), '🎯');
    }
    if (!d.linked) {
      return emptyState(T('حسابك مو مربوط بموظف', 'Your login is not linked to an employee'),
        T('كلّم المالك يربط حسابك من «مين هو مين».', 'Ask the owner to link your login.'), '🎯');
    }
    var m = d.money || {}, y = d.day || {}, units = arr(m.units), h = '<div class="tg-day">', b;
    var byUnit = {}, action = '/api/book/wa' + (tok() ? '?token=' + encodeURIComponent(tok()) : '');
    var race = y.race || {}, ms = y.mission || {};
    arr(y.units).forEach(function (u) { byUnit[u.unit] = u; });

    /* a new apartment crossed its target since the last visit */
    newlyAbove(d).forEach(function (u) {
      h += '<div class="tg-cheer">' + nm(u.name) + ' ' + esc(T('تعدّت هدفها', 'passed its target')) +
        '<span>' + esc(T('من الحين كل ليلة زيادة عليها ≈ ', 'From now every extra night on it ≈ ')) + sar(u.night_value) + esc(T(' لك.', ' for you.')) + '</span></div>';
    });

    /* 1 — my money (the one dark block) */
    var amount = Number(y.amount != null ? y.amount : m.amount) || 0, pot = Math.max(Number(y.potential) || 0, amount);
    h += '<div class="tg-hero"><p>' + esc(m.final ? T('كسبت في ', 'You earned in ') + monName(d.month) + T(' — معتمد', ' — approved')
      : y.live ? T('جبت هالشهر للحين', 'Earned so far this month') : T('عمولة ', 'Commission for ') + monName(d.month)) + '</p>' +
      '<div class="big">' + num(Math.round(amount).toLocaleString('en-US')) + '<small>' + esc(T('ر.س', 'SAR')) + '</small></div>';
    if (y.live && m.has_targets) {
      h += '<div class="tg-road' + (S.grown ? '' : ' go') + '"><i style="inline-size:' + (pot > 0 ? Math.max(2, Math.round(100 * amount / pot)) : 0) + '%"></i></div>' +
        '<div class="tg-ends"><span>' + esc(T('الحين', 'Now')) + '</span><span>' + esc(T('تقدر توصل ', 'You can reach ')) + '<b>' + sar(pot) + '</b></span></div>' +
        '<p class="fine">' + esc(T('لو انباعت نص لياليك الفاضية بسعرها المعتاد. تقدير، مو وعد.', 'If half your empty nights sell at their usual price. An estimate, not a promise.')) + '</p>';
      S.grown = true;
    }
    if (m.won_prize > 0) {
      h += '<div class="tg-chips"><span class="first">' + esc(T('الأول هالشهر — الجائزة ', 'First this month — prize ')) + '<b>' + sar(m.won_prize) + '</b></span></div>';
    } else if (y.live && race.place) {
      h += '<div class="tg-chips"><span' + (race.place === 1 ? ' class="first"' : '') + '>' + esc(T('ترتيبك ', 'Your place ')) + '<b>' + num(race.place) + '</b>' + esc(T(' من ', ' of ')) + num(race.of) + '</span>' +
        '<span>' + esc(T('رسائلك اليوم ', 'Messages today ')) + '<b>' + num(ms.today || 0) + '</b></span>' +
        (ms.streak > 1 ? '<span><b>' + num(ms.streak) + '</b>' + esc(T(' أيام ورا بعض', ' days in a row')) + '</span>' : '') + '</div>';
    }
    h += '</div>';
    if (!m.has_targets) {
      h += '<div class="tg-banner" style="margin:0">' + esc(T('أهداف هالربع ما اعتمدها المالك للحين — العمولة والسباق يبدون بعد الاعتماد.',
        'This quarter’s targets are not approved yet — commission and the race start once they are.')) + '</div>';
    }

    /* 2 — the race */
    if (arr(race.board).length) {
      b = '';
      var top = 0;
      arr(race.board).forEach(function (r) { top = Math.max(top, Number(r.pct) || 0); });
      arr(race.board).forEach(function (r) {
        b += '<div class="tg-race' + (r.place === 1 ? ' p1' : '') + (r.me ? ' me' : '') + '"><span class="pl">' + num(r.place) + '</span>' +
          '<span class="who">' + esc(r.employee) + (r.me ? '<span class="tg-st gold">' + esc(T('أنت', 'You')) + '</span>' : '') + '</span>' +
          '<span class="pc">' + pct(r.pct) + '</span>' +
          '<div class="tg-meter"><i style="width:' + (top > 0 ? Math.round(100 * r.pct / top) : 0) + '%"></i></div></div>';
      });
      var foot = y.live
        ? (race.place === 1 ? T('أنت الأول. حافظ عليها لآخر الشهر.', 'You are first. Hold it to month end.')
          : T('باقي لك دخل ', 'You need ') + '<b>' + sar(race.to_first) + '</b>' + T(' على شققك وتصير الأول.', ' more revenue on your units to be first.'))
        : '';
      h += sx(T('سباق الشهر', 'This month’s race'), esc(T('الأول ياخذ ', 'First place takes ')) + '<b style="color:var(--text)">' + sar(race.prize) + '</b>',
        b, y.live ? (race.place === 1 ? esc(foot) : foot) : '') ;
    }

    if (y.live) {
      /* 3 — the nearest money */
      var hot = arr(y.nearest).map(function (id) { return byUnit[id]; }).filter(Boolean);
      b = '';
      hot.forEach(function (u) {
        var guests = arr(d.list && d.list.items).filter(function (it) { return String(it.unit) === String(u.unit); }).slice(0, 3);
        b += hotRow(u, guests, action);
      });
      if (m.has_targets) {
        h += sx(T('أقرب فلوس', 'Nearest money'), esc(T('اضغط اسم الضيف ويفتح واتساب برسالة جاهزة', 'Tap a guest: WhatsApp opens with the message written')),
          b || '<p class="tg-note" style="margin:14px 0">' + esc(T('ما فيه ليالي فاضية تقدر تكسب منها الحين. ارجع بكرة.', 'No empty nights to earn from right now. Come back tomorrow.')) + '</p>');
      }

      /* 4 — wins */
      if (arr(y.wins).length) {
        b = '';
        arr(y.wins).forEach(function (wn) {
          b += '<div class="tg-win"><span>' + esc(wn.guest) + ' · ' + nm(wn.unit_name) + ' · ' + nights(wn.nights) + '</span>' +
            (wn.mine > 0 ? '<em>' + num('+' + Math.round(wn.mine).toLocaleString('en-US')) + ' ' + esc(T('ر.س', 'SAR')) + '</em>' : '<em class="z">' + esc(T('قرّبك من الهدف', 'Closer to target')) + '</em>') + '</div>';
        });
        h += sx(T('آخر الحجوزات على شققي', 'Latest bookings on my units'), esc(T('وكم زاد كل حجز بعمولتك', 'and what each added to your commission')), b);
      }
    }

    /* 5 — my record */
    var rec = y.record || {}, months = arr(rec.months), peak = 0;
    months.forEach(function (x) { peak = Math.max(peak, Number(x.amount) || 0); });
    if (months.length) {
      b = '<div class="tg-rec">';
      months.forEach(function (x) {
        b += '<div><b>' + num(Math.round(x.amount).toLocaleString('en-US')) + '</b><i class="' + (x.final ? 'fin' : 'now') + '" style="height:' + (peak > 0 ? Math.round(72 * x.amount / peak) : 0) + 'px"></i><span>' + esc(monName(x.month)) + '</span></div>';
      });
      b += '</div>';
      h += sx(T('سجلّي', 'My record'), esc(T('المجموع ', 'Total ')) + '<b style="color:var(--text)">' + sar(rec.earned) + '</b>', b,
        (rec.best ? esc(T('أحسن شهر: ', 'Best month: ')) + '<b>' + esc(monName(rec.best.month)) + ' ' + sar(rec.best.amount) + '</b> · ' : '') +
        esc(T('الغامق معتمد من المالك، والفاتح لسا.', 'Solid is approved by the owner; light is not yet.')));
    }

    /* 6 — every unit */
    h += '<details class="tg-sx"' + (y.live ? '' : ' open') + '><summary>' + esc(T('كل شققي', 'All my units')) + ' (' + units.length + ')</summary><div class="in">' +
      '<div class="tg-wrap"><table class="tg-t stack"><thead><tr><th>' + esc(T('الشقة', 'Unit')) + '</th><th>' + esc(T('دخل الشهر', 'Month revenue')) + '</th><th>' +
      esc(T('الحالة', 'Status')) + '</th><th>' + esc(T('التقييم', 'Rating')) + '</th></tr></thead><tbody>';
    if (!units.length) h += '<tr><td colspan="4">' + esc(T('ما عندك شقق بأهداف معتمدة هالشهر.', 'No units with approved targets this month.')) + '</td></tr>';
    units.forEach(function (u) { h += unitRow(u, !m.final); });
    h += '</tbody></table></div></div><footer>' + esc(T('الليالي المقفلة تنقص من الهدف. وإذا السوق كله نزل، هدفك ينزل معه آخر الشهر. التقييم تحت 4.75 يوقف عمولة الشقة إلا إذا قبل المشرف ملاحظتك.',
        'Blocked nights lower the target. If the whole market drops, your target drops with it at month end. A rating under 4.75 stops the unit’s commission unless the supervisor accepts your note.')) + '</footer></details>';
    return h + '</div>';
  }

  /* ---------------------------------------------------------------- الفريق (manager) */

  /* The apartments farthest from their revenue target, worst first. (An older shape of this
     list, saved before 2026-11-15, carried occupancy instead: those rows are skipped.) */
  function rescueTable(rows) {
    rows = arr(rows).filter(function (r) { return r.target > 0; });
    if (!rows.length) return '<p class="tg-note">' + esc(T('ما فيه شقق تحت هدفها.', 'No units under their target.')) + '</p>';
    var h = '<div class="tg-wrap"><table class="tg-t stack"><thead><tr><th>' + esc(T('الشقة', 'Unit')) + '</th><th>' + esc(T('الموظف', 'Employee')) +
      '</th><th>' + esc(T('دخلها من هدفها', 'Revenue vs target')) + '</th><th>' + esc(T('باقي للهدف', 'Left to target')) +
      '</th><th>' + esc(T('ليالي فاضية', 'Empty nights')) + '</th></tr></thead><tbody>';
    rows.forEach(function (r) {
      h += '<tr><td><b>' + nm(r.name) + '</b></td><td>' + esc(r.employee || '—') + '</td>' +
        '<td>' + pct(r.pct) + ' <span class="tg-sub">' + sar(r.revenue) + ' ' + esc(T('من', 'of')) + ' ' + sar(r.target) + '</span>' +
        '<div class="tg-meter"><i style="width:' + Math.min(100, Math.round(100 * r.pct)) + '%"></i></div></td>' +
        '<td>' + sar(r.gap) + '</td><td>' + (r.empty ? num(r.empty) : '<span class="tg-sub">' + esc(T('ما باقي ليالي', 'none left')) + '</span>') + '</td></tr>';
    });
    return h + '</tbody></table></div>';
  }

  /* The guest's last booking with us: the number an employee searches in Hostaway to read the
     conversation before writing. */
  function lastStay(it) {
    var l = it && it.last;
    if (!l || !l.booking) return '';
    return '<span class="tg-sub">' + esc(T('آخر سكن: ', 'Last stay: ')) + nm(l.unit_name || '—') + ' · ' + num(day(l.arrival)) + ' ← ' + num(day(l.departure)) +
      ' · ' + nights(l.nights) + (l.channel ? ' · ' + esc(l.channel) : '') + '</span>' +
      '<span class="tg-sub">' + esc(T('رقم الحجز: ', 'Booking no.: ')) + '<a href="https://dashboard.hostaway.com/reservations/' + encodeURIComponent(l.booking) +
      '" target="_blank" rel="noopener" style="color:var(--gold);font-weight:700">' + num(l.booking) + '</a>' +
      esc(T(' — اضغطه يفتح الحجز والمحادثة في Hostaway', ' — tap to open the booking and conversation in Hostaway')) + '</span>';
  }

  /* Rating notes: the employee says the low rating was not theirs; the supervisor decides once. */
  function notesBox(rows) {
    var h = '<div class="tg-box"><div class="tg-h">' + esc(T('ملاحظات التقييم', 'Rating notes')) +
      '<span class="tg-sub">' + esc(T('الموظف يقول التقييم نزل بسبب شي مو بيده (عيب مطور، العمارة). قبولك يرجّع عمولة الشقة لهالشهر. القرار مرة وحدة.',
        'The employee says the low rating was not in their hands (developer defect, the building). Accepting restores the unit’s commission for the month. Decided once.')) + '</span></div>';
    if (!arr(rows).length) return h + '<p class="tg-note">' + esc(T('ما فيه ملاحظات هالشهر.', 'No notes this month.')) + '</p></div>';
    arr(rows).forEach(function (n) {
      var right = n.status === 'pending'
        ? '<div class="tg-row"><button class="tg-btn sm go" data-tg="noteYes" data-id="' + esc(n.id) + '">' + esc(T('اقبل', 'Accept')) + '</button>' +
          '<button class="tg-btn sm" data-tg="noteNo" data-id="' + esc(n.id) + '">' + esc(T('ارفض', 'Refuse')) + '</button></div>'
        : '<span class="tg-st' + (n.status === 'approved' ? ' ok' : '') + '">' + esc(n.status === 'approved' ? T('انقبلت', 'Accepted') : T('انرفضت', 'Refused')) + '</span>';
      h += '<div class="tg-call"><div><b>' + nm(n.unit_name) + '</b> <span class="tg-sub">' + esc(n.employee) + ' · ' + esc(T('التقييم ', 'Rating ')) +
        (n.rating == null ? '—' : num(Number(n.rating).toFixed(2))) + '</span><span class="tg-sub">' + esc(n.reason) + '</span></div>' + right + '</div>';
    });
    return h + '</div>';
  }

  /* The operations manager's own month: her share so far and the steps of her team bonus. */
  function mineBox(v) {
    if (!v || !v.is_set) return '';
    var h = '<div class="tg-day" style="margin-bottom:18px"><div class="tg-hero"><p>' + esc(v.final ? T('حسبتي — معتمدة', 'My month — approved') : v.closed ? T('حسبتي لهالشهر', 'My month') : T('حسبتي هالشهر للحين', 'My month so far')) + '</p>' +
      '<div class="big">' + num(Math.round(v.amount).toLocaleString('en-US')) + '<small>' + esc(T('ر.س', 'SAR')) + '</small></div>' +
      '<div class="tg-road"><i style="inline-size:' + Math.min(100, Math.round(100 * (v.units ? v.above / v.units : 0) / 0.4)) + '%"></i></div>' +
      '<div class="tg-ends"><span>' + esc(T('شقق فوق هدفها: ', 'Units above target: ')) + '<b>' + num(v.above + ' / ' + v.units) + '</b> (' + pct(v.rate) + ')</span></div>' +
      '<div class="tg-chips">';
    arr(v.steps).forEach(function (st) {
      h += '<span' + (st.left === 0 ? ' class="first"' : '') + '>' + pct(st.need) + esc(T(' من الشقق = ', ' of units = ')) + '<b>' + sar(st.sar) + '</b>' +
        (st.left === 0 ? esc(T(' ✓', ' ✓')) : esc(T(' · باقي ', ' · ')) + num(st.left) + esc(T(' شقة', ' to go'))) + '</span>';
    });
    h += '</div><p class="fine">' + esc(T('حسبتك = نصيبك من عمولات الفريق + جائزة الفريق. الجائزة تثبت بعد نهاية الشهر.', 'Your month = your share of the team’s commission + the team bonus. The bonus is fixed after month end.')) + '</p></div></div>';
    return h;
  }

  /* Her page, top to bottom in the order she works: her own month, the notes waiting for her
     decision, who is moving, and the apartments to rescue. */
  function teamView(d) {
    var h = mineBox(d.mine) + notesBox(d.notes);
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('نشاط الفريق', 'Team activity')) +
      '<span class="tg-sub">' + esc(T('رسائل كل موظف هالشهر، وكم شقة عنده فوق هدفها.', 'Each employee’s messages this month, and how many of their units are above target.')) + '</span></div>' +
      '<div class="tg-wrap"><table class="tg-t"><thead><tr><th>' +
      esc(T('الموظف', 'Employee')) + '</th><th>' + esc(T('رسائل واتساب', 'WhatsApp messages')) + '</th><th>' +
      esc(T('شقق فوق هدفها', 'Units above target')) + '</th></tr></thead><tbody>';
    if (!arr(d.activity).length) h += '<tr><td colspan="3">' + esc(T('ما فيه أهداف معتمدة هالشهر.', 'No approved targets this month.')) + '</td></tr>';
    arr(d.activity).forEach(function (r) {
      h += '<tr><td>' + esc(r.employee) + '</td><td>' + num(r.contacts) + '</td><td>' + num(r.above + ' / ' + r.units) + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('قائمة الإنقاذ', 'Rescue list')) +
      '<span class="tg-sub">' + esc(T('أبعد الشقق عن هدف دخلها هالشهر، الأبعد أول. تنحفظ نسخة يوم 10 ويوم 20.', 'The units farthest from their revenue target this month, worst first. A copy is saved on day 10 and day 20.')) + '</span></div>';
    if (d.quarter_state !== 'approved') h += '<p class="tg-note">' + esc(T('أهداف الربع ما اعتمدت، فالقائمة فاضية.', 'Quarter targets are not approved, so the list is empty.')) + '</p>';
    h += rescueTable(d.rescue) + '</div>';
    arr(d.snapshots).forEach(function (s) {
      h += '<div class="tg-box"><div class="tg-h">' + esc(T('نسخة يوم ', 'Copy of day ')) + num(s.day) + '</div>' + rescueTable(s.units) + '</div>';
    });
    return h;
  }

  /* ---------------------------------------------------------------- الإدارة (owner only) */

  function opt(v, label, sel) { return '<option value="' + esc(v) + '"' + (String(v) === String(sel) ? ' selected' : '') + '>' + esc(label) + '</option>'; }

  /* The owner's board: who is where, in one look — the first thing on «الإدارة». */
  function ownerBoard(d) {
    var s = d.sheet || {}, emps = arr(s.employees).slice().sort(function (a, b) { return (a.rank || 99) - (b.rank || 99); });
    var act = {}, g = s.team_goal || {}, top = 0, mgr = d.mine || {}, winners = (s.prize && s.prize.winners) || [];
    arr(d.activity).forEach(function (a) { act[a.employee] = a; });
    emps.forEach(function (e) { top = Math.max(top, Number(e.pct) || 0); });
    var h = '<div class="tg-day" style="max-width:none;margin-bottom:18px"><div class="tg-hero"><p>' + esc(T('لوحة المالك — ', 'Owner’s board — ')) + esc(monName(s.month || d.month)) +
      (s.approval ? esc(T(' · معتمد', ' · approved')) : s.closed ? esc(T(' · الشهر خلص، ينتظر اعتمادك', ' · month ended, waiting for your approval')) : esc(T(' · الشهر شغّال', ' · month running'))) + '</p>' +
      '<div class="big">' + num(Math.round(s.total_paid || 0).toLocaleString('en-US')) + '<small>' + esc(T('ر.س ينصرف للحين (الفريق + المديرة + الجائزة)', 'SAR to pay so far (team + manager + prize)')) + '</small></div>' +
      '<div class="tg-chips">' +
      '<span>' + esc(T('دخل الشقق ', 'Revenue ')) + '<b>' + sar(s.revenue) + '</b></span>' +
      '<span>' + esc(T('فوق الأهداف ', 'Above targets ')) + '<b>' + sar(s.over) + '</b></span>' +
      '<span>' + esc(T('شقق فوق هدفها ', 'Units above target ')) + '<b>' + num((g.above || 0) + ' / ' + (g.units || 0)) + '</b> (' + pct(g.rate) + ')</span>' +
      (mgr.is_set ? '<span>' + esc(T('حسبة المديرة ', 'Manager ')) + '<b>' + sar(mgr.amount) + '</b></span>' : '') +
      '</div></div>';
    var b = '';
    if (!emps.length) b = '<p class="tg-note" style="margin:14px 0">' + esc(T('ما فيه أهداف معتمدة لهالشهر.', 'No approved targets for this month.')) + '</p>';
    emps.forEach(function (e) {
      var a = act[e.employee] || {}, won = winners.indexOf(e.employee) >= 0;
      b += '<div class="tg-race' + (e.rank === 1 ? ' p1' : '') + '"><span class="pl">' + num(e.rank || '—') + '</span>' +
        '<span class="who">' + esc(e.employee) + (won ? '<span class="tg-st gold">' + esc(T('الجائزة', 'Prize')) + '</span>' : '') + '</span>' +
        '<span class="pc">' + pct(e.pct) + '</span>' +
        '<div class="tg-meter"><i style="width:' + (top > 0 ? Math.round(100 * e.pct / top) : 0) + '%"></i></div>' +
        '<span class="tg-sub" style="grid-column:2 / 4;margin:0">' + sar(e.revenue) + ' ' + esc(T('من هدف', 'of target')) + ' ' + sar(e.target) +
        ' · ' + esc(T('شقق فوق هدفها ', 'above target ')) + num(e.above + ' / ' + e.units) +
        ' · ' + esc(T('رسائل: اليوم ', 'messages: today ')) + num(a.today || 0) + esc(T('، الشهر ', ', month ')) + num(a.contacts || 0) +
        ' · ' + esc(T('عمولته ', 'commission ')) + '<b style="color:var(--text)">' + sar(e.commission != null ? e.commission : e.paid) + '</b></span></div>';
    });
    h += sx(T('ترتيب الفريق', 'Team standing'), esc(T('النسبة = دخل شققه ÷ أهدافها. الأول ياخذ ', 'Share = his units’ revenue ÷ their targets. First takes ')) + '<b style="color:var(--text)">' + sar((s.prize || {}).amount) + '</b>', b,
      esc(T('الأرقام تتحدث مع كل حجز. العمولة والجائزة تثبت بعد نهاية الشهر واعتمادك.', 'Figures move with every booking. Commission and prize are fixed after month end and your approval.')));
    return h + '</div>';
  }

  function adminView(d) {
    var f = d.flags || {}, h = ownerBoard(d), sy = (d.seed && d.seed.sync) || {};
    /* 1 — status + seed */
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('الحالة', 'Status')) + '</div><div class="tg-row">' +
      '<span class="tg-st">' + esc(T('من ينتصل عليهم: ', 'Callable: ')) + esc(arr(f.channels).join(' + ')) + '</span>' +
      '<span class="tg-st">' + esc(T('وافقوا على التواصل: ', 'Consented: ')) + num(d.consents) + '</span>' +
      '<span class="tg-st">' + esc(T('لا تتصل: ', 'Do not contact: ')) + num(d.dnc) + '</span></div>' +
      '<p class="tg-note">' + esc(T('الحجوزات المخزّنة: ', 'Stored bookings: ')) + num(d.seed.rows) + ' · ' +
      esc(T('ملف البداية: ', 'Seed file: ')) + esc(d.seed.imported_at ? d.seed.imported_at.slice(0, 16).replace('T', ' ') : T('ما انرفع', 'not uploaded')) + ' · ' +
      esc(T('آخر مزامنة: ', 'Last sync: ')) + esc(d.seed.synced_at ? d.seed.synced_at.slice(0, 16).replace('T', ' ') : '—') + '</p>' +
      '<div class="tg-row" style="margin-top:10px"><input type="file" id="tgSeedFile" accept=".csv" class="tg-in">' +
      '<button class="tg-btn go" data-tg="seed">' + esc(T('ارفع ملف البداية', 'Upload seed file')) + '</button>' +
      '<button class="tg-btn" data-tg="sync" id="tgSyncBtn"' + (sy.running ? ' disabled' : '') + '>' + esc(sy.running ? T('المزامنة شغّالة…', 'Sync running…') : T('مزامنة الآن', 'Sync now')) + '</button></div>' +
      '<p class="tg-note" id="tgSyncNote">' + esc(syncNote(sy)) + '</p>' +
      '<p class="tg-note">' + esc(T('الملف فيه أسماء وجوالات ضيوف: ينحفظ على السيرفر بس، وما يدخل GitHub.', 'The file holds guest names and phones: it is kept on the server only, never in GitHub.')) + '</p></div>';

    /* 2 — unmapped names */
    if (arr(d.seed.unmapped).length) {
      h += '<div class="tg-box"><div class="tg-h">' + esc(T('أسماء شقق ما انربطت', 'Listing names not matched')) +
        '<span class="tg-sub">' + esc(T('ما خمّنت. اختر الشقة الصح، أو خلّها «محذوفة — تاريخ فقط».', 'Nothing was guessed. Pick the right unit, or keep it as “deleted — history only”.')) + '</span></div>';
      arr(d.seed.unmapped).forEach(function (n) {
        var sel = '<select class="tg-in" data-name="' + esc(n.name) + '">' + opt('', T('محذوفة — تاريخ فقط', 'Deleted — history only'), '');
        arr(d.listings).forEach(function (l) { sel += opt(l.id, l.name, ''); });
        h += '<div class="tg-call"><b>' + esc(n.shown) + '</b><div class="tg-row">' + sel + '</select>' +
          '<button class="tg-btn sm" data-tg="map" data-name="' + esc(n.name) + '">' + esc(T('احفظ', 'Save')) + '</button></div></div>';
      });
      h += '</div>';
    }

    /* 3 — who is who + manager */
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('مين هو مين', 'Who is who')) +
      '<span class="tg-sub">' + esc(T('اربط كل حساب دخول بموظف من تقويم الموظفين. الحساب غير المربوط ما يشوف شي.', 'Link each login to a schedule employee. An unlinked login sees nothing.')) + '</span></div>';
    arr(d.users).forEach(function (u) {
      var sel = '<select class="tg-in" data-tg-change="link" data-user="' + esc(u.id) + '">' + opt('', T('— مو مربوط —', '— not linked —'), u.employee);
      arr(d.employees).forEach(function (e) { sel += opt(e, e, u.employee); });
      h += '<div class="tg-call"><b>' + esc(u.name) + '</b>' + sel + '</select></div>';
    });
    var ms = '<select class="tg-in" data-tg-change="manager">' + opt('', T('— ما تحدد —', '— not set —'), d.manager_user || '');
    arr(d.users).forEach(function (u) { ms += opt(u.id, u.name, d.manager_user || ''); });
    h += '<div class="tg-call"><b>' + esc(T('مدير التشغيل', 'Operations manager')) + '</b>' + ms + '</select></div></div>';

    /* 4 — quarter targets */
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('أهداف الربع ', 'Quarter targets ')) + esc(d.quarter) +
      '<div class="tg-row"><button class="tg-btn sm" data-tg="quarter" data-by="-1">‹</button><button class="tg-btn sm" data-tg="quarter" data-by="1">›</button>' +
      '<button class="tg-btn sm" data-tg="propose">' + esc(T('احسب الأهداف', 'Compute targets')) + '</button>' +
      (d.quarter_state === 'proposed' ? '<button class="tg-btn sm go" data-tg="approveQ">' + esc(T('اعتمد أهداف الربع', 'Approve quarter')) + '</button>' : '') +
      '</div></div>';
    h += '<p class="tg-note">' + esc(d.quarter_state === 'approved' ? T('معتمدة. نقل الشقق والحدود يتغير أول الربع الجاي.', 'Approved. Units and bounds change at the next quarter.')
      : d.quarter_state === 'proposed' ? T('مقترحة — هدف الدخل = متوسط آخر 3 شهور + ', 'Proposed — revenue target = the last 3 months’ average + ') + Math.round(((d.rules || {}).step || 0) * 100) + T('%. عدّل اللي تبي ثم اعتمد. لو خانة الهدف صفر اضغط «احسب الأهداف».', '%. Edit what you like, then approve. If a target shows zero, press “Compute targets”.')
        : T('ما انحسبت. اضغط «احسب الأهداف».', 'Not computed. Press “Compute targets”.')) + '</p>';
    if (arr(d.targets).length) {
      h += '<div class="tg-wrap"><table class="tg-t"><thead><tr><th>' + esc(T('الشقة', 'Unit')) + '</th><th>' + esc(T('الموظف', 'Employee')) + '</th><th>' +
        esc(T('هدف الدخل بالشهر', 'Monthly revenue target')) + '</th><th>' + esc(T('إشغال: برونزي / فضي / ذهبي', 'Occupancy: Bronze / Silver / Gold')) + '</th><th>' + esc(T('الحد الأدنى', 'Floor')) +
        '</th><th>' + esc(T('الحد الأعلى', 'Ceiling')) + '</th><th></th></tr></thead><tbody>';
      arr(d.targets).forEach(function (t) {
        var ed = t.status === 'proposed';
        h += '<tr><td><b>' + nm(t.name) + '</b>' + (t.basis === 'peers' ? '<span class="tg-sub">' + esc(T('شقة جديدة — من متوسط شقق مثلها', 'New unit — from similar units')) + '</span>' : '') +
          '</td><td>' + esc(t.employee || '—') + '</td>' +
          '<td>' + (ed ? '<input class="tg-in n" inputmode="numeric" data-f="rev_target" data-unit="' + esc(t.unit) + '" value="' + esc(Math.round(t.rev_target || 0)) + '">' : num(Math.round(t.rev_target || 0).toLocaleString('en-US'))) +
          '<span class="tg-sub">' + esc(T('متوسط 3 شهور: ', '3-month average: ')) + num(Math.round(t.rev_base || 0).toLocaleString('en-US')) + '</span></td>' +
          '<td>' + pct(t.bronze) + ' / ' + pct(t.silver) + ' / ' + pct(t.gold) + '</td>' +
          '<td>' + (ed ? '<input class="tg-in n" inputmode="numeric" data-f="floor" data-unit="' + esc(t.unit) + '" value="' + esc(Math.round(t.floor || 0)) + '">' : num(Math.round(t.floor || 0))) +
          '<span class="tg-sub">' + esc(T('المقترح: ', 'Suggested: ')) + num(Math.round(t.floor_suggested || 0)) + '</span></td>' +
          '<td>' + (ed ? '<input class="tg-in n" inputmode="numeric" data-f="ceiling" data-unit="' + esc(t.unit) + '" value="' + esc(Math.round(t.ceiling || 0)) + '">' : num(Math.round(t.ceiling || 0))) +
          '<span class="tg-sub">' + esc(T('المقترح: ', 'Suggested: ')) + num(Math.round(t.ceiling_suggested || 0)) + '</span></td>' +
          '<td>' + (ed ? '<button class="tg-btn sm" data-tg="unit" data-unit="' + esc(t.unit) + '">' + esc(T('احفظ', 'Save')) + '</button>' : '<span class="tg-st ok">' + esc(T('معتمد', 'Approved')) + '</span>') + '</td></tr>';
      });
      h += '</tbody></table></div>';
    }
    h += '</div>';

    /* 5 — month sheet */
    var s = d.sheet || {}, R = d.rules || {};
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('صرف شهر ', 'Payout for ')) + esc(s.month || '') +
      '<span class="tg-sub">' + esc(T('الموظف ياخذ ', 'The employee gets ')) + pct(R.share) + esc(T(' من حصة عوجا في الدخل اللي فوق هدف الشقة. المدير ', ' of Ouja’s fee on revenue above the unit’s target. The manager ')) + pct(R.manager) + esc(T(' فوقها + جائزة الفريق. والأول بسباق الشهر ياخذ ', ' on top + the team bonus. First place in the month’s race takes ')) + sar((s.prize || {}).amount) + esc(T('.', '.')) + '</span></div>' +
      '<div class="tg-kpis">' +
      '<div class="tg-kpi"><b>' + sar(s.revenue) + '</b><span>' + esc(T('دخل الشقق هالشهر', 'Units’ revenue this month')) + '</span></div>' +
      '<div class="tg-kpi"><b>' + sar(s.over) + '</b><span>' + esc(T('دخل فوق الأهداف', 'Revenue above targets')) + '</span></div>' +
      '<div class="tg-kpi"><b>' + pct(s.season) + '</b><span>' + esc(s.closed ? T('الموسم (100% = ما نزّل الأهداف)', 'Season (100% = targets not lowered)') : T('الموسم — ينحسب آخر الشهر', 'Season — judged at month end')) + '</span></div>' +
      '<div class="tg-kpi"><b>' + sar(s.total_paid) + '</b><span>' + esc(T('ينصرف (مع المدير)', 'To pay (with the manager)')) + '</span></div></div>';
    if (!s.approved_quarter) {
      h += '<div class="tg-banner">' + esc(T('أهداف هالربع ما اعتمدت — ما ينصرف شي لين تعتمدها.', 'This quarter’s targets are not approved — nothing is paid until they are.')) + '</div>';
    }
    h += '<div class="tg-wrap"><table class="tg-t"><thead><tr><th>' + esc(T('الموظف', 'Employee')) + '</th><th>' + esc(T('شقق فوق هدفها', 'Units above target')) + '</th><th>' +
      esc(T('دخل فوق الأهداف', 'Above targets')) + '</th><th>' + esc(T('العمولة', 'Commission')) + '</th><th>' + esc(T('مضاعف الالتزام', 'Ops multiplier')) +
      '</th><th>' + esc(T('الترتيب', 'Place')) + '</th><th>' + esc(T('الجائزة', 'Prize')) + '</th><th>' + esc(T('ينصرف', 'Paid')) + '</th></tr></thead><tbody>';
    if (!arr(s.employees).length) h += '<tr><td colspan="8">' + esc(T('ما فيه أهداف معتمدة لهالشهر.', 'No approved targets for this month.')) + '</td></tr>';
    arr(s.employees).forEach(function (e) {
      h += '<tr><td>' + esc(e.employee) + '</td><td>' + num(e.above + ' / ' + e.units) + '</td><td>' + sar(e.over) + '</td><td>' + sar(e.raw) +
        '</td><td>' + num('×' + e.multiplier) + '</td><td>' + (e.rank ? num(e.rank) + ' <span class="tg-sub">' + pct(e.pct) + '</span>' : '—') + '</td><td>' + (e.prize > 0 ? sar(e.prize) : '—') + '</td><td><b>' + sar(e.paid) + '</b></td></tr>';
    });
    if (s.manager) h += '<tr><td>' + esc(s.manager.name) + ' <span class="tg-sub">' + esc(T('مدير التشغيل', 'Operations manager')) + (s.manager.bonus > 0 ? ' · ' + esc(T('منها جائزة الفريق ', 'incl. team bonus ')) + sar(s.manager.bonus) : '') + '</span></td><td colspan="6"></td><td><b>' + sar(s.manager.amount) + '</b></td></tr>';
    h += '</tbody></table></div>';
    h += '<div class="tg-wrap" style="margin-top:12px"><table class="tg-t"><thead><tr><th>' + esc(T('الشقة', 'Unit')) + '</th><th>' + esc(T('الموظف', 'Employee')) + '</th><th>' +
      esc(T('الدخل', 'Revenue')) + '</th><th>' + esc(T('هدف الشهر', 'Month target')) + '</th><th>' + esc(T('فوق الهدف', 'Above')) + '</th><th>' + esc(T('التقييم', 'Rating')) +
      '</th><th>' + esc(T('العمولة', 'Commission')) + '</th></tr></thead><tbody>';
    arr(s.units).forEach(function (u) {
      var flag = u.rating_blocked ? ' <span class="tg-st bad">' + esc(T('موقوفة بالتقييم', 'Stopped by rating')) + '</span>'
        : (u.note && u.note.status === 'approved' ? ' <span class="tg-st ok">' + esc(T('ملاحظة مقبولة', 'Note accepted')) + '</span>' : '');
      h += '<tr><td><b>' + nm(u.name) + '</b>' + (u.blocked ? '<span class="tg-sub">' + num(u.blocked) + ' ' + esc(T('ليلة مقفلة', 'blocked nights')) + '</span>' : '') +
        (u.no_fee ? '<span class="tg-sub">' + esc(T('بدون نسبة عقد', 'No contract fee')) + '</span>' : '') + '</td><td>' + esc(u.employee || '—') + '</td><td>' + sar(u.revenue) +
        '</td><td>' + sar(u.target) + '</td><td>' + (u.over > 0 ? sar(u.over) : '—') + '</td><td>' + (u.rating == null ? '—' : num(Number(u.rating).toFixed(2))) + flag +
        '</td><td>' + (u.raw > 0 ? sar(u.raw) : '—') + '</td></tr>';
    });
    h += '</tbody></table></div>';
    if (arr(s.no_fee_units).length) {
      h += '<div class="tg-banner lock" style="margin-top:12px">' + esc(T('شقق فوق هدفها بس ما لها نسبة عقد مسجّلة — عمولتها صفر لين تنضاف بالمركز المالي: ', 'Units above target with no contract fee on record — they pay zero until it is added in Finance: ')) +
        esc(arr(s.no_fee_units).join('، ')) + '</div>';
    }
    var why = s.approval ? T('معتمد — الأرقام مثبّتة', 'Approved — figures frozen')
      : !s.approved_quarter ? T('اعتمد أهداف الربع أول', 'Approve the quarter targets first')
        : !s.closed ? T('الشهر ما خلص', 'The month has not ended')
          : s.notes_waiting ? T('باقي ملاحظات تقييم ما انبتّ فيها', 'Rating notes are still waiting') : '';
    h += '<div class="tg-row" style="margin-top:12px"><button class="tg-btn go" data-tg="approveM"' + (why ? ' disabled' : '') + '>' + esc(T('اعتمد صرف الشهر', 'Approve the month')) + '</button>' +
      (why ? '<span class="tg-sub">' + esc(why) + '</span>' : '') + '</div>';
    h += '<p class="tg-note">' + esc(T('الاعتماد يثبّت أرقام الشهر ويسجّل سطر. ما يكتب بالرواتب ولا بالمركز المالي.', 'Approval freezes the month and records one row. It writes nothing to payroll or the Finance Center.')) + '</p></div>';
    h += notesBox(d.notes);
    var ms2 = d.measure || {};
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('هل رسائل الواتساب تجيب حجوزات؟', 'Do the WhatsApp messages bring bookings?')) +
      '<span class="tg-sub">' + esc(T('للمعلومة بس — ما تأثر على العمولة. نقارن اللي انرسل لهم بمجموعة ما انرسل لها شي.', 'For information only — it does not change pay. Those messaged are compared with a group that got nothing.')) + '</span></div>' +
      '<div class="tg-kpis">' +
      '<div class="tg-kpi"><b>' + num(ms2.contacted || 0) + '</b><span>' + esc(T('انرسل لهم', 'Messaged')) + ' · ' + esc(T('حجز منهم ', 'booked ')) + num(ms2.contacted_bookings || 0) + '</span></div>' +
      '<div class="tg-kpi"><b>' + num(ms2.holdout || 0) + '</b><span>' + esc(T('ما انرسل لهم (عدد بس)', 'Not messaged (count only)')) + ' · ' + esc(T('حجز منهم ', 'booked ')) + num(ms2.holdout_bookings || 0) + '</span></div>' +
      '</div></div>';

    /* 6 — rescue */
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('قائمة الإنقاذ', 'Rescue list')) + '</div>' + rescueTable(d.rescue) + '</div>';
    return h;
  }

  /* The sync takes minutes on the server (Hostaway is throttled), so it runs in the
     background there. Here we only say so, and check back quietly until it is done —
     without redrawing the page under the owner's hands. */
  function syncNote(sy) {
    if (sy.running) return T('المزامنة شغّالة بالخلفية — تاخذ كم دقيقة. تقدر تكمل شغلك، وما يحتاج تضغط مرة ثانية.', 'The sync is running in the background — it takes a few minutes. Carry on; no need to press again.');
    if (sy.error) return T('آخر مزامنة ما كملت: ', 'The last sync did not finish: ') + sy.error;
    return '';
  }
  var syncTimer = null;
  function watchSync() {
    clearTimeout(syncTimer);
    if (!(S.admin && S.admin.seed && S.admin.seed.sync && S.admin.seed.sync.running)) return;
    syncTimer = setTimeout(function () {
      api('/api/targets/admin?month=' + encodeURIComponent(S.month)).then(function (a) {
        if (!a || !a.ok || !S.admin) return;
        S.admin.seed.sync = a.seed.sync;
        if (a.seed.sync.running) { watchSync(); return; }
        toast(a.seed.sync.error ? T('المزامنة ما كملت', 'The sync did not finish') : T('خلصت المزامنة', 'Sync finished'));
        if (S.pane === 'admin') loadTargets(true);
      }).catch(function () { watchSync(); });
    }, 20000);
  }

  /* ---------------------------------------------------------------- render + load «أهدافي» */

  function renderTargets() {
    css();
    var d = S.me || {}, h = '', panes = [['me', T('يومي', 'My day')]];
    if (d.is_admin || d.is_manager) panes.push(['team', T('الفريق', 'Team')]);
    if (d.is_admin) panes.push(['admin', T('الإدارة', 'Admin')]);
    h += '<div class="tg-bar">';
    if (panes.length > 1) {
      h += '<div class="tg-seg">';
      panes.forEach(function (p) { h += '<button data-tg="pane" data-pane="' + p[0] + '"' + (S.pane === p[0] ? ' class="on"' : '') + '>' + esc(p[1]) + '</button>'; });
      h += '</div>';
    } else { h += '<span></span>'; }
    h += monthBar() + '</div>';
    if (S.pane === 'admin' && S.admin) h += adminView(S.admin);
    else if (S.pane === 'team' && S.team) h += teamView(S.team);
    else h += meView(d);
    putHtml('tgBody', h);
    watchSync();
  }

  function loadTargets(force) {
    css();
    if (S.busy && !force) return;
    S.busy = true;
    var q = S.month ? '?month=' + encodeURIComponent(S.month) : '';
    api('/api/targets/me' + q).then(function (d) {
      if (!d || !d.ok) throw new Error((d && d.error) || 'failed');
      S.me = d;
      S.month = d.month || S.month || new Date().toISOString().slice(0, 7);
      /* The owner is not an employee: their first view is «الإدارة», not an empty «صفحتي». */
      if (!S.opened) { S.opened = true; if (!d.linked) S.pane = d.is_admin ? 'admin' : (d.is_manager ? 'team' : 'me'); }
      if (S.pane === 'admin' && !d.is_admin) S.pane = 'me';
      if (S.pane === 'team' && !(d.is_admin || d.is_manager)) S.pane = 'me';
      if (S.pane === 'admin') {
        return api('/api/targets/admin?month=' + encodeURIComponent(S.month) + (S.quarter ? '&quarter=' + encodeURIComponent(S.quarter) : ''))
          .then(function (a) { if (a && a.ok) { S.admin = a; S.quarter = a.quarter; } else { S.admin = null; S.pane = 'me'; } });
      }
      if (S.pane === 'team') {
        return api('/api/targets/team?month=' + encodeURIComponent(S.month))
          .then(function (t) { if (t && t.ok) { S.team = t; } else { S.team = null; S.pane = 'me'; } });
      }
    }).then(function () { S.busy = false; renderTargets(); })
      .catch(function () { S.busy = false; putHtml('tgBody', errorState('loadTargets(1)')); });
  }

  function shiftQuarter(q, by) {
    var y = Number(q.slice(0, 4)), n = Number(q.slice(6)) - 1 + by;
    y += Math.floor(n / 4); n = ((n % 4) + 4) % 4;
    return y + '-Q' + (n + 1);
  }

  function act(path, body, okMsg) {
    return post(path, body).then(function (r) {
      if (r && r.ok) { toast(okMsg || T('تم', 'Done')); loadTargets(true); }
      else { toast((r && (r.error || r.message)) || T('ما تم', 'Not done')); }
      return r;
    });
  }

  function onTargetsClick(ev) {
    var el = ev.target.closest('[data-tg]');
    if (!el) return;
    var a = el.getAttribute('data-tg');
    if (a === 'pane') { S.pane = el.getAttribute('data-pane'); loadTargets(true); }
    else if (a === 'month') { S.month = shiftMonth(S.month, Number(el.getAttribute('data-by'))); loadTargets(true); }
    else if (a === 'quarter') { S.quarter = shiftQuarter(S.quarter, Number(el.getAttribute('data-by'))); loadTargets(true); }
    else if (a === 'propose') { act('/api/targets/admin/propose', { quarter: S.quarter }, T('انحسبت الأهداف', 'Targets computed')); }
    else if (a === 'approveQ') {
      if (confirm(T('تعتمد أهداف وحدود هالربع؟ بعدها ما تتغير لين الربع الجاي.', 'Approve this quarter’s targets and bounds? They cannot change until next quarter.'))) {
        act('/api/targets/admin/approve-quarter', { quarter: S.quarter }, T('انعتمدت', 'Approved'));
      }
    }
    else if (a === 'unit') {
      var u = el.getAttribute('data-unit'), root = document.getElementById('tgBody'), v = { floor: 0, ceiling: 0, rev_target: 0 };
      Array.prototype.forEach.call(root.querySelectorAll('input[data-unit]'), function (i) {
        if (i.getAttribute('data-unit') !== u) return;
        v[i.getAttribute('data-f')] = Number(i.value) || 0;
      });
      act('/api/targets/admin/unit', { quarter: S.quarter, unit: u, floor: v.floor, ceiling: v.ceiling, rev_target: v.rev_target });
    }
    else if (a === 'note') {
      var nu = el.getAttribute('data-unit'), why = '';
      Array.prototype.forEach.call(document.getElementById('tgBody').querySelectorAll('input[data-note-unit]'), function (i) {
        if (i.getAttribute('data-note-unit') === nu) why = i.value;
      });
      act('/api/targets/note', { unit: nu, month: S.month, reason: why }, T('وصلت الملاحظة للمشرف', 'Note sent to the supervisor'));
    }
    else if (a === 'noteYes' || a === 'noteNo') {
      if (confirm(a === 'noteYes' ? T('تقبل الملاحظة؟ عمولة الشقة ترجع لهالشهر. القرار ما يتغير.', 'Accept the note? The unit’s commission returns for this month. The decision is final.')
        : T('ترفض الملاحظة؟ القرار ما يتغير.', 'Refuse the note? The decision is final.'))) {
        act('/api/targets/note-decide', { id: Number(el.getAttribute('data-id')), accept: a === 'noteYes' });
      }
    }
    else if (a === 'map') {
      var nm = el.getAttribute('data-name'), pick = '';
      Array.prototype.forEach.call(document.getElementById('tgBody').querySelectorAll('select[data-name]'), function (sl) {
        if (sl.getAttribute('data-name') === nm) pick = sl.value;
      });
      act('/api/targets/admin/map-name', { name: nm, listing_id: pick });
    }
    else if (a === 'sync') {
      el.disabled = true;
      post('/api/targets/admin/sync', {}).then(function (r) {
        if (!r || !r.ok) { el.disabled = false; toast((r && r.error) || T('ما بدت المزامنة', 'The sync did not start')); return; }
        toast(r.started ? T('بدت المزامنة — تاخذ كم دقيقة', 'Sync started — it takes a few minutes') : T('المزامنة شغّالة من قبل', 'A sync is already running'));
        if (S.admin && S.admin.seed) S.admin.seed.sync = r.sync;
        el.textContent = T('المزامنة شغّالة…', 'Sync running…');
        putHtml('tgSyncNote', esc(syncNote(r.sync || {})));
        watchSync();
      });
    }
    else if (a === 'seed') { uploadSeed(el); }
    else if (a === 'approveM') {
      if (confirm(T('تعتمد صرف هالشهر؟ الأرقام تتثبّت وما تتغير بعدها.', 'Approve this month? The figures are frozen afterwards.'))) {
        act('/api/targets/admin/approve-month', { month: S.month }, T('انعتمد', 'Approved'));
      }
    }
  }

  function onTargetsChange(ev) {
    var el = ev.target.closest('[data-tg-change]');
    if (!el) return;
    var a = el.getAttribute('data-tg-change');
    if (a === 'link') act('/api/targets/admin/link', { user_id: el.getAttribute('data-user'), employee: el.value });
    else if (a === 'manager') act('/api/targets/admin/manager', { user_id: el.value });
  }

  function uploadSeed(btn) {
    var inp = document.getElementById('tgSeedFile');
    if (!inp || !inp.files || !inp.files[0]) { toast(T('اختر الملف أول', 'Pick the file first')); return; }
    var fd = new FormData();
    fd.append('file', inp.files[0]);
    btn.disabled = true;
    btn.textContent = T('جاري الرفع…', 'Uploading…');
    fetch('/api/targets/admin/seed-upload', { method: 'POST', headers: { 'X-Token': tok() }, body: fd })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        if (r && r.ok) {
          var rep = r.report || {};
          toast(T('انرفع: ', 'Imported: ') + (rep.rows || 0) + T(' حجز', ' bookings') + (arr(rep.unmapped).length ? ' · ' + arr(rep.unmapped).length + T(' اسم ما انربط', ' names unmatched') : ''));
        } else { toast((r && r.error) || T('ما انرفع', 'Upload failed')); }
        loadTargets(true);
      })
      .catch(function () { toast(T('ما انرفع', 'Upload failed')); loadTargets(true); });
  }

  /* ---------------------------------------------------------------- «دفتر العملاء» */

  var OUT = { booked: ['حجز', 'Booked'], interested: ['مهتم', 'Interested'], declined: ['رفض', 'Declined'], dnc: ['لا تتصل', 'Do not contact'] };

  function bookView(d) {
    var h = '';
    if (!d.linked) {
      return h + emptyState(T('حسابك مو مربوط بموظف', 'Your login is not linked to an employee'),
        T('كلّم المالك يربط حسابك من «مين هو مين».', 'Ask the owner to link your login.'), '📒');
    }
    var L = d.list || {}, action = '/api/book/wa' + (tok() ? '?token=' + encodeURIComponent(tok()) : '');
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('قائمة اليوم', 'Today’s list')) +
      '<span class="tg-sub">' + num(L.open_nights || 0) + ' ' + esc(T('ليلة فاضية في', 'empty nights in')) + ' ' + num(L.open_units || 0) + ' ' + esc(T('شقة خلال 14 يوم', 'units over 14 days')) + '</span></div>';
    if (!L.open_units) {
      h += '<p class="tg-note">' + esc(T('ما عندك ليالي فاضية خلال 14 يوم. ما فيه أحد تتصل عليه اليوم.', 'No empty nights in the next 14 days. Nobody to contact today.')) + '</p>';
    } else if (!arr(L.items).length) {
      h += '<p class="tg-note">' + esc(T('ما فيه ضيوف مناسبين اليوم. القائمة تكبر كل ما وافق ضيوف أكثر على التواصل.', 'No matching guests today. The list grows as more guests agree to be contacted.')) + '</p>';
    }
    arr(L.items).forEach(function (it) {
      h += '<div class="tg-call"><div><b>' + esc(it.name) + '</b><span class="tg-sub">' + esc(it.reason) + '</span>' +
        '<span class="tg-sub">' + nm(it.unit_name) + ' · ' + esc(T('فاضية يوم ', 'empty on ')) + num(day(it.night)) + ' · ' + esc(T('سكن ', 'stayed ')) + num(it.stays) + ' ' + esc(T('مرة', 'times')) + '</span>' + lastStay(it) + '</div>' +
        '<form method="POST" action="' + esc(action) + '" target="_blank" rel="noopener" data-tg-form="wa"><input type="hidden" name="g" value="' + esc(it.g) + '">' +
        '<button type="submit" class="tg-btn wa">' + esc(T('واتساب', 'WhatsApp')) + '</button></form></div>';
    });
    h += '<p class="tg-note">' + esc(T('ضغطة الزر هي التسجيل. اتصال واحد لكل ضيف كل 45 يوم، وأول من يضغط هو صاحبه.', 'Pressing the button is the log. One contact per guest every 45 days; the first to press owns it.')) + '</p></div>';

    function sentRow(c) {
      var btns = '';
      if (!c.outcome) {
        Object.keys(OUT).forEach(function (k) {
          btns += '<button class="tg-btn sm" data-tg="outcome" data-id="' + esc(c.id) + '" data-o="' + k + '">' + esc(T(OUT[k][0], OUT[k][1])) + '</button>';
        });
      } else { btns = '<span class="tg-st">' + esc(T(OUT[c.outcome][0], OUT[c.outcome][1])) + '</span>'; }
      return '<div class="tg-call"><div><b>' + esc(c.name) + '</b>' + (c.booked ? ' <span class="tg-st ok">' + esc(T('حجز', 'Booked')) + '</span>' : '') +
        '<span class="tg-sub">' + esc(T('راسلته يوم ', 'Messaged on ')) + num(day(c.at)) +
        (c.unit_name ? ' · ' + esc(T('عن ', 'about ')) + nm(c.unit_name) + (c.night ? ' ' + esc(T('ليلة ', 'night ')) + num(day(c.night)) : '') : '') +
        (c.open ? ' · ' + esc(T('باقي ', '')) + num(c.days_left) + ' ' + esc(T('يوم على النافذة', 'days left in the window')) : '') + '</span>' + lastStay(c) + '</div>' +
        '<div class="tg-row">' + btns + '</div></div>';
    }
    var sent = arr(d.open), opened = sent.filter(function (c) { return c.open !== false; }), older = sent.filter(function (c) { return c.open === false; });
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('اتصالاتي المفتوحة', 'My open contacts')) +
      '<span class="tg-sub">' + esc(T('كل حجز تجيبه يرفع دخل الشقة — واللي فوق هدفها لك منه عمولة.', 'Every booking you bring lifts the unit’s revenue — and you earn on what is above its target.')) + '</span></div>';
    if (!opened.length) h += '<p class="tg-note">' + esc(T('ما فيه اتصالات مفتوحة.', 'No open contacts.')) + '</p>';
    opened.forEach(function (c) { h += sentRow(c); });
    h += '</div>';
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('اللي راسلتهم قبل', 'People I messaged before')) +
      '<span class="tg-sub">' + esc(T('آخر 4 شهور. ترجع لهم وتشوف رقم حجزهم وآخر سكن.', 'The last 4 months. Come back to them and see their booking number and last stay.')) + '</span></div>';
    if (!older.length) h += '<p class="tg-note">' + esc(T('ما فيه رسائل أقدم من أسبوعين للحين.', 'Nothing older than two weeks yet.')) + '</p>';
    older.forEach(function (c) { h += sentRow(c); });
    return h + '</div>';
  }

  function loadBook(force) {
    css();
    api('/api/book/list').then(function (d) {
      if (!d || !d.ok) throw new Error('failed');
      S.book = d;
      putHtml('bkBody', bookView(d));
    }).catch(function () { putHtml('bkBody', errorState('loadBook(1)')); });
  }

  function onBookClick(ev) {
    var el = ev.target.closest('[data-tg="outcome"]');
    if (!el) return;
    var o = el.getAttribute('data-o');
    if (o === 'dnc' && !confirm(T('«لا تتصل» نهائي: هالضيف ما راح يطلع لأي أحد مرة ثانية. متأكد؟', '“Do not contact” is permanent: this guest will never appear to anyone again. Sure?'))) return;
    post('/api/book/outcome', { id: Number(el.getAttribute('data-id')), outcome: o }).then(function (r) {
      toast(r && r.ok ? T('تسجّلت', 'Saved') : ((r && r.error) || T('ما تسجّلت', 'Not saved')));
      loadBook(true);
    });
  }

  function onBookSubmit(ev) {
    if (!ev.target || ev.target.getAttribute('data-tg-form') !== 'wa') return;
    /* The form posts in a new tab (server logs the contact, then redirects to WhatsApp).
       Refresh this list a moment later so the guest moves to «اتصالاتي المفتوحة». */
    setTimeout(function () { loadBook(true); }, 1800);
  }

  function onDaySubmit(ev) {
    if (!ev.target || ev.target.getAttribute('data-tg-form') !== 'wa') return;
    /* The press is the log: a moment later the mission pip fills and the guest leaves the list. */
    setTimeout(function () { loadTargets(true); }, 1800);
  }

  function bind(id, type, fn) {
    var el = document.getElementById(id);
    if (el && !el['__tg_' + type]) { el.addEventListener(type, fn); el['__tg_' + type] = 1; }
  }

  window.TargetsTab = {
    targets: function (force) { bind('tgBody', 'click', onTargetsClick); bind('tgBody', 'change', onTargetsChange); bind('tgBody', 'submit', onDaySubmit); return loadTargets(force); },
    book: function (force) { bind('bkBody', 'click', onBookClick); bind('bkBody', 'submit', onBookSubmit); return loadBook(force); }
  };
  /* The dashboard's retry buttons call these by name. */
  if (typeof window.loadTargets !== 'function') window.loadTargets = function (f) { return window.TargetsTab.targets(f); };
  if (typeof window.loadBook !== 'function') window.loadBook = function (f) { return window.TargetsTab.book(f); };
})();
