from __future__ import annotations

import re
from typing import Any

import pandas as pd


UNCLASSIFIED_SETUP = 'Unclassified'
UNCLASSIFIED_ENTRY_TACTIC = 'Unclassified'

SETUP_SUMMARY_COLUMNS = [
    'Setup',
    'Count',
    'Sample',
    'Active',
    'Active %',
    'D0 Fail',
    'D0 Fail %',
    'Failed After D0',
    'Failed After D0 %',
    'Total Failed',
    'Failure %',
    'Close < BE',
    'Close < BE %',
    'Retested D0',
    'Retested After D0',
    'Median Current %',
    'Median Max %',
    'Median D3 High %',
    'Avg Max %',
    'Rating Avg',
    'Rating 4-5 Count',
    'Latest Setup Date',
]

SETUP_ENTRY_TACTIC_COLUMNS = [
    'Setup',
    'Entry Tactic',
    'Count',
    'Sample',
    'Failure %',
    'D0 Fail %',
    'Active %',
    'Median Max %',
    'Median Current %',
    'Close < BE %',
]

SUMMARY_CARD_COLUMNS = ['Metric', 'Value', 'Detail']
SETUP_FAILURE_TREND_COLUMNS = ['Setup', 'Last 5', 'Previous 5', 'Last 10', 'Last 20', 'Read']
SETUP_TREND_WINDOW_LABELS = {
    'Last 5 setup dates': 'Last 5',
    'Previous 5 setup dates': 'Previous 5',
    'Last 10 setup dates': 'Last 10',
    'Last 20 setup dates': 'Last 20',
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip().lower() in {'', 'nan', 'none', 'null', '-'}


def _clean_label(value: Any, fallback: str) -> str:
    return fallback if _is_missing(value) else str(value).strip()


def _status_series(rows: pd.DataFrame) -> pd.Series:
    if 'Current Status' not in rows:
        return pd.Series('', index=rows.index, dtype=object)
    return rows['Current Status'].fillna('').astype(str).str.strip()


def _trigger_day_series(rows: pd.DataFrame) -> pd.Series:
    if 'Trigger Day' not in rows:
        return pd.Series('', index=rows.index, dtype=object)
    return rows['Trigger Day'].fillna('').astype(str).str.strip()


def _numeric_series(rows: pd.DataFrame, raw_column: str, display_column: str) -> pd.Series:
    if raw_column in rows:
        return pd.to_numeric(rows[raw_column], errors='coerce')
    if display_column in rows:
        text = rows[display_column].fillna('').astype(str).str.replace('%', '', regex=False)
        return pd.to_numeric(text, errors='coerce') / 100
    return pd.Series(float('nan'), index=rows.index)


def _yes_series(rows: pd.DataFrame, column: str) -> pd.Series:
    if column not in rows:
        return pd.Series(False, index=rows.index)
    values = rows[column]
    if values.dtype == bool:
        return values.fillna(False)
    return values.fillna('').astype(str).str.strip().str.casefold().isin({'yes', 'true', '1', 'y'})


def _retest_days(value: Any) -> set[int]:
    if _is_missing(value):
        return set()
    return {int(match) for match in re.findall(r'\bD\s*(\d+)\b', str(value), flags=re.IGNORECASE)}


def _pct(count: int, total: int) -> float:
    return 0.0 if total <= 0 else float(count) / float(total)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return '-'
    try:
        if pd.isna(value):
            return '-'
        return f'{float(value) * 100:.1f}%'
    except (TypeError, ValueError):
        return '-'


def _fmt_num(value: Any) -> str:
    if value is None:
        return '-'
    try:
        if pd.isna(value):
            return '-'
        return f'{float(value):.2f}'
    except (TypeError, ValueError):
        return '-'


def _sample_label(count: int) -> str:
    if count < 5:
        return 'Small sample'
    if count < 15:
        return 'Developing'
    return 'Useful sample'


def _latest_setup_date(rows: pd.DataFrame) -> str:
    if 'Setup Date' not in rows or rows.empty:
        return ''
    dates = pd.to_datetime(rows['Setup Date'], errors='coerce').dropna()
    if dates.empty:
        return ''
    return dates.max().date().isoformat()


def _prepared_rows(rows: pd.DataFrame) -> pd.DataFrame:
    out = rows.copy()
    if out.empty:
        return out
    out['Setup'] = out['Setup'].apply(lambda value: _clean_label(value, UNCLASSIFIED_SETUP)) if 'Setup' in out else UNCLASSIFIED_SETUP
    out['Entry Tactic'] = (
        out['Entry Tactic'].apply(lambda value: _clean_label(value, UNCLASSIFIED_ENTRY_TACTIC))
        if 'Entry Tactic' in out
        else UNCLASSIFIED_ENTRY_TACTIC
    )
    out['_status'] = _status_series(out)
    out['_trigger_day'] = _trigger_day_series(out)
    out['_active'] = out['_status'].eq('Active')
    out['_failed_d0'] = out['_status'].eq('Failed D0') | out['_trigger_day'].eq('Fail')
    out['_failed_after_d0'] = out['_status'].str.match(r'^Failed D[1-9]\d*$', na=False)
    out['_close_below_be'] = _yes_series(out, 'Close < BE')
    retest_source = 'Retest Days Raw' if 'Retest Days Raw' in out else 'Retests'
    retests = out[retest_source].apply(_retest_days) if retest_source in out else pd.Series([set()] * len(out), index=out.index)
    out['_retested_d0'] = retests.apply(lambda days: 0 in days)
    out['_retested_after_d0'] = retests.apply(lambda days: any(day > 0 for day in days))
    out['_current_pct'] = _numeric_series(out, 'current_pct_raw', 'Current %')
    out['_max_pct'] = _numeric_series(out, 'max_pct_raw', 'Max %')
    out['_d3_high_pct'] = _numeric_series(out, 'd3_high_pct_raw', 'D3 High %')
    out['_rating'] = pd.to_numeric(out['Rating'], errors='coerce') if 'Rating' in out else pd.Series(float('nan'), index=out.index)
    return out


def filter_setup_performance_rows(
    rows: pd.DataFrame,
    setup_date_window: str = 'All',
    rating_filter: str = 'All',
    current_status_filter: str = 'All',
) -> pd.DataFrame:
    """Apply page-level filters to canonical Rolling Setup Monitor history rows."""
    prepared = _prepared_rows(rows)
    if prepared.empty:
        return prepared

    out = prepared
    if setup_date_window != 'All' and 'Setup Date' in out:
        match = re.search(r'Last\s+(\d+)\s+setup dates', setup_date_window, flags=re.IGNORECASE)
        if match:
            limit = int(match.group(1))
            dates = pd.to_datetime(out['Setup Date'], errors='coerce')
            latest_dates = sorted(dates.dropna().dt.normalize().unique())[-limit:]
            out = out[dates.dt.normalize().isin(latest_dates)]

    if rating_filter == '4-5 only':
        out = out[out['_rating'].between(4, 5, inclusive='both')]
    elif rating_filter == '3+ only':
        out = out[out['_rating'] >= 3]

    if current_status_filter == 'Active only':
        out = out[out['_active']]
    elif current_status_filter == 'Failed only':
        out = out[out['_failed_d0'] | out['_failed_after_d0']]

    return out.copy()


def build_setup_summary(rows: pd.DataFrame, sort_by: str = 'Count') -> pd.DataFrame:
    prepared = _prepared_rows(rows)
    if prepared.empty:
        return pd.DataFrame(columns=SETUP_SUMMARY_COLUMNS)

    records = []
    for setup, group in prepared.groupby('Setup', dropna=False, sort=False):
        count = int(len(group))
        active = int(group['_active'].sum())
        failed_d0 = int(group['_failed_d0'].sum())
        failed_after_d0 = int(group['_failed_after_d0'].sum())
        total_failed = failed_d0 + failed_after_d0
        close_be = int(group['_close_below_be'].sum())
        rating_45 = int(group['_rating'].between(4, 5, inclusive='both').sum())
        records.append({
            'Setup': setup,
            'Count': count,
            'Sample': _sample_label(count),
            'Active': active,
            'Active %': _fmt_pct(_pct(active, count)),
            'D0 Fail': failed_d0,
            'D0 Fail %': _fmt_pct(_pct(failed_d0, count)),
            'Failed After D0': failed_after_d0,
            'Failed After D0 %': _fmt_pct(_pct(failed_after_d0, count)),
            'Total Failed': total_failed,
            'Failure %': _fmt_pct(_pct(total_failed, count)),
            'Close < BE': close_be,
            'Close < BE %': _fmt_pct(_pct(close_be, count)),
            'Retested D0': int(group['_retested_d0'].sum()),
            'Retested After D0': int(group['_retested_after_d0'].sum()),
            'Median Current %': _fmt_pct(group['_current_pct'].median()),
            'Median Max %': _fmt_pct(group['_max_pct'].median()),
            'Median D3 High %': _fmt_pct(group['_d3_high_pct'].median()),
            'Avg Max %': _fmt_pct(group['_max_pct'].mean()),
            'Rating Avg': _fmt_num(group['_rating'].mean()),
            'Rating 4-5 Count': rating_45,
            'Latest Setup Date': _latest_setup_date(group),
            '_failure_sort': _pct(total_failed, count),
            '_median_max_sort': group['_max_pct'].median(),
        })

    out = pd.DataFrame(records)
    if sort_by == 'Failure %':
        out = out.sort_values(['_failure_sort', 'Count', '_median_max_sort', 'Setup'], ascending=[False, False, False, True])
    elif sort_by == 'Median Max %':
        out = out.sort_values(['_median_max_sort', 'Count', '_failure_sort', 'Setup'], ascending=[False, False, True, True])
    else:
        out = out.sort_values(['Count', '_failure_sort', '_median_max_sort', 'Setup'], ascending=[False, False, False, True])
    return out[SETUP_SUMMARY_COLUMNS].reset_index(drop=True)


def build_setup_entry_tactic_summary(rows: pd.DataFrame) -> pd.DataFrame:
    prepared = _prepared_rows(rows)
    if prepared.empty:
        return pd.DataFrame(columns=SETUP_ENTRY_TACTIC_COLUMNS)

    records = []
    for (setup, tactic), group in prepared.groupby(['Setup', 'Entry Tactic'], dropna=False, sort=False):
        count = int(len(group))
        failed_d0 = int(group['_failed_d0'].sum())
        total_failed = failed_d0 + int(group['_failed_after_d0'].sum())
        active = int(group['_active'].sum())
        close_be = int(group['_close_below_be'].sum())
        records.append({
            'Setup': setup,
            'Entry Tactic': tactic,
            'Count': count,
            'Sample': _sample_label(count),
            'Failure %': _fmt_pct(_pct(total_failed, count)),
            'D0 Fail %': _fmt_pct(_pct(failed_d0, count)),
            'Active %': _fmt_pct(_pct(active, count)),
            'Median Max %': _fmt_pct(group['_max_pct'].median()),
            'Median Current %': _fmt_pct(group['_current_pct'].median()),
            'Close < BE %': _fmt_pct(_pct(close_be, count)),
            '_failure_sort': _pct(total_failed, count),
            '_median_max_sort': group['_max_pct'].median(),
        })
    out = pd.DataFrame(records).sort_values(
        ['Setup', 'Count', '_failure_sort', '_median_max_sort', 'Entry Tactic'],
        ascending=[True, False, False, False, True],
    )
    return out[SETUP_ENTRY_TACTIC_COLUMNS].reset_index(drop=True)


def setup_performance_cards(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=SUMMARY_CARD_COLUMNS)

    work = summary.copy()
    classified = work[work['Setup'] != UNCLASSIFIED_SETUP]
    sample_gate = classified[classified['Count'] >= 5]
    if sample_gate.empty:
        sample_gate = classified if not classified.empty else work

    total_classified = int(classified['Count'].sum())
    unclassified_count = int(work.loc[work['Setup'].eq(UNCLASSIFIED_SETUP), 'Count'].sum())
    small_sample_note = ' Small sample.' if not classified.empty and classified[classified['Count'] >= 5].empty else ''
    highest_active = sample_gate.assign(_active=sample_gate['Active %'].str.rstrip('%').astype(float)).sort_values(
        ['_active', 'Count', 'Setup'],
        ascending=[False, False, True],
    ).head(1)
    lowest_failure = sample_gate.assign(_failure=sample_gate['Failure %'].str.rstrip('%').astype(float)).sort_values(
        ['_failure', 'Count', 'Setup'],
        ascending=[True, False, True],
    ).head(1)
    highest_failure = sample_gate.assign(_failure=sample_gate['Failure %'].str.rstrip('%').astype(float)).sort_values(
        ['_failure', 'Count', 'Setup'],
        ascending=[False, False, True],
    ).head(1)

    def _failure_detail(row: pd.Series) -> str:
        failed = int(row.get('Total Failed', 0) or 0)
        count = int(row.get('Count', 0) or 0)
        return f"{failed} failed / {count} rows{small_sample_note}"

    def _active_detail(row: pd.Series) -> str:
        active = int(row.get('Active', 0) or 0)
        count = int(row.get('Count', 0) or 0)
        return f"{active} active / {count} rows{small_sample_note}"

    return pd.DataFrame([
        {
            'Metric': 'Total Classified Setups',
            'Value': str(total_classified),
            'Detail': f'{len(classified)} setup types',
        },
        {
            'Metric': 'Setup Types',
            'Value': str(len(classified)),
            'Detail': 'classified setup groups',
        },
        {
            'Metric': 'Highest Active Rate',
            'Value': highest_active['Setup'].iloc[0] if not highest_active.empty else '-',
            'Detail': _active_detail(highest_active.iloc[0]) if not highest_active.empty else '-',
        },
        {
            'Metric': 'Lowest Failure Setup',
            'Value': lowest_failure['Setup'].iloc[0] if not lowest_failure.empty else '-',
            'Detail': _failure_detail(lowest_failure.iloc[0]) if not lowest_failure.empty else '-',
        },
        {
            'Metric': 'Highest Failure Setup',
            'Value': highest_failure['Setup'].iloc[0] if not highest_failure.empty else '-',
            'Detail': _failure_detail(highest_failure.iloc[0]) if not highest_failure.empty else '-',
        },
        {
            'Metric': 'Unclassified Count',
            'Value': str(unclassified_count),
            'Detail': 'blank/null Setup rows',
        },
    ], columns=SUMMARY_CARD_COLUMNS)


def _setup_trend_cell(failed: int, count: int) -> str:
    if int(count) <= 0:
        return '—'
    success = max(int(count) - int(failed), 0)
    pct = round((success / int(count)) * 100)
    return f'{pct}% ({success}/{int(count)})'


def _setup_trend_read(last_failed: int, last_count: int, previous_failed: int, previous_count: int) -> str:
    if int(last_count) == 0:
        return 'No recent sample'
    if int(last_count) < 5:
        return 'Small sample'
    last_rate = (int(last_count) - int(last_failed)) / int(last_count)
    if last_failed == 0:
        return 'Clean recent'
    if int(previous_count) < 5:
        return 'Small sample'
    previous_rate = (int(previous_count) - int(previous_failed)) / int(previous_count)
    delta = (last_rate - previous_rate) * 100
    if delta >= 20:
        return 'Improved recent'
    if delta <= -20:
        return 'Worse recent'
    return 'Stable'


def _window_rows(prepared: pd.DataFrame, label: str) -> pd.DataFrame:
    if prepared.empty or 'Setup Date' not in prepared:
        return prepared.iloc[0:0].copy()
    dates = pd.to_datetime(prepared['Setup Date'], errors='coerce')
    setup_dates = sorted(dates.dropna().dt.normalize().unique())
    if label == 'Previous 5 setup dates':
        selected = setup_dates[-10:-5]
    else:
        match = re.search(r'Last\s+(\d+)\s+setup dates', label, flags=re.IGNORECASE)
        selected = setup_dates[-int(match.group(1)):] if match else setup_dates
    if not selected:
        return prepared.iloc[0:0].copy()
    return prepared[dates.dt.normalize().isin(selected)].copy()


def build_setup_failure_trend(rows: pd.DataFrame) -> pd.DataFrame:
    prepared = _prepared_rows(rows)
    if prepared.empty:
        return pd.DataFrame(columns=SETUP_FAILURE_TREND_COLUMNS)

    setup_names = sorted(str(name) for name in prepared['Setup'].dropna().unique())
    windows = {
        label: _window_rows(prepared, label)
        for label in SETUP_TREND_WINDOW_LABELS
    }
    records = []
    for setup in setup_names:
        cells = {}
        counts = {}
        total_rows = 0
        for window_label, display_label in SETUP_TREND_WINDOW_LABELS.items():
            group = windows[window_label][windows[window_label]['Setup'].eq(setup)]
            count = int(len(group))
            failed = int((group['_failed_d0'] | group['_failed_after_d0']).sum()) if count else 0
            total_rows += count
            counts[window_label] = (failed, count)
            cells[display_label] = _setup_trend_cell(failed, count)
        if total_rows <= 0:
            continue
        last_failed, last_count = counts['Last 5 setup dates']
        previous_failed, previous_count = counts['Previous 5 setup dates']
        records.append({
            'Setup': setup,
            **cells,
            'Read': _setup_trend_read(last_failed, last_count, previous_failed, previous_count),
            '_sort_count': last_count,
            '_sort_failure': (last_failed / last_count) if last_count else -1,
        })
    if not records:
        return pd.DataFrame(columns=SETUP_FAILURE_TREND_COLUMNS)
    out = pd.DataFrame(records).sort_values(
        ['_sort_count', '_sort_failure', 'Setup'],
        ascending=[False, False, True],
    )
    return out[SETUP_FAILURE_TREND_COLUMNS].reset_index(drop=True)
