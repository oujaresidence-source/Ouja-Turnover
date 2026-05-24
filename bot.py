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
from datetime import datetime, timedelta
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
DEFAULT_CHECKOUT_HOUR = int(os.environ.get("DEFAULT_CHECKOUT_HOUR", "12"))

BASE = "https://api.hostaway.com/v1"
GOLD = 0xC8A24B
HANDLED_FILE = "handled.json"

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

def channel_name(internal_name, checkout_dt):
    base = re.sub(r"[^a-z0-9]+", "-", internal_name.lower()).strip("-")[:80] or "unit"
    return f"{base}-{checkout_dt.strftime('%b%d').lower()}"

async def get_category(guild):
    for cat in guild.categories:
        if cat.name == CATEGORY_NAME:
            return cat
    return await guild.create_category(CATEGORY_NAME)

async def sync_checkouts():
    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("Guild not found — check DISCORD_GUILD_ID and that the bot was invited.")
        return
    category = await get_category(guild)

    # reservation ids that already have a live channel
    existing = set()
    for ch in category.text_channels:
        if ch.topic and ch.topic.startswith("hostaway-res:"):
            existing.add(ch.topic.split(":", 1)[1])
    handled.update(existing)

    items = await asyncio.to_thread(fetch_upcoming_checkouts)
    for it in items:
        if it["res_id"] in handled or it["res_id"] in existing:
            continue
        try:
            ch = await guild.create_text_channel(
                channel_name(it["listing"], it["checkout"]),
                category=category, topic=f"hostaway-res:{it['res_id']}")
            embed = discord.Embed(title=f"🧹 Turnover — {it['listing']}", color=GOLD)
            embed.add_field(name="Guest", value=it["guest"], inline=True)
            embed.add_field(name="Checkout",
                            value=it["checkout"].strftime("%a %d %b · %I:%M %p"), inline=True)
            embed.set_footer(text="Tap the button below once cleaning is complete to close this channel.")
            await ch.send(embed=embed, view=CleaningDoneView())
            handled.add(it["res_id"])
            save_handled(handled)
            print(f"Opened channel for {it['listing']} (res {it['res_id']})")
        except Exception as e:
            print("create error:", e)

@tasks.loop(minutes=POLL_MINUTES)
async def poll_loop():
    try:
        await sync_checkouts()
    except Exception as e:
        print("poll error:", e)

@bot.event
async def on_ready():
    bot.add_view(CleaningDoneView())   # re-bind button handlers after a restart
    print(f"Logged in as {bot.user}. Watching for checkouts every {POLL_MINUTES} min.")
    if not poll_loop.is_running():
        poll_loop.start()

if __name__ == "__main__":
    missing = [k for k in ("HOSTAWAY_ACCOUNT_ID", "HOSTAWAY_API_KEY", "DISCORD_TOKEN", "DISCORD_GUILD_ID")
               if not os.environ.get(k)]
    if missing:
        raise SystemExit("Missing environment variables: " + ", ".join(missing))
    bot.run(DISCORD_TOKEN)
