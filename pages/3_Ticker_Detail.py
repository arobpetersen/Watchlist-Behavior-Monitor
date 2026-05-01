import streamlit as st

from src.config import get_settings
from src.database import get_connection

con = get_connection(str(get_settings().db_path))
st.title('Ticker Detail')
tickers = [r[0] for r in con.execute('select distinct ticker from watchlist_candidates order by ticker').fetchall()]
if not tickers:
    st.info('No data yet')
else:
    t = st.selectbox('Ticker', tickers)
    st.dataframe(con.execute('''
    select c.watchlist_date,c.ticker,c.rating,c.setup,c.focus,c.key_level,
           f.close_location,f.closed_above_vwap,b.primary_label,b.secondary_labels
    from watchlist_candidates c
    left join entry_day_features f using(candidate_id,watchlist_date,ticker)
    left join behavior_labels b using(candidate_id,watchlist_date,ticker)
    where c.ticker=? order by c.watchlist_date desc
    ''', [t]).df(), use_container_width=True)
