# -*- coding: utf-8 -*-
"""
watchdog.routes — API + the standalone /watchdog page: the phone-first LIVE report
(Discord is only the alarm; this page is where the owner actually reads while walking)
plus the code-mode settings section.

Reads need dash auth; the code-mode WRITE re-checks role (admin/ops) exactly like
schedule.routes. The page string has the SAME backslash trap as DASHBOARD_HTML:
normal triple-quoted string → it contains NO backslashes at all (real newlines,
event delegation, no regex literals, no inline-onclick quote building).
"""

import traceback

from . import db, engine  # noqa: F401
from .host import HOST

EDIT_ROLES = ("admin", "ops")


def _can_edit(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in EDIT_ROLES
    except Exception:
        return False


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
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _safe_public(fn):
    """PUBLIC read wrapper — NO auth (same pattern as the /team-calendar share link, owner's
    explicit call 2026-07-05: anyone with the URL reads the report). WRITES stay double-gated."""
    async def _w(request):
        try:
            return await fn(request)
        except Exception:
            traceback.print_exc()
            return HOST.json_response(
                {"ok": False, "error": "صار خطأ مؤقت — حدّث الصفحة وجرّب مرة ثانية"}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ---------------- API ----------------

def _snapshot():
    snap = HOST.last_snapshot
    if not snap and HOST.load_json:
        try:
            snap = HOST.load_json("watchdog_snapshot.json", {})
        except Exception:
            snap = {}
    return snap or {}


async def api_status(request):
    """Latest snapshot (live memory, falls back to the persisted copy after a restart)."""
    return HOST.json_response({"ok": True, "snapshot": _snapshot()})


async def api_code_mode_get(request):
    listings = {}
    try:
        listings = HOST.listings() or {}
    except Exception:
        pass
    modes = db.all_code_modes()
    rows = [{"lid": str(lid), "name": name, "mode": modes.get(str(lid), "auto")}
            for lid, name in sorted(listings.items(), key=lambda x: str(x[1]))]
    return HOST.json_response({"ok": True, "rows": rows,
                               "manual_n": sum(1 for r in rows if r["mode"] == "manual"),
                               "can_edit": _can_edit(request)})


async def api_code_mode_set(request):
    if not _can_edit(request):
        return HOST.json_response({"ok": False, "error": "غير مصرّح لك بالتعديل"}, 403)
    d = await _body(request)
    lid = str(d.get("lid") or "").strip()
    mode = str(d.get("mode") or "").strip()
    if not lid or mode not in ("auto", "manual"):
        return HOST.json_response({"ok": False, "error": "bad lid/mode"}, 200)
    db.set_code_mode(lid, mode, by=str(d.get("by") or ""))
    return HOST.json_response({"ok": True, "lid": lid, "mode": db.code_mode(lid),
                               "manual_n": len(db.manual_listing_ids())})


# ---------------- the /watchdog page ----------------
# NO BACKSLASHES anywhere inside this string (trap: normal triple-quoted string).

WATCHDOG_PAGE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>الرقيب — عوجا</title>
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
  .wrap{max-width:660px;margin:0 auto;padding:14px 14px 80px}

  .hero{position:sticky;top:10px;z-index:50;border-radius:var(--r);padding:16px 18px;
    box-shadow:var(--sh);border:1px solid var(--border);margin-bottom:14px;
    display:flex;align-items:center;justify-content:space-between;gap:12px}
  .hero.green{background:var(--green-soft);border-color:#CBDFD1}
  .hero.gold{background:var(--amber-soft);border-color:#E8D9BC}
  .hero.red{background:var(--red-soft);border-color:#EBCCCC}
  .hero .verdict{font-size:21px;font-weight:800;color:var(--ink)}
  .hero .when{font-size:13px;color:var(--muted);font-weight:500}
  .hero .dot{width:16px;height:16px;border-radius:50%;flex:none;margin-inline-start:2px}
  .hero.green .dot{background:var(--green)} .hero.gold .dot{background:var(--amber)}
  .hero.red .dot{background:var(--red);animation:pulse 1.6s var(--ease) infinite}
  @keyframes pulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.25);opacity:.7}}

  .chips{display:flex;gap:8px;overflow-x:auto;padding:2px 0 12px;scrollbar-width:none}
  .chips::-webkit-scrollbar{display:none}
  .chip{flex:none;background:var(--panel);border:1px solid var(--border);border-radius:999px;
    padding:8px 14px;font-size:14px;font-weight:700;color:var(--ink);cursor:pointer}
  .chip b{font-family:var(--num);font-size:15px}
  .chip.alert{background:var(--red-soft);border-color:#EBCCCC;color:var(--red)}

  section{margin:0 0 18px}
  h2{font-size:20px;font-weight:800;color:var(--ink);margin:0 0 10px;display:flex;
    align-items:center;gap:8px}
  h2 .count{font-family:var(--num);font-size:14px;font-weight:800;background:var(--gold-soft);
    color:var(--ink);border-radius:999px;padding:2px 11px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r-sm);
    padding:12px 14px;margin-bottom:8px;box-shadow:var(--sh)}
  .card.bad{border-inline-start:5px solid var(--red)}
  .card.warn{border-inline-start:5px solid var(--amber)}
  .card.ok{border-inline-start:5px solid var(--green)}
  .who{font-size:17px;font-weight:800;color:var(--ink)}
  .who .unit{font-weight:700;color:var(--gold);font-size:15px}
  .meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
  .tag{font-size:13px;font-weight:700;border-radius:8px;padding:3px 9px;background:var(--bg);
    border:1px solid var(--border);color:var(--body)}
  .tag.bad{background:var(--red-soft);color:var(--red);border-color:#EBCCCC}
  .tag.good{background:var(--green-soft);color:var(--green);border-color:#CBDFD1}
  .tag.amber{background:var(--amber-soft);color:var(--amber);border-color:#E8D9BC}
  .tag.person{background:var(--gold-soft);border-color:#E4D6B8}
  .age{font-family:var(--num);font-weight:800}
  .empty{color:var(--muted);font-size:15px;padding:10px 4px}
  .foot{color:var(--muted);font-size:13px;text-align:center;padding:20px 0}

  .cov{display:flex;flex-wrap:wrap;gap:8px}
  .cov .card{flex:1 1 45%;margin:0;display:flex;justify-content:space-between;align-items:center}

  input.search{width:100%;padding:12px 14px;font:inherit;font-size:16px;border:1px solid var(--border);
    border-radius:var(--r-sm);background:var(--panel);color:var(--body);margin-bottom:10px;outline:none}
  .seg{display:flex;border:1px solid var(--border);border-radius:999px;overflow:hidden;flex:none}
  .seg button{min-width:70px;min-height:44px;border:0;background:transparent;font:inherit;
    font-size:13px;font-weight:700;color:var(--muted);cursor:pointer;padding:0 12px}
  .seg button.on-auto{background:var(--gold-soft);color:var(--ink)}
  .seg button.on-manual{background:var(--red-soft);color:var(--red)}
  .rowline{display:flex;align-items:center;justify-content:space-between;gap:10px;
    background:var(--panel);border:1px solid var(--border);border-radius:var(--r-sm);
    padding:8px 12px;margin-bottom:6px}
  .rowline .nm{font-size:14px;font-weight:600;min-width:0;overflow:hidden;
    text-overflow:ellipsis;white-space:nowrap}
  .toast{position:fixed;bottom:18px;right:50%;transform:translateX(50%);background:var(--ink);
    color:#FAF7F1;padding:10px 18px;border-radius:999px;font-size:14px;opacity:0;
    pointer-events:none;transition:opacity .25s var(--ease);z-index:99}
  .toast.show{opacity:1}
  details.settings{margin-top:26px}
  details.settings summary{font-size:17px;font-weight:800;color:var(--ink);cursor:pointer;
    padding:10px 0;list-style-position:inside}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important;animation:none !important} }
</style>
</head>
<body>
<div class="wrap">
  <div class="hero green" id="hero">
    <div>
      <div class="verdict" id="verdict">جاري التحميل…</div>
      <div class="when" id="when"></div>
    </div>
    <div class="dot"></div>
  </div>
  <div class="chips" id="chips"></div>
  <div id="report"><div class="empty">لحظة… نجيب آخر فحص</div></div>
  <details class="settings" id="settings">
    <summary>⚙️ إعدادات الأكواد (تلقائي / يدوي)</summary>
    <p class="empty">«يدوي» = الرقيب يتأكد قبل كل وصول أن أحد أرسل الكود، وينبّه إذا ما انرسل.</p>
    <input class="search" id="q" placeholder="ابحث باسم الشقة…" autocomplete="off">
    <div id="codes"><div class="empty">جاري التحميل…</div></div>
  </details>
  <div class="foot" id="foot"></div>
</div>
<div class="toast" id="toast"></div>
<script>
var TOKEN = new URLSearchParams(location.search).get('token') || '';
var CODES = [];
var CAN_EDIT = false;

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
function ageLabel(m){
  m = Math.max(0, Math.round(m || 0));
  if (m < 60) return m + ' دقيقة';
  if (m < 2880) return Math.round(m / 60) + ' ساعة';
  return Math.round(m / 1440) + ' يوم';
}
function nightsLabel(n){
  n = Math.round(n || 0);
  if (n === 1) return 'ليلة';
  if (n === 2) return 'ليلتين';
  if (n >= 3 && n <= 10) return n + ' ليال';
  return n + ' ليلة';
}
function tag(cls, txt){ return '<span class="tag ' + cls + '">' + txt + '</span>'; }
function personTag(name){ return tag('person', '👤 ' + esc(name || 'غير معروف')); }

function chip(label, n, alert, anchor){
  return '<span class="chip' + (alert ? ' alert' : '') + '" data-go="' + anchor + '">'
    + label + ' <b>' + n + '</b></span>';
}

function renderReport(s){
  var LIVE_MAX = 2880;
  var escs = (s.escalations || []).filter(function(x){ return (x.age_min || 0) <= LIVE_MAX; });
  var pends = (s.pending || []).filter(function(x){ return (x.age_min || 0) <= LIVE_MAX; });
  var archived = ((s.escalations || []).length - escs.length) + ((s.pending || []).length - pends.length);
  escs.sort(function(a, b){ return (b.age_min || 0) - (a.age_min || 0); });
  pends.sort(function(a, b){ return (b.age_min || 0) - (a.age_min || 0); });
  var proms = s.promises || [];
  var arrs = s.arrivals || [];
  var deps = s.departures || [];
  var stale = s.cleaning_stale || [];
  var cov = s.coverage || {};
  var t = s.today || {};
  var cs = s.codes_summary || {};
  var errs = s.errors || [];

  var codeMissing = arrs.filter(function(a){ return a.code_mode === 'manual' && !a.code_found; }).length;
  var notReady = arrs.filter(function(a){ return a.cleaning_ok === false; }).length;
  var expired = proms.filter(function(p){ return p.expired; }).length;
  var critical = codeMissing + notReady + expired
    + escs.filter(function(x){ return (x.age_min || 0) >= 120; }).length;

  var hero = document.getElementById('hero');
  var color = critical ? 'red' : ((escs.length || pends.length || proms.length || stale.length || errs.length) ? 'gold' : 'green');
  hero.className = 'hero ' + color;
  document.getElementById('verdict').textContent =
    color === 'red' ? '🔴 يحتاج تدخل — ' + critical + ' حرجة'
    : color === 'gold' ? '🟡 فيه ملاحظات' : '🟢 كل شي تمام';
  document.getElementById('when').textContent = 'آخر فحص: ' + (s.generated_at || '—') + ' · يتحدث كل 30 دقيقة';

  document.getElementById('chips').innerHTML =
    chip('🏠 وصول', t.arr_n || 0, false, 'sec-arr')
    + chip('🚪 مغادرة', t.dep_n || 0, false, 'sec-dep')
    + chip('🔑 أكواد', (cs.sent || 0) + '/' + (cs.manual_total || 0), codeMissing > 0, 'sec-arr')
    + chip('📩 محادثات', escs.length + pends.length, escs.length > 0, 'sec-conv')
    + chip('🤝 وعود', proms.length, expired > 0, 'sec-prom')
    + chip('🧹 نظافة', stale.length, false, 'sec-clean')
    + chip('👥 التوزيع', (cov.working || []).length, false, 'sec-cov');

  var h = [];

  h.push('<section id="sec-arr"><h2>🏠 وصول اليوم <span class="count">' + arrs.length + '</span></h2>');
  if (!arrs.length) h.push('<div class="empty">ما فيه وصول قادم خلال الفترة</div>');
  arrs.forEach(function(a){
    var bad = (a.code_mode === 'manual' && !a.code_found) || a.cleaning_ok === false;
    var tags = [personTag(a.employee)];
    if (a.code_mode === 'manual'){
      if (a.code_found) tags.push(a.code_late ? tag('amber', '🔑 أرسل متأخر') : tag('good', '🔑 الكود مرسل'));
      else tags.push(tag('bad', '🔑 الكود ما انرسل'));
    } else tags.push(tag('', '🔑 تلقائي'));
    tags.push(a.cleaning_ok === false ? tag('bad', '🧹 مو جاهزة') : tag('good', '🧹 جاهزة'));
    tags.push(a.signed ? tag('good', '📄 العقد موقّع') : tag('amber', '📄 العقد غير موقّع'));
    if (a.nights) tags.push(tag('', nightsLabel(a.nights)));
    if (a.price) tags.push(tag('', Math.round(a.price) + ' ر.س'));
    if (a.open_tickets) tags.push(tag('amber', '🛠️ ' + a.open_tickets + ' تذكرة'));
    h.push('<div class="card ' + (bad ? 'bad' : 'ok') + '">'
      + '<div class="who"><span class="age">' + esc(a.time_label || '؟') + '</span> · '
      + esc(a.guest) + ' <span class="unit">— ' + esc(a.unit) + '</span></div>'
      + '<div class="meta">' + tags.join('') + '</div></div>');
  });
  h.push('</section>');

  h.push('<section id="sec-dep"><h2>🚪 مغادرات اليوم <span class="count">' + deps.length + '</span></h2>');
  if (!deps.length) h.push('<div class="empty">ما فيه مغادرات اليوم</div>');
  deps.forEach(function(d){
    h.push('<div class="card"><div class="who">' + esc(d.guest)
      + ' <span class="unit">— ' + esc(d.unit) + '</span></div>'
      + '<div class="meta">' + personTag(d.employee) + tag('', '🧹 تنظيف بعد الخروج') + '</div></div>');
  });
  h.push('</section>');

  h.push('<section id="sec-conv"><h2>📩 محادثات تحتاج الفريق <span class="count">' + (escs.length + pends.length) + '</span></h2>');
  if (!escs.length && !pends.length) h.push('<div class="empty">✅ ما فيه شي حي يحتاج تدخل</div>');
  escs.forEach(function(x){
    h.push('<div class="card ' + ((x.age_min || 0) >= 120 ? 'bad' : 'warn') + '">'
      + '<div class="who">📣 ' + esc(x.guest) + ' <span class="unit">— ' + esc(x.unit) + '</span></div>'
      + '<div class="meta">' + tag('bad', 'تصعيد بدون استلام من <span class="age">' + ageLabel(x.age_min) + '</span>')
      + (x.kind === 'booking' ? tag('good', 'حجز مؤكد') : (x.kind === 'inquiry' ? tag('amber', 'استفسار') : ''))
      + (x.n > 1 ? tag('', x.n + ' رسائل') : '') + '</div></div>');
  });
  pends.forEach(function(x){
    h.push('<div class="card warn"><div class="who">💬 ' + esc(x.guest)
      + ' <span class="unit">— ' + esc(x.unit) + '</span></div>'
      + '<div class="meta">' + tag('amber', 'رد ينتظر الاعتماد من <span class="age">' + ageLabel(x.age_min) + '</span>')
      + (x.n > 1 ? tag('', x.n + ' رسائل') : '') + '</div></div>');
  });
  if (archived) h.push('<div class="empty">🗄️ أرشيف قديم: ' + archived + ' — أقدم من يومين، ما يُحسب</div>');
  h.push('</section>');

  h.push('<section id="sec-prom"><h2>🤝 وعود متأخرة <span class="count">' + proms.length + '</span></h2>');
  if (!proms.length) h.push('<div class="empty">✅ ما فيه وعود متأخرة</div>');
  proms.forEach(function(p){
    h.push('<div class="card ' + (p.expired ? 'bad' : 'warn') + '">'
      + '<div class="who">' + esc(p.promised_by || 'غير معروف')
      + ' <span class="unit">— ' + esc(p.apartment || '') + '</span></div>'
      + '<div class="meta">' + (p.expired ? tag('bad', 'منتهي بدون تنفيذ')
        : tag('amber', 'متأخر <span class="age">' + Math.round(p.overdue_h || 0) + '</span> ساعة')) + '</div></div>');
  });
  h.push('</section>');

  h.push('<section id="sec-clean"><h2>🧹 نظافة متأخرة <span class="count">' + stale.length + '</span></h2>');
  if (!stale.length) h.push('<div class="empty">✅ ما فيه غرف تنظيف عالقة</div>');
  stale.forEach(function(c){
    h.push('<div class="card warn"><div class="who">' + esc(c.unit) + '</div>'
      + '<div class="meta">' + tag('amber', 'مفتوحة من <span class="age">'
      + ageLabel((c.opened_h || 0) * 60) + '</span> بدون تقرير') + '</div></div>');
  });
  h.push('</section>');

  h.push('<section id="sec-cov"><h2>👥 توزيع الموظفين اليوم</h2><div class="cov">');
  (cov.working || []).forEach(function(w){
    h.push('<div class="card"><span class="who">' + esc(w.emoji || '👤') + ' ' + esc(w.name)
      + '</span><span class="tag"><b class="age">' + (w.n || 0) + '</b> شقة</span></div>');
  });
  h.push('</div>');
  if ((cov.off_names || []).length) h.push('<div class="empty">🌙 إجازة اليوم: ' + esc(cov.off_names.join('، ')) + '</div>');
  if (cov.ok === false) h.push('<div class="empty">⚠️ التوزيع غير متوازن (فرق ' + (cov.imbalance || '؟') + ' شقق)</div>');
  h.push('</section>');

  if (errs.length){
    h.push('<section><h2>🔧 النظام</h2>');
    errs.forEach(function(e2){
      var why = (s.errors_detail || {})[e2] || '';
      h.push('<div class="card bad"><div class="who">⚪ تعذّر فحص: ' + esc(e2) + '</div>'
        + (why ? '<div class="meta">' + tag('', esc(why).slice(0, 160)) + '</div>' : '') + '</div>');
    });
    h.push('</section>');
  }

  document.getElementById('report').innerHTML = h.join('');
}

function renderCodes(){
  var q = (document.getElementById('q').value || '').trim();
  var list = document.getElementById('codes');
  var rows = CODES.filter(function(r){ return !q || (r.name || '').indexOf(q) >= 0; });
  if (!rows.length){ list.innerHTML = '<div class="empty">لا توجد شقق مطابقة</div>'; return; }
  list.innerHTML = rows.map(function(r){
    return '<div class="rowline" data-lid="' + r.lid + '">'
      + '<span class="nm">' + esc(r.name) + '</span>'
      + '<span class="seg">'
      + '<button type="button" data-mode="auto" class="' + (r.mode === 'auto' ? 'on-auto' : '') + '">تلقائي</button>'
      + '<button type="button" data-mode="manual" class="' + (r.mode === 'manual' ? 'on-manual' : '') + '">يدوي</button>'
      + '</span></div>';
  }).join('');
}

document.getElementById('codes').addEventListener('click', function(ev){
  var btn = ev.target.closest('button[data-mode]');
  if (!btn) return;
  if (!CAN_EDIT){ toast('غير مصرّح لك بالتعديل'); return; }
  var lid = btn.closest('.rowline').getAttribute('data-lid');
  api('/api/watchdog/code-mode', {method: 'POST', body: JSON.stringify({lid: lid, mode: btn.getAttribute('data-mode')})})
    .then(function(r){
      if (!r.ok){ toast(r.error || 'صار خطأ'); return; }
      var row = CODES.find(function(x){ return x.lid === r.lid; });
      if (row) row.mode = r.mode;
      renderCodes();
      toast('تم الحفظ ✅');
    })
    .catch(function(){ toast('تعذّر الحفظ — جرّب مرة ثانية'); });
});
document.getElementById('q').addEventListener('input', renderCodes);
document.getElementById('chips').addEventListener('click', function(ev){
  var c = ev.target.closest('.chip');
  if (!c) return;
  var el = document.getElementById(c.getAttribute('data-go'));
  if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
});

function refresh(){
  api('/api/watchdog/status').then(function(r){
    if (!r.ok){ document.getElementById('verdict').textContent = 'غير مصرّح — افتح الرابط المحفوظ عندك'; return; }
    if (!r.snapshot || !Object.keys(r.snapshot).length){
      document.getElementById('verdict').textContent = '⏳ أول فحص جاري…';
      return;
    }
    renderReport(r.snapshot);
    document.getElementById('foot').textContent = 'الرقيب التشغيلي — عوجا · الصفحة تتحدث تلقائياً كل دقيقة';
  }).catch(function(){
    document.getElementById('verdict').textContent = 'تعذّر التحميل — تأكد من الشبكة';
  });
}
refresh();
setInterval(refresh, 60000);
api('/api/watchdog/code-mode').then(function(r){
  if (r.ok){ CODES = r.rows || []; CAN_EDIT = !!r.can_edit; renderCodes(); }
});
</script>
</body>
</html>"""


async def handle_page(request):
    web = HOST.require("web")
    return web.Response(content_type="text/html", charset="utf-8", text=WATCHDOG_PAGE_HTML)


def register(app):
    # READ = PUBLIC (owner's call — share-link like /team-calendar); WRITE = login + role.
    app.router.add_get("/api/watchdog/status", _safe_public(api_status))
    app.router.add_get("/api/watchdog/code-mode", _safe_public(api_code_mode_get))
    app.router.add_post("/api/watchdog/code-mode", _safe(api_code_mode_set))
    app.router.add_get("/watchdog", handle_page)
