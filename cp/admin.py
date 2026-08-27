# -*- coding: utf-8 -*-
"""
cp.admin — the HTTP surface behind the «الملف التعريفي» dashboard tab.

Auth model, layered so no single mistake is fatal:
  * bot.py's role middleware maps /api/cp/admin/ → the `cp` tab (read on GET,
    write on POST, `create` checked here for publish/rollback);
  * every handler ALSO starts with HOST.dash_auth — belt and braces, and it
    keeps this package testable without the middleware;
  * nothing here is in _ROLE_EXEMPT_WRITES. Only the public lead endpoint is.

The write discipline is the point of the whole tab: validate → render the page
the save would produce → cp.guard.scan it → only then save. A copy string that
carries a withheld figure gets a 400 that NAMES the numbers, and the overlay is
untouched. The guard verdict rides back on every write response so the UI can
show green/red without a second round trip.
"""
import csv
import io
import json
import os
import time
import traceback
import uuid

from . import admin_store, guard, page, stats
from .host import HOST

LEAD_STATUSES = ("new", "contacted", "booked", "closed")


def _store():
    return admin_store.Store(load_json=HOST.load_json, save_json=HOST.save_json)


def _user(request):
    try:
        info = HOST.dash_perms(request) if HOST.dash_perms else {}
    except Exception:
        info = {}
    return (info or {}).get("user") or ""


def _perm(request, kind):
    """The cp-tab permission for this session. When bot.py's middleware already
    enforced it this is redundant — by design."""
    try:
        info = HOST.dash_perms(request) if HOST.dash_perms else {}
    except Exception:
        info = {}
    return bool(((info or {}).get("cp") or {}).get(kind))


def _authed(request):
    try:
        return bool(HOST.dash_auth and HOST.dash_auth(request))
    except Exception:
        return False


def _guarded(fn):
    async def _w(request):
        if not _authed(request):
            return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
        if request.method == "POST" and not _perm(request, "write"):
            return HOST.json_response({"ok": False, "error": "forbidden"}, 403)
        try:
            return await fn(request)
        except admin_store.ValidationError as e:
            return HOST.json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            if isinstance(e, HOST.web.HTTPException):
                raise
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": type(e).__name__}, 500)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# preview render + guard verdict
# --------------------------------------------------------------------------- #
def render_preview(store=None):
    """Render the page as the WORKING overlay would publish it. Until the v2
    template lands this renders the v1 path with the overlay's inputs — the
    guard contract is identical either way."""
    store = store or _store()
    ov = store.overlay()
    contacts = ov.get("contacts") or {}
    return page.render_ar(
        snapshot=HOST.load_json("cp_stats.json", None) if HOST.load_json else None,
        base=HOST.base_url() if callable(HOST.base_url) else (HOST.base_url or ""),
        links={"email": contacts.get("email", ""), "wa": contacts.get("whatsapp", "")},
        reviews=_chosen_reviews(store),
        units=None,   # showcase units resolve through routes on the public path
        ask=None,
        check=False,  # the caller inspects the verdict instead of catching
    )


def guard_verdict(markup):
    hits = guard.scan(markup)
    return {"clean": not hits, "hits": hits[:20]}


def _chosen_reviews(store):
    ids = ((store.overlay().get("reviews") or {}).get("ids")) or []
    if not ids:
        return None
    rows = {r.get("id"): r for r in (HOST.reviews_store() if HOST.reviews_store else [])}
    out = []
    for rid in ids:
        r = rows.get(rid)
        if not r:
            continue
        out.append({"slot": len(out) + 1, "guest_name": r.get("name", ""),
                    "listing_name": r.get("listing", ""), "date": r.get("date", ""),
                    "language": r.get("lang", "ar"),
                    "text_original": r.get("text", "")})
    return out


def _check_then(store, section, patch, by):
    """The write discipline: apply on a THROWAWAY copy, render, guard, and only
    persist when clean."""
    probe = admin_store.Store(load_json=lambda n, d=None: json.loads(
        json.dumps(store.overlay())) if n == admin_store.STORE_NAME else d,
        save_json=lambda n, o: True)
    # validate + apply into the probe (raises ValidationError on bad input)
    probe_section = admin_store._VALIDATORS[section](
        probe.overlay().get(section) or ({} if section != "shots" else []), patch)
    probe_ov = probe.overlay()
    probe_ov[section] = probe_section

    # Two scans, deliberately: the render catches figures the template would
    # show, and the raw section catches figures parked in overlay strings the
    # CURRENT template happens not to render — which would otherwise sit as a
    # landmine for the day a template change starts rendering them.
    rendered = render_preview(store=_ProbeStore(probe_ov))
    raw = "<p>" + json.dumps(probe_section, ensure_ascii=False) + "</p>"
    hits = guard.scan(rendered) + guard.scan(raw)
    seen, uniq = set(), []
    for h in hits:
        k = (h["figure"], h["why"])
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    verdict = {"clean": not uniq, "hits": uniq[:20]}
    if not verdict["clean"]:
        raise admin_store.ValidationError(
            "الحفظ مرفوض — أرقام لا يجوز نشرها: "
            + "، ".join(h["figure"] for h in verdict["hits"][:6]))
    saved = store.update_section(section, patch, by=by)
    return saved, verdict


class _ProbeStore:
    """A read-only store view over an in-memory overlay, for pre-save renders."""
    def __init__(self, ov):
        self._ov = ov

    def overlay(self):
        return self._ov


# --------------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------------- #
async def api_overview(request):
    store = _store()
    ov = store.overlay()
    verdict = guard_verdict(render_preview(store=store))
    leads = (HOST.load_json("cp_leads.json", {"leads": []}) or {}).get("leads", [])
    now = time.time()
    snap = HOST.load_json("cp_stats.json", None) if HOST.load_json else None
    stamp = stats.sync_stamp(snapshot=snap)
    return HOST.json_response({
        "ok": True,
        "published_version": ov.get("published_version", "v1"),
        "updated_at": ov.get("updated_at"), "updated_by": ov.get("updated_by"),
        "guard": verdict,
        "stamp": stamp,
        "leads_7d": sum(1 for l in leads if now - l.get("at", 0) < 7 * 86400),
        "leads_30d": sum(1 for l in leads if now - l.get("at", 0) < 30 * 86400),
        "preview_url": "/cp/ar?v=2",
        "can_publish": _perm(request, "create"),
        "dirty": store.is_dirty(),
        "dirty_sections": store.dirty_sections(),
    })


async def api_contacts_get(request):
    return HOST.json_response({"ok": True,
                               "contacts": _store().overlay().get("contacts")})


async def api_copy_get(request):
    defaults = page.COPY_AR
    return HOST.json_response({"ok": True, "defaults": defaults,
                               "overlay": _store().overlay().get("copy") or {}})


async def api_figures_get(request):
    store = _store()
    snap = HOST.load_json("cp_stats.json", None) if HOST.load_json else None
    return HOST.json_response({
        "ok": True,
        "manual": store.merged_manual(stats.MANUAL),
        "manual_overlay": store.overlay().get("figures_manual") or {},
        "benchmarks": store.overlay().get("benchmarks") or {},
        "hostaway": {k: v for k, v in stats.load(snapshot=snap).items()
                     if v["source"] == "hostaway"},
        "stats_url": "/api/cp/stats",
    })


async def api_showcase_get(request):
    store = _store()
    cache = HOST.listings_cache() if HOST.listings_cache else {"listings": [], "synced_at": None}
    return HOST.json_response({
        "ok": True,
        "cache": cache.get("listings") or [],
        "synced_at": cache.get("synced_at"),
        "showcase": store.overlay().get("showcase"),
    })


async def api_reviews_get(request):
    store = _store()
    rows = HOST.reviews_store() if HOST.reviews_store else []
    return HOST.json_response({
        "ok": True,
        "store": [{"id": r.get("id"), "name": r.get("name"), "date": r.get("date"),
                   "listing": r.get("listing"), "lang": r.get("lang"),
                   "text": r.get("text")} for r in rows],
        "chosen": ((store.overlay().get("reviews") or {}).get("ids")) or [],
    })


async def api_leads_get(request):
    leads = (HOST.load_json("cp_leads.json", {"leads": []}) or {}).get("leads", [])
    return HOST.json_response({"ok": True, "leads": leads[-500:]})


async def api_leads_csv(request):
    leads = (HOST.load_json("cp_leads.json", {"leads": []}) or {}).get("leads", [])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["at", "name", "phone", "audience", "mode", "slot", "status", "message"])
    for l in leads:
        f = l.get("fields") or {}
        w.writerow([l.get("at"), f.get("name", ""), f.get("phone", ""),
                    l.get("audience", ""), f.get("mode", ""), f.get("slot", ""),
                    l.get("status", "new"), f.get("message", "")])
    return HOST.web.Response(text=buf.getvalue(), content_type="text/csv",
                             charset="utf-8", headers={
                                 "Content-Disposition":
                                 'attachment; filename="cp-leads.csv"'})


async def api_shots_get(request):
    """What is already uploaded. The upload endpoint existed without this, so
    the tab could add screenshots but never show, rename or remove them."""
    return HOST.json_response({"ok": True,
                               "shots": _store().overlay().get("shots") or [],
                               "max": admin_store.SHOTS_MAX})


async def api_shot_delete(request):
    """Drop one screenshot from the page AND from disk — an orphaned upload
    stays publicly fetchable at its /cp/shot/<id> url otherwise."""
    b = await _body(request)
    sid = str(b.get("id") or "")
    store = _store()
    shots = store.overlay().get("shots") or []
    kept = [sh for sh in shots if sh.get("id") != sid]
    if len(kept) == len(shots):
        return HOST.json_response({"ok": False, "error": "shot_not_found"}, 404)
    store.update_section("shots", kept, by=_user(request))
    try:
        path = os.path.join(HOST.upload_dir or "", sid)
        if HOST.upload_dir and os.path.exists(path):
            os.remove(path)
    except Exception:
        traceback.print_exc()
    return HOST.json_response({"ok": True, "shots": kept})


async def api_history_get(request):
    hist = _store().overlay().get("history") or []
    return HOST.json_response({"ok": True, "history": [
        {"at": h["at"], "by": h["by"], "version": h["version"]} for h in hist]})


# --------------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------------- #
def _section_writer(section):
    async def _handler(request):
        patch = await _body(request)
        store = _store()
        saved, verdict = _check_then(store, section, patch, _user(request))
        return HOST.json_response({"ok": True, "saved": saved, "guard": verdict,
                                   "dirty": store.is_dirty()})
    _handler.__name__ = "api_%s_post" % section
    return _handler


async def api_publish(request):
    if not _perm(request, "create"):
        return HOST.json_response({"ok": False, "error": "publish_requires_create"}, 403)
    b = await _body(request)
    version = str(b.get("version") or "v2")
    store = _store()
    verdict = guard_verdict(render_preview(store=store))
    if not verdict["clean"]:
        return HOST.json_response({"ok": False, "error": "guard_red",
                                   "guard": verdict}, 400)
    entry = store.publish(version, by=_user(request))
    return HOST.json_response({"ok": True, "published": entry["at"],
                               "version": version, "guard": verdict})


async def api_rollback(request):
    if not _perm(request, "create"):
        return HOST.json_response({"ok": False, "error": "rollback_requires_create"}, 403)
    b = await _body(request)
    entry = _store().rollback(str(b.get("at") or ""), by=_user(request))
    return HOST.json_response({"ok": True, "restored": entry["at"],
                               "version": entry["version"]})


async def api_sync_listings(request):
    rep = HOST.sync_listings() if HOST.sync_listings else {"ok": False,
                                                           "error": "not_wired"}
    return HOST.json_response({"ok": bool((rep or {}).get("ok", True)), "report": rep})


async def api_snapshot_now(request):
    rep = HOST.run_snapshot() if HOST.run_snapshot else {"ok": False,
                                                         "error": "not_wired"}
    return HOST.json_response({"ok": bool((rep or {}).get("ok")), "report": rep})


# --------------------------------------------------------------------------- #
# platform screenshots — sniffed, capped, OCR'd, guarded (plan §2.5)
# --------------------------------------------------------------------------- #
_SHOT_TYPES = (
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG", "png", "image/png"),
)


def _sniff(data):
    for magic, ext, ct in _SHOT_TYPES:
        if data[:len(magic)] == magic:
            return ext, ct
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None, None


def _tesseract_available():
    try:
        import pytesseract  # noqa: F401
        import shutil as _sh
        return bool(_sh.which("tesseract"))
    except ImportError:
        return False


def ocr_text(data):
    """(text, engine). A missing engine SKIPS with a logged warning — an owner's
    upload must never fail because CI lacks a binary (§7). Tests monkeypatch
    this to exercise both paths without tesseract."""
    if not _tesseract_available():
        print("[cp] tesseract absent — screenshot uploaded WITHOUT the OCR guard")
        return None, "skipped"
    try:
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(io.BytesIO(data)),
                                           lang="ara+eng")
        return text, "tesseract"
    except Exception as e:
        print("[cp] ocr failed (upload continues unguarded):", repr(e))
        return None, "error"


async def api_shot_upload(request):
    store = _store()
    shots = store.overlay().get("shots") or []
    if len(shots) >= admin_store.SHOTS_MAX:
        return HOST.json_response(
            {"ok": False, "error": "الحد %d لقطات — احذف واحدة أولاً"
             % admin_store.SHOTS_MAX}, 400)
    post = await request.post()
    field = post.get("file")
    caption = str(post.get("caption_ar") or "")[:300]
    data = field.file.read() if hasattr(field, "file") else (
        field if isinstance(field, (bytes, bytearray)) else b"")
    if not data:
        return HOST.json_response({"ok": False, "error": "no_file"}, 400)
    if len(data) > 4 * 1024 * 1024:
        return HOST.json_response(
            {"ok": False, "error": "اللقطة كبيرة (الحد 4MB)"}, 400)
    ext, ct = _sniff(bytes(data[:16]))
    if not ext:
        return HOST.json_response(
            {"ok": False, "error": "نوع غير مدعوم (PNG/JPG/WebP)"}, 400)

    # the OCR guard: a screenshot that leaks a withheld figure never lands
    text, engine = ocr_text(bytes(data))
    if text:
        hits = guard.scan("<p>%s</p>" % text)
        if hits:
            return HOST.json_response(
                {"ok": False,
                 "error": "اللقطة مرفوضة — أرقام لا يجوز نشرها: "
                          + "، ".join(h["figure"] for h in hits[:6]),
                 "hits": hits[:10]}, 400)

    sid = uuid.uuid4().hex[:16] + "." + ext
    os.makedirs(HOST.upload_dir, exist_ok=True)
    with open(os.path.join(HOST.upload_dir, sid), "wb") as fh:
        fh.write(data)
    shot = {"id": sid, "caption_ar": caption, "path": sid}
    store.update_section("shots", shots + [shot], by=_user(request))
    return HOST.json_response({"ok": True, "shot": shot, "ocr": engine})


_SHOT_CT = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


async def serve_shot(request):
    """PUBLIC: the page's «الدليل» images. Week-cached; the id is unguessable."""
    sid = request.match_info.get("id", "")
    if not (sid and "/" not in sid and ".." not in sid):
        raise HOST.web.HTTPNotFound()
    path = os.path.join(HOST.upload_dir or "", sid)
    if not (HOST.upload_dir and os.path.exists(path)):
        raise HOST.web.HTTPNotFound()
    return HOST.web.FileResponse(path, headers={
        "Cache-Control": "public, max-age=604800",
        "Content-Type": _SHOT_CT.get(sid.rsplit(".", 1)[-1], "image/png")})


# --------------------------------------------------------------------------- #
# the logo — one upload, four derived assets
# --------------------------------------------------------------------------- #
def _brand_dir():
    d = os.path.join(HOST.upload_dir or "", "brand")
    os.makedirs(d, exist_ok=True)
    return d


def rebuild_brand(png_bytes):
    """logo.png in, favicon trio + 1200x630 share card out.

    Composed on the LOGO'S OWN background colour rather than the page cream: a
    logo that ships with its own ground shows a visible seam otherwise (that
    happened on v1 and had to be redone).
    """
    from PIL import Image
    src = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    flat = Image.new("RGB", src.size, src.convert("RGB").getpixel((2, 2)))
    flat.paste(src, (0, 0), src)
    ground = flat.getpixel((2, 2))

    # tight crop around the mark so the favicon is not mostly padding
    grey = flat.convert("L")
    w, h = flat.size
    px = grey.load()
    base = px[2, 2]
    xs, ys = [], []
    for y in range(0, h, max(1, h // 220)):
        for x in range(0, w, max(1, w // 220)):
            if abs(px[x, y] - base) > 18:
                xs.append(x)
                ys.append(y)
    if xs and ys:
        l, r, t, b = min(xs), max(xs), min(ys), max(ys)
    else:
        l, r, t, b = 0, w - 1, 0, h - 1
    mw, mh = max(1, r - l), max(1, b - t)

    side = int(max(mw, mh) * 1.18)
    cx, cy = (l + r) // 2, (t + b) // 2
    icon = flat.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2))
    out = _brand_dir()
    for size, name in ((512, "icon-512.png"), (192, "icon-192.png"), (64, "icon.png")):
        icon.resize((size, size), Image.LANCZOS).save(os.path.join(out, name),
                                                      optimize=True)
    card = Image.new("RGB", (1200, 630), ground)
    mark = flat.crop((l, t, r + 1, b + 1))
    scale = min(760.0 / mw, 470.0 / mh)
    mark = mark.resize((max(1, int(mw * scale)), max(1, int(mh * scale))), Image.LANCZOS)
    card.paste(mark, ((1200 - mark.width) // 2, (630 - mark.height) // 2))
    card.save(os.path.join(out, "share.png"), optimize=True)
    return ["icon.png", "icon-192.png", "icon-512.png", "share.png"]


async def api_logo_upload(request):
    post = await request.post()
    field = post.get("file")
    data = field.file.read() if hasattr(field, "file") else (
        field if isinstance(field, (bytes, bytearray)) else b"")
    if not data:
        return HOST.json_response({"ok": False, "error": "no_file"}, 400)
    if len(data) > 4 * 1024 * 1024:
        return HOST.json_response({"ok": False, "error": "الملف كبير (الحد 4MB)"}, 400)
    ext, _ct = _sniff(bytes(data[:16]))
    if ext not in ("png", "jpg", "webp"):
        return HOST.json_response(
            {"ok": False, "error": "الشعار يجب أن يكون PNG أو JPG أو WebP"}, 400)
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(bytes(data)))
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, format="PNG")
        png = buf.getvalue()
    except Exception:
        return HOST.json_response({"ok": False, "error": "تعذّرت قراءة الصورة"}, 400)
    with open(os.path.join(_brand_dir(), "logo.png"), "wb") as fh:
        fh.write(png)
    derived = []
    try:
        derived = rebuild_brand(png)
    except Exception:
        traceback.print_exc()   # the logo still installs; the icons keep the old set
    return HOST.json_response({"ok": True, "derived": derived})


async def api_logo_delete(request):
    removed = []
    for name in ("logo.png", "icon.png", "icon-192.png", "icon-512.png", "share.png"):
        path = os.path.join(_brand_dir(), name)
        if os.path.exists(path):
            os.remove(path)
            removed.append(name)
    return HOST.json_response({"ok": True, "removed": removed})


async def api_lead_status(request):
    b = await _body(request)
    status = str(b.get("status") or "")
    if status not in LEAD_STATUSES:
        return HOST.json_response({"ok": False, "error": "bad_status"}, 400)
    at = b.get("at")
    store = HOST.load_json("cp_leads.json", {"leads": []}) or {"leads": []}
    hit = False
    for l in store.get("leads", []):
        if l.get("at") == at:
            l["status"] = status
            hit = True
    if not hit:
        return HOST.json_response({"ok": False, "error": "lead_not_found"}, 404)
    HOST.save_json("cp_leads.json", store)
    return HOST.json_response({"ok": True})


def register(app):
    g, p = app.router.add_get, app.router.add_post
    g("/api/cp/admin/overview", _guarded(api_overview))
    g("/api/cp/admin/contacts", _guarded(api_contacts_get))
    g("/api/cp/admin/copy", _guarded(api_copy_get))
    g("/api/cp/admin/figures", _guarded(api_figures_get))
    g("/api/cp/admin/showcase", _guarded(api_showcase_get))
    g("/api/cp/admin/reviews", _guarded(api_reviews_get))
    g("/api/cp/admin/leads", _guarded(api_leads_get))
    g("/api/cp/admin/leads.csv", _guarded(api_leads_csv))
    g("/api/cp/admin/shots", _guarded(api_shots_get))
    g("/api/cp/admin/history", _guarded(api_history_get))
    for section in ("contacts", "copy", "figures", "benchmarks",
                    "showcase", "reviews", "shots"):
        target = {"figures": "figures_manual"}.get(section, section)
        p("/api/cp/admin/" + section, _guarded(_section_writer(target)))
    p("/api/cp/admin/publish", _guarded(api_publish))
    p("/api/cp/admin/rollback", _guarded(api_rollback))
    p("/api/cp/admin/sync-listings", _guarded(api_sync_listings))
    p("/api/cp/admin/snapshot-now", _guarded(api_snapshot_now))
    p("/api/cp/admin/lead-status", _guarded(api_lead_status))
    p("/api/cp/admin/shot-upload", _guarded(api_shot_upload))
    p("/api/cp/admin/shot-delete", _guarded(api_shot_delete))
    p("/api/cp/admin/logo-upload", _guarded(api_logo_upload))
    p("/api/cp/admin/logo-delete", _guarded(api_logo_delete))
    g("/cp/shot/{id}", serve_shot)
