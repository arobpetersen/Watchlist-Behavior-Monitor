from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


MARKET_PROXY = 'QQQ'
UNAVAILABLE_TEXT = 'Market context unavailable for selected setup date.'


@dataclass(frozen=True)
class MarketContext:
    available: bool
    setup_date: str
    proxy: str = MARKET_PROXY
    pct_change: float | None = None
    gap_pct: float | None = None
    range_pct: float | None = None
    close_location: float | None = None
    atr14: float | None = None
    range_vs_atr14: float | None = None
    day_type: str = 'Unavailable'
    read: str = UNAVAILABLE_TEXT


def _safe_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric):
        return None
    return numeric


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _fmt_pct(value: float | None) -> str:
    return '-' if value is None or pd.isna(value) else f'{value * 100:+.1f}%'


def _fmt_num(value: float | None) -> str:
    return '-' if value is None or pd.isna(value) else f'{value:.2f}'


def _fmt_whole_pct(value: float | None) -> str:
    return '-' if value is None or pd.isna(value) else f'{value * 100:.0f}%'


def _fmt_atr_multiple(value: float | None) -> str:
    return '-' if value is None or pd.isna(value) else f'{value:.2f}x ATR(14)'


def market_move_label(pct_change: float | None) -> str:
    if pct_change is None or pd.isna(pct_change):
        return 'Flat / Mixed'
    if pct_change >= 0.0150:
        return 'Strong Up Day'
    if pct_change >= 0.0050:
        return 'Up Day'
    if pct_change <= -0.0150:
        return 'Strong Down Day'
    if pct_change <= -0.0050:
        return 'Down Day'
    return 'Flat / Mixed'


def _close_area(close_location: float | None) -> str:
    if close_location is None or pd.isna(close_location):
        return 'range unknown'
    if close_location >= 0.70:
        return 'near highs'
    if close_location <= 0.30:
        return 'near lows'
    if close_location <= 0.45:
        return 'mid/lower range'
    if close_location >= 0.55:
        return 'mid/upper range'
    return 'mid-range'


def _true_range(prior: pd.DataFrame) -> pd.Series:
    prev_close = prior['close'].shift(1)
    parts = pd.concat([
        prior['high'] - prior['low'],
        (prior['high'] - prev_close).abs(),
        (prior['low'] - prev_close).abs(),
    ], axis=1)
    return parts.max(axis=1, skipna=True)


def classify_market_day(
    pct_change: float | None,
    gap_pct: float | None,
    close_location: float | None,
    range_pct: float | None,
    range_vs_atr14: float | None = None,
) -> str:
    if pct_change is None or gap_pct is None or close_location is None or range_pct is None:
        return 'Mixed'

    volatile = range_vs_atr14 is not None and not pd.isna(range_vs_atr14) and range_vs_atr14 >= 1.20
    recovery = close_location >= 0.70 and (pct_change <= 0 or gap_pct <= -0.0050)
    fade = close_location <= 0.30 and (pct_change >= 0 or gap_pct >= 0.0050)
    if volatile and recovery:
        return 'Volatile Recovery'
    if recovery:
        return 'Recovery'
    if volatile and fade:
        return 'Volatile Fade'
    if fade:
        return 'Fade'
    if pct_change >= 0.0075 and close_location >= 0.70:
        return 'Trend Up'
    if pct_change <= -0.0075 and close_location <= 0.30:
        return 'Trend Down'
    if volatile and 0.35 <= close_location <= 0.65:
        return 'Volatile Chop'
    if range_vs_atr14 is not None and not pd.isna(range_vs_atr14):
        pass
    elif range_pct >= 0.0150 and 0.35 <= close_location <= 0.65:
        return 'Volatile Chop'
    if abs(pct_change) < 0.0040:
        if range_vs_atr14 is not None and not pd.isna(range_vs_atr14):
            if range_vs_atr14 < 0.80:
                return 'Quiet'
        elif range_pct < 0.0090:
            return 'Quiet'
    return 'Mixed'


def market_context_read(day_type: str, pct_change: float | None, close_location: float | None) -> str:
    if day_type == 'Trend Up':
        return f'QQQ {_fmt_pct(pct_change)}, closed near highs'
    if day_type == 'Trend Down':
        return f'QQQ {_fmt_pct(pct_change)}, closed near lows'
    if day_type == 'Volatile Recovery':
        return 'Wide range, strong recovery close'
    if day_type == 'Recovery':
        return 'Recovery close after pressure'
    if day_type == 'Volatile Fade':
        return 'Wide range, weak fade close'
    if day_type == 'Fade':
        return 'Fade into weak close'
    if day_type in {'Gap Up Fade', 'Gap Up Faded'}:
        return 'Gap up faded; QQQ closed mid/lower range'
    if day_type in {'Gap Down Reversal', 'Gap Down Recovered'}:
        return 'Gap down recovered; QQQ closed mid/upper range'
    if day_type in {'Volatile Chop', 'Choppy'}:
        return 'Wide range, mid-range close'
    if day_type in {'Quiet', 'Quiet / Inside'}:
        return 'Quiet index session'
    if day_type == 'Unavailable':
        return UNAVAILABLE_TEXT
    return f'QQQ {_fmt_pct(pct_change)}, closed {_close_area(close_location)}'


def calculate_market_context_from_daily_bars(daily_bars: pd.DataFrame, setup_date: str, proxy: str = MARKET_PROXY) -> MarketContext:
    setup_date_text = pd.to_datetime(setup_date).date().isoformat()
    if daily_bars is None or daily_bars.empty:
        return MarketContext(available=False, setup_date=setup_date_text, proxy=proxy)

    rows = daily_bars.copy()
    rows['ticker'] = rows['ticker'].astype(str).str.upper()
    rows = rows[rows['ticker'].eq(proxy.upper())].copy()
    if rows.empty:
        return MarketContext(available=False, setup_date=setup_date_text, proxy=proxy)

    rows['trading_date'] = pd.to_datetime(rows['trading_date'], errors='coerce').dt.date
    rows = rows.dropna(subset=['trading_date']).sort_values('trading_date').reset_index(drop=True)
    target_date = pd.to_datetime(setup_date).date()
    matches = rows[rows['trading_date'].eq(target_date)]
    if matches.empty:
        return MarketContext(available=False, setup_date=setup_date_text, proxy=proxy)

    idx = int(matches.index[0])
    if idx <= 0:
        return MarketContext(available=False, setup_date=setup_date_text, proxy=proxy)

    prior = rows.iloc[:idx].copy()
    bar = rows.loc[idx]
    previous_close = _safe_float(rows.loc[idx - 1, 'close'])
    open_price = _safe_float(bar.get('open'))
    high = _safe_float(bar.get('high'))
    low = _safe_float(bar.get('low'))
    close = _safe_float(bar.get('close'))
    if previous_close in (None, 0) or None in {open_price, high, low, close}:
        return MarketContext(available=False, setup_date=setup_date_text, proxy=proxy)

    day_range = high - low
    close_location = _safe_div(close - low, day_range)
    atr14 = None if prior.empty else _safe_float(_true_range(prior).tail(14).mean())
    range_vs_atr14 = _safe_div(day_range, atr14)
    pct_change = _safe_div(close - previous_close, previous_close)
    gap_pct = _safe_div(open_price - previous_close, previous_close)
    range_pct = _safe_div(day_range, previous_close)
    day_type = classify_market_day(pct_change, gap_pct, close_location, range_pct, range_vs_atr14)
    read = market_context_read(day_type, pct_change, close_location)

    return MarketContext(
        available=True,
        setup_date=setup_date_text,
        proxy=proxy,
        pct_change=pct_change,
        gap_pct=gap_pct,
        range_pct=range_pct,
        close_location=close_location,
        atr14=atr14,
        range_vs_atr14=range_vs_atr14,
        day_type=day_type,
        read=read,
    )


def _query_context_bars(con, setup_dates: list[str], proxy: str = MARKET_PROXY) -> pd.DataFrame:
    if not setup_dates:
        return pd.DataFrame()
    dates = sorted({pd.to_datetime(value).date().isoformat() for value in setup_dates})
    start_date = (pd.to_datetime(dates[0]) - pd.Timedelta(days=35)).date().isoformat()
    end_date = dates[-1]
    return con.execute(
        """
        select ticker, trading_date, open, high, low, close, volume
        from daily_bars
        where upper(ticker) = ?
          and trading_date between ? and ?
        order by trading_date
        """,
        [proxy.upper(), start_date, end_date],
    ).df()


def market_context_for_setup_date(con, setup_date: str, proxy: str = MARKET_PROXY) -> MarketContext:
    bars = _query_context_bars(con, [setup_date], proxy=proxy)
    return calculate_market_context_from_daily_bars(bars, setup_date, proxy=proxy)


def market_context_for_setup_dates(con, setup_dates: list[str], proxy: str = MARKET_PROXY) -> dict[str, MarketContext]:
    normalized = sorted({pd.to_datetime(value).date().isoformat() for value in setup_dates})
    bars = _query_context_bars(con, normalized, proxy=proxy)
    return {
        setup_date: calculate_market_context_from_daily_bars(bars, setup_date, proxy=proxy)
        for setup_date in normalized
    }


def format_market_context_strip(context: MarketContext) -> str:
    if not context.available:
        return UNAVAILABLE_TEXT
    return (
        f'{context.proxy} {_fmt_pct(context.pct_change)} | '
        f'{market_move_label(context.pct_change)} | '
        f'{context.day_type} | '
        f'Gap {_fmt_pct(context.gap_pct)} | '
        f'Close Position {_fmt_whole_pct(context.close_location)} | '
        f'Range {_fmt_atr_multiple(context.range_vs_atr14)}'
    )
