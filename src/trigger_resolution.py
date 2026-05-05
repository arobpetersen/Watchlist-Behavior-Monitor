from __future__ import annotations

import json
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
    return _text(_first_present(row, ['vwap_reclaim_result', 'Raw VWAP Reclaim Result', 'VWAP Reclaim Result', 'VWAP Reclaim'])).casefold()


def _vwap_price(row: pd.Series) -> float | None:
    return _num(_first_present(row, ['vwap_reclaim_trigger_price', 'Raw VWAP Reclaim Trigger Price', 'VWAP Reclaim Trigger Price']))


def _json_field(value: Any, field: str) -> Any:
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed.get(field)
    return None


def _orh_price(row: pd.Series, minutes: int) -> float | None:
    label = f'{minutes}m ORH'
    value = _first_present(
        row,
        [
            f'{label} Trigger Price',
            f'{label} Price',
            f'{label} Level',
            f'{label}',
            f'or_{minutes}m_orh',
        ],
    )
    if value is not None:
        price = _num(value)
        if price is not None:
            return price
    json_column = f'or_{minutes}m'
    if json_column in row:
        return _num(_json_field(row.get(json_column), 'orh'))
    return None


def _resolved_trigger_price(row: pd.Series) -> float | None:
    return _num(_first_present(row, ['trigger_level', 'Trigger Level']))


def _vwap_stop_valid(row: pd.Series) -> bool:
    value = _first_present(row, ['vwap_reclaim_stop_valid', 'Raw VWAP Reclaim Stop Valid', 'VWAP Reclaim Stop Valid'])
    if value is None or _text(value) == '':
        return True
    if isinstance(value, str):
        return value.strip().casefold() not in {'false', 'no', '0'}
    return bool(value)


def should_promote_vwap_reclaim(row: pd.Series) -> bool:
    return qualified_vwap_trigger_fields(row)['vwap_qualified_trigger_result'] == 'success'


def qualified_vwap_trigger_fields(row: pd.Series) -> dict:
    raw_result = _vwap_result(row)
    vwap_price = _vwap_price(row)
    trigger = _trigger_label(row)
    if raw_result != 'success':
        return {
            'vwap_qualified_trigger_result': '',
            'vwap_qualified_trigger_reason': f'raw VWAP Reclaim is {raw_result or "blank"}',
        }
    if vwap_price is None:
        return {
            'vwap_qualified_trigger_result': '',
            'vwap_qualified_trigger_reason': 'raw VWAP trigger price unavailable',
        }
    if not _vwap_stop_valid(row):
        return {
            'vwap_qualified_trigger_result': '',
            'vwap_qualified_trigger_reason': 'post-VWAP stop/reference low breached',
        }
    if trigger in FALLBACK_TRIGGER_LABELS or trigger == '':
        return {
            'vwap_qualified_trigger_result': 'success',
            'vwap_qualified_trigger_reason': 'VWAP selected over fallback trigger',
        }
    if trigger in ORH_TRIGGER_LABELS:
        existing_price = _resolved_trigger_price(row)
        if existing_price is not None and vwap_price < existing_price:
            return {
                'vwap_qualified_trigger_result': 'success',
                'vwap_qualified_trigger_reason': f'VWAP trigger price lower than {trigger}',
            }
        return {
            'vwap_qualified_trigger_result': '',
            'vwap_qualified_trigger_reason': f'{trigger} trigger price is lower or unavailable',
        }
    if trigger == 'PDH':
        return {
            'vwap_qualified_trigger_result': '',
            'vwap_qualified_trigger_reason': 'PDH trigger preserved',
        }
    return {
        'vwap_qualified_trigger_result': '',
        'vwap_qualified_trigger_reason': f'{trigger or "current"} trigger preserved',
    }


def vwap_superseded_orh_display_values(row: pd.Series, one_min_result: Any, five_min_result: Any) -> tuple[str, str]:
    one = _text(one_min_result)
    five = _text(five_min_result)
    trigger = _trigger_label(row)
    if trigger != 'VWAP Reclaim':
        return one, five
    vwap_price = _vwap_price(row)
    if vwap_price is None:
        return one, five
    one_price = _orh_price(row, 1)
    five_price = _orh_price(row, 5)
    if one == 'success' and one_price is not None and one_price >= vwap_price:
        one = 'superseded'
    if five == 'success' and five_price is not None and five_price >= vwap_price:
        five = 'superseded'
    return one, five


def vwap_orh_suppression_reason(row: pd.Series, one_min_result: Any, five_min_result: Any) -> str:
    one, five = vwap_superseded_orh_display_values(row, one_min_result, five_min_result)
    labels = []
    if one == 'superseded':
        labels.append('1m ORH')
    if five == 'superseded':
        labels.append('5m ORH')
    if not labels:
        return ''
    return f"{', '.join(labels)} hidden because VWAP Reclaim trigger price is lower or equal"


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
    for column in ['vwap_qualified_trigger_result', 'vwap_qualified_trigger_reason']:
        if column not in out:
            out[column] = ''
    if 'VWAP Trigger' in out and 'VWAP Trigger Reason' not in out:
        out['VWAP Trigger Reason'] = ''
    for idx, row in out.iterrows():
        qualified = qualified_vwap_trigger_fields(row)
        for column, value in qualified.items():
            if column in out:
                out.at[idx, column] = value
        if 'VWAP Trigger' in out:
            out.at[idx, 'VWAP Trigger'] = qualified['vwap_qualified_trigger_result']
        if 'VWAP Trigger Reason' in out:
            out.at[idx, 'VWAP Trigger Reason'] = qualified['vwap_qualified_trigger_reason']
        if qualified['vwap_qualified_trigger_result'] != 'success':
            continue
        if 'trigger_type' in out:
            out.at[idx, 'trigger_type'] = 'VWAP Reclaim'
        if 'Trigger' in out:
            out.at[idx, 'Trigger'] = 'VWAP Reclaim'
        vwap_price = _vwap_price(row)
        vwap_time = _first_present(row, ['vwap_reclaim_trigger_time', 'Raw VWAP Reclaim Trigger Time', 'VWAP Reclaim Trigger Time'])
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
