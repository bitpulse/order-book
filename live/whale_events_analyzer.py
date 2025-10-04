#!/usr/bin/env python3
"""
Whale Events Analyzer
Finds time intervals with highest whale activity and analyzes order flow patterns
"""

import os
import sys
import json
import csv
import argparse
from datetime import datetime, timedelta, timezone
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


class WhaleEventsAnalyzer:
    """Analyzes whale order book events and identifies significant activity patterns"""

    def __init__(self, symbol: str, lookback: str, interval: str,
                 min_usd: float = 10000, top_n: int = 10, sort_by: str = 'volume'):
        """
        Initialize the analyzer

        Args:
            symbol: Trading pair (e.g., BTC_USDT)
            lookback: Time period to analyze (e.g., 1h, 24h, 7d)
            interval: Window size for aggregation (e.g., 10s, 30s, 1m, 5m)
            min_usd: Minimum total USD volume per interval
            top_n: Number of top intervals to return
            sort_by: Sorting criteria (volume, imbalance, events)
        """
        self.symbol = symbol
        self.lookback = lookback
        self.interval = interval
        self.min_usd = min_usd
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

    def _deduplicate_intervals(self, intervals: List[Dict]) -> List[Dict]:
        """
        Remove overlapping intervals to show unique whale activity clusters.

        For each interval, check if it overlaps with any already-selected interval.
        If it overlaps, skip it (it's capturing the same activity).
        If it doesn't overlap, it's a unique cluster - keep it.

        Args:
            intervals: List of interval dicts sorted by metric (largest first)

        Returns:
            List of non-overlapping intervals (unique clusters only)
        """
        if not intervals:
            return []

        unique_intervals = []

        for interval in intervals:
            # Check if this interval overlaps with any already-selected interval
            is_duplicate = False

            for existing in unique_intervals:
                # Two intervals overlap if:
                # interval.end >= existing.start AND interval.start <= existing.end
                if (interval['end_time'] >= existing['start_time'] and
                    interval['start_time'] <= existing['end_time']):
                    is_duplicate = True
                    break

            # Only keep non-overlapping (unique) intervals
            if not is_duplicate:
                unique_intervals.append(interval)

        return unique_intervals

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
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                })

        # Sort by time
        events.sort(key=lambda x: x['time'])
        return events

    def get_price_data(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Get price data for context

        Args:
            start_time: Start of interval
            end_time: End of interval

        Returns:
            List of price point dicts
        """
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

        # Sort by time
        price_points.sort(key=lambda x: x['time'])
        return price_points

    def find_whale_activity_clusters(self) -> List[Dict]:
        """
        Find intervals with highest whale activity

        Returns:
            List of dicts with whale activity metrics and events
        """
        interval_seconds = self._parse_interval_to_seconds(self.interval)

        # Get all whale events for the lookback period
        lookback_time = datetime.now(timezone.utc) - self._parse_lookback_to_timedelta(self.lookback)
        end_time = datetime.now(timezone.utc)

        all_events = self.get_whale_events(lookback_time, end_time)

        if not all_events:
            print(f"{RED}No whale events found for {self.symbol}{RESET}")
            return []

        # Aggregate events into intervals
        intervals = []
        interval_delta = timedelta(seconds=interval_seconds)

        # Use 1-second sliding window for high resolution
        slide_seconds = 1
        start_idx = 0

        # Get first event time
        current_start = all_events[0]['time']

        while current_start < end_time:
            current_end = current_start + interval_delta

            # Find events in this interval
            interval_events = []
            for event in all_events:
                if current_start <= event['time'] < current_end:
                    interval_events.append(event)

            if interval_events:
                # Calculate metrics
                total_usd = sum(e['usd_value'] for e in interval_events)

                if total_usd >= self.min_usd:
                    # Event type summary
                    event_summary = defaultdict(lambda: {'count': 0, 'total_usd': 0})
                    buy_volume = 0
                    sell_volume = 0

                    for event in interval_events:
                        etype = event['event_type']
                        event_summary[etype]['count'] += 1
                        event_summary[etype]['total_usd'] += event['usd_value']

                        # Track buy/sell volume
                        if event['side'] == 'bid' or event['event_type'] == 'market_buy':
                            buy_volume += event['usd_value']
                        elif event['side'] == 'ask' or event['event_type'] == 'market_sell':
                            sell_volume += event['usd_value']

                    # Calculate order flow imbalance (-1 to +1, positive = bullish)
                    total_flow = buy_volume + sell_volume
                    if total_flow > 0:
                        order_flow_imbalance = (buy_volume - sell_volume) / total_flow
                    else:
                        order_flow_imbalance = 0

                    # Calculate aggression score (ratio of market orders to total)
                    market_orders = event_summary.get('market_buy', {'total_usd': 0})['total_usd'] + \
                                  event_summary.get('market_sell', {'total_usd': 0})['total_usd']
                    aggression_score = market_orders / total_usd if total_usd > 0 else 0

                    intervals.append({
                        'start_time': current_start,
                        'end_time': current_end,
                        'total_usd_volume': total_usd,
                        'event_count': len(interval_events),
                        'buy_volume': buy_volume,
                        'sell_volume': sell_volume,
                        'order_flow_imbalance': order_flow_imbalance,
                        'aggression_score': aggression_score,
                        'event_summary': dict(event_summary),
                        'whale_events': interval_events,
                    })

            # Slide window forward
            current_start += timedelta(seconds=slide_seconds)

        # Sort by selected metric
        if self.sort_by == 'volume':
            intervals.sort(key=lambda x: x['total_usd_volume'], reverse=True)
        elif self.sort_by == 'imbalance':
            intervals.sort(key=lambda x: abs(x['order_flow_imbalance']), reverse=True)
        elif self.sort_by == 'events':
            intervals.sort(key=lambda x: x['event_count'], reverse=True)

        # De-duplicate overlapping intervals
        deduplicated = self._deduplicate_intervals(intervals)

        # Return top N unique intervals
        return deduplicated[:self.top_n]

    def analyze(self) -> List[Dict]:
        """
        Run full analysis: find whale activity clusters and add context

        Returns:
            List of dicts with whale activity info, events, and price context
        """
        print(f"{CYAN}Analyzing whale activity for {self.symbol}...{RESET}")
        print(f"{DIM}Lookback: {self.lookback}, Interval: {self.interval}, Min USD: ${self.min_usd:,.0f}{RESET}\n")

        clusters = self.find_whale_activity_clusters()

        if not clusters:
            print(f"{YELLOW}No significant whale activity found.{RESET}")
            return []

        print(f"{GREEN}Found {len(clusters)} intervals with significant whale activity{RESET}\n")

        results = []
        for i, cluster in enumerate(clusters, 1):
            # Calculate extended time window for context (before and after)
            interval_duration = cluster['end_time'] - cluster['start_time']

            # Get price data: before, during, and after the interval
            context_multiplier = 3
            extended_start = cluster['start_time'] - interval_duration * context_multiplier
            extended_end = cluster['end_time'] + interval_duration * context_multiplier
            price_data = self.get_price_data(extended_start, extended_end)

            # Get whale events from before and after for context
            whale_events_before = self.get_whale_events(extended_start, cluster['start_time'])
            whale_events_after = self.get_whale_events(cluster['end_time'], extended_end)

            results.append({
                'rank': i,
                'symbol': self.symbol,
                'start_time': cluster['start_time'],
                'end_time': cluster['end_time'],
                'total_usd_volume': cluster['total_usd_volume'],
                'event_count': cluster['event_count'],
                'buy_volume': cluster['buy_volume'],
                'sell_volume': cluster['sell_volume'],
                'order_flow_imbalance': cluster['order_flow_imbalance'],
                'aggression_score': cluster['aggression_score'],
                'event_summary': cluster['event_summary'],
                'whale_events': cluster['whale_events'],
                'whale_events_before': whale_events_before,
                'whale_events_after': whale_events_after,
                'price_data': price_data,
                'extended_start': extended_start,
                'extended_end': extended_end
            })

        return results

    def _get_event_color(self, event_type: str, side: str = '') -> str:
        """Get color for event type based on market impact"""
        # Definitive market events - bright colors
        if event_type == 'market_buy':
            return CYAN
        elif event_type == 'market_sell':
            return MAGENTA
        # Volume changes - muted colors
        elif event_type == 'increase':
            return f"{DIM}{GREEN}" if side == 'bid' else f"{DIM}{RED}"
        elif event_type == 'decrease':
            return f"{DIM}{RED}" if side == 'bid' else f"{DIM}{GREEN}"
        # New orders - bright colors
        elif 'bid' in event_type or 'buy' in event_type:
            return GREEN
        elif 'ask' in event_type or 'sell' in event_type:
            return RED
        else:
            return WHITE

    def display_terminal(self, results: List[Dict]):
        """Display results in terminal with color coding"""
        for result in results:
            imbalance = result['order_flow_imbalance']
            imbalance_color = GREEN if imbalance > 0 else RED if imbalance < 0 else YELLOW
            pressure = "BULLISH" if imbalance > 0.1 else "BEARISH" if imbalance < -0.1 else "NEUTRAL"

            print(f"{BOLD}{'='*80}{RESET}")
            print(f"{BOLD}Rank #{result['rank']}: ${result['total_usd_volume']:,.0f} whale activity "
                  f"({result['event_count']} events, {imbalance_color}{imbalance:+.0%} {pressure}{RESET}){RESET}")
            print(f"{DIM}Time: {result['start_time']} → {result['end_time']}{RESET}")
            print(f"{DIM}Order Flow Imbalance: {imbalance_color}{imbalance:+.2f}{RESET} ({pressure})")
            print(f"{DIM}Aggression Score: {result['aggression_score']:.2f}{RESET}")

            # Event summary
            if result['event_summary']:
                print(f"\n{BOLD}Whale Activity Summary:{RESET}")
                for event_type, stats in sorted(result['event_summary'].items(),
                                               key=lambda x: x[1]['total_usd'],
                                               reverse=True):
                    event_color = self._get_event_color(event_type)
                    print(f"  {event_color}{event_type:15s}{RESET}: {stats['count']:3d} events, "
                          f"${stats['total_usd']:,.0f} total")

            # Buy/Sell breakdown
            print(f"\n{BOLD}Volume Breakdown:{RESET}")
            print(f"  {GREEN}Buy Volume {RESET}: ${result['buy_volume']:,.0f}")
            print(f"  {RED}Sell Volume{RESET}: ${result['sell_volume']:,.0f}")
            print(f"  {imbalance_color}Net Flow   {RESET}: ${result['buy_volume'] - result['sell_volume']:+,.0f}")

            # Detailed timeline
            if result['whale_events']:
                print(f"\n{BOLD}Event Timeline ({len(result['whale_events'])} events):{RESET}")
                for event in result['whale_events'][:20]:  # Show first 20
                    event_color = self._get_event_color(event['event_type'], event.get('side', ''))
                    time_str = event['time'].strftime('%H:%M:%S.%f')[:-3]
                    distance_str = f"{event['distance_from_mid_pct']:+.3f}%" if event.get('distance_from_mid_pct') else 'N/A'
                    print(f"  {DIM}{time_str}{RESET} {event_color}{event['event_type']:15s}{RESET} "
                          f"${event['price']:.2f} × {event['volume']:.4f} "
                          f"= ${event['usd_value']:,.0f} "
                          f"{DIM}({distance_str}){RESET}")

                if len(result['whale_events']) > 20:
                    print(f"  {DIM}... and {len(result['whale_events']) - 20} more events{RESET}")
            else:
                print(f"\n{DIM}No whale events in this interval{RESET}")

            print()

    def export_json(self, results: List[Dict], filepath: str):
        """Export results to JSON file"""
        # Convert datetime objects to strings
        intervals = []
        for result in results:
            export_result = result.copy()
            export_result['start_time'] = result['start_time'].isoformat()
            export_result['end_time'] = result['end_time'].isoformat()
            export_result['extended_start'] = result['extended_start'].isoformat()
            export_result['extended_end'] = result['extended_end'].isoformat()

            # Convert whale event times
            export_result['whale_events'] = [
                {**event, 'time': event['time'].isoformat()}
                for event in result['whale_events']
            ]

            export_result['whale_events_before'] = [
                {**event, 'time': event['time'].isoformat()}
                for event in result['whale_events_before']
            ]

            export_result['whale_events_after'] = [
                {**event, 'time': event['time'].isoformat()}
                for event in result['whale_events_after']
            ]

            # Convert price data times
            export_result['price_data'] = [
                {**point, 'time': point['time'].isoformat()}
                for point in result['price_data']
            ]

            intervals.append(export_result)

        # Create export data with metadata
        export_data = {
            'metadata': {
                'symbol': self.symbol,
                'lookback': self.lookback,
                'interval': self.interval,
                'min_usd': self.min_usd,
                'sort_by': self.sort_by,
                'export_time': datetime.now().isoformat()
            },
            'intervals': intervals
        }

        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)

        print(f"{GREEN}Exported to {filepath}{RESET}")

    def export_csv(self, results: List[Dict], filepath: str):
        """Export results to CSV file"""
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'Rank', 'Start Time', 'End Time', 'Total USD Volume', 'Event Count',
                'Buy Volume', 'Sell Volume', 'Order Flow Imbalance', 'Aggression Score',
                'Event Types'
            ])

            # Data
            for result in results:
                event_types = ', '.join(result['event_summary'].keys())

                writer.writerow([
                    result['rank'],
                    result['start_time'].isoformat(),
                    result['end_time'].isoformat(),
                    result['total_usd_volume'],
                    result['event_count'],
                    result['buy_volume'],
                    result['sell_volume'],
                    result['order_flow_imbalance'],
                    result['aggression_score'],
                    event_types
                ])

        print(f"{GREEN}Exported to {filepath}{RESET}")

    def close(self):
        """Close InfluxDB client"""
        self.client.close()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze whale order book events and identify significant activity patterns'
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
        default='3h',
        help='Time period to analyze (e.g., 1h, 3h, 6h, 24h) (default: 3h)'
    )

    parser.add_argument(
        '--interval',
        type=str,
        default='30s',
        help='Window size for aggregation (e.g., 10s, 30s, 1m, 5m) (default: 30s)'
    )

    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Number of top intervals to show (default: 10)'
    )

    parser.add_argument(
        '--min-usd',
        type=float,
        default=10000,
        help='Minimum total USD volume per interval (default: 10000)'
    )

    parser.add_argument(
        '--sort-by',
        type=str,
        choices=['volume', 'imbalance', 'events'],
        default='volume',
        help='Sorting criteria (default: volume)'
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
        analyzer = WhaleEventsAnalyzer(
            symbol=args.symbol,
            lookback=args.lookback,
            interval=args.interval,
            min_usd=args.min_usd,
            top_n=args.top,
            sort_by=args.sort_by
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
                filename = f"whale_activity_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                export_path = os.path.join(data_dir, filename)

            analyzer.export_json(results, export_path)
        elif args.output == 'csv':
            # Create data directory if it doesn't exist
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)

            if args.export_path:
                export_path = args.export_path
            else:
                filename = f"whale_activity_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
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
