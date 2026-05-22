from __future__ import annotations

import pandas as pd

from src.failure_timing import failure_timing_distribution


def test_failure_timing_uses_triggered_denominator_and_excludes_untriggered_rows():
    rows = pd.DataFrame([
        {'Ticker': 'ACT', 'Trigger Day': 'Success', 'Current Status': 'Active'},
        {'Ticker': 'FAIL', 'Trigger Day': 'Fail', 'Current Status': '-'},
        {'Ticker': 'NO', 'Trigger Day': 'Unresolved', 'Current Status': '-'},
        {'Ticker': 'BLANK', 'Trigger Day': '', 'Current Status': 'Active'},
    ])

    out = failure_timing_distribution(rows).iloc[0]

    assert out['Triggered'] == 2
    assert out['Active'] == 1
    assert out['D0 Fail'] == 1
    assert out['Active %'] == '50%'
    assert out['D0 Fail %'] == '50%'


def test_failure_timing_dedupes_d0_fail_per_row():
    rows = pd.DataFrame([
        {'Trigger Day': 'Fail', 'Current Status': 'Failed D0'},
        {'Trigger Day': 'Success', 'Current Status': 'Failed D0'},
    ])

    out = failure_timing_distribution(rows).iloc[0]

    assert out['Triggered'] == 2
    assert out['D0 Fail'] == 2
    assert out['D0 Fail %'] == '100%'


def test_failure_timing_classifies_d1_d2_d3_after_d3_active_and_unresolved():
    rows = pd.DataFrame([
        {'Trigger Day': 'Success', 'Current Status': 'Failed D1'},
        {'Trigger Day': 'Success', 'Current Status': 'Failed D2'},
        {'Trigger Day': 'Success', 'Current Status': 'Failed D3'},
        {'Trigger Day': 'Success', 'Current Status': 'Failed D4'},
        {'Trigger Day': 'Success', 'Current Status': 'Failed D12'},
        {'Trigger Day': 'Success', 'Current Status': 'Failed After D3'},
        {'Trigger Day': 'Success', 'Current Status': 'Active'},
        {'Trigger Day': 'Success', 'Current Status': 'Later Failed'},
    ])

    out = failure_timing_distribution(rows).iloc[0]

    assert out['Triggered'] == 8
    assert out['D1 Fail'] == 1
    assert out['D2 Fail'] == 1
    assert out['D3 Fail'] == 1
    assert out['Failed After D3'] == 3
    assert out['Active'] == 1
    assert out['Unresolved'] == 1
    assert out['D1 Fail %'] == '12%'
    assert out['Failed After D3 %'] == '38%'


def test_failure_timing_groups_by_column_and_omits_zero_trigger_groups():
    rows = pd.DataFrame([
        {'Trigger': '1m ORH', 'Trigger Day': 'Success', 'Current Status': 'Active'},
        {'Trigger': '1m ORH', 'Trigger Day': 'Fail', 'Current Status': '-'},
        {'Trigger': 'VWAP Reclaim', 'Trigger Day': 'Success', 'Current Status': 'Failed D2'},
        {'Trigger': 'No Trigger', 'Trigger Day': 'Unresolved', 'Current Status': '-'},
    ])

    out = failure_timing_distribution(rows, group_by='Trigger').set_index('Trigger')

    assert out.loc['1m ORH', 'Triggered'] == 2
    assert out.loc['1m ORH', 'Active %'] == '50%'
    assert out.loc['1m ORH', 'D0 Fail %'] == '50%'
    assert out.loc['VWAP Reclaim', 'Triggered'] == 1
    assert out.loc['VWAP Reclaim', 'D2 Fail %'] == '100%'
    assert 'No Trigger' not in out.index


def test_failure_timing_empty_dataset_renders_safely():
    out = failure_timing_distribution(pd.DataFrame()).iloc[0]

    assert out['Triggered'] == 0
    assert out['Active %'] == '-'
    assert out['D0 Fail %'] == '-'
