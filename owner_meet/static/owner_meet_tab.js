/* «اجتماع المالك» — the Owner Meeting tab of the Ouja dashboard.
 *
 * Served by owner_meet/routes.py at /meet/static/owner_meet_tab.js and loaded on first visit by the
 * tiny loadMeet() stub inside DASHBOARD_HTML. A REAL file on purpose: DASHBOARD_HTML is a Python
 * string that eats backslashes (CLAUDE.md trap 1); this file is not. Must pass `node --check`.
 *
 * Uses the dashboard's globals only: api, post, tok, esc, putHtml, errorState.
 * Every action is event-delegated through data-om="…" (no inline onclick string-building).
 * Nothing here sends anything to an owner: «تجهيز» builds a frozen snapshot, «افتح العرض» opens it.
 */
(function () {
  'use strict';

  var S = { owners: [], owner: '', lids: [], kind: '', first: '', last: '', meetings: [], active: null, timer: null,
            ab: null, abMsg: '', commits: [], sendMsg: '' };
  var CSTATUS = [['open', 'مفتوح'], ['in_progress', 'قيد التنفيذ'], ['done', 'تم'], ['not_done', 'لم يتم']];
  var KINDS = [
    ['since_last', 'منذ آخر اجتماع'], ['this_month', 'هذا الشهر حتى اليوم'], ['last_month', 'الشهر الماضي'],
    ['quarter', 'آخر ثلاثة أشهر كاملة'], ['ytd', 'من بداية السنة'], ['custom', 'أشهر أختارها']
  ];
  var STATE = { draft: 'مسودة', building: 'جاري التجهيز', ready: 'جاهز للعرض', error: 'تعذّر التجهيز',
                presented: 'عُرض', sent: 'أُرسل للمالك', reopened: 'أعيد فتحه' };

  function arr(x) { return Array.isArray(x) ? x : []; }
  var MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  /* «2026-10-06» -> «6 أكتوبر 2026». An ISO date inside Arabic text gets reordered by bidi. */
  function d(iso) {
    var m = /^([0-9]{4})-([0-9]{2})-([0-9]{2})/.exec(String(iso || ''));
    return m ? (parseInt(m[3], 10) + ' ' + MONTHS[parseInt(m[2], 10) - 1] + ' ' + m[1]) : String(iso || '');
  }
  function css() {
    if (document.getElementById('omCss')) return;
    var s = document.createElement('style');
    s.id = 'omCss';
    s.textContent = [
      /* Diriyah mud brown instead of the dashboard blue, inside this tab only (Faisal 2026-10-06) */
      '#view_meet{--accent:#8B5A3C;--accent-soft:#EBDCCB}',
      '#view_meet .btn.primary{background:#8B5A3C;border-color:#8B5A3C;color:#FFFFFF}',
      '#view_meet .btn.primary:hover{background:#74492F;border-color:#74492F}',
      '.om-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);gap:18px;align-items:start}',
      '@media (max-width:900px){.om-grid{grid-template-columns:1fr}}',
      '.om-panel{border:1px solid var(--line);border-radius:var(--r-md);background:var(--surface);padding:16px}',
      '.om-panel h3{font-size:14px;font-weight:700;margin:0 0 12px;color:var(--text)}',
      '.om-field{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}',
      '.om-field label,.om-field .lbl{font-size:12.5px;color:var(--text-2);font-weight:600}',
      '.om-field select,.om-field input[type=month]{font:inherit;font-size:14px;min-height:40px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--text)}',
      '.om-units{display:flex;flex-direction:column;gap:6px;max-height:220px;overflow:auto}',
      '.om-units label{display:flex;gap:8px;align-items:center;font-size:13.5px;color:var(--text);cursor:pointer;min-height:32px}',
      '.om-row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}',
      '.om-go{width:100%;min-height:44px;font-size:14.5px;transition:transform .12s cubic-bezier(0.23,1,0.32,1)}',
      '.om-go:active{transform:scale(.97)}',
      '.om-bar{height:6px;border-radius:3px;background:var(--surface-2);overflow:hidden;margin:10px 0 6px}',
      '.om-bar i{display:block;height:100%;width:100%;background:var(--accent);transform-origin:right;transition:transform .25s cubic-bezier(0.23,1,0.32,1)}',
      '.om-step{font-size:12.5px;color:var(--text-2)}',
      '.om-checks{list-style:none;padding:0;margin:12px 0 0}',
      '.om-checks li{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-top:1px solid var(--line);font-size:13.5px;color:var(--text)}',
      '.om-tag{flex-shrink:0;font-size:11px;font-weight:700;padding:2px 8px;border-radius:5px}',
      '.om-tag.red{background:var(--red-soft);color:var(--red)}',
      '.om-tag.yellow{background:var(--yellow-soft);color:var(--yellow)}',
      '.om-tag.ok{background:var(--green-soft);color:var(--green)}',
      '.om-acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}',
      '.om-list{width:100%;border-collapse:collapse;font-size:13px}',
      '.om-list th{text-align:start;font-weight:600;color:var(--text-2);padding:6px 4px;border-bottom:1px solid var(--line)}',
      '.om-list td{padding:9px 4px;border-bottom:1px solid var(--line);color:var(--text)}',
      '.om-list tr[data-om]{cursor:pointer}',
      '.om-list tr[data-om]:hover td{background:var(--surface-2)}',
      '.om-muted{color:var(--text-2);font-size:13px;line-height:1.7}',
      '.om-err{color:var(--red);font-size:13.5px;margin-top:8px}'
    ].join('');
    document.head.appendChild(s);
  }

  function opt(v, t, sel) { return '<option value="' + esc(v) + '"' + (sel ? ' selected' : '') + '>' + esc(t) + '</option>'; }
  function owner() { return arr(S.owners).filter(function (o) { return o.owner === S.owner; })[0] || null; }

  function formHtml() {
    var o = owner();
    var h = '<div class="om-field"><label for="omOwner">المالك</label><select id="omOwner" data-om="owner">' +
      opt('', 'اختر المالك', !S.owner) + arr(S.owners).map(function (x) { return opt(x.owner, x.owner, x.owner === S.owner); }).join('') +
      '</select></div>';
    if (!o) return h + '<p class="om-muted">اختر المالك لتظهر شققه وفتراته.</p>';
    h += '<div class="om-field"><span class="lbl">الشقق</span><div class="om-units">' +
      arr(o.units).map(function (u) {
        var on = S.lids.indexOf(u.lid) >= 0;
        return '<label><input type="checkbox" data-om="lid" value="' + esc(u.lid) + '"' + (on ? ' checked' : '') + '> <bdi>' + esc(u.name) + '</bdi></label>';
      }).join('') + '</div></div>';
    var kinds = KINDS.filter(function (k) { return k[0] !== 'since_last' || o.last; });
    if (!S.kind) S.kind = o.last ? 'since_last' : 'quarter';
    h += '<div class="om-field"><label for="omKind">الفترة</label><select id="omKind" data-om="kind">' +
      kinds.map(function (k) { return opt(k[0], k[1], k[0] === S.kind); }).join('') + '</select>' +
      (o.last ? '<span class="om-step">آخر اجتماع: ' + esc(d(o.last.meeting_date)) + ' — يغطي حتى ' + esc(d(o.last.period_to)) + '</span>' : '') +
      '</div>';
    if (S.kind === 'custom') {
      h += '<div class="om-row2"><div class="om-field"><label for="omFirst">من شهر</label><input type="month" id="omFirst" data-om="first" value="' + esc(S.first) + '"></div>' +
        '<div class="om-field"><label for="omLast">إلى شهر</label><input type="month" id="omLast" data-om="last" value="' + esc(S.last) + '"></div></div>';
    }
    h += '<button class="btn primary om-go" data-om="build"' + (S.lids.length ? '' : ' disabled') + '>تجهيز الاجتماع</button>' +
      '<p class="om-muted" style="margin-top:10px">التجهيز يأخذ لقطة ثابتة من كشف المالك والحجوزات. لا يُرسل شيء للمالك من هنا.</p>';
    return h;
  }

  function statusHtml(m) {
    if (!m) return '<p class="om-muted">جهّز اجتماعاً أو اختر اجتماعاً سابقاً من القائمة.</p>';
    var mt = m.meeting || {};
    var h = '<h3>اجتماع ' + esc(d(mt.meeting_date)) + ' · ' + esc(STATE[mt.state] || mt.state || '') + '</h3>' +
      '<div class="om-step">الفترة من ' + esc(d(mt.period_from)) + ' إلى ' + esc(d(mt.period_to)) + '</div>';
    if (mt.state === 'building') {
      h += '<div class="om-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + (mt.build_progress || 0) +
        '"><i style="transform:scaleX(' + ((mt.build_progress || 0) / 100) + ')"></i></div><div class="om-step">' + esc(mt.build_step || '') +
        (m.queue ? (m.queue.waiting_ahead ? ' · قبله في الطابور ' + m.queue.waiting_ahead : '') + ' · ' + m.queue.elapsed_s + ' ثانية' : '') + '</div>';
    } else if (mt.state === 'error') {
      h += '<p class="om-err">' + esc(mt.build_error || 'تعذّر التجهيز') + '</p>' +
        '<div class="om-acts"><button class="btn sm" data-om="rebuild">أعد التجهيز</button></div>';
    } else if (m.version) {
      var checks = arr(m.readiness);
      h += '<ul class="om-checks">' + (checks.length ? checks.map(function (c) {
        return '<li><span class="om-tag ' + esc(c.level) + '">' + (c.level === 'red' ? 'يمنع الإرسال' : 'تنبيه') + '</span><span>' + esc(c.text_ar) + '</span></li>';
      }).join('') : '<li><span class="om-tag ok">سليم</span><span>كل الفحوص سليمة.</span></li>') + '</ul>' +
        '<div class="om-acts"><button class="btn primary sm" data-om="present">افتح العرض</button>' +
        '<button class="btn sm" data-om="notes">نافذة ملاحظاتي</button>' +
        (mt.state !== 'sent' ? '<button class="btn ghost sm" data-om="rebuild">أعد التجهيز</button>' : '') + '</div>' +
        '<p class="om-muted" style="margin-top:10px">شارك تبويب العرض فقط. نافذة الملاحظات لك وحدك (أو افتحها في جوالك).</p>' +
        sendHtml(m);
    }
    return h;
  }

  function sendHtml(m) {
    var mt = m.meeting || {};
    var rec = m.record || { decisions: [], commitments: [] };
    var h = '<div style="margin-top:14px;border-top:1px solid var(--line);padding-top:12px"><h3>الإرسال للمالك</h3>' +
      '<p class="om-muted">في السجل: ' + arr(rec.decisions).length + ' قرار و' + arr(rec.commitments).length + ' التزام.</p>';
    var live = arr(m.links).filter(function (l) { return l.active; })[0];
    if (mt.state === 'sent' && live) {
      h += '<p class="om-step">رابط المالك (للقراءة فقط):</p><p><bdi style="word-break:break-all">' + esc(live.url) + '</bdi></p>' +
        '<p class="om-step">فُتح ' + esc(live.opens) + ' مرة' + (live.last_opened_at ? ' · آخر فتح ' + esc(d(live.last_opened_at)) : '') + '</p>' +
        '<div class="om-acts"><a class="btn primary sm" href="/api/meet/meetings/' + esc(mt.id) + '/wa" target="_blank" rel="noopener">افتح واتساب برسالة جاهزة</a>' +
        '<a class="btn sm" href="' + esc(live.url) + '" target="_blank" rel="noopener">افتح الرابط</a>' +
        '<a class="btn sm" href="' + esc(live.pdf) + '" target="_blank" rel="noopener">PDF</a>' +
        '<button class="btn ghost sm" data-om="revoke" data-token="' + esc(live.token) + '">أوقف الرابط</button>' +
        '<button class="btn ghost sm" data-om="reopen">أعد فتح الاجتماع</button></div>' +
        '<p class="om-muted" style="margin-top:8px">واتساب يفتح برسالة مكتوبة، ولا يُرسل شيء إلا إذا ضغطت إرسال في واتساب.</p>';
    } else {
      h += m.can_send ? '<div class="om-acts"><button class="btn primary sm" data-om="send">جمّد وأنشئ رابط المالك</button></div>' +
        '<p class="om-muted" style="margin-top:8px">التجميد يحفظ نسخة لا تتغيّر، وينشئ رابطاً وPDF. لا يُرسل شيء للمالك حتى تفتح واتساب وترسل بنفسك.</p>' :
        '<p class="om-err">الإرسال موقوف: ' + esc(m.send_block || 'فحص أحمر مفتوح') + '</p>';
    }
    if (S.sendMsg) h += '<p class="om-step" style="margin-top:8px">' + esc(S.sendMsg) + '</p>';
    return h + '</div>';
  }

  function commitsHtml() {
    var cs = arr(S.commits);
    if (!S.owner || !cs.length) return '';
    return '<div class="om-panel" style="margin-top:14px"><h3>متابعة التزامات الاجتماعات السابقة</h3>' +
      '<p class="om-muted">ما تحدّثه هنا يظهر للمالك في فصل «ما وعدناك به» في الاجتماع القادم. التذكرة المرتبطة إذا أُغلقت تُحسب «تم» تلقائياً.</p>' +
      '<table class="om-list"><thead><tr><th>الاجتماع</th><th>الالتزام</th><th>الحالة</th><th>الدليل</th><th></th></tr></thead><tbody>' +
      cs.map(function (c) {
        return '<tr><td>' + esc(d(c.meeting_date)) + '</td><td>' + esc(c.side === 'ouja' ? 'علينا: ' : 'على المالك: ') + esc(c.text) + '</td>' +
          '<td><select data-cst="' + esc(c.id) + '">' + CSTATUS.map(function (x) {
            return '<option value="' + x[0] + '"' + (x[0] === c.status ? ' selected' : '') + '>' + x[1] + '</option>';
          }).join('') + '</select></td><td><input data-cev="' + esc(c.id) + '" value="' + esc(c.evidence || '') + '" placeholder="أُرسلت الصور" style="min-height:36px"></td>' +
          '<td><button class="btn sm" data-om="csave" data-cid="' + esc(c.id) + '">حفظ</button></td></tr>';
      }).join('') + '</tbody></table></div>';
  }

  function listHtml() {
    var ms = arr(S.meetings);
    if (!S.owner) return '';
    if (!ms.length) return '<p class="om-muted">لا توجد اجتماعات سابقة لهذا المالك.</p>';
    return '<table class="om-list"><thead><tr><th>التاريخ</th><th>الفترة</th><th>الحالة</th></tr></thead><tbody>' +
      ms.map(function (m) {
        return '<tr data-om="open" data-id="' + esc(m.id) + '"><td>' + esc(d(m.meeting_date)) + '</td><td>' + esc(d(m.period_from)) +
          ' ← ' + esc(d(m.period_to)) + '</td><td>' + esc(STATE[m.state] || m.state) + '</td></tr>';
      }).join('') + '</tbody></table>';
  }

  function abHtml() {
    var a = S.ab;
    var h = '<h3>تقرير فرص المضيف من Airbnb</h3>';
    if (!a) return h + '<p class="om-muted">جاري التحميل…</p>';
    h += a.latest ? '<p class="om-muted">آخر تقرير: بيانات ' + esc(d(a.latest.data_as_of)) + ' · ' + esc(a.latest.rows) +
      ' سطراً · مربوط ' + esc(a.mapped) + ' · سعر الدولار ' + esc(a.latest.fx_sar_per_usd) + ' ريال</p>' :
      '<p class="om-muted">لم يُستورد أي تقرير بعد. الاجتماع يعرض فصل «كيف يصل إلينا الضيف» فاضياً حتى تستورده.</p>';
    h += '<div class="om-acts"><input type="file" id="omAbFile" accept=".tsv,.csv,.xlsx,.txt" aria-label="ملف تقرير Airbnb">' +
      '<button class="btn sm" data-om="abup">استيراد التقرير</button></div>';
    if (S.abMsg) h += '<p class="om-step" style="margin-top:8px">' + esc(S.abMsg) + '</p>';
    var un = arr(a.unmapped);
    if (un.length) {
      var opts = arr(a.choices);
      h += '<p class="om-muted" style="margin-top:12px">أسطر بلا شقة مربوطة (' + un.length + '): اختر الشقة الصحيحة واضغط «اربط». المقترح محدّد مسبقاً، ولا يُستخدم حتى تؤكده.</p>' +
        '<table class="om-list"><thead><tr><th>عنوان Airbnb</th><th>الغرف</th><th>الشقة عندنا</th><th></th></tr></thead><tbody>' +
        un.map(function (r) {
          var sug = r.suggest ? r.suggest.lid : '';
          return '<tr><td><bdi>' + esc(r.title) + '</bdi></td><td>' + esc(r.bedrooms == null ? '' : r.bedrooms) + '</td><td><select data-ab="' + esc(r.airbnb_id) + '">' +
            '<option value="">— ليست عندنا —</option>' + opts.map(function (o) {
              return '<option value="' + esc(o.lid) + '"' + (String(o.lid) === String(sug) ? ' selected' : '') + '>' + esc(o.name) + '</option>';
            }).join('') + '</select></td><td><button class="btn sm" data-om="abmap" data-aid="' + esc(r.airbnb_id) + '">اربط</button></td></tr>';
        }).join('') + '</tbody></table>';
    }
    return h;
  }

  function paint() {
    putHtml('omBody', '<div class="om-grid"><div><div class="om-panel"><h3>تجهيز اجتماع</h3>' + formHtml() + '</div>' +
      '<div class="om-panel" style="margin-top:14px" id="omAb">' + abHtml() + '</div></div>' +
      '<div><div class="om-panel" id="omStatus">' + statusHtml(S.active) + '</div>' +
      '<div class="om-panel" style="margin-top:14px"><h3>الاجتماعات السابقة</h3>' + listHtml() + '</div>' + commitsHtml() + '</div></div>');
  }

  function loadAb() {
    api('/api/meet/airbnb').then(function (x) { S.ab = (x && x.ok) ? x : { unmapped: [], choices: [] }; paint(); })
      .catch(function () { S.ab = { unmapped: [], choices: [] }; paint(); });
  }

  function abUpload() {
    var f = document.getElementById('omAbFile');
    if (!f || !f.files || !f.files[0]) { S.abMsg = 'اختر ملف التقرير أولاً'; paint(); return; }
    var fd = new FormData();
    fd.append('file', f.files[0]);
    S.abMsg = 'جاري الاستيراد…'; paint();
    fetch('/api/meet/airbnb/import', { method: 'POST', headers: { 'X-Token': tok() }, body: fd })
      .then(function (r) { return r.json(); })
      .then(function (x) {
        if (!x || !x.ok) { S.abMsg = (x && x.error_ar) || 'تعذّر الاستيراد'; paint(); return; }
        S.ab = x;
        S.abMsg = x.imported && x.imported.duplicate ? 'هذا الملف مستورد من قبل — لم يتغيّر شيء.' :
          ('استُورد التقرير: بيانات ' + d(x.imported.data_as_of) + ' · ' + x.imported.rows + ' سطراً.');
        paint();
      }).catch(function () { S.abMsg = 'تعذّر الاستيراد'; paint(); });
  }

  function abMap(aid) {
    var sel = document.querySelector('select[data-ab="' + aid + '"]');
    post('/api/meet/airbnb/map', { airbnb_id: aid, lid: sel ? sel.value : '' }).then(function (x) {
      if (x && x.ok) { S.ab = x; S.abMsg = 'رُبط السطر.'; } else { S.abMsg = (x && x.error_ar) || 'تعذّر الربط'; }
      paint();
    });
  }

  function paintStatus() {
    var el = document.getElementById('omStatus');
    if (el) el.innerHTML = statusHtml(S.active);
  }

  function loadMeetings() {
    if (!S.owner) { S.meetings = []; S.commits = []; paint(); return; }
    api('/api/meet/meetings?owner=' + encodeURIComponent(S.owner)).then(function (x) {
      S.meetings = arr(x && x.meetings);
      paint();
    }).catch(function () { S.meetings = []; paint(); });
    api('/api/meet/commitments?owner=' + encodeURIComponent(S.owner)).then(function (x) {
      S.commits = arr(x && x.commitments);
      paint();
    }).catch(function () { S.commits = []; });
  }

  function act(path, body, okMsg) {
    var mid = S.active && S.active.meeting ? S.active.meeting.id : null;
    post(path, body || {}).then(function (x) {
      S.sendMsg = (x && x.ok) ? okMsg : ((x && x.error_ar) || 'تعذّر التنفيذ');
      if (mid) poll(mid);
    });
  }

  function poll(id) {
    clearTimeout(S.timer);
    api('/api/meet/meetings/' + id).then(function (d) {
      if (!d || !d.ok) { S.active = null; paintStatus(); return; }
      S.active = d;
      paintStatus();
      if (d.meeting && d.meeting.state === 'building') S.timer = setTimeout(function () { poll(id); }, 1500);
      else loadMeetings();
    }).catch(function () { S.timer = setTimeout(function () { poll(id); }, 4000); });
  }

  function build(id) {
    if (S.posting) return;                       // a double-click must not queue a second build
    S.posting = true;
    var body = id ? { rebuild: id } : { owner: S.owner, lids: S.lids, kind: S.kind, first: S.first, last: S.last };
    post('/api/meet/meetings', body).then(function (d) {
      S.posting = false;
      if (!d || !d.ok) {
        var el = document.getElementById('omStatus');
        if (el) el.innerHTML = '<p class="om-err">' + esc((d && (d.error_ar || d.message)) || 'تعذّر بدء التجهيز') + '</p>';
        return;
      }
      poll(d.id);
    }).catch(function () { S.posting = false; });
  }

  function onEvent(e) {
    var t = e.target.closest ? e.target.closest('[data-om]') : null;
    if (!t || !document.getElementById('omBody').contains(t)) return;
    var a = t.getAttribute('data-om');
    if (e.type === 'change') {
      if (a === 'owner') {
        S.owner = t.value; S.kind = ''; S.active = null;
        var o = owner();
        S.lids = o ? arr(o.units).map(function (u) { return u.lid; }) : [];
        loadMeetings();
      } else if (a === 'lid') {
        var v = parseInt(t.value, 10);
        S.lids = S.lids.filter(function (x) { return x !== v; });
        if (t.checked) S.lids.push(v);
        paint();
      } else if (a === 'kind') { S.kind = t.value; paint(); }
      else if (a === 'first') { S.first = t.value; }
      else if (a === 'last') { S.last = t.value; }
      return;
    }
    if (e.type !== 'click') return;
    var mid = S.active && S.active.meeting ? S.active.meeting.id : null;
    if (a === 'build') build(null);
    else if (a === 'rebuild' && mid) build(mid);
    else if (a === 'present' && mid) window.open('/meet/' + mid, 'ouja-meet-' + mid);
    else if (a === 'notes' && mid) window.open('/meet/' + mid + '/notes', 'ouja-meet-notes-' + mid, 'width=760,height=900');
    else if (a === 'open') poll(t.getAttribute('data-id'));
    else if (a === 'abup') abUpload();
    else if (a === 'send' && mid) act('/api/meet/meetings/' + mid + '/send', {}, 'جُمّد الاجتماع وأُنشئ رابط المالك. افتح واتساب لإرساله بنفسك.');
    else if (a === 'revoke') act('/api/meet/links/' + t.getAttribute('data-token') + '/revoke', {}, 'أُوقف الرابط — لم يعد يفتح.');
    else if (a === 'reopen' && mid) {
      var why = window.prompt('سبب إعادة فتح الاجتماع (يُحفظ في السجل):');
      if (why) act('/api/meet/meetings/' + mid + '/reopen', { reason: why }, 'أُعيد فتح الاجتماع. جهّزه من جديد ثم أرسله.');
    }
    else if (a === 'csave') {
      var cid = t.getAttribute('data-cid');
      var st = document.querySelector('select[data-cst="' + cid + '"]');
      var ev = document.querySelector('input[data-cev="' + cid + '"]');
      post('/api/meet/commitments/' + cid, { status: st ? st.value : null, evidence: ev ? ev.value : null }).then(function () { loadMeetings(); });
    }
    else if (a === 'abmap') abMap(t.getAttribute('data-aid'));
  }

  function load(force) {
    css();
    var root = document.getElementById('omBody');
    if (!root) return;
    if (!root.__omBound) {
      root.addEventListener('click', onEvent);
      root.addEventListener('change', onEvent);
      root.__omBound = 1;
    }
    if (S.owners.length && !force) { paint(); return; }
    putHtml('omBody', '<div class="empty sk">جاري التحميل…</div>');
    api('/api/meet/owners').then(function (d) {
      if (!d || !d.ok) { putHtml('omBody', errorState('loadMeet(1)', (d && d.error_ar) || '')); return; }
      S.owners = arr(d.owners);
      paint();
      loadAb();
    }).catch(function () { putHtml('omBody', errorState('loadMeet(1)')); });
  }

  window.MeetTab = { load: load };
})();
