from __future__ import annotations

from typing import Any

import pandas as pd


FAILURE_TIMING_PERCENT_COLUMNS = [
    'Active %',
    'D0 Fail %',
    'D1 Fail %',
    'D2 Fail %',
    'D3 Fail %',
    'Failed After D3 %',
    'Unresolved %',
]
FAILURE_TIMING_DISPLAY_COLUMNS = ['Triggered', *FAILURE_TIMING_PERCENT_COLUMNS]


def _rows_frame(rows: pd.DataFrame | list[dict] | tuple[dict, ...] | None) -> pd.DataFrame:
    if rows is None:
        return pd.DataFrame()
    if isinstance(rows, pd.DataFrame):
        return rows.copy()
    return pd.DataFrame(list(rows))


def _text_series(rows: pd.DataFrame, column: str) -> pd.Series:
    if rows.empty:
        return pd.Series(dtype=object)
    if column not in rows:
        return pd.Series('', index=rows.index, dtype=object)
    return rows[column].fillna('').astype(str).str.strip()


def _pct(count: int, denominator: int) -> str:
    if int(denominator) <= 0:
        return '-'
    return f'{round((int(count) / int(denominator)) * 100)}%'


def _failed_after_d3_mask(status: pd.Series) -> pd.Series:
    extracted = status.str.extract(r'^Failed D(\d+)\+?$', expand=False)
    day = pd.to_numeric(extracted, errors='coerce')
    return day.gt(3).fillna(False) | status.isin({'Failed After D3', 'Failed D4+'})


def _distribution_row(rows: pd.DataFrame) -> dict[str, Any]:
    trigger_day = _text_series(rows, 'Trigger Day')
    status = _text_series(rows, 'Current Status')
    triggered = trigger_day.isin({'Success', 'Fail'})
    denominator = int(triggered.sum())

    d0 = triggered & (trigger_day.eq('Fail') | status.eq('Failed D0'))
    d1 = triggered & status.eq('Failed D1')
    d2 = triggered & status.eq('Failed D2')
    d3 = triggered & status.eq('Failed D3')
    after_d3 = triggered & _failed_after_d3_mask(status)
    active = triggered & status.eq('Active')
    classified = active | d0 | d1 | d2 | d3 | after_d3
    unresolved = triggered & ~classified

    counts = {
        'Triggered': denominator,
        'Active': int(active.sum()),
        'D0 Fail': int(d0.sum()),
        'D1 Fail': int(d1.sum()),
        'D2 Fail': int(d2.sum()),
        'D3 Fail': int(d3.sum()),
        'Failed After D3': int(after_d3.sum()),
        'Unresolved': int(unresolved.sum()),
    }
    counts.update({
        'Active %': _pct(counts['Active'], denominator),
        'D0 Fail %': _pct(counts['D0 Fail'], denominator),
        'D1 Fail %': _pct(counts['D1 Fail'], denominator),
        'D2 Fail %': _pct(counts['D2 Fail'], denominator),
        'D3 Fail %': _pct(counts['D3 Fail'], denominator),
        'Failed After D3 %': _pct(counts['Failed After D3'], denominator),
        'Unresolved %': _pct(counts['Unresolved'], denominator),
    })
    return counts


def failure_timing_distribution(
    rows: pd.DataFrame | list[dict] | tuple[dict, ...] | None,
    group_by: str | None = None,
) -> pd.DataFrame:
    """Summarize when triggered setup rows fail using existing status fields."""
    frame = _rows_frame(rows)
    if group_by is None:
        return pd.DataFrame([_distribution_row(frame)], columns=[*FAILURE_TIMING_DISPLAY_COLUMNS, 'Active', 'D0 Fail', 'D1 Fail', 'D2 Fail', 'D3 Fail', 'Failed After D3', 'Unresolved'])

    if frame.empty:
        return pd.DataFrame(columns=[group_by, *FAILURE_TIMING_DISPLAY_COLUMNS])
    if group_by not in frame:
        frame[group_by] = ''

    records = []
    for value, group in frame.groupby(group_by, dropna=False, sort=True):
        row = _distribution_row(group)
        if int(row['Triggered']) <= 0:
            continue
        row[group_by] = '' if pd.isna(value) else str(value)
        records.append(row)
    columns = [group_by, *FAILURE_TIMING_DISPLAY_COLUMNS, 'Active', 'D0 Fail', 'D1 Fail', 'D2 Fail', 'D3 Fail', 'Failed After D3', 'Unresolved']
    return pd.DataFrame(records, columns=columns)
