"""Generates realistic demo data for a phone repair & accessories shop. No real customer data.

Sales: 6 months of repair jobs, new phones, reconditioned phones and accessories.
Returns: ~300, mostly repair comebacks on fitted parts.

Built-in patterns (so the dashboard has something to find):
- Standard aftermarket screens come back ~5x more often than genuine screens.
- Supplier C's aftermarket batteries had a bad batch (jobs from late May to early July).
- Google Pixel screen repairs often come back with fingerprint-sensor problems.
- Sensor flex repairs (Face ID / proximity) are the trickiest part to get right.
- Cheap wireless earbuds and fast chargers are the accessories most often returned faulty.
- A few free re-repairs and refunds break policy, to show the policy check working.
"""
import math
import random
from datetime import date, timedelta

from tracker import db
from tracker.policy import policy_warnings, suggests_supplier_claim

START, END = date(2026, 4, 1), date(2026, 9, 30)
WARM_UP = timedelta(days=150)                       # jobs before April can still come back in the period
BAD_BATTERY_BATCH = (date(2026, 5, 25), date(2026, 7, 10))

# device: (brand, genuine screen price, genuine battery price, small-part price)
DEVICES = {
    "iPhone 11": ("Apple", 169, 79, 69), "iPhone 12": ("Apple", 229, 89, 79),
    "iPhone 13": ("Apple", 279, 89, 79), "iPhone 14": ("Apple", 329, 99, 89),
    "iPhone 15": ("Apple", 369, 109, 99),
    "Galaxy S21": ("Samsung", 239, 69, 59), "Galaxy S22": ("Samsung", 259, 75, 65),
    "Galaxy S23": ("Samsung", 279, 79, 69), "Galaxy A53": ("Samsung", 139, 59, 49),
    "Galaxy A54": ("Samsung", 149, 59, 49),
    "Pixel 6": ("Google", 199, 69, 59), "Pixel 7": ("Google", 219, 75, 59), "Pixel 8": ("Google", 249, 79, 65),
    "OnePlus 9": ("OnePlus", 189, 65, 55), "OnePlus 10 Pro": ("OnePlus", 229, 69, 59),
    "OnePlus Nord 3": ("OnePlus", 139, 55, 49),
}
GRADE_SUPPLIER = {"Genuine": "Supplier A", "Premium aftermarket": "Supplier B", "Standard aftermarket": "Supplier C"}
GRADE_PRICE = {"Genuine": 1.0, "Premium aftermarket": 0.6, "Standard aftermarket": 0.42}
GRADE_COST = {"Genuine": 0.45, "Premium aftermarket": 0.35, "Standard aftermarket": 0.28}

NEW_PHONES = [("Samsung", "Galaxy A16", 199, 160), ("Samsung", "Galaxy A56", 469, 390),
              ("Samsung", "Galaxy S25", 899, 760), ("Google", "Pixel 9a", 499, 420),
              ("OnePlus", "OnePlus Nord 4", 449, 370)]
RECON_PHONES = [("Apple", "iPhone 12", "Grade A", 349, 260), ("Apple", "iPhone 13", "Grade A", 429, 330),
                ("Apple", "iPhone 13", "Grade B", 379, 290), ("Apple", "iPhone 14", "Grade A", 529, 420),
                ("Samsung", "Galaxy S22", "Grade A", 329, 240), ("Samsung", "Galaxy S23", "Grade A", 449, 350),
                ("Google", "Pixel 7", "Grade A", 299, 220)]
ACCESSORIES = [  # subcategory, name, price, cost, sales weight, return rate
    ("Cases & protection", "Clear case", 15, 2.5, 12, 0.012),
    ("Cases & protection", "Wallet case", 25, 5, 6, 0.014),
    ("Cases & protection", "Rugged case", 30, 7, 4, 0.010),
    ("Cases & protection", "Tempered glass protector", 15, 1.5, 22, 0.006),
    ("Cases & protection", "Privacy screen protector", 20, 2.5, 5, 0.010),
    ("Cases & protection", "Camera lens protector", 12, 1.5, 4, 0.008),
    ("Charging", "USB-C cable", 12, 2.5, 14, 0.014),
    ("Charging", "Lightning cable", 15, 3, 8, 0.018),
    ("Charging", "20W USB-C charger", 25, 6, 9, 0.014),
    ("Charging", "45W fast charger", 39, 11, 4, 0.030),
    ("Charging", "Wireless charging pad", 35, 10, 3, 0.020),
    ("Charging", "MagSafe charger", 39, 9, 3, 0.022),
    ("Power banks", "Power bank 10,000mAh", 35, 11, 3, 0.016),
    ("Power banks", "Power bank 20,000mAh", 49, 16, 2, 0.018),
    ("Audio", "Wired earphones", 15, 3, 4, 0.012),
    ("Audio", "Wireless earbuds", 45, 14, 5, 0.035),
    ("Audio", "Bluetooth speaker", 39, 13, 2, 0.015),
    ("Car & mounts", "Car mount", 20, 5, 3, 0.010),
    ("Car & mounts", "Car charger", 18, 4, 3, 0.016),
    ("Wearables", "Smartwatch strap", 19, 3, 3, 0.012),
    ("Storage & memory", "MicroSD card 128GB", 22, 8, 3, 0.010),
    ("Storage & memory", "USB flash drive 64GB", 15, 5, 2, 0.008),
]
STAFF = [("Ciarán B.", "technician"), ("Priya S.", "technician"), ("Aoife M.", "sales"),
         ("Tomás K.", "sales"), ("Mei L.", "manager")]

BRAND_SHARE = {"Apple": 45, "Samsung": 30, "Google": 12, "OnePlus": 13}
PART_SHARE = {"Screen": 50, "Battery": 25, "Charging port flex": 10, "Sensor flex": 5, "Back glass": 6, "Camera": 4}
SCREEN_GRADES = {"Genuine": 22, "Premium aftermarket": 45, "Standard aftermarket": 33}
BATTERY_GRADES = {"Genuine": 35, "Standard aftermarket": 65}
SINGLE_GRADE = {"Charging port flex": "Premium aftermarket", "Sensor flex": "Premium aftermarket",
                "Back glass": "Standard aftermarket", "Camera": "Genuine"}

COMEBACK = {  # (part, grade) -> chance a job comes back
    ("Screen", "Genuine"): 0.022, ("Screen", "Premium aftermarket"): 0.048, ("Screen", "Standard aftermarket"): 0.115,
    ("Battery", "Genuine"): 0.022, ("Battery", "Standard aftermarket"): 0.055,
    ("Charging port flex", "Premium aftermarket"): 0.045, ("Sensor flex", "Premium aftermarket"): 0.10,
    ("Back glass", "Standard aftermarket"): 0.03, ("Camera", "Genuine"): 0.03,
}
REPAIR_REASONS = {
    "Screen": {"Touch not working / ghost touch": 38, "Lines or dead pixels on display": 30, "Part dead on arrival": 10,
               "Sensor not working (Face ID / proximity / fingerprint)": 6, "Fitting issue (workmanship)": 8,
               "Customer damage after repair": 8},
    "Battery": {"Battery drains fast / not holding charge": 65, "Not charging": 8, "Part dead on arrival": 10,
                "Fitting issue (workmanship)": 9, "Customer damage after repair": 3},
    "Charging port flex": {"Not charging": 65, "Part dead on arrival": 12, "Fitting issue (workmanship)": 18,
                           "Customer damage after repair": 5},
    "Sensor flex": {"Sensor not working (Face ID / proximity / fingerprint)": 75, "Part dead on arrival": 12,
                    "Fitting issue (workmanship)": 13},
    "Back glass": {"Fitting issue (workmanship)": 45, "Customer damage after repair": 40, "Part dead on arrival": 15},
    "Camera": {"Part dead on arrival": 45, "Fitting issue (workmanship)": 45, "Customer damage after repair": 10},
}
DAYS = {  # reason -> (min, max) days between sale and return
    "Part dead on arrival": (0, 3), "Touch not working / ghost touch": (2, 40),
    "Lines or dead pixels on display": (2, 40), "Battery drains fast / not holding charge": (7, 100),
    "Not charging": (3, 60), "Sensor not working (Face ID / proximity / fingerprint)": (0, 20),
    "Fitting issue (workmanship)": (1, 21), "Customer damage after repair": (5, 110),
    "Changed mind": (1, 20), "Faulty": (2, 150), "Wrong model bought": (0, 5),
    "Battery health lower than stated": (2, 30), "Cosmetic grade not as described": (0, 7),
    "Not compatible with phone": (0, 10),
}
COMPAT_PRONE = {"Cases & protection", "Charging"}


def _poisson(rng, mean):
    limit, k, p = math.exp(-mean), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _pick(rng, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _catalogue():
    rows = []  # category, subcategory, brand, device, name, grade, supplier, price, cost
    for device, (brand, screen, battery, small) in DEVICES.items():
        for grade in SCREEN_GRADES:
            rows.append(("Repair", None, brand, device, "Screen", grade, GRADE_SUPPLIER[grade],
                         round(screen * GRADE_PRICE[grade]), round(screen * GRADE_COST[grade], 2)))
        for grade in BATTERY_GRADES:
            price = battery if grade == "Genuine" else round(battery * 0.75)
            rows.append(("Repair", None, brand, device, "Battery", grade, GRADE_SUPPLIER[grade], price,
                         round(price * GRADE_COST[grade], 2)))
        rows.append(("Repair", None, brand, device, "Charging port flex", "Premium aftermarket", "Supplier B",
                     small, round(small * 0.3, 2)))
        rows.append(("Repair", None, brand, device, "Sensor flex", "Premium aftermarket", "Supplier B",
                     small + 30, round((small + 30) * 0.35, 2)))
        if brand != "OnePlus":
            rows.append(("Repair", None, brand, device, "Back glass", "Standard aftermarket", "Supplier C",
                         small + 20, round((small + 20) * 0.25, 2)))
        rows.append(("Repair", None, brand, device, "Camera", "Genuine", "Supplier A",
                     small + 40, round((small + 40) * 0.45, 2)))
    for brand, device, price, cost in NEW_PHONES:
        rows.append(("New phone", None, brand, device, "Brand new", None, "Distributor", price, cost))
    for brand, device, grade, price, cost in RECON_PHONES:
        rows.append(("Reconditioned phone", None, brand, device, grade, None, "Refurb partner", price, cost))
    for sub, name, price, cost, _, _ in ACCESSORIES:
        rows.append(("Accessory", sub, "Universal", None, name, None, "Supplier D", price, cost))
    return rows


def _repair_return(rng, brand, part, grade, supplier, day):
    rate = COMEBACK[(part, grade)]
    in_batch = part == "Battery" and supplier == "Supplier C" and BAD_BATTERY_BATCH[0] <= day <= BAD_BATTERY_BATCH[1]
    if in_batch:
        rate *= 3.5
    if brand == "Google" and part == "Screen":
        rate *= 1.6
    if rng.random() >= rate:
        return None
    reasons = dict(REPAIR_REASONS[part])
    if brand == "Google" and part == "Screen":
        reasons["Sensor not working (Face ID / proximity / fingerprint)"] *= 5
    reason = _pick(rng, reasons)
    lo, hi = (5, 35) if in_batch and reason.startswith("Battery") else DAYS[reason]
    days = rng.randint(lo, hi)
    if reason == "Customer damage after repair":
        outcome = "Declined" if rng.random() < 0.9 else "Re-repair (free)"   # goodwill re-repairs break policy
    elif days > 90:
        outcome = "Declined" if rng.random() < 0.75 else "Re-repair (free)"
    elif reason == "Fitting issue (workmanship)":
        outcome = "Re-repair (free)" if rng.random() < 0.95 else "Refund"
    else:
        outcome = "Re-repair (free)" if rng.random() < 0.82 else "Refund"
    return reason, days, outcome


def _product_return(rng, category, subcategory, rate):
    if rng.random() >= rate:
        return None
    if category == "Reconditioned phone":
        reason = _pick(rng, {"Changed mind": 30, "Faulty": 20, "Battery health lower than stated": 30,
                             "Cosmetic grade not as described": 20})
    elif category == "New phone":
        reason = _pick(rng, {"Changed mind": 50, "Faulty": 25, "Wrong model bought": 25})
    else:
        compat = 40 if subcategory in COMPAT_PRONE else 8
        reason = _pick(rng, {"Changed mind": 30, "Faulty": 45, "Not compatible with phone": compat})
    days = rng.randint(*DAYS[reason])
    if reason == "Changed mind":
        outcome = ("Refund" if rng.random() < 0.7 else "Store credit") if days <= 14 else \
                  ("Store credit" if rng.random() < 0.6 else "Refund")
    elif reason in ("Wrong model bought", "Not compatible with phone"):
        outcome = "Exchange"
    elif category == "New phone" and days > 30:
        outcome = "Declined"  # goes to manufacturer warranty
    else:
        outcome = "Exchange" if rng.random() < 0.6 else "Refund"
    return reason, days, outcome


def seed(conn, rng_seed: int = 7) -> None:
    rng = random.Random(rng_seed)
    conn.executemany(
        """INSERT INTO items (category, subcategory, brand, device, name, part_grade, supplier, price, cost)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", _catalogue())
    conn.executemany("INSERT INTO staff (name, role) VALUES (?, ?)", STAFF)
    rows = conn.execute("SELECT id, category, subcategory, brand, device, name, part_grade, supplier FROM items").fetchall()
    staff = {role: [i for i, r in conn.execute("SELECT id, role FROM staff") if r == role]
             for role in ("technician", "sales", "manager")}
    repairs = {(r[4], r[5], r[6]): r for r in rows if r[1] == "Repair"}
    devices_by_brand = {b: [d for d, v in DEVICES.items() if v[0] == b] for b in BRAND_SHARE}
    phones = {c: [r for r in rows if r[1] == c] for c in ("New phone", "Reconditioned phone")}
    accessories = {r[5]: r for r in rows if r[1] == "Accessory"}

    sales, returns = [], []

    def record(day, item, staff_id, result):
        if not result:
            return
        reason, days, outcome = result
        return_day = day + timedelta(days=days)
        if not START <= return_day <= END:
            return
        category = item[1]
        flagged = bool(policy_warnings(category, reason, outcome, days))
        claim = suggests_supplier_claim(category, reason) and outcome != "Declined" and rng.random() < 0.9
        handler = rng.choice(staff["technician"] if category == "Repair" else staff["sales"] + staff["manager"])
        returns.append((return_day.isoformat(), day.isoformat(), days, item[0], reason, outcome, handler,
                        int(claim), int(flagged), "Approved by manager" if flagged and rng.random() < 0.4 else None))

    day = START - WARM_UP
    while day <= END:
        busy = 1.25 if day.weekday() == 5 else 1.0   # Saturdays are busiest
        for _ in range(_poisson(rng, 16 * busy)):      # repair jobs
            brand = _pick(rng, BRAND_SHARE)
            device = rng.choice(devices_by_brand[brand])
            part = _pick(rng, PART_SHARE)
            if part == "Back glass" and brand == "OnePlus":
                part = "Screen"
            grade = (_pick(rng, SCREEN_GRADES) if part == "Screen" else
                     _pick(rng, BATTERY_GRADES) if part == "Battery" else SINGLE_GRADE[part])
            item = repairs[(device, part, grade)]
            tech = rng.choice(staff["technician"])
            if day >= START:
                sales.append((day.isoformat(), item[0], tech, 1))
            record(day, item, tech, _repair_return(rng, brand, part, grade, item[7], day))
        for category, mean, rate in (("New phone", 0.8, 0.03), ("Reconditioned phone", 1.3, 0.10)):
            for _ in range(_poisson(rng, mean * busy)):
                item = rng.choice(phones[category])
                seller = rng.choice(staff["sales"])
                if day >= START:
                    sales.append((day.isoformat(), item[0], seller, 1))
                record(day, item, seller, _product_return(rng, category, None, rate))
        for _ in range(_poisson(rng, 20 * busy)):      # accessories
            sub, name, _, _, _, rate = rng.choices(ACCESSORIES, weights=[a[4] for a in ACCESSORIES])[0]
            item = accessories[name]
            seller = rng.choice(staff["sales"])
            if day >= START:
                sales.append((day.isoformat(), item[0], seller, 1))
            record(day, item, seller, _product_return(rng, "Accessory", sub, rate))
        day += timedelta(days=1)

    conn.executemany("INSERT INTO sales (sale_date, item_id, staff_id, quantity) VALUES (?, ?, ?, ?)", sales)
    conn.executemany(
        """INSERT INTO returns (return_date, purchase_date, days_since_purchase, item_id, reason, outcome,
                                staff_id, supplier_claim, out_of_policy, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", returns)
    conn.commit()


if __name__ == "__main__":
    c = db.connect()
    db.init_db(c)
    if db.is_empty(c):
        seed(c)
    print(c.execute("SELECT (SELECT SUM(quantity) FROM sales), (SELECT COUNT(*) FROM returns)").fetchone())
