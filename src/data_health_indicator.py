from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.data_quality import (
    ACTIVE_DAILY_BAR_COVERAGE_COLUMNS,
    DataHealthSummary,
    build_data_health_summary,
    data_health_line,
)
from src.database import get_connection


DATA_HEALTH_CACHE_VERSION = 'data-health-active-daily-coverage-v1'


def _watchlist_metadata_fingerprint(db_path: str) -> str:
    try:
        con = get_connection(db_path)
        columns = {
            row[1]
            for row in con.execute("pragma table_info('watchlist_candidates')").fetchall()
        }
        if not columns:
            return 'no-watchlist-candidates'
        entry_tactic_expr = "coalesce(cast(entry_tactic as varchar), '')" if 'entry_tactic' in columns else "''"
        row = con.execute(
            f"""
            select
                count(*)::varchar,
                coalesce(max(candidate_id), 0)::varchar,
                coalesce(sum(hash(
                    coalesce(cast(candidate_id as varchar), '') || '|' ||
                    coalesce(cast(watchlist_date as varchar), '') || '|' ||
                    coalesce(cast(ticker as varchar), '') || '|' ||
                    coalesce(cast(setup as varchar), '') || '|' ||
                    {entry_tactic_expr} || '|' ||
                    coalesce(cast(rating as varchar), '')
                )), 0)::varchar
            from watchlist_candidates
            """
        ).fetchone()
    except Exception:
        return 'metadata-unavailable'
    return ':'.join(str(part) for part in row)


def data_health_cache_token(db_path: str) -> str:
    path = Path(db_path)
    try:
        stat = path.stat()
    except OSError:
        return f'{DATA_HEALTH_CACHE_VERSION}:missing'
    metadata = _watchlist_metadata_fingerprint(db_path)
    return f'{DATA_HEALTH_CACHE_VERSION}:{stat.st_mtime_ns}:{stat.st_size}:{metadata}'


@st.cache_data(show_spinner=False)
def load_data_health_summary(db_path: str, cache_version: str = DATA_HEALTH_CACHE_VERSION) -> DataHealthSummary:
    con = get_connection(db_path)
    return build_data_health_summary(con)


def render_data_health_indicator(summary: DataHealthSummary) -> None:
    expanded = summary.status == 'Check Data'
    with st.expander(f'Data Health: {summary.status}', expanded=expanded):
        st.caption(data_health_line(summary))
        st.dataframe(
            [{
                'Latest Setup Date': summary.latest_setup_date,
                'Latest Daily Bar Date': summary.latest_daily_bar_date,
                'Latest Intraday Bar Date': summary.latest_intraday_bar_date,
                'Candidate Rows': summary.candidate_rows,
                'Duplicate Candidate Keys': summary.duplicate_candidate_key_count,
                'Partial Intraday Sessions': summary.partial_intraday_session_count,
                'Reason': summary.reason,
            }],
            width='stretch',
            hide_index=True,
        )
        st.dataframe(
            [{
                'Active/Coverage Rows': summary.active_row_count,
                'Coverage Source': summary.active_daily_bar_coverage_source or '-',
                'Missing Latest Daily Bar': summary.active_missing_latest_daily_bar_count,
                'Max Stale Trading-Day Gap': summary.active_max_stale_trading_day_gap,
            }],
            width='stretch',
            hide_index=True,
        )
        stale_rows = summary.active_stale_daily_bar_rows
        if stale_rows is None:
            stale_rows = pd.DataFrame(columns=ACTIVE_DAILY_BAR_COVERAGE_COLUMNS)
        elif stale_rows.empty:
            stale_rows = pd.DataFrame(columns=ACTIVE_DAILY_BAR_COVERAGE_COLUMNS)
        else:
            stale_rows = stale_rows[ACTIVE_DAILY_BAR_COVERAGE_COLUMNS]
        st.dataframe(stale_rows, width='stretch', hide_index=True)
