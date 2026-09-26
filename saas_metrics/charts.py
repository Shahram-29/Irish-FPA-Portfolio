"""Charts for the README and the Streamlit app. Each returns a matplotlib figure.

    py charts.py      # redraws figures/*.png
"""
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from metrics import connect, load, project

FIGURES = Path(__file__).parent / "figures"
SURFACE, INK, INK_2, MUTED, GRID, BASELINE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
MOVES = {"new": ("New", "#2a78d6"), "expansion": ("Expansion", "#1baf7a"),
         "contraction": ("Contraction", "#eda100"), "churn": ("Churn", "#eb6834")}
BLUE, ORANGE = "#2a78d6", "#eb6834"


def _style(ax, title, grid="y"):
    ax.set_facecolor(SURFACE)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(length=0, labelcolor=INK_2)
    ax.set_title(title, loc="left", color=INK, fontsize=11)


def _euro(ax, scale=1e3, suffix="k"):
    ax.yaxis.set_major_formatter(lambda y, _: f"{'−' if y < 0 else ''}€{abs(y) / scale:,.0f}{suffix}")


def arr_and_bridge(bridge, months=24):
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 4.2), facecolor=SURFACE,
                                      gridspec_kw={"width_ratios": [1, 1.4]})
    left.plot(bridge.index, bridge.closing * 12, color=BLUE, linewidth=2)
    left.annotate(f"€{bridge.closing.iloc[-1] * 12 / 1e6:.1f}m", (bridge.index[-1], bridge.closing.iloc[-1] * 12),
                  xytext=(-4, 6), textcoords="offset points", ha="right", fontsize=9, color=INK_2)
    _euro(left, 1e6, "m")
    left.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _style(left, "Annual recurring revenue (MRR × 12)")

    b = bridge.iloc[-months:]
    width = 20  # days
    up = down = 0
    for col, (label, colour) in MOVES.items():
        values = b[col]
        base = up if col in ("new", "expansion") else down
        right.bar(b.index, values, width=width, bottom=base, color=colour, label=label)
        if col in ("new", "expansion"):
            up = up + values
        else:
            down = down + values
    right.axhline(0, color=BASELINE, linewidth=1)
    _euro(right)
    right.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    right.legend(frameon=False, ncol=4, loc="upper left", labelcolor=INK_2, fontsize=8)
    _style(right, f"MRR movements, last {months} months")
    right.set_ylim(down.min() * 1.3, up.max() * 1.35)
    fig.tight_layout()
    return fig


def cohort_heatmap(cohorts, max_months=36):
    c = cohorts.loc[:, :max_months]
    cmap = LinearSegmentedColormap.from_list("div", ["#e34948", "#f0efec", "#2a78d6"])
    fig, ax = plt.subplots(figsize=(12, 5), facecolor=SURFACE)
    im = ax.imshow(c.values, aspect="auto", cmap=cmap, norm=TwoSlopeNorm(vmin=0.5, vcenter=1.0, vmax=1.5))
    ax.set_yticks(range(len(c)), [f"{d.year} Q{(d.month - 1) // 3 + 1}" for d in c.index], fontsize=8)
    ax.set_xticks(range(0, c.shape[1], 3))
    ax.set_xlabel("Months since signup", color=INK_2)
    ax.tick_params(length=0, labelcolor=INK_2)
    for side in ax.spines.values():
        side.set_visible(False)
    bar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    bar.ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    bar.ax.tick_params(labelsize=8, labelcolor=INK_2)
    bar.outline.set_visible(False)
    ax.set_title("Net revenue retention by signup cohort (100% = the cohort's first-month MRR)",
                 loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    return fig


def retention_chart(retention):
    fig, ax = plt.subplots(figsize=(8, 3.8), facecolor=SURFACE)
    for col, label, colour in (("nrr", "Net revenue retention", BLUE), ("grr", "Gross revenue retention", ORANGE)):
        ax.plot(retention.index, retention[col], color=colour, linewidth=2, label=label)
        ax.annotate(f"{label}: {retention[col].iloc[-1]:.0%}", (retention.index[-1], retention[col].iloc[-1]),
                    xytext=(-4, 7), textcoords="offset points", ha="right", fontsize=8, color=INK_2)
    ax.axhline(1, color=BASELINE, linewidth=1)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.legend(frameon=False, loc="lower left", labelcolor=INK_2, fontsize=8)
    _style(ax, "12-month revenue retention")
    fig.tight_layout()
    return fig


def deferred_chart(deferred):
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 3.8), facecolor=SURFACE)
    left.plot(deferred.index, deferred.billings, color=ORANGE, linewidth=1.5, label="Billings (invoiced)")
    left.plot(deferred.index, deferred.revenue, color=BLUE, linewidth=2, label="Revenue (recognised)")
    left.legend(frameon=False, loc="upper left", labelcolor=INK_2, fontsize=8)
    _euro(left)
    left.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _style(left, "Billings vs revenue by month")
    right.fill_between(deferred.index, deferred.deferred_revenue, color="#86b6ef")
    right.plot(deferred.index, deferred.deferred_revenue, color=BLUE, linewidth=1.5)
    _euro(right, 1e6, "m")
    right.yaxis.set_major_formatter(lambda y, _: f"€{y / 1e6:,.1f}m")
    right.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _style(right, "Deferred revenue balance (contract liability)")
    fig.tight_layout()
    return fig


def scenario_chart(base, scenario=None):
    fig, (left, right) = plt.subplots(1, 2, figsize=(12, 3.8), facecolor=SURFACE)
    for ax, col, title in ((left, "ARR", "Projected ARR"), (right, "cash", "Projected cash balance")):
        ax.plot(base.index, base[col], color=MUTED if scenario is not None else BLUE,
                linestyle=(0, (4, 3)) if scenario is not None else "-", linewidth=2, label="Base case")
        if scenario is not None:
            ax.plot(scenario.index, scenario[col], color=BLUE, linewidth=2, label="Scenario")
        ax.axhline(0, color=BASELINE, linewidth=1)
        ax.yaxis.set_major_formatter(lambda y, _: f"€{y / 1e6:,.1f}m")
        ax.set_xlabel("Months from now", color=INK_2)
        _style(ax, title)
    if scenario is not None:
        left.legend(frameon=False, loc="upper left", labelcolor=INK_2, fontsize=8)
    fig.tight_layout()
    return fig


if __name__ == "__main__":
    matplotlib.use("Agg")
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    FIGURES.mkdir(exist_ok=True)
    m = load(connect())
    figures = {"arr_and_mrr_movements": arr_and_bridge(m["bridge"]), "cohort_retention": cohort_heatmap(m["cohorts"]),
               "revenue_retention": retention_chart(m["retention"]), "deferred_revenue": deferred_chart(m["deferred"]),
               "base_case_projection": scenario_chart(project(m["unit"]))}
    for name, fig in figures.items():
        fig.savefig(FIGURES / f"{name}.png", dpi=150)
    print("Wrote", ", ".join(figures))
