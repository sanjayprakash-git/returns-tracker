"""Tests for the policy rules and dashboard maths. Run with: python -m unittest"""
import sqlite3
import unittest

import pandas as pd

from tracker import analytics, db, stock
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


class StockTests(unittest.TestCase):
    """The stock ledger keeps shelf, faulty bin and supplier returns correct."""

    def setUp(self):
        from datetime import date
        self.d = date(2026, 7, 10)
        self.conn = sqlite3.connect(":memory:")
        db.init_db(self.conn)
        self.conn.execute("INSERT INTO staff (name, role) VALUES ('Tester', 'sales')")
        self.conn.execute("""INSERT INTO items (category, subcategory, brand, name, supplier, warranty_days, price, cost)
                             VALUES ('Accessory', 'Audio', 'Universal', 'Wireless earbuds', 'Atlantic', 90, 45, 14)""")
        stock.receive_delivery(self.conn, self.d, 1, 10, 0, 1)

    def test_faulty_swap_moves_one_to_bin_and_one_off_shelf(self):
        db.add_return(self.conn, return_date=self.d, purchase_date=self.d, item_id=1, reason="Faulty",
                      outcome="Exchange", staff_id=1, supplier_claim=True, out_of_policy=False)
        self.assertEqual(stock.levels(self.conn, 1), {"shelf": 9, "faulty_bin": 1})

    def test_faulty_refund_only_adds_to_bin(self):
        db.add_return(self.conn, return_date=self.d, purchase_date=self.d, item_id=1, reason="Faulty",
                      outcome="Refund", staff_id=1, supplier_claim=True, out_of_policy=False)
        self.assertEqual(stock.levels(self.conn, 1), {"shelf": 10, "faulty_bin": 1})

    def test_damaged_delivery_goes_to_bin(self):
        stock.receive_delivery(self.conn, self.d, 1, 8, 2, 1, problem="Box crushed / packaging damaged")
        self.assertEqual(stock.levels(self.conn, 1), {"shelf": 18, "faulty_bin": 2})

    def test_supplier_return_and_replacement(self):
        stock.found_faulty(self.conn, self.d, 1, 3, 1)
        [claim] = stock.send_to_supplier(self.conn, self.d, {1: 3}, 1, "RMA-1")
        self.assertEqual(stock.levels(self.conn, 1), {"shelf": 7, "faulty_bin": 0, "with_supplier": 3})
        stock.close_claim(self.conn, claim, "Replacement stock", self.d, 1, replacement_qty=3)
        self.assertEqual(stock.levels(self.conn, 1)["shelf"], 10)
        self.assertAlmostEqual(db.claims_df(self.conn).iloc[0]["recovered"], 3 * 14)

    def test_rejected_claim_is_written_off(self):
        stock.found_faulty(self.conn, self.d, 1, 2, 1)
        [claim] = stock.send_to_supplier(self.conn, self.d, {1: 2}, 1)
        stock.close_claim(self.conn, claim, "Rejected - written off", self.d, 1)
        self.assertEqual(stock.levels(self.conn, 1), {"shelf": 8, "faulty_bin": 0, "with_supplier": 0})

    def test_stock_count_records_missing_units(self):
        variance = stock.stock_count(self.conn, self.d, 1, 7, 1)
        self.assertEqual(variance, -3)
        self.assertEqual(stock.levels(self.conn, 1)["shelf"], 7)
        moves = db.movements_df(self.conn)
        self.assertEqual(int(moves.loc[moves["to_loc"] == stock.UNEXPLAINED, "quantity"].sum()), 3)


class AuthTests(unittest.TestCase):
    def test_password_hash_round_trip(self):
        from tracker.auth import hash_password, verify_password
        h = hash_password("s3cret")
        self.assertNotIn("s3cret", h)
        self.assertTrue(verify_password("s3cret", h))
        self.assertFalse(verify_password("wrong", h))

    def test_demo_accounts_sign_in_with_roles(self):
        from tracker.auth import DEMO_LOGINS, authenticate
        conn = sqlite3.connect(":memory:")
        db.init_db(conn)
        seed(conn)
        for username, password, role in DEMO_LOGINS:
            self.assertEqual(authenticate(conn, username, password)["role"], role.lower())
        self.assertIsNone(authenticate(conn, "sanjay", "wrong-password"))


class SeedTests(unittest.TestCase):
    def test_seed_tells_the_go_live_story(self):
        conn = sqlite3.connect(":memory:")
        db.init_db(conn)
        seed(conn)
        total, repairs, bad = conn.execute(
            """SELECT COUNT(*), SUM(i.category = 'Repair'), SUM(r.days_since_purchase < 0)
               FROM returns r JOIN items i ON i.id = r.item_id""").fetchone()
        self.assertTrue(300 <= total <= 550, total)
        self.assertGreater(repairs / total, 0.4)
        self.assertEqual(bad, 0)
        levels = stock.levels_df(conn)
        self.assertEqual(int((levels[["shelf", "faulty_bin", "with_supplier"]] < 0).sum().sum()), 0)
        box = conn.execute("SELECT SUM(quantity) FROM stock_movements WHERE reason = 'Old faulty box counted at go-live'")
        self.assertGreater(box.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
