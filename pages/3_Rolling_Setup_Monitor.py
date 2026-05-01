import pandas as pd
import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.rolling_setup_monitor import rolling_setup_monitor

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))
st.title('Rolling Setup Monitor')

sections = rolling_setup_monitor(con, setup_dates=5)
if not sections:
    st.info('No setup candidates yet.')
else:
    for section in sections:
        st.subheader(f"Setup Date: {section['setup_date']}")
        summary = pd.DataFrame([section['summary']])
        st.dataframe(summary, width='stretch', hide_index=True)
        st.dataframe(section['table'], width='stretch', hide_index=True)
