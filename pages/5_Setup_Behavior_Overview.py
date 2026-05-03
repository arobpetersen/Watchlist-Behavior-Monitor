import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.setup_behavior_overview import metric_cards_html, setup_behavior_overview


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))

st.title('Setup Behavior Overview')
st.caption('Rolling summary of Back-Watch setup behavior across recent setup-date windows.')
st.caption('D3 High only includes setups with completed D3 data.')

with st.expander('Definitions / Logic', expanded=False):
    st.markdown(
        """
- **Current Status**: current setup state. Active means a trigger-day success has not failed later; Failed D1/D2/D3 means the selected reference low failed after setup day; dash means day-0 fail or unresolved.
- **Trigger Day**: setup-day outcome. Success means a selected trigger/reference held through day 0, Fail means it failed on day 0, and Unresolved means no trigger.
- **PDH**: prior-day high diagnostic. Gap means the stock opened above prior-day high, so the ORH framework governs. Success means PDH broke and held day 0, failed means PDH broke and failed day 0, and dash means PDH did not trigger or is unavailable.
- **1m ORH / 5m ORH**: diagnostic opening-range high results. Success requires a strict high break above ORH and the selected trigger-time reference low holding after trigger.
- **Alt Required**: alternate framework used only when failed/missing OR triggers repair under the existing 15m/close-location rule.
- **Failed OR Trigger**: OR trigger framework failed and no alternate qualification repaired it.
- **Retest**: first D0/D1/D2/D3 touch of the selected trigger level.
- **D3 High**: day-3 high follow-through; overview medians only include rows with completed D3 data.
- **Wide OR notes**: flags opening ranges that are wide versus ATR14.
        """
    )

overview = setup_behavior_overview(con)

if overview['summary'].empty:
    st.info('No setup candidates yet. Process Back-Watch files to populate setup behavior history.')
else:
    st.subheader('Historical Window Comparison')
    st.dataframe(overview['summary'], width='stretch', hide_index=True)

    labels = [window.label for window in overview['windows']]
    selected_window = st.selectbox('Selected Window', labels, index=0)

    st.subheader('Selected Window Snapshot')
    st.markdown(overview['snapshot_cards'][selected_window], unsafe_allow_html=True)

    st.subheader('Selected Window Breakdown')
    st.markdown(metric_cards_html(overview['breakdowns'][selected_window]), unsafe_allow_html=True)

    st.subheader('Selected Window Mix')
    mix_cols = st.columns(3)
    for column, (title, table) in zip(mix_cols, overview['mixes'][selected_window].items()):
        with column:
            st.markdown(f'**{title}**')
            st.dataframe(table, width='stretch', hide_index=True)

    st.subheader('Opening Behavior / Trigger Path')
    st.dataframe(overview['opening_behavior'][selected_window], width='stretch', hide_index=True)
    st.caption(
        'Opening behavior separates clean early follow-through from early trigger failure followed by later reclaim. '
        'This helps distinguish an aggressive market from a choppy but still constructive market.'
    )
    st.caption(
        'Path rows use the displayed/applicable PDH, 1m ORH, and 5m ORH results from Rolling Setup Monitor; '
        'hidden raw diagnostics remain in the detail/audit views.'
    )

    st.subheader('Trigger Outcome Comparison')
    st.dataframe(overview['trigger_outcome_comparison'], width='stretch', hide_index=True)

    st.subheader('Trigger Quality')
    st.dataframe(overview['trigger_quality'][selected_window], width='stretch', hide_index=True)

    st.subheader('Selected Window Read')
    st.write(overview['reads'][selected_window])

    st.subheader('Selected Window Ticker Detail')
    st.dataframe(overview['details'][selected_window], width='stretch', hide_index=True)
