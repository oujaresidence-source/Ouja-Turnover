# -*- coding: utf-8 -*-
"""
targets.routes — «أهدافي» + «دفتر العملاء» endpoints.

    GET  /targets/static/targets_tab.js   PUBLIC code, no data
    GET  /my-targets, /my-book            phone pages (login)
    GET  /api/targets/me                  my scoreboard + my money         («targets» read)
    GET  /api/targets/team                rescue list + counts             (admin / ops manager)
    GET  /api/targets/admin               everything                        (ADMIN ONLY)
    POST /api/targets/admin/*             propose, unit, approve-quarter, link, manager,
                                          seed-upload, sync, map-name, approve-month (ADMIN ONLY)
    GET  /api/book/list                   my call list + my open contacts  («book» read)
    POST /api/book/wa                     logs the contact, then 302 -> wa.me   («book» write)
    POST /api/book/outcome                how my contact went              («book» write)
    POST /api/tg-consent                  PUBLIC — the guide page's consent box

WHO SEES WHAT
  An employee = a login the owner linked to a schedule employee («مين هو مين»). An unlinked
  login sees nothing. An employee gets ONLY their own board, their own amount and their own
  list. Nothing here returns Ouja's fee, a contract percentage, a colleague's number, the pool
  or anything about the hidden group — those live in /api/targets/admin, which is admin-only.
  The hidden group's IDENTITIES are returned by no endpoint at all, admin included.

THERE IS NO ENDPOINT THAT INSERTS OR DATES A CONTACT. The only writer is /api/book/wa, which
takes one opaque guest token and nothing else.
"""

import os
import time
import traceback

from . import book, db, engine, history, money, score
from . import host as _host
from .host import HOST

STATIC_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "targets_tab.js")
_js_cache = {"mtime": None, "text": ""}
MAX_SEED_BYTES = 60 * 1024 * 1024
_consent_hits = {}
CONSENT_PER_HOUR = 6


# ------------------------------------------------------------------ helpers

def _json(data, status=200):
    return HOST.json_response(data, status)


async def _run(fn, *a, **kw):
    return await HOST.web_thread(fn, *a, **kw)


def _role(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") or "viewer"
    except Exception:
        return "viewer"


def is_admin(request):
    return _role(request) == "admin"


def _actor(request):
    try:
        return (HOST.actor(request) if HOST.actor else "") or "غير معروف"
    except Exception:
        return "غير معروف"


def employee_of(request):
    """The schedule employee this login is linked to ('' when not linked)."""
    try:
        uid = HOST.user_id(request) if HOST.user_id else ""
    except Exception:
        uid = ""
    return db.link(uid) if uid else ""


def is_manager(request):
    emp = employee_of(request)
    return bool(emp) and emp == db.setting("manager")


def _safe(fn):
    async def _w(request):
        if not HOST.dash_auth(request):
            return _json({"ok": False, "error": "unauthorized"}, 401)
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return _json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _admin(fn):
    async def _w(request):
        if not is_admin(request):
            return _json({"ok": False, "error": "للمالك فقط"}, 403)
        return await fn(request)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _safe(_w)


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def _today():
    return HOST.require("now")().date()


def _month(request):
    m = (request.query.get("month") or "").strip()
    try:
        engine.month_bounds(m)
        return m[:7]
    except Exception:
        return score.month_of(_today())


def flags():
    return {"channels": list(_host.pool_channels())}


# ------------------------------------------------------------------ employee: «أهدافي»

def me_payload(employee, month_key, today):
    """Everything ONE employee may see on «أهدافي»."""
    return {"employee": employee, "month": month_key,
            "board": score.board(employee, month_key, today),
            "money": money.my_money(employee, month_key, today)}


async def api_me(request):
    emp = employee_of(request)
    asked = (request.query.get("employee") or "").strip()
    if asked and is_admin(request):
        emp = asked                                   # the owner may look at anyone's page
    base = {"ok": True, "is_admin": is_admin(request), "is_manager": is_manager(request), "linked": bool(emp)}
    if not emp:
        return _json(base)
    base.update(await _run(me_payload, emp, _month(request), _today()))
    return _json(base)


# ------------------------------------------------------------------ employee: «دفتر العملاء»

def book_payload(employee, today):
    return {"employee": employee,
            "list": book.public_items(book.call_list(employee, today)),
            "open": book.open_contacts(employee, today)}


async def api_book_list(request):
    emp = employee_of(request)
    base = {"ok": True, "linked": bool(emp)}
    if not emp:
        return _json(base)
    base.update(await _run(book_payload, emp, _today()))
    return _json(base)


def _wa_page(msg):
    html = ("<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>دفتر العملاء</title>"
            "<body style='font-family:system-ui;background:#F1EDE6;color:#33302B;padding:28px'>"
            "<div style='max-width:460px;margin:0 auto;background:#FAF7F1;border:1px solid #E7DFD1;"
            "border-radius:16px;padding:20px;font-size:16px;font-weight:700'>%s"
            "<div style='font-weight:400;font-size:13px;color:#9C958A;margin-top:8px'>"
            "سكّر هالصفحة وارجع لدفتر العملاء.</div></div></body></html>")
    safe = (msg or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HOST.web.Response(text=html % safe, content_type="text/html", charset="utf-8", status=200)


async def api_book_wa(request):
    """The WhatsApp button. The press IS the log: record the contact, then redirect."""
    if not HOST.dash_auth(request):
        return _wa_page("سجّل دخولك في اللوحة أول.")
    try:
        form = await request.post()
        g = str(form.get("g") or request.query.get("g") or "")
    except Exception:
        g = str(request.query.get("g") or "")
    try:
        ok, err, out = await _run(book.log_contact, employee_of(request), g)
    except Exception:
        traceback.print_exc()
        return _wa_page("صار خطأ مؤقت. جرّب مرة ثانية.")
    if not ok:
        return _wa_page(err)
    url = HOST.require("wa_url")(out["phone"], out["text"])
    return HOST.web.Response(status=302, headers={"Location": url, "Referrer-Policy": "no-referrer",
                                                  "Cache-Control": "no-store"})


async def api_book_outcome(request):
    emp = employee_of(request)
    if not emp:
        return _json({"ok": False, "error": "حسابك مو مربوط بموظف"}, 403)
    b = await _body(request)
    try:
        cid = int(b.get("id"))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "رقم غير صحيح"})
    ok, err = await _run(book.set_outcome, emp, cid, str(b.get("outcome") or ""))
    return _json({"ok": ok, "error": err})


# ------------------------------------------------------------------ operations manager

def team_payload(month_key, today):
    return {"month": month_key, "rescue": score.rescue(month_key, today),
            "snapshots": db.rescues(month_key), "activity": money.team_activity(month_key, today),
            "quarter_state": score.quarter_state(score.quarter_of(month_key))}


async def api_team(request):
    if not (is_admin(request) or is_manager(request)):
        return _json({"ok": False, "error": "لمدير التشغيل فقط"}, 403)
    out = await _run(team_payload, _month(request), _today())
    return _json(dict(out, ok=True))


# ------------------------------------------------------------------ admin

def admin_payload(month_key, quarter, today):
    links = db.links()
    users = [dict(u, employee=links.get(str(u.get("id")), ""))
             for u in (HOST.call("users", []) or [])]
    live = HOST.call("listings", {}) or {}
    return {
        "flags": flags(), "month": month_key, "quarter": quarter,
        "seed": {"rows": db.res_count(), "imported_at": db.setting("seed_imported_at"),
                 "synced_at": db.setting("synced_at"), "unmapped": history.unmapped()},
        "listings": sorted(({"id": str(k), "name": v} for k, v in live.items()),
                           key=lambda x: x["name"] or ""),
        "users": users, "employees": score.employees(quarter), "manager": db.setting("manager"),
        "quarter_state": score.quarter_state(quarter), "targets": db.targets(quarter),
        "sheet": money.month_sheet(month_key, today),
        "rescue": score.rescue(month_key, today), "snapshots": db.rescues(month_key),
        "consents": len(db.consents()), "dnc": len(db.dnc()),
    }


def _quarter(request_value, today):
    qv = str(request_value or "").strip()
    if len(qv) == 7 and qv[4:6] == "-Q" and qv[:4].isdigit() and qv[6] in "1234":
        return qv
    return score.quarter_of(today)


async def api_admin(request):
    today = _today()
    out = await _run(admin_payload, _month(request), _quarter(request.query.get("quarter"), today), today)
    return _json(dict(out, ok=True))


async def api_propose(request):
    b = await _body(request)
    today = _today()
    quarter = _quarter(b.get("quarter"), today)
    rows = await _run(score.propose, quarter, today)
    db.log("propose", HOST.now().isoformat(timespec="seconds"), _actor(request), {"quarter": quarter})
    return _json({"ok": True, "quarter": quarter, "targets": rows})


async def api_unit(request):
    b = await _body(request)
    try:
        floor = max(0.0, float(b.get("floor") or 0))
        ceiling = max(0.0, float(b.get("ceiling") or 0))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "رقم غير صحيح"})
    if ceiling and ceiling <= floor:
        return _json({"ok": False, "error": "الحد الأعلى لازم يكون فوق الحد الأدنى"})
    n = await _run(db.edit_target, str(b.get("quarter") or ""), str(b.get("unit") or ""), floor, ceiling)
    if not n:
        return _json({"ok": False, "error": "الشقة معتمدة أو غير موجودة — الحدود تتغير قبل الاعتماد فقط"})
    return _json({"ok": True})


async def api_approve_quarter(request):
    b = await _body(request)
    quarter = _quarter(b.get("quarter"), _today())
    now = HOST.now().isoformat(timespec="seconds")
    n = await _run(db.approve_targets, quarter, _actor(request), now)
    if not n:
        return _json({"ok": False, "error": "ما فيه أهداف مقترحة لهالربع. اضغط «احسب الأهداف» أول."})
    db.log("approve_quarter", now, _actor(request), {"quarter": quarter, "units": n})
    return _json({"ok": True, "approved": n})


async def api_link(request):
    b = await _body(request)
    uid, emp = str(b.get("user_id") or "").strip(), str(b.get("employee") or "").strip()
    if not uid:
        return _json({"ok": False, "error": "اختر المستخدم"})
    if emp and emp not in score.employees(score.quarter_of(_today())):
        return _json({"ok": False, "error": "الموظف غير موجود في تقويم الموظفين"})
    await _run(db.set_link, uid, emp, _actor(request), HOST.now().isoformat(timespec="seconds"))
    return _json({"ok": True})


async def api_manager(request):
    b = await _body(request)
    name = str(b.get("name") or "").strip()[:80]
    now = HOST.now().isoformat(timespec="seconds")
    await _run(db.set_setting, "manager", name, _actor(request), now)
    db.log("manager", now, _actor(request), {"name": name})
    return _json({"ok": True})


async def api_seed_upload(request):
    """One-time upload of the Hostaway reservations export. Stored under STATE_DIR only."""
    reader = await request.multipart()
    part = await reader.next()
    while part is not None and part.name != "file":
        part = await reader.next()
    if part is None:
        return _json({"ok": False, "error": "ما وصل ملف"})
    path = history.seed_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp, size = path + ".part", 0
    with open(tmp, "wb") as f:
        while True:
            chunk = await part.read_chunk(256 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SEED_BYTES:
                break
            f.write(chunk)
    if size > MAX_SEED_BYTES or size == 0:
        os.remove(tmp)
        return _json({"ok": False, "error": "الملف فاضي أو أكبر من 60 ميجا"})
    os.replace(tmp, path)
    try:
        report = await _run(history.import_seed_file, path, _actor(request))
    except Exception as e:
        traceback.print_exc()
        return _json({"ok": False, "error": "الملف مو بصيغة تصدير Hostaway: %s" % e})
    await _run(book.run_attribution)
    return _json({"ok": True, "report": report})


async def api_sync(request):
    rep = await _run(book.nightly, _today())
    return _json({"ok": True, "report": rep})


async def api_map_name(request):
    b = await _body(request)
    ok, err = await _run(history.map_name, str(b.get("name") or ""),
                         str(b.get("listing_id") or "").strip(), _actor(request))
    return _json({"ok": ok, "error": err})


async def api_approve_month(request):
    b = await _body(request)
    m = str(b.get("month") or "")[:7]
    try:
        engine.month_bounds(m)
    except Exception:
        return _json({"ok": False, "error": "شهر غير صحيح"})
    ok, err = await _run(money.approve_month, m, _actor(request))
    return _json({"ok": ok, "error": err})


# ------------------------------------------------------------------ public: consent box

def _consent_allowed(ip, now=None):
    now = now or time.time()
    hits = [t for t in _consent_hits.get(ip, []) if now - t < 3600]
    if len(hits) >= CONSENT_PER_HOUR:
        _consent_hits[ip] = hits
        return False
    hits.append(now)
    _consent_hits[ip] = hits
    if len(_consent_hits) > 5000:
        _consent_hits.clear()
    return True


async def api_consent(request):
    """The guide page's «أوافق على التواصل» box. Always answers the same, whoever asks."""
    try:
        b = await _body(request)
        ip = (request.headers.get("X-Forwarded-For") or request.remote or "?").split(",")[0].strip()
        if b.get("agree") is True and _consent_allowed(ip):
            await _run(book.record_consent, str(b.get("phone") or "")[:30], str(b.get("slug") or ""))
    except Exception:
        traceback.print_exc()
    return _json({"ok": True})


# ------------------------------------------------------------------ static + pages

def js_version():
    try:
        return str(int(os.path.getmtime(STATIC_JS)))
    except OSError:
        return "0"


def _js_text():
    m = os.path.getmtime(STATIC_JS)
    if _js_cache["mtime"] != m:
        with open(STATIC_JS, encoding="utf-8") as f:
            _js_cache["text"] = f.read()
        _js_cache["mtime"] = m
    return _js_cache["text"]


async def handle_static_js(request):
    text = await _run(_js_text)
    return HOST.web.Response(text=text, content_type="application/javascript",
                             headers={"Cache-Control": "no-cache"})


def _page(which):
    async def _h(request):
        from . import page
        if not HOST.dash_auth(request):
            return HOST.web.Response(text=page.LOGIN_HINT_HTML, content_type="text/html",
                                     charset="utf-8", status=401)
        html = page.render(which, js_version())
        return HOST.web.Response(text=html, content_type="text/html", charset="utf-8",
                                 headers={"Cache-Control": "no-store"})
    return _h


# ------------------------------------------------------------------ dashboard injection
# bot.py's DASHBOARD_HTML is NOT edited for this feature. When TG_ENABLED=1 these three
# snippets are spliced in at import, next to anchors that already exist; with TG_ENABLED=0
# the dashboard string is byte-for-byte what it was. ZERO backslashes below.

DASH_VIEWS = """<section class="view" id="view_targets">
        <div class="page-head">
          <div>
            <div class="page-title">🎯 أهدافي</div>
            <div class="page-sub">شققي · الإشغال والشرائح · عمولتي من دفتر العملاء</div>
          </div>
        </div>
        <div id="tgBody"><div class="empty sk">—</div></div>
      </section>

      <section class="view" id="view_book">
        <div class="page-head">
          <div>
            <div class="page-title">📒 دفتر العملاء</div>
            <div class="page-sub">قائمة اليوم · زر الواتساب هو التسجيل · اتصال واحد لكل ضيف كل ٤٥ يوم</div>
          </div>
        </div>
        <div id="bkBody"><div class="empty sk">—</div></div>
      </section>

      """

DASH_STUBS = """/* «أهدافي» + «دفتر العملاء» — the code is the real file /targets/static/targets_tab.js */
function __tgLoad(which, force){
  if(window.__tgJs){ return window.TargetsTab[which](force); }
  window.__tgWant=which;
  if(window.__tgLoading){ return; }
  window.__tgLoading=1;
  var s=document.createElement('script');
  s.src='/targets/static/targets_tab.js?v=__TG_JS_V__';
  s.onload=function(){ window.__tgJs=1; window.TargetsTab[window.__tgWant](force); };
  s.onerror=function(){ window.__tgLoading=0; putHtml(which==='book'?'bkBody':'tgBody', errorState(which==='book'?'loadBook(1)':'loadTargets(1)')); };
  document.head.appendChild(s);
}
function loadTargets(force){ return __tgLoad('targets', force); }
function loadBook(force){ return __tgLoad('book', force); }
"""

DASH_HOOK = " if(id==='targets') loadTargets(); if(id==='book') loadBook();"

ANCHOR_VIEW = '<section class="view" id="view_oncall">'
ANCHOR_HOOK = "if(id==='oncall') loadOncall();"
ANCHOR_STUB = "/* «المناوبة» — the tab's code is the real file"

# The consent box for the public guide page (/guide/{slug}). Spliced in by guide.routes via
# HOST.page_extra when TG_ENABLED=1. Self-contained; ZERO backslashes.
GUIDE_CONSENT_HTML = """<section id="tgConsent" dir="rtl" aria-label="عروض عوجا">
        <style>
          #tgConsent{margin:26px 0 8px;padding:18px 16px;border:1px solid var(--hairline,rgba(139,111,71,.2));border-radius:14px;background:var(--ivory,#FAF6EE);text-align:right;font-family:var(--thmanyah,system-ui,sans-serif)}
          #tgConsent .tgc-t{font-size:16px;font-weight:700;color:var(--ink,#1A130D);margin-bottom:4px}
          #tgConsent .tgc-s{font-size:13px;line-height:1.7;color:var(--muted,#78695A);margin-bottom:12px}
          #tgConsent label{display:flex;gap:10px;align-items:flex-start;font-size:13.5px;line-height:1.6;color:var(--ink-soft,#3A2A1F);cursor:pointer;margin-bottom:12px}
          #tgConsent input[type=checkbox]{width:20px;height:20px;margin-top:2px;accent-color:var(--bronze,#8B6F47);flex:none}
          #tgConsent .tgc-r{display:flex;gap:8px;flex-wrap:wrap}
          #tgConsent input[type=tel]{flex:1;min-width:160px;min-height:46px;padding:10px 12px;border:1px solid var(--hairline,rgba(139,111,71,.2));border-radius:10px;background:#fff;font-size:16px;color:var(--ink,#1A130D);text-align:left}
          #tgConsent button{min-height:46px;padding:10px 20px;border-radius:10px;border:1px solid var(--bronze,#8B6F47);background:var(--bronze,#8B6F47);color:#fff;font:inherit;font-size:15px;font-weight:700;cursor:pointer;transition:transform .12s cubic-bezier(0.23,1,0.32,1)}
          #tgConsent button:active{transform:scale(.97)}
          #tgConsent button:disabled{opacity:.55;cursor:default;transform:none}
          #tgConsent .tgc-m{font-size:13px;color:var(--bronze,#8B6F47);margin-top:10px;min-height:20px}
          @media (prefers-reduced-motion:reduce){#tgConsent button{transition:none}#tgConsent button:active{transform:none}}
        </style>
        <div class="tgc-t">تبي نبلغك أول واحد لما تفضى شقتك؟</div>
        <div class="tgc-s">اترك رقمك ونكلمك على الواتساب بعروض خاصة لضيوفنا. تقدر توقفها بأي وقت بكلمة وحدة.</div>
        <label><input type="checkbox" id="tgcAgree"><span>أوافق إن عوجا ريزيدنس تتواصل معي على الواتساب بعروض الإقامة.</span></label>
        <div class="tgc-r">
          <input type="tel" id="tgcPhone" inputmode="tel" autocomplete="tel" placeholder="05xxxxxxxx" dir="ltr" aria-label="رقم الجوال">
          <button type="button" id="tgcBtn">سجّلني</button>
        </div>
        <div class="tgc-m" id="tgcMsg" role="status" aria-live="polite"></div>
        <script>
        (function () {
          var btn = document.getElementById('tgcBtn');
          if (!btn) { return; }
          function digits(s) {
            var n = 0, i;
            for (i = 0; i < s.length; i++) { if (s.charAt(i) >= '0' && s.charAt(i) <= '9') { n++; } }
            return n;
          }
          btn.addEventListener('click', function () {
            var msg = document.getElementById('tgcMsg');
            var phone = String(document.getElementById('tgcPhone').value || '');
            if (!document.getElementById('tgcAgree').checked) { msg.textContent = 'علّم على «أوافق» أول.'; return; }
            if (digits(phone) < 9) { msg.textContent = 'اكتب رقم جوالك كامل.'; return; }
            var slug = '';
            try { slug = (typeof id === 'string') ? id : ''; } catch (e) { slug = ''; }
            btn.disabled = true;
            var done = function () { msg.textContent = 'تم، شكراً لك 🌿'; };
            try {
              fetch('/api/tg-consent', {
                method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({phone: phone, slug: slug, agree: true})
              }).then(done).catch(done);
            } catch (e) { done(); }
          });
        })();
        </script>
      </section>

      """

NAV_ITEMS = [{"id": "targets", "ic": "strat", "tk": "targets"},
             {"id": "book", "ic": "guests", "tk": "book"}]
NAV_LABELS = {"ar": {"targets": "أهدافي", "book": "دفتر العملاء"},
              "en": {"targets": "My targets", "book": "Client book"}}


def patch_dashboard(html):
    """Return the dashboard with the two tabs spliced in — or the SAME string, untouched, if
    any anchor is missing or ambiguous (a silent no-op beats a broken login)."""
    if any(html.count(a) != 1 for a in (ANCHOR_VIEW, ANCHOR_HOOK, ANCHOR_STUB)):
        print("[targets] dashboard anchors not found exactly once — tabs NOT injected")
        return html
    out = html.replace(ANCHOR_VIEW, DASH_VIEWS + ANCHOR_VIEW, 1)
    out = out.replace(ANCHOR_HOOK, ANCHOR_HOOK + DASH_HOOK, 1)
    out = out.replace(ANCHOR_STUB, DASH_STUBS.replace("__TG_JS_V__", js_version()) + ANCHOR_STUB, 1)
    return out


def patch_nav(nav_def):
    """Add the two tabs to the shared NAV_DEF (items, a category slot, labels in BOTH languages)."""
    have = {i.get("id") for i in nav_def.get("items", [])}
    for it in NAV_ITEMS:
        if it["id"] not in have:
            nav_def["items"].append(dict(it))
    cats = nav_def.get("cats") or []
    home = next((c for c in cats if c.get("tk") == "cat_ops"), cats[0] if cats else None)
    if home is not None:
        for it in NAV_ITEMS:
            if not any(it["id"] in (c.get("ids") or []) for c in cats):
                home["ids"].append(it["id"])
    for lang, words in NAV_LABELS.items():
        nav_def.setdefault("labels", {}).setdefault(lang, {}).update(words)
    return nav_def


def register_routes(app):
    g, p = app.router.add_get, app.router.add_post
    g("/targets/static/targets_tab.js", handle_static_js)
    g("/my-targets", _page("targets"))
    g("/my-book", _page("book"))
    p("/api/tg-consent", api_consent)
    g("/api/targets/me", _safe(api_me))
    g("/api/targets/team", _safe(api_team))
    g("/api/targets/admin", _admin(api_admin))
    p("/api/targets/admin/propose", _admin(api_propose))
    p("/api/targets/admin/unit", _admin(api_unit))
    p("/api/targets/admin/approve-quarter", _admin(api_approve_quarter))
    p("/api/targets/admin/link", _admin(api_link))
    p("/api/targets/admin/manager", _admin(api_manager))
    p("/api/targets/admin/seed-upload", _admin(api_seed_upload))
    p("/api/targets/admin/sync", _admin(api_sync))
    p("/api/targets/admin/map-name", _admin(api_map_name))
    p("/api/targets/admin/approve-month", _admin(api_approve_month))
    g("/api/book/list", _safe(api_book_list))
    p("/api/book/wa", api_book_wa)
    p("/api/book/outcome", _safe(api_book_outcome))


def nightly_due(now, last_run_date):
    """True once per day after 03:30 Riyadh. Pure, so the loop in bot.py stays trivial."""
    return (now.hour, now.minute) >= (3, 30) and last_run_date != now.date().isoformat()


__all__ = ["register_routes", "patch_dashboard", "patch_nav", "js_version", "nightly_due",
           "me_payload", "book_payload", "admin_payload", "team_payload"]
