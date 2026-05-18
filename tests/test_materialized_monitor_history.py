from __future__ import annotations

import pandas as pd

from src.materialized_monitor_history import (
    ROWS_TABLE,
    RUNS_TABLE,
    clear_materialized_monitor_history,
    ensure_monitor_history_tables,
    is_materialized_monitor_history_fresh,
    latest_monitor_history_run,
    materialize_monitor_history,
    read_materialized_monitor_history,
)
from src.monitor_history_loader import MONITOR_HISTORY_CACHE_VERSION, load_cached_monitor_history
from src.setup_behavior_overview import setup_behavior_overview
from src.trigger_event_explorer import explorer_rows
from src.watchlist_top_movers import load_top_movers, prepare_top_mover_rows
from src.setup_performance import build_setup_summary, filter_setup_performance_rows


def _history() -> pd.DataFrame:
    return pd.DataFrame([
        {
            'Setup Date': '2026-05-01',
            'Ticker': 'AAA',
            'Current Status': 'Active',
            'Trigger Day': 'Success',
            'Trigger': 'VWAP Reclaim',
            'PDH': '-',
            '1m ORH': '-',
            'VWAP Reclaim': 'success',
            '5m ORH': '-',
            'Notes': '',
            'Current %': '5.0%',
            'Max %': '12.0%',
            'Close < BE': 'No',
            'D3 High %': '15.0%',
            'D3 High': '15.0%',
            'Retests': '',
            'Setup': 'EP',
            'Entry Tactic': 'Bias Flip',
            'Rating': '5',
            'current_pct_raw': 0.05,
            'max_pct_raw': 0.12,
            'd3_high_pct_raw': 0.15,
            'Latest Status Date': '2026-05-03',
            'Ticker Latest Bar Date': '2026-05-03',
            'Global Latest Bar Date': '2026-05-03',
        },
        {
            'Setup Date': '2026-05-02',
            'Ticker': 'BBB',
            'Current Status': 'Failed D1',
            'Trigger Day': 'Success',
            'Trigger': '1m ORH',
            'PDH': '-',
            '1m ORH': 'success',
            'VWAP Reclaim': '',
            '5m ORH': '',
            'Notes': '',
            'Current %': '-2.0%',
            'Max %': '8.0%',
            'Close < BE': 'Yes',
            'D3 High %': '9.0%',
            'D3 High': '9.0%',
            'Retests': 'D1',
            'Setup': '',
            'Entry Tactic': '',
            'Rating': '3',
            'current_pct_raw': -0.02,
            'max_pct_raw': 0.08,
            'd3_high_pct_raw': 0.09,
            'Latest Status Date': '2026-05-03',
            'Ticker Latest Bar Date': '2026-05-03',
            'Global Latest Bar Date': '2026-05-03',
        },
    ])


def test_tables_are_created_if_missing(con=None):
    import duckdb

    con = duckdb.connect(':memory:')
    ensure_monitor_history_tables(con)

    tables = {row[0] for row in con.execute('show tables').fetchall()}
    assert RUNS_TABLE in tables


def test_materialize_writes_successful_run_and_rows():
    import duckdb

    con = duckdb.connect(':memory:')
    result = materialize_monitor_history(
        con,
        cache_version=MONITOR_HISTORY_CACHE_VERSION,
        data_token='token-a',
        history_builder=lambda _con: _history(),
    )

    assert result.status == 'success'
    assert result.row_count == 2
    assert result.setup_date_count == 2
    assert con.execute(f'select count(*) from {RUNS_TABLE} where status = ?', ['success']).fetchone()[0] == 1
    assert con.execute(f'select count(*) from {ROWS_TABLE}').fetchone()[0] == 2

    read_back = read_materialized_monitor_history(con)
    assert len(read_back) == len(_history())
    assert read_back[['Setup Date', 'Ticker', 'Trigger', 'Current Status']].astype(str).to_dict('records') == (
        _history()[['Setup Date', 'Ticker', 'Trigger', 'Current Status']].astype(str).to_dict('records')
    )


def test_freshness_checks_version_and_data_token():
    import duckdb

    con = duckdb.connect(':memory:')
    materialize_monitor_history(
        con,
        cache_version=MONITOR_HISTORY_CACHE_VERSION,
        data_token='token-a',
        history_builder=lambda _con: _history(),
    )

    assert is_materialized_monitor_history_fresh(con, 'token-a', MONITOR_HISTORY_CACHE_VERSION)
    assert not is_materialized_monitor_history_fresh(con, 'token-b', MONITOR_HISTORY_CACHE_VERSION)
    assert not is_materialized_monitor_history_fresh(con, 'token-a', 'different-version')
    assert latest_monitor_history_run(con)['row_count'] == 2


def test_shared_loader_uses_materialized_rows_when_fresh(tmp_path, monkeypatch):
    from src.database import get_connection

    db_path = tmp_path / 'watchlist.duckdb'
    con = get_connection(str(db_path))
    materialize_monitor_history(
        con,
        cache_version=MONITOR_HISTORY_CACHE_VERSION,
        data_token='token-a',
        history_builder=lambda _con: _history(),
    )
    con.close()
    load_cached_monitor_history.clear()
    monkeypatch.setattr('src.monitor_history_loader.monitor_history', lambda _con, perf=None: (_ for _ in ()).throw(AssertionError('dynamic path used')))

    history, timings = load_cached_monitor_history(str(db_path), f'{MONITOR_HISTORY_CACHE_VERSION}:token-a')

    assert len(history) == 2
    assert history['Ticker'].tolist() == ['AAA', 'BBB']
    assert 'materialized' in timings[0]['Step']


def test_shared_loader_falls_back_when_materialized_missing_or_stale(tmp_path, monkeypatch):
    from src.database import get_connection

    db_path = tmp_path / 'watchlist.duckdb'
    get_connection(str(db_path)).close()
    load_cached_monitor_history.clear()
    monkeypatch.setattr('src.monitor_history_loader.monitor_history', lambda _con, perf=None: _history())

    history, timings = load_cached_monitor_history(str(db_path), f'{MONITOR_HISTORY_CACHE_VERSION}:token-a')

    assert len(history) == 2
    assert history['Ticker'].tolist() == ['AAA', 'BBB']
    assert any('dynamic' in row['Step'] for row in timings)


def test_downstream_helpers_accept_materialized_rows():
    from src.database import get_connection

    con = get_connection(':memory:')
    con.execute(
        """
        insert into watchlist_candidates
        values
        (1, '2026-05-01', 'AAA', 5, 'EP', 'Bias Flip', '', null, 'test.csv', current_timestamp),
        (2, '2026-05-02', 'BBB', 3, '', '', '', null, 'test.csv', current_timestamp)
        """
    )
    materialize_monitor_history(
        con,
        cache_version=MONITOR_HISTORY_CACHE_VERSION,
        data_token='token-a',
        history_builder=lambda _con: _history(),
    )
    history = read_materialized_monitor_history(con)

    overview = setup_behavior_overview(con, history=history)
    explorer = explorer_rows(history, 'All')
    top_history, latest = load_top_movers(con, history=history)
    mapped = prepare_top_mover_rows(top_history, latest)
    perf_rows = filter_setup_performance_rows(history)
    setup_summary = build_setup_summary(perf_rows)

    assert len(overview['details']['Last 10 Setup Dates']) == 2
    assert len(explorer) == 2
    assert len(mapped) == 2
    assert not setup_summary.empty


def test_clear_materialized_monitor_history_removes_rows_and_runs():
    import duckdb

    con = duckdb.connect(':memory:')
    materialize_monitor_history(
        con,
        cache_version=MONITOR_HISTORY_CACHE_VERSION,
        data_token='token-a',
        history_builder=lambda _con: _history(),
    )

    clear_materialized_monitor_history(con)

    assert con.execute(f'select count(*) from {RUNS_TABLE}').fetchone()[0] == 0
    assert con.execute(f'select count(*) from {ROWS_TABLE}').fetchone()[0] == 0
