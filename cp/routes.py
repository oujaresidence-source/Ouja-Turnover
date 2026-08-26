# -*- coding: utf-8 -*-
"""
cp.routes — aiohttp handlers for /cp.

The page itself is public and indexable: it is a profile, and gating it would
defeat the point. The lead endpoint is public too, and therefore rate-limited
and strictly field-limited.

Nothing here calls Hostaway. The page renders from a snapshot; a request never
waits on the PMS. Handlers that must touch the disk do so through HOST.load_json,
which is the bot's own cached store.
"""
import json
import os
import time
import traceback

from . import admin_store, page, page_v2, stats
from .host import HOST

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Words that identify who is writing, so the lead lands in front of the right
# person. Seeds §12: owners come through WhatsApp, capital partners and
# government reviewers do not — one button for all five would lose that.
AUDIENCES = ("owner", "investor", "corporate", "platform", "supplier")

_MAX_FIELD = 2000
_RATE_WINDOW_SEC = 3600
_RATE_MAX = 8
_recent = {}   # ip -> [timestamps]


def _read_json(name, default):
    try:
        with open(os.path.join(_DATA, name), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return data


def _links():
    return HOST.links or {}


def _reviews():
    return _read_json("cp_reviews.json", [])


def _units():
    """Six residences, each resolved through the existing /stay photo pipeline.

    HOST.listing_photos is injected by bot.py and is the ONLY way an image gets
    onto this page — there is deliberately no second image system (superprompt §6).
    """
    units = _read_json("cp_units.json", [])
    resolved = []
    for u in units:
        u = dict(u)
        lid = str(u.get("listing_id") or "").strip()
        # "photo" may pin one gallery image by URL — used when the listing's
        # cover fails the photo rules (e.g. a TV screen showing third-party
        # content) and a clean shot from the same gallery replaces it.
        pinned = str(u.get("photo") or "").strip()
        pinned = pinned if pinned.lower().startswith("http") else ""
        if lid and HOST.listing_photos:
            try:
                shot = HOST.listing_photos(lid, pinned or None) or {}
                u["photo"] = shot.get("photo") or ""
                u["photo_srcset"] = shot.get("srcset") or ""
            except Exception:
                traceback.print_exc()
                u["photo"] = u["photo_srcset"] = ""
        resolved.append(u)
    return resolved


def _snapshot():
    try:
        if HOST.load_json:
            return HOST.load_json("cp_stats.json", None)
    except Exception:
        traceback.print_exc()
    return None


def _safe_public(fn):
    """Public wrapper: a prospect must never see a stack trace, and a broken
    figure must never take the page down — the fallbacks exist for that."""
    async def _w(request):
        try:
            return await fn(request)
        except Exception as e:
            if isinstance(e, HOST.web.HTTPException):
                raise
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": type(e).__name__}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


# --------------------------------------------------------------------------- #
# pages
# --------------------------------------------------------------------------- #
def _base():
    """HOST.base_url may be a static string or a callable — bot.py wires the
    callable so the share-card URL works with zero env setup: it resolves
    PUBLIC_BASE_URL, else the host auto-captured from real traffic."""
    b = HOST.base_url
    try:
        b = b() if callable(b) else b
    except Exception:
        b = ""
    return (b or "").rstrip("/")


def _render_ar():
    return page.render_ar(
        snapshot=_snapshot(),
        base=_base(),
        links=_links(),
        reviews=_reviews(),
        units=_units(),
        ask=_read_json("cp_ask.json", {}),
        english=bool(HOST.english_ready),
        pdf=bool(_pdf_path()),
    )


async def handle_root(request):
    lang = (HOST.default_lang or "ar").lower()
    raise HOST.web.HTTPFound("/cp/" + ("en" if lang == "en" and HOST.english_ready else "ar"))


def _admin_store():
    return admin_store.Store(load_json=HOST.load_json, save_json=HOST.save_json)


def _v2_requested(request):
    """v2 serves when: the dashboard PUBLISHED it; or a logged-in preview asks
    with ?v=2; or CP_V2=1 forces it (the escape hatch). Anything else is v1."""
    if os.environ.get("CP_V2") == "1":
        return True, "env"
    if request is not None and request.query.get("v") == "2":
        try:
            if HOST.dash_auth and HOST.dash_auth(request):
                return True, "preview"
        except Exception:
            pass
    try:
        if _admin_store().overlay().get("published_version") == "v2":
            return True, "published"
    except Exception:
        traceback.print_exc()
    return False, "v1"


def _resolve_photos(units):
    photos = {}
    for u in units or []:
        lid = str(u.get("listing_id") or "")
        if not lid or not HOST.listing_photos:
            continue
        try:
            pinned = u.get("cover_url") or None
            photos[lid] = HOST.listing_photos(lid, pinned) or {}
        except Exception:
            traceback.print_exc()
    return photos


def _mark_inactive(units):
    """An inactive Hostaway listing is skipped on the public render (§4)."""
    try:
        cache = HOST.listings_cache() if HOST.listings_cache else {}
        active = {str(l.get("id")): bool(l.get("active"))
                  for l in (cache.get("listings") or [])}
    except Exception:
        active = {}
    out = []
    for u in units or []:
        u = dict(u)
        lid = str(u.get("listing_id") or "")
        if lid in active and not active[lid]:
            u["inactive"] = True
        out.append(u)
    return out


def _resolve_reviews(sections):
    ids = ((sections.get("reviews") or {}).get("ids")) or []
    if not ids or not HOST.reviews_store:
        return None
    try:
        rows = {r.get("id"): r for r in HOST.reviews_store()}
    except Exception:
        return None
    out = []
    for rid in ids:
        r = rows.get(rid)
        if not r:
            continue
        out.append({"name": r.get("name", ""), "date": r.get("date", ""),
                    "label": r.get("listing", ""), "lang": r.get("lang", "ar"),
                    "text": r.get("text", ""),
                    "critical": "العزل" in (r.get("text") or "")})
    return out or None


def _render_v2(request, more_key=None):
    store = _admin_store()
    is_v2, why = _v2_requested(request)
    sections = (store.overlay() if why in ("preview", "env")
                else store.published_overlay())
    units = _mark_inactive((sections.get("showcase") or {}).get("units"))
    if units:
        sections = dict(sections)
        sections["showcase"] = {"units": units}
    return page_v2.render_v2(
        sections=sections,
        snapshot=_snapshot(),
        base=_base(),
        photos=_resolve_photos(units),
        reviews=_resolve_reviews(sections),
        more_key=more_key,
    )


async def handle_ar(request):
    is_v2, _why = _v2_requested(request)
    if is_v2:
        return HOST.web.Response(text=_render_v2(request),
                                 content_type="text/html", charset="utf-8")
    return HOST.web.Response(text=_render_ar(), content_type="text/html", charset="utf-8")


async def handle_more(request):
    key = request.match_info.get("key", "")
    if key not in page_v2.DRAWER_KEYS:
        raise HOST.web.HTTPNotFound()
    return HOST.web.Response(text=_render_v2(request, more_key=key),
                             content_type="text/html", charset="utf-8")


async def handle_en(request):
    """The English edition is not built yet (owner decision, 2026-08-26: Arabic
    first). Until it is, this is a TEMPORARY redirect — a 302, so no cache or
    search engine records it as the permanent home of the English page."""
    if HOST.english_ready:
        return HOST.web.Response(text=page.render_en(), content_type="text/html",
                                 charset="utf-8")
    raise HOST.web.HTTPFound("/cp/ar")


def _pdf_path():
    p = (HOST.pdf_path or "").strip()
    if not p:
        return ""
    if not os.path.isabs(p):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), p)
    return p if os.path.exists(p) else ""


async def handle_pdf(request):
    path = _pdf_path()
    if not path:
        raise HOST.web.HTTPNotFound(text="The PDF profile is not published yet.")
    return HOST.web.FileResponse(path, headers={
        "Content-Disposition": 'inline; filename="Ouja-Residence-Company-Profile.pdf"'})


_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_ASSET_NAMES = ("icon.png", "icon-192.png", "icon-512.png", "share.png")


async def handle_asset(request):
    """Brand assets (favicon, share card) — generated from the owner's logo,
    immutable-cached; the filename changes if the logo ever does."""
    name = request.match_info.get("name", "")
    if name not in _ASSET_NAMES:
        raise HOST.web.HTTPNotFound()
    return HOST.web.FileResponse(
        os.path.join(_ASSETS, name),
        headers={"Cache-Control": "public, max-age=604800"})


async def handle_business_redirect(request):
    raise HOST.web.HTTPMovedPermanently("/cp")


# --------------------------------------------------------------------------- #
# json
# --------------------------------------------------------------------------- #
async def api_stats(request):
    cells = stats.load(snapshot=_snapshot())
    return HOST.json_response({
        "ok": True,
        "stamp": stats.sync_stamp(snapshot=_snapshot()),
        "market": stats.MARKET,
        "figures": cells,
    })


async def api_reviews(request):
    """Only what is published on the page: verbatim text, first name plus last
    initial, month and year. No reservation id, no listing id, no full date."""
    out = []
    for r in _reviews():
        if not (r.get("text_original") or "").strip():
            continue
        out.append({k: r.get(k) for k in
                    ("slot", "guest_name", "listing_name", "date", "rating",
                     "language", "text_original", "translation_ar", "translation_en",
                     "our_response")})
    return HOST.json_response({"ok": True, "reviews": out, "count": len(out)})


# --------------------------------------------------------------------------- #
# leads
# --------------------------------------------------------------------------- #
def _client_ip(request):
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    peer = request.transport.get_extra_info("peername") if request.transport else None
    return (peer[0] if peer else "") or "unknown"


def _rate_limited(ip, now=None):
    now = now or time.time()
    hits = [t for t in _recent.get(ip, []) if now - t < _RATE_WINDOW_SEC]
    _recent[ip] = hits
    if len(hits) >= _RATE_MAX:
        return True
    hits.append(now)
    return False


async def _body(request):
    try:
        return await request.json()
    except Exception:
        try:
            return dict(await request.post())
        except Exception:
            return {}


MODES = ("online", "office")
SLOTS = ("am", "pm", "eve")

_AR_INDIC = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_AR_INDIC.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})

_MODE_AR = {"online": "عن بُعد · اتصال مرئي", "office": "في مكتبنا · الرياض"}
_SLOT_AR = {"am": "صباحاً", "pm": "بعد الظهر", "eve": "مساءً"}
_AUD_AR = {"owner": "تملك عقاراً", "investor": "تدرس الاستثمار",
           "corporate": "تسكن موظفيك", "platform": "منصة حجز",
           "supplier": "مورّد"}


def normalize_phone(raw):
    """What a Saudi guest actually types — ٠٥٥…, ۰۵۵…, +966, or bare — into a
    single storable shape: digits, 966-prefixed. Too short/long returns ''."""
    digits = "".join(ch for ch in str(raw or "").translate(_AR_INDIC)
                     if ch.isdigit())
    if not 9 <= len(digits) <= 15:
        return ""
    if digits.startswith("00966"):
        digits = digits[2:]
    if digits.startswith("05") and len(digits) == 10:
        digits = "966" + digits[1:]
    elif digits.startswith("0") and len(digits) >= 9:
        digits = "966" + digits.lstrip("0")
    elif len(digits) == 9:
        digits = "966" + digits
    return digits if 11 <= len(digits) <= 15 else ""


def clean_lead(raw):
    """Field-limited on purpose: this endpoint is public, so it accepts exactly
    what the reservation card offers and nothing a caller invents."""
    out = {}
    for key in ("name", "company", "message"):
        value = str(raw.get(key) or "").strip()
        if value:
            out[key] = value[:_MAX_FIELD]
    phone = normalize_phone(raw.get("phone"))
    if phone:
        out["phone"] = phone
    audience = str(raw.get("audience") or "").strip().lower()
    out["audience"] = audience if audience in AUDIENCES else "owner"
    mode = str(raw.get("mode") or "").strip().lower()
    out["mode"] = mode if mode in MODES else "online"
    slot = str(raw.get("slot") or "").strip().lower()
    out["slot"] = slot if slot in SLOTS else "am"
    return out


def lead_embed_text(record):
    """The Discord line the team reads — mode, slot and audience in Arabic."""
    f = record.get("fields") or {}
    lines = ["**طلب لقاء — %s**" % _AUD_AR.get(record.get("audience") or
                                               f.get("audience"), "؟"),
             "الطريقة: %s" % _MODE_AR.get(f.get("mode"), f.get("mode") or "—"),
             "الوقت: %s" % _SLOT_AR.get(f.get("slot"), f.get("slot") or "—")]
    for key, label in (("name", "الاسم"), ("phone", "الجوال"),
                       ("company", "الجهة"), ("message", "الرسالة")):
        if f.get(key):
            lines.append("%s: %s" % (label, f[key]))
    lines.append("_%s · %s_" % (record.get("lang", "ar"),
                                record.get("referrer") or "no referrer"))
    return chr(10).join(lines)


async def api_lead(request):
    ip = _client_ip(request)
    if _rate_limited(ip):
        return HOST.json_response({"ok": False, "error": "rate_limited"}, 429)

    raw = await _body(request)
    # honeypot: humans never see company_url; a filled one gets a quiet
    # pretend-success so the bot learns nothing, and nothing is stored.
    if str(raw.get("company_url") or "").strip():
        return HOST.json_response({"ok": True, "notified": False})
    data = clean_lead(raw)
    if not data.get("phone") and not data.get("name"):
        return HOST.json_response({"ok": False, "error": "contact_required"}, 400)

    record = {
        "at": int(time.time()),
        "status": "new",
        "audience": data["audience"],
        "fields": data,
        "lang": (request.match_info.get("lang") or "ar"),
        "referrer": request.headers.get("Referer", "")[:400],
        "ip": ip,
    }

    # Durable first, notify second: a lead that reaches the disk is never lost
    # even if Discord is down, which is the failure this ordering exists for.
    try:
        if HOST.save_json and HOST.load_json:
            store = HOST.load_json("cp_leads.json", {"leads": []}) or {"leads": []}
            store.setdefault("leads", []).append(record)
            store["leads"] = store["leads"][-500:]
            HOST.save_json("cp_leads.json", store)
    except Exception:
        traceback.print_exc()

    notified = False
    try:
        if HOST.notify:
            HOST.notify(record)
            notified = True
    except Exception:
        traceback.print_exc()

    return HOST.json_response({"ok": True, "notified": notified})


def register(app):
    from . import admin as _admin
    _admin.register(app)
    g, p = app.router.add_get, app.router.add_post
    g("/cp", _safe_public(handle_root))
    g("/cp/ar", _safe_public(handle_ar))
    g("/cp/ar/more/{key}", _safe_public(handle_more))
    g("/cp/en", _safe_public(handle_en))
    g("/cp.pdf", _safe_public(handle_pdf))
    g("/cp/{name:(?:icon|icon-192|icon-512|share)[.]png}", _safe_public(handle_asset))
    g("/api/cp/stats", _safe_public(api_stats))
    g("/api/cp/reviews", _safe_public(api_reviews))
    p("/api/cp/lead", _safe_public(api_lead))
    # Held behind a flag until the English edition exists: /business currently
    # serves English by default, and redirecting it to an Arabic-only page would
    # be a regression for exactly the readers most likely to hold the old link.
    if HOST.redirect_business:
        g("/business", _safe_public(handle_business_redirect))
        g("/business/ar", _safe_public(handle_business_redirect))
