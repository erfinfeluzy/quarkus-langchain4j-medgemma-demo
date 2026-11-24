"""Figures for paper-edge-medgemma.md (run from the project folder, see docs/figures/README.md).

Fig. 1  high-level architecture with the container runtime
Fig. 2  the four public brain MRI images of the image benchmark
Fig. 3  median time to first token per pipeline, split by stage
Fig. 4  distribution of time to first token per pipeline (all measured requests)
Fig. 5  GPU board energy per request per pipeline (Table 4)
"""
import csv
import random
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

RESULTS = Path(sys.argv[1] if len(sys.argv) > 1 else "bench/results/20261110-175216/results.csv")
OUT = Path("docs/figures")

# Reference palette (dataviz skill), validated: blue, orange, aqua in fixed order
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE, INK, INK2, GRID = "#ffffff", "#0b0b0b", "#52514e", "#e4e3df"
PIPELINES = ["baseline", "rag", "tools", "image"]
LABELS = {"baseline": "Baseline", "rag": "RAG", "tools": "FHIR tools", "image": "Image"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def load():
    rows = []
    with RESULTS.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["route_ok"] == "true":
                rows.append(r)
    return rows


def nearest_rank(values, p):
    """Same percentile definition as bench/Benchmark.java, so figures match the paper's tables."""
    values = sorted(values)
    rank = -(-len(values) * p // 100)  # ceil
    return values[max(0, min(len(values) - 1, int(rank) - 1))]


def median(rows, scenario, column):
    values = [float(r[column]) for r in rows if r["expected_scenario"] == scenario and r[column]]
    return nearest_rank(values, 50) / 1000 if values else 0.0


def fig_ttft_breakdown(rows):
    fig, ax = plt.subplots(figsize=(8, 3.4), dpi=200)
    stages = [("routing_ms", "Routing (router + tool call)", BLUE),
              ("retrieval_ms", "RAG (embed + vector search)", ORANGE),
              ("medgemma_ttft_ms", "MedGemma TTFT", AQUA)]
    order = list(reversed(PIPELINES))
    for y, p in enumerate(order):
        left = 0.0
        for column, _, color in stages:
            width = median(rows, p, column)
            if width <= 0:
                continue
            ax.barh(y, width, left=left, height=0.56, color=color, edgecolor=SURFACE, linewidth=2)
            if width >= 0.12:
                ax.text(left + width / 2, y, f"{width:.2f}", ha="center", va="center", fontsize=8.5,
                        color="#ffffff" if color == BLUE else INK)
            left += width
        ttft = median(rows, p, "client_ttft_ms")
        p95 = nearest_rank([float(r["client_ttft_ms"]) for r in rows if r["expected_scenario"] == p], 95) / 1000
        ax.text(left + 0.04, y, f"TTFT {ttft:.2f} s  (p95 {p95:.2f} s)", va="center", fontsize=9, color=INK)
    rag_retrieval = median(rows, "rag", "retrieval_ms")
    ax.annotate(f"RAG {rag_retrieval * 1000:.0f} ms", xy=(median(rows, "rag", "routing_ms") + rag_retrieval / 2, 2.28),
                xytext=(0.62, 2.62), fontsize=8, color=INK2,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.set_yticks(range(len(order)), [LABELS[p] for p in order])
    ax.set_xlim(0, 3.4)
    ax.set_xlabel("Median time per stage (s)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in stages]
    ax.legend(handles, [label for _, label, _ in stages], loc="upper center", bbox_to_anchor=(0.5, -0.22),
              ncol=3, frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "fig3-ttft-breakdown.png")
    plt.close(fig)


def fig_ttft_distribution(rows):
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=200)
    rng = random.Random(42)
    order = list(reversed(PIPELINES))
    for y, p in enumerate(order):
        values = [float(r["client_ttft_ms"]) / 1000 for r in rows if r["expected_scenario"] == p]
        jitter = [y + rng.uniform(-0.18, 0.18) for _ in values]
        ax.scatter(values, jitter, s=14, color=BLUE, alpha=0.55, edgecolors="none")
        m = nearest_rank(values, 50)
        ax.plot([m, m], [y - 0.3, y + 0.3], color=INK, linewidth=2)
        ax.text(m, y + 0.36, f"median {m:.2f} s", ha="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(order)), [f"{LABELS[p]} (n={sum(1 for r in rows if r['expected_scenario'] == p)})"
                                      for p in order])
    ax.set_xlim(0, 4.6)
    ax.set_ylim(-0.6, len(order) - 0.3)
    ax.set_xlabel("Time to first token per request, measured at the client (s)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    fig.savefig(OUT / "fig4-ttft-distribution.png")
    plt.close(fig)


def fig_energy(rows):
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=200)
    rng = random.Random(42)
    order = list(reversed(PIPELINES))
    for y, p in enumerate(order):
        values = [float(r["gpu_energy_j"]) for r in rows if r["expected_scenario"] == p and r["gpu_energy_j"]]
        jitter = [y + rng.uniform(-0.18, 0.18) for _ in values]
        ax.scatter(values, jitter, s=14, color=BLUE, alpha=0.55, edgecolors="none")
        m = nearest_rank(values, 50)
        ax.plot([m, m], [y - 0.3, y + 0.3], color=INK, linewidth=2)
        ax.text(m, y + 0.36, f"median {m:.1f} J ({m / 3600:.4f} Wh)", ha="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(order)), [f"{LABELS[p]} (n={sum(1 for r in rows if r['expected_scenario'] == p)})"
                                      for p in order])
    ax.set_xlim(0, 380)
    ax.set_ylim(-0.6, len(order) - 0.3)
    ax.set_xlabel("GPU board energy per request (J)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    fig.savefig(OUT / "fig5-gpu-energy.png")
    plt.close(fig)


SAMPLE_IMAGES = [  # Order and labels match the Figure 2 caption in the paper
    ("sample-image/mri-meningioma-besar.jpg", "(a) Large meningioma"),
    ("sample-image/mri-glioblastoma.jpg", "(b) Glioblastoma"),
    ("sample-image/mri-meningioma-4-potongan.jpg", "(c) Meningioma, four slices"),
    ("sample-image/mri-normal-warna-semu.png", "(d) No mass (false colour)"),
]


def fig_sample_images():
    fig, axes = plt.subplots(1, len(SAMPLE_IMAGES), figsize=(10, 3.0), dpi=200)
    for ax, (path, label) in zip(axes, SAMPLE_IMAGES):
        ax.imshow(plt.imread(path), cmap="gray")
        ax.set_title(label, fontsize=9, color=INK, pad=6)
        ax.axis("off")
    fig.tight_layout(w_pad=1.2)
    fig.savefig(OUT / "fig2-sample-images.png", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def box(ax, x, y, w, h, title, lines=(), fill="#ffffff", edge=INK2, dashed=False, title_size=9.5, bold=True):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.12", facecolor=fill,
                                edgecolor=edge, linewidth=1.1, linestyle=(0, (4, 3)) if dashed else "solid"))
    ax.text(x + 0.15, y + h - 0.22, title, fontsize=title_size, fontweight="bold" if bold else "normal",
            color=INK, va="top")
    for i, line in enumerate(lines):
        ax.text(x + 0.15, y + h - 0.58 - i * 0.3, line, fontsize=8.2, color=INK2, va="top")


def arrow(ax, start, end, label=None, dashed=False, label_offset=(0, 0.12), rad=0.0):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=11, color=INK2, linewidth=1.1,
                                 linestyle=(0, (4, 3)) if dashed else "solid",
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2))
    if label:
        ax.text((start[0] + end[0]) / 2 + label_offset[0], (start[1] + end[1]) / 2 + label_offset[1], label,
                fontsize=7.8, color=INK2, ha="center", va="bottom")


def fig_architecture():
    fig, ax = plt.subplots(figsize=(11, 7.4), dpi=200)
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 14.8)
    ax.axis("off")

    # Laptop and Windows host
    box(ax, 4.2, 0.3, 17.5, 14.2, "Consumer laptop  ·  Windows 11", ["Intel Core 7 · 16 GB RAM · NVIDIA RTX 5060 Laptop 8 GB"],
        fill="#f6f6f4", edge=INK2)
    # Docker Desktop / WSL2 VM
    box(ax, 4.6, 2.6, 16.7, 10.6, "Docker Desktop  ·  WSL2 virtual machine (10 GB RAM, 8 GB swap)",
        ["Container network demo-net"], fill="#eef4fc", edge=BLUE)

    # Containers
    box(ax, 5.0, 7.6, 6.2, 4.4, "med-app container", ["Quarkus + LangChain4j", "Web UI and chat API (port 8081)",
                                                      "Pipelines: RAG · FHIR tools · image", "FHIR R4 mapper (read-only FHIR tools)",
                                                      "Deterministic safety layers"], fill="#ffffff", edge=BLUE)
    box(ax, 13.6, 6.4, 7.3, 5.6, "ollama container  (GPU)", ["Ollama 0.40.4 · llama.cpp", "context 8K · flash attention",
                                                            "host prompt cache off"], fill="#ffffff", edge=BLUE)
    box(ax, 13.85, 9.0, 6.8, 0.9, "MedGemma 4B Q4_K_M: answers, images", fill="#e8f7f1", edge=AQUA, title_size=8)
    box(ax, 13.85, 7.95, 6.8, 0.9, "Qwen2.5 3B Q4_K_M: router", fill="#eaf2fc", edge=BLUE, title_size=8)
    box(ax, 13.85, 6.9, 6.8, 0.9, "nomic-embed-text: embeddings", fill="#fdf0ea", edge=ORANGE, title_size=8)

    box(ax, 5.0, 3.0, 4.6, 2.6, "demo-redis container", ["Redis", "Vector index (guidelines)", "Chat memory"],
        fill="#ffffff", edge=BLUE)
    box(ax, 10.2, 3.0, 4.6, 2.6, "demo-mysql container", ["MySQL 8.4", "Clinic records,", "one table per FHIR resource"],
        fill="#ffffff", edge=BLUE)
    box(ax, 15.4, 3.0, 4.4, 2.6, "Mounted volumes", ["rag-docs: guidelines,", "formulary, clinic info",
                                                    "ollama: model weights"], fill="#ffffff", edge=INK2, dashed=True)

    # GPU, outside the virtual machine but inside the laptop
    box(ax, 13.6, 0.6, 7.3, 1.5, "GPU  ·  RTX 5060 Laptop 8 GB", ["3 models resident, 7.0 GB peak"], fill="#ffffff", edge=INK2)

    # Outside the laptop
    box(ax, 0.2, 9.4, 3.4, 2.6, "Health worker", ["Browser on the", "PHC's local network"], fill="#ffffff", edge=INK2)
    box(ax, 0.2, 0.9, 3.4, 2.4, "National HIE", ["SATUSEHAT", "(FHIR R4, online only)"], fill="#ffffff", edge=INK2, dashed=True)

    arrow(ax, (3.6, 9.9), (5.0, 9.9))
    ax.text(4.3, 9.5, "question,\nimage", fontsize=7.8, color=INK2, ha="center", va="top")
    arrow(ax, (11.2, 10.4), (13.6, 10.4), "prompts, images")
    arrow(ax, (13.6, 8.8), (11.2, 8.8), "tool calls, tokens", label_offset=(0, -0.38))
    arrow(ax, (7.3, 7.6), (7.3, 5.6))
    ax.text(5.95, 6.85, "embed + search,\nchat history", fontsize=7.8, color=INK2, ha="center", va="center")
    arrow(ax, (10.0, 7.6), (12.4, 5.6))
    ax.text(12.0, 6.95, "read-only\nFHIR queries", fontsize=7.8, color=INK2, ha="left", va="center")
    arrow(ax, (20.35, 6.4), (20.35, 2.1))
    ax.text(20.5, 4.3, "CUDA\nvia\nWSL2", fontsize=7.8, color=INK2, ha="left", va="center")
    arrow(ax, (11.0, 3.0), (3.6, 1.9), dashed=True)
    ax.text(7.2, 1.95, "sync when online", fontsize=7.8, color=INK2, ha="center", va="top")
    fig.savefig(OUT / "fig1-architecture.png", bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load()
    fig_architecture()
    fig_sample_images()
    fig_ttft_breakdown(rows)
    fig_ttft_distribution(rows)
    fig_energy(rows)
    print("figures written to", OUT)
