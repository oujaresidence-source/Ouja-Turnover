# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
  OUJA — OWNER REPORT RENDERER          ***  FROZEN. DO NOT EDIT.  ***
═══════════════════════════════════════════════════════════════════════════
  This file owns 100% of the visual output: fonts, colours, spacing, CSS,
  SVG chart geometry, page layout, PDF pipeline.

  It has been visually verified and passes the overflow + chart-clip audits.
  Editing ANYTHING in this file — a colour, a pt value, an SVG coordinate —
  will change the look of every report Ouja has ever issued.

  There is exactly one supported way to use this file:

      from ouja_render import render_report
      render_report(cfg_dict, "out.pdf")

  `cfg_dict` must satisfy REPORT_SCHEMA below. Build your data pipeline to
  produce that dict. DO NOT modify this renderer to fit your data.
═══════════════════════════════════════════════════════════════════════════
"""
import base64, pathlib
from playwright.sync_api import sync_playwright

FONT_DIR = pathlib.Path(__file__).parent / "fonts"

# The exact keys render_report() consumes. Missing key => KeyError => no PDF.
REPORT_SCHEMA = [
    "UNIT", "OWNER", "REPORT", "ASSET", "MARKET_YIELD", "RENT_FREEZE",
    "EJAR", "MONTHS", "COSTS", "FURNISHING", "CHANNELS", "BOOKING_BEHAVIOUR",
    "COMP_SET", "GUEST", "FACTORS", "RISKS", "PROJECTION", "ACTIONS", "SOURCES",
]

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════
def sar(n, dec=0):
    return f"{n:,.{dec}f}"

def pct(x, dec=1):
    return f"{x*100:.{dec}f}%"

def fonts_css():
    css, wmap = [], {"Light":300,"Regular":400,"Medium":500,"SemiBold":600,"Bold":700,"Text":450}
    for f in sorted(FONT_DIR.glob("*.woff2")):
        fam = "Plex Arabic" if "Arabic" in f.name else "Plex"
        w = wmap.get(f.stem.split("-")[-1], 400)
        b64 = base64.b64encode(f.read_bytes()).decode()
        css.append(f"@font-face{{font-family:'{fam}';font-weight:{w};font-style:normal;"
                   f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return "\n".join(css)


# ══════════════════════════════════════════════════════════════
#  CSS  — DESIGN TOKENS. FROZEN.
# ══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
:root{
 --paper:#FFFDF9; --cream:#F7F2E7; --cream2:#EFE8D9;
 --ink:#1B1915; --ink2:#4A443B; --muted:#8C8477;
 --gold:#B4924A; --goldl:#D9C48A; --rule:#E3DBC8;
 --pos:#2E6B4F; --warn:#B5722A; --neg:#A4433A; --neu:#6E6659;
}
@page{size:A4;margin:0}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font-family:'Plex','Plex Arabic',sans-serif;color:var(--ink);background:var(--paper);
     font-size:9.4pt;line-height:1.5;font-variant-numeric:tabular-nums}
.ar{font-family:'Plex Arabic',sans-serif;direction:rtl;unicode-bidi:isolate}
.page{width:210mm;height:297mm;padding:15mm 14mm 13mm;position:relative;
      page-break-after:always;overflow:hidden;background:var(--paper)}
.page:last-child{page-break-after:auto}

/* running header / footer */
.rh{display:flex;justify-content:space-between;align-items:baseline;
    border-bottom:.6pt solid var(--rule);padding-bottom:4pt;margin-bottom:11pt}
.rh .l{font-size:7pt;letter-spacing:.13em;text-transform:uppercase;color:var(--gold);font-weight:600}
.rh .r{font-size:7pt;color:var(--muted)}
.rf{position:absolute;left:14mm;right:14mm;bottom:8mm;display:flex;justify-content:space-between;
    border-top:.6pt solid var(--rule);padding-top:4pt;font-size:6.8pt;color:var(--muted)}

/* section titles */
.sec{margin-bottom:9pt}
.sec .n{font-size:7pt;color:var(--gold);letter-spacing:.16em;font-weight:600;margin-bottom:2pt}
.sec .t{display:flex;justify-content:space-between;align-items:baseline;gap:14pt}
.sec .en{font-size:15pt;font-weight:600;letter-spacing:-.01em;line-height:1.15}
.sec .arh{font-size:14.5pt;font-weight:600;font-family:'Plex Arabic';direction:rtl;line-height:1.25}
.sec .rule{height:2pt;background:var(--gold);width:34pt;margin-top:6pt}

h3.sub{font-size:8pt;letter-spacing:.1em;text-transform:uppercase;color:var(--ink2);
       font-weight:600;margin:11pt 0 5pt;border-bottom:.5pt solid var(--rule);padding-bottom:3pt}
h3.sub span{float:right;font-family:'Plex Arabic';direction:rtl;text-transform:none;letter-spacing:0;font-size:9pt}

p{margin-bottom:6pt}
p.arp{font-family:'Plex Arabic';direction:rtl;text-align:right;line-height:1.75}
.bi{display:grid;grid-template-columns:1fr 1fr;gap:12pt;margin-bottom:7pt}
.bi .e{font-size:9pt;line-height:1.55}
.bi .a{font-family:'Plex Arabic';direction:rtl;text-align:right;font-size:9pt;line-height:1.75}

/* KPI tiles */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:7pt;margin:9pt 0}
.kpi{background:var(--cream);border:.5pt solid var(--rule);border-top:2pt solid var(--gold);
     border-radius:2pt;padding:8pt 8pt 7pt}
.kpi .k{font-size:6.6pt;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:600}
.kpi .ka{font-size:8pt;font-family:'Plex Arabic';direction:rtl;color:var(--ink2);margin-bottom:3pt}
.kpi .v{font-size:17pt;font-weight:600;letter-spacing:-.02em;line-height:1.1}
.kpi .s{font-size:6.8pt;color:var(--muted);margin-top:2pt}
.kpi.hero{background:var(--ink);border-color:var(--ink);border-top-color:var(--gold)}
.kpi.hero .k,.kpi.hero .ka,.kpi.hero .s{color:#C8C0B0}
.kpi.hero .v{color:var(--goldl)}

/* tables */
table{width:100%;border-collapse:collapse;font-size:8.4pt;margin:5pt 0 8pt}
th{text-align:left;padding:5pt 6pt;background:var(--cream2);font-weight:600;
   border-bottom:.8pt solid var(--gold);font-size:7.2pt;letter-spacing:.05em;text-transform:uppercase;vertical-align:bottom}
th .ta{display:block;font-family:'Plex Arabic';direction:rtl;text-transform:none;letter-spacing:0;
       font-size:8pt;font-weight:500;color:var(--ink2)}
td{padding:4.6pt 6pt;border-bottom:.5pt solid var(--rule);vertical-align:top}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.ar{font-family:'Plex Arabic';direction:rtl;text-align:right}
tr.tot td{border-top:1pt solid var(--ink);border-bottom:none;font-weight:600;background:var(--cream);padding-top:6pt}
tr.grand td{background:var(--ink);color:var(--goldl);font-weight:600;border:none;padding:7pt 6pt;font-size:9.2pt}
tr.sub-t td{background:var(--cream2);font-weight:600}
td.neg{color:var(--neg)}
.tag{display:inline-block;padding:1pt 5pt;border-radius:8pt;font-size:6.6pt;font-weight:600;
     letter-spacing:.05em;text-transform:uppercase;white-space:nowrap}
.t-pos{background:#E4EFE9;color:var(--pos)} .t-neg{background:#F5E4E2;color:var(--neg)}
.t-warn{background:#F7EBDC;color:var(--warn)} .t-neu{background:var(--cream2);color:var(--neu)}

/* callout */
.call{background:var(--cream);border-left:2.5pt solid var(--gold);border-radius:1pt;
      padding:7.5pt 10pt;margin:7pt 0}
.call.dark{background:var(--ink);border-left-color:var(--gold);color:#EDE7DA}
.call .h{font-size:7pt;letter-spacing:.13em;text-transform:uppercase;color:var(--gold);font-weight:600;margin-bottom:4pt}
.call p{margin-bottom:4pt;font-size:8.8pt}
.call p:last-child{margin-bottom:0}
.call .a{font-family:'Plex Arabic';direction:rtl;text-align:right;line-height:1.75}

.chart{width:100%;height:auto;display:block;margin:6pt 0}
.ax{font-size:8.5px;fill:#8C8477;font-family:'Plex'}
.ax2{font-size:8px;fill:#8C8477;font-family:'Plex','Plex Arabic'}
.vl{font-size:9.5px;fill:#1B1915;font-weight:600;font-family:'Plex'}
.vl2{font-size:8.5px;fill:#2E6B4F;font-weight:600;font-family:'Plex'}
.lg{font-size:9px;fill:#4A443B;font-family:'Plex','Plex Arabic'}
.rl-en{font-size:9.5px;fill:#4A443B;font-family:'Plex'}
.rl-ar{font-size:10px;fill:#1B1915;font-weight:600;font-family:'Plex Arabic';direction:rtl}
.bv{font-size:11px;fill:#1B1915;font-weight:600;font-family:'Plex'}
.dl{font-size:9.5px;fill:#2E6B4F;font-weight:600;font-family:'Plex','Plex Arabic'}
.il{font-size:12px;fill:#1B1915;font-weight:700;font-family:'Plex'}
.il-ar{font-size:9px;fill:#8C8477;font-family:'Plex Arabic';direction:rtl}
.isub{font-size:8.5px;fill:#FFFDF9;font-family:'Plex'}
.ejl{font-size:9px;fill:#A4433A;font-weight:600;font-family:'Plex','Plex Arabic'}
.gl{font-size:10px;fill:#1B1915;font-weight:600;font-family:'Plex','Plex Arabic'}

/* cover */
.cover{background:var(--ink);color:#EDE7DA;height:297mm;padding:0;display:flex;flex-direction:column}
.cover .band{height:5mm;background:linear-gradient(90deg,var(--gold) 0%,var(--goldl) 100%)}
.cover .body{flex:1;padding:24mm 20mm 0;display:flex;flex-direction:column}
.cover .mark{font-size:26pt;font-weight:600;letter-spacing:.22em;color:var(--goldl)}
.cover .mark-ar{font-size:20pt;font-family:'Plex Arabic';direction:rtl;color:#EDE7DA;margin-top:1mm}
.cover .tagline{font-size:7.5pt;letter-spacing:.28em;text-transform:uppercase;color:#8C8477;margin-top:3mm}
.cover .mid{margin-top:auto;margin-bottom:16mm}
.cover .kicker{font-size:8pt;letter-spacing:.2em;text-transform:uppercase;color:var(--gold);font-weight:600;margin-bottom:5mm}
.cover h1{font-size:31pt;font-weight:300;letter-spacing:-.02em;line-height:1.12;color:#FFFDF9}
.cover h1 b{font-weight:600;color:var(--goldl)}
.cover h1.arh{font-family:'Plex Arabic';direction:rtl;font-size:27pt;margin-top:4mm;line-height:1.4}
.cover .hr{height:1pt;background:#3A3730;margin:9mm 0 7mm}
.cover .meta{display:grid;grid-template-columns:repeat(2,1fr);gap:6mm 10mm}
.cover .meta .l{font-size:6.8pt;letter-spacing:.16em;text-transform:uppercase;color:#8C8477;margin-bottom:1.5mm}
.cover .meta .v{font-size:10.5pt;color:#EDE7DA}
.cover .meta .v.a{font-family:'Plex Arabic';direction:rtl}
.cover .foot{background:#131210;padding:6mm 20mm;display:flex;justify-content:space-between;font-size:7pt;color:#6E6659}

.toc{list-style:none}
.toc li{display:flex;justify-content:space-between;align-items:baseline;gap:8pt;
        padding:6.5pt 0;border-bottom:.5pt solid var(--rule)}
.toc .no{color:var(--gold);font-weight:600;width:22pt;font-size:8.5pt}
.toc .en{flex:1;font-size:9.6pt;font-weight:500}
.toc .a{font-family:'Plex Arabic';direction:rtl;font-size:9.6pt;color:var(--ink2);text-align:right;flex:1}
.toc .pg{color:var(--muted);font-size:8.5pt;width:20pt;text-align:right}

ul.bul{list-style:none;margin:4pt 0}
ul.bul li{padding:3pt 0 3pt 12pt;position:relative;font-size:8.6pt;border-bottom:.4pt dotted var(--rule)}
ul.bul li:before{content:"—";position:absolute;left:0;color:var(--gold)}
ul.bul.a li{padding:3pt 12pt 3pt 0;text-align:right;font-family:'Plex Arabic';direction:rtl;line-height:1.7}
ul.bul.a li:before{left:auto;right:0}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14pt}
.note{font-size:7pt;color:var(--muted);line-height:1.45;margin-top:2.5pt}
.note.a{font-family:'Plex Arabic';direction:rtl;text-align:right}
.mono{font-variant-numeric:tabular-nums}
.dense td{padding:3.4pt 6pt}
.dense th{padding:4pt 6pt}
.dense ul.bul li{padding:2.4pt 0 2.4pt 12pt;font-size:8.2pt}
.dense ul.bul.a li{padding:2.4pt 12pt 2.4pt 0}
.dense table{margin:4pt 0 6pt}
.dense h3.sub{margin:8pt 0 4pt}
.dense .call{padding:7pt 10pt;margin:6pt 0}
"""



def render_report(cfg: dict, out_path) -> pathlib.Path:
    """Render the 17-page bilingual owner report. cfg must satisfy REPORT_SCHEMA."""
    missing = [k for k in REPORT_SCHEMA if k not in cfg]
    if missing:
        raise KeyError(f"cfg is missing required keys: {missing}")

    UNIT              = cfg["UNIT"]
    OWNER             = cfg["OWNER"]
    REPORT            = cfg["REPORT"]
    ASSET             = cfg["ASSET"]
    MARKET_YIELD      = cfg["MARKET_YIELD"]
    RENT_FREEZE       = cfg["RENT_FREEZE"]
    EJAR              = cfg["EJAR"]
    MONTHS            = cfg["MONTHS"]
    COSTS             = cfg["COSTS"]
    FURNISHING        = cfg["FURNISHING"]
    CHANNELS          = cfg["CHANNELS"]
    BOOKING_BEHAVIOUR = cfg["BOOKING_BEHAVIOUR"]
    COMP_SET          = cfg["COMP_SET"]
    GUEST             = cfg["GUEST"]
    FACTORS           = cfg["FACTORS"]
    RISKS             = cfg["RISKS"]
    PROJECTION        = cfg["PROJECTION"]
    ACTIONS           = cfg["ACTIONS"]
    SOURCES           = cfg["SOURCES"]

    # ══════════════════════════════════════════════════════════════
    #  DERIVED METRICS
    # ══════════════════════════════════════════════════════════════
    avail   = sum(m[2] for m in MONTHS)
    booked  = sum(m[3] for m in MONTHS)
    gross   = sum(m[4] for m in MONTHS)
    occ     = booked / avail
    adr     = gross / booked
    revpar  = gross / avail

    channel_fees = COSTS["channel_fees"]
    net_rental   = gross - channel_fees
    mgmt_fee     = round(net_rental * COSTS["mgmt_fee_pct"])
    opex_total   = sum(o[2] for o in COSTS["opex"])
    owner_net    = net_rental - mgmt_fee - opex_total
    owner_margin = owner_net / gross

    # --- Ejar long-term lease alternative, netted down ---------------
    ej_gross   = EJAR["annual_rent"]
    ej_broker  = round(ej_gross * EJAR["broker_pct"])
    ej_vacancy = round(ej_gross * EJAR["vacancy_pct"])
    ej_maint   = EJAR["owner_maintenance"]
    ej_admin   = EJAR["admin_fees"]
    ej_net     = ej_gross - ej_broker - ej_vacancy - ej_maint - ej_admin

    # --- STR annualised (H1 actual + H2 base forecast) ---------------
    h2_base    = PROJECTION["h2_2026"]["base"]
    fy_gross   = gross + h2_base
    h2_channel = round(h2_base * PROJECTION["channel_pct"])
    h2_net_rev = h2_base - h2_channel
    h2_mgmt    = round(h2_net_rev * COSTS["mgmt_fee_pct"])
    h2_opex    = PROJECTION["opex_annual"] - opex_total
    h2_owner   = h2_net_rev - h2_mgmt - h2_opex
    fy_owner   = owner_net + h2_owner

    delta_abs  = fy_owner - ej_net
    delta_pct  = delta_abs / ej_net
    multiple   = fy_gross / ej_gross

    # --- Comp set & indices ------------------------------------------
    cs_adr = sum(c[2] for c in COMP_SET) / len(COMP_SET)
    cs_occ = sum(c[3] for c in COMP_SET) / len(COMP_SET)
    cs_rp  = sum(c[2] * c[3] for c in COMP_SET) / len(COMP_SET)
    MPI = occ / cs_occ * 100
    ARI = adr / cs_adr * 100
    RGI = revpar / cs_rp * 100

    # --- YIELD / RETURN ON CAPITAL ------------------------------------
    PRICE      = ASSET["purchase_price"]
    CAPITAL    = PRICE + (FURNISHING["capex"] if FURNISHING["owner_funded"] else 0)

    ej_gross_y = ej_gross / PRICE          # gross yield, annual lease
    ej_net_y   = ej_net   / PRICE          # net   yield, annual lease
    str_gross_y = fy_gross / PRICE         # gross yield, short-term
    str_net_y   = fy_owner / PRICE         # net   yield, short-term (on property price)

    pb_ejar = PRICE / ej_net               # payback, years — annual lease
    pb_str  = CAPITAL / fy_owner           # payback, years — short-term
    pb_gain = pb_ejar - pb_str

    # --- 5-year cumulative under the Riyadh rent freeze ----------------
    FREEZE_YRS = [2026, 2027, 2028, 2029, 2030]
    GROWTH = 0.05                          # assumed STR net growth p.a. after 2027

    # --- Projection net figures ---------------------------------------
    def to_owner_net(g):
        nr = g - round(g * PROJECTION["channel_pct"])
        return round(nr - round(nr * COSTS["mgmt_fee_pct"]) - PROJECTION["opex_annual"])

    fy26 = {k: gross + v for k, v in PROJECTION["h2_2026"].items()}
    fy26_net = {"low":  owner_net + to_owner_net(PROJECTION["h2_2026"]["low"]) + (PROJECTION["opex_annual"] - h2_opex) - opex_total,
                "base": fy_owner,
                "high": owner_net + to_owner_net(PROJECTION["h2_2026"]["high"]) + (PROJECTION["opex_annual"] - h2_opex) - opex_total}
    fy26_net = {k: round(v) for k, v in fy26_net.items()}
    fy27     = PROJECTION["fy_2027"]
    fy27_net = {k: to_owner_net(v) for k, v in fy27.items()}

    # 5-year cumulative: annual lease is FROZEN by decree; short-term is not
    lease_series = [ej_net] * 5
    str_series   = [fy_owner, fy27_net["base"]]
    for _ in range(3):
        str_series.append(round(str_series[-1] * (1 + GROWTH)))
    lease_cum = sum(lease_series)
    str_cum   = sum(str_series)
    cum_delta = str_cum - lease_cum


    # ══════════════════════════════════════════════════════════════
    #  SVG CHARTS
    # ══════════════════════════════════════════════════════════════
    def chart_monthly():
        """Bars = revenue (lower panel).  Line = occupancy (its own upper strip, so labels never collide)."""
        W, H, PL, PR = 700, 256, 48, 26
        cw = W - PL - PR
        OT, OH = 10, 38          # occupancy strip: top, height
        PT, PB = 62, 42          # bar panel
        ch = H - PT - PB
        LO, HI = 0.55, 0.95      # occupancy axis bounds
        mx = max(m[4] for m in MONTHS) * 1.12
        n = len(MONTHS); slot = cw / n; bw = slot * 0.42
        s = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" class="chart">']

        # --- occupancy strip -------------------------------------------------
        s.append(f'<text x="{PL-8}" y="{OT+6}" text-anchor="end" class="ax">{HI*100:.0f}%</text>')
        s.append(f'<text x="{PL-8}" y="{OT+OH+4}" text-anchor="end" class="ax">{LO*100:.0f}%</text>')
        s.append(f'<line x1="{PL}" y1="{OT+OH+8:.0f}" x2="{PL+cw}" y2="{OT+OH+8:.0f}" stroke="#E3DBC8" stroke-width="1"/>')
        pts = []
        for i, (_, en, av, bk, rev) in enumerate(MONTHS):
            cx = PL + slot * i + slot / 2
            o = bk / av
            oy = OT + OH - ((o - LO) / (HI - LO)) * OH
            pts.append((cx, oy, o))
        path = " ".join(f"{'M' if i==0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y, _) in enumerate(pts))
        s.append(f'<path d="{path}" fill="none" stroke="#2E6B4F" stroke-width="1.8" stroke-linejoin="round"/>')
        for x, y, o in pts:
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#FFFDF9" stroke="#2E6B4F" stroke-width="1.8"/>')
            s.append(f'<text x="{x:.1f}" y="{y-8:.1f}" text-anchor="middle" class="vl2">{o*100:.0f}%</text>')

        # --- revenue bars ----------------------------------------------------
        for i in range(5):
            v = mx * i / 4; y = PT + ch - (v / mx) * ch
            s.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{PL+cw}" y2="{y:.1f}" stroke="#E3DBC8" stroke-width="1"/>')
            s.append(f'<text x="{PL-8}" y="{y+3.5:.1f}" text-anchor="end" class="ax">{v/1000:.0f}k</text>')
        for i, (_, en, av, bk, rev) in enumerate(MONTHS):
            cx = PL + slot * i + slot / 2
            bh = (rev / mx) * ch; by = PT + ch - bh
            s.append(f'<rect x="{cx-bw/2:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2.5" fill="#B4924A"/>')
            s.append(f'<text x="{cx:.1f}" y="{by-6:.1f}" text-anchor="middle" class="vl">{rev/1000:.1f}k</text>')
            s.append(f'<text x="{cx:.1f}" y="{PT+ch+17:.1f}" text-anchor="middle" class="ax">{en}</text>')

        s.append(f'<text x="{PL}" y="{H-8}" class="lg">'
                 f'<tspan fill="#2E6B4F">▬</tspan> Occupancy الإشغال (top)'
                 f'   <tspan fill="#B4924A">■</tspan> Revenue SAR الإيراد (bars)</text>')
        s.append('</svg>')
        return "".join(s)

    def chart_versus():
        W, H = 700, 192
        s = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" class="chart">']
        mx = max(fy_owner, ej_net) * 1.26
        rows = [
            ("Ouja short-term — net to owner", "عوجا قصير الأجل — صافي المالك", fy_owner, "#B4924A"),
            ("Annual lease per Ejar — net to owner", "العقد السنوي (إيجار) — صافي المالك", ej_net, "#6E6659"),
        ]
        PL, bh, gap, PT = 236, 32, 26, 24
        cw = W - PL - 96
        for i, (en, ar, val, col) in enumerate(rows):
            y = PT + i * (bh + gap)
            bw = (val / mx) * cw
            s.append(f'<text x="{PL-12}" y="{y+12}" text-anchor="end" class="rl-ar">{ar}</text>')
            s.append(f'<text x="{PL-12}" y="{y+25}" text-anchor="end" class="rl-en">{en}</text>')
            s.append(f'<rect x="{PL}" y="{y}" width="{bw:.1f}" height="{bh}" rx="3" fill="{col}"/>')
            s.append(f'<text x="{PL+bw+9:.1f}" y="{y+20}" class="bv">{sar(val)}</text>')
        yb = PT + 2 * (bh + gap) + 4
        s.append(f'<text x="{PL}" y="{yb+14}" class="dl">'
                 f'Δ +{sar(delta_abs)} SAR per year — {pct(delta_pct,0)} above the annual lease</text>')
        s.append(f'<text x="{PL}" y="{yb+30}" class="dl">'
                 f'أعلى من العقد السنوي بـ {sar(delta_abs)} ريال سنويًا — بنسبة {pct(delta_pct,0)}</text>')
        s.append('</svg>')
        return "".join(s)

    def chart_index():
        W, H = 700, 166
        s = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" class="chart">']
        idx = [("MPI", "مؤشر الإشغال", MPI, "Occupancy vs market"),
               ("ARI", "مؤشر السعر", ARI, "Rate vs market"),
               ("RGI", "مؤشر الإيراد", RGI, "RevPAR vs market")]
        PL, PT, cw, bh, gap = 150, 24, 428, 27, 25
        mx = 140
        base = (100 / mx) * cw
        for i, (code, ar, v, sub) in enumerate(idx):
            y = PT + i * (bh + gap)
            bw = (v / mx) * cw
            col = "#2E6B4F" if v >= 100 else "#A4433A"
            s.append(f'<text x="{PL-12}" y="{y+13}" text-anchor="end" class="il">{code}</text>')
            s.append(f'<text x="{PL-12}" y="{y+25}" text-anchor="end" class="il-ar">{ar}</text>')
            s.append(f'<rect x="{PL}" y="{y}" width="{cw}" height="{bh}" rx="3" fill="#EFE8D9"/>')
            s.append(f'<rect x="{PL}" y="{y}" width="{bw:.1f}" height="{bh}" rx="3" fill="{col}"/>')
            # sub-label sits INSIDE the coloured bar (white on colour), never below it
            s.append(f'<text x="{PL+9}" y="{y+bh/2+3.6:.1f}" class="isub">{sub}</text>')
            s.append(f'<line x1="{PL+base:.1f}" y1="{y-4}" x2="{PL+base:.1f}" y2="{y+bh+4}" '
                     f'stroke="#1B1915" stroke-width="1.4" stroke-dasharray="3 2"/>')
            s.append(f'<text x="{PL+bw+9:.1f}" y="{y+bh/2+4:.1f}" class="bv">{v:.1f}</text>')
        s.append(f'<text x="{PL+base:.1f}" y="{PT-9}" text-anchor="middle" class="ax">100 = market par · مطابقة السوق</text>')
        s.append('</svg>')
        return "".join(s)

    def chart_yield():
        """Net yield on the 1.3M purchase price, against Riyadh market benchmarks."""
        W, H = 700, 216
        s = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" class="chart">']
        rows = [
            ("Ouja short-term — net yield", "عوجا قصير الأجل — العائد الصافي", str_net_y, "#B4924A", False),
            ("Annual lease (Ejar) — net yield", "العقد السنوي (إيجار) — العائد الصافي", ej_net_y, "#6E6659", False),
            ("Riyadh residential average — net", "متوسط السوق السكني بالرياض — صافي", MARKET_YIELD["riyadh_net_avg"], "#EFE8D9", True),
        ]
        mx = max(r[2] for r in rows) * 1.30
        PL, bh, gap, PT = 236, 26, 15, 18
        cw = W - PL - 92
        for i, (en, ar, v, col, outline) in enumerate(rows):
            y = PT + i * (bh + gap)
            bw = (v / mx) * cw
            stroke = ' stroke="#C9C0AB" stroke-width="1"' if outline else ''
            s.append(f'<text x="{PL-12}" y="{y+11}" text-anchor="end" class="rl-ar">{ar}</text>')
            s.append(f'<text x="{PL-12}" y="{y+23}" text-anchor="end" class="rl-en">{en}</text>')
            s.append(f'<rect x="{PL}" y="{y}" width="{bw:.1f}" height="{bh}" rx="3" fill="{col}"{stroke}/>')
            s.append(f'<text x="{PL+bw+9:.1f}" y="{y+18}" class="bv">{v*100:.2f}%</text>')
        yb = PT + 3 * (bh + gap) + 2
        s.append(f'<text x="14" y="{yb+13}" class="dl">'
                 f'Net yield on the SAR {sar(PRICE)} purchase price — short-term is {str_net_y/ej_net_y:.1f}× the annual lease</text>')
        s.append(f'<text x="14" y="{yb+28}" class="dl">'
                 f'العائد الصافي على سعر الشراء — قصير الأجل يعادل {str_net_y/ej_net_y:.1f} ضعف العقد السنوي</text>')
        s.append('</svg>')
        return "".join(s)

    def chart_scen():
        W, H = 700, 178
        s = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" class="chart">']
        groups = [("FY 2026", "السنة المالية 2026", fy26_net), ("FY 2027", "السنة المالية 2027", fy27_net)]
        mx = max(list(fy26_net.values()) + list(fy27_net.values()) + [ej_net]) * 1.22
        PL, PT, ch2, gw = 52, 16, 96, 285
        cols = {"low": "#EFE8D9", "base": "#B4924A", "high": "#2E6B4F"}
        labs = {"low": "Conservative متحفظ", "base": "Base أساسي", "high": "Upside متفائل"}
        ejy = PT + ch2 - (ej_net / mx) * ch2
        s.append(f'<line x1="{PL-14}" y1="{ejy:.1f}" x2="{W-18}" y2="{ejy:.1f}" stroke="#A4433A" stroke-width="1.4" stroke-dasharray="5 3"/>')
        s.append(f'<text x="{W-18}" y="{ejy-6:.1f}" text-anchor="end" class="ejl">Ejar annual-lease net  صافي العقد السنوي  {sar(ej_net)}</text>')
        for gi, (en, ar, d) in enumerate(groups):
            gx = PL + gi * (gw + 70)
            for bi, k in enumerate(["low", "base", "high"]):
                v = d[k]; bw = 68
                x = gx + bi * (bw + 20)
                bh = (v / mx) * ch2; y = PT + ch2 - bh
                s.append(f'<rect x="{x}" y="{y:.1f}" width="{bw}" height="{bh:.1f}" rx="3" fill="{cols[k]}" '
                         f'{"stroke=\'#C9C0AB\' stroke-width=\'1\'" if k=="low" else ""}/>')
                s.append(f'<text x="{x+bw/2}" y="{y-7:.1f}" text-anchor="middle" class="vl">{sar(v)}</text>')
                s.append(f'<text x="{x+bw/2}" y="{PT+ch2+15}" text-anchor="middle" class="ax2">{labs[k]}</text>')
            s.append(f'<text x="{gx+gw/2-25}" y="{PT+ch2+38}" text-anchor="middle" class="gl">{en}  ·  {ar}</text>')
        s.append(f'<text x="{PL-14}" y="{H-6}" class="ax">Net to owner, SAR  ·  صافي المالك بالريال</text>')
        s.append('</svg>')
        return "".join(s)


    # ══════════════════════════════════════════════════════════════
    #  PAGE FRAGMENTS
    # ══════════════════════════════════════════════════════════════
    def rh(sec_en, sec_ar):
        return (f'<div class="rh"><div class="l">{sec_en}</div>'
                f'<div class="r ar">{sec_ar} &nbsp;·&nbsp; {UNIT["listing_name_ar"]}</div></div>')

    _pgno = [1]   # cover is page 1
    def rf():
        _pgno[0] += 1
        return (f'<div class="rf"><div>{REPORT["doc_ref"]} &nbsp;·&nbsp; Confidential — prepared for the unit owner</div>'
                f'<div>{_pgno[0]}</div></div>')

    def sec(n, en, ar):
        return (f'<div class="sec"><div class="n">{n}</div><div class="t">'
                f'<div class="en">{en}</div><div class="arh">{ar}</div></div>'
                f'<div class="rule"></div></div>')

    pages = []

    # ---------- P1 COVER ----------
    pages.append(f"""
    <div class="page cover">
     <div class="band"></div>
     <div class="body">
       <div>
         <div class="mark">OUJA</div>
         <div class="mark-ar">عوجا لإدارة الأملاك</div>
         <div class="tagline">Riyadh · Hospitality-grade short-term rental</div>
       </div>
       <div class="mid">
         <div class="kicker">{REPORT["type_en"]}  ·  {REPORT["period_label_en"].split("·")[0].strip()}</div>
         <h1>Owner Performance,<br><b>Market Benchmark</b><br>& Forward Outlook</h1>
         <h1 class="arh">تقرير أداء الوحدة<br><b>ومقارنتها بالسوق</b><br>والتوقعات المستقبلية</h1>
         <div class="hr"></div>
         <div class="meta">
           <div><div class="l">Unit / الوحدة</div>
                <div class="v">{UNIT["listing_name_en"]} · {UNIT["unit_ref"]}</div>
                <div class="v a">{UNIT["compound_ar"]}</div></div>
           <div><div class="l">Period / الفترة</div>
                <div class="v">{REPORT["period_label_en"]}</div>
                <div class="v a">{REPORT["period_label_ar"]}</div></div>
           <div><div class="l">Prepared for / مُعدّ لـ</div>
                <div class="v">{OWNER["name_en"]}</div>
                <div class="v a">{OWNER["name_ar"]}</div></div>
           <div><div class="l">Issued / تاريخ الإصدار</div>
                <div class="v">{REPORT["issue_date_en"]}</div>
                <div class="v a">{REPORT["issue_date_ar"]}</div></div>
         </div>
       </div>
     </div>
     <div class="foot"><div>{REPORT["prepared_by_en"]}</div><div>{REPORT["doc_ref"]}</div></div>
    </div>""")

    # ---------- P2 CONTENTS ----------
    toc = [
     ("01","Executive Summary","الملخص التنفيذي","3"),
     ("02","Short-Term vs. Annual Lease (Ejar SAR 85,000)","التأجير قصير الأجل مقابل العقد السنوي","4"),
     ("03","Return on Capital (SAR 1,300,000 purchase price)","العائد على رأس المال (سعر الشراء 1,300,000)","5"),
     ("04","The Rent Freeze & the Five-Year View","تجميد الإيجارات والنظرة الخمسية","6"),
     ("05","Revenue Performance","أداء الإيرادات","7"),
     ("06","Channel Mix & Booking Behaviour","توزيع قنوات الحجز وسلوك الضيوف","8"),
     ("07","Market & Competitive Benchmark","المقارنة بالسوق والمنافسين","9"),
     ("08","What Moved the Numbers","العوامل المؤثرة على الأداء","10"),
     ("09","Cost & Fee Transparency","شفافية التكاليف والرسوم","11"),
     ("10","Guest Experience & Asset Condition","تجربة الضيف وحالة الأصل","12"),
     ("11","Risks & Mitigations","المخاطر وإجراءات المعالجة","13"),
     ("12","Forward Projection & Year-End Close","التوقعات وإقفال نهاية السنة","14"),
     ("13","90-Day Action Plan","خطة العمل لـ 90 يومًا","15"),
     ("14","Methodology, Definitions & Sources","المنهجية والمصطلحات والمصادر","16"),
    ]
    toc_html = "".join(f'<li><span class="no">{a}</span><span class="en">{b}</span>'
                       f'<span class="a">{c}</span><span class="pg">{d}</span></li>' for a,b,c,d in toc)
    pages.append(f"""
    <div class="page">
     {rh("Contents","المحتويات")}
     {sec("CONTENTS","What's inside this report","محتويات التقرير")}
     <div class="bi">
      <div class="e">This report answers, in order: how the unit performed, whether that is good, how it compares to a normal annual lease and to competing units, what drove the result, exactly where every riyal went, what could go wrong, and what we expect next.</div>
      <div class="a">يجيب هذا التقرير — بالترتيب — عن: كيف كان أداء الوحدة، وهل هذا الأداء جيد، وكيف يُقارن بالعقد السنوي التقليدي وبالوحدات المنافسة، وما الذي أثّر على النتيجة، وأين ذهب كل ريال بالتفصيل، وما المخاطر، وما هو المتوقع في الفترة القادمة.</div>
     </div>
     <ol class="toc">{toc_html}</ol>
     <div class="call">
       <div class="h">The one number, if you read nothing else / الرقم الأهم</div>
       <p><b>SAR {sar(owner_net)}</b> was paid to you for H1 2026 — {pct(owner_margin,0)} of gross revenue. On a
          full-year basis this projects to <b>SAR {sar(fy_owner)}</b>, versus <b>SAR {sar(ej_net)}</b> net from the
          annual lease registered in Ejar (SAR {sar(ej_gross)}). On the <b>SAR {sar(PRICE)}</b> you paid for the unit,
          that is a net yield of <b>{pct(str_net_y,1)}</b> — against <b>{pct(ej_net_y,1)}</b> on a lease and a Riyadh
          residential average near <b>{pct(MARKET_YIELD["riyadh_net_avg"],1)}</b>.</p>
       <p class="a"><b>{sar(owner_net)} ريال</b> صافي ما تم تحويله لك عن النصف الأول من 2026 — أي {pct(owner_margin,0)} من إجمالي الإيراد.
          وعلى أساس سنوي كامل، المتوقع <b>{sar(fy_owner)} ريال</b>، مقابل <b>{sar(ej_net)} ريال</b> صافي من العقد السنوي
          المسجّل في إيجار ({sar(ej_gross)} ريال). وعلى <b>{sar(PRICE)} ريال</b> التي دفعتها ثمنًا للوحدة، فهذا عائد صافٍ
          <b>{pct(str_net_y,1)}</b> — مقابل <b>{pct(ej_net_y,1)}</b> بعقد سنوي، ومتوسط سكني في الرياض قريب من
          <b>{pct(MARKET_YIELD["riyadh_net_avg"],1)}</b>.</p>
     </div>
     {rf()}
    </div>""")

    # ---------- P3 EXECUTIVE SUMMARY ----------
    pages.append(f"""
    <div class="page">
     {rh("01 · Executive Summary","الملخص التنفيذي")}
     {sec("01","Executive Summary","الملخص التنفيذي")}
     <div class="kpis">
      <div class="kpi hero"><div class="k">Net paid to owner</div><div class="ka">صافي المحوّل للمالك</div>
        <div class="v">{sar(owner_net)}</div><div class="s">SAR · H1 2026 · {pct(owner_margin,0)} of gross</div></div>
      <div class="kpi"><div class="k">Gross revenue</div><div class="ka">إجمالي الإيراد</div>
        <div class="v">{sar(gross)}</div><div class="s">SAR · excl. VAT & cleaning</div></div>
      <div class="kpi"><div class="k">Occupancy</div><div class="ka">نسبة الإشغال</div>
        <div class="v">{pct(occ,1)}</div><div class="s">{booked} of {avail} nights</div></div>
      <div class="kpi"><div class="k">Net yield</div><div class="ka">العائد الصافي</div>
        <div class="v">{pct(str_net_y,1)}</div><div class="s">on SAR {sar(PRICE)} · lease: {pct(ej_net_y,1)}</div></div>
     </div>

     <h3 class="sub">The verdict <span>الخلاصة</span></h3>
     <div class="bi">
      <div class="e">The unit generated <b>SAR {sar(gross)}</b> in six months — <b>{multiple:.2f}×</b> its full-year
       Ejar-registered lease value of SAR {sar(ej_gross)}, in half the time. After every fee and cost,
       <b>SAR {sar(owner_net)}</b> reached your account.
       <br><br>Against the market, the unit is outperforming on all three benchmark indices, with occupancy
       the strongest driver (RGI {RGI:.0f} — it captured {RGI-100:.0f}% more revenue per available night than its
       competitive set).
       <br><br>On the <b>SAR {sar(PRICE)}</b> purchase price, that is a <b>{pct(str_net_y,1)}</b> net yield versus
       <b>{pct(ej_net_y,1)}</b> on an annual lease — and it recovers your capital in <b>{pb_str:.1f} years</b> instead
       of {pb_ejar:.1f}.
       <br><br>The main watch item is the summer trough (Jul–Aug), which is expected and already being managed
       through long-stay and corporate rates.</div>
      <div class="a">حققت الوحدة <b>{sar(gross)} ريال</b> خلال ستة أشهر — أي <b>{multiple:.2f} ضعف</b>
       قيمة العقد السنوي المسجّل في إيجار ({sar(ej_gross)} ريال) وفي نصف المدة فقط. وبعد خصم كامل الرسوم
       والتكاليف، وصل إلى حسابك <b>{sar(owner_net)} ريال</b>.
       <br><br>وبمقارنتها بالسوق، تتفوق الوحدة على منافسيها في المؤشرات الثلاثة، والإشغال هو المحرّك الأقوى
       (مؤشر الإيراد {RGI:.0f} — أي أنها حققت إيرادًا أعلى بـ {RGI-100:.0f}% لكل ليلة متاحة مقارنةً بمجموعة المنافسين).
       <br><br>وعلى سعر الشراء البالغ <b>{sar(PRICE)} ريال</b>، فهذا عائد صافٍ <b>{pct(str_net_y,1)}</b> مقابل
       <b>{pct(ej_net_y,1)}</b> بعقد سنوي — ويسترد رأس مالك خلال <b>{pb_str:.1f} سنة</b> بدلًا من {pb_ejar:.1f} سنة.
       <br><br>النقطة الوحيدة التي تحتاج متابعة هي ركود الصيف (يوليو–أغسطس)، وهو متوقع ونعمل عليه حاليًا
       عبر أسعار الإقامات الطويلة وعملاء الشركات.</div>
     </div>

     <h3 class="sub">Performance at a glance <span>نظرة سريعة على الأداء</span></h3>
     <table>
      <tr><th>Metric<span class="ta">المؤشر</span></th><th class="num">This unit<span class="ta">هذه الوحدة</span></th>
          <th class="num">Comp set<span class="ta">المنافسون</span></th><th class="num">Index<span class="ta">المؤشر</span></th>
          <th>Read<span class="ta">القراءة</span></th></tr>
      <tr><td>Occupancy · الإشغال</td><td class="num">{pct(occ,1)}</td><td class="num">{pct(cs_occ,1)}</td>
          <td class="num"><b>{MPI:.1f}</b></td><td><span class="tag t-pos">Above market</span></td></tr>
      <tr><td>ADR · متوسط السعر</td><td class="num">{sar(adr,0)}</td><td class="num">{sar(cs_adr,0)}</td>
          <td class="num"><b>{ARI:.1f}</b></td><td><span class="tag t-pos">Above market</span></td></tr>
      <tr><td>RevPAR · إيراد الليلة المتاحة</td><td class="num">{sar(revpar,0)}</td><td class="num">{sar(cs_rp,0)}</td>
          <td class="num"><b>{RGI:.1f}</b></td><td><span class="tag t-pos">Above market</span></td></tr>
      <tr><td>Guest rating · تقييم الضيوف</td><td class="num">{GUEST["overall"]}</td><td class="num">4.72</td>
          <td class="num"><b>103.6</b></td><td><span class="tag t-pos">Above market</span></td></tr>
      <tr><td>Direct bookings · الحجز المباشر</td><td class="num">21%</td><td class="num">~8%</td>
          <td class="num"><b>262</b></td><td><span class="tag t-pos">Above market</span></td></tr>
      <tr><td>Net yield on capital · العائد الصافي</td><td class="num">{pct(str_net_y,1)}</td>
          <td class="num">{pct(MARKET_YIELD["riyadh_net_avg"],1)}</td>
          <td class="num"><b>{str_net_y/MARKET_YIELD["riyadh_net_avg"]*100:.0f}</b></td>
          <td><span class="tag t-pos">Above market</span></td></tr>
     </table>
     <div class="note">Index = this unit ÷ competitive-set average × 100. A value of 100 means market par.
       Comp set = five comparable furnished 2BR short-term units in Riyadh, same period.</div>
     <div class="note a">المؤشر = أداء الوحدة ÷ متوسط مجموعة المنافسين × 100. القيمة 100 تعني مطابقة السوق تمامًا.
       مجموعة المنافسين = خمس وحدات مفروشة من غرفتين للإيجار قصير الأجل في الرياض، خلال نفس الفترة.</div>
     {rf()}
    </div>""")

    # ---------- P4 THE EJAR COMPARISON ----------
    pages.append(f"""
    <div class="page">
     {rh("02 · Short-term vs. annual lease","التأجير قصير الأجل مقابل العقد السنوي")}
     {sec("02","Short-Term vs. Annual Lease","التأجير قصير الأجل مقابل العقد السنوي")}
     <div class="bi">
      <div class="e">This is the question every owner asks: <i>would I be better off just leasing the unit for a
       year?</i> Below is the honest, net-to-net answer — not gross against gross. The annual lease figure is
       <b>SAR {sar(ej_gross)}</b>, the rate registered on the <b>Ejar</b> platform for a comparable unit in this
       compound. We then deduct the costs a landlord still carries under an annual lease.</div>
      <div class="a">هذا هو السؤال الذي يطرحه كل مالك: <i>هل كان الأفضل تأجير الوحدة بعقد سنوي؟</i>
       في الأسفل الإجابة بشكل صريح — مقارنة صافي بصافي، لا إجمالي بإجمالي. قيمة العقد السنوي هي
       <b>{sar(ej_gross)} ريال</b>، وهي القيمة المسجّلة في منصة <b>إيجار</b> لوحدة مماثلة في نفس المجمع.
       ثم نخصم التكاليف التي يتحمّلها المالك حتى في حالة العقد السنوي.</div>
     </div>

     {chart_versus()}

     <div class="two">
      <div>
       <h3 class="sub">Annual lease (Ejar) <span>العقد السنوي (إيجار)</span></h3>
       <table>
        <tr><th>Line<span class="ta">البند</span></th><th class="num">SAR<span class="ta">ريال</span></th></tr>
        <tr><td>Contracted annual rent · قيمة العقد السنوي</td><td class="num">{sar(ej_gross)}</td></tr>
        <tr><td>Agency / brokerage ({pct(EJAR["broker_pct"],1)}) · عمولة الوساطة</td><td class="num neg">({sar(ej_broker)})</td></tr>
        <tr><td>Vacancy allowance ({pct(EJAR["vacancy_pct"],0)}) · فترة الشغور</td><td class="num neg">({sar(ej_vacancy)})</td></tr>
        <tr><td>Owner-borne maintenance · صيانة على المالك</td><td class="num neg">({sar(ej_maint)})</td></tr>
        <tr><td>Ejar registration & admin · تسجيل ورسوم إدارية</td><td class="num neg">({sar(ej_admin)})</td></tr>
        <tr class="grand"><td>Net to owner · صافي المالك</td><td class="num">{sar(ej_net)}</td></tr>
       </table>
       <div class="note">Source: {EJAR["ref"]}.</div>
      </div>
      <div>
       <h3 class="sub">Ouja short-term (FY2026) <span>عوجا قصير الأجل (2026)</span></h3>
       <table>
        <tr><th>Line<span class="ta">البند</span></th><th class="num">SAR<span class="ta">ريال</span></th></tr>
        <tr><td>Gross revenue (H1 actual + H2 base) · إجمالي الإيراد</td><td class="num">{sar(fy_gross)}</td></tr>
        <tr><td>Channel fees · رسوم المنصات</td><td class="num neg">({sar(channel_fees + h2_channel)})</td></tr>
        <tr><td>Ouja management fee ({pct(COSTS["mgmt_fee_pct"],0)}) · رسوم الإدارة</td><td class="num neg">({sar(mgmt_fee + h2_mgmt)})</td></tr>
        <tr><td>Operating costs · التكاليف التشغيلية</td><td class="num neg">({sar(PROJECTION["opex_annual"])})</td></tr>
        <tr class="grand"><td>Net to owner · صافي المالك</td><td class="num">{sar(fy_owner)}</td></tr>
       </table>
       <div class="note">H2 2026 is the base-case forecast (page 14), not actuals. The unit was delivered furnished,
         so no furnishing capex is charged to you.</div>
       <div class="note a">النصف الثاني من 2026 توقّع أساسي (صفحة 14) وليس أرقامًا فعلية. والوحدة وصلت مؤثثة، فلا
         تُحمَّل عليك أي تكلفة أثاث.</div>
      </div>
     </div>

     <div class="call dark">
      <div class="h">Net-to-net conclusion / الخلاصة صافي مقابل صافي</div>
      <p>Short-term management delivers <b>SAR {sar(delta_abs)} more</b> per year than the annual lease —
         <b>{pct(delta_pct,0)} higher</b>, on the same asset, with no furnishing capex to recover. You also keep the
         flexibility to use, sell, or re-let the unit at any time, which an annual lease removes.</p>
      <p class="a">الإدارة قصيرة الأجل تحقق <b>{sar(delta_abs)} ريال إضافية</b> سنويًا مقارنةً بالعقد السنوي —
         أي <b>أعلى بنسبة {pct(delta_pct,0)}</b>، على نفس الأصل، وبدون أي تكلفة أثاث تُسترد. إضافةً إلى احتفاظك بحرية
         استخدام الوحدة أو بيعها أو إعادة تأجيرها في أي وقت، وهي مرونة يفقدها المالك في العقد السنوي.</p>
     </div>
     <div class="note">The annual lease does give you predictability and near-zero involvement — at the cost of
       upside, flexibility and control over the asset. Both sides are shown so the decision is yours, on the facts.
       <span class="ar" style="display:block;margin-top:2pt">العقد السنوي يمنحك استقرارًا وعدم تدخّل تشغيلي — مقابل
       التنازل عن فرص النمو والمرونة والتحكم في الأصل. عرضنا الجانبين ليكون القرار لك ومبنيًا على أرقام واضحة.</span></div>
     {rf()}
    </div>""")

    # ---------- RETURN ON CAPITAL (NEW) ----------
    fy_rows = "".join(
        f'<tr><td>{y}</td>'
        f'<td class="num">{sar(lease_series[i])}</td>'
        f'<td class="num">{sar(str_series[i])}</td>'
        f'<td class="num" style="color:var(--pos);font-weight:600">+{sar(str_series[i]-lease_series[i])}</td></tr>'
        for i, y in enumerate(FREEZE_YRS))

    pages.append(f"""
    <div class="page dense">
     {rh("03 · Return on capital","العائد على رأس المال")}
     {sec("03","Return on Capital","العائد على رأس المال")}
     <div class="bi">
      <div class="e">Revenue is only half the question. The other half is what it returns on the
       <b>SAR {sar(PRICE)}</b> you paid for the unit. Below is the yield on that capital, measured against
       published Riyadh benchmarks.</div>
      <div class="a">الإيراد نصف السؤال فقط. والنصف الآخر هو: كم يعود هذا الإيراد على
       <b>{sar(PRICE)} ريال</b> التي دفعتها ثمنًا للوحدة؟ في الأسفل العائد على رأس المال، مقارنًا بالمؤشرات
       المنشورة لسوق الرياض.</div>
     </div>

     <div class="kpis">
      <div class="kpi hero"><div class="k">Net yield · short-term</div><div class="ka">العائد الصافي · قصير الأجل</div>
        <div class="v">{pct(str_net_y,1)}</div><div class="s">on SAR {sar(PRICE)}</div></div>
      <div class="kpi"><div class="k">Net yield · annual lease</div><div class="ka">العائد الصافي · عقد سنوي</div>
        <div class="v">{pct(ej_net_y,1)}</div><div class="s">Ejar SAR {sar(ej_gross)}</div></div>
      <div class="kpi"><div class="k">Riyadh market · net</div><div class="ka">متوسط الرياض · صافي</div>
        <div class="v">{pct(MARKET_YIELD["riyadh_net_avg"],1)}</div><div class="s">residential average</div></div>
      <div class="kpi"><div class="k">Capital payback</div><div class="ka">استرداد رأس المال</div>
        <div class="v">{pb_str:.1f}</div><div class="s">yrs vs {pb_ejar:.1f} on a lease</div></div>
     </div>

     {chart_yield()}

     <div class="two">
      <div>
       <h3 class="sub">Yield on the purchase price <span>العائد على سعر الشراء</span></h3>
       <table>
        <tr><th>Basis<span class="ta">الأساس</span></th><th class="num">Gross<span class="ta">إجمالي</span></th>
            <th class="num">Net<span class="ta">صافي</span></th></tr>
        <tr><td>Annual lease (Ejar {sar(ej_gross)}) · عقد سنوي</td>
            <td class="num">{pct(ej_gross_y,2)}</td><td class="num">{pct(ej_net_y,2)}</td></tr>
        <tr class="grand"><td>Ouja short-term (FY2026) · عوجا قصير الأجل</td>
            <td class="num">{pct(str_gross_y,2)}</td><td class="num">{pct(str_net_y,2)}</td></tr>
        <tr class="tot"><td>Uplift · الفارق</td><td class="num">+{(str_gross_y-ej_gross_y)*100:.2f} pts</td>
            <td class="num">+{(str_net_y-ej_net_y)*100:.2f} pts</td></tr>
       </table>
       <div class="note">Capital deployed = SAR {sar(PRICE)}, the purchase price. The unit was delivered furnished,
         so there is no furnishing capex to add. · رأس المال = {sar(PRICE)} ريال، وهو سعر الشراء. والوحدة وصلت مؤثثة،
         فلا توجد تكلفة أثاث تُضاف.</div>
      </div>
      <div>
       <h3 class="sub">Against the Riyadh market <span>مقارنةً بسوق الرياض</span></h3>
       <table>
        <tr><th>Benchmark<span class="ta">المؤشر المرجعي</span></th><th class="num">Yield<span class="ta">العائد</span></th></tr>
        <tr><td>Riyadh residential — gross, citywide · إجمالي</td>
            <td class="num">{pct(MARKET_YIELD["riyadh_gross_low"],1)}–{pct(MARKET_YIELD["riyadh_gross_high"],1)}</td></tr>
        <tr><td>Riyadh residential — net average · صافي</td><td class="num">{pct(MARKET_YIELD["riyadh_net_avg"],1)}</td></tr>
        <tr><td>Saudi national — gross average · المتوسط الوطني</td><td class="num">{pct(MARKET_YIELD["ksa_gross_avg"],2)}</td></tr>
        <tr class="sub-t"><td>Your unit — annual lease, net · وحدتك بعقد سنوي</td><td class="num">{pct(ej_net_y,2)}</td></tr>
        <tr class="grand"><td>Your unit — Ouja short-term, net · وحدتك مع عوجا</td><td class="num">{pct(str_net_y,2)}</td></tr>
       </table>
       <div class="note">Sources: Global Property Guide, Bayut, JLL (H1 2026). Yields vary by district and source.</div>
      </div>
     </div>

     <div class="note">Yield here is income only. Capital appreciation is excluded on purpose — the unit's value
       moves the same way whichever strategy you choose, so it does not separate the two. See page 6 for the effect
       of the Riyadh rent freeze on the annual-lease option.</div>
     <div class="note a">العائد هنا دخلي فقط. وارتفاع قيمة العقار مستبعد عمدًا — لأن قيمة الوحدة تتحرك بنفس القدر
       أيًا كان الخيار، فهو لا يفرّق بينهما. انظر صفحة 6 لأثر تجميد الإيجارات في الرياض على خيار العقد السنوي.</div>
     {rf()}
    </div>""")

    # ---------- 04 · THE RENT FREEZE & THE FIVE-YEAR VIEW ----------
    pages.append(f"""
    <div class="page dense">
     {rh("04 · The rent freeze & the five-year view","تجميد الإيجارات والنظرة الخمسية")}
     {sec("04","The Rent Freeze & the Five-Year View","تجميد الإيجارات والنظرة الخمسية")}
     <div class="bi">
      <div class="e">A regulatory change in September 2025 materially altered the annual-lease option — and most
       owners have not yet re-run their numbers against it. This page does.</div>
      <div class="a">تغيير تنظيمي في سبتمبر 2025 غيّر جوهريًا خيار العقد السنوي — ومعظم المُلّاك لم يُعيدوا حساب
       أرقامهم بناءً عليه بعد. هذه الصفحة تفعل ذلك.</div>
     </div>

     <div class="call dark">
      <div class="h">The rent freeze changes the maths / تجميد الإيجارات يغيّر المعادلة</div>
      <p>By Royal Decree, rents inside Riyadh's urban boundary are <b>frozen for five years from 25 September 2025</b>
         — for new <i>and</i> existing leases — and leases now renew automatically. If you signed an annual lease at
         SAR {sar(ej_gross)}, that figure would be <b>locked until {RENT_FREEZE["ends"]}</b> and could not be raised at
         renewal. Short-term nightly rates are not an Ejar annual lease and continue to reprice daily with demand.</p>
      <p class="a">بموجب مرسوم ملكي، الإيجارات داخل النطاق العمراني للرياض <b>مجمّدة خمس سنوات ابتداءً من 25 سبتمبر 2025</b>
         — للعقود الجديدة والقائمة — والعقود تُجدَّد تلقائيًا. أي أنك لو أجّرت الوحدة بعقد سنوي بـ {sar(ej_gross)} ريال،
         لبقي هذا الرقم <b>مجمّدًا حتى {RENT_FREEZE["ends_ar"]}</b> دون إمكانية رفعه عند التجديد. أما الأسعار اليومية للتأجير
         قصير الأجل فليست عقد إيجار سنوي في "إيجار"، وتستمر في التسعير اليومي حسب الطلب.</p>
     </div>

     <h3 class="sub">Five-year cumulative, net to owner <span>الإجمالي التراكمي لخمس سنوات — صافي المالك</span></h3>
     <table>
      <tr><th>Year<span class="ta">السنة</span></th>
          <th class="num">Annual lease — frozen<span class="ta">عقد سنوي — مجمّد</span></th>
          <th class="num">Ouja short-term<span class="ta">عوجا قصير الأجل</span></th>
          <th class="num">Difference<span class="ta">الفارق</span></th></tr>
      {fy_rows}
      <tr class="grand"><td>Cumulative · التراكمي</td><td class="num">{sar(lease_cum)}</td>
          <td class="num">{sar(str_cum)}</td><td class="num">+{sar(cum_delta)}</td></tr>
     </table>
     <div class="note">Short-term assumes the base case for 2026–27, then {pct(GROWTH,0)} net growth p.a. The annual
       lease is held flat because the freeze does not permit an increase. Estimates, not guarantees. This is a
       commercial summary, not legal advice — confirm the freeze's application to your contract with REGA or your
       legal adviser.</div>
     <div class="note a">التأجير قصير الأجل مبني على السيناريو الأساسي لعامي 2026–2027، ثم نمو صافٍ {pct(GROWTH,0)} سنويًا.
       والعقد السنوي ثابت لأن التجميد لا يسمح بالزيادة. هذه تقديرات وليست ضمانات، وهي ملخص تجاري لا يُعد استشارة
       قانونية — يُرجى التأكد من انطباق التجميد على عقدك مع الهيئة العامة للعقار أو مستشارك القانوني.</div>
     {rf()}
    </div>""")

    # ---------- P5 REVENUE ----------
    mrows = ""
    for ar, en, av, bk, rev in MONTHS:
        o = bk / av; a_ = rev / bk; rp = rev / av
        mrows += (f'<tr><td>{en} · <span class="ar">{ar}</span></td><td class="num">{av}</td><td class="num">{bk}</td>'
                  f'<td class="num">{pct(o,0)}</td><td class="num">{sar(a_,0)}</td><td class="num">{sar(rp,0)}</td>'
                  f'<td class="num">{sar(rev)}</td></tr>')
    pages.append(f"""
    <div class="page">
     {rh("05 · Revenue performance","أداء الإيرادات")}
     {sec("05","Revenue Performance","أداء الإيرادات")}
     {chart_monthly()}
     <table>
      <tr><th>Month<span class="ta">الشهر</span></th><th class="num">Nights avail.<span class="ta">ليالٍ متاحة</span></th>
          <th class="num">Nights sold<span class="ta">ليالٍ مباعة</span></th><th class="num">Occ.<span class="ta">الإشغال</span></th>
          <th class="num">ADR<span class="ta">متوسط السعر</span></th><th class="num">RevPAR<span class="ta">إيراد الليلة المتاحة</span></th>
          <th class="num">Revenue (SAR)<span class="ta">الإيراد</span></th></tr>
      {mrows}
      <tr class="tot"><td>H1 2026 · النصف الأول</td><td class="num">{avail}</td><td class="num">{booked}</td>
          <td class="num">{pct(occ,1)}</td><td class="num">{sar(adr,0)}</td><td class="num">{sar(revpar,0)}</td>
          <td class="num">{sar(gross)}</td></tr>
     </table>

     <div class="two">
      <div>
       <h3 class="sub">How to read this <span>كيف تقرأ الأرقام</span></h3>
       <ul class="bul">
        <li><b>ADR</b> — the average nightly price actually achieved.</li>
        <li><b>Occupancy</b> — nights sold ÷ nights available.</li>
        <li><b>RevPAR</b> — revenue per available night. It blends price and occupancy, and is the fairest single
            measure of how hard the asset is working. A high ADR with low occupancy is a warning sign; a high
            RevPAR is not.</li>
       </ul>
      </div>
      <div>
       <h3 class="sub">‎ <span>ملاحظات</span></h3>
       <ul class="bul a">
        <li><b>متوسط السعر اليومي</b> — السعر الفعلي المتحقق لكل ليلة.</li>
        <li><b>الإشغال</b> — الليالي المباعة ÷ الليالي المتاحة.</li>
        <li><b>إيراد الليلة المتاحة</b> — يجمع بين السعر والإشغال، وهو أعدل مقياس لكفاءة تشغيل الأصل. سعر مرتفع
            مع إشغال منخفض = مؤشر خطر، أما ارتفاع إيراد الليلة المتاحة فليس كذلك.</li>
       </ul>
      </div>
     </div>

     <div class="call">
      <div class="h">Best & weakest months / أقوى وأضعف شهر</div>
      <p><b>April</b> was the strongest month (SAR 19,760 · 87% occupancy · ADR 760) — post-Eid demand plus the
         dynamic pricing engine capturing the peak. <b>February</b> was the weakest (SAR 11,780 · 68%) — the first
         half of Ramadan, which is a structural, predictable dip in leisure demand across Riyadh, not a
         performance issue.</p>
      <p class="a"><b>أبريل</b> كان الأقوى (19,760 ريال · إشغال 87% · متوسط سعر 760) — بسبب طلب ما بعد العيد
         مع محرك التسعير الديناميكي الذي التقط الذروة. و<b>فبراير</b> كان الأضعف (11,780 ريال · 68%) — النصف
         الأول من رمضان، وهو انخفاض موسمي متوقع في الطلب الترفيهي على مستوى الرياض كاملة، وليس ضعفًا في الأداء.</p>
     </div>
     <div class="note">Accommodation revenue only — excludes 15% VAT and cleaning fees. Detail on page 9.</div>
     {rf()}
    </div>""")

    # ---------- P6 CHANNELS ----------
    crows = ""
    for ar, en, sh in CHANNELS:
        rv = round(gross * sh)
        bar = f'<div style="background:var(--cream2);height:7pt;border-radius:4pt;overflow:hidden"><div style="width:{sh*100:.0f}%;height:7pt;background:var(--gold)"></div></div>'
        crows += (f'<tr><td>{en} · <span class="ar">{ar}</span></td><td class="num">{pct(sh,0)}</td>'
                  f'<td class="num">{sar(rv)}</td><td style="width:34%">{bar}</td></tr>')
    pages.append(f"""
    <div class="page">
     {rh("06 · Channels & booking behaviour","قنوات الحجز وسلوك الضيوف")}
     {sec("06","Channel Mix & Booking Behaviour","توزيع قنوات الحجز وسلوك الضيوف")}
     <div class="bi">
      <div class="e">Where a booking comes from decides how much of it you keep. Every direct booking avoids a
       platform commission entirely — which is why we invest in the Ouja direct channel and the Ouja Elite
       loyalty base (4,500+ members).</div>
      <div class="a">مصدر الحجز هو ما يحدد كم يبقى منه في جيبك. كل حجز مباشر يوفّر عمولة المنصة بالكامل —
       ولهذا نستثمر في قناة الحجز المباشر لعوجا وفي برنامج عوجا إيليت للولاء (أكثر من 4,500 عضو).</div>
     </div>
     <table>
      <tr><th>Channel<span class="ta">القناة</span></th><th class="num">Share<span class="ta">الحصة</span></th>
          <th class="num">Revenue (SAR)<span class="ta">الإيراد</span></th><th>‎</th></tr>
      {crows}
      <tr class="tot"><td>Total · الإجمالي</td><td class="num">100%</td><td class="num">{sar(gross)}</td><td></td></tr>
     </table>

     <h3 class="sub">Booking behaviour <span>سلوك الحجز</span></h3>
     <div class="kpis">
      <div class="kpi"><div class="k">Reservations</div><div class="ka">عدد الحجوزات</div>
        <div class="v">{BOOKING_BEHAVIOUR["reservations"]}</div><div class="s">in the period</div></div>
      <div class="kpi"><div class="k">Avg. length of stay</div><div class="ka">متوسط مدة الإقامة</div>
        <div class="v">{BOOKING_BEHAVIOUR["alos"]}</div><div class="s">nights · ليالٍ</div></div>
      <div class="kpi"><div class="k">Booking lead time</div><div class="ka">مدة الحجز المسبق</div>
        <div class="v">{BOOKING_BEHAVIOUR["lead_time"]}</div><div class="s">days ahead · يوم</div></div>
      <div class="kpi"><div class="k">Repeat guests</div><div class="ka">ضيوف متكررون</div>
        <div class="v">{pct(BOOKING_BEHAVIOUR["repeat_guest_pct"],0)}</div><div class="s">of reservations</div></div>
     </div>

     <div class="two">
      <div>
       <h3 class="sub">What this tells us <span>ماذا يعني هذا</span></h3>
       <ul class="bul">
        <li>A short lead time ({BOOKING_BEHAVIOUR["lead_time"]} days) means the Riyadh market books late — so
            holding rate late into the window is correct, and discounting early is value destruction.</li>
        <li>{pct(BOOKING_BEHAVIOUR["repeat_guest_pct"],0)} repeat guests is well above the Riyadh STR norm and
            is a direct result of the Elite programme and guest service.</li>
        <li>Cancellation rate {pct(BOOKING_BEHAVIOUR["cancellation_pct"],1)} — low, and within tolerance.</li>
        <li>Airbnb at 64% is a concentration risk we are actively reducing.</li>
       </ul>
      </div>
      <div>
       <h3 class="sub">‎ <span>القراءة</span></h3>
       <ul class="bul a">
        <li>قِصر مدة الحجز المسبق ({BOOKING_BEHAVIOUR["lead_time"]} يوم) يعني أن سوق الرياض يحجز متأخرًا —
            لذلك الثبات على السعر حتى قرب الموعد هو التصرف الصحيح، والتخفيض المبكر يُضيّع قيمة.</li>
        <li>نسبة الضيوف المتكررين {pct(BOOKING_BEHAVIOUR["repeat_guest_pct"],0)} أعلى بكثير من متوسط السوق،
            وهي نتيجة مباشرة لبرنامج إيليت ومستوى الخدمة.</li>
        <li>نسبة الإلغاء {pct(BOOKING_BEHAVIOUR["cancellation_pct"],1)} — منخفضة وضمن الحدود المقبولة.</li>
        <li>اعتماد 64% على Airbnb يمثل تركّزًا نعمل على تقليله.</li>
       </ul>
      </div>
     </div>
     {rf()}
    </div>""")

    # ---------- P7 COMPETITIVE BENCHMARK ----------
    comprows = ""
    for ar, en, a_, o_ in COMP_SET:
        comprows += (f'<tr><td>{en}<br><span class="ar" style="font-size:7.6pt;color:var(--muted)">{ar}</span></td>'
                     f'<td class="num">{sar(a_)}</td><td class="num">{pct(o_,1)}</td>'
                     f'<td class="num">{sar(a_*o_,0)}</td></tr>')
    pages.append(f"""
    <div class="page dense">
     {rh("07 · Market & competitive benchmark","المقارنة بالسوق والمنافسين")}
     {sec("07","Market & Competitive Benchmark","المقارنة بالسوق والمنافسين")}
     <div class="bi">
      <div class="e">Absolute numbers mean little alone. What matters is whether the unit takes more or less than
       its fair share of the market. The three indices below are the standard hospitality measures for exactly that.</div>
      <div class="a">الأرقام المطلقة وحدها لا تكفي. المهم: هل تأخذ الوحدة أكثر أم أقل من حصتها العادلة من السوق؟
       المؤشرات الثلاثة أدناه هي المقاييس المعتمدة عالميًا في قطاع الضيافة للإجابة على ذلك.</div>
     </div>
     {chart_index()}
     <table>
      <tr><th>Competitive set<span class="ta">مجموعة المنافسين</span></th><th class="num">ADR<span class="ta">متوسط السعر</span></th>
          <th class="num">Occupancy<span class="ta">الإشغال</span></th><th class="num">RevPAR<span class="ta">إيراد الليلة المتاحة</span></th></tr>
      {comprows}
      <tr class="sub-t"><td>Comp-set average · متوسط المنافسين</td><td class="num">{sar(cs_adr,0)}</td>
          <td class="num">{pct(cs_occ,1)}</td><td class="num">{sar(cs_rp,0)}</td></tr>
      <tr class="grand"><td>{UNIT["listing_name_en"]} · {UNIT["listing_name_ar"]}</td><td class="num">{sar(adr,0)}</td>
          <td class="num">{pct(occ,1)}</td><td class="num">{sar(revpar,0)}</td></tr>
     </table>

     <div class="call">
      <div class="h">The read / القراءة</div>
      <p>The unit is <b>{ARI-100:.0f}% above market on price</b> and <b>{MPI-100:.0f}% above market on occupancy</b>
         at the same time — an unusual combination, since most operators buy occupancy by cutting rate. Comp D is the
         cautionary example: the highest ADR in the set (SAR 750), but at 58% occupancy its RevPAR lands
         <i>below</i> ours despite charging more per night.</p>
      <p class="a">الوحدة أعلى من السوق بـ <b>{ARI-100:.0f}% في السعر</b> و<b>{MPI-100:.0f}% في الإشغال</b> في آنٍ واحد —
         وهذا مزيج نادر، لأن أغلب المشغّلين يرفعون الإشغال بخفض السعر. ومنافس د مثال واضح: أعلى سعر في المجموعة
         (750 ريال)، لكن بإشغال 58% جاء إيراد الليلة المتاحة لديه <i>أقل</i> من إيرادنا رغم أن سعره أعلى.</p>
     </div>

     <h3 class="sub">Definitions <span>تعريف المؤشرات</span></h3>
     <table>
      <tr><th>Index<span class="ta">المؤشر</span></th><th>Formula<span class="ta">المعادلة</span></th>
          <th>Meaning<span class="ta">المعنى</span></th></tr>
      <tr><td><b>MPI</b></td><td>Our occ. ÷ market occ. × 100</td>
          <td>Are we filling more nights than the market? · هل نبيع ليالٍ أكثر من السوق؟</td></tr>
      <tr><td><b>ARI</b></td><td>Our ADR ÷ market ADR × 100</td>
          <td>Are we charging more than the market? · هل نسعّر أعلى من السوق؟</td></tr>
      <tr><td><b>RGI</b></td><td>Our RevPAR ÷ market RevPAR × 100</td>
          <td>Are we capturing more revenue overall? · هل نحقق إيرادًا أعلى إجمالًا؟</td></tr>
     </table>
     {rf()}
    </div>""")

    # ---------- P8 FACTORS ----------
    frows = ""
    tagmap = {"up": ("t-pos", "Positive · إيجابي"), "down": ("t-neg", "Negative · سلبي"), "flat": ("t-neu", "Neutral · محايد")}
    for imp, ar_t, en_t, ar_d, en_d in FACTORS:
        cls, lab = tagmap[imp]
        frows += (f'<tr><td><span class="tag {cls}">{lab}</span></td>'
                  f'<td><b>{en_t}</b><br><span style="color:var(--ink2)">{en_d}</span></td>'
                  f'<td class="ar"><b>{ar_t}</b><br><span style="color:var(--ink2)">{ar_d}</span></td></tr>')
    pages.append(f"""
    <div class="page">
     {rh("08 · What moved the numbers","العوامل المؤثرة على الأداء")}
     {sec("08","What Moved the Numbers","العوامل المؤثرة على الأداء")}
     <div class="bi">
      <div class="e">Performance is never just management. It is management plus the calendar, the market, the
       regulator, and the weather. Below is a full, unedited account of everything that pushed the numbers up or
       down this period — including the things that worked against us.</div>
      <div class="a">الأداء ليس نتيجة الإدارة وحدها، بل الإدارة + التقويم + السوق + الجهات التنظيمية + الطقس.
       في الأسفل سرد كامل وصريح لكل ما رفع الأرقام أو خفضها خلال هذه الفترة — بما في ذلك ما كان ضدنا.</div>
     </div>
     <table>
      <tr><th style="width:15%">Impact<span class="ta">الأثر</span></th>
          <th style="width:43%">Factor<span class="ta">العامل</span></th>
          <th style="width:42%">‎<span class="ta">التفاصيل</span></th></tr>
      {frows}
     </table>
     <div class="call">
      <div class="h">Seasonality is structural, not a failure / الموسمية طبيعة السوق لا خلل في الأداء</div>
      <p>Riyadh short-term demand has a fixed rhythm: a strong Riyadh Season (Oct–Mar), a Ramadan dip, an Eid
         spike, a strong spring, and a summer trough. We do not fight it — we price into it. Judging any single
         month against another is misleading; judge the year.</p>
      <p class="a">للطلب في سوق الرياض إيقاع ثابت: موسم رياض قوي (أكتوبر–مارس)، ثم انخفاض في رمضان، ثم قفزة
         في العيد، وربيع قوي، ثم ركود صيفي. نحن لا نقاوم هذا الإيقاع — بل نسعّر بناءً عليه. لذلك مقارنة شهر
         بشهر آخر مضللة؛ والحكم الصحيح يكون على السنة كاملة.</p>
     </div>
     {rf()}
    </div>""")

    # ---------- P9 COSTS ----------
    oprows = ""
    for ar, en, v in COSTS["opex"]:
        oprows += f'<tr><td>{en} · <span class="ar">{ar}</span></td><td class="num neg">({sar(v)})</td><td class="num">{pct(v/gross,1)}</td></tr>'
    pages.append(f"""
    <div class="page">
     {rh("09 · Cost & fee transparency","شفافية التكاليف والرسوم")}
     {sec("09","Cost & Fee Transparency","شفافية التكاليف والرسوم")}
     <div class="bi">
      <div class="e">Every riyal, from the guest's payment to your account. Nothing is netted off silently.</div>
      <div class="a">كل ريال — من دفعة الضيف إلى حسابك. لا يوجد أي خصم غير معلن.</div>
     </div>
     <table>
      <tr><th style="width:52%">Line<span class="ta">البند</span></th><th class="num">SAR<span class="ta">ريال</span></th>
          <th class="num">% of gross<span class="ta">من الإجمالي</span></th></tr>
      <tr class="sub-t"><td>Gross accommodation revenue · إجمالي إيراد الإقامة</td><td class="num">{sar(gross)}</td><td class="num">100.0%</td></tr>
      <tr><td>Channel &amp; payment fees · رسوم المنصات والدفع</td><td class="num neg">({sar(channel_fees)})</td><td class="num">{pct(channel_fees/gross,1)}</td></tr>
      <tr class="tot"><td>Net rental revenue · صافي إيراد التأجير</td><td class="num">{sar(net_rental)}</td><td class="num">{pct(net_rental/gross,1)}</td></tr>
      <tr><td>Ouja management fee ({pct(COSTS["mgmt_fee_pct"],0)} of net rental revenue) · رسوم إدارة عوجا</td>
          <td class="num neg">({sar(mgmt_fee)})</td><td class="num">{pct(mgmt_fee/gross,1)}</td></tr>
      {oprows}
      <tr class="tot"><td>Total operating costs · إجمالي التكاليف التشغيلية</td><td class="num neg">({sar(opex_total)})</td><td class="num">{pct(opex_total/gross,1)}</td></tr>
      <tr class="grand"><td>Net paid to owner · صافي المحوّل للمالك</td><td class="num">{sar(owner_net)}</td><td class="num">{pct(owner_margin,1)}</td></tr>
     </table>

     <div class="two">
      <div>
       <h3 class="sub">Not in the numbers above <span>بنود خارج الأرقام أعلاه</span></h3>
       <ul class="bul">
        <li><b>VAT (15%)</b> — charged to the guest on top of the nightly rate and remitted in full to ZATCA. It is
            never your revenue and never our fee.</li>
        <li><b>Cleaning fee</b> — collected from the guest and paid to the cleaning team. Net effect on you: zero.</li>
        <li><b>Security deposits &amp; damage claims</b> — held and recovered through the platform; any recovery is
            credited to you in the month it lands.</li>
        <li><b>Furnishing</b> — the unit was delivered furnished. There is no furnishing capex charged to you and
            none deducted from your payouts.</li>
       </ul>
      </div>
      <div>
       <h3 class="sub">‎ <span>الشرح</span></h3>
       <ul class="bul a">
        <li><b>ضريبة القيمة المضافة (15%)</b> — تُضاف على الضيف فوق سعر الليلة وتُورّد بالكامل لهيئة الزكاة
            والضريبة والجمارك. ليست إيرادًا لك ولا رسومًا لنا.</li>
        <li><b>رسوم النظافة</b> — تُحصّل من الضيف وتُدفع لفريق النظافة. الأثر عليك: صفر.</li>
        <li><b>مبالغ التأمين ومطالبات الأضرار</b> — تُحجز وتُسترد عبر المنصة، وأي مبلغ مسترد يُضاف لحسابك في
            الشهر الذي يُستلم فيه.</li>
        <li><b>الأثاث</b> — الوحدة وصلت مؤثثة. لا توجد تكلفة أثاث محمّلة عليك ولا مخصومة من مستحقاتك.</li>
       </ul>
      </div>
     </div>
     <div class="call">
      <div class="h">The management fee, plainly / رسوم الإدارة بوضوح</div>
      <p>Our fee is {pct(COSTS["mgmt_fee_pct"],0)} of net rental revenue — <b>SAR {sar(mgmt_fee)}</b> this period.
         It is charged on what the unit actually earns, so if the unit earns less, we earn less. We are paid to
         grow the same number you are paid on.</p>
      <p class="a">رسومنا {pct(COSTS["mgmt_fee_pct"],0)} من صافي إيراد التأجير — <b>{sar(mgmt_fee)} ريال</b> هذه الفترة.
         وتُحتسب على ما تحققه الوحدة فعليًا، فإذا انخفض دخل الوحدة انخفض دخلنا. أي أن مصلحتنا مرتبطة تمامًا
         بنفس الرقم الذي تُحاسَب عليه أنت.</p>
     </div>
     {rf()}
    </div>""")

    # ---------- P10 GUEST EXPERIENCE ----------
    grows = ""
    for ar, en, v in GUEST["sub"]:
        w = (v / 5) * 100
        bar = f'<div style="background:var(--cream2);height:7pt;border-radius:4pt;overflow:hidden"><div style="width:{w:.0f}%;height:7pt;background:var(--pos)"></div></div>'
        grows += f'<tr><td>{en} · <span class="ar">{ar}</span></td><td class="num">{v}</td><td style="width:45%">{bar}</td></tr>'
    pages.append(f"""
    <div class="page">
     {rh("10 · Guest experience & asset condition","تجربة الضيف وحالة الأصل")}
     {sec("10","Guest Experience & Asset Condition","تجربة الضيف وحالة الأصل")}
     <div class="bi">
      <div class="e">Reviews are not vanity. Platform ranking is driven by rating and response behaviour, and
       ranking drives occupancy 60–90 days out. Today's review score is next quarter's revenue.</div>
      <div class="a">التقييمات ليست ترفًا. ترتيب الوحدة في المنصات يعتمد على التقييم وسرعة الاستجابة، والترتيب
       هو ما يحدد الإشغال بعد 60–90 يومًا. تقييم اليوم هو إيراد الربع القادم.</div>
     </div>
     <div class="kpis">
      <div class="kpi hero"><div class="k">Overall rating</div><div class="ka">التقييم العام</div>
        <div class="v">{GUEST["overall"]}</div><div class="s">of 5 · {GUEST["reviews"]} reviews</div></div>
      <div class="kpi"><div class="k">Response rate</div><div class="ka">معدل الاستجابة</div>
        <div class="v">{pct(GUEST["response_rate"],0)}</div><div class="s">median {GUEST["median_response_min"]} min</div></div>
      <div class="kpi"><div class="k">Superhost</div><div class="ka">مضيف متميز</div>
        <div class="v">✓</div><div class="s">maintained · محافظ عليه</div></div>
      <div class="kpi"><div class="k">Market avg.</div><div class="ka">متوسط السوق</div>
        <div class="v">4.72</div><div class="s">comp-set rating</div></div>
     </div>
     <h3 class="sub">Rating breakdown <span>تفصيل التقييم</span></h3>
     <table>{grows}</table>

     <h3 class="sub">Asset condition <span>حالة الأصل</span></h3>
     <table>
      <tr><th>Item<span class="ta">البند</span></th><th>Status<span class="ta">الحالة</span></th>
          <th>Action<span class="ta">الإجراء</span></th></tr>
      <tr><td>Structure, plumbing, electrical · الإنشاء والسباكة والكهرباء</td>
          <td><span class="tag t-pos">Good · جيد</span></td><td>Routine inspection · فحص دوري</td></tr>
      <tr><td>Air conditioning · التكييف</td><td><span class="tag t-pos">Serviced · تمت الصيانة</span></td>
          <td>Preventive service before season · صيانة وقائية قبل الموسم</td></tr>
      <tr><td>Sofa & mattresses · الكنب والمراتب</td><td><span class="tag t-warn">Year-two wear · استهلاك السنة الثانية</span></td>
          <td>Refresh scheduled Sep 2026 · تحديث مجدول سبتمبر</td></tr>
      <tr><td>Linen & towels · المفارش والمناشف</td><td><span class="tag t-warn">Rotation due · تحتاج تجديد</span></td>
          <td>Replace Sep 2026 · استبدال سبتمبر</td></tr>
      <tr><td>Appliances · الأجهزة</td><td><span class="tag t-pos">Good · جيد</span></td><td>—</td></tr>
     </table>
     <div class="call">
      <div class="h">Why "Value" is the lowest sub-score / لماذا "القيمة" هو الأدنى</div>
      <p>Value at {GUEST["sub"][-1][2]} is our lowest line — it is the normal trade-off of pricing above market
         ({ARI:.0f} rate index). It is not a problem while occupancy stays above market, but it is the number we
         watch: if Value falls below 4.70 while occupancy softens, that is the signal to adjust rate, not before.</p>
      <p class="a">تقييم "القيمة" {GUEST["sub"][-1][2]} هو الأدنى لدينا — وهذا هو المقابل الطبيعي للتسعير أعلى
         من السوق (مؤشر السعر {ARI:.0f}). لا يمثل مشكلة طالما بقي الإشغال أعلى من السوق، لكنه الرقم الذي نراقبه:
         إذا نزل تقييم القيمة تحت 4.70 مع تراجع الإشغال، فهذه هي إشارة تعديل السعر — وليس قبل ذلك.</p>
     </div>
     {rf()}
    </div>""")

    # ---------- P11 RISKS ----------
    rrows = ""
    rmap = {"high": ("t-neg", "High · مرتفع"), "med": ("t-warn", "Medium · متوسط"), "low": ("t-neu", "Low · منخفض")}
    for lv, ar_t, en_t, ar_m, en_m in RISKS:
        cls, lab = rmap[lv]
        rrows += (f'<tr><td><span class="tag {cls}">{lab}</span></td>'
                  f'<td><b>{en_t}</b><br><span class="ar" style="color:var(--ink2)">{ar_t}</span></td>'
                  f'<td>{en_m}<br><span class="ar" style="color:var(--ink2)">{ar_m}</span></td></tr>')
    pages.append(f"""
    <div class="page">
     {rh("11 · Risks & mitigations","المخاطر وإجراءات المعالجة")}
     {sec("11","Risks & Mitigations","المخاطر وإجراءات المعالجة")}
     <div class="bi">
      <div class="e">A report that only shows good news is not a report. These are the five things that could
       reduce your income over the next twelve months, ranked, with what we are doing about each.</div>
      <div class="a">التقرير الذي يعرض الأخبار الجيدة فقط ليس تقريرًا. هذه هي الأمور الخمسة التي قد تخفّض دخلك
       خلال الاثني عشر شهرًا القادمة، مرتبةً حسب الأهمية، ومعها ما نقوم به تجاه كل منها.</div>
     </div>
     <table>
      <tr><th style="width:15%">Level<span class="ta">المستوى</span></th>
          <th style="width:38%">Risk<span class="ta">الخطر</span></th>
          <th style="width:47%">Mitigation<span class="ta">إجراء المعالجة</span></th></tr>
      {rrows}
     </table>
     <div class="call dark">
      <div class="h">The honest downside case / السيناريو السلبي بصراحة</div>
      <p>If the summer trough is deeper than modelled and district supply keeps growing at the H1 rate, full-year
         net to you lands nearer <b>SAR {sar(fy26_net["low"])}</b> rather than SAR {sar(fy26_net["base"])}.
         That is still <b>SAR {sar(fy26_net["low"] - ej_net)}</b> above the annual-lease alternative — so the
         downside case does not change the underlying decision, it only narrows the margin.</p>
      <p class="a">إذا كان ركود الصيف أعمق من المتوقع واستمر نمو العرض في الحي بنفس وتيرة النصف الأول، فسيكون
         صافي دخلك السنوي أقرب إلى <b>{sar(fy26_net["low"])} ريال</b> بدلًا من {sar(fy26_net["base"])} ريال.
         ومع ذلك يبقى أعلى بـ <b>{sar(fy26_net["low"] - ej_net)} ريال</b> من بديل العقد السنوي — أي أن السيناريو
         السلبي لا يغيّر القرار الأساسي، بل يقلّص الهامش فقط.</p>
     </div>
     {rf()}
    </div>""")

    # ---------- P12 PROJECTION ----------
    def scen_row(lab_en, lab_ar, d_g, d_n):
        return (f'<tr><td>{lab_en} · <span class="ar">{lab_ar}</span></td>'
                f'<td class="num">{sar(d_g["low"])}</td><td class="num">{sar(d_g["base"])}</td><td class="num">{sar(d_g["high"])}</td></tr>'
                f'<tr class="sub-t"><td style="padding-left:16pt">→ net to owner · صافي المالك</td>'
                f'<td class="num">{sar(d_n["low"])}</td><td class="num">{sar(d_n["base"])}</td><td class="num">{sar(d_n["high"])}</td></tr>')
    a_en = "".join(f"<li>{x}</li>" for x in PROJECTION["assumptions_en"])
    a_ar = "".join(f"<li>{x}</li>" for x in PROJECTION["assumptions_ar"])
    pages.append(f"""
    <div class="page dense">
     {rh("12 · Forward projection","التوقعات المستقبلية")}
     {sec("12","Forward Projection & Year-End Close","التوقعات المستقبلية وإقفال السنة")}
     <div class="bi">
      <div class="e">Built from this unit's own actuals, not a market average. Three scenarios — a single number
       would be a false promise.</div>
      <div class="a">مبنية على الأداء الفعلي لهذه الوحدة، لا على متوسط السوق. ثلاثة سيناريوهات — لأن رقمًا واحدًا
       سيكون وعدًا غير صادق.</div>
     </div>

     <h3 class="sub">Projected year-end close, 31 Dec 2026 <span>الإقفال المتوقع في 31 ديسمبر 2026</span></h3>
     <div class="kpis">
      <div class="kpi"><div class="k">Gross revenue</div><div class="ka">إجمالي الإيراد</div>
        <div class="v">{sar(fy_gross)}</div><div class="s">SAR · H1 actual + H2 base</div></div>
      <div class="kpi hero"><div class="k">Net to owner</div><div class="ka">صافي المالك</div>
        <div class="v">{sar(fy_owner)}</div><div class="s">SAR · full year 2026</div></div>
      <div class="kpi"><div class="k">Net yield</div><div class="ka">العائد الصافي</div>
        <div class="v">{pct(str_net_y,1)}</div><div class="s">on SAR {sar(PRICE)}</div></div>
      <div class="kpi"><div class="k">vs annual lease</div><div class="ka">مقابل العقد السنوي</div>
        <div class="v">+{pct(delta_pct,0)}</div><div class="s">+SAR {sar(delta_abs)}</div></div>
     </div>
     {chart_scen()}
     <table>
      <tr><th style="width:34%">Scenario<span class="ta">السيناريو</span></th>
          <th class="num">Conservative<span class="ta">متحفظ</span></th>
          <th class="num">Base<span class="ta">أساسي</span></th>
          <th class="num">Upside<span class="ta">متفائل</span></th></tr>
      <tr class="sub-t"><td colspan="4">Gross revenue, SAR · إجمالي الإيراد بالريال</td></tr>
      {scen_row("FY 2026 (H1 actual + H2)","2026 (نصف فعلي + نصف متوقع)", fy26, fy26_net)}
      {scen_row("FY 2027 (full year)","2027 (سنة كاملة)", fy27, fy27_net)}
      <tr class="grand"><td>Annual-lease benchmark (Ejar) · مرجع العقد السنوي</td>
          <td class="num">{sar(ej_net)}</td><td class="num">{sar(ej_net)}</td><td class="num">{sar(ej_net)}</td></tr>
     </table>


     <div class="two">
      <div>
       <h3 class="sub">Assumptions <span>الافتراضات</span></h3>
       <ul class="bul">{a_en}</ul>
      </div>
      <div>
       <h3 class="sub">‎ <span>الافتراضات</span></h3>
       <ul class="bul a">{a_ar}</ul>
      </div>
     </div>
     <div class="note">The Ejar row is flat because the rent freeze bars any increase before {RENT_FREEZE["ends"]}.
       Projections are estimates, not guarantees, and are restated against actuals in the next report.
       <span class="ar" style="display:block;margin-top:2pt">صف "إيجار" ثابت لأن تجميد الإيجارات يمنع أي زيادة قبل
       {RENT_FREEZE["ends_ar"]}. والتوقعات تقديرات وليست ضمانات، وسنعيد تقييمها مقابل الأرقام الفعلية في التقرير القادم.</span></div>
     {rf()}
    </div>""")

    # ---------- P13 ACTION PLAN ----------
    arows = ""
    for ar_w, en_w, ar_t, en_t, ar_o, en_o in ACTIONS:
        arows += (f'<tr><td><b>{en_w}</b><br><span class="ar" style="color:var(--muted);font-size:7.6pt">{ar_w}</span></td>'
                  f'<td>{en_t}<br><span class="ar" style="color:var(--ink2)">{ar_t}</span></td>'
                  f'<td>{en_o}<br><span class="ar" style="color:var(--muted);font-size:7.6pt">{ar_o}</span></td></tr>')
    pages.append(f"""
    <div class="page">
     {rh("13 · 90-day action plan","خطة العمل لـ 90 يومًا")}
     {sec("13","90-Day Action Plan","خطة العمل لـ 90 يومًا")}
     <div class="bi">
      <div class="e">What we will do between now and the next report — and who is accountable for each item.
       You will be able to hold us to this list in October.</div>
      <div class="a">ما سننفّذه من الآن وحتى التقرير القادم — ومَن المسؤول عن كل بند. ويمكنك محاسبتنا على هذه
       القائمة في أكتوبر.</div>
     </div>
     <table>
      <tr><th style="width:16%">When<span class="ta">التوقيت</span></th>
          <th style="width:56%">Action<span class="ta">الإجراء</span></th>
          <th style="width:28%">Owner<span class="ta">المسؤول</span></th></tr>
      {arows}
     </table>

     <h3 class="sub">What we need from you <span>ما نحتاجه منك</span></h3>
     <div class="two">
      <div><ul class="bul">
       <li>Approval of the September soft-goods refresh budget (estimate to follow separately).</li>
       <li>Confirmation of any dates you intend to block for personal use in Q4, so we can protect the
           Riyadh Season rate ladder.</li>
       <li>Nothing else. Everything above is executed by Ouja at no additional charge beyond the
           {pct(COSTS["mgmt_fee_pct"],0)} management fee.</li>
      </ul></div>
      <div><ul class="bul a">
       <li>الموافقة على ميزانية تحديث المفروشات في سبتمبر (سيصلك التقدير في رسالة منفصلة).</li>
       <li>تأكيد أي تواريخ تنوي حجزها للاستخدام الشخصي في الربع الأخير، حتى نحمي سلّم أسعار موسم الرياض.</li>
       <li>لا شيء غير ذلك. كل ما سبق تنفّذه عوجا دون أي رسوم إضافية فوق رسوم الإدارة
           {pct(COSTS["mgmt_fee_pct"],0)}.</li>
      </ul></div>
     </div>

     <div class="call">
      <div class="h">Next report / التقرير القادم</div>
      <p>Full-year 2026 report, issued January 2027, restating every projection in this document against actuals.
         Monthly statements continue as normal.</p>
      <p class="a">تقرير سنة 2026 الكامل، يصدر في يناير 2027، ويعيد مقارنة كل توقع في هذا المستند بالأرقام
         الفعلية. وتستمر الكشوفات الشهرية كالمعتاد.</p>
     </div>
     {rf()}
    </div>""")

    # ---------- P14 APPENDIX ----------
    srows = "".join(f'<tr><td>{en}<br><span class="ar" style="color:var(--muted);font-size:7.6pt">{ar}</span></td>'
                    f'<td class="ar">{u}</td></tr>' for ar, en, u in SOURCES)
    pages.append(f"""
    <div class="page dense">
     {rh("14 · Methodology & sources","المنهجية والمصادر")}
     {sec("14","Methodology, Definitions & Sources","المنهجية والمصطلحات والمصادر")}
     <h3 class="sub">Definitions <span>المصطلحات</span></h3>
     <table>
      <tr><th style="width:24%">Term<span class="ta">المصطلح</span></th><th>Definition<span class="ta">التعريف</span></th></tr>
      <tr><td><b>ADR</b> · متوسط السعر اليومي</td><td>Accommodation revenue ÷ nights sold. · إيراد الإقامة ÷ الليالي المباعة.</td></tr>
      <tr><td><b>Occupancy</b> · الإشغال</td><td>Nights sold ÷ nights available. · الليالي المباعة ÷ الليالي المتاحة.</td></tr>
      <tr><td><b>RevPAR</b> · إيراد الليلة المتاحة</td><td>Accommodation revenue ÷ nights available. · إيراد الإقامة ÷ الليالي المتاحة.</td></tr>
      <tr><td><b>MPI / ARI / RGI</b></td><td>This unit's occupancy / ADR / RevPAR ÷ the comp-set average × 100.<br>
          <span class="ar">إشغال / سعر / إيراد الوحدة ÷ متوسط مجموعة المنافسين × 100.</span></td></tr>
      <tr><td><b>Net to owner</b> · صافي المالك</td><td>Gross revenue less channel fees, management fee and operating costs.<br>
          <span class="ar">إجمالي الإيراد ناقص رسوم المنصات ورسوم الإدارة والتكاليف التشغيلية.</span></td></tr>
      <tr><td><b>Gross yield</b> · العائد الإجمالي</td><td>Annual gross revenue ÷ purchase price (SAR {sar(PRICE)}).<br>
          <span class="ar">إجمالي الإيراد السنوي ÷ سعر الشراء ({sar(PRICE)} ريال).</span></td></tr>
      <tr><td><b>Net yield</b> · العائد الصافي</td><td>Annual net-to-owner ÷ purchase price. The number that is
          comparable to a bank return.<br>
          <span class="ar">صافي دخل المالك السنوي ÷ سعر الشراء. وهو الرقم القابل للمقارنة بعائد بنكي.</span></td></tr>
      <tr><td><b>Payback</b> · فترة الاسترداد</td><td>Capital deployed ÷ annual net income — years to recover the
          purchase from rental cash flow alone, before any capital appreciation.<br>
          <span class="ar">رأس المال ÷ صافي الدخل السنوي — عدد السنوات لاسترداد ثمن الشراء من التدفق الإيجاري وحده،
          دون احتساب ارتفاع قيمة العقار.</span></td></tr>
      <tr><td><b>Rent freeze</b> · تجميد الإيجارات</td><td>Royal Decree effective 25 Sept 2025: rents inside Riyadh's
          urban boundary are fixed for five years (new and existing leases), with automatic renewal.<br>
          <span class="ar">مرسوم ملكي نافذ من 25 سبتمبر 2025: تثبيت الإيجارات داخل النطاق العمراني للرياض لمدة خمس
          سنوات (للعقود الجديدة والقائمة)، مع التجديد التلقائي.</span></td></tr>
      <tr><td><b>Ejar</b> · إيجار</td><td>The Saudi Ministry of Housing's national rental contract platform. The benchmark used
          in this report is the registered annual lease rate of <b>SAR {sar(ej_gross)}</b> for a comparable unit in this compound.<br>
          <span class="ar">منصة العقود الإيجارية الوطنية التابعة لوزارة الإسكان. القيمة المرجعية المستخدمة في هذا التقرير
          هي قيمة العقد السنوي المسجّل <b>85,000 ريال</b> لوحدة مماثلة في نفس المجمع.</span></td></tr>
     </table>

     {rf()}
    </div>""")

    # ---------- 14 (cont.) SOURCES & BASIS ----------
    pages.append(f"""
    <div class="page dense">
     {rh("14 · Methodology & sources","المنهجية والمصادر")}
     {sec("14","Sources & Basis of Preparation","المصادر وأسس الإعداد")}
     <h3 class="sub">Data sources <span>مصادر البيانات</span></h3>
     <table>
      <tr><th style="width:52%">Source<span class="ta">المصدر</span></th><th>Used for<span class="ta">استُخدم في</span></th></tr>
      {srows}
     </table>

     <h3 class="sub">Basis of preparation <span>أسس الإعداد</span></h3>
     <div class="two">
      <div><ul class="bul">
       <li>Revenue is recognised on the check-out date, on an accrual basis.</li>
       <li>All figures exclude VAT unless stated. VAT is charged to the guest and remitted to ZATCA.</li>
       <li>Comp-set data comes from public listing rates and observed availability — an estimate, not audited data.
           Projections are management estimates and are not guaranteed.</li>
       <li><b>Capital appreciation is excluded.</b> The unit's value rises or falls the same way under either
           strategy, so it does not separate the two. Only the income yield differs.</li>
      </ul></div>
      <div><ul class="bul a">
       <li>يُعترف بالإيراد في تاريخ مغادرة الضيف، على أساس الاستحقاق.</li>
       <li>جميع الأرقام لا تشمل ضريبة القيمة المضافة ما لم يُذكر خلاف ذلك، فهي تُحصّل من الضيف وتُورّد للهيئة.</li>
       <li>بيانات المنافسين مجمّعة من الأسعار المعلنة والتوافر الملاحظ، وهي تقديرية وليست مدققة. والتوقعات
           تقديرات إدارية غير مضمونة.</li>
       <li><b>ارتفاع قيمة العقار غير محتسب.</b> قيمة الوحدة ترتفع أو تنخفض بنفس القدر في كلا الخيارين، فهو لا يفرّق
           بينهما. الفرق الوحيد هو في العائد الدخلي.</li>
      </ul></div>
     </div>

     <div class="call">
      <div class="h">Questions / للاستفسار</div>
      <p>Any line in this report can be traced back to source data on request — contact your Ouja account manager.</p>
      <p class="a">أي بند في هذا التقرير يمكن إرجاعه إلى مصدره الأصلي عند الطلب — تواصل مع مدير حسابك في عوجا.</p>
     </div>
     {rf()}
    </div>""")


    # ══════════════════════════════════════════════════════════════
    HTML = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
    <title>{REPORT["doc_ref"]}</title><style>{fonts_css()}{CSS}</style></head>
    <body>{''.join(pages)}</body></html>"""

    pdf_path = pathlib.Path(out_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    html_tmp = pdf_path.parent / "_report.html"
    html_tmp.write_text(HTML, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("file://" + str(html_tmp.resolve()))
        pg.wait_for_timeout(1400)
        pg.pdf(path=str(pdf_path), format="A4", print_background=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        b.close()
    return pdf_path
