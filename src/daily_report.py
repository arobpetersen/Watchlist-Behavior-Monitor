from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.setup_behavior_overview import (
    trigger_event_shift_highlights,
    trigger_outcome_comparison,
)
from src.watchlist_top_movers import prepare_top_mover_rows, top_movers_from_history


WINDOW_LABELS = ['Last 5 Setup Dates', 'Previous 5 Setup Dates', 'Last 10 Setup Dates', 'Last 20 Setup Dates']
RATE_CHANGE_THRESHOLD = 15.0
CLOSE_BE_THRESHOLD = 10.0
RETURN_CHANGE_THRESHOLD = 0.03
COUNT_CHANGE_THRESHOLD = 3
REPORT_WINDOWS = ['Latest', 'Last 5', 'Previous 5']
ROLLING_AVG_SETUP_DATES = 20
REPORT_WINDOW_LABELS = {
    'Latest': 'Latest Setup Date',
    'Last 5': 'Recent 5 Setup Dates',
    'Previous 5': 'Prior 5 Setup Dates',
}


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


def _window_display(label: str) -> str:
    return REPORT_WINDOW_LABELS.get(label, label)


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


def _pts_text(value: float | None) -> str:
    if value is None:
        return '-'
    sign = '+' if value > 0 else ''
    return f'{sign}{value:.1f} pts'


def _whole_pct_text(value: float | None) -> str:
    return '-' if value is None else f'{value:.0f}%'


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


def _rows_for_latest_n_setup_dates(history: pd.DataFrame, n: int, offset: int = 0) -> pd.DataFrame:
    if history.empty or 'Setup Date' not in history:
        return pd.DataFrame()
    out = history.copy()
    out['_setup_date'] = pd.to_datetime(out['Setup Date'], errors='coerce')
    setup_dates = sorted(out['_setup_date'].dt.date.dropna().unique())
    if not setup_dates:
        return pd.DataFrame()
    end = len(setup_dates) - offset
    start = max(0, end - n)
    selected = set(setup_dates[start:end])
    return out[out['_setup_date'].dt.date.isin(selected)].drop(columns=['_setup_date']).copy()


def _snapshot(rows: pd.DataFrame) -> dict:
    total = len(rows)
    status = _status_text(rows)
    trigger_day = _trigger_day_text(rows)
    return {
        'setup_count': total,
        'active_count': int(status.eq('Active').sum()),
        'active_pct': _pct(int(status.eq('Active').sum()), total),
        'failed_d0_count': int(trigger_day.eq('Fail').sum()),
        'failed_d0_pct': _pct(int(trigger_day.eq('Fail').sum()), total),
        'failed_after_d0_count': int(_failed_after_d0_mask(rows).sum()),
        'failed_after_d0_pct': _pct(int(_failed_after_d0_mask(rows).sum()), total),
        'unresolved_count': int(trigger_day.eq('Unresolved').sum()),
        'unresolved_pct': _pct(int(trigger_day.eq('Unresolved').sum()), total),
        'close_below_be_count': int(_close_be_mask(rows).sum()),
        'close_below_be_pct': _pct(int(_close_be_mask(rows).sum()), total),
        'retested_after_d0_count': int(_retested_after_d0_mask(rows).sum()),
        'retested_after_d0_pct': _pct(int(_retested_after_d0_mask(rows).sum()), total),
        'median_current': None if rows.empty else _numeric_series(rows, 'current_pct_raw').median(),
        'median_max': None if rows.empty else _numeric_series(rows, 'max_pct_raw').median(),
    }


def _clean_active_mask(rows: pd.DataFrame) -> pd.Series:
    if rows.empty:
        return pd.Series(False, index=rows.index)
    return _status_text(rows).eq('Active') & ~_close_be_mask(rows) & ~_failed_after_d0_mask(rows)


def _valid_return_pair(rows: pd.DataFrame) -> pd.DataFrame:
    pairs = pd.DataFrame({
        'current': _numeric_series(rows, 'current_pct_raw'),
        'max': _numeric_series(rows, 'max_pct_raw'),
    }, index=rows.index)
    return pairs[pairs['current'].notna() & pairs['max'].notna()]


def _hold_ratio(rows: pd.DataFrame) -> dict:
    active = rows[_clean_active_mask(rows)].copy()
    pairs = _valid_return_pair(active)
    pairs = pairs[pairs['max'] > 0]
    if pairs.empty:
        return {'value': None, 'count': 0}
    ratios = (pairs['current'] / pairs['max']).clip(lower=0)
    return {'value': round(float(ratios.median() * 100), 1), 'count': int(ratios.notna().sum())}


def _row_hold_ratio(row: pd.Series) -> float | None:
    current = pd.to_numeric(pd.Series([row.get('current_pct_raw', row.get('_current_sort'))]), errors='coerce').iloc[0]
    max_pct = pd.to_numeric(pd.Series([row.get('max_pct_raw', row.get('_max_sort'))]), errors='coerce').iloc[0]
    if pd.isna(current) or pd.isna(max_pct) or float(max_pct) <= 0:
        return None
    return round(float(max(current, 0) / max_pct * 100), 1)


def _row_return_evidence(row: pd.Series, include_hold: bool = True) -> str:
    current = row.get('current_pct_raw', row.get('_current_sort'))
    max_pct = row.get('max_pct_raw', row.get('_max_sort'))
    evidence = f"Current {_return_text(current)}; Max {_return_text(max_pct)}"
    hold = _row_hold_ratio(row)
    if include_hold and hold is not None:
        evidence += f"; Hold {hold:.1f}%"
    return evidence


def _median_days_to_max(rows: pd.DataFrame) -> float | None:
    if rows.empty:
        return None
    for column in ['Days to Max', 'days_to_max']:
        if column in rows:
            values = pd.to_numeric(rows[column], errors='coerce').dropna()
            return None if values.empty else round(float(values.median()), 1)
    if {'Setup Date', 'Max Date'}.issubset(rows.columns):
        setup = pd.to_datetime(rows['Setup Date'], errors='coerce')
        max_date = pd.to_datetime(rows['Max Date'], errors='coerce')
        values = (max_date - setup).dt.days.dropna()
        return None if values.empty else round(float(values.median()), 1)
    return None


def _window_quality_summary(rows: pd.DataFrame) -> dict:
    total = len(rows)
    max_values = _numeric_series(rows, 'max_pct_raw').dropna()
    eligible_max = int(max_values.shape[0])
    clean_active = _clean_active_mask(rows)
    failed_d0 = _trigger_day_text(rows).eq('Fail')
    close_be = _close_be_mask(rows)
    retested_after = _retested_after_d0_mask(rows)
    return {
        'setup_count': total,
        'clean_active_count': int(clean_active.sum()),
        'clean_active_pct': _pct(int(clean_active.sum()), total),
        'failed_d0_count': int(failed_d0.sum()),
        'failed_d0_pct': _pct(int(failed_d0.sum()), total),
        'close_below_be_count': int(close_be.sum()),
        'close_below_be_pct': _pct(int(close_be.sum()), total),
        'median_current': None if rows.empty else _numeric_series(rows, 'current_pct_raw').median(),
        'median_max': None if rows.empty else _numeric_series(rows, 'max_pct_raw').median(),
        'hold_ratio': _hold_ratio(rows),
        'retested_after_d0_count': int(retested_after.sum()),
        'retested_after_d0_pct': _pct(int(retested_after.sum()), total),
        'thresholds': {
            '5': {'count': int(max_values.ge(0.05).sum()), 'total': eligible_max, 'pct': _pct(int(max_values.ge(0.05).sum()), eligible_max)},
            '10': {'count': int(max_values.ge(0.10).sum()), 'total': eligible_max, 'pct': _pct(int(max_values.ge(0.10).sum()), eligible_max)},
            '20': {'count': int(max_values.ge(0.20).sum()), 'total': eligible_max, 'pct': _pct(int(max_values.ge(0.20).sum()), eligible_max)},
        },
        'median_days_to_max': _median_days_to_max(rows),
    }


def _report_windows(history: pd.DataFrame, overview: dict) -> dict[str, pd.DataFrame]:
    return {
        'Latest': _rows_for_latest_n_setup_dates(history, 1),
        'Last 5': _window_rows(history, overview, 'Last 5 Setup Dates'),
        'Previous 5': _window_rows(history, overview, 'Previous 5 Setup Dates'),
    }


def _rolling_window_rows(history: pd.DataFrame) -> pd.DataFrame:
    # Rolling Avg is the most recent 20 setup dates, including the latest setup date.
    return _rows_for_latest_n_setup_dates(history, ROLLING_AVG_SETUP_DATES)


def _trigger_failure_snapshot(history: pd.DataFrame, overview: dict) -> list[dict]:
    windows = _report_windows(history, overview)
    windows['Rolling Avg'] = _rolling_window_rows(history)
    trigger_order = ['1m ORH', 'VWAP Reclaim', 'PDH', '5m ORH']
    rows: list[dict] = []
    for trigger in trigger_order:
        cells = {}
        present = False
        total_attempts = 0
        for label, window_rows in windows.items():
            if window_rows.empty or 'Trigger' not in window_rows:
                cells[label] = {'triggered': 0, 'failed': 0, 'fail_rate': None}
                continue
            trigger_rows = window_rows[window_rows['Trigger'].fillna('').astype(str).eq(trigger)]
            triggered = int(len(trigger_rows))
            failed = int(_trigger_day_text(trigger_rows).eq('Fail').sum()) if triggered else 0
            if triggered:
                present = True
                total_attempts += triggered
            cells[label] = {'triggered': triggered, 'failed': failed, 'fail_rate': _pct(failed, triggered)}
        if present:
            rows.append({'trigger': trigger, 'cells': cells, 'total_attempts': total_attempts})
    return rows[:4]


def _latest_report_date(history: pd.DataFrame) -> pd.Timestamp | None:
    if history.empty:
        return None
    source = history.get('Latest Status Date', history.get('latest_trading_date_raw', history.get('Setup Date')))
    dates = pd.to_datetime(source, errors='coerce')
    if dates.dropna().empty:
        return None
    return pd.to_datetime(dates.max())


def _prepared_report_rows(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    try:
        prepared = prepare_top_mover_rows(history, latest_date=_latest_report_date(history))
    except Exception:
        return history.copy()
    return prepared


def _watchlist_pulse(history: pd.DataFrame, overview: dict) -> dict:
    pulse = {
        label: _window_quality_summary(rows)
        for label, rows in _report_windows(history, overview).items()
    }
    pulse['Rolling Avg'] = _window_quality_summary(_rolling_window_rows(history))
    return pulse


def _comparison_payload(history: pd.DataFrame, overview: dict) -> dict:
    latest = _rows_for_latest_n_setup_dates(history, 1)
    prior = _rows_for_latest_n_setup_dates(history, 1, offset=1)
    last2 = _rows_for_latest_n_setup_dates(history, 2)
    last5 = _window_rows(history, overview, 'Last 5 Setup Dates')
    previous5 = _window_rows(history, overview, 'Previous 5 Setup Dates')
    return {
        'latest_vs_prior': {'current': _snapshot(latest), 'baseline': _snapshot(prior)},
        'latest_vs_last5': {'current': _snapshot(latest), 'baseline': _snapshot(last5)},
        'last2_vs_last5': {'current': _snapshot(last2), 'baseline': _snapshot(last5)},
        'last5_vs_previous5': {'current': _snapshot(last5), 'baseline': _snapshot(previous5)},
    }


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
        return {'current_progress_count': 0, 'top_current_progress': [], 'longest_open': [], 'rated_4_count': 0, 'rated_5_count': 0, 'median_current_progress': None}
    latest_dates = pd.to_datetime(history.get('Latest Status Date', history.get('Setup Date')), errors='coerce')
    latest_date = None if latest_dates.dropna().empty else latest_dates.max()
    current = top_movers_from_history(history, latest_date=latest_date, portfolio_view='Current Progress').portfolio_table
    longest = top_movers_from_history(history, latest_date=latest_date, portfolio_view='Longest Open').portfolio_table
    rating = pd.to_numeric(current.get('Rating', pd.Series(dtype=object)), errors='coerce')
    current_pct = pd.to_numeric(current.get('Current %', pd.Series(dtype=object)).astype(str).str.replace('%', '', regex=False), errors='coerce') / 100
    return {
        'current_progress_count': int(len(current)),
        'top_current_progress': current.head(5).get('Ticker', pd.Series(dtype=object)).astype(str).tolist(),
        'longest_open': longest.head(5).get('Ticker', pd.Series(dtype=object)).astype(str).tolist(),
        'rated_4_count': int(rating.eq(4).sum()),
        'rated_5_count': int(rating.eq(5).sum()),
        'median_current_progress': None if current_pct.dropna().empty else float(current_pct.median()),
    }


def _delta(current: Any, baseline: Any) -> float | None:
    if current is None or baseline is None:
        return None
    try:
        if pd.isna(current) or pd.isna(baseline):
            return None
    except (TypeError, ValueError):
        pass
    return float(current) - float(baseline)


def _direction(delta: float, higher_is_better: bool) -> str:
    improved = delta > 0 if higher_is_better else delta < 0
    return 'improved' if improved else 'deteriorated'


def _sample_note(current: dict, baseline: dict) -> str:
    current_total = int(current.get('setup_count', 0) or 0)
    baseline_total = int(baseline.get('setup_count', 0) or 0)
    if min(current_total, baseline_total) < 5:
        return ' Small sample.'
    return ''


def _rate_observation(comparison: str, metric: str, current: dict, baseline: dict, higher_is_better: bool, threshold: float, meaning: str) -> dict | None:
    delta = _delta(current.get(f'{metric}_pct'), baseline.get(f'{metric}_pct'))
    if delta is None or abs(delta) < threshold:
        return None
    current_count = int(current.get(f'{metric}_count', 0) or 0)
    baseline_count = int(baseline.get(f'{metric}_count', 0) or 0)
    current_total = int(current.get('setup_count', 0) or 0)
    baseline_total = int(baseline.get('setup_count', 0) or 0)
    count_delta = current_count - baseline_count
    if abs(count_delta) < COUNT_CHANGE_THRESHOLD and min(current_total, baseline_total) >= 10:
        return None
    label = metric.replace('_', ' ').title()
    change_word = 'increased' if delta > 0 else 'decreased'
    section = 'Short-Term Shifts' if comparison.startswith('Last 2') or comparison.startswith('Last 5') else 'Current Read'
    return {
        'section': section,
        'comparison': comparison,
        'metric': metric,
        'metric_label': label,
        'prior': _pct_text(baseline.get(f'{metric}_pct')),
        'current': _pct_text(current.get(f'{metric}_pct')),
        'change': _pts_text(delta),
        'read': _short_read(metric, delta, current, baseline),
        'direction': _direction(delta, higher_is_better),
        'text': (
            f"{comparison}: {label} {change_word} from {_pct_text(baseline.get(f'{metric}_pct'))} to "
            f"{_pct_text(current.get(f'{metric}_pct'))} "
            f"({baseline_count}/{baseline_total} to {current_count}/{current_total} setups). {meaning}{_sample_note(current, baseline)}"
        ),
    }


def _return_observation(comparison: str, metric: str, current: dict, baseline: dict, higher_is_better: bool, meaning: str) -> dict | None:
    delta = _delta(current.get(metric), baseline.get(metric))
    if delta is None or abs(delta) < RETURN_CHANGE_THRESHOLD:
        return None
    label = metric.replace('_', ' ').title()
    change_word = 'improved' if delta > 0 else 'weakened'
    section = 'Short-Term Shifts' if comparison.startswith('Last 2') or comparison.startswith('Last 5') else 'Current Read'
    return {
        'section': section,
        'comparison': comparison,
        'metric': metric,
        'metric_label': label,
        'prior': _return_text(baseline.get(metric)),
        'current': _return_text(current.get(metric)),
        'change': _pts_text(delta * 100),
        'read': 'Current progress improved' if metric == 'median_current' and delta > 0 else 'Current progress weakened' if metric == 'median_current' else 'Max progress improved' if delta > 0 else 'Max progress weakened',
        'direction': _direction(delta, higher_is_better),
        'text': (
            f"{comparison}: {label} {change_word} from {_return_text(baseline.get(metric))} to "
            f"{_return_text(current.get(metric))} "
            f"({baseline.get('setup_count', 0)} to {current.get('setup_count', 0)} setups). {meaning}{_sample_note(current, baseline)}"
        ),
    }


def _short_read(metric: str, delta: float | None, current: dict | None = None, baseline: dict | None = None) -> str:
    sample = 'Small sample' if current is not None and baseline is not None and min(int(current.get('setup_count', 0) or 0), int(baseline.get('setup_count', 0) or 0)) < 5 else ''
    if metric == 'active':
        read = 'Improved active rate' if delta and delta > 0 else 'Weaker active rate'
    elif metric == 'failed_d0':
        read = 'More setup-day failures' if delta and delta > 0 else 'Fewer setup-day failures'
    elif metric == 'failed_after_d0':
        read = 'More later failures' if delta and delta > 0 else 'Fewer later failures'
    elif metric == 'close_below_be':
        read = 'More weak closes' if delta and delta > 0 else 'Fewer weak closes'
    elif metric == 'retested_after_d0':
        read = 'More post-D0 retests' if delta and delta > 0 else 'Fewer post-D0 retests'
    else:
        read = 'Material shift'
    return f'{read}; {sample}' if sample else read


def _meaning(metric: str, delta: float | None) -> str:
    if metric == 'active':
        return 'This measures whether setups are staying active.' if delta and delta > 0 else 'This marks weaker active retention.'
    if metric == 'failed_d0':
        return 'This shows more setup-day failures.' if delta and delta > 0 else 'This shows fewer setup-day failures.'
    if metric == 'failed_after_d0':
        return 'This flags setups that worked first but failed later.' if delta and delta > 0 else 'This shows fewer later failures after initial success.'
    if metric == 'close_below_be':
        return 'This highlights weaker end-of-day follow-through.' if delta and delta > 0 else 'This shows fewer end-of-day follow-through breaks.'
    if metric == 'retested_after_d0':
        return 'This shows more post-D0 retest activity.' if delta and delta > 0 else 'This shows post-D0 retest activity eased.'
    return 'highlighting a material behavior shift.'


def _trigger_share(rows: pd.DataFrame) -> dict[str, dict]:
    if rows.empty or 'Trigger' not in rows:
        return {}
    success = rows[_trigger_day_text(rows).eq('Success')]
    total = len(success)
    if total == 0:
        return {}
    return {
        str(trigger): {'pct': round((count / total) * 100, 1), 'count': int(count), 'total': int(total)}
        for trigger, count in success['Trigger'].fillna('').astype(str).value_counts().items()
        if trigger and trigger != 'No Trigger'
    }


def _trigger_failure_rates(rows: pd.DataFrame) -> dict[str, dict]:
    if rows.empty or 'Trigger' not in rows:
        return {}
    out = {}
    for trigger, group in rows.groupby(rows['Trigger'].fillna('').astype(str)):
        if not trigger or trigger == 'No Trigger':
            continue
        total = len(group)
        if total:
            failed = int(_trigger_day_text(group).eq('Fail').sum())
            out[trigger] = {'pct': round((failed / total) * 100, 1), 'failed': failed, 'total': int(total)}
    return out


def _trigger_observations(history: pd.DataFrame, overview: dict) -> list[dict]:
    observations = []
    pairs = {
        'Latest setup date vs prior setup date': (
            _rows_for_latest_n_setup_dates(history, 1),
            _rows_for_latest_n_setup_dates(history, 1, offset=1),
        ),
        'Latest setup date vs Last 5 setup dates': (
            _rows_for_latest_n_setup_dates(history, 1),
            _window_rows(history, overview, 'Last 5 Setup Dates'),
        ),
        'Last 2 setup dates vs Last 5 setup-date baseline': (
            _rows_for_latest_n_setup_dates(history, 2),
            _window_rows(history, overview, 'Last 5 Setup Dates'),
        ),
        'Last 5 setup dates vs Previous 5 setup dates': (
            _window_rows(history, overview, 'Last 5 Setup Dates'),
            _window_rows(history, overview, 'Previous 5 Setup Dates'),
        ),
    }
    for label, (current_rows, baseline_rows) in pairs.items():
        current_share = _trigger_share(current_rows)
        baseline_share = _trigger_share(baseline_rows)
        for trigger in sorted(set(current_share) | set(baseline_share)):
            current = current_share.get(trigger, {'pct': 0.0, 'count': 0, 'total': 0})
            baseline = baseline_share.get(trigger, {'pct': 0.0, 'count': 0, 'total': 0})
            delta = current['pct'] - baseline['pct']
            if abs(delta) >= RATE_CHANGE_THRESHOLD:
                word = 'larger' if delta > 0 else 'smaller'
                note = ' Small sample.' if min(current['total'], baseline['total']) < 5 else ''
                observations.append({
                    'section': 'Trigger Read',
                    'comparison': label,
                    'metric': 'successful_trigger_share',
                    'direction': 'changed',
                    'text': (
                        f"{label}: {trigger} contributed a {word} share of successful triggers "
                        f"({_pct_text(baseline['pct'])} to {_pct_text(current['pct'])}; "
                        f"{baseline['count']}/{baseline['total']} to {current['count']}/{current['total']} successes). "
                        f"This identifies a trigger-mix shift.{note}"
                    ),
                })
        current_fail = _trigger_failure_rates(current_rows)
        baseline_fail = _trigger_failure_rates(baseline_rows)
        for trigger in sorted(set(current_fail) | set(baseline_fail)):
            current = current_fail.get(trigger, {'pct': 0.0, 'failed': 0, 'total': 0})
            baseline = baseline_fail.get(trigger, {'pct': 0.0, 'failed': 0, 'total': 0})
            delta = current['pct'] - baseline['pct']
            if abs(delta) >= RATE_CHANGE_THRESHOLD:
                word = 'higher' if delta > 0 else 'lower'
                meaning = 'This points to faster trigger failures.' if delta > 0 else 'This shows that trigger held more often.'
                note = ' Small sample.' if min(current['total'], baseline['total']) < 5 else ''
                observations.append({
                    'section': 'Trigger Read',
                    'comparison': label,
                    'metric': 'trigger_failure_rate',
                    'direction': 'deteriorated' if delta > 0 else 'improved',
                    'text': (
                        f"{label}: {trigger} failure rate was {word} "
                        f"({_pct_text(baseline['pct'])} to {_pct_text(current['pct'])}; "
                        f"{baseline['failed']}/{baseline['total']} to {current['failed']}/{current['total']} triggered attempts failed). "
                        f"{meaning}{note}"
                    ),
                })
    return observations[:8]


def _trigger_read_rows(history: pd.DataFrame) -> list[dict]:
    windows = {
        'Latest': _rows_for_latest_n_setup_dates(history, 1),
        'Last 2': _rows_for_latest_n_setup_dates(history, 2),
        'Last 5': _rows_for_latest_n_setup_dates(history, 5),
        'Previous 5': _rows_for_latest_n_setup_dates(history, 5, offset=5),
    }
    rows = []
    for label, window_rows in windows.items():
        if window_rows.empty or 'Trigger' not in window_rows:
            continue
        for trigger, group in window_rows.groupby(window_rows['Trigger'].fillna('').astype(str)):
            if not trigger or trigger == 'No Trigger':
                continue
            triggered = int(len(group))
            if triggered <= 0:
                continue
            failed = int(_trigger_day_text(group).eq('Fail').sum())
            success = int(_trigger_day_text(group).eq('Success').sum())
            clean_active = int(_clean_active_mask(group).sum())
            median_max = _numeric_series(group, 'max_pct_raw').median()
            fail_pct = _pct(failed, triggered)
            read = _trigger_quality_read(triggered, clean_active, fail_pct, median_max)
            rows.append({
                'trigger': trigger,
                'window': label,
                'triggered': triggered,
                'failed': failed,
                'success': success,
                'clean_active': clean_active,
                'median_max': None if pd.isna(median_max) else float(median_max),
                'failure_rate': _pct_text(_pct(failed, triggered)),
                'read': read,
            })
    return rows[:10]


def _trigger_quality_read(triggered: int, clean_active: int, fail_pct: float | None, median_max: Any) -> str:
    if triggered < 3:
        return 'Small sample'
    if fail_pct is not None and fail_pct >= 50:
        return 'Elevated failures'
    median = pd.to_numeric(pd.Series([median_max]), errors='coerce').iloc[0]
    clean_pct = _pct(clean_active, triggered)
    if clean_pct is not None and clean_pct >= 70 and not pd.isna(median) and median >= 0.10:
        return 'Clean follow-through'
    if clean_pct is not None and clean_pct >= 50 and not pd.isna(median) and median >= 0.10:
        return 'Usable follow-through'
    if not pd.isna(median) and median >= 0.10:
        return 'Mixed hold'
    return 'Limited follow-through'


def _fresh_active_mask(rows: pd.DataFrame) -> pd.Series:
    if rows.empty:
        return pd.Series(False, index=rows.index)
    current = _status_text(rows).eq('Active')
    if '_status_current' in rows:
        current = current & rows['_status_current'].fillna(False).astype(bool)
    elif 'Status Current' in rows:
        current = current & rows['Status Current'].fillna('').astype(str).str.casefold().eq('yes')
    elif any(name in rows for name in ['Latest Status Date', 'latest_trading_date_raw']) and any(name in rows for name in ['ticker_latest_bar_date', 'Ticker Latest Bar Date']):
        latest_status = pd.to_datetime(rows.get('Latest Status Date', rows.get('latest_trading_date_raw')), errors='coerce').dt.normalize()
        ticker_latest = pd.to_datetime(rows.get('ticker_latest_bar_date', rows.get('Ticker Latest Bar Date')), errors='coerce').dt.normalize()
        current = current & latest_status.notna() & ticker_latest.notna() & latest_status.eq(ticker_latest)
    return current


def _valid_review_support_mask(rows: pd.DataFrame) -> pd.Series:
    if rows.empty:
        return pd.Series(False, index=rows.index)
    valid = pd.Series(True, index=rows.index)
    if any(name in rows for name in ['_ticker_latest_bar_date', 'ticker_latest_bar_date', 'Ticker Latest Bar Date']):
        ticker_latest = pd.to_datetime(
            rows.get('_ticker_latest_bar_date', rows.get('ticker_latest_bar_date', rows.get('Ticker Latest Bar Date'))),
            errors='coerce',
        )
        valid = valid & ticker_latest.notna()
    return valid


def _trigger_quality_rows(history: pd.DataFrame, overview: dict) -> list[dict]:
    rows = []
    for label, window_rows in _report_windows(history, overview).items():
        if window_rows.empty or 'Trigger' not in window_rows:
            continue
        for trigger, group in window_rows.groupby(window_rows['Trigger'].fillna('').astype(str)):
            if not trigger or trigger == 'No Trigger':
                continue
            triggered = int(len(group))
            failed = int(_trigger_day_text(group).eq('Fail').sum())
            clean_active = int(_clean_active_mask(group).sum())
            median_max = _numeric_series(group, 'max_pct_raw').median()
            fail_pct = _pct(failed, triggered)
            rows.append({
                'trigger': trigger,
                'window': label,
                'sample': triggered,
                'failed': failed,
                'clean_active': clean_active,
                'median_max': None if pd.isna(median_max) else float(median_max),
                'fail_rate': fail_pct,
                'read': _trigger_quality_read(triggered, clean_active, fail_pct, median_max),
            })

    by_trigger: dict[str, dict[str, dict]] = {}
    for row in rows:
        by_trigger.setdefault(str(row.get('trigger')), {})[str(row.get('window'))] = row
    for trigger_rows in by_trigger.values():
        last5 = trigger_rows.get('Last 5')
        previous5 = trigger_rows.get('Previous 5')
        if not last5 or not previous5:
            continue
        fail_delta = _delta(last5.get('fail_rate'), previous5.get('fail_rate'))
        clean_delta = _delta(
            _pct(int(last5.get('clean_active', 0) or 0), int(last5.get('sample', 0) or 0)),
            _pct(int(previous5.get('clean_active', 0) or 0), int(previous5.get('sample', 0) or 0)),
        )
        if fail_delta is not None and fail_delta >= RATE_CHANGE_THRESHOLD:
            last5['read'] = 'Trigger weakened' if last5.get('read') != 'Elevated failures' else 'Elevated failures'
            last5['_change_signal'] = True
        elif fail_delta is not None and fail_delta <= -RATE_CHANGE_THRESHOLD:
            last5['read'] = 'Trigger improved'
            last5['_change_signal'] = True
        elif clean_delta is not None and abs(clean_delta) >= RATE_CHANGE_THRESHOLD:
            last5['read'] = 'Trigger improved' if clean_delta > 0 else 'Trigger weakened'
            last5['_change_signal'] = True

    def score(row: dict) -> tuple[int, int, float]:
        sample = int(row.get('sample', 0) or 0)
        fail_rate = float(row.get('fail_rate') or 0)
        median_max = float(row.get('median_max') or 0)
        if sample >= 3 and fail_rate >= 50:
            return (0, -sample, -fail_rate)
        if sample >= 3 and row.get('read') in {'Clean follow-through', 'Usable follow-through'}:
            return (1, -sample, -median_max)
        if sample >= 3 and row.get('_change_signal'):
            return (2, -sample, -abs(fail_rate))
        if row.get('window') == 'Latest' and (sample >= 3 or median_max >= 0.10):
            return (3, -sample, -median_max)
        if sample < 3:
            return (5, -sample, -median_max)
        return (4, -sample, -median_max)

    return sorted(rows, key=score)[:5]


def _notable_name_rows(notable_tickers: dict, portfolio: dict, history: pd.DataFrame | None = None) -> list[dict]:
    out = []
    seen = set()

    def add(item: dict, why: str, evidence: str | None = None) -> None:
        ticker = item.get('ticker')
        if not ticker or ticker in seen or len(out) >= 5:
            return
        seen.add(ticker)
        out.append({
            'ticker': ticker,
            'why': why,
            'evidence': evidence or f"Current {item.get('current', '-')}; Max {item.get('max', '-')}",
            'current': item.get('current', '-'),
            'max': item.get('max', '-'),
            'status': item.get('status', '-'),
        })

    rows = history.copy() if history is not None else pd.DataFrame()
    if not rows.empty:
        pairs = _valid_return_pair(rows)
        review_supported = _valid_review_support_mask(rows)
        giveback_index = pairs[(pairs['max'] >= 0.10) & (pairs['current'] / pairs['max'] < 0.5)].index
        giveback = rows.loc[giveback_index].copy()
        giveback = giveback[_fresh_active_mask(giveback) & review_supported.loc[giveback.index]]
        if not giveback.empty:
            giveback = giveback.assign(_sort_max=_numeric_series(giveback, 'max_pct_raw')).sort_values('_sort_max', ascending=False)
            for _, row in giveback.head(2).iterrows():
                add(
                    {
                        'ticker': _display(row.get('Ticker')),
                        'current': _return_text(row.get('current_pct_raw')),
                        'max': _return_text(row.get('max_pct_raw')),
                        'status': _display(row.get('Current Status')),
                    },
                    'Major giveback from large max move',
                    _row_return_evidence(row),
                )
        clean = rows[_clean_active_mask(rows) & _fresh_active_mask(rows) & _valid_review_support_mask(rows)].copy()
        if not clean.empty:
            clean = clean.assign(
                _sort_current=_numeric_series(clean, 'current_pct_raw'),
                _hold_ratio=clean.apply(_row_hold_ratio, axis=1),
            )
            clean = clean[clean['_hold_ratio'].isna() | clean['_hold_ratio'].ge(50)].sort_values('_sort_current', ascending=False)
            for _, row in clean.head(2).iterrows():
                add(
                    {
                        'ticker': _display(row.get('Ticker')),
                        'current': _return_text(row.get('current_pct_raw')),
                        'max': _return_text(row.get('max_pct_raw')),
                        'status': _display(row.get('Current Status')),
                    },
                    'Clean active leader',
                    _row_return_evidence(row),
                )
        retest_hold = rows[_clean_active_mask(rows) & _fresh_active_mask(rows) & _valid_review_support_mask(rows) & _retested_after_d0_mask(rows)].copy()
        if not retest_hold.empty:
            retest_hold = retest_hold.assign(_sort_current=_numeric_series(retest_hold, 'current_pct_raw')).sort_values('_sort_current', ascending=False)
            for _, row in retest_hold.head(1).iterrows():
                add(
                    {
                        'ticker': _display(row.get('Ticker')),
                        'current': _return_text(row.get('current_pct_raw')),
                        'max': _return_text(row.get('max_pct_raw')),
                        'status': _display(row.get('Current Status')),
                    },
                    'Retest hold',
                    f"Retests {_display(row.get('Retests'))}; {_row_return_evidence(row)}",
                )

    failed_rows = rows[_failed_after_d0_mask(rows) & _valid_review_support_mask(rows)].copy() if not rows.empty else pd.DataFrame()
    if not failed_rows.empty:
        failed_rows = failed_rows.assign(_sort_max=_numeric_series(failed_rows, 'max_pct_raw')).sort_values('_sort_max', ascending=False)
        for _, row in failed_rows.head(3).iterrows():
            add(
                {
                    'ticker': _display(row.get('Ticker')),
                    'current': _return_text(row.get('current_pct_raw', row.get('_current_sort'))),
                    'max': _return_text(row.get('max_pct_raw', row.get('_max_sort'))),
                    'status': _display(row.get('Current Status')),
                },
                'Max move later failed',
                _row_return_evidence(row, include_hold=False),
            )
    else:
        for item in notable_tickers.get('failed_after_initially_working', [])[:3]:
            add(item, 'Max move later failed')
    for item in notable_tickers.get('close_below_be', [])[:3]:
        add(item, 'Close < BE')
    for ticker in portfolio.get('top_current_progress', [])[:3]:
        add({'ticker': ticker, 'current': '-', 'max': '-', 'status': 'Portfolio'}, 'Clean active leader')
    return out


def _material_observations(history: pd.DataFrame, overview: dict, comparisons: dict, notable_tickers: dict, portfolio: dict) -> list[dict]:
    observations: list[dict] = []
    comparison_labels = {
        'latest_vs_prior': 'Latest setup date vs prior setup date',
        'latest_vs_last5': 'Latest setup date vs Last 5 setup dates',
        'last2_vs_last5': 'Last 2 setup dates vs Last 5 setup-date baseline',
        'last5_vs_previous5': 'Last 5 setup dates vs Previous 5 setup dates',
    }
    for label, pair in comparisons.items():
        name = comparison_labels.get(label, label.replace('_', ' ').title())
        current = pair.get('current', {})
        baseline = pair.get('baseline', {})
        checks = [
            _rate_observation(name, 'active', current, baseline, True, RATE_CHANGE_THRESHOLD, _meaning('active', _delta(current.get('active_pct'), baseline.get('active_pct')))),
            _rate_observation(name, 'failed_d0', current, baseline, False, RATE_CHANGE_THRESHOLD, _meaning('failed_d0', _delta(current.get('failed_d0_pct'), baseline.get('failed_d0_pct')))),
            _rate_observation(name, 'failed_after_d0', current, baseline, False, RATE_CHANGE_THRESHOLD, _meaning('failed_after_d0', _delta(current.get('failed_after_d0_pct'), baseline.get('failed_after_d0_pct')))),
            _rate_observation(name, 'close_below_be', current, baseline, False, CLOSE_BE_THRESHOLD, _meaning('close_below_be', _delta(current.get('close_below_be_pct'), baseline.get('close_below_be_pct')))),
            _rate_observation(name, 'retested_after_d0', current, baseline, False, RATE_CHANGE_THRESHOLD, _meaning('retested_after_d0', _delta(current.get('retested_after_d0_pct'), baseline.get('retested_after_d0_pct')))),
            _return_observation(name, 'median_current', current, baseline, True, 'showing whether names are holding current progress.'),
            _return_observation(name, 'median_max', current, baseline, True, 'showing whether names are still producing upside progress.'),
        ]
        observations.extend(item for item in checks if item is not None)
        max_delta = _delta(current.get('median_max'), baseline.get('median_max'))
        active_delta = _delta(current.get('active_pct'), baseline.get('active_pct'))
        if max_delta is not None and max_delta >= RETURN_CHANGE_THRESHOLD and (active_delta is None or active_delta < RATE_CHANGE_THRESHOLD):
            observations.append({
                'section': 'Short-Term Shifts' if label in {'last2_vs_last5', 'last5_vs_previous5'} else 'Current Read',
                'comparison': name,
                'metric': 'max_without_active',
                'metric_label': 'Median Max / Active %',
                'prior': f"{_return_text(baseline.get('median_max'))} / {_pct_text(baseline.get('active_pct'))}",
                'current': f"{_return_text(current.get('median_max'))} / {_pct_text(current.get('active_pct'))}",
                'change': _pts_text(max_delta * 100),
                'read': 'Max progress improved without active-rate improvement',
                'direction': 'mixed',
                'text': (
                    f"{name}: Median Max improved from {_return_text(baseline.get('median_max'))} to {_return_text(current.get('median_max'))} "
                    f"while Active % did not materially improve ({_pct_text(baseline.get('active_pct'))} to {_pct_text(current.get('active_pct'))}). "
                    "This flags movement that did not translate into active retention."
                ),
            })
    observations.extend(_trigger_observations(history, overview))
    if notable_tickers.get('top_active_by_current'):
        leaders = ', '.join(
            f"{item['ticker']} ({item['current']} current, {item['max']} max)"
            for item in notable_tickers['top_active_by_current'][:3]
        )
        observations.append({
            'section': 'Notable Names',
            'comparison': 'Current leaders',
            'metric': 'top_active',
            'direction': 'leader',
            'text': f"Top active names by Current %: {leaders}. This identifies where follow-through is still present.",
        })
    if notable_tickers.get('failed_after_initially_working'):
        faded = ', '.join(
            f"{item['ticker']} ({item['max']} max, {item['status']})"
            for item in notable_tickers['failed_after_initially_working'][:3]
        )
        observations.append({
            'section': 'Notable Names',
            'comparison': 'Faded leaders',
            'metric': 'failed_after_initially_working',
            'direction': 'risk',
            'text': f"Names with max progress that later failed include {faded}. This highlights movement that did not stay active.",
        })
    if portfolio.get('top_current_progress'):
        observations.append({
            'section': 'Portfolio Snapshot',
            'comparison': 'Current Progress',
            'metric': 'portfolio_leaders',
            'direction': 'leader',
            'text': (
                f"Current Progress portfolio has {portfolio.get('current_progress_count', 0)} qualifying names; "
                f"leaders are {', '.join(portfolio.get('top_current_progress', [])[:3])}."
            ),
        })
    limits = {'Current Read': 5, 'Trigger Read': 5, 'Short-Term Shifts': 4, 'Notable Names': 3, 'Portfolio Snapshot': 1}
    counts = {section: 0 for section in limits}
    filtered = []
    for item in observations:
        section = item.get('section')
        if section not in limits:
            continue
        if counts[section] >= limits[section]:
            continue
        filtered.append(item)
        counts[section] += 1
    return filtered


def build_daily_report_payload(history: pd.DataFrame, overview: dict) -> dict:
    history = history.copy() if history is not None else pd.DataFrame()
    overview = overview or {}
    comparisons = _comparison_payload(history, overview)
    notable_tickers = _notable_tickers(history)
    portfolio = _portfolio_summary(history)
    watchlist_pulse = _watchlist_pulse(history, overview)
    prepared_rows = _prepared_report_rows(history)
    return {
        'latest_setup_date_summary': _latest_setup_date_summary(history),
        'recent_window_summary': _recent_window_summary(history, overview),
        'watchlist_pulse': watchlist_pulse,
        'comparison_summary': comparisons,
        'trigger_summary': _trigger_summary(overview),
        'notable_tickers': notable_tickers,
        'trigger_read_rows': _trigger_read_rows(history),
        'trigger_failure_snapshot': _trigger_failure_snapshot(history, overview),
        'trigger_quality_rows': _trigger_quality_rows(history, overview),
        'notable_name_rows': _notable_name_rows(notable_tickers, portfolio, prepared_rows),
        'portfolio_summary': portfolio,
        'material_observations': _material_observations(history, overview, comparisons, notable_tickers, portfolio),
    }


def _line_for_count(label: str, payload: dict) -> str:
    return f"{label}: {payload.get('count', 0)} ({_pct_text(payload.get('pct'))})"


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return ''
    header = '| ' + ' | '.join(headers) + ' |'
    align = '| ' + ' | '.join(['---'] + ['---:' if name in {'Value', 'Count', 'Prior', 'Current', 'Triggered', 'Failed', 'Success', 'Failure Rate'} else '---' for name in headers[1:]]) + ' |'
    body = ['| ' + ' | '.join(str(value) for value in row) + ' |' for row in rows]
    return '\n'.join([header, align, *body])


def _count_text(payload: dict, total: int) -> str:
    return f"{payload.get('count', 0)} / {total}"


def _count_rate_text(count: int, total: int) -> str:
    return f"{int(count)} / {int(total)} ({_pct_text(_pct(int(count), int(total)))})"


def _compact_count_rate_text(count: int, total: int) -> str:
    pct = _pct(int(count), int(total))
    pct_text = '-' if pct is None else f'{pct:.0f}%'
    return f"{int(count)}/{int(total)} ({pct_text})"


def _threshold_text(payload: dict) -> str:
    return _count_rate_text(int(payload.get('count', 0) or 0), int(payload.get('total', 0) or 0))


def _hold_ratio_text(payload: dict) -> str:
    value = payload.get('value')
    count = int(payload.get('count', 0) or 0)
    if value is None:
        return '-'
    sample = ' sample' if count == 1 else ' samples'
    return f"{float(value):.1f}% ({count}{sample})"


def _days_text(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors='coerce').iloc[0]
    if pd.isna(numeric):
        return '-'
    return f'{numeric:.1f}'


def _watchlist_pulse_table(pulse: dict) -> str:
    windows = REPORT_WINDOWS
    rolling = pulse.get('Rolling Avg', {})

    def window(label: str) -> dict:
        return pulse.get(label, {})

    rows = [
        ['Setups', *[window(label).get('setup_count', 0) for label in windows], rolling.get('setup_count', 0) or '-'],
        [
            'Clean Active',
            *[_compact_count_rate_text(window(label).get('clean_active_count', 0), window(label).get('setup_count', 0)) for label in windows],
            _compact_count_rate_text(rolling.get('clean_active_count', 0), rolling.get('setup_count', 0)),
        ],
        [
            'Failed D0',
            *[_compact_count_rate_text(window(label).get('failed_d0_count', 0), window(label).get('setup_count', 0)) for label in windows],
            _compact_count_rate_text(rolling.get('failed_d0_count', 0), rolling.get('setup_count', 0)),
        ],
        [
            'Close < BE',
            *[_compact_count_rate_text(window(label).get('close_below_be_count', 0), window(label).get('setup_count', 0)) for label in windows],
            _compact_count_rate_text(rolling.get('close_below_be_count', 0), rolling.get('setup_count', 0)),
        ],
        ['Median Current %', *[_return_text(window(label).get('median_current')) for label in windows], _return_text(rolling.get('median_current'))],
        ['Median Max %', *[_return_text(window(label).get('median_max')) for label in windows], _return_text(rolling.get('median_max'))],
        ['Hold Ratio', *[_hold_ratio_text(window(label).get('hold_ratio', {})) for label in windows], _hold_ratio_text(rolling.get('hold_ratio', {}))],
    ]
    return _markdown_table(['Metric', *[_window_display(label) for label in windows], 'Rolling Avg'], rows)


def _trigger_failure_cell(cell: dict) -> str:
    triggered = int(cell.get('triggered', 0) or 0)
    if triggered <= 0:
        return '0 / - / -'
    failed = int(cell.get('failed', 0) or 0)
    fail_rate = cell.get('fail_rate')
    fail_text = '-' if fail_rate is None else f"{float(fail_rate):.0f}%"
    return f"{triggered} / {failed} / {fail_text}"


def _trigger_failure_snapshot_table(rows: list[dict]) -> str:
    table_rows = []
    for row in rows[:4]:
        cells = row.get('cells', {})
        table_rows.append([
            row.get('trigger', '-'),
            *[_trigger_failure_cell(cells.get(label, {})) for label in REPORT_WINDOWS],
            _trigger_failure_cell(cells.get('Rolling Avg', {})),
        ])
    return _markdown_table(['Trigger', *[_window_display(label) for label in REPORT_WINDOWS], 'Rolling Avg'], table_rows)


def _progression_quality_table(pulse: dict) -> str:
    rows = []
    windows = REPORT_WINDOWS
    include_days = any(pulse.get(label, {}).get('median_days_to_max') is not None for label in windows)
    for label in windows:
        window = pulse.get(label, {})
        thresholds = window.get('thresholds', {})
        row = [
            _window_display(label),
            window.get('setup_count', 0),
            _threshold_text(thresholds.get('5', {})),
            _threshold_text(thresholds.get('10', {})),
            _threshold_text(thresholds.get('20', {})),
            _count_rate_text(window.get('retested_after_d0_count', 0), window.get('setup_count', 0)),
        ]
        if include_days:
            row.insert(5, _days_text(window.get('median_days_to_max')))
        rows.append(row)
    headers = ['Setup Cohort', 'Setups', 'Reached +5%', 'Reached +10%', 'Reached +20%', 'Retested After D0']
    if include_days:
        headers.insert(5, 'Median Days to Max')
    return _markdown_table(headers, rows)


def _executive_snapshot_table(latest: dict) -> str:
    total = int(latest.get('setup_count', 0) or 0)
    rows = [
        ['Latest Setup Date', latest.get('latest_setup_date') or '-', '-'],
        ['Setups', str(total), str(total)],
        ['Active', _pct_text(latest.get('active', {}).get('pct')), _count_text(latest.get('active', {}), total)],
        ['Failed D0', _pct_text(latest.get('failed_d0', {}).get('pct')), _count_text(latest.get('failed_d0', {}), total)],
        ['Failed After D0', _pct_text(latest.get('failed_after_d0', {}).get('pct')), _count_text(latest.get('failed_after_d0', {}), total)],
        ['Close < BE', _pct_text(latest.get('close_below_be', {}).get('pct')), _count_text(latest.get('close_below_be', {}), total)],
        ['Retested After D0', _pct_text(latest.get('retested_after_d0', {}).get('pct')), _count_text(latest.get('retested_after_d0', {}), total)],
    ]
    unresolved = latest.get('unresolved', {})
    if int(unresolved.get('count', 0) or 0) > 0:
        rows.insert(5, ['Unresolved', _pct_text(unresolved.get('pct')), _count_text(unresolved, total)])
    retested_d0 = latest.get('retested_d0_only', {})
    if int(retested_d0.get('count', 0) or 0) > 0 and float(retested_d0.get('pct', 0) or 0) >= 25:
        rows.append(['Retested D0 Only', _pct_text(retested_d0.get('pct')), _count_text(retested_d0, total)])
    return _markdown_table(['Metric', 'Value', 'Count'], rows)


def _change_magnitude(item: dict) -> float:
    value = pd.to_numeric(
        str(item.get('change', '0')).replace('pts', '').replace('+', '').strip(),
        errors='coerce',
    )
    return 0.0 if pd.isna(value) else abs(float(value))


def _key_shift_items(observations: list[dict], limit: int = 5) -> list[dict]:
    priorities = {
        'active': 0,
        'failed_d0': 1,
        'failed_after_d0': 2,
        'close_below_be': 3,
        'retested_after_d0': 4,
        'max_without_active': 5,
        'median_current': 6,
        'median_max': 7,
    }
    candidates = [
        item for item in observations
        if item.get('section') in {'Current Read', 'Short-Term Shifts'}
    ]
    best_by_metric: dict[str, dict] = {}
    for item in candidates:
        metric = str(item.get('metric', ''))
        change = _change_magnitude(item)
        existing = best_by_metric.get(metric)
        existing_change = -1 if existing is None else _change_magnitude(existing)
        if existing is None or change > existing_change:
            best_by_metric[metric] = item
    return sorted(
        best_by_metric.values(),
        key=lambda item: (priorities.get(str(item.get('metric')), 99), -_change_magnitude(item), str(item.get('comparison'))),
    )[:limit]


def _short_comparison_label(label: str) -> str:
    mapping = {
        'Latest setup date vs prior setup date': 'Latest vs Prior',
        'Latest setup date vs Last 5 setup dates': 'Latest vs Last 5',
        'Last 2 setup dates vs Last 5 setup-date baseline': 'Last 2 vs Last 5',
        'Last 5 setup dates vs Previous 5 setup dates': 'Last 5 vs Previous 5',
    }
    return mapping.get(label, label or '-')


def _comparison_phrase(label: str) -> str:
    mapping = {
        'Latest setup date vs prior setup date': 'versus prior setup date',
        'Latest setup date vs Last 5 setup dates': 'versus Last 5 setup dates',
        'Last 2 setup dates vs Last 5 setup-date baseline': 'versus the Last 5 baseline',
        'Last 5 setup dates vs Previous 5 setup dates': 'versus Previous 5 setup dates',
    }
    return mapping.get(label, f"for {_short_comparison_label(label)}")


def _shift_area(metric: str) -> str:
    mapping = {
        'active': 'Current Status',
        'failed_d0': 'Setup Failures',
        'failed_after_d0': 'Later Failures',
        'close_below_be': 'Weak Closes',
        'retested_after_d0': 'Retests',
        'max_without_active': 'Follow-Through',
        'median_current': 'Current Progress',
        'median_max': 'Max Progress',
    }
    return mapping.get(metric, metric.replace('_', ' ').title())


def _read_parts(read: str) -> tuple[str, bool]:
    parts = [part.strip() for part in str(read or 'Material shift').split(';') if part.strip()]
    return parts[0] if parts else 'Material shift', any(part == 'Small sample' for part in parts[1:])


def _summary_lead(metric: str, read: str) -> str:
    improved = not read.lower().startswith(('more ', 'weaker '))
    if metric == 'active':
        return 'Latest batch held better' if improved else 'Active retention weakened'
    if metric == 'failed_d0':
        return 'Setup-day failures eased' if improved else 'Setup-day failures increased'
    if metric == 'failed_after_d0':
        return 'Later failures eased' if improved else 'Later failures increased'
    if metric == 'close_below_be':
        return 'Weak closes eased' if improved else 'Weak closes increased'
    if metric == 'retested_after_d0':
        return 'Delayed retests eased' if improved else 'Delayed retests increased'
    if metric == 'median_current':
        return 'Current progress improved' if improved else 'Current progress weakened'
    if metric == 'median_max':
        return 'Max progress improved' if improved else 'Max progress weakened'
    return read


def _material_shifts_table(observations: list[dict]) -> str:
    selected = _key_shift_items(observations)
    rows = [
        [
            _shift_area(str(item.get('metric', ''))),
            _read_parts(item.get('read', '-'))[0],
            f"{_short_comparison_label(item.get('comparison', '-'))}: {item.get('prior', '-')} -> {item.get('current', '-')}",
            'Small sample' if _read_parts(item.get('read', '-'))[1] else 'Material shift',
        ]
        for item in selected
    ]
    return _markdown_table(['Area', 'Change', 'Evidence', 'Read'], rows)


def _trigger_read_items(rows: list[dict], limit: int = 5) -> list[dict]:
    def score(row: dict) -> tuple[int, int]:
        triggered = int(row.get('triggered', 0))
        failed = int(row.get('failed', 0))
        if triggered >= 3 and failed:
            return (0, -triggered)
        if row.get('window') == 'Latest':
            return (1, -triggered)
        if triggered >= 3:
            return (2, -triggered)
        return (3, -triggered)

    return sorted(rows, key=score)[:limit]


def _trigger_read_table(rows: list[dict]) -> str:
    selected = _trigger_read_items(rows)
    return _markdown_table(
        ['Trigger', 'Window', 'Evidence', 'Read'],
        [
            [
                row['trigger'],
                row['window'],
                f"{row['triggered']} triggered, {row['failed']} failed, {row['success']} success ({row['failure_rate']} fail)",
                row['read'],
            ]
            for row in selected
        ],
    )


def _trigger_quality_table(rows: list[dict]) -> str:
    selected = rows[:5]
    return _markdown_table(
        ['Trigger', 'Window', 'Sample', 'Clean Active', 'Median Max %', 'Fail Rate', 'Read'],
        [
            [
                row.get('trigger', '-'),
                _window_display(row.get('window', '-')),
                int(row.get('sample', 0) or 0),
                _count_rate_text(row.get('clean_active', 0), row.get('sample', 0)),
                _return_text(row.get('median_max')),
                _pct_text(row.get('fail_rate')),
                row.get('read', '-'),
            ]
            for row in selected
        ],
    )


def _notable_names_table(rows: list[dict]) -> str:
    return _markdown_table(
        ['Ticker', 'Review Reason', 'Evidence', 'Status'],
        [[row['ticker'], row['why'], row.get('evidence', '-'), row['status']] for row in rows[:5]],
    )


def _portfolio_snapshot_line(portfolio: dict) -> str:
    leaders = ', '.join(portfolio.get('top_current_progress', [])[:3]) or '-'
    return (
        f"Current Progress portfolio: {portfolio.get('current_progress_count', 0)} qualifying names. "
        f"Leaders: {leaders}. Median current progress: {_return_text(portfolio.get('median_current_progress'))}."
    )


def _summary_read_lines(report_payload: dict) -> list[str]:
    pulse = report_payload.get('watchlist_pulse', {})
    trigger_rows = report_payload.get('trigger_quality_rows', [])
    lines: list[str] = []

    last5 = pulse.get('Last 5', {})
    previous5 = pulse.get('Previous 5', {})
    latest = pulse.get('Latest', {})

    if last5 and previous5:
        clean_delta = _delta(last5.get('clean_active_pct'), previous5.get('clean_active_pct'))
        if clean_delta is not None:
            label = 'cleaner' if clean_delta > 0 else 'weaker' if clean_delta < 0 else 'stable'
            lines.append(
                f"- Recent 5 are {label}: Clean Active "
                f"{_compact_count_rate_text(last5.get('clean_active_count', 0), last5.get('setup_count', 0))} vs "
                f"Prior 5 at {_compact_count_rate_text(previous5.get('clean_active_count', 0), previous5.get('setup_count', 0))}."
            )

    thresholds = last5.get('thresholds', {}) if last5 else {}
    if thresholds:
        ten = thresholds.get('10', {})
        twenty = thresholds.get('20', {})
        lines.append(
            f"- Follow-through is broad: {_compact_count_rate_text(ten.get('count', 0), ten.get('total', 0))} reached +10%, with "
            f"{_compact_count_rate_text(twenty.get('count', 0), twenty.get('total', 0))} reaching +20% in Recent 5."
        )

    hold = last5.get('hold_ratio', {}) if last5 else {}
    if hold.get('value') is not None and len(lines) < 4:
        lines.append(
            f"- Hold quality is strong among clean active names: {_hold_ratio_text(hold)} retained from max progress in Recent 5 setup dates."
        )
    elif latest.get('hold_ratio', {}).get('value') is not None and len(lines) < 4:
        lines.append(
            f"- Hold quality is visible in the latest batch: {_hold_ratio_text(latest.get('hold_ratio', {}))} retained from max progress."
        )

    if trigger_rows and len(lines) < 4:
        row = trigger_rows[0]
        sample = int(row.get('sample', 0) or 0)
        small = ' Small sample.' if sample < 3 else ''
        lines.append(
            f"- {row.get('trigger', '-')} is the weak trigger: {sample} samples, "
            f"{int(row.get('failed', 0) or 0)} failed ({_whole_pct_text(row.get('fail_rate'))}), "
            f"{row.get('clean_active', 0)} clean active, "
            f"{_return_text(row.get('median_max'))} median max in {_window_display(row.get('window', '-'))}.{small}"
        )

    return lines[:4]


def render_daily_report_markdown(report_payload: dict) -> str:
    no_data = 'No reportable watchlist behavior data is available.'
    pulse_table = _watchlist_pulse_table(report_payload.get('watchlist_pulse', {}))
    trigger_failure_table = _trigger_failure_snapshot_table(report_payload.get('trigger_failure_snapshot', []))
    progression_table = _progression_quality_table(report_payload.get('watchlist_pulse', {}))
    trigger_table = _trigger_quality_table(report_payload.get('trigger_quality_rows', []))
    names_table = _notable_names_table(report_payload.get('notable_name_rows', []))
    summary = _summary_read_lines(report_payload)

    lines = [
        '# Daily Intelligence Report',
        '',
        '## Summary Read',
        *(summary or [no_data]),
        '',
        '## Watchlist Pulse',
        pulse_table or no_data,
        '',
        '## Trigger Failure Snapshot',
        'Format: Triggered / Failed / Fail %',
        '',
        trigger_failure_table or no_data,
        '',
        '## Progression Quality by Setup Cohort',
        'Thresholds use max move; older setup cohorts have had more time to reach levels.',
        '',
        progression_table or no_data,
        '',
        '## Trigger Quality',
        trigger_table or no_data,
        '',
        '## Names to Review',
        names_table or no_data,
        '',
        '## Portfolio Snapshot',
        _portfolio_snapshot_line(report_payload.get('portfolio_summary', {})),
        '',
    ]
    return '\n'.join(lines)


def build_llm_report_prompt(report_payload: dict) -> str:
    structured_summary = json.dumps(report_payload, indent=2, default=str)
    return (
        'Summarize the following structured Watchlist Behavior Monitor metrics only from the provided data.\n'
        'Do not make trade recommendations. Do not infer from raw database rows. Use the Summary Read, '
        'Watchlist Pulse, Trigger Failure Snapshot, Progression Quality by Setup Cohort, Trigger Quality, Names to Review, and Portfolio Snapshot fields when present. Call out notable '
        'shifts, data limitations, and keep the report concise.\n\n'
        f'STRUCTURED_SUMMARY:\n{structured_summary}'
    )
