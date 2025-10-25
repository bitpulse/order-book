"""
DataLoader - Fetches historical data from InfluxDB and MongoDB

This module handles all data retrieval and preprocessing for backtesting.
It connects to your existing InfluxDB (for tick data and whale events) and
MongoDB (for pre-computed analysis results).
"""

import os
import pandas as pd
import hashlib
from pathlib import Path
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
                 mongodb_database: Optional[str] = None,
                 cache_dir: Optional[str] = None,
                 use_cache: bool = True,
                 cache_max_age_days: int = 30):
        """
        Initialize DataLoader with database connections

        Args:
            influxdb_url: InfluxDB URL (default: from env)
            influxdb_token: InfluxDB token (default: from env)
            influxdb_org: InfluxDB organization (default: from env)
            influxdb_bucket: InfluxDB bucket (default: from env)
            mongodb_url: MongoDB URL (default: from env)
            mongodb_database: MongoDB database name (default: from env)
            cache_dir: Directory for cached data files (default: ./backtesting/cache/)
            use_cache: Enable file-based caching (default: True)
            cache_max_age_days: Max age of cache files in days (default: 30)
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
            org=self.influx_org,
            timeout=3_600_000,  # 60 minute timeout (in milliseconds)
            enable_gzip=True    # Enable compression for large queries
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

        # File-based cache settings
        self.use_cache = use_cache
        self.cache_max_age_days = cache_max_age_days
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Default to backtesting/cache/ relative to project root
            self.cache_dir = Path(__file__).parent.parent / 'cache'

        # Create cache directory if it doesn't exist
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cache directory: {self.cache_dir}")

    def _get_cache_filename(self, data_type: str, symbol: str, start: datetime, end: datetime) -> Path:
        """
        Generate cache filename based on query parameters

        Args:
            data_type: 'prices' or 'whales'
            symbol: Trading symbol
            start: Start datetime
            end: End datetime

        Returns:
            Path to cache file
        """
        # Format timestamps as YYYY-MM-DD_HH-MM-SS
        start_str = start.strftime('%Y-%m-%d_%H-%M-%S')
        end_str = end.strftime('%Y-%m-%d_%H-%M-%S')

        # Create filename: type_SYMBOL_START_END.parquet
        filename = f"{data_type}_{symbol}_{start_str}_{end_str}.parquet"
        return self.cache_dir / filename

    def _load_from_cache(self, cache_file: Path) -> Optional[pd.DataFrame]:
        """
        Load data from cache file if it exists and is not too old

        Args:
            cache_file: Path to cache file

        Returns:
            DataFrame if cache is valid, None otherwise
        """
        if not cache_file.exists():
            return None

        # Check file age
        file_age_days = (datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)).days
        if file_age_days > self.cache_max_age_days:
            logger.info(f"Cache file too old ({file_age_days} days), refreshing: {cache_file.name}")
            cache_file.unlink()  # Delete old cache
            return None

        try:
            df = pd.read_parquet(cache_file)
            logger.info(f"Loaded {len(df):,} rows from cache: {cache_file.name}")
            return df
        except Exception as e:
            logger.warning(f"Failed to load cache file {cache_file.name}: {e}")
            return None

    def _save_to_cache(self, df: pd.DataFrame, cache_file: Path):
        """
        Save DataFrame to cache file

        Args:
            df: DataFrame to cache
            cache_file: Path to cache file
        """
        try:
            df.to_parquet(cache_file, index=False)
            logger.info(f"Saved {len(df):,} rows to cache: {cache_file.name}")
        except Exception as e:
            logger.warning(f"Failed to save cache file {cache_file.name}: {e}")

    def get_price_data(self,
                       symbol: str,
                       start: str,
                       end: str,
                       resolution: str = '1s') -> pd.DataFrame:
        """
        Fetch price data from InfluxDB (with file-based caching)

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

        # Try to load from cache first
        if self.use_cache:
            cache_file = self._get_cache_filename('prices', symbol, start, end)
            cached_df = self._load_from_cache(cache_file)
            if cached_df is not None:
                # Convert timestamp column back to datetime if needed
                if 'timestamp' in cached_df.columns and not pd.api.types.is_datetime64_any_dtype(cached_df['timestamp']):
                    cached_df['timestamp'] = pd.to_datetime(cached_df['timestamp'])
                return cached_df

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

            # Save to cache
            if self.use_cache:
                self._save_to_cache(df, cache_file)
        else:
            logger.warning(f"No price data found for {symbol}")

        return df

    def get_whale_events(self,
                         symbol: str,
                         start: str,
                         end: str,
                         min_usd: Optional[float] = None) -> pd.DataFrame:
        """
        Fetch whale events from InfluxDB (with file-based caching)

        Args:
            symbol: Trading symbol (e.g., 'BTC_USDT')
            start: Start time (ISO format or datetime)
            end: End time (ISO format or datetime)
            min_usd: Minimum USD value filter (optional, applied after loading from cache)

        Returns:
            DataFrame with columns: timestamp, event_type, side, price, volume,
                                   usd_value, distance_from_mid_pct, etc.
        """
        # Convert string dates to datetime if needed
        if isinstance(start, str):
            start = self._parse_time_string(start)
        if isinstance(end, str):
            end = self._parse_time_string(end)

        # Try to load from cache first (cache contains ALL events, we filter by min_usd after)
        if self.use_cache:
            cache_file = self._get_cache_filename('whales', symbol, start, end)
            cached_df = self._load_from_cache(cache_file)
            if cached_df is not None:
                # Convert timestamp column back to datetime if needed
                if 'timestamp' in cached_df.columns and not pd.api.types.is_datetime64_any_dtype(cached_df['timestamp']):
                    cached_df['timestamp'] = pd.to_datetime(cached_df['timestamp'])

                # Apply minimum USD filter if specified
                if min_usd is not None:
                    filtered_df = cached_df[cached_df['usd_value'] >= min_usd].copy()
                    logger.info(f"Filtered cached data: {len(filtered_df):,} whale events (min_usd=${min_usd:,})")
                    return filtered_df
                return cached_df

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
            logger.info(f"Loaded {len(df):,} whale events from InfluxDB")

            # Save to cache BEFORE filtering (so we cache all data)
            if self.use_cache:
                self._save_to_cache(df, cache_file)

            # Apply minimum USD filter if specified
            if min_usd is not None:
                df = df[df['usd_value'] >= min_usd]
                logger.info(f"Filtered to {len(df):,} whale events (min_usd=${min_usd:,})")
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
            # Add empty whale columns
            df['whale_usd_total'] = 0
            df['whale_count'] = 0
            df['whale_max_usd'] = 0
            df['market_buy_count'] = 0
            df['market_sell_count'] = 0
            df['whale_bid_volume'] = 0
            df['whale_ask_volume'] = 0
            df['whale_imbalance'] = 0
            df['price_change_pct'] = df['mid_price'].pct_change() * 100
            df['spread_pct'] = (df['spread'] / df['mid_price']) * 100
            return df  # Keep timestamp as index!

        # Don't resample - keep whale events at their exact timestamps
        # Instead, we'll match them in the backtest engine directly
        # But we still need to add whale columns to price data for compatibility

        # Initialize whale columns with zeros
        df['whale_usd_total'] = 0.0
        df['whale_count'] = 0
        df['whale_max_usd'] = 0.0
        df['market_buy_count'] = 0
        df['market_sell_count'] = 0
        df['whale_bid_volume'] = 0.0
        df['whale_ask_volume'] = 0.0
        df['whale_imbalance'] = 0.0

        # Add derived features
        df['price_change_pct'] = df['mid_price'].pct_change() * 100
        df['spread_pct'] = (df['spread'] / df['mid_price']) * 100

        logger.info(f"Created unified timeline with {len(df):,} data points")

        return df  # Keep timestamp as index!

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
