import streamlit as st

from src.config import get_settings
from src.data_health_indicator import data_health_cache_token, load_data_health_summary, render_data_health_indicator
from src.database import get_connection
from src.performance import PerfTimer, render_perf_debug
from src.watchlist_top_movers import (
    DEFAULT_SETUP_WINDOW,
    SETUP_WINDOW_OPTIONS,
    SORT_OPTIONS,
    TOP_N_OPTIONS,
    load_top_movers,
    top_movers_from_history,
)


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')


TOP_MOVERS_CACHE_VERSION = 'top-movers-hypothetical-portfolio-v2'


@st.cache_data(show_spinner=False)
def load_watchlist_top_movers(db_path: str, cache_version: str):
    con = get_connection(db_path)
    return load_top_movers(con)


db_path = str(get_settings().db_path)
perf = PerfTimer('Watchlist Top Movers')

st.title('Watchlist Top Movers')
st.caption('Top-performing ticker/setup instances from uploaded Back-Watch setup data.')
with perf.measure('Data Health load'):
    health_summary = load_data_health_summary(db_path, data_health_cache_token(db_path))
render_data_health_indicator(health_summary)

top_movers_cache_token = f'{TOP_MOVERS_CACHE_VERSION}:{data_health_cache_token(db_path)}'
with perf.measure('Watchlist Top Movers data build'):
    history, latest_date = load_watchlist_top_movers(db_path, top_movers_cache_token)

if history.empty:
    st.info('No setup candidates yet. Process Back-Watch files to populate watchlist movers.')
else:
    with perf.measure('active table preparation'):
        all_active_result = top_movers_from_history(
            history,
            latest_date=latest_date,
            setup_window='All',
            top_n=20,
            sort_by='Max %',
        )

    st.subheader('Hypothetical Optimal Portfolio')
    st.caption('Descriptive view of currently active 4-5 star names from all available setup dates.')
    if all_active_result.portfolio_table.empty:
        st.info('No active 4–5 star names currently qualify.')
    else:
        st.dataframe(all_active_result.portfolio_table, width='stretch', hide_index=True)

    st.subheader('Top 10 Active Watchlist Movers')
    st.caption('Uses all available setup dates and is not affected by the setup-window filter below.')
    st.caption(f'Active rows: {len(all_active_result.active_table)}')
    if all_active_result.active_table.empty and not all_active_result.audit.empty and 'Active Table Exclusion Reason' in all_active_result.audit:
        reasons = all_active_result.audit['Active Table Exclusion Reason'].fillna('-').astype(str)
        reasons = reasons[reasons.ne('-')].value_counts().head(3)
        if not reasons.empty:
            st.caption('Why empty: ' + '; '.join(f'{reason}: {count}' for reason, count in reasons.items()))
    st.dataframe(all_active_result.active_table, width='stretch', hide_index=True)

    st.subheader('Top Triggered Watchlist Movers')
    st.caption('Filters below apply only to this triggered movers table and its Details / Audit view.')
    filter_cols = st.columns([1.4, 0.8, 1.0])
    with filter_cols[0]:
        setup_window = st.selectbox(
            'Setup Window',
            SETUP_WINDOW_OPTIONS,
            index=SETUP_WINDOW_OPTIONS.index(DEFAULT_SETUP_WINDOW),
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

    with perf.measure('triggered movers display preparation'):
        result = top_movers_from_history(
            history,
            latest_date=latest_date,
            setup_window=setup_window,
            top_n=top_n,
            sort_by=sort_by,
        )

    st.dataframe(result.table, width='stretch', hide_index=True)

    with st.expander('Details / Audit', expanded=False):
        st.dataframe(result.audit, width='stretch', hide_index=True)

render_perf_debug(st, perf)
