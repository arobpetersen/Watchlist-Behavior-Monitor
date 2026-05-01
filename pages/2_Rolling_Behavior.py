import streamlit as st

from src.config import get_settings
from src.database import get_connection

con = get_connection(str(get_settings().db_path))
st.title('Rolling Behavior')
window = st.selectbox('Window', [5, 10, 20])
st.dataframe(con.execute('''
select watchlist_date,
       count(*) as names,
       avg(close_location) as avg_close_location,
       median(range_vs_atr20) as median_range_vs_atr20,
       median(relative_volume_20d) as median_relative_volume_20d,
       avg(case when closed_higher_D1 then 1 else 0 end) as d1_continuation_rate,
       avg(case when broke_entry_day_high_within_3d then 1 else 0 end) as d3_high_break_rate,
       avg(case when broke_entry_day_low_within_3d then 1 else 0 end) as d3_low_break_rate
from entry_day_features
group by watchlist_date
order by watchlist_date desc
limit ?
''', [window]).df(), use_container_width=True)
