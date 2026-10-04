# -*- coding: utf-8 -*-
"""
aqd.sign_page — the public signing page shell served at /sign/{token}.

A plain HTML shell with NO data in it: everything is fetched by /aqd/static/sign.js from
/api/aqd-t/{token}. Same trap as DASHBOARD_HTML (a normal triple-quoted Python string), so this
file contains ZERO backslashes — guarded by tests/test_aqd_dashboard.py and gate G8.

Mobile first: 16 px gutter, max-width 720 px, rtl, no horizontal page scroll. Tokens copied from
onboarding/page.py; fonts from the public /guide/fonts route with a system-ui fallback.
"""

PAGE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<meta name="theme-color" content="#F1EDE6">
<title>عقد عوجا — التوقيع</title>
<style>
@font-face{font-family:'Thmanyah';font-weight:400;font-display:swap;src:url(/guide/fonts/thmanyahsans-Regular.woff2) format('woff2')}
@font-face{font-family:'Thmanyah';font-weight:500;font-display:swap;src:url(/guide/fonts/thmanyahsans-Medium.woff2) format('woff2')}
@font-face{font-family:'Thmanyah';font-weight:700;font-display:swap;src:url(/guide/fonts/thmanyahsans-Bold.woff2) format('woff2')}
:root{
  --bg:#F1EDE6; --panel:#FAF7F1; --ink:#292925; --body:#33302B; --muted:#6B655A;
  --gold:#B29A6A; --gold-ink:#7E6A40; --gold-soft:#F0E8D8; --maroon:#8B3748; --maroon-soft:#F5E4E6;
  --green:#4A7C59; --green-soft:#E4EEE6; --border:#E7DFD1; --focus:#7E6A40;
  --r:14px; --ease:cubic-bezier(0.23,1,0.32,1);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--body);font:16px/1.7 'Thmanyah',system-ui,-apple-system,'Segoe UI',Tahoma,sans-serif;overflow-x:hidden}
main{max-width:720px;margin:0 auto;padding:16px 16px calc(120px + env(safe-area-inset-bottom))}
h1,h2,h3{color:var(--ink);line-height:1.35;margin:0}
button,input{font:inherit}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:8px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:6px 0 18px;border-bottom:1px solid var(--border);margin-bottom:18px}
.mark{font-weight:700;font-size:26px;color:var(--ink);letter-spacing:0}
.top .t{font-size:13.5px;color:var(--muted);text-align:left}
.top h1{display:block;color:var(--ink);font-weight:500;font-size:14px;margin:0}
::selection{background:var(--gold-soft);color:var(--ink)}
input{caret-color:var(--gold-ink)}
.ref{font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate}
.card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:20px 18px;margin-bottom:14px}
.hello{font-size:22px;font-weight:700;color:var(--ink);margin-bottom:4px}
.lede{color:var(--muted);margin:0 0 14px;font-size:15px}
.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0;padding:0;list-style:none}
.facts li{background:var(--bg);border-radius:10px;padding:10px 8px;text-align:center}
.facts .v{display:block;font-weight:700;font-size:19px;color:var(--ink);font-variant-numeric:tabular-nums}
.facts .l{display:block;font-size:12.5px;color:var(--muted)}
.gate h2{font-size:18px;margin-bottom:4px}
.boxes{display:flex;gap:10px;justify-content:center;direction:ltr;margin:16px 0 8px}
.boxes input{width:56px;height:64px;text-align:center;font-size:28px;font-weight:700;color:var(--ink);border:1.5px solid var(--border);border-radius:12px;background:#fff;caret-color:var(--gold)}
.boxes input:focus{border-color:var(--gold-ink);outline:none;box-shadow:0 0 0 3px var(--gold-soft)}
.boxes.bad input{border-color:var(--maroon)}
.boxes.shake{animation:shake .32s var(--ease)}
@keyframes shake{0%,100%{transform:translateX(0)}25%{transform:translateX(-6px)}75%{transform:translateX(6px)}}
.msg{font-size:14.5px;min-height:22px;text-align:center;margin:0}
.msg.bad{color:var(--maroon)}
.note{border-radius:12px;padding:12px 14px;font-size:14.5px;margin-bottom:14px}
.note.warn{background:var(--gold-soft);color:var(--ink)}
.note.bad{background:var(--maroon-soft);color:var(--maroon)}
.note.ok{background:var(--green-soft);color:var(--green)}
.state{text-align:center;padding:36px 18px}
.state .ic{width:56px;height:56px;border-radius:50%;margin:0 auto 14px;display:grid;place-items:center}
.state .ic svg{width:26px;height:26px;fill:none;stroke:currentColor;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
.state .ic.ok{background:var(--green-soft);color:var(--green)}
.state .ic.bad{background:var(--maroon-soft);color:var(--maroon)}
.state .ic.wait{background:var(--gold-soft);color:var(--gold-ink)}
.state h2{font-size:20px;margin-bottom:6px}
.state p{margin:0 0 16px;color:var(--muted)}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0 8px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.bar .lbl{font-weight:500;color:var(--ink);font-size:14.5px}
.bar .prog{flex:1 1 120px;height:6px;border-radius:6px;background:var(--border);overflow:hidden;min-width:100px}
.bar .prog i{display:block;height:100%;width:100%;background:var(--gold);transform:scaleX(0);transform-origin:right;transition:transform .2s var(--ease)}
.link{color:var(--gold-ink);font-weight:500;text-decoration:underline;text-underline-offset:3px;background:none;border:0;padding:6px 0;cursor:pointer;min-height:44px;display:inline-flex;align-items:center}
.doc{background:#fff;border:1px solid var(--border);border-radius:var(--r);overflow:hidden;margin-bottom:14px}
.doc iframe{display:block;width:100%;border:0;height:70vh;background:#fff}
.read{display:flex;justify-content:center;margin:0 0 14px}
.sign h2{font-size:18px;margin-bottom:12px}
.fld{margin-bottom:16px}
.fld label{display:block;font-weight:500;color:var(--ink);margin-bottom:6px;font-size:15px}
.fld input[type=text]{width:100%;min-height:48px;border:1.5px solid var(--border);border-radius:12px;padding:10px 12px;background:#fff;color:var(--ink)}
.fld input[type=text]:focus{border-color:var(--gold-ink);outline:none;box-shadow:0 0 0 3px var(--gold-soft)}
.pad{position:relative;border:1.5px dashed var(--gold);border-radius:12px;background:#fff;touch-action:none}
.pad canvas{display:block;width:100%;height:190px;border-radius:12px;cursor:crosshair}
.pad .hint{position:absolute;inset:0;display:grid;place-items:center;color:var(--muted);pointer-events:none;font-size:15px}
.pad.has .hint{display:none}
.padrow{display:flex;justify-content:space-between;align-items:center;margin-top:6px;font-size:13.5px;color:var(--muted)}
.consent{display:flex;gap:12px;align-items:flex-start;background:var(--bg);border-radius:12px;padding:12px;cursor:pointer;font-size:14.5px;color:var(--ink)}
.consent input{width:22px;height:22px;margin:3px 0 0;flex:none;accent-color:var(--gold-ink)}
.cta{position:fixed;inset-inline:0;bottom:0;z-index:10;background:var(--bg);border-top:1px solid var(--border);padding:12px 16px calc(14px + env(safe-area-inset-bottom))}
.cta .in{max-width:720px;margin:0 auto}
.btn{appearance:none;border:0;border-radius:14px;min-height:54px;width:100%;font-weight:700;font-size:17px;cursor:pointer;transition:transform .14s var(--ease),opacity .14s var(--ease)}
.btn:active{transform:scale(.97)}
.btn.primary{background:var(--ink);color:#FAF7F1}
.btn.primary[disabled]{opacity:.42;cursor:not-allowed;transform:none}
.btn.ghost{background:var(--panel);color:var(--ink);border:1.5px solid var(--border)}
.btn.inline{width:auto;padding:0 22px;min-height:48px;font-size:15.5px}
.sk{height:120px;border-radius:var(--r);background:var(--panel);border:1px solid var(--border)}
.small{font-size:13px;color:var(--muted)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
[hidden]{display:none !important}
@media (max-width:380px){.boxes input{width:50px;height:58px}.facts .v{font-size:17px}}
@media (prefers-reduced-motion:reduce){*{animation:none !important;transition:none !important}}
</style>
</head>
<body>
<main id="app" aria-live="polite">
  <header class="top">
    <div class="mark" aria-label="عوجا">عوجا</div>
    <div class="t"><h1>عقد تشغيل وحدات ضيافة خاصة</h1><span class="ref" id="ref"></span></div>
  </header>
  <div id="view"><div class="sk" aria-hidden="true"></div><p class="sr">جاري التحميل</p></div>
</main>
<div class="cta" id="cta" hidden><div class="in"><button class="btn primary" id="signBtn" type="button" disabled>توقيع العقد</button></div></div>
<noscript><p style="padding:16px">فعّل JavaScript في المتصفح لفتح العقد.</p></noscript>
<script src="/aqd/static/sign.js?v=__SIGN_JS_V__"></script>
</body>
</html>
"""


def html():
    from . import routes
    return PAGE.replace("__SIGN_JS_V__", routes.js_version("sign.js"), 1)
