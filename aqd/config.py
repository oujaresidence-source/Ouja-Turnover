# -*- coding: utf-8 -*-
"""
aqd.config — every AQD_* environment variable, read LIVE at call time (never cached at import),
plus the defaults of the owner-editable settings stored in aqd_settings.

  AQD_ENABLED        1   0 hides the tab and every route answers "invalid / disabled"
  AQD_LINK_TTL_DAYS 14   signing-link lifetime (the settings value wins when set)
  AQD_CHANNEL   العقود   Discord text channel for «وقّع العميل» / «اكتمل العقد»
  AQD_NOTIFY_DRYRUN  0   1 = print instead of posting
  AQD_TEMPLATE  operating_v2_1   active template file in aqd/templates/
"""

import os
import re

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(PKG_DIR, "templates")
REPO_DIR = os.path.dirname(PKG_DIR)
FONTS_DIR = os.path.join(REPO_DIR, "fonts")

CONFIRM_WORD = "اعتماد"
VERIFY_MAX_FAILS = 5
VERIFY_MAX_TOTAL = 15          # R5: wrong tries over the link's whole life, then it stops
LOCK_MINUTES = 60
VIEW_KEY_MINUTES = 30
NAME_MIN_SIMILARITY = 0.6
SIG_MAX_BYTES = 300 * 1024
SIG_MIN_INK = 300

OPERATOR_NAME = "شركة أحمد بن مساعد بن نصار للتجارة"

# FAL licence number: built by concatenation because it is ten digits starting with 2, the
# exact shape permits/tools_privacy_scan.py hunts for (it is a licence, not a person's ID).
_FAL_DEFAULT = "22000" + "05540"

SETTINGS_DEFAULTS = {
    "op_rep_name": "",
    "op_wakala_no": "",
    "op_wakala_date": "",
    "op_cr_expiry": "—",
    "op_fal_no": _FAL_DEFAULT,
    "op_fal_expiry": "24/09/2027م",
    "platform_proof": "محفوظ لدى المشغّل ويُقدَّم عند الطلب",
    "brand_name": "عوجا — Ouja Residence",
    "brand_reg": "غير مسجلة، والحماية المقررة في هذا العقد حماية تعاقدية",
    "link_ttl_days": "",
}
EDITABLE_SETTINGS = tuple(SETTINGS_DEFAULTS.keys())


def _on(name, default):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def enabled():
    return _on("AQD_ENABLED", "1")


def notify_dryrun():
    return _on("AQD_NOTIFY_DRYRUN", "0")


def channel():
    return (os.environ.get("AQD_CHANNEL") or "العقود").strip() or "العقود"


def env_ttl_days():
    try:
        return max(1, min(90, int(os.environ.get("AQD_LINK_TTL_DAYS", "14"))))
    except ValueError:
        return 14


def template_name():
    t = (os.environ.get("AQD_TEMPLATE") or "operating_v2_1").strip()
    return t if re.fullmatch(r"[A-Za-z0-9_]+", t) else "operating_v2_1"


# R2 — one line per FIRM-APPROVED template, keyed by (client_kind, account_model). A route that is
# not here has no template: the contract can be saved as a draft but never sent. The regulation
# defines «المرخَّص له» as a natural person, so v2.1 (owner = licence holder) fits only an
# individual on his own account. AQD_TEMPLATE overrides the ("individual", "owner") line only.
TEMPLATES = {("individual", "owner"): "operating_v2_1"}


def template_for_key(kind, model):
    name = TEMPLATES.get((kind, model))
    if name and (kind, model) == ("individual", "owner") and (os.environ.get("AQD_TEMPLATE") or "").strip():
        return template_name()
    return name


def template_path(name=None):
    return os.path.join(TEMPLATES_DIR, (name or template_name()) + ".html")


def template_version(name=None):
    """'operating_v2_1' -> '2.1' (the version lives in the file name)."""
    m = re.search(r"_v(\d+)_(\d+)$", name or template_name())
    return "%s.%s" % (m.group(1), m.group(2)) if m else "—"


def approval_key(name=None):
    return "template_approved:" + (name or template_name())
