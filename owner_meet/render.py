# -*- coding: utf-8 -*-
"""
owner_meet.render — HTML for the shared presentation, the presenter window and (S5) the owner's
link + PDF. ONE renderer, server-side, from the frozen snapshot.

The presentation is built from snapshot["owner"] ONLY. Nothing internal is ever in its DOM — not
hidden, not commented out (R1–R5 apply to the HTML source, not just what is visible). The presenter
window is the only surface that reads snapshot["presenter"].

ZERO backslashes in this file (brief P3): CSS and markup are plain strings; behaviour lives in the
real JS files under owner_meet/static/ (node --check).
"""

from html import escape

from . import charts, texts

FONT_FILES = (
    ("TS", 400, "ThmanyahSans-Regular.woff2"),
    ("TS", 500, "ThmanyahSans-Medium.woff2"),
    ("TS", 700, "ThmanyahSans-Bold.woff2"),
    ("TD", 700, "ThmanyahSerifDisplay-Bold.woff2"),
    ("TD", 900, "ThmanyahSerifDisplay-Black.woff2"),
)


def font_css(base):
    return "".join('@font-face{font-family:%s;src:url("%s%s") format("woff2");font-weight:%d;font-display:swap}'
                   % (fam, base, name, w) for fam, w, name in FONT_FILES)


# The locked palette: digest/render/tokens.py (ink, paper, gold, green = in the owner's favour,
# red = against, Diriyah mud brown = data (Faisal 2026-10-06, replacing blue). Neutrals are tinted
# toward the navy, never pure grey.
CSS = """
:root{--ink:#0B1A2E;--ink-2:#122944;--paper:#F7F4EE;--wash:#EDEAE3;--line:#E4E1DA;--mute:#5C6470;
--gold:#C6A15B;--gold-t:#7F5A1C;--gold-2:#D9C194;--green:#1F6F55;--green-bg:#E6EFEC;--red:#B23A34;--red-bg:#F9F1F0;
--mud:#8B5A3C;--mud-soft:#EBDCCB;--body:#2A3646;
--f-body:TS,"Noto Sans Arabic",Tahoma,sans-serif;--f-disp:TD,TS,"Noto Naskh Arabic",serif;color-scheme:light}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font-family:var(--f-body);color:var(--ink);-webkit-font-smoothing:antialiased}
::selection{background:var(--gold-2);color:var(--ink)}
.n{font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate}
.lt{direction:ltr;unicode-bidi:isolate}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
body.deck{background:#060F1C;overflow:hidden}
.stage{position:absolute;inset:0;margin:auto;width:min(100vw,calc(100vh*16/9));height:min(100vh,calc(100vw*9/16))}
.slide{position:absolute;inset:0;container-type:inline-size;background:var(--paper);overflow:hidden;opacity:0;visibility:hidden;
transition:opacity .28s cubic-bezier(.23,1,.32,1),visibility 0s linear .28s}
.slide.on{opacity:1;visibility:visible;transition:opacity .28s cubic-bezier(.23,1,.32,1)}
@media (prefers-reduced-motion:reduce){.slide,.slide.on,.prog i{transition:none}}
.in{--u:1cqw;position:absolute;inset:0;padding:calc(var(--u)*3.6) calc(var(--u)*5) calc(var(--u)*2.8);display:flex;flex-direction:column}
.dark{background:var(--ink);color:#FFFFFF}
.folio{display:flex;justify-content:space-between;align-items:baseline;font-size:calc(var(--u)*1.05);color:var(--mute);
padding-bottom:calc(var(--u)*.8);border-bottom:1.5px solid var(--ink);margin-bottom:calc(var(--u)*2.4)}
.folio b{font-family:var(--f-disp);font-weight:900;color:var(--ink);font-size:calc(var(--u)*1.35)}
.dark .folio{border-color:rgba(255,255,255,.22);color:#9AA6B6}.dark .folio b{color:#FFFFFF}
.s-foot{margin-top:auto;display:flex;justify-content:space-between;gap:calc(var(--u)*2);font-size:calc(var(--u)*.85);
color:var(--mute);border-top:1px solid var(--line);padding-top:calc(var(--u)*.7);line-height:1.5}
.dark .s-foot{border-color:rgba(255,255,255,.16);color:#8E9AAB}
h2.t{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*3.1);line-height:1.2;text-wrap:balance;margin-bottom:calc(var(--u)*1)}
.lede{font-size:calc(var(--u)*1.3);line-height:1.75;color:var(--body);max-width:62ch}
.mute{color:var(--mute)}
.cv h1{font-weight:700;font-size:calc(var(--u)*4.4);line-height:1.15;margin-top:auto;text-wrap:balance}
.cv h1.lt{text-align:right}
.cv .sub{font-size:calc(var(--u)*1.5);color:#C9D1DC;margin-top:calc(var(--u)*1.2)}
.trio{display:grid;grid-template-columns:repeat(3,1fr);margin-top:calc(var(--u)*4);border-top:1px solid rgba(255,255,255,.2)}
.trio div{padding:calc(var(--u)*1.6) 0 0;padding-inline-end:calc(var(--u)*2)}
.trio small{font-size:calc(var(--u)*1.05);color:#9AA6B6;display:block}
.trio b{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*4.4);line-height:1.1;display:block;margin-top:calc(var(--u)*.5)}
.trio em{font-family:var(--f-body);font-style:normal;font-weight:500;font-size:calc(var(--u)*1.3);color:#9AA6B6;margin-inline-start:calc(var(--u)*.6)}
.units{width:100%;border-collapse:collapse;margin-top:auto;font-size:calc(var(--u)*1.25)}
.units th{font-weight:500;color:#9AA6B6;text-align:start;font-size:calc(var(--u)*1);padding-bottom:calc(var(--u)*.6)}
.units td{padding:calc(var(--u)*.9) 0;border-top:1px solid rgba(255,255,255,.16)}
.units td b{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*2)}
.headline{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*3.6);line-height:1.3;max-width:24ch;text-wrap:balance}
.headline .em{color:var(--gold-t)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);margin-top:auto;border-top:1.5px solid var(--ink)}
.kpis>div{padding:calc(var(--u)*1.4) calc(var(--u)*1.4) 0;border-inline-start:1px solid var(--line)}
.kpis>div:first-child{border-inline-start:0;padding-inline-start:0}
.kpis small{display:block;font-size:calc(var(--u)*1.05);color:var(--mute)}
.kpis b{display:block;font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*3.4);line-height:1.1;margin-top:calc(var(--u)*.5)}
.kpis em{font-family:var(--f-body);font-style:normal;font-weight:500;font-size:calc(var(--u)*1.1);color:var(--mute);margin-inline-start:calc(var(--u)*.4)}
.chip{display:inline-block;margin-top:calc(var(--u)*.7);font-size:calc(var(--u)*.95);font-weight:700;padding:calc(var(--u)*.15) calc(var(--u)*.7);
border-radius:99px;border:1px solid currentColor}
.chip.top{color:var(--green)}.chip.mid{color:var(--mute)}.chip.low{color:var(--red)}
.split{display:grid;grid-template-columns:1fr calc(var(--u)*25);gap:calc(var(--u)*3);flex:1;min-height:0;align-items:start}
.fig{min-width:0}.fig svg{width:100%;height:auto;display:block;direction:ltr}
.side{border-inline-start:1px solid var(--line);padding-inline-start:calc(var(--u)*2.4);display:flex;flex-direction:column;gap:calc(var(--u)*1.4)}
.side .lbl{font-size:calc(var(--u)*1.05);color:var(--mute)}
.mega{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*6);line-height:1}
.mega em{font-family:var(--f-body);font-style:normal;font-size:calc(var(--u)*1.4);font-weight:500;color:var(--mute);margin-inline-start:calc(var(--u)*.5)}
.side p{font-size:calc(var(--u)*1.15);line-height:1.7;color:var(--body)}
.kv{display:flex;justify-content:space-between;gap:calc(var(--u)*1);font-size:calc(var(--u)*1.15);padding:calc(var(--u)*.55) 0;border-bottom:1px solid var(--line)}
.kv b{font-weight:700}.kv.own b{color:var(--green)}
.empty{font-size:calc(var(--u)*1.35);line-height:1.7;color:var(--mute);border-top:1px solid var(--line);padding-top:calc(var(--u)*1.4);max-width:56ch}
svg .tk{font-size:11px;fill:#5C6470}
svg .vl{font-size:12.5px;font-weight:700;fill:#0B1A2E;font-family:TS,sans-serif}
svg .lb{font-size:12.5px;fill:#0B1A2E;font-family:TS,sans-serif}
svg .lbm{font-size:11px;fill:#5C6470;font-family:TS,sans-serif}
.figs{display:grid;gap:calc(var(--u)*.8);min-height:0}
.figs h3{font-size:calc(var(--u)*1.05);font-weight:700;color:var(--mute);margin-bottom:calc(var(--u)*.2)}
.cap{font-size:calc(var(--u)*.92);color:var(--mute);display:flex;gap:calc(var(--u)*2);margin-top:calc(var(--u)*.2)}
.figs svg{width:100%;height:auto;display:block;direction:ltr}
.bands{display:grid;gap:calc(var(--u)*.9);margin-top:calc(var(--u)*.4)}
.brow{display:grid;grid-template-columns:calc(var(--u)*17) 1fr calc(var(--u)*17);gap:calc(var(--u)*2);align-items:center}
.brow .nm{font-size:calc(var(--u)*1.35);font-weight:700}
.brow .nm small{display:block;font-weight:400;font-size:calc(var(--u)*.92);color:var(--mute)}
.brow svg{width:100%;height:auto;display:block;direction:ltr}
.brow .vr b{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*1.9);display:block;line-height:1.1}
.brow .vr b small{font-family:var(--f-body);font-weight:500;font-size:calc(var(--u)*1);margin-inline-start:calc(var(--u)*.4)}
.brow .vr .chip{margin-top:calc(var(--u)*.3)}
.keyrow svg{width:calc(var(--u)*34);height:auto;display:block;direction:ltr;margin-inline-start:calc(var(--u)*19);margin-top:calc(var(--u)*.4)}
.fair{display:flex;gap:calc(var(--u)*2.4);align-items:center;border-top:1.5px solid var(--ink);padding-top:calc(var(--u)*.9);margin-top:calc(var(--u)*1)}
.fair b{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*3.4);line-height:1}
.fair p{font-size:calc(var(--u)*1.12);line-height:1.6;color:var(--body);max-width:58ch}
.ctrs{display:grid;grid-template-columns:repeat(5,1fr);border-top:1.5px solid var(--ink);border-bottom:1px solid var(--line)}
.ctrs div{padding:calc(var(--u)*1) calc(var(--u)*1.2);border-inline-start:1px solid var(--line)}
.ctrs div:first-child{border-inline-start:0;padding-inline-start:0}
.ctrs b{display:block;font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*3);line-height:1}
.ctrs small{display:block;font-size:calc(var(--u)*.98);color:var(--mute);margin-top:calc(var(--u)*.4)}
.tline{list-style:none;margin-top:calc(var(--u)*1)}
.tline li{display:grid;grid-template-columns:calc(var(--u)*9) 1fr;gap:calc(var(--u)*1.2);align-items:baseline;padding:calc(var(--u)*.55) 0;
border-bottom:1px solid var(--line);font-size:calc(var(--u)*1.12);position:relative;padding-inline-start:calc(var(--u)*1.6)}
.tline li:before{content:"";position:absolute;inset-inline-start:0;top:50%;width:calc(var(--u)*.7);height:calc(var(--u)*.7);border-radius:50%;transform:translateY(-50%);background:var(--ink)}
.tline li.k-rr:before{background:var(--gold)}.tline li.k-review:before{background:var(--mud)}.tline li.k-price:before{background:var(--mute)}
.tline .d{color:var(--mute)}
.more{font-size:calc(var(--u)*1);color:var(--mute);margin-top:calc(var(--u)*.6)}
.mstats{display:grid;grid-template-columns:repeat(4,1fr);gap:calc(var(--u)*2);margin-bottom:calc(var(--u)*1)}
.mstats small{font-size:calc(var(--u)*1);color:var(--mute);display:block}
.mstats b{display:block;font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*2.8);line-height:1.1}
.mstats em{font-family:var(--f-body);font-style:normal;font-size:calc(var(--u)*1);color:var(--mute);margin-inline-start:calc(var(--u)*.4);font-weight:500}
.tb{width:100%;border-collapse:collapse;font-size:calc(var(--u)*1.05)}
.tb th{font-weight:500;color:var(--mute);text-align:start;padding:calc(var(--u)*.5) calc(var(--u)*.4);border-bottom:1.5px solid var(--ink);font-size:calc(var(--u)*.95)}
.tb td{padding:calc(var(--u)*.6) calc(var(--u)*.4);border-bottom:1px solid var(--line);vertical-align:top}
.tb .open{color:var(--red);font-weight:700}
.rrtop{display:grid;grid-template-columns:calc(var(--u)*16) 1fr;gap:calc(var(--u)*3);align-items:center;margin-bottom:calc(var(--u)*1.2)}
.rrtop svg{width:100%;height:auto;display:block;direction:ltr}
.rrtop .kv{font-size:calc(var(--u)*1.3)}
svg .ringv{font-family:TD,TS,serif;font-weight:900;font-size:40px;fill:#0B1A2E}
.claims{list-style:none;display:grid;gap:calc(var(--u)*.2)}
.claims li{border-top:1px solid var(--line);padding:calc(var(--u)*.8) 0;display:grid;grid-template-columns:1fr calc(var(--u)*20);gap:calc(var(--u)*2)}
.claims b{font-size:calc(var(--u)*1.25)}
.claims p{font-size:calc(var(--u)*1.02);line-height:1.6;color:var(--body);margin-top:calc(var(--u)*.3)}
.claims .amt{font-size:calc(var(--u)*1.05);line-height:1.7}
.st{display:inline-block;font-size:calc(var(--u)*.92);font-weight:700;padding:calc(var(--u)*.1) calc(var(--u)*.7);border-radius:6px;margin-inline-start:calc(var(--u)*.6)}
.st.full,.st.received{background:var(--green-bg);color:var(--green)}.st.partial{background:#F4EBDC;color:var(--gold-t)}
.st.denied{background:var(--red-bg);color:var(--red)}.st.open{background:var(--wash);color:var(--ink)}
.dl{color:var(--red);font-weight:700}
.rvtop{display:grid;grid-template-columns:calc(var(--u)*20) 1fr;gap:calc(var(--u)*3);align-items:start;margin-bottom:calc(var(--u)*1)}
.rvtop .mega{font-size:calc(var(--u)*5)}
.rvtop svg{width:100%;height:auto;display:block;direction:ltr}
.rvs{list-style:none}
.rvs li{border-top:1px solid var(--line);padding:calc(var(--u)*.8) 0}
.rvs .h{font-size:calc(var(--u)*1.05);color:var(--mute)}
.rvs .h b{color:var(--ink);font-weight:700;margin-inline-end:calc(var(--u)*.6)}
.rvs .h .stars{color:var(--gold-t);font-weight:700;margin-inline-end:calc(var(--u)*.6)}
.rvs p{font-size:calc(var(--u)*1.15);line-height:1.7;color:var(--body);margin-top:calc(var(--u)*.3)}
.rvs .fu{font-size:calc(var(--u)*.95);color:var(--green);margin-top:calc(var(--u)*.2)}
.fun{display:grid;grid-template-columns:1fr 1fr;gap:calc(var(--u)*3);margin-top:calc(var(--u)*.6)}
.fun h4{font-size:calc(var(--u)*1.15);margin-bottom:calc(var(--u)*.8)}
.step{display:grid;grid-template-columns:1fr calc(var(--u)*11);align-items:center;gap:calc(var(--u)*1.2);margin-bottom:calc(var(--u)*.7)}
.step .bx{height:calc(var(--u)*2.6);border-radius:4px;background:var(--mud-soft);margin-inline-start:auto}
.step.me .bx{background:var(--mud)}
.step .tx{font-size:calc(var(--u)*1.02);line-height:1.35}
.step .tx b{display:block;font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*1.8)}
.gauge{margin-top:calc(var(--u)*1.4);display:flex;gap:calc(var(--u)*2.4);align-items:center;border-top:1.5px solid var(--ink);padding-top:calc(var(--u)*1.1)}
.gauge .big{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*4.2);line-height:1}
.gauge p{font-size:calc(var(--u)*1.12);line-height:1.6;color:var(--body);max-width:52ch}
.tag{display:inline-block;font-size:calc(var(--u)*1);font-weight:700;padding:calc(var(--u)*.2) calc(var(--u)*.8);border-radius:6px;background:var(--green-bg);color:var(--green)}
.plan{display:grid;grid-template-columns:1fr 1fr;gap:calc(var(--u)*1.2) calc(var(--u)*3);margin-top:calc(var(--u)*.8)}
.it{padding-top:calc(var(--u)*1);border-top:1px solid var(--line)}
.it b{display:block;font-size:calc(var(--u)*1.22);line-height:1.5}
.it p{font-size:calc(var(--u)*1.02);line-height:1.6;color:var(--body);margin-top:calc(var(--u)*.3)}
.it em{display:inline-block;font-style:normal;font-size:calc(var(--u)*.92);font-weight:700;color:var(--gold-t);margin-top:calc(var(--u)*.3)}
.it.owner{border-top:1.5px solid var(--gold)}
.tgt{display:grid;grid-template-columns:1fr 1fr;gap:calc(var(--u)*4);align-items:end;margin-top:auto}
.col{border-top:1.5px solid var(--ink);padding-top:calc(var(--u)*1.1)}
.col small{font-size:calc(var(--u)*1.1);color:var(--mute)}
.col b{display:block;font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*5.4);line-height:1.05;margin-top:calc(var(--u)*.4)}
.col b em{font-family:var(--f-body);font-style:normal;font-size:calc(var(--u)*1.3);font-weight:500;color:var(--mute);margin-inline-start:calc(var(--u)*.5)}
.col.g b{color:var(--gold-t)}
.col ul{list-style:none;margin-top:calc(var(--u)*.8)}
.col li{font-size:calc(var(--u)*1.02);color:var(--body);padding:calc(var(--u)*.2) 0}
.close{font-family:var(--f-disp);font-weight:900;font-size:calc(var(--u)*2.3);margin-top:calc(var(--u)*2);color:var(--ink)}
.close span{font-family:var(--f-body);font-weight:500;font-size:calc(var(--u)*1.15);color:var(--mute);margin-inline-start:calc(var(--u)*1.2)}
.proms{list-style:none;margin-top:calc(var(--u)*.6)}
.proms li{display:grid;grid-template-columns:calc(var(--u)*9) 1fr;gap:calc(var(--u)*1.4);align-items:baseline;border-top:1px solid var(--line);padding:calc(var(--u)*.8) 0}
.proms b{font-size:calc(var(--u)*1.2);line-height:1.5;font-weight:700}
.proms p{font-size:calc(var(--u)*1);color:var(--mute);margin-top:calc(var(--u)*.2)}
.proms .st{margin-inline-start:0;text-align:center}
.prog{position:fixed;left:0;right:0;bottom:0;height:3px;background:rgba(255,255,255,.08)}
.prog i{display:block;height:100%;background:var(--gold);width:100%;transform:scaleX(0);transform-origin:right;transition:transform .28s cubic-bezier(.23,1,.32,1)}
.black{position:fixed;inset:0;background:#000;z-index:9}
"""

NOTES_CSS = """
body.notes{background:#0B1A2E;color:#E7EBF0;font-size:16px;line-height:1.7;padding:20px 18px 40px;max-width:820px;margin:0 auto}
.nt-top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;border-bottom:1px solid rgba(255,255,255,.14);padding-bottom:12px}
.nt-top h1{font-family:var(--f-disp);font-weight:900;font-size:20px}
.nt-top .n{color:#9AA6B6;font-size:14px}
.nt-now{margin-top:18px}
.nt-now small{display:block;color:#9AA6B6;font-size:13px}
.nt-now b{display:block;font-family:var(--f-disp);font-weight:900;font-size:30px;line-height:1.25}
.nt-next{color:#9AA6B6;font-size:14px;margin-top:4px}
.nt-ctl{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.nt-ctl button{font:inherit;font-size:15px;font-weight:700;color:#0B1A2E;background:#F7F4EE;border:0;border-radius:8px;min-height:44px;padding:8px 18px;cursor:pointer;
transition:transform .12s cubic-bezier(.23,1,.32,1)}
.nt-ctl button:active{transform:scale(.97)}
.nt-ctl select{font:inherit;font-size:15px;background:#122944;color:#FFFFFF;border:1px solid rgba(255,255,255,.2);border-radius:8px;min-height:44px;padding:6px 10px}
.nt-pts{margin-top:18px;border-top:1px solid rgba(255,255,255,.14);padding-top:12px}
.nt-pts ul{padding-inline-start:20px}
.nt-pts li{margin:6px 0}
.nt-pts li.int{color:#F2C9A0}
.nt-card{display:none}.nt-card.on{display:block}
.nt-ready{margin-top:22px;border-top:1px solid rgba(255,255,255,.14);padding-top:12px}
.nt-ready h2,.nt-pts h2{font-size:13px;color:#D9C194;font-weight:500;margin-bottom:6px}
.nt-ready li{list-style:none;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.08)}
.nt-ready li.red{color:#F2B8B3}.nt-ready li.yellow{color:#F2DDA0}
.nt-ready li span{font-weight:700;margin-inline-end:8px}
.nt-ok{color:#9FD0BC}
"""


# ------------------------------------------------------------------ small builders
def _e(x):
    return escape("" if x is None else str(x))


def _money(x):
    return '<span class="n">%s</span>' % texts.money(x)


def _chip(band):
    c = texts.chip(band)
    return '<span class="chip %s">%s</span>' % (band["tone"], _e(c)) if c else ""


def _frame(chapter, unit_name, body, source, dark=False, cls=""):
    return ('<div class="in%s%s"><header class="folio"><b>عوجا</b><span>%s%s</span></header>%s'
            '<footer class="s-foot"><span>%s</span><span class="n pg"></span></footer></div>') % (
        " dark" if dark else "", (" " + cls) if cls else "", _e(chapter),
        (' · <bdi class="lt">%s</bdi>' % _e(unit_name)) if unit_name else "", body, _e(source))


def _asof(snap):
    a = (snap.get("meta") or {}).get("data_as_of")
    return ("، بيانات حتى " + texts.date_ar(a)) if a else ""


# ------------------------------------------------------------------ chapters
def ch_portfolio(snap):
    o = snap["owner"]
    rows = "".join(
        '<tr><td><bdi class="lt">%s</bdi><br><small class="mute">%s</small></td><td data-l="صافي المالك"><b><span class="n">%s</span></b> <small>ريال</small></td>'
        '<td data-l="الإشغال"><b class="n">%s</b></td><td data-l="التقييم"><b class="n">%s</b></td></tr>' % (
            _e(u["name"]), _e(texts.bedrooms(u.get("bedrooms"))), texts.money(u["money"]["total"]["owner_net"]),
            texts.pct((u.get("stats") or {}).get("occupancy")),
            texts.num((u.get("rating") or {}).get("value"), 2) if (u.get("rating") or {}).get("value") else "—")
        for u in o["units"])
    body = ('<h1>%s</h1><p class="sub">%s</p><table class="units"><thead><tr><th>الشقة</th><th>صافي المالك</th>'
            '<th>الإشغال</th><th>التقييم</th></tr></thead><tbody>%s</tbody></table>') % (
        _e("شققك في عوجا"), _e(texts.range_ar(o["period"]["start"], o["period"]["end"])), rows)
    return _frame("اجتماع المالك · " + texts.date_ar(snap["meta"]["meeting_date"]), None, body,
                  texts.SRC_STATEMENT + _asof(snap), dark=True, cls="cv")


def ch_cover(snap, u):
    o = snap["owner"]
    r = (u.get("rating") or {}).get("value")
    trio = (('<div><small>صافي المالك للفترة</small><b><span class="n">%s</span><em>ريال</em></b></div>'
             '<div><small>تقييم الضيوف</small><b><span class="n">%s</span><em>%s</em></b></div>'
             '<div><small>الحجوزات</small><b><span class="n">%s</span><em>حجزاً</em></b></div>') % (
        texts.money(u["money"]["total"]["owner_net"]), texts.num(r, 2) if r else "—",
        "من 5" if r else "لا تقييمات بعد", texts.num(u.get("bookings") or 0)))
    sub = " · ".join(x for x in (texts.bedrooms(u.get("bedrooms")),
                                  "الأداء " + texts.range_ar(o["period"]["start"], o["period"]["end"])) if x)
    body = '<h1 class="lt">%s</h1><p class="sub">%s</p><div class="trio">%s</div>' % (_e(u["name"]), _e(sub), trio)
    return _frame("اجتماع المالك · " + texts.date_ar(snap["meta"]["meeting_date"]), None, body,
                  texts.SRC_STATEMENT + _asof(snap), dark=True, cls="cv")


def ch_summary(snap, u):
    hl = u.get("headline")
    if hl:
        head = "".join(('<span class="em">%s</span>' % _e(t)) if em else _e(t) for t, em in hl)
    else:
        head = _e("أرقام هذه الفترة")
    p = u.get("peers") or {}
    st = u.get("stats") or {}
    r = (u.get("rating") or {}).get("value")
    nx = u.get("next14") or {}
    kp = [
        ("قيمة الحجوزات", texts.money(st.get("income")), "ريال", p.get("income")),
        ("صافي المالك", texts.money(u["money"]["total"]["owner_net"]), "ريال", p.get("net_per_night")),
        ("تقييم الضيوف", texts.num(r, 2) if r else "—", "من 5" if r else "", p.get("rating")),
        ("المحجوز من 14 ليلة قادمة", texts.pct(nx.get("share")), "", nx.get("band")),
    ]
    kpis = "".join('<div><small>%s</small><b><span class="n">%s</span><em>%s</em></b>%s</div>' % (
        _e(a), b, _e(c), _chip(band) if band else "") for a, b, c, band in kp)
    body = '<p class="headline">%s</p><div class="kpis">%s</div>' % (head, kpis)
    return _frame(texts.CH["summary"], u["name"], body,
                  texts.SRC_STATEMENT + "؛ المقارنة: " + texts.SRC_PEERS.replace("المصدر: ", "") + _asof(snap))


def ch_money(snap, u):
    m = u["money"]
    wf, per = m["waterfall"], m.get("per100")
    net = m["total"]["owner_net"]
    if wf["reconciled"]:
        fig = charts.waterfall(wf["rows"], "أين ذهب كل ريال",
                               "من صافي الحجوزات %s ريال إلى صافي المالك %s ريال." % (
                                   texts.money(wf["rows"][0]["amount"]), texts.money(net)))
    else:
        fig = '<p class="empty">%s</p>' % _e(texts.EMPTY["money"])
    side = ['<div><span class="lbl">صافي المالك</span><div class="mega"><span class="n">%s</span><em>ريال</em></div></div>' % texts.money(net)]
    if per:
        side.append('<p>من كل 100 ريال من صافي الحجوزات، يصل للمالك <b class="n">%d</b> ريالاً.</p>' % per["owner"])
        for k in ("fee", "cleaning", "expenses"):
            if k in per:
                side.append('<div class="kv"><span>%s</span><b class="n">%d</b></div>' % (_e(texts.PER100[k]), per[k]))
        side.append('<div class="kv own"><span>%s</span><b class="n">%d</b></div>' % (_e(texts.PER100["owner"]), per["owner"]))
    else:
        for r in wf["rows"]:
            side.append('<div class="kv"><span>%s</span><b class="n">%s</b></div>' % (
                _e(texts.WATERFALL.get(r["key"], r["key"])), texts.money(r["amount"])))
    if u.get("mgmt_pct") not in (None, ""):
        side.append('<p class="mute">رسوم عوجا %s٪ حسب عقدك.</p>' % texts.num(u["mgmt_pct"], 0 if float(u["mgmt_pct"]).is_integer() else 1))
    body = '<h2 class="t">%s</h2><div class="split"><div class="fig">%s</div><div class="side">%s</div></div>' % (
        _e(texts.CH["money"]), fig, "".join(side))
    return _frame(texts.CH["money"], u["name"], body, texts.SRC_STATEMENT + _asof(snap))


def _season_shade(snap, months):
    """{mkey: label} for months holding ≥ 7 days of Ramadan and/or any day of an Eid
    («رمضان» / «العيد» / «رمضان والعيد»)."""
    from . import periods
    seen = {}
    for s in (snap["owner"].get("seasons") or []):
        k = s.get("kind")
        if k not in texts.SEASON:
            continue
        for mk in months:
            if periods.window_days_in_month(mk, s["start"], s["end"]) >= (7 if k == "ramadan" else 1):
                seen.setdefault(mk, set()).add("ramadan" if k == "ramadan" else "eid")
    words = {frozenset(["ramadan"]): "رمضان", frozenset(["eid"]): "العيد", frozenset(["ramadan", "eid"]): "رمضان والعيد"}
    return {mk: words[frozenset(v)] for mk, v in seen.items()}


def _notes_by_month(snap, months):
    """-> ({mkey: marker}, [(marker, month, text)]): annotated months get a numbered marker under the
    bar; the full sentence goes in a caption under the chart (a slot is too narrow for it)."""
    from . import periods
    marks, caption = {}, []
    for a in (snap["owner"].get("annotations") or []):
        hit = [mk for mk in months if periods.window_days_in_month(mk, a["start"], a["end"]) > 0]
        if not hit:
            continue
        mark = "*" * (len(caption) + 1)
        for mk in hit:
            marks.setdefault(mk, mark)
        caption.append((mark, hit[0], a["text_ar"]))
    return marks, caption


def ch_monthly(snap, u):
    trend = u.get("trend") or []
    if not trend:
        return _frame(texts.CH["monthly"], u["name"], '<p class="empty">%s</p>' % _e(texts.EMPTY["monthly"]),
                      texts.SRC_STATEMENT)
    months = [t["m"] for t in trend]
    shade = _season_shade(snap, months)
    marks, caption = _notes_by_month(snap, months)
    nets = charts.month_bars([{"m": t["m"], "value": t["net"], "partial": t.get("partial")} for t in trend],
                             "صافي المالك كل شهر", "صافي المالك لكل شهر من %s إلى %s." % (
                                 texts.month_ar(months[0], True), texts.month_ar(months[-1], True)),
                             height=290, shade=shade, notes=marks, width=1180)
    occ = charts.month_bars([{"m": t["m"], "value": t.get("occupancy") or 0, "partial": t.get("partial")} for t in trend],
                            "الإشغال كل شهر", "نسبة الليالي المحجوزة في كل شهر.", fmt=texts.pct, height=130,
                            colour=charts.MUD, width=1180)
    cap = "".join('<span>%s %s: %s</span>' % (_e(m), _e(texts.month_ar(mk, True)), _e(t)) for m, mk, t in caption)
    body = ('<h2 class="t">%s</h2><div class="figs"><div>%s%s</div><div><h3>الإشغال</h3>%s</div></div>') % (
        _e("صافي المالك كل شهر"), nets, ('<p class="cap">%s</p>' % cap) if cap else "", occ)
    return _frame(texts.CH["monthly"], u["name"], body, texts.SRC_STATEMENT + "؛ المواسم بالتقويم الهجري (أم القرى)" + _asof(snap))


BAND_FMT = {"income": texts.money, "net_per_night": texts.money, "occupancy": texts.pct, "adr": texts.money,
            "rating": lambda v: texts.num(v, 2)}
BAND_UNIT = {"income": "ريال", "net_per_night": "ريال", "adr": "ريال", "occupancy": "", "rating": "من 5"}


def ch_peers(snap, u):
    p = u.get("peers") or {}
    scope = next((b.get("scope") for b in p.values() if b), "peers")
    title = "مكانك بين الشقق المشابهة" if scope == "peers" else "مكانك بين شققنا"
    rows = []
    for k in ("income", "net_per_night", "occupancy", "adr", "rating"):
        b = p.get(k)
        if not b:
            continue
        name, hint = texts.METRIC[k]
        fmt = BAND_FMT[k]
        rows.append('<div class="brow"><div class="nm">%s<small>%s</small></div>%s<div class="vr"><b><span class="n">%s</span>%s</b>%s</div></div>' % (
            _e(name), _e(hint), charts.band(b, fmt, name), _e(fmt(b["value"])),
            (' <small class="mute">%s</small>' % _e(BAND_UNIT[k])) if BAND_UNIT[k] else "", _chip(b)))
    if not rows:
        inner = '<p class="empty">%s</p>' % _e(texts.EMPTY["peers"])
    else:
        lede = ("نقارن شقتك بشقق عوجا التي لها %s ونشطة طوال الفترة." % texts.bedrooms(u.get("bedrooms"))
                if scope == "peers" else "نقارن شقتك بكل شقق عوجا النشطة طوال الفترة.")
        inner = '<p class="lede">%s</p><div class="bands">%s</div><div class="keyrow">%s</div>' % (
            _e(lede), "".join(rows), charts.band_key())
        fs = u.get("fair_share")
        if fs is not None:
            inner += ('<div class="fair"><b class="n">%d</b><p>نصيب شقتك العادل من الدخل: 100 يعني أنها تكسب بقدر الشقق '
                      'المقارنة لكل ليلة متاحة، وما فوق 100 يعني أكثر من نصيبها.</p></div>') % fs
    mk = (snap["owner"].get("market") or {}).get("airdna") or {}
    src = texts.SRC_PEERS + _asof(snap)
    if mk.get("occupancy_pct") is not None:
        src += " · السوق في الرياض: إشغال %s٪ ومتوسط ليلة %s ريال (AirDNA، %s)" % (
            texts.num(mk["occupancy_pct"], 0), texts.money(mk.get("adr_sar")), texts.source_date_ar(mk.get("as_of")))
    return _frame(texts.CH["peers"], u["name"], '<h2 class="t">%s</h2>%s' % (_e(title), inner), src)


def _steps(f, maxv, me):
    rows = [("تظهر في البحث", 10000), ("يفتحون الإعلان", f["views"]), ("يحجزون", f["bookings"])]
    out = []
    for label, v in rows:
        w = max(1.5, 100.0 * float(v) / float(maxv)) if maxv else 0
        out.append('<div class="step%s"><div class="bx" style="width:%.1f%%"></div><div class="tx"><b class="n">%s</b>%s</div></div>' % (
            " me" if me else "", w, texts.num(v, 1 if (isinstance(v, float) and v < 100 and not float(v).is_integer()) else 0), _e(label)))
    return "".join(out)


def ch_funnel(snap, u):
    ab = u.get("airbnb")
    if not ab or not ab.get("funnel"):
        body = '<h2 class="t">%s</h2><p class="empty">%s</p>' % (_e(texts.CH["funnel"]), _e(texts.EMPTY["funnel"]))
        return _frame(texts.CH["funnel"], u["name"], body, "المصدر: تقرير فرص المضيف من Airbnb")
    f, pf = ab["funnel"], ab.get("peer")
    cols = '<div><h4>شقتك</h4>%s</div>' % _steps(f, 10000, True)
    if pf:
        cols += '<div><h4>%s</h4>%s</div>' % ("الوسيط بين الشقق المشابهة" if pf.get("scope") == "peers" else "الوسيط بين شققنا",
                                             _steps(pf, 10000, False))
    gauge = '<div class="gauge"><div><span class="big n">%s</span></div><p>يفتح الإعلانَ <b class="n">%s</b> من كل 100 ظهور%s، ويحجز <b class="n">%s٪</b> ممن يفتحونه%s.</p>%s</div>' % (
        texts.num(f["ctr100"], 1), texts.num(f["ctr100"], 1),
        (" (الوسيط <span class='n'>%s</span>)" % texts.num(pf["ctr100"], 1)) if pf else "",
        texts.num(f["conv"], 2), (" (الوسيط <span class='n'>%s٪</span>)" % texts.num(pf["conv"], 2)) if pf else "",
        '<span class="tag">مفضّل الضيوف</span>' if ab.get("guest_favorite") else "")
    promos = '<p class="more">إعدادات العروض الآن: %s.</p>' % _e("، ".join(ab.get("promos") or []))
    body = ('<h2 class="t">%s</h2><p class="lede">من كل 10,000 مرة تظهر فيها الشقة في بحث Airbnb:</p>'
            '<div class="fun">%s</div>%s%s') % (_e("من البحث إلى الحجز"), cols, gauge, promos)
    return _frame(texts.CH["funnel"], u["name"], body,
                  "المصدر: تقرير فرص المضيف من Airbnb، بيانات %s" % (texts.date_ar(ab["data_as_of"]) if ab.get("data_as_of") else ""))


def ch_plan(snap, u):
    acts = u.get("actions") or []
    if not acts:
        return _frame(texts.CH["plan"], u["name"], '<h2 class="t">%s</h2><p class="empty">%s</p>' % (
            _e(texts.CH["plan"]), _e(texts.EMPTY["plan"])), "المصدر: بيانات الشقة في هذا العرض")
    pages = _pages(acts, 6)
    out = []
    for i, pg in enumerate(pages):
        items = "".join('<div class="it%s"><div><b>%s</b><p>%s</p><em>بحلول <bdi>%s</bdi></em></div></div>' % (
            " owner" if a.get("side") == "owner" else "", _e(("مطلوب منك: " if a.get("side") == "owner" else "") + a["owner_text"]),
            _e(a["evidence"]), _e(texts.date_ar(a["due"]))) for a in pg)
        body = '<h2 class="t">%s</h2><div class="plan">%s</div>%s' % (
            _e("ما اكتشفناه، وما نطبّقه من الآن" if i == 0 else "ما نطبّقه من الآن (تابع)"), items, _more(i, pages))
        out.append(_frame(texts.CH["plan"], u["name"], body, "المصدر: الأرقام نفسها في فصول هذا العرض"))
    return out


def ch_forecast(snap, u):
    fc = u.get("forecast")
    meet = snap["meta"]["meeting_date"]
    import datetime as _dt
    nxt_meet = _dt.date.fromisoformat(meet) + _dt.timedelta(days=91)
    close = '<p class="close">%s<span>الاجتماع القادم: قرابة <bdi>%s</bdi></span></p>' % (_e(texts.CLOSING), _e(texts.date_ar(nxt_meet)))
    if not fc:
        body = '<h2 class="t">%s</h2><p class="empty">%s</p>%s' % (_e(texts.CH["forecast"]), _e(texts.EMPTY["forecast"]), close)
        return _frame(texts.CH["forecast"], u["name"], body, texts.SRC_STATEMENT)
    span = "من %s إلى %s" % (texts.month_ar(fc["months"][0]), texts.month_ar(fc["months"][-1], True))
    how = ("مجموع آخر ثلاثة أشهر كاملة" if fc["method"] == "pace"
           else "الموسم نفسه في السنة الماضية × وتيرة آخر ثلاثة أشهر")
    ups = "".join('<li>%s: <span class="n">+%s٪</span></li>' % (_e(texts.UPLIFT.get(i["key"], i["key"])), texts.num(i["pct"], 0))
                  for i in fc["uplifts"])
    if fc.get("capped"):
        ups += '<li>المجموع محدود بسقف <span class="n">%s٪</span></li>' % texts.num(fc["total_pct"], 0)
    body = ('<h2 class="t">%s</h2><p class="lede">رقمان من بيانات شقتك نفسها: أين نصل إذا استمر كل شيء كما هو، وأين نستهدف أن نصل بعد الخطة. الهدف رقم نعمل عليه، وليس وعداً.</p>'
            '<div class="tgt"><div class="col"><small>على الوتيرة الحالية</small><b><span class="n">%s</span><em>ريال صافٍ</em></b><ul><li>%s</li></ul></div>'
            '<div class="col g"><small>الهدف بعد الخطة</small><b><span class="n">%s</span><em>ريال صافٍ</em></b><ul>%s</ul></div></div>%s') % (
        _e("الربع القادم: " + span), texts.money(fc["base"]), _e(how), texts.money(fc["target"]), ups or "<li>بدون إضافات</li>", close)
    return _frame(texts.CH["forecast"], u["name"], body, texts.SRC_STATEMENT + "؛ الهدف تقديري ومبني على الافتراضات المكتوبة أعلاه")


def _pages(items, per):
    return [items[i:i + per] for i in range(0, len(items), per)] or [[]]


def _more(page_i, pages):
    return ('<p class="more">تتمة في الشريحة التالية</p>' if page_i < len(pages) - 1 else "")


def ch_log(snap, u):
    lg = u.get("log") or {"events": [], "counters": {}}
    c = lg["counters"]
    ctrs = [(c.get("maint", 0), "تذكرة صيانة"), (c.get("rr", 0), "طلب تعويض"), (c.get("reviews", 0), "تقييم"),
            (c.get("price_nights", 0), "ليلة رُوجع سعرها"),
            (c.get("recovery", 0), "اتصال متابعة") if not c.get("direct") else (c.get("direct", 0), "حجز مباشر")]
    head = '<div class="ctrs">%s</div>' % "".join('<div><b><span class="n">%s</span></b><small>%s</small></div>' % (texts.num(n), _e(t)) for n, t in ctrs)
    if c.get("cleaning_score"):
        head += '<p class="more">تقييم الضيوف للنظافة بعد إقامتهم: <span class="n">%s</span> من 5</p>' % texts.num(c["cleaning_score"], 2)
    ev = lg["events"]
    if not ev:
        return [_frame(texts.CH["log"], u["name"], '<h2 class="t">%s</h2>%s<p class="empty">%s</p>' % (
            _e("سجلّ الشقة في هذه الفترة"), head, _e(texts.EMPTY["log"])), texts.SRC_OPS)]
    pages = _pages(ev, 9)
    out = []
    for i, pg in enumerate(pages):
        lis = "".join('<li class="k-%s"><span class="d">%s</span><span>%s</span></li>' % (
            _e(e["kind"]), _e(texts.day_month_ar(e["date"])), _e(e["text"])) for e in pg)
        out.append(_frame(texts.CH["log"], u["name"], '<h2 class="t">%s</h2>%s<ul class="tline">%s</ul>%s' % (
            _e("سجلّ الشقة في هذه الفترة" if i == 0 else "سجلّ الشقة (تابع)"), head if i == 0 else "", lis, _more(i, pages)),
            texts.SRC_OPS))
    return out


def ch_maint(snap, u):
    m = u.get("maint") or {"rows": [], "stats": {}}
    st = m["stats"]
    if not m["rows"]:
        return [_frame(texts.CH["maint"], u["name"], '<h2 class="t">%s</h2><p class="empty">%s</p>' % (
            _e("الصيانة"), _e(texts.EMPTY["maint"])), texts.SRC_OPS)]
    mh = st.get("median_hours")
    stats = ('<div class="mstats"><div><small>التذاكر</small><b><span class="n">%s</span></b></div><div><small>مفتوحة الآن</small><b><span class="n">%s</span></b></div>'
             '<div><small>الوسيط حتى الإغلاق</small><b><span class="n">%s</span><em>ساعة</em></b></div>'
             '<div><small>التكلفة</small><b><span class="n">%s</span><em>ريال</em></b></div></div>') % (
        texts.num(st.get("count")), texts.num(st.get("open_now")), texts.num(mh, 0) if mh is not None else "—",
        texts.money(st.get("total_cost")))
    if st.get("team_share") is not None:
        stats += '<p class="more">اكتشفها فريقنا قبل أن يبلّغ الضيف: <span class="n">%d٪</span> من التذاكر.</p>' % st["team_share"]
    pages = _pages(m["rows"], 7)
    out = []
    for i, pg in enumerate(pages):
        trs = "".join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td%s>%s</td><td class="n">%s</td></tr>' % (
            _e(texts.day_month_ar(r["date"])), _e(r["category"]), _e(r["summary"]), _e(r["source_ar"]),
            ' class="open"' if r["open"] else "", _e("مفتوحة" if r["open"] else ("%s ساعة" % texts.num(r["hours"], 0) if r["hours"] is not None else "مغلقة")),
            texts.money(r["cost"]) if r["cost"] else "—") for r in pg)
        table = ('<table class="tb"><thead><tr><th>التاريخ</th><th>التصنيف</th><th>الوصف</th><th>من اكتشفها</th>'
                 '<th>الإغلاق</th><th>التكلفة</th></tr></thead><tbody>%s</tbody></table>') % trs
        out.append(_frame(texts.CH["maint"], u["name"], '<h2 class="t">%s</h2>%s%s%s' % (
            _e("كل تذكرة، ومتى أُغلقت، وكم كلّفت" if i == 0 else "الصيانة (تابع)"), stats if i == 0 else "", table, _more(i, pages)),
            texts.SRC_OPS))
    return out


def ch_claims(snap, u):
    cl = u.get("claims") or {"rows": [], "ring": {}}
    rows, ring = cl["rows"], cl["ring"]
    if not rows:
        return [_frame(texts.CH["claims"], u["name"], '<h2 class="t">%s</h2><p class="empty">%s</p>' % (
            _e("طلبات التعويض"), _e(texts.EMPTY["claims"])), texts.SRC_RR)]
    top = ('<div class="rrtop">%s<div><div class="kv"><span>طالبنا به (طلبات مغلقة)</span><b><span class="n">%s</span> ريال</b></div>'
           '<div class="kv own"><span>استلمناه</span><b><span class="n">%s</span> ريال</b></div>'
           '<div class="kv"><span>طلبات قيد المراجعة</span><b class="n">%s</b></div></div></div>') % (
        charts.ring(ring.get("rate"), "نسبة ما استُرد", "استلمنا %s من %s ريال طالبنا بها في الطلبات المغلقة." % (
            texts.money(ring.get("received")), texts.money(ring.get("claimed")))),
        texts.money(ring.get("claimed")), texts.money(ring.get("received")), texts.num(ring.get("open")))
    pages = _pages(rows, 3)
    out = []
    for i, pg in enumerate(pages):
        lis = []
        for r in pg:
            items = "، ".join(r["items"][:4]) + ((" وبنود أخرى" if (len(r["items"]) > 4 or r["items_hidden"]) else ""))
            right = '<b>%s</b><span class="st %s">%s</span><p>%s</p>%s%s' % (
                _e(r["type_ar"]), _e(r["chip"]), _e(r["chip_ar"]), _e(items or "—"),
                ('<p>رد Airbnb: %s</p>' % _e(r["answer_ar"])) if r.get("answer_ar") else "",
                ('<p class="dl">آخر موعد لتقديمه في <bdi>AirCover</bdi>: <bdi>%s</bdi> (باقي <span class="n">%d</span> يوم)</p>' % (
                    _e(texts.date_ar(r["deadline"]["date"])), max(0, r["deadline"]["days_left"])))
                if r.get("deadline") else "")
            left = '<div class="amt"><bdi>%s</bdi><br>طالبنا: <span class="n">%s</span> ريال<br>استلمنا: %s%s</div>' % (
                _e(texts.date_ar(r["date"])), texts.money(r["claimed"]) if r["claimed"] is not None else "—",
                ('<span class="n">%s</span> ريال' % texts.money(r["received"])) if r["received"] is not None else "—",
                ("<br>" + _e(r["payer_ar"])) if r.get("payer_ar") else "")
            lis.append("<li><div>%s</div>%s</li>" % (right, left))
        out.append(_frame(texts.CH["claims"], u["name"], '<h2 class="t">%s</h2>%s<ul class="claims">%s</ul>%s' % (
            _e("ما طالبنا به لشقتك، وما رجع" if i == 0 else "طلبات التعويض (تابع)"), top if i == 0 else "",
            "".join(lis), _more(i, pages)), texts.SRC_RR))
    return out


def _review_pages(rows, budget=620, most=3):
    pages, cur, size = [], [], 0
    for r in rows:
        ln = len(r.get("text") or "") + 80
        if cur and (len(cur) >= most or size + ln > budget):
            pages.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += ln
    if cur:
        pages.append(cur)
    return pages or [[]]


def ch_reviews(snap, u):
    rv = u.get("reviews") or {"rows": [], "summary": {}}
    rows, sm = rv["rows"], rv["summary"]
    if not rows:
        return [_frame(texts.CH["reviews"], u["name"], '<h2 class="t">%s</h2><p class="empty">%s</p>' % (
            _e("ماذا قال الضيوف"), _e(texts.EMPTY["reviews"])), texts.SRC_REVIEWS)]
    subs = sm.get("subscores") or []
    top = ('<div class="rvtop"><div><span class="lbl mute">متوسط تقييمات الفترة</span><div class="mega"><span class="n">%s</span><em>من 5</em></div>'
           '<p class="more">%s تقييماً · الهدف أعلى من <span class="n">%s</span></p></div><div>%s</div></div>') % (
        texts.num(sm.get("mean"), 2), texts.num(sm.get("count")), texts.num(sm.get("target"), 2),
        charts.score_bars(subs, "التقييمات التفصيلية", "متوسط كل جانب من 5.", target=sm.get("target")) if subs else "")
    pages = _review_pages(rows)
    out = []
    for i, pg in enumerate(pages):
        lis = "".join('<li><div class="h"><span class="stars"><span class="n">%s</span> من 5</span> · <bdi><b>%s</b></bdi> · <bdi>%s</bdi></div><p>%s</p>%s</li>' % (
            ("%g" % r["stars"]), _e(r["first_name"]), _e(texts.date_ar(r["date"])), _e(r["text"] or "بلا تعليق مكتوب"),
            ('<div class="fu">%s</div>' % _e(r["followed"])) if r.get("followed") else "") for r in pg)
        out.append(_frame(texts.CH["reviews"], u["name"], '<h2 class="t">%s</h2>%s<ul class="rvs">%s</ul>%s' % (
            _e("كل تقييم في هذه الفترة" if i == 0 else "ماذا قال الضيوف (تابع)"), top if i == 0 else "", lis, _more(i, pages)),
            texts.SRC_REVIEWS))
    return out


def ch_promises(snap):
    pm = snap["owner"].get("promises")
    items = pm.get("items") or []
    if not items:
        body = '<h2 class="t">%s</h2><p class="empty">%s</p>' % (_e(texts.CH["promises"]), _e("لم نسجّل التزامات في الاجتماع الماضي"))
    else:
        lis = "".join('<li><span class="st %s">%s</span><div><b>%s%s</b>%s</div></li>' % (
            {"done": "full", "in_progress": "partial", "not_done": "denied"}[i["status"]], _e(i["status_ar"]),
            _e("علينا: " if i["side"] == "ouja" else "عليك: "), _e(i["text"]),
            ('<p>%s</p>' % _e(i["evidence"])) if i.get("evidence") else
            (('<p>الموعد: <bdi>%s</bdi></p>' % _e(texts.date_ar(i["due"]))) if i.get("due") else "")) for i in items)
        done = sum(1 for i in items if i["status"] == "done")
        body = ('<h2 class="t">%s</h2><p class="lede">من اجتماع <bdi>%s</bdi>: نفّذنا <span class="n">%d</span> من <span class="n">%d</span>.</p>'
                '<ul class="proms">%s</ul>') % (_e(texts.CH["promises"]), _e(texts.date_ar(pm["meeting_date"])), done, len(items), lis)
    return _frame(texts.CH["promises"], None, body, "المصدر: سجل الاجتماع الماضي وتذاكر عوجا")


def ch_agreed(snap):
    ag = snap["owner"].get("agreed") or {}
    dec, com = ag.get("decisions") or [], ag.get("commitments") or []
    rows = "".join('<li><span class="st full">قرار</span><div><b>%s</b>%s</div></li>' % (
        _e(d["text"]), ('<p><span class="n">%s</span> ريال</p>' % texts.money(d["amount_sar"])) if d.get("amount_sar") else "") for d in dec)
    rows += "".join('<li><span class="st %s">%s</span><div><b>%s</b>%s</div></li>' % (
        "open" if c["side"] == "ouja" else "partial", "علينا" if c["side"] == "ouja" else "عليك", _e(c["text"]),
        ('<p>بحلول <bdi>%s</bdi></p>' % _e(texts.date_ar(c["due"]))) if c.get("due") else "") for c in com)
    body = '<h2 class="t">%s</h2>%s' % (_e(texts.CH["agreed"]), ('<ul class="proms">%s</ul>' % rows) if rows else
                                        '<p class="empty">%s</p>' % _e("لم نسجّل قرارات في هذا الاجتماع"))
    return _frame(texts.CH["agreed"], None, body, "المصدر: سجل الاجتماع بتاريخ %s" % texts.date_ar(snap["meta"]["meeting_date"]))


UNIT_CHAPTERS = (("summary", ch_summary), ("money", ch_money), ("monthly", ch_monthly),
                 ("peers", ch_peers), ("funnel", ch_funnel), ("log", ch_log), ("maint", ch_maint),
                 ("claims", ch_claims), ("reviews", ch_reviews), ("plan", ch_plan), ("forecast", ch_forecast))


def chapters(snap):
    """-> [{key, lid, title, html}] in presentation order. Built from snapshot["owner"] only."""
    o = snap["owner"]
    units = o["units"]
    out = []
    if len(units) > 1:
        out.append({"key": "portfolio", "lid": None, "title": texts.CH["portfolio"], "html": ch_portfolio(snap)})
    for n, u in enumerate(units):
        out.append({"key": "cover", "lid": u["lid"], "title": texts.CH["cover"], "html": ch_cover(snap, u)})
        if n == 0 and o.get("promises") is not None:
            out.append({"key": "promises", "lid": None, "title": texts.CH["promises"], "html": ch_promises(snap)})
        for key, fn in UNIT_CHAPTERS:
            html = fn(snap, u)
            for j, h in enumerate(html if isinstance(html, list) else [html]):
                out.append({"key": key, "lid": u["lid"], "title": texts.CH[key] + (" (تابع)" if j else ""), "html": h})
    if o.get("agreed"):
        out.append({"key": "agreed", "lid": None, "title": texts.CH["agreed"], "html": ch_agreed(snap)})
    return out


# ------------------------------------------------------------------ pages
def _page(title, body_cls, body, css, font_base, script=None, extra_head=""):
    js = ('<script src="%s"></script>' % _e(script)) if script else ""
    return ('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex,nofollow"><title>%s</title><style>%s%s%s</style>%s</head>'
            '<body class="%s">%s%s</body></html>') % (
        _e(title), font_css(font_base), CSS, css, extra_head, body_cls, body, js)


def presentation_html(snap, mid, js_v="0", font_base="/meet/font/"):
    chs = chapters(snap)
    slides = "".join('<section class="slide%s" data-i="%d" data-key="%s" aria-label="%s">%s</section>' % (
        " on" if i == 0 else "", i, c["key"], _e(c["title"]), c["html"]) for i, c in enumerate(chs))
    body = ('<main class="stage" id="stage" data-meeting="%d" data-total="%d">%s</main>'
            '<div class="prog" aria-hidden="true"><i id="prog"></i></div><div class="black" id="black" hidden></div>') % (
        int(mid), len(chs), slides)
    units = snap["owner"]["units"]
    title = "اجتماع المالك · " + (units[0]["name"] if len(units) == 1 else "شقق المالك")
    return _page(title, "deck", body, "", font_base, "/meet/static/stage.js?v=%s" % js_v)


def talking_points(snap, chs):
    """Presenter-only bullets per chapter: [(text, internal_bool)]. Reads snapshot["presenter"]."""
    pr = snap.get("presenter") or {}
    units = {u["lid"]: u for u in snap["owner"]["units"]}
    out = []
    for c in chs:
        u = units.get(c["lid"])
        pts = []
        pi = (pr.get("peer_internal") or {}).get(c["lid"]) or (pr.get("peer_internal") or {}).get(str(c["lid"])) or {}
        if c["key"] == "portfolio":
            pts.append(("ابدأ بالصورة الكاملة لشققه، ثم ادخل في كل شقة.", False))
        elif c["key"] == "cover":
            pts.append(("الفترة: %s." % texts.range_ar(snap["owner"]["period"]["start"], snap["owner"]["period"]["end"]), False))
            if snap["owner"]["period"].get("partial"):
                pts.append(("الشهر الأخير حتى تاريخه وليس شهراً كاملاً.", False))
        elif c["key"] == "summary" and u:
            from . import engine
            _k, w = engine.weakness(u)
            pts.append((("نقطة الضعف الأولى: %s." % w) if w else "لا توجد نقطة ضعف واضحة في هذه الفترة.", False))
        elif c["key"] == "money" and u:
            pts.append(("نسبة الإدارة من شروط العقد بتاريخ نهاية الفترة: %s٪." % texts.num(u.get("mgmt_pct"), 1), False))
            if u.get("cleaning_type") == "owner":
                pts.append(("المالك يدفع اشتراك التنظيف حسب عقده.", False))
            if not u["money"]["waterfall"]["reconciled"]:
                pts.append(("داخلي: بنود الكشف لا تطابق الصافي، راجع الكشف قبل الاجتماع.", True))
        elif c["key"] == "monthly" and u:
            tr = [t for t in (u.get("trend") or []) if not t.get("partial")]
            if tr:
                best = max(tr, key=lambda t: t["net"])
                worst = min(tr, key=lambda t: t["net"])
                pts.append(("أفضل شهر %s (%s ريال)، وأضعف شهر %s (%s ريال)." % (
                    texts.month_ar(best["m"], True), texts.money(best["net"]),
                    texts.month_ar(worst["m"], True), texts.money(worst["net"])), False))
        elif c["key"] == "peers":
            for k, inn in sorted(pi.items()):
                if inn and inn.get("n"):
                    pts.append(("داخلي (لا تذكره للمالك): «%s» قورنت بـ %d شقة، %s." % (
                        texts.METRIC.get(k, (k,))[0], inn["n"], "نفس عدد الغرف" if inn.get("scope") == "peers" else "كل الشقق"), True))
                elif inn and inn.get("reason") == "too_few":
                    pts.append(("داخلي: «%s» بلا مقارنة لأن الشقق التي لها بيانات قليلة." % texts.METRIC.get(k, (k,))[0], True))
        elif c["key"] == "funnel" and u:
            fi = pi.get("funnel")
            if fi and fi.get("n"):
                pts.append(("داخلي (لا تذكره للمالك): الوسيط من %d إعلاناً في التقرير، %s." % (
                    fi["n"], "نفس عدد الغرف" if fi.get("scope") == "peers" else "كل الإعلانات"), True))
            if not u.get("airbnb"):
                pts.append(("الشقة غير مربوطة بتقرير Airbnb — اربطها من التبويب قبل الاجتماع.", True))
        elif c["key"] == "plan" and u:
            pl = (pr.get("plan") or {}).get(c["lid"]) or (pr.get("plan") or {}).get(str(c["lid"])) or {}
            for a in u.get("actions") or []:
                pts.append(("%s ← %s" % (a["role"], a["owner_text"][:60]), True))
            for n in pl.get("notes") or []:
                pts.append(("داخلي: " + n, True))
            st = pl.get("stack")
            if st and st.get("warn"):
                pts.append(("داخلي: أسوأ خصم مجمّع ممكن %s٪ يتجاوز السقف %s٪ — راجع الخصومات قبل التجربة." % (
                    texts.num(st["combined"] * 100, 0), texts.num(st["ceiling"] * 100, 0)), True))
            for k, v in sorted((pr.get("levers") or {}).items()):
                pts.append(("قرار %s: %s" % (texts.LEVER_AR.get(k, k), texts.DECISION_AR.get(v.get("decision"), v.get("decision"))), True))
        elif c["key"] == "forecast" and u and u.get("forecast"):
            fc = u["forecast"]
            pts.append(("الأساس %s ريال (%s)، والهدف %s ريال. قلها: «هدف، وليس وعداً»." % (
                texts.money(fc["base"]), "موسمي" if fc["method"] == "seasonal" else "على الوتيرة", texts.money(fc["target"])), False))
        elif c["key"] == "log" and u and not c["title"].endswith("(تابع)"):
            pm = u.get("permit")
            if pm is None:
                pts.append(("داخلي: تصريح وزارة السياحة لهذه الشقة غير مسجّل في «التصاريح».", True))
            elif pm.get("days_left") is not None:
                pts.append(("تصريح وزارة السياحة باسم المالك: باقي %s يوماً%s." % (
                    texts.num(pm["days_left"]), "، والتجديد مفتوح" if pm.get("renewal_open") else ""), False))
        elif c["key"] == "maint" and u and not c["title"].endswith("(تابع)"):
            st = (u.get("maint") or {}).get("stats") or {}
            if st.get("open_now"):
                pts.append(("%s تذكرة مفتوحة الآن: قل له متى تُغلق." % texts.num(st["open_now"]), False))
        elif c["key"] == "claims" and u and not c["title"].endswith("(تابع)"):
            for r in (u.get("claims") or {}).get("rows") or []:
                if r.get("deadline") and r["deadline"]["days_left"] <= 5:
                    pts.append(("موعد AirCover لطلب %s يقترب (%s يوم)." % (r["type_ar"], max(0, r["deadline"]["days_left"])), True))
        elif c["key"] == "reviews" and u and not c["title"].endswith("(تابع)"):
            priv = (pr.get("private_reviews") or {}).get(c["lid"]) or (pr.get("private_reviews") or {}).get(str(c["lid"])) or []
            for p in priv[:6]:
                pts.append(("داخلي — ملاحظة خاصة من ضيف (%s، %s نجوم): %s" % (texts.date_ar(p["date"]), "%g" % p["stars"], p["text"]), True))
        out.append(pts)
    return out


RECORDER = (
    '<section class="nt-rec" id="rec"><h2>سجل الاجتماع</h2>'
    '<form class="rf" data-kind="decision"><label>قرار وافق عليه المالك<input name="text" required maxlength="500" '
    'placeholder="وافق على تصوير جديد"></label><label>المبلغ (ريال، اختياري)<input name="amount_sar" inputmode="decimal"></label>'
    '<button type="submit">أضف القرار</button></form>'
    '<form class="rf" data-kind="ouja"><label>التزام علينا<input name="text" required maxlength="500"></label>'
    '<label>الدور<input name="role" maxlength="40" placeholder="العمليات / المنصة / المحتوى"></label>'
    '<label>الموعد<input name="due" type="date"></label><label>رقم تذكرة مرتبطة (اختياري)<input name="linked_ticket" maxlength="64"></label>'
    '<button type="submit">أضف التزاماً علينا</button></form>'
    '<form class="rf" data-kind="owner"><label>التزام على المالك<input name="text" required maxlength="500"></label>'
    '<label>الموعد<input name="due" type="date"></label><button type="submit">أضف التزاماً على المالك</button></form>'
    '<ul id="recList" class="rec-list"></ul><p id="recMsg" class="rec-msg" aria-live="polite"></p>'
    '<button type="button" class="rec-done" data-presented="1">انتهى الاجتماع</button></section>')

RECORDER_CSS = """
.nt-rec{margin-top:22px;border-top:1px solid rgba(255,255,255,.14);padding-top:12px}
.nt-rec h2{font-size:13px;color:#D9C194;font-weight:500;margin-bottom:8px}
.rf{display:grid;gap:8px;padding:12px 0;border-bottom:1px solid rgba(255,255,255,.08)}
.rf label{display:grid;gap:4px;font-size:13px;color:#9AA6B6}
.rf input{font:inherit;font-size:15px;color:#FFFFFF;background:#122944;border:1px solid rgba(255,255,255,.2);border-radius:8px;min-height:44px;padding:6px 10px}
.rf input::placeholder{color:#93A0B2}
.rf button,.rec-done{font:inherit;font-size:15px;font-weight:700;color:#0B1A2E;background:#D9C194;border:0;border-radius:8px;min-height:44px;padding:8px 16px;cursor:pointer;justify-self:start;transition:transform .12s cubic-bezier(.23,1,.32,1)}
.rf button:active,.rec-done:active{transform:scale(.97)}
.rec-list{list-style:none;margin-top:12px}
.rec-list li{display:flex;justify-content:space-between;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.08)}
.rec-list li span{font-size:12px;color:#D9C194;margin-inline-end:8px}
.rec-list button{font:inherit;font-size:13px;color:#F2B8B3;background:none;border:0;cursor:pointer;min-height:36px}
.rec-msg{font-size:13px;color:#9FD0BC;min-height:20px;margin:8px 0}
.rec-done{background:#F7F4EE;margin-top:4px}
"""


def notes_html(snap, mid, js_v="0", font_base="/meet/font/"):
    chs = chapters(snap)
    pts = talking_points(snap, chs)
    names = {u["lid"]: u["name"] for u in snap["owner"]["units"]}
    cards = "".join(
        '<div class="nt-card%s" data-i="%d"><div class="nt-now"><small>الشريحة <span class="n">%d / %d</span></small><b>%s</b>'
        '<div class="nt-next">%s</div></div><div class="nt-pts"><h2>نقاط الحديث</h2><ul>%s</ul></div></div>' % (
            " on" if i == 0 else "", i, i + 1, len(chs), _e(c["title"] + ((" · " + names[c["lid"]]) if c["lid"] in names else "")),
            _e(("التالية: " + chs[i + 1]["title"]) if i + 1 < len(chs) else "آخر شريحة"),
            "".join('<li%s>%s</li>' % (' class="int"' if internal else "", _e(t)) for t, internal in p) or "<li>—</li>")
        for i, (c, p) in enumerate(zip(chs, pts)))
    ready = (snap.get("presenter") or {}).get("readiness") or []
    notes = (snap.get("presenter") or {}).get("notes") or []
    rl = "".join('<li class="%s"><span>%s</span>%s</li>' % (
        _e(r["level"]), "أحمر" if r["level"] == "red" else "تنبيه", _e(r["text_ar"])) for r in ready)
    rl += "".join('<li class="yellow"><span>ملاحظة</span>%s</li>' % _e(n.get("text_ar")) for n in notes)
    if not rl:
        rl = '<li class="nt-ok">كل الفحوص سليمة.</li>'
    jump = "".join('<option value="%d">%s</option>' % (i, _e(names.get(c["lid"]) or c["title"]))
                   for i, c in enumerate(chs) if c["key"] in ("cover", "portfolio"))
    body = ('<header class="nt-top"><h1>ملاحظاتي · لا تشارك هذه النافذة</h1><span class="n" id="clock">00:00</span></header>'
            '<div class="nt-ctl"><button type="button" data-go="-1" aria-label="الشريحة السابقة">السابقة</button>'
            '<button type="button" data-go="1" aria-label="الشريحة التالية">التالية</button>%s</div>'
            '<div id="cards" data-meeting="%d" data-total="%d">%s</div>'
            '<section class="nt-ready"><h2>فحوص قبل العرض</h2><ul>%s</ul></section>' + RECORDER) % (
        ('<select id="jump" aria-label="انتقل إلى شقة">%s</select>' % jump) if jump.count("<option") > 1 else "",
        int(mid), len(chs), cards, rl)
    return _page("ملاحظاتي · اجتماع المالك", "notes", body, NOTES_CSS + RECORDER_CSS, font_base, "/meet/static/notes.js?v=%s" % js_v)


# ------------------------------------------------------------------ the owner's link (phone) and the PDF (S5)
DOC_CSS = """
body.doc{background:#E9E5DD;padding:0 0 40px}
.doc-top{max-width:1280px;margin:0 auto;padding:22px 16px 10px;display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.doc-top b{font-family:var(--f-disp);font-weight:900;font-size:22px}
.doc-top span{color:var(--mute);font-size:14px}
.doc-top a{color:var(--ink);font-weight:700;font-size:14px}
.pages{max-width:1280px;margin:0 auto;display:grid;gap:18px;padding:0 16px}
.doc .slide{position:relative;inset:auto;opacity:1;visibility:visible;aspect-ratio:16/9;width:100%;box-shadow:0 1px 0 var(--line),0 14px 30px -24px rgba(30,24,16,.28);border-radius:4px;transition:none}
.exp{background:var(--paper);border-radius:4px;padding:20px 18px}
.exp h3{font-family:var(--f-disp);font-weight:900;font-size:24px;margin-bottom:10px}
.exp table{width:100%;border-collapse:collapse;font-size:14px}
.exp th{text-align:start;color:var(--mute);font-weight:500;border-bottom:1.5px solid var(--ink);padding:6px 4px}
.exp td{border-bottom:1px solid var(--line);padding:8px 4px;vertical-align:top}
.exp a{color:var(--gold-t);font-weight:700}
.doc-foot{max-width:1280px;margin:18px auto 0;padding:0 16px;color:var(--mute);font-size:13px;line-height:1.7}
@media (max-width:760px){
 .doc .slide{aspect-ratio:auto;container-type:normal}
 .doc .in{position:relative;inset:auto;--u:11px;padding:20px 16px 16px}
 .doc .slide .in{min-height:0}
 .doc .kpis,.doc .trio,.doc .split,.doc .fun,.doc .plan,.doc .tgt,.doc .rrtop,.doc .rvtop,.doc .claims li,.doc .proms li{grid-template-columns:1fr}
 .doc .brow{grid-template-columns:1fr;gap:6px}
 .doc .mstats{grid-template-columns:1fr 1fr}
 .doc .ctrs{grid-template-columns:1fr 1fr 1fr}
 .doc .kpis>div,.doc .ctrs div{border-inline-start:0;padding-inline-start:0}
 .doc .side{border-inline-start:0;padding-inline-start:0}
 .doc .tb{display:block;overflow-x:auto}
 .doc .keyrow svg{margin-inline-start:0;width:100%}
 .doc .cv h1{margin-top:28px}
 .doc .s-foot{margin-top:16px}
 .doc .units thead{display:none}
 .doc .units,.doc .units tbody{display:block}
 .doc .units tr{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px 12px;padding:12px 0;border-top:1px solid rgba(255,255,255,.16)}
 .doc .units td{display:block;border:0;padding:0}
 .doc .units td:first-child{grid-column:1 / -1}
 .doc .units td[data-l]::before{content:attr(data-l);display:block;font-size:11px;color:#9AA6B6;margin-bottom:2px}
 .doc .headline{font-size:28px;max-width:none}
 .doc h2.t{font-size:28px}
 .doc .s-foot{flex-direction:column;gap:4px}
 .exp table{display:block;overflow-x:auto}
}
"""

PRINT_CSS = """
@page{size:1280px 720px;margin:0}
html,body{margin:0;padding:0;background:#FFFFFF}
.print .slide{position:relative;inset:auto;width:1280px;height:720px;opacity:1;visibility:visible;transition:none;page-break-after:always;break-after:page}
.print .slide:last-child{page-break-after:auto;break-after:auto}
"""


def _expenses_html(snap, receipt_token):
    blocks = []
    for u in snap["owner"]["units"]:
        ex = u.get("expenses") or []
        if not ex:
            continue
        rows = "".join('<tr><td><bdi>%s</bdi></td><td>%s</td><td>%s</td><td class="n">%s</td><td>%s</td></tr>' % (
            _e(texts.date_ar(x["date"])) if x.get("date") else "—", _e(x["category"]), _e(x["description"]),
            texts.money(x["amount"]),
            ('<a href="/fin/receipt/%s?t=%s" target="_blank" rel="noopener">الإيصال</a>' % (_e(x["id"]), _e(receipt_token)))
            if (x.get("receipt") and receipt_token and x.get("id")) else "—") for x in ex)
        blocks.append('<section class="exp"><h3>مصاريف <bdi>%s</bdi></h3><table><thead><tr><th>التاريخ</th><th>البند</th>'
                      '<th>الوصف</th><th>المبلغ (ريال)</th><th>الإيصال</th></tr></thead><tbody>%s</tbody></table></section>' % (
                          _e(u["name"]), rows))
    return "".join(blocks)


def owner_page_html(snap, token, receipt_token=None, font_base="/meet/font/"):
    """The owner's read-only link: every chapter of the frozen snapshot, stacked (16:9 on a wide
    screen, flowing text on a phone), plus his statement expense lines with their receipts."""
    chs = chapters(snap)
    pages = "".join('<section class="slide" aria-label="%s">%s</section>' % (_e(c["title"]), c["html"]) for c in chs)
    units = snap["owner"]["units"]
    name = units[0]["name"] if len(units) == 1 else "شققك في عوجا"
    top = ('<header class="doc-top"><b>عوجا</b><span>اجتماع المالك · <bdi>%s</bdi> · <bdi>%s</bdi></span>'
           '<a href="/m/%s.pdf">تحميل PDF</a></header>') % (_e(name), _e(texts.date_ar(snap["meta"]["meeting_date"])), _e(token))
    foot = ('<p class="doc-foot">هذه نسخة ثابتة مما عرضناه في الاجتماع، ولا تتغيّر بعد إرسالها. الأرقام من كشفك الشهري في نظام عوجا. '
            '%s</p>') % _e(texts.CLOSING)
    body = '%s<main class="pages">%s%s</main>%s' % (top, pages, _expenses_html(snap, receipt_token), foot)
    pg = _page("اجتماع المالك · " + name, "doc", body, DOC_CSS, font_base)
    return _number_pages(pg, len(chs))


def _number_pages(html, total):
    """Static page numbers for the stacked owner page / PDF (the stage numbers them in JS)."""
    out, i, marker = [], 0, '<span class="n pg"></span>'
    parts = html.split(marker)
    for k, part in enumerate(parts):
        out.append(part)
        if k < len(parts) - 1:
            i += 1
            out.append('<span class="n pg">%d / %d</span>' % (i, total))
    return "".join(out)


def print_html(snap, font_base):
    """The PDF: the same 16:9 chapters, one per 1280×720 page, fonts from disk."""
    chs = chapters(snap)
    pages = "".join('<section class="slide">%s</section>' % c["html"] for c in chs)
    return _number_pages(_page("اجتماع المالك", "print", pages, PRINT_CSS, font_base), len(chs)), len(chs)
