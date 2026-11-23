/* «المقاولات» — the contracting projects tab of the Ouja dashboard.
 *
 * Served by contracting/routes.py at /contracting/static/contracting_tab.js and loaded on first
 * visit by the tiny loadContr() stub inside DASHBOARD_HTML. A REAL file on purpose:
 * DASHBOARD_HTML is a Python string that eats backslashes (CLAUDE.md trap 1); this file is not.
 *
 * Owner rule (2026-11-23): one date per quote line, list order = work order, one Start button.
 * Uses the dashboard's globals only: api, post, esc, labelText, toast, putHtml, emptyState,
 * errorState, canWrite. Every action is event-delegated through data-ct="…".
 * Must pass `node --check`.
 */
(function () {
  'use strict';

  var S = { data: null, sel: null, newOpen: false, saving: {} };
  var DAYS = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
  var MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  var ST = { open: ['مفتوح', 'Open', ''], awaiting_photos: ['ينتظر الصور', 'Awaiting photos', 'gold'],
             blocked: ['واقف', 'Blocked', 'bad'], done: ['خلص', 'Done', 'ok'] };
  var PST = { draft: ['ما بدأ', 'Not started', ''], active: ['شغّال', 'Running', 'gold'], done: ['خلص', 'Done', 'ok'] };
  var HST = { ok: ['على الخطة', 'On track', 'ok'], late: ['متأخر', 'Late', 'bad'], blocked: ['فيه بند واقف', 'Blocked', 'bad'], done: ['خلص', 'Done', 'ok'] };
  var KIND = { heads_up: 'تنبيه قبل يومين', ask: '«خلص؟»', esc_lead: 'تصعيد لأصيل', esc_boss: 'تصعيد لفيصل',
               blocked_boss: 'واقف من يوم', summary: 'ملخص الصباح', open: 'فتح القناة' };
  var ROLE = { boss: 'صاحب القرار', lead: 'مشرف المشاريع', account: 'مدير الحساب', site: 'مشرف موقع' };

  function T(ar, en) { return labelText(ar, en); }
  function arr(x) { return Array.isArray(x) ? x : []; }
  function editable() { try { return canWrite('contr'); } catch (e) { return false; } }
  function d(s) { var p = String(s || '').slice(0, 10).split('-'); return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null; }
  function fmt(s) { var x = d(s); return x ? DAYS[x.getDay()] + ' ' + x.getDate() + ' ' + MONTHS[x.getMonth()] : T('بدون تاريخ', 'No date'); }
  function money(v) {
    var n = Number(v);
    if (v === null || v === '' || !isFinite(n)) return '—';
    var frac = Math.round(n * 100) % 100 !== 0;
    return n.toLocaleString('en-US', { minimumFractionDigits: frac ? 2 : 0, maximumFractionDigits: 2 });
  }
  /* the log shows Discord text: drop bold marks, turn raw mentions into a readable word */
  function plain(s) { return String(s || '').split('**').join('').replace(/<@[0-9]+>/g, '@منشن').replace(/<#[0-9]+>/g, '#القناة'); }
  function pill(map, k) { var m = map[k] || [k, k, '']; return '<span class="ct-st ' + m[2] + '">' + esc(T(m[0], m[1])) + '</span>'; }
  /* UTC ISO → Riyadh 'D/M H:MM' */
  function when(iso) {
    var t = Date.parse(String(iso || '') + 'Z'); if (!isFinite(t)) return '—';
    var x = new Date(t + 3 * 3600 * 1000);
    var h = x.getUTCHours(), m = String(x.getUTCMinutes()).padStart(2, '0');
    return x.getUTCDate() + '/' + (x.getUTCMonth() + 1) + ' ' + (h % 12 || 12) + ':' + m;
  }
  function proj(id) { return arr(S.data && S.data.projects).filter(function (p) { return p.id === id; })[0] || null; }
  function sites() { return arr(S.data && S.data.people).filter(function (p) { return p.role === 'site'; }); }
  function leadName() { var l = arr(S.data && S.data.people).filter(function (p) { return p.role === 'lead'; })[0]; return l ? l.name : 'أصيل'; }

  function css() {
    if (document.getElementById('ctCss')) return;
    var s = document.createElement('style');
    s.id = 'ctCss';
    s.textContent = [
      '.ct-banner{padding:11px 14px;border-radius:var(--r-md);background:var(--gold-tint);color:var(--text);font-size:12.5px;margin-bottom:14px;line-height:1.7}',
      '.ct-tabs{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}',
      '.ct-chip{display:inline-flex;align-items:center;gap:8px;min-height:40px;padding:0 14px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--text);font:inherit;font-size:13px;font-weight:600;cursor:pointer}',
      '.ct-chip.on{background:var(--text);color:var(--surface);border-color:var(--text)}',
      '.ct-chip.add{border-style:dashed;color:var(--text-2)}',
      '.ct-chip:active,.ct-go:active{transform:scale(.97)}',
      '.ct-card{max-width:720px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);padding:18px}',
      '.ct-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 12px;align-items:baseline;padding-bottom:12px;border-bottom:1.5px solid var(--text)}',
      '.ct-head b{font-size:17px}',
      '.ct-sub{font-size:12.5px;color:var(--mut)}',
      '.ct-num{font-variant-numeric:tabular-nums;white-space:nowrap}',
      '.ct-st{display:inline-flex;align-items:center;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}',
      '.ct-st.bad{background:var(--red-soft);color:var(--red)}.ct-st.ok{background:var(--green-soft);color:var(--green)}.ct-st.gold{background:var(--gold-tint);color:var(--gold)}',
      '.ct-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;padding:12px 0;border-bottom:1px solid var(--line)}',
      '.ct-fields label{display:flex;flex-direction:column;gap:5px;font-size:12px;font-weight:700;color:var(--text)}',
      '.ct-card input,.ct-card select,.ct-card textarea{min-height:42px;padding:8px 10px;border:1px solid var(--line);border-radius:9px;background:var(--surface);color:var(--text);font:inherit;font-size:16px}',
      '.ct-card textarea{min-height:150px;resize:vertical;line-height:1.7}',
      '.ct-card input.bad{border-color:var(--red);background:var(--red-soft)}',
      '.ct-checks{display:flex;flex-wrap:wrap;gap:16px;padding:12px 0;border-bottom:1px solid var(--line);font-size:13.5px}',
      '.ct-checks label{display:flex;align-items:center;gap:8px;cursor:pointer}',
      '.ct-checks input{min-height:0;width:20px;height:20px}',
      '.ct-list{list-style:none;margin:0;padding:0}',
      '.ct-row{display:grid;grid-template-columns:24px minmax(0,1fr) 170px;gap:4px 12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line)}',
      '.ct-row .n{font-weight:800;color:var(--gold);font-size:16px}',
      '.ct-row b{display:block;font-size:14px;line-height:1.45}',
      '.ct-row .ask{grid-column:2/-1;font-size:12.5px;color:var(--text-2)}',
      '.ct-row .ask.err{color:var(--red)}',
      '.ct-row.done b{color:var(--mut);text-decoration:line-through;text-decoration-color:var(--line)}',
      '@media (max-width:520px){.ct-row{grid-template-columns:24px minmax(0,1fr)}.ct-row .dt{grid-column:2}}',
      '.ct-stop{margin-top:14px;padding:10px 12px;border-radius:9px;background:var(--red-soft);color:var(--red);font-size:13px}',
      '.ct-go{margin-top:12px;width:100%;min-height:48px;border:0;border-radius:999px;background:var(--text);color:var(--surface);font:inherit;font-size:15px;font-weight:700;cursor:pointer;transition:transform .12s cubic-bezier(.23,1,.32,1)}',
      '.ct-go[disabled]{background:var(--surface-2);color:var(--mut);cursor:not-allowed;transform:none}',
      '.ct-link{border:0;background:none;color:var(--text-2);font:inherit;font-size:12.5px;text-decoration:underline;cursor:pointer;padding:6px 0}',
      '.ct-meta{display:flex;flex-wrap:wrap;gap:6px 14px;padding:10px 0;font-size:12.5px;color:var(--text-2);border-bottom:1px solid var(--line)}',
      '.ct-sec{margin-top:26px;max-width:720px}',
      '.ct-sec h3{font-size:14px;margin:0 0 8px}',
      '.ct-ppl{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}',
      '.ct-ppl li{display:grid;grid-template-columns:minmax(0,150px) minmax(0,1fr) auto;gap:8px 12px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line);font-size:13px}',
      '.ct-ppl input{min-height:38px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text);font:inherit;font-size:14px;width:100%}',
      '@media (max-width:520px){.ct-ppl li{grid-template-columns:1fr}}',
      '.ct-log{list-style:none;margin:0;padding:0;border-top:1px solid var(--line);font-size:12.5px}',
      '.ct-log li{padding:9px 0;border-bottom:1px solid var(--line);display:grid;grid-template-columns:86px minmax(0,1fr);gap:10px}',
      '.ct-log .tx{color:var(--text-2);white-space:pre-wrap;overflow-wrap:anywhere;max-height:4.8em;overflow:hidden}',
      '@media (prefers-reduced-motion:reduce){.ct-chip:active,.ct-go:active{transform:none}}'
    ].join('');
    document.head.appendChild(s);
  }

  /* ---------------------------------------------------------------- render */

  function render() {
    var D = S.data;
    if (!D || !D.ok) { putHtml('ctBody', errorState('loadContr(1)', D && D.error)); return; }
    var ps = arr(D.projects);
    if (!S.sel || !proj(S.sel)) S.sel = ps.length ? ps[0].id : null;
    var h = '';
    if (D.dryrun) {
      h += '<div class="ct-banner"><b>' + esc(T('وضع التجربة', 'Dry run')) + ':</b> ' +
        esc(T('النظام يكتب كل رسالة في السجل تحت، وما يرسل شي لديسكورد ولا يفتح قنوات. للتشغيل الفعلي: CONTRACTING_DRYRUN=0 في Railway.',
          'Every message goes to the log below; nothing is posted to Discord and no channel is opened. To go live: CONTRACTING_DRYRUN=0 in Railway.')) + '</div>';
    }
    h += '<div class="ct-tabs">' + ps.map(function (p) {
      return '<button class="ct-chip' + (p.id === S.sel && !S.newOpen ? ' on' : '') + '" data-ct="sel" data-id="' + esc(p.id) + '">' +
        esc(p.title) + ' ' + pill(PST, p.status) + '</button>';
    }).join('') + (editable() ? '<button class="ct-chip add" data-ct="newopen">+ ' + esc(T('مشروع جديد', 'New project')) + '</button>' : '') + '</div>';
    if (S.newOpen) h += newForm();
    else if (!S.sel) h += emptyState(T('ما فيه مشاريع', 'No projects yet'));
    else h += projectCard(proj(S.sel));
    h += peopleSec() + logSec();
    putHtml('ctBody', h);
  }

  function newForm() {
    return '<div class="ct-card"><div class="ct-head"><b>' + esc(T('مشروع جديد', 'New project')) + '</b>' +
      '<span class="ct-sub">' + esc(T('الصق بنود عرض السعر: كل بند بسطر، والمبلغ آخر السطر', 'Paste the quote lines: one per line, amount last')) + '</span></div>' +
      '<div class="ct-fields">' +
      '<label>' + esc(T('اسم المشروع', 'Project name')) + '<input id="ctNTitle"></label>' +
      '<label>' + esc(T('المالك', 'Owner')) + '<input id="ctNOwner"></label>' +
      '<label>' + esc(T('الوحدة', 'Unit')) + '<input id="ctNUnit"></label>' +
      '<label>' + esc(T('إجمالي العرض (ر.س)', 'Quote total (SAR)')) + '<input id="ctNTotal" inputmode="decimal"></label>' +
      '</div><div style="padding-top:12px"><textarea id="ctNLines" placeholder="رفع مساحي للتراس   350"></textarea></div>' +
      '<button class="ct-go" data-ct="create">' + esc(T('أضف المشروع', 'Add project')) + '</button>' +
      '<button class="ct-link" data-ct="newclose">' + esc(T('إلغاء', 'Cancel')) + '</button></div>';
  }

  function askLine(p, it, err) {
    if (err) return '<span class="ask err">' + esc(err) + '</span>';
    var who = it.is_handover ? leadName() : (p.supervisor || T('المشرف', 'the supervisor'));
    if (it.status === 'done') return '<span class="ask">' + esc(T('خلص', 'Done')) + (it.done_by ? ' — ' + esc(it.done_by) : '') + ' · ' + arr(it.photos).length + ' ' + esc(T('صور', 'photos')) + '</span>';
    if (it.status === 'awaiting_photos') return '<span class="ask">' + esc(T('ضغط «خلص» — ينتظر الصور', 'Pressed done — waiting for photos')) + ' (' + arr(it.photos).length + '/' + (S.data.photos_needed || 3) + ')</span>';
    if (it.status === 'blocked') return '<span class="ask err">' + esc(T('واقف: ', 'Blocked: ')) + esc(it.blocked_reason || '') + '</span>';
    var extra = it.delays ? ' · ' + esc(T('تأخر ', 'delayed ')) + it.delays + 'x' : '';
    return '<span class="ask">' + esc(T('يسأل ', 'Asks ')) + esc(who) + ' «خلص؟» ' + esc(fmt(it.due)) + extra + '</span>';
  }

  function projectCard(p) {
    var ed = editable(), draft = p.status === 'draft';
    var probs = p.problems || {};
    var h = '<div class="ct-card"><div class="ct-head"><div><b>' + esc(p.unit || T('وحدة؟', 'Unit?')) + '</b><div class="ct-sub">' +
      esc(p.owner || T('مالك؟', 'Owner?')) + ' · <span class="ct-num">' + esc(money(p.total_sar)) + '</span> ر.س</div></div>' +
      (draft ? pill(PST, 'draft') : pill(HST, p.health && p.health.state)) + '</div>';
    if (draft && ed) {
      h += '<div class="ct-fields">' +
        '<label>' + esc(T('المالك', 'Owner')) + '<input data-ct="f" data-k="owner" value="' + esc(p.owner || '') + '"' + (p.owner ? '' : ' class="bad"') + '></label>' +
        '<label>' + esc(T('الوحدة', 'Unit')) + '<input data-ct="f" data-k="unit" value="' + esc(p.unit || '') + '"' + (p.unit ? '' : ' class="bad"') + '></label>' +
        '<label>' + esc(T('مشرف الموقع (له التذكيرات)', 'Site supervisor (gets the reminders)')) + '<select data-ct="f" data-k="supervisor"><option value="">' + esc(T('اختر', 'Choose')) + '</option>' +
        sites().map(function (x) { return '<option' + (x.name === p.supervisor ? ' selected' : '') + '>' + esc(x.name) + '</option>'; }).join('') + '</select></label></div>' +
        '<div class="ct-checks"><label><input type="checkbox" data-ct="f" data-k="signed"' + (p.signed ? ' checked' : '') + '>' + esc(T('المالك وقّع العرض', 'Owner signed the quote')) + '</label>' +
        '<label><input type="checkbox" data-ct="f" data-k="paid"' + (p.paid ? ' checked' : '') + '>' + esc(T('الدفعة وصلت', 'Payment received')) + '</label></div>';
    } else {
      var ch = p.channel_id ? '#' + esc(p.channel_name) : (p.channel_error ? esc(T('ما انفتحت القناة: ', 'Channel failed: ')) + esc(p.channel_error) :
        (draft ? esc(T('القناة تنفتح لما يبدأ', 'Channel opens on start')) : (S.data.dryrun ? esc(T('وضع التجربة — ما فيه قناة', 'Dry run — no channel')) : esc(T('القناة تنفتح…', 'Opening channel…')))));
      h += '<div class="ct-meta"><span>' + esc(T('مشرف الموقع: ', 'Supervisor: ')) + '<b>' + esc(p.supervisor || '—') + '</b></span>' +
        (p.health ? '<span>' + p.health.done + ' ' + esc(T('من', 'of')) + ' ' + p.health.total + ' ' + esc(T('خلصت', 'done')) + '</span>' : '') +
        '<span>' + ch + '</span>' +
        (p.channel_error && ed ? '<button class="ct-link" data-ct="retry" data-id="' + esc(p.id) + '">' + esc(T('جرّب مرة ثانية', 'Retry')) + '</button>' : '') + '</div>';
    }
    h += '<ol class="ct-list">' + arr(p.items).map(function (it) {
      var err = probs[it.id] || '';
      var canDate = ed && it.status !== 'done';
      return '<li class="ct-row' + (it.status === 'done' ? ' done' : '') + '"><span class="n">' + it.pos + '</span>' +
        '<div><b>' + esc(it.name) + '</b>' + (it.amount_sar != null ? '<span class="ct-sub ct-num">' + esc(money(it.amount_sar)) + ' ر.س</span> ' : '') +
        (draft ? '' : pill(ST, it.status)) + '</div>' +
        '<div class="dt">' + (canDate ? '<input type="date" data-ct="due" data-id="' + esc(it.id) + '" value="' + esc(it.due || '') + '"' + (err ? ' class="bad"' : '') + ' aria-label="' + esc(it.name) + '">' :
          '<span class="ct-sub">' + esc(fmt(it.due)) + '</span>') + '</div>' +
        askLine(p, it, err) + '</li>';
    }).join('') + '</ol>';
    if (draft) {
      var why = arr(p.gate && p.gate.why);
      if (why.length) h += '<p class="ct-stop">' + esc(T('ما يبدأ لين: ', 'Can’t start until: ')) + esc(why.join('، ')) + '</p>';
      if (ed) {
        h += '<button class="ct-go" data-ct="start" data-id="' + esc(p.id) + '"' + (why.length ? ' disabled' : '') + '>' + esc(T('ابدأ المشروع', 'Start project')) + '</button>' +
          '<button class="ct-link" data-ct="del" data-id="' + esc(p.id) + '">' + esc(T('احذف المسودة', 'Delete draft')) + '</button>';
      }
    }
    if (p.source) h += '<p class="ct-sub" style="margin:10px 0 0">' + esc(T('المصدر: ', 'Source: ')) + esc(p.source) + '</p>';
    return h + '</div>';
  }

  function peopleSec() {
    var ed = editable();
    return '<div class="ct-sec"><h3>' + esc(T('الفريق في ديسكورد', 'Team on Discord')) + '</h3>' +
      '<p class="ct-sub" style="margin:0 0 8px">' + esc(T('اللي مربوط ينمنشن باسمه. اللي مو مربوط: الصق رقمه من ديسكورد (كليك يمين على الاسم ← Copy User ID).', 'Linked people get a real mention. Others: paste their Discord ID (right-click name → Copy User ID).')) + '</p>' +
      '<ul class="ct-ppl">' + arr(S.data.people).map(function (x) {
        var st = x.linked ? '<span class="ct-st ok">' + esc(x.linked_from === 'ops' ? T('مربوط (من الالتزام)', 'Linked (ops)') : T('مربوط', 'Linked')) + '</span>' : '<span class="ct-st bad">' + esc(T('مو مربوط', 'Not linked')) + '</span>';
        return '<li><div><b>' + esc(x.name) + '</b><div class="ct-sub">' + esc(ROLE[x.role] || x.role) + '</div></div>' +
          (ed ? '<input data-ct="did" data-name="' + esc(x.name) + '" value="' + esc(x.did || '') + '" placeholder="' + esc(T('رقم ديسكورد', 'Discord ID')) + '" inputmode="numeric">' : '<span></span>') + st + '</li>';
      }).join('') + '</ul></div>';
  }

  function logSec() {
    var log = arr(S.data.log);
    return '<div class="ct-sec"><h3>' + esc(S.data.dryrun ? T('سجل التجربة — وش كان بيرسل', 'Dry-run log — what it would have sent') : T('آخر الرسائل', 'Latest messages')) + '</h3>' +
      (log.length ? '<ul class="ct-log">' + log.map(function (r) {
        var st = r.dryrun ? '' : (r.delivered ? ' ✓' : (r.error ? ' ✗ ' + r.error : ' …'));
        return '<li><span class="ct-sub ct-num">' + esc(when(r.at)) + '</span><div><b>' + esc(KIND[r.kind] || r.kind) + '</b>' + esc(st) + '<div class="tx">' + esc(plain(r.text)) + '</div></div></li>';
      }).join('') + '</ul>' : '<p class="ct-sub">' + esc(T('ما فيه رسائل للحين. تبدأ لما يبدأ مشروع ويقرب موعد بند.', 'Nothing yet. Messages start once a project runs and a line comes due.')) + '</p>') + '</div>';
  }

  /* ---------------------------------------------------------------- actions */

  async function act(path, body) {
    try {
      var r = await post(path, body);
      if (!r || r.ok === false) { toast((r && r.error) || T('ما انحفظ', 'Not saved')); return null; }
      return r;
    } catch (e) { toast(T('ما انحفظ — جرب مرة ثانية', 'Not saved — try again')); return null; }
  }

  async function saveDraft(p, fields, dues) {
    var r = await act('/api/contr/save', { id: p.id, dues: dues || {}, title: fields.title, owner: fields.owner, unit: fields.unit,
      supervisor: fields.supervisor, signed: fields.signed, paid: fields.paid, total_sar: fields.total_sar });
    if (r) await load(true, true);
  }

  function draftFields(p) {
    return { title: p.title, owner: p.owner, unit: p.unit, supervisor: p.supervisor, signed: !!p.signed, paid: !!p.paid, total_sar: p.total_sar };
  }

  async function onChange(e) {
    var el = e.target, k = el.getAttribute('data-ct');
    if (!k) return;
    var p = proj(S.sel);
    if (k === 'f' && p) {
      var f = draftFields(p), key = el.getAttribute('data-k');
      f[key] = el.type === 'checkbox' ? el.checked : el.value;
      await saveDraft(p, f, {});
    } else if (k === 'due' && p) {
      var id = el.getAttribute('data-id'), dues = {};
      if (p.status === 'draft') { dues[id] = el.value; await saveDraft(p, draftFields(p), dues); }
      else if (await act('/api/contr/due', { item_id: id, due: el.value })) { toast(T('انحفظ الموعد الجديد', 'New date saved')); await load(true, true); }
      else await load(true, true);
    } else if (k === 'did') {
      if (await act('/api/contr/people', { name: el.getAttribute('data-name'), did: el.value })) { toast(T('انحفظ', 'Saved')); await load(true, true); }
    }
  }

  async function onClick(e) {
    var el = e.target.closest('[data-ct]');
    if (!el || el.tagName === 'INPUT' || el.tagName === 'SELECT') return;
    var k = el.getAttribute('data-ct'), id = el.getAttribute('data-id');
    if (k === 'sel') { S.sel = id; S.newOpen = false; render(); }
    else if (k === 'newopen') { S.newOpen = true; render(); var t = document.getElementById('ctNTitle'); if (t) t.focus(); }
    else if (k === 'newclose') { S.newOpen = false; render(); }
    else if (k === 'create') {
      var v = function (x) { var n = document.getElementById(x); return n ? n.value : ''; };
      el.disabled = true;
      var r = await act('/api/contr/new', { title: v('ctNTitle'), owner: v('ctNOwner'), unit: v('ctNUnit'), total_sar: v('ctNTotal'), lines: v('ctNLines') });
      el.disabled = false;
      if (r) { S.newOpen = false; S.sel = r.id; toast(T('انضاف — حط التواريخ', 'Added — now set the dates')); await load(true, true); }
    } else if (k === 'start') {
      el.disabled = true;
      var rs = await act('/api/contr/start', { id: id });
      if (rs) toast(rs.dryrun ? T('بدأ — وضع التجربة: الرسائل تنكتب بالسجل', 'Started — dry run: messages go to the log') : T('بدأ — قناة المشروع تنفتح في ديسكورد', 'Started — the Discord channel is opening'));
      await load(true, true);
    } else if (k === 'del') {
      if (el.getAttribute('data-sure') !== '1') { el.setAttribute('data-sure', '1'); el.textContent = T('متأكد؟ اضغط مرة ثانية', 'Sure? Press again'); return; }
      if (await act('/api/contr/delete', { id: id })) { S.sel = null; toast(T('انحذفت المسودة', 'Draft deleted')); await load(true, true); }
    } else if (k === 'retry') {
      if (await act('/api/contr/retry', { id: id })) { toast(T('جاري فتح القناة', 'Opening the channel')); await load(true, true); }
    }
  }

  function bind() {
    var b = document.getElementById('ctBody');
    if (!b || b.__ctBound) return;
    b.__ctBound = 1;
    b.addEventListener('click', onClick);
    b.addEventListener('change', onChange);
  }

  async function load(force, quiet) {
    css();
    bind();
    if (!S.data && !quiet) putHtml('ctBody', '<div class="empty sk">—</div>');
    try { S.data = await api('/api/contr/board'); }
    catch (e) { S.data = null; }
    render();
  }

  window.ContrTab = { load: load };
})();
