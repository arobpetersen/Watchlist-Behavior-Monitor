import pandas as pd

from src.feature_engine import opening_range


def test_opening_range_1m_break():
    ts = pd.date_range('2026-05-01 09:30', periods=3, freq='min')
    df = pd.DataFrame({'timestamp_et': ts, 'open': [10, 10, 10], 'high': [10, 11, 10], 'low': [9, 9, 9], 'close': [10, 10, 10], 'volume': [100, 100, 100]})
    assert opening_range(df, 1)['broke_orh'] is True
