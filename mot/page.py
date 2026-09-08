# -*- coding: utf-8 -*-
"""
mot.page — /mot, the MANAGER view: portfolio table, per-unit history + open-round editor,
price list. Login + «mot» permission (every /api/mot/* call enforces it; the page itself
is plain HTML with no data in it).

SAME BACKSLASH TRAP AS DASHBOARD_HTML: this is a normal triple-quoted string. There are
ZERO backslashes anywhere below the docstring — real newlines, String.fromCharCode(10),
split/join instead of regex escapes, event delegation instead of inline-onclick quoting.
tests/test_mot_token_scope.py counts them. esprima-parse after any edit.
"""

HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>مطابقة وزارة السياحة — عوجا</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#F1EDE6;--panel:#FAF7F1;--ink:#292925;--body:#33302B;--muted:#9C958A;
--gold:#B29A6A;--gold-soft:#F0E8D8;--maroon:#8B3748;--maroon-soft:#F3E2E4;
--green:#4A7C59;--green-soft:#E4EFE6;--amber:#B4802F;--amber-soft:#F7EBD6;
--border:#E7DFD1;--r:16px;--r-sm:11px;
--sh:0 1px 2px rgba(41,41,37,.04),0 10px 30px rgba(41,41,37,.07);
--ease:cubic-bezier(0.23,1,0.32,1);--font:'Tajawal',system-ui,sans-serif;--num:'Inter',sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);font-size:15px;line-height:1.5}
a{color:inherit}
.top{position:sticky;top:0;z-index:5;background:rgba(241,237,230,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}
.top .in{max-width:1180px;margin:0 auto;padding:12px 18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.brand{font-weight:800;font-size:18px;color:var(--ink)}
.brand small{display:block;font-weight:400;color:var(--muted);font-size:12px}
.tabs{display:flex;gap:4px;margin-inline-start:auto;background:var(--panel);border:1px solid var(--border);border-radius:999px;padding:3px}
.tabs button{border:0;background:transparent;font:inherit;font-weight:700;padding:6px 14px;border-radius:999px;color:var(--muted);cursor:pointer;transition:all .18s var(--ease)}
.tabs button.on{background:var(--ink);color:#fff}
.wrap{max-width:1180px;margin:0 auto;padding:18px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:12px 14px;box-shadow:var(--sh)}
.kpi b{display:block;font-family:var(--num);font-size:26px;color:var(--ink);line-height:1.1}
.kpi span{font-size:12px;color:var(--muted)}
.card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--sh);overflow:hidden}
table{width:100%;border-collapse:collapse}
th{font-size:12px;color:var(--muted);font-weight:700;text-align:right;padding:10px 12px;border-bottom:1px solid var(--border);background:#F6F1E8}
td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle}
tr.row{cursor:pointer;transition:background .15s var(--ease)}
tr.row:hover{background:#F6F1E8}
.num{font-family:var(--num);font-weight:600}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700;line-height:1.5}
.pill.ok{background:var(--green-soft);color:var(--green)}
.pill.bad{background:var(--maroon-soft);color:var(--maroon)}
.pill.warn{background:var(--amber-soft);color:var(--amber)}
.pill.mute{background:#EDE7DC;color:var(--muted)}
.pill.gold{background:var(--gold-soft);color:#7d6738}
.btn{border:1px solid var(--border);background:#fff;font:inherit;font-weight:700;padding:8px 14px;border-radius:var(--r-sm);cursor:pointer;transition:transform .12s var(--ease),background .15s;color:var(--ink)}
.btn:active{transform:scale(.97)}
.btn.primary{background:var(--ink);color:#fff;border-color:var(--ink)}
.btn.gold{background:var(--gold);color:#fff;border-color:var(--gold)}
.btn.danger{background:var(--maroon-soft);color:var(--maroon);border-color:#e3c5ca}
.btn.sm{padding:5px 10px;font-size:13px}
.btn:disabled{opacity:.45;cursor:not-allowed}
.hdr{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:14px 16px;border-bottom:1px solid var(--border)}
.hdr h2{margin:0;font-size:18px;color:var(--ink)}
.hdr .sp{flex:1}
.sec{padding:0}
.sec h3{margin:0;padding:10px 16px;background:#F6F1E8;font-size:13px;color:var(--muted);border-bottom:1px solid var(--border);border-top:1px solid var(--border)}
.comp{display:grid;grid-template-columns:44px 1fr auto;gap:10px;align-items:center;padding:9px 16px;border-bottom:1px solid var(--border)}
.comp .no{font-family:var(--num);color:var(--muted);font-size:13px}
.comp .lbl b{display:block;color:var(--ink)}
.comp .lbl small{color:var(--muted);font-size:12px}
.seg{display:inline-flex;border:1px solid var(--border);border-radius:999px;overflow:hidden;background:#fff}
.seg button{border:0;background:transparent;font:inherit;font-weight:700;padding:6px 12px;cursor:pointer;color:var(--muted);transition:all .15s var(--ease)}
.seg button.av.on{background:var(--green);color:#fff}
.seg button.mi.on{background:var(--maroon);color:#fff}
.seg button.un.on{background:#D9D2C5;color:var(--ink)}
.extra{grid-column:2/4;display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:13px}
.extra input,.extra select{font:inherit;padding:5px 8px;border:1px solid var(--border);border-radius:8px;background:#fff}
.extra input.q{width:64px;font-family:var(--num)}
.extra input.n{flex:1;min-width:160px}
.hist{padding:12px 16px;display:grid;gap:8px}
.hrow{display:flex;gap:10px;align-items:center;padding:10px 12px;border:1px solid var(--border);border-radius:var(--r-sm);background:#fff;font-size:14px;flex-wrap:wrap}
.hrow .sp{flex:1}
.empty{padding:36px;text-align:center;color:var(--muted)}
.toast{position:fixed;bottom:22px;left:50%;transform:translate(-50%,20px);background:var(--ink);color:#fff;padding:10px 18px;border-radius:999px;opacity:0;transition:all .22s var(--ease);pointer-events:none;z-index:20;max-width:90vw}
.toast.show{opacity:1;transform:translate(-50%,0)}
.modal{position:fixed;inset:0;background:rgba(41,41,37,.45);display:none;align-items:center;justify-content:center;z-index:15;padding:16px}
.modal.on{display:flex}
.box{background:var(--panel);border-radius:var(--r);max-width:480px;width:100%;padding:20px;box-shadow:var(--sh)}
.box h3{margin:0 0 8px;color:var(--ink)}
.box p{margin:0 0 14px;color:var(--body)}
.box .acts{display:flex;gap:8px;justify-content:flex-start;flex-wrap:wrap}
.box textarea,.box input{width:100%;font:inherit;padding:8px;border:1px solid var(--border);border-radius:8px;margin-bottom:10px;background:#fff}
.sumbar{display:flex;gap:14px;flex-wrap:wrap;padding:12px 16px;background:#F6F1E8;border-top:1px solid var(--border);font-size:13px;align-items:center}
.sumbar b{font-family:var(--num);color:var(--ink)}
.stale{color:var(--amber);font-size:12px}
.ph{display:inline-flex;gap:4px;align-items:center}
.ph img{width:34px;height:26px;object-fit:cover;border-radius:5px;border:1px solid var(--border)}
.linkbox{display:flex;gap:8px;align-items:center;padding:10px 16px;background:var(--gold-soft);border-bottom:1px solid var(--border);font-size:13px;flex-wrap:wrap}
.linkbox code{background:#fff;padding:4px 8px;border-radius:6px;font-family:var(--num);font-size:12px;direction:ltr;max-width:100%;overflow:auto}
.meta{font-size:12px;color:var(--muted)}
@media (max-width:720px){.comp{grid-template-columns:34px 1fr}.comp .seg{grid-column:1/3}.hdr h2{font-size:16px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<div class="top"><div class="in">
  <div class="brand">مطابقة وزارة السياحة<small>سجل مؤرّخ لكل شقة مقابل ٤٧ معيارًا</small></div>
  <div class="tabs" id="tabs">
    <button data-v="portfolio" class="on">الشقق</button>
    <button data-v="prices">قائمة الأسعار</button>
    <button data-v="back">← اللوحة</button>
  </div>
</div></div>
<div class="wrap" id="app"><div class="empty">جارٍ التحميل…</div></div>
<div class="toast" id="toast"></div>
<div class="modal" id="modal"><div class="box" id="modalbox"></div></div>
<script>
var TOKEN = (function(){
  var q = location.search; if(q.charAt(0)==='?') q = q.slice(1);
  var parts = q.split('&');
  for(var i=0;i<parts.length;i++){ var kv = parts[i].split('='); if(decodeURIComponent(kv[0])==='token') return decodeURIComponent(kv[1]||''); }
  return '';
})();
var S = {view:'portfolio', lid:null, portfolio:null, unit:null, prices:null, names:{}};
var SECTIONS = [['s1','المبنى والوصول'],['s2','الوحدة العامة'],['s3','الراحة والتجهيزات'],['s4','غرفة النوم والاستديو'],['s5','دورة المياه'],['s6','المطبخ'],['s7','السلامة والاستدامة'],['s8','معايير المسبح']];
var KIND = {product:'منتج', works:'أعمال', document:'مستند', structural:'إنشائي'};
var NL = String.fromCharCode(10);

function esc(s){ return String(s===null||s===undefined?'':s).split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;').split('"').join('&quot;'); }
function qs(id){ return document.getElementById(id); }
function fmt(n){ if(n===null||n===undefined||n==='') return '—'; var x = Math.round(Number(n)); return x.toLocaleString('en-US'); }
function pct(n){ return (n===null||n===undefined) ? '—' : (Number(n).toFixed(1).replace('.0','') + '٪'); }
function day(s){ return s ? String(s).slice(0,10) : '—'; }
function toast(m){ var t = qs('toast'); t.textContent = m; t.classList.add('show'); setTimeout(function(){ t.classList.remove('show'); }, 2600); }
function api(path, body, method){
  var opt = {method: method || (body?'POST':'GET'), headers:{'Accept':'application/json','X-Token':TOKEN}};
  if(body){ opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  return fetch(path, opt).then(function(r){ return r.json(); });
}
function withTok(path){ return path + (path.indexOf('?')>=0?'&':'?') + 'token=' + encodeURIComponent(TOKEN); }
function modal(html){ qs('modalbox').innerHTML = html; qs('modal').classList.add('on'); }
function closeModal(){ qs('modal').classList.remove('on'); }

/* ---------- routing ---------- */
function nav(v, lid){
  S.view = v; S.lid = lid || null;
  var h = v==='unit' ? ('#unit=' + lid) : ('#' + v);
  if(location.hash !== h) history.replaceState(null, '', h);
  var bs = qs('tabs').querySelectorAll('button');
  for(var i=0;i<bs.length;i++){ bs[i].classList.toggle('on', bs[i].getAttribute('data-v')===(v==='unit'?'portfolio':v)); }
  render();
}
function readHash(){
  var h = location.hash.replace('#','');
  if(h.indexOf('unit=')===0) return nav('unit', h.slice(5));
  if(h==='prices') return nav('prices');
  nav('portfolio');
}
qs('tabs').addEventListener('click', function(e){
  var b = e.target.closest('button'); if(!b) return;
  var v = b.getAttribute('data-v');
  if(v==='back'){ location.href = '/dashboard?token=' + encodeURIComponent(TOKEN); return; }
  nav(v);
});
window.addEventListener('hashchange', readHash);

/* ---------- render ---------- */
function render(){
  if(S.view==='prices') return renderPrices();
  if(S.view==='unit') return renderUnit();
  renderPortfolio();
}

async function renderPortfolio(){
  var app = qs('app');
  if(!S.portfolio){ app.innerHTML = '<div class="empty">جارٍ التحميل…</div>'; var j = await api('/api/mot/portfolio'); if(!j.ok){ app.innerHTML = '<div class="empty">' + esc(j.error||'سجّل دخولك من اللوحة أولًا') + '</div>'; return; } S.portfolio = j; j.rows.forEach(function(r){ S.names[r.listing_id] = r.name; }); }
  var p = S.portfolio, s = p.summary;
  var h = '<div class="kpis">'
    + '<div class="kpi"><b>' + s.units + '</b><span>شقة نشطة</span></div>'
    + '<div class="kpi"><b style="color:var(--green)">' + s.compliant + '</b><span>مطابقة ١٠٠٪</span></div>'
    + '<div class="kpi"><b style="color:var(--maroon)">' + s.blocked + '</b><span>فيها معيار إنشائي</span></div>'
    + '<div class="kpi"><b style="color:var(--amber)">' + s.overdue + '</b><span>تجاوزت موعد إعادة الفحص</span></div>'
    + '<div class="kpi"><b>' + s.never + '</b><span>ما انفحصت أبدًا</span></div>'
    + '<div class="kpi"><b>' + fmt(s.outstanding_sar) + '</b><span>ر.س نواقص للوصول للمطابقة</span></div>'
    + '</div>';
  h += '<div class="card"><div class="hdr"><h2>الشقق</h2><span class="meta">نسخة المعايير ' + esc(p.catalogue_version) + ' · النسبتان منفصلتان عمدًا: المطابقة = متوفر ÷ ما فُحص، الفحص = ما فُحص ÷ الكل</span><div class="sp"></div><button class="btn gold sm" id="newunit">+ شقة جديدة (قيد الضم)</button></div>';
  h += '<div style="overflow:auto"><table><thead><tr><th>الشقة</th><th>آخر جولة</th><th>المطابقة</th><th>الفحص</th><th>إنشائي</th><th>نواقص (ر.س)</th><th>إعادة الفحص</th><th></th></tr></thead><tbody>';
  p.rows.forEach(function(r){
    var L = r.latest;
    h += '<tr class="row" data-lid="' + r.listing_id + '"><td><b>' + esc(r.name) + '</b>' + (r.fresh ? ' <span class="pill mute">قيد الضم</span>' : '') + (r.open ? ' <span class="pill gold">جولة مفتوحة · ' + pct(r.open.live.inspected_pct) + ' فُحص</span>' : '') + '</td>';
    if(!L){ h += '<td colspan="6" class="meta">ما انفحصت بعد</td>'; }
    else {
      var cls = r.blockers ? 'bad' : ((L.compliance_pct||0) >= 100 ? 'ok' : 'warn');
      h += '<td class="meta">' + day(L.closed_at) + ' · ' + esc(L.inspector||'') + '</td>'
        + '<td><span class="pill ' + cls + '">' + pct(L.compliance_pct) + '</span></td>'
        + '<td class="num">' + pct(L.inspected_pct) + ' <span class="meta">/' + L.denominator + '</span></td>'
        + '<td>' + (r.blockers ? '<span class="pill bad">' + r.blockers + '</span>' : '<span class="meta">—</span>') + '</td>'
        + '<td class="num">' + fmt(r.outstanding_sar) + '</td>'
        + '<td>' + (L.recheck_due ? '<span class="pill ' + (r.overdue?'warn':'mute') + '">' + day(L.recheck_due) + '</span>' : '—') + '</td>';
    }
    h += '<td><button class="btn sm">فتح</button></td></tr>';
  });
  h += '</tbody></table></div></div>';
  app.innerHTML = h;
  app.querySelector('tbody').addEventListener('click', function(e){ var tr = e.target.closest('tr[data-lid]'); if(tr) nav('unit', tr.getAttribute('data-lid')); });
  qs('newunit').onclick = newUnitForm;
}

function newUnitForm(){
  modal('<h3>شقة جديدة قيد الضم</h3><p class="meta">تنفتح كمشروع في «ضم الوحدات» وتظهر هنا فورًا. لما تدخل Hostaway، جولاتها تنتقل معها.</p>'
    + '<input id="nu_name" placeholder="اسم الشقة (يبدأ بـ Ouja | تلقائيًا)">'
    + '<input id="nu_district" placeholder="الحي">'
    + '<input id="nu_owner" placeholder="اسم المالك">'
    + '<input id="nu_phone" placeholder="جوال المالك" inputmode="tel">'
    + '<input id="nu_beds" type="number" min="0" placeholder="عدد غرف النوم (٠ = استوديو)">'
    + '<select id="nu_kind"><option value="compound">مجمع</option><option value="tower">برج</option><option value="standalone">مستقلة</option></select>'
    + '<select id="nu_furn"><option value="furnished">مؤثثة</option><option value="partial">مؤثثة جزئيًا</option><option value="unfurnished">غير مؤثثة</option></select>'
    + '<select id="nu_ctype"><option value="owner">العميل مالك</option><option value="tenant">العميل مستأجر</option><option value="prospect">عميل محتمل</option></select>'
    + '<select id="nu_pool"><option value="">المسبح: نسأل عند الفحص</option><option value="1">فيها مسبح</option></select>'
    + '<div class="acts"><button class="btn primary" id="nu_go">إضافة وفتح</button><button class="btn" id="nu_cancel">إلغاء</button></div>');
  qs('nu_cancel').onclick = closeModal;
  qs('nu_go').onclick = async function(){
    var body = {unit_name: qs('nu_name').value, district: qs('nu_district').value, client_name: qs('nu_owner').value,
                client_whatsapp: qs('nu_phone').value, bedrooms: qs('nu_beds').value, unit_kind: qs('nu_kind').value,
                furnish_state: qs('nu_furn').value, client_type: qs('nu_ctype').value};
    if(qs('nu_pool').value === '1') body.has_pool = true;
    var j = await api('/api/mot/new-unit', body);
    if(!j.ok){ toast(j.error||'خطأ'); return; }
    closeModal(); S.portfolio = null; toast('انضافت — افتح جولة الفحص'); nav('unit', j.listing_id);
  };
}

async function loadUnit(){ var j = await api('/api/mot/unit?listing_id=' + encodeURIComponent(S.lid)); if(!j.ok){ toast(j.error||'خطأ'); return null; } S.unit = j; return j; }

async function renderUnit(){
  var app = qs('app');
  app.innerHTML = '<div class="empty">جارٍ التحميل…</div>';
  var u = await loadUnit(); if(!u) return;
  var m = u.meta || {};
  var h = '<div class="card"><div class="hdr"><button class="btn sm" id="bk">→ الشقق</button><h2>' + esc(u.name) + '</h2>' + (m.fresh ? '<span class="pill mute">قيد الضم · مشروع #' + m.project_id + '</span>' : '')
    + '<span class="meta">' + (m.bedrooms!=null ? m.bedrooms + ' غرف · ' : '') + (m.bathrooms!=null ? m.bathrooms + ' حمام · ' : '') + 'المالك: ' + esc(m.owner||'—')
    + ' · المسبح: ' + (u.pool_known ? (u.has_pool ? 'نعم' : 'لا') + ' (جدول المرافق)' : '<span class="stale">غير معروف</span>')
    + ' · الإنترنت: ' + (u.wifi===true ? '<span class="pill ok">اشتراك فعّال</span>' : (u.wifi===false ? '<span class="pill bad">بدون اشتراك</span>' : '—')) + '</span>'
    + '<div class="sp"></div>';
  if(!u.open) h += '<button class="btn primary" id="openr">فتح جولة فحص</button>';
  h += '</div>';
  if(u.open){ h += renderOpenRound(u); }
  h += '<div class="sec"><h3>سجل الجولات</h3><div class="hist">';
  if(!u.rounds.length) h += '<div class="meta">ما فيه جولات بعد</div>';
  u.rounds.forEach(function(r){
    if(r.is_open) return;
    var cls = r.abandoned ? 'mute' : (r.blockers.length ? 'bad' : ((r.compliance_pct||0)>=100 ? 'ok' : 'warn'));
    h += '<div class="hrow"><span class="num">#' + r.id + '</span><span>' + day(r.closed_at) + '</span>'
      + (r.abandoned ? '<span class="pill mute">متروكة</span>' : '<span class="pill ' + cls + '">مطابقة ' + pct(r.compliance_pct) + '</span><span class="meta">فحص ' + pct(r.inspected_pct) + ' من ' + r.denominator + (r.has_pool?' (مسبح)':'') + '</span>')
      + '<span class="meta">' + esc(r.inspector||'') + '</span>'
      + (r.blockers.length ? '<span class="pill bad">' + r.blockers.length + ' إنشائي</span>' : '')
      + (r.fanout && r.fanout.quote && r.fanout.quote.number ? '<a class="pill gold" style="text-decoration:none" href="/dashboard?token=' + encodeURIComponent(TOKEN) + '#quote">عرض ' + esc(r.fanout.quote.number) + ' · ' + fmt(r.fanout.quote.total) + ' ر.س ↗</a>' : '')
      + (r.fanout && r.fanout.purchase_ticket ? '<span class="pill mute">تذكرة مشتريات</span>' : '')
      + (r.fanout && r.fanout.maint_tickets && r.fanout.maint_tickets.length ? '<span class="pill mute">' + r.fanout.maint_tickets.length + ' صيانة</span>' : '')
      + '<span class="sp"></span>'
      + (r.abandoned ? '' : (r.inspected_pct>=100 ? '<a class="btn sm" target="_blank" href="' + withTok('/api/mot/report?id=' + r.id) + '">ملف الدليل</a>' : '<span class="meta">ناقصة — ما تصلح دليلًا</span>'))
      + '</div>';
  });
  h += '</div></div></div>';
  app.innerHTML = h;
  qs('bk').onclick = function(){ S.portfolio = null; nav('portfolio'); };
  if(qs('openr')) qs('openr').onclick = function(){ openRound({}); };
  if(u.open) bindOpenRound(u);
}

function renderOpenRound(u){
  var o = u.open, res = o.results || {}, prices = o.prices || {}, photos = {};
  (o.photos||[]).forEach(function(p){ (photos[p.comp_key] = photos[p.comp_key] || []).push(p); });
  var lv = o.live;
  var h = '<div class="linkbox">جولة مفتوحة #' + o.id + ' منذ ' + day(o.opened_at) + ' · ' + o.denominator + ' مكوّن' + (o.has_pool?' (مع مسبح)':'') + ' · المفتش: ' + esc(o.inspector||'')
    + '<span class="sp" style="flex:1"></span><button class="btn sm" id="mint">رابط الفحص للجوال</button><span id="linkout"></span></div>';
  h += '<div class="sumbar"><span>فُحص <b>' + pct(lv.inspected_pct) + '</b></span><span>متوفر <b>' + lv.available + '</b></span><span>غير متوفر <b>' + lv.missing + '</b></span><span>باقي <b>' + lv.not_inspected + '</b></span>'
    + '<span class="sp" style="flex:1"></span><span>نواقص المالك <b>' + fmt(o.quote_preview.owner_total) + '</b> ر.س · مشتريات عوجا <b>' + fmt(o.quote_preview.ouja_products_total) + '</b> ر.س</span>'
    + (o.quote_preview.unpriced.length ? '<span class="stale">' + o.quote_preview.unpriced.length + ' بند بدون سعر</span>' : '')
    + (o.quote_preview.stale.length ? '<span class="stale">' + o.quote_preview.stale.length + ' سعر قديم</span>' : '')
    + '</div>';
  SECTIONS.forEach(function(sec){
    var comps = o.components.filter(function(c){ return c.section===sec[0]; });
    if(!comps.length) return;
    h += '<div class="sec"><h3>' + esc(sec[1]) + '</h3>';
    comps.forEach(function(c){
      var r = res[c.key] || {}; var st = r.state || 'unchecked';
      var pr = prices[c.key]; var ph = photos[c.key] || [];
      h += '<div class="comp" data-key="' + esc(c.key) + '"><span class="no">' + c.criterion_no + '</span>'
        + '<div class="lbl"><b>' + esc(c.label_ar) + '</b><small>' + esc(c.criterion_ar) + ' · ' + KIND[c.kind] + (c.description_ar ? '<br><span style="color:var(--muted)">' + esc(c.description_ar) + '</span>' : '') + (c.key==='c13.wifi' && r.source==='wifi' ? ' · <span class="pill ok">من اشتراكات النت</span>' : '') + (r.source==='override' ? ' · <span class="pill warn">تجاوز</span>' : '') + '</small></div>'
        + '<div class="seg"><button class="av' + (st==='available'?' on':'') + '" data-s="available">متوفر</button><button class="mi' + (st==='missing'?' on':'') + '" data-s="missing">غير متوفر</button><button class="un' + (st==='unchecked'?' on':'') + '" data-s="unchecked">لم يُفحص</button></div>';
      if(st==='missing'){
        h += '<div class="extra">';
        if(c.kind==='product' || c.kind==='works'){
          h += '<label>الكمية <input class="q" type="number" min="1" data-f="qty" value="' + (r.qty||'') + '" placeholder="تلقائي"></label>'
            + '<label>يدفعها <select data-f="billed_to"><option value=""' + (!r.billed_to?' selected':'') + '>الافتراضي (' + (c.billed_to==='owner'?'المالك':'عوجا') + ')</option><option value="owner"' + (r.billed_to==='owner'?' selected':'') + '>المالك</option><option value="ouja"' + (r.billed_to==='ouja'?' selected':'') + '>عوجا</option></select></label>'
            + '<span class="meta">السعر: ' + (pr && pr.price_sar>0 ? '<span class="num">' + fmt(pr.price_sar) + '</span> ر.س' : '<span class="stale">بدون سعر</span>') + '</span>';
        }
        if(c.kind==='structural') h += '<span class="pill bad">يوقف الوحدة — يحتاج قرار، ما يدخل العرض</span>';
        if(c.kind==='document') h += '<span class="pill mute">مهمة مستندات في «ضم الوحدات»</span>';
        h += '<input class="n" data-f="note" placeholder="ملاحظة" value="' + esc(r.note||'') + '">';
        h += '<span class="ph">' + ph.map(function(p){ return '<img src="' + withTok('/api/mot/photo/' + p.id) + '">'; }).join('') + '<label class="btn sm">📷<input type="file" accept="image/*" capture="environment" data-f="photo" hidden></label></span>';
        h += '</div>';
      } else if(ph.length){
        h += '<div class="extra"><span class="ph">' + ph.map(function(p){ return '<img src="' + withTok('/api/mot/photo/' + p.id) + '">'; }).join('') + '</span></div>';
      }
      h += '</div>';
    });
    h += '</div>';
  });
  h += '<div class="sumbar" style="flex-direction:column;align-items:stretch;gap:8px"><div class="meta">' + (lv.not_inspected ? 'كمّل الفحص أولًا — الإغلاق هو اللي يطلع عرض السعر والتذاكر' : 'الفحص مكتمل ✓ — اضغط الإغلاق ليصدر عرض السعر للمالك وتذاكر عوجا تلقائيًا') + '</div><div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center"><button class="btn gold" id="closer" style="font-size:15px;padding:10px 18px"' + (lv.not_inspected ? ' disabled' : '') + '>' + (lv.not_inspected ? 'إغلاق الجولة (باقي ' + lv.not_inspected + ')' : '🧾 إغلاق الجولة وإصدار عرض السعر') + '</button>'
    + '<label>إعادة الفحص <input type="date" id="recheck" style="font:inherit;padding:5px 8px;border:1px solid var(--border);border-radius:8px"></label>'
    + '<span class="sp" style="flex:1"></span><button class="btn danger sm" id="aband">ترك الجولة</button></div></div>';
  return h;
}

function bindOpenRound(u){
  var o = u.open;
  var app = qs('app');
  app.addEventListener('click', async function(e){
    var b = e.target.closest('.seg button'); if(!b) return;
    var comp = b.closest('.comp'); var key = comp.getAttribute('data-key');
    var j = await api('/api/mot/result', {id:o.id, comp_key:key, state:b.getAttribute('data-s')});
    if(!j.ok){
      if(key==='c13.wifi'){ var why = prompt(j.error + NL + 'اكتب السبب:'); if(why){ j = await api('/api/mot/result', {id:o.id, comp_key:key, state:b.getAttribute('data-s'), note:why}); } }
      if(!j.ok){ toast(j.error||'خطأ'); return; }
    }
    renderUnit();
  });
  app.addEventListener('change', async function(e){
    var el = e.target; var f = el.getAttribute('data-f'); if(!f) return;
    var comp = el.closest('.comp'); var key = comp.getAttribute('data-key');
    if(f==='photo'){
      var file = el.files && el.files[0]; if(!file) return;
      var fd = new FormData(); fd.append('id', o.id); fd.append('comp_key', key); fd.append('file', file);
      toast('جارٍ رفع الصورة…');
      var r = await fetch('/api/mot/photo', {method:'POST', headers:{'X-Token':TOKEN}, body:fd}).then(function(x){ return x.json(); });
      if(!r.ok){ toast(r.error||'فشل الرفع'); return; }
      renderUnit(); return;
    }
    var body = {id:o.id, comp_key:key, state:'missing'}; body[f] = el.value;
    var j = await api('/api/mot/result', body);
    if(!j.ok) toast(j.error||'خطأ'); else if(f!=='note') renderUnit();
  });
  qs('mint').onclick = async function(){
    var j = await api('/api/mot/token', {id:o.id}); if(!j.ok){ toast(j.error); return; }
    qs('linkout').innerHTML = '<code>' + esc(j.link) + '</code>';
    try{ await navigator.clipboard.writeText(j.link); toast('انسخ الرابط وأرسله للمفتش — صالح ٧ أيام'); }catch(err){ toast('الرابط جاهز — انسخه'); }
  };
  qs('aband').onclick = async function(){
    if(!confirm('ترك الجولة؟ ما تنحسب ولا تطلع فيها أرقام.')) return;
    var j = await api('/api/mot/abandon', {id:o.id}); if(!j.ok){ toast(j.error); return; }
    S.portfolio = null; renderUnit();
  };
  qs('closer').onclick = function(){ closeRound(o, {}); };
}

async function closeRound(o, extra){
  var body = {id:o.id}; var d = qs('recheck') && qs('recheck').value; if(d) body.recheck_due = d;
  for(var k in extra) body[k] = extra[k];
  var j = await api('/api/mot/close', body);
  if(!j.ok){
    if(j.unpriced){ if(confirm(j.error + NL + 'تكمل الإغلاق والبنود بدون سعر تطلع بصفر؟')) return closeRound(o, {allow_unpriced:true}); return; }
    toast(j.error||'خطأ'); return;
  }
  var f = j.fanout || {};
  var msg = 'أُغلقت الجولة · مطابقة ' + pct(j.score.compliance_pct) + ' · فحص ' + pct(j.score.inspected_pct);
  var lines = [];
  if(f.quote) lines.push('عرض سعر للمالك ' + f.quote.number + ' · ' + fmt(f.quote.total) + ' ر.س (في تبويب عروض الأسعار)');
  if(f.purchase_ticket) lines.push('تذكرة مشتريات عوجا ' + f.purchase_ticket + ' — افتح منها تذكرة proc في ديسكورد');
  if(f.maint_tickets && f.maint_tickets.length) lines.push(f.maint_tickets.length + ' تذكرة صيانة');
  if(f.documents && f.documents.keys && f.documents.keys.length) lines.push('مستندات: ' + (f.documents.seeded ? 'أُضيفت لمشروع ضم الوحدات' : 'ما فيه مشروع ضم — تابعها يدويًا'));
  if(f.blocked && f.blocked.length) lines.push(f.blocked.length + ' معيار إنشائي — الوحدة غير مطابقة وتحتاج قرار');
  if(f.errors && f.errors.length) lines.push('تنبيه: ' + f.errors.join(' · '));
  lines.push('إعادة الفحص: ' + j.recheck_due);
  modal('<h3>' + esc(msg) + '</h3><p>' + lines.map(esc).join('<br>') + '</p><div class="acts">'
    + (f.quote ? '<a class="btn gold" href="/dashboard?token=' + encodeURIComponent(TOKEN) + '#quote">افتح عرض السعر ' + esc(f.quote.number) + '</a>' : '')
    + (j.score.inspected_pct>=100 ? '<a class="btn" target="_blank" href="' + withTok('/api/mot/report?id=' + o.id) + '">ملف الدليل</a>' : '')
    + '<button class="btn primary" id="mok">تمام</button></div>');
  qs('mok').onclick = function(){ closeModal(); S.portfolio = null; renderUnit(); };
}

async function openRound(extra){
  var body = {listing_id: Number(S.lid)}; for(var k in extra) body[k] = extra[k];
  var j = await api('/api/mot/open', body);
  if(j.need_pool_answer){
    modal('<h3>فيها مسبح؟</h3><p>' + esc(j.error) + '</p><div class="acts"><button class="btn primary" id="py">فيها مسبح (٦٧ مكوّن)</button><button class="btn" id="pn">ما فيها (٦١ مكوّن)</button><button class="btn" id="pc">إلغاء</button></div>');
    qs('py').onclick = function(){ closeModal(); openRound({has_pool:true}); };
    qs('pn').onclick = function(){ closeModal(); openRound({has_pool:false}); };
    qs('pc').onclick = closeModal;
    return;
  }
  if(!j.ok){ toast(j.error||'خطأ'); return; }
  S.portfolio = null; renderUnit();
}

/* ---------- prices ---------- */
async function renderPrices(){
  var app = qs('app');
  app.innerHTML = '<div class="empty">جارٍ التحميل…</div>';
  var j = await api('/api/mot/prices'); if(!j.ok){ app.innerHTML = '<div class="empty">' + esc(j.error) + '</div>'; return; }
  var h = '<div class="card"><div class="hdr"><h2>قائمة الأسعار</h2><span class="meta">سعر واحد لكل مكوّن على مستوى الشركة · أي سعر أقدم من ' + j.stale_days + ' يومًا يتعلّم عليه «قديم» قبل ما يدخل عرضًا</span></div>';
  h += '<div style="overflow:auto"><table><thead><tr><th>#</th><th>المكوّن</th><th>النوع</th><th>الكمية الافتراضية</th><th>السعر (ر.س)</th><th>آخر تحديث</th></tr></thead><tbody>';
  j.rows.forEach(function(c){
    if(c.kind==='structural' || c.kind==='document') return;
    h += '<tr><td class="num">' + c.criterion_no + '</td><td><b>' + esc(c.label_ar) + '</b><div class="meta">' + esc(c.criterion_ar) + '</div></td><td>' + KIND[c.kind] + '</td>'
      + '<td class="meta">' + ({per_unit:'١ للشقة', per_bedroom:'لكل غرفة', per_bed:'لكل سرير', per_bathroom:'لكل حمام'}[c.unit_hint]||'') + '</td>'
      + '<td><input type="number" min="0" step="1" class="num" data-key="' + esc(c.key) + '" value="' + (c.price_sar!=null?c.price_sar:'') + '" style="width:110px;font:inherit;padding:6px 8px;border:1px solid var(--border);border-radius:8px"></td>'
      + '<td class="meta">' + (c.set_at ? day(c.set_at) + ' · ' + esc(c.set_by||'') + (c.stale ? ' <span class="pill warn">قديم</span>' : '') : '<span class="stale">ما انحط سعر</span>') + '</td></tr>';
  });
  h += '</tbody></table></div></div>';
  app.innerHTML = h;
  app.querySelector('tbody').addEventListener('change', async function(e){
    var el = e.target; if(!el.getAttribute('data-key')) return;
    var r = await api('/api/mot/price', {comp_key: el.getAttribute('data-key'), price_sar: el.value});
    if(!r.ok){ toast(r.error||'خطأ'); return; }
    toast('انحفظ السعر'); renderPrices();
  });
}

readHash();
</script>
</body>
</html>
"""
