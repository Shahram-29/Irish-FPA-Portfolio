"""Simulate customer-level subscription data for a fictional Dublin B2B software company,
Example SaaS Ltd, from January 2023 to August 2026. All data is made up.

    py generate_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
MONTHS = pd.period_range("2023-01", "2026-08", freq="M")
rng = np.random.default_rng(7)


def simulate():
    customers, rows, next_id = [], [], 1
    active = {}  # customer_id -> [mrr, billing, signup index]
    for i, month in enumerate(MONTHS):
        # Existing customers: monthly payers can churn, expand or contract any month;
        # annual payers only at renewal. Churn is higher in the first year.
        for cid, (mrr, billing, start) in list(active.items()):
            age = i - start
            if billing == "annual" and age % 12:
                continue
            churn = 0.025 if age < 12 else 0.014
            churn *= 12 if billing == "annual" else 1  # a year's worth of churn at each renewal
            u = rng.random()
            if u < churn:
                del active[cid]
            elif u < churn + (0.045 if billing == "monthly" else 0.30):
                active[cid][0] = round(mrr * rng.uniform(1.15, 1.5), -1)
            elif u < churn + (0.060 if billing == "monthly" else 0.38):
                active[cid][0] = round(mrr * rng.uniform(0.7, 0.85), -1)
        # New customers: growing from about 25 to 45 a month.
        for _ in range(rng.poisson(25 + 20 * i / len(MONTHS))):
            billing = "annual" if rng.random() < 0.3 else "monthly"
            mrr = round(float(np.clip(rng.lognormal(np.log(450), 0.6), 99, 5000)), -1)
            active[next_id] = [mrr, billing, i]
            customers.append((next_id, month, billing, rng.choice(["Inbound", "Outbound", "Partner"], p=[.5, .3, .2])))
            next_id += 1
        rows += [(cid, month, mrr) for cid, (mrr, _, _) in active.items()]
    subs = pd.DataFrame(rows, columns=["customer_id", "month", "mrr"])
    cust = pd.DataFrame(customers, columns=["customer_id", "signup_month", "billing", "channel"])
    # Sales and marketing spend, growing through the period, with noise.
    spend = pd.DataFrame({"month": MONTHS,
                          "sales_and_marketing": (180_000 * 1.013 ** np.arange(len(MONTHS))
                                                  * rng.uniform(0.9, 1.1, len(MONTHS))).round(-2)})
    return subs, cust, spend


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    subs, cust, spend = simulate()
    for df in (subs, cust, spend):
        for col in ("month", "signup_month"):
            if col in df:
                df[col] = df[col].dt.to_timestamp().dt.date  # first day of the month
    subs.to_csv(DATA / "subscriptions.csv", index=False)
    cust.to_csv(DATA / "customers.csv", index=False)
    spend.to_csv(DATA / "sales_marketing_spend.csv", index=False)
    last = subs[subs.month == subs.month.max()]
    print(f"{len(cust)} customers, {len(last)} active in August 2026, MRR €{last.mrr.sum():,.0f}")
