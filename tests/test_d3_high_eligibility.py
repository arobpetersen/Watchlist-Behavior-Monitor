from __future__ import annotations

import pandas as pd

from src.d3_high_eligibility import d3_high_eligible_mask, eligible_d3_high_pct


def test_d3_high_eligibility_excludes_failed_before_or_on_d3_and_unresolved():
    rows = pd.DataFrame([
        {'Ticker': 'D0', 'Current Status': 'Failed D0', 'Trigger Day': 'Success', 'd3_high_pct_raw': 0.20},
        {'Ticker': 'TRIGFAIL', 'Current Status': '-', 'Trigger Day': 'Fail', 'd3_high_pct_raw': 0.30},
        {'Ticker': 'D1', 'Current Status': 'Failed D1', 'Trigger Day': 'Success', 'd3_high_pct_raw': 0.40},
        {'Ticker': 'D2', 'Current Status': 'Failed D2', 'Trigger Day': 'Success', 'd3_high_pct_raw': 0.50},
        {'Ticker': 'D3', 'Current Status': 'Failed D3', 'Trigger Day': 'Success', 'd3_high_pct_raw': 0.60},
        {'Ticker': 'UNRES', 'Current Status': 'Active', 'Trigger Day': 'Unresolved', 'd3_high_pct_raw': 0.70},
    ])

    assert d3_high_eligible_mask(rows).tolist() == [False, False, False, False, False, False]
    assert eligible_d3_high_pct(rows).dropna().empty


def test_d3_high_eligibility_includes_active_and_failed_d4_rows():
    rows = pd.DataFrame([
        {'Ticker': 'ACT', 'Current Status': 'Active', 'Trigger Day': 'Success', 'd3_high_pct_raw': 0.10},
        {'Ticker': 'D4', 'Current Status': 'Failed D4', 'Trigger Day': 'Success', 'd3_high_pct_raw': 0.20},
        {'Ticker': 'NOD3', 'Current Status': 'Active', 'Trigger Day': 'Success', 'd3_high_pct_raw': None},
    ])

    assert d3_high_eligible_mask(rows).tolist() == [True, True, False]
    assert round(float(eligible_d3_high_pct(rows).dropna().median()), 4) == 0.15
