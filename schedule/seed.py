# -*- coding: utf-8 -*-
"""
schedule.seed — the EXACT seed from the build spec §4 (53 apartments, apartment sort_order =
order in each list from 0). Idempotent: seeds only when empty. `reset_to_default()` is the
editor-only "إعادة تعيين البيانات للوضع الافتراضي" action — wipes schedule_* and re-seeds.
"""

from . import db

EMPLOYEES = [
    {"name": "ناصر",        "off_day": 2, "color": "#4A6246", "emoji": "🟢", "sort_order": 0},
    {"name": "مآثر",        "off_day": 0, "color": "#8B593C", "emoji": "🟠", "sort_order": 1},
    {"name": "نورة",        "off_day": 1, "color": "#6A3A5D", "emoji": "🟣", "sort_order": 2},
    {"name": "محمد اليامي", "off_day": 3, "color": "#3C5462", "emoji": "🔵", "sort_order": 3},
    {"name": "عهود",        "off_day": 6, "color": "#36655E", "emoji": "🟡", "sort_order": 4},
]
APARTMENTS = {
    "ناصر":        ["الملقا 1", "A5", "FD1", "103", "H8", "202 الملقا", "A2 (التعاون)", "Jood12", "Jood13", "حطين 6b", "نزل فاتن"],
    "مآثر":        ["201a", "201b", "101a", "101b", "202a", "202b", "102a", "102b", "قرطبه B20", "قرطبه A1", "هاجر 22", "كالما 90"],
    "نورة":        ["F1", "6b", "3b", "C2 (العارض)", "C2 (النفل)", "C08", "Heu9", "F2", "شقة 11 (الملقا)"],
    "محمد اليامي": ["C204", "B10", "B03", "B02", "التعاون b13", "رافال 4101", "رافال 4511", "C03", "العارض A11", "نصل العقيق", "14B البدور"],
    "عهود":        ["رويال B11", "القيروان ديار 20", "القيروان D7", "حطين (صاد)", "B06 الملقا", "103 النرجس", "9b", "12b", "عرقه E15", "C118 (الربيع)"],
}
DEFAULT_TITLE = "تقويم موظفي عوجا"
DEFAULT_SUBTITLE = "مسؤوليات التغطية اليومية"


def _insert_seed(cx=None):
    """Insert the default data. With `cx` every row rides ONE open transaction
    (reset_to_default); without it each row commits on its own (first boot)."""
    def ex(sql, args=()):
        if cx is not None:
            return cx.execute(sql, args).lastrowid
        return db.execute(sql, args)
    name_to_id = {}
    for e in EMPLOYEES:
        eid = ex(
            "INSERT INTO schedule_employees(name,off_day,color,emoji,sort_order,created_at) VALUES(?,?,?,?,?,?)",
            (e["name"], e["off_day"], e["color"], e.get("emoji"), e["sort_order"], db.now_iso()))
        name_to_id[e["name"]] = eid
    for owner, names in APARTMENTS.items():
        for so, nm in enumerate(names):
            ex(
                "INSERT INTO schedule_apartments(name,owner_id,sort_order,created_at) VALUES(?,?,?,?)",
                (nm, name_to_id[owner], so, db.now_iso()))
    has_settings = (cx.execute("SELECT COUNT(*) FROM schedule_settings").fetchone()[0]
                    if cx is not None else bool(db.settings()))
    if not has_settings:
        ex("INSERT OR REPLACE INTO schedule_settings(id,title,subtitle) VALUES(1,?,?)",
           (DEFAULT_TITLE, DEFAULT_SUBTITLE))


def seed_if_empty():
    """Idempotent: insert the default data only when there are no employees yet."""
    db._ensure()
    if db.employees():
        return {"seeded": False, "employees": len(db.employees()), "apartments": len(db.apartments())}
    _insert_seed()
    return {"seeded": True, "employees": len(db.employees()), "apartments": len(db.apartments())}


def reset_to_default():
    """Editor-only hard reset: wipe ALL schedule_* rows and re-seed the defaults —
    in ONE transaction, so a mid-seed failure rolls back instead of leaving the
    schedule wiped."""
    with db.transaction() as cx:
        for t in ("schedule_coverage_overrides", "schedule_absences",
                  "schedule_apartments", "schedule_employees", "schedule_settings"):
            cx.execute("DELETE FROM " + t)
        _insert_seed(cx)
    return {"reset": True, "employees": len(db.employees()), "apartments": len(db.apartments())}
