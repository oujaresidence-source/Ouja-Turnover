#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot Guide import CLI (also runnable from the dashboard button).

    python3 tools/guide_import.py [csv_path] [--no-media]

Reads supabase_export_listings.csv → guide_units in brain.db, mirrors the
Google-Drive photos into $STATE_DIR/guide_media/, matches Hostaway listings
when HOSTAWAY_* env is set, and prints the owner report (failures included).
Idempotent — safe to re-run; the Netlify site keeps working regardless."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guide import importer  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    csv_path = args[0] if args else "supabase_export_listings.csv"
    fetch_media = "--no-media" not in sys.argv
    lm = {}
    if os.environ.get("HOSTAWAY_API_KEY"):
        try:
            import bot
            lm = bot.get_listings_map() or {}
        except Exception as e:
            print("Hostaway match skipped:", e)
    media_dir = os.path.join(os.environ.get("STATE_DIR", "/data"), "guide_media")
    rep = importer.import_csv(csv_path, media_dir=media_dir, listings_map=lm,
                              fetch_media=fetch_media)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if rep["media_failed"]:
        print("\n⚠️  %d photo link(s) could not be mirrored (dead/private Drive links)."
              % len(rep["media_failed"]))
        print("   The page still shows them via the original Drive link when public.")
    if rep["unmatched"]:
        print("\n⚠️  %d unit(s) without an exact Hostaway name match — link them "
              "later in the dashboard Guide tab:" % len(rep["unmatched"]))
        for n in rep["unmatched"]:
            print("   ·", n)


if __name__ == "__main__":
    main()
