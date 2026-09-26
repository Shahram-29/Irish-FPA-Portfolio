"""Irish corporation tax, R&D credit and Pillar Two scenario model.
py -m streamlit run irish_corporation_tax/app.py"""
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import charts
from ct_model import EXAMPLE, RD, projection, year

st.set_page_config(page_title="Irish corporation tax model", layout="wide")
st.title("Irish corporation tax: R&D credit and Pillar Two")
st.caption("Illustrative model for a fictional company, using 2026 Irish rules checked against Revenue guidance. "
           "Not tax advice; the Pillar Two calculation is simplified.")

with st.sidebar:
    m = 1_000_000
    inputs = {
        "trading_profit": st.number_input("Trading profit (€m, before R&D credit)", 0.0, 5_000.0, 40.0, 1.0) * m,
        "non_trading_income": st.number_input("Non-trading income, e.g. interest (€m)", 0.0, 500.0, 1.0, 0.5) * m,
        "rd_spend": st.number_input("Qualifying R&D spend (€m)", 0.0, 500.0, 8.0, 0.5) * m,
        "payroll": st.number_input("Irish payroll (€m)", 0.0, 2_000.0, 30.0, 1.0) * m,
        "tangible_assets": st.number_input("Irish tangible assets (€m)", 0.0, 5_000.0, 60.0, 5.0) * m,
        "in_scope_group": st.toggle("Group revenue of €750m or more (Pillar Two applies)", True),
    }
    growth = st.slider("Profit growth a year (%)", -20, 30, 8) / 100

r = year(**inputs)
p2, alt = r["pillar_two"], r["pillar_two_if_ordinary_credit"]
c = st.columns(4)
c[0].metric("Corporation tax", f"€{r['corporation_tax'] / m:,.2f}m")
c[1].metric(f"R&D credit ({RD['rate']:.0%})", f"€{r['rd_credit'] / m:,.2f}m")
c[2].metric("Pillar Two effective rate", f"{p2['etr']:.2%}")
c[3].metric("Top-up tax", f"€{p2['top_up_tax'] / m:,.2f}m",
            f"€{(alt['top_up_tax'] - p2['top_up_tax']) / m:,.2f}m less than with an ordinary credit", delta_color="off")

this_year, pillar, three_years = st.tabs(["2026 position", "Pillar Two", "Three-year projection"])
with this_year:
    st.table(pd.DataFrame({
        "€": [r["profit"], r["corporation_tax"], r["rd_credit"], *r["rd_instalments"], r["net_tax_after_credit"],
              *[a for _, a in r["preliminary_tax"]], r["balance_with_return"]]},
        index=["Profit before the R&D credit", "Corporation tax (12.5% trading, 25% non-trading)", "R&D credit",
               "  first instalment (with the 2026 return)", "  second instalment (2027 return)",
               "  third instalment (2028 return)", "Tax after the R&D credit",
               *[f"Preliminary tax, month {mo}" for mo, _ in r["preliminary_tax"]], "Balance with the return"],
    ).style.format("{:,.0f}"))
with pillar:
    st.pyplot(charts.pillar_two_chart(inputs))
    st.table(pd.DataFrame({
        "Qualified refundable credit": [p2["etr"], p2["carve_out"], p2["excess_profit"], p2["top_up_rate"], p2["top_up_tax"]],
        "If it were an ordinary credit": [alt["etr"], alt["carve_out"], alt["excess_profit"], alt["top_up_rate"], alt["top_up_tax"]]},
        index=["Effective tax rate", "Substance carve-out (€)", "Excess profit (€)", "Top-up rate", "Top-up tax (€)"],
    ).T.style.format({"Effective tax rate": "{:.2%}", "Top-up rate": "{:.2%}", "Substance carve-out (€)": "{:,.0f}",
                      "Excess profit (€)": "{:,.0f}", "Top-up tax (€)": "{:,.0f}"}))
with three_years:
    table, _ = projection(inputs, profit_growth=growth)
    st.pyplot(charts.cash_tax_chart(table))
    st.dataframe(table.T.style.format("{:,.0f}", subset=pd.IndexSlice[table.columns.drop("Effective tax rate (P&L)"), :])
                 .format("{:.1%}", subset=pd.IndexSlice[["Effective tax rate (P&L)"], :]))
plt.close("all")
