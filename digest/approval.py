# -*- coding: utf-8 -*-
"""digest.approval — the five owner actions as one state machine.

    preview  --approve-->  approved  --publish-->  published
    preview  --alt / rephrase / drop-->  preview   (re-rendered)
    preview  --rebuild-->  building -> preview | failed
    published: nothing changes it.

`act()` is the single entry point used by the Discord buttons and the web page. It
NEVER posts on its own: publishing is the injected `publisher` callable, and with
dry_run=True it is never called — tests prove that. Every action writes digest_rulings
(who / when / what) so rank.py can learn."""

from . import build, db

ACTIONS = ("approve", "alt", "rephrase", "drop", "rebuild")
TRANSITIONS = {
    ("preview", "approve"): "approved",
    ("preview", "alt"): "preview",
    ("preview", "rephrase"): "preview",
    ("preview", "drop"): "preview",
    ("preview", "rebuild"): "building",
    ("failed", "rebuild"): "building",
    ("approved", "publish"): "published",
}
LABELS_AR = {"approve": "✅ اعتمد وانشر", "alt": "🔁 بدائل", "rephrase": "✍️ غيّر الصيغة",
             "drop": "🗑️ احذف العنصر", "rebuild": "🔄 ابنِ من جديد"}


class ApprovalError(RuntimeError):
    pass


def transition(status, action):
    return TRANSITIONS.get((status, action))


def allowed(status):
    return [a for a in ACTIONS if transition(status, a)]


def act(issue_id, action, who, now, http, section=None, slot=None, rank_no=None,
        model_call=None, model=None, search=None, load_json=None, public_base=None,
        dry_run=True, publisher=None, out_root=None):
    """-> {"ok", "status", "files", "message"}. Raises ApprovalError on a bad request."""
    row = db.issue(issue_id)
    if not row:
        raise ApprovalError("ما فيه عدد بهالرقم")
    nxt = transition(row["status"], action)
    if not nxt:
        raise ApprovalError("«%s» ما ينفع والعدد حالته %s" % (LABELS_AR.get(action, action), row["status"]))
    files = {}
    if action == "approve":
        build.approve(issue_id, now, who=who)
        status = "approved"
        if not dry_run and publisher is not None:
            publisher(db.issue(issue_id))
            db.set_issue(issue_id, status="published", published_at=db.now_iso())
            status = "published"
        msg = "تم الاعتماد" + (" والنشر" if status == "published" else " (تجربة — ما انتشر)")
    elif action == "alt":
        if section is None or slot is None or rank_no is None:
            raise ApprovalError("بدائل تحتاج القسم والخانة ورقم البديل")
        try:
            files = build.apply_alternate(issue_id, section, int(slot), int(rank_no), http, now, who=who, out_root=out_root)
        except build.BuildError as e:
            raise ApprovalError(str(e))
        status, msg = "preview", "بدّلنا العنصر وأعدنا الرسم"
    elif action == "rephrase":
        files = build.rephrase(issue_id, now, model_call, model=model, who=who, out_root=out_root)
        status, msg = "preview", "غيّرنا الصيغة، نفس الحقائق"
    elif action == "drop":
        if section is None or slot is None:
            raise ApprovalError("الحذف يحتاج القسم والخانة")
        try:
            files = build.drop_slot(issue_id, section, int(slot), now, who=who, out_root=out_root)
        except build.BuildError as e:
            raise ApprovalError(str(e))
        status, msg = "preview", "حذفنا العنصر وأعدنا الرسم"
    else:  # rebuild
        try:
            rep = build.rebuild(issue_id, now, http, search=search, load_json=load_json, who=who, out_root=out_root,
                                model_call=model_call, model=model, public_base=public_base)
        except build.BuildError as e:
            raise ApprovalError(str(e))
        files = rep.get("files") or {}
        status = rep.get("status", "failed")
        msg = "بنيناه من جديد" if status == "preview" else "إعادة البناء فشلت: %s" % "; ".join(rep.get("errors") or [])[:300]
    return {"ok": True, "status": status, "files": files, "message": msg}
