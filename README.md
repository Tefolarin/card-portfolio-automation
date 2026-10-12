# Premium Card Portfolio: Automated Cleaning & P&L Forecast

## The Business Problem

Issuer and network teams running a multi-market premium credit card portfolio typically receive transaction exports that are inconsistent across markets: mixed date formats, inconsistent market naming, missing fields, duplicate records, and the occasional extreme outlier transaction. Reconciling a monthly export like this manually, and then building a revenue forecast on top of it, is a multi-day task that has to be repeated every reporting cycle.

This is modeled on the kind of portfolio reporting problem I worked on managing the premium card P&L at Mastercard across five West African markets, where manual data reconciliation was consistently the bottleneck between "transactions happened" and "leadership has a number they can act on."

## The Technical Solution

A two-stage Python pipeline:

1. **`scripts/generate_raw_data.py`** — generates a synthetic, intentionally messy transaction dataset (~60,000 rows) simulating a premium card portfolio across five markets. All data is fictional; no real cardholder, merchant, or institutional data is used anywhere in this repository.
2. **`scripts/clean_and_forecast.py`** — the actual automation:
   - Standardizes market names and merchant category text across inconsistent source formats
   - Parses transaction dates across multiple formats
   - Removes duplicate records
   - Drops unattributable rows (no usable date or market)
   - Imputes missing spend amounts using category-level medians
   - Separates purchases from refunds
   - Recomputes missing interchange revenue using the portfolio's implied rate
   - Winsorizes extreme outlier transactions (caps rather than deletes, so legitimate high-value luxury spend survives)
   - Aggregates monthly spend and revenue by market
   - Forecasts next-6-month interchange revenue per market using a linear trend
   - Outputs a four-tab Excel workbook: Executive Summary, Monthly Trends, 6-Month Forecast, and a Clean Data Sample

## The Business Impact

On this synthetic run:

| Metric | Value |
|---|---|
| Raw export rows | 60,720 |
| Duplicate rows removed | 720 |
| Unattributable rows dropped | 480 |
| Extreme outliers capped | 596 |
| Clean transactions analyzed | 59,520 |
| Total historical interchange revenue | $258,090 |
| Top market by revenue | Nigeria (40% of portfolio) |
| 6-month forward revenue forecast | $18,027 |

What used to be a multi-day manual reconciliation becomes a single script run producing a leadership-ready workbook, with every cleaning decision documented and reproducible.

## Running It

```bash
pip install -r requirements.txt
python scripts/generate_raw_data.py      # generates data/raw_transactions.csv
python scripts/clean_and_forecast.py     # generates output/portfolio_executive_dashboard.xlsx
```

## Repository Structure

```
├── scripts/
│   ├── generate_raw_data.py       # synthetic messy data generator
│   └── clean_and_forecast.py      # cleaning + forecasting pipeline
├── data/                          # generated on run (not committed)
├── output/                        # generated dashboard (not committed)
├── requirements.txt
└── README.md
```

## Notes on the Data

All data in this repository is synthetically generated for demonstration purposes. Dollar figures, markets, and transaction patterns are illustrative and do not represent any real institution's financials. The full 60,000-row raw and cleaned datasets are reproducible by running the scripts; a 200-row sample (`data/sample_raw_transactions.csv`) is committed so the messiness is visible without running anything.

---
Built by [Tosin Folarin](https://www.linkedin.com/in/folarintosin/) — strategy and product leader across payments, card products, and management consulting.
