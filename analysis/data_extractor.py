"""
Data Extractor Module

Queries InfluxDB for price and whale event data, and aligns time series.
"""

import sys
from pathlib import Path
import pandas as pd
from influxdb_client import InfluxDBClient
from typing import Optional, List
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import get_settings


class DataExtractor:
    """Extract and align order book data from InfluxDB"""

    def __init__(self):
        self.settings = get_settings()
        self.client = InfluxDBClient(
            url=self.settings.influxdb_url,
            token=self.settings.influxdb_token,
            org=self.settings.influxdb_org
        )
        self.query_api = self.client.query_api()
        self.bucket = self.settings.influxdb_bucket

    def query_price_data(self, symbol: str, lookback_hours: int = 24) -> pd.DataFrame:
        """
        Query continuous price data from orderbook_price measurement

        Args:
            symbol: Trading pair (e.g., "BTC_USDT")
            lookback_hours: Hours of historical data

        Returns:
            DataFrame with columns: time, best_bid, best_ask, mid_price, spread
        """
        logger.info(f"Querying price data for {symbol} (last {lookback_hours} hours)...")

        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{lookback_hours}h)
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        tables = self.query_api.query(query)
        records = []
        for table in tables:
            for record in table.records:
                records.append({
                    'time': record.get_time(),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                    'mid_price': record.values.get('mid_price', 0),
                    'spread': record.values.get('spread', 0),
                })

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values('time').reset_index(drop=True)
        logger.info(f"Loaded {len(df)} price records")
        return df

    def query_whale_events(self, symbol: str, lookback_hours: int = 24,
                          event_types: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Query whale/order book events from orderbook_whale_events measurement

        Args:
            symbol: Trading pair
            lookback_hours: Hours of historical data
            event_types: Filter by specific event types (optional)

        Returns:
            DataFrame with all event fields
        """
        logger.info(f"Querying whale events for {symbol}...")

        event_filter = ""
        if event_types:
            event_conditions = " or ".join([f'r.event_type == "{et}"' for et in event_types])
            event_filter = f'|> filter(fn: (r) => {event_conditions})'

        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{lookback_hours}h)
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          {event_filter}
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        tables = self.query_api.query(query)
        records = []
        for table in tables:
            for record in table.records:
                records.append({
                    'time': record.get_time(),
                    'event_type': record.values.get('event_type', ''),
                    'side': record.values.get('side', ''),
                    'price': record.values.get('price', 0),
                    'volume': record.values.get('volume', 0),
                    'usd_value': record.values.get('usd_value', 0),
                    'distance_from_mid_pct': record.values.get('distance_from_mid_pct', 0),
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                    'spread': record.values.get('spread', 0),
                    'level': record.values.get('level', 0),
                    'order_count': record.values.get('order_count', 0),
                    'info': record.values.get('info', ''),
                })

        df = pd.DataFrame(records)
        if not df.empty:
            df = df.sort_values('time').reset_index(drop=True)
        logger.info(f"Loaded {len(df)} whale events")
        return df

    def align_timeseries(self, price_df: pd.DataFrame, events_df: pd.DataFrame,
                        window: str = '1s') -> pd.DataFrame:
        """
        Align price data with events on common time grid

        Args:
            price_df: Price DataFrame
            events_df: Events DataFrame
            window: Resampling window (e.g., '1s', '5s')

        Returns:
            Combined DataFrame with aligned timestamps
        """
        if price_df.empty or events_df.empty:
            return pd.DataFrame()

        logger.info(f"Aligning time series with {window} window...")

        # Resample price data to regular intervals
        price_df = price_df.set_index('time')
        price_resampled = price_df.resample(window).last().ffill()

        # Merge events with nearest price
        events_df = events_df.set_index('time')
        combined = pd.merge_asof(
            events_df.sort_index(),
            price_resampled[['mid_price', 'spread']],
            left_index=True,
            right_index=True,
            direction='nearest',
            suffixes=('_event', '_current')
        )

        logger.info(f"Aligned {len(combined)} records")
        return combined.reset_index()

    def close(self):
        """Close InfluxDB connection"""
        self.client.close()
