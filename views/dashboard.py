"""Page 3 — manager dashboard (US-07 to US-12)."""
import altair as alt
import streamlit as st

from tracker import analytics, db
from tracker.policy import CATEGORIES, PART_GRADES, PART_TYPES
from tracker.state import get_connection

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SEQ = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#104281"]  # single-hue blue ramp, light → dark

conn = get_connection()
returns, sales = db.returns_df(conn), db.sales_df(conn)

st.title("📊 Manager dashboard")

f1, f2, f3 = st.columns([1.4, 1.6, 1.4])
lo, hi = sales["sale_date"].min().date(), max(sales["sale_date"].max(), returns["return_date"].max()).date()
period = f1.date_input("Period", value=(lo, hi), min_value=lo, max_value=hi, format="DD/MM/YYYY")
categories = f2.multiselect("Type", CATEGORIES, placeholder="Repairs, phones and accessories")
brands = f3.multiselect("Brand", ["Apple", "Samsung", "Google", "OnePlus"], placeholder="All brands")
if len(period) != 2:
    st.stop()

r, s = analytics.filter_period(returns, sales, period[0], period[1], categories, brands)
rep_r, rep_s = r[r["category"] == "Repair"], s[s["category"] == "Repair"]

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Returns & comebacks", f"{len(r):,}")
k2.metric("Repair comeback rate", f"{len(rep_r) / rep_s['quantity'].sum():.1%}" if len(rep_s) else "–",
          help="Repairs that came back ÷ repair jobs done")
k3.metric("Cost of returns", f"€{analytics.cost_of_returns(r):,.0f}",
          help="Free re-repairs (part + labour), refunds, store credit and replacement stock")
claims_in_period = db.claims_df(conn)
claims_in_period = claims_in_period[(claims_in_period["created_date"].dt.date >= period[0])
                                    & (claims_in_period["created_date"].dt.date <= period[1])]
k4.metric("Recovered from suppliers", f"€{analytics.claim_summary(claims_in_period)['recovered']:,.0f}",
          help="Credit notes, refunds and replacement stock from supplier claims logged in this period")
k5.metric("Outside policy", int(r["out_of_policy"].sum()))

with st.container(border=True):
    st.markdown("**What the data says**")
    for line in analytics.insights(r, s):
        st.markdown(f"- {line}")

if r.empty:
    st.stop()


def hbar(df, x, y, color=BLUE, fmt=".1%", title=None, height=300, sort="-x", tooltip=None, label=True, label_limit=260):
    top = float(df[x].max()) * 1.18 if len(df) else 1  # room for the value labels
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:Q", title=title, scale=alt.Scale(domain=[0, top], nice=False),
                axis=alt.Axis(format="%" if fmt.endswith("%") else "d", tickCount=5, labelFlush=True)),
        y=alt.Y(f"{y}:N", sort=sort, title=None, axis=alt.Axis(labelLimit=label_limit, labelOverlap=False)),
        tooltip=tooltip,
    )
    bars = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.7}, color=color) if isinstance(color, str) else \
        base.mark_bar(cornerRadiusEnd=4, height={"band": 0.7}).encode(color=color)
    layers = [bars]
    if label:
        layers.append(base.mark_text(align="left", dx=4, color="#52514e").encode(text=alt.Text(f"{x}:Q", format=fmt)))
    return alt.layer(*layers).properties(height=height, padding={"left": 5, "top": 5, "right": 24, "bottom": 5})


rate_tip = lambda name: [alt.Tooltip(f"{name}:N", title=name.capitalize()), alt.Tooltip("rate:Q", title="Rate", format=".1%"),
                         alt.Tooltip("returns:Q", title="Came back"), alt.Tooltip("units:Q", title="Sold / jobs", format=",")]

c1, c2 = st.columns([1.25, 1])
with c1:
    st.subheader("Repair comeback rate by part and grade")
    m = analytics.part_grade_matrix(r, s)
    if len(m):
        base = alt.Chart(m).encode(
            x=alt.X("part_grade:N", sort=PART_GRADES, title=None,
                    axis=alt.Axis(labelAngle=0, orient="top", labelExpr="split(datum.label, ' ')[0]")),
            y=alt.Y("part:N", sort=PART_TYPES, title=None),
        )
        heat = base.mark_rect(cornerRadius=4, stroke="white", strokeWidth=2).encode(
            color=alt.Color("rate:Q", scale=alt.Scale(range=SEQ), legend=alt.Legend(format="%", title="Comeback rate")),
            tooltip=[alt.Tooltip("part:N", title="Part"), alt.Tooltip("part_grade:N", title="Grade"),
                     alt.Tooltip("rate:Q", title="Comeback rate", format=".1%"),
                     alt.Tooltip("returns:Q", title="Came back"), alt.Tooltip("units:Q", title="Jobs", format=",")],
        )
        text = base.mark_text(fontSize=13, fontWeight=600).encode(
            text=alt.Text("rate:Q", format=".1%"),
            color=alt.condition(alt.datum.rate > 0.06, alt.value("white"), alt.value("#0b0b0b")),
        )
        st.altair_chart((heat + text).properties(height=300), use_container_width=True)
        st.caption("Grades: genuine, premium aftermarket, standard aftermarket. Blank cells: that part isn't offered in that grade.")
    else:
        st.info("No repairs in this selection.")

with c2:
    st.subheader("Return rate by type")
    st.altair_chart(hbar(analytics.rate_by(r, s, "category"), "rate", "category", tooltip=rate_tip("category"),
                         title="Returned ÷ sold"), use_container_width=True)

c3, c4 = st.columns(2)
with c3:
    st.subheader("Repairs that come back most")
    w = analytics.worst_items(r, s)
    if len(w):
        st.altair_chart(hbar(w, "rate", "item", color=ORANGE, tooltip=rate_tip("item"), title="Comeback rate"),
                        use_container_width=True)
        st.caption(f"Device, part and grade combinations with at least {analytics.MIN_JOBS} jobs.")
    else:
        st.info(f"No repair item has {analytics.MIN_JOBS}+ jobs in this selection.")

with c4:
    st.subheader("Why things come back")
    rs = analytics.reasons(r)
    color = alt.Color("responsibility:N", title=None, legend=alt.Legend(orient="bottom", columns=2, labelLimit=160),
                      scale=alt.Scale(domain=["Part fault", "Workmanship", "Customer damage", "Sale-related"],
                                      range=[BLUE, ORANGE, AQUA, YELLOW]))
    st.altair_chart(hbar(rs, "returns", "reason", color=color, fmt="d", title="Returns", label=False, height=420, label_limit=175,
                         tooltip=[alt.Tooltip("reason:N", title="Reason"), alt.Tooltip("returns:Q", title="Returns"),
                                  alt.Tooltip("share:Q", title="Share", format=".0%"),
                                  alt.Tooltip("responsibility:N", title="Responsibility")]),
                    use_container_width=True)

c5, c6 = st.columns(2)
with c5:
    st.subheader("Monthly rate")
    mo = analytics.monthly(r, s)
    line = alt.Chart(mo).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=70, filled=True)).encode(
        x=alt.X("month:T", title=None, axis=alt.Axis(format="%b", tickCount="month")),
        y=alt.Y("rate:Q", title="Rate", axis=alt.Axis(format="%"), scale=alt.Scale(zero=True)),
        color=alt.Color("series:N", title=None, legend=alt.Legend(orient="bottom"),
                        scale=alt.Scale(domain=["Repair comebacks", "Product returns"], range=[BLUE, ORANGE])),
        tooltip=[alt.Tooltip("series:N", title="Series"), alt.Tooltip("month:T", title="Month", format="%B %Y"),
                 alt.Tooltip("rate:Q", title="Rate", format=".1%"), alt.Tooltip("returns:Q", title="Came back"),
                 alt.Tooltip("units:Q", title="Sold / jobs", format=",")],
    )
    st.altair_chart(line.properties(height=300), use_container_width=True)

with c6:
    st.subheader("Accessory returns by type")
    acc_r, acc_s = r[r["category"] == "Accessory"], s[s["category"] == "Accessory"]
    if len(acc_s):
        st.altair_chart(hbar(analytics.rate_by(acc_r, acc_s, "subcategory"), "rate", "subcategory",
                             tooltip=rate_tip("subcategory"), title="Returned ÷ sold"), use_container_width=True)
    else:
        st.info("No accessories in this selection.")

st.subheader("What happened to each return")
o = analytics.outcomes(r)
st.altair_chart(hbar(o, "returns", "outcome", fmt="d", title="Returns", height=200,
                     sort=["Re-repair (free)", "Refund", "Exchange", "Store credit", "Declined"],
                     tooltip=[alt.Tooltip("outcome:N", title="Outcome"), alt.Tooltip("returns:Q", title="Returns"),
                              alt.Tooltip("share:Q", title="Share", format=".0%")]),
                use_container_width=True)

with st.expander("View the numbers as tables"):
    t1, t2 = st.columns(2)
    t1.dataframe(m.style.format({"rate": "{:.1%}"}), hide_index=True, width="stretch")
    t2.dataframe(analytics.rate_by(r, s, "category").style.format({"rate": "{:.1%}"}), hide_index=True, width="stretch")
