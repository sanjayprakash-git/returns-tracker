"""Counter — the fast actions staff do many times a day. Every one keeps stock correct."""
from datetime import date

import streamlit as st

from tracker import db, stock
from tracker.policy import policy_warnings
from tracker.state import get_connection

conn = get_connection()
user = st.session_state.user
items = db.items(conn)
levels = stock.levels_df(conn).set_index("item_id")
products = items[items["category"] != "Repair"]

st.title("🔁 Counter")
st.caption("Faulty swaps, deliveries and faulty stock: one step each, so the shelf, the faulty bin and the system "
           "always agree.")
if flash := st.session_state.pop("counter_flash", None):
    st.success(flash)


def on_shelf(item_id) -> int:
    return int(levels.at[item_id, stock.SHELF]) if item_id in levels.index else 0


def pick_product(key, pool=products, label="Product"):
    a, b = st.columns([1, 2])
    groups = sorted(pool["subcategory"].dropna().unique())
    group = a.selectbox("Group", groups, index=None, placeholder="All groups", key=f"{key}-group")
    pool = pool[pool["subcategory"] == group] if group else pool
    choice = b.selectbox(label, pool["label"], index=None, placeholder="Search a product", key=f"{key}-item")
    return pool[pool["label"] == choice].iloc[0] if choice else None


swap_tab, delivery_tab, found_tab = st.tabs(["Faulty swap / refund", "Delivery in", "Found faulty on shelf"])

with swap_tab:
    with st.container(border=True):
        item = pick_product("swap")
        a, b, c = st.columns(3)
        fault = a.selectbox("Fault", stock.FAULTS, key="swap-fault")
        sold_on = b.date_input("Date sold", value=None, max_value=date.today(), format="DD/MM/YYYY",
                               help="From the receipt. Leave empty if there's no receipt.")
        outcome = c.radio("Customer gets", ["Exchange", "Refund", "Store credit"], horizontal=True,
                          format_func=lambda o: "Swap for a new one" if o == "Exchange" else o, key="swap-outcome")
        if item is not None:
            shelf = on_shelf(item["id"])
            days = (date.today() - sold_on).days if sold_on else 0
            st.caption(f"On the shelf: **{shelf}** · warranty **{item['warranty_days']} days**"
                       + (f" · sold **{days} days** ago" if sold_on else ""))
            if outcome == "Exchange" and shelf <= 0:
                st.warning("None left on the shelf to swap. Offer a refund or store credit, or order more.", icon="📦")
            for w in policy_warnings(item["category"], "Faulty", outcome, days, int(item["warranty_days"])):
                st.warning(f"**Outside policy:** {w}", icon="⚠️")
            st.info(f"Saving will: put the faulty unit in the **faulty bin**"
                    + (" and take the replacement **off the shelf**" if outcome == "Exchange" else "")
                    + f", for return to **{item['supplier']}**.", icon="ℹ️")
        if st.button("Save swap", type="primary", disabled=item is None or (outcome == "Exchange" and on_shelf(
                item["id"] if item is not None else -1) <= 0), key="swap-save"):
            today = date.today()
            days = (today - sold_on).days if sold_on else 0
            db.add_return(conn, return_date=today, purchase_date=sold_on or today, item_id=int(item["id"]),
                          reason="Faulty", outcome=outcome, staff_id=user["id"], supplier_claim=True,
                          out_of_policy=bool(policy_warnings(item["category"], "Faulty", outcome, days,
                                                             int(item["warranty_days"]))),
                          notes=f"Fault: {fault}" + ("" if sold_on else " · no receipt"))
            st.session_state.counter_flash = (f"Saved: {item['label']}. Faulty unit in the bin"
                                              + (", replacement taken off the shelf." if outcome == "Exchange" else "."))
            st.rerun()

with delivery_tab:
    with st.container(border=True):
        item = pick_product("dlv", pool=items, label="Product or part")
        a, b, c = st.columns(3)
        qty = a.number_input("Units delivered", min_value=1, max_value=1000, value=10, key="dlv-qty")
        damaged = b.number_input("Of which damaged", min_value=0, max_value=1000, value=0, key="dlv-dmg")
        problem = c.selectbox("Damage", stock.DELIVERY_PROBLEMS, disabled=damaged == 0, key="dlv-problem")
        note = st.text_input("Delivery reference (optional)", max_chars=60, placeholder="e.g. invoice 4471",
                             key="dlv-note")
        if item is not None:
            st.caption(f"Supplier **{item['supplier']}** · on the shelf now **{on_shelf(item['id'])}** → "
                       f"after this delivery **{on_shelf(item['id']) + qty - damaged}**"
                       + (f" · **{damaged}** to the faulty bin (€{damaged * item['cost']:,.2f} to claim)" if damaged else ""))
        if damaged > qty:
            st.error("Damaged can't be more than delivered.")
        if st.button("Book in delivery", type="primary", disabled=item is None or damaged > qty, key="dlv-save"):
            stock.receive_delivery(conn, date.today(), int(item["id"]), int(qty - damaged), int(damaged), user["id"],
                                   problem=problem if damaged else None, note=note.strip() or None)
            conn.commit()
            st.session_state.counter_flash = (f"Booked in {qty - damaged} × {item['label']}"
                                              + (f"; {damaged} damaged moved to the faulty bin." if damaged else "."))
            st.rerun()

with found_tab:
    with st.container(border=True):
        item = pick_product("found")
        a, b = st.columns([1, 2])
        qty = a.number_input("Units", min_value=1, max_value=100, value=1, key="found-qty")
        note = b.selectbox("What's wrong", ["Failed pre-sale test", "Damaged on the shelf", "Missing parts in box",
                                            "Other"], key="found-note")
        if item is not None:
            st.caption(f"On the shelf: **{on_shelf(item['id'])}**")
        if st.button("Move to faulty bin", type="primary", disabled=item is None, key="found-save"):
            stock.found_faulty(conn, date.today(), int(item["id"]), int(qty), user["id"], note=note)
            conn.commit()
            st.session_state.counter_flash = f"Moved {qty} × {item['label']} from the shelf to the faulty bin."
            st.rerun()
