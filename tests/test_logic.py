"""Tests for the policy rules and dashboard maths. Run with: python -m unittest"""
import sqlite3
import unittest

import pandas as pd

from tracker import analytics, db
from tracker.policy import policy_warnings
from tracker.seed import seed


class PolicyTests(unittest.TestCase):
    def test_change_of_mind_refund_within_14_days_is_allowed(self):
        self.assertEqual(policy_warnings("Changed mind", "Refund", 14), [])

    def test_change_of_mind_refund_after_14_days_is_flagged(self):
        self.assertEqual(len(policy_warnings("Changed mind", "Refund", 15)), 1)

    def test_change_of_mind_exchange_after_14_days_is_allowed(self):
        self.assertEqual(policy_warnings("Changed mind", "Exchange", 40), [])

    def test_fault_refund_after_30_days_is_flagged(self):
        self.assertEqual(policy_warnings("Faulty – screen", "Refund", 30), [])
        self.assertEqual(len(policy_warnings("Faulty – screen", "Refund", 31)), 1)

    def test_accidental_damage_only_allows_repair(self):
        self.assertEqual(policy_warnings("Accidental damage", "Repair", 5), [])
        self.assertEqual(len(policy_warnings("Accidental damage", "Exchange", 5)), 1)


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.returns = pd.DataFrame({
            "return_date": pd.to_datetime(["2026-05-02", "2026-05-10", "2026-06-01"]),
            "model": ["A", "A", "B"], "series": ["A-series"] * 3, "price": [100.0, 100.0, 900.0],
            "reason": ["Changed mind", "Faulty – battery", "Changed mind"],
            "outcome": ["Refund", "Repair", "Refund"], "out_of_policy": [False, False, True],
        })
        self.sales = pd.DataFrame({
            "sale_date": pd.to_datetime(["2026-05-01", "2026-05-01", "2026-06-01"]),
            "model": ["A", "B", "B"], "series": ["A-series"] * 3, "price": [100.0, 900.0, 900.0],
            "quantity": [10, 20, 30],
        })

    def test_return_rate_uses_units_sold_per_model(self):
        rates = analytics.rate_by_model(self.returns, self.sales).set_index("model")
        self.assertAlmostEqual(rates.loc["A", "return_rate"], 2 / 10)
        self.assertAlmostEqual(rates.loc["B", "return_rate"], 1 / 50)

    def test_refunded_value_counts_refunds_only(self):
        self.assertEqual(analytics.refunded_value(self.returns), 1000.0)

    def test_insights_name_highest_rate_model(self):
        self.assertIn("**A**", analytics.insights(self.returns, self.sales)[0])


class SeedTests(unittest.TestCase):
    def test_seed_produces_about_300_returns_with_no_negative_days(self):
        conn = sqlite3.connect(":memory:")
        db.init_db(conn)
        seed(conn)
        n, bad = conn.execute("SELECT COUNT(*), SUM(days_since_purchase < 0) FROM returns").fetchone()
        self.assertTrue(250 <= n <= 350, n)
        self.assertEqual(bad, 0)


if __name__ == "__main__":
    unittest.main()
