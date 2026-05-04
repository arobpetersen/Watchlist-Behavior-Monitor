from __future__ import annotations

import math

import duckdb
import pandas as pd

from src.setup_behavior_overview import (
    COMPARISON_COLUMNS,
    DETAIL_COLUMNS,
    FULL_SUMMARY_COLUMNS,
    MAIN_OPENING_TRIGGERS,
    OPENING_BEHAVIOR_MAIN_COLUMNS,
    SUMMARY_COLUMNS,
    TRIGGER_EVENT_MAIN_COLUMNS,
    TRIGGER_COMPARISON_BY_WINDOW_COLUMNS,
    TRIGGER_COMPARISON_COLUMNS,
    comparison_rows,
    detail_rows,
    factual_read,
    filter_detail_rows,
    main_opening_behavior_table,
    mix_tables,
    monitor_history,
    opening_behavior_table,
    overview_windows,
    resolve_display_triggers,
    selected_window_metrics,
    selected_window_snapshot,
    snapshot_cards_html,
    setup_behavior_overview,
    summarize_window,
    trigger_outcome_by_window_tables,
    trigger_outcome_comparison,
    trigger_event_main_tables,
    trigger_quality_table,
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
            'VWAP Trigger': '',
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
            'VWAP Trigger': '',
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
            'VWAP Trigger': '',
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
            'VWAP Trigger': '',
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


def test_overview_windows_use_actual_setup_dates_not_calendar_days():
    windows = overview_windows(['2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30', '2026-05-01'])

    assert [(w.label, [d.date().isoformat() for d in w.setup_dates]) for w in windows] == [
        ('Last 5 Setup Dates', ['2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30', '2026-05-01']),
        ('Last 10 Setup Dates', ['2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30', '2026-05-01']),
        ('Last 20 Setup Dates', ['2026-04-27', '2026-04-28', '2026-04-29', '2026-04-30', '2026-05-01']),
    ]


def test_overview_windows_keep_only_latest_n_setup_dates():
    dates = pd.date_range('2026-04-01', periods=25, freq='B')
    windows = overview_windows(dates)

    assert len(windows[0].setup_dates) == 5
    assert len(windows[1].setup_dates) == 10
    assert len(windows[2].setup_dates) == 20
    assert windows[0].setup_dates[0] == pd.Timestamp('2026-04-29')
    assert windows[0].setup_dates[-1] == pd.Timestamp('2026-05-05')


def test_summarize_window_counts_percentages_and_medians():
    window = overview_windows(['2026-04-28', '2026-05-02', '2026-05-08'])[1]
    out = summarize_window(_history(), window)

    assert out['Window'] == 'Last 10 Setup Dates'
    assert out['Dates'] == '2026-04-28 → 2026-05-08'
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
    assert out['D3 Eligible'] == '3 (75%)'
    assert out['Median Current'] == '1.5%'
    assert out['Median Max'] == '7.0%'
    assert out['Median D3 High'] == '7.0%'


def test_comparison_rows_exclude_secondary_diagnostics():
    full = pd.DataFrame([summarize_window(_history(), window) for window in overview_windows(['2026-04-10', '2026-04-28', '2026-05-02', '2026-05-08'])], columns=FULL_SUMMARY_COLUMNS)
    comparison = comparison_rows(full)

    assert comparison.columns.tolist() == COMPARISON_COLUMNS
    assert comparison['Window'].tolist() == ['Last 5 Setup Dates', 'Last 10 Setup Dates', 'Last 20 Setup Dates']
    assert comparison.columns.tolist() == [
        'Window',
        'Dates',
        'Setup Dates',
        'Setups',
        'Day Success %',
        'Active %',
        'Later Failed %',
        'Median Current',
        'Median Max',
    ]
    assert 'Failed 1m' not in comparison.columns
    assert 'Failed 5m' not in comparison.columns
    assert 'Failed OR Trigger' not in comparison.columns
    assert 'Retested' not in comparison.columns
    assert 'Wide 1m OR' not in comparison.columns
    assert 'Median D3 High' not in comparison.columns


def test_summarize_window_empty_and_unavailable_values_format_cleanly():
    window = overview_windows(['2026-05-08'])[0]
    empty = summarize_window(pd.DataFrame(columns=_history().columns), window)

    assert empty['Setups'] == 0
    assert empty['Day Success'] == '0 (0%)'
    assert empty['Median Current'] == '-'
    assert empty['Median Max'] == '-'
    assert empty['Median D3 High'] == '-'

    one_incomplete = summarize_window(_history().iloc[[0]], window)
    assert one_incomplete['Median D3 High'] == '-'
    assert one_incomplete['D3 Eligible'] == '0 (0%)'


def test_detail_rows_match_expected_columns_and_window_filter():
    window = overview_windows(['2026-05-02', '2026-05-08'])[0]
    detail = detail_rows(_history(), window)

    assert detail.columns.tolist() == DETAIL_COLUMNS
    assert detail.columns.tolist()[5:9] == ['PDH', '1m ORH', 'VWAP Reclaim', '5m ORH']
    assert 'VWAP Trigger' not in detail.columns
    assert 'Close < BE' in detail.columns
    assert detail['Ticker'].tolist() == ['AAA', 'EEE', 'BBB']
    assert detail.loc[0, 'D3 High'] == '-'
    assert detail.loc[1, 'Setup'] == '-'
    assert detail.loc[1, 'Rating'] == '-'


def test_detail_rows_sort_by_date_status_priority_and_current():
    window = overview_windows(['2026-05-02', '2026-05-08'])[0]
    detail = detail_rows(_history(), window)

    assert detail[['Ticker', 'Current Status', 'Current']].values.tolist() == [
        ['AAA', 'Active', '5.0%'],
        ['EEE', 'Failed D1', '2.0%'],
        ['BBB', 'Failed D2', '1.0%'],
    ]


def test_selected_window_metrics_group_diagnostics_separately():
    summary = summarize_window(_history(), overview_windows(['2026-04-28', '2026-05-02', '2026-05-08'])[1])
    groups = selected_window_metrics(summary)

    assert [group['title'] for group in groups] == [
        'Trigger Day Quality',
        'Current Outcome',
        'Trigger Mix',
        'Diagnostics',
    ]
    comparison = comparison_rows(pd.DataFrame([summary], columns=FULL_SUMMARY_COLUMNS))
    diagnostics = dict(groups[3]['metrics'])
    current_outcome = dict(groups[1]['metrics'])

    assert 'Failed 1m' not in comparison.columns
    assert current_outcome['D3 Eligible'] == '3 (75%)'
    assert diagnostics['Failed 1m'] == '3 (75%)'
    assert diagnostics['Failed 5m'] == '2 (50%)'
    assert diagnostics['Wide 1m OR'] == '2 (50%)'


def test_pdh_trigger_mix_aggregation_stays_out_of_top_comparison():
    history = _history().copy()
    history.loc[0, 'Trigger'] = 'PDH'
    history.loc[0, 'PDH'] = 'success'
    history.loc[0, '1m ORH'] = '-'
    history.loc[0, '5m ORH'] = '-'
    history.loc[1, 'Trigger'] = 'Failed PDH Trigger'
    history.loc[1, 'PDH'] = 'failed'
    history.loc[1, '1m ORH'] = '-'
    history.loc[1, '5m ORH'] = '-'
    summary = summarize_window(history, overview_windows(['2026-05-02', '2026-05-08'])[0])
    groups = selected_window_metrics(summary)
    trigger_mix = dict(groups[2]['metrics'])
    comparison = comparison_rows(pd.DataFrame([summary], columns=FULL_SUMMARY_COLUMNS))

    assert summary['PDH'] == '1 (33%)'
    assert summary['Failed PDH Trigger'] == '1 (33%)'
    assert summary['Clean 1m'] == '0 (0%)'
    assert summary['Failed 1m'] == '1 (33%)'
    assert summary['Clean 5m'] == '1 (33%)'
    assert summary['Failed 5m'] == '0 (0%)'
    assert trigger_mix['PDH'] == '1 (33%)'
    assert trigger_mix['Failed PDH Trigger'] == '1 (33%)'
    assert 'PDH' not in comparison.columns
    assert 'Failed PDH Trigger' not in comparison.columns


def test_overview_5m_counts_exclude_selected_1m_rows_with_5m_display_hidden():
    history = _history().copy()
    history.loc[0, 'Trigger'] = '1m ORH'
    history.loc[0, '1m ORH'] = 'success'
    history.loc[0, '5m ORH'] = '-'

    summary = summarize_window(history.iloc[[0]], overview_windows(['2026-05-08'])[0])

    assert summary['Clean 1m'] == '1 (100%)'
    assert summary['Clean 5m'] == '0 (0%)'
    assert summary['Failed 5m'] == '0 (0%)'


def test_factual_read_is_objective_and_contains_key_metrics():
    summary = summarize_window(_history(), overview_windows(['2026-04-28', '2026-05-02', '2026-05-08'])[1])
    text = factual_read(summary, opening_behavior_table(_history().iloc[:4]))

    assert text == (
        'Last 10 Setup Dates: 4 setups across 3 setup dates, 75% Day Success, '
        '25% Active, 50% Later Failed, 1.5% Median Current, 7.0% Median Max.'
    )
    lowered = text.lower()
    assert 'trade more aggressively' not in lowered
    assert 'avoid' not in lowered
    assert 'recommended' not in lowered
    assert 'market is good' not in lowered
    assert 'market is bad' not in lowered


def test_selected_window_snapshot_contains_key_metrics():
    summary = summarize_window(_history(), overview_windows(['2026-04-28', '2026-05-02', '2026-05-08'])[1])
    text = selected_window_snapshot(summary)

    assert '4 setups across 3 setup dates' in text
    assert '75% Day Success' in text
    assert '25% Active' in text
    assert '50% Later Failed' in text
    assert 'Median Current 1.5%' in text
    assert 'Median Max 7.0%' in text


def test_snapshot_cards_html_prioritizes_key_metrics():
    summary = summarize_window(_history(), overview_windows(['2026-04-28', '2026-05-02', '2026-05-08'])[1])
    html = snapshot_cards_html(summary)

    assert 'Scope' in html
    assert 'Trigger Day' in html
    assert 'Current Outcome' in html
    assert 'Follow-Through' in html
    assert '75%' in html
    assert '1.5%' in html
    assert '7.0%' in html


def test_mix_tables_include_objective_selected_window_mixes():
    summary = summarize_window(_history(), overview_windows(['2026-04-28', '2026-05-02', '2026-05-08'])[1])
    mixes = mix_tables(summary)

    assert list(mixes) == ['Outcome Mix', 'Current Mix', 'Trigger Mix']
    assert mixes['Outcome Mix']['Metric'].tolist() == ['Day Success', 'Day Fail', 'Unresolved']
    assert 'PDH' in mixes['Trigger Mix']['Metric'].tolist()
    assert 'Failed OR Trigger' in mixes['Trigger Mix']['Metric'].tolist()


def test_trigger_quality_table_groups_by_selected_trigger():
    quality = trigger_quality_table(_history())
    by_trigger = quality.set_index('Trigger')

    assert by_trigger.loc['1m ORH', 'Count'] == 1
    assert by_trigger.loc['1m ORH', 'Failed Count'] == 0
    assert by_trigger.loc['1m ORH', 'Failed %'] == '0%'
    assert by_trigger.loc['1m ORH', 'Day Success %'] == '100%'
    assert by_trigger.loc['1m ORH', 'Active %'] == '100%'
    assert by_trigger.loc['1m ORH', 'Later Failed %'] == '0%'
    assert by_trigger.loc['5m ORH', 'Count'] == 1
    assert by_trigger.loc['5m ORH', 'Failed Count'] == 1
    assert by_trigger.loc['5m ORH', 'Failed %'] == '100%'
    assert by_trigger.loc['5m ORH', 'Active %'] == '0%'
    assert by_trigger.loc['5m ORH', 'Later Failed %'] == '100%'
    assert by_trigger.loc['No Trigger', 'Day Success %'] == '0%'
    assert by_trigger.loc['PDH', 'Count'] == 0


def test_vwap_reclaim_resolves_as_display_trigger_after_orh_before_alt():
    rows = pd.DataFrame([
        {
            'Ticker': 'VWAP',
            'Trigger': 'Alt Required',
            'Trigger Day': 'Success',
            '1m ORH': 'failed',
            '5m ORH': 'failed',
            'VWAP Reclaim': 'success',
            'VWAP Reclaim Trigger Price': 10.5,
            'PDH': '-',
        },
        {
            'Ticker': 'ONE',
            'Trigger': '1m ORH',
            'Trigger Day': 'Success',
            '1m ORH': 'success',
            '5m ORH': '-',
            'VWAP Reclaim': 'success',
            'VWAP Reclaim Trigger Price': 9.5,
            'Trigger Level': 10.0,
            'PDH': 'Gap',
        },
        {
            'Ticker': 'PDH',
            'Trigger': 'PDH',
            'Trigger Day': 'Success',
            '1m ORH': '-',
            '5m ORH': '-',
            'VWAP Reclaim': 'success',
            'VWAP Reclaim Trigger Price': 9.5,
            'PDH': 'success',
        },
        {
            'Ticker': 'ALT',
            'Trigger': 'Alt Required',
            'Trigger Day': 'Success',
            '1m ORH': 'failed',
            '5m ORH': 'failed',
            'VWAP Reclaim': '',
            'PDH': '-',
        },
    ])

    out = resolve_display_triggers(rows)

    assert out['Trigger'].tolist() == ['VWAP Reclaim', 'VWAP Reclaim', 'PDH', 'Alt Required']


def test_vwap_reclaim_higher_price_preserves_orh_display_trigger():
    rows = pd.DataFrame([{
        'Ticker': 'ONE',
        'Trigger': '1m ORH',
        'Trigger Day': 'Success',
        '1m ORH': 'success',
        '5m ORH': '-',
        'VWAP Reclaim': 'success',
        'VWAP Reclaim Trigger Price': 10.5,
        'Trigger Level': 10.0,
        'PDH': 'Gap',
    }])

    out = resolve_display_triggers(rows)

    assert out.loc[0, 'Trigger'] == '1m ORH'
    assert out.loc[0, 'vwap_qualified_trigger_result'] == ''


def test_vwap_reclaim_lower_price_promotes_over_5m_orh():
    rows = pd.DataFrame([{
        'Ticker': 'FIVE',
        'Trigger': '5m ORH',
        'Trigger Day': 'Success',
        '1m ORH': 'failed',
        '5m ORH': 'success',
        'VWAP Reclaim': 'success',
        'VWAP Reclaim Trigger Price': 10.5,
        'Trigger Level': 11.0,
        'PDH': 'Gap',
    }])

    out = resolve_display_triggers(rows)

    assert out.loc[0, 'Trigger'] == 'VWAP Reclaim'
    assert out.loc[0, 'vwap_qualified_trigger_result'] == 'success'


def test_vwap_reclaim_stop_invalid_prevents_display_trigger_promotion():
    rows = pd.DataFrame([{
        'Ticker': 'FIVE',
        'Trigger': '5m ORH',
        'Trigger Day': 'Success',
        '1m ORH': 'failed',
        '5m ORH': 'success',
        'VWAP Reclaim': 'success',
        'VWAP Reclaim Trigger Price': 10.5,
        'VWAP Reclaim Stop Valid': False,
        'Trigger Level': 11.0,
        'PDH': 'Gap',
    }])

    out = resolve_display_triggers(rows)

    assert out.loc[0, 'Trigger'] == '5m ORH'
    assert out.loc[0, 'vwap_qualified_trigger_result'] == ''


def test_vwap_reclaim_raw_non_success_results_do_not_qualify():
    rows = pd.DataFrame([
        {'Ticker': 'FAILED', 'Trigger': 'Alt Required', 'VWAP Reclaim': 'failed', 'VWAP Reclaim Trigger Price': 10.5},
        {'Ticker': 'BLANK', 'Trigger': 'Alt Required', 'VWAP Reclaim': '', 'VWAP Reclaim Trigger Price': 10.5},
        {'Ticker': 'NA', 'Trigger': 'Alt Required', 'VWAP Reclaim': 'Not Applicable', 'VWAP Reclaim Trigger Price': 10.5},
    ])

    out = resolve_display_triggers(rows)

    assert out['Trigger'].tolist() == ['Alt Required', 'Alt Required', 'Alt Required']
    assert out['vwap_qualified_trigger_result'].tolist() == ['', '', '']


def test_vwap_reclaim_display_trigger_appears_in_detail_rows():
    history = pd.DataFrame([{
        'Setup Date': '2026-05-08',
        'Ticker': 'VWAP',
        'Current Status': 'Active',
        'Trigger Day': 'Success',
        'Trigger': 'Alt Required',
        'VWAP Reclaim Trigger Price': 10.5,
        'PDH': '-',
        '1m ORH': 'failed',
        '5m ORH': 'failed',
        'VWAP Reclaim': 'success',
        'Notes': '',
        'Current %': '4.0%',
        'Max %': '11.0%',
        'D3 High %': '-',
        'Retest Day': '',
        'Setup': '',
        'Rating': '',
        'current_pct_raw': 0.04,
        'max_pct_raw': 0.11,
    }])
    resolved = resolve_display_triggers(history)

    detail = detail_rows(resolved, overview_windows(['2026-05-08'])[0])

    assert detail.loc[0, 'Trigger'] == 'VWAP Reclaim'
    assert detail.loc[0, 'VWAP Reclaim'] == 'success'


def test_detail_rows_hides_superseded_orh_when_vwap_is_resolved_trigger():
    history = pd.DataFrame([{
        'Setup Date': '2026-05-08',
        'Ticker': 'VWAP',
        'Current Status': 'Active',
        'Trigger Day': 'Success',
        'Trigger': 'VWAP Reclaim',
        '1m ORH': 'failed',
        '5m ORH': 'success',
        'VWAP Trigger': 'success',
        'vwap_qualified_trigger_reason': 'VWAP trigger price lower than 5m ORH',
        'PDH': '-',
        'Notes': '',
        'Close < BE': 'Yes',
        'Current %': '4.0%',
        'Max %': '11.0%',
        'D3 High %': '-',
        'Retest Day': '',
        'Setup': '',
        'Rating': '',
        'current_pct_raw': 0.04,
        'max_pct_raw': 0.11,
    }])

    detail = detail_rows(history, overview_windows(['2026-05-08'])[0])

    assert detail.loc[0, 'Trigger'] == 'VWAP Reclaim'
    assert detail.loc[0, '5m ORH'] == '-'
    assert detail.loc[0, 'VWAP Reclaim'] == 'success'
    assert detail.loc[0, 'Close < BE'] == 'Yes'


def _trigger_comparison_history() -> dict[str, pd.DataFrame]:
    base = pd.DataFrame([
        {
            'Ticker': 'A',
            'Current Status': 'Active',
            'Trigger': '1m ORH',
            'Trigger Day': 'Success',
            '1m ORH': 'success',
            '5m ORH': '-',
            'VWAP Trigger': '',
            'PDH': 'Gap',
            'current_pct_raw': 0.04,
            'max_pct_raw': 0.10,
        },
        {
            'Ticker': 'B',
            'Current Status': 'Failed D1',
            'Trigger': '5m ORH',
            'Trigger Day': 'Success',
            '1m ORH': 'failed',
            '5m ORH': 'success',
            'VWAP Trigger': 'success',
            'PDH': '-',
            'current_pct_raw': 0.02,
            'max_pct_raw': 0.08,
        },
        {
            'Ticker': 'C',
            'Current Status': 'Active',
            'Trigger': 'PDH',
            'Trigger Day': 'Success',
            '1m ORH': '-',
            '5m ORH': 'failed',
            'VWAP Trigger': '',
            'PDH': 'success',
            'current_pct_raw': 0.01,
            'max_pct_raw': 0.05,
        },
        {
            'Ticker': 'D',
            'Current Status': 'â€”',
            'Trigger': 'No Trigger',
            'Trigger Day': 'Unresolved',
            '1m ORH': '',
            '5m ORH': '',
            'VWAP Trigger': '',
            'PDH': '-',
            'current_pct_raw': None,
            'max_pct_raw': None,
        },
    ])
    return {
        'Last 5 Setup Dates': base.iloc[:2].copy(),
        'Last 10 Setup Dates': base.copy(),
        'Last 20 Setup Dates': base.iloc[[3]].copy(),
    }


def test_trigger_outcome_comparison_rows_and_denominators():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())

    assert comparison.columns.tolist() == TRIGGER_COMPARISON_COLUMNS
    assert comparison[['Trigger', 'Window']].values.tolist() == [
        ['1m ORH', 'Last 5 Setup Dates'],
        ['1m ORH', 'Last 10 Setup Dates'],
        ['1m ORH', 'Last 20 Setup Dates'],
        ['5m ORH', 'Last 5 Setup Dates'],
        ['5m ORH', 'Last 10 Setup Dates'],
        ['5m ORH', 'Last 20 Setup Dates'],
        ['VWAP Reclaim', 'Last 5 Setup Dates'],
        ['VWAP Reclaim', 'Last 10 Setup Dates'],
        ['VWAP Reclaim', 'Last 20 Setup Dates'],
        ['PDH', 'Last 5 Setup Dates'],
        ['PDH', 'Last 10 Setup Dates'],
        ['PDH', 'Last 20 Setup Dates'],
        ['Alt Required', 'Last 5 Setup Dates'],
        ['Alt Required', 'Last 10 Setup Dates'],
        ['Alt Required', 'Last 20 Setup Dates'],
    ]

    one_last_10 = comparison[(comparison['Trigger'] == '1m ORH') & (comparison['Window'] == 'Last 10 Setup Dates')].iloc[0]
    assert one_last_10['Setups'] == 4
    assert one_last_10['Eligible'] == 4
    assert one_last_10['Ineligible'] == 0
    assert one_last_10['Triggered'] == 2
    assert one_last_10['Trigger Rate'] == '50%'
    assert one_last_10['Success'] == 1
    assert one_last_10['Success %'] == '50%'
    assert one_last_10['Failed'] == 1
    assert one_last_10['Fail %'] == '50%'


def test_trigger_outcome_by_window_tables_drop_window_column_and_group_triggers():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())
    by_window = trigger_outcome_by_window_tables(comparison)

    assert list(by_window) == ['Last 5 Setup Dates', 'Last 10 Setup Dates', 'Last 20 Setup Dates']
    last_10 = by_window['Last 10 Setup Dates']
    assert last_10.columns.tolist() == TRIGGER_COMPARISON_BY_WINDOW_COLUMNS
    assert 'Window' not in last_10.columns
    assert last_10['Trigger'].tolist() == ['1m ORH', '5m ORH', 'VWAP Reclaim', 'PDH', 'Alt Required']
    assert all(table['Trigger'].tolist() == ['1m ORH', '5m ORH', 'VWAP Reclaim', 'PDH', 'Alt Required'] for table in by_window.values())
    assert 'Eligible' in last_10.columns
    assert 'Ineligible' in last_10.columns
    assert last_10.loc[0, 'Triggered'] == 2
    assert last_10.loc[1, 'Triggered'] == 2
    assert last_10.loc[2, 'Triggered'] == 1
    assert last_10.loc[3, 'Triggered'] == 1
    assert last_10.loc[4, 'Triggered'] == 0


def test_trigger_event_main_tables_use_compact_count_percent_columns():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())
    main = trigger_event_main_tables(comparison)
    last_10 = main['Last 10 Setup Dates']

    assert last_10.columns.tolist() == TRIGGER_EVENT_MAIN_COLUMNS
    assert last_10['Trigger'].tolist() == ['1m ORH', '5m ORH', 'VWAP Reclaim', 'PDH', 'Alt Required']
    assert last_10.loc[0, 'Eligible'] == 4
    assert last_10.loc[0, 'Triggered'] == '2 (50%)'
    assert last_10.loc[0, 'Failed'] == '1 (50%)'
    assert last_10.loc[0, 'Success'] == '1 (50%)'
    assert last_10.loc[0, 'Currently Active'] == '1 (100%)'
    assert last_10.loc[0, 'Later Failed'] == '0 (0%)'
    assert last_10.loc[0, 'Median Max'] == '10.0%'
    assert 'Median Current' not in last_10.columns
    assert 'Ineligible' not in last_10.columns
    assert 'Active %' not in last_10.columns
    assert 'Later Failed %' not in last_10.columns


def test_trigger_outcome_internal_table_includes_alt_required_event_rows():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())

    assert comparison.columns.tolist() == TRIGGER_COMPARISON_COLUMNS
    assert comparison[['Trigger', 'Window']].values.tolist() == [
        ['1m ORH', 'Last 5 Setup Dates'],
        ['1m ORH', 'Last 10 Setup Dates'],
        ['1m ORH', 'Last 20 Setup Dates'],
        ['5m ORH', 'Last 5 Setup Dates'],
        ['5m ORH', 'Last 10 Setup Dates'],
        ['5m ORH', 'Last 20 Setup Dates'],
        ['VWAP Reclaim', 'Last 5 Setup Dates'],
        ['VWAP Reclaim', 'Last 10 Setup Dates'],
        ['VWAP Reclaim', 'Last 20 Setup Dates'],
        ['PDH', 'Last 5 Setup Dates'],
        ['PDH', 'Last 10 Setup Dates'],
        ['PDH', 'Last 20 Setup Dates'],
        ['Alt Required', 'Last 5 Setup Dates'],
        ['Alt Required', 'Last 10 Setup Dates'],
        ['Alt Required', 'Last 20 Setup Dates'],
    ]


def test_trigger_outcome_comparison_later_failed_active_and_medians():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())

    five_last_10 = comparison[(comparison['Trigger'] == '5m ORH') & (comparison['Window'] == 'Last 10 Setup Dates')].iloc[0]
    assert five_last_10['Triggered'] == 2
    assert five_last_10['Success'] == 1
    assert five_last_10['Later Failed Count'] == 1
    assert five_last_10['Later Failed %'] == '100%'
    assert five_last_10['Active Count'] == 0
    assert five_last_10['Active %'] == '0%'
    assert five_last_10['Median Current'] == '1.5%'
    assert five_last_10['Median Max'] == '8.0%'


def test_trigger_outcome_follow_through_uses_successful_trigger_rows_only():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())

    one_last_10 = comparison[(comparison['Trigger'] == '1m ORH') & (comparison['Window'] == 'Last 10 Setup Dates')].iloc[0]
    assert one_last_10['Triggered'] == 2
    assert one_last_10['Trigger Rate'] == '50%'
    assert one_last_10['Failed'] == 1
    assert one_last_10['Fail %'] == '50%'
    assert one_last_10['Success'] == 1
    assert one_last_10['Success %'] == '50%'
    assert one_last_10['Active Count'] == 1
    assert one_last_10['Active %'] == '100%'
    assert one_last_10['Later Failed Count'] == 0
    assert one_last_10['Later Failed %'] == '0%'
    assert one_last_10['Median Max'] == '10.0%'


def test_trigger_outcome_includes_qualified_vwap_trigger_rows():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())

    vwap_last_10 = comparison[(comparison['Trigger'] == 'VWAP Reclaim') & (comparison['Window'] == 'Last 10 Setup Dates')].iloc[0]
    assert vwap_last_10['Setups'] == 4
    assert vwap_last_10['Eligible'] == 4
    assert vwap_last_10['Triggered'] == 1
    assert vwap_last_10['Trigger Rate'] == '25%'
    assert vwap_last_10['Success'] == 1
    assert vwap_last_10['Success %'] == '100%'
    assert vwap_last_10['Failed'] == 0
    assert vwap_last_10['Fail %'] == '0%'
    assert vwap_last_10['Later Failed Count'] == 1
    assert vwap_last_10['Later Failed %'] == '100%'
    assert vwap_last_10['Median Max'] == '8.0%'


def test_trigger_outcome_pdh_gap_is_ineligible_for_trigger_rate():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())

    pdh_last_10 = comparison[(comparison['Trigger'] == 'PDH') & (comparison['Window'] == 'Last 10 Setup Dates')].iloc[0]
    assert pdh_last_10['Setups'] == 4
    assert pdh_last_10['Eligible'] == 3
    assert pdh_last_10['Ineligible'] == 1
    assert pdh_last_10['Triggered'] == 1
    assert pdh_last_10['Trigger Rate'] == '33%'
    assert pdh_last_10['Success'] == 1
    assert pdh_last_10['Success %'] == '100%'
    assert pdh_last_10['Failed'] == 0
    assert pdh_last_10['Fail %'] == '0%'


def test_trigger_outcome_alt_required_derives_event_result_and_denominator():
    history = {
        'Last 5 Setup Dates': pd.DataFrame([
            {
                'Ticker': 'ALT',
                'Current Status': 'Active',
                'Trigger': 'Alt Required',
                'Trigger Day': 'Success',
                '1m ORH': 'failed',
                '5m ORH': 'failed',
                'VWAP Trigger': '',
                'PDH': '-',
                'current_pct_raw': 0.03,
                'max_pct_raw': 0.07,
            },
            {
                'Ticker': 'ORH',
                'Current Status': 'Active',
                'Trigger': '1m ORH',
                'Trigger Day': 'Success',
                '1m ORH': 'success',
                '5m ORH': '-',
                'VWAP Trigger': '',
                'PDH': 'Gap',
                'current_pct_raw': 0.05,
                'max_pct_raw': 0.10,
            },
            {
                'Ticker': 'MISS',
                'Current Status': 'â€”',
                'Trigger': 'No Trigger',
                'Trigger Day': 'Unresolved',
                '1m ORH': '',
                '5m ORH': '',
                'VWAP Trigger': '',
                'PDH': '-',
                'current_pct_raw': None,
                'max_pct_raw': None,
            },
        ])
    }
    comparison = trigger_outcome_comparison(history)

    alt = comparison[(comparison['Trigger'] == 'Alt Required') & (comparison['Window'] == 'Last 5 Setup Dates')].iloc[0]
    assert alt['Setups'] == 3
    assert alt['Eligible'] == 2
    assert alt['Ineligible'] == 1
    assert alt['Triggered'] == 1
    assert alt['Trigger Rate'] == '50%'
    assert alt['Success'] == 1
    assert alt['Success %'] == '100%'
    assert alt['Failed'] == 0
    assert alt['Fail %'] == '0%'
    assert alt['Median Current'] == '3.0%'
    assert alt['Median Max'] == '7.0%'


def test_vwap_success_prevents_fallback_alt_required_event_count():
    history = {
        'Last 5 Setup Dates': pd.DataFrame([
            {
                'Ticker': 'VWAP',
                'Current Status': 'Active',
                'Trigger': 'No Trigger',
                'Trigger Day': 'Success',
                '1m ORH': 'failed',
                '5m ORH': 'failed',
                'VWAP Trigger': 'success',
                'PDH': '-',
                'current_pct_raw': 0.04,
                'max_pct_raw': 0.11,
            },
            {
                'Ticker': 'ALT',
                'Current Status': 'Active',
                'Trigger': 'Alt Required',
                'Trigger Day': 'Success',
                '1m ORH': 'failed',
                '5m ORH': 'failed',
                'VWAP Trigger': '',
                'PDH': '-',
                'current_pct_raw': 0.03,
                'max_pct_raw': 0.07,
            },
        ])
    }

    comparison = trigger_outcome_comparison(history)

    vwap = comparison[(comparison['Trigger'] == 'VWAP Reclaim') & (comparison['Window'] == 'Last 5 Setup Dates')].iloc[0]
    alt = comparison[(comparison['Trigger'] == 'Alt Required') & (comparison['Window'] == 'Last 5 Setup Dates')].iloc[0]
    assert vwap['Success'] == 1
    assert alt['Eligible'] == 1
    assert alt['Triggered'] == 1
    assert alt['Success'] == 1


def test_superseded_orh_is_not_counted_as_successful_trigger():
    rows = pd.DataFrame([{
        'Setup Date': '2026-05-08',
        'Ticker': 'VWAP',
        'Current Status': 'Active',
        'Trigger Day': 'Success',
        'Trigger': 'VWAP Reclaim',
        '1m ORH': 'failed',
        '5m ORH': 'success',
        'VWAP Trigger': 'success',
        'vwap_qualified_trigger_reason': 'VWAP trigger price lower than 5m ORH',
        'PDH': '-',
        'Notes': '',
        'Retest Day': '',
        'current_pct_raw': 0.04,
        'max_pct_raw': 0.11,
    }])
    window = overview_windows(['2026-05-08'])[0]

    summary = summarize_window(rows, window)
    main = main_opening_behavior_table(rows).set_index('Trigger')
    comparison = trigger_outcome_comparison({'Last 5 Setup Dates': rows})

    assert summary['Clean 5m'] == '0 (0%)'
    assert summary['VWAP Reclaim'] == '1 (100%)'
    assert main.loc['5m ORH', 'Count'] == 0
    assert main.loc['VWAP Reclaim', 'Count'] == 1
    assert comparison[(comparison['Trigger'] == '5m ORH') & (comparison['Window'] == 'Last 5 Setup Dates')].iloc[0]['Success'] == 0
    assert comparison[(comparison['Trigger'] == 'VWAP Reclaim') & (comparison['Window'] == 'Last 5 Setup Dates')].iloc[0]['Success'] == 1


def test_trigger_outcome_comparison_zero_trigger_display():
    comparison = trigger_outcome_comparison(_trigger_comparison_history())

    pdh_last_5 = comparison[(comparison['Trigger'] == 'PDH') & (comparison['Window'] == 'Last 5 Setup Dates')].iloc[0]
    assert pdh_last_5['Setups'] == 2
    assert pdh_last_5['Eligible'] == 1
    assert pdh_last_5['Ineligible'] == 1
    assert pdh_last_5['Triggered'] == 0
    assert pdh_last_5['Trigger Rate'] == '0%'
    assert pdh_last_5['Success %'] == '-'
    assert pdh_last_5['Fail %'] == '-'
    assert pdh_last_5['Later Failed %'] == '-'
    assert pdh_last_5['Active %'] == '-'
    assert pdh_last_5['Median Current'] == '-'
    assert pdh_last_5['Median Max'] == '-'


def test_trigger_outcome_zero_success_display_uses_dashes_for_follow_through():
    comparison = trigger_outcome_comparison({
        'Last 5 Setup Dates': pd.DataFrame([{
            'Ticker': 'FAIL',
            'Current Status': 'Active',
            'Trigger': '5m ORH',
            'Trigger Day': 'Success',
            '1m ORH': 'failed',
            '5m ORH': 'success',
            'VWAP Trigger': '',
            'PDH': '-',
            'current_pct_raw': 0.03,
            'max_pct_raw': 0.09,
        }])
    })

    one = comparison[(comparison['Trigger'] == '1m ORH') & (comparison['Window'] == 'Last 5 Setup Dates')].iloc[0]
    assert one['Triggered'] == 1
    assert one['Failed'] == 1
    assert one['Fail %'] == '100%'
    assert one['Success'] == 0
    assert one['Success %'] == '0%'
    assert one['Active Count'] == 0
    assert one['Active %'] == '-'
    assert one['Later Failed Count'] == 0
    assert one['Later Failed %'] == '-'
    assert one['Median Max'] == '-'


def test_trigger_outcome_eligible_zero_display():
    comparison = trigger_outcome_comparison({
        'Last 5 Setup Dates': pd.DataFrame([
            {'Ticker': 'A', 'Current Status': 'Active', 'PDH': 'Gap', 'current_pct_raw': 0.01, 'max_pct_raw': 0.02},
            {'Ticker': 'B', 'Current Status': 'Active', 'PDH': 'N/A', 'current_pct_raw': 0.03, 'max_pct_raw': 0.04},
        ])
    })

    pdh = comparison[(comparison['Trigger'] == 'PDH') & (comparison['Window'] == 'Last 5 Setup Dates')].iloc[0]
    assert pdh['Setups'] == 2
    assert pdh['Eligible'] == 0
    assert pdh['Ineligible'] == 2
    assert pdh['Triggered'] == 0
    assert pdh['Trigger Rate'] == '-'
    assert pdh['Success %'] == '-'
    assert pdh['Fail %'] == '-'


def test_trigger_event_outcomes_are_separate_from_primary_trigger_grouping():
    rows = _trigger_comparison_history()['Last 10 Setup Dates'].copy()
    rows['Trigger'] = ['1m ORH', '5m ORH', 'PDH', 'No Trigger']
    rows['Trigger Day'] = ['Success', 'Success', 'Success', 'Unresolved']
    event = trigger_outcome_comparison({'Last 10 Setup Dates': rows})
    primary = trigger_quality_table(rows)

    assert event[(event['Trigger'] == '1m ORH') & (event['Window'] == 'Last 10 Setup Dates')].iloc[0]['Triggered'] == 2
    assert primary[primary['Trigger'] == '1m ORH'].iloc[0]['Count'] == 1


def test_filter_detail_rows_by_trigger_level_and_result():
    detail = detail_rows(_history(), overview_windows(['2026-04-28', '2026-05-02', '2026-05-08'])[0])

    one_success = filter_detail_rows(detail, trigger_level='1m ORH', trigger_result='success')
    five_success = filter_detail_rows(detail, trigger_level='5m ORH', trigger_result='success')
    assert five_success['Ticker'].tolist() == ['AAA', 'BBB']
    assert one_success['Ticker'].tolist() == ['AAA']

    pdh_blank = filter_detail_rows(detail, trigger_level='PDH', trigger_result='blank')
    assert pdh_blank['Ticker'].tolist() == ['AAA', 'EEE', 'BBB', 'CCC']

    vwap_success = filter_detail_rows(detail.assign(**{'VWAP Reclaim': ['success', '', '', '']}), trigger_level='VWAP Reclaim', trigger_result='success')
    assert vwap_success['Ticker'].tolist() == ['AAA']


def test_filter_detail_rows_by_ineligible_gap_result():
    detail = pd.DataFrame([
        {'Ticker': 'A', 'PDH': 'Gap', '1m ORH': 'success', '5m ORH': '-'},
        {'Ticker': 'B', 'PDH': 'success', '1m ORH': '-', '5m ORH': '-'},
    ])

    gap = filter_detail_rows(detail, trigger_level='PDH', trigger_result='Gap')

    assert gap['Ticker'].tolist() == ['A']


def test_filter_detail_rows_by_alt_required_event():
    detail = pd.DataFrame([
        {'Ticker': 'ALT', 'Current Status': 'Active', 'Trigger': 'Alt Required', 'Trigger Day': 'Success', 'PDH': '-', '1m ORH': 'failed', '5m ORH': 'failed'},
        {'Ticker': 'ONE', 'Current Status': 'Active', 'Trigger': '1m ORH', 'Trigger Day': 'Success', 'PDH': 'Gap', '1m ORH': 'success', '5m ORH': '-'},
        {'Ticker': 'MISS', 'Current Status': 'â€”', 'Trigger': 'No Trigger', 'Trigger Day': 'Unresolved', 'PDH': '-', '1m ORH': '', '5m ORH': ''},
    ])

    alt_success = filter_detail_rows(detail, trigger_level='Alt Required', trigger_result='success')
    alt_blank = filter_detail_rows(detail, trigger_level='Alt Required', trigger_result='blank')

    assert alt_success['Ticker'].tolist() == ['ALT']
    assert alt_blank['Ticker'].tolist() == ['MISS']


def test_filter_detail_rows_combines_trigger_and_current_status_filters():
    detail = detail_rows(_history(), overview_windows(['2026-04-28', '2026-05-02', '2026-05-08'])[0])

    failed_later = filter_detail_rows(detail, trigger_level='5m ORH', trigger_result='success', current_status='Later Failed')

    assert failed_later['Ticker'].tolist() == ['BBB']


def test_filter_detail_rows_by_current_status_bucket():
    detail = detail_rows(_history(), overview_windows(['2026-04-10', '2026-04-28', '2026-05-02', '2026-05-08'])[0])

    active = filter_detail_rows(detail, current_status='Active')
    later_failed = filter_detail_rows(detail, current_status='Later Failed')
    unresolved = filter_detail_rows(detail, current_status='Unresolved')

    assert active['Ticker'].tolist() == ['AAA']
    assert later_failed['Ticker'].tolist() == ['EEE', 'BBB']
    assert unresolved['Ticker'].tolist() == ['DDD']


def test_filter_detail_rows_by_opening_path_group():
    detail = pd.DataFrame([
        {'Ticker': 'A', 'Current Status': 'Active', 'Trigger Day': 'Success', 'Trigger': '1m ORH', 'PDH': 'Gap', '1m ORH': 'success', '5m ORH': '-'},
        {'Ticker': 'B', 'Current Status': 'Active', 'Trigger Day': 'Success', 'Trigger': '5m ORH', 'PDH': 'Gap', '1m ORH': 'failed', '5m ORH': 'success'},
        {'Ticker': 'C', 'Current Status': '—', 'Trigger Day': 'Fail', 'Trigger': 'Failed OR Trigger', 'PDH': '-', '1m ORH': 'failed', '5m ORH': 'failed'},
    ])

    reclaimed = filter_detail_rows(detail, opening_path_group='1m ORH Failed, Later Reclaimed')
    failed_all = filter_detail_rows(detail, opening_path_group='Failed All Opening Triggers')

    assert reclaimed['Ticker'].tolist() == ['B']
    assert failed_all['Ticker'].tolist() == ['C']


def _opening_behavior_history() -> pd.DataFrame:
    return pd.DataFrame([
        {
            'Ticker': 'CLN',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': '1m ORH',
            'PDH': 'Gap',
            '1m ORH': 'success',
            '5m ORH': '-',
            'current_pct_raw': 0.04,
            'max_pct_raw': 0.10,
        },
        {
            'Ticker': 'REC',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': '5m ORH',
            'PDH': 'Gap',
            '1m ORH': 'failed',
            '5m ORH': 'success',
            'current_pct_raw': 0.03,
            'max_pct_raw': 0.08,
        },
        {
            'Ticker': 'NRV',
            'Current Status': 'â€”',
            'Trigger Day': 'Fail',
            'Trigger': 'Failed OR Trigger',
            'PDH': '-',
            '1m ORH': 'failed',
            '5m ORH': 'failed',
            'current_pct_raw': -0.02,
            'max_pct_raw': 0.01,
        },
        {
            'Ticker': 'PDH',
            'Current Status': 'Failed D1',
            'Trigger Day': 'Success',
            'Trigger': 'PDH',
            'PDH': 'success',
            '1m ORH': 'failed',
            '5m ORH': '-',
            'current_pct_raw': 0.01,
            'max_pct_raw': 0.05,
        },
        {
            'Ticker': 'ALL',
            'Current Status': 'â€”',
            'Trigger Day': 'Fail',
            'Trigger': 'Failed PDH Trigger',
            'PDH': 'failed',
            '1m ORH': 'failed',
            '5m ORH': '-',
            'current_pct_raw': -0.03,
            'max_pct_raw': 0.00,
        },
    ])


def test_opening_behavior_classifies_clean_1m_success():
    table = opening_behavior_table(_opening_behavior_history()).set_index('Path')

    assert table.loc['Clean 1m ORH Success', 'Count'] == 1
    assert table.loc['Clean 1m ORH Success', '% of Setups'] == '20%'
    assert table.loc['Clean 1m ORH Success', 'Active %'] == '100%'
    assert table.loc['Clean 1m ORH Success', 'Median Max'] == '10.0%'


def test_opening_behavior_classifies_failed_1m_later_reclaimed():
    table = opening_behavior_table(_opening_behavior_history()).set_index('Path')

    assert table.loc['1m ORH Failed, Later Reclaimed', 'Count'] == 2
    assert table.loc['1m ORH Failed, Later Reclaimed', '% of Setups'] == '40%'
    assert table.loc['1m ORH Failed, Later Reclaimed', 'Active %'] == '50%'
    assert table.loc['1m ORH Failed, Later Reclaimed', 'Later Failed %'] == '50%'


def test_opening_behavior_classifies_failed_1m_never_recovered():
    table = opening_behavior_table(_opening_behavior_history()).set_index('Path')

    assert table.loc['1m ORH Failed, Never Recovered', 'Count'] == 2
    assert table.loc['1m ORH Failed, Never Recovered', '% of Setups'] == '40%'


def test_opening_behavior_classifies_5m_success_after_1m_failure():
    table = opening_behavior_table(_opening_behavior_history()).set_index('Path')

    assert table.loc['5m ORH Success After 1m Failure', 'Count'] == 1
    assert table.loc['5m ORH Success After 1m Failure', 'Median Current'] == '3.0%'


def test_opening_behavior_classifies_pdh_success_after_early_noise():
    table = opening_behavior_table(_opening_behavior_history()).set_index('Path')

    assert table.loc['PDH Success After Early Noise', 'Count'] == 1
    assert table.loc['PDH Success After Early Noise', 'Later Failed %'] == '100%'


def test_opening_behavior_classifies_failed_all_opening_triggers():
    table = opening_behavior_table(_opening_behavior_history()).set_index('Path')

    assert table.loc['Failed All Opening Triggers', 'Count'] == 2
    assert table.loc['Failed All Opening Triggers', '% of Setups'] == '40%'
    assert table.loc['Failed All Opening Triggers', 'Active %'] == '0%'


def test_opening_behavior_main_table_shows_successful_trigger_rows_only():
    history = pd.concat([
        _opening_behavior_history(),
        pd.DataFrame([{
            'Ticker': 'ALT',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': 'Alt Required',
            'PDH': '-',
            '1m ORH': 'failed',
            '5m ORH': 'failed',
            'current_pct_raw': 0.02,
            'max_pct_raw': 0.07,
        }]),
    ], ignore_index=True)
    main = main_opening_behavior_table(history)

    assert main.columns.tolist() == OPENING_BEHAVIOR_MAIN_COLUMNS
    assert main['Trigger'].tolist() == MAIN_OPENING_TRIGGERS
    assert 'Clean 1m ORH Success' not in main['Trigger'].tolist()
    assert '1m ORH Failed, Later Reclaimed' not in main['Trigger'].tolist()
    assert '5m ORH Success After 1m Failure' not in main['Trigger'].tolist()
    assert 'PDH Success After Early Noise' not in main['Trigger'].tolist()
    assert 'Failed All Opening Triggers' not in main['Trigger'].tolist()
    by_trigger = main.set_index('Trigger')
    assert by_trigger.loc['1m ORH', 'Count'] == 1
    assert by_trigger.loc['1m ORH', '% of Setups'] == '17%'
    assert by_trigger.loc['1m ORH', 'Currently Active'] == '1 (100%)'
    assert by_trigger.loc['1m ORH', 'Later Failed'] == '0 (0%)'
    assert by_trigger.loc['1m ORH', 'Median Max'] == '10.0%'
    assert by_trigger.loc['5m ORH', 'Count'] == 1
    assert by_trigger.loc['PDH', 'Count'] == 1
    assert by_trigger.loc['Alt Required', 'Count'] == 1
    assert by_trigger.loc['Alt Required', 'Median Max'] == '7.0%'
    assert 'Median Current' not in main.columns


def test_opening_behavior_main_table_zero_count_display():
    history = pd.DataFrame([{
        'Ticker': 'NONE',
        'Current Status': '—',
        'Trigger Day': 'Unresolved',
        'Trigger': 'No Trigger',
        'PDH': '-',
        '1m ORH': '-',
        '5m ORH': '-',
        'max_pct_raw': None,
    }])

    main = main_opening_behavior_table(history).set_index('Trigger')

    assert main.loc['1m ORH', 'Count'] == 0
    assert main.loc['1m ORH', '% of Setups'] == '0%'
    assert main.loc['1m ORH', 'Currently Active'] == '-'
    assert main.loc['1m ORH', 'Later Failed'] == '-'
    assert main.loc['1m ORH', 'Median Max'] == '-'


def test_opening_behavior_main_table_includes_vwap_reclaim_success_row():
    history = pd.DataFrame([{
        'Ticker': 'VWAP',
        'Current Status': 'Failed D1',
        'Trigger Day': 'Success',
        'Trigger': 'No Trigger',
        'PDH': '-',
        '1m ORH': 'failed',
        '5m ORH': 'failed',
        'VWAP Trigger': 'success',
        'max_pct_raw': 0.12,
    }])

    main = main_opening_behavior_table(history).set_index('Trigger')

    assert main.loc['VWAP Reclaim', 'Count'] == 1
    assert main.loc['VWAP Reclaim', '% of Setups'] == '100%'
    assert main.loc['VWAP Reclaim', 'Currently Active'] == '0 (0%)'
    assert main.loc['VWAP Reclaim', 'Later Failed'] == '1 (100%)'
    assert main.loc['VWAP Reclaim', 'Median Max'] == '12.0%'


def test_setup_behavior_page_uses_successful_triggers_section_title():
    page = open('pages/5_Setup_Behavior_Overview.py', encoding='utf-8').read()

    assert "st.subheader('Selected Window Successful Triggers')" in page
    assert "st.subheader('Selected Window Opening Path')" not in page
    assert "'VWAP Reclaim'" in page


def test_opening_behavior_detail_retains_richer_path_rows():
    table = opening_behavior_table(_opening_behavior_history())

    assert 'Clean 1m ORH Success' in table['Path'].tolist()
    assert '1m ORH Failed, Later Reclaimed' in table['Path'].tolist()
    assert '5m ORH Success After 1m Failure' in table['Path'].tolist()
    assert 'PDH Success After Early Noise' in table['Path'].tolist()
    assert 'Failed All Opening Triggers' in table['Path'].tolist()


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
    assert out['snapshot_cards'] == {}
    assert out['opening_behavior'] == {}
    assert out['opening_behavior_main'] == {}
    assert out['trigger_outcome_comparison'].columns.tolist() == TRIGGER_COMPARISON_COLUMNS
    assert out['trigger_outcome_comparison'].empty
    assert out['trigger_outcome_by_window'] == {}
    assert out['trigger_event_main_by_window'] == {}
    assert out['details'] == {}
    assert out['windows'] == []
