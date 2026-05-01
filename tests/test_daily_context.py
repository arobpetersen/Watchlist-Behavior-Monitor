from __future__ import annotations

import pandas as pd
import pytest

from src.daily_context import calculate_daily_context


def test_daily_context_atr_rvol_gap_and_forward_stats():
    rows = []
    for d in pd.bdate_range('2026-04-02', periods=20):
        rows.append({
            'ticker': 'AAPL',
            'trading_date': d.date().isoformat(),
            'open': 100,
            'high': 105,
            'low': 95,
            'close': 100,
            'volume': 1000,
        })
    rows.extend([
        {'ticker': 'AAPL', 'trading_date': '2026-04-30', 'open': 105, 'high': 115, 'low': 100, 'close': 110, 'volume': 2500},
        {'ticker': 'AAPL', 'trading_date': '2026-05-01', 'open': 111, 'high': 116, 'low': 104, 'close': 111, 'volume': 1300},
        {'ticker': 'AAPL', 'trading_date': '2026-05-04', 'open': 110, 'high': 114, 'low': 99, 'close': 100, 'volume': 1400},
        {'ticker': 'AAPL', 'trading_date': '2026-05-05', 'open': 112, 'high': 117, 'low': 105, 'close': 116, 'volume': 1500},
    ])

    metrics = calculate_daily_context(pd.DataFrame(rows), 'AAPL', '2026-04-30')

    assert metrics['prior_close'] == 100
    assert metrics['gap_pct'] == pytest.approx(0.05)
    assert metrics['atr20'] == pytest.approx(10)
    assert metrics['day_range_pct'] == pytest.approx(15 / 105)
    assert metrics['range_vs_atr20'] == pytest.approx(1.5)
    assert metrics['avg_volume_20d'] == pytest.approx(1000)
    assert metrics['relative_volume_20d'] == pytest.approx(2.5)
    assert metrics['broke_entry_day_high_D1'] is True
    assert metrics['broke_entry_day_low_D1'] is False
    assert metrics['closed_higher_D1'] is True
    assert metrics['broke_entry_day_high_within_3d'] is True
    assert metrics['broke_entry_day_low_within_3d'] is True
    assert metrics['max_gain_3d_pct'] == pytest.approx(7 / 110)
    assert metrics['max_drawdown_3d_pct'] == pytest.approx(-11 / 110)
