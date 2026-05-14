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
    'Failed D0',
    'Failed D0 %',
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
    'Failed D0 %',
    'Active %',
    'Median Max %',
    'Median Current %',
    'Close < BE %',
]

SUMMARY_CARD_COLUMNS = ['Metric', 'Value', 'Detail']


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
    out['_active'] = out['_status'].eq('Active')
    out['_failed_d0'] = out['_status'].eq('Failed D0')
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
            'Failed D0': failed_d0,
            'Failed D0 %': _fmt_pct(_pct(failed_d0, count)),
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
            'Failed D0 %': _fmt_pct(_pct(failed_d0, count)),
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
    most_common = classified.sort_values(['Count', 'Setup'], ascending=[False, True]).head(1)
    highest_failure = sample_gate.assign(_failure=sample_gate['Failure %'].str.rstrip('%').astype(float)).sort_values(
        ['_failure', 'Count', 'Setup'],
        ascending=[False, False, True],
    ).head(1)
    best_median = sample_gate.assign(_median=sample_gate['Median Max %'].str.rstrip('%').replace('-', float('nan')).astype(float)).sort_values(
        ['_median', 'Count', 'Setup'],
        ascending=[False, False, True],
    ).head(1)

    return pd.DataFrame([
        {
            'Metric': 'Total Classified Setups',
            'Value': str(total_classified),
            'Detail': f'{len(classified)} setup types',
        },
        {
            'Metric': 'Most Common Setup',
            'Value': most_common['Setup'].iloc[0] if not most_common.empty else '-',
            'Detail': f"{int(most_common['Count'].iloc[0])} rows" if not most_common.empty else '-',
        },
        {
            'Metric': 'Highest Failure Setup',
            'Value': highest_failure['Setup'].iloc[0] if not highest_failure.empty else '-',
            'Detail': f"{highest_failure['Failure %'].iloc[0]} of {int(highest_failure['Count'].iloc[0])}" if not highest_failure.empty else '-',
        },
        {
            'Metric': 'Best Median Max % Setup',
            'Value': best_median['Setup'].iloc[0] if not best_median.empty else '-',
            'Detail': f"{best_median['Median Max %'].iloc[0]} median max, {int(best_median['Count'].iloc[0])} rows" if not best_median.empty else '-',
        },
        {
            'Metric': 'Unclassified Count',
            'Value': str(unclassified_count),
            'Detail': 'blank/null Setup rows',
        },
    ], columns=SUMMARY_CARD_COLUMNS)
