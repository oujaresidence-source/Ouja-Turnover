# -*- coding: utf-8 -*-
"""
ops.page — two standalone pages, deliberately NOT a new dashboard tab.

    /appeal/{token}  the employee's answer to a warning. Token only, no login, Arabic, RTL,
                     phone-first: one textarea and one optional photo.
    /compliance      what the owner and the leaders read: the dry-run log, who is unreachable,
                     live commission, open appeals.

DASHBOARD_HTML is the file that has killed the login twice, so nothing here touches it.

SAME BACKSLASH TRAP as DASHBOARD_HTML and schedule/page.py: these are normal triple-quoted
strings, so a backslash escape typed into the JS is eaten by PYTHON first and the script dies.
There are ZERO backslashes in this file — real newlines, event delegation, no inline onclick
quote-building, no regex literals. Keep it that way, and esprima-parse after any edit.

Design tokens are the locked Ouja set already used by schedule/page.py: warm tinted neutrals,
gold accent, maroon only for real trouble. No pure black, no gradient text, no glass.
"""

_CSS = """
  :root{
    --bg:#F1EDE6; --panel:#FAF7F1; --ink:#292925; --body:#33302B; --muted:#9C958A;
    --gold:#B29A6A; --gold-soft:#F0E8D8; --maroon:#8B3748; --maroon-soft:#F3E2E4;
    --green:#4A6246; --green-soft:#E4EBE2; --border:#E7DFD1;
    --r:16px; --r-sm:11px; --sh:0 1px 2px rgba(41,41,37,.04),0 10px 30px rgba(41,41,37,.07);
    --ease:cubic-bezier(0.23,1,0.32,1); --font:'Tajawal',-apple-system,system-ui,sans-serif;
    --num:'Inter',sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);line-height:1.6}
  body{padding:max(16px,env(safe-area-inset-top)) 16px calc(34px + env(safe-area-inset-bottom))}
  .wrap{max-width:760px;margin:0 auto}
  .num{font-family:var(--num);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate;display:inline-block}
  h1{font-size:22px;font-weight:800;color:var(--ink);margin:0 0 4px;letter-spacing:-.01em}
  .sub{color:var(--muted);font-size:13.5px;margin-bottom:18px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    box-shadow:var(--sh);padding:18px;margin-bottom:14px}
  .card h2{font-size:15px;font-weight:800;color:var(--ink);margin:0 0 12px}
  label{display:block;font-weight:700;font-size:14px;color:var(--ink);margin:0 0 6px}
  textarea,input[type=text]{width:100%;border:1px solid var(--border);border-radius:var(--r-sm);
    padding:12px;font-family:var(--font);font-size:15.5px;background:#fff;color:var(--body);resize:vertical}
  textarea:focus,input:focus{outline:2px solid var(--gold);outline-offset:1px;border-color:var(--gold)}
  .hint{color:var(--muted);font-size:12.5px;margin-top:6px}
  button{font-family:var(--font);font-weight:700;font-size:15px;border-radius:999px;cursor:pointer;
    min-height:46px;padding:11px 22px;border:1px solid var(--border);background:var(--panel);color:var(--body);
    transition:transform .12s var(--ease),background .15s,color .15s,border-color .15s}
  button:active{transform:scale(.97)}
  button:disabled{opacity:.5;cursor:not-allowed;transform:none}
  .primary{background:var(--ink);color:#fff;border-color:var(--ink)}
  .danger{background:var(--maroon-soft);color:var(--maroon);border-color:#E6CDD2}
  .ghost{background:transparent}
  .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  .pill{display:inline-block;border-radius:999px;padding:3px 11px;font-size:12.5px;font-weight:700}
  .p-ok{background:var(--green-soft);color:var(--green)}
  .p-warn{background:var(--maroon-soft);color:var(--maroon)}
  .p-wait{background:var(--gold-soft);color:#7A6742}
  .p-mute{background:#EFEAE1;color:var(--muted)}
  table{width:100%;border-collapse:collapse;font-size:14px}
  th{text-align:right;font-size:12px;color:var(--muted);font-weight:700;padding:8px 6px;
    border-bottom:1px solid var(--border);white-space:nowrap}
  td{padding:11px 6px;border-bottom:1px solid var(--border);vertical-align:middle}
  tr:last-child td{border-bottom:0}
  .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
  .banner{border-radius:var(--r);padding:13px 16px;margin-bottom:14px;font-size:14px;font-weight:700}
  .b-dry{background:var(--gold-soft);color:#7A6742;border:1px solid #E3D6BC}
  .b-bad{background:var(--maroon-soft);color:var(--maroon);border:1px solid #E6CDD2}
  .b-ok{background:var(--green-soft);color:var(--green);border:1px solid #D5E0D2}
  .swrow{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--border)}
  .swrow:last-of-type{border-bottom:0}
  .swrow button{min-width:96px}
  .idbox{width:190px;min-width:150px;padding:8px 10px;font-family:var(--num);font-size:13px;
    direction:ltr;text-align:left;border-radius:var(--r-sm)}
  .idmsg{margin-top:4px;max-width:210px}
  .log{font-family:var(--num);font-size:12.5px;color:var(--body);direction:rtl}
  .log div{padding:7px 0;border-bottom:1px dashed var(--border)}
  .muted{color:var(--muted)}
  .steps{display:flex;gap:6px;margin:12px 0 0}
  .step{flex:1;text-align:center;font-size:12.5px;font-weight:700;padding:8px 4px;border-radius:var(--r-sm);
    background:#EFEAE1;color:var(--muted)}
  .step.on{background:var(--ink);color:#fff}
  .step.done{background:var(--green-soft);color:var(--green)}
  @media (prefers-reduced-motion:reduce){*{transition:none !important}}
"""

_HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@600;700&display=swap" rel="stylesheet">"""


# ===================================================================== the appeal page

APPEAL_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
""" + _HEAD + """
<title>اعتراض على إنذار</title>
<style>""" + _CSS + """</style>
</head>
<body>
<div class="wrap">
  <h1>اعتراض على إنذار</h1>
  <div class="sub">اكتب لنا وش صار. اعتراضك يوصل مباشرة للمسؤولين، ولازم يردون عليك.</div>
  <div id="app"><div class="card muted">لحظة…</div></div>
</div>
<script>
var TOKEN = location.pathname.split('/').filter(Boolean).pop() || '';
var PHOTO = '';

function esc(s){
  var d = document.createElement('div');
  d.textContent = (s === null || s === undefined) ? '' : String(s);
  return d.innerHTML;
}
function el(id){ return document.getElementById(id); }

function load(){
  fetch('/api/ops/appeal/' + encodeURIComponent(TOKEN))
    .then(function(r){ return r.json(); })
    .then(render)
    .catch(function(){
      el('app').innerHTML = '<div class="card">صار خطأ مؤقت — حدّث الصفحة وجرّب مرة ثانية.</div>';
    });
}

function stagesBar(d){
  var names = d.stages || [];
  var cur = d.appeal ? d.appeal.stage : 's1';
  var order = ['s1','s2','s3'];
  var idx = order.indexOf(cur);
  if (cur === 'closed') idx = 3;
  var out = '<div class="steps">';
  for (var i = 0; i < names.length; i++){
    var cls = 'step';
    if (i < idx) cls += ' done';
    else if (i === idx) cls += ' on';
    out += '<div class="' + cls + '">' + esc(names[i]) + '</div>';
  }
  return out + '</div>';
}

function history(d){
  if (!d.appeal || !d.appeal.decisions || !d.appeal.decisions.length) return '';
  var lab = {opened:'قدّمت الاعتراض', accepted:'انقبل', rejected:'انرفض',
             escalated:'انتقل للمرحلة اللي بعدها', auto_escalated:'انتقل تلقائياً بعد ٢٤ ساعة'};
  var out = '<div class="card"><h2>مسار الاعتراض</h2><div class="log">';
  for (var i = 0; i < d.appeal.decisions.length; i++){
    var x = d.appeal.decisions[i];
    out += '<div><b>' + esc(lab[x.action] || x.action) + '</b>'
        + (x.by ? ' — ' + esc(x.by) : '')
        + (x.reason ? '<div class="muted">' + esc(x.reason) + '</div>' : '')
        + '<div class="muted num">' + esc((x.at || '').slice(0, 16).replace('T', ' ')) + '</div></div>';
  }
  return out + '</div></div>';
}

function render(d){
  if (!d.ok){
    el('app').innerHTML = '<div class="card"><b>' + esc(d.error || 'الرابط غير صحيح') + '</b>'
      + '<div class="hint">إذا تعتقد إن فيه غلط، كلّم المسؤول مباشرة.</div></div>';
    return;
  }
  var w = d.warning;
  var head = '<div class="card"><h2>الإنذار</h2>'
    + '<div>' + esc(w.reason_ar || 'التقرير الأسبوعي') + '</div>'
    + '<div class="muted num" style="margin-top:6px">'
    + esc((w.issued_at || '').slice(0, 16).replace('T', ' ')) + '</div>'
    + (w.status === 'voided'
        ? '<div class="banner b-ok" style="margin-top:12px">هذا الإنذار انلغى ✅</div>' : '')
    + '</div>';

  if (d.appeal){
    var done = d.appeal.outcome;
    var msg = done === 'accepted'
        ? '<div class="banner b-ok">اعتراضك انقبل — انلغى الإنذار ورجعت عمولتك ✅</div>'
        : (done === 'rejected'
            ? '<div class="banner b-bad">اعتراضك انرفض. تقدر تكلّم فيصل مباشرة.</div>'
            : '<div class="banner b-dry">اعتراضك قيد المراجعة عند '
              + esc(d.appeal.stage_name) + '. لازم يرد خلال ٢٤ ساعة، وإذا ما رد ينتقل تلقائياً للي بعده.</div>');
    el('app').innerHTML = head + msg + stagesBar(d) + history(d);
    return;
  }

  el('app').innerHTML = head
    + '<div class="card">'
    + '<label for="txt">وش صار؟</label>'
    + '<textarea id="txt" rows="6" placeholder="اكتب بالتفصيل — كل اللي تكتبه يوصل للمسؤولين"></textarea>'
    + '<div style="margin-top:14px">'
    +   '<label for="pic">صورة (اختياري)</label>'
    +   '<input type="file" id="pic" accept="image/*">'
    +   '<div class="hint" id="pichint">إذا عندك إثبات — سكرين شوت أو صورة — أرفقها.</div>'
    + '</div>'
    + '<div class="row" style="margin-top:16px">'
    +   '<button class="primary" id="send">أرسل الاعتراض</button>'
    +   '<span class="muted" id="state"></span>'
    + '</div></div>'
    + stagesBar(d);
}

// downscale in the browser: the appeal database must never become a photo store
function readPhoto(file){
  var reader = new FileReader();
  reader.onload = function(e){
    var img = new Image();
    img.onload = function(){
      var max = 1000;
      var w = img.width, h = img.height;
      if (w > max || h > max){
        var k = Math.min(max / w, max / h);
        w = Math.round(w * k); h = Math.round(h * k);
      }
      var c = document.createElement('canvas');
      c.width = w; c.height = h;
      c.getContext('2d').drawImage(img, 0, 0, w, h);
      PHOTO = c.toDataURL('image/jpeg', 0.7);
      if (PHOTO.length > 700000){ PHOTO = c.toDataURL('image/jpeg', 0.45); }
      var hint = el('pichint');
      if (hint) hint.textContent = 'الصورة جاهزة ✅';
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

function submit(){
  var txt = (el('txt') ? el('txt').value : '').trim();
  if (!txt){
    el('state').textContent = 'اكتب لنا وش صار أول';
    return;
  }
  var btn = el('send');
  btn.disabled = true;
  el('state').textContent = 'نرسل…';
  fetch('/api/ops/appeal/submit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: TOKEN, text: txt, evidence: PHOTO ? [PHOTO] : []})
  }).then(function(r){ return r.json(); })
    .then(function(r){
      if (r.ok){ load(); }
      else {
        btn.disabled = false;
        el('state').textContent = r.error || 'ما انرسل — جرّب مرة ثانية';
      }
    })
    .catch(function(){
      btn.disabled = false;
      el('state').textContent = 'ما انرسل — جرّب مرة ثانية';
    });
}

document.addEventListener('click', function(ev){
  var t = ev.target;
  if (t && t.id === 'send'){ submit(); }
});
document.addEventListener('change', function(ev){
  var t = ev.target;
  if (t && t.id === 'pic' && t.files && t.files[0]){ readPhoto(t.files[0]); }
});

load();
</script>
</body>
</html>"""


# ===================================================================== the owner surface

COMPLIANCE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
""" + _HEAD + """
<title>نظام الالتزام</title>
<style>""" + _CSS + """</style>
</head>
<body>
<div class="wrap">
  <h1>نظام الالتزام</h1>
  <div class="sub" id="sub">التقرير الأسبوعي — الإنذارات والعمولة</div>
  <div id="app"><div class="card muted">لحظة…</div></div>
</div>
<script>
var TK = '';
try { TK = new URLSearchParams(location.search).get('token') || ''; } catch (e) { TK = ''; }

function esc(s){
  var d = document.createElement('div');
  d.textContent = (s === null || s === undefined) ? '' : String(s);
  return d.innerHTML;
}
function el(id){ return document.getElementById(id); }
function url(p){ return TK ? (p + (p.indexOf('?') > -1 ? '&' : '?') + 'token=' + encodeURIComponent(TK)) : p; }

function api(p){
  return fetch(url(p), {credentials: 'same-origin'}).then(function(r){ return r.json(); });
}
function post(p, body){
  return fetch(url(p), {
    method: 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {})
  }).then(function(r){ return r.json(); });
}

var STATE = null;
var SCORE = null;

function d_effect(key){
  var sw = ((STATE || {}).control || {}).switches || [];
  for (var i = 0; i < sw.length; i++){
    if (sw[i].key === key) return 'تشغيله معناه: ' + sw[i].effect;
  }
  return '';
}

function pill(status){
  var m = {done: ['p-ok', 'تم'], pending: ['p-wait', 'ما وصل بعد'], missed: ['p-warn', 'ما وصل'],
           waived: ['p-mute', 'ملغى'], excused: ['p-mute', 'معذور']};
  var x = m[status] || ['p-mute', status];
  return '<span class="pill ' + x[0] + '">' + esc(x[1]) + '</span>';
}

function controlPanel(d){
  var c = d.control || {};
  var sw = c.switches || [];
  if (!sw.length) return '';
  var out = '<div class="card"><h2>التحكم — شغّل ووقّف من هنا</h2>';
  out += '<div class="hint" style="margin-bottom:12px">'
    + 'ما تحتاج تدخل Railway. اللي تغيّره هنا يبقى حتى بعد تحديث النظام.</div>';
  for (var i = 0; i < sw.length; i++){
    var s = sw[i];
    out += '<div class="swrow">'
      + '<div style="flex:1">'
      +   '<b>' + esc(s.label) + '</b>'
      +   '<div class="hint">' + (s.dry
            ? 'وضع التجربة — يحسب كل شي وما يرسل ولا رسالة'
            : '⚠️ شغّال فعلياً — ' + esc(s.effect)) + '</div>'
      +   (s.changed_by ? '<div class="hint">آخر تغيير: ' + esc(s.changed_by) + '</div>' : '')
      + '</div>'
      + '<span class="pill ' + (s.dry ? 'p-wait' : 'p-warn') + '">'
      +   (s.dry ? 'تجربة' : 'شغّال') + '</span>'
      + '<button class="' + (s.dry ? 'primary' : 'ghost') + '"'
      +   ' data-sw="' + esc(s.key) + '" data-dry="' + (s.dry ? '0' : '1') + '">'
      +   (s.dry ? 'شغّله' : 'وقّفه') + '</button>'
      + '</div>';
  }
  if (!c.all_quiet){
    out += '<div class="row" style="margin-top:14px">'
      + '<button class="danger" data-sw="stop_all" data-dry="1">🛑 وقّف كل شي الحين</button>'
      + '</div>';
  }
  return out + '</div>';
}

function approverPanel(d){
  var ap = d.approvers || [];
  if (!ap.length) return '';
  var out = '<div class="card"><h2>سلسلة الاعتراضات</h2>'
    + '<div class="hint" style="margin-bottom:12px">'
    + 'الاعتراض يروح للأول، وإذا ما رد خلال ٢٤ ساعة ينتقل للي بعده لحاله.</div>';
  for (var i = 0; i < ap.length; i++){
    var a = ap[i];
    var src = a.source === 'page' ? 'مضاف من هنا'
            : (a.source === 'railway' ? 'من إعدادات Railway' : '⚠️ ما فيه أحد — بينتقل تلقائياً');
    out += '<div class="swrow">'
      + '<div style="flex:1"><b>' + esc(i + 1) + '. ' + esc(a.name) + '</b>'
      +   '<div class="hint">' + esc(src) + '</div></div>'
      + '<input type="text" class="idbox apbox" data-stage="' + esc(a.stage) + '"'
      +   ' value="' + esc(a.did || '') + '" placeholder="الصق المعرّف أو المنشن"'
      +   ' inputmode="numeric" autocomplete="off">'
      + '</div>';
  }
  return out + '<div class="hint" style="margin-top:10px">'
    + 'أسهل طريقة تجيب المعرّف: <b>!ouja اربط</b> في الديسكورد يعرض لك المعرّفات.</div></div>';
}

function rosterTable(d){
  var out = '<div class="card"><h2>هذا الأسبوع · ' + esc(d.period) + '</h2><div class="scroll"><table>'
    + '<tr><th>الموظف</th><th>معرّف الديسكورد</th><th>الحالة</th><th>إنذارات</th>'
    + '<th>العمولة</th><th>التذكيرات</th></tr>';
  for (var i = 0; i < d.rows.length; i++){
    var r = d.rows[i];
    out += '<tr><td><b>' + esc(r.employee) + '</b>'
        + (r.reachable ? '' : '<div><span class="pill p-warn">ما نقدر نوصله</span></div>')
        + '</td>'
        + '<td><input type="text" class="idbox" data-emp="' + esc(r.employee) + '"'
        +   ' value="' + esc(r.did || '') + '" placeholder="الصق المعرّف أو المنشن"'
        +   ' inputmode="numeric" autocomplete="off">'
        +   '<div class="hint idmsg" data-msg="' + esc(r.employee) + '">'
        +   esc(r.id_source || '') + '</div></td>'
        + '<td>' + pill(r.status) + '</td>'
        + '<td class="num">' + esc(r.active_warnings) + '</td>'
        + '<td class="num">' + Math.round(r.multiplier * 100) + '%</td>'
        + '<td class="muted num">' + esc((r.sent || []).join(' ')) + '</td></tr>';
  }
  out += '</table></div>'
    + '<div class="hint" style="margin-top:12px">'
    + 'وش هو «معرّف الديسكورد»؟ رقم طويل خاص بكل شخص. أسهل طريقة: في الديسكورد اكتب '
    + '<b>!ouja اربط اسم-الموظف @المستخدم</b> ومنشنه، والنظام يحفظه لحاله. '
    + 'أو انسخ الرقم من الديسكورد والصقه هنا.'
    + '</div></div>';
  return out;
}

function warningsCard(d){
  if (!d.warnings.length) return '<div class="card"><h2>الإنذارات</h2><div class="muted">ما فيه أي إنذار — وهذا الوضع الطبيعي.</div></div>';
  var out = '<div class="card"><h2>الإنذارات</h2><div class="scroll"><table>'
    + '<tr><th>الموظف</th><th>الأسبوع</th><th>الحالة</th><th></th></tr>';
  for (var i = 0; i < d.warnings.length; i++){
    var w = d.warnings[i];
    var st = {active: ['p-warn', 'فعّال'], voided: ['p-ok', 'ملغي'], retired: ['p-ok', 'انشال']}[w.status]
             || ['p-mute', w.status];
    out += '<tr><td><b>' + esc(w.employee) + '</b></td>'
        + '<td class="num">' + esc((w.obligation_id || '').split('_').pop()) + '</td>'
        + '<td><span class="pill ' + st[0] + '">' + esc(st[1]) + '</span></td>'
        + '<td>' + (w.status === 'active'
            ? '<button class="ghost" data-waive="' + esc(w.id) + '">إلغاء الإنذار</button>' : '')
        + '</td></tr>';
  }
  return out + '</table></div></div>';
}

function appealsCard(d){
  if (!d.appeals.length) return '';
  var out = '<div class="card"><h2>اعتراضات مفتوحة</h2>';
  for (var i = 0; i < d.appeals.length; i++){
    var a = d.appeals[i];
    out += '<div style="padding:12px 0;border-bottom:1px solid var(--border)">'
      + '<b>' + esc(a.employee) + '</b> — عند ' + esc(a.stage_name)
      + '<div class="muted" style="margin:6px 0">' + esc(a.text || '') + '</div>'
      + '<div class="row">'
      +   '<button class="primary" data-dec="accept" data-id="' + esc(a.id) + '">اقبل</button>'
      +   '<button class="danger" data-dec="reject" data-id="' + esc(a.id) + '">ارفض</button>'
      +   '<button class="ghost" data-dec="escalate" data-id="' + esc(a.id) + '">ارفعه للي بعده</button>'
      + '</div></div>';
  }
  return out + '</div>';
}

function turnoverCard(d){
  var t = d.turnover || {};
  var rows = t.rows || [];
  var out = '<div class="card"><h2>تسليم الشقق اليوم · ' + esc(t.date || '') + '</h2>';
  if (t.dryrun){
    out += '<div class="hint" style="margin-bottom:10px">وضع التجربة — ما انرسل ولا تذكير.</div>';
  }
  if (!rows.length){
    return out + '<div class="muted">ما فيه شقق مفتوحة اليوم.</div></div>';
  }
  out += '<div class="scroll"><table>'
    + '<tr><th>الشقة</th><th>المسؤول</th><th>دخول الضيف</th><th>الحالة</th><th>التذكيرات</th></tr>';
  for (var i = 0; i < rows.length; i++){
    var r = rows[i];
    var st = r.acked_at ? '<span class="pill p-ok">جاهزة</span>'
           : (r.problem_at ? '<span class="pill p-warn">فيه مشكلة</span>'
           : (r.asleep ? '<span class="pill p-wait">محوّلة (نايم)</span>'
           : (r.closed ? '<span class="pill p-mute">مقفلة</span>'
           : '<span class="pill p-wait">شغالة</span>')));
    out += '<tr><td><b>' + esc(r.unit) + '</b></td>'
        + '<td>' + esc(r.employee || '—')
        + (r.reassigned_to ? ' <span class="muted">→ ' + esc(r.reassigned_to) + '</span>' : '')
        + '</td>'
        + '<td class="num">' + esc(r.checkin_at) + '</td>'
        + '<td>' + st + '</td>'
        + '<td class="muted num">' + esc((r.levels || []).join(' ')) + '</td></tr>';
  }
  out += '</table></div>';

  var sig = t.staffing_signal || [];
  if (sig.length){
    out += '<div class="banner b-dry" style="margin-top:14px">'
      + '👥 تحويلات ليلية آخر ٣٠ يوم (مؤشّر توظيف — <b>مو</b> مخالفة): ';
    var parts = [];
    for (var j = 0; j < sig.length; j++){
      parts.push(esc(sig[j].employee) + ' (' + esc(sig[j].n) + ')');
    }
    out += parts.join(' · ') + '</div>';
  }
  return out + '</div>';
}

// «كرت التقييم» — the owner sees the score AND the raw numbers behind every single line,
// because approving a 3 you cannot explain is how the whole thing stops meaning anything.
function scorecardCard(){
  var s = SCORE || {};
  var cards = s.cards || [];
  var out = '<div class="card"><h2>كرت التقييم الشهري · ' + esc(s.month || '') + '</h2>';
  if (s.dryrun){
    out += '<div class="hint" style="margin-bottom:10px">وضع التجربة — ما ينرسل أي كرت للموظفين.</div>';
  }
  if (!cards.length){
    return out + '<div class="muted">ما فيه كروت محسوبة لهذا الشهر.</div>'
      + '<div class="row" style="margin-top:14px">'
      + '<button class="primary" id="cardcompute">احسب كروت الشهر</button></div></div>';
  }
  for (var i = 0; i < cards.length; i++){
    var c = cards[i];
    out += '<div style="padding:14px 0;border-bottom:1px solid var(--border)">'
      + '<div class="row" style="justify-content:space-between">'
      +   '<b>' + esc(c.employee) + '</b>'
      +   '<span class="num" style="font-size:20px;font-weight:800">'
      +     (c.score === null || c.score === undefined ? '—' : esc(c.score)) + ' / 5</span>'
      + '</div>'
      + '<div class="muted" style="margin:4px 0 10px">'
      +   (c.no_data_month
          ? 'ما فيه بيانات كافية لهذا الشهر — ما ينحسب كرت، وما ينحسب على أحد شي'
          : 'مكافأة التغطية: ' + esc(c.coverage_bonus) + ' · المضاعف: ' + esc(c.multiplier))
      +   (c.released_at ? ' · <b>انرسل للموظف</b>' : '') + '</div>'
      + '<div class="scroll"><table>'
      + '<tr><th>البند</th><th>الوزن</th><th>الدرجة</th><th>العيّنة</th><th></th></tr>';
    for (var j = 0; j < (c.lines || []).length; j++){
      var l = c.lines[j];
      var missing = (l.score === null || l.score === undefined);
      out += '<tr><td>' + esc(l.label || l.key)
        + (missing && l.why_ar
            ? '<div class="hint">' + esc(l.why_ar) + '</div>' : '') + '</td>'
        + '<td class="num">' + esc(Math.round(l.effective_weight)) + '%</td>'
        + '<td>' + (missing
            ? '<span class="pill p-mute">بيانات ناقصة</span>'
            : '<b class="num">' + esc(l.score) + '</b>'
              + (l.overridden ? ' <span class="pill p-wait">معدّل</span>' : '')) + '</td>'
        + '<td class="num muted">' + esc(l.sample) + '</td>'
        + '<td>' + (c.released_at ? '' :
            '<button class="ghost" data-ov="' + esc(l.key) + '"'
            + ' data-emp="' + esc(c.employee) + '">عدّل</button>') + '</td></tr>';
    }
    out += '</table></div>';
    for (var k = 0; k < (c.lines || []).length; k++){
      var ol = c.lines[k];
      if (ol.overridden){
        out += '<div class="hint">✏️ ' + esc(ol.label) + ': ' + esc(ol.overridden.by)
             + ' — ' + esc(ol.overridden.reason) + '</div>';
      }
    }
    out += '</div>';
  }
  out += '<div class="row" style="margin-top:14px">'
    + '<button class="ghost" id="cardcompute">أعد الحساب</button>'
    + '<button class="primary" id="cardrelease">اعتمد وأرسل للموظفين</button>'
    + '<span class="muted" id="cardstate"></span></div>';
  return out + '</div>';
}

function logCard(d){
  if (!d.dryrun) return '';
  if (!d.dry_log.length){
    return '<div class="card"><h2>سجل التجربة</h2><div class="muted">ما فيه شي بعد — اضغط «شغّل الفحص الآن».</div></div>';
  }
  var out = '<div class="card"><h2>سجل التجربة — وش كان بيصير لو النظام شغّال</h2><div class="log">';
  for (var i = 0; i < d.dry_log.length; i++){
    var r = d.dry_log[i];
    out += '<div>' + esc((r.at || '').slice(5, 16).replace('T', ' ')) + ' · '
        + (r.employee ? '<b>' + esc(r.employee) + '</b> · ' : '')
        + esc(r.detail || '') + '</div>';
  }
  return out + '</div></div>';
}

function render(d){
  STATE = d;
  if (!d.ok){ el('app').innerHTML = '<div class="card">' + esc(d.error || 'خطأ') + '</div>'; return; }
  var banner = d.dryrun
    ? '<div class="banner b-dry">وضع التجربة شغّال — النظام يحسب كل شي ويسجله، وما يرسل ولا رسالة وما ينسجل أي إنذار. لتشغيله فعلياً: OPS_WARN_DRYRUN=0 في Railway.</div>'
    : '<div class="banner b-bad">النظام شغّال فعلياً — الرسائل تنرسل والإنذارات تنسجل.</div>';

  var un = d.unreachable || {};
  var holes = (un.no_discord_id || []).concat((un.delivery_failures || []).map(function(x){ return x.employee; }));
  var hole = holes.length
    ? '<div class="banner b-bad">ما نقدر نوصل: ' + esc(holes.join(' · '))
      + ' — هؤلاء ما ينسجل عليهم إنذار أبداً إلى أن ينضبط الديسكورد حقهم.</div>'
    : '';

  el('sub').textContent = 'التقرير الأسبوعي · الموعد ' + (d.due_at || '').replace('T', ' ');
  el('app').innerHTML = banner + hole
    + controlPanel(d)
    + approverPanel(d)
    + rosterTable(d)
    + turnoverCard(d)
    + scorecardCard()
    + appealsCard(d)
    + warningsCard(d)
    + logCard(d)
    + '<div class="card"><h2>الملخص الشهري (اللي ينشر — بدون أسماء)</h2>'
    +   '<div>' + esc(d.summary) + '</div></div>'
    + '<div class="row" style="margin-bottom:30px">'
    +   '<button class="primary" id="tick">شغّل الفحص الآن</button>'
    +   '<span class="muted" id="state"></span></div>';
}

function load(){
  api('/api/ops/scorecard').then(function(s){ SCORE = s; }).catch(function(){ SCORE = null; })
    .then(function(){ return api('/api/ops/state'); }).then(render).catch(function(){
    el('app').innerHTML = '<div class="card">ما قدرنا نجيب البيانات — تأكد من الرابط والتوكن.</div>';
  });
}

// Saving an id must never redraw the table under the owner's fingers while they are still
// typing in the next row, so this patches ONE line of text instead of calling load().
function saveId(input){
  var emp = input.getAttribute('data-emp');
  var msg = document.querySelector('[data-msg="' + emp + '"]');
  if (msg){ msg.textContent = 'نحفظ…'; }
  post('/api/ops/identity', {employee: emp, discord_id: input.value}).then(function(r){
    if (!msg) return;
    msg.textContent = r.ok ? (r.message || 'انحفظ') : (r.error || 'ما انحفظ');
    msg.style.color = r.ok ? 'var(--green)' : 'var(--maroon)';
    if (r.ok){
      var pillEl = input.closest('tr').querySelector('.p-warn');
      if (pillEl && r.discord_id){ pillEl.remove(); }
    }
  }).catch(function(){
    if (msg){ msg.textContent = 'ما انحفظ — جرّب مرة ثانية'; msg.style.color = 'var(--maroon)'; }
  });
}

function saveApprover(input){
  var stage = input.getAttribute('data-stage');
  post('/api/ops/approver', {stage: stage, discord_id: input.value}).then(function(r){
    if (!r.ok) alert(r.error || 'ما انحفظ');
    load();
  });
}

document.addEventListener('change', function(ev){
  var t = ev.target;
  if (!t || !t.className) return;
  if (t.className.indexOf('apbox') > -1){ saveApprover(t); return; }
  if (t.className.indexOf('idbox') > -1){ saveId(t); }
});
document.addEventListener('keydown', function(ev){
  var t = ev.target;
  if (ev.key === 'Enter' && t && t.className && t.className.indexOf('idbox') > -1){
    t.blur();
  }
});

document.addEventListener('click', function(ev){
  var t = ev.target;
  if (!t || !t.getAttribute) return;

  if (t.id === 'tick'){
    t.disabled = true;
    el('state').textContent = 'نفحص…';
    post('/api/ops/tick', {}).then(function(){ load(); });
    return;
  }
  var sw = t.getAttribute('data-sw');
  if (sw){
    var wantDry = t.getAttribute('data-dry') === '1';
    var body = {key: sw, dry: wantDry};
    if (!wantDry){
      var word = prompt((d_effect(sw) || '') + String.fromCharCode(10)
        + 'اكتب كلمة «' + ((STATE.control || {}).confirm_word || '') + '» عشان تشغّله فعلياً:');
      if (!word) return;
      body.confirm = word;
    }
    t.disabled = true;
    post('/api/ops/switch', body).then(function(r){
      if (!r.ok) alert(r.error || 'ما ضبط');
      else if (!wantDry) alert(r.message || '');
      load();
    });
    return;
  }
  var wid = t.getAttribute('data-waive');
  if (wid){
    var why = prompt('ليش تلغي هذا الإنذار؟ (لازم سبب مكتوب)');
    if (!why || !why.trim()) return;
    post('/api/ops/waive', {warning_id: wid, reason: why}).then(function(r){
      if (!r.ok) alert(r.error || 'ما ضبط');
      load();
    });
    return;
  }
  if (t.id === 'cardcompute'){
    t.disabled = true;
    var cs = el('cardstate'); if (cs) cs.textContent = 'نحسب…';
    post('/api/ops/scorecard-compute', {}).then(function(){ load(); });
    return;
  }
  if (t.id === 'cardrelease'){
    if (!confirm('تعتمد الكروت وترسلها للموظفين؟')) return;
    post('/api/ops/scorecard-release', {month: (SCORE || {}).month}).then(function(r){
      if (!r.ok) alert(r.error || 'ما ضبط');
      load();
    });
    return;
  }
  var ov = t.getAttribute('data-ov');
  if (ov){
    var emp = t.getAttribute('data-emp');
    var sc = prompt('الدرجة الجديدة (من ١ إلى ٥):');
    if (!sc) return;
    var why = prompt('ليش تعدّلها؟ (التعديل بدون سبب مرفوض)');
    if (!why || !why.trim()) return;
    post('/api/ops/scorecard-override', {month: (SCORE || {}).month, employee: emp,
                                         line: ov, score: sc, reason: why}).then(function(r){
      if (!r.ok) alert(r.error || 'ما ضبط');
      load();
    });
    return;
  }
  var dec = t.getAttribute('data-dec');
  if (dec){
    var id = t.getAttribute('data-id');
    var q = dec === 'accept' ? 'ليش تقبل الاعتراض؟'
          : (dec === 'reject' ? 'ليش ترفض؟ (الرفض بدون سبب مرفوض)' : 'ملاحظة قبل ما ترفعه (اختياري)');
    var why = prompt(q);
    if (dec !== 'escalate' && (!why || !why.trim())) return;
    post('/api/ops/appeal/decide', {appeal_id: id, action: dec, reason: why || ''}).then(function(r){
      if (!r.ok) alert(r.error || 'ما ضبط');
      load();
    });
    return;
  }
});

load();
</script>
</body>
</html>"""


LOGIN_HINT_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
""" + _HEAD + """
<title>نظام الالتزام</title>
<style>""" + _CSS + """</style>
</head>
<body>
<div class="wrap">
  <h1>نظام الالتزام</h1>
  <div class="card">
    هذي الصفحة تحتاج تسجيل دخول.
    <div class="hint">افتح اللوحة أول، أو استخدم الرابط اللي فيه التوكن.</div>
  </div>
</div>
</body>
</html>"""
