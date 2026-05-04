from __future__ import annotations

import pandas as pd

from src.data_quality import duplicate_candidate_keys, partial_intraday_sessions, partial_intraday_sessions_from_db
from src.database import get_connection


def test_duplicate_candidate_keys_detects_natural_key_duplicates():
    con = get_connection(':memory:')
    con.execute("""
        insert into watchlist_candidates
        values
        (1, '2026-05-01', 'AAPL', null, '', '', null, '2026-05-01_watchlist.csv', current_timestamp),
        (2, '2026-05-01', 'AAPL', null, '', '', null, '2026-05-01_watchlist.csv', current_timestamp),
        (3, '2026-05-01', 'MSFT', null, '', '', null, '2026-05-01_watchlist.csv', current_timestamp)
    """)

    out = duplicate_candidate_keys(con)

    assert out.to_dict('records') == [{
        'Setup Date': '2026-05-01',
        'Ticker': 'AAPL',
        'Source File': '2026-05-01_watchlist.csv',
        'Rows': 2,
    }]


def test_duplicate_candidate_keys_empty_when_no_duplicates():
    con = get_connection(':memory:')
    con.execute("""
        insert into watchlist_candidates
        values
        (1, '2026-05-01', 'AAPL', null, '', '', null, '2026-05-01_watchlist.csv', current_timestamp),
        (2, '2026-05-01', 'AAPL', null, '', '', null, '2026-05-01_other.csv', current_timestamp)
    """)

    out = duplicate_candidate_keys(con)

    assert out.empty


def _bars(ticker: str, trading_date: str, times: list[str]) -> pd.DataFrame:
    return pd.DataFrame([
        {'ticker': ticker, 'trading_date': trading_date, 'timestamp_et': f'{trading_date} {time}'}
        for time in times
    ])


def test_partial_intraday_sessions_flags_very_low_bar_count():
    bars = _bars('AAPL', '2026-05-01', ['09:30:00', '09:31:00', '15:55:00'])

    out = partial_intraday_sessions(bars, min_regular_session_bars=10)

    assert out.loc[0, 'Ticker'] == 'AAPL'
    assert bool(out.loc[0, 'Very Low Bar Count']) is True
    assert 'very low bar count' in out.loc[0, 'Reasons']


def test_partial_intraday_sessions_flags_missing_open_period():
    bars = _bars('AAPL', '2026-05-01', ['09:35:00', '09:36:00', '15:55:00'])

    out = partial_intraday_sessions(bars, min_regular_session_bars=2)

    assert bool(out.loc[0, 'Missing Open Period']) is True
    assert 'missing open-period bars' in out.loc[0, 'Reasons']


def test_partial_intraday_sessions_flags_missing_late_session():
    bars = _bars('AAPL', '2026-05-01', ['09:30:00', '09:31:00', '15:54:00'])

    out = partial_intraday_sessions(bars, min_regular_session_bars=2)

    assert bool(out.loc[0, 'Missing Late Session']) is True
    assert 'missing late-session bars' in out.loc[0, 'Reasons']


def test_partial_intraday_sessions_ignores_full_session_shape():
    bars = _bars(
        'AAPL',
        '2026-05-01',
        ['09:30:00', '09:31:00', '09:32:00', '09:33:00', '09:34:00', '15:55:00', '15:56:00'],
    )

    out = partial_intraday_sessions(bars, min_regular_session_bars=7)

    assert out.empty


def test_partial_intraday_sessions_from_db_reads_cached_bars():
    con = get_connection(':memory:')
    con.execute("""
        insert into intraday_bars_1m
        values
        ('AAPL', '2026-05-01', '2026-05-01 09:35:00', 1, 1, 1, 1, 1, 'test', current_timestamp),
        ('AAPL', '2026-05-01', '2026-05-01 15:55:00', 1, 1, 1, 1, 1, 'test', current_timestamp)
    """)

    out = partial_intraday_sessions_from_db(con, min_regular_session_bars=2)

    assert out.loc[0, 'Ticker'] == 'AAPL'
    assert bool(out.loc[0, 'Missing Open Period']) is True
