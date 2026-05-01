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
Drop CSV/XLSX files into `data/watchlists/`.
Required: `ticker`.
Optional: `rating, setup, focus, key_level`.

Each file represents setup candidates for that setup date. The dashboard summarizes objective behavior such as VWAP, opening range outcomes, close location, ATR/RVOL context, and short D+1 to D+3 follow-through.

## Back-Watch Source Folder
Set `BACKWATCH_SOURCE_DIR` to your local TC2000/export folder. The app's Ingest Back-Watch page reads CSV/XLSX/XLS files from that folder, infers the setup date from the filename, previews normalized tickers, and saves a canonical CSV into `data/watchlists/`.

Recommended filename:
```text
YYYY-MM-DD_backwatch.xlsx
```

Accepted date patterns include `YYYY-MM-DD`, `YYYY_MM_DD`, `YYYYMMDD`, `MM-DD-YYYY`, and `M-D-YY`. If no date is found, the app asks for a manual setup date instead of assuming today.

## Commands
- Run pipeline: `python -m src.run_daily`
- Inspect DB counts: `python -m src.db_inspect`
- Run tests on Windows temp permission issues: `pytest -q --basetemp=.pytest_tmp`
- If OneDrive blocks pytest temp cleanup, use an external temp path: `pytest -q --basetemp=C:\Temp\wbm_pytest`
