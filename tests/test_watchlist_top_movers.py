from __future__ import annotations

import pandas as pd

from src.watchlist_top_movers import (
    ACTIVE_VISIBLE_COLUMNS,
    DEFAULT_SETUP_WINDOW,
    VISIBLE_COLUMNS,
    filter_setup_window,
    top_movers_from_history,
)


def _history() -> pd.DataFrame:
    rows = []
    for index in range(1, 13):
        rows.append({
            'Ticker': f'T{index:02d}',
            'Setup Date': f'2026-04-{index:02d}',
            'Trigger': '1m ORH' if index % 3 == 0 else '5m ORH' if index % 3 == 1 else 'PDH',
            'Current Status': 'Active' if index % 2 else 'Failed D1',
            'Current %': f'{index:.1f}%',
            'Max %': f'{index + 5:.1f}%',
            'Latest Status Date': '2026-04-30',
            'current_pct_raw': float(index) / 100,
            'max_pct_raw': float(index + 5) / 100,
            'Max High': 20 + index,
            'Retest Day': 'D1' if index % 4 == 0 else '',
            'Breakeven / D1 Eligible': 'Yes' if index % 5 == 0 else '',
            'Notes': 'Wide 5m OR' if index % 6 == 0 else '',
            'Trigger Level': 10 + index,
            'Latest Close': 15 + index,
            'D3 High %': f'{index + 3:.1f}%',
            'Setup': 'Flag',
            'Rating': 3,
        })
    return pd.DataFrame(rows)


def test_setup_window_filtering_by_last_5_setup_dates():
    out = filter_setup_window(_history(), 'Last 5 setup dates')

    assert out['Setup Date'].dt.strftime('%Y-%m-%d').tolist() == [
        '2026-04-08',
        '2026-04-09',
        '2026-04-10',
        '2026-04-11',
        '2026-04-12',
    ]


def test_setup_window_filtering_by_last_10_setup_dates():
    out = filter_setup_window(_history(), 'Last 10 setup dates')

    assert len(out) == 10
    assert out['Setup Date'].dt.strftime('%Y-%m-%d').min() == '2026-04-03'


def test_setup_window_filtering_by_last_20_setup_dates_includes_all_available():
    out = filter_setup_window(_history(), 'Last 20 setup dates')

    assert len(out) == 12


def test_setup_window_all_includes_all_setup_dates():
    out = filter_setup_window(_history(), 'All')

    assert len(out) == 12


def test_default_setup_window_is_all():
    page = open('pages/6_Watchlist_Top_Movers.py', encoding='utf-8').read()

    assert DEFAULT_SETUP_WINDOW == 'All'
    assert 'index=SETUP_WINDOW_OPTIONS.index(DEFAULT_SETUP_WINDOW)' in page


def test_page_groups_active_table_outside_setup_window_filters():
    page = open('pages/6_Watchlist_Top_Movers.py', encoding='utf-8').read()

    active_heading = page.index("st.subheader('Top 10 Active Watchlist Movers')")
    filter_heading = page.index("st.subheader('Top Triggered Watchlist Movers')")
    filter_widget = page.index("st.selectbox(\n            'Setup Window'")
    assert active_heading < filter_heading < filter_widget
    assert 'Uses all available setup dates and is not affected by the setup-window filter below.' in page


def test_top_n_filtering_and_deterministic_rank_assignment():
    result = top_movers_from_history(_history(), latest_date='2026-04-30', top_n=3, sort_by='Max %')

    assert result.table['Rank'].tolist() == [1, 2, 3]
    assert result.table['Ticker'].tolist() == ['T12', 'T11', 'T10']


def test_max_pct_sort_behavior_uses_current_pct_tiebreaker():
    history = pd.DataFrame([
        {'Ticker': 'A', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
        {'Ticker': 'B', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.04, 'max_pct_raw': 0.10},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30', top_n=10, sort_by='Max %')

    assert result.table['Ticker'].tolist() == ['B', 'A']


def test_current_pct_sort_behavior_uses_max_pct_tiebreaker():
    history = pd.DataFrame([
        {'Ticker': 'A', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.05, 'max_pct_raw': 0.08},
        {'Ticker': 'B', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.05, 'max_pct_raw': 0.12},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30', top_n=10, sort_by='Current %')

    assert result.table['Ticker'].tolist() == ['B', 'A']


def test_days_since_setup_calculation_and_sort_behavior():
    history = pd.DataFrame([
        {'Ticker': 'OLD', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.01, 'max_pct_raw': 0.03},
        {'Ticker': 'NEW', 'Setup Date': '2026-04-10', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.02, 'max_pct_raw': 0.08},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30', top_n=10, sort_by='Days Since Setup')

    assert result.table['Ticker'].tolist() == ['OLD', 'NEW']
    assert result.table['Days Since Setup'].tolist() == [29, 20]


def test_field_mapping_for_trigger_status_max_high_retest_and_breakeven():
    result = top_movers_from_history(_history().iloc[[4]], latest_date='2026-04-30')
    row = result.table.iloc[0]

    assert row['Trigger'] == 'PDH'
    assert row['Current Status'] == 'Active'
    assert row['Max High'] == '25.00'
    assert row['Retested'] == '-'
    assert row['Breakeven / D1 Eligible'] == 'Yes'


def test_vwap_reclaim_can_display_as_top_mover_trigger():
    history = pd.DataFrame([{
        'Ticker': 'VWAP',
        'Setup Date': '2026-04-01',
        'Trigger': 'Alt Required',
        'Trigger Day': 'Success',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-05',
        '1m ORH': 'failed',
        '5m ORH': 'failed',
        'VWAP Reclaim': 'success',
        'VWAP Reclaim Trigger Price': 10.5,
        'PDH': '-',
        'current_pct_raw': 0.06,
        'max_pct_raw': 0.14,
    }])

    result = top_movers_from_history(history, latest_date='2026-04-05')

    assert result.table.loc[0, 'Trigger'] == 'VWAP Reclaim'
    assert result.active_table.loc[0, 'Trigger'] == 'VWAP Reclaim'


def test_raw_vwap_reclaim_does_not_display_as_top_mover_trigger_when_not_resolved():
    history = pd.DataFrame([{
        'Ticker': 'PDH',
        'Setup Date': '2026-04-01',
        'Trigger': 'PDH',
        'Trigger Day': 'Success',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-05',
        '1m ORH': '-',
        '5m ORH': '-',
        'VWAP Reclaim': 'success',
        'VWAP Reclaim Trigger Price': 10.5,
        'PDH': 'success',
        'current_pct_raw': 0.06,
        'max_pct_raw': 0.14,
    }])

    result = top_movers_from_history(history, latest_date='2026-04-05')

    assert result.table.loc[0, 'Trigger'] == 'PDH'


def test_missing_optional_field_behavior_keeps_row_with_dashes():
    history = pd.DataFrame([{
        'Ticker': 'MISS',
        'Setup Date': '2026-04-01',
        'Trigger': 'Alt Required',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-05',
        'current_pct_raw': 0.012,
        'max_pct_raw': 0.044,
    }])

    result = top_movers_from_history(history, latest_date='2026-04-05')
    row = result.table.iloc[0]

    assert row['Max High'] == '-'
    assert row['Retested'] == '-'
    assert row['Breakeven / D1 Eligible'] == '-'
    assert row['Notes'] == '-'


def test_setup_date_formats_as_date_only_in_tables_and_audit():
    result = top_movers_from_history(_history().iloc[[0]], latest_date='2026-04-30')

    assert result.table.loc[0, 'Setup Date'] == '2026-04-01'
    assert result.audit.loc[0, 'Setup Date'] == '2026-04-01'
    assert result.active_table.loc[0, 'Setup Date'] == '2026-04-01'


def test_visible_column_contract():
    result = top_movers_from_history(_history(), latest_date='2026-04-30')

    assert result.table.columns.tolist() == VISIBLE_COLUMNS


def test_active_table_filters_active_only_and_omits_current_status():
    result = top_movers_from_history(_history(), latest_date='2026-04-30')

    assert result.active_table.columns.tolist() == ACTIVE_VISIBLE_COLUMNS
    assert 'Current Status' not in result.active_table.columns
    assert result.active_table['Ticker'].tolist() == ['T11', 'T09', 'T07', 'T05', 'T03', 'T01']


def test_active_table_ignores_selected_setup_window():
    result = top_movers_from_history(_history(), latest_date='2026-04-30', setup_window='Last 5 setup dates')

    assert result.active_table['Ticker'].tolist() == ['T11', 'T09', 'T07', 'T05', 'T03', 'T01']
    assert result.table['Ticker'].tolist() == ['T12', 'T11', 'T10', 'T09', 'T08']


def test_active_table_limits_to_10_rows():
    history = _history()
    history['Current Status'] = 'Active'

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert len(result.active_table) == 10
    assert result.active_table['Rank'].tolist() == list(range(1, 11))


def test_active_table_sorts_by_max_pct_then_current_pct():
    history = pd.DataFrame([
        {'Ticker': 'A', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
        {'Ticker': 'B', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.04, 'max_pct_raw': 0.10},
        {'Ticker': 'C', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Failed D1', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.20},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['B', 'A']


def test_active_table_excludes_non_active_statuses():
    history = pd.DataFrame([
        {'Ticker': 'ACTIVE', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Trigger Day': 'Success', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
        {'Ticker': 'LATER', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Trigger Day': 'Success', 'Current Status': 'Later Failed', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.30},
        {'Ticker': 'D1', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Trigger Day': 'Success', 'Current Status': 'Failed D1', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.29},
        {'Ticker': 'DAYFAIL', 'Setup Date': '2026-04-01', 'Trigger': 'Failed OR Trigger', 'Trigger Day': 'Fail', 'Current Status': '—', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.28},
        {'Ticker': 'UNRES', 'Setup Date': '2026-04-01', 'Trigger': 'No Trigger', 'Trigger Day': 'Unresolved', 'Current Status': '—', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.27},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['ACTIVE']


def test_active_table_excludes_stale_active_status_rows():
    history = pd.DataFrame([
        {'Ticker': 'CURRENT', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
        {'Ticker': 'STALE', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-22', 'current_pct_raw': 0.08, 'max_pct_raw': 0.30},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['CURRENT']
    assert result.table['Ticker'].tolist() == ['STALE', 'CURRENT']
    assert result.audit.set_index('Ticker').loc['STALE', 'Status Current'] == 'No'


def test_active_table_uses_latest_status_when_duplicate_ticker_setup_rows_exist():
    history = pd.DataFrame([
        {'Ticker': 'DUP', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-22', 'current_pct_raw': 0.08, 'max_pct_raw': 0.30},
        {'Ticker': 'DUP', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Failed D1', 'Latest Status Date': '2026-04-30', 'current_pct_raw': -0.02, 'max_pct_raw': 0.30},
        {'Ticker': 'OK', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['OK']


def test_active_table_excludes_bird_like_stale_status_even_with_high_max_return():
    history = pd.DataFrame([{
        'Ticker': 'BIRD',
        'Setup Date': '2026-04-15',
        'Trigger': '5m ORH',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-22',
        'Trigger Level': 7.94,
        'Reference Low': 6.11,
        'Latest Close': 8.43,
        'current_pct_raw': 0.0617,
        'max_pct_raw': 2.0617,
    }])

    result = top_movers_from_history(history, latest_date='2026-05-04')

    assert result.active_table.empty
    assert result.table.loc[0, 'Ticker'] == 'BIRD'
