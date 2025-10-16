"""
InfluxDB Service Layer
Handles all InfluxDB operations for live data streaming
"""

import os
from typing import List, Dict, Any, Optional, Tuple
from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi


class InfluxDBService:
    """Service for InfluxDB operations"""

    def __init__(self):
        """Initialize InfluxDB service"""
        self.url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.token = os.getenv("INFLUXDB_TOKEN")
        self.org = os.getenv("INFLUXDB_ORG", "trading")
        self.bucket = os.getenv("INFLUXDB_BUCKET", "trading_data")

    def get_client(self) -> Tuple[Optional[InfluxDBClient], Optional[QueryApi]]:
        """
        Get configured InfluxDB client and query API

        Returns:
            Tuple of (client, query_api) or (None, None) if connection fails
        """
        try:
            if not self.token:
                print("Warning: INFLUXDB_TOKEN not set")
                return None, None

            client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org
            )

            query_api = client.query_api()
            return client, query_api

        except Exception as e:
            print(f"Failed to connect to InfluxDB: {e}")
            return None, None

    def get_price_data(
        self,
        symbol: str,
        start: str,
        end: str
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Fetch raw price data from InfluxDB for a specific time range

        Args:
            symbol: Trading symbol (e.g., BTC_USDT)
            start: Start time (ISO 8601 format)
            end: End time (ISO 8601 format)

        Returns:
            Tuple of (price_points list, error_message)
        """
        try:
            client, query_api = self.get_client()
            if not client:
                return [], "InfluxDB not configured"

            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: {start}, stop: {end})
              |> filter(fn: (r) => r._measurement == "orderbook_price")
              |> filter(fn: (r) => r.symbol == "{symbol}")
              |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''

            result = query_api.query(query)

            price_points = []
            for table in result:
                for record in table.records:
                    price_points.append({
                        'time': record.get_time().isoformat(),
                        'mid_price': record.values.get('mid_price', 0),
                        'best_bid': record.values.get('best_bid', 0),
                        'best_ask': record.values.get('best_ask', 0),
                        'spread': record.values.get('spread', 0)
                    })

            client.close()
            return price_points, None

        except Exception as e:
            import traceback
            print(f"Error fetching price data: {e}")
            print(traceback.format_exc())
            return [], str(e)

    def get_whale_events(
        self,
        symbol: str,
        start: str,
        end: str
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Fetch raw whale events from InfluxDB for a specific time range

        Args:
            symbol: Trading symbol (e.g., BTC_USDT)
            start: Start time (ISO 8601 format)
            end: End time (ISO 8601 format)

        Returns:
            Tuple of (events list, error_message)
        """
        try:
            client, query_api = self.get_client()
            if not client:
                return [], "InfluxDB not configured"

            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: {start}, stop: {end})
              |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
              |> filter(fn: (r) => r.symbol == "{symbol}")
              |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''

            result = query_api.query(query)

            events = []
            for table in result:
                for record in table.records:
                    events.append({
                        'time': record.get_time().isoformat(),
                        'event_type': record.values.get('event_type', 'unknown'),
                        'side': record.values.get('side', 'unknown'),
                        'price': record.values.get('price', 0),
                        'volume': record.values.get('volume', 0),
                        'usd_value': record.values.get('usd_value', 0),
                        'distance_from_mid_pct': record.values.get('distance_from_mid_pct', 0)
                    })

            client.close()
            return events, None

        except Exception as e:
            import traceback
            print(f"Error fetching whale events: {e}")
            print(traceback.format_exc())
            return [], str(e)

    def get_price_history(
        self,
        symbol: str,
        lookback: str = "1h"
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Get price history for live chart with aggregation

        Args:
            symbol: Trading symbol
            lookback: Time duration (e.g., "1h", "30m")

        Returns:
            Tuple of (price_points list, error_message)
        """
        try:
            client, query_api = self.get_client()
            if not client:
                return [], "InfluxDB not configured"

            # Query with aggregateWindow for better performance
            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: -{lookback})
              |> filter(fn: (r) => r._measurement == "orderbook_price")
              |> filter(fn: (r) => r.symbol == "{symbol}")
              |> filter(fn: (r) => r._field == "mid_price")
              |> aggregateWindow(every: 1s, fn: last, createEmpty: false)
            '''

            result = query_api.query(query)

            price_points = []
            for table in result:
                for record in table.records:
                    price_points.append({
                        'time': record.get_time().isoformat(),
                        'price': record.get_value()
                    })

            client.close()
            return price_points, None

        except Exception as e:
            return [], str(e)

    def get_live_whale_events(
        self,
        symbol: str,
        lookback: str = "30m",
        min_usd: float = 5000,
        last_timestamp: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
        """
        Get recent whale events for live chart - optimized for incremental updates

        Args:
            symbol: Trading symbol
            lookback: Time duration (e.g., "30m", "1h")
            min_usd: Minimum USD value filter
            last_timestamp: Last timestamp for incremental updates (ISO format)

        Returns:
            Tuple of (events list, is_incremental flag, error_message)
        """
        try:
            client, query_api = self.get_client()
            if not client:
                return [], False, "InfluxDB not configured"

            # If last_timestamp provided, only fetch newer events (incremental)
            # Otherwise fetch full history (initial load)
            if last_timestamp:
                # Convert ISO timestamp to RFC3339 format for Flux
                # Handle URL decoding: space back to +, then + to Z
                start_time = last_timestamp.replace(' 00:00', '+00:00').replace('+00:00', 'Z')

                # Use time() function in Flux to properly parse RFC3339 timestamp
                query = f'''
                from(bucket: "{self.bucket}")
                  |> range(start: time(v: "{start_time}"))
                  |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
                  |> filter(fn: (r) => r.symbol == "{symbol}")
                  |> filter(fn: (r) => r._field == "usd_value" or r._field == "price" or r._field == "volume" or r._field == "distance_from_mid_pct")
                  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
                  |> filter(fn: (r) => r.usd_value >= {min_usd})
                  |> sort(columns: ["_time"], desc: false)
                '''
            else:
                # Initial load - get historical events
                query = f'''
                from(bucket: "{self.bucket}")
                  |> range(start: -{lookback})
                  |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
                  |> filter(fn: (r) => r.symbol == "{symbol}")
                  |> filter(fn: (r) => r._field == "usd_value" or r._field == "price" or r._field == "volume" or r._field == "distance_from_mid_pct")
                  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
                  |> filter(fn: (r) => r.usd_value >= {min_usd})
                  |> sort(columns: ["_time"], desc: true)
                  |> limit(n: 100)
                '''

            result = query_api.query(query)

            # Parse events from pivoted data
            events = []
            for table in result:
                for record in table.records:
                    event = {
                        'time': record.get_time().isoformat(),
                        'event_type': record.values.get('event_type'),
                        'side': record.values.get('side'),
                        'price': record.values.get('price'),
                        'volume': record.values.get('volume'),
                        'usd_value': record.values.get('usd_value'),
                        'distance_from_mid_pct': record.values.get('distance_from_mid_pct')
                    }
                    events.append(event)

            if last_timestamp:
                # For incremental updates, sort ascending (oldest first)
                events.sort(key=lambda x: x['time'])
            else:
                # For initial load, sort descending (newest first) and limit
                events.sort(key=lambda x: x['time'], reverse=True)
                events = events[:100]

            client.close()
            return events, last_timestamp is not None, None

        except Exception as e:
            import traceback
            print(f"Error fetching live whale events: {e}")
            print(traceback.format_exc())
            return [], False, str(e)

    def get_orderbook_snapshot(
        self,
        symbol: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Get latest orderbook snapshot

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (orderbook data, error_message)
        """
        try:
            client, query_api = self.get_client()
            if not client:
                return None, "InfluxDB not configured"

            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: -5m)
              |> filter(fn: (r) => r._measurement == "orderbook_snapshot")
              |> filter(fn: (r) => r.symbol == "{symbol}")
              |> last()
              |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''

            result = query_api.query(query)

            orderbook = None
            for table in result:
                for record in table.records:
                    orderbook = {
                        'time': record.get_time().isoformat(),
                        'symbol': symbol,
                        'bids': record.values.get('bids', []),
                        'asks': record.values.get('asks', []),
                        'mid_price': record.values.get('mid_price', 0)
                    }
                    break

            client.close()
            return orderbook, None

        except Exception as e:
            return None, str(e)

    def get_live_stats(
        self,
        symbol: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Get live statistics for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (stats dict, error_message)
        """
        try:
            client, query_api = self.get_client()
            if not client:
                return None, "InfluxDB not configured"

            # Get recent price stats
            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: -1h)
              |> filter(fn: (r) => r._measurement == "orderbook_price")
              |> filter(fn: (r) => r.symbol == "{symbol}")
              |> filter(fn: (r) => r._field == "mid_price")
            '''

            result = query_api.query(query)

            prices = []
            for table in result:
                for record in table.records:
                    prices.append(record.get_value())

            stats = {}
            if prices:
                stats['current_price'] = prices[-1]
                stats['min_price'] = min(prices)
                stats['max_price'] = max(prices)
                stats['avg_price'] = sum(prices) / len(prices)
                stats['price_change'] = ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] != 0 else 0

            client.close()
            return stats, None

        except Exception as e:
            return None, str(e)
