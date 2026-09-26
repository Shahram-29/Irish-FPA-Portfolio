"""Run from this folder:  py -m unittest -v"""
import unittest

import pandas as pd

from pipeline import check, load, payroll_bridge, pnl, prepare, prsi_rate, revenue_bridge, run

AUG = pd.Period("2026-08", "M")


class BridgesByHand(unittest.TestCase):

    def test_revenue_bridge(self):
        # Budget: 100 seats at $10 at 1.25 $/EUR = EUR 800. Actual: 110 seats at $11 at 1.10 = EUR 1,100.
        # Volume 10 x 10 / 1.25 = 80; price 110 x 1 / 1.25 = 88; FX 1,210 x (1/1.10 - 1/1.25) = 132.
        row = {"line": "Revenue", "period": AUG, "currency": "USD"}
        budget = pd.DataFrame([{**row, "units": 100, "amount": -1000, "rate": 1.25}])
        actual = pd.DataFrame([{**row, "units": 110, "amount": -1210, "rate": 1.10}])
        b = revenue_bridge(actual, budget, [AUG]).loc["USD"]
        for part, expected in {"Budget": 800, "Volume": 80, "Price": 88, "FX": 132, "Actual": 1100}.items():
            self.assertAlmostEqual(b[part], expected, places=6, msg=part)

    def test_payroll_bridge(self):
        # Budget 10 heads at EUR 5,000; actual 8 heads at EUR 5,500.
        # Headcount effect -(8 - 10) x 5,000 = +10,000; cost per head -8 x 500 = -4,000; total +6,000.
        row = {"line": "Payroll", "period": AUG, "department": "R&D"}
        budget = pd.DataFrame([{**row, "units": 10, "eur": -50_000}])
        actual = pd.DataFrame([{**row, "units": 8, "eur": -44_000}])
        p = payroll_bridge(actual, budget, [AUG]).loc["R&D"]
        self.assertEqual((p["Headcount effect"], p["Cost per head effect"], p["Variance"]), (10_000, -4_000, 6_000))


class SampleCompany(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.res = run("2026-08")

    def test_bridge_explains_the_whole_revenue_variance(self):
        b = self.res["revenue_bridge"]
        self.assertAlmostEqual((b.Budget + b.Volume + b.Price + b.FX - b.Actual).abs().max(), 0, places=6)
        self.assertAlmostEqual(b.Actual.sum() - b.Budget.sum(), self.res["pnl_ytd"].loc["Revenue", "Variance"], places=6)

    def test_operating_profit_is_the_sum_of_the_lines(self):
        t = self.res["pnl_ytd"]
        lines = ["Revenue", "Cost of revenue", "Payroll", "Marketing programmes", "Software and tools", "Travel",
                 "Rent and facilities", "Professional fees"]
        self.assertAlmostEqual(t.loc[lines, "Actual"].sum(), t.loc["Operating profit", "Actual"], places=6)

    def test_forecast_starts_next_month_and_ignores_one_off_jumps(self):
        f = self.res["forecast"]
        self.assertEqual((len(f), f.index[0]), (12, pd.Period("2026-09", "M")))
        # June's USD deal is a one-off jump; extrapolating it would push September far above August.
        august = self.res["actual"].query("period == @AUG and line == 'Revenue'").eur.sum()
        self.assertLess(f.loc["2026-09", "Revenue"] / august, 1.03)

    def test_employer_prsi_rises_in_october(self):
        self.assertEqual((prsi_rate(pd.Period("2026-09", "M")), prsi_rate(pd.Period("2026-10", "M"))),
                         (0.1125, 0.1140))

    def test_commentary_reports_the_planted_problems(self):
        text = "\n".join(self.res["commentary"])
        self.assertIn("R&D: 3 heads under budget", text)
        self.assertIn("1 repeated posting removed: JE100157", text)
        self.assertIn("1 line posted to UNALLOCATED: JE100156", text)


class DataChecks(unittest.TestCase):

    def setUp(self):
        self.d = load()

    def errors(self):
        _, issues = check(self.d["gl_actuals"], self.d["chart_of_accounts"], self.d["cost_centres"], self.d["fx_rates"])
        return [name for severity, name, _ in issues if severity == "error"]

    def test_clean_apart_from_the_two_warnings(self):
        self.assertEqual(self.errors(), [])

    def test_unmapped_account_stops_the_run(self):
        self.d["gl_actuals"].loc[0, "account"] = 9999
        self.assertIn("Unmapped account", self.errors())
        with self.assertRaises(ValueError):
            prepare(self.d)

    def test_unknown_cost_centre(self):
        self.d["gl_actuals"].loc[0, "cost_centre"] = "CC999"
        self.assertIn("Unknown cost centre", self.errors())

    def test_missing_exchange_rate(self):
        self.d["fx_rates"] = self.d["fx_rates"][self.d["fx_rates"].period != AUG]
        self.assertIn("Missing exchange rate", self.errors())


if __name__ == "__main__":
    unittest.main()
