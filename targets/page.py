# -*- coding: utf-8 -*-
"""
targets.page — the two phone pages: /my-targets («أهدافي») and /my-book («دفتر العملاء»).

They are thin shells. The screen itself is the SAME script the dashboard tabs use
(/targets/static/targets_tab.js), so the phone and the dashboard cannot drift. This file only
supplies the handful of helpers that script expects from its host page, and the Ouja tokens.

SAME BACKSLASH TRAP as DASHBOARD_HTML, schedule/page.py and ops/page.py: these are normal
triple-quoted strings, so a backslash typed into the JS is eaten by PYTHON first and the script
dies. There are ZERO backslashes in this file. Keep it that way, and esprima-parse after edits.

Login: the dashboard's own session (the ouja_token cookie planted at login, or ?token=).
"""

_HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">"""

_CSS = """
  :root{
    --bg:#F1EDE6; --surface:#FAF7F1; --surface-2:#EFEAE1; --line:#E7DFD1;
    --text:#292925; --text-2:#4A463F; --mut:#8A8377;
    --gold:#9C8350; --gold-tint:#F0E8D8;
    --red:#8B3748; --red-soft:#F3E2E4; --green:#4A6246; --green-soft:#E4EBE2;
    --r-md:12px; --font-mono:'JetBrains Mono',ui-monospace,monospace;
  }
  *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  html,body{margin:0;background:var(--bg);color:var(--text-2);
    font-family:'IBM Plex Sans Arabic',-apple-system,system-ui,sans-serif;line-height:1.6}
  body{padding:max(14px,env(safe-area-inset-top)) 14px calc(30px + env(safe-area-inset-bottom))}
  .wrap{max-width:760px;margin:0 auto}
  h1{font-size:21px;font-weight:700;color:var(--text);margin:0 0 2px}
  .sub{color:var(--mut);font-size:13px;margin-bottom:14px}
  .top{display:flex;gap:8px;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap}
  .nav{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface)}
  .nav a{padding:10px 16px;font-size:14px;font-weight:700;color:var(--text-2);text-decoration:none;min-height:44px;display:inline-flex;align-items:center}
  .nav a.on{background:var(--gold-tint);color:var(--text)}
  .lang{border:1px solid var(--line);background:var(--surface);color:var(--text-2);border-radius:10px;
    min-height:44px;padding:8px 14px;font:inherit;font-weight:700;cursor:pointer}
  .empty{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-md);padding:26px 16px;text-align:center}
  .de-ic{font-size:26px}
  .de-t{font-weight:700;color:var(--text);margin-top:6px}
  .de-a{font-size:13px;color:var(--mut);margin-top:4px}
  .retry{margin-top:12px;min-height:44px;padding:8px 18px;border-radius:9px;border:1px solid var(--line);
    background:var(--surface);font:inherit;font-weight:700;cursor:pointer;color:var(--text)}
  #toast{position:fixed;inset-inline:14px;bottom:calc(16px + env(safe-area-inset-bottom));margin:0 auto;max-width:420px;
    background:var(--text);color:#fff;border-radius:11px;padding:12px 16px;font-size:14px;font-weight:700;text-align:center;
    opacity:0;transform:translateY(8px);pointer-events:none;transition:opacity .18s,transform .18s cubic-bezier(0.23,1,0.32,1)}
  #toast.show{opacity:1;transform:none}
  @media (prefers-reduced-motion:reduce){#toast{transition:none}}
"""

_SHIM = """
var L = 'ar';
try { L = localStorage.getItem('tg_lang') || 'ar'; } catch (e) { L = 'ar'; }
function tok() {
  try {
    var q = new URLSearchParams(location.search).get('token');
    return q || '';
  } catch (e) { return ''; }
}
function esc(s) {
  var d = document.createElement('div');
  d.textContent = (s == null ? '' : String(s));
  return d.innerHTML.split('"').join('&quot;');
}
function labelText(ar, en) { return L === 'ar' ? ar : en; }
function putHtml(id, html) { var el = document.getElementById(id); if (el) { el.innerHTML = html || ''; } }
function toast(m) {
  var e = document.getElementById('toast');
  e.textContent = m;
  e.classList.add('show');
  clearTimeout(e._t);
  e._t = setTimeout(function () { e.classList.remove('show'); }, 2400);
}
function emptyState(title, action, icon) {
  return '<div class="empty"><div class="de-ic">' + esc(icon || '—') + '</div><div class="de-t">' + esc(title || '') +
    '</div><div class="de-a">' + esc(action || '') + '</div></div>';
}
function errorState() {
  return '<div class="empty"><div class="de-ic">⚠</div><div class="de-t">' + esc(labelText('تعذّر التحميل', 'Could not load')) +
    '</div><div class="de-a">' + esc(labelText('فيه مشكلة مؤقتة. جرّب مرة ثانية.', 'A temporary problem. Try again.')) +
    '</div><button class="retry" id="retryBtn">' + esc(labelText('أعد المحاولة', 'Retry')) + '</button></div>';
}
function hdr() { var t = tok(); return t ? { 'X-Token': t } : {}; }
function api(path) {
  return fetch(path, { headers: hdr(), credentials: 'same-origin' }).then(function (r) {
    if (r.status === 401) { throw new Error('unauthorized'); }
    return r.json();
  });
}
function post(path, body) {
  var h = hdr();
  h['Content-Type'] = 'application/json';
  return fetch(path, { method: 'POST', headers: h, credentials: 'same-origin', body: JSON.stringify(body || {}) })
    .then(function (r) { return r.json(); })
    .catch(function () { return {}; });
}
function start() {
  var which = document.body.getAttribute('data-which');
  document.documentElement.lang = L;
  document.documentElement.dir = L === 'ar' ? 'rtl' : 'ltr';
  document.getElementById('langBtn').textContent = L === 'ar' ? 'English' : 'عربي';
  document.getElementById('ttl').textContent = which === 'book' ? labelText('دفتر العملاء', 'Client book') : labelText('أهدافي', 'My targets');
  document.getElementById('navT').textContent = labelText('أهدافي', 'My targets');
  document.getElementById('navB').textContent = labelText('دفتر العملاء', 'Client book');
  var keep = tok() ? '?token=' + encodeURIComponent(tok()) : '';
  document.getElementById('navT').setAttribute('href', '/my-targets' + keep);
  document.getElementById('navB').setAttribute('href', '/my-book' + keep);
  window.TargetsTab[which](true);
}
document.addEventListener('click', function (ev) {
  if (ev.target && ev.target.id === 'retryBtn') { start(); }
  if (ev.target && ev.target.id === 'langBtn') {
    L = (L === 'ar' ? 'en' : 'ar');
    try { localStorage.setItem('tg_lang', L); } catch (e) { L = L; }
    start();
  }
});
"""

_PAGE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
__HEAD__
<title>__TITLE__</title>
<style>__CSS__</style>
</head>
<body data-which="__WHICH__">
<div class="wrap">
  <div class="top">
    <div class="nav">
      <a id="navT" href="/my-targets" class="__ON_T__">أهدافي</a>
      <a id="navB" href="/my-book" class="__ON_B__">دفتر العملاء</a>
    </div>
    <button class="lang" id="langBtn" type="button">English</button>
  </div>
  <h1 id="ttl">__TITLE__</h1>
  <div class="sub">عوجا ريزيدنس</div>
  <div id="__BODY__"><div class="empty"><div class="de-a">…</div></div></div>
</div>
<div id="toast" role="status" aria-live="polite"></div>
<script>__SHIM__</script>
<script src="/targets/static/targets_tab.js?v=__V__"></script>
<script>start();</script>
</body>
</html>
"""

LOGIN_HINT_HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
""" + _HEAD + """
<title>عوجا</title>
<style>""" + _CSS + """</style>
</head>
<body>
<div class="wrap">
  <h1>هالصفحة تحتاج تسجيل دخول</h1>
  <div class="empty"><div class="de-t">افتح لوحة عوجا وسجّل دخولك أول</div>
  <div class="de-a">بعدها ارجع لهالرابط من نفس المتصفح.</div></div>
</div>
</body>
</html>
"""


def render(which, js_version="0"):
    which = "book" if which == "book" else "targets"
    title = "دفتر العملاء" if which == "book" else "أهدافي"
    out = _PAGE
    for k, v in (("__HEAD__", _HEAD), ("__CSS__", _CSS), ("__SHIM__", _SHIM), ("__TITLE__", title),
                 ("__WHICH__", which), ("__BODY__", "bkBody" if which == "book" else "tgBody"),
                 ("__ON_T__", "on" if which == "targets" else ""),
                 ("__ON_B__", "on" if which == "book" else ""), ("__V__", str(js_version))):
        out = out.replace(k, v)
    return out
