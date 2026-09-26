"""Irish corporation tax, the R&D tax credit and a simplified Pillar Two top-up tax for a company's
2026 year, plus a three-year projection linking the tax charge, cash tax and balance sheet.

    py ct_model.py
"""
import json
from pathlib import Path

import pandas as pd

RULES = json.loads((Path(__file__).parent / "rules_2026.json").read_text())
CT, RD, PT, P2 = RULES["corporation_tax"], RULES["rd_credit"], RULES["preliminary_tax"], RULES["pillar_two"]

# A fictional Irish subsidiary of a large multinational group, for the examples and the app.
EXAMPLE = {"trading_profit": 40_000_000, "non_trading_income": 1_000_000, "rd_spend": 8_000_000,
           "payroll": 30_000_000, "tangible_assets": 60_000_000, "in_scope_group": True}


def corporation_tax(trading_profit, non_trading_income):
    return trading_profit * CT["trading_rate"] + non_trading_income * CT["non_trading_rate"]


def rd_instalments(credit, threshold=RD["first_instalment_threshold"]):
    """The three annual instalments of an R&D credit claim (Tax and Duty Manual 29-02-03, 2.3.1):
    first = the greater of the threshold (or the whole credit if lower) and 50% of the credit;
    second = three-fifths of what's left; third = the rest."""
    first = max(min(threshold, credit), 0.5 * credit)
    second = (credit - first) * RD["second_instalment_share_of_balance"]
    return [first, second, credit - first - second]


def preliminary_tax(current, prior):
    """Preliminary tax instalments (month of the accounting year, amount) paying the lower of the
    current-year and prior-year bases, and the balance due with the return."""
    if prior > PT["large_company_prior_liability_over"]:
        first = min(PT["large_first_instalment"]["share_of_current"] * current,
                    PT["large_first_instalment"]["share_of_prior"] * prior)
        second = PT["large_second_instalment"]["cumulative_share_of_current"] * current - first
        paid = [(6, first), (11, max(second, 0.0))]
    else:
        s = PT["small_single_instalment"]
        paid = [(11, min(s["share_of_current"] * current, s["share_of_prior"] * prior))]
    return paid, current - sum(amount for _, amount in paid)


def pillar_two(globe_income, covered_taxes, payroll, tangible_assets, in_scope=True):
    """Simplified jurisdictional top-up tax: (15% - effective rate) x (GloBE income - substance carve-out).
    Leaves out safe harbours, deferred tax adjustments and the 2026 side-by-side rules."""
    etr = covered_taxes / globe_income
    carve_out = P2["payroll_carve_out_2026"] * payroll + P2["tangible_asset_carve_out_2026"] * tangible_assets
    excess = max(globe_income - carve_out, 0.0)
    top_up_rate = max(P2["minimum_rate"] - etr, 0.0) if in_scope else 0.0
    return {"etr": etr, "carve_out": carve_out, "excess_profit": excess, "top_up_rate": top_up_rate,
            "top_up_tax": top_up_rate * excess}


def year(trading_profit, non_trading_income, rd_spend, payroll, tangible_assets, in_scope_group=True,
         prior_liability=None):
    """One year's tax position. Profit is before the R&D credit, and is assumed equal to taxable profit
    (no adjustments or deferred tax). The R&D credit isn't taxable."""
    profit = trading_profit + non_trading_income
    ct = corporation_tax(trading_profit, non_trading_income)
    credit = RD["rate"] * rd_spend
    # Pillar Two: the payable R&D credit is a qualified refundable tax credit, so it counts as income
    # and doesn't reduce covered taxes. The counterfactual treats it as an ordinary credit.
    qualified = pillar_two(profit + credit, ct, payroll, tangible_assets, in_scope_group)
    ordinary = pillar_two(profit, ct - credit, payroll, tangible_assets, in_scope_group)
    instalments, balance = preliminary_tax(ct, ct if prior_liability is None else prior_liability)
    return {"profit": profit, "corporation_tax": ct, "rd_credit": credit, "rd_instalments": rd_instalments(credit),
            "net_tax_after_credit": ct - credit, "rate_after_credit": (ct - credit) / profit,
            "pillar_two": qualified, "pillar_two_if_ordinary_credit": ordinary,
            "preliminary_tax": instalments, "balance_with_return": balance}


def projection(start=EXAMPLE, years=(2026, 2027, 2028), profit_growth=0.08, rd_growth=0.10):
    """Three years linking the P&L tax charge, cash tax paid in each calendar year and the balance sheet.

    Cash timing for a 31 December year-end: preliminary tax in June and November of the year; the balance
    in September of the next year, with the return; each R&D instalment is received with a return
    (claim year + 1, + 2, + 3); domestic top-up tax paid about 15 months after the year-end (year + 2).
    The R&D credit is shown above the line (reducing R&D costs), a common Irish presentation for a
    credit that is paid regardless of tax profits, so the tax charge is corporation tax plus top-up tax.
    """
    rows, prior = [], None
    results = {}
    for i, y in enumerate(years):
        g = (1 + profit_growth) ** i
        r = year(start["trading_profit"] * g, start["non_trading_income"] * g, start["rd_spend"] * (1 + rd_growth) ** i,
                 start["payroll"] * g, start["tangible_assets"], start["in_scope_group"], prior)
        results[y], prior = r, r["corporation_tax"]
    for y in years:
        cash_ct = sum(a for _, a in results[y]["preliminary_tax"]) + \
            (results[y - 1]["balance_with_return"] if y - 1 in results else 0.0)
        top_up_paid = results[y - 2]["pillar_two"]["top_up_tax"] if y - 2 in results else 0.0
        rd_received = sum(results[y - k]["rd_instalments"][k - 1] for k in (1, 2, 3) if y - k in results)
        r = results[y]
        rows.append({"year": y, "Profit before tax (incl. R&D credit)": r["profit"] + r["rd_credit"],
                     "Tax charge": r["corporation_tax"] + r["pillar_two"]["top_up_tax"],
                     "Corporation tax paid": cash_ct, "Top-up tax paid": top_up_paid,
                     "R&D credit received": rd_received,
                     "Net cash tax": cash_ct + top_up_paid - rd_received})
    t = pd.DataFrame(rows).set_index("year")
    t["Effective tax rate (P&L)"] = t["Tax charge"] / t["Profit before tax (incl. R&D credit)"]
    # Balance sheet at each year-end: tax owed, and R&D credit claimed but not yet received.
    charge, paid = t["Tax charge"].cumsum(), (t["Corporation tax paid"] + t["Top-up tax paid"]).cumsum()
    t["Tax payable at year-end"] = charge - paid
    claimed = pd.Series({y: results[y]["rd_credit"] for y in years}).cumsum()
    t["R&D credit receivable at year-end"] = claimed - t["R&D credit received"].cumsum()
    return t, results


if __name__ == "__main__":
    r = year(**EXAMPLE)
    p2, alt = r["pillar_two"], r["pillar_two_if_ordinary_credit"]
    print(f"Corporation tax €{r['corporation_tax']:,.0f}; R&D credit €{r['rd_credit']:,.0f} "
          f"paid as {', '.join(f'€{x:,.0f}' for x in r['rd_instalments'])}")
    print(f"Net tax after credit €{r['net_tax_after_credit']:,.0f} = {r['rate_after_credit']:.2%} of profit")
    print(f"Pillar Two, credit as qualified refundable: ETR {p2['etr']:.2%}, top-up €{p2['top_up_tax']:,.0f}")
    print(f"Pillar Two, credit as ordinary credit:      ETR {alt['etr']:.2%}, top-up €{alt['top_up_tax']:,.0f}")
    print("Preliminary tax:", [(m, round(a)) for m, a in r["preliminary_tax"]], "balance", round(r["balance_with_return"]))
    pd.options.display.float_format = "{:,.0f}".format
    print(projection()[0].T)
