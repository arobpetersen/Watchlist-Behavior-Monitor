from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Callable
from uuid import uuid4

import pandas as pd

from src.database import get_connection


RUNS_TABLE = 'canonical_monitor_history_runs'
ROWS_TABLE = 'canonical_monitor_history_rows'
SOURCE_TABLES = [
    'watchlist_candidates',
    'entry_day_features',
    'behavior_labels',
    'daily_bars',
    'intraday_bars_1m',
]


@dataclass(frozen=True)
class MaterializedMonitorHistoryResult:
    run_id: str
    status: str
    row_count: int
    setup_date_count: int
    seconds: float
    source: str
    error: str = ''


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(con, table_name: str) -> bool:
    return bool(con.execute(
        """
        select count(*)
        from information_schema.tables
        where table_name = ?
        """,
        [table_name],
    ).fetchone()[0])


def _table_columns(con, table_name: str) -> dict[str, str]:
    if not _table_exists(con, table_name):
        return {}
    return {row[1]: row[2] for row in con.execute(f'pragma table_info({_quote(table_name)})').fetchall()}


def _duckdb_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return 'boolean'
    if pd.api.types.is_integer_dtype(series):
        return 'bigint'
    if pd.api.types.is_float_dtype(series):
        return 'double'
    if pd.api.types.is_datetime64_any_dtype(series):
        return 'timestamp'
    return 'varchar'


def ensure_monitor_history_tables(con) -> None:
    con.execute(f"""
        create table if not exists {_quote(RUNS_TABLE)} (
            run_id varchar,
            created_at timestamp,
            cache_version varchar,
            data_health_token varchar,
            row_count bigint,
            setup_date_count bigint,
            source varchar,
            status varchar,
            error varchar
        )
    """)


def monitor_history_source_token(db_path: str) -> str:
    con = get_connection(db_path)
    parts = []
    for table in SOURCE_TABLES:
        if not _table_exists(con, table):
            parts.append(f'{table}:missing')
            continue
        columns = [row[1] for row in con.execute(f'pragma table_info({_quote(table)})').fetchall()]
        if not columns:
            parts.append(f'{table}:no-columns')
            continue
        concat_expr = " || '|' || ".join(f"coalesce(cast({_quote(column)} as varchar), '')" for column in columns)
        row = con.execute(
            f"""
            select count(*)::varchar, coalesce(sum(hash({concat_expr})), 0)::varchar
            from {_quote(table)}
            """
        ).fetchone()
        parts.append(f'{table}:{row[0]}:{row[1]}')
    return 'monitor-source-v1:' + ':'.join(parts)


def _ensure_rows_table_for_frame(con, frame: pd.DataFrame) -> None:
    if not _table_exists(con, ROWS_TABLE):
        initial = frame.copy()
        initial.insert(0, 'run_id', '')
        con.register('monitor_history_schema_frame', initial.head(0))
        con.execute(f'create table {_quote(ROWS_TABLE)} as select * from monitor_history_schema_frame')
        con.unregister('monitor_history_schema_frame')
        return
    existing = _table_columns(con, ROWS_TABLE)
    if 'run_id' not in existing:
        con.execute(f'alter table {_quote(ROWS_TABLE)} add column {_quote("run_id")} varchar')
    for column in frame.columns:
        if column not in existing:
            con.execute(f'alter table {_quote(ROWS_TABLE)} add column {_quote(column)} {_duckdb_type(frame[column])}')


def _replace_rows_table(con, rows: pd.DataFrame) -> None:
    con.register('monitor_history_rows_to_write', rows)
    con.execute(f'create or replace table {_quote(ROWS_TABLE)} as select * from monitor_history_rows_to_write')
    con.unregister('monitor_history_rows_to_write')


def latest_monitor_history_run(con) -> dict | None:
    ensure_monitor_history_tables(con)
    row = con.execute(f"""
        select run_id, created_at, cache_version, data_health_token, row_count,
               setup_date_count, source, status, error
        from {_quote(RUNS_TABLE)}
        where status = 'success'
        order by created_at desc
        limit 1
    """).fetchone()
    if row is None:
        return None
    columns = ['run_id', 'created_at', 'cache_version', 'data_health_token', 'row_count', 'setup_date_count', 'source', 'status', 'error']
    return dict(zip(columns, row))


def is_materialized_monitor_history_fresh(con, data_token: str, cache_version: str) -> bool:
    run = latest_monitor_history_run(con)
    if not run:
        return False
    return run.get('cache_version') == cache_version and run.get('data_health_token') == data_token


def read_materialized_monitor_history(con) -> pd.DataFrame:
    run = latest_monitor_history_run(con)
    if not run or not _table_exists(con, ROWS_TABLE):
        return pd.DataFrame()
    frame = con.execute(
        f'select * from {_quote(ROWS_TABLE)} where run_id = ?',
        [run['run_id']],
    ).df()
    if 'run_id' in frame:
        frame = frame.drop(columns=['run_id'])
    return frame


def clear_materialized_monitor_history(con) -> None:
    ensure_monitor_history_tables(con)
    if _table_exists(con, ROWS_TABLE):
        con.execute(f'delete from {_quote(ROWS_TABLE)}')
    con.execute(f'delete from {_quote(RUNS_TABLE)}')


def _insert_run(
    con,
    *,
    run_id: str,
    cache_version: str,
    data_token: str,
    row_count: int,
    setup_date_count: int,
    source: str,
    status: str,
    error: str = '',
) -> None:
    con.execute(
        f'insert into {_quote(RUNS_TABLE)} values (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [run_id, datetime.now(), cache_version, data_token, row_count, setup_date_count, source, status, error],
    )


def materialize_monitor_history(
    con,
    db_path: str | None = None,
    source: str = 'manual',
    cache_version: str = 'monitor-history-vwap-triggered-fail-v1',
    data_token: str | None = None,
    history_builder: Callable | None = None,
) -> MaterializedMonitorHistoryResult:
    from src.setup_behavior_overview import monitor_history

    ensure_monitor_history_tables(con)
    run_id = str(uuid4())
    start = perf_counter()
    resolved_token = data_token or (monitor_history_source_token(db_path) if db_path else '')
    try:
        builder = history_builder or monitor_history
        history = builder(con)
        if history is None:
            history = pd.DataFrame()
        history = history.copy()
        setup_date_count = int(history['Setup Date'].nunique()) if 'Setup Date' in history and not history.empty else 0
        rows_to_write = history.copy()
        rows_to_write.insert(0, 'run_id', run_id)
        _replace_rows_table(con, rows_to_write)
        row_count = len(history)
        _insert_run(
            con,
            run_id=run_id,
            cache_version=cache_version,
            data_token=resolved_token,
            row_count=row_count,
            setup_date_count=setup_date_count,
            source=source,
            status='success',
        )
        return MaterializedMonitorHistoryResult(run_id, 'success', row_count, setup_date_count, perf_counter() - start, source)
    except Exception as exc:
        _insert_run(
            con,
            run_id=run_id,
            cache_version=cache_version,
            data_token=resolved_token,
            row_count=0,
            setup_date_count=0,
            source=source,
            status='failure',
            error=str(exc),
        )
        raise
