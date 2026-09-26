"""Simulate the sales ledger of a fictional Irish food and drink distributor, Example Distribution Ltd,
from January 2024 to 31 August 2026. All data is made up.

Writes data/invoices.csv, the ledger as it looks on 31 August 2026 (later payments aren't known yet),
and data/payments_after_cutoff.csv, what happened to the open invoices afterwards, kept apart and
used only to backtest the cash forecast.

    py generate_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
CUTOFF = pd.Timestamp("2026-08-31")
rng = np.random.default_rng(11)

# Hidden payment behaviour: (share of customers, mean days late, spread, chance an invoice is never paid)
BEHAVIOUR = {"reliable": (0.6, 1, 5, 0.0), "slow": (0.3, 20, 12, 0.005), "risky": (0.1, 45, 25, 0.05)}


def simulate(n_customers=150):
    kinds = rng.choice(list(BEHAVIOUR), size=n_customers, p=[b[0] for b in BEHAVIOUR.values()])
    # Five reliable customers start paying late from March 2026: a change the ledger has to reveal.
    deteriorating = set(rng.choice(np.flatnonzero(kinds == "reliable"), size=5, replace=False))
    rows = []
    for c, kind in enumerate(kinds):
        _, mean, spread, never = BEHAVIOUR[kind]
        typical = rng.lognormal(np.log(6000), 0.8)
        terms = 60 if rng.random() < 0.2 else 30
        for month in pd.date_range("2024-01-01", CUTOFF, freq="MS"):
            for _ in range(rng.poisson(2)):
                issued = month + pd.Timedelta(days=int(rng.integers(0, 28)))
                if issued > CUTOFF:
                    continue
                amount = round(typical * rng.lognormal(0, 0.4), 2)
                late = rng.normal(mean, spread)
                if c in deteriorating and issued >= pd.Timestamp("2026-03-01"):
                    late += 35
                late += 5 * (amount > 2 * typical) + 7 * (issued.month == 12)  # big invoices, Christmas
                due = issued + pd.Timedelta(days=terms)
                paid = pd.NaT if rng.random() < never else due + pd.Timedelta(days=max(-10, round(late)))
                rows.append((c + 1, issued, due, amount, paid))
    inv = pd.DataFrame(rows, columns=["customer_id", "invoice_date", "due_date", "amount", "paid_date"])
    inv = inv.sort_values("invoice_date", kind="stable").reset_index(drop=True)
    inv.insert(0, "invoice_id", [f"INV{100001 + i}" for i in range(len(inv))])
    return inv


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    inv = simulate()
    after = inv.paid_date.isna() | (inv.paid_date > CUTOFF)
    inv.loc[after, ["invoice_id", "paid_date"]].to_csv(DATA / "payments_after_cutoff.csv", index=False)
    ledger = inv.assign(paid_date=inv.paid_date.where(~after))
    ledger.to_csv(DATA / "invoices.csv", index=False, date_format="%Y-%m-%d")
    print(f"{len(inv)} invoices; {after.sum()} open at {CUTOFF.date()} worth €{inv.amount[after].sum():,.0f}")
