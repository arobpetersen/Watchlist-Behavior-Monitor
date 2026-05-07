from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.database import get_connection
from src.run_daily import run_daily_pipeline


def _empty_ingest() -> dict:
    return {
        'files_scanned': 0,
        'candidates_inserted': 0,
        'skipped_sample_files': 0,
        'skipped_weekend_files': 0,
        'failures': [],
    }


def test_read_timeout_for_one_ticker_does_not_stop_other_tickers(tmp_path: Path, monkeypatch):
    db_path = tmp_path / 'watchlist.duckdb'
    watchlists_dir = tmp_path / 'watchlists'
    watchlists_dir.mkdir()
    con = get_connection(str(db_path))
    con.execute(
        """
        insert into watchlist_candidates values
        (1, '2026-05-06', 'OKLO', null, '', '', null, '2026-05-06_backwatch.csv', current_timestamp),
        (2, '2026-05-06', 'MSFT', null, '', '', null, '2026-05-06_backwatch.csv', current_timestamp)
        """
    )
    con.close()

    calls = []

    class FakeMassiveClient:
        def __init__(self, api_key, base_url):
            pass

        def fetch_intraday_1m(self, ticker, trading_date):
            calls.append(('intraday', ticker, str(trading_date)))
            if ticker == 'OKLO':
                raise RuntimeError('OKLO: market-data fetch timed out; retry later.')
            return pd.DataFrame(
                [
                    {
                        'ticker': ticker,
                        'trading_date': str(trading_date),
                        'timestamp_et': datetime(2026, 5, 6, 9, 30),
                        'open': 10.0,
                        'high': 10.5,
                        'low': 9.9,
                        'close': 10.2,
                        'volume': 1000,
                        'source': 'massive',
                        'fetched_at': datetime.now(timezone.utc),
                    }
                ]
            )

        def fetch_daily(self, ticker, from_date, to_date):
            calls.append(('daily', ticker, str(from_date), str(to_date)))
            return pd.DataFrame()

    monkeypatch.setattr(
        'src.run_daily.get_settings',
        lambda: SimpleNamespace(
            db_path=db_path,
            watchlists_dir=watchlists_dir,
            massive_api_key='secret-key',
            massive_base_url='https://api.polygon.io',
        ),
    )
    monkeypatch.setattr('src.run_daily.MassiveClient', FakeMassiveClient)
    monkeypatch.setattr('src.run_daily.compute_features', lambda con, candidate: False)
    monkeypatch.setattr('src.run_daily.assign_labels_for_date', lambda con, d: 0)

    summary = run_daily_pipeline(_empty_ingest())
    con = get_connection(str(db_path))

    assert summary['failures'] == ['OKLO: market-data fetch timed out; retry later.']
    assert summary['bars_fetched'] == 1
    assert ('intraday', 'MSFT', '2026-05-06 00:00:00') in calls
    assert con.execute("select count(*) from intraday_bars_1m where ticker='MSFT'").fetchone()[0] == 1
    assert con.execute("select count(*) from intraday_bars_1m where ticker='OKLO'").fetchone()[0] == 0
    assert con.execute("select count(*) from entry_day_features where ticker='OKLO'").fetchone()[0] == 0
