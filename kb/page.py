# -*- coding: utf-8 -*-
"""
kb.page — the share-link page served at /kb/{token}.

Standalone and self-contained, like schedule/page.py and wifi/page.py: no login, no
dashboard shell, phone-first Arabic. The token is read back out of the URL and sent with
every call, so the page has no state to lose.

THE SAME BACKSLASH TRAP AS DASHBOARD_HTML
-----------------------------------------
These are normal triple-quoted Python strings, NOT raw. A backslash written inside the JS
is eaten by Python before the browser ever sees it, and one mangled string literal takes
the whole page down. ZERO backslashes below — real newlines, String.fromCharCode where a
newline is needed inside a JS string, and event delegation instead of quote-built inline
handlers. tests/test_kb_public.py parses this with esprima on every run.

The colour tokens are copied by value from DASHBOARD_HTML's :root rather than imported —
there is no shared stylesheet to import from — so the page reads as the same product.
Keep them in sync by hand if the design system moves.
"""

DEAD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>عوجا · قاعدة المعرفة</title>
<style>
body{margin:0;background:#F5F5F7;color:#1D1D1F;font-family:'IBM Plex Sans Arabic','SF Arabic','Segoe UI',system-ui,sans-serif;
 display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
.box{background:#fff;border:1px solid #E8E8ED;border-radius:16px;padding:34px 30px;max-width:430px;text-align:center}
h1{font-size:19px;margin:0 0 10px}
p{color:#86868B;font-size:14px;line-height:1.8;margin:0}
</style></head><body>
<div class="box">
  <h1>الرابط ما عاد يشتغل</h1>
  <p>هذا الرابط انتغيّر أو انسحب. اطلب الرابط الجديد من فيصل.</p>
</div></body></html>"""


HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>عوجا · قاعدة المعرفة</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#F5F5F7; --surface:#FFFFFF; --surface-2:#F1F1F4;
  --line:#E8E8ED; --line-strong:#DEDEE3;
  --text:#1D1D1F; --text-2:#424245; --text-3:#6E6E73; --mut:#86868B;
  --accent:#0A84FF; --accent-soft:#E9F2FF; --accent-tint:rgba(10,132,255,0.10);
  --green:#137333; --green-soft:#E7F5EC;
  --red:#C5221F;   --red-soft:#FCEAE9;
  --yellow:#9A6700; --yellow-soft:#FCF3DC;
  --r:14px; --r-sm:10px;
  --ease:cubic-bezier(0.22,0.61,0.36,1);
  --f:'IBM Plex Sans Arabic','SF Arabic','Segoe UI',system-ui,-apple-system,sans-serif;
  --mono:'Inter','SF Mono','Menlo',monospace;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--f);font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:1040px;margin:0 auto;padding:22px 18px 80px}
header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.brand{font-size:19px;font-weight:700;letter-spacing:-.01em}
.brand span{color:var(--accent)}
.tag{color:var(--mut);font-size:13px}
.counts{margin-inline-start:auto;display:flex;gap:6px;flex-wrap:wrap}
.pill{background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:12px;color:var(--mut);white-space:nowrap}
.pill b{color:var(--text);font-weight:600}
.searchbar{position:relative;margin-bottom:11px}
#q{width:100%;padding:16px 46px 16px 16px;font-family:var(--f);font-size:16px;font-weight:500;
 border:1.5px solid var(--line);border-radius:var(--r);background:var(--surface);color:var(--text);outline:none;transition:.15s}
#q::placeholder{color:var(--mut);font-weight:400}
#q:focus{border-color:var(--accent);box-shadow:0 0 0 4px var(--accent-tint)}
.searchbar .ic{position:absolute;inset-inline-end:16px;top:50%;transform:translateY(-50%);font-size:16px;color:var(--mut);pointer-events:none}
.filters{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
.chip{border:1px solid var(--line);background:var(--surface);color:var(--text-2);border-radius:999px;
 padding:6px 13px;font-size:12.5px;font-weight:600;font-family:var(--f);cursor:pointer;
 transition:transform .12s var(--ease),background .15s ease,color .15s ease,border-color .15s ease}
.chip:hover{border-color:var(--line-strong);color:var(--text)}
.chip:active{transform:scale(.97)}
.chip.on{background:var(--text);color:var(--surface);border-color:var(--text)}
.chip:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
select.chip{padding-inline-end:24px}
.meta{color:var(--mut);font-size:12.5px;margin:10px 2px}
.list{display:flex;flex-direction:column;gap:8px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);padding:13px 15px}
.card.gap{border-inline-start:3px solid var(--yellow)}
.card.conf{border-inline-start:3px solid var(--red)}
.card.saved{border-inline-start:3px solid var(--green)}
.top{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.nm{font-size:16px;font-weight:700;letter-spacing:-.01em}
.code{font-family:var(--mono);font-size:11.5px;color:var(--text-3);background:var(--surface-2);border-radius:6px;padding:2px 7px;direction:ltr}
.t{font-size:11px;font-weight:700;border-radius:5px;padding:2px 8px}
.t.warn{background:var(--yellow-soft);color:var(--yellow)}
.t.bad{background:var(--red-soft);color:var(--red)}
.t.ouja{background:var(--accent-tint);color:var(--accent)}
.acts{margin-inline-start:auto;display:flex;gap:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px 16px}
.lbl{font-size:11px;color:var(--mut);margin-bottom:2px}
.val{font-size:14px;font-weight:600}
.val.miss{color:var(--yellow);font-weight:500}
.val small{display:block;font-weight:500;font-size:11px;color:var(--mut);margin-top:1px}
.note{margin-top:10px;padding:8px 11px;border-radius:8px;font-size:12.5px;line-height:1.6}
.note.warn{background:var(--yellow-soft)}
.note.bad{background:var(--red-soft)}
.note b{color:var(--red)}
.who{font-size:11px;color:var(--mut);margin-top:9px}
.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:11px}
.form .full{grid-column:1/-1}
.form label{display:block;font-size:11px;font-weight:600;color:var(--mut);margin-bottom:4px}
.form input,.form select,.form textarea{width:100%;padding:10px 11px;border:1px solid var(--line);border-radius:9px;
 background:var(--surface);color:var(--text);font-family:var(--f);font-size:14px;outline:none}
.form input:focus,.form select:focus,.form textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-tint)}
.form textarea{min-height:66px;resize:vertical}
.fa{display:flex;gap:7px;margin-top:13px;align-items:center;flex-wrap:wrap}
.fa .sp{margin-inline-start:auto}
.btn{background:var(--accent);color:#fff;border:1px solid var(--accent);border-radius:9px;padding:9px 16px;
 font-family:var(--f);font-size:13.5px;font-weight:600;cursor:pointer;transition:transform .12s var(--ease),background .15s ease}
.btn:active{transform:scale(.97)}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.btn.ghost{background:var(--surface);color:var(--text-2);border-color:var(--line)}
.btn.ghost:hover{border-color:var(--line-strong);color:var(--text)}
.btn.red{background:var(--surface);color:var(--red);border-color:#E8C4C0}
.btn.sm{padding:6px 12px;font-size:12.5px}
.owner{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r);padding:12px 15px;margin-bottom:8px}
.owner .w{font-size:15px;font-weight:700}
.units{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}
.uc{background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:4px 11px;
 font-size:12px;font-weight:600;color:var(--text-2);cursor:pointer;font-family:var(--f)}
.uc:hover{border-color:var(--accent);color:var(--accent)}
.empty{background:var(--surface);border:1px dashed var(--line-strong);border-radius:var(--r);padding:26px 20px;text-align:center}
.empty h3{margin:0 0 6px;font-size:16px}
.empty p{margin:0 0 14px;color:var(--mut);font-size:13.5px}
.hist{font-size:12px;margin-top:10px;border-top:1px solid var(--line);padding-top:9px}
.hist .r{display:flex;justify-content:space-between;gap:9px;padding:5px 0;color:var(--text-2)}
.hist .r .w{color:var(--mut);font-family:var(--mono);white-space:nowrap;font-size:11px}
.toast{position:fixed;bottom:22px;inset-inline-start:50%;transform:translateX(50%);background:var(--text);color:#fff;
 padding:10px 18px;border-radius:10px;font-size:13.5px;z-index:50;opacity:0;transition:opacity .2s;pointer-events:none;max-width:88vw}
.toast.on{opacity:1}
.help{background:var(--accent-soft);border:1px solid var(--accent-tint);border-radius:var(--r);padding:12px 14px;margin-bottom:14px;font-size:13px;line-height:1.75;color:var(--text-2)}
.help b{color:var(--text)}
@media (max-width:600px){.wrap{padding:16px 13px 90px}#q{font-size:16px}.grid{grid-template-columns:repeat(auto-fit,minmax(115px,1fr))}}
@media (prefers-reduced-motion:reduce){*{transition:none !important}.chip:active,.btn:active{transform:none}}
</style></head><body>
<div class="wrap">
<header>
  <div>
    <div class="brand">عوجا <span>· قاعدة المعرفة</span></div>
    <div class="tag">دوّر قبل ما تسأل — وإذا ما لقيت، ضيفها بنفسك</div>
  </div>
  <div class="counts" id="counts"></div>
</header>

<div class="help">
  اكتب اسم الشقة، أو كود هوستاواي، أو اسم المالك، أو الحي — بالعربي أو الإنجليزي.
  <b>الفراغ ما ينخبى:</b> إذا معلومة ما أحد سجّلها بتشوف «غير مسجّل» بالأصفر — اضغط «تعديل» واكتبها.
  <b>والأحمر معناه تعارض</b> في كود هوستاواي، وهذا ما ينصلح من هنا.
</div>

<div class="searchbar">
  <input id="q" type="search" autocomplete="off" placeholder="ابحث باسم الشقة، الكود، اسم المالك، أو الحي…">
  <span class="ic">🔍</span>
</div>
<div class="filters" id="filters"></div>
<div class="meta" id="meta"></div>
<div id="body"><div class="empty"><p>…</p></div></div>
</div>
<div class="toast" id="toast"></div>
<script>
/* The token is the only thing that authorises this page, and it lives in the path:
   /kb/<token>. Read it once and send it with every call. */
var TOK = (function(){
  var parts = location.pathname.split('/');
  return parts[parts.length - 1] || '';
})();
var S = {data:null, q:'', owned:'all', gaps:false, district:'', editing:null, saved:{}, timer:null, busy:false};

function esc(s){return (s==null?'':String(s)).replace(/[<>&"']/g,function(c){
  return ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'})[c];});}
function el(id){return document.getElementById(id)}
function put(id,h){var e=el(id); if(e) e.innerHTML=h||''}
function arr(x){return Array.isArray(x)?x:[]}
function num(x){x=Number(x); return isFinite(x)?x:0}
function toast(m){var t=el('toast'); t.textContent=m; t.classList.add('on');
  clearTimeout(t._t); t._t=setTimeout(function(){t.classList.remove('on')},2600);}

function get(path){
  return fetch(path + (path.indexOf('?')<0?'?':'&') + 't=' + encodeURIComponent(TOK))
    .then(function(r){return r.json()});
}
function send(path, body){
  body = body || {}; body.t = TOK;
  return fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
                      body:JSON.stringify(body)}).then(function(r){return r.json()})
    .catch(function(){return {}});
}

function url(){
  var p = ['q=' + encodeURIComponent(S.q)];
  if(S.owned !== 'all') p.push('owned=' + S.owned);
  if(S.gaps) p.push('gaps=1');
  if(S.district) p.push('district=' + encodeURIComponent(S.district));
  return '/api/kbp/search?' + p.join('&');
}

function load(){
  if(S.busy) return Promise.resolve();
  S.busy = true;
  return get(url()).then(function(r){
    S.busy = false;
    if(!r || !r.ok){
      put('body','<div class="empty"><h3>' + esc(r && r.message ? r.message : 'ما قدرنا نفتح الصفحة') + '</h3></div>');
      return;
    }
    S.data = r; render();
  }).catch(function(){
    S.busy = false;
    put('body','<div class="empty"><h3>ما قدرنا نفتح الصفحة</h3><p>جرّب حدّث الصفحة.</p></div>');
  });
}

function typed(){
  S.q = el('q').value;
  clearTimeout(S.timer);
  S.timer = setTimeout(function(){ S.editing = null; load(); }, 110);
}

function filtersHtml(){
  var d = S.data || {}, c = d.counts || {};
  var h = '';
  h += '<button class="chip' + (S.owned==='all'?' on':'') + '" data-act="owned" data-v="all">الكل ' + num(c.units) + '</button>';
  h += '<button class="chip' + (S.owned==='inv'?' on':'') + '" data-act="owned" data-v="inv">المستثمرين</button>';
  h += '<button class="chip' + (S.owned==='ouja'?' on':'') + '" data-act="owned" data-v="ouja">عوجا ' + num(c.ouja_owned) + '</button>';
  h += '<button class="chip' + (S.gaps?' on':'') + '" data-act="gaps">ناقصة معلومات ' + num(c.gaps) + '</button>';
  var ds = arr(d.districts);
  h += '<select class="chip" data-act="district"><option value="">كل الأحياء</option>';
  for(var i=0;i<ds.length;i++){
    h += '<option value="' + esc(ds[i].district) + '"' + (S.district===ds[i].district?' selected':'') + '>'
       + esc(ds[i].district) + ' (' + num(ds[i].count) + ')</option>';
  }
  return h + '</select><button class="chip" data-act="new">+ أضف شقة</button>';
}

function render(){
  var d = S.data; if(!d) return;
  var c = d.counts || {};
  put('counts', '<span class="pill"><b>' + num(c.units) + '</b> وحدة</span>'
     + '<span class="pill"><b>' + num(c.owners) + '</b> مالك</span>'
     + '<span class="pill"><b>' + num(c.gaps) + '</b> ناقصة</span>');
  put('filters', filtersHtml());
  var units = arr(d.units), owners = arr(d.owners);
  put('meta', units.length + ' نتيجة' + (S.q ? (' لـ "' + esc(S.q) + '"') : ''));

  if(S.editing === '__new__'){ put('body', formHtml({})); return; }
  if(!units.length && !owners.length){ put('body', emptyHtml()); return; }

  var h = '';
  for(var i=0;i<owners.length;i++) h += ownerHtml(owners[i]);
  h += '<div class="list">';
  for(var j=0;j<units.length;j++) h += cardHtml(units[j]);
  put('body', h + '</div>');
}

function emptyHtml(){
  return '<div class="empty"><h3>ما لقينا شيء لـ "' + esc(S.q) + '"</h3>'
    + '<p>إما إنها ما انسجّلت عندنا، أو مكتوبة باسم ثاني.</p>'
    + '<button class="btn sm" data-act="new">+ أضف شقة</button> '
    + '<button class="btn ghost sm" data-act="ask">سجّل السؤال</button></div>';
}

function ownerHtml(o){
  var h = '<div class="owner"><div class="w">' + esc(o.name_ar)
        + ' <span class="code">' + num(o.unit_count) + ' شقة</span></div><div class="units">';
  var us = arr(o.units);
  for(var i=0;i<us.length;i++){
    h += '<button class="uc" data-act="find" data-v="' + esc(us[i].unit_name) + '">' + esc(us[i].unit_name) + '</button>';
  }
  return h + '</div></div>';
}

function miss(){ return '<span class="val miss">غير مسجّل</span>'; }

function fld(lbl, val, sub){
  return '<div><div class="lbl">' + esc(lbl) + '</div>'
    + (val ? ('<div class="val">' + esc(val) + (sub?('<small>' + esc(sub) + '</small>'):'') + '</div>') : miss())
    + '</div>';
}

function cleanText(u){
  if(u.cleaning_policy === 'ouja') return 'علينا';
  if(u.cleaning_policy === 'owner'){
    if(u.cleaning_monthly_sar === null || u.cleaning_monthly_sar === undefined) return null;
    return 'على المالك — ' + num(u.cleaning_monthly_sar) + ' ريال/شهر';
  }
  return null;
}

function cardHtml(u){
  if(S.editing === u.unit_id) return formHtml(u);
  var cls = 'card';
  if(u.conflicts && u.conflicts.length) cls += ' conf';
  else if(S.saved[u.unit_id]) cls += ' saved';
  else if(u.gaps && u.gaps.length) cls += ' gap';

  var h = '<div class="' + cls + '"><div class="top"><span class="nm">' + esc(u.unit_name) + '</span>';
  if(u.listing_code) h += '<span class="code">' + esc(u.listing_code) + '</span>';
  if(u.ouja_owned) h += '<span class="t ouja">شقة عوجا</span>';
  if(u.gaps && u.gaps.length) h += '<span class="t warn">ناقص: ' + esc(u.gaps.join(' · ')) + '</span>';
  if(u.conflicts && u.conflicts.length) h += '<span class="t bad">كود مكرر</span>';
  h += '<span class="acts"><button class="btn ghost sm" data-act="edit" data-id="' + esc(u.unit_id) + '">تعديل</button></span></div>';

  h += '<div class="grid">' + fld('المالك', u.owner_ar) + fld('الحي', u.district, u.district_en)
     + fld('النظافة', cleanText(u)) + fld('دورة الدفع', u.cycle_ar) + '</div>';

  if(u.note) h += '<div class="note warn">' + esc(u.note) + '</div>';
  if(u.conflicts && u.conflicts.length){
    var c = u.conflicts[0];
    var others = arr(c.with_names && c.with_names.length ? c.with_names : c["with"]).join(' + ');
    h += '<div class="note bad"><b>تعارض: </b>هذي الشقة تشارك كود هوستاواي ' + esc(c.code)
       + ' مع ' + esc(others) + '. معناها الإيراد ممكن ينزل على الشقة الغلط — لازم يتصلح من هوستاواي.</div>';
  }
  if(u.updated_by) h += '<div class="who">آخر تعديل: ' + esc(u.updated_by)
    + (u.last_reviewed ? (' · ' + esc(u.last_reviewed)) : '') + '</div>';
  return h + '</div>';
}

function opt(v, cur, label){
  return '<option value="' + esc(v) + '"' + (cur===v?' selected':'') + '>' + esc(label) + '</option>';
}

function formHtml(u){
  var isNew = !u.unit_id;
  var h = '<div class="card"><div class="top"><span class="nm">' + esc(isNew ? 'شقة جديدة' : u.unit_name) + '</span></div>'
    + '<div class="form">'
    + '<div><label>اسم الشقة</label><input id="f_unit_name" value="' + esc(u.unit_name||'') + '"></div>'
    + '<div><label>كود هوستاواي</label><input id="f_listing_code" inputmode="numeric" value="' + esc(u.listing_code||'') + '"></div>'
    + '<div><label>الحي</label><input id="f_district" value="' + esc(u.district||'') + '"></div>'
    + '<div><label>الحي بالإنجليزي</label><input id="f_district_en" value="' + esc(u.district_en||'') + '"></div>'
    + '<div><label>مين يدفع النظافة</label><select id="f_cleaning_policy">'
    + opt('', u.cleaning_policy||'', 'غير مسجّل')
    + opt('ouja', u.cleaning_policy||'', 'علينا')
    + opt('owner', u.cleaning_policy||'', 'على المالك')
    + '</select></div>'
    + '<div><label>مبلغ الاشتراك بالشهر (ريال)</label><input id="f_cleaning_monthly_sar" inputmode="decimal" value="'
    + esc(u.cleaning_monthly_sar===null||u.cleaning_monthly_sar===undefined?'':u.cleaning_monthly_sar) + '"></div>'
    + '<div><label>دورة الدفع</label><select id="f_payment_cycle">'
    + opt('', u.payment_cycle||'', 'غير مسجّل')
    + opt('monthly', u.payment_cycle||'', 'شهري')
    + opt('biweekly_quarter_month', u.payment_cycle||'', 'ربع شهري')
    + opt('quarterly', u.payment_cycle||'', 'ربع سنوي')
    + '</select></div>'
    + '<div><label>شقة عوجا؟</label><select id="f_ouja_owned">'
    + opt('0', u.ouja_owned?'1':'0', 'لا — شقة مستثمر')
    + opt('1', u.ouja_owned?'1':'0', 'نعم — شقة عوجا')
    + '</select></div>'
    + '<div class="full"><label>ملاحظة</label><textarea id="f_note">' + esc(u.note||'') + '</textarea></div>'
    + '</div><div class="fa">'
    + '<button class="btn" data-act="save" data-id="' + esc(u.unit_id||'') + '">احفظ</button>'
    + '<button class="btn ghost sm" data-act="cancel">إلغاء</button>';
  if(!isNew){
    h += '<span class="sp"></span>'
       + '<button class="btn ghost sm" data-act="hist" data-id="' + esc(u.unit_id) + '">سجل التعديلات</button>'
       + '<button class="btn red sm" data-act="del" data-id="' + esc(u.unit_id) + '">اخفِ من البحث</button>';
  }
  return h + '</div><div id="hist"></div></div>';
}

function v(id){ var e = el(id); return e ? e.value : ''; }

function save(unit_id){
  var body = {
    unit_name: v('f_unit_name'), listing_code: v('f_listing_code'),
    district: v('f_district'), district_en: v('f_district_en'),
    cleaning_policy: v('f_cleaning_policy'),
    cleaning_monthly_sar: v('f_cleaning_monthly_sar'),
    payment_cycle: v('f_payment_cycle'), ouja_owned: v('f_ouja_owned'),
    note: v('f_note')
  };
  if(unit_id && unit_id !== '__new__') body.unit_id = unit_id;
  send('/api/kbp/unit-save', body).then(function(r){
    /* The server decides. A refused enum comes back with its own Arabic reason, and a
       success toast on assumption would be a lie. */
    if(!r || !r.ok){ toast((r && r.message) || 'ما انحفظ'); return; }
    toast(r.message || 'انحفظ');
    S.saved[(r.unit && r.unit.unit_id) || unit_id] = 1;
    S.editing = null;
    load();
  });
}

function del(unit_id){
  if(!confirm('تنخفي من البحث؟ بياناتها وسجلها يظلون محفوظين.')) return;
  send('/api/kbp/unit-delete', {unit_id: unit_id}).then(function(r){
    toast((r && r.message) || 'تم');
    S.editing = null;
    load();
  });
}

function hist(unit_id){
  get('/api/kbp/unit/' + encodeURIComponent(unit_id)).then(function(r){
    var rows = (r && arr(r.audit)) || [];
    if(!rows.length){ put('hist','<div class="hist">ما فيه تعديلات بعد</div>'); return; }
    var h = '<div class="hist">';
    for(var i=0;i<rows.length;i++){
      var x = rows[i];
      h += '<div class="r"><span>' + esc(x.field + ': ' + (x.old_value===null?'فاضي':x.old_value)
         + ' ' + String.fromCharCode(8592) + ' ' + (x.new_value===null?'فاضي':x.new_value)) + '</span>'
         + '<span class="w">' + esc((x.changed_by||'') + ' · ' + String(x.changed_at||'').slice(0,16)) + '</span></div>';
    }
    put('hist', h + '</div>');
  });
}

function ask(){
  var t = prompt('وش السؤال اللي ما لقيت جوابه؟', S.q);
  if(!t) return;
  send('/api/kbp/question', {text: t}).then(function(r){ toast((r && r.message) || 'انسجّل'); });
}

/* One delegated listener for the whole page — no handler is ever built out of quotes. */
document.addEventListener('click', function(ev){
  var e = ev.target;
  while(e && e !== document && !(e.getAttribute && e.getAttribute('data-act'))) e = e.parentNode;
  if(!e || !e.getAttribute) return;
  var act = e.getAttribute('data-act'), id = e.getAttribute('data-id'), val = e.getAttribute('data-v');
  if(act === 'owned'){ S.owned = val; S.editing = null; load(); }
  else if(act === 'gaps'){ S.gaps = !S.gaps; S.editing = null; load(); }
  else if(act === 'edit'){ S.editing = id; render(); }
  else if(act === 'save') save(id);
  else if(act === 'cancel'){ S.editing = null; render(); }
  else if(act === 'del') del(id);
  else if(act === 'hist') hist(id);
  else if(act === 'new'){ S.editing = '__new__'; render(); }
  else if(act === 'ask') ask();
  else if(act === 'find'){ el('q').value = val; S.q = val; S.editing = null; load(); }
});
document.addEventListener('change', function(ev){
  var e = ev.target;
  if(e && e.getAttribute && e.getAttribute('data-act') === 'district'){
    S.district = e.value; S.editing = null; load();
  }
});
el('q').addEventListener('input', typed);
load();
</script></body></html>"""
