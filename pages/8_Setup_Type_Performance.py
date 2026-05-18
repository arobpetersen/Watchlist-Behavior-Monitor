import streamlit as st
from html import escape

from src.config import get_settings
from src.data_health_indicator import data_health_cache_token, load_data_health_summary, render_data_health_indicator
from src.monitor_history_loader import MONITOR_HISTORY_CACHE_VERSION, load_cached_monitor_history
from src.performance import PerfTimer, render_perf_debug
from src.setup_performance import (
    build_setup_entry_tactic_summary,
    build_setup_failure_trend,
    build_setup_summary,
    filter_setup_performance_rows,
    setup_performance_cards,
)
from src.view_refresh import DERIVED_REFRESH_MESSAGE, refresh_derived_watchlist_views


st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')


def _setup_performance_styles() -> str:
    return '''
<style>
.setup-perf-controls {
  border: 1px solid rgba(250, 250, 250, 0.10);
  border-radius: 8px;
  background: rgba(250, 250, 250, 0.035);
  padding: 0.65rem 0.75rem 0.35rem 0.75rem;
  margin: 0.45rem 0 0.75rem 0;
}
.setup-perf-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.62rem;
  margin: 0.45rem 0 0.85rem 0;
}
.setup-perf-card {
  border: 1px solid rgba(250, 250, 250, 0.12);
  border-radius: 8px;
  background: rgba(250, 250, 250, 0.055);
  padding: 0.74rem 0.82rem;
  min-height: 5.7rem;
}
.setup-perf-card-label {
  color: rgba(250, 250, 250, 0.62);
  font-size: 0.82rem;
  font-weight: 780;
  text-transform: uppercase;
  margin-bottom: 0.34rem;
}
.setup-perf-card-value {
  color: rgba(250, 250, 250, 0.98);
  font-size: 1.18rem;
  font-weight: 870;
  line-height: 1.18;
  overflow-wrap: anywhere;
}
.setup-perf-card-detail {
  color: rgba(250, 250, 250, 0.68);
  font-size: 0.9rem;
  line-height: 1.25;
  margin-top: 0.44rem;
}
.setup-perf-section-caption {
  color: rgba(250, 250, 250, 0.66);
  margin: -0.3rem 0 0.55rem 0;
}
</style>
'''


def _card_lookup(cards, metric: str) -> dict:
    if cards is None or cards.empty:
        return {'Value': '-', 'Detail': '-'}
    match = cards[cards['Metric'].eq(metric)]
    if match.empty:
        return {'Value': '-', 'Detail': '-'}
    return match.iloc[0].to_dict()


def _setup_perf_card(label: str, value: str, detail: str) -> str:
    return (
        '<section class="setup-perf-card">'
        f'<div class="setup-perf-card-label">{escape(str(label))}</div>'
        f'<div class="setup-perf-card-value">{escape(str(value))}</div>'
        f'<div class="setup-perf-card-detail">{escape(str(detail))}</div>'
        '</section>'
    )


def _setup_perf_cards_html(cards, summary) -> str:
    total = _card_lookup(cards, 'Total Classified Setups')
    setup_types = _card_lookup(cards, 'Setup Types')
    highest_active = _card_lookup(cards, 'Highest Active Rate')
    lowest_failure = _card_lookup(cards, 'Lowest Failure Setup')
    highest_failure = _card_lookup(cards, 'Highest Failure Setup')
    unclassified = _card_lookup(cards, 'Unclassified Count')
    items = [
        _setup_perf_card('Classified Setups', total.get('Value', '-'), total.get('Detail', '-')),
        _setup_perf_card('Setup Types', setup_types.get('Value', '-'), setup_types.get('Detail', '-')),
        _setup_perf_card('Highest Active Rate', highest_active.get('Value', '-'), highest_active.get('Detail', '-')),
        _setup_perf_card('Lowest Failure', lowest_failure.get('Value', '-'), lowest_failure.get('Detail', '-')),
        _setup_perf_card('Highest Failure', highest_failure.get('Value', '-'), highest_failure.get('Detail', '-')),
        _setup_perf_card('Unclassified', unclassified.get('Value', '-'), unclassified.get('Detail', '-')),
    ]
    return f'<div class="setup-perf-card-grid">{"".join(items)}</div>'


perf = PerfTimer('Setup Type Performance')
db_path = str(get_settings().db_path)

st.title('Setup Type Performance')
st.caption('Setup-level read of manually logged setup types using canonical monitor rows.')
st.markdown(_setup_performance_styles(), unsafe_allow_html=True)

cache_token = data_health_cache_token(db_path)

control_refresh_col, control_note_col = st.columns([0.32, 0.68])
if control_refresh_col.button(
    'Refresh derived views from database',
    key='setup_performance_refresh_derived',
    help='Refreshes cached monitor/report views after data or manual metadata changes.',
):
    refresh_derived_watchlist_views()
    st.session_state['derived_views_refreshed'] = True
    st.rerun()
control_note_col.caption('Refreshes cached monitor/report views after data or manual metadata changes.')
if st.session_state.pop('derived_views_refreshed', False):
    st.success(DERIVED_REFRESH_MESSAGE)

with perf.measure('Data Health load'):
    health_summary = load_data_health_summary(db_path, cache_token)
render_data_health_indicator(health_summary)

history_cache_token = f'{MONITOR_HISTORY_CACHE_VERSION}:{cache_token}'
with perf.measure('shared monitor_history load'):
    history, history_timings = load_cached_monitor_history(db_path, history_cache_token)
perf.extend(history_timings, prefix='monitor_history detail: ')

if history.empty:
    st.info('No setup candidates yet. Process Back-Watch files to populate setup performance history.')
else:
    st.markdown('<div class="setup-perf-controls">', unsafe_allow_html=True)
    filter_cols = st.columns(4)
    setup_window = filter_cols[0].selectbox(
        'Setup date window',
        ['Last 5 setup dates', 'Last 10 setup dates', 'Last 20 setup dates', 'All'],
        index=1,
        key='setup_performance_window',
    )
    rating_filter = filter_cols[1].selectbox(
        'Rating filter',
        ['All', '4-5 only', '3+ only'],
        key='setup_performance_rating',
    )
    status_filter = filter_cols[2].selectbox(
        'Current Status filter',
        ['All', 'Active only', 'Failed only'],
        key='setup_performance_status',
    )
    sort_by = filter_cols[3].selectbox(
        'Sort setup table',
        ['Count', 'Failure %', 'Median Max %'],
        key='setup_performance_sort',
    )
    st.markdown('</div>', unsafe_allow_html=True)

    with perf.measure('setup performance aggregation'):
        filtered = filter_setup_performance_rows(
            history,
            setup_date_window=setup_window,
            rating_filter=rating_filter,
            current_status_filter=status_filter,
        )
        summary = build_setup_summary(filtered, sort_by=sort_by)
        tactic_summary = build_setup_entry_tactic_summary(filtered)
        trend = build_setup_failure_trend(filtered)
        cards = setup_performance_cards(summary)

    if summary.empty:
        st.info('No rows match the selected setup performance filters.')
    else:
        st.markdown(_setup_perf_cards_html(cards, summary), unsafe_allow_html=True)

        st.subheader('Setup Success Trend')
        st.markdown(
            '<div class="setup-perf-section-caption">Cells show Success % (successful setup rows / setup rows). '
            'Success = rows not counted as D0 Fail or Failed After D0. '
            'D0 Fail includes Trigger Day Fail or Current Status Failed D0.</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            trend,
            width='stretch',
            hide_index=True,
            column_config={'Setup': st.column_config.TextColumn('Setup', width='large')},
        )

        st.subheader('Setup Summary')
        st.markdown(
            '<div class="setup-perf-section-caption">Blank/null Setup values are grouped as Unclassified. '
            'Highest/best cards ignore samples under 5 unless no setup has enough sample.</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            summary,
            width='stretch',
            hide_index=True,
            column_config={
                'Setup': st.column_config.TextColumn('Setup', width='large'),
                'Sample': st.column_config.TextColumn('Sample', width='medium'),
                'Latest Setup Date': st.column_config.TextColumn('Latest Setup Date', width='medium'),
            },
        )

        with st.expander('Setup x Entry Tactic', expanded=False):
            st.dataframe(tactic_summary, width='stretch', hide_index=True)
            st.caption('Entry Tactic blanks are grouped as Unclassified.')

    with st.expander('Definitions / Logic', expanded=False):
        st.markdown(
            """
- **Count**: candidate rows in the filtered Rolling Backwatch Monitor history.
- **Active**: Current Status equals Active.
- **D0 Fail**: Trigger Day equals Fail or Current Status equals Failed D0, counted once per row.
- **Failed After D0**: Current Status is Failed D1 or later.
- **Failure %**: D0 Fail plus Failed After D0 divided by Count.
- **Close < BE %**: rows where Close < BE is Yes/true.
- **Retested D0 / Retested After D0**: parsed from Retests / Retest Days Raw.
- **Current %, Max %, D3 High %**: existing monitor values, using raw monitor percent fields when present.
- **Rating Avg**: numeric ratings only; blank ratings are ignored.
- **Sample**: Small sample under 5, Developing from 5 to 14, Useful sample at 15 or more.
            """
        )

render_perf_debug(st, perf)
