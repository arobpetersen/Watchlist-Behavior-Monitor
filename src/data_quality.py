from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


PARTIAL_INTRADAY_COLUMNS = [
    'Ticker',
    'Trading Date',
    'Bar Count',
    'First Timestamp',
    'Last Timestamp',
    'Very Low Bar Count',
    'Missing Open Period',
    'Missing Late Session',
    'Reasons',
]

CANDIDATE_DUPLICATE_COLUMNS = [
    'Setup Date',
    'Ticker',
    'Source File',
    'Rows',
]

ACTIVE_DAILY_BAR_COVERAGE_COLUMNS = [
    'Ticker',
    'Setup Date',
    'Ticker Latest Bar Date',
    'Global Latest Bar Date',
    'Stale Trading-Day Gap',
]


@dataclass(frozen=True)
class DataHealthSummary:
    status: str
    latest_setup_date: str
    latest_daily_bar_date: str
    latest_intraday_bar_date: str
    candidate_rows: int
    duplicate_candidate_key_count: int
    partial_intraday_session_count: int
    reason: str = ''
    active_row_count: int = 0
    active_missing_latest_daily_bar_count: int = 0
    active_max_stale_trading_day_gap: int = 0
    active_stale_daily_bar_rows: pd.DataFrame | None = None
    active_daily_bar_coverage_source: str = ''


def duplicate_candidate_keys(con) -> pd.DataFrame:
    rows = con.execute(
        """
        select cast(watchlist_date as varchar) as setup_date,
               ticker,
               source_file,
               count(*) as rows
        from watchlist_candidates
        where watchlist_date is not null
          and ticker is not null
          and source_file is not null
        group by watchlist_date, ticker, source_file
        having count(*) > 1
        order by watchlist_date, ticker, source_file
        """
    ).df()
    if rows.empty:
        return pd.DataFrame(columns=CANDIDATE_DUPLICATE_COLUMNS)
    rows = rows.rename(columns={
        'setup_date': 'Setup Date',
        'ticker': 'Ticker',
        'source_file': 'Source File',
        'rows': 'Rows',
    })
    return rows[CANDIDATE_DUPLICATE_COLUMNS]


def _fmt_ts(value: Any) -> str:
    parsed = pd.to_datetime(value, errors='coerce')
    if pd.isna(parsed):
        return '-'
    return parsed.strftime('%Y-%m-%d %H:%M')


def partial_intraday_sessions(
    bars: pd.DataFrame,
    min_regular_session_bars: int = 300,
) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(columns=PARTIAL_INTRADAY_COLUMNS)
    required = {'ticker', 'trading_date', 'timestamp_et'}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f'intraday bars missing columns: {", ".join(sorted(missing))}')

    df = bars.copy()
    df['timestamp_et'] = pd.to_datetime(df['timestamp_et'], errors='coerce')
    df = df.dropna(subset=['timestamp_et'])
    if df.empty:
        return pd.DataFrame(columns=PARTIAL_INTRADAY_COLUMNS)
    df['time'] = df['timestamp_et'].dt.time

    out = []
    for (ticker, trading_date), group in df.groupby(['ticker', 'trading_date'], dropna=False):
        group = group.sort_values('timestamp_et')
        bar_count = len(group)
        open_period = group[
            (group['time'] >= pd.Timestamp('09:30').time())
            & (group['time'] < pd.Timestamp('09:35').time())
        ]
        late_session = group[
            (group['time'] >= pd.Timestamp('15:55').time())
            & (group['time'] <= pd.Timestamp('16:00').time())
        ]
        low_count = bar_count < min_regular_session_bars
        missing_open = open_period.empty
        missing_late = late_session.empty
        reasons = []
        if low_count:
            reasons.append('very low bar count')
        if missing_open:
            reasons.append('missing open-period bars')
        if missing_late:
            reasons.append('missing late-session bars')
        if not reasons:
            continue
        out.append({
            'Ticker': str(ticker),
            'Trading Date': str(pd.to_datetime(trading_date).date()),
            'Bar Count': bar_count,
            'First Timestamp': _fmt_ts(group['timestamp_et'].iloc[0]),
            'Last Timestamp': _fmt_ts(group['timestamp_et'].iloc[-1]),
            'Very Low Bar Count': low_count,
            'Missing Open Period': missing_open,
            'Missing Late Session': missing_late,
            'Reasons': '; '.join(reasons),
        })
    return pd.DataFrame(out, columns=PARTIAL_INTRADAY_COLUMNS)


def partial_intraday_sessions_from_db(con, min_regular_session_bars: int = 300) -> pd.DataFrame:
    bars = con.execute(
        """
        select ticker, trading_date, timestamp_et
        from intraday_bars_1m
        where ticker is not null
          and trading_date is not null
          and timestamp_et is not null
        """
    ).df()
    return partial_intraday_sessions(bars, min_regular_session_bars=min_regular_session_bars)


def _empty_active_daily_bar_coverage() -> pd.DataFrame:
    return pd.DataFrame(columns=ACTIVE_DAILY_BAR_COVERAGE_COLUMNS)


def _coverage_rows_from_history(history: pd.DataFrame | None) -> pd.DataFrame:
    if history is None or history.empty or 'Current Status' not in history:
        return pd.DataFrame(columns=['Ticker', 'Setup Date'])
    active = history[history['Current Status'].fillna('').astype(str).str.strip().eq('Active')].copy()
    if active.empty or 'Ticker' not in active:
        return pd.DataFrame(columns=['Ticker', 'Setup Date'])
    out = active[['Ticker']].copy()
    out['Ticker'] = out['Ticker'].astype(str)
    out['Setup Date'] = (
        pd.to_datetime(active['Setup Date'], errors='coerce').dt.strftime('%Y-%m-%d')
        if 'Setup Date' in active
        else ''
    )
    return out[['Ticker', 'Setup Date']]


def _coverage_rows_from_candidates(con) -> pd.DataFrame:
    try:
        rows = con.execute(
            """
            select ticker as "Ticker",
                   cast(watchlist_date as varchar) as "Setup Date"
            from watchlist_candidates
            where ticker is not null
              and watchlist_date is not null
            order by watchlist_date, ticker
            """
        ).df()
    except Exception:
        return pd.DataFrame(columns=['Ticker', 'Setup Date'])
    if rows.empty:
        return pd.DataFrame(columns=['Ticker', 'Setup Date'])
    rows['Ticker'] = rows['Ticker'].astype(str)
    rows['Setup Date'] = pd.to_datetime(rows['Setup Date'], errors='coerce').dt.strftime('%Y-%m-%d')
    return rows[['Ticker', 'Setup Date']]


def _coverage_rows(
    con,
    history: pd.DataFrame | None = None,
    allow_monitor_history: bool = False,
) -> tuple[pd.DataFrame, str]:
    if history is not None:
        return _coverage_rows_from_history(history), 'Canonical monitor history'
    if allow_monitor_history:
        try:
            from src.setup_behavior_overview import monitor_history

            return _coverage_rows_from_history(monitor_history(con)), 'Canonical monitor history'
        except Exception:
            return pd.DataFrame(columns=['Ticker', 'Setup Date']), 'Canonical monitor history unavailable'
    return _coverage_rows_from_candidates(con), 'Watchlist candidates (fast coverage check)'


def _active_daily_bar_coverage(
    con,
    history: pd.DataFrame | None = None,
    limit: int = 10,
    allow_monitor_history: bool = False,
) -> tuple[int, int, int, pd.DataFrame, str]:
    """Diagnostic coverage check for active/candidate rows against latest daily bars."""
    active, source = _coverage_rows(con, history=history, allow_monitor_history=allow_monitor_history)
    active_count = len(active)
    if active.empty or 'Ticker' not in active:
        return active_count, 0, 0, _empty_active_daily_bar_coverage(), source

    try:
        latest_global = _scalar(con, 'select max(trading_date) from daily_bars')
        ticker_latest = con.execute(
            """
            select ticker, max(trading_date) as ticker_latest_bar_date
            from daily_bars
            where ticker is not null
            group by ticker
            """
        ).df()
        trading_calendar = con.execute(
            """
            select distinct trading_date
            from daily_bars
            where trading_date is not null
            order by trading_date
            """
        ).df()
    except Exception:
        return active_count, 0, 0, _empty_active_daily_bar_coverage(), source

    if latest_global is None:
        return active_count, active_count, 0, _empty_active_daily_bar_coverage(), source

    latest_global_ts = pd.to_datetime(latest_global, errors='coerce')
    if pd.isna(latest_global_ts):
        return active_count, active_count, 0, _empty_active_daily_bar_coverage(), source

    out = active[['Ticker', 'Setup Date']].copy()
    ticker_latest = ticker_latest.rename(columns={'ticker': 'Ticker'})
    out = out.merge(ticker_latest, how='left', on='Ticker')
    out['Ticker Latest Bar Date'] = pd.to_datetime(out['ticker_latest_bar_date'], errors='coerce')
    out['Global Latest Bar Date'] = latest_global_ts

    calendar = pd.to_datetime(trading_calendar.get('trading_date', pd.Series(dtype=object)), errors='coerce').dropna().dt.normalize()
    latest_norm = latest_global_ts.normalize()

    def stale_gap(value) -> int:
        ticker_date = pd.to_datetime(value, errors='coerce')
        if pd.isna(ticker_date):
            return int(calendar.le(latest_norm).sum())
        ticker_norm = ticker_date.normalize()
        if ticker_norm >= latest_norm:
            return 0
        return int((calendar.gt(ticker_norm) & calendar.le(latest_norm)).sum())

    out['Stale Trading-Day Gap'] = out['Ticker Latest Bar Date'].apply(stale_gap)
    stale = out[out['Stale Trading-Day Gap'].gt(0)].copy()
    missing_count = len(stale)
    max_gap = int(stale['Stale Trading-Day Gap'].max()) if not stale.empty else 0
    if stale.empty:
        return active_count, 0, 0, _empty_active_daily_bar_coverage(), source

    stale['Ticker Latest Bar Date'] = stale['Ticker Latest Bar Date'].dt.strftime('%Y-%m-%d').fillna('-')
    stale['Global Latest Bar Date'] = stale['Global Latest Bar Date'].dt.strftime('%Y-%m-%d').fillna('-')
    stale = stale.sort_values(['Stale Trading-Day Gap', 'Ticker', 'Setup Date'], ascending=[False, True, True])
    return (
        active_count,
        missing_count,
        max_gap,
        stale[ACTIVE_DAILY_BAR_COVERAGE_COLUMNS].head(int(limit)).reset_index(drop=True),
        source,
    )


def active_daily_bar_coverage(
    con,
    history: pd.DataFrame | None = None,
    limit: int = 10,
    allow_monitor_history: bool = False,
) -> tuple[int, int, int, pd.DataFrame]:
    """Diagnostic coverage check without rebuilding monitor history by default.

    Passing precomputed monitor history preserves exact canonical active-row semantics.
    Without history, the default path uses watchlist candidates as a fast daily-bar
    coverage fallback so Data Health stays cheap on page render.
    """
    active_count, missing_count, max_gap, stale, _source = _active_daily_bar_coverage(
        con,
        history=history,
        limit=limit,
        allow_monitor_history=allow_monitor_history,
    )
    return active_count, missing_count, max_gap, stale


def _scalar(con, sql: str, default: Any = None) -> Any:
    try:
        row = con.execute(sql).fetchone()
        if row is None:
            return default
        return row[0] if row[0] is not None else default
    except Exception:
        return default


def _fmt_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors='coerce')
    if pd.isna(parsed):
        return '-'
    return parsed.strftime('%Y-%m-%d')


def _is_newer(left: Any, right: Any) -> bool:
    left_date = pd.to_datetime(left, errors='coerce')
    right_date = pd.to_datetime(right, errors='coerce')
    if pd.isna(left_date) or pd.isna(right_date):
        return False
    return left_date.date() > right_date.date()


def build_data_health_summary(con) -> DataHealthSummary:
    latest_setup = _scalar(con, 'select max(watchlist_date) from watchlist_candidates')
    latest_daily = _scalar(con, 'select max(trading_date) from daily_bars')
    latest_intraday = _scalar(con, 'select max(trading_date) from intraday_bars_1m')
    candidate_rows = int(_scalar(con, 'select count(*) from watchlist_candidates', 0) or 0)

    try:
        duplicate_count = len(duplicate_candidate_keys(con))
    except Exception:
        duplicate_count = 0
    try:
        partial_count = len(partial_intraday_sessions_from_db(con))
    except Exception:
        partial_count = 0
    (
        active_count,
        active_missing_count,
        active_max_gap,
        active_stale_rows,
        active_coverage_source,
    ) = _active_daily_bar_coverage(con)

    reasons = []
    if candidate_rows == 0 or latest_setup is None:
        reasons.append('no setup candidates')
    if duplicate_count > 0:
        reasons.append('duplicate candidate keys detected')
    if partial_count > 0:
        reasons.append('partial intraday sessions detected')
    if candidate_rows > 0 and latest_daily is None:
        reasons.append('daily bars unavailable')
    elif _is_newer(latest_setup, latest_daily):
        reasons.append('latest setup date newer than latest daily bars')
    if candidate_rows > 0 and latest_intraday is None:
        reasons.append('intraday bars unavailable')
    elif _is_newer(latest_setup, latest_intraday):
        reasons.append('latest setup date newer than latest intraday bars')

    check_data = (
        candidate_rows == 0
        or latest_setup is None
        or duplicate_count > 0
        or partial_count > 0
        or (candidate_rows > 0 and (latest_daily is None or latest_intraday is None))
        or _is_newer(latest_setup, latest_daily)
        or _is_newer(latest_setup, latest_intraday)
    )
    return DataHealthSummary(
        status='Check Data' if check_data else 'OK',
        latest_setup_date=_fmt_date(latest_setup),
        latest_daily_bar_date=_fmt_date(latest_daily),
        latest_intraday_bar_date=_fmt_date(latest_intraday),
        candidate_rows=candidate_rows,
        duplicate_candidate_key_count=duplicate_count,
        partial_intraday_session_count=partial_count,
        reason='; '.join(reasons),
        active_row_count=active_count,
        active_missing_latest_daily_bar_count=active_missing_count,
        active_max_stale_trading_day_gap=active_max_gap,
        active_stale_daily_bar_rows=active_stale_rows,
        active_daily_bar_coverage_source=active_coverage_source,
    )


def data_health_line(summary: DataHealthSummary) -> str:
    return (
        f'Data Health: {summary.status} | '
        f'Latest Setup: {summary.latest_setup_date} | '
        f'Daily Bars: {summary.latest_daily_bar_date} | '
        f'Intraday: {summary.latest_intraday_bar_date} | '
        f'Candidates: {summary.candidate_rows} | '
        f'Duplicates: {summary.duplicate_candidate_key_count} | '
        f'Partial Sessions: {summary.partial_intraday_session_count}'
        + (f' | Reason: {summary.reason}' if summary.reason else '')
    )
