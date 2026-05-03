from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.or_trigger_audit import audit_for_candidate, setup_dates, tickers_for_setup_date


def _or(**kwargs):
    return json.dumps(kwargs)


def _con():
    con = duckdb.connect(':memory:')
    con.execute("""
        create table watchlist_candidates (
          candidate_id bigint,
          watchlist_date date,
          ticker text
        )
    """)
    con.execute("""
        create table entry_day_features (
          candidate_id bigint,
          watchlist_date date,
          ticker text,
          or_1m json,
          or_5m json,
          or_15m json,
          close_location double,
          open_price double
        )
    """)
    con.execute("""
        create table intraday_bars_1m (
          ticker text,
          trading_date date,
          timestamp_et timestamp,
          open double,
          high double,
          low double,
          close double,
          volume bigint,
          vwap double
        )
    """)
    con.execute("""
        create table daily_bars (
          ticker text,
          trading_date date,
          open double,
          high double,
          low double,
          close double,
          volume bigint
        )
    """)
    con.execute("insert into watchlist_candidates values (1, '2026-04-29', 'FCEL')")
    con.execute(
        "insert into entry_day_features values (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            1,
            '2026-04-29',
            'FCEL',
            _or(orh=1.10, orl=1.00, broke_orh=True, broke_orl=True, orh_break_time='2026-04-29 09:31:00', orl_break_time='2026-04-29 09:33:00', orh_then_orl=True),
            _or(orh=1.20, orl=0.95, broke_orh=True, broke_orl=False, orh_break_time='2026-04-29 09:35:00', orl_break_time=None, orh_then_orl=False),
            _or(orh=1.25, orl=0.90),
            0.7,
            1.2,
        ],
    )
    con.execute("insert into daily_bars values ('FCEL', '2026-04-28', 1.0, 1.15, 0.95, 1.05, 1000)")
    bars = pd.DataFrame({
        'ticker': ['FCEL'] * 7,
        'trading_date': ['2026-04-29'] * 7,
        'timestamp_et': pd.to_datetime([
            '2026-04-29 09:29:00',
            '2026-04-29 09:30:00',
            '2026-04-29 09:31:00',
            '2026-04-29 09:32:00',
            '2026-04-29 09:33:00',
            '2026-04-29 09:35:00',
            '2026-04-29 16:01:00',
        ]),
        'open': [1.0, 1.0, 1.1, 1.1, 1.0, 1.2, 1.3],
        'high': [1.2, 1.1, 1.11, 1.10, 1.05, 1.21, 1.4],
        'low': [0.9, 1.0, 1.05, 1.00, 0.99, 1.10, 1.2],
        'close': [1.0, 1.1, 1.08, 1.02, 1.0, 1.2, 1.3],
        'volume': [100, 100, 100, 100, 100, 100, 100],
        'vwap': [None] * 7,
    })
    con.register('bars_df', bars)
    con.execute('insert into intraday_bars_1m select * from bars_df')
    con.execute("insert into daily_bars values ('FCEL', '2026-04-29', 1.0, 1.3, 0.99, 1.2, 1000)")
    con.execute("insert into daily_bars values ('FCEL', '2026-04-30', 1.2, 1.4, 0.98, 1.3, 1000)")
    return con


def test_audit_selectors_list_setup_dates_and_tickers():
    con = _con()

    assert setup_dates(con) == ['2026-04-29']
    assert tickers_for_setup_date(con, '2026-04-29') == ['FCEL']


def test_audit_fields_and_break_rows_use_strict_comparisons():
    con = _con()

    audit = audit_for_candidate(con, '2026-04-29', 'FCEL')
    row = audit['audit'].iloc[0].to_dict()
    break_rows = audit['break_bars']

    assert row['Ticker'] == 'FCEL'
    assert row['Setup Date'] == '2026-04-29'
    assert row['1m ORH'] == '1.10'
    assert row['1m ORL'] == '1.00'
    assert row['1m OR Start'] == '2026-04-29 09:30:00'
    assert row['1m OR End'] == '2026-04-29 09:31:00'
    assert row['1m ORH Break Time'] == '2026-04-29 09:31:00'
    assert row['1m ORL Break After ORH Time'] == '2026-04-29 09:33:00'
    assert row['1m ORH Attempted'] == 'Yes'
    assert row['Trigger Mode'] == 'ORH stack active'
    assert row['Displayed 1m ORH'] == 'failed'
    assert row['Raw 1m ORH Result'] == 'failed'
    assert row['Prior Day High'] == '1.15'
    assert row['Setup Day Open'] == '1.20'
    assert row['Open Over PDH'] == 'Yes'
    assert row['Displayed PDH'] == '-'
    assert row['PDH Result'] == '-'
    assert row['5m ORH Attempted'] == 'Yes'
    assert row['Displayed 5m ORH'] == 'failed'
    assert row['Raw 5m ORH Result'] == 'failed'
    assert row['Alt Required Qualified'] == ''
    assert row['15m ORH'] == '1.25'
    assert row['15m ORL'] == '0.90'
    assert row['Selected Trigger'] == 'Failed OR Trigger'
    assert row['Trigger Level'] == '1.10'
    assert row['Reference Low'] == '1.00'
    assert row['Reference Basis'] == 'Failed LOD at 1m Trigger'
    assert row['Trigger Break Time'] == '2026-04-29 09:31:00'
    assert row['Final Trigger'] == 'Failed OR Trigger'
    assert row['Final Status'] == 'Failed'
    assert row['Final Fail Day'] == 'Day 0'
    assert len(audit['first_15_bars']) == 5
    assert not break_rows['Timestamp'].str.contains('09:32:00').any()
    assert break_rows['Timestamp'].str.contains('09:31:00').any()
    assert break_rows['Timestamp'].str.contains('09:33:00').any()
