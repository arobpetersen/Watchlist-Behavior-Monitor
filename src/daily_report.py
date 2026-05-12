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
RATE_CHANGE_THRESHOLD = 15.0
CLOSE_BE_THRESHOLD = 10.0
RETURN_CHANGE_THRESHOLD = 0.03
COUNT_CHANGE_THRESHOLD = 3


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


def _pts_text(value: float | None) -> str:
    if value is None:
        return '-'
    sign = '+' if value > 0 else ''
    return f'{sign}{value:.1f} pts'


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
            read = 'Small sample' if triggered < 3 else 'Elevated failures' if _pct(failed, triggered) is not None and _pct(failed, triggered) >= 50 else 'Tracked trigger behavior'
            rows.append({
                'trigger': trigger,
                'window': label,
                'triggered': triggered,
                'failed': failed,
                'success': success,
                'failure_rate': _pct_text(_pct(failed, triggered)),
                'read': read,
            })
    return rows[:10]


def _notable_name_rows(notable_tickers: dict, portfolio: dict) -> list[dict]:
    out = []
    seen = set()

    def add(item: dict, why: str) -> None:
        ticker = item.get('ticker')
        if not ticker or ticker in seen or len(out) >= 5:
            return
        seen.add(ticker)
        out.append({
            'ticker': ticker,
            'why': why,
            'current': item.get('current', '-'),
            'max': item.get('max', '-'),
            'status': item.get('status', '-'),
        })

    for item in notable_tickers.get('top_active_by_current', [])[:3]:
        add(item, 'Top active mover')
    for item in notable_tickers.get('failed_after_initially_working', [])[:3]:
        add(item, 'Max move later failed')
    for item in notable_tickers.get('close_below_be', [])[:3]:
        add(item, 'Close < BE')
    for ticker in portfolio.get('top_current_progress', [])[:3]:
        add({'ticker': ticker, 'current': '-', 'max': '-', 'status': 'Portfolio'}, 'Portfolio name')
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
    return {
        'latest_setup_date_summary': _latest_setup_date_summary(history),
        'recent_window_summary': _recent_window_summary(history, overview),
        'comparison_summary': comparisons,
        'trigger_summary': _trigger_summary(overview),
        'notable_tickers': notable_tickers,
        'trigger_read_rows': _trigger_read_rows(history),
        'notable_name_rows': _notable_name_rows(notable_tickers, portfolio),
        'portfolio_summary': portfolio,
        'material_observations': _material_observations(history, overview, comparisons, notable_tickers, portfolio),
    }


def _line_for_count(label: str, payload: dict) -> str:
    return f"{label}: {payload.get('count', 0)} ({_pct_text(payload.get('pct'))})"


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return ''
    header = '| ' + ' | '.join(headers) + ' |'
    align = '| ' + ' | '.join(['---'] + ['---:' if name in {'Value', 'Count', 'Prior', 'Current', 'Change', 'Triggered', 'Failed', 'Success', 'Failure Rate'} else '---' for name in headers[1:]]) + ' |'
    body = ['| ' + ' | '.join(str(value) for value in row) + ' |' for row in rows]
    return '\n'.join([header, align, *body])


def _count_text(payload: dict, total: int) -> str:
    return f"{payload.get('count', 0)} / {total}"


def _executive_snapshot_table(latest: dict) -> str:
    total = int(latest.get('setup_count', 0) or 0)
    rows = [
        ['Latest Setup Date', latest.get('latest_setup_date') or '-', '-'],
        ['Setups', str(total), str(total)],
        ['Active', _pct_text(latest.get('active', {}).get('pct')), _count_text(latest.get('active', {}), total)],
        ['Failed D0', _pct_text(latest.get('failed_d0', {}).get('pct')), _count_text(latest.get('failed_d0', {}), total)],
        ['Failed After D0', _pct_text(latest.get('failed_after_d0', {}).get('pct')), _count_text(latest.get('failed_after_d0', {}), total)],
        ['Unresolved', _pct_text(latest.get('unresolved', {}).get('pct')), _count_text(latest.get('unresolved', {}), total)],
        ['Close < BE', _pct_text(latest.get('close_below_be', {}).get('pct')), _count_text(latest.get('close_below_be', {}), total)],
        ['Retested D0 Only', _pct_text(latest.get('retested_d0_only', {}).get('pct')), _count_text(latest.get('retested_d0_only', {}), total)],
        ['Retested After D0', _pct_text(latest.get('retested_after_d0', {}).get('pct')), _count_text(latest.get('retested_after_d0', {}), total)],
    ]
    return _markdown_table(['Metric', 'Value', 'Count'], rows)


def _material_shifts_table(observations: list[dict]) -> str:
    rows = [
        [
            item.get('comparison', '-'),
            item.get('metric_label') or item.get('metric', '-'),
            item.get('prior', '-'),
            item.get('current', '-'),
            item.get('change', '-'),
            item.get('read', '-'),
        ]
        for item in observations
        if item.get('section') in {'Current Read', 'Short-Term Shifts'}
    ]
    return _markdown_table(['Comparison', 'Metric', 'Prior', 'Current', 'Change', 'Read'], rows)


def _trigger_read_table(rows: list[dict]) -> str:
    return _markdown_table(
        ['Trigger', 'Window', 'Triggered', 'Failed', 'Success', 'Failure Rate', 'Read'],
        [
            [row['trigger'], row['window'], row['triggered'], row['failed'], row['success'], row['failure_rate'], row['read']]
            for row in rows
        ],
    )


def _notable_names_table(rows: list[dict]) -> str:
    return _markdown_table(
        ['Ticker', 'Why Notable', 'Current %', 'Max %', 'Status'],
        [[row['ticker'], row['why'], row['current'], row['max'], row['status']] for row in rows],
    )


def _portfolio_snapshot_table(portfolio: dict) -> str:
    leaders = ', '.join(portfolio.get('top_current_progress', [])[:3]) or '-'
    longest = ', '.join(portfolio.get('longest_open', [])[:3]) or '-'
    rows = [
        ['Qualifying names', portfolio.get('current_progress_count', 0)],
        ['Leaders', leaders],
        ['Longest Open', longest],
        ['Rated 5 / Rated 4', f"{portfolio.get('rated_5_count', 0)} / {portfolio.get('rated_4_count', 0)}"],
    ]
    return _markdown_table(['Metric', 'Value'], rows)


def render_daily_report_markdown(report_payload: dict) -> str:
    latest = report_payload.get('latest_setup_date_summary', {})
    observations = report_payload.get('material_observations', [])

    no_shift = 'No material behavior shifts detected across the selected comparison windows.'
    material_table = _material_shifts_table(observations)
    trigger_table = _trigger_read_table(report_payload.get('trigger_read_rows', []))
    names_table = _notable_names_table(report_payload.get('notable_name_rows', []))

    lines = [
        '# Daily Intelligence Report',
        '',
        '## Executive Snapshot',
        _executive_snapshot_table(latest),
        '',
        '## Material Shifts',
        material_table or no_shift,
        '',
        '## Trigger Read',
        trigger_table or no_shift,
        '',
        '## Notable Names',
        names_table or no_shift,
        '',
        '## Portfolio Snapshot',
        _portfolio_snapshot_table(report_payload.get('portfolio_summary', {})),
        '',
    ]
    if not observations:
        lines.insert(4, no_shift)
    return '\n'.join(lines)


def build_llm_report_prompt(report_payload: dict) -> str:
    structured_summary = json.dumps(report_payload, indent=2, default=str)
    return (
        'Summarize the following structured Watchlist Behavior Monitor metrics only from the provided data.\n'
        'Do not make trade recommendations. Do not infer from raw database rows. Use the Executive Snapshot, '
        'Material Shifts, Trigger Read, Notable Names, and Portfolio Snapshot fields when present. Call out notable '
        'shifts, data limitations, and keep the report concise.\n\n'
        f'STRUCTURED_SUMMARY:\n{structured_summary}'
    )
