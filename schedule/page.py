# -*- coding: utf-8 -*-
"""
schedule.page — the standalone /team-calendar page (build spec §6). Mobile-first, Arabic RTL,
OUJA palette. Two views: «اليوم» (cards + day selector + detail sheet) and «التقويم الأسبوعي»
(matrix). Read-only here; editing lives in the dashboard «التوزيع اليومي» tab (richer surface).
Auth = existing multi-user token (?token=...).

SAME backslash trap as DASHBOARD_HTML: normal triple-quoted string, so it contains NO
backslashes (real newlines + event delegation, no inline-onclick quote building, no regex).
"""

SCHEDULE_PAGE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>تقويم موظفي عوجا</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#F1EDE6; --panel:#FAF7F1; --ink:#292925; --body:#33302B; --muted:#9C958A;
    --gold:#B29A6A; --gold-soft:#F0E8D8; --maroon:#8B3748; --maroon-soft:#F3E2E4; --border:#E7DFD1;
    --r:16px; --r-sm:11px; --sh:0 1px 2px rgba(41,41,37,.04),0 10px 30px rgba(41,41,37,.07);
    --ease:cubic-bezier(0.23,1,0.32,1); --font:'Tajawal',-apple-system,system-ui,sans-serif;
    --num:'Inter',sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);line-height:1.55}
  body{padding:max(14px,env(safe-area-inset-top)) 14px calc(30px + env(safe-area-inset-bottom))}
  .num{font-family:var(--num);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate;display:inline-block}
  header{margin-bottom:14px}
  .ttl{font-weight:800;font-size:21px;color:var(--ink);letter-spacing:-.01em}
  .sub{color:var(--muted);font-size:13px;margin-top:2px}
  .tabs{display:flex;gap:8px;margin:14px 0}
  .tab{flex:1;border:1px solid var(--border);background:var(--panel);color:var(--body);border-radius:999px;
    padding:10px;font-family:var(--font);font-weight:700;font-size:14px;cursor:pointer;min-height:44px;
    transition:transform .12s var(--ease),background .15s,color .15s,border-color .15s}
  .tab[aria-selected="true"]{background:var(--ink);color:#fff;border-color:var(--ink)}
  .tab:active{transform:scale(.97)}
  .days{display:flex;gap:6px;overflow-x:auto;padding-bottom:6px;margin-bottom:14px;-webkit-overflow-scrolling:touch}
  .day{flex:none;border:1px solid var(--border);background:var(--panel);border-radius:999px;padding:8px 14px;
    font-weight:700;font-size:13.5px;cursor:pointer;color:var(--body);min-height:40px;transition:transform .12s var(--ease),background .15s,color .15s}
  .day[aria-selected="true"]{background:var(--gold);color:#fff;border-color:var(--gold)}
  .day:active{transform:scale(.96)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
  .ecard{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--sh);
    padding:14px;cursor:pointer;border-inline-start:4px solid var(--c,var(--gold));
    transition:transform .12s var(--ease)}
  .ecard:active{transform:scale(.98)}
  .ecard .nm{font-weight:800;font-size:16px;color:var(--ink)}
  .ecard .lo{font-family:var(--num);font-variant-numeric:tabular-nums;font-weight:700;font-size:26px;color:var(--ink);margin-top:6px;direction:ltr}
  .ecard .meta{color:var(--muted);font-size:12.5px;margin-top:2px}
  .ecard.offc{background:var(--maroon-soft);border-inline-start-color:var(--maroon)}
  .ecard.offc .tag{color:var(--maroon);font-weight:700;font-size:14px;margin-top:6px}
  /* weekly matrix */
  .mwrap{overflow-x:auto;border:1px solid var(--border);border-radius:var(--r);background:var(--panel);box-shadow:var(--sh)}
  table{border-collapse:collapse;width:100%;min-width:480px}
  th,td{padding:9px 8px;text-align:center;font-size:13px;border-bottom:1px solid var(--border)}
  th{font-weight:700;color:#fff;font-size:12.5px}
  td.dname{font-weight:700;color:var(--ink);background:var(--panel);white-space:nowrap}
  tr.today td.dname{color:var(--gold)}
  tr.today td{background:var(--gold-soft)}
  td.cell{cursor:pointer}
  td .v{font-family:var(--num);font-weight:700;font-size:16px;direction:ltr}
  td .bk{color:var(--muted);font-size:10.5px}
  td.off .v{color:var(--maroon);font-family:var(--font);font-size:12.5px}
  /* detail sheet */
  .scrim{position:fixed;inset:0;background:rgba(41,41,37,.42);opacity:0;pointer-events:none;transition:.25s;z-index:40}
  .scrim.show{opacity:1;pointer-events:auto}
  .sheet{position:fixed;left:0;right:0;bottom:0;background:var(--panel);border-radius:20px 20px 0 0;
    box-shadow:0 -10px 40px rgba(41,41,37,.18);z-index:41;transform:translateY(102%);transition:transform .3s var(--ease);
    max-height:82vh;overflow-y:auto;padding:18px 16px calc(22px + env(safe-area-inset-bottom))}
  .sheet.show{transform:translateY(0)}
  .sheeth{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
  .sheeth .nm{font-weight:800;font-size:19px;color:var(--ink)}
  .x{border:none;background:var(--bg);color:var(--body);width:34px;height:34px;border-radius:50%;font-size:18px;cursor:pointer}
  .grp{margin-top:14px}
  .grp .h{font-size:13px;color:var(--muted);font-weight:700;margin-bottom:8px;display:flex;justify-content:space-between}
  .row{display:flex;align-items:center;gap:8px;padding:8px 11px;border:1px solid var(--border);border-radius:var(--r-sm);margin-bottom:6px;background:var(--bg)}
  .row .dot{width:8px;height:8px;border-radius:50%;flex:none}
  .row.own .dot{background:var(--muted)} .row.cov .dot{background:var(--gold)}
  .row .for{margin-inline-start:auto;color:var(--gold);font-size:12px;font-weight:700}
  .row .ov{background:var(--gold);color:#fff;font-size:10px;font-weight:700;border-radius:5px;padding:1px 6px;margin-inline-start:6px}
  .big{font-family:var(--num);font-weight:800;font-size:30px;color:var(--ink);direction:ltr}
  .center{min-height:55vh;display:grid;place-items:center;color:var(--muted);text-align:center;padding:24px}
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
  @media (min-width:620px){body{max-width:680px;margin:0 auto}}
</style>
</head>
<body>
  <header><div class="ttl" id="ttl">تقويم موظفي عوجا</div><div class="sub" id="sub"></div></header>
  <div class="tabs">
    <button class="tab" id="tabToday" aria-selected="true" data-view="today">اليوم</button>
    <button class="tab" id="tabWeek" aria-selected="false" data-view="week">التقويم الأسبوعي</button>
  </div>
  <div id="root"><div class="center">…</div></div>
  <div class="scrim" id="scrim"></div>
  <div class="sheet" id="sheet"></div>
<script>
var TOK = new URLSearchParams(location.search).get('token') || localStorage.getItem('ouja_sched_tok') || '';
if (new URLSearchParams(location.search).get('token')) { localStorage.setItem('ouja_sched_tok', TOK); }
var DAYS = ['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'];
var view = 'today';
var sel = null;        // selected weekday for the Today view
var DAY = null;        // current day result
var WEEK = null;

function esc(s){ s=(s==null?'':String(s)); var m={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}; return s.replace(/[&<>"']/g,function(c){return m[c];}); }
function gdate(iso){ try{ return new Date(iso+'T00:00:00').toLocaleDateString('ar-SA',{day:'numeric',month:'long',year:'numeric'}); }catch(e){ return iso; } }

async function apiGet(path){
  var r = await fetch(path + (path.indexOf('?')>=0?'&':'?') + 'token=' + encodeURIComponent(TOK));
  if (r.status===401 || r.status===403) { return {__auth:false}; }
  return r.json();
}

async function loadDay(wd){
  var j = await apiGet('/api/schedule/day' + (wd==null?'':('?weekday='+wd)));
  if (j.__auth===false){ noauth(); return; }
  if (!j.ok){ document.getElementById('root').innerHTML='<div class="center">تعذّر التحميل</div>'; return; }
  DAY = j.day; sel = DAY.weekday;
  if (j.title){ document.getElementById('ttl').textContent=j.title; }
  document.getElementById('sub').textContent = DAY.weekday_ar + ' · ' + gdate(DAY.date);
  if (view==='today'){ renderToday(); }
}

async function loadWeek(){
  var j = await apiGet('/api/schedule/week');
  if (j.__auth===false){ noauth(); return; }
  if (j.ok){ WEEK = j.week; if (view==='week'){ renderWeek(); } }
}

function noauth(){ document.getElementById('root').innerHTML='<div class="center">افتح الصفحة من الرابط الموثوق (مع الرمز).</div>'; }

function renderToday(){
  if (!DAY){ return; }
  var h = '<div class="days">';
  for (var i=0;i<7;i++){ h += '<button class="day" data-wd="'+i+'" aria-selected="'+(i===sel)+'">'+DAYS[i]+'</button>'; }
  h += '</div><div class="grid">';
  DAY.working.slice().sort(function(a,b){return a.sort_order-b.sort_order;}).forEach(function(w){
    h += '<div class="ecard" data-emp="'+w.id+'" style="--c:'+esc(w.color||'#B29A6A')+'"><div class="nm">'+esc(w.name)+'</div><div class="lo">'+w.load+'</div><div class="meta">أصلي '+w.own.length+(w.coverage.length?(' · تغطية '+w.coverage.length):'')+'</div></div>';
  });
  DAY.off.forEach(function(o){
    h += '<div class="ecard offc" data-emp="'+o.id+'" style="--c:'+esc(o.color||'#8B3748')+'"><div class="nm">'+esc(o.name)+'</div><div class="tag">'+(o.reason==='leave'?'إجازة':'في إجازة اليوم')+'</div><div class="meta">'+o.apartments.length+' شقة يغطّيها الفريق</div></div>';
  });
  h += '</div>';
  document.getElementById('root').innerHTML = h;
}

function renderWeek(){
  if (!WEEK){ document.getElementById('root').innerHTML='<div class="center">…</div>'; loadWeek(); return; }
  var cols = WEEK.columns;
  var h = '<div class="mwrap"><table><thead><tr><th style="background:var(--ink)">اليوم</th>';
  cols.forEach(function(c){ h += '<th style="background:'+esc(c.color||'#6A3A5D')+'">'+esc(c.name)+'</th>'; });
  h += '</tr></thead><tbody>';
  WEEK.rows.forEach(function(row){
    var tr = (row.weekday===WEEK.today)?' class="today"':'';
    h += '<tr'+tr+'><td class="dname">'+DAYS[row.weekday]+'</td>';
    cols.forEach(function(c){
      var cell = row.cells[c.id] || {load:0,base:0,cov:0,off:false};
      if (cell.off){ h += '<td class="cell off" data-wd="'+row.weekday+'" data-emp="'+c.id+'"><span class="v">إجازة</span></td>'; }
      else { h += '<td class="cell" data-wd="'+row.weekday+'" data-emp="'+c.id+'"><span class="v">'+cell.load+'</span>'+(cell.cov?'<div class="bk">'+cell.base+'+'+cell.cov+'</div>':'')+'</td>'; }
    });
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  document.getElementById('root').innerHTML = h;
}

function openSheet(empId){
  if (!DAY){ return; }
  var w = DAY.working.filter(function(x){return x.id===empId;})[0];
  var o = DAY.off.filter(function(x){return x.id===empId;})[0];
  var h = '';
  if (w){
    h += '<div class="sheeth"><div class="nm">'+esc(w.name)+'</div><button class="x" data-close="1">&times;</button></div>';
    h += '<div class="big">'+w.load+'</div><div class="sub">إجمالي شقق اليوم</div>';
    h += '<div class="grp"><div class="h"><span>عقاراتك الأصلية</span><span>'+w.own.length+'</span></div>';
    w.own.forEach(function(a){ h += '<div class="row own"><span class="dot"></span>'+esc(a.name)+'</div>'; });
    h += '</div>';
    if (w.coverage.length){
      h += '<div class="grp"><div class="h"><span>تغطيات اليوم</span><span>'+w.coverage.length+'</span></div>';
      w.coverage.forEach(function(c){ h += '<div class="row cov"><span class="dot"></span>'+esc(c.apartment.name)+'<span class="for">بدل '+esc(c.owner_name||'')+'</span>'+(c.overridden?'<span class="ov">يدوي</span>':'')+'</div>'; });
      h += '</div>';
    }
  } else if (o){
    h += '<div class="sheeth"><div class="nm">'+esc(o.name)+'</div><button class="x" data-close="1">&times;</button></div>';
    h += '<div class="grp"><div class="h"><span>'+(o.reason==='leave'?'في إجازة':'في إجازة اليوم')+'</span><span>'+o.apartments.length+'</span></div>';
    o.apartments.forEach(function(a){ h += '<div class="row cov"><span class="dot"></span>'+esc(a.apartment.name)+'<span class="for">يغطّيها '+esc(a.covering_name||'—')+'</span></div>'; });
    h += '</div>';
  } else { return; }
  document.getElementById('sheet').innerHTML = h;
  document.getElementById('sheet').classList.add('show');
  document.getElementById('scrim').classList.add('show');
}
function closeSheet(){ document.getElementById('sheet').classList.remove('show'); document.getElementById('scrim').classList.remove('show'); }

function setView(v){
  view = v;
  document.getElementById('tabToday').setAttribute('aria-selected', v==='today');
  document.getElementById('tabWeek').setAttribute('aria-selected', v==='week');
  if (v==='today'){ renderToday(); } else { renderWeek(); }
}

document.addEventListener('click', function(ev){
  var t = ev.target;
  var tab = t.closest ? t.closest('.tab') : null;
  if (tab){ setView(tab.getAttribute('data-view')); return; }
  var day = t.closest ? t.closest('.day') : null;
  if (day){ loadDay(parseInt(day.getAttribute('data-wd'),10)); return; }
  if (t.closest && t.closest('[data-close]')){ closeSheet(); return; }
  if (t.id==='scrim'){ closeSheet(); return; }
  var ec = t.closest ? t.closest('.ecard') : null;
  if (ec){ openSheet(parseInt(ec.getAttribute('data-emp'),10)); return; }
  var cell = t.closest ? t.closest('.cell') : null;
  if (cell){
    var wd = parseInt(cell.getAttribute('data-wd'),10), emp = parseInt(cell.getAttribute('data-emp'),10);
    loadDay(wd).then(function(){ setView('today'); openSheet(emp); });
    return;
  }
});

if (!TOK){ noauth(); } else { loadDay(null); loadWeek(); }
</script>
</body>
</html>"""
