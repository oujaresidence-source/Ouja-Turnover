# -*- coding: utf-8 -*-
"""studio.mobile — the phone page behind the Discord links.

The owner's actual workflow: he's in Discord on his phone, types a command, taps the
link, and wants to be filming within ten seconds. So this page is NOT the dashboard
shrunk down — it's a different product: one column, ranked best-first, filters as
thumb-sized chips, and every card copyable in one tap.

Auth is the unguessable link token (same trust model as the investor link), NOT a
login — a login form on a phone is exactly the friction this is meant to remove.
Every route re-checks the token; there is no session.

SAME BACKSLASH TRAP as DASHBOARD_HTML: this is a normal triple-quoted string, so it
contains NO backslashes at all. Real newlines, event delegation, no regex literals.
node --check the extracted script after any edit.
"""

import secrets

from . import db, engine, learn, plan, rank
from .host import HOST

_TOKEN_FILE = "studio_link.json"
_cache = {}

VIEWS = ("today", "ideas", "signals", "posted")


def link_token():
    """The stable share token. Generated once, then persisted — a token that changed
    on every deploy would silently break every link already sitting in Discord."""
    if _cache.get("token"):
        return _cache["token"]
    data = {}
    try:
        data = HOST.load_json(_TOKEN_FILE, {}) or {}
    except Exception:
        data = {}
    tok = str(data.get("token") or "").strip()
    if not tok:
        tok = secrets.token_urlsafe(18)
        try:
            HOST.save_json(_TOKEN_FILE, {"token": tok, "created_at": _now_iso()})
        except Exception as e:
            print("[studio] link token not persisted (will regenerate on restart):", e)
    _cache["token"] = tok
    return tok


def regenerate_token():
    _cache.pop("token", None)
    tok = secrets.token_urlsafe(18)
    try:
        HOST.save_json(_TOKEN_FILE, {"token": tok, "created_at": _now_iso()})
    except Exception:
        pass
    _cache["token"] = tok
    return tok


def _now_iso():
    try:
        return HOST.require("now")().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _today():
    return _now_iso()[:10]


def token_ok(request):
    want = link_token()
    got = str(request.match_info.get("token") or "")
    return bool(want) and secrets.compare_digest(got, want)


def share_url(view="today", base=""):
    """The link that goes into Discord. `base` comes from PUBLIC_BASE_URL."""
    u = "%s/s/%s" % (str(base or "").rstrip("/"), link_token())
    return u + ("?v=" + view if view and view != "today" else "")


# ---------------- feed ----------------

def _signal_strengths():
    out = {}
    try:
        for s in db.signals(limit=400):
            out[s["sid"]] = s.get("strength", 50)
    except Exception:
        pass
    return out


def feed(view="today", filters=None):
    """The ranked card list for one view. Filters are ANDed; an unknown value is
    ignored rather than returning an empty page (a phone user can't debug a filter)."""
    filters = filters or {}
    view = view if view in VIEWS else "today"
    today = _today()
    stats = learn.stats(db.learn_rows())

    if view == "signals":
        rows = [s for s in db.signals(limit=200) if s.get("status") != "hidden"]
        fam = filters.get("family")
        if fam in engine.SIGNAL_FAMILIES:
            rows = [s for s in rows if s.get("family") == fam]
        for s in rows:
            age = engine.freshness_days(s.get("as_of"), today)
            s["age_days"] = age
            s["is_hot"] = bool(s.get("family") == "external" and age is not None and age <= 7)
        rows.sort(key=lambda s: (-(s.get("strength") or 0), str(s.get("as_of") or "")),
                  reverse=False)
        return {"view": view, "signals": rows, "cards": [], "stats": stats}

    if view == "today":
        cards = plan.build_day(today, plan.DAILY_N, False)
    elif view == "posted":
        cards = [c for c in db.ideas(limit=200)
                 if c.get("status") in ("posted", "filmed")]
    else:
        cards = [c for c in db.ideas(limit=200)
                 if c.get("status") in ("new", "shortlisted")]

    strengths = _signal_strengths()
    for c in cards:
        c["signal_strength"] = strengths.get(c.get("signal_sid"), 50)

    for key, field in (("audience", "audience"), ("family", "signal_family"),
                       ("trigger", "trigger_kind"), ("format", "video_type")):
        want = filters.get(key)
        if want:
            got = [c for c in cards if str(c.get(field) or "") == want]
            if got or view != "today":       # never blank out today's plan on a typo
                cards = got
    ranked = rank.rank(cards, stats, today)
    return {"view": view, "cards": ranked, "signals": [], "stats": stats}


def facets(cards):
    """Which filter chips are worth showing — never offer a filter that yields zero."""
    def _vals(field):
        seen = []
        for c in cards:
            v = str(c.get(field) or "")
            if v and v not in seen:
                seen.append(v)
        return seen
    return {"audience": _vals("audience"), "family": _vals("signal_family"),
            "trigger": _vals("trigger_kind"), "format": _vals("video_type")}


# ---------------- the page ----------------
# NO BACKSLASHES anywhere below this line inside the string.

MOBILE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#F1EDE6">
<title>عوجا ستوديو — وش أصوّر</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=Inter:wght@600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#F1EDE6; --panel:#FAF7F1; --ink:#292925; --body:#33302B; --muted:#8F887C;
    --gold:#B29A6A; --gold-soft:#F0E8D8; --red:#B93A3A; --red-soft:#F6E3E3;
    --green:#3E7D4E; --green-soft:#E4EFE7; --amber:#A8762A; --amber-soft:#F5EBDA;
    --border:#E7DFD1; --r:16px;
    --sh:0 1px 2px rgba(41,41,37,.05),0 10px 26px rgba(41,41,37,.07);
    --ease:cubic-bezier(0.23,1,0.32,1);
    --font:'IBM Plex Sans Arabic',-apple-system,system-ui,sans-serif;
    --num:'Inter',sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);
    line-height:1.6;font-size:17px;-webkit-text-size-adjust:100%}
  .wrap{max-width:620px;margin:0 auto;padding:12px 12px calc(96px + env(safe-area-inset-bottom))}

  .top{display:flex;align-items:baseline;justify-content:space-between;gap:10px;
    padding:6px 4px 10px}
  .top h1{font-size:19px;font-weight:700;color:var(--ink);margin:0}
  .top .d{font-size:13px;color:var(--muted);font-family:var(--num)}

  .rowchips{display:flex;gap:7px;overflow-x:auto;padding:2px 0 10px;scrollbar-width:none}
  .rowchips::-webkit-scrollbar{display:none}
  .c{flex:none;min-height:42px;display:inline-flex;align-items:center;gap:5px;
    background:var(--panel);border:1px solid var(--border);border-radius:999px;
    padding:0 15px;font:inherit;font-size:15px;font-weight:600;color:var(--muted);
    cursor:pointer;transition:transform .15s var(--ease),background .15s var(--ease)}
  .c:active{transform:scale(.97)}
  .c.on{background:var(--ink);border-color:var(--ink);color:#FAF7F1}
  .c.f.on{background:var(--gold-soft);border-color:#E4D6B8;color:var(--ink)}
  .fbar{display:flex;gap:7px;overflow-x:auto;padding:0 0 10px;scrollbar-width:none}
  .fbar::-webkit-scrollbar{display:none}

  .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    padding:14px;margin-bottom:12px;box-shadow:var(--sh);position:relative}
  .rk{display:flex;align-items:center;gap:8px;margin-bottom:10px}
  .rk .n{font-family:var(--num);font-weight:700;font-size:15px;color:var(--ink);
    background:var(--gold-soft);border-radius:999px;padding:3px 12px}
  .rk .n.top{background:var(--ink);color:#FAF7F1}
  .rk .w{font-size:12px;color:var(--muted);font-weight:500;line-height:1.4}
  .rk .v{font-family:var(--num);font-weight:600;font-size:12px;color:var(--green);
    background:var(--green-soft);border:1px solid #CBDFD1;border-radius:999px;padding:2px 9px}
  .rk .v.low{color:var(--amber);background:var(--amber-soft);border-color:#E8D9BC}
  .fix{background:var(--amber-soft);border:1px solid #E8D9BC;border-radius:10px;
    padding:9px 12px;margin-bottom:9px;font-size:14px;color:var(--ink)}
  .fix b{display:block;font-size:12px;color:var(--amber);margin-bottom:3px}
  .fix ul{margin:0;padding-inline-start:18px}
  .fix li{margin-bottom:3px}

  .hookbox{background:var(--ink);color:#FAF7F1;border-radius:12px;padding:15px 16px;
    text-align:center;margin-bottom:10px}
  .hookbox .vt{font-size:19px;font-weight:700;line-height:1.45}
  .hookbox .vs{font-size:14px;font-weight:400;opacity:.85;margin-top:3px}
  .say{display:flex;gap:8px;align-items:baseline;background:var(--gold-soft);
    border-radius:10px;padding:9px 12px;margin-bottom:9px;font-size:16px;font-weight:600;
    color:var(--ink)}
  .say span{flex:none;font-size:11px;font-weight:700;color:var(--amber)}
  .sig{border-inline-start:3px solid var(--gold);background:var(--bg);border-radius:8px;
    padding:8px 11px;margin-bottom:9px;font-size:14px;color:var(--ink)}
  .sig b{font-weight:600}
  .sig .m{display:block;margin-top:4px;font-size:12px;color:var(--muted)}
  .sig a{color:var(--gold);text-decoration:none;font-weight:600}
  ol.s{margin:0 0 9px;padding-inline-start:19px;font-size:15px}
  ol.s li{margin-bottom:4px}
  .why{background:var(--green-soft);border:1px solid #CBDFD1;border-radius:8px;
    padding:8px 11px;margin-bottom:9px;font-size:14px;color:var(--ink)}
  .tags{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:11px}
  .t{font-size:12px;font-weight:600;border-radius:7px;padding:3px 9px;background:var(--bg);
    border:1px solid var(--border);color:var(--body)}
  .t.g{background:var(--gold-soft);border-color:#E4D6B8}
  .t.hot{background:var(--red-soft);color:var(--red);border-color:#EBCCCC}
  .t.ok{background:var(--green-soft);color:var(--green);border-color:#CBDFD1}

  .acts{display:flex;flex-wrap:wrap;gap:8px}
  .acts button{flex:1 1 auto;min-height:46px;border:1px solid var(--border);
    border-radius:999px;padding:0 14px;font:inherit;font-size:15px;font-weight:600;
    background:var(--bg);color:var(--ink);cursor:pointer;
    transition:transform .15s var(--ease)}
  .acts button:active{transform:scale(.97)}
  .acts button.main{background:var(--ink);color:#FAF7F1;border-color:var(--ink)}
  .acts button[disabled]{opacity:.5}
  .vin{display:flex;gap:8px;width:100%;margin-top:8px}
  .vin input{flex:1;min-height:46px;padding:0 14px;font:inherit;font-size:16px;
    border:1px solid var(--border);border-radius:999px;background:var(--bg);
    color:var(--body);outline:none;font-family:var(--num)}

  .sg{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);
    padding:13px 14px;margin-bottom:10px;box-shadow:var(--sh);
    border-inline-start:3px solid var(--gold)}
  .sg.ext{border-inline-start-color:var(--green)}
  .sg .f{font-size:16px;font-weight:600;color:var(--ink);line-height:1.55}
  .sg .d{font-size:14px;margin-top:4px}

  .empty{color:var(--muted);font-size:15px;padding:26px 10px;text-align:center}
  .foot{color:var(--muted);font-size:12px;text-align:center;padding:16px 0 0}
  .toast{position:fixed;bottom:calc(16px + env(safe-area-inset-bottom));right:50%;
    transform:translateX(50%);background:var(--ink);color:#FAF7F1;padding:11px 20px;
    border-radius:999px;font-size:15px;opacity:0;pointer-events:none;
    transition:opacity .25s var(--ease);z-index:99}
  .toast.show{opacity:1}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important;animation:none !important} }
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><h1>🎬 وش أصوّر</h1><span class="d" id="day"></span></div>
  <div class="rowchips" id="views">
    <button class="c on" data-v="today">📅 اليوم</button>
    <button class="c" data-v="ideas">💡 كل الأفكار</button>
    <button class="c" data-v="signals">📡 الإشارات</button>
    <button class="c" data-v="posted">🚀 نشرتها</button>
  </div>
  <div class="fbar" id="filters"></div>
  <div id="list"><div class="empty">لحظة…</div></div>
  <div class="foot">مرتّبة بالأقرب إنها تشتغل لك — من أدائك أنت، مو من قواعد عامة</div>
</div>
<div class="toast" id="toast"></div>
<script>
var BASE = location.pathname.replace(/[/]+$/, '');
var V = new URLSearchParams(location.search).get('v') || 'today';
var F = {};
var DATA = {cards: [], signals: []};
var NL = String.fromCharCode(10);

var TRG = {curiosity:'فضول', loss:'خسارة', identity:'هوية', provocation:'رأي مخالف',
  authority:'خبرة داخلية', social_proof:'أرقام', news:'خبر', emotion:'مشاعر'};
var AUD = {niche:'ملّاك 🏠', escape:'جمهور عام 🌍'};
var VT = {talking:'كلام', tour:'جولة', before_after:'قبل/بعد', story_voiceover:'سرد',
  onsite:'ميداني', data_reveal:'أرقام', news_reaction:'رد على خبر'};
var SRC = {occupancy:'الإشغال', pricing:'التسعير', reviews:'التقييمات', ops:'العمليات',
  season:'الموسم', insider:'من الداخل', guest_story:'قصة ضيف', regulation:'أنظمة',
  market:'سوق السعودية', global_trend:'اتجاه عالمي', trend:'خبر', manual:'كتبته بنفسك'};
var FAM = {internal:'بيانات عوجا', external:'مصدر خارجي', manual:'موقف من عندك'};
var FLBL = {audience:AUD, family:FAM, trigger:TRG, format:VT};

function esc(s){
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function toast(m){
  var t = document.getElementById('toast');
  t.textContent = m; t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2200);
}
function qs(){
  var p = ['v=' + V], k;
  for (k in F){ if (F[k]){ p.push(k + '=' + encodeURIComponent(F[k])); } }
  return p.join('&');
}
function load(){
  fetch(BASE + '/feed?' + qs()).then(function(r){ return r.json(); }).then(function(r){
    if (!r.ok){ document.getElementById('list').innerHTML =
      '<div class="empty">' + esc(r.error || 'ما قدرت أفتح') + '</div>'; return; }
    DATA = r; render(r);
  });
}
function chipRow(fac){
  var html = '', k, i;
  var keys = ['audience','family','trigger','format'];
  for (i = 0; i < keys.length; i++){
    k = keys[i];
    var vals = (fac[k] || []);
    if (vals.length < 2){ continue; }
    for (var j = 0; j < vals.length; j++){
      var v = vals[j];
      var lbl = (FLBL[k] || {})[v] || v;
      html += '<button class="c f' + (F[k] === v ? ' on' : '') + '" data-f="' + k
        + '" data-fv="' + esc(v) + '">' + esc(lbl) + '</button>';
    }
  }
  if (html){ html = '<button class="c f' + (Object.keys(F).length ? '' : ' on')
    + '" data-f="clear">الكل</button>' + html; }
  return html;
}
function card(x, i){
  var s = (x.script || []).map(function(b){ return '<li>' + esc(b) + '</li>'; }).join('');
  var why = (x.rank_why || []).join(' · ');
  var st = x.status || 'new';
  var sig = x.signal_text
    ? '<div class="sig"><b>الإشارة:</b> ' + esc(x.signal_text)
      + '<span class="m">' + esc(SRC[x.signal_source] || '')
      + (x.signal_date ? ' · ' + esc(x.signal_date) : '')
      + (x.signal_url ? ' · <a href="' + esc(x.signal_url) + '" target="_blank" rel="noopener">المصدر</a>' : '')
      + '</span></div>'
    : '';
  var vs = (x.virality === undefined) ? '' :
    '<span class="v' + (x.virality < 60 ? ' low' : '') + '">بناء ' + x.virality + '٪</span>';
  var fixes = (x.fixes || []).length
    ? '<div class="fix"><b>وش تعدّل قبل ما تصوّر</b><ul>'
      + x.fixes.map(function(f){ return '<li>' + esc(f) + '</li>'; }).join('') + '</ul></div>'
    : '';
  return '<div class="card" data-id="' + x.id + '">'
    + '<div class="rk"><span class="n' + (i === 0 ? ' top' : '') + '">' + (x.rank_score || 0) + '٪</span>'
    + vs + '<span class="w">' + esc(why || 'ترتيب مبدئي') + '</span></div>'
    + '<div class="hookbox"><div class="vt">' + esc(x.visual_title) + '</div>'
    + (x.visual_sub ? '<div class="vs">' + esc(x.visual_sub) + '</div>' : '') + '</div>'
    + '<div class="say"><span>🎤 قول</span>' + esc(x.hook_spoken) + '</div>'
    + sig
    + (x.why_it_works ? '<div class="why">💡 ' + esc(x.why_it_works) + '</div>' : '')
    + (s ? '<ol class="s">' + s + '</ol>' : '')
    + fixes
    + (x.cta ? '<div class="why" style="background:var(--amber-soft);border-color:#E8D9BC">🎯 ' + esc(x.cta) + '</div>' : '')
    + '<div class="tags"><span class="t g">' + esc(AUD[x.audience] || x.audience) + '</span>'
    + '<span class="t">' + esc(TRG[x.trigger_kind] || '') + '</span>'
    + '<span class="t">' + esc(VT[x.video_type] || '') + '</span>'
    + (st === 'posted' ? '<span class="t ok">🚀 ' + (x.views || 0) + ' مشاهدة</span>' : '')
    + (st === 'filmed' ? '<span class="t">🎥 مصوّر</span>' : '')
    + '</div>'
    + '<div class="acts"><button data-a="copy">📋 انسخ</button>'
    + (st !== 'posted' ? '<button data-a="filmed">🎥 صوّرته</button>' : '')
    + (st !== 'posted' ? '<button data-a="posted" class="main">🚀 نشرته</button>' : '')
    + (st === 'posted' ? '<div class="vin"><input type="number" inputmode="numeric" placeholder="كم مشاهدة؟" data-v>'
      + '<button data-a="views" class="main">احفظ</button></div>' : '')
    + '</div></div>';
}
function sigCard(s){
  return '<div class="sg' + (s.family === 'external' ? ' ext' : '') + '" data-sid="' + esc(s.sid) + '">'
    + '<div class="f">' + esc(s.fact) + '</div>'
    + (s.detail ? '<div class="d">' + esc(s.detail) + '</div>' : '')
    + '<div class="tags" style="margin-top:9px"><span class="t g">' + esc(SRC[s.source] || s.source) + '</span>'
    + (s.is_hot ? '<span class="t hot">🔥 طازج</span>' : '')
    + (s.as_of ? '<span class="t">' + esc(s.as_of) + '</span>' : '')
    + (s.url ? '<a class="t" href="' + esc(s.url) + '" target="_blank" rel="noopener">المصدر ↗</a>' : '')
    + '</div>'
    + '<div class="acts"><button data-a="siggen" class="main">✨ سوّها فكرة</button></div></div>';
}
function render(r){
  document.getElementById('day').textContent = r.day || '';
  document.getElementById('filters').innerHTML =
    (V === 'signals') ? '' : chipRow(r.facets || {});
  var el = document.getElementById('list');
  if (V === 'signals'){
    el.innerHTML = (r.signals || []).map(sigCard).join('')
      || '<div class="empty">ما فيه إشارات — أرسل «إشارات» بالديسكورد عشان يحدّثها</div>';
    return;
  }
  var cards = r.cards || [];
  el.innerHTML = cards.map(card).join('') || '<div class="empty">'
    + (V === 'posted' ? 'ما سجّلت أي فيديو منشور بعد — كل ما تسجّل، الترتيب يصير أذكى'
       : 'ما فيه أفكار هنا — جرّب فلتر ثاني أو أرسل «أفكار» بالديسكورد') + '</div>';
}
document.getElementById('views').addEventListener('click', function(e){
  var b = e.target.closest('.c');
  if (!b){ return; }
  V = b.getAttribute('data-v'); F = {};
  document.querySelectorAll('#views .c').forEach(function(c){ c.classList.toggle('on', c === b); });
  history.replaceState(null, '', BASE + '?v=' + V);
  load();
});
document.getElementById('filters').addEventListener('click', function(e){
  var b = e.target.closest('.c');
  if (!b){ return; }
  var k = b.getAttribute('data-f');
  if (k === 'clear'){ F = {}; }
  else {
    var v = b.getAttribute('data-fv');
    if (F[k] === v){ delete F[k]; } else { F[k] = v; }
  }
  load();
});
function copyCard(x){
  var L = ['🎬 ' + x.visual_title];
  if (x.visual_sub){ L.push(x.visual_sub); }
  L.push('', '🎤 ' + x.hook_spoken, '');
  if (x.signal_text){ L.push('📌 ' + x.signal_text, ''); }
  (x.script || []).forEach(function(b, i){ L.push((i + 1) + '. ' + b); });
  if (x.cta){ L.push('', '🎯 ' + x.cta); }
  var txt = L.join(NL);
  if (navigator.clipboard){
    navigator.clipboard.writeText(txt).then(function(){ toast('انسخ ✅'); },
      function(){ toast('ما قدرت أنسخ'); });
  } else { toast('ما قدرت أنسخ'); }
}
function act(body){
  return fetch(BASE + '/act', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)})
    .then(function(r){ return r.json(); });
}
document.getElementById('list').addEventListener('click', function(e){
  var btn = e.target.closest('button');
  if (!btn){ return; }
  var a = btn.getAttribute('data-a');
  var sgEl = e.target.closest('[data-sid]');
  if (a === 'siggen' && sgEl){
    btn.disabled = true; btn.textContent = 'يفكّر…';
    act({do:'siggen', sid: sgEl.getAttribute('data-sid')}).then(function(r){
      if (r.ok){ toast('طلعت ' + r.n + ' فكرة 💡'); V = 'ideas';
        document.querySelectorAll('#views .c').forEach(function(c){
          c.classList.toggle('on', c.getAttribute('data-v') === 'ideas'); });
        load();
      } else { toast(r.error || 'ما زبطت'); btn.disabled = false; btn.textContent = '✨ سوّها فكرة'; }
    });
    return;
  }
  var el = e.target.closest('[data-id]');
  if (!el){ return; }
  var id = parseInt(el.getAttribute('data-id'), 10);
  var x = (DATA.cards || []).filter(function(c){ return c.id === id; })[0] || {};
  if (a === 'copy'){ copyCard(x); return; }
  if (a === 'views'){
    var inp = el.querySelector('[data-v]');
    var n = parseInt((inp && inp.value) || '0', 10) || 0;
    act({do:'status', id: id, status:'posted', views: n}).then(function(){
      toast('انحفظ 📊 — الترتيب صار أذكى'); load();
    });
    return;
  }
  if (a === 'filmed' || a === 'posted'){
    act({do:'status', id: id, status: a}).then(function(){
      toast(a === 'posted' ? 'سجّلته 🚀 — لا تنسى تكتب المشاهدات' : 'سجّلته 🎥'); load();
    });
  }
});
load();
</script>
</body>
</html>"""


# ---------------- aiohttp handlers ----------------

DENY_HTML = ("<!doctype html><meta charset='utf-8'>"
             "<div dir='rtl' style='font:600 18px system-ui;padding:40px;text-align:center'>"
             "الرابط مو صحيح أو انتهى.</div>")


def _deny():
    return HOST.web.Response(text=DENY_HTML, content_type="text/html", status=403)


async def page(request):
    if not token_ok(request):
        return _deny()
    return HOST.web.Response(text=MOBILE_HTML, content_type="text/html")


async def api_feed(request):
    if not token_ok(request):
        return HOST.json_response({"ok": False, "error": "رابط غير صحيح"}, 403)
    q = request.query
    data = feed(q.get("v") or "today",
                {"audience": q.get("audience"), "family": q.get("family"),
                 "trigger": q.get("trigger"), "format": q.get("format")})
    # facets come from the UNFILTERED view so a chip never disappears once tapped
    base = feed(q.get("v") or "today", {})
    data["facets"] = facets(base.get("cards") or [])
    data["day"] = _today()
    data["ok"] = True
    data.pop("stats", None)
    return HOST.json_response(data)


async def api_act(request):
    if not token_ok(request):
        return HOST.json_response({"ok": False, "error": "رابط غير صحيح"}, 403)
    try:
        d = await request.json()
    except Exception:
        d = {}
    what = str((d or {}).get("do") or "")
    if what == "status":
        iid = d.get("id")
        status = str(d.get("status") or "")
        if not iid or status not in ("new", "shortlisted", "filmed", "posted", "rejected"):
            return HOST.json_response({"ok": False, "error": "طلب غير صحيح"}, 200)
        views = d.get("views")
        db.set_idea_status(int(iid), status,
                           views=int(views) if views not in (None, "") else None)
        return HOST.json_response({"ok": True})
    if what == "siggen":
        import asyncio
        from . import ideas as ideas_mod
        sid = str(d.get("sid") or "")
        if not sid:
            return HOST.json_response({"ok": False, "error": "إشارة غير معروفة"}, 200)
        cards = await asyncio.to_thread(ideas_mod.generate_for_signal, sid)
        if not cards:
            return HOST.json_response(
                {"ok": False, "error": "ما طلعت أفكار من هالإشارة"}, 200)
        return HOST.json_response({"ok": True, "n": len(cards)})
    return HOST.json_response({"ok": False, "error": "أمر غير معروف"}, 200)


def register(app):
    app.router.add_get("/s/{token}", page)
    app.router.add_get("/s/{token}/feed", api_feed)
    app.router.add_post("/s/{token}/act", api_act)
