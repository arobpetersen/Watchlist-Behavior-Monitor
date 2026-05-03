import streamlit as st

from src.config import get_settings
from src.database import get_connection
from src.or_trigger_audit import audit_for_candidate, setup_dates, tickers_for_setup_date
from src.rolling_setup_monitor import (
    apply_setup_rating_updates,
    detail_table,
    format_monitor_table_html,
    format_summary_blocks_html,
    main_table,
    rating_dropdown_options,
    rolling_setup_monitor,
    setup_dropdown_options,
)

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))
st.title('Rolling Setup Monitor')

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
- **D3 High**: day-3 high follow-through; shown only when completed D3 data is available.
- **Wide OR notes**: flags opening ranges that are wide versus ATR14.
        """
    )

with st.expander('Audit OR Trigger', expanded=False):
    audit_dates = setup_dates(con)
    if not audit_dates:
        st.info('No setup candidates available for audit.')
    else:
        selected_date = st.selectbox('Audit Setup Date', audit_dates, key='or_audit_setup_date')
        audit_tickers = tickers_for_setup_date(con, selected_date)
        if not audit_tickers:
            st.info('No tickers available for this setup date.')
        else:
            selected_ticker = st.selectbox('Audit Ticker', audit_tickers, key='or_audit_ticker')
            audit = audit_for_candidate(con, selected_date, selected_ticker)
            st.caption(
                'Regular session: 09:30 ET to 16:00 ET. '
                '1m OR: 09:30:00 <= timestamp < 09:31:00; breaks start at 09:31. '
                '5m OR: 09:30:00 <= timestamp < 09:35:00; breaks start at 09:35. '
                'Breaks use high > ORH and low < ORL; retests may use low <= trigger level.'
            )
            st.dataframe(audit['audit'], width='stretch', height='auto', hide_index=True)
            st.subheader('First 15 Regular-Session 1m Bars')
            st.dataframe(audit['first_15_bars'], width='stretch', height='auto', hide_index=True)
            st.subheader('Strict OR Break Rows')
            st.dataframe(audit['break_bars'], width='stretch', height='auto', hide_index=True)

sections = rolling_setup_monitor(con, setup_dates=5)
if not sections:
    st.info('No setup candidates yet.')
else:
    for section in sections:
        st.subheader(f"Setup Date: {section['setup_date']}")

        st.markdown(format_summary_blocks_html(section['summary']), unsafe_allow_html=True)

        table = section['table']
        display = main_table(table)
        st.markdown(format_monitor_table_html(display), unsafe_allow_html=True)

        with st.expander('Edit Setup / Rating', expanded=False):
            editable = display[['Ticker', 'Setup', 'Rating']].copy()
            editable.insert(0, 'candidate_id', table['candidate_id'].tolist())

            edited = st.data_editor(
                editable,
                key=f"monitor_metadata_editor_{section['setup_date']}",
                width='stretch',
                hide_index=True,
                column_order=['Ticker', 'Setup', 'Rating'],
                disabled=['Ticker'],
                column_config={
                    'Setup': st.column_config.SelectboxColumn(
                        'Setup',
                        options=setup_dropdown_options(table),
                    ),
                    'Rating': st.column_config.SelectboxColumn(
                        'Rating',
                        options=rating_dropdown_options(table),
                    ),
                },
            )

            if st.button('Save Setup/Rating', key=f"save_monitor_{section['setup_date']}"):
                edited_for_save = edited.copy()
                edited_for_save['candidate_id'] = editable['candidate_id'].tolist()
                changed = apply_setup_rating_updates(con, editable, edited_for_save)
                if changed:
                    st.success(f'Saved Setup/Rating for {changed} row(s).')
                    st.rerun()
                else:
                    st.info('No Setup/Rating changes to save.')

        with st.expander('Show full detail table', expanded=False):
            st.dataframe(detail_table(table), width='stretch', hide_index=True)
