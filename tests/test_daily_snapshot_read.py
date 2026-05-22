from __future__ import annotations

import pandas as pd

from src.daily_snapshot_read import (
    daily_snapshot_day_read_metrics,
    daily_snapshot_status_counts,
    daily_snapshot_trigger_read_groups,
    trigger_other_bucket_counts,
)


def test_day_read_counts_trigger_day_fail_as_d0_fail():
    rows = pd.DataFrame([
        {'Trigger Day': 'Success', 'Current Status': 'Active', 'Close < BE': 'No', 'Retests': 'D1'},
        {'Trigger Day': 'Fail', 'Current Status': '', 'Close < BE': 'No', 'Retests': ''},
    ])

    counts = daily_snapshot_status_counts(rows)

    assert counts['total'] == 2
    assert counts['active'] == 1
    assert counts['failed_d0'] == 1


def test_day_read_counts_failed_d0_status_and_dedupes_same_row():
    rows = pd.DataFrame([
        {'Trigger Day': 'Fail', 'Current Status': 'Failed D0', 'Close < BE': 'No', 'Retests': ''},
        {'Trigger Day': 'Success', 'Current Status': 'Failed D0', 'Close < BE': 'No', 'Retests': ''},
    ])

    counts = daily_snapshot_status_counts(rows)

    assert counts['failed_d0'] == 2


def test_day_read_failed_after_d0_counts_only_failed_d1_plus():
    rows = pd.DataFrame([
        {'Trigger Day': 'Success', 'Current Status': 'Failed D1', 'Close < BE': 'No', 'Retests': ''},
        {'Trigger Day': 'Success', 'Current Status': 'Failed D12', 'Close < BE': 'No', 'Retests': ''},
        {'Trigger Day': 'Success', 'Current Status': 'Failed D0', 'Close < BE': 'No', 'Retests': ''},
        {'Trigger Day': 'Success', 'Current Status': 'Later Failed', 'Close < BE': 'No', 'Retests': ''},
    ])

    counts = daily_snapshot_status_counts(rows)

    assert counts['failed_after_d0'] == 2


def test_day_read_metrics_exclude_median_current_and_median_max():
    rows = pd.DataFrame([
        {'Current Status': 'Active', 'Trigger Day': 'Success', 'Close < BE': 'No', 'Retests': 'D0', 'D3 High %': '12.0%', 'Current %': '5.0%', 'Max %': '20.0%'},
        {'Current Status': 'Active', 'Trigger Day': 'Success', 'Close < BE': 'Yes', 'Retests': '', 'D3 High %': '16.0%', 'Current %': '7.0%', 'Max %': '22.0%'},
    ])

    metrics = daily_snapshot_day_read_metrics(rows)
    labels = [label for label, _ in metrics]

    assert 'Median Current' not in labels
    assert 'Median Max' not in labels
    assert ('Median D3 High', '14.0%') in metrics
    assert ('Close < BE', '1 / 50%') in metrics
    assert ('Retested', '1 / 50%') in metrics


def test_day_read_median_d3_high_uses_only_eligible_rows():
    rows = pd.DataFrame([
        {'Current Status': 'Failed D0', 'Trigger Day': 'Success', 'Close < BE': 'No', 'Retests': '', 'D3 High %': '30.0%'},
        {'Current Status': 'Failed D1', 'Trigger Day': 'Success', 'Close < BE': 'No', 'Retests': '', 'D3 High %': '40.0%'},
        {'Current Status': 'Failed D2', 'Trigger Day': 'Success', 'Close < BE': 'No', 'Retests': '', 'D3 High %': '50.0%'},
        {'Current Status': 'Failed D3', 'Trigger Day': 'Success', 'Close < BE': 'No', 'Retests': '', 'D3 High %': '60.0%'},
        {'Current Status': 'Active', 'Trigger Day': 'Success', 'Close < BE': 'No', 'Retests': '', 'D3 High %': '10.0%'},
        {'Current Status': 'Failed D4', 'Trigger Day': 'Success', 'Close < BE': 'No', 'Retests': '', 'D3 High %': '20.0%'},
        {'Current Status': 'Active', 'Trigger Day': 'Unresolved', 'Close < BE': 'No', 'Retests': '', 'D3 High %': '80.0%'},
    ])

    metrics = daily_snapshot_day_read_metrics(rows)

    assert ('Median D3 High', '15.0%') in metrics


def test_trigger_read_suppresses_empty_other():
    rows = pd.DataFrame([
        {'PDH': 'success', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'PDH', 'Trigger Day': 'Success'},
    ])

    groups = daily_snapshot_trigger_read_groups(rows)

    assert ('PDH', '100% (1/1 attempts)') in groups
    assert not any(label == 'Untriggered' for label, _ in groups)


def test_trigger_read_other_counts_unresolved_no_trigger_once():
    rows = pd.DataFrame([
        {'Ticker': 'ICHR', 'PDH': '', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'No Trigger', 'Trigger Day': 'Unresolved'},
    ])

    groups = daily_snapshot_trigger_read_groups(rows)
    other = trigger_other_bucket_counts(rows)

    assert other == {'Alt Required': 0, 'Unresolved': 1, 'No Trigger': 0}
    assert ('Untriggered', '1 unresolved') in groups
    assert not any(text == '1 no trigger / 1 unresolved' for _, text in groups)


def test_trigger_read_other_precedence_and_trigger_counts():
    rows = pd.DataFrame([
        {'PDH': 'success', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'PDH', 'Trigger Day': 'Success'},
        {'PDH': '', 'VWAP Reclaim': 'success', '1m ORH': '', '5m ORH': '', 'Trigger': 'VWAP Reclaim', 'Trigger Day': 'Success'},
        {'PDH': '', 'VWAP Reclaim': '', '1m ORH': 'success', '5m ORH': '', 'Trigger': '1m ORH', 'Trigger Day': 'Success'},
        {'PDH': '', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': 'success', 'Trigger': '5m ORH', 'Trigger Day': 'Success'},
        {'PDH': '', 'VWAP Reclaim': '', '1m ORH': 'failed', '5m ORH': 'failed', 'Trigger': 'Alt Required', 'Trigger Day': 'Success'},
        {'PDH': '', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'No Trigger', 'Trigger Day': 'Unresolved'},
        {'PDH': '', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'No Trigger', 'Trigger Day': ''},
    ])

    groups = dict(daily_snapshot_trigger_read_groups(rows))
    other = trigger_other_bucket_counts(rows)

    assert groups['PDH'] == '100% (1/1 attempts)'
    assert groups['VWAP Reclaim'] == '100% (1/1 attempts)'
    assert groups['1m ORH'] == '50% (1/2 attempts)'
    assert groups['5m ORH'] == '50% (1/2 attempts)'
    assert groups['Untriggered'] == '1 alt required / 1 unresolved / 1 no trigger'
    assert other == {'Alt Required': 1, 'Unresolved': 1, 'No Trigger': 1}


def test_trigger_read_rates_and_suppression():
    rows = pd.DataFrame([
        {'PDH': '', 'VWAP Reclaim': 'success', '1m ORH': '', '5m ORH': '', 'Trigger': 'VWAP Reclaim', 'Trigger Day': 'Success'},
        {'PDH': '', 'VWAP Reclaim': 'success', '1m ORH': '', '5m ORH': '', 'Trigger': 'VWAP Reclaim', 'Trigger Day': 'Success'},
        {'PDH': '', 'VWAP Reclaim': 'success', '1m ORH': '', '5m ORH': '', 'Trigger': 'VWAP Reclaim', 'Trigger Day': 'Success'},
        {'PDH': '', 'VWAP Reclaim': '', '1m ORH': 'failed', '5m ORH': '', 'Trigger': 'Failed OR Trigger', 'Trigger Day': 'Fail'},
        {'PDH': 'success', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'PDH', 'Trigger Day': 'Success'},
        {'PDH': 'failed', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'Failed PDH Trigger', 'Trigger Day': 'Fail'},
        {'PDH': 'Gap', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'No Trigger', 'Trigger Day': 'Unresolved'},
    ])

    groups = dict(daily_snapshot_trigger_read_groups(rows))

    assert groups['VWAP Reclaim'] == '100% (3/3 attempts)'
    assert groups['1m ORH'] == '0% (0/1 attempts)'
    assert groups['PDH'] == '50% (1/2 attempts) / 1 gap'
    assert '5m ORH' not in groups
    assert groups['Untriggered'] == '1 unresolved'
