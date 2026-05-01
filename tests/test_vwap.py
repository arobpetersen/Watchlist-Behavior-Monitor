import pandas as pd

from src.feature_engine import calc_vwap


def test_vwap():
    df = pd.DataFrame({'high': [11, 12], 'low': [9, 10], 'close': [10, 11], 'volume': [100, 100]})
    assert round(float(calc_vwap(df).iloc[-1]), 2) == 10.5
