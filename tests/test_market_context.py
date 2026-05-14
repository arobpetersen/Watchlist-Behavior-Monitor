from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.market_context import (
    UNAVAILABLE_TEXT,
    calculate_market_context_from_daily_bars,
    classify_market_day,
    format_market_context_strip,
    market_move_label,
)


def _bars(target: dict | None = None, ticker: str = 'QQQ') -> pd.DataFrame:
    rows = []
    for idx in range(14):
        close = 100 + idx
        rows.append({
            'ticker': ticker,
            'trading_date': pd.Timestamp('2026-04-01') + pd.Timedelta(days=idx),
            'open': close - 0.5,
            'high': close + 1.0,
            'low': close - 1.0,
            'close': close,
            'volume': 1000,
        })
    rows.append(target or {
        'ticker': ticker,
        'trading_date': '2026-04-15',
        'open': 114.5,
        'high': 118.0,
        'low': 113.0,
        'close': 117.0,
        'volume': 1200,
    })
    return pd.DataFrame(rows)


def test_calculates_qqq_change_gap_and_close_location():
    context = calculate_market_context_from_daily_bars(_bars(), '2026-04-15')

    assert context.available is True
    assert context.pct_change == pytest.approx((117.0 / 113.0) - 1)
    assert context.gap_pct == pytest.approx((114.5 / 113.0) - 1)
    assert context.range_pct == pytest.approx((118.0 - 113.0) / 113.0)
    assert context.close_location == pytest.approx((117.0 - 113.0) / (118.0 - 113.0))
    assert context.atr14 == pytest.approx(2.0)
    assert context.range_vs_atr14 == pytest.approx(2.5)


def test_atr14_uses_prior_14_completed_days_and_excludes_setup_date():
    rows = []
    start = pd.Timestamp('2026-04-01')
    rows.append({
        'ticker': 'QQQ',
        'trading_date': start,
        'open': 100.0,
        'high': 101.0,
        'low': 99.0,
        'close': 100.0,
        'volume': 1000,
    })
    rows.append({
        'ticker': 'QQQ',
        'trading_date': start + pd.Timedelta(days=1),
        'open': 129.5,
        'high': 130.0,
        'low': 129.0,
        'close': 129.5,
        'volume': 1000,
    })
    for idx in range(2, 15):
        close = 129.5 + idx
        rows.append({
            'ticker': 'QQQ',
            'trading_date': start + pd.Timedelta(days=idx),
            'open': close,
            'high': close + 1.0,
            'low': close - 1.0,
            'close': close,
            'volume': 1000,
        })
    rows.append({
        'ticker': 'QQQ',
        'trading_date': '2026-04-16',
        'open': 144.0,
        'high': 244.0,
        'low': 144.0,
        'close': 144.0,
        'volume': 1000,
    })

    context = calculate_market_context_from_daily_bars(pd.DataFrame(rows), '2026-04-16')

    expected_prior_trs = [30.0, 3.0] + [2.0] * 12
    assert context.atr14 == pytest.approx(sum(expected_prior_trs) / 14)
    assert context.range_vs_atr14 == pytest.approx(100.0 / context.atr14)


def test_handles_high_equals_low_safely():
    context = calculate_market_context_from_daily_bars(
        _bars({'ticker': 'QQQ', 'trading_date': '2026-04-15', 'open': 113.0, 'high': 113.0, 'low': 113.0, 'close': 113.0, 'volume': 1200}),
        '2026-04-15',
    )

    assert context.available is True
    assert context.close_location is None
    assert context.day_type == 'Mixed'
    assert 'Close Position -' in format_market_context_strip(context)


@pytest.mark.parametrize(
    ('pct_change', 'gap_pct', 'close_location', 'range_pct', 'range_vs_atr14', 'expected'),
    [
        (0.010, 0.002, 0.80, 0.012, 1.00, 'Trend Up'),
        (-0.010, -0.002, 0.20, 0.012, 1.00, 'Trend Down'),
        (-0.008, -0.007, 0.78, 0.018, 1.38, 'Volatile Recovery'),
        (-0.004, -0.006, 0.74, 0.010, 1.00, 'Recovery'),
        (0.004, 0.006, 0.22, 0.018, 1.30, 'Volatile Fade'),
        (0.004, 0.006, 0.22, 0.010, 1.00, 'Fade'),
        (0.002, 0.000, 0.50, 0.020, 1.25, 'Volatile Chop'),
        (0.001, 0.000, 0.50, 0.006, 0.70, 'Quiet'),
    ],
)
def test_classifies_market_day_types(pct_change, gap_pct, close_location, range_pct, range_vs_atr14, expected):
    assert classify_market_day(pct_change, gap_pct, close_location, range_pct, range_vs_atr14) == expected


def test_volatile_recovery_can_still_finish_negative():
    day_type = classify_market_day(
        pct_change=-0.008,
        gap_pct=-0.007,
        close_location=0.78,
        range_pct=0.018,
        range_vs_atr14=1.38,
    )

    assert day_type == 'Volatile Recovery'


def test_classifies_choppy_and_quiet_without_atr_fallbacks():
    assert classify_market_day(0.002, 0.000, 0.50, 0.016, None) == 'Volatile Chop'
    assert classify_market_day(0.001, 0.000, 0.50, 0.008, None) == 'Quiet'


def test_market_context_strip_uses_clear_close_position_and_range_labels():
    context = calculate_market_context_from_daily_bars(_bars(), '2026-04-15')

    strip = format_market_context_strip(context)

    assert 'QQQ +3.5%' in strip
    assert 'Gap +1.3%' in strip
    assert 'Close Position 80%' in strip
    assert 'Close Loc' not in strip
    assert 'Range 2.50x ATR(14)' in strip
    assert 'Range/ATR' not in strip


@pytest.mark.parametrize(
    ('pct_change', 'expected'),
    [
        (0.0150, 'Strong Up Day'),
        (0.0050, 'Up Day'),
        (0.0049, 'Flat / Mixed'),
        (-0.0049, 'Flat / Mixed'),
        (-0.0050, 'Down Day'),
        (-0.0150, 'Strong Down Day'),
    ],
)
def test_market_move_labels(pct_change, expected):
    assert market_move_label(pct_change) == expected


def test_missing_qqq_data_returns_stable_unavailable_output():
    context = calculate_market_context_from_daily_bars(_bars(ticker='SPY'), '2026-04-15')

    assert context.available is False
    assert context.read == UNAVAILABLE_TEXT
    assert format_market_context_strip(context) == UNAVAILABLE_TEXT


def test_daily_snapshot_page_renders_market_context_strip_from_local_helper():
    page = (Path(__file__).resolve().parents[1] / 'pages' / '1_Daily_Snapshot.py').read_text()

    assert 'market_context_for_setup_date(con, d)' in page
    assert '_market_context_panel(market_context)' in page
    assert 'Close Position' in page
    assert 'x ATR(14)' in page
    assert 'fetch_daily' not in page


def test_rolling_monitor_page_renders_market_context_strip_for_rendered_dates():
    page = (Path(__file__).resolve().parents[1] / 'pages' / '3_Rolling_Setup_Monitor.py').read_text()

    assert "market_context_for_setup_dates(con, [section['setup_date'] for section in sections])" in page
    assert '_market_context_banner(market_context)' in page
    assert 'day-type-chip' in page
    assert 'Close Position' in page
    assert 'Range' in page
    assert 'Range/ATR' not in page
    assert 'fetch_daily' not in page
