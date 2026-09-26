"""Charts for the README and the Streamlit app. Each returns a matplotlib figure.

    py charts.py      # redraws figures/*.png
"""
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from ct_model import EXAMPLE, P2, projection, year

FIGURES = Path(__file__).parent / "figures"
SURFACE, INK, INK_2, MUTED, GRID, BASELINE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"


def _style(ax, title, grid="y"):
    ax.set_facecolor(SURFACE)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(length=0, labelcolor=INK_2)
    ax.set_title(title, loc="left", color=INK, fontsize=11)


def pillar_two_chart(inputs=EXAMPLE):
    """Top-up tax as R&D spend rises, with the credit treated as qualified refundable vs ordinary."""
    spend = np.linspace(0, 20_000_000, 41)
    q = [year(**{**inputs, "rd_spend": s})["pillar_two"]["top_up_tax"] for s in spend]
    o = [year(**{**inputs, "rd_spend": s})["pillar_two_if_ordinary_credit"]["top_up_tax"] for s in spend]
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
    ax.plot(spend, o, color=ORANGE, linewidth=2, label="If the R&D credit were an ordinary tax credit")
    ax.plot(spend, q, color=BLUE, linewidth=2, label="As a qualified refundable credit (how Ireland's works)")
    ax.axvline(inputs["rd_spend"], color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    ax.annotate("Current R&D spend", (inputs["rd_spend"], max(o) * 0.55), xytext=(4, 0), textcoords="offset points",
                fontsize=8, color=INK_2)
    ax.set_xticks(np.arange(0, 20_000_001, 5_000_000))
    ax.xaxis.set_major_formatter(lambda x, _: f"€{x / 1e6:,.0f}m")
    ax.yaxis.set_major_formatter(lambda y, _: f"€{y / 1e6:,.1f}m")
    ax.set_xlabel("Qualifying R&D spend", color=INK_2)
    ax.legend(frameon=False, loc="upper left", labelcolor=INK_2, fontsize=8)
    _style(ax, "Pillar Two top-up tax in Ireland, by R&D spend (group in scope)")
    fig.tight_layout()
    return fig


def cash_tax_chart(table):
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
    x = np.arange(len(table))
    ax.bar(x, table["Corporation tax paid"], color=BLUE, width=0.5, label="Corporation tax paid")
    ax.bar(x, table["Top-up tax paid"], bottom=table["Corporation tax paid"], color=ORANGE, width=0.5,
           label="Top-up tax paid")
    ax.bar(x, -table["R&D credit received"], color=AQUA, width=0.5, label="R&D credit received")
    ax.plot(x, table["Net cash tax"], color=INK, marker="o", markersize=6, linewidth=1.5, label="Net cash tax")
    for xi, v in zip(x, table["Net cash tax"]):
        ax.annotate(f"€{v / 1e6:,.2f}m", (xi, v), xytext=(10, 4), textcoords="offset points", fontsize=8, color=INK)
    ax.axhline(0, color=BASELINE, linewidth=1)
    ax.set_xticks(x, table.index)
    ax.yaxis.set_major_formatter(lambda y, _: f"{'−' if y < 0 else ''}€{abs(y) / 1e6:,.0f}m")
    ax.legend(frameon=False, loc="upper left", labelcolor=INK_2, fontsize=8, ncol=2)
    ax.set_ylim(-table["R&D credit received"].max() * 1.4, (table["Corporation tax paid"] + table["Top-up tax paid"]).max() * 1.35)
    _style(ax, "Cash tax by calendar year: payments out, R&D credit in")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    matplotlib.use("Agg")
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    FIGURES.mkdir(exist_ok=True)
    figures = {"pillar_two_by_rd_spend": pillar_two_chart(), "cash_tax": cash_tax_chart(projection()[0])}
    for name, fig in figures.items():
        fig.savefig(FIGURES / f"{name}.png", dpi=150)
    print("Wrote", ", ".join(figures), "| minimum rate", P2["minimum_rate"])
