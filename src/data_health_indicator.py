from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.data_quality import DataHealthSummary, build_data_health_summary, data_health_line
from src.database import get_connection


DATA_HEALTH_CACHE_VERSION = 'data-health-freshness-v2'


def data_health_cache_token(db_path: str) -> str:
    path = Path(db_path)
    try:
        stat = path.stat()
    except OSError:
        return f'{DATA_HEALTH_CACHE_VERSION}:missing'
    return f'{DATA_HEALTH_CACHE_VERSION}:{stat.st_mtime_ns}:{stat.st_size}'


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
