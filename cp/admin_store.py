# -*- coding: utf-8 -*-
"""
cp.admin_store — the one overlay behind the «الملف التعريفي» tab.

Everything the dashboard edits lives in $STATE_DIR/cp_admin.json; the repo's
cp/data/*.json stay the immutable defaults. Two overlays matter and they are
deliberately different things:

  * the WORKING overlay — what the tab edits and the preview renders,
  * the PUBLISHED overlay — the frozen copy the public page renders, written
    only by publish() and restored only by rollback().

That split is the entire safety story of "edit freely, publish deliberately":
a half-finished edit can never leak to a prospect, and publish is an atomic
copy of a state someone actually looked at. History keeps the last 10 published
snapshots; rollback is a copy back, not an undo stack.

Validation lives HERE, not in the handlers, so no future endpoint can save
garbage by forgetting a check. The store raises ValidationError with an
Arabic-ready message; handlers translate it to a 400.
"""
import copy
import json
import re
from datetime import datetime, timezone, timedelta

STORE_NAME = "cp_admin.json"
HISTORY_MAX = 10
SHOWCASE_HARD_MAX = 12
SHOTS_MAX = 3
REVIEWS_MAX = 6

_TZ = timezone(timedelta(hours=3))   # Riyadh

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SECTIONS = ("contacts", "copy", "figures_manual", "benchmarks",
             "showcase", "reviews", "shots")

_TOP_KEYS = ("schema_version", "published_version", "published_overlay",
             "updated_at", "updated_by", "history") + _SECTIONS


class ValidationError(ValueError):
    """A save that must not happen. The message is shown to the editor."""


def default_overlay():
    return {
        "schema_version": 1,
        "published_version": "v1",
        "published_overlay": {},        # frozen sections at last publish
        "updated_at": "",
        "updated_by": "",
        "contacts": {
            "whatsapp": "966533779297",
            "email": "Info@oujares.com",
            "booking_link": "",
            "booking_modes": {"online": True, "office": True},
            "office_label_ar": "في مكتبنا · الرياض",
            "slots": ["am", "pm", "eve"],
            "lead_channel_id": "",
            "pdf_path": "",
            "english_ready": False,
        },
        "copy": {},
        "figures_manual": {},
        "benchmarks": {},
        "showcase": {"max": 6, "units": []},
        "reviews": {"ids": []},
        "shots": [],
        "history": [],
    }


def _now():
    return datetime.now(_TZ).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# validators — one per section
# --------------------------------------------------------------------------- #
def _digits(s):
    return re.sub(r"\D", "", str(s or ""))


def _validate_contacts(cur, patch):
    out = dict(cur)
    for key, value in patch.items():
        if key == "whatsapp":
            d = _digits(value)
            if value and not (9 <= len(d) <= 15):
                raise ValidationError("رقم الواتساب غير صالح — أرقام فقط (9–15 خانة)")
            out["whatsapp"] = d
        elif key == "email":
            v = str(value or "").strip()
            if v and not _EMAIL_RE.match(v):
                raise ValidationError("صيغة البريد غير صحيحة")
            out["email"] = v
        elif key == "booking_link":
            v = str(value or "").strip()
            if v and not v.lower().startswith(("http://", "https://")):
                raise ValidationError("رابط التقويم يجب أن يبدأ بـ https://")
            out["booking_link"] = v
        elif key == "booking_modes":
            modes = {"online": bool((value or {}).get("online")),
                     "office": bool((value or {}).get("office"))}
            if not (modes["online"] or modes["office"]):
                raise ValidationError("يجب أن تبقى طريقة لقاء واحدة على الأقل مفعّلة")
            out["booking_modes"] = modes
        elif key == "slots":
            slots = [str(x) for x in (value or [])]
            if not slots or any(s not in ("am", "pm", "eve") for s in slots):
                raise ValidationError("الأوقات المسموحة: صباحاً/بعد الظهر/مساءً")
            out["slots"] = slots
        elif key in ("office_label_ar", "lead_channel_id", "pdf_path"):
            out[key] = str(value or "").strip()[:400]
        elif key == "english_ready":
            out[key] = bool(value)
        # unknown contact keys are dropped silently
    return out


def _validate_copy(cur, patch):
    out = dict(cur)
    for key, value in (patch or {}).items():
        if not re.match(r"^[a-z0-9_.-]{1,80}$", str(key)):
            raise ValidationError("مفتاح نص غير صالح: %r" % key)
        out[str(key)] = str(value if value is not None else "")[:4000]
    return out


def _validate_manual(cur, patch):
    out = dict(cur)
    for key, entry in (patch or {}).items():
        if entry is None:            # explicit clear -> fall back to default
            out.pop(key, None)
            continue
        if not isinstance(entry, dict):
            raise ValidationError("قيمة يدوية غير صالحة: %r" % key)
        missing = [f for f in ("value", "as_of", "source")
                   if not str(entry.get(f) if entry.get(f) is not None else "").strip()]
        if missing:
            raise ValidationError(
                "الرقم اليدوي «%s» ناقص: %s — قيمة وتاريخ ومصدر أو لا يُنشر"
                % (key, "، ".join(missing)))
        out[key] = {"value": entry["value"], "as_of": str(entry["as_of"]),
                    "source": str(entry["source"])[:200]}
    return out


def _validate_benchmarks(cur, patch):
    # same three-field discipline as the manual layer — a benchmark without a
    # source and date is exactly the unverifiable figure this page must not carry
    return _validate_manual(cur, patch)


def _validate_showcase(cur, patch):
    out = dict(cur)
    if "max" in patch:
        try:
            m = int(patch["max"])
        except (TypeError, ValueError):
            raise ValidationError("حد الوحدات يجب أن يكون رقماً")
        if not 1 <= m <= SHOWCASE_HARD_MAX:
            raise ValidationError("حد الوحدات بين 1 و%d" % SHOWCASE_HARD_MAX)
        out["max"] = m
    if "units" in patch:
        units = patch["units"] or []
        if not isinstance(units, list) or len(units) > SHOWCASE_HARD_MAX:
            raise ValidationError("قائمة الوحدات غير صالحة (الحد %d)" % SHOWCASE_HARD_MAX)
        clean = []
        for u in units:
            if not isinstance(u, dict) or not str(u.get("listing_id") or "").strip():
                raise ValidationError("كل وحدة تحتاج listing_id")
            clean.append({
                "listing_id": str(u["listing_id"]).strip(),
                "name_ar": str(u.get("name_ar") or "")[:120],
                "bedrooms_label_ar": str(u.get("bedrooms_label_ar") or "")[:80],
                "line_ar": str(u.get("line_ar") or "")[:300],
                "cover_url": str(u.get("cover_url") or "")[:1000],
                "hidden": bool(u.get("hidden")),
            })
        out["units"] = clean
    return out


def _validate_reviews(cur, patch):
    out = dict(cur)
    if "ids" in patch:
        ids = patch["ids"] or []
        try:
            ids = [int(x) for x in ids]
        except (TypeError, ValueError):
            raise ValidationError("معرّفات المراجعات أرقام فقط")
        if len(ids) > REVIEWS_MAX:
            raise ValidationError("الحد %d مراجعات" % REVIEWS_MAX)
        out["ids"] = ids
    return out


def _validate_shots(cur, patch):
    shots = patch or []
    if not isinstance(shots, list) or len(shots) > SHOTS_MAX:
        raise ValidationError("الحد %d لقطات" % SHOTS_MAX)
    clean = []
    for sh in shots:
        if not isinstance(sh, dict) or not str(sh.get("id") or "").strip():
            raise ValidationError("لقطة بلا معرّف")
        clean.append({"id": str(sh["id"])[:64],
                      "caption_ar": str(sh.get("caption_ar") or "")[:300],
                      "path": str(sh.get("path") or "")[:400]})
    return clean


_VALIDATORS = {
    "contacts": _validate_contacts,
    "copy": _validate_copy,
    "figures_manual": _validate_manual,
    "benchmarks": _validate_benchmarks,
    "showcase": _validate_showcase,
    "reviews": _validate_reviews,
    "shots": lambda cur, patch: _validate_shots(cur, patch),
}


# --------------------------------------------------------------------------- #
# the store
# --------------------------------------------------------------------------- #
class Store:
    def __init__(self, load_json, save_json):
        self._load = load_json
        self._save = save_json

    # -- read ---------------------------------------------------------------- #
    def overlay(self):
        """The working overlay, schema-corrected. Unknown top-level keys from a
        hand-edited file are dropped so they cannot ride into a render."""
        raw = self._load(STORE_NAME, None)
        base = default_overlay()
        if isinstance(raw, dict):
            for key in _TOP_KEYS:
                if key in raw:
                    if isinstance(base.get(key), dict) and isinstance(raw[key], dict):
                        merged = dict(base[key])
                        merged.update(raw[key])
                        base[key] = merged
                    else:
                        base[key] = raw[key]
        return base

    def published_overlay(self):
        """The frozen sections the PUBLIC page renders. Before any publish this
        is empty — the renderer then uses repo defaults, exactly v1 behavior."""
        ov = self.overlay()
        pub = ov.get("published_overlay") or {}
        out = {k: copy.deepcopy(pub.get(k)) for k in _SECTIONS if k in pub}
        out["published_version"] = ov.get("published_version", "v1")
        return out

    def merged_manual(self, defaults):
        """defaults (repo cp_manual.json shape) ← overlay figures_manual."""
        merged = dict(defaults or {})
        merged.update(self.overlay().get("figures_manual") or {})
        return merged

    # -- write --------------------------------------------------------------- #
    def _write(self, ov):
        self._save(STORE_NAME, ov)

    def update_section(self, section, patch, by=""):
        if section not in _SECTIONS:
            raise ValidationError("قسم غير معروف: %r" % section)
        ov = self.overlay()
        ov[section] = _VALIDATORS[section](ov.get(section) or
                                           ({} if section != "shots" else []), patch)
        ov["updated_at"] = _now()
        ov["updated_by"] = str(by or "")[:80]
        self._write(ov)
        return ov[section]

    def publish(self, version, by=""):
        """Freeze the working sections as the published overlay + history entry."""
        if version not in ("v1", "v2"):
            raise ValidationError("نسخة غير معروفة: %r" % version)
        ov = self.overlay()
        frozen = {k: copy.deepcopy(ov.get(k)) for k in _SECTIONS}
        entry = {"at": _now(), "by": str(by or "")[:80], "version": version,
                 "overlay": frozen}
        ov["published_overlay"] = frozen
        ov["published_version"] = version
        ov["history"] = (ov.get("history") or [])[-(HISTORY_MAX - 1):] + [entry]
        ov["updated_at"] = entry["at"]
        ov["updated_by"] = entry["by"]
        self._write(ov)
        return entry

    def rollback(self, at, by=""):
        """Restore the published overlay (and version) from a history entry."""
        ov = self.overlay()
        entry = next((h for h in (ov.get("history") or []) if h.get("at") == at), None)
        if not entry:
            raise ValidationError("لا توجد نسخة منشورة بهذا التاريخ")
        ov["published_overlay"] = copy.deepcopy(entry["overlay"])
        ov["published_version"] = entry["version"]
        ov["updated_at"] = _now()
        ov["updated_by"] = str(by or "")[:80]
        self._write(ov)
        return entry


def to_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)
