import pandas as pd

from src.feature_engine import opening_range


def test_opening_range_1m_break():
    ts = pd.date_range('2026-05-01 09:30', periods=3, freq='min')
    df = pd.DataFrame({'timestamp_et': ts, 'open': [10, 10, 10], 'high': [10, 11, 10], 'low': [9, 9, 9], 'close': [10, 10, 10], 'volume': [100, 100, 100]})
    assert opening_range(df, 1)['broke_orh'] is True


def test_opening_range_uses_strict_greater_than_for_orh_break():
    ts = pd.date_range('2026-05-01 09:30', periods=3, freq='min')
    df = pd.DataFrame({'timestamp_et': ts, 'open': [10, 10, 10], 'high': [10, 10, 10.01], 'low': [9, 9.5, 9.5], 'close': [10, 10, 10], 'volume': [100, 100, 100]})

    out = opening_range(df, 1)

    assert out['broke_orh'] is True
    assert out['orh_break_time'] == '2026-05-01 09:32:00'


def test_opening_range_equal_high_does_not_count_as_orh_break():
    ts = pd.date_range('2026-05-01 09:30', periods=2, freq='min')
    df = pd.DataFrame({'timestamp_et': ts, 'open': [10, 10], 'high': [10, 10], 'low': [9, 9.5], 'close': [10, 10], 'volume': [100, 100]})

    assert opening_range(df, 1)['broke_orh'] is False


def test_opening_range_uses_strict_less_than_for_orl_break():
    ts = pd.date_range('2026-05-01 09:30', periods=3, freq='min')
    df = pd.DataFrame({'timestamp_et': ts, 'open': [10, 10, 10], 'high': [10, 9.8, 9.8], 'low': [9, 9, 8.99], 'close': [10, 9.5, 9.2], 'volume': [100, 100, 100]})

    out = opening_range(df, 1)

    assert out['broke_orl'] is True
    assert out['orl_break_time'] == '2026-05-01 09:32:00'


def test_opening_range_equal_low_does_not_count_as_orl_break():
    ts = pd.date_range('2026-05-01 09:30', periods=2, freq='min')
    df = pd.DataFrame({'timestamp_et': ts, 'open': [10, 10], 'high': [10, 9.8], 'low': [9, 9], 'close': [10, 9.5], 'volume': [100, 100]})

    assert opening_range(df, 1)['broke_orl'] is False


def test_opening_range_same_bar_breaks_both_sides_marks_ambiguity():
    ts = pd.date_range('2026-05-01 09:30', periods=2, freq='min')
    df = pd.DataFrame({'timestamp_et': ts, 'open': [10, 10], 'high': [10, 10.1], 'low': [9, 8.9], 'close': [10, 9.5], 'volume': [100, 100]})

    out = opening_range(df, 1)

    assert out['broke_orh'] is True
    assert out['broke_orl'] is True
    assert out['same_bar_orh_orl_break'] is True
    assert out['orh_then_orl'] is False
