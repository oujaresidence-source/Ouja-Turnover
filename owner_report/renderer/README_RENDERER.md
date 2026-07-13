# Ouja Owner Report — Renderer Kit

## The contract

`ouja_render.py` is **FROZEN**. It owns 100% of the visual output: fonts, colours,
spacing, CSS, SVG chart geometry, page layout, PDF pipeline.

You build the **data pipeline**. You do not touch the renderer.

```python
from ouja_render import render_report, REPORT_SCHEMA
render_report(cfg_dict, "out.pdf")     # cfg_dict must satisfy REPORT_SCHEMA
```

## Files

| File | Purpose |
|---|---|
| `ouja_render.py` | **FROZEN.** The renderer. Do not edit. |
| `fonts/` | IBM Plex Sans Arabic + Latin, embedded as base64 at render time. |
| `reference_data.py` | The reference `cfg`. This is the data contract, field by field. |
| `golden_reference.pdf` | The approved 17-page design. This is what output must look like. |
| `golden_fingerprint.json` | Per-page pixel + text hashes of the approved design. |
| `test_render_frozen.py` | **CI gate.** Proves the renderer is unmodified. Must always pass. |
| `audit_layout.py` | **Per-report gate.** Proves real data didn't break the layout. |

## The two gates

**1. `test_render_frozen.py`** — run in CI on every commit.
Renders `reference_data.py` and compares pixel-by-pixel to the golden.
It catches a single changed hex digit. If it fails, someone edited the renderer.
**Do not update the golden to make it pass.** Find the change and revert it.

**2. `audit_layout.py`** — run on every generated report, before release.
The golden test proves the renderer is intact; this proves *live data* didn't break it.
A long unit name, a 6-row comp set, or an unusually large number can still push
content past the footer or clip a chart label.

```python
from audit_layout import assert_clean
assert_clean(html)     # raises if the layout is broken
```

Zero violations, or the PDF does not go to an owner.
