"""Faulty bin & suppliers — get faulty stock back to suppliers and record what comes back."""
from datetime import date

import pandas as pd
import streamlit as st

from tracker import db, recovery, stock
from tracker.state import get_connection

conn = get_connection()
user = st.session_state.user
items = db.items(conn).set_index("id")
levels = stock.levels_df(conn)
moves = db.movements_df(conn)
claims = db.claims_df(conn)

st.title("♻️ Faulty bin & suppliers")
st.caption("Faulty units from swaps, repair comebacks, damaged deliveries and pre-sale tests collect here. "
           "Send them back to the supplier in one step, then record the replacement stock or credit.")
if flash := st.session_state.pop("bin_flash", None):
    st.success(flash)

# What's in the bin, and how long the oldest unit has been waiting
in_bin = levels[levels[stock.BIN] > 0].join(items, on="item_id")
in_bin = in_bin.assign(value=in_bin[stock.BIN] * in_bin["cost"])
last_sent = moves[moves["to_loc"] == stock.WITH_SUPPLIER].groupby("item_id")["moved_date"].max()
arrived = moves[moves["to_loc"] == stock.BIN][["item_id", "moved_date"]]
arrived = arrived[arrived["moved_date"] > arrived["item_id"].map(last_sent).fillna(pd.Timestamp.min)]
oldest = arrived.groupby("item_id")["moved_date"].min()
in_bin["oldest"] = in_bin["item_id"].map(oldest)
open_claims = claims[claims["status"] == "Sent to supplier"]

k1, k2, k3, k4 = st.columns(4)
k1.metric(f"In the faulty bin ({int(in_bin[stock.BIN].sum())} units)", f"€{in_bin['value'].sum():,.0f}")
k2.metric(f"Waiting on suppliers ({int(open_claims['quantity'].sum())} units)", f"€{open_claims['value'].sum():,.0f}")
closed = claims[claims["status"] == "Closed"]
k3.metric("Recovered", f"€{closed['recovered'].sum():,.0f}", help="Credit notes, refunds, replacement stock at cost")
k4.metric("Written off", f"€{closed.loc[closed['resolution'] == 'Rejected - written off', 'value'].sum():,.0f}",
          help="Rejected by the supplier")

bin_tab, waiting_tab, score_tab, history_tab = st.tabs(
    ["Faulty bin", "Waiting on suppliers", "Supplier scorecard", "Claim history"])

with bin_tab:
    if in_bin.empty:
        st.success("The faulty bin is empty.")
    for supplier, group in in_bin.groupby("supplier"):
        age = (pd.Timestamp(date.today()) - group["oldest"].min()).days
        with st.expander(f"**{supplier}** · {int(group[stock.BIN].sum())} units · €{group['value'].sum():,.0f}"
                         f" · oldest waiting {age} days", expanded=age > 30):
            if age > 30:
                st.warning("Some units have waited over 30 days. Suppliers often refuse old claims.", icon="⏳")
            st.dataframe(group.assign(item=group["label"])[["item", stock.BIN, "value", "oldest"]],
                         hide_index=True, width="stretch",
                         column_config={"item": "Item", stock.BIN: st.column_config.NumberColumn("Units"),
                                        "value": st.column_config.NumberColumn("Value", format="€%.2f"),
                                        "oldest": st.column_config.DateColumn("Oldest in bin", format="DD MMM YYYY")})
            a, b = st.columns([2, 1])
            rma = a.text_input("Supplier RMA / return reference", key=f"rma-{supplier}", max_chars=40,
                               placeholder="from the supplier's returns form")
            if b.button(f"Send all to {supplier}", key=f"send-{supplier}", type="primary"):
                stock.send_to_supplier(conn, date.today(), dict(zip(group["item_id"], group[stock.BIN])), user["id"],
                                       rma.strip() or None)
                conn.commit()
                st.session_state.bin_flash = (f"Sent {int(group[stock.BIN].sum())} units (€{group['value'].sum():,.0f}) "
                                              f"to {supplier}. Record their decision under Waiting on suppliers.")
                st.rerun()

with waiting_tab:
    if open_claims.empty:
        st.success("Nothing waiting on suppliers.")
    else:
        st.dataframe(open_claims[["id", "sent_date", "supplier", "rma_reference", "item", "quantity", "value"]],
                     hide_index=True, width="stretch",
                     column_config={"id": st.column_config.NumberColumn("#", width="small"),
                                    "sent_date": st.column_config.DateColumn("Sent", format="DD MMM YYYY"),
                                    "supplier": "Supplier", "rma_reference": "RMA ref", "item": "Item",
                                    "quantity": st.column_config.NumberColumn("Qty", width="small"),
                                    "value": st.column_config.NumberColumn("Value", format="€%.2f")})
        labels = {f"#{r.id} · {r.item} ×{r.quantity} · {r.supplier}": r for r in open_claims.itertuples()}
        choice = st.selectbox("Record the supplier's decision for", list(labels), index=None,
                              placeholder="Choose a claim")
        if choice:
            c = labels[choice]
            with st.container(border=True):
                resolution = st.radio("Supplier decision", stock.RESOLUTIONS, index=None, horizontal=True)
                a, b = st.columns(2)
                when = a.date_input("Date", value=date.today(), format="DD/MM/YYYY")
                qty = credit = None
                if resolution == "Replacement stock":
                    qty = b.number_input("Replacement units received", min_value=0, max_value=int(c.quantity),
                                         value=int(c.quantity))
                elif resolution in ("Credit note", "Refund"):
                    credit = b.number_input("Amount (€)", min_value=0.0, value=float(round(c.value, 2)), step=1.0)
                note = st.text_input("Note (optional)", max_chars=200)
                if st.button("Save decision", type="primary", disabled=resolution is None):
                    stock.close_claim(conn, int(c.id), resolution, when, user["id"], qty, credit, note.strip() or None)
                    conn.commit()
                    st.session_state.bin_flash = f"Claim #{c.id} closed: {resolution}."
                    st.rerun()

with score_tab:
    st.dataframe(recovery.by_supplier(claims), hide_index=True, width="stretch",
                 column_config={"supplier": "Supplier", "units_sent": "Units sent",
                                "value_sent": st.column_config.NumberColumn("Value sent", format="€%.0f"),
                                "accepted_rate": st.column_config.ProgressColumn("Accepted", format="percent",
                                                                                 min_value=0, max_value=1),
                                "avg_days_to_settle": st.column_config.NumberColumn("Days to settle", format="%.0f"),
                                "recovered": st.column_config.NumberColumn("Recovered", format="€%.0f"),
                                "still_open": st.column_config.NumberColumn("Still open", format="€%.0f")})
    st.caption("Accepted = settled with replacement stock, a credit note or a refund.")

with history_tab:
    st.dataframe(claims[["id", "sent_date", "supplier", "rma_reference", "item", "quantity", "value", "status",
                         "resolution", "recovered", "resolved_date", "staff", "notes"]],
                 hide_index=True, width="stretch", height=480,
                 column_config={"id": st.column_config.NumberColumn("#", width="small"),
                                "sent_date": st.column_config.DateColumn("Sent", format="DD MMM YYYY"),
                                "resolved_date": st.column_config.DateColumn("Settled", format="DD MMM YYYY"),
                                "value": st.column_config.NumberColumn("Value", format="€%.2f"),
                                "recovered": st.column_config.NumberColumn("Recovered", format="€%.2f"),
                                "supplier": "Supplier", "rma_reference": "RMA ref", "item": "Item",
                                "quantity": "Qty", "status": "Status", "resolution": "Outcome", "staff": "By",
                                "notes": "Notes"})
    st.download_button("Download as CSV", claims.to_csv(index=False).encode(), "supplier_claims.csv", "text/csv")
