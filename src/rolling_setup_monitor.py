from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.dashboard_queries import _clean_display_df, _close_bucket
from src.feature_engine import session_filter


SETUP_OPTIONS = [
    '',
    'EP',
    'Breakout',
    'Range Breakout',
    'Pullback',
    'VWAP Reclaim',
    'Gap Hold',
    'High Tight Pivot',
    'High Tight Flag',
    'Stage 2 Continuation Breakout',
    'Momentum',
    'Theme Leader',
    'Theme Sympathy',
    'Other',
]

RATING_OPTIONS = ['', '1', '2', '3', '4', '5']

MAIN_COLUMNS = [
    'Ticker',
    'Status',
    'Trigger',
    '1m ORH',
    '5m ORH',
    'Notes',
    'Current %',
    'Max %',
    'D3 High %',
    'Retest Day',
    'Fail Day',
    'Setup',
    'Rating',
]

DETAIL_COLUMNS = [
    'Ticker',
    'Trigger Level',
    'Reference Low',
    'Reference Basis',
    'Trigger Break Time',
    'Latest Close',
    'Setup Close',
    'Setup High',
    'Setup Low',
    'Current vs Setup Close',
    'Max Gain from Setup Close',
    'RVOL',
    'Range / ATR14',
    '1m OR Width / ATR14',
    '5m OR Width / ATR14',
    'Close Bucket',
    '1m OR Result',
    '5m OR Result',
]

STATUS_PRIORITY = {'Active': 0, 'Unresolved': 1, 'Failed': 2}


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
    trigger_level = _num(data.get('orh'))
    fallback_low = _num(data.get('orl'))
    trigger_low = reference_low_at_trigger(intraday, trigger_break_time)
    reference_low = trigger_low if trigger_low is not None else fallback_low
    bars = _regular_session_bars(intraday)
    if bars.empty and trigger_break_time is None:
        broke_orh = bool(data.get('broke_orh') and not data.get('orh_then_orl') and not _same_bar_break(data))
    else:
        broke_orh = bool(data.get('broke_orh') and not _same_bar_break(data) and trigger_break_time is not None)
    daily_bars = daily if daily is not None else pd.DataFrame()
    failure_day = fail_day(_regular_session_bars(intraday), daily_bars, trigger_break_time, reference_low) if broke_orh else None
    failed_after_trigger = failure_day is not None
    return {
        'broke_orh': broke_orh,
        'trigger_level': trigger_level,
        'trigger_break_time': trigger_break_time,
        'reference_low': reference_low,
        'reference_basis': f'LOD at {minutes}m Trigger' if trigger_low is not None else f'{minutes}m OR',
        'failed_after_trigger': failed_after_trigger,
        'failure_day': failure_day,
    }


def orh_framework_failed(or_json: str, assessment: dict) -> bool:
    data = _loads(or_json)
    if assessment.get('broke_orh') and assessment.get('failed_after_trigger'):
        return True
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
        and fifteen_fail is None
    )


def failed_or_trigger_reference(one_assessment: dict, five_assessment: dict) -> dict:
    failed = []
    for label, assessment in [('1m ORH', one_assessment), ('5m ORH', five_assessment)]:
        if assessment.get('broke_orh') and assessment.get('failed_after_trigger'):
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


def derive_trigger_reference(or_1m: str, or_5m: str, or_15m: str, close_location, intraday: pd.DataFrame | None = None, daily: pd.DataFrame | None = None) -> dict:
    fifteen = _loads(or_15m)
    one_assessment = orh_trigger_assessment(or_1m, 1, intraday, daily)
    five_assessment = orh_trigger_assessment(or_5m, 5, intraday, daily)

    if one_assessment['broke_orh'] and not one_assessment['failed_after_trigger']:
        return {
            'trigger_type': '1m ORH',
            'trigger_level': one_assessment['trigger_level'],
            'reference_low': one_assessment['reference_low'],
            'reference_basis': one_assessment['reference_basis'],
            'trigger_break_time': one_assessment['trigger_break_time'],
        }

    if five_assessment['broke_orh'] and not five_assessment['failed_after_trigger']:
        return {
            'trigger_type': '5m ORH',
            'trigger_level': five_assessment['trigger_level'],
            'reference_low': five_assessment['reference_low'],
            'reference_basis': five_assessment['reference_basis'],
            'trigger_break_time': five_assessment['trigger_break_time'],
        }

    if alt_required_qualified(or_1m, or_5m, or_15m, close_location, intraday, daily):
        return {
            'trigger_type': 'Alt Required',
            'trigger_level': _num(fifteen.get('orh')),
            'reference_low': _num(fifteen.get('orl')),
            'reference_basis': '15m OR Reference',
            'trigger_break_time': _ts(fifteen.get('orh_break_time')),
        }

    failed_reference = failed_or_trigger_reference(one_assessment, five_assessment)
    if failed_reference:
        return failed_reference

    return {
        'trigger_type': 'No Trigger',
        'trigger_level': None,
        'reference_low': None,
        'reference_basis': 'Setup-Day Close fallback',
        'trigger_break_time': None,
        'framework_fail_day': None,
        'failed_framework': None,
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


def opening_range_result(or_json: str, minutes: int, trigger_type: str, intraday: pd.DataFrame | None = None, daily: pd.DataFrame | None = None) -> str:
    data = _loads(or_json)
    if trigger_type == 'Alt Required' and minutes in {1, 5}:
        return 'failed'
    clean_type = f'{minutes}m ORH'
    assessment = orh_trigger_assessment(or_json, minutes, intraday, daily)
    if assessment['broke_orh'] and not assessment['failed_after_trigger']:
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


def retest_day(intraday: pd.DataFrame, daily: pd.DataFrame, trigger_break_time, trigger_level: float | None) -> int | None:
    if trigger_level is None:
        return None
    if day0_retest(intraday, trigger_break_time, trigger_level):
        return 0
    after_setup = daily.iloc[1:4] if not daily.empty else pd.DataFrame()
    for day_number, (_, row) in enumerate(after_setup.iterrows(), start=1):
        if _num(row.get('low')) is not None and float(row['low']) <= float(trigger_level):
            return day_number
    return None


def status_for(trigger_type: str, fail_day_value: int | None) -> str:
    if trigger_type == 'Failed OR Trigger':
        return 'Failed'
    if fail_day_value is not None:
        return 'Failed'
    if trigger_type in {'1m ORH', '5m ORH', 'Alt Required'}:
        return 'Active'
    return 'Unresolved'


def _follow_through(row: dict, daily_bars: pd.DataFrame, intraday_bars: pd.DataFrame) -> dict:
    setup_date = pd.to_datetime(row['watchlist_date']).date()
    daily = _daily_for_ticker(daily_bars, row['ticker'], setup_date)
    intraday = _bars_for_ticker_date(intraday_bars, row['ticker'], setup_date)
    trigger_level = row.get('trigger_level')
    reference_low = row.get('reference_low')
    setup_close = _num(row.get('close_price'))
    preset_fail_day = row.get('framework_fail_day')

    if daily.empty:
        base_price = trigger_level if trigger_level is not None else setup_close
        return {
            'latest_trading_date': None,
            'latest_close': None,
            'current_pct': None,
            'max_pct': None,
            'd3_high_pct': None,
            'current_pct_from_setup_close': None,
            'max_gain_from_setup_close': None,
            'fail_day': preset_fail_day if row.get('trigger_type') == 'Failed OR Trigger' else fail_day(intraday, daily, row.get('trigger_break_time'), reference_low),
            'retest_day': retest_day(intraday, daily, row.get('trigger_break_time'), trigger_level),
            'base_price': base_price,
        }

    latest = daily.iloc[-1]
    latest_close = _num(latest.get('close'))
    base_price = trigger_level if trigger_level is not None else setup_close
    max_high = _num(daily['high'].max())
    d3 = daily.iloc[:4]
    d3_high = _num(d3['high'].max()) if not d3.empty else None

    return {
        'latest_trading_date': latest['trading_date'],
        'latest_close': latest_close,
        'current_pct': _pct(latest_close - base_price, base_price),
        'max_pct': _pct(max_high - base_price, base_price),
        'd3_high_pct': _pct(d3_high - base_price, base_price),
        'current_pct_from_setup_close': _pct(latest_close - setup_close, setup_close),
        'max_gain_from_setup_close': _pct(max_high - setup_close, setup_close),
        'fail_day': preset_fail_day if row.get('trigger_type') == 'Failed OR Trigger' else fail_day(intraday, daily, row.get('trigger_break_time'), reference_low),
        'retest_day': retest_day(intraday, daily, row.get('trigger_break_time'), trigger_level),
        'base_price': base_price,
    }


def sort_monitor_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    table = df.copy()
    table['_status_priority'] = table['Status'].map(STATUS_PRIORITY).fillna(99)
    table['_current_sort'] = table['current_pct_raw'].fillna(float('-inf'))
    return table.sort_values(
        ['_status_priority', '_current_sort', 'Ticker'],
        ascending=[True, False, True],
    ).drop(columns=['_status_priority', '_current_sort'])


def main_table(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return pd.DataFrame(columns=MAIN_COLUMNS)
    return _clean_display_df(sort_monitor_rows(table)[MAIN_COLUMNS])


def detail_table(table: pd.DataFrame) -> pd.DataFrame:
    if table.empty:
        return pd.DataFrame(columns=DETAIL_COLUMNS)
    return _clean_display_df(sort_monitor_rows(table)[DETAIL_COLUMNS])


def day_summary(df: pd.DataFrame) -> dict:
    return {
        'Setups': len(df),
        'Clean 1m': int((df['Trigger'] == '1m ORH').sum()) if not df.empty else 0,
        'Clean 5m': int((df['Trigger'] == '5m ORH').sum()) if not df.empty else 0,
        '1m Failed': int((df['1m ORH'] == 'failed').sum()) if not df.empty else 0,
        '5m Failed': int((df['5m ORH'] == 'failed').sum()) if not df.empty else 0,
        'Alt Required': int((df['Trigger'] == 'Alt Required').sum()) if not df.empty else 0,
        'No Trigger': int((df['Trigger'] == 'No Trigger').sum()) if not df.empty else 0,
        'Active': int((df['Status'] == 'Active').sum()) if not df.empty else 0,
        'Failed': int((df['Status'] == 'Failed').sum()) if not df.empty else 0,
        'Retested': int((df['Retest Day'] != '').sum()) if not df.empty else 0,
        'Median Current %': _fmt_pct(df['current_pct_raw'].median()) if not df.empty else '',
        'Median Max %': _fmt_pct(df['max_pct_raw'].median()) if not df.empty else '',
    }


def setup_dropdown_options(table: pd.DataFrame) -> list[str]:
    values = [] if table.empty or 'Setup' not in table else [_blank(v) for v in table['Setup'].tolist()]
    extras = sorted({v for v in values if v and v not in SETUP_OPTIONS})
    return [*SETUP_OPTIONS, *extras]


def rating_dropdown_options(table: pd.DataFrame) -> list[str]:
    values = [] if table.empty or 'Rating' not in table else [_blank(v) for v in table['Rating'].tolist()]
    extras = sorted({v for v in values if v and v not in RATING_OPTIONS})
    return [*RATING_OPTIONS, *extras]


def apply_setup_rating_updates(con, original: pd.DataFrame, edited: pd.DataFrame) -> int:
    if original.empty or edited.empty:
        return 0
    changed = 0
    original_by_id = original.set_index('candidate_id')
    for _, row in edited.iterrows():
        candidate_id = row.get('candidate_id')
        if candidate_id not in original_by_id.index:
            continue
        prior = original_by_id.loc[candidate_id]
        new_setup = _blank(row.get('Setup'))
        new_rating = _blank(row.get('Rating'))
        old_setup = _blank(prior.get('Setup'))
        old_rating = _blank(prior.get('Rating'))
        if new_setup == old_setup and new_rating == old_rating:
            continue
        rating_value = None if new_rating == '' else float(new_rating)
        con.execute(
            'update watchlist_candidates set setup=?, rating=? where candidate_id=?',
            [new_setup or None, rating_value, int(candidate_id)],
        )
        changed += 1
    return changed


def _format_section_table(raw: pd.DataFrame) -> pd.DataFrame:
    blank_series = pd.Series([None] * len(raw), index=raw.index)
    display = pd.DataFrame({
        'candidate_id': raw['candidate_id'],
        'Ticker': raw['ticker'].astype(str),
        'Status': raw['status'],
        'Trigger': raw['trigger_type'],
        '1m ORH': raw['one_min_result'],
        '5m ORH': raw['five_min_result'],
        'Notes': raw.get('notes', blank_series).apply(_blank),
        'Current %': raw['current_pct'].apply(_fmt_pct),
        'Max %': raw['max_pct'].apply(_fmt_pct),
        'D3 High %': raw['d3_high_pct'].apply(_fmt_pct),
        'Retest Day': raw['retest_day'].apply(_fmt_day),
        'Fail Day': raw['fail_day'].apply(_fmt_day),
        'Setup': raw['setup'].apply(_blank),
        'Rating': raw['rating'].apply(lambda v: '' if _num(v) is None else str(int(float(v))) if float(v).is_integer() else str(float(v))),
        'Trigger Level': raw['trigger_level'].apply(_fmt_price),
        'Reference Low': raw['reference_low'].apply(_fmt_price),
        'Reference Basis': raw['reference_basis'].apply(_blank),
        'Trigger Break Time': raw['trigger_break_time'].apply(_fmt_ts),
        'Latest Close': raw['latest_close'].apply(_fmt_price),
        'Setup Close': raw['close_price'].apply(_fmt_price),
        'Setup High': raw['high_price'].apply(_fmt_price),
        'Setup Low': raw['low_price'].apply(_fmt_price),
        'Current vs Setup Close': raw['current_pct_from_setup_close'].apply(_fmt_pct),
        'Max Gain from Setup Close': raw['max_gain_from_setup_close'].apply(_fmt_pct),
        'RVOL': raw['relative_volume_20d'].apply(_fmt_price),
        'Range / ATR14': raw['range_vs_atr20'].apply(_fmt_price),
        '1m OR Width / ATR14': raw.get('one_min_or_width_vs_atr14', blank_series).apply(_fmt_ratio),
        '5m OR Width / ATR14': raw.get('five_min_or_width_vs_atr14', blank_series).apply(_fmt_ratio),
        'Close Bucket': raw['close_location'].apply(_close_bucket),
        '1m OR Result': raw['one_min_result'],
        '5m OR Result': raw['five_min_result'],
        'current_pct_raw': raw['current_pct'],
        'max_pct_raw': raw['max_pct'],
    })
    return display


def rolling_setup_monitor(con, setup_dates: int = 5) -> list[dict]:
    dates = [
        r[0]
        for r in con.execute(
            'select distinct watchlist_date from watchlist_candidates where watchlist_date is not null order by watchlist_date desc limit ?',
            [setup_dates],
        ).fetchall()
    ]
    if not dates:
        return []

    placeholders = ','.join(['?'] * len(dates))
    candidates = con.execute(
        f"""
        select c.candidate_id,c.watchlist_date,c.ticker,c.rating,c.setup,c.focus,
               f.high_price,f.low_price,f.close_price,f.close_location,
               f.or_1m,f.or_5m,f.or_15m,f.atr20,f.relative_volume_20d,f.range_vs_atr20
        from watchlist_candidates c
        left join entry_day_features f using(candidate_id,watchlist_date,ticker)
        where c.watchlist_date in ({placeholders})
        order by c.watchlist_date desc, c.ticker
        """,
        dates,
    ).df()
    if candidates.empty:
        return []

    tickers = candidates['ticker'].dropna().astype(str).unique().tolist()
    daily_bars = con.execute(
        f"select * from daily_bars where ticker in ({','.join(['?'] * len(tickers))}) order by ticker,trading_date",
        tickers,
    ).df() if tickers else pd.DataFrame()
    intraday_bars = con.execute(
        f"""
        select * from intraday_bars_1m
        where ticker in ({','.join(['?'] * len(tickers))})
          and trading_date in ({placeholders})
        order by ticker,trading_date,timestamp_et
        """,
        [*tickers, *dates],
    ).df() if tickers else pd.DataFrame()

    rows = []
    for _, item in candidates.iterrows():
        record = item.to_dict()
        setup_date = pd.to_datetime(record['watchlist_date']).date()
        ticker_intraday = _bars_for_ticker_date(intraday_bars, record['ticker'], setup_date)
        ticker_daily = _daily_for_ticker(daily_bars, record['ticker'], setup_date)
        trigger = derive_trigger_reference(
            record.get('or_1m'),
            record.get('or_5m'),
            record.get('or_15m'),
            record.get('close_location'),
            ticker_intraday,
            ticker_daily,
        )
        record.update(trigger)
        record.update(opening_range_width_notes(record.get('or_1m'), record.get('or_5m'), record.get('atr20')))
        record.update(_follow_through(record, daily_bars, intraday_bars))
        record['one_min_result'] = opening_range_result(record.get('or_1m'), 1, record['trigger_type'], ticker_intraday, ticker_daily)
        record['five_min_result'] = opening_range_result(record.get('or_5m'), 5, record['trigger_type'], ticker_intraday, ticker_daily)
        record['status'] = status_for(record['trigger_type'], record['fail_day'])
        rows.append(record)

    raw = pd.DataFrame(rows)
    sections = []
    for setup_date, group in raw.groupby('watchlist_date', sort=False):
        table = _format_section_table(group)
        sections.append({
            'setup_date': pd.to_datetime(setup_date).date().isoformat(),
            'summary': day_summary(table),
            'table': sort_monitor_rows(table),
        })
    return sections
