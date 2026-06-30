"""
roster.hostaway — reconcile the roster's properties against the live Hostaway listings
(build spec §5). READ-ONLY against Hostaway (reuses HOST.get_listings_map / HOST.ls_get;
never creates a second client). NEVER auto-assigns an owner — new listings land in the
"unassigned" panel for ops to name + own; vanished listings are flagged, never auto-offboarded.
"""

from . import db
from .host import HOST


def sync():
    """Match roster_properties to Hostaway listings. Returns a report dict.
      - linked:           properties we attached a hostaway_listing_id/zone to
      - created:          NEW listings with no roster row -> created with NO owner (unassigned)
      - possibly_inactive: roster props whose listing id is no longer in Hostaway
    """
    report = {"linked": [], "created": [], "possibly_inactive": []}

    listings = {}
    try:
        listings = HOST.get_listings_map() or {}   # {lid: internal_name}
    except Exception as e:
        return {"error": "listings: %s" % e, **report}

    zone_by_lid = {}
    try:
        for lid, rec in ((HOST.ls_get() or {}).get("listings") or {}).items():
            zone_by_lid[str(lid)] = (rec or {}).get("group") or None
    except Exception:
        pass

    props = db.properties()
    by_lid = {str(p["hostaway_listing_id"]): p for p in props if p.get("hostaway_listing_id")}
    by_name = {p["display_name_ar"]: p for p in props}
    live_lids = {str(lid) for lid in listings}

    for lid, name in listings.items():
        slid = str(lid)
        name = str(name).strip()
        if slid in by_lid:
            # already linked — refresh zone if we learned one
            zone = zone_by_lid.get(slid)
            if zone and not by_lid[slid].get("zone"):
                db.execute("UPDATE roster_properties SET zone=? WHERE id=?", (zone, by_lid[slid]["id"]))
            continue
        match = by_name.get(name)
        if match:
            db.execute("UPDATE roster_properties SET hostaway_listing_id=?, zone=COALESCE(zone,?) WHERE id=?",
                       (slid, zone_by_lid.get(slid), match["id"]))
            report["linked"].append({"id": match["id"], "name": name, "lid": slid})
        else:
            # NEW listing with no roster row -> create UNASSIGNED (no owner). Ops names+owns it.
            pid = db.execute(
                "INSERT INTO roster_properties(hostaway_listing_id,display_name_ar,primary_owner_id,"
                "zone,turnover_weight,status,created_at) VALUES(?,?,?,?,1,'active',?)",
                (slid, name or ("Listing %s" % slid), None, zone_by_lid.get(slid), db.now_iso()))
            report["created"].append({"id": pid, "name": name, "lid": slid})

    # roster props whose listing id vanished from Hostaway -> flag (do NOT auto-offboard)
    for p in props:
        hid = p.get("hostaway_listing_id")
        if hid and str(hid) not in live_lids and p.get("status") == "active":
            report["possibly_inactive"].append({"id": p["id"], "name": p["display_name_ar"], "lid": str(hid)})

    return report
