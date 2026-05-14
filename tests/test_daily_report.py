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
        and not line.startswith('| Window |') and not line.startswith('| Setup Cohort |')
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


def test_daily_report_payload_includes_watchlist_pulse_quality_metrics():
    history = _report_history()
    payload = build_daily_report_payload(history, _overview(history))
    pulse = payload['watchlist_pulse']

    assert pulse['Latest']['clean_active_count'] == 0
    assert pulse['Last 5']['clean_active_count'] == 0
    assert pulse['Previous 5']['clean_active_count'] == 5
    assert pulse['Last 5']['median_current'] == 0.10
    assert round(float(pulse['Last 5']['median_max']), 2) == 0.22
    assert pulse['Previous 5']['hold_ratio']['value'] == 41.7
    assert pulse['Last 5']['thresholds']['5']['count'] == 5
    assert pulse['Last 5']['thresholds']['10']['count'] == 5
    assert pulse['Last 5']['thresholds']['20']['count'] == 4


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


def test_daily_report_payload_includes_trigger_quality_and_review_names():
    history = _report_history()
    payload = build_daily_report_payload(history, _overview(history))

    trigger_quality = payload['trigger_quality_rows']
    review_names = payload['notable_name_rows']

    assert any(row['trigger'] == '1m ORH' and row['window'] == 'Last 5' and row['sample'] == 5 and row['read'] == 'Elevated failures' for row in trigger_quality)
    assert any(row['why'] == 'Major giveback from large max move' and 'Hold' in row['evidence'] for row in review_names)
    assert not any(row['ticker'] == 'T9' and row['why'] == 'Clean active leader' for row in review_names)


def test_daily_report_markdown_headers_and_no_recommendation_language():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history))).lower()

    for header in ['summary read', 'watchlist pulse', 'trigger failure snapshot', 'progression quality by setup cohort', 'trigger quality', 'names to review', 'portfolio snapshot']:
        assert header in markdown
    for forbidden in ['buy', 'sell', 'recommendation']:
        assert forbidden not in markdown


def test_daily_report_markdown_renders_watchlist_workflow_sections():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))

    assert '| Metric | Latest Setup Date | Recent 5 Setup Dates | Prior 5 Setup Dates | Rolling Avg |' in markdown
    assert '| Setup Cohort | Setups | Reached +5% | Reached +10% | Reached +20% | Retested After D0 |' in markdown
    assert 'Median Days to Max' not in markdown
    assert '| Trigger | Window | Sample | Clean Active | Median Max % | Fail Rate | Read |' in markdown
    assert '| Ticker | Review Reason | Evidence | Status |' in markdown
    assert 'Current Progress portfolio: 0 qualifying names. Leaders: -. Median current progress: -.' in markdown
    assert '| 1m ORH | Recent 5 Setup Dates | 5 | 0 / 5 (0.0%) | 22.0% | 60.0% | Elevated failures |' in markdown
    assert '## Key Shifts' not in markdown


def test_daily_report_replaces_ambiguous_window_labels_in_rendered_report():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))

    assert 'Latest Setup Date' in markdown
    assert 'Recent 5 Setup Dates' in markdown
    assert 'Prior 5 Setup Dates' in markdown
    assert '| Metric | Latest | Last 5 | Previous 5 |' not in markdown
    assert '| Last 5 |' not in markdown
    assert '| Previous 5 |' not in markdown


def test_daily_report_trigger_failure_snapshot_appears_below_watchlist_pulse():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    snapshot = _section(markdown, 'Trigger Failure Snapshot')

    assert markdown.index('## Watchlist Pulse') < markdown.index('## Trigger Failure Snapshot') < markdown.index('## Progression Quality by Setup Cohort')
    assert 'Format: Triggered / Failed / Fail %' in snapshot
    assert '| Trigger | Latest Setup Date | Recent 5 Setup Dates | Prior 5 Setup Dates | Rolling Avg |' in snapshot
    assert '| 1m ORH | 1 / 0 / 0% | 5 / 3 / 60% | 5 / 0 / 0% | 10 / 3 / 30% |' in snapshot
    assert len(_table_body_rows(snapshot)) <= 4


def test_daily_report_trigger_failure_snapshot_zero_attempts_are_compact():
    history = _report_history()
    history.loc[history.index[-1], 'Trigger'] = 'PDH'

    snapshot = build_daily_report_payload(history, _overview(history))['trigger_failure_snapshot']
    markdown = render_daily_report_markdown({
        'watchlist_pulse': build_daily_report_payload(history, _overview(history))['watchlist_pulse'],
        'trigger_failure_snapshot': snapshot,
        'trigger_quality_rows': [],
        'notable_name_rows': [],
        'portfolio_summary': {},
    })

    section = _section(markdown, 'Trigger Failure Snapshot')
    assert '| PDH | 1 / 0 / 0% | 1 / 0 / 0% | 0 / - / - | 1 / 0 / 0% |' in section


def test_daily_report_summary_read_is_capped_and_evidence_based():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    summary = _section(markdown, 'Summary Read')
    bullets = [line for line in summary.splitlines() if line.startswith('- ')]

    assert 1 <= len(bullets) <= 4
    assert any('Clean Active' in bullet and 'Recent 5' in bullet and 'Prior 5' in bullet for bullet in bullets)
    assert any('samples' in bullet and 'failed' in bullet for bullet in bullets)
    assert 'moved from' not in summary
    assert 'Clean Active is' not in summary
    assert 'setup dates are' not in summary
    assert 'Environment improved:' not in summary
    assert 'Environment weakened:' not in summary
    assert 'Progression:' not in summary


def test_daily_report_watchlist_pulse_includes_progress_and_hold_quality():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    pulse = _section(markdown, 'Watchlist Pulse')

    assert '| Clean Active | 0/1 (0%) | 0/5 (0%) | 5/5 (100%) | 5/10 (50%) |' in pulse
    assert '0.0%)' not in pulse
    assert '| Median Current % | 12.0% | 10.0% | 5.0% | 7.5% |' in pulse
    assert '| Median Max % | 26.0% | 22.0% | 12.0% | 17.0% |' in pulse
    assert '| Hold Ratio | - | - | 41.7% (5 samples) | 41.7% (5 samples) |' in pulse


def test_daily_report_rolling_average_uses_latest_20_setup_dates():
    rows = []
    for idx, date in enumerate(pd.date_range('2026-04-01', periods=25, freq='D')):
        rows.append({
            'Setup Date': date.date().isoformat(),
            'Ticker': f'R{idx}',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': '1m ORH',
            'Close < BE': 'No',
            'Retests': '',
            'Latest Status Date': '2026-04-25',
            'ticker_latest_bar_date': '2026-04-25',
            'current_pct_raw': 0.05,
            'max_pct_raw': 0.10,
        })
    history = pd.DataFrame(rows)
    payload = build_daily_report_payload(history, _overview(history))

    assert payload['watchlist_pulse']['Rolling Avg']['setup_count'] == 20
    assert payload['trigger_failure_snapshot'][0]['cells']['Rolling Avg']['triggered'] == 20


def test_daily_report_progression_quality_includes_threshold_follow_through():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    progression = _section(markdown, 'Progression Quality by Setup Cohort')
    rows = _table_body_rows(progression)

    assert len(rows) == 3
    assert 'Thresholds use max move; older setup cohorts have had more time to reach levels.' in progression
    assert '| Recent 5 Setup Dates | 5 | 5 / 5 (100.0%) | 5 / 5 (100.0%) | 4 / 5 (80.0%) | 2 / 5 (40.0%) |' in progression
    assert 'Median Days to Max' not in progression


def test_daily_report_trigger_quality_includes_movement_and_failure_quality():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    trigger_quality = _section(markdown, 'Trigger Quality')
    rows = _table_body_rows(trigger_quality)

    assert len(rows) <= 5
    assert 'Small sample' in trigger_quality
    assert 'Median Max %' in trigger_quality
    assert 'Fail Rate' in trigger_quality
    assert rows[0].startswith('| 1m ORH | Recent 5 Setup Dates |')
    assert 'Elevated failures' in rows[0]
    assert rows.index(next(row for row in rows if '| Prior 5 Setup Dates |' in row)) < rows.index(next(row for row in rows if '| Latest Setup Date |' in row))


def test_daily_report_names_to_review_caps_at_five_rows_and_portfolio_is_compact():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    notable_names = _section(markdown, 'Names to Review')
    portfolio = _section(markdown, 'Portfolio Snapshot')

    assert len(_table_body_rows(notable_names)) <= 5
    assert 'Evidence' in notable_names
    assert 'Major giveback from large max move' in notable_names
    assert 'Hold 46.2%' in notable_names
    assert '| T9 | Clean active leader |' not in notable_names
    assert 'Current Progress portfolio:' in portfolio
    assert '| Qualifying names |' not in portfolio
    assert 'Rolling Avg' not in notable_names


def test_daily_report_clean_active_leader_requires_acceptable_hold_ratio():
    history = _report_history()
    extra = history.iloc[[0]].copy()
    extra['Ticker'] = 'HOLD'
    extra['Setup Date'] = '2026-05-10'
    extra['Current Status'] = 'Active'
    extra['Trigger Day'] = 'Success'
    extra['Close < BE'] = 'No'
    extra['current_pct_raw'] = 0.15
    extra['max_pct_raw'] = 0.20
    history = pd.concat([history, extra], ignore_index=True)

    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    names = _section(markdown, 'Names to Review')

    assert '| HOLD | Clean active leader | Current 15.0%; Max 20.0%; Hold 75.0% | Active |' in names
    assert '| T9 | Clean active leader |' not in names


def test_daily_report_excludes_stale_active_giveback_from_names_to_review():
    history = pd.DataFrame([
        {
            'Setup Date': '2026-05-09',
            'Ticker': 'BIRD',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': '1m ORH',
            'Close < BE': 'No',
            'Retests': '',
            'Latest Status Date': '2026-05-09',
            'ticker_latest_bar_date': '2026-05-09',
            'current_pct_raw': 0.062,
            'max_pct_raw': 2.062,
        },
        {
            'Setup Date': '2026-05-10',
            'Ticker': 'VALID',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': '1m ORH',
            'Close < BE': 'No',
            'Retests': '',
            'Latest Status Date': '2026-05-10',
            'ticker_latest_bar_date': '2026-05-10',
            'current_pct_raw': 0.08,
            'max_pct_raw': 0.40,
        },
    ])

    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    names = _section(markdown, 'Names to Review')

    assert 'BIRD' not in names
    assert '| VALID | Major giveback from large max move | Current 8.0%; Max 40.0%; Hold 20.0% | Active |' in names


def test_daily_report_allows_valid_failed_historical_review_names():
    history = pd.DataFrame([
        {
            'Setup Date': '2026-05-10',
            'Ticker': 'FAIL',
            'Current Status': 'Failed D2',
            'Trigger Day': 'Success',
            'Trigger': 'VWAP Reclaim',
            'Close < BE': 'Yes',
            'Retests': '',
            'Latest Status Date': '2026-05-10',
            'ticker_latest_bar_date': '2026-05-10',
            'current_pct_raw': -0.03,
            'max_pct_raw': 0.32,
        },
    ])

    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    names = _section(markdown, 'Names to Review')

    assert '| FAIL | Max move later failed | Current -3.0%; Max 32.0% | Failed D2 |' in names
    assert '| FAIL | Clean active leader |' not in names


def test_daily_report_clean_active_leader_requires_fresh_active_eligibility():
    history = pd.DataFrame([
        {
            'Setup Date': '2026-05-09',
            'Ticker': 'STALE',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': 'PDH',
            'Close < BE': 'No',
            'Retests': '',
            'Latest Status Date': '2026-05-09',
            'ticker_latest_bar_date': '2026-05-09',
            'current_pct_raw': 0.20,
            'max_pct_raw': 0.25,
        },
        {
            'Setup Date': '2026-05-10',
            'Ticker': 'FRESH',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': 'PDH',
            'Close < BE': 'No',
            'Retests': '',
            'Latest Status Date': '2026-05-10',
            'ticker_latest_bar_date': '2026-05-10',
            'current_pct_raw': 0.18,
            'max_pct_raw': 0.24,
        },
    ])

    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    names = _section(markdown, 'Names to Review')

    assert 'STALE' not in names
    assert '| FRESH | Clean active leader | Current 18.0%; Max 24.0%; Hold 75.0% | Active |' in names


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

    assert 'No reportable watchlist behavior data is available.' not in markdown
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
