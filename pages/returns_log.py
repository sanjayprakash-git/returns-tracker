"""Page 2 — browse and filter all returns (US-05)."""
import streamlit as st

from tracker import db
from tracker.policy import OUTCOMES, REASONS

conn = st.session_state.conn
df = db.returns_df(conn)

st.title("📋 Returns log")

f1, f2, f3, f4, f5 = st.columns([1.4, 1.2, 1.2, 1, 1])
lo, hi = df["return_date"].min().date(), df["return_date"].max().date()
period = f1.date_input("Return date", value=(lo, hi), min_value=lo, max_value=hi, format="DD/MM/YYYY")
models = f2.multiselect("Model", sorted(df["model"].unique()), placeholder="All models")
reasons = f3.multiselect("Reason", REASONS, placeholder="All reasons")
outcomes = f4.multiselect("Outcome", OUTCOMES, placeholder="All")
staff = f5.multiselect("Staff", sorted(df["staff"].unique()), placeholder="All staff")
only_flagged = st.toggle("Only show returns outside policy")

view = df
if len(period) == 2:
    view = view[(view["return_date"].dt.date >= period[0]) & (view["return_date"].dt.date <= period[1])]
for col, chosen in [("model", models), ("reason", reasons), ("outcome", outcomes), ("staff", staff)]:
    if chosen:
        view = view[view[col].isin(chosen)]
if only_flagged:
    view = view[view["out_of_policy"]]

st.caption(f"Showing **{len(view):,}** of {len(df):,} returns")
table = view[["id", "return_date", "model", "reason", "condition", "outcome", "days_since_purchase",
              "staff", "out_of_policy", "notes"]]
st.dataframe(
    table, hide_index=True, width="stretch", height=520,
    column_config={
        "id": st.column_config.NumberColumn("#", width="small"),
        "return_date": st.column_config.DateColumn("Returned", format="DD MMM YYYY"),
        "days_since_purchase": st.column_config.NumberColumn("Days since purchase"),
        "out_of_policy": st.column_config.CheckboxColumn("Out of policy"),
        "model": "Model", "reason": "Reason", "condition": "Condition", "outcome": "Outcome",
        "staff": "Logged by", "notes": "Notes",
    },
)
st.download_button("Download as CSV", table.to_csv(index=False).encode(), "returns.csv", "text/csv")
