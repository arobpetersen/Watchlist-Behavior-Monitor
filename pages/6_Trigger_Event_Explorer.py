import pandas as pd
import streamlit as st

from src.config import get_settings
from src.data_health_indicator import data_health_cache_token, load_data_health_summary, render_data_health_indicator
from src.materialized_monitor_history import monitor_history_source_token
from src.monitor_history_loader import MONITOR_HISTORY_CACHE_VERSION, load_cached_monitor_history
from src.performance import PerfTimer, render_perf_debug
from src.trigger_event_explorer import (
    CLOSE_BE_OPTIONS,
    DEFAULT_WINDOW,
    ExplorerFilters,
    SORT_OPTIONS,
    TRIGGER_DAY_OPTIONS,
    TRIGGER_ORDER,
    WINDOW_OPTIONS,
    active_filter_summary,
    apply_filters,
    csv_bytes,
    dataframe_height,
    explorer_rows,
    option_values,
    rating_filter_values,
    summary_cards,
)


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

perf = PerfTimer('Trigger Event Explorer')
db_path = str(get_settings().db_path)

st.title('Trigger Event Explorer')
st.caption('Filter and export trigger-level setup rows from canonical monitor history.')
st.markdown(
    '''
<style>
.explorer-metric-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 0.45rem;
  margin: 0.35rem 0 0.7rem 0;
}
.explorer-metric {
  border: 1px solid rgba(250, 250, 250, 0.10);
  border-radius: 7px;
  background: rgba(250, 250, 250, 0.045);
  padding: 0.46rem 0.6rem;
}
.explorer-metric span {
  display: block;
  color: rgba(250, 250, 250, 0.62);
  font-size: 0.78rem;
  font-weight: 760;
  line-height: 1.15;
}
.explorer-metric strong {
  display: block;
  color: rgba(250, 250, 250, 0.96);
  font-size: 1.05rem;
  font-weight: 850;
  line-height: 1.2;
  margin-top: 0.16rem;
}
</style>
''',
    unsafe_allow_html=True,
)

cache_token = data_health_cache_token(db_path)
monitor_history_cache_token = f'{MONITOR_HISTORY_CACHE_VERSION}:{monitor_history_source_token(db_path)}'
with perf.measure('Data Health load'):
    health_summary = load_data_health_summary(db_path, cache_token)
render_data_health_indicator(health_summary, compact=True)

with perf.measure('shared monitor_history load'):
    history, history_timings = load_cached_monitor_history(db_path, monitor_history_cache_token)
perf.extend(history_timings, prefix='monitor_history detail: ')

control_cols = st.columns([1.15, 1.1, 1.0, 1.1, 1.1, 0.95])
with control_cols[0]:
    window = st.selectbox('Setup date window', WINDOW_OPTIONS, index=WINDOW_OPTIONS.index(DEFAULT_WINDOW))

base_rows = explorer_rows(history, window)

with control_cols[1]:
    trigger_options = [value for value in TRIGGER_ORDER if value == 'All' or value in set(base_rows.get('Trigger', pd.Series(dtype=str)).astype(str))]
    trigger = st.selectbox('Trigger', trigger_options)
with control_cols[2]:
    trigger_day = st.selectbox('Trigger Day', TRIGGER_DAY_OPTIONS)
with control_cols[3]:
    current_status = st.selectbox('Current Status', ['All', 'Active', 'D0 Fail', 'Failed After D0', 'Unresolved / blank'])
with control_cols[4]:
    ticker_search = st.text_input('Ticker search', '')
with control_cols[5]:
    sort_by = st.selectbox('Sort by', SORT_OPTIONS)

with st.expander('Advanced Filters', expanded=False):
    filter_cols = st.columns([1.1, 1.1, 0.9, 0.9])
    with filter_cols[0]:
        setup = st.selectbox('Setup', option_values(base_rows, 'Setup'))
    with filter_cols[1]:
        entry_tactic = st.selectbox('Entry Tactic', option_values(base_rows, 'Entry Tactic'))
    with filter_cols[2]:
        rating = st.selectbox('Rating', rating_filter_values(base_rows))
    with filter_cols[3]:
        close_be = st.selectbox('Close < BE', CLOSE_BE_OPTIONS)

    numeric_cols = st.columns([1, 1, 2])
    with numeric_cols[0]:
        min_current_enabled = st.checkbox('Min Current %')
        min_current_pct = st.number_input('Current % at least', value=0.0, step=1.0, disabled=not min_current_enabled)
    with numeric_cols[1]:
        min_max_enabled = st.checkbox('Min Max %')
        min_max_pct = st.number_input('Max % at least', value=0.0, step=1.0, disabled=not min_max_enabled)

filters = ExplorerFilters(
    window=window,
    trigger=trigger,
    trigger_day=trigger_day,
    current_status=current_status,
    setup=setup,
    entry_tactic=entry_tactic,
    rating=rating,
    close_be=close_be,
    ticker_search=ticker_search,
    min_current_pct=float(min_current_pct) if min_current_enabled else None,
    min_max_pct=float(min_max_pct) if min_max_enabled else None,
    sort_by=sort_by,
)

with perf.measure('filter rows'):
    filtered_rows = apply_filters(base_rows, filters)

st.caption(active_filter_summary(filters))

cards = summary_cards(filtered_rows)
st.markdown(
    '<div class="explorer-metric-strip">'
    + ''.join(
        '<section class="explorer-metric">'
        f'<span>{card["Metric"]}</span>'
        f'<strong>{card["Value"]}</strong>'
        '</section>'
        for card in cards
    )
    + '</div>',
    unsafe_allow_html=True,
)

result_title_col, download_col = st.columns([0.68, 0.32])
with result_title_col:
    st.subheader(f'Filtered Results - {len(filtered_rows)} rows')
with download_col:
    st.download_button(
        'Download filtered rows as CSV',
        data=csv_bytes(filtered_rows),
        file_name='trigger_event_explorer_filtered.csv',
        mime='text/csv',
        width='stretch',
    )

if filtered_rows.empty:
    st.info('No rows match the selected filters.')
else:
    st.dataframe(filtered_rows, width='stretch', height=dataframe_height(len(filtered_rows)), hide_index=True)

render_perf_debug(st, perf)
