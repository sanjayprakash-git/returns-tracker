"""Page 1 — staff log a repair comeback or product return (US-01 to US-05)."""
from datetime import date, timedelta

import streamlit as st

from tracker import db
from tracker.policy import (CATEGORIES, OUTCOMES_BY_CATEGORY, REASONS, policy_warnings,
                            responsibility, suggests_supplier_claim)
from tracker.state import get_connection

conn = get_connection()
items = db.items(conn)
user = st.session_state.user

st.title("📝 Log a return")
st.caption(f"Repair comebacks and product returns, logged by **{user['name']}**. "
           "Takes about 30 seconds; every field except notes is required.")

with st.container(border=True):
    category = st.segmented_control("What's coming back?", CATEGORIES, default="Repair")
    if not category:
        st.stop()
    pool = items[items["category"] == category]

    c1, c2 = st.columns(2)
    if category == "Accessory":
        group = c1.selectbox("Accessory type", sorted(pool["subcategory"].unique()), index=None,
                             placeholder="Choose a type")
        pool = pool[pool["subcategory"] == group] if group else pool.iloc[0:0]
        item_label = "Product"
    else:
        brand = c1.selectbox("Brand", sorted(pool["brand"].unique()), index=None, placeholder="Choose a brand")
        pool = pool[pool["brand"] == brand] if brand else pool.iloc[0:0]
        item_label = "Device · part · grade" if category == "Repair" else "Phone"
    item = c2.selectbox(item_label, pool["label"], index=None, placeholder="Search or choose")
    warranty = int(pool.loc[pool["label"] == item, "warranty_days"].iloc[0]) if item else None
    if warranty:
        c2.caption(f"Warranty on this item: **{warranty} days**")

    sold_word = "Repair date" if category == "Repair" else "Purchase date"
    purchase_date = c1.date_input(sold_word, value=date.today() - timedelta(days=10),
                                  max_value=date.today(), format="DD/MM/YYYY")
    return_date = c2.date_input("Date it came back", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")

    reason = c1.selectbox("Reason", REASONS[category], index=None, placeholder="Choose a reason")
    outcome = c2.radio("Outcome", OUTCOMES_BY_CATEGORY[category], index=None, horizontal=True)
    notes = st.text_input("Notes (optional)", max_chars=200, placeholder="e.g. touch dead in top corner")

    days = (return_date - purchase_date).days
    m1, m2 = st.columns(2)
    if days < 0:
        st.error("The return date can't be before the purchase/repair date.")
    else:
        m1.metric("Days since " + ("repair" if category == "Repair" else "purchase"), days)
    if reason:
        m2.metric("Responsibility", responsibility(reason))

    claim = False
    if reason and suggests_supplier_claim(category, reason):
        claim = st.checkbox("Send part back to supplier for a claim (RMA)", value=outcome != "Declined",
                            key=f"claim-{category}-{reason}-{outcome}",
                            help="Suggested because the reason points to a faulty part or product.")

    warnings = policy_warnings(category, reason, outcome, days, warranty) if reason and outcome and days >= 0 else []
    for w in warnings:
        st.warning(f"**Outside policy:** {w}", icon="⚠️")

    missing = [label for label, v in [("item", item), ("reason", reason), ("outcome", outcome)] if not v]
    if st.button("Save return", type="primary", width="stretch"):
        if missing:
            st.error(f"Please fill in: {', '.join(missing)}.")
        elif days < 0:
            st.error("Fix the dates before saving.")
        else:
            new_id = db.add_return(
                conn,
                return_date=return_date, purchase_date=purchase_date,
                item_id=int(items.loc[items["label"] == item, "id"].iloc[0]),
                reason=reason, outcome=outcome,
                staff_id=user["id"],
                supplier_claim=claim, out_of_policy=bool(warnings), notes=notes.strip(),
            )
            extra = " Flagged as outside policy for the manager to review." if warnings else ""
            extra += " Supplier claim recorded." if claim else ""
            st.success(f"Return #{new_id} saved: {item}, {reason.lower()}, {outcome.lower()}.{extra}")

st.info("Demo app: data you add is kept until the app restarts, then the sample data is reloaded.", icon="ℹ️")
