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


def _section(markdown: str, header: str) -> str:
    start = markdown.index(f'## {header}')
    rest = markdown[start + len(f'## {header}'):]
    next_header = rest.find('\n## ')
    return rest if next_header == -1 else rest[:next_header]


def _table_body_rows(section: str) -> list[str]:
    return [
        line for line in section.splitlines()
        if line.startswith('| ') and not line.startswith('| ---') and not line.startswith('| Metric |')
        and not line.startswith('| Area |') and not line.startswith('| Trigger |') and not line.startswith('| Ticker |')
    ]


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


def test_daily_report_payload_includes_material_comparison_observations():
    history = _report_history()
    payload = build_daily_report_payload(history, _overview(history))

    observations = payload['material_observations']

    assert set(payload['comparison_summary']) == {
        'latest_vs_prior',
        'latest_vs_last5',
        'last2_vs_last5',
        'last5_vs_previous5',
    }
    assert any('Latest setup date vs prior setup date' in item['text'] for item in observations)
    assert any(item['section'] == 'Trigger Read' and 'failure rate' in item['text'] for item in observations)
    assert any(item['section'] == 'Short-Term Shifts' for item in observations)
    assert any('/' in item['text'] and 'setups' in item['text'] for item in observations)
    assert any('Small sample.' in item['text'] for item in observations)


def test_daily_report_payload_includes_top_active_names():
    history = _report_history()
    payload = build_daily_report_payload(history, _overview(history))

    names = payload['notable_tickers']['top_active_by_current']

    assert names[0]['ticker'] == 'T9'
    assert names[0]['current'] == '12.0%'


def test_daily_report_markdown_headers_and_no_recommendation_language():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history))).lower()

    for header in ['summary read', 'executive snapshot', 'key shifts', 'trigger read', 'notable names', 'portfolio snapshot']:
        assert header in markdown
    for forbidden in ['buy', 'sell', 'recommendation']:
        assert forbidden not in markdown


def test_daily_report_markdown_renders_hybrid_sections():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))

    assert '| Metric | Value | Count |' in markdown
    assert '| Area | Change | Evidence | Read |' in markdown
    assert '| Trigger | Window | Evidence | Read |' in markdown
    assert '| Ticker | Why Notable | Current % | Max % | Status |' in markdown
    assert 'Current Progress portfolio: 0 qualifying names. Leaders: -.' in markdown
    assert '| 1m ORH | Latest | 1 triggered, 0 failed, 1 success (0.0% fail) | Small sample |' in markdown
    assert '- Latest setup date vs prior setup date:' not in markdown


def test_daily_report_summary_read_is_capped_and_evidence_based():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    summary = _section(markdown, 'Summary Read')
    bullets = [line for line in summary.splitlines() if line.startswith('- ')]

    assert 1 <= len(bullets) <= 4
    assert any('moved from' in bullet or 'triggered' in bullet for bullet in bullets)


def test_daily_report_executive_snapshot_omits_low_value_zero_rows():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    snapshot = _section(markdown, 'Executive Snapshot')

    assert '| Unresolved |' not in snapshot
    assert '| Retested D0 Only |' not in snapshot
    assert '| Retested After D0 | 0.0% | 0 / 1 |' in snapshot


def test_daily_report_key_shifts_are_capped_and_suppress_duplicates():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    key_shifts = _section(markdown, 'Key Shifts')
    rows = _table_body_rows(key_shifts)

    assert len(rows) <= 5
    assert sum('| Active |' in row for row in rows) == 1
    assert '| Area | Change | Evidence | Read |' in key_shifts


def test_daily_report_trigger_read_is_filtered_and_labels_small_samples():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    trigger_read = _section(markdown, 'Trigger Read')
    rows = _table_body_rows(trigger_read)

    assert len(rows) <= 5
    assert 'Small sample' in trigger_read
    assert 'triggered' in trigger_read and 'failed' in trigger_read and 'success' in trigger_read


def test_daily_report_notable_names_caps_at_five_rows_and_portfolio_is_compact():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    notable_names = _section(markdown, 'Notable Names')
    portfolio = _section(markdown, 'Portfolio Snapshot')

    assert len(_table_body_rows(notable_names)) <= 5
    assert 'Current Progress portfolio:' in portfolio
    assert '| Qualifying names |' not in portfolio


def test_daily_report_markdown_omits_raw_metric_dump_and_handles_no_material_shifts():
    history = _report_history()
    history['Current Status'] = 'Active'
    history['Trigger Day'] = 'Success'
    history['1m ORH'] = 'success'
    history['Close < BE'] = 'No'
    history['Retests'] = ''
    history['current_pct_raw'] = 0.05
    history['max_pct_raw'] = 0.10
    payload = build_daily_report_payload(history, _overview(history))
    payload['notable_tickers'] = {'top_active_by_current': [], 'failed_after_initially_working': [], 'close_below_be': [], 'strongest_max': []}
    payload['portfolio_summary'] = {'current_progress_count': 0, 'top_current_progress': [], 'longest_open': [], 'rated_4_count': 0, 'rated_5_count': 0}
    payload['material_observations'] = []

    markdown = render_daily_report_markdown(payload)

    assert 'No material behavior shifts detected across the selected comparison windows.' in markdown
    assert 'Active:' not in markdown
    assert 'Failed D0:' not in markdown
    assert 'Last 5 active rate' not in markdown


def test_llm_prompt_uses_structured_summary_not_raw_row_dump():
    history = _report_history()
    prompt = build_llm_report_prompt(build_daily_report_payload(history, _overview(history)))

    assert 'STRUCTURED_SUMMARY' in prompt
    assert 'Do not make trade recommendations' in prompt
    assert 'candidate_id' not in prompt
    assert 'current_pct_raw' not in prompt
