"""Build docs/dissertation-proposal.pptx: a dissertation proposal deck based on the paper (paper-edge-medgemma).

Run from the project folder:  py docs/build_proposal.py
The preliminary study is the paper; the research plan comes from its limitations and future work. All numbers are
taken from the paper (final benchmark run, bench/results/20261110-175216).
"""
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

DOCS = Path(__file__).resolve().parent
OUT = DOCS / "dissertation-proposal.pptx"

# Palette: deep teal (clinical, dominant), teal, mint tint, coral accent for the numbers that matter
DARK, TEAL, MINT, CORAL = "0B3C49", "1B7F79", "E3F1EE", "D9542F"
INK, MUTED, WHITE, LINE = "1F2933", "5F6B73", "FFFFFF", "C9D6D3"
HEAD, BODY = "Cambria", "Calibri"
SHORT = "Sovereign generative AI at the edge · Dissertation proposal"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
W = 13.333


def rgb(hex_):
    return RGBColor.from_string(hex_)


def background(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = rgb(color)


def text(slide, x, y, w, h, paragraphs, size=16, color=INK, font=BODY, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, space_after=6, name=None):
    """paragraphs: list of str or list of runs [(text, {bold, color, size, italic})]."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        box.name = name
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        runs = para if isinstance(para, list) else [(para, {})]
        for content, opts in runs:
            r = p.add_run()
            r.text = content
            r.font.name = opts.get("font", font)
            r.font.size = Pt(opts.get("size", size))
            r.font.bold = opts.get("bold", bold)
            r.font.italic = opts.get("italic", False)
            r.font.color.rgb = rgb(opts.get("color", color))
    return box


def bullets(slide, x, y, w, h, items, size=16, color=INK):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        p.level = 0
        # Real bullet via paragraph properties
        ppr = p._p.get_or_add_pPr()
        ppr.set("marL", str(int(Inches(0.25))))
        ppr.set("indent", str(-int(Inches(0.25))))
        bu = ppr.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}buChar", {"char": "•"})
        ppr.append(bu)
        runs = item if isinstance(item, list) else [(item, {})]
        for content, opts in runs:
            r = p.add_run()
            r.text = content
            r.font.name = BODY
            r.font.size = Pt(opts.get("size", size))
            r.font.bold = opts.get("bold", False)
            r.font.color.rgb = rgb(opts.get("color", color))
    return box


def shape(slide, kind, x, y, w, h, fill, line=None, name=None):
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if name:
        s.name = name
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = 0.08
    return s


def badge(slide, x, y, label, size=0.55, fill=TEAL, font_size=18):
    """Motif: a number or short label in a filled circle."""
    c = shape(slide, MSO_SHAPE.OVAL, x, y, size, size, fill)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.name, r.font.size, r.font.bold = BODY, Pt(font_size), True
    r.font.color.rgb = rgb(WHITE)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return c


def content_slide(title, number, notes):
    s = prs.slides.add_slide(BLANK)
    background(s, WHITE)
    text(s, 0.6, 0.45, 12.1, 0.9, [title], size=32, color=DARK, font=HEAD, bold=True, anchor=MSO_ANCHOR.TOP,
         name="Title")
    text(s, 0.6, 7.0, 9, 0.3, [SHORT], size=10, color=MUTED)
    text(s, 11.9, 7.0, 0.83, 0.3, [str(number)], size=10, color=MUTED, align=PP_ALIGN.RIGHT)
    s.notes_slide.notes_text_frame.text = notes
    return s


def picture(slide, path, x, y, max_w, max_h):
    iw, ih = Image.open(path).size
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    return slide.shapes.add_picture(str(path), Inches(x + (max_w - w) / 2), Inches(y), Inches(w), Inches(h))


def bar_chart(slide, x, y, w, h, categories, values, labels_text, title, color=TEAL, highlight=None, maximum=None):
    """labels_text: one label per bar, written as text so the decimal point does not follow the viewer's locale."""
    data = CategoryChartData()
    data.categories = categories
    data.add_series(title, values)
    frame = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), data)
    chart = frame.chart
    chart.has_legend = False
    chart.has_title = True
    chart.chart_title.text_frame.text = title
    tp = chart.chart_title.text_frame.paragraphs[0]
    tp.runs[0].font.size, tp.runs[0].font.bold, tp.runs[0].font.name = Pt(14), True, BODY
    tp.runs[0].font.color.rgb = rgb(INK)
    plot = chart.plots[0]
    plot.gap_width = 60
    series = plot.series[0]
    for point_index, label in enumerate(labels_text):
        dl = series.points[point_index].data_label
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        dl.text_frame.text = label
        run = dl.text_frame.paragraphs[0].runs[0]
        run.font.size, run.font.name = Pt(13), BODY
        run.font.color.rgb = rgb(INK)
    series.format.fill.solid()
    series.format.fill.fore_color.rgb = rgb(color)
    if highlight is not None:
        point = series.points[highlight]
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = rgb(CORAL)
    cat, val = chart.category_axis, chart.value_axis
    cat.tick_labels.font.size, cat.tick_labels.font.name = Pt(13), BODY
    cat.tick_labels.font.color.rgb = rgb(INK)
    cat.format.line.color.rgb = rgb(LINE)
    cat.reverse_order = True
    val.visible = False
    val.has_major_gridlines = False
    val.minimum_scale = 0
    if maximum is not None:
        val.maximum_scale = maximum   # headroom so the longest bar's label is not clipped
    return chart


# ------------------------------------------------------------------ 1. Title
s = prs.slides.add_slide(BLANK)
background(s, DARK)
text(s, 0.8, 0.9, 6, 0.4, ["DISSERTATION PROPOSAL"], size=14, color="8FD3C8", bold=True)
text(s, 0.8, 1.5, 11.5, 2.4, ["Can Sovereign Generative AI Run at the Edge?"], size=44, color=WHITE, font=HEAD,
     bold=True, anchor=MSO_ANCHOR.BOTTOM)
text(s, 0.8, 4.05, 11.5, 0.9, ["Offline medical AI for remote primary health centres in Indonesia"], size=24,
     color="CFE7E2", font=HEAD)
text(s, 0.8, 5.6, 8, 1.0, [[("Erfin Feluzy", {"bold": True, "color": WHITE})],
                           [("[Programme · University] · [Supervisors]", {"color": "CFE7E2"})],
                           [("November 2026", {"color": "CFE7E2"})]], size=16)
s.notes_slide.notes_text_frame.text = (
    "This proposal asks whether sovereign generative AI, running fully offline inside a remote health centre, "
    "can support primary care in Indonesia. A preliminary study, already written as a paper, shows that the "
    "complete stack runs on one consumer laptop. The dissertation extends it to accuracy, safety and use in the field.")

# ------------------------------------------------------------------ 2. Problem
s = content_slide("Remote primary care lacks doctors and connectivity", 2,
                  "Ministry of Health workforce data (August 2023): 351 of 10,445 PHCs had no doctor, concentrated in the "
                  "east; Papua alone has more than half of them. BPS village data (2025): 3,469 villages receive no "
                  "mobile internet signal. Nurses and midwives decide with little reference material, and a cloud "
                  "assistant cannot reach them.")
stats = [("351", "public health centres (PHCs) with no doctor, 3.4% of 10,445", "Ministry of Health, Aug 2023 [1]"),
         ("40.6%", "of PHCs in Papua have no doctor (192 of 473)", "Ministry of Health, Aug 2023 [1]"),
         ("3,469", "villages without a mobile internet signal, 4.12% of all villages", "Statistics Indonesia (BPS), 2025 [2]")]
for i, (big, label, source) in enumerate(stats):
    x = 0.6 + i * 4.1
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.9, 3.8, 3.6, MINT, name=f"Stat card {i + 1}")
    text(s, x + 0.35, 2.2, 3.1, 1.3, [big], size=60, color=CORAL, font=HEAD, bold=True)
    text(s, x + 0.35, 3.55, 3.1, 1.2, [label], size=17, color=INK)
    text(s, x + 0.35, 4.85, 3.1, 0.4, [source], size=11, color=MUTED)
text(s, 0.6, 5.9, 12.1, 0.8, [[("Nurses and midwives make decisions that would normally involve a physician — "
                                "often where a cloud service cannot be reached.", {"italic": True})]],
     size=18, color=DARK)

# ------------------------------------------------------------------ 3. Why not the cloud
s = content_slide("Cloud AI is the wrong fit for remote health centres", 3,
                  "Three reasons. Connectivity: a cloud assistant fails exactly where it is needed. Data protection: "
                  "to help at the point of care the assistant must read the patient record, and Law No. 27/2022 treats "
                  "health data as specific personal data and restricts its transfer abroad. Sovereignty: data, compute "
                  "and models should stay under national and facility control.")
rows = [("1", "Connectivity", "Cloud assistants fail where the signal is intermittent or absent (3T regions)."),
        ("2", "Data protection", "Patient records are specific personal data under Law No. 27/2022; transfer abroad "
                                 "is restricted, and medical records are confidential (Permenkes 24/2022)."),
        ("3", "Sovereignty", "A foreign API decides where patient data is stored, who can access it, and what it costs.")]
for i, (n, head, body) in enumerate(rows):
    y = 1.75 + i * 1.6
    badge(s, 0.6, y, n)
    text(s, 1.4, y - 0.02, 6.3, 0.45, [head], size=20, color=DARK, bold=True)
    text(s, 1.4, y + 0.45, 6.3, 1.0, [body], size=16, color=INK)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 8.3, 1.75, 4.4, 4.5, DARK, name="Answer card")
text(s, 8.7, 2.1, 3.7, 3.8, [[("The alternative", {"size": 14, "color": "8FD3C8", "bold": True})],
                            [("Run the whole assistant inside the facility, on hardware a health centre can buy, "
                              "fully offline.", {"size": 22, "color": WHITE, "font": HEAD})]], space_after=12)

# ------------------------------------------------------------------ 4. Gap
s = content_slide("Open models exist; deployment evidence does not", 4,
                  "MedGemma (Google, 2025) is open: the 4B model scores 64.4% on MedQA against 50.7% for its Gemma 3 "
                  "base. Benchmarks measure the model in isolation. What is missing is whether a complete clinical "
                  "stack runs offline on one consumer device, and at what cost. MedAide is the closest prior system; "
                  "this work differs in four ways.")
text(s, 0.6, 1.6, 4.6, 0.4, ["What we know"], size=18, color=TEAL, bold=True)
bullets(s, 0.6, 2.1, 4.6, 2.2, [[("MedGemma 4B: ", {"bold": True}), ("64.4% on MedQA vs 50.7% for its base [4]", {})],
                                "Quantised 4B models fit on a laptop-class GPU",
                                "Edge AI avoids latency, bandwidth and privacy limits of the cloud [9]"], size=16)
text(s, 0.6, 4.4, 4.6, 0.4, ["What is missing"], size=18, color=CORAL, bold=True)
bullets(s, 0.6, 4.9, 4.6, 1.8, ["Does model + RAG + patient records + routing + images run offline on one device?",
                                "How long is the wait, and what does it cost in memory and energy?"], size=16)
rows = [["", "MedAide [11]", "This work"],
        ["Model", "Fine-tuned general LLMs (OPT, Bloom, LLaMA-2)", "Open medical model (MedGemma 4B), with images"],
        ["Patient data", "General documents only", "Patient record via FHIR R4 tools"],
        ["Measured", "Accuracy; per-model latency and memory", "Stage-level latency, GPU memory, energy per query"],
        ["Setting", "Generic remote areas", "Indonesian PHCs, national FHIR exchange, data law"]]
tbl = s.shapes.add_table(len(rows), 3, Inches(5.7), Inches(1.65), Inches(7.0), Inches(4.4)).table
for c, w in enumerate((1.5, 2.6, 2.9)):
    tbl.columns[c].width = Inches(w)
for r, row in enumerate(rows):
    for c, value in enumerate(row):
        cell = tbl.cell(r, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = rgb(DARK if r == 0 else (MINT if c == 2 else WHITE))
        tf = cell.text_frame
        tf.word_wrap = True
        cell.margin_left = cell.margin_right = Inches(0.1)
        run = tf.paragraphs[0].add_run()
        run.text = value
        run.font.size, run.font.name = Pt(14), BODY
        run.font.bold = r == 0 or c == 0
        run.font.color.rgb = rgb(WHITE if r == 0 else INK)

# ------------------------------------------------------------------ 5. Aim and RQs
s = content_slide("Aim and research questions", 5,
                  "RQ1–RQ3 are answered by the preliminary study (the paper). RQ4–RQ6 are the work of the dissertation: "
                  "accuracy of the quantised model in Indonesian, faithfulness and clinical safety, and use by health "
                  "workers in the field.")
text(s, 0.6, 1.5, 12.1, 0.9, [[("Aim: ", {"bold": True, "color": TEAL}),
                               ("establish whether sovereign generative AI, running fully offline inside a remote health "
                                "centre, can support primary care in Indonesia — feasibly, accurately, safely and usably.",
                                {})]], size=18)
rqs = [("RQ1", "Can the complete stack run on one consumer laptop (8 GB GPU, 16 GB RAM), and with which configuration?", True),
       ("RQ2", "How long does a health worker wait for the first token, and which stage causes the wait?", True),
       ("RQ3", "How much GPU memory and energy does a query need?", True),
       ("RQ4", "How accurate is the quantised model in Indonesian, with and without RAG over local guidelines?", False),
       ("RQ5", "Are answers faithful to the patient record and clinically safe?", False),
       ("RQ6", "Is the assistant usable by nurses and midwives in a remote PHC?", False)]
for i, (rq, q, done) in enumerate(rqs):
    col, row = i // 3, i % 3
    x, y = 0.6 + col * 6.25, 2.75 + row * 1.35
    badge(s, x, y + 0.05, rq, size=0.75, fill=TEAL if done else CORAL, font_size=14)
    text(s, x + 0.95, y, 5.0, 1.2, [q], size=16)
text(s, 0.6, 2.35, 6, 0.35, [[("Answered by the preliminary study", {"color": TEAL, "bold": True})]], size=14)
text(s, 6.85, 2.35, 6, 0.35, [[("Proposed for the dissertation", {"color": CORAL, "bold": True})]], size=14)

# ------------------------------------------------------------------ 6. Architecture
s = content_slide("Proposed architecture: one device, fully offline", 6,
                  "Four containers on one consumer laptop. MedGemma 4B writes every answer and reads images. Because "
                  "MedGemma cannot call tools in this runtime, a small Qwen2.5 3B router selects the read-only FHIR "
                  "tools. RAG runs over the facility's guidelines in Redis. A connection, when available, is used only "
                  "to synchronise records with SATUSEHAT.")
picture(s, DOCS / "figures/fig1-architecture.png", 0.5, 1.45, 7.6, 5.3)
items = [("MedGemma 4B", "answers and image reading (Q4, local)"),
         ("Qwen2.5 3B router", "selects FHIR tools — MedGemma cannot call tools"),
         ("RAG", "guidelines and SOPs in an in-memory vector store (Redis)"),
         ("FHIR R4 tools", "read-only patient records, compatible with SATUSEHAT")]
for i, (head, body) in enumerate(items):
    y = 1.6 + i * 1.3
    badge(s, 8.5, y, str(i + 1), size=0.5, font_size=16)
    text(s, 9.2, y - 0.03, 3.6, 0.4, [head], size=17, color=DARK, bold=True)
    text(s, 9.2, y + 0.38, 3.6, 0.8, [body], size=15)

# ------------------------------------------------------------------ 7. Method
s = content_slide("Preliminary study: method", 7,
                  "Four pipelines with 20 questions each in Indonesian. The baseline gets the same questions as RAG, so "
                  "the two can be compared pairwise. After one warm-up pass, all 80 questions run five times in random "
                  "order, giving 100 measured requests per pipeline. The server times each stage; GPU power and memory "
                  "are sampled every 100 ms.")
pipes = [("Baseline", "MedGemma alone — the lower bound"), ("RAG", "Clinic schedule, formulary, guidelines"),
         ("FHIR tools", "Diagnoses, allergies, medications, labs, visits"), ("Image", "4 public brain MRIs × 5 prompts")]
for i, (head, body) in enumerate(pipes):
    x = 0.6 + i * 3.08
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.65, 2.85, 2.2, MINT, name=f"Pipeline {head}")
    text(s, x + 0.25, 1.85, 2.4, 0.45, [head], size=20, color=DARK, bold=True)
    text(s, x + 0.25, 2.35, 2.4, 0.5, [[("20 questions", {"color": CORAL, "bold": True})]], size=15)
    text(s, x + 0.25, 2.8, 2.4, 1.0, [body], size=15)
text(s, 0.6, 4.2, 5.8, 0.4, ["Protocol"], size=18, color=TEAL, bold=True)
bullets(s, 0.6, 4.7, 5.8, 2.1, ["1 warm-up pass, then 5 passes in random order (seed 42)",
                                "100 measured requests per pipeline, 400 in total",
                                "Consumer laptop: RTX 5060 8 GB GPU, 16 GB RAM, Ollama"], size=16)
text(s, 6.9, 4.2, 5.8, 0.4, ["Metrics"], size=18, color=TEAL, bold=True)
bullets(s, 6.9, 4.7, 5.8, 2.1, ["Time to first token (median, p95) and time per stage",
                                "Decode rate and end-to-end latency",
                                "GPU memory and energy per query; routing reliability"], size=16)

# ------------------------------------------------------------------ 8. Results: latency
s = content_slide("Answers start within about two seconds", 8,
                  "Median time to first token: 0.10 s for the model alone, 0.54 s with RAG, 1.11 s for images and "
                  "2.14 s for patient questions (p95 3.03 s). The router accounts for 79% of the wait for patient "
                  "questions, because it reads the full FHIR record before ending its turn. Decode speed is 56–61 "
                  "tokens per second on every pipeline.")
bar_chart(s, 0.6, 1.5, 7.4, 5.2, ["Baseline", "RAG", "Image", "FHIR tools"], [0.10, 0.54, 1.11, 2.14],
          ["0.10 s", "0.54 s", "1.11 s", "2.14 s"], "Median time to first token (s), 100 requests per pipeline",
          highlight=3, maximum=2.6)
callouts = [("79%", "of the wait for patient questions is the router, not the medical model"),
            ("56–61", "tokens per second while answering, on every pipeline"),
            ("15 ms", "for the RAG search itself (embedding and vector search)")]
for i, (big, label) in enumerate(callouts):
    y = 1.6 + i * 1.75
    text(s, 8.6, y, 4.1, 0.75, [big], size=40, color=CORAL if i == 0 else TEAL, font=HEAD, bold=True)
    text(s, 8.6, y + 0.75, 4.1, 0.9, [label], size=16)

# ------------------------------------------------------------------ 9. Results: resources
s = content_slide("It fits on a consumer laptop", 9,
                  "All three models stay resident on the 8 GB GPU, peaking at 7.0 GB. GPU board energy per query ranges "
                  "from 0.009 Wh for the model alone to 0.045 Wh for images. The router sent all 200 text questions "
                  "down the intended pipeline. Host RAM, not GPU memory, was the binding constraint.")
cards = [("7.0 GB", "of the 8 GB GPU for all three models"),
         ("200/200", "text questions routed to the intended pipeline"),
         ("16 GB", "host RAM — the real constraint, not GPU memory")]
for i, (big, label) in enumerate(cards):
    y = 1.55 + i * 1.75
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, y, 4.6, 1.5, MINT, name=f"Resource card {i + 1}")
    text(s, 0.9, y + 0.15, 4.0, 0.7, [big], size=36, color=DARK, font=HEAD, bold=True)
    text(s, 0.9, y + 0.85, 4.0, 0.6, [label], size=15)
bar_chart(s, 5.7, 1.5, 7.0, 5.2, ["Baseline", "RAG", "FHIR tools", "Image"], [0.0088, 0.0104, 0.0322, 0.0453],
          ["0.009 Wh", "0.010 Wh", "0.032 Wh", "0.045 Wh"], "GPU board energy per query (Wh, median)",
          highlight=3, maximum=0.056)

# ------------------------------------------------------------------ 10. Findings
s = content_slide("What the preliminary study taught us", 10,
                  "Three lessons shape the dissertation. The router, not the medical model, sets the wait and makes the "
                  "least reliable decisions. Runtime defaults are tuned for servers: a 32K context, a large prompt "
                  "cache and a half-size virtual machine caused failures until changed. And MedGemma's licence is set "
                  "by its developer, so the stack is sovereign in data and compute, but not fully in its model.")
lessons = [("The router sets the wait", "79% of the patient-question wait; it also made the faulty tool calls. "
                                        "A medical model with native tool calling would remove it."),
           ("Defaults are tuned for servers", "A 32K context, the host prompt cache and a half-size VM caused "
                                              "out-of-memory failures and latency spikes on a 16 GB laptop."),
           ("Sovereignty is partial", "Data and compute stay in the facility; MedGemma's licence terms are set "
                                      "by its developer.")]
for i, (head, body) in enumerate(lessons):
    x = 0.6 + i * 4.1
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.7, 3.8, 4.6, MINT, name=f"Lesson {i + 1}")
    badge(s, x + 0.35, 2.0, str(i + 1), size=0.6, fill=CORAL)
    text(s, x + 0.35, 2.85, 3.1, 0.9, [head], size=20, color=DARK, bold=True, font=HEAD)
    text(s, x + 0.35, 3.85, 3.1, 2.3, [body], size=16)

# ------------------------------------------------------------------ 11. Limitations
s = content_slide("What the preliminary study does not show", 11,
                  "The paper measures feasibility and performance only. Accuracy is taken from the model's developer, "
                  "measured at full precision on English benchmarks. Faithfulness, clinical safety and use by health "
                  "workers are not evaluated, and the data is synthetic. These gaps define the dissertation.")
gaps = [("Accuracy", "taken from the developer: full precision, English benchmarks"),
        ("Faithfulness and safety", "not evaluated: does the answer match the record, is it safe?"),
        ("Users", "no health workers involved; no outcomes measured"),
        ("Scope", "one laptop, one runtime, 20 questions per pipeline; GPU energy only"),
        ("Data", "synthetic records lack the messiness of real PHC data")]
for i, (head, body) in enumerate(gaps):
    y = 1.6 + i * 1.0
    badge(s, 0.6, y, "!", size=0.5, fill=CORAL, font_size=18)
    text(s, 1.3, y + 0.04, 3.4, 0.5, [head], size=18, color=DARK, bold=True)
    text(s, 4.8, y + 0.06, 7.9, 0.8, [body], size=16)

# ------------------------------------------------------------------ 12. Research plan
s = content_slide("Research plan: six work packages", 12,
                  "Each work package answers a gap from the preliminary study. WP1 and WP2 address accuracy and "
                  "safety (RQ4, RQ5). WP3 and WP4 improve and fully measure the system. WP5 takes it to users and the "
                  "field (RQ6), after ethics approval. WP6 builds national capacity through fine-tuning and federated "
                  "learning.")
wps = [("WP1", "Accuracy in Indonesian", "Quantised model, with and without RAG; RQ4"),
       ("WP2", "Faithfulness and safety", "Answers vs FHIR record; clinical safety review; RQ5"),
       ("WP3", "Router", "End the turn after the tool call, deterministic rules, or a model with native tool calling"),
       ("WP4", "Whole-system energy", "Power meter at the wall, idle and under load"),
       ("WP5", "Users and field pilot", "Usability study with nurses and midwives; pilot in [2–3] 3T PHCs; RQ6"),
       ("WP6", "National capacity", "Fine-tune on Indonesian guidelines; federated learning across facilities")]
for i, (wp, head, body) in enumerate(wps):
    col, row = i % 3, i // 3
    x, y = 0.6 + col * 4.1, 1.6 + row * 2.65
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 3.8, 2.4, MINT, name=f"{wp} card")
    badge(s, x + 0.3, y + 0.3, wp, size=0.75, fill=TEAL, font_size=13)
    text(s, x + 1.2, y + 0.38, 2.45, 0.7, [head], size=18, color=DARK, bold=True)
    text(s, x + 0.3, y + 1.2, 3.25, 1.1, [body], size=15)

# ------------------------------------------------------------------ 13. Timeline
s = content_slide("Indicative timeline (three years)", 13,
                  "An indicative plan over six semesters, to be agreed with the supervisors. Ethics approval from the "
                  "research ethics committee (KEPK) is needed before the usability study and field pilot in WP5.")
x0, y0, col_w, row_h = 3.3, 1.75, 1.55, 0.58
for k in range(6):
    year, sem = k // 2 + 1, k % 2 + 1
    text(s, x0 + k * col_w, y0 - 0.45, col_w, 0.35, [f"Y{year} · S{sem}"], size=13, color=MUTED, bold=True,
         align=PP_ALIGN.CENTER)
plan = [("WP1 Accuracy", 0, 2, TEAL), ("WP2 Faithfulness, safety", 1, 3, TEAL), ("WP3 Router", 1, 4, TEAL),
        ("WP4 Energy", 2, 3, TEAL), ("Ethics approval (KEPK)", 2, 3, CORAL), ("WP5 Users, field pilot", 3, 6, TEAL),
        ("WP6 Fine-tuning, federated", 3, 6, TEAL), ("Writing the dissertation", 4, 6, DARK)]
for i, (label, start, end, color) in enumerate(plan):
    y = y0 + i * row_h
    text(s, 0.6, y + 0.08, 2.6, 0.45, [label], size=15, color=INK, bold=color != TEAL)
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x0 + start * col_w + 0.05, y + 0.1, (end - start) * col_w - 0.1, 0.42,
          color, name=f"Bar {label}")
text(s, 0.6, 6.55, 12, 0.35, [[("Indicative; to be agreed with the supervisors.", {"italic": True})]], size=13,
     color=MUTED)

# ------------------------------------------------------------------ 14. Contributions
s = content_slide("Expected contributions", 14,
                  "Two contributions already exist from the preliminary study: the reference architecture and the "
                  "stage-level evaluation with its validated configuration. The dissertation adds evidence on accuracy, "
                  "safety and field use, and releases the implementation and benchmark openly.")
contribs = [("Reference architecture", "Offline medical LLM support for the primary-care edge, aligned with SATUSEHAT",
             "Done"),
            ("Validated runtime configuration", "Three local models within 16 GB RAM and 8 GB GPU memory", "Done"),
            ("Stage-level evaluation", "Latency, memory, energy and routing on consumer hardware", "Done"),
            ("Accuracy and safety evidence", "Quantised model in Indonesian; faithfulness to records", "Planned"),
            ("Field evidence", "Usability and pilot results from remote PHCs", "Planned"),
            ("Open release", "Prototype, benchmark harness and raw results for replication", "Planned")]
for i, (head, body, status) in enumerate(contribs):
    col, row = i // 3, i % 3
    x, y = 0.6 + col * 6.25, 1.6 + row * 1.7
    done = status == "Done"
    badge(s, x, y + 0.05, "✓" if done else "→", size=0.6, fill=TEAL if done else CORAL, font_size=18)
    text(s, x + 0.85, y, 5.1, 0.45, [head], size=18, color=DARK, bold=True)
    text(s, x + 0.85, y + 0.45, 5.1, 0.9, [body], size=15)

# ------------------------------------------------------------------ 15. Ethics
s = content_slide("Ethics and data governance", 15,
                  "The preliminary study used only synthetic patient records and public, openly licensed images, and "
                  "involved no participants. The system is decision support for trained health workers, not a "
                  "registered medical device. Any user study or field pilot needs approval from a research ethics "
                  "committee first.")
points = [("Synthetic data only", "No real patient data in the preliminary study; public, openly licensed MRI images."),
          ("Decision support, not a device", "For trained health workers; not patient-facing; not a registered medical device."),
          ("Ethics approval first", "User study and field pilot only after approval by a research ethics committee (KEPK)."),
          ("Data stays local", "Records stay on the device, in a format compatible with the Ministry of Health standard.")]
for i, (head, body) in enumerate(points):
    col, row = i % 2, i // 2
    x, y = 0.6 + col * 6.25, 1.7 + row * 2.4
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 5.95, 2.1, MINT, name=f"Ethics card {i + 1}")
    text(s, x + 0.35, y + 0.3, 5.3, 0.5, [head], size=19, color=DARK, bold=True)
    text(s, x + 0.35, y + 0.85, 5.3, 1.1, [body], size=16)

# ------------------------------------------------------------------ 16. Closing
s = prs.slides.add_slide(BLANK)
background(s, DARK)
text(s, 0.8, 1.3, 11.6, 2.4, ["Sovereign medical AI can run inside a remote health centre."], size=38, color=WHITE,
     font=HEAD, bold=True, anchor=MSO_ANCHOR.BOTTOM)
text(s, 0.8, 3.9, 11.6, 1.2, ["The dissertation will establish whether it is accurate, safe and usable there."],
     size=24, color="CFE7E2", font=HEAD)
text(s, 0.8, 5.6, 8, 0.8, [[("Questions and discussion", {"bold": True, "color": "8FD3C8"})]], size=20)
s.notes_slide.notes_text_frame.text = (
    "Summary: the preliminary study shows feasibility on one consumer laptop — answers start within about two "
    "seconds, all models fit in 7 GB of GPU memory, and a query costs 0.01–0.05 Wh of GPU energy. The dissertation "
    "turns to accuracy, safety and use in the field.")

# ------------------------------------------------------------------ 17. References
s = content_slide("Key references", 17, "Full reference list in the accompanying paper.")
refs = ["[1] Ministry of Health of Indonesia: Profil Data Tenaga Kesehatan, Edisi Agustus 2023. Jakarta (2023)",
        "[2] Badan Pusat Statistik: Villages by province and reception of mobile internet signal, 2025. Jakarta (2025)",
        "[4] Sellergren, A., et al.: MedGemma technical report. arXiv:2507.05201 (2025)",
        "[5] Republic of Indonesia: Law No. 27 of 2022 on Personal Data Protection (2022)",
        "[9] Prakash, A., Ayyanathan, N.: Preventive healthcare through IoT and edge AI (2026)",
        "[11] Basit, A., et al.: MedAide: LLMs for on-premise medical assistance on edge devices. arXiv:2403.00830 (2024)",
        "[14] Heryawan, L., Mori, Y., et al.: FHIR-based interoperability design in Indonesia. JMIR Formative Research (2025)",
        "[18] Qwen Team: Qwen2.5 technical report. arXiv:2412.15115 (2024)"]
text(s, 0.6, 1.6, 12.1, 5.2, refs, size=15, space_after=10)

prs.core_properties.title = "Dissertation proposal: Can Sovereign Generative AI Run at the Edge?"
prs.core_properties.author = "Erfin Feluzy"
prs.save(OUT)
print("written", OUT, "-", len(prs.slides), "slides")
