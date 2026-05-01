import pandas as pd
import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.rolling_setup_monitor import SECTION_ORDER, compact_table, detail_table, rolling_setup_monitor

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))
st.title('Rolling Setup Monitor')

sections = rolling_setup_monitor(con, setup_dates=5)
if not sections:
    st.info('No setup candidates yet.')
else:
    tabs = st.tabs([str(section['setup_date']) for section in sections])
    for tab, section in zip(tabs, sections):
        with tab:
            summary = section['summary']
            cards = [
                ('Candidates', summary['Candidate Count']),
                ('Clean 1m', summary['Clean 1m ORH']),
                ('Clean 5m', summary['Clean 5m ORH']),
                ('Alt Required', summary['Alternate Means Required']),
                ('No Trigger', summary['No Clean OR Trigger']),
                ('Trending', summary['Trending Higher']),
                ('Failed Low', summary['Failed Setup-Day Low']),
                ('Median Current', summary['Median Current % from Setup Close']),
                ('Median Max Gain', summary['Median Max Gain from Setup Close']),
            ]
            for start in range(0, len(cards), 5):
                cols = st.columns(5)
                for col, (label, value) in zip(cols, cards[start:start + 5]):
                    col.metric(label, value)

            table = section['table']
            for label in SECTION_ORDER:
                subset = compact_table(table, label)
                if subset.empty:
                    continue
                st.subheader(label)
                st.dataframe(subset, width='stretch', hide_index=True)

            with st.expander('Show full detail table', expanded=False):
                st.dataframe(detail_table(table), width='stretch', hide_index=True)
