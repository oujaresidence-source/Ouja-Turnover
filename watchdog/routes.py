# -*- coding: utf-8 -*-
"""
watchdog.routes — API + the standalone /watchdog code-mode editor page.

Reads need dash auth; the code-mode WRITE re-checks role (admin/ops) exactly like
schedule.routes. The page string has the SAME backslash trap as DASHBOARD_HTML:
normal triple-quoted string → it contains NO backslashes at all (real newlines,
event delegation, no regex literals, no inline-onclick quote building).
"""

import traceback

from . import db, engine  # noqa: F401  (engine imported for parity/debug use)
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


async def _body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ---------------- API ----------------

async def api_status(request):
    """Latest snapshot the bot cycle computed (read-only mirror for the dashboard)."""
    snap = HOST.last_snapshot or {}
    return HOST.json_response({"ok": True, "snapshot": snap})


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


# ---------------- the /watchdog editor page ----------------
# NO BACKSLASHES anywhere inside this string (trap: normal triple-quoted string).

WATCHDOG_PAGE_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>الرقيب — أكواد الدخول</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&family=Inter:wght@600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#F1EDE6; --panel:#FAF7F1; --ink:#292925; --body:#33302B; --muted:#9C958A;
    --gold:#B29A6A; --gold-soft:#F0E8D8; --maroon:#8B3748; --maroon-soft:#F3E2E4; --border:#E7DFD1;
    --r:16px; --r-sm:11px; --sh:0 1px 2px rgba(41,41,37,.04),0 10px 30px rgba(41,41,37,.07);
    --ease:cubic-bezier(0.23,1,0.32,1); --font:'Tajawal',-apple-system,system-ui,sans-serif;
    --num:'Inter',sans-serif;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);line-height:1.55}
  .wrap{max-width:640px;margin:0 auto;padding:18px 14px 90px}
  header{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:6px}
  h1{font-size:20px;font-weight:800;color:var(--ink);margin:0}
  .sub{color:var(--muted);font-size:13px;margin:0 0 14px}
  .stat{background:var(--gold-soft);border:1px solid var(--border);border-radius:var(--r-sm);
        padding:4px 12px;font-size:13px;font-weight:700;color:var(--ink);white-space:nowrap}
  input.search{width:100%;padding:12px 14px;font:inherit;font-size:15px;border:1px solid var(--border);
        border-radius:var(--r-sm);background:var(--panel);color:var(--body);margin-bottom:12px;outline:none}
  input.search:focus{border-color:var(--gold)}
  .row{display:flex;align-items:center;justify-content:space-between;gap:10px;background:var(--panel);
       border:1px solid var(--border);border-radius:var(--r-sm);padding:10px 12px;margin-bottom:8px;
       box-shadow:var(--sh)}
  .nm{font-size:14px;font-weight:500;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .seg{display:flex;border:1px solid var(--border);border-radius:999px;overflow:hidden;flex:none}
  .seg button{min-width:74px;min-height:44px;border:0;background:transparent;font:inherit;font-size:13px;
       font-weight:700;color:var(--muted);cursor:pointer;padding:0 12px;transition:background .18s var(--ease),color .18s var(--ease)}
  .seg button.on-auto{background:var(--gold-soft);color:var(--ink)}
  .seg button.on-manual{background:var(--maroon-soft);color:var(--maroon)}
  .seg button:active{transform:scale(.97)}
  .empty{color:var(--muted);text-align:center;padding:30px 0}
  .toast{position:fixed;bottom:18px;right:50%;transform:translateX(50%);background:var(--ink);color:#FAF7F1;
       padding:10px 18px;border-radius:999px;font-size:13px;opacity:0;pointer-events:none;
       transition:opacity .25s var(--ease)}
  .toast.show{opacity:1}
  .note{background:var(--panel);border:1px dashed var(--border);border-radius:var(--r-sm);
       padding:10px 12px;font-size:12.5px;color:var(--muted);margin:0 0 14px}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important} }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🔑 أكواد الدخول</h1>
    <span class="stat" id="stat">…</span>
  </header>
  <p class="sub">حدد لكل شقة: الكود يوصل الضيف تلقائي، ولا لازم موظف يرسله يدوي. الرقيب يراقب اليدوية فقط.</p>
  <p class="note">🟡 «يدوي» يعني: قبل كل وصول، الرقيب يتأكد أن أحد من الفريق أرسل الكود بالمحادثة — وإذا ما انرسل والضيف قرب، ينبّه فوراً.</p>
  <input class="search" id="q" placeholder="ابحث باسم الشقة…" autocomplete="off">
  <div id="list"><div class="empty">جاري التحميل…</div></div>
</div>
<div class="toast" id="toast"></div>
<script>
var TOKEN = new URLSearchParams(location.search).get('token') || '';
var ROWS = [];
var CAN_EDIT = false;

function api(path, opts){
  opts = opts || {};
  opts.headers = Object.assign({'X-Token': TOKEN, 'Content-Type': 'application/json'}, opts.headers || {});
  return fetch(path, opts).then(function(r){ return r.json(); });
}

function toast(msg){
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2200);
}

function render(){
  var q = (document.getElementById('q').value || '').trim();
  var list = document.getElementById('list');
  var rows = ROWS.filter(function(r){ return !q || (r.name || '').indexOf(q) >= 0; });
  if (!rows.length){ list.innerHTML = '<div class="empty">لا توجد شقق مطابقة</div>'; return; }
  var html = rows.map(function(r){
    var autoCls = r.mode === 'auto' ? 'on-auto' : '';
    var manCls = r.mode === 'manual' ? 'on-manual' : '';
    return '<div class="row" data-lid="' + r.lid + '">' +
      '<span class="nm">' + r.name + '</span>' +
      '<span class="seg">' +
      '<button type="button" data-mode="auto" class="' + autoCls + '">تلقائي</button>' +
      '<button type="button" data-mode="manual" class="' + manCls + '">يدوي</button>' +
      '</span></div>';
  }).join('');
  list.innerHTML = html;
}

function stat(n){
  document.getElementById('stat').textContent = 'يدوي: ' + n;
}

document.getElementById('list').addEventListener('click', function(ev){
  var btn = ev.target.closest('button[data-mode]');
  if (!btn) return;
  if (!CAN_EDIT){ toast('غير مصرّح لك بالتعديل'); return; }
  var rowEl = btn.closest('.row');
  var lid = rowEl.getAttribute('data-lid');
  var mode = btn.getAttribute('data-mode');
  api('/api/watchdog/code-mode', {method: 'POST', body: JSON.stringify({lid: lid, mode: mode})})
    .then(function(r){
      if (!r.ok){ toast(r.error || 'صار خطأ'); return; }
      var row = ROWS.find(function(x){ return x.lid === r.lid; });
      if (row) row.mode = r.mode;
      stat(r.manual_n);
      render();
    })
    .catch(function(){ toast('تعذّر الحفظ — جرّب مرة ثانية'); });
});

document.getElementById('q').addEventListener('input', render);

api('/api/watchdog/code-mode').then(function(r){
  if (!r.ok){ document.getElementById('list').innerHTML = '<div class="empty">' + (r.error || 'unauthorized') + '</div>'; return; }
  ROWS = r.rows || [];
  CAN_EDIT = !!r.can_edit;
  stat(r.manual_n || 0);
  render();
}).catch(function(){
  document.getElementById('list').innerHTML = '<div class="empty">تعذّر التحميل</div>';
});
</script>
</body>
</html>"""


async def handle_page(request):
    web = HOST.require("web")
    if not HOST.dash_auth(request):
        return web.Response(status=403, content_type="text/html", charset="utf-8",
                            text="<!doctype html><meta charset='utf-8'>"
                                 "<body style='font-family:sans-serif;text-align:center;padding:60px'>"
                                 "<h3>غير مصرّح — افتح الرابط من لوحة التحكم</h3></body>")
    return web.Response(content_type="text/html", charset="utf-8", text=WATCHDOG_PAGE_HTML)


def register(app):
    app.router.add_get("/api/watchdog/status", _safe(api_status))
    app.router.add_get("/api/watchdog/code-mode", _safe(api_code_mode_get))
    app.router.add_post("/api/watchdog/code-mode", _safe(api_code_mode_set))
    app.router.add_get("/watchdog", handle_page)
