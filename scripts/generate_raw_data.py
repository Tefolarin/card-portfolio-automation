"""
generate_raw_data.py

Generates a synthetic, intentionally messy transaction-level dataset simulating
a premium credit card portfolio across five West African markets. This mirrors
the shape of real issuer/network portfolio data: card-level transactions with
merchant category, spend amount, fees, and market.

The dataset is fictional. No real cardholder, merchant, or institutional data
is used anywhere in this repository.

Messiness injected on purpose (to be resolved by clean_and_forecast.py):
  - Duplicate rows
  - Missing values in spend_amount, merchant_category, market
  - Inconsistent date formats
  - Inconsistent text casing / whitespace in categorical fields
  - A handful of extreme outlier transaction amounts
  - Negative amounts that should represent refunds but are mislabeled
  - Inconsistent market naming (e.g., "Nigeria" vs "NG" vs "nigeria ")
"""

import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(42)

N_ROWS = 60_000
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "raw_transactions.csv"

MARKETS = {
    "Nigeria": ["Nigeria", "NG", "nigeria ", "NIGERIA"],
    "Ghana": ["Ghana", "GH", "ghana", " Ghana"],
    "Kenya": ["Kenya", "KE", "kenya "],
    "Cote d'Ivoire": ["Cote d'Ivoire", "CI", "cote d'ivoire", "Ivory Coast"],
    "Senegal": ["Senegal", "SN", "senegal "],
}

MERCHANT_CATEGORIES = [
    "Travel & Airlines", "Fine Dining", "Luxury Retail", "Hotels & Lodging",
    "Fuel & Auto", "Grocery & Supermarket", "Electronics", "Entertainment",
    "Healthcare", "Online Marketplace",
]

CARD_TIERS = ["Platinum", "World Elite", "Signature"]

def random_dates(n):
    start = pd.Timestamp("2024-01-01")
    end = pd.Timestamp("2026-06-30")
    days = (end - start).days
    offsets = RNG.integers(0, days, size=n)
    dates = start + pd.to_timedelta(offsets, unit="D")
    # mix of date formats, inserted as strings
    fmt_choice = RNG.integers(0, 4, size=n)
    out = []
    for d, f in zip(dates, fmt_choice):
        if f == 0:
            out.append(d.strftime("%Y-%m-%d"))
        elif f == 1:
            out.append(d.strftime("%d/%m/%Y"))
        elif f == 2:
            out.append(d.strftime("%m-%d-%Y"))
        else:
            out.append(d.strftime("%d %b %Y"))
    return out


def build():
    n = N_ROWS
    card_ids = RNG.integers(100000, 199999, size=n)

    market_keys = RNG.choice(list(MARKETS.keys()), size=n, p=[0.4, 0.2, 0.15, 0.15, 0.1])
    market_messy = [RNG.choice(MARKETS[m]) for m in market_keys]

    category = RNG.choice(MERCHANT_CATEGORIES, size=n)
    tier = RNG.choice(CARD_TIERS, size=n, p=[0.5, 0.3, 0.2])

    # base spend by category (premium portfolio, so higher averages)
    base_mu = {
        "Travel & Airlines": 420, "Fine Dining": 110, "Luxury Retail": 350,
        "Hotels & Lodging": 300, "Fuel & Auto": 70, "Grocery & Supermarket": 85,
        "Electronics": 260, "Entertainment": 95, "Healthcare": 150,
        "Online Marketplace": 130,
    }
    spend = np.array([RNG.normal(base_mu[c], base_mu[c] * 0.35) for c in category])
    spend = np.clip(spend, 5, None)

    # inject extreme outliers (~0.1%)
    outlier_idx = RNG.choice(n, size=int(n * 0.001), replace=False)
    spend[outlier_idx] *= RNG.uniform(40, 90, size=len(outlier_idx))

    # mislabel some refunds as positive when they should be negative (~1.5%)
    refund_idx = RNG.choice(n, size=int(n * 0.015), replace=False)
    spend[refund_idx] = -np.abs(spend[refund_idx]) * RNG.uniform(0.2, 1.0, size=len(refund_idx))

    interchange_rate = RNG.normal(0.021, 0.004, size=n).clip(0.008, 0.035)
    interchange_revenue = np.where(spend > 0, spend * interchange_rate, 0)

    dates = random_dates(n)

    df = pd.DataFrame({
        "transaction_id": np.arange(1, n + 1),
        "card_id": card_ids,
        "card_tier": tier,
        "market": market_messy,
        "transaction_date": dates,
        "merchant_category": category,
        "spend_amount_usd": np.round(spend, 2),
        "interchange_revenue_usd": np.round(interchange_revenue, 2),
    })

    # randomly uppercase/lowercase/pad merchant_category to simulate messy source systems
    def mess_text(x):
        r = RNG.random()
        if r < 0.1:
            return x.upper()
        if r < 0.2:
            return x.lower()
        if r < 0.27:
            return f" {x} "
        return x

    df["merchant_category"] = df["merchant_category"].apply(mess_text)

    # inject missing values
    for col, frac in [("spend_amount_usd", 0.01), ("merchant_category", 0.015),
                       ("market", 0.008), ("card_tier", 0.01)]:
        idx = RNG.choice(n, size=int(n * frac), replace=False)
        df.loc[idx, col] = np.nan

    # inject duplicate rows (~1.2%)
    dup_sample = df.sample(frac=0.012, random_state=1)
    df = pd.concat([df, dup_sample], ignore_index=True)

    # shuffle
    df = df.sample(frac=1, random_state=7).reset_index(drop=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(df):,} rows to {OUT_PATH}")


if __name__ == "__main__":
    build()
