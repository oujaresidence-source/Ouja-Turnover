#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ouja Turnover Bot
=================
Watches Hostaway for upcoming checkouts and, 12 hours before each one, opens a
Discord channel named after the unit's internal name. The channel shows the
guest name + checkout time and has a "✅ Cleaning Done" button. When a cleaner
taps it, the channel is deleted instantly.

Runs 24/7 (e.g. on Railway). All secrets come from environment variables —
never hard-code them in this file.

Required environment variables:
  HOSTAWAY_ACCOUNT_ID   your Hostaway account id (e.g. 147296)
  HOSTAWAY_API_KEY      your Hostaway API key
  DISCORD_TOKEN         the bot token from the Discord Developer Portal
  DISCORD_GUILD_ID      your Discord server id (right-click server -> Copy Server ID)

Optional (sensible defaults):
  HOURS_AHEAD           how many hours before checkout to open the channel (default 12)
  POLL_MINUTES          how often to check Hostaway (default 15)
  TIMEZONE              default "Asia/Riyadh"
  CATEGORY_NAME         Discord category to group channels (default "🧹 Turnovers")
  DEFAULT_CHECKOUT_HOUR used if a reservation has no checkout time (default 12)
"""

import os
import re
import json
import time
import asyncio
from datetime import datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo

import requests
import discord
from discord.ext import commands, tasks

# ---------------- config ----------------
HOSTAWAY_ACCOUNT_ID = os.environ.get("HOSTAWAY_ACCOUNT_ID", "")
HOSTAWAY_API_KEY    = os.environ.get("HOSTAWAY_API_KEY", "")
DISCORD_TOKEN       = os.environ.get("DISCORD_TOKEN", "")
GUILD_ID            = int(os.environ.get("DISCORD_GUILD_ID", "0") or "0")

HOURS_AHEAD          = int(os.environ.get("HOURS_AHEAD", "12"))
POLL_MINUTES         = int(os.environ.get("POLL_MINUTES", "15"))
TZ                   = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Riyadh"))
CATEGORY_NAME        = os.environ.get("CATEGORY_NAME", "🧹 Turnovers")
# Category for the guest-assistant + escalations channels (your existing ops category).
ASSISTANT_CATEGORY   = os.environ.get("ASSISTANT_CATEGORY", "Operations")
DEFAULT_CHECKOUT_HOUR = int(os.environ.get("DEFAULT_CHECKOUT_HOUR", "12"))

# ---- last-minute tiered discount (all Riyadh time) ----
# Tier 1 fires at midnight, Tier 2 deepens it at noon, Tier 3 deepens again at 4 PM.
DISCOUNT_TIER1_PERCENT = float(os.environ.get("DISCOUNT_TIER1_PERCENT", "15"))
DISCOUNT_TIER1_HOUR    = int(os.environ.get("DISCOUNT_TIER1_HOUR", "0"))    # 00:00 = midnight
DISCOUNT_TIER2_PERCENT = float(os.environ.get("DISCOUNT_TIER2_PERCENT", "20"))
DISCOUNT_TIER2_HOUR    = int(os.environ.get("DISCOUNT_TIER2_HOUR", "12"))   # 12:00 = noon
DISCOUNT_TIER3_PERCENT = float(os.environ.get("DISCOUNT_TIER3_PERCENT", "30"))
DISCOUNT_TIER3_HOUR    = int(os.environ.get("DISCOUNT_TIER3_HOUR", "18"))   # 18:00 = 6 PM
DISCOUNT_DRY_RUN = os.environ.get("DISCOUNT_DRY_RUN", "1") not in ("0", "false", "False", "no")
DISCOUNT_FLOOR   = float(os.environ.get("DISCOUNT_FLOOR", "0") or "0")      # 0 = no floor
DISCOUNT_CHANNEL = os.environ.get("DISCOUNT_CHANNEL", "pricing-log")        # summary channel
DISCOUNT_STATE_FILE = "discount_state.json"                                 # remembers tonight's original price
# Diagnostics: after each live write, re-read the day and log requested vs actual price.
DISCOUNT_VERIFY  = os.environ.get("DISCOUNT_VERIFY", "0") in ("1", "true", "True", "yes")
# Set to a percent (e.g. "15") to run one tier immediately on startup for testing.
DISCOUNT_TEST    = os.environ.get("DISCOUNT_TEST", "0")

# ---- 9 PM heads-up: preview tomorrow's still-empty units (3h before the midnight tier) ----
HEADS_UP_HOUR    = int(os.environ.get("HEADS_UP_HOUR", "21"))               # 21:00 = 9 PM Riyadh
HEADS_UP_CHANNEL = os.environ.get("HEADS_UP_CHANNEL", "discount-heads-up")  # where the preview is posted
HEADS_UP_TEST    = os.environ.get("HEADS_UP_TEST", "0") in ("1", "true", "True", "yes")  # post once on startup

# ---- weekend rule (Thu/Fri): no midnight/noon tiers — a single softer discount at 5:30 PM ----
WEEKEND_DAYS = set(int(x) for x in os.environ.get("WEEKEND_DAYS", "3,4").split(",")
                   if x.strip().isdigit())                                  # 3=Thu, 4=Fri (Mon=0)
WEEKEND_DISCOUNT_PERCENT = float(os.environ.get("WEEKEND_DISCOUNT_PERCENT", "20"))
WEEKEND_DISCOUNT_HOUR    = int(os.environ.get("WEEKEND_DISCOUNT_HOUR", "17"))
WEEKEND_DISCOUNT_MINUTE  = int(os.environ.get("WEEKEND_DISCOUNT_MINUTE", "30"))  # 17:30 = 5:30 PM

# ---- cleaning reminders: nag the open turnover channels until ✅ Cleaning Done ----
REMINDER_START_HOUR = int(os.environ.get("REMINDER_START_HOUR", "12"))  # start at 12 PM
REMINDER_FAST_HOUR  = int(os.environ.get("REMINDER_FAST_HOUR", "15"))   # speed up at 3 PM
REMINDER_END_HOUR   = int(os.environ.get("REMINDER_END_HOUR", "23"))    # stop at 11 PM
REMINDER_SLOW_MIN   = int(os.environ.get("REMINDER_SLOW_MIN", "30"))    # 12 PM–3 PM: every 30 min
REMINDER_FAST_MIN   = int(os.environ.get("REMINDER_FAST_MIN", "15"))    # after 3 PM: every 15 min
OPERATION_ROLE_ID   = os.environ.get("OPERATION_ROLE_ID", "")           # role to ping if no cleaner
OPERATION_ROLE_NAME = os.environ.get("OPERATION_ROLE_NAME", "operation")

# ---- AI guest-message assistant (Claude drafts, a human approves, then it sends) ----
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL       = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
# Smarter model for the few high-touch, personality-heavy messages (manager script +
# empathetic repeat-escalation acks). Low volume, so the extra cost is tiny.
CLAUDE_MODEL_PREMIUM = os.environ.get("CLAUDE_MODEL_PREMIUM", "claude-sonnet-4-6")
ASSISTANT_ENABLED  = os.environ.get("ASSISTANT_ENABLED", "0") in ("1", "true", "True", "yes")
ASSISTANT_CHANNEL  = os.environ.get("ASSISTANT_CHANNEL", "guest-assistant")
ASSISTANT_POLL_MIN = int(os.environ.get("ASSISTANT_POLL_MIN", "2"))   # check inbox every N min
ASSISTANT_SCAN     = int(os.environ.get("ASSISTANT_SCAN", "30"))      # how many recent convos to scan
# Safety: replies are NEVER sent automatically unless you explicitly turn this on later.
ASSISTANT_AUTOSEND = os.environ.get("ASSISTANT_AUTOSEND", "0") in ("1", "true", "True", "yes")
ASSISTANT_DEBUG    = os.environ.get("ASSISTANT_DEBUG", "0") in ("1", "true", "True", "yes")
# Skip the startup "mark everything seen" baseline so the latest unanswered guest
# messages get drafted right away (handy for a first test without sending a new message).
ASSISTANT_TEST     = os.environ.get("ASSISTANT_TEST", "0") in ("1", "true", "True", "yes")
# On startup, messages newer than this many minutes are NOT baselined, so a fresh guest
# message still gets a card even if the bot just restarted/redeployed. Set 0 to baseline all.
ASSISTANT_BASELINE_GRACE_MIN = int(os.environ.get("ASSISTANT_BASELINE_GRACE_MIN", "15"))
# Also draft a reply when the only thing sent AFTER the guest's question is an automated
# welcome/booking message (so guest questions buried under auto-messages still get answered).
# A real human/bot reply after the guest still counts as "answered" and is skipped.
ASSISTANT_ANSWER_PAST_AUTO = os.environ.get("ASSISTANT_ANSWER_PAST_AUTO", "1") in ("1", "true", "True", "yes")
# Outbound messages containing any of these (case-insensitive, '|'-separated) are treated as
# automated, not a real answer. Add your Hostaway welcome/automation phrases here.
AUTO_REPLY_MARKERS = [m.strip() for m in os.environ.get(
    "AUTO_REPLY_MARKERS", "truly delighted|we are truly|delighted by your|we've prepared|we have prepared").split("|") if m.strip()]
# Always draft a card for the guest's latest message, even if the team/automation already
# replied after it. Set 0 to only draft when the guest is unanswered.
ASSISTANT_ALWAYS_DRAFT = os.environ.get("ASSISTANT_ALWAYS_DRAFT", "1") in ("1", "true", "True", "yes")
# Knowledge base: a Discord channel the assistant reads as facts about Ouja. Anyone can add
# facts by typing in it, and the 🧠 Teach button on a card saves corrections here.
KNOWLEDGE_CHANNEL     = os.environ.get("KNOWLEDGE_CHANNEL", "knowledge")
KNOWLEDGE_REFRESH_MIN = int(os.environ.get("KNOWLEDGE_REFRESH_MIN", "5"))
KNOWLEDGE_MAX         = int(os.environ.get("KNOWLEDGE_MAX", "300"))   # facts (messages) to load
# When on, logs each listing's active-status + whether an Airbnb link was found (for tuning).
CATALOG_DEBUG = os.environ.get("CATALOG_DEBUG", "0") in ("1", "true", "True", "yes")
# Pull a real "starting from" nightly price from each unit's calendar (reflects dynamic pricing).
CATALOG_CALENDAR_PRICES = os.environ.get("CATALOG_CALENDAR_PRICES", "1") in ("1", "true", "True", "yes")
# Auto-send: when ON, very simple/safe replies (action="auto") go straight to the guest;
# anything needing approval or a human still posts a card. Default OFF — everything waits
# for approval/edit until you've judged the assistant's quality. Set to 1 to enable later.
ASSISTANT_AUTO     = os.environ.get("ASSISTANT_AUTO", "0") in ("1", "true", "True", "yes")
ASSISTANT_AUTO_CONF = float(os.environ.get("ASSISTANT_AUTO_CONF", "0.85"))  # min confidence to auto-send
# Signature appended to every guest-facing message.
ASSISTANT_SIGNATURE_AR = os.environ.get("ASSISTANT_SIGNATURE_AR", "الدعم الفني - مساعد 🤍")
ASSISTANT_SIGNATURE_EN = os.environ.get("ASSISTANT_SIGNATURE_EN", "Technical Support - Musaid 🤍")
# When a chat escalates to a human, auto-send the guest a holding message.
ASSISTANT_ESC_ACK  = os.environ.get("ASSISTANT_ESC_ACK", "1") in ("1", "true", "True", "yes")
ASSISTANT_ACK_AR   = os.environ.get("ASSISTANT_ACK_AR",
    "حياك الله 🤍 رفعنا موضوعك للقسم المختص، وبيتواصل معك الفريق في أقرب وقت.")
ASSISTANT_ACK_EN   = os.environ.get("ASSISTANT_ACK_EN",
    "Thank you 🤍 We've escalated this to our specialized team and someone will contact you shortly.")
# Escalations go to their own channel, ping the operation team, and re-ping until claimed.
ESCALATION_CHANNEL    = os.environ.get("ESCALATION_CHANNEL", "escalations")
ESCALATION_REPING_MIN = int(os.environ.get("ESCALATION_REPING_MIN", "10"))   # re-ping every N min
ESCALATION_MAX_PINGS  = int(os.environ.get("ESCALATION_MAX_PINGS", "12"))    # stop after this many re-pings
CLAIM_NAMES = [n.strip() for n in os.environ.get(
    "CLAIM_NAMES", "اسيل,فيصل,ماثر,نوره,ناصر,محمد").split(",") if n.strip()]
# When someone claims an escalation, DM them a ready-to-send reply in the owner's warm style.
MANAGER_SCRIPT = os.environ.get("MANAGER_SCRIPT", "1") in ("1", "true", "True", "yes")

BASE = "https://api.hostaway.com/v1"
GOLD = 0xC8A24B

# ---------------- Persistent state (Railway Volume) ----------------
# Mount a Railway Volume at this path so state survives restarts AND redeploys.
STATE_DIR = os.environ.get("STATE_DIR", "/data")

def _state_path(name):
    return os.path.join(STATE_DIR, name)

def _save_json(name, obj):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = _state_path(name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, _state_path(name))   # atomic write
    except Exception as e:
        print(f"state save error ({name}):", e)

def _load_json(name, default):
    try:
        with open(_state_path(name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _state_persistent():
    """True if STATE_DIR looks like a mounted volume (writable & exists)."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        return os.path.isdir(STATE_DIR)
    except Exception:
        return False

HANDLED_FILE = _state_path("handled.json")

# ---------------- Hostaway ----------------
_token = {"value": None}

def get_token(force=False):
    if _token["value"] and not force:
        return _token["value"]
    r = requests.post(
        f"{BASE}/accessTokens",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "client_id": HOSTAWAY_ACCOUNT_ID,
              "client_secret": HOSTAWAY_API_KEY, "scope": "general"},
        timeout=30,
    )
    r.raise_for_status()
    _token["value"] = r.json()["access_token"]
    return _token["value"]

def api_get(path, params=None, _retry=0):
    token = get_token()
    r = requests.get(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Cache-control": "no-cache"},
        params=params or {}, timeout=60,
    )
    if r.status_code == 403 and _retry == 0:        # token expired -> refresh once
        get_token(force=True)
        return api_get(path, params, _retry + 1)
    if r.status_code == 429:                          # rate limited -> brief backoff
        time.sleep(10)
        if _retry < 3:
            return api_get(path, params, _retry + 1)
    r.raise_for_status()
    return r.json()

def api_post(path, body, _retry=0):
    token = get_token()
    r = requests.post(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Cache-control": "no-cache"},
        json=body, timeout=60,
    )
    if r.status_code == 403 and _retry == 0:
        get_token(force=True)
        return api_post(path, body, _retry + 1)
    if r.status_code == 429:
        time.sleep(10)
        if _retry < 3:
            return api_post(path, body, _retry + 1)
    r.raise_for_status()
    return r.json()


def api_put(path, body, _retry=0):
    token = get_token()
    r = requests.put(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Cache-control": "no-cache"},
        json=body, timeout=60,
    )
    if r.status_code == 403 and _retry == 0:
        get_token(force=True)
        return api_put(path, body, _retry + 1)
    if r.status_code == 429:
        time.sleep(10)
        if _retry < 3:
            return api_put(path, body, _retry + 1)
    r.raise_for_status()
    return r.json()

_listings = {"map": {}, "ts": 0}

def get_listings_map():
    """listingMapId -> internal name (cached for 1 hour)."""
    if _listings["map"] and time.time() - _listings["ts"] < 3600:
        return _listings["map"]
    m, limit, offset = {}, 100, 0
    while True:
        data = api_get("/listings", params={"limit": limit, "offset": offset})
        batch = data.get("result", []) or []
        for l in batch:
            m[l.get("id")] = l.get("internalListingName") or l.get("name") or f"unit-{l.get('id')}"
        if len(batch) < limit:
            break
        offset += limit
    _listings["map"], _listings["ts"] = m, time.time()
    return m

def parse_hour(v, default):
    if v is None:
        return default
    s = str(v)
    if ":" in s:
        try: return int(s.split(":")[0])
        except: return default
    try: return int(float(s))
    except: return default

SKIP_STATUSES = {"cancelled", "declined", "expired", "inquiry", "inquirydenied", "inquirytimedout"}

def fetch_upcoming_checkouts():
    """Reservations whose checkout falls within the next HOURS_AHEAD hours."""
    listings = get_listings_map()
    now = datetime.now(TZ)
    window_end = now + timedelta(hours=HOURS_AHEAD)
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()

    out, limit, offset, pages = [], 100, 0, 0
    while pages < 10:
        data = api_get("/reservations", params={
            "departureStartDate": today, "departureEndDate": tomorrow,
            "limit": limit, "offset": offset, "includeResources": 0,
        })
        batch = data.get("result", []) or []
        if not batch:
            break
        for res in batch:
            if (res.get("status") or "").lower() in SKIP_STATUSES:
                continue
            dep = res.get("departureDate")
            if not dep:
                continue
            hour = parse_hour(res.get("checkOutTime"), DEFAULT_CHECKOUT_HOUR)
            try:
                checkout = datetime.strptime(dep[:10], "%Y-%m-%d").replace(
                    hour=min(hour, 23), tzinfo=TZ)
            except ValueError:
                continue
            if now <= checkout <= window_end:
                lm = res.get("listingMapId")
                out.append({
                    "res_id": str(res.get("id")),
                    "listing": listings.get(lm) or res.get("listingName") or f"unit-{lm}",
                    "guest": res.get("guestName") or res.get("guestFirstName") or "Guest",
                    "checkout": checkout,
                })
        if len(batch) < limit:
            break
        offset += limit
        pages += 1
    return out

def _load_discount_state():
    try:
        return json.load(open(DISCOUNT_STATE_FILE, encoding="utf-8"))
    except Exception:
        return {}

def _save_discount_state(st):
    try:
        json.dump(st, open(DISCOUNT_STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass

def apply_discount_tier(pct):
    """Set tonight's price to `pct`% off the ORIGINAL price, for every still-empty unit.
    The original is captured once per day (state file + Hostaway note) so the two tiers
    never compound. Returns (changes, today). Honors DRY-RUN."""
    factor = (100.0 - pct) / 100.0
    today = datetime.now(TZ).date().isoformat()
    state = _load_discount_state()
    state = {today: state.get(today, {})}      # keep only today's record
    day_orig = state[today]
    listings = get_listings_map()
    changes = []
    for lid, name in listings.items():
        lid_s = str(lid)
        try:
            cal = api_get(f"/listings/{lid}/calendar",
                          params={"startDate": today, "endDate": today})
            days = cal.get("result", []) or []
            if not days:
                continue
            d = days[0]
            available = int(d.get("isAvailable", 0) or 0) == 1
            booked = bool(d.get("reservationId"))
            current = d.get("price")
            if not available or booked or not current:
                continue                                   # booked / blocked / no price
            current = float(current)
            # recover tonight's original: remembered state -> Hostaway note -> current
            original = day_orig.get(lid_s)
            if original is None:
                m = re.search(r"ouja-orig:(\d+(?:\.\d+)?)", str(d.get("note") or ""))
                original = float(m.group(1)) if m else current
                day_orig[lid_s] = original
            new_price = round(original * factor)
            if DISCOUNT_FLOOR and new_price < DISCOUNT_FLOOR:
                new_price = int(DISCOUNT_FLOOR)
            if new_price >= current:
                continue                                   # already at/below this level
            if not DISCOUNT_DRY_RUN:
                resp = api_put(f"/listings/{lid}/calendar",
                        {"startDate": today, "endDate": today,
                         "isAvailable": 1, "price": new_price,
                         "note": f"ouja-orig:{int(original)}"})
                if DISCOUNT_VERIFY:
                    try:
                        chk = api_get(f"/listings/{lid}/calendar",
                                      params={"startDate": today, "endDate": today})
                        cd = (chk.get("result") or [{}])[0]
                        actual = cd.get("price")
                        status = resp.get("status") if isinstance(resp, dict) else "?"
                        stuck = "✅ stuck" if str(actual) == str(new_price) else "❌ reverted/ignored"
                        print(f"   VERIFY {name}: requested {new_price}, Hostaway now shows "
                              f"{actual} ({stuck}) · PUT status={status}")
                    except Exception as e:
                        print(f"   VERIFY {name}: read-back failed: {e}")
            changes.append({"name": name, "orig": int(original),
                            "old": int(current), "new": int(new_price)})
        except Exception as e:
            print(f"discount error for {name}: {e}")
    _save_discount_state(state)
    return changes, today

def is_weekend_today():
    return datetime.now(TZ).weekday() in WEEKEND_DAYS

def compute_headsup():
    """List units still empty for TOMORROW night, with the discount they'll actually get."""
    f1 = (100.0 - DISCOUNT_TIER1_PERCENT) / 100.0
    f2 = (100.0 - DISCOUNT_TIER2_PERCENT) / 100.0
    f3 = (100.0 - DISCOUNT_TIER3_PERCENT) / 100.0
    fw = (100.0 - WEEKEND_DISCOUNT_PERCENT) / 100.0
    tomorrow_date = datetime.now(TZ).date() + timedelta(days=1)
    tomorrow = tomorrow_date.isoformat()
    weekend = tomorrow_date.weekday() in WEEKEND_DAYS
    listings = get_listings_map()
    items = []
    for lid, name in listings.items():
        try:
            cal = api_get(f"/listings/{lid}/calendar",
                          params={"startDate": tomorrow, "endDate": tomorrow})
            days = cal.get("result", []) or []
            if not days:
                continue
            d = days[0]
            available = int(d.get("isAvailable", 0) or 0) == 1
            booked = bool(d.get("reservationId"))
            price = d.get("price")
            if not available or booked or not price:
                continue
            price = float(price)
            items.append({"name": name, "price": int(price),
                          "t1": int(round(price * f1)), "t2": int(round(price * f2)),
                          "t3": int(round(price * f3)), "w": int(round(price * fw))})
        except Exception as e:
            print(f"headsup error for {name}: {e}")
    return items, tomorrow, weekend

# ---------------- handled-set persistence ----------------
def load_handled():
    try:
        return set(json.load(open(HANDLED_FILE)))
    except Exception:
        return set()

def save_handled(s):
    try:
        json.dump(list(s), open(HANDLED_FILE, "w"))
    except Exception:
        pass

handled = load_handled()

# ---------------- Discord ----------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!ouja ", intents=intents)

class CleaningDoneView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)   # persistent across restarts

    @discord.ui.button(label="✅ Cleaning Done", style=discord.ButtonStyle.success,
                       custom_id="ouja_cleaning_done")
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"✅ Marked done by {interaction.user.mention}. Closing this channel…",
            ephemeral=False)
        await asyncio.sleep(2)
        try:
            await interaction.channel.delete(reason=f"Cleaning completed by {interaction.user}")
        except Exception as e:
            print("delete error:", e)

def channel_name(internal_name):
    # Discord channel names must be lowercase, no spaces/symbols.
    # "Ouja | B209" -> "ouja-b209". The full name is shown inside the channel.
    return re.sub(r"[^a-z0-9]+", "-", internal_name.lower()).strip("-")[:90] or "unit"

# ---- responsible-person lookup (from assignments.json built off the Excel) ----
try:
    ASSIGNMENTS = json.load(open("assignments.json", encoding="utf-8"))
except Exception as e:
    print("Could not load assignments.json:", e)
    ASSIGNMENTS = {"by_day": {}, "discord_ids": {}}

# Python weekday(): Mon=0 ... Sun=6
ARABIC_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

def norm_unit(s):
    s = str(s).strip().lower().replace("ouja", "").replace("|", "")
    return re.sub(r"[\s\-_]+", " ", s).strip()

def _clip(s, n=18):
    """Trim a unit name so the table columns stay aligned."""
    s = str(s).strip()
    return s if len(s) <= n else s[:n - 1] + "…"

def _fmt_hour(h):
    """24h int -> friendly label, e.g. 0->'12 AM', 12->'12 PM', 18->'6 PM'."""
    suffix = "AM" if h < 12 else "PM"
    return f"{h % 12 or 12} {suffix}"

def parse_topic_res(topic):
    """Reservation id stored in a turnover channel's topic."""
    m = re.search(r"hostaway-res:(\d+)", topic or "")
    return m.group(1) if m else None

def parse_topic_did(topic):
    """Responsible cleaner's Discord id stored in the topic (None if unassigned)."""
    m = re.search(r"did:(\d+)", topic or "")
    return m.group(1) if m else None

def find_operation_role(guild):
    """The role to ping when a unit has no assigned cleaner."""
    if OPERATION_ROLE_ID.isdigit():
        r = guild.get_role(int(OPERATION_ROLE_ID))
        if r:
            return r
    name = OPERATION_ROLE_NAME.lower()
    for r in guild.roles:
        if r.name.lower() == name:
            return r
    return None

def responsible_for(internal_name, checkout_dt):
    """Returns (employee_name, discord_id, arabic_day). Any may be None if no match."""
    day = ARABIC_DAYS[checkout_dt.weekday()]
    emp = ASSIGNMENTS.get("by_day", {}).get(day, {}).get(norm_unit(internal_name))
    did = ASSIGNMENTS.get("discord_ids", {}).get(emp) if emp else None
    return emp, did, day

async def get_category(guild):
    for cat in guild.categories:
        if cat.name == CATEGORY_NAME:
            return cat
    return await guild.create_category(CATEGORY_NAME)

async def get_assistant_category(guild):
    """Category for guest-assistant + escalations. Reuses your existing Operations category."""
    want = ASSISTANT_CATEGORY.lower()
    for cat in guild.categories:
        if cat.name.lower() == want:
            return cat
    return await guild.create_category(ASSISTANT_CATEGORY)

async def ensure_channel(guild, name, category=None):
    """Find a text channel by name (create it if missing) and keep it under `category`."""
    ch = discord.utils.get(guild.text_channels, name=name)
    if ch is None:
        try:
            ch = await guild.create_text_channel(name, category=category)
        except Exception as e:
            print(f"channel create error ({name}):", e)
            return None
    elif category is not None and ch.category_id != category.id:
        try:
            await ch.edit(category=category)      # move existing channel under the category
        except Exception as e:
            print(f"channel move error ({name}):", e)
    return ch

async def sync_checkouts():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("Guild not found — check DISCORD_GUILD_ID and that the bot was invited.")
        return
    category = await get_category(guild)

    # reservation ids that already have a live channel
    existing = set()
    for ch in category.text_channels:
        rid = parse_topic_res(ch.topic)
        if rid:
            existing.add(rid)
    handled.update(existing)

    items = await asyncio.to_thread(fetch_upcoming_checkouts)
    for it in items:
        if it["res_id"] in handled or it["res_id"] in existing:
            continue
        try:
            emp, did, day = responsible_for(it["listing"], it["checkout"])
            # topic carries the reservation id + responsible discord id (for reminders)
            topic = f"hostaway-res:{it['res_id']} did:{did or ''}"
            ch = await guild.create_text_channel(
                channel_name(it["listing"]), category=category, topic=topic)
            embed = discord.Embed(title="🧹 Turnover Ready", color=GOLD)
            embed.add_field(name="Unit", value=it["listing"], inline=False)
            embed.add_field(name="Guest", value=it["guest"], inline=True)
            embed.add_field(name="Checkout",
                            value=it["checkout"].strftime("%a %d %b · %I:%M %p"), inline=True)

            if emp:
                embed.add_field(name="مسؤول التنظيف",
                                value=(f"<@{did}> ({emp})" if did else emp), inline=False)
            embed.set_footer(text="Tap the button below once cleaning is complete to close this channel.")

            content = f"<@{did}> 🧹 وحدة جاهزة للتنظيف" if did else None
            await ch.send(content=content, embed=embed, view=CleaningDoneView(),
                          allowed_mentions=discord.AllowedMentions(users=True, roles=True))
            handled.add(it["res_id"])
            save_handled(handled)
            note = f" -> {emp}" if emp else " (no responsible match — check unit name)"
            print(f"Opened channel for {it['listing']} (res {it['res_id']}){note}")
        except Exception as e:
            print("create error:", e)

@tasks.loop(minutes=POLL_MINUTES)
async def poll_loop():
    try:
        await sync_checkouts()
    except Exception as e:
        print("poll error:", e)

# remembers when each open channel was last pinged (resets on restart, which is fine)
_last_reminder = {}

@tasks.loop(minutes=1)
async def reminder_loop():
    """Nag every open turnover channel until cleaning is marked done.
    12 PM–3 PM: every 30 min. After 3 PM: every 15 min. Quiet outside those hours."""
    now = datetime.now(TZ)
    hour = now.hour
    if hour < REMINDER_START_HOUR or hour >= REMINDER_END_HOUR:
        return
    interval = REMINDER_SLOW_MIN if hour < REMINDER_FAST_HOUR else REMINDER_FAST_MIN
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
    if category is None:
        return
    op_role = find_operation_role(guild)
    live_ids = set()
    for ch in list(category.text_channels):
        if not parse_topic_res(ch.topic):
            continue                      # only turnover channels
        live_ids.add(ch.id)
        last = _last_reminder.get(ch.id)
        if last and (now - last) < timedelta(minutes=interval):
            continue
        did = parse_topic_did(ch.topic)
        if did:
            mention = f"<@{did}>"
        elif op_role:
            mention = op_role.mention
        else:
            mention = f"@{OPERATION_ROLE_NAME}"
        try:
            await ch.send(
                f"{mention} ⏰ تذكير: هالوحدة لسه تحتاج تنظيف — اضغط ✅ Cleaning Done لما تخلص.",
                allowed_mentions=discord.AllowedMentions(users=True, roles=True))
            _last_reminder[ch.id] = now
        except Exception as e:
            print(f"reminder error ({ch.name}):", e)
    # drop timers for channels that no longer exist (cleaning done)
    for cid in list(_last_reminder.keys()):
        if cid not in live_ids:
            _last_reminder.pop(cid, None)

async def post_discount_summary(changes, today, pct, label):
    if not changes:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    category = await get_category(guild)
    channel = await ensure_channel(guild, DISCOUNT_CHANNEL, category)
    if channel is None:
        return
    state = ("🧪 معاينة فقط — ما تغيّر أي سعر"
             if DISCOUNT_DRY_RUN else f"✅ تم تطبيق خصم {int(pct)}٪ من السعر الأصلي")
    lines = "\n".join(f"• {c['name']}: {c['orig']} → {c['new']} ر.س" for c in changes[:60])
    embed = discord.Embed(title=f"💰 {label} · خصم {int(pct)}٪ · {today}",
                          description=lines, color=GOLD)
    embed.set_footer(text=f"{state} · {len(changes)} وحدة فاضية")
    await channel.send(embed=embed)

async def _run_tier(pct, label):
    try:
        changes, today = await asyncio.to_thread(apply_discount_tier, pct)
        mode = "DRY-RUN" if DISCOUNT_DRY_RUN else "LIVE"
        print(f"[{label} {today}] {mode} {pct:.0f}%: {len(changes)} empty units")
        for c in changes:
            print(f"   {c['name']}: orig {c['orig']} -> {c['new']}")
        await post_discount_summary(changes, today, pct, label)
    except Exception as e:
        print(f"{label} error:", e)

@tasks.loop(time=dt_time(hour=DISCOUNT_TIER1_HOUR, tzinfo=TZ))
async def discount_tier1_loop():
    if is_weekend_today():
        print("[Tier 1] Thu/Fri — skipping midnight discount (weekend rule)")
        return
    await _run_tier(DISCOUNT_TIER1_PERCENT, "Tier 1 (midnight)")

@tasks.loop(time=dt_time(hour=DISCOUNT_TIER2_HOUR, tzinfo=TZ))
async def discount_tier2_loop():
    if is_weekend_today():
        print("[Tier 2] Thu/Fri — skipping noon discount (weekend rule)")
        return
    await _run_tier(DISCOUNT_TIER2_PERCENT, "Tier 2 (noon)")

@tasks.loop(time=dt_time(hour=DISCOUNT_TIER3_HOUR, tzinfo=TZ))
async def discount_tier3_loop():
    if is_weekend_today():
        print("[Tier 3] Thu/Fri — skipping evening discount (weekend rule)")
        return
    await _run_tier(DISCOUNT_TIER3_PERCENT, "Tier 3 (6 PM)")

@tasks.loop(time=dt_time(hour=WEEKEND_DISCOUNT_HOUR, minute=WEEKEND_DISCOUNT_MINUTE, tzinfo=TZ))
async def discount_weekend_loop():
    if not is_weekend_today():
        return                       # only fires on Thu/Fri
    await _run_tier(WEEKEND_DISCOUNT_PERCENT, "Weekend (Thu/Fri 5:30 PM)")

def _headsup_table(items, weekend):
    """Build a clean monospace table + an explanatory note for the heads-up preview."""
    if weekend:
        wp = int(WEEKEND_DISCOUNT_PERCENT)
        c1, c2 = f"-{wp}%", "SAVE"
        header = f"{'UNIT':<16}{'NOW':>6}{c1:>6}{c2:>6}"
        rows = [f"{_clip(it['name'], 16):<16}{it['price']:>6}{it['w']:>6}"
                f"{it['price'] - it['w']:>6}" for it in items]
        note = f"Single drop if still empty: **-{wp}% at 5:30 PM** (weekend rule)."
    else:
        p1, p2, p3 = (int(DISCOUNT_TIER1_PERCENT), int(DISCOUNT_TIER2_PERCENT),
                      int(DISCOUNT_TIER3_PERCENT))
        c1, c2, c3 = f"-{p1}%", f"-{p2}%", f"-{p3}%"
        header = f"{'UNIT':<16}{'NOW':>6}{c1:>6}{c2:>6}{c3:>6}"
        rows = [f"{_clip(it['name'], 16):<16}{it['price']:>6}{it['t1']:>6}"
                f"{it['t2']:>6}{it['t3']:>6}" for it in items]
        note = (f"Prices auto-drop if still empty: **-{p1}% at {_fmt_hour(DISCOUNT_TIER1_HOUR)}** → "
                f"**-{p2}% at {_fmt_hour(DISCOUNT_TIER2_HOUR)}** → "
                f"**-{p3}% at {_fmt_hour(DISCOUNT_TIER3_HOUR)}**.")
    sep = "─" * len(header)
    # Prefix each line with a zero-width LEFT-TO-RIGHT MARK so an Arabic unit
    # name can't flip the line's direction and scramble the number columns.
    lines = [header, sep, *rows]
    return note, "\n".join("\u200e" + ln for ln in lines)

async def post_headsup(items, tomorrow, weekend):
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    category = await get_category(guild)
    channel = await ensure_channel(guild, HEADS_UP_CHANNEL, category)
    if channel is None:
        return
    try:
        date_str = datetime.strptime(tomorrow, "%Y-%m-%d").strftime("%a · %d %b %Y")
    except ValueError:
        date_str = tomorrow
    if not items:
        await channel.send(embed=discord.Embed(
            title="📋 Tomorrow's Open Units",
            description=f"**{date_str}**\n\nAll units are booked for tomorrow — nothing to discount. 🎉",
            color=GOLD))
        return
    shown = items[:45]
    extra = len(items) - len(shown)
    note, table = _headsup_table(shown, weekend)
    desc = f"**{date_str}** · **{len(items)} units** still open\n{note}\n```\n{table}\n```"
    if extra > 0:
        desc += f"\n*+{extra} more not shown.*"
    embed = discord.Embed(title="📋 Tomorrow's Open Units", description=desc, color=GOLD)
    embed.set_footer(text="All prices in SAR · preview only — nothing changes until the scheduled time.")
    await channel.send(embed=embed)

@tasks.loop(time=dt_time(hour=HEADS_UP_HOUR, tzinfo=TZ))
async def headsup_loop():
    try:
        items, tomorrow, weekend = await asyncio.to_thread(compute_headsup)
        print(f"[heads-up {tomorrow}] {len(items)} units open for tomorrow "
              f"({'weekend' if weekend else 'weekday'})")
        await post_headsup(items, tomorrow, weekend)
    except Exception as e:
        print("headsup error:", e)

# ====================== AI guest-message assistant ======================
# Claude drafts a reply, a human approves it in Discord, and only then is it sent.
ASSISTANT_RULES = """You are "فيصل", the front-desk assistant for Ouja Residence, a premium short-term \
rental company in Riyadh, Saudi Arabia. You draft replies to guest messages. A human teammate reviews \
every draft before it is sent, so be helpful but stay strictly within your lane.

TONE
- Warm, friendly, professional — Ritz-Carlton hospitality standard.
- Reply in the SAME language the guest used, switching immediately if they switch.
- For Arabic: write CLEAN, modern, natural Saudi Arabic with only a LIGHT local touch — \
warm phrases like "حياك الله"، "تم"، "أبشر"، "بالتوفيق" used naturally and sparingly. \
Do NOT write heavy or folksy Najdi slang. Aim for how a polished, well-spoken Saudi host \
talks — simple, elegant, respectful — not exaggerated dialect.
- Keep replies short, human, and to the point. Never reveal you are an AI unless asked.

CHOOSE ONE OF THREE ACTIONS
- "auto" → a VERY simple, safe, low-risk reply you are highly confident about, where a wrong \
answer would do no harm: greetings, thanks, reassurance, simple confirmations, and basic facts \
that are obvious or that you were explicitly given (e.g. a friendly "حياك الله", "شكراً لك", \
"تم، بالتوفiق"). These get sent to the guest automatically, so only use "auto" when you are sure.
- "reply" → a helpful reply you CAN draft, but a human should approve it first because it is more \
substantive, or you are not fully certain (most amenity/directions/check-in answers fall here).
- "escalate" → matches the MUST-escalate list below. Draft no reply.

WHEN IN DOUBT between "auto" and "reply", pick "reply" — a human approves it before it sends, so it is \
always safe. Only choose "escalate" when the request matches the MUST-escalate list (complaint, dispute, \
refund, booking change, upset guest, security info). A question you simply don't have the answer to \
(like live availability) is NOT a reason to escalate — suggest what you can and point the guest to the \
Airbnb link. Never gamble on "auto".

YOU MAY draft replies (auto or reply) about
- Unit amenities (wifi, parking, pool, kitchen, facilities)
- Check-in / check-out TIMES and the self-entry PROCESS (never the actual code)
- Directions, location, nearby restaurants and areas
- House-rules clarifications
- Greetings, thanks, general hospitality

ARRIVAL GUIDE LINK (important)
- When a guest asks about the location, the address, directions, where to park, the outer/building \
door number, or any arrival detail, point them to the unit's arrival-guide link (it is provided to \
you in the context as "Arrival-guide link for this unit"). Tell them all the details are there.
- Always include the exact link given to you. NEVER invent a link.
- If the link is "NOT AVAILABLE", do NOT make one up — set action to "escalate" instead.
- If the guest says they can't open it or nothing happens, explain it opens an Airbnb warning page \
("you're leaving Airbnb"): they should tap "متابعة" (or "Continue" if their app is in English), \
then tap the guide/directions option. (This is "auto"/"reply" — just a helpful instruction.)

PRE-BOOKING PRIVACY (critical)
- The context gives you "Booking status". If it is NOT CONFIRMED (an inquiry or pre-booking), you \
MUST NOT share the exact location, address, building/door number, or the arrival-guide link — even \
if the guest asks directly. Politely tell them the full location and arrival details are sent right \
after the booking is confirmed. You may still talk about the general area, amenities, and price.
- Only share location and the arrival-guide link when Booking status is CONFIRMED.

SUGGESTING A UNIT / AVAILABILITY  (do NOT escalate these — suggest instead)
- If the guest asks for another/different unit, a bigger/cheaper/smaller one, a unit in another area, \
a unit with a certain feature (balcony, pool, terrace, X bedrooms, etc.), OR simply "do you have a \
unit available today / for these dates?": this is a SUGGESTION task. Use action "reply" (a human \
approves it). It is NOT an escalation.
- FIRST, if you don't already know what they want, ask briefly: preferred area, number of bedrooms, \
and any must-have or budget. If they already told you, skip the questions and suggest right away.
- Then, from the "قائمة وحدات عوجا" in the context, suggest 1-3 matches. For each: name, bedrooms, \
area, the "starting from" nightly price, and the Airbnb link if it is in the list. NEVER invent a link \
or a detail. If nothing matches exactly, suggest the closest and state the differences honestly.
- AVAILABILITY: you do NOT have live availability. Never promise a unit is free. Instead, suggest the \
options and tell the guest to check live availability and book directly from the Airbnb link (the link \
always shows what is open for their dates). Not knowing availability is NEVER a reason to escalate — \
suggest + send them to the link.
- A FEATURE you're not sure about (e.g. whether a unit allows smoking, or has a specific view): if it \
is not in your provided info, suggest the closest units, be honest that you'd confirm that specific \
detail with the team, and keep it action "reply" so a human checks. Do NOT invent the feature.
- Whenever you mention a price, add a short note that prices are approximate and BEFORE tax and the \
platform service fee.
- MIXED message: if a guest asks several things and you can help with some (suggest units, directions, \
amenities) but one part truly needs a human (e.g. extending checkout, a refund), DRAFT a "reply" that \
handles what you can and says you'll check the rest with the team — do not escalate the whole message.

YOU MUST NOT do these — instead set action to "escalate"
- Confirm, modify, cancel, or refund a booking
- Offer any discount, comp, or price change
- Share the door/entry CODE or any building security info
- Share other guests', owners', or internal/financial information
- Handle any complaint, dispute, damage claim, or an upset guest
- Promise late checkout, early check-in, or extra services you cannot verify
- Give legal, medical, or financial advice
- Discuss anything outside hosting / off-topic
- State any fact about the unit you were not given — never invent details
- Anything you are unsure about — when in doubt, escalate; never guess

OUTPUT — respond with ONLY a JSON object, nothing else:
{"action": "auto" | "reply" | "escalate",
 "reply": "the drafted message to the guest IN THE GUEST'S OWN LANGUAGE; empty string if escalating",
 "intent": "short label IN ARABIC, e.g. واي فاي، اتجاهات، تسجيل دخول، تسعير، شكوى، تعديل حجز",
 "sentiment": "ok" | "upset",
 "reason": "one short line IN ARABIC for the human reviewer explaining your choice (the team reads Arabic)",
 "confidence": 0.0-1.0}

IMPORTANT: "reply" stays in the guest's language (Najdi Arabic if they wrote Arabic). But "intent" and \
"reason" must ALWAYS be written in Arabic, because the Ouja team reading these cards speaks Arabic."""

def _msg_is_inbound(m):
    return int(m.get("isIncoming", m.get("incoming", 0)) or 0) == 1

def _msg_time(m):
    return str(m.get("date") or m.get("insertedOn") or m.get("latestMessageDate") or "")

def _parse_msg_dt(s):
    """Parse a Hostaway message timestamp as Riyadh local time. Returns aware dt or None.
    Parsing as TZ is safe for baselining: a tz mismatch can only make a message look OLDER
    (so it gets baselined like before), never wrongly resurrect an old one."""
    s = str(s).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=TZ)
        except Exception:
            pass
    return None

def _looks_automated(body):
    """True if an outbound message looks like an automated welcome/booking message
    (i.e. not a real answer to the guest)."""
    b = (body or "").lower()
    return any(mk.lower() in b for mk in AUTO_REPLY_MARKERS)

_guide_cache = {}

def get_guide_url(listing_id):
    """Pull the arrival-guide link stored in the listing's Custom Fields. Cached per listing."""
    if listing_id in _guide_cache:
        return _guide_cache[listing_id]
    url = None
    try:
        data = api_get(f"/listings/{listing_id}", params={"includeResources": 1})
        listing = data.get("result") or {}
        # 1) look through the listing's custom-field values for a URL
        for key in ("listingCustomFieldValues", "customFieldValues", "customFields"):
            for cf in (listing.get(key) or []):
                v = str(cf.get("value") or "").strip()
                if v.startswith("http"):
                    url = v
                    break
            if url:
                break
        # 2) fallback: scan the whole listing for the guide domain
        if not url:
            blob = json.dumps(listing, ensure_ascii=False)
            m = (re.search(r"https?://[^\s\"']*oujaguide[^\s\"']*", blob)
                 or re.search(r"https?://[^\s\"']*netlify[^\s\"']*", blob))
            if m:
                url = m.group(0)
    except Exception as e:
        print(f"guide url error for listing {listing_id}: {e}")
    _guide_cache[listing_id] = url
    return url

# A booking only counts as "confirmed" (safe to share location/guide) for these statuses.
CONFIRMED_STATUSES = {"new", "modified"}

def get_reservation_status(reservation_id):
    """Return the reservation status (lowercased), or '' if unknown. Not cached — it can change."""
    if not reservation_id:
        return ""
    try:
        data = api_get(f"/reservations/{reservation_id}")
        return (data.get("result", {}) or {}).get("status", "").lower()
    except Exception as e:
        print(f"reservation status error ({reservation_id}):", e)
        return ""

# Knowledge base loaded from the #knowledge Discord channel; injected into every draft.
_knowledge_text = ""

# Units catalog (name · bedrooms · area · base price · Airbnb link) pulled from Hostaway.
_catalog_text = ""
_catalog_ts = 0

def _listing_active(L):
    """False if the listing looks inactive/unlisted (the red 🚫 in Hostaway) — skip those."""
    v = L.get("status")
    if isinstance(v, str) and v.lower() in (
            "inactive", "disabled", "unlisted", "delisted", "deleted", "draft", "paused", "off"):
        return False
    if v in (0, "0", False):
        return False
    for key in ("isActive", "listed", "active", "isListed"):
        if key in L and L.get(key) in (0, "0", False, "false", "False"):
            return False
    return True

def _airbnb_link(L):
    """Best-effort Airbnb listing URL from the listing's channel data."""
    blob = json.dumps(L, ensure_ascii=False)
    m = (re.search(r"https?://[^\s\"']*airbnb\.[^\s\"']*/rooms/\d+", blob)
         or re.search(r"https?://[^\s\"']*airbnb\.[^\s\"']*", blob))
    if m:
        return m.group(0)
    m2 = re.search(r'"airbnb[A-Za-z]*[Ii]d"\s*:\s*"?(\d{5,})"?', blob)
    if m2:
        return f"https://www.airbnb.com/rooms/{m2.group(1)}"
    return ""

def _nightly_from(listing_id):
    """A representative 'starting from' nightly price from the calendar (next ~30 days)."""
    try:
        today = datetime.now(TZ).date()
        data = api_get(f"/listings/{listing_id}/calendar",
                       params={"startDate": today.isoformat(),
                               "endDate": (today + timedelta(days=30)).isoformat()})
        prices = [d.get("price") for d in (data.get("result", []) or [])
                  if d.get("isAvailable", 1) and isinstance(d.get("price"), (int, float))
                  and d.get("price") > 0]
        return min(prices) if prices else None
    except Exception as e:
        print(f"price fetch error ({listing_id}):", e)
        return None

def load_catalog(force=False):
    """Build a units catalog from Hostaway listings (cached 1h). Used to suggest alternatives.
    Skips inactive/unlisted listings (the red 🚫)."""
    global _catalog_text, _catalog_ts
    if not force and _catalog_text and (time.time() - _catalog_ts) < 3600:
        return
    try:
        data = api_get("/listings", params={"limit": 100, "includeResources": 1})
        rows, skipped = [], 0
        for L in (data.get("result", []) or []):
            name = (L.get("internalListingName") or L.get("name") or "").strip()
            if not name:
                continue
            if not _listing_active(L):
                skipped += 1
                if CATALOG_DEBUG:
                    print(f"  catalog SKIP (inactive): {name} · status={L.get('status')!r}")
                continue
            parts = [name]
            beds = L.get("bedroomsNumber")
            if beds:
                parts.append(f"{beds} غرفة نوم")
            area = (L.get("city") or L.get("address") or "").strip()
            if area:
                parts.append(area)
            price = (_nightly_from(L.get("id")) if CATALOG_CALENDAR_PRICES else None) or L.get("price")
            if price:
                parts.append(f"تبدأ من ~{round(price)} ر.س/الليلة")
            link = _airbnb_link(L)
            if link:
                parts.append(link)
            rows.append(" · ".join(parts))
            if CATALOG_DEBUG:
                print(f"  catalog OK: {name} · status={L.get('status')!r} · link={'yes' if link else 'no'}")
        _catalog_text = "\n".join(rows)[:6000]
        _catalog_ts = time.time()
        print(f"catalog: loaded {len(rows)} active units (skipped {skipped} inactive)")
    except Exception as e:
        print("catalog load error:", e)

# Hints that the guest is asking about a different unit, availability, or a feature
# (any of these injects the units catalog so the bot SUGGESTS instead of escalating).
_ALT_HINTS = [
    # another / different / bigger / cheaper
    "ثاني", "ثانيه", "ثانية", "بديل", "غيره", "غيرها", "اكبر", "أكبر", "ارخص", "أرخص",
    "اصغر", "أصغر", "خيار", "خيارات", "وحده ثاني", "شقه ثاني",
    "another", "other", "different", "bigger", "cheaper", "smaller", "option", "alternativ",
    # availability / is there a unit
    "متاح", "متاحه", "متاحة", "متوفر", "متوفره", "متوفرة", "توفر", "التوفر", "فاضي", "فاضيه",
    "فاضية", "شاغر", "شاغره", "فيه وحده", "فيه شقة", "فيه شقه", "عندكم وحده", "عندكم شقة",
    "available", "availab", "vacant", "vacancy", "any unit", "do you have a unit",
    # features that point to a different unit
    "بلكون", "تراس", "مسبح", "تدخين", "حوش", "استوديو", "غرفتين", "ثلاث غرف", "ثلاث غرفه",
    "balcony", "terrace", "pool", "smoking", "studio", "two bedroom", "2 bedroom",
    "three bedroom", "3 bedroom",
]

def claude_draft(guest_name, unit, history_text, guide_url=None, confirmed=False, dates=None):
    """Call Claude to draft a reply. Returns parsed dict or None on failure."""
    if not ANTHROPIC_API_KEY:
        print("assistant: ANTHROPIC_API_KEY not set")
        return None
    status_line = ("Booking status: CONFIRMED" if confirmed
                   else "Booking status: NOT CONFIRMED (inquiry / pre-booking)")
    guide_line = (f"Arrival-guide link for this unit: {guide_url}"
                  if (guide_url and confirmed)
                  else "Arrival-guide link for this unit: NOT AVAILABLE / do not share")
    dates_line = (f"\nتواريخ الحجز: {dates[0]} إلى {dates[1]}"
                  if dates and dates[0] else "")
    facts = _knowledge_text.strip()
    facts_block = (f"معلومات معتمدة عن عوجا (استخدمها كمصدر الحقيقة وصحّح أي تعارض):\n{facts}\n\n"
                   if facts else "")
    want_catalog = _catalog_text and any(h in history_text.lower() for h in _ALT_HINTS)
    catalog_block = (
        "قائمة وحدات عوجا للاقتراح عند طلب بديل أو سؤال عن التوفّر:\n" + _catalog_text + "\n\n"
        "تعليمات الاقتراح:\n"
        "- أول ما يطلب شقة/وحدة ثانية أو بديل أو يسأل (فيه وحده متاحه؟ / عندكم شي فاضي؟): اسأله بلطف "
        "عن اللي يبيه (أي حي، كم غرفة، وش المهم له) إلا إذا قالها، وبعدها اقترح طول.\n"
        "- طابق من القائمة واقترح 1-3 خيارات. لكل خيار: الاسم، عدد الغرف، المنطقة، السعر التقريبي لليلة "
        "(يبدأ من)، ورابط Airbnb لو موجود. لا تخترع رابط أو تفاصيل.\n"
        "- لو ما فيه مطابق تماماً، اقترح أقرب خيار ووضّح الفروقات بصراحة.\n"
        "- التوفّر: إنت ما تعرف التوفّر المباشر. لا توعد إن وحدة فاضية — بدّل: اعرض الخيارات ووجّهه يتأكد "
        "ويحجز من رابط Airbnb (الرابط يبيّن المتاح لتواريخه). **السؤال عن التوفّر مو سبب للتصعيد إطلاقاً** "
        "— اقترح ووجّهه للرابط.\n"
        "- ميزة مو متأكد منها (مثلاً: الوحدة مسموح فيها تدخين؟ فيها بلكون؟) وما هي عندك بالمعلومات: اقترح "
        "أقرب الوحدات، وقل بصراحة إنك بتتأكد من هالتفصيلة مع الفريق، وخلها رد (يراجعه إنسان). لا تخترع.\n"
        "- إذا ذكرت سعر، أضف تنويه: الأسعار تقريبية وقبل الضريبة ورسوم المنصة.\n\n"
        ) if want_catalog else ""
    user = (f"{facts_block}{catalog_block}Guest name: {guest_name}\nUnit: {unit}\n"
            f"{status_line}\n{guide_line}{dates_line}\n\n"
            f"Conversation so far (oldest first, last line is the guest's new message):\n"
            f"{history_text}\n\nDraft your reply as the JSON object.")
    model = CLAUDE_MODEL_PREMIUM if want_catalog else CLAUDE_MODEL
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 700, "system": ASSISTANT_RULES,
                  "messages": [{"role": "user", "content": user}]},
            timeout=60,
        )
        r.raise_for_status()
        blocks = r.json().get("content", []) or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print("claude_draft error:", e)
        return None

def claude_text(system, user, max_tokens=600, model=None):
    """Plain-text Claude call (no JSON). Returns the text or None."""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model or CLAUDE_MODEL, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=60,
        )
        r.raise_for_status()
        blocks = r.json().get("content", []) or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip() or None
    except Exception as e:
        print("claude_text error:", e)
        return None

def claude_escalation_ack(guest, unit, history, guest_text):
    """An empathetic, problem-specific holding message for a repeat escalation."""
    sys = ("أنت تكتب رسالة طمأنة قصيرة لضيف في عوجا تصعّد موضوعه مرة ثانية وهو لا يزال ينتظر أو منزعج. "
           "اكتب بأسلوب سعودي نجدي دافئ وراقٍ: اعترف بمشكلته تحديداً، تفهّم شعوره، اعتذر بصدق، "
           "وطمّنه إن الفريق المختص يشتغل على موضوعه الحين وبيتواصل معه قريب جداً. "
           "لا تكتبها كأنها قالب آلي مكرر. لو الضيف يكتب إنجليزي رد بالإنجليزي. اكتب نص الرسالة فقط.")
    user = (f"الوحدة: {unit}\nالضيف: {guest}\nالمحادثة:\n{history}\n\n"
            f"آخر رسالة من الضيف: {guest_text}")
    return claude_text(sys, user, 500, model=CLAUDE_MODEL_PREMIUM) or claude_text(sys, user, 500)

def claude_manager_script(guest, unit, history, guest_text, reason, manager_name):
    """A ready-to-send reply in the owner's warm/charismatic voice for whoever claims."""
    sys = (f"أنت تكتب رسالة جاهزة بينسخها {manager_name} (مدير العقار في عوجا) ويرسلها للضيف مباشرة. "
           "الأسلوب: سعودي نجدي دافئ، واثق، وكاريزما عالية مثل صاحب البيت اللي يهتم بضيفه شخصياً. "
           f"الرسالة لازم: تحيي الضيف بحرارة، تعرّف إن {manager_name} مدير العقار وتولّى الموضوع بنفسه، "
           "تذكر إن الشباب (الفريق) بلّغوه عن مشكلته، تلخّص مشكلته باختصار عشان يحس إنه مسموع، "
           "تتفهّم وتعتذر بصدق، وتطمّنه بعبارات دافئة (مثل: أبشر بالي يسرّ خاطرك يا طويل العمر) إن الموضوع بينحل. "
           "طبيعية مهب قالب جامد. لو الضيف يكتب إنجليزي رد بالإنجليزي. اكتب نص الرسالة فقط بدون أي شرح.")
    user = (f"الوحدة: {unit}\nالضيف: {guest}\nسبب التصعيد: {reason}\nالمحادثة:\n{history}\n\n"
            f"آخر رسالة من الضيف: {guest_text}")
    return claude_text(sys, user, 700, model=CLAUDE_MODEL_PREMIUM) or claude_text(sys, user, 700)

def fetch_new_guest_messages(seen, debug=False):
    """Scan recent conversations, fetch each one's messages, and return new inbound
    guest messages (the guest's latest message that hasn't been answered/seen)."""
    listings = get_listings_map()
    out = []
    try:
        data = api_get("/conversations", params={"limit": ASSISTANT_SCAN, "includeResources": 1})
    except Exception as e:
        print("assistant fetch error:", e)
        return out
    convos = data.get("result", []) or []
    if debug:
        print(f"assistant DEBUG: /conversations returned {len(convos)} conversations")
    for c in convos:
        cid = c.get("id")
        if not cid:
            continue
        try:
            md = api_get(f"/conversations/{cid}/messages")
            msgs = md.get("result", []) or []
        except Exception as e:
            if debug:
                print(f"  conv {cid}: messages fetch error: {e}")
            continue
        if not msgs:
            continue
        msgs = sorted(msgs, key=_msg_time)
        # the guest's most recent (inbound) message
        guest_idx = next((i for i in range(len(msgs) - 1, -1, -1)
                          if _msg_is_inbound(msgs[i])), None)
        if guest_idx is None:
            continue                                    # guest never messaged
        guest_msg = msgs[guest_idx]
        mid = str(guest_msg.get("id"))
        after = msgs[guest_idx + 1:]                     # anything sent after the guest spoke
        # "answered" = a real reply exists after the guest (not just an automated welcome)
        answered = bool(after) and not all(
            _looks_automated(m.get("body") or "") for m in after)
        if debug:
            print(f"  conv {cid}: {len(msgs)} msgs · guest_last_id={mid} · after={len(after)} · "
                  f"answered={answered} · body={(guest_msg.get('body') or '')[:50]!r}")
        if mid in seen:
            continue                                    # already drafted for this message
        if not ASSISTANT_ALWAYS_DRAFT:
            if answered:
                continue                                # a real human/bot reply already exists
            if after and not ASSISTANT_ANSWER_PAST_AUTO:
                continue                                # only auto-replies after, feature off
        lm = c.get("listingMapId")
        unit = listings.get(lm) or c.get("listingName") or f"unit-{lm}"
        guest = c.get("recipientName") or c.get("guestName") or "Guest"
        res = c.get("reservation") or {}
        history = "\n".join(
            f"{'Guest' if _msg_is_inbound(m) else 'Host'}: {(m.get('body') or '').strip()}"
            for m in msgs[-8:] if (m.get("body") or "").strip())
        out.append({
            "conversation_id": cid, "message_id": mid, "guest": guest, "unit": unit,
            "listing_id": lm,
            "reservation_id": c.get("reservationId") or res.get("id"),
            "res_status": (res.get("status") or "").lower(),
            "comm_type": guest_msg.get("communicationType") or "email",
            "guest_text": (guest_msg.get("body") or "").strip(), "history": history,
            "last_time": _msg_time(guest_msg),
            "checkin": res.get("arrivalDate"), "checkout": res.get("departureDate"),
        })
    if debug:
        print(f"assistant DEBUG: {len(out)} new inbound guest message(s) to draft")
    return out

def _has_arabic(s):
    return any("\u0600" <= ch <= "\u06ff" for ch in str(s))

def with_signature(text):
    """Append the support signature, language-matched to the message."""
    sig = ASSISTANT_SIGNATURE_AR if _has_arabic(text) else ASSISTANT_SIGNATURE_EN
    return f"{str(text).rstrip()}\n\n{sig}"

def send_guest_message(conversation_id, body, comm_type="email"):
    return api_post(f"/conversations/{conversation_id}/messages",
                    {"body": with_signature(body), "communicationType": comm_type})

# pending escalations: discord_message_id -> {channel_id, guest, unit, last_ping, attempts, claimed_by}
_escalations = {}
_esc_ack_count = {}     # conversation_id -> how many escalation acks we've sent
_claimed_convos = set() # conversation_ids a human has claimed (stop auto-acks)

class NameSelect(discord.ui.Select):
    """The name picker shown after tapping Claim."""
    def __init__(self, channel_id, message_id):
        super().__init__(placeholder="اختر اسمك للاستلام…", min_values=1, max_values=1,
                         options=[discord.SelectOption(label=n) for n in CLAIM_NAMES])
        self.target_channel_id = channel_id
        self.target_message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        name = self.values[0]
        esc = _escalations.get(self.target_message_id)
        if esc and esc.get("claimed_by"):
            await interaction.response.edit_message(
                content=f"⚠️ التصعيد مستلم مسبقاً بواسطة {esc['claimed_by']}.", view=None)
            return
        if esc:
            esc["claimed_by"] = name
            if esc.get("conversation_id"):
                _claimed_convos.add(esc["conversation_id"])   # stop auto-acks
        try:
            ch = interaction.client.get_channel(self.target_channel_id)
            msg = await ch.fetch_message(self.target_message_id)
            embed = msg.embeds[0] if msg.embeds else discord.Embed()
            embed.add_field(name="✅ تم الاستلام", value=f"بواسطة **{name}**", inline=False)
            embed.color = 0x3BA55D
            done = ClaimView()
            for c in done.children:
                c.disabled = True
            await msg.edit(embed=embed, view=done)
        except Exception as e:
            print("claim edit error:", e)
        tail = " — جهّزت لك رد جاهز تحت 👇" if (esc and MANAGER_SCRIPT) else ""
        await interaction.response.edit_message(
            content=f"✅ استلمت التصعيد باسم **{name}**.{tail}", view=None)
        # show the claimer a ready-to-send reply (private to them, right here in the channel)
        if esc and MANAGER_SCRIPT:
            script = await asyncio.to_thread(
                claude_manager_script, esc.get("guest"), esc.get("unit"),
                esc.get("history", ""), esc.get("guest_text", ""), esc.get("reason", ""), name)
            if script:
                dm = (f"🎯 رد جاهز للضيف **{esc.get('guest')} · {esc.get('unit')}** "
                      f"(انسخ والصق ثم أرسل):\n\n{script}")
            else:
                dm = ("⚠️ تعذّر توليد الرد الجاهز — تواصل مع الضيف مباشرة.")
            await interaction.followup.send(dm, ephemeral=True)

class ClaimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)   # persistent across restarts

    @discord.ui.button(label="🙋 أخذ المهمة / Claim", style=discord.ButtonStyle.primary,
                       custom_id="ouja_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        esc = _escalations.get(interaction.message.id)
        if esc and esc.get("claimed_by"):
            await interaction.response.send_message(
                f"⚠️ مستلم مسبقاً بواسطة {esc['claimed_by']}.", ephemeral=True)
            return
        picker = discord.ui.View(timeout=300)
        picker.add_item(NameSelect(interaction.channel.id, interaction.message.id))
        await interaction.response.send_message("اختر اسمك للاستلام:", view=picker, ephemeral=True)

class EditModal(discord.ui.Modal, title="تعديل الرد قبل الإرسال"):
    def __init__(self, item, draft, message_id=None):
        super().__init__()
        self.item = item
        self.message_id = message_id
        self.box = discord.ui.TextInput(label="الرد للضيف", style=discord.TextStyle.paragraph,
                                        default=draft, max_length=1800)
        self.add_item(self.box)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)   # ack now; sending can be slow
        text = str(self.box.value).strip()
        try:
            await asyncio.to_thread(send_guest_message, self.item["conversation_id"], text,
                                    self.item["comm_type"])
            try:
                msg = await interaction.channel.fetch_message(self.message_id)
                done = ApproveView()
                for c in done.children:
                    c.disabled = True
                await msg.edit(view=done)
            except Exception:
                pass
            _pending_replies.pop(self.message_id, None)
            await interaction.followup.send(
                f"✅ تم الإرسال (بعد التعديل) بواسطة {interaction.user.mention} "
                f"للضيف **{self.item['guest']}**.")
        except Exception as e:
            await interaction.followup.send(f"⚠️ فشل الإرسال: {e}", ephemeral=True)

# pending approval cards: discord_message_id -> {"item": item, "draft": draft}
_pending_replies = {}

def _recover_from_embed(message):
    """Rebuild (item, draft) from the card itself, so buttons work even after a full redeploy."""
    try:
        if not message.embeds:
            return None, None
        emb = message.embeds[0]
        foot = (emb.footer.text or "") if emb.footer else ""
        m = re.search(r"#(\d+)·(\S+)", foot)
        if not m:
            return None, None
        title = emb.title or ""
        guest = "الضيف"
        if "💬" in title:
            t = title.split("💬", 1)[1].strip()
            guest = (t.split("·", 1)[0].strip() or guest)
        draft = None
        for f in emb.fields:
            if "الرد المقترح" in (f.name or ""):
                draft = (f.value or "").strip()
        if not draft or draft == "—":
            return None, None
        return {"conversation_id": int(m.group(1)), "comm_type": m.group(2), "guest": guest}, draft
    except Exception as e:
        print("embed recover error:", e)
        return None, None

async def load_knowledge(guild):
    """Read the #knowledge channel and build the facts text the assistant uses."""
    global _knowledge_text
    ch = discord.utils.get(guild.text_channels, name=KNOWLEDGE_CHANNEL)
    if ch is None:
        return
    try:
        facts = []
        async for m in ch.history(limit=KNOWLEDGE_MAX, oldest_first=True):
            body = (m.content or "").strip()
            if body and not body.startswith(("/", "!")):   # skip commands
                facts.append(f"- {body}")
        _knowledge_text = "\n".join(facts)[:8000]
        print(f"knowledge: loaded {len(facts)} fact(s) from #{KNOWLEDGE_CHANNEL}")
    except Exception as e:
        print("knowledge load error:", e)

async def save_fact(guild, text):
    """Append a fact to the #knowledge channel (creating it if needed) and refresh."""
    ch = await ensure_channel(guild, KNOWLEDGE_CHANNEL, await get_assistant_category(guild))
    if ch is None:
        return False
    try:
        await ch.send(text[:1900])
        await load_knowledge(guild)
        return True
    except Exception as e:
        print("save fact error:", e)
        return False

class TeachModal(discord.ui.Modal, title="🧠 علّم المساعد معلومة"):
    def __init__(self, message_id, item=None):
        super().__init__()
        self.message_id = message_id
        self.item = item
        self.topic = discord.ui.TextInput(label="الموضوع (اختياري)", required=False,
                                          placeholder="مثال: واي فاي وحدة C08 / موقف السيارة",
                                          max_length=120)
        self.fact = discord.ui.TextInput(label="المعلومة الصحيحة", style=discord.TextStyle.paragraph,
                                         placeholder="اكتب المعلومة الصح اللي تبي المساعد يعرفها ويستخدمها.",
                                         max_length=900)
        self.add_item(self.topic)
        self.add_item(self.fact)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        topic = str(self.topic.value).strip()
        fact = str(self.fact.value).strip()
        line = f"**{topic}**: {fact}" if topic else fact
        ok = await save_fact(interaction.guild, line)
        if not ok:
            await interaction.followup.send("⚠️ تعذّر حفظ المعلومة.", ephemeral=True)
            return
        # regenerate this card's draft using the new knowledge (if we still have context)
        data = _pending_replies.get(self.message_id)
        item = (data or {}).get("item") or self.item
        regen = False
        if item and item.get("history"):
            try:
                result = await asyncio.to_thread(
                    claude_draft, item["guest"], item["unit"], item["history"],
                    (data or {}).get("guide"), (data or {}).get("confirmed", False))
                reply = (result or {}).get("reply", "").strip()
                if reply:
                    msg = await interaction.channel.fetch_message(self.message_id)
                    emb = msg.embeds[0]
                    fields = emb.fields
                    emb.clear_fields()
                    for f in fields:
                        emb.add_field(name=f.name,
                                      value=(reply[:1024] if "الرد المقترح" in f.name else f.value),
                                      inline=f.inline)
                    await msg.edit(embed=emb, view=ApproveView())
                    if data:
                        data["draft"] = reply
                    else:
                        _pending_replies[self.message_id] = {"item": item, "draft": reply,
                                                             "guide": (data or {}).get("guide"),
                                                             "confirmed": (data or {}).get("confirmed", False)}
                    regen = True
            except Exception as e:
                print("teach regen error:", e)
        note = "✅ حفظت المعلومة" + (" وأعدت صياغة الرد بها 👆" if regen else " — بتنطبق على الردود الجاية.")
        await interaction.followup.send(note, ephemeral=True)

class ConfirmActionView(discord.ui.View):
    """Ephemeral 'are you sure?' shown before a Send or Reject actually happens."""
    def __init__(self, action, channel_id, message_id):
        super().__init__(timeout=120)
        self.action = action            # "send" or "reject"
        self.channel_id = channel_id
        self.message_id = message_id

    async def _disable_card(self, interaction):
        try:
            ch = interaction.client.get_channel(self.channel_id)
            card = await ch.fetch_message(self.message_id)
            done = ApproveView()
            for c in done.children:
                c.disabled = True
            await card.edit(view=done)
        except Exception as e:
            print("confirm card edit error:", e)

    @discord.ui.button(label="✅ نعم، أكمل", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.action == "send":
            data = _pending_replies.get(self.message_id)
            item = (data or {}).get("item")
            draft = (data or {}).get("draft")
            if not item:
                try:
                    ch = interaction.client.get_channel(self.channel_id)
                    card = await ch.fetch_message(self.message_id)
                    item, draft = _recover_from_embed(card)
                except Exception:
                    item = None
            if not item:
                await interaction.response.edit_message(
                    content="⚠️ هذا الكرت قديم — تعامل مع الرسالة يدوياً.", view=None)
                return
            await interaction.response.edit_message(content="⏳ جاري الإرسال…", view=None)
            try:
                await asyncio.to_thread(send_guest_message, item["conversation_id"], draft,
                                        item["comm_type"])
                await self._disable_card(interaction)
                _pending_replies.pop(self.message_id, None)
                await interaction.followup.send(
                    f"✅ تم الإرسال بواسطة {interaction.user.mention} للضيف **{item['guest']}**.")
            except Exception as e:
                await interaction.followup.send(f"⚠️ فشل الإرسال: {e}", ephemeral=True)
        else:   # reject
            await self._disable_card(interaction)
            _pending_replies.pop(self.message_id, None)
            await interaction.response.edit_message(content="🗑️ تم التجاهل.", view=None)
            await interaction.followup.send(f"🗑️ تم التجاهل بواسطة {interaction.user.mention}.")

    @discord.ui.button(label="✖️ تراجع", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="تمام، ما سويت شي. الكرت زي ما هو 👍", view=None)

class ApproveView(discord.ui.View):
    def __init__(self, item=None, draft=None):
        super().__init__(timeout=None)   # persistent — survives bot restarts
        self.item = item
        self.draft = draft

    def _resolve(self, interaction):
        data = _pending_replies.get(interaction.message.id)
        if data:
            return data["item"], data["draft"]
        if self.item:
            return self.item, self.draft     # same-session fallback
        return _recover_from_embed(interaction.message)   # rebuild after a redeploy

    @discord.ui.button(label="✅ إرسال", style=discord.ButtonStyle.success, custom_id="ouja_send")
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        item, draft = self._resolve(interaction)
        if not item:
            await interaction.response.send_message(
                "⚠️ هذا الكرت قديم (انعاد تشغيل البوت) — تجاهله وتعامل مع الرسالة يدوياً.",
                ephemeral=True)
            return
        preview = (draft or "")[:300]
        await interaction.response.send_message(
            f"📤 متأكد تبي ترسل هذا الرد للضيف **{item['guest']}**؟\n\n>>> {preview}",
            view=ConfirmActionView("send", interaction.channel.id, interaction.message.id),
            ephemeral=True)

    @discord.ui.button(label="✏️ تعديل وإرسال", style=discord.ButtonStyle.primary, custom_id="ouja_edit")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        item, draft = self._resolve(interaction)
        if not item:
            await interaction.response.send_message(
                "⚠️ هذا الكرت قديم (انعاد تشغيل البوت) — تجاهله وتعامل يدوياً.", ephemeral=True)
            return
        await interaction.response.send_modal(EditModal(item, draft, interaction.message.id))

    @discord.ui.button(label="🗑️ رفض", style=discord.ButtonStyle.danger, custom_id="ouja_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🗑️ متأكد تبي ترفض هذا الكرت وتتجاهله؟",
            view=ConfirmActionView("reject", interaction.channel.id, interaction.message.id),
            ephemeral=True)

    @discord.ui.button(label="🧠 علّم", style=discord.ButtonStyle.secondary, custom_id="ouja_teach")
    async def teach(self, interaction: discord.Interaction, button: discord.ui.Button):
        item, _ = self._resolve(interaction)
        await interaction.response.send_modal(TeachModal(interaction.message.id, item))

_assistant_seen = set()

_SENTIMENT_AR = {"ok": "عادي", "upset": "غاضب/منزعج"}

async def post_assistant_card(channel, item, result, guide=None, confirmed=False):
    g = item["guest"]
    intent = result.get("intent", "—")
    sentiment = result.get("sentiment", "ok")
    sent_ar = _SENTIMENT_AR.get(sentiment, sentiment)
    conf = float(result.get("confidence", 0) or 0)
    action = result.get("action", "escalate")
    reply = (result.get("reply") or "").strip()
    escalate = action == "escalate" or sentiment == "upset" or conf < 0.55

    # ---- needs a human: tell the guest it's escalated, then alert the team ----
    if escalate:
        embed = discord.Embed(title=f"🚨 تصعيد · {g} · {item['unit']}", color=0xD64545)
        embed.add_field(name="📩 الضيف يقول", value=(item["guest_text"] or "—")[:1000], inline=False)
        embed.add_field(name="🔴 يحتاج تدخل بشري",
                        value=result.get("reason", "تم التصعيد — تعامل معه يدوياً."), inline=False)
        cid = item["conversation_id"]
        if cid in _claimed_convos:
            embed.add_field(name="🙋 مستلمة",
                            value="الموضوع مستلم من أحد الفريق — ما أرسلنا رد تلقائي.", inline=False)
        elif ASSISTANT_ESC_ACK:
            _esc_ack_count[cid] = _esc_ack_count.get(cid, 0) + 1
            n = _esc_ack_count[cid]
            static = ASSISTANT_ACK_AR if _has_arabic(item["guest_text"]) else ASSISTANT_ACK_EN
            if n == 1:
                ack = static                       # first time: quick holding message
            else:                                  # repeat: empathetic, problem-specific
                ack = await asyncio.to_thread(claude_escalation_ack, g, item["unit"],
                                              item["history"], item["guest_text"]) or static
            try:
                await asyncio.to_thread(send_guest_message, cid, ack, item["comm_type"])
                embed.add_field(name="📤 تم إبلاغ الضيف",
                                value=("رسالة طمأنة متعاطفة (متابعة)" if n > 1
                                       else "رسالة طمأنة إنه تم تصعيد طلبه للقسم المختص."),
                                inline=False)
            except Exception as e:
                embed.add_field(name="⚠️ تعذّر إبلاغ الضيف", value=str(e), inline=False)
        embed.set_footer(text=f"النوع: {intent} · المشاعر: {sent_ar} · الثقة: {conf} · "
                              f"يعاد التنبيه كل {ESCALATION_REPING_MIN} دقيقة لين يستلمه أحد")
        # post to the dedicated escalations channel and @mention the operation team
        guild = channel.guild
        esc_channel = await ensure_channel(guild, ESCALATION_CHANNEL,
                                           await get_assistant_category(guild))
        target = esc_channel or channel
        op_role = find_operation_role(guild)
        mention = op_role.mention if op_role else f"@{OPERATION_ROLE_NAME}"
        try:
            msg = await target.send(content=f"{mention} 🚨 تصعيد جديد يحتاج استلام",
                                    embed=embed, view=ClaimView(),
                                    allowed_mentions=discord.AllowedMentions(roles=True))
            _escalations[msg.id] = {"channel_id": target.id, "guest": g, "unit": item["unit"],
                                    "conversation_id": item["conversation_id"],
                                    "guest_text": item["guest_text"],
                                    "reason": result.get("reason", ""), "history": item["history"],
                                    "last_ping": time.time(), "attempts": 0, "claimed_by": None}
        except Exception as e:
            print("escalation post error:", e)
        return

    # ---- very simple & high-confidence: send automatically, then post an FYI card ----
    can_auto = (ASSISTANT_AUTO and action == "auto" and sentiment == "ok"
                and conf >= ASSISTANT_AUTO_CONF and reply)
    if can_auto:
        try:
            await asyncio.to_thread(send_guest_message, item["conversation_id"], reply,
                                    item["comm_type"])
            embed = discord.Embed(title=f"💬 {g} · {item['unit']}", color=0x3BA55D)
            embed.add_field(name="📩 الضيف يقول", value=(item["guest_text"] or "—")[:1000], inline=False)
            embed.add_field(name="✅ تم الرد تلقائياً", value=reply[:1000], inline=False)
            embed.set_footer(text=f"النوع: {intent} · الثقة: {conf} · رد تلقائي (للعلم)")
            await channel.send(embed=embed)
            return
        except Exception as e:
            print("auto-send failed, falling back to approval:", e)
            # fall through to the approval card if the send failed

    # ---- needs approval: draft + buttons ----
    embed = discord.Embed(title=f"💬 {g} · {item['unit']}", color=GOLD)
    embed.add_field(name="📩 الضيف يقول", value=(item["guest_text"] or "—")[:1024], inline=False)
    embed.add_field(name="✍️ الرد المقترح", value=(reply or "—")[:1024], inline=False)
    embed.set_footer(text=f"النوع: {intent} · الثقة: {conf} · راجعه قبل الإرسال · التوقيع يُضاف "
                          f"تلقائياً · #{item['conversation_id']}·{item['comm_type']}")
    sent = await channel.send(embed=embed, view=ApproveView(item, reply))
    _pending_replies[sent.id] = {"item": item, "draft": reply, "guide": guide, "confirmed": confirmed}

@tasks.loop(minutes=ASSISTANT_POLL_MIN)
async def assistant_loop():
    if not ASSISTANT_ENABLED:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    channel = await ensure_channel(guild, ASSISTANT_CHANNEL,
                                   await get_assistant_category(guild))
    if channel is None:
        return
    try:
        items = await asyncio.to_thread(fetch_new_guest_messages, _assistant_seen, ASSISTANT_DEBUG)
    except Exception as e:
        print("assistant_loop fetch error:", e)
        return
    for it in items:
        _assistant_seen.add(it["message_id"])
        if not it["guest_text"]:
            continue
        status = it.get("res_status") or await asyncio.to_thread(
            get_reservation_status, it.get("reservation_id"))
        confirmed = status in CONFIRMED_STATUSES
        guide = (await asyncio.to_thread(get_guide_url, it.get("listing_id"))
                 if (confirmed and it.get("listing_id")) else None)
        result = await asyncio.to_thread(
            claude_draft, it["guest"], it["unit"], it["history"], guide, confirmed,
            (it.get("checkin"), it.get("checkout")))
        if not result:
            continue
        try:
            await post_assistant_card(channel, it, result, guide, confirmed)
        except Exception as e:
            print("assistant card error:", e)

@tasks.loop(minutes=1)
async def escalation_reping_loop():
    """Re-ping the operation team about any escalation that hasn't been claimed yet."""
    if not _escalations:
        return
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        return
    op_role = find_operation_role(guild)
    mention = op_role.mention if op_role else f"@{OPERATION_ROLE_NAME}"
    now = time.time()
    for mid, esc in list(_escalations.items()):
        if esc.get("claimed_by") or esc["attempts"] >= ESCALATION_MAX_PINGS:
            continue
        if (now - esc["last_ping"]) < ESCALATION_REPING_MIN * 60:
            continue
        ch = bot.get_channel(esc["channel_id"])
        if ch is None:
            continue
        try:
            ref = discord.MessageReference(message_id=mid, channel_id=esc["channel_id"],
                                           fail_if_not_exists=False)
            await ch.send(f"{mention} ⏰ لسه ما تم استلام التصعيد — **{esc['guest']} · {esc['unit']}**. "
                          f"اضغط 🙋 أخذ المهمة.",
                          reference=ref, allowed_mentions=discord.AllowedMentions(roles=True))
            esc["last_ping"] = now
            esc["attempts"] += 1
        except Exception as e:
            print("reping error:", e)

@tasks.loop(minutes=KNOWLEDGE_REFRESH_MIN)
async def knowledge_loop():
    guild = bot.get_guild(GUILD_ID)
    if guild is not None:
        await load_knowledge(guild)
    await asyncio.to_thread(load_catalog)   # refreshes only if >1h old

def load_state():
    """Restore in-memory state from the volume so nothing is lost across restarts/redeploys."""
    global _assistant_seen, _pending_replies, _escalations, _esc_ack_count, _claimed_convos
    try:
        _assistant_seen = set(_load_json("seen.json", []))
        _pending_replies = {int(k): v for k, v in _load_json("pending.json", {}).items()}
        _escalations = {int(k): v for k, v in _load_json("escalations.json", {}).items()}
        _esc_ack_count = {int(k): v for k, v in _load_json("ack_count.json", {}).items()}
        _claimed_convos = set(int(x) for x in _load_json("claimed.json", []))
        if _assistant_seen or _pending_replies or _escalations:
            print(f"state: restored {len(_assistant_seen)} seen · {len(_pending_replies)} cards · "
                  f"{len(_escalations)} escalations · {len(_claimed_convos)} claimed")
    except Exception as e:
        print("state load error:", e)

def persist_state():
    _save_json("seen.json", list(_assistant_seen)[-20000:])
    _save_json("pending.json", {str(k): v for k, v in _pending_replies.items()})
    _save_json("escalations.json", {str(k): v for k, v in _escalations.items()})
    _save_json("ack_count.json", {str(k): v for k, v in _esc_ack_count.items()})
    _save_json("claimed.json", list(_claimed_convos))

@tasks.loop(seconds=60)
async def persist_loop():
    await asyncio.to_thread(persist_state)

@bot.event
async def on_ready():
    load_state()                       # restore seen/cards/escalations from the volume FIRST
    bot.add_view(CleaningDoneView())   # re-bind button handlers after a restart
    bot.add_view(ClaimView())          # re-bind escalation claim buttons after a restart
    bot.add_view(ApproveView())        # re-bind guest-reply approval buttons after a restart
    # On first start, mark older inbox messages as already-seen so the assistant doesn't
    # replay old backlog — but KEEP messages from the last few minutes so a fresh guest
    # message still gets a card even if the bot just restarted/redeployed.
    # (After the first run, _assistant_seen is restored from the volume above, so this
    #  whole block is skipped and NOTHING is ever re-baselined or lost.)
    if ASSISTANT_ENABLED and not ASSISTANT_TEST and not _assistant_seen:
        try:
            now = datetime.now(TZ)
            grace = ASSISTANT_BASELINE_GRACE_MIN * 60
            kept = 0
            for it in await asyncio.to_thread(fetch_new_guest_messages, set(), False):
                dt = _parse_msg_dt(it.get("last_time"))
                recent = dt is not None and 0 <= (now - dt).total_seconds() <= grace
                if recent and grace > 0:
                    kept += 1            # leave unseen -> gets a card on the next poll
                else:
                    _assistant_seen.add(it["message_id"])
            print(f"assistant: baselined {len(_assistant_seen)} old conversations, "
                  f"{kept} recent kept for follow-up (grace={ASSISTANT_BASELINE_GRACE_MIN}m)")
        except Exception as e:
            print("assistant baseline error:", e)
    print(f"Logged in as {bot.user}. Watching for checkouts every {POLL_MINUTES} min.")
    print(f"Weekday tiers (Riyadh): {DISCOUNT_TIER1_PERCENT:.0f}% at {DISCOUNT_TIER1_HOUR:02d}:00, "
          f"{DISCOUNT_TIER2_PERCENT:.0f}% at {DISCOUNT_TIER2_HOUR:02d}:00, "
          f"{DISCOUNT_TIER3_PERCENT:.0f}% at {DISCOUNT_TIER3_HOUR:02d}:00 "
          f"{'(DRY-RUN)' if DISCOUNT_DRY_RUN else '(LIVE)'}")
    print(f"Weekend rule (Thu/Fri): {WEEKEND_DISCOUNT_PERCENT:.0f}% at "
          f"{WEEKEND_DISCOUNT_HOUR:02d}:{WEEKEND_DISCOUNT_MINUTE:02d} only")
    print(f"Heads-up preview at {HEADS_UP_HOUR:02d}:00 -> #{HEADS_UP_CHANNEL}")
    print(f"Cleaning reminders: every {REMINDER_SLOW_MIN} min "
          f"{REMINDER_START_HOUR:02d}:00–{REMINDER_FAST_HOUR:02d}:00, then every "
          f"{REMINDER_FAST_MIN} min until {REMINDER_END_HOUR:02d}:00")
    print(f"AI assistant: {'ON' if ASSISTANT_ENABLED else 'OFF'} · model={CLAUDE_MODEL} · "
          f"premium={CLAUDE_MODEL_PREMIUM} · "
          f"auto-send simple={'ON' if ASSISTANT_AUTO else 'OFF'} · "
          f"escalation-ack={'ON' if ASSISTANT_ESC_ACK else 'OFF'} -> #{ASSISTANT_CHANNEL}")
    if not poll_loop.is_running():
        poll_loop.start()
    if not reminder_loop.is_running():
        reminder_loop.start()
    if not discount_tier1_loop.is_running():
        discount_tier1_loop.start()
    if not discount_tier2_loop.is_running():
        discount_tier2_loop.start()
    if not discount_tier3_loop.is_running():
        discount_tier3_loop.start()
    if not discount_weekend_loop.is_running():
        discount_weekend_loop.start()
    if not headsup_loop.is_running():
        headsup_loop.start()
    if ASSISTANT_ENABLED:
        guild0 = bot.get_guild(GUILD_ID)
        if guild0 is not None:
            await load_knowledge(guild0)
        await asyncio.to_thread(load_catalog, True)
    if not assistant_loop.is_running():
        assistant_loop.start()
    if not escalation_reping_loop.is_running():
        escalation_reping_loop.start()
    if not persist_loop.is_running():
        persist_loop.start()
    if ASSISTANT_ENABLED and not knowledge_loop.is_running():
        knowledge_loop.start()
    if HEADS_UP_TEST:
        print("HEADS_UP_TEST=1 — posting a heads-up preview now (test run)")
        try:
            items, tomorrow, weekend = await asyncio.to_thread(compute_headsup)
            await post_headsup(items, tomorrow, weekend)
        except Exception as e:
            print("test heads-up error:", e)
    if DISCOUNT_TEST not in ("0", "", "false", "False", "no"):
        try:
            pct = (DISCOUNT_TIER1_PERCENT if DISCOUNT_TEST in ("1", "true", "True", "yes")
                   else float(DISCOUNT_TEST))
        except ValueError:
            pct = DISCOUNT_TIER1_PERCENT
        print(f"DISCOUNT_TEST — running a {pct:.0f}% tier now "
              f"({'DRY-RUN' if DISCOUNT_DRY_RUN else 'LIVE'})")
        await _run_tier(pct, "Test (startup)")

if __name__ == "__main__":
    missing = [k for k in ("HOSTAWAY_ACCOUNT_ID", "HOSTAWAY_API_KEY", "DISCORD_TOKEN", "DISCORD_GUILD_ID")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit("Missing environment variables: " + ", ".join(missing))
    bot.run(DISCORD_TOKEN)
