from __future__ import annotations

import pandas as pd

from src.data_quality import (
    build_data_health_summary,
    data_health_line,
    duplicate_candidate_keys,
    partial_intraday_sessions,
    partial_intraday_sessions_from_db,
)
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


def _insert_full_market_data(con) -> None:
    con.execute("""
        insert into watchlist_candidates
        values (1, '2026-05-01', 'AAPL', null, '', '', null, '2026-05-01_watchlist.csv', current_timestamp)
    """)
    con.execute("""
        insert into daily_bars
        values ('AAPL', '2026-05-01', 1, 1, 1, 1, 1, null, 'test', current_timestamp)
    """)
    rows = [
        ('AAPL', '2026-05-01', f'2026-05-01 09:{minute:02d}:00', 1, 1, 1, 1, 1, 'test')
        for minute in range(30, 60)
    ] + [
        ('AAPL', '2026-05-01', f'2026-05-01 10:{minute:02d}:00', 1, 1, 1, 1, 1, 'test')
        for minute in range(0, 60)
    ] + [
        ('AAPL', '2026-05-01', f'2026-05-01 11:{minute:02d}:00', 1, 1, 1, 1, 1, 'test')
        for minute in range(0, 60)
    ] + [
        ('AAPL', '2026-05-01', f'2026-05-01 12:{minute:02d}:00', 1, 1, 1, 1, 1, 'test')
        for minute in range(0, 60)
    ] + [
        ('AAPL', '2026-05-01', f'2026-05-01 13:{minute:02d}:00', 1, 1, 1, 1, 1, 'test')
        for minute in range(0, 60)
    ] + [
        ('AAPL', '2026-05-01', f'2026-05-01 14:{minute:02d}:00', 1, 1, 1, 1, 1, 'test')
        for minute in range(0, 60)
    ] + [
        ('AAPL', '2026-05-01', f'2026-05-01 15:{minute:02d}:00', 1, 1, 1, 1, 1, 'test')
        for minute in range(0, 60)
    ]
    con.executemany(
        """
        insert into intraday_bars_1m
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        """,
        rows,
    )


def test_data_health_summary_ok_when_core_data_has_no_obvious_issues():
    con = get_connection(':memory:')
    _insert_full_market_data(con)

    summary = build_data_health_summary(con)

    assert summary.status == 'OK'
    assert summary.latest_setup_date == '2026-05-01'
    assert summary.latest_daily_bar_date == '2026-05-01'
    assert summary.latest_intraday_bar_date == '2026-05-01'
    assert summary.candidate_rows == 1
    assert summary.duplicate_candidate_key_count == 0
    assert summary.partial_intraday_session_count == 0


def test_data_health_summary_check_data_when_duplicate_candidate_keys_exist():
    con = get_connection(':memory:')
    _insert_full_market_data(con)
    con.execute("""
        insert into watchlist_candidates
        values (2, '2026-05-01', 'AAPL', null, '', '', null, '2026-05-01_watchlist.csv', current_timestamp)
    """)

    summary = build_data_health_summary(con)

    assert summary.status == 'Check Data'
    assert summary.duplicate_candidate_key_count == 1


def test_data_health_summary_check_data_when_partial_intraday_sessions_exist():
    con = get_connection(':memory:')
    con.execute("""
        insert into watchlist_candidates
        values (1, '2026-05-01', 'AAPL', null, '', '', null, '2026-05-01_watchlist.csv', current_timestamp)
    """)
    con.execute("""
        insert into daily_bars
        values ('AAPL', '2026-05-01', 1, 1, 1, 1, 1, null, 'test', current_timestamp)
    """)
    con.execute("""
        insert into intraday_bars_1m
        values ('AAPL', '2026-05-01', '2026-05-01 09:35:00', 1, 1, 1, 1, 1, 'test', current_timestamp)
    """)

    summary = build_data_health_summary(con)

    assert summary.status == 'Check Data'
    assert summary.partial_intraday_session_count == 1


def test_data_health_summary_handles_missing_optional_market_tables_gracefully():
    con = get_connection(':memory:')
    con.execute("""
        insert into watchlist_candidates
        values (1, '2026-05-01', 'AAPL', null, '', '', null, '2026-05-01_watchlist.csv', current_timestamp)
    """)

    summary = build_data_health_summary(con)

    assert summary.status == 'Check Data'
    assert summary.latest_setup_date == '2026-05-01'
    assert summary.latest_daily_bar_date == '-'
    assert summary.latest_intraday_bar_date == '-'


def test_data_health_summary_handles_missing_setup_candidates_gracefully():
    con = get_connection(':memory:')

    summary = build_data_health_summary(con)

    assert summary.status == 'Check Data'
    assert summary.latest_setup_date == '-'
    assert summary.candidate_rows == 0


def test_data_health_line_formats_dates_as_yyyy_mm_dd():
    con = get_connection(':memory:')
    _insert_full_market_data(con)

    line = data_health_line(build_data_health_summary(con))

    assert 'Latest Setup: 2026-05-01' in line
    assert 'Daily Bars: 2026-05-01' in line
    assert 'Intraday: 2026-05-01' in line
