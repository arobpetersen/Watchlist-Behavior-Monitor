import pandas as pd
import streamlit as st

from src.config import get_settings
from src.dashboard_queries import (
    DAILY_WORKFLOW_COLUMNS,
    daily_snapshot_monitor_table,
    daily_snapshot_summary_groups,
    dates,
    group_summaries,
    snapshot_metrics,
    snapshot_table,
)
from src.database import get_connection
from src.market_context import format_market_context_strip, market_context_for_setup_date
from src.rolling_setup_monitor import (
    apply_setup_rating_updates,
    entry_tactic_dropdown_options,
    format_monitor_table_html,
    rating_dropdown_options,
    setup_dropdown_options,
)
from src.setup_behavior_overview import metric_cards_html
from src.view_refresh import DERIVED_REFRESH_MESSAGE, refresh_derived_watchlist_views

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')


def _missing(value):
    return value is None or value != value


def _fmt_pct(value):
    return '—' if _missing(value) else f'{value * 100:.0f}%'


def _fmt_num(value):
    return '—' if _missing(value) else f'{value:.2f}'


con = get_connection(str(get_settings().db_path))
st.title('Setup Day Snapshot')
if st.button('Refresh derived views from database', key='daily_snapshot_refresh_derived'):
    refresh_derived_watchlist_views()
    st.session_state['derived_views_refreshed'] = True
    st.rerun()
if st.session_state.pop('derived_views_refreshed', False):
    st.success(DERIVED_REFRESH_MESSAGE)
all_dates = dates(con)
if not all_dates:
    st.info('No data yet. Run python -m src.run_daily')
else:
    d = st.selectbox('Setup Date', all_dates)
    market_context = market_context_for_setup_date(con, d)
    st.caption(f'Market Context: {format_market_context_strip(market_context)}')
    if market_context.available:
        st.caption(market_context.read)
    m = snapshot_metrics(con, d)
    workflow_table = daily_snapshot_monitor_table(con, d, include_candidate_id=True)
    workflow_display = workflow_table[DAILY_WORKFLOW_COLUMNS] if 'candidate_id' in workflow_table else workflow_table
    summary_groups = daily_snapshot_summary_groups(m, workflow_table)
    st.markdown(metric_cards_html(summary_groups), unsafe_allow_html=True)

    st.subheader('Setup Candidates')
    st.markdown(format_monitor_table_html(workflow_display), unsafe_allow_html=True)

    st.subheader('Edit Selected Candidate')
    metadata_columns = ['candidate_id', 'Ticker', 'Setup', 'Entry Tactic', 'Rating']
    metadata_candidates = workflow_table[metadata_columns].copy() if set(metadata_columns).issubset(workflow_table.columns) else pd.DataFrame(columns=metadata_columns)
    if metadata_candidates.empty:
        st.info('No setup candidates available to edit for this date.')
    else:
        duplicate_tickers = metadata_candidates['Ticker'].duplicated(keep=False)
        candidate_options = metadata_candidates['candidate_id'].tolist()

        def _candidate_label(candidate_id):
            row = metadata_candidates.loc[metadata_candidates['candidate_id'].eq(candidate_id)].iloc[0]
            ticker = row['Ticker']
            return f'{ticker} ({candidate_id})' if bool(duplicate_tickers.loc[row.name]) else ticker

        selected_candidate_id = st.selectbox(
            'Ticker',
            candidate_options,
            format_func=_candidate_label,
            key=f'daily_metadata_candidate_{d}',
        )
        current = metadata_candidates.loc[metadata_candidates['candidate_id'].eq(selected_candidate_id)].iloc[0]
        original = pd.DataFrame([current.to_dict()])

        setup_options = setup_dropdown_options(metadata_candidates)
        entry_tactic_options = entry_tactic_dropdown_options(metadata_candidates)
        rating_options = rating_dropdown_options(metadata_candidates)

        def _option_index(options, value):
            return options.index(value) if value in options else 0

        col_setup, col_entry, col_rating, col_save = st.columns([2, 2, 1, 1])
        setup_value = col_setup.selectbox(
            'Setup',
            setup_options,
            index=_option_index(setup_options, current['Setup']),
            key=f'daily_metadata_setup_{d}_{current["candidate_id"]}',
        )
        entry_tactic_value = col_entry.selectbox(
            'Entry Tactic',
            entry_tactic_options,
            index=_option_index(entry_tactic_options, current['Entry Tactic']),
            key=f'daily_metadata_entry_tactic_{d}_{current["candidate_id"]}',
        )
        rating_value = col_rating.selectbox(
            'Rating',
            rating_options,
            index=_option_index(rating_options, current['Rating']),
            key=f'daily_metadata_rating_{d}_{current["candidate_id"]}',
        )

        if col_save.button('Save', key=f'daily_metadata_save_{d}_{current["candidate_id"]}'):
            edited = original.copy()
            edited.loc[0, 'Setup'] = setup_value
            edited.loc[0, 'Entry Tactic'] = entry_tactic_value
            edited.loc[0, 'Rating'] = rating_value
            try:
                changed = apply_setup_rating_updates(con, original, edited)
                if changed:
                    refresh_derived_watchlist_views()
                    st.session_state['daily_metadata_saved'] = True
                    st.success('Saved setup metadata.')
                    st.rerun()
                else:
                    st.info('No changes to save.')
            except Exception as exc:
                st.error(f'Save failed: {exc}')

    if st.session_state.pop('daily_metadata_saved', False):
        st.success('Saved setup metadata.')

    with st.expander('Daily Feature Detail', expanded=False):
        st.dataframe(snapshot_table(con, d), width='stretch', hide_index=True)

    st.subheader('Group Summaries')
    tabs = st.tabs(['Rating Bucket', 'Setup', 'Focus'])
    tabs[0].dataframe(group_summaries(con, d, 'rating_bucket'), width='stretch', hide_index=True)
    tabs[1].dataframe(group_summaries(con, d, 'setup'), width='stretch', hide_index=True)
    tabs[2].dataframe(group_summaries(con, d, 'focus'), width='stretch', hide_index=True)
