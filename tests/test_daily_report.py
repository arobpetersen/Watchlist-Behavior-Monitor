from __future__ import annotations

import pandas as pd

from src.daily_report import (
    build_daily_report_payload,
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

    for header in ['summary read', 'market context', 'day read', 'trigger read', 'names to review', 'portfolio snapshot']:
        assert header in markdown
    for forbidden in ['buy', 'sell', 'recommendation']:
        assert forbidden not in markdown


def test_daily_report_markdown_renders_concise_top_read_sections():
    history = _report_history()
    markdown = render_daily_report_markdown(
        build_daily_report_payload(
            history,
            _overview(history),
            market_context='QQQ -0.8% | Down Day | Volatile Recovery | Gap -0.7% | Close Position 78% | Range 1.38x ATR(14)',
        )
    )

    assert 'QQQ -0.8% | Down Day | Volatile Recovery | Gap -0.7% | Close Position 78% | Range 1.38x ATR(14)' in markdown
    assert '| Metric | Read |' in markdown
    assert '| Setups | 1 |' in markdown
    assert '| Active | 1 / 100% |' in markdown
    assert '| D0 Fail | 0 / 0% |' in markdown
    assert '| Failed After D0 | 0 / 0% |' in markdown
    assert '| Close < BE | 1 / 100% |' in markdown
    assert '| Retested | 0 / 0% |' in markdown
    assert 'Median Current' not in _section(markdown, 'Day Read')
    assert 'Median Max' not in _section(markdown, 'Day Read')
    assert '| Trigger | Read |' in markdown
    assert '| 1m ORH | 1 success |' in markdown
    assert '| Ticker | Review Reason | Evidence | Status |' in markdown
    assert 'Current Progress portfolio: 0 qualifying names. Leaders: -. Median current progress: -.' in markdown
    assert '## Watchlist Pulse' not in markdown
    assert '## Trigger Failure Snapshot' not in markdown
    assert '## Progression Quality by Setup Cohort' not in markdown
    assert '## Trigger Quality' not in markdown


def test_daily_report_uses_latest_setup_day_language_in_rendered_report():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))

    assert 'Latest setup date: 2026-05-10' in markdown
    assert 'D0 Fail' in markdown
    assert 'Failed After D0' in markdown
    assert '| Metric | Latest | Last 5 | Previous 5 |' not in markdown
    assert 'Clean Active' not in _section(markdown, 'Summary Read')


def test_daily_report_market_context_has_stable_unavailable_message():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    market = _section(markdown, 'Market Context')
    summary = _section(markdown, 'Summary Read')

    assert 'Market context unavailable for latest setup date.' in market
    assert '- Market context unavailable for latest setup date.' in summary


def test_daily_report_trigger_read_uses_latest_setup_date_groups():
    history = _report_history()
    history.loc[history.index[-1], 'Trigger'] = 'PDH'
    history.loc[history.index[-1], 'PDH'] = 'success'
    history.loc[history.index[-1], '1m ORH'] = '-'

    payload = build_daily_report_payload(history, _overview(history))
    markdown = render_daily_report_markdown(payload)

    section = _section(markdown, 'Trigger Read')
    assert '| PDH | 1 success |' in section
    assert '0 / - / -' not in section


def test_daily_report_summary_read_is_capped_and_evidence_based():
    history = _report_history()
    markdown = render_daily_report_markdown(
        build_daily_report_payload(history, _overview(history), market_context='QQQ +1.1% | Up Day | Trend Up')
    )
    summary = _section(markdown, 'Summary Read')
    bullets = [line for line in summary.splitlines() if line.startswith('- ')]

    assert len(bullets) == 4
    assert any('Latest setup date: 2026-05-10' in bullet and 'D0 fail' in bullet for bullet in bullets)
    assert any('Market context: QQQ +1.1% | Up Day | Trend Up.' in bullet for bullet in bullets)
    assert any('Trigger read:' in bullet and '1m ORH 1 success' in bullet for bullet in bullets)
    assert any('Early follow-through:' in bullet and 'Close < BE 1 / 100%' in bullet for bullet in bullets)
    assert 'moved from' not in summary
    assert 'Clean Active is' not in summary
    assert 'setup dates are' not in summary
    assert 'Environment improved:' not in summary
    assert 'Environment weakened:' not in summary
    assert 'Progression:' not in summary


def test_daily_report_day_read_matches_snapshot_definitions():
    history = _report_history()
    failed_d0_status = history.iloc[[-1]].copy()
    failed_d0_status['Ticker'] = 'D0STATUS'
    failed_d0_status['Current Status'] = 'Failed D0'
    failed_d0_status['Trigger Day'] = 'Success'
    failed_d0_status['Close < BE'] = 'No'
    failed_d0_status['Retests'] = 'D0'
    failed_d0_status['D3 High %'] = '14.0%'
    trigger_fail = history.iloc[[-1]].copy()
    trigger_fail['Ticker'] = 'TRIGFAIL'
    trigger_fail['Current Status'] = '-'
    trigger_fail['Trigger Day'] = 'Fail'
    trigger_fail['Close < BE'] = 'No'
    trigger_fail['Retests'] = ''
    trigger_fail['D3 High %'] = '10.0%'
    duplicate = history.iloc[[-1]].copy()
    duplicate['Ticker'] = 'BOTH'
    duplicate['Current Status'] = 'Failed D0'
    duplicate['Trigger Day'] = 'Fail'
    duplicate['Close < BE'] = 'No'
    duplicate['Retests'] = ''
    duplicate['D3 High %'] = '20.0%'
    later = history.iloc[[-1]].copy()
    later['Ticker'] = 'LATER'
    later['Current Status'] = 'Failed D2'
    later['Trigger Day'] = 'Success'
    later['Close < BE'] = 'Yes'
    later['Retests'] = 'D1'
    later['D3 High %'] = '12.0%'
    history = pd.concat([history, failed_d0_status, trigger_fail, duplicate, later], ignore_index=True)

    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))
    day_read = _section(markdown, 'Day Read')

    assert '| Setups | 5 |' in day_read
    assert '| Active | 1 / 20% |' in day_read
    assert '| D0 Fail | 3 / 60% |' in day_read
    assert '| Failed After D0 | 1 / 20% |' in day_read
    assert '| Close < BE | 2 / 40% |' in day_read
    assert '| Retested | 2 / 40% |' in day_read
    assert '| Median D3 High | 13.0% |' in day_read
    assert 'Median Current' not in day_read
    assert 'Median Max' not in day_read


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


def test_daily_report_omits_progression_quality_section_from_markdown():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))

    assert '## Progression Quality by Setup Cohort' not in markdown
    assert 'Thresholds use max move' not in markdown


def test_daily_report_omits_trigger_quality_section_from_markdown():
    history = _report_history()
    markdown = render_daily_report_markdown(build_daily_report_payload(history, _overview(history)))

    assert '## Trigger Quality' not in markdown
    assert '| Trigger | Window | Sample | Clean Active | Median Max % | Fail Rate | Read |' not in markdown


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

