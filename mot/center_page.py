# -*- coding: utf-8 -*-
"""
mot.center_page — /compliance-center, «مركز الالتزام»: the PUBLIC walkthrough for a
Ministry of Tourism contact.

What it is: the whole journey, on the phone, on ONE DEMO APARTMENT — open a round, tick
the 61/67 components, watch the two percentages move, close the round and see the owner
quotation, the tickets and the evidence file the system produces. Everything is rendered
client-side from the CATALOGUE plus a fixed demo dataset baked in at import time.

What it is NOT: it never touches brain.db, never calls /api/mot/*, and carries no unit count,
unit name, owner, price list or score of ours. The only data on the page is the catalogue
(public ministry structure) and the demo apartment, labelled «نموذج توضيحي» on every
screen. tests/test_mot_center.py greps for that.

ZERO backslashes below the docstring (the DASHBOARD_HTML trap). esprima-parse after edits.
"""
import html as _h
import json

from . import catalogue as C
from . import engine, report

DEMO_UNIT = {"name": "شقة نموذجية — عوجا", "bedrooms": 2, "bathrooms": 2, "beds": 3,
             "owner": "مالك الوحدة (نموذج)"}
# demo prices, SAR — illustrative only, NOT our price list
DEMO_PRICES = {"c21.mattress": 900, "c27.toilet": 350, "c37.smoke_detector": 85,
               "c08.detergents": 60, "c24.blackout": 420, "c37.first_aid": 95,
               "c30.shampoo": 12, "c16.tv": 1400, "c10.iron": 150, "c12.prayer_rug": 45}
DEMO_MISSING = {"c21.mattress": {"qty": 2, "note": "مهترئة — تحتاج تبديل"},
                "c27.toilet": {"note": "الشطاف لا يعمل"},
                "c37.smoke_detector": {},
                "c08.detergents": {},
                "c39.evac_plan": {},
                "c24.blackout": {}}
SERVICE_RATE = 5
VAT_RATE = 15


def _demo_results(has_pool):
    res = {}
    for c in C.components(has_pool):
        if c["key"] in DEMO_MISSING:
            res[c["key"]] = dict(DEMO_MISSING[c["key"]], state="missing")
        else:
            res[c["key"]] = {"state": "available"}
    return res


def _demo_report_html():
    rnd = {"id": 1, "listing_id": 0, "apartment_name": DEMO_UNIT["name"], "has_pool": 0,
           "denominator": 61, "catalogue_version": C.CATALOGUE_VERSION,
           "closed_at": "2026-09-14T11:20:00", "inspector": "مفتش عوجا (نموذج)", "opened_by": ""}
    return report.html_for(rnd, _demo_results(False), [], DEMO_UNIT, DEMO_PRICES, state_dir="/nonexistent")


def build():
    comps = C.components(True)
    sections = [{"key": k, "label": v,
                 "criteria": sorted({c["criterion_no"] for c in comps if c["section"] == k}),
                 "n": len([c for c in comps if c["section"] == k])} for k, v in C.SECTIONS]
    data = {"version": C.CATALOGUE_VERSION, "components": comps, "sections": sections,
            "unit": DEMO_UNIT, "prices": DEMO_PRICES, "missing": DEMO_MISSING,
            "service_rate": SERVICE_RATE, "vat_rate": VAT_RATE,
            "works_sep": engine.WORKS_SEPARATOR, "recheck_days": engine.RECHECK_DAYS,
            "doc_tasks": C.DOCUMENT_TASK_KEY}
    return (TEMPLATE
            .replace("@@DATA@@", json.dumps(data, ensure_ascii=False))
            .replace("@@REPORT@@", _h.escape(_demo_report_html(), quote=True)))


TEMPLATE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>مركز الالتزام — عوجا للإقامة</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&family=Inter:wght@500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#F3EFE8;--panel:#FBF8F2;--ink:#26231F;--body:#3B3731;--muted:#8B8477;--gold:#B29A6A;--gold-deep:#8C7443;--gold-soft:#F0E8D8;
--maroon:#8B3748;--maroon-soft:#F5E4E6;--green:#3F7451;--green-soft:#E3EFE6;--amber:#B4802F;--amber-soft:#F7EBD6;--border:#E5DDCF;
--r:18px;--ease:cubic-bezier(.23,1,.32,1);--font:'IBM Plex Sans Arabic','Tajawal',system-ui,sans-serif;--num:'Inter',sans-serif}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--body);font-family:var(--font);font-size:16px;line-height:1.7}
.wrap{max-width:720px;margin:0 auto;padding:0 18px 80px}
.hero{padding:34px 0 10px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:600;letter-spacing:.02em;color:var(--gold-deep);background:var(--gold-soft);padding:4px 12px;border-radius:999px}
.hero h1{font-size:30px;line-height:1.3;margin:14px 0 8px;color:var(--ink);text-wrap:balance;font-weight:700}
.hero p{margin:0 0 10px;font-size:17px}
.demo{display:inline-flex;gap:6px;align-items:center;font-size:12.5px;color:var(--maroon);background:var(--maroon-soft);padding:4px 12px;border-radius:999px;font-weight:600;margin-top:6px}
.nav{display:flex;gap:6px;overflow:auto;padding:16px 0 6px;position:sticky;top:0;background:linear-gradient(var(--bg) 80%,transparent);z-index:5;scrollbar-width:none}
.nav a{white-space:nowrap;text-decoration:none;font-size:13.5px;font-weight:600;color:var(--muted);background:var(--panel);border:1px solid var(--border);padding:6px 13px;border-radius:999px}
.nav a.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
section{margin-top:40px}
section h2{font-size:22px;color:var(--ink);margin:0 0 6px;font-weight:700}
section .lead{margin:0 0 16px;color:var(--muted);font-size:15px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;box-shadow:0 1px 2px rgba(38,35,31,.04),0 10px 30px rgba(38,35,31,.06)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.sec{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--border);border-radius:14px;background:var(--panel)}
.sec b{font-family:var(--num);font-size:22px;color:var(--ink);min-width:34px;text-align:center}
.sec span{font-size:14px;color:var(--body)}
.sec small{display:block;font-size:12px;color:var(--muted)}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:14px 0}
.steps button{border:1px solid var(--border);background:var(--panel);font:inherit;font-weight:700;font-size:13px;padding:10px 4px;border-radius:12px;color:var(--muted);cursor:pointer;transition:all .18s var(--ease)}
.steps button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.steps button:active{transform:scale(.97)}
.step{display:none}.step.on{display:block}
.kv{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid var(--border);font-size:15px}
.kv:last-child{border-bottom:0}
.kv b{color:var(--ink);font-family:var(--num);font-weight:600}
.seg2{display:inline-flex;border:1px solid var(--border);border-radius:999px;overflow:hidden;background:#fff}
.seg2 button{border:0;background:transparent;font:inherit;font-weight:700;padding:6px 14px;cursor:pointer;color:var(--muted)}
.seg2 button.on{background:var(--gold);color:#fff}
.phone{margin:14px auto 0;max-width:390px;background:#FBF8F2;border:1px solid var(--border);border-radius:34px;padding:10px;box-shadow:0 20px 50px rgba(38,35,31,.14)}
.screen{background:var(--bg);border-radius:26px;overflow:hidden;height:640px;display:flex;flex-direction:column}
.ptop{padding:14px 16px 10px;background:rgba(243,239,232,.96);border-bottom:1px solid var(--border)}
.ptop b{display:block;font-size:15px;color:var(--ink)}
.ptop small{color:var(--muted);font-size:12px}
.bar{height:7px;background:#E2DACB;border-radius:99px;overflow:hidden;margin-top:8px}
.bar i{display:block;height:100%;background:var(--green);transition:width .3s var(--ease)}
.plist{flex:1;overflow:auto;padding:8px 10px 12px}
.plist h4{margin:12px 6px 6px;font-size:12px;color:var(--muted);font-weight:700}
.comp{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:10px 12px;margin-bottom:8px}
.comp .t{display:flex;gap:8px;align-items:baseline}
.comp .t .no{font-family:var(--num);color:var(--muted);font-size:12px}
.comp .t b{color:var(--ink);font-size:14px}
.comp .t small{color:var(--muted);font-size:11px;margin-inline-start:auto}
.seg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin-top:8px}
.seg button{border:1px solid var(--border);background:#fff;font:inherit;font-weight:700;padding:8px 2px;border-radius:10px;color:var(--muted);cursor:pointer;font-size:12.5px;transition:transform .12s var(--ease)}
.seg button:active{transform:scale(.97)}
.seg button.av.on{background:var(--green);color:#fff;border-color:var(--green)}
.seg button.mi.on{background:var(--maroon);color:#fff;border-color:var(--maroon)}
.seg button.un.on{background:#D9D2C5;color:var(--ink);border-color:#D9D2C5}
.extra{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--muted)}
.chip{background:var(--gold-soft);color:var(--gold-deep);padding:2px 9px;border-radius:999px;font-weight:600}
.chip.cam{background:#fff;border:1px solid var(--border);color:var(--body)}
.pfoot{display:flex;gap:12px;align-items:center;padding:10px 14px;background:rgba(251,248,242,.97);border-top:1px solid var(--border);font-size:12.5px}
.pfoot b{font-family:var(--num);color:var(--ink)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.big{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:14px 16px}
.big b{display:block;font-family:var(--num);font-size:30px;color:var(--ink);line-height:1.1}
.big span{font-size:12.5px;color:var(--muted)}
.big i{display:block;font-style:normal;font-size:12px;color:var(--gold-deep);margin-top:4px}
.out{display:grid;gap:10px;margin-top:14px}
.o{border:1px solid var(--border);border-radius:16px;background:var(--panel);padding:14px 16px}
.o h4{margin:0 0 4px;font-size:15px;color:var(--ink)}
.o p{margin:0;font-size:14px;color:var(--body)}
.o .tag{display:inline-block;font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:999px;margin-bottom:6px}
.o .tag.owner{background:var(--gold-soft);color:var(--gold-deep)}
.o .tag.ouja{background:var(--green-soft);color:var(--green)}
.o .tag.works{background:var(--amber-soft);color:var(--amber)}
.o .tag.doc{background:#E9E4F4;color:#5B4B8A}
.o .tag.block{background:var(--maroon-soft);color:var(--maroon)}
.o ul{margin:6px 0 0;padding-inline-start:18px;font-size:13.5px}
.quote{background:#fff;border:1px solid #ece2cf;border-radius:8px;padding:22px 20px;margin-top:12px;font-family:'Tahoma','Times New Roman',serif;color:#2b2b2b;direction:rtl}
.quote .brand{text-align:center;padding-bottom:12px}
.quote .brand .ar{font-size:24px;font-weight:800;color:#1c1c1c}
.quote .brand .en{font-size:10px;letter-spacing:6px;color:#b08d4f;font-weight:600;margin-top:4px}
.quote .rule{height:2px;background:linear-gradient(90deg,transparent,#c9a96e 18%,#c9a96e 82%,transparent)}
.quote .docrow{display:flex;justify-content:space-between;align-items:flex-end;margin:16px 0 14px}
.quote .title{font-size:18px;font-weight:300;letter-spacing:6px;color:#1c1c1c}
.quote .title small{display:block;font-size:10px;letter-spacing:2px;color:#b08d4f;font-weight:600}
.quote .meta{font-size:11px;color:#555;line-height:1.9;text-align:start}
.quote .party{display:flex;gap:10px;margin-bottom:14px}
.quote .pc{flex:1;background:#faf7f0;border:1px solid #ece2cf;border-radius:4px;padding:10px 12px}
.quote .lbl{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:#b08d4f;font-weight:700}
.quote .nm{font-size:13px;font-weight:700;color:#1c1c1c;margin-top:4px}
.quote table{width:100%;border-collapse:collapse;font-size:12px}
.quote thead th{background:#1c1c1c;color:#e9d9b8;padding:8px 6px;font-size:9.5px;letter-spacing:1px;text-transform:uppercase;font-weight:600;text-align:center}
.quote thead th.d{text-align:start}
.quote tbody td{padding:8px 6px;border-bottom:1px solid #efe9da;text-align:center;color:#333}
.quote tbody td.d{text-align:start;color:#1c1c1c}
.quote tbody td.amt{font-weight:700;color:#b08d4f}
.quote tbody tr.sep td{background:#faf7f0;color:#8c7443;font-weight:700;font-size:11.5px}
.quote .tot{display:flex;justify-content:flex-end;margin-top:12px}
.quote .tbl{width:240px;font-size:12px}
.quote .row{display:flex;justify-content:space-between;padding:5px 2px;color:#555;border-bottom:1px solid #f0ece0}
.quote .grand{display:flex;justify-content:space-between;background:#1c1c1c;color:#fff;padding:10px 12px;margin-top:8px;border-radius:3px;font-size:13px;font-weight:700}
.quote .grand span:last-child{color:#e9d9b8}
.quote .notes{margin-top:14px;background:#faf7f0;border-inline-start:3px solid #c9a96e;padding:9px 12px;border-radius:3px;font-size:11.5px;color:#444}
.frame{width:100%;height:560px;border:1px solid var(--border);border-radius:14px;background:#fff;margin-top:12px}
.pr{display:grid;gap:10px}
.p{display:flex;gap:12px;align-items:flex-start;padding:14px 16px;background:var(--panel);border:1px solid var(--border);border-radius:16px}
.p i{flex:none;width:34px;height:34px;border-radius:10px;background:var(--gold-soft);color:var(--gold-deep);display:flex;align-items:center;justify-content:center;font-style:normal;font-weight:700;font-family:var(--num)}
.p b{display:block;color:var(--ink);font-size:15px}
.p span{font-size:14px}
.foot{margin-top:50px;padding-top:18px;border-top:1px solid var(--border);font-size:13px;color:var(--muted);text-align:center}
.foot b{display:block;color:var(--ink);font-size:15px;margin-bottom:2px}
.blocker{background:var(--maroon-soft);border:1px solid #e8cbd0;color:var(--maroon);border-radius:14px;padding:10px 14px;font-size:14px;margin-top:10px}
@media (max-width:480px){.grid2{grid-template-columns:1fr}.steps button{font-size:12px;padding:9px 2px}.hero h1{font-size:26px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto}}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <span class="eyebrow">عوجا للإقامة · الرياض</span>
    <h1>مركز الالتزام بمعايير وزارة السياحة</h1>
    <p>كيف نطبّق معايير مرافق الضيافة السياحية على كل وحدة نديرها: جولة فحص مؤرّخة، دليل مصوّر، ونواقص تتحوّل تلقائيًا إلى شراء وإصلاح وإعادة فحص.</p>
    <span class="demo">⚠ نموذج توضيحي — الشقة والأسعار والأرقام في هذه الصفحة افتراضية بالكامل</span>
  </header>

  <nav class="nav" id="nav">
    <a href="#standards" class="on">المعايير</a><a href="#journey">الرحلة</a><a href="#principles">المبادئ</a><a href="#about">عن عوجا</a>
  </nav>

  <section id="standards">
    <h2>المعايير كما نقرؤها</h2>
    <p class="lead">٤٧ معيارًا في ثمانية أقسام، حوّلناها إلى <b id="ncomp"></b> مكوّنًا قابلًا للفحص على أرض الشقة (<b id="ncomp_pool"></b> مع المسبح). كل مكوّن له مفتاح ثابت لا يتغيّر، ونسخة معايير <span class="chip" id="ver"></span> تُثبَّت على كل جولة.</p>
    <div class="grid2" id="sections"></div>
    <p class="lead" style="margin-top:12px;font-size:13.5px">نص المعايير الرسمي يُعرض حرفيًا من اللائحة عند اعتماده، ولا نعيد صياغته.</p>
  </section>

  <section id="journey">
    <h2>الرحلة على شقة نموذجية</h2>
    <p class="lead">جرّبها بنفسك: غيّر حالة أي مكوّن في الجوال وشاهد الأرقام والعرض تتغيّر.</p>
    <div class="steps" id="steps">
      <button data-s="1" class="on">١ · فتح الجولة</button><button data-s="2">٢ · الفحص</button><button data-s="3">٣ · الإغلاق</button><button data-s="4">٤ · ملف الدليل</button>
    </div>

    <div class="step on" id="s1">
      <div class="card">
        <div class="kv"><span>الوحدة</span><b style="font-family:var(--font)" id="uname"></b></div>
        <div class="kv"><span>غرف النوم · دورات المياه</span><b id="ubb"></b></div>
        <div class="kv"><span>فيها مسبح؟</span><span class="seg2"><button id="pool_n" class="on">لا</button><button id="pool_y">نعم</button></span></div>
        <div class="kv"><span>المكوّنات المحسوبة (المقام)</span><b id="denom"></b></div>
        <div class="kv"><span>نسخة المعايير المثبّتة</span><b id="ver2"></b></div>
        <div class="kv"><span>الإنترنت (معيار ١٣)</span><span class="chip">يُقرأ من سجل الاشتراكات، لا يُكتب يدويًا</span></div>
      </div>
      <p class="lead" style="margin-top:12px">قاعدة: لا تُفتح جولتان على شقة واحدة، وقاعدة البيانات نفسها ترفض الثانية. المقام يُثبَّت عند الفتح فلا تُقارَن جولة ٦١ بجولة ٦٧ دون أن يُقال.</p>
    </div>

    <div class="step" id="s2">
      <div class="phone"><div class="screen">
        <div class="ptop"><b id="pname"></b><small id="psub"></small><div class="bar"><i id="pbar"></i></div></div>
        <div class="plist" id="plist"></div>
        <div class="pfoot"><span>باقي <b id="f_un">0</b></span><span>متوفر <b id="f_av">0</b></span><span>غير متوفر <b id="f_mi">0</b></span></div>
      </div></div>
      <div class="two">
        <div class="big"><b id="k_comp">—</b><span>نسبة المطابقة</span><i>متوفر ÷ ما فُحص</i></div>
        <div class="big"><b id="k_insp">—</b><span>نسبة الفحص</span><i>ما فُحص ÷ الكل</i></div>
      </div>
      <p class="lead" style="margin-top:12px">المفتش يفتح الرابط من جواله بلا تسجيل دخول، يعلّم كل مكوّن، ويصوّر النقص. الصورة تُحفظ عندنا كدليل لا تنتهي صلاحيته. رقمان لا يُدمجان أبدًا في رقم واحد.</p>
    </div>

    <div class="step" id="s3">
      <div class="card">
        <div class="kv"><span>شرط الإغلاق</span><b style="font-family:var(--font)" id="closeok"></b></div>
        <div class="kv"><span>إعادة الفحص</span><b id="recheck"></b></div>
      </div>
      <div id="blockers"></div>
      <div class="out" id="outputs"></div>
      <div id="quotebox"></div>
      <p class="lead" style="margin-top:12px">كل هذا يصدر من إغلاق واحد. الجولة المقفلة لا تُعدَّل بعدها؛ التصحيح جولة جديدة، وهكذا يبقى التاريخ صادقًا.</p>
    </div>

    <div class="step" id="s4">
      <p class="lead">لكل جولة مكتملة ١٠٠٪ ملف A4 مؤرّخ باسم المفتش، بكل معيار وحالته وصوره، جاهز للتقديم. الجولة الناقصة لا يمكن تصديرها كدليل.</p>
      <iframe class="frame" title="نموذج ملف الدليل" srcdoc="@@REPORT@@"></iframe>
    </div>
  </section>

  <section id="principles">
    <h2>المبادئ التي بُني عليها</h2>
    <div class="pr">
      <div class="p"><i>١</i><div><b>الجولة سجل، لا قائمة</b><span>كل فحص جولة مؤرّخة باسم من فحص ومتى. المقفلة لا تُمس؛ التصحيح جولة جديدة.</span></div></div>
      <div class="p"><i>٢</i><div><b>رقمان لا يختلطان</b><span>نسبة المطابقة تقيس جودة ما رأيناه، ونسبة الفحص تقيس كم رأينا. لا نرفع رقمًا مدمجًا لا يمكن الدفاع عنه.</span></div></div>
      <div class="p"><i>٣</i><div><b>لا نقص بلا أثر</b><span>غير المتوفر يتحوّل تلقائيًا إلى عرض سعر أو تذكرة شراء أو تذكرة صيانة أو مهمة مستندات، مع موعد إعادة فحص.</span></div></div>
      <div class="p"><i>٤</i><div><b>الإنشائي يوقف الوحدة</b><span>ما لا يُصلَح بالشراء (المصعد، المساحة، ملاءمة العقار) لا يدخل عرضًا؛ يُعلَّم كمعيار حاسم ويُرفع لقرار.</span></div></div>
      <div class="p"><i>٥</i><div><b>الشقة الجديدة تُفحص قبل أن تفتح</b><span>الوحدة تحت الضم تدخل البرنامج قبل تشغيلها، ويرافقها سجلها بعد التشغيل.</span></div></div>
    </div>
  </section>

  <section id="about">
    <h2>عن عوجا للإقامة</h2>
    <div class="card">
      <p style="margin:0 0 8px">شركة إدارة وتشغيل وحدات ضيافة سياحية في الرياض، تعمل في المجمّعات السكنية المميزة، وفي مرحلة استكمال ترخيص إدارة مرافق الضيافة السياحية فئة (د). بنينا هذا النظام داخليًا لتكون كل وحدة نديرها قابلة للإثبات: ماذا فيها، متى فُحصت، ومن تحقّق.</p>
      <p style="margin:0;color:var(--muted);font-size:14px">يسعدنا استقبال أي ملاحظة من الوزارة على المنهجية، ومواءمة الصياغة مع النص الرسمي للمعايير عند اعتماده.</p>
    </div>
  </section>

  <div class="foot"><b>عوجا للإقامة · Ouja Residence</b>الرياض · المملكة العربية السعودية · هذه الصفحة نموذج توضيحي ولا تحوي بيانات تشغيلية</div>
</div>

<script>
var D = @@DATA@@;
var POOL = false;
var R = {};            /* comp key -> {state, qty, note} */
var KIND = {product:'منتج', works:'أعمال', document:'مستند', structural:'إنشائي'};

function esc(s){ return String(s===null||s===undefined?'':s).split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;').split('"').join('&quot;'); }
function qs(id){ return document.getElementById(id); }
function fmt(n){ return Math.round(Number(n)||0).toLocaleString('en-US'); }
function money(n){ return (Math.round((Number(n)||0)*100)/100).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}); }
function comps(){ return D.components.filter(function(c){ return POOL || !c.pool_only; }); }
function reset(){
  R = {};
  comps().forEach(function(c){ var m = D.missing[c.key]; R[c.key] = m ? {state:'missing', qty:m.qty||null, note:m.note||''} : {state:'available', qty:null, note:''}; });
}
function defQty(c){
  var u = D.unit; var h = c.unit_hint;
  var q = h==='per_bedroom' ? u.bedrooms : (h==='per_bathroom' ? u.bathrooms : (h==='per_bed' ? (u.beds||u.bedrooms) : 1));
  return Math.max(1, q||1);
}
function score(){
  var av=0, mi=0, un=0;
  comps().forEach(function(c){ var s = (R[c.key]||{}).state||'unchecked'; if(s==='available') av++; else if(s==='missing') mi++; else un++; });
  var seen = av+mi, den = comps().length;
  return {av:av, mi:mi, un:un, den:den, comp: seen ? Math.round(av/seen*1000)/10 : null, insp: den ? Math.round(seen/den*1000)/10 : 0};
}
function split(){
  var owner=[], oujaP=[], oujaW=[], docs=[], blocked=[];
  comps().forEach(function(c){
    var r = R[c.key]||{}; if(r.state!=='missing') return;
    if(c.kind==='structural'){ blocked.push(c); return; }
    if(c.kind==='document'){ docs.push(c); return; }
    var qty = r.qty || defQty(c); var price = D.prices[c.key]||0;
    var line = {c:c, qty:qty, price:price, total:qty*price, note:r.note||''};
    if(c.billed_to==='owner'){ owner.push(line); } else if(c.kind==='works'){ oujaW.push(line); } else { oujaP.push(line); }
  });
  owner.sort(function(a,b){ return (a.c.kind==='works'?1:0)-(b.c.kind==='works'?1:0); });
  return {owner:owner, oujaP:oujaP, oujaW:oujaW, docs:docs, blocked:blocked};
}

/* ---------- render ---------- */
function renderStandards(){
  qs('ncomp').textContent = D.components.filter(function(c){ return !c.pool_only; }).length;
  qs('ncomp_pool').textContent = D.components.length;
  qs('ver').textContent = D.version; qs('ver2').textContent = D.version;
  qs('sections').innerHTML = D.sections.map(function(s){
    return '<div class="sec"><b>' + s.n + '</b><span>' + esc(s.label) + '<small>المعايير ' + s.criteria[0] + '–' + s.criteria[s.criteria.length-1] + (s.key==='s8' ? ' · تُحسب فقط مع مسبح' : '') + '</small></span></div>';
  }).join('');
}
function renderOpen(){
  qs('uname').textContent = D.unit.name;
  qs('ubb').textContent = D.unit.bedrooms + ' · ' + D.unit.bathrooms;
  qs('denom').textContent = comps().length + (POOL ? ' (مع المسبح)' : ' (بدون مسبح)');
  qs('pool_n').classList.toggle('on', !POOL); qs('pool_y').classList.toggle('on', POOL);
}
function renderPhone(){
  var s = score();
  qs('pname').textContent = D.unit.name;
  qs('psub').textContent = 'جولة نموذجية · ' + s.den + ' مكوّن · فُحص ' + (s.av+s.mi) + ' من ' + s.den;
  qs('pbar').style.width = s.insp + '%';
  qs('f_un').textContent = s.un; qs('f_av').textContent = s.av; qs('f_mi').textContent = s.mi;
  qs('k_comp').textContent = s.comp===null ? '—' : s.comp + '٪';
  qs('k_insp').textContent = s.insp + '٪';
  var h = '';
  D.sections.forEach(function(sec){
    var cs = comps().filter(function(c){ return c.section===sec.key; }); if(!cs.length) return;
    h += '<h4>' + esc(sec.label) + '</h4>';
    cs.forEach(function(c){
      var r = R[c.key]||{}; var st = r.state||'unchecked';
      h += '<div class="comp" data-key="' + esc(c.key) + '"><div class="t"><span class="no">' + c.criterion_no + '</span><b>' + esc(c.label_ar) + '</b><small>' + esc(c.criterion_ar) + (c.key==='c13.wifi' ? ' · من الاشتراكات' : '') + '</small></div>'
        + '<div class="seg"><button class="av' + (st==='available'?' on':'') + '" data-s="available">متوفر</button><button class="mi' + (st==='missing'?' on':'') + '" data-s="missing">غير متوفر</button><button class="un' + (st==='unchecked'?' on':'') + '" data-s="unchecked">لم يُفحص</button></div>';
      if(st==='missing'){
        h += '<div class="extra">';
        if(c.kind==='product'||c.kind==='works') h += '<span class="chip">الكمية ' + (r.qty||defQty(c)) + '</span><span class="chip">' + (c.billed_to==='owner' ? 'على المالك' : 'على عوجا') + '</span>';
        if(c.kind==='structural') h += '<span class="chip" style="background:var(--maroon-soft);color:var(--maroon)">إنشائي — يوقف الوحدة</span>';
        if(c.kind==='document') h += '<span class="chip">مهمة مستندات</span>';
        h += '<span class="chip cam">📷 صورة الدليل</span>' + (r.note ? '<span>' + esc(r.note) + '</span>' : '') + '</div>';
      }
      h += '</div>';
    });
  });
  qs('plist').innerHTML = h;
}
function renderClose(){
  var s = score(), sp = split();
  qs('closeok').textContent = s.un ? ('مرفوض — باقي ' + s.un + ' مكوّن لم يُفحص') : 'مقبول — الفحص ١٠٠٪';
  qs('recheck').textContent = '+' + D.recheck_days + ' يومًا';
  qs('blockers').innerHTML = sp.blocked.length ? '<div class="blocker"><b>الوحدة غير مطابقة — تحتاج قرار:</b> ' + sp.blocked.map(function(c){ return esc(c.criterion_no + '. ' + c.label_ar); }).join('، ') + ' <br><small>معيار إنشائي لا يُصلَح بالشراء؛ لا يدخل العرض.</small></div>' : '';
  var o = [];
  var ownerTotal = sp.owner.reduce(function(a,l){ return a+l.total; }, 0);
  if(sp.owner.length) o.push('<div class="o"><span class="tag owner">عرض سعر للمالك</span><h4>' + sp.owner.length + ' بند · ' + fmt(ownerTotal) + ' ر.س قبل الخدمة والضريبة</h4><p>يصدر من نظام عروض الأسعار المعتمد بترقيمه، باسم مالك الوحدة، والأعمال مفصولة عن المنتجات.</p></div>');
  if(sp.oujaP.length) o.push('<div class="o"><span class="tag ouja">تذكرة مشتريات — على عوجا</span><h4>' + sp.oujaP.length + ' بند · ' + fmt(sp.oujaP.reduce(function(a,l){ return a+l.total; },0)) + ' ر.س</h4><ul>' + sp.oujaP.map(function(l){ return '<li>' + esc(l.c.label_ar) + ' × ' + l.qty + '</li>'; }).join('') + '</ul></div>');
  if(sp.oujaW.length) o.push('<div class="o"><span class="tag works">تذاكر صيانة — على عوجا</span><ul>' + sp.oujaW.map(function(l){ return '<li>' + esc(l.c.label_ar) + '</li>'; }).join('') + '</ul></div>');
  if(sp.docs.length) o.push('<div class="o"><span class="tag doc">مهام مستندات في ملف الترخيص</span><ul>' + sp.docs.map(function(c){ return '<li>' + esc(c.label_ar) + ' <small style="color:var(--muted)">(' + esc(D.doc_tasks[c.key]||'') + ')</small></li>'; }).join('') + '</ul></div>');
  if(!o.length && !sp.blocked.length) o.push('<div class="o"><span class="tag ouja">لا نواقص</span><h4>الوحدة مطابقة ١٠٠٪</h4><p>لا يصدر شيء سوى ملف الدليل وموعد إعادة الفحص.</p></div>');
  qs('outputs').innerHTML = o.join('');
  qs('quotebox').innerHTML = sp.owner.length ? renderQuote(sp.owner) : '';
}
function renderQuote(lines){
  var rows = '', i = 0, sub = 0, sepDone = false;
  lines.forEach(function(l){
    if(l.c.kind==='works' && !sepDone){ rows += '<tr class="sep"><td></td><td class="d" colspan="4">' + esc(D.works_sep) + '</td></tr>'; sepDone = true; }
    i++; sub += l.total;
    rows += '<tr><td>' + i + '</td><td class="d">' + esc(l.c.criterion_ar + ' — ' + l.c.label_ar) + '<br><small style="color:#888">معيار ' + l.c.criterion_no + (l.note ? ' · ' + esc(l.note) : '') + '</small></td><td>' + l.qty + '</td><td>' + money(l.price) + '</td><td class="amt">' + money(l.total) + '</td></tr>';
  });
  var srv = sub * D.service_rate/100, vat = (sub+srv) * D.vat_rate/100, grand = sub+srv+vat;
  return '<div class="quote"><div class="brand"><div class="ar">عوجا ريزيدنس</div><div class="en">OUJA RESIDENCE</div></div><div class="rule"></div>'
    + '<div class="docrow"><div class="title">QUOTATION<small>عرض سعر · نموذج</small></div><div class="meta">رقم العرض: <b>OJ-YYYYMM-NNN</b><br>التاريخ: <b>يوم الإغلاق</b></div></div>'
    + '<div class="party"><div class="pc"><div class="lbl">مقدّم إلى</div><div class="nm">' + esc(D.unit.owner) + '</div></div><div class="pc"><div class="lbl">من</div><div class="nm">عوجا ريزيدنس</div></div></div>'
    + '<table><thead><tr><th style="width:26px">#</th><th class="d">الوصف</th><th style="width:44px">العدد</th><th style="width:70px">السعر</th><th style="width:80px">الإجمالي</th></tr></thead><tbody>' + rows + '</tbody></table>'
    + '<div class="tot"><div class="tbl"><div class="row"><span>المجموع الفرعي</span><span>' + money(sub) + ' ر.س</span></div><div class="row"><span>رسوم خدمة ' + D.service_rate + '٪</span><span>' + money(srv) + ' ر.س</span></div><div class="row"><span>ضريبة القيمة المضافة ' + D.vat_rate + '٪</span><span>' + money(vat) + ' ر.س</span></div><div class="grand"><span>الإجمالي</span><span>' + money(grand) + ' ر.س</span></div></div></div>'
    + '<div class="notes">نواقص مطابقة وزارة السياحة — ' + esc(D.unit.name) + ' — جولة نموذجية. الأسعار توضيحية.</div></div>';
}
function renderAll(){ renderOpen(); renderPhone(); renderClose(); }

/* ---------- events ---------- */
qs('pool_n').onclick = function(){ POOL = false; reset(); renderAll(); };
qs('pool_y').onclick = function(){ POOL = true; reset(); renderAll(); };
qs('steps').addEventListener('click', function(e){
  var b = e.target.closest('button'); if(!b) return;
  var n = b.getAttribute('data-s');
  var bs = qs('steps').querySelectorAll('button'); for(var i=0;i<bs.length;i++) bs[i].classList.toggle('on', bs[i]===b);
  for(var k=1;k<=4;k++) qs('s'+k).classList.toggle('on', String(k)===n);
});
qs('plist').addEventListener('click', function(e){
  var b = e.target.closest('.seg button'); if(!b) return;
  var key = b.closest('.comp').getAttribute('data-key');
  R[key] = R[key] || {}; R[key].state = b.getAttribute('data-s');
  var top = qs('plist').scrollTop; renderPhone(); renderClose(); qs('plist').scrollTop = top;
});
var links = qs('nav').querySelectorAll('a');
window.addEventListener('scroll', function(){
  var cur = 'standards';
  ['standards','journey','principles','about'].forEach(function(id){ var el = qs(id); if(el && el.getBoundingClientRect().top < 120) cur = id; });
  for(var i=0;i<links.length;i++) links[i].classList.toggle('on', links[i].getAttribute('href')==='#'+cur);
}, {passive:true});

renderStandards(); reset(); renderAll();
</script>
</body>
</html>
"""

HTML = build()
