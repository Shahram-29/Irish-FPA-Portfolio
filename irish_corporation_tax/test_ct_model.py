"""Run from this folder:  py -m unittest -v"""
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from ct_model import EXAMPLE, corporation_tax, pillar_two, preliminary_tax, projection, rd_instalments, year


class RevenueRdExamples(unittest.TestCase):
    """Tax and Duty Manual 29-02-03 (April 2026), examples 4 to 7."""

    def test_example_4_small_claim_2025(self):
        self.assertEqual(rd_instalments(65_000, threshold=75_000), [65_000, 0, 0])

    def test_example_5_larger_claim_2025(self):
        self.assertEqual(rd_instalments(100_000, threshold=75_000), [75_000, 15_000, 10_000])

    def test_example_6_small_claim_2026(self):
        self.assertEqual(rd_instalments(80_000), [80_000, 0, 0])

    def test_example_7_larger_claim_2026(self):
        self.assertEqual(rd_instalments(150_000), [87_500, 37_500, 25_000])

    def test_half_up_front_for_big_claims(self):
        self.assertEqual(rd_instalments(2_800_000), [1_400_000, 840_000, 560_000])


class ByHand(unittest.TestCase):

    def test_corporation_tax(self):
        # 12.5% of 40m + 25% of 1m
        self.assertEqual(corporation_tax(40_000_000, 1_000_000), 5_250_000)

    def test_preliminary_tax_large_company(self):
        # Prior liability 5m > 200k, so large. First: lower of 45% x 6m = 2.7m and 50% x 5m = 2.5m.
        # Second brings the total to 90% x 6m = 5.4m, so 2.9m. Balance 0.6m with the return.
        paid, balance = preliminary_tax(6_000_000, 5_000_000)
        self.assertEqual(paid, [(6, 2_500_000), (11, 2_900_000)])
        self.assertAlmostEqual(balance, 600_000)

    def test_preliminary_tax_small_company(self):
        # Prior liability 150k: one instalment in month 11, the lower of 90% x 180k and 100% x 150k.
        self.assertEqual(preliminary_tax(180_000, 150_000), ([(11, 150_000)], 30_000))

    def test_pillar_two(self):
        # GloBE income 43.8m, covered taxes 5.25m: ETR 11.99%, top-up rate 3.01%.
        # Carve-out 9.4% x 30m + 7.4% x 60m = 7.26m; excess profit 36.54m.
        p = pillar_two(43_800_000, 5_250_000, 30_000_000, 60_000_000)
        self.assertAlmostEqual(p["carve_out"], 7_260_000)
        self.assertAlmostEqual(p["top_up_tax"], (0.15 - 5_250_000 / 43_800_000) * 36_540_000)

    def test_no_top_up_outside_scope_or_above_15_percent(self):
        self.assertEqual(pillar_two(10_000_000, 1_000_000, 0, 0, in_scope=False)["top_up_tax"], 0)
        self.assertEqual(pillar_two(10_000_000, 1_600_000, 0, 0)["top_up_tax"], 0)

    def test_refundable_credit_means_less_top_up(self):
        r = year(**EXAMPLE)
        self.assertLess(r["pillar_two"]["top_up_tax"], r["pillar_two_if_ordinary_credit"]["top_up_tax"])


class Projection(unittest.TestCase):

    def test_balance_sheet_rolls_forward(self):
        t, results = projection()
        # Tax payable at the end of 2026 = the balance due with the return + that year's top-up tax.
        r = results[2026]
        self.assertAlmostEqual(t.loc[2026, "Tax payable at year-end"],
                               r["balance_with_return"] + r["pillar_two"]["top_up_tax"])
        # Nothing received in the claim year; the first instalment arrives the year after.
        self.assertEqual(t.loc[2026, "R&D credit received"], 0)
        self.assertEqual(t.loc[2027, "R&D credit received"], r["rd_instalments"][0])

    def test_app_renders(self):
        at = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=120).run()
        self.assertFalse(at.exception)


if __name__ == "__main__":
    unittest.main()
