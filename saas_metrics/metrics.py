"""SaaS metrics for Example SaaS Ltd (simulated): MRR bridge, retention, unit economics,
IFRS 15 deferred revenue and a 36-month scenario model with cash runway.

    py metrics.py
"""
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
GROSS_MARGIN = 0.78  # assumption: hosting and support at 22% of revenue
# Scenario assumptions that aren't in the data: cash in the bank, and costs other than sales and marketing.
CASH = 6_000_000
FIXED_COSTS = 450_000  # per month
FIXED_COST_GROWTH = 0.005


def connect(data=HERE / "data"):
    con = duckdb.connect()
    for table, file in (("subscriptions", "subscriptions.csv"), ("customers", "customers.csv"),
                        ("spend", "sales_marketing_spend.csv")):
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_csv_auto('{(data / file).as_posix()}')")
    return con


def query(con, name):
    return con.execute((HERE / "sql" / f"{name}.sql").read_text()).df()


def load(con):
    """Every metric table, keyed by name."""
    bridge = query(con, "mrr_bridge").set_index("month")
    cohorts = query(con, "cohort_retention").pivot(index="cohort", columns="months_since_signup", values="retention")
    retention = query(con, "net_retention").set_index("month")
    subs = con.execute("SELECT * FROM subscriptions").df()
    customers = con.execute("SELECT * FROM customers").df()
    spend = con.execute("SELECT * FROM spend").df().set_index("month").sales_and_marketing
    return {"bridge": bridge, "cohorts": cohorts, "retention": retention,
            "deferred": deferred_revenue(subs, customers), "unit": unit_economics(bridge, spend)}


def unit_economics(bridge, spend, window=3, churn_window=12):
    """CAC, ARPA, logo churn, LTV and CAC payback at the latest month.

    CAC      = sales and marketing spend / new customers, over the last `window` months
    ARPA     = MRR / customers (average revenue per account, monthly)
    Churn    = average monthly logo churn over the last `churn_window` months
    LTV      = ARPA x gross margin / monthly churn
    Payback  = CAC / (ARPA x gross margin), in months
    """
    recent = bridge.iloc[-window:]
    cac = spend.loc[recent.index].sum() / recent.new_customers.sum()
    last = bridge.iloc[-1]
    arpa = last.closing / last.closing_customers
    churn = (bridge.churned_customers / bridge.opening_customers).iloc[-churn_window:].mean()
    net_expansion = ((bridge.expansion + bridge.contraction) / bridge.opening).iloc[-churn_window:].mean()
    ltv = arpa * GROSS_MARGIN / churn
    return {"MRR": last.closing, "ARR": last.closing * 12, "Customers": int(last.closing_customers),
            "ARPA": arpa, "New customers per month": recent.new_customers.mean(), "CAC": cac,
            "Monthly logo churn": churn, "Monthly net expansion": net_expansion, "LTV": ltv,
            "LTV to CAC": ltv / cac, "CAC payback (months)": cac / (arpa * GROSS_MARGIN)}


def deferred_revenue(subs, customers):
    """IFRS 15 view of the same subscriptions: billings, revenue and the deferred revenue balance.

    Monthly payers are billed each month for that month's service. Annual payers are billed 12
    months in advance at signup and each renewal. Revenue is recognised as the service is
    delivered (one month's MRR per month), so annual invoices create a contract liability,
    deferred revenue, that unwinds over the year.
    """
    s = subs.merge(customers[["customer_id", "signup_month", "billing"]], on="customer_id")
    months_in = (s.month.dt.year - s.signup_month.dt.year) * 12 + (s.month.dt.month - s.signup_month.dt.month)
    annual = s.billing == "annual"
    s["billed"] = np.where(annual, np.where(months_in % 12 == 0, 12 * s.mrr, 0), s.mrr)
    t = s.groupby("month").agg(billings=("billed", "sum"), revenue=("mrr", "sum"))
    t["deferred_revenue"] = (t.billings - t.revenue).cumsum()
    return t


def project(start, months=36, new_per_month=None, churn=None, net_expansion=None, price_change=0.0,
            cac=None, cash=CASH, fixed_costs=FIXED_COSTS, fixed_cost_growth=FIXED_COST_GROWTH):
    """Monthly projection from the latest position. Defaults come from recent actuals (`start` is
    unit_economics()). Returns customers, MRR, ARR, costs, cash flow and cash by month."""
    new = start["New customers per month"] if new_per_month is None else new_per_month
    churn = start["Monthly logo churn"] if churn is None else churn
    net_expansion = start["Monthly net expansion"] if net_expansion is None else net_expansion
    cac = start["CAC"] if cac is None else cac
    customers, arpa = start["Customers"], start["ARPA"] * (1 + price_change)
    rows = []
    for m in range(1, months + 1):
        customers = customers * (1 - churn) + new
        arpa *= 1 + net_expansion
        mrr = customers * arpa
        sm, fixed = new * cac, fixed_costs * (1 + fixed_cost_growth) ** m
        flow = mrr * GROSS_MARGIN - sm - fixed
        cash += flow
        rows.append({"month": m, "customers": customers, "MRR": mrr, "ARR": mrr * 12, "gross profit": mrr * GROSS_MARGIN,
                     "sales and marketing": sm, "other costs": fixed, "cash flow": flow, "cash": cash})
    return pd.DataFrame(rows).set_index("month")


def runway(projection):
    """Months until cash runs out, or None if it never does within the projection."""
    out = projection.index[projection.cash < 0]
    return int(out[0]) if len(out) else None


def breakeven(projection):
    """First month with positive cash flow, or None if it doesn't happen within the projection."""
    positive = projection.index[projection["cash flow"] >= 0]
    return int(positive[0]) if len(positive) else None


if __name__ == "__main__":
    pd.options.display.float_format = "{:,.2f}".format
    m = load(connect())
    for k, v in m["unit"].items():
        print(f"{k:<26}{v:>14,.3f}" if isinstance(v, float) else f"{k:<26}{v:>14,}")
    print(m["bridge"].tail(3).T, "\n")
    print(m["retention"].tail(3), "\n")
    print(m["deferred"].tail(3), "\n")
    p = project(m["unit"])
    print(p.iloc[[0, 11, 23, 35]][["customers", "ARR", "cash flow", "cash"]])
    print("Runway:", runway(p))
