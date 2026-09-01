# -*- coding: utf-8 -*-
"""digest.page — the owner's web preview at /digest (login-gated).

SAME backslash trap as DASHBOARD_HTML and schedule/page.py: this is a normal
triple-quoted string, so there are ZERO backslashes in this file. Newlines in JS are
String.fromCharCode(10); no regex literals; HTML is built with + and an esc() helper;
one delegated click handler reads data-* attributes. Colours are the digest tokens."""

DIGEST_PAGE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>وش صاير بالرياض · المعاينة</title>
<style>
:root{--ink:#0B1A2E;--ink-2:#122944;--ink-3:#1D3048;--paper:#F7F4EE;--white:#FFFFFF;--line:#ECEAE5;--mute:#6B7280;--gold:#C6A15B;--gold-2:#D9C194;--green:#1F6F55;--green-bg:#E6EFEC;--red:#B23A34;--red-bg:#F9F1F0}
*{box-sizing:border-box}
html,body{margin:0;background:var(--paper);color:var(--ink);font-family:"IBM Plex Sans Arabic","Almarai",system-ui,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:24px 18px 60px}
.eyebrow{display:inline-block;font-size:12px;letter-spacing:.12em;color:var(--mute);padding-bottom:6px;border-bottom:2px solid var(--gold);margin-bottom:16px}
h1{font-size:30px;margin:0 0 6px}
.status{color:var(--mute);margin-bottom:18px}
.grid{display:grid;grid-template-columns:minmax(280px,1fr) 2fr;gap:22px}
@media (max-width:820px){.grid{grid-template-columns:1fr}}
.card{background:var(--white);border:1px solid var(--line);border-radius:12px;padding:18px}
.card h2{font-size:15px;letter-spacing:.06em;color:var(--mute);margin:0 0 12px;font-weight:600}
.story{width:100%;border-radius:10px;border:1px solid var(--line);display:block}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
button{font:inherit;border:1px solid var(--line);background:var(--white);color:var(--ink);border-radius:999px;padding:9px 16px;cursor:pointer;transition:transform .12s cubic-bezier(.23,1,.32,1),background .12s}
button:active{transform:scale(.97)}
button.primary{background:var(--ink);color:var(--paper);border-color:var(--ink)}
button.danger{color:var(--red);border-color:var(--red-bg);background:var(--red-bg)}
button[disabled]{opacity:.45;cursor:not-allowed}
.sec{padding:10px 0;border-top:1px solid var(--line)}
.sec .k{font-size:12px;letter-spacing:.1em;color:var(--gold);margin-bottom:6px}
.item{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:6px 0}
.item .t{font-weight:600}
.item .s{color:var(--mute);font-size:13px}
.item .ops{display:flex;gap:6px;flex-shrink:0}
.item .ops button{padding:5px 10px;font-size:13px}
.drops{color:var(--mute);font-size:13px}
.msg{white-space:pre-wrap;font-size:13px;color:var(--ink);background:var(--paper);border-radius:8px;padding:12px;border:1px solid var(--line)}
.toast{position:fixed;inset-inline-start:18px;inset-block-end:18px;background:var(--ink);color:var(--paper);padding:10px 14px;border-radius:10px;font-size:14px;opacity:0;transform:translateY(6px);transition:opacity .2s,transform .2s cubic-bezier(.23,1,.32,1)}
.toast.on{opacity:1;transform:translateY(0)}
.alts{margin-top:8px;padding:10px;border:1px dashed var(--line);border-radius:8px;display:none}
.alts.on{display:block}
.alts button{display:block;width:100%;text-align:start;margin:4px 0;border-radius:8px}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;background:var(--green-bg);color:var(--green);margin-inline-start:6px}
.tag.dry{background:var(--red-bg);color:var(--red)}
a{color:var(--ink)}
@media (prefers-reduced-motion:reduce){button,.toast{transition:none}}
</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">عوجا · نشرة نهاية الأسبوع</div>
  <h1>وش صاير بالرياض <span id="dry" class="tag dry" hidden>تجربة — ما ينشر</span></h1>
  <div class="status" id="status">…</div>
  <div class="grid">
    <div class="card">
      <h2>الستوري</h2>
      <img id="story" class="story" alt="" hidden>
      <div class="actions" id="files"></div>
    </div>
    <div class="card">
      <h2>القرار</h2>
      <div class="actions" id="actions"></div>
      <div id="sections"></div>
      <div class="sec"><div class="k">حذفناه</div><div class="drops" id="drops"></div></div>
      <div class="sec"><div class="k">نص الرسالة</div><div class="msg" id="msg"></div></div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
var NL = String.fromCharCode(10);
var ISSUE = null;
function esc(s){ return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function toast(t){ var el = document.getElementById('toast'); el.textContent = t; el.className = 'toast on'; setTimeout(function(){ el.className = 'toast'; }, 2600); }
function api(path, body){
  var opt = body ? {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)} : {};
  return fetch(path, opt).then(function(r){ return r.json(); });
}
function render(d){
  ISSUE = d.issue;
  document.getElementById('dry').hidden = !d.dryrun;
  var st = document.getElementById('status');
  if (!ISSUE){ st.textContent = 'ما فيه عدد بعد. الأربعاء ١:٠٠ ظهراً يبني نفسه، أو اضغط «ابنِ الآن».'; document.getElementById('actions').innerHTML = '<button class="primary" data-act="build">ابنِ الآن</button>'; return; }
  st.textContent = ISSUE.status_line + (ISSUE.error ? ' — ' + ISSUE.error : '');
  var img = document.getElementById('story');
  if (ISSUE.status === 'preview' || ISSUE.status === 'approved' || ISSUE.status === 'published'){ img.src = '/digest/file/' + ISSUE.issue_no + '/png?t=' + Date.now(); img.hidden = false; } else { img.hidden = true; }
  document.getElementById('files').innerHTML = '<a href="/digest/file/' + ISSUE.issue_no + '/pdf" target="_blank">PDF</a> · <a href="/digest/file/' + ISSUE.issue_no + '/json" target="_blank">JSON</a>';
  var allowed = ISSUE.allowed || [];
  var labels = {approve:'✅ اعتمد وانشر', rephrase:'✍️ غيّر الصيغة', rebuild:'🔄 ابنِ من جديد'};
  var html = '';
  ['approve','rephrase','rebuild'].forEach(function(a){
    var cls = a === 'approve' ? 'primary' : '';
    html += '<button class="' + cls + '" data-act="' + a + '"' + (allowed.indexOf(a) < 0 ? ' disabled' : '') + '>' + labels[a] + '</button>';
  });
  document.getElementById('actions').innerHTML = html;
  var secs = '';
  (ISSUE.sections || []).forEach(function(s){
    if (!s.items.length) return;
    secs += '<div class="sec"><div class="k">' + esc(s.title) + '</div>';
    s.items.forEach(function(it, i){
      var key = s.key + '.' + i;
      var alts = (ISSUE.alternates && ISSUE.alternates[key]) || [];
      secs += '<div class="item"><div><div class="t">' + esc(it.ttl) + '</div><div class="s">' + esc(it.sub) + '</div></div>';
      secs += '<div class="ops">';
      if (allowed.indexOf('alt') >= 0 && alts.length) secs += '<button data-act="showalt" data-key="' + key + '">🔁 بدائل</button>';
      if (allowed.indexOf('drop') >= 0) secs += '<button class="danger" data-act="drop" data-section="' + s.key + '" data-slot="' + i + '">🗑️</button>';
      secs += '</div></div>';
      secs += '<div class="alts" id="alts-' + key + '">';
      alts.forEach(function(a){ secs += '<button data-act="alt" data-section="' + s.key + '" data-slot="' + i + '" data-rank="' + a.rank + '">' + esc(a.ttl) + ' <span class="s">' + esc((a.reasons || []).join(' · ')) + '</span></button>'; });
      secs += '</div>';
    });
    secs += '</div>';
  });
  document.getElementById('sections').innerHTML = secs;
  document.getElementById('drops').innerHTML = (ISSUE.dropped || []).map(function(d){ return '• ' + esc(d.ttl) + ' — ' + esc(d.reason); }).join('<br>') || '—';
  document.getElementById('msg').textContent = ISSUE.message || '';
}
function load(){ api('/api/digest/status').then(render).catch(function(){ toast('تعذّر التحميل'); }); }
document.addEventListener('click', function(ev){
  var b = ev.target.closest('button[data-act]');
  if (!b) return;
  var act = b.getAttribute('data-act');
  if (act === 'showalt'){ var el = document.getElementById('alts-' + b.getAttribute('data-key')); el.className = el.className === 'alts on' ? 'alts' : 'alts on'; return; }
  if (act === 'build'){ b.disabled = true; toast('نبني… دقيقة'); api('/api/digest/build', {}).then(function(d){ if (!d.ok) toast(d.error || (d.errors || []).join(' ')); load(); }); return; }
  if (!ISSUE) return;
  if (act === 'approve' && !confirm('تعتمد العدد ' + ISSUE.issue_no + '؟')) return;
  if (act === 'drop' && !confirm('تحذف هالعنصر؟')) return;
  var body = {issue: ISSUE.id, action: act, section: b.getAttribute('data-section'), slot: b.getAttribute('data-slot'), rank: b.getAttribute('data-rank')};
  b.disabled = true; toast('شغالين…');
  api('/api/digest/act', body).then(function(d){ toast(d.ok ? d.result.message : (d.error || 'ما صار')); if (d.issue){ render({issue: d.issue, dryrun: document.getElementById('dry').hidden === false}); } else { load(); } });
});
load();
</script>
</body>
</html>
"""
