from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.rolling_setup_monitor import (
    _format_section_table,
    _follow_through,
    _vwap_reclaim_fields,
    apply_setup_rating_updates,
    apply_weak_close_note,
    day_summary,
    derive_trigger_reference,
    detail_table,
    entry_tactic_dropdown_options,
    fail_day,
    format_monitor_table_html,
    format_summary_blocks_html,
    main_table,
    opening_range_result,
    opening_range_width_notes,
    orh_trigger_assessment,
    apply_one_min_quality_notes,
    one_min_follow_through_atr,
    pdh_trigger_assessment,
    rating_dropdown_options,
    retest_day,
    retest_events,
    setup_dropdown_options,
    sort_monitor_rows,
    status_for,
    current_status_display,
    trigger_day_status,
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


def _base_formatted_record():
    return {
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': '1m ORH',
        'pdh_result': '',
        'one_min_result': 'success',
        'five_min_result': '',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
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
    }


def _pdh_intraday(lows_after_trigger=None, highs=None):
    lows_after_trigger = lows_after_trigger or [10.6, 10.8]
    highs = highs or [10.1, 10.6, 11.2, 11.4]
    return pd.DataFrame({
        'ticker': ['AAPL'] * 4,
        'trading_date': pd.to_datetime(['2026-05-01'] * 4),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:33',
        ]),
        'open': [10.0, 10.2, 10.8, 11.0],
        'high': highs,
        'low': [9.8, 9.9, *lows_after_trigger],
        'close': [10.0, 10.4, 11.0, 11.2],
    })


def _pdh_failed_recovery_intraday(highs=None, lows=None):
    highs = highs or [9.9, 10.2, 10.4, 10.7, 10.8, 11.2, 11.0]
    lows = lows or [9.8, 9.7, 9.6, 9.9, 10.0, 10.4, 10.2]
    return pd.DataFrame({
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
        'open': [9.8, 9.9, 10.1, 10.5, 10.6, 11.0, 10.9],
        'high': highs,
        'low': lows,
        'close': [9.9, 10.1, 9.8, 10.6, 10.7, 11.0, 10.8],
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


def test_pdh_result_gap_when_open_over_prior_day_high():
    out = pdh_trigger_assessment(9.9, 10.0, _pdh_intraday(), _daily())

    assert out['pdh_result'] == 'Gap'
    assert out['open_over_pdh'] is True


def test_pdh_break_holds_selects_pdh_trigger():
    intraday = _pdh_intraday()
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35'),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        11.0,
        10.0,
    )

    assert out['trigger_type'] == 'PDH'
    assert out['pdh_result'] == 'success'
    assert out['trigger_level'] == 11.0
    assert out['reference_low'] == 9.8
    assert out['reference_basis'] == 'LOD at PDH Trigger'


def test_pdh_break_fails_day0_selects_failed_pdh_trigger():
    intraday = _pdh_intraday(lows_after_trigger=[10.6, 9.7])
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35'),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        11.0,
        10.0,
    )

    assert out['trigger_type'] == 'Failed PDH Trigger'
    assert out['pdh_result'] == 'failed'
    assert out['framework_fail_day'] == 0
    assert status_for(out['trigger_type'], out['framework_fail_day']) == 'Failed'


def test_pdh_break_fails_day1_stays_trigger_day_success_with_failed_d1_status():
    intraday = _pdh_intraday()
    out = derive_trigger_reference(
        _or(broke_orh=False, broke_orl=False, orh=10.5, orl=9.8),
        _or(broke_orh=False, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
        _daily(lows=[10.1, 9.7, 10.3, 10.4]),
        11.0,
        10.0,
    )
    failure = fail_day(intraday, _daily(lows=[10.1, 9.7, 10.3, 10.4]), out['trigger_break_time'], out['reference_low'])
    trigger_day = trigger_day_status(out['trigger_type'], failure)

    assert out['trigger_type'] == 'PDH'
    assert failure == 1
    assert trigger_day == 'Success'
    assert current_status_display(trigger_day, failure) == 'Failed D1'


def test_failed_pdh_allows_1m_recovery_after_pdh_failure():
    intraday = _pdh_failed_recovery_intraday()
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh=10.5, orl=9.8),
        _or(broke_orh=True, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=11.5, orl=9.5),
        0.5,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        10.0,
        9.8,
    )

    assert out['pdh_result'] == 'failed'
    assert out['trigger_type'] == '1m ORH'
    assert out['pdh_recovery_trigger'] == '1m ORH'
    assert out['one_recovery_qualified'] is True
    assert out['trigger_break_time'] == pd.Timestamp('2026-05-01 09:33')
    assert out['reference_low'] == 9.6
    assert out['reference_basis'] == 'LOD at 1m Recovery Trigger'


def test_failed_pdh_allows_5m_recovery_and_later_d1_failure():
    intraday = _pdh_failed_recovery_intraday(highs=[9.9, 10.2, 10.4, 10.6, 10.8, 11.2, 11.0])
    daily = _daily(lows=[10.1, 9.5, 10.2, 10.3])
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh=10.0, orl=9.8),
        _or(broke_orh=True, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=11.5, orl=9.5),
        0.5,
        intraday,
        daily,
        10.0,
        9.8,
    )
    failure = fail_day(intraday, daily, out['trigger_break_time'], out['reference_low'])
    trigger_day = trigger_day_status(out['trigger_type'], failure)

    assert out['trigger_type'] == '5m ORH'
    assert out['pdh_recovery_trigger'] == '5m ORH'
    assert out['one_recovery_qualified'] is False
    assert out['five_recovery_qualified'] is True
    assert out['trigger_break_time'] == pd.Timestamp('2026-05-01 09:35')
    assert trigger_day == 'Success'
    assert current_status_display(trigger_day, failure) == 'Failed D1'


def test_failed_pdh_allows_alt_required_recovery():
    intraday = _pdh_failed_recovery_intraday(highs=[9.9, 10.2, 10.4, 10.6, 10.8, 11.0, 11.6])
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh=10.0, orl=9.8),
        _or(broke_orh=False, broke_orl=False, orh=10.0, orl=9.6),
        _or(broke_orh=True, broke_orl=False, orh=11.5, orl=9.5),
        0.85,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        10.0,
        9.8,
    )

    assert out['trigger_type'] == 'Alt Required'
    assert out['pdh_recovery_trigger'] == 'Alt Required'
    assert out['alt_recovery_qualified'] is True
    assert out['reference_low'] == 9.5
    assert out['reference_basis'] == '15m OR Reference'


def test_failed_pdh_without_recovery_stays_failed_pdh_trigger():
    intraday = _pdh_failed_recovery_intraday(highs=[9.9, 10.2, 10.4, 10.6, 10.8, 11.0, 11.1])
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh=10.0, orl=9.8),
        _or(broke_orh=False, broke_orl=False, orh=10.0, orl=9.6),
        _or(broke_orh=False, broke_orl=False, orh=11.5, orl=9.5),
        0.5,
        intraday,
        _daily(),
        10.0,
        9.8,
    )

    assert out['trigger_type'] == 'Failed PDH Trigger'
    assert out['framework_fail_day'] == 0
    assert out['one_recovery_qualified'] is False
    assert out['five_recovery_qualified'] is False
    assert out['alt_recovery_qualified'] is False


def test_failed_pdh_recovery_requires_level_above_pdh_after_failure_and_day0_hold():
    before_failure_break = _pdh_failed_recovery_intraday(highs=[9.9, 10.7, 10.4, 10.6, 10.8, 11.0, 11.1])
    low_level = _pdh_failed_recovery_intraday()
    fails_after_recovery = _pdh_failed_recovery_intraday(lows=[9.8, 9.7, 9.6, 9.9, 10.0, 10.4, 9.5])

    before = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh=10.5, orl=9.8),
        _or(broke_orh=False, broke_orl=False, orh=10.0, orl=9.6),
        _or(orh=11.5, orl=9.5),
        0.5,
        before_failure_break,
        _daily(),
        10.0,
        9.8,
    )
    low = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh=10.0, orl=9.8),
        _or(broke_orh=True, broke_orl=False, orh=10.0, orl=9.6),
        _or(orh=11.5, orl=9.5),
        0.5,
        low_level,
        _daily(),
        10.0,
        9.8,
    )
    broken_ref = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh=10.5, orl=9.8),
        _or(broke_orh=False, broke_orl=False, orh=10.0, orl=9.6),
        _or(orh=11.5, orl=9.5),
        0.5,
        fails_after_recovery,
        _daily(),
        10.0,
        9.8,
    )

    assert before['trigger_type'] == 'Failed PDH Trigger'
    assert low['trigger_type'] == 'Failed PDH Trigger'
    assert broken_ref['trigger_type'] == 'Failed PDH Trigger'


def test_pdh_governed_display_hides_orh_results_but_detail_keeps_raw_diagnostics():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'ATOM',
        'status': 'Active',
        'trigger_type': 'PDH',
        'pdh_result': 'success',
        'pdh_governed': True,
        'one_min_result': '-',
        'five_min_result': '-',
        'raw_one_min_result': 'failed',
        'raw_five_min_result': 'success',
        'notes': '',
        'current_pct': 0.05,
        'max_pct': 0.10,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': '',
        'rating': None,
        'prior_day_high': 10.0,
        'setup_day_open': 9.8,
        'open_over_pdh': False,
        'pdh_trigger_break_time': pd.Timestamp('2026-05-01 09:32'),
        'pdh_trigger_level': 10.0,
        'pdh_reference_low': 9.6,
        'pdh_reference_basis': 'LOD at PDH Trigger',
        'trigger_level': 10.0,
        'reference_low': 9.6,
        'reference_basis': 'LOD at PDH Trigger',
        'trigger_break_time': pd.Timestamp('2026-05-01 09:32'),
        'latest_close': 10.5,
        'close_price': 10.2,
        'high_price': 10.8,
        'low_price': 9.6,
        'current_pct_from_setup_close': 0.03,
        'max_gain_from_setup_close': 0.06,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': 0.8,
        'current_pct_raw': 0.05,
        'max_pct_raw': 0.10,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'PDH'] == 'success'
    assert table.loc[0, '1m ORH'] == '-'
    assert table.loc[0, '5m ORH'] == '-'
    assert table.loc[0, '1m OR Result'] == 'failed'
    assert table.loc[0, '5m OR Result'] == 'success'


def test_gap_over_pdh_display_marks_pdh_not_applicable_and_keeps_orh_results():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'TWLO',
        'status': 'Active',
        'trigger_type': '5m ORH',
        'pdh_result': 'Gap',
        'pdh_governed': False,
        'one_min_result': 'failed',
        'five_min_result': 'success',
        'raw_one_min_result': 'failed',
        'raw_five_min_result': 'success',
        'notes': '',
        'current_pct': 0.05,
        'max_pct': 0.10,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': '',
        'rating': None,
        'prior_day_high': 10.0,
        'setup_day_open': 10.2,
        'open_over_pdh': True,
        'pdh_trigger_break_time': None,
        'pdh_trigger_level': None,
        'pdh_reference_low': None,
        'pdh_reference_basis': '',
        'trigger_level': 10.8,
        'reference_low': 9.6,
        'reference_basis': 'LOD at 5m Trigger',
        'trigger_break_time': pd.Timestamp('2026-05-01 09:35'),
        'latest_close': 10.5,
        'close_price': 10.2,
        'high_price': 10.8,
        'low_price': 9.6,
        'current_pct_from_setup_close': 0.03,
        'max_gain_from_setup_close': 0.06,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': 0.8,
        'current_pct_raw': 0.05,
        'max_pct_raw': 0.10,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'PDH'] == 'Gap'
    assert table.loc[0, '1m ORH'] == 'failed'
    assert table.loc[0, '5m ORH'] == 'success'


def test_selected_1m_orh_displays_5m_not_applicable_but_detail_keeps_raw_5m():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'ONE',
        'status': 'Active',
        'trigger_type': '1m ORH',
        'pdh_result': 'Gap',
        'pdh_governed': False,
        'one_min_result': 'success',
        'five_min_result': '-',
        'raw_one_min_result': 'success',
        'raw_five_min_result': 'success',
        'notes': '',
        'current_pct': 0.05,
        'max_pct': 0.10,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': '',
        'rating': None,
        'prior_day_high': 9.5,
        'setup_day_open': 9.8,
        'open_over_pdh': True,
        'pdh_trigger_break_time': None,
        'pdh_trigger_level': None,
        'pdh_reference_low': None,
        'pdh_reference_basis': '',
        'trigger_level': 10.0,
        'reference_low': 9.6,
        'reference_basis': 'LOD at 1m Trigger',
        'trigger_break_time': pd.Timestamp('2026-05-01 09:31'),
        'latest_close': 10.5,
        'close_price': 10.2,
        'high_price': 10.8,
        'low_price': 9.6,
        'current_pct_from_setup_close': 0.03,
        'max_gain_from_setup_close': 0.06,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': 0.8,
        'or_5m': _or(broke_orh=True, orh_break_time='2026-05-01 09:35'),
        'one_min_follow_through_atr': 0.30,
        'current_pct_raw': 0.05,
        'max_pct_raw': 0.10,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, '1m ORH'] == 'success'
    assert table.loc[0, '5m ORH'] == '-'
    assert table.loc[0, '5m OR Result'] == 'success'
    assert table.loc[0, '5m ORH Break Time'] == '2026-05-01 09:35'
    assert table.loc[0, '5m ORH Broke After Range'] == 'Yes'


def test_one_min_quality_notes_add_no_5m_confirm_and_weak_follow_through():
    intraday = pd.DataFrame({
        'timestamp_et': pd.to_datetime(['2026-05-01 09:30', '2026-05-01 09:31', '2026-05-01 09:32']),
        'high': [10.0, 10.1, 10.2],
        'low': [9.8, 9.9, 10.0],
    })
    record = {
        'trigger_type': '1m ORH',
        'or_1m': _or(orh=10.0, orh_break_time='2026-05-01 09:31'),
        'or_5m': _or(broke_orh=False),
        'atr20': 1.0,
        'notes': 'Wide 1m OR',
    }

    out = apply_one_min_quality_notes(record, intraday)

    assert out['notes'] == 'Wide 1m OR; No 5m Confirm; Weak 1m Follow-Through'
    assert out['one_min_follow_through_atr'] < 0.25


def test_one_min_quality_notes_skip_weak_when_follow_through_confirmed_or_atr_missing():
    intraday = pd.DataFrame({
        'timestamp_et': pd.to_datetime(['2026-05-01 09:31', '2026-05-01 09:32']),
        'high': [10.1, 10.4],
        'low': [9.9, 10.0],
    })
    base = {
        'trigger_type': '1m ORH',
        'or_1m': _or(orh=10.0, orh_break_time='2026-05-01 09:31'),
        'or_5m': _or(broke_orh=True),
        'notes': '',
    }

    strong = apply_one_min_quality_notes({**base, 'atr20': 1.0}, intraday)
    missing = apply_one_min_quality_notes({**base, 'atr20': None}, intraday)
    zero = apply_one_min_quality_notes({**base, 'atr20': 0}, intraday)

    assert strong['one_min_follow_through_atr'] >= 0.25
    assert 'Weak 1m Follow-Through' not in strong['notes']
    assert missing['one_min_follow_through_atr'] is None
    assert zero['one_min_follow_through_atr'] is None
    assert missing['notes'] == ''
    assert zero['notes'] == ''


def test_close_below_be_for_vwap_reclaim_below_trigger_price_without_note_append():
    out = apply_weak_close_note({
        'trigger_type': 'VWAP Reclaim',
        'fail_day': None,
        'trigger_level': 10.5,
        'close_price': 10.1,
        'notes': '',
    })

    assert out['notes'] == ''
    assert out['close_below_be'] is True
    assert out['close_below_be_day'] == 0


def test_close_below_be_for_non_vwap_trigger_below_breakeven_without_note_append():
    out = apply_weak_close_note({
        'trigger_type': '5m ORH',
        'fail_day': None,
        'trigger_level': 10.5,
        'close_price': 10.1,
        'notes': '',
    })

    assert out['notes'] == ''
    assert out['close_below_be'] is True
    assert out['close_below_be_day'] == 0


def test_weak_close_note_skips_strong_close_failures_and_missing_inputs():
    strong = apply_weak_close_note({
        'trigger_type': '1m ORH',
        'fail_day': None,
        'trigger_level': 10.5,
        'close_price': 10.7,
        'notes': '',
    })
    failed = apply_weak_close_note({
        'trigger_type': '1m ORH',
        'fail_day': 0,
        'trigger_level': 10.5,
        'close_price': 10.1,
        'notes': '',
    })
    missing = apply_weak_close_note({
        'trigger_type': '1m ORH',
        'fail_day': None,
        'notes': '',
    })

    assert strong['notes'] == ''
    assert strong['close_below_be'] is False
    assert strong['close_below_be_day'] is None
    assert failed['notes'] == ''
    assert failed['close_below_be'] is None
    assert failed['close_below_be_day'] is None
    assert missing['notes'] == ''
    assert missing['close_below_be'] is None
    assert missing['close_below_be_day'] is None


def test_close_below_be_preserves_existing_notes_and_uses_current_return_fallback():
    out = apply_weak_close_note({
        'trigger_type': 'Alt Required',
        'fail_day': None,
        'current_pct': -0.01,
        'notes': 'Wide 5m OR',
    })
    duplicate = apply_weak_close_note({
        'trigger_type': 'Alt Required',
        'fail_day': None,
        'current_pct': -0.01,
        'notes': out['notes'],
    })

    assert out['notes'] == 'Wide 5m OR'
    assert out['close_below_be'] is True
    assert out['close_below_be_day'] is None
    assert duplicate['notes'] == out['notes']


def test_close_below_be_current_return_fallback_uses_latest_day_when_available():
    out = apply_weak_close_note({
        'trigger_type': 'Alt Required',
        'fail_day': None,
        'current_pct': -0.01,
        'latest_day': 4,
        'notes': '',
    })

    assert out['close_below_be'] is True
    assert out['close_below_be_day'] == 4


def test_weak_close_column_displays_no_and_dash_states():
    no = _format_section_table(pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'STRONG',
        'status': 'Active',
        'trigger_type': '1m ORH',
        'one_min_result': 'success',
        'five_min_result': '-',
        'notes': '',
        'close_below_be': False,
        'current_pct': 0.02,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.0,
        'reference_low': 9.8,
        'reference_basis': '1m ORH',
        'trigger_break_time': pd.Timestamp('2026-05-01 09:31'),
        'latest_close': 10.2,
        'close_price': 10.2,
        'high_price': 10.8,
        'low_price': 9.6,
        'current_pct_from_setup_close': 0.02,
        'max_gain_from_setup_close': 0.08,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': None,
    }]))
    dash = _format_section_table(pd.DataFrame([{
        'candidate_id': 2,
        'ticker': 'FAIL',
        'status': 'Failed',
        'trigger_type': 'Failed OR Trigger',
        'one_min_result': 'failed',
        'five_min_result': 'failed',
        'notes': '',
        'close_below_be': None,
        'current_pct': None,
        'max_pct': None,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': 0,
        'setup': None,
        'rating': None,
        'trigger_level': None,
        'reference_low': None,
        'reference_basis': '',
        'trigger_break_time': None,
        'latest_close': None,
        'close_price': None,
        'high_price': None,
        'low_price': None,
        'current_pct_from_setup_close': None,
        'max_gain_from_setup_close': None,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': None,
    }]))

    assert no.loc[0, 'Close < BE'] == 'No'
    assert dash.loc[0, 'Close < BE'] == ''


def test_format_section_table_displays_close_below_be_without_weak_close_note():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': 'VWAP Reclaim',
        'one_min_result': 'failed',
        'five_min_result': 'failed',
        'vwap_qualified_trigger_result': 'success',
        'notes': '',
        'close_below_be': True,
        'current_pct': -0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.5,
        'reference_low': 9.8,
        'reference_basis': 'VWAP Reclaim',
        'trigger_break_time': pd.Timestamp('2026-05-01 10:10'),
        'latest_close': 10.1,
        'close_price': 10.1,
        'high_price': 10.8,
        'low_price': 9.6,
        'current_pct_from_setup_close': -0.01,
        'max_gain_from_setup_close': 0.08,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': None,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Notes'] == ''
    assert table.loc[0, 'Close < BE'] == 'Yes'
    assert main_table(table).loc[0, 'Notes'] == ''
    assert main_table(table).loc[0, 'Close < BE'] == 'Yes'


def test_one_min_follow_through_atr_formula():
    intraday = pd.DataFrame({
        'timestamp_et': pd.to_datetime(['2026-05-01 09:31', '2026-05-01 09:32']),
        'high': [10.1, 10.5],
        'low': [9.9, 10.0],
    })

    assert one_min_follow_through_atr(_or(orh=10.0, orh_break_time='2026-05-01 09:31'), 2.0, intraday) == 0.25


def test_follow_through_handles_missing_base_prices():
    row = {
        'watchlist_date': '2026-05-01',
        'ticker': 'AAPL',
        'trigger_type': 'No Trigger',
        'trigger_level': None,
        'reference_low': None,
        'close_price': None,
        'trigger_break_time': None,
    }
    daily = pd.DataFrame([
        {'ticker': 'AAPL', 'trading_date': '2026-05-01', 'high': 10.5, 'low': 9.5, 'close': 10.0},
        {'ticker': 'AAPL', 'trading_date': '2026-05-02', 'high': 11.0, 'low': 10.0, 'close': 10.8},
    ])

    out = _follow_through(row, daily, pd.DataFrame())

    assert out['latest_close'] == 10.8
    assert out['base_price'] is None
    assert out['current_pct'] is None
    assert out['max_pct'] is None
    assert out['current_pct_from_setup_close'] is None


def test_pdh_never_breaks_does_not_fall_back_to_clean_1m():
    intraday = _pdh_intraday(highs=[10.1, 10.6, 10.8, 10.9])
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=False, orh=10.9, orl=9.6, orh_break_time='2026-05-01 09:35'),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        11.0,
        10.0,
    )

    assert out['trigger_type'] == 'No Trigger'
    assert out['pdh_result'] == '-'
    assert out['pdh_governed'] is True


def test_pdh_never_breaks_does_not_fall_back_to_clean_5m():
    intraday = _pdh_intraday(highs=[10.1, 10.2, 10.8, 10.9])
    out = derive_trigger_reference(
        _or(broke_orh=False, broke_orl=False, orh=10.5, orl=9.8),
        _or(broke_orh=True, broke_orl=False, orh=10.7, orl=9.6, orh_break_time='2026-05-01 09:32'),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        11.0,
        10.0,
    )

    assert out['trigger_type'] == 'No Trigger'
    assert out['pdh_result'] == '-'
    assert out['pdh_governed'] is True


def test_pdh_never_breaks_and_no_fallback_is_no_trigger():
    intraday = _pdh_intraday(highs=[10.1, 10.2, 10.8, 10.9])
    out = derive_trigger_reference(
        _or(broke_orh=False, broke_orl=False, orh=10.5, orl=9.8),
        _or(broke_orh=False, broke_orl=False, orh=10.7, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        11.0,
        10.0,
    )

    assert out['trigger_type'] == 'No Trigger'
    assert out['pdh_result'] == '-'


def test_open_over_pdh_uses_orh_stack():
    intraday = _pdh_intraday()
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31'),
        _or(broke_orh=False, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        9.9,
        10.0,
    )

    assert out['trigger_type'] == '1m ORH'
    assert out['pdh_result'] == 'Gap'
    assert out['pdh_governed'] is False


def test_missing_pdh_falls_back_to_orh_stack():
    intraday = _pdh_intraday()
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:31'),
        _or(broke_orh=False, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
        _daily(lows=[10.1, 10.2, 10.3, 10.4]),
        None,
        10.0,
    )

    assert out['trigger_type'] == '1m ORH'
    assert out['pdh_result'] == '-'
    assert out['pdh_governed'] is False


def test_1m_orl_break_before_orh_late_orh_can_succeed():
    intraday = _flush_then_trigger_intraday(after_low=9.6)
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=False, broke_orl=False, orh=11.0, orl=9.6),
        _or(orh=12.0, orl=9.2),
        0.5,
        intraday,
    )
    failure = fail_day(intraday, _daily(lows=[10.1, 10.0, 10.2, 10.3]), out['trigger_break_time'], out['reference_low'])
    assessment = orh_trigger_assessment(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        1,
        intraday,
    )

    assert out['trigger_type'] == '1m ORH'
    assert out['reference_low'] == 9.5
    assert out['reference_basis'] == 'LOD at 1m Trigger'
    assert assessment['low_swept_before_trigger'] is True
    assert assessment['post_trigger_stop_breached'] is False
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=10.5, orl=9.8, orh_break_time='2026-05-01 09:32', orl_break_time='2026-05-01 09:31'),
        1,
        out['trigger_type'],
        intraday,
    ) == 'success'
    assert failure is None
    assert status_for(out['trigger_type'], failure) == 'Active'


def test_cifr_like_pretrigger_low_sweep_resolves_as_1m_orh_when_stop_holds():
    intraday = pd.DataFrame({
        'ticker': ['CIFR'] * 6,
        'trading_date': pd.to_datetime(['2026-05-05'] * 6),
        'timestamp_et': pd.to_datetime([
            '2026-05-05 09:30',
            '2026-05-05 09:31',
            '2026-05-05 09:32',
            '2026-05-05 09:34',
            '2026-05-05 09:35',
            '2026-05-05 09:36',
        ]),
        'high': [18.53, 18.10, 18.20, 18.60, 18.95, 18.80],
        'low': [17.89, 17.70, 17.65, 18.41, 18.50, 18.55],
        'close': [18.00, 17.80, 18.10, 18.55, 18.90, 18.70],
    })
    one = _or(
        broke_orh=True,
        broke_orl=True,
        first_break_direction='down',
        orh_then_orl=False,
        orl_then_orh=True,
        orh=18.53,
        orl=17.89,
        orh_break_time='2026-05-05 09:34',
        orl_break_time='2026-05-05 09:31',
    )
    five = _or(broke_orh=True, broke_orl=False, orh=18.60, orl=17.65, orh_break_time='2026-05-05 09:35')
    out = derive_trigger_reference(one, five, _or(orh=19.0, orl=17.65), 0.80, intraday)
    assessment = orh_trigger_assessment(one, 1, intraday)

    assert assessment['low_swept_before_trigger'] is True
    assert assessment['reference_low'] == 17.65
    assert assessment['post_trigger_stop_breached'] is False
    assert out['trigger_type'] == '1m ORH'
    assert opening_range_result(one, 1, out['trigger_type'], intraday) == 'success'
    assert opening_range_result(five, 5, out['trigger_type'], intraday) == 'success'


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
    assessment = orh_trigger_assessment(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=11.0, orl=9.6, orh_break_time='2026-05-01 09:35', orl_break_time='2026-05-01 09:32'),
        5,
        intraday,
    )

    assert out['trigger_type'] == '5m ORH'
    assert out['reference_low'] == 9.4
    assert out['reference_basis'] == 'LOD at 5m Trigger'
    assert assessment['low_swept_before_trigger'] is True
    assert assessment['post_trigger_stop_breached'] is False
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


def test_docn_like_same_bar_low_sweep_resolves_as_1m_orh_when_stop_holds():
    intraday = pd.DataFrame({
        'ticker': ['DOCN'] * 5,
        'trading_date': pd.to_datetime(['2026-05-05'] * 5),
        'timestamp_et': pd.to_datetime([
            '2026-05-05 09:30',
            '2026-05-05 09:31',
            '2026-05-05 09:32',
            '2026-05-05 09:35',
            '2026-05-05 09:37',
        ]),
        'high': [132.599, 133.00, 138.00, 142.00, 143.50],
        'low': [130.20, 129.51, 134.37, 139.00, 141.00],
        'close': [132.00, 132.90, 137.50, 141.50, 143.00],
    })
    one = _or(
        broke_orh=True,
        broke_orl=True,
        first_break_direction='none',
        same_bar_orh_orl_break=True,
        orh_then_orl=False,
        orl_then_orh=False,
        orh=132.599,
        orl=130.20,
        orh_break_time='2026-05-05 09:31',
        orl_break_time='2026-05-05 09:31',
    )
    five = _or(broke_orh=True, broke_orl=False, orh=143.0, orl=129.51, orh_break_time='2026-05-05 09:37')
    out = derive_trigger_reference(one, five, _or(orh=144.0, orl=129.51), 0.85, intraday)
    assessment = orh_trigger_assessment(one, 1, intraday)

    assert assessment['broke_orh'] is True
    assert assessment['low_swept_before_trigger'] is True
    assert assessment['reference_low'] == 129.51
    assert assessment['post_trigger_stop_breached'] is False
    assert out['trigger_type'] == '1m ORH'
    assert out['reference_low'] == 129.51
    assert opening_range_result(one, 1, out['trigger_type'], intraday) == 'success'
    assert opening_range_result(five, 5, out['trigger_type'], intraday) == 'success'


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


def test_crml_style_failed_1m_5m_then_15m_break_selects_alt_required():
    intraday = pd.DataFrame({
        'ticker': ['CRML'] * 8,
        'trading_date': pd.to_datetime(['2026-04-27'] * 8),
        'timestamp_et': pd.to_datetime([
            '2026-04-27 09:30',
            '2026-04-27 09:31',
            '2026-04-27 09:33',
            '2026-04-27 09:37',
            '2026-04-27 09:50',
            '2026-04-27 13:31',
            '2026-04-27 13:32',
            '2026-04-27 15:59',
        ]),
        'high': [12.80, 12.50, 12.90, 13.10, 12.50, 13.20, 13.40, 14.50],
        'low': [12.20, 12.06, 12.10, 12.20, 11.56, 12.80, 13.00, 14.00],
        'close': [12.40, 12.20, 12.85, 13.00, 12.00, 13.15, 13.30, 14.45],
    })
    daily = _daily(lows=[11.56, 11.83, 11.05, 11.50])
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=12.80, orl=12.20, orh_break_time='2026-04-27 09:33', orl_break_time='2026-04-27 09:31'),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=12.94, orl=12.06, orh_break_time='2026-04-27 09:37', orl_break_time='2026-04-27 09:50'),
        _or(broke_orh=True, broke_orl=True, orh=13.00, orl=12.06, orh_break_time='2026-04-27 13:31', orl_break_time='2026-04-27 09:50'),
        0.90,
        intraday,
        daily,
    )

    assert out['trigger_type'] == 'Alt Required'
    assert out['trigger_level'] == 13.00
    assert out['reference_low'] == 12.06


def test_lar_style_5m_post_trigger_d1_failure_can_use_alt_required():
    intraday = pd.DataFrame({
        'ticker': ['LAR'] * 6,
        'trading_date': pd.to_datetime(['2026-04-27'] * 6),
        'timestamp_et': pd.to_datetime([
            '2026-04-27 09:30',
            '2026-04-27 09:31',
            '2026-04-27 09:49',
            '2026-04-27 10:00',
            '2026-04-27 10:25',
            '2026-04-27 15:59',
        ]),
        'high': [9.50, 9.55, 9.60, 9.70, 9.80, 9.99],
        'low': [9.41, 9.45, 9.34, 9.50, 9.60, 9.80],
        'close': [9.45, 9.50, 9.50, 9.65, 9.78, 9.97],
    })
    daily = pd.DataFrame({
        'ticker': ['LAR'] * 4,
        'trading_date': pd.to_datetime(['2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30']),
        'high': [9.99, 9.84, 9.83, 10.46],
        'low': [9.34, 9.21, 9.44, 9.77],
        'close': [9.97, 9.62, 9.62, 10.17],
    })
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=9.50, orl=9.41, orh_break_time='2026-04-27 09:31', orl_break_time='2026-04-27 09:49'),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=9.75, orl=9.41, orh_break_time='2026-04-27 10:25', orl_break_time='2026-04-27 09:49'),
        _or(broke_orh=True, orh=9.75, orl=9.41, orh_break_time='2026-04-27 10:25'),
        0.90,
        intraday,
        daily,
    )
    failure = fail_day(intraday, daily, out['trigger_break_time'], out['reference_low'])
    table = _format_section_table(pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'LAR',
        'status': status_for(out['trigger_type'], failure),
        'trigger_type': out['trigger_type'],
        'one_min_result': opening_range_result(_or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=9.50, orl=9.41, orh_break_time='2026-04-27 09:31', orl_break_time='2026-04-27 09:49'), 1, out['trigger_type'], intraday, daily),
        'five_min_result': opening_range_result(_or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=9.75, orl=9.41, orh_break_time='2026-04-27 10:25', orl_break_time='2026-04-27 09:49'), 5, out['trigger_type'], intraday, daily),
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.02,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': failure,
        'setup': None,
        'rating': None,
        'trigger_level': out['trigger_level'],
        'reference_low': out['reference_low'],
        'reference_basis': out['reference_basis'],
        'trigger_break_time': out['trigger_break_time'],
        'latest_close': 9.62,
        'close_price': 9.97,
        'high_price': 9.99,
        'low_price': 9.34,
        'current_pct_from_setup_close': None,
        'max_gain_from_setup_close': None,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': 0.90,
    }]))

    assert out['trigger_type'] == 'Alt Required'
    assert out['reference_low'] == 9.41
    assert failure == 1
    assert table.loc[0, 'Trigger Day'] == 'Success'
    assert table.loc[0, 'Current Status'] == 'Failed D1'
    assert table.loc[0, '5m ORH'] == 'failed'


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


def test_docn_style_pretrigger_flush_resolves_as_1m_orh_success():
    intraday = pd.DataFrame({
        'ticker': ['TWLO'] * 7,
        'trading_date': pd.to_datetime(['2026-05-01'] * 7),
        'timestamp_et': pd.to_datetime([
            '2026-05-01 09:30',
            '2026-05-01 09:31',
            '2026-05-01 09:32',
            '2026-05-01 09:35',
            '2026-05-01 10:16',
            '2026-05-01 13:03',
            '2026-05-01 15:59',
        ]),
        'high': [179.47, 178.67, 177.66, 175.36, 172.43, 179.86, 183.59],
        'low': [177.28, 176.45, 173.33, 172.30, 171.01, 178.87, 182.91],
        'close': [178.37, 177.81, 175.89, 172.31, 172.43, 179.86, 183.35],
    })
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=179.47, orl=177.28, orh_break_time='2026-05-01 13:03', orl_break_time='2026-05-01 09:31'),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=179.47, orl=173.33, orh_break_time='2026-05-01 13:03', orl_break_time='2026-05-01 09:35'),
        _or(broke_orh=True, broke_orl=True, orh=179.47, orl=172.30, orh_break_time='2026-05-01 13:03'),
        0.75,
        intraday,
    )

    assert out['trigger_type'] == '1m ORH'
    assert out['reference_low'] == 171.01
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=179.47, orl=177.28, orh_break_time='2026-05-01 13:03', orl_break_time='2026-05-01 09:31'),
        1,
        out['trigger_type'],
        intraday,
    ) == 'success'
    assert opening_range_result(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=False, orl_then_orh=True, orh=179.47, orl=173.33, orh_break_time='2026-05-01 13:03', orl_break_time='2026-05-01 09:35'),
        5,
        out['trigger_type'],
        intraday,
    ) == 'success'
    assert status_for(out['trigger_type'], fail_day(intraday, _daily(lows=[180.0, 179.0, 178.0, 177.0]), out['trigger_break_time'], out['reference_low'])) == 'Active'


def test_prch_style_5m_reference_low_break_after_trigger_is_failed():
    intraday = pd.DataFrame({
        'ticker': ['PRCH'] * 6,
        'trading_date': pd.to_datetime(['2026-04-29'] * 6),
        'timestamp_et': pd.to_datetime([
            '2026-04-29 09:30',
            '2026-04-29 09:31',
            '2026-04-29 09:32',
            '2026-04-29 09:33',
            '2026-04-29 09:34',
            '2026-04-29 09:35',
        ]),
        'high': [10.32, 10.20, 10.40, 10.45, 10.50, 10.70],
        'low': [9.91, 10.00, 9.90, 10.10, 10.20, 10.55],
        'close': [10.10, 10.15, 10.30, 10.35, 10.45, 10.65],
    })
    daily = pd.DataFrame({
        'ticker': ['PRCH'] * 4,
        'trading_date': pd.to_datetime(['2026-04-29', '2026-04-30', '2026-05-01', '2026-05-04']),
        'high': [10.90, 10.80, 10.70, 10.60],
        'low': [9.90, 9.80, 9.95, 10.00],
        'close': [10.65, 10.10, 10.20, 10.30],
    })
    out = derive_trigger_reference(
        _or(broke_orh=False, broke_orl=True, orh=10.32, orl=9.91),
        _or(broke_orh=True, broke_orl=False, orh=10.69, orl=9.90, orh_break_time='2026-04-29 09:35'),
        _or(broke_orh=False, orh=10.83, orl=9.90),
        0.30,
        intraday,
        daily,
    )

    assert out['trigger_type'] == 'Failed OR Trigger'
    assert out['failed_framework'] == '5m ORH'
    assert status_for(out['trigger_type'], out['framework_fail_day']) == 'Failed'


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


def test_retest_events_no_retest():
    days, dates = retest_events(_intraday(), _daily(lows=[10.5, 10.4, 10.3, 10.2]), pd.Timestamp('2026-05-01 09:35'), 10.0)

    assert days == []
    assert dates == []


def test_retest_events_multiple_days_in_order():
    daily = _daily(lows=[10.5, 10.6, 10.1, 10.2])

    days, dates = retest_events(_intraday(), daily, pd.Timestamp('2026-05-01 09:31'), 10.25)

    assert days == [0, 2, 3]
    assert dates == ['2026-05-01', '2026-05-05', '2026-05-06']


def test_retest_events_cap_display_in_formatted_table():
    raw = pd.DataFrame([{
        **_base_formatted_record(),
        'retest_days': [0, 2, 5, 6],
        'retest_dates': ['2026-05-01', '2026-05-05', '2026-05-08', '2026-05-11'],
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Retests'] == 'D0, D2, D5 +1'
    assert table.loc[0, 'Retest Count'] == '4'
    assert table.loc[0, 'Retest Days Raw'] == 'D0, D2, D5, D6'
    assert table.loc[0, 'Retest Dates Raw'] == '2026-05-01, 2026-05-05, 2026-05-08, 2026-05-11'


def test_retest_events_excludes_after_failure_day():
    daily = pd.DataFrame({
        'ticker': ['AAPL'] * 6,
        'trading_date': pd.to_datetime(['2026-05-01', '2026-05-04', '2026-05-05', '2026-05-06', '2026-05-07', '2026-05-08']),
        'high': [11.0, 11.4, 11.5, 11.2, 11.1, 11.3],
        'low': [10.5, 10.2, 10.4, 10.1, 10.0, 10.2],
        'close': [10.8, 11.1, 10.9, 11.0, 10.7, 11.2],
    })

    days, _ = retest_events(_intraday(), daily, pd.Timestamp('2026-05-01 09:35'), 10.25, fail_day_value=3)

    assert days == [1, 3]


def test_status_values():
    assert status_for('1m ORH', None) == 'Active'
    assert status_for('5m ORH', 1) == 'Failed'
    assert status_for('Failed OR Trigger', None) == 'Failed'
    assert status_for('No Trigger', None) == 'Unresolved'


def test_trigger_day_display_values():
    assert trigger_day_status('1m ORH', None) == 'Success'
    assert trigger_day_status('5m ORH', 1) == 'Success'
    assert trigger_day_status('Alt Required', 2) == 'Success'
    assert trigger_day_status('Failed OR Trigger', 3) == 'Success'
    assert trigger_day_status('Failed OR Trigger', 0) == 'Fail'
    assert trigger_day_status('No Trigger', None) == 'Unresolved'


def test_current_status_display_values():
    assert current_status_display('Success', None) == 'Active'
    assert current_status_display('Success', None, True) == 'Active'
    assert current_status_display('Success', None, True, 0) == 'Active'
    assert current_status_display('Success', None, False) == 'Active'
    assert current_status_display('Success', 0) == 'Active'
    assert current_status_display('Success', 1) == 'Failed D1'
    assert current_status_display('Success', 2) == 'Failed D2'
    assert current_status_display('Success', 3) == 'Failed D3'
    assert current_status_display('Fail', 0) == '—'
    assert current_status_display('Fail', None) == '—'
    assert current_status_display('Unresolved', None) == '—'

def test_sezl_style_retest_and_close_below_be_remains_active():
    raw = pd.DataFrame([{
        **_base_formatted_record(),
        'ticker': 'SEZL',
        'trigger_type': '1m ORH',
        'retest_days': [0],
        'close_below_be': True,
        'close_below_be_day': 0,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Trigger Day'] == 'Success'
    assert table.loc[0, 'Retests'] == 'D0'
    assert table.loc[0, 'Current Status'] == 'Active'
    assert table.loc[0, 'Close < BE'] == 'Yes'


def test_successful_non_vwap_close_below_be_remains_active():
    raw = pd.DataFrame([{
        **_base_formatted_record(),
        'trigger_type': '1m ORH',
        'close_below_be': True,
        'close_below_be_day': 2,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Current Status'] == 'Active'
    assert table.loc[0, 'Close < BE'] == 'Yes'


def test_close_below_be_unknown_day_remains_active():
    raw = pd.DataFrame([{
        **_base_formatted_record(),
        'trigger_type': '1m ORH',
        'close_below_be': True,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Current Status'] == 'Active'
    assert table.loc[0, 'Close < BE'] == 'Yes'


def test_successful_trigger_close_above_be_remains_active():
    raw = pd.DataFrame([{
        **_base_formatted_record(),
        'trigger_type': '5m ORH',
        'close_below_be': False,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Current Status'] == 'Active'
    assert table.loc[0, 'Close < BE'] == 'No'


def test_no_trigger_close_below_be_blank_does_not_become_later_failed():
    raw = pd.DataFrame([{
        **_base_formatted_record(),
        'trigger_type': 'No Trigger',
        'one_min_result': '',
        'close_below_be': None,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Trigger Day'] == 'Unresolved'
    assert table.loc[0, 'Current Status'] == '—'


def test_trigger_day_failure_status_unchanged_by_close_below_be():
    raw = pd.DataFrame([{
        **_base_formatted_record(),
        'trigger_type': 'Failed OR Trigger',
        'fail_day': 0,
        'close_below_be': True,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Trigger Day'] == 'Fail'
    assert table.loc[0, 'Current Status'] == '—'


def test_retest_without_failure_remains_active():
    raw = pd.DataFrame([{
        **_base_formatted_record(),
        'ticker': 'RETEST',
        'trigger_type': 'VWAP Reclaim',
        'vwap_qualified_trigger_result': 'success',
        'retest_days': [0],
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'Current Status'] == 'Active'
    assert table.loc[0, 'Retests'] == 'D0'


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
        'Current Status': 'Active',
        'Trigger Day': 'Success',
        'Trigger': '1m ORH',
        '1m ORH': 'success',
        '5m ORH': '',
        'Notes': 'Wide 1m OR',
        'Current %': '1.0%',
        'Max %': '3.0%',
        'D3 High %': '-',
        'Retests': '',
        'Fail Day': '',
        'Setup': 'Pullback',
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
        'Ticker', 'Current Status', 'Trigger Day', 'Trigger', 'PDH', '1m ORH', 'VWAP Reclaim', '5m ORH', 'Notes',
        'Current %', 'Max %', 'Close < BE', 'D3 High %', 'Retests', 'Setup', 'Entry Tactic', 'Rating',
    ]
    assert 'VWAP Trigger' not in main_table(df).columns
    assert detail_table(df).columns.tolist() == [
        'Ticker', 'Prior Day High', 'Setup Day Open', 'Open Over PDH', 'PDH Result',
        'PDH Fail Time', '1m Recovery Qualified', '1m Recovery Break Time',
        '1m Recovery Reference Low', '5m Recovery Qualified', '5m Recovery Break Time',
        '5m Recovery Reference Low', 'Alt Recovery Qualified',
        'PDH Trigger Break Time', 'PDH Trigger Level', 'PDH Reference Low', 'PDH Reference Basis',
        'Raw VWAP Reclaim Result', 'Raw VWAP Reclaim Prior Below VWAP',
        'Raw VWAP Reclaim Time', 'Raw VWAP Reclaim Bar High',
        'Raw VWAP Reclaim Trigger Time', 'Raw VWAP Reclaim Trigger Price',
        'Raw VWAP Reclaim Stop Valid', 'Raw VWAP Reclaim Result Reason',
        'Qualified VWAP Trigger Result', 'Qualified VWAP Trigger Reason',
        'VWAP Success Later Failed',
        'ORH Display Suppression', '1m ORH Trigger Price', '5m ORH Trigger Price',
        'Trigger Level', 'Reference Low', 'Reference Basis', 'Trigger Break Time',
        '1m Low Swept Before Trigger', '1m ORH Reference Low', '1m ORH Reference Basis',
        '1m Post-Trigger Stop Breach', '5m Low Swept Before Trigger',
        '5m ORH Reference Low', '5m ORH Reference Basis', '5m Post-Trigger Stop Breach',
        'Fail Day', 'Retests', 'Retest Count', 'Retest Days Raw', 'Retest Dates Raw',
        'Latest Close', 'Setup Close', 'Setup High', 'Setup Low',
        'Current vs Setup Close', 'Max Gain from Setup Close', 'RVOL', 'Range / ATR14', '1m OR Width / ATR14',
        '5m OR Width / ATR14', 'Close Bucket',
        '1m OR Result', '5m OR Result', '5m ORH Break Time',
        '5m ORH Broke After Range', '1m Follow-Through / ATR14',
    ]
    assert main_table(df).loc[0, 'Rating'] == ''
    assert main_table(df).loc[0, 'Setup'] == 'Pullback'
    assert main_table(df).loc[0, 'Entry Tactic'] == ''


def test_format_monitor_table_html_escapes_blanks_and_relabels_headers():
    df = pd.DataFrame([{
        'Ticker': '<ABC>',
        'Current Status': 'Active',
        'Trigger Day': 'Success',
        'Trigger': 'Alt Required',
        '1m ORH': 'success',
        '5m ORH': 'failed',
        'Current %': float('nan'),
        'Retests': '',
    }])

    html = format_monitor_table_html(df)

    assert '<th>Ticker</th>' in html
    assert '<th>Current</th>' in html
    assert '<th>Retests</th>' in html
    assert '&lt;ABC&gt;' in html
    assert 'current-status-active' in html
    assert 'trigger-day-success' in html
    assert 'trigger-alt-required' in html
    assert 'result-success' in html
    assert 'result-failed' in html
    assert '<td>nan</td>' not in html
    assert 'height:' not in html
    assert 'overflow-y: scroll' not in html
    assert 'overflow-y: auto' not in html


def test_rolling_setup_monitor_page_uses_db_backed_cache_token_and_perf_debug():
    page = open('pages/3_Rolling_Setup_Monitor.py', encoding='utf-8').read()

    assert "ROLLING_MONITOR_CACHE_VERSION = 'rolling-monitor-vwap-actionable-display-v3'" in page
    assert "rolling_cache_token = f'{ROLLING_MONITOR_CACHE_VERSION}:{data_health_cache_token(db_path)}'" in page
    assert 'load_rolling_setup_sections(db_path, rolling_cache_token)' in page
    assert "PerfTimer('Rolling Setup Monitor')" in page
    assert 'render_perf_debug(st, perf)' in page
    assert "Edit Setup / Entry Tactic / Rating" in page
    assert "display[['Ticker', 'Setup', 'Entry Tactic', 'Rating']]" in page
    assert 'entry_tactic_dropdown_options(table)' in page
    assert 'st.cache_data.clear()' in page
    assert "st.success('Saved setup/rating changes.')" in page


def test_format_summary_blocks_html_includes_group_titles():
    summary = {
        'Setups': 3,
        'Active': 1,
        'Later Failed': 1,
        'Day Success': 2,
        'Day Fail': 0,
        'Unresolved': 1,
        'PDH': 1,
        'PDH Gap': 1,
        'Failed PDH Trigger': 1,
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
    assert 'PDH' in html
    assert '1m OR' in html
    assert '5m OR' in html
    assert 'Alternate / Other' in html
    assert 'Follow-Through' in html
    assert 'Median D3 High' in html
    assert 'Day Success</span><strong>2 (67%)</strong>' in html
    assert 'Day Fail</span><strong>0 (0%)</strong>' in html
    assert 'Active</span><strong>1 (33%)</strong>' in html
    assert 'Later Failed</span><strong>1 (33%)</strong>' in html
    assert 'Gap</span><strong>1 (33%)</strong>' in html
    assert 'Success</span><strong>1 (33%)</strong>' in html
    assert 'Failed</span><strong>1 (33%)</strong>' in html
    assert 'Clean 5m</span><strong>0 (0%)</strong>' in html
    assert 'Median Current</span><strong>5.0%</strong>' in html
    assert 'Median Current</span><strong>5.0% (' not in html


def test_format_summary_blocks_html_uses_zero_percent_when_no_setups():
    html = format_summary_blocks_html({
        'Setups': 0,
        'Active': 0,
        'Later Failed': 0,
        'Day Success': 0,
        'Day Fail': 0,
        'Unresolved': 0,
        'PDH': 0,
        'PDH Gap': 0,
        'Failed PDH Trigger': 0,
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
    assert 'Day Success</span><strong>0 (0%)</strong>' in html
    assert 'Active</span><strong>0 (0%)</strong>' in html
    assert 'Gap</span><strong>0 (0%)</strong>' in html
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

    assert table.loc[0, 'Retests'] == ''
    assert table.loc[0, 'Fail Day'] == ''
    assert table.loc[0, 'D3 High %'] == '-'


def test_format_section_table_exposes_vwap_reclaim_result_and_detail():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': 'VWAP Reclaim',
        'one_min_result': 'failed',
        'five_min_result': 'failed',
        'vwap_reclaim_result': 'success',
        'vwap_reclaim_time': pd.Timestamp('2026-05-01 10:05'),
        'vwap_reclaim_reclaim_bar_high': 10.4,
        'vwap_reclaim_trigger_time': pd.Timestamp('2026-05-01 10:10'),
        'vwap_reclaim_trigger_price': 10.4,
        'vwap_reclaim_stop_valid': True,
        'vwap_reclaim_prior_below_vwap_observed': True,
        'vwap_reclaim_failure_reason': '',
        'vwap_reclaim_result_reason': '',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.4,
        'reference_low': 9.8,
        'reference_basis': 'VWAP Reclaim',
        'trigger_break_time': pd.Timestamp('2026-05-01 10:10'),
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

    assert table.loc[0, 'Trigger'] == 'VWAP Reclaim'
    assert table.loc[0, 'VWAP Reclaim'] == 'success'
    assert table.loc[0, 'Raw VWAP Reclaim Result'] == 'success'
    assert table.loc[0, 'Raw VWAP Reclaim Trigger Price'] == '10.40'
    assert table.loc[0, 'Raw VWAP Reclaim Stop Valid'] == 'Yes'
    assert table.loc[0, 'Raw VWAP Reclaim Prior Below VWAP'] == 'Yes'


def test_format_section_table_keeps_raw_vwap_success_out_of_main_when_not_qualified():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': 'PDH',
        'one_min_result': '-',
        'five_min_result': '-',
        'vwap_reclaim_result': 'success',
        'vwap_reclaim_time': pd.Timestamp('2026-05-01 10:05'),
        'vwap_reclaim_reclaim_bar_high': 10.4,
        'vwap_reclaim_trigger_time': pd.Timestamp('2026-05-01 10:10'),
        'vwap_reclaim_trigger_price': 10.4,
        'vwap_reclaim_stop_valid': True,
        'vwap_reclaim_prior_below_vwap_observed': True,
        'vwap_reclaim_result_reason': '',
        'vwap_qualified_trigger_result': '',
        'vwap_qualified_trigger_reason': 'PDH trigger preserved',
        'pdh_result': 'success',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.8,
        'reference_low': 9.8,
        'reference_basis': 'PDH',
        'trigger_break_time': pd.Timestamp('2026-05-01 09:45'),
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

    assert table.loc[0, 'VWAP Reclaim'] == '-'
    assert table.loc[0, 'Raw VWAP Reclaim Result'] == 'success'
    assert table.loc[0, 'Qualified VWAP Trigger Reason'] == 'PDH trigger preserved'


def test_format_section_table_preserves_raw_vwap_failure_without_qualified_failure():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': '1m ORH',
        'raw_one_min_result': 'success',
        'raw_five_min_result': '-',
        'one_min_result': 'success',
        'five_min_result': '-',
        'vwap_reclaim_result': 'failed',
        'vwap_reclaim_result_reason': 'reclaim-bar high not taken out',
        'vwap_qualified_trigger_result': '',
        'vwap_qualified_trigger_reason': 'raw VWAP Reclaim is failed',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.5,
        'reference_low': 9.8,
        'reference_basis': '1m ORH',
        'trigger_break_time': pd.Timestamp('2026-05-01 09:31'),
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

    assert table.loc[0, 'VWAP Reclaim'] == '-'
    assert table.loc[0, 'Raw VWAP Reclaim Result'] == 'failed'
    assert table.loc[0, 'Raw VWAP Reclaim Result Reason'] == 'reclaim-bar high not taken out'
    assert table.loc[0, 'Qualified VWAP Trigger Result'] == '-'
    assert table.loc[0, 'Qualified VWAP Trigger Reason'] == 'raw VWAP Reclaim is failed'


def test_format_section_table_flags_vwap_success_later_failed_in_detail_only():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Failed',
        'trigger_type': 'VWAP Reclaim',
        'raw_one_min_result': 'failed',
        'raw_five_min_result': 'failed',
        'one_min_result': 'failed',
        'five_min_result': 'failed',
        'vwap_reclaim_result': 'success',
        'vwap_qualified_trigger_result': 'success',
        'vwap_qualified_trigger_reason': 'VWAP selected over fallback trigger',
        'notes': '',
        'current_pct': -0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': 1,
        'setup': None,
        'rating': None,
        'trigger_level': 10.4,
        'reference_low': 9.8,
        'reference_basis': 'VWAP Reclaim',
        'trigger_break_time': pd.Timestamp('2026-05-01 10:10'),
        'latest_close': 10.3,
        'close_price': 10.0,
        'high_price': 10.8,
        'low_price': 9.6,
        'current_pct_from_setup_close': 0.03,
        'max_gain_from_setup_close': 0.08,
        'relative_volume_20d': None,
        'range_vs_atr20': None,
        'one_min_or_width_vs_atr14': None,
        'five_min_or_width_vs_atr14': None,
        'close_location': None,
    }])

    table = _format_section_table(raw)

    assert table.loc[0, 'VWAP Reclaim'] == 'success'
    assert table.loc[0, 'Current Status'] == 'Failed D1'
    assert table.loc[0, 'VWAP Success Later Failed'] == 'Yes'
    assert 'VWAP Success Later Failed' not in main_table(table).columns


def test_format_section_table_marks_5m_orh_superseded_when_vwap_is_tighter():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': 'VWAP Reclaim',
        'raw_one_min_result': 'failed',
        'raw_five_min_result': 'success',
        'one_min_result': 'failed',
        'five_min_result': 'success',
        'or_1m': _or(orh=10.2),
        'or_5m': _or(orh=10.8),
        'vwap_reclaim_result': 'success',
        'vwap_reclaim_trigger_price': 10.4,
        'vwap_qualified_trigger_result': 'success',
        'vwap_qualified_trigger_reason': 'VWAP trigger price lower than 5m ORH',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.4,
        'reference_low': 9.8,
        'reference_basis': 'VWAP Reclaim',
        'trigger_break_time': pd.Timestamp('2026-05-01 10:10'),
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

    assert table.loc[0, 'Trigger'] == 'VWAP Reclaim'
    assert table.loc[0, '5m ORH'] == 'superseded'
    assert table.loc[0, '5m OR Result'] == 'success'
    assert table.loc[0, 'ORH Display Suppression'] == '5m ORH hidden because VWAP Reclaim trigger price is lower or equal'
    assert table.loc[0, 'VWAP Reclaim'] == 'success'
    assert main_table(table).loc[0, '5m ORH'] == '-'


def test_format_section_table_marks_1m_orh_superseded_when_vwap_is_tighter():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': 'VWAP Reclaim',
        'raw_one_min_result': 'success',
        'raw_five_min_result': '-',
        'one_min_result': 'success',
        'five_min_result': '-',
        'or_1m': _or(orh=10.8),
        'or_5m': _or(orh=10.2),
        'vwap_reclaim_result': 'success',
        'vwap_reclaim_trigger_price': 10.4,
        'vwap_qualified_trigger_result': 'success',
        'vwap_qualified_trigger_reason': 'VWAP trigger price lower than 1m ORH',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.4,
        'reference_low': 9.8,
        'reference_basis': 'VWAP Reclaim',
        'trigger_break_time': pd.Timestamp('2026-05-01 10:10'),
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

    assert table.loc[0, 'Trigger'] == 'VWAP Reclaim'
    assert table.loc[0, '1m ORH'] == 'superseded'
    assert table.loc[0, '1m OR Result'] == 'success'
    assert table.loc[0, 'ORH Display Suppression'] == '1m ORH hidden because VWAP Reclaim trigger price is lower or equal'
    assert table.loc[0, 'VWAP Reclaim'] == 'success'
    assert main_table(table).loc[0, '1m ORH'] == '-'


def test_format_section_table_marks_all_orh_successes_superseded_when_vwap_is_tighter():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': 'VWAP Reclaim',
        'raw_one_min_result': 'success',
        'raw_five_min_result': 'success',
        'one_min_result': 'success',
        'five_min_result': 'success',
        'or_1m': _or(orh=10.8),
        'or_5m': _or(orh=11.0),
        'vwap_reclaim_result': 'success',
        'vwap_reclaim_trigger_price': 10.4,
        'vwap_qualified_trigger_result': 'success',
        'vwap_qualified_trigger_reason': 'VWAP trigger price lower than 1m ORH',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.4,
        'reference_low': 9.8,
        'reference_basis': 'VWAP Reclaim',
        'trigger_break_time': pd.Timestamp('2026-05-01 10:10'),
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
    summary = day_summary(table)

    assert table.loc[0, '1m ORH'] == 'superseded'
    assert table.loc[0, '5m ORH'] == 'superseded'
    assert table.loc[0, '1m OR Result'] == 'success'
    assert table.loc[0, '5m OR Result'] == 'success'
    assert table.loc[0, 'ORH Display Suppression'] == '1m ORH, 5m ORH hidden because VWAP Reclaim trigger price is lower or equal'
    assert main_table(table).loc[0, '1m ORH'] == '-'
    assert main_table(table).loc[0, '5m ORH'] == '-'
    assert summary['VWAP Trigger'] == 1
    assert summary['Clean 1m'] == 0
    assert summary['Clean 5m'] == 0


def test_format_section_table_keeps_lower_orh_success_visible_when_vwap_is_higher():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': 'VWAP Reclaim',
        'raw_one_min_result': 'success',
        'raw_five_min_result': 'success',
        'one_min_result': 'success',
        'five_min_result': 'success',
        'or_1m': _or(orh=10.2),
        'or_5m': _or(orh=10.8),
        'vwap_reclaim_result': 'success',
        'vwap_reclaim_trigger_price': 10.4,
        'vwap_qualified_trigger_result': 'success',
        'vwap_qualified_trigger_reason': 'VWAP selected over fallback trigger',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.4,
        'reference_low': 9.8,
        'reference_basis': 'VWAP Reclaim',
        'trigger_break_time': pd.Timestamp('2026-05-01 10:10'),
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

    assert table.loc[0, '1m ORH'] == 'success'
    assert table.loc[0, '5m ORH'] == 'superseded'
    assert main_table(table).loc[0, '1m ORH'] == 'success'
    assert main_table(table).loc[0, '5m ORH'] == '-'


def test_format_section_table_keeps_orh_success_when_vwap_does_not_qualify():
    raw = pd.DataFrame([{
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'trigger_type': '5m ORH',
        'raw_one_min_result': 'failed',
        'raw_five_min_result': 'success',
        'one_min_result': 'failed',
        'five_min_result': 'success',
        'vwap_reclaim_result': 'success',
        'vwap_reclaim_trigger_price': 11.0,
        'vwap_qualified_trigger_result': '',
        'vwap_qualified_trigger_reason': '5m ORH trigger price is lower or unavailable',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': None,
        'retest_day': None,
        'fail_day': None,
        'setup': None,
        'rating': None,
        'trigger_level': 10.4,
        'reference_low': 9.8,
        'reference_basis': '5m ORH',
        'trigger_break_time': pd.Timestamp('2026-05-01 09:35'),
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

    assert table.loc[0, 'Trigger'] == '5m ORH'
    assert table.loc[0, '5m ORH'] == 'success'
    assert table.loc[0, 'VWAP Reclaim'] == '-'


def test_vwap_reclaim_fields_detect_stop_validity_from_existing_reference_low():
    intraday = pd.DataFrame({
        'ticker': ['AAPL'] * 390,
        'trading_date': ['2026-05-01'] * 390,
        'timestamp_et': pd.date_range('2026-05-01 09:30', periods=390, freq='min'),
        'open': [10.0] * 390,
        'high': [10.1] * 390,
        'low': [9.9] * 390,
        'close': [10.0] * 390,
        'volume': [1000] * 390,
    })
    mask = (intraday['timestamp_et'] >= pd.Timestamp('2026-05-01 10:00')) & (intraday['timestamp_et'] < pd.Timestamp('2026-05-01 10:05'))
    intraday.loc[mask, ['open', 'high', 'low', 'close']] = [10.6, 10.8, 10.5, 10.7]
    intraday.loc[intraday['timestamp_et'] == pd.Timestamp('2026-05-01 10:10'), 'high'] = 10.9
    intraday.loc[intraday['timestamp_et'] == pd.Timestamp('2026-05-01 10:11'), 'low'] = 9.4

    valid = _vwap_reclaim_fields(intraday, reference_low=9.3)
    invalid = _vwap_reclaim_fields(intraday, reference_low=9.5)

    assert valid['vwap_reclaim_result'] == 'success'
    assert valid['vwap_reclaim_trigger_price'] == 10.8
    assert valid['vwap_reclaim_stop_valid'] is True
    assert valid['vwap_reclaim_prior_below_vwap_observed'] is True
    assert invalid['vwap_reclaim_stop_valid'] is False


def test_format_section_table_derives_status_display_fields():
    base = {
        'candidate_id': 1,
        'ticker': 'AAPL',
        'status': 'Active',
        'one_min_result': 'success',
        'five_min_result': '',
        'notes': '',
        'current_pct': 0.01,
        'max_pct': 0.03,
        'd3_high_pct': 0.05,
        'retest_day': None,
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
    }
    raw = pd.DataFrame([
        {**base, 'candidate_id': 1, 'trigger_type': '1m ORH', 'fail_day': None},
        {**base, 'candidate_id': 2, 'trigger_type': '5m ORH', 'fail_day': 1},
        {**base, 'candidate_id': 3, 'trigger_type': 'Failed OR Trigger', 'fail_day': 0},
        {**base, 'candidate_id': 4, 'trigger_type': 'No Trigger', 'fail_day': None},
    ])

    table = _format_section_table(raw)

    assert table['Trigger Day'].tolist() == ['Success', 'Success', 'Fail', 'Unresolved']
    assert table['Current Status'].tolist() == ['Active', 'Failed D1', '—', '—']


def test_day_summary_metrics():
    df = pd.DataFrame([
        {'Trigger': '1m ORH', '1m ORH': 'success', '5m ORH': '', 'Trigger Day': 'Success', 'Current Status': 'Active', 'Retests': 'D1', 'current_pct_raw': 0.10, 'max_pct_raw': 0.20, 'd3_high_pct_raw': 0.25},
        {'Trigger': 'Alt Required', '1m ORH': 'failed', '5m ORH': 'failed', 'Trigger Day': 'Success', 'Current Status': 'Failed D2', 'Retests': '', 'current_pct_raw': 0.00, 'max_pct_raw': 0.10, 'd3_high_pct_raw': 0.15},
        {'Trigger': 'No Trigger', '1m ORH': '', '5m ORH': '', 'Trigger Day': 'Unresolved', 'Current Status': '—', 'Retests': '', 'current_pct_raw': None, 'max_pct_raw': None, 'd3_high_pct_raw': None},
    ])

    summary = day_summary(df)

    assert summary['Setups'] == 3
    assert summary['Clean 1m'] == 1
    assert summary['Alt Required'] == 1
    assert summary['No Trigger'] == 1
    assert summary['1m Failed'] == 1
    assert summary['5m Failed'] == 1
    assert summary['Day Success'] == 2
    assert summary['Day Fail'] == 0
    assert summary['Unresolved'] == 1
    assert summary['Active'] == 1
    assert summary['Later Failed'] == 1
    assert summary['Retested'] == 1
    assert summary['Median Current %'] == '5.0%'
    assert summary['Median Max %'] == '15.0%'
    assert summary['Median D3 High %'] == '20.0%'


def test_day_summary_counts_pdh_and_excludes_pdh_rows_from_orh_counts():
    muted = current_status_display('Fail', 0)
    df = pd.DataFrame([
        {'Trigger': 'PDH', '1m ORH': '-', '5m ORH': '-', 'Trigger Day': 'Success', 'Current Status': 'Active', 'Retests': '', 'current_pct_raw': 0.04, 'max_pct_raw': 0.08, 'd3_high_pct_raw': 0.10},
        {'Trigger': 'Failed PDH Trigger', '1m ORH': '-', '5m ORH': '-', 'Trigger Day': 'Fail', 'Current Status': muted, 'Retests': '', 'current_pct_raw': -0.01, 'max_pct_raw': 0.02, 'd3_high_pct_raw': 0.03},
        {'Trigger': '1m ORH', 'PDH': 'Gap', '1m ORH': 'success', '5m ORH': 'success', 'Trigger Day': 'Success', 'Current Status': 'Active', 'Retests': '', 'current_pct_raw': 0.02, 'max_pct_raw': 0.04, 'd3_high_pct_raw': 0.05},
    ])

    summary = day_summary(df)

    assert summary['PDH'] == 1
    assert summary['PDH Gap'] == 1
    assert summary['Failed PDH Trigger'] == 1
    assert summary['Clean 1m'] == 1
    assert summary['Clean 5m'] == 1
    assert summary['1m Failed'] == 0
    assert summary['5m Failed'] == 0


def test_sort_monitor_rows_current_status_then_current_pct():
    df = pd.DataFrame([
        {'Ticker': 'FAIL', 'Current Status': 'Failed D1', 'current_pct_raw': 0.50},
        {'Ticker': 'UNRES', 'Current Status': '—', 'current_pct_raw': 0.30},
        {'Ticker': 'ACTIVE2', 'Current Status': 'Active', 'current_pct_raw': 0.10},
        {'Ticker': 'ACTIVE1', 'Current Status': 'Active', 'current_pct_raw': 0.20},
    ])

    out = sort_monitor_rows(df)

    assert out['Ticker'].tolist() == ['ACTIVE1', 'ACTIVE2', 'FAIL', 'UNRES']


def test_setup_dropdown_preserves_unknown_existing_value():
    df = pd.DataFrame({'Setup': ['Custom Pattern', 'EP'], 'Entry Tactic': ['Bias Flip', 'Custom Tactic'], 'Rating': ['7', '1']})

    assert 'Pullback' in setup_dropdown_options(df)
    assert 'Custom Pattern' in setup_dropdown_options(df)
    assert 'Bias Flip' in entry_tactic_dropdown_options(df)
    assert 'Custom Tactic' in entry_tactic_dropdown_options(df)
    assert '7' in rating_dropdown_options(df)


def test_apply_setup_rating_updates_only_manual_fields():
    con = duckdb.connect(':memory:')
    con.execute('create table watchlist_candidates (candidate_id bigint, setup text, rating double, ticker text)')
    con.execute("insert into watchlist_candidates values (1, 'EP', 2, 'AAPL')")
    original = pd.DataFrame([{'candidate_id': 1, 'Setup': 'EP', 'Rating': '2', 'Status': 'Active'}])
    edited = pd.DataFrame([{'candidate_id': 1, 'Setup': 'Pullback', 'Rating': '3', 'Status': 'Failed'}])

    changed = apply_setup_rating_updates(con, original, edited)
    row = con.execute('select setup,entry_tactic,rating,ticker from watchlist_candidates where candidate_id=1').fetchone()

    assert changed == 1
    assert row == ('Pullback', None, 3.0, 'AAPL')


def test_apply_setup_rating_updates_persists_setup_entry_tactic_and_rating():
    con = duckdb.connect(':memory:')
    con.execute('create table watchlist_candidates (candidate_id bigint, setup text, entry_tactic text, rating double, ticker text)')
    con.execute("insert into watchlist_candidates values (1, 'EP', null, 2, 'AAPL')")
    original = pd.DataFrame([{'candidate_id': 1, 'Setup': 'EP', 'Entry Tactic': '', 'Rating': '2'}])
    edited = pd.DataFrame([{'candidate_id': 1, 'Setup': 'Pullback', 'Entry Tactic': 'Bias Flip', 'Rating': '4'}])

    changed = apply_setup_rating_updates(con, original, edited)
    row = con.execute('select setup,entry_tactic,rating from watchlist_candidates where candidate_id=1').fetchone()

    assert changed == 1
    assert row == ('Pullback', 'Bias Flip', 4.0)


def test_apply_setup_rating_updates_handles_no_change_and_blanks():
    con = duckdb.connect(':memory:')
    con.execute('create table watchlist_candidates (candidate_id bigint, setup text, entry_tactic text, rating double, ticker text)')
    con.execute("insert into watchlist_candidates values (1, 'Pullback', 'Reclaim', 4, 'AAPL')")
    original = pd.DataFrame([{'candidate_id': 1, 'Setup': 'Pullback', 'Entry Tactic': 'Reclaim', 'Rating': '4'}])

    assert apply_setup_rating_updates(con, original, original.copy()) == 0

    edited = pd.DataFrame([{'candidate_id': 1, 'Setup': '', 'Entry Tactic': '', 'Rating': ''}])
    assert apply_setup_rating_updates(con, original, edited) == 1
    assert con.execute('select setup,entry_tactic,rating from watchlist_candidates where candidate_id=1').fetchone() == (None, None, None)


def test_apply_setup_rating_updates_all_entry_tactic_options_persist():
    for tactic in ['Bias Flip', 'Gap Over Range', 'Micro Gap', 'OR Range Break', 'Reclaim']:
        con = duckdb.connect(':memory:')
        con.execute('create table watchlist_candidates (candidate_id bigint, setup text, entry_tactic text, rating double, ticker text)')
        con.execute("insert into watchlist_candidates values (1, null, null, null, 'AAPL')")
        original = pd.DataFrame([{'candidate_id': 1, 'Setup': '', 'Entry Tactic': '', 'Rating': ''}])
        edited = pd.DataFrame([{'candidate_id': 1, 'Setup': '', 'Entry Tactic': tactic, 'Rating': ''}])

        assert apply_setup_rating_updates(con, original, edited) == 1
        assert con.execute('select entry_tactic from watchlist_candidates where candidate_id=1').fetchone()[0] == tactic


def test_apply_setup_rating_updates_rejects_invalid_entry_tactic():
    con = duckdb.connect(':memory:')
    con.execute('create table watchlist_candidates (candidate_id bigint, setup text, entry_tactic text, rating double, ticker text)')
    con.execute("insert into watchlist_candidates values (1, null, null, null, 'AAPL')")
    original = pd.DataFrame([{'candidate_id': 1, 'Setup': '', 'Entry Tactic': '', 'Rating': ''}])
    edited = pd.DataFrame([{'candidate_id': 1, 'Setup': '', 'Entry Tactic': 'Chase', 'Rating': ''}])

    try:
        apply_setup_rating_updates(con, original, edited)
    except ValueError as exc:
        assert 'Invalid Entry Tactic: Chase' in str(exc)
    else:
        raise AssertionError('Expected ValueError')
