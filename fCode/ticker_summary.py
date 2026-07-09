"""
ticker_summary.py
Single-call ticker summarizer. Reads tickers.csv (same directory), fetches data
via yfinance, and writes findings to ticker_summary.pdf.

Usage (one line):
    from ticker_summary import summarize; summarize()
or from the shell:
    python ticker_summary.py
    python -c "from ticker_summary import summarize; summarize()"

Columns: ticker, company_name, issue, currency, earliest_date, latest_date, one_yr_move_pct
- issue is taken from the tickers.csv Issue column (yfinance quoteType as fallback)
- company_name / currency come from tickers.csv if present, else yfinance,
  else history metadata, else (currency only) inferred from ticker suffix
- negative one-year moves shown in brackets, e.g. (12.34)
Requires: pip install yfinance pandas matplotlib
"""

import os
import sys
from datetime import datetime

import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from settings_paths import load_settings, resolve_data_path

SETTINGS = load_settings()
ROWS_PER_PAGE = 40
ERR_LINES_PER_PAGE = 55

# Yahoo suffix -> currency (used only as last-resort fallback)
SUFFIX_CURRENCY = {
    "TO": "CAD", "V": "CAD", "CN": "CAD", "NE": "CAD",   # Canadian venues
}
DEFAULT_CURRENCY = "USD"    # no suffix on Yahoo = US listing

# --- palette ---
HEADER_BG = "#1F4E79"
HEADER_FG = "white"
ROW_ALT_BG = "#DCE6F1"
ROW_BG = "white"
TITLE_COLOR = "#1F4E79"
SUBTITLE_COLOR = "#5A5A5A"
ERR_TITLE_COLOR = "#9C2B2B"
ERR_TEXT_COLOR = "#5A5A5A"


def _find_col(df, names):
    """Case/format-insensitive column lookup."""
    for c in df.columns:
        if c.strip().lower().replace("_", "").replace(" ", "") in names:
            return c
    return None


def _load_csv(csv_path, errors):
    """Return list of tickers plus per-ticker attributes from the CSV."""
    if not os.path.exists(csv_path):
        sys.exit(f"ERROR: {csv_path} not found.")
    df = pd.read_csv(csv_path)

    tcol = _find_col(df, ("ticker", "tickers", "symbol", "symbols")) or df.columns[0]
    icol = _find_col(df, ("issue",))
    ccol = _find_col(df, ("currency", "ccy"))
    ncol = _find_col(df, ("companyname", "company", "name"))

    df = df.dropna(subset=[tcol])
    df["_ticker"] = df[tcol].astype(str).str.strip().str.upper()
    df = df[df["_ticker"] != ""].drop_duplicates(subset="_ticker")

    csv_attrs = {}
    for _, r in df.iterrows():
        csv_attrs[r["_ticker"]] = {
            "issue": str(r[icol]).strip() if icol and pd.notna(r[icol]) else "",
            "currency": str(r[ccol]).strip() if ccol and pd.notna(r[ccol]) else "",
            "company_name": str(r[ncol]).strip() if ncol and pd.notna(r[ncol]) else "",
        }

    tickers = df["_ticker"].tolist()
    if not tickers:
        errors.append(f"{csv_path}: no tickers found in column '{tcol}'")
    return tickers, csv_attrs


def _suffix_currency(symbol):
    suffix = symbol.rsplit(".", 1)[1] if "." in symbol else ""
    return SUFFIX_CURRENCY.get(suffix, DEFAULT_CURRENCY if not suffix else "")


def _fmt_move(val):
    """Format percent move; negatives in brackets: (12.34)."""
    if val == "" or val is None:
        return ""
    return f"({abs(val):.2f})" if val < 0 else f"{val:.2f}"


def _summarize_ticker(symbol, csv_row, errors):
    row = {
        "ticker": symbol,
        "company_name": csv_row.get("company_name", ""),
        "issue": csv_row.get("issue", ""),          # CSV is the source for issue
        "currency": csv_row.get("currency", ""),
        "earliest_date": "",
        "latest_date": "",
        "one_yr_move_pct": "",
    }
    tk = yf.Ticker(symbol)

    try:
        info = tk.info or {}
        if not row["company_name"]:
            row["company_name"] = info.get("longName") or info.get("shortName") or ""
        if not row["issue"]:
            row["issue"] = info.get("quoteType") or ""
        if not row["currency"]:
            row["currency"] = info.get("currency") or ""
    except Exception as e:
        errors.append(f"{symbol}: info fetch failed ({e})")

    try:
        hist = tk.history(period="max", auto_adjust=False).dropna(subset=["Close"])

        # fallback: fill remaining gaps from history metadata
        try:
            meta = tk.history_metadata or {}
            if not row["company_name"]:
                row["company_name"] = (meta.get("longName")
                                       or meta.get("shortName") or "")
            if not row["issue"]:
                row["issue"] = meta.get("instrumentType") or ""
            if not row["currency"]:
                row["currency"] = meta.get("currency") or ""
        except Exception:
            pass

        if hist.empty:
            errors.append(f"{symbol}: no price history returned")
        else:
            earliest, latest = hist.index.min(), hist.index.max()
            row["earliest_date"] = earliest.date().isoformat()
            row["latest_date"] = latest.date().isoformat()

            one_year_ago = latest - pd.Timedelta(days=365)
            past = hist.loc[hist.index <= one_year_ago]
            base = past["Close"].iloc[-1] if not past.empty else hist["Close"].iloc[0]
            last = hist["Close"].iloc[-1]
            if base:
                row["one_yr_move_pct"] = round((last / base - 1) * 100, 2)
            else:
                errors.append(f"{symbol}: base price unavailable, "
                              f"1yr move not computed")
    except Exception as e:
        errors.append(f"{symbol}: history fetch failed ({e})")

    # last-resort fills so error rows are never blank
    if not row["currency"]:
        row["currency"] = _suffix_currency(symbol)
    if not row["company_name"]:
        row["company_name"] = "(name unavailable)"

    row["one_yr_move_pct"] = _fmt_move(row["one_yr_move_pct"])
    return row


def _new_page(generated_str, page_no, n_pages):
    """Fixed-size portrait page with title block and page number footer."""
    fig = plt.figure(figsize=(8.5, 11))
    fig.suptitle("Ticker Summary", fontsize=16, fontweight="bold",
                 color=TITLE_COLOR, y=0.97)
    fig.text(0.5, 0.94, f"Generated: {generated_str}", ha="center",
             fontsize=10, color=SUBTITLE_COLOR)
    fig.text(0.5, 0.025, f"{page_no} of {n_pages}", ha="center",
             fontsize=9, color=SUBTITLE_COLOR)
    ax = fig.add_axes([0.04, 0.06, 0.92, 0.86])
    ax.axis("off")
    return fig, ax


def _table_page(fig, ax, chunk, columns):
    table = ax.table(
        cellText=chunk.values,
        colLabels=columns,
        cellLoc="left",
        loc="upper left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.35)

    # deterministic column widths: proportional to longest entry, summing
    # to the full axes width so the table always fits the page exactly
    char_lens = [
        max([len(str(col))] + [len(str(v)) for v in chunk.iloc[:, i]])
        for i, col in enumerate(columns)
    ]
    total = sum(char_lens)
    widths = [max(l / total, 0.05) for l in char_lens]     # min 5% per column
    widths = [w / sum(widths) for w in widths]              # renormalize to 1.0
    for (r, c), cell in table.get_celld().items():
        cell.set_width(widths[c])

    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#B7C4D8")
        if r == 0:
            cell.set_facecolor(HEADER_BG)
            cell.set_text_props(weight="bold", color=HEADER_FG)
        else:
            cell.set_facecolor(ROW_ALT_BG if r % 2 == 0 else ROW_BG)


def _error_page(ax, err_lines):
    ax.text(0.5, 1.0, "Error Log", transform=ax.transAxes, ha="center",
            va="top", fontsize=13, fontweight="bold", color=ERR_TITLE_COLOR)
    text = "\n".join(err_lines) if err_lines else "No errors."
    ax.text(0.02, 0.94, text, transform=ax.transAxes,
            fontsize=8, color=ERR_TEXT_COLOR, va="top", family="monospace")


def _write_pdf(summary, errors, pdf_path, generated_str):
    table_chunks = [summary.iloc[i:i + ROWS_PER_PAGE]
                    for i in range(0, len(summary), ROWS_PER_PAGE)] or [summary]
    err_lines = ([f"{i}. {msg}" for i, msg in enumerate(errors, 1)]
                 if errors else ["No errors."])
    err_chunks = [err_lines[i:i + ERR_LINES_PER_PAGE]
                  for i in range(0, len(err_lines), ERR_LINES_PER_PAGE)]
    n_pages = len(table_chunks) + len(err_chunks)

    page_no = 0
    with PdfPages(pdf_path) as pdf:
        for chunk in table_chunks:
            page_no += 1
            fig, ax = _new_page(generated_str, page_no, n_pages)
            _table_page(fig, ax, chunk, summary.columns)
            pdf.savefig(fig)
            plt.close(fig)

        for err_chunk in err_chunks:
            page_no += 1
            fig, ax = _new_page(generated_str, page_no, n_pages)
            _error_page(ax, err_chunk)
            pdf.savefig(fig)
            plt.close(fig)


def summarize(csv_path=None, pdf_path=None):
    """Single-call entry point: read tickers, fetch data, write PDF."""
    csv_path = resolve_data_path(csv_path or "tickers.csv", SETTINGS)
    pdf_path = resolve_data_path(pdf_path or "ticker_summary.pdf", SETTINGS)

    errors = []
    tickers, csv_attrs = _load_csv(csv_path, errors)
    print(f"Found {len(tickers)} tickers in {csv_path}")

    rows = []
    for i, t in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {t} ...")
        rows.append(_summarize_ticker(t, csv_attrs.get(t, {}), errors))
    summary = pd.DataFrame(rows)

    generated_str = datetime.now().strftime("%B %d, %Y  %H:%M")
    _write_pdf(summary, errors, pdf_path, generated_str)

    print(f"Saved to {pdf_path}  ({len(errors)} error(s) logged)")
    return summary


if __name__ == "__main__":
    summarize()