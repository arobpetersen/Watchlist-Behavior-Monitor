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
