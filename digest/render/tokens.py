# -*- coding: utf-8 -*-
"""digest.render.tokens — the design tokens sampled from the KAFD 5.04 memo (brief §3.2).
Single source: nothing else in the package declares a colour, and
tests/test_digest_render.py fails on any hex in the rendered CSS that is not here."""

TOKENS = {
    "ink":      "#0B1A2E",   # deep navy — dark pages, headline ink on paper
    "ink-2":    "#122944",   # top of the navy gradient
    "ink-3":    "#1D3048",   # card surface on navy
    "paper":    "#F7F4EE",   # warm cream — the default page
    "white":    "#FFFFFF",
    "line":     "#ECEAE5",
    "mute":     "#6B7280",   # derived: ink at ~55% on paper (the one added token)
    "gold":     "#C6A15B",   # the eyebrow rule, the single accent
    "gold-2":   "#D9C194",
    "blue":     "#1F4E79",   # neutral data series
    "green":    "#1F6F55",   # "in your favour"
    "green-bg": "#E6EFEC",
    "red":      "#B23A34",   # "against you"
    "red-bg":   "#F9F1F0",
}

PAGE_W_PT, PAGE_H_PT = 810, 1440          # the memo's mobile page, 9:16
STORY_W, STORY_H = 1080, 1920             # Instagram / TikTok story
STORY_CSS_W, STORY_CSS_H = 540, 960       # rendered at deviceScaleFactor 2
QR_MIN_MM = 22                             # printed minimum (brief §7)


def css_root():
    return ":root{" + ";".join("--%s:%s" % (k, v) for k, v in TOKENS.items()) + "}"


def hexes():
    return {v.lower() for v in TOKENS.values()}
