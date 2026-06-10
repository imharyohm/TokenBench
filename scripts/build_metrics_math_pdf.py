"""Build a visual, beginner-friendly PDF explaining tokenbench/core/metrics.py.

Run:
    MPLCONFIGDIR=/tmp/mplcache python scripts/build_metrics_math_pdf.py

Output:
    research/metrics_math_explained.pdf

Design goals:
- Zero new dependencies (uses matplotlib, already in requirements).
- One concept per page so each page is digestible on its own.
- Diagrams over prose where possible. Worked numeric examples everywhere.
- Each formula is accompanied by a plain-English restatement.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT_PATH = Path(__file__).resolve().parents[1] / "research" / "metrics_math_explained.pdf"

PAGE = (8.5, 11.0)
TITLE_COLOR = "#0b3d91"
ACCENT = "#e07b00"
MUTED = "#555555"
GOOD = "#1b7a3e"
BAD = "#b3261e"
BOX_BG = "#f4f4f9"
BOX_EDGE = "#cccccc"


def blank_axes(fig):
    """A single full-page axes with no ticks, no spines — a blank canvas."""
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    return ax


def draw_box(ax, x, y, w, h, text, *, facecolor=BOX_BG, edgecolor=BOX_EDGE,
             fontsize=11, weight="normal", color="black", family="sans-serif"):
    """Rounded rectangle with centered text."""
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.005,rounding_size=0.012",
        linewidth=1.2, edgecolor=edgecolor, facecolor=facecolor,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text,
            ha="center", va="center", fontsize=fontsize, weight=weight,
            color=color, family=family, wrap=True)


def draw_arrow(ax, x1, y1, x2, y2, *, color="#444", lw=1.5, style="->"):
    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle=style, mutation_scale=14,
        linewidth=lw, color=color,
    )
    ax.add_patch(arrow)


def page_header(ax, page_num, total, title, subtitle=None):
    ax.text(0.06, 0.955, title,
            fontsize=20, weight="bold", color=TITLE_COLOR, va="top")
    if subtitle:
        ax.text(0.06, 0.915, subtitle,
                fontsize=11, color=MUTED, va="top", style="italic")
    ax.text(0.94, 0.97, f"{page_num} / {total}",
            fontsize=9, color=MUTED, ha="right", va="top")
    ax.plot([0.06, 0.94], [0.895, 0.895], color="#dddddd", lw=0.8)


def page_footer(ax, label="TokenBench · metrics math"):
    ax.text(0.5, 0.03, label,
            fontsize=8, color=MUTED, ha="center", va="bottom", style="italic")


# ───────────────────────────────────────────────────────────────────────────
# Page builders
# ───────────────────────────────────────────────────────────────────────────

def page_cover(pdf, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    ax.text(0.5, 0.70, "TokenBench",
            ha="center", va="center", fontsize=44, weight="bold", color=TITLE_COLOR)
    ax.text(0.5, 0.63, "Metrics Math",
            ha="center", va="center", fontsize=34, weight="light", color=TITLE_COLOR)
    ax.text(0.5, 0.55, "How TPCA, Pareto frontiers, and bootstrap CIs work",
            ha="center", va="center", fontsize=14, color=MUTED, style="italic")

    draw_box(ax, 0.18, 0.30, 0.64, 0.18,
             "A visual, step-by-step explanation of\n"
             "tokenbench/core/metrics.py\n\n"
             "Every formula in plain English.\n"
             "Worked examples for every edge case.\n"
             "Flow diagrams tying it all together.",
             fontsize=12, facecolor="#fbfbfd", edgecolor=ACCENT)

    ax.text(0.5, 0.18, "Reads in ~10 minutes. No prior stats knowledge required.",
            ha="center", fontsize=10, color=MUTED)
    ax.text(0.5, 0.06, f"Companion to: tokenbench/core/metrics.py",
            ha="center", fontsize=9, color=MUTED, family="monospace")
    pdf.savefig(fig); plt.close(fig)


def page_big_picture(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "1. The big picture",
                subtitle="What this whole file does, in one diagram.")

    ax.text(0.06, 0.85,
            "The benchmark produces a stream of RunRecords — one per attempt.\n"
            "metrics.py turns those records into three things humans can act on:",
            fontsize=11, va="top")

    # Three output bullets
    ax.text(0.10, 0.78, "  •  One headline number (TPCA)",
            fontsize=11, va="top")
    ax.text(0.10, 0.755, "  •  One headline plot (Pareto frontier)",
            fontsize=11, va="top")
    ax.text(0.10, 0.730, "  •  One uncertainty estimate (bootstrap CI)",
            fontsize=11, va="top")

    # Flow diagram
    draw_box(ax, 0.10, 0.50, 0.30, 0.10,
             "RunRecords\n(many rows, one per attempt)",
             fontsize=11, weight="bold", facecolor="#eef3fb", edgecolor=TITLE_COLOR)

    draw_box(ax, 0.45, 0.61, 0.45, 0.07,
             "tokens per record  (with build-cost amortized over V)",
             fontsize=10)
    draw_box(ax, 0.45, 0.52, 0.45, 0.07,
             "summarize()  →  median, IQR  (the honest distribution)",
             fontsize=10)
    draw_box(ax, 0.45, 0.43, 0.45, 0.07,
             "bootstrap_ci()  →  (low, high) confidence interval",
             fontsize=10)
    draw_box(ax, 0.45, 0.34, 0.45, 0.07,
             "tpca()  →  THE NUMBER",
             fontsize=10, weight="bold", facecolor="#fff3e0", edgecolor=ACCENT)
    draw_box(ax, 0.45, 0.25, 0.45, 0.07,
             "pareto_frontier()  →  THE PLOT",
             fontsize=10, weight="bold", facecolor="#fff3e0", edgecolor=ACCENT)

    # Arrows
    for y in [0.645, 0.555, 0.465, 0.375, 0.285]:
        draw_arrow(ax, 0.40, 0.55, 0.45, y)

    ax.text(0.06, 0.17,
            "Every page that follows zooms into one of these boxes.",
            fontsize=11, color=MUTED, style="italic", va="top")

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


def page_per_record_tokens(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "2. The building block",
                subtitle="How many tokens does one attempt cost?")

    ax.text(0.06, 0.85, "Formula", fontsize=14, weight="bold", color=TITLE_COLOR)
    draw_box(ax, 0.06, 0.76, 0.88, 0.07,
             "tokens(record, V)  =  input_norm  +  output_norm  +  build_norm / V",
             fontsize=12, family="monospace", facecolor="#fbf7ee", edgecolor=ACCENT)

    ax.text(0.06, 0.72, "In plain English", fontsize=14, weight="bold", color=TITLE_COLOR)
    ax.text(0.06, 0.685,
            "Add up: what went IN to the model, what came OUT, plus a fair slice\n"
            "of the one-time setup cost (split across V future queries).",
            fontsize=11, va="top")

    # Visual: stacked bar at V=1 vs V=100
    sub = fig.add_axes([0.10, 0.30, 0.80, 0.27])
    methods = ["V = 1\n(cold)", "V = 100\n(warm)", "V = 10,000\n(steady)"]
    input_tok = [100, 100, 100]
    output_tok = [10, 10, 10]
    build_tok = [10000 / 1, 10000 / 100, 10000 / 10000]

    x = np.arange(len(methods))
    sub.bar(x, input_tok, label="input_norm (100)", color="#5b9bd5")
    sub.bar(x, output_tok, bottom=input_tok, label="output_norm (10)", color="#70ad47")
    sub.bar(x, build_tok, bottom=np.array(input_tok) + np.array(output_tok),
            label="build_norm / V", color=ACCENT)
    sub.set_xticks(x)
    sub.set_xticklabels(methods, fontsize=10)
    sub.set_ylabel("tokens per attempt", fontsize=10)
    sub.set_yscale("log")
    sub.set_title("Same method, three amortization volumes  (build_norm = 10,000)",
                  fontsize=11)
    sub.legend(loc="upper right", fontsize=9)
    sub.grid(axis="y", alpha=0.3, which="both")

    ax.text(0.06, 0.22,
            "Key insight:  build cost dominates at V=1, disappears at V=10,000.\n"
            "This is why the benchmark forbids a single TPCA without stating V.",
            fontsize=11, va="top", color=MUTED, style="italic")

    # Edge cases
    ax.text(0.06, 0.14, "Edge cases", fontsize=12, weight="bold", color=TITLE_COLOR)
    ax.text(0.06, 0.115,
            "•  V = 0 or V < 0  →  raises ValueError (caught at the boundary)\n"
            "•  V = ∞  →  build_share = 0 (guarded by math.isfinite)\n"
            "•  V = NaN  →  silently treated as ∞  (minor wart, not user-facing)",
            fontsize=10, va="top", family="monospace")

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


def page_tpca(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "3. TPCA  —  the headline number",
                subtitle="Tokens Per Correct Answer.  Lower is better.")

    draw_box(ax, 0.06, 0.78, 0.88, 0.09,
             "TPCA(V)  =   Σ tokens used (all attempts)  /  Σ correct attempts",
             fontsize=14, family="monospace", facecolor="#fbf7ee", edgecolor=ACCENT)

    ax.text(0.06, 0.74, "In plain English", fontsize=14, weight="bold", color=TITLE_COLOR)
    ax.text(0.06, 0.71,
            "How many tokens did we burn for every correct answer we got?\n"
            "WRONG attempts also cost tokens — they sit in the numerator but not the denominator.",
            fontsize=11, va="top")

    # Worked example table
    ax.text(0.06, 0.62, "Worked example", fontsize=14, weight="bold", color=TITLE_COLOR)

    rows = [
        ("Attempt", "tokens", "correct?"),
        ("1",       "110",    "✓"),
        ("2",       "110",    "✓"),
        ("3",       "1,100",  "✗  (wrong but still cost tokens)"),
    ]
    y0 = 0.55
    col_x = [0.10, 0.32, 0.55]
    for i, row in enumerate(rows):
        y = y0 - i * 0.035
        weight = "bold" if i == 0 else "normal"
        for x, cell in zip(col_x, row):
            color = "black"
            if i > 0 and x == col_x[2]:
                color = GOOD if "✓" in cell else BAD
            ax.text(x, y, cell, fontsize=11, weight=weight, va="center", color=color)
        if i == 0:
            ax.plot([0.09, 0.86], [y - 0.018, y - 0.018], color="#888", lw=0.7)

    # Calculation
    draw_box(ax, 0.10, 0.30, 0.80, 0.12,
             "Σ tokens   =  110 + 110 + 1,100   =  1,320\n"
             "Σ correct  =  2\n"
             "TPCA       =  1,320 / 2   =   660  tokens per correct answer",
             fontsize=12, family="monospace", facecolor="#eef3fb", edgecolor=TITLE_COLOR)

    # Anti-gaming insight
    ax.text(0.06, 0.21,
            "Anti-gaming property",
            fontsize=12, weight="bold", color=TITLE_COLOR)
    ax.text(0.06, 0.18,
            "What if a method refuses to answer to avoid being wrong?\n"
            "  →  0 correct  →  TPCA = ∞   (worst possible score)\n"
            "What if a method answers with a single character to save tokens?\n"
            "  →  almost never correct  →  high tokens per correct, also bad",
            fontsize=10, va="top")

    ax.text(0.06, 0.07,
            "The math punishes both verbosity AND giving up.  That's the design.",
            fontsize=11, va="top", color=ACCENT, weight="bold", style="italic")

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


def page_why_V_matters(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "4. Why V matters",
                subtitle="The same method can look terrible OR amazing — depending on V.")

    ax.text(0.06, 0.85,
            "Some methods (RAG, Graphify) pay a big one-time setup cost\n"
            "(building an embeddings index or a code graph).",
            fontsize=11, va="top")
    ax.text(0.06, 0.78,
            "If you only ask ONE question, that setup cost is wasted.\n"
            "If you ask 10,000 questions, the setup cost is basically free per query.",
            fontsize=11, va="top")

    # Curve: TPCA vs V for two methods
    sub = fig.add_axes([0.12, 0.27, 0.78, 0.42])
    V = np.array([1, 3, 10, 30, 100, 300, 1000, 3000, 10000])
    per_query = 110
    build_a = 0       # raw method, no build cost
    build_b = 200_000  # Graphify-like

    tpca_a = per_query + build_a / V
    tpca_b = per_query + build_b / V

    sub.plot(V, tpca_a, "-o", color="#5b9bd5", label="Method A (no build cost)", lw=2)
    sub.plot(V, tpca_b, "-o", color=ACCENT, label="Method B (build cost = 200k)", lw=2)
    sub.set_xscale("log")
    sub.set_yscale("log")
    sub.set_xlabel("V  (number of queries the build cost is spread over)", fontsize=11)
    sub.set_ylabel("TPCA  (tokens per correct answer)", fontsize=11)
    sub.set_title("Reading the same method at three different V values",
                  fontsize=12)
    sub.grid(True, which="both", alpha=0.3)
    sub.legend(loc="upper right", fontsize=10)

    # Highlight the three V values
    for V_val in [1, 100, 10000]:
        sub.axvline(V_val, color="#aaa", linestyle="--", lw=0.8)
        sub.text(V_val, sub.get_ylim()[1] * 0.7, f"V={V_val}",
                 fontsize=9, ha="center", color=MUTED)

    ax.text(0.06, 0.20,
            "At V = 1   (cold start, one query):    Method B looks 1,800× worse than A.\n"
            "At V = 10,000  (steady state):           Method B looks nearly identical to A.",
            fontsize=11, family="monospace", va="top")

    ax.text(0.06, 0.08,
            "DECISIONS.md  #5  →  always report TPCA at V ∈ {1, 100, 10,000}.\n"
            "Reporting a single V is a load-bearing lie.",
            fontsize=10, color=BAD, weight="bold", va="top")

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


def page_distribution(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "5. Distribution  —  why median, not mean",
                subtitle="Token usage is heavy-tailed. The mean lies; the median doesn't.")

    ax.text(0.06, 0.85,
            "Imagine 100 questions that each used about 1,000 tokens, plus ONE question\n"
            "that hit a pathological case and used 1,000,000 tokens.",
            fontsize=11, va="top")

    # Histogram of a fake heavy-tail
    rng = np.random.default_rng(7)
    body = rng.normal(loc=1000, scale=150, size=99)
    sample = np.concatenate([body, [1_000_000]])
    sub = fig.add_axes([0.12, 0.40, 0.78, 0.30])
    sub.hist(sample, bins=np.logspace(2.5, 6.1, 30), color="#5b9bd5", edgecolor="white")
    sub.set_xscale("log")
    sub.set_xlabel("tokens per query (log scale)", fontsize=10)
    sub.set_ylabel("how many queries", fontsize=10)
    sub.axvline(np.median(sample), color=GOOD, lw=2.5,
                label=f"median = {int(np.median(sample)):,}")
    sub.axvline(np.mean(sample), color=BAD, lw=2.5, linestyle="--",
                label=f"mean   = {int(np.mean(sample)):,}")
    sub.legend(loc="upper right", fontsize=10)
    sub.set_title("99 normal queries + 1 outlier:  mean vs median", fontsize=11)
    sub.grid(True, alpha=0.3)

    ax.text(0.06, 0.32,
            "Reading this honestly",
            fontsize=13, weight="bold", color=TITLE_COLOR)
    ax.text(0.06, 0.29,
            "•  median  ≈  1,000   →   'typical query costs 1,000 tokens'  (true)\n"
            "•  mean    ≈ 11,000   →   'typical query costs 11,000 tokens'  (LIE — one outlier did this)",
            fontsize=10, family="monospace", va="top")

    ax.text(0.06, 0.20,
            "What summarize() returns",
            fontsize=13, weight="bold", color=TITLE_COLOR)
    draw_box(ax, 0.06, 0.08, 0.88, 0.10,
             "Distribution(n, mean, median, q25, q75)\n\n"
             "always report median + IQR (q75 − q25) alongside the mean,\n"
             "never just the mean, per tokenbench_architecture.md §0.1",
             fontsize=11, family="monospace", facecolor=BOX_BG, edgecolor=BOX_EDGE)

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


def page_bootstrap(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "6. Bootstrap CI  —  how sure are we?",
                subtitle="A confidence interval, computed by resampling your own data.")

    ax.text(0.06, 0.85,
            "TPCA is a single number — but it has uncertainty.\n"
            "A confidence interval (CI) says: 'I'm 95% sure the true mean is in this range.'",
            fontsize=11, va="top")

    # 4-step algorithm
    ax.text(0.06, 0.76, "The algorithm in 4 steps", fontsize=13, weight="bold", color=TITLE_COLOR)
    steps = [
        "1.  Take your N data points.",
        "2.  Resample N points WITH REPLACEMENT  →  one 'bootstrap sample'.",
        "3.  Compute the mean of that sample.  Repeat 10,000 times → 10,000 means.",
        "4.  The 2.5th and 97.5th percentiles of those means = your 95% CI.",
    ]
    for i, s in enumerate(steps):
        ax.text(0.08, 0.71 - i * 0.035, s, fontsize=11, va="top", family="monospace")

    # Visual: distribution of bootstrap means
    rng = np.random.default_rng(0)
    data = rng.normal(loc=500, scale=80, size=60)
    n_resamples = 10_000
    idx = rng.integers(0, len(data), size=(n_resamples, len(data)))
    means = data[idx].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])

    sub = fig.add_axes([0.12, 0.34, 0.78, 0.22])
    sub.hist(means, bins=60, color="#5b9bd5", edgecolor="white")
    sub.axvline(low, color=BAD, lw=2.5, label=f"2.5%  ({low:.1f})")
    sub.axvline(high, color=BAD, lw=2.5, label=f"97.5%  ({high:.1f})")
    sub.axvline(means.mean(), color=GOOD, lw=2.5, linestyle="--",
                label=f"mean of means ({means.mean():.1f})")
    sub.set_xlabel("mean from each bootstrap sample", fontsize=10)
    sub.set_ylabel("count out of 10,000", fontsize=10)
    sub.set_title("10,000 bootstrap means → 95% CI is the [2.5%, 97.5%] band",
                  fontsize=11)
    sub.legend(loc="upper right", fontsize=9)
    sub.grid(True, alpha=0.3)

    ax.text(0.06, 0.27, "Why this matters when comparing methods",
            fontsize=13, weight="bold", color=TITLE_COLOR)
    ax.text(0.06, 0.235,
            "If method A is TPCA = 500 [CI: 450, 550]   and\n"
            "   method B is TPCA = 600 [CI: 580, 620]\n"
            "   →  CIs don't overlap  →  A is GENUINELY better, not noise.",
            fontsize=10, family="monospace", color=GOOD, va="top")
    ax.text(0.06, 0.13,
            "If method A is TPCA = 500 [CI: 400, 600]   and\n"
            "   method B is TPCA = 600 [CI: 500, 700]\n"
            "   →  CIs overlap  →  CANNOT conclude A is better — likely just noise.",
            fontsize=10, family="monospace", color=BAD, va="top")

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


def page_pareto(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "7. Pareto frontier  —  the headline plot",
                subtitle="The set of methods that aren't strictly worse than someone else.")

    ax.text(0.06, 0.85,
            "A method is 'dominated' if some other method beats it on BOTH axes\n"
            "(higher accuracy AND fewer tokens). Dominated methods drop off.",
            fontsize=11, va="top")

    ax.text(0.06, 0.78, "Rule of thumb", fontsize=13, weight="bold", color=TITLE_COLOR)
    draw_box(ax, 0.06, 0.69, 0.88, 0.07,
             "If you ever have to argue your method belongs on the frontier,\n"
             "find one axis where nothing else beats you. That's all 'non-dominated' means.",
             fontsize=11, facecolor="#fbf7ee", edgecolor=ACCENT)

    # Pareto plot example
    sub = fig.add_axes([0.13, 0.22, 0.76, 0.42])
    # (label, x, y, on_frontier, annotation_offset)
    methods = [
        ("A (cheap, low acc)",  50,  0.30, True,  (10, -14)),
        ("B (mid, mid acc)",    200, 0.75, True,  (10, 8)),
        ("C (expensive, high)", 800, 0.92, True,  (-12, -16)),
        ("D (dominated by C)",  900, 0.85, False, (-110, 4)),
        ("E (dominated by B)",  500, 0.55, False, (-110, 4)),
    ]
    for label, tok, acc, on_front, offset in methods:
        color = ACCENT if on_front else "#888"
        size = 230 if on_front else 90
        edge = "black" if on_front else "#bbb"
        sub.scatter(tok, acc, s=size, color=color, edgecolor=edge,
                    linewidth=2 if on_front else 1, zorder=3)
        ha = "right" if offset[0] < 0 else "left"
        sub.annotate(label, (tok, acc), xytext=offset,
                     textcoords="offset points", fontsize=9, ha=ha,
                     color="black" if on_front else MUTED)

    # Frontier line (connect A → B → C in token order)
    sub.plot([50, 200, 800], [0.30, 0.75, 0.92],
             color=ACCENT, lw=1.5, linestyle="--", alpha=0.6, zorder=2,
             label="Pareto frontier")
    sub.set_xscale("log")
    sub.set_xlabel("tokens per query (log)", fontsize=11)
    sub.set_ylabel("accuracy", fontsize=11)
    sub.set_title("A, B, C are on the frontier · D and E are dominated", fontsize=11)
    sub.grid(True, which="both", alpha=0.3)
    sub.legend(loc="lower right", fontsize=10)

    ax.text(0.06, 0.13,
            "Why this is the headline visual (not a single score)",
            fontsize=12, weight="bold", color=TITLE_COLOR)
    ax.text(0.06, 0.10,
            "Different users want different trade-offs:  cheap-and-OK  vs  expensive-and-great.\n"
            "The frontier shows ALL the legitimate options at once. The score (TPCA) picks one.",
            fontsize=10, va="top")

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


def page_full_pipeline(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "8. The complete pipeline",
                subtitle="Every function in metrics.py, in the order data flows.")

    # Layout: vertical stack of stages
    stages = [
        ("input",   "Many RunRecords  (one per attempt)",                 "#eef3fb", TITLE_COLOR),
        ("step1",   "_tokens_for_record(rec, V)\nper-attempt token count, build amortized over V", BOX_BG, BOX_EDGE),
        ("step2a",  "summarize(values)\n→ median, IQR  (heavy-tail honest summary)",                BOX_BG, BOX_EDGE),
        ("step2b",  "bootstrap_ci(values)\n→ (low, high)  confidence interval",                    BOX_BG, BOX_EDGE),
        ("step2c",  "tpca(records, V)  =  Σ tokens / Σ correct\n→ THE NUMBER",                     "#fff3e0", ACCENT),
        ("step3",   "tpca_curve(records)\n→ TPCA at V ∈ {1, 100, 10,000}  (mandatory by DECISIONS.md)", BOX_BG, BOX_EDGE),
        ("step4",   "ParetoPoint(method, accuracy, tokens_per_query)  →  pareto_frontier(points)\n→ THE PLOT", "#fff3e0", ACCENT),
    ]

    y = 0.82
    boxes = []
    for key, text, bg, edge in stages:
        height = 0.07 if "\n" not in text else 0.085
        weight = "bold" if bg == "#fff3e0" else "normal"
        draw_box(ax, 0.10, y - height, 0.80, height, text,
                 fontsize=10, weight=weight, facecolor=bg, edgecolor=edge)
        boxes.append((0.5, y - height))
        y -= height + 0.022

    # Arrows between consecutive boxes
    for i in range(len(boxes) - 1):
        x_mid, y_top = boxes[i]
        _, y_next = boxes[i + 1]
        draw_arrow(ax, x_mid, y_top, x_mid, y_next + 0.07, color="#888", lw=1.4)

    ax.text(0.06, 0.10,
            "Read the file top-to-bottom and you'll see the functions in roughly this order.\n"
            "Every later chunk plugs into this same shape — only the data source changes.",
            fontsize=10, va="top", color=MUTED, style="italic")

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


def page_cheatsheet(pdf, page_num, total):
    fig = plt.figure(figsize=PAGE)
    ax = blank_axes(fig)
    page_header(ax, page_num, total, "9. Cheat sheet",
                subtitle="Every formula on one page. Print this and stick it on the wall.")

    items = [
        ("Per-attempt tokens",
         "tokens = input_norm + output_norm + (build_norm / V)"),
        ("TPCA  —  the headline number",
         "TPCA(V) = Σ tokens / Σ correct          (lower is better; ∞ if 0 correct)"),
        ("TPCA curve  (mandatory for methods with build cost)",
         "tpca_curve(records) = { 1: ..., 100: ..., 10000: ... }"),
        ("Accuracy",
         "accuracy = Σ correct / N"),
        ("Distribution  (heavy-tail aware)",
         "summarize(values) → mean, median, q25, q75, n          (report median + IQR)"),
        ("Bootstrap 95% CI on the mean",
         "resample 10k times → percentiles[2.5%, 97.5%] of the resample means"),
        ("Pareto frontier",
         "drop any point dominated on BOTH axes; keep the rest"),
    ]
    y = 0.83
    for label, formula in items:
        ax.text(0.06, y, label, fontsize=12, weight="bold", color=TITLE_COLOR, va="top")
        draw_box(ax, 0.06, y - 0.060, 0.88, 0.045, formula,
                 fontsize=10, family="monospace",
                 facecolor=BOX_BG, edgecolor=BOX_EDGE)
        y -= 0.095

    ax.text(0.06, 0.12,
            "Companion: tokenbench/core/metrics.py  ·  tests: tests/test_metrics.py",
            fontsize=10, color=MUTED, family="monospace", va="top")
    ax.text(0.06, 0.09,
            "Locked decisions referenced here: DECISIONS.md  #1  (tokenizer),  #5  (build-cost amortization).",
            fontsize=9, color=MUTED, va="top", style="italic")

    page_footer(ax)
    pdf.savefig(fig); plt.close(fig)


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────

def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOTAL = 10
    with PdfPages(OUT_PATH) as pdf:
        page_cover(pdf, TOTAL)
        page_big_picture(pdf, 2, TOTAL)
        page_per_record_tokens(pdf, 3, TOTAL)
        page_tpca(pdf, 4, TOTAL)
        page_why_V_matters(pdf, 5, TOTAL)
        page_distribution(pdf, 6, TOTAL)
        page_bootstrap(pdf, 7, TOTAL)
        page_pareto(pdf, 8, TOTAL)
        page_full_pipeline(pdf, 9, TOTAL)
        page_cheatsheet(pdf, 10, TOTAL)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
