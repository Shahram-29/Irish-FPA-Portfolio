"""Receivables, late-payment risk and cash forecast.  py -m streamlit run ar_cash_forecast/app.py"""
import matplotlib.pyplot as plt
import streamlit as st

import charts
from ar import BUCKETS, run

st.set_page_config(page_title="Receivables and cash forecast", layout="wide")


@st.cache_data
def results():
    return run()


r = results()
o, ev, bt = r["open"], r["evaluation"], r["backtest"]
st.title("Example Distribution Ltd: receivables and cash forecast")
st.caption("Simulated sales ledger for a portfolio project, as at 31 August 2026. "
           "Payments after that date are held back and used only for the backtest.")

cols = st.columns(4)
cols[0].metric("Open receivables", f"€{o.amount.sum() / 1e6:,.2f}m")
cols[1].metric("Overdue", f"{o.amount[o.days_past_due > 0].sum() / o.amount.sum():.0%}")
cols[2].metric("DSO", f"{r['dso']:.0f} days")
cols[3].metric("Expected in September", f"€{bt['Model forecast'].iloc[0] / 1e6:,.2f}m")

ageing, customers, cash, model = st.tabs(["Ageing", "Customers at risk", "Cash forecast", "Risk model"])
with ageing:
    st.pyplot(charts.ageing_and_dso(r))
    bucket = st.selectbox("Show customers with balances in", ["Total", *BUCKETS])
    t = r["ageing"]
    st.dataframe(t[t[bucket] > 0].sort_values(bucket, ascending=False).style.format("€{:,.0f}"))
with customers:
    st.markdown("Ranked by the open amount expected to be paid more than 30 days late "
                "(open amount × modelled chance of paying late).")
    st.dataframe(r["customers"].head(25).style.format(
        {"open": "€{:,.0f}", "overdue": "€{:,.0f}", "at_risk": "€{:,.0f}", "within_90": "€{:,.0f}",
         "chance_late": "{:.0%}"}))
with cash:
    st.pyplot(charts.backtest_chart(bt))
    st.dataframe(bt.style.format("€{:,.0f}"))
    st.dataframe(o.groupby("band", observed=False).agg(invoices=("amount", "size"), open=("amount", "sum"))
                 .style.format({"open": "€{:,.0f}"}))
with model:
    c = st.columns(3)
    c[0].metric("AUC, test invoices", f"{ev['auc']:.3f}", f"{ev['auc'] - ev['auc_baseline']:+.3f} vs track record alone")
    c[1].metric("Brier score", f"{ev['brier']:.3f}")
    c[2].metric("Late share, test invoices", f"{ev['late_share']:.1%}")
    left, right = st.columns(2)
    left.pyplot(charts.calibration_chart(ev))
    right.markdown(f"Logistic regression, trained on {ev['n_train']:,} invoices issued Jul 2024–Dec 2025 and "
                   f"tested on {ev['n_test']:,} issued Jan–Apr 2026. Standardised coefficients:")
    right.dataframe(ev["coefficients"].rename("coefficient").to_frame().style.format("{:+.2f}"))
    right.caption("late_rate and mean_days_late move together, so their individual signs shouldn't be read alone.")
plt.close("all")
