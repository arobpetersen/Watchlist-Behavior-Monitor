import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.watchlist_top_movers import (
    SETUP_WINDOW_OPTIONS,
    SORT_OPTIONS,
    TOP_N_OPTIONS,
    load_top_movers,
    top_movers_from_history,
)


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')


@st.cache_data(show_spinner=False)
def load_watchlist_top_movers(db_path: str):
    con = get_connection(db_path)
    return load_top_movers(con)


db_path = str(get_settings().db_path)

st.title('Watchlist Top Movers')
st.caption('Top-performing ticker/setup instances from uploaded Back-Watch setup data.')

history, latest_date = load_watchlist_top_movers(db_path)

if history.empty:
    st.info('No setup candidates yet. Process Back-Watch files to populate watchlist movers.')
else:
    filter_cols = st.columns([1.4, 0.8, 1.0])
    with filter_cols[0]:
        setup_window = st.selectbox(
            'Setup Window',
            SETUP_WINDOW_OPTIONS,
            index=SETUP_WINDOW_OPTIONS.index('Last 20 setup dates'),
            key='top_movers_setup_window',
        )
    with filter_cols[1]:
        top_n = st.selectbox(
            'Top N',
            TOP_N_OPTIONS,
            index=TOP_N_OPTIONS.index(20),
            key='top_movers_top_n',
        )
    with filter_cols[2]:
        sort_by = st.selectbox(
            'Sort By',
            SORT_OPTIONS,
            index=SORT_OPTIONS.index('Max %'),
            key='top_movers_sort_by',
        )

    result = top_movers_from_history(
        history,
        latest_date=latest_date,
        setup_window=setup_window,
        top_n=top_n,
        sort_by=sort_by,
    )

    st.subheader('Top Triggered Watchlist Movers')
    st.dataframe(result.table, width='stretch', hide_index=True)

    with st.expander('Details / Audit', expanded=False):
        st.dataframe(result.audit, width='stretch', hide_index=True)
