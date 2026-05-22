from __future__ import annotations

import pandas as pd
import streamlit as st

from src.database import get_connection
from src.materialized_monitor_history import (
    is_materialized_monitor_history_fresh,
    latest_monitor_history_run,
    read_materialized_monitor_history,
)
from src.performance import PerfTimer
from src.setup_behavior_overview import monitor_history


MONITOR_HISTORY_CACHE_VERSION = 'monitor-history-d3-eligible-v1'


@st.cache_data(show_spinner=False)
def load_cached_monitor_history(db_path: str, cache_version: str) -> tuple[pd.DataFrame, list[dict]]:
    timer = PerfTimer('Shared Monitor History', enabled=True)
    con = get_connection(db_path)
    monitor_cache_version, data_token = cache_version.split(':', 1) if ':' in cache_version else (cache_version, '')
    if is_materialized_monitor_history_fresh(con, data_token, monitor_cache_version):
        history = read_materialized_monitor_history(con)
        run = latest_monitor_history_run(con) or {}
        return history, [{
            'Step': f"Shared Monitor History source: materialized ({run.get('row_count', len(history))} rows)",
            'Seconds': 0.0,
        }]
    history = monitor_history(con, perf=timer)
    timer.add('Shared Monitor History source: dynamic', 0.0)
    return history, timer.rows()
