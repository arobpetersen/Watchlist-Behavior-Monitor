from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import pandas as pd

from src.setup_behavior_overview import monitor_history, resolve_display_triggers


SETUP_WINDOW_OPTIONS = ['Last 5 setup dates', 'Last 10 setup dates', 'Last 20 setup dates', 'All']
DEFAULT_SETUP_WINDOW = 'All'
TOP_N_OPTIONS = [10, 20, 50]
SORT_OPTIONS = ['Max %', 'Current %', 'Days Since Setup']
PORTFOLIO_VIEW_OPTIONS = ['Current Progress', 'Max Progress']
DEFAULT_PORTFOLIO_VIEW = 'Current Progress'
VISIBLE_COLUMNS = [
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
ACTIVE_VISIBLE_COLUMNS = [
    'Rank',
    'Ticker',
    'Setup Date',
    'Trigger',
    'Entry Ref',
    'Rating',
    'Current %',
    'Max %',
    'Max High',
    'Days Since Setup',
    'Retested',
    'Setup',
    'Entry Tactic',
    'Notes',
]
PORTFOLIO_VISIBLE_COLUMNS = [
    'Rank',
    'Ticker',
    'Setup Date',
    'Trigger',
    'Rating',
    'Current %',
    'Max %',
    'Days Since Setup',
    'Retests',
    'Setup',
    'Entry Tactic',
]
MAX_PORTFOLIO_VISIBLE_COLUMNS = [
    'Rank',
    'Ticker',
    'Setup Date',
    'Trigger',
    'Current Status',
    'Rating',
    'Current %',
    'Max %',
    'Close < BE',
    'Days Since Setup',
    'Retests',
    'Setup',
    'Entry Tactic',
]
AUDIT_COLUMNS = [
    'Rank',
    'Ticker',
    'Setup Date',
    'Entry Ref',
    'Reference Price',
    'Latest Close',
    'Max High',
    'Setup Current %',
    'Setup Max %',
    'Close < BE',
    'Breakeven / D1 Eligible',
    'Latest Status Date',
    'Ticker Latest Bar Date',
    'Global Latest Bar Date',
    'Status Current',
    'Active Table Exclusion Reason',
    'Portfolio Eligible',
    'Portfolio Exclusion Reason',
    'Portfolio View Eligible',
    'Portfolio View Exclusion Reason',
    'Current Progress Eligible',
    'Max Progress Eligible',
    'Retest Count',
    'Retest Days Raw',
    'Retest Dates Raw',
    'Max Date',
    'D3 High',
    'Setup',
    'Entry Tactic',
    'Rating',
    'Rating Normalized',
    'Source',
    'Missing Data Notes',
]
PORTFOLIO_AUDIT_SAMPLE_COLUMNS = [
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


@dataclass(frozen=True)
class TopMoverResult:
    portfolio_table: pd.DataFrame
    active_table: pd.DataFrame
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


def _plain_numeric(rows: pd.DataFrame, names: list[str]) -> pd.Series:
    return pd.to_numeric(_first_existing(rows, names), errors='coerce')


def _coalesced_numeric(rows: pd.DataFrame, names: list[str]) -> pd.Series:
    values = pd.Series(pd.NA, index=rows.index, dtype='Float64')
    for name in names:
        if name in rows:
            values = values.combine_first(pd.to_numeric(rows[name], errors='coerce'))
    return values


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


def _trigger_unavailable(value: Any) -> bool:
    text = _display(value).strip().lower()
    return text in {'-', '—', 'no trigger', 'unavailable', 'none', 'nan'}


def _entry_ref(rows: pd.DataFrame) -> pd.Series:
    trigger = _first_existing(rows, ['Trigger', 'trigger_type']).apply(_display)
    vwap_ref = _coalesced_numeric(
        rows,
        ['VWAP Reclaim Trigger Price', 'Raw VWAP Reclaim Trigger Price', 'vwap_reclaim_trigger_price'],
    )
    standard_ref = _coalesced_numeric(rows, ['Trigger Level', 'trigger_level', 'Reference Price', 'base_price'])
    entry = standard_ref.copy()
    entry = entry.where(~trigger.eq('VWAP Reclaim'), vwap_ref)
    entry = entry.where(~trigger.apply(_trigger_unavailable))
    return entry.where(entry.gt(0))


def _post_trigger_max_high(rows: pd.DataFrame) -> pd.Series:
    return _coalesced_numeric(rows, ['Max High After Trigger', 'max_high_after_trigger', 'post_trigger_max_high'])


def _pct_from_entry(value: pd.Series, entry: pd.Series) -> pd.Series:
    return ((value - entry) / entry).where(entry.gt(0) & value.notna())


def _rating_display(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors='coerce').iloc[0]
    if pd.isna(numeric):
        return '-'
    return str(int(numeric)) if float(numeric).is_integer() else f'{float(numeric):g}'


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


def _format_setup_date(series: pd.Series) -> pd.Series:
    dates = pd.to_datetime(series, errors='coerce')
    return dates.dt.strftime('%Y-%m-%d').fillna('-')


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
        if pd.isna(row.get('_entry_ref')):
            missing.append('Entry Ref')
        if pd.isna(row.get('_latest_close_num')):
            missing.append('Latest Close')
        if pd.isna(row.get('_post_trigger_max_high')):
            missing.append('post-trigger Max High')
        if pd.isna(row.get('_current_sort')):
            missing.append('Current % from entry')
        if pd.isna(row.get('_max_sort')):
            missing.append('Max % from entry')
        notes.append('Missing: ' + ', '.join(missing) if missing else '-')
    return pd.Series(notes, index=rows.index)


def _date_display(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors='coerce').dt.strftime('%Y-%m-%d').fillna('-')


def _date_equal(left: pd.Series, right: pd.Series) -> pd.Series:
    left_dates = pd.to_datetime(left, errors='coerce').dt.normalize()
    right_dates = pd.to_datetime(right, errors='coerce').dt.normalize()
    return left_dates.notna() & right_dates.notna() & left_dates.eq(right_dates)


def _active_exclusion_reasons(rows: pd.DataFrame) -> pd.Series:
    reasons = []
    for _, row in rows.iterrows():
        status = _display(row.get('Current Status'))
        if status != 'Active':
            reasons.append(f'not active: {status}')
        elif pd.isna(row.get('_latest_status_date')):
            reasons.append('missing latest status date')
        elif pd.isna(row.get('_ticker_latest_bar_date')):
            reasons.append('missing ticker latest bar date')
        elif pd.isna(row.get('_global_latest_bar_date')):
            reasons.append('missing global latest bar date')
        elif not bool(row.get('_status_matches_ticker_latest')):
            reasons.append('latest status date older than ticker latest bar date')
        elif not bool(row.get('_ticker_current_to_global')):
            reasons.append('ticker latest bar date older than global latest bar date')
        else:
            reasons.append('-')
    return pd.Series(reasons, index=rows.index)


def _rating_numeric(rows: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(_first_existing(rows, ['Rating', 'rating']), errors='coerce')


def _portfolio_exclusion_reasons(rows: pd.DataFrame) -> pd.Series:
    reasons = []
    for _, row in rows.iterrows():
        row_reasons = []
        status = _display(row.get('Current Status'))
        rating = row.get('_rating_sort')
        if status != 'Active':
            row_reasons.append(f'not active: {status}')
        if not bool(row.get('_status_current')):
            active_reason = _display(row.get('Active Table Exclusion Reason'))
            row_reasons.append('not fresh' if active_reason == '-' else active_reason)
        if pd.isna(rating):
            row_reasons.append('missing rating')
        elif float(rating) < 4:
            row_reasons.append('rating below 4')
        if _display(row.get('Close < BE')) == 'Yes':
            row_reasons.append('close below breakeven')
        if pd.isna(row.get('_current_sort')):
            row_reasons.append('missing Current %')
        if pd.isna(row.get('_max_sort')):
            row_reasons.append('missing Max %')
        reasons.append('; '.join(dict.fromkeys(row_reasons)) if row_reasons else '-')
    return pd.Series(reasons, index=rows.index)


def _max_progress_exclusion_reasons(rows: pd.DataFrame) -> pd.Series:
    reasons = []
    for _, row in rows.iterrows():
        row_reasons = []
        rating = row.get('_rating_sort')
        if pd.isna(rating):
            row_reasons.append('missing rating')
        elif float(rating) < 4:
            row_reasons.append('rating below 4')
        if pd.isna(row.get('_max_sort')):
            row_reasons.append('missing Max %')
        reasons.append('; '.join(dict.fromkeys(row_reasons)) if row_reasons else '-')
    return pd.Series(reasons, index=rows.index)


def _portfolio_columns(portfolio_view: str) -> list[str]:
    return MAX_PORTFOLIO_VISIBLE_COLUMNS if portfolio_view == 'Max Progress' else PORTFOLIO_VISIBLE_COLUMNS


def portfolio_summary(table: pd.DataFrame) -> str:
    if table.empty:
        return ''
    current = _numeric(table, ['Current %'])
    max_pct = _numeric(table, ['Max %'])
    rating = pd.to_numeric(_first_existing(table, ['Rating']), errors='coerce')
    row_count = len(table)
    name_label = 'name' if row_count == 1 else 'names'
    return (
        f'{row_count} {name_label} | '
        f'Avg Current {_fmt_pct(current.mean())} | '
        f'Avg Max {_fmt_pct(max_pct.mean())} | '
        f'{int(rating.eq(5).sum())} rated 5★ | '
        f'{int(rating.eq(4).sum())} rated 4★'
    )


def portfolio_eligibility_funnel(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        counts = [
            ('total rows', 0),
            ('rows with Current Status = Active', 0),
            ('rows with fresh/current status', 0),
            ('rows with Rating present', 0),
            ('rows with Rating 4 or 5', 0),
            ('rows with Close < BE != Yes', 0),
            ('rows with valid Current %', 0),
            ('rows with valid Max %', 0),
            ('final portfolio eligible rows', 0),
        ]
        return pd.DataFrame(counts, columns=['Step', 'Rows'])

    rating = pd.to_numeric(_first_existing(rows, ['_rating_sort', 'Rating', 'rating']), errors='coerce')
    counts = [
        ('total rows', len(rows)),
        ('rows with Current Status = Active', int(_first_existing(rows, ['Current Status']).apply(_display).eq('Active').sum())),
        ('rows with fresh/current status', int(_first_existing(rows, ['_status_current']).fillna(False).astype(bool).sum())),
        ('rows with Rating present', int(rating.notna().sum())),
        ('rows with Rating 4 or 5', int(rating.between(4, 5, inclusive='both').sum())),
        ('rows with Close < BE != Yes', int((~_first_existing(rows, ['Close < BE', 'close_below_be'], '-').apply(_display).eq('Yes')).sum())),
        ('rows with valid Current %', int(pd.to_numeric(_first_existing(rows, ['_current_sort']), errors='coerce').notna().sum())),
        ('rows with valid Max %', int(pd.to_numeric(_first_existing(rows, ['_max_sort']), errors='coerce').notna().sum())),
        ('final portfolio eligible rows', int(_first_existing(rows, ['Portfolio Eligible'], '').apply(_display).eq('Yes').sum())),
    ]
    return pd.DataFrame(counts, columns=['Step', 'Rows'])


def portfolio_exclusion_samples(rows: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=PORTFOLIO_AUDIT_SAMPLE_COLUMNS)
    out = rows[_first_existing(rows, ['Portfolio Eligible'], '').apply(_display).ne('Yes')].copy()
    if out.empty:
        return pd.DataFrame(columns=PORTFOLIO_AUDIT_SAMPLE_COLUMNS)
    if 'Status Current' not in out:
        out['Status Current'] = out.get('_status_current', pd.Series(False, index=out.index)).apply(lambda v: 'Yes' if bool(v) else 'No')
    return out[PORTFOLIO_AUDIT_SAMPLE_COLUMNS].head(int(limit)).reset_index(drop=True)


def hypothetical_optimal_portfolio(rows: pd.DataFrame, limit: int = 8, portfolio_view: str = DEFAULT_PORTFOLIO_VIEW) -> pd.DataFrame:
    columns = _portfolio_columns(portfolio_view)
    if rows.empty:
        return pd.DataFrame(columns=columns)
    eligible_col = 'Max Progress Eligible' if portfolio_view == 'Max Progress' else 'Current Progress Eligible'
    out = rows[rows.get(eligible_col, pd.Series('', index=rows.index)).eq('Yes')].copy()
    if out.empty:
        return pd.DataFrame(columns=columns)
    if portfolio_view == 'Max Progress':
        sort_cols = ['_max_sort', '_current_sort', '_rating_sort', 'Setup Date', 'Ticker']
        ascending = [False, False, False, False, True]
    else:
        sort_cols = ['_current_sort', '_rating_sort', '_max_sort', 'Setup Date', 'Ticker']
        ascending = [False, False, False, False, True]
    out = out.sort_values(
        sort_cols,
        ascending=ascending,
        na_position='last',
    ).head(int(limit)).copy()
    out.insert(0, 'Rank', range(1, len(out) + 1))
    return out[columns].reset_index(drop=True)


def top_movers_from_history(
    history: pd.DataFrame,
    latest_date: pd.Timestamp | str | None = None,
    setup_window: str = DEFAULT_SETUP_WINDOW,
    top_n: int = 20,
    sort_by: str = 'Max %',
    mapped_history: pd.DataFrame | None = None,
    portfolio_view: str = DEFAULT_PORTFOLIO_VIEW,
) -> TopMoverResult:
    portfolio_view = portfolio_view if portfolio_view in PORTFOLIO_VIEW_OPTIONS else DEFAULT_PORTFOLIO_VIEW
    portfolio_columns = _portfolio_columns(portfolio_view)
    if history.empty:
        return TopMoverResult(
            pd.DataFrame(columns=portfolio_columns),
            pd.DataFrame(columns=ACTIVE_VISIBLE_COLUMNS),
            pd.DataFrame(columns=VISIBLE_COLUMNS),
            pd.DataFrame(columns=AUDIT_COLUMNS),
        )

    all_rows = mapped_history.copy() if mapped_history is not None else _mapped_top_mover_rows(history, latest_date)
    _apply_portfolio_view_fields(all_rows, portfolio_view)
    portfolio_table = hypothetical_optimal_portfolio(all_rows, portfolio_view=portfolio_view)
    active_table = _active_top_movers_table(all_rows)

    rows = filter_setup_window(all_rows, setup_window).copy()
    if '_setup_date_display' in rows:
        rows['Setup Date'] = rows['_setup_date_display']
    if rows.empty:
        return TopMoverResult(
            portfolio_table.reset_index(drop=True),
            active_table.reset_index(drop=True),
            pd.DataFrame(columns=VISIBLE_COLUMNS),
            pd.DataFrame(columns=AUDIT_COLUMNS),
        )

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
    audit = _audit_table(rows)
    return TopMoverResult(portfolio_table.reset_index(drop=True), active_table.reset_index(drop=True), table.reset_index(drop=True), audit.reset_index(drop=True))


def prepare_top_mover_rows(history: pd.DataFrame, latest_date: pd.Timestamp | str | None = None) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    return _mapped_top_mover_rows(history, latest_date)


def _mapped_top_mover_rows(rows: pd.DataFrame, latest_date: pd.Timestamp | str | None) -> pd.DataFrame:
    rows = resolve_display_triggers(rows.copy())
    rows['Setup Date'] = pd.to_datetime(rows['Setup Date'])
    rows['_setup_date_display'] = _format_setup_date(rows['Setup Date'])
    rows['_setup_current_sort'] = _numeric(rows, ['current_pct_raw', 'Current %'])
    rows['_setup_max_sort'] = _numeric(rows, ['max_pct_raw', 'Max %'])
    rows['_whole_window_max_high'] = _coalesced_numeric(rows, ['Max High', 'max_high'])
    rows['_entry_ref'] = _entry_ref(rows)
    rows['_latest_close_num'] = _coalesced_numeric(rows, ['Latest Close', 'latest_close'])
    rows['_post_trigger_max_high'] = _post_trigger_max_high(rows)
    rows['_current_sort'] = _pct_from_entry(rows['_latest_close_num'], rows['_entry_ref'])
    entry_max_sort = _pct_from_entry(rows['_post_trigger_max_high'], rows['_entry_ref'])
    rows['_max_sort'] = entry_max_sort.combine_first(rows['_setup_max_sort'])
    rows['_display_max_high'] = rows['_post_trigger_max_high'].combine_first(rows['_whole_window_max_high'])
    rows['_days_sort'] = _days_since(rows['Setup Date'], pd.to_datetime(latest_date) if latest_date is not None else None)
    latest_status_dates = pd.to_datetime(
        _first_existing(rows, ['latest_trading_date_raw', 'Latest Status Date', 'latest_trading_date']),
        errors='coerce',
    )
    latest_market_date = pd.to_datetime(latest_date, errors='coerce') if latest_date is not None else pd.NaT
    ticker_latest_source_exists = any(name in rows for name in ['ticker_latest_bar_date', 'Ticker Latest Bar Date'])
    ticker_latest_dates = pd.to_datetime(
        _first_existing(rows, ['ticker_latest_bar_date', 'Ticker Latest Bar Date']),
        errors='coerce',
    )
    if not ticker_latest_source_exists and not pd.isna(latest_market_date):
        ticker_latest_dates = pd.Series(latest_market_date, index=rows.index)
    global_latest_source_exists = any(name in rows for name in ['global_latest_bar_date', 'Global Latest Bar Date'])
    global_latest_dates = pd.to_datetime(
        _first_existing(rows, ['global_latest_bar_date', 'Global Latest Bar Date']),
        errors='coerce',
    )
    if not global_latest_source_exists and not pd.isna(latest_market_date):
        global_latest_dates = pd.Series(latest_market_date, index=rows.index)
    rows['_latest_status_date'] = latest_status_dates
    rows['_ticker_latest_bar_date'] = ticker_latest_dates
    rows['_global_latest_bar_date'] = global_latest_dates
    rows['_status_matches_ticker_latest'] = _date_equal(latest_status_dates, ticker_latest_dates)
    rows['_ticker_current_to_global'] = _date_equal(ticker_latest_dates, global_latest_dates)
    rows['_status_current'] = rows['_status_matches_ticker_latest'] & rows['_ticker_current_to_global']
    rows['_rating_sort'] = _rating_numeric(rows)

    rows['Ticker'] = _first_existing(rows, ['Ticker', 'ticker']).apply(_display)
    rows['Trigger'] = _first_existing(rows, ['Trigger', 'trigger_type']).apply(_display)
    rows['Current Status'] = _first_existing(rows, ['Current Status', 'Status', 'status']).apply(_display)
    rows['Entry Ref'] = rows['_entry_ref'].apply(_fmt_price)
    rows['Current %'] = rows['_current_sort'].apply(_fmt_pct)
    rows['Max %'] = rows['_max_sort'].apply(_fmt_pct)
    rows['Max High'] = rows['_display_max_high'].apply(_fmt_price)
    rows['Close < BE'] = _first_existing(rows, ['Close < BE', 'close_below_be'], '-').apply(_display)
    rows['Days Since Setup'] = rows['_days_sort'].apply(lambda v: '-' if pd.isna(v) else int(v))
    rows['Retests'] = _first_existing(rows, ['Retests', 'Retested', 'Retest', 'Retest Day', 'retest_day']).apply(_display)
    rows['Retested'] = rows['Retests']
    rows['Breakeven / D1 Eligible'] = _breakeven_or_d1(rows).apply(_display)
    rows['Notes'] = _first_existing(rows, ['Notes', 'notes']).apply(_display)
    rows['Setup'] = _first_existing(rows, ['Setup', 'setup']).apply(_display)
    rows['Entry Tactic'] = _first_existing(rows, ['Entry Tactic', 'entry_tactic']).apply(_display)
    rows['Rating'] = _first_existing(rows, ['Rating', 'rating']).apply(_display)
    rows['Rating Normalized'] = rows['_rating_sort'].apply(_rating_display)
    rows['Setup Date'] = rows['_setup_date_display']
    rows['Active Table Exclusion Reason'] = _active_exclusion_reasons(rows)
    rows['Portfolio Exclusion Reason'] = _portfolio_exclusion_reasons(rows)
    rows['Portfolio Eligible'] = rows['Portfolio Exclusion Reason'].eq('-').map(lambda value: 'Yes' if value else 'No')
    rows['Current Progress Eligible'] = rows['Portfolio Eligible']
    rows['Max Progress Exclusion Reason'] = _max_progress_exclusion_reasons(rows)
    rows['Max Progress Eligible'] = rows['Max Progress Exclusion Reason'].eq('-').map(lambda value: 'Yes' if value else 'No')
    _apply_portfolio_view_fields(rows, DEFAULT_PORTFOLIO_VIEW)
    return rows


def _apply_portfolio_view_fields(rows: pd.DataFrame, portfolio_view: str) -> None:
    if portfolio_view == 'Max Progress':
        rows['Portfolio View Eligible'] = _first_existing(rows, ['Max Progress Eligible']).apply(_display)
        rows['Portfolio View Exclusion Reason'] = _first_existing(rows, ['Max Progress Exclusion Reason']).apply(_display)
    else:
        rows['Portfolio View Eligible'] = _first_existing(rows, ['Current Progress Eligible', 'Portfolio Eligible']).apply(_display)
        rows['Portfolio View Exclusion Reason'] = _first_existing(rows, ['Portfolio Exclusion Reason']).apply(_display)


def _active_top_movers_table(rows: pd.DataFrame) -> pd.DataFrame:
    active_rows = rows[rows['Current Status'].eq('Active') & rows['_status_current'].fillna(False)].copy()
    active_rows = active_rows.sort_values(
        ['_current_sort', '_rating_sort', '_max_sort', 'Setup Date', 'Ticker'],
        ascending=[False, False, False, False, True],
        na_position='last',
    ).head(10).copy()
    active_rows.insert(0, 'Rank', range(1, len(active_rows) + 1))
    return active_rows[ACTIVE_VISIBLE_COLUMNS].copy()


def _audit_table(rows: pd.DataFrame) -> pd.DataFrame:
    rows = rows.copy()
    rows['Entry Ref'] = rows['_entry_ref'].apply(_fmt_price)
    rows['Reference Price'] = _first_existing(rows, ['Trigger Level', 'Reference Price', 'base_price']).apply(_display)
    rows['Latest Close'] = _first_existing(rows, ['Latest Close', 'latest_close']).apply(_display)
    rows['Max High'] = rows['_whole_window_max_high'].apply(_fmt_price)
    rows['Setup Current %'] = rows['_setup_current_sort'].apply(_fmt_pct)
    rows['Setup Max %'] = rows['_setup_max_sort'].apply(_fmt_pct)
    rows['Close < BE'] = _first_existing(rows, ['Close < BE', 'close_below_be'], '-').apply(_display)
    rows['Breakeven / D1 Eligible'] = _breakeven_or_d1(rows).apply(_display)
    rows['Latest Status Date'] = _date_display(rows['_latest_status_date'])
    rows['Ticker Latest Bar Date'] = _date_display(rows['_ticker_latest_bar_date'])
    rows['Global Latest Bar Date'] = _date_display(rows['_global_latest_bar_date'])
    rows['Status Current'] = rows['_status_current'].apply(lambda v: 'Yes' if bool(v) else 'No')
    rows['Active Table Exclusion Reason'] = _first_existing(rows, ['Active Table Exclusion Reason']).apply(_display)
    rows['Portfolio Eligible'] = _first_existing(rows, ['Portfolio Eligible']).apply(_display)
    rows['Portfolio Exclusion Reason'] = _first_existing(rows, ['Portfolio Exclusion Reason']).apply(_display)
    rows['Portfolio View Eligible'] = _first_existing(rows, ['Portfolio View Eligible']).apply(_display)
    rows['Portfolio View Exclusion Reason'] = _first_existing(rows, ['Portfolio View Exclusion Reason']).apply(_display)
    rows['Current Progress Eligible'] = _first_existing(rows, ['Current Progress Eligible']).apply(_display)
    rows['Max Progress Eligible'] = _first_existing(rows, ['Max Progress Eligible']).apply(_display)
    rows['Retest Count'] = _first_existing(rows, ['Retest Count', 'retest_count']).apply(_display)
    rows['Retest Days Raw'] = _first_existing(rows, ['Retest Days Raw', 'retest_days_raw']).apply(_display)
    rows['Retest Dates Raw'] = _first_existing(rows, ['Retest Dates Raw', 'retest_dates_raw']).apply(_display)
    rows['Max Date'] = _first_existing(rows, ['Max Date', 'max_date']).apply(_display)
    rows['D3 High'] = _first_existing(rows, ['D3 High %', 'D3 High', 'd3_high_pct_raw']).apply(_display)
    rows['Setup'] = _first_existing(rows, ['Setup', 'setup']).apply(_display)
    rows['Entry Tactic'] = _first_existing(rows, ['Entry Tactic', 'entry_tactic']).apply(_display)
    rows['Rating'] = _first_existing(rows, ['Rating', 'rating']).apply(_display)
    rows['Rating Normalized'] = _first_existing(rows, ['Rating Normalized']).apply(_display)
    rows['Source'] = _first_existing(rows, ['Source', 'source_file', 'Source File']).apply(_display)
    rows['Missing Data Notes'] = _missing_notes(rows)
    return rows[AUDIT_COLUMNS].copy()


def load_top_movers(con, history: pd.DataFrame | None = None, perf=None) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    if history is None:
        start = perf_counter()
        history = monitor_history(con, perf=perf)
        if perf is not None:
            perf.add('Top Movers monitor_history build', perf_counter() - start)
    start = perf_counter()
    latest = latest_market_date(con, history)
    if perf is not None:
        perf.add('Top Movers SQL: latest market date', perf_counter() - start)
    if not history.empty and 'Ticker' in history:
        tickers = history['Ticker'].dropna().astype(str).unique().tolist()
        if tickers:
            try:
                start = perf_counter()
                latest_by_ticker = con.execute(
                    f"""
                    select ticker, max(trading_date) as ticker_latest_bar_date
                    from daily_bars
                    where ticker in ({','.join(['?'] * len(tickers))})
                    group by ticker
                    """,
                    tickers,
                ).df()
                if perf is not None:
                    perf.add('Top Movers SQL: ticker latest dates', perf_counter() - start)
                history = history.merge(latest_by_ticker, how='left', left_on='Ticker', right_on='ticker')
                history = history.drop(columns=['ticker'], errors='ignore')
            except Exception:
                history['ticker_latest_bar_date'] = pd.NaT
        else:
            history['ticker_latest_bar_date'] = pd.NaT
        history['global_latest_bar_date'] = latest
    return history, latest
