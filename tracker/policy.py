"""Returns policy: reference values and the out-of-policy check (business rules BR-01 to BR-03)."""

REASONS = [
    "Changed mind",
    "Faulty – screen",
    "Faulty – battery",
    "Faulty – charging port",
    "Not as described",
    "Wrong model bought",
    "Network / connectivity issue",
    "Accidental damage",
]
FAULT_REASONS = {"Faulty – screen", "Faulty – battery", "Faulty – charging port"}
CONDITIONS = ["Sealed / unopened", "Like new", "Used – good", "Damaged"]
OUTCOMES = ["Refund", "Exchange", "Repair"]

CHANGE_OF_MIND_DAYS = 14   # BR-01
FAULT_REFUND_DAYS = 30     # BR-02


def policy_warnings(reason: str, outcome: str, days_since_purchase: int) -> list[str]:
    """Return the reasons a return breaks policy (empty list = within policy)."""
    warnings = []
    if reason == "Changed mind" and outcome == "Refund" and days_since_purchase > CHANGE_OF_MIND_DAYS:
        warnings.append(
            f"Change-of-mind refunds are only allowed within {CHANGE_OF_MIND_DAYS} days "
            f"(this is day {days_since_purchase}). Offer an exchange or get manager approval."
        )
    if reason in FAULT_REASONS and outcome == "Refund" and days_since_purchase > FAULT_REFUND_DAYS:
        warnings.append(
            f"Faulty phones can only be refunded within {FAULT_REFUND_DAYS} days "
            f"(this is day {days_since_purchase}). After that, repair or exchange under warranty."
        )
    if reason == "Accidental damage" and outcome in ("Refund", "Exchange"):
        warnings.append("Accidental damage isn't covered by the returns policy. Offer a paid repair.")
    return warnings
