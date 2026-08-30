# -*- coding: utf-8 -*-
"""
onboarding.page — the standalone /onboarding page (build spec §8).

A STANDALONE page, deliberately not a section of DASHBOARD_HTML: that string is 16k+ lines and
its backslash trap has killed the dashboard login twice. A form this size does not belong in
it, so the blast radius of a mistake here is one page instead of the whole dashboard. The
dashboard's nav item redirects here, exactly as studio / ownrep / monthlylab already do.

SAME backslash trap as DASHBOARD_HTML and schedule.page: this is a normal (non-raw)
triple-quoted string, so Python eats any backslash escape BEFORE JavaScript ever sees it. This
file therefore contains ZERO backslashes — real newlines, String.fromCharCode(10) where JS
needs one, no regex literals, and event delegation instead of inline-onclick quote building.
A test asserts chr(92) is absent.
"""

ONBOARDING_PAGE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>ضم الوحدات · عوجا</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#F1EDE6; --panel:#FAF7F1; --ink:#292925; --body:#33302B; --muted:#9C958A;
    --gold:#B29A6A; --gold-soft:#F0E8D8; --maroon:#8B3748; --maroon-soft:#F3E2E4; --border:#E7DFD1;
    --green:#4A7C59; --green-soft:#E3EDE5;
    --r:16px; --r-sm:11px; --sh:0 1px 2px rgba(41,41,37,.04),0 10px 30px rgba(41,41,37,.07);
    --ease:cubic-bezier(0.23,1,0.32,1); --font:'Tajawal',-apple-system,system-ui,sans-serif;
    --num:'Inter',sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);line-height:1.55}
  body{padding:max(14px,env(safe-area-inset-top)) 14px calc(120px + env(safe-area-inset-bottom));max-width:1080px;margin:0 auto}
  .num{font-family:var(--num);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate;display:inline-block}
  h1,h2,h3{margin:0;color:var(--ink)}
  header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:16px;flex-wrap:wrap}
  .ttl{font-weight:800;font-size:22px}
  .sub{color:var(--muted);font-size:13px;margin-top:2px}
  button{font-family:var(--font)}
  .btn{border:1px solid var(--border);background:var(--panel);color:var(--body);border-radius:999px;
    padding:10px 18px;font-weight:700;font-size:14px;cursor:pointer;min-height:44px;
    transition:transform .12s var(--ease),background .15s,color .15s,border-color .15s}
  .btn:active{transform:scale(.97)}
  .btn.primary{background:var(--ink);color:#fff;border-color:var(--ink)}
  .btn.gold{background:var(--gold);color:#fff;border-color:var(--gold)}
  .btn.ghost{background:transparent}
  .btn.sm{padding:7px 13px;min-height:36px;font-size:13px}
  .btn[disabled]{opacity:.45;cursor:not-allowed}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--sh);padding:16px;margin-bottom:14px}
  .counters{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
  .ct{flex:1;min-width:120px;background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:13px 15px}
  .ct .v{font-family:var(--num);font-weight:700;font-size:25px;color:var(--ink);direction:ltr}
  .ct .k{color:var(--muted);font-size:12.5px;margin-top:1px}
  input,select,textarea{font-family:var(--font);font-size:14px;color:var(--body);background:#fff;
    border:1px solid var(--border);border-radius:var(--r-sm);padding:10px 12px;width:100%;min-height:44px}
  textarea{min-height:78px;resize:vertical;line-height:1.6}
  input:focus,select:focus,textarea:focus{outline:2px solid var(--gold);outline-offset:1px}
  label{display:block;font-weight:700;font-size:13px;color:var(--ink);margin:12px 0 5px}
  .req{color:var(--maroon);font-weight:700;font-size:12px;margin-top:4px}
  .grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0 14px}
  .plist{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
  .pcard{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--sh);
    padding:15px;cursor:pointer;transition:transform .12s var(--ease)}
  .pcard:active{transform:scale(.985)}
  .pcard .nm{font-weight:800;font-size:15.5px;color:var(--ink)}
  .pcard .mt{color:var(--muted);font-size:12.5px;margin-top:2px}
  .row{display:flex;align-items:center;justify-content:space-between;gap:10px}
  .pill{display:inline-block;border-radius:999px;padding:3px 11px;font-size:12px;font-weight:700;border:1px solid var(--border);background:#fff}
  .pill.wait{background:var(--gold-soft);border-color:var(--gold);color:#6E5C33}
  .pill.ready{background:var(--green-soft);border-color:var(--green);color:#2F5138}
  .pill.done{background:var(--ink);border-color:var(--ink);color:#fff}
  .chip{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:700;
    background:var(--gold-soft);color:#6E5C33;border:1px solid var(--gold)}
  .av{display:inline-flex;align-items:center;justify-content:center;width:27px;height:27px;border-radius:50%;
    color:#fff;font-weight:700;font-size:12.5px;margin-inline-start:-6px;border:2px solid var(--panel)}
  .ring{position:relative;width:44px;height:44px;flex:none}
  .ring svg{transform:rotate(-90deg)}
  .ring .pv{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    font-family:var(--num);font-weight:700;font-size:12px;color:var(--ink);direction:ltr}
  .gate{border-radius:var(--r);padding:16px;margin-bottom:14px;border:1px solid}
  .gate.bad{background:var(--maroon-soft);border-color:var(--maroon)}
  .gate.good{background:var(--green-soft);border-color:var(--green)}
  .gate h3{font-size:15.5px;margin-bottom:9px}
  .gate.bad h3{color:var(--maroon)}
  .gate.good h3{color:#2F5138}
  .blk{display:block;width:100%;text-align:start;background:#fff;border:1px solid var(--maroon);
    color:var(--maroon);border-radius:var(--r-sm);padding:11px 13px;margin-top:7px;font-weight:700;
    font-size:13.5px;cursor:pointer;min-height:44px;transition:transform .12s var(--ease)}
  .blk:active{transform:scale(.99)}
  .slots{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
  .slot{border:1px dashed var(--border);border-radius:var(--r);padding:14px;background:#fff;min-height:96px}
  .slot.full{border-style:solid;background:var(--panel)}
  .slot .lb{color:var(--muted);font-size:12px}
  .slot .nm{font-weight:800;font-size:15px;color:var(--ink);margin-top:4px}
  .stg{border:1px solid var(--border);border-radius:var(--r);background:var(--panel);margin-bottom:10px;overflow:hidden}
  .stg > .hd{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 15px;cursor:pointer;font-weight:800;color:var(--ink);font-size:14.5px}
  .stg > .bd{display:none;border-top:1px solid var(--border)}
  .stg.open > .bd{display:block}
  .tsk{padding:13px 15px;border-bottom:1px solid var(--border);border-inline-start:3px solid transparent;transition:border-color .15s}
  .tsk:last-child{border-bottom:none}
  .tsk.dirty{border-inline-start-color:var(--gold);background:#FFFDF8}
  .tsk .tt{font-weight:700;font-size:13.8px;color:var(--ink);line-height:1.5}
  .tsk .ctl{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-top:9px}
  .tsk select{width:auto;min-width:130px;min-height:38px;padding:6px 10px;font-size:13px}
  .res{border:1px solid var(--border);background:#fff;border-radius:999px;padding:6px 13px;font-size:12.5px;
    font-weight:700;cursor:pointer;color:var(--body);min-height:38px;transition:transform .12s var(--ease)}
  .res:active{transform:scale(.96)}
  .res.on[data-res="done"]{background:var(--green);border-color:var(--green);color:#fff}
  .res.on[data-res="na"]{background:var(--muted);border-color:var(--muted);color:#fff}
  .res.on[data-res="blocked"]{background:var(--maroon);border-color:var(--maroon);color:#fff}
  .rsn{margin-top:9px;display:none;gap:7px}
  .rsn.on{display:flex}
  .rsn input{flex:1;min-height:40px}
  .why{color:var(--muted);font-size:12px;margin-top:5px}
  .bar{position:fixed;inset-inline:0;bottom:0;background:var(--ink);color:#fff;padding:13px 16px calc(13px + env(safe-area-inset-bottom));
    display:none;align-items:center;justify-content:space-between;gap:12px;z-index:60;
    box-shadow:0 -8px 30px rgba(41,41,37,.18)}
  .bar.on{display:flex}
  .bar .tx{font-weight:700;font-size:14px}
  .toast{position:fixed;inset-inline:0;bottom:0;background:var(--green);color:#fff;padding:14px 16px calc(14px + env(safe-area-inset-bottom));
    text-align:center;font-weight:700;display:none;z-index:70}
  .toast.on{display:block}
  .steps{display:flex;gap:7px;margin-bottom:16px}
  .step{flex:1;height:5px;border-radius:99px;background:var(--border)}
  .step.on{background:var(--gold)}
  .wz{display:none}
  .wz.on{display:block}
  .log{list-style:none;margin:0;padding:0}
  .log li{padding:10px 0;border-bottom:1px solid var(--border);font-size:13px}
  .log li:last-child{border-bottom:none}
  .log .w{color:var(--muted);font-size:11.5px}
  .empty{text-align:center;color:var(--muted);padding:44px 16px}
  .empty .ic{font-size:34px}
  .hide{display:none}
  .cp{background:var(--gold-soft);border:1px solid var(--gold);border-radius:var(--r-sm);padding:11px 13px;
    font-family:var(--num);font-size:12px;direction:ltr;word-break:break-all;margin-top:7px}
  @media (prefers-reduced-motion: reduce){*{transition:none !important;animation:none !important}}
</style>
</head>
<body>
<header>
  <div>
    <h1 class="ttl">ضم الوحدات</h1>
    <div class="sub" id="sub">من أول تواصل مع العميل إلى تسليم الوحدة لفريق العمليات</div>
  </div>
  <div id="hdact"></div>
</header>

<div id="gateauth" class="card hide">
  <h3>سجّل دخولك أول</h3>
  <div class="why">افتح الصفحة من لوحة التحكم عشان يوصل رمز الدخول معك.</div>
</div>

<main id="main"></main>
<div class="bar" id="savebar"><span class="tx" id="savetx"></span><button class="btn gold sm" id="savebtn">حفظ</button></div>
<div class="toast" id="toast"></div>

<script>
var TOKEN = (function(){
  try{
    var q = location.search.substring(1).split('&');
    for (var i=0;i<q.length;i++){ var kv=q[i].split('='); if (kv[0]==='token') return decodeURIComponent(kv[1]||''); }
  }catch(e){}
  return '';
})();
var S = { view:'list', list:null, cur:null, dirty:{}, step:1, wiz:{}, openStages:{} };
var NL = String.fromCharCode(10);

function esc(s){
  return String(s==null?'':s).split('&').join('&amp;').split('<').join('&lt;')
    .split('>').join('&gt;').split('"').join('&quot;');
}
function el(id){ return document.getElementById(id); }
function sep(a){ return a.join('، '); }

function api(path, body){
  var url = path + (path.indexOf('?')>=0?'&':'?') + 'token=' + encodeURIComponent(TOKEN);
  var opt = { headers:{'Content-Type':'application/json'} };
  if (body){ opt.method='POST'; opt.body=JSON.stringify(body); }
  return fetch(url, opt).then(function(r){
    if (r.status===401 || r.status===403){ return r.json().then(function(j){ j.__auth=true; return j; }); }
    return r.json();
  }).catch(function(){ return {ok:false, error:'ما وصلنا للخادم — حدّث الصفحة'}; });
}
function authFail(j){
  if (!j || !j.__auth) return false;
  el('gateauth').classList.remove('hide');
  el('main').innerHTML = '';
  el('hdact').innerHTML = '';
  return true;
}
function toast(msg){
  var t = el('toast'); t.textContent = msg; t.classList.add('on');
  setTimeout(function(){ t.classList.remove('on'); }, 3000);
}
function ring(pct){
  var r = 18, c = 2*Math.PI*r, off = c*(1-(pct||0)/100);
  return '<div class="ring"><svg width="44" height="44"><circle cx="22" cy="22" r="18" fill="none" stroke="#E7DFD1" stroke-width="4"></circle>'
    + '<circle cx="22" cy="22" r="18" fill="none" stroke="#B29A6A" stroke-width="4" stroke-linecap="round" stroke-dasharray="'
    + c.toFixed(1) + '" stroke-dashoffset="' + off.toFixed(1) + '"></circle></svg>'
    + '<div class="pv">' + (pct||0) + '</div></div>';
}
function avatars(list){
  var h = '';
  for (var i=0;i<(list||[]).length;i++){
    var a = list[i], nm = String(a.employee_name||'?');
    h += '<span class="av" style="background:' + (a.color||'#B29A6A') + '">' + esc(nm.charAt(0)) + '</span>';
  }
  return h;
}

/* ---------------- A. the list ---------------- */
function loadList(){
  return api('/api/onb/list').then(function(j){
    if (authFail(j)) return;
    if (!j.ok){ el('main').innerHTML = '<div class="card">' + esc(j.error||'خطأ') + '</div>'; return; }
    S.list = j; S.view = 'list'; renderList('');
  });
}
function renderList(filter){
  var j = S.list, c = j.counters || {};
  el('hdact').innerHTML = '<button class="btn primary" id="newbtn">مشروع جديد</button>';
  var h = '<div class="counters">'
    + '<div class="ct"><div class="v">' + (c.active||0) + '</div><div class="k">نشِطة</div></div>'
    + '<div class="ct"><div class="v">' + (c.ready||0) + '</div><div class="k">جاهزة للنشر</div></div>'
    + '<div class="ct"><div class="v">' + (c.published||0) + '</div><div class="k">منشورة</div></div>'
    + '</div>'
    + '<div class="card" style="padding:11px 13px"><input id="q" placeholder="دوّر باسم الوحدة أو العميل أو الحي" value="' + esc(filter||'') + '"></div>';
  var rows = (j.projects||[]).filter(function(p){
    if (!filter) return true;
    var hay = [p.unit_name,p.client_name,p.district,p.ref].join(' ').toLowerCase();
    return hay.indexOf(String(filter).toLowerCase()) >= 0;
  });
  if (!rows.length){
    h += '<div class="empty"><div class="ic">🏠</div><div>ما فيه مشاريع بعد</div><div class="why">ابدأ من زر «مشروع جديد» فوق.</div></div>';
  } else {
    h += '<div class="plist">';
    for (var i=0;i<rows.length;i++){
      var p = rows[i];
      var pill = p.status==='published' ? '<span class="pill done">✅ منشورة</span>'
        : (p.status==='walked_away' ? '<span class="pill">انسحبنا</span>'
        : (p.ready ? '<span class="pill ready">🔒 جاهزة — بانتظار النشر</span>'
                   : '<span class="pill wait">⏳ قيد التجهيز</span>'));
      h += '<div class="pcard" data-open="' + p.id + '">'
        + '<div class="row"><div style="flex:1"><div class="nm">' + esc(p.unit_name||'') + '</div>'
        + '<div class="mt">' + esc(p.client_name||'') + (p.district?(' · ' + esc(p.district)):'') + '</div></div>'
        + ring(p.progress) + '</div>'
        + '<div class="row" style="margin-top:11px">' + pill
        + '<span class="num" style="color:#9C958A;font-size:11.5px">' + esc(p.ref||'') + '</span></div>'
        + '<div class="row" style="margin-top:9px"><span class="chip">' + esc(p.stage_label||'') + '</span>'
        + '<span>' + avatars(p.assignees) + '</span></div>'
        + '</div>';
    }
    h += '</div>';
  }
  el('main').innerHTML = h;
}

/* ---------------- B. the intake wizard ---------------- */
var WSTEPS = [
  {t:'العميل', f:[
    {k:'client_name', l:'اسم العميل', req:1},
    {k:'client_type', l:'نوع العميل', req:1, o:[['owner','مالك'],['tenant','مستأجر'],['prospect','مشترٍ محتمل']]},
    {k:'client_whatsapp', l:'واتساب العميل', req:1},
    {k:'client_email', l:'الإيميل (اختياري)'}
  ]},
  {t:'الوحدة', f:[
    {k:'unit_name', l:'اسم الوحدة', req:1, hint:'بيبدأ بـ Ouja | تلقائيًا، وأقل من 50 حرف'},
    {k:'district', l:'الحي', req:1},
    {k:'unit_kind', l:'نوع الوحدة', req:1, o:[['tower','برج'],['compound','مجمع'],['standalone','مستقلة']]},
    {k:'bedrooms', l:'عدد الغرف', req:1, n:1},
    {k:'furnish_state', l:'حالة التأثيث', req:1, o:[['furnished','مفروشة'],['partial','جزئية'],['unfurnished','غير مفروشة']]},
    {k:'area_sqm', l:'المساحة بالمتر (اختياري)', n:1}
  ]},
  {t:'الشروط التجارية', f:[
    {k:'strategy', l:'استراتيجية التأجير', o:[['yearly','سنوي'],['monthly','شهري'],['weekly_nightly','أسبوعي/ليلي']]},
    {k:'ouja_rate_pct', l:'نسبة عوجا ٪', n:1, hint:'القياسي 20 إلى 25'},
    {k:'cleaning_sar', l:'اشتراك النظافة بالريال', n:1, hint:'القياسي 750 إلى 1400 شهريًا'},
    {k:'contract_signed_at', l:'تاريخ توقيع العقد', d:1}
  ]},
  {t:'التسليم', f:[
    {k:'handover_target', l:'التسليم المستهدف', d:1},
    {k:'access_notes', l:'الدخول والمفاتيح', a:1},
    {k:'wifi_notes', l:'الواي فاي', a:1},
    {k:'house_rules', l:'قواعد المنزل', a:1}
  ]}
];
function openWizard(){
  S.view='wizard'; S.step=1; S.wiz={};
  el('hdact').innerHTML = '<button class="btn ghost" id="backbtn">رجوع</button>';
  renderWizard();
}
function renderWizard(){
  var h = '<div class="steps">';
  for (var i=0;i<WSTEPS.length;i++) h += '<div class="step' + (i<S.step?' on':'') + '"></div>';
  h += '</div>';
  for (var s=0;s<WSTEPS.length;s++){
    var st = WSTEPS[s];
    h += '<div class="wz' + ((s+1)===S.step?' on':'') + '" data-wz="' + (s+1) + '"><div class="card"><h3>' + esc(st.t) + '</h3><div class="grid2">';
    for (var f=0;f<st.f.length;f++){
      var fd = st.f[f], v = S.wiz[fd.k]==null?'':S.wiz[fd.k];
      h += '<div><label>' + esc(fd.l) + (fd.req?' *':'') + '</label>';
      if (fd.o){
        h += '<select data-wk="' + fd.k + '"><option value="">— اختر —</option>';
        for (var o=0;o<fd.o.length;o++)
          h += '<option value="' + fd.o[o][0] + '"' + (v===fd.o[o][0]?' selected':'') + '>' + esc(fd.o[o][1]) + '</option>';
        h += '</select>';
      } else if (fd.a){
        h += '<textarea data-wk="' + fd.k + '">' + esc(v) + '</textarea>';
      } else {
        h += '<input data-wk="' + fd.k + '" type="' + (fd.d?'date':(fd.n?'number':'text')) + '" value="' + esc(v) + '">';
      }
      if (fd.hint) h += '<div class="why">' + esc(fd.hint) + '</div>';
      h += '<div class="req hide" data-reqfor="' + fd.k + '">مطلوب</div></div>';
    }
    h += '</div></div></div>';
  }
  h += '<div class="card"><div class="row">'
    + '<div class="why">تقدر تكمل الباقي لاحقًا — بس ما ينشر إلا وكل شي مكتمل.</div>'
    + '<div style="display:flex;gap:8px">'
    + (S.step>1?'<button class="btn ghost sm" id="wprev">السابق</button>':'')
    + (S.step<WSTEPS.length?'<button class="btn primary sm" id="wnext">التالي</button>'
                           :'<button class="btn gold sm" id="wsave">افتح المشروع</button>')
    + '</div></div></div>';
  el('main').innerHTML = h;
}
function stepValid(n){
  var st = WSTEPS[n-1], ok = true;
  for (var i=0;i<st.f.length;i++){
    var fd = st.f[i];
    if (!fd.req) continue;
    var v = S.wiz[fd.k];
    var bad = (v==null || String(v).trim()==='');
    var w = document.querySelector('[data-reqfor="' + fd.k + '"]');
    if (w) w.classList.toggle('hide', !bad);
    if (bad) ok = false;
  }
  return ok;
}
function saveWizard(){
  if (!stepValid(1) || !stepValid(2)){ toast('كمّل بيانات العميل والوحدة أول'); return; }
  api('/api/onb/create', S.wiz).then(function(j){
    if (authFail(j)) return;
    if (!j.ok){
      if (j.fields){ for (var k in j.fields){ var w=document.querySelector('[data-reqfor="'+k+'"]'); if(w){ w.textContent=j.fields[k]; w.classList.remove('hide'); } } }
      toast(j.error||'ما انفتح المشروع'); return;
    }
    toast('انفتح المشروع وتولّدت ' + j.task_count + ' مهمة');
    openProject(j.project.id);
  });
}

/* ---------------- C. the project ---------------- */
function openProject(id){
  return api('/api/onb/get?id=' + encodeURIComponent(id)).then(function(j){
    if (authFail(j)) return;
    if (!j.ok){ toast(j.error||'ما لقيت المشروع'); return; }
    S.cur = j; S.view='project'; S.dirty = {};
    el('hdact').innerHTML = '<button class="btn ghost" id="backbtn">رجوع</button>';
    renderProject();
  });
}
var FIELDCARDS = [
  {t:'الشروط التجارية والعقد', f:[
    {k:'strategy', l:'الاستراتيجية', o:[['yearly','سنوي'],['monthly','شهري'],['weekly_nightly','أسبوعي/ليلي']]},
    {k:'ouja_rate_pct', l:'نسبة عوجا ٪', n:1},
    {k:'cleaning_sar', l:'اشتراك النظافة بالريال', n:1},
    {k:'contract_signed_at', l:'تاريخ توقيع العقد', d:1},
    {k:'ceo_approval', l:'اعتماد الرئيس التنفيذي', o:[['not_needed','ما يحتاج'],['pending','بانتظار'],['approved','معتمد'],['rejected','مرفوض']]},
    {k:'sublet_ok', l:'بند التأجير من الباطن', o:[['1','يسمح'],['0','ما يسمح']]}
  ]},
  {t:'الرخصة والصور', f:[
    {k:'license_no', l:'رقم الرخصة'},
    {k:'license_expiry', l:'تاريخ انتهاء الرخصة', d:1},
    {k:'photos_url', l:'رابط الصور'},
    {k:'photos_approved', l:'الصور معتمدة', o:[['0','لا'],['1','نعم']]},
    {k:'pmo_project_id', l:'ربط مشروع «تجهيز الشقق» (اختياري)'}
  ]},
  {t:'ملف التسليم — هذا اللي يمنع العمليات ترجع تسألك', f:[
    {k:'access_notes', l:'الدخول والمفاتيح', a:1},
    {k:'wifi_notes', l:'الواي فاي', a:1},
    {k:'house_rules', l:'قواعد المنزل', a:1},
    {k:'checkin_time', l:'وقت الدخول'},
    {k:'checkout_time', l:'وقت الخروج'},
    {k:'client_promises', l:'وعود قطعناها للعميل', a:1},
    {k:'client_prefs', l:'تفضيلات العميل', a:1}
  ]}
];
function renderProject(){
  var j = S.cur, p = j.project, r = j.readiness || {}, pub = (p.status==='published');
  var h = '<div class="card"><div class="row">'
    + '<div style="flex:1"><h2 style="font-size:19px">' + esc(p.unit_name||'') + '</h2>'
    + '<div class="mt sub"><span class="num">' + esc(p.ref||'') + '</span> · ' + esc(p.client_name||'')
    + (p.district?(' · ' + esc(p.district)):'') + '</div>'
    + '<div style="margin-top:8px"><span class="chip">' + esc((j.stages.filter(function(s){return s.id===p.stage;})[0]||{}).label || '') + '</span></div></div>'
    + ring(j.progress) + '</div>';
  if (!pub && j.can_publish) h += '<div style="margin-top:13px"><button class="btn gold" id="pubbtn" style="width:100%">نشر الوحدة لفريق العمليات</button></div>';
  if (!pub && !j.can_publish) h += '<div class="why" style="margin-top:11px">النشر للمالك فقط.</div>';
  h += '</div>';

  if (pub){
    h += '<div class="gate good"><h3>✅ الوحدة انسلّمت</h3>'
      + '<div>نشرها ' + esc(p.published_by||'') + ' بتاريخ <span class="num">' + esc(String(p.published_at||'').substring(0,10)) + '</span></div>'
      + '<div style="margin-top:11px"><button class="btn sm" id="copyho">نسخ ملف التسليم</button></div></div>';
  } else {
    if (r.ok){
      h += '<div class="gate good"><h3>✅ كل شي مكتمل — جاهزة للنشر</h3><div>ما فيه أي ناقص. تقدر تنشرها الحين.</div></div>';
    } else {
      h += '<div class="gate bad"><h3>ما ينفع النشر — فيه ' + ((r.blockers||[]).length) + ' ناقص</h3>';
      for (var b=0;b<(r.blockers||[]).length;b++){
        var bl = r.blockers[b];
        h += '<button class="blk" data-jump="' + esc(bl.field||'') + '" data-jstage="' + esc(bl.stage||'') + '">' + esc(bl.ar) + ' ›</button>';
      }
      h += '</div>';
    }
  }

  /* delegation strip */
  h += '<div class="card"><h3 style="font-size:15.5px;margin-bottom:11px">فريق العمليات المسؤول</h3><div class="slots" id="slots">';
  var asg = j.assignees || [];
  for (var i=0;i<2;i++){
    var a = asg[i];
    if (a){
      var lk = (j.emp_links.filter(function(x){return x.employee_name===a.employee_name;})[0]||{}).link || '';
      h += '<div class="slot full"><div class="lb">' + (i===0?'الموظف الأول (الأساسي)':'الموظف الثاني') + '</div>'
        + '<div class="nm">' + esc(a.employee_name) + '</div>'
        + (a.employee_did?'':'<div class="why">ما فيه معرّف ديسكورد — بلغه يدوي</div>')
        + '<div class="cp">' + esc(lk) + '</div>'
        + (pub?'':'<div style="margin-top:9px"><button class="btn sm ghost" data-rmemp="' + a.employee_id + '">احذف</button>'
        + ' <button class="btn sm ghost" data-copy="' + esc(lk) + '">انسخ الرابط</button></div>')
        + '</div>';
    } else {
      h += '<div class="slot"><div class="lb">' + (i===0?'الموظف الأول':'الموظف الثاني') + '</div>'
        + (pub?'<div class="why">—</div>':'<div id="pick' + i + '" style="margin-top:8px"></div>') + '</div>';
    }
  }
  h += '</div>';
  if (!pub && asg.length >= 2) h += '<div class="why" style="margin-top:11px">ما ينفع أكثر من موظفين اثنين على نفس المشروع. الحاليين: ' + esc(sep(asg.map(function(a){return a.employee_name;}))) + ' — احذف واحد قبل لا تضيف غيره.</div>';
  h += '</div>';

  /* stage accordion */
  h += '<div id="stages">' + renderStages() + '</div>';

  /* field cards */
  if (!pub){
    for (var c=0;c<FIELDCARDS.length;c++){
      var fc = FIELDCARDS[c];
      h += '<div class="card"><h3 style="font-size:15px">' + esc(fc.t) + '</h3><div class="grid2">';
      for (var f=0;f<fc.f.length;f++){
        var fd = fc.f[f], v = p[fd.k]==null?'':String(p[fd.k]);
        h += '<div><label id="lbl_' + fd.k + '">' + esc(fd.l) + '</label>';
        if (fd.o){
          h += '<select data-pk="' + fd.k + '" id="fld_' + fd.k + '"><option value="">—</option>';
          for (var o=0;o<fd.o.length;o++)
            h += '<option value="' + fd.o[o][0] + '"' + (v===fd.o[o][0]?' selected':'') + '>' + esc(fd.o[o][1]) + '</option>';
          h += '</select>';
        } else if (fd.a){
          h += '<textarea data-pk="' + fd.k + '" id="fld_' + fd.k + '">' + esc(v) + '</textarea>';
        } else {
          h += '<input data-pk="' + fd.k + '" id="fld_' + fd.k + '" type="' + (fd.d?'date':(fd.n?'number':'text')) + '" value="' + esc(v) + '">';
        }
        h += '</div>';
      }
      h += '</div></div>';
    }
  }

  /* activity log */
  h += '<div class="card"><h3 style="font-size:15px;margin-bottom:9px">سجل الحركة</h3><ul class="log">';
  var lg = j.log || [];
  if (!lg.length) h += '<li class="w">ما فيه حركة بعد</li>';
  for (var q=0;q<lg.length;q++)
    h += '<li>' + esc(lg[q].text_ar||'') + '<div class="w">' + esc(lg[q].who||'') + ' · <span class="num">' + esc(String(lg[q].at||'').substring(0,16).split('T').join(' ')) + '</span></div></li>';
  h += '</ul></div>';

  el('main').innerHTML = h;
  if (!pub && asg.length < 2) loadPickers(asg.length);
  syncBar();
}
function renderStages(){
  var j = S.cur, pub = (j.project.status==='published');
  var sc = j.stage_counts || {}, tasks = j.tasks || [], asg = j.assignees || [];
  var h = '';
  for (var s=0;s<j.stages.length;s++){
    var st = j.stages[s], cnt = sc[st.id] || {resolved:0,total:0};
    var open = S.openStages[st.id] ? ' open' : '';
    h += '<div class="stg' + open + '" data-stage="' + st.id + '"><div class="hd" data-toggle="' + st.id + '">'
      + '<span>' + esc(st.label) + '</span>'
      + '<span class="num" style="color:#9C958A;font-size:13px">' + cnt.resolved + '/' + cnt.total + '</span></div><div class="bd">';
    var rows = tasks.filter(function(t){ return t.stage===st.id; });
    for (var i=0;i<rows.length;i++){
      var t = rows[i], res = t.resolution || 'open';
      var dirty = S.dirty[t.id] !== undefined ? ' dirty' : '';
      h += '<div class="tsk' + dirty + '" data-task="' + t.id + '">'
        + '<div class="tt">' + (t.gate?'🔒 ':'') + esc(t.title_ar) + '</div>'
        + '<div class="ctl"><span class="chip">' + esc(j.owner_role_ar[t.owner_role]||t.owner_role) + '</span>';
      if (!pub){
        var sel = (S.dirty[t.id] !== undefined) ? S.dirty[t.id] : (t.assignee_id==null?'':String(t.assignee_id));
        h += '<select data-asg="' + t.id + '"><option value="">بدون</option>';
        for (var a=0;a<asg.length;a++)
          h += '<option value="' + asg[a].employee_id + '"' + (sel===String(asg[a].employee_id)?' selected':'') + '>' + esc(asg[a].employee_name) + '</option>';
        h += '</select>';
        h += '<button class="res' + (res==='done'?' on':'') + '" data-res="done" data-t="' + t.id + '">تم</button>'
          + '<button class="res' + (res==='na'?' on':'') + '" data-res="na" data-t="' + t.id + '">ما ينطبق</button>'
          + '<button class="res' + (res==='blocked'?' on':'') + '" data-res="blocked" data-t="' + t.id + '">متوقف</button>';
      } else {
        h += '<span class="pill">' + esc({open:'ما انحلّت',done:'تم',na:'ما ينطبق',blocked:'متوقف'}[res]) + '</span>'
          + (t.assignee_name?('<span class="chip">' + esc(t.assignee_name) + '</span>'):'');
      }
      h += '</div>';
      h += '<div class="rsn" id="rsn' + t.id + '"><input placeholder="اكتب السبب — بدونه ما ينحفظ" data-rin="' + t.id + '"><button class="btn sm gold" data-rok="' + t.id + '">تأكيد</button></div>';
      if (t.reason) h += '<div class="why">السبب: ' + esc(t.reason) + '</div>';
      if (t.assignee_name && !pub) h += '<div class="why">مسندة لـ ' + esc(t.assignee_name) + (t.notified_at?' · انفتح لها تكت':' · ما انفتح تكت بعد') + '</div>';
      h += '</div>';
    }
    if (!rows.length) h += '<div class="tsk why">ما فيه مهام في هالمرحلة</div>';
    h += '</div></div>';
  }
  return h;
}
function syncBar(){
  var ids = Object.keys(S.dirty), bar = el('savebar');
  if (!ids.length){ bar.classList.remove('on'); return; }
  var byEmp = {}, asg = (S.cur.assignees||[]);
  for (var i=0;i<ids.length;i++){
    var v = S.dirty[ids[i]];
    var nm = v==='' ? 'بدون' : (asg.filter(function(a){return String(a.employee_id)===v;})[0]||{}).employee_name || '؟';
    byEmp[nm] = (byEmp[nm]||0)+1;
  }
  var parts = [];
  for (var k in byEmp) parts.push('<span class="num">' + byEmp[k] + '</span> لـ ' + esc(k));
  el('savetx').innerHTML = 'حفظ التوزيع — ' + parts.join(' و');
  bar.classList.add('on');
}
function saveAssign(){
  var changes = [];
  for (var id in S.dirty) changes.push({task_id: parseInt(id,10), employee_id: S.dirty[id]===''?null:parseInt(S.dirty[id],10)});
  if (!changes.length) return;
  el('savebtn').disabled = true;
  api('/api/onb/task/assign', {project_id:S.cur.project.id, changes:changes}).then(function(j){
    el('savebtn').disabled = false;
    if (authFail(j)) return;
    if (!j.ok){ toast(j.error||'ما انحفظ التوزيع'); return; }
    S.dirty = {};
    var msgs = [];
    for (var i=0;i<(j.notified||[]).length;i++){
      var n = j.notified[i];
      msgs.push(n.reachable ? ('انفتح تكت لـ' + n.name + ' — ' + n.count + ' مهام')
                            : ('انفتح تكت بس ما فيه معرّف ديسكورد لـ' + n.name + ' — بلغه يدوي'));
    }
    toast(msgs.length ? msgs.join(' · ') : 'انحفظ التوزيع');
    openProject(S.cur.project.id);
  });
}
function resolveTask(tid, res, reason){
  api('/api/onb/task/resolve', {project_id:S.cur.project.id, task_id:tid, resolution:res, reason:reason||''})
    .then(function(j){
      if (authFail(j)) return;
      if (!j.ok){ toast(j.error||'ما انحفظ'); return; }
      openProject(S.cur.project.id);
    });
}
function saveField(k, v){
  var body = {id:S.cur.project.id}; body[k] = v;
  api('/api/onb/update', body).then(function(j){
    if (authFail(j)) return;
    if (!j.ok){ toast(j.error||'ما انحفظ'); return; }
    S.cur.project = j.project; S.cur.readiness = j.readiness; S.cur.tasks = j.tasks;
    S.cur.progress = j.progress; S.cur.stage_counts = j.stage_counts;
    renderProject();
  });
}
function loadPickers(slot){
  api('/api/onb/employees').then(function(j){
    if (!j || !j.ok) return;
    var box = el('pick' + slot); if (!box) return;
    if (!(j.employees||[]).length){ box.innerHTML = '<div class="why">' + esc(j.hint||'ما فيه موظفين') + '</div>'; return; }
    var taken = (S.cur.assignees||[]).map(function(a){ return String(a.employee_id); });
    var h = '<select id="empsel"><option value="">— اختر موظف —</option>';
    for (var i=0;i<j.employees.length;i++){
      var e = j.employees[i];
      if (taken.indexOf(String(e.id))>=0) continue;
      h += '<option value="' + e.id + '">' + esc(e.name) + ' (' + e.projects + ' مشاريع)' + (e.reachable?'':' — بدون ديسكورد') + '</option>';
    }
    h += '</select><button class="btn sm primary" id="addemp" style="margin-top:8px">أضف</button>';
    box.innerHTML = h;
  });
}
function addEmp(){
  var s = el('empsel'); if (!s || !s.value){ toast('اختر موظف'); return; }
  api('/api/onb/assignee/add', {project_id:S.cur.project.id, employee_id:parseInt(s.value,10)}).then(function(j){
    if (authFail(j)) return;
    if (!j.ok){ toast(j.error); return; }
    toast('انضاف للفريق');
    openProject(S.cur.project.id);
  });
}
function doPublish(){
  if (!confirm('تأكيد النشر؟ بعد النشر ما ينفع تعديل الوحدة.')) return;
  api('/api/onb/publish', {id:S.cur.project.id}).then(function(j){
    if (authFail(j)) return;
    if (!j.ok){
      toast(j.error || 'ما ينفع النشر');
      if (j.blockers){ S.cur.readiness = {ok:false, blockers:j.blockers}; renderProject(); }
      return;
    }
    toast('نُشرت الوحدة وانسلّمت لفريق العمليات');
    openProject(S.cur.project.id);
  });
}
function copyHandover(){
  api('/api/onb/handover?id=' + encodeURIComponent(S.cur.project.id)).then(function(j){
    if (!j.ok){ toast(j.error||'ما فيه ملف'); return; }
    copyText(j.text);
  });
}
function copyText(txt){
  try{
    if (navigator.clipboard){ navigator.clipboard.writeText(txt); toast('انتسخ'); return; }
  }catch(e){}
  var ta = document.createElement('textarea');
  ta.value = txt; document.body.appendChild(ta); ta.select();
  try{ document.execCommand('copy'); toast('انتسخ'); }catch(e){ toast('انسخه يدوي'); }
  document.body.removeChild(ta);
}
function jumpTo(field, stage){
  if (stage==='tasks'){
    for (var k in S.openStages) S.openStages[k]=false;
    var stgs = S.cur.stages;
    for (var i=0;i<stgs.length;i++) S.openStages[stgs[i].id] = true;
    el('stages').innerHTML = renderStages();
    var first = document.querySelector('.tsk');
    if (first) first.scrollIntoView({behavior:'smooth', block:'center'});
    return;
  }
  if (field==='assignees'){ var sl = el('slots'); if (sl) sl.scrollIntoView({behavior:'smooth', block:'center'}); return; }
  var t = el('fld_' + field);
  if (t){ t.scrollIntoView({behavior:'smooth', block:'center'}); setTimeout(function(){ t.focus(); }, 320); }
}

/* ---------------- one listener for everything ---------------- */
document.addEventListener('click', function(ev){
  var t = ev.target; if (!t.closest) return;
  if (t.id==='newbtn'){ openWizard(); return; }
  if (t.id==='backbtn'){ if (guardLeave()) loadList(); return; }
  if (t.id==='wnext'){ if (stepValid(S.step)){ S.step++; renderWizard(); } return; }
  if (t.id==='wprev'){ S.step--; renderWizard(); return; }
  if (t.id==='wsave'){ saveWizard(); return; }
  if (t.id==='savebtn'){ saveAssign(); return; }
  if (t.id==='pubbtn'){ doPublish(); return; }
  if (t.id==='copyho'){ copyHandover(); return; }
  if (t.id==='addemp'){ addEmp(); return; }
  var card = t.closest('.pcard');
  if (card){ openProject(card.getAttribute('data-open')); return; }
  var blk = t.closest('.blk');
  if (blk){ jumpTo(blk.getAttribute('data-jump'), blk.getAttribute('data-jstage')); return; }
  var hd = t.closest('[data-toggle]');
  if (hd){ var sid = hd.getAttribute('data-toggle'); S.openStages[sid] = !S.openStages[sid];
           hd.parentNode.classList.toggle('open'); return; }
  var cp = t.closest('[data-copy]');
  if (cp){ copyText(cp.getAttribute('data-copy')); return; }
  var rm = t.closest('[data-rmemp]');
  if (rm){
    if (!confirm('تحذف الموظف من المشروع؟ مهامه بترجع بدون مسؤول.')) return;
    api('/api/onb/assignee/remove', {project_id:S.cur.project.id, employee_id:parseInt(rm.getAttribute('data-rmemp'),10)})
      .then(function(j){ if (authFail(j)) return; if (!j.ok){ toast(j.error); return; } openProject(S.cur.project.id); });
    return;
  }
  var rb = t.closest('.res');
  if (rb){
    var tid = rb.getAttribute('data-t'), res = rb.getAttribute('data-res');
    if (res==='done'){ resolveTask(parseInt(tid,10), 'done', ''); return; }
    var box = el('rsn' + tid);
    box.classList.add('on');
    box.setAttribute('data-mode', res);
    var inp = box.querySelector('input'); if (inp) inp.focus();
    return;
  }
  var ok = t.closest('[data-rok]');
  if (ok){
    var id2 = ok.getAttribute('data-rok'), bx = el('rsn' + id2);
    var val = bx.querySelector('input').value.trim();
    if (!val){ toast('اكتب السبب — «ما ينطبق» و«متوقف» لازم لها سبب'); return; }
    resolveTask(parseInt(id2,10), bx.getAttribute('data-mode'), val);
    return;
  }
});
document.addEventListener('change', function(ev){
  var t = ev.target;
  if (t.getAttribute && t.getAttribute('data-wk')){ S.wiz[t.getAttribute('data-wk')] = t.value; return; }
  if (t.getAttribute && t.getAttribute('data-asg')){
    var tid = t.getAttribute('data-asg');
    var row = (S.cur.tasks||[]).filter(function(x){ return String(x.id)===String(tid); })[0] || {};
    var orig = row.assignee_id==null ? '' : String(row.assignee_id);
    if (t.value === orig) delete S.dirty[tid]; else S.dirty[tid] = t.value;
    var tr = t.closest('.tsk'); if (tr) tr.classList.toggle('dirty', S.dirty[tid] !== undefined);
    syncBar();
    return;
  }
  if (t.getAttribute && t.getAttribute('data-pk')){ saveField(t.getAttribute('data-pk'), t.value); return; }
});
document.addEventListener('blur', function(ev){
  var t = ev.target;
  if (t.getAttribute && t.getAttribute('data-pk') && t.tagName !== 'SELECT'){
    var k = t.getAttribute('data-pk');
    var was = S.cur.project[k]==null?'':String(S.cur.project[k]);
    if (t.value !== was) saveField(k, t.value);
  }
  if (t.getAttribute && t.getAttribute('data-q')){ }
}, true);
document.addEventListener('input', function(ev){
  var t = ev.target;
  if (t.id==='q'){ renderList(t.value); var q2=el('q'); if(q2){ q2.focus(); q2.setSelectionRange(q2.value.length,q2.value.length); } }
});
function guardLeave(){
  if (Object.keys(S.dirty).length && !confirm('فيه توزيع ما انحفظ. تطلع وتفقده؟')) return false;
  S.dirty = {}; el('savebar').classList.remove('on');
  return true;
}
window.addEventListener('beforeunload', function(e){
  if (Object.keys(S.dirty).length){ e.preventDefault(); e.returnValue = ''; }
});

loadList();
</script>
</body>
</html>"""
