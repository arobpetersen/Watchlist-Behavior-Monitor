import streamlit as st

from src.config import get_settings
from src.data_health_indicator import data_health_cache_token, load_data_health_summary, render_data_health_indicator
from src.monitor_history_loader import MONITOR_HISTORY_CACHE_VERSION, load_cached_monitor_history
from src.performance import PerfTimer, render_perf_debug
from src.setup_performance import (
    build_setup_entry_tactic_summary,
    build_setup_summary,
    filter_setup_performance_rows,
    setup_performance_cards,
)
from src.view_refresh import DERIVED_REFRESH_MESSAGE, refresh_derived_watchlist_views


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')


perf = PerfTimer('Setup Performance')
db_path = str(get_settings().db_path)

st.title('Setup Performance')
st.caption('Concise setup-level read of manually logged Setup values using canonical Rolling Setup Monitor rows.')
st.caption('No status, lifecycle, Current %, Max %, or metadata-save logic is recalculated here.')

if st.button('Refresh derived views from database', key='setup_performance_refresh_derived'):
    refresh_derived_watchlist_views()
    st.session_state['derived_views_refreshed'] = True
    st.rerun()
if st.session_state.pop('derived_views_refreshed', False):
    st.success(DERIVED_REFRESH_MESSAGE)

with perf.measure('Data Health load'):
    health_summary = load_data_health_summary(db_path, data_health_cache_token(db_path))
render_data_health_indicator(health_summary)

with st.expander('Definitions / Logic', expanded=False):
    st.markdown(
        """
- **Count**: candidate rows in the filtered Rolling Setup Monitor history.
- **Active**: Current Status equals Active.
- **Failed D0**: Current Status equals Failed D0.
- **Failed After D0**: Current Status is Failed D1 or later.
- **Failure %**: Failed D0 plus Failed After D0 divided by Count.
- **Close < BE %**: rows where Close < BE is Yes/true.
- **Retested D0 / Retested After D0**: parsed from Retests / Retest Days Raw.
- **Current %, Max %, D3 High %**: existing monitor values, using raw monitor percent fields when present.
- **Rating Avg**: numeric ratings only; blank ratings are ignored.
- **Sample**: Small sample under 5, Developing from 5 to 14, Useful sample at 15 or more.
        """
    )

history_cache_token = f'{MONITOR_HISTORY_CACHE_VERSION}:{data_health_cache_token(db_path)}'
with perf.measure('shared monitor_history load'):
    history, history_timings = load_cached_monitor_history(db_path, history_cache_token)
perf.extend(history_timings, prefix='monitor_history detail: ')

if history.empty:
    st.info('No setup candidates yet. Process Back-Watch files to populate setup performance history.')
else:
    filter_cols = st.columns(4)
    with filter_cols[0]:
        setup_window = st.selectbox(
            'Setup date window',
            ['Last 5 setup dates', 'Last 10 setup dates', 'Last 20 setup dates', 'All'],
            index=1,
            key='setup_performance_window',
        )
    with filter_cols[1]:
        rating_filter = st.selectbox(
            'Rating filter',
            ['All', '4-5 only', '3+ only'],
            key='setup_performance_rating',
        )
    with filter_cols[2]:
        status_filter = st.selectbox(
            'Current Status filter',
            ['All', 'Active only', 'Failed only'],
            key='setup_performance_status',
        )
    with filter_cols[3]:
        sort_by = st.selectbox(
            'Sort setup table',
            ['Count', 'Failure %', 'Median Max %'],
            key='setup_performance_sort',
        )

    with perf.measure('setup performance aggregation'):
        filtered = filter_setup_performance_rows(
            history,
            setup_date_window=setup_window,
            rating_filter=rating_filter,
            current_status_filter=status_filter,
        )
        summary = build_setup_summary(filtered, sort_by=sort_by)
        tactic_summary = build_setup_entry_tactic_summary(filtered)
        cards = setup_performance_cards(summary)

    if summary.empty:
        st.info('No rows match the selected setup performance filters.')
    else:
        card_cols = st.columns(len(cards))
        for column, (_, card) in zip(card_cols, cards.iterrows()):
            with column:
                st.metric(card['Metric'], card['Value'], help=card['Detail'])
                st.caption(card['Detail'])

        st.subheader('Setup Summary')
        st.dataframe(summary, width='stretch', hide_index=True)
        st.caption('Blank or null Setup values are grouped as Unclassified. Highest/best cards ignore samples under 5 unless no setup has enough sample.')

        with st.expander('Setup x Entry Tactic', expanded=False):
            st.dataframe(tactic_summary, width='stretch', hide_index=True)
            st.caption('Entry Tactic blanks are grouped as Unclassified.')

render_perf_debug(st, perf)
