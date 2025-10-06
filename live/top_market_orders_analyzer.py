#!/usr/bin/env python3
"""
Top Market Orders Analyzer
Finds and ranks INDIVIDUAL market buy/sell orders by size (no time intervals)
Filters by distance from mid price and minimum USD value
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

# ANSI color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'
WHITE = '\033[97m'
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

# Load environment variables
load_dotenv()


class TopMarketOrdersAnalyzer:
    """Analyzes and ranks individual market buy/sell orders by size"""

    def __init__(self, symbol: str, lookback: str,
                 min_usd: float = 10000,
                 max_distance: float = None,
                 min_distance: float = None,
                 top_n: int = 50,
                 sort_by: str = 'size'):
        """
        Initialize the analyzer

        Args:
            symbol: Trading pair (e.g., BTC_USDT)
            lookback: Time period to analyze (e.g., 1h, 24h, 7d)
            min_usd: Minimum USD value per order
            max_distance: Maximum distance from mid price (%)
            min_distance: Minimum distance from mid price (%)
            top_n: Number of top orders to return
            sort_by: Sorting criteria (size, distance, time)
        """
        self.symbol = symbol
        self.lookback = lookback
        self.min_usd = min_usd
        self.max_distance = max_distance
        self.min_distance = min_distance
        self.top_n = top_n
        self.sort_by = sort_by

        # Initialize InfluxDB client
        self.influx_url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
        self.influx_token = os.getenv("INFLUXDB_TOKEN")
        self.influx_org = os.getenv("INFLUXDB_ORG", "trading")
        self.influx_bucket = os.getenv("INFLUXDB_BUCKET", "trading_data")

        if not self.influx_token:
            raise ValueError("INFLUXDB_TOKEN environment variable is required")

        self.client = InfluxDBClient(
            url=self.influx_url,
            token=self.influx_token,
            org=self.influx_org
        )
        self.query_api = self.client.query_api()

    def _parse_lookback_to_timedelta(self, lookback: str) -> timedelta:
        """Parse lookback string (e.g., '1h', '24h', '7d') to timedelta"""
        value = int(lookback[:-1])
        unit = lookback[-1]

        if unit == 's':
            return timedelta(seconds=value)
        elif unit == 'm':
            return timedelta(minutes=value)
        elif unit == 'h':
            return timedelta(hours=value)
        elif unit == 'd':
            return timedelta(days=value)
        else:
            raise ValueError(f"Invalid lookback unit: {unit}. Use s, m, h, or d")

    def get_all_whale_events(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Get ALL whale events for the time period (market orders, limit orders, volume changes)

        Args:
            start_time: Start of interval
            end_time: End of interval

        Returns:
            List of whale event dicts
        """
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        print(f"{CYAN}Querying all whale events from {start_time} to {end_time}...{RESET}")

        # Query ALL whale events (not just market orders)
        query_filters = [
            f'r._measurement == "orderbook_whale_events"',
            f'r.symbol == "{self.symbol}"'
        ]

        query = f'''
        from(bucket: "{self.influx_bucket}")
          |> range(start: {start_str}, stop: {end_str})
          |> filter(fn: (r) => {" and ".join(query_filters)})
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        result = self.query_api.query(query)

        events = []
        for table in result:
            for record in table.records:
                event = {
                    'time': record.get_time(),
                    'event_type': record.values.get('event_type', 'unknown'),
                    'side': record.values.get('side', 'unknown'),
                    'price': record.values.get('price', 0),
                    'volume': record.values.get('volume', 0),
                    'usd_value': record.values.get('usd_value', 0),
                    'distance_from_mid_pct': record.values.get('distance_from_mid_pct', 0),
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                }

                # Apply filters
                if event['usd_value'] < self.min_usd:
                    continue

                distance = abs(event['distance_from_mid_pct'])

                if self.max_distance is not None and distance > self.max_distance:
                    continue

                if self.min_distance is not None and distance < self.min_distance:
                    continue

                events.append(event)

        events.sort(key=lambda x: x['time'])
        return events

    def get_price_data(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get price data for context"""
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        query = f'''
        from(bucket: "{self.influx_bucket}")
          |> range(start: {start_str}, stop: {end_str})
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{self.symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        result = self.query_api.query(query)

        price_points = []
        for table in result:
            for record in table.records:
                price_points.append({
                    'time': record.get_time(),
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                    'spread': record.values.get('spread', 0),
                })

        price_points.sort(key=lambda x: x['time'])
        return price_points

    def analyze(self) -> Dict:
        """
        Run analysis: find and rank individual market orders

        Returns:
            Dict with metadata and ranked orders
        """
        print(f"{CYAN}Analyzing TOP MARKET ORDERS for {self.symbol}...{RESET}")
        print(f"{DIM}Lookback: {self.lookback}, Min USD: ${self.min_usd:,.0f}{RESET}")
        if self.max_distance is not None:
            print(f"{DIM}Max distance from mid: {self.max_distance}%{RESET}")
        if self.min_distance is not None:
            print(f"{DIM}Min distance from mid: {self.min_distance}%{RESET}")
        print()

        lookback_time = datetime.now(timezone.utc) - self._parse_lookback_to_timedelta(self.lookback)
        end_time = datetime.now(timezone.utc)

        # Get all whale events (market orders, limit orders, volume changes)
        all_events = self.get_all_whale_events(lookback_time, end_time)

        if not all_events:
            print(f"{RED}No whale events found matching criteria{RESET}")
            return None

        print(f"{GREEN}Found {len(all_events)} whale events{RESET}")

        # Filter to only market orders for ranking (we want top MARKET orders specifically)
        all_orders = [e for e in all_events if e['event_type'] in ('market_buy', 'market_sell')]

        if not all_orders:
            print(f"{RED}No market orders found in whale events{RESET}")
            return None

        print(f"{GREEN}  → {len(all_orders)} are market orders{RESET}")

        # Calculate statistics
        buy_orders = [o for o in all_orders if o['event_type'] == 'market_buy']
        sell_orders = [o for o in all_orders if o['event_type'] == 'market_sell']

        total_buy_volume = sum(o['usd_value'] for o in buy_orders)
        total_sell_volume = sum(o['usd_value'] for o in sell_orders)

        # Sort orders
        if self.sort_by == 'size':
            all_orders.sort(key=lambda x: x['usd_value'], reverse=True)
        elif self.sort_by == 'distance':
            all_orders.sort(key=lambda x: abs(x['distance_from_mid_pct']), reverse=True)
        elif self.sort_by == 'time':
            all_orders.sort(key=lambda x: x['time'], reverse=True)

        # Get top N orders
        top_orders = all_orders[:self.top_n]

        # OPTIMIZATION: Calculate the full extended time range for all top orders
        context_duration = timedelta(minutes=3)
        min_time = min(order['time'] for order in top_orders) - context_duration
        max_time = max(order['time'] for order in top_orders) + context_duration

        print(f"{CYAN}Fetching all data for extended range: {min_time} to {max_time}...{RESET}")

        # Get ALL events and price data in one query each (much faster than per-order queries)
        all_context_events = self.get_all_whale_events(min_time, max_time)
        all_price_data = self.get_price_data(min_time, max_time)

        print(f"{GREEN}Retrieved {len(all_context_events)} events and {len(all_price_data)} price points{RESET}")

        # Create intervals for each order (like price analysis)
        print(f"{CYAN}Creating intervals for each order...{RESET}")
        intervals = []

        for i, order in enumerate(top_orders, 1):
            order_time = order['time']

            # Define context window (3 minutes before/after = 6 minute total interval)
            interval_start = order_time
            interval_end = order_time
            extended_start = order_time - context_duration
            extended_end = order_time + context_duration

            # Filter events and price data for this order's window (fast in-memory filtering)
            price_data = [p for p in all_price_data if extended_start <= p['time'] <= extended_end]

            whale_events_before = [e for e in all_context_events if extended_start <= e['time'] < interval_start]
            whale_events_during = [order]  # The main order itself
            whale_events_after = [e for e in all_context_events if interval_end < e['time'] <= extended_end]

            # Create interval object (same format as whale_events_analyzer)
            interval = {
                'rank': i,
                'symbol': self.symbol,
                'start_time': interval_start.isoformat(),
                'end_time': interval_end.isoformat(),
                'extended_start': extended_start.isoformat(),
                'extended_end': extended_end.isoformat(),
                'whale_events': [{**order, 'time': order['time'].isoformat(), 'period': 'during'}],
                'whale_events_before': [{**e, 'time': e['time'].isoformat(), 'period': 'before'} for e in whale_events_before if e['time'] != order_time],
                'whale_events_after': [{**e, 'time': e['time'].isoformat(), 'period': 'after'} for e in whale_events_after if e['time'] != order_time],
                'price_data': [{**p, 'time': p['time'].isoformat()} for p in price_data],
                'total_usd_volume': order['usd_value'],
                'buy_volume': order['usd_value'] if order['event_type'] == 'market_buy' else 0,
                'sell_volume': order['usd_value'] if order['event_type'] == 'market_sell' else 0,
                'event_count': 1,
                'order_flow_imbalance': 1.0 if order['event_type'] == 'market_buy' else -1.0,
                'event_type': order['event_type'],
                'price': order['price'],
                'volume': order['volume'],
                'distance_from_mid_pct': order['distance_from_mid_pct']
            }

            intervals.append(interval)

        # Create result in intervals format (like whale_events_analyzer)
        result = {
            'metadata': {
                'symbol': self.symbol,
                'lookback': self.lookback,
                'min_usd': self.min_usd,
                'max_distance': self.max_distance,
                'min_distance': self.min_distance,
                'top_n': self.top_n,
                'sort_by': self.sort_by,
                'analyzer': 'top_market_orders',
                'export_time': datetime.now().isoformat(),
                'total_orders': len(all_orders),
                'buy_count': len(buy_orders),
                'sell_count': len(sell_orders),
                'total_buy_volume': total_buy_volume,
                'total_sell_volume': total_sell_volume,
            },
            'intervals': intervals
        }

        print(f"\n{BOLD}Summary:{RESET}")
        print(f"  {CYAN}Market Buys {RESET}: {len(buy_orders):4d} orders, ${total_buy_volume:,.0f}")
        print(f"  {MAGENTA}Market Sells{RESET}: {len(sell_orders):4d} orders, ${total_sell_volume:,.0f}")
        print(f"  {GREEN}Top {self.top_n} orders selected{RESET}")
        print()

        return result

    def display_terminal(self, result: Dict):
        """Display results in terminal"""
        if not result:
            return

        intervals = result['intervals']
        metadata = result['metadata']

        print(f"{BOLD}{'='*100}{RESET}")
        print(f"{BOLD}TOP {len(intervals)} MARKET ORDERS - {metadata['symbol']}{RESET}")
        print(f"{BOLD}{'='*100}{RESET}\n")

        for interval in intervals:
            order = interval['whale_events'][0]  # The main order
            event_type = order['event_type']
            color = CYAN if event_type == 'market_buy' else MAGENTA
            symbol = '▲' if event_type == 'market_buy' else '▼'

            time_str = datetime.fromisoformat(order['time']).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            distance_color = GREEN if order['distance_from_mid_pct'] >= 0 else RED

            print(f"{BOLD}#{interval['rank']:3d} {color}{symbol} {event_type.upper():13s}{RESET} ${order['usd_value']:12,.0f}")
            print(f"      {DIM}Time:{RESET} {time_str}")
            print(f"      {DIM}Price:{RESET} ${order['price']:.6f}  {DIM}Volume:{RESET} {order['volume']:.4f}")
            print(f"      {DIM}Distance from mid:{RESET} {distance_color}{order['distance_from_mid_pct']:+.4f}%{RESET}")
            print(f"      {DIM}Context:{RESET} {len(interval['whale_events_before'])} before, {len(interval['whale_events_after'])} after")
            print()

    def export_json(self, result: Dict, filepath: str):
        """Export results to JSON file"""
        if not result:
            return

        # Result is already serialized (datetimes converted to ISO strings in analyze())
        with open(filepath, 'w') as f:
            json.dump(result, f, indent=2)

        print(f"{GREEN}Exported to {filepath}{RESET}")

    def close(self):
        """Close InfluxDB client"""
        self.client.close()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Find and rank individual market buy/sell orders by size'
    )

    parser.add_argument('--symbol', type=str, default='SPX_USDT',
                       help='Trading pair symbol (default: SPX_USDT)')
    parser.add_argument('--lookback', type=str, default='1h',
                       help='Time period to analyze (default: 1h)')
    parser.add_argument('--top', type=int, default=50,
                       help='Number of top orders to show (default: 50)')
    parser.add_argument('--min-usd', type=float, default=10000,
                       help='Minimum USD value per order (default: 10000)')
    parser.add_argument('--max-distance', type=float, default=None,
                       help='Maximum distance from mid price in %% (e.g., 1.0 for 1%%)')
    parser.add_argument('--min-distance', type=float, default=None,
                       help='Minimum distance from mid price in %% (e.g., 0.1 for 0.1%%)')
    parser.add_argument('--sort-by', type=str, choices=['size', 'distance', 'time'], default='size',
                       help='Sorting criteria (default: size)')
    parser.add_argument('--output', type=str, choices=['terminal', 'json'], default='terminal',
                       help='Output format (default: terminal)')
    parser.add_argument('--export-path', type=str,
                       help='Path for JSON export (auto-generated if not specified)')

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()

    try:
        analyzer = TopMarketOrdersAnalyzer(
            symbol=args.symbol,
            lookback=args.lookback,
            min_usd=args.min_usd,
            max_distance=args.max_distance,
            min_distance=args.min_distance,
            top_n=args.top,
            sort_by=args.sort_by
        )

        result = analyzer.analyze()

        if not result:
            return

        if args.output == 'terminal':
            analyzer.display_terminal(result)
        elif args.output == 'json':
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)

            if args.export_path:
                export_path = args.export_path
            else:
                filename = f"top_market_orders_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                export_path = os.path.join(data_dir, filename)

            analyzer.export_json(result, export_path)

        analyzer.close()

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user{RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
