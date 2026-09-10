# -*- coding: utf-8 -*-
"""
directpay.proof — the file that lets a collection room close.

Duck-typed over discord.py objects (a channel with async history(), messages with
.attachments, attachments with .filename/.content_type/.size/.read()) so the package never
imports discord and the tests drive it with fakes.

TWO DELIBERATE DIFFERENCES FROM bot._maint_has_proof — do not "fix" them:
  1. Only an image or a PDF counts. A .txt is not an invoice.
  2. A history-read error returns NO proof ("unreadable"), never "proof present". The
     maintenance ticket fails OPEN because trapping a maintenance room shut is worse than a
     weak close. Money is the opposite: if we cannot see the proof, we do not close. The
     honest Arabic message for that case is reason_ar("unreadable").

The BYTES are stored under STATE_DIR/directpay/<ticket_id>/<n>_<safe_name>. A Discord
attachment URL is signed and expires; storing the URL is storing nothing.
"""
import json
import os

from . import engine

ROOT = "directpay"
_SCAN = 200
_REASONS = {
    "none": "📎 ما فيه صورة ولا PDF من StayHub مرفوعة في هذي الغرفة. ارفع الإثبات أول، بعدين اضغط «تم التحصيل».",
    "unreadable": "ما قدرت أقرأ الملفات في الغرفة الحين، جرّب بعد شوي.",
    "ok": "",
}


def reason_ar(code):
    return _REASONS.get(str(code or ""), "")


def _qualifies(att):
    return engine.is_proof_type(getattr(att, "content_type", None), getattr(att, "filename", ""))


async def find_proof(channel, scan=_SCAN):
    """(attachment, reason). Newest qualifying attachment in the room, or (None, 'none') /
    (None, 'unreadable'). FAILS CLOSED on a history error."""
    try:
        async for m in channel.history(limit=scan):
            for att in (getattr(m, "attachments", None) or []):
                if _qualifies(att):
                    return att, "ok"
    except Exception as e:
        print("[directpay] proof scan error (refusing the close — money fails closed):", e)
        return None, "unreadable"
    return None, "none"


def check(att, max_mb):
    """(ok, reason_ar). Type and size, before a single byte is downloaded."""
    if att is None:
        return False, reason_ar("none")
    if not _qualifies(att):
        return False, "الملف لازم يكون صورة أو PDF."
    size = int(getattr(att, "size", 0) or 0)
    cap = int(max_mb) * 1024 * 1024
    if size > cap:
        mb = size / (1024.0 * 1024.0)
        return False, ("الملف كبير (%.0f ميجا) — الحد %d ميجا. ارفع نسخة أصغر أو صورة شاشة."
                       % (mb, int(max_mb)))
    return True, ""


def _safe_name(name, fallback="proof"):
    keep = []
    for c in str(name or ""):
        if c.isalnum() or c in "._-":
            keep.append(c)
        else:
            keep.append("_")
    s = "".join(keep).strip("._")
    return (s or fallback)[:80]


def _next_n(folder):
    try:
        return len([f for f in os.listdir(folder) if not f.startswith(".")]) + 1
    except FileNotFoundError:
        return 1


async def store(state_dir, ticket_id, att, uploader_name, uploader_id):
    """Download the bytes and persist them; returns (relative_path, meta). Raises if the read
    fails — nothing is written then, and the caller refuses the close."""
    data = await att.read()                        # <-- the BYTES. never the URL.
    folder = os.path.join(state_dir, ROOT, _safe_name(ticket_id, "ticket"))
    os.makedirs(folder, exist_ok=True)
    fname = "%d_%s" % (_next_n(folder), _safe_name(getattr(att, "filename", ""), "proof"))
    rel = "%s/%s/%s" % (ROOT, _safe_name(ticket_id, "ticket"), fname)
    with open(os.path.join(state_dir, rel), "wb") as f:
        f.write(data)
    meta = {"filename": str(getattr(att, "filename", "") or ""), "size": len(data),
            "content_type": str(getattr(att, "content_type", "") or ""),
            "uploader": str(uploader_name or ""), "uploader_id": str(uploader_id or ""),
            "stored_as": fname}
    return rel, meta


def abs_path(state_dir, rel):
    rel = str(rel or "")
    if not rel.startswith(ROOT + "/") or ".." in rel:
        return None
    return os.path.join(state_dir, rel)


def meta_json(meta):
    try:
        return json.dumps(meta or {}, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"
