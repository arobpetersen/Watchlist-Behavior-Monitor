from __future__ import annotations

import json
from typing import Any

import pandas as pd

from src.feature_engine import calc_vwap, session_filter
from src.rolling_setup_monitor import (
    alt_required_qualified,
    derive_trigger_reference,
    fail_day,
    opening_range_result,
    pdh_trigger_assessment,
    retest_day,
    status_for,
)


AUDIT_COLUMNS = [
    'Ticker',
    'Setup Date',
    'Trigger Mode',
    '1m ORH',
    '1m ORL',
    '1m OR Start',
    '1m OR End',
    '1m ORH Break Time',
    '1m ORL Break After ORH Time',
    '1m ORH Attempted',
    'Displayed 1m ORH',
    'Raw 1m ORH Result',
    'Prior Day High',
    'Setup Day Open',
    'Open Over PDH',
    'Displayed PDH',
    'PDH Result',
    'PDH Trigger Break Time',
    'PDH Trigger Level',
    'PDH Reference Low',
    'PDH Reference Basis',
    '5m ORH',
    '5m ORL',
    '5m OR Start',
    '5m OR End',
    '5m ORH Break Time',
    '5m ORL Break After ORH Time',
    '5m ORH Attempted',
    'Displayed 5m ORH',
    'Raw 5m ORH Result',
    'Alt Required Qualified',
    '15m ORH',
    '15m ORL',
    '15m ORH Break Time',
    'Selected Trigger',
    'Trigger Level',
    'Reference Low',
    'Reference Basis',
    'Trigger Break Time',
    'Retest Day',
    'Fail Day',
    'Final Trigger',
    'Final Status',
    'Final Fail Day',
]


INTRADAY_COLUMNS = [
    'Timestamp',
    'Open',
    'High',
    'Low',
    'Close',
    'Volume',
    'VWAP',
]


BREAK_COLUMNS = [
    *INTRADAY_COLUMNS,
    'High > 1m ORH',
    'Low < 1m ORL',
    'High > 5m ORH',
    'Low < 5m ORL',
]


def _loads(value: Any) -> dict:
    if not isinstance(value, str) or not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


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


def _fmt_price(value: Any) -> str:
    num = _num(value)
    return '' if num is None else f'{num:.2f}'


def _fmt_ts(value: Any) -> str:
    ts = _ts(value)
    return '' if ts is None else ts.strftime('%Y-%m-%d %H:%M:%S')


def _fmt_day(value: int | None) -> str:
    if value is None or pd.isna(value):
        return ''
    return f'Day {int(value)}'


def _session_timestamp(setup_date, hour: int, minute: int) -> pd.Timestamp:
    return pd.Timestamp(pd.to_datetime(setup_date).date()).replace(hour=hour, minute=minute, second=0)


def _orl_after_orh_time(or_data: dict) -> str:
    if not or_data.get('orh_then_orl'):
        return ''
    return _fmt_ts(or_data.get('orl_break_time'))


def _daily_for_ticker(con, ticker: str, setup_date) -> pd.DataFrame:
    df = con.execute(
        'select * from daily_bars where ticker=? order by trading_date',
        [ticker],
    ).df()
    if not df.empty:
        df['trading_date'] = pd.to_datetime(df['trading_date']).dt.date
    return df


def _prior_day_high(daily: pd.DataFrame, setup_date) -> float | None:
    if daily.empty:
        return None
    prior = daily[pd.to_datetime(daily['trading_date']).dt.date < setup_date]
    if prior.empty:
        return None
    return _num(prior.iloc[-1].get('high'))


def _regular_intraday(con, ticker: str, setup_date) -> pd.DataFrame:
    df = con.execute(
        """
        select * from intraday_bars_1m
        where ticker=? and trading_date=?
        order by timestamp_et
        """,
        [ticker, str(setup_date)],
    ).df()
    if df.empty:
        return df
    df['timestamp_et'] = pd.to_datetime(df['timestamp_et'])
    df = session_filter(df)
    if df.empty:
        return df
    if 'vwap' not in df or df['vwap'].isna().all():
        df['vwap'] = calc_vwap(df)
    return df.sort_values('timestamp_et')


def _format_intraday(df: pd.DataFrame, include_flags: bool = False) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=BREAK_COLUMNS if include_flags else INTRADAY_COLUMNS)
    out = pd.DataFrame({
        'Timestamp': df['timestamp_et'].apply(_fmt_ts),
        'Open': df['open'].apply(_fmt_price),
        'High': df['high'].apply(_fmt_price),
        'Low': df['low'].apply(_fmt_price),
        'Close': df['close'].apply(_fmt_price),
        'Volume': df['volume'],
        'VWAP': df['vwap'].apply(_fmt_price) if 'vwap' in df else '',
    })
    if include_flags:
        for column in ['High > 1m ORH', 'Low < 1m ORL', 'High > 5m ORH', 'Low < 5m ORL']:
            out[column] = df[column].map(lambda value: 'Yes' if bool(value) else '')
    return out


def setup_dates(con) -> list[str]:
    rows = con.execute(
        """
        select distinct watchlist_date
        from watchlist_candidates
        where watchlist_date is not null
        order by watchlist_date desc
        """
    ).fetchall()
    return [pd.to_datetime(r[0]).date().isoformat() for r in rows]


def tickers_for_setup_date(con, setup_date) -> list[str]:
    rows = con.execute(
        """
        select ticker
        from watchlist_candidates
        where watchlist_date=?
        order by ticker
        """,
        [str(setup_date)],
    ).fetchall()
    return [r[0] for r in rows]


def audit_for_candidate(con, setup_date, ticker: str) -> dict:
    row = con.execute(
        """
        select c.candidate_id,c.watchlist_date,c.ticker,
               f.or_1m,f.or_5m,f.or_15m,f.close_location
               ,f.open_price
        from watchlist_candidates c
        left join entry_day_features f using(candidate_id,watchlist_date,ticker)
        where c.watchlist_date=? and c.ticker=?
        order by c.candidate_id
        limit 1
        """,
        [str(setup_date), ticker],
    ).df()
    if row.empty:
        return {
            'audit': pd.DataFrame(columns=AUDIT_COLUMNS),
            'first_15_bars': pd.DataFrame(columns=INTRADAY_COLUMNS),
            'break_bars': pd.DataFrame(columns=BREAK_COLUMNS),
        }

    record = row.iloc[0].to_dict()
    setup_day = pd.to_datetime(record['watchlist_date']).date()
    one = _loads(record.get('or_1m'))
    five = _loads(record.get('or_5m'))
    fifteen = _loads(record.get('or_15m'))
    intraday = _regular_intraday(con, record['ticker'], setup_day)
    daily_all = _daily_for_ticker(con, record['ticker'], setup_day)
    prior_high = _prior_day_high(daily_all, setup_day)
    daily = daily_all[pd.to_datetime(daily_all['trading_date']).dt.date >= setup_day].copy() if not daily_all.empty else daily_all
    pdh = pdh_trigger_assessment(prior_high, record.get('open_price'), intraday, daily)
    trigger = derive_trigger_reference(
        record.get('or_1m'),
        record.get('or_5m'),
        record.get('or_15m'),
        record.get('close_location'),
        intraday,
        daily,
        prior_high,
        record.get('open_price'),
    )
    retest = retest_day(intraday, daily, trigger.get('trigger_break_time'), trigger.get('trigger_level'))
    failure = fail_day(intraday, daily, trigger.get('trigger_break_time'), trigger.get('reference_low'))
    if trigger.get('trigger_type') in {'Failed OR Trigger', 'Failed PDH Trigger'}:
        failure = trigger.get('framework_fail_day')
    final_status = status_for(trigger.get('trigger_type'), failure)
    trigger_mode = 'PDH-governed' if pdh.get('open_over_pdh') is False else 'ORH stack active'
    raw_one_result = opening_range_result(record.get('or_1m'), 1, trigger['trigger_type'], intraday, daily)
    raw_five_result = opening_range_result(record.get('or_5m'), 5, trigger['trigger_type'], intraday, daily)
    displayed_one = '-' if trigger.get('pdh_governed') else raw_one_result or '-'
    displayed_five = '-' if trigger.get('pdh_governed') else raw_five_result or '-'
    displayed_pdh = pdh.get('pdh_result') or '-'

    audit = pd.DataFrame([{
        'Ticker': record['ticker'],
        'Setup Date': setup_day.isoformat(),
        'Trigger Mode': trigger_mode,
        '1m ORH': _fmt_price(one.get('orh')),
        '1m ORL': _fmt_price(one.get('orl')),
        '1m OR Start': _fmt_ts(_session_timestamp(setup_day, 9, 30)),
        '1m OR End': _fmt_ts(_session_timestamp(setup_day, 9, 31)),
        '1m ORH Break Time': _fmt_ts(one.get('orh_break_time')),
        '1m ORL Break After ORH Time': _orl_after_orh_time(one),
        '1m ORH Attempted': 'Yes' if one.get('broke_orh') else '',
        'Displayed 1m ORH': displayed_one,
        'Raw 1m ORH Result': raw_one_result,
        'Prior Day High': _fmt_price(prior_high),
        'Setup Day Open': _fmt_price(pdh.get('setup_day_open')),
        'Open Over PDH': '' if pdh.get('open_over_pdh') is None else 'Yes' if pdh.get('open_over_pdh') else 'No',
        'Displayed PDH': displayed_pdh,
        'PDH Result': pdh.get('pdh_result') or '-',
        'PDH Trigger Break Time': _fmt_ts(pdh.get('trigger_break_time')),
        'PDH Trigger Level': _fmt_price(pdh.get('trigger_level') if pdh.get('broke_pdh') else None),
        'PDH Reference Low': _fmt_price(pdh.get('reference_low')),
        'PDH Reference Basis': pdh.get('reference_basis') or '',
        '5m ORH': _fmt_price(five.get('orh')),
        '5m ORL': _fmt_price(five.get('orl')),
        '5m OR Start': _fmt_ts(_session_timestamp(setup_day, 9, 30)),
        '5m OR End': _fmt_ts(_session_timestamp(setup_day, 9, 35)),
        '5m ORH Break Time': _fmt_ts(five.get('orh_break_time')),
        '5m ORL Break After ORH Time': _orl_after_orh_time(five),
        '5m ORH Attempted': 'Yes' if five.get('broke_orh') else '',
        'Displayed 5m ORH': displayed_five,
        'Raw 5m ORH Result': raw_five_result,
        'Alt Required Qualified': 'Yes' if alt_required_qualified(record.get('or_1m'), record.get('or_5m'), record.get('or_15m'), record.get('close_location'), intraday, daily) else '',
        '15m ORH': _fmt_price(fifteen.get('orh')),
        '15m ORL': _fmt_price(fifteen.get('orl')),
        '15m ORH Break Time': _fmt_ts(fifteen.get('orh_break_time')),
        'Selected Trigger': trigger['trigger_type'],
        'Trigger Level': _fmt_price(trigger.get('trigger_level')),
        'Reference Low': _fmt_price(trigger.get('reference_low')),
        'Reference Basis': trigger.get('reference_basis') or '',
        'Trigger Break Time': _fmt_ts(trigger.get('trigger_break_time')),
        'Retest Day': _fmt_day(retest),
        'Fail Day': _fmt_day(failure),
        'Final Trigger': trigger['trigger_type'],
        'Final Status': final_status,
        'Final Fail Day': _fmt_day(failure),
    }])

    first_15 = _format_intraday(intraday.head(15))
    break_bars = intraday.copy()
    one_orh = _num(one.get('orh'))
    one_orl = _num(one.get('orl'))
    five_orh = _num(five.get('orh'))
    five_orl = _num(five.get('orl'))
    break_bars['High > 1m ORH'] = False if one_orh is None else break_bars['high'] > one_orh
    break_bars['Low < 1m ORL'] = False if one_orl is None else break_bars['low'] < one_orl
    break_bars['High > 5m ORH'] = False if five_orh is None else break_bars['high'] > five_orh
    break_bars['Low < 5m ORL'] = False if five_orl is None else break_bars['low'] < five_orl
    flag_columns = ['High > 1m ORH', 'Low < 1m ORL', 'High > 5m ORH', 'Low < 5m ORL']
    break_bars = break_bars[break_bars[flag_columns].any(axis=1)]

    return {
        'audit': audit[AUDIT_COLUMNS],
        'first_15_bars': first_15,
        'break_bars': _format_intraday(break_bars, include_flags=True),
    }
