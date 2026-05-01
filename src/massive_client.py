from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests


class MassiveClient:
    def __init__(self, api_key: str | None, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')

    def fetch_intraday_1m(self, ticker: str, date_str: str) -> pd.DataFrame:
        if not self.api_key:
            raise RuntimeError('MASSIVE_API_KEY missing')
        r = requests.get(f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/minute/{date_str}/{date_str}", params={'adjusted':'true', 'sort':'asc', 'limit':50000, 'apiKey':self.api_key}, timeout=30)
        r.raise_for_status()
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
