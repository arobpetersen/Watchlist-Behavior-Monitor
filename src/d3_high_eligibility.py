from __future__ import annotations

from typing import Any

import pandas as pd


RAW_D3_HIGH_COLUMN = 'd3_high_pct_raw'
ELIGIBLE_D3_HIGH_COLUMN = 'eligible_d3_high_pct_raw'
D3_HIGH_ELIGIBLE_COLUMN = 'D3 High Eligible'


def _text_series(rows: pd.DataFrame, column: str) -> pd.Series:
    if rows is None or rows.empty:
        return pd.Series(dtype=object)
    if column not in rows:
        return pd.Series('', index=rows.index, dtype=object)
    return rows[column].fillna('').astype(str).str.strip()


def _numeric_d3_high(rows: pd.DataFrame) -> pd.Series:
    if rows is None or rows.empty:
        return pd.Series(dtype='float64')
    if RAW_D3_HIGH_COLUMN in rows:
        return pd.to_numeric(rows[RAW_D3_HIGH_COLUMN], errors='coerce')
    if 'D3 High %' in rows:
        text = rows['D3 High %'].fillna('').astype(str).str.replace('%', '', regex=False).str.strip()
        return pd.to_numeric(text, errors='coerce') / 100
    return pd.Series(float('nan'), index=rows.index)


def d3_high_survived_through_d3_mask(rows: pd.DataFrame) -> pd.Series:
    """Rows whose trigger path survived long enough for D3 high to be tradable."""
    if rows is None or rows.empty:
        return pd.Series(dtype=bool)

    status = _text_series(rows, 'Current Status')
    trigger_day = _text_series(rows, 'Trigger Day')
    triggered_success = trigger_day.eq('Success')
    failed_before_or_on_d3 = trigger_day.eq('Fail') | status.isin({'Failed D0', 'Failed D1', 'Failed D2', 'Failed D3'})
    return triggered_success & ~failed_before_or_on_d3


def d3_high_eligible_mask(rows: pd.DataFrame) -> pd.Series:
    """Rows that should contribute to primary Median D3 High metrics."""
    if rows is None or rows.empty:
        return pd.Series(dtype=bool)
    return d3_high_survived_through_d3_mask(rows) & _numeric_d3_high(rows).notna()


def eligible_d3_high_pct(rows: pd.DataFrame) -> pd.Series:
    if rows is None or rows.empty:
        return pd.Series(dtype='float64')
    if ELIGIBLE_D3_HIGH_COLUMN in rows:
        return pd.to_numeric(rows[ELIGIBLE_D3_HIGH_COLUMN], errors='coerce')
    values = _numeric_d3_high(rows)
    return values.where(d3_high_eligible_mask(rows))


def display_d3_high_eligible(value: Any) -> str:
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    try:
        if pd.isna(value):
            return 'No'
    except (TypeError, ValueError):
        pass
    text = str(value).strip().casefold()
    return 'Yes' if text in {'yes', 'true', '1', 'y'} else 'No'
