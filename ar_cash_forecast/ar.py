"""Accounts receivable for Example Distribution Ltd (simulated) at 31 August 2026: ageing, DSO,
a late-payment risk model and a probability-weighted cash collection forecast, backtested
against what was actually collected afterwards.

    py ar.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DATA = Path(__file__).parent / "data"
CUTOFF = pd.Timestamp("2026-08-31")
LATE = 30  # "late" = paid more than 30 days after the due date, or never paid
BUCKETS = ["Not yet due", "1–30 days", "31–60 days", "61–90 days", "Over 90 days"]
FEATURES = ["late_rate", "mean_days_late", "history", "log_amount", "amount_vs_usual", "december"]
RECENT = 180  # payment behaviour is measured over the last 180 days
TRAIN = ("2024-07-01", "2025-12-31")  # invoices used to fit the model
TEST = ("2026-01-01", "2026-04-30")   # later invoices, all with known outcomes by the cut-off
WINDOWS = [(0, 30, "Sep 2026 (days 1–30)"), (30, 60, "Oct 2026 (days 31–60)"), (60, 90, "Nov 2026 (days 61–90)")]
BANDS = [(0, 0.15, "Low"), (0.15, 0.5, "Medium"), (0.5, 1.01, "High")]


def load(data=DATA):
    inv = pd.read_csv(data / "invoices.csv", parse_dates=["invoice_date", "due_date", "paid_date"])
    later = pd.read_csv(data / "payments_after_cutoff.csv", parse_dates=["paid_date"])
    return inv, later


def open_at(inv, as_of=CUTOFF):
    """Invoices issued by `as_of` and not paid by then, with days past due and ageing bucket."""
    o = inv[(inv.invoice_date <= as_of) & ~(inv.paid_date <= as_of)].copy()
    o["days_past_due"] = (as_of - o.due_date).dt.days
    o["bucket"] = pd.cut(o.days_past_due, [-np.inf, 0, 30, 60, 90, np.inf], labels=BUCKETS)
    return o


def ageing(inv, as_of=CUTOFF):
    """Open balance by customer and ageing bucket."""
    t = open_at(inv, as_of).pivot_table(index="customer_id", columns="bucket", values="amount",
                                        aggfunc="sum", observed=False, fill_value=0)
    return t.assign(Total=t.sum(axis=1)).sort_values("Total", ascending=False)


def dso(inv, as_of=CUTOFF, days=90):
    """Days sales outstanding: receivables ÷ credit sales over the last `days` days × `days`."""
    sales = inv.amount[(inv.invoice_date > as_of - pd.Timedelta(days=days)) & (inv.invoice_date <= as_of)].sum()
    return open_at(inv, as_of).amount.sum() / sales * days


def history_features(inv, times):
    """For each invoice, what was known about its customer at time `times[i]`: share of invoices paid
    late and average days late over the last RECENT days (lifetime values kept for customers with no
    recent record), number of past invoices with a known outcome, and invoice size.

    Behaviour is measured over a recent window because lifetime averages hide deterioration: two
    years of prompt payment outweigh five months of late payment."""
    day = lambda s: s.values.astype("datetime64[D]").astype("float")
    at = pd.Series(day(times.reindex(inv.index)), index=inv.index)
    rate = lambda late, k: late[k].sum() / k.sum() if k.any() else np.nan
    days = lambda paid, due, k: np.mean(paid[k] - due[k]) if k.any() else np.nan
    rows = {}
    for _, g in inv.groupby("customer_id"):
        issued, due = day(g.invoice_date), day(g.due_date)
        paid = np.where(g.paid_date.isna(), np.nan, day(g.paid_date.fillna(g.due_date)))
        amount, december = g.amount.values, (g.invoice_date.dt.month == 12).values
        for i, idx in enumerate(g.index):
            t = at[idx]
            prior = issued < t
            paid_known = prior & (paid < t)
            late_known = (paid_known & (paid - due > LATE)) | (prior & ~(paid < t) & (t - due > LATE))
            known = paid_known | late_known
            recent = issued >= t - RECENT
            rows[idx] = [rate(late_known, known & recent), days(paid, due, paid_known & recent), known.sum(),
                         np.log(amount[i]), amount[i] / np.median(amount[prior]) if prior.any() else 1.0,
                         float(december[i]), rate(late_known, known), days(paid, due, paid_known)]
    return pd.DataFrame.from_dict(rows, orient="index", columns=FEATURES + ["late_rate_all", "mean_days_late_all"]
                                  ).reindex(inv.index)


def label(inv, as_of=CUTOFF):
    """1 if the invoice was paid more than LATE days after its due date or not at all, as known at `as_of`;
    NaN while the outcome is still open."""
    days_late = (inv.paid_date - inv.due_date).dt.days
    unpaid_late = inv.paid_date.isna() & ((as_of - inv.due_date).dt.days > LATE)
    y = pd.Series(np.nan, index=inv.index)
    y[days_late.notna()] = (days_late[days_late.notna()] > LATE).astype(float)
    y[unpaid_late] = 1.0
    return y


def fill(X, prior_rate):
    """Model inputs: recent behaviour, else lifetime behaviour, else the average late rate."""
    X = X.fillna({"late_rate": X.late_rate_all, "mean_days_late": X.mean_days_late_all})
    return X.fillna({"late_rate": prior_rate, "mean_days_late": 0.0})[FEATURES]


def fit(X, y):
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    return model.fit(X, y)


def evaluate(inv):
    """Fit on TRAIN invoices, score TEST invoices (time-based split, no look-ahead)."""
    X = history_features(inv, inv.invoice_date)
    y = label(inv)
    tr = inv.invoice_date.between(*TRAIN) & y.notna()
    te = inv.invoice_date.between(*TEST) & y.notna()
    prior = y[tr].mean()
    model = fit(fill(X[tr], prior), y[tr])
    p = model.predict_proba(fill(X[te], prior))[:, 1]
    baseline = fill(X[te], prior).late_rate  # the customer's own track record, nothing else
    deciles = pd.qcut(p, 10, labels=False, duplicates="drop")
    calibration = pd.DataFrame({"predicted": p, "actual": y[te].values}).groupby(deciles).mean()
    return {"auc": roc_auc_score(y[te], p), "auc_baseline": roc_auc_score(y[te], baseline),
            "brier": brier_score_loss(y[te], p), "late_share": y[te].mean(), "n_train": int(tr.sum()),
            "n_test": int(te.sum()), "calibration": calibration, "model": model, "prior": prior,
            "coefficients": pd.Series(model[-1].coef_[0], index=FEATURES)}


def band(p):
    return pd.cut(p, [b[0] for b in BANDS] + [BANDS[-1][1]], labels=[b[2] for b in BANDS], right=False)


def forecast(inv, ev):
    """Expected collections from the invoices open at the cut-off, per 30-day window.

    Each open invoice gets a late-payment probability (features as known at the cut-off) and a risk
    band. For each band, the history of how many days after the due date invoices were paid gives a
    distribution F. An invoice already d days past due that is still unpaid is paid between day d+a
    and d+b with probability (F(d+b) - F(d+a)) / (1 - F(d)).
    """
    o = open_at(inv)
    X = fill(history_features(inv, pd.Series(CUTOFF, index=inv.index)).loc[o.index], ev["prior"])
    o["p_late"] = ev["model"].predict_proba(X)[:, 1]
    o["band"] = band(o.p_late)

    hist = inv[inv.invoice_date <= TRAIN[1]]
    hist_p = ev["model"].predict_proba(fill(history_features(hist, hist.invoice_date), ev["prior"]))[:, 1]
    days_late = (hist.paid_date - hist.due_date).dt.days.fillna(np.inf).values  # never paid = infinite
    dist = {name: np.sort(days_late[band(hist_p) == name]) for _, _, name in BANDS}
    pooled = np.sort(days_late)
    cdf = lambda d, x: np.searchsorted(d, x, side="right") / len(d)

    for lo, hi, name in WINDOWS:
        probs = []
        for d0, b in zip(o.days_past_due, o.band):
            d = dist[b] if len(dist[b]) and 1 - cdf(dist[b], d0) > 1e-9 else pooled
            survive = 1 - cdf(d, d0)
            probs.append((cdf(d, d0 + hi) - cdf(d, d0 + lo)) / survive if survive > 1e-9 else 0.0)
        o[name] = o.amount * np.array(probs)
    return o


def customer_risk(o):
    """Open balance by customer, ranked by the amount expected to be paid late."""
    names = [w[2] for w in WINDOWS]
    g = o.assign(at_risk=o.amount * o.p_late, overdue=o.amount.where(o.days_past_due > 0, 0),
                 within_90=o[names].sum(axis=1)).groupby("customer_id")
    t = g.agg(open=("amount", "sum"), overdue=("overdue", "sum"), at_risk=("at_risk", "sum"),
              within_90=("within_90", "sum"), invoices=("amount", "size"))
    t["chance_late"] = t.at_risk / t.open
    return t.sort_values("at_risk", ascending=False)


def backtest(o, later):
    """Forecast vs what was actually collected, plus a contractual forecast that assumes every
    invoice is paid on its due date (overdue ones straight away)."""
    actual_paid = o[["invoice_id"]].merge(later, on="invoice_id", how="left").paid_date.values
    rows = []
    for lo, hi, name in WINDOWS:
        start, end = CUTOFF + pd.Timedelta(days=lo), CUTOFF + pd.Timedelta(days=hi)
        in_window = lambda dates: (dates > start) & (dates <= end)
        contractual = o.due_date.clip(lower=CUTOFF + pd.Timedelta(days=1))
        rows.append({"window": name, "Model forecast": o[name].sum(),
                     "Contractual (due dates)": o.amount[in_window(contractual)].sum(),
                     "Actual": o.amount[in_window(pd.Series(actual_paid, index=o.index))].sum()})
    return pd.DataFrame(rows).set_index("window")


def run():
    inv, later = load()
    ev = evaluate(inv)
    o = forecast(inv, ev)
    months = pd.date_range("2024-06-30", CUTOFF, freq="ME")
    return {"invoices": inv, "evaluation": ev, "open": o, "ageing": ageing(inv), "dso": dso(inv),
            "customers": customer_risk(o),
            "dso_trend": pd.Series([dso(inv, m) for m in months], index=months), "backtest": backtest(o, later)}


if __name__ == "__main__":
    pd.options.display.float_format = "{:,.2f}".format
    r = run()
    ev = r["evaluation"]
    print(f"Open receivables €{r['open'].amount.sum():,.0f}; DSO {r['dso']:.0f} days")
    print(r["ageing"][BUCKETS].sum().round(0), "\n")
    print(f"Model AUC {ev['auc']:.3f} vs customer track record alone {ev['auc_baseline']:.3f}; "
          f"Brier {ev['brier']:.3f}; late share {ev['late_share']:.1%}; train {ev['n_train']}, test {ev['n_test']}")
    print(ev["coefficients"].round(2), "\n")
    print(ev["calibration"].round(3), "\n")
    print(r["open"].groupby("band", observed=False).amount.agg(["count", "sum"]), "\n")
    print(r["backtest"].round(0))
