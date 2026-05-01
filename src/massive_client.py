from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urljoin

import pandas as pd
import requests


def _format_aggregate_date(value: str | date | datetime) -> str:
    parsed = pd.to_datetime(value).date()
    formatted = parsed.isoformat()
    if ' ' in formatted:
        raise ValueError('Aggregate date must be formatted as YYYY-MM-DD')
    return formatted


class MassiveClient:
    def __init__(self, api_key: str | None, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')

    def fetch_intraday_1m(self, ticker: str, trading_date: str | date | datetime) -> pd.DataFrame:
        if not self.api_key:
            raise RuntimeError('API key missing')
        date_str = _format_aggregate_date(trading_date)
        url = urljoin(self.base_url + '/', f"v2/aggs/ticker/{ticker}/range/1/minute/{date_str}/{date_str}")
        r = requests.get(url, params={'adjusted':'true', 'sort':'asc', 'limit':50000, 'apiKey':self.api_key}, timeout=30)
        try:
            r.raise_for_status()
        except requests.HTTPError:
            reason = r.reason or 'HTTP error'
            raise RuntimeError(f"Massive fetch failed for {ticker} on {date_str}: {r.status_code} {reason}") from None
        rows = r.json().get('results', [])
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df['timestamp_et'] = pd.to_datetime(df['t'], unit='ms', utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None)
        df = df.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume'})
        df['ticker'] = ticker
        df['trading_date'] = date_str
        df['source'] = 'massive'
        df['fetched_at'] = datetime.utcnow()
        return df[['ticker','trading_date','timestamp_et','open','high','low','close','volume','source','fetched_at']]
