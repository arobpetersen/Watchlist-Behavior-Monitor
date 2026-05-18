from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.setup_performance import (
    SETUP_ENTRY_TACTIC_COLUMNS,
    SETUP_FAILURE_TREND_COLUMNS,
    SETUP_SUMMARY_COLUMNS,
    build_setup_entry_tactic_summary,
    build_setup_failure_trend,
    build_setup_summary,
    filter_setup_performance_rows,
    setup_performance_cards,
)


def _rows() -> pd.DataFrame:
    return pd.DataFrame([
        {
            'Setup Date': '2026-05-01',
            'Setup': 'MU',
            'Entry Tactic': 'Reclaim',
            'Current Status': 'Active',
            'Close < BE': 'No',
            'Retests': 'D0, D2',
            'current_pct_raw': 0.10,
            'max_pct_raw': 0.30,
            'd3_high_pct_raw': 0.20,
            'Rating': '5',
        },
        {
            'Setup Date': '2026-05-02',
            'Setup': 'MU',
            'Entry Tactic': 'Reclaim',
            'Current Status': 'Failed D0',
            'Close < BE': 'Yes',
            'Retests': '',
            'current_pct_raw': -0.02,
            'max_pct_raw': 0.04,
            'd3_high_pct_raw': None,
            'Rating': '',
        },
        {
            'Setup Date': '2026-05-03',
            'Setup': 'MU',
            'Entry Tactic': 'Opening Drive',
            'Current Status': 'Failed D2',
            'Trigger Day': 'Success',
            'Close < BE': 'true',
            'Retests': 'D1',
            'current_pct_raw': 0.03,
            'max_pct_raw': 0.12,
            'd3_high_pct_raw': 0.09,
            'Rating': None,
        },
        {
            'Setup Date': '2026-05-04',
            'Setup': '',
            'Entry Tactic': '',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Close < BE': 'No',
            'Retests': 'D10',
            'current_pct_raw': 0.01,
            'max_pct_raw': 0.05,
            'd3_high_pct_raw': 0.06,
            'Rating': '4',
        },
        {
            'Setup Date': '2026-05-05',
            'Setup': None,
            'Entry Tactic': None,
            'Current Status': 'Failed D1',
            'Trigger Day': 'Success',
            'Close < BE': 'Yes',
            'Retests': 'D0',
            'current_pct_raw': 0.00,
            'max_pct_raw': 0.02,
            'd3_high_pct_raw': 0.03,
            'Rating': '3',
        },
    ])


def test_setup_summary_groups_blank_setup_status_counts_percentages_and_follow_through_metrics():
    summary = build_setup_summary(_rows()).set_index('Setup')

    mu = summary.loc['MU']
    assert int(mu['Count']) == 3
    assert int(mu['Active']) == 1
    assert int(mu['D0 Fail']) == 1
    assert int(mu['Failed After D0']) == 1
    assert int(mu['Total Failed']) == 2
    assert mu['Failure %'] == '66.7%'
    assert mu['D0 Fail %'] == '33.3%'
    assert mu['Failed After D0 %'] == '33.3%'
    assert int(mu['Close < BE']) == 2
    assert mu['Close < BE %'] == '66.7%'
    assert int(mu['Retested D0']) == 1
    assert int(mu['Retested After D0']) == 2
    assert mu['Median Current %'] == '3.0%'
    assert mu['Median Max %'] == '12.0%'
    assert mu['Median D3 High %'] == '14.5%'
    assert mu['Avg Max %'] == '15.3%'
    assert mu['Rating Avg'] == '5.00'
    assert int(mu['Rating 4-5 Count']) == 1
    assert mu['Latest Setup Date'] == '2026-05-03'

    unclassified = summary.loc['Unclassified']
    assert int(unclassified['Count']) == 2
    assert int(unclassified['Active']) == 1
    assert int(unclassified['Failed After D0']) == 1
    assert unclassified['Failure %'] == '50.0%'


def test_setup_summary_counts_trigger_day_fail_as_d0_fail_once():
    rows = pd.DataFrame([
        {'Setup': 'A', 'Current Status': '-', 'Trigger Day': 'Fail'},
        {'Setup': 'A', 'Current Status': 'Failed D0', 'Trigger Day': 'Success'},
        {'Setup': 'A', 'Current Status': 'Failed D0', 'Trigger Day': 'Fail'},
        {'Setup': 'A', 'Current Status': 'Failed D2', 'Trigger Day': 'Success'},
    ])

    summary = build_setup_summary(rows).set_index('Setup')

    assert int(summary.loc['A', 'D0 Fail']) == 3
    assert int(summary.loc['A', 'Failed After D0']) == 1
    assert int(summary.loc['A', 'Total Failed']) == 4


def test_sample_labels_cover_small_developing_and_useful_samples():
    rows = pd.concat([
        pd.DataFrame({'Setup': ['Small'] * 4, 'Current Status': ['Active'] * 4}),
        pd.DataFrame({'Setup': ['Developing'] * 5, 'Current Status': ['Active'] * 5}),
        pd.DataFrame({'Setup': ['Useful'] * 15, 'Current Status': ['Active'] * 15}),
    ], ignore_index=True)

    summary = build_setup_summary(rows).set_index('Setup')

    assert summary.loc['Small', 'Sample'] == 'Small sample'
    assert summary.loc['Developing', 'Sample'] == 'Developing'
    assert summary.loc['Useful', 'Sample'] == 'Useful sample'


def test_setup_entry_tactic_aggregation_uses_setup_and_tactic_groups():
    table = build_setup_entry_tactic_summary(_rows())
    reclaim = table[(table['Setup'] == 'MU') & (table['Entry Tactic'] == 'Reclaim')].iloc[0]

    assert list(table.columns) == SETUP_ENTRY_TACTIC_COLUMNS
    assert int(reclaim['Count']) == 2
    assert reclaim['Failure %'] == '50.0%'
    assert reclaim['D0 Fail %'] == '50.0%'
    assert reclaim['Active %'] == '50.0%'
    assert reclaim['Median Max %'] == '17.0%'
    assert reclaim['Median Current %'] == '4.0%'
    assert reclaim['Close < BE %'] == '50.0%'


def test_filters_apply_setup_date_rating_and_current_status():
    rows = _rows()

    filtered = filter_setup_performance_rows(
        rows,
        setup_date_window='Last 2 setup dates',
        rating_filter='3+ only',
        current_status_filter='Failed only',
    )

    assert filtered['Setup Date'].tolist() == ['2026-05-05']
    assert filtered['Setup'].tolist() == ['Unclassified']


def test_cards_sample_gate_extreme_setup_reads():
    rows = pd.concat([
        pd.DataFrame({
            'Setup Date': pd.date_range('2026-05-01', periods=5).astype(str),
            'Setup': ['Reliable'] * 5,
            'Current Status': ['Active'] * 5,
            'max_pct_raw': [0.10, 0.11, 0.12, 0.13, 0.14],
        }),
        pd.DataFrame({
            'Setup Date': ['2026-05-06'],
            'Setup': ['TinyFail'],
            'Current Status': ['Failed D0'],
            'max_pct_raw': [0.90],
        }),
    ], ignore_index=True)

    cards = setup_performance_cards(build_setup_summary(rows)).set_index('Metric')

    assert cards.loc['Highest Active Rate', 'Value'] == 'Reliable'
    assert cards.loc['Lowest Failure Setup', 'Value'] == 'Reliable'
    assert cards.loc['Highest Failure Setup', 'Value'] == 'Reliable'
    assert 'Most Common Setup' not in cards.index
    assert 'Best Median Max % Setup' not in cards.index


def test_cards_choose_best_active_lowest_and_highest_failure_with_sample_gate():
    rows = pd.concat([
        pd.DataFrame({
            'Setup': ['Reliable'] * 5,
            'Current Status': ['Active'] * 5,
            'Trigger Day': ['Success'] * 5,
        }),
        pd.DataFrame({
            'Setup': ['Mixed'] * 5,
            'Current Status': ['Active', 'Active', 'Failed D1', 'Failed D2', '-'],
            'Trigger Day': ['Success', 'Success', 'Success', 'Success', 'Fail'],
        }),
        pd.DataFrame({
            'Setup': ['TinyClean'] * 2,
            'Current Status': ['Active'] * 2,
            'Trigger Day': ['Success'] * 2,
        }),
    ], ignore_index=True)

    cards = setup_performance_cards(build_setup_summary(rows)).set_index('Metric')

    assert cards.loc['Highest Active Rate', 'Value'] == 'Reliable'
    assert cards.loc['Highest Active Rate', 'Detail'] == '5 active / 5 rows'
    assert cards.loc['Lowest Failure Setup', 'Value'] == 'Reliable'
    assert cards.loc['Lowest Failure Setup', 'Detail'] == '0 failed / 5 rows'
    assert cards.loc['Highest Failure Setup', 'Value'] == 'Mixed'
    assert cards.loc['Highest Failure Setup', 'Detail'] == '3 failed / 5 rows'


def test_setup_failure_trend_matrix_cells_and_reads():
    rows = []
    # Prior 5 dates: Improving 4/5 failed, Worsening 0/5 failed, Stable 2/5 failed.
    for idx, date in enumerate(pd.date_range('2026-05-01', periods=5).astype(str)):
        rows.extend([
            {'Setup Date': date, 'Setup': 'Improving', 'Current Status': 'Failed D1' if idx < 4 else 'Active', 'Trigger Day': 'Success'},
            {'Setup Date': date, 'Setup': 'Worsening', 'Current Status': 'Active', 'Trigger Day': 'Success'},
            {'Setup Date': date, 'Setup': 'Stable', 'Current Status': 'Failed D1' if idx < 2 else 'Active', 'Trigger Day': 'Success'},
        ])
    # Last 5 dates.
    for idx, date in enumerate(pd.date_range('2026-05-06', periods=5).astype(str)):
        rows.extend([
            {'Setup Date': date, 'Setup': 'Improving', 'Current Status': 'Failed D1' if idx == 0 else 'Active', 'Trigger Day': 'Success'},
            {'Setup Date': date, 'Setup': 'Worsening', 'Current Status': 'Failed D1' if idx < 3 else 'Active', 'Trigger Day': 'Success'},
            {'Setup Date': date, 'Setup': 'Stable', 'Current Status': 'Failed D1' if idx < 2 else 'Active', 'Trigger Day': 'Success'},
            {'Setup Date': date, 'Setup': 'Clean', 'Current Status': 'Active', 'Trigger Day': 'Success'},
        ])
    rows.extend([
        {'Setup Date': '2026-05-09', 'Setup': 'Small', 'Current Status': 'Active', 'Trigger Day': 'Success'},
        {'Setup Date': '2026-05-10', 'Setup': 'Small', 'Current Status': 'Failed D0', 'Trigger Day': 'Fail'},
        {'Setup Date': '2026-05-01', 'Setup': 'NoRecent', 'Current Status': 'Failed D1', 'Trigger Day': 'Success'},
        {'Setup Date': '2026-05-02', 'Setup': 'NoRecent', 'Current Status': 'Active', 'Trigger Day': 'Success'},
        {'Setup Date': '2026-05-10', 'Setup': '', 'Current Status': '-', 'Trigger Day': 'Fail'},
    ])

    trend = build_setup_failure_trend(pd.DataFrame(rows)).set_index('Setup')

    assert list(build_setup_failure_trend(pd.DataFrame(rows)).columns) == SETUP_FAILURE_TREND_COLUMNS
    assert trend.loc['Improving', 'Last 5'] == '80% (4/5)'
    assert trend.loc['Improving', 'Previous 5'] == '20% (1/5)'
    assert trend.loc['Improving', 'Read'] == 'Improved recent'
    assert trend.loc['Worsening', 'Read'] == 'Worse recent'
    assert trend.loc['Stable', 'Read'] == 'Stable'
    assert trend.loc['Clean', 'Read'] == 'Clean recent'
    assert trend.loc['Small', 'Read'] == 'Small sample'
    assert trend.loc['NoRecent', 'Last 5'] == '—'
    assert trend.loc['NoRecent', 'Read'] == 'No recent sample'
    assert trend.loc['Unclassified', 'Last 5'] == '0% (0/1)'


def test_setup_failure_trend_cell_format_is_success_rate_first():
    rows = []
    for idx, date in enumerate(pd.date_range('2026-05-01', periods=12).astype(str)):
        rows.append({
            'Setup Date': date,
            'Setup': 'Format',
            'Current Status': 'Failed D1' if idx < 4 else 'Active',
            'Trigger Day': 'Success',
        })
    rows.append({'Setup Date': '2026-05-12', 'Setup': 'OneRow', 'Current Status': 'Active', 'Trigger Day': 'Success'})
    for date in pd.date_range('2026-05-10', periods=3).astype(str):
        rows.append({'Setup Date': date, 'Setup': 'AllFailed', 'Current Status': 'Failed D1', 'Trigger Day': 'Success'})

    trend = build_setup_failure_trend(pd.DataFrame(rows)).set_index('Setup')

    assert trend.loc['Format', 'Last 20'] == '67% (8/12)'
    assert trend.loc['OneRow', 'Last 5'] == '100% (1/1)'
    assert trend.loc['AllFailed', 'Last 5'] == '0% (0/3)'


def test_empty_input_returns_stable_tables():
    summary = build_setup_summary(pd.DataFrame())
    tactic = build_setup_entry_tactic_summary(pd.DataFrame())
    cards = setup_performance_cards(summary)

    assert list(summary.columns) == SETUP_SUMMARY_COLUMNS
    assert list(tactic.columns) == SETUP_ENTRY_TACTIC_COLUMNS
    assert summary.empty
    assert tactic.empty
    assert cards.empty


def test_setup_performance_page_uses_shared_monitor_history_cache_token():
    page = Path(__file__).resolve().parents[1] / 'pages' / '8_Setup_Type_Performance.py'
    source = page.read_text()

    assert 'cache_token = data_health_cache_token(db_path)' in source
    assert "history_cache_token = f'{MONITOR_HISTORY_CACHE_VERSION}:{cache_token}'" in source
    assert 'SETUP_PERFORMANCE_CACHE_VERSION' not in source
    assert 'refresh_derived_watchlist_views(load_cached_monitor_history)' not in source
