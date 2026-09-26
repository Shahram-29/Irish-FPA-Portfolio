"""Charts for the board pack, the README and the Streamlit app. Each returns a matplotlib figure."""
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from pipeline import LINES, monthly

SURFACE, INK, INK_2, MUTED, GRID, BASELINE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, TOTAL = "#2a78d6", "#eb6834", "#52514e"
FAVOURABLE, UNFAVOURABLE = "#2a78d6", "#e34948"  # diverging poles


def _style(ax, title, grid="y"):
    ax.set_facecolor(SURFACE)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(length=0, labelcolor=INK_2)
    ax.set_title(title, loc="left", color=INK, fontsize=11)


def k(x, signed=False):
    return f"{x / 1000:+,.0f}k" if signed else f"{x / 1000:,.0f}k"


def revenue_bridge_chart(bridge):
    """Waterfall from budget revenue to actual revenue: volume, price, exchange rates."""
    steps = [("Budget", bridge.Budget.sum())] + [(c, bridge[c].sum()) for c in ("Volume", "Price", "FX")] \
        + [("Actual", bridge.Actual.sum())]
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
    running = 0
    for i, (name, v) in enumerate(steps):
        if name in ("Budget", "Actual"):
            bottom, height, colour, label = 0, v, TOTAL, k(v)
            running = v
        else:
            bottom, height = (running, v) if v >= 0 else (running + v, -v)
            colour, label = (FAVOURABLE if v >= 0 else UNFAVOURABLE), k(v, signed=True)
            running += v
        ax.bar(i, height, bottom=bottom, color=colour, width=0.6)
        ax.annotate(label, (i, bottom + height), xytext=(0, 3), textcoords="offset points", ha="center",
                    fontsize=9, color=INK_2)
    lo = min(bridge.Budget.sum(), bridge.Actual.sum())
    ax.set_ylim(lo * 0.97, max(bridge.Budget.sum(), bridge.Actual.sum()) * 1.015)  # zoom to the movements
    ax.set_xticks(range(len(steps)), ["Budget", "Volume", "Price", "Exchange\nrates", "Actual"])
    ax.yaxis.set_major_formatter(lambda y, _: f"€{y / 1e6:,.2f}m")
    _style(ax, "Revenue year to date: budget to actual (€)")
    ax.text(0, -0.16, "Axis starts above zero to show the movements.", transform=ax.transAxes, fontsize=8, color=MUTED)
    fig.tight_layout()
    return fig


def variance_chart(pnl_ytd):
    """Year-to-date variance by P&L line, favourable positive."""
    v = pnl_ytd.loc[LINES, "Variance"][::-1]
    fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
    ax.barh(v.index, v, color=[FAVOURABLE if x >= 0 else UNFAVOURABLE for x in v], height=0.6)
    for i, x in enumerate(v):
        ax.annotate(k(x, signed=True), (x, i), xytext=(4 if x >= 0 else -4, 0), textcoords="offset points",
                    va="center", ha="left" if x >= 0 else "right", fontsize=8, color=INK_2)
    ax.axvline(0, color=BASELINE, linewidth=1)
    pad = v.abs().max() * 0.25
    ax.set_xlim(v.min() - pad, v.max() + pad)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x / 1000:,.0f}k")
    _style(ax, "Variance to budget, year to date (€, favourable = positive)", grid="x")
    ax.spines["bottom"].set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (FAVOURABLE, UNFAVOURABLE)]
    ax.legend(handles, ["Favourable", "Unfavourable"], frameon=False, loc="lower right", labelcolor=INK_2, fontsize=8)
    fig.tight_layout()
    return fig


def forecast_chart(res):
    """Monthly revenue and operating profit: actuals, rolling forecast and budget."""
    last = res["month"]
    act = monthly(res["actual"][res["actual"].period <= last])
    fc = res["forecast"].assign(**{"Operating profit": res["forecast"].sum(axis=1)})
    bud = monthly(res["budget"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), facecolor=SURFACE)
    for ax, col in zip(axes, ("Revenue", "Operating profit")):
        x = lambda idx: idx.to_timestamp()
        ax.plot(x(bud.index), bud[col], color=MUTED, linewidth=1.5, linestyle=(0, (4, 3)), label="Budget 2026")
        ax.plot(x(act.index), act[col], color=BLUE, linewidth=2, label="Actual")
        joined = pd.concat([act[col].iloc[-1:], fc[col]])
        ax.plot(x(joined.index), joined, color=ORANGE, linewidth=2, label="Rolling forecast")
        ax.yaxis.set_major_formatter(lambda y, _: f"€{y / 1000:,.0f}k")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.tick_params(axis="x", labelsize=8)
        _style(ax, f"{col} by month")
    axes[0].legend(frameon=False, loc="upper left", labelcolor=INK_2, fontsize=8)
    fig.tight_layout()
    return fig
