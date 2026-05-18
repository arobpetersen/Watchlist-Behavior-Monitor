from __future__ import annotations

import pytest

from src.dashboard_queries import (
    DAILY_WORKFLOW_INTERNAL_COLUMNS,
    DAILY_WORKFLOW_COLUMNS,
    DAILY_TABLE_COLUMNS,
    GROUP_SUMMARY_COLUMNS,
    ROLLING_COLUMNS,
    TICKER_DETAIL_COLUMNS,
    _clean_display_value,
    _close_bucket,
    _format_num,
    _format_pct,
    _or_result,
    _rating_bucket,
    _vwap_result,
    daily_snapshot_monitor_table,
    daily_snapshot_summary_groups,
)


@pytest.mark.parametrize(
    ('payload', 'expected'),
    [
        ('{}', 'No Break'),
        ('{"broke_orh": true, "closed_above_orh": true}', 'Held'),
        ('{"broke_orh": true, "orh_then_orl": true}', 'Failed'),
        ('{"broke_orl": true, "closed_below_orl": true}', 'Failed'),
    ],
)
def test_or_result_formatting(payload, expected):
    assert _or_result(payload) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (True, 'Above VWAP'),
        (False, 'Below VWAP'),
        (None, 'No Data'),
    ],
)
def test_vwap_result_formatting(value, expected):
    assert _vwap_result(value) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (5, '4+'),
        (3.5, '3 to <4'),
        (2.5, '2 to <3'),
        (1, '<2'),
        (None, 'No Rating'),
    ],
)
def test_rating_bucket_formatting(value, expected):
    assert _rating_bucket(value) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (0.90, 'Top 20%'),
        (0.70, 'Upper Half'),
        (0.50, 'Middle'),
        (0.30, 'Lower Half'),
        (0.10, 'Bottom 20%'),
        (None, ''),
    ],
)
def test_close_bucket_formatting(value, expected):
    assert _close_bucket(value) == expected


def test_clean_display_value_hides_missing_values():
    assert _clean_display_value(None) == ''
    assert _clean_display_value(float('nan')) == ''
    assert _clean_display_value('') == ''
    assert _clean_display_value('   ') == ''
    assert _clean_display_value('nan') == ''
    assert _clean_display_value('setup') == 'setup'


def test_numeric_formatters_treat_blank_strings_as_missing():
    assert _format_num('') == ''
    assert _format_num('   ') == ''
    assert _format_pct('') == ''
    assert _rating_bucket('') == 'No Rating'
    assert _close_bucket('') == ''


def test_display_labels_use_atr14_not_atr20():
    labels = [
        *DAILY_TABLE_COLUMNS.values(),
        *GROUP_SUMMARY_COLUMNS.values(),
        *ROLLING_COLUMNS.values(),
        *TICKER_DETAIL_COLUMNS.values(),
    ]

    assert 'ATR14' in labels
    assert 'Range x ATR(14)' in labels
    assert not any('ATR20' in label for label in labels)


def test_daily_snapshot_workflow_columns_prioritize_monitor_fields():
    assert DAILY_WORKFLOW_COLUMNS == [
        'Ticker',
        'Current Status',
        'Trigger Day',
        'Trigger',
        'PDH',
        '1m ORH',
        'VWAP Reclaim',
        '5m ORH',
        'Notes',
        'Current %',
        'Max %',
        'Close < BE',
        'D3 High %',
        'Retests',
        'Setup',
        'Entry Tactic',
        'Rating',
    ]
    assert 'Label' not in DAILY_WORKFLOW_COLUMNS
    assert 'Secondary' not in DAILY_WORKFLOW_COLUMNS
    assert 'Close Loc.' not in DAILY_WORKFLOW_COLUMNS
    assert 'Range x ATR(14)' not in DAILY_WORKFLOW_COLUMNS


def test_daily_snapshot_monitor_table_reuses_single_date_rolling_monitor_and_sorts(monkeypatch):
    import pandas as pd
    import src.rolling_setup_monitor as rolling_setup_monitor

    raw = pd.DataFrame([
        {'candidate_id': 1, 'Ticker': 'ZED', 'Current Status': 'Failed D1', 'Trigger Day': 'Success', 'Trigger': 'PDH', 'Current %': '50.0%', 'Max %': '60.0%', 'Rating': '5'},
        {'candidate_id': 2, 'Ticker': 'ACT', 'Current Status': 'Active', 'Trigger Day': 'Success', 'Trigger': '1m ORH', 'Current %': '60.0%', 'Max %': '65.0%', 'D3 High %': '14.0%', 'Rating': '4'},
        {'candidate_id': 3, 'Ticker': 'FAIL', 'Current Status': 'Failed D0', 'Trigger Day': 'Fail', 'Trigger': 'Failed OR Trigger', 'Current %': '40.0%', 'Max %': '50.0%', 'Rating': '5'},
        {'candidate_id': 4, 'Ticker': 'UNR', 'Current Status': '-', 'Trigger Day': 'Unresolved', 'Trigger': 'No Trigger', 'Current %': '90.0%', 'Max %': '90.0%', 'Rating': '5'},
    ])
    calls = []

    def fake_rolling_setup_monitor_for_date(_con, setup_date):
        calls.append(setup_date)
        return [{'setup_date': '2026-04-01', 'table': raw}]

    monkeypatch.setattr(rolling_setup_monitor, 'rolling_setup_monitor_for_date', fake_rolling_setup_monitor_for_date)
    monkeypatch.setattr(rolling_setup_monitor, 'sort_monitor_rows', lambda table: table.copy())
    monkeypatch.setattr(rolling_setup_monitor, 'main_table', lambda table: table.drop(columns=['candidate_id']).copy())

    out = daily_snapshot_monitor_table(object(), '2026-04-01', include_candidate_id=True)

    assert calls == ['2026-04-01']
    assert out.columns.tolist() == DAILY_WORKFLOW_INTERNAL_COLUMNS
    assert out['Ticker'].tolist() == ['ACT', 'ZED', 'FAIL', 'UNR']
    assert out['candidate_id'].tolist() == [2, 1, 3, 4]
    assert out.loc[out['Ticker'].eq('ACT'), 'Max %'].iloc[0] == '65.0%'
    assert out.loc[out['Ticker'].eq('ACT'), 'D3 High %'].iloc[0] == '14.0%'


def test_daily_snapshot_summary_groups_include_command_center_sections():
    import pandas as pd

    table = pd.DataFrame([
        {
            'Ticker': 'AAA',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': '1m ORH',
            'PDH': '-',
            '1m ORH': 'success',
            'VWAP Reclaim': '-',
            '5m ORH': '-',
            'Current %': '12.0%',
            'Max %': '22.0%',
            'Close < BE': 'No',
            'D3 High %': '18.0%',
            'Retests': 'D0, D2',
            'Rating': '5',
        },
        {
            'Ticker': 'BBB',
            'Current Status': 'Failed D0',
            'Trigger Day': 'Fail',
            'Trigger': 'Failed OR Trigger',
            'PDH': 'Gap',
            '1m ORH': 'failed',
            'VWAP Reclaim': 'failed',
            '5m ORH': 'failed',
            'Current %': '-4.0%',
            'Max %': '5.0%',
            'Close < BE': 'Yes',
            'D3 High %': '',
            'Retests': '',
            'Rating': '3',
        },
    ])
    metrics = {
        'setup_candidate_count': 2,
        'pct_closed_above_vwap': 0.5,
        'pct_closed_near_hod': 0.25,
        'median_close_location': 0.7,
        'median_range_vs_atr20': 1.2,
        'median_relative_volume': 2.3,
        'pct_broke_setup_day_high_within_3d': 0.5,
        'pct_broke_setup_day_low_within_3d': 0.0,
    }

    groups = daily_snapshot_summary_groups(metrics, table)

    assert [group['title'] for group in groups] == [
        'Overall',
        'Trigger Quality',
        'Follow-Through',
        'Opening / Intraday Character',
    ]
    assert ('Active', '1 (50%)') in groups[0]['metrics']
    assert ('1m ORH Success', '1 (50%)') in groups[1]['metrics']
    assert ('Close < BE', '1 (50%)') in groups[2]['metrics']
    assert ('Retested After D0', '1 (50%)') in groups[2]['metrics']
    assert ('Closed Above VWAP %', '50.0%') in groups[3]['metrics']


def test_daily_snapshot_summary_groups_handle_empty_table():
    groups = daily_snapshot_summary_groups({'setup_candidate_count': 0}, __import__('pandas').DataFrame())

    assert [group['title'] for group in groups] == [
        'Overall',
        'Trigger Quality',
        'Follow-Through',
        'Opening / Intraday Character',
    ]
    assert ('Setups', '0') in groups[0]['metrics']


def test_daily_snapshot_table_reload_shows_saved_metadata(monkeypatch):
    import duckdb
    import pandas as pd
    import src.rolling_setup_monitor as rolling_setup_monitor
    from src.rolling_setup_monitor import apply_setup_rating_updates, manual_metadata_candidates

    con = duckdb.connect(':memory:')
    con.execute(
        """
        create table watchlist_candidates (
            candidate_id bigint,
            watchlist_date date,
            ticker text,
            setup text,
            entry_tactic text,
            rating double
        )
        """
    )
    con.execute("insert into watchlist_candidates values (1, '2026-05-01', 'AAPL', 'EP', null, 2)")

    def fake_rolling_setup_monitor_for_date(db_con, setup_date):
        metadata = manual_metadata_candidates(db_con, setup_date)
        table = metadata.assign(**{
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': 'PDH',
            'Current %': '10.0%',
            'Max %': '20.0%',
        })
        return [{'setup_date': str(pd.to_datetime(setup_date).date()), 'table': table}]

    monkeypatch.setattr(rolling_setup_monitor, 'rolling_setup_monitor_for_date', fake_rolling_setup_monitor_for_date)
    monkeypatch.setattr(rolling_setup_monitor, 'sort_monitor_rows', lambda table: table.copy())
    monkeypatch.setattr(rolling_setup_monitor, 'main_table', lambda table: table.drop(columns=['candidate_id']).copy())

    original = daily_snapshot_monitor_table(con, '2026-05-01', include_candidate_id=True)
    edited = original[['candidate_id', 'Ticker', 'Setup', 'Entry Tactic', 'Rating']].copy()
    edited.loc[0, 'Setup'] = 'Pullback'
    edited.loc[0, 'Entry Tactic'] = 'Bias Flip'
    edited.loc[0, 'Rating'] = '4'

    assert apply_setup_rating_updates(con, original, edited) == 1
    reloaded = daily_snapshot_monitor_table(con, '2026-05-01', include_candidate_id=True)

    assert reloaded.loc[0, 'Setup'] == 'Pullback'
    assert reloaded.loc[0, 'Entry Tactic'] == 'Bias Flip'
    assert reloaded.loc[0, 'Rating'] == '4'
    assert reloaded.loc[0, 'Current Status'] == 'Active'
    assert reloaded.loc[0, 'Current %'] == '10.0%'


def test_daily_snapshot_page_exposes_compact_manual_metadata_editor():
    page = open('pages/1_Daily_Snapshot.py', encoding='utf-8').read()

    assert "st.subheader('Edit Selected Candidate')" in page
    assert 'daily_snapshot_monitor_table(con, d, include_candidate_id=True)' in page
    assert 'apply_setup_rating_updates(con, original, edited)' in page
    assert 'refresh_derived_watchlist_views(db_path=str(get_settings().db_path), rebuild_materialized_history=True)' in page
    assert "st.button('Refresh derived views from database'" in page
    assert 'st.cache_data.clear()' not in page
    assert "edited.loc[0, 'Setup']" in page
    assert "edited.loc[0, 'Entry Tactic']" in page
    assert "edited.loc[0, 'Rating']" in page
    assert "edited.loc[0, 'Trigger']" not in page
    assert "edited.loc[0, 'Current Status']" not in page
