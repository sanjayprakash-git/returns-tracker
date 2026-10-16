"""Generates realistic demo data: 6 months of sales and ~300 returns. No real customer data.

Built-in patterns (so the dashboard has something to find):
- Budget models (Galaxy A06) come back more often, mostly "changed mind" / "not as described".
- Galaxy A17 has a battery-fault spike in June–July (a bad batch sold late May to early July), which settles from August.
- S25 Ultra returns are mostly change of mind: expensive phones get second thoughts.
- A handful of refunds break policy, to show the policy check working.
"""
import math
import random
from datetime import date, timedelta

from tracker import db
from tracker.policy import FAULT_REASONS, policy_warnings

START, END = date(2026, 4, 1), date(2026, 9, 30)
BAD_BATCH = (date(2026, 5, 20), date(2026, 7, 5))  # A17 units sold in this window have weak batteries
WARM_UP = timedelta(days=120)  # phones bought before April can still come back in the period

PRODUCTS = [  # model, series, price (EUR), relative sales volume, base return rate
    ("Galaxy A06", "A-series", 139, 1.3, 0.085),
    ("Galaxy A16", "A-series", 219, 1.6, 0.055),
    ("Galaxy A17", "A-series", 249, 1.2, 0.040),
    ("Galaxy A26", "A-series", 289, 1.4, 0.048),
    ("Galaxy A36", "A-series", 379, 1.2, 0.042),
    ("Galaxy A56", "A-series", 469, 1.0, 0.038),
    ("Galaxy S25 FE", "S-series", 649, 0.7, 0.060),
    ("Galaxy S25", "S-series", 899, 0.8, 0.034),
    ("Galaxy S25+", "S-series", 1099, 0.4, 0.030),
    ("Galaxy S25 Ultra", "S-series", 1399, 0.6, 0.046),
]
STAFF = [("Aoife M.", "staff"), ("Ciarán B.", "staff"), ("Priya S.", "staff"),
         ("Tomás K.", "staff"), ("Mei L.", "manager")]

BASE_REASONS = {  # default mix of return reasons
    "Changed mind": 24, "Faulty – screen": 12, "Faulty – battery": 10, "Faulty – charging port": 9,
    "Not as described": 12, "Wrong model bought": 12, "Network / connectivity issue": 11,
    "Accidental damage": 10,
}
MODEL_REASON_BOOST = {
    "Galaxy A06": {"Changed mind": 2.0, "Not as described": 2.2},
    "Galaxy S25 FE": {"Faulty – screen": 2.6},
    "Galaxy S25 Ultra": {"Changed mind": 2.8, "Faulty – battery": 0.4},
}


def _days_since_purchase(rng, reason):
    if reason == "Changed mind":
        return rng.choice(range(1, 15)) if rng.random() < 0.88 else rng.randint(15, 24)
    if reason in ("Wrong model bought", "Not as described"):
        return rng.randint(0, 7)
    if reason == "Network / connectivity issue":
        return rng.randint(1, 20)
    if reason == "Faulty – battery":
        return rng.randint(4, 35)   # battery faults show up within weeks
    return rng.randint(3, 90)       # other faults and accidental damage turn up later


def _condition(rng, reason):
    if reason == "Accidental damage":
        return "Damaged"
    if reason in ("Changed mind", "Wrong model bought"):
        return rng.choices(["Sealed / unopened", "Like new"], weights=[45, 55])[0]
    return rng.choices(["Like new", "Used – good"], weights=[35, 65])[0]


def _outcome(rng, reason, days):
    if reason == "Accidental damage":
        return "Repair"
    if reason == "Wrong model bought":
        return "Exchange"
    if reason == "Changed mind":
        return "Refund" if days <= 14 else "Exchange"
    if reason in FAULT_REASONS:
        if days <= 30:
            return rng.choices(["Refund", "Exchange", "Repair"], weights=[30, 40, 30])[0]
        return rng.choices(["Exchange", "Repair"], weights=[35, 65])[0]
    return rng.choices(["Refund", "Exchange"], weights=[55, 45])[0]


def _return_rate(model, base, day):
    if model == "Galaxy A17" and BAD_BATCH[0] <= day <= BAD_BATCH[1]:
        return base * 3.2 * 1.05  # bad battery batch
    return base * 1.05


def _reason_weights(model, day):
    weights = dict(BASE_REASONS)
    for reason, factor in MODEL_REASON_BOOST.get(model, {}).items():
        weights[reason] *= factor
    if model == "Galaxy A17" and BAD_BATCH[0] <= day <= BAD_BATCH[1]:
        weights["Faulty – battery"] *= 9
    return weights


def _poisson(rng, mean):
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def seed(conn, rng_seed: int = 42) -> None:
    rng = random.Random(rng_seed)
    conn.executemany("INSERT INTO products (model, series, price) VALUES (?, ?, ?)",
                     [(m, s, p) for m, s, p, _, _ in PRODUCTS])
    conn.executemany("INSERT INTO staff (name, role) VALUES (?, ?)", STAFF)
    product_ids = {m: i for i, m in conn.execute("SELECT id, model FROM products")}
    staff_ids = [i for (i,) in conn.execute("SELECT id FROM staff")]

    sales, returns = [], []
    day = START - WARM_UP
    while day <= END:
        footfall = 1.35 if day.weekday() >= 5 else 1.0  # busier weekends
        for model, _, _, volume, base_rate in PRODUCTS:
            units = _poisson(rng, 2.6 * volume * footfall)
            if units and day >= START:
                sales.append((day.isoformat(), product_ids[model], rng.choice(staff_ids), units))
            for _ in range(units):
                if rng.random() < _return_rate(model, base_rate, day):
                    weights = _reason_weights(model, day)
                    reason = rng.choices(list(weights), weights=list(weights.values()))[0]
                    days = _days_since_purchase(rng, reason)
                    return_day = day + timedelta(days=days)
                    if not START <= return_day <= END:
                        continue
                    outcome = _outcome(rng, reason, days)
                    if reason == "Changed mind" and days > 14 and rng.random() < 0.6:
                        outcome = "Refund"  # staff gave a refund they shouldn't have
                    flagged = bool(policy_warnings(reason, outcome, days))
                    returns.append((return_day.isoformat(), day.isoformat(), days, product_ids[model],
                                    reason, _condition(rng, reason), outcome, rng.choice(staff_ids),
                                    int(flagged), "Approved by manager" if flagged and rng.random() < 0.3 else None))
        day += timedelta(days=1)

    conn.executemany("INSERT INTO sales (sale_date, product_id, staff_id, quantity) VALUES (?, ?, ?, ?)", sales)
    conn.executemany(
        """INSERT INTO returns (return_date, purchase_date, days_since_purchase, product_id, reason,
                                condition, outcome, staff_id, out_of_policy, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", returns)
    conn.commit()


if __name__ == "__main__":
    c = db.connect()
    db.init_db(c)
    if db.is_empty(c):
        seed(c)
    print(c.execute("SELECT (SELECT SUM(quantity) FROM sales), (SELECT COUNT(*) FROM returns)").fetchone())
