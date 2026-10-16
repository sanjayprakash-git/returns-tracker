"""Stock — where every unit is, stock counts, and the trail of who moved what."""
from datetime import date

import streamlit as st

from tracker import db, stock
from tracker.state import get_connection

conn = get_connection()
user = st.session_state.user
items = db.items(conn)
levels = stock.levels_df(conn)
table = items.merge(levels, left_on="id", right_on="item_id", how="left").fillna(
    {stock.SHELF: 0, stock.BIN: 0, stock.WITH_SUPPLIER: 0})

st.title("📦 Stock")
if flash := st.session_state.pop("stock_flash", None):
    st.success(flash)

GROUP_ORDER = ["Audio", "Smartwatches", "Gaming", "Toys & gadgets", "Charging", "Power banks",
               "Cases & protection", "Phones", "Repair parts"]

levels_tab, count_tab, history_tab = st.tabs(["Stock levels", "Stock count", "Movement history"])

with levels_tab:
    f1, f2, f3 = st.columns([1.4, 1.4, 1])
    groups = f1.multiselect("Group", GROUP_ORDER, placeholder="All groups")
    search = f2.text_input("Search", placeholder="e.g. earbuds, iPhone 13 screen")
    only_low = f3.toggle("Only low stock")
    only_bin = f3.toggle("Only with faulty units")
    view = table
    if groups:
        view = view[view["subcategory"].isin(groups)]
    if search:
        words = search.lower().split()
        view = view[view["label"].str.lower().apply(lambda s: all(w in s for w in words))]
    view = view.assign(low=view[stock.SHELF] <= view["reorder_level"],
                       faulty_value=view[stock.BIN] * view["cost"])
    if only_low:
        view = view[view["low"]]
    if only_bin:
        view = view[view[stock.BIN] > 0]
    k1, k2, k3 = st.columns(3)
    k1.metric("Units on the shelf", f"{int(view[stock.SHELF].sum()):,}")
    k2.metric("Units in the faulty bin", f"{int(view[stock.BIN].sum()):,}",
              help="Faulty units waiting to go back to the supplier")
    k3.metric("Faulty bin value", f"€{view['faulty_value'].sum():,.0f}")
    st.dataframe(
        view[["label", "subcategory", "supplier", stock.SHELF, "reorder_level", "low", stock.BIN,
              stock.WITH_SUPPLIER, "faulty_value"]].sort_values([stock.BIN, "label"], ascending=[False, True]),
        hide_index=True, width="stretch", height=480,
        column_config={"label": "Item", "subcategory": "Group", "supplier": "Supplier",
                       stock.SHELF: st.column_config.NumberColumn("On shelf"),
                       "reorder_level": st.column_config.NumberColumn("Reorder at"),
                       "low": st.column_config.CheckboxColumn("Low"),
                       stock.BIN: st.column_config.NumberColumn("Faulty bin"),
                       stock.WITH_SUPPLIER: st.column_config.NumberColumn("With supplier"),
                       "faulty_value": st.column_config.NumberColumn("Faulty value", format="€%.2f")})

with count_tab:
    st.markdown("Count what's physically on the shelf. The app compares it with the system and records any "
                "difference with your name, so missing stock is never just \"gone\".")
    with st.container(border=True):
        a, b = st.columns([1, 2])
        group = a.selectbox("Group", GROUP_ORDER, index=None, placeholder="All groups", key="count-group")
        pool = table[table["subcategory"] == group] if group else table
        choice = b.selectbox("Item", pool["label"], index=None, placeholder="Search an item", key="count-item")
        if choice:
            row = pool[pool["label"] == choice].iloc[0]
            system = int(row[stock.SHELF])
            c1, c2, c3 = st.columns(3)
            c1.metric("System says", system)
            counted = c2.number_input("You counted", min_value=0, max_value=10000, value=system, key="count-qty")
            diff = int(counted) - system
            c3.metric("Difference", f"{diff:+d}", delta=f"€{diff * row['cost']:+,.2f}" if diff else None)
            note = st.text_input("Note (optional)", max_chars=120, key="count-note",
                                 placeholder="e.g. 2 found in the old faulty box")
            if diff < 0:
                st.warning(f"{-diff} unit(s) missing. Check the faulty box and recent swaps in Movement history "
                           "before saving.", icon="🔎")
            if st.button("Save count", type="primary", key="count-save"):
                stock.stock_count(conn, date.today(), int(row["id"]), int(counted), user["id"], note=note.strip() or None)
                conn.commit()
                st.session_state.stock_flash = (f"Count saved for {choice}: "
                                                + ("matches the system." if diff == 0 else f"{diff:+d} recorded."))
                st.rerun()

with history_tab:
    moves = db.movements_df(conn)
    f1, f2, f3 = st.columns([2, 1.2, 1])
    choice = f1.selectbox("Item", sorted(moves["item"].unique()), index=None, placeholder="All items",
                          key="hist-item")
    reasons = f2.multiselect("Movement", sorted(moves["reason"].unique()), placeholder="All movements")
    who = f3.multiselect("Staff", sorted(moves["staff"].unique()), placeholder="Everyone")
    view = moves
    if choice:
        view = view[view["item"] == choice]
    if reasons:
        view = view[view["reason"].isin(reasons)]
    if who:
        view = view[view["staff"].isin(who)]
    names = {stock.SHELF: "Shelf", stock.BIN: "Faulty bin", stock.WITH_SUPPLIER: "With supplier",
             stock.SUPPLIER: "Supplier", stock.CUSTOMER: "Customer", stock.WRITTEN_OFF: "Written off",
             stock.UNEXPLAINED: "Unexplained"}
    view = view.assign(from_loc=view["from_loc"].map(names), to_loc=view["to_loc"].map(names))
    st.caption(f"{len(view):,} movements")
    st.dataframe(view[["moved_date", "item", "quantity", "from_loc", "to_loc", "reason", "staff", "note"]],
                 hide_index=True, width="stretch", height=480,
                 column_config={"moved_date": st.column_config.DateColumn("Date", format="DD MMM YYYY"),
                                "item": "Item", "quantity": st.column_config.NumberColumn("Qty", width="small"),
                                "from_loc": "From", "to_loc": "To", "reason": "Why", "staff": "Who", "note": "Note"})
