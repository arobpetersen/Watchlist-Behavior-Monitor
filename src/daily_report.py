from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.setup_behavior_overview import (
    trigger_event_shift_highlights,
    trigger_outcome_comparison,
)
from src.watchlist_top_movers import top_movers_from_history


WINDOW_LABELS = ['Last 5 Setup Dates', 'Previous 5 Setup Dates', 'Last 10 Setup Dates', 'Last 20 Setup Dates']


def _display(value: Any) -> str:
    if value is None:
        return '-'
    try:
        if pd.isna(value):
            return '-'
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else '-'


def _numeric_series(rows: pd.DataFrame, column: str) -> pd.Series:
    if column not in rows:
        return pd.Series(dtype='float64')
    return pd.to_numeric(rows[column], errors='coerce')


def _pct(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round((count / total) * 100, 1)


def _pct_text(value: float | None) -> str:
    return '-' if value is None else f'{value:.1f}%'


def _return_text(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors='coerce').iloc[0]
    if pd.isna(numeric):
        return '-'
    return f'{numeric * 100:.1f}%'


def _count_payload(count: int, total: int) -> dict:
    return {'count': int(count), 'pct': _pct(int(count), int(total))}


def _status_text(rows: pd.DataFrame) -> pd.Series:
    if 'Current Status' not in rows:
        return pd.Series('', index=rows.index, dtype=object)
    return rows['Current Status'].fillna('').astype(str)


def _trigger_day_text(rows: pd.DataFrame) -> pd.Series:
    if 'Trigger Day' not in rows:
        return pd.Series('', index=rows.index, dtype=object)
    return rows['Trigger Day'].fillna('').astype(str)


def _close_be_mask(rows: pd.DataFrame) -> pd.Series:
    if 'Close < BE' not in rows:
        return pd.Series(False, index=rows.index)
    return rows['Close < BE'].fillna('').astype(str).str.casefold().eq('yes')


def _retest_text(rows: pd.DataFrame) -> pd.Series:
    for column in ['Retest Days Raw', 'Retests', 'Retest Day']:
        if column in rows:
            return rows[column].fillna('').astype(str)
    return pd.Series('', index=rows.index, dtype=object)


def _retested_d0_only_mask(rows: pd.DataFrame) -> pd.Series:
    retests = _retest_text(rows)
    has_d0 = retests.str.contains('D0', regex=False)
    has_later = retests.str.contains(r'D[1-9]', regex=True)
    return has_d0 & ~has_later


def _retested_after_d0_mask(rows: pd.DataFrame) -> pd.Series:
    return _retest_text(rows).str.contains(r'D[1-9]', regex=True)


def _failed_after_d0_mask(rows: pd.DataFrame) -> pd.Series:
    status = _status_text(rows)
    return status.str.match(r'Failed D[1-9]\d*', na=False)


def _latest_setup_date_summary(history: pd.DataFrame) -> dict:
    if history.empty or 'Setup Date' not in history:
        return {'latest_setup_date': None, 'setup_count': 0}
    dates = pd.to_datetime(history['Setup Date'], errors='coerce')
    latest = dates.max()
    if pd.isna(latest):
        return {'latest_setup_date': None, 'setup_count': 0}
    rows = history[dates.dt.date.eq(latest.date())].copy()
    total = len(rows)
    trigger_day = _trigger_day_text(rows)
    status = _status_text(rows)
    return {
        'latest_setup_date': latest.date().isoformat(),
        'setup_count': total,
        'active': _count_payload(int(status.eq('Active').sum()), total),
        'failed_d0': _count_payload(int(trigger_day.eq('Fail').sum()), total),
        'failed_after_d0': _count_payload(int(_failed_after_d0_mask(rows).sum()), total),
        'unresolved': _count_payload(int(trigger_day.eq('Unresolved').sum()), total),
        'close_below_be': _count_payload(int(_close_be_mask(rows).sum()), total),
        'retested_d0_only': _count_payload(int(_retested_d0_only_mask(rows).sum()), total),
        'retested_after_d0': _count_payload(int(_retested_after_d0_mask(rows).sum()), total),
    }


def _window_rows(history: pd.DataFrame, overview: dict, label: str) -> pd.DataFrame:
    if 'windows' not in overview or history.empty or 'Setup Date' not in history:
        return pd.DataFrame()
    window = next((item for item in overview.get('windows', []) if item.label == label), None)
    if window is None:
        return pd.DataFrame()
    included = {date.date() for date in window.setup_dates}
    dates = pd.to_datetime(history['Setup Date'], errors='coerce')
    return history[dates.dt.date.isin(included)].copy()


def _recent_window_summary(history: pd.DataFrame, overview: dict) -> dict:
    summaries = {}
    for label in WINDOW_LABELS:
        rows = _window_rows(history, overview, label)
        total = len(rows)
        status = _status_text(rows)
        trigger_day = _trigger_day_text(rows)
        summaries[label] = {
            'setup_count': total,
            'active_pct': _pct(int(status.eq('Active').sum()), total),
            'failed_d0_pct': _pct(int(trigger_day.eq('Fail').sum()), total),
            'failed_after_d0_pct': _pct(int(_failed_after_d0_mask(rows).sum()), total),
            'median_current': None if rows.empty else _numeric_series(rows, 'current_pct_raw').median(),
            'median_max': None if rows.empty else _numeric_series(rows, 'max_pct_raw').median(),
            'close_below_be_pct': _pct(int(_close_be_mask(rows).sum()), total),
            'retested_after_d0_pct': _pct(int(_retested_after_d0_mask(rows).sum()), total),
        }
    return summaries


def _trigger_summary(overview: dict) -> dict:
    comparison = overview.get('trigger_outcome_comparison')
    if comparison is None or comparison.empty:
        comparison = trigger_outcome_comparison({})
    failure_rates = []
    successful_mix = []
    for _, row in comparison.iterrows():
        if row.get('Window') not in WINDOW_LABELS:
            continue
        failure_rates.append({
            'window': row.get('Window'),
            'trigger': row.get('Trigger'),
            'triggered': int(row.get('Triggered', 0)),
            'failed': int(row.get('Failed', 0)),
            'fail_pct': row.get('Fail %', '-'),
        })
        successful_mix.append({
            'window': row.get('Window'),
            'trigger': row.get('Trigger'),
            'success': int(row.get('Success', 0)),
            'success_pct': row.get('Success %', '-'),
        })
    highlights = overview.get('trigger_event_shift_highlights') or trigger_event_shift_highlights(comparison)
    shifts = [
        {'window': window, 'trigger': trigger, 'metric': metric, 'direction': direction}
        for (window, trigger, metric), direction in sorted(highlights.items())
        if window == 'Last 5 Setup Dates'
    ]
    return {'successful_trigger_mix': successful_mix, 'failure_rates': failure_rates, 'notable_shifts': shifts}


def _name_rows(rows: pd.DataFrame, sort_column: str, limit: int = 5, ascending: bool = False) -> list[dict]:
    if rows.empty:
        return []
    out = rows.copy()
    out[sort_column] = pd.to_numeric(out.get(sort_column), errors='coerce')
    out = out[out[sort_column].notna()].sort_values(sort_column, ascending=ascending).head(limit)
    names = []
    for _, row in out.iterrows():
        names.append({
            'ticker': _display(row.get('Ticker')),
            'setup_date': _display(row.get('Setup Date')),
            'trigger': _display(row.get('Trigger')),
            'current': _return_text(row.get('current_pct_raw')),
            'max': _return_text(row.get('max_pct_raw')),
            'status': _display(row.get('Current Status')),
        })
    return names


def _notable_tickers(history: pd.DataFrame) -> dict:
    if history.empty:
        return {
            'top_active_by_current': [],
            'failed_after_initially_working': [],
            'close_below_be': [],
            'strongest_max': [],
        }
    return {
        'top_active_by_current': _name_rows(history[_status_text(history).eq('Active')].copy(), 'current_pct_raw'),
        'failed_after_initially_working': _name_rows(history[_failed_after_d0_mask(history)].copy(), 'max_pct_raw'),
        'close_below_be': _name_rows(history[_close_be_mask(history)].copy(), 'current_pct_raw'),
        'strongest_max': _name_rows(history.copy(), 'max_pct_raw'),
    }


def _portfolio_summary(history: pd.DataFrame) -> dict:
    if history.empty:
        return {'current_progress_count': 0, 'top_current_progress': [], 'longest_open': [], 'rated_4_count': 0, 'rated_5_count': 0}
    latest_dates = pd.to_datetime(history.get('Latest Status Date', history.get('Setup Date')), errors='coerce')
    latest_date = None if latest_dates.dropna().empty else latest_dates.max()
    current = top_movers_from_history(history, latest_date=latest_date, portfolio_view='Current Progress').portfolio_table
    longest = top_movers_from_history(history, latest_date=latest_date, portfolio_view='Longest Open').portfolio_table
    rating = pd.to_numeric(current.get('Rating', pd.Series(dtype=object)), errors='coerce')
    return {
        'current_progress_count': int(len(current)),
        'top_current_progress': current.head(5).get('Ticker', pd.Series(dtype=object)).astype(str).tolist(),
        'longest_open': longest.head(5).get('Ticker', pd.Series(dtype=object)).astype(str).tolist(),
        'rated_4_count': int(rating.eq(4).sum()),
        'rated_5_count': int(rating.eq(5).sum()),
    }


def build_daily_report_payload(history: pd.DataFrame, overview: dict) -> dict:
    history = history.copy() if history is not None else pd.DataFrame()
    return {
        'latest_setup_date_summary': _latest_setup_date_summary(history),
        'recent_window_summary': _recent_window_summary(history, overview or {}),
        'trigger_summary': _trigger_summary(overview or {}),
        'notable_tickers': _notable_tickers(history),
        'portfolio_summary': _portfolio_summary(history),
    }


def _line_for_count(label: str, payload: dict) -> str:
    return f"{label}: {payload.get('count', 0)} ({_pct_text(payload.get('pct'))})"


def render_daily_report_markdown(report_payload: dict) -> str:
    latest = report_payload.get('latest_setup_date_summary', {})
    windows = report_payload.get('recent_window_summary', {})
    triggers = report_payload.get('trigger_summary', {})
    names = report_payload.get('notable_tickers', {})
    portfolio = report_payload.get('portfolio_summary', {})
    last5 = windows.get('Last 5 Setup Dates', {})
    previous5 = windows.get('Previous 5 Setup Dates', {})

    def ticker_list(items: list[dict] | list[str]) -> str:
        if not items:
            return '-'
        if isinstance(items[0], str):
            return ', '.join(items)
        return ', '.join(f"{item['ticker']} ({item['current']} current, {item['max']} max)" for item in items[:5])

    shifts = triggers.get('notable_shifts', [])
    shift_text = '; '.join(f"{item['trigger']} {item['metric']} {item['direction']}" for item in shifts[:5]) or '-'
    failure_rates = [
        f"{item['trigger']} {item['fail_pct']}"
        for item in triggers.get('failure_rates', [])
        if item.get('window') == 'Last 5 Setup Dates' and item.get('triggered', 0)
    ]

    return '\n'.join([
        '# Daily Intelligence Report',
        '',
        '## Latest Setup Date',
        f"- Date: {latest.get('latest_setup_date') or '-'}",
        f"- Setups: {latest.get('setup_count', 0)}",
        f"- {_line_for_count('Active', latest.get('active', {}))}",
        f"- {_line_for_count('Failed D0', latest.get('failed_d0', {}))}",
        f"- {_line_for_count('Close < BE', latest.get('close_below_be', {}))}",
        '',
        '## Current Read',
        f"- Last 5 active rate: {_pct_text(last5.get('active_pct'))}; Previous 5 active rate: {_pct_text(previous5.get('active_pct'))}",
        f"- Last 5 median current: {_return_text(last5.get('median_current'))}; median max: {_return_text(last5.get('median_max'))}",
        '',
        '## Trigger Read',
        f"- Last 5 failure rates: {', '.join(failure_rates) if failure_rates else '-'}",
        '',
        '## Short-Term Shifts',
        f"- {shift_text}",
        '',
        '## Notable Names',
        f"- Top active by Current %: {ticker_list(names.get('top_active_by_current', []))}",
        f"- Failed after initially working: {ticker_list(names.get('failed_after_initially_working', []))}",
        f"- Close < BE: {ticker_list(names.get('close_below_be', []))}",
        f"- Strongest Max %: {ticker_list(names.get('strongest_max', []))}",
        '',
        '## Portfolio Snapshot',
        f"- Current Progress count: {portfolio.get('current_progress_count', 0)}",
        f"- Top Current Progress: {ticker_list(portfolio.get('top_current_progress', []))}",
        f"- Longest Open: {ticker_list(portfolio.get('longest_open', []))}",
        f"- Ratings in Current Progress: {portfolio.get('rated_5_count', 0)} rated 5; {portfolio.get('rated_4_count', 0)} rated 4",
        '',
    ])


def build_llm_report_prompt(report_payload: dict) -> str:
    structured_summary = json.dumps(report_payload, indent=2, default=str)
    return (
        'Summarize the following structured Watchlist Behavior Monitor metrics only from the provided data.\n'
        'Do not make trade recommendations. Do not infer from raw database rows. Call out notable shifts, data limitations, '
        'and keep the report concise.\n\n'
        f'STRUCTURED_SUMMARY:\n{structured_summary}'
    )
