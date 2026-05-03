import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.setup_behavior_overview import setup_behavior_overview


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))

st.title('Setup Behavior Overview')
st.caption('Rolling summary of Back-Watch setup behavior across recent time windows.')

overview = setup_behavior_overview(con)

if overview['summary'].empty:
    st.info('No setup candidates yet. Process Back-Watch files to populate setup behavior history.')
else:
    st.subheader('Historical Summary')
    st.dataframe(overview['summary'], width='stretch', hide_index=True)

    for label, detail in overview['details'].items():
        with st.expander(f'Show {label} tickers', expanded=False):
            st.dataframe(detail, width='stretch', hide_index=True)
