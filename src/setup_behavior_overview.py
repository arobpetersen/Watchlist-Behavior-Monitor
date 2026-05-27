from __future__ import annotations

from dataclasses import dataclass
from html import escape
import re
from time import perf_counter
from typing import Any

import pandas as pd

from src.d3_high_eligibility import eligible_d3_high_pct
from src.failure_timing import failure_timing_distribution
from src.rolling_setup_monitor import rolling_setup_monitor
from src.trigger_resolution import resolve_display_triggers, vwap_superseded_orh_display_values
from src.vwap_reclaim import assess_vwap_reclaim


FULL_SUMMARY_COLUMNS = [
    'Window',
    'Dates',
    'Setup Dates',
    'Setups',
    'Day Success',
    'Day Fail',
    'Unresolved',
    'Active',
    'Failed After D0',
    'Clean 1m',
    'Failed 1m',
    'Clean 5m',
    'Failed 5m',
    'VWAP Reclaim',
    'PDH',
    'Failed PDH Trigger',
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
    'Day Success %',
    'Active %',
    'Failed After D0 %',
    'Median Current',
    'Median Max',
]

SUMMARY_COLUMNS = COMPARISON_COLUMNS

DETAIL_COLUMNS = [
    'Setup Date',
    'Ticker',
    'Current Status',
    'Trigger Day',
    'Trigger',
    'PDH',
    '1m ORH',
    'VWAP Reclaim',
    '5m ORH',
    'Notes',
    'Current',
    'Max',
    'Close < BE',
    'D3 High',
    'Retests',
    'Setup',
    'Entry Tactic',
    'Rating',
]

CURRENT_STATUS_PRIORITY = {
    'Active': 0,
    'Failed D0': 1,
    'Later Failed': 2,
    'Failed': 2,
    'Failed D1': 3,
    'Failed D2': 4,
    'Failed D3': 5,
    '—': 6,
}
OPENING_PATH_FILTER_OPTIONS = [
    'All',
    'Clean 1m ORH Success',
    '1m ORH Failed, Later Reclaimed',
    '1m ORH Failed, Never Recovered',
    '5m ORH Success After 1m Failure',
    'PDH Success After Early Noise',
    'Alt Required Success',
    'Failed All Opening Triggers',
]


@dataclass(frozen=True)
class OverviewWindow:
    label: str
    setup_dates: tuple[pd.Timestamp, ...]

    @property
    def start_date(self) -> pd.Timestamp | None:
        return min(self.setup_dates) if self.setup_dates else None

    @property
    def end_date(self) -> pd.Timestamp | None:
        return max(self.setup_dates) if self.setup_dates else None


def _date(value: Any) -> pd.Timestamp:
    return pd.Timestamp(pd.to_datetime(value).date())


def _fmt_date(value: pd.Timestamp | None) -> str:
    if value is None:
        return '-'
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


def _pct_from_count_text(value: Any) -> str:
    text = str(value)
    if '(' not in text or ')' not in text:
        return '-'
    return text.split('(', 1)[1].split(')', 1)[0]


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


def _status_priority(value: Any) -> int:
    text = _display(value)
    if text == 'Active':
        return 0
    if text.startswith('Failed D'):
        try:
            return 1 + int(float(text.removeprefix('Failed D')))
        except (TypeError, ValueError):
            return 50
    if text in {'Failed', 'Later Failed'}:
        return 50
    return 99


def overview_windows(setup_date_values) -> list[OverviewWindow]:
    if isinstance(setup_date_values, (str, pd.Timestamp)) or not hasattr(setup_date_values, '__iter__'):
        dates = [_date(setup_date_values)]
    else:
        dates = sorted({_date(value) for value in setup_date_values})
    return [
        OverviewWindow('Last 2 Setup Dates', tuple(dates[-2:])),
        OverviewWindow('Last 5 Setup Dates', tuple(dates[-5:])),
        OverviewWindow('Previous 5 Setup Dates', tuple(dates[-10:-5])),
        OverviewWindow('Last 10 Setup Dates', tuple(dates[-10:])),
        OverviewWindow('Last 20 Setup Dates', tuple(dates[-20:])),
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


def monitor_history(con, perf=None) -> pd.DataFrame:
    start = perf_counter()
    dates = setup_dates(con)
    if perf is not None:
        perf.add('monitor_history SQL: setup dates', perf_counter() - start)
    if not dates:
        return pd.DataFrame()
    start = perf_counter()
    try:
        sections = rolling_setup_monitor(con, setup_dates=len(dates), perf=perf)
    except TypeError:
        sections = rolling_setup_monitor(con, setup_dates=len(dates))
    if perf is not None:
        perf.add('monitor_history rolling sections build', perf_counter() - start)
    start = perf_counter()
    frames = []
    for section in sections:
        table = section['table'].copy()
        table['Setup Date'] = section['setup_date']
        frames.append(table)
    if not frames:
        return pd.DataFrame()
    history = pd.concat(frames, ignore_index=True)
    history['Setup Date'] = pd.to_datetime(history['Setup Date'])
    if perf is not None:
        perf.add('monitor_history concat/normalize', perf_counter() - start)
    start = perf_counter()
    history = _add_vwap_reclaim_events(con, history, perf=perf)
    if perf is not None:
        perf.add('monitor_history VWAP/display trigger pass', perf_counter() - start)
    return history


def _vwap_reclaim_defaults(history: pd.DataFrame) -> pd.DataFrame:
    out = history.copy()
    audit_columns = {
        'Raw VWAP Reclaim Prior Below VWAP',
        'Raw VWAP Reclaim Bar Open',
        'Raw VWAP Reclaim Bar High',
        'Raw VWAP Reclaim Bar Low',
        'Raw VWAP Reclaim Bar Close',
        'Raw VWAP Reclaim Trigger Price',
        'Raw VWAP Reclaim Trigger LOD Reference',
        'Raw VWAP Reclaim Post-Trigger High',
        'Raw VWAP Reclaim Post-Trigger Low',
        'Raw VWAP Reclaim Post-Trigger Stop Breached',
    }
    for column, value in {
        'VWAP Trigger': '',
        'VWAP Trigger Reason': '',
        'Raw VWAP Reclaim Result': 'Not Applicable',
        'Raw VWAP Reclaim Prior Below VWAP': None,
        'Raw VWAP Reclaim Time': '',
        'Raw VWAP Reclaim Bar Open': None,
        'Raw VWAP Reclaim Bar High': None,
        'Raw VWAP Reclaim Bar Low': None,
        'Raw VWAP Reclaim Bar Close': None,
        'Raw VWAP Reclaim Trigger Time': '',
        'Raw VWAP Reclaim Trigger Price': None,
        'Raw VWAP Reclaim Trigger LOD Reference': None,
        'Raw VWAP Reclaim Reference Basis': '',
        'Raw VWAP Reclaim Post-Trigger High': None,
        'Raw VWAP Reclaim Post-Trigger Low': None,
        'Raw VWAP Reclaim Post-Trigger Stop Breached': None,
        'Raw VWAP Reclaim Result Reason': 'intraday bars unavailable',
    }.items():
        if column not in out:
            out[column] = value
        if column in audit_columns:
            out[column] = out[column].astype(object)
    return out


def _add_vwap_reclaim_events(con, history: pd.DataFrame, perf=None) -> pd.DataFrame:
    """Attach raw VWAP diagnostics and qualified VWAP trigger display fields."""
    history = _vwap_reclaim_defaults(history)
    if history.empty or 'Ticker' not in history or 'Setup Date' not in history:
        return history

    tickers = sorted(history['Ticker'].dropna().astype(str).unique())
    setup_dates = sorted(pd.to_datetime(history['Setup Date'], errors='coerce').dt.date.dropna().astype(str).unique())
    if not tickers or not setup_dates:
        return history

    ticker_placeholders = ','.join(['?'] * len(tickers))
    date_placeholders = ','.join(['?'] * len(setup_dates))
    try:
        start = perf_counter()
        bars = con.execute(
            f"""
            select ticker, trading_date, timestamp_et, open, high, low, close, volume
            from intraday_bars_1m
            where ticker in ({ticker_placeholders})
              and cast(trading_date as varchar) in ({date_placeholders})
            order by ticker, trading_date, timestamp_et
            """,
            tickers + setup_dates,
        ).df()
        if perf is not None:
            perf.add('monitor_history SQL: VWAP intraday bars', perf_counter() - start)
    except Exception:
        return history

    if bars.empty:
        return history

    start = perf_counter()
    bars['ticker'] = bars['ticker'].astype(str)
    bars['trading_date'] = pd.to_datetime(bars['trading_date'], errors='coerce').dt.date.astype(str)
    grouped = {
        (ticker, trading_date): group.copy()
        for (ticker, trading_date), group in bars.groupby(['ticker', 'trading_date'], dropna=False)
    }

    for idx, row in history.iterrows():
        ticker = str(row.get('Ticker', ''))
        setup_date = pd.to_datetime(row.get('Setup Date'), errors='coerce')
        if not ticker or pd.isna(setup_date):
            continue
        result = assess_vwap_reclaim(grouped.get((ticker, setup_date.date().isoformat())), setup_date=setup_date)
        history.at[idx, 'Raw VWAP Reclaim Result'] = result.get('result') or ''
        history.at[idx, 'Raw VWAP Reclaim Prior Below VWAP'] = result.get('prior_below_vwap_observed')
        history.at[idx, 'Raw VWAP Reclaim Time'] = result.get('reclaim_time') or ''
        history.at[idx, 'Raw VWAP Reclaim Bar Open'] = result.get('reclaim_bar_open')
        history.at[idx, 'Raw VWAP Reclaim Bar High'] = result.get('reclaim_bar_high')
        history.at[idx, 'Raw VWAP Reclaim Bar Low'] = result.get('reclaim_bar_low')
        history.at[idx, 'Raw VWAP Reclaim Bar Close'] = result.get('reclaim_bar_close')
        history.at[idx, 'Raw VWAP Reclaim Trigger Time'] = result.get('trigger_time') or ''
        history.at[idx, 'Raw VWAP Reclaim Trigger Price'] = result.get('trigger_price')
        history.at[idx, 'Raw VWAP Reclaim Trigger LOD Reference'] = result.get('vwap_trigger_lod_reference')
        history.at[idx, 'Raw VWAP Reclaim Reference Basis'] = result.get('vwap_reference_basis') or ''
        history.at[idx, 'Raw VWAP Reclaim Post-Trigger High'] = result.get('post_trigger_high')
        history.at[idx, 'Raw VWAP Reclaim Post-Trigger Low'] = result.get('post_trigger_low')
        history.at[idx, 'Raw VWAP Reclaim Post-Trigger Stop Breached'] = result.get('post_trigger_stop_breached')
        history.at[idx, 'Raw VWAP Reclaim Result Reason'] = result.get('result_reason') or result.get('failure_reason') or ''
    if perf is not None:
        perf.add('monitor_history derivation: raw VWAP reclaim', perf_counter() - start)
    start = perf_counter()
    history = resolve_display_triggers(history)
    if perf is not None:
        perf.add('monitor_history derivation: final trigger resolution', perf_counter() - start)
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
        included = {date.date() for date in window.setup_dates}
        rows = history[setup_dates_series.dt.date.isin(included)].copy()

    setups = len(rows)
    setup_dates_count = 0 if rows.empty else int(rows['Setup Date'].nunique())

    def count_fmt(count: int) -> str:
        return _fmt_count(count, setups)

    current_status = rows['Current Status'] if 'Current Status' in rows else pd.Series(dtype=object)
    trigger_day = rows['Trigger Day'] if 'Trigger Day' in rows else pd.Series(dtype=object)
    trigger = rows['Trigger'] if 'Trigger' in rows else pd.Series(dtype=object)
    pdh = rows['PDH'] if 'PDH' in rows else pd.Series(dtype=object)
    one, five = _visible_orh_results(rows) if not rows.empty else (pd.Series(dtype=object), pd.Series(dtype=object))
    notes = rows['Notes'] if 'Notes' in rows else pd.Series(dtype=object)
    retest = rows['Retests'] if 'Retests' in rows else rows['Retest Day'] if 'Retest Day' in rows else pd.Series(dtype=object)

    d3_values = eligible_d3_high_pct(rows).dropna()

    return {
        'Window': window.label,
        'Dates': f'{_fmt_date(window.start_date)} \u2192 {_fmt_date(window.end_date)}',
        'Setup Dates': setup_dates_count,
        'Setups': setups,
        'Day Success': count_fmt(_count(trigger_day, 'Success')),
        'Day Fail': count_fmt(_count(trigger_day, 'Fail')),
        'Unresolved': count_fmt(_count(trigger_day, 'Unresolved')),
        'Active': count_fmt(_count(current_status, 'Active')),
        'Failed After D0': count_fmt(int(_is_later_failed(current_status).sum())),
        'Clean 1m': count_fmt(_count(one, 'success')),
        'Failed 1m': count_fmt(_count(one, 'failed')),
        'Clean 5m': count_fmt(_count(five, 'success')),
        'Failed 5m': count_fmt(_count(five, 'failed')),
        'VWAP Reclaim': count_fmt(_count(_qualified_vwap_values(rows), 'success')),
        'PDH': count_fmt(_count(trigger, 'PDH')),
        'Failed PDH Trigger': count_fmt(_count(trigger, 'Failed PDH Trigger')),
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
    included = {date.date() for date in window.setup_dates}
    rows = history[setup_dates_series.dt.date.isin(included)].copy()
    if rows.empty:
        return pd.DataFrame(columns=DETAIL_COLUMNS)

    vwap_trigger = _qualified_vwap_values(rows)
    one_min_result, five_min_result = _visible_orh_results(rows)
    retests = rows['Retests'] if 'Retests' in rows else rows['Retest Day'] if 'Retest Day' in rows else pd.Series('', index=rows.index)
    out = pd.DataFrame({
        'Setup Date': pd.to_datetime(rows['Setup Date']).dt.date.astype(str),
        'Ticker': rows['Ticker'].apply(_display),
        'Current Status': rows['Current Status'].apply(_display),
        'Trigger Day': rows['Trigger Day'].apply(_display),
        'Trigger': rows['Trigger'].apply(_display),
        'PDH': rows['PDH'].apply(_display) if 'PDH' in rows else '-',
        '1m ORH': one_min_result.replace('superseded', '-'),
        'VWAP Reclaim': vwap_trigger.apply(_display),
        '5m ORH': five_min_result.replace('superseded', '-'),
        'Notes': rows['Notes'].apply(_display),
        'Current': rows['Current %'].apply(_display),
        'Max': rows['Max %'].apply(_display),
        'Close < BE': rows['Close < BE'].apply(_display) if 'Close < BE' in rows else '-',
        'D3 High': rows['D3 High %'].apply(_display),
        'Retests': retests.apply(_display),
        'Setup': rows['Setup'].apply(_display),
        'Entry Tactic': rows['Entry Tactic'].apply(_display) if 'Entry Tactic' in rows else '-',
        'Rating': rows['Rating'].apply(_display),
    })
    out['_status_priority'] = out['Current Status'].apply(_status_priority)
    out['_current_sort'] = pd.to_numeric(out['Current'].str.rstrip('%'), errors='coerce').fillna(float('-inf'))
    out = out.sort_values(['Setup Date', '_status_priority', '_current_sort', 'Ticker'], ascending=[False, True, False, True])
    return out[DETAIL_COLUMNS]


def comparison_rows(window_summaries: pd.DataFrame) -> pd.DataFrame:
    if window_summaries.empty:
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    out = pd.DataFrame({
        'Window': window_summaries['Window'],
        'Dates': window_summaries['Dates'],
        'Setup Dates': window_summaries['Setup Dates'],
        'Setups': window_summaries['Setups'],
        'Day Success %': window_summaries['Day Success'].apply(_pct_from_count_text),
        'Active %': window_summaries['Active'].apply(_pct_from_count_text),
        'Failed After D0 %': window_summaries['Failed After D0'].apply(_pct_from_count_text),
        'Median Current': window_summaries['Median Current'],
        'Median Max': window_summaries['Median Max'],
    })
    return out[COMPARISON_COLUMNS].copy()


def _insight_pct(value: float) -> str:
    return f'{round(value * 100):.0f}%'


def _insight_return(value: float) -> str:
    pct = value * 100
    sign = '+' if pct > 0 else ''
    return f'{sign}{pct:.1f}%'


def _window_rows_for_insights(rows: pd.DataFrame, dates: tuple[pd.Timestamp, ...]) -> pd.DataFrame:
    if rows.empty or 'Setup Date' not in rows:
        return pd.DataFrame()
    included = {date.date() for date in dates}
    setup_dates = pd.to_datetime(rows['Setup Date'], errors='coerce')
    return rows[setup_dates.dt.date.isin(included)].copy()


def _insight_rate(rows: pd.DataFrame, kind: str) -> float | None:
    if rows.empty:
        return None
    total = len(rows)
    if total == 0:
        return None
    if kind == 'Day Success':
        return float(rows.get('Trigger Day', pd.Series('', index=rows.index)).eq('Success').sum() / total)
    if kind == 'Day Fail':
        return float(rows.get('Trigger Day', pd.Series('', index=rows.index)).eq('Fail').sum() / total)
    if kind == 'Unresolved':
        return float(rows.get('Trigger Day', pd.Series('', index=rows.index)).eq('Unresolved').sum() / total)
    if kind == 'Active':
        return float(rows.get('Current Status', pd.Series('', index=rows.index)).eq('Active').sum() / total)
    if kind in {'Failed After D0', 'Later Failed'}:
        return float(_is_later_failed(rows.get('Current Status', pd.Series('', index=rows.index))).sum() / total)
    if kind in {'PDH', '1m ORH', '5m ORH', 'Alt Required', 'Failed OR Trigger', 'No Trigger'}:
        return float(rows.get('Trigger', pd.Series('', index=rows.index)).eq(kind).sum() / total)
    if kind == 'Retested':
        retests = rows['Retests'] if 'Retests' in rows else rows['Retest Day'] if 'Retest Day' in rows else pd.Series('', index=rows.index)
        return float(retests.fillna('').astype(str).ne('').sum() / total)
    if kind == 'Wide 1m OR':
        return float(rows.get('Notes', pd.Series('', index=rows.index)).fillna('').astype(str).str.contains('Wide 1m OR', regex=False).sum() / total)
    if kind == 'Wide 5m OR':
        return float(rows.get('Notes', pd.Series('', index=rows.index)).fillna('').astype(str).str.contains('Wide 5m OR', regex=False).sum() / total)
    return None


def _insight_median(rows: pd.DataFrame, column: str) -> float | None:
    if rows.empty:
        return None
    if column == 'eligible_d3_high_pct_raw':
        values = eligible_d3_high_pct(rows).dropna()
    elif column in rows:
        values = pd.to_numeric(rows[column], errors='coerce').dropna()
    else:
        return None
    if len(values) < 5:
        return None
    return float(values.median())


def generate_behavior_insights(summary_data, derived_rows: pd.DataFrame) -> list[dict]:
    if derived_rows is None or derived_rows.empty or 'Setup Date' not in derived_rows:
        return []

    windows = {window.label: window for window in overview_windows(derived_rows['Setup Date'].dropna().unique())}
    comparisons = [
        ('Last 5 Setup Dates', 'Previous 5 Setup Dates', 'Compared last 5 setup dates vs prior 5 setup dates'),
        ('Last 5 Setup Dates', 'Last 20 Setup Dates', 'Compared last 5 setup dates vs last 20 setup dates'),
        ('Last 10 Setup Dates', 'Last 20 Setup Dates', 'Compared last 10 setup dates vs last 20 setup dates'),
    ]
    row_cache = {
        label: _window_rows_for_insights(derived_rows, window.setup_dates)
        for label, window in windows.items()
    }

    candidates: list[dict] = []

    def add_candidate(priority: int, score: float, text: str, basis: str) -> None:
        candidates.append({'priority': priority, 'score': score, 'text': text, 'basis': basis})

    rate_metrics = [
        (1, 'Day Success'),
        (1, 'Day Fail'),
        (1, 'Unresolved'),
        (2, 'Active'),
        (2, 'Failed After D0'),
        (4, 'PDH'),
        (4, '1m ORH'),
        (4, '5m ORH'),
        (4, 'Alt Required'),
        (4, 'Failed OR Trigger'),
        (4, 'No Trigger'),
        (5, 'Retested'),
        (5, 'Wide 1m OR'),
        (5, 'Wide 5m OR'),
    ]
    median_metrics = [
        (3, 'Median Current %', 'current_pct_raw'),
        (3, 'Median Max %', 'max_pct_raw'),
        (3, 'Median D3 High %', 'eligible_d3_high_pct_raw'),
    ]
    trigger_bucket_metrics = {'PDH', '1m ORH', '5m ORH', 'Alt Required', 'Failed OR Trigger', 'No Trigger'}

    for recent_label, baseline_label, basis in comparisons:
        recent = row_cache.get(recent_label, pd.DataFrame())
        baseline = row_cache.get(baseline_label, pd.DataFrame())
        if len(recent) < 5 or len(baseline) < 5:
            continue

        for priority, metric in rate_metrics:
            if metric in trigger_bucket_metrics:
                trigger_count = int(recent.get('Trigger', pd.Series('', index=recent.index)).eq(metric).sum())
                if trigger_count < 3:
                    continue
            recent_value = _insight_rate(recent, metric)
            baseline_value = _insight_rate(baseline, metric)
            if recent_value is None or baseline_value is None:
                continue
            delta = recent_value - baseline_value
            if abs(delta) < 0.15:
                continue
            if metric == 'Failed After D0' and delta > 0:
                text = (
                    f'Failed After D0 increased from {_insight_pct(baseline_value)} to {_insight_pct(recent_value)}, '
                    'meaning more setups are working on trigger day but failing later.'
                )
            elif metric.startswith('Wide') and delta > 0:
                text = (
                    f'{metric} frequency increased from {_insight_pct(baseline_value)} to {_insight_pct(recent_value)}, '
                    'meaning more setups required wider opening-range triggers.'
                )
            elif metric in trigger_bucket_metrics:
                direction = 'increased' if delta > 0 else 'decreased'
                text = f'{metric} usage {direction} from {_insight_pct(baseline_value)} to {_insight_pct(recent_value)} of setups.'
            else:
                direction = 'improved' if metric == 'Day Success' and delta > 0 else 'increased' if delta > 0 else 'decreased'
                text = f'{metric} {direction} from {_insight_pct(baseline_value)} to {_insight_pct(recent_value)}.'
            add_candidate(priority, abs(delta), text, basis)

        for priority, metric, column in median_metrics:
            recent_value = _insight_median(recent, column)
            baseline_value = _insight_median(baseline, column)
            if recent_value is None or baseline_value is None:
                continue
            delta = recent_value - baseline_value
            if abs(delta) < 0.02:
                continue
            direction = 'improved' if delta > 0 else 'decreased'
            add_candidate(
                priority,
                abs(delta),
                f'{metric} {direction} from {_insight_return(baseline_value)} to {_insight_return(recent_value)}.',
                basis,
            )

    candidates = sorted(candidates, key=lambda item: (item['priority'], -item['score'], item['text']))
    seen: set[str] = set()
    insights: list[dict] = []
    for item in candidates:
        if item['text'] in seen:
            continue
        seen.add(item['text'])
        insights.append({'text': item['text'], 'basis': item['basis']})
        if len(insights) == 5:
            break
    return insights


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
                ('Failed After D0', window_summary.get('Failed After D0', '-')),
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
                ('VWAP Reclaim', window_summary.get('VWAP Reclaim', '-')),
                ('PDH', window_summary.get('PDH', '-')),
                ('Failed PDH Trigger', window_summary.get('Failed PDH Trigger', '-')),
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


OPENING_BEHAVIOR_COLUMNS = [
    'Path',
    'Count',
    '% of Setups',
    'Active %',
    'Failed After D0 %',
    'Median Current',
    'Median Max',
]
OPENING_BEHAVIOR_MAIN_COLUMNS = [
    'Trigger',
    'Count',
    '% of Setups',
    'Currently Active',
    'Failed After D0',
    'Median Max',
]
MAIN_OPENING_TRIGGERS = ['1m ORH', '5m ORH', 'VWAP Reclaim', 'PDH', 'Alt Required']


def _count_int(value: Any) -> int:
    if isinstance(value, str):
        try:
            return int(value.split(' ', 1)[0])
        except (IndexError, ValueError):
            return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_later_failed(series: pd.Series) -> pd.Series:
    normalized = series.fillna('').astype(str).str.strip()
    return normalized.eq('Later Failed') | normalized.eq('Failed') | normalized.str.match(r'^Failed D\d+$')


def _is_blank_or_dash(series: pd.Series) -> pd.Series:
    normalized = series.fillna('').astype(str).str.strip()
    return normalized.isin({'', '-', '—', 'â€”'})


def _normalized_result(series: pd.Series) -> pd.Series:
    return series.fillna('').astype(str).str.strip()


def _qualified_vwap_values(rows: pd.DataFrame) -> pd.Series:
    if rows.empty:
        return pd.Series('', index=rows.index)
    values_by_priority = []
    for column in ['Qualified VWAP Trigger Result', 'vwap_qualified_trigger_result', 'VWAP Reclaim', 'VWAP Trigger']:
        if column in rows:
            values = _normalized_result(rows[column])
            if values.ne('').any():
                values_by_priority.append(values)
    if not values_by_priority:
        return pd.Series('', index=rows.index)
    out = values_by_priority[0].copy()
    for values in values_by_priority[1:]:
        out = out.mask(_is_blank_or_dash(out), values)
    return out


def _visible_orh_results(rows: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    one = rows['1m ORH'].apply(_display) if '1m ORH' in rows else pd.Series('', index=rows.index)
    five = rows['5m ORH'].apply(_display) if '5m ORH' in rows else pd.Series('', index=rows.index)
    adjusted = [
        vwap_superseded_orh_display_values(row, one_value, five_value)
        for (_, row), one_value, five_value in zip(rows.iterrows(), one, five)
    ]
    return (
        pd.Series([one_value for one_value, _ in adjusted], index=rows.index),
        pd.Series([five_value for _, five_value in adjusted], index=rows.index),
    )


def _ineligible_trigger_mask(series: pd.Series) -> pd.Series:
    normalized = _normalized_result(series).str.casefold()
    return normalized.isin({'gap', 'n/a', 'na', 'not applicable', 'not-applicable'})


def _eligible_trigger_mask(series: pd.Series) -> pd.Series:
    # Blank/dash currently means the trigger level was applicable but did not
    # trigger. Explicit not-applicable states, such as PDH Gap, are excluded.
    return ~_ineligible_trigger_mask(series)


def _pct_of_rows(count: int, denominator: int) -> str:
    if denominator <= 0:
        return '-'
    return f'{round((count / denominator) * 100)}%'


def _fmt_rate(count: int, denominator: int) -> str:
    if denominator <= 0:
        return '-'
    return f'{round((count / denominator) * 100)}%'


def _opening_path_row(path: str, rows: pd.DataFrame, total_setups: int) -> dict:
    count = len(rows)
    return {
        'Path': path,
        'Count': count,
        '% of Setups': _pct_of_rows(count, total_setups),
        'Active %': _pct_of_rows(int(rows['Current Status'].eq('Active').sum()) if 'Current Status' in rows else 0, count),
        'Failed After D0 %': _pct_of_rows(int(_is_later_failed(rows['Current Status']).sum()) if 'Current Status' in rows else 0, count),
        'Median Current': _fmt_pct(rows['current_pct_raw'].median() if 'current_pct_raw' in rows and count else None),
        'Median Max': _fmt_pct(rows['max_pct_raw'].median() if 'max_pct_raw' in rows and count else None),
    }


def opening_behavior_table(rows: pd.DataFrame) -> pd.DataFrame:
    """Summarize displayed opening behavior paths.

    The Rolling Setup Monitor exposes applicable/displayed PDH, 1m ORH, and 5m ORH
    results. It does not expose every hidden intraday sequence flag here, so these
    paths use the deterministic displayed results rather than reclassifying raw bars.
    """
    columns = OPENING_BEHAVIOR_COLUMNS
    if rows.empty:
        return pd.DataFrame(columns=columns)

    total = len(rows)
    one, five = _visible_orh_results(rows)
    pdh = rows['PDH'] if 'PDH' in rows else pd.Series('', index=rows.index)
    vwap = _qualified_vwap_values(rows)
    trigger = rows['Trigger'] if 'Trigger' in rows else pd.Series('', index=rows.index)

    one_success = one.eq('success')
    one_failed = one.eq('failed')
    five_success = five.eq('success')
    five_failed_or_blank = five.eq('failed') | _is_blank_or_dash(five)
    pdh_success = pdh.eq('success')
    pdh_failed_or_blank = pdh.eq('failed') | _is_blank_or_dash(pdh)
    successful_trigger = trigger.isin({'PDH', '1m ORH', '5m ORH', 'Alt Required'}) | vwap.eq('success')
    trigger_day = rows['Trigger Day'] if 'Trigger Day' in rows else pd.Series('', index=rows.index)
    alt_success = trigger.eq('Alt Required') & trigger_day.eq('Success')

    masks = [
        ('Clean 1m ORH Success', one_success),
        ('1m ORH Failed, Later Reclaimed', one_failed & (five_success | pdh_success)),
        ('1m ORH Failed, Never Recovered', one_failed & ~five_success & ~pdh_success),
        ('5m ORH Success After 1m Failure', one_failed & five_success),
        ('PDH Success After Early Noise', pdh_success & (one.eq('failed') | five.eq('failed'))),
        ('Alt Required Success', alt_success),
        ('Failed All Opening Triggers', one_failed & five_failed_or_blank & pdh_failed_or_blank & ~successful_trigger),
    ]
    return pd.DataFrame([_opening_path_row(label, rows[mask], total) for label, mask in masks], columns=columns)


def _main_opening_row(trigger_name: str, rows: pd.DataFrame, total_setups: int) -> dict:
    count = len(rows)
    active_count = int(rows['Current Status'].eq('Active').sum()) if 'Current Status' in rows else 0
    later_failed_count = int(_is_later_failed(rows['Current Status']).sum()) if 'Current Status' in rows else 0
    return {
        'Trigger': trigger_name,
        'Count': count,
        '% of Setups': _pct_of_rows(count, total_setups),
        'Currently Active': _count_with_pct(active_count, _pct_of_rows(active_count, count)) if count else '-',
        'Failed After D0': _count_with_pct(later_failed_count, _pct_of_rows(later_failed_count, count)) if count else '-',
        'Median Max': _fmt_pct(rows['max_pct_raw'].median() if 'max_pct_raw' in rows and count else None),
    }


def main_opening_behavior_table(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame([
            _main_opening_row(trigger_name, rows.copy(), 0)
            for trigger_name in MAIN_OPENING_TRIGGERS
        ], columns=OPENING_BEHAVIOR_MAIN_COLUMNS)
    total = len(rows)
    trigger_day = rows['Trigger Day'] if 'Trigger Day' in rows else pd.Series('', index=rows.index)
    one, five = _visible_orh_results(rows)
    masks = {
        '1m ORH': one.eq('success'),
        '5m ORH': five.eq('success'),
        'VWAP Reclaim': _qualified_vwap_values(rows).eq('success'),
        'PDH': rows['PDH'].eq('success') if 'PDH' in rows else pd.Series(False, index=rows.index),
        'Alt Required': (rows['Trigger'].eq('Alt Required') & trigger_day.eq('Success')) if 'Trigger' in rows else pd.Series(False, index=rows.index),
    }
    return pd.DataFrame([
        _main_opening_row(trigger_name, rows[masks[trigger_name]], total)
        for trigger_name in MAIN_OPENING_TRIGGERS
    ], columns=OPENING_BEHAVIOR_MAIN_COLUMNS)


def _opening_path_mask(rows: pd.DataFrame, path: str) -> pd.Series:
    one, five = _visible_orh_results(rows)
    pdh = rows['PDH'] if 'PDH' in rows else pd.Series('', index=rows.index)
    vwap = _qualified_vwap_values(rows)
    trigger = rows['Trigger'] if 'Trigger' in rows else pd.Series('', index=rows.index)
    one_success = one.eq('success')
    one_failed = one.eq('failed')
    five_success = five.eq('success')
    five_failed_or_blank = five.eq('failed') | _is_blank_or_dash(five)
    pdh_success = pdh.eq('success')
    pdh_failed_or_blank = pdh.eq('failed') | _is_blank_or_dash(pdh)
    successful_trigger = trigger.isin({'PDH', '1m ORH', '5m ORH', 'Alt Required'}) | vwap.eq('success')
    trigger_day = rows['Trigger Day'] if 'Trigger Day' in rows else pd.Series('', index=rows.index)
    masks = {
        'Clean 1m ORH Success': one_success,
        '1m ORH Failed, Later Reclaimed': one_failed & (five_success | pdh_success),
        '1m ORH Failed, Never Recovered': one_failed & ~five_success & ~pdh_success,
        '5m ORH Success After 1m Failure': one_failed & five_success,
        'PDH Success After Early Noise': pdh_success & (one.eq('failed') | five.eq('failed')),
        'Alt Required Success': trigger.eq('Alt Required') & trigger_day.eq('Success'),
        'Failed All Opening Triggers': one_failed & five_failed_or_blank & pdh_failed_or_blank & ~successful_trigger,
    }
    return masks.get(path, pd.Series(True, index=rows.index))


def _opening_count(opening_behavior: pd.DataFrame | None, path: str) -> int:
    if opening_behavior is None or opening_behavior.empty:
        return 0
    match = opening_behavior[opening_behavior['Path'] == path]
    if match.empty:
        return 0
    return _count_int(match.iloc[0]['Count'])


def factual_read(window_summary: dict, opening_behavior: pd.DataFrame | None = None) -> str:
    window = window_summary.get('Window', 'Selected window')
    setups = window_summary.get('Setups', 0)
    setup_dates_count = window_summary.get('Setup Dates', 0)
    day_success_pct = _pct_from_count_text(window_summary.get('Day Success', '-'))
    active_pct = _pct_from_count_text(window_summary.get('Active', '-'))
    later_failed_pct = _pct_from_count_text(window_summary.get('Failed After D0', '-'))
    median_current = window_summary.get('Median Current', '-')
    median_max = window_summary.get('Median Max', '-')
    return (
        f'{window}: {setups} setups across {setup_dates_count} setup dates, '
        f'{day_success_pct} Day Success, {active_pct} Active, {later_failed_pct} Failed After D0, '
        f'{median_current} Median Current, {median_max} Median Max.'
    )


def selected_window_snapshot(window_summary: dict) -> str:
    setups = window_summary.get('Setups', 0)
    setup_dates_count = window_summary.get('Setup Dates', 0)
    day_success_pct = _pct_from_count_text(window_summary.get('Day Success', '-'))
    active_pct = _pct_from_count_text(window_summary.get('Active', '-'))
    later_failed_pct = _pct_from_count_text(window_summary.get('Failed After D0', '-'))
    median_current = window_summary.get('Median Current', '-')
    median_max = window_summary.get('Median Max', '-')
    return (
        f'{setups} setups across {setup_dates_count} setup dates | '
        f'{day_success_pct} Day Success | {active_pct} Active | {later_failed_pct} Failed After D0 | '
        f'Median Current {median_current} | Median Max {median_max}'
    )


def _successful_trigger_mix(rows: pd.DataFrame) -> list[tuple[str, str]]:
    if rows.empty or 'Trigger' not in rows:
        return []
    trigger_day = rows['Trigger Day'] if 'Trigger Day' in rows else pd.Series('', index=rows.index)
    successful = rows[rows['Trigger'].isin(MAIN_OPENING_TRIGGERS) & trigger_day.eq('Success')]
    total = len(successful)
    if total <= 0:
        return []
    labels = {
        '1m ORH': '1m',
        '5m ORH': '5m',
        'VWAP Reclaim': 'VWAP',
        'PDH': 'PDH',
        'Alt Required': 'Alt',
    }
    out = []
    for trigger_name in MAIN_OPENING_TRIGGERS:
        count = int(successful['Trigger'].eq(trigger_name).sum())
        if count:
            out.append((labels[trigger_name], f'{count} ({_fmt_rate(count, total)})'))
    out.sort(key=lambda item: _count_int(item[1]), reverse=True)
    return out


def _failure_rate_rows(window_trigger_outcomes: pd.DataFrame | None) -> list[tuple[str, str]]:
    labels = {
        '1m ORH': '1m',
        '5m ORH': '5m',
        'VWAP Reclaim': 'VWAP',
        'PDH': 'PDH',
        'Alt Required': 'Alt',
    }
    if window_trigger_outcomes is None or window_trigger_outcomes.empty:
        return [(labels[name], '-') for name in MAIN_OPENING_TRIGGERS]
    indexed = window_trigger_outcomes.set_index('Trigger')
    out = []
    for trigger_name in MAIN_OPENING_TRIGGERS:
        if trigger_name not in indexed.index:
            out.append((labels[trigger_name], '-'))
            continue
        row = indexed.loc[trigger_name]
        triggered = _count_int(row.get('Triggered'))
        failed = _count_int(row.get('Failed'))
        out.append((labels[trigger_name], '-' if triggered <= 0 else f'{failed} / {triggered} ({_fmt_rate(failed, triggered)})'))
    return out


def _current_status_snapshot(rows: pd.DataFrame | None, window_summary: dict, total: int) -> list[tuple[str, str]]:
    if rows is not None and not rows.empty and 'Current Status' in rows:
        status = rows['Current Status'].fillna('').astype(str).str.strip()
        active_count = int(status.eq('Active').sum())
        failed_d0_count = int(status.eq('Failed D0').sum())
        failed_after_count = int((status.eq('Failed') | status.eq('Later Failed') | status.str.match(r'^Failed D[1-9]\d*$')).sum())
        unresolved_count = max(total - active_count - failed_d0_count - failed_after_count, 0)
    else:
        active_count = _count_int(window_summary.get('Active', 0))
        failed_d0_count = 0
        failed_after_count = _count_int(window_summary.get('Failed After D0', 0))
        unresolved_count = _count_int(window_summary.get('Unresolved', 0))
    return [
        ('Active', f'{_fmt_rate(active_count, total)} ({active_count} / {total})'),
        ('D0 Fail', f'{_fmt_rate(failed_d0_count, total)} ({failed_d0_count} / {total})'),
        ('Failed After D0', f'{_fmt_rate(failed_after_count, total)} ({failed_after_count} / {total})'),
        ('Unresolved', f'{_fmt_rate(unresolved_count, total)} ({unresolved_count} / {total})'),
    ]


def _follow_through_flags(rows: pd.DataFrame | None, total: int) -> list[tuple[str, str]]:
    if rows is None or rows.empty:
        return [('Close < BE', '-'), ('Retested D0 Only', '-'), ('Retested After D0', '-')]
    close_values = rows['Close < BE'] if 'Close < BE' in rows else pd.Series('', index=rows.index)
    if 'Retest Days Raw' in rows:
        retest_values = rows['Retest Days Raw']
    elif 'Retests' in rows:
        retest_values = rows['Retests']
    elif 'Retest Day' in rows:
        retest_values = rows['Retest Day']
    else:
        retest_values = pd.Series('', index=rows.index)
    close_count = int(close_values.fillna('').astype(str).str.strip().str.casefold().eq('yes').sum())
    retest_days = retest_values.apply(_retest_day_numbers)
    d0_only_count = int(retest_days.apply(lambda days: 0 in days and not any(day > 0 for day in days)).sum())
    after_d0_count = int(retest_days.apply(lambda days: any(day > 0 for day in days)).sum())
    return [
        ('Close < BE', f'{_fmt_rate(close_count, total)} ({close_count} / {total})'),
        ('Retested D0 Only', f'{_fmt_rate(d0_only_count, total)} ({d0_only_count} / {total})'),
        ('Retested After D0', f'{_fmt_rate(after_d0_count, total)} ({after_d0_count} / {total})'),
    ]


def _retest_day_numbers(value: Any) -> set[int]:
    if value is None:
        return set()
    try:
        if pd.isna(value):
            return set()
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text == '-' or text.lower() == 'nan':
        return set()
    return {int(match) for match in re.findall(r'D(\d+)', text)}


def _snapshot_lines(items: list[tuple[str, str]]) -> str:
    if not items:
        return '<div class="snapshot-line"><span>-</span><strong>-</strong></div>'
    return ''.join(
        f'<div class="snapshot-line"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'
        for label, value in items
    )


def snapshot_cards_html(
    window_summary: dict,
    rows: pd.DataFrame | None = None,
    trigger_outcomes: pd.DataFrame | None = None,
) -> str:
    total = int(window_summary.get('Setups', 0) or 0)
    if rows is not None and not rows.empty:
        total = len(rows)
        success_mix = _successful_trigger_mix(rows)
    else:
        success_mix = []

    current_status_lines = _current_status_snapshot(rows, window_summary, total)
    follow_through_lines = _follow_through_flags(rows, total)
    failure_rates = _failure_rate_rows(trigger_outcomes)
    return f'''
<style>
.snapshot-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 0.85rem;
  margin: 0.35rem 0 1rem 0;
}}
.snapshot-card {{
  border: 1px solid rgba(250, 250, 250, 0.13);
  border-radius: 8px;
  padding: 0.95rem 1rem;
  background: rgba(250, 250, 250, 0.04);
}}
.snapshot-label {{
  color: rgba(250, 250, 250, 0.66);
  font-size: 0.82rem;
  margin-bottom: 0.32rem;
}}
.snapshot-value {{
  color: rgba(250, 250, 250, 0.97);
  font-size: 1.42rem;
  line-height: 1.15;
  font-weight: 760;
}}
.snapshot-sub {{
  color: rgba(250, 250, 250, 0.68);
  font-size: 0.86rem;
  margin-top: 0.28rem;
}}
.snapshot-line {{
  display: flex;
  justify-content: space-between;
  gap: 0.85rem;
  color: rgba(250, 250, 250, 0.72);
  font-size: 0.88rem;
  padding: 0.08rem 0;
}}
.snapshot-line strong {{
  color: rgba(250, 250, 250, 0.96);
  font-weight: 750;
  white-space: nowrap;
}}
</style>
<div class="snapshot-grid">
  <section class="snapshot-card"><div class="snapshot-label">Current Status</div>{_snapshot_lines(current_status_lines)}</section>
  <section class="snapshot-card"><div class="snapshot-label">Follow-Through Flags</div>{_snapshot_lines(follow_through_lines)}</section>
  <section class="snapshot-card"><div class="snapshot-label">Successful Trigger Mix</div>{_snapshot_lines(success_mix)}</section>
  <section class="snapshot-card"><div class="snapshot-label">Failure Rate by Trigger</div>{_snapshot_lines(failure_rates)}</section>
</div>
'''


def _summary_count(summary: dict, key: str) -> int:
    value = summary.get(key, 0)
    if isinstance(value, str):
        try:
            return int(value.split(' ', 1)[0])
        except (ValueError, IndexError):
            return 0
    return int(value or 0)


def mix_tables(window_summary: dict) -> dict[str, pd.DataFrame]:
    unresolved = _summary_count(window_summary, 'Unresolved')
    day_fail = _summary_count(window_summary, 'Day Fail')
    return {
        'Outcome Mix': pd.DataFrame([
            {'Metric': 'Day Success', 'Value': window_summary.get('Day Success', '-')},
            {'Metric': 'Day Fail', 'Value': window_summary.get('Day Fail', '-')},
            {'Metric': 'Unresolved', 'Value': window_summary.get('Unresolved', '-')},
        ]),
        'Current Mix': pd.DataFrame([
            {'Metric': 'Active', 'Value': window_summary.get('Active', '-')},
            {'Metric': 'Failed After D0', 'Value': window_summary.get('Failed After D0', '-')},
            {'Metric': 'Unresolved / Not Active', 'Value': _fmt_count(unresolved + day_fail, int(window_summary.get('Setups', 0) or 0))},
        ]),
        'Trigger Mix': pd.DataFrame([
            {'Metric': 'PDH', 'Value': window_summary.get('PDH', '-')},
            {'Metric': '1m ORH', 'Value': window_summary.get('Clean 1m', '-')},
            {'Metric': '5m ORH', 'Value': window_summary.get('Clean 5m', '-')},
            {'Metric': 'VWAP Reclaim', 'Value': window_summary.get('VWAP Reclaim', '-')},
            {'Metric': 'Alt Required', 'Value': window_summary.get('Alt Required', '-')},
            {'Metric': 'Failed PDH Trigger', 'Value': window_summary.get('Failed PDH Trigger', '-')},
            {'Metric': 'Failed OR Trigger', 'Value': window_summary.get('Failed OR Trigger', '-')},
            {'Metric': 'No Trigger', 'Value': window_summary.get('No Trigger', '-')},
        ]),
    }


TRIGGER_ORDER = ['1m ORH', '5m ORH', 'VWAP Reclaim', 'PDH', 'Alt Required', 'Failed PDH Trigger', 'Failed OR Trigger', 'No Trigger']
TRIGGER_COMPARISON_ORDER = ['1m ORH', '5m ORH', 'VWAP Reclaim', 'PDH', 'Alt Required']
TRIGGER_COMPARISON_COLUMNS = [
    'Trigger',
    'Window',
    'Setups',
    'Eligible',
    'Ineligible',
    'Triggered',
    'Trigger Rate',
    'Failed',
    'Fail %',
    'Success',
    'Success %',
    'Failed After D0 Count',
    'Failed After D0 %',
    'Active Count',
    'Active %',
    'Median Current',
    'Median Max',
]
TRIGGER_COMPARISON_BY_WINDOW_COLUMNS = [column for column in TRIGGER_COMPARISON_COLUMNS if column != 'Window']
TRIGGER_EVENT_MAIN_COLUMNS = [
    'Trigger',
    'Eligible',
    'Triggered',
    'Failed',
    'Success',
    'Currently Active',
    'Failed After D0',
    'Median Max',
]
TRIGGER_FAILURE_TREND_BASE_COLUMNS = ['Trigger', 'Last 2', 'Last 5', 'Previous 5', 'Last 10', 'Last 20', 'Read']
TRIGGER_FAILURE_TREND_COLUMNS = ['Window', 'PDH', '1m ORH', 'VWAP Reclaim', '5m ORH']
TRIGGER_SHIFT_READ_COLUMNS = ['Trigger', 'Read']
TRIGGER_FAILURE_TREND_WINDOW_LABELS = {
    'Last 2 Setup Dates': 'Last 2',
    'Last 5 Setup Dates': 'Last 5',
    'Previous 5 Setup Dates': 'Previous 5',
    'Last 10 Setup Dates': 'Last 10',
    'Last 20 Setup Dates': 'Last 20',
}
TRIGGER_EVENT_WINDOW_ORDER = [
    'Last 2 Setup Dates',
    'Last 5 Setup Dates',
    'Previous 5 Setup Dates',
    'Last 10 Setup Dates',
    'Last 20 Setup Dates',
]
TRIGGER_EVENT_SHIFT_METRICS = [
    ('Failed', 'Fail %', True, 15.0),
    ('Success', 'Success %', False, 15.0),
    ('Currently Active', 'Active %', False, 15.0),
    ('Median Max', 'Median Max', False, 3.0),
]
TRIGGER_EVENT_HIGHLIGHT_STYLES = {
    'positive': 'background-color: rgba(36, 164, 89, 0.16); color: #d8f5df; font-weight: 650;',
    'negative': 'background-color: rgba(210, 74, 74, 0.16); color: #ffe0e0; font-weight: 650;',
}
FAILURE_TIMING_BUCKETS = ['Active', 'D0 Fail', 'D1 Fail', 'D2 Fail', 'D3 Fail', 'Failed After D3', 'Unresolved']
FAILURE_TIMING_WINDOW_COLUMNS = ['Window', 'Triggered', *FAILURE_TIMING_BUCKETS]
FAILURE_TIMING_TRIGGER_COLUMNS = ['Trigger', 'Triggered', *FAILURE_TIMING_BUCKETS]


def _short_window_label(label: str) -> str:
    return str(label).replace(' Setup Dates', '').replace(' setup dates', '')


def _failure_timing_bucket_cell(row: dict, bucket: str) -> str:
    triggered = int(row.get('Triggered', 0) or 0)
    if triggered <= 0:
        return '—'
    count = int(row.get(bucket, 0) or 0)
    pct = round((count / triggered) * 100)
    return f'{pct}% ({count}/{triggered})'


def _format_failure_timing_row(row: dict, label_column: str, label: str) -> dict:
    return {
        label_column: label,
        'Triggered': int(row.get('Triggered', 0) or 0),
        **{bucket: _failure_timing_bucket_cell(row, bucket) for bucket in FAILURE_TIMING_BUCKETS},
    }


def failure_timing_by_window_table(history_by_window: dict[str, pd.DataFrame]) -> pd.DataFrame:
    records = []
    for window_label, rows in history_by_window.items():
        timing = failure_timing_distribution(rows)
        row = timing.iloc[0].to_dict() if not timing.empty else {'Triggered': 0}
        records.append(_format_failure_timing_row(row, 'Window', _short_window_label(window_label)))
    return pd.DataFrame(records, columns=FAILURE_TIMING_WINDOW_COLUMNS)


def failure_timing_by_trigger_table(rows: pd.DataFrame) -> pd.DataFrame:
    timing = failure_timing_distribution(rows, group_by='Trigger')
    if timing.empty:
        return pd.DataFrame(columns=FAILURE_TIMING_TRIGGER_COLUMNS)
    records = [
        _format_failure_timing_row(row.to_dict(), 'Trigger', str(row.get('Trigger', '')))
        for _, row in timing.iterrows()
    ]
    return pd.DataFrame(records, columns=FAILURE_TIMING_TRIGGER_COLUMNS)


def _trigger_event_values(rows: pd.DataFrame, trigger_name: str) -> pd.Series:
    if rows.empty:
        return pd.Series('', index=rows.index)
    if trigger_name == 'VWAP Reclaim':
        return _qualified_vwap_values(rows)
    if trigger_name == '1m ORH':
        return _normalized_result(_visible_orh_results(rows)[0])
    if trigger_name == '5m ORH':
        return _normalized_result(_visible_orh_results(rows)[1])
    if trigger_name in {'VWAP Reclaim', 'PDH'}:
        if trigger_name not in rows:
            return pd.Series('', index=rows.index)
        return _normalized_result(rows[trigger_name])
    if trigger_name != 'Alt Required':
        return pd.Series('', index=rows.index)

    # Alt Required is stored as a final/primary trigger label, not a raw event
    # diagnostic column. For event aggregation, treat it as applicable only when
    # no displayed 1m/5m/VWAP/PDH trigger event succeeded, or when Alt
    # Required itself was the final trigger. Eligible non-trigger rows stay
    # blank so Alt Required remains the fallback event.
    trigger = rows['Trigger'] if 'Trigger' in rows else pd.Series('', index=rows.index)
    trigger_day = rows['Trigger Day'] if 'Trigger Day' in rows else pd.Series('', index=rows.index)
    one, five = _visible_orh_results(rows)
    vwap = _qualified_vwap_values(rows)
    pdh = rows['PDH'] if 'PDH' in rows else pd.Series('', index=rows.index)
    lower_success = one.eq('success') | five.eq('success') | vwap.eq('success') | pdh.eq('success')
    alt_selected = trigger.eq('Alt Required')

    values = pd.Series('Not Applicable', index=rows.index, dtype=object)
    values.loc[~lower_success | alt_selected] = ''
    values.loc[alt_selected & trigger_day.eq('Success')] = 'success'
    values.loc[alt_selected & trigger_day.eq('Fail')] = 'failed'
    return values


def trigger_outcome_comparison(history_by_window: dict[str, pd.DataFrame]) -> pd.DataFrame:
    out = []
    for trigger_name in TRIGGER_COMPARISON_ORDER:
        for window_label, rows in history_by_window.items():
            setups = len(rows)
            values = _trigger_event_values(rows, trigger_name)
            success_mask = values.eq('success')
            failed_mask = values.eq('failed')
            eligible_mask = _eligible_trigger_mask(values)
            triggered_mask = success_mask | failed_mask
            triggered = rows[triggered_mask].copy()
            successful = rows[success_mask].copy()
            eligible_count = int(eligible_mask.sum())
            ineligible_count = setups - eligible_count
            triggered_count = len(triggered)
            success_count = len(successful)
            later_failed_count = int(_is_later_failed(successful['Current Status']).sum()) if success_count and 'Current Status' in successful else 0
            active_count = int(successful['Current Status'].eq('Active').sum()) if success_count and 'Current Status' in successful else 0
            out.append({
                'Trigger': trigger_name,
                'Window': window_label,
                'Setups': setups,
                'Eligible': eligible_count,
                'Ineligible': ineligible_count,
                'Triggered': triggered_count,
                'Trigger Rate': _fmt_rate(triggered_count, eligible_count),
                'Success': success_count,
                'Success %': _fmt_rate(success_count, triggered_count),
                'Failed': int(failed_mask.sum()),
                'Fail %': _fmt_rate(int(failed_mask.sum()), triggered_count),
                'Failed After D0 Count': later_failed_count,
                'Failed After D0 %': _fmt_rate(later_failed_count, success_count),
                'Active Count': active_count,
                'Active %': _fmt_rate(active_count, success_count),
                'Median Current': _fmt_pct(triggered['current_pct_raw'].median() if 'current_pct_raw' in triggered and triggered_count else None),
                'Median Max': _fmt_pct(successful['max_pct_raw'].median() if 'max_pct_raw' in successful and success_count else None),
            })
    return pd.DataFrame(out, columns=TRIGGER_COMPARISON_COLUMNS)


def filter_detail_rows(
    rows: pd.DataFrame,
    trigger_level: str = 'All',
    trigger_result: str = 'All',
    current_status: str = 'All',
    opening_path_group: str = 'All',
) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    out = rows.copy()
    trigger_columns = ['1m ORH', '5m ORH', 'VWAP Reclaim', 'PDH', 'Alt Required']

    if trigger_level != 'All':
        values = _trigger_event_values(out, trigger_level)
        if trigger_result == 'All':
            out = out[_eligible_trigger_mask(values)]
        elif trigger_result == 'blank':
            out = out[_is_blank_or_dash(values)]
        else:
            out = out[values.eq(trigger_result)]
    elif trigger_result != 'All':
        if trigger_result == 'blank':
            mask = pd.Series(True, index=out.index)
            for column in trigger_columns:
                mask &= _is_blank_or_dash(_trigger_event_values(out, column))
            out = out[mask]
        else:
            mask = pd.Series(False, index=out.index)
            for column in trigger_columns:
                mask |= _trigger_event_values(out, column).eq(trigger_result)
            out = out[mask]

    if current_status == 'Active' and 'Current Status' in out:
        out = out[out['Current Status'] == 'Active']
    elif current_status in {'Failed After D0', 'Later Failed'} and 'Current Status' in out:
        out = out[_is_later_failed(out['Current Status'])]
    elif current_status == 'Unresolved':
        mask = pd.Series(False, index=out.index)
        if 'Trigger Day' in out:
            mask |= out['Trigger Day'].eq('Unresolved')
        if 'Trigger' in out:
            mask |= out['Trigger'].eq('No Trigger')
        out = out[mask]

    if opening_path_group != 'All':
        out = out[_opening_path_mask(out, opening_path_group)]

    return out


def trigger_outcome_by_window_tables(trigger_outcomes: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    tables = {}
    for window_label in TRIGGER_EVENT_WINDOW_ORDER:
        if trigger_outcomes is None or trigger_outcomes.empty:
            tables[window_label] = pd.DataFrame(columns=TRIGGER_COMPARISON_BY_WINDOW_COLUMNS)
            continue
        rows = trigger_outcomes[trigger_outcomes['Window'] == window_label].copy()
        tables[window_label] = rows[TRIGGER_COMPARISON_BY_WINDOW_COLUMNS].reset_index(drop=True)
    return tables


def _count_with_pct(count: Any, pct: Any) -> str:
    return f'{count} ({pct})'


def trigger_event_main_tables(trigger_outcomes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    tables = {}
    for window_label, table in trigger_outcome_by_window_tables(trigger_outcomes).items():
        if table.empty:
            tables[window_label] = pd.DataFrame(columns=TRIGGER_EVENT_MAIN_COLUMNS)
            continue
        out = pd.DataFrame({
            'Trigger': table['Trigger'],
            'Eligible': table['Eligible'],
            'Triggered': [_count_with_pct(count, pct) for count, pct in zip(table['Triggered'], table['Trigger Rate'])],
            'Failed': [_count_with_pct(count, pct) for count, pct in zip(table['Failed'], table['Fail %'])],
            'Success': [_count_with_pct(count, pct) for count, pct in zip(table['Success'], table['Success %'])],
            'Currently Active': [_count_with_pct(count, pct) if pct != '-' else '-' for count, pct in zip(table['Active Count'], table['Active %'])],
            'Failed After D0': [_count_with_pct(count, pct) if pct != '-' else '-' for count, pct in zip(table['Failed After D0 Count'], table['Failed After D0 %'])],
            'Median Max': table['Median Max'],
        })
        tables[window_label] = out[TRIGGER_EVENT_MAIN_COLUMNS]
    return tables


def _failure_trend_cell(failed: int, triggered: int) -> str:
    if int(triggered) <= 0:
        return '—'
    success = max(int(triggered) - int(failed), 0)
    pct = round((success / int(triggered)) * 100)
    return f'{pct}% ({success}/{int(triggered)})'


def _failure_trend_read(last_failed: int, last_triggered: int, previous_failed: int, previous_triggered: int) -> str:
    if int(last_triggered) == 0:
        return 'No recent sample'
    if int(last_triggered) < 3:
        return 'Small sample'
    last_rate = (int(last_triggered) - int(last_failed)) / int(last_triggered)
    if last_failed == 0:
        return 'Clean recent'
    if int(previous_triggered) < 3:
        return 'Stable'
    previous_rate = (int(previous_triggered) - int(previous_failed)) / int(previous_triggered)
    delta = (last_rate - previous_rate) * 100
    if delta >= 20:
        return 'Improved recent'
    if delta <= -20:
        return 'Worse recent'
    return 'Stable'


def _trigger_failure_trend_by_trigger(trigger_outcomes: pd.DataFrame | None) -> pd.DataFrame:
    if trigger_outcomes is None or trigger_outcomes.empty:
        return pd.DataFrame(columns=TRIGGER_FAILURE_TREND_BASE_COLUMNS)

    indexed = trigger_outcomes.set_index(['Window', 'Trigger'])
    rows = []
    display_order = ['PDH', '1m ORH', 'VWAP Reclaim', '5m ORH', 'Alt Required']
    for trigger_name in display_order:
        cells = {}
        any_triggered = False
        counts_by_window = {}
        for window_label in TRIGGER_EVENT_WINDOW_ORDER:
            key = (window_label, trigger_name)
            if key in indexed.index:
                row = indexed.loc[key]
                failed = int(row.get('Failed', 0) or 0)
                triggered = int(row.get('Triggered', 0) or 0)
            else:
                failed = 0
                triggered = 0
            any_triggered = any_triggered or triggered > 0
            counts_by_window[window_label] = (failed, triggered)
            cells[TRIGGER_FAILURE_TREND_WINDOW_LABELS[window_label]] = _failure_trend_cell(failed, triggered)
        if not any_triggered and trigger_name == 'Alt Required':
            continue
        last_failed, last_triggered = counts_by_window['Last 5 Setup Dates']
        previous_failed, previous_triggered = counts_by_window['Previous 5 Setup Dates']
        rows.append({
            'Trigger': trigger_name,
            **cells,
            'Read': _failure_trend_read(last_failed, last_triggered, previous_failed, previous_triggered),
        })
    return pd.DataFrame(rows, columns=TRIGGER_FAILURE_TREND_BASE_COLUMNS)


def trigger_failure_trend_matrix(trigger_outcomes: pd.DataFrame | None) -> pd.DataFrame:
    by_trigger = _trigger_failure_trend_by_trigger(trigger_outcomes)
    if by_trigger.empty:
        return pd.DataFrame(columns=TRIGGER_FAILURE_TREND_COLUMNS)

    trigger_columns = [trigger for trigger in by_trigger['Trigger'].tolist() if trigger != 'Alt Required']
    if 'Alt Required' in by_trigger['Trigger'].tolist():
        trigger_columns.append('Alt Required')

    records = []
    for window_label in TRIGGER_FAILURE_TREND_WINDOW_LABELS.values():
        row = {'Window': window_label}
        for trigger_name in trigger_columns:
            match = by_trigger[by_trigger['Trigger'].eq(trigger_name)]
            row[trigger_name] = match.iloc[0][window_label] if not match.empty else '—'
        records.append(row)
    return pd.DataFrame(records, columns=['Window', *trigger_columns])


def trigger_shift_read_table(trigger_outcomes: pd.DataFrame | None) -> pd.DataFrame:
    by_trigger = _trigger_failure_trend_by_trigger(trigger_outcomes)
    if by_trigger.empty:
        return pd.DataFrame(columns=TRIGGER_SHIFT_READ_COLUMNS)
    return by_trigger[TRIGGER_SHIFT_READ_COLUMNS].reset_index(drop=True)


def _percent_point_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text == '-' or text.lower() == 'nan':
        return None
    if '(' in text and ')' in text:
        text = text.split('(', 1)[1].split(')', 1)[0]
    text = text.rstrip('%').strip()
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def trigger_event_shift_highlights(trigger_outcomes: pd.DataFrame | None) -> dict[tuple[str, str, str], str]:
    highlights: dict[tuple[str, str, str], str] = {}
    if trigger_outcomes is None or trigger_outcomes.empty:
        return highlights
    required_windows = {'Last 5 Setup Dates', 'Previous 5 Setup Dates'}
    if not required_windows.issubset(set(trigger_outcomes['Window'])):
        return highlights

    indexed = trigger_outcomes.set_index(['Window', 'Trigger'])
    for trigger_name in TRIGGER_COMPARISON_ORDER:
        pair_keys = [('Last 5 Setup Dates', trigger_name), ('Previous 5 Setup Dates', trigger_name)]
        if any(key not in indexed.index for key in pair_keys):
            continue
        last_row = indexed.loc[pair_keys[0]]
        previous_row = indexed.loc[pair_keys[1]]
        for display_column, source_column, lower_is_better, threshold in TRIGGER_EVENT_SHIFT_METRICS:
            last_value = _percent_point_value(last_row.get(source_column))
            previous_value = _percent_point_value(previous_row.get(source_column))
            if last_value is None or previous_value is None:
                continue
            delta = last_value - previous_value
            if abs(delta) < threshold:
                continue
            direction = 'positive' if (delta < 0 if lower_is_better else delta > 0) else 'negative'
            highlights[('Last 5 Setup Dates', trigger_name, display_column)] = direction
            highlights[('Previous 5 Setup Dates', trigger_name, display_column)] = direction
    return highlights


def trigger_event_highlight_styles(
    table: pd.DataFrame,
    window_label: str,
    highlights: dict[tuple[str, str, str], str],
) -> pd.DataFrame:
    styles = pd.DataFrame('', index=table.index, columns=table.columns)
    if table.empty or not highlights or 'Trigger' not in table:
        return styles
    for idx, trigger_name in table['Trigger'].items():
        for column in table.columns:
            direction = highlights.get((window_label, trigger_name, column))
            if direction:
                styles.at[idx, column] = TRIGGER_EVENT_HIGHLIGHT_STYLES[direction]
    return styles


def style_trigger_event_table(
    table: pd.DataFrame,
    window_label: str,
    highlights: dict[tuple[str, str, str], str],
):
    styles = trigger_event_highlight_styles(table, window_label, highlights)
    if styles.eq('').all().all():
        return table
    return table.style.apply(lambda _: styles, axis=None)


def trigger_quality_table(rows: pd.DataFrame) -> pd.DataFrame:
    columns = ['Trigger', 'Count', 'Failed Count', 'Failed %', 'Day Success %', 'Active %', 'Failed After D0 %', 'Median Current', 'Median Max']
    if rows.empty or 'Trigger' not in rows:
        return pd.DataFrame(columns=columns)
    out = []
    for trigger in TRIGGER_ORDER:
        group = rows[rows['Trigger'] == trigger]
        count = len(group)
        if count == 0:
            out.append({'Trigger': trigger, 'Count': 0, 'Failed Count': 0, 'Failed %': '-', 'Day Success %': '-', 'Active %': '-', 'Failed After D0 %': '-', 'Median Current': '-', 'Median Max': '-'})
            continue
        later_failed = int(_is_later_failed(group["Current Status"]).sum())
        day_failed = int(group["Trigger Day"].eq("Fail").sum())
        failed_count = day_failed + later_failed
        out.append({
            'Trigger': trigger,
            'Count': count,
            'Failed Count': failed_count,
            'Failed %': f'{round((failed_count / count) * 100)}%',
            'Day Success %': f'{round((group["Trigger Day"].eq("Success").sum() / count) * 100)}%',
            'Active %': f'{round((group["Current Status"].eq("Active").sum() / count) * 100)}%',
            'Failed After D0 %': f'{round((later_failed / count) * 100)}%',
            'Median Current': _fmt_pct(group['current_pct_raw'].median() if 'current_pct_raw' in group else None),
            'Median Max': _fmt_pct(group['max_pct_raw'].median() if 'max_pct_raw' in group else None),
        })
    return pd.DataFrame(out, columns=columns)


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


def setup_behavior_overview(con, history: pd.DataFrame | None = None, perf=None) -> dict:
    start = perf_counter()
    dates = setup_dates(con)
    if perf is not None:
        perf.add('Setup Behavior SQL: setup dates', perf_counter() - start)
    if not dates:
        return {
            'summary': pd.DataFrame(columns=COMPARISON_COLUMNS),
            'window_summaries': pd.DataFrame(columns=FULL_SUMMARY_COLUMNS),
            'breakdowns': {},
            'reads': {},
            'snapshots': {},
            'snapshot_cards': {},
            'mixes': {},
            'opening_behavior': {},
            'opening_behavior_main': {},
            'trigger_outcome_comparison': pd.DataFrame(columns=TRIGGER_COMPARISON_COLUMNS),
            'trigger_outcome_by_window': {},
            'trigger_event_main_by_window': {},
            'trigger_failure_trend': pd.DataFrame(columns=TRIGGER_FAILURE_TREND_COLUMNS),
            'trigger_shift_read': pd.DataFrame(columns=TRIGGER_SHIFT_READ_COLUMNS),
            'failure_timing_by_window': pd.DataFrame(columns=FAILURE_TIMING_WINDOW_COLUMNS),
            'failure_timing_by_trigger': {},
            'trigger_event_shift_highlights': {},
            'trigger_quality': {},
            'details': {},
            'behavior_insights': [],
            'windows': [],
        }

    windows = overview_windows(dates)
    if history is None:
        start = perf_counter()
        history = monitor_history(con, perf=perf)
        if perf is not None:
            perf.add('Setup Behavior monitor_history build', perf_counter() - start)
    start = perf_counter()
    window_summaries = pd.DataFrame([summarize_window(history, window) for window in windows], columns=FULL_SUMMARY_COLUMNS)
    summary = comparison_rows(window_summaries)
    summary_by_window = {row['Window']: row.to_dict() for _, row in window_summaries.iterrows()}
    if perf is not None:
        perf.add('Setup Behavior aggregation: summaries', perf_counter() - start)
    start = perf_counter()
    details = {window.label: detail_rows(history, window) for window in windows}
    if perf is not None:
        perf.add('Setup Behavior formatting: detail rows', perf_counter() - start)
    start = perf_counter()
    history_by_window = {}
    for window in windows:
        included = {date.date() for date in window.setup_dates}
        history_by_window[window.label] = history[pd.to_datetime(history['Setup Date']).dt.date.isin(included)].copy() if not history.empty else pd.DataFrame()
    opening_behavior = {label: opening_behavior_table(history_by_window[label]) for label in summary_by_window}
    trigger_outcomes = trigger_outcome_comparison(history_by_window)
    if perf is not None:
        perf.add('Setup Behavior aggregation: trigger/opening tables', perf_counter() - start)
    start = perf_counter()
    result = {
        'summary': summary,
        'window_summaries': window_summaries,
        'breakdowns': {label: selected_window_metrics(row) for label, row in summary_by_window.items()},
        'reads': {label: factual_read(row, opening_behavior[label]) for label, row in summary_by_window.items()},
        'snapshots': {label: selected_window_snapshot(row) for label, row in summary_by_window.items()},
        'snapshot_cards': {
            label: snapshot_cards_html(
                row,
                history_by_window[label],
                trigger_outcomes[trigger_outcomes['Window'].eq(label)] if not trigger_outcomes.empty else pd.DataFrame(),
            )
            for label, row in summary_by_window.items()
        },
        'mixes': {label: mix_tables(row) for label, row in summary_by_window.items()},
        'opening_behavior': opening_behavior,
        'opening_behavior_main': {label: main_opening_behavior_table(history_by_window[label]) for label in summary_by_window},
        'trigger_outcome_comparison': trigger_outcomes,
        'trigger_outcome_by_window': trigger_outcome_by_window_tables(trigger_outcomes),
        'trigger_event_main_by_window': trigger_event_main_tables(trigger_outcomes),
        'trigger_failure_trend': trigger_failure_trend_matrix(trigger_outcomes),
        'trigger_shift_read': trigger_shift_read_table(trigger_outcomes),
        'failure_timing_by_window': failure_timing_by_window_table(history_by_window),
        'failure_timing_by_trigger': {label: failure_timing_by_trigger_table(history_by_window[label]) for label in summary_by_window},
        'trigger_event_shift_highlights': trigger_event_shift_highlights(trigger_outcomes),
        'trigger_quality': {label: trigger_quality_table(history_by_window[label]) for label in summary_by_window},
        'details': details,
        'behavior_insights': generate_behavior_insights(window_summaries, history),
        'windows': windows,
    }
    if perf is not None:
        perf.add('Setup Behavior formatting: display table assembly', perf_counter() - start)
    return result
