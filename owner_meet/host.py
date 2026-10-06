# -*- coding: utf-8 -*-
"""
owner_meet.host — the ONE bridge between this package and bot.py (permits/host.py pattern).
bot.py calls owner_meet.wire(_owner_meet_caps()) once at web-server start. The package never
imports bot and never calls Hostaway: everything PMS-shaped arrives here as a cap, so the
Hostaway -> StayHub move changes bot.py's caps only (spec §4, brief P7).
"""


class _Host:
    # ---- web plumbing (same as permits/reviewask) ----
    dash_auth = None            # (request) -> bool                 any logged-in staff
    req_role = None             # (request) -> 'admin'|'ops'|'viewer'|'accountant'
    actor = None                # (request) -> display name
    tab_allowed = None          # (request, tab_id) -> bool          the per-page permission matrix
    json_response = None        # (data, status=200) -> web.Response
    web = None                  # aiohttp web module
    web_thread = None           # async (fn, *a) -> result   REQUEST handlers only (never to_thread)
    tz = None
    now = None                  # () -> tz-aware Riyadh datetime
    state_dir = None            # str — STATE_DIR
    link_base = None            # () -> 'https://…'   public origin for owner links

    # ---- owners, units, terms (READ-ONLY) ----
    owners = None               # () -> [{owner, units:[{apartment, lid}]}]
    owner_lids = None           # (owner) -> [int]
    unit_info = None            # (lid) -> {lid, name, bedrooms, owner, apartment} | None
    listings_meta = None        # () -> {lid: {name, bedrooms, active}}
    terms_on = None             # (lid, date) -> {mgmt_pct, cleaning:{type, amount}} | None
    owner_portal_token = None   # (owner) -> str | None   (never creates one)

    # ---- money (READ-ONLY; the statement path is the single truth) ----
    month_report = None         # (owner, 'YYYY-MM') -> statement dict   (_owner_month_report)
    unit_month = None           # (owner, 'YYYY-MM', lid) -> one apartment's slice (unit_slice)
    cached_unit_nets = None     # (['YYYY-MM']) -> {lid: {mkey: owner_net}}   cache only, never computes

    # ---- reservations / calendar (READ-ONLY) ----
    reservations_window = None  # (start_date, end_date) -> (rows, degraded)   never the truncating cache
    explode_nights = None       # (rows) -> (nights[(lid, date, nightly)], arrivals[(lid, date)])
    season_windows = None       # (start_date, end_date) -> [{kind, start, end}]

    # ---- guest voice (READ-ONLY) ----
    reviews_all = None          # () -> [review dicts as stored in _reviews]
    review_followups = None     # ([reservation_id]) -> [{reservation_id, lid, state, mode, closed_at}]  (reviewask)

    # ---- the unit's operational record (READ-ONLY; raw — owner_meet.ops redacts) ----
    maint_tickets = None        # ([lid]) -> _dtk maint records
    proc_tickets = None         # ([lid]) -> _dtk purchase records
    rr_tickets = None           # ([lid], [unit_name]) -> _dtk reimbursement records
    dash_tickets = None         # ([lid]) -> dashboard tracker tickets
    rr_outcome = None           # (claimed, received) -> unknown|denied|received|over|full|partial
    rr_item_lines = None        # (items_raw) -> (lines, hidden)
    rr_ar_texts = None          # (rec) -> {story, reason, note, ok}    (BUILD time only — it calls Claude)
    rr_types = None             # () -> {key: arabic label}
    price_actions = None        # ([lid], start, end) -> non-dry price changes
    recovery_for = None         # ([lid], start, end) -> recovery_tickets rows
    directpay_for = None        # ([lid], start, end) -> directpay rows
    permit_for = None           # (lid) -> {end_date, days_left, band, renewal_open} | None
    cleaning_feedback = None    # ([lid], start, end) -> [{lid, score, day}]
    staff_names = None          # () -> [str]   privacy scan only, never rendered

    # ---- Airbnb report mapping + pricing (READ-ONLY) ----
    airbnb_room_ids = None      # () -> {lid: airbnb room id}   from Hostaway's own channel data
    listing_titles = None       # () -> {lid: public title}     title-similarity suggestions only
    min_price = None            # (lid) -> SAR floor | None     (the pricing engine's per-unit floor)

    # ---- the meeting record + sending (S5) ----
    owner_phone = None          # (owner) -> '9665…' | ''      only for a wa.me link Faisal taps
    ticket_status = None        # (ticket ref) -> {found, closed, closed_at}

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("owner_meet used '%s' before owner_meet.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
