# -*- coding: utf-8 -*-
"""
The first two projects, typed from the signed quotes of 22 Nov 2026, plus the team.
Owner (2026-11-23): «هذا مشروعين جاهزة» — both are signed and paid, so they are seeded as
ready drafts; the apartment quote left the unit and owner blank, and the start gate will ask
for them. Runs once (contracting_meta.seeded) — a deleted project never comes back.
"""

from . import db

PEOPLE = [("فيصل", "boss"), ("أصيل", "lead"), ("ناصر", "account"),
          ("أبو أمين", "site"), ("تقي", "site"), ("وجدان", "site")]

PROJECTS = [
    {"title": "الجلسة الخارجية · D2", "owner": "أ. عبدالعزيز الزاحم",
     "unit": "الجلسة الخارجية، وحدة D2", "total_sar": 22317.90, "signed": 1, "paid": 1,
     "source": "عرض سعر 22 نوفمبر 2026 — موقّع",
     "lines": [("رفع مساحي للتراس", 350, "2026-11-24"),
               ("منقل غاز مع تمديد الغاز", 1900, "2026-11-30"),
               ("برجولا حديد مع سقف لكسان", 4800, "2026-12-06"),
               ("كهرباء وإضاءة مخفية 38.84 م", 1509, "2026-12-08"),
               ("كبينة MDF + عازل فلين", 2480, "2026-12-09"),
               ("حامل برافع كهربائي + شاشة 75", 5259, "2026-12-10"),
               ("كنب خارجي مبني U", 4000, "2026-12-13")],
     "handover": "2026-12-15"},
    {"title": "صيانة وتأثيث شقة", "owner": "", "unit": "", "total_sar": 11376.31,
     "signed": 1, "paid": 1, "source": "عرض سعر 22 نوفمبر 2026",
     "lines": [("قطع السباكة + السخان (عرض المورد 2547)", 1159, "2026-11-24"),
               ("الفني يركّب السباكة", 300, "2026-11-25"),
               ("كنب جديد + شيل القديم + النقل", 4000, "2026-11-27"),
               ("سجادة + طاولة", 2448, "2026-11-28"),
               ("سرير + مرتبة", 1200, "2026-11-30"),
               ("المفروشات لسريرين (درة الفنادق 40003558SQ)", 1235.10, "2026-12-01")],
     "handover": "2026-12-03"},
]


def seed_if_empty(by="system"):
    if db.meta("seeded"):
        return False
    for name, role in PEOPLE:
        if not db.person(name):
            db.set_person(name, role, "", by)
    if not db.q1("SELECT id FROM contracting_projects LIMIT 1"):
        for p in PROJECTS:
            db.create_project(p["title"],
                              [{"name": n, "amount": a, "due": d} for n, a, d in p["lines"]],
                              by=by, owner=p["owner"], unit=p["unit"], total_sar=p["total_sar"],
                              signed=p["signed"], paid=p["paid"], source=p["source"],
                              handover_due=p["handover"])
    db.set_meta("seeded", db.now_iso())
    return True
