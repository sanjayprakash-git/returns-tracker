"""Page 1 — staff log a return (US-01 to US-04)."""
from datetime import date, timedelta

import streamlit as st

from tracker import db
from tracker.policy import CONDITIONS, OUTCOMES, REASONS, policy_warnings

conn = st.session_state.conn
products = db.products(conn)
staff = db.staff(conn)

st.title("📝 Log a return")
st.caption("Takes about 30 seconds. Every field except notes is required.")

with st.container(border=True):
    c1, c2 = st.columns(2)
    purchase_date = c1.date_input("Purchase date", value=date.today() - timedelta(days=7),
                                  max_value=date.today(), format="DD/MM/YYYY")
    return_date = c2.date_input("Return date", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")

    model = c1.selectbox("Phone model", products["model"], index=None, placeholder="Choose a model")
    reason = c2.selectbox("Reason for return", REASONS, index=None, placeholder="Choose a reason")
    condition = c1.selectbox("Condition", CONDITIONS, index=None, placeholder="Choose condition")
    outcome = c2.radio("Outcome", OUTCOMES, index=None, horizontal=True)
    staff_name = c1.selectbox("Logged by", staff["name"], index=None, placeholder="Your name")
    notes = c2.text_input("Notes (optional)", max_chars=200)

    days = (return_date - purchase_date).days
    if days < 0:
        st.error("The return date can't be before the purchase date.")
    else:
        st.metric("Days since purchase", days)

    warnings = policy_warnings(reason, outcome, days) if reason and outcome and days >= 0 else []
    for w in warnings:
        st.warning(f"**Outside returns policy:** {w}", icon="⚠️")

    missing = [label for label, v in [("model", model), ("reason", reason), ("condition", condition),
                                       ("outcome", outcome), ("staff name", staff_name)] if not v]
    if st.button("Save return", type="primary", width="stretch"):
        if missing:
            st.error(f"Please fill in: {', '.join(missing)}.")
        elif days < 0:
            st.error("Fix the dates before saving.")
        else:
            new_id = db.add_return(
                conn,
                return_date=return_date, purchase_date=purchase_date,
                product_id=int(products.loc[products["model"] == model, "id"].iloc[0]),
                reason=reason, condition=condition, outcome=outcome,
                staff_id=int(staff.loc[staff["name"] == staff_name, "id"].iloc[0]),
                out_of_policy=bool(warnings), notes=notes.strip(),
            )
            flag = " It's flagged as outside policy for the manager to review." if warnings else ""
            st.success(f"Return #{new_id} saved: {model}, {reason.lower()}, {outcome.lower()}.{flag}")

st.info("Demo app: data you add is kept until the app restarts, then the sample data is reloaded.", icon="ℹ️")
