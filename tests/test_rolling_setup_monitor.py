from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.rolling_setup_monitor import (
    _format_section_table,
    apply_setup_rating_updates,
    day_summary,
    derive_trigger_reference,
    detail_table,
    fail_day,
    format_monitor_table_html,
    format_summary_blocks_html,
    main_table,
    opening_range_result,
    opening_range_width_notes,
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


def _flush_then_trigger_intraday(after_low=9.6):
    return pd.DataFrame({
        'ticker': ['AAPL'] * 5,
        'trading_date': pd.to_datetime(['2026-05-01'] * 5),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:33',
            '2026-05-01 09:34',
        ]),
        'high': [10.0, 9.9, 10.6, 10.4, 10.5],
        'low': [9.8, 9.5, 9.7, after_low, 9.9],
        'close': [9.9, 9.7, 10.5, 10.2, 10.4],
    })


def _alt_required_intraday(after_15m_low=9.2):
    return pd.DataFrame({
        'ticker': ['AAPL'] * 8,
        'trading_date': pd.to_datetime(['2026-05-01'] * 8),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:33',
            '2026-05-01 09:35',
            '2026-05-01 09:36',
            '2026-05-01 09:46',
            '2026-05-01 09:47',
        ]),
        'high': [10.0, 9.9, 10.6, 10.4, 11.2, 11.0, 12.1, 12.0],
        'low': [9.8, 9.5, 9.7, 9.4, 10.9, 9.3, 11.5, after_15m_low],
        'close': [9.9, 9.7, 10.5, 10.2, 11.1, 10.8, 12.0, 11.8],
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


def test_1m_flush_then_orh_trigger_uses_trigger_time_low_and_stays_active():
    intraday = _flush_then_trigger_intraday(after_low=9.6)
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=False, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
    )
    failure = fail_day(intraday, _daily(lows=[10.1, 10.0, 10.2, 10.3]), out['trigger_break_time'], out['reference_low'])

    assert out['trigger_type'] == '1m ORH'
    assert out['reference_low'] == 9.5
    assert out['reference_basis'] == 'LOD at 1m Trigger'
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        1,
        out['trigger_type'],
        intraday,
    ) == 'success'
    assert failure is None
    assert status_for(out['trigger_type'], failure) == 'Active'


def test_1m_flush_then_orh_trigger_fails_when_trigger_time_low_breaks_afterward():
    intraday = _flush_then_trigger_intraday(after_low=9.4)
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=False, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
    )
    failure = fail_day(intraday, _daily(), out['trigger_break_time'], out['reference_low'])

    assert out['trigger_type'] == 'Failed OR Trigger'
    assert out['reference_low'] == 9.5
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        1,
        out['trigger_type'],
        intraday,
    ) == 'failed'
    assert failure == 0
    assert status_for(out['trigger_type'], failure) == 'Failed'


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


def test_5m_flush_then_orh_trigger_uses_trigger_time_low_and_stays_active():
    intraday = pd.DataFrame({
        'ticker': ['AAPL'] * 7,
        'trading_date': pd.to_datetime(['2026-05-01'] * 7),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:33',
            '2026-05-01 09:34',
            '2026-05-01 09:35',
            '2026-05-01 09:36',
        ]),
        'high': [10.0, 10.1, 10.2, 10.0, 10.1, 11.2, 11.0],
        'low': [9.9, 9.7, 9.4, 9.8, 9.6, 10.9, 9.5],
        'close': [10.0, 9.8, 9.7, 9.9, 10.0, 11.1, 10.8],
    })
    out = derive_trigger_reference(
        _or(broke_orh=False, broke_orl=True, orh=10.5, orl=9.8),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:32'),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
    )
    failure = fail_day(intraday, _daily(lows=[10.1, 10.0, 10.2, 10.3]), out['trigger_break_time'], out['reference_low'])

    assert out['trigger_type'] == '5m ORH'
    assert out['reference_low'] == 9.4
    assert out['reference_basis'] == 'LOD at 5m Trigger'
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:32'),
        5,
        out['trigger_type'],
        intraday,
    ) == 'success'
    assert failure is None


def test_5m_flush_then_orh_trigger_fails_when_trigger_time_low_breaks_afterward():
    intraday = pd.DataFrame({
        'ticker': ['AAPL'] * 7,
        'trading_date': pd.to_datetime(['2026-05-01'] * 7),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:33',
            '2026-05-01 09:34',
            '2026-05-01 09:35',
            '2026-05-01 09:36',
        ]),
        'high': [10.0, 10.1, 10.2, 10.0, 10.1, 11.2, 11.0],
        'low': [9.9, 9.7, 9.4, 9.8, 9.6, 10.9, 9.3],
        'close': [10.0, 9.8, 9.7, 9.9, 10.0, 11.1, 10.8],
    })
    out = derive_trigger_reference(
        _or(broke_orh=False, broke_orl=True, orh=10.5, orl=9.8),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:32'),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
    )
    failure = fail_day(intraday, _daily(), out['trigger_break_time'], out['reference_low'])

    assert out['trigger_type'] == 'Failed OR Trigger'
    assert out['reference_low'] == 9.4
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:32'),
        5,
        out['trigger_type'],
        intraday,
    ) == 'failed'
    assert failure == 0


def test_fail_day_uses_trigger_time_reference_low_not_original_orl():
    intraday = _flush_then_trigger_intraday(after_low=9.6)
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=False, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
    )

    assert out['reference_low'] == 9.5
    assert fail_day(intraday, _daily(), out['trigger_break_time'], out['reference_low']) is None
    assert fail_day(intraday, _daily(), out['trigger_break_time'], 9.8) == 0


def test_same_bar_orh_and_orl_break_is_not_clean():
    out = derive_trigger_reference(
        _or(
            broke_orh=True,
            broke_orl=True,
            orh_then_orl=False,
            same_bar_orh_orl_break=True,
            orh=10.5,
            orl=9.8,
            orh_break_time='2026-05-01 09:31',
            orl_break_time='2026-05-01 09:31',
        ),
        _or(broke_orh=False, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
    )

    assert out['trigger_type'] == 'No Trigger'
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, same_bar_orh_orl_break=True),
        1,
        out['trigger_type'],
    ) == 'failed'


def test_alt_required_uses_15m_references():
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=10.5, orl=9.8),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=11.0, orl=9.6),
        _or(broke_orh=True, orh=12.0, orl=9.2, orh_break_time='2026-05-01 09:48'),
        0.85,
    )

    assert out['trigger_type'] == 'Alt Required'
    assert out['trigger_level'] == 12.0
    assert out['reference_low'] == 9.2
    assert out['reference_basis'] == '15m OR Reference'


def test_failed_1m_and_5m_with_15m_break_and_high_close_selects_alt_required_active():
    intraday = _alt_required_intraday(after_15m_low=9.2)
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=12.0, orl=9.0, orh_break_time='2026-05-01 09:46'),
        0.85,
        intraday,
    )
    failure = fail_day(intraday, _daily(lows=[10.1, 10.0, 10.2, 10.3]), out['trigger_break_time'], out['reference_low'])

    assert out['trigger_type'] == 'Alt Required'
    assert out['trigger_level'] == 12.0
    assert out['reference_low'] == 9.0
    assert out['reference_basis'] == '15m OR Reference'
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        1,
        out['trigger_type'],
        intraday,
    ) == 'failed'
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:31'),
        5,
        out['trigger_type'],
        intraday,
    ) == 'failed'
    assert failure is None
    assert status_for(out['trigger_type'], failure) == 'Active'


def test_alt_required_failed_if_15m_reference_low_breaks_after_trigger():
    intraday = _alt_required_intraday(after_15m_low=8.9)
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=12.0, orl=9.0, orh_break_time='2026-05-01 09:46'),
        0.85,
        intraday,
    )
    failure = fail_day(intraday, _daily(), out['trigger_break_time'], out['reference_low'])

    assert out['trigger_type'] == 'Failed OR Trigger'
    assert failure == 0
    assert status_for(out['trigger_type'], failure) == 'Failed'


def test_failed_1m_and_5m_with_low_close_location_is_not_alt_required():
    intraday = _alt_required_intraday(after_15m_low=9.2)
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=12.0, orl=9.0, orh_break_time='2026-05-01 09:46'),
        0.50,
        intraday,
    )

    assert out['trigger_type'] == 'Failed OR Trigger'


def test_failed_or_trigger_uses_earliest_fail_day_from_primary_frameworks():
    intraday = pd.DataFrame({
        'ticker': ['AAPL'] * 8,
        'trading_date': pd.to_datetime(['2026-05-01'] * 8),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:35',
            '2026-05-01 09:36',
            '2026-05-01 09:37',
            '2026-05-01 09:38',
            '2026-05-01 09:39',
        ]),
        'high': [10.0, 10.6, 10.4, 11.2, 11.0, 11.0, 11.0, 11.0],
        'low': [9.8, 10.0, 9.7, 10.9, 9.7, 9.6, 10.5, 9.5],
        'close': [9.9, 10.5, 10.2, 11.1, 10.8, 10.7, 10.6, 10.5],
    })
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35'),
        _or(broke_orh=False, orh=12.0, orl=9.0),
        0.5,
        intraday,
    )

    assert out['trigger_type'] == 'Failed OR Trigger'
    assert out['failed_framework'] == '1m ORH'
    assert out['framework_fail_day'] == 0


def test_failed_or_trigger_uses_daily_fail_from_primary_framework():
    intraday = pd.DataFrame({
        'ticker': ['AAPL'] * 4,
        'trading_date': pd.to_datetime(['2026-05-01'] * 4),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:35',
            '2026-05-01 09:36',
        ]),
        'high': [10.0, 10.6, 11.2, 11.0],
        'low': [9.8, 10.0, 10.9, 10.7],
        'close': [9.9, 10.5, 11.1, 10.8],
    })
    daily = _daily(lows=[10.1, 9.7, 10.2, 10.3])
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35'),
        _or(broke_orh=False, orh=12.0, orl=9.0),
        0.5,
        intraday,
        daily,
    )

    assert out['trigger_type'] == 'Failed OR Trigger'
    assert out['failed_framework'] == '1m ORH'
    assert out['framework_fail_day'] == 1


def test_clean_1m_still_takes_priority_over_alt_required():
    intraday = _flush_then_trigger_intraday(after_low=9.6)
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh_then_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32'),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:36'),
        _or(broke_orh=True, broke_orl=False, orh=12.0, orl=9.0, orh_break_time='2026-05-01 09:46'),
        0.90,
        intraday,
    )

    assert out['trigger_type'] == '1m ORH'


def test_clean_5m_still_takes_priority_over_alt_required_when_1m_fails():
    intraday = pd.DataFrame({
        'ticker': ['AAPL'] * 6,
        'trading_date': pd.to_datetime(['2026-05-01'] * 6),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:35',
            '2026-05-01 09:46',
            '2026-05-01 09:47',
        ]),
        'high': [10.0, 10.6, 10.4, 11.2, 12.1, 12.0],
        'low': [9.8, 9.7, 9.4, 10.9, 11.5, 11.0],
        'close': [9.9, 10.5, 10.2, 11.1, 12.0, 11.8],
    })
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31', orl_break_time='2026-05-01 09:32'),
        _or(broke_orh=True, broke_orl=False, orh_then_orl=False, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35'),
        _or(broke_orh=True, broke_orl=False, orh=12.0, orl=9.0, orh_break_time='2026-05-01 09:46'),
        0.90,
        intraday,
    )

    assert out['trigger_type'] == '5m ORH'


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
    assert status_for('Failed OR Trigger', None) == 'Failed'
    assert status_for('No Trigger', None) == 'Unresolved'


def test_opening_range_display_results():
    assert opening_range_result(_or(broke_orh=True, orh_then_orl=False), 1, '1m ORH') == 'success'
    assert opening_range_result(_or(broke_orh=True, orh_then_orl=True), 1, '5m ORH') == 'failed'
    assert opening_range_result(_or(broke_orh=False), 1, 'No Trigger') == ''
    assert opening_range_result(_or(broke_orh=True, broke_orl=True), 5, 'Alt Required') == 'failed'


def test_wide_one_min_or_note_when_width_vs_atr_is_at_least_threshold():
    out = opening_range_width_notes(
        _or(orh=10.75, orl=10.00),
        _or(orh=11.00, orl=10.50),
        1.0,
    )

    assert out['one_min_or_width_vs_atr14'] == 0.75
    assert out['five_min_or_width_vs_atr14'] == 0.5
    assert out['notes'] == 'Wide 1m OR'


def test_wide_five_min_or_note_when_width_vs_atr_is_at_least_threshold():
    out = opening_range_width_notes(
        _or(orh=10.50, orl=10.00),
        _or(orh=11.25, orl=10.50),
        1.0,
    )

    assert out['notes'] == 'Wide 5m OR'


def test_no_wide_or_note_when_atr_missing_or_zero():
    missing = opening_range_width_notes(_or(orh=10.75, orl=10.00), _or(orh=11.25, orl=10.50), None)
    zero = opening_range_width_notes(_or(orh=10.75, orl=10.00), _or(orh=11.25, orl=10.50), 0)

    assert missing['notes'] == ''
    assert missing['one_min_or_width_vs_atr14'] is None
    assert zero['notes'] == ''
    assert zero['five_min_or_width_vs_atr14'] is None


def test_main_and_detail_table_columns_and_blank_handling():
    df = pd.DataFrame([{
        'candidate_id': 1,
        'Ticker': 'AAPL',
        'Status': 'Active',
        'Trigger': '1m ORH',
        '1m ORH': 'success',
        '5m ORH': '',
        'Notes': 'Wide 1m OR',
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
        'Range / ATR14': '',
        '1m OR Width / ATR14': '0.75',
        '5m OR Width / ATR14': '',
        'Close Bucket': '',
        '1m OR Result': 'success',
        '5m OR Result': '',
        'current_pct_raw': 0.01,
        'max_pct_raw': 0.03,
    }])

    assert main_table(df).columns.tolist() == [
        'Ticker', 'Status', 'Trigger', '1m ORH', '5m ORH', 'Notes', 'Current %', 'Max %',
        'D3 High %', 'Retest Day', 'Fail Day', 'Setup', 'Rating',
    ]
    assert detail_table(df).columns.tolist() == [
        'Ticker', 'Trigger Level', 'Reference Low', 'Reference Basis', 'Trigger Break Time',
        'Latest Close', 'Setup Close', 'Setup High', 'Setup Low', 'Current vs Setup Close',
        'Max Gain from Setup Close', 'RVOL', 'Range / ATR14', '1m OR Width / ATR14',
        '5m OR Width / ATR14', 'Close Bucket',
        '1m OR Result', '5m OR Result',
    ]
    assert main_table(df).loc[0, 'Rating'] == ''


def test_format_monitor_table_html_escapes_blanks_and_relabels_headers():
    df = pd.DataFrame([{
        'Ticker': '<ABC>',
        'Status': 'Active',
        'Trigger': 'Alt Required',
        '1m ORH': 'success',
        '5m ORH': 'failed',
        'Current %': float('nan'),
        'Retest Day': '',
    }])

    html = format_monitor_table_html(df)

    assert '<th>Ticker</th>' in html
    assert '<th>Current</th>' in html
    assert '<th>Retest</th>' in html
    assert '&lt;ABC&gt;' in html
    assert 'status-active' in html
    assert 'trigger-alt-required' in html
    assert 'result-success' in html
    assert 'result-failed' in html
    assert '<td>nan</td>' not in html
    assert 'height:' not in html
    assert 'overflow-y: scroll' not in html
    assert 'overflow-y: auto' not in html


def test_format_summary_blocks_html_includes_group_titles():
    summary = {
        'Setups': 3,
        'Active': 1,
        'Failed': 1,
        'Unresolved': 1,
        'Clean 1m': 1,
        '1m Failed': 1,
        'Clean 5m': 0,
        '5m Failed': 1,
        'Alt Required': 1,
        'No Trigger': 1,
        'Retested': 1,
        'Median Current %': '5.0%',
        'Median Max %': '15.0%',
        'Median D3 High %': '20.0%',
    }

    html = format_summary_blocks_html(summary)

    assert 'Overall' in html
    assert '1m OR' in html
    assert '5m OR' in html
    assert 'Alternate / Other' in html
    assert 'Follow-Through' in html
    assert 'Median D3 High' in html
    assert 'Active</span><strong>1 (33%)</strong>' in html
    assert 'Failed</span><strong>1 (33%)</strong>' in html
    assert 'Clean 5m</span><strong>0 (0%)</strong>' in html
    assert 'Median Current</span><strong>5.0%</strong>' in html
    assert 'Median Current</span><strong>5.0% (' not in html


def test_format_summary_blocks_html_uses_zero_percent_when_no_setups():
    html = format_summary_blocks_html({
        'Setups': 0,
        'Active': 0,
        'Failed': 0,
        'Unresolved': 0,
        'Clean 1m': 0,
        '1m Failed': 0,
        'Clean 5m': 0,
        '5m Failed': 0,
        'Alt Required': 0,
        'No Trigger': 0,
        'Retested': 0,
        'Median Current %': '',
        'Median Max %': '',
        'Median D3 High %': '',
    })

    assert 'Setups</span><strong>0</strong>' in html
    assert 'Active</span><strong>0 (0%)</strong>' in html
    assert 'Failed 1m</span><strong>0 (0%)</strong>' in html
    assert 'No Trigger</span><strong>0 (0%)</strong>' in html


def test_format_section_table_formats_nan_day_values_as_blank():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': '1m ORH',
        'one_min_result': 'success',
        'five_min_result': '',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': float('nan'),
        'fail_day': float('nan'),
        'setup': None,
        'rating': None,
        'trigger_level': 10.5,
        'reference_low': 9.8,
        'reference_basis': '1m OR',
        'trigger_break_time': None,
        'latest_close': 10.6,
        'close_price': 10.0,
        'high_price': 10.8,
        'low_price': 9.6,
        'current_pct_from_setup_close': 0.06,
        'max_gain_from_setup_close': 0.08,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': None,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Retest Day'] == ''
    assert table.loc[0, 'Fail Day'] == ''


def test_day_summary_metrics():
    df = pd.DataFrame([
        {'Trigger': '1m ORH', '1m ORH': 'success', '5m ORH': '', 'Status': 'Active', 'Retest Day': 'Day 1', 'current_pct_raw': 0.10, 'max_pct_raw': 0.20, 'd3_high_pct_raw': 0.25},
        {'Trigger': 'Alt Required', '1m ORH': 'failed', '5m ORH': 'failed', 'Status': 'Failed', 'Retest Day': '', 'current_pct_raw': 0.00, 'max_pct_raw': 0.10, 'd3_high_pct_raw': 0.15},
        {'Trigger': 'No Trigger', '1m ORH': '', '5m ORH': '', 'Status': 'Unresolved', 'Retest Day': '', 'current_pct_raw': None, 'max_pct_raw': None, 'd3_high_pct_raw': None},
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
    assert summary['Median D3 High %'] == '20.0%'


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
