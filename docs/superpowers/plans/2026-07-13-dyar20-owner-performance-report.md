# DYAR 20 Owner Performance Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a polished bilingual PowerPoint that explains DYAR 20's H1 2026 performance, market position, competitors, and H2 scenarios.

**Architecture:** A deterministic Python analysis script converts the supplied Hostaway CSV into a compact JSON model. A plain JavaScript ES module uses `@oai/artifact-tool` to build editable PowerPoint slides, native charts, rendered previews, and layout evidence. Research claims and URLs live in a source-note file and in presentation footers.

**Tech Stack:** Python standard library, JavaScript ES modules, `@oai/artifact-tool`, bundled slide render and test utilities.

---

### Task 1: Lock the analytical model

**Files:**
- Create: `/private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/analyze_dyar20.py`
- Create: `/private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/analysis.json`

- [ ] **Step 1: Parse the reservation export**

Read `/Users/faisalouja/Downloads/20260713_reservations_filtered.csv`, retain reservations overlapping 1 January–30 June 2026, and allocate cross-period reservations by night.

- [ ] **Step 2: Compute auditable KPIs**

Calculate accommodation revenue from Airbnb base price plus direct total, expected payout, unique-night occupancy, booked-night ADR, RevPAR, monthly performance, channel mix, lead-time buckets, stay-length buckets, weekday performance, and H2 scenarios.

- [ ] **Step 3: Run the model and inspect output**

Run:

```bash
/Users/faisalouja/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/analyze_dyar20.py
```

Expected: JSON reports SAR 98,388.83 accommodation revenue, 86.19% occupancy, SAR 618.80 ADR, and 63 period reservations.

### Task 2: Capture research and asset provenance

**Files:**
- Create: `/private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/source-notes.txt`
- Create: `/private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/assets/complex.jpg`

- [ ] **Step 1: Record market sources**

Document AirDNA's June 2026 Riyadh occupancy, ADR, RevPAR, active listing count, and trend figures; SAMA's SAR 3.75 USD rate; GASTAT tourism indicators; CBRE Q1 2026 context; the Dyar 20 developer page; and public Airbnb competitor URLs.

- [ ] **Step 2: Verify the property image**

Confirm `complex.jpg` is a valid 1200 × 871 JPEG sourced from the property's existing Google Drive asset.

### Task 3: Build the editable deck

**Files:**
- Create: `/private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/build_deck.mjs`
- Create: `/Users/faisalouja/Ouja-Turnover/outputs/DYAR20_H1_2026_Performance_Report_AR_EN.pptx`

- [ ] **Step 1: Initialize the artifact-tool workspace**

Run:

```bash
/Users/faisalouja/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node \
  /Users/faisalouja/.codex/plugins/cache/openai-primary-runtime/presentations/26.630.12135/skills/presentations/container_tools/setup_artifact_tool_workspace.mjs \
  --workspace /private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp
```

Expected: the scratch workspace resolves the bundled `@oai/artifact-tool` package.

- [ ] **Step 2: Author 14 bilingual slides**

Create the approved narrative, Arabic-first copy, native charts, competitor table, scenario ranges, source footers, and slide numbers. Use a 1280 × 720 canvas and the approved palette and typography.

- [ ] **Step 3: Export evidence and PowerPoint**

The builder must export each slide PNG, each layout JSON, a deck montage, and the final PPTX.

### Task 4: Verify and repair the presentation

**Files:**
- Inspect: `/private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/preview/`
- Inspect: `/private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/layout/`
- Inspect: `/private/tmp/codex-presentations/manual-dyar20/dyar20-h1-report/tmp/qa/`

- [ ] **Step 1: Run structural tests**

Run:

```bash
/Users/faisalouja/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  /Users/faisalouja/.codex/plugins/cache/openai-primary-runtime/presentations/26.630.12135/skills/presentations/container_tools/slides_test.py \
  /Users/faisalouja/Ouja-Turnover/outputs/DYAR20_H1_2026_Performance_Report_AR_EN.pptx
```

Expected: no content overflow outside the slide canvas.

- [ ] **Step 2: Inspect the full deck visually**

Open the montage and then inspect any dense slide at full size. Check bilingual line breaks, chart labels, table widths, footers, image crop, and text contrast.

- [ ] **Step 3: Repair and rerun**

Patch the builder, regenerate the deck, and repeat structural and visual checks until all severe defects are removed.

- [ ] **Step 4: Verify content reconciliation**

Confirm that the visible scorecard, monthly chart, channel mix, booking behavior, weekday analysis, market comparison, competitor table, and H2 scenarios match `analysis.json` and the recorded research sources.

