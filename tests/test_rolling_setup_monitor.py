from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.rolling_setup_monitor import (
    apply_setup_rating_updates,
    day_summary,
    derive_trigger_reference,
    detail_table,
    fail_day,
    main_table,
    opening_range_result,
    rating_dropdown_options,
    retest_day,
    setup_dropdown_options,
    sort_monitor_rows,
    status_for,
)


def _or(**kwargs):
    return json.dumps(kwargs)


def _intraday():
    return pd.DataFrame({
        'ticker': ['AAPL'] * 5,
        'trading_date': pd.to_datetime(['2026-05-01'] * 5),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:33',
            '2026-05-01 09:34',
            '2026-05-01 09:35',
        ]),
        'high': [10.6, 10.8, 10.7, 10.5, 10.3],
        'low': [10.2, 10.4, 10.1, 9.8, 9.4],
        'close': [10.5, 10.7, 10.2, 10.0, 9.6],
    })


def _daily(lows=None):
    lows = lows or [10.1, 10.2, 9.7, 9.6]
    return pd.DataFrame({
        'ticker': ['AAPL'] * 4,
        'trading_date': pd.to_datetime(['2026-05-01', '2026-05-04', '2026-05-05', '2026-05-06']),
        'high': [11.0, 11.4, 11.5, 11.2],
        'low': lows,
        'close': [10.8, 11.1, 10.9, 11.0],
    })


def test_clean_1m_orh_trigger_level_and_reference_low():
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh_then_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
    )

    assert out['trigger_type'] == '1m ORH'
    assert out['trigger_level'] == 10.5
    assert out['reference_low'] == 9.8
    assert out['reference_basis'] == '1m OR'
    assert out['trigger_break_time'] == pd.Timestamp('2026-05-01 09:31')


def test_clean_5m_fallback_trigger_level_and_reference_low():
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=10.5, orl=9.8),
        _or(broke_orh=True, broke_orl=False, orh_then_orl=False, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:36'),
        _or(orh=12.0, orl=9.2),
        0.5,
    )

    assert out['trigger_type'] == '5m ORH'
    assert out['trigger_level'] == 11.0
    assert out['reference_low'] == 9.6
    assert out['reference_basis'] == '5m OR'


def test_alt_required_uses_15m_references():
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=10.5, orl=9.8),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2, orh_break_time='2026-05-01 09:48'),
        0.85,
    )

    assert out['trigger_type'] == 'Alt Required'
    assert out['trigger_level'] == 12.0
    assert out['reference_low'] == 9.2
    assert out['reference_basis'] == '15m OR Reference'


def test_no_trigger_fallback():
    out = derive_trigger_reference(
        _or(broke_orh=False, broke_orl=True),
        _or(broke_orh=False, broke_orl=True),
        _or(orh=12.0, orl=9.2),
        0.4,
    )

    assert out['trigger_type'] == 'No Trigger'
    assert out['trigger_level'] is None
    assert out['reference_low'] is None
    assert out['reference_basis'] == 'Setup-Day Close fallback'


def test_fail_day_day0_after_trigger():
    assert fail_day(_intraday(), _daily(), pd.Timestamp('2026-05-01 09:31'), 9.9) == 0


def test_fail_day_day1():
    intraday = _intraday()
    daily = _daily(lows=[10.1, 9.7, 9.6, 9.5])

    assert fail_day(intraday, daily, pd.Timestamp('2026-05-01 09:35'), 9.9) == 1


def test_fail_day_no_fail():
    intraday = _intraday()
    daily = _daily(lows=[10.1, 10.0, 10.2, 10.3])

    assert fail_day(intraday, daily, pd.Timestamp('2026-05-01 09:35'), 9.9) is None


def test_retest_day_day0_after_trigger():
    assert retest_day(_intraday(), _daily(), pd.Timestamp('2026-05-01 09:31'), 10.2) == 0


def test_retest_day_day1():
    intraday = _intraday()
    daily = _daily(lows=[10.5, 10.2, 10.1, 10.0])

    assert retest_day(intraday, daily, pd.Timestamp('2026-05-01 09:35'), 10.25) == 1


def test_retest_without_failure():
    intraday = _intraday()
    daily = _daily(lows=[10.5, 10.2, 10.1, 10.0])

    assert retest_day(intraday, daily, pd.Timestamp('2026-05-01 09:35'), 10.25) == 1
    assert fail_day(intraday, daily, pd.Timestamp('2026-05-01 09:35'), 9.9) is None


def test_retest_day_no_retest():
    intraday = _intraday()
    daily = _daily(lows=[10.5, 10.4, 10.3, 10.2])

    assert retest_day(intraday, daily, pd.Timestamp('2026-05-01 09:35'), 10.0) is None


def test_status_values():
    assert status_for('1m ORH', None) == 'Active'
    assert status_for('5m ORH', 1) == 'Failed'
    assert status_for('No Trigger', None) == 'Unresolved'


def test_opening_range_display_results():
    assert opening_range_result(_or(broke_orh=True, orh_then_orl=False), 1, '1m ORH') == 'success'
    assert opening_range_result(_or(broke_orh=True, orh_then_orl=True), 1, '5m ORH') == 'failed'
    assert opening_range_result(_or(broke_orh=False), 1, 'No Trigger') == ''
    assert opening_range_result(_or(broke_orh=True, broke_orl=True), 5, 'Alt Required') == 'failed'


def test_main_and_detail_table_columns_and_blank_handling():
    df = pd.DataFrame([{
        'candidate_id': 1,
        'Ticker': 'AAPL',
        'Status': 'Active',
        'Trigger': '1m ORH',
        '1m ORH': 'success',
        '5m ORH': '',
        'Current %': '1.0%',
        'Max %': '3.0%',
        'D3 High %': '',
        'Retest Day': '',
        'Fail Day': '',
        'Setup': '',
        'Rating': '',
        'Trigger Level': '10.50',
        'Reference Low': '9.80',
        'Reference Basis': '1m OR',
        'Trigger Break Time': '2026-05-01 09:31',
        'Latest Close': '10.60',
        'Setup Close': '10.00',
        'Setup High': '10.80',
        'Setup Low': '9.60',
        'Current vs Setup Close': '6.0%',
        'Max Gain from Setup Close': '8.0%',
        'RVOL': '',
        'Range / ATR': '',
        'Close Bucket': '',
        '1m OR Result': 'success',
        '5m OR Result': '',
        'current_pct_raw': 0.01,
        'max_pct_raw': 0.03,
    }])

    assert main_table(df).columns.tolist() == [
        'Ticker', 'Status', 'Trigger', '1m ORH', '5m ORH', 'Current %', 'Max %',
        'D3 High %', 'Retest Day', 'Fail Day', 'Setup', 'Rating',
    ]
    assert detail_table(df).columns.tolist() == [
        'Ticker', 'Trigger Level', 'Reference Low', 'Reference Basis', 'Trigger Break Time',
        'Latest Close', 'Setup Close', 'Setup High', 'Setup Low', 'Current vs Setup Close',
        'Max Gain from Setup Close', 'RVOL', 'Range / ATR', 'Close Bucket',
        '1m OR Result', '5m OR Result',
    ]
    assert main_table(df).loc[0, 'Rating'] == ''


def test_day_summary_metrics():
    df = pd.DataFrame([
        {'Trigger': '1m ORH', '1m ORH': 'success', '5m ORH': '', 'Status': 'Active', 'Retest Day': 'Day 1', 'current_pct_raw': 0.10, 'max_pct_raw': 0.20},
        {'Trigger': 'Alt Required', '1m ORH': 'failed', '5m ORH': 'failed', 'Status': 'Failed', 'Retest Day': '', 'current_pct_raw': 0.00, 'max_pct_raw': 0.10},
        {'Trigger': 'No Trigger', '1m ORH': '', '5m ORH': '', 'Status': 'Unresolved', 'Retest Day': '', 'current_pct_raw': None, 'max_pct_raw': None},
    ])

    summary = day_summary(df)

    assert summary['Setups'] == 3
    assert summary['Clean 1m'] == 1
    assert summary['Alt Required'] == 1
    assert summary['No Trigger'] == 1
    assert summary['1m Failed'] == 1
    assert summary['5m Failed'] == 1
    assert summary['Active'] == 1
    assert summary['Failed'] == 1
    assert summary['Retested'] == 1
    assert summary['Median Current %'] == '5.0%'
    assert summary['Median Max %'] == '15.0%'


def test_sort_monitor_rows_status_then_current_pct():
    df = pd.DataFrame([
        {'Ticker': 'FAIL', 'Status': 'Failed', 'current_pct_raw': 0.50},
        {'Ticker': 'UNRES', 'Status': 'Unresolved', 'current_pct_raw': 0.30},
        {'Ticker': 'ACTIVE2', 'Status': 'Active', 'current_pct_raw': 0.10},
        {'Ticker': 'ACTIVE1', 'Status': 'Active', 'current_pct_raw': 0.20},
    ])

    out = sort_monitor_rows(df)

    assert out['Ticker'].tolist() == ['ACTIVE1', 'ACTIVE2', 'UNRES', 'FAIL']


def test_setup_dropdown_preserves_unknown_existing_value():
    df = pd.DataFrame({'Setup': ['Custom Pattern', 'EP'], 'Rating': ['7', '1']})

    assert 'Custom Pattern' in setup_dropdown_options(df)
    assert '7' in rating_dropdown_options(df)


def test_apply_setup_rating_updates_only_manual_fields():
    con = duckdb.connect(':memory:')
    con.execute('create table watchlist_candidates (candidate_id bigint, setup text, rating double, ticker text)')
    con.execute("insert into watchlist_candidates values (1, 'EP', 2, 'AAPL')")
    original = pd.DataFrame([{'candidate_id': 1, 'Setup': 'EP', 'Rating': '2', 'Status': 'Active'}])
    edited = pd.DataFrame([{'candidate_id': 1, 'Setup': 'Breakout', 'Rating': '3', 'Status': 'Failed'}])

    changed = apply_setup_rating_updates(con, original, edited)
    row = con.execute('select setup,rating,ticker from watchlist_candidates where candidate_id=1').fetchone()

    assert changed == 1
    assert row == ('Breakout', 3.0, 'AAPL')
