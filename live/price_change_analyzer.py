#!/usr/bin/env python3
"""
Price Change Analyzer with Whale Activity Correlation
Finds time intervals with largest price movements and displays whale activity during those periods
"""

import os
import sys
import json
import csv
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from collections import defaultdict
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


class PriceChangeAnalyzer:
    """Analyzes price changes and correlates with whale activity"""

    def __init__(self, symbol: str, lookback: str, interval: str,
                 min_change: float = 0.1, top_n: int = 10):
        """
        Initialize the analyzer

        Args:
            symbol: Trading pair (e.g., BTC_USDT)
            lookback: Time period to analyze (e.g., 1h, 24h, 7d)
            interval: Window size for price changes (e.g., 1s, 5s, 1m, 5m)
            min_change: Minimum price change % to consider
            top_n: Number of top intervals to return
        """
        self.symbol = symbol
        self.lookback = lookback
        self.interval = interval
        self.min_change = min_change
        self.top_n = top_n

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

    def _parse_interval_to_seconds(self, interval: str) -> int:
        """Convert interval string to seconds"""
        unit = interval[-1]
        value = int(interval[:-1])

        if unit == 's':
            return value
        elif unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        else:
            raise ValueError(f"Invalid interval unit: {unit}. Use s, m, or h")

    def find_price_changes(self) -> List[Dict]:
        """
        Find intervals with largest price changes

        Returns:
            List of dicts with: start_time, end_time, start_price, end_price, change_pct
        """
        interval_seconds = self._parse_interval_to_seconds(self.interval)

        # Query to get price data and calculate changes over sliding windows
        # Using aggregateWindow to get first and last price in each window
        query = f'''
        import "timezone"

        data = from(bucket: "{self.influx_bucket}")
          |> range(start: -{self.lookback})
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{self.symbol}")
          |> filter(fn: (r) => r._field == "mid_price")

        first = data
          |> aggregateWindow(every: {interval_seconds}s, fn: first, createEmpty: false)
          |> set(key: "_field", value: "start_price")

        last = data
          |> aggregateWindow(every: {interval_seconds}s, fn: last, createEmpty: false)
          |> set(key: "_field", value: "end_price")

        union(tables: [first, last])
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        result = self.query_api.query(query)

        price_changes = []
        for table in result:
            for record in table.records:
                start_price = record.values.get('start_price')
                end_price = record.values.get('end_price')
                timestamp = record.get_time()

                if start_price and end_price and start_price > 0:
                    change_pct = ((end_price - start_price) / start_price) * 100

                    if abs(change_pct) >= self.min_change:
                        # Calculate window boundaries
                        start_time = timestamp
                        end_time = timestamp + timedelta(seconds=interval_seconds)

                        price_changes.append({
                            'start_time': start_time,
                            'end_time': end_time,
                            'start_price': start_price,
                            'end_price': end_price,
                            'change_pct': change_pct,
                            'change_abs': abs(change_pct)
                        })

        # Sort by absolute change and return top N
        price_changes.sort(key=lambda x: x['change_abs'], reverse=True)
        return price_changes[:self.top_n]

    def get_whale_events(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Get whale events for a specific time interval

        Args:
            start_time: Start of interval
            end_time: End of interval

        Returns:
            List of whale event dicts
        """
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        query = f'''
        from(bucket: "{self.influx_bucket}")
          |> range(start: {start_str}, stop: {end_str})
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{self.symbol}")
          |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''

        result = self.query_api.query(query)

        events = []
        for table in result:
            for record in table.records:
                events.append({
                    'time': record.get_time(),
                    'event_type': record.values.get('event_type', 'unknown'),
                    'side': record.values.get('side', 'unknown'),
                    'price': record.values.get('price', 0),
                    'volume': record.values.get('volume', 0),
                    'usd_value': record.values.get('usd_value', 0),
                    'distance_from_mid_pct': record.values.get('distance_from_mid_pct', 0),
                })

        # Sort by time
        events.sort(key=lambda x: x['time'])
        return events

    def analyze(self) -> List[Dict]:
        """
        Run full analysis: find price changes and correlate with whale events

        Returns:
            List of dicts with price change info and whale events
        """
        print(f"{CYAN}Analyzing price changes for {self.symbol}...{RESET}")
        print(f"{DIM}Lookback: {self.lookback}, Interval: {self.interval}, Min change: {self.min_change}%{RESET}\n")

        price_changes = self.find_price_changes()

        if not price_changes:
            print(f"{YELLOW}No significant price changes found.{RESET}")
            return []

        print(f"{GREEN}Found {len(price_changes)} intervals with significant price changes{RESET}\n")

        results = []
        for i, change in enumerate(price_changes, 1):
            whale_events = self.get_whale_events(change['start_time'], change['end_time'])

            # Aggregate events by type
            event_summary = defaultdict(lambda: {'count': 0, 'total_usd': 0})
            for event in whale_events:
                etype = event['event_type']
                event_summary[etype]['count'] += 1
                event_summary[etype]['total_usd'] += event['usd_value']

            results.append({
                'rank': i,
                'start_time': change['start_time'],
                'end_time': change['end_time'],
                'start_price': change['start_price'],
                'end_price': change['end_price'],
                'change_pct': change['change_pct'],
                'whale_events': whale_events,
                'event_summary': dict(event_summary)
            })

        return results

    def display_terminal(self, results: List[Dict]):
        """Display results in terminal with color coding"""
        for result in results:
            change_pct = result['change_pct']
            color = GREEN if change_pct > 0 else RED

            print(f"{BOLD}{'='*80}{RESET}")
            print(f"{BOLD}Rank #{result['rank']}: {color}{change_pct:+.3f}%{RESET} price change{RESET}")
            print(f"{DIM}Time: {result['start_time']} → {result['end_time']}{RESET}")
            print(f"{DIM}Price: ${result['start_price']:.2f} → ${result['end_price']:.2f}{RESET}")

            # Event summary
            if result['event_summary']:
                print(f"\n{BOLD}Whale Activity Summary:{RESET}")
                for event_type, stats in result['event_summary'].items():
                    event_color = self._get_event_color(event_type)
                    print(f"  {event_color}{event_type:15s}{RESET}: {stats['count']:3d} events, "
                          f"${stats['total_usd']:,.0f} total")

            # Detailed timeline
            if result['whale_events']:
                print(f"\n{BOLD}Event Timeline ({len(result['whale_events'])} events):{RESET}")
                for event in result['whale_events'][:20]:  # Show first 20
                    event_color = self._get_event_color(event['event_type'])
                    time_str = event['time'].strftime('%H:%M:%S.%f')[:-3]
                    print(f"  {DIM}{time_str}{RESET} {event_color}{event['event_type']:15s}{RESET} "
                          f"${event['price']:.2f} × {event['volume']:.4f} "
                          f"= ${event['usd_value']:,.0f}")

                if len(result['whale_events']) > 20:
                    print(f"  {DIM}... and {len(result['whale_events']) - 20} more events{RESET}")
            else:
                print(f"\n{DIM}No whale events during this interval{RESET}")

            print()

    def _get_event_color(self, event_type: str) -> str:
        """Get color for event type"""
        if 'bid' in event_type or 'buy' in event_type:
            return GREEN
        elif 'ask' in event_type or 'sell' in event_type:
            return RED
        elif 'increase' in event_type:
            return CYAN
        elif 'decrease' in event_type:
            return MAGENTA
        else:
            return WHITE

    def export_json(self, results: List[Dict], filepath: str):
        """Export results to JSON file"""
        # Convert datetime objects to strings
        export_data = []
        for result in results:
            export_result = result.copy()
            export_result['start_time'] = result['start_time'].isoformat()
            export_result['end_time'] = result['end_time'].isoformat()

            # Convert whale event times
            export_result['whale_events'] = [
                {**event, 'time': event['time'].isoformat()}
                for event in result['whale_events']
            ]

            export_data.append(export_result)

        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)

        print(f"{GREEN}Exported to {filepath}{RESET}")

    def export_csv(self, results: List[Dict], filepath: str):
        """Export results to CSV file"""
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'Rank', 'Start Time', 'End Time', 'Start Price', 'End Price',
                'Change %', 'Event Count', 'Event Types', 'Total USD Volume'
            ])

            # Data
            for result in results:
                event_types = ', '.join(result['event_summary'].keys())
                total_usd = sum(s['total_usd'] for s in result['event_summary'].values())

                writer.writerow([
                    result['rank'],
                    result['start_time'].isoformat(),
                    result['end_time'].isoformat(),
                    result['start_price'],
                    result['end_price'],
                    result['change_pct'],
                    len(result['whale_events']),
                    event_types,
                    total_usd
                ])

        print(f"{GREEN}Exported to {filepath}{RESET}")

    def close(self):
        """Close InfluxDB client"""
        self.client.close()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze price changes and correlate with whale activity'
    )

    parser.add_argument(
        '--symbol',
        type=str,
        default='BTC_USDT',
        help='Trading pair symbol (default: BTC_USDT)'
    )

    parser.add_argument(
        '--lookback',
        type=str,
        default='24h',
        help='Time period to analyze (e.g., 1h, 6h, 24h, 7d) (default: 24h)'
    )

    parser.add_argument(
        '--interval',
        type=str,
        default='1m',
        help='Window size for price changes (e.g., 1s, 5s, 10s, 30s, 1m, 5m, 15m, 30m, 1h) (default: 1m)'
    )

    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Number of top intervals to show (default: 10)'
    )

    parser.add_argument(
        '--min-change',
        type=float,
        default=0.1,
        help='Minimum price change %% to consider (default: 0.1)'
    )

    parser.add_argument(
        '--output',
        type=str,
        choices=['terminal', 'json', 'csv'],
        default='terminal',
        help='Output format (default: terminal)'
    )

    parser.add_argument(
        '--export-path',
        type=str,
        help='Path for JSON/CSV export (auto-generated if not specified)'
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()

    try:
        analyzer = PriceChangeAnalyzer(
            symbol=args.symbol,
            lookback=args.lookback,
            interval=args.interval,
            min_change=args.min_change,
            top_n=args.top
        )

        results = analyzer.analyze()

        if not results:
            return

        if args.output == 'terminal':
            analyzer.display_terminal(results)
        elif args.output == 'json':
            # Create data directory if it doesn't exist
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)

            if args.export_path:
                export_path = args.export_path
            else:
                filename = f"price_changes_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                export_path = os.path.join(data_dir, filename)

            analyzer.export_json(results, export_path)
        elif args.output == 'csv':
            # Create data directory if it doesn't exist
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)

            if args.export_path:
                export_path = args.export_path
            else:
                filename = f"price_changes_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                export_path = os.path.join(data_dir, filename)

            analyzer.export_csv(results, export_path)

        analyzer.close()

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted by user{RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}")
        sys.exit(1)


if __name__ == '__main__':
    main()
