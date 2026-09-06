# -*- coding: utf-8 -*-
"""
mot.routes — /api/mot/*. Two doors, like wifi and onboarding:

    MANAGER  (login + «mot» permission, enforced by bot.py's role middleware on /api/mot/)
        GET  /api/mot/portfolio        POST /api/mot/open        POST /api/mot/result
        GET  /api/mot/unit             POST /api/mot/close       POST /api/mot/abandon
        GET  /api/mot/prices           POST /api/mot/price       POST /api/mot/token
        POST /api/mot/photo            GET  /api/mot/photo/{id}  GET  /api/mot/report
        GET  /mot

    INSPECTOR (token is the auth — NO login, NO DASHBOARD_TOKEN)
        GET  /mot-check/{token}                      the phone page
        GET  /api/mot-t/{token}                      the round (OUTSIDE the gated prefix, like /api/onb-t/)
        GET  /api/mot-t/{token}/photo/{id}           that round's own photos only
        POST /api/mot/check-result                   write ONE result into the token's OPEN round
        POST /api/mot/check-photo                    attach a photo to a component in that round

The inspector door writes results and photos and nothing else — it cannot open, close,
abandon, price, delete, mint, or read another unit. tests/test_mot_token_scope.py reads
the source of the two check_* cores and fails if they grow those words.

Every endpoint is a thin aiohttp wrapper over a pure core_*(payload, actor, today) that
takes plain dicts and returns (status, body), so the whole close-the-round chain can be
driven in a test with fake HOST caps and no web server.
"""
import datetime
import json
import traceback

from . import catalogue as C
from . import db, engine, photos, report
from .host import HOST

ALREADY_OPEN = "فيه جولة مفتوحة على هذي الشقة — أكملها أو اتركها قبل ما تفتح جديدة"
NEED_POOL = "ما نعرف إذا الشقة فيها مسبح — جاوب أول (فيها / ما فيها) عشان يثبت عدد المعايير"
NOT_FOUND = "الجولة غير موجودة"
CLOSED = "الجولة مقفلة — التصحيح يكون بجولة جديدة"
BAD_TOKEN = "الرابط ما عاد شغّال — كلّم مدير العمليات"


def _today():
    try:
        return HOST.now().date() if HOST.now else datetime.date.today()
    except Exception:
        return datetime.date.today()


def _listings():
    try:
        return dict(HOST.listings() or {}) if HOST.listings else {}
    except Exception:
        traceback.print_exc()
        return {}


def _fresh():
    """{-project_id: project} for ACTIVE onboarding projects that have NO Hostaway listing yet.
    A fresh apartment is inspected under a NEGATIVE id (minus its project id) until it lands
    in Hostaway; _reconcile_fresh then moves its rounds to the real listing id."""
    out = {}
    try:
        rows = HOST.onb_fresh_units() if HOST.onb_fresh_units else []
    except Exception:
        traceback.print_exc()
        rows = []
    for pr in rows or []:
        try:
            pid = int(pr.get("project_id") or pr.get("id"))
        except (TypeError, ValueError):
            continue
        if pr.get("listing_id") in (None, ""):
            out[-pid] = pr
    return out


def _reconcile_fresh():
    """Pre-launch rounds follow the apartment into Hostaway: for every onboarding project that
    now carries a listing_id, rows inspected under -project_id move to that listing_id. One
    project, one listing, so the mapping cannot cross apartments."""
    try:
        rows = HOST.onb_fresh_units() if HOST.onb_fresh_units else []
    except Exception:
        return
    for pr in rows or []:
        try:
            pid = int(pr.get("project_id") or pr.get("id"))
            lid = int(pr.get("listing_id"))
        except (TypeError, ValueError):
            continue
        if lid <= 0:
            continue
        if db.q1("SELECT 1 AS x FROM mot_inspection WHERE listing_id=? LIMIT 1", (-pid,)):
            db.execute("UPDATE mot_inspection SET listing_id=? WHERE listing_id=?", (lid, -pid))


def _all_units():
    """{unit_id: name} — Hostaway units from the listings master store PLUS fresh onboarding
    units under negative ids. Nothing is ever typed by hand into mot."""
    names = _listings()
    for uid, pr in _fresh().items():
        names[uid] = pr.get("unit_name") or ("مشروع #%d" % -uid)
    return names


def _meta(lid):
    try:
        lid = int(lid)
    except (TypeError, ValueError):
        return {}
    if lid < 0:
        pr = _fresh().get(lid) or {}
        return {"bedrooms": pr.get("bedrooms"), "bathrooms": None, "beds": None,
                "owner": pr.get("client_name") or "", "owner_phone": pr.get("client_whatsapp") or "",
                "fresh": True, "project_id": -lid, "district": pr.get("district") or ""}
    try:
        return dict(HOST.unit_meta(lid) or {}) if HOST.unit_meta else {}
    except Exception:
        traceback.print_exc()
        return {}


def _features(lid):
    """None = unknown to the decor sheet; [] = known to have nothing. Never collapsed.
    A fresh unit answers from its onboarding amenities only when they mention a pool;
    otherwise it is unknown and the inspector is asked."""
    try:
        lid = int(lid)
    except (TypeError, ValueError):
        return None
    if lid < 0:
        am = str((_fresh().get(lid) or {}).get("amenities") or "").lower()
        return ["pool"] if ("pool" in am or "مسبح" in am) else None
    try:
        return HOST.unit_features(lid) if HOST.unit_features else None
    except Exception:
        traceback.print_exc()
        return None


def _wifi(lid):
    try:
        if int(lid) < 0:
            return None
        return HOST.wifi_status(lid) if HOST.wifi_status else None
    except Exception:
        return None


def _log(text):
    try:
        if HOST.log_event:
            HOST.log_event("ops", text)
    except Exception:
        pass


def _price_map():
    return {k: v for k, v in db.prices().items()}


def _round_view(rnd, results=None):
    """A round as the pages read it: frozen numbers if closed, live numbers if open."""
    results = results if results is not None else db.results(rnd["id"])
    has_pool = bool(rnd["has_pool"])
    sc = engine.score(results, has_pool)
    v = dict(rnd)
    v["live"] = sc
    v["blockers"] = [b["key"] for b in engine.blockers(results, has_pool)]
    v["is_open"] = rnd.get("closed_at") is None
    v["abandoned"] = (rnd.get("note") or "") == "abandoned"
    try:
        v["fanout"] = json.loads(rnd.get("fanout") or "{}")
    except ValueError:
        v["fanout"] = {}
    return v


# ============================================================ manager cores ==================

def core_portfolio(today=None):
    today = today or _today()
    _reconcile_fresh()
    names = _all_units()
    latest = db.latest_closed_by_listing()
    opens = db.open_by_listing()
    prices = _price_map()
    res = db.results_many([r["id"] for r in latest.values()])
    rows = []
    tot_out = 0.0
    n_ok = n_blocked = n_overdue = n_never = 0
    for lid, name in sorted(names.items(), key=lambda kv: str(kv[1])):
        lr = latest.get(lid)
        op = opens.get(lid)
        row = {"listing_id": lid, "name": name, "latest": None, "open": None,
               "outstanding_sar": 0.0, "blockers": 0, "overdue": False,
               "fresh": lid < 0, "project_id": (-lid if lid < 0 else None)}
        if lr:
            rr = res.get(lr["id"], {})
            has_pool = bool(lr["has_pool"])
            meta = _meta(lid)
            out = engine.outstanding_sar(rr, prices, meta, has_pool)
            bl = engine.blockers(rr, has_pool)
            row["latest"] = {"id": lr["id"], "closed_at": lr["closed_at"],
                             "compliance_pct": lr["compliance_pct"], "inspected_pct": lr["inspected_pct"],
                             "denominator": lr["denominator"], "has_pool": has_pool,
                             "recheck_due": lr["recheck_due"], "quote_id": lr["quote_id"],
                             "inspector": lr["inspector"]}
            row["outstanding_sar"] = out
            row["blockers"] = len(bl)
            row["overdue"] = bool(lr["recheck_due"] and str(lr["recheck_due"])[:10] < today.isoformat()
                                  and (out > 0 or bl))
            tot_out += out
            if bl:
                n_blocked += 1
            elif (lr["compliance_pct"] or 0) >= 100:
                n_ok += 1
            if row["overdue"]:
                n_overdue += 1
        else:
            n_never += 1
        if op:
            orr = db.results(op["id"])
            row["open"] = {"id": op["id"], "opened_at": op["opened_at"], "inspector": op["inspector"],
                           "live": engine.score(orr, bool(op["has_pool"]))}
        rows.append(row)
    return 200, {"ok": True, "today": today.isoformat(), "rows": rows,
                 "summary": {"units": len(rows), "compliant": n_ok, "blocked": n_blocked,
                             "overdue": n_overdue, "never": n_never,
                             "outstanding_sar": round(tot_out, 2)},
                 "catalogue_version": C.CATALOGUE_VERSION}


def core_unit(listing_id):
    try:
        lid = int(listing_id)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "bad listing_id"}
    _reconcile_fresh()
    names = _all_units()
    rounds = db.rounds_for(lid)
    res = db.results_many([r["id"] for r in rounds])
    feats = _features(lid)
    meta = _meta(lid)
    views = [_round_view(r, res.get(r["id"], {})) for r in rounds]
    open_v = next((v for v in views if v["is_open"]), None)
    if open_v:
        open_v["results"] = res.get(open_v["id"], {})
        open_v["photos"] = db.photos(open_v["id"])
        open_v["components"] = engine.components_for(bool(open_v["has_pool"]))
        open_v["prices"] = _price_map()
        open_v["quote_preview"] = engine.quote_lines(open_v["results"], open_v["prices"], meta,
                                                     bool(open_v["has_pool"]), today=_today())
    return 200, {"ok": True, "listing_id": lid, "name": names.get(lid) or ("#%d" % lid),
                 "meta": meta, "pool_known": feats is not None,
                 "has_pool": (("pool" in feats) if feats is not None else None),
                 "wifi": _wifi(lid), "rounds": views, "open": open_v,
                 "catalogue_version": C.CATALOGUE_VERSION}


def core_open(payload, actor="", today=None):
    p = payload or {}
    try:
        lid = int(p.get("listing_id"))
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "bad listing_id"}
    names = _all_units()
    if lid not in names:
        return 404, {"ok": False, "error": "الشقة مو في ماستر الشقق ولا في «ضم الوحدات»"}
    feats = _features(lid)
    answer = p.get("has_pool")
    reason = (p.get("pool_reason") or "").strip()
    if feats is None:
        # unknown ≠ no pool: the inspector is asked once and the answer teaches the sheet
        if answer is None:
            return 409, {"ok": False, "error": NEED_POOL, "need_pool_answer": True}
        has_pool = bool(answer)
        source = "inspector"
        try:
            if HOST.set_unit_features and lid > 0:
                HOST.set_unit_features(lid, ["pool"] if has_pool else [], actor)
        except Exception:
            traceback.print_exc()
    else:
        has_pool = "pool" in feats
        source = "decor"
        if answer is not None and bool(answer) != has_pool:
            if not reason:
                return 400, {"ok": False, "error": "تجاوز جدول المرافق يحتاج سبب مكتوب"}
            has_pool = bool(answer)
            source = "override"
    comps = engine.components_for(has_pool)
    try:
        rid = db.open_round(lid, names.get(lid), C.CATALOGUE_VERSION, has_pool, source,
                            len(comps), by=actor, inspector=(p.get("inspector") or actor))
    except db.RoundAlreadyOpen:
        return 409, {"ok": False, "error": ALREADY_OPEN, "open": db.open_round_for(lid)}
    if source == "override":
        db.execute("UPDATE mot_inspection SET note=? WHERE id=?", ("تجاوز المسبح: " + reason, rid))
    # criterion 13 is answered by the wifi subsystem, never re-typed
    w = _wifi(lid)
    if w is not None:
        db.set_result(rid, C.WIFI_KEY, "available" if w else "missing", source="wifi", by="wifi")
    _log("مطابقة السياحة · فتح جولة على %s · %d مكوّن%s" % (
        names.get(lid), len(comps), " (مع مسبح)" if has_pool else ""))
    return 200, {"ok": True, "id": rid, "round": _round_view(db.round_(rid)), "components": comps}


def _apply_result(rnd, p, actor, allow_billed):
    key = (p.get("comp_key") or "").strip()
    comp = C.by_key(key)
    if not comp or (comp["pool_only"] and not rnd["has_pool"]):
        return 400, {"ok": False, "error": "مكوّن غير معروف لهذي الجولة"}
    state = (p.get("state") or "").strip()
    if state not in engine.STATES:
        return 400, {"ok": False, "error": "الحالة: متوفر / غير متوفر / لم يُفحص"}
    source = "inspector"
    note = p.get("note")
    if key == C.WIFI_KEY:
        cur = db.results(rnd["id"]).get(key) or {}
        if cur.get("source") == "wifi" and cur.get("state") != state:
            if not (note or "").strip():
                return 400, {"ok": False, "error": "الإنترنت يجي من «اشتراكات النت» — تجاوزه يحتاج سبب"}
            source = "override"
    try:
        r = db.set_result(rnd["id"], key, state, qty=p.get("qty"),
                          billed_to=(p.get("billed_to") if allow_billed else None),
                          source=source, note=note, by=actor)
    except db.RoundClosed:
        return 409, {"ok": False, "error": CLOSED}
    results = db.results(rnd["id"])
    return 200, {"ok": True, "result": r, "live": engine.score(results, bool(rnd["has_pool"]))}


def core_result(payload, actor=""):
    p = payload or {}
    rnd = db.round_(p.get("id"))
    if not rnd:
        return 404, {"ok": False, "error": NOT_FOUND}
    if rnd.get("closed_at"):
        return 409, {"ok": False, "error": CLOSED}
    return _apply_result(rnd, p, actor, allow_billed=True)


def _fanout(rnd, results, q, meta, today, actor):
    """Everything closing a round produces. Each branch is guarded so one failing bridge
    cannot stop the round from closing — the record says what happened."""
    name = rnd["apartment_name"] or ("#%d" % rnd["listing_id"])
    out = {"quote": None, "purchase_ticket": None, "maint_tickets": [], "documents": [],
           "blocked": [b["key"] for b in q["blocked"]], "errors": []}
    # (a) owner quote
    if q["owner"]:
        items = engine.quote_items(q["owner"])
        payload = {
            "client_name": meta.get("owner") or "",
            "client_phone": meta.get("owner_phone") or "",
            "items": items, "by": actor or "mot",
            "notes": "نواقص مطابقة وزارة السياحة — %s — جولة %s (%d/%d مكوّن)" % (
                name, today.isoformat(), engine.score(results, bool(rnd["has_pool"]))["available"],
                rnd["denominator"]),
        }
        try:
            if HOST.save_quote:
                qd = HOST.save_quote(payload) or {}
                out["quote"] = {"id": qd.get("id"), "number": qd.get("number"),
                                "total": (qd.get("totals") or {}).get("grand_total"),
                                "lines": len(q["owner"])}
            else:
                out["errors"].append("quotes bridge absent")
        except Exception as e:
            traceback.print_exc()
            out["errors"].append("quote: %s" % e)
    # (b) one internal purchase ticket for Ouja-billed products — carries every field the
    #     real proc form asks for, so the ops supervisor opens the Discord proc ticket by
    #     copy-paste. This is a KNOWN SEAM, not a silent gap: _proc_open_ticket needs a live
    #     Discord interaction and cannot be called from the web.
    if q["ouja_products"]:
        lines = ["الوحدات: %s" % name, "السبب: missing (نواقص مطابقة السياحة)",
                 "البنود:"]
        for l in q["ouja_products"]:
            lines.append("  - %s × %d = %.0f ر.س (معيار %d)" % (l["label_ar"], l["qty"], l["total"], l["criterion_no"]))
        lines.append("المبلغ: %.0f ر.س" % q["ouja_products_total"])
        lines.append("جولة المطابقة #%d · افتح تذكرة مشتريات (proc) في ديسكورد بهذي البيانات" % rnd["id"])
        try:
            if HOST.ticket_create:
                t = HOST.ticket_create("مشتريات مطابقة السياحة — %s" % name,
                                       description="\n".join(lines),
                                       lid=(rnd["listing_id"] if rnd["listing_id"] > 0 else None),
                                       priority="med", category="مشتريات", source="manual",
                                       source_ref="mot:%d" % rnd["id"], created_by=actor or "mot",
                                       cost=q["ouja_products_total"])
                out["purchase_ticket"] = (t or {}).get("id")
            else:
                out["errors"].append("ticket bridge absent")
        except Exception as e:
            traceback.print_exc()
            out["errors"].append("purchase: %s" % e)
    # (c) maintenance tickets for Ouja-billed works
    for l in q["ouja_works"]:
        try:
            if HOST.ticket_create:
                t = HOST.ticket_create("%s — %s" % (l["label_ar"], name),
                                       description="معيار %d (%s) غير متوفر في جولة المطابقة #%d%s" % (
                                           l["criterion_no"], l["criterion_ar"], rnd["id"],
                                           (" · " + l["note"]) if l.get("note") else ""),
                                       lid=(rnd["listing_id"] if rnd["listing_id"] > 0 else None),
                                       priority="med", category="صيانة",
                                       source="manual", source_ref="mot:%d" % rnd["id"],
                                       created_by=actor or "mot")
                out["maint_tickets"].append((t or {}).get("id"))
        except Exception as e:
            traceback.print_exc()
            out["errors"].append("maint %s: %s" % (l["key"], e))
    # (d) documents -> onboarding license-stage tasks (when the unit has a project)
    if q["documents"]:
        keys = [d["task_key"] for d in q["documents"] if d.get("task_key")]
        try:
            if HOST.onb_license_tasks:
                r = HOST.onb_license_tasks(rnd["listing_id"], keys) or {}
                out["documents"] = {"keys": keys, "project_id": r.get("project_id"),
                                    "seeded": bool(r.get("project_id"))}
            else:
                out["documents"] = {"keys": keys, "project_id": None, "seeded": False}
        except Exception as e:
            traceback.print_exc()
            out["documents"] = {"keys": keys, "project_id": None, "seeded": False}
            out["errors"].append("onb: %s" % e)
    return out


def core_close(payload, actor="", today=None):
    p = payload or {}
    today = today or _today()
    rnd = db.round_(p.get("id"))
    if not rnd:
        return 404, {"ok": False, "error": NOT_FOUND}
    if rnd.get("closed_at"):
        return 409, {"ok": False, "error": CLOSED}
    has_pool = bool(rnd["has_pool"])
    results = db.results(rnd["id"])
    sc = engine.score(results, has_pool)
    if sc["not_inspected"]:
        return 409, {"ok": False, "not_inspected": sc["not_inspected"],
                     "error": "باقي %d مكوّن ما انفحص — الجولة ما تنقفل ناقصة (تقدر تتركها بدل الإغلاق)"
                              % sc["not_inspected"]}
    meta = _meta(rnd["listing_id"])
    q = engine.quote_lines(results, _price_map(), meta, has_pool, today=today)
    if q["unpriced"] and not p.get("allow_unpriced"):
        return 409, {"ok": False, "unpriced": q["unpriced"],
                     "error": "فيه %d بند بدون سعر — سعّره في قائمة الأسعار أو أكّد الإغلاق بدونه"
                              % len(q["unpriced"])}
    fan = _fanout(rnd, results, q, meta, today, actor)
    due = (p.get("recheck_due") or "").strip()[:10] or (today + datetime.timedelta(days=engine.RECHECK_DAYS)).isoformat()
    qid = (fan.get("quote") or {}).get("id")
    try:
        closed = db.close_round(rnd["id"], sc["compliance_pct"], sc["inspected_pct"], due, qid,
                                json.dumps(fan, ensure_ascii=False), by=actor)
    except db.RoundClosed:
        return 409, {"ok": False, "error": CLOSED}
    total = q["owner_total"] + q["ouja_products_total"]
    _log("مطابقة السياحة · %s · مطابقة %s٪ · فحص %s٪ · نواقص %.0f ر.س%s" % (
        rnd["apartment_name"], sc["compliance_pct"], sc["inspected_pct"], total,
        (" · %d معيار إنشائي" % len(fan["blocked"])) if fan["blocked"] else ""))
    return 200, {"ok": True, "round": _round_view(closed, results), "score": sc, "fanout": fan,
                 "quote": q, "recheck_due": due}


def core_abandon(payload, actor=""):
    rnd = db.round_((payload or {}).get("id"))
    if not rnd:
        return 404, {"ok": False, "error": NOT_FOUND}
    try:
        r = db.abandon_round(rnd["id"], by=actor)
    except db.RoundClosed:
        return 409, {"ok": False, "error": CLOSED}
    _log("مطابقة السياحة · ترك جولة #%d على %s" % (rnd["id"], rnd["apartment_name"]))
    return 200, {"ok": True, "round": _round_view(r)}


UNIT_PREFIX = "Ouja |"
UNIT_NAME_MAX = 50
CLIENT_TYPES = ("owner", "tenant", "prospect")
UNIT_KINDS = ("tower", "compound", "standalone")
FURNISH_STATES = ("furnished", "partial", "unfurnished")


def core_new_unit(payload, actor=""):
    """A FRESH apartment (not in Hostaway yet) = an onboarding project. This opens one through
    the same db function «ضم الوحدات» uses (pure DB, no notification), so the unit shows in
    both tabs with no second registry. Returns the negative mot unit id."""
    p = payload or {}
    name = " ".join(str(p.get("unit_name") or "").split())
    if not name:
        return 400, {"ok": False, "error": "اسم الشقة مطلوب"}
    if not name.startswith(UNIT_PREFIX):
        name = "%s %s" % (UNIT_PREFIX, name.lstrip("| ").strip())
    if len(name) > UNIT_NAME_MAX:
        return 400, {"ok": False, "error": "اسم الشقة طويل — الحد %d حرف" % UNIT_NAME_MAX}
    owner = str(p.get("client_name") or "").strip()
    phone = "".join(ch for ch in str(p.get("client_whatsapp") or "") if ch.isdigit() or ch == "+")[:18]
    district = str(p.get("district") or "").strip()
    if not owner or not phone or not district:
        return 400, {"ok": False, "error": "المالك وجواله والحي مطلوبة — «ضم الوحدات» ما يفتح مشروعًا ناقصًا"}
    try:
        bedrooms = int(p.get("bedrooms"))
        if bedrooms < 0:
            raise ValueError
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "عدد غرف النوم رقم"}
    ctype = p.get("client_type") if p.get("client_type") in CLIENT_TYPES else "owner"
    kind = p.get("unit_kind") if p.get("unit_kind") in UNIT_KINDS else "compound"
    fstate = p.get("furnish_state") if p.get("furnish_state") in FURNISH_STATES else "furnished"
    fields = {"unit_name": name, "client_name": owner, "client_whatsapp": phone, "district": district,
              "bedrooms": bedrooms, "client_type": ctype, "unit_kind": kind, "furnish_state": fstate}
    if p.get("has_pool") is True:
        fields["amenities"] = "pool"
    if not HOST.onb_create_unit:
        return 503, {"ok": False, "error": "«ضم الوحدات» غير متاح — ما نقدر نسجّل شقة جديدة"}
    pr = HOST.onb_create_unit(fields, actor) or {}
    pid = pr.get("id")
    if not pid:
        return 500, {"ok": False, "error": "ما انفتح المشروع"}
    _log("مطابقة السياحة · شقة جديدة قيد الضم: %s (مشروع #%s)" % (name, pid))
    return 200, {"ok": True, "listing_id": -int(pid), "project_id": int(pid), "name": name}


def core_prices(today=None):
    today = today or _today()
    pm = _price_map()
    rows = []
    for c in C.components(True):
        p = pm.get(c["key"]) or {}
        rows.append(dict(c, price_sar=p.get("price_sar"), set_by=p.get("set_by"), set_at=p.get("set_at"),
                         stale=engine._is_stale(p.get("set_at"), today) if p else False))
    return 200, {"ok": True, "rows": rows, "stale_days": engine.STALE_DAYS}


def core_price(payload, actor=""):
    p = payload or {}
    key = (p.get("comp_key") or "").strip()
    if not C.by_key(key):
        return 400, {"ok": False, "error": "مكوّن غير معروف"}
    try:
        price = float(p.get("price_sar"))
        if price < 0:
            raise ValueError
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "السعر رقم موجب"}
    return 200, {"ok": True, "price": db.set_price(key, price, by=actor)}


def core_token(payload, actor=""):
    rnd = db.round_((payload or {}).get("id"))
    if not rnd:
        return 404, {"ok": False, "error": NOT_FOUND}
    if rnd.get("closed_at"):
        return 409, {"ok": False, "error": CLOSED}
    tok = db.mint_token(rnd["id"], by=actor)
    base = ""
    try:
        base = (HOST.public_base() if HOST.public_base else "") or ""
    except Exception:
        base = ""
    return 200, {"ok": True, "token": tok, "link": "%s/mot-check/%s" % (base.rstrip("/"), tok)}


def core_photo(rnd, comp_key, data, actor=""):
    """Shared by both doors AFTER each has resolved its own round."""
    if rnd.get("closed_at"):
        return 409, {"ok": False, "error": CLOSED}
    comp = C.by_key(comp_key or "")
    if not comp:
        return 400, {"ok": False, "error": "مكوّن غير معروف"}
    n = db.photo_count(rnd["id"], comp["key"])
    if n >= photos.MAX_PER_COMPONENT:
        return 409, {"ok": False, "error": "الحد %d صور للمكوّن" % photos.MAX_PER_COMPONENT}
    rel = photos.save(HOST.state_dir, rnd["id"], comp["key"], n + 1, data)
    try:
        pid = db.add_photo(rnd["id"], comp["key"], rel, by=actor)
    except db.RoundClosed:
        return 409, {"ok": False, "error": CLOSED}
    return 200, {"ok": True, "photo": {"id": pid, "comp_key": comp["key"], "url": rel},
                 "count": n + 1}


def core_report(rid, today=None):
    rnd = db.round_(rid)
    if not rnd:
        return 404, {"ok": False, "error": NOT_FOUND}
    results = db.results(rnd["id"])
    ok, why = engine.can_export_evidence(rnd, results, bool(rnd["has_pool"]))
    if not ok:
        return 409, {"ok": False, "error": why}
    html = report.html_for(rnd, results, db.photos(rnd["id"]), _meta(rnd["listing_id"]),
                           _price_map(), state_dir=HOST.state_dir)
    return 200, {"ok": True, "html": html, "round": rnd}


# ============================================================ inspector cores ================
# These two are the WHOLE write surface of the token door. Keep them small; a test reads them.

def core_check_get(token):
    rnd = db.round_by_token(token)
    if not rnd:
        return 404, {"ok": False, "error": BAD_TOKEN}
    results = db.results(rnd["id"])
    ph = {}
    for p in db.photos(rnd["id"]):
        ph.setdefault(p["comp_key"], []).append(p["id"])
    return 200, {"ok": True, "round": {"id": rnd["id"], "apartment_name": rnd["apartment_name"],
                                       "has_pool": bool(rnd["has_pool"]), "opened_at": rnd["opened_at"],
                                       "denominator": rnd["denominator"]},
                 "components": engine.components_for(bool(rnd["has_pool"])),
                 "results": {k: {"state": r["state"], "qty": r["qty"], "note": r["note"],
                                 "source": r["source"]} for k, r in results.items()},
                 "photos": ph, "max_photos": photos.MAX_PER_COMPONENT,
                 "live": engine.score(results, bool(rnd["has_pool"]))}


def core_check_result(payload, actor=""):
    p = payload or {}
    rnd = db.round_by_token(p.get("token"))
    if not rnd:
        return 404, {"ok": False, "error": BAD_TOKEN}
    who = (p.get("who") or "").strip()[:60] or "رابط الفحص"
    return _apply_result(rnd, p, who, allow_billed=False)


# ============================================================ aiohttp wrappers ===============

def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def _actor(request):
    try:
        return HOST.actor(request) if HOST.actor else ""
    except Exception:
        return ""


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
    """PUBLIC wrapper — NO auth. Used ONLY by the inspector token door."""
    async def _w(request):
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


def _reply(pair):
    status, body = pair
    return HOST.json_response(body, status)


async def _multipart(request):
    """-> (fields, bytes). Same shape as the cleaning-photo uploader."""
    reader = await request.multipart()
    fields, data = {}, b""
    async for part in reader:
        if part.name == "file":
            chunks, total = [], 0
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                total += len(chunk)
                if total > photos.MAX_UPLOAD_MB * 1024 * 1024:
                    raise ValueError("too_large")
                chunks.append(chunk)
            data = b"".join(chunks)
        else:
            fields[part.name] = (await part.text()).strip()
    return fields, data


async def _persist():
    try:
        if HOST.persist and HOST.web_thread:
            await HOST.web_thread(HOST.persist)
    except Exception:
        traceback.print_exc()


async def api_portfolio(request):
    return _reply(core_portfolio())


async def api_unit(request):
    return _reply(core_unit(request.query.get("listing_id")))


async def api_open(request):
    return _reply(core_open(await _body(request), actor=_actor(request)))


async def api_result(request):
    return _reply(core_result(await _body(request), actor=_actor(request)))


async def api_close(request):
    pair = core_close(await _body(request), actor=_actor(request))
    if pair[0] == 200:
        await _persist()          # the quote + tickets live in bot.py's JSON state
    return _reply(pair)


async def api_new_unit(request):
    return _reply(core_new_unit(await _body(request), actor=_actor(request)))


async def api_abandon(request):
    return _reply(core_abandon(await _body(request), actor=_actor(request)))


async def api_prices(request):
    return _reply(core_prices())


async def api_price(request):
    return _reply(core_price(await _body(request), actor=_actor(request)))


async def api_token(request):
    return _reply(core_token(await _body(request), actor=_actor(request)))


async def api_photo(request):
    try:
        fields, data = await _multipart(request)
    except ValueError:
        return HOST.json_response({"ok": False, "error": "الصورة أكبر من %dMB" % photos.MAX_UPLOAD_MB}, 400)
    if not data:
        return HOST.json_response({"ok": False, "error": "ما وصلت صورة"}, 400)
    rnd = db.round_(fields.get("id"))
    if not rnd:
        return HOST.json_response({"ok": False, "error": NOT_FOUND}, 404)
    return _reply(await HOST.web_thread(core_photo, rnd, fields.get("comp_key"), data, _actor(request)))


def _photo_response(photo):
    full = photos.abs_path(HOST.state_dir, (photo or {}).get("url"))
    if not full:
        return HOST.json_response({"ok": False, "error": "not found"}, 404)
    try:
        return HOST.web.FileResponse(full)
    except Exception:
        return HOST.json_response({"ok": False, "error": "not found"}, 404)


async def api_photo_file(request):
    p = db.q1("SELECT * FROM mot_photo WHERE id=?", (request.match_info.get("id"),))
    return _photo_response(p)


async def api_report(request):
    pair = core_report(request.query.get("id"))
    if pair[0] != 200:
        return _reply(pair)
    html = pair[1]["html"]
    rnd = pair[1]["round"]
    if request.query.get("fmt") == "html" or not report.chromium_available():
        return HOST.web.Response(text=html, content_type="text/html")
    try:
        pdf = await HOST.web_thread(report.pdf_bytes, html)
    except Exception:
        traceback.print_exc()
        return HOST.web.Response(text=html, content_type="text/html")
    fn = "mot-%d-%s.pdf" % (rnd["id"], str(rnd["closed_at"])[:10])
    return HOST.web.Response(body=pdf, content_type="application/pdf",
                             headers={"Content-Disposition": 'inline; filename="%s"' % fn})


# --- inspector door

async def api_check_get(request):
    return _reply(core_check_get(request.match_info.get("token")))


async def api_check_result(request):
    return _reply(core_check_result(await _body(request)))


async def api_check_photo(request):
    try:
        fields, data = await _multipart(request)
    except ValueError:
        return HOST.json_response({"ok": False, "error": "الصورة أكبر من %dMB" % photos.MAX_UPLOAD_MB}, 400)
    if not data:
        return HOST.json_response({"ok": False, "error": "ما وصلت صورة"}, 400)
    rnd = db.round_by_token(fields.get("token"))
    if not rnd:
        return HOST.json_response({"ok": False, "error": BAD_TOKEN}, 404)
    who = (fields.get("who") or "").strip()[:60] or "رابط الفحص"
    return _reply(await HOST.web_thread(core_photo, rnd, fields.get("comp_key"), data, who))


async def api_check_photo_file(request):
    rnd = db.round_by_token(request.match_info.get("token"))
    if not rnd:
        return HOST.json_response({"ok": False, "error": BAD_TOKEN}, 404)
    p = db.q1("SELECT * FROM mot_photo WHERE id=? AND inspection_id=?",
              (request.match_info.get("id"), rnd["id"]))
    return _photo_response(p)


async def handle_page(request):
    from . import page
    return HOST.web.Response(text=page.HTML, content_type="text/html")


async def handle_check_page(request):
    from . import check_page
    return HOST.web.Response(text=check_page.HTML, content_type="text/html")


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    # manager door — every /api/mot/* GET and POST is role-gated by bot.py
    g("/api/mot/portfolio", _safe(api_portfolio))
    g("/api/mot/unit", _safe(api_unit))
    g("/api/mot/prices", _safe(api_prices))
    g("/api/mot/photo/{id}", _safe(api_photo_file))
    g("/api/mot/report", _safe(api_report))
    p("/api/mot/open", _safe(api_open))
    p("/api/mot/result", _safe(api_result))
    p("/api/mot/close", _safe(api_close))
    p("/api/mot/abandon", _safe(api_abandon))
    p("/api/mot/new-unit", _safe(api_new_unit))
    p("/api/mot/price", _safe(api_price))
    p("/api/mot/token", _safe(api_token))
    p("/api/mot/photo", _safe(api_photo))
    g("/mot", handle_page)
    # inspector door — token is the auth. Reads sit OUTSIDE the gated prefix (like /api/onb-t/);
    # the two writes keep /api/mot/check-* and are exact-path exempt in _ROLE_EXEMPT_WRITES.
    g("/api/mot-t/{token}", _safe_public(api_check_get))
    g("/api/mot-t/{token}/photo/{id}", _safe_public(api_check_photo_file))
    p("/api/mot/check-result", _safe_public(api_check_result))
    p("/api/mot/check-photo", _safe_public(api_check_photo))
    g("/mot-check/{token}", handle_check_page)
