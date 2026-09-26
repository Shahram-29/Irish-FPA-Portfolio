"""Month-end FP&A pipeline for Example Software EMEA Ltd (fictional): general ledger to
budget vs actual, revenue and payroll variance bridges, a 12-month rolling forecast and
written commentary.

    py pipeline.py --month 2026-08            # print the results
    py pipeline.py --refresh-fx               # re-download ECB exchange rates first
"""
import argparse
import io
from pathlib import Path

import numpy as np
import pandas as pd
import requests

DATA = Path(__file__).parent / "data"
LINES = ["Revenue", "Cost of revenue", "Payroll", "Marketing programmes", "Software and tools", "Travel",
         "Rent and facilities", "Professional fees"]
OPEX = LINES[2:]
ECB_FX = "https://data-api.ecb.europa.eu/service/data/EXR/M.{currencies}.EUR.SP00.A"
EMPLOYER_PRSI = {"2026-01": 0.1125, "2026-10": 0.1140}  # Class A employer rate, pay above EUR 552 a week
MATERIALITY = (25_000, 0.05)  # comment on variances of at least EUR 25k and 5%


def prsi_rate(month):
    return [rate for start, rate in EMPLOYER_PRSI.items() if pd.Period(start, "M") <= month][-1]


def fetch_fx(currencies=("GBP", "USD"), start="2026-01"):
    """ECB monthly average reference rates, in units of each currency per euro."""
    r = requests.get(ECB_FX.format(currencies="+".join(currencies)),
                     params={"format": "csvdata", "detail": "dataonly", "startPeriod": start}, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), usecols=["CURRENCY", "TIME_PERIOD", "OBS_VALUE"])
    return df.set_axis(["currency", "period", "rate"], axis=1)[["period", "currency", "rate"]]


def load(data=DATA):
    d = {name: pd.read_csv(data / f"{name}.csv") for name in
         ("gl_actuals", "budget", "chart_of_accounts", "cost_centres", "budget_rates", "fx_rates")}
    d["gl_actuals"]["period"] = pd.to_datetime(d["gl_actuals"].posting_date).dt.to_period("M")
    for name in ("budget", "fx_rates"):
        d[name]["period"] = pd.to_datetime(d[name].period).dt.to_period("M")
    return d


def check(gl, coa, cost_centres, fx):
    """Data checks on the ledger. Returns (cleaned ledger, issues as (severity, check, detail)).

    Warnings are fixed and reported; errors mean the numbers can't be trusted and stop the run.
    """
    issues = []
    dup = gl.duplicated("transaction_id")
    if dup.any():
        issues.append(("warning", "Duplicate postings",
                       f"{plural(dup.sum(), 'repeated posting')} removed: {', '.join(gl.transaction_id[dup])}"))
        gl = gl[~dup]
    no_cc = gl.cost_centre.isna()
    if no_cc.any():
        issues.append(("warning", "Missing cost centre",
                       f"{plural(no_cc.sum(), 'line')} posted to UNALLOCATED: {', '.join(gl.transaction_id[no_cc])}"))
        gl = gl.assign(cost_centre=gl.cost_centre.fillna("UNALLOCATED"))
    bad_cc = ~gl.cost_centre.isin(set(cost_centres.cost_centre) | {"UNALLOCATED"})
    if bad_cc.any():
        issues.append(("error", "Unknown cost centre", ", ".join(sorted(set(gl.cost_centre[bad_cc])))))
    unmapped = ~gl.account.isin(coa.account)
    if unmapped.any():
        issues.append(("error", "Unmapped account", ", ".join(map(str, sorted(set(gl.account[unmapped]))))))
    rates = pd.concat([fx, pd.DataFrame({"period": gl.period.unique(), "currency": "EUR", "rate": 1.0})])
    missing = gl.merge(rates, on=["period", "currency"], how="left").rate.isna()
    if missing.any():
        pairs = gl.loc[missing.values, ["period", "currency"]].drop_duplicates()
        issues.append(("error", "Missing exchange rate",
                       ", ".join(f"{c} {p}" for p, c in pairs.itertuples(index=False))))
    return gl, issues


def prepare(d):
    """Actuals at each month's ECB average rate and budget at the budget rates, in EUR with profit sign
    (income positive, costs negative), plus P&L line and department."""
    gl, issues = check(d["gl_actuals"], d["chart_of_accounts"], d["cost_centres"], d["fx_rates"])
    if any(severity == "error" for severity, _, _ in issues):
        raise ValueError("Data checks failed: " + "; ".join(f"{c}: {detail}" for s, c, detail in issues if s == "error"))
    eur = pd.DataFrame({"currency": "EUR", "rate": 1.0, "period": gl.period.unique()})
    actual = gl.merge(pd.concat([d["fx_rates"], eur]), on=["period", "currency"])
    budget = d["budget"].merge(d["budget_rates"], on="currency")
    out = []
    for df in (actual, budget):
        df = df.merge(d["chart_of_accounts"][["account", "line"]], on="account")
        df = df.merge(d["cost_centres"], on="cost_centre", how="left").fillna({"department": "Unallocated"})
        out.append(df.assign(eur=-df.amount / df.rate))
    return out[0], out[1], issues


def pnl(actual, budget, periods):
    """Budget vs actual by P&L line with subtotals. Positive variance = favourable."""
    a = actual[actual.period.isin(periods)].groupby("line").eur.sum()
    b = budget[budget.period.isin(periods)].groupby("line").eur.sum()
    t = pd.DataFrame({"Actual": a, "Budget": b}).reindex(LINES).fillna(0.0)
    t.loc["Gross profit"] = t.loc["Revenue"] + t.loc["Cost of revenue"]
    t.loc["Operating expenses"] = t.loc[OPEX].sum()
    t.loc["Operating profit"] = t.loc["Gross profit"] + t.loc["Operating expenses"]
    t = t.loc[["Revenue", "Cost of revenue", "Gross profit", *OPEX, "Operating expenses", "Operating profit"]]
    t["Variance"] = t.Actual - t.Budget
    t["Variance %"] = t.Variance / t.Budget.abs()
    return t


def revenue_bridge(actual, budget, periods):
    """Split the revenue variance by currency into volume, price and exchange-rate effects.

    With seats V, local price P and rate R (currency per EUR), for budget (b) and actual (a):
      volume = (Va - Vb) x Pb / Rb,  price = Va x (Pa - Pb) / Rb,  FX = Va x Pa x (1/Ra - 1/Rb)
    The three add up exactly to actual revenue minus budget revenue.
    """
    def by_month(df):
        rev = df[(df.line == "Revenue") & df.period.isin(periods)]
        g = rev.groupby(["currency", "period"]).agg(V=("units", "sum"), local=("amount", "sum"), R=("rate", "first"))
        return g.assign(P=-g.local / g.V)
    m = by_month(actual).join(by_month(budget), lsuffix="a", rsuffix="b")
    parts = pd.DataFrame({
        "Budget": m.Vb * m.Pb / m.Rb,
        "Volume": (m.Va - m.Vb) * m.Pb / m.Rb,
        "Price": m.Va * (m.Pa - m.Pb) / m.Rb,
        "FX": m.Va * m.Pa * (1 / m.Ra - 1 / m.Rb),
        "Actual": m.Va * m.Pa / m.Ra,
    })
    return parts.groupby(level="currency").sum()


def payroll_bridge(actual, budget, periods):
    """Payroll variance by department, split into headcount and cost-per-head effects (favourable +)."""
    def by_month(df):
        pay = df[(df.line == "Payroll") & df.period.isin(periods)]
        g = pay.groupby(["department", "period"]).agg(H=("units", "sum"), cost=("eur", "sum"))
        return g.assign(C=-g.cost / g.H)
    m = by_month(actual).join(by_month(budget), lsuffix="a", rsuffix="b")
    parts = pd.DataFrame({"Headcount effect": -(m.Ha - m.Hb) * m.Cb, "Cost per head effect": -m.Ha * (m.Ca - m.Cb)})
    out = parts.groupby(level="department").sum()
    last = m.xs(max(periods), level="period")
    out.insert(0, "Budget heads", last.Hb)
    out.insert(1, "Actual heads", last.Ha)
    out["Variance"] = out["Headcount effect"] + out["Cost per head effect"]
    return out


def rolling_forecast(actual, budget, last, horizon=12):
    """Monthly forecast (EUR, profit sign) by P&L line for the `horizon` months after `last`.

    Revenue: seats grow at the median of the last three month-on-month growth rates, so a one-off
    jump isn't extrapolated; price and exchange rate held at last month's. Hosting: last month's
    cost per seat. Payroll: last month's heads plus the budgeted hires, at last month's cost per head,
    with employer PRSI at the rate in force. Other costs: average of the last three months.
    """
    future = pd.period_range(last + 1, periods=horizon, freq="M")
    hist = actual[actual.period <= last]
    recent = pd.period_range(max(last - 2, hist.period.min()), last, freq="M")  # up to three months of history
    steps = np.arange(1, horizon + 1)
    rows = []

    rev = hist[hist.line == "Revenue"].groupby(["currency", "period"]).agg(
        V=("units", "sum"), local=("amount", "sum"), R=("rate", "first"))
    seats_total = np.zeros(horizon)
    for currency, g in rev.groupby(level="currency"):
        g = g.droplevel("currency")
        growth = g.V.pct_change().reindex(recent).median()  # NaN with only one month of history
        seats = g.V[last] * (1 + (0 if pd.isna(growth) else growth)) ** steps
        seats_total += seats
        rows += [(p, "Revenue", s * -g.local[last] / g.V[last] / g.R[last]) for p, s in zip(future, seats)]

    host = hist[(hist.line == "Cost of revenue") & (hist.period == last)]
    per_seat_eur = host.eur.sum() / host.units.sum()
    rows += [(p, "Cost of revenue", s * per_seat_eur) for p, s in zip(future, seats_total)]

    salaries = hist[(hist.account == 6000) & (hist.period == last)].groupby("cost_centre").agg(
        H=("units", "sum"), eur=("eur", "sum"))
    planned = budget[budget.account == 6000].groupby(["cost_centre", "period"]).units.sum()
    for cc, s in salaries.iterrows():
        hires = planned[cc].diff().reindex(future).fillna(0).cumsum()  # no plan beyond the budget year
        for p, h in zip(future, s.H + hires):
            rows.append((p, "Payroll", h * s.eur / s.H * (1 + prsi_rate(p))))

    other = hist[hist.line.isin(OPEX[1:]) & hist.period.isin(recent)]
    for line, avg in (other.groupby("line").eur.sum() / len(recent)).items():
        rows += [(p, line, avg) for p in future]

    return pd.DataFrame(rows, columns=["period", "line", "eur"]).pivot_table(
        index="period", columns="line", values="eur", aggfunc="sum").reindex(columns=LINES)


def monthly(df):
    """EUR by month and P&L line, with operating profit."""
    t = df.pivot_table(index="period", columns="line", values="eur", aggfunc="sum").reindex(columns=LINES)
    return t.assign(**{"Operating profit": t.sum(axis=1)})


def outlook(actual, budget, forecast, last):
    """Full-year latest estimate: actuals to `last` plus forecast for the rest of the year, against budget."""
    rest = forecast[forecast.index.year == last.year]
    le = pd.concat([monthly(actual[actual.period <= last]), rest.assign(**{"Operating profit": rest.sum(axis=1)})])
    fy = pd.DataFrame({"Latest estimate": le.sum(), "Budget": monthly(budget).sum()})
    return fy.assign(Variance=fy["Latest estimate"] - fy.Budget)


def eur(x):
    size = f"€{abs(x) / 1e6:,.2f}m" if abs(x) >= 1e6 else f"€{abs(x) / 1e3:,.0f}k"
    return ("−" if x < 0 else "") + size


def signed(x):
    return ("+" if x >= 0 else "−") + eur(abs(x))


def plural(n, word):
    return f"{n:.0f} {word}{'' if n == 1 else 's'}"


def commentary(res, materiality=MATERIALITY):
    """Rule-based commentary: every sentence comes from the numbers in `res`."""
    y, bridge, payroll, fy, last = res["pnl_ytd"], res["revenue_bridge"], res["payroll_bridge"], res["outlook"], res["month"]
    op, rev, op_month = y.loc["Operating profit"], y.loc["Revenue"], res["pnl_month"].loc["Operating profit"]
    fav = lambda v: "ahead of" if v >= 0 else "behind"
    out = [f"In {last.strftime('%B')}, operating profit was {eur(op_month.Actual)}, {eur(abs(op_month.Variance))} "
           f"{fav(op_month.Variance)} budget.",
           f"Year to date to {last.strftime('%B %Y')}, operating profit is {eur(op.Actual)}, {eur(abs(op.Variance))} "
           f"({abs(op['Variance %']):.1%}) {fav(op.Variance)} budget.",
           f"Revenue is {signed(rev.Variance)} against budget: volume {signed(bridge.Volume.sum())}, "
           f"price {signed(bridge.Price.sum())}, exchange rates {signed(bridge.FX.sum())}."]
    for currency, row in bridge.iterrows():
        effects = row[["Volume", "Price", "FX"]]
        material = effects[effects.abs() >= materiality[0]].sort_values(key=abs, ascending=False)
        if len(material):
            out.append(f"{currency} revenue: " + ", ".join(f"{k.lower()} {signed(v)}" for k, v in material.items()) + ".")
    for line in ["Cost of revenue", *OPEX]:
        v, pct = y.loc[line, "Variance"], y.loc[line, "Variance %"]
        if abs(v) >= materiality[0] and abs(pct) >= materiality[1]:
            out.append(f"{line} is {eur(abs(v))} ({abs(pct):.0%}) {'under' if v > 0 else 'over'} budget.")
    for dept, row in payroll.iterrows():
        gap = row["Actual heads"] - row["Budget heads"]
        if gap and abs(row["Headcount effect"]) >= materiality[0]:
            out.append(f"{dept}: {plural(abs(gap), 'head')} {'over' if gap > 0 else 'under'} budget "
                       f"({signed(row['Headcount effect'])} year to date).")
    rate_effect = payroll["Cost per head effect"].sum()
    if abs(rate_effect) >= materiality[0]:
        out.append(f"Pay per head is running {'above' if rate_effect < 0 else 'below'} budget across departments "
                   f"({signed(rate_effect)} year to date).")
    le = fy.loc["Operating profit"]
    out.append(f"Full-year outlook: operating profit {eur(le['Latest estimate'])} against a budget of "
               f"{eur(le.Budget)} ({signed(le.Variance)}), using actuals to {last.strftime('%B')} and the rolling forecast after.")
    for severity, name, detail in res["issues"]:
        out.append(f"Data check ({severity}): {name.lower()}, {detail}.")
    return out


def run(month="2026-08", data=DATA):
    d = load(data)
    actual, budget, issues = prepare(d)
    last = pd.Period(month, "M")
    ytd = pd.period_range(f"{last.year}-01", last, freq="M")
    forecast = rolling_forecast(actual, budget, last)
    res = {"month": last, "issues": issues, "actual": actual, "budget": budget,
           "pnl_month": pnl(actual, budget, [last]), "pnl_ytd": pnl(actual, budget, ytd),
           "revenue_bridge": revenue_bridge(actual, budget, ytd), "payroll_bridge": payroll_bridge(actual, budget, ytd),
           "forecast": forecast, "outlook": outlook(actual, budget, forecast, last)}
    res["commentary"] = commentary(res)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--month", default="2026-08")
    ap.add_argument("--refresh-fx", action="store_true", help="re-download ECB monthly rates")
    a = ap.parse_args()
    if a.refresh_fx:
        fetch_fx().to_csv(DATA / "fx_rates.csv", index=False)
    res = run(a.month)
    pd.options.display.float_format = "{:,.0f}".format
    print(res["pnl_ytd"].drop(columns="Variance %"), "\n")
    print(res["revenue_bridge"], "\n")
    print(res["payroll_bridge"], "\n")
    print(res["outlook"], "\n")
    print("\n".join(res["commentary"]))
