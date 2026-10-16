"""Generates realistic demo data for a phone repair, accessories & electronics shop. No real data.

The story the data tells (modelled on how small phone shops actually run):

* Before the app (April–June): sales go through the till, but most faulty swaps at the counter
  are NOT recorded — the customer gets a new unit off the shelf, the faulty one gets "faulty"
  written on the box and goes into an old box under the counter. Some repair parts aren't
  deducted, some damaged deliveries go straight into the box, and a little stock walks.
  Nothing goes back to suppliers.
* Go-live (1 July): a full stock count shows units missing from the shelf. The old faulty box is
  counted and sent back, but suppliers reject a lot of it because it's too old.
* After go-live (July–September): every swap is recorded in one step, the faulty bin goes back
  to suppliers every month, and monthly counts match the system.

Other built-in patterns: wireless earbuds fail far more than anything else (2–4 in 10),
standard aftermarket screens come back ~5x more than genuine, and Corrib Budget Parts had
a bad battery batch in early summer. All supplier and staff names are fictional.
"""
import math
import random
from collections import defaultdict
from datetime import date, timedelta

from tracker import db, stock
from tracker.auth import DEMO_LOGINS, hash_password
from tracker.policy import policy_warnings, suggests_supplier_claim

START, END = date(2026, 4, 1), date(2026, 9, 30)
GO_LIVE = date(2026, 7, 1)
WARM_UP = timedelta(days=150)                       # repair jobs before April can still come back
BAD_BATTERY_BATCH = (date(2026, 5, 25), date(2026, 7, 10))
SHIP_DATES = [date(2026, 7, 3), date(2026, 8, 3), date(2026, 9, 1)]   # faulty bin goes back monthly
RECORDED_BEFORE_GO_LIVE = 0.3   # share of faulty swaps that got recorded before the app

DEVICES = {  # device: (brand, genuine screen price, genuine battery price, small-part price)
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
GRADE_SUPPLIER = {"Genuine": "Harbourline Parts", "Premium aftermarket": "Liffeyside Spares",
                  "Standard aftermarket": "Corrib Budget Parts"}
GRADE_PRICE = {"Genuine": 1.0, "Premium aftermarket": 0.6, "Standard aftermarket": 0.42}
GRADE_COST = {"Genuine": 0.45, "Premium aftermarket": 0.35, "Standard aftermarket": 0.28}

NEW_PHONES = [("Samsung", "Galaxy A16", 199, 160), ("Samsung", "Galaxy A56", 469, 390),
              ("Samsung", "Galaxy S25", 899, 760), ("Google", "Pixel 9a", 499, 420),
              ("OnePlus", "OnePlus Nord 4", 449, 370)]
RECON_PHONES = [("Apple", "iPhone 12", "Grade A", 349, 260), ("Apple", "iPhone 13", "Grade A", 429, 330),
                ("Apple", "iPhone 13", "Grade B", 379, 290), ("Apple", "iPhone 14", "Grade A", 529, 420),
                ("Samsung", "Galaxy S22", "Grade A", 329, 240), ("Samsung", "Galaxy S23", "Grade A", 449, 350),
                ("Google", "Pixel 7", "Grade A", 299, 220)]

ACC, AUDIO, GAMING, TOYS = ("Emerald Isle Accessories", "Atlantic Audio & Wearables",
                            "Shannon Gaming Supply", "Lir Toys & Gadgets")
PRODUCTS = [  # group, name, supplier, price, cost, daily sales weight, fault rate, warranty days
    ("Cases & protection", "Clear case", ACC, 15, 2.5, 12, 0.01, 30),
    ("Cases & protection", "Wallet case", ACC, 25, 5, 6, 0.015, 30),
    ("Cases & protection", "Rugged case", ACC, 30, 7, 4, 0.01, 30),
    ("Cases & protection", "Tempered glass protector", ACC, 15, 1.5, 20, 0.01, 30),
    ("Charging", "USB-C cable", ACC, 12, 2.5, 13, 0.05, 30),
    ("Charging", "Lightning cable", ACC, 15, 3, 7, 0.07, 30),
    ("Charging", "20W USB-C charger", ACC, 25, 6, 8, 0.05, 90),
    ("Charging", "45W fast charger", ACC, 39, 11, 4, 0.09, 90),
    ("Charging", "Wireless charging pad", ACC, 35, 10, 3, 0.07, 90),
    ("Charging", "Car charger", ACC, 18, 4, 3, 0.06, 90),
    ("Power banks", "Power bank 10,000mAh", ACC, 35, 11, 3, 0.08, 90),
    ("Power banks", "Power bank 20,000mAh", ACC, 49, 16, 2, 0.10, 90),
    ("Audio", "Wireless earbuds", AUDIO, 45, 14, 6, 0.28, 90),
    ("Audio", "Wired earphones", AUDIO, 15, 3, 3, 0.06, 30),
    ("Audio", "Bluetooth speaker", AUDIO, 39, 13, 2, 0.07, 90),
    ("Smartwatches", "Smartwatch", AUDIO, 59, 22, 3, 0.11, 90),
    ("Smartwatches", "Fitness band", AUDIO, 35, 12, 2, 0.08, 90),
    ("Smartwatches", "Kids smartwatch", AUDIO, 39, 15, 2, 0.14, 90),
    ("Gaming", "Wireless game controller", GAMING, 45, 18, 3, 0.13, 90),
    ("Gaming", "Handheld game console", GAMING, 199, 150, 0.6, 0.05, 90),
    ("Gaming", "Gaming headset", GAMING, 39, 14, 2, 0.09, 90),
    ("Toys & gadgets", "RC car", TOYS, 29, 10, 2, 0.16, 30),
    ("Toys & gadgets", "Mini drone", TOYS, 49, 20, 1.5, 0.20, 30),
    ("Toys & gadgets", "Galaxy star projector", TOYS, 25, 8, 2, 0.10, 30),
]
SUPPLIER_TERMS = {  # days to settle, acceptance rate, what they give back when they accept
    "Harbourline Parts": ((7, 14), 0.95, {"Credit note": 70, "Replacement stock": 30}),
    "Liffeyside Spares": ((10, 20), 0.88, {"Replacement stock": 60, "Credit note": 40}),
    "Corrib Budget Parts": ((15, 40), 0.70, {"Replacement stock": 50, "Credit note": 50}),
    ACC: ((5, 12), 0.92, {"Replacement stock": 70, "Credit note": 30}),
    AUDIO: ((8, 18), 0.85, {"Replacement stock": 60, "Credit note": 40}),
    GAMING: ((10, 21), 0.80, {"Replacement stock": 50, "Credit note": 50}),
    TOYS: ((6, 14), 0.75, {"Credit note": 70, "Replacement stock": 30}),
    "Renew Mobile Refurb": ((10, 20), 0.85, {"Refund": 50, "Replacement stock": 50}),
    "Celtic Handset Distribution": ((7, 14), 0.95, {"Replacement stock": 80, "Credit note": 20}),
}
STAFF = [("Sanjay", "manager", "sanjay"), ("Karolina", "technician", "karolina"),
         ("William", "technician", "william"), ("Kariana", "sales", "kariana")]

BRAND_SHARE = {"Apple": 45, "Samsung": 30, "Google": 12, "OnePlus": 13}
PART_SHARE = {"Screen": 50, "Battery": 25, "Charging port flex": 10, "Sensor flex": 5, "Back glass": 6, "Camera": 4}
SCREEN_GRADES = {"Genuine": 22, "Premium aftermarket": 45, "Standard aftermarket": 33}
BATTERY_GRADES = {"Genuine": 35, "Standard aftermarket": 65}
SINGLE_GRADE = {"Charging port flex": "Premium aftermarket", "Sensor flex": "Premium aftermarket",
                "Back glass": "Standard aftermarket", "Camera": "Genuine"}
COMEBACK = {  # (part, grade) -> chance a repair comes back
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
REPAIR_DAYS = {
    "Part dead on arrival": (0, 3), "Touch not working / ghost touch": (2, 40),
    "Lines or dead pixels on display": (2, 40), "Battery drains fast / not holding charge": (7, 100),
    "Not charging": (3, 60), "Sensor not working (Face ID / proximity / fingerprint)": (0, 20),
    "Fitting issue (workmanship)": (1, 21), "Customer damage after repair": (5, 110),
}
THEFT_PRONE = ["Wireless earbuds", "Smartwatch", "Power bank 20,000mAh", "Wireless game controller"]
PRE_SALE_TEST_FAILS = ["Wireless earbuds", "Mini drone", "Kids smartwatch", "45W fast charger"]


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
    rows = []  # category, subcategory, brand, device, name, grade, supplier, warranty, price, cost, reorder_level
    for device, (brand, screen, battery, small) in DEVICES.items():
        for grade in SCREEN_GRADES:
            rows.append(("Repair", "Repair parts", brand, device, "Screen", grade, GRADE_SUPPLIER[grade], 90,
                         round(screen * GRADE_PRICE[grade]), round(screen * GRADE_COST[grade], 2), 1))
        for grade in BATTERY_GRADES:
            price = battery if grade == "Genuine" else round(battery * 0.75)
            rows.append(("Repair", "Repair parts", brand, device, "Battery", grade, GRADE_SUPPLIER[grade], 90, price,
                         round(price * GRADE_COST[grade], 2), 1))
        for part, grade, price, ratio in (("Charging port flex", "Premium aftermarket", small, 0.3),
                                          ("Sensor flex", "Premium aftermarket", small + 30, 0.35),
                                          ("Back glass", "Standard aftermarket", small + 20, 0.25),
                                          ("Camera", "Genuine", small + 40, 0.45)):
            if part == "Back glass" and brand == "OnePlus":
                continue
            rows.append(("Repair", "Repair parts", brand, device, part, grade, GRADE_SUPPLIER[grade], 90, price,
                         round(price * ratio, 2), 1))
    for brand, device, price, cost in NEW_PHONES:
        rows.append(("New phone", "Phones", brand, device, "Brand new", None, "Celtic Handset Distribution", 30,
                     price, cost, 1))
    for brand, device, grade, price, cost in RECON_PHONES:
        rows.append(("Reconditioned phone", "Phones", brand, device, grade, None, "Renew Mobile Refurb", 180,
                     price, cost, 1))
    for group, name, supplier, price, cost, weight, _, warranty in PRODUCTS:
        rows.append(("Accessory", group, "Universal", None, name, None, supplier, warranty, price, cost,
                     max(2, round(weight * 0.8))))
    return rows


def _reorder_qty(category, weight=1.0):
    if category == "Repair":
        return 4
    if category in ("New phone", "Reconditioned phone"):
        return 3
    return max(5, round(weight * 3))


class _Shop:
    """Simulates the shop day by day, writing everything the system would record."""

    def __init__(self, conn, rng):
        self.conn, self.rng = conn, rng
        staff = {role: [i for i, r in conn.execute("SELECT id, role FROM staff") if r == role]
                 for role in ("technician", "sales", "manager")}
        self.techs, self.sales_staff, self.manager = staff["technician"], staff["sales"], staff["manager"][0]
        self.counter = staff["sales"] + staff["manager"]
        cols = ["id", "category", "subcategory", "brand", "device", "name", "part_grade", "supplier",
                "warranty_days", "price", "cost", "reorder_level"]
        self.items = {r[0]: dict(zip(cols, r)) for r in conn.execute(f"SELECT {', '.join(cols)} FROM items")}
        self.repairs = {(i["device"], i["name"], i["part_grade"]): i for i in self.items.values()
                        if i["category"] == "Repair"}
        self.phones = {c: [i for i in self.items.values() if i["category"] == c]
                       for c in ("New phone", "Reconditioned phone")}
        self.products = {i["name"]: i for i in self.items.values() if i["category"] == "Accessory"}
        self.weight = {p[1]: p[5] for p in PRODUCTS}
        self.fault_rate = {p[1]: p[6] for p in PRODUCTS}
        self.shelf = defaultdict(int)          # what is physically on the shelf
        self.old_box = defaultdict(int)        # faulty units swapped before the app, never recorded
        self.events = defaultdict(list)        # day -> customers coming back
        self.settles = defaultdict(list)       # day -> supplier decisions
        self.deliveries = defaultdict(list)    # day -> deliveries arriving
        self.on_order = set()
        self.sales = []

    def recorded(self, day, share=RECORDED_BEFORE_GO_LIVE):
        return day >= GO_LIVE or self.rng.random() < share

    def reorder_qty(self, iid):
        item = self.items[iid]
        return _reorder_qty(item["category"], self.weight.get(item["name"], 1))

    def deliver(self, day, iid, qty):
        """Damaged units go to the faulty bin — or, before the app, often into the old box unrecorded."""
        item, rng = self.items[iid], self.rng
        dmg_rate = 0.04 if item["subcategory"] in ("Gaming", "Toys & gadgets") else 0.02
        damaged = sum(rng.random() < dmg_rate for _ in range(qty)) if item["category"] != "Repair" else 0
        if damaged and not self.recorded(day, 0.5):
            stock.receive_delivery(self.conn, day, iid, qty, 0, rng.choice(self.counter))   # booked as all fine
            self.old_box[iid] += damaged
        else:
            stock.receive_delivery(self.conn, day, iid, qty - damaged, damaged, rng.choice(self.counter),
                                   problem=rng.choice(stock.DELIVERY_PROBLEMS) if damaged else None)
        self.shelf[iid] += qty - damaged
        self.on_order.discard(iid)

    def take_from_shelf(self, day, iid):
        if self.shelf[iid] <= 0:                 # urgent order for a repair part or phone
            self.deliver(day, iid, self.reorder_qty(iid))
        self.shelf[iid] -= 1

    def log_return(self, day, iid, sale_day, reason, outcome, handler, faulty, note=None):
        item = self.items[iid]
        days = (day - sale_day).days
        flagged = bool(policy_warnings(item["category"], reason, outcome, days, item["warranty_days"]))
        db.add_return(self.conn, return_date=day, purchase_date=sale_day, item_id=iid, reason=reason,
                      outcome=outcome, staff_id=handler, supplier_claim=faulty, out_of_policy=flagged,
                      category=item["category"],
                      notes=note or ("Approved by manager" if flagged and self.rng.random() < 0.4 else None),
                      commit=False)

    # ── One simulated day ──
    def repair_jobs(self, day, busy):
        rng = self.rng
        for _ in range(_poisson(rng, 16 * busy)):
            brand = _pick(rng, BRAND_SHARE)
            device = rng.choice([d for d, v in DEVICES.items() if v[0] == brand])
            part = _pick(rng, PART_SHARE)
            if part == "Back glass" and brand == "OnePlus":
                part = "Screen"
            grade = (_pick(rng, SCREEN_GRADES) if part == "Screen" else
                     _pick(rng, BATTERY_GRADES) if part == "Battery" else SINGLE_GRADE[part])
            item = self.repairs[(device, part, grade)]
            tech = rng.choice(self.techs)
            if day >= START:
                self.sales.append((day.isoformat(), item["id"], tech, 1))
                self.take_from_shelf(day, item["id"])
                if self.recorded(day, 0.95):         # before the app, a few parts weren't deducted
                    stock.record_sale(self.conn, day, item["id"], tech, repair=True)
            in_batch = part == "Battery" and item["supplier"] == "Corrib Budget Parts" and \
                BAD_BATTERY_BATCH[0] <= day <= BAD_BATTERY_BATCH[1]
            rate = COMEBACK[(part, grade)] * (3.5 if in_batch else 1) * (1.6 if brand == "Google" and part == "Screen" else 1)
            if rng.random() < rate:
                reasons = dict(REPAIR_REASONS[part])
                if brand == "Google" and part == "Screen":
                    reasons["Sensor not working (Face ID / proximity / fingerprint)"] *= 5
                reason = _pick(rng, reasons)
                lo, hi = (5, 35) if in_batch and reason.startswith("Battery") else REPAIR_DAYS[reason]
                self.events[day + timedelta(days=rng.randint(lo, hi))].append(("comeback", item["id"], day, reason))

    def product_sales(self, day, busy):
        rng = self.rng
        for category, mean, rate in (("New phone", 0.8, 0.03), ("Reconditioned phone", 1.3, 0.10)):
            for _ in range(_poisson(rng, mean * busy)):
                item = rng.choice(self.phones[category])
                seller = rng.choice(self.sales_staff)
                self.sales.append((day.isoformat(), item["id"], seller, 1))
                self.take_from_shelf(day, item["id"])
                stock.record_sale(self.conn, day, item["id"], seller)
                if rng.random() < rate:
                    reason = _pick(rng, {"Changed mind": 40, "Faulty": 30, "Battery health lower than stated": 30}
                                   if category == "Reconditioned phone" else
                                   {"Changed mind": 50, "Faulty": 25, "Wrong model bought": 25})
                    self.events[day + timedelta(days=rng.randint(1, 25))].append(("phone", item["id"], day, reason))
        for _ in range(_poisson(rng, 24 * busy)):
            name = rng.choices(list(self.weight), weights=list(self.weight.values()))[0]
            item = self.products[name]
            if self.shelf[item["id"]] <= 0:
                continue                             # out of stock: lost sale
            seller = rng.choice(self.sales_staff)
            self.sales.append((day.isoformat(), item["id"], seller, 1))
            self.shelf[item["id"]] -= 1
            stock.record_sale(self.conn, day, item["id"], seller)
            if rng.random() < self.fault_rate[name]:
                self.events[day + timedelta(days=rng.randint(1, 45))].append(("fault", item["id"], day, None))
            elif rng.random() < 0.012:
                reason = "Not compatible with phone" if item["subcategory"] in ("Cases & protection", "Charging") \
                    and rng.random() < 0.5 else "Changed mind"
                self.events[day + timedelta(days=rng.randint(0, 12))].append(("other", item["id"], day, reason))

    def shrinkage_and_tests(self, day):
        rng = self.rng
        if day.weekday() == 0 and rng.random() < (0.5 if day < GO_LIVE else 0.12):   # stock walks
            iid = self.products[rng.choice(THEFT_PRONE)]["id"]
            if self.shelf[iid] > 0:
                self.shelf[iid] -= 1
        if day >= GO_LIVE and rng.random() < 0.05:                                    # pre-sale test fails
            iid = self.products[rng.choice(PRE_SALE_TEST_FAILS)]["id"]
            if self.shelf[iid] > 0:
                self.shelf[iid] -= 1
                stock.found_faulty(self.conn, day, iid, 1, rng.choice(self.counter), note="Failed pre-sale test")

    def customers_coming_back(self, day):
        rng = self.rng
        for kind, iid, sale_day, reason in self.events.pop(day, []):
            if day < START:
                continue
            item, days = self.items[iid], (day - sale_day).days
            if kind == "comeback":
                if reason == "Customer damage after repair":
                    outcome = "Declined" if rng.random() < 0.9 else "Re-repair (free)"
                elif days > 90:
                    outcome = "Declined" if rng.random() < 0.75 else "Re-repair (free)"
                elif reason == "Fitting issue (workmanship)":
                    outcome = "Re-repair (free)" if rng.random() < 0.95 else "Refund"
                else:
                    outcome = "Re-repair (free)" if rng.random() < 0.82 else "Refund"
                if outcome == "Re-repair (free)":
                    self.take_from_shelf(day, iid)
                faulty = suggests_supplier_claim("Repair", reason) and outcome != "Declined"
                self.log_return(day, iid, sale_day, reason, outcome, rng.choice(self.techs), faulty)
            elif kind == "fault":                    # the "2 in 10 earbuds" situation
                if days > item["warranty_days"]:
                    continue
                outcome = "Exchange" if self.shelf[iid] > 0 and rng.random() < 0.82 else \
                    _pick(rng, {"Refund": 60, "Store credit": 40})
                if outcome == "Exchange":
                    self.shelf[iid] -= 1
                if self.recorded(day):
                    self.log_return(day, iid, sale_day, "Faulty", outcome, rng.choice(self.counter), True,
                                    note=f"Fault: {rng.choice(stock.FAULTS[:6])}")
                else:
                    self.old_box[iid] += 1           # swapped at the counter, nothing recorded
            elif kind == "phone":
                faulty = reason in ("Faulty", "Battery health lower than stated")
                if faulty and days > item["warranty_days"]:
                    continue
                if reason == "Changed mind":
                    outcome = "Refund" if days <= 14 else "Store credit"
                elif reason == "Wrong model bought" or (faulty and self.shelf[iid] > 0 and rng.random() < 0.6):
                    outcome = "Exchange"
                else:
                    outcome = "Refund"
                if outcome == "Exchange" and faulty:
                    self.shelf[iid] -= 1
                if not faulty:
                    self.shelf[iid] += 1
                self.log_return(day, iid, sale_day, reason, outcome, rng.choice(self.counter), faulty)
            else:                                    # changed mind / not compatible: back on the shelf
                self.shelf[iid] += 1
                outcome = "Exchange" if reason == "Not compatible with phone" else \
                    ("Refund" if rng.random() < 0.7 else "Store credit")
                self.log_return(day, iid, sale_day, reason, outcome, rng.choice(self.counter), False)

    def go_live_count(self, day):
        for iid in self.items:
            stock.stock_count(self.conn, day, iid, self.shelf[iid], self.manager, note="Go-live full stock count")
        for iid, qty in self.old_box.items():
            stock.move(self.conn, day, iid, qty, stock.UNEXPLAINED, stock.BIN, "Old faulty box counted at go-live",
                       self.manager, note="Swapped at the counter before the app, never recorded")
        self.old_box.clear()

    def ship_faulty_bin(self, day):
        rng = self.rng
        levels = stock.levels_df(self.conn)
        by_supplier = defaultdict(dict)
        for row in levels[levels[stock.BIN] > 0].itertuples(index=False):
            by_supplier[self.items[row.item_id]["supplier"]][row.item_id] = getattr(row, stock.BIN)
        for supplier, item_qty in by_supplier.items():
            rma = f"RMA-{''.join(w[0] for w in supplier.split()[:2])}{rng.randint(1000, 9999)}"
            (lo, hi), accept, accepted = SUPPLIER_TERMS[supplier]
            if day == SHIP_DATES[0]:
                accept *= 0.6                        # the old box: many units too old to claim
            for claim_id in stock.send_to_supplier(self.conn, day, item_qty, self.manager, rma):
                settle_day = day + timedelta(days=rng.randint(lo, hi))
                if settle_day <= END:
                    resolution = _pick(rng, accepted) if rng.random() < accept else \
                        _pick(rng, {"Rejected - written off": 70, "Rejected - repaired & resold": 30})
                    self.settles[settle_day].append((claim_id, resolution, supplier))

    def supplier_decisions(self, day):
        for claim_id, resolution, supplier in self.settles.pop(day, []):
            iid, qty = self.conn.execute("SELECT item_id, quantity FROM supplier_claims WHERE id = ?",
                                         (claim_id,)).fetchone()
            cost = self.items[iid]["cost"]
            replacement = qty if resolution == "Replacement stock" else None
            credit = round(cost * qty * (0.8 if supplier == "Corrib Budget Parts" else 1.0), 2) \
                if resolution in ("Credit note", "Refund") else None
            stock.close_claim(self.conn, claim_id, resolution, day, self.manager, replacement, credit)
            if resolution in ("Replacement stock", "Rejected - repaired & resold"):
                self.shelf[iid] += qty

    def reorder(self, day):
        for iid in self.deliveries.pop(day, []):
            if iid in self.on_order:
                self.deliver(day, iid, self.reorder_qty(iid))
        for iid, item in self.items.items():
            if self.shelf[iid] <= item["reorder_level"] and iid not in self.on_order:
                self.on_order.add(iid)
                self.deliveries[day + timedelta(days=2)].append(iid)

    def run(self):
        for iid in self.items:                       # opening stock
            qty = self.reorder_qty(iid) + self.items[iid]["reorder_level"]
            stock.move(self.conn, START, iid, qty, stock.SUPPLIER, stock.SHELF, "Opening stock", self.manager)
            self.shelf[iid] = qty
        day = START - WARM_UP
        while day <= END:
            busy = 1.25 if day.weekday() == 5 else 1.0      # Saturdays are busiest
            if day == GO_LIVE:
                self.go_live_count(day)
            self.repair_jobs(day, busy)
            if day >= START:
                self.product_sales(day, busy)
                self.shrinkage_and_tests(day)
            self.customers_coming_back(day)
            if day in SHIP_DATES:
                self.ship_faulty_bin(day)
            self.supplier_decisions(day)
            if day > GO_LIVE and (day + timedelta(days=1)).day == 1:   # month-end counts
                for iid in self.items:
                    stock.stock_count(self.conn, day, iid, self.shelf[iid], self.manager, note="Month-end count")
            if day >= START:
                self.reorder(day)
            day += timedelta(days=1)
        self.conn.executemany("INSERT INTO sales (sale_date, item_id, staff_id, quantity) VALUES (?, ?, ?, ?)",
                              self.sales)


def seed(conn, rng_seed: int = 7) -> None:
    conn.executemany(
        """INSERT INTO items (category, subcategory, brand, device, name, part_grade, supplier, warranty_days,
                              price, cost, reorder_level)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", _catalogue())
    demo_passwords = {user: password for user, password, _ in DEMO_LOGINS}
    conn.executemany("INSERT INTO staff (name, role, username, password_hash) VALUES (?, ?, ?, ?)",
                     [(name, role, user, hash_password(demo_passwords.get(user, f"{user}-demo")))
                      for name, role, user in STAFF])
    _Shop(conn, random.Random(rng_seed)).run()
    conn.commit()


if __name__ == "__main__":
    c = db.connect()
    db.init_db(c)
    if db.is_empty(c):
        seed(c)
    print(c.execute("""SELECT (SELECT SUM(quantity) FROM sales), (SELECT COUNT(*) FROM returns),
                              (SELECT COUNT(*) FROM stock_movements), (SELECT COUNT(*) FROM supplier_claims)""").fetchone())
