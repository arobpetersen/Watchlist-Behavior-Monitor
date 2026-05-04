from __future__ import annotations

import json

import pandas as pd


DISPLAY_NULL = '—'


def _is_missing(value) -> bool:
    if value is None or pd.isna(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {'', 'nan', 'none'}:
        return True
    return False


def _or_result(s: str) -> str:
    if not isinstance(s, str):
        return 'No Break'
    d = json.loads(s or '{}')
    if not d:
        return 'No Break'
    up, dn = d.get('broke_orh'), d.get('broke_orl')
    if up and d.get('orh_then_orl'):
        return 'Failed'
    if up and dn:
        return 'Failed' if d.get('orh_then_orl') else 'Both Sides'
    if up and d.get('closed_above_orh'):
        return 'Held'
    if up:
        return 'Broke High Only'
    if dn and d.get('closed_below_orl'):
        return 'Failed'
    if dn:
        return 'Broke Low Only'
    return 'No Break'


def _vwap_result(value) -> str:
    if _is_missing(value):
        return 'No Data'
    return 'Above VWAP' if bool(value) else 'Below VWAP'


def _rating_bucket(value) -> str:
    if _is_missing(value):
        return 'No Rating'
    rating = float(value)
    if rating >= 4:
        return '4+'
    if rating >= 3:
        return '3 to <4'
    if rating >= 2:
        return '2 to <3'
    return '<2'


def _close_bucket(value) -> str:
    if _is_missing(value):
        return ''
    close_location = float(value)
    if close_location >= 0.80:
        return 'Top 20%'
    if close_location >= 0.60:
        return 'Upper Half'
    if close_location >= 0.40:
        return 'Middle'
    if close_location > 0.20:
        return 'Lower Half'
    return 'Bottom 20%'


def _clean_display_value(value):
    if _is_missing(value):
        return ''
    return value


def _clean_display_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(_clean_display_value)


def _format_pct(value):
    return '' if _is_missing(value) else f'{float(value) * 100:.0f}%'


def _format_num(value):
    return '' if _is_missing(value) else f'{float(value):.2f}'


def _rename(df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    return _clean_display_df(df.rename(columns=columns))


def _format_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    formatted = _clean_display_df(df.copy())
    for column in formatted.columns:
        if column.endswith('%'):
            formatted[column] = formatted[column].apply(_format_pct)
    for column in ['Median Range / ATR14', 'Median RVOL']:
        if column in formatted.columns:
            formatted[column] = formatted[column].apply(_format_num)
    return formatted


DAILY_TABLE_COLUMNS = {
    'ticker': 'Ticker',
    'rating': 'Rating',
    'setup': 'Setup',
    'focus': 'Focus',
    'primary_label': 'Label',
    'secondary_labels': 'Secondary',
    '1m OR result': '1m OR',
    '5m OR result': '5m OR',
    '15m OR result': '15m OR',
    'VWAP result': 'VWAP',
    'close_location': 'Close Loc.',
    'close_bucket': 'Close Bucket',
    'range_vs_atr20': 'Range / ATR14',
    'relative_volume_20d': 'RVOL',
    'broke_setup_day_high_within_3d': 'High Broke 3D',
    'broke_setup_day_low_within_3d': 'Low Broke 3D',
}


GROUP_SUMMARY_COLUMNS = {
    'group_value': 'Group',
    'count': 'Count',
    'pct_closed_above_vwap': 'Above VWAP %',
    'pct_closed_near_hod': 'Near HOD %',
    'pct_5m_orh_fakeout': '5m Fakeout %',
    'median_range_vs_atr20': 'Median Range / ATR14',
    'median_relative_volume': 'Median RVOL',
    'pct_broke_setup_day_high_within_3d': 'High Broke 3D %',
    'pct_broke_setup_day_low_within_3d': 'Low Broke 3D %',
}


ROLLING_COLUMNS = {
    'window': 'Window',
    'count': 'Count',
    'pct_closed_above_vwap': 'Above VWAP %',
    'pct_closed_near_hod': 'Near HOD %',
    'pct_1m_orh_fakeout': '1m Fakeout %',
    'pct_5m_orh_fakeout': '5m Fakeout %',
    'median_range_vs_atr20': 'Median Range / ATR14',
    'median_relative_volume': 'Median RVOL',
    'pct_broke_setup_day_high_within_3d': 'High Broke 3D %',
    'pct_broke_setup_day_low_within_3d': 'Low Broke 3D %',
}


TICKER_DETAIL_COLUMNS = {
    'setup_date': 'Setup Date',
    'ticker': 'Ticker',
    'rating': 'Rating',
    'setup': 'Setup',
    'focus': 'Focus',
    'key_level': 'Key Level',
    'open_price': 'Open',
    'high_price': 'High',
    'low_price': 'Low',
    'close_price': 'Close',
    'close_location': 'Close Loc.',
    'VWAP result': 'VWAP',
    'session_vwap': 'Session VWAP',
    'ever_below_vwap': 'Ever Below VWAP',
    'ever_above_vwap': 'Ever Above VWAP',
    '1m OR result': '1m OR',
    '5m OR result': '5m OR',
    '15m OR result': '15m OR',
    'gap_pct': 'Gap %',
    'atr20': 'ATR14',
    'day_range_pct': 'Day Range %',
    'range_vs_atr20': 'Range / ATR14',
    'avg_volume_20d': 'Avg Volume 20D',
    'relative_volume_20d': 'RVOL',
    'broke_setup_day_high_D1': 'High Broke D+1',
    'broke_setup_day_low_D1': 'Low Broke D+1',
    'closed_higher_D1': 'Closed Higher D+1',
    'broke_setup_day_high_within_3d': 'High Broke 3D',
    'broke_setup_day_low_within_3d': 'Low Broke 3D',
    'max_gain_3d_pct': 'Max Gain 3D %',
    'max_drawdown_3d_pct': 'Max Drawdown 3D %',
    'primary_label': 'Label',
    'secondary_labels': 'Secondary',
}


def dates(con):
    return [r[0] for r in con.execute('select distinct watchlist_date from watchlist_candidates where watchlist_date is not null order by watchlist_date desc').fetchall()]


def snapshot_metrics(con, d):
    return con.execute("""
    select count(*) as setup_candidate_count,
    median(c.rating) as median_rating,
    avg(case when f.closed_above_vwap then 1 else 0 end) as pct_closed_above_vwap,
    avg(case when f.closed_near_high then 1 else 0 end) as pct_closed_near_hod,
    avg(case when json_extract(f.or_1m,'$.broke_orh')::boolean then 1 else 0 end) as pct_broke_1m_orh,
    avg(case when json_extract(f.or_1m,'$.orh_then_orl')::boolean then 1 else 0 end) as pct_1m_orh_fakeout,
    avg(case when json_extract(f.or_5m,'$.broke_orh')::boolean then 1 else 0 end) as pct_broke_5m_orh,
    avg(case when json_extract(f.or_5m,'$.orh_then_orl')::boolean then 1 else 0 end) as pct_5m_orh_fakeout,
    median(f.close_location) as median_close_location,
    median(f.range_vs_atr20) as median_range_vs_atr20,
    median(f.relative_volume_20d) as median_relative_volume,
    avg(case when f.broke_entry_day_high_within_3d then 1 else 0 end) as pct_broke_setup_day_high_within_3d,
    avg(case when f.broke_entry_day_low_within_3d then 1 else 0 end) as pct_broke_setup_day_low_within_3d
    from watchlist_candidates c
    left join entry_day_features f using(candidate_id,watchlist_date,ticker)
    where c.watchlist_date=?
    """, [d]).df().iloc[0].to_dict()


def snapshot_table(con, d):
    df = con.execute('''
    select c.ticker,c.rating,c.setup,c.focus,b.primary_label,b.secondary_labels,
           f.close_location,f.closed_above_vwap,f.gap_pct,f.range_vs_atr20,
           f.relative_volume_20d,f.broke_entry_day_high_within_3d,
           f.broke_entry_day_low_within_3d,f.or_1m,f.or_5m,f.or_15m
    from watchlist_candidates c
    left join entry_day_features f using(candidate_id,watchlist_date,ticker)
    left join behavior_labels b using(candidate_id,watchlist_date,ticker)
    where c.watchlist_date=? order by c.ticker''', [d]).df()
    df['1m OR result'] = df['or_1m'].apply(_or_result)
    df['5m OR result'] = df['or_5m'].apply(_or_result)
    df['15m OR result'] = df['or_15m'].apply(_or_result)
    df['VWAP result'] = df['closed_above_vwap'].apply(_vwap_result)
    df['close_bucket'] = df['close_location'].apply(_close_bucket)
    df = df.rename(columns={
        'broke_entry_day_high_within_3d': 'broke_setup_day_high_within_3d',
        'broke_entry_day_low_within_3d': 'broke_setup_day_low_within_3d',
    })
    df = df[['ticker','rating','setup','focus','primary_label','secondary_labels','1m OR result','5m OR result','15m OR result','VWAP result','close_location','close_bucket','range_vs_atr20','relative_volume_20d','broke_setup_day_high_within_3d','broke_setup_day_low_within_3d']]
    return _rename(df, DAILY_TABLE_COLUMNS)


def group_summaries(con, d, field: str):
    if field not in {'rating_bucket', 'setup', 'focus'}:
        raise ValueError('Unsupported summary field')
    group_expr = {
        'rating_bucket': """
            case
                when c.rating is null then 'No Rating'
                when c.rating >= 4 then '4+'
                when c.rating >= 3 then '3 to <4'
                when c.rating >= 2 then '2 to <3'
                else '<2'
            end
        """,
        'setup': "coalesce(nullif(c.setup, ''), 'Blank')",
        'focus': "coalesce(nullif(c.focus, ''), 'Blank')",
    }[field]
    df = con.execute(f"""
    select {group_expr} as group_value,
           count(*) as count,
           avg(case when f.closed_above_vwap then 1 else 0 end) as pct_closed_above_vwap,
           avg(case when f.closed_near_high then 1 else 0 end) as pct_closed_near_hod,
           avg(case when json_extract(f.or_5m,'$.orh_then_orl')::boolean then 1 else 0 end) as pct_5m_orh_fakeout,
           median(f.range_vs_atr20) as median_range_vs_atr20,
           median(f.relative_volume_20d) as median_relative_volume,
           avg(case when f.broke_entry_day_high_within_3d then 1 else 0 end) as pct_broke_setup_day_high_within_3d,
           avg(case when f.broke_entry_day_low_within_3d then 1 else 0 end) as pct_broke_setup_day_low_within_3d
    from watchlist_candidates c
    left join entry_day_features f using(candidate_id,watchlist_date,ticker)
    where c.watchlist_date=?
    group by group_value
    order by count desc, group_value
    """, [d]).df()
    return _format_summary_df(_rename(df, GROUP_SUMMARY_COLUMNS))


def rolling_window_summary(con, windows=(5, 10, 20)):
    rows = []
    for window in windows:
        row = con.execute("""
        with last_dates as (
            select distinct watchlist_date
            from watchlist_candidates
            where watchlist_date is not null
            order by watchlist_date desc
            limit ?
        )
        select ? as window,
               count(*) as count,
               avg(case when f.closed_above_vwap then 1 else 0 end) as pct_closed_above_vwap,
               avg(case when f.closed_near_high then 1 else 0 end) as pct_closed_near_hod,
               avg(case when json_extract(f.or_1m,'$.orh_then_orl')::boolean then 1 else 0 end) as pct_1m_orh_fakeout,
               avg(case when json_extract(f.or_5m,'$.orh_then_orl')::boolean then 1 else 0 end) as pct_5m_orh_fakeout,
               median(f.range_vs_atr20) as median_range_vs_atr20,
               median(f.relative_volume_20d) as median_relative_volume,
               avg(case when f.broke_entry_day_high_within_3d then 1 else 0 end) as pct_broke_setup_day_high_within_3d,
               avg(case when f.broke_entry_day_low_within_3d then 1 else 0 end) as pct_broke_setup_day_low_within_3d
        from watchlist_candidates c
        left join entry_day_features f using(candidate_id,watchlist_date,ticker)
        where c.watchlist_date in (select watchlist_date from last_dates)
        """, [window, f'Last {window} setup dates']).df().iloc[0].to_dict()
        rows.append(row)
    return _format_summary_df(_rename(pd.DataFrame(rows), ROLLING_COLUMNS))


def ticker_detail_table(con, ticker: str):
    df = con.execute('''
    select c.watchlist_date as setup_date,c.ticker,c.rating,c.setup,c.focus,c.key_level,
           f.open_price,f.high_price,f.low_price,f.close_price,f.close_location,
           f.closed_near_high,f.closed_near_low,f.session_vwap,f.closed_above_vwap,
           f.ever_below_vwap,f.ever_above_vwap,f.gap_pct,f.atr20,f.day_range_pct,
           f.range_vs_atr20,f.avg_volume_20d,f.relative_volume_20d,
           f.broke_entry_day_high_D1,f.broke_entry_day_low_D1,f.closed_higher_D1,
           f.broke_entry_day_high_within_3d,f.broke_entry_day_low_within_3d,
           f.max_gain_3d_pct,f.max_drawdown_3d_pct,f.or_1m,f.or_5m,f.or_15m,
           b.primary_label,b.secondary_labels
    from watchlist_candidates c
    left join entry_day_features f using(candidate_id,watchlist_date,ticker)
    left join behavior_labels b using(candidate_id,watchlist_date,ticker)
    where c.ticker=? order by c.watchlist_date desc
    ''', [ticker]).df()
    if df.empty:
        return df
    df['1m OR result'] = df['or_1m'].apply(_or_result)
    df['5m OR result'] = df['or_5m'].apply(_or_result)
    df['15m OR result'] = df['or_15m'].apply(_or_result)
    df['VWAP result'] = df['closed_above_vwap'].apply(_vwap_result)
    df = df.rename(columns={
        'broke_entry_day_high_D1': 'broke_setup_day_high_D1',
        'broke_entry_day_low_D1': 'broke_setup_day_low_D1',
        'broke_entry_day_high_within_3d': 'broke_setup_day_high_within_3d',
        'broke_entry_day_low_within_3d': 'broke_setup_day_low_within_3d',
    })
    df = df[[
        'setup_date','ticker','rating','setup','focus','key_level',
        'open_price','high_price','low_price','close_price','close_location',
        'VWAP result','session_vwap','ever_below_vwap','ever_above_vwap',
        '1m OR result','5m OR result','15m OR result',
        'gap_pct','atr20','day_range_pct','range_vs_atr20','avg_volume_20d','relative_volume_20d',
        'broke_setup_day_high_D1','broke_setup_day_low_D1','closed_higher_D1',
        'broke_setup_day_high_within_3d','broke_setup_day_low_within_3d',
        'max_gain_3d_pct','max_drawdown_3d_pct','primary_label','secondary_labels'
    ]]
    return _rename(df, TICKER_DETAIL_COLUMNS)
