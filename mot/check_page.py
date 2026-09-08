# -*- coding: utf-8 -*-
"""
mot.check_page — /mot-check/{token}, the INSPECTOR phone page.

No login, no DASHBOARD_TOKEN: the token in the URL is the credential, and it can only
write results and photos into ONE open round (see routes.core_check_*). It reads
/api/mot-t/{token} and posts /api/mot/check-result and /api/mot/check-photo — nothing
else, and tests/test_mot_token_scope.py greps this file to keep it that way.

ZERO backslashes below the docstring (the DASHBOARD_HTML trap). esprima-parse after edits.
"""

HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>فحص المطابقة — عوجا</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#F1EDE6;--panel:#FAF7F1;--ink:#292925;--body:#33302B;--muted:#9C958A;--gold:#B29A6A;--gold-soft:#F0E8D8;
--maroon:#8B3748;--maroon-soft:#F3E2E4;--green:#4A7C59;--green-soft:#E4EFE6;--amber:#B4802F;--amber-soft:#F7EBD6;
--border:#E7DFD1;--r:16px;--ease:cubic-bezier(0.23,1,0.32,1);--font:'Tajawal',system-ui,sans-serif;--num:'Inter',sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);font-size:16px;line-height:1.45;max-width:560px;margin:0 auto;padding-bottom:90px}
.top{position:sticky;top:0;z-index:5;background:rgba(241,237,230,.94);backdrop-filter:blur(10px);border-bottom:1px solid var(--border);padding:12px 16px}
.top b{display:block;font-size:17px;color:var(--ink)}
.top small{color:var(--muted)}
.bar{height:8px;background:#E4DDD0;border-radius:99px;overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;background:var(--green);width:0;transition:width .3s var(--ease)}
.who{display:flex;gap:8px;align-items:center;margin-top:8px;font-size:14px}
.who input{flex:1;font:inherit;padding:6px 10px;border:1px solid var(--border);border-radius:10px;background:#fff}
h3{margin:18px 16px 6px;font-size:14px;color:var(--muted);font-weight:700}
.comp{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);margin:0 12px 10px;padding:12px 14px;box-shadow:0 1px 2px rgba(41,41,37,.04)}
.comp .t{display:flex;gap:8px;align-items:baseline}
.comp .t .no{font-family:var(--num);color:var(--muted);font-size:13px}
.comp .t b{color:var(--ink);font-size:16px}
.comp .t small{color:var(--muted);font-size:12px;margin-inline-start:auto}
.seg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:10px}
.seg button{border:1px solid var(--border);background:#fff;font:inherit;font-weight:800;padding:11px 4px;border-radius:12px;color:var(--muted);cursor:pointer;transition:transform .12s var(--ease),background .15s;font-size:14px}
.seg button:active{transform:scale(.97)}
.seg button.av.on{background:var(--green);color:#fff;border-color:var(--green)}
.seg button.mi.on{background:var(--maroon);color:#fff;border-color:var(--maroon)}
.seg button.un.on{background:#D9D2C5;color:var(--ink);border-color:#D9D2C5}
.extra{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px;font-size:14px}
.step{display:inline-flex;align-items:center;border:1px solid var(--border);border-radius:10px;background:#fff;overflow:hidden}
.step button{border:0;background:transparent;font:inherit;font-size:20px;width:40px;height:38px;cursor:pointer;color:var(--ink)}
.step span{font-family:var(--num);font-weight:700;min-width:34px;text-align:center}
.extra input.n{flex:1;min-width:140px;font:inherit;padding:8px 10px;border:1px solid var(--border);border-radius:10px;background:#fff}
.cam{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);background:#fff;border-radius:10px;padding:8px 12px;font-weight:700;cursor:pointer}
.cam input{display:none}
.ph{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.ph img{width:64px;height:48px;object-fit:cover;border-radius:8px;border:1px solid var(--border)}
.tag{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px;font-weight:700}
.tag.ok{background:var(--green-soft);color:var(--green)} .tag.bad{background:var(--maroon-soft);color:var(--maroon)} .tag.mute{background:#EDE7DC;color:var(--muted)}
.empty{padding:40px 20px;text-align:center;color:var(--muted)}
.foot{position:fixed;bottom:0;left:0;right:0;background:rgba(250,247,241,.96);border-top:1px solid var(--border);padding:10px 16px;display:flex;gap:10px;align-items:center;font-size:14px;max-width:560px;margin:0 auto}
.foot b{font-family:var(--num);color:var(--ink)}
.foot a.go{margin-inline-start:auto;background:var(--gold);color:#fff;text-decoration:none;font-weight:800;padding:9px 12px;border-radius:12px;font-size:13px;white-space:nowrap}
.toast{position:fixed;bottom:70px;left:50%;transform:translate(-50%,20px);background:var(--ink);color:#fff;padding:10px 18px;border-radius:999px;opacity:0;transition:all .22s var(--ease);pointer-events:none;z-index:20;max-width:90vw;font-size:14px}
.toast.show{opacity:1;transform:translate(-50%,0)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<div class="top" id="top"><b>فحص المطابقة</b><small>جارٍ التحميل…</small></div>
<div id="list"><div class="empty">جارٍ التحميل…</div></div>
<div class="foot" id="foot"></div>
<div class="toast" id="toast"></div>
<script>
var TOKEN = (function(){ var p = location.pathname.split('/'); return decodeURIComponent(p[p.length-1] || ''); })();
var SECTIONS = [['s1','المبنى والوصول'],['s2','الوحدة العامة'],['s3','الراحة والتجهيزات'],['s4','غرفة النوم والاستديو'],['s5','دورة المياه'],['s6','المطبخ'],['s7','السلامة والاستدامة'],['s8','معايير المسبح']];
var D = null;
var WHO = '';
try{ WHO = localStorage.getItem('mot_who') || ''; }catch(e){}

function esc(s){ return String(s===null||s===undefined?'':s).split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;').split('"').join('&quot;'); }
function qs(id){ return document.getElementById(id); }
function toast(m){ var t = qs('toast'); t.textContent = m; t.classList.add('show'); setTimeout(function(){ t.classList.remove('show'); }, 2200); }
function post(path, body){ return fetch(path, {method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body:JSON.stringify(body)}).then(function(r){ return r.json(); }); }

async function load(){
  var j = await fetch('/api/mot-t/' + encodeURIComponent(TOKEN), {headers:{'Accept':'application/json'}}).then(function(r){ return r.json(); });
  if(!j.ok){ qs('top').innerHTML = '<b>فحص المطابقة</b><small>' + esc(j.error||'الرابط ما عاد شغّال') + '</small>'; qs('list').innerHTML = '<div class="empty">' + esc(j.error||'') + '</div>'; qs('foot').innerHTML = ''; return; }
  D = j; render();
}

function render(){
  var r = D.round, lv = D.live;
  qs('top').innerHTML = '<b>' + esc(r.apartment_name) + '</b><small>جولة #' + r.id + ' · ' + r.denominator + ' مكوّن' + (r.has_pool ? ' (مع مسبح)' : '') + ' · فُحص ' + (lv.available+lv.missing) + ' من ' + r.denominator + '</small>'
    + '<div class="bar"><i style="width:' + lv.inspected_pct + '%"></i></div>'
    + '<div class="who"><span>اسمك:</span><input id="who" value="' + esc(WHO) + '" placeholder="اكتب اسمك مرة وحدة"></div>';
  qs('who').addEventListener('change', function(){ WHO = this.value.trim(); try{ localStorage.setItem('mot_who', WHO); }catch(e){} });
  var h = '';
  SECTIONS.forEach(function(sec){
    var comps = D.components.filter(function(c){ return c.section===sec[0]; });
    if(!comps.length) return;
    h += '<h3>' + esc(sec[1]) + '</h3>';
    comps.forEach(function(c){
      var res = D.results[c.key] || {}; var st = res.state || 'unchecked'; var ph = D.photos[c.key] || [];
      h += '<div class="comp" data-key="' + esc(c.key) + '"><div class="t"><span class="no">' + c.criterion_no + '</span><b>' + esc(c.label_ar) + '</b><small>' + esc(c.criterion_ar) + (res.source==='wifi' ? ' · <span class="tag ok">من اشتراكات النت</span>' : '') + '</small></div>';
      h += '<div class="seg"><button class="av' + (st==='available'?' on':'') + '" data-s="available">متوفر</button><button class="mi' + (st==='missing'?' on':'') + '" data-s="missing">غير متوفر</button><button class="un' + (st==='unchecked'?' on':'') + '" data-s="unchecked">لم يُفحص</button></div>';
      if(st==='missing'){
        h += '<div class="extra">';
        if(c.kind==='product' || c.kind==='works'){
          h += '<span class="step"><button data-d="-1">−</button><span class="qv">' + (res.qty || '—') + '</span><button data-d="1">+</button></span><span style="color:var(--muted);font-size:12px">الكمية (— = حسب الغرف)</span>';
        }
        h += '<input class="n" data-f="note" placeholder="ملاحظة" value="' + esc(res.note||'') + '">';
        h += '<label class="cam">📷 صورة (' + ph.length + '/' + D.max_photos + ')<input type="file" accept="image/*" capture="environment"' + (ph.length>=D.max_photos?' disabled':'') + '></label>';
        h += '</div>';
      }
      if(ph.length) h += '<div class="ph">' + ph.map(function(id){ return '<img src="/api/mot-t/' + encodeURIComponent(TOKEN) + '/photo/' + id + '">'; }).join('') + '</div>';
      h += '</div>';
    });
  });
  qs('list').innerHTML = h;
  qs('foot').innerHTML = '<span>باقي <b>' + lv.not_inspected + '</b></span><span>متوفر <b>' + lv.available + '</b></span><span>غير متوفر <b>' + lv.missing + '</b></span>'
    + (lv.not_inspected ? '<span style="margin-inline-start:auto;color:var(--muted);font-size:12px">كمّل الكل عشان تقدر تقفل الجولة</span>'
                        : '<a class="go" href="/mot#unit=' + encodeURIComponent(r.listing_id) + '">🧾 إغلاق وإصدار العرض (اللوحة)</a>');
}

async function save(key, patch){
  var body = {token:TOKEN, comp_key:key, who:WHO};
  var cur = D.results[key] || {};
  body.state = patch.state || cur.state || 'unchecked';
  if(patch.qty !== undefined) body.qty = patch.qty;
  if(patch.note !== undefined) body.note = patch.note;
  var j = await post('/api/mot/check-result', body);
  if(!j.ok){ toast(j.error||'ما انحفظ'); return false; }
  D.results[key] = {state:j.result.state, qty:j.result.qty, note:j.result.note, source:j.result.source};
  D.live = j.live;
  return true;
}

qs('list').addEventListener('click', async function(e){
  var comp = e.target.closest('.comp'); if(!comp) return;
  var key = comp.getAttribute('data-key');
  var sb = e.target.closest('.seg button');
  if(sb){
    var st = sb.getAttribute('data-s');
    var cur = D.results[key] || {};
    if(key==='c13.wifi' && cur.source==='wifi' && cur.state!==st){
      var why = prompt('الإنترنت يجي من «اشتراكات النت» — اكتب سبب التغيير:'); if(!why) return;
      if(await save(key, {state:st, note:why})) render();
      return;
    }
    if(await save(key, {state:st})) render();
    return;
  }
  var stp = e.target.closest('.step button');
  if(stp){
    var cur2 = D.results[key] || {}; var q = Number(cur2.qty || 1) + Number(stp.getAttribute('data-d'));
    if(q < 1) q = 1;
    if(await save(key, {qty:q})) comp.querySelector('.qv').textContent = q;
  }
});
qs('list').addEventListener('change', async function(e){
  var comp = e.target.closest('.comp'); if(!comp) return;
  var key = comp.getAttribute('data-key');
  if(e.target.getAttribute('data-f')==='note'){ await save(key, {note:e.target.value}); return; }
  if(e.target.type==='file'){
    var f = e.target.files && e.target.files[0]; if(!f) return;
    var fd = new FormData(); fd.append('token', TOKEN); fd.append('comp_key', key); fd.append('who', WHO); fd.append('file', f);
    toast('جارٍ رفع الصورة…');
    var j = await fetch('/api/mot/check-photo', {method:'POST', body:fd}).then(function(r){ return r.json(); });
    if(!j.ok){ toast(j.error||'فشل الرفع'); return; }
    (D.photos[key] = D.photos[key] || []).push(j.photo.id);
    render(); toast('انرفعت');
  }
});

load();
</script>
</body>
</html>
"""
