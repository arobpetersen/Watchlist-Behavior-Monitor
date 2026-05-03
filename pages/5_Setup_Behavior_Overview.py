import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.setup_behavior_overview import metric_cards_html, setup_behavior_overview


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))

st.title('Setup Behavior Overview')
st.caption('Rolling summary of Back-Watch setup behavior across recent time windows.')
st.caption('D3 High only includes setups with completed D3 data.')

with st.expander('Definitions / Logic', expanded=False):
    st.markdown(
        """
- **Current Status**: current setup state. Active means a trigger-day success has not failed later; Failed D1/D2/D3 means the selected reference low failed after setup day; dash means day-0 fail or unresolved.
- **Trigger Day**: setup-day outcome. Success means a selected trigger/reference held through day 0, Fail means it failed on day 0, and Unresolved means no trigger.
- **PDH**: prior-day high diagnostic. Dash means PDH is not applicable or did not trigger, success means PDH broke and held day 0, and failed means PDH broke and failed day 0.
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

    st.subheader('Selected Window Breakdown')
    st.markdown(metric_cards_html(overview['breakdowns'][selected_window]), unsafe_allow_html=True)

    st.subheader('Selected Window Read')
    st.write(overview['reads'][selected_window])

    st.subheader('Selected Window Ticker Detail')
    st.dataframe(overview['details'][selected_window], width='stretch', hide_index=True)
