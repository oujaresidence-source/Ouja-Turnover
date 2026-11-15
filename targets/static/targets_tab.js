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

  var S = { me: null, admin: null, team: null, book: null, month: '', quarter: '', pane: 'me', busy: false, opened: false };

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
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
      '.tg-st{display:inline-flex;align-items:center;padding:2px 9px;border-radius:6px;font-size:11.5px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
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
      '@media (prefers-reduced-motion:reduce){.tg-btn{transition:none}.tg-btn:active{transform:none}}'
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

  var TIER = { bronze: ['برونزي', 'Bronze'], silver: ['فضي', 'Silver'], gold: ['ذهبي', 'Gold'] };

  function unitRow(u) {
    if (u.excluded) {
      return '<tr><td><b>' + esc(u.name) + '</b></td><td colspan="4"><span class="tg-st">' +
        esc(T('خارج الحسبة — متاحة أقل من 15 ليلة', 'Left out — open fewer than 15 nights')) + '</span></td></tr>';
    }
    var marks = '';
    if (u.has_target) {
      ['bronze', 'silver', 'gold'].forEach(function (k) {
        marks += '<u style="inset-inline-start:' + Math.round(u[k] * 100) + '%"></u>';
      });
    }
    var tier = u.tier ? '<span class="tg-st ok">' + esc(T(TIER[u.tier][0], TIER[u.tier][1])) + '</span>'
      : (u.has_target ? '<span class="tg-st">' + esc(T('تحت البرونزي', 'Below bronze')) + '</span>' : '<span class="tg-st">—</span>');
    var why = [];
    if (u.below_floor) why.push(u.below_floor + ' ' + T('ليلة تحت الحد الأدنى للسعر — ما انحسبت', 'nights under the price floor — not counted'));
    if (u.half_nights) why.push(u.half_nights + ' ' + T('ليلة سعرها تحت متوسط الشقة — انحسبت نص', 'nights under the unit average — counted half'));
    return '<tr><td><b>' + esc(u.name) + '</b>' +
      (why.length ? '<span class="tg-sub">' + esc(why.join(' · ')) + '</span>' : '') + '</td>' +
      '<td>' + pct(u.occupancy) + '<div class="tg-meter"><i style="width:' + Math.min(100, Math.round(u.occupancy * 100)) + '%"></i>' + marks + '</div></td>' +
      '<td>' + tier + '</td>' +
      '<td>' + (u.has_target ? (u.to_bronze ? num(u.to_bronze) + ' ' + esc(T('ليلة للبرونزي', 'nights to bronze')) : esc(T('وصلت', 'Reached'))) : '—') + '</td>' +
      '<td>' + num(u.empty) + ' ' + esc(T('ليلة فاضية', 'empty nights')) + '</td></tr>';
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
    var b = d.board, m = d.money, h = '';
    h += '<div class="tg-kpis">' +
      '<div class="tg-kpi"><b>' + sar(m.amount) + '</b><span>' + esc(T('عمولتي هالشهر', 'My commission this month')) + + '</span></div>' +
      '<div class="tg-kpi"><b>' + pct(b.share) + '</b><span>' + esc(T('نسبتي الحين', 'My share now')) + '</span></div>' +
      '<div class="tg-kpi"><b>' + num(b.hit + ' / ' + b.scored) + '</b><span>' + esc(T('شقق ضربت البرونزي', 'Units at bronze')) + '</span></div>' +
      '<div class="tg-kpi"><b>' + num(b.units_to_full_share) + '</b><span>' + esc(T('شقة باقي عشان توصل 40%', 'units to reach 40%')) + '</span></div>' +
      '</div>';
    if (!b.approved) {
      h += '<div class="tg-banner">' + esc(T('أهداف هالربع ما اعتمدها المالك للحين — نسبتك 30% لين تنعتمد.',
        'This quarter’s targets are not approved yet — your share stays 30% until they are.')) + '</div>';
    }
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('حجوزات انحسبت لي', 'Bookings counted for me')) +
      '<span class="tg-sub">' + esc(T('من اتصالات هالشهر. العمولة تنحسب بعد خروج الضيف.', 'From this month’s contacts. Commission counts after checkout.')) + '</span></div>';
    if (!arr(m.bookings).length) {
      h += '<p class="tg-note">' + esc(T('ما فيه حجوزات من اتصالاتك هالشهر للحين.', 'No bookings from your contacts this month yet.')) + '</p>';
    } else {
      h += '<div class="tg-wrap"><table class="tg-t stack"><thead><tr><th>' + esc(T('الضيف', 'Guest')) + '</th><th>' + esc(T('الشقة', 'Unit')) +
        '</th><th>' + esc(T('الليالي', 'Nights')) + '</th><th>' + esc(T('الحالة', 'Status')) + '</th></tr></thead><tbody>';
      arr(m.bookings).forEach(function (x) {
        h += '<tr><td>' + esc(x.guest) + '</td><td>' + esc(x.unit_name) + '</td><td>' + num(x.nights) + '</td><td>' +
          (x.state === 'completed' ? '<span class="tg-st ok">' + esc(T('انحسب', 'Counted')) + '</span>'
            : '<span class="tg-st gold">' + esc(T('بانتظار خروج الضيف', 'Waiting for checkout')) + '</span>') + '</td></tr>';
      });
      h += '</tbody></table></div>';
    }
    h += '</div>';
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('شققي', 'My units')) + '</div><div class="tg-wrap"><table class="tg-t stack"><thead><tr><th>' +
      esc(T('الشقة', 'Unit')) + '</th><th>' + esc(T('الإشغال', 'Occupancy')) + '</th><th>' + esc(T('الشريحة', 'Tier')) + '</th><th>' +
      esc(T('باقي', 'To go')) + '</th><th>' + esc(T('فاضي', 'Empty')) + '</th></tr></thead><tbody>';
    if (!arr(b.units).length) h += '<tr><td colspan="5">' + esc(T('ما عندك شقق في تقويم الموظفين.', 'No units under your name in the team calendar.')) + '</td></tr>';
    arr(b.units).forEach(function (u) { h += unitRow(u); });
    h += '</tbody></table></div></div>';
    return h;
  }

  /* ---------------------------------------------------------------- الفريق (manager) */

  function rescueTable(rows) {
    if (!arr(rows).length) return '<p class="tg-note">' + esc(T('ما فيه شقق متأخرة عن البرونزي.', 'No units behind bronze.')) + '</p>';
    var h = '<div class="tg-wrap"><table class="tg-t"><thead><tr><th>' + esc(T('الشقة', 'Unit')) + '</th><th>' + esc(T('الموظف', 'Employee')) +
      '</th><th>' + esc(T('الإشغال', 'Occupancy')) + '</th><th>' + esc(T('البرونزي', 'Bronze')) + '</th><th>' + esc(T('باقي', 'To go')) +
      '</th><th>' + esc(T('ملاحظة', 'Note')) + '</th></tr></thead><tbody>';
    arr(rows).forEach(function (r) {
      h += '<tr><td><b>' + esc(r.name) + '</b></td><td>' + esc(r.employee || '—') + '</td><td>' + pct(r.occupancy) + '</td><td>' + pct(r.bronze) +
        '</td><td>' + num(r.to_bronze) + ' ' + esc(T('ليلة', 'nights')) + '</td><td>' +
        (r.price_stuck ? '<span class="tg-st bad">' + esc(T('واقفة بسبب السعر — ارفعها لمسؤول التسعير', 'Stuck on price — raise with pricing')) + '</span>' : '') + '</td></tr>';
    });
    return h + '</tbody></table></div>';
  }

  function teamView(d) {
    var h = '<div class="tg-box"><div class="tg-h">' + esc(T('قائمة الإنقاذ', 'Rescue list')) +
      '<span class="tg-sub">' + esc(T('الشقق المتأخرة عن البرونزي هالشهر. تنحفظ نسخة يوم 10 ويوم 20.', 'Units behind bronze this month. A copy is saved on day 10 and day 20.')) + '</span></div>';
    if (d.quarter_state !== 'approved') h += '<p class="tg-note">' + esc(T('أهداف الربع ما اعتمدت، فالقائمة فاضية.', 'Quarter targets are not approved, so the list is empty.')) + '</p>';
    h += rescueTable(d.rescue) + '</div>';
    arr(d.snapshots).forEach(function (s) {
      h += '<div class="tg-box"><div class="tg-h">' + esc(T('نسخة يوم ', 'Copy of day ')) + num(s.day) + '</div>' + rescueTable(s.units) + '</div>';
    });
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('نشاط الفريق', 'Team activity')) + '</div><div class="tg-wrap"><table class="tg-t"><thead><tr><th>' +
      esc(T('الموظف', 'Employee')) + '</th><th>' + esc(T('اتصالات', 'Contacts')) + '</th><th>' + esc(T('حجوزات', 'Bookings')) + '</th><th>' +
      esc(T('شقق على البرونزي', 'Units at bronze')) + '</th></tr></thead><tbody>';
    if (!arr(d.activity).length) h += '<tr><td colspan="4">' + esc(T('ما فيه اتصالات هالشهر.', 'No contacts this month.')) + '</td></tr>';
    arr(d.activity).forEach(function (r) {
      h += '<tr><td>' + esc(r.employee) + '</td><td>' + num(r.contacts) + '</td><td>' + num(r.bookings) + '</td><td>' + num(r.hit + ' / ' + r.scored) + '</td></tr>';
    });
    return h + '</tbody></table></div></div>';
  }

  /* ---------------------------------------------------------------- الإدارة (owner only) */

  function opt(v, label, sel) { return '<option value="' + esc(v) + '"' + (String(v) === String(sel) ? ' selected' : '') + '>' + esc(label) + '</option>'; }

  function adminView(d) {
    var f = d.flags || {}, h = '', sy = (d.seed && d.seed.sync) || {};
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
    var ms = '<select class="tg-in" data-tg-change="manager">' + opt('', T('— ما تحدد —', '— not set —'), d.manager);
    arr(d.employees).forEach(function (e) { ms += opt(e, e, d.manager); });
    h += '<div class="tg-call"><b>' + esc(T('مدير التشغيل', 'Operations manager')) + '</b>' + ms + '</select></div></div>';

    /* 4 — quarter targets */
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('أهداف الربع ', 'Quarter targets ')) + esc(d.quarter) +
      '<div class="tg-row"><button class="tg-btn sm" data-tg="quarter" data-by="-1">‹</button><button class="tg-btn sm" data-tg="quarter" data-by="1">›</button>' +
      '<button class="tg-btn sm" data-tg="propose">' + esc(T('احسب الأهداف', 'Compute targets')) + '</button>' +
      (d.quarter_state === 'proposed' ? '<button class="tg-btn sm go" data-tg="approveQ">' + esc(T('اعتمد أهداف الربع', 'Approve quarter')) + '</button>' : '') +
      '</div></div>';
    h += '<p class="tg-note">' + esc(d.quarter_state === 'approved' ? T('معتمدة. نقل الشقق والحدود يتغير أول الربع الجاي.', 'Approved. Units and bounds change at the next quarter.')
      : d.quarter_state === 'proposed' ? T('مقترحة — عدّل الحد الأدنى والأعلى ثم اعتمد.', 'Proposed — edit the floor and ceiling, then approve.')
        : T('ما انحسبت. اضغط «احسب الأهداف».', 'Not computed. Press “Compute targets”.')) + '</p>';
    if (arr(d.targets).length) {
      h += '<div class="tg-wrap"><table class="tg-t"><thead><tr><th>' + esc(T('الشقة', 'Unit')) + '</th><th>' + esc(T('الموظف', 'Employee')) + '</th><th>' +
        esc(T('الأساس', 'Baseline')) + '</th><th>' + esc(T('برونزي / فضي / ذهبي', 'Bronze / Silver / Gold')) + '</th><th>' + esc(T('الحد الأدنى', 'Floor')) +
        '</th><th>' + esc(T('الحد الأعلى', 'Ceiling')) + '</th><th></th></tr></thead><tbody>';
      arr(d.targets).forEach(function (t) {
        var ed = t.status === 'proposed';
        h += '<tr><td><b>' + esc(t.name) + '</b>' + (t.basis === 'peers' ? '<span class="tg-sub">' + esc(T('شقة جديدة — من متوسط شقق مثلها', 'New unit — from similar units')) + '</span>' : '') +
          '</td><td>' + esc(t.employee || '—') + '</td><td>' + pct(t.baseline) + '</td><td>' + pct(t.bronze) + ' / ' + pct(t.silver) + ' / ' + pct(t.gold) + '</td>' +
          '<td>' + (ed ? '<input class="tg-in n" inputmode="numeric" data-f="floor" data-unit="' + esc(t.unit) + '" value="' + esc(Math.round(t.floor || 0)) + '">' : num(Math.round(t.floor || 0))) + '</td>' +
          '<td>' + (ed ? '<input class="tg-in n" inputmode="numeric" data-f="ceiling" data-unit="' + esc(t.unit) + '" value="' + esc(Math.round(t.ceiling || 0)) + '">' : num(Math.round(t.ceiling || 0))) +
          '<span class="tg-sub">' + esc(T('المقترح: ', 'Suggested: ')) + num(Math.round(t.ceiling_suggested || 0)) + '</span></td>' +
          '<td>' + (ed ? '<button class="tg-btn sm" data-tg="unit" data-unit="' + esc(t.unit) + '">' + esc(T('احفظ', 'Save')) + '</button>' : '<span class="tg-st ok">' + esc(T('معتمد', 'Approved')) + '</span>') + '</td></tr>';
      });
      h += '</tbody></table></div>';
    }
    h += '</div>';

    /* 5 — month sheet */
    var s = d.sheet || {}, m = s.measure || {};
    h += '<div class="tg-box"><div class="tg-h">' + esc(T('صرف شهر ', 'Payout for ')) + esc(s.month || '') + + '</div>' +
      '<div class="tg-kpis">' +
      '<div class="tg-kpi"><b>' + num(m.contacted || 0) + '</b><span>' + esc(T('انتصل عليهم', 'Contacted')) + ' · ' + esc(T('حجز منهم ', 'booked ')) + num(m.contacted_bookings || 0) + '</span></div>' +
      '<div class="tg-kpi"><b>' + num(m.holdout || 0) + '</b><span>' + esc(T('المجموعة الضابطة (عدد بس)', 'Hidden group (count only)')) + ' · ' + esc(T('حجز منهم ', 'booked ')) + num(m.holdout_bookings || 0) + '</span></div>' +
      '<div class="tg-kpi"><b>' + num((Math.round((s.incremental || 0) * 10) / 10)) + '</b><span>' + esc(T('حجوزات زادت بسبب الاتصال', 'Bookings the calls added')) + '</span></div>' +
      '<div class="tg-kpi"><b>' + sar(s.pool) + '</b><span>' + esc(T('السقف (50% من الزيادة)', 'Cap (50% of the uplift)')) + '</span></div>' +
      '<div class="tg-kpi"><b>' + sar(s.raw_total) + '</b><span>' + esc(T('المطالبة قبل السقف', 'Claim before the cap')) + '</span></div>' +
      '<div class="tg-kpi"><b>' + sar(s.total_paid) + '</b><span>' + esc(T('ينصرف بعد السقف', 'Paid after the cap')) + '</span></div></div>';
    h += '<div class="tg-wrap"><table class="tg-t"><thead><tr><th>' + esc(T('نوع الضيف', 'Guest type')) + '</th><th>' + esc(T('انتصل عليهم', 'Contacted')) + '</th><th>' +
      esc(T('حجزوا', 'Booked')) + '</th><th>' + esc(T('الضابطة', 'Hidden')) + '</th><th>' + esc(T('حجزوا', 'Booked')) + '</th><th>' + esc(T('معدل الرجوع بدون اتصال', 'Return rate with no call')) + '</th></tr></thead><tbody>';
    var BN = { 1: ['سكن مرة', '1 past stay'], 2: ['سكن مرتين', '2 past stays'], 3: ['3 مرات وأكثر', '3+ past stays'] };
    var SRC = { holdout: ['من الضابطة', 'measured'], history: ['من التاريخ (الضابطة قليلة)', 'from history (thin group)'], none: ['ما فيه دليل — ما ينصرف', 'no evidence — pays nothing'] };
    arr(m.buckets).forEach(function (b) {
      h += '<tr><td>' + esc(T(BN[b.bucket][0], BN[b.bucket][1])) + '</td><td>' + num(b.contacted) + '</td><td>' + num(b.contacted_bookings) + '</td><td>' + num(b.holdout) +
        '</td><td>' + num(b.holdout_bookings) + '</td><td>' + num((Math.round(b.rate * 1000) / 10) + '%') + ' <span class="tg-sub">' + esc(T(SRC[b.rate_source][0], SRC[b.rate_source][1])) + '</span></td></tr>';
    });
    h += '</tbody></table></div>';
    h += '<div class="tg-wrap" style="margin-top:12px"><table class="tg-t"><thead><tr><th>' + esc(T('الموظف', 'Employee')) + '</th><th>' + esc(T('اتصالات', 'Contacts')) + '</th><th>' +
      esc(T('حجوزات', 'Bookings')) + '</th><th>' + esc(T('نسبته', 'Share')) + '</th><th>' + esc(T('قبل السقف', 'Raw')) + '</th><th>' + esc(T('مضاعف الالتزام', 'Ops multiplier')) +
      '</th><th>' + esc(T('ينصرف', 'Paid')) + '</th></tr></thead><tbody>';
    if (!arr(s.employees).length) h += '<tr><td colspan="7">' + esc(T('ما فيه اتصالات مسجّلة هالشهر.', 'No logged contacts this month.')) + '</td></tr>';
    arr(s.employees).forEach(function (e) {
      h += '<tr><td>' + esc(e.employee) + '</td><td>' + num(e.contacts) + '</td><td>' + num(e.completed) + (e.pending ? ' <span class="tg-sub">+' + num(e.pending) + ' ' + esc(T('بانتظار الخروج', 'pending')) + '</span>' : '') +
        '</td><td>' + pct(e.share) + '</td><td>' + sar(e.raw) + '</td><td>' + num('×' + e.multiplier) + '</td><td><b>' + sar(e.paid) + '</b></td></tr>';
    });
    if (s.manager) h += '<tr><td>' + esc(s.manager.name) + ' <span class="tg-sub">' + esc(T('مدير التشغيل', 'Operations manager')) + '</span></td><td colspan="5"></td><td><b>' + sar(s.manager.amount) + '</b></td></tr>';
    h += '</tbody></table></div>';
    if (arr(s.no_fee_units).length) {
      h += '<div class="tg-banner lock" style="margin-top:12px">' + esc(T('شقق ما لها نسبة عقد مسجّلة — عمولتها صفر لين تنضاف بالمركز المالي: ', 'Units with no contract fee on record — they pay zero until it is added in Finance: ')) +
        esc(arr(s.no_fee_units).join('، ')) + '</div>';
    }
    var why = s.approval ? T('معتمد', 'Approved')
      : !s.window_closed ? T('الشهر ما قفل (14 يوم بعد نهايته)', 'Month not closed (14 days after it ends)')
        : s.pending ? T('باقي حجوزات ما خرج ضيوفها', 'Some guests have not checked out') : '';
    h += '<div class="tg-row" style="margin-top:12px"><button class="tg-btn go" data-tg="approveM"' + (why ? ' disabled' : '') + '>' + esc(T('اعتمد صرف الشهر', 'Approve the month')) + '</button>' +
      (why ? '<span class="tg-sub">' + esc(why) + '</span>' : '') + '</div>';
    h += '<p class="tg-note">' + esc(T('الاعتماد يسجّل سطر بس. ما يكتب بالرواتب ولا بالمركز المالي.', 'Approval records one row. It writes nothing to payroll or the Finance Center.')) + '</p></div>';

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
    var d = S.me || {}, h = '', panes = [['me', T('صفحتي', 'My page')]];
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
      if (!S.opened) { S.opened = true; if (d.is_admin && !d.linked) S.pane = 'admin'; }
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
      var u = el.getAttribute('data-unit'), root = document.getElementById('tgBody'), f = 0, c = 0;
      Array.prototype.forEach.call(root.querySelectorAll('input[data-unit]'), function (i) {
        if (i.getAttribute('data-unit') !== u) return;
        if (i.getAttribute('data-f') === 'floor') f = Number(i.value) || 0; else c = Number(i.value) || 0;
      });
      act('/api/targets/admin/unit', { quarter: S.quarter, unit: u, floor: f, ceiling: c });
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
      if (confirm(T('تعتمد صرف هالشهر؟ الاعتماد يسجّل سطر بس.', 'Approve this month? Approval records one row only.'))) {
        act('/api/targets/admin/approve-month', { month: S.month }, T('انعتمد', 'Approved'));
      }
    }
  }

  function onTargetsChange(ev) {
    var el = ev.target.closest('[data-tg-change]');
    if (!el) return;
    var a = el.getAttribute('data-tg-change');
    if (a === 'link') act('/api/targets/admin/link', { user_id: el.getAttribute('data-user'), employee: el.value });
    else if (a === 'manager') act('/api/targets/admin/manager', { name: el.value });
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
        '<span class="tg-sub">' + esc(it.unit_name) + ' · ' + esc(T('فاضية يوم ', 'empty on ')) + num(day(it.night)) + ' · ' + esc(T('سكن ', 'stayed ')) + num(it.stays) + ' ' + esc(T('مرة', 'times')) + '</span></div>' +
        '<form method="POST" action="' + esc(action) + '" target="_blank" rel="noopener" data-tg-form="wa"><input type="hidden" name="g" value="' + esc(it.g) + '">' +
        '<button type="submit" class="tg-btn wa">' + esc(T('واتساب', 'WhatsApp')) + '</button></form></div>';
    });
    h += '<p class="tg-note">' + esc(T('ضغطة الزر هي التسجيل. اتصال واحد لكل ضيف كل 45 يوم، وأول من يضغط هو صاحبه.', 'Pressing the button is the log. One contact per guest every 45 days; the first to press owns it.')) + '</p></div>';

    h += '<div class="tg-box"><div class="tg-h">' + esc(T('اتصالاتي المفتوحة', 'My open contacts')) +
      '<span class="tg-sub">' + esc(T('لو حجز الضيف خلال 14 يوم من اتصالك، ينحسب لك.', 'If the guest books within 14 days of your contact, it counts for you.')) + '</span></div>';
    if (!arr(d.open).length) h += '<p class="tg-note">' + esc(T('ما فيه اتصالات مفتوحة.', 'No open contacts.')) + '</p>';
    arr(d.open).forEach(function (c) {
      var btns = '';
      if (!c.outcome) {
        Object.keys(OUT).forEach(function (k) {
          btns += '<button class="tg-btn sm" data-tg="outcome" data-id="' + esc(c.id) + '" data-o="' + k + '">' + esc(T(OUT[k][0], OUT[k][1])) + '</button>';
        });
      } else { btns = '<span class="tg-st">' + esc(T(OUT[c.outcome][0], OUT[c.outcome][1])) + '</span>'; }
      h += '<div class="tg-call"><div><b>' + esc(c.name) + '</b>' + (c.booked ? ' <span class="tg-st ok">' + esc(T('حجز — انحسب لك', 'Booked — counted')) + '</span>' : '') +
        '<span class="tg-sub">' + esc(T('اتصلت يوم ', 'Contacted on ')) + num(day(c.at)) + ' · ' + esc(T('باقي ', '')) + num(c.days_left) + ' ' + esc(T('يوم على النافذة', 'days left in the window')) + '</span></div>' +
        '<div class="tg-row">' + btns + '</div></div>';
    });
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

  function bind(id, type, fn) {
    var el = document.getElementById(id);
    if (el && !el['__tg_' + type]) { el.addEventListener(type, fn); el['__tg_' + type] = 1; }
  }

  window.TargetsTab = {
    targets: function (force) { bind('tgBody', 'click', onTargetsClick); bind('tgBody', 'change', onTargetsChange); return loadTargets(force); },
    book: function (force) { bind('bkBody', 'click', onBookClick); bind('bkBody', 'submit', onBookSubmit); return loadBook(force); }
  };
  /* The dashboard's retry buttons call these by name. */
  if (typeof window.loadTargets !== 'function') window.loadTargets = function (f) { return window.TargetsTab.targets(f); };
  if (typeof window.loadBook !== 'function') window.loadBook = function (f) { return window.TargetsTab.book(f); };
})();
