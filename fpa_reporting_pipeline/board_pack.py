"""Build the month-end board pack (PowerPoint) and the README charts from the pipeline results.

    py board_pack.py --month 2026-08      # writes output/board_pack_2026-08.pptx and figures/*.png
"""
import argparse
import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

import charts
from pipeline import run

HERE = Path(__file__).parent
INK, INK_2, MUTED = RGBColor(0x0B, 0x0B, 0x0B), RGBColor(0x52, 0x51, 0x4E), RGBColor(0x89, 0x87, 0x81)


def text(slide, content, left, top, width, height, size=14, colour=INK, bold=False):
    frame = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height)).text_frame
    frame.word_wrap = True
    for i, line in enumerate([content] if isinstance(content, str) else content):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.text = line
        para.font.size, para.font.bold, para.font.color.rgb = Pt(size), bold, colour
        para.space_after = Pt(4)
    return frame


def kpi(slide, label, value, note, left):
    text(slide, label, left, 1.2, 3.0, 0.4, size=12, colour=INK_2)
    text(slide, value, left, 1.55, 3.0, 0.6, size=28, bold=True)
    text(slide, note, left, 2.15, 3.0, 0.4, size=12, colour=INK_2)


def new_slide(prs, title):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    text(slide, title, 0.5, 0.3, 12.3, 0.7, size=26, bold=True)
    text(slide, "Example Software EMEA Ltd · simulated data for a portfolio project", 0.5, 7.0, 12.3, 0.3,
         size=9, colour=MUTED)
    return slide


def table(slide, df, left, top, width, row_height=0.3, size=10):
    rows, cols = df.shape[0] + 1, df.shape[1] + 1
    shape = slide.shapes.add_table(rows, cols, Inches(left), Inches(top), Inches(width), Inches(row_height * rows))
    cells = [[df.index.name or ""] + list(df.columns)] + [[i] + list(r) for i, r in zip(df.index, df.values)]
    for r, values in enumerate(cells):
        for c, v in enumerate(values):
            cell = shape.table.cell(r, c)
            cell.text = str(v)
            para = cell.text_frame.paragraphs[0]
            para.font.size = Pt(size)
            para.font.bold = r == 0
            if c > 0:
                para.alignment = PP_ALIGN.RIGHT


def picture(slide, fig, left, top, width):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200)
    plt.close(fig)
    buf.seek(0)
    slide.shapes.add_picture(buf, Inches(left), Inches(top), width=Inches(width))


def k(x):
    return f"({abs(x) / 1000:,.0f})" if x < 0 else f"{x / 1000:,.0f}"


def build(res, out):
    month = res["month"].strftime("%B %Y")
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    text(slide, "Example Software EMEA Ltd", 0.8, 2.4, 11.5, 1, size=40, bold=True)
    text(slide, f"Month-end pack: {month}", 0.8, 3.4, 11.5, 0.8, size=24, colour=INK_2)
    text(slide, "Simulated company data for a portfolio project. Exchange rates: ECB monthly averages.",
         0.8, 4.3, 11.5, 0.5, size=12, colour=MUTED)

    slide = new_slide(prs, "Summary")
    y, fy = res["pnl_ytd"], res["outlook"]
    le = fy.loc["Operating profit"]
    kpis = [("Revenue, year to date", y.loc["Revenue", "Actual"], y.loc["Revenue", "Variance"]),
            ("Operating profit, year to date", y.loc["Operating profit", "Actual"], y.loc["Operating profit", "Variance"]),
            ("Operating profit, full-year outlook", le["Latest estimate"], le.Variance)]
    for i, (label, value, variance) in enumerate(kpis):
        kpi(slide, label, f"€{value / 1e6:,.2f}m", f"€{variance / 1000:+,.0f}k vs budget", 0.5 + i * 3.6)
    commentary = [c for c in res["commentary"] if not c.startswith("Data check")]
    text(slide, ["• " + c for c in commentary], 0.5, 2.8, 12.3, 4.1, size=12, colour=INK_2)

    slide = new_slide(prs, f"Profit and loss, year to date to {month} (€k)")
    t = y.assign(**{"Variance %": y["Variance %"].map(lambda v: f"{v:+.1%}")})
    for col in ("Actual", "Budget", "Variance"):
        t[col] = t[col].map(k)
    table(slide, t.rename_axis("€k"), 0.5, 1.2, 9.0)
    text(slide, ["Positive variance = favourable.", "Costs are shown in brackets.",
                 "Actuals at ECB monthly average rates; budget at budget rates."], 9.8, 1.2, 3.1, 2, size=11,
         colour=INK_2)

    slide = new_slide(prs, "Revenue: volume, price and exchange rates")
    picture(slide, charts.revenue_bridge_chart(res["revenue_bridge"]), 0.4, 1.1, 7.2)
    b = res["revenue_bridge"].map(k).rename_axis("€k")
    table(slide, b, 7.8, 1.3, 5.1, size=10)
    text(slide, ["Volume: extra seats at budget price and rate.", "Price: price change on actual seats at budget rate.",
                 "Exchange rates: actual revenue at actual vs budget rate."], 7.8, 3.0, 5.1, 1.5, size=11, colour=INK_2)

    slide = new_slide(prs, "Costs and headcount")
    picture(slide, charts.variance_chart(y), 0.4, 1.1, 6.6)
    p = res["payroll_bridge"].copy()
    for col in ("Headcount effect", "Cost per head effect", "Variance"):
        p[col] = p[col].map(k)
    p[["Budget heads", "Actual heads"]] = p[["Budget heads", "Actual heads"]].astype(int)
    table(slide, p.rename_axis("Payroll (€k)"), 7.2, 1.3, 5.8, size=9)
    text(slide, ["Heads at the latest month; effects are year to date.",
                 "Headcount effect: extra or missing heads at budget cost per head.",
                 "Cost per head effect: actual heads at actual vs budget cost per head."],
         7.2, 3.6, 5.8, 1.5, size=11, colour=INK_2)

    slide = new_slide(prs, "Rolling 12-month forecast")
    picture(slide, charts.forecast_chart(res), 0.4, 1.1, 8.6)
    o = fy.map(k).rename_axis("Full year (€k)")
    table(slide, o, 9.2, 1.2, 3.9, row_height=0.28, size=9)
    text(slide, "Revenue: seats grow at the median of the last three monthly growth rates; price and FX held at the "
                "latest month. Payroll: latest heads plus budgeted hires, employer PRSI 11.40% from October. "
                "Other costs: last three months' average.", 0.5, 4.3, 8.4, 1.2, size=11, colour=INK_2)

    slide = new_slide(prs, "Data checks")
    issues = res["issues"] or [("ok", "All checks passed", "")]
    text(slide, [f"{s.upper()}: {name}. {detail}" for s, name, detail in issues], 0.5, 1.2, 12.3, 2, size=14)
    text(slide, ["Checks run before any numbers are reported:",
                 "• Duplicate transaction IDs (removed, warning)", "• Missing cost centre (posted to UNALLOCATED, warning)",
                 "• Unknown cost centre, unmapped account, missing exchange rate (errors: the run stops)"],
         0.5, 3.4, 12.3, 2, size=12, colour=INK_2)

    prs.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--month", default="2026-08")
    a = ap.parse_args()
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans"]
    res = run(a.month)
    (HERE / "output").mkdir(exist_ok=True)
    (HERE / "figures").mkdir(exist_ok=True)
    build(res, HERE / "output" / f"board_pack_{a.month}.pptx")
    figures = {"revenue_bridge": charts.revenue_bridge_chart(res["revenue_bridge"]),
               "variance_by_line": charts.variance_chart(res["pnl_ytd"]),
               "rolling_forecast": charts.forecast_chart(res)}
    for name, fig in figures.items():
        fig.savefig(HERE / "figures" / f"{name}.png", dpi=150)
        plt.close(fig)
    print(f"Wrote output/board_pack_{a.month}.pptx and figures/")
