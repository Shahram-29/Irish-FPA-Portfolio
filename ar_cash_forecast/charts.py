"""Charts for the README and the Streamlit app. Each returns a matplotlib figure.

    py charts.py      # redraws figures/*.png
"""
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from ar import BUCKETS, run

FIGURES = Path(__file__).parent / "figures"
SURFACE, INK, INK_2, MUTED, GRID, BASELINE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
AGEING_RAMP = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]  # older debt = darker


def _style(ax, title, grid="y"):
    ax.set_facecolor(SURFACE)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(length=0, labelcolor=INK_2)
    ax.set_title(title, loc="left", color=INK, fontsize=11)


def ageing_and_dso(res):
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 4), facecolor=SURFACE)
    totals = res["ageing"][BUCKETS].sum()
    left.bar(range(len(totals)), totals, color=AGEING_RAMP, width=0.65)
    for i, v in enumerate(totals):
        left.annotate(f"€{v / 1e6:,.2f}m\n{v / totals.sum():.0%}", (i, v), xytext=(0, 3), textcoords="offset points",
                      ha="center", fontsize=8, color=INK_2)
    left.set_xticks(range(len(totals)), [b.replace(" days", "\ndays") for b in BUCKETS], fontsize=8)
    left.yaxis.set_major_formatter(lambda y, _: f"€{y / 1e6:,.1f}m")
    left.set_ylim(0, totals.max() * 1.2)
    _style(left, "Open receivables by days past due, 31 Aug 2026")
    d = res["dso_trend"]
    right.plot(d.index, d, color=BLUE, linewidth=2)
    right.annotate(f"{d.iloc[-1]:.0f} days", (d.index[-1], d.iloc[-1]), xytext=(-4, 6), textcoords="offset points",
                   ha="right", fontsize=9, color=INK_2)
    right.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    right.set_ylim(0, d.max() * 1.2)
    _style(right, "Days sales outstanding (90-day basis), month-end")
    fig.tight_layout()
    return fig


def calibration_chart(ev):
    c = ev["calibration"]
    fig, ax = plt.subplots(figsize=(5.5, 4.5), facecolor=SURFACE)
    ax.plot([0, 1], [0, 1], color=BASELINE, linewidth=1, linestyle=(0, (4, 3)), label="Perfect calibration")
    ax.plot(c.predicted, c.actual, color=BLUE, linewidth=2, marker="o", markersize=6, label="Model, test invoices")
    ax.set_xlim(0, 0.8)
    ax.set_ylim(0, 0.8)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("Predicted chance of paying late (decile average)", color=INK_2)
    ax.set_ylabel("Share actually paid late", color=INK_2)
    ax.legend(frameon=False, loc="upper left", labelcolor=INK_2, fontsize=8)
    _style(ax, f"Calibration on Jan–Apr 2026 invoices (AUC {ev['auc']:.2f})")
    fig.tight_layout()
    return fig


def backtest_chart(bt):
    fig, ax = plt.subplots(figsize=(8, 4), facecolor=SURFACE)
    x = np.arange(len(bt))
    series = [("Contractual (due dates)", MUTED), ("Model forecast", BLUE), ("Actual", ORANGE)]
    for i, (col, colour) in enumerate(series):
        ax.bar(x + (i - 1) * 0.26, bt[col], width=0.24, color=colour, label=col)
        for xi, v in zip(x, bt[col]):
            ax.annotate(f"€{v / 1e6:,.2f}m", (xi + (i - 1) * 0.26, v), xytext=(0, 3), textcoords="offset points",
                        ha="center", fontsize=7, color=INK_2)
    ax.set_xticks(x, bt.index)
    ax.yaxis.set_major_formatter(lambda y, _: f"€{y / 1e6:,.1f}m")
    ax.legend(frameon=False, loc="upper right", labelcolor=INK_2, fontsize=8)
    _style(ax, "Cash collected from the 31 Aug 2026 receivables: forecasts vs actual")
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    matplotlib.use("Agg")
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    FIGURES.mkdir(exist_ok=True)
    r = run()
    figures = {"ageing_and_dso": ageing_and_dso(r), "calibration": calibration_chart(r["evaluation"]),
               "cash_forecast_backtest": backtest_chart(r["backtest"])}
    for name, fig in figures.items():
        fig.savefig(FIGURES / f"{name}.png", dpi=150)
    print("Wrote", ", ".join(figures))
