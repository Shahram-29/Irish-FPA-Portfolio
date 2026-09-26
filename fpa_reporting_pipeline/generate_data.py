"""Simulate a year of budget and eight months of general ledger actuals for a fictional
Dublin-based EMEA headquarters, Example Software EMEA Ltd. All company data is made up;
only the exchange rates (data/fx_rates.csv, from the ECB) are real.

    py generate_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline import prsi_rate

DATA = Path(__file__).parent / "data"
YEAR = pd.period_range("2026-01", "2026-12", freq="M")
ACTUAL_MONTHS = YEAR[:8]  # January to August 2026
rng = np.random.default_rng(2026)

# Revenue is billed per seat per month in three currencies.
REGIONS = {
    4000: {"currency": "EUR", "seats": 14000, "growth": 0.020, "price": 55.0},
    4010: {"currency": "GBP", "seats": 5000, "growth": 0.015, "price": 48.0},
    4020: {"currency": "USD", "seats": 7000, "growth": 0.020, "price": 60.0},
}
HOSTING_PER_SEAT = 6.00  # USD per seat per month
# Heads at the start and end of the year, and monthly cost per head in EUR.
DEPARTMENTS = {
    "CC100": ("Sales", 20, 26, 7000), "CC200": ("Marketing", 8, 10, 6000), "CC300": ("R&D", 30, 40, 8500),
    "CC400": ("Customer Success", 12, 15, 5000), "CC500": ("G&A", 10, 12, 6500),
}
# (account, cost centre, currency, monthly budget in local currency)
OTHER_COSTS = [(6100, "CC200", "EUR", 60000), (6100, "CC200", "GBP", 15000), (6200, "CC300", "USD", 20000),
               (6300, "CC100", "EUR", 15000), (6400, "CC500", "EUR", 45000), (6500, "CC500", "EUR", 10000)]


def heads(start, end, month_index):
    return round(start + (end - start) * month_index / 11)


def budget():
    rows = []
    for i, month in enumerate(YEAR):
        total_seats = 0
        for account, r in REGIONS.items():
            seats = round(r["seats"] * (1 + r["growth"]) ** i)
            total_seats += seats
            rows.append((month, account, "CC100", r["currency"], seats, -seats * r["price"]))
        rows.append((month, 5000, "CC300", "USD", total_seats, total_seats * HOSTING_PER_SEAT))
        for cc, (_, start, end, cost) in DEPARTMENTS.items():
            salaries = heads(start, end, i) * cost
            rows.append((month, 6000, cc, "EUR", heads(start, end, i), salaries))
            rows.append((month, 6010, cc, "EUR", 0, round(salaries * prsi_rate(month), 2)))
        rows += [(month, account, cc, cur, 0, amount) for account, cc, cur, amount in OTHER_COSTS]
    return pd.DataFrame(rows, columns=["period", "account", "cost_centre", "currency", "units", "amount"])


def actual_seats_and_price(account, i):
    r = REGIONS[account]
    if account == 4000:    # EU: grows faster than budget, but discounted to EUR 54 from April
        return round(r["seats"] * 1.025 ** i), 55.0 if i < 3 else 54.0
    if account == 4010:    # UK: grows more slowly than budget
        return round(r["seats"] * 1.005 ** i), 48.0
    seats = round(r["seats"] * 1.02 ** i) + (1400 if i >= 5 else 0)  # USD: large deal signed in June
    return seats, 60.0 if i < 6 else 62.4                               # and a 4% price rise from July


def actuals():
    rows = []
    for i, month in enumerate(ACTUAL_MONTHS):
        day = month.to_timestamp(how="end").normalize()
        total_seats = 0
        for account, r in REGIONS.items():
            seats, price = actual_seats_and_price(account, i)
            total_seats += seats
            rows.append((day, account, "CC100", r["currency"], seats, -seats * price, "Subscription billing"))
        rows.append((day, 5000, "CC300", "USD", total_seats, round(total_seats * 6.30, 2), "Cloud hosting invoice"))
        for cc, (name, start, end, cost) in DEPARTMENTS.items():
            n = heads(start, end, i) + (1 if cc == "CC100" and i >= 2 else 0) - (3 if cc == "CC300" and i >= 3 else 0)
            salaries = round(n * cost * 1.02, 2)  # pay review 2% above budget
            rows.append((day, 6000, cc, "EUR", n, salaries, f"Payroll {name}"))
            rows.append((day, 6010, cc, "EUR", 0, round(salaries * prsi_rate(month), 2), f"Employer PRSI {name}"))
        for account, cc, cur, amount in OTHER_COSTS:
            amount *= {6200: 1.10, 6300: 1.20}.get(account, 1.0) * rng.uniform(0.97, 1.03)
            if account == 6100 and cur == "EUR" and i == 2:
                amount += 35000                      # spring campaign
            if account == 6500 and i == 4:
                amount += 30000                      # one-off legal fees
            if account == 6400:
                amount = 45000
            rows.append((day, account, cc, cur, 0, round(amount, 2), "Supplier invoices"))
    gl = pd.DataFrame(rows, columns=["posting_date", "account", "cost_centre", "currency", "units", "amount",
                                     "description"])
    gl.insert(0, "transaction_id", [f"JE{100000 + i}" for i in range(len(gl))])
    # Two data problems for the checks to find: a duplicated posting and a line with no cost centre.
    gl = pd.concat([gl, gl[(gl.account == 6300) & (gl.posting_date == gl.posting_date.max())]])
    gl.loc[(gl.account == 6200) & (gl.posting_date == gl.posting_date.max()), "cost_centre"] = None
    return gl


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    budget().to_csv(DATA / "budget.csv", index=False)
    actuals().to_csv(DATA / "gl_actuals.csv", index=False)
    print("Wrote data/budget.csv and data/gl_actuals.csv")
