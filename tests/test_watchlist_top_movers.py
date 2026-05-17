from __future__ import annotations

import pandas as pd

from src.watchlist_top_movers import (
    ACTIVE_VISIBLE_COLUMNS,
    DEFAULT_PORTFOLIO_VIEW,
    DEFAULT_SETUP_WINDOW,
    PORTFOLIO_VIEW_OPTIONS,
    PORTFOLIO_VISIBLE_COLUMNS,
    VISIBLE_COLUMNS,
    filter_setup_window,
    portfolio_eligibility_funnel,
    portfolio_exclusion_samples,
    portfolio_summary,
    prepare_top_mover_rows,
    top_movers_from_history,
)


def _with_entry_prices(row: dict, entry: float = 10.0) -> dict:
    out = dict(row)
    current = out.get('current_pct_raw')
    max_pct = out.get('max_pct_raw')
    out.setdefault('Trigger Level', entry)
    if current is not None:
        out.setdefault('Latest Close', entry * (1 + float(current)))
    if max_pct is not None:
        out.setdefault('Max High After Trigger', entry * (1 + float(max_pct)))
    out.setdefault('Max High', out.get('Max High After Trigger'))
    return out


def _entry_history(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([_with_entry_prices(row) for row in rows])


def _history() -> pd.DataFrame:
    rows = []
    for index in range(1, 13):
        entry = 10 + index
        current_pct = float(index) / 100
        max_pct = float(index + 5) / 100
        rows.append({
            'Ticker': f'T{index:02d}',
            'Setup Date': f'2026-04-{index:02d}',
            'Trigger': '1m ORH' if index % 3 == 0 else '5m ORH' if index % 3 == 1 else 'PDH',
            'Current Status': 'Active' if index % 2 else 'Failed D1',
            'Current %': f'{index:.1f}%',
            'Max %': f'{index + 5:.1f}%',
            'Latest Status Date': '2026-04-30',
            'Ticker Latest Bar Date': '2026-04-30',
            'Global Latest Bar Date': '2026-04-30',
            'current_pct_raw': current_pct,
            'max_pct_raw': max_pct,
            'Max High': 20 + index,
            'Close < BE': 'Yes' if index % 7 == 0 else 'No',
            'Retest Day': 'D1' if index % 4 == 0 else '',
            'Breakeven / D1 Eligible': 'Yes' if index % 5 == 0 else '',
            'Notes': 'Wide 5m OR' if index % 6 == 0 else '',
            'Trigger Level': entry,
            'Latest Close': entry * (1 + current_pct),
            'Max High After Trigger': entry * (1 + max_pct),
            'D3 High %': f'{index + 3:.1f}%',
            'Setup': 'Flag',
            'Entry Tactic': 'Gap Over Range' if index == 1 else '',
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
    page = open('pages/6_Top_Movers.py', encoding='utf-8').read()

    assert DEFAULT_SETUP_WINDOW == 'All'
    assert 'index=SETUP_WINDOW_OPTIONS.index(DEFAULT_SETUP_WINDOW)' in page


def test_page_groups_active_table_outside_setup_window_filters():
    page = open('pages/6_Top_Movers.py', encoding='utf-8').read()

    portfolio_heading = page.index("st.subheader('Hypothetical Portfolio View')")
    portfolio_selector = page.index("'Portfolio View'")
    portfolio_caption = page.index("st.caption('Current Progress:")
    portfolio_table = page.index("st.dataframe(all_active_result.portfolio_table")
    reference_heading = page.index("st.header('Reference Tables')")
    active_heading = page.index("st.subheader('Top 10 Active Watchlist Movers')")
    active_table = page.index("st.dataframe(all_active_result.active_table")
    filter_heading = page.index("st.subheader('Top Triggered Watchlist Movers')")
    filter_widget = page.index("st.selectbox(\n            'Setup Window'")
    assert portfolio_heading < portfolio_selector < portfolio_caption < portfolio_table
    assert portfolio_table < reference_heading < active_heading < active_table < filter_heading < filter_widget
    assert 'No active 4–5 star names currently qualify.' in page
    assert 'No active 4–5 star names with valid Days Since Setup currently qualify.' in page
    assert "'Portfolio View'" in page
    assert "key='top_movers_portfolio_view'" in page
    assert 'Current Progress: active, fresh 4–5 star names ranked by Current %.' in page
    assert 'Longest Open: active, fresh 4–5 star names ranked by Days Since Setup.' in page
    assert 'Max Progress' not in page
    assert 'Ranks active setups by entry-based Current %, then Rating, then entry-based Max %.' in page
    assert 'Entry Ref is the resolved trigger/reference price; setup-close returns remain in Details / Audit.' in page
    assert "setup_window='All'" in page
    assert 'portfolio_view=portfolio_view' in page
    assert 'top_n=20' in page
    assert 'portfolio_summary(all_active_result.portfolio_table)' in page


def test_page_active_table_uses_db_backed_cache_token_and_row_count_caption():
    page = open('pages/6_Top_Movers.py', encoding='utf-8').read()

    assert "TOP_MOVERS_CACHE_VERSION = 'top-movers-longest-open-v1'" in page
    assert "top_movers_cache_token = f'{TOP_MOVERS_CACHE_VERSION}:{data_health_cache_token(db_path)}'" in page
    assert 'load_watchlist_top_movers(db_path, top_movers_cache_token, base_history)' in page
    assert 'load_cached_monitor_history(db_path, monitor_history_cache_token)' in page
    assert "st.button('Refresh derived views from database'" in page
    assert 'refresh_derived_watchlist_views(load_watchlist_top_movers)' in page
    assert "PerfTimer('Top Movers')" in page
    assert 'render_perf_debug(st, perf)' in page
    assert "st.caption(f'Active rows: {len(all_active_result.active_table)}')" in page
    assert 'Why empty:' in page


def test_default_portfolio_view_is_current_progress():
    page = open('pages/6_Top_Movers.py', encoding='utf-8').read()

    assert DEFAULT_PORTFOLIO_VIEW == 'Current Progress'
    assert PORTFOLIO_VIEW_OPTIONS == ['Current Progress', 'Longest Open']
    assert 'index=PORTFOLIO_VIEW_OPTIONS.index(DEFAULT_PORTFOLIO_VIEW)' in page


def test_portfolio_summary_formats_counts_and_averages():
    table = pd.DataFrame([
        {'Ticker': 'A', 'Rating': 5, 'Current %': '10.0%', 'Max %': '20.0%'},
        {'Ticker': 'B', 'Rating': '4', 'Current %': '20.0%', 'Max %': '40.0%'},
        {'Ticker': 'C', 'Rating': 5.0, 'Current %': '30.0%', 'Max %': '60.0%'},
    ])

    assert portfolio_summary(table) == '3 names | Avg Current 20.0% | Avg Max 40.0% | 2 rated 5★ | 1 rated 4★'


def test_portfolio_summary_handles_empty_table_without_averages():
    assert portfolio_summary(pd.DataFrame(columns=PORTFOLIO_VISIBLE_COLUMNS)) == ''


def test_top_n_filtering_and_deterministic_rank_assignment():
    result = top_movers_from_history(_history(), latest_date='2026-04-30', top_n=3, sort_by='Max %')

    assert result.table['Rank'].tolist() == [1, 2, 3]
    assert result.table['Ticker'].tolist() == ['T12', 'T11', 'T10']


def test_prepared_top_mover_rows_preserve_output_values():
    history = _history()
    mapped = prepare_top_mover_rows(history, latest_date='2026-04-30')

    dynamic = top_movers_from_history(history, latest_date='2026-04-30', top_n=10)
    optimized = top_movers_from_history(history, latest_date='2026-04-30', top_n=10, mapped_history=mapped)

    pd.testing.assert_frame_equal(optimized.portfolio_table, dynamic.portfolio_table)
    pd.testing.assert_frame_equal(optimized.active_table, dynamic.active_table)
    pd.testing.assert_frame_equal(optimized.table, dynamic.table)
    pd.testing.assert_frame_equal(optimized.audit, dynamic.audit)


def test_max_pct_sort_behavior_uses_current_pct_tiebreaker():
    history = _entry_history([
        {'Ticker': 'A', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
        {'Ticker': 'B', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.04, 'max_pct_raw': 0.10},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30', top_n=10, sort_by='Max %')

    assert result.table['Ticker'].tolist() == ['B', 'A']


def test_current_pct_sort_behavior_uses_max_pct_tiebreaker():
    history = _entry_history([
        {'Ticker': 'A', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.05, 'max_pct_raw': 0.08},
        {'Ticker': 'B', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.05, 'max_pct_raw': 0.12},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30', top_n=10, sort_by='Current %')

    assert result.table['Ticker'].tolist() == ['B', 'A']


def test_days_since_setup_calculation_and_sort_behavior():
    history = _entry_history([
        {'Ticker': 'OLD', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.01, 'max_pct_raw': 0.03},
        {'Ticker': 'NEW', 'Setup Date': '2026-04-10', 'Trigger': 'PDH', 'Current Status': 'Active', 'current_pct_raw': 0.02, 'max_pct_raw': 0.08},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30', top_n=10, sort_by='Days Since Setup')

    assert result.table['Ticker'].tolist() == ['OLD', 'NEW']
    assert result.table['Days Since Setup'].tolist() == [29, 20]


def test_field_mapping_for_trigger_status_max_high_retest_and_breakeven():
    result = top_movers_from_history(_history().iloc[[4]], latest_date='2026-04-30')
    row = result.table.iloc[0]
    audit = result.audit.iloc[0]

    assert row['Trigger'] == 'PDH'
    assert row['Current Status'] == 'Active'
    assert 'Max High' not in row.index
    assert audit['Max High'] == '25.00'
    assert row['Retests'] == '-'
    assert 'Breakeven / D1 Eligible' not in row.index
    assert audit['Breakeven / D1 Eligible'] == 'Yes'


def test_vwap_reclaim_can_display_as_top_mover_trigger():
    history = pd.DataFrame([{
        'Ticker': 'VWAP',
        'Setup Date': '2026-04-01',
        'Trigger': 'Alt Required',
        'Trigger Day': 'Success',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-05',
        'Ticker Latest Bar Date': '2026-04-05',
        'Global Latest Bar Date': '2026-04-05',
        '1m ORH': 'failed',
        '5m ORH': 'failed',
        'VWAP Reclaim': 'success',
        'VWAP Reclaim Trigger Price': None,
        'Raw VWAP Reclaim Trigger Price': 10.5,
        'Latest Close': 11.13,
        'Max High After Trigger': 11.97,
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
        'Ticker Latest Bar Date': '2026-04-05',
        'Global Latest Bar Date': '2026-04-05',
        '1m ORH': '-',
        '5m ORH': '-',
        'VWAP Reclaim': 'success',
        'VWAP Reclaim Trigger Price': 10.5,
        'PDH': 'success',
        'Trigger Level': 10.0,
        'Latest Close': 10.6,
        'Max High After Trigger': 11.4,
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
        'Ticker Latest Bar Date': '2026-04-05',
        'Global Latest Bar Date': '2026-04-05',
        'current_pct_raw': 0.012,
        'max_pct_raw': 0.044,
    }])

    result = top_movers_from_history(history, latest_date='2026-04-05')
    row = result.table.iloc[0]
    audit = result.audit.iloc[0]

    assert 'Max High' not in row.index
    assert audit['Max High'] == '-'
    assert row['Retests'] == '-'
    assert 'Breakeven / D1 Eligible' not in row.index
    assert audit['Breakeven / D1 Eligible'] == '-'
    assert row['Close < BE'] == '-'
    assert row['Notes'] == '-'
    assert result.active_table['Ticker'].tolist() == ['MISS']


def test_multiple_retests_display_in_top_movers_tables():
    history = pd.DataFrame([{
        'Ticker': 'MULTI',
        'Setup Date': '2026-04-01',
        'Trigger': 'PDH',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-05',
        'Ticker Latest Bar Date': '2026-04-05',
        'Global Latest Bar Date': '2026-04-05',
        'current_pct_raw': 0.012,
        'max_pct_raw': 0.044,
        'Retests': 'D0, D3',
    }])

    result = top_movers_from_history(history, latest_date='2026-04-05')

    assert result.table.loc[0, 'Retests'] == 'D0, D3'
    assert result.active_table.loc[0, 'Retested'] == 'D0, D3'


def test_setup_date_formats_as_date_only_in_tables_and_audit():
    result = top_movers_from_history(_history().iloc[[0]], latest_date='2026-04-30')

    assert result.table.loc[0, 'Setup Date'] == '2026-04-01'
    assert result.audit.loc[0, 'Setup Date'] == '2026-04-01'


def test_top_movers_audit_displays_entry_tactic():
    result = top_movers_from_history(_history().iloc[[0]], latest_date='2026-04-30')

    assert 'Entry Tactic' in result.audit.columns
    assert result.audit.loc[0, 'Entry Tactic'] == 'Gap Over Range'
    assert result.active_table.loc[0, 'Setup Date'] == '2026-04-01'


def test_visible_column_contract():
    result = top_movers_from_history(_history(), latest_date='2026-04-30')

    assert result.table.columns.tolist() == VISIBLE_COLUMNS
    assert result.table.columns.tolist() == [
        'Rank',
        'Ticker',
        'Setup Date',
        'Trigger',
        'Current Status',
        'Current %',
        'Max %',
        'Close < BE',
        'Days Since Setup',
        'Retests',
        'Notes',
    ]
    assert 'Max High' not in result.table.columns
    assert 'Breakeven / D1 Eligible' not in result.table.columns
    assert 'Close < BE' in result.table.columns


def test_entry_based_return_beats_setup_close_return_in_active_table():
    history = _entry_history([
        {
            'Ticker': 'GAP',
            'Setup Date': '2026-04-01',
            'Trigger': 'PDH',
            'Current Status': 'Active',
            'Latest Status Date': '2026-04-30',
            'Ticker Latest Bar Date': '2026-04-30',
            'Global Latest Bar Date': '2026-04-30',
            'Trigger Level': 18,
            'Latest Close': 18.5,
            'Max High After Trigger': 19,
            'current_pct_raw': 0.85,
            'max_pct_raw': 0.90,
        },
        {
            'Ticker': 'CLEAN',
            'Setup Date': '2026-04-01',
            'Trigger': 'PDH',
            'Current Status': 'Active',
            'Latest Status Date': '2026-04-30',
            'Ticker Latest Bar Date': '2026-04-30',
            'Global Latest Bar Date': '2026-04-30',
            'Trigger Level': 11,
            'Latest Close': 13,
            'Max High After Trigger': 13.5,
            'current_pct_raw': 0.30,
            'max_pct_raw': 0.40,
        },
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['CLEAN', 'GAP']
    assert result.active_table.set_index('Ticker').loc['CLEAN', 'Current %'] == '18.2%'
    audit = result.audit.set_index('Ticker')
    assert audit.loc['GAP', 'Setup Current %'] == '85.0%'
    assert audit.loc['CLEAN', 'Setup Current %'] == '30.0%'


def test_active_ranking_uses_current_rating_max_date_and_ticker():
    history = _entry_history([
        {'Ticker': 'CUR', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.30, 'max_pct_raw': 0.31},
        {'Ticker': 'RATE', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.20, 'max_pct_raw': 0.22},
        {'Ticker': 'MAX', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.20, 'max_pct_raw': 0.50},
        {'Ticker': 'NEW', 'Setup Date': '2026-04-02', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.20, 'max_pct_raw': 0.40},
        {'Ticker': 'AAA', 'Setup Date': '2026-04-02', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.20, 'max_pct_raw': 0.40},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['CUR', 'RATE', 'MAX', 'AAA', 'NEW']


def test_vwap_reclaim_uses_vwap_trigger_price_as_entry_ref():
    history = pd.DataFrame([{
        'Ticker': 'VWAP',
        'Setup Date': '2026-04-01',
        'Trigger': 'Alt Required',
        'Trigger Day': 'Success',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-05',
        'Ticker Latest Bar Date': '2026-04-05',
        'Global Latest Bar Date': '2026-04-05',
        '1m ORH': 'failed',
        '5m ORH': 'failed',
        'VWAP Reclaim': 'success',
        'VWAP Reclaim Trigger Price': 10.5,
        'Trigger Level': 9.5,
        'Latest Close': 12.6,
        'Max High After Trigger': 13.65,
        'PDH': '-',
        'current_pct_raw': 0.60,
        'max_pct_raw': 0.80,
    }])

    result = top_movers_from_history(history, latest_date='2026-04-05')

    assert result.active_table.loc[0, 'Entry Ref'] == '10.50'
    assert result.active_table.loc[0, 'Current %'] == '20.0%'
    assert result.audit.loc[0, 'Reference Price'] == '10.5'


def test_no_trigger_rows_have_missing_entry_ref_and_sort_last():
    history = _entry_history([
        {'Ticker': 'GOOD', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.03},
        {'Ticker': 'UNTRIG', 'Setup Date': '2026-04-01', 'Trigger': 'No Trigger', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.99, 'max_pct_raw': 1.20},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['GOOD', 'UNTRIG']
    assert result.active_table.set_index('Ticker').loc['UNTRIG', 'Entry Ref'] == '-'
    assert result.active_table.set_index('Ticker').loc['UNTRIG', 'Current %'] == '-'
    assert 'Missing: Entry Ref' in result.audit.set_index('Ticker').loc['UNTRIG', 'Missing Data Notes']


def test_audit_preserves_setup_close_returns():
    history = _entry_history([
        {'Ticker': 'AUD', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.21, 'max_pct_raw': 0.34},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.audit.loc[0, 'Setup Current %'] == '21.0%'
    assert result.audit.loc[0, 'Setup Max %'] == '34.0%'


def test_missing_post_trigger_max_high_falls_back_to_setup_max_with_audit_note():
    history = pd.DataFrame([{
        'Ticker': 'WHOLE',
        'Setup Date': '2026-04-01',
        'Trigger': 'PDH',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-30',
        'Ticker Latest Bar Date': '2026-04-30',
        'Global Latest Bar Date': '2026-04-30',
        'Trigger Level': 10,
        'Latest Close': 11,
        'Max High': 25,
        'current_pct_raw': 0.10,
        'max_pct_raw': 1.50,
    }])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table.loc[0, 'Max %'] == '150.0%'
    assert result.active_table.loc[0, 'Max High'] == '25.00'
    audit = result.audit.loc[0]
    assert audit['Max High'] == '25.00'
    assert audit['Setup Max %'] == '150.0%'
    assert 'Missing: post-trigger Max High' in audit['Missing Data Notes']


def test_active_table_filters_active_only_and_omits_current_status():
    result = top_movers_from_history(_history(), latest_date='2026-04-30')

    assert result.active_table.columns.tolist() == ACTIVE_VISIBLE_COLUMNS
    assert 'Current Status' not in result.active_table.columns
    assert 'Entry Ref' in result.active_table.columns
    assert 'Rating' in result.active_table.columns
    assert 'Max High' in result.active_table.columns
    assert 'Breakeven / D1 Eligible' not in result.active_table.columns
    assert 'Close < BE' not in result.active_table.columns
    assert result.active_table['Ticker'].tolist() == ['T11', 'T09', 'T07', 'T05', 'T03', 'T01']


def _portfolio_history() -> pd.DataFrame:
    return _entry_history([
        {'Ticker': 'BEST', 'Setup Date': '2026-04-07', 'Trigger': '1m ORH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.30, 'max_pct_raw': 0.50, 'Close < BE': 'No', 'Retests': 'D1', 'Setup': 'Pullback'},
        {'Ticker': 'TIE_NEW', 'Setup Date': '2026-04-08', 'Trigger': '5m ORH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.20, 'max_pct_raw': 0.40, 'Close < BE': 'No', 'Retests': '', 'Setup': 'EP'},
        {'Ticker': 'TIE_OLD', 'Setup Date': '2026-04-06', 'Trigger': '5m ORH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.20, 'max_pct_raw': 0.40, 'Close < BE': 'No', 'Retests': '', 'Setup': 'Flag'},
        {'Ticker': 'FOUR', 'Setup Date': '2026-04-09', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.40, 'max_pct_raw': 0.60, 'Close < BE': 'No', 'Retests': '', 'Setup': 'Flag'},
        {'Ticker': 'FAILED', 'Setup Date': '2026-04-10', 'Trigger': 'PDH', 'Current Status': 'Failed D1', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.90, 'max_pct_raw': 1.00, 'Close < BE': 'No', 'Setup': 'Flag'},
        {'Ticker': 'STALE', 'Setup Date': '2026-04-11', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-29', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.80, 'max_pct_raw': 0.90, 'Close < BE': 'No', 'Setup': 'Flag'},
        {'Ticker': 'LOWRATE', 'Setup Date': '2026-04-12', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 3, 'current_pct_raw': 0.70, 'max_pct_raw': 0.80, 'Close < BE': 'No', 'Setup': 'Flag'},
        {'Ticker': 'NORATE', 'Setup Date': '2026-04-13', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': '', 'current_pct_raw': 0.60, 'max_pct_raw': 0.70, 'Close < BE': 'No', 'Setup': 'Flag'},
        {'Ticker': 'BELOWBE', 'Setup Date': '2026-04-14', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.55, 'max_pct_raw': 0.65, 'Close < BE': 'Yes', 'Setup': 'Flag'},
        {'Ticker': 'NOCUR', 'Setup Date': '2026-04-15', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': None, 'max_pct_raw': 0.65, 'Close < BE': 'No', 'Setup': 'Flag'},
        {'Ticker': 'NOMAX', 'Setup Date': '2026-04-16', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.55, 'max_pct_raw': None, 'Close < BE': 'No', 'Setup': 'Flag'},
    ])


def test_hypothetical_portfolio_filters_and_ranks_candidates():
    result = top_movers_from_history(_portfolio_history(), latest_date='2026-04-30', setup_window='All')

    assert result.portfolio_table.columns.tolist() == PORTFOLIO_VISIBLE_COLUMNS
    assert result.portfolio_table['Ticker'].tolist() == ['FOUR', 'BEST', 'TIE_NEW', 'TIE_OLD']
    assert result.portfolio_table['Rank'].tolist() == [1, 2, 3, 4]
    assert result.portfolio_table.loc[1, 'Setup'] == 'Pullback'
    assert result.portfolio_table.loc[1, 'Retests'] == 'D1'
    assert 'Close < BE' not in result.portfolio_table.columns
    assert 'Days Since Setup' in result.portfolio_table.columns
    assert 'Entry Tactic' in result.portfolio_table.columns
    assert result.table['Ticker'].tolist() != result.portfolio_table['Ticker'].tolist()
    assert set(result.audit['Portfolio Eligible'].unique()) == {'Yes', 'No'}
    stale_reason = result.audit.set_index('Ticker').loc['STALE', 'Portfolio Exclusion Reason']
    assert 'latest status date older than ticker latest bar date' in stale_reason
    audit_by_ticker = result.audit.set_index('Ticker')
    assert audit_by_ticker.loc['BELOWBE', 'Portfolio Eligible'] == 'No'
    assert 'close below breakeven' in audit_by_ticker.loc['BELOWBE', 'Portfolio Exclusion Reason']
    assert audit_by_ticker.loc['LOWRATE', 'Portfolio Eligible'] == 'No'
    assert 'rating below 4' in audit_by_ticker.loc['LOWRATE', 'Portfolio Exclusion Reason']
    assert audit_by_ticker.loc['FOUR', 'Current Progress Eligible'] == 'Yes'
    assert audit_by_ticker.loc['FOUR', 'Portfolio View Eligible'] == 'Yes'


def test_current_progress_excludes_stale_close_below_be_and_low_rating_rows():
    result = top_movers_from_history(_portfolio_history(), latest_date='2026-04-30', setup_window='All')
    tickers = set(result.portfolio_table['Ticker'])
    audit = result.audit.set_index('Ticker')

    assert 'STALE' not in tickers
    assert 'BELOWBE' not in tickers
    assert 'LOWRATE' not in tickers
    assert audit.loc['STALE', 'Current Progress Eligible'] == 'No'
    assert 'latest status date older than ticker latest bar date' in audit.loc['STALE', 'Portfolio Exclusion Reason']
    assert 'close below breakeven' in audit.loc['BELOWBE', 'Portfolio Exclusion Reason']
    assert 'rating below 4' in audit.loc['LOWRATE', 'Portfolio Exclusion Reason']


def test_hypothetical_portfolio_limits_to_8_rows():
    rows = _entry_history([
        {'Ticker': f'P{i:02d}', 'Setup Date': f'2026-04-{i:02d}', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': i / 100, 'max_pct_raw': (i + 1) / 100, 'Close < BE': 'No', 'Setup': ''}
        for i in range(1, 12)
    ])

    result = top_movers_from_history(rows, latest_date='2026-04-30')

    assert len(result.portfolio_table) == 8
    assert result.portfolio_table['Rank'].tolist() == list(range(1, 9))
    assert result.portfolio_table['Ticker'].tolist() == ['P11', 'P10', 'P09', 'P08', 'P07', 'P06', 'P05', 'P04']


def test_current_progress_ranks_by_current_pct_first():
    history = _entry_history([
        {'Ticker': 'CUR', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.30, 'max_pct_raw': 0.31, 'Close < BE': 'No'},
        {'Ticker': 'MAX', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.20, 'max_pct_raw': 0.80, 'Close < BE': 'No'},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30', portfolio_view='Current Progress')

    assert result.portfolio_table['Ticker'].tolist() == ['CUR', 'MAX']


def test_hypothetical_portfolio_empty_when_no_rows_qualify():
    result = top_movers_from_history(_history(), latest_date='2026-04-30')

    assert result.portfolio_table.empty
    assert result.portfolio_table.columns.tolist() == PORTFOLIO_VISIBLE_COLUMNS


def test_longest_open_uses_current_progress_eligibility_and_ranks_by_days_since_setup():
    history = _entry_history([
        {'Ticker': 'OLDER', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.10, 'max_pct_raw': 0.40, 'Close < BE': 'No'},
        {'Ticker': 'NEWER', 'Setup Date': '2026-04-10', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.90, 'max_pct_raw': 1.20, 'Close < BE': 'No'},
        {'Ticker': 'FAILED', 'Setup Date': '2026-04-02', 'Trigger': 'PDH', 'Current Status': 'Failed D1', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.80, 'max_pct_raw': 1.00, 'Close < BE': 'No'},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30', portfolio_view='Longest Open')

    assert result.portfolio_table.columns.tolist() == PORTFOLIO_VISIBLE_COLUMNS
    assert result.portfolio_table['Ticker'].tolist() == ['OLDER', 'NEWER']
    audit = result.audit.set_index('Ticker')
    assert audit.loc['OLDER', 'Longest Open Eligible'] == 'Yes'
    assert audit.loc['OLDER', 'Portfolio View Eligible'] == 'Yes'
    assert audit.loc['FAILED', 'Longest Open Eligible'] == 'No'
    assert 'not active: Failed D1' in audit.loc['FAILED', 'Portfolio View Exclusion Reason']


def test_longest_open_tiebreaks_by_current_rating_max_date_and_ticker():
    rows = _entry_history([
        {'Ticker': 'DAYS', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.10, 'max_pct_raw': 0.20, 'Close < BE': 'No'},
        {'Ticker': 'CUR', 'Setup Date': '2026-04-02', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.30, 'max_pct_raw': 0.31, 'Close < BE': 'No'},
        {'Ticker': 'RATE', 'Setup Date': '2026-04-02', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': 0.20, 'max_pct_raw': 0.22, 'Close < BE': 'No'},
        {'Ticker': 'MAX', 'Setup Date': '2026-04-02', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.20, 'max_pct_raw': 0.50, 'Close < BE': 'No'},
        {'Ticker': 'NEW', 'Setup Date': '2026-04-03', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.20, 'max_pct_raw': 0.40, 'Close < BE': 'No'},
        {'Ticker': 'AAA', 'Setup Date': '2026-04-03', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.20, 'max_pct_raw': 0.40, 'Close < BE': 'No'},
    ])

    result = top_movers_from_history(rows, latest_date='2026-04-30', portfolio_view='Longest Open')

    assert result.portfolio_table['Ticker'].tolist() == ['DAYS', 'CUR', 'RATE', 'MAX', 'AAA', 'NEW']


def test_longest_open_limits_to_8_rows():
    rows = _entry_history([
        {'Ticker': f'L{i:02d}', 'Setup Date': f'2026-04-{i:02d}', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 5, 'current_pct_raw': i / 200, 'max_pct_raw': i / 100, 'Close < BE': 'No'}
        for i in range(1, 12)
    ])

    result = top_movers_from_history(rows, latest_date='2026-04-30', portfolio_view='Longest Open')

    assert len(result.portfolio_table) == 8
    assert result.portfolio_table['Ticker'].tolist() == ['L01', 'L02', 'L03', 'L04', 'L05', 'L06', 'L07', 'L08']


def test_longest_open_requires_days_since_setup():
    history = _entry_history([
        {'Ticker': 'NODAYS', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.30, 'max_pct_raw': 0.40, 'Close < BE': 'No'},
    ])

    result = top_movers_from_history(history, latest_date=None, portfolio_view='Longest Open')
    audit = result.audit.set_index('Ticker')

    assert result.portfolio_table.empty
    assert result.portfolio_table.columns.tolist() == PORTFOLIO_VISIBLE_COLUMNS
    assert audit.loc['NODAYS', 'Current Progress Eligible'] == 'Yes'
    assert audit.loc['NODAYS', 'Longest Open Eligible'] == 'No'
    assert 'missing Days Since Setup' in audit.loc['NODAYS', 'Portfolio View Exclusion Reason']


def test_hypothetical_portfolio_accepts_integer_string_and_float_four_ratings():
    history = _entry_history([
        {'Ticker': 'INT', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.10, 'max_pct_raw': 0.20, 'Close < BE': 'No'},
        {'Ticker': 'STR', 'Setup Date': '2026-04-02', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': '4', 'current_pct_raw': 0.09, 'max_pct_raw': 0.20, 'Close < BE': 'No'},
        {'Ticker': 'FLOAT', 'Setup Date': '2026-04-03', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4.0, 'current_pct_raw': 0.08, 'max_pct_raw': 0.20, 'Close < BE': 'No'},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.portfolio_table['Ticker'].tolist() == ['INT', 'STR', 'FLOAT']
    assert result.audit.set_index('Ticker').loc['FLOAT', 'Rating Normalized'] == '4'


def test_hypothetical_portfolio_excludes_missing_low_rating_and_close_below_be():
    history = _entry_history([
        {'Ticker': 'LOW', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 3, 'current_pct_raw': 0.10, 'max_pct_raw': 0.20, 'Close < BE': 'No'},
        {'Ticker': 'MISS', 'Setup Date': '2026-04-02', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': '', 'current_pct_raw': 0.09, 'max_pct_raw': 0.20, 'Close < BE': 'No'},
        {'Ticker': 'BE', 'Setup Date': '2026-04-03', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.08, 'max_pct_raw': 0.20, 'Close < BE': 'Yes'},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')
    audit = result.audit.set_index('Ticker')

    assert result.portfolio_table.empty
    assert 'rating below 4' in audit.loc['LOW', 'Portfolio Exclusion Reason']
    assert 'missing rating' in audit.loc['MISS', 'Portfolio Exclusion Reason']
    assert 'close below breakeven' in audit.loc['BE', 'Portfolio Exclusion Reason']


def test_metadata_rating_refresh_can_make_current_progress_candidate_qualify():
    history = _entry_history([
        {
            'Ticker': 'MU',
            'Setup Date': '2026-04-01',
            'Trigger': 'PDH',
            'Current Status': 'Active',
            'Latest Status Date': '2026-04-30',
            'Ticker Latest Bar Date': '2026-04-30',
            'Global Latest Bar Date': '2026-04-30',
            'Rating': 3,
            'Current %': '25.0%',
            'Max %': '40.0%',
            'current_pct_raw': 0.25,
            'max_pct_raw': 0.40,
            'Close < BE': 'No',
            'Setup': 'EP',
            'Entry Tactic': '',
        },
    ])

    before = top_movers_from_history(history, latest_date='2026-04-30', portfolio_view='Current Progress')
    refreshed_history = history.copy()
    refreshed_history.loc[0, 'Rating'] = 5
    refreshed_history.loc[0, 'Setup'] = 'Pullback'
    refreshed_history.loc[0, 'Entry Tactic'] = 'Reclaim'
    after = top_movers_from_history(refreshed_history, latest_date='2026-04-30', portfolio_view='Current Progress')

    assert before.portfolio_table.empty
    assert 'rating below 4' in before.audit.loc[0, 'Portfolio Exclusion Reason']
    assert after.portfolio_table['Ticker'].tolist() == ['MU']
    assert after.portfolio_table.loc[0, 'Setup'] == 'Pullback'
    assert after.portfolio_table.loc[0, 'Entry Tactic'] == 'Reclaim'
    assert after.portfolio_table.loc[0, 'Rating'] == '5'


def test_hypothetical_portfolio_exclusion_reason_identifies_stale_status():
    history = _entry_history([
        {'Ticker': 'STALE', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-29', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'Rating': 4, 'current_pct_raw': 0.10, 'max_pct_raw': 0.20, 'Close < BE': 'No'},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    reason = result.audit.loc[0, 'Portfolio Exclusion Reason']
    assert 'latest status date older than ticker latest bar date' in reason


def test_portfolio_audit_funnel_counts_and_samples_exclusions():
    result = top_movers_from_history(_portfolio_history(), latest_date='2026-04-30', setup_window='All')
    mapped = prepare_top_mover_rows(_portfolio_history(), latest_date='2026-04-30')

    funnel = portfolio_eligibility_funnel(mapped)
    samples = portfolio_exclusion_samples(mapped, limit=2)

    assert funnel.set_index('Step').loc['final portfolio eligible rows', 'Rows'] == 4
    assert funnel.set_index('Step').loc['rows with valid Max %', 'Rows'] == 10
    assert samples.columns.tolist() == [
        'Ticker',
        'Setup Date',
        'Current Status',
        'Status Current',
        'Rating',
        'Close < BE',
        'Current %',
        'Max %',
        'Portfolio Exclusion Reason',
    ]
    assert len(samples) == 2


def test_manual_rating_column_flows_into_watchlist_top_movers_portfolio_helper():
    history = _entry_history([
        {'Ticker': 'MANUAL', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'rating': 4.0, 'current_pct_raw': 0.10, 'max_pct_raw': 0.20, 'Close < BE': 'No'},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.portfolio_table['Ticker'].tolist() == ['MANUAL']
    assert result.portfolio_table.loc[0, 'Rating'] == '4.0'
    assert result.audit.loc[0, 'Rating Normalized'] == '4'


def test_active_table_excludes_close_below_be_later_failed_rows():
    history = _entry_history([
        {'Ticker': 'HIMS', 'Setup Date': '2026-04-28', 'Trigger': 'VWAP Reclaim', 'Trigger Day': 'Success', 'Current Status': 'Failed D0', 'Close < BE': 'Yes', 'Latest Status Date': '2026-05-04', 'Ticker Latest Bar Date': '2026-05-04', 'Global Latest Bar Date': '2026-05-04', 'current_pct_raw': -0.049, 'max_pct_raw': 0.005},
        {'Ticker': 'OK', 'Setup Date': '2026-04-28', 'Trigger': '1m ORH', 'Trigger Day': 'Success', 'Current Status': 'Active', 'Close < BE': 'No', 'Latest Status Date': '2026-05-04', 'Ticker Latest Bar Date': '2026-05-04', 'Global Latest Bar Date': '2026-05-04', 'current_pct_raw': 0.02, 'max_pct_raw': 0.08},
    ])

    result = top_movers_from_history(history, latest_date='2026-05-04')

    assert result.active_table['Ticker'].tolist() == ['OK']
    assert result.table['Ticker'].tolist() == ['OK', 'HIMS']


def test_audit_keeps_secondary_fields_removed_from_visible_tables():
    result = top_movers_from_history(_history(), latest_date='2026-04-30')

    assert 'Max High' in result.audit.columns
    assert 'Breakeven / D1 Eligible' in result.audit.columns
    assert 'Retest Count' in result.audit.columns
    assert 'Retest Days Raw' in result.audit.columns
    assert 'Retest Dates Raw' in result.audit.columns


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
    history = _entry_history([
        {'Ticker': 'A', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
        {'Ticker': 'B', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.04, 'max_pct_raw': 0.10},
        {'Ticker': 'C', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Failed D1', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.20},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['B', 'A']


def test_active_table_excludes_non_active_statuses():
    history = _entry_history([
        {'Ticker': 'ACTIVE', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Trigger Day': 'Success', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
        {'Ticker': 'LATER', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Trigger Day': 'Success', 'Current Status': 'Failed D2', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.30},
        {'Ticker': 'D1', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Trigger Day': 'Success', 'Current Status': 'Failed D1', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.29},
        {'Ticker': 'DAYFAIL', 'Setup Date': '2026-04-01', 'Trigger': 'Failed OR Trigger', 'Trigger Day': 'Fail', 'Current Status': '—', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.28},
        {'Ticker': 'UNRES', 'Setup Date': '2026-04-01', 'Trigger': 'No Trigger', 'Trigger Day': 'Unresolved', 'Current Status': '—', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.27},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['ACTIVE']


def test_active_table_excludes_stale_active_status_rows():
    history = _entry_history([
        {'Ticker': 'CURRENT', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
        {'Ticker': 'STALE', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-22', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.30},
    ])

    result = top_movers_from_history(history, latest_date='2026-04-30')

    assert result.active_table['Ticker'].tolist() == ['CURRENT']
    assert result.table['Ticker'].tolist() == ['STALE', 'CURRENT']
    assert result.audit.set_index('Ticker').loc['STALE', 'Status Current'] == 'No'
    assert result.audit.set_index('Ticker').loc['STALE', 'Active Table Exclusion Reason'] == 'latest status date older than ticker latest bar date'


def test_active_table_uses_latest_status_when_duplicate_ticker_setup_rows_exist():
    history = _entry_history([
        {'Ticker': 'DUP', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-22', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.08, 'max_pct_raw': 0.30},
        {'Ticker': 'DUP', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Failed D1', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': -0.02, 'max_pct_raw': 0.30},
        {'Ticker': 'OK', 'Setup Date': '2026-04-01', 'Trigger': 'PDH', 'Current Status': 'Active', 'Latest Status Date': '2026-04-30', 'Ticker Latest Bar Date': '2026-04-30', 'Global Latest Bar Date': '2026-04-30', 'current_pct_raw': 0.02, 'max_pct_raw': 0.10},
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
        'Ticker Latest Bar Date': '2026-04-22',
        'Global Latest Bar Date': '2026-05-04',
        'Trigger Level': 7.94,
        'Reference Low': 6.11,
        'Latest Close': 8.43,
        'current_pct_raw': 0.0617,
        'max_pct_raw': 2.0617,
    }])

    result = top_movers_from_history(history, latest_date='2026-05-04')

    assert result.active_table.empty
    assert result.table.loc[0, 'Ticker'] == 'BIRD'


def test_active_table_includes_rows_with_current_ticker_and_global_status_dates():
    history = _entry_history([{
        'Ticker': 'AKAN',
        'Setup Date': '2026-04-28',
        'Trigger': 'PDH',
        'Current Status': 'Active',
        'Latest Status Date': '2026-05-04',
        'Ticker Latest Bar Date': '2026-05-04',
        'Global Latest Bar Date': '2026-05-04',
        'current_pct_raw': 2.038,
        'max_pct_raw': 4.836,
    }])

    result = top_movers_from_history(history, latest_date='2026-05-04')

    assert result.active_table['Ticker'].tolist() == ['AKAN']
    audit = result.audit.set_index('Ticker').loc['AKAN']
    assert audit['Status Current'] == 'Yes'
    assert audit['Active Table Exclusion Reason'] == '-'


def test_active_table_excludes_ticker_not_current_to_global_latest_bar_date():
    history = _entry_history([{
        'Ticker': 'STALE_TICKER',
        'Setup Date': '2026-04-28',
        'Trigger': 'PDH',
        'Current Status': 'Active',
        'Latest Status Date': '2026-04-22',
        'Ticker Latest Bar Date': '2026-04-22',
        'Global Latest Bar Date': '2026-05-04',
        'current_pct_raw': 0.10,
        'max_pct_raw': 0.50,
    }])

    result = top_movers_from_history(history, latest_date='2026-05-04')

    assert result.active_table.empty
    audit = result.audit.set_index('Ticker').loc['STALE_TICKER']
    assert audit['Status Current'] == 'No'
    assert audit['Active Table Exclusion Reason'] == 'ticker latest bar date older than global latest bar date'
