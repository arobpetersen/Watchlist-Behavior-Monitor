from __future__ import annotations

import json

import pandas as pd

from src.rolling_setup_monitor import (
    display_status,
    display_trigger,
    current_status,
    derive_trigger_reference,
    sort_monitor_rows,
)


def _or(**kwargs):
    return json.dumps(kwargs)


def test_clean_1m_orh_trigger_selection():
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=False, orh_then_orl=False, orh=10.5),
        _or(broke_orh=True, broke_orl=False, orh=11.0),
        _or(orh=12.0),
        0.5,
    )

    assert out['trigger_reference_type'] == 'Clean 1m ORH'
    assert out['trigger_reference_price'] == 10.5
    assert out['trigger_reference_basis'] == '1m ORH'


def test_clean_5m_orh_fallback_when_1m_fails():
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=10.5),
        _or(broke_orh=True, broke_orl=False, orh_then_orl=False, orh=11.0),
        _or(orh=12.0),
        0.5,
    )

    assert out['trigger_reference_type'] == 'Clean 5m ORH'
    assert out['trigger_reference_price'] == 11.0
    assert out['trigger_reference_basis'] == '5m ORH'


def test_alternate_means_uses_15m_reference():
    out = derive_trigger_reference(
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=10.5),
        _or(broke_orh=True, broke_orl=True, orh_then_orl=True, orh=11.0),
        _or(orh=12.0),
        0.85,
    )

    assert out['trigger_reference_type'] == 'Alternate Means Required'
    assert out['trigger_reference_price'] == 12.0
    assert out['trigger_reference_basis'] == '15m ORH Reference'


def test_no_clean_or_trigger():
    out = derive_trigger_reference(
        _or(broke_orh=False, broke_orl=True),
        _or(broke_orh=False, broke_orl=True),
        _or(orh=12.0),
        0.4,
    )

    assert out['trigger_reference_type'] == 'No Clean OR Trigger'
    assert out['trigger_reference_price'] is None


def test_current_status_failed_setup_day_low():
    assert current_status(True, True, 11.0, 12.0, 10.0, 'Clean 1m ORH') == 'Failed Setup-Day Low'


def test_current_status_trending_higher():
    assert current_status(False, True, 12.5, 12.0, 10.0, 'Clean 1m ORH') == 'Trending Higher'


def test_current_status_still_working():
    assert current_status(False, False, 10.5, 12.0, 10.0, 'Clean 1m ORH') == 'Still Working'


def test_current_status_pulled_back_but_holding():
    assert current_status(False, False, 9.8, 12.0, 10.0, 'Clean 1m ORH') == 'Pulled Back but Holding'


def test_display_prefixes():
    assert display_trigger('Clean 1m ORH').startswith('[Clean]')
    assert display_trigger('Clean 5m ORH').startswith('[Clean]')
    assert display_trigger('Alternate Means Required').startswith('[Alt]')
    assert display_trigger('No Clean OR Trigger').startswith('[None]')
    assert display_status('Trending Higher').startswith('[Up]')
    assert display_status('Failed Setup-Day Low').startswith('[Fail]')


def test_sort_monitor_rows_status_then_current_setup_return():
    df = pd.DataFrame([
        {'Ticker': 'FAIL', 'Status': 'Failed Setup-Day Low', 'Current % from Setup Close': 0.50},
        {'Ticker': 'PULL', 'Status': 'Pulled Back but Holding', 'Current % from Setup Close': 0.30},
        {'Ticker': 'TREND2', 'Status': 'Trending Higher', 'Current % from Setup Close': 0.10},
        {'Ticker': 'TREND1', 'Status': 'Trending Higher', 'Current % from Setup Close': 0.20},
        {'Ticker': 'WORK', 'Status': 'Still Working', 'Current % from Setup Close': 0.40},
    ])

    out = sort_monitor_rows(df)

    assert out['Ticker'].tolist() == ['TREND1', 'TREND2', 'WORK', 'PULL', 'FAIL']
