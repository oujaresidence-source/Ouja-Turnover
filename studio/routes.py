# -*- coding: utf-8 -*-
"""studio.routes — API + the standalone /studio page (Ouja Studio).

Everything is LOGIN-GATED (_safe → HOST.dash_auth): story cards contain real
operational situations — never public. The page string has the SAME backslash
trap as DASHBOARD_HTML: normal triple-quoted string → it contains NO backslashes
at all (real newlines, event delegation, no regex literals, no inline-onclick
quote building). esprima-parse every <script> block after edits."""

import traceback

from . import db, ideas as ideas_mod, mine  # noqa: F401
from .host import HOST


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def _safe(fn):
    async def _w(request):
        g = _guard(request)
        if g:
            return g
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response(
                {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ---------------- API ----------------

async def api_status(request):
    return HOST.json_response({"ok": True, "scan": mine.snapshot()})


async def api_scan(request):
    started = mine.start_scan_thread()
    return HOST.json_response({"ok": True, "started": started,
                               "scan": mine.snapshot()})


async def api_deep_scan(request):
    """v2 deep re-mine: clear weak legacy cards + cursor, then scan under the positive
    lens. Keeps posted/filmed cards. Owner-triggered only."""
    started = mine.start_scan_thread(deep=True)
    return HOST.json_response({"ok": True, "started": started, "deep": True,
                               "scan": mine.snapshot()})


async def api_stories(request):
    status = request.query.get("status") or None
    rows = db.stories(status=status)
    for r in rows:
        r["ideas_n"] = len(db.ideas_for_story(r["id"]))
    return HOST.json_response({"ok": True, "stories": rows})


async def api_story_status(request):
    d = await _body(request)
    sid, status = d.get("id"), str(d.get("status") or "")
    if not sid or status not in ("new", "used", "hidden"):
        return HOST.json_response({"ok": False, "error": "bad id/status"}, 200)
    db.set_story_status(int(sid), status)
    return HOST.json_response({"ok": True})


async def api_generate(request):
    d = await _body(request)
    sid = d.get("story_id")
    if not sid:
        return HOST.json_response({"ok": False, "error": "bad story_id"}, 200)
    import asyncio
    cards = await asyncio.to_thread(ideas_mod.generate_for_story, int(sid))
    if not cards:
        return HOST.json_response(
            {"ok": False, "error": "ما طلعت أفكار — جرّب مرة ثانية"}, 200)
    return HOST.json_response({"ok": True, "ideas": cards})


async def api_ideas(request):
    status = request.query.get("status") or None
    return HOST.json_response({"ok": True, "ideas": db.ideas(status=status)})


async def api_idea_status(request):
    d = await _body(request)
    iid, status = d.get("id"), str(d.get("status") or "")
    if not iid or status not in ("new", "shortlisted", "filmed", "posted", "rejected"):
        return HOST.json_response({"ok": False, "error": "bad id/status"}, 200)
    views = d.get("views")
    note = d.get("perf_note")
    db.set_idea_status(int(iid), status,
                       views=int(views) if views not in (None, "") else None,
                       perf_note=note if note is not None else None)
    return HOST.json_response({"ok": True})


# ---------------- the /studio page ----------------
# NO BACKSLASHES anywhere inside this string (trap: normal triple-quoted string).

STUDIO_PAGE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>استوديو عوجا — مصنع الأفكار</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@600;800&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#F1EDE6; --panel:#FAF7F1; --ink:#292925; --body:#33302B; --muted:#8F887C;
    --gold:#B29A6A; --gold-soft:#F0E8D8; --red:#B93A3A; --red-soft:#F6E3E3;
    --green:#3E7D4E; --green-soft:#E4EFE7; --amber:#A8762A; --amber-soft:#F5EBDA;
    --border:#E7DFD1; --r:18px; --r-sm:12px;
    --sh:0 1px 2px rgba(41,41,37,.05),0 12px 32px rgba(41,41,37,.08);
    --ease:cubic-bezier(0.23,1,0.32,1); --font:'Tajawal',-apple-system,system-ui,sans-serif;
    --num:'Inter',sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);
    line-height:1.6;font-size:17px}
  .wrap{max-width:660px;margin:0 auto;padding:14px 14px 90px}

  .hero{border-radius:var(--r);padding:16px 18px;box-shadow:var(--sh);
    border:1px solid var(--border);background:var(--panel);margin-bottom:12px}
  .hero h1{font-size:22px;font-weight:800;color:var(--ink);margin:0}
  .hero .sub{font-size:13px;color:var(--muted);font-weight:500}
  .hero .row{display:flex;align-items:center;justify-content:space-between;gap:12px}
  .scanbtn{min-height:44px;border:0;border-radius:999px;padding:0 20px;font:inherit;
    font-size:15px;font-weight:800;background:var(--ink);color:#FAF7F1;cursor:pointer;
    transition:transform .15s var(--ease),opacity .15s var(--ease)}
  .scanbtn:active{transform:scale(.97)}
  .scanbtn[disabled]{opacity:.5;cursor:default}
  .prog{font-size:13px;color:var(--muted);margin-top:8px;font-weight:500}
  .prog b{font-family:var(--num)}
  .bar{height:6px;border-radius:999px;background:var(--gold-soft);margin-top:6px;overflow:hidden}
  .bar i{display:block;height:100%;width:0%;background:var(--gold);border-radius:999px;
    transition:width .4s var(--ease)}

  .chips{display:flex;gap:8px;overflow-x:auto;padding:2px 0 12px;scrollbar-width:none}
  .chips::-webkit-scrollbar{display:none}
  .chip{flex:none;min-height:44px;display:inline-flex;align-items:center;gap:6px;
    background:var(--panel);border:1px solid var(--border);border-radius:999px;
    padding:0 16px;font:inherit;font-size:15px;font-weight:700;color:var(--muted);cursor:pointer;
    transition:transform .15s var(--ease)}
  .chip:active{transform:scale(.97)}
  .chip.on{background:var(--gold-soft);border-color:#E4D6B8;color:var(--ink)}
  .chip b{font-family:var(--num);font-size:14px}

  .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r-sm);
    padding:14px 16px;margin-bottom:10px;box-shadow:var(--sh)}
  .score{font-family:var(--num);font-weight:800;font-size:14px;border-radius:999px;
    padding:2px 11px;background:var(--gold-soft);color:var(--ink);flex:none}
  .score.hot{background:var(--red-soft);color:var(--red)}
  .ttl{font-size:18px;font-weight:800;color:var(--ink);margin:0 0 2px}
  .unit{font-size:13px;font-weight:700;color:var(--gold)}
  .sum{font-size:15px;margin:8px 0 0}
  .quote{border-inline-start:4px solid var(--gold);background:var(--bg);border-radius:8px;
    padding:6px 12px;margin:8px 0 0;font-size:14px;font-weight:500;color:var(--ink)}
  .meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
  .tag{font-size:13px;font-weight:700;border-radius:8px;padding:3px 9px;background:var(--bg);
    border:1px solid var(--border);color:var(--body)}
  .tag.gold{background:var(--gold-soft);border-color:#E4D6B8}
  .tag.green{background:var(--green-soft);color:var(--green);border-color:#CBDFD1}
  .tag.amber{background:var(--amber-soft);color:var(--amber);border-color:#E8D9BC}
  .tag.red{background:var(--red-soft);color:var(--red);border-color:#EBCCCC}

  .hookbox{background:var(--ink);color:#FAF7F1;border-radius:var(--r-sm);padding:16px 18px;
    text-align:center;margin:4px 0 10px}
  .hookbox .vt{font-size:20px;font-weight:800;line-height:1.4}
  .hookbox .vs{font-size:14px;font-weight:500;opacity:.85;margin-top:2px}
  .spoken{display:flex;gap:8px;align-items:baseline;background:var(--gold-soft);
    border-radius:8px;padding:8px 12px;margin-bottom:8px;font-size:15px;font-weight:700;
    color:var(--ink)}
  .spoken span{flex:none;font-size:12px;font-weight:800;color:var(--amber)}
  ol.script{margin:8px 0 0;padding-inline-start:20px;font-size:14px}
  ol.script li{margin-bottom:4px}
  .cta-line{font-size:14px;margin-top:8px;color:var(--ink)}
  .cta-line b{color:var(--amber)}
  .why{display:flex;gap:8px;align-items:baseline;background:var(--green-soft);
    border:1px solid #CBDFD1;border-radius:8px;padding:8px 12px;margin-top:8px;
    font-size:14px;font-weight:600;color:var(--ink)}
  .why span{flex:none;font-size:12px;font-weight:800;color:var(--green)}

  .acts{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
  .acts button{min-height:44px;border:1px solid var(--border);border-radius:999px;
    padding:0 16px;font:inherit;font-size:14px;font-weight:700;background:var(--bg);
    color:var(--ink);cursor:pointer;transition:transform .15s var(--ease)}
  .acts button:active{transform:scale(.97)}
  .acts button.main{background:var(--ink);color:#FAF7F1;border-color:var(--ink)}
  .acts button[disabled]{opacity:.5;cursor:default}

  .views-in{display:flex;gap:8px;margin-top:10px}
  .views-in input{flex:1;min-height:44px;padding:0 14px;font:inherit;font-size:16px;
    border:1px solid var(--border);border-radius:999px;background:var(--bg);
    color:var(--body);outline:none;font-family:var(--num)}

  .empty{color:var(--muted);font-size:15px;padding:18px 6px;text-align:center}
  .foot{color:var(--muted);font-size:13px;text-align:center;padding:20px 0}
  .toast{position:fixed;bottom:18px;right:50%;transform:translateX(50%);background:var(--ink);
    color:#FAF7F1;padding:10px 18px;border-radius:999px;font-size:14px;opacity:0;
    pointer-events:none;transition:opacity .25s var(--ease);z-index:99}
  .toast.show{opacity:1}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important;animation:none !important} }
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="row">
      <div>
        <h1>🎬 استوديو عوجا</h1>
        <div class="sub">قصص حقيقية من محادثات الضيوف → أفكار فيديو جاهزة</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">
        <button class="scanbtn" id="scanbtn">امسح الجديد</button>
        <button class="scanbtn" id="deepbtn" style="background:var(--gold);color:var(--ink)">🔄 مسح عميق</button>
      </div>
    </div>
    <div class="prog" id="prog"></div>
    <div class="bar" id="bar" hidden><i id="barfill"></i></div>
  </div>

  <div class="chips" id="tabs">
    <button class="chip on" data-tab="ideas">💡 أفكار <b id="n-ideas">0</b></button>
    <button class="chip" data-tab="stories">📖 قصص <b id="n-stories">0</b></button>
    <button class="chip" data-tab="posted">🚀 منشور <b id="n-posted">0</b></button>
  </div>

  <div id="list"><div class="empty">لحظة…</div></div>
  <div class="foot">استوديو عوجا · الأفكار من محادثات حقيقية — بدون أسماء ضيوف</div>
</div>
<div class="toast" id="toast"></div>
<script>
var TOKEN = new URLSearchParams(location.search).get('token') || '';
var TAB = 'ideas';
var STORIES = [], IDEAS = [];
var NL = String.fromCharCode(10);

var TYPE_AR = {hero_save:'إنقاذ الموقف', transformation:'تحوّل', transparency_numbers:'أرقام وشفافية',
  day_in_life:'كواليس اليوم', hospitality_wow:'لمسة ضيافة', weird_delight:'طلب طريف',
  heartwarming:'موقف إنساني', loyal_return:'ضيف رجع', operational_craft:'سر الصنعة', other:'موقف'};
var TRG_AR = {curiosity:'فضول', loss:'خسارة', identity:'هوية', provocation:'استفزاز', emotion:'مشاعر'};
var AUD_AR = {niche:'للملّاك 🏠', escape:'جمهور عام 🌍'};
var VT_AR = {talking:'توك للكاميرا', tour:'جولة', before_after:'قبل/بعد',
  story_voiceover:'سرد بصوت', onsite:'من الموقع'};

function api(path, opts){
  opts = opts || {};
  opts.headers = Object.assign({'X-Token': TOKEN, 'Content-Type': 'application/json'}, opts.headers || {});
  return fetch(path, opts).then(function(r){ return r.json(); });
}
function esc(s){
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function toast(msg){
  var t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2200);
}
function tag(cls, txt){ return '<span class="tag ' + cls + '">' + txt + '</span>'; }

// ---------- scan ----------
function renderScan(s){
  var btn = document.getElementById('scanbtn');
  var deep = document.getElementById('deepbtn');
  var prog = document.getElementById('prog');
  var bar = document.getElementById('bar');
  if (deep){ deep.disabled = !!s.running; }
  if (s.running){
    btn.disabled = true; btn.textContent = 'يمسح…'; bar.hidden = false;
    var pct = Math.min(100, Math.round(100 * (s.qualified || 0) / (s.target || 300)));
    document.getElementById('barfill').style.width = pct + '%';
    prog.textContent = 'قرأ ' + (s.scanned || 0) + ' محادثة · ' + (s.qualified || 0)
      + ' حقيقية · ' + (s.stories || 0) + ' قصة 📖 · ' + (s.blocked || 0)
      + ' مستبعدة للبراند 🚫 · آخر شقة: ' + (s.last_unit || '—');
    setTimeout(loadStatus, 4000);
  } else {
    btn.disabled = false; btn.textContent = 'امسح الجديد'; bar.hidden = true;
    var c = s.counts || {};
    var done = 0, k;
    for (k in c){ done += c[k]; }
    prog.textContent = done ? ('في الأرشيف: ' + done + ' محادثة مفحوصة · '
      + (c.story || 0) + ' قصة · ' + (c.blocked_brand || 0) + ' مستبعدة للبراند — «امسح الجديد» يكمّل من وين وقف، و«مسح عميق» يعيد الفحص بالعدسة الجديدة')
      : 'أول مسح ياخذ وقت ويقرأ آخر ٢٠٠٠ محادثة حقيقية بعدسة إيجابية';
    if (s.error){ prog.textContent = 'خطأ: ' + s.error; }
  }
}
function loadStatus(){
  api('/api/studio/status').then(function(r){
    if (r.ok){ renderScan(r.scan || {}); }
  });
}
document.getElementById('scanbtn').addEventListener('click', function(){
  api('/api/studio/scan', {method:'POST', body:'{}'}).then(function(r){
    if (r.ok){ toast(r.started ? 'بدأ المسح 🔍' : 'فيه مسح شغّال'); renderScan(r.scan || {}); }
  });
});
document.getElementById('deepbtn').addEventListener('click', function(){
  if (!confirm('المسح العميق يعيد فحص آخر ٢٠٠٠ محادثة بالعدسة الإيجابية الجديدة، ويمسح البطاقات القديمة الضعيفة (يبقي المنشور والمصوّر). يمكن ياخذ وقت. نبدأ؟')){ return; }
  api('/api/studio/deep-scan', {method:'POST', body:'{}'}).then(function(r){
    if (r.ok){ toast(r.started ? 'بدأ المسح العميق 🔄' : 'فيه مسح شغّال'); renderScan(r.scan || {}); loadAll(); }
  });
});

// ---------- cards ----------
function ideaCard(x){
  var st = x.status || 'new';
  var script = (x.script || []).map(function(b){ return '<li>' + esc(b) + '</li>'; }).join('');
  var stTag = st === 'posted' ? tag('green', '🚀 منشور · ' + (x.views || 0) + ' مشاهدة')
    : st === 'filmed' ? tag('amber', '🎥 مصوّر') : st === 'shortlisted' ? tag('gold', '⭐ مرشّح') : '';
  return '<div class="card" data-idea="' + x.id + '">'
    + '<div class="hookbox"><div class="vt">' + esc(x.visual_title) + '</div>'
    + (x.visual_sub ? '<div class="vs">' + esc(x.visual_sub) + '</div>' : '') + '</div>'
    + '<div class="spoken"><span>🎤 أول ما تقول</span>' + esc(x.hook_spoken) + '</div>'
    + (x.angle ? '<div class="sum">' + esc(x.angle) + '</div>' : '')
    + (x.why_it_works ? '<div class="why"><span>💡 ليش بيشتغل</span>' + esc(x.why_it_works) + '</div>' : '')
    + (script ? '<ol class="script">' + script + '</ol>' : '')
    + (x.cta ? '<div class="cta-line"><b>الختام:</b> ' + esc(x.cta) + '</div>' : '')
    + '<div class="meta">' + tag('gold', AUD_AR[x.audience] || x.audience)
    + tag('', TRG_AR[x.trigger_kind || x.trigger] || 'فضول') + tag('', VT_AR[x.video_type] || x.video_type)
    + stTag + '</div>'
    + '<div class="acts">'
    + '<button data-act="copy">📋 نسخ السكربت</button>'
    + (st === 'new' || st === 'shortlisted' ? '<button data-act="filmed" class="main">🎥 صوّرته</button>' : '')
    + (st !== 'posted' ? '<button data-act="posted">🚀 نشرته</button>' : '')
    + (st === 'posted' ? '<div class="views-in"><input type="number" inputmode="numeric" placeholder="كم مشاهدة؟" data-views>'
      + '<button data-act="views">حفظ</button></div>' : '')
    + (st === 'new' ? '<button data-act="rejected">🗑</button>' : '')
    + '</div></div>';
}
function storyCard(s){
  var quotes = (s.quotes || []).map(function(q){ return '<div class="quote">«' + esc(q) + '»</div>'; }).join('');
  var beats = (s.beats || []).map(function(b){ return '<li>' + esc(b) + '</li>'; }).join('');
  return '<div class="card" data-story="' + s.id + '">'
    + '<div style="display:flex;justify-content:space-between;gap:10px;align-items:start">'
    + '<div><div class="ttl">' + esc(s.title) + '</div>'
    + '<span class="unit">' + esc(s.unit || '') + '</span></div>'
    + '<span class="score' + (s.score >= 8 ? ' hot' : '') + '">' + s.score + '/10</span></div>'
    + '<div class="sum">' + esc(s.summary) + '</div>'
    + (beats ? '<ol class="script">' + beats + '</ol>' : '') + quotes
    + '<div class="meta">' + tag('gold', TYPE_AR[s.story_type] || 'موقف')
    + (s.emotion ? tag('', esc(s.emotion)) : '')
    + (s.ideas_n ? tag('green', '💡 ' + s.ideas_n + ' فكرة') : '') + '</div>'
    + '<div class="acts">'
    + '<button data-act="gen" class="main">✨ ولّد أفكار فيديو</button>'
    + '<button data-act="hide">إخفاء</button>'
    + '</div></div>';
}

function render(){
  var el = document.getElementById('list');
  var html = '';
  if (TAB === 'stories'){
    var vis = STORIES.filter(function(s){ return s.status !== 'hidden'; });
    html = vis.map(storyCard).join('') ||
      '<div class="empty">ما فيه قصص بعد — اضغط «امسح المحادثات» فوق 👆</div>';
  } else if (TAB === 'posted'){
    var posted = IDEAS.filter(function(x){ return x.status === 'posted' || x.status === 'filmed'; });
    html = posted.map(ideaCard).join('') ||
      '<div class="empty">إذا صوّرت أو نشرت فكرة علّمها — عشان نتعلم وش يشتغل</div>';
  } else {
    var fresh = IDEAS.filter(function(x){ return x.status === 'new' || x.status === 'shortlisted'; });
    html = fresh.map(ideaCard).join('') ||
      '<div class="empty">ما فيه أفكار بعد — روح لتبويب «قصص» واضغط «ولّد أفكار» على قصة تعجبك</div>';
  }
  el.innerHTML = html;
  document.getElementById('n-ideas').textContent =
    IDEAS.filter(function(x){ return x.status === 'new' || x.status === 'shortlisted'; }).length;
  document.getElementById('n-stories').textContent =
    STORIES.filter(function(s){ return s.status !== 'hidden'; }).length;
  document.getElementById('n-posted').textContent =
    IDEAS.filter(function(x){ return x.status === 'posted' || x.status === 'filmed'; }).length;
}

function loadAll(){
  Promise.all([api('/api/studio/stories'), api('/api/studio/ideas')]).then(function(rs){
    if (rs[0].ok){ STORIES = rs[0].stories || []; }
    if (rs[1].ok){ IDEAS = rs[1].ideas || []; }
    render();
  });
}

// ---------- actions (event delegation — no inline onclick) ----------
document.getElementById('tabs').addEventListener('click', function(e){
  var b = e.target.closest('.chip');
  if (!b){ return; }
  TAB = b.getAttribute('data-tab');
  document.querySelectorAll('.chip').forEach(function(c){ c.classList.toggle('on', c === b); });
  render();
});

function copyIdea(x){
  var lines = ['🎬 ' + x.visual_title, (x.visual_sub || ''), '',
    '🎤 الهوك: ' + x.hook_spoken, ''];
  if (x.why_it_works){ lines.push('💡 ليش بيشتغل: ' + x.why_it_works, ''); }
  (x.script || []).forEach(function(b, i){ lines.push((i + 1) + '. ' + b); });
  if (x.cta){ lines.push('', 'الختام: ' + x.cta); }
  navigator.clipboard.writeText(lines.join(NL)).then(function(){ toast('انسخ ✅'); },
    function(){ toast('ما قدرت أنسخ'); });
}

document.getElementById('list').addEventListener('click', function(e){
  var btn = e.target.closest('button');
  if (!btn){ return; }
  var act = btn.getAttribute('data-act');
  var ideaEl = e.target.closest('[data-idea]');
  var storyEl = e.target.closest('[data-story]');
  if (storyEl){
    var sid = parseInt(storyEl.getAttribute('data-story'), 10);
    if (act === 'gen'){
      btn.disabled = true; btn.textContent = 'يفكّر… ٢٠-٣٠ ثانية';
      api('/api/studio/generate', {method:'POST', body: JSON.stringify({story_id: sid})})
        .then(function(r){
          if (r.ok){ toast('طلعت ' + r.ideas.length + ' فكرة 💡'); loadAll(); }
          else { toast(r.error || 'ما زبطت'); btn.disabled = false; btn.textContent = '✨ ولّد أفكار فيديو'; }
        });
    } else if (act === 'hide'){
      api('/api/studio/story-status', {method:'POST', body: JSON.stringify({id: sid, status:'hidden'})})
        .then(function(){ loadAll(); });
    }
    return;
  }
  if (!ideaEl){ return; }
  var iid = parseInt(ideaEl.getAttribute('data-idea'), 10);
  var idea = IDEAS.filter(function(x){ return x.id === iid; })[0] || {};
  if (act === 'copy'){ copyIdea(idea); return; }
  if (act === 'views'){
    var inp = ideaEl.querySelector('[data-views]');
    var v = parseInt((inp && inp.value) || '0', 10) || 0;
    api('/api/studio/idea-status', {method:'POST',
      body: JSON.stringify({id: iid, status:'posted', views: v})})
      .then(function(){ toast('انحفظ 📊'); loadAll(); });
    return;
  }
  if (act === 'filmed' || act === 'posted' || act === 'rejected'){
    api('/api/studio/idea-status', {method:'POST', body: JSON.stringify({id: iid, status: act})})
      .then(function(){ loadAll(); });
  }
});

loadStatus();
loadAll();
</script>
</body>
</html>"""


async def page(request):
    return HOST.web.Response(text=STUDIO_PAGE_HTML, content_type="text/html")


def register(app):
    app.router.add_get("/studio", page)
    app.router.add_get("/api/studio/status", _safe(api_status))
    app.router.add_post("/api/studio/scan", _safe(api_scan))
    app.router.add_post("/api/studio/deep-scan", _safe(api_deep_scan))
    app.router.add_get("/api/studio/stories", _safe(api_stories))
    app.router.add_post("/api/studio/story-status", _safe(api_story_status))
    app.router.add_post("/api/studio/generate", _safe(api_generate))
    app.router.add_get("/api/studio/ideas", _safe(api_ideas))
    app.router.add_post("/api/studio/idea-status", _safe(api_idea_status))
