import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.setup_behavior_overview import metric_cards_html, setup_behavior_overview


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))

st.title('Setup Behavior Overview')
st.caption('Rolling summary of Back-Watch setup behavior across recent time windows.')

overview = setup_behavior_overview(con)

if overview['summary'].empty:
    st.info('No setup candidates yet. Process Back-Watch files to populate setup behavior history.')
else:
    st.subheader('Historical Window Comparison')
    st.dataframe(overview['summary'], width='stretch', hide_index=True)

    labels = [window.label for window in overview['windows']]
    selected_window = st.selectbox('Selected Window', labels, index=0)

    st.subheader('Selected Window Breakdown')
    st.markdown(metric_cards_html(overview['breakdowns'][selected_window]), unsafe_allow_html=True)

    st.subheader('Selected Window Read')
    st.write(overview['reads'][selected_window])

    st.subheader('Selected Window Ticker Detail')
    st.dataframe(overview['details'][selected_window], width='stretch', hide_index=True)
