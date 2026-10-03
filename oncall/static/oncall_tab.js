/* «المناوبة» — the evening on-call tab of the Ouja dashboard.
 *
 * Served by oncall/routes.py at /oncall/static/oncall_tab.js and loaded on first visit by the
 * tiny loadOncall() stub inside DASHBOARD_HTML. A REAL file on purpose: DASHBOARD_HTML is a
 * Python string that eats backslashes (CLAUDE.md trap 1); this file is not.
 *
 * Sections: الحين · الليلة · بكرة · المشاكل · السجل · الإعدادات.
 * Uses the dashboard's globals only: api, post, esc, labelText, toast, putHtml, emptyState,
 * errorState. Every action is event-delegated through data-oc="…". Must pass `node --check`.
 */
(function () {
  'use strict';

  var S = { data: null, loading: false, editing: null };

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
  /* ISO timestamp -> 12-hour '6:15', the way the team and the Discord messages say it. */
  function hm(s) {
    if (!s) return '—';
    var h = Number(String(s).slice(11, 13)), m = String(s).slice(14, 16);
    return isFinite(h) && m ? (h % 12 || 12) + ':' + m : '—';
  }
  /* A time range inside Arabic text renders right-to-left ('7:00–5:00'); pin it LTR. */
  function span(a, b) { return '<span dir="ltr">' + esc(a) + '–' + esc(b) + '</span>'; }

  var STATUS = { none: ['ما نزل', 'Not published'], published: ['منشور — التبديل مفتوح', 'Published — swaps open'],
                 locked: ['مقفل', 'Locked'] };
  var CHECK = { missed: ['غياب', 'Missed'], late: ['غياب (ضغط متأخر)', 'Missed (late press)'],
                voided: ['ملغي', 'Void'] };
  var VOID = { not_delivered: ['ما وصله السؤال', 'Not delivered'], bot_down: ['البوت كان متوقف', 'Bot was down'],
               unreachable: ['الحساب مو مربوط', 'Not linked'], switched_off: ['النظام كان موقّف', 'System was off'],
               on_leave: ['إجازة مسجّلة', 'On recorded leave'], reassigned: ['تغيّر المناوب', 'Slot reassigned'] };

  function css() {
    if (document.getElementById('ocCss')) return;
    var s = document.createElement('style');
    s.id = 'ocCss';
    s.textContent = [
      '.oc-banner{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;justify-content:space-between;padding:11px 14px;border-radius:var(--r-md);border:1px solid var(--line);background:var(--surface);margin-bottom:14px;font-size:12.5px;color:var(--text-2)}',
      '.oc-banner.off{background:var(--red-soft);border-color:transparent;color:var(--red)}',
      '.oc-banner b{color:var(--text)}',
      '.oc-now{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}',
      '.oc-h{font-size:13px;font-weight:700;color:var(--text);margin:0 0 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}',
      '.oc-st{display:inline-flex;align-items:center;padding:2px 8px;border-radius:5px;font-size:11px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
      '.oc-st.bad{background:var(--red-soft);color:var(--red)}',
      '.oc-st.ok{background:var(--green-soft);color:var(--green)}',
      '.oc-st.gold{background:var(--gold-tint);color:var(--gold)}',
      '.oc-sub{display:block;font-size:11px;color:var(--mut);margin-top:2px}',
      '.oc-num{font-family:var(--font-mono);white-space:nowrap}',
      '.oc-edit{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px}',
      '.oc-edit select,.oc-edit input,.oc-set input{min-height:34px;padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:var(--surface);color:var(--text);font:inherit;font-size:12.5px}',
      '.oc-edit input{flex:1;min-width:140px}',
      '.oc-set{display:grid;gap:10px;max-width:520px}',
      '.oc-set label{font-size:12px;font-weight:700;color:var(--text)}',
      '.oc-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid var(--line);border-radius:999px;font-size:12px;margin:0 0 6px 6px}',
      '.oc-chip button{border:0;background:none;color:var(--mut);cursor:pointer;font:inherit;padding:0}',
      '.oc-wrap{overflow-x:auto}',
      '.btn:active{transform:scale(.97)}',
      '@media (prefers-reduced-motion:reduce){.btn:active{transform:none}}'
    ].join('');
    document.head.appendChild(s);
  }

  async function load(force) {
    css();
    if (S.loading) return;
    S.loading = true;
    if (force || !S.data) putHtml('ocBody', '<div class="empty sk">…</div>');
    try {
      var d = await api('/api/oncall/state');
      if (!d || d.ok === false) { putHtml('ocBody', errorState('loadOncall(1)', d && d.error)); return; }
      S.data = d;
      render();
    } catch (e) {
      putHtml('ocBody', errorState('loadOncall(1)'));
    } finally {
      S.loading = false;
    }
  }

  function banner(d) {
    var on = !!d.enabled;
    var btn = d.can_edit
      ? '<button class="btn ' + (on ? 'ghost' : 'primary') + ' sm" data-oc="switch" data-on="' + (on ? '0' : '1') + '">' +
        (on ? T('إيقاف النظام كامل', 'Stop everything') : T('تشغيل النظام', 'Turn on')) + '</button>'
      : '';
    var txt = on
      ? T('النظام شغّال — «موجود؟» كل ', 'Running — check every ') + '<b class="oc-num">' + d.settings.every_min +
        '</b>' + T(' دقيقة، و', ' min, ') + '<b class="oc-num">' + d.settings.window_min + '</b>' +
        T(' دقايق للرد. المشرفة: ', ' min to answer. Supervisor: ') + '<b>' + esc(d.settings.supervisor_name) + '</b>' +
        (d.settings.supervisor_linked ? '' : ' <span class="oc-st bad">' + T('حساب المشرفة مو مربوط', 'not linked') + '</span>')
      : '<b>' + T('النظام موقّف', 'Stopped') + '</b> — ' + T('ما فيه أسئلة ولا تنبيهات ولا إنذارات.', 'no checks, alerts or warnings.');
    return '<div class="oc-banner' + (on ? '' : ' off') + '"><span>' + txt + '</span>' + btn + '</div>';
  }

  function nowCards(d) {
    var n = d.now;
    if (!d.in_window) {
      return '<div class="oc-now"><div class="kpi"><div class="kpi-val">—</div><div class="kpi-lbl">' +
        T('خارج وقت المناوبة (٥ العصر – ١٢ الليل)', 'Outside on-call hours (5 PM – 12 AM)') + '</div></div></div>';
    }
    if (!n) {
      return '<div class="oc-now"><div class="kpi"><div class="kpi-val">⚠</div><div class="kpi-lbl">' +
        T('ما فيه مناوب الحين — الليلة ما لها جدول', 'Nobody on duty — no schedule tonight') + '</div></div></div>';
    }
    function k(v, l) { return '<div class="kpi"><div class="kpi-val">' + v + '</div><div class="kpi-lbl">' + l + '</div></div>'; }
    return '<div class="oc-now">' +
      k(esc(n.employee), T('المناوب الحين', 'On duty now') + ' · <span class="oc-num">' + span(n.from, n.to) + '</span>') +
      k('<span class="oc-num">' + hm(n.last_answered) + '</span>', T('آخر «موجود»', 'Last check-in')) +
      k('<span class="oc-num">' + esc(n.next_check || '—') + '</span>', T('السؤال الجاي', 'Next check')) +
      k('<span class="oc-num">' + arr(d.issues).filter(function (i) { return !i.resolved_at; }).length + '</span>',
        T('مشاكل مفتوحة', 'Open issues')) +
      '</div>';
  }

  function nightCard(title, nv, d) {
    var st = STATUS[nv.status] || STATUS.none;
    var h = '<div class="card"><div class="oc-h">' + title + ' · ' + esc(nv.label) +
      ' <span class="oc-st ' + (nv.status === 'locked' ? 'gold' : '') + '">' + T(st[0], st[1]) + '</span>' +
      (d.can_edit && nv.rebuildable ? ' <button class="btn ghost sm" data-oc="rebuild" data-date="' + esc(nv.date) + '">' +
        T('إعادة توزيع', 'Redistribute') + '</button>' : '') + '</div>';
    if (!nv.slots.length) {
      h += emptyState(nv.status === 'none' ? T('الجدول ينزل الساعة ١٢ الظهر قبلها بيوم', 'Published at 12 PM the day before')
                                           : T('ما فيه أحد متاح', 'Nobody available'));
    } else {
      h += '<div class="oc-wrap"><table class="data"><thead><tr><th>' + T('الوقت', 'Time') + '</th><th>' + T('المناوب', 'On duty') +
        '</th><th>' + T('ردود', 'Answered') + '</th><th>' + T('غياب', 'Missed') + '</th><th></th></tr></thead><tbody>';
      nv.slots.forEach(function (s) {
        var src = s.source === 'swap' ? T('تبديل', 'swap') : (s.source === 'edit' ? T('تعديل: ', 'edit: ') + esc(s.edited_by) : '');
        h += '<tr><td class="oc-num">' + span(s.from, s.to) + '</td><td>' + esc(s.employee) +
          (src ? '<span class="oc-sub">' + src + (s.edit_reason ? ' — ' + esc(s.edit_reason) : '') + '</span>' : '') +
          (s.linked ? '' : ' <span class="oc-st bad">' + T('مو مربوط', 'not linked') + '</span>') + '</td>' +
          '<td class="oc-num">' + s.answered + '</td><td class="oc-num">' +
          (s.missed ? '<span class="oc-st bad">' + s.missed + '</span>' : '0') + '</td><td>' +
          (d.can_edit ? '<button class="btn ghost sm" data-oc="edit" data-id="' + s.id + '">' + T('تغيير', 'Change') + '</button>' : '') +
          '</td></tr>';
        if (S.editing === s.id) {
          h += '<tr><td colspan="5"><div class="oc-edit"><select data-oc-f="emp">' +
            arr(d.settings.roster).map(function (r) {
              return '<option' + (r === s.employee ? ' selected' : '') + '>' + esc(r) + '</option>';
            }).join('') + '</select><input data-oc-f="reason" placeholder="' + T('السبب (إلزامي)', 'Reason (required)') + '">' +
            '<button class="btn primary sm" data-oc="save-slot" data-id="' + s.id + '">' + T('حفظ', 'Save') + '</button>' +
            '<button class="btn ghost sm" data-oc="cancel">' + T('إلغاء', 'Cancel') + '</button></div></td></tr>';
        }
      });
      h += '</tbody></table></div>';
    }
    if (nv.unavailable && nv.unavailable.length) {
      h += '<div class="oc-sub" style="margin-top:8px">' + T('مو موجودين: ', 'Not available: ') +
        nv.unavailable.map(function (u) { return esc(u.name) + ' (' + esc(u.why) + ')'; }).join('، ') + '</div>';
    }
    return h + '</div>';
  }

  function issuesCard(d) {
    var rows = arr(d.issues);
    var h = '<div class="card"><div class="oc-h">' + T('المشاكل وأصحابها', 'Issues and owners') + '</div>';
    if (!rows.length) return h + emptyState(T('ما فيه مشاكل للحين', 'No issues yet')) + '</div>';
    h += '<div class="oc-wrap"><table class="data"><thead><tr><th>' + T('المشكلة', 'Issue') + '</th><th>' + T('الصاحب', 'Owner') +
      '</th><th>' + T('فتحت', 'Opened') + '</th><th>' + T('الحالة', 'Status') + '</th></tr></thead><tbody>';
    rows.forEach(function (i) {
      /* a maintenance ticket has no «استلمت» step — it is open until the room is closed */
      var st = i.resolved_at ? '<span class="oc-st ok">' + T('انحلّت', 'Resolved') + '</span>'
        : (i.kind === 'maint' ? '<span class="oc-st gold">' + T('مفتوحة', 'Open') + '</span>'
        : (i.claimed_at ? '<span class="oc-st gold">' + T('مستلمة', 'Claimed') + '</span>'
                        : '<span class="oc-st bad">' + T('ما انستلمت', 'Unclaimed') + '</span>'));
      h += '<tr><td>' + (i.kind === 'maint' ? '🛠️ ' : '🚨 ') + esc(i.title || '—') + '</td><td>' + esc(i.owner) +
        (i.helper ? '<span class="oc-sub">' + T('ساعده: ', 'Helped by: ') + esc(i.helper) + '</span>' : '') +
        '</td><td class="oc-num"><span dir="ltr">' + esc(String(i.opened_at || '').slice(5, 10)) + ' ' + hm(i.opened_at) + '</span></td><td>' + st + '</td></tr>';
    });
    return h + '</tbody></table></div></div>';
  }

  function logCard(d) {
    var rows = arr(d.problems);
    var h = '<div class="card"><div class="oc-h">' + T('سجل الغياب والإلغاء', 'Misses and voids') + '</div>';
    if (!rows.length) return h + emptyState(T('ما فيه غياب مسجّل', 'No misses recorded')) + '</div>';
    h += '<div class="oc-wrap"><table class="data"><thead><tr><th>' + T('الموظف', 'Employee') + '</th><th>' + T('الوقت', 'When') +
      '</th><th>' + T('النتيجة', 'Result') + '</th></tr></thead><tbody>';
    rows.forEach(function (c) {
      var lbl = CHECK[c.status] || [c.status, c.status];
      var why = VOID[c.void_reason];
      h += '<tr><td>' + esc(c.employee) + '</td><td class="oc-num"><span dir="ltr">' + esc(c.date) + ' ' + hm(c.due_at) + '</span></td><td>' +
        '<span class="oc-st ' + (c.status === 'voided' ? '' : 'bad') + '">' + T(lbl[0], lbl[1]) + '</span>' +
        (why ? '<span class="oc-sub">' + T(why[0], why[1]) + '</span>' : '') + '</td></tr>';
    });
    h += '</tbody></table></div>';
    if (arr(d.warnings).length) {
      h += '<div class="oc-sub" style="margin-top:8px">' + T('الإنذارات الرسمية والاعتراضات في صفحة ', 'Formal warnings and appeals live on ') +
        '<a href="/compliance" target="_blank" rel="noopener">/compliance</a></div>';
    }
    return h + '</div>';
  }

  function settingsCard(d) {
    if (!d.can_edit) return '';
    var st = d.settings;
    return '<div class="card"><div class="oc-h">' + T('الإعدادات', 'Settings') + '</div><div class="oc-set">' +
      '<label>' + T('فريق المناوبة', 'On-call team') + '</label><div>' +
      arr(st.roster).map(function (r) {
        return '<span class="oc-chip">' + esc(r) + '<button data-oc="rm" data-n="' + esc(r) + '" aria-label="remove">✕</button></span>';
      }).join('') + '</div>' +
      '<div class="oc-edit"><input data-oc-f="add" placeholder="' + T('اسم كما في تقويم الموظفين', 'Name as in the employee calendar') + '">' +
      '<button class="btn ghost sm" data-oc="add">' + T('إضافة', 'Add') + '</button></div>' +
      '<label>' + T('ديسكورد المشرفة (رقم الحساب)', 'Supervisor Discord ID') + '</label>' +
      '<div class="oc-edit"><input data-oc-f="sup" inputmode="numeric" value="' + esc(st.supervisor_did || '') + '" placeholder="' +
      T('فاضي = نفس مسؤول الاعتراضات في /compliance', 'Empty = the /compliance appeal lead') + '">' +
      '<button class="btn ghost sm" data-oc="sup">' + T('حفظ', 'Save') + '</button></div>' +
      '<div class="oc-sub">' + T('روم ديسكورد: #', 'Discord room: #') + esc(st.channel) + '</div></div></div>';
  }

  function render() {
    var d = S.data;
    putHtml('ocBody', banner(d) + nowCards(d) + nightCard(T('الليلة', 'Tonight'), d.tonight, d) +
      nightCard(T('بكرة', 'Tomorrow'), d.tomorrow, d) + issuesCard(d) + logCard(d) + settingsCard(d));
  }

  function field(name) {
    var el = document.querySelector('#view_oncall [data-oc-f="' + name + '"]');
    return el ? el.value : '';
  }

  async function act(path, body, el) {
    if (el) el.setAttribute('aria-busy', 'true');
    try {
      var r = await post(path, body);
      if (!r || r.ok === false) { toast((r && r.error) || T('ما انحفظ', 'Not saved')); return false; }
      return true;
    } finally {
      if (el) el.removeAttribute('aria-busy');
    }
  }

  async function onClick(ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-oc]') : null;
    if (!el) return;
    var view = document.getElementById('view_oncall');
    if (!view || !view.contains(el)) return;
    var a = el.getAttribute('data-oc');
    var d = S.data;
    if (a === 'edit') { S.editing = Number(el.getAttribute('data-id')); render(); }
    else if (a === 'cancel') { S.editing = null; render(); }
    else if (a === 'save-slot') {
      var reason = field('reason').trim();
      if (!reason) { toast(T('اكتب السبب', 'Write a reason')); return; }
      if (await act('/api/oncall/slot', { slot_id: Number(el.getAttribute('data-id')), employee: field('emp'), reason: reason }, el)) {
        S.editing = null; toast(T('تم — وصلهم خبر بديسكورد', 'Saved — both were told on Discord')); load(true);
      }
    } else if (a === 'rebuild') {
      if (await act('/api/oncall/rebuild', { date: el.getAttribute('data-date') }, el)) {
        toast(T('انعاد التوزيع — الجدول في ديسكورد تحدّث', 'Redistributed — the Discord post was updated')); load(true);
      }
    } else if (a === 'switch') {
      if (await act('/api/oncall/switch', { on: el.getAttribute('data-on') === '1' }, el)) load(true);
    } else if (a === 'rm' || a === 'add') {
      var names = arr(d.settings.roster).slice();
      if (a === 'rm') names = names.filter(function (n) { return n !== el.getAttribute('data-n'); });
      else { var nn = field('add').trim(); if (!nn) return; if (names.indexOf(nn) < 0) names.push(nn); }
      if (await act('/api/oncall/settings', { roster: names }, el)) load(true);
    } else if (a === 'sup') {
      if (await act('/api/oncall/settings', { supervisor_did: field('sup').trim() }, el)) { toast(T('انحفظ', 'Saved')); load(true); }
    }
  }

  if (!window.__ocBound) {
    window.__ocBound = 1;
    document.addEventListener('click', onClick);
  }

  window.OncallTab = { load: load };
})();
