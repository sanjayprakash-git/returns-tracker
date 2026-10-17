"""Counter — find the item, say what happened, save. Every action keeps stock correct."""
from datetime import date

import streamlit as st

from tracker import db, stock
from tracker.policy import OUTCOMES_BY_CATEGORY, REASONS, policy_warnings, responsibility, suggests_supplier_claim
from tracker.state import get_connection

conn = get_connection()
user = st.session_state.user
items = db.items(conn)
levels = stock.levels_df(conn).set_index("item_id")


def on_shelf(item_id) -> int:
    return int(levels.at[item_id, stock.SHELF]) if item_id in levels.index else 0


st.title("🔁 Counter")
if flash := st.session_state.pop("counter_flash", None):
    st.success(flash)

choice = st.selectbox("Item", items["label"], index=None, placeholder="🔎  Search: earbuds, 45W charger, iPhone 13 screen…",
                      label_visibility="collapsed", key=f"counter_item_{st.session_state.get('counter_round', 0)}")
if not choice:
    st.caption("Search for the product or part, then choose what happened. "
               "Faulty units go into the **faulty box** and are sent back to the supplier from there.")
    st.stop()

item = items[items["label"] == choice].iloc[0]
iid, shelf = int(item["id"]), on_shelf(int(item["id"]))
is_part = item["category"] == "Repair"
st.caption(f"**{shelf}** on the shelf · supplier **{item['supplier']}** · warranty **{item['warranty_days']} days**")

actions = (["Repair comeback", "Delivery in", "Found faulty"] if is_part else
           ["Faulty – swap", "Faulty – refund", "Returned OK", "Delivery in", "Found faulty"])
action = st.segmented_control("What happened?", actions, default=actions[0])


def save(message):
    conn.commit()
    st.session_state.counter_flash = message
    st.session_state.counter_round = st.session_state.get("counter_round", 0) + 1   # fresh search box
    st.rerun()


def sale_date_and_warnings(reason, outcome):
    """Optional sale/repair date for the warranty check; returns (date, days, warnings)."""
    with st.expander("More details (optional)"):
        sold = st.date_input("Date sold" if not is_part else "Date of the repair", value=None,
                             max_value=date.today(), format="DD/MM/YYYY")
        note = st.text_input("Note", max_chars=120)
    days = (date.today() - sold).days if sold else 0
    warn = policy_warnings(item["category"], reason, outcome, days, int(item["warranty_days"]))
    for w in warn:
        st.warning(w, icon="⚠️")
    return sold, days, warn, note


with st.container(border=True):
    if action in ("Faulty – swap", "Faulty – refund"):
        swap = action == "Faulty – swap"
        outcome = "Exchange" if swap else st.radio("Give the customer", ["Refund", "Store credit"], horizontal=True)
        fault = st.pills("Fault", stock.FAULTS, default=stock.FAULTS[0])
        sold, days, warn, note = sale_date_and_warnings("Faulty", outcome)
        if swap and shelf <= 0:
            st.warning("None left on the shelf to swap. Give a refund or store credit instead.", icon="📦")
        st.caption("Saving: faulty unit → **faulty box**" + (" · new one → **customer**" if swap else ""))
        if st.button("Swap it" if swap else "Save", type="primary", disabled=swap and shelf <= 0):
            db.add_return(conn, return_date=date.today(), purchase_date=sold or date.today(), item_id=iid,
                          reason="Faulty", outcome=outcome, staff_id=user["id"], supplier_claim=True,
                          out_of_policy=bool(warn),
                          notes=" · ".join(filter(None, [f"Fault: {fault}" if fault else None,
                                                         None if sold else "no receipt", note])), commit=False)
            save(f"Done: {choice}. Faulty unit is in the faulty box"
                 + (", new one given to the customer." if swap else f", {outcome.lower()} given."))

    elif action == "Returned OK":
        reason = st.radio("Why", ["Changed mind", "Not compatible with phone"], horizontal=True)
        outcome = st.radio("Give the customer", ["Refund", "Store credit", "Exchange"], horizontal=True)
        sold, days, warn, note = sale_date_and_warnings(reason, outcome)
        st.caption("Saving: unit → back **on the shelf**")
        if st.button("Save", type="primary"):
            db.add_return(conn, return_date=date.today(), purchase_date=sold or date.today(), item_id=iid,
                          reason=reason, outcome=outcome, staff_id=user["id"], supplier_claim=False,
                          out_of_policy=bool(warn), notes=note or None, commit=False)
            save(f"Done: {choice} back on the shelf, {outcome.lower()} given.")

    elif action == "Repair comeback":
        reason = st.selectbox("What's wrong", REASONS["Repair"])
        outcome = st.radio("Outcome", OUTCOMES_BY_CATEGORY["Repair"], horizontal=True)
        sold, days, warn, note = sale_date_and_warnings(reason, outcome)
        faulty = suggests_supplier_claim("Repair", reason) and outcome != "Declined"
        st.caption(f"Responsibility: **{responsibility(reason)}** · Saving: "
                   + ", ".join(filter(None, ["faulty part → **faulty box**" if faulty else None,
                                             "new part → off the shelf" if outcome == "Re-repair (free)" else None]))
                   if faulty or outcome == "Re-repair (free)" else f"Responsibility: **{responsibility(reason)}**")
        if st.button("Save", type="primary", disabled=outcome == "Re-repair (free)" and shelf <= 0):
            db.add_return(conn, return_date=date.today(), purchase_date=sold or date.today(), item_id=iid,
                          reason=reason, outcome=outcome, staff_id=user["id"], supplier_claim=faulty,
                          out_of_policy=bool(warn), notes=note or None, commit=False)
            save(f"Done: comeback on {choice} recorded.")

    elif action == "Delivery in":
        a, b = st.columns(2)
        qty = a.number_input("Units delivered", min_value=1, max_value=1000, value=10)
        damaged = b.number_input("Damaged", min_value=0, max_value=1000, value=0)
        problem = st.pills("Damage", stock.DELIVERY_PROBLEMS, default=stock.DELIVERY_PROBLEMS[0]) if damaged else None
        if damaged > qty:
            st.error("Damaged can't be more than delivered.")
        st.caption(f"Saving: **{qty - damaged}** → shelf (then {shelf + qty - damaged})"
                   + (f" · **{damaged}** → faulty box (€{damaged * item['cost']:,.2f} to claim)" if damaged else ""))
        if st.button("Book in", type="primary", disabled=damaged > qty):
            stock.receive_delivery(conn, date.today(), iid, int(qty - damaged), int(damaged), user["id"], problem=problem)
            save(f"Booked in {qty - damaged} × {choice}" + (f"; {damaged} damaged in the faulty box." if damaged else "."))

    elif action == "Found faulty":
        a, b = st.columns([1, 2])
        qty = a.number_input("Units", min_value=1, max_value=max(shelf, 1), value=1)
        why = b.pills("What's wrong", ["Failed pre-sale test", "Damaged on the shelf", "Missing parts in box"],
                      default="Failed pre-sale test")
        st.caption("Saving: shelf → **faulty box**")
        if st.button("Move to faulty box", type="primary", disabled=shelf <= 0):
            stock.found_faulty(conn, date.today(), iid, int(qty), user["id"], note=why)
            save(f"Moved {qty} × {choice} to the faulty box.")
