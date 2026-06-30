# -*- coding: utf-8 -*-
"""
roster.page — the standalone, mobile-first team-leader page served at /roster (build spec §7B).

Same self-contained shell idea as bot.py's OUJACT_ROUTE_HTML: its own minimal HTML, reusing
the approved Ouja tokens (canvas #F5F5F7, white cards, Tajawal for Arabic, Inter tabular for
numbers rendered LTR, semantic-only status colour). Read-mostly: shows the same board + status
banner the dashboard shows (one engine), and lets an authorised leader log a same-day sick
leave. Auth is the existing multi-user token (?token=...), so leaders never touch the dashboard.

IMPORTANT (same trap as DASHBOARD_HTML): this is a normal triple-quoted Python string, so a
backslash escape (\\n, \\t, \\u, \\s) would be eaten by Python first and could break the page.
This file therefore contains NO backslashes — newlines use real line breaks inside template
literals, and there are no regexes.
"""

ROSTER_ROUTE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>عوجا — التوزيع اليومي</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#F5F5F7; --surface:#FFFFFF; --surface-2:#FAFAFC;
    --ink:#1C1C1E; --ink-2:#3A3A3C; --mut:#8E8E93; --line:#E8E8EC;
    --accent:#0A84FF; --accent-soft:#E9F2FF;
    --good:#34C759; --good-soft:#E7F8EC; --warn:#FF9F0A; --warn-soft:#FFF3DF;
    --bad:#FF3B30; --bad-soft:#FFE9E7; --info:#0A84FF; --info-soft:#E9F2FF;
    --r:16px; --r-sm:11px; --sh:0 1px 2px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.06);
    --ease:cubic-bezier(0.23,1,0.32,1);
    --font:'Tajawal',-apple-system,system-ui,sans-serif; --num:'Inter',sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);line-height:1.5}
  body{padding:max(14px,env(safe-area-inset-top)) 14px calc(28px + env(safe-area-inset-bottom))}
  .num{font-family:var(--num);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate;display:inline-block}
  header{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}
  .brand{font-weight:800;font-size:19px;letter-spacing:-.01em}
  .brand small{display:block;font-weight:500;font-size:12.5px;color:var(--mut);letter-spacing:0}
  .langbtn{border:1px solid var(--line);background:var(--surface);color:var(--ink-2);
    border-radius:999px;padding:8px 14px;font-family:var(--font);font-weight:700;font-size:13px;cursor:pointer;
    min-height:40px;transition:transform .12s var(--ease),background .12s}
  .langbtn:active{transform:scale(.96);background:var(--surface-2)}
  .banner{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px}
  .stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-sm);
    padding:12px 8px;text-align:center;box-shadow:var(--sh)}
  .stat .v{font-family:var(--num);font-variant-numeric:tabular-nums;font-weight:700;font-size:22px;line-height:1.1;direction:ltr}
  .stat .k{font-size:11.5px;color:var(--mut);margin-top:3px}
  .stat.ok .v{color:var(--good)} .stat.bad .v{color:var(--bad)} .stat.acc .v{color:var(--accent)}
  .pill{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:3px 10px;font-size:12.5px;font-weight:700}
  .pill.off{background:var(--warn-soft);color:#9a6200} .pill.leave{background:var(--bad-soft);color:#b3261e}
  .row-absent{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:14px}
  .sec{font-size:13px;color:var(--mut);font-weight:700;margin:6px 2px 9px}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
    box-shadow:var(--sh);padding:14px;margin-bottom:11px;animation:rise .32s var(--ease) both}
  @keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
  .chd{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
  .who{display:flex;align-items:center;gap:10px;min-width:0}
  .ava{width:38px;height:38px;border-radius:50%;background:var(--accent-soft);color:var(--accent);
    display:grid;place-items:center;font-weight:800;font-size:16px;flex:none}
  .nm{font-weight:800;font-size:16px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .load{font-family:var(--num);font-variant-numeric:tabular-nums;font-weight:700;font-size:15px;
    background:var(--surface-2);border:1px solid var(--line);border-radius:999px;padding:5px 12px;direction:ltr;flex:none}
  .grp{margin-top:9px}
  .grp .lab{font-size:12px;color:var(--mut);margin-bottom:6px;font-weight:700}
  .chips{display:flex;flex-wrap:wrap;gap:6px}
  .chip{background:var(--surface-2);border:1px solid var(--line);border-radius:8px;padding:5px 9px;font-size:12.5px}
  .chip.cov{background:var(--info-soft);border-color:#cfe4ff}
  .chip.cov b{font-weight:700;color:var(--mut);font-size:11px}
  .sick{margin-top:11px;width:100%;border:1px dashed var(--line);background:transparent;color:var(--ink-2);
    border-radius:10px;padding:11px;font-family:var(--font);font-weight:700;font-size:13.5px;cursor:pointer;
    min-height:44px;transition:transform .12s var(--ease),background .12s,border-color .12s}
  .sick:active{transform:scale(.98)} .sick:hover{border-color:var(--bad);color:var(--bad);background:var(--bad-soft)}
  .gapbox{background:var(--bad-soft);border:1px solid #f3c6c2;border-radius:var(--r);padding:14px;margin-bottom:12px}
  .gapbox b{color:#b3261e}
  .note{color:var(--mut);font-size:12.5px;text-align:center;margin-top:18px;line-height:1.6}
  .center{min-height:60vh;display:grid;place-items:center;text-align:center;color:var(--mut);padding:24px}
  .toast{position:fixed;left:50%;bottom:calc(20px + env(safe-area-inset-bottom));transform:translateX(-50%) translateY(20px);
    background:var(--ink);color:#fff;padding:11px 18px;border-radius:999px;font-weight:700;font-size:13.5px;
    opacity:0;pointer-events:none;transition:.28s var(--ease);z-index:50;max-width:90vw;text-align:center}
  .toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
  @media (prefers-reduced-motion: reduce){*{animation:none !important;transition:none !important}}
  @media (min-width:560px){ body{max-width:620px;margin:0 auto} }
</style>
</head>
<body>
  <header>
    <div class="brand">عوجا — التوزيع<small id="sub">مسؤوليات التغطية اليوم</small></div>
    <button class="langbtn" id="langbtn" onclick="toggleLang()">EN</button>
  </header>
  <div id="root"><div class="center">…</div></div>
  <div class="toast" id="toast"></div>
<script>
var L = (localStorage.getItem('ouja_roster_lang') || 'ar');
var TOK = new URLSearchParams(location.search).get('token') || localStorage.getItem('ouja_roster_tok') || '';
if (new URLSearchParams(location.search).get('token')) { localStorage.setItem('ouja_roster_tok', TOK); }
var DATA = null;

var T = {
  ar: {sub:'مسؤوليات التغطية اليوم', total:'الشقق', avail:'المتاحون', cov:'تغطية', gaps:'فجوات',
       own:'ملكه', covering:'يغطّي', off:'يوم راحة', leave:'إجازة', team:'فريق اليوم',
       sick:'تسجيل غياب اليوم', confirm:'تأكيد تسجيل غياب', gapsTitle:'تحتاج تغطية عاجلة',
       noauth:'افتح الصفحة من الرابط الموثوق (مع الرمز).', err:'تعذّر التحميل', saved:'تم الحفظ',
       allcov:'كل الشقق مغطّاة', forName:'بدل'},
  en: {sub:'Today coverage duties', total:'Units', avail:'Available', cov:'Coverage', gaps:'Gaps',
       own:'Own', covering:'Covering', off:'Day off', leave:'Leave', team:'Today team',
       sick:'Log absent today', confirm:'Confirm absence for', gapsTitle:'Needs urgent coverage',
       noauth:'Open this page from the trusted link (with token).', err:'Could not load', saved:'Saved',
       allcov:'All units covered', forName:'for'}
};
function t(){ return T[L]; }
function esc(s){ s = (s==null?'':String(s)); var m={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}; return s.replace(/[&<>"']/g, function(c){return m[c];}); }
function setLang(){ document.documentElement.lang = L; document.documentElement.dir = (L==='ar'?'rtl':'ltr'); document.getElementById('langbtn').textContent = (L==='ar'?'EN':'ع'); document.getElementById('sub').textContent = t().sub; }
function toggleLang(){ L = (L==='ar'?'en':'ar'); localStorage.setItem('ouja_roster_lang', L); setLang(); render(); }
function toast(msg){ var el=document.getElementById('toast'); el.textContent=msg; el.classList.add('show'); setTimeout(function(){el.classList.remove('show');}, 2400); }

function fmtDate(iso){ try{ var d=new Date(iso+'T00:00:00'); return d.toLocaleDateString(L==='ar'?'ar-SA':'en-GB', {weekday:'long', day:'numeric', month:'long'}); }catch(e){ return iso; } }

async function load(){
  setLang();
  if (!TOK){ document.getElementById('root').innerHTML = '<div class="center">'+esc(t().noauth)+'</div>'; return; }
  try{
    var r = await fetch('/api/roster?token='+encodeURIComponent(TOK));
    if (r.status===401 || r.status===403){ document.getElementById('root').innerHTML = '<div class="center">'+esc(t().noauth)+'</div>'; return; }
    var j = await r.json();
    DATA = j.roster; DATA.can_write = j.can_write;
    render();
  }catch(e){ document.getElementById('root').innerHTML = '<div class="center">'+esc(t().err)+'</div>'; }
}

function render(){
  if (!DATA){ return; }
  setLang();
  var s = DATA.status, h = '';
  h += '<div class="sec">'+esc(fmtDate(DATA.date))+'</div>';
  h += '<div class="banner">'
     + statCard('acc', s.total, t().total)
     + statCard('acc', s.available, t().avail)
     + statCard('ok', s.assigned, t().cov)
     + statCard(s.gaps>0?'bad':'ok', s.gaps, t().gaps)
     + '</div>';

  if (DATA.absent && DATA.absent.length){
    h += '<div class="row-absent">';
    DATA.absent.forEach(function(a){
      var cls = (a.reason==='leave'?'leave':'off');
      h += '<span class="pill '+cls+'">'+esc(a.name)+' · '+esc(a.reason==='leave'?t().leave:t().off)+'</span>';
    });
    h += '</div>';
  }

  if (DATA.gaps && DATA.gaps.length){
    h += '<div class="gapbox"><b>⚠ '+esc(t().gapsTitle)+' ('+DATA.gaps.length+')</b><div class="chips" style="margin-top:8px">';
    DATA.gaps.forEach(function(g){ h += '<span class="chip">'+esc(g.name)+'</span>'; });
    h += '</div></div>';
  }

  h += '<div class="sec">'+esc(t().team)+'</div>';
  DATA.board.forEach(function(e){
    h += '<div class="card">';
    h += '<div class="chd"><div class="who"><div class="ava">'+esc(e.initial||e.name.slice(0,1))+'</div><div class="nm">'+esc(e.name)+'</div></div><div class="load">'+e.load+'</div></div>';
    if (e.primary && e.primary.length){
      h += '<div class="grp"><div class="lab">'+esc(t().own)+' ('+e.primary.length+')</div><div class="chips">';
      e.primary.forEach(function(p){ h += '<span class="chip">'+esc(p.name)+'</span>'; });
      h += '</div></div>';
    }
    if (e.covered && e.covered.length){
      h += '<div class="grp"><div class="lab">'+esc(t().covering)+' ('+e.covered.length+')</div><div class="chips">';
      e.covered.forEach(function(c){ h += '<span class="chip cov">'+esc(c.name)+' <b>'+esc(t().forName)+' '+esc(c.orig_name||'')+'</b></span>'; });
      h += '</div></div>';
    }
    if (DATA.can_write){
      h += '<button class="sick" data-sick="'+e.id+'" data-name="'+esc(e.name)+'">'+esc(t().sick)+'</button>';
    }
    h += '</div>';
  });

  h += '<div class="note">عوجا · '+esc(DATA.date)+'</div>';
  document.getElementById('root').innerHTML = h;
}

function statCard(cls, v, k){ return '<div class="stat '+cls+'"><div class="v">'+v+'</div><div class="k">'+esc(k)+'</div></div>'; }

async function logSick(empId, name){
  if (!confirm(t().confirm+' '+name+' — '+fmtDate(DATA.date)+'?')){ return; }
  try{
    var r = await fetch('/api/absence?token='+encodeURIComponent(TOK), {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({employee_id:empId, start_date:DATA.date, end_date:DATA.date, type:'sick'})});
    var j = await r.json();
    if (j && j.ok && j.roster){ DATA = j.roster; DATA.can_write=true; render(); toast(t().saved); }
    else { toast((j && j.error) ? j.error : t().err); }
  }catch(e){ toast(t().err); }
}

document.addEventListener('click', function(ev){
  var b = ev.target.closest ? ev.target.closest('[data-sick]') : null;
  if (b){ logSick(parseInt(b.getAttribute('data-sick'),10), b.getAttribute('data-name')||''); }
});

load();
</script>
</body>
</html>"""
