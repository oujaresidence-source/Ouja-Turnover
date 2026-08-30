# -*- coding: utf-8 -*-
"""
onboarding.emp_page — the assigned employee's page at /onb/t/{token} (build spec §9.2).

Opened from the Discord card, on a phone, in one tap, with NO login: the token IS the
credential. Same precedent as the ops appeal link.

What it deliberately does NOT show: the client's phone number and email. This link carries no
login and gets forwarded around, so it must never leak a client's contact details — the same
reason the public team calendar strips the leave type and note. The server builds its payload
from an allow-list, and a test asserts those two keys never appear in the response.

SAME zero-backslash rule as onboarding.page: normal triple-quoted string, real newlines,
String.fromCharCode(10) in JS, no regex literals, event delegation only.
"""

EMP_PAGE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>مهامي · عوجا</title>
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
  body{padding:max(16px,env(safe-area-inset-top)) 14px calc(34px + env(safe-area-inset-bottom));max-width:560px;margin:0 auto}
  .num{font-family:var(--num);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate;display:inline-block}
  h1,h2,h3{margin:0;color:var(--ink)}
  .hero{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--sh);padding:17px;margin-bottom:13px}
  .hero .u{font-weight:800;font-size:19px;color:var(--ink)}
  .hero .m{color:var(--muted);font-size:13px;margin-top:3px}
  .chip{display:inline-block;border-radius:999px;padding:3px 10px;font-size:11.5px;font-weight:700;
    background:var(--gold-soft);color:#6E5C33;border:1px solid var(--gold);margin-top:9px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--sh);padding:16px;margin-bottom:13px}
  .card h3{font-size:15px;margin-bottom:10px}
  .kv{padding:9px 0;border-bottom:1px solid var(--border)}
  .kv:last-child{border-bottom:none}
  .kv .k{color:var(--muted);font-size:12px}
  .kv .v{font-size:14px;color:var(--ink);margin-top:2px;white-space:pre-wrap;line-height:1.6}
  .kv .v.none{color:var(--muted);font-style:italic}
  .stg{font-weight:800;color:var(--ink);font-size:14px;margin:16px 0 8px}
  .tsk{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:14px;margin-bottom:10px;
    border-inline-start:3px solid var(--border)}
  .tsk.done{border-inline-start-color:var(--green);background:var(--green-soft)}
  .tsk.na{border-inline-start-color:var(--muted)}
  .tsk.blocked{border-inline-start-color:var(--maroon);background:var(--maroon-soft)}
  .tsk .tt{font-weight:700;font-size:14px;color:var(--ink);line-height:1.5}
  .btns{display:flex;gap:7px;margin-top:11px;flex-wrap:wrap}
  button{font-family:var(--font)}
  .res{flex:1;min-width:88px;border:1px solid var(--border);background:#fff;border-radius:999px;padding:9px 8px;
    font-size:13px;font-weight:700;cursor:pointer;color:var(--body);min-height:44px;
    transition:transform .12s var(--ease),background .15s,color .15s}
  .res:active{transform:scale(.97)}
  .res.on[data-res="done"]{background:var(--green);border-color:var(--green);color:#fff}
  .res.on[data-res="na"]{background:var(--muted);border-color:var(--muted);color:#fff}
  .res.on[data-res="blocked"]{background:var(--maroon);border-color:var(--maroon);color:#fff}
  .rsn{display:none;gap:7px;margin-top:10px}
  .rsn.on{display:flex}
  .rsn input{flex:1;font-family:var(--font);font-size:14px;border:1px solid var(--border);border-radius:var(--r-sm);
    padding:10px 12px;min-height:44px;background:#fff;color:var(--body)}
  .rsn button{border:1px solid var(--gold);background:var(--gold);color:#fff;border-radius:999px;padding:9px 16px;
    font-weight:700;font-size:13px;cursor:pointer;min-height:44px}
  .why{color:var(--muted);font-size:12px;margin-top:6px}
  .bar{height:7px;border-radius:99px;background:var(--border);overflow:hidden;margin-top:12px}
  .bar > i{display:block;height:100%;background:var(--gold);transition:width .3s var(--ease)}
  .toast{position:fixed;inset-inline:0;bottom:0;background:var(--green);color:#fff;padding:14px 16px calc(14px + env(safe-area-inset-bottom));
    text-align:center;font-weight:700;display:none;z-index:70}
  .toast.on{display:block}
  .toast.bad{background:var(--maroon)}
  .note{background:var(--green-soft);border:1px solid var(--green);color:#2F5138;border-radius:var(--r);
    padding:15px;font-weight:700;margin-bottom:13px}
  .empty{text-align:center;color:var(--muted);padding:40px 16px}
  @media (prefers-reduced-motion: reduce){*{transition:none !important;animation:none !important}}
</style>
</head>
<body>
<main id="main"><div class="empty">لحظة…</div></main>
<div class="toast" id="toast"></div>

<script>
var TOKEN = (function(){
  var p = location.pathname.split('/');
  return decodeURIComponent(p[p.length-1] || '');
})();
var D = null, RO = false;

function esc(s){
  return String(s==null?'':s).split('&').join('&amp;').split('<').join('&lt;')
    .split('>').join('&gt;').split('"').join('&quot;');
}
function el(id){ return document.getElementById(id); }
function toast(msg, bad){
  var t = el('toast'); t.textContent = msg;
  t.className = 'toast on' + (bad?' bad':'');
  setTimeout(function(){ t.className = 'toast'; }, 3200);
}
function api(path, body){
  var opt = { headers:{'Content-Type':'application/json'} };
  if (body){ opt.method='POST'; opt.body=JSON.stringify(body); }
  return fetch(path, opt).then(function(r){ return r.json(); })
    .catch(function(){ return {ok:false, error:'ما وصلنا للخادم — حدّث الصفحة'}; });
}
function load(){
  return api('/api/onb-t/' + encodeURIComponent(TOKEN)).then(function(j){
    if (!j.ok){ el('main').innerHTML = '<div class="empty">' + esc(j.error||'الرابط ما عاد شغّال') + '</div>'; return; }
    D = j; RO = !!j.readonly; render();
  });
}
var HFIELDS = [
  ['access_notes','الدخول والمفاتيح'],
  ['wifi_notes','الواي فاي'],
  ['house_rules','قواعد المنزل'],
  ['checkin_time','وقت الدخول'],
  ['checkout_time','وقت الخروج']
];
function render(){
  var p = D.project, h = '';
  if (RO) h += '<div class="note">الوحدة انسلّمت — شكرًا</div>';
  h += '<div class="hero"><div class="u">' + esc(p.unit_name||'') + '</div>'
    + '<div class="m"><span class="num">' + esc(p.ref||'') + '</span>'
    + (p.district?(' · ' + esc(p.district)):'') + '</div>'
    + '<div class="m">' + esc(p.client_name||'') + (p.bedrooms?(' · <span class="num">' + p.bedrooms + '</span> غرف'):'')
    + (p.handover_target?(' · التسليم المستهدف <span class="num">' + esc(p.handover_target) + '</span>'):'') + '</div>'
    + '<div class="chip">' + esc(p.stage_label||'') + '</div>'
    + '<div class="bar"><i style="width:' + (D.progress||0) + '%"></i></div>'
    + '<div class="why">تقدّم المشروع <span class="num">' + (D.progress||0) + '%</span>'
    + (D.buddy?(' · معك ' + esc(D.buddy)):'') + '</div></div>';

  h += '<div class="card"><h3>معلومات تحتاجها</h3>';
  for (var i=0;i<HFIELDS.length;i++){
    var k = HFIELDS[i][0], v = D.handover[k];
    var none = (v==null || String(v).trim()==='');
    h += '<div class="kv"><div class="k">' + esc(HFIELDS[i][1]) + '</div>'
      + '<div class="v' + (none?' none':'') + '">' + esc(none?'لسا ما تعبّى':v) + '</div></div>';
  }
  h += '</div>';

  var tasks = D.tasks || [];
  if (!tasks.length){
    h += '<div class="empty">ما فيه مهام مسندة لك على هالوحدة</div>';
  } else {
    var stages = D.stages || [];
    for (var s=0;s<stages.length;s++){
      var rows = tasks.filter(function(t){ return t.stage===stages[s].id; });
      if (!rows.length) continue;
      h += '<div class="stg">' + esc(stages[s].label) + '</div>';
      for (var r=0;r<rows.length;r++){
        var t = rows[r], res = t.resolution || 'open';
        h += '<div class="tsk ' + esc(res) + '" data-task="' + t.id + '">'
          + '<div class="tt">' + (t.gate?'🔒 ':'') + esc(t.title_ar) + '</div>';
        if (t.reason) h += '<div class="why">السبب: ' + esc(t.reason) + '</div>';
        if (!RO){
          h += '<div class="btns">'
            + '<button class="res' + (res==='done'?' on':'') + '" data-res="done" data-t="' + t.id + '">تم</button>'
            + '<button class="res' + (res==='na'?' on':'') + '" data-res="na" data-t="' + t.id + '">ما ينطبق</button>'
            + '<button class="res' + (res==='blocked'?' on':'') + '" data-res="blocked" data-t="' + t.id + '">متوقف</button>'
            + '</div>'
            + '<div class="rsn" id="rsn' + t.id + '"><input placeholder="اكتب السبب" data-rin="' + t.id + '">'
            + '<button data-rok="' + t.id + '">تأكيد</button></div>';
        } else {
          h += '<div class="why">' + esc({open:'ما انحلّت',done:'تم',na:'ما ينطبق',blocked:'متوقف'}[res]) + '</div>';
        }
        h += '</div>';
      }
    }
  }
  el('main').innerHTML = h;
}
function submit(tid, res, reason){
  api('/api/onb/t/submit', {token:TOKEN, task_id:tid, resolution:res, reason:reason||''})
    .then(function(j){
      if (!j.ok){ toast(j.error||'ما انحفظ', true); return; }
      toast('انحفظ');
      D.tasks = j.tasks; D.progress = j.progress; render();
    });
}
document.addEventListener('click', function(ev){
  var t = ev.target; if (!t.closest) return;
  var rb = t.closest('.res');
  if (rb){
    var tid = rb.getAttribute('data-t'), res = rb.getAttribute('data-res');
    if (res==='done'){ submit(parseInt(tid,10), 'done', ''); return; }
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
    if (!val){ toast('اكتب السبب — «ما ينطبق» و«متوقف» لازم لها سبب', true); return; }
    submit(parseInt(id2,10), bx.getAttribute('data-mode'), val);
    return;
  }
});

load();
</script>
</body>
</html>"""
