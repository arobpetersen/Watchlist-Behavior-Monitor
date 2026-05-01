import streamlit as st

from src.config import get_settings
from src.dashboard_queries import dates, snapshot_metrics, snapshot_table
from src.database import get_connection

con = get_connection(str(get_settings().db_path))
st.title('Daily Snapshot')
all_dates = dates(con)
if not all_dates:
    st.info('No data yet. Run python -m src.run_daily')
else:
    d = st.selectbox('watchlist_date', all_dates)
    m = snapshot_metrics(con, d)
    cards = st.columns(4)
    cards[0].metric('Median Range / ATR20', f"{m.get('median_range_vs_atr20') or 0:.2f}")
    cards[1].metric('Median Relative Volume', f"{m.get('median_relative_volume_20d') or 0:.2f}")
    cards[2].metric('% Broke High Within 3D', f"{(m.get('pct_broke_entry_day_high_within_3d') or 0) * 100:.0f}%")
    cards[3].metric('% Broke Low Within 3D', f"{(m.get('pct_broke_entry_day_low_within_3d') or 0) * 100:.0f}%")
    st.dataframe(snapshot_table(con, d), use_container_width=True)
