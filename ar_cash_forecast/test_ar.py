"""Run from this folder:  py -m unittest -v"""
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from ar import BUCKETS, CUTOFF, WINDOWS, ageing, dso, history_features, label, open_at, run


def invoice(customer, issued, due, amount, paid=None):
    return {"customer_id": customer, "invoice_date": pd.Timestamp(issued), "due_date": pd.Timestamp(due),
            "amount": amount, "paid_date": pd.Timestamp(paid) if paid else pd.NaT}


class ByHand(unittest.TestCase):

    def setUp(self):
        self.inv = pd.DataFrame([
            invoice(1, "2026-08-20", "2026-09-19", 100),                 # not yet due
            invoice(1, "2026-07-01", "2026-07-31", 200),                 # 31 days past due
            invoice(2, "2026-04-01", "2026-05-01", 300),                 # 122 days past due
            invoice(2, "2026-06-01", "2026-07-01", 400, "2026-07-20"),   # paid, so not open
        ])

    def test_ageing_buckets(self):
        t = ageing(self.inv)
        self.assertEqual((t.loc[1, "Not yet due"], t.loc[1, "31–60 days"], t.loc[2, "Over 90 days"]), (100, 200, 300))
        self.assertEqual(t.Total.sum(), 600)

    def test_dso(self):
        # Open 600. The 90 days to 31 Aug start on 2 June, so the 1 June invoice falls outside:
        # sales 100 + 200 = 300, and DSO = 600 / 300 x 90 = 180.
        self.assertAlmostEqual(dso(self.inv), 180)

    def test_labels_use_only_what_is_known_at_the_cutoff(self):
        y = label(self.inv)
        # Not yet due: unknown. 31 days past due and unpaid: late. 122 days: late. Paid 19 days late: on time.
        self.assertTrue(np.isnan(y[0]))
        self.assertEqual(list(y[1:]), [1.0, 1.0, 0.0])

    def test_history_features_do_not_look_ahead(self):
        # Customer 2's June invoice: the April invoice was 31 days past due on 1 June, so known late.
        X = history_features(self.inv, self.inv.invoice_date)
        self.assertEqual((X.loc[3, "late_rate"], X.loc[3, "history"]), (1.0, 1.0))
        self.assertTrue(np.isnan(X.loc[2, "late_rate"]))  # nothing known before its first invoice


class RecentBehaviour(unittest.TestCase):

    def test_recent_lateness_is_not_hidden_by_a_good_past(self):
        # 20 invoices paid on time in 2024-25, then 4 paid 45 days late in 2026.
        rows = [invoice(1, f"{2024 + m // 12}-{m % 12 + 1:02d}-01", f"{2024 + m // 12}-{m % 12 + 1:02d}-28", 100,
                        f"{2024 + m // 12}-{m % 12 + 1:02d}-28") for m in range(20)]
        rows += [invoice(1, f"2026-0{m}-01", f"2026-0{m}-28", 100, f"2026-0{m + 2}-12") for m in range(1, 5)]
        inv = pd.DataFrame(rows)
        X = history_features(inv, pd.Series(CUTOFF, index=inv.index))
        self.assertEqual(X.late_rate.iloc[0], 1.0)                         # last 180 days: all 4 late
        self.assertAlmostEqual(X.late_rate_all.iloc[0], 4 / 24)             # lifetime: diluted to 17%


class SampleLedger(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.r = run()

    def test_ageing_matches_open_invoices(self):
        self.assertAlmostEqual(self.r["ageing"][BUCKETS].values.sum(), open_at(self.r["invoices"]).amount.sum(), 2)

    def test_forecast_never_exceeds_what_is_owed(self):
        o = self.r["open"]
        expected = o[[w[2] for w in WINDOWS]].sum(axis=1)
        self.assertTrue(((expected >= -1e-9) & (expected <= o.amount + 1e-6)).all())

    def test_model_beats_chance_and_forecast_beats_due_dates(self):
        self.assertGreater(self.r["evaluation"]["auc"], 0.75)
        bt = self.r["backtest"]
        model_error = (bt["Model forecast"] - bt.Actual).abs().sum()
        contractual_error = (bt["Contractual (due dates)"] - bt.Actual).abs().sum()
        self.assertLess(model_error, contractual_error)

    def test_app_renders(self):
        at = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=300).run()
        self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main()
