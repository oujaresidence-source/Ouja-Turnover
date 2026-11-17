# -*- coding: utf-8 -*-
"""
staff.page — «عوجا فريق», the employees' phone app (served at /team).

TRAP (same as DASHBOARD_HTML and schedule/page.py): HTML below is a NORMAL triple-quoted
Python string. It must contain ZERO backslashes — Python would eat them before the browser
sees the JS. Newlines are real newlines; clicks go through ONE delegated listener reading
data-act, so no handler ever builds quoted strings. tests/test_staff_routes.py enforces
the zero-backslash rule and esprima-parses the script.

Visual world = the guest site (/apartments): limestone paper, ink, Thmanyah Serif Display +
Thmanyah Sans from the public /monthly/static/fonts, gold for marks only, drawn SVG icons.
"""

HTML = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>عوجا فريق</title>
<link rel="manifest" href="/team/manifest.webmanifest">
<meta name="theme-color" content="#F4EFE7">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="عوجا فريق">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="apple-touch-icon" href="/pwa/icons/apple-touch-icon.png">
<link rel="preload" as="font" type="font/woff2" crossorigin href="/monthly/static/fonts/thmanyah-sans-regular.v20260827a.woff2">
<link rel="preload" as="font" type="font/woff2" crossorigin href="/monthly/static/fonts/thmanyah-serif-display-black.v20260827a.woff2">
<style>
@font-face{font-family:"Thmanyah Serif";font-weight:900;font-display:swap;src:url(/monthly/static/fonts/thmanyah-serif-display-black.v20260827a.woff2) format("woff2")}
@font-face{font-family:"Thmanyah Serif";font-weight:700;font-display:swap;src:url(/monthly/static/fonts/thmanyah-serif-display-bold.v20260827a.woff2) format("woff2")}
@font-face{font-family:"Thmanyah Sans";font-weight:400;font-display:swap;src:url(/monthly/static/fonts/thmanyah-sans-regular.v20260827a.woff2) format("woff2")}
@font-face{font-family:"Thmanyah Sans";font-weight:500;font-display:swap;src:url(/monthly/static/fonts/thmanyah-sans-medium.v20260827a.woff2) format("woff2")}
@font-face{font-family:"Thmanyah Sans";font-weight:700;font-display:swap;src:url(/monthly/static/fonts/thmanyah-sans-bold.v20260827a.woff2) format("woff2")}
:root{
  --paper:#F4EFE7;--paper2:#ECE5D9;--card:#FBF8F3;--ink:#1D1813;--ink2:#463C33;--mut:#6B5F52;
  --line:#DCD2C3;--line2:#E8E1D5;--gold:#A57A2C;--gold-soft:#EBDDC2;--night:#15110D;
  --ok:#2E6A49;--ok-bg:#E0EADF;--warn:#8A4B2A;--warn-bg:#F2E4D2;--bad:#9A3F29;--bad-bg:#F4DFD6;
  --f-d:"Thmanyah Serif","Thmanyah Sans",Georgia,serif;
  --f-t:"Thmanyah Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --ease:cubic-bezier(.23,1,.32,1);--drawer:cubic-bezier(.32,.72,0,1);
  --tabbar:64px;
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{background:var(--paper);-webkit-tap-highlight-color:transparent;-webkit-text-size-adjust:100%;overscroll-behavior:none}
body{margin:0;min-height:100dvh;background:var(--paper);color:var(--ink);font-family:var(--f-t);font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;overscroll-behavior:none}
::selection{background:var(--gold-soft);color:var(--ink)}
:focus-visible{outline:2px solid var(--ink);outline-offset:3px;border-radius:8px}
button,a,[role=button],.tab{touch-action:manipulation;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
button{font:inherit;color:inherit}
a{color:inherit}
bdi{unicode-bidi:isolate}
.num{font-variant-numeric:tabular-nums}
svg.i{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}
svg.i.s{width:18px;height:18px}

.app{max-width:520px;margin:0 auto;padding:0 18px calc(var(--tabbar) + 36px + env(safe-area-inset-bottom))}
header.top{position:sticky;top:0;z-index:20;background:var(--paper);display:flex;align-items:center;justify-content:space-between;gap:12px;padding:calc(10px + env(safe-area-inset-top)) 0 10px}
.brand{display:flex;align-items:baseline;gap:8px}
.brand b{font-family:var(--f-d);font-weight:900;font-size:27px;line-height:1}
.brand span{font-size:14px;font-weight:500;color:var(--mut)}
.brand i{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--gold);transform:translateY(-3px)}
.ibtn{width:44px;height:44px;border-radius:999px;border:1px solid var(--line);background:var(--card);display:grid;place-items:center;cursor:pointer;transition:transform .12s var(--ease)}
.ibtn:active{transform:scale(.94)}
.ibtn.spin svg{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(-360deg)}}

.hello{padding:12px 0 4px}
.date{color:var(--mut);font-size:15px;margin:4px 0 0}
h1{font-family:var(--f-d);font-weight:900;font-size:38px;line-height:1.12;margin:4px 0 8px;text-wrap:balance}
.status{font-size:19px;line-height:1.5;color:var(--ink2);margin:0;text-wrap:pretty}
.note{font-size:14px;color:var(--mut);margin:10px 0 0;display:flex;gap:8px;align-items:center}
.asbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:6px 0 0;padding:10px 14px;border-radius:14px;background:var(--paper2);font-size:15px}
.asbar button{background:none;border:0;font-weight:700;text-decoration:underline;text-underline-offset:4px;padding:8px 0;cursor:pointer}
h2{font-size:15px;font-weight:700;letter-spacing:0;margin:30px 2px 10px;color:var(--ink2);display:flex;justify-content:space-between;align-items:baseline}
h2 small{font-weight:400;color:var(--mut);font-size:14px}

.list{background:var(--card);border:1px solid var(--line2);border-radius:20px;overflow:hidden}
.row{display:flex;align-items:center;gap:12px;width:100%;min-height:66px;padding:12px 14px;background:none;border:0;border-top:1px solid var(--line2);text-align:start;cursor:pointer;text-decoration:none;transition:background-color .16s var(--ease)}
.row:first-child{border-top:0}
.row:active{background:var(--paper2)}
.row .main{flex:1;min-width:0}
.t1{display:block;font-weight:700;font-size:16.5px;line-height:1.35}
.t2{display:block;font-size:14.5px;color:var(--mut);line-height:1.45;margin-top:2px}
.chev{color:var(--mut)}
.mark{width:40px;height:40px;border-radius:13px;display:grid;place-items:center;flex:none;background:var(--paper2);color:var(--ink2)}
.tone-danger{background:var(--bad-bg);color:var(--bad)}
.tone-warn{background:var(--warn-bg);color:var(--warn)}
.tone-ok{background:var(--ok-bg);color:var(--ok)}
.tone-info{background:var(--paper2);color:var(--ink2)}
.tone-quiet{background:transparent;color:var(--mut);box-shadow:inset 0 0 0 1px var(--line)}
.chip{font-size:13px;font-weight:500;line-height:1;padding:7px 10px;border-radius:999px;white-space:nowrap;flex:none}
.code{font-family:var(--f-d);font-weight:700;font-size:19px;font-variant-numeric:tabular-nums}
.sub{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center}
.flag{display:inline-flex;align-items:center;gap:4px;color:var(--warn);font-size:14px}
.group{font-size:14px;color:var(--mut);padding:12px 16px 4px;border-top:1px solid var(--line2);background:var(--paper)}
.group:first-child{border-top:0}

.calm{padding:22px 18px;display:flex;gap:14px;align-items:flex-start}
.calm .t1{font-family:var(--f-d);font-weight:700;font-size:21px}
.night{display:flex;gap:12px;align-items:center;margin:22px 2px 0;color:var(--ink2);font-size:15px}
.fresh{color:var(--mut);font-size:13px;text-align:center;margin:26px 0 0}

.week{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.day{background:var(--card);border:1px solid var(--line2);border-radius:14px;padding:10px 2px;text-align:center;font-size:12.5px;color:var(--mut)}
.day b{display:block;font-size:17px;color:var(--ink);font-weight:700;margin:2px 0 4px}
.day.today{border-color:var(--ink)}
.day .st{font-size:12px;font-weight:500}
.day .st.working{color:var(--ink2)}
.day .st.off,.day .st.leave{color:var(--warn);font-weight:700}

nav.tabs{position:fixed;inset-inline:0;bottom:0;z-index:30;background:var(--paper);border-top:1px solid var(--line);padding:4px 8px env(safe-area-inset-bottom)}
nav.tabs .in{max-width:520px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr)}
.tab{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;min-height:var(--tabbar);background:none;border:0;font-size:12.5px;font-weight:500;color:var(--mut);cursor:pointer}
.tab:active svg{transform:scale(.9)}
.tab svg{transition:transform .12s var(--ease)}
.tab[aria-selected=true]{color:var(--ink);font-weight:700}
.tab[aria-selected=true]::before{content:"";position:absolute;top:0;width:24px;height:3px;border-radius:0 0 3px 3px;background:var(--gold)}
.badge{position:absolute;top:8px;inset-inline-start:calc(50% + 6px);min-width:19px;height:19px;padding:0 5px;border-radius:10px;background:var(--bad);color:#fff;font-size:11.5px;font-weight:700;line-height:19px;text-align:center}
body.gate nav.tabs,body.gate header .ibtn{display:none}

.panel{display:none}
.panel.on{display:block;animation:rise .22s var(--ease)}
@keyframes rise{from{opacity:.001;transform:translateY(6px)}}

.btn{display:flex;align-items:center;justify-content:center;gap:9px;width:100%;min-height:54px;padding:0 22px;border:0;border-radius:999px;background:var(--ink);color:var(--paper);font-size:16.5px;font-weight:700;cursor:pointer;text-decoration:none;transition:transform .12s var(--ease),background-color .2s var(--ease)}
.btn:active{transform:scale(.97)}
.btn.ghost{background:transparent;color:var(--ink);box-shadow:inset 0 0 0 1.5px var(--ink)}
.btn[disabled]{opacity:.55}
.field{display:block;margin:0 0 14px}
.field span{display:block;font-size:14px;font-weight:500;color:var(--ink2);margin:0 2px 6px}
.field input,.field select{width:100%;min-height:52px;padding:0 16px;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--ink);font:inherit;font-size:17px}
.field input:focus,.field select:focus{outline:2px solid var(--ink);outline-offset:1px}
.check{display:flex;align-items:center;gap:10px;min-height:48px;margin:0 2px 14px;font-size:16px}
.check input{width:22px;height:22px;accent-color:var(--ink)}
.err{color:var(--bad);font-size:15px;margin:0 2px 12px;min-height:1px}

.gatebox{min-height:calc(100dvh - 120px);display:flex;flex-direction:column;justify-content:center;padding:20px 0 40px}
.gatebox h1{font-size:44px}
.gatebox p{color:var(--ink2);font-size:17px;margin:0 0 26px}

.scrim{position:fixed;inset:0;z-index:40;background:rgba(21,17,13,.42);opacity:0;pointer-events:none;transition:opacity .5s var(--drawer)}
.scrim.on{opacity:1;pointer-events:auto}
.sheet{position:fixed;inset-inline:0;bottom:0;z-index:41;margin:0 auto;max-width:520px;max-height:90dvh;display:flex;flex-direction:column;background:var(--card);border-radius:26px 26px 0 0;box-shadow:0 -12px 40px rgba(29,24,19,.16);transform:translateY(105%);visibility:hidden;transition:transform .5s var(--drawer),visibility 0s linear .5s}
.sheet.on{transform:translateY(0);visibility:visible;transition:transform .5s var(--drawer),visibility 0s}
.grab{touch-action:none;padding:10px 20px 4px;cursor:grab}
#sheetHead{padding-inline-end:56px}
.handle{width:42px;height:5px;border-radius:3px;background:var(--line);margin:0 auto 14px}
.sheet .body{overflow-y:auto;overscroll-behavior:contain;padding:0 20px calc(26px + env(safe-area-inset-bottom))}
.sheet h3{font-family:var(--f-d);font-weight:900;font-size:34px;line-height:1.1;margin:0}
.sheet .full{color:var(--mut);font-size:14.5px;margin:4px 0 0}
.facts{margin:18px 0 0;border-top:1px solid var(--line2)}
.fact{display:flex;justify-content:space-between;gap:12px;padding:13px 0;border-bottom:1px solid var(--line2);font-size:16px}
.fact span:first-child{color:var(--mut)}
.fact span:last-child{font-weight:500;text-align:end}
.sheet h4{font-size:15px;font-weight:700;color:var(--ink2);margin:22px 0 8px}
.item{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--line2);font-size:15.5px}
.item:last-child{border-bottom:0}
.acts{display:grid;gap:10px;margin:24px 0 0}
.closex{position:absolute;top:12px;inset-inline-end:14px}

#toast{position:fixed;inset-inline:0;bottom:calc(var(--tabbar) + 18px + env(safe-area-inset-bottom));z-index:60;margin:0 auto;width:max-content;max-width:calc(100% - 36px);padding:12px 18px;border-radius:999px;background:var(--night);color:var(--paper);font-size:15px;font-weight:500;opacity:0;transform:translateY(8px);transition:opacity .2s var(--ease),transform .2s var(--ease);pointer-events:none}
#toast.on{opacity:1;transform:none}

.skel{height:66px;border-top:1px solid var(--line2);background:linear-gradient(90deg,var(--card),var(--paper2),var(--card));background-size:200% 100%;animation:shimmer 1.4s linear infinite}
.skel:first-child{border-top:0}
@keyframes shimmer{to{background-position:-200% 0}}

@media (hover:hover) and (pointer:fine){
  .row:hover{background:var(--paper2)}
  .ibtn:hover{background:var(--paper2)}
  .btn:hover{background:var(--ink2)}
  .btn.ghost:hover{background:var(--paper2)}
  .tab:hover{color:var(--ink)}
}
@media (min-width:760px){
  .app{padding-top:18px}
  h1{font-size:44px}
}
@media (prefers-reduced-motion:reduce){
  .panel.on{animation:none}
  .sheet,.sheet.on,.scrim{transition-duration:.01s}
  .skel{animation:none}
  .ibtn.spin svg{animation:none}
}
</style>
</head>
<body class="gate">
<!-- DIRECTION — world: the guest site's limestone paper, ink and Thmanyah; gold only marks.
     first viewport: one sentence says if you work today and whose apartments you hold, then
     the three things to do first. path: tap any row -> the apartment's sheet. signature: the
     sheet follows the finger and leaves at the speed it was thrown. reach: /team only. -->
<div class="app">
  <header class="top">
    <div class="brand"><b>عوجا</b><i aria-hidden="true"></i><span>فريق</span></div>
    <button class="ibtn" data-act="refresh" id="refreshBtn" aria-label="تحديث">
      <svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>
    </button>
  </header>
  <main id="main">
    <section class="panel on" id="p-gate"></section>
    <section class="panel" id="p-today" aria-label="اليوم"></section>
    <section class="panel" id="p-tasks" aria-label="المهام"></section>
    <section class="panel" id="p-team" aria-label="الفريق"></section>
    <section class="panel" id="p-me" aria-label="أنا"></section>
  </main>
</div>
<nav class="tabs" aria-label="الأقسام">
  <div class="in" role="tablist">
    <button class="tab" role="tab" data-act="tab" data-tab="today" aria-selected="true">
      <svg class="i" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/></svg>اليوم</button>
    <button class="tab" role="tab" data-act="tab" data-tab="tasks" aria-selected="false">
      <svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 6h10M10 12h10M10 18h10"/><path d="M3.5 6l1.5 1.5L7.5 5M3.5 12l1.5 1.5 2.5-2.5M3.5 18l1.5 1.5 2.5-2.5"/></svg>المهام<span class="badge" id="taskBadge" hidden></span></button>
    <button class="tab" role="tab" data-act="tab" data-tab="team" aria-selected="false">
      <svg class="i" viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3.2"/><path d="M2.8 19.5c.4-3.3 3-5.5 6.2-5.5s5.8 2.2 6.2 5.5"/><circle cx="17.2" cy="9" r="2.4"/><path d="M16.4 14.1c2.6.2 4.4 2 4.8 4.9"/></svg>الفريق</button>
    <button class="tab" role="tab" data-act="tab" data-tab="me" aria-selected="false">
      <svg class="i" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 20.5c.6-4 3.9-6.5 8-6.5s7.4 2.5 8 6.5"/></svg>أنا</button>
  </div>
</nav>
<div class="scrim" id="scrim" data-act="close"></div>
<div class="sheet" id="sheet" role="dialog" aria-modal="true" aria-labelledby="sheetTitle" tabindex="-1">
  <div class="grab" id="grab"><div class="handle" aria-hidden="true"></div><div id="sheetHead"></div></div>
  <button class="ibtn closex" data-act="close" aria-label="إغلاق">
    <svg class="i s" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
  </button>
  <div class="body" id="sheetBody"></div>
</div>
<div id="toast" role="status" aria-live="polite"></div>
<script>
(function(){
var TK = 'ouja_token';
var D = null, TAB = 'today', AS = '', lastLoad = 0, installEvt = null, loading = false, openLid = null;
try { AS = sessionStorage.getItem('staff_as') || ''; } catch (e) {}

var IC = {
  chev: '<path d="M14 6l-6 6 6 6"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M14.5 8.5l2 2"/>',
  out: '<path d="M13 4H6v16h7"/><path d="M10 12h11M17.5 8.5L21 12l-3.5 3.5"/>',
  turn: '<path d="M4 9h13l-3.5-3.5"/><path d="M20 15H7l3.5 3.5"/>',
  bed: '<path d="M3 18V7M3 13h18v5M21 13a3 3 0 0 0-3-3h-7v3"/><circle cx="7" cy="10.5" r="1.6"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M18.5 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
  chat: '<path d="M4 5h16v11H9.5L5 20v-4H4z"/>',
  alert: '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5M12 17.5v.01"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v6H4V6h6"/>',
  out2: '<path d="M15 4h4v16h-4"/><path d="M10 8l-4 4 4 4M6 12h10"/>',
  down: '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 20h14"/>',
  target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".6"/>',
  book: '<path d="M5 4.5h11a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z"/><path d="M5 17a3 3 0 0 1 3-3h11"/>',
  grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  photo: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><circle cx="9" cy="10.5" r="1.8"/><path d="M20.5 16l-5-5-8 7.5"/>'
};
function ic(name, cls){ return '<svg class="i' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" aria-hidden="true">' + (IC[name] || '') + '</svg>'; }
function esc(s){ return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function $(id){ return document.getElementById(id); }
function tok(){ try { return localStorage.getItem(TK) || ''; } catch (e) { return ''; } }
function short(name){ var s = String(name || ''); var i = s.indexOf('|'); return (i >= 0 ? s.slice(i + 1) : s).trim() || s; }
function andJoin(a){ return a.join(' و'); }

function headers(json){ var h = {}; var t = tok(); if (t) h['X-Token'] = t; if (json) h['Content-Type'] = 'application/json'; return h; }
function getJSON(path){
  return fetch(path, {headers: headers(false), credentials: 'same-origin', cache: 'no-store'}).then(function(r){
    if (r.status === 401) { var e = new Error('auth'); e.auth = true; throw e; }
    return r.json();
  });
}
function postJSON(path, body){
  return fetch(path, {method: 'POST', headers: headers(true), credentials: 'same-origin', body: JSON.stringify(body || {})}).then(function(r){
    return r.json().catch(function(){ return {}; }).then(function(j){ j._status = r.status; return j; });
  });
}

var toastT = null;
function toast(msg){ var t = $('toast'); t.textContent = msg; t.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(function(){ t.classList.remove('on'); }, 2600); }

function fmt(iso, opts){
  try { return new Intl.DateTimeFormat('ar-SA-u-ca-gregory-nu-latn', Object.assign({timeZone: 'Asia/Riyadh'}, opts)).format(new Date(String(iso).slice(0, 10) + 'T12:00:00+03:00')); }
  catch (e) { return String(iso || ''); }
}
function hm(s){ var x = String(s || ''); return x.length >= 16 ? x.slice(11, 16) : x; }
function clock(){ try { return new Intl.DateTimeFormat('ar-SA-u-nu-latn', {hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Riyadh'}).format(new Date()); } catch (e) { return ''; } }

/* ---------- shell ---------- */
function setGate(on){ document.body.classList.toggle('gate', !!on); }
function showPanel(id){
  var ids = ['gate', 'today', 'tasks', 'team', 'me'];
  for (var i = 0; i < ids.length; i++) { $('p-' + ids[i]).classList.toggle('on', ids[i] === id); }
  var tabs = document.querySelectorAll('.tab');
  for (var j = 0; j < tabs.length; j++) { tabs[j].setAttribute('aria-selected', tabs[j].getAttribute('data-tab') === id ? 'true' : 'false'); }
}
function go(tab){
  TAB = tab;
  showPanel(tab);
  try { history.replaceState(null, '', tab === 'today' ? '/team' : '/team#' + tab); } catch (e) {}
  window.scrollTo(0, 0);
}

/* ---------- gate screens ---------- */
function loginView(msg){
  setGate(true); closeSheet(true);
  $('p-gate').innerHTML =
    '<div class="gatebox"><h1>عوجا فريق</h1><p>يومك وشققك ومهامك، في مكان واحد.</p>' +
    '<form id="loginForm" novalidate>' +
    '<label class="field"><span>اسم المستخدم</span><input id="lgU" name="username" autocomplete="username" autocapitalize="none" autocorrect="off" spellcheck="false" enterkeyhint="next" required></label>' +
    '<label class="field"><span>كلمة المرور</span><input id="lgP" name="password" type="password" autocomplete="current-password" enterkeyhint="go" required></label>' +
    '<p class="err" id="lgErr" role="alert">' + esc(msg || '') + '</p>' +
    '<button class="btn" type="submit" id="lgBtn">دخول</button></form>' +
    '<p class="note" style="justify-content:center;margin-top:22px">نفس اسمك وكلمة مرورك في لوحة عوجا.</p></div>';
  showPanel('gate');
}
function noteView(title, body, extra){
  setGate(true);
  $('p-gate').innerHTML = '<div class="gatebox"><h1>' + esc(title) + '</h1><p>' + esc(body) + '</p>' + (extra || '') +
    '<button class="btn ghost" data-act="logout">' + ic('out2') + 'تسجيل الخروج</button></div>';
  showPanel('gate');
}

/* ---------- data ---------- */
function load(quiet){
  if (loading) return;
  loading = true;
  var b = $('refreshBtn'); b.classList.add('spin');
  if (!D && !quiet) skeleton();
  getJSON('/api/staff/today' + (AS ? '?as=' + encodeURIComponent(AS) : '')).then(function(d){
    loading = false; b.classList.remove('spin');
    if (!d || !d.ok) { if (!D) noteView('ما قدرنا نجيب يومك', 'صار خلل بسيط. زر «إعادة المحاولة» تحت.', '<button class="btn" data-act="refresh" style="margin-bottom:12px">إعادة المحاولة</button>'); else toast('ما قدرنا نحدّث الحين'); return; }
    D = d; lastLoad = Date.now();
    if (d.status === 'unlinked') {
      noteView('حسابك ما انربط باسمك', 'عشان يطلع لك يومك، لازم المدير يربط حسابك باسمك في تقويم الموظفين («مين هو مين» في الأهداف).');
      return;
    }
    if (d.status === 'pick') { renderPick(); return; }
    setGate(false);
    renderAll();
    var tf = $('tform');
    if (openLid != null && !(tf && tf.children.length)) { var a = findApt(openLid); if (a) fillSheet(a); }
    if (!quiet) { var h = (location.hash || '').replace('#', ''); go(['today', 'tasks', 'team', 'me'].indexOf(h) >= 0 ? h : TAB); }
    else showPanel(TAB);
  }).catch(function(e){
    loading = false; b.classList.remove('spin');
    if (e && e.auth) { D = null; loginView(''); return; }
    if (!D) noteView('ما فيه اتصال', 'النت مقطوع أو ضعيف.', '<button class="btn" data-act="refresh" style="margin-bottom:12px">إعادة المحاولة</button>');
    else toast('ما فيه اتصال الحين');
  });
}
function skeleton(){
  setGate(false);
  $('p-today').innerHTML = '<div class="hello"><h1>هلا</h1><p class="status">نجهّز يومك…</p></div><h2>أول ثلاث أشياء</h2><div class="list"><div class="skel"></div><div class="skel"></div><div class="skel"></div></div>';
  showPanel('today');
}
function findApt(lid){ var l = (D && D.apartments) || []; for (var i = 0; i < l.length; i++) { if (String(l[i].lid) === String(lid)) return l[i]; } return null; }

/* ---------- today ---------- */
function firstName(n){ return String(n || '').trim().split(' ')[0] || ''; }
function statusLine(d){
  var by = [];
  (d.covered_by || []).forEach(function(c){ if (c.by && by.indexOf(c.by) < 0) by.push(c.by); });
  if (d.status === 'working') return (d.covering_for || []).length ? 'اليوم دوام · ومعك شقق ' + andJoin(d.covering_for) : 'اليوم دوام · شققك معك';
  if (d.status === 'leave') return 'اليوم إجازة' + (by.length ? ' · شققك عند ' + andJoin(by) : '');
  if (d.status === 'off') return 'اليوم راحة' + (by.length ? ' · شققك عند ' + andJoin(by) : '');
  return 'الاسم ما ظهر في تقويم اليوم. المدير يقدر يتأكد منه.';
}
var EV_IC = {turnover: 'turn', checkout: 'out', checkin: 'key', inhouse: 'bed', vacant: 'moon', unknown: 'bed'};
var KIND_IC = {arrival_ticket: 'alert', turnover_clean: 'spark', promise_late: 'chat', ticket_late: 'wrench', ticket_urgent: 'wrench', checkout_clean: 'spark', cleaning_fix: 'photo', checkin: 'key', promise: 'chat', ticket: 'wrench', review: 'photo', replies: 'chat', escalations: 'alert'};
function taskRow(t){
  return '<button class="row" data-act="open" data-lid="' + esc(t.lid) + '">' +
    '<span class="mark tone-' + esc(t.tone) + '">' + ic(KIND_IC[t.kind] || 'check') + '</span>' +
    '<span class="main"><span class="t1 sub"><bdi class="code">' + esc(short(t.unit)) + '</bdi></span>' +
    '<span class="t2">' + esc(t.title) + '</span></span>' + ic('chev', 's chev') + '</button>';
}
function aptRow(a){
  var flags = '';
  if ((a.tickets || []).length) flags += '<span class="flag">' + ic('wrench', 's') + 'تذكرة</span>';
  if ((a.promises || []).length) flags += '<span class="flag">' + ic('chat', 's') + 'وعد</span>';
  var guest = a.guest ? ' · ' + esc(a.guest) : '';
  var chip = needsCleanChip(a) ? '<span class="chip tone-' + esc(a.cleaning.tone) + '">' + esc(a.cleaning.label) + '</span>' : '';
  return '<button class="row" data-act="open" data-lid="' + esc(a.lid) + '">' +
    '<span class="mark">' + ic(EV_IC[a.event] || 'bed') + '</span>' +
    '<span class="main"><span class="t1"><bdi class="code">' + esc(short(a.name)) + '</bdi></span>' +
    '<span class="t2 sub"><span>' + esc(a.event_ar) + guest + '</span>' + flags + '</span></span>' +
    chip + '</button>';
}
function needsCleanChip(a){ return a.cleaning.key !== 'none' || a.event === 'checkout' || a.event === 'turnover'; }
function asBar(d){
  if (!d.viewing_as) return '';
  return '<div class="asbar"><span>يوم ' + esc(d.employee) + '</span><button data-act="asme">رجوع</button></div>';
}
var MISS = {day: 'تقويم الموظفين', tickets: 'تذاكر الصيانة', promises: 'وعود الضيوف', cleaning: 'حالة التنظيف'};
function freshNote(d){
  var miss = (d.missing || []).map(function(k){ return MISS[k] || k; });
  if (miss.length) return '<p class="note">' + ic('alert', 's') + 'ما وصلت للحين: ' + esc(andJoin(miss)) + '. زر التحديث فوق يجيبها.</p>';
  if (d.has_snapshot === false) return '<p class="note">' + ic('alert', 's') + 'حجوزات اليوم ما وصلت للحين. تتحدث خلال دقايق.</p>';
  if (d.snap_age_min != null && d.snap_age_min > 30) return '<p class="note">' + ic('alert', 's') + 'حجوزات اليوم آخر تحديث لها قبل ' + esc(d.snap_age_min) + ' دقيقة.</p>';
  return '';
}
function oncallLine(d){
  var t = ((d.oncall || {}).tonight) || [];
  if (!t.length) return '';
  var s = t.map(function(x){ return esc(x.employee) + ' <bdi class="num" dir="ltr">' + esc(x.from) + '–' + esc(x.to) + '</bdi>'; }).join(' · ');
  return '<div class="night">' + ic('moon') + '<span>مناوبة الليلة: ' + s + '</span></div>';
}
function renderToday(d){
  var nxt = d.next || [];
  var html = '<div class="hello"><h1>هلا ' + esc(firstName(d.employee)) + '</h1><p class="status">' + esc(statusLine(d)) + '</p>' +
    '<div class="date">' + esc(fmt(d.date || d.today, {weekday: 'long', day: 'numeric', month: 'long'})) + '</div>' + freshNote(d) + asBar(d) + '</div>';
  if (d.status === 'working') {
    html += '<h2>أول ثلاث أشياء</h2>';
    html += nxt.length ? '<div class="list">' + nxt.map(taskRow).join('') + '</div>' :
      '<div class="list"><div class="calm"><span class="mark tone-ok">' + ic('check') + '</span><span><span class="t1">ما عليك شي عاجل الحين</span><span class="t2">إذا جدّ شي بيطلع هنا أول.</span></span></div></div>';
    var mine = (d.apartments || []).filter(function(a){ return a.mine; });
    var cover = {};
    (d.apartments || []).forEach(function(a){ if (!a.mine) { (cover[a.owner_name] = cover[a.owner_name] || []).push(a); } });
    html += '<h2>شققي اليوم</h2><div class="list">';
    html += mine.map(aptRow).join('');
    Object.keys(cover).forEach(function(n){ html += '<div class="group">شقق ' + esc(n) + ' · معك اليوم</div>' + cover[n].map(aptRow).join(''); });
    if (!(d.apartments || []).length) html += '<div class="calm"><span class="t2">ما فيه شقق باسمك في تقويم اليوم.</span></div>';
    html += '</div>';
  } else if (d.status === 'off' || d.status === 'leave') {
    var cb = d.covered_by || [];
    if (cb.length) {
      html += '<h2>مين ماسك شققك</h2><div class="list">' + cb.map(function(c){
        return '<div class="row" style="cursor:default"><span class="mark">' + ic('bed') + '</span><span class="main"><span class="t1"><bdi class="code">' + esc(short(c.name)) + '</bdi></span><span class="t2">عند ' + esc(c.by || 'ما تحدد') + '</span></span></div>';
      }).join('') + '</div>';
    }
  }
  html += oncallLine(d) + '<p class="fresh">آخر تحديث ' + esc(clock()) + '</p>';
  $('p-today').innerHTML = html;
}

/* ---------- tasks ---------- */
function countLine(n, urgent){
  var u = urgent ? ' · ' + urgent + ' عاجلة' : '';
  if (!n) return 'ما عليك شي الحين';
  if (n === 1) return 'شي واحد ينتظرك' + u;
  if (n === 2) return 'شيئين ينتظرونك' + u;
  if (n <= 10) return n + ' أشياء تنتظرك' + u;
  return n + ' شي ينتظرك' + u;
}
function renderTasks(d){
  var t = d.tasks || [], sup = d.supervisor || [];
  var urgent = t.filter(function(x){ return x.tone === 'danger'; }).length;
  var html = '<div class="hello"><h1>المهام</h1><p class="status">' + esc(countLine(t.length, urgent)) + '</p>' + asBar(d) + '</div>';
  if (t.length) html += '<h2>على شققك</h2><div class="list">' + t.map(taskRow).join('') + '</div>';
  else html += '<div class="list" style="margin-top:18px"><div class="calm"><span class="mark tone-ok">' + ic('check') + '</span><span><span class="t1">كل شي تمام</span><span class="t2">لا تذاكر مفتوحة ولا وعود على شققك.</span></span></div></div>';
  if (sup.length) {
    html += '<h2>للإشراف</h2><div class="list">' + sup.map(function(s){
      return '<a class="row" href="' + esc(s.href) + '"><span class="mark tone-' + esc(s.tone) + '">' + ic(KIND_IC[s.kind] || 'check') + '</span>' +
        '<span class="main"><span class="t1">' + esc(s.title) + '</span>' + (s.unit ? '<span class="t2"><bdi>' + esc(short(s.unit)) + '</bdi></span>' : '<span class="t2">تفتح في لوحة عوجا</span>') + '</span>' + ic('ext', 's chev') + '</a>';
    }).join('') + '</div>';
  }
  $('p-tasks').innerHTML = html;
  var bd = $('taskBadge'); bd.hidden = !urgent; bd.textContent = urgent ? String(urgent) : '';
  bd.setAttribute('aria-label', urgent ? urgent + ' عاجل' : '');
}

/* ---------- team ---------- */
function renderTeam(d){
  var tm = d.team || {working: [], off: []};
  var html = '<div class="hello"><h1>الفريق</h1><p class="status">' + esc(fmt(d.date || d.today, {weekday: 'long', day: 'numeric', month: 'long'})) + '</p></div>';
  html += '<h2>على رأس العمل</h2><div class="list">' + (tm.working || []).map(function(w){
    return '<div class="row" style="cursor:default"><span class="main"><span class="t1">' + esc(w.name) + (w.me ? ' <span class="chip tone-info">أنت</span>' : '') + '</span>' +
      '<span class="t2">' + ((w.covering_for || []).length ? 'الشقق الأساسية + شقق ' + esc(andJoin(w.covering_for)) : 'الشقق الأساسية') + '</span></span></div>';
  }).join('') + ((tm.working || []).length ? '' : '<div class="calm"><span class="t2">ما فيه أحد بالتقويم اليوم.</span></div>') + '</div>';
  if ((tm.off || []).length) {
    html += '<h2>غايبين اليوم</h2><div class="list">' + tm.off.map(function(o){
      return '<div class="row" style="cursor:default"><span class="main"><span class="t1">' + esc(o.name) + (o.me ? ' <span class="chip tone-info">أنت</span>' : '') + '</span>' +
        '<span class="t2">' + (o.reason === 'leave' ? 'إجازة' : 'راحة') + ((o.covered_by || []).length ? ' · الشقق عند ' + esc(andJoin(o.covered_by)) : '') + '</span></span></div>';
    }).join('') + '</div>';
  }
  var t = ((d.oncall || {}).tonight) || [], now = (d.oncall || {}).now;
  if (t.length || now) {
    html += '<h2>المناوبة</h2><div class="list">';
    if (now) html += '<div class="row" style="cursor:default"><span class="main"><span class="t1">' + esc(now.employee) + '</span><span class="t2">المناوبة الحين · <bdi class="num" dir="ltr">' + esc(now.from) + '–' + esc(now.to) + '</bdi></span></span></div>';
    html += t.map(function(x){ return '<div class="row" style="cursor:default"><span class="main"><span class="t1">' + esc(x.employee) + '</span><span class="t2">الليلة · <bdi class="num" dir="ltr">' + esc(x.from) + '–' + esc(x.to) + '</bdi></span></span></div>'; }).join('');
    html += '</div>';
  }
  $('p-team').innerHTML = html;
}

/* ---------- me ---------- */
var standalone = (window.matchMedia && matchMedia('(display-mode: standalone)').matches) || navigator.standalone === true;
var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent || '');
function link(href, icon, t1, t2, act){
  var a = act ? '<button class="row" data-act="' + act + '">' : '<a class="row" href="' + esc(href) + '">';
  return a + '<span class="main"><span class="t1">' + esc(t1) + '</span>' + (t2 ? '<span class="t2">' + esc(t2) + '</span>' : '') + '</span>' + ic('chev', 's chev') + (act ? '</button>' : '</a>');
}
function weekView(d){
  var w = d.week || [];
  if (!w.length) return '';
  var lab = {working: 'دوام', off: 'راحة', leave: 'إجازة', unknown: '—'};
  return '<h2>أسبوعي</h2><div class="week">' + w.map(function(x){
    return '<div class="day' + (x.date === d.today ? ' today' : '') + '">' + esc(fmt(x.date, {weekday: 'short'})) + '<b class="num">' + esc(fmt(x.date, {day: 'numeric'})) + '</b><span class="st ' + esc(x.status) + '">' + esc(lab[x.status] || '') + '</span></div>';
  }).join('') + '</div>';
}
function pickList(d){
  var e = d.employees || [];
  if (!e.length) return '';
  return '<h2>يوم موظف</h2><div class="list">' + e.map(function(n){
    return '<button class="row" data-act="as" data-name="' + esc(n) + '"><span class="main"><span class="t1">' + esc(n) + '</span></span>' + ic('chev', 's chev') + '</button>';
  }).join('') + '</div>';
}
function renderMe(d){
  var p = d.perms || {};
  var role = {admin: 'مدير', ops: 'العمليات', viewer: 'مشاهد', accountant: 'المحاسبة'}[(d.me || {}).role] || '';
  var html = '<div class="hello"><h1>' + esc((d.me || {}).name || d.employee || '') + '</h1><p class="status">' + esc(role) + (d.employee && d.employee !== (d.me || {}).name ? ' · ' + esc(d.employee) : '') + '</p>' + asBar(d) + '</div>';
  html += weekView(d);
  html += '<h2>روابط</h2><div class="list">';
  if (p.targets) html += link('/my-targets', 'target', 'أهدافي', 'وين وصلت هالشهر');
  if (p.book) html += link('/my-book', 'book', 'دفتر العملاء', 'الضيوف اللي بالتواصل');
  if (p.dashboard) html += link('/dashboard', 'grid', 'لوحة عوجا الكاملة', 'للكمبيوتر غالبًا');
  if (!standalone && (installEvt || isIOS)) html += link('', 'down', 'تثبيت التطبيق', isIOS ? 'من Safari: زر المشاركة ثم «إضافة إلى الشاشة الرئيسية»' : 'يصير له أيقونة على شاشتك', 'install');
  html += link('', 'out2', 'تسجيل الخروج', '', 'logout') + '</div>';
  if (p.view_as) html += pickList(d);
  $('p-me').innerHTML = html;
}
function renderPick(){
  setGate(false);
  var d = D;
  $('p-today').innerHTML = '<div class="hello"><h1>هلا ' + esc(firstName((d.me || {}).name)) + '</h1><p class="status">الحساب مو مربوط بموظف. هذي أسماء الفريق، ويوم أي واحد منهم ينفتح بضغطة.</p><div class="date">' + esc(fmt(d.today, {weekday: 'long', day: 'numeric', month: 'long'})) + '</div></div>' + pickList(d);
  $('p-tasks').innerHTML = $('p-today').innerHTML;
  renderTeam(d); renderMe(d);
  go(TAB === 'me' || TAB === 'team' ? TAB : 'today');
}
function renderAll(){ renderToday(D); renderTasks(D); renderTeam(D); renderMe(D); }

/* ---------- apartment sheet ---------- */
var PRIO = {urgent: 'عاجلة', high: 'مهمة', med: 'عادية', low: 'بسيطة'};
var CATS = ['صيانة', 'تكييف', 'كهرباء', 'سباكة', 'أجهزة', 'أثاث', 'إنترنت', 'أقفال', 'تنظيف', 'أخرى'];
function fillSheet(a){
  var p = (D && D.perms) || {};
  $('sheetHead').innerHTML = '<h3 id="sheetTitle"><bdi>' + esc(short(a.name)) + '</bdi></h3><p class="full"><bdi>' + esc(a.name) + '</bdi>' + (a.mine ? '' : ' · شقة ' + esc(a.owner_name)) + '</p>';
  var h = '<div class="facts"><div class="fact"><span>اليوم</span><span>' + esc(a.event_ar) + '</span></div>';
  if (a.guest) h += '<div class="fact"><span>الضيف</span><span>' + esc(a.guest) + '</span></div>';
  if (a.event === 'checkin' || a.event === 'turnover') {
    if (a.nights) h += '<div class="fact"><span>الليالي</span><span class="num">' + esc(a.nights) + '</span></div>';
    if (a.checkout) h += '<div class="fact"><span>يطلع</span><span>' + esc(fmt(a.checkout, {weekday: 'long', day: 'numeric', month: 'long'})) + '</span></div>';
  }
  if (needsCleanChip(a)) h += '<div class="fact"><span>التنظيف</span><span><span class="chip tone-' + esc(a.cleaning.tone) + '">' + esc(a.cleaning.label) + '</span></span></div>';
  h += '</div>';
  h += '<h4>تذاكر الصيانة</h4>';
  h += (a.tickets || []).length ? (a.tickets.map(function(t){
    return '<div class="item"><span class="mark ' + (t.late ? 'tone-warn' : 'tone-info') + '" style="width:34px;height:34px">' + ic('wrench', 's') + '</span><span><b>' + esc(t.title) + '</b><br><span class="t2">' + esc(PRIO[t.priority] || '') + (t.status === 'in_progress' ? ' · قيد العمل' : ' · مفتوحة') + (t.late ? ' · متأخرة' : '') + '</span></span></div>';
  }).join('')) : '<p class="t2" style="margin:0">ما فيه تذاكر مفتوحة.</p>';
  if ((a.promises || []).length) {
    h += '<h4>وعود للضيف</h4>' + a.promises.map(function(x){
      return '<div class="item"><span class="mark ' + (x.late ? 'tone-danger' : 'tone-info') + '" style="width:34px;height:34px">' + ic('chat', 's') + '</span><span><b>' + esc(x.text) + '</b><br><span class="t2">' + (x.due_at ? 'قبل <span class="num">' + esc(hm(x.due_at)) + '</span>' : '') + (x.late ? ' · متأخر' : '') + '</span></span></div>';
    }).join('');
  }
  h += '<div class="acts">';
  if (p.ticket_create) h += '<button class="btn" data-act="tform">' + ic('wrench') + 'فتح تذكرة صيانة</button><div id="tform"></div>';
  if (p.photos) h += '<a class="btn ghost" href="/dashboard#cphotos">' + ic('photo') + 'صور التنظيف</a>';
  h += '</div>';
  $('sheetBody').innerHTML = h;
}
function ticketForm(){
  var box = $('tform'); if (!box) return;
  var btn = document.querySelector('[data-act="tform"]'); if (btn) btn.hidden = true;
  box.innerHTML = '<label class="field"><span>وش المشكلة؟</span><input id="tkTitle" maxlength="120" placeholder="المكيف ما يبرّد بالصالة" enterkeyhint="done"></label>' +
    '<label class="field"><span>النوع</span><select id="tkCat">' + CATS.map(function(c){ return '<option>' + esc(c) + '</option>'; }).join('') + '</select></label>' +
    '<label class="check"><input type="checkbox" id="tkUrgent">عاجلة (الضيف متضايق أو داخل اليوم)</label>' +
    '<p class="err" id="tkErr" role="alert"></p><button class="btn" data-act="tsend">إرسال التذكرة</button>';
  var i = $('tkTitle'); if (i) i.focus();
}
function sendTicket(){
  var a = findApt(openLid); if (!a) return;
  var title = ($('tkTitle').value || '').trim();
  if (!title) { $('tkErr').textContent = 'وصف المشكلة مطلوب.'; return; }
  var btn = document.querySelector('[data-act="tsend"]'); btn.disabled = true; btn.textContent = 'نرسل…';
  postJSON('/api/tickets/create', {title: title, lid: a.lid, category: $('tkCat').value,
    priority: $('tkUrgent').checked ? 'urgent' : 'med', description: 'من تطبيق عوجا فريق', created_by: (D.me || {}).name || ''}).then(function(r){
    if (r && (r.ok || r.ticket || r.id)) { closeSheet(); toast('انفتحت التذكرة'); load(true); return; }
    btn.disabled = false; btn.textContent = 'إرسال التذكرة';
    $('tkErr').textContent = r._status === 403 ? 'الحساب ما عنده صلاحية فتح تذاكر. المدير يقدر يضيفها.' : 'ما انرسلت. الزر يرسلها مرة ثانية.';
  }).catch(function(){ btn.disabled = false; btn.textContent = 'إرسال التذكرة'; $('tkErr').textContent = 'ما فيه اتصال. الزر يرسلها مرة ثانية.'; });
}
var lastFocus = null;
function openSheet(lid){
  var a = findApt(lid); if (!a) return;
  openLid = a.lid; lastFocus = document.activeElement;
  fillSheet(a);
  var s = $('sheet'); s.style.transform = ''; $('scrim').style.opacity = '';
  s.classList.add('on'); $('scrim').classList.add('on');
  $('sheetBody').scrollTop = 0;
  setTimeout(function(){ try { s.focus({preventScroll: true}); } catch (e) {} }, 30);
}
function closeSheet(instant){
  var s = $('sheet'), sc = $('scrim');
  if (!s.classList.contains('on')) return;
  openLid = null;
  s.style.transform = ''; sc.style.opacity = '';
  s.classList.remove('on'); sc.classList.remove('on');
  if (lastFocus && lastFocus.focus && !instant) { try { lastFocus.focus({preventScroll: true}); } catch (e) {} }
}
/* drag: the sheet IS the finger while down (no easing), then the CSS drawer curve finishes it */
(function(){
  var grab = $('grab'), s = $('sheet'), sc = $('scrim'), dr = null;
  grab.addEventListener('pointerdown', function(e){
    if (!s.classList.contains('on')) return;
    var t = performance.now();
    dr = {y0: e.clientY, dy: 0, h: s.offsetHeight || 1, ly: e.clientY, lt: t, v: 0};
    s.style.transition = 'none'; sc.style.transition = 'none';
    try { grab.setPointerCapture(e.pointerId); } catch (x) {}
  });
  grab.addEventListener('pointermove', function(e){
    if (!dr) return;
    var dy = e.clientY - dr.y0;
    if (dy < 0) dy = dy * 0.18;
    var t = performance.now();
    dr.v = (e.clientY - dr.ly) / Math.max(1, t - dr.lt); dr.ly = e.clientY; dr.lt = t; dr.dy = dy;
    s.style.transform = 'translateY(' + dy + 'px)';
    sc.style.opacity = String(Math.max(0, 1 - dy / dr.h));
  });
  function end(){
    if (!dr) return;
    var dismiss = dr.dy > dr.h * 0.3 || (dr.v > 0.45 && dr.dy > 12);
    if (dismiss) {
      /* leave at the speed it was thrown: the rest of the way at the finger's own pace */
      var dur = Math.round(Math.min(420, Math.max(160, (dr.h - dr.dy) / Math.max(dr.v, 0.9))));
      if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) dur = 10;
      s.style.transition = 'transform ' + dur + 'ms cubic-bezier(.2,.75,.3,1), visibility 0s linear ' + dur + 'ms';
      sc.style.transition = 'opacity ' + dur + 'ms ease-out';
      dr = null;
      closeSheet();
      setTimeout(function(){ s.style.transition = ''; sc.style.transition = ''; }, dur + 40);
    } else {
      s.style.transition = ''; sc.style.transition = '';
      dr = null;
      s.style.transform = ''; sc.style.opacity = '';
    }
  }
  grab.addEventListener('pointerup', end);
  grab.addEventListener('pointercancel', end);
})();

/* ---------- events ---------- */
document.addEventListener('click', function(e){
  var el = e.target.closest ? e.target.closest('[data-act]') : null;
  if (!el) return;
  var act = el.getAttribute('data-act');
  if (act === 'tab') { go(el.getAttribute('data-tab')); }
  else if (act === 'open') { openSheet(el.getAttribute('data-lid')); }
  else if (act === 'close') { closeSheet(); }
  else if (act === 'refresh') { load(false); }
  else if (act === 'tform') { ticketForm(); }
  else if (act === 'tsend') { sendTicket(); }
  else if (act === 'as' || act === 'asme') {
    AS = act === 'as' ? (el.getAttribute('data-name') || '') : '';
    try { if (AS) sessionStorage.setItem('staff_as', AS); else sessionStorage.removeItem('staff_as'); } catch (x) {}
    TAB = 'today'; D = null; load(false);
  }
  else if (act === 'install') {
    if (installEvt) { installEvt.prompt(); installEvt.userChoice.then(function(){ installEvt = null; if (D) renderMe(D); }); }
    else toast('من Safari: زر المشاركة ثم «إضافة إلى الشاشة الرئيسية»');
  }
  else if (act === 'logout') {
    postJSON('/api/auth/logout', {}).catch(function(){}).then(function(){
      try { localStorage.removeItem(TK); sessionStorage.removeItem('staff_as'); } catch (x) {}
      D = null; AS = ''; loginView('');
    });
  }
});
document.addEventListener('submit', function(e){
  if (!e.target || e.target.id !== 'loginForm') return;
  e.preventDefault();
  var u = ($('lgU').value || '').trim(), pw = $('lgP').value || '', er = $('lgErr'), b = $('lgBtn');
  if (!u || !pw) { er.textContent = 'الاسم وكلمة المرور مطلوبة.'; return; }
  b.disabled = true; b.textContent = 'ندخّلك…'; er.textContent = '';
  postJSON('/api/auth/login', {username: u, password: pw}).then(function(r){
    if (r && r.token) { try { localStorage.setItem(TK, r.token); } catch (x) {} D = null; load(false); return; }
    b.disabled = false; b.textContent = 'دخول';
    er.textContent = r && r._status === 429 ? 'محاولات كثيرة. المحاولة بعد شوي.' : 'الاسم أو كلمة المرور غلط.';
  }).catch(function(){ b.disabled = false; b.textContent = 'دخول'; er.textContent = 'ما فيه اتصال. زر الدخول يعيد المحاولة.'; });
});
document.addEventListener('keydown', function(e){ if (e.key === 'Escape') closeSheet(); });
document.addEventListener('visibilitychange', function(){ if (document.visibilityState === 'visible' && D && Date.now() - lastLoad > 30000) load(true); });
setInterval(function(){ if (document.visibilityState === 'visible' && D && !$('sheet').classList.contains('on')) load(true); }, 60000);
window.addEventListener('beforeinstallprompt', function(e){ e.preventDefault(); installEvt = e; if (D && D.ok) renderMe(D); });
window.addEventListener('hashchange', function(){ var h = (location.hash || '').replace('#', ''); if (D && ['today', 'tasks', 'team', 'me'].indexOf(h) >= 0) go(h); });
if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(function(){}); }

var h0 = (location.hash || '').replace('#', '');
if (['tasks', 'team', 'me'].indexOf(h0) >= 0) TAB = h0;
load(false);
})();
</script>
</body>
</html>
"""
