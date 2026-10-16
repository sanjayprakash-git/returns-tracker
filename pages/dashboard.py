"""Page 3 — manager dashboard (US-06 to US-10)."""
import altair as alt
import streamlit as st

from tracker import analytics, db

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"

conn = st.session_state.conn
returns, sales = db.returns_df(conn), db.sales_df(conn)

st.title("📊 Manager dashboard")

f1, f2, _ = st.columns([1.4, 1.2, 2])
lo, hi = sales["sale_date"].min().date(), max(sales["sale_date"].max(), returns["return_date"].max()).date()
period = f1.date_input("Period", value=(lo, hi), min_value=lo, max_value=hi, format="DD/MM/YYYY")
series = f2.multiselect("Series", ["A-series", "S-series"], placeholder="All series")
if len(period) != 2:
    st.stop()

r, s = analytics.filter_period(returns, sales, period[0], period[1], series)

# KPI row
k1, k2, k3, k4 = st.columns(4)
units = int(s["quantity"].sum())
k1.metric("Returns", f"{len(r):,}")
k2.metric("Return rate", f"{len(r) / units:.1%}" if units else "–", help="Returns ÷ phones sold in the period")
k3.metric("Refunded value", f"€{analytics.refunded_value(r):,.0f}", help="Retail price of refunded phones")
k4.metric("Outside policy", int(r["out_of_policy"].sum()))

with st.container(border=True):
    st.markdown("**What the data says**")
    for line in analytics.insights(r, s):
        st.markdown(f"- {line}")

if r.empty:
    st.stop()

c1, c2 = st.columns(2)

with c1:
    st.subheader("Return rate by model")
    rates = analytics.rate_by_model(r, s)
    bars = alt.Chart(rates).mark_bar(color=BLUE, cornerRadiusEnd=4, height={"band": 0.7}).encode(
        x=alt.X("return_rate:Q", title="Return rate", axis=alt.Axis(format="%", grid=True)),
        y=alt.Y("model:N", sort="-x", title=None),
        tooltip=[alt.Tooltip("model:N", title="Model"), alt.Tooltip("return_rate:Q", title="Return rate", format=".1%"),
                 alt.Tooltip("returns:Q", title="Returns"), alt.Tooltip("units_sold:Q", title="Units sold", format=",")],
    )
    labels = bars.mark_text(align="left", dx=4).encode(text=alt.Text("return_rate:Q", format=".1%"))
    avg = alt.Chart().mark_rule(strokeDash=[4, 4], opacity=0.35).encode(x=alt.datum(len(r) / units))
    st.altair_chart(alt.layer(avg, bars, labels, data=rates).properties(height=340), use_container_width=True)
    st.caption("Dashed line = shop average. Rates use units sold of the same model, so popular phones aren't penalised.")

with c2:
    st.subheader("Why phones come back")
    rs = analytics.reasons(r)
    chart = alt.Chart(rs).mark_bar(cornerRadiusEnd=4, height={"band": 0.7}).encode(
        x=alt.X("returns:Q", title="Returns"),
        y=alt.Y("reason:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        color=alt.Color("type:N", scale=alt.Scale(domain=["Other reason", "Product fault"], range=[BLUE, ORANGE]),
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("reason:N", title="Reason"), alt.Tooltip("returns:Q", title="Returns"),
                 alt.Tooltip("share:Q", title="Share", format=".0%")],
    )
    st.altair_chart(chart.properties(height=340), use_container_width=True)

c3, c4 = st.columns(2)

with c3:
    st.subheader("Monthly return rate")
    m = analytics.monthly(r, s)
    line = alt.Chart(m).mark_line(color=BLUE, strokeWidth=2, point=alt.OverlayMarkDef(size=70, filled=True)).encode(
        x=alt.X("month:T", title=None, axis=alt.Axis(format="%b", tickCount="month")),
        y=alt.Y("return_rate:Q", title="Return rate", axis=alt.Axis(format="%"), scale=alt.Scale(zero=True)),
        tooltip=[alt.Tooltip("month:T", title="Month", format="%B %Y"),
                 alt.Tooltip("return_rate:Q", title="Return rate", format=".1%"),
                 alt.Tooltip("returns:Q", title="Returns"), alt.Tooltip("units_sold:Q", title="Units sold", format=",")],
    )
    st.altair_chart(line.properties(height=300), use_container_width=True)

with c4:
    st.subheader("Refund, exchange or repair")
    o = analytics.outcomes(r)
    chart = alt.Chart(o).mark_bar(cornerRadiusEnd=4, height={"band": 0.6}).encode(
        x=alt.X("returns:Q", title="Returns"),
        y=alt.Y("outcome:N", sort=["Refund", "Exchange", "Repair"], title=None),
        color=alt.Color("outcome:N", scale=alt.Scale(domain=["Refund", "Exchange", "Repair"], range=[BLUE, ORANGE, AQUA]),
                        legend=None),
        tooltip=[alt.Tooltip("outcome:N", title="Outcome"), alt.Tooltip("returns:Q", title="Returns"),
                 alt.Tooltip("share:Q", title="Share", format=".0%")],
    )
    text = chart.mark_text(align="left", dx=4).encode(
        text=alt.Text("share:Q", format=".0%"), color=alt.value("currentColor"))
    st.altair_chart(alt.layer(chart, text).properties(height=300), use_container_width=True)

with st.expander("View the numbers as tables"):
    t1, t2 = st.columns(2)
    t1.dataframe(rates.style.format({"return_rate": "{:.1%}"}), hide_index=True, width="stretch")
    t2.dataframe(m.assign(month=m["month"].dt.strftime("%b %Y")).style.format({"return_rate": "{:.1%}"}),
                 hide_index=True, width="stretch")
