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
    for column in ['Median Range x ATR(14)', 'Median RVOL']:
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
    'close_location': 'Close Position',
    'close_bucket': 'Close Bucket',
    'range_vs_atr20': 'Range x ATR(14)',
    'relative_volume_20d': 'RVOL',
    'broke_setup_day_high_within_3d': 'High Broke 3D',
    'broke_setup_day_low_within_3d': 'Low Broke 3D',
}


DAILY_WORKFLOW_COLUMNS = [
    'Ticker',
    'Current Status',
    'Trigger Day',
    'Trigger',
    'PDH',
    '1m ORH',
    'VWAP Reclaim',
    '5m ORH',
    'Notes',
    'Current %',
    'Max %',
    'Close < BE',
    'D3 High %',
    'Retests',
    'Setup',
    'Entry Tactic',
    'Rating',
]

DAILY_WORKFLOW_INTERNAL_COLUMNS = ['candidate_id', *DAILY_WORKFLOW_COLUMNS]


GROUP_SUMMARY_COLUMNS = {
    'group_value': 'Group',
    'count': 'Count',
    'pct_closed_above_vwap': 'Above VWAP %',
    'pct_closed_near_hod': 'Near HOD %',
    'pct_5m_orh_fakeout': '5m Fakeout %',
    'median_range_vs_atr20': 'Median Range x ATR(14)',
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
    'median_range_vs_atr20': 'Median Range x ATR(14)',
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
    'close_location': 'Close Position',
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
    'range_vs_atr20': 'Range x ATR(14)',
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


def _count_pct(count: int, total: int) -> str:
    pct = 0 if total <= 0 else round((int(count) / total) * 100)
    return f'{int(count)} ({pct}%)'


def _compact_pct(value):
    return DISPLAY_NULL if _is_missing(value) else f'{float(value) * 100:.1f}%'


def _compact_num(value):
    return DISPLAY_NULL if _is_missing(value) else f'{float(value):.2f}'


def _status_sort(value) -> int:
    text = '' if _is_missing(value) else str(value).strip()
    if text == 'Active':
        return 0
    return 1


def _trigger_day_sort(value) -> int:
    text = '' if _is_missing(value) else str(value).strip()
    if text == 'Success':
        return 0
    if text == 'Fail':
        return 1
    if text == 'Unresolved':
        return 2
    return 3


def _numeric_sort(series: pd.Series) -> pd.Series:
    text = series.fillna('').astype(str).str.replace('%', '', regex=False)
    return pd.to_numeric(text, errors='coerce').fillna(float('-inf'))


def _rating_sort(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors='coerce').fillna(float('-inf'))


def daily_snapshot_monitor_table(con, d, include_candidate_id: bool = False) -> pd.DataFrame:
    """Build the selected date through the Rolling Setup Monitor semantics."""
    selected = str(pd.to_datetime(d).date())

    from src.rolling_setup_monitor import main_table, rolling_setup_monitor_for_date, sort_monitor_rows

    sections = rolling_setup_monitor_for_date(con, selected)
    matching = next((section for section in sections if section.get('setup_date') == selected), None)
    if matching is None:
        columns = DAILY_WORKFLOW_INTERNAL_COLUMNS if include_candidate_id else DAILY_WORKFLOW_COLUMNS
        return pd.DataFrame(columns=columns)

    source = sort_monitor_rows(matching['table']).reset_index(drop=True)
    table = main_table(matching['table']).reset_index(drop=True)
    if include_candidate_id:
        table.insert(0, 'candidate_id', source['candidate_id'].tolist() if 'candidate_id' in source else [''] * len(table))
    for column in DAILY_WORKFLOW_COLUMNS:
        if column not in table:
            table[column] = ''
    columns = DAILY_WORKFLOW_INTERNAL_COLUMNS if include_candidate_id else DAILY_WORKFLOW_COLUMNS
    table = table[columns].copy()
    if table.empty:
        return table

    table['_status_sort'] = table['Current Status'].apply(_status_sort)
    table['_trigger_day_sort'] = table['Trigger Day'].apply(_trigger_day_sort)
    table['_current_sort'] = _numeric_sort(table['Current %'])
    table['_max_sort'] = _numeric_sort(table['Max %'])
    table['_rating_sort'] = _rating_sort(table['Rating'])
    table = table.sort_values(
        ['_status_sort', '_trigger_day_sort', '_current_sort', '_max_sort', '_rating_sort', 'Ticker'],
        ascending=[True, True, False, False, False, True],
    )
    return table[columns].reset_index(drop=True)


def _retest_days(value) -> set[int]:
    if _is_missing(value):
        return set()
    out = set()
    for part in str(value).replace('+', ',').split(','):
        text = part.strip().lstrip('D')
        if not text or not text.split()[0].isdigit():
            continue
        out.add(int(text.split()[0]))
    return out


def daily_snapshot_summary_groups(metrics: dict, monitor_table: pd.DataFrame) -> list[dict]:
    total = len(monitor_table)
    status = monitor_table['Current Status'].fillna('').astype(str) if 'Current Status' in monitor_table else pd.Series(dtype=str)
    trigger_day = monitor_table['Trigger Day'].fillna('').astype(str) if 'Trigger Day' in monitor_table else pd.Series(dtype=str)
    trigger = monitor_table['Trigger'].fillna('').astype(str) if 'Trigger' in monitor_table else pd.Series(dtype=str)
    pdh = monitor_table['PDH'].fillna('').astype(str) if 'PDH' in monitor_table else pd.Series(dtype=str)
    one = monitor_table['1m ORH'].fillna('').astype(str) if '1m ORH' in monitor_table else pd.Series(dtype=str)
    vwap = monitor_table['VWAP Reclaim'].fillna('').astype(str) if 'VWAP Reclaim' in monitor_table else pd.Series(dtype=str)
    five = monitor_table['5m ORH'].fillna('').astype(str) if '5m ORH' in monitor_table else pd.Series(dtype=str)
    close_be = monitor_table['Close < BE'].fillna('').astype(str) if 'Close < BE' in monitor_table else pd.Series(dtype=str)
    retests = monitor_table['Retests'].fillna('').astype(str) if 'Retests' in monitor_table else pd.Series(dtype=str)

    active = int(status.eq('Active').sum())
    failed_d0 = int(status.eq('Failed D0').sum())
    failed_after_d0 = int(status.str.match(r'^Failed D[1-9]\d*$').sum() + status.isin({'Failed', 'Later Failed'}).sum())
    unresolved = int(trigger_day.eq('Unresolved').sum())
    close_be_count = int(close_be.str.casefold().eq('yes').sum())
    retest_days = retests.apply(_retest_days) if not retests.empty else pd.Series(dtype=object)
    retested_d0 = int(retest_days.apply(lambda days: 0 in days).sum()) if not retest_days.empty else 0
    retested_after_d0 = int(retest_days.apply(lambda days: any(day > 0 for day in days)).sum()) if not retest_days.empty else 0

    current = _numeric_sort(monitor_table['Current %']) / 100 if 'Current %' in monitor_table else pd.Series(dtype=float)
    max_pct = _numeric_sort(monitor_table['Max %']) / 100 if 'Max %' in monitor_table else pd.Series(dtype=float)
    d3_high = _numeric_sort(monitor_table['D3 High %']) / 100 if 'D3 High %' in monitor_table else pd.Series(dtype=float)
    rating = pd.to_numeric(monitor_table['Rating'], errors='coerce') if 'Rating' in monitor_table else pd.Series(dtype=float)

    overall = [
        ('Setups', str(int(metrics.get('setup_candidate_count') or total or 0))),
        ('Active', _count_pct(active, total)),
        ('Failed D0', _count_pct(failed_d0, total)),
        ('Failed After D0', _count_pct(failed_after_d0, total)),
    ]
    if unresolved:
        overall.append(('Unresolved', _count_pct(unresolved, total)))
    median_rating = rating.dropna().median()
    if not pd.isna(median_rating):
        overall.append(('Median Rating', _compact_num(median_rating)))

    trigger_quality = [
        ('PDH Success', _count_pct(int(pdh.eq('success').sum()), total)),
        ('PDH Fail', _count_pct(int(pdh.eq('failed').sum()), total)),
        ('PDH Gap', _count_pct(int(pdh.eq('Gap').sum()), total)),
        ('1m ORH Success', _count_pct(int(one.eq('success').sum()), total)),
        ('1m ORH Fail', _count_pct(int(one.eq('failed').sum()), total)),
        ('VWAP Reclaim Success', _count_pct(int(vwap.eq('success').sum()), total)),
        ('VWAP Reclaim Fail', _count_pct(int(vwap.eq('failed').sum()), total)),
        ('5m ORH Success', _count_pct(int(five.eq('success').sum()), total)),
        ('5m ORH Fail', _count_pct(int(five.eq('failed').sum()), total)),
    ]
    alt_count = int(trigger.eq('Alt Required').sum())
    no_trigger_count = int(trigger.eq('No Trigger').sum())
    if alt_count:
        trigger_quality.append(('Alt Required', _count_pct(alt_count, total)))
    if no_trigger_count:
        trigger_quality.append(('No Trigger', _count_pct(no_trigger_count, total)))

    follow = [
        ('Median Current %', _compact_pct(current[current > float('-inf')].median() if not current.empty else None)),
        ('Median Max %', _compact_pct(max_pct[max_pct > float('-inf')].median() if not max_pct.empty else None)),
        ('Close < BE', _count_pct(close_be_count, total)),
        ('Retested D0', _count_pct(retested_d0, total)),
        ('Retested After D0', _count_pct(retested_after_d0, total)),
    ]
    d3_values = d3_high[d3_high > float('-inf')]
    if not d3_values.empty:
        follow.append(('Median D3 High', _compact_pct(d3_values.median())))

    opening = [
        ('Closed Above VWAP %', _compact_pct(metrics.get('pct_closed_above_vwap'))),
        ('Closed Near HOD %', _compact_pct(metrics.get('pct_closed_near_hod'))),
        ('Median Close Position', _compact_num(metrics.get('median_close_location'))),
        ('Median Range x ATR(14)', _compact_num(metrics.get('median_range_vs_atr20'))),
        ('Median RVOL', _compact_num(metrics.get('median_relative_volume'))),
        ('High Broke 3D %', _compact_pct(metrics.get('pct_broke_setup_day_high_within_3d'))),
        ('Low Broke 3D %', _compact_pct(metrics.get('pct_broke_setup_day_low_within_3d'))),
    ]
    return [
        {'title': 'Overall', 'metrics': overall},
        {'title': 'Trigger Quality', 'metrics': trigger_quality},
        {'title': 'Follow-Through', 'metrics': follow},
        {'title': 'Opening / Intraday Character', 'metrics': opening},
    ]


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
