"""Interactive month-end pack.  py -m streamlit run app.py"""
import io

import matplotlib.pyplot as plt
import streamlit as st

import charts
from board_pack import build
from pipeline import commentary, load, run

st.set_page_config(page_title="FP&A month-end pipeline", layout="wide")


@st.cache_data
def results(month):
    return run(month)


def money(df, pct_cols=()):
    fmt = {c: "{:+.1%}" if c in pct_cols else "{:,.0f}" for c in df.columns}
    return df.style.format(fmt)


months = sorted(load()["gl_actuals"].period.astype(str).unique())
with st.sidebar:
    month = st.selectbox("Month", months, index=len(months) - 1)
    threshold = st.slider("Comment on variances of at least (€k)", 5, 100, 25, step=5)
res = results(month)

st.title("Example Software EMEA Ltd: month-end pack")
st.caption("Simulated company data for a portfolio project. Exchange rates are real ECB monthly averages.")

y, le = res["pnl_ytd"], res["outlook"].loc["Operating profit"]
cols = st.columns(3)
cols[0].metric("Revenue, year to date", f"€{y.loc['Revenue', 'Actual'] / 1e6:,.2f}m",
               f"{y.loc['Revenue', 'Variance'] / 1000:+,.0f}k vs budget")
cols[1].metric("Operating profit, year to date", f"€{y.loc['Operating profit', 'Actual'] / 1e6:,.2f}m",
               f"{y.loc['Operating profit', 'Variance'] / 1000:+,.0f}k vs budget")
cols[2].metric("Operating profit, full-year outlook", f"€{le['Latest estimate'] / 1e6:,.2f}m",
               f"{le.Variance / 1000:+,.0f}k vs budget")

summary, pl, revenue, costs, forecast, checks = st.tabs(
    ["Commentary", "Profit and loss", "Revenue bridge", "Costs and headcount", "Rolling forecast", "Data checks"])
with summary:
    st.markdown("\n".join(f"- {line}" for line in commentary(res, (threshold * 1000, 0.05))))
with pl:
    period = st.radio("Period", ["Year to date", "Month"], horizontal=True)
    st.dataframe(money(res["pnl_ytd" if period == "Year to date" else "pnl_month"], ["Variance %"]))
    st.caption("EUR, profit sign: income positive, costs negative. Positive variance = favourable.")
with revenue:
    st.pyplot(charts.revenue_bridge_chart(res["revenue_bridge"]))
    st.dataframe(money(res["revenue_bridge"]))
with costs:
    st.pyplot(charts.variance_chart(y))
    st.dataframe(money(res["payroll_bridge"]))
with forecast:
    st.pyplot(charts.forecast_chart(res))
    st.dataframe(money(res["outlook"]))
with checks:
    if res["issues"]:
        st.table([{"Severity": s, "Check": c, "Detail": d} for s, c, d in res["issues"]])
    else:
        st.success("All checks passed.")
plt.close("all")

with st.sidebar:
    pack = io.BytesIO()
    build(res, pack)
    st.download_button("Download board pack (.pptx)", pack.getvalue(), f"board_pack_{month}.pptx",
                       "application/vnd.openxmlformats-officedocument.presentationml.presentation")
