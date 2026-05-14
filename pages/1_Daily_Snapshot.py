import pandas as pd
import streamlit as st
from html import escape

from src.config import get_settings
from src.dashboard_queries import (
    DAILY_WORKFLOW_COLUMNS,
    daily_snapshot_monitor_table,
    dates,
    group_summaries,
    snapshot_table,
)
from src.database import get_connection
from src.daily_snapshot_read import daily_snapshot_day_read_metrics, daily_snapshot_trigger_read_groups
from src.market_context import market_context_for_setup_date, market_move_label
from src.rolling_setup_monitor import (
    apply_setup_rating_updates,
    entry_tactic_dropdown_options,
    format_monitor_table_html,
    rating_dropdown_options,
    setup_dropdown_options,
)
from src.view_refresh import DERIVED_REFRESH_MESSAGE, refresh_derived_watchlist_views

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')


def _missing(value):
    return value is None or value != value


def _fmt_pct(value):
    return '-' if _missing(value) else f'{value * 100:.0f}%'


def _fmt_num(value):
    return '-' if _missing(value) else f'{value:.2f}'


def _fmt_whole_pct(value):
    return '-' if _missing(value) else f'{value * 100:.0f}%'


def _fmt_atr_multiple(value):
    return '-' if _missing(value) else f'{value:.2f}x ATR(14)'


def _snapshot_styles():
    return '''
<style>
.snapshot-top-grid { display: grid; grid-template-columns: minmax(280px, 0.9fr) minmax(420px, 1.55fr); gap: 0.6rem; align-items: stretch; margin: 0.35rem 0 0.65rem 0; }
.snapshot-read-panel { border: 1px solid rgba(250, 250, 250, 0.14); border-radius: 8px; background: rgba(250, 250, 250, 0.045); padding: 0.78rem 0.9rem; }
.snapshot-market-panel { border-left: 3px solid rgba(96, 165, 250, 0.78); }
.snapshot-day-panel { background: rgba(250, 250, 250, 0.06); }
.snapshot-panel-title { color: rgba(250, 250, 250, 0.70); font-size: 0.92rem; font-weight: 850; text-transform: uppercase; margin-bottom: 0.44rem; }
.snapshot-chip-row, .snapshot-trigger-row { display: flex; flex-wrap: wrap; gap: 0.54rem; }
.snapshot-chip { display: inline-flex; align-items: baseline; gap: 0.42rem; padding: 0.44rem 0.64rem; border-radius: 7px; border: 1px solid rgba(250, 250, 250, 0.10); background: rgba(250, 250, 250, 0.064); }
.snapshot-chip span, .snapshot-tile-label { color: rgba(250, 250, 250, 0.62); font-size: 0.82rem; font-weight: 760; }
.snapshot-chip strong { color: rgba(250, 250, 250, 0.96); font-size: 1.08rem; font-weight: 850; }
.snapshot-read-secondary { margin-top: 0.52rem; color: rgba(250, 250, 250, 0.74); font-size: 0.98rem; }
.snapshot-tile-grid { display: grid; grid-template-columns: repeat(4, minmax(112px, 1fr)); gap: 0.55rem; }
.snapshot-tile, .snapshot-trigger-tile { border: 1px solid rgba(250, 250, 250, 0.12); border-radius: 8px; background: rgba(250, 250, 250, 0.075); padding: 0.58rem 0.68rem; }
.snapshot-tile-value { color: rgba(250, 250, 250, 0.98); font-size: 1.18rem; font-weight: 880; line-height: 1.18; margin-top: 0.3rem; }
.snapshot-trigger-panel { margin: 0.55rem 0 0.85rem 0; }
.snapshot-trigger-tile { flex: 0 1 auto; min-width: 10rem; }
.snapshot-trigger-tile h4 { margin: 0 0 0.3rem 0; color: rgba(250, 250, 250, 0.94); font-size: 1.02rem; }
.snapshot-trigger-tile div { color: rgba(250, 250, 250, 0.78); font-size: 0.98rem; }
@media (max-width: 900px) { .snapshot-top-grid { grid-template-columns: 1fr; } .snapshot-tile-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); } }
</style>
'''


def _chip(label, value):
    return f'<span class="snapshot-chip"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></span>'


def _tile(label, value):
    return (
        '<section class="snapshot-tile">'
        f'<div class="snapshot-tile-label">{escape(str(label))}</div>'
        f'<div class="snapshot-tile-value">{escape(str(value))}</div>'
        '</section>'
    )


def _market_context_panel(context):
    if context is None or not getattr(context, 'available', False):
        return '''
<section class="snapshot-read-panel snapshot-market-panel">
  <div class="snapshot-panel-title">Market Context</div>
  <div class="snapshot-read-secondary">Market context unavailable for selected setup date.</div>
</section>
'''
    chips = [
        _chip(context.proxy, _fmt_pct(context.pct_change)),
        _chip('Move', market_move_label(context.pct_change)),
        _chip('Character', context.day_type),
        _chip('Gap', _fmt_pct(context.gap_pct)),
        _chip('Close Position', _fmt_whole_pct(context.close_location)),
        _chip('Range', _fmt_atr_multiple(context.range_vs_atr14)),
    ]
    return f'''
<section class="snapshot-read-panel snapshot-market-panel">
  <div class="snapshot-panel-title">Market Context</div>
  <div class="snapshot-chip-row">{''.join(chips)}</div>
  <div class="snapshot-read-secondary">{escape(context.read)}</div>
</section>
'''


def _day_read_panel(workflow_table):
    tiles = ''.join(_tile(label, value) for label, value in daily_snapshot_day_read_metrics(workflow_table))
    return f'''
<section class="snapshot-read-panel snapshot-day-panel">
  <div class="snapshot-panel-title">Day Read</div>
  <div class="snapshot-tile-grid">{tiles}</div>
</section>
'''


def _trigger_read_panel(workflow_table):
    groups = daily_snapshot_trigger_read_groups(workflow_table)
    body = ''.join(
        '<section class="snapshot-trigger-tile">'
        f'<h4>{escape(label)}</h4><div>{escape(value)}</div>'
        '</section>'
        for label, value in groups
    )
    if not body:
        body = '<div class="snapshot-read-secondary">No notable trigger events.</div>'
    return f'''
<section class="snapshot-read-panel snapshot-trigger-panel">
  <div class="snapshot-panel-title">Trigger Read</div>
  <div class="snapshot-trigger-row">{body}</div>
</section>
'''


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
    workflow_table = daily_snapshot_monitor_table(con, d, include_candidate_id=True)
    workflow_display = workflow_table[DAILY_WORKFLOW_COLUMNS] if 'candidate_id' in workflow_table else workflow_table
    market_context = market_context_for_setup_date(con, d)
    st.markdown(_snapshot_styles(), unsafe_allow_html=True)
    st.markdown(
        '<div class="snapshot-top-grid">'
        + _market_context_panel(market_context)
        + _day_read_panel(workflow_table)
        + '</div>'
        + _trigger_read_panel(workflow_table),
        unsafe_allow_html=True,
    )

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

