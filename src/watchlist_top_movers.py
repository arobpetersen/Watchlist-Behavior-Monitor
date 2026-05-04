from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.setup_behavior_overview import monitor_history


SETUP_WINDOW_OPTIONS = ['Last 5 setup dates', 'Last 10 setup dates', 'Last 20 setup dates', 'All']
TOP_N_OPTIONS = [10, 20, 50]
SORT_OPTIONS = ['Max %', 'Current %', 'Days Since Setup']
VISIBLE_COLUMNS = [
    'Rank',
    'Ticker',
    'Setup Date',
    'Trigger',
    'Current Status',
    'Current %',
    'Max %',
    'Max High',
    'Days Since Setup',
    'Retested',
    'Breakeven / D1 Eligible',
    'Notes',
]
AUDIT_COLUMNS = [
    'Rank',
    'Ticker',
    'Setup Date',
    'Reference Price',
    'Latest Close',
    'Max Date',
    'D3 High',
    'Setup',
    'Rating',
    'Source',
    'Missing Data Notes',
]


@dataclass(frozen=True)
class TopMoverResult:
    table: pd.DataFrame
    audit: pd.DataFrame


def _display(value: Any) -> str:
    if value is None:
        return '-'
    try:
        if pd.isna(value):
            return '-'
    except TypeError:
        pass
    text = str(value).strip()
    return text if text else '-'


def _first_existing(rows: pd.DataFrame, names: list[str], default: Any = None) -> pd.Series:
    for name in names:
        if name in rows:
            return rows[name]
    return pd.Series(default, index=rows.index)


def _numeric(rows: pd.DataFrame, names: list[str]) -> pd.Series:
    values = _first_existing(rows, names)
    text = values.astype(str)
    numeric = pd.to_numeric(text.str.rstrip('%'), errors='coerce')
    return numeric.where(~text.str.contains('%', regex=False), numeric / 100)


def _fmt_pct(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors='coerce').iloc[0]
    if pd.isna(numeric):
        return '-'
    return f'{numeric * 100:.1f}%'


def _fmt_price(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors='coerce').iloc[0]
    if pd.isna(numeric):
        return '-'
    return f'{numeric:.2f}'


def _window_limit(setup_window: str) -> int | None:
    if setup_window == 'All':
        return None
    if setup_window.startswith('Last 5'):
        return 5
    if setup_window.startswith('Last 10'):
        return 10
    if setup_window.startswith('Last 20'):
        return 20
    return 20


def filter_setup_window(rows: pd.DataFrame, setup_window: str) -> pd.DataFrame:
    if rows.empty or 'Setup Date' not in rows:
        return rows.copy()
    out = rows.copy()
    out['Setup Date'] = pd.to_datetime(out['Setup Date'])
    limit = _window_limit(setup_window)
    if limit is None:
        return out
    setup_dates = sorted(out['Setup Date'].dt.date.dropna().unique())
    included = set(setup_dates[-limit:])
    return out[out['Setup Date'].dt.date.isin(included)].copy()


def latest_market_date(con, fallback_rows: pd.DataFrame | None = None) -> pd.Timestamp | None:
    try:
        row = con.execute('select max(trading_date) from daily_bars').fetchone()
        if row and row[0] is not None:
            return pd.to_datetime(row[0])
    except Exception:
        pass
    if fallback_rows is not None and not fallback_rows.empty and 'Setup Date' in fallback_rows:
        dates = pd.to_datetime(fallback_rows['Setup Date'], errors='coerce').dropna()
        if not dates.empty:
            return pd.to_datetime(dates.max())
    return None


def _days_since(setup_dates: pd.Series, latest_date: pd.Timestamp | None) -> pd.Series:
    dates = pd.to_datetime(setup_dates, errors='coerce')
    if latest_date is None:
        return pd.Series([pd.NA] * len(dates), index=dates.index, dtype='Int64')
    days = (pd.to_datetime(latest_date).normalize() - dates.dt.normalize()).dt.days
    return days.astype('Int64')


def _breakeven_or_d1(rows: pd.DataFrame) -> pd.Series:
    # Rolling Setup Monitor does not expose a formal breakeven field yet. If a
    # future row source supplies one, prefer it; otherwise keep the display
    # intentionally blank rather than inventing management state.
    return _first_existing(
        rows,
        ['Breakeven / D1 Eligible', 'D1 Eligible', 'Breakeven', 'B/E', 'breakeven_d1_eligible'],
        '-',
    )


def _missing_notes(rows: pd.DataFrame) -> pd.Series:
    notes = []
    for _, row in rows.iterrows():
        missing = []
        if pd.isna(row.get('_current_sort')):
            missing.append('Current %')
        if pd.isna(row.get('_max_sort')):
            missing.append('Max %')
        if _display(row.get('Max High')) == '-':
            missing.append('Max High')
        notes.append('Missing: ' + ', '.join(missing) if missing else '-')
    return pd.Series(notes, index=rows.index)


def top_movers_from_history(
    history: pd.DataFrame,
    latest_date: pd.Timestamp | str | None = None,
    setup_window: str = 'Last 20 setup dates',
    top_n: int = 20,
    sort_by: str = 'Max %',
) -> TopMoverResult:
    if history.empty:
        return TopMoverResult(pd.DataFrame(columns=VISIBLE_COLUMNS), pd.DataFrame(columns=AUDIT_COLUMNS))

    rows = filter_setup_window(history, setup_window).copy()
    if rows.empty:
        return TopMoverResult(pd.DataFrame(columns=VISIBLE_COLUMNS), pd.DataFrame(columns=AUDIT_COLUMNS))

    rows['Setup Date'] = pd.to_datetime(rows['Setup Date'])
    rows['_current_sort'] = _numeric(rows, ['current_pct_raw', 'Current %'])
    rows['_max_sort'] = _numeric(rows, ['max_pct_raw', 'Max %'])
    rows['_days_sort'] = _days_since(rows['Setup Date'], pd.to_datetime(latest_date) if latest_date is not None else None)

    rows['Ticker'] = _first_existing(rows, ['Ticker', 'ticker']).apply(_display)
    rows['Trigger'] = _first_existing(rows, ['Trigger', 'trigger_type']).apply(_display)
    rows['Current Status'] = _first_existing(rows, ['Current Status', 'Status', 'status']).apply(_display)
    rows['Current %'] = rows['_current_sort'].apply(_fmt_pct)
    rows['Max %'] = rows['_max_sort'].apply(_fmt_pct)
    rows['Max High'] = _first_existing(rows, ['Max High', 'max_high']).apply(_fmt_price)
    rows['Days Since Setup'] = rows['_days_sort'].apply(lambda v: '-' if pd.isna(v) else int(v))
    rows['Retested'] = _first_existing(rows, ['Retested', 'Retest', 'Retest Day', 'retest_day']).apply(_display)
    rows['Breakeven / D1 Eligible'] = _breakeven_or_d1(rows).apply(_display)
    rows['Notes'] = _first_existing(rows, ['Notes', 'notes']).apply(_display)

    if sort_by == 'Current %':
        sort_cols = ['_current_sort', '_max_sort', 'Setup Date', 'Ticker']
        ascending = [False, False, False, True]
    elif sort_by == 'Days Since Setup':
        sort_cols = ['_days_sort', '_max_sort', 'Setup Date', 'Ticker']
        ascending = [False, False, False, True]
    else:
        sort_cols = ['_max_sort', '_current_sort', 'Setup Date', 'Ticker']
        ascending = [False, False, False, True]
    rows = rows.sort_values(sort_cols, ascending=ascending, na_position='last').head(int(top_n)).copy()
    rows.insert(0, 'Rank', range(1, len(rows) + 1))

    table = rows[VISIBLE_COLUMNS].copy()

    rows['Reference Price'] = _first_existing(rows, ['Trigger Level', 'Reference Price', 'base_price']).apply(_display)
    rows['Latest Close'] = _first_existing(rows, ['Latest Close', 'latest_close']).apply(_display)
    rows['Max Date'] = _first_existing(rows, ['Max Date', 'max_date']).apply(_display)
    rows['D3 High'] = _first_existing(rows, ['D3 High %', 'D3 High', 'd3_high_pct_raw']).apply(_display)
    rows['Setup'] = _first_existing(rows, ['Setup', 'setup']).apply(_display)
    rows['Rating'] = _first_existing(rows, ['Rating', 'rating']).apply(_display)
    rows['Source'] = _first_existing(rows, ['Source', 'source_file', 'Source File']).apply(_display)
    rows['Missing Data Notes'] = _missing_notes(rows)
    audit = rows[AUDIT_COLUMNS].copy()
    return TopMoverResult(table.reset_index(drop=True), audit.reset_index(drop=True))


def load_top_movers(con) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    history = monitor_history(con)
    return history, latest_market_date(con, history)
