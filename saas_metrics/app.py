"""SaaS metrics and scenario model.  py -m streamlit run saas_metrics/app.py"""
from pathlib import Path

import matplotlib.pyplot as plt
import streamlit as st

import charts
from metrics import CASH, FIXED_COSTS, GROSS_MARGIN, breakeven, connect, load, project, runway

st.set_page_config(page_title="SaaS metrics", layout="wide")


@st.cache_data
def metrics():
    return load(connect())


m = metrics()
u = m["unit"]
st.title("Example SaaS Ltd: recurring revenue metrics")
st.caption("Simulated customer data for a portfolio project. Metrics are calculated in SQL (DuckDB) and Python.")

cols = st.columns(4)
cols[0].metric("ARR", f"€{u['ARR'] / 1e6:,.2f}m")
cols[1].metric("Net revenue retention (12 months)", f"{m['retention'].nrr.iloc[-1]:.0%}")
cols[2].metric("LTV to CAC", f"{u['LTV to CAC']:.1f}x")
cols[3].metric("CAC payback", f"{u['CAC payback (months)']:.0f} months")

overview, cohorts, unit, rev_rec, scenario, sql = st.tabs(
    ["Growth", "Cohorts", "Unit economics", "Revenue recognition", "Scenario model", "SQL"])
with overview:
    st.pyplot(charts.arr_and_bridge(m["bridge"]))
    st.dataframe(m["bridge"].tail(12).style.format("{:,.0f}"))
    st.pyplot(charts.retention_chart(m["retention"]))
with cohorts:
    st.pyplot(charts.cohort_heatmap(m["cohorts"]))
    st.dataframe(m["cohorts"][[3, 6, 12, 24]].rename(columns=lambda c: f"Month {c}").style.format("{:.0%}", na_rep=""))
with unit:
    st.dataframe({k: (f"{v:.2%}" if "churn" in k or "expansion" in k else f"{v:,.1f}") for k, v in u.items()})
    st.markdown(f"CAC = sales and marketing spend ÷ new customers (last 3 months). "
                f"LTV = ARPA × gross margin ({GROSS_MARGIN:.0%}) ÷ monthly logo churn (last 12 months). "
                f"Payback = CAC ÷ (ARPA × gross margin).")
with rev_rec:
    st.pyplot(charts.deferred_chart(m["deferred"]))
    st.dataframe(m["deferred"].tail(12).style.format("{:,.0f}"))
with scenario:
    left, right = st.columns([1, 3])
    with left:
        new = st.slider("New customers per month", 0, 100, round(u["New customers per month"]))
        churn = st.slider("Monthly logo churn (%)", 0.0, 5.0, round(u["Monthly logo churn"] * 100, 1), 0.1) / 100
        expansion = st.slider("Monthly net expansion (%)", -2.0, 3.0, round(u["Monthly net expansion"] * 100, 1), 0.1) / 100
        price = st.slider("One-off price change (%)", -20, 20, 0) / 100
        cac = st.slider("CAC (€)", 2_000, 20_000, int(round(u["CAC"], -2)), 100)
        cash = st.number_input("Cash today (€)", 0, 50_000_000, CASH, 250_000)
        fixed = st.number_input("Other monthly costs (€)", 0, 5_000_000, FIXED_COSTS, 25_000)
    base = project(u)
    scen = project(u, new_per_month=new, churn=churn, net_expansion=expansion, price_change=price, cac=cac,
                   cash=cash, fixed_costs=fixed)
    with right:
        c = st.columns(3)
        c[0].metric("ARR in 36 months", f"€{scen.ARR.iloc[-1] / 1e6:,.1f}m",
                    f"{(scen.ARR.iloc[-1] - base.ARR.iloc[-1]) / 1e6:+,.1f}m vs base")
        be, rw = breakeven(scen), runway(scen)
        c[1].metric("Cash-flow breakeven", f"month {be}" if be else "not within 36 months")
        c[2].metric("Cash runs out", f"month {rw}" if rw else "not within 36 months")
        st.pyplot(charts.scenario_chart(base, scen))
        st.caption("Base case = recent actuals. Cash and other costs are assumptions, not from the data.")
with sql:
    for f in sorted((Path(__file__).parent / "sql").glob("*.sql")):
        st.subheader(f.name)
        st.code(f.read_text(), language="sql")
plt.close("all")
