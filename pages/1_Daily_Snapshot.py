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
    st.write(m)
    st.dataframe(snapshot_table(con, d), use_container_width=True)
