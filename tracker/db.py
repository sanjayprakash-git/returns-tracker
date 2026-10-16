"""SQLite storage: schema, inserts and the queries the pages need."""
import sqlite3
from pathlib import Path

import pandas as pd

from tracker import stock

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "returns.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY,
    category    TEXT NOT NULL CHECK (category IN ('Repair', 'New phone', 'Reconditioned phone', 'Accessory')),
    brand       TEXT NOT NULL,           -- Apple, Samsung, Google, OnePlus, or Universal for accessories
    device      TEXT,                    -- e.g. iPhone 13 (repairs and phones)
    subcategory TEXT,                    -- product group, e.g. Audio, Gaming, Toys & gadgets
    name        TEXT NOT NULL,           -- part type for repairs (Screen), product name otherwise
    part_grade  TEXT,                    -- Genuine / Premium aftermarket / Standard aftermarket (repair parts)
    supplier    TEXT,
    warranty_days INTEGER,               -- 90 repairs, 180 reconditioned, 30 or 90 products
    price       REAL NOT NULL CHECK (price > 0),
    cost        REAL NOT NULL CHECK (cost >= 0),
    reorder_level INTEGER NOT NULL DEFAULT 2
);
CREATE TABLE IF NOT EXISTS staff (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    role    TEXT NOT NULL CHECK (role IN ('technician', 'sales', 'manager')),
    username      TEXT UNIQUE,
    password_hash TEXT
);
CREATE TABLE IF NOT EXISTS sales (               -- repair jobs and product sales
    id          INTEGER PRIMARY KEY,
    sale_date   TEXT NOT NULL,
    item_id     INTEGER NOT NULL REFERENCES items(id),
    staff_id    INTEGER NOT NULL REFERENCES staff(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0)
);
CREATE TABLE IF NOT EXISTS returns (             -- repair comebacks and product returns
    id                  INTEGER PRIMARY KEY,
    return_date         TEXT NOT NULL,
    purchase_date       TEXT NOT NULL,
    days_since_purchase INTEGER NOT NULL CHECK (days_since_purchase >= 0),
    item_id             INTEGER NOT NULL REFERENCES items(id),
    reason              TEXT NOT NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('Re-repair (free)', 'Refund', 'Exchange', 'Store credit', 'Declined')),
    staff_id            INTEGER NOT NULL REFERENCES staff(id),
    supplier_claim      INTEGER NOT NULL DEFAULT 0,   -- faulty unit kept for the supplier (goes into the faulty bin)
    out_of_policy       INTEGER NOT NULL DEFAULT 0,
    notes               TEXT
);
CREATE TABLE IF NOT EXISTS supplier_claims (     -- faulty units sent back to a supplier (RMA)
    id              INTEGER PRIMARY KEY,
    sent_date       TEXT NOT NULL,
    item_id         INTEGER NOT NULL REFERENCES items(id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    rma_reference   TEXT,
    status          TEXT NOT NULL DEFAULT 'Sent to supplier' CHECK (status IN ('Sent to supplier', 'Closed')),
    resolution      TEXT CHECK (resolution IN ('Replacement stock', 'Credit note', 'Refund', 'Rejected - written off',
                                               'Rejected - repaired & resold')),
    replacement_qty INTEGER,
    credit_value    REAL,
    resolved_date   TEXT,
    staff_id        INTEGER REFERENCES staff(id),
    notes           TEXT
);
CREATE TABLE IF NOT EXISTS stock_movements (     -- every unit that moves, who moved it and why
    id          INTEGER PRIMARY KEY,
    moved_date  TEXT NOT NULL,
    item_id     INTEGER NOT NULL REFERENCES items(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    from_loc    TEXT NOT NULL,
    to_loc      TEXT NOT NULL,
    reason      TEXT NOT NULL,
    staff_id    INTEGER REFERENCES staff(id),
    return_id   INTEGER REFERENCES returns(id),
    claim_id    INTEGER REFERENCES supplier_claims(id),
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_returns_date ON returns(return_date);
CREATE INDEX IF NOT EXISTS idx_moves_item ON stock_movements(item_id, moved_date);
"""

LABOUR_COST = 15.0  # technician time for a free re-repair, EUR


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)  # shared across Streamlit sessions
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0


def item_label(row) -> str:
    if row["category"] == "Repair":
        return f"{row['device']} · {row['name']} · {row['part_grade']}"
    if row["device"]:
        return f"{row['device']} · {row['name']}"
    return f"{row['subcategory']} · {row['name']}" if row["subcategory"] else row["name"]


def items(conn) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM items ORDER BY category, brand, device, subcategory, name, part_grade", conn)
    df["label"] = df.apply(item_label, axis=1)
    return df


def staff(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT id, name, role, username FROM staff ORDER BY name", conn)


def add_return(conn, *, return_date, purchase_date, item_id, reason, outcome, staff_id,
               supplier_claim, out_of_policy, notes=None, category=None, commit=True) -> int:
    """Record a return and the stock it moves (faulty unit to the bin, replacement off the shelf)."""
    days = (return_date - purchase_date).days
    cur = conn.execute(
        """INSERT INTO returns (return_date, purchase_date, days_since_purchase, item_id, reason,
                                outcome, staff_id, supplier_claim, out_of_policy, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (return_date.isoformat(), purchase_date.isoformat(), days, item_id, reason, outcome,
         staff_id, int(supplier_claim), int(out_of_policy), notes or None),
    )
    if category is None:
        category = conn.execute("SELECT category FROM items WHERE id = ?", (item_id,)).fetchone()[0]
    stock.record_return(conn, return_date, item_id, category, reason, outcome, staff_id,
                        faulty=bool(supplier_claim), return_id=cur.lastrowid)
    if commit:
        conn.commit()
    return cur.lastrowid


def claims_df(conn) -> pd.DataFrame:
    df = pd.read_sql(
        """SELECT c.*, i.category, i.subcategory, i.brand, i.device, i.name, i.part_grade, i.supplier, i.cost,
                  s.name AS staff
           FROM supplier_claims c JOIN items i ON i.id = c.item_id LEFT JOIN staff s ON s.id = c.staff_id
           ORDER BY c.sent_date DESC, c.id DESC""",
        conn,
    )
    for col in ("sent_date", "resolved_date"):
        df[col] = pd.to_datetime(df[col])
    df["item"] = df.apply(item_label, axis=1) if len(df) else ""
    df["value"] = df["cost"] * df["quantity"]  # what the faulty stock cost us
    resold = df["resolution"] == "Rejected - repaired & resold"
    # value recovered: credit/refund amount, replacement units at cost, or units repaired and resold
    df["recovered"] = (df["credit_value"].fillna(0) + df["replacement_qty"].fillna(0) * df["cost"]
                       + df["value"].where(resold, 0))
    df["notes"] = df["notes"].fillna("")
    df["rma_reference"] = df["rma_reference"].fillna("")
    return df


def movements_df(conn) -> pd.DataFrame:
    df = pd.read_sql(
        """SELECT m.id, m.moved_date, m.item_id, m.quantity, m.from_loc, m.to_loc, m.reason, m.note,
                  m.return_id, m.claim_id, s.name AS staff,
                  i.category, i.subcategory, i.brand, i.device, i.name, i.part_grade, i.supplier, i.cost
           FROM stock_movements m JOIN items i ON i.id = m.item_id LEFT JOIN staff s ON s.id = m.staff_id
           ORDER BY m.moved_date DESC, m.id DESC""",
        conn,
    )
    df["moved_date"] = pd.to_datetime(df["moved_date"])
    df["item"] = df.apply(item_label, axis=1) if len(df) else ""
    df["staff"] = df["staff"].fillna("—")
    df["note"] = df["note"].fillna("")
    return df


def return_cost(df: pd.DataFrame) -> pd.Series:
    """What each return cost the shop: a new part + labour, the refund, or a replacement."""
    cost = pd.Series(0.0, index=df.index)
    rerepair = df["outcome"] == "Re-repair (free)"
    refund = df["outcome"].isin(["Refund", "Store credit"])
    exchange = df["outcome"] == "Exchange"
    cost[rerepair] = df.loc[rerepair, "cost"] + LABOUR_COST
    cost[refund] = df.loc[refund, "price"]
    cost[exchange] = df.loc[exchange, "cost"]
    return cost


def returns_df(conn) -> pd.DataFrame:
    df = pd.read_sql(
        """SELECT r.id, r.return_date, r.purchase_date, r.days_since_purchase,
                  i.category, i.subcategory, i.brand, i.device, i.name, i.part_grade, i.supplier,
                  i.price, i.cost, r.reason, r.outcome, s.name AS staff, r.supplier_claim, r.out_of_policy, r.notes
           FROM returns r
           JOIN items i ON i.id = r.item_id
           JOIN staff s ON s.id = r.staff_id
           ORDER BY r.return_date DESC, r.id DESC""",
        conn,
    )
    df["return_date"] = pd.to_datetime(df["return_date"])
    df["purchase_date"] = pd.to_datetime(df["purchase_date"])
    df["supplier_claim"] = df["supplier_claim"].astype(bool)
    df["out_of_policy"] = df["out_of_policy"].astype(bool)
    df["notes"] = df["notes"].fillna("")
    df["item"] = df.apply(item_label, axis=1) if len(df) else ""
    df["return_cost"] = return_cost(df) if len(df) else 0.0
    return df


def sales_df(conn) -> pd.DataFrame:
    df = pd.read_sql(
        """SELECT sa.sale_date, i.category, i.subcategory, i.brand, i.device, i.name, i.part_grade, i.supplier,
                  i.price, sa.quantity
           FROM sales sa JOIN items i ON i.id = sa.item_id""",
        conn,
    )
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    df["item"] = df.apply(item_label, axis=1) if len(df) else ""
    return df
