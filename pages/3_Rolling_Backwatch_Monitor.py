import streamlit as st
from html import escape

from src.config import get_settings
from src.data_health_indicator import data_health_cache_token
from src.database import get_connection
from src.daily_snapshot_read import daily_snapshot_trigger_read_groups
from src.market_context import market_context_for_setup_dates, market_move_label
from src.or_trigger_audit import audit_for_candidate, setup_dates, tickers_for_setup_date
from src.performance import PerfTimer, render_perf_debug
from src.rolling_setup_monitor import (
    apply_setup_rating_updates,
    detail_table,
    entry_tactic_dropdown_options,
    format_monitor_table_html,
    main_table,
    rating_dropdown_options,
    rolling_setup_monitor,
    setup_dropdown_options,
)
from src.view_refresh import DERIVED_REFRESH_MESSAGE, refresh_derived_watchlist_views

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

ROLLING_MONITOR_CACHE_VERSION = 'rolling-monitor-other-dedup-v2'


@st.cache_data(show_spinner=False)
def load_rolling_setup_sections(db_path: str, cache_version: str):
    timer = PerfTimer('Rolling Backwatch Monitor Build', enabled=True)
    con = get_connection(db_path)
    return rolling_setup_monitor(con, setup_dates=5, perf=timer), timer.rows()


def _count_rate(count: int, total: int) -> str:
    pct = 0 if total <= 0 else round((int(count) / int(total)) * 100)
    return f'{int(count)} / {pct}%'


def _fmt_pct(value) -> str:
    try:
        if value is None or value != value:
            return '-'
        return f'{float(value) * 100:+.1f}%'
    except (TypeError, ValueError):
        return '-'


def _fmt_num(value) -> str:
    try:
        if value is None or value != value:
            return '-'
        return f'{float(value):.2f}'
    except (TypeError, ValueError):
        return '-'


def _fmt_whole_pct(value) -> str:
    try:
        if value is None or value != value:
            return '-'
        return f'{float(value) * 100:.0f}%'
    except (TypeError, ValueError):
        return '-'


def _fmt_atr_multiple(value) -> str:
    try:
        if value is None or value != value:
            return '-'
        return f'{float(value):.2f}x ATR(14)'
    except (TypeError, ValueError):
        return '-'


def _status_counts(table):
    if table is None or table.empty:
        return {'active': 0, 'failed_d0': 0, 'failed_after_d0': 0, 'close_be': None}
    status = table['Current Status'].fillna('').astype(str).str.strip() if 'Current Status' in table else ''
    trigger_day = table['Trigger Day'].fillna('').astype(str).str.strip() if 'Trigger Day' in table else ''
    close_be = None
    if 'Close < BE' in table:
        close_be = int(table['Close < BE'].fillna('').astype(str).str.casefold().eq('yes').sum())
    d0_failed = status.eq('Failed D0') | trigger_day.eq('Fail')
    return {
        'active': int(status.eq('Active').sum()),
        'failed_d0': int(d0_failed.sum()),
        'failed_after_d0': int(status.str.match(r'^Failed D[1-9]\d*$', na=False).sum()),
        'close_be': close_be,
    }


def _metric_chip(label: str, value: str, extra_class: str = '') -> str:
    classes = 'market-chip' if not extra_class else f'market-chip {extra_class}'
    return (
        f'<span class="{escape(classes)}">'
        f'<span class="chip-label">{escape(label)}</span>'
        f'<strong>{escape(value)}</strong>'
        '</span>'
    )


def _metric_tile(label: str, value: str) -> str:
    return (
        '<section class="day-metric-tile">'
        f'<div class="tile-label">{escape(label)}</div>'
        f'<div class="tile-value">{escape(value)}</div>'
        '</section>'
    )


def _market_context_banner(context) -> str:
    if context is None or not getattr(context, 'available', False):
        return '''
<section class="monitor-read-banner market-read-banner">
  <div class="read-banner-title">Market Context</div>
  <div class="read-chip-row unavailable-market">Market context unavailable for this setup date.</div>
</section>
'''
    day_type = getattr(context, 'day_type', 'Mixed')
    chips = [
        _metric_chip(context.proxy, _fmt_pct(getattr(context, 'pct_change', None))),
        _metric_chip('Move', market_move_label(getattr(context, 'pct_change', None))),
        _metric_chip('Day Type', day_type, 'day-type-chip'),
        _metric_chip('Gap', _fmt_pct(getattr(context, 'gap_pct', None))),
        _metric_chip('Close Position', _fmt_whole_pct(getattr(context, 'close_location', None))),
        _metric_chip('Range', _fmt_atr_multiple(getattr(context, 'range_vs_atr14', None))),
    ]
    secondary = getattr(context, 'read', '')
    secondary_html = f'<div class="read-banner-secondary">{escape(secondary)}</div>' if secondary else ''
    return f'''
<section class="monitor-read-banner market-read-banner">
  <div class="read-banner-title">Market Context</div>
  <div class="read-chip-row">{''.join(chips)}</div>
  {secondary_html}
</section>
'''


def _day_read_banner(summary: dict, table) -> str:
    total = int(summary.get('Setups', 0) or 0)
    counts = _status_counts(table)
    result_tiles = [
        _metric_tile('Setups', str(total)),
        _metric_tile('Active', _count_rate(counts['active'], total)),
        _metric_tile('D0 Fail', _count_rate(counts['failed_d0'], total)),
        _metric_tile('Failed After D0', _count_rate(counts['failed_after_d0'], total)),
    ]
    follow_tiles = [
        _metric_tile('Close < BE', _count_rate(counts['close_be'], total)) if counts['close_be'] is not None else '',
        _metric_tile('Retested', _count_rate(int(summary.get('Retested', 0) or 0), total)),
    ]
    d3_high = str(summary.get('Median D3 High %', '') or '')
    if d3_high and d3_high != '-':
        follow_tiles.append(_metric_tile('Median D3 High', d3_high))
    follow_tiles = [tile for tile in follow_tiles if tile]
    return f'''
<section class="monitor-read-banner day-read-banner">
  <div class="read-banner-title">Day Read</div>
  <div class="day-metric-grid">{''.join(result_tiles + follow_tiles)}</div>
</section>
'''


def _trigger_group(label: str, details: str) -> str:
    if not details:
        return ''
    return (
        '<section class="trigger-mini-card">'
        f'<h4>{escape(label)}</h4>'
        f'<div>{escape(str(details))}</div>'
        '</section>'
    )


def _trigger_read_strip(table) -> str:
    groups = [_trigger_group(label, details) for label, details in daily_snapshot_trigger_read_groups(table)]
    body = ''.join(group for group in groups if group)
    if not body:
        body = '<span class="muted-trigger-metric">No notable trigger events</span>'
    return f'''
<section class="monitor-read-banner trigger-read-banner">
  <div class="read-banner-title">Trigger Read</div>
  <div class="trigger-mini-grid">{body}</div>
</section>
'''


def _readability_styles() -> str:
    return '''
<style>
.monitor-date-section {
  margin: 0.45rem 0 0.95rem 0;
}
.monitor-top-grid {
  display: grid;
  grid-template-columns: minmax(260px, 0.82fr) minmax(420px, 1.55fr);
  gap: 0.55rem;
  align-items: stretch;
}
.monitor-read-banner {
  border: 1px solid rgba(250, 250, 250, 0.12);
  border-radius: 8px;
  background: rgba(250, 250, 250, 0.036);
  padding: 0.78rem 0.9rem;
  margin: 0 0 0.46rem 0;
}
.market-read-banner {
  border-left: 3px solid rgba(96, 165, 250, 0.78);
  height: 100%;
}
.day-read-banner {
  background: rgba(250, 250, 250, 0.058);
  border-color: rgba(250, 250, 250, 0.16);
  height: 100%;
}
.trigger-read-banner {
  margin-top: 0.55rem;
}
.read-banner-title {
  display: block;
  color: rgba(250, 250, 250, 0.70);
  font-size: 0.92rem;
  font-weight: 850;
  letter-spacing: 0;
  text-transform: uppercase;
  margin-bottom: 0.44rem;
}
.read-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.52rem;
  align-items: center;
}
.market-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 0.46rem;
  padding: 0.46rem 0.68rem;
  border-radius: 7px;
  border: 1px solid rgba(250, 250, 250, 0.10);
  background: rgba(250, 250, 250, 0.066);
  color: rgba(250, 250, 250, 0.68);
  font-size: 1.02rem;
  line-height: 1.2;
  white-space: nowrap;
}
.market-chip strong {
  color: rgba(250, 250, 250, 0.96);
  font-size: 1.18rem;
  font-weight: 850;
}
.chip-label {
  color: rgba(250, 250, 250, 0.62);
  font-weight: 700;
}
.day-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(118px, 1fr));
  gap: 0.56rem;
  align-items: stretch;
}
.day-metric-tile {
  border: 1px solid rgba(250, 250, 250, 0.12);
  border-radius: 8px;
  background: rgba(250, 250, 250, 0.078);
  padding: 0.58rem 0.68rem;
  min-height: 3.75rem;
}
.tile-label {
  color: rgba(250, 250, 250, 0.62);
  font-size: 0.82rem;
  font-weight: 760;
  line-height: 1.15;
  margin-bottom: 0.34rem;
}
.tile-value {
  color: rgba(250, 250, 250, 0.98);
  font-size: 1.22rem;
  font-weight: 880;
  line-height: 1.18;
}
.read-banner-secondary {
  margin-top: 0.54rem;
  color: rgba(250, 250, 250, 0.74);
  font-size: 1.0rem;
  line-height: 1.3;
}
.day-type-chip {
  border: 1px solid rgba(96, 165, 250, 0.34);
  background: rgba(59, 130, 246, 0.17);
}
.day-type-chip strong {
  color: rgba(224, 242, 254, 0.98);
}
.unavailable-market {
  color: rgba(250, 250, 250, 0.72);
  font-size: 0.92rem;
}
.trigger-mini-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.58rem;
}
.trigger-mini-card {
  flex: 0 1 auto;
  border: 1px solid rgba(250, 250, 250, 0.10);
  border-radius: 7px;
  background: rgba(250, 250, 250, 0.052);
  padding: 0.62rem 0.76rem;
  min-width: 10.2rem;
}
.trigger-mini-card h4 {
  margin: 0 0 0.34rem 0;
  color: rgba(250, 250, 250, 0.94);
  font-size: 1.06rem;
  font-weight: 850;
}
.trigger-mini-card div {
  color: rgba(250, 250, 250, 0.78);
  font-size: 1.0rem;
  line-height: 1.25;
}
.muted-trigger-metric {
  color: rgba(250, 250, 250, 0.48);
}
@media (max-width: 900px) {
  .monitor-top-grid {
    grid-template-columns: 1fr;
  }
  .day-metric-grid {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }
}
@media (max-width: 560px) {
  .day-metric-grid {
    grid-template-columns: 1fr;
  }
}
</style>
'''


perf = PerfTimer('Rolling Backwatch Monitor')
db_path = str(get_settings().db_path)
with perf.measure('DB connection/open'):
    con = get_connection(db_path)
st.title('Rolling Backwatch Monitor')
st.caption('Recent back-watch setup dates using canonical trigger/status rows.')
if st.button('Refresh derived views from database', key='rolling_monitor_refresh_derived', help='Refreshes cached monitor/report views after data or manual metadata changes.'):
    refresh_derived_watchlist_views(load_rolling_setup_sections)
    st.session_state['derived_views_refreshed'] = True
    st.rerun()
if st.session_state.pop('derived_views_refreshed', False):
    st.success(DERIVED_REFRESH_MESSAGE)

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
with perf.measure('Rolling Backwatch Monitor data build'):
    sections, build_timings = load_rolling_setup_sections(db_path, rolling_cache_token)
perf.extend(build_timings, prefix='cache miss detail: ')
if not sections:
    st.info('No setup candidates yet.')
else:
    market_context_by_date = market_context_for_setup_dates(con, [section['setup_date'] for section in sections])
    st.markdown(_readability_styles(), unsafe_allow_html=True)
    for section in sections:
        st.subheader(f"Setup Date: {section['setup_date']}")
        table = section['table']
        market_context = market_context_by_date.get(section['setup_date'])
        st.markdown(
            '<div class="monitor-date-section">'
            + '<div class="monitor-top-grid">'
            + '<div>'
            + _market_context_banner(market_context)
            + '</div>'
            + '<div>'
            + _day_read_banner(section['summary'], table)
            + '</div>'
            + '</div>'
            + _trigger_read_strip(table)
            + '</div>',
            unsafe_allow_html=True,
        )

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
                        refresh_derived_watchlist_views(load_rolling_setup_sections)
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
