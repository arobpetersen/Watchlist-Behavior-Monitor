from __future__ import annotations

import pandas as pd
import streamlit as st

from src.database import get_connection
from src.performance import PerfTimer
from src.setup_behavior_overview import monitor_history


MONITOR_HISTORY_CACHE_VERSION = 'monitor-history-vwap-triggered-fail-v1'


@st.cache_data(show_spinner=False)
def load_cached_monitor_history(db_path: str, cache_version: str) -> tuple[pd.DataFrame, list[dict]]:
    timer = PerfTimer('Shared Monitor History', enabled=True)
    con = get_connection(db_path)
    history = monitor_history(con, perf=timer)
    return history, timer.rows()
