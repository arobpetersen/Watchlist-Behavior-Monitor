# Archived from sidebar; legacy feature summary retained for reference.
import streamlit as st

from src.config import get_settings
from src.dashboard_queries import rolling_window_summary
from src.database import get_connection

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))
st.title('Rolling Setup Behavior')
st.dataframe(rolling_window_summary(con), width='stretch', hide_index=True)
