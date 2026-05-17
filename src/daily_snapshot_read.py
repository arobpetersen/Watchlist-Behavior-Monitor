from __future__ import annotations

from typing import Any

import pandas as pd


def _series(rows: pd.DataFrame, column: str) -> pd.Series:
    if rows is None or rows.empty or column not in rows:
        return pd.Series(dtype=str)
    return rows[column].fillna('').astype(str).str.strip()


def _row_series(rows: pd.DataFrame, column: str) -> pd.Series:
    if rows is None or rows.empty:
        return pd.Series(dtype=str)
    if column not in rows:
        return pd.Series('', index=rows.index, dtype=str)
    return rows[column].fillna('').astype(str).str.strip()


def trigger_other_bucket_counts(rows: pd.DataFrame) -> dict[str, int]:
    """Classify each row into one Trigger Read Other bucket at most."""
    trigger = _row_series(rows, 'Trigger')
    trigger_day = _row_series(rows, 'Trigger Day')
    alt_required = trigger.eq('Alt Required')
    unresolved = ~alt_required & trigger_day.eq('Unresolved')
    no_trigger = ~alt_required & ~unresolved & trigger.eq('No Trigger')
    return {
        'Alt Required': int(alt_required.sum()),
        'Unresolved': int(unresolved.sum()),
        'No Trigger': int(no_trigger.sum()),
    }


def _count_rate(count: int, total: int) -> str:
    pct = 0 if total <= 0 else round((int(count) / int(total)) * 100)
    return f'{int(count)} / {pct}%'


def _numeric_pct(rows: pd.DataFrame, column: str) -> pd.Series:
    if rows is None or rows.empty or column not in rows:
        return pd.Series(dtype=float)
    text = rows[column].fillna('').astype(str).str.replace('%', '', regex=False).str.strip()
    numeric = pd.to_numeric(text, errors='coerce')
    return numeric.where(~text.eq(''), pd.NA) / 100


def _fmt_pct(value: Any) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors='coerce').iloc[0]
    if pd.isna(numeric):
        return '-'
    return f'{float(numeric) * 100:.1f}%'


def daily_snapshot_status_counts(rows: pd.DataFrame) -> dict[str, int | None]:
    total = len(rows) if rows is not None else 0
    status = _series(rows, 'Current Status')
    trigger_day = _series(rows, 'Trigger Day')
    close_be = _series(rows, 'Close < BE')
    retests = _series(rows, 'Retests')
    d0_failed = status.eq('Failed D0') | trigger_day.eq('Fail')
    return {
        'total': total,
        'active': int(status.eq('Active').sum()),
        'failed_d0': int(d0_failed.sum()),
        'failed_after_d0': int(status.str.match(r'^Failed D[1-9]\d*$', na=False).sum()),
        'close_be': int(close_be.str.casefold().eq('yes').sum()) if 'Close < BE' in (rows.columns if rows is not None else []) else None,
        'retested': int(retests.replace('-', '').str.len().gt(0).sum()) if 'Retests' in (rows.columns if rows is not None else []) else 0,
    }


def daily_snapshot_day_read_metrics(rows: pd.DataFrame) -> list[tuple[str, str]]:
    counts = daily_snapshot_status_counts(rows)
    total = int(counts['total'] or 0)
    metrics = [
        ('Setups', str(total)),
        ('Active', _count_rate(int(counts['active'] or 0), total)),
        ('D0 Fail', _count_rate(int(counts['failed_d0'] or 0), total)),
        ('Failed After D0', _count_rate(int(counts['failed_after_d0'] or 0), total)),
    ]
    if counts['close_be'] is not None:
        metrics.append(('Close < BE', _count_rate(int(counts['close_be'] or 0), total)))
    metrics.append(('Retested', _count_rate(int(counts['retested'] or 0), total)))
    d3 = _numeric_pct(rows, 'D3 High %')
    d3 = d3.dropna()
    if not d3.empty:
        metrics.append(('Median D3 High', _fmt_pct(d3.median())))
    return metrics


def _attempt_rate(success: int, failed: int) -> str | None:
    attempts = int(success) + int(failed)
    if attempts <= 0:
        return None
    pct = round((int(success) / attempts) * 100)
    return f'{pct}% ({int(success)}/{attempts} attempts)'


def _trigger_path_group(label: str, success: int, failed: int, secondary: list[str] | None = None) -> tuple[str, str] | None:
    details = []
    rate = _attempt_rate(success, failed)
    if rate:
        details.append(rate)
    details.extend(secondary or [])
    if not details:
        return None
    return label, ' / '.join(details)


def _untriggered_group(other: dict[str, int]) -> tuple[str, str] | None:
    metrics = [
        ('alt required', int(other.get('Alt Required', 0) or 0)),
        ('unresolved', int(other.get('Unresolved', 0) or 0)),
        ('no trigger', int(other.get('No Trigger', 0) or 0)),
    ]
    filtered = [(metric, count) for metric, count in metrics if count != 0]
    if not filtered:
        return None
    return 'Untriggered', ' / '.join(f'{count} {metric}' for metric, count in filtered)


def daily_snapshot_trigger_read_groups(rows: pd.DataFrame) -> list[tuple[str, str]]:
    if rows is None:
        rows = pd.DataFrame()
    trigger = _series(rows, 'Trigger')
    pdh = _series(rows, 'PDH')
    one = _series(rows, '1m ORH')
    vwap = _series(rows, 'VWAP Reclaim')
    five = _series(rows, '5m ORH')
    other = trigger_other_bucket_counts(rows)
    pdh_gap = int(pdh.eq('Gap').sum())

    groups = [
        _trigger_path_group(
            'PDH',
            int(pdh.str.casefold().eq('success').sum()),
            int((pdh.str.casefold().eq('failed') | trigger.eq('Failed PDH Trigger')).sum()),
            [f'{pdh_gap} gap'] if pdh_gap else None,
        ),
        _trigger_path_group(
            'VWAP Reclaim',
            int(vwap.str.casefold().eq('success').sum()),
            int(vwap.str.casefold().eq('failed').sum()),
        ),
        _trigger_path_group(
            '1m ORH',
            int(one.str.casefold().eq('success').sum()),
            int(one.str.casefold().eq('failed').sum()),
        ),
        _trigger_path_group(
            '5m ORH',
            int(five.str.casefold().eq('success').sum()),
            int(five.str.casefold().eq('failed').sum()),
        ),
        _untriggered_group(other),
    ]
    return [group for group in groups if group is not None]
