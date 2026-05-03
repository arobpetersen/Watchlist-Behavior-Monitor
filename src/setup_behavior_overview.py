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
    'Day Success',
    'Day Fail',
    'Unresolved',
    'Active',
    'Later Failed',
    'Clean 1m',
    'Clean 5m',
    'PDH',
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
    'PDH',
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


def overview_windows(setup_date_values) -> list[OverviewWindow]:
    if isinstance(setup_date_values, (str, pd.Timestamp)) or not hasattr(setup_date_values, '__iter__'):
        dates = [_date(setup_date_values)]
    else:
        dates = sorted({_date(value) for value in setup_date_values})
    return [
        OverviewWindow('Last 5 Setup Dates', tuple(dates[-5:])),
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
    one = rows['1m ORH'] if '1m ORH' in rows else pd.Series(dtype=object)
    five = rows['5m ORH'] if '5m ORH' in rows else pd.Series(dtype=object)
    notes = rows['Notes'] if 'Notes' in rows else pd.Series(dtype=object)
    retest = rows['Retest Day'] if 'Retest Day' in rows else pd.Series(dtype=object)

    d3_values = rows['d3_high_pct_raw'].dropna() if 'd3_high_pct_raw' in rows else pd.Series(dtype=float)

    return {
        'Window': window.label,
        'Dates': f'{_fmt_date(window.start_date)} \u2192 {_fmt_date(window.end_date)}',
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

    out = pd.DataFrame({
        'Setup Date': pd.to_datetime(rows['Setup Date']).dt.date.astype(str),
        'Ticker': rows['Ticker'].apply(_display),
        'Current Status': rows['Current Status'].apply(_display),
        'Trigger Day': rows['Trigger Day'].apply(_display),
        'Trigger': rows['Trigger'].apply(_display),
        'PDH': rows['PDH'].apply(_display) if 'PDH' in rows else '-',
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
    'Later Failed %',
    'Median Current',
    'Median Max',
]


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
    return series.isin({'Failed D1', 'Failed D2', 'Failed D3'})


def _is_blank_or_dash(series: pd.Series) -> pd.Series:
    normalized = series.fillna('').astype(str).str.strip()
    return normalized.isin({'', '-', '—', 'â€”'})


def _pct_of_rows(count: int, denominator: int) -> str:
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
        'Later Failed %': _pct_of_rows(int(_is_later_failed(rows['Current Status']).sum()) if 'Current Status' in rows else 0, count),
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
    one = rows['1m ORH'] if '1m ORH' in rows else pd.Series('', index=rows.index)
    five = rows['5m ORH'] if '5m ORH' in rows else pd.Series('', index=rows.index)
    pdh = rows['PDH'] if 'PDH' in rows else pd.Series('', index=rows.index)
    trigger = rows['Trigger'] if 'Trigger' in rows else pd.Series('', index=rows.index)

    one_success = one.eq('success')
    one_failed = one.eq('failed')
    five_success = five.eq('success')
    five_failed_or_blank = five.eq('failed') | _is_blank_or_dash(five)
    pdh_success = pdh.eq('success')
    pdh_failed_or_blank = pdh.eq('failed') | _is_blank_or_dash(pdh)
    successful_trigger = trigger.isin({'PDH', '1m ORH', '5m ORH', 'Alt Required'})

    masks = [
        ('Clean 1m ORH Success', one_success),
        ('1m ORH Failed, Later Reclaimed', one_failed & (five_success | pdh_success)),
        ('1m ORH Failed, Never Recovered', one_failed & ~five_success & ~pdh_success),
        ('5m ORH Success After 1m Failure', one_failed & five_success),
        ('PDH Success After Early Noise', pdh_success & (one.eq('failed') | five.eq('failed'))),
        ('Failed All Opening Triggers', one_failed & five_failed_or_blank & pdh_failed_or_blank & ~successful_trigger),
    ]
    return pd.DataFrame([_opening_path_row(label, rows[mask], total) for label, mask in masks], columns=columns)


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
    day_success = window_summary.get('Day Success', '-')
    active = window_summary.get('Active', '-')
    later_failed = window_summary.get('Later Failed', '-')
    median_current = window_summary.get('Median Current', '-')
    median_max = window_summary.get('Median Max', '-')
    clean_1m = _opening_count(opening_behavior, 'Clean 1m ORH Success')
    reclaimed = _opening_count(opening_behavior, '1m ORH Failed, Later Reclaimed')
    failed_all = _opening_count(opening_behavior, 'Failed All Opening Triggers')
    median_max_raw = window_summary.get('Median Max', '-')
    positive_max = median_max_raw != '-' and not str(median_max_raw).startswith('-')

    if reclaimed > 0 and positive_max:
        behavior = (
            f'Opening behavior is choppy but constructive: {reclaimed} setup'
            f'{"s" if reclaimed != 1 else ""} had an early 1m ORH failure followed by a later 5m ORH/PDH reclaim.'
        )
    elif clean_1m > 0 and reclaimed == 0 and failed_all == 0:
        behavior = (
            f'Opening behavior is clean early: {clean_1m} setup'
            f'{"s" if clean_1m != 1 else ""} followed the 1m ORH path.'
        )
    elif failed_all > 0 and failed_all >= clean_1m + reclaimed:
        behavior = (
            f'Opening behavior is failure-heavy: {failed_all} setup'
            f'{"s" if failed_all != 1 else ""} failed opening triggers without a later displayed reclaim.'
        )
    else:
        behavior = 'Opening behavior is mixed across clean triggers, later reclaims, and unresolved or failed paths.'

    return (
        f'{window} includes {setups} setups across {setup_dates_count} setup dates. '
        f'{day_success} succeeded on trigger day, {active} remain active, and {later_failed} failed later. '
        f'Median current return is {median_current} and median max return is {median_max}. '
        f'{behavior}'
    )


def selected_window_snapshot(window_summary: dict) -> str:
    setups = window_summary.get('Setups', 0)
    setup_dates_count = window_summary.get('Setup Dates', 0)
    day_success_pct = _pct_from_count_text(window_summary.get('Day Success', '-'))
    active_pct = _pct_from_count_text(window_summary.get('Active', '-'))
    later_failed_pct = _pct_from_count_text(window_summary.get('Later Failed', '-'))
    median_current = window_summary.get('Median Current', '-')
    median_max = window_summary.get('Median Max', '-')
    return (
        f'{setups} setups across {setup_dates_count} setup dates | '
        f'{day_success_pct} Day Success | {active_pct} Active | {later_failed_pct} Later Failed | '
        f'Median Current {median_current} | Median Max {median_max}'
    )


def snapshot_cards_html(window_summary: dict) -> str:
    setups = escape(str(window_summary.get('Setups', 0)))
    setup_dates_count = escape(str(window_summary.get('Setup Dates', 0)))
    day_success_pct = escape(_pct_from_count_text(window_summary.get('Day Success', '-')))
    active_pct = escape(_pct_from_count_text(window_summary.get('Active', '-')))
    later_failed_pct = escape(_pct_from_count_text(window_summary.get('Later Failed', '-')))
    median_current = escape(str(window_summary.get('Median Current', '-')))
    median_max = escape(str(window_summary.get('Median Max', '-')))
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
</style>
<div class="snapshot-grid">
  <section class="snapshot-card"><div class="snapshot-label">Scope</div><div class="snapshot-value">{setups}</div><div class="snapshot-sub">{setup_dates_count} setup dates</div></section>
  <section class="snapshot-card"><div class="snapshot-label">Trigger Day</div><div class="snapshot-value">{day_success_pct}</div><div class="snapshot-sub">Day Success</div></section>
  <section class="snapshot-card"><div class="snapshot-label">Current Outcome</div><div class="snapshot-value">{active_pct}</div><div class="snapshot-sub">{later_failed_pct} later failed</div></section>
  <section class="snapshot-card"><div class="snapshot-label">Follow-Through</div><div class="snapshot-value">{median_max}</div><div class="snapshot-sub">Median Max; current {median_current}</div></section>
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
            {'Metric': 'Later Failed', 'Value': window_summary.get('Later Failed', '-')},
            {'Metric': 'Unresolved / Not Active', 'Value': _fmt_count(unresolved + day_fail, int(window_summary.get('Setups', 0) or 0))},
        ]),
        'Trigger Mix': pd.DataFrame([
            {'Metric': 'PDH', 'Value': window_summary.get('PDH', '-')},
            {'Metric': '1m ORH', 'Value': window_summary.get('Clean 1m', '-')},
            {'Metric': '5m ORH', 'Value': window_summary.get('Clean 5m', '-')},
            {'Metric': 'Alt Required', 'Value': window_summary.get('Alt Required', '-')},
            {'Metric': 'Failed PDH Trigger', 'Value': window_summary.get('Failed PDH Trigger', '-')},
            {'Metric': 'Failed OR Trigger', 'Value': window_summary.get('Failed OR Trigger', '-')},
            {'Metric': 'No Trigger', 'Value': window_summary.get('No Trigger', '-')},
        ]),
    }


TRIGGER_ORDER = ['PDH', '1m ORH', '5m ORH', 'Alt Required', 'Failed PDH Trigger', 'Failed OR Trigger', 'No Trigger']


def trigger_quality_table(rows: pd.DataFrame) -> pd.DataFrame:
    columns = ['Trigger', 'Count', 'Failed Count', 'Failed %', 'Day Success %', 'Active %', 'Later Failed %', 'Median Current', 'Median Max']
    if rows.empty or 'Trigger' not in rows:
        return pd.DataFrame(columns=columns)
    out = []
    for trigger in TRIGGER_ORDER:
        group = rows[rows['Trigger'] == trigger]
        count = len(group)
        if count == 0:
            out.append({'Trigger': trigger, 'Count': 0, 'Failed Count': 0, 'Failed %': '-', 'Day Success %': '-', 'Active %': '-', 'Later Failed %': '-', 'Median Current': '-', 'Median Max': '-'})
            continue
        later_failed = int(group["Current Status"].isin({"Failed D1", "Failed D2", "Failed D3"}).sum())
        day_failed = int(group["Trigger Day"].eq("Fail").sum())
        failed_count = day_failed + later_failed
        out.append({
            'Trigger': trigger,
            'Count': count,
            'Failed Count': failed_count,
            'Failed %': f'{round((failed_count / count) * 100)}%',
            'Day Success %': f'{round((group["Trigger Day"].eq("Success").sum() / count) * 100)}%',
            'Active %': f'{round((group["Current Status"].eq("Active").sum() / count) * 100)}%',
            'Later Failed %': f'{round((later_failed / count) * 100)}%',
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


def setup_behavior_overview(con) -> dict:
    dates = setup_dates(con)
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
            'trigger_quality': {},
            'details': {},
            'windows': [],
        }

    windows = overview_windows(dates)
    history = monitor_history(con)
    window_summaries = pd.DataFrame([summarize_window(history, window) for window in windows], columns=FULL_SUMMARY_COLUMNS)
    summary = comparison_rows(window_summaries)
    summary_by_window = {row['Window']: row.to_dict() for _, row in window_summaries.iterrows()}
    details = {window.label: detail_rows(history, window) for window in windows}
    history_by_window = {}
    for window in windows:
        included = {date.date() for date in window.setup_dates}
        history_by_window[window.label] = history[pd.to_datetime(history['Setup Date']).dt.date.isin(included)].copy() if not history.empty else pd.DataFrame()
    opening_behavior = {label: opening_behavior_table(history_by_window[label]) for label in summary_by_window}
    return {
        'summary': summary,
        'window_summaries': window_summaries,
        'breakdowns': {label: selected_window_metrics(row) for label, row in summary_by_window.items()},
        'reads': {label: factual_read(row, opening_behavior[label]) for label, row in summary_by_window.items()},
        'snapshots': {label: selected_window_snapshot(row) for label, row in summary_by_window.items()},
        'snapshot_cards': {label: snapshot_cards_html(row) for label, row in summary_by_window.items()},
        'mixes': {label: mix_tables(row) for label, row in summary_by_window.items()},
        'opening_behavior': opening_behavior,
        'trigger_quality': {label: trigger_quality_table(history_by_window[label]) for label in summary_by_window},
        'details': details,
        'windows': windows,
    }
