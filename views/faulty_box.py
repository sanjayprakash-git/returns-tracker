"""Faulty box — send faulty stock back to suppliers and record what they give back."""
from datetime import date

import pandas as pd
import streamlit as st

from tracker import db, stock
from tracker.state import get_connection

conn = get_connection()
user = st.session_state.user
items = db.items(conn).set_index("id")
levels = stock.levels_df(conn)
moves = db.movements_df(conn)
claims = db.claims_df(conn)

st.title("♻️ Faulty box")
if flash := st.session_state.pop("box_flash", None):
    st.success(flash)

# What's in the box, and how long the oldest unit has waited since it went in
in_box = levels[levels[stock.BIN] > 0].join(items, on="item_id")
in_box = in_box.assign(value=in_box[stock.BIN] * in_box["cost"])
last_sent = moves[moves["to_loc"] == stock.WITH_SUPPLIER].groupby("item_id")["moved_date"].max()
arrived = moves[moves["to_loc"] == stock.BIN][["item_id", "moved_date"]]
arrived = arrived[arrived["moved_date"] > arrived["item_id"].map(last_sent).fillna(pd.Timestamp.min)]
in_box["oldest"] = in_box["item_id"].map(arrived.groupby("item_id")["moved_date"].min())
as_of = min(pd.Timestamp(date.today()), moves["moved_date"].max())  # latest activity (= today in a live shop)
waiting = claims[claims["status"] == "Sent to supplier"]
closed = claims[claims["status"] == "Closed"]

k1, k2, k3 = st.columns(3)
k1.metric(f"In the box ({int(in_box[stock.BIN].sum())} units)", f"€{in_box['value'].sum():,.0f}")
k2.metric(f"Sent back, waiting ({int(waiting['quantity'].sum())} units)", f"€{waiting['value'].sum():,.0f}")
k3.metric("Got back so far", f"€{closed['recovered'].sum():,.0f}", help="Credit, refunds and replacement stock (at cost)")

send_tab, waiting_tab, history_tab = st.tabs(["To send back", "Sent back, waiting", "History"])

with send_tab:
    if in_box.empty:
        st.success("The faulty box is empty.")
    for supplier, group in sorted(in_box.groupby("supplier"), key=lambda g: -g[1]["value"].sum()):
        age = (as_of - group["oldest"].min()).days
        flag = " ⏳" if age > 30 else ""
        with st.expander(f"**{supplier}** · {int(group[stock.BIN].sum())} units · €{group['value'].sum():,.0f}"
                         f" · oldest {age} days{flag}"):
            if age > 30:
                st.caption("⏳ Waiting over 30 days. Suppliers often refuse old claims, so send these soon.")
            st.dataframe(group.assign(item=group["label"])[["item", stock.BIN, "value"]], hide_index=True,
                         width="stretch",
                         column_config={"item": "Item", stock.BIN: st.column_config.NumberColumn("Units"),
                                        "value": st.column_config.NumberColumn("Value", format="€%.2f")})
            a, b = st.columns([2, 1])
            ref = a.text_input("Supplier's return reference (RMA)", key=f"rma-{supplier}", max_chars=40,
                               placeholder="optional")
            if b.button("Send back", key=f"send-{supplier}", type="primary", width="stretch"):
                stock.send_to_supplier(conn, date.today(), dict(zip(group["item_id"], group[stock.BIN])), user["id"],
                                       ref.strip() or None)
                conn.commit()
                st.session_state.box_flash = (f"Sent {int(group[stock.BIN].sum())} units back to {supplier}. "
                                              "When they reply, record it under Sent back, waiting.")
                st.rerun()

with waiting_tab:
    if waiting.empty:
        st.success("Nothing waiting on suppliers.")
    else:
        labels = {f"{r.supplier} · {r.item} ×{r.quantity} · sent {r.sent_date:%d %b}": r for r in waiting.itertuples()}
        choice = st.selectbox("Supplier replied about", list(labels), index=None, placeholder="Choose what they replied about")
        if choice:
            c = labels[choice]
            with st.container(border=True):
                answer = st.segmented_control("What did they give back?", ["New stock", "Credit / refund", "Refused"],
                                              default="New stock")
                qty = credit = None
                if answer == "New stock":
                    qty = st.number_input("Units received", min_value=0, max_value=int(c.quantity), value=int(c.quantity))
                    resolution = "Replacement stock"
                elif answer == "Credit / refund":
                    credit = st.number_input("Amount (€)", min_value=0.0, value=float(round(c.value, 2)), step=1.0)
                    resolution = "Credit note"
                else:
                    keep = st.radio("What will you do with them?", ["Write off", "Repair and resell"], horizontal=True)
                    resolution = "Rejected - written off" if keep == "Write off" else "Rejected - repaired & resold"
                if st.button("Save", type="primary", disabled=answer is None):
                    stock.close_claim(conn, int(c.id), resolution, date.today(), user["id"], qty, credit)
                    conn.commit()
                    st.session_state.box_flash = f"Saved: {c.supplier} — {answer.lower()}."
                    st.rerun()
        st.dataframe(waiting[["sent_date", "supplier", "item", "quantity", "value", "rma_reference"]],
                     hide_index=True, width="stretch",
                     column_config={"sent_date": st.column_config.DateColumn("Sent", format="DD MMM"),
                                    "supplier": "Supplier", "item": "Item", "quantity": "Units",
                                    "value": st.column_config.NumberColumn("Value", format="€%.2f"),
                                    "rma_reference": "Reference"})

with history_tab:
    st.markdown("**Everything sent back**")
    st.dataframe(claims[["sent_date", "supplier", "item", "quantity", "value", "resolution", "recovered",
                         "resolved_date"]],
                 hide_index=True, width="stretch", height=380,
                 column_config={"sent_date": st.column_config.DateColumn("Sent", format="DD MMM YYYY"),
                                "resolved_date": st.column_config.DateColumn("Replied", format="DD MMM YYYY"),
                                "supplier": "Supplier", "item": "Item", "quantity": "Units",
                                "value": st.column_config.NumberColumn("Value", format="€%.2f"),
                                "resolution": "Result",
                                "recovered": st.column_config.NumberColumn("Got back", format="€%.2f")})
