"""
ticker_summary.py
Summarizes data for tickers listed in tickers.csv (same directory as this script).

Output columns:
    Ticker, CompanyName, Issue, Currency, EarliestDate, LatestDate, 1YrMovePct

Requires:  pip install yfinance pandas
"""

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from settings_paths import load_settings, resolve_data_path

SETTINGS = load_settings()
CSV_PATH = resolve_data_path("tickers.csv", SETTINGS)
OUT_PATH = resolve_data_path("ticker_summary.csv", SETTINGS)


def load_tickers(csv_path: str) -> list[str]:
    """Read tickers.csv and return a list of ticker symbols."""
    if not os.path.exists(csv_path):
        sys.exit(f"ERROR: {csv_path} not found.")

    df = pd.read_csv(csv_path)

    # Look for a column named Ticker/Symbol (case-insensitive); else use first column
    col = None
    for c in df.columns:
        if c.strip().lower() in ("ticker", "tickers", "symbol", "symbols"):
            col = c
            break
    if col is None:
        col = df.columns[0]

    tickers = (
        df[col]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
    )
    return [t for t in tickers if t]


def summarize_ticker(symbol: str) -> dict:
    """Fetch metadata and full price history for one ticker."""
    row = {
        "Ticker": symbol,
        "CompanyName": None,
        "Issue": None,
        "Currency": None,
        "EarliestDate": None,
        "LatestDate": None,
        "1YrMovePct": None,
    }

    tk = yf.Ticker(symbol)

    # --- Metadata ---
    try:
        info = tk.info or {}
        row["CompanyName"] = info.get("longName") or info.get("shortName")
        row["Issue"] = info.get("quoteType")       # e.g. EQUITY, ETF, MUTUALFUND
        row["Currency"] = info.get("currency")
    except Exception as e:
        print(f"  [warn] {symbol}: could not fetch info ({e})")

    # --- Full price history ---
    try:
        hist = tk.history(period="max", auto_adjust=False)
        if hist.empty:
            print(f"  [warn] {symbol}: no price history returned")
            return row

        hist = hist.dropna(subset=["Close"])
        earliest = hist.index.min()
        latest = hist.index.max()
        row["EarliestDate"] = earliest.date().isoformat()
        row["LatestDate"] = latest.date().isoformat()

        # --- 1-year price move ---
        one_year_ago = latest - pd.Timedelta(days=365)
        past = hist.loc[hist.index <= one_year_ago]
        if not past.empty:
            base_price = past["Close"].iloc[-1]        # last close on/before 1yr ago
        else:
            base_price = hist["Close"].iloc[0]          # ticker younger than 1 yr
        last_price = hist["Close"].iloc[-1]

        if base_price and base_price != 0:
            row["1YrMovePct"] = round((last_price / base_price - 1) * 100, 2)
    except Exception as e:
        print(f"  [warn] {symbol}: could not fetch history ({e})")

    return row


def main():
    tickers = load_tickers(CSV_PATH)
    print(f"Found {len(tickers)} tickers in {CSV_PATH}\n")

    rows = []
    for i, symbol in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {symbol} ...")
        rows.append(summarize_ticker(symbol))

    summary = pd.DataFrame(rows)

    # Display in console
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 160)
    print("\n=== SUMMARY ===")
    print(summary.to_string(index=False))

    # Save alongside the script
    summary.to_csv(OUT_PATH, index=False)
    print(f"\nSaved to {OUT_PATH}")


if __name__ == "__main__":
    main()