from __future__ import annotations

from typing import Any

import pandas as pd


FALLBACK_TRIGGER_LABELS = {'Alt Required', 'Failed OR Trigger', 'No Trigger'}
ORH_TRIGGER_LABELS = {'1m ORH', '5m ORH'}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        text = str(value).replace(',', '').strip()
        if text in {'', '-'}:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _first_present(row: pd.Series, names: list[str]) -> Any:
    for name in names:
        if name in row:
            value = row.get(name)
            if _text(value) != '':
                return value
    return None


def _trigger_label(row: pd.Series) -> str:
    return _text(_first_present(row, ['trigger_type', 'Trigger']))


def _vwap_result(row: pd.Series) -> str:
    return _text(_first_present(row, ['vwap_reclaim_result', 'VWAP Reclaim'])).casefold()


def _vwap_price(row: pd.Series) -> float | None:
    return _num(_first_present(row, ['vwap_reclaim_trigger_price', 'VWAP Reclaim Trigger Price']))


def _resolved_trigger_price(row: pd.Series) -> float | None:
    return _num(_first_present(row, ['trigger_level', 'Trigger Level']))


def _vwap_stop_valid(row: pd.Series) -> bool:
    value = _first_present(row, ['vwap_reclaim_stop_valid', 'VWAP Reclaim Stop Valid'])
    if value is None or _text(value) == '':
        return True
    if isinstance(value, str):
        return value.strip().casefold() not in {'false', 'no', '0'}
    return bool(value)


def should_promote_vwap_reclaim(row: pd.Series) -> bool:
    if _vwap_result(row) != 'success' or _vwap_price(row) is None or not _vwap_stop_valid(row):
        return False
    trigger = _trigger_label(row)
    if trigger in FALLBACK_TRIGGER_LABELS:
        return True
    if trigger in ORH_TRIGGER_LABELS:
        existing_price = _resolved_trigger_price(row)
        return existing_price is not None and _vwap_price(row) < existing_price
    return False


def resolve_display_triggers(rows: pd.DataFrame) -> pd.DataFrame:
    """Promote successful VWAP Reclaim to the displayed trigger when warranted.

    The rule is deterministic and display-focused:
    - fallback labels promote when VWAP succeeded;
    - 1m/5m ORH labels promote only when VWAP trigger price is lower;
    - PDH and other labels are preserved.
    """
    if rows.empty:
        return rows.copy()
    out = rows.copy()
    for idx, row in out.iterrows():
        if not should_promote_vwap_reclaim(row):
            continue
        if 'trigger_type' in out:
            out.at[idx, 'trigger_type'] = 'VWAP Reclaim'
        if 'Trigger' in out:
            out.at[idx, 'Trigger'] = 'VWAP Reclaim'
        vwap_price = _vwap_price(row)
        vwap_time = _first_present(row, ['vwap_reclaim_trigger_time', 'VWAP Reclaim Trigger Time'])
        if 'trigger_level' in out:
            out.at[idx, 'trigger_level'] = vwap_price
        if 'Trigger Level' in out and vwap_price is not None:
            out.at[idx, 'Trigger Level'] = vwap_price
        if 'trigger_break_time' in out:
            out.at[idx, 'trigger_break_time'] = vwap_time
        if 'Trigger Break Time' in out and vwap_time is not None:
            out.at[idx, 'Trigger Break Time'] = vwap_time
        if 'reference_basis' in out:
            out.at[idx, 'reference_basis'] = 'VWAP Reclaim'
        if 'Reference Basis' in out:
            out.at[idx, 'Reference Basis'] = 'VWAP Reclaim'
    return out
