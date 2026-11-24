/* «الحملات» — the owner's page for every WhatsApp campaign (owner, 2026-11-24:
 * «كيف اتابع كل الحملات؟ … ومتى تبدا ومين تستهدف وكم المتوقع العائد وكيف نحسب العايد»).
 *
 * Served by campaigns/routes.py at /campaigns/static/campaigns_tab.js and loaded on first visit
 * by the tiny loadCamp() stub inside DASHBOARD_HTML. A REAL file on purpose: DASHBOARD_HTML is a
 * Python string that eats backslashes (CLAUDE.md trap 1); this file is not.
 * Reads GET /api/campaigns/board; an admin types Hatif's own counts through
 * POST /api/campaigns/board/numbers. Uses the dashboard's globals only: api, post, esc,
 * labelText, toast, putHtml, errorState. Every action is event-delegated through data-cm="…".
 * Must pass `node --check`.
 */
(function () {
  'use strict';

  var S = { data: null, open: {}, edit: null, busy: false };
  var DAYS = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
  var MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  var ST = { scheduled: ['مجدولة', 'Scheduled', ''], measuring: ['انرسلت · نقيس', 'Sent · measuring', 'gold'],
             done: ['خلص القياس', 'Measured', 'ok'], cancelled: ['ملغاة', 'Cancelled', 'bad'] };
  var TAP = { show_units: 'وريني الشقق', elite_info: 'وش إيليت؟', owner_call: 'إيه، كلموني',
              owner_later: 'مو الحين', show_packages: 'وريني الباقات', opt_out: 'إيقاف العروض', other: 'ردود ثانية' };

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
  function n0(v) { var n = Number(v); return isFinite(n) ? n : 0; }
  function num(v, frac) {
    var n = Number(v);
    if (v === null || v === undefined || v === '' || !isFinite(n)) return '—';
    return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: frac === undefined ? 0 : frac });
  }
  function sar(v) { return v === null || v === undefined ? '—' : num(v) + ' ' + T('ر.س', 'SAR'); }
  function range(a, b) {
    var f = function (x) { return num(x, x < 10 ? 1 : 0); };
    return f(a) === f(b) ? f(a) : f(a) + '–' + f(b);
  }
  /* '2026-11-25T11:00' (Riyadh) → parts */
  function parts(local) {
    var m = String(local || '').match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    if (!m) return null;
    var d = new Date(+m[1], +m[2] - 1, +m[3]);
    return { day: DAYS[d.getDay()], date: +m[3], month: MONTHS[+m[2] - 1], key: m[1] + m[2] + m[3], h: +m[4], mi: m[5] };
  }
  /* UTC ISO → Riyadh 'الأربعاء 25 نوفمبر · 12:00 م' */
  function riyadhNow(iso) {
    var x = Date.parse(String(iso || '') + 'Z');
    if (!isFinite(x)) return '—';
    var d = new Date(x + 3 * 3600 * 1000), z = function (v) { return String(v).padStart(2, '0'); };
    var p = parts(d.getUTCFullYear() + '-' + z(d.getUTCMonth() + 1) + '-' + z(d.getUTCDate()) + 'T' + z(d.getUTCHours()) + ':' + z(d.getUTCMinutes()));
    return p ? dayLabel(p) + ' · ' + clock(p) : '—';
  }
  function clock(p) { return (p.h % 12 || 12) + ':' + p.mi + ' ' + (p.h < 12 ? 'ص' : 'م'); }
  function dayLabel(p) { return p.day + ' ' + p.date + ' ' + p.month; }
  function pill(k) { var m = ST[k] || [k, k, '']; return '<span class="cm-st ' + m[2] + '">' + esc(T(m[0], m[1])) + '</span>'; }
  function camp(id) { return arr(S.data && S.data.campaigns).filter(function (c) { return c.id === id; })[0] || null; }

  function css() {
    if (document.getElementById('cmCss')) return;
    var s = document.createElement('style');
    s.id = 'cmCss';
    s.textContent = [
      '.cm-wrap{max-width:860px}',
      '.cm-next{padding:12px 14px;border-radius:var(--r-md);background:var(--surface-2);font-size:13.5px;line-height:1.7;margin-bottom:16px}',
      '.cm-next b{font-weight:700}',
      '.cm-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;border-top:1.5px solid var(--text);border-bottom:1px solid var(--line);margin-bottom:8px}',
      '.cm-kpi{padding:14px 12px 14px 0}',
      '.cm-kpi+.cm-kpi{border-inline-start:1px solid var(--line);padding-inline-start:14px}',
      '.cm-kpi .l{font-size:12px;color:var(--mut);font-weight:600}',
      '.cm-kpi .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.3;margin-top:4px;white-space:nowrap}',
      '.cm-kpi .s{font-size:12px;color:var(--text-2);margin-top:2px;line-height:1.5}',
      '@media (max-width:640px){.cm-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.cm-kpi:nth-child(3){border-inline-start:0;padding-inline-start:0}.cm-kpi:nth-child(n+3){border-top:1px solid var(--line)}}',
      '.cm-owners{font-size:13px;color:var(--text-2);padding:8px 0 18px}',
      '.cm-day{margin-top:22px}',
      '.cm-day h3{font-size:13px;font-weight:700;color:var(--mut);margin:0 0 2px;display:flex;gap:8px;align-items:baseline}',
      '.cm-day h3 .c{font-weight:600;font-size:12px}',
      '.cm-row{border-bottom:1px solid var(--line);padding:14px 0}',
      '.cm-top{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:baseline;justify-content:space-between}',
      '.cm-top .t{font-size:15px;font-weight:700;line-height:1.5}',
      '.cm-top .tm{color:var(--gold-logo);font-weight:700;font-variant-numeric:tabular-nums;margin-inline-end:6px}',
      '.cm-who{font-size:12.5px;color:var(--text-2);margin-top:3px;line-height:1.6}',
      '.cm-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px 16px;margin-top:10px}',
      '.cm-grid .l{font-size:11.5px;color:var(--mut);font-weight:600}',
      '.cm-grid .v{font-size:14px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px}',
      '.cm-grid .s{font-size:11.5px;color:var(--text-2);line-height:1.5}',
      '.cm-grid .v.up{color:var(--green)}.cm-grid .v.down{color:var(--red)}',
      '@media (max-width:520px){.cm-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}',
      '.cm-taps{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}',
      '.cm-tap{font-size:12px;padding:3px 10px;border-radius:999px;background:var(--surface-2);color:var(--text-2);font-variant-numeric:tabular-nums}',
      '.cm-tap.bad{background:var(--red-soft);color:var(--red)}',
      '.cm-warn{font-size:12px;color:var(--yellow);margin-top:8px}',
      '.cm-st{display:inline-flex;align-items:center;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
      '.cm-st.bad{background:var(--red-soft);color:var(--red)}.cm-st.ok{background:var(--green-soft);color:var(--green)}.cm-st.gold{background:var(--yellow-soft);color:var(--yellow)}',
      '.cm-link{border:0;background:none;color:var(--text-2);font:inherit;font-size:12.5px;text-decoration:underline;cursor:pointer;padding:8px 0 0;min-height:32px}',
      '.cm-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-top:10px;padding:12px;border-radius:var(--r-sm);background:var(--surface-2)}',
      '.cm-form label{display:flex;flex-direction:column;gap:4px;font-size:11.5px;font-weight:700;color:var(--text)}',
      '.cm-form input{box-sizing:border-box;min-height:42px;padding:6px 10px;border:1px solid var(--line);border-radius:9px;background:var(--surface);color:var(--text);font:inherit;font-size:16px;width:100%}',
      '.cm-form .chk{flex-direction:row;align-items:center;gap:8px}',
      '.cm-form .chk input{width:20px;height:20px;min-height:0}',
      '.cm-form .act{grid-column:1/-1;display:flex;gap:8px}',
      '.cm-btn{min-height:44px;padding:0 20px;border:0;border-radius:999px;background:var(--text);color:var(--surface);font:inherit;font-size:14px;font-weight:700;cursor:pointer;transition:transform .12s cubic-bezier(.23,1,.32,1)}',
      '.cm-btn.ghost{background:transparent;color:var(--text);border:1px solid var(--line-strong)}',
      '.cm-btn:active{transform:scale(.97)}',
      '.cm-btn[disabled]{opacity:.5;cursor:wait}',
      '.cm-hold{margin-top:22px;padding:14px;border-radius:var(--r-md);border:1px solid var(--line);font-size:13px;line-height:1.8}',
      '.cm-how{margin-top:26px;border-top:1.5px solid var(--text);padding-top:6px}',
      '.cm-how summary{cursor:pointer;font-weight:700;font-size:15px;padding:10px 0;min-height:44px;display:flex;align-items:center}',
      '.cm-how ol{margin:4px 0 0;padding-inline-start:20px;font-size:13.5px;line-height:1.9;color:var(--text)}',
      '.cm-how li{margin-bottom:8px}',
      '.cm-how .g{margin-top:10px;font-size:12.5px;color:var(--text-2);line-height:1.8}',
      '.cm-foot{font-size:11.5px;color:var(--mut);margin-top:18px;line-height:1.7}',
      '@media (prefers-reduced-motion:reduce){.cm-btn:active{transform:none}}'
    ].join('');
    document.head.appendChild(s);
  }

  /* ---------------------------------------------------------------- pieces */

  function kpis(D) {
    var t = D.totals || {};
    var sent = n0(t.campaigns_sent) > 0;
    var h = '<div class="cm-kpis">';
    h += '<div class="cm-kpi"><div class="l">' + esc(T('صرفنا على الرسائل', 'Spent on messages')) + '</div><div class="v">' + esc(sar(t.cost)) + '</div>' +
      '<div class="s">' + esc(T('من ', 'of ') + sar(t.cost_planned) + T(' لكل الحملات', ' for all campaigns')) + '</div></div>';
    h += '<div class="cm-kpi"><div class="l">' + esc(T('حجزوا بعد الرسالة', 'Booked after the message')) + '</div><div class="v">' + esc(sent ? num(t.bookings) : '—') + '</div>' +
      '<div class="s">' + esc(sent ? T('عادةً بدون رسالة: ', 'Usually, no message: ') + num(t.baseline, 1) : T('يبدأ القياس مع أول إرسال', 'Starts with the first send')) + '</div></div>';
    h += '<div class="cm-kpi"><div class="l">' + esc(T('قيمة حجوزاتهم', 'Their bookings')) + '</div><div class="v">' + esc(sent ? sar(t.revenue) : '—') + '</div>' +
      '<div class="s">' + esc(T('المتوقع: ', 'Expected: ') + num((t.expected_sar || [])[0]) + '–' + num((t.expected_sar || [])[2]) + ' ' + T('ر.س', 'SAR')) + '</div></div>';
    h += '<div class="cm-kpi"><div class="l">' + esc(T('كل ريال رجّع', 'Each riyal returned')) + '</div><div class="v">' + esc(t.roi === null || t.roi === undefined ? '—' : num(t.roi, 1) + ' ' + T('ر.س', 'SAR')) + '</div>' +
      '<div class="s">' + esc(T('قيمة الحجوزات ÷ تكلفة الرسائل', 'Bookings ÷ message cost')) + '</div></div>';
    h += '</div>';
    if (sent) {
      h += '<div class="cm-owners">' + esc(T('الملاك: ', 'Owners: ') + num(t.owner_replies) + T(' ردّوا · ', ' replied · ') +
        num(t.owner_signed) + T(' شقة وقّعت', ' units signed') + (n0(t.owner_monthly) ? ' (' + sar(t.owner_monthly) + T(' بالشهر لعوجا', ' a month to Ouja') + ')' : '') +
        T(' · إيقاف العروض: ', ' · Opt-outs: ') + num(t.opt_out)) + '</div>';
    }
    return h;
  }

  function nextLine(D) {
    var ids = arr(D.next);
    if (!ids.length) return '';
    var cs = ids.map(camp).filter(Boolean);
    var p = parts(cs[0].send_at);
    var people = cs.reduce(function (a, c) { return a + n0(c.people); }, 0);
    return '<div class="cm-next">' + esc(T('الإرسال الجاي: ', 'Next send: ')) + '<b>' + esc(p ? dayLabel(p) + ' · ' + clock(p) : '') + '</b> — ' +
      esc(cs.map(function (c) { return c.title; }).join('، ')) + ' · ' + esc(num(people) + T(' شخص', ' people')) + '</div>';
  }

  function expectedCell(c) {
    var e = c.expected || {}, cnt = e.count || [0, 0, 0], s = e.sar || [0, 0, 0];
    var tail = c.kind === 'owner' ? T(' بالشهر', ' a month') : '';
    return '<div><div class="l">' + esc(T('المتوقع', 'Expected')) + '</div><div class="v">' + esc(range(cnt[0], cnt[2]) + ' ' + (c.unit || '')) + '</div>' +
      '<div class="s">' + esc(T('≈ ', '≈ ') + num(s[0]) + '–' + num(s[2]) + ' ' + T('ر.س', 'SAR') + tail) + '</div></div>';
  }

  function actualCells(c) {
    var a = c.actual || {}, h = '';
    if (c.status === 'cancelled') {
      return '<div><div class="l">' + esc(T('صار', 'Result')) + '</div><div class="v">—</div><div class="s">' + esc(T('ما انرسلت', 'Not sent')) + '</div></div>';
    }
    if (c.status === 'scheduled') {
      if (c.kind === 'owner' || c.baseline_rate === null || c.baseline_rate === undefined) return '';
      return '<div><div class="l">' + esc(T('عادةً بدون رسالة', 'Usually, no message')) + '</div><div class="v">' +
        esc('≈ ' + num(n0(c.people) * n0(c.baseline_rate), 1) + ' ' + (c.unit || '')) + '</div>' +
        '<div class="s">' + esc(T('يحجزون حتى لو ما أرسلنا', 'Book even without it')) + '</div></div>';
    }
    if (c.kind === 'owner') {
      h += '<div><div class="l">' + esc(T('ردّوا', 'Replied')) + '</div><div class="v">' + esc(num(a.replies)) + '</div>' +
        '<div class="s">' + esc(T('ضغطوا زر من الرسالة', 'Pressed a button')) + '</div></div>';
      h += '<div><div class="l">' + esc(T('وقّعوا', 'Signed')) + '</div><div class="v">' + esc(num(a.signed) + ' ' + T('شقة', 'units')) + '</div>' +
        '<div class="s">' + esc(n0(a.sar) ? sar(a.sar) + T(' بالشهر', ' a month') : T('يدخله المدير', 'Entered by admin')) + '</div></div>';
      return h;
    }
    var lift = c.lift, cls = lift === null || lift === undefined ? '' : (lift > 0 ? ' up' : (lift < 0 ? ' down' : ''));
    h += '<div><div class="l">' + esc(T('حجزوا', 'Booked')) + '</div><div class="v">' + esc(num(a.bookings) + ' ' + (c.unit || '')) + '</div>' +
      '<div class="s">' + esc(sar(a.sar)) + '</div></div>';
    h += '<div><div class="l">' + esc(T('عادةً بدون رسالة', 'Usually, no message')) + '</div><div class="v' + cls + '">' +
      esc(c.baseline === null || c.baseline === undefined ? '—' : num(c.baseline, 1)) + '</div>' +
      '<div class="s">' + esc(lift === null || lift === undefined ? T('ما عندنا تاريخ لهالفئة', 'No history for this group')
        : (lift >= 0 ? T('زيادة الرسالة: +', 'Message added: +') + num(lift, 1) : T('أقل من العادة بـ ', 'Below usual by ') + num(-lift, 1))) + '</div></div>';
    return h;
  }

  function tapsLine(c) {
    if (c.status === 'scheduled' || c.status === 'cancelled') return '';
    var t = c.taps || {}, keys = Object.keys(t), n = c.numbers || {}, h = '';
    var hat = [];
    if (n.sent !== null && n.sent !== undefined) hat.push(T('انرسلت ', 'Sent ') + num(n.sent));
    if (n.delivered !== null && n.delivered !== undefined) hat.push(T('وصلت ', 'Delivered ') + num(n.delivered));
    if (n.read_n !== null && n.read_n !== undefined) hat.push(T('قروها ', 'Read ') + num(n.read_n));
    if (n.replied !== null && n.replied !== undefined) hat.push(T('ردّوا ', 'Replied ') + num(n.replied));
    h += '<div class="cm-taps">';
    hat.forEach(function (x) { h += '<span class="cm-tap">' + esc(x) + '</span>'; });
    keys.forEach(function (k) {
      h += '<span class="cm-tap' + (k === 'opt_out' ? ' bad' : '') + '">' + esc((TAP[k] || k) + ' ' + num(t[k])) + '</span>';
    });
    if (!hat.length && !keys.length) h += '<span class="cm-tap">' + esc(T('ما فيه ردود للحين', 'No replies yet')) + '</span>';
    h += '</div>';
    if (c.kind !== 'owner' && !n0(c.audience_loaded)) {
      h += '<div class="cm-warn">' + esc(T('قائمة اللي وصلتهم ما انربطت للحين، فالحجوزات ما تنحسب لهالحملة.', 'Recipient list not linked yet, so bookings are not counted.')) + '</div>';
    }
    return h;
  }

  function editForm(c) {
    var n = c.numbers || {};
    function f(k, label, v) {
      return '<label>' + esc(label) + '<input inputmode="numeric" data-cm="f" data-k="' + k + '" value="' + esc(v === null || v === undefined ? '' : String(v)) + '"></label>';
    }
    var h = '<div class="cm-form">';
    h += f('sent', T('انرسلت (من هاتف)', 'Sent (Hatif)'), n.sent);
    h += f('delivered', T('وصلت', 'Delivered'), n.delivered);
    h += f('read_n', T('قروها', 'Read'), n.read_n);
    h += f('replied', T('ردّوا', 'Replied'), n.replied);
    if (c.kind === 'owner') h += f('signed', T('شقق وقّعت', 'Units signed'), n.signed);
    h += '<label>' + esc(T('وقت الإرسال', 'Send time')) + '<input data-cm="f" data-k="send_at" placeholder="2026-11-25T11:00" value="' + esc(c.send_at || '') + '"></label>';
    h += '<label class="chk"><input type="checkbox" data-cm="f" data-k="cancelled"' + (c.status === 'cancelled' ? ' checked' : '') + '>' + esc(T('ألغيناها في هاتف', 'Cancelled in Hatif')) + '</label>';
    h += '<div class="act"><button class="cm-btn" data-cm="save" data-id="' + esc(c.id) + '">' + esc(T('احفظ', 'Save')) + '</button>' +
      '<button class="cm-btn ghost" data-cm="close">' + esc(T('إلغاء', 'Cancel')) + '</button></div>';
    return h + '</div>';
  }

  function row(c) {
    var p = parts(c.send_at);
    var h = '<div class="cm-row" id="cm-' + esc(c.id) + '">';
    h += '<div class="cm-top"><div class="t"><span class="tm">' + esc(p ? clock(p) : '') + '</span>' + esc(c.title || c.id) + '</div>' + pill(c.status) + '</div>';
    h += '<div class="cm-who">' + esc(c.who || '') + '</div>';
    h += '<div class="cm-grid"><div><div class="l">' + esc(T('كم شخص', 'People')) + '</div><div class="v">' + esc(num(c.people)) + '</div>' +
      '<div class="s">' + esc(T('التكلفة ', 'Cost ') + sar(c.cost_planned)) + '</div></div>' + expectedCell(c) + actualCells(c) + '</div>';
    h += tapsLine(c);
    if (S.data && S.data.can_edit) {
      h += S.edit === c.id ? editForm(c) : '<button class="cm-link" data-cm="edit" data-id="' + esc(c.id) + '">' + esc(T('أدخل أرقام هاتف / عدّل الوقت', 'Enter Hatif numbers / edit time')) + '</button>';
    }
    return h + '</div>';
  }

  function timeline(D) {
    var cs = arr(D.campaigns).slice().sort(function (a, b) { return String(a.send_utc).localeCompare(String(b.send_utc)); });
    var days = [], byDay = {};
    cs.forEach(function (c) {
      var p = parts(c.send_at), k = p ? p.key : '?';
      if (!byDay[k]) { byDay[k] = { p: p, list: [] }; days.push(k); }
      byDay[k].list.push(c);
    });
    return days.map(function (k) {
      var d = byDay[k], ppl = d.list.reduce(function (a, c) { return a + n0(c.people); }, 0);
      return '<div class="cm-day"><h3>' + esc(d.p ? dayLabel(d.p) : '') + '<span class="c">' + esc(num(ppl) + T(' شخص', ' people')) + '</span></h3>' +
        d.list.map(row).join('') + '</div>';
    }).join('');
  }

  function holdout(D) {
    var h = D.holdout;
    if (!h) return '';
    var b1 = arr(D.campaigns).filter(function (c) { return c.group === 'B1' && (c.status === 'measuring' || c.status === 'done'); });
    var ppl = 0, bk = 0;
    b1.forEach(function (c) { ppl += n0(c.people); bk += n0((c.actual || {}).bookings); });
    var rate = ppl ? Math.round(1000 * bk / ppl) / 10 : 0;
    return '<div class="cm-hold"><b>' + esc(T('مجموعة المقارنة — الليلة الثانية بنص', 'Comparison group — second night half')) + '</b><br>' +
      esc(T('تركنا ' + num(h.people) + ' شخص من نفس الفئة بدون رسالة: حجز منهم ' + num(h.booked) + '، يعني ' + num(h.rate, 1) + '٪. ' +
            'واللي وصلتهم الرسالة: حجز ' + num(bk) + ' من ' + num(ppl) + '، يعني ' + num(rate, 1) + '٪.',
            'We left ' + num(h.people) + ' people of the same group without a message: ' + num(h.booked) + ' booked, ' + num(h.rate, 1) + '%. ' +
            'Those who got it: ' + num(bk) + ' of ' + num(ppl) + ' booked, ' + num(rate, 1) + '%.')) +
      '<br><span style="color:var(--mut);font-size:12px">' + esc(T('العدد صغير، فاقرأه كإشارة مب حكم نهائي.', 'Small sample: read it as a signal, not a verdict.')) + '</span></div>';
  }

  function how(D) {
    var g = D.groups || {}, seen = {}, notes = [];
    arr(D.campaigns).forEach(function (c) {
      if (seen[c.group]) return; seen[c.group] = 1;
      notes.push('<b>' + esc((g[c.group] || {}).name || c.group) + ':</b> ' + esc(c.baseline_note || '') + (c.value_note ? ' · ' + esc(T('قيمة الوحدة ', 'Value ') + sar(c.value) + ' — ' + c.value_note) : ''));
    });
    return '<details class="cm-how"><summary>' + esc(T('كيف نحسب العائد؟', 'How is the return calculated?')) + '</summary><ol>' +
      '<li>' + esc(T('المتوقع قبل الإرسال = عدد الناس × نسبة اللي نتوقع يحجزون (أقل وأعلى) × متوسط قيمة حجز هالفئة. للملاك: الشقق اللي نتوقع توقّع × رسوم عوجا الشهرية.',
        'Expected = people × expected booking share (low–high) × the group\'s average booking. Owners: units expected to sign × Ouja\'s monthly fee.')) + '</li>' +
      '<li>' + esc(T('الحجز ينحسب للحملة إذا الشخص اللي وصلته الرسالة حجز خلال ١٤ يوم من الإرسال (الملاك والشهري ٣٠ يوم). نطابقه برقم جواله مع Hostaway، ونحسب الحجوزات المؤكدة بس، والمبلغ من Hostaway نفسه.',
        'A booking counts when someone who got the message books within 14 days (owners and monthly: 30), matched by phone in Hostaway; confirmed bookings only, the amount from Hostaway.')) + '</li>' +
      '<li>' + esc(T('بعضهم كان بيحجز حتى بدون رسالة. «عادةً بدون رسالة» = كم شخص من نفس الفئة يحجز بنفس المدة بدون أي رسالة، محسوبة من حجوزات Hostaway مارس–أكتوبر. الفرق هو اللي جابته الرسالة فعلاً.',
        'Some would book anyway. «Usually» = how many of the same group book in the same window with no message, back-tested on Hostaway Mar–Oct. The difference is what the message added.')) + '</li>' +
      '<li>' + esc(T('التكلفة = عدد الرسائل × ٠٫٢٥ ر.س من رصيد هاتف. «كل ريال رجّع» = قيمة الحجوزات ÷ التكلفة.',
        'Cost = messages × 0.25 SAR of Hatif credit. «Each riyal returned» = bookings value ÷ cost.')) + '</li>' +
      '<li>' + esc(T('أرقام «وصلت / قروها» ما يعطيها هاتف للنظام، تنقل من صفحته يدوياً. الضغطات والحجوزات تجي لحالها.',
        'Hatif does not share «delivered / read» with our system: they are typed from its page. Taps and bookings arrive on their own.')) + '</li>' +
      '</ol><div class="g">' + notes.join('<br>') + '</div></details>';
  }

  function render() {
    var D = S.data;
    if (!D || !D.ok) { putHtml('cmBody', errorState('loadCamp(1)', D && D.error)); return; }
    var h = '<div class="cm-wrap">' + nextLine(D) + kpis(D) + timeline(D) + holdout(D) + how(D);
    var t = String(D.now_utc || '');
    h += '<div class="cm-foot">' + esc(T('الحجوزات من Hostaway، تتحدث كل ١٠ دقايق · الضغطات من هاتف لحظياً · ', 'Bookings from Hostaway, refreshed every 10 min · taps from Hatif live · ') +
      T('آخر تحديث ', 'Updated ') + riyadhNow(t)) + '</div>';
    putHtml('cmBody', h + '</div>');
  }

  /* ---------------------------------------------------------------- actions */

  async function save(id) {
    var c = camp(id);
    if (!c || S.busy) return;
    var box = document.getElementById('cm-' + id);
    var body = { campaign: id };
    arr(box ? box.querySelectorAll('[data-cm="f"]') : []).forEach(function (el) {
      var k = el.getAttribute('data-k');
      if (k === 'cancelled') { body.status = el.checked ? 'cancelled' : ''; return; }
      var v = String(el.value || '').trim();
      if (k === 'send_at') { body.send_at = v === c.send_at ? undefined : v; return; }
      if (v !== '' && !/^[0-9]+$/.test(v)) { el.focus(); throw new Error(T('أرقام بس', 'Numbers only')); }
      body[k] = v;
    });
    if (body.send_at === undefined) delete body.send_at;
    S.busy = true;
    try {
      var r = await post('/api/campaigns/board/numbers', body);
      if (!r || !r.ok) { toast((r && r.error) || T('ما انحفظ', 'Not saved')); return; }
      toast(T('انحفظ ✓', 'Saved ✓'));
      S.edit = null;
      await load(1);
    } finally { S.busy = false; }
  }

  function onClick(e) {
    var el = e.target.closest ? e.target.closest('[data-cm]') : null;
    if (!el) return;
    var a = el.getAttribute('data-cm');
    if (a === 'edit') { S.edit = el.getAttribute('data-id'); render(); }
    else if (a === 'close') { S.edit = null; render(); }
    else if (a === 'save') {
      save(el.getAttribute('data-id')).catch(function (err) { toast(String((err && err.message) || err)); S.busy = false; });
    }
  }

  async function load(force) {
    css();
    var body = document.getElementById('cmBody');
    if (body && !body.__cmBound) { body.addEventListener('click', onClick); body.__cmBound = 1; }
    if (!S.data || force) { if (!S.data) putHtml('cmBody', '<div class="empty sk">—</div>'); }
    try {
      S.data = await api('/api/campaigns/board');
    } catch (e) {
      S.data = { ok: false };
    }
    render();
  }

  window.CampTab = { load: load };
})();
