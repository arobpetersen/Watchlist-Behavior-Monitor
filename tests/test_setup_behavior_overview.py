from __future__ import annotations

import math

import duckdb
import pandas as pd

from src.setup_behavior_overview import (
    COMPARISON_COLUMNS,
    DETAIL_COLUMNS,
    FULL_SUMMARY_COLUMNS,
    SUMMARY_COLUMNS,
    comparison_rows,
    detail_rows,
    factual_read,
    monitor_history,
    overview_windows,
    selected_window_metrics,
    setup_behavior_overview,
    summarize_window,
)


def _history() -> pd.DataFrame:
    return pd.DataFrame([
        {
            'Setup Date': '2026-05-08',
            'Ticker': 'AAA',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': '1m ORH',
            '1m ORH': 'success',
            '5m ORH': 'success',
            'Notes': 'Wide 1m OR',
            'Current %': '5.0%',
            'Max %': '10.0%',
            'D3 High %': '-',
            'Retest Day': 'D1',
            'Setup': 'EP',
            'Rating': '3',
            'current_pct_raw': 0.05,
            'max_pct_raw': 0.10,
            'd3_high_pct_raw': math.nan,
        },
        {
            'Setup Date': '2026-05-08',
            'Ticker': 'EEE',
            'Current Status': 'Failed D1',
            'Trigger Day': 'Success',
            'Trigger': 'Alt Required',
            '1m ORH': 'failed',
            '5m ORH': 'failed',
            'Notes': '',
            'Current %': '2.0%',
            'Max %': '6.0%',
            'D3 High %': '7.0%',
            'Retest Day': '',
            'Setup': 'nan',
            'Rating': '',
            'current_pct_raw': 0.02,
            'max_pct_raw': 0.06,
            'd3_high_pct_raw': 0.07,
        },
        {
            'Setup Date': '2026-05-02',
            'Ticker': 'BBB',
            'Current Status': 'Failed D2',
            'Trigger Day': 'Success',
            'Trigger': '5m ORH',
            '1m ORH': 'failed',
            '5m ORH': 'success',
            'Notes': 'Wide 5m OR',
            'Current %': '1.0%',
            'Max %': '8.0%',
            'D3 High %': '12.0%',
            'Retest Day': '',
            'Setup': '',
            'Rating': '',
            'current_pct_raw': 0.01,
            'max_pct_raw': 0.08,
            'd3_high_pct_raw': 0.12,
        },
        {
            'Setup Date': '2026-04-28',
            'Ticker': 'CCC',
            'Current Status': '—',
            'Trigger Day': 'Fail',
            'Trigger': 'Failed OR Trigger',
            '1m ORH': 'failed',
            '5m ORH': 'failed',
            'Notes': 'Wide 1m OR; Wide 5m OR',
            'Current %': '-1.0%',
            'Max %': '2.0%',
            'D3 High %': '3.0%',
            'Retest Day': 'D0',
            'Setup': 'Pullback',
            'Rating': '2',
            'current_pct_raw': -0.01,
            'max_pct_raw': 0.02,
            'd3_high_pct_raw': 0.03,
        },
        {
            'Setup Date': '2026-04-10',
            'Ticker': 'DDD',
            'Current Status': '—',
            'Trigger Day': 'Unresolved',
            'Trigger': 'No Trigger',
            '1m ORH': '',
            '5m ORH': '',
            'Notes': '',
            'Current %': '',
            'Max %': '',
            'D3 High %': '-',
            'Retest Day': '',
            'Setup': '',
            'Rating': '',
            'current_pct_raw': None,
            'max_pct_raw': None,
            'd3_high_pct_raw': None,
        },
    ])


def test_overview_windows_use_latest_setup_date_as_end():
    windows = overview_windows('2026-05-08')

    assert [(w.label, w.start_date.date().isoformat(), w.end_date.date().isoformat()) for w in windows] == [
        ('Last 1 Week', '2026-05-01', '2026-05-08'),
        ('Last 2 Weeks', '2026-04-24', '2026-05-08'),
        ('Last 1 Month', '2026-04-08', '2026-05-08'),
    ]


def test_summarize_window_counts_percentages_and_medians():
    window = overview_windows('2026-05-08')[1]
    out = summarize_window(_history(), window)

    assert out['Window'] == 'Last 2 Weeks'
    assert out['Dates'] == '2026-04-24 to 2026-05-08'
    assert out['Setup Dates'] == 3
    assert out['Setups'] == 4
    assert out['Day Success'] == '3 (75%)'
    assert out['Day Fail'] == '1 (25%)'
    assert out['Unresolved'] == '0 (0%)'
    assert out['Active'] == '1 (25%)'
    assert out['Later Failed'] == '2 (50%)'
    assert out['Clean 1m'] == '1 (25%)'
    assert out['Failed 1m'] == '3 (75%)'
    assert out['Clean 5m'] == '2 (50%)'
    assert out['Failed 5m'] == '2 (50%)'
    assert out['Alt Required'] == '1 (25%)'
    assert out['Failed OR Trigger'] == '1 (25%)'
    assert out['No Trigger'] == '0 (0%)'
    assert out['Retested'] == '2 (50%)'
    assert out['Wide 1m OR'] == '2 (50%)'
    assert out['Wide 5m OR'] == '2 (50%)'
    assert out['Median Current'] == '1.5%'
    assert out['Median Max'] == '7.0%'
    assert out['Median D3 High'] == '7.0%'


def test_comparison_rows_exclude_secondary_diagnostics():
    full = pd.DataFrame([summarize_window(_history(), window) for window in overview_windows('2026-05-08')], columns=FULL_SUMMARY_COLUMNS)
    comparison = comparison_rows(full)

    assert comparison.columns.tolist() == COMPARISON_COLUMNS
    assert comparison['Window'].tolist() == ['Last 1 Week', 'Last 2 Weeks', 'Last 1 Month']
    assert 'Failed 1m' not in comparison.columns
    assert 'Failed 5m' not in comparison.columns
    assert 'Failed OR Trigger' not in comparison.columns
    assert 'Retested' not in comparison.columns
    assert 'Wide 1m OR' not in comparison.columns


def test_summarize_window_empty_and_unavailable_values_format_cleanly():
    window = overview_windows('2026-05-08')[0]
    empty = summarize_window(pd.DataFrame(columns=_history().columns), window)

    assert empty['Setups'] == 0
    assert empty['Day Success'] == '0 (0%)'
    assert empty['Median Current'] == '-'
    assert empty['Median Max'] == '-'
    assert empty['Median D3 High'] == '-'

    one_incomplete = summarize_window(_history().iloc[[0]], window)
    assert one_incomplete['Median D3 High'] == '-'


def test_detail_rows_match_expected_columns_and_window_filter():
    window = overview_windows('2026-05-08')[0]
    detail = detail_rows(_history(), window)

    assert detail.columns.tolist() == DETAIL_COLUMNS
    assert detail['Ticker'].tolist() == ['AAA', 'EEE', 'BBB']
    assert detail.loc[0, 'D3 High'] == '-'
    assert detail.loc[1, 'Setup'] == '-'
    assert detail.loc[1, 'Rating'] == '-'


def test_detail_rows_sort_by_date_status_priority_and_current():
    window = overview_windows('2026-05-08')[0]
    detail = detail_rows(_history(), window)

    assert detail[['Ticker', 'Current Status', 'Current']].values.tolist() == [
        ['AAA', 'Active', '5.0%'],
        ['EEE', 'Failed D1', '2.0%'],
        ['BBB', 'Failed D2', '1.0%'],
    ]


def test_selected_window_metrics_group_diagnostics_separately():
    summary = summarize_window(_history(), overview_windows('2026-05-08')[1])
    groups = selected_window_metrics(summary)

    assert [group['title'] for group in groups] == [
        'Trigger Day Quality',
        'Current Outcome',
        'Trigger Mix',
        'Diagnostics',
    ]
    comparison = comparison_rows(pd.DataFrame([summary], columns=FULL_SUMMARY_COLUMNS))
    diagnostics = dict(groups[3]['metrics'])

    assert 'Failed 1m' not in comparison.columns
    assert diagnostics['Failed 1m'] == '3 (75%)'
    assert diagnostics['Failed 5m'] == '2 (50%)'
    assert diagnostics['Wide 1m OR'] == '2 (50%)'


def test_factual_read_is_objective_and_contains_key_metrics():
    summary = summarize_window(_history(), overview_windows('2026-05-08')[1])
    text = factual_read(summary)

    assert 'Last 2 Weeks includes 4 setups across 3 setup dates.' in text
    assert '3 (75%) succeeded on trigger day' in text
    assert '1 (25%) remain active' in text
    assert '2 (50%) failed later' in text
    assert 'Median current return is 1.5%' in text
    assert 'median max return is 7.0%' in text
    lowered = text.lower()
    assert 'trade more aggressively' not in lowered
    assert 'avoid' not in lowered
    assert 'recommended' not in lowered
    assert 'market is good' not in lowered
    assert 'market is bad' not in lowered


def test_monitor_history_uses_rolling_setup_monitor_derived_rows(monkeypatch):
    calls = []

    def fake_setup_dates(_con):
        return [pd.Timestamp('2026-05-01'), pd.Timestamp('2026-05-08')]

    def fake_rolling_setup_monitor(_con, setup_dates):
        calls.append(setup_dates)
        return [{
            'setup_date': '2026-05-08',
            'table': pd.DataFrame([{
                'Ticker': 'LAR',
                'Current Status': 'Failed D1',
                'Trigger Day': 'Success',
                'Trigger': '5m ORH',
                '1m ORH': 'failed',
                '5m ORH': 'success',
                'current_pct_raw': 0.01,
                'max_pct_raw': 0.02,
                'd3_high_pct_raw': 0.03,
            }]),
        }]

    monkeypatch.setattr('src.setup_behavior_overview.setup_dates', fake_setup_dates)
    monkeypatch.setattr('src.setup_behavior_overview.rolling_setup_monitor', fake_rolling_setup_monitor)

    history = monitor_history(object())

    assert calls == [2]
    assert history.loc[0, 'Ticker'] == 'LAR'
    assert history.loc[0, 'Current Status'] == 'Failed D1'
    assert history.loc[0, 'Trigger Day'] == 'Success'
    assert history.loc[0, 'Trigger'] == '5m ORH'
    assert history.loc[0, '5m ORH'] == 'success'


def test_setup_behavior_overview_handles_zero_setup_dates():
    con = duckdb.connect(':memory:')
    con.execute('create table watchlist_candidates (watchlist_date date)')

    out = setup_behavior_overview(con)

    assert out['summary'].columns.tolist() == SUMMARY_COLUMNS
    assert out['summary'].empty
    assert out['window_summaries'].columns.tolist() == FULL_SUMMARY_COLUMNS
    assert out['breakdowns'] == {}
    assert out['reads'] == {}
    assert out['details'] == {}
    assert out['windows'] == []
