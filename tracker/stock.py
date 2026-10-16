"""Stock ledger: every unit's location, and every action that moves units between locations.

Locations we hold stock in:   shelf (sellable) · faulty_bin · with_supplier
Outside the shop:             supplier · customer · written_off · unexplained
Stock in a location = units moved in − units moved out. Nothing is edited in place, so every
change has a date, a reason and the staff member who made it.
"""
import pandas as pd

SHELF, BIN, WITH_SUPPLIER = "shelf", "faulty_bin", "with_supplier"
SUPPLIER, CUSTOMER, WRITTEN_OFF, UNEXPLAINED = "supplier", "customer", "written_off", "unexplained"
HELD = (SHELF, BIN, WITH_SUPPLIER)

FAULTS = ["Not powering on", "Not charging / battery", "Sound or connection issue", "Screen or display fault",
          "Buttons or controls", "Physical defect", "Other fault"]
DELIVERY_PROBLEMS = ["Box crushed / packaging damaged", "Item broken on arrival", "Dead on arrival (won't power on)",
                     "Wrong item delivered"]
RESOLUTIONS = ["Replacement stock", "Credit note", "Refund", "Rejected - written off", "Rejected - repaired & resold"]


def _d(day):
    return day.isoformat() if hasattr(day, "isoformat") else str(day)


def move(conn, day, item_id, qty, from_loc, to_loc, reason, staff_id=None, return_id=None, claim_id=None, note=None):
    if qty <= 0:
        return
    conn.execute(
        """INSERT INTO stock_movements (moved_date, item_id, quantity, from_loc, to_loc, reason, staff_id,
                                        return_id, claim_id, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_d(day), item_id, int(qty), from_loc, to_loc, reason, staff_id, return_id, claim_id, note or None))


# ── Counter and back-office actions ──────────────────────────────────────────────

def record_sale(conn, day, item_id, staff_id, qty=1, repair=False):
    move(conn, day, item_id, qty, SHELF, CUSTOMER, "Used in repair" if repair else "Sold", staff_id)


def record_return(conn, day, item_id, category, reason, outcome, staff_id, faulty, return_id=None, note=None):
    """Stock side of a return: faulty unit into the bin, replacement off the shelf, resellable back on it."""
    if outcome == "Declined":
        return
    if faulty:
        move(conn, day, item_id, 1, CUSTOMER, BIN,
             "Faulty part removed (comeback)" if category == "Repair" else "Faulty unit returned", staff_id,
             return_id, note=note)
    if outcome == "Exchange" and faulty:
        move(conn, day, item_id, 1, SHELF, CUSTOMER, "Replacement given (faulty swap)", staff_id, return_id)
    elif outcome == "Re-repair (free)":
        move(conn, day, item_id, 1, SHELF, CUSTOMER, "New part fitted (re-repair)", staff_id, return_id)
    elif not faulty and category != "Repair":
        move(conn, day, item_id, 1, CUSTOMER, SHELF, "Returned to shelf (resellable)", staff_id, return_id)


def receive_delivery(conn, day, item_id, qty_ok, qty_damaged, staff_id, problem=None, note=None):
    move(conn, day, item_id, qty_ok, SUPPLIER, SHELF, "Delivery received", staff_id, note=note)
    move(conn, day, item_id, qty_damaged, SUPPLIER, BIN, "Damaged on delivery", staff_id,
         note=problem if not note else f"{problem} — {note}")


def found_faulty(conn, day, item_id, qty, staff_id, note=None):
    move(conn, day, item_id, qty, SHELF, BIN, "Found faulty on the shelf", staff_id, note=note)


def send_to_supplier(conn, day, item_qty: dict, staff_id, rma_reference=None, note=None) -> list[int]:
    """Send faulty-bin units back: one claim per item, all under one RMA reference."""
    claim_ids = []
    for item_id, qty in item_qty.items():
        if qty <= 0:
            continue
        cur = conn.execute(
            """INSERT INTO supplier_claims (sent_date, item_id, quantity, rma_reference, staff_id, notes)
               VALUES (?, ?, ?, ?, ?, ?)""", (_d(day), item_id, int(qty), rma_reference or None, staff_id, note or None))
        move(conn, day, item_id, qty, BIN, WITH_SUPPLIER, "Sent back to supplier", staff_id, claim_id=cur.lastrowid,
             note=rma_reference)
        claim_ids.append(cur.lastrowid)
    return claim_ids


def close_claim(conn, claim_id, resolution, day, staff_id=None, replacement_qty=None, credit_value=None, note=None):
    item_id, qty, status = conn.execute(
        "SELECT item_id, quantity, status FROM supplier_claims WHERE id = ?", (claim_id,)).fetchone()
    if status == "Closed":
        return
    conn.execute(
        """UPDATE supplier_claims SET status = 'Closed', resolution = ?, resolved_date = ?, replacement_qty = ?,
                  credit_value = ?, notes = COALESCE(?, notes) WHERE id = ?""",
        (resolution, _d(day), replacement_qty, credit_value, note or None, claim_id))
    if resolution == "Rejected - written off":
        move(conn, day, item_id, qty, WITH_SUPPLIER, WRITTEN_OFF, "Supplier rejected — written off", staff_id, claim_id=claim_id)
    elif resolution == "Rejected - repaired & resold":
        move(conn, day, item_id, qty, WITH_SUPPLIER, SHELF, "Supplier rejected — repaired, back on shelf", staff_id,
             claim_id=claim_id)
    else:
        move(conn, day, item_id, qty, WITH_SUPPLIER, SUPPLIER, f"Supplier accepted ({resolution.lower()})", staff_id,
             claim_id=claim_id)
        if resolution == "Replacement stock":
            move(conn, day, item_id, replacement_qty or 0, SUPPLIER, SHELF, "Replacement stock received", staff_id,
                 claim_id=claim_id)


def stock_count(conn, day, item_id, counted, staff_id, note=None) -> int:
    """Adjust the shelf to what was physically counted. Returns the variance (counted − system)."""
    system = levels(conn, item_id).get(SHELF, 0)
    variance = int(counted) - system
    label = f"Stock count: system {system}, counted {counted}" + (f" — {note}" if note else "")
    if variance < 0:
        move(conn, day, item_id, -variance, SHELF, UNEXPLAINED, "Missing at stock count", staff_id, note=label)
    elif variance > 0:
        move(conn, day, item_id, variance, UNEXPLAINED, SHELF, "Found at stock count", staff_id, note=label)
    return variance


# ── Reading stock ────────────────────────────────────────────────────────────────

def levels(conn, item_id) -> dict:
    rows = conn.execute(
        """SELECT loc, SUM(q) FROM (
               SELECT to_loc AS loc, quantity AS q FROM stock_movements WHERE item_id = ?
               UNION ALL SELECT from_loc, -quantity FROM stock_movements WHERE item_id = ?)
           GROUP BY loc""", (item_id, item_id)).fetchall()
    return {loc: int(q) for loc, q in rows if loc in HELD}


def levels_df(conn) -> pd.DataFrame:
    """One row per item: units on the shelf, in the faulty bin and with suppliers."""
    df = pd.read_sql(
        """SELECT item_id, loc, SUM(q) AS qty FROM (
               SELECT item_id, to_loc AS loc, quantity AS q FROM stock_movements
               UNION ALL SELECT item_id, from_loc, -quantity FROM stock_movements)
           WHERE loc IN ('shelf', 'faulty_bin', 'with_supplier') GROUP BY item_id, loc""", conn)
    wide = df.pivot(index="item_id", columns="loc", values="qty").reindex(columns=list(HELD)).fillna(0).astype(int)
    return wide.reset_index()
