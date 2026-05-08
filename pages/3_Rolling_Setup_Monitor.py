import streamlit as st

from src.config import get_settings
from src.data_health_indicator import data_health_cache_token
from src.database import get_connection
from src.or_trigger_audit import audit_for_candidate, setup_dates, tickers_for_setup_date
from src.performance import PerfTimer, render_perf_debug
from src.rolling_setup_monitor import (
    apply_setup_rating_updates,
    detail_table,
    entry_tactic_dropdown_options,
    format_monitor_table_html,
    format_summary_blocks_html,
    main_table,
    rating_dropdown_options,
    rolling_setup_monitor,
    setup_dropdown_options,
)

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

ROLLING_MONITOR_CACHE_VERSION = 'rolling-monitor-vwap-actionable-display-v3'


@st.cache_data(show_spinner=False)
def load_rolling_setup_sections(db_path: str, cache_version: str):
    timer = PerfTimer('Rolling Setup Monitor Build', enabled=True)
    con = get_connection(db_path)
    return rolling_setup_monitor(con, setup_dates=5, perf=timer), timer.rows()


perf = PerfTimer('Rolling Setup Monitor')
db_path = str(get_settings().db_path)
with perf.measure('DB connection/open'):
    con = get_connection(db_path)
st.title('Rolling Setup Monitor')

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

rolling_cache_token = f'{ROLLING_MONITOR_CACHE_VERSION}:{data_health_cache_token(db_path)}'
with perf.measure('Rolling Setup Monitor data build'):
    sections, build_timings = load_rolling_setup_sections(db_path, rolling_cache_token)
perf.extend(build_timings, prefix='cache miss detail: ')
if not sections:
    st.info('No setup candidates yet.')
else:
    for section in sections:
        st.subheader(f"Setup Date: {section['setup_date']}")

        st.markdown(format_summary_blocks_html(section['summary']), unsafe_allow_html=True)

        table = section['table']
        with perf.measure(f"{section['setup_date']} display preparation"):
            display = main_table(table)
            display_html = format_monitor_table_html(display)
        st.markdown(display_html, unsafe_allow_html=True)

        with st.expander('Edit Setup / Entry Tactic / Rating', expanded=False):
            editable = display[['Ticker', 'Setup', 'Entry Tactic', 'Rating']].copy()
            editable.insert(0, 'candidate_id', table['candidate_id'].tolist())

            edited = st.data_editor(
                editable,
                key=f"monitor_metadata_editor_{section['setup_date']}",
                width='stretch',
                hide_index=True,
                column_order=['Ticker', 'Setup', 'Entry Tactic', 'Rating'],
                disabled=['Ticker'],
                column_config={
                    'Setup': st.column_config.SelectboxColumn(
                        'Setup',
                        options=setup_dropdown_options(table),
                    ),
                    'Entry Tactic': st.column_config.SelectboxColumn(
                        'Entry Tactic',
                        options=entry_tactic_dropdown_options(table),
                    ),
                    'Rating': st.column_config.SelectboxColumn(
                        'Rating',
                        options=rating_dropdown_options(table),
                    ),
                },
            )

            if st.button('Save Manual Fields', key=f"save_monitor_{section['setup_date']}"):
                edited_for_save = edited.copy()
                edited_for_save['candidate_id'] = editable['candidate_id'].tolist()
                try:
                    changed = apply_setup_rating_updates(con, editable, edited_for_save)
                    if changed:
                        st.cache_data.clear()
                        st.success('Saved setup/rating changes.')
                        st.rerun()
                    else:
                        st.info('No changes to save.')
                except Exception as exc:
                    st.error(f'Save failed: {exc}')

        with st.expander('Show full detail table', expanded=False):
            with perf.measure(f"{section['setup_date']} detail table preparation"):
                detail = detail_table(table)
            st.dataframe(detail, width='stretch', hide_index=True)

render_perf_debug(st, perf)
