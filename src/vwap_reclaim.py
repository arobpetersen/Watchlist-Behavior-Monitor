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
    setup_date: Any = None,
) -> dict:
    def result(
        value: str,
        reclaim_time=None,
        reclaim_bar_open=None,
        reclaim_bar_high=None,
        reclaim_bar_low=None,
        reclaim_bar_close=None,
        trigger_time=None,
        trigger_price=None,
        post_trigger_high=None,
        post_trigger_low=None,
        post_trigger_stop_breached: bool | None = None,
        failure_reason: str = '',
        prior_below_vwap_observed: bool | None = None,
    ) -> dict:
        return {
            'result': value,
            'reclaim_time': reclaim_time,
            'reclaim_bar_open': reclaim_bar_open,
            'reclaim_bar_high': reclaim_bar_high,
            'reclaim_bar_low': reclaim_bar_low,
            'reclaim_bar_close': reclaim_bar_close,
            'trigger_time': trigger_time,
            'trigger_price': trigger_price,
            'post_trigger_high': post_trigger_high,
            'post_trigger_low': post_trigger_low,
            'post_trigger_stop_breached': post_trigger_stop_breached,
            'failure_reason': failure_reason,
            'result_reason': failure_reason,
            'prior_below_vwap_observed': prior_below_vwap_observed,
        }

    if bars is None or bars.empty:
        return result('Not Applicable', failure_reason='missing intraday bars')

    source = bars.copy()
    if setup_date is not None:
        setup_day = pd.to_datetime(setup_date, errors='coerce')
        if pd.isna(setup_day):
            return result('Not Applicable', failure_reason='invalid setup date')
        if 'trading_date' in source:
            dates = pd.to_datetime(source['trading_date'], errors='coerce').dt.normalize()
            source = source[dates.eq(setup_day.normalize())].copy()
        elif 'timestamp_et' in source:
            timestamps = pd.to_datetime(source['timestamp_et'], errors='coerce').dt.normalize()
            source = source[timestamps.eq(setup_day.normalize())].copy()
        if source.empty:
            return result('Not Applicable', failure_reason='missing setup-date intraday bars')

    session = regular_session_bars(source)
    if session.empty:
        return result('Not Applicable', failure_reason='missing regular-session bars')
    quality_rows = partial_intraday_sessions(
        session[['ticker', 'trading_date', 'timestamp_et']] if {'ticker', 'trading_date'}.issubset(session.columns) else pd.DataFrame(),
        min_regular_session_bars=min_regular_session_bars,
    ) if {'ticker', 'trading_date'}.issubset(session.columns) else pd.DataFrame()
    if not quality_rows.empty:
        return result('Not Applicable', failure_reason='partial intraday data')

    five_minute = five_minute_bars_with_vwap(session)
    if five_minute.empty:
        return result('', failure_reason='no 5-minute bars', prior_below_vwap_observed=False)
    end_times = five_minute['end_time'].dt.time
    close = pd.to_numeric(five_minute['close'], errors='coerce')
    vwap = pd.to_numeric(five_minute['vwap'], errors='coerce')
    prior_below = (close <= vwap).shift(fill_value=False).cummax()
    candidates = five_minute[
        (end_times >= pd.Timestamp('10:00').time())
        & (end_times <= pd.Timestamp('11:30').time())
        & (close > vwap)
        & prior_below
    ]
    if candidates.empty:
        any_prior_below = bool(prior_below.any())
        above_in_window = bool((
            (end_times >= pd.Timestamp('10:00').time())
            & (end_times <= pd.Timestamp('11:30').time())
            & (close > vwap)
        ).any())
        reason = 'no prior 5-minute close below or equal to VWAP' if above_in_window and not any_prior_below else 'no true VWAP reclaim'
        return result('', failure_reason=reason, prior_below_vwap_observed=any_prior_below)

    reclaim = candidates.iloc[0]
    reclaim_open = float(reclaim['open'])
    reclaim_high = float(reclaim['high'])
    reclaim_low = float(reclaim['low'])
    reclaim_close = float(reclaim['close'])
    reclaim_end = reclaim['end_time']
    later = session[session['timestamp_et'] >= reclaim_end]
    trigger = later[pd.to_numeric(later['high'], errors='coerce') > reclaim_high]
    if trigger.empty:
        return result(
            'failed',
            reclaim_time=_fmt_ts(reclaim_end),
            reclaim_bar_open=reclaim_open,
            reclaim_bar_high=reclaim_high,
            reclaim_bar_low=reclaim_low,
            reclaim_bar_close=reclaim_close,
            trigger_price=reclaim_high,
            failure_reason='reclaim-bar high not taken out',
            prior_below_vwap_observed=True,
        )
    first = trigger.iloc[0]
    trigger_time = first['timestamp_et']
    post_trigger = session[session['timestamp_et'] >= trigger_time]
    post_trigger_high = pd.to_numeric(post_trigger['high'], errors='coerce').max()
    post_trigger_low = pd.to_numeric(post_trigger['low'], errors='coerce').min()
    stop_breached = bool(pd.notna(post_trigger_low) and post_trigger_low < reclaim_low)
    if stop_breached:
        return result(
            'failed',
            reclaim_time=_fmt_ts(reclaim_end),
            reclaim_bar_open=reclaim_open,
            reclaim_bar_high=reclaim_high,
            reclaim_bar_low=reclaim_low,
            reclaim_bar_close=reclaim_close,
            trigger_time=_fmt_ts(trigger_time),
            trigger_price=reclaim_high,
            post_trigger_high=float(post_trigger_high) if pd.notna(post_trigger_high) else None,
            post_trigger_low=float(post_trigger_low) if pd.notna(post_trigger_low) else None,
            post_trigger_stop_breached=True,
            failure_reason='post-trigger reclaim-bar low breached',
            prior_below_vwap_observed=True,
        )
    return result(
        'success',
        reclaim_time=_fmt_ts(reclaim_end),
        reclaim_bar_open=reclaim_open,
        reclaim_bar_high=reclaim_high,
        reclaim_bar_low=reclaim_low,
        reclaim_bar_close=reclaim_close,
        trigger_time=_fmt_ts(trigger_time),
        trigger_price=reclaim_high,
        post_trigger_high=float(post_trigger_high) if pd.notna(post_trigger_high) else None,
        post_trigger_low=float(post_trigger_low) if pd.notna(post_trigger_low) else None,
        post_trigger_stop_breached=False,
        failure_reason='reclaim confirmed and held through setup session',
        prior_below_vwap_observed=True,
    )
