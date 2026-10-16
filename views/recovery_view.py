"""Loss & recovery (manager) — how much faulty and missing stock cost, and how much came back."""
from datetime import date

import altair as alt
import streamlit as st

from tracker import db, recovery, stock
from tracker.seed import GO_LIVE
from tracker.state import get_connection

BLUE, ORANGE, AQUA, YELLOW, RED = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948"

conn = get_connection()
items, moves, claims = db.items(conn), db.movements_df(conn), db.claims_df(conn)
sales, levels = db.sales_df(conn), stock.levels_df(conn)

st.title("💶 Loss & recovery")
st.caption("Every faulty or missing unit, valued at cost: what came back from suppliers, what's still to recover, "
           "and what was lost.")

s = recovery.summary(moves, claims, levels, items)
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric(f"Faulty stock ({s['faulty_units']} units)", f"€{s['faulty_value']:,.0f}",
          help="Everything that went into the faulty bin, at cost")
k2.metric(f"Recovered ({s['recovered'] / max(s['faulty_value'], 1):.0%})", f"€{s['recovered']:,.0f}",
          help="Credit notes, refunds and replacement stock from suppliers")
k3.metric("Still to recover", f"€{s['in_bin'] + s['with_suppliers']:,.0f}",
          help="In the faulty bin or sent and waiting for the supplier")
k4.metric("Written off", f"€{s['written_off']:,.0f}", help="Rejected by suppliers")
k5.metric("Unexplained", f"€{s['unexplained']:,.0f}", help="Missing at stock counts and never found")

with st.container(border=True):
    st.markdown("**What the data says**")
    for line in recovery.insights(moves, claims, sales, levels, items, GO_LIVE, date.today()):
        st.markdown(f"- {line}")

c1, c2 = st.columns([1.3, 1])
with c1:
    st.subheader("Before and after the app")
    mo = recovery.monthly(moves, claims)
    mo["label"] = mo["month"].dt.strftime("%b") + mo["month"].dt.month.map({7: " (go-live)"}).fillna("")
    order = list(dict.fromkeys(mo.sort_values("month")["label"]))
    series = ["Recorded as faulty", "Recovered from suppliers", "Missing at stock count"]
    bars = alt.Chart(mo).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("label:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("series:N", sort=series),
        y=alt.Y("value:Q", title="€ at cost", axis=alt.Axis(format="~s")),
        color=alt.Color("series:N", sort=series, title=None, legend=alt.Legend(orient="bottom"),
                        scale=alt.Scale(domain=series, range=[BLUE, AQUA, RED])),
        tooltip=[alt.Tooltip("month:T", title="Month", format="%B %Y"), alt.Tooltip("series:N", title=""),
                 alt.Tooltip("value:Q", title="€", format=",.0f")],
    )
    st.altair_chart(bars.properties(height=320), use_container_width=True)
    st.caption("Before July almost nothing was recorded as faulty and nothing came back from suppliers; the go-live "
               "count exposed the missing stock. After it, faults are recorded and recovered every month.")

with c2:
    st.subheader("How stock ends up faulty")
    src = recovery.sources(moves)
    chart = alt.Chart(src).mark_bar(cornerRadiusEnd=4, color=BLUE, height={"band": 0.7}).encode(
        x=alt.X("value:Q", title="€ at cost", axis=alt.Axis(format="~s")),
        y=alt.Y("source:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        tooltip=[alt.Tooltip("source:N", title="Source"), alt.Tooltip("units:Q", title="Units"),
                 alt.Tooltip("value:Q", title="€", format=",.0f")],
    )
    labels = chart.mark_text(align="left", dx=4, color="#52514e").encode(text=alt.Text("units:Q", format=",d"))
    st.altair_chart((chart + labels).properties(height=260, padding={"right": 30}), use_container_width=True)
    st.caption("Bar length = value at cost; label = units.")

st.subheader("Products and parts that fail most")
f1, f2, _ = st.columns([1.2, 1.2, 1])
since_go_live = f1.toggle("Since go-live only", value=True,
                          help="Before the app most faults weren't recorded, so earlier rates are too low")
group = f2.multiselect("Group", sorted(items["subcategory"].dropna().unique()), placeholder="All groups")
prod = recovery.by_product(moves, claims, sales, levels, since=GO_LIVE if since_go_live else None)
if group:
    prod = prod[prod["subcategory"].isin(group)]
if since_go_live:   # rank by how often things fail; recovery columns only make sense over all time
    prod = prod[prod["sold"] >= 10].sort_values("fault_rate", ascending=False)
    cols = ["item", "supplier", "sold", "customer_faults", "fault_rate", "faulty_value"]
else:
    cols = ["item", "supplier", "sold", "customer_faults", "fault_rate", "faulty_value", "recovered", "pending",
            "written_off"]
st.dataframe(
    prod[cols],
    hide_index=True, width="stretch", height=380,
    column_config={"item": "Item", "supplier": "Supplier", "sold": "Sold / used",
                   "customer_faults": "Came back faulty",
                   "fault_rate": st.column_config.ProgressColumn("Fault rate", format="percent", min_value=0,
                                                                 max_value=0.35),
                   "faulty_value": st.column_config.NumberColumn("Faulty value", format="€%.0f"),
                   "recovered": st.column_config.NumberColumn("Recovered", format="€%.0f"),
                   "pending": st.column_config.NumberColumn("Still to recover", format="€%.0f"),
                   "written_off": st.column_config.NumberColumn("Written off", format="€%.0f")})

st.subheader("Suppliers")
st.dataframe(recovery.by_supplier(claims), hide_index=True, width="stretch",
             column_config={"supplier": "Supplier", "units_sent": "Units sent",
                            "value_sent": st.column_config.NumberColumn("Value sent", format="€%.0f"),
                            "accepted_rate": st.column_config.ProgressColumn("Accepted", format="percent",
                                                                             min_value=0, max_value=1),
                            "avg_days_to_settle": st.column_config.NumberColumn("Days to settle", format="%.0f"),
                            "recovered": st.column_config.NumberColumn("Recovered", format="€%.0f"),
                            "still_open": st.column_config.NumberColumn("Still open", format="€%.0f")})
