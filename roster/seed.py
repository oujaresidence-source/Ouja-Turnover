"""
roster.seed — idempotent seed from the real ops data (build spec §3 + §10).

IDEMPOTENT: re-running never duplicates. Employees are matched by name_ar, properties by
display_name_ar; only missing rows are inserted. Existing edits (owner changes, off-days,
absences) are never clobbered.

SEED SOURCES (real data, no invention):
  * employees: the 5 custodians + their weekly day-off from the build spec, plus the two
    managers (Wejdan = ops_manager, Aseel = team_leader). Discord ids come from
    assignments.json -> discord_ids.
  * properties: the 55 live unit names from assignments.json. Each unit's PRIMARY custodian
    is the MODAL (most-frequent) assignee across the 7-day rota — a deterministic, defensible
    read of how the unit is actually staffed.

KNOWN GAP (reported, never faked): assignments.json contains only 4 custodians
(ناصر/ماذر/نورة/محمد اليامي). عهود is NOT in any repo data, so her 8 units cannot be
derived. عهود is seeded as an active custodian with 0 units; the owner assigns her units in
2 minutes via the dashboard Owners panel, OR by dropping a `roster_owner_overrides.json`
(unit_name -> custodian_name) on the volume which this seeder applies on top of the modal.
"""

import json
import os

from . import db
from .host import HOST

# assignment-rota name  ->  canonical employee name_ar
_NAME_CANON = {
    "ناصر": "ناصر",
    "ماذر": "مآثر", "مآثر": "مآثر", "ماثر": "مآثر",
    "نورة": "نورة", "نوره": "نورة",
    "محمد اليامي": "محمد اليامي", "محمد": "محمد اليامي",
    "عهود": "عهود",
}

# the workforce + roles + weekly day off (build spec §3)
_EMPLOYEES = [
    {"name_ar": "ناصر",        "initial_ar": "ن", "weekly_off": "tue", "role": "employee"},
    {"name_ar": "مآثر",        "initial_ar": "م", "weekly_off": "sun", "role": "employee"},
    {"name_ar": "نورة",        "initial_ar": "ن", "weekly_off": "mon", "role": "employee"},
    {"name_ar": "محمد اليامي", "initial_ar": "م", "weekly_off": "wed", "role": "employee"},
    {"name_ar": "عهود",        "initial_ar": "ع", "weekly_off": "sat", "role": "employee"},
    {"name_ar": "وجدان",       "initial_ar": "و", "weekly_off": "",    "role": "ops_manager"},
    {"name_ar": "أسيل",        "initial_ar": "أ", "weekly_off": "",    "role": "team_leader"},
]


def _load_assignments():
    """assignments.json from the volume (preferred) or the repo copy as a fallback."""
    data = {}
    try:
        if HOST.load_json:
            data = HOST.load_json("assignments.json", {}) or {}
    except Exception:
        data = {}
    if not data.get("by_day"):
        try:
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            with open(os.path.join(here, "assignments.json"), encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}
    return data


def _modal_owners(assignments):
    """unit_name -> canonical custodian name, by most-frequent assignee across the 7 days."""
    tally = {}   # unit -> {canon_name: count}
    for _day, units in (assignments.get("by_day") or {}).items():
        for unit, who in (units or {}).items():
            canon = _NAME_CANON.get((who or "").strip(), (who or "").strip())
            tally.setdefault(unit, {}).setdefault(canon, 0)
            tally[unit][canon] += 1
    out = {}
    for unit, counts in tally.items():
        # deterministic: highest count, then name order
        out[unit] = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return out


def _apply_overrides(modal):
    """Optional owner-editable file on the volume: {unit_name: custodian_name}."""
    try:
        ov = HOST.load_json("roster_owner_overrides.json", {}) if HOST.load_json else {}
    except Exception:
        ov = {}
    for unit, who in (ov or {}).items():
        modal[unit] = _NAME_CANON.get((who or "").strip(), (who or "").strip())
    return modal


def seed_all():
    """Create+seed everything. Returns a human-readable report dict. Idempotent."""
    db._ensure()
    report = {"employees_added": 0, "properties_added": 0, "owner_counts": {},
              "unmatched_owner": [], "notes": []}

    # ---- employees (match by name_ar) ----
    discord_ids = (_load_assignments().get("discord_ids") or {})
    existing = {e["name_ar"]: e for e in db.employees()}
    for e in _EMPLOYEES:
        if e["name_ar"] in existing:
            continue
        did = discord_ids.get(e["name_ar"]) or discord_ids.get(
            next((k for k, v in _NAME_CANON.items() if v == e["name_ar"]), ""), "")
        db.execute(
            "INSERT INTO roster_employees(name_ar,initial_ar,weekly_off,role,is_active,discord_id,created_at)"
            " VALUES(?,?,?,?,1,?,?)",
            (e["name_ar"], e["initial_ar"], e["weekly_off"], e["role"], did or None, db.now_iso()))
        report["employees_added"] += 1

    name_to_id = {e["name_ar"]: e["id"] for e in db.employees()}

    # ---- properties (match by display_name_ar) ----
    assignments = _load_assignments()
    modal = _apply_overrides(_modal_owners(assignments))

    # optional listing match for hostaway_listing_id + zone
    lid_by_name, zone_by_lid = {}, {}
    try:
        if HOST.get_listings_map:
            for lid, nm in (HOST.get_listings_map() or {}).items():
                lid_by_name[str(nm).strip()] = lid
        if HOST.ls_get:
            for lid, rec in ((HOST.ls_get() or {}).get("listings") or {}).items():
                zone_by_lid[str(lid)] = (rec or {}).get("group") or None
    except Exception:
        pass

    existing_props = {p["display_name_ar"] for p in db.properties()}
    for unit in modal:
        if unit in existing_props:
            continue
        owner_name = modal.get(unit)
        owner_id = name_to_id.get(owner_name)
        if not owner_id:
            report["unmatched_owner"].append(unit)
        lid = lid_by_name.get(unit)
        zone = zone_by_lid.get(str(lid)) if lid else None
        db.execute(
            "INSERT INTO roster_properties(hostaway_listing_id,display_name_ar,primary_owner_id,"
            "zone,turnover_weight,status,created_at) VALUES(?,?,?,?,1,'active',?)",
            (str(lid) if lid else None, unit, owner_id, zone, db.now_iso()))
        report["properties_added"] += 1

    # ---- report: how many units each custodian carries now ----
    rows = db.q("SELECT e.name_ar nm, COUNT(p.id) n FROM roster_employees e "
                "LEFT JOIN roster_properties p ON p.primary_owner_id=e.id AND p.status='active' "
                "GROUP BY e.id ORDER BY e.id")
    report["owner_counts"] = {r["nm"]: r["n"] for r in rows}
    ahoud = report["owner_counts"].get("عهود", 0)
    if ahoud == 0:
        report["notes"].append(
            "عهود لا تملك شقق بعد — أسماء شققها غير موجودة في بيانات المستودع. "
            "عيّنها من تبويب «المسؤولون» أو عبر roster_owner_overrides.json.")
    return report
