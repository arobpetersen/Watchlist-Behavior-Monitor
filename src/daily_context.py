from __future__ import annotations

import pandas as pd


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def calculate_daily_context(daily_bars: pd.DataFrame, ticker: str, trading_date: str) -> dict:
    empty = {
        'prior_close': None,
        'gap_pct': None,
        'atr20': None,
        'day_range_pct': None,
        'range_vs_atr20': None,
        'avg_volume_20d': None,
        'relative_volume_20d': None,
        'broke_entry_day_high_D1': None,
        'broke_entry_day_low_D1': None,
        'closed_higher_D1': None,
        'broke_entry_day_high_within_3d': None,
        'broke_entry_day_low_within_3d': None,
        'max_gain_3d_pct': None,
        'max_drawdown_3d_pct': None,
    }
    if daily_bars.empty:
        return empty

    df = daily_bars[daily_bars['ticker'] == ticker].copy()
    if df.empty:
        return empty
    df['trading_date'] = pd.to_datetime(df['trading_date']).dt.date
    target_date = pd.to_datetime(trading_date).date()
    df = df.sort_values('trading_date').reset_index(drop=True)

    entry_rows = df[df['trading_date'] == target_date]
    if entry_rows.empty:
        return empty
    entry_idx = int(entry_rows.index[0])
    entry = df.loc[entry_idx]
    prior = df.iloc[:entry_idx].tail(14).copy()
    forward = df.iloc[entry_idx + 1:entry_idx + 4].copy()

    prior_close = None if prior.empty else float(prior.iloc[-1]['close'])
    entry_open = float(entry['open'])
    entry_high = float(entry['high'])
    entry_low = float(entry['low'])
    entry_close = float(entry['close'])
    entry_volume = float(entry['volume'])
    entry_range = entry_high - entry_low

    atr14 = None
    avg_volume_20d = None
    if not prior.empty:
        prior['prev_close'] = prior['close'].shift(1)
        tr_parts = pd.concat([
            prior['high'] - prior['low'],
            (prior['high'] - prior['prev_close']).abs(),
            (prior['low'] - prior['prev_close']).abs(),
        ], axis=1)
        prior['true_range'] = tr_parts.max(axis=1, skipna=True)
        atr14 = float(prior['true_range'].mean())
        avg_volume_20d = float(prior['volume'].mean())

    d1 = forward.iloc[0] if not forward.empty else None
    max_forward_high = None if forward.empty else float(forward['high'].max())
    min_forward_low = None if forward.empty else float(forward['low'].min())

    return {
        'prior_close': prior_close,
        'gap_pct': _safe_div(entry_open - prior_close, prior_close) if prior_close is not None else None,
        'atr20': atr14,
        'day_range_pct': _safe_div(entry_range, entry_open),
        'range_vs_atr20': _safe_div(entry_range, atr14),
        'avg_volume_20d': avg_volume_20d,
        'relative_volume_20d': _safe_div(entry_volume, avg_volume_20d),
        'broke_entry_day_high_D1': None if d1 is None else bool(float(d1['high']) > entry_high),
        'broke_entry_day_low_D1': None if d1 is None else bool(float(d1['low']) < entry_low),
        'closed_higher_D1': None if d1 is None else bool(float(d1['close']) > entry_close),
        'broke_entry_day_high_within_3d': None if forward.empty else bool(max_forward_high > entry_high),
        'broke_entry_day_low_within_3d': None if forward.empty else bool(min_forward_low < entry_low),
        'max_gain_3d_pct': _safe_div(max_forward_high - entry_close, entry_close) if max_forward_high is not None else None,
        'max_drawdown_3d_pct': _safe_div(min_forward_low - entry_close, entry_close) if min_forward_low is not None else None,
    }
