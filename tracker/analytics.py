"""Metrics and plain-English insights for the manager dashboard (US-06 to US-10)."""
import pandas as pd

from tracker.policy import FAULT_REASONS


def filter_period(returns: pd.DataFrame, sales: pd.DataFrame, start, end, series=None):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    r = returns[(returns["return_date"] >= start) & (returns["return_date"] <= end)]
    s = sales[(sales["sale_date"] >= start) & (sales["sale_date"] <= end)]
    if series:
        r, s = r[r["series"].isin(series)], s[s["series"].isin(series)]
    return r, s


def rate_by_model(returns: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    units = sales.groupby("model")["quantity"].sum().rename("units_sold")
    count = returns.groupby("model").size().rename("returns")
    df = pd.concat([units, count], axis=1).fillna(0).astype(int)
    df = df[df["units_sold"] > 0]
    df["return_rate"] = df["returns"] / df["units_sold"]
    return df.sort_values("return_rate", ascending=False).reset_index(names="model")


def reasons(returns: pd.DataFrame) -> pd.DataFrame:
    df = returns.groupby("reason").size().rename("returns").reset_index()
    df["share"] = df["returns"] / df["returns"].sum() if len(df) else 0
    df["type"] = df["reason"].map(lambda r: "Product fault" if r in FAULT_REASONS else "Other reason")
    return df.sort_values("returns", ascending=False)


def monthly(returns: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    r = returns.groupby(returns["return_date"].dt.to_period("M")).size().rename("returns")
    s = sales.groupby(sales["sale_date"].dt.to_period("M"))["quantity"].sum().rename("units_sold")
    df = pd.concat([r, s], axis=1).fillna(0)
    df = df[df["units_sold"] > 0]
    df["return_rate"] = df["returns"] / df["units_sold"]
    df.index = df.index.to_timestamp()
    return df.reset_index(names="month")


def outcomes(returns: pd.DataFrame) -> pd.DataFrame:
    df = returns.groupby("outcome").size().rename("returns").reset_index()
    df["share"] = df["returns"] / df["returns"].sum() if len(df) else 0
    return df.sort_values("returns", ascending=False)


def refunded_value(returns: pd.DataFrame) -> float:
    return float(returns.loc[returns["outcome"] == "Refund", "price"].sum())


def insights(returns: pd.DataFrame, sales: pd.DataFrame) -> list[str]:
    """Three to four headline sentences that update with the filters."""
    if returns.empty or sales.empty:
        return ["No returns in the selected period."]
    out = []

    rates = rate_by_model(returns, sales)
    overall = len(returns) / sales["quantity"].sum()
    top = rates.iloc[0]
    out.append(
        f"**{top['model']}** has the highest return rate at **{top['return_rate']:.1%}** "
        f"({top['returns']} of {top['units_sold']:,} sold), {top['return_rate'] / overall:.1f}× the shop average of {overall:.1%}."
    )

    rs = reasons(returns)
    lead = rs.iloc[0]
    fault_share = rs.loc[rs["type"] == "Product fault", "returns"].sum() / len(returns)
    out.append(
        f"**{lead['reason']}** is the top reason ({lead['share']:.0%} of returns). "
        f"Product faults account for {fault_share:.0%}, so most returns are about the sale, not the phone."
        if fault_share < 0.5 else
        f"**{lead['reason']}** is the top reason ({lead['share']:.0%} of returns), and product faults account for {fault_share:.0%}."
    )

    m = monthly(returns, sales)
    if len(m) >= 2:
        last, prev = m.iloc[-1], m.iloc[-2]
        change = last["return_rate"] - prev["return_rate"]
        direction = "up" if change > 0 else "down"
        out.append(
            f"In **{last['month']:%B}** the return rate was **{last['return_rate']:.1%}**, "
            f"{direction} {abs(change) * 100:.1f} points from {prev['month']:%B}."
        )

    # Biggest single-model fault spike in any month
    faults = returns[returns["reason"].isin(FAULT_REASONS)]
    if not faults.empty:
        by = faults.groupby([faults["return_date"].dt.to_period("M"), "model", "reason"]).size()
        (month, model, reason), n = by.idxmax(), by.max()
        months = returns["return_date"].dt.to_period("M").unique()
        typical = by.xs((model, reason), level=(1, 2)).reindex(months, fill_value=0).median()
        if n >= 5 and n >= 3 * max(typical, 1):
            out.append(
                f"⚠️ **{model}** had a spike of **{n} '{reason.split('– ')[-1]}' faults in {month.strftime('%B')}**. "
                f"Worth checking that stock batch with the supplier."
            )

    flagged = int(returns["out_of_policy"].sum())
    if flagged:
        out.append(f"**{flagged}** returns were handled outside the returns policy.")
    return out
