import streamlit as st

from src.config import get_settings
from src.data_health_indicator import data_health_cache_token, load_data_health_summary, render_data_health_indicator
from src.database import get_connection
from src.daily_report import build_daily_report_payload, build_llm_report_prompt, render_daily_report_markdown
from src.monitor_history_loader import MONITOR_HISTORY_CACHE_VERSION, load_cached_monitor_history
from src.performance import PerfTimer, render_perf_debug
from src.setup_behavior_overview import (
    OPENING_BEHAVIOR_MAIN_COLUMNS,
    OPENING_PATH_FILTER_OPTIONS,
    filter_detail_rows,
    main_opening_behavior_table,
    metric_cards_html,
    setup_behavior_overview,
    style_trigger_event_table,
    trigger_event_shift_highlights,
    trigger_event_main_tables,
)


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')


OVERVIEW_CACHE_VERSION = 'setup-overview-daily-report-v1'


@st.cache_data(show_spinner=False)
def load_setup_behavior_overview(db_path: str, cache_version: str, _history) -> tuple[dict, list[dict]]:
    timer = PerfTimer('Setup Behavior Overview Build', enabled=True)
    con = get_connection(db_path)
    overview = setup_behavior_overview(con, history=_history, perf=timer)
    return overview, timer.rows()


def ensure_overview_display_tables(overview: dict) -> dict:
    if 'opening_behavior_main' not in overview:
        overview['opening_behavior_main'] = {
            label: main_opening_behavior_table(table)
            for label, table in overview.get('details', {}).items()
        }
        if not overview['opening_behavior_main']:
            overview['opening_behavior_main'] = {
                label: main_opening_behavior_table(table)
                for label, table in overview.get('opening_behavior', {}).items()
                if set(OPENING_BEHAVIOR_MAIN_COLUMNS).issubset(table.columns)
            }
    if 'trigger_event_main_by_window' not in overview:
        overview['trigger_event_main_by_window'] = trigger_event_main_tables(
            overview.get('trigger_outcome_comparison')
        )
    if 'trigger_event_shift_highlights' not in overview:
        overview['trigger_event_shift_highlights'] = trigger_event_shift_highlights(
            overview.get('trigger_outcome_comparison')
        )
    if 'behavior_insights' not in overview:
        overview['behavior_insights'] = []
    return overview


db_path = str(get_settings().db_path)
perf = PerfTimer('Setup Behavior Overview')

st.title('Setup Behavior Overview')
st.caption('Rolling summary of Back-Watch setup behavior across recent setup-date windows.')
st.caption('D3 High only includes setups with completed D3 data.')
overview_cache_token = f'{OVERVIEW_CACHE_VERSION}:{data_health_cache_token(db_path)}'
monitor_history_cache_token = f'{MONITOR_HISTORY_CACHE_VERSION}:{data_health_cache_token(db_path)}'
with perf.measure('Data Health load'):
    health_summary = load_data_health_summary(db_path, data_health_cache_token(db_path))
render_data_health_indicator(health_summary)

with st.expander('Definitions / Logic', expanded=False):
    st.markdown(
        """
- **Current Status**: current setup state. Active means a trigger-day success has not broken the selected reference low later; Failed D# means the selected reference low failed on that setup-relative day; dash means day-0 fail or unresolved.
- **Trigger Day**: setup-day outcome. Success means a selected trigger/reference held through day 0, Fail means it failed on day 0, and Unresolved means no trigger.
- **PDH**: prior-day high diagnostic. Gap means the stock opened above prior-day high, so the ORH framework governs. Success means PDH broke and held day 0, failed means PDH broke and failed day 0, and dash means PDH did not trigger or is unavailable.
- **1m ORH / 5m ORH**: diagnostic opening-range high results. Success requires a strict high break above ORH and the selected trigger-time reference low holding after trigger.
- **VWAP Reclaim**: qualified VWAP reclaim trigger shown only when the shared trigger stack selects VWAP over fallback labels or a looser ORH trigger. Raw VWAP reclaim diagnostics remain in detail/audit fields.
- **Alt Required**: alternate framework used only when failed/missing OR triggers repair under the existing 15m/close-location rule.
- **Failed OR Trigger**: OR trigger framework failed and no alternate qualification repaired it.
- **Retests**: D0/D1/etc. touches of the selected trigger level while the setup is still active, capped in the table after the first three labels.
- **D3 High**: day-3 high follow-through; overview medians only include rows with completed D3 data.
- **Wide OR notes**: flags opening ranges that are wide versus ATR14.
        """
    )

with perf.measure('shared monitor_history load'):
    history, history_timings = load_cached_monitor_history(db_path, monitor_history_cache_token)
perf.extend(history_timings, prefix='monitor_history detail: ')

with perf.measure('Setup Behavior Overview data build'):
    overview, overview_timings = load_setup_behavior_overview(db_path, overview_cache_token, history)
    overview = ensure_overview_display_tables(overview)
perf.extend(overview_timings, prefix='overview detail: ')

if overview['summary'].empty:
    st.info('No setup candidates yet. Process Back-Watch files to populate setup behavior history.')
else:
    st.subheader('Historical Window Summary')
    st.dataframe(overview['summary'], width='stretch', hide_index=True)

    labels = [window.label for window in overview['windows']]
    if 'setup_behavior_selected_window' not in st.session_state or st.session_state.setup_behavior_selected_window not in labels:
        st.session_state.setup_behavior_selected_window = labels[0]
    selected_window = st.selectbox('Selected Window', labels, key='setup_behavior_selected_window')

    with st.expander('Daily Intelligence Report', expanded=False):
        report_payload = build_daily_report_payload(history, overview)
        latest_date = report_payload.get('latest_setup_date_summary', {}).get('latest_setup_date') or '-'
        st.caption(f'Latest setup date: {latest_date}')
        st.markdown(render_daily_report_markdown(report_payload))
        with st.expander('LLM-ready structured prompt', expanded=False):
            st.code(build_llm_report_prompt(report_payload), language='text')

    st.subheader('Selected Window Snapshot')
    with perf.measure('snapshot display preparation'):
        snapshot_html = overview['snapshot_cards'][selected_window]
    st.markdown(snapshot_html, unsafe_allow_html=True)
    st.write(overview['reads'][selected_window])

    st.subheader('Selected Window Successful Triggers')
    st.dataframe(overview['opening_behavior_main'][selected_window], width='stretch', hide_index=True)
    st.caption(
        'Currently Active and Later Failed are measured among setups where that trigger succeeded. Richer path detail '
        'remains in Supporting Selected-Window Stats.'
    )

    st.subheader('Trigger Event Outcomes Across Windows')
    shift_highlights = overview.get('trigger_event_shift_highlights', {})
    for window_label, table in overview['trigger_event_main_by_window'].items():
        st.markdown(f'**{window_label}**')
        st.dataframe(style_trigger_event_table(table, window_label, shift_highlights), width='stretch', hide_index=True)
    st.caption(
        'Triggered % uses eligible setups. Failed % and Success % use triggered setups. Currently Active, Later Failed, '
        'and Median Max use successful trigger setups only.'
    )
    st.caption('Highlighted cells mark notable Last 5 vs Previous 5 shifts.')

    st.subheader('Supporting Stats / Primary Trigger Outcome')
    with st.expander('Supporting Selected-Window Stats', expanded=False):
        st.markdown('**Opening Path Detail**')
        st.dataframe(overview['opening_behavior'][selected_window], width='stretch', hide_index=True)

        st.markdown('**Trigger Event Detail**')
        for window_label, table in overview['trigger_outcome_by_window'].items():
            st.markdown(f'_{window_label}_')
            st.dataframe(table, width='stretch', hide_index=True)

        st.markdown('**Selected Window Breakdown**')
        st.markdown(metric_cards_html(overview['breakdowns'][selected_window]), unsafe_allow_html=True)

        st.markdown('**Selected Window Mix**')
        mix_cols = st.columns(3)
        for column, (title, table) in zip(mix_cols, overview['mixes'][selected_window].items()):
            with column:
                st.markdown(f'**{title}**')
                st.dataframe(table, width='stretch', hide_index=True)

        st.markdown('**Primary / Final Trigger Outcome**')
        st.dataframe(overview['trigger_quality'][selected_window], width='stretch', hide_index=True)
        st.caption(
            'This groups setups by their final/primary trigger label. For per-trigger success/failure, use Trigger Event Outcomes Across Windows.'
        )

    st.subheader('Selected Window Ticker Detail')
    filter_cols = st.columns(4)
    with filter_cols[0]:
        trigger_level = st.selectbox('Trigger event level', ['All', '1m ORH', '5m ORH', 'VWAP Reclaim', 'PDH', 'Alt Required'], key='setup_behavior_trigger_event_level')
    with filter_cols[1]:
        trigger_result = st.selectbox(
            'Trigger event result',
            ['All', 'success', 'failed', 'blank', 'Gap', 'N/A', 'Not Applicable'],
            key='setup_behavior_trigger_event_result',
        )
    with filter_cols[2]:
        current_status = st.selectbox('Current status', ['All', 'Active', 'Later Failed', 'Unresolved'], key='setup_behavior_current_status_filter')
    with filter_cols[3]:
        opening_path_group = st.selectbox('Opening path group', OPENING_PATH_FILTER_OPTIONS, key='setup_behavior_opening_path_group')
    filtered_detail = filter_detail_rows(
        overview['details'][selected_window],
        trigger_level=trigger_level,
        trigger_result=trigger_result,
        current_status=current_status,
        opening_path_group=opening_path_group,
    )
    st.dataframe(filtered_detail, width='stretch', hide_index=True)

render_perf_debug(st, perf)
