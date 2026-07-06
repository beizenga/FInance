"""
Create HLC/OHLC bar charts from prices.csv and write them to a PDF.

Expected prices.csv columns:
    Date, Symbol, Open, High, Low, Close, Volume
Volume is allowed but not required for this chart.

Expected tickers.csv columns:
    Ticker, CompanyName, Issue or Security, Market

Chart style:
    - vertical High-Low bar for each trading day
    - small left tick = Open
    - small right tick = Close
    - four charts per PDF page

Run:
    pip install pandas matplotlib
    python plot_hlc_pdf.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages


PRICES_FILE = "prices.csv"
TICKERS_FILE = "tickers.csv"
OUTPUT_PDF = "hlc_charts.pdf"

REQUIRED_PRICE_COLUMNS = {"Date", "Symbol", "Open", "High", "Low", "Close"}
REQUIRED_TICKER_COLUMNS = {"Ticker", "CompanyName", "Market"}


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from CSV column names."""
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    return df


def yahoo_symbol(ticker: str, market: str) -> str:
    """Build the complete Yahoo symbol using Ticker + Market suffix."""
    ticker = str(ticker).strip()
    market = "" if pd.isna(market) else str(market).strip()
    return f"{ticker}{market}"


def pick_security_column(tickers: pd.DataFrame) -> str | None:
    """Accept either Security or Issue as the descriptive security field."""
    for candidate in ["Security", "Issue", "Description"]:
        if candidate in tickers.columns:
            return candidate
    return None


def read_prices(path: str | Path) -> pd.DataFrame:
    prices = clean_columns(pd.read_csv(path))

    missing = REQUIRED_PRICE_COLUMNS - set(prices.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required columns: {sorted(missing)}"
        )

    prices["Date"] = pd.to_datetime(prices["Date"], errors="coerce")
    prices = prices.dropna(subset=["Date", "Symbol"])

    for col in ["Open", "High", "Low", "Close"]:
        prices[col] = pd.to_numeric(prices[col], errors="coerce")

    prices = prices.dropna(subset=["Open", "High", "Low", "Close"])
    prices["Symbol"] = prices["Symbol"].astype(str).str.strip()

    return prices


def read_tickers(path: str | Path) -> pd.DataFrame:
    tickers = clean_columns(pd.read_csv(path))

    missing = REQUIRED_TICKER_COLUMNS - set(tickers.columns)
    if missing:
        raise ValueError(
            f"{path} is missing required columns: {sorted(missing)}"
        )

    tickers["YahooSymbol"] = tickers.apply(
        lambda row: yahoo_symbol(row["Ticker"], row["Market"]), axis=1
    )

    security_col = pick_security_column(tickers)
    if security_col is None:
        tickers["Security"] = ""
    elif security_col != "Security":
        tickers["Security"] = tickers[security_col]

    for col in ["Ticker", "CompanyName", "Security", "Market", "YahooSymbol"]:
        tickers[col] = tickers[col].fillna("").astype(str).str.strip()

    return tickers


def title_for_symbol(symbol: str, tickers: pd.DataFrame) -> str:
    match = tickers[tickers["YahooSymbol"].str.upper() == symbol.upper()]

    if match.empty:
        return symbol

    row = match.iloc[0]
    company = row.get("CompanyName", "").strip()
    security = row.get("Security", "").strip()

    if company and security:
        return f"{company} - {security} ({symbol})"
    if company:
        return f"{company} ({symbol})"
    return symbol


def normalize_requested_symbols(
    requested: str,
    tickers: pd.DataFrame,
    prices: pd.DataFrame,
) -> list[str]:
    """
    Convert user input into Yahoo symbols.

    Blank input means all tickers from tickers.csv that have price data.
    Input may be Yahoo symbols like BMO.TO or base tickers like BMO.
    """
    available_symbols = set(prices["Symbol"].str.upper())

    if not requested.strip():
        ordered = []
        for symbol in tickers["YahooSymbol"]:
            if symbol.upper() in available_symbols and symbol not in ordered:
                ordered.append(symbol)
        return ordered

    selected: list[str] = []
    requested_items = [item.strip() for item in requested.split(",") if item.strip()]

    for item in requested_items:
        upper_item = item.upper()

        # User entered complete Yahoo symbol, e.g. BMO.TO
        if upper_item in available_symbols:
            selected.append(item)
            continue

        # User entered base ticker, e.g. BMO. Include matching ticker rows.
        matches = tickers[tickers["Ticker"].str.upper() == upper_item]
        for symbol in matches["YahooSymbol"]:
            if symbol.upper() in available_symbols:
                selected.append(symbol)

    # preserve order and remove duplicates
    unique = []
    seen = set()
    for symbol in selected:
        key = symbol.upper()
        if key not in seen:
            unique.append(symbol)
            seen.add(key)

    return unique


def plot_hlc_bars(ax, data: pd.DataFrame, title: str) -> None:
    """
    Draw HLC/OHLC bars:
        vertical line: Low to High
        left tick: Open
        right tick: Close
    """
    data = data.sort_values("Date").copy()
    dates = mdates.date2num(data["Date"])

    if len(dates) == 0:
        ax.set_title(title)
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    # Tick size is based on the chart span so daily and sparse data both work.
    date_span = max(dates.max() - dates.min(), 1)
    tick_width = max(date_span / 500, 0.15)

    # High-low vertical bars.
    ax.vlines(dates, data["Low"], data["High"], linewidth=0.6)

    # Open ticks to the left.
    ax.hlines(
        data["Open"],
        dates - tick_width,
        dates,
        linewidth=0.6,
    )

    # Close ticks to the right.
    ax.hlines(
        data["Close"],
        dates,
        dates + tick_width,
        linewidth=0.6,
    )

    ax.set_title(title, fontsize=9)
    ax.set_ylabel("Price", fontsize=8)
    ax.grid(True, linewidth=0.3, alpha=0.5)

    ax.xaxis_date()
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))

    ax.tick_params(axis="both", labelsize=7)


def create_hlc_pdf(
    symbols: Iterable[str],
    prices: pd.DataFrame,
    tickers: pd.DataFrame,
    output_pdf: str | Path = OUTPUT_PDF,
) -> None:
    symbols = list(symbols)

    if not symbols:
        raise ValueError("No matching symbols were found in prices.csv.")

    with PdfPages(output_pdf) as pdf:
        for page_start in range(0, len(symbols), 4):
            page_symbols = symbols[page_start:page_start + 4]
            fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
            axes = axes.flatten()

            for ax_index, ax in enumerate(axes):
                if ax_index >= len(page_symbols):
                    axes[ax_index].axis("off")
                    continue

                symbol = page_symbols[ax_index]
                data = prices[prices["Symbol"].str.upper() == symbol.upper()]
                title = title_for_symbol(symbol, tickers)
                plot_hlc_bars(ax, data, title)

            fig.suptitle("Price Charts", fontsize=12)
            fig.tight_layout(rect=[0, 0, 1, 0.96])
            pdf.savefig(fig)
            plt.close(fig)


def main() -> None:
    prices = read_prices(PRICES_FILE)
    tickers = read_tickers(TICKERS_FILE)

    requested = input(
        "Ticker(s) to plot, comma-separated. Leave blank for all available tickers: "
    )

    symbols = normalize_requested_symbols(requested, tickers, prices)

    create_hlc_pdf(symbols, prices, tickers, OUTPUT_PDF)

    print(f"Created {OUTPUT_PDF} with {len(symbols)} chart(s).")


if __name__ == "__main__":
    main()
