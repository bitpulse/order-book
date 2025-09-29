"""
InfluxDB Query Service for API
"""

from influxdb_client import InfluxDBClient
from influxdb_client.client.query_api import QueryApi
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger
import os
from dotenv import load_dotenv

load_dotenv()


class InfluxDBService:
    """Service for querying InfluxDB time-series data"""

    def __init__(self):
        self.client = InfluxDBClient(
            url=os.getenv("INFLUXDB_URL", "http://localhost:8086"),
            token=os.getenv("INFLUXDB_TOKEN"),
            org=os.getenv("INFLUXDB_ORG", "bitpulse")
        )
        self.query_api: QueryApi = self.client.query_api()
        self.bucket = os.getenv("INFLUXDB_BUCKET", "trading_data")
        self.org = os.getenv("INFLUXDB_ORG", "bitpulse")

    async def get_current_orderbook(self, symbol: str) -> Dict[str, Any]:
        """Get current order book snapshot"""
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -1m)
          |> filter(fn: (r) => r._measurement == "order_book_snapshot")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> last()
        '''

        tables = self.query_api.query(query, org=self.org)

        bids = []
        asks = []
        timestamp = None

        for table in tables:
            for record in table.records:
                side = record.values.get('side')
                level = int(record.values.get('level', 0))
                field = record.values.get('_field')
                value = record.values.get('_value')
                timestamp = record.values.get('_time')

                # Build order book levels
                if side == 'bid':
                    if len(bids) < level:
                        bids.extend([{} for _ in range(level - len(bids))])
                    if field in ['price', 'volume', 'total_value']:
                        bids[level-1][field] = value
                elif side == 'ask':
                    if len(asks) < level:
                        asks.extend([{} for _ in range(level - len(asks))])
                    if field in ['price', 'volume', 'total_value']:
                        asks[level-1][field] = value

        return {
            "symbol": symbol,
            "timestamp": timestamp.isoformat() if timestamp else None,
            "bids": bids,
            "asks": asks
        }

    async def get_current_stats(self, symbol: str) -> Dict[str, Any]:
        """Get current order book statistics"""
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -1m)
          |> filter(fn: (r) => r._measurement == "order_book_stats")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> last()
        '''

        tables = self.query_api.query(query, org=self.org)

        stats = {}
        timestamp = None

        for table in tables:
            for record in table.records:
                field = record.values.get('_field')
                value = record.values.get('_value')
                timestamp = record.values.get('_time')
                stats[field] = value

        return {
            "symbol": symbol,
            "timestamp": timestamp.isoformat() if timestamp else None,
            **stats
        }

    async def get_recent_whales(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        min_value: float = 50000
    ) -> List[Dict[str, Any]]:
        """Get recent whale orders"""
        try:
            query_filter = f'''
              |> filter(fn: (r) => r._measurement == "whale_orders")'''

            if symbol:
                query_filter += f'''
              |> filter(fn: (r) => r.symbol == "{symbol}")'''

            query_filter += f'''
              |> filter(fn: (r) => r._field == "value_usdt")
              |> filter(fn: (r) => r._value >= {min_value})'''

            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: -1h){query_filter}
              |> sort(columns: ["_time"], desc: true)
              |> limit(n: {limit})
            '''

            tables = self.query_api.query(query, org=self.org)

            whales = []
            processed_times = set()  # Track processed timestamps to avoid duplicates

            for table in tables:
                for record in table.records:
                    timestamp = record.values.get('_time')
                    if not timestamp:
                        continue

                    # Create unique key to avoid duplicates
                    key = f"{record.values.get('symbol')}_{record.values.get('side')}_{timestamp}"
                    if key in processed_times:
                        continue
                    processed_times.add(key)

                    # Get all tags and fields for this whale order
                    whale_data = {
                        "symbol": record.values.get('symbol', 'UNKNOWN'),
                        "side": record.values.get('side', 'unknown'),
                        "timestamp": timestamp.isoformat(),
                        "value_usdt": float(record.values.get('_value', 0)),
                        "price": 0.0,
                        "volume": 0.0,
                        "distance_from_mid": 0.0,
                        "level": 0
                    }

                    # Try to get additional fields
                    try:
                        detail_query = f'''
                        from(bucket: "{self.bucket}")
                          |> range(start: -1h)
                          |> filter(fn: (r) => r._measurement == "whale_orders")
                          |> filter(fn: (r) => r.symbol == "{whale_data['symbol']}")
                          |> filter(fn: (r) => r.side == "{whale_data['side']}")
                          |> filter(fn: (r) => r._time == {timestamp.timestamp()}s)
                        '''

                        detail_tables = self.query_api.query(detail_query, org=self.org)
                        for dt in detail_tables:
                            for dr in dt.records:
                                field = dr.values.get('_field')
                                if field == 'price':
                                    whale_data['price'] = float(dr.values.get('_value', 0))
                                elif field == 'volume':
                                    whale_data['volume'] = float(dr.values.get('_value', 0))
                                elif field == 'distance_from_mid':
                                    whale_data['distance_from_mid'] = float(dr.values.get('_value', 0))
                                elif field == 'level':
                                    whale_data['level'] = int(dr.values.get('_value', 0))
                    except Exception:
                        pass  # Use defaults if detail query fails

                    whales.append(whale_data)

            return whales

        except Exception as e:
            logger.error(f"Error getting recent whales: {e}")
            # Return empty list on error
            return []

    async def get_spread_history(
        self,
        symbol: str,
        start: str = "-1h",
        interval: str = "1m"
    ) -> List[Dict[str, Any]]:
        """Get spread history with aggregation"""
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: {start})
          |> filter(fn: (r) => r._measurement == "order_book_stats")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> filter(fn: (r) => r._field == "spread_percentage" or r._field == "spread")
          |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
        '''

        tables = self.query_api.query(query, org=self.org)

        results = []
        data_points = {}

        for table in tables:
            for record in table.records:
                time = record.values.get('_time')
                field = record.values.get('_field')
                value = record.values.get('_value')

                if time not in data_points:
                    data_points[time] = {"timestamp": time.isoformat()}
                data_points[time][field] = value

        results = list(data_points.values())
        results.sort(key=lambda x: x['timestamp'])

        return results

    async def get_recent_whales(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        min_value: float = 50000
    ) -> List[Dict[str, Any]]:
        """Get recent whale orders"""
        symbol_filter = f'|> filter(fn: (r) => r.symbol == "{symbol}")' if symbol else ''

        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -24h)
          |> filter(fn: (r) => r._measurement == "whale_orders")
          {symbol_filter}
          |> filter(fn: (r) => r._field == "value_usdt")
          |> filter(fn: (r) => r._value >= {min_value})
          |> sort(columns: ["_time"], desc: true)
          |> limit(n: {limit})
        '''

        tables = self.query_api.query(query, org=self.org)

        whales = []
        whale_times = []

        # First get the times of whale orders
        for table in tables:
            for record in table.records:
                whale_times.append(record.values.get('_time'))

        # Then get full details for each whale order
        for whale_time in whale_times[:limit]:
            # Format time properly for Flux query
            time_str = whale_time.isoformat().replace('+00:00', 'Z')
            detail_query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: -24h)
              |> filter(fn: (r) => r._measurement == "whale_orders")
              |> filter(fn: (r) => r._time == {time_str})
            '''

            detail_tables = self.query_api.query(detail_query, org=self.org)
            whale_data = {
                "timestamp": whale_time.isoformat()
            }

            for table in detail_tables:
                for record in table.records:
                    field = record.values.get('_field')
                    value = record.values.get('_value')
                    whale_data[field] = value

                    # Also get tags
                    whale_data['symbol'] = record.values.get('symbol')
                    whale_data['side'] = record.values.get('side')

            whales.append(whale_data)

        return whales

    async def get_market_depth(
        self,
        symbol: str,
        depth_percentage: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get current market depth at various percentages"""
        depth_filter = f'|> filter(fn: (r) => r.depth_percentage == "{depth_percentage}")' if depth_percentage else ''

        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -1m)
          |> filter(fn: (r) => r._measurement == "market_depth")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          {depth_filter}
          |> last()
        '''

        tables = self.query_api.query(query, org=self.org)

        depth_data = {}

        for table in tables:
            for record in table.records:
                depth_pct = record.values.get('depth_percentage')
                field = record.values.get('_field')
                value = record.values.get('_value')
                timestamp = record.values.get('_time')

                if depth_pct not in depth_data:
                    depth_data[depth_pct] = {
                        "depth_percentage": depth_pct,
                        "timestamp": timestamp.isoformat() if timestamp else None
                    }
                depth_data[depth_pct][field] = value

        return list(depth_data.values())

    async def get_imbalance_history(
        self,
        symbol: str,
        start: str = "-1h",
        interval: str = "1m"
    ) -> List[Dict[str, Any]]:
        """Get order book imbalance history"""
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: {start})
          |> filter(fn: (r) => r._measurement == "order_book_stats")
          |> filter(fn: (r) => r.symbol == "{symbol}")
          |> filter(fn: (r) => r._field == "imbalance")
          |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
        '''

        tables = self.query_api.query(query, org=self.org)

        results = []
        for table in tables:
            for record in table.records:
                results.append({
                    "timestamp": record.values.get('_time').isoformat(),
                    "imbalance": record.values.get('_value')
                })

        return results

    async def get_whale_statistics(
        self,
        symbol: Optional[str] = None,
        period: str = "-24h"
    ) -> Dict[str, Any]:
        """Get whale order statistics"""
        symbol_filter = f'|> filter(fn: (r) => r.symbol == "{symbol}")' if symbol else ''

        # Count whales by category
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: {period})
          |> filter(fn: (r) => r._measurement == "whale_orders")
          {symbol_filter}
          |> filter(fn: (r) => r._field == "value_usdt")
          |> group(columns: ["side"])
          |> count()
        '''

        tables = self.query_api.query(query, org=self.org)

        stats = {
            "period": period,
            "symbol": symbol,
            "total_count": 0,
            "bid_count": 0,
            "ask_count": 0,
            "categories": {}
        }

        for table in tables:
            for record in table.records:
                side = record.values.get('side')
                count = record.values.get('_value')

                if side == 'bid':
                    stats['bid_count'] = count
                elif side == 'ask':
                    stats['ask_count'] = count
                stats['total_count'] += count

        # Get average values
        avg_query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: {period})
          |> filter(fn: (r) => r._measurement == "whale_orders")
          {symbol_filter}
          |> filter(fn: (r) => r._field == "value_usdt")
          |> mean()
        '''

        avg_tables = self.query_api.query(avg_query, org=self.org)
        for table in avg_tables:
            for record in table.records:
                stats['average_value'] = record.values.get('_value')

        return stats

    def close(self):
        """Close InfluxDB connection"""
        self.client.close()