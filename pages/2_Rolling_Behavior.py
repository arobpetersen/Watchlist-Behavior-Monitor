import streamlit as st

from src.config import get_settings
from src.database import get_connection

con = get_connection(str(get_settings().db_path))
st.title('Rolling Behavior')
window = st.selectbox('Window', [5, 10, 20])
st.dataframe(con.execute('''
select watchlist_date, count(*) names, avg(close_location) avg_close_location
from entry_day_features
group by watchlist_date
order by watchlist_date desc
limit ?
''', [window]).df(), use_container_width=True)
