from __future__ import annotations

import pandas as pd

from src.daily_snapshot_read import (
    daily_snapshot_day_read_metrics,
    daily_snapshot_status_counts,
    daily_snapshot_trigger_read_groups,
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


def test_trigger_read_suppresses_empty_other():
    rows = pd.DataFrame([
        {'PDH': 'success', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'PDH', 'Trigger Day': 'Success'},
    ])

    groups = daily_snapshot_trigger_read_groups(rows)

    assert ('PDH', '1 success') in groups
    assert not any(label == 'Other' for label, _ in groups)


def test_trigger_read_includes_notable_other():
    rows = pd.DataFrame([
        {'PDH': '', 'VWAP Reclaim': '', '1m ORH': '', '5m ORH': '', 'Trigger': 'No Trigger', 'Trigger Day': 'Unresolved'},
    ])

    groups = daily_snapshot_trigger_read_groups(rows)

    assert ('Other', '1 no trigger / 1 unresolved') in groups
