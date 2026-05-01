from __future__ import annotations

import pytest

from src.dashboard_queries import _or_result, _rating_bucket, _vwap_result


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
