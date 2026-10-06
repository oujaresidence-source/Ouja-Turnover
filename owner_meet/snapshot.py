# -*- coding: utf-8 -*-
"""
owner_meet.snapshot — build the frozen meeting snapshot from HOST caps + the pure modules.

    {"meta":      {schema_version, period, meeting_date, built_at, data_as_of, degraded},
     "owner":     everything an owner may see (R1–R5): his own units, bands, never a count,
     "presenter": readiness checks, peer counts, notes — NEVER rendered on an owner surface}

Runs on owner_meet.jobs' own pool (never the web lane). Money comes ONLY from
HOST.month_report / HOST.unit_month (M1); reservations ONLY from HOST.reservations_window (P6).
"""

import datetime
import json
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from . import abnb, config, db, engine, money, ops, periods, privacy, redact, texts
from .host import HOST

MONTH_WORKERS = 4                     # same ceiling _owner_portal_data uses for cold months


def _f(x):
    """Decimal -> float for JSON (2dp values are exact enough for display; M1 re-reads via str)."""
    return float(x) if isinstance(x, Decimal) else x


def _row_json(r):
    """A month row for the OWNER half: money only — no computed_at / cleaning_type internals."""
    return {k: _f(v) for k, v in r.items() if k not in ("computed_at", "cleaning_type", "stale")}


def _r(x, nd):
    return None if x is None else round(float(x), nd)


def _round_band(band, kind):
    """Owner-facing values are rounded (money 2dp, ratios 4dp, rating 2dp): a 17-digit float is
    noise to the owner and a fingerprint to anyone reverse-engineering the comparison group."""
    nd = {"occupancy": 4, "rating": 2}.get(kind, 2)
    out = dict(band)
    for k in ("value", "p25", "p50", "p75"):
        out[k] = _r(out.get(k), nd)
    return out


def _money_block(rows):
    tot = money.sum_rows(rows)
    wf = money.waterfall(tot)
    return {
        "months": [_row_json(r) for r in rows],
        "total": {k: _f(v) for k, v in tot.items()},
        "waterfall": {"rows": [{"key": r["key"], "amount": _f(r["amount"]), "sign": r["sign"]}
                               for r in wf["rows"]],
                      "reconciled": wf["reconciled"], "residual": _f(wf["residual"])},
        "per100": money.per_100(wf),
    }


def _date(v):
    return v if isinstance(v, datetime.date) else datetime.date.fromisoformat(str(v)[:10])


def _check(level, key, text_ar, **extra):
    d = {"level": level, "key": key, "text_ar": text_ar}
    d.update(extra)
    return d


# ------------------------------------------------------------------ money
def collect_money(owner, scope_lids, months, partial, progress=None):
    """-> (owner_rows, {lid: unit_rows}). One month_report per month (cached by the statement
    layer), one unit_slice per (month, lid). Parallel over months, ≤ MONTH_WORKERS."""
    def one(mk):
        # One month that cannot be computed becomes a RED readiness line for that month (missing),
        # never a dead build: the other eleven months are still worth seeing before the meeting.
        try:
            rep = HOST.month_report(owner, mk)
            units = {lid: HOST.unit_month(owner, mk, lid) for lid in scope_lids}
        except Exception as e:
            print("[owner_meet] month %s for %s failed: %s" % (mk, owner, e))
            rep, units = None, {}
        return mk, rep, units

    done = {}
    with ThreadPoolExecutor(max_workers=MONTH_WORKERS, thread_name_prefix="meet-month") as ex:
        for i, (mk, rep, units) in enumerate(ex.map(one, months)):
            done[mk] = (rep, units)
            if progress:
                progress(10 + int(40 * (i + 1) / max(1, len(months))), "كشف شهر %s" % mk)
    owner_rows = [money.month_row(mk, done[mk][0], partial=(mk == partial)) for mk in months]
    unit_rows = {lid: [money.month_row(mk, done[mk][1].get(lid), partial=(mk == partial)) for mk in months]
                 for lid in scope_lids}
    expenses = {lid: [] for lid in scope_lids}
    for mk in months:
        for lid in scope_lids:
            for x in ((done[mk][1].get(lid) or {}).get("exp_lines") or []):
                expenses[lid].append({"id": x.get("id"), "date": str(x.get("date") or "")[:10], "category": x.get("category") or "",
                                      "description": x.get("description") or x.get("label") or "",
                                      "amount": _f(money.D(x.get("amount"))), "receipt": bool(x.get("receipt_url"))})
    return owner_rows, unit_rows, expenses


def scope_rows(owner_rows, unit_rows, scope_lids, whole_owner):
    """The money rows for the meeting's scope: the OWNER statement when the meeting covers all of
    his units (M1 at owner level); otherwise the per-month sum of the chosen units' slices."""
    if whole_owner:
        return owner_rows
    out = []
    for i, base in enumerate(owner_rows):
        parts = [unit_rows[lid][i] for lid in scope_lids]
        r = {"m": base["m"], "partial": base["partial"],
             "missing": any(p["missing"] for p in parts),
             "degraded": any(p["degraded"] for p in parts) or base["degraded"],
             "computed_at": base.get("computed_at")}
        for f in money.FIELDS:
            r[f] = sum((p[f] for p in parts), Decimal(0))
        out.append(r)
    return out


# ------------------------------------------------------------------ nights & peers
def night_stats(nights, start, end, months):
    """{lid: {"nights", "income", "months": set(mkey), "by_month": {mkey: nights}}} inside [start, end]."""
    s, e = _date(start), _date(end)
    out = {}
    for lid, d, nightly in nights:
        d = _date(d)
        if d < s or d > e:
            continue
        try:
            lid = int(lid)
        except (TypeError, ValueError):
            continue
        st = out.setdefault(lid, {"nights": 0, "income": 0.0, "months": set(), "by_month": {}})
        mk = periods.mkey(d)
        st["nights"] += 1
        st["income"] += float(nightly or 0)
        st["months"].add(mk)
        st["by_month"][mk] = st["by_month"].get(mk, 0) + 1
    return out


def peer_metrics(stats, days, ratings, nets, months):
    """Per-lid metric values. `nets` = {lid: {mkey: owner_net}} (cache-only for peers)."""
    vals = {k: {} for k in ("income", "occupancy", "adr", "revpar", "rating", "net_per_night")}
    for lid, st in stats.items():
        vals["income"][lid] = st["income"]
        vals["occupancy"][lid] = st["nights"] / float(days) if days else None
        vals["adr"][lid] = (st["income"] / st["nights"]) if st["nights"] else None
        vals["revpar"][lid] = st["income"] / float(days) if days else None
    for lid, (n, R) in ratings.items():
        vals["rating"][lid] = engine.rating5(n, R)
    for lid, by in nets.items():
        if all(m in by for m in months):
            vals["net_per_night"][lid] = sum(float(by[m] or 0) for m in months) / float(days) if days else None
    return vals


METRICS = ("income", "net_per_night", "occupancy", "adr", "rating", "revpar")
NEXT_NIGHTS = 14
_CP_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cp", "data")


def _names_in(rec):
    """Every person-name field a ticket record can carry (staff + guest), for redaction."""
    out = []
    for k, v in (rec or {}).items():
        if isinstance(v, str) and (k in ("opener", "assignee", "closed_by", "claimed_by", "returned_by", "owner_name")
                                   or k.endswith("_by")):
            out.append(v)
    co = (rec or {}).get("closeout") or {}
    if co.get("by"):
        out.append(str(co["by"]))
    for t in (rec or {}).get("trail") or []:
        if isinstance(t, dict) and t.get("by"):
            out.append(str(t["by"]))
    return out


def collect_ops(owner, units_out, all_lids, rows, start, end_d, today, rules, notes):
    """Chapters 7–10 for every unit: raw rows through caps, joined + redacted by owner_meet.ops.
    Each source that fails becomes a presenter note and an EMPTY section — never a dead build."""
    s_d = _date(start)

    def grab(name, fn, default):
        try:
            return fn()
        except Exception as e:
            print("[owner_meet] %s read failed: %s" % (name, e))
            notes.append({"key": "source_" + name, "text_ar": "تعذّر قراءة %s — القسم يظهر فاضياً" % name})
            return default

    staff = grab("staff", lambda: HOST.staff_names() if HOST.staff_names else [], [])
    reviews_all = HOST.reviews_all() or []
    types_ar = grab("rr_types", lambda: HOST.rr_types() if HOST.rr_types else {}, {})
    for u in units_out:
        lid = u["lid"]
        maint = grab("maint", lambda: HOST.maint_tickets([lid]) if HOST.maint_tickets else [], [])
        dash = grab("dash", lambda: HOST.dash_tickets([lid]) if HOST.dash_tickets else [], [])
        proc = grab("proc", lambda: HOST.proc_tickets([lid]) if HOST.proc_tickets else [], [])
        rr = grab("rr", lambda: HOST.rr_tickets([lid], [u["name"]]) if HOST.rr_tickets else [], [])
        rec_rows = grab("recovery", lambda: HOST.recovery_for([lid], s_d, end_d) if HOST.recovery_for else [], [])
        price = grab("price", lambda: HOST.price_actions([lid], s_d, end_d) if HOST.price_actions else [], [])
        dp = grab("directpay", lambda: HOST.directpay_for([lid], s_d, end_d) if HOST.directpay_for else [], [])
        clean = grab("cleaning", lambda: HOST.cleaning_feedback([lid], s_d, end_d) if HOST.cleaning_feedback else [], [])
        permit = grab("permit", lambda: HOST.permit_for(lid) if HOST.permit_for else None, None)
        guests = [r.get("guestName") for r in rows if str(r.get("listingMapId")) == str(lid) and r.get("guestName")]
        guests += [r.get("guest") for r in rr if r.get("guest")]
        guests += [r.get("guest_name") for r in reviews_all
                   if str(r.get("listing_id")) == str(lid) and r.get("guest_name")]
        guests += [d.get("guest") for d in dash if d.get("guest")]
        u["_guests"] = sorted({str(g).strip() for g in guests if g})
        people = list(staff) + [n for rec in maint + proc + rr + dash for n in _names_in(rec)]
        people += [d.get("assignee") for d in dash if d.get("assignee")] + [d.get("created_by") for d in dash if d.get("created_by")]
        people += [x.get("who") for d in dash for x in (d.get("log") or []) if isinstance(x, dict) and x.get("who")]
        u["_staff"] = sorted({str(p).strip() for p in people if p})
        red = redact.Redactor(guest_names=guests, staff_names=people)
        m_rows, m_stats = ops.maintenance(maint, dash, s_d, end_d, today, red)
        p_rows = ops.purchases(proc, s_d, end_d, red)
        ar_fn = HOST.rr_ar_texts or (lambda rec: {"ok": False})
        c_rows, ring, c_notes = ops.claims(rr, s_d, end_d, today, HOST.rr_outcome or (lambda c, r: "unknown"),
                                           HOST.rr_item_lines or (lambda x: ([], 0)), ar_fn, types_ar, red)
        notes.extend(c_notes)
        res_ids = [r.get("reservation_id") or (r.get("raw") or {}).get("reservationId") for r in reviews_all
                   if str(r.get("listing_id")) == str(lid)]
        fol = grab("followups", lambda: HOST.review_followups(res_ids) if HOST.review_followups else [], [])
        followed = {str(f.get("reservation_id")) for f in fol}
        r_rows, r_sum, private = ops.reviews(reviews_all, lid, s_d, end_d, followed, red,
                                             float(rules.get("rating_target", 4.75)))
        weeks = ops.price_weeks(price)
        events, counters = ops.timeline(m_rows, p_rows, c_rows, r_rows, rec_rows, weeks, permit, dp, clean, s_d, end_d)
        u["maint"] = {"rows": m_rows, "stats": m_stats}
        u["claims"] = {"rows": c_rows, "ring": ring}
        u["reviews"] = {"rows": r_rows, "summary": r_sum}
        u["log"] = {"events": events, "counters": counters}
        u["permit"] = permit
        u["_private_reviews"] = private


PROMO_WORDS = (("weekly_current", "خصم الأسبوع"), ("monthly_current", "خصم الشهر"), ("early_bird_current", "خصم الحجز المبكر"),
               ("last_minute_current", "خصم اللحظة الأخيرة"))


def _promo_words(row):
    out = []
    for key, word in PROMO_WORDS:
        v = row.get(key)
        out.append("%s %s" % (word, ("%d٪" % round(v * 100)) if v else "غير مفعّل"))
    return out


def _season_next(start, end):
    """Riyadh Season (mid-Oct → mid-Mar) or an Eid inside the coming quarter -> the season uplift."""
    if any(m in (10, 11, 12, 1, 2, 3) for m in (start.month, end.month)):
        return True
    try:
        return any(w.get("kind") in ("eid_fitr", "eid_adha") for w in (HOST.season_windows(start, end) or []))
    except Exception:
        return False


STATUS_AR = {"done": "تم", "in_progress": "قيد التنفيذ", "not_done": "لم يتم"}


def collect_promises(owner, meeting_id, meeting_date, today):
    """Chapter 0: every commitment of the previous presented/sent meeting, with its status and the
    evidence. A linked ticket that is now closed IS the evidence (and marks it done). -> dict | None."""
    prev = db.last_meeting_before(owner, meeting_date, exclude_id=meeting_id)
    if not prev:
        return None
    rec = db.record(prev["id"])
    if not rec["commitments"]:
        return {"meeting_date": prev["meeting_date"], "items": []}
    red = redact.Redactor(staff_names=HOST.staff_names() if HOST.staff_names else [])
    items = []
    for c in rec["commitments"]:
        status, evidence = c["status"], c.get("evidence") or ""
        if c.get("linked_ticket") and status != "done" and HOST.ticket_status:
            try:
                t = HOST.ticket_status(c["linked_ticket"]) or {}
            except Exception:
                t = {}
            if t.get("closed"):
                status = "done"
                day = str(t.get("closed_at") or "")[:10]
                evidence = evidence or ("أُغلقت التذكرة المرتبطة" + ((" بتاريخ " + texts.date_ar(day)) if day else ""))
        if status == "open":
            status = "not_done" if (c.get("due") and str(c["due"])[:10] < today.isoformat()) else "in_progress"
        items.append({"side": c["side"], "text": red(c["text"]), "status": status, "status_ar": STATUS_AR[status],
                      "due": c.get("due"), "evidence": red(evidence)})
    return {"meeting_date": prev["meeting_date"], "items": items}


def collect_plan(owner, units_out, meeting_date, today, rules, readiness, notes, peer_internal):
    """Chapters 6, 11, 12: the Airbnb funnel (latest import at or before the meeting date), the
    action list, and the next-quarter target. A missing report is an honest empty chapter."""
    imp, rows = abnb.latest(meeting_date)
    mp = abnb.mapping(rows) if rows else {"by_lid": {}, "unmapped": []}
    group = rules.get("promo_test_group_a") or {}
    in_a = set(group.get("airbnb_ids") or []) if engine.promo_confirmed(rules) else set()
    fx = float((imp or {}).get("fx_sar_per_usd") or rules.get("fx_sar_per_usd", 3.75))
    cur = periods.mkey(today)
    trailing = [periods.add_months(cur, -i) for i in (3, 2, 1)]
    ly_t = [periods.add_months(m, -12) for m in trailing]
    nxt = [periods.add_months(cur, i) for i in (0, 1, 2)]
    ly_n = [periods.add_months(m, -12) for m in nxt]
    for u in units_out:
        lid = u["lid"]
        aid = mp["by_lid"].get(lid)
        row = rows.get(aid) if aid else None
        if rows and row is None:
            readiness.append(_check("yellow", "abnb_unmapped", "شقة %s غير مربوطة بسطر في تقرير Airbnb — اربطها من «استيراد تقرير Airbnb»" % u["name"], lid=lid))
        f = engine.funnel(row) if row else None
        pf, pin = engine.funnel_peers(list(rows.values()), row, int(rules.get("peer_min", engine.PEER_MIN_DEFAULT))) if row else (None, None)
        peer_internal.setdefault(lid, {})["funnel"] = pin
        u["airbnb"] = None if not row else {
            "data_as_of": (imp or {}).get("data_as_of"), "funnel": f,
            "peer": ({k: pf[k] for k in ("views", "bookings", "ctr100", "conv", "scope")} if pf else None),
            "guest_favorite": bool(row.get("guest_favorite")), "rating": row.get("rating"),
            "bookings_365": row.get("bookings_l365"), "occ_n3m": row.get("occ_n3m"),
            "gbv_sar": (round(row["gbv_usd"] * fx) if row.get("gbv_usd") is not None else None), "fx": fx,
            "promos": _promo_words(row), "new_listing_eligible": row.get("new_listing_eligible")}
        nx = u.get("next14") or {}
        open14 = None if nx.get("share") is None else int(round(14 * (1 - nx["share"])))
        try:
            mp_floor = HOST.min_price(lid) if HOST.min_price else None
        except Exception:
            mp_floor = None
        ctx = {"rating": (u.get("rating") or {}).get("value") if (u.get("rating") or {}).get("value") is not None
               else (row or {}).get("rating"),
               "bookings_365": (row or {}).get("bookings_l365"), "funnel": f, "peer_funnel": pf,
               "income_tone": ((u.get("peers") or {}).get("income") or {}).get("tone"), "open14": open14,
               "maint_open": ((u.get("maint") or {}).get("stats") or {}).get("open_now"),
               "rr_open": [c for c in ((u.get("claims") or {}).get("rows") or []) if not c.get("closed")],
               "permit": u.get("permit"), "min_price": mp_floor, "in_test_group": bool(aid and aid in in_a)}
        acts = engine.actions(ctx, rules, today)
        u["actions"] = [{k: a[k] for k in ("key", "owner_text", "evidence", "due", "role", "side")} for a in acts]
        u["_action_notes"] = [a["internal_note"] for a in acts if a.get("internal_note")]
        u["headline"] = engine.headline(u, degraded=False, rating_target=float(rules.get("rating_target", 4.75)))

        def nets(months):
            out = []
            for m in months:
                try:
                    rep = HOST.unit_month(owner, m, lid)
                except Exception:
                    rep = None
                out.append(None if rep is None else float(money.D(rep.get("owner_net"))))
            return out
        t = nets(trailing)
        fc = engine.forecast(t, nets(ly_t), nets(ly_n), {a["key"] for a in acts}, rules,
                             _season_next(periods.month_bounds(nxt[0])[0], periods.month_bounds(nxt[-1])[1]))
        if fc:
            fc["months"] = nxt
            fc["trailing"] = trailing
        u["forecast"] = fc
        u["_stack"] = engine.discount_stack(row, rules) if row else None
        u["_in_test_group"] = bool(aid and aid in in_a)
    if rows and mp["unmapped"]:
        notes.append({"key": "abnb_unmapped_rows", "text_ar": "%d سطراً في تقرير Airbnb بلا شقة مربوطة" % len(mp["unmapped"])})


def forbidden_terms(owner, all_lids, units_out, rows):
    """What the privacy scan must never find on this owner's pages (R1–R4). Presenter-only."""
    mine = {int(x) for x in all_lids}
    other_units = [m.get("name") for lid, m in (HOST.listings_meta() or {}).items()
                   if int(lid) not in mine and m.get("name")]
    other_owners = [o["owner"] for o in (HOST.owners() or []) if o.get("owner") and o["owner"] != owner] if HOST.owners else []
    guests = {str(r.get("guestName")).strip() for r in rows if r.get("guestName")}
    staff = set(HOST.staff_names() if HOST.staff_names else [])
    for u in units_out:
        guests |= set(u.pop("_guests", []))
        staff |= set(u.pop("_staff", []))
    full = sorted(g for g in guests if len(g.split()) >= 2)
    return {"other_units": sorted(set(other_units)), "other_owners": sorted(set(other_owners)),
            "guest_full_names": full, "staff": sorted(staff),
            "staff_tokens": sorted({t for n in staff for t in redact.tokens(n)})}


def privacy_hits(snap):
    from . import render
    html = render.presentation_html(snap, 0)
    return privacy.scan(html, (snap.get("presenter") or {}).get("forbidden") or {})


def market():
    """The dated market references the company profile already publishes (AirDNA + MoT), each with
    its source and date so the page can print them under the number. Missing file -> {}."""
    out = {}
    try:
        with open(os.path.join(_CP_DATA, "cp_market.json"), encoding="utf-8") as f:
            m = json.load(f)
        out["airdna"] = {"occupancy_pct": m.get("occupancy_pct"), "adr_sar": m.get("adr_sar"),
                         "source": m.get("source"), "as_of": m.get("source_date")}
    except Exception:
        pass
    try:
        with open(os.path.join(_CP_DATA, "cp_benchmarks.json"), encoding="utf-8") as f:
            b = json.load(f)
        for k in ("mot_occupancy", "mot_adr"):
            if isinstance(b.get(k), dict):
                out[k] = {"value": b[k].get("value"), "as_of": b[k].get("as_of"), "source": b[k].get("source")}
    except Exception:
        pass
    return out


def next_nights_share(today, n=NEXT_NIGHTS):
    """{lid: booked share of the next n nights from today} for every unit with any booking, plus
    the raw pull's degraded flag. One targeted window read (never the truncating cache)."""
    end = today + datetime.timedelta(days=n - 1)
    rows, deg = HOST.reservations_window(today, end)
    nights, _a = HOST.explode_nights(rows)
    seen = {}
    for lid, d, _p in nights:
        d = _date(d)
        if today <= d <= end:
            try:
                seen.setdefault(int(lid), set()).add(d)
            except (TypeError, ValueError):
                continue
    return {lid: len(ds) / float(n) for lid, ds in seen.items()}, deg


# ------------------------------------------------------------------ build
def build(params, progress=None, today=None):
    """params: {owner, lids: [int] (empty = all his units), period: periods.resolve(...),
    meeting_date: 'YYYY-MM-DD'} -> snapshot dict. Raises ValueError(arabic) on bad input."""
    rules = config.rules()
    owner = params["owner"]
    period = params["period"]
    months, partial = period["months"], period.get("partial")
    start, end = period["start"], period["end"]
    days = periods.days(_date(start), _date(end))
    say = progress or (lambda pct, step: None)

    say(5, "تجهيز الشقق")
    all_lids = [int(x) for x in (HOST.owner_lids(owner) or [])]
    if not all_lids:
        raise ValueError("ما لقينا شقق مربوطة بهذا المالك")
    scope = [int(x) for x in (params.get("lids") or [])] or list(all_lids)
    stray = [l for l in scope if l not in all_lids]
    if stray:
        raise ValueError("شقة ليست لهذا المالك: %s" % stray)
    whole_owner = set(scope) == set(all_lids)
    info = {lid: (HOST.unit_info(lid) or {"lid": lid}) for lid in scope}
    readiness, notes = [], []

    owner_rows, unit_rows, expenses = collect_money(owner, scope, months, partial, say)
    srows = scope_rows(owner_rows, unit_rows, scope, whole_owner)

    for r in owner_rows:
        if r["missing"]:
            readiness.append(_check("red", "missing_month", "تعذّر حساب كشف شهر %s" % r["m"], month=r["m"]))
        elif r["degraded"]:
            readiness.append(_check("red", "degraded", "سحب الحجوزات لشهر %s جزئي — الأرقام قد تكون ناقصة" % r["m"],
                                    month=r["m"]))
    stale = [r["m"] for r in owner_rows if r.get("stale")]
    if stale:
        readiness.append(_check("yellow", "stale", "أشهر من نسخة محفوظة وتتحدّث الآن (%s) — أعد التجهيز بعد دقائق للأحدث"
                                % "، ".join(stale), months=stale))
    if whole_owner and len(scope) > 1:
        for i, r in enumerate(owner_rows):
            usum = sum((unit_rows[l][i]["owner_net"] for l in scope), Decimal(0))
            if abs(usum - r["owner_net"]) > money.HALALA and not r["missing"]:
                notes.append({"key": "owner_level_lines", "month": r["m"], "amount": _f(r["owner_net"] - usum),
                              "text_ar": "بنود على مستوى المالك لا تتبع شقة في %s: %s ريال"
                                         % (r["m"], money.D(r["owner_net"] - usum))})

    say(52, "شروط العقد")
    units_out = []
    end_d = _date(end)
    for lid in scope:
        terms = HOST.terms_on(lid, end_d) or {}
        pct = terms.get("mgmt_pct")
        if pct in (None, "", 0):
            readiness.append(_check("red", "mgmt_pct", "نسبة الإدارة غير محددة لـ %s" % (info[lid].get("name") or lid),
                                    lid=lid))
        units_out.append({"lid": lid, "name": info[lid].get("name") or str(lid),
                          "bedrooms": info[lid].get("bedrooms"),
                          "mgmt_pct": pct, "cleaning_type": (terms.get("cleaning") or {}).get("type"),
                          "money": _money_block(unit_rows[lid]), "_expenses": expenses.get(lid) or []})

    say(58, "الحجوزات والليالي")
    rows, rdeg = HOST.reservations_window(_date(start), end_d)
    if rdeg:
        readiness.append(_check("red", "res_degraded", "سحب الحجوزات للفترة جزئي — أعد التجهيز لاحقاً"))
    nights, arrivals = HOST.explode_nights(rows)
    stats = night_stats(nights, start, end, months)

    say(70, "المقارنة بالشقق المشابهة")
    meta_all = HOST.listings_meta() or {}
    active = [lid for lid, st in stats.items() if all(m in st["months"] for m in months)]
    ratings = engine.rating_stats(HOST.reviews_all() or [])
    nets = {}
    try:
        nets = HOST.cached_unit_nets(months) or {}
    except Exception as e:                                       # a cache read never fails the build
        notes.append({"key": "nets_cache", "text_ar": "تعذّر قراءة صافي الشقق الأخرى من الذاكرة: %s" % e})
    vals = peer_metrics(stats, days, ratings, nets, months)
    peer_min = int(rules.get("peer_min", engine.PEER_MIN_DEFAULT))
    top_at = int(rules.get("percentile_top_at", 60))
    low_at = int(rules.get("percentile_low_at", 30))
    peer_internal = {}
    for u in units_out:
        lid = u["lid"]
        unit_net = sum((r["owner_net"] for r in unit_rows[lid]), Decimal(0))
        vals["net_per_night"][lid] = float(unit_net) / days if days else None      # his own, exact
        st = stats.get(lid) or {"nights": 0, "income": 0.0, "by_month": {}}
        for k in ("income", "occupancy", "adr", "revpar"):
            vals[k].setdefault(lid, None)
        if st["nights"] == 0:
            vals["income"][lid], vals["occupancy"][lid], vals["revpar"][lid] = 0.0, 0.0, 0.0
        br = u["bedrooms"] if u["bedrooms"] is not None else (meta_all.get(lid) or {}).get("bedrooms")
        peers = [l for l in active if (meta_all.get(l) or {}).get("bedrooms") == br and br is not None]
        bands, internal = {}, {}
        for k in METRICS:
            band, inn = engine.peer_bands(vals[k], lid, peers, active, peer_min, top_at, low_at)
            internal[k] = inn
            if band is not None:
                bands[k] = _round_band(band, k)
        rv = bands.get("revpar")
        u["fair_share"] = engine.fair_share_index(rv["value"], rv["p50"]) if rv else None
        u["peers"] = {k: v for k, v in bands.items() if k != "revpar"}
        n, R = ratings.get(lid, (0, 0))
        u["rating"] = {"value": _r(engine.rating5(n, R), 2), "reviews": n}
        u["nights"] = st["nights"]
        u["stats"] = {"income": _r(vals["income"].get(lid), 2), "occupancy": _r(vals["occupancy"].get(lid), 4),
                      "adr": _r(vals["adr"].get(lid), 2), "nights": st["nights"], "days": days}
        u["trend"] = [{"m": r["m"], "net": _f(r["owner_net"]), "partial": r["partial"],
                       "occupancy": _r(st["by_month"].get(r["m"], 0) /
                                       float(periods.window_days_in_month(r["m"], start, end) or 1), 4)}
                      for r in unit_rows[lid]]
        peer_internal[lid] = internal
        s_d, e_d = _date(start), end_d
        u["bookings"] = sum(1 for al, ad in arrivals
                            if str(al) == str(lid) and s_d <= _date(ad) <= e_d)

    say(80, "الأسبوعان القادمان")
    today = (HOST.now().date() if HOST.now else datetime.date.today())
    nxt, ndeg = next_nights_share(today)
    if ndeg:
        readiness.append(_check("yellow", "next_degraded", "سحب حجوزات الأسبوعين القادمين جزئي"))
    nxt_vals = {lid: nxt.get(lid, 0.0) for lid in active}
    for u in units_out:
        lid = u["lid"]
        nxt_vals[lid] = nxt.get(lid, 0.0)
        br = u["bedrooms"]
        peers = [l for l in active if (meta_all.get(l) or {}).get("bedrooms") == br and br is not None]
        band, inn = engine.peer_bands(nxt_vals, lid, peers, active, peer_min, top_at, low_at)
        u["next14"] = {"share": _r(nxt_vals[lid], 4), "from": today.isoformat(),
                       "band": _round_band(band, "occupancy") if band else None}
        peer_internal[lid]["next14"] = inn
        u["headline"] = engine.headline(u, degraded=False,
                                        rating_target=float(rules.get("rating_target", 4.75)))

    say(84, "سجل الشقة والصيانة والتعويضات والتقييمات")
    collect_ops(owner, units_out, all_lids, rows, start, end_d, today, rules, notes)

    for u in units_out:                       # statement expense lines, redacted like every free text
        red = redact.Redactor(staff_names=HOST.staff_names() if HOST.staff_names else [])
        u["expenses"] = [dict(x, description=red(x["description"])) for x in sorted(u.pop("_expenses", []),
                                                                                    key=lambda x: x["date"])]
    promises = collect_promises(owner, params.get("meeting_id"), params["meeting_date"], today)

    say(86, "تقرير Airbnb والخطة والهدف")
    collect_plan(owner, units_out, params["meeting_date"], today, rules, readiness, notes, peer_internal)

    say(88, "تجميع العرض")
    scope_money = _money_block(srows)
    if not scope_money["waterfall"]["reconciled"]:
        readiness.append(_check("yellow", "waterfall", "توزيع «أين ذهب كل ريال» لا يطابق صافي الكشف — سنعرض الإجماليات فقط"))
    if HOST.owner_portal_token is not None and not HOST.owner_portal_token(owner):
        readiness.append(_check("yellow", "portal_token", "رابط بوابة المالك غير مفعّل — الإيصالات لن تظهر"))
    seasons = HOST.season_windows(_date(start), end_d) if HOST.season_windows else []
    notes_ann = [a for a in db.annotations() if a["end_date"] >= start and a["start_date"] <= end]
    stamps = [r.get("computed_at") for r in owner_rows if r.get("computed_at")]
    degraded = any(c["key"] in ("degraded", "res_degraded") for c in readiness)
    if degraded:                                                  # a headline over half the data would lie
        for u in units_out:
            u["headline"] = None
    now = HOST.now() if HOST.now else datetime.datetime.utcnow()
    forbidden = forbidden_terms(owner, all_lids, units_out, rows)
    snap = {
        "meta": {"schema_version": db.SCHEMA_VERSION, "period": period, "meeting_date": params["meeting_date"],
                 "built_at": now.isoformat(timespec="seconds"),
                 "data_as_of": (min(stamps) if stamps else None), "degraded": degraded,
                 "whole_owner": whole_owner},
        "owner": {
            "owner_name": owner,
            "period": {"start": start, "end": end, "months": months, "partial": partial, "kind": period.get("kind")},
            "scope": {"lids": scope, "money": scope_money,
                      "trend": [{"m": r["m"], "net": _f(r["owner_net"]), "partial": r["partial"]} for r in srows]},
            "units": units_out,
            "promises": promises,
            "seasons": seasons,
            "market": market(),
            "annotations": [{"start": a["start_date"], "end": a["end_date"], "text_ar": a["text_ar"]}
                            for a in notes_ann],
        },
        "presenter": {"readiness": readiness, "notes": notes, "peer_internal": peer_internal,
                      "private_reviews": {u["lid"]: u.pop("_private_reviews", []) for u in units_out},
                      "plan": {u["lid"]: {"notes": u.pop("_action_notes", []), "stack": u.pop("_stack", None),
                                          "in_test_group": u.pop("_in_test_group", False)} for u in units_out},
                      "levers": rules.get("levers"),
                      "forbidden": forbidden},
    }
    say(94, "فحص الخصوصية")
    hits = privacy_hits(snap)
    if hits:
        readiness.append(privacy.readiness_line(hits))
        snap["meta"]["privacy_hits"] = [h["kind"] for h in hits]
    return snap
