from __future__ import annotations

import json
from html import escape
from time import perf_counter
from typing import Any

import pandas as pd

from src.daily_snapshot_read import trigger_other_bucket_counts
from src.dashboard_queries import _clean_display_df, _close_bucket
from src.feature_engine import session_filter
from src.trigger_resolution import resolve_display_triggers, vwap_orh_suppression_reason, vwap_superseded_orh_display_values
from src.vwap_reclaim import assess_vwap_reclaim


SETUP_OPTIONS = [
    '',
    'EP',
    'High Tight Pivot',
    'High Tight Flag',
    'High Tight Compression',
    'Pullback',
    'Stage 2 Continuation Breakout',
    
]

ENTRY_TACTIC_OPTIONS = ['', 'Bias Flip', 'Gap Over Range', 'Micro Gap', 'OR Range Break', 'Reclaim']
RATING_OPTIONS = ['', '1', '2', '3', '4', '5']

MAIN_COLUMNS = [
    'Ticker',
    'Current Status',
    'Trigger Day',
    'Trigger',
    'PDH',
    '1m ORH',
    'VWAP Reclaim',
    '5m ORH',
    'Notes',
    'Current %',
    'Max %',
    'Close < BE',
    'D3 High %',
    'Retests',
    'Setup',
    'Entry Tactic',
    'Rating',
]

MAIN_COLUMN_LABELS = {
    '1m ORH': '1m ORH',
    '5m ORH': '5m ORH',
    'Current %': 'Current',
    'Max %': 'Max',
    'D3 High %': 'D3 High',
}

DETAIL_COLUMNS = [
    'Ticker',
    'Prior Day High',
    'Setup Day Open',
    'Open Over PDH',
    'PDH Result',
    'PDH Fail Time',
    '1m Recovery Qualified',
    '1m Recovery Break Time',
    '1m Recovery Reference Low',
    '5m Recovery Qualified',
    '5m Recovery Break Time',
    '5m Recovery Reference Low',
    'Alt Recovery Qualified',
    'PDH Trigger Break Time',
    'PDH Trigger Level',
    'PDH Reference Low',
    'PDH Reference Basis',
    'Raw VWAP Reclaim Result',
    'Raw VWAP Reclaim Prior Below VWAP',
    'Raw VWAP Reclaim Time',
    'Raw VWAP Reclaim Bar Open',
    'Raw VWAP Reclaim Bar High',
    'Raw VWAP Reclaim Bar Low',
    'Raw VWAP Reclaim Bar Close',
    'Raw VWAP Reclaim Trigger Time',
    'Raw VWAP Reclaim Trigger Price',
    'Raw VWAP Reclaim Trigger LOD Reference',
    'Raw VWAP Reclaim Reference Basis',
    'Raw VWAP Reclaim Post-Trigger High',
    'Raw VWAP Reclaim Post-Trigger Low',
    'Raw VWAP Reclaim Post-Trigger Stop Breached',
    'Raw VWAP Reclaim Stop Valid',
    'Raw VWAP Reclaim Result Reason',
    'Qualified VWAP Trigger Result',
    'Qualified VWAP Trigger Reason',
    'VWAP Success Failed After D0',
    'ORH Display Suppression',
    '1m ORH Trigger Price',
    '5m ORH Trigger Price',
    'Trigger Level',
    'Reference Low',
    'Reference Basis',
    'Trigger Break Time',
    '1m Low Swept Before Trigger',
    '1m ORH Reference Low',
    '1m ORH Reference Basis',
    '1m Post-Trigger Stop Breach',
    '5m Low Swept Before Trigger',
    '5m ORH Reference Low',
    '5m ORH Reference Basis',
    '5m Post-Trigger Stop Breach',
    'Fail Day',
    'Retests',
    'Retest Count',
    'Retest Days Raw',
    'Retest Dates Raw',
    'Latest Close',
    'Setup Close',
    'Setup High',
    'Setup Low',
    'Current vs Setup Close',
    'Max Gain from Setup Close',
    'RVOL',
    'Range x ATR(14)',
    '1m OR Width / ATR14',
    '5m OR Width / ATR14',
    'Close Bucket',
    '1m OR Result',
    '5m OR Result',
    '5m ORH Break Time',
    '5m ORH Broke After Range',
    '1m Follow-Through / ATR14',
]

ACTIVE_LIFECYCLE_AUDIT_COLUMNS = [
    'Ticker',
    'Setup Date',
    'Trigger',
    'Trigger Level',
    'Reference Low',
    'Breach Date',
    'Breach Day Index',
    'Breach Reason',
]

STATUS_PRIORITY = {
    'Active': 0,
    'Failed D0': 1,
    'Later Failed': 2,
    'Failed': 2,
    'Failed D1': 3,
    'Failed D2': 4,
    'Failed D3': 5,
    '—': 6,
}


def _loads(value: Any) -> dict:
    if not isinstance(value, str) or not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _blank(value: Any) -> str:
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    return str(value)


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _ts(value: Any) -> pd.Timestamp | None:
    if value is None or value == '':
        return None
    out = pd.to_datetime(value, errors='coerce')
    if pd.isna(out):
        return None
    return out


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _change_pct(value: float | None, base: float | None) -> float | None:
    if value is None or base is None:
        return None
    return _pct(float(value) - float(base), base)


def _fmt_pct(value) -> str:
    return '' if value is None or pd.isna(value) else f'{float(value) * 100:.1f}%'


def _fmt_price(value) -> str:
    return '' if value is None or pd.isna(value) else f'{float(value):.2f}'


def _fmt_ratio(value) -> str:
    return '' if value is None or pd.isna(value) else f'{float(value):.2f}'


def _fmt_ts(value) -> str:
    ts = _ts(value)
    return '' if ts is None else ts.strftime('%Y-%m-%d %H:%M')


def _fmt_day(value: int | None) -> str:
    if value is None or pd.isna(value):
        return ''
    return f'Day {int(value)}'


def _fmt_compact_day(value: int | None) -> str:
    if value is None or pd.isna(value):
        return ''
    return f'D{int(value)}'


def _retest_day_values(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        try:
            if pd.isna(value):
                return []
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if not text:
            return []
        values = [part.strip().lstrip('D') for part in text.split(',')]
    days: list[int] = []
    for item in values:
        try:
            if pd.isna(item):
                continue
        except (TypeError, ValueError):
            pass
        text = str(item).strip().lstrip('D')
        if not text:
            continue
        try:
            day = int(float(text))
        except (TypeError, ValueError):
            continue
        if day not in days:
            days.append(day)
    return sorted(days)


def _fmt_retests(value: Any, fallback: Any = None) -> str:
    days = _retest_day_values(value)
    if not days:
        days = _retest_day_values(fallback)
    if not days:
        return ''
    labels = [f'D{day}' for day in days[:3]]
    extra = len(days) - 3
    return f"{', '.join(labels)} +{extra}" if extra > 0 else ', '.join(labels)


def _fmt_retest_count(value: Any, fallback: Any = None) -> str:
    days = _retest_day_values(value)
    if not days:
        days = _retest_day_values(fallback)
    return '' if not days else str(len(days))


def _fmt_retest_days_raw(value: Any, fallback: Any = None) -> str:
    days = _retest_day_values(value)
    if not days:
        days = _retest_day_values(fallback)
    return ', '.join(f'D{day}' for day in days)


def _fmt_retest_dates_raw(value: Any) -> str:
    if value is None:
        return ''
    if not isinstance(value, (list, tuple, set)):
        try:
            if pd.isna(value):
                return ''
        except (TypeError, ValueError):
            pass
        return _blank(value)
    dates = []
    for item in value:
        if item is None:
            continue
        try:
            if pd.isna(item):
                continue
        except (TypeError, ValueError):
            pass
        date_value = pd.to_datetime(item, errors='coerce')
        if not pd.isna(date_value):
            dates.append(date_value.date().isoformat())
    return ', '.join(dates)


def _fmt_d3_pct(value) -> str:
    return '-' if value is None or pd.isna(value) else _fmt_pct(value)


def _fmt_bool_available(value) -> str:
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    return 'Yes' if bool(value) else 'No'


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {'', '-', 'nan', 'none'}:
            return None
        if text in {'yes', 'true', '1'}:
            return True
        if text in {'no', 'false', '0'}:
            return False
    return bool(value)


def _status_priority(value: Any) -> int:
    text = _blank(value).strip()
    if text == 'Active':
        return 0
    if text.startswith('Failed D'):
        day = _status_day(text.removeprefix('Failed D'))
        return 1 + day if day is not None else 50
    if text in {'Failed', 'Later Failed'}:
        return 50
    return 99


def trigger_day_status(trigger_type: str, fail_day_value: int | None) -> str:
    if trigger_type == 'No Trigger':
        return 'Unresolved'
    if fail_day_value == 0:
        return 'Fail'
    return 'Success'


def _status_day(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def current_status_display(
    trigger_day: str,
    fail_day_value: int | None,
    close_below_be: bool | None = None,
    close_below_be_day: int | None = None,
) -> str:
    fail_day_number = _status_day(fail_day_value)
    if trigger_day != 'Success':
        return '\u2014'
    if fail_day_number is not None and fail_day_number > 0:
        return f'Failed D{fail_day_number}'
    close_day_number = _status_day(close_below_be_day)
    if close_below_be and close_day_number is not None and close_day_number > 0:
        return f'Failed D{close_day_number}'
    return 'Active'


def _has_close_location(value: Any, threshold: float) -> bool:
    num = _num(value)
    return num is not None and num >= threshold


def _same_bar_break(data: dict) -> bool:
    if data.get('same_bar_orh_orl_break'):
        return True
    orh_time = _ts(data.get('orh_break_time'))
    orl_time = _ts(data.get('orl_break_time'))
    return orh_time is not None and orl_time is not None and orh_time == orl_time


def _clean_orh(data: dict) -> bool:
    return bool(data.get('broke_orh') and not data.get('orh_then_orl') and not _same_bar_break(data))


def _regular_session_bars(intraday: pd.DataFrame | None) -> pd.DataFrame:
    if intraday is None or intraday.empty:
        return pd.DataFrame()
    bars = intraday.copy()
    bars['timestamp_et'] = pd.to_datetime(bars['timestamp_et'])
    return session_filter(bars).sort_values('timestamp_et')


def reference_low_at_trigger(intraday: pd.DataFrame | None, trigger_break_time) -> float | None:
    bars = _regular_session_bars(intraday)
    break_time = _ts(trigger_break_time)
    if bars.empty or break_time is None:
        return None
    through_trigger = bars[bars['timestamp_et'] <= break_time]
    if through_trigger.empty:
        return None
    return _num(through_trigger['low'].min())


def orh_trigger_assessment(or_json: str, minutes: int, intraday: pd.DataFrame | None, daily: pd.DataFrame | None = None) -> dict:
    data = _loads(or_json)
    trigger_break_time = _ts(data.get('orh_break_time'))
    orl_break_time = _ts(data.get('orl_break_time'))
    trigger_level = _num(data.get('orh'))
    fallback_low = _num(data.get('orl'))
    trigger_low = reference_low_at_trigger(intraday, trigger_break_time)
    reference_low = trigger_low if trigger_low is not None else fallback_low
    bars = _regular_session_bars(intraday)
    if bars.empty and trigger_break_time is None:
        broke_orh = bool(data.get('broke_orh') and not data.get('orh_then_orl') and not _same_bar_break(data))
    else:
        broke_orh = bool(data.get('broke_orh') and trigger_break_time is not None and (not _same_bar_break(data) or not bars.empty))
    low_swept_before_trigger = bool(
        broke_orh
        and orl_break_time is not None
        and trigger_break_time is not None
        and orl_break_time <= trigger_break_time
        and not data.get('orh_then_orl')
    )
    daily_bars = daily if daily is not None else pd.DataFrame()
    trigger_failure_day = fail_day(_regular_session_bars(intraday), daily_bars, trigger_break_time, reference_low) if broke_orh else None
    trigger_day_failed = trigger_failure_day == 0
    failure_day = trigger_failure_day
    failed_after_trigger = trigger_failure_day is not None
    failed = failed_after_trigger
    return {
        'broke_orh': broke_orh,
        'trigger_level': trigger_level,
        'trigger_break_time': trigger_break_time,
        'reference_low': reference_low,
        'reference_basis': f'LOD at {minutes}m Trigger' if trigger_low is not None else f'{minutes}m OR',
        'low_swept_before_trigger': low_swept_before_trigger,
        'pretrigger_orl_flush': low_swept_before_trigger,
        'first_break_failed': False,
        'failed_after_trigger': failed_after_trigger,
        'post_trigger_stop_breached': failed_after_trigger,
        'trigger_day_failed': trigger_day_failed,
        'failed': failed,
        'failure_day': failure_day,
    }


def orh_framework_failed(or_json: str, assessment: dict) -> bool:
    data = _loads(or_json)
    if assessment.get('broke_orh'):
        return bool(assessment.get('failed'))
    return bool(data.get('broke_orh') and (data.get('orh_then_orl') or _same_bar_break(data)))


def alt_required_qualified(or_1m: str, or_5m: str, or_15m: str, close_location, intraday: pd.DataFrame | None = None, daily: pd.DataFrame | None = None) -> bool:
    one_assessment = orh_trigger_assessment(or_1m, 1, intraday, daily)
    five_assessment = orh_trigger_assessment(or_5m, 5, intraday, daily)
    fifteen = _loads(or_15m)
    fifteen_fail = fail_day(_regular_session_bars(intraday), daily if daily is not None else pd.DataFrame(), _ts(fifteen.get('orh_break_time')), _num(fifteen.get('orl')))
    return bool(
        orh_framework_failed(or_1m, one_assessment)
        and orh_framework_failed(or_5m, five_assessment)
        and fifteen.get('broke_orh')
        and _has_close_location(close_location, 0.80)
        and fifteen_fail != 0
    )


def failed_or_trigger_reference(one_assessment: dict, five_assessment: dict) -> dict:
    failed = []
    for label, assessment in [('1m ORH', one_assessment), ('5m ORH', five_assessment)]:
        if assessment.get('broke_orh') and assessment.get('failed'):
            failed.append((assessment.get('failure_day'), label, assessment))
    if not failed:
        return {}
    failed.sort(key=lambda item: (99 if item[0] is None else item[0], 0 if item[1] == '1m ORH' else 1))
    failure_day, label, assessment = failed[0]
    return {
        'trigger_type': 'Failed OR Trigger',
        'trigger_level': assessment.get('trigger_level'),
        'reference_low': assessment.get('reference_low'),
        'reference_basis': f"Failed {assessment.get('reference_basis')}",
        'trigger_break_time': assessment.get('trigger_break_time'),
        'framework_fail_day': failure_day,
        'failed_framework': label,
    }


def day0_fail_time(intraday: pd.DataFrame, trigger_break_time, reference_low: float | None) -> pd.Timestamp | None:
    break_time = _ts(trigger_break_time)
    if intraday.empty or break_time is None or reference_low is None:
        return None
    post_trigger = intraday[intraday['timestamp_et'] > break_time]
    failures = post_trigger[post_trigger['low'] < float(reference_low)]
    if failures.empty:
        return None
    return _ts(failures.iloc[0]['timestamp_et'])


def _vwap_reclaim_fields(intraday: pd.DataFrame | None, reference_low: float | None = None, setup_date=None) -> dict:
    assessment = assess_vwap_reclaim(intraday, setup_date=setup_date)
    trigger_time = _ts(assessment.get('trigger_time'))
    stop_valid = None if assessment.get('post_trigger_stop_breached') is None else not bool(assessment.get('post_trigger_stop_breached'))
    return {
        'vwap_reclaim_result': assessment.get('result') or '',
        'vwap_reclaim_time': _ts(assessment.get('reclaim_time')),
        'vwap_reclaim_reclaim_bar_open': assessment.get('reclaim_bar_open'),
        'vwap_reclaim_reclaim_bar_high': assessment.get('reclaim_bar_high'),
        'vwap_reclaim_reclaim_bar_low': assessment.get('reclaim_bar_low'),
        'vwap_reclaim_reclaim_bar_close': assessment.get('reclaim_bar_close'),
        'vwap_reclaim_trigger_time': trigger_time,
        'vwap_reclaim_trigger_price': assessment.get('trigger_price'),
        'vwap_reclaim_trigger_lod_reference': assessment.get('vwap_trigger_lod_reference'),
        'vwap_reclaim_reference_basis': assessment.get('vwap_reference_basis') or '',
        'vwap_reclaim_post_trigger_high': assessment.get('post_trigger_high'),
        'vwap_reclaim_post_trigger_low': assessment.get('post_trigger_low'),
        'vwap_reclaim_post_trigger_stop_breached': assessment.get('post_trigger_stop_breached'),
        'vwap_reclaim_stop_valid': stop_valid,
        'vwap_reclaim_prior_below_vwap_observed': assessment.get('prior_below_vwap_observed'),
        'vwap_reclaim_failure_reason': assessment.get('failure_reason') or '',
        'vwap_reclaim_result_reason': assessment.get('result_reason') or '',
    }


def pdh_trigger_assessment(
    prior_day_high,
    setup_day_open=None,
    intraday: pd.DataFrame | None = None,
    daily: pd.DataFrame | None = None,
) -> dict:
    pdh = _num(prior_day_high)
    bars = _regular_session_bars(intraday)
    setup_open = _num(setup_day_open)
    if setup_open is None and not bars.empty:
        setup_open = _num(bars.iloc[0].get('open'))
    if pdh is None or setup_open is None:
        return {
            'pdh_result': '-',
            'prior_day_high': pdh,
            'setup_day_open': setup_open,
            'open_over_pdh': None,
            'broke_pdh': False,
            'trigger_level': pdh,
            'trigger_break_time': None,
            'reference_low': None,
            'reference_basis': '',
            'failure_day': None,
        }
    open_over_pdh = setup_open > pdh
    if open_over_pdh:
        return {
            'pdh_result': 'Gap',
            'prior_day_high': pdh,
            'setup_day_open': setup_open,
            'open_over_pdh': True,
            'broke_pdh': False,
            'trigger_level': pdh,
            'trigger_break_time': None,
            'reference_low': None,
            'reference_basis': '',
            'failure_day': None,
        }
    breaks = bars[bars['high'] > pdh] if not bars.empty else pd.DataFrame()
    if breaks.empty:
        return {
            'pdh_result': '-',
            'prior_day_high': pdh,
            'setup_day_open': setup_open,
            'open_over_pdh': False,
            'broke_pdh': False,
            'trigger_level': pdh,
            'trigger_break_time': None,
            'reference_low': None,
            'reference_basis': '',
            'failure_day': None,
        }
    trigger_break_time = breaks.iloc[0]['timestamp_et']
    through_trigger = bars[bars['timestamp_et'] <= trigger_break_time]
    reference_low = _num(through_trigger['low'].min()) if not through_trigger.empty else None
    failure_day = fail_day(bars, daily if daily is not None else pd.DataFrame(), trigger_break_time, reference_low)
    return {
        'pdh_result': 'failed' if failure_day == 0 else 'success',
        'prior_day_high': pdh,
        'setup_day_open': setup_open,
        'open_over_pdh': False,
        'broke_pdh': True,
        'trigger_level': pdh,
        'trigger_break_time': trigger_break_time,
        'reference_low': reference_low,
        'reference_basis': 'LOD at PDH Trigger',
        'failure_day': failure_day,
        'fail_time': day0_fail_time(bars, trigger_break_time, reference_low) if failure_day == 0 else None,
    }


def _recovery_assessment(
    label: str,
    level,
    pdh,
    pdh_fail_time,
    intraday: pd.DataFrame | None,
    daily: pd.DataFrame | None,
    reference_low_override=None,
    reference_basis: str | None = None,
    close_location=None,
) -> dict:
    trigger_level = _num(level)
    prior_high = _num(pdh)
    fail_time = _ts(pdh_fail_time)
    bars = _regular_session_bars(intraday)
    if trigger_level is None or prior_high is None or fail_time is None or bars.empty:
        return {'qualified': False, 'break_time': None, 'reference_low': None}
    if trigger_level <= prior_high:
        return {'qualified': False, 'break_time': None, 'reference_low': None}
    if label == 'Alt Required' and not _has_close_location(close_location, 0.80):
        return {'qualified': False, 'break_time': None, 'reference_low': None}

    breaks = bars[bars['high'] > trigger_level]
    if breaks.empty:
        return {'qualified': False, 'break_time': None, 'reference_low': None}
    first_break = _ts(breaks.iloc[0]['timestamp_et'])
    if first_break is None or first_break <= fail_time:
        return {'qualified': False, 'break_time': None, 'reference_low': None}

    through_trigger = bars[bars['timestamp_et'] <= first_break]
    reference_low = _num(reference_low_override)
    if reference_low is None:
        reference_low = _num(through_trigger['low'].min()) if not through_trigger.empty else None
    if reference_low is None:
        return {'qualified': False, 'break_time': first_break, 'reference_low': None}

    if day0_fail(bars, first_break, reference_low):
        return {'qualified': False, 'break_time': first_break, 'reference_low': reference_low}

    return {
        'qualified': True,
        'break_time': first_break,
        'reference_low': reference_low,
        'reference_basis': reference_basis or f'LOD at {label} Recovery Trigger',
    }


def _pdh_recovery_details(one: dict, five: dict, alt: dict, pdh_fail_time) -> dict:
    return {
        'pdh_fail_time': pdh_fail_time,
        'one_recovery_qualified': bool(one.get('qualified')),
        'one_recovery_break_time': one.get('break_time'),
        'one_recovery_reference_low': one.get('reference_low'),
        'five_recovery_qualified': bool(five.get('qualified')),
        'five_recovery_break_time': five.get('break_time'),
        'five_recovery_reference_low': five.get('reference_low'),
        'alt_recovery_qualified': bool(alt.get('qualified')),
    }


def derive_trigger_reference(
    or_1m: str,
    or_5m: str,
    or_15m: str,
    close_location,
    intraday: pd.DataFrame | None = None,
    daily: pd.DataFrame | None = None,
    prior_day_high=None,
    setup_day_open=None,
) -> dict:
    fifteen = _loads(or_15m)
    one_assessment = orh_trigger_assessment(or_1m, 1, intraday, daily)
    five_assessment = orh_trigger_assessment(or_5m, 5, intraday, daily)
    pdh_assessment = pdh_trigger_assessment(prior_day_high, setup_day_open, intraday, daily)

    pdh_governed = pdh_assessment['open_over_pdh'] is False

    if pdh_governed and pdh_assessment['broke_pdh']:
        if pdh_assessment['failure_day'] == 0:
            pdh_fail_time = pdh_assessment.get('fail_time')
            one_recovery = _recovery_assessment(
                '1m',
                _loads(or_1m).get('orh'),
                prior_day_high,
                pdh_fail_time,
                intraday,
                daily,
                reference_basis='LOD at 1m Recovery Trigger',
            )
            five_recovery = _recovery_assessment(
                '5m',
                _loads(or_5m).get('orh'),
                prior_day_high,
                pdh_fail_time,
                intraday,
                daily,
                reference_basis='LOD at 5m Recovery Trigger',
            )
            alt_recovery = _recovery_assessment(
                'Alt Required',
                fifteen.get('orh'),
                prior_day_high,
                pdh_fail_time,
                intraday,
                daily,
                reference_low_override=fifteen.get('orl'),
                reference_basis='15m OR Reference',
                close_location=close_location,
            )
            recovery_details = _pdh_recovery_details(one_recovery, five_recovery, alt_recovery, pdh_fail_time)
            base_details = {
                'pdh_result': pdh_assessment['pdh_result'],
                'pdh_trigger_break_time': pdh_assessment['trigger_break_time'],
                'pdh_trigger_level': pdh_assessment['trigger_level'],
                'pdh_reference_low': pdh_assessment['reference_low'],
                'pdh_reference_basis': pdh_assessment['reference_basis'],
                'pdh_governed': True,
                **recovery_details,
            }
            if one_recovery.get('qualified'):
                return {
                    'trigger_type': '1m ORH',
                    'trigger_level': _num(_loads(or_1m).get('orh')),
                    'reference_low': one_recovery.get('reference_low'),
                    'reference_basis': one_recovery.get('reference_basis'),
                    'trigger_break_time': one_recovery.get('break_time'),
                    'pdh_recovery_trigger': '1m ORH',
                    **base_details,
                }
            if five_recovery.get('qualified'):
                return {
                    'trigger_type': '5m ORH',
                    'trigger_level': _num(_loads(or_5m).get('orh')),
                    'reference_low': five_recovery.get('reference_low'),
                    'reference_basis': five_recovery.get('reference_basis'),
                    'trigger_break_time': five_recovery.get('break_time'),
                    'pdh_recovery_trigger': '5m ORH',
                    **base_details,
                }
            if alt_recovery.get('qualified'):
                return {
                    'trigger_type': 'Alt Required',
                    'trigger_level': _num(fifteen.get('orh')),
                    'reference_low': alt_recovery.get('reference_low'),
                    'reference_basis': alt_recovery.get('reference_basis'),
                    'trigger_break_time': alt_recovery.get('break_time'),
                    'pdh_recovery_trigger': 'Alt Required',
                    **base_details,
                }
            return {
                'trigger_type': 'Failed PDH Trigger',
                'trigger_level': pdh_assessment['trigger_level'],
                'reference_low': pdh_assessment['reference_low'],
                'reference_basis': pdh_assessment['reference_basis'],
                'trigger_break_time': pdh_assessment['trigger_break_time'],
                'framework_fail_day': 0,
                'failed_framework': 'PDH',
                'pdh_result': pdh_assessment['pdh_result'],
                'pdh_trigger_break_time': pdh_assessment['trigger_break_time'],
                'pdh_trigger_level': pdh_assessment['trigger_level'],
                'pdh_reference_low': pdh_assessment['reference_low'],
                'pdh_reference_basis': pdh_assessment['reference_basis'],
                'pdh_governed': True,
                **recovery_details,
            }
        return {
            'trigger_type': 'PDH',
            'trigger_level': pdh_assessment['trigger_level'],
            'reference_low': pdh_assessment['reference_low'],
            'reference_basis': pdh_assessment['reference_basis'],
            'trigger_break_time': pdh_assessment['trigger_break_time'],
            'pdh_result': pdh_assessment['pdh_result'],
            'pdh_trigger_break_time': pdh_assessment['trigger_break_time'],
            'pdh_trigger_level': pdh_assessment['trigger_level'],
            'pdh_reference_low': pdh_assessment['reference_low'],
            'pdh_reference_basis': pdh_assessment['reference_basis'],
            'pdh_governed': True,
        }

    if pdh_governed:
        return {
            'trigger_type': 'No Trigger',
            'trigger_level': None,
            'reference_low': None,
            'reference_basis': 'PDH not triggered',
            'trigger_break_time': None,
            'framework_fail_day': None,
            'failed_framework': None,
            'pdh_result': pdh_assessment['pdh_result'],
            'pdh_trigger_break_time': None,
            'pdh_trigger_level': None,
            'pdh_reference_low': None,
            'pdh_reference_basis': '',
            'pdh_governed': True,
        }

    pdh_details = {
        'pdh_result': pdh_assessment['pdh_result'],
        'pdh_trigger_break_time': pdh_assessment['trigger_break_time'],
        'pdh_trigger_level': pdh_assessment['trigger_level'] if pdh_assessment['broke_pdh'] else None,
        'pdh_reference_low': pdh_assessment['reference_low'],
        'pdh_reference_basis': pdh_assessment['reference_basis'],
        'pdh_governed': False,
    }

    if one_assessment['broke_orh'] and not one_assessment['failed']:
        return {
            'trigger_type': '1m ORH',
            'trigger_level': one_assessment['trigger_level'],
            'reference_low': one_assessment['reference_low'],
            'reference_basis': one_assessment['reference_basis'],
            'trigger_break_time': one_assessment['trigger_break_time'],
            **pdh_details,
        }

    if five_assessment['broke_orh'] and not five_assessment['failed']:
        return {
            'trigger_type': '5m ORH',
            'trigger_level': five_assessment['trigger_level'],
            'reference_low': five_assessment['reference_low'],
            'reference_basis': five_assessment['reference_basis'],
            'trigger_break_time': five_assessment['trigger_break_time'],
            **pdh_details,
        }

    if alt_required_qualified(or_1m, or_5m, or_15m, close_location, intraday, daily):
        return {
            'trigger_type': 'Alt Required',
            'trigger_level': _num(fifteen.get('orh')),
            'reference_low': _num(fifteen.get('orl')),
            'reference_basis': '15m OR Reference',
            'trigger_break_time': _ts(fifteen.get('orh_break_time')),
            **pdh_details,
        }

    failed_reference = failed_or_trigger_reference(one_assessment, five_assessment)
    if failed_reference:
        failed_reference.update(pdh_details)
        return failed_reference

    return {
        'trigger_type': 'No Trigger',
        'trigger_level': None,
        'reference_low': None,
        'reference_basis': 'Setup-Day Close fallback',
        'trigger_break_time': None,
        'framework_fail_day': None,
        'failed_framework': None,
        **pdh_details,
    }


def _or_width_vs_atr(or_data: dict, atr14) -> float | None:
    atr = _num(atr14)
    orh = _num(or_data.get('orh'))
    orl = _num(or_data.get('orl'))
    if atr in (None, 0) or orh is None or orl is None:
        return None
    return (orh - orl) / atr


def opening_range_width_notes(or_1m: str, or_5m: str, atr14) -> dict:
    one_ratio = _or_width_vs_atr(_loads(or_1m), atr14)
    five_ratio = _or_width_vs_atr(_loads(or_5m), atr14)
    notes = []
    if one_ratio is not None and one_ratio >= 0.75:
        notes.append('Wide 1m OR')
    if five_ratio is not None and five_ratio >= 0.75:
        notes.append('Wide 5m OR')
    return {
        'one_min_or_width_vs_atr14': one_ratio,
        'five_min_or_width_vs_atr14': five_ratio,
        'notes': '; '.join(notes),
    }


def one_min_follow_through_atr(or_1m: str, atr14, intraday: pd.DataFrame | None = None) -> float | None:
    data = _loads(or_1m)
    trigger_level = _num(data.get('orh'))
    trigger_time = _ts(data.get('orh_break_time'))
    atr = _num(atr14)
    bars = _regular_session_bars(intraday)
    if trigger_level is None or trigger_time is None or atr in (None, 0) or bars.empty:
        return None
    after_trigger = bars[bars['timestamp_et'] >= trigger_time]
    if after_trigger.empty:
        return None
    max_high = _num(after_trigger['high'].max())
    if max_high is None:
        return None
    return (max_high - trigger_level) / atr


def apply_one_min_quality_notes(record: dict, intraday: pd.DataFrame | None = None) -> dict:
    notes = [note for note in _blank(record.get('notes')).split('; ') if note]
    follow_through = None
    if record.get('trigger_type') == '1m ORH':
        five = _loads(record.get('or_5m'))
        if not five.get('broke_orh'):
            notes.append('No 5m Confirm')
        follow_through = one_min_follow_through_atr(record.get('or_1m'), record.get('atr20'), intraday)
        if follow_through is not None and follow_through < 0.25:
            notes.append('Weak 1m Follow-Through')
    return {
        'notes': '; '.join(dict.fromkeys(notes)),
        'one_min_follow_through_atr': follow_through,
    }


ACTIONABLE_TRIGGERS = {'VWAP Reclaim', '1m ORH', '5m ORH', 'PDH', 'Alt Required'}


def weak_close_assessment(record: dict) -> dict:
    trigger_type = _blank(record.get('trigger_type'))
    if trigger_type not in ACTIONABLE_TRIGGERS:
        return {'close_below_be': None, 'close_below_be_day': None}
    if trigger_day_status(trigger_type, record.get('fail_day')) != 'Success':
        return {'close_below_be': None, 'close_below_be_day': None}

    close = _num(record.get('latest_close'))
    if close is None:
        close = _num(record.get('close_price'))
    breakeven = _num(record.get('trigger_level'))
    if breakeven is None:
        breakeven = _num(record.get('base_price'))
    for key in ['reference_price', 'entry_price', 'setup_price']:
        if breakeven is None:
            breakeven = _num(record.get(key))

    below_breakeven = close is not None and breakeven is not None and close < breakeven
    close_below_be_day = _status_day(record.get('latest_day')) if below_breakeven else None
    if close_below_be_day is None and below_breakeven:
        close_below_be_day = 0
    if close is None or breakeven is None:
        current_pct = _num(record.get('current_pct'))
        if current_pct is None:
            return {'close_below_be': None, 'close_below_be_day': None}
        below_breakeven = current_pct < 0
        close_below_be_day = _status_day(record.get('latest_day')) if below_breakeven else None
    return {'close_below_be': bool(below_breakeven), 'close_below_be_day': close_below_be_day}


def apply_weak_close_note(record: dict) -> dict:
    assessment = weak_close_assessment(record)
    return {
        'notes': _blank(record.get('notes')),
        'close_below_be': assessment['close_below_be'],
        'close_below_be_day': assessment['close_below_be_day'],
    }


def opening_range_result(or_json: str, minutes: int, trigger_type: str, intraday: pd.DataFrame | None = None, daily: pd.DataFrame | None = None) -> str:
    data = _loads(or_json)
    if trigger_type == 'Alt Required' and minutes in {1, 5}:
        return 'failed'
    clean_type = f'{minutes}m ORH'
    assessment = orh_trigger_assessment(or_json, minutes, intraday, daily)
    if assessment['broke_orh'] and not assessment['failed']:
        return 'success'
    if assessment['broke_orh'] or (data.get('broke_orh') and (data.get('orh_then_orl') or _same_bar_break(data))):
        return 'failed'
    return ''


def _bars_for_ticker_date(intraday_bars: pd.DataFrame, ticker: str, setup_date) -> pd.DataFrame:
    if intraday_bars.empty:
        return pd.DataFrame()
    bars = intraday_bars[
        (intraday_bars['ticker'] == ticker)
        & (pd.to_datetime(intraday_bars['trading_date']).dt.date == setup_date)
    ].copy()
    if bars.empty:
        return bars
    bars['timestamp_et'] = pd.to_datetime(bars['timestamp_et'])
    return _regular_session_bars(bars)


def _daily_for_ticker(daily_bars: pd.DataFrame, ticker: str, setup_date) -> pd.DataFrame:
    if daily_bars.empty:
        return pd.DataFrame()
    bars = daily_bars[daily_bars['ticker'] == ticker].copy()
    if bars.empty:
        return bars
    bars['trading_date'] = pd.to_datetime(bars['trading_date']).dt.date
    return bars[bars['trading_date'] >= setup_date].sort_values('trading_date')


def daily_follow_through_returns(
    ticker: str,
    setup_date,
    base_price: float | None,
    setup_close: float | None,
    daily_bars: pd.DataFrame,
) -> dict:
    """Calculate current/max returns from all available daily bars for a setup."""
    daily = _daily_for_ticker(daily_bars, ticker, pd.to_datetime(setup_date).date())
    if daily.empty:
        return {
            'latest_trading_date': None,
            'latest_day': None,
            'latest_close': None,
            'current_pct': None,
            'max_pct': None,
            'max_high': None,
            'max_high_date': None,
            'd3_high_pct': None,
            'current_pct_from_setup_close': None,
            'max_gain_from_setup_close': None,
        }

    latest = daily.iloc[-1]
    latest_close = _num(latest.get('close'))
    max_high = _num(daily['high'].max())
    max_high_date = None
    if max_high is not None:
        max_idx = pd.to_numeric(daily['high'], errors='coerce').idxmax()
        max_high_date = daily.loc[max_idx, 'trading_date']
    d3 = daily.iloc[:4]
    d3_high = _num(d3['high'].max()) if len(d3) >= 4 else None
    return {
        'latest_trading_date': latest['trading_date'],
        'latest_day': len(daily) - 1,
        'latest_close': latest_close,
        'current_pct': _change_pct(latest_close, base_price),
        'max_pct': _change_pct(max_high, base_price),
        'max_high': max_high,
        'max_high_date': max_high_date,
        'd3_high_pct': _change_pct(d3_high, base_price),
        'current_pct_from_setup_close': _change_pct(latest_close, setup_close),
        'max_gain_from_setup_close': _change_pct(max_high, setup_close),
    }


def _prior_day_high_for_ticker(daily_bars: pd.DataFrame, ticker: str, setup_date) -> float | None:
    if daily_bars.empty:
        return None
    bars = daily_bars[daily_bars['ticker'] == ticker].copy()
    if bars.empty:
        return None
    bars['trading_date'] = pd.to_datetime(bars['trading_date']).dt.date
    prior = bars[bars['trading_date'] < setup_date].sort_values('trading_date')
    if prior.empty:
        return None
    return _num(prior.iloc[-1].get('high'))


def day0_fail(intraday: pd.DataFrame, trigger_break_time, reference_low: float | None) -> bool:
    break_time = _ts(trigger_break_time)
    if intraday.empty or break_time is None or reference_low is None:
        return False
    post_trigger = intraday[intraday['timestamp_et'] > break_time]
    return bool(not post_trigger.empty and (post_trigger['low'] < float(reference_low)).any())


def day0_retest(intraday: pd.DataFrame, trigger_break_time, trigger_level: float | None) -> bool:
    break_time = _ts(trigger_break_time)
    if intraday.empty or break_time is None or trigger_level is None:
        return False
    post_trigger = intraday[intraday['timestamp_et'] > break_time]
    return bool(not post_trigger.empty and (post_trigger['low'] <= float(trigger_level)).any())


def fail_day(intraday: pd.DataFrame, daily: pd.DataFrame, trigger_break_time, reference_low: float | None) -> int | None:
    if reference_low is None:
        return None
    if day0_fail(intraday, trigger_break_time, reference_low):
        return 0
    after_setup = daily.iloc[1:4] if not daily.empty else pd.DataFrame()
    for day_number, (_, row) in enumerate(after_setup.iterrows(), start=1):
        if _num(row.get('low')) is not None and float(row['low']) < float(reference_low):
            return day_number
    return None


def later_lifecycle_failure_day(
    daily: pd.DataFrame,
    reference_low: float | None,
    breakeven_price: float | None = None,
) -> int | None:
    if daily.empty:
        return None
    after_setup = daily.iloc[1:]
    for day_number, (_, row) in enumerate(after_setup.iterrows(), start=1):
        low = _num(row.get('low'))
        close = _num(row.get('close'))
        if reference_low is not None and low is not None and float(low) < float(reference_low):
            return day_number
        if breakeven_price is not None and close is not None and float(close) < float(breakeven_price):
            return day_number
    return None


def lifecycle_fail_day(
    intraday: pd.DataFrame,
    daily: pd.DataFrame,
    trigger_break_time,
    reference_low: float | None,
    breakeven_price: float | None = None,
) -> int | None:
    if reference_low is not None and day0_fail(intraday, trigger_break_time, reference_low):
        return 0
    return later_lifecycle_failure_day(daily, reference_low, breakeven_price)


def _row_value(row: pd.Series, names: list[str]) -> Any:
    for name in names:
        if name in row:
            return row.get(name)
    return None


def _empty_active_lifecycle_audit() -> pd.DataFrame:
    return pd.DataFrame(columns=ACTIVE_LIFECYCLE_AUDIT_COLUMNS)


def audit_active_lifecycle_violations(rows: pd.DataFrame, daily_bars: pd.DataFrame) -> pd.DataFrame:
    """Return active rows that already violate the canonical later-failure rule."""
    if rows is None or rows.empty or daily_bars is None or daily_bars.empty:
        return _empty_active_lifecycle_audit()

    if 'Current Status' in rows:
        status = rows['Current Status']
    elif 'current_status' in rows:
        status = rows['current_status']
    else:
        return _empty_active_lifecycle_audit()
    active = rows[status.fillna('').astype(str).str.strip().eq('Active')].copy()
    if active.empty:
        return _empty_active_lifecycle_audit()

    bars = daily_bars.copy()
    if 'ticker' not in bars or 'trading_date' not in bars:
        return _empty_active_lifecycle_audit()
    bars['ticker'] = bars['ticker'].astype(str)
    bars['trading_date'] = pd.to_datetime(bars['trading_date'], errors='coerce')
    bars = bars.dropna(subset=['trading_date']).sort_values(['ticker', 'trading_date'])

    out = []
    for _, row in active.iterrows():
        ticker = _blank(_row_value(row, ['Ticker', 'ticker']))
        setup_date_value = _row_value(row, ['Setup Date', 'watchlist_date', 'setup_date'])
        setup_date = pd.to_datetime(setup_date_value, errors='coerce')
        trigger = _blank(_row_value(row, ['Trigger', 'trigger_type']))
        trigger_level = _num(_row_value(row, ['Trigger Level', 'trigger_level', 'Entry Ref', 'base_price']))
        reference_low = _num(_row_value(row, ['Reference Low', 'reference_low']))
        if not ticker or pd.isna(setup_date):
            continue
        daily = bars[(bars['ticker'].eq(ticker)) & (bars['trading_date'].dt.date >= setup_date.date())].copy()
        if daily.empty:
            continue
        for day_number, (_, daily_row) in enumerate(daily.iloc[1:].iterrows(), start=1):
            low = _num(daily_row.get('low'))
            close = _num(daily_row.get('close'))
            reason = ''
            if reference_low is not None and low is not None and float(low) < float(reference_low):
                reason = 'low below reference low'
            elif trigger_level is not None and close is not None and float(close) < float(trigger_level):
                reason = 'close below breakeven'
            if not reason:
                continue
            breach_date = pd.to_datetime(daily_row.get('trading_date'), errors='coerce')
            out.append({
                'Ticker': ticker,
                'Setup Date': setup_date.date().isoformat(),
                'Trigger': trigger,
                'Trigger Level': '' if trigger_level is None else f'{trigger_level:.2f}',
                'Reference Low': '' if reference_low is None else f'{reference_low:.2f}',
                'Breach Date': '' if pd.isna(breach_date) else breach_date.date().isoformat(),
                'Breach Day Index': day_number,
                'Breach Reason': reason,
            })
            break

    if not out:
        return _empty_active_lifecycle_audit()
    return pd.DataFrame(out, columns=ACTIVE_LIFECYCLE_AUDIT_COLUMNS)


def retest_day(intraday: pd.DataFrame, daily: pd.DataFrame, trigger_break_time, trigger_level: float | None) -> int | None:
    days, _ = retest_events(intraday, daily, trigger_break_time, trigger_level)
    return days[0] if days else None


def retest_events(
    intraday: pd.DataFrame,
    daily: pd.DataFrame,
    trigger_break_time,
    trigger_level: float | None,
    fail_day_value: int | None = None,
    latest_trading_date=None,
) -> tuple[list[int], list[str]]:
    if trigger_level is None:
        return [], []

    max_day = None
    if fail_day_value is not None:
        try:
            if not pd.isna(fail_day_value):
                max_day = int(float(fail_day_value))
        except (TypeError, ValueError):
            max_day = None

    days: list[int] = []
    dates: list[str] = []
    setup_date = None
    if not daily.empty and 'trading_date' in daily:
        setup_date = pd.to_datetime(daily.iloc[0].get('trading_date'), errors='coerce')
        setup_date = None if pd.isna(setup_date) else setup_date.date().isoformat()
    if setup_date is None:
        break_time = _ts(trigger_break_time)
        setup_date = '' if break_time is None else break_time.date().isoformat()

    if max_day is None or max_day >= 0:
        if day0_retest(intraday, trigger_break_time, trigger_level):
            days.append(0)
            dates.append(setup_date)

    if daily.empty:
        return days, dates

    bars = daily.copy()
    if latest_trading_date is not None and 'trading_date' in bars:
        latest_date = pd.to_datetime(latest_trading_date, errors='coerce')
        if not pd.isna(latest_date):
            bars = bars[pd.to_datetime(bars['trading_date'], errors='coerce') <= latest_date]

    after_setup = bars.iloc[1:]
    for day_number, (_, row) in enumerate(after_setup.iterrows(), start=1):
        if max_day is not None and day_number > max_day:
            break
        if _num(row.get('low')) is not None and float(row['low']) <= float(trigger_level):
            if day_number not in days:
                days.append(day_number)
                date_value = pd.to_datetime(row.get('trading_date'), errors='coerce')
                dates.append('' if pd.isna(date_value) else date_value.date().isoformat())
    return days, dates


def status_for(trigger_type: str, fail_day_value: int | None) -> str:
    if trigger_type in {'Failed OR Trigger', 'Failed PDH Trigger'}:
        return 'Failed'
    if fail_day_value is not None:
        return 'Failed'
    if trigger_type in {'PDH', '1m ORH', '5m ORH', 'VWAP Reclaim', 'Alt Required'}:
        return 'Active'
    return 'Unresolved'


def _follow_through(row: dict, daily_bars: pd.DataFrame, intraday_bars: pd.DataFrame) -> dict:
    setup_date = pd.to_datetime(row['watchlist_date']).date()
    daily = _daily_for_ticker(daily_bars, row['ticker'], setup_date)
    intraday = _bars_for_ticker_date(intraday_bars, row['ticker'], setup_date)
    trigger_level = row.get('trigger_level')
    reference_low = row.get('reference_low')
    setup_close = _num(row.get('close_price'))
    base_price = trigger_level if trigger_level is not None else setup_close
    preset_fail_day = row.get('framework_fail_day')
    current_fail_day = (
        preset_fail_day
        if row.get('trigger_type') in {'Failed OR Trigger', 'Failed PDH Trigger'}
        else lifecycle_fail_day(intraday, daily, row.get('trigger_break_time'), reference_low, base_price)
    )
    current_retest_days, current_retest_dates = retest_events(
        intraday,
        daily,
        row.get('trigger_break_time'),
        trigger_level,
        current_fail_day,
    )

    if daily.empty:
        return {
            'latest_trading_date': None,
            'latest_day': None,
            'latest_close': None,
            'current_pct': None,
            'max_pct': None,
            'd3_high_pct': None,
            'current_pct_from_setup_close': None,
            'max_gain_from_setup_close': None,
            'fail_day': current_fail_day,
            'retest_day': current_retest_days[0] if current_retest_days else None,
            'retest_days': current_retest_days,
            'retest_dates': current_retest_dates,
            'base_price': base_price,
        }

    returns = daily_follow_through_returns(row['ticker'], setup_date, base_price, setup_close, daily_bars)
    current_retest_days, current_retest_dates = retest_events(
        intraday,
        daily,
        row.get('trigger_break_time'),
        trigger_level,
        current_fail_day,
        returns.get('latest_trading_date'),
    )

    return {
        **returns,
        'fail_day': current_fail_day,
        'retest_day': current_retest_days[0] if current_retest_days else None,
        'retest_days': current_retest_days,
        'retest_dates': current_retest_dates,
        'base_price': base_price,
    }


def sort_monitor_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    table = df.copy()
    status_column = 'Current Status' if 'Current Status' in table else 'Status'
    table['_status_priority'] = table[status_column].apply(_status_priority)
    table['_current_sort'] = table['current_pct_raw'].fillna(float('-inf'))
    return table.sort_values(
        ['_status_priority', '_current_sort', 'Ticker'],
        ascending=[True, False, True],
    ).drop(columns=['_status_priority', '_current_sort'])


def main_table(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return pd.DataFrame(columns=MAIN_COLUMNS)
    out = sort_monitor_rows(table).copy()
    for column in MAIN_COLUMNS:
        if column not in out:
            out[column] = ''
    display = out[MAIN_COLUMNS].replace('superseded', '-')
    return _clean_display_df(display)


def _badge_class(column: str, value: str) -> str:
    normalized = value.lower().replace(' ', '-').replace('/', '-')
    if column == 'Current Status':
        if value == '—':
            return 'monitor-badge status-muted'
        return f'monitor-badge current-status-{normalized}'
    if column == 'Trigger Day':
        return f'monitor-badge trigger-day-{normalized}'
    if column == 'Trigger':
        return f'monitor-badge trigger-{normalized}'
    if column in {'PDH', '1m ORH', '5m ORH', 'VWAP Reclaim'} and value in {'success', 'failed'}:
        return f'monitor-badge result-{value}'
    if value in {'-', 'Gap', 'Not Applicable', 'superseded'}:
        return 'monitor-badge status-muted'
    return ''


def _table_cell(column: str, value: Any) -> str:
    text = '' if pd.isna(value) else str(value)
    if text == '':
        return '<td class="is-muted"></td>'
    badge_class = _badge_class(column, text)
    if badge_class:
        return f'<td><span class="{badge_class}">{escape(text)}</span></td>'
    return f'<td>{escape(text)}</td>'


def format_monitor_table_html(df: pd.DataFrame) -> str:
    display = _clean_display_df(df).fillna('')
    header = ''.join(f'<th>{escape(MAIN_COLUMN_LABELS.get(str(column), str(column)))}</th>' for column in display.columns)
    body_rows = []
    for _, row in display.iterrows():
        cells = ''.join(_table_cell(str(column), value) for column, value in row.items())
        body_rows.append(f'<tr>{cells}</tr>')
    body = ''.join(body_rows)
    return f'''
<style>
.monitor-table-wrap {{
  width: 100%;
  overflow-x: auto;
  overflow-y: visible;
  margin: 0.45rem 0 0.85rem 0;
  border: 1px solid rgba(250, 250, 250, 0.12);
  border-radius: 8px;
}}
.monitor-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}}
.monitor-table th {{
  text-align: left;
  padding: 0.58rem 0.62rem;
  border-bottom: 1px solid rgba(250, 250, 250, 0.22);
  background: rgba(250, 250, 250, 0.11);
  color: rgba(250, 250, 250, 0.96);
  font-size: 0.93rem;
  font-weight: 750;
  white-space: nowrap;
}}
.monitor-table td {{
  padding: 0.5rem 0.62rem;
  border-bottom: 1px solid rgba(250, 250, 250, 0.13);
  color: rgba(250, 250, 250, 0.92);
  white-space: nowrap;
}}
.monitor-table tbody tr:nth-child(even) {{
  background: rgba(250, 250, 250, 0.035);
}}
.monitor-table tbody tr:hover {{
  background: rgba(250, 250, 250, 0.06);
}}
.monitor-table tbody tr:last-child td {{
  border-bottom: none;
}}
.is-muted {{
  color: rgba(250, 250, 250, 0.38);
}}
.monitor-badge {{
  display: inline-block;
  padding: 0.16rem 0.42rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 650;
}}
.current-status-active, .trigger-day-success, .result-success {{
  color: #baf7d0;
  background: rgba(46, 160, 91, 0.24);
  border: 1px solid rgba(94, 218, 138, 0.36);
}}
.current-status-failed, .current-status-failed-d0, .current-status-failed-d1, .current-status-failed-d2, .current-status-failed-d3, .trigger-day-fail, .result-failed {{
  color: #ffc7c7;
  background: rgba(196, 61, 61, 0.24);
  border: 1px solid rgba(240, 112, 112, 0.35);
}}
.trigger-day-unresolved, .status-muted {{
  color: rgba(250, 250, 250, 0.78);
  background: rgba(148, 163, 184, 0.18);
  border: 1px solid rgba(148, 163, 184, 0.30);
}}
.trigger-pdh, .trigger-failed-pdh-trigger, .trigger-1m-orh, .trigger-5m-orh, .trigger-vwap-reclaim, .trigger-alt-required, .trigger-failed-or-trigger, .trigger-no-trigger {{
  color: rgba(236, 244, 255, 0.92);
  background: rgba(59, 130, 246, 0.16);
  border: 1px solid rgba(96, 165, 250, 0.28);
}}
</style>
<div class="monitor-table-wrap">
  <table class="monitor-table">
    <thead><tr>{header}</tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>
'''


def _summary_count_with_pct(summary: dict, key: str, denominator: int) -> str:
    count = int(summary.get(key, 0) or 0)
    pct = 0 if denominator <= 0 else round((count / denominator) * 100)
    return f'{count} ({pct}%)'


def format_summary_blocks_html(summary: dict) -> str:
    setups_count = int(summary.get('Setups', 0) or 0)
    groups = [
        ('Overall', [('Setups', 'Setups', False), ('Day Success', 'Day Success', True), ('Day Fail', 'Day Fail', True), ('Unresolved', 'Unresolved', True), ('Active', 'Active', True), ('Failed After D0', 'Later Failed', True)]),
        ('PDH', [('Gap', 'PDH Gap', True), ('Success', 'PDH', True), ('Failed', 'Failed PDH Trigger', True)]),
        ('VWAP', [('Success', 'VWAP Trigger', True), ('Failed', 'VWAP Failed', True)]),
        ('1m OR', [('Clean 1m', 'Clean 1m', True), ('Failed 1m', '1m Failed', True)]),
        ('5m OR', [('Clean 5m', 'Clean 5m', True), ('Failed 5m', '5m Failed', True)]),
        ('Alternate / Other', [('Alt Required', 'Alt Required', True), ('No Trigger', 'No Trigger', True), ('Retested', 'Retested', True)]),
        ('Follow-Through', [('Median Current', 'Median Current %', False), ('Median Max', 'Median Max %', False), ('Median D3 High', 'Median D3 High %', False)]),
    ]
    cards = []
    for title, metrics in groups:
        items = []
        for label, key, show_pct in metrics:
            value = _summary_count_with_pct(summary, key, setups_count) if show_pct else str(summary.get(key, ''))
            items.append(f'<div class="summary-item"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>')
        cards.append(f'<section class="summary-card"><h4>{escape(title)}</h4>{"".join(items)}</section>')
    return f'''
<style>
.summary-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 0.65rem;
  margin: 0.2rem 0 0.85rem 0;
}}
.summary-card {{
  border: 1px solid rgba(250, 250, 250, 0.12);
  border-radius: 8px;
  padding: 0.7rem 0.75rem;
  background: rgba(250, 250, 250, 0.035);
}}
.summary-card h4 {{
  margin: 0 0 0.5rem 0;
  color: rgba(250, 250, 250, 0.92);
  font-size: 0.94rem;
  font-weight: 750;
}}
.summary-item {{
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 0.18rem 0;
  color: rgba(250, 250, 250, 0.68);
  font-size: 0.86rem;
}}
.summary-item strong {{
  color: rgba(250, 250, 250, 0.95);
  font-weight: 750;
}}
</style>
<div class="summary-grid">{''.join(cards)}</div>
'''


def detail_table(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return pd.DataFrame(columns=DETAIL_COLUMNS)
    out = sort_monitor_rows(table).copy()
    for column in DETAIL_COLUMNS:
        if column not in out:
            out[column] = ''
    return _clean_display_df(out[DETAIL_COLUMNS])


def day_summary(df: pd.DataFrame) -> dict:
    pdh = df['PDH'] if 'PDH' in df else pd.Series(dtype=object)
    vwap = df['VWAP Reclaim'] if 'VWAP Reclaim' in df else pd.Series(dtype=object)
    other = trigger_other_bucket_counts(df)
    return {
        'Setups': len(df),
        'PDH Gap': int((pdh == 'Gap').sum()) if not df.empty else 0,
        'PDH': int((df['Trigger'] == 'PDH').sum()) if not df.empty else 0,
        'Failed PDH Trigger': int((df['Trigger'] == 'Failed PDH Trigger').sum()) if not df.empty else 0,
        'VWAP Trigger': int((vwap == 'success').sum()) if not df.empty else 0,
        'VWAP Failed': int((vwap == 'failed').sum()) if not df.empty else 0,
        'Clean 1m': int((df['1m ORH'] == 'success').sum()) if not df.empty else 0,
        'Clean 5m': int((df['5m ORH'] == 'success').sum()) if not df.empty else 0,
        '1m Failed': int((df['1m ORH'] == 'failed').sum()) if not df.empty else 0,
        '5m Failed': int((df['5m ORH'] == 'failed').sum()) if not df.empty else 0,
        'Alt Required': other['Alt Required'],
        'No Trigger': other['No Trigger'],
        'Day Success': int((df['Trigger Day'] == 'Success').sum()) if not df.empty else 0,
        'Day Fail': int((df['Trigger Day'] == 'Fail').sum()) if not df.empty else 0,
        'Unresolved': other['Unresolved'],
        'Active': int((df['Current Status'] == 'Active').sum()) if not df.empty else 0,
        'Later Failed': int(df['Current Status'].fillna('').astype(str).str.startswith('Failed').sum()) if not df.empty else 0,
        'Retested': int((df['Retests'] != '').sum()) if not df.empty and 'Retests' in df else 0,
        'Median Current %': _fmt_pct(df['current_pct_raw'].median()) if not df.empty else '',
        'Median Max %': _fmt_pct(df['max_pct_raw'].median()) if not df.empty else '',
        'Median D3 High %': _fmt_pct(df['d3_high_pct_raw'].median()) if not df.empty and 'd3_high_pct_raw' in df else '',
    }


def setup_dropdown_options(table: pd.DataFrame) -> list[str]:
    values = [] if table.empty or 'Setup' not in table else [_blank(v) for v in table['Setup'].tolist()]
    extras = sorted({v for v in values if v and v not in SETUP_OPTIONS})
    return [*SETUP_OPTIONS, *extras]


def rating_dropdown_options(table: pd.DataFrame) -> list[str]:
    values = [] if table.empty or 'Rating' not in table else [_blank(v) for v in table['Rating'].tolist()]
    extras = sorted({v for v in values if v and v not in RATING_OPTIONS})
    return [*RATING_OPTIONS, *extras]


def entry_tactic_dropdown_options(table: pd.DataFrame) -> list[str]:
    values = [] if table.empty or 'Entry Tactic' not in table else [_blank(v) for v in table['Entry Tactic'].tolist()]
    extras = sorted({v for v in values if v and v not in ENTRY_TACTIC_OPTIONS})
    return [*ENTRY_TACTIC_OPTIONS, *extras]


def ensure_manual_metadata_columns(con) -> None:
    con.execute('alter table watchlist_candidates add column if not exists entry_tactic text')


def manual_metadata_candidates(con, setup_date) -> pd.DataFrame:
    ensure_manual_metadata_columns(con)
    raw = con.execute(
        """
        select candidate_id, ticker, setup, entry_tactic, rating
        from watchlist_candidates
        where watchlist_date=?
        order by ticker
        """,
        [setup_date],
    ).df()
    if raw.empty:
        return pd.DataFrame(columns=['candidate_id', 'Ticker', 'Setup', 'Entry Tactic', 'Rating'])
    rating = raw['rating'].apply(lambda v: '' if _num(v) is None else str(int(float(v))) if float(v).is_integer() else str(float(v)))
    return pd.DataFrame({
        'candidate_id': raw['candidate_id'],
        'Ticker': raw['ticker'].astype(str),
        'Setup': raw['setup'].apply(_blank),
        'Entry Tactic': raw['entry_tactic'].apply(_blank),
        'Rating': rating,
    })


def apply_setup_rating_updates(con, original: pd.DataFrame, edited: pd.DataFrame) -> int:
    if original.empty or edited.empty:
        return 0
    ensure_manual_metadata_columns(con)
    changed = 0
    original_by_id = original.set_index('candidate_id')
    for _, row in edited.iterrows():
        candidate_id = row.get('candidate_id')
        if candidate_id not in original_by_id.index:
            continue
        prior = original_by_id.loc[candidate_id]
        new_setup = _blank(row.get('Setup'))
        new_entry_tactic = _blank(row.get('Entry Tactic'))
        new_rating = _blank(row.get('Rating'))
        old_setup = _blank(prior.get('Setup'))
        old_entry_tactic = _blank(prior.get('Entry Tactic'))
        old_rating = _blank(prior.get('Rating'))
        if new_entry_tactic and new_entry_tactic not in ENTRY_TACTIC_OPTIONS:
            raise ValueError(f'Invalid Entry Tactic: {new_entry_tactic}')
        if new_setup == old_setup and new_entry_tactic == old_entry_tactic and new_rating == old_rating:
            continue
        rating_value = None if new_rating == '' else float(new_rating)
        con.execute(
            'update watchlist_candidates set setup=?, entry_tactic=?, rating=? where candidate_id=?',
            [new_setup or None, new_entry_tactic or None, rating_value, int(candidate_id)],
        )
        changed += 1
    if changed:
        try:
            con.commit()
        except Exception:
            pass
    return changed


def _format_section_table(raw: pd.DataFrame) -> pd.DataFrame:
    blank_series = pd.Series([None] * len(raw), index=raw.index)
    close_below_be = raw.get('close_below_be', blank_series).apply(_bool_or_none)
    close_below_be_day = raw.get('close_below_be_day', blank_series)
    trigger_days = [
        trigger_day_status(trigger_type, fail_day_value)
        for trigger_type, fail_day_value in zip(raw['trigger_type'], raw['fail_day'])
    ]
    current_statuses = [
        current_status_display(trigger_day, fail_day_value, close_flag, close_day)
        for trigger_day, fail_day_value, close_flag, close_day in zip(trigger_days, raw['fail_day'], close_below_be, close_below_be_day)
    ]
    pdh_governed = raw.get('pdh_governed', blank_series).map(lambda v: bool(v) if not pd.isna(v) else False)
    raw_one_min_result = raw.get('raw_one_min_result', raw.get('one_min_result', blank_series)).apply(_blank)
    raw_five_min_result = raw.get('raw_five_min_result', raw.get('five_min_result', blank_series)).apply(_blank)
    display_one_min_result = raw.get('one_min_result', raw_one_min_result).apply(_blank)
    display_five_min_result = raw.get('five_min_result', raw_five_min_result).apply(_blank)
    vwap_selected = raw['trigger_type'].eq('VWAP Reclaim') if 'trigger_type' in raw else pd.Series(False, index=raw.index)
    display_one_min_result = display_one_min_result.mask(vwap_selected, raw_one_min_result)
    display_five_min_result = display_five_min_result.mask(vwap_selected, raw_five_min_result)
    qualified_vwap_result = raw.get('vwap_qualified_trigger_result', blank_series).apply(_blank)
    qualified_vwap_result = qualified_vwap_result.mask(qualified_vwap_result.eq('') & raw['trigger_type'].eq('VWAP Reclaim'), 'success')
    orh_suppression_reason = pd.Series(
        [
            vwap_orh_suppression_reason(row, one, five)
            for (_, row), one, five in zip(raw.iterrows(), display_one_min_result, display_five_min_result)
        ],
        index=raw.index,
    )
    adjusted_orh = [
        vwap_superseded_orh_display_values(row, one, five)
        for (_, row), one, five in zip(raw.iterrows(), display_one_min_result, display_five_min_result)
    ]
    display_one_min_result = pd.Series([one for one, _ in adjusted_orh], index=raw.index)
    display_five_min_result = pd.Series([five for _, five in adjusted_orh], index=raw.index)
    vwap_success_later_failed = pd.Series(
        [
            bool(trigger == 'VWAP Reclaim' and qualified == 'success' and str(status).startswith('Failed'))
            for trigger, qualified, status in zip(raw['trigger_type'], qualified_vwap_result, current_statuses)
        ],
        index=raw.index,
    )

    display = pd.DataFrame({
        'candidate_id': raw['candidate_id'],
        'Ticker': raw['ticker'].astype(str),
        'Status': raw['status'],
        'Current Status': current_statuses,
        'Trigger Day': trigger_days,
        'Trigger': raw['trigger_type'],
        'PDH': raw.get('pdh_result', blank_series).apply(lambda v: '-' if _blank(v) == '' else _blank(v)),
        '1m ORH': display_one_min_result.apply(lambda v: '-' if v == '' else v),
        '5m ORH': display_five_min_result.apply(lambda v: '-' if v == '' else v),
        'VWAP Reclaim': qualified_vwap_result.apply(lambda v: '-' if v == '' else v),
        'Notes': raw.get('notes', blank_series).apply(_blank),
        'Current %': raw['current_pct'].apply(_fmt_pct),
        'Max %': raw['max_pct'].apply(_fmt_pct),
        'Close < BE': close_below_be.apply(_fmt_bool_available),
        'D3 High %': raw['d3_high_pct'].apply(_fmt_d3_pct),
        'Retests': [
            _fmt_retests(days, fallback)
            for days, fallback in zip(raw.get('retest_days', blank_series), raw.get('retest_day', blank_series))
        ],
        'Fail Day': raw['fail_day'].apply(_fmt_day),
        'Retest Count': [
            _fmt_retest_count(days, fallback)
            for days, fallback in zip(raw.get('retest_days', blank_series), raw.get('retest_day', blank_series))
        ],
        'Retest Days Raw': [
            _fmt_retest_days_raw(days, fallback)
            for days, fallback in zip(raw.get('retest_days', blank_series), raw.get('retest_day', blank_series))
        ],
        'Retest Dates Raw': raw.get('retest_dates', blank_series).apply(_fmt_retest_dates_raw),
        'Setup': raw['setup'].apply(_blank),
        'Entry Tactic': raw.get('entry_tactic', blank_series).apply(_blank),
        'Rating': raw['rating'].apply(lambda v: '' if _num(v) is None else str(int(float(v))) if float(v).is_integer() else str(float(v))),
        'Prior Day High': raw.get('prior_day_high', blank_series).apply(_fmt_price),
        'Setup Day Open': raw.get('setup_day_open', blank_series).apply(_fmt_price),
        'Open Over PDH': raw.get('open_over_pdh', blank_series).apply(lambda v: '' if v is None or pd.isna(v) else 'Yes' if bool(v) else 'No'),
        'PDH Result': raw.get('pdh_result', blank_series).apply(lambda v: '-' if _blank(v) == '' else _blank(v)),
        'PDH Fail Time': raw.get('pdh_fail_time', blank_series).apply(_fmt_ts),
        '1m Recovery Qualified': raw.get('one_recovery_qualified', blank_series).apply(lambda v: 'Yes' if bool(v) else ''),
        '1m Recovery Break Time': raw.get('one_recovery_break_time', blank_series).apply(_fmt_ts),
        '1m Recovery Reference Low': raw.get('one_recovery_reference_low', blank_series).apply(_fmt_price),
        '5m Recovery Qualified': raw.get('five_recovery_qualified', blank_series).apply(lambda v: 'Yes' if bool(v) else ''),
        '5m Recovery Break Time': raw.get('five_recovery_break_time', blank_series).apply(_fmt_ts),
        '5m Recovery Reference Low': raw.get('five_recovery_reference_low', blank_series).apply(_fmt_price),
        'Alt Recovery Qualified': raw.get('alt_recovery_qualified', blank_series).apply(lambda v: 'Yes' if bool(v) else ''),
        'PDH Trigger Break Time': raw.get('pdh_trigger_break_time', blank_series).apply(_fmt_ts),
        'PDH Trigger Level': raw.get('pdh_trigger_level', blank_series).apply(_fmt_price),
        'PDH Reference Low': raw.get('pdh_reference_low', blank_series).apply(_fmt_price),
        'PDH Reference Basis': raw.get('pdh_reference_basis', blank_series).apply(_blank),
        'Raw VWAP Reclaim Result': raw.get('vwap_reclaim_result', blank_series).apply(lambda v: '-' if _blank(v) == '' else _blank(v)),
        'Raw VWAP Reclaim Prior Below VWAP': raw.get('vwap_reclaim_prior_below_vwap_observed', blank_series).apply(_fmt_bool_available),
        'Raw VWAP Reclaim Time': raw.get('vwap_reclaim_time', blank_series).apply(_fmt_ts),
        'Raw VWAP Reclaim Bar Open': raw.get('vwap_reclaim_reclaim_bar_open', blank_series).apply(_fmt_price),
        'Raw VWAP Reclaim Bar High': raw.get('vwap_reclaim_reclaim_bar_high', blank_series).apply(_fmt_price),
        'Raw VWAP Reclaim Bar Low': raw.get('vwap_reclaim_reclaim_bar_low', blank_series).apply(_fmt_price),
        'Raw VWAP Reclaim Bar Close': raw.get('vwap_reclaim_reclaim_bar_close', blank_series).apply(_fmt_price),
        'Raw VWAP Reclaim Trigger Time': raw.get('vwap_reclaim_trigger_time', blank_series).apply(_fmt_ts),
        'Raw VWAP Reclaim Trigger Price': raw.get('vwap_reclaim_trigger_price', blank_series).apply(_fmt_price),
        'Raw VWAP Reclaim Trigger LOD Reference': raw.get('vwap_reclaim_trigger_lod_reference', blank_series).apply(_fmt_price),
        'Raw VWAP Reclaim Reference Basis': raw.get('vwap_reclaim_reference_basis', blank_series).apply(_blank),
        'Raw VWAP Reclaim Post-Trigger High': raw.get('vwap_reclaim_post_trigger_high', blank_series).apply(_fmt_price),
        'Raw VWAP Reclaim Post-Trigger Low': raw.get('vwap_reclaim_post_trigger_low', blank_series).apply(_fmt_price),
        'Raw VWAP Reclaim Post-Trigger Stop Breached': raw.get('vwap_reclaim_post_trigger_stop_breached', blank_series).apply(_fmt_bool_available),
        'Raw VWAP Reclaim Stop Valid': raw.get('vwap_reclaim_stop_valid', blank_series).apply(_fmt_bool_available),
        'Raw VWAP Reclaim Result Reason': raw.get('vwap_reclaim_result_reason', blank_series).apply(_blank),
        'Qualified VWAP Trigger Result': raw.get('vwap_qualified_trigger_result', blank_series).apply(lambda v: '-' if _blank(v) == '' else _blank(v)),
        'Qualified VWAP Trigger Reason': raw.get('vwap_qualified_trigger_reason', blank_series).apply(_blank),
        'VWAP Success Failed After D0': vwap_success_later_failed.apply(lambda v: 'Yes' if v else ''),
        'ORH Display Suppression': orh_suppression_reason,
        '1m ORH Trigger Price': raw.get('or_1m', blank_series).apply(lambda v: _fmt_price(_loads(v).get('orh'))),
        '5m ORH Trigger Price': raw.get('or_5m', blank_series).apply(lambda v: _fmt_price(_loads(v).get('orh'))),
        'Trigger Level': raw['trigger_level'].apply(_fmt_price),
        'Reference Low': raw['reference_low'].apply(_fmt_price),
        'Reference Basis': raw['reference_basis'].apply(_blank),
        'Trigger Break Time': raw['trigger_break_time'].apply(_fmt_ts),
        '1m Low Swept Before Trigger': raw.get('one_min_low_swept_before_trigger', blank_series).apply(lambda v: 'Yes' if v is True else ''),
        '1m ORH Reference Low': raw.get('one_min_reference_low', blank_series).apply(_fmt_price),
        '1m ORH Reference Basis': raw.get('one_min_reference_basis', blank_series).apply(_blank),
        '1m Post-Trigger Stop Breach': raw.get('one_min_post_trigger_stop_breached', blank_series).apply(lambda v: 'Yes' if v is True else ''),
        '5m Low Swept Before Trigger': raw.get('five_min_low_swept_before_trigger', blank_series).apply(lambda v: 'Yes' if v is True else ''),
        '5m ORH Reference Low': raw.get('five_min_reference_low', blank_series).apply(_fmt_price),
        '5m ORH Reference Basis': raw.get('five_min_reference_basis', blank_series).apply(_blank),
        '5m Post-Trigger Stop Breach': raw.get('five_min_post_trigger_stop_breached', blank_series).apply(lambda v: 'Yes' if v is True else ''),
        'Latest Close': raw['latest_close'].apply(_fmt_price),
        'Latest Status Date': raw.get('latest_trading_date', blank_series).apply(lambda v: '' if pd.isna(v) else pd.to_datetime(v).date().isoformat()),
        'Max High': raw.get('max_high', blank_series).apply(_fmt_price),
        'Max Date': raw.get('max_high_date', blank_series).apply(lambda v: '' if pd.isna(v) else pd.to_datetime(v).date().isoformat()),
        'Setup Close': raw['close_price'].apply(_fmt_price),
        'Setup High': raw['high_price'].apply(_fmt_price),
        'Setup Low': raw['low_price'].apply(_fmt_price),
        'Current vs Setup Close': raw['current_pct_from_setup_close'].apply(_fmt_pct),
        'Max Gain from Setup Close': raw['max_gain_from_setup_close'].apply(_fmt_pct),
        'RVOL': raw['relative_volume_20d'].apply(_fmt_price),
        'Range x ATR(14)': raw['range_vs_atr20'].apply(_fmt_price),
        '1m OR Width / ATR14': raw.get('one_min_or_width_vs_atr14', blank_series).apply(_fmt_ratio),
        '5m OR Width / ATR14': raw.get('five_min_or_width_vs_atr14', blank_series).apply(_fmt_ratio),
        'Close Bucket': raw['close_location'].apply(_close_bucket),
        '1m OR Result': raw_one_min_result,
        '5m OR Result': raw_five_min_result,
        '5m ORH Break Time': raw.get('or_5m', blank_series).apply(lambda v: _fmt_ts(_loads(v).get('orh_break_time'))),
        '5m ORH Broke After Range': raw.get('or_5m', blank_series).apply(lambda v: 'Yes' if _loads(v).get('broke_orh') else ''),
        '1m Follow-Through / ATR14': raw.get('one_min_follow_through_atr', blank_series).apply(_fmt_ratio),
        'current_pct_raw': raw['current_pct'],
        'max_pct_raw': raw['max_pct'],
        'd3_high_pct_raw': raw['d3_high_pct'],
        'latest_trading_date_raw': raw.get('latest_trading_date', blank_series),
    })
    return display


def _rolling_setup_monitor_for_dates(con, dates: list, perf=None) -> list[dict]:
    if not dates:
        return []

    placeholders = ','.join(['?'] * len(dates))
    start = perf_counter()
    candidates = con.execute(
        f"""
        select c.candidate_id,c.watchlist_date,c.ticker,c.rating,c.setup,c.entry_tactic,c.focus,
               f.high_price,f.low_price,f.close_price,f.close_location,
               f.open_price,f.or_1m,f.or_5m,f.or_15m,f.atr20,f.relative_volume_20d,f.range_vs_atr20
        from watchlist_candidates c
        left join entry_day_features f using(candidate_id,watchlist_date,ticker)
        where c.watchlist_date in ({placeholders})
        order by c.watchlist_date desc, c.ticker
        """,
        dates,
    ).df()
    if perf is not None:
        perf.add('Rolling Setup Monitor SQL: candidates/features', perf_counter() - start)
    if candidates.empty:
        return []

    tickers = candidates['ticker'].dropna().astype(str).unique().tolist()
    start = perf_counter()
    daily_bars = con.execute(
        f"select * from daily_bars where ticker in ({','.join(['?'] * len(tickers))}) order by ticker,trading_date",
        tickers,
    ).df() if tickers else pd.DataFrame()
    if perf is not None:
        perf.add('Rolling Setup Monitor SQL: daily bars', perf_counter() - start)
    start = perf_counter()
    intraday_bars = con.execute(
        f"""
        select * from intraday_bars_1m
        where ticker in ({','.join(['?'] * len(tickers))})
          and trading_date in ({placeholders})
        order by ticker,trading_date,timestamp_et
        """,
        [*tickers, *dates],
    ).df() if tickers else pd.DataFrame()
    if perf is not None:
        perf.add('Rolling Setup Monitor SQL: intraday bars', perf_counter() - start)

    rows = []
    bar_slice_seconds = 0.0
    trigger_seconds = 0.0
    orh_pdh_seconds = 0.0
    vwap_seconds = 0.0
    follow_retest_seconds = 0.0
    status_note_seconds = 0.0
    for _, item in candidates.iterrows():
        record = item.to_dict()
        setup_date = pd.to_datetime(record['watchlist_date']).date()
        start = perf_counter()
        ticker_intraday = _bars_for_ticker_date(intraday_bars, record['ticker'], setup_date)
        ticker_daily = _daily_for_ticker(daily_bars, record['ticker'], setup_date)
        prior_day_high = _prior_day_high_for_ticker(daily_bars, record['ticker'], setup_date)
        bar_slice_seconds += perf_counter() - start
        start = perf_counter()
        trigger = derive_trigger_reference(
            record.get('or_1m'),
            record.get('or_5m'),
            record.get('or_15m'),
            record.get('close_location'),
            ticker_intraday,
            ticker_daily,
            prior_day_high,
            record.get('open_price'),
        )
        trigger_seconds += perf_counter() - start
        start = perf_counter()
        one_assessment = orh_trigger_assessment(record.get('or_1m'), 1, ticker_intraday, ticker_daily)
        five_assessment = orh_trigger_assessment(record.get('or_5m'), 5, ticker_intraday, ticker_daily)
        pdh_assessment = pdh_trigger_assessment(prior_day_high, record.get('open_price'), ticker_intraday, ticker_daily)
        orh_pdh_seconds += perf_counter() - start
        record.update({
            'prior_day_high': pdh_assessment.get('prior_day_high'),
            'setup_day_open': pdh_assessment.get('setup_day_open'),
            'open_over_pdh': pdh_assessment.get('open_over_pdh'),
            'one_min_low_swept_before_trigger': one_assessment.get('low_swept_before_trigger'),
            'one_min_reference_low': one_assessment.get('reference_low'),
            'one_min_reference_basis': one_assessment.get('reference_basis'),
            'one_min_post_trigger_stop_breached': one_assessment.get('post_trigger_stop_breached'),
            'five_min_low_swept_before_trigger': five_assessment.get('low_swept_before_trigger'),
            'five_min_reference_low': five_assessment.get('reference_low'),
            'five_min_reference_basis': five_assessment.get('reference_basis'),
            'five_min_post_trigger_stop_breached': five_assessment.get('post_trigger_stop_breached'),
        })
        record.update(trigger)
        start = perf_counter()
        record.update(_vwap_reclaim_fields(ticker_intraday, record.get('reference_low'), setup_date))
        vwap_seconds += perf_counter() - start
        start = perf_counter()
        record.update(resolve_display_triggers(pd.DataFrame([record])).iloc[0].to_dict())
        trigger_seconds += perf_counter() - start
        record.update(opening_range_width_notes(record.get('or_1m'), record.get('or_5m'), record.get('atr20')))
        start = perf_counter()
        record.update(_follow_through(record, daily_bars, intraday_bars))
        follow_retest_seconds += perf_counter() - start
        start = perf_counter()
        raw_one_min_result = opening_range_result(record.get('or_1m'), 1, record['trigger_type'], ticker_intraday, ticker_daily)
        raw_five_min_result = opening_range_result(record.get('or_5m'), 5, record['trigger_type'], ticker_intraday, ticker_daily)
        orh_pdh_seconds += perf_counter() - start
        record['raw_one_min_result'] = raw_one_min_result
        record['raw_five_min_result'] = raw_five_min_result
        if record.get('pdh_governed'):
            record['one_min_result'] = 'success' if record.get('pdh_recovery_trigger') == '1m ORH' else '-'
            record['five_min_result'] = 'success' if record.get('pdh_recovery_trigger') == '5m ORH' else '-'
        else:
            record['one_min_result'] = raw_one_min_result or '-'
            record['five_min_result'] = '-' if record['trigger_type'] == '1m ORH' else raw_five_min_result or '-'
        start = perf_counter()
        record.update(apply_one_min_quality_notes(record, ticker_intraday))
        record.update(apply_weak_close_note(record))
        record['status'] = status_for(record['trigger_type'], record['fail_day'])
        status_note_seconds += perf_counter() - start
        rows.append(record)
    if perf is not None:
        perf.add('Rolling Setup Monitor derivation: bar slicing', bar_slice_seconds)
        perf.add('Rolling Setup Monitor derivation: trigger resolution', trigger_seconds)
        perf.add('Rolling Setup Monitor derivation: ORH/PDH triggers', orh_pdh_seconds)
        perf.add('Rolling Setup Monitor derivation: VWAP reclaim', vwap_seconds)
        perf.add('Rolling Setup Monitor derivation: retests/follow-through', follow_retest_seconds)
        perf.add('Rolling Setup Monitor derivation: close < BE/status/notes', status_note_seconds)

    start = perf_counter()
    raw = pd.DataFrame(rows)
    sections = []
    for setup_date, group in raw.groupby('watchlist_date', sort=False):
        table = _format_section_table(group)
        sections.append({
            'setup_date': pd.to_datetime(setup_date).date().isoformat(),
            'summary': day_summary(table),
            'table': sort_monitor_rows(table),
        })
    if perf is not None:
        perf.add('Rolling Setup Monitor dataframe formatting', perf_counter() - start)
    return sections


def rolling_setup_monitor_for_date(con, setup_date, perf=None) -> list[dict]:
    selected = pd.to_datetime(setup_date).date()
    return _rolling_setup_monitor_for_dates(con, [selected], perf=perf)


def rolling_setup_monitor(con, setup_dates: int = 5, perf=None) -> list[dict]:
    start = perf_counter()
    dates = [
        r[0]
        for r in con.execute(
            'select distinct watchlist_date from watchlist_candidates where watchlist_date is not null order by watchlist_date desc limit ?',
            [setup_dates],
        ).fetchall()
    ]
    if perf is not None:
        perf.add('Rolling Setup Monitor SQL: setup dates', perf_counter() - start)
    return _rolling_setup_monitor_for_dates(con, dates, perf=perf)
