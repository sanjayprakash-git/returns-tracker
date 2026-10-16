"""Page 4 — faulty stock and supplier claims (US-13 to US-16)."""
from datetime import date

import streamlit as st

from tracker import analytics, db
from tracker.state import get_connection

conn = get_connection()
claims = db.claims_df(conn)
items = db.items(conn)

st.title("📦 Supplier claims")
if flash := st.session_state.pop("claims_flash", None):
    st.success(flash)
st.caption("Every faulty unit, from the faulty-stock shelf back to the supplier, until you get replacement stock, "
           "a credit note or a refund. Customer returns marked for a claim appear here automatically.")

s = analytics.claim_summary(claims)
k1, k2, k3, k4 = st.columns(4)
k1.metric("In faulty stock", f"€{s['in_faulty_stock']:,.0f}", help="Faulty units on the shelf, not yet sent (at cost)")
k2.metric("With suppliers", f"€{s['with_suppliers']:,.0f}", help="Sent and waiting for the supplier's decision")
k3.metric("Recovered", f"€{s['recovered']:,.0f}", help="Credit notes, refunds, and replacement stock at cost")
k4.metric("Rejected", f"€{s['rejected']:,.0f}", help="Claims the supplier refused (written off, used for parts or resold)")

notes = analytics.claim_insights(claims, date.today())
if notes:
    with st.container(border=True):
        for line in notes:
            st.markdown(f"- {line}")

tab_open, tab_new, tab_score, tab_all = st.tabs(["Open claims", "Log damaged delivery", "Supplier scorecard", "All claims"])

cols = {"id": st.column_config.NumberColumn("#", width="small"),
        "created_date": st.column_config.DateColumn("Logged", format="DD MMM YYYY"),
        "sent_date": st.column_config.DateColumn("Sent", format="DD MMM YYYY"),
        "resolved_date": st.column_config.DateColumn("Closed", format="DD MMM YYYY"),
        "value": st.column_config.NumberColumn("Value", format="€%.2f"),
        "recovered": st.column_config.NumberColumn("Recovered", format="€%.2f"),
        "quantity": st.column_config.NumberColumn("Qty", width="small"),
        "item": "Item", "supplier": "Supplier", "source": "Source", "problem": "Problem",
        "status": "Status", "rma_reference": "RMA ref", "resolution": "Outcome", "notes": "Notes"}

with tab_open:
    waiting = claims[claims["status"] == "In faulty stock"]
    sent = claims[claims["status"] == "Sent to supplier"]
    st.markdown(f"**On the faulty-stock shelf** · {len(waiting)} claims · €{waiting['value'].sum():,.0f}")
    st.dataframe(waiting[["id", "created_date", "source", "item", "quantity", "supplier", "problem", "value"]],
                 hide_index=True, width="stretch", column_config=cols)
    st.markdown(f"**Sent, waiting for the supplier** · {len(sent)} claims · €{sent['value'].sum():,.0f}")
    st.dataframe(sent[["id", "sent_date", "item", "quantity", "supplier", "rma_reference", "problem", "value"]],
                 hide_index=True, width="stretch", column_config=cols)

    st.subheader("Update a claim")
    open_claims = claims[claims["status"] != "Closed"]
    if open_claims.empty:
        st.success("No open claims.")
    else:
        labels = {f"#{r.id} · {r.item} ×{r.quantity} · {r.supplier} · {r.status}": r for r in open_claims.itertuples()}
        choice = st.selectbox("Claim", list(labels), index=None, placeholder="Choose an open claim")
        if choice:
            c = labels[choice]
            with st.container(border=True):
                if c.status == "In faulty stock":
                    a, b = st.columns(2)
                    sent_on = a.date_input("Date sent to supplier", value=date.today(), format="DD/MM/YYYY")
                    rma = b.text_input("Supplier RMA / reference number", max_chars=40, placeholder="e.g. RMA-48213")
                    if st.button("Mark as sent", type="primary"):
                        db.mark_claim_sent(conn, int(c.id), sent_on, rma)
                        st.session_state.claims_flash = f"Claim #{c.id} marked as sent to {c.supplier}."
                        st.rerun()
                else:
                    resolution = st.radio("What did the supplier do?", db.RESOLUTIONS, horizontal=True, index=None)
                    a, b = st.columns(2)
                    resolved_on = a.date_input("Date", value=date.today(), format="DD/MM/YYYY")
                    qty = credit = None
                    if resolution == "Replacement stock":
                        qty = b.number_input("Replacement units received", min_value=0, max_value=int(c.quantity),
                                             value=int(c.quantity))
                    elif resolution in ("Credit note", "Refund"):
                        credit = b.number_input("Amount (€)", min_value=0.0, value=float(round(c.value, 2)), step=1.0)
                    note = st.text_input("Notes (optional)", max_chars=200)
                    if st.button("Close claim", type="primary", disabled=resolution is None):
                        db.close_claim(conn, int(c.id), resolution, resolved_on, qty, credit, note)
                        st.session_state.claims_flash = f"Claim #{c.id} closed: {resolution}."
                        st.rerun()

with tab_new:
    st.markdown("For stock that arrives damaged, or fails testing before it's sold. No customer involved.")
    with st.container(border=True):
        a, b = st.columns(2)
        source = a.radio("What happened?", ["Damaged on delivery", "Found faulty in stock"], horizontal=True)
        when = b.date_input("Date", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
        kind = a.selectbox("Stock type", ["Accessory", "Repair part", "New phone", "Reconditioned phone"])
        pool = items[items["category"] == ("Repair" if kind == "Repair part" else kind)]
        if kind == "Accessory":
            group = b.selectbox("Accessory type", sorted(pool["subcategory"].unique()))
            pool = pool[pool["subcategory"] == group]
        item = a.selectbox("Item", pool["label"], index=None, placeholder="Search or choose")
        qty = b.number_input("Quantity affected", min_value=1, max_value=500, value=1)
        problem = a.selectbox("Problem", db.CLAIM_PROBLEMS[source])
        note = b.text_input("Notes (optional)", max_chars=200, placeholder="e.g. 3 boxes crushed in delivery #4471")
        if item:
            row = pool[pool["label"] == item].iloc[0]
            st.caption(f"Supplier: **{row['supplier']}** · value at cost: **€{row['cost'] * qty:,.2f}**")
        if st.button("Add to faulty stock", type="primary", disabled=item is None):
            new_id = db.add_claim(conn, created_date=when, source=source,
                                  item_id=int(pool.loc[pool["label"] == item, "id"].iloc[0]),
                                  quantity=int(qty), problem=problem, notes=note.strip())
            st.session_state.claims_flash = (f"Claim #{new_id} added to faulty stock: {item} ×{qty}. "
                                             "Send it from the Open claims tab.")
            st.rerun()

with tab_score:
    card = analytics.supplier_scorecard(claims)
    st.dataframe(
        card, hide_index=True, width="stretch",
        column_config={
            "supplier": "Supplier", "claims": "Claims", "units": "Units",
            "accepted_rate": st.column_config.ProgressColumn("Accepted", format="percent", min_value=0, max_value=1),
            "avg_days_to_resolve": st.column_config.NumberColumn("Avg days to settle", format="%.0f"),
            "recovered": st.column_config.NumberColumn("Recovered", format="€%.0f"),
            "still_open": st.column_config.NumberColumn("Still open", format="€%.0f"),
        },
    )
    st.caption("Accepted = closed claims settled with replacement stock, a credit note or a refund. "
               "Days to settle = from sending to the supplier's decision.")

with tab_all:
    f1, f2, f3 = st.columns(3)
    status_f = f1.multiselect("Status", ["In faulty stock", "Sent to supplier", "Closed"], placeholder="All")
    source_f = f2.multiselect("Source", list(db.CLAIM_PROBLEMS), placeholder="All sources")
    supplier_f = f3.multiselect("Supplier", sorted(claims["supplier"].unique()), placeholder="All suppliers")
    view = claims
    for col, chosen in [("status", status_f), ("source", source_f), ("supplier", supplier_f)]:
        if chosen:
            view = view[view[col].isin(chosen)]
    table = view[["id", "created_date", "source", "item", "quantity", "supplier", "problem", "status",
                  "rma_reference", "resolution", "value", "recovered", "resolved_date", "notes"]]
    st.dataframe(table, hide_index=True, width="stretch", height=480, column_config=cols)
    st.download_button("Download as CSV", table.to_csv(index=False).encode(), "supplier_claims.csv", "text/csv")
