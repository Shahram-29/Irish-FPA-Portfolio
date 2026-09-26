"""Run from this folder:  py -m unittest -v"""
import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from metrics import breakeven, connect, deferred_revenue, load, project, runway, unit_economics


class SampleCompany(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.con = connect()
        cls.m = load(cls.con)

    def test_mrr_bridge_adds_up(self):
        b = self.m["bridge"]
        moves = b.opening + b.new + b.expansion + b.contraction + b.churn
        self.assertAlmostEqual((moves - b.closing).abs().max(), 0, places=6)
        self.assertTrue((b.opening.iloc[1:].values == b.closing.iloc[:-1].values).all())

    def test_sql_matches_a_plain_sum(self):
        # The SQL bridge's closing MRR must equal a simple total of the subscriptions table.
        subs = self.con.execute("SELECT * FROM subscriptions").df()
        totals = subs.groupby("month").mrr.sum()
        self.assertAlmostEqual((totals - self.m["bridge"].closing).abs().max(), 0, places=6)

    def test_cohorts_start_at_100_percent(self):
        self.assertTrue((self.m["cohorts"][0] == 1).all())

    def test_gross_retention_never_exceeds_net_or_100_percent(self):
        r = self.m["retention"]
        self.assertTrue((r.grr <= r.nrr + 1e-12).all() and (r.grr <= 1).all())

    def test_deferred_revenue_never_negative(self):
        self.assertGreaterEqual(self.m["deferred"].deferred_revenue.min(), 0)

    def test_app_renders(self):
        at = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=120).run()
        self.assertFalse(at.exception)


class ByHand(unittest.TestCase):

    def test_annual_contract_unwinds_over_the_year(self):
        # One annual customer at EUR 100 a month from January: billed EUR 1,200 in January,
        # EUR 100 recognised each month, so deferred revenue is 1,100 after January and 0 after December.
        months = pd.date_range("2026-01-01", periods=12, freq="MS")
        subs = pd.DataFrame({"customer_id": 1, "month": months, "mrr": 100.0})
        customers = pd.DataFrame({"customer_id": [1], "signup_month": [months[0]], "billing": ["annual"]})
        d = deferred_revenue(subs, customers)
        self.assertEqual((d.billings.iloc[0], d.deferred_revenue.iloc[0], d.deferred_revenue.iloc[-1]), (1200, 1100, 0))

    def test_unit_economics(self):
        # 100 customers at EUR 500 MRR; 2 of 100 churn each month; 10 new customers for EUR 80,000 spend.
        # CAC 8,000; LTV 500 x 0.78 / 0.02 = 19,500; payback 8,000 / 390 = 20.5 months.
        idx = pd.date_range("2026-01-01", periods=3, freq="MS")
        bridge = pd.DataFrame({"closing": 50_000.0, "closing_customers": 100, "new_customers": 10,
                               "churned_customers": 2, "opening_customers": 100, "opening": 50_000.0,
                               "expansion": 0.0, "contraction": 0.0}, index=idx)
        u = unit_economics(bridge, pd.Series(80_000.0, index=idx), window=1, churn_window=3)
        self.assertEqual((u["CAC"], round(u["LTV"]), round(u["CAC payback (months)"], 2)), (8_000, 19_500, 20.51))

    def test_projection_with_nothing_changing(self):
        start = {"Customers": 100, "ARPA": 500.0, "New customers per month": 0, "Monthly logo churn": 0.0,
                 "Monthly net expansion": 0.0, "CAC": 5_000.0}
        p = project(start, months=12, cash=100_000, fixed_costs=50_000, fixed_cost_growth=0)
        # MRR stays 50,000; gross profit 39,000 - other costs 50,000 = -11,000 a month.
        self.assertTrue((p.MRR == 50_000).all())
        self.assertAlmostEqual(p["cash flow"].iloc[0], -11_000)
        self.assertEqual((runway(p), breakeven(p)), (10, None))


if __name__ == "__main__":
    unittest.main()
