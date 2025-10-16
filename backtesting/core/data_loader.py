"""
DataLoader - Fetches historical data from InfluxDB and MongoDB

This module handles all data retrieval and preprocessing for backtesting.
It connects to your existing InfluxDB (for tick data and whale events) and
MongoDB (for pre-computed analysis results).
"""

import os
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from influxdb_client import InfluxDBClient
from pymongo import MongoClient
from loguru import logger


class DataLoader:
    """
    Loads and preprocesses historical data for backtesting

    Data Sources:
    - InfluxDB: orderbook_price (tick data)
    - InfluxDB: orderbook_whale_events (whale activity)
    - MongoDB: Pre-computed analysis results (optional)

    Example:
        loader = DataLoader()

        # Load price data
        prices = loader.get_price_data(
            symbol='BTC_USDT',
            start='2025-09-01',
            end='2025-10-01'
        )

        # Load whale events
        whales = loader.get_whale_events(
            symbol='BTC_USDT',
            start='2025-09-01',
            end='2025-10-01'
        )

        # Get unified timeline
        data = loader.create_unified_timeline(prices, whales)
    """

    def __init__(self,
                 influxdb_url: Optional[str] = None,
                 influxdb_token: Optional[str] = None,
                 influxdb_org: Optional[str] = None,
                 influxdb_bucket: Optional[str] = None,
                 mongodb_url: Optional[str] = None,
                 mongodb_database: Optional[str] = None):
        """
        Initialize DataLoader with database connections

        Args:
            influxdb_url: InfluxDB URL (default: from env)
            influxdb_token: InfluxDB token (default: from env)
            influxdb_org: InfluxDB organization (default: from env)
            influxdb_bucket: InfluxDB bucket (default: from env)
            mongodb_url: MongoDB URL (default: from env)
            mongodb_database: MongoDB database name (default: from env)
        """
        # InfluxDB connection
        self.influx_url = influxdb_url or os.getenv('INFLUXDB_URL', 'http://localhost:8086')
        self.influx_token = influxdb_token or os.getenv('INFLUXDB_TOKEN')
        self.influx_org = influxdb_org or os.getenv('INFLUXDB_ORG', 'trading')
        self.influx_bucket = influxdb_bucket or os.getenv('INFLUXDB_BUCKET', 'trading_data')

        if not self.influx_token:
            raise ValueError("INFLUXDB_TOKEN environment variable or parameter is required")

        self.influx_client = InfluxDBClient(
            url=self.influx_url,
            token=self.influx_token,
            org=self.influx_org
        )
        self.query_api = self.influx_client.query_api()

        # MongoDB connection (optional)
        self.mongodb_url = mongodb_url or os.getenv('MONGODB_URL', 'mongodb://localhost:27017')
        self.mongodb_database = mongodb_database or os.getenv('MONGODB_DATABASE', 'orderbook_analytics')

        try:
            self.mongo_client = MongoClient(self.mongodb_url, serverSelectionTimeoutMS=2000)
            self.mongo_client.server_info()  # Test connection
            self.mongo_db = self.mongo_client[self.mongodb_database]
            logger.info(f"Connected to MongoDB: {self.mongodb_database}")
        except Exception as e:
            logger.warning(f"MongoDB connection failed: {e}. MongoDB features disabled.")
            self.mongo_client = None
            self.mongo_db = None

    def get_price_data(self,
                       symbol: str,
                       start: str,
                       end: str,
                       resolution: str = '1s') -> pd.DataFrame:
        """
        Fetch price data from InfluxDB

        Args:
            symbol: Trading symbol (e.g., 'BTC_USDT')
            start: Start time (ISO format or datetime)
            end: End time (ISO format or datetime)
            resolution: Time resolution (not implemented - returns raw data)

        Returns:
            DataFrame with columns: timestamp, mid_price, best_bid, best_ask, spread
        """
        # Convert string dates to datetime if needed
        if isinstance(start, str):
            start = self._parse_time_string(start)
        if isinstance(end, str):
            end = self._parse_time_string(end)

        start_str = start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_str = end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        query = f'''
        from(bucket: "{self.influx_bucket}")
          |> range(start: {start_str}, stop: {end_str})
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        logger.info(f"Fetching price data for {symbol} from {start_str} to {end_str}")

        result = self.query_api.query(query)

        # Convert to DataFrame
        data = []
        for table in result:
            for record in table.records:
                data.append({
                    'timestamp': record.get_time(),
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                    'spread': record.values.get('spread', 0),
                })

        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values('timestamp').reset_index(drop=True)
            logger.info(f"Loaded {len(df):,} price points")
        else:
            logger.warning(f"No price data found for {symbol}")

        return df

    def get_whale_events(self,
                         symbol: str,
                         start: str,
                         end: str,
                         min_usd: Optional[float] = None) -> pd.DataFrame:
        """
        Fetch whale events from InfluxDB

        Args:
            symbol: Trading symbol (e.g., 'BTC_USDT')
            start: Start time (ISO format or datetime)
            end: End time (ISO format or datetime)
            min_usd: Minimum USD value filter (optional)

        Returns:
            DataFrame with columns: timestamp, event_type, side, price, volume,
                                   usd_value, distance_from_mid_pct, etc.
        """
        # Convert string dates to datetime if needed
        if isinstance(start, str):
            start = self._parse_time_string(start)
        if isinstance(end, str):
            end = self._parse_time_string(end)

        start_str = start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_str = end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        query = f'''
        from(bucket: "{self.influx_bucket}")
          |> range(start: {start_str}, stop: {end_str})
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        logger.info(f"Fetching whale events for {symbol} from {start_str} to {end_str}")

        result = self.query_api.query(query)

        # Convert to DataFrame
        data = []
        for table in result:
            for record in table.records:
                data.append({
                    'timestamp': record.get_time(),
                    'event_type': record.values.get('event_type', 'unknown'),
                    'side': record.values.get('side', 'unknown'),
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
                })

        df = pd.DataFrame(data)

        if not df.empty:
            df = df.sort_values('timestamp').reset_index(drop=True)

            # Apply minimum USD filter if specified
            if min_usd is not None:
                df = df[df['usd_value'] >= min_usd]
                logger.info(f"Loaded {len(df):,} whale events (min_usd=${min_usd:,})")
            else:
                logger.info(f"Loaded {len(df):,} whale events")
        else:
            logger.warning(f"No whale events found for {symbol}")

        return df

    def create_unified_timeline(self,
                                price_data: pd.DataFrame,
                                whale_events: pd.DataFrame,
                                window_size: str = '1min') -> pd.DataFrame:
        """
        Merge price data and whale events into unified timeline with aggregated features

        This creates a time-series DataFrame with:
        - Price data (mid_price, spread)
        - Whale activity aggregated into time windows
        - Derived features (imbalance, volume ratios)

        Args:
            price_data: DataFrame from get_price_data()
            whale_events: DataFrame from get_whale_events()
            window_size: Rolling window size for aggregations (e.g., '1min', '5min')

        Returns:
            DataFrame with unified timeline and features
        """
        if price_data.empty:
            logger.error("Cannot create timeline: price_data is empty")
            return pd.DataFrame()

        # Start with price data as base timeline
        df = price_data.copy()
        df = df.set_index('timestamp')

        if whale_events.empty:
            logger.warning("No whale events to merge - using price data only")
            return df.reset_index()

        # Aggregate whale events into time buckets
        whale_df = whale_events.copy()
        whale_df = whale_df.set_index('timestamp')

        # Calculate whale activity metrics per time window
        whale_agg = whale_df.resample(window_size).agg({
            'usd_value': ['sum', 'count', 'max'],
            'event_type': lambda x: (x == 'market_buy').sum(),  # Count market buys
        }).fillna(0)

        # Flatten column names
        whale_agg.columns = ['whale_usd_total', 'whale_count', 'whale_max_usd', 'market_buy_count']

        # Calculate market sell count
        whale_agg['market_sell_count'] = whale_df.resample(window_size)['event_type'].apply(
            lambda x: (x == 'market_sell').sum()
        ).fillna(0)

        # Calculate bid/ask imbalance from whale events
        whale_bid_volume = whale_df[whale_df['side'] == 'bid'].resample(window_size)['usd_value'].sum().fillna(0)
        whale_ask_volume = whale_df[whale_df['side'] == 'ask'].resample(window_size)['usd_value'].sum().fillna(0)

        whale_agg['whale_bid_volume'] = whale_bid_volume
        whale_agg['whale_ask_volume'] = whale_ask_volume
        whale_agg['whale_imbalance'] = (whale_bid_volume - whale_ask_volume) / (whale_bid_volume + whale_ask_volume + 1e-9)

        # Merge with price data (forward fill for missing whale data)
        df = df.merge(whale_agg, left_index=True, right_index=True, how='left')
        df = df.fillna(0)

        # Add derived features
        df['price_change_pct'] = df['mid_price'].pct_change() * 100
        df['spread_pct'] = (df['spread'] / df['mid_price']) * 100

        logger.info(f"Created unified timeline with {len(df):,} data points")

        return df.reset_index()

    def _parse_time_string(self, time_str: str) -> datetime:
        """
        Parse time string to timezone-aware UTC datetime

        Supports:
        - ISO 8601: "2025-10-15T14:00:00Z"
        - Simple: "2025-10-15 14:00:00"
        - Date only: "2025-10-15"
        """
        if not time_str:
            raise ValueError("Time string cannot be empty")

        # Try ISO 8601 with Z
        try:
            dt = datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%SZ')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        # Try ISO format
        try:
            dt = datetime.fromisoformat(time_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except ValueError:
            pass

        # Try simple datetime
        try:
            dt = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        # Try date only
        try:
            dt = datetime.strptime(time_str, '%Y-%m-%d')
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        raise ValueError(
            f"Invalid time format: '{time_str}'. "
            f"Supported: 'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SSZ'"
        )

    def close(self):
        """Close database connections"""
        if self.influx_client:
            self.influx_client.close()
            logger.info("Closed InfluxDB connection")

        if self.mongo_client:
            self.mongo_client.close()
            logger.info("Closed MongoDB connection")
