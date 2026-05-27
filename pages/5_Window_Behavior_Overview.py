import streamlit as st

from src.config import get_settings
from src.data_health_indicator import data_health_cache_token, load_data_health_summary, render_data_health_indicator
from src.database import get_connection
from src.daily_report import build_daily_report_payload, render_daily_report_markdown
from src.market_context import format_market_context_strip, market_context_for_setup_date
from src.materialized_monitor_history import monitor_history_source_token
from src.monitor_history_loader import MONITOR_HISTORY_CACHE_VERSION, load_cached_monitor_history
from src.performance import PerfTimer, render_perf_debug
from src.setup_behavior_overview import (
    OPENING_BEHAVIOR_MAIN_COLUMNS,
    failure_timing_by_trigger_table,
    failure_timing_by_window_table,
    filter_detail_rows,
    main_opening_behavior_table,
    metric_cards_html,
    setup_behavior_overview,
    style_trigger_event_table,
    trigger_failure_trend_matrix,
    trigger_event_shift_highlights,
    trigger_event_main_tables,
)
from src.view_refresh import DERIVED_REFRESH_MESSAGE, refresh_derived_watchlist_views


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')


OVERVIEW_CACHE_VERSION = 'setup-overview-last2-pulse-v1'


@st.cache_data(show_spinner=False)
def load_setup_behavior_overview(db_path: str, cache_version: str, _history) -> tuple[dict, list[dict]]:
    timer = PerfTimer('Window Behavior Overview Build', enabled=True)
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
    if 'trigger_failure_trend' not in overview:
        overview['trigger_failure_trend'] = trigger_failure_trend_matrix(
            overview.get('trigger_outcome_comparison')
        )
    if 'failure_timing_by_window' not in overview:
        overview['failure_timing_by_window'] = failure_timing_by_window_table(overview.get('details', {}))
    if 'failure_timing_by_trigger' not in overview:
        overview['failure_timing_by_trigger'] = {
            label: failure_timing_by_trigger_table(table)
            for label, table in overview.get('details', {}).items()
        }
    if 'trigger_event_shift_highlights' not in overview:
        overview['trigger_event_shift_highlights'] = trigger_event_shift_highlights(
            overview.get('trigger_outcome_comparison')
        )
    if 'behavior_insights' not in overview:
        overview['behavior_insights'] = []
    return overview


db_path = str(get_settings().db_path)
perf = PerfTimer('Window Behavior Overview')

st.title('Window Behavior Overview')
st.caption('Compare setup behavior across recent back-watch windows.')
st.caption('Median D3 High only includes triggered rows that survived through D3.')
if st.button('Refresh derived views from database', key='setup_overview_refresh_derived', help='Refreshes cached monitor/report views after data or manual metadata changes.'):
    refresh_derived_watchlist_views(load_setup_behavior_overview, db_path=db_path, rebuild_materialized_history=True)
    st.session_state['derived_views_refreshed'] = True
    st.rerun()
if st.session_state.pop('derived_views_refreshed', False):
    st.success(DERIVED_REFRESH_MESSAGE)
monitor_source_token = monitor_history_source_token(db_path)
overview_cache_token = f'{OVERVIEW_CACHE_VERSION}:{monitor_source_token}'
monitor_history_cache_token = f'{MONITOR_HISTORY_CACHE_VERSION}:{monitor_source_token}'
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
- **D3 High**: raw day-3 high follow-through in detail rows; overview medians only include triggered rows that survived through D3.
- **Wide OR notes**: flags opening ranges that are wide versus ATR14.
        """
    )

with perf.measure('shared monitor_history load'):
    history, history_timings = load_cached_monitor_history(db_path, monitor_history_cache_token)
perf.extend(history_timings, prefix='monitor_history detail: ')

with perf.measure('Window Behavior Overview data build'):
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
        if latest_date != '-':
            report_con = get_connection(db_path)
            report_payload['market_context'] = format_market_context_strip(market_context_for_setup_date(report_con, latest_date))
        st.caption(f'Latest setup date: {latest_date}')
        st.markdown(render_daily_report_markdown(report_payload))

    st.subheader('Selected Window Snapshot')
    with perf.measure('snapshot display preparation'):
        snapshot_html = overview['snapshot_cards'][selected_window]
    st.markdown(snapshot_html, unsafe_allow_html=True)
    st.write(overview['reads'][selected_window])

    st.subheader('Selected Window Successful Triggers')
    st.dataframe(overview['opening_behavior_main'][selected_window], width='stretch', hide_index=True)
    st.caption(
        'Currently Active and Failed After D0 are measured among setups where that trigger succeeded. Richer path detail '
        'remains in Supporting Selected-Window Stats.'
    )

    st.subheader('Trigger Success Trend')
    st.caption('Cells show Success % (successful trigger attempts / triggered attempts). Last 2 is an immediate pulse.')
    st.dataframe(overview['trigger_failure_trend'], width='stretch', hide_index=True)
    st.markdown('**Trigger Shift Read**')
    st.caption('Trigger Shift Read compares Last 5 vs Previous 5.')
    st.dataframe(overview['trigger_shift_read'], width='stretch', hide_index=True)

    st.subheader('Failure Timing Distribution')
    st.caption('Immediate Pulse = Last 2 setup dates. Cells show % of triggered rows (bucket count / triggered rows). D0 Fail includes Trigger Day Fail or Current Status Failed D0.')
    st.dataframe(overview['failure_timing_by_window'], width='stretch', hide_index=True)
    with st.expander('Failure Timing by Trigger', expanded=False):
        st.caption('Selected-window breakdown. Trigger Success Trend answers whether attempts are working; this table shows when triggered rows fail.')
        st.dataframe(overview['failure_timing_by_trigger'].get(selected_window), width='stretch', hide_index=True)

    st.subheader('Trigger Event Outcomes Across Windows')
    shift_highlights = overview.get('trigger_event_shift_highlights', {})
    for window_label, table in overview['trigger_event_main_by_window'].items():
        st.markdown(f'**{window_label}**')
        st.dataframe(style_trigger_event_table(table, window_label, shift_highlights), width='stretch', hide_index=True)
    st.caption(
        'Triggered % uses eligible setups. Failed % and Success % use triggered setups. Currently Active, Failed After D0, '
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

    st.subheader('Selected Window Ticker Detail Preview')
    st.caption('Detailed trigger-event row research now lives in Trigger Event Explorer. Use it for full filtering and CSV export.')
    with st.expander('Preview selected-window rows', expanded=False):
        filtered_detail = filter_detail_rows(overview['details'][selected_window]).head(10)
        st.dataframe(filtered_detail, width='stretch', hide_index=True)

render_perf_debug(st, perf)
