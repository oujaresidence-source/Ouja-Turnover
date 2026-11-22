#!/usr/bin/env python3
"""Build ouja-word-template.docx: a right-to-left A4 Word template in the «لوك عوجا» look.

    pip install python-docx
    python3 docs/brand/templates/make_docx.py            # writes ouja-word-template.docx next to this file

Styles set: Normal, Title, Subtitle, Heading 1-3, Caption, Quote, and a sample hairline table to copy.
Fonts are referenced by NAME only. Nothing is embedded or converted (the Thmanyah licence forbids
converting the files). Word shows them only where Thmanyah is installed from thmanyah.com.
Elsewhere it substitutes, which is why anything sent outside the company goes as PDF.
"""
import json
import pathlib

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

HERE = pathlib.Path(__file__).resolve().parent
TOK = json.loads((HERE.parent / "ouja-tokens.json").read_text(encoding="utf-8"))
C = TOK["color"]
SERIF = "Thmanyah Serif Display"
SANS = "Thmanyah Sans"


def rgb(hex_):
    return RGBColor.from_string(hex_.lstrip("#").upper())


def set_fonts(rpr_owner, family, size_pt, color, bold=False):
    """Latin and complex-script (Arabic) slots both, or Arabic silently falls back."""
    font = rpr_owner.font
    font.name = family
    font.size = Pt(size_pt)
    font.bold = bold
    font.color.rgb = rgb(color)
    rpr = rpr_owner.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for slot in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(slot), family)
    for tag, val in (("w:szCs", str(int(size_pt * 2))),):
        el = rpr.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            rpr.append(el)
        el.set(qn("w:val"), val)
    if bold:
        if rpr.find(qn("w:bCs")) is None:
            rpr.append(OxmlElement("w:bCs"))
    rtl = rpr.find(qn("w:rtl"))
    if rtl is None:
        rpr.append(OxmlElement("w:rtl"))


def set_para(style, before=0, after=6, line=1.5, keep_next=False):
    pf = style.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.keep_with_next = keep_next
    # no explicit alignment: a bidi paragraph starts on the right by itself. Word reads
    # left/right LOGICALLY inside bidi paragraphs, so 'RIGHT' would push text to the left.
    ppr = style.element.get_or_add_pPr()
    if ppr.find(qn("w:bidi")) is None:
        ppr.append(OxmlElement("w:bidi"))


def hairline_bottom(paragraph, color, size=4):
    ppr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", str(size)), ("w:space", "6"), ("w:color", color.lstrip("#"))):
        b.set(qn(k), v)
    bdr.append(b)
    ppr.append(bdr)


def hairline_table(table):
    tbl = table._tbl
    tblpr = tbl.tblPr
    bidi = OxmlElement("w:bidiVisual")
    tblpr.append(bidi)
    borders = OxmlElement("w:tblBorders")
    for edge, sz, col in (("top", 0, "FFFFFF"), ("left", 0, "FFFFFF"), ("right", 0, "FFFFFF"),
                          ("bottom", 6, C["ink"]), ("insideH", 4, C["line2"]), ("insideV", 0, "FFFFFF")):
        el = OxmlElement("w:" + edge)
        el.set(qn("w:val"), "nil" if sz == 0 else "single")
        if sz:
            el.set(qn("w:sz"), str(sz))
            el.set(qn("w:color"), col.lstrip("#"))
        borders.append(el)
    tblpr.append(borders)


def main():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = Mm(18)
    sec.top_margin, sec.bottom_margin = Mm(22), Mm(20)
    sectpr = sec._sectPr
    sectpr.append(OxmlElement("w:bidi"))

    st = doc.styles
    set_fonts(st["Normal"], SANS, 10.5, C["ink2"])
    set_para(st["Normal"], after=6, line=1.6)
    set_fonts(st["Title"], SERIF, 34, C["ink"], bold=True)
    set_para(st["Title"], after=10, line=1.15)
    tpr = st["Title"].element.get_or_add_pPr()
    for b in tpr.findall(qn("w:pBdr")):
        tpr.remove(b)
    set_fonts(st["Subtitle"], SANS, 13, C["ink2"])
    set_para(st["Subtitle"], after=18, line=1.5)
    set_fonts(st["Heading 1"], SERIF, 22, C["ink"], bold=True)
    set_para(st["Heading 1"], before=24, after=8, line=1.2, keep_next=True)
    set_fonts(st["Heading 2"], SERIF, 16, C["ink"], bold=True)
    set_para(st["Heading 2"], before=18, after=6, line=1.25, keep_next=True)
    set_fonts(st["Heading 3"], SANS, 12, C["ink"], bold=True)
    set_para(st["Heading 3"], before=12, after=4, line=1.3, keep_next=True)
    set_fonts(st["Caption"], SANS, 8.5, C["mut"])
    set_para(st["Caption"], after=10, line=1.4)
    set_fonts(st["Quote"], SANS, 11.5, C["ink"])
    set_para(st["Quote"], before=8, after=8, line=1.7)
    for name in ("Heading 1", "Heading 2", "Heading 3", "Title", "Subtitle", "Caption", "Quote"):
        st[name].font.italic = False

    # header / footer: the wordmark and the page number
    hp = sec.header.paragraphs[0]
    hp.style = st["Caption"]
    hp.text = "عوجا · OUJA RESIDENCE"
    hairline_bottom(hp, C["line"])

    doc.add_paragraph("دراسة · سرّي", style="Caption")
    doc.add_paragraph("عنوان المستند في سطرين بالكثير", style="Title")
    doc.add_paragraph("جملة وحدة تقول وش يلقى القارئ في هالملف، ولمين هو.", style="Subtitle")
    meta = doc.add_paragraph("22 نوفمبر 2026 · فريق عوجا · النسخة 1.0", style="Caption")
    hairline_bottom(meta, C["line"])

    doc.add_paragraph("الخلاصة", style="Heading 1")
    doc.add_paragraph("اكتب الجواب أول، والتفاصيل بعدين. فقرة قصيرة بدون مقدمات. "
                      "كل رقم له مصدر وتاريخ، ولا تذكر عدد الشقق.")
    doc.add_paragraph("عنوان فرعي", style="Heading 2")
    doc.add_paragraph("نص عادي بخط ثمانية سانس. لا تغيّر الخط أو اللون يدوياً — استخدم الأنماط من شريط الأنماط.")
    doc.add_paragraph("نقطة صغيرة", style="Heading 3")
    doc.add_paragraph("«اقتباس من ضيف أو مالك، مكتوب مثل ما قاله.» — الاسم الأول · الشهر 2026", style="Quote")

    doc.add_paragraph("جدول (انسخه واستخدمه)", style="Heading 3")
    rows = [("البند", "القيمة · ريال", "النسبة"), ("بند أول", "12,400", "41%"),
            ("بند ثاني", "9,800", "33%"), ("المجموع", "22,200", "74%")]
    table = doc.add_table(rows=len(rows), cols=3)
    hairline_table(table)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = table.cell(r, c)
            para = cell.paragraphs[0]
            para.text = val
            para.style = st["Caption"] if r == 0 else st["Normal"]
            if c:  # figures sit at the END of the cell (visual left), logically 'right' in bidi
                para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if r in (0, len(rows) - 1):
                for run in para.runs:
                    run.font.bold = True
    doc.add_paragraph("المصدر: اسم المصدر، الشهر والسنة.", style="Caption")

    out = HERE / "ouja-word-template.docx"
    doc.save(out)
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
