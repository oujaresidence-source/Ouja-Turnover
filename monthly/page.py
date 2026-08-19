# -*- coding: utf-8 -*-
"""
monthly.page — /monthly-lab, «التسعير الشهري».

SAME BACKSLASH TRAP AS DASHBOARD_HTML, schedule/page.py AND pricecheck/page.py:
the HTML below is a normal triple-quoted Python string, so Python eats any
backslash escape BEFORE the browser sees it. One stray backslash-n inside a JS
string literal becomes a real newline, the string never closes, and the whole
page dies silently.

RULE FOR THIS FILE: ZERO BACKSLASHES. Newlines come from String.fromCharCode(10).
No regex literals with escapes. Verify after any edit:
    python3 -c "import monthly.page as p; assert chr(92) not in p.HTML"
and parse every <script> with esprima.

TWO THINGS THIS SCREEN MUST NEVER DO, both of them owner rules:
  * It never shows a number without its data quality beside it. A unit priced
    from a district pool says so ON THE ROW, next to the price, so it can never
    be mistaken for a measured one.
  * It says «تقدير», never «سعر» — until real monthly bookings exist to check
    the model against.
"""

HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>التسعير الشهري — عوجا</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#FAF8F2; --surface:#FFFFFF; --surface-2:#F3F0E8; --surface-3:#E9E4D7;
  --line:#DFD8C8; --line-strong:#C8BFA9;
  --text:#17150F; --text-2:#4A4339; --mut:#736C5C;
  --gold:#8B6320; --gold-2:#6F4F18; --gold-soft:#F5ECD8;
  --red:#B3382A; --red-soft:#FBE7E3; --red-line:#E8BDB5;
  --green:#0B6E42; --green-soft:#DCF0E5;
  --blue:#2A5C8B; --blue-soft:#E4EDF6;
  --ease:cubic-bezier(0.23,1,0.32,1);
  --font-ar:'IBM Plex Sans Arabic',system-ui,-apple-system,sans-serif;
  --font-num:'Inter',system-ui,sans-serif;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font-ar);
  font-size:15px;line-height:1.6;padding:0 0 90px}
.wrap{max-width:1120px;margin:0 auto;padding:20px 18px 0}
h1{font-size:25px;font-weight:700;margin:0 0 2px;letter-spacing:-.3px}
.sub{color:var(--text-2);font-size:14px;margin:0 0 16px;max-width:72ch}
.num{font-family:var(--font-num);font-variant-numeric:tabular-nums;
  unicode-bidi:isolate;direction:ltr;display:inline-block}
.bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:0 0 18px}
select,input[type=text],input[type=number]{font:inherit;padding:9px 11px;
  border:1px solid var(--line);border-radius:10px;background:var(--surface);
  color:var(--text);min-width:150px}
.btn{font:inherit;font-weight:600;padding:9px 16px;border-radius:10px;
  border:1px solid var(--line);background:var(--surface);color:var(--text);
  cursor:pointer;transition:transform .18s var(--ease),background .18s var(--ease)}
.btn:active{transform:scale(.97)}
.btn.primary{background:var(--gold);border-color:var(--gold);color:#fff}
.btn.ghost{background:transparent}
.btn:disabled{opacity:.5;cursor:default}
.tabs{display:flex;gap:6px;border-bottom:1px solid var(--line);margin:0 0 18px}
.tab{padding:9px 14px;border:0;background:transparent;font:inherit;font-weight:600;
  color:var(--mut);cursor:pointer;border-bottom:2px solid transparent;
  transition:color .18s var(--ease),border-color .18s var(--ease)}
.tab.on{color:var(--gold-2);border-bottom-color:var(--gold)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;
  padding:18px;margin:0 0 16px}
.hero{display:flex;flex-wrap:wrap;gap:22px;align-items:flex-start}
.price{font-family:var(--font-num);font-size:46px;font-weight:700;line-height:1.05;
  letter-spacing:-1.5px}
.price small{font-size:16px;font-weight:600;color:var(--mut);letter-spacing:0}
.est{display:inline-block;margin-inline-start:10px;padding:3px 10px;border-radius:999px;
  background:var(--gold-soft);color:var(--gold-2);font-size:12.5px;font-weight:700;
  vertical-align:middle}
.bound{margin-top:8px;font-size:15px;color:var(--text-2);max-width:52ch}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.chip{padding:4px 11px;border-radius:999px;font-size:12.5px;font-weight:600;
  border:1px solid var(--line);background:var(--surface-2);color:var(--text-2)}
.chip.hi{background:var(--green-soft);border-color:#B6DCC7;color:var(--green)}
.chip.md{background:var(--gold-soft);border-color:#E3D3AC;color:var(--gold-2)}
.chip.lo{background:var(--red-soft);border-color:var(--red-line);color:var(--red)}
.chip.info{background:var(--blue-soft);border-color:#BFD6EA;color:var(--blue)}
.quality{margin-top:14px;padding:11px 13px;border-radius:11px;font-size:13.5px;
  border:1px solid var(--line);background:var(--surface-2);color:var(--text-2)}
.quality.warn{background:var(--red-soft);border-color:var(--red-line);color:var(--red)}
.gates{display:grid;gap:10px;margin-top:6px}
.gate{display:grid;grid-template-columns:112px 1fr 108px;gap:12px;align-items:center}
.gate .lbl{font-weight:600;font-size:14px}
.gate .track{height:26px;background:var(--surface-2);border-radius:8px;overflow:hidden;
  border:1px solid var(--line)}
.gate .fill{height:100%;background:var(--surface-3);
  transition:width .35s var(--ease)}
.gate.on .fill{background:var(--gold)}
.gate.on .lbl{color:var(--gold-2)}
.gate .val{text-align:left;font-family:var(--font-num);font-weight:600;font-size:14.5px}
.gate .note{grid-column:1 / -1;font-size:12.5px;color:var(--mut);margin-top:-4px}
.gate.dead .lbl,.gate.dead .val{color:var(--mut);text-decoration:line-through;
  text-decoration-thickness:1px}
.gate.dead .fill{background:repeating-linear-gradient(45deg,var(--surface-3),
  var(--surface-3) 5px,var(--surface-2) 5px,var(--surface-2) 10px)}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:9px 10px;text-align:right;border-bottom:1px solid var(--line)}
th{font-size:12.5px;color:var(--mut);font-weight:600;white-space:nowrap}
td.n,th.n{text-align:left;font-family:var(--font-num);font-variant-numeric:tabular-nums;
  unicode-bidi:isolate;direction:ltr}
tr.tot td{font-weight:700;border-top:2px solid var(--line-strong);border-bottom:0}
.neg{color:var(--red)}
.pos{color:var(--green)}
.muted{color:var(--mut)}
.rowlink{cursor:pointer;transition:background .15s var(--ease)}
.rowlink:hover{background:var(--surface-2)}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11.5px;
  font-weight:600;background:var(--surface-2);border:1px solid var(--line);color:var(--text-2)}
.pill.pool{background:var(--blue-soft);border-color:#BFD6EA;color:var(--blue)}
.pill.none{background:var(--red-soft);border-color:var(--red-line);color:var(--red)}
.slider{width:100%;margin:10px 0 4px}
.ovbox{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:8px}
.ovwarn{margin-top:10px;padding:10px 12px;border-radius:10px;background:var(--red-soft);
  border:1px solid var(--red-line);color:var(--red);font-size:13.5px;font-weight:600}
.protocol{background:var(--gold-soft);border:1px solid #E3D3AC;border-radius:12px;
  padding:14px 16px;margin:0 0 16px}
.protocol h3{margin:0 0 8px;font-size:15px;color:var(--gold-2)}
.protocol ol{margin:0;padding-inline-start:20px;font-size:13.5px;color:var(--text-2)}
.protocol li{margin:4px 0}
.anchor{margin-top:10px;font-size:13px;font-weight:600;color:var(--gold-2)}
.attr{display:grid;grid-template-columns:1fr 130px 92px;gap:10px;align-items:center;
  padding:10px 0;border-bottom:1px solid var(--line)}
.attr .nm{font-weight:600;font-size:14px}
.attr .meta{font-size:12px;color:var(--mut)}
.attr .unset{color:var(--mut);font-style:normal}
.empty{padding:34px 16px;text-align:center;color:var(--mut)}
.sk{background:linear-gradient(90deg,var(--surface-2),var(--surface-3),var(--surface-2));
  border-radius:8px;animation:sh 1.2s infinite}
@keyframes sh{0%{opacity:.6}50%{opacity:1}100%{opacity:.6}}
.costwarn{display:inline-block;padding:6px 12px;border-radius:9px;font-size:13px;
  font-weight:600;background:var(--red-soft);border:1px solid var(--red-line);
  color:var(--red)}
.toast{position:fixed;inset-inline-start:50%;transform:translateX(-50%);bottom:24px;
  background:var(--text);color:#fff;padding:11px 18px;border-radius:11px;font-size:14px;
  font-weight:600;opacity:0;pointer-events:none;transition:opacity .2s var(--ease)}
.toast.on{opacity:1}
@media (max-width:640px){
  .price{font-size:38px}
  .gate{grid-template-columns:90px 1fr 92px}
  .attr{grid-template-columns:1fr 110px}
  .attr .meta{grid-column:1 / -1}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none !important;transition:none !important}
}
</style>
</head>
<body>
<div class="wrap">
  <h1>التسعير الشهري</h1>
  <p class="sub">كم المفروض نأجر الشقة بالشهر، وليش هذا الرقم بالذات. كل رقم هنا
     تقدير محسوب من حجوزاتنا نفسها — مو سعر مؤكد.</p>

  <div class="bar">
    <select id="month"></select>
    <select id="unit"><option value="">— اختر شقة —</option></select>
    <button class="btn ghost" id="refresh">تحديث البيانات</button>
    <span id="stamp" class="muted" style="font-size:12.5px"></span>
  </div>

  <div class="tabs">
    <button class="tab on" data-tab="list">كل الشقق</button>
    <button class="tab" data-tab="unit">الشقة</button>
    <button class="tab" data-tab="attrs">مواصفات الشقة</button>
    <button class="tab" data-tab="admin">الإعدادات</button>
  </div>

  <div id="view"></div>
</div>
<div class="toast" id="toast"></div>

<script>
var NL = String.fromCharCode(10);
var TAB = 'list';
var MONTH = '';
var LID = '';
var UNITS = null;
var PRICE = null;
var ATTRS = null;
var CFG = null;

function $(id){ return document.getElementById(id); }
function he(s){
  return String(s === null || s === undefined ? '' : s)
    .split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;')
    .split('"').join('&quot;');
}
function sar(v){
  if(v === null || v === undefined || isNaN(v)) return '—';
  return Math.round(v).toLocaleString('en-US');
}
function pct(v){
  if(v === null || v === undefined || isNaN(v)) return '—';
  return Math.round(v * 100) + '%';
}
function toast(msg){
  var t = $('toast'); t.textContent = msg; t.classList.add('on');
  setTimeout(function(){ t.classList.remove('on'); }, 2600);
}
function api(path, opts){
  return fetch(path, opts).then(function(r){ return r.json(); });
}

/* ---- month options: this month and the 11 after it ---- */
function buildMonths(){
  var sel = $('month'); var now = new Date();
  var names = ['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس',
               'سبتمبر','أكتوبر','نوفمبر','ديسمبر'];
  var html = '';
  for(var i = 0; i < 12; i++){
    var d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    var mm = d.getMonth() + 1;
    var key = d.getFullYear() + '-' + (mm < 10 ? '0' + mm : String(mm));
    html += '<option value="' + key + '">' + names[d.getMonth()] + ' ' +
            d.getFullYear() + '</option>';
  }
  sel.innerHTML = html;
  MONTH = sel.value;
}

/* ---- data quality, said out loud on every surface ---- */
function basisLabel(basis){
  if(basis === 'own_history') return 'من سجل هالشقة نفسها';
  if(basis === 'district_pool') return 'من متوسط الحي — مو من هالشقة';
  if(basis === 'bedroom_pool') return 'من متوسط الحجم — مو من هالشقة';
  return 'ما فيه بيانات كافية';
}
function basisPill(basis){
  if(basis === 'own_history') return '<span class="pill">سجلها</span>';
  if(basis === 'district_pool') return '<span class="pill pool">متوسط الحي</span>';
  if(basis === 'bedroom_pool') return '<span class="pill pool">متوسط الحجم</span>';
  return '<span class="pill none">بدون بيانات</span>';
}
function confChip(c){
  var m = {high:['عالية','hi'], medium:['متوسطة','md'],
           low:['منخفضة','lo'], insufficient:['ما تكفي','lo']};
  var v = m[c] || ['—','lo'];
  return '<span class="chip ' + v[1] + '">الثقة: ' + v[0] + '</span>';
}
function boundSentence(b){
  if(b === 'floor') return 'هذا أقل سعر يغطي تكلفتنا مقارنة بالتأجير اليومي. تحته نخسر.';
  if(b === 'model') return 'هذا اللي تستاهله الشقة بمواصفاتها وأداء الحي.';
  if(b === 'ceiling') return 'وقفناه عند السقف: لازم يكون أرخص من حجز 30 ليلة وحدة وحدة، وإلا ما فيه سبب يأخذ الضيف العرض الشهري.';
  return '';
}
function noPriceReason(w){
  var m = {
    insufficient_history: 'ما عندنا حجوزات كافية لهالشقة بهذا الشهر',
    floor_above_ceiling: 'تكلفتنا أعلى من اللي يدفعه الضيف — ما ينفع تأجير شهري هذا الشهر',
    band_too_narrow: 'الفرق بين أقل سعر وأعلى سعر أضيق من 50 ريال — ما فيه مجال'
  };
  return m[w] || w || 'غير معروف';
}

/* ================= LIST ================= */
function viewList(){
  var v = $('view');
  if(!UNITS){ v.innerHTML = '<div class="card"><div class="sk" style="height:220px"></div></div>'; return; }
  var q = UNITS;
  var h = '';
  h += '<div class="card">';
  h += '<div class="chips" style="margin-top:0">';
  h += '<span class="chip">' + q.n + ' شقة</span>';
  h += '<span class="chip">' + q.n_priced + ' لها تقدير</span>';
  h += '<span class="chip ' + (q.trustworthy ? 'hi' : 'lo') + '">' +
       Math.round(q.pct_own_history * 100) + '% من سجلها نفسها</span>';
  h += '</div>';
  if(!q.trustworthy){
    h += '<div class="quality warn">أغلب الشقق تسعيرها جاي من متوسط الحي مو من سجلها. ' +
         'الأرقام تحت تقريبية أكثر من المعتاد — كل صف يقول مصدره.</div>';
  }
  h += '</div>';

  var own = [], pooled = [], none = [];
  for(var i = 0; i < q.rows.length; i++){
    var r = q.rows[i];
    if(r.price === null || r.price === undefined) none.push(r);
    else if(r.basis === 'own_history') own.push(r);
    else pooled.push(r);
  }
  own.sort(function(a, b){ return (b.price || 0) - (a.price || 0); });
  pooled.sort(function(a, b){ return (b.price || 0) - (a.price || 0); });

  h += section('من سجل الشقة نفسها', own.length + ' شقة — هذي الأرقام مقاسة',
               own, 'own');
  h += section('من متوسط الحي أو الحجم', pooled.length +
               ' شقة — تقريبية، معروضة كنطاق مو رقم واحد', pooled, 'pool');
  h += section('بدون تقدير', none.length + ' شقة', none, 'none');
  v.innerHTML = h;
}

function section(title, subtitle, rows, kind){
  if(!rows.length) return '';
  var h = '<div class="card"><h3 style="margin:0 0 2px;font-size:16px">' + he(title) + '</h3>';
  h += '<div class="muted" style="font-size:13px;margin-bottom:12px">' + he(subtitle) + '</div>';
  h += '<table><thead><tr><th>الشقة</th><th>الحي</th><th class="n">التقدير</th>';
  h += (kind === 'none' ? '<th>السبب</th>' : '<th>اللي حدّده</th><th>مصدر الرقم</th>');
  h += '<th class="n">ليالينا</th></tr></thead><tbody>';
  for(var i = 0; i < rows.length; i++){
    var r = rows[i];
    h += '<tr class="rowlink" data-lid="' + he(r.lid) + '">';
    h += '<td>' + he(r.name || r.lid) + '</td>';
    h += '<td class="muted">' + he(r.district || '—') + '</td>';
    if(kind === 'none'){
      h += '<td class="n"><span class="pill none">—</span></td>';
      h += '<td class="muted">' + he(noPriceReason(r.no_price_reason)) + '</td>';
    } else if(kind === 'pool' && r.pooled_range){
      h += '<td class="n">تقريباً ' + sar(r.pooled_range.low) + ' – ' +
           sar(r.pooled_range.high) + '</td>';
      h += '<td>' + he({floor:'الأرضية', model:'المواصفات', ceiling:'السقف'}[r.bound_by] || '—') + '</td>';
      h += '<td>' + basisPill(r.basis) + '</td>';
    } else {
      h += '<td class="n"><b>' + sar(r.price) + '</b></td>';
      h += '<td>' + he({floor:'الأرضية', model:'المواصفات', ceiling:'السقف'}[r.bound_by] || '—') + '</td>';
      h += '<td>' + basisPill(r.basis) + '</td>';
    }
    h += '<td class="n muted">' + nightsCell(r) + '</td>';
    h += '</tr>';
  }
  return h + '</tbody></table></div>';
}

/* Zero of our own nights, with a price beside it, reads as "we measured nothing
   and priced it anyway". Say which it is instead of printing a bare 0. */
function nightsCell(r){
  if(r.own_obs === null || r.own_obs === undefined) return '—';
  if(r.own_obs > 0) return String(r.own_obs);
  if(r.basis === 'district_pool') return '0 — من متوسط الحي';
  if(r.basis === 'bedroom_pool') return '0 — من متوسط الحجم';
  return '0';
}

/* ================= UNIT ================= */
function gateBar(key, label, val, bound, max, dead, note){
  var w = (val && max) ? Math.max(3, Math.round(val / max * 100)) : 0;
  var on = (key === bound && !dead) ? ' on' : '';
  var cls = dead ? ' dead' : '';
  var h = '<div class="gate' + on + cls + '"><div class="lbl">' + label + '</div>' +
          '<div class="track"><div class="fill" style="width:' + w + '%"></div></div>' +
          '<div class="val">' + sar(val) + '</div>';
  if(note) h += '<div class="note">' + he(note) + '</div>';
  return h + '</div>';
}
function viewUnit(){
  var v = $('view');
  if(!LID){ v.innerHTML = '<div class="card"><div class="empty">اختر شقة من القائمة فوق</div></div>'; return; }
  if(!PRICE){ v.innerHTML = '<div class="card"><div class="sk" style="height:260px"></div></div>'; return; }
  var p = PRICE;
  var h = '';

  h += '<div class="card"><div class="hero"><div style="flex:1;min-width:280px">';
  if(p.price === null || p.price === undefined){
    h += '<div class="price">—</div>';
    h += '<div class="bound"><b>ما فيه تقدير لهالشقة هذا الشهر.</b><br>' +
         he(noPriceReason((p.warnings || [])[0])) + '</div>';
  } else {
    h += '<div class="price">' + sar(p.price) + ' <small>ريال / شهر</small>' +
         '<span class="est">' + he(p.label_ar || 'تقدير') + '</span></div>';
    h += '<div class="bound">' + he(boundSentence(p.bound_by)) + '</div>';
  }
  h += '<div class="chips">' + confChip(p.confidence);
  h += '<span class="chip info">' + he(basisLabel(p.basis)) + '</span>';
  h += '<span class="chip">ليالينا المرصودة: ' +
       ((p.data && p.data.own_obs !== null && p.data.own_obs !== undefined) ? p.data.own_obs : '—') + '</span>';
  if(p.quality) h += '<span class="chip">' + p.quality.unanswered + ' صفة غير مسجّلة</span>';
  h += '</div>';

  if(p.basis !== 'own_history'){
    h += '<div class="quality warn">هذا الرقم مو مقاس من هالشقة — جاي من ' +
         he(basisLabel(p.basis)) + '. عامله كمؤشر، مو كقياس.</div>';
  } else {
    h += '<div class="quality">محسوب من حجوزات هالشقة نفسها في نفس الشهر من السنوات اللي فاتت.</div>';
  }
  h += '</div></div></div>';

  if(p.price !== null && p.price !== undefined){
    var g = p.gates || {};
    var mx = Math.max(g.floor || 0, g.model || 0, g.ceiling || 0) * 1.05;
    h += '<div class="card"><h3 style="margin:0 0 14px;font-size:16px">البوابات الثلاث</h3>';
    h += '<div class="gates">';
    var measured = p.quality && Math.abs((p.quality.mult || 1) - 1) > 0.000000001;
    h += gateBar('floor', 'الأرضية', g.floor, p.bound_by, mx, false, '');
    h += gateBar('model', 'المواصفات', g.model, p.bound_by, mx, !measured,
        measured ? '' :
        'ما فيه مواصفات مسجّلة لهالشقة — هذا نفس دخل التأجير اليومي، مو تقييم مستقل');
    h += gateBar('ceiling', 'السقف', g.ceiling, p.bound_by, mx, false, '');
    h += '</div>';
    h += '<div class="quality" style="margin-top:14px">الأرضية = أقل شي يغطي تكلفتنا · ' +
         'المواصفات = اللي تستاهله الشقة · السقف = أرخص من حجز 30 ليلة وحدة وحدة</div>';
    if(!measured){
      h += '<div class="quality warn">بوابة «المواصفات» مطفية: ما دام ما فيه صفات ' +
           'مسجّلة، حسابها يطلع نفس دخل التأجير اليومي بالضبط. سجّل المواصفات ' +
           'عشان تصير رقم مستقل.</div>';
    }
    h += '</div>';

    h += '<div class="card"><h3 style="margin:0 0 12px;font-size:16px">من وين طلع الرقم</h3>';
    h += '<table><tbody>';
    var comps = p.components || [];
    for(var i = 0; i < comps.length; i++){
      var c = comps[i];
      var cls = c.sar < 0 ? ' class="n neg"' : ' class="n"';
      h += '<tr><td>' + he(c.label_ar) + '</td><td' + cls + '>' + sar(c.sar) + '</td></tr>';
    }
    h += '<tr class="tot"><td>التقدير</td><td class="n">' + sar(p.price) + '</td></tr>';
    h += '</tbody></table></div>';

    var mults = p.multipliers || [];
    if(mults.length){
      h += '<div class="card"><h3 style="margin:0 0 12px;font-size:16px">وش رفع أو نزّل السعر</h3>';
      h += '<table><thead><tr><th>الصفة</th><th class="n">الدرجة</th>' +
           '<th class="n">الأثر</th></tr></thead><tbody>';
      for(var j = 0; j < mults.length; j++){
        var m = mults[j];
        var d = m.delta_sar || 0;
        h += '<tr><td>' + he(m.label_ar) + '</td><td class="n">' +
             (m.score === null || m.score === undefined ? '—' : Math.round(m.score * 10) / 10) +
             '</td><td class="n ' + (d < 0 ? 'neg' : 'pos') + '">' +
             (d > 0 ? '+' : '') + sar(d) + '</td></tr>';
      }
      h += '</tbody></table></div>';
    }

    h += '<div class="card"><h3 style="margin:0 0 6px;font-size:16px">تعديل يدوي</h3>';
    h += '<div class="muted" style="font-size:13px;margin-bottom:6px">' +
         'أي تعديل لازم له سبب مكتوب — بدون سبب ما ينحفظ.</div>';
    h += '<input class="slider" type="range" id="ovr" min="-20" max="40" step="1" value="0">';
    h += '<div class="ovbox">';
    h += '<input type="number" id="ovrnum" min="-20" max="40" step="1" value="0" style="min-width:90px">';
    h += '<span class="muted">%</span>';
    h += '<span>السعر بعد التعديل: <b class="num" id="ovrout">' + sar(p.price) + '</b> ريال</span>';
    h += '</div>';
    h += '<div id="ovrwarn"></div>';
    h += '<div class="ovbox" style="margin-top:12px">';
    h += '<input type="text" id="ovrreason" placeholder="ليش عدّلت السعر؟" style="flex:1;min-width:240px">';
    h += '<button class="btn primary" id="savequote">احفظ التسعيرة</button>';
    h += '<a class="btn ghost" id="pdfbtn" target="_blank" href="/api/mrent/quote.pdf?lid=' +
         encodeURIComponent(LID) + '&month=' + encodeURIComponent(MONTH) + '">ملف المالك (PDF)</a>';
    h += '</div>';
    if(p.saved_quote){
      h += '<div class="quality" style="margin-top:12px">آخر تسعيرة محفوظة: ' +
           '<b class="num">' + sar(p.saved_quote.final_price) + '</b> ريال · ' +
           he(p.saved_quote.created_at || '') + '</div>';
    }
    h += '</div>';

    var mc = p.market_context || {};
    h += '<div class="card"><h3 style="margin:0 0 8px;font-size:16px">سياق السوق</h3>';
    if(mc.available){
      h += '<div>الإيجار السنوي بالحي <b class="num">' + sar(mc.annual_rent) + '</b> ريال ' +
           '= <b class="num">' + sar(mc.annual_equivalent_month) + '</b> بالشهر.</div>';
      h += '<div style="margin-top:6px">تقديرنا يعادل <b class="num">' +
           (Math.round((mc.multiple || 0) * 100) / 100) + '×</b> السوق السنوي — ' +
           'مفروش ومخدوم وفواتيره مشمولة ومرن.</div>';
      h += '<div class="quality" style="margin-top:10px">' + he(mc.message_ar || '') + '</div>';
    } else {
      h += '<div class="muted">' + he(mc.message_ar || 'ما فيه مرجع سوق لهذا الحي') + '</div>';
    }
    h += '</div>';
  }
  v.innerHTML = h;
  bindUnit();
}

function bindUnit(){
  var s = $('ovr'), n = $('ovrnum');
  if(!s) return;
  function sync(val){
    var p = PRICE; if(!p || p.price === null) return;
    s.value = val; n.value = val;
    var np = p.price * (1 + val / 100);
    $('ovrout').textContent = sar(np);
    var g = p.gates || {};
    var w = '';
    if(g.floor && np < g.floor){
      w = 'تحت الأرضية بـ' + sar(g.floor - np) + ' ريال — بهذا السعر نخسر مقارنة بالتأجير اليومي.';
    } else if(g.ceiling && np > g.ceiling){
      w = 'فوق السقف بـ' + sar(np - g.ceiling) + ' ريال — الضيف يحجز 30 ليلة وحدة وحدة بأرخص.';
    }
    $('ovrwarn').innerHTML = w ? '<div class="ovwarn">' + he(w) + '</div>' : '';
  }
  s.addEventListener('input', function(){ sync(parseInt(s.value, 10) || 0); });
  n.addEventListener('input', function(){ sync(parseInt(n.value, 10) || 0); });
  sync(0);
}

/* ================= ATTRIBUTES ================= */
function viewAttrs(){
  var v = $('view');
  if(!LID){ v.innerHTML = '<div class="card"><div class="empty">اختر شقة أول</div></div>'; return; }
  if(!ATTRS){ v.innerHTML = '<div class="card"><div class="sk" style="height:300px"></div></div>'; return; }
  var a = ATTRS;
  var h = '';
  h += '<div class="protocol"><h3>طريقة التقييم — اقراها قبل ما تكتب أي رقم</h3><ol>';
  for(var i = 0; i < (a.protocol_ar || []).length; i++){
    h += '<li>' + he(a.protocol_ar[i]) + '</li>';
  }
  h += '</ol><div class="anchor">' + he(a.anchor_ar) + '</div></div>';

  h += '<div class="card">';
  h += '<div class="muted" style="font-size:13px;margin-bottom:6px">' +
       a.unanswered + ' من 16 صفة غير مسجّلة. الصفة الفاضية ما ترفع ولا تنزّل السعر.</div>';
  for(var j = 0; j < a.rows.length; j++){
    var r = a.rows[j];
    h += '<div class="attr" data-key="' + he(r.key) + '">';
    h += '<div><div class="nm">' + he(r.label_ar) + '</div>';
    h += '<div class="meta">' + (r.answered
          ? ('مسجّلة' + (r.scored_by ? ' · ' + he(r.scored_by) : ''))
          : '<span class="unset">غير مسجّلة</span>') + '</div></div>';
    if(r.kind === 'bool'){
      h += '<select data-input="' + he(r.key) + '">';
      h += '<option value=""' + (r.value === null || r.value === undefined ? ' selected' : '') + '>— غير مسجّلة —</option>';
      h += '<option value="1"' + (String(r.value) === 'True' || String(r.value) === '1' ? ' selected' : '') + '>نعم</option>';
      h += '<option value="0"' + (String(r.value) === 'False' || String(r.value) === '0' ? ' selected' : '') + '>لا</option>';
      h += '</select>';
    } else {
      h += '<input type="number" data-input="' + he(r.key) + '" value="' +
           he(r.value === null || r.value === undefined ? '' : r.value) +
           '" placeholder="' + (r.kind === 'score' ? '1 - 10' : 'رقم') + '">';
    }
    h += '<button class="btn ghost" data-save="' + he(r.key) + '">حفظ</button>';
    h += '</div>';
  }
  h += '</div>';
  v.innerHTML = h;
}

/* ================= SETTINGS ================= */
function viewAdmin(){
  var v = $('view');
  if(!CFG){ v.innerHTML = '<div class="card"><div class="sk" style="height:240px"></div></div>'; return; }
  var f = CFG.flip || {};
  var on = f.price_source === 'engine';
  var h = '';

  h += '<div class="card">';
  h += '<h3 style="margin:0 0 4px;font-size:16px">سعر موقع الضيوف</h3>';
  h += '<div class="muted" style="font-size:13px;margin-bottom:12px">' +
       'وش يشوفه الضيف في صفحة /monthly.</div>';

  /* the number that says not to flip, printed beside the switch */
  h += '<div class="' + (f.may_flip ? 'quality' : 'quality warn') + '">' +
       '<b>تغطية السجل الذاتي الآن: ' +
       (f.coverage_pct === null || f.coverage_pct === undefined ? '—' : f.coverage_pct + '%') +
       '</b> (شهر ' + he(CFG.coverage_month || '') + ') — الحد الأدنى ' + f.min_pct + '%.<br>' +
       he(f.criterion_ar || '') + '</div>';

  h += '<div class="ovbox" style="margin-top:14px">';
  h += '<button class="btn' + (!on ? ' primary' : ' ghost') + '" data-src="discount">' +
       'الخصم الثابت (الوضع الحالي)</button>';
  h += '<button class="btn' + (on ? ' primary' : ' ghost') + '" data-src="engine"' +
       (f.may_flip ? '' : ' data-needs-override="1"') + '>محرّك التسعير</button>';
  h += '</div>';

  if(!f.may_flip){
    h += '<div class="ovwarn" style="margin-top:12px">التحويل لمحرّك التسعير ' +
         'مرفوض برمجياً وقت التغطية تحت الحد. لو أصررت، اكتب السبب تحت — ' +
         'ينحفظ باسمك.</div>';
    h += '<div class="ovbox" style="margin-top:10px">';
    h += '<input type="text" id="ovreason" placeholder="سبب التجاوز" style="flex:1;min-width:240px">';
    h += '</div>';
  }
  if(f.last_change && f.last_change.at){
    h += '<div class="quality" style="margin-top:12px">آخر تغيير: ' +
         he(f.last_change.at) + (f.last_change.actor ? ' · ' + he(f.last_change.actor) : '') +
         (f.last_change.reason ? ' · ' + he(f.last_change.reason) : '') +
         (f.last_change.overridden ? ' · بتجاوز' : '') + '</div>';
  }
  h += '</div>';

  h += '<div class="card"><h3 style="margin:0 0 4px;font-size:16px">تكلفة التنظيفة</h3>';
  h += '<div class="muted" style="font-size:13px;margin-bottom:10px">' +
       'كل الأسعار مبنية على هذا الرقم. خذه من صفحة تغطية التنظيف.</div>';
  h += '<div class="ovbox"><input type="number" id="tcost" placeholder="140" value="' +
       he(CFG.turnover_cost_sar === null || CFG.turnover_cost_sar === undefined ? '' : CFG.turnover_cost_sar) +
       '" style="min-width:120px"><span class="muted">ريال للتنظيفة</span>' +
       '<button class="btn primary" id="savetcost">حفظ</button></div></div>';

  var ex = CFG.expiry || {};
  h += '<div class="card"><h3 style="margin:0 0 4px;font-size:16px">تراخيص الإعلان</h3>';
  h += '<div class="muted" style="font-size:13px;margin-bottom:10px">' +
       'الفلترة مطفية الآن — موعد تشغيلها ' + he(CFG.licence_filter_due || '') +
       '. لين ذاك الوقت ما نخفي أي شقة.</div>';
  var nexp = (ex.expired || []).length, nsoon = (ex.expiring || []).length;
  if(nexp || nsoon){
    h += '<div class="ovwarn">' + (nexp ? nexp + ' ترخيص منتهي. ' : '') +
         (nsoon ? nsoon + ' ينتهي خلال ' + CFG.licence_warn_days + ' يوم.' : '') + '</div>';
  } else {
    h += '<div class="quality">ما فيه تراخيص منتهية أو قريبة الانتهاء.</div>';
  }
  h += '<div class="ovbox" style="margin-top:12px">';
  h += '<input type="text" id="licno" placeholder="رقم الترخيص" style="min-width:180px">';
  h += '<input type="text" id="licexp" placeholder="ينتهي YYYY-MM-DD" style="min-width:170px">';
  h += '<button class="btn primary" id="savelic">احفظ للشقة المختارة</button>';
  h += '</div>';
  if(!LID) h += '<div class="muted" style="font-size:12.5px;margin-top:8px">اختر شقة أول من فوق.</div>';
  h += '</div>';
  v.innerHTML = h;
}

function loadCfg(){
  CFG = null; render();
  api('/api/mrent/settings').then(function(d){
    if(!d.ok){ toast(d.message || 'ما قدرنا نجيب الإعدادات'); return; }
    CFG = d; render();
  });
}

/* ================= wiring ================= */
function render(){
  var tabs = document.querySelectorAll('.tab');
  for(var i = 0; i < tabs.length; i++){
    tabs[i].classList.toggle('on', tabs[i].getAttribute('data-tab') === TAB);
  }
  if(TAB === 'list') viewList();
  else if(TAB === 'unit') viewUnit();
  else if(TAB === 'admin') viewAdmin();
  else viewAttrs();
}
function loadUnits(force){
  UNITS = null; render();
  api('/api/mrent/units?month=' + encodeURIComponent(MONTH) + (force ? '&refresh=1' : ''))
    .then(function(d){
      if(!d.ok){ toast(d.message || 'ما قدرنا نجيب البيانات'); return; }
      UNITS = d;
      var sel = $('unit');
      var html = '<option value="">— اختر شقة —</option>';
      for(var i = 0; i < d.rows.length; i++){
        html += '<option value="' + he(d.rows[i].lid) + '">' + he(d.rows[i].name || d.rows[i].lid) + '</option>';
      }
      sel.innerHTML = html;
      if(LID) sel.value = LID;
      var src = d.turnover_cost_source || '';
      var el = $('stamp');
      if(src.indexOf('DEFAULT') === 0){
        el.className = 'costwarn';
        el.textContent = 'تكلفة التنظيف رقم مبدئي (140 ريال) — الأسعار كلها مبنية عليه. ' +
                         'حدّثه من صفحة تغطية التنظيف.';
      } else {
        el.className = 'muted';
        el.textContent = 'تكلفة التنظيف: من إعدادات المالك';
      }
      render();
    });
}
function loadPrice(){
  PRICE = null; render();
  api('/api/mrent/price?lid=' + encodeURIComponent(LID) + '&month=' + encodeURIComponent(MONTH))
    .then(function(d){
      if(!d.ok){ toast(d.message || 'ما قدرنا نحسب'); return; }
      PRICE = d.price; render();
    });
}
function loadAttrs(){
  ATTRS = null; render();
  api('/api/mrent/attrs?lid=' + encodeURIComponent(LID)).then(function(d){
    if(!d.ok){ toast(d.message || 'ما قدرنا نجيب المواصفات'); return; }
    ATTRS = d; render();
  });
}

document.addEventListener('click', function(e){
  var t = e.target;
  var tab = t.closest ? t.closest('.tab') : null;
  if(tab){
    TAB = tab.getAttribute('data-tab');
    if(TAB === 'unit' && LID && !PRICE) loadPrice();
    else if(TAB === 'attrs' && LID && !ATTRS) loadAttrs();
    else if(TAB === 'admin' && !CFG) loadCfg();
    else render();
    return;
  }
  var row = t.closest ? t.closest('[data-lid]') : null;
  if(row){
    LID = row.getAttribute('data-lid');
    $('unit').value = LID;
    TAB = 'unit'; PRICE = null; ATTRS = null;
    loadPrice();
    return;
  }
  var sv = t.getAttribute ? t.getAttribute('data-save') : null;
  if(sv){
    var inp = document.querySelector('[data-input="' + sv + '"]');
    var val = inp ? inp.value : '';
    api('/api/mrent/attrs', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({lid: parseInt(LID, 10), key: sv,
                            value: (val === '' ? null : val), month: MONTH})
    }).then(function(d){
      if(!d.ok){ toast(d.message || 'ما انحفظت'); return; }
      toast('انحفظت');
      ATTRS = null; PRICE = null; loadAttrs();
    });
    return;
  }
  if(t.id === 'refresh'){ PRICE = null; loadUnits(true); if(LID) loadPrice(); return; }
  var src = t.getAttribute ? t.getAttribute('data-src') : null;
  if(src){
    var body = {price_source: src};
    if(t.getAttribute('data-needs-override')){
      var rs = (($('ovreason') || {}).value || '').trim();
      if(!rs){ toast('اكتب سبب التجاوز'); return; }
      body.override = true; body.reason = rs;
    }
    api('/api/mrent/settings', {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .then(function(d){
        if(!d.ok){ toast(d.message || 'مرفوض'); return; }
        toast('انحفظ'); CFG = null; loadCfg();
      });
    return;
  }
  if(t.id === 'savetcost'){
    api('/api/mrent/settings', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({turnover_cost_sar: ($('tcost') || {}).value})})
      .then(function(d){
        if(!d.ok){ toast(d.message || 'ما انحفظ'); return; }
        toast('انحفظ — الأسعار تنحسب من جديد'); CFG = null; UNITS = null; PRICE = null;
        loadCfg();
      });
    return;
  }
  if(t.id === 'savelic'){
    if(!LID){ toast('اختر شقة أول'); return; }
    api('/api/mrent/licence', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({lid: parseInt(LID, 10),
                            licence_no: ($('licno') || {}).value,
                            expires: ($('licexp') || {}).value})})
      .then(function(d){
        if(!d.ok){ toast(d.message || 'ما انحفظ'); return; }
        toast('انحفظ الترخيص'); CFG = null; loadCfg();
      });
    return;
  }
  if(t.id === 'savequote'){
    var pctv = parseInt(($('ovrnum') || {}).value, 10) || 0;
    var reason = (($('ovrreason') || {}).value || '').trim();
    if(pctv !== 0 && !reason){ toast('اكتب سبب التعديل'); return; }
    api('/api/mrent/quote', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({lid: parseInt(LID, 10), month: MONTH,
                            override_pct: pctv / 100, reason: reason})
    }).then(function(d){
      if(!d.ok){ toast(d.message || 'ما انحفظت'); return; }
      toast('انحفظت التسعيرة');
      PRICE = null; loadPrice();
    });
    return;
  }
});

$('month').addEventListener('change', function(){
  MONTH = $('month').value; UNITS = null; PRICE = null; loadUnits(false);
  if(LID && TAB === 'unit') loadPrice();
});
$('unit').addEventListener('change', function(){
  LID = $('unit').value; PRICE = null; ATTRS = null;
  if(LID){ TAB = 'unit'; loadPrice(); } else { TAB = 'list'; render(); }
});

buildMonths();
loadUnits(false);
</script>
</body>
</html>
"""
