# «لوك عوجا» — The Ouja Look

> **The reference for everything Ouja makes:** web pages, the dashboard, PDFs, Word files,
> studies, decks, charts, technical drawings, WhatsApp images.
> Source of truth: the guest site **oujares.com/apartments** (`STAY_HTML` in `bot.py`, 2026-11 redesign).
> When this file and the site disagree, the site wins. Fix this file.
> Owner decision, 2026-11-22.

**Files in this folder**
| File | What it is |
|---|---|
| `OUJA_LOOK.md` | This guide: the rules and the reasons behind them |
| `ouja-tokens.css` | Colours, type, spacing and base components as CSS. Paste into any new web page |
| `ouja-tokens.json` | The same values for Python, PDF, Word, charts and drawings |
| `templates/report-a4.html` | A4 print template for studies, reports and proposals (RTL) |
| `templates/build_pdf.py` | Turns any HTML in this look into a PDF with the fonts embedded |
| `templates/make_docx.py` → `templates/ouja-word-template.docx` | Word template with the styles set |

---

## ملخص للمالك

1. **ثلاث ألوان:** ورق بلون حجر الرياض، وحبر غامق دافي، وذهبي. الذهبي للعلامات بس، والأزرار دايم حبر.
2. **خطين:** «ثمانية سيرف» للعناوين الكبيرة والأرقام، و«ثمانية سانس» لكل شيء ينقرى.
3. **فرق كبير بين الأحجام:** العنوان كبير وواضح، والنص مريح، والصغير هادي.
4. **الصورة هي الكرت.** نفصل الأقسام بخطوط رفيعة بدل الصناديق، وما نحط صندوق داخل صندوق.
5. **مساحة واسعة بين الأقسام.** الصفحة تتنفس.
6. **كل شيء ينضغط مدوّر وكبير** بحجم الإصبع.
7. **لحظة وحدة كبيرة في كل صفحة.** الباقي هادي.
8. **حركة خفيفة وسريعة**، وما فيها نطّ.
9. **كلام قصير بالنجدي، يبدأ بالفعل**، وكل رقم له مصدر، وما نذكر عدد الشقق.
10. **النهاية غامقة:** الفوتر أو القسم الأخير يقفل الصفحة.

---

## 1. Why /apartments works

These are the reasons behind every rule below. When a new case comes up, decide it from these.

1. **One world, not a palette.** Riyadh limestone by day (paper), Najdi night (ink), one saffron-gold
   thread. Every colour has a job. Nothing is decoration.
2. **Gold is a mark, never a surface.** Stars, the selected day, the active underline, step numbers,
   the tick on a bar. White text on gold measures 3.87:1 and fails, so buttons are ink.
3. **Two faces, two jobs.** The serif is for display moments: the hero, section titles, big figures,
   the wordmark. The sans is for reading. A paragraph is never set in the serif.
4. **Hierarchy comes from size, not colour or boxes.** The hero is 6× the body text. You can read the
   page from its headings alone.
5. **The photo is the card.** Listing cards have no border, no shadow and no box. A rounded photo,
   then text under it. Boxes are kept for things you act on: the search bar, the booking panel, sheets.
6. **Hairlines instead of containers.** Lists, steps and the neighbourhood index are separated by
   1px lines. There are never cards inside cards.
7. **Generous rhythm.** 64–128px between sections and a 1240px measure. Nothing is crowded, so the
   one big moment can be big.
8. **One type moment per page.** On the home page it is the neighbourhood index in 54px serif. Every
   page gets one such moment and only one.
9. **Thumb-first.** Pill controls 52px tall, never under 44px. A bottom sheet on the phone and a
   centred dialog on desktop. Sticky booking bar on the unit page.
10. **Motion you feel, not see.** One ease curve. Press shrinks to 0.97. Under 300ms for anything
    you touch. Respects reduced motion.
11. **Honest words.** Short Najdi sentences that start with a verb. Real reviews with first names.
    No unit counts, no superlatives, no "luxury".
12. **A dark bookend.** The page closes on night ink, the same way the hero opens on a dark photo.

**What it avoids** (the AI-slop list it was built against): purple/blue gradients, gradient text,
glassmorphism as decoration, cards in cards, pure #000 or #888 greys, grey text on colour, bounce
easing, emoji icons, Inter for everything, letter-spaced Arabic, centred everything, stock photos,
"Discover luxury living" copy.

---

## 2. Colour

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#F4EFE7` | The page ground. Riyadh limestone |
| `--paper2` | `#ECE5D9` | Quiet fills: image placeholders, hover, secondary chips, table footers |
| `--card` | `#FBF8F3` | Raised surfaces: sheets, panels, tiles, inputs on paper. Never pure white |
| `--ink` | `#1D1813` | Text, buttons, the selected state. Najdi night ink |
| `--ink2` | `#463C33` | Body copy and descriptions |
| `--mut` | `#6B5F52` | Captions, meta, hints, placeholders |
| `--line` | `#DCD2C3` | Hairlines and control outlines |
| `--line2` | `#E8E1D5` | Softer hairlines inside cards and sheets |
| `--gold` | `#A57A2C` | **Marks only:** stars, step numerals, selected-day dot, underline accent, focus ring |
| `--gold-soft` | `#EBDDC2` | The selected date range, gentle notice banners |
| `--night` | `#15110D` | Dark bookend: footer, dark sections, the lightbox, photo overlays |
| `--night2` | `#231C16` | Raised surfaces on night |
| `--ok` | `#2E6A49` | Licensed, available, done |
| `--warn` | `#8A4B2A` | Notices. Errors use `#7A3420` on `#F6E2DA` |
| hover ink | `#3A3027` | Button hover |
| on night | `rgba(244,239,231,.78)` / `.62` | Body / meta text on night |
| night accent | `#B07F2F` | Gold on night (dashboard night mode) |

**Measured contrast (WCAG):**
| Text \ ground | paper | paper2 | card | night |
|---|---|---|---|---|
| ink `#1D1813` | 15.4 | 14.1 | 16.6 | — |
| ink2 `#463C33` | 9.4 | 8.6 | 10.1 | — |
| mut `#6B5F52` | 5.4 | 5.0 | 5.9 | 3.0 ✗ |
| gold `#A57A2C` | 3.4 ✗ text | 3.1 ✗ | 3.7 ✗ | 4.9 |
| paper on ink | 15.4 | | | |

So: **gold is never small text on a light ground** (marks, 24px+ numerals and underlines only).
**`--mut` is never used on night.** Use the on-night values there.

**Proportion:** about 80% paper, 15% ink, 5% gold and everything else. A page that looks gold has
too much gold.

---

## 3. Type

**Faces** (self-hosted, never Google Fonts):
- **Thmanyah Serif Display**: weights 700 and 900. Display moments only. CSS family `"Thmanyah Serif"`.
- **Thmanyah Sans**: weights 400, 500 and 700. Everything that is read. CSS family `"Thmanyah Sans"`.
- Fallbacks: serif → `"Thmanyah Sans", Georgia, serif`. Sans → `system-ui, -apple-system, "Segoe UI", sans-serif`.
- Files: `monthly_public/static/fonts/thmanyah-*.v20260827a.woff2` (served at `/monthly/static/fonts/`)
  and `fonts/Thmanyah*.woff2`. See §14 for the licence before using them anywhere new.

**Scale (web)**: fluid sizes using `clamp(min, preferred, max)`.
| Role | Face / weight | Size | Line height |
|---|---|---|---|
| Hero (over photo) | Serif 900 | `clamp(44px,10vw,100px)`, max 11ch | 1.16 |
| Hero (no photo, long sentence) | Serif 900 | `clamp(36px,5.4vw,68px)`, max 15ch | 1.2 |
| Page title | Serif 700 | `clamp(32px,5vw,56px)` | 1.12 |
| Section title (h2) | Serif 700 | `clamp(30px,5vw,54px)` | 1.12–1.16 |
| The page's one type moment | Serif 700 | `clamp(30px,5.2vw,54px)` | 1.2 |
| Big figure | Serif 700/900 | 30–120px, tabular numerals | 1 |
| Block title | Sans 700 | 20–22px | 1.35 |
| Card / item title | Sans 700 | 17–18px | 1.4 |
| Lede | Sans 400 | `clamp(17px,2.1vw,21px)` | 1.6 |
| Body | Sans 400 | 16px | 1.7 |
| Long reading (descriptions, reviews) | Sans 400 | 16.5–17px, max 68ch | 1.85 |
| UI / meta | Sans 500 | 14–15px | 1.5 |
| Caption / fine print | Sans 400 | 12.5–13.5px | 1.65 |
| Latin label (`OUJA RESIDENCE`) | Sans 700 | 10.5–13px, `letter-spacing:.18–.24em`, uppercase | 1 |

**Print scale** (A4, from `ouja-tokens.json`): cover 40pt serif 900 · h1 26pt serif 700 ·
h2 18pt serif 700 · h3 12.5pt sans 700 · body 10.5pt sans 400 / 1.75 · caption 8.5pt · big figure 30pt serif 700.

**Rules**
- **No letter-spacing on Arabic, ever.** It breaks the joins. Latin-only labels may track.
- Headings use `text-wrap: balance`. Body copy never goes past 68 characters a line.
- Numbers use `font-variant-numeric: tabular-nums` and `unicode-bidi: isolate`. Western digits (21,000,
  not ٢١٬٠٠٠), as in Saudi business documents. Step numerals may be Arabic-Indic (١ ٢ ٣) in gold.
- One weight jump at a time: 900 for the single biggest moment, 700 for titles, 400/500 for the rest.
- Never italic Arabic. Never underline for emphasis: use weight.

---

## 4. Space and layout

| Token | Value |
|---|---|
| Page padding `--pad` | `clamp(16px,4.4vw,44px)` |
| Measure `--maxw` | 1240px (reading pages 760px) |
| Section gap | `clamp(64px,10vw,128px)` |
| Section header → content | `clamp(24px,3.4vw,40px)` |
| Card grid gap | 34px rows × 22px columns |
| Tile grid gap | 10–14px |
| Block inside a page | 30px top and bottom, hairline between |
| Radius | 14px (`--r`) controls and inputs · 16–18px tiles · 22px (`--r-lg`) photos and panels · 24–26px sheets · 999px pills |
| Header | 64px, sticky, paper at 92% with a blur, hairline once scrolled |
| Breakpoints | 430 · 600 · 640 · 760 · 900 · 960 · 1024 |

- Grids: 1 column → 2 at 640px → 3 at 1024px. On phones, horizontal rails scroll with snap
  (82% card width) instead of shrinking cards.
- Right-to-left first: use logical properties (`inset-inline-start`, `padding-inline`,
  `margin-inline`), never left/right.
- One ground per page (paper). Do not alternate white and beige bands; space separates sections.
  The only band change is the night bookend.

---

## 5. Components

**Button**: pill, 52px tall (small: 44px), `0 24px` padding, ink on paper, Sans 700 16px.
Hover `#3A3027`. Press `scale(.97)` at 120ms. Variants: ghost (inset 1.5px ink ring), light
(paper on night), WhatsApp (green ring). Disabled: paper2 with mut text. **Never gold. Never a gradient.**

**Link**: Sans 700, underline 1.5px, offset 5px, underline colour gold. The underline turns ink on hover.

**Chip / filter**: pill 40px, card fill with an inset 1px `--line` ring, 14.5px weight 500. Selected:
ink fill, paper text, no ring.

**Tag on a photo**: 28px pill, card at 94%, 12.5px weight 700. The "available" tag is ok-green with a light dot.

**Listing card** (photo-as-card): 4:3 photo with 22px radius, zoom 1.03 on hover over 600ms, press 0.985.
Under it: a meta row (area · ★ rating in gold), a 2-line clamped Sans 700 18px title, meta with
3px dots, and the price with the figure in bold. No box.

**Tile** (amenities, scores, doors): card fill, inset 1px `--line2`, radius 16, padding 16–22px,
icon 28px at stroke 1.4.

**Panel** (booking, comparisons): card fill, radius 22, `0 0 0 1px var(--line)` ring plus a
`0 24px 60px rgba(29,24,19,.08)` shadow. At most one per screen.

**Hairline list** (steps, neighbourhoods, governance): 1px `--line` between rows, no boxes. Numerals
are serif in gold.

**Sheet / drawer**: bottom sheet on the phone (radius 24 at the top, slides up on
`cubic-bezier(.32,.72,0,1)` over 420ms, with a grab handle). Centred 600px dialog on desktop
(scale .97 → 1, 300ms). Scrim `rgba(21,17,13,.46)`. Sticky footer with a "clear" link and the action button.

**Form field**: 52px, radius 14, card or paper fill, inset 1px `--line` ring. Focus: inset 2px ink ring.
Labels above the field in Sans 700 13px. Input text is 16px (stops iOS zoom).

**Banner**: gold-soft fill, radius 14, an ink line of text with a warn-coloured icon.

**Stats row**: up to 4 figures divided by `--line2` hairlines. Figure in Sans 700 20–26px, label in mut 13px.

**Review**: card tile with radius 18, a gold quote icon, the quote in Sans 16.5px at 1.85 line
height, then first name + stay + month in mut. The quote is printed as written.

**Header**: wordmark «عوجا» in serif 900 28px plus `OUJA RESIDENCE` tracked Latin (hidden under 430px).
Nav links are 44px pills.

**Footer**: night ground, wordmark 40px, links paper with a 35% underline, fine print 13px at 62%.

**Icons**: 20px line icons, stroke 1.6, round caps and joins, `currentColor`. Never emoji in UI.

**Empty and loading**: a shimmer skeleton in the real shape. Empty states get a serif title, one
honest sentence and two actions.

---

## 6. Motion

- Ease `cubic-bezier(.23,1,.32,1)` for everything. Drawer/sheet `cubic-bezier(.32,.72,0,1)`.
- Press: `scale(.97)` at 120ms (cards 0.985). Never `scale(0)`. Never bounce.
- Hover colour: 200ms. Image zoom: 600ms to 1.03. Sheet: 420ms. Page entrance: rise 14px over 900ms,
  staggered 80ms, once only.
- Animate `transform` and `opacity` only. Do not animate things that auto-refresh.
- `prefers-reduced-motion`: every duration drops to near zero.

---

## 7. Imagery

- Real photos of our own units only. A photo always shows the unit it is labelled as.
- 4:3 for cards, 3:4 for tall feature tiles, full-bleed for the hero. Radius 22.
- Text on a photo only over a night gradient (`rgba(21,17,13,…)`), never over a flat grey veil.
- No stock photos, no AI renders as the look, no cartoons, no emoji illustrations.
- Above the fold: load eagerly. Below the fold: lazy-load in WebP through the image proxy.

---

## 8. Words

- Najdi, casual and warm. Short sentences that start with a verb: «اختر شقتك من هنا»,
  «ادخل بنفسك».
- Say the thing, then stop. No "نفخر", "تجربة استثنائية", "فخامة", "اكتشف".
- **Never state an apartment count** (owner rule, 2026-11-13), in any medium.
- Every figure has a source and a date. If a number is not backed, it does not render.
- SAR as «ريال» in running text, «ر.س» in tables. Western digits.
- Names of units start «عوجا |» on channels. The Arabic site uses no prefix.
- Run `stop-slop` / `humanizer` on any long text before it ships.

---

## 9. Applying it per medium

### Web pages (any new page, any site)
1. Start from `ouja-tokens.css`. Load only the five font files.
2. Pick the page's **one** type moment before writing any CSS.
3. Build mobile first at 375px, then 760, then 1240.
4. Run the checklist in §12. For pages embedded in `bot.py` as strings, CLAUDE.md's backslash trap
   applies: esprima-parse every script.

### Dashboard and team tools
Already on these tokens (the «عوجا look» stages 1–3, `tests/test_ouja_tokens.py`). Night mode uses
`--night` with the `#B07F2F` accent. Same component rules. Density can go up (14px body), but the
faces and colours do not change.

### PDFs: studies, reports, proposals, statements, company documents
1. Write the document as HTML on `templates/report-a4.html`. It has A4 pages, RTL, a cover, a
   section opener, figures, a table, a callout and a footer with page numbers.
2. Build it: `python3 docs/brand/templates/build_pdf.py my-study.html my-study.pdf`.
   Chromium embeds a subset of the fonts in the PDF, so it looks the same on any phone.
3. Print rules: white page with paper only on the cover and section openers (saves ink), 18mm
   margins, a running header with the wordmark and title, page numbers bottom-left, tables with
   hairlines only (no zebra fills, no vertical rules), figures in serif.
4. Anything sent outside the company goes out as a **PDF**, never as a Word file.

### Word documents
- Use `templates/ouja-word-template.docx` (styles: Title, Subtitle, Heading 1–3, Normal, Caption,
  Quote, plus a sample hairline table to copy). Write in the styles; never hand-format.
- Right-to-left trap: inside an Arabic paragraph Word reads "left/right" alignment logically. Leave
  paragraphs unaligned (they start on the right), and set figure cells to "right" to put them on the
  visual left. `make_docx.py` does this.
- Word needs the fonts **installed** on the computer that opens it: download Thmanyah from
  thmanyah.com (the licence allows only that source). Without it, Word substitutes a system font, so
  Word is for drafts that people edit. The final version leaves as PDF.
- Generated documents (python-docx): load the template, `doc = Document("ouja-word-template.docx")`,
  and only use its named styles.

### Slides and decks
- 16:9, paper ground, one idea per slide, a serif headline (36–54pt), Sans body (18–24pt), at most
  3 lines of body text.
- One big figure per slide in serif 900 with its source in mut 12pt under it.
- Photo slides are full-bleed with a night gradient under the text.
- Close on a night slide (the bookend). No templates with blue headers, no clip-art icons.

### Charts and data
- Series order: **ink** `#1D1813` (us / the main series) → **gold** `#A57A2C` (the highlight or
  target) → **mut** `#6B5F52` → `#B8AD9F` → ok `#2E6A49` / warn `#8A4B2A` only for good/bad meaning.
  The market or comparison series is always mut or `#D3C7B5`, never a colour that competes with ink.
- Hairline gridlines in `--line2`, no chart borders, no 3D, no pie charts over 4 slices.
- Label the line directly instead of a legend where possible. Figures in tabular Sans.
- Use the `dataviz` skill for method, with these colours swapped into its palette.

### Technical drawings, floor plans, dimensions (2D)
- Use the `dimensional-drawing` skill with this palette: ink lines on paper. Dimension lines in mut
  at 0.5pt, the critical dimension in gold, room labels in Sans 500, the title block in the
  report-a4 footer style.
- Line weights: walls 0.7mm ink, furniture 0.25mm ink2, dimensions 0.18mm mut.
- Units in mm on drawings and in m² in text. North arrow and scale bar on every plan.

### WhatsApp, social and image cards
- 1080×1350 (4:5) or 1080×1080. Paper or full-bleed photo with a night gradient.
- Serif headline, at most 2 lines. Wordmark bottom-right. No more than one gold mark.

### Email
- Plain and single-column, 600px wide, paper background, an ink button, Sans with system fallbacks
  (email clients drop web fonts).

---

## 10. Skills behind it, and how to use them

| Skill | Used for | When |
|---|---|---|
| **ouja-look** (this guide as a skill) | Loads these rules | First, before any design work |
| **taste-skill** | Anti-slop: one system, real photos, one dealt moment per page | Building or redesigning any page |
| **impeccable** | Critique → audit → polish → harden. Typeset, colorize, layout | Before shipping any UI |
| **emil-design-eng** | The feel: press states, ease curves, sheets, timing | Interactions and motion |
| **oil-ui** | Exploring three directions side by side, screenshot review | When a new page needs a direction |
| **brand-identity** | Measuring contrast, glyph coverage, font licences | When the identity itself changes |
| **dimensional-drawing** | Spec sheets and dimensioned drawings | Technical 2D deliverables |
| **dataviz** | Chart method | Any chart |
| **anthropic-skills:pdf / docx / pptx** | File mechanics | Producing the file, after this guide sets the look |
| **stop-slop / humanizer** | Removing AI-sounding text | Any long text |

**Order of work:** ouja-look → (taste-skill + emil for building) → impeccable audit → the checklist
→ screenshots at 375px and 1366px → the owner.

---

## 11. Banned

Gold buttons · gradients on buttons or text · pure `#000`, `#fff` page grounds, or `#888` greys ·
cards inside cards · borders and shadows on listing cards · letter-spaced Arabic · italic Arabic ·
Inter, Almarai, Tajawal, IBM Plex or Cairo as the main face · Google Fonts links · emoji as icons ·
bounce or elastic easing · animating width/height/top · more than one hero-size moment per page ·
alternating beige/white bands · stock photos · the words "luxury", "discover", "exceptional" ·
apartment counts · a number without a source · "None", "undefined", "NaN" or "[object Object]"
reaching a reader.

---

## 12. Checklist before anything ships

- [ ] Only tokens from `ouja-tokens.css/json`: no new hex values.
- [ ] Two faces, the right weights, no tracking on Arabic.
- [ ] One type moment. Everything else is quiet.
- [ ] Gold used only as marks. Buttons are ink.
- [ ] Every text/ground pair is ≥ 4.5:1 (≥ 3:1 for 24px+).
- [ ] Every tap target is ≥ 44px. Inputs are 16px.
- [ ] Looked at 375px and 1366px. No sideways scroll.
- [ ] RTL with logical properties. Numbers isolated.
- [ ] Motion ≤ 300ms for UI, with reduced motion respected.
- [ ] No apartment count. Every figure has a source. No "None".
- [ ] Copy run through stop-slop.
- [ ] PDF: fonts embedded (`pdffonts file.pdf` lists Thmanyah), A4, page numbers.

---

## 13. Where it already lives

- `/apartments` (`STAY_HTML`): the source.
- Dashboard, Finance Center, `/team`, and the side pages: tokens adopted in commits a31ae1f and c2f249a.
  Locked by `tests/test_ouja_tokens.py`.
- `/cp` company profile: moved to this look on 2026-11-22 (`cp/templates/ar_v2.html`, `cp/templates/fonts.css`).
- `/elite` (`ELITE_HTML`): moved to this look on 2026-11-25, the VIP twin of /apartments with WhatsApp-only
  booking. Locked by `tests/test_elite_look.py`.
- Not yet: `/monthly`, `/guide`, the `/cp` PDF, owner statements, and the other print documents.

## 14. Font licence (Thmanyah, read before using the files anywhere new)

The licence (`fonts/LICENSE-Thmanyah.pdf`) **allows** commercial use in branding, websites, printed
materials and design work, and **embedding in documents we create** (PDF, Word). It **forbids**
redistributing the font files, converting or modifying them, and making them extractable as files
"including through web embedding". So:
- PDFs and Word files with embedded fonts: allowed.
- Never send the font files to anyone, never put them in a shared zip or a skill upload, and never
  convert them (woff2 → ttf). Install them from thmanyah.com on each machine.
- **Open question for the owner:** our websites serve the woff2 files as plain public URLs. A strict
  reading of the "web embedding" clause asks for something less extractable. Ask Thmanyah
  (ask@thmanyah.com) for written confirmation of web use, or an extended licence.
