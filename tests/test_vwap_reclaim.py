from __future__ import annotations

import pandas as pd

from src.vwap_reclaim import add_intraday_vwap, assess_vwap_reclaim, five_minute_bars_with_vwap


def _bars(date: str, rows: list[tuple[str, float, float, float, float, int]]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            'ticker': 'AAPL',
            'trading_date': date,
            'timestamp_et': f'{date} {time}',
            'open': open_,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
        }
        for time, open_, high, low, close, volume in rows
    ])


def _session_with_reclaim(
    reclaim_start: str = '10:00:00',
    reclaim_close: float = 11.0,
    reclaim_high: float = 11.2,
    later_high: float | None = 11.4,
) -> pd.DataFrame:
    rows = []
    for hour in [9, 10, 11, 12, 13, 14, 15]:
        start = 30 if hour == 9 else 0
        end = 60
        for minute in range(start, end):
            rows.append((f'{hour:02d}:{minute:02d}:00', 10.0, 10.1, 9.9, 10.0, 1000))
    reclaim_hour, reclaim_minute = [int(part) for part in reclaim_start.split(':')[:2]]
    for minute in range(reclaim_minute, reclaim_minute + 5):
        idx = next(i for i, row in enumerate(rows) if row[0] == f'{reclaim_hour:02d}:{minute:02d}:00')
        rows[idx] = (rows[idx][0], 10.6, reclaim_high, 10.5, reclaim_close, 1000)
    if later_high is not None:
        later_idx = next(i for i, row in enumerate(rows) if row[0] == '10:10:00')
        rows[later_idx] = ('10:10:00', 10.9, later_high, 10.8, 11.0, 1000)
    return _bars('2026-05-01', rows)


def test_vwap_calculation_from_synthetic_1m_bars():
    bars = _bars('2026-05-01', [
        ('09:30:00', 10, 11, 9, 10, 100),
        ('09:31:00', 20, 21, 19, 20, 100),
    ])

    out = add_intraday_vwap(bars)

    assert out['vwap'].round(2).tolist() == [10.0, 15.0]


def test_five_minute_bar_construction_from_1m_bars():
    bars = _bars('2026-05-01', [
        ('09:30:00', 10, 11, 9, 10.5, 100),
        ('09:31:00', 10.5, 12, 10, 11, 100),
        ('09:35:00', 11, 13, 10.8, 12, 100),
    ])

    out = five_minute_bars_with_vwap(bars)

    assert len(out) == 2
    assert str(out.loc[0, 'end_time']) == '2026-05-01 09:35:00'
    assert out.loc[0, 'high'] == 12
    assert out.loc[0, 'close'] == 11


def test_vwap_reclaim_ignored_before_10am():
    bars = _session_with_reclaim(reclaim_start='09:45:00', later_high=None)

    out = assess_vwap_reclaim(bars, min_regular_session_bars=300)

    assert out['result'] == ''


def test_vwap_reclaim_detected_between_10_and_1130():
    bars = _session_with_reclaim(reclaim_start='10:00:00')

    out = assess_vwap_reclaim(bars, min_regular_session_bars=300)

    assert out['result'] == 'success'
    assert out['reclaim_time'] == '2026-05-01 10:05:00'
    assert out['reclaim_bar_high'] == 11.2
    assert out['trigger_time'] == '2026-05-01 10:10:00'
    assert out['trigger_price'] == 11.2


def test_vwap_reclaim_ignored_after_1130():
    bars = _session_with_reclaim(reclaim_start='11:30:00', later_high=None)

    out = assess_vwap_reclaim(bars, min_regular_session_bars=300)

    assert out['result'] == ''


def test_vwap_reclaim_failed_when_reclaim_high_not_taken_out():
    bars = _session_with_reclaim(reclaim_start='10:00:00', later_high=11.1)

    out = assess_vwap_reclaim(bars, min_regular_session_bars=300)

    assert out['result'] == 'failed'
    assert out['failure_reason'] == 'reclaim-bar high not taken out'


def test_vwap_reclaim_blank_when_no_qualifying_close_above_vwap():
    bars = _session_with_reclaim(reclaim_start='10:00:00', reclaim_close=9.8, reclaim_high=10.1, later_high=None)

    out = assess_vwap_reclaim(bars, min_regular_session_bars=300)

    assert out['result'] == ''


def test_vwap_reclaim_ineligible_when_intraday_missing():
    out = assess_vwap_reclaim(pd.DataFrame())

    assert out['result'] == 'Not Applicable'
    assert out['failure_reason'] == 'missing intraday bars'


def test_vwap_reclaim_ineligible_when_intraday_partial():
    bars = _bars('2026-05-01', [
        ('10:00:00', 10, 11, 10, 11, 1000),
        ('10:05:00', 11, 12, 11, 12, 1000),
    ])

    out = assess_vwap_reclaim(bars, min_regular_session_bars=300)

    assert out['result'] == 'Not Applicable'
    assert out['failure_reason'] == 'partial intraday data'
