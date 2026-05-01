# Watchlist Behavior Monitor

Lightweight Streamlit + DuckDB app to monitor watchlist behavior (not a backtester, not a trade journal).

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

## Commands
- Run pipeline: `python -m src.run_daily`
- Inspect DB counts: `python -m src.db_inspect`
- Run tests on Windows temp permission issues: `pytest -q --basetemp=.pytest_tmp`
- If OneDrive blocks pytest temp cleanup, use an external temp path: `pytest -q --basetemp=C:\Temp\wbm_pytest`
