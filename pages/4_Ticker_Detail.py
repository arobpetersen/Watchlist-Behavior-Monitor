import streamlit as st

from src.config import get_settings
from src.dashboard_queries import ticker_detail_table
from src.database import get_connection

st.set_page_config(page_title='Watchlist Behavior Monitor', layout='wide')

con = get_connection(str(get_settings().db_path))
st.title('Ticker Setup Behavior')
tickers = [r[0] for r in con.execute('select distinct ticker from watchlist_candidates order by ticker').fetchall()]
if not tickers:
    st.info('No data yet')
else:
    t = st.selectbox('Ticker', tickers)
    st.dataframe(ticker_detail_table(con, t), use_container_width=True, hide_index=True)
