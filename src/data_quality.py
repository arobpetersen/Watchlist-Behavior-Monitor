from __future__ import annotations

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
