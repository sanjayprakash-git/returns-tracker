"""Reference values and returns/warranty policy (business rules BR-01 to BR-06)."""

CATEGORIES = ["Repair", "New phone", "Reconditioned phone", "Accessory"]
BRANDS = ["Apple", "Samsung", "Google", "OnePlus"]
PART_TYPES = ["Screen", "Battery", "Charging port flex", "Sensor flex", "Back glass", "Camera"]
PART_GRADES = ["Genuine", "Premium aftermarket", "Standard aftermarket"]

REASONS = {
    "Repair": [
        "Touch not working / ghost touch",
        "Lines or dead pixels on display",
        "Battery drains fast / not holding charge",
        "Not charging",
        "Sensor not working (Face ID / proximity / fingerprint)",
        "Part dead on arrival",
        "Fitting issue (workmanship)",
        "Customer damage after repair",
    ],
    "New phone": ["Changed mind", "Faulty", "Wrong model bought"],
    "Reconditioned phone": ["Changed mind", "Faulty", "Battery health lower than stated",
                            "Cosmetic grade not as described"],
    "Accessory": ["Changed mind", "Faulty", "Not compatible with phone"],
}
ALL_REASONS = sorted({r for reasons in REASONS.values() for r in reasons})

# Who is responsible — drives supplier claims and the "why" chart
SUPPLIER_FAULT = {
    "Touch not working / ghost touch", "Lines or dead pixels on display",
    "Battery drains fast / not holding charge", "Not charging",
    "Sensor not working (Face ID / proximity / fingerprint)", "Part dead on arrival",
    "Faulty", "Battery health lower than stated",
}
WORKMANSHIP = {"Fitting issue (workmanship)"}
CUSTOMER = {"Customer damage after repair"}


def responsibility(reason: str) -> str:
    if reason in SUPPLIER_FAULT:
        return "Part fault"
    if reason in WORKMANSHIP:
        return "Workmanship"
    if reason in CUSTOMER:
        return "Customer damage"
    return "Sale-related"


OUTCOMES = ["Re-repair (free)", "Refund", "Exchange", "Store credit", "Declined"]
OUTCOMES_BY_CATEGORY = {
    "Repair": ["Re-repair (free)", "Refund", "Declined"],
    "New phone": ["Refund", "Exchange", "Store credit", "Declined"],
    "Reconditioned phone": ["Refund", "Exchange", "Store credit", "Declined"],
    "Accessory": ["Refund", "Exchange", "Store credit", "Declined"],
}

REPAIR_WARRANTY_DAYS = 90        # BR-01
CHANGE_OF_MIND_DAYS = 14         # BR-03
NEW_PHONE_REFUND_DAYS = 30       # BR-04 (after that: manufacturer warranty)
RECON_WARRANTY_DAYS = 180        # BR-05
DEFAULT_ACCESSORY_WARRANTY_DAYS = 90  # BR-05: 30 or 90 days depending on the product


def suggests_supplier_claim(category: str, reason: str) -> bool:
    """A faulty part or product can be sent back to the supplier (RMA)."""
    return category in ("Repair", "Accessory", "Reconditioned phone") and reason in SUPPLIER_FAULT


def policy_warnings(category: str, reason: str, outcome: str, days: int,
                    warranty_days: int | None = None) -> list[str]:
    """Return the ways a return breaks policy (empty list = within policy)."""
    w = []
    if category == "Repair":
        if reason in CUSTOMER and outcome != "Declined":
            w.append("Damage caused after the repair isn't covered by the repair warranty. "
                     "Offer a new paid repair (outcome: Declined).")
        elif days > REPAIR_WARRANTY_DAYS and outcome in ("Re-repair (free)", "Refund"):
            w.append(f"The repair warranty is {REPAIR_WARRANTY_DAYS} days (this is day {days}). "
                     "A free re-repair or refund needs manager approval.")
        return w
    if reason == "Changed mind" and outcome == "Refund" and days > CHANGE_OF_MIND_DAYS:
        w.append(f"Change-of-mind refunds are only allowed within {CHANGE_OF_MIND_DAYS} days "
                 f"(this is day {days}). Offer store credit or get manager approval.")
    if category == "New phone" and reason == "Faulty" and outcome == "Refund" and days > NEW_PHONE_REFUND_DAYS:
        w.append(f"After {NEW_PHONE_REFUND_DAYS} days a faulty new phone goes to the manufacturer "
                 "warranty instead of a shop refund.")
    if category == "Reconditioned phone" and reason in SUPPLIER_FAULT and days > RECON_WARRANTY_DAYS \
            and outcome != "Declined":
        w.append(f"Reconditioned phones have a {RECON_WARRANTY_DAYS}-day warranty (this is day {days}).")
    if category == "Accessory" and reason == "Faulty" and outcome != "Declined":
        limit = warranty_days or DEFAULT_ACCESSORY_WARRANTY_DAYS
        if days > limit:
            w.append(f"This accessory has a {limit}-day warranty (this is day {days}).")
    return w
