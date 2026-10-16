"""Metrics and plain-English insights for the manager dashboard."""
import pandas as pd

from tracker.policy import responsibility

MIN_JOBS = 30  # ignore items with too few jobs to judge a rate


def filter_period(returns, sales, start, end, categories=None, brands=None):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    r = returns[(returns["return_date"] >= start) & (returns["return_date"] <= end)]
    s = sales[(sales["sale_date"] >= start) & (sales["sale_date"] <= end)]
    if categories:
        r, s = r[r["category"].isin(categories)], s[s["category"].isin(categories)]
    if brands:
        r, s = r[r["brand"].isin(brands)], s[s["brand"].isin(brands)]
    return r, s


def rate_by(returns, sales, keys) -> pd.DataFrame:
    """Returns ÷ units sold, grouped by one or more columns."""
    keys = [keys] if isinstance(keys, str) else keys
    units = sales.groupby(keys)["quantity"].sum().rename("units")
    count = returns.groupby(keys).size().rename("returns")
    df = pd.concat([units, count], axis=1).fillna(0)
    df = df[df["units"] > 0].astype({"units": int, "returns": int})
    df["rate"] = df["returns"] / df["units"]
    return df.reset_index().sort_values("rate", ascending=False)


def part_grade_matrix(returns, sales) -> pd.DataFrame:
    rr, ss = returns[returns["category"] == "Repair"], sales[sales["category"] == "Repair"]
    return rate_by(rr, ss, ["name", "part_grade"]).rename(columns={"name": "part"})


def worst_items(returns, sales, n=8) -> pd.DataFrame:
    rr, ss = returns[returns["category"] == "Repair"], sales[sales["category"] == "Repair"]
    df = rate_by(rr, ss, "item")
    return df[df["units"] >= MIN_JOBS].head(n)


def reasons(returns) -> pd.DataFrame:
    df = returns.groupby("reason").size().rename("returns").reset_index()
    df["share"] = df["returns"] / df["returns"].sum() if len(df) else 0
    df["responsibility"] = df["reason"].map(responsibility)
    return df.sort_values("returns", ascending=False)


def monthly(returns, sales) -> pd.DataFrame:
    """Monthly rate for repairs (comebacks) and products (returns), in long format for one chart."""
    def group(df_r, df_s):
        r = df_r.groupby(df_r["return_date"].dt.to_period("M")).size()
        s = df_s.groupby(df_s["sale_date"].dt.to_period("M"))["quantity"].sum()
        out = pd.concat([r.rename("returns"), s.rename("units")], axis=1).fillna(0)
        out = out[out["units"] > 0]
        out["rate"] = out["returns"] / out["units"]
        out.index = out.index.to_timestamp()
        return out.reset_index(names="month")
    is_rep_r, is_rep_s = returns["category"] == "Repair", sales["category"] == "Repair"
    parts = []
    for label, r, s in (("Repair comebacks", returns[is_rep_r], sales[is_rep_s]),
                        ("Product returns", returns[~is_rep_r], sales[~is_rep_s])):
        if len(s):
            parts.append(group(r, s).assign(series=label))
    return pd.concat(parts) if parts else pd.DataFrame(columns=["month", "returns", "units", "rate", "series"])


def outcomes(returns) -> pd.DataFrame:
    df = returns.groupby("outcome").size().rename("returns").reset_index()
    df["share"] = df["returns"] / df["returns"].sum() if len(df) else 0
    return df


def cost_of_returns(returns) -> float:
    return float(returns["return_cost"].sum())


def supplier_recoverable(returns) -> float:
    """Part / product cost the shop can claim back from suppliers (RMA)."""
    return float(returns.loc[returns["supplier_claim"], "cost"].sum())


def insights(returns, sales) -> list[str]:
    if returns.empty or sales.empty:
        return ["No returns in the selected period."]
    out = []
    rep_r, rep_s = returns[returns["category"] == "Repair"], sales[sales["category"] == "Repair"]

    # 1. Screen grade comparison — the biggest lever in a repair shop
    m = part_grade_matrix(returns, sales).set_index(["part", "part_grade"])
    try:
        std, gen = m.loc[("Screen", "Standard aftermarket")], m.loc[("Screen", "Genuine")]
        prem = m.loc[("Screen", "Premium aftermarket")]
        avoidable = round((std["rate"] - prem["rate"]) * std["units"])
        out.append(
            f"**Standard aftermarket screens** come back **{std['rate']:.1%}** of the time vs "
            f"{prem['rate']:.1%} for premium and {gen['rate']:.1%} for genuine. Fitting premium instead "
            f"would have avoided about **{avoidable} comebacks**."
        )
    except KeyError:
        pass

    # 2. Worst repair item with enough volume
    worst = worst_items(returns, sales, n=1)
    if len(worst) and len(rep_s):
        avg = len(rep_r) / rep_s["quantity"].sum()
        w = worst.iloc[0]
        out.append(f"Worst repair: **{w['item']}** at **{w['rate']:.0%}** comeback rate "
                   f"({w['returns']} of {w['units']} jobs), vs {avg:.1%} across all repairs.")

    # 3. Supplier / part spike in a single month
    if len(rep_r):
        grid = (rep_r.groupby([rep_r["return_date"].dt.to_period("M"), "supplier", "name"]).size()
                .unstack(["supplier", "name"], fill_value=0))
        best = None
        for (supplier, part), counts in grid.items():
            n, typical = counts.max(), counts.median()
            ratio = n / max(typical, 1)
            if n >= 8 and ratio >= 2.5 and (best is None or ratio > best[0]):
                best = (ratio, supplier, part, counts.idxmax(), n, typical)
        if best:
            _, supplier, part, month, n, typical = best
            out.append(f"⚠️ **{part} repairs with {supplier} parts**: {n} comebacks in {month.strftime('%B')} "
                       f"vs a typical {typical:.0f} a month. Likely a bad batch, so raise it with the supplier.")

    # 4. Money to claim back
    recoverable, claims = supplier_recoverable(returns), int(returns["supplier_claim"].sum())
    if claims:
        out.append(f"**€{recoverable:,.0f}** in faulty parts and products ({claims} items) can be claimed back from suppliers.")

    # 5. Workmanship
    work = int((rep_r["reason"].map(responsibility) == "Workmanship").sum())
    if work:
        out.append(f"**{work}** comebacks ({work / max(len(rep_r), 1):.0%} of repair comebacks) were fitting issues: "
                   "a technician training opportunity rather than a parts problem.")

    flagged = int(returns["out_of_policy"].sum())
    if flagged:
        out.append(f"**{flagged}** returns were handled outside policy.")
    return out


# ── Supplier claims (faulty stock → supplier → replacement / credit) ─────────────

def claim_summary(claims) -> dict:
    """Money in each stage of the claims process."""
    status = claims["status"]
    closed = claims[status == "Closed"]
    rejected = closed["resolution"].str.startswith("Rejected", na=False)
    return {
        "in_faulty_stock": float(claims.loc[status == "In faulty stock", "value"].sum()),
        "with_suppliers": float(claims.loc[status == "Sent to supplier", "value"].sum()),
        "recovered": float(closed["recovered"].sum()),
        "rejected": float(closed.loc[rejected, "value"].sum()),
        "open_count": int((status != "Closed").sum()),
    }


def supplier_scorecard(claims) -> pd.DataFrame:
    """Per supplier: claims, acceptance rate, days to resolve, value recovered and still open."""
    if claims.empty:
        return pd.DataFrame()
    c = claims.assign(
        closed=claims["status"] == "Closed",
        accepted=(claims["status"] == "Closed") & ~claims["resolution"].str.startswith("Rejected", na=False),
        days=(claims["resolved_date"] - claims["sent_date"]).dt.days,
        open_value=claims["value"].where(claims["status"] != "Closed", 0),
    )
    g = c.groupby("supplier")
    df = pd.DataFrame({
        "claims": g.size(),
        "units": g["quantity"].sum(),
        "accepted_rate": g["accepted"].sum() / g["closed"].sum().replace(0, float("nan")),
        "avg_days_to_resolve": g["days"].mean(),
        "recovered": g["recovered"].sum(),
        "still_open": g["open_value"].sum(),
    })
    return df.reset_index().sort_values("claims", ascending=False)


def claim_insights(claims, today) -> list[str]:
    if claims.empty:
        return []
    out = []
    s = claim_summary(claims)
    out.append(f"**€{s['in_faulty_stock'] + s['with_suppliers']:,.0f}** of faulty stock is waiting to be recovered: "
               f"€{s['in_faulty_stock']:,.0f} still on the shelf and €{s['with_suppliers']:,.0f} with suppliers.")
    waiting = claims[claims["status"] == "In faulty stock"]
    if len(waiting):
        oldest = (pd.Timestamp(today) - waiting["created_date"].min()).days
        out.append(f"**{len(waiting)}** claims haven't been sent yet; the oldest has waited **{oldest} days**. "
                   "Send them in this week's supplier box.")
    card = supplier_scorecard(claims).dropna(subset=["avg_days_to_resolve"])
    if len(card) >= 2:
        slow = card.sort_values("avg_days_to_resolve").iloc[-1]
        fast = card.sort_values("avg_days_to_resolve").iloc[0]
        out.append(f"**{slow['supplier']}** takes **{slow['avg_days_to_resolve']:.0f} days** to settle a claim and accepts "
                   f"{slow['accepted_rate']:.0%}, vs {fast['avg_days_to_resolve']:.0f} days for {fast['supplier']}.")
    damaged = claims[claims["source"] == "Damaged on delivery"]
    if len(damaged):
        out.append(f"**{int(damaged['quantity'].sum())} units** arrived damaged in {len(damaged)} deliveries "
                   f"(€{damaged['value'].sum():,.0f} at cost).")
    return out
