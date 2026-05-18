from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.setup_behavior_overview import DETAIL_COLUMNS, OverviewWindow, detail_rows


WINDOW_OPTIONS = ['Last 5 setup dates', 'Previous 5 setup dates', 'Last 10 setup dates', 'Last 20 setup dates', 'All']
DEFAULT_WINDOW = 'Last 10 setup dates'
TRIGGER_ORDER = ['All', 'PDH', 'VWAP Reclaim', '1m ORH', '5m ORH', 'Alt Required', 'No Trigger']
TRIGGER_DAY_OPTIONS = ['All', 'Success', 'Fail', 'Unresolved']
CURRENT_STATUS_OPTIONS = ['All', 'Active', 'D0 Fail', 'Failed After D0', 'Unresolved / blank']
RATING_OPTIONS = ['All', '4-5', '3+']
CLOSE_BE_OPTIONS = ['All', 'Yes', 'No']
SORT_OPTIONS = ['Setup Date', 'Max %', 'Current %', 'Ticker']

DISPLAY_COLUMNS = [
    'Setup Date',
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
    'D3 High',
    'Retests',
    'Setup',
    'Entry Tactic',
    'Rating',
]


@dataclass(frozen=True)
class ExplorerFilters:
    window: str = DEFAULT_WINDOW
    trigger: str = 'All'
    trigger_day: str = 'All'
    current_status: str = 'All'
    setup: str = 'All'
    entry_tactic: str = 'All'
    rating: str = 'All'
    close_be: str = 'All'
    ticker_search: str = ''
    min_current_pct: float | None = None
    min_max_pct: float | None = None
    sort_by: str = 'Setup Date'


def _display(value: Any) -> str:
    if value is None:
        return 'Unclassified'
    try:
        if pd.isna(value):
            return 'Unclassified'
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text not in {'-', '—', 'nan'} else 'Unclassified'


def _pct_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.fillna('').astype(str).str.replace('%', '', regex=False).str.strip(), errors='coerce')


def setup_date_values(history: pd.DataFrame) -> list[pd.Timestamp]:
    if history is None or history.empty or 'Setup Date' not in history:
        return []
    return sorted(pd.to_datetime(history['Setup Date']).dropna().dt.normalize().unique())


def window_setup_dates(history: pd.DataFrame, window: str) -> tuple[pd.Timestamp, ...]:
    dates = setup_date_values(history)
    if window == 'Last 5 setup dates':
        selected = dates[-5:]
    elif window == 'Previous 5 setup dates':
        selected = dates[-10:-5]
    elif window == 'Last 20 setup dates':
        selected = dates[-20:]
    elif window == 'All':
        selected = dates
    else:
        selected = dates[-10:]
    return tuple(pd.Timestamp(value) for value in selected)


def explorer_rows(history: pd.DataFrame, window: str = DEFAULT_WINDOW) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)
    dates = window_setup_dates(history, window)
    if not dates:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)
    rows = detail_rows(history, OverviewWindow(window, dates)).rename(columns={'Current': 'Current %', 'Max': 'Max %'})
    for column in DISPLAY_COLUMNS:
        if column not in rows:
            rows[column] = ''
    rows = rows[DISPLAY_COLUMNS].copy()
    rows['Setup'] = rows['Setup'].apply(_display)
    rows['Entry Tactic'] = rows['Entry Tactic'].apply(_display)
    return default_sort(rows)


def option_values(rows: pd.DataFrame, column: str) -> list[str]:
    if rows is None or rows.empty or column not in rows:
        return ['All']
    values = sorted({_display(value) for value in rows[column].tolist()})
    return ['All', *values]


def rating_filter_values(rows: pd.DataFrame) -> list[str]:
    values = [] if rows is None or rows.empty or 'Rating' not in rows else sorted({str(v).strip() for v in rows['Rating'].tolist() if str(v).strip() not in {'', '-', '—', 'nan'}})
    return [*RATING_OPTIONS, *values]


def apply_filters(rows: pd.DataFrame, filters: ExplorerFilters) -> pd.DataFrame:
    if rows is None or rows.empty:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)
    out = rows.copy()

    if filters.trigger != 'All' and 'Trigger' in out:
        out = out[out['Trigger'].fillna('').astype(str).eq(filters.trigger)]
    if filters.trigger_day != 'All' and 'Trigger Day' in out:
        out = out[out['Trigger Day'].fillna('').astype(str).eq(filters.trigger_day)]
    if filters.current_status != 'All' and 'Current Status' in out:
        status = out['Current Status'].fillna('').astype(str)
        trigger_day = out['Trigger Day'].fillna('').astype(str) if 'Trigger Day' in out else pd.Series('', index=out.index)
        if filters.current_status == 'Active':
            out = out[status.eq('Active')]
        elif filters.current_status == 'D0 Fail':
            out = out[status.eq('Failed D0') | trigger_day.eq('Fail')]
        elif filters.current_status == 'Failed After D0':
            out = out[status.str.match(r'^Failed D[1-9]\d*$', na=False)]
        elif filters.current_status == 'Unresolved / blank':
            out = out[trigger_day.eq('Unresolved') | status.isin(['', '-', '—', 'Unclassified'])]
    if filters.setup != 'All' and 'Setup' in out:
        out = out[out['Setup'].apply(_display).eq(filters.setup)]
    if filters.entry_tactic != 'All' and 'Entry Tactic' in out:
        out = out[out['Entry Tactic'].apply(_display).eq(filters.entry_tactic)]
    if filters.rating != 'All' and 'Rating' in out:
        rating = pd.to_numeric(out['Rating'], errors='coerce')
        if filters.rating == '4-5':
            out = out[rating.ge(4)]
        elif filters.rating == '3+':
            out = out[rating.ge(3)]
        else:
            out = out[out['Rating'].fillna('').astype(str).str.strip().eq(filters.rating)]
    if filters.close_be != 'All' and 'Close < BE' in out:
        out = out[out['Close < BE'].fillna('').astype(str).str.casefold().eq(filters.close_be.casefold())]
    if filters.ticker_search and 'Ticker' in out:
        query = filters.ticker_search.strip()
        if query:
            out = out[out['Ticker'].fillna('').astype(str).str.contains(query, case=False, na=False, regex=False)]
    if filters.min_current_pct is not None and 'Current %' in out:
        out = out[_pct_numeric(out['Current %']).ge(filters.min_current_pct)]
    if filters.min_max_pct is not None and 'Max %' in out:
        out = out[_pct_numeric(out['Max %']).ge(filters.min_max_pct)]
    return default_sort(out, filters.sort_by)


def default_sort(rows: pd.DataFrame, sort_by: str = 'Setup Date') -> pd.DataFrame:
    if rows is None or rows.empty:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)
    out = rows.copy()
    out['_setup_date_sort'] = pd.to_datetime(out['Setup Date'], errors='coerce')
    out['_trigger_day_sort'] = out['Trigger Day'].map({'Success': 0, 'Fail': 1, 'Unresolved': 2}).fillna(3)
    out['_status_sort'] = out['Current Status'].map({'Active': 0}).fillna(1)
    out['_max_sort'] = _pct_numeric(out['Max %'])
    out['_current_sort'] = _pct_numeric(out['Current %'])
    if sort_by == 'Max %':
        sort_cols, ascending = ['_max_sort', '_setup_date_sort', 'Ticker'], [False, False, True]
    elif sort_by == 'Current %':
        sort_cols, ascending = ['_current_sort', '_setup_date_sort', 'Ticker'], [False, False, True]
    elif sort_by == 'Ticker':
        sort_cols, ascending = ['Ticker', '_setup_date_sort'], [True, False]
    else:
        sort_cols, ascending = ['_setup_date_sort', '_trigger_day_sort', '_status_sort', '_max_sort', 'Ticker'], [False, True, True, False, True]
    out = out.sort_values(sort_cols, ascending=ascending, na_position='last')
    return out[[column for column in DISPLAY_COLUMNS if column in out]]


def summary_cards(rows: pd.DataFrame) -> list[dict[str, str]]:
    if rows is None or rows.empty:
        return [
            {'Metric': 'Rows', 'Value': '0'},
            {'Metric': 'Triggered', 'Value': '0'},
            {'Metric': 'Success %', 'Value': '-'},
            {'Metric': 'Active', 'Value': '0'},
            {'Metric': 'Failed After D0', 'Value': '0'},
            {'Metric': 'Median Max %', 'Value': '-'},
        ]
    total = len(rows)
    trigger_day = rows['Trigger Day'].fillna('').astype(str) if 'Trigger Day' in rows else pd.Series('', index=rows.index)
    status = rows['Current Status'].fillna('').astype(str) if 'Current Status' in rows else pd.Series('', index=rows.index)
    triggered = trigger_day.isin(['Success', 'Fail'])
    success = trigger_day.eq('Success')
    triggered_count = int(triggered.sum())
    success_count = int(success.sum())
    success_pct = '-' if triggered_count == 0 else f'{round(success_count / triggered_count * 100)}%'
    median_max = _pct_numeric(rows['Max %']).median() if 'Max %' in rows else pd.NA
    median_max_text = '-' if pd.isna(median_max) else f'{float(median_max):.1f}%'
    return [
        {'Metric': 'Rows', 'Value': str(total)},
        {'Metric': 'Triggered', 'Value': str(triggered_count)},
        {'Metric': 'Success %', 'Value': f'{success_pct} ({success_count}/{triggered_count})' if triggered_count else '-'},
        {'Metric': 'Active', 'Value': str(int(status.eq('Active').sum()))},
        {'Metric': 'Failed After D0', 'Value': str(int(status.str.match(r'^Failed D[1-9]\d*$', na=False).sum()))},
        {'Metric': 'Median Max %', 'Value': median_max_text},
    ]


def active_filter_summary(filters: ExplorerFilters) -> str:
    parts = []
    if filters.window != DEFAULT_WINDOW:
        parts.append(f'Setup date window = {filters.window}')
    if filters.trigger != 'All':
        parts.append(f'Trigger = {filters.trigger}')
    if filters.trigger_day != 'All':
        parts.append(f'Trigger Day = {filters.trigger_day}')
    if filters.current_status != 'All':
        parts.append(f'Current Status = {filters.current_status}')
    if filters.setup != 'All':
        parts.append(f'Setup = {filters.setup}')
    if filters.entry_tactic != 'All':
        parts.append(f'Entry Tactic = {filters.entry_tactic}')
    if filters.rating != 'All':
        parts.append(f'Rating = {filters.rating}')
    if filters.close_be != 'All':
        parts.append(f'Close < BE = {filters.close_be}')
    query = filters.ticker_search.strip()
    if query:
        parts.append(f'Ticker search = {query}')
    if filters.min_current_pct is not None:
        parts.append(f'Min Current % = {filters.min_current_pct:g}')
    if filters.min_max_pct is not None:
        parts.append(f'Min Max % = {filters.min_max_pct:g}')
    if not parts:
        return 'Active filters: none'
    return 'Active filters: ' + ' | '.join(parts)


def dataframe_height(row_count: int, row_height: int = 34, header_height: int = 38, minimum: int = 220) -> int:
    return max(int(minimum), int(header_height) + max(int(row_count), 1) * int(row_height))


def csv_bytes(rows: pd.DataFrame) -> bytes:
    table = rows if rows is not None else pd.DataFrame(columns=DISPLAY_COLUMNS)
    return table.to_csv(index=False).encode('utf-8')
