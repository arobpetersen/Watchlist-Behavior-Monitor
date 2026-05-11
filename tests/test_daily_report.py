from __future__ import annotations

import pandas as pd

from src.daily_report import (
    build_daily_report_payload,
    build_llm_report_prompt,
    render_daily_report_markdown,
)
from src.setup_behavior_overview import (
    overview_windows,
    trigger_event_shift_highlights,
    trigger_outcome_comparison,
)


def _report_history() -> pd.DataFrame:
    rows = []
    dates = pd.date_range('2026-05-01', periods=10, freq='D')
    for idx, date in enumerate(dates):
        recent = idx >= 5
        ticker = f'T{idx}'
        current = 0.03 + (idx * 0.01)
        max_pct = 0.08 + (idx * 0.02)
        trigger_result = 'failed' if recent and idx < 8 else 'success'
        trigger_day = 'Fail' if trigger_result == 'failed' else 'Success'
        status = '—' if trigger_day == 'Fail' else 'Active'
        if idx == 8:
            status = 'Failed D2'
        rows.append({
            'Setup Date': date.date().isoformat(),
            'Ticker': ticker,
            'Current Status': status,
            'Trigger Day': trigger_day,
            'Trigger': '1m ORH',
            '1m ORH': trigger_result,
            '5m ORH': '-',
            'VWAP Reclaim': '-',
            'PDH': '-',
            'Current %': f'{current * 100:.1f}%',
            'Max %': f'{max_pct * 100:.1f}%',
            'Close < BE': 'Yes' if idx == 9 else 'No',
            'Retests': 'D0' if idx == 5 else 'D1' if idx in {6, 8} else '',
            'Rating': '5' if idx == 9 else '4',
            'Setup': 'Pullback',
            'Entry Tactic': 'Reclaim',
            'Latest Status Date': '2026-05-10',
            'current_pct_raw': current,
            'max_pct_raw': max_pct,
        })
    return pd.DataFrame(rows)


def _overview(history: pd.DataFrame) -> dict:
    windows = overview_windows(history['Setup Date'])
    history_by_window = {}
    for window in windows:
        included = {date.date() for date in window.setup_dates}
        dates = pd.to_datetime(history['Setup Date'], errors='coerce')
        history_by_window[window.label] = history[dates.dt.date.isin(included)].copy()
    comparison = trigger_outcome_comparison(history_by_window)
    return {
        'windows': windows,
        'trigger_outcome_comparison': comparison,
        'trigger_event_shift_highlights': trigger_event_shift_highlights(comparison),
    }


def test_daily_report_payload_includes_latest_setup_date_summary():
    history = _report_history()
    payload = build_daily_report_payload(history, _overview(history))

    latest = payload['latest_setup_date_summary']

    assert latest['latest_setup_date'] == '2026-05-10'
    assert latest['setup_count'] == 1
    assert latest['active']['count'] == 1
    assert latest['close_below_be']['count'] == 1


def test_daily_report_payload_includes_last5_and_previous5_summaries():
    history = _report_history()
    payload = build_daily_report_payload(history, _overview(history))

    windows = payload['recent_window_summary']

    assert {'Last 5 Setup Dates', 'Previous 5 Setup Dates'}.issubset(windows)
    assert windows['Last 5 Setup Dates']['setup_count'] == 5
    assert windows['Previous 5 Setup Dates']['setup_count'] == 5
    assert windows['Last 5 Setup Dates']['failed_d0_pct'] == 60.0


def test_daily_report_payload_includes_trigger_failure_rates_and_shifts():
    history = _report_history()
    payload = build_daily_report_payload(history, _overview(history))

    failure_rates = payload['trigger_summary']['failure_rates']
    shifts = payload['trigger_summary']['notable_shifts']

    assert any(item['window'] == 'Last 5 Setup Dates' and item['trigger'] == '1m ORH' and item['fail_pct'] == '60%' for item in failure_rates)
    assert any(item['trigger'] == '1m ORH' and item['metric'] == 'Failed' for item in shifts)


def test_daily_report_payload_includes_top_active_names():
    history = _report_history()
    payload = build_daily_report_payload(history, _overview(history))

    names = payload['notable_tickers']['top_active_by_current']

    assert names[0]['ticker'] == 'T9'
    assert names[0]['current'] == '12.0%'


def test_daily_report_markdown_headers_and_no_recommendation_language():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history))).lower()

    for header in ['latest setup date', 'current read', 'trigger read', 'short-term shifts', 'notable names', 'portfolio snapshot']:
        assert header in markdown
    for forbidden in ['buy', 'sell', 'recommendation']:
        assert forbidden not in markdown


def test_llm_prompt_uses_structured_summary_not_raw_row_dump():
    history = _report_history()
    prompt = build_llm_report_prompt(build_daily_report_payload(history, _overview(history)))

    assert 'STRUCTURED_SUMMARY' in prompt
    assert 'Do not make trade recommendations' in prompt
    assert 'candidate_id' not in prompt
    assert 'current_pct_raw' not in prompt
