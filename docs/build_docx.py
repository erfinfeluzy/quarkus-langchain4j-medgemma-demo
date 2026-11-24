"""Build docs/paper-edge-medgemma.docx from paper-edge-medgemma.md in IEEE two-column style (Times New Roman).

Run from the project folder:  py docs/build_docx.py
Layout: US Letter; title, authors and abstract span the page; body in two 3.5-inch columns. Sections become
"I. INTRODUCTION" (small caps) and subsections "A. ..." (italic); in-text "Section 3.2" becomes "Section III-B",
"Figure 3" becomes "Fig. 3" and "Table 3" becomes "Table III". Wide tables and figures span both columns.
"""
import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

DOCS = Path(__file__).resolve().parent
SRC = DOCS / "paper-edge-medgemma.md"
OUT = DOCS / "paper-edge-medgemma.docx"

FONT, CODE_FONT = "Times New Roman", "Courier New"
BODY, SMALL = Pt(10), Pt(8)
GREY = RGBColor(0x59, 0x59, 0x59)
COLUMN_W, PAGE_W = Inches(3.5), Inches(7.25)
FULL_WIDTH_FIGURES = {"1", "2"}       # architecture and the four MRI images
FULL_WIDTH_TABLE_MIN_COLS = 6         # Table III (nine columns) spans the page

ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# ---------------------------------------------------------------- cross references
def section_ref(token):
    """'3.2' -> 'III-B', '5' -> 'V'."""
    parts = token.split(".")
    if not parts[0].isdigit() or int(parts[0]) >= len(ROMAN):
        return token
    out = ROMAN[int(parts[0])]
    if len(parts) > 1 and parts[1].isdigit():
        out += "-" + LETTERS[int(parts[1]) - 1]
    return out


def convert_refs(text):
    text = re.sub(r"\b(Sections?) (\d+(?:\.\d+)?(?:(?:, | and |–)\d+(?:\.\d+)?)*)",
                  lambda m: m.group(1) + " " + re.sub(r"\d+(?:\.\d+)?", lambda n: section_ref(n.group(0)), m.group(2)),
                  text)
    text = re.sub(r"\bFigures (\d+) and (\d+)", r"Figs. \1 and \2", text)
    text = re.sub(r"\bFigure (\d+)", r"Fig. \1", text)
    text = re.sub(r"\bTables? (\d+)\b", lambda m: m.group(0).split()[0] + " " + ROMAN[int(m.group(1))], text)
    return text


# ---------------------------------------------------------------- low-level formatting
def set_run_font(run, name=FONT, size=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), name)
    if size is not None:
        run.font.size = size


def style_font(style, size, bold=False, italic=False, small_caps=False):
    style.font.name = FONT
    style.font.size = size
    style.font.bold = bold
    style.font.italic = italic
    style.font.small_caps = small_caps
    style.font.color.rgb = RGBColor(0, 0, 0)
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)
    for theme in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(theme), None)


def set_columns(section, num):
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        section._sectPr.append(cols)
    cols.set(qn("w:num"), str(num))
    cols.set(qn("w:space"), "360")  # 0.25 inch gap


def page_setup(section, columns):
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin, section.bottom_margin = Inches(0.75), Inches(1.0)
    section.left_margin = section.right_margin = Inches(0.625)
    set_columns(section, columns)


def new_section(doc, columns):
    section = doc.add_section(WD_SECTION.CONTINUOUS)
    page_setup(section, columns)
    return section


def shade(paragraph, fill="F2F2F2"):
    ppr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.append(shd)


INLINE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|<https?://[^>]+>)")


def add_inline(paragraph, text, size=BODY, italic=False, bold=False, color=None):
    """Markdown inline -> runs: **bold**, *italic*, `code`, <url>."""
    for part in INLINE.split(text):
        if not part:
            continue
        b, i, font, s = bold, italic, FONT, size
        if part.startswith("**") and part.endswith("**"):
            part, b = part[2:-2], True
        elif part.startswith("`") and part.endswith("`"):
            part, font, s = part[1:-1], CODE_FONT, Pt(size.pt - 1)
        elif part.startswith("<http") and part.endswith(">"):
            part = part[1:-1]
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            part, i = part[1:-1], not italic
        # Nested italic inside bold, e.g. **...*x*...**
        for j, seg in enumerate(re.split(r"\*([^*]+)\*", part) if "*" in part else [part]):
            if not seg:
                continue
            run = paragraph.add_run(seg)
            set_run_font(run, font, s)
            run.bold = b
            run.italic = (not i) if j % 2 else i
            if color is not None:
                run.font.color.rgb = color


def body_paragraph(doc, text, indent=True):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    fmt = p.paragraph_format
    fmt.space_before, fmt.space_after = Pt(0), Pt(0)
    if indent:
        fmt.first_line_indent = Inches(0.14)
    add_inline(p, text)
    return p


def note(doc, text):
    """TODO blocks and the draft banner: small grey italic on a light background."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(3), Pt(3)
    shade(p)
    add_inline(p, text, size=SMALL, italic=True, color=GREY)
    return p


def caption(doc, text, align=WD_ALIGN_PARAGRAPH.JUSTIFY, before=Pt(3), after=Pt(8)):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before, p.paragraph_format.space_after = before, after
    add_inline(p, text, size=SMALL)
    return p


# ---------------------------------------------------------------- block renderers
def render_list(doc, items, numbered):
    for n, item in enumerate(items, 1):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        fmt = p.paragraph_format
        fmt.left_indent, fmt.first_line_indent = Inches(0.25), Inches(-0.17)
        fmt.space_before, fmt.space_after = Pt(1), Pt(1)
        marker = f"{n})" if numbered else "•"
        run = p.add_run(marker + "\t")
        set_run_font(run, FONT, BODY)
        fmt.tab_stops.add_tab_stop(Inches(0.25))
        add_inline(p, item)


def parse_table(lines):
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    return rows[0], [r for r in rows[2:]]


def col_widths(header, rows, total):
    """Each column gets at least the width of its longest word at 8 pt (no mid-word breaks); the rest of the
    width is shared in proportion to the average cell length."""
    char_w, padding = Inches(0.062), Inches(0.16)
    minimum, average = [], []
    for j in range(len(header)):
        column = [header[j]] + [r[j] for r in rows if j < len(r)]
        longest_word = max(len(w.strip("*`")) for c in column for w in c.split())
        minimum.append(longest_word * char_w + padding)
        average.append(max(1, sum(len(c) for c in column[1:]) / max(1, len(column) - 1)))
    spare = total - sum(minimum)
    if spare <= 0:  # cannot fit every word; scale the minimums
        return [int(total * m / sum(minimum)) for m in minimum]
    return [int(m + spare * a / sum(average)) for m, a in zip(minimum, average)]


def render_table(doc, header, rows, width):
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    widths = col_widths(header, rows, width)
    # Word lays out from the table grid, so set it as well as each cell's width
    for grid_col, w in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), widths):
        grid_col.set(qn("w:w"), str(int(w / 635)))  # EMU -> twips
    tbl_layout = OxmlElement("w:tblLayout")
    tbl_layout.set(qn("w:type"), "fixed")
    table._tbl.tblPr.append(tbl_layout)
    for i, row in enumerate([header] + rows):
        for j, cell_text in enumerate(row):
            cell = table.cell(i, j)
            cell.width = widths[j]
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(1)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i == 0 else WD_ALIGN_PARAGRAPH.LEFT
            add_inline(p, cell_text, size=SMALL, bold=(i == 0))
            if i == 0:
                tc_pr = cell._tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:fill"), "E7E6E6")
                tc_pr.append(shd)
    # Header row repeats if the table breaks across columns or pages
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)
    # Keep short tables together: rows never split, and each row stays with the next. Long tables (Table V)
    # may still break between rows, so a column is never left with only a header.
    keep_together = len(rows) <= 6
    for r_index, row in enumerate(table.rows):
        cant_split = OxmlElement("w:cantSplit")
        row._tr.get_or_add_trPr().append(cant_split)
        if keep_together and r_index < len(table.rows) - 1:
            for cell in row.cells:
                for para in cell.paragraphs:
                    para.paragraph_format.keep_with_next = True
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)
    return table


def table_caption(doc, text):
    m = re.match(r"\*?Table (\d+)\.\s*(.*?)\*?$", text.strip())
    number, rest = m.group(1), m.group(2)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(8), Pt(0)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(f"TABLE {ROMAN[int(number)]}")
    set_run_font(run, FONT, SMALL)
    p2 = caption(doc, convert_refs(rest), align=WD_ALIGN_PARAGRAPH.CENTER, before=Pt(0), after=Pt(3))
    p2.paragraph_format.keep_with_next = True


def figure(doc, path, caption_text, width):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(DOCS / path), width=width)
    m = re.match(r"\*?Figure (\d+)\.\s*(.*?)\*?$", caption_text.strip(), re.S)
    caption(doc, f"Fig. {m.group(1)}. " + convert_refs(m.group(2)))


# ---------------------------------------------------------------- document
def build():
    md = SRC.read_text(encoding="utf-8")
    blocks = [b.strip("\n") for b in re.split(r"\n\s*\n", md) if b.strip()]

    doc = Document()
    styles = doc.styles
    style_font(styles["Normal"], BODY)
    styles["Normal"].paragraph_format.space_after = Pt(0)
    styles["Normal"].paragraph_format.line_spacing = 1.0
    style_font(styles["Heading 1"], BODY, small_caps=True)
    style_font(styles["Heading 2"], BODY, italic=True)
    for name, before, after in (("Heading 1", 10, 4), ("Heading 2", 6, 2)):
        pf = styles[name].paragraph_format
        pf.space_before, pf.space_after, pf.keep_with_next = Pt(before), Pt(after), True
    page_setup(doc.sections[0], 1)

    two_column = False
    section_no, sub_no = 0, 0
    in_references = False
    pending_table_caption = None
    i = 0
    while i < len(blocks):
        block = blocks[i]
        first = block.splitlines()[0]

        if block == "---":
            i += 1
            continue

        # Title, banner, authors (single-column front matter)
        if first.startswith("# "):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(10)
            run = p.add_run(first[2:].strip())
            set_run_font(run, FONT, Pt(24))
            i += 1
            continue
        if block.startswith("> ") and not two_column and "Working draft" in block:
            note(doc, block[2:])
            i += 1
            continue
        if block.startswith("**Erfin"):
            names = [s.strip() for s in block.split("·")]
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(6)
            run = p.add_run(names[0].strip("*"))
            set_run_font(run, FONT, Pt(11))
            for extra in names[1:]:
                q = doc.add_paragraph()
                q.alignment = WD_ALIGN_PARAGRAPH.CENTER
                add_inline(q, extra, size=Pt(10), italic=True)
            doc.paragraphs[-1].paragraph_format.space_after = Pt(12)
            i += 1
            continue
        if first == "## Abstract":
            abstract = blocks[i + 1]
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run = p.add_run("Abstract—")
            set_run_font(run, FONT, Pt(9))
            run.bold = run.italic = True
            add_inline(p, abstract, size=Pt(9), bold=True)
            i += 2
            continue
        if block.startswith("**Keywords:**"):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(6), Pt(12)
            run = p.add_run("Index Terms—")
            set_run_font(run, FONT, Pt(9))
            run.bold = run.italic = True
            terms = block.split("**Keywords:**", 1)[1].strip()
            add_inline(p, terms[0].upper() + terms[1:], size=Pt(9), bold=True)
            i += 1
            continue

        # Section headings; the first numbered section starts the two-column body
        if first.startswith("## "):
            title = first[3:].strip()
            if not two_column:
                new_section(doc, 2)
                two_column = True
            m = re.match(r"(\d+)\.\s+(.*)", title)
            if m:
                section_no, sub_no = int(m.group(1)), 0
                text = f"{ROMAN[section_no]}. {m.group(2)}"
            else:
                text = title
                in_references = title.lower() == "references"
            h = doc.add_heading(level=1)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = h.add_run(text)
            set_run_font(run, FONT, BODY)
            i += 1
            continue
        if first.startswith("### "):
            title = re.sub(r"^\d+\.\d+\s+", "", first[4:].strip())
            sub_no += 1
            h = doc.add_heading(level=2)
            run = h.add_run(f"{LETTERS[sub_no - 1]}. {title}")
            set_run_font(run, FONT, BODY)
            i += 1
            continue

        # Notes (TODO blocks)
        if block.startswith("> "):
            note(doc, convert_refs(" ".join(l[2:] for l in block.splitlines())))
            i += 1
            continue

        # Table caption precedes its table
        if re.match(r"\*Table \d+\.", block):
            pending_table_caption = block
            i += 1
            continue
        if block.startswith("|"):
            header, rows = parse_table(block.splitlines())
            header = [convert_refs(c) for c in header]
            rows = [[convert_refs(c) for c in r] for r in rows]
            wide = len(header) >= FULL_WIDTH_TABLE_MIN_COLS
            if wide:
                new_section(doc, 1)
            if pending_table_caption:
                table_caption(doc, pending_table_caption)
                pending_table_caption = None
            render_table(doc, header, rows, PAGE_W if wide else COLUMN_W)
            if wide:
                new_section(doc, 2)
            i += 1
            continue

        # Figures: image line followed by its caption block
        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)", block)
        if m:
            cap = blocks[i + 1]
            number = re.match(r"\*Figure (\d+)", cap).group(1)
            wide = number in FULL_WIDTH_FIGURES
            if wide:
                new_section(doc, 1)
            figure(doc, m.group(1), cap, Inches(6.9) if wide else Inches(3.45))
            if wide:
                new_section(doc, 2)
            i += 2
            continue

        # Lists
        lines = block.splitlines()
        if all(l.startswith("- ") for l in lines):
            render_list(doc, [convert_refs(l[2:]) for l in lines], numbered=False)
            i += 1
            continue
        if all(re.match(r"\d+\. ", l) for l in lines):
            items = [re.sub(r"^\d+\.\s+", "", l) for l in lines]
            if in_references:
                for n, item in enumerate(items, 1):
                    item = re.sub(r"\s+—\s+\*[^*]+\*\s*$", "", item)  # drop draft source-tier labels
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT  # long URLs leave gaps when justified
                    fmt = p.paragraph_format
                    fmt.left_indent, fmt.first_line_indent = Inches(0.3), Inches(-0.3)
                    fmt.space_after = Pt(0)
                    fmt.tab_stops.add_tab_stop(Inches(0.3))
                    run = p.add_run(f"[{n}]\t")
                    set_run_font(run, FONT, SMALL)
                    add_inline(p, item, size=SMALL)
            else:
                render_list(doc, [convert_refs(t) for t in items], numbered=True)
            i += 1
            continue

        body_paragraph(doc, convert_refs(" ".join(lines)))
        i += 1

    # A closing continuous break makes Word balance the two columns on the last page, as IEEE papers do.
    # The paragraphs around it are made 1 pt high so a full last page does not spill onto a blank one.
    new_section(doc, 1)
    from docx.enum.text import WD_LINE_SPACING
    for para in (doc.paragraphs[-1], doc.add_paragraph()):
        fmt = para.paragraph_format
        fmt.space_before = fmt.space_after = Pt(0)
        fmt.line_spacing_rule, fmt.line_spacing = WD_LINE_SPACING.EXACTLY, Pt(1)
        mark = para._p.get_or_add_pPr().get_or_add_rPr() if hasattr(para._p.get_or_add_pPr(), "get_or_add_rPr") else None
        if mark is not None:
            size = OxmlElement("w:sz")
            size.set(qn("w:val"), "2")
            mark.append(size)
    doc.core_properties.title = re.match(r"# (.*)", md).group(1)
    doc.core_properties.author = "Erfin Feluzy"
    doc.save(OUT)
    print("written", OUT)


if __name__ == "__main__":
    build()
