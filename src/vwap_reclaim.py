from __future__ import annotations

from typing import Any

import pandas as pd

from src.data_quality import partial_intraday_sessions


def regular_session_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty or 'timestamp_et' not in bars:
        return pd.DataFrame()
    out = bars.copy()
    out['timestamp_et'] = pd.to_datetime(out['timestamp_et'], errors='coerce')
    out = out.dropna(subset=['timestamp_et']).sort_values('timestamp_et')
    times = out['timestamp_et'].dt.time
    return out[(times >= pd.Timestamp('09:30').time()) & (times <= pd.Timestamp('16:00').time())].copy()


def add_intraday_vwap(bars: pd.DataFrame) -> pd.DataFrame:
    out = regular_session_bars(bars)
    if out.empty:
        return out
    volume = pd.to_numeric(out.get('volume', 0), errors='coerce').fillna(0)
    typical = (
        pd.to_numeric(out['high'], errors='coerce')
        + pd.to_numeric(out['low'], errors='coerce')
        + pd.to_numeric(out['close'], errors='coerce')
    ) / 3
    cumulative_volume = volume.cumsum()
    out['vwap'] = (typical * volume).cumsum() / cumulative_volume.replace(0, pd.NA)
    return out


def five_minute_bars_with_vwap(bars: pd.DataFrame) -> pd.DataFrame:
    one_minute = add_intraday_vwap(bars)
    if one_minute.empty:
        return pd.DataFrame(columns=['start_time', 'end_time', 'open', 'high', 'low', 'close', 'volume', 'vwap'])
    grouped = one_minute.set_index('timestamp_et').resample('5min', origin='start_day', offset='9h30min', label='left', closed='left')
    out = grouped.agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'vwap': 'last',
    }).dropna(subset=['open', 'high', 'low', 'close'])
    out = out.reset_index().rename(columns={'timestamp_et': 'start_time'})
    out['end_time'] = out['start_time'] + pd.Timedelta(minutes=5)
    return out[['start_time', 'end_time', 'open', 'high', 'low', 'close', 'volume', 'vwap']]


def _fmt_ts(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors='coerce')
    if pd.isna(parsed):
        return None
    return str(parsed)


def assess_vwap_reclaim(
    bars: pd.DataFrame | None,
    min_regular_session_bars: int = 300,
) -> dict:
    if bars is None or bars.empty:
        return {
            'result': 'Not Applicable',
            'reclaim_time': None,
            'reclaim_bar_high': None,
            'trigger_time': None,
            'trigger_price': None,
            'failure_reason': 'missing intraday bars',
        }

    session = regular_session_bars(bars)
    if session.empty:
        return {
            'result': 'Not Applicable',
            'reclaim_time': None,
            'reclaim_bar_high': None,
            'trigger_time': None,
            'trigger_price': None,
            'failure_reason': 'missing regular-session bars',
        }
    quality_rows = partial_intraday_sessions(
        session[['ticker', 'trading_date', 'timestamp_et']] if {'ticker', 'trading_date'}.issubset(session.columns) else pd.DataFrame(),
        min_regular_session_bars=min_regular_session_bars,
    ) if {'ticker', 'trading_date'}.issubset(session.columns) else pd.DataFrame()
    if not quality_rows.empty:
        return {
            'result': 'Not Applicable',
            'reclaim_time': None,
            'reclaim_bar_high': None,
            'trigger_time': None,
            'trigger_price': None,
            'failure_reason': 'partial intraday data',
        }

    five_minute = five_minute_bars_with_vwap(session)
    if five_minute.empty:
        return {
            'result': '',
            'reclaim_time': None,
            'reclaim_bar_high': None,
            'trigger_time': None,
            'trigger_price': None,
            'failure_reason': 'no 5-minute bars',
        }
    end_times = five_minute['end_time'].dt.time
    candidates = five_minute[
        (end_times >= pd.Timestamp('10:00').time())
        & (end_times <= pd.Timestamp('11:30').time())
        & (pd.to_numeric(five_minute['close'], errors='coerce') > pd.to_numeric(five_minute['vwap'], errors='coerce'))
    ]
    if candidates.empty:
        return {
            'result': '',
            'reclaim_time': None,
            'reclaim_bar_high': None,
            'trigger_time': None,
            'trigger_price': None,
            'failure_reason': 'no qualifying 5-minute close above VWAP',
        }

    reclaim = candidates.iloc[0]
    reclaim_high = float(reclaim['high'])
    reclaim_end = reclaim['end_time']
    later = session[session['timestamp_et'] >= reclaim_end]
    trigger = later[pd.to_numeric(later['high'], errors='coerce') > reclaim_high]
    if trigger.empty:
        return {
            'result': 'failed',
            'reclaim_time': _fmt_ts(reclaim_end),
            'reclaim_bar_high': reclaim_high,
            'trigger_time': None,
            'trigger_price': reclaim_high,
            'failure_reason': 'reclaim-bar high not taken out',
        }
    first = trigger.iloc[0]
    return {
        'result': 'success',
        'reclaim_time': _fmt_ts(reclaim_end),
        'reclaim_bar_high': reclaim_high,
        'trigger_time': _fmt_ts(first['timestamp_et']),
        'trigger_price': reclaim_high,
        'failure_reason': '',
    }
