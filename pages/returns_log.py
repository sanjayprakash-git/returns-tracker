"""Page 2 — browse and filter all returns (US-06)."""
import streamlit as st

from tracker import db
from tracker.policy import ALL_REASONS, CATEGORIES, OUTCOMES

conn = st.session_state.conn
df = db.returns_df(conn)

st.title("📋 Returns log")

f1, f2, f3, f4, f5 = st.columns([1.4, 1.2, 1, 1.4, 1])
lo, hi = df["return_date"].min().date(), df["return_date"].max().date()
period = f1.date_input("Date it came back", value=(lo, hi), min_value=lo, max_value=hi, format="DD/MM/YYYY")
categories = f2.multiselect("Type", CATEGORIES, placeholder="All types")
brands = f3.multiselect("Brand", sorted(df["brand"].unique()), placeholder="All brands")
reasons = f4.multiselect("Reason", ALL_REASONS, placeholder="All reasons")
outcomes = f5.multiselect("Outcome", OUTCOMES, placeholder="All")
t1, t2, _ = st.columns([1, 1, 2])
only_flagged = t1.toggle("Only outside policy")
only_claims = t2.toggle("Only supplier claims")

view = df
if len(period) == 2:
    view = view[(view["return_date"].dt.date >= period[0]) & (view["return_date"].dt.date <= period[1])]
for col, chosen in [("category", categories), ("brand", brands), ("reason", reasons), ("outcome", outcomes)]:
    if chosen:
        view = view[view[col].isin(chosen)]
if only_flagged:
    view = view[view["out_of_policy"]]
if only_claims:
    view = view[view["supplier_claim"]]

st.caption(f"Showing **{len(view):,}** of {len(df):,} returns · cost to the shop **€{view['return_cost'].sum():,.0f}**")
table = view[["id", "return_date", "category", "item", "supplier", "reason", "outcome", "days_since_purchase",
              "staff", "supplier_claim", "out_of_policy", "notes"]]
st.dataframe(
    table, hide_index=True, width="stretch", height=520,
    column_config={
        "id": st.column_config.NumberColumn("#", width="small"),
        "return_date": st.column_config.DateColumn("Came back", format="DD MMM YYYY"),
        "category": "Type", "item": "Item", "supplier": "Supplier", "reason": "Reason", "outcome": "Outcome",
        "days_since_purchase": st.column_config.NumberColumn("Days"),
        "staff": "Logged by",
        "supplier_claim": st.column_config.CheckboxColumn("Supplier claim"),
        "out_of_policy": st.column_config.CheckboxColumn("Out of policy"),
        "notes": "Notes",
    },
)
st.download_button("Download as CSV", table.to_csv(index=False).encode(), "returns.csv", "text/csv")
