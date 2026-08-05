# -*- coding: utf-8 -*-
"""
pricecheck.page — /pricecheck, «فحص الأسعار».

SAME BACKSLASH TRAP AS DASHBOARD_HTML AND schedule/page.py: HTML below is a normal
triple-quoted Python string, so Python eats any backslash escape BEFORE the browser
ever sees it. A single stray backslash-n inside a JS string literal becomes a real
newline, the string never closes, and the whole page dies silently.

RULE FOR THIS FILE: ZERO BACKSLASHES. Newlines in JS come from String.fromCharCode(10).
No regex literals with escapes. Verify after any edit:
    python3 -c "import pricecheck.page as p; assert chr(92) not in p.HTML"
"""

HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>فحص الأسعار — عوجا</title>
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
  --ease:cubic-bezier(0.23,1,0.32,1);
  --font-ar:'IBM Plex Sans Arabic',system-ui,-apple-system,sans-serif;
  --font-num:'Inter',system-ui,sans-serif;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font-ar);
  font-size:15px;line-height:1.6;padding:0 0 80px}
.wrap{max-width:1180px;margin:0 auto;padding:20px 18px 0}
h1{font-size:26px;font-weight:700;margin:0 0 4px;letter-spacing:-.3px}
.sub{color:var(--text-2);font-size:14.5px;margin:0 0 18px;max-width:70ch}
/* Numbers are LTR islands inside RTL text. Without the isolate, a minus sign lands on
   the WRONG SIDE of the amount — '900.00-' — which on a money page reads as a typo at
   best and as a positive number at worst. */
.num,td.n{font-family:var(--font-num);font-variant-numeric:tabular-nums;
  font-feature-settings:'tnum' 1;direction:ltr;unicode-bidi:isolate}
.num{display:inline-block}
td.n{text-align:right}

.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;
  padding:16px 18px;margin:0 0 16px;box-shadow:0 1px 2px rgba(23,21,15,.04)}
.card h2{font-size:16px;font-weight:700;margin:0 0 4px}
.card .hint{color:var(--mut);font-size:13px;margin:0 0 12px}

.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end}
.f{display:flex;flex-direction:column;gap:5px}
.f label{font-size:12.5px;font-weight:600;color:var(--text-2)}
input[type=date],select{font:inherit;font-family:var(--font-num);font-size:14.5px;
  padding:9px 11px;border:1px solid var(--line-strong);border-radius:10px;
  background:var(--surface);color:var(--text);min-height:42px}
select{font-family:var(--font-ar)}
.chk{display:flex;align-items:center;gap:7px;font-size:13.5px;color:var(--text-2);
  padding-bottom:10px;cursor:pointer}
.chk input{width:17px;height:17px;accent-color:var(--gold)}

.btn{font:inherit;font-size:15px;font-weight:600;border-radius:11px;padding:10px 18px;
  min-height:42px;border:1px solid var(--line-strong);background:var(--surface);
  color:var(--text);cursor:pointer;transition:transform .12s var(--ease),filter .12s var(--ease)}
.btn:active{transform:scale(.97)}
.btn.primary{background:var(--gold);border-color:var(--gold-2);color:#fff}
.btn.primary:active{filter:brightness(.94)}
.btn:disabled{opacity:.5;cursor:default;transform:none}
.btn.sm{font-size:13px;padding:7px 13px;min-height:34px}

.verdict{border-width:1px;border-style:solid;border-radius:16px;padding:20px;margin:0 0 16px}
.verdict.bad{background:var(--red-soft);border-color:var(--red-line)}
.verdict.good{background:var(--green-soft);border-color:#B6DCC6}
.verdict.idle{background:var(--surface-2);border-color:var(--line)}
.verdict .big{font-size:29px;font-weight:700;letter-spacing:-.5px;margin:0 0 6px;line-height:1.25}
.verdict .why{font-size:14.5px;color:var(--text-2);margin:0}
.verdict.bad .big{color:var(--red)} .verdict.good .big{color:var(--green)}

.stats{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
.stat{background:rgba(255,255,255,.72);border:1px solid rgba(23,21,15,.08);
  border-radius:11px;padding:9px 13px;min-width:104px}
.stat b{display:block;font-family:var(--font-num);font-size:19px;font-weight:600;
  font-variant-numeric:tabular-nums}
.stat span{font-size:12px;color:var(--mut)}

table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:right;font-size:12.5px;font-weight:600;color:var(--mut);
  padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:10px;border-bottom:1px solid var(--surface-3);vertical-align:top}
tbody tr:last-child td{border-bottom:none}
tbody tr.click{cursor:pointer;transition:background .12s var(--ease)}
tbody tr.click:hover{background:var(--surface-2)}
td.n{white-space:nowrap}
td.gap{font-weight:700}
.up{color:var(--green)} .down{color:var(--red)}
.scroll{overflow-x:auto;margin:0 -18px;padding:0 18px}

.pill{display:inline-block;font-size:11.5px;font-weight:600;padding:2px 8px;
  border-radius:999px;background:var(--surface-2);color:var(--text-2);
  border:1px solid var(--line);white-space:nowrap}
.pill.win{background:var(--gold-soft);border-color:#E3CFA0;color:var(--gold-2)}
.mono{font-family:var(--font-num);font-size:13px}
.nights{background:var(--surface-2);border-radius:10px;padding:10px 12px;margin:2px 0}
.nights .row{display:flex;justify-content:space-between;gap:14px;font-size:13px;
  padding:3px 0;border-bottom:1px dotted var(--line)}
.nights .row:last-child{border-bottom:none}
.miss{color:var(--red);font-weight:600}
.fieldsdump{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.fieldsdump span{font-size:11.5px;background:var(--surface);border:1px solid var(--line);
  border-radius:7px;padding:2px 7px;font-family:var(--font-num)}
.empty{color:var(--mut);font-size:14px;padding:14px 2px}
.err{background:var(--red-soft);border:1px solid var(--red-line);color:var(--red);
  border-radius:11px;padding:11px 14px;font-size:14px;margin:0 0 14px}
.note{background:var(--gold-soft);border:1px solid #E3CFA0;border-radius:11px;
  padding:11px 14px;font-size:13.5px;color:var(--gold-2);margin:12px 0 0}
.spin{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.4);
  border-top-color:#fff;border-radius:50%;animation:sp .7s linear infinite;margin-inline-end:7px;
  vertical-align:-2px}
@keyframes sp{to{transform:rotate(360deg)}}
.hide{display:none}
@media (max-width:640px){
  .wrap{padding:16px 14px 0} h1{font-size:22px} .verdict .big{font-size:23px}
  .controls{gap:10px} .f{flex:1 1 140px}
}
@media (prefers-reduced-motion:reduce){*{animation:none !important;transition:none !important}}
</style>
</head>
<body>
<div class="wrap">

  <h1>فحص الأسعار</h1>
  <p class="sub">التقويم هو الصحيح. هذي الصفحة تقارن كل حجز بالسعر المسجّل في تقويم هوستاواي،
     وتطلع لك الحجوزات اللي أرقامها ما تطابق التقويم. <b>ما تغيّر أي شيء — قراءة فقط.</b></p>

  <div class="card">
    <div class="controls">
      <div class="f"><label>من تاريخ</label><input type="date" id="d1"></div>
      <div class="f"><label>إلى تاريخ</label><input type="date" id="d2"></div>
      <div class="f"><label>القناة</label>
        <select id="ch">
          <option value="direct">مباشر / يدوي</option>
          <option value="airbnb">Airbnb</option>
          <option value="all">الكل</option>
        </select>
      </div>
      <div class="f"><label>الشقة</label>
        <select id="lid"><option value="">كل الشقق</option></select>
      </div>
      <label class="chk"><input type="checkbox" id="deep"> تفاصيل مالية أعمق</label>
      <label class="chk"><input type="checkbox" id="canc"> شامل الملغية</label>
      <div class="f"><button class="btn primary" id="go">افحص</button></div>
    </div>
    <p class="hint" id="hint" style="margin:12px 0 0">الفحص الأعمق يقرأ تفاصيل كل حجز على حدة —
       أبطأ، لكنه يكشف تفصيل الأسعار الكامل اللي تعتمد عليه تقارير هوستاواي.</p>
  </div>

  <div id="err" class="err hide"></div>

  <div id="verdict" class="verdict idle">
    <p class="big">اختر الفترة واضغط «افحص»</p>
    <p class="why">ابدأ بشهر أو شهرين. الحجوزات المباشرة اليدوية هي مصدر المشكلة عادة.</p>
  </div>

  <div class="card hide" id="rankCard">
    <h2>أي رقم في هوستاواي يطابق التقويم؟</h2>
    <p class="hint">ما خمّنّا. قارنّا كل رقم مالي في كل حجز بالتقويم، وهذي نسبة تطابقه.
       الرقم اللي فوق هو اللي تعتمده تقارير هوستاواي عادة — اختره لتشوف الحجوزات المخالفة.</p>
    <div class="scroll"><table id="rank"></table></div>
  </div>

  <div class="card hide" id="wrongCard">
    <h2 id="wrongTitle">الحجوزات اللي تخالف التقويم</h2>
    <p class="hint">اضغط على أي صف لتشوف ليالي التقويم وكل الأرقام المالية للحجز.
       «الفرق» = رقم هوستاواي ناقص مجموع التقويم — بالسالب يعني هوستاواي أقل من التقويم.</p>
    <div style="margin:0 0 10px"><button class="btn sm" id="csv">نزّل CSV</button></div>
    <div class="scroll"><table id="wrong"></table></div>
  </div>

  <div class="card hide" id="otherCard">
    <h2>حجوزات ما قدرنا نحكم عليها</h2>
    <p class="hint">ما نطلع فرق من بيانات ناقصة. هذي الحجوزات التقويم ما غطّى كل لياليها،
       أو الرقم المختار غير موجود فيها أصلاً.</p>
    <div class="scroll"><table id="other"></table></div>
  </div>

  <div id="metaNote" class="note hide"></div>
</div>

<script>
var DATA = null, FIELD = null, OPEN = {};

function $(id){ return document.getElementById(id); }
function fmt(n){
  if(n === null || n === undefined) return '—';
  return Number(n).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
}
function esc(s){
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function iso(d){
  var m = d.getMonth()+1, day = d.getDate();
  return d.getFullYear() + '-' + (m<10?'0':'') + m + '-' + (day<10?'0':'') + day;
}
function qs(){
  var p = [];
  p.push('start=' + $('d1').value);
  p.push('end=' + $('d2').value);
  p.push('channel=' + $('ch').value);
  if($('lid').value) p.push('lid=' + encodeURIComponent($('lid').value));
  if($('deep').checked) p.push('deep=1');
  if($('canc').checked) p.push('cancelled=1');
  return p.join('&');
}

function showErr(msg){
  var e = $('err');
  if(!msg){ e.className = 'err hide'; return; }
  e.className = 'err'; e.textContent = msg;
}

async function run(){
  var btn = $('go');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>جاري الفحص';
  showErr('');
  try{
    var r = await fetch('/api/pricecheck/scan?' + qs(), {credentials:'same-origin'});
    var d = await r.json();
    if(!d.ok){
      showErr(d.message || d.error || 'تعذّر الفحص');
      DATA = null; render();
    } else {
      DATA = d;
      FIELD = (d.ranking && d.ranking.length) ? d.ranking[0].field : null;
      OPEN = {};
      fillListings(d.listings || []);
      render();
    }
  } catch(e){
    showErr('تعذّر الاتصال بالخادم — ' + e);
  }
  btn.disabled = false;
  btn.textContent = 'افحص';
}

function fillListings(list){
  var sel = $('lid'), cur = sel.value;
  var html = '<option value="">كل الشقق</option>';
  for(var i=0;i<list.length;i++){
    html += '<option value="' + esc(list[i][0]) + '">' + esc(list[i][1]) + '</option>';
  }
  sel.innerHTML = html;
  sel.value = cur;
}

function computeVerdict(){
  if(!DATA || !FIELD) return null;
  var ok=0, wrong=[], unknown=[], skipped=[], gap=0;
  for(var i=0;i<DATA.rows.length;i++){
    var r = DATA.rows[i];
    if(r.status === 'uncertain' || r.calendar_total === null){ skipped.push(r); continue; }
    var v = r.money[FIELD];
    if(v === undefined || v === null){ unknown.push(r); continue; }
    var g = Math.round((v - r.calendar_total)*100)/100;
    if(Math.abs(g) <= 0.5){ ok++; }
    else { var c = {}; for(var k in r) c[k]=r[k]; c.field_value=v; c.gap=g; wrong.push(c); gap+=g; }
  }
  wrong.sort(function(a,b){ return Math.abs(b.gap) - Math.abs(a.gap); });
  return {ok:ok, wrong:wrong, unknown:unknown, skipped:skipped,
          gap:Math.round(gap*100)/100};
}

function render(){
  var v = $('verdict');
  if(!DATA){
    v.className = 'verdict idle';
    v.innerHTML = '<p class="big">اختر الفترة واضغط «افحص»</p>' +
      '<p class="why">ابدأ بشهر أو شهرين.</p>';
    $('rankCard').className = 'card hide';
    $('wrongCard').className = 'card hide';
    $('otherCard').className = 'card hide';
    $('metaNote').className = 'note hide';
    return;
  }
  var res = computeVerdict();
  renderRank();
  if(!res){
    v.className = 'verdict idle';
    v.innerHTML = '<p class="big">ما لقينا أي رقم مالي في هذي الحجوزات</p>' +
      '<p class="why">جرّب «تفاصيل مالية أعمق» أو وسّع الفترة.</p>';
  } else if(res.wrong.length === 0){
    v.className = 'verdict good';
    v.innerHTML = '<p class="big">كل الحجوزات مطابقة للتقويم</p>' +
      '<p class="why">قارنّا ' + res.ok + ' حجز بالرقم «' + esc(FIELD) +
      '» وكلها تساوي مجموع ليالي التقويم.</p>' + statsHtml(res);
  } else {
    v.className = 'verdict bad';
    v.innerHTML = '<p class="big">' + res.wrong.length +
      ' حجز يختلف سعره عن التقويم</p>' +
      '<p class="why">مجموع الفرق <b class="num">' + fmt(res.gap) +
      '</b> ر.س — بالمقارنة مع الرقم «' + esc(FIELD) + '».' +
      (res.gap < 0 ? ' هوستاواي أقل من التقويم، يعني إيراد ناقص في التقارير.'
                   : ' هوستاواي أعلى من التقويم.') + '</p>' + statsHtml(res);
  }
  renderWrong(res);
  renderOther(res);
  renderMeta();
}

function statsHtml(res){
  return '<div class="stats">' +
    '<div class="stat"><b class="num">' + res.ok + '</b><span>مطابق</span></div>' +
    '<div class="stat"><b class="num">' + res.wrong.length + '</b><span>مختلف</span></div>' +
    '<div class="stat"><b class="num">' + res.unknown.length + '</b><span>الرقم غير موجود</span></div>' +
    '<div class="stat"><b class="num">' + res.skipped.length + '</b><span>تقويم ناقص</span></div>' +
    '<div class="stat"><b class="num">' + DATA.meta.compared + '</b><span>حجوزات مفحوصة</span></div>' +
    '</div>';
}

function renderRank(){
  var rk = DATA.ranking || [];
  if(!rk.length){ $('rankCard').className = 'card hide'; return; }
  $('rankCard').className = 'card';
  var h = '<thead><tr><th></th><th>الرقم في هوستاواي</th><th>نسبة التطابق</th>' +
          '<th>طابق</th><th>قورن</th></tr></thead><tbody>';
  for(var i=0;i<rk.length;i++){
    var f = rk[i];
    h += '<tr class="click" data-field="' + esc(f.field) + '">' +
      '<td><input type="radio" name="fld" ' + (f.field===FIELD?'checked':'') +
        ' data-field="' + esc(f.field) + '" style="accent-color:var(--gold)"></td>' +
      '<td class="mono">' + esc(f.field) +
        (i===0 && f.compared>0 ? ' <span class="pill win">الأقرب للتقويم</span>' : '') + '</td>' +
      '<td class="n">' + f.rate + '%</td>' +
      '<td class="n">' + f.agrees + '</td>' +
      '<td class="n">' + f.compared + '</td></tr>';
  }
  $('rank').innerHTML = h + '</tbody>';
}

function rowKey(r){ return String(r.id); }

function renderWrong(res){
  if(!res || !res.wrong.length){ $('wrongCard').className = 'card hide'; return; }
  $('wrongCard').className = 'card';
  $('wrongTitle').textContent = 'الحجوزات اللي تخالف التقويم (' + res.wrong.length + ')';
  var h = '<thead><tr><th>الضيف</th><th>الشقة</th><th>الدخول</th><th>الخروج</th>' +
          '<th>ليالي</th><th>التقويم</th><th>' + esc(FIELD) + '</th><th>الفرق</th>' +
          '<th>القناة</th></tr></thead><tbody>';
  for(var i=0;i<res.wrong.length;i++){
    var r = res.wrong[i], k = rowKey(r);
    h += '<tr class="click" data-row="' + esc(k) + '">' +
      '<td>' + esc(r.guest || '—') + '</td>' +
      '<td>' + esc(r.listing) + '</td>' +
      '<td class="n">' + esc(r.checkin) + '</td>' +
      '<td class="n">' + esc(r.checkout) + '</td>' +
      '<td class="n">' + r.nights_expected + '</td>' +
      '<td class="n">' + fmt(r.calendar_total) + '</td>' +
      '<td class="n">' + fmt(r.field_value) + '</td>' +
      '<td class="n gap ' + (r.gap<0?'down':'up') + '">' + (r.gap>0?'+':'') + fmt(r.gap) + '</td>' +
      '<td><span class="pill">' + esc(r.channel || 'مباشر') + '</span></td></tr>';
    if(OPEN[k]) h += '<tr><td colspan="9">' + detailHtml(r) + '</td></tr>';
  }
  $('wrong').innerHTML = h + '</tbody>';
}

function detailHtml(r){
  var h = '<div class="nights"><div class="row"><b>ليالي التقويم</b><span><b class="num">' +
          fmt(r.calendar_total !== null ? r.calendar_total : r.calendar_partial) +
          '</b> ر.س</span></div>';
  for(var i=0;i<r.nights.length;i++){
    var n = r.nights[i];
    h += '<div class="row"><span class="num">' + esc(n.date) + '</span>' +
         (n.matched ? '<span class="num">' + fmt(n.price) + '</span>'
                    : '<span class="miss">ما فيه ليلة مسجّلة لهذا الحجز</span>') + '</div>';
  }
  h += '</div><div style="font-size:12.5px;color:var(--mut);margin-top:8px">' +
       'كل الأرقام المالية اللي يرسلها هوستاواي لهذا الحجز — رقم الحجز ' +
       '<span class="mono">' + esc(r.id) + '</span></div><div class="fieldsdump">';
  var keys = Object.keys(r.money).sort();
  if(!keys.length) h += '<span>ما فيه أرقام مالية في هذا الحجز</span>';
  for(var j=0;j<keys.length;j++){
    h += '<span>' + esc(keys[j]) + ' = ' + fmt(r.money[keys[j]]) + '</span>';
  }
  return h + '</div>';
}

function renderOther(res){
  if(!res || (!res.unknown.length && !res.skipped.length)){
    $('otherCard').className = 'card hide'; return;
  }
  $('otherCard').className = 'card';
  var all = [];
  for(var i=0;i<res.unknown.length;i++) all.push(['الرقم غير موجود في الحجز', res.unknown[i]]);
  for(var j=0;j<res.skipped.length;j++) all.push(['التقويم ما غطّى كل الليالي', res.skipped[j]]);
  var h = '<thead><tr><th>السبب</th><th>الضيف</th><th>الشقة</th><th>الدخول</th>' +
          '<th>ليالي</th><th>ليالي موجودة</th></tr></thead><tbody>';
  for(var k=0;k<all.length;k++){
    var r = all[k][1];
    h += '<tr class="click" data-row="' + esc(rowKey(r)) + '">' +
      '<td><span class="pill">' + all[k][0] + '</span></td>' +
      '<td>' + esc(r.guest || '—') + '</td>' +
      '<td>' + esc(r.listing) + '</td>' +
      '<td class="n">' + esc(r.checkin) + '</td>' +
      '<td class="n">' + r.nights_expected + '</td>' +
      '<td class="n' + (r.nights_matched < r.nights_expected ? ' down' : '') + '">' +
        r.nights_matched + '</td></tr>';
    if(OPEN[rowKey(r)]) h += '<tr><td colspan="6">' + detailHtml(r) + '</td></tr>';
  }
  $('other').innerHTML = h + '</tbody>';
}

function renderMeta(){
  var m = DATA.meta, bits = [];
  bits.push('قرأنا ' + m.fetched + ' حجز من هوستاواي، وقارنّا ' + m.compared +
            ' منها عبر ' + m.listings_scanned + ' شقة.');
  if(m.deep) bits.push('الفحص العميق قرأ ' + m.deep_fetched + ' حجز بالتفصيل' +
                       (m.deep_capped ? ' (وصلنا الحد الأقصى — قسّم الفترة)' : '') + '.');
  if(m.calendar_errors && m.calendar_errors.length)
    bits.push('تعذّر قراءة تقويم ' + m.calendar_errors.length + ' شقة.');
  var odd = m.unrecognised_statuses || {}, oddKeys = Object.keys(odd);
  if(oddKeys.length){
    var parts = [];
    for(var i=0;i<oddKeys.length;i++) parts.push(oddKeys[i] + ' (' + odd[oddKeys[i]] + ')');
    bits.push('حالات حجز غير معروفة تم إبقاؤها في الفحص: ' + parts.join('، ') + '.');
  }
  bits.push('هذي الصفحة قراءة فقط — ما عدّلت أي سعر.');
  $('metaNote').className = 'note';
  $('metaNote').textContent = bits.join(' ');
}

function downloadCsv(){
  var res = computeVerdict();
  if(!res) return;
  var NL = String.fromCharCode(10), out = [];
  out.push(['reservation_id','guest','listing','checkin','checkout','nights',
            'calendar_total', FIELD, 'gap','channel'].join(','));
  function cell(x){
    var s = String(x === null || x === undefined ? '' : x);
    return (s.indexOf(',') >= 0 || s.indexOf('"') >= 0)
      ? '"' + s.split('"').join('""') + '"' : s;
  }
  for(var i=0;i<res.wrong.length;i++){
    var r = res.wrong[i];
    out.push([r.id, r.guest, r.listing, r.checkin, r.checkout, r.nights_expected,
              r.calendar_total, r.field_value, r.gap, r.channel].map(cell).join(','));
  }
  var blob = new Blob([String.fromCharCode(65279) + out.join(NL)],
                      {type:'text/csv;charset=utf-8'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'pricecheck-' + $('d1').value + '-to-' + $('d2').value + '.csv';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

document.addEventListener('click', function(ev){
  var t = ev.target;
  if(!t || !t.closest) return;
  if(t.closest('#go')){ run(); return; }
  if(t.closest('#csv')){ downloadCsv(); return; }
  var fEl = t.closest('[data-field]');
  if(fEl){ FIELD = fEl.getAttribute('data-field'); render(); return; }
  var rEl = t.closest('[data-row]');
  if(rEl){
    var k = rEl.getAttribute('data-row');
    OPEN[k] = !OPEN[k];
    render();
  }
});

(function init(){
  var today = new Date();
  var from = new Date(today.getTime() - 60*86400000);
  var to = new Date(today.getTime() + 30*86400000);
  $('d1').value = iso(from);
  $('d2').value = iso(to);
})();
</script>
</body>
</html>
"""
