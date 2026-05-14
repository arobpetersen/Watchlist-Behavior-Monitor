from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.setup_performance import (
    SETUP_ENTRY_TACTIC_COLUMNS,
    SETUP_SUMMARY_COLUMNS,
    build_setup_entry_tactic_summary,
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
    assert int(mu['Failed D0']) == 1
    assert int(mu['Failed After D0']) == 1
    assert int(mu['Total Failed']) == 2
    assert mu['Failure %'] == '66.7%'
    assert mu['Failed D0 %'] == '33.3%'
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
    assert reclaim['Failed D0 %'] == '50.0%'
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

    assert cards.loc['Highest Failure Setup', 'Value'] == 'Reliable'
    assert cards.loc['Best Median Max % Setup', 'Value'] == 'Reliable'


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
    page = Path(__file__).resolve().parents[1] / 'pages' / '7_Setup_Performance.py'
    source = page.read_text()

    assert "history_cache_token = f'{MONITOR_HISTORY_CACHE_VERSION}:{data_health_cache_token(db_path)}'" in source
    assert 'SETUP_PERFORMANCE_CACHE_VERSION' not in source
    assert 'refresh_derived_watchlist_views(load_cached_monitor_history)' not in source
