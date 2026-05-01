import streamlit as st

from src.config import get_settings
from src.dashboard_queries import dates, group_summaries, snapshot_metrics, snapshot_table
from src.database import get_connection


def _missing(value):
    return value is None or value != value


def _fmt_pct(value):
    return '—' if _missing(value) else f'{value * 100:.0f}%'


def _fmt_num(value):
    return '—' if _missing(value) else f'{value:.2f}'


con = get_connection(str(get_settings().db_path))
st.title('Setup Day Snapshot')
all_dates = dates(con)
if not all_dates:
    st.info('No data yet. Run python -m src.run_daily')
else:
    d = st.selectbox('Setup Date', all_dates)
    m = snapshot_metrics(con, d)
    metric_rows = [
        [
            ('Setup Candidates', f"{int(m.get('setup_candidate_count') or 0)}"),
            ('Median Rating', _fmt_num(m.get('median_rating'))),
            ('Closed Above VWAP %', _fmt_pct(m.get('pct_closed_above_vwap'))),
            ('Closed Near HOD %', _fmt_pct(m.get('pct_closed_near_hod'))),
        ],
        [
            ('Broke 1m ORH %', _fmt_pct(m.get('pct_broke_1m_orh'))),
            ('1m ORH Fakeout %', _fmt_pct(m.get('pct_1m_orh_fakeout'))),
            ('Broke 5m ORH %', _fmt_pct(m.get('pct_broke_5m_orh'))),
            ('5m ORH Fakeout %', _fmt_pct(m.get('pct_5m_orh_fakeout'))),
        ],
        [
            ('Median Close Loc.', _fmt_num(m.get('median_close_location'))),
            ('Median Range / ATR', _fmt_num(m.get('median_range_vs_atr20'))),
            ('Median RVOL', _fmt_num(m.get('median_relative_volume'))),
            ('High Broke 3D %', _fmt_pct(m.get('pct_broke_setup_day_high_within_3d'))),
        ],
        [
            ('Low Broke 3D %', _fmt_pct(m.get('pct_broke_setup_day_low_within_3d'))),
        ],
    ]
    for metric_row in metric_rows:
        cols = st.columns(4)
        for col, (label, value) in zip(cols, metric_row):
            col.metric(label, value)

    st.subheader('Setup Candidates')
    st.dataframe(snapshot_table(con, d), use_container_width=True)
    st.subheader('Group Summaries')
    tabs = st.tabs(['Rating Bucket', 'Setup', 'Focus'])
    tabs[0].dataframe(group_summaries(con, d, 'rating_bucket'), use_container_width=True)
    tabs[1].dataframe(group_summaries(con, d, 'setup'), use_container_width=True)
    tabs[2].dataframe(group_summaries(con, d, 'focus'), use_container_width=True)
