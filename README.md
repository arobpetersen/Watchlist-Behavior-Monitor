# Back-Watch Setup Behavior Monitor

Lightweight Streamlit + DuckDB app to monitor how a daily back-watch list of valid setup candidates behaved. It is a setup behavior monitor, not a backtester, not a trade journal, and not a record of trades taken.

## Windows setup
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.run_daily
streamlit run app.py
```

## Input
Canonical CSV files in `data/watchlists/` are the production files used by the app after Back-Watch source exports are normalized.
Required: `ticker`.
Optional: `rating, setup, focus, key_level`.

Each file represents setup candidates for that setup date. The dashboard summarizes objective behavior such as VWAP, opening range outcomes, close location, ATR14/RVOL context, and short D+1 to D+3 follow-through.

Sample data lives outside the production ingestion folder in `examples/sample_backwatch.csv`. Files with sample, example, or test in the filename are skipped by ingestion.

## Back-Watch Source Folder
Set `BACKWATCH_SOURCE_DIR` to your local TC2000/export folder. The main app page reads CSV/XLSX/XLS files from that folder, infers the setup date from the filename, previews normalized tickers, and saves a canonical CSV into `data/watchlists/`.

Recommended source folder:
```env
BACKWATCH_SOURCE_DIR=C:/Users/arobp/OneDrive/Documents/Trade/Watchlist-Behavior-Monitor-main/tc2000
```

If this repo is inside a nested `Watchlist-Behavior-Monitor` folder, the TC2000 export folder may still live one level above the app folder. When `BACKWATCH_SOURCE_DIR` is not set, the app checks `tc2000` under the app folder and then `../tc2000`.

Recommended filename:
```text
YYYY-MM-DD_backwatch.xlsx
```

Accepted date patterns include `YYYY-MM-DD`, `YYYY_MM_DD`, `YYYYMMDD`, `MM-DD-YYYY`, and `M-D-YY`. If no date is found, the app asks for a manual setup date instead of assuming today.

TC2000 one-column exports with the header `Symbols from TC2000` are supported.

Daily workflow:
1. Export TC2000 Back-Watch files into `BACKWATCH_SOURCE_DIR`.
2. Name files like `YYYY-MM-DD_backwatch.xlsx`.
3. Open Streamlit.
4. Click Process All New Back-Watch Files.
5. Review Daily Snapshot, Rolling Behavior, and Ticker Detail.

If a Back-Watch export was uploaded incorrectly, use the main app page's Maintenance / Reprocess expander. Select the corrected source file and click Reprocess Selected Back-Watch File. The app removes candidate rows tied to that canonical source file, keeps cached market bars, recreates the canonical CSV, re-ingests the file, and reruns metrics.

## Rolling Setup Monitor
The Rolling Setup Monitor page shows ticker-level monitoring for the last 5 setup dates. It uses a simple objective trigger reference ladder:

```text
Clean 1m ORH -> Clean 5m ORH -> Alternate Means Required using 15m ORH reference -> No Clean OR Trigger
```

It tracks current follow-through from the trigger reference when one exists, and from the setup-day close for all names. This page is for setup behavior monitoring only; it is not a trade journal or backtest.

## Commands
- Run pipeline: `python -m src.run_daily`
- Inspect DB counts: `python -m src.db_inspect`
- Remove sample/test/example candidate rows: `python -m src.data_maintenance --remove-samples`
- Run tests on Windows temp permission issues: `pytest -q --basetemp=.pytest_tmp`
- If OneDrive blocks pytest temp cleanup, use an external temp path: `pytest -q --basetemp=C:\Temp\wbm_pytest`
