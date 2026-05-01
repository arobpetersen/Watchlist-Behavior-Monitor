from __future__ import annotations

import pytest

from src.dashboard_queries import _clean_display_value, _close_bucket, _or_result, _rating_bucket, _vwap_result


@pytest.mark.parametrize(
    ('payload', 'expected'),
    [
        ('{}', 'No Break'),
        ('{"broke_orh": true, "closed_above_orh": true}', 'Held'),
        ('{"broke_orh": true, "orh_then_orl": true}', 'Failed'),
        ('{"broke_orl": true, "closed_below_orl": true}', 'Failed'),
    ],
)
def test_or_result_formatting(payload, expected):
    assert _or_result(payload) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (True, 'Above VWAP'),
        (False, 'Below VWAP'),
        (None, 'No Data'),
    ],
)
def test_vwap_result_formatting(value, expected):
    assert _vwap_result(value) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (5, '4+'),
        (3.5, '3 to <4'),
        (2.5, '2 to <3'),
        (1, '<2'),
        (None, 'No Rating'),
    ],
)
def test_rating_bucket_formatting(value, expected):
    assert _rating_bucket(value) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (0.90, 'Top 20%'),
        (0.70, 'Upper Half'),
        (0.50, 'Middle'),
        (0.30, 'Lower Half'),
        (0.10, 'Bottom 20%'),
        (None, ''),
    ],
)
def test_close_bucket_formatting(value, expected):
    assert _close_bucket(value) == expected


def test_clean_display_value_hides_missing_values():
    assert _clean_display_value(None) == ''
    assert _clean_display_value(float('nan')) == ''
    assert _clean_display_value('nan') == ''
    assert _clean_display_value('setup') == 'setup'
