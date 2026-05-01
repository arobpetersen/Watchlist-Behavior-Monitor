import streamlit as st

from src.config import get_settings
from src.dashboard_queries import rolling_window_summary
from src.database import get_connection

con = get_connection(str(get_settings().db_path))
st.title('Rolling Setup Behavior')
st.dataframe(rolling_window_summary(con), use_container_width=True)
