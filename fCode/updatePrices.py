import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import date

from settings_paths import load_settings, resolve_data_path

SETTINGS = load_settings()
TICKERS_FILE = resolve_data_path("tickers.csv", SETTINGS)
PRICES_FILE = resolve_data_path("prices.csv", SETTINGS)
START_DATE = "2023-01-01"
END_DATE = date.today().isoformat()   # yfinance end date is exclusive; script adds 1 day below

REQUIRED_PRICE_COLUMNS = ["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def yahoo_symbol(row: pd.Series) -> str:
    ticker = str(row["Ticker"]).strip()
    market = "" if pd.isna(row.get("Market", "")) else str(row.get("Market", "")).strip()
    return f"{ticker}{market}"


def load_tickers() -> list[str]:
    tickers = clean_columns(pd.read_csv(TICKERS_FILE))

    if "Ticker" not in tickers.columns:
        raise ValueError("tickers.csv must contain a Ticker column")

    if "Market" not in tickers.columns:
        tickers["Market"] = ""

    tickers["Symbol"] = tickers.apply(yahoo_symbol, axis=1)
    return sorted(tickers["Symbol"].dropna().drop_duplicates().tolist())


def load_prices() -> pd.DataFrame:
    if PRICES_FILE.exists():
        prices = clean_columns(pd.read_csv(PRICES_FILE))
    else:
        prices = pd.DataFrame(columns=REQUIRED_PRICE_COLUMNS)

    for col in REQUIRED_PRICE_COLUMNS:
        if col not in prices.columns:
            prices[col] = pd.NA

    prices = prices[REQUIRED_PRICE_COLUMNS]
    prices["Date"] = pd.to_datetime(prices["Date"], errors="coerce").dt.date
    prices["Symbol"] = prices["Symbol"].astype(str).str.strip()
    prices = prices.dropna(subset=["Date", "Symbol"])

    return prices


def existing_dates_by_symbol(prices: pd.DataFrame) -> dict[str, set]:
    if prices.empty:
        return {}
    return prices.groupby("Symbol")["Date"].apply(set).to_dict()


def download_symbol(symbol: str) -> pd.DataFrame:
    # Add one day because yfinance treats end as exclusive.
    end_exclusive = (pd.Timestamp.today().normalize() + pd.Timedelta(days=1)).date().isoformat()

    data = yf.download(
        symbol,
        start=START_DATE,
        end=end_exclusive,
        progress=False,
        auto_adjust=False,
        actions=False,
    )

    if data.empty:
        return pd.DataFrame(columns=REQUIRED_PRICE_COLUMNS)

    # yfinance can return multi-index columns in some versions.
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()
    data["Date"] = pd.to_datetime(data["Date"]).dt.date
    data["Symbol"] = symbol

    return data[["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]]


def main() -> None:
    symbols = load_tickers()
    prices = load_prices()
    existing = existing_dates_by_symbol(prices)

    new_rows = []

    for symbol in symbols:
        print(f"Checking {symbol}...")
        downloaded = download_symbol(symbol)

        if downloaded.empty:
            print(f"  No data returned for {symbol}")
            continue

        have_dates = existing.get(symbol, set())
        missing = downloaded[~downloaded["Date"].isin(have_dates)].copy()

        if missing.empty:
            print(f"  No missing rows")
        else:
            print(f"  Adding {len(missing)} rows")
            new_rows.append(missing)

    if new_rows:
        prices = pd.concat([prices, *new_rows], ignore_index=True)
        prices = prices.drop_duplicates(subset=["Date", "Symbol"], keep="last")
        prices = prices.sort_values(["Symbol", "Date"])

        # Optional rounding to keep the CSV readable.
        for col in ["Open", "High", "Low", "Close"]:
            prices[col] = pd.to_numeric(prices[col], errors="coerce").round(4)
        prices["Volume"] = pd.to_numeric(prices["Volume"], errors="coerce").astype("Int64")

        prices.to_csv(PRICES_FILE, index=False)
        print(f"Saved {len(prices)} total rows to {PRICES_FILE}")
    else:
        print("No new rows needed.")


if __name__ == "__main__":
    main()
