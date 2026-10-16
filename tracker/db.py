"""SQLite storage: schema, inserts and the queries the pages need."""
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "returns.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id      INTEGER PRIMARY KEY,
    model   TEXT NOT NULL UNIQUE,
    series  TEXT NOT NULL CHECK (series IN ('A-series', 'S-series')),
    price   REAL NOT NULL CHECK (price > 0)
);
CREATE TABLE IF NOT EXISTS staff (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    role    TEXT NOT NULL CHECK (role IN ('staff', 'manager'))
);
CREATE TABLE IF NOT EXISTS sales (
    id          INTEGER PRIMARY KEY,
    sale_date   TEXT NOT NULL,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    staff_id    INTEGER NOT NULL REFERENCES staff(id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0)
);
CREATE TABLE IF NOT EXISTS returns (
    id                  INTEGER PRIMARY KEY,
    return_date         TEXT NOT NULL,
    purchase_date       TEXT NOT NULL,
    days_since_purchase INTEGER NOT NULL CHECK (days_since_purchase >= 0),
    product_id          INTEGER NOT NULL REFERENCES products(id),
    reason              TEXT NOT NULL,
    condition           TEXT NOT NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('Refund', 'Exchange', 'Repair')),
    staff_id            INTEGER NOT NULL REFERENCES staff(id),
    out_of_policy       INTEGER NOT NULL DEFAULT 0,
    notes               TEXT
);
CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_returns_date ON returns(return_date);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)  # shared across Streamlit sessions
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0


def products(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT id, model, series, price FROM products ORDER BY series, price", conn)


def staff(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT id, name, role FROM staff ORDER BY name", conn)


def add_return(conn, *, return_date, purchase_date, product_id, reason, condition,
               outcome, staff_id, out_of_policy, notes=None) -> int:
    days = (return_date - purchase_date).days
    cur = conn.execute(
        """INSERT INTO returns (return_date, purchase_date, days_since_purchase, product_id,
                                reason, condition, outcome, staff_id, out_of_policy, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (return_date.isoformat(), purchase_date.isoformat(), days, product_id, reason,
         condition, outcome, staff_id, int(out_of_policy), notes or None),
    )
    conn.commit()
    return cur.lastrowid


def returns_df(conn) -> pd.DataFrame:
    df = pd.read_sql(
        """SELECT r.id, r.return_date, r.purchase_date, r.days_since_purchase,
                  p.model, p.series, p.price, r.reason, r.condition, r.outcome,
                  s.name AS staff, r.out_of_policy, r.notes
           FROM returns r
           JOIN products p ON p.id = r.product_id
           JOIN staff s ON s.id = r.staff_id
           ORDER BY r.return_date DESC, r.id DESC""",
        conn,
    )
    df["return_date"] = pd.to_datetime(df["return_date"])
    df["purchase_date"] = pd.to_datetime(df["purchase_date"])
    df["out_of_policy"] = df["out_of_policy"].astype(bool)
    df["notes"] = df["notes"].fillna("")
    return df


def sales_df(conn) -> pd.DataFrame:
    df = pd.read_sql(
        """SELECT sa.sale_date, p.model, p.series, p.price, sa.quantity
           FROM sales sa JOIN products p ON p.id = sa.product_id""",
        conn,
    )
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    return df
