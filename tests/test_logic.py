"""Tests for the policy rules and dashboard maths. Run with: python -m unittest"""
import sqlite3
import unittest

import pandas as pd

from tracker import analytics, db
from tracker.policy import policy_warnings, responsibility, suggests_supplier_claim
from tracker.seed import seed


class PolicyTests(unittest.TestCase):
    def test_free_re_repair_within_90_days_is_allowed(self):
        self.assertEqual(policy_warnings("Repair", "Touch not working / ghost touch", "Re-repair (free)", 90), [])

    def test_free_re_repair_after_90_days_is_flagged(self):
        self.assertEqual(len(policy_warnings("Repair", "Touch not working / ghost touch", "Re-repair (free)", 91)), 1)

    def test_customer_damage_is_only_ok_when_declined(self):
        self.assertEqual(policy_warnings("Repair", "Customer damage after repair", "Declined", 5), [])
        self.assertEqual(len(policy_warnings("Repair", "Customer damage after repair", "Re-repair (free)", 5)), 1)

    def test_change_of_mind_refund_after_14_days_is_flagged(self):
        self.assertEqual(policy_warnings("Accessory", "Changed mind", "Refund", 14), [])
        self.assertEqual(len(policy_warnings("Accessory", "Changed mind", "Refund", 15)), 1)
        self.assertEqual(policy_warnings("Accessory", "Changed mind", "Store credit", 30), [])

    def test_accessory_warranty_depends_on_product(self):
        self.assertEqual(policy_warnings("Accessory", "Faulty", "Exchange", 30, warranty_days=30), [])
        self.assertEqual(len(policy_warnings("Accessory", "Faulty", "Exchange", 31, warranty_days=30)), 1)
        self.assertEqual(policy_warnings("Accessory", "Faulty", "Exchange", 60, warranty_days=90), [])

    def test_faulty_new_phone_refund_after_30_days_is_flagged(self):
        self.assertEqual(len(policy_warnings("New phone", "Faulty", "Refund", 31)), 1)

    def test_supplier_claim_suggested_for_part_faults_only(self):
        self.assertTrue(suggests_supplier_claim("Repair", "Part dead on arrival"))
        self.assertFalse(suggests_supplier_claim("Repair", "Fitting issue (workmanship)"))
        self.assertFalse(suggests_supplier_claim("Accessory", "Changed mind"))

    def test_responsibility(self):
        self.assertEqual(responsibility("Fitting issue (workmanship)"), "Workmanship")
        self.assertEqual(responsibility("Lines or dead pixels on display"), "Part fault")
        self.assertEqual(responsibility("Changed mind"), "Sale-related")


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.returns = pd.DataFrame({
            "return_date": pd.to_datetime(["2026-05-02", "2026-05-10", "2026-06-01"]),
            "category": ["Repair", "Repair", "Accessory"], "brand": ["Apple", "Apple", "Universal"],
            "name": ["Screen", "Screen", "USB-C cable"], "part_grade": ["Standard aftermarket", "Genuine", None],
            "item": ["iPhone 13 · Screen · Standard aftermarket", "iPhone 13 · Screen · Genuine", "USB-C cable"],
            "supplier": ["Supplier C", "Supplier A", "Supplier D"],
            "reason": ["Touch not working / ghost touch", "Fitting issue (workmanship)", "Faulty"],
            "outcome": ["Re-repair (free)", "Re-repair (free)", "Exchange"],
            "price": [109.0, 279.0, 12.0], "cost": [30.0, 125.0, 2.5],
            "supplier_claim": [True, False, True], "out_of_policy": [False, False, False],
        })
        self.returns["return_cost"] = db.return_cost(self.returns)
        self.sales = pd.DataFrame({
            "sale_date": pd.to_datetime(["2026-05-01"] * 3),
            "category": ["Repair", "Repair", "Accessory"], "brand": ["Apple", "Apple", "Universal"],
            "name": ["Screen", "Screen", "USB-C cable"], "part_grade": ["Standard aftermarket", "Genuine", None],
            "item": ["iPhone 13 · Screen · Standard aftermarket", "iPhone 13 · Screen · Genuine", "USB-C cable"],
            "quantity": [10, 40, 100],
        })

    def test_comeback_rate_by_part_and_grade(self):
        m = analytics.part_grade_matrix(self.returns, self.sales).set_index("part_grade")
        self.assertAlmostEqual(m.loc["Standard aftermarket", "rate"], 1 / 10)
        self.assertAlmostEqual(m.loc["Genuine", "rate"], 1 / 40)

    def test_cost_of_returns(self):
        # re-repairs: part cost + €15 labour each; exchange: replacement cost
        self.assertAlmostEqual(analytics.cost_of_returns(self.returns), (30 + 15) + (125 + 15) + 2.5)

    def test_supplier_recoverable_counts_claims_only(self):
        self.assertAlmostEqual(analytics.supplier_recoverable(self.returns), 30 + 2.5)


class SeedTests(unittest.TestCase):
    def test_seed_is_mostly_repair_comebacks(self):
        conn = sqlite3.connect(":memory:")
        db.init_db(conn)
        seed(conn)
        total, repairs, bad = conn.execute(
            """SELECT COUNT(*), SUM(i.category = 'Repair'), SUM(r.days_since_purchase < 0)
               FROM returns r JOIN items i ON i.id = r.item_id""").fetchone()
        self.assertTrue(220 <= total <= 340, total)
        self.assertGreater(repairs / total, 0.6)
        self.assertEqual(bad, 0)


if __name__ == "__main__":
    unittest.main()
