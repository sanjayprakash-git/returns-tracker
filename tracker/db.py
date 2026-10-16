"""SQLite storage: schema, inserts and the queries the pages need."""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "returns.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY,
    category    TEXT NOT NULL CHECK (category IN ('Repair', 'New phone', 'Reconditioned phone', 'Accessory')),
    brand       TEXT NOT NULL,           -- Apple, Samsung, Google, OnePlus, or Universal for accessories
    device      TEXT,                    -- e.g. iPhone 13 (repairs and phones)
    subcategory TEXT,                    -- accessory group, e.g. Charging, Cases & protection
    name        TEXT NOT NULL,           -- part type for repairs (Screen), product name otherwise
    part_grade  TEXT,                    -- Genuine / Premium aftermarket / Standard aftermarket (repairs only)
    supplier    TEXT,
    price       REAL NOT NULL CHECK (price > 0),
    cost        REAL NOT NULL CHECK (cost >= 0)
);
CREATE TABLE IF NOT EXISTS staff (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    role    TEXT NOT NULL CHECK (role IN ('technician', 'sales', 'manager'))
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
    supplier_claim      INTEGER NOT NULL DEFAULT 0,
    out_of_policy       INTEGER NOT NULL DEFAULT 0,
    notes               TEXT
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_returns_date ON returns(return_date);
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
    df = pd.read_sql("SELECT * FROM items ORDER BY category, brand, device, name, part_grade", conn)
    df["label"] = df.apply(item_label, axis=1)
    return df


def staff(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT id, name, role FROM staff ORDER BY name", conn)


def add_return(conn, *, return_date, purchase_date, item_id, reason, outcome, staff_id,
               supplier_claim, out_of_policy, notes=None) -> int:
    days = (return_date - purchase_date).days
    cur = conn.execute(
        """INSERT INTO returns (return_date, purchase_date, days_since_purchase, item_id, reason,
                                outcome, staff_id, supplier_claim, out_of_policy, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (return_date.isoformat(), purchase_date.isoformat(), days, item_id, reason, outcome,
         staff_id, int(supplier_claim), int(out_of_policy), notes or None),
    )
    conn.commit()
    return cur.lastrowid


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
