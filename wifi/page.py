# -*- coding: utf-8 -*-
"""
wifi.page — the standalone /wifi-fill backfill page for the field team.

Follows the /team-calendar precedent: phone-first, Arabic RTL, NO login and NO token, so
the team opens the link with nothing. Unlike /team-calendar this one WRITES — but only
through the add-only public door (wifi.routes.core_fill_save), which cannot close, edit
or delete anything and stamps every row is_backfill=1.

WHAT THE PAGE ASKS FOR (owner call, 2026-08-03):
    GO AND FIND THE REAL DATE. The telco app, the purchase SMS, the invoice, or a call to
    the shop — the information exists, so the page asks for it plainly and does not offer
    a shortcut past the question.

    «ما لقيت المعلومة» still exists, but quiet and secondary, and it says out loud what
    happens next (saved with no date, shows up under «ما نعرف»). It is kept for one
    reason: somebody who genuinely cannot find the date would otherwise type ANY date
    just to be allowed to save, and an invented date is worse than a blank — the system
    believes it, and would then report a live subscription as dead. A blank is honest;
    a fabrication is not.

SAME BACKSLASH TRAP AS DASHBOARD_HTML: this is a normal triple-quoted string, so Python
eats any backslash before JavaScript ever sees it. There are ZERO backslashes in this
file — real newlines, event delegation, no inline-onclick quote building, no regex.
Verify with esprima after any edit.
"""

HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>اشتراكات النت — تعبئة</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#F1EDE6; --panel:#FAF7F1; --ink:#292925; --body:#33302B; --muted:#9C958A;
    --gold:#B29A6A; --gold-soft:#F0E8D8; --maroon:#8B3748; --maroon-soft:#F3E2E4;
    --green:#4A7C59; --green-soft:#E4EFE6; --amber:#B4802F; --amber-soft:#F7EBD6;
    --border:#E7DFD1; --r:16px; --r-sm:11px;
    --sh:0 1px 2px rgba(41,41,37,.04),0 10px 30px rgba(41,41,37,.07);
    --ease:cubic-bezier(0.23,1,0.32,1); --font:'Tajawal',-apple-system,system-ui,sans-serif;
    --num:'Inter',sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);line-height:1.55}
  body{padding:max(14px,env(safe-area-inset-top)) 14px calc(34px + env(safe-area-inset-bottom))}
  .num{font-family:var(--num);font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate;display:inline-block}
  header{margin-bottom:14px}
  .ttl{font-weight:800;font-size:21px;color:var(--ink);letter-spacing:-.01em}
  .sub{color:var(--muted);font-size:13px;margin-top:2px}
  .who{margin-top:10px;font-size:13.5px;color:var(--body)}
  .who b{color:var(--ink)}
  .lnk{background:none;border:none;color:var(--gold);font-family:var(--font);font-weight:700;
    font-size:13.5px;cursor:pointer;padding:2px 4px;text-decoration:underline;text-underline-offset:3px}
  /* progress */
  .prog{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    box-shadow:var(--sh);padding:14px;margin-bottom:16px}
  .prog .line{display:flex;align-items:baseline;justify-content:space-between;gap:10px}
  .prog .big{font-weight:800;font-size:17px;color:var(--ink)}
  .prog .bar{height:8px;border-radius:99px;background:var(--gold-soft);margin-top:10px;overflow:hidden}
  .prog .bar i{display:block;height:100%;background:var(--gold);border-radius:99px;
    transition:width .4s var(--ease)}
  /* cards */
  .grid{display:grid;gap:10px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    box-shadow:var(--sh);padding:14px;text-align:start;width:100%;font-family:var(--font);
    cursor:pointer;border-inline-start:4px solid var(--border);
    transition:transform .12s var(--ease)}
  .card:active{transform:scale(.98)}
  .card .nm{font-weight:800;font-size:16px;color:var(--ink)}
  .card .st{font-size:13px;margin-top:4px;color:var(--muted)}
  .card.done{border-inline-start-color:var(--green);background:var(--green-soft)}
  .card.done .st{color:var(--green);font-weight:700}
  .card.todo{border-inline-start-color:var(--gold)}
  .prog.allDone{background:var(--green-soft);border-color:rgba(74,124,89,.25)}
  .prog.allDone .big{color:var(--green)}
  .fin{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    box-shadow:var(--sh);padding:26px 18px;text-align:center;margin-bottom:6px}
  .fin .fe{font-size:38px;line-height:1}
  .fin .ft{font-weight:800;font-size:19px;color:var(--ink);margin-top:10px}
  .fin .fs{color:var(--muted);font-size:13.5px;margin-top:4px}
  .sect{font-weight:700;font-size:13.5px;color:var(--muted);margin:18px 0 8px}
  .empty{color:var(--muted);font-size:14px;padding:20px;text-align:center;
    background:var(--panel);border:1px solid var(--border);border-radius:var(--r)}
  /* people picker */
  .people{display:grid;gap:10px}
  .pbtn{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    padding:16px;font-family:var(--font);font-weight:800;font-size:16px;color:var(--ink);
    cursor:pointer;text-align:start;box-shadow:var(--sh);transition:transform .12s var(--ease)}
  .pbtn:active{transform:scale(.98)}
  /* sheet */
  .scrim{position:fixed;inset:0;background:rgba(41,41,37,.42);opacity:0;pointer-events:none;
    transition:opacity .25s var(--ease);z-index:40}
  .scrim.show{opacity:1;pointer-events:auto}
  .sheet{position:fixed;left:0;right:0;bottom:0;background:var(--panel);
    border-radius:20px 20px 0 0;box-shadow:0 -10px 40px rgba(41,41,37,.18);z-index:41;
    transform:translateY(102%);transition:transform .3s var(--ease);max-height:88vh;
    overflow-y:auto;padding:18px 16px calc(24px + env(safe-area-inset-bottom))}
  .sheet.show{transform:translateY(0)}
  .sheeth{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
  .sheeth .nm{font-weight:800;font-size:19px;color:var(--ink)}
  .x{border:none;background:var(--bg);color:var(--body);width:34px;height:34px;
    border-radius:50%;font-size:18px;cursor:pointer;font-family:var(--font)}
  .q{margin-top:18px}
  .q .lab{font-weight:700;font-size:14.5px;color:var(--ink);margin-bottom:8px}
  .chips{display:flex;flex-wrap:wrap;gap:8px}
  .chip{border:1px solid var(--border);background:var(--bg);color:var(--body);
    border-radius:999px;padding:10px 15px;font-family:var(--font);font-weight:700;
    font-size:14px;cursor:pointer;min-height:44px;
    transition:transform .12s var(--ease),background .15s,color .15s,border-color .15s}
  .chip:active{transform:scale(.97)}
  .chip[aria-pressed="true"]{background:var(--ink);color:#fff;border-color:var(--ink)}
  input[type=text],input[type=number],input[type=date]{width:100%;padding:12px;
    border:1px solid var(--border);border-radius:var(--r-sm);background:var(--bg);
    font-family:var(--font);font-size:16px;color:var(--ink);min-height:46px}
  input:focus{outline:2px solid var(--gold);outline-offset:1px}
  .row{display:flex;gap:8px;align-items:center}
  .row input{flex:1}
  .hint{color:var(--muted);font-size:12.5px;margin-top:6px}
  /* The escape hatch is DELIBERATELY quiet now: the ask is to go and find the real
     date, not to tap past the question. It still exists, because somebody who truly
     cannot find it would otherwise type any date just to be allowed to save — and an
     invented date is worse than a blank, since the system believes it. */
  .dk{border:none;background:none;color:var(--muted);font-family:var(--font);font-weight:600;
    font-size:12.5px;cursor:pointer;padding:8px 2px;margin-top:2px;text-decoration:underline;
    text-underline-offset:3px;transition:color .15s}
  .dk:active{color:var(--ink)}
  .dk[aria-pressed="true"]{color:var(--amber);text-decoration:none;font-weight:700}
  .dknote{display:none;background:var(--amber-soft);color:var(--ink);border-radius:var(--r-sm);
    padding:9px 11px;font-size:12.5px;line-height:1.6;margin-top:6px}
  .dknote.on{display:block}
  .save{width:100%;margin-top:22px;border:none;background:var(--ink);color:#fff;
    border-radius:var(--r-sm);padding:15px;font-family:var(--font);font-weight:800;
    font-size:16px;cursor:pointer;min-height:52px;transition:transform .12s var(--ease),opacity .15s}
  .save:active{transform:scale(.98)}
  .save[disabled]{opacity:.45;cursor:default}
  .known{background:var(--green-soft);border:1px solid var(--border);border-radius:var(--r-sm);
    padding:12px;font-size:13.5px;color:var(--ink);margin-top:14px}
  .toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,20px);opacity:0;
    background:var(--ink);color:#fff;padding:12px 18px;border-radius:999px;font-weight:700;
    font-size:14px;z-index:60;pointer-events:none;transition:opacity .2s,transform .25s var(--ease)}
  .toast.show{opacity:1;transform:translate(-50%,0)}
  @media (prefers-reduced-motion:reduce){*{transition:none !important}}
</style>
</head>
<body>

<header>
  <div class="ttl" id="hello">اشتراكات النت</div>
  <div class="sub" id="helloSub">سجّل اشتراك النت لكل شقة — طلّع المعلومة الصح</div>
  <div class="who" id="whoLine"></div>
</header>

<div id="progWrap"></div>
<div id="body"><div class="empty">جاري التحميل…</div></div>

<div class="scrim" id="scrim"></div>
<div class="sheet" id="sheet" role="dialog" aria-modal="true"></div>
<div class="toast" id="toast"></div>

<script>
var D = {units:[], people:[], who:'', me:null, done:0, total:0, remaining:0,
         providers:[], provider_ar:{}, label_days:[30,60,90]};
var F = {};          /* the answers for the apartment currently open */
var CUR = null;      /* the apartment currently open */
var EID = '';        /* the short ?e=<id> the WhatsApp link carries */

function esc(s){
  return String(s === null || s === undefined ? '' : s)
    .split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;')
    .split('"').join('&quot;');
}
function qs(id){ return document.getElementById(id); }

function param(name){
  var q = location.search;
  if(q.charAt(0) === '?') q = q.slice(1);
  var parts = q.split('&');
  for(var i=0;i<parts.length;i++){
    var kv = parts[i].split('=');
    if(decodeURIComponent(kv[0]) === name) return decodeURIComponent((kv[1]||'').split('+').join(' '));
  }
  return '';
}

function toast(msg){
  var t = qs('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2200);
}

/* ---------- load ---------- */

async function load(){
  /* The link we send on WhatsApp is /wifi-fill?e=1 — short and clean. Once someone
     picks a name by hand we fall back to ?who=, which older links still use. */
  var who = D.who || param('who');
  var eid = EID || param('e');
  var url = '/api/wifi/fill';
  if(eid) url += '?e=' + encodeURIComponent(eid);
  else if(who) url += '?who=' + encodeURIComponent(who);
  try{
    var r = await fetch(url, {headers:{'Accept':'application/json'}});
    var j = await r.json();
    if(!j.ok){ qs('body').innerHTML = '<div class="empty">ما قدرنا نجيب البيانات</div>'; return; }
    D.units = j.units || [];
    D.people = j.people || [];
    D.who = j.who || '';
    D.me = j.me || null;
    D.done = j.done || 0;
    D.total = j.total || 0;
    D.remaining = (j.remaining === undefined) ? (D.total - D.done) : j.remaining;
    D.providers = j.providers || [];
    D.provider_ar = j.provider_ar || {};
    D.label_days = j.label_days || [30,60,90];
    applyPersonalTheme();
    render();
  }catch(e){
    qs('body').innerHTML = '<div class="empty">ما قدرنا نجيب البيانات — جرّب تحدّث الصفحة</div>';
  }
}

/* ---------- render ---------- */

/* The page wears the employee's OWN colour from تقويم الموظفين — ناصر's is green,
   مآثر's is orange. Same page, but it reads as his. One source: change the colour in
   the calendar and this follows, because nothing is copied here. */
function applyPersonalTheme(){
  var c = (D.me && D.me.color) ? D.me.color : '';
  var root = document.documentElement;
  if(c){ root.style.setProperty('--gold', c); root.style.setProperty('--accent-ink', c); }
  else { root.style.removeProperty('--gold'); root.style.removeProperty('--accent-ink'); }
}

function render(){
  if(!D.who){ renderPeople(); return; }
  renderGreeting();
  renderProgress();
  renderList();
}

/* Arabic counts its nouns properly or it reads like a machine wrote it:
   1 = شقة وحدة, 2 = شقتين, 3-10 = N شقق, 11+ = N شقة. */
function aptCount(n){
  if(n === 1) return 'شقة وحدة';
  if(n === 2) return 'شقتين';
  if(n <= 10) return n + ' شقق';
  return n + ' شقة';
}

function renderGreeting(){
  var emo = (D.me && D.me.emoji) ? (D.me.emoji + ' ') : '';
  qs('hello').innerHTML = 'هلا ' + esc(D.who) + ' ' + esc(emo.trim()) + ' 👋';
  qs('helloSub').textContent = D.remaining
    ? ('باقي عليك ' + aptCount(D.remaining))
    : 'ما باقي عليك شي';
  qs('whoLine').innerHTML = '<button class="lnk" data-act="switch">مو أنت؟ غيّر الاسم</button>';
}

function renderPeople(){
  qs('hello').textContent = 'اشتراكات النت';
  qs('helloSub').textContent = 'سجّل اشتراك النت لكل شقة — طلّع المعلومة الصح';
  qs('whoLine').innerHTML = '';
  qs('progWrap').innerHTML = '';
  var h = '<div class="sect">مين أنت؟</div><div class="people">';
  for(var i=0;i<D.people.length;i++){
    h += '<button class="pbtn" data-act="pick" data-who="' + esc(D.people[i]) + '">'
       + esc(D.people[i]) + '</button>';
  }
  h += '<button class="pbtn" data-act="pick" data-who="">كل الشقق</button></div>';
  qs('body').innerHTML = h;
}

function renderProgress(){
  var pct = D.total ? Math.round(D.done * 100 / D.total) : 0;
  var done = D.total > 0 && D.done >= D.total;
  qs('progWrap').innerHTML =
    '<div class="prog' + (done ? ' allDone' : '') + '"><div class="line">'
    + '<div class="big">خلصت <span class="num">' + D.done
    + '</span> من <span class="num">' + D.total + '</span></div>'
    + '<div class="sub"><span class="num">' + pct + '%</span></div></div>'
    + '<div class="bar"><i style="width:' + pct + '%"></i></div></div>';
}

function bandWord(u){
  if(!u.known) return 'ما سجّلنا له شي';
  var p = D.provider_ar[u.provider] || u.provider || 'مسجّل';
  if(u.end_date) return 'مسجّل · ' + p + ' · ينتهي ' + u.end_date;
  return 'مسجّل · ' + p + ' · التاريخ غير معروف';
}

function renderList(){
  if(!D.units.length){
    qs('body').innerHTML = '<div class="empty">ما فيه شقق مربوطة باسمك</div>';
    return;
  }
  var todo = [], done = [];
  for(var i=0;i<D.units.length;i++){ (D.units[i].known ? done : todo).push(D.units[i]); }
  var h = '';
  /* Finishing deserves to look like finishing. An empty list with no message reads as a
     bug; this says plainly that there is nothing left. */
  if(!todo.length){
    h += '<div class="fin"><div class="fe">🎉</div>'
      + '<div class="ft">خلصت كل شققك</div>'
      + '<div class="fs">ما باقي عليك ولا شقة — شكراً ' + esc(D.who) + '</div></div>';
  }
  if(todo.length){
    h += '<div class="sect">باقي عليك (' + todo.length + ')</div><div class="grid">';
    for(var a=0;a<todo.length;a++) h += cardHtml(todo[a]);
    h += '</div>';
  }
  if(done.length){
    h += '<div class="sect">مسجّلة (' + done.length + ')</div><div class="grid">';
    for(var b=0;b<done.length;b++) h += cardHtml(done[b]);
    h += '</div>';
  }
  qs('body').innerHTML = h;
}

function cardHtml(u){
  return '<button class="card ' + (u.known ? 'done' : 'todo') + '" data-act="open" data-lid="'
    + u.listing_id + '"><div class="nm">' + esc(u.apartment_name) + '</div>'
    + '<div class="st">' + esc(bandWord(u)) + '</div></button>';
}

/* ---------- the sheet ---------- */

function openSheet(lid){
  var u = null;
  for(var i=0;i<D.units.length;i++){ if(String(D.units[i].listing_id) === String(lid)) u = D.units[i]; }
  if(!u) return;
  CUR = u;
  F = {provider:'', source_kind:'', source_name:'', amount_sar:'', purchase_date:'',
       label_days:'', unknown_date:false};
  qs('sheet').innerHTML = sheetHtml(u);
  qs('scrim').classList.add('show');
  qs('sheet').classList.add('show');
  syncSave();
}

function closeSheet(){
  qs('scrim').classList.remove('show');
  qs('sheet').classList.remove('show');
  CUR = null;
}

function chipsHtml(name, items){
  var h = '<div class="chips">';
  for(var i=0;i<items.length;i++){
    h += '<button class="chip" data-act="chip" data-field="' + name + '" data-value="'
       + esc(items[i].v) + '" aria-pressed="false">' + esc(items[i].t) + '</button>';
  }
  return h + '</div>';
}

function sheetHtml(u){
  var provs = [];
  for(var i=0;i<D.providers.length;i++){
    provs.push({v:D.providers[i], t:(D.provider_ar[D.providers[i]] || D.providers[i])});
  }
  var lens = [];
  for(var j=0;j<D.label_days.length;j++){
    lens.push({v:String(D.label_days[j]), t:D.label_days[j] + ' يوم'});
  }
  var h = '<div class="sheeth"><div class="nm">' + esc(u.apartment_name) + '</div>'
    + '<button class="x" data-act="close" aria-label="إغلاق">×</button></div>';

  if(u.known){
    h += '<div class="known">هذي الشقة مسجّل لها اشتراك — ' + esc(bandWord(u))
       + '. لو فيه غلط، كلّم المشرف يعدّله من اللوحة.</div>';
    return h;
  }

  h += '<div class="q"><div class="lab">1 · الشركة</div>' + chipsHtml('provider', provs) + '</div>';

  h += '<div class="q"><div class="lab">2 · من وين شريناه</div>'
     + chipsHtml('source_kind', [{v:'first_party', t:'من الشركة نفسها'}, {v:'vendor', t:'من محل'}])
     + '<div id="shopWrap" style="display:none;margin-top:8px">'
     + '<input type="text" id="shopName" placeholder="اسم المحل" inputmode="text">'
     + '</div></div>';

  h += '<div class="q"><div class="lab">3 · كم مدته</div>' + chipsHtml('label_days', lens)
     + '<div class="hint">اللي مكتوب على الباقة نفسها</div></div>';

  h += '<div class="q"><div class="lab">4 · كم دفعنا</div>'
     + '<input type="number" id="amount" placeholder="بالريال" inputmode="decimal" min="0"></div>';

  h += '<div class="q"><div class="lab">5 · متى شريناه</div>'
     + '<input type="date" id="pdate">'
     + '<div class="hint">طلّعه من تطبيق الشركة أو من رسالة الشراء أو الفاتورة — لا تكتب تاريخ من راسك</div>'
     + '<button class="dk" data-act="dontknow" aria-pressed="false">ما لقيت المعلومة</button>'
     + '<div class="dknote" id="dkNote">بنسجّلها بدون تاريخ، وبتظهر عند فيصل ضمن «ما نعرف». '
     + 'إذا لقيت التاريخ بعدين كلّمه يحدّثها.</div></div>';

  h += '<button class="save" id="saveBtn" data-act="save" disabled>احفظ</button>';
  return h;
}

function syncSave(){
  var btn = qs('saveBtn');
  if(!btn) return;
  var dateOk = F.unknown_date || (qs('pdate') && qs('pdate').value);
  var ok = F.provider && F.source_kind && F.label_days && dateOk;
  btn.disabled = !ok;
}

function pickChip(field, value, el){
  F[field] = value;
  var group = el.parentNode.querySelectorAll('.chip');
  for(var i=0;i<group.length;i++) group[i].setAttribute('aria-pressed', 'false');
  el.setAttribute('aria-pressed', 'true');
  if(field === 'source_kind'){
    var w = qs('shopWrap');
    if(w) w.style.display = (value === 'vendor') ? 'block' : 'none';
  }
  syncSave();
}

function toggleDontKnow(el){
  F.unknown_date = !F.unknown_date;
  el.setAttribute('aria-pressed', F.unknown_date ? 'true' : 'false');
  el.textContent = F.unknown_date ? 'ما لقيت المعلومة ✓' : 'ما لقيت المعلومة';
  /* Say what happens next, so tapping this is a decision and not a shortcut. */
  var note = qs('dkNote');
  if(note) note.classList.toggle('on', F.unknown_date);
  var d = qs('pdate');
  if(d){
    if(F.unknown_date) d.value = '';
    d.disabled = F.unknown_date;
  }
  syncSave();
}

async function save(){
  if(!CUR) return;
  var btn = qs('saveBtn');
  if(btn) btn.disabled = true;
  var shop = qs('shopName');
  var amount = qs('amount');
  var pdate = qs('pdate');
  var payload = {
    listing_id: CUR.listing_id,
    apartment_name: CUR.apartment_name,
    provider: F.provider,
    source_kind: F.source_kind,
    source_name: (F.source_kind === 'vendor' && shop) ? shop.value : '',
    label_days: F.label_days,
    amount_sar: amount ? amount.value : '',
    purchase_date: F.unknown_date ? '' : (pdate ? pdate.value : ''),
    who: D.who
  };
  try{
    var r = await fetch('/api/wifi/fill-save', {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    var j = await r.json();
    if(!j.ok){ toast('ما انحفظ — جرّب مرة ثانية'); if(btn) btn.disabled = false; return; }
    toast(j.kind === 'exists' ? 'مسجّلة أصلاً' : 'انحفظت');
    closeSheet();
    await load();
  }catch(e){
    toast('ما انحفظ — تأكد من النت');
    if(btn) btn.disabled = false;
  }
}

/* ---------- one delegated listener for the whole page ---------- */

document.addEventListener('click', function(ev){
  var el = ev.target;
  while(el && el !== document.body && !el.getAttribute('data-act')) el = el.parentNode;
  if(!el || el === document.body) return;
  var act = el.getAttribute('data-act');
  if(act === 'open') openSheet(el.getAttribute('data-lid'));
  else if(act === 'close') closeSheet();
  else if(act === 'chip') pickChip(el.getAttribute('data-field'), el.getAttribute('data-value'), el);
  else if(act === 'dontknow') toggleDontKnow(el);
  else if(act === 'save') save();
  /* Picking a name by hand drops the ?e= that came from the link, otherwise the id
     would keep winning and the person could never switch off their own page. */
  else if(act === 'pick'){ EID = ''; D.who = el.getAttribute('data-who'); D.me = null; load(); }
  else if(act === 'switch'){ EID = ''; D.who = ''; D.me = null; D.units = [];
                             applyPersonalTheme(); renderPeople(); }
});

document.addEventListener('input', function(ev){
  if(ev.target && (ev.target.id === 'pdate' || ev.target.id === 'amount')) syncSave();
});

qs('scrim').addEventListener('click', closeSheet);

load();
</script>
</body>
</html>
"""
