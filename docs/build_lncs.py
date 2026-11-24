"""Build docs/paper-edge-medgemma-lncs.docx in Springer LNCS format from paper-edge-medgemma.md.

Run from the project folder:  py docs/build_lncs.py
The page setup, styles and running heads come from the Springer template docs/splnproc2510.docm. Its macros
(vbaProject.bin), ribbon (customUI) and sample chart are left out, and its sample body is replaced. Text uses the
template's own styles: papertitle, author, address, abstract, keywords, heading1/heading2 (numbered by the
template), p1a for first paragraphs, bulletitem/numitem, image, figurecaption, tablecaption, acknowlegments and
referenceitem. References are given in Springer style below; the Markdown keeps its IEEE-style list.
"""
import io
import re
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

DOCS = Path(__file__).resolve().parent
SRC = DOCS / "paper-edge-medgemma.md"
TEMPLATE = DOCS / "splnproc2510.docm"
OUT = DOCS / "paper-edge-medgemma-lncs.docx"

SHORT_TITLE = "Sovereign Generative AI at the Edge"   # right running head
SHORT_AUTHORS = "E. Feluzy"                           # left running head
TEXT_W = Inches(4.8)                                   # LNCS text width, 12.2 cm
FIGURE_W = {"1": Inches(4.8), "2": Inches(4.8)}        # others use 4.5 in

# Springer reference style; order and numbering must match the Markdown's reference list.
REFERENCES = [
    "Ministry of Health of the Republic of Indonesia, Directorate General of Health Workforce: Profil Data Tenaga Kesehatan, Edisi Agustus 2023 [Health Workforce Data Profile, August 2023 edition]. Jakarta (2023), https://repositori-ditjen-nakes.kemkes.go.id/566/1/Profil%20Data%20Nakes%20Edisi%20Agustus%202023%20%281%29.pdf",
    "Badan Pusat Statistik (Statistics Indonesia): Banyaknya Desa/Kelurahan menurut Provinsi dan Penerimaan Sinyal Internet Telepon Seluler, 2025 [Number of villages by province and reception of mobile internet signal]. Statistics table, Jakarta (2025), https://www.bps.go.id/id/statistics-table/3/TDJsTlFXOXhXVW81VEZoa1EwUk1iRUphZEVkRFVUMDkjMyMwMDAw/banyaknya-desa-kelurahan-menurut-provinsi-dan-penerimaan-sinyal-internet-telepon-seluler.html?year=2025",
    "Singhal, K., et al.: Large language models encode clinical knowledge. Nature 620, 172–180 (2023)",
    "Sellergren, A., et al.: MedGemma technical report. arXiv:2507.05201 (2025)",
    "Republic of Indonesia: Law No. 27 of 2022 on Personal Data Protection (UU PDP) (2022)",
    "Gemma Team: Gemma 3 technical report. arXiv:2503.19786 (2025)",
    "MedGemma Team: MedGemma 1.5 technical report. arXiv:2604.05081 (2026)",
    "Jin, D., et al.: What disease does this patient have? A large-scale open domain question answering dataset from medical exams. Applied Sciences 11(14) (2021)",
    "Prakash, A., Ayyanathan, N.: Preventive healthcare through IoT and edge AI: A study on early detection and management of chronic and acute diseases (2026), https://ieeexplore.ieee.org/document/11742014 [venue, DOI]",
    "Frantar, E., et al.: GPTQ: Accurate post-training quantization for generative pre-trained transformers. In: International Conference on Learning Representations (ICLR) (2023)",
    "Basit, A., Hussain, K., Hanif, M.A., Shafique, M.: MedAide: Leveraging large language models for on-premise medical assistance on edge devices. arXiv:2403.00830 (2024)",
    "Lewis, P., et al.: Retrieval-augmented generation for knowledge-intensive NLP tasks. In: Advances in Neural Information Processing Systems 33 (NeurIPS) (2020)",
    "Ji, Z., et al.: Survey of hallucination in natural language generation. ACM Computing Surveys 55(12) (2023)",
    "Heryawan, L., Mori, Y., et al.: Fast Healthcare Interoperability Resources (FHIR)–based interoperability design in Indonesia: Content analysis of developer hub's social networking service. JMIR Formative Research (2025), https://formative.jmir.org/2025/1/e51270",
    "Ministry of Health of Indonesia: Regulation No. 24 of 2022 on Medical Records (Permenkes 24/2022) (2022)",
    "World Health Organization: Ethics and Governance of Artificial Intelligence for Health. WHO, Geneva (2021)",
    "World Health Organization: Ethics and Governance of Artificial Intelligence for Health: Guidance on Large Multi-Modal Models. WHO, Geneva (2024)",
    "Qwen Team: Qwen2.5 technical report. arXiv:2412.15115 (2024)",
    "Nussbaum, Z., et al.: Nomic Embed: Training a reproducible long context text embedder. arXiv:2402.01613 (2024)",
]
DISCLOSURE = "[Declare any competing interests, or state that the authors have no competing interests to declare.]"


# ---------------------------------------------------------------- template without macros
def clean_template():
    """Return the template as an in-memory .docx: no VBA, ribbon or sample chart; running heads filled in."""
    src = zipfile.ZipFile(TEMPLATE)
    out = io.BytesIO()
    drop = re.compile(r"^(customUI/|word/vbaProject\.bin|word/vbaData\.xml|word/_rels/vbaProject\.bin\.rels|word/charts/)")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            name = item.filename
            if drop.match(name) or name.endswith("/"):
                continue
            data = src.read(name)
            if name == "[Content_Types].xml":
                text = data.decode("utf-8-sig")
                text = text.replace("application/vnd.ms-word.document.macroEnabled.main+xml",
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
                text = re.sub(r'<Override PartName="/(word/vbaData\.xml|word/charts/[^"]*|customUI/[^"]*)"[^>]*/>', "", text)
                text = re.sub(r'<Default Extension="bin"[^>]*/>', "", text)
                data = text.encode("utf-8")
            elif name in ("_rels/.rels", "word/_rels/document.xml.rels"):
                text = data.decode("utf-8-sig")
                text = re.sub(r'<Relationship [^>]*Target="[^"]*(customUI|vbaProject|charts/)[^"]*"[^>]*/>', "", text)
                data = text.encode("utf-8")
            elif name == "word/header1.xml":
                data = data.decode("utf-8").replace("F. Author and S. Author", SHORT_AUTHORS).encode("utf-8")
            elif name == "word/header2.xml":
                data = data.decode("utf-8").replace("Contribution Title (shortened if too long) ", SHORT_TITLE + " ").encode("utf-8")
            dst.writestr(name, data)
    out.seek(0)
    return out


# ---------------------------------------------------------------- text helpers
def convert_refs(text):
    """Springer style: 'Fig. 3', 'Figs. 3 and 4', 'Sect. 3.2' (but 'Section' at the start of a sentence)."""
    text = re.sub(r"\bFigures (\d+) and (\d+)", r"Figs. \1 and \2", text)
    text = re.sub(r"\bFigure (\d+)", r"Fig. \1", text)

    def section(m):
        before = text[:m.start()].rstrip()
        if not before or before[-1] in ".!?":
            return m.group(0)
        return "Sects." if m.group(0) == "Sections" else "Sect."
    return re.sub(r"\bSections?\b(?= \d)", section, text)


INLINE = re.compile(r"(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|<https?://[^>]+>)")


def add_inline(paragraph, text, size=None, bold=False):
    for part in INLINE.split(text):
        if not part:
            continue
        b, i, mono = bold, False, False
        if part.startswith("**") and part.endswith("**"):
            part, b = part[2:-2], True
        elif part.startswith("`") and part.endswith("`"):
            part, mono = part[1:-1], True
        elif part.startswith("<http") and part.endswith(">"):
            part = part[1:-1]
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            part, i = part[1:-1], True
        segments = re.split(r"\*([^*]+)\*", part) if "*" in part else [part]
        for j, seg in enumerate(segments):
            if not seg:
                continue
            run = paragraph.add_run(seg)
            run.bold = b or None
            run.italic = (not i) if j % 2 else (i or None)
            if mono:
                run.font.name = "Courier New"
                run.font.size = Pt(9)
            elif size is not None:
                run.font.size = size


def labelled(doc, style, label, text, size=None):
    """Caption-like paragraph: bold run-in label, then the text."""
    p = doc.add_paragraph(style=style)
    run = p.add_run(label)
    run.bold = True
    add_inline(p, " " + text, size=size)
    return p


# ---------------------------------------------------------------- tables
def col_widths(header, rows, total, char_w):
    minimum, average = [], []
    for j in range(len(header)):
        column = [header[j]] + [r[j] for r in rows if j < len(r)]
        # Capitals are wider than the average character, so they count 1.5
        longest = max(sum(1.5 if ch.isupper() else 1 for ch in w.strip("*`")) for c in column for w in c.split())
        minimum.append(longest * char_w + Inches(0.14))  # word plus the 2 x 70-twip cell margins
        average.append(max(1, sum(len(c) for c in column[1:]) / max(1, len(column) - 1)))
    spare = total - sum(minimum)
    if spare <= 0:
        return [int(total * m / sum(minimum)) for m in minimum]
    return [int(m + spare * a / sum(average)) for m, a in zip(minimum, average)]


def border(cell, **edges):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge, size in edges.items():
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tc_pr.append(borders)


def render_table(doc, header, rows):
    wide = len(header) >= 6   # Table 3 has nine columns in a 12.2 cm text width
    size = Pt(7.5) if wide else Pt(9)
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.alignment = 1  # centre
    widths = col_widths(header, rows, TEXT_W, Inches(0.06 if wide else 0.068))
    for grid_col, w in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), widths):
        grid_col.set(qn("w:w"), str(int(w / 635)))
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    table._tbl.tblPr.append(layout)
    # Narrow cell margins (70 twips), as in the template's sample table; Word's default 108 eats narrow columns
    margins = OxmlElement("w:tblCellMar")
    for side in ("left", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), "70")
        el.set(qn("w:type"), "dxa")
        margins.append(el)
    table._tbl.tblPr.append(margins)
    last = len(rows)
    for i, row in enumerate([header] + rows):
        tr_pr = table.rows[i]._tr.get_or_add_trPr()
        tr_pr.append(OxmlElement("w:cantSplit"))
        for j, text in enumerate(row):
            cell = table.cell(i, j)
            cell.width = widths[j]
            # Springer tables: rule above and below the header, rule below the last row
            if i == 0:
                border(cell, top=12, bottom=6)
            elif i == last:
                border(cell, bottom=12)
            p = cell.paragraphs[0]
            p.paragraph_format.first_line_indent = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.keep_with_next = len(rows) <= 6 and i < last
            add_inline(p, text, size=size)


# ---------------------------------------------------------------- document
def build():
    md = SRC.read_text(encoding="utf-8")
    md_refs = re.findall(r"^\d+\. ", md.split("## References", 1)[1], flags=re.M)
    assert len(md_refs) == len(REFERENCES), f"Markdown has {len(md_refs)} references, LNCS list has {len(REFERENCES)}"
    blocks = [b.strip("\n") for b in re.split(r"\n\s*\n", md) if b.strip()]

    doc = Document(clean_template())
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)

    first = True        # next body paragraph is the first after a heading, list, table or figure -> p1a
    after_table = False # the paragraph after a table gets space above it
    in_references = False
    pending_caption = None
    skipped_notes = 0
    i = 0
    while i < len(blocks):
        block = blocks[i]
        head = block.splitlines()[0]

        if block == "---":
            i += 1
            continue
        if head.startswith("# "):
            title, _, subtitle = head[2:].strip().partition("? ")
            doc.add_paragraph(title + ("?" if subtitle else ""), style="papertitle")
            if subtitle:
                doc.add_paragraph(subtitle, style="papersubtitle")
            i += 1
            continue
        if block.startswith("> "):
            skipped_notes += 1    # draft banner and TODO notes are not part of the submission
            i += 1
            continue
        if block.startswith("**Erfin"):
            doc.add_paragraph("Erfin Feluzy", style="author")
            address = doc.add_paragraph("[Affiliation]", style="address")
            address.add_run().add_break(WD_BREAK.LINE)
            address.add_run("[email]")
            i += 1
            continue
        if head == "## Abstract":
            p = doc.add_paragraph(style="abstract")
            p.add_run("Abstract. ").bold = True
            add_inline(p, blocks[i + 1])
            i += 2
            continue
        if block.startswith("**Keywords:**"):
            p = doc.add_paragraph(style="keywords")
            p.add_run("Keywords:").bold = True
            add_inline(p, " " + block.split("**Keywords:**", 1)[1].strip())
            i += 1
            continue

        if head.startswith("## "):
            title = re.sub(r"^\d+\.\s+", "", head[3:].strip())
            if title == "Acknowledgement":
                text = blocks[i + 1]
                p = doc.add_paragraph(style="acknowlegments")
                run = p.add_run("Acknowledgments.")
                run.style = doc.styles["heading3"]
                p.add_run(" ")
                add_inline(p, text)
                p = doc.add_paragraph(style="acknowlegments")
                run = p.add_run("Disclosure of Interests.")
                run.style = doc.styles["heading3"]
                p.add_run(" " + DISCLOSURE)
                i += 2
                continue
            h = doc.add_paragraph(title, style="heading1")
            if title == "References":
                in_references = True
                ppr = h._p.get_or_add_pPr()
                num_pr = OxmlElement("w:numPr")
                ilvl, num_id = OxmlElement("w:ilvl"), OxmlElement("w:numId")
                ilvl.set(qn("w:val"), "0")
                num_id.set(qn("w:val"), "0")
                num_pr.extend([ilvl, num_id])
                ppr.append(num_pr)
                for ref in REFERENCES:
                    item = doc.add_paragraph(ref, style="referenceitem")
                    item.alignment = WD_ALIGN_PARAGRAPH.LEFT  # long URLs stretch justified lines
            first = True
            i += 1
            continue
        if head.startswith("### "):
            doc.add_paragraph(re.sub(r"^\d+\.\d+\s+", "", head[4:].strip()), style="heading2")
            first = True
            i += 1
            continue
        if in_references:
            i += 1
            continue

        if re.match(r"\*Table \d+\.", block):
            pending_caption = block
            i += 1
            continue
        if block.startswith("|"):
            rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in block.splitlines()]
            header, data = rows[0], rows[2:]
            if pending_caption:
                m = re.match(r"\*Table (\d+)\.\s*(.*?)\*$", pending_caption.strip(), re.S)
                cap = labelled(doc, "tablecaption", f"Table {m.group(1)}.", convert_refs(m.group(2)))
                cap.paragraph_format.keep_with_next = True
                pending_caption = None
            render_table(doc, [convert_refs(c) for c in header], [[convert_refs(c) for c in r] for r in data])
            first = after_table = True
            i += 1
            continue

        m = re.match(r"!\[[^\]]*\]\(([^)]+)\)", block)
        if m:
            cap = re.match(r"\*Figure (\d+)\.\s*(.*?)\*$", blocks[i + 1].strip(), re.S)
            number, text = cap.group(1), convert_refs(cap.group(2))
            p = doc.add_paragraph(style="image")
            p.paragraph_format.keep_with_next = True
            p.add_run().add_picture(str(DOCS / m.group(1)), width=FIGURE_W.get(number, Inches(4.5)))
            caption = labelled(doc, "figurecaption", f"Fig. {number}.", text)
            # Short captions are centred, long ones justified (template rule)
            caption.alignment = WD_ALIGN_PARAGRAPH.CENTER if len(text) < 90 else WD_ALIGN_PARAGRAPH.JUSTIFY
            first = True
            i += 2
            continue

        lines = block.splitlines()
        if all(l.startswith("- ") for l in lines):
            for l in lines:
                add_inline(doc.add_paragraph(style="bulletitem"), convert_refs(l[2:]))
            first = True
            i += 1
            continue
        if all(re.match(r"\d+\. ", l) for l in lines):
            for l in lines:
                add_inline(doc.add_paragraph(style="numitem"), convert_refs(re.sub(r"^\d+\.\s+", "", l)))
            first = True
            i += 1
            continue

        p = doc.add_paragraph(style="p1a" if first else "Normal")
        if after_table:
            p.paragraph_format.space_before = Pt(10)
        add_inline(p, convert_refs(" ".join(lines)))
        first = after_table = False
        i += 1

    doc.core_properties.title = re.match(r"# (.*)", md).group(1)
    doc.core_properties.author = "Erfin Feluzy"
    doc.save(OUT)
    print("written", OUT, f"(left out {skipped_notes} draft notes)")


if __name__ == "__main__":
    build()
