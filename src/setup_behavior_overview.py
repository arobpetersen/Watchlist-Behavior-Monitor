from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

import pandas as pd

from src.rolling_setup_monitor import rolling_setup_monitor


FULL_SUMMARY_COLUMNS = [
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
    'D3 Eligible',
    'Median Current',
    'Median Max',
    'Median D3 High',
]

COMPARISON_COLUMNS = [
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
    'Clean 5m',
    'Alt Required',
    'Median Current',
    'Median Max',
    'Median D3 High',
]

SUMMARY_COLUMNS = COMPARISON_COLUMNS

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

CURRENT_STATUS_PRIORITY = {'Active': 0, 'Failed D1': 1, 'Failed D2': 2, 'Failed D3': 3, '—': 4}


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


def _display(value: Any) -> str:
    if value is None:
        return '-'
    try:
        if pd.isna(value):
            return '-'
    except (TypeError, ValueError):
        pass
    text = str(value)
    return '-' if text == '' or text.lower() == 'nan' else text


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
        'D3 Eligible': count_fmt(len(d3_values)),
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
        'Ticker': rows['Ticker'].apply(_display),
        'Current Status': rows['Current Status'].apply(_display),
        'Trigger Day': rows['Trigger Day'].apply(_display),
        'Trigger': rows['Trigger'].apply(_display),
        '1m ORH': rows['1m ORH'].apply(_display),
        '5m ORH': rows['5m ORH'].apply(_display),
        'Notes': rows['Notes'].apply(_display),
        'Current': rows['Current %'].apply(_display),
        'Max': rows['Max %'].apply(_display),
        'D3 High': rows['D3 High %'].apply(_display),
        'Retest': rows['Retest Day'].apply(_display),
        'Setup': rows['Setup'].apply(_display),
        'Rating': rows['Rating'].apply(_display),
    })
    out['_status_priority'] = out['Current Status'].map(CURRENT_STATUS_PRIORITY).fillna(99)
    out['_current_sort'] = pd.to_numeric(out['Current'].str.rstrip('%'), errors='coerce').fillna(float('-inf'))
    out = out.sort_values(['Setup Date', '_status_priority', '_current_sort', 'Ticker'], ascending=[False, True, False, True])
    return out[DETAIL_COLUMNS]


def comparison_rows(window_summaries: pd.DataFrame) -> pd.DataFrame:
    if window_summaries.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    return window_summaries[COMPARISON_COLUMNS].copy()


def selected_window_metrics(window_summary: dict) -> list[dict]:
    return [
        {
            'title': 'Trigger Day Quality',
            'metrics': [
                ('Setups', str(window_summary.get('Setups', 0))),
                ('Day Success', window_summary.get('Day Success', '-')),
                ('Day Fail', window_summary.get('Day Fail', '-')),
                ('Unresolved', window_summary.get('Unresolved', '-')),
            ],
        },
        {
            'title': 'Current Outcome',
            'metrics': [
                ('Active', window_summary.get('Active', '-')),
                ('Later Failed', window_summary.get('Later Failed', '-')),
                ('Median Current', window_summary.get('Median Current', '-')),
                ('Median Max', window_summary.get('Median Max', '-')),
                ('Median D3 High', window_summary.get('Median D3 High', '-')),
                ('D3 Eligible', window_summary.get('D3 Eligible', '-')),
            ],
        },
        {
            'title': 'Trigger Mix',
            'metrics': [
                ('Clean 1m', window_summary.get('Clean 1m', '-')),
                ('Clean 5m', window_summary.get('Clean 5m', '-')),
                ('Alt Required', window_summary.get('Alt Required', '-')),
                ('Failed OR Trigger', window_summary.get('Failed OR Trigger', '-')),
                ('No Trigger', window_summary.get('No Trigger', '-')),
            ],
        },
        {
            'title': 'Diagnostics',
            'metrics': [
                ('Failed 1m', window_summary.get('Failed 1m', '-')),
                ('Failed 5m', window_summary.get('Failed 5m', '-')),
                ('Retested', window_summary.get('Retested', '-')),
                ('Wide 1m OR', window_summary.get('Wide 1m OR', '-')),
                ('Wide 5m OR', window_summary.get('Wide 5m OR', '-')),
            ],
        },
    ]


def factual_read(window_summary: dict) -> str:
    window = window_summary.get('Window', 'Selected window')
    setups = window_summary.get('Setups', 0)
    setup_dates_count = window_summary.get('Setup Dates', 0)
    day_success = window_summary.get('Day Success', '-')
    active = window_summary.get('Active', '-')
    later_failed = window_summary.get('Later Failed', '-')
    median_current = window_summary.get('Median Current', '-')
    median_max = window_summary.get('Median Max', '-')
    return (
        f'{window} includes {setups} setups across {setup_dates_count} setup dates. '
        f'{day_success} succeeded on trigger day, {active} remain active, and {later_failed} failed later. '
        f'Median current return is {median_current} and median max return is {median_max}.'
    )


def metric_cards_html(groups: list[dict]) -> str:
    cards = []
    for group in groups:
        items = ''.join(
            f'<div class="overview-metric"><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>'
            for label, value in group['metrics']
        )
        cards.append(f'<section class="overview-card"><h4>{escape(group["title"])}</h4>{items}</section>')
    return f'''
<style>
.overview-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 0.65rem;
  margin: 0.35rem 0 0.85rem 0;
}}
.overview-card {{
  border: 1px solid rgba(250, 250, 250, 0.12);
  border-radius: 8px;
  padding: 0.72rem 0.78rem;
  background: rgba(250, 250, 250, 0.035);
}}
.overview-card h4 {{
  margin: 0 0 0.55rem 0;
  color: rgba(250, 250, 250, 0.92);
  font-size: 0.95rem;
  font-weight: 750;
}}
.overview-metric {{
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 0.18rem 0;
  color: rgba(250, 250, 250, 0.70);
  font-size: 0.87rem;
}}
.overview-metric strong {{
  color: rgba(250, 250, 250, 0.96);
  font-weight: 750;
  white-space: nowrap;
}}
</style>
<div class="overview-grid">{''.join(cards)}</div>
'''


def setup_behavior_overview(con) -> dict:
    dates = setup_dates(con)
    if not dates:
        return {
            'summary': pd.DataFrame(columns=COMPARISON_COLUMNS),
            'window_summaries': pd.DataFrame(columns=FULL_SUMMARY_COLUMNS),
            'breakdowns': {},
            'reads': {},
            'details': {},
            'windows': [],
        }

    windows = overview_windows(max(dates))
    history = monitor_history(con)
    window_summaries = pd.DataFrame([summarize_window(history, window) for window in windows], columns=FULL_SUMMARY_COLUMNS)
    summary = comparison_rows(window_summaries)
    summary_by_window = {row['Window']: row.to_dict() for _, row in window_summaries.iterrows()}
    details = {window.label: detail_rows(history, window) for window in windows}
    return {
        'summary': summary,
        'window_summaries': window_summaries,
        'breakdowns': {label: selected_window_metrics(row) for label, row in summary_by_window.items()},
        'reads': {label: factual_read(row) for label, row in summary_by_window.items()},
        'details': details,
        'windows': windows,
    }
