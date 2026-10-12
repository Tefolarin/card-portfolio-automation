"""
clean_and_forecast.py

Automates what was previously a manual, multi-day process: taking raw,
inconsistent transaction exports from a premium credit card portfolio and
turning them into a clean dataset plus an executive-ready P&L forecast.

Pipeline:
  1. Load raw_transactions.csv
  2. Clean: standardize market names, normalize dates, dedupe, handle
     missing values, correct mislabeled refunds, winsorize outliers
  3. Aggregate monthly revenue and spend by market
  4. Forecast next 6 months of interchange revenue per market using a
     simple linear trend (adequate for a portfolio-level directional view)
  5. Write a multi-tab Excel workbook: Executive Summary, Cleaned Data
     sample, Monthly Trends, and Forecast

Run:
    python scripts/clean_and_forecast.py
"""

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw_transactions.csv"
CLEAN_PATH = ROOT / "data" / "clean_transactions.csv"
OUTPUT_XLSX = ROOT / "output" / "portfolio_executive_dashboard.xlsx"

MARKET_MAP = {
    "nigeria": "Nigeria", "ng": "Nigeria",
    "ghana": "Ghana", "gh": "Ghana",
    "kenya": "Kenya", "ke": "Kenya",
    "cote d'ivoire": "Cote d'Ivoire", "ci": "Cote d'Ivoire", "ivory coast": "Cote d'Ivoire",
    "senegal": "Senegal", "sn": "Senegal",
}

FORECAST_MONTHS = 6


def load_raw() -> pd.DataFrame:
    return pd.read_csv(RAW_PATH)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1. Drop exact duplicate rows
    before = len(df)
    df = df.drop_duplicates()
    dupes_removed = before - len(df)

    # 2. Normalize merchant_category text
    df["merchant_category"] = df["merchant_category"].astype(str).str.strip().str.title()
    df.loc[df["merchant_category"] == "Nan", "merchant_category"] = np.nan

    # 3. Normalize market names to a single canonical label per market
    df["market"] = (
        df["market"].astype(str).str.strip().str.lower().map(MARKET_MAP)
    )

    # 4. Parse transaction_date across multiple formats
    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"], errors="coerce", format="mixed", dayfirst=False
    )

    # 5. Drop rows with no usable date or market (can't be analyzed or attributed)
    before = len(df)
    df = df.dropna(subset=["transaction_date", "market"])
    unattributable_removed = before - len(df)

    # 6. Fix mislabeled refunds: spend_amount negative is a legitimate refund,
    #    keep as-is, but flag it as its own transaction_type for clarity
    df["transaction_type"] = np.where(df["spend_amount_usd"] < 0, "refund", "purchase")

    # 7. Impute missing spend_amount with the median for that merchant category
    df["spend_amount_usd"] = df.groupby("merchant_category")["spend_amount_usd"].transform(
        lambda s: s.fillna(s.median())
    )
    # Any category that was entirely missing: fall back to global median
    df["spend_amount_usd"] = df["spend_amount_usd"].fillna(df["spend_amount_usd"].median())

    # 8. Impute missing card_tier with portfolio mode
    df["card_tier"] = df["card_tier"].fillna(df["card_tier"].mode().iloc[0])

    # 9. Recompute interchange revenue for rows where it's missing or inconsistent
    #    (use a flat 2.1% assumption consistent with the generator's mean rate)
    implied_rate = 0.021
    missing_ir = df["interchange_revenue_usd"].isna()
    df.loc[missing_ir, "interchange_revenue_usd"] = (
        df.loc[missing_ir, "spend_amount_usd"].clip(lower=0) * implied_rate
    )

    # 10. Winsorize extreme spend outliers at the 0.5 / 99.5 percentile
    #     (caps, doesn't delete, so legitimate large luxury purchases survive)
    lower, upper = df["spend_amount_usd"].quantile([0.005, 0.995])
    outliers_capped = int(((df["spend_amount_usd"] < lower) | (df["spend_amount_usd"] > upper)).sum())
    df["spend_amount_usd"] = df["spend_amount_usd"].clip(lower=lower, upper=upper)

    df.attrs["dupes_removed"] = dupes_removed
    df.attrs["unattributable_removed"] = unattributable_removed
    df.attrs["outliers_capped"] = outliers_capped

    return df.reset_index(drop=True)


def monthly_trends(df: pd.DataFrame) -> pd.DataFrame:
    purchases = df[df["transaction_type"] == "purchase"].copy()
    purchases["month"] = purchases["transaction_date"].dt.to_period("M").dt.to_timestamp()
    agg = (
        purchases.groupby(["market", "month"])
        .agg(
            total_spend_usd=("spend_amount_usd", "sum"),
            interchange_revenue_usd=("interchange_revenue_usd", "sum"),
            transaction_count=("transaction_id", "count"),
        )
        .reset_index()
        .sort_values(["market", "month"])
    )
    return agg


def forecast_revenue(trends: pd.DataFrame, months_ahead: int = FORECAST_MONTHS) -> pd.DataFrame:
    """Simple per-market linear trend forecast on interchange revenue."""
    rows = []
    for market, g in trends.groupby("market"):
        g = g.sort_values("month").reset_index(drop=True)
        if len(g) < 3:
            continue
        x = np.arange(len(g))
        y = g["interchange_revenue_usd"].values
        slope, intercept = np.polyfit(x, y, 1)

        last_month = g["month"].iloc[-1]
        for i in range(1, months_ahead + 1):
            future_x = len(g) - 1 + i
            forecast_val = max(slope * future_x + intercept, 0)
            future_month = last_month + pd.DateOffset(months=i)
            rows.append({
                "market": market,
                "month": future_month,
                "forecast_interchange_revenue_usd": round(forecast_val, 2),
            })
    return pd.DataFrame(rows)


def executive_summary(df: pd.DataFrame, trends: pd.DataFrame, forecast: pd.DataFrame) -> pd.DataFrame:
    total_revenue = trends["interchange_revenue_usd"].sum()
    total_spend = trends["total_spend_usd"].sum()
    forecast_total = forecast["forecast_interchange_revenue_usd"].sum()

    by_market = (
        trends.groupby("market")["interchange_revenue_usd"].sum().sort_values(ascending=False)
    )
    top_market = by_market.index[0]
    top_market_share = by_market.iloc[0] / total_revenue

    summary_rows = [
        ("Rows in raw export", f"{df.attrs.get('_raw_rows', len(df)):,}"),
        ("Duplicate rows removed", f"{df.attrs.get('dupes_removed', 0):,}"),
        ("Unattributable rows dropped (bad date/market)", f"{df.attrs.get('unattributable_removed', 0):,}"),
        ("Extreme outliers capped (winsorized)", f"{df.attrs.get('outliers_capped', 0):,}"),
        ("Clean transactions analyzed", f"{len(df):,}"),
        ("Total historical spend (USD)", f"${total_spend:,.0f}"),
        ("Total historical interchange revenue (USD)", f"${total_revenue:,.0f}"),
        ("Top market by revenue", f"{top_market} ({top_market_share:.0%} of portfolio revenue)"),
        (f"Forecast interchange revenue, next {FORECAST_MONTHS} months (USD)", f"${forecast_total:,.0f}"),
    ]
    return pd.DataFrame(summary_rows, columns=["Metric", "Value"])


def write_workbook(df: pd.DataFrame, trends: pd.DataFrame, forecast: pd.DataFrame, summary: pd.DataFrame):
    OUTPUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_XLSX, engine="xlsxwriter") as writer:
        summary.to_excel(writer, sheet_name="Executive Summary", index=False)
        trends.to_excel(writer, sheet_name="Monthly Trends", index=False)
        forecast.to_excel(writer, sheet_name="6-Month Forecast", index=False)
        df.sample(min(2000, len(df)), random_state=1).sort_values("transaction_date").to_excel(
            writer, sheet_name="Clean Data Sample", index=False
        )

        workbook = writer.book
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "$#,##0"})

        ws = writer.sheets["Executive Summary"]
        ws.set_column("A:A", 48)
        ws.set_column("B:B", 30)
        ws.write(0, 0, "Metric", bold)
        ws.write(0, 1, "Value", bold)

        for sheet in ["Monthly Trends", "6-Month Forecast"]:
            ws = writer.sheets[sheet]
            ws.set_column("A:Z", 18)

    print(f"Wrote executive dashboard to {OUTPUT_XLSX}")


def main():
    raw = load_raw()
    cleaned = clean(raw)
    cleaned.attrs["_raw_rows"] = len(raw)
    cleaned.attrs["dupes_removed"] = cleaned.attrs.get("dupes_removed", 0)

    CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(CLEAN_PATH, index=False)

    trends = monthly_trends(cleaned)
    forecast = forecast_revenue(trends)
    summary = executive_summary(cleaned, trends, forecast)

    write_workbook(cleaned, trends, forecast, summary)

    print("\n--- Executive Summary ---")
    for _, row in summary.iterrows():
        print(f"{row['Metric']}: {row['Value']}")


if __name__ == "__main__":
    main()
