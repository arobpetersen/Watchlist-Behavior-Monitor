from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.rolling_setup_monitor import rolling_setup_monitor


SUMMARY_COLUMNS = [
    'Window',
    'Dates',
    'Setup Dates',
    'Setups',
    'Day Success',
    'Day Fail',
    'Unresolved',
    'Active',
    'Later Failed',
    'Clean 1m',
    'Failed 1m',
    'Clean 5m',
    'Failed 5m',
    'Alt Required',
    'Failed OR Trigger',
    'No Trigger',
    'Retested',
    'Wide 1m OR',
    'Wide 5m OR',
    'Median Current',
    'Median Max',
    'Median D3 High',
]

DETAIL_COLUMNS = [
    'Setup Date',
    'Ticker',
    'Current Status',
    'Trigger Day',
    'Trigger',
    '1m ORH',
    '5m ORH',
    'Notes',
    'Current',
    'Max',
    'D3 High',
    'Retest',
    'Setup',
    'Rating',
]


@dataclass(frozen=True)
class OverviewWindow:
    label: str
    start_date: pd.Timestamp
    end_date: pd.Timestamp


def _date(value: Any) -> pd.Timestamp:
    return pd.Timestamp(pd.to_datetime(value).date())


def _fmt_date(value: pd.Timestamp) -> str:
    return value.date().isoformat()


def _fmt_count(count: int, denominator: int) -> str:
    pct = 0 if denominator <= 0 else round((count / denominator) * 100)
    return f'{int(count)} ({pct}%)'


def _fmt_pct(value: Any) -> str:
    if value is None:
        return '-'
    try:
        if pd.isna(value):
            return '-'
        return f'{float(value) * 100:.1f}%'
    except (TypeError, ValueError):
        return '-'


def overview_windows(latest_setup_date) -> list[OverviewWindow]:
    end = _date(latest_setup_date)
    return [
        OverviewWindow('Last 1 Week', end - pd.Timedelta(days=7), end),
        OverviewWindow('Last 2 Weeks', end - pd.Timedelta(days=14), end),
        OverviewWindow('Last 1 Month', end - pd.Timedelta(days=30), end),
    ]


def setup_dates(con) -> list[pd.Timestamp]:
    rows = con.execute(
        """
        select distinct watchlist_date
        from watchlist_candidates
        where watchlist_date is not null
        order by watchlist_date
        """
    ).fetchall()
    return [_date(r[0]) for r in rows]


def monitor_history(con) -> pd.DataFrame:
    dates = setup_dates(con)
    if not dates:
        return pd.DataFrame()
    sections = rolling_setup_monitor(con, setup_dates=len(dates))
    frames = []
    for section in sections:
        table = section['table'].copy()
        table['Setup Date'] = section['setup_date']
        frames.append(table)
    if not frames:
        return pd.DataFrame()
    history = pd.concat(frames, ignore_index=True)
    history['Setup Date'] = pd.to_datetime(history['Setup Date'])
    return history


def _count(series: pd.Series, value: str) -> int:
    return int((series == value).sum())


def _contains(series: pd.Series, text: str) -> int:
    return int(series.fillna('').astype(str).str.contains(text, regex=False).sum())


def summarize_window(history: pd.DataFrame, window: OverviewWindow) -> dict:
    if history.empty:
        rows = history.copy()
    else:
        setup_dates_series = pd.to_datetime(history['Setup Date'])
        rows = history[(setup_dates_series >= window.start_date) & (setup_dates_series <= window.end_date)].copy()

    setups = len(rows)
    setup_dates_count = 0 if rows.empty else int(rows['Setup Date'].nunique())

    def count_fmt(count: int) -> str:
        return _fmt_count(count, setups)

    current_status = rows['Current Status'] if 'Current Status' in rows else pd.Series(dtype=object)
    trigger_day = rows['Trigger Day'] if 'Trigger Day' in rows else pd.Series(dtype=object)
    trigger = rows['Trigger'] if 'Trigger' in rows else pd.Series(dtype=object)
    one = rows['1m ORH'] if '1m ORH' in rows else pd.Series(dtype=object)
    five = rows['5m ORH'] if '5m ORH' in rows else pd.Series(dtype=object)
    notes = rows['Notes'] if 'Notes' in rows else pd.Series(dtype=object)
    retest = rows['Retest Day'] if 'Retest Day' in rows else pd.Series(dtype=object)

    d3_values = rows['d3_high_pct_raw'].dropna() if 'd3_high_pct_raw' in rows else pd.Series(dtype=float)

    return {
        'Window': window.label,
        'Dates': f'{_fmt_date(window.start_date)} to {_fmt_date(window.end_date)}',
        'Setup Dates': setup_dates_count,
        'Setups': setups,
        'Day Success': count_fmt(_count(trigger_day, 'Success')),
        'Day Fail': count_fmt(_count(trigger_day, 'Fail')),
        'Unresolved': count_fmt(_count(trigger_day, 'Unresolved')),
        'Active': count_fmt(_count(current_status, 'Active')),
        'Later Failed': count_fmt(int(current_status.isin({'Failed D1', 'Failed D2', 'Failed D3'}).sum())),
        'Clean 1m': count_fmt(_count(one, 'success')),
        'Failed 1m': count_fmt(_count(one, 'failed')),
        'Clean 5m': count_fmt(_count(five, 'success')),
        'Failed 5m': count_fmt(_count(five, 'failed')),
        'Alt Required': count_fmt(_count(trigger, 'Alt Required')),
        'Failed OR Trigger': count_fmt(_count(trigger, 'Failed OR Trigger')),
        'No Trigger': count_fmt(_count(trigger, 'No Trigger')),
        'Retested': count_fmt(int((retest.fillna('').astype(str) != '').sum())),
        'Wide 1m OR': count_fmt(_contains(notes, 'Wide 1m OR')),
        'Wide 5m OR': count_fmt(_contains(notes, 'Wide 5m OR')),
        'Median Current': _fmt_pct(rows['current_pct_raw'].median() if 'current_pct_raw' in rows and not rows.empty else None),
        'Median Max': _fmt_pct(rows['max_pct_raw'].median() if 'max_pct_raw' in rows and not rows.empty else None),
        'Median D3 High': _fmt_pct(d3_values.median() if not d3_values.empty else None),
    }


def detail_rows(history: pd.DataFrame, window: OverviewWindow) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=DETAIL_COLUMNS)
    setup_dates_series = pd.to_datetime(history['Setup Date'])
    rows = history[(setup_dates_series >= window.start_date) & (setup_dates_series <= window.end_date)].copy()
    if rows.empty:
        return pd.DataFrame(columns=DETAIL_COLUMNS)

    out = pd.DataFrame({
        'Setup Date': pd.to_datetime(rows['Setup Date']).dt.date.astype(str),
        'Ticker': rows['Ticker'],
        'Current Status': rows['Current Status'],
        'Trigger Day': rows['Trigger Day'],
        'Trigger': rows['Trigger'],
        '1m ORH': rows['1m ORH'],
        '5m ORH': rows['5m ORH'],
        'Notes': rows['Notes'],
        'Current': rows['Current %'],
        'Max': rows['Max %'],
        'D3 High': rows['D3 High %'],
        'Retest': rows['Retest Day'],
        'Setup': rows['Setup'],
        'Rating': rows['Rating'],
    })
    return out.sort_values(['Setup Date', 'Ticker'], ascending=[False, True])[DETAIL_COLUMNS]


def setup_behavior_overview(con) -> dict:
    dates = setup_dates(con)
    if not dates:
        return {
            'summary': pd.DataFrame(columns=SUMMARY_COLUMNS),
            'details': {},
            'windows': [],
        }

    windows = overview_windows(max(dates))
    history = monitor_history(con)
    summary = pd.DataFrame([summarize_window(history, window) for window in windows], columns=SUMMARY_COLUMNS)
    details = {window.label: detail_rows(history, window) for window in windows}
    return {
        'summary': summary,
        'details': details,
        'windows': windows,
    }
