"""Loss & recovery: where faulty and missing stock went, and how much money came back."""
import pandas as pd

from tracker import stock

INTO_BIN = {"Faulty unit returned": "Customer swap / refund", "Faulty part removed (comeback)": "Repair comeback",
            "Damaged on delivery": "Damaged on delivery", "Found faulty on the shelf": "Failed pre-sale test",
            "Old faulty box counted at go-live": "Old faulty box (pre-app)"}


def _value(df):
    return df["quantity"] * df["cost"]


def summary(moves, claims, levels, items) -> dict:
    """Headline money: faulty, recovered, still to recover, written off, unexplained."""
    m = moves.assign(value=_value(moves))
    faulty = m[m["to_loc"] == stock.BIN]
    cost = items.set_index("id")["cost"]
    held = levels.set_index("item_id")
    pending_bin = float((held[stock.BIN].clip(lower=0) * cost.reindex(held.index)).sum())
    pending_sup = float((held[stock.WITH_SUPPLIER].clip(lower=0) * cost.reindex(held.index)).sum())
    closed = claims[claims["status"] == "Closed"]
    written_off = float(closed.loc[closed["resolution"] == "Rejected - written off", "value"].sum())
    missing = float(m.loc[m["to_loc"] == stock.UNEXPLAINED, "value"].sum())
    found = float(m.loc[m["from_loc"] == stock.UNEXPLAINED, "value"].sum())   # found on shelf or in the old box
    return {
        "faulty_value": float(faulty["value"].sum()),
        "faulty_units": int(faulty["quantity"].sum()),
        "recovered": float(closed["recovered"].sum()),
        "in_bin": pending_bin,
        "with_suppliers": pending_sup,
        "written_off": written_off,
        "unexplained": max(missing - found, 0.0),
    }


def by_product(moves, claims, sales, levels, since=None) -> pd.DataFrame:
    """Per product/part: units sold, fault rate, faulty value, recovered, still pending, written off."""
    m = moves.assign(value=_value(moves))
    if since is not None:
        m = m[m["moved_date"] >= pd.Timestamp(since)]
        sales = sales[sales["sale_date"] >= pd.Timestamp(since)]
        claims = claims[claims["sent_date"] >= pd.Timestamp(since)]
    faulty = m[m["to_loc"] == stock.BIN].groupby("item").agg(faulty_units=("quantity", "sum"),
                                                              faulty_value=("value", "sum"))
    customer = m[(m["to_loc"] == stock.BIN) & (m["from_loc"] == stock.CUSTOMER)].groupby("item")["quantity"].sum()
    sold = sales.groupby("item")["quantity"].sum()
    closed = claims[claims["status"] == "Closed"]
    rec = closed.groupby("item")["recovered"].sum()
    off = closed[closed["resolution"] == "Rejected - written off"].groupby("item")["value"].sum()
    meta = m.drop_duplicates("item").set_index("item")[["category", "subcategory", "supplier", "cost", "item_id"]]
    df = faulty.join(meta).join(sold.rename("sold")).join(customer.rename("customer_faults"))
    df = df.join(rec.rename("recovered")).join(off.rename("written_off")).fillna(0)
    held = levels.set_index("item_id")
    df["pending"] = [(held.at[i, stock.BIN] + held.at[i, stock.WITH_SUPPLIER]) * c if i in held.index else 0
                     for i, c in zip(df["item_id"], df["cost"])]
    df["fault_rate"] = (df["customer_faults"] / df["sold"].where(df["sold"] > 0)).fillna(0)
    df["recovery_rate"] = (df["recovered"] / df["faulty_value"].where(df["faulty_value"] > 0)).fillna(0)
    return df.reset_index().sort_values("faulty_value", ascending=False)


def by_supplier(claims) -> pd.DataFrame:
    if claims.empty:
        return pd.DataFrame()
    c = claims.assign(
        closed=claims["status"] == "Closed",
        accepted=(claims["status"] == "Closed") & ~claims["resolution"].str.startswith("Rejected", na=False),
        days=(claims["resolved_date"] - claims["sent_date"]).dt.days,
        open_value=claims["value"].where(claims["status"] != "Closed", 0),
    )
    g = c.groupby("supplier")
    df = pd.DataFrame({
        "units_sent": g["quantity"].sum(),
        "value_sent": g["value"].sum(),
        "accepted_rate": g["accepted"].sum() / g["closed"].sum().replace(0, float("nan")),
        "avg_days_to_settle": g["days"].mean(),
        "recovered": g["recovered"].sum(),
        "still_open": g["open_value"].sum(),
    })
    return df.reset_index().sort_values("value_sent", ascending=False)


def sources(moves) -> pd.DataFrame:
    """How units ended up in the faulty bin."""
    m = moves[moves["to_loc"] == stock.BIN].assign(value=lambda d: d["quantity"] * d["cost"])
    m = m.assign(source=m["reason"].map(INTO_BIN).fillna(m["reason"]))
    return m.groupby("source").agg(units=("quantity", "sum"), value=("value", "sum")).reset_index() \
        .sort_values("value", ascending=False)


def monthly(moves, claims) -> pd.DataFrame:
    """Per month: value missing at counts, faulty value recorded, value recovered (by date settled)."""
    m = moves.assign(value=_value(moves), month=moves["moved_date"].dt.to_period("M"))
    rows = {
        "Recorded as faulty": m[m["to_loc"] == stock.BIN].groupby("month")["value"].sum(),
        "Missing at stock count": m[m["to_loc"] == stock.UNEXPLAINED].groupby("month")["value"].sum(),
    }
    closed = claims[claims["status"] == "Closed"]
    rows["Got back from suppliers"] = closed.groupby(closed["resolved_date"].dt.to_period("M"))["recovered"].sum()
    df = pd.DataFrame(rows).fillna(0)
    df.index = df.index.to_timestamp()
    return df.reset_index(names="month").melt("month", var_name="series", value_name="value")


def insights(moves, claims, sales, levels, items, go_live, today) -> list[str]:
    out = []
    m = moves.assign(value=_value(moves))
    gl = pd.Timestamp(go_live)
    count = m[(m["moved_date"] == gl) & (m["to_loc"] == stock.UNEXPLAINED)]
    box = m[m["reason"] == "Old faulty box counted at go-live"]
    if len(count):
        parts = count[count["category"] == "Repair"]
        out.append(
            f"**Go-live stock count ({gl:%d %b}):** {int(count['quantity'].sum())} units (€{count['value'].sum():,.0f}) "
            f"were missing from the shelf. The old faulty box explained {int(box['quantity'].sum())} of them "
            f"(swaps done at the counter but never recorded), and {int(parts['quantity'].sum())} were repair parts "
            f"used but never deducted (€{parts['value'].sum():,.0f}).")
    first = claims[claims["sent_date"] == claims["sent_date"].min()] if len(claims) else claims
    later = claims[claims["sent_date"] > claims["sent_date"].min()] if len(claims) else claims
    acc = lambda c: (~c.loc[c["status"] == "Closed", "resolution"].str.startswith("Rejected")).mean()
    if len(first) and len(later):
        lost = first.loc[first["resolution"] == "Rejected - written off", "value"].sum()
        out.append(f"Suppliers accepted only **{acc(first):.0%}** of the old faulty box (too old, no proof of date), "
                   f"so **€{lost:,.0f}** was written off. Since go-live, faulty stock goes back monthly and "
                   f"**{acc(later):.0%}** is accepted.")
    after = m[(m["moved_date"] > gl) & (m["to_loc"] == stock.UNEXPLAINED)]
    out.append(f"Month-end counts since go-live: only **{int(after['quantity'].sum())} units "
               f"(€{after['value'].sum():,.0f})** missing, against €{count['value'].sum():,.0f} at go-live.")
    prod = by_product(moves, claims, sales, levels, since=go_live)
    prod = prod[(prod["category"] == "Accessory") & (prod["sold"] >= 30)].sort_values("fault_rate", ascending=False)
    if len(prod):
        w = prod.iloc[0]
        out.append(f"**{w['item'].split(' · ')[-1]}** fail most: **{w['fault_rate']:.0%}** of units sold since go-live "
                   f"came back faulty (€{w['faulty_value']:,.0f} at cost). Use the numbers with **{w['supplier']}**: "
                   "ask for a faulty allowance or credit, or change product.")
    held = levels.set_index("item_id")
    cost = items.set_index("id")["cost"]
    bin_units = int(held[stock.BIN].clip(lower=0).sum())
    if bin_units:
        bin_value = float((held[stock.BIN].clip(lower=0) * cost.reindex(held.index)).sum())
        out.append(f"**{bin_units} units (€{bin_value:,.0f})** are in the faulty box now. Send them back this month.")
    return out
