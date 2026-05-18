from __future__ import annotations

import pandas as pd

from src.trigger_event_explorer import (
    DISPLAY_COLUMNS,
    ExplorerFilters,
    active_filter_summary,
    apply_filters,
    csv_bytes,
    dataframe_height,
    explorer_rows,
    option_values,
    summary_cards,
    window_setup_dates,
)


def _history() -> pd.DataFrame:
    rows = []
    triggers = ['PDH', 'VWAP Reclaim', '1m ORH', '5m ORH', 'Alt Required', 'No Trigger']
    statuses = ['Active', 'Failed D0', 'Failed D1', '—']
    days = ['Success', 'Fail', 'Unresolved']
    for index in range(1, 13):
        trigger = triggers[(index - 1) % len(triggers)]
        trigger_day = days[(index - 1) % len(days)]
        if trigger in {'PDH', 'VWAP Reclaim', '1m ORH', '5m ORH', 'Alt Required'} and trigger_day == 'Unresolved':
            trigger_day = 'Success'
        if trigger == 'No Trigger':
            trigger_day = 'Unresolved'
        rows.append({
            'Setup Date': f'2026-05-{index:02d}',
            'Ticker': f'T{index:02d}',
            'Current Status': statuses[(index - 1) % len(statuses)],
            'Trigger Day': trigger_day,
            'Trigger': trigger,
            'PDH': 'success' if trigger == 'PDH' and trigger_day == 'Success' else 'failed' if trigger == 'PDH' else '-' if trigger != 'PDH' else '',
            '1m ORH': 'success' if trigger == '1m ORH' else 'failed' if trigger == 'Alt Required' else '',
            'VWAP Reclaim': 'success' if trigger == 'VWAP Reclaim' else '',
            '5m ORH': 'success' if trigger == '5m ORH' else 'failed' if trigger == 'Alt Required' else '',
            'Notes': '',
            'Current %': f'{index:.1f}%',
            'Max %': f'{index + 10:.1f}%',
            'Close < BE': 'Yes' if index % 2 == 0 else 'No',
            'D3 High %': f'{index + 5:.1f}%',
            'Retests': 'D1' if index % 3 == 0 else '',
            'Setup': '' if index in {4, 10} else 'EP' if index % 2 else 'Pullback',
            'Entry Tactic': '' if index in {5, 11} else 'Bias Flip' if index % 2 else 'Gap Over Range',
            'Rating': str((index % 5) + 1),
            'current_pct_raw': index / 100,
            'max_pct_raw': (index + 10) / 100,
            'd3_high_pct_raw': (index + 5) / 100,
        })
    return pd.DataFrame(rows)


def test_window_setup_dates():
    history = _history()

    assert [d.date().isoformat() for d in window_setup_dates(history, 'Last 5 setup dates')] == [
        '2026-05-08', '2026-05-09', '2026-05-10', '2026-05-11', '2026-05-12'
    ]
    assert [d.date().isoformat() for d in window_setup_dates(history, 'Previous 5 setup dates')] == [
        '2026-05-03', '2026-05-04', '2026-05-05', '2026-05-06', '2026-05-07'
    ]
    assert len(window_setup_dates(history, 'Last 10 setup dates')) == 10
    assert len(window_setup_dates(history, 'Last 20 setup dates')) == 12
    assert len(window_setup_dates(history, 'All')) == 12


def test_filters_and_unclassified_options():
    rows = explorer_rows(_history(), 'All')

    assert 'Unclassified' in option_values(rows, 'Setup')
    assert apply_filters(rows, ExplorerFilters(window='All', trigger='VWAP Reclaim'))['Trigger'].eq('VWAP Reclaim').all()
    assert apply_filters(rows, ExplorerFilters(window='All', trigger_day='Success'))['Trigger Day'].eq('Success').all()
    assert apply_filters(rows, ExplorerFilters(window='All', current_status='Active'))['Current Status'].eq('Active').all()
    assert apply_filters(rows, ExplorerFilters(window='All', setup='Unclassified'))['Setup'].eq('Unclassified').all()
    assert apply_filters(rows, ExplorerFilters(window='All', entry_tactic='Unclassified'))['Entry Tactic'].eq('Unclassified').all()
    assert apply_filters(rows, ExplorerFilters(window='All', close_be='Yes'))['Close < BE'].eq('Yes').all()
    assert apply_filters(rows, ExplorerFilters(window='All', ticker_search='t01'))['Ticker'].tolist() == ['T01']


def test_rating_filters_numeric_filters_summary_and_csv():
    rows = explorer_rows(_history(), 'All')

    four_five = apply_filters(rows, ExplorerFilters(window='All', rating='4-5'))
    assert pd.to_numeric(four_five['Rating']).ge(4).all()
    three_plus = apply_filters(rows, ExplorerFilters(window='All', rating='3+'))
    assert pd.to_numeric(three_plus['Rating']).ge(3).all()
    exact = apply_filters(rows, ExplorerFilters(window='All', rating='5'))
    assert exact['Rating'].eq('5').all()
    current = apply_filters(rows, ExplorerFilters(window='All', min_current_pct=10))
    assert current['Ticker'].tolist() == ['T12', 'T11', 'T10']
    max_rows = apply_filters(rows, ExplorerFilters(window='All', min_max_pct=21))
    assert max_rows['Ticker'].tolist() == ['T12', 'T11']

    cards = {card['Metric']: card['Value'] for card in summary_cards(four_five)}
    assert cards['Rows'] == str(len(four_five))
    assert cards['Triggered'] != ''
    assert cards['Median Max %'].endswith('%') or cards['Median Max %'] == '-'

    exported = csv_bytes(exact).decode('utf-8')
    assert 'T04' in exported
    assert 'T01' not in exported


def test_empty_filtered_result_is_safe():
    rows = apply_filters(explorer_rows(_history(), 'All'), ExplorerFilters(window='All', ticker_search='ZZZ'))

    assert rows.empty
    assert list(rows.columns) == DISPLAY_COLUMNS
    assert summary_cards(rows)[0] == {'Metric': 'Rows', 'Value': '0'}
    assert csv_bytes(rows).decode('utf-8').startswith('Setup Date,Ticker')


def test_active_filter_summary_default_and_non_default_filters():
    assert active_filter_summary(ExplorerFilters()) == 'Active filters: none'

    summary = active_filter_summary(ExplorerFilters(
        window='Last 5 setup dates',
        trigger='VWAP Reclaim',
        trigger_day='Success',
        current_status='Active',
        setup='EP',
        entry_tactic='Bias Flip',
        rating='4-5',
        close_be='Yes',
        ticker_search='ichr',
        min_current_pct=5,
        min_max_pct=10,
    ))

    assert summary == (
        'Active filters: Setup date window = Last 5 setup dates | Trigger = VWAP Reclaim | '
        'Trigger Day = Success | Current Status = Active | Setup = EP | Entry Tactic = Bias Flip | '
        'Rating = 4-5 | Close < BE = Yes | Ticker search = ichr | Min Current % = 5 | Min Max % = 10'
    )


def test_dataframe_height_scales_with_rows():
    assert dataframe_height(0) == 220
    assert dataframe_height(10) == 378
    assert dataframe_height(50) == 1738
