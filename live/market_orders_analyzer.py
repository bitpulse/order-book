#!/usr/bin/env python3
"""
Market Orders Analyzer
Finds time intervals with highest MARKET BUY/SELL activity (aggressive whale trading)
Focus: Only market_buy and market_sell events (not limit orders)
"""

import os
import sys
import json
import csv
import argparse
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from collections import defaultdict
from bisect import bisect_left, bisect_right
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


class MarketOrdersAnalyzer:
    """Analyzes MARKET BUY/SELL orders only - aggressive whale trading patterns"""

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
            sort_by: Sorting criteria (volume, imbalance, aggression)
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
        """Remove overlapping intervals to show unique market order clusters"""
        if not intervals:
            return []

        unique_intervals = []

        for interval in intervals:
            is_duplicate = False

            for existing in unique_intervals:
                if (interval['end_time'] >= existing['start_time'] and
                    interval['start_time'] <= existing['end_time']):
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_intervals.append(interval)

        return unique_intervals

    def get_market_orders(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Get ONLY market buy/sell orders for a specific time interval

        Args:
            start_time: Start of interval
            end_time: End of interval

        Returns:
            List of market order dicts (market_buy and market_sell only)
        """
        start_str = start_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        end_str = end_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

        # Query ONLY market orders (filter in Flux for efficiency)
        query = f'''
        from(bucket: "{self.influx_bucket}")
          |> range(start: {start_str}, stop: {end_str})
          |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
          |> filter(fn: (r) => r.symbol == "{self.symbol}")
          |> filter(fn: (r) => r.event_type == "market_buy" or r.event_type == "market_sell")
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

    def find_market_order_clusters(self) -> List[Dict]:
        """
        Find intervals with highest MARKET ORDER activity

        Returns:
            List of dicts with market order metrics and events
        """
        interval_seconds = self._parse_interval_to_seconds(self.interval)

        lookback_time = datetime.now(timezone.utc) - self._parse_lookback_to_timedelta(self.lookback)
        end_time = datetime.now(timezone.utc)

        all_events = self.get_market_orders(lookback_time, end_time)

        if not all_events:
            print(f"{RED}No market orders found for {self.symbol}{RESET}")
            return []

        print(f"{CYAN}Found {len(all_events)} market orders (buy/sell only){RESET}")

        intervals = []
        interval_delta = timedelta(seconds=interval_seconds)

        # Adaptive sliding window
        slide_seconds = max(1, interval_seconds // 10)
        print(f"Using {slide_seconds}s sliding step (interval: {interval_seconds}s)")

        first_event_time = all_events[0]['time']
        last_event_time = all_events[-1]['time']
        current_start = first_event_time

        # Create time list for binary search
        event_times = [e['time'] for e in all_events]

        # Progress tracking
        total_iterations = int((last_event_time - first_event_time).total_seconds() / slide_seconds)
        iteration = 0
        last_progress_print = 0

        while current_start < end_time:
            current_end = current_start + interval_delta

            # Progress indicator
            iteration += 1
            progress = int((iteration / total_iterations) * 100) if total_iterations > 0 else 0
            if progress >= last_progress_print + 10:
                print(f"Progress: {progress}% ({iteration}/{total_iterations} windows)", flush=True)
                last_progress_print = progress

            # Binary search for events
            start_idx = bisect_left(event_times, current_start)
            end_idx = bisect_right(event_times, current_end)

            interval_events = all_events[start_idx:end_idx]

            if interval_events:
                total_usd = sum(e['usd_value'] for e in interval_events)

                if total_usd >= self.min_usd:
                    buy_volume = 0
                    sell_volume = 0
                    buy_count = 0
                    sell_count = 0

                    for event in interval_events:
                        if event['event_type'] == 'market_buy':
                            buy_volume += event['usd_value']
                            buy_count += 1
                        elif event['event_type'] == 'market_sell':
                            sell_volume += event['usd_value']
                            sell_count += 1

                    # Order flow imbalance (-1 to +1)
                    total_flow = buy_volume + sell_volume
                    if total_flow > 0:
                        order_flow_imbalance = (buy_volume - sell_volume) / total_flow
                    else:
                        order_flow_imbalance = 0

                    # Aggression score (always 1.0 since we only track market orders)
                    aggression_score = 1.0

                    intervals.append({
                        'start_time': current_start,
                        'end_time': current_end,
                        'total_usd_volume': total_usd,
                        'event_count': len(interval_events),
                        'buy_volume': buy_volume,
                        'sell_volume': sell_volume,
                        'buy_count': buy_count,
                        'sell_count': sell_count,
                        'order_flow_imbalance': order_flow_imbalance,
                        'aggression_score': aggression_score,
                        'whale_events': interval_events,
                    })

            current_start += timedelta(seconds=slide_seconds)

        # Sort by selected metric
        if self.sort_by == 'volume':
            intervals.sort(key=lambda x: x['total_usd_volume'], reverse=True)
        elif self.sort_by == 'imbalance':
            intervals.sort(key=lambda x: abs(x['order_flow_imbalance']), reverse=True)
        elif self.sort_by == 'aggression':
            # All are 100% aggressive, so sort by volume
            intervals.sort(key=lambda x: x['total_usd_volume'], reverse=True)

        deduplicated = self._deduplicate_intervals(intervals)

        return deduplicated[:self.top_n]

    def analyze(self) -> List[Dict]:
        """Run full analysis"""
        print(f"{CYAN}Analyzing MARKET ORDERS for {self.symbol}...{RESET}")
        print(f"{DIM}Lookback: {self.lookback}, Interval: {self.interval}, Min USD: ${self.min_usd:,.0f}{RESET}\n")

        clusters = self.find_market_order_clusters()

        if not clusters:
            print(f"{YELLOW}No significant market order activity found.{RESET}")
            return []

        print(f"{GREEN}Found {len(clusters)} intervals with significant market order activity{RESET}\n")

        results = []
        for i, cluster in enumerate(clusters, 1):
            interval_duration = cluster['end_time'] - cluster['start_time']

            # Get price data context
            context_multiplier = 3
            extended_start = cluster['start_time'] - interval_duration * context_multiplier
            extended_end = cluster['end_time'] + interval_duration * context_multiplier
            price_data = self.get_price_data(extended_start, extended_end)

            # Get market orders from before and after for context
            whale_events_before = self.get_market_orders(extended_start, cluster['start_time'])
            whale_events_after = self.get_market_orders(cluster['end_time'], extended_end)

            results.append({
                'rank': i,
                'symbol': self.symbol,
                'start_time': cluster['start_time'],
                'end_time': cluster['end_time'],
                'total_usd_volume': cluster['total_usd_volume'],
                'event_count': cluster['event_count'],
                'buy_volume': cluster['buy_volume'],
                'sell_volume': cluster['sell_volume'],
                'buy_count': cluster['buy_count'],
                'sell_count': cluster['sell_count'],
                'order_flow_imbalance': cluster['order_flow_imbalance'],
                'aggression_score': cluster['aggression_score'],
                'whale_events': cluster['whale_events'],
                'whale_events_before': whale_events_before,
                'whale_events_after': whale_events_after,
                'price_data': price_data,
                'extended_start': extended_start,
                'extended_end': extended_end
            })

        return results

    def display_terminal(self, results: List[Dict]):
        """Display results in terminal"""
        for result in results:
            imbalance = result['order_flow_imbalance']
            imbalance_color = GREEN if imbalance > 0 else RED if imbalance < 0 else YELLOW
            pressure = "BULLISH" if imbalance > 0.1 else "BEARISH" if imbalance < -0.1 else "NEUTRAL"

            print(f"{BOLD}{'='*80}{RESET}")
            print(f"{BOLD}Rank #{result['rank']}: ${result['total_usd_volume']:,.0f} market orders "
                  f"({result['event_count']} events, {imbalance_color}{imbalance:+.0%} {pressure}{RESET}){RESET}")
            print(f"{DIM}Time: {result['start_time']} → {result['end_time']}{RESET}")

            print(f"\n{BOLD}Market Order Breakdown:{RESET}")
            print(f"  {CYAN}Market Buys {RESET}: {result['buy_count']:3d} orders, ${result['buy_volume']:,.0f}")
            print(f"  {MAGENTA}Market Sells{RESET}: {result['sell_count']:3d} orders, ${result['sell_volume']:,.0f}")
            print(f"  {imbalance_color}Net Flow    {RESET}: ${result['buy_volume'] - result['sell_volume']:+,.0f}")
            print(f"  {imbalance_color}Imbalance   {RESET}: {imbalance:+.2f} ({pressure})")
            print()

    def export_json(self, results: List[Dict], filepath: str):
        """Export results to JSON file"""
        intervals = []
        for result in results:
            export_result = result.copy()
            export_result['start_time'] = result['start_time'].isoformat()
            export_result['end_time'] = result['end_time'].isoformat()
            export_result['extended_start'] = result['extended_start'].isoformat()
            export_result['extended_end'] = result['extended_end'].isoformat()

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

            export_result['price_data'] = [
                {**point, 'time': point['time'].isoformat()}
                for point in result['price_data']
            ]

            intervals.append(export_result)

        export_data = {
            'analysis': {
                'symbol': self.symbol,
                'lookback': self.lookback,
                'interval': self.interval,
                'min_usd': self.min_usd,
                'sort_by': self.sort_by,
                'analyzer': 'market_orders',  # Distinguish from general whale_activity
                'timestamp': datetime.now().isoformat()
            },
            'intervals': intervals
        }

        # Save to MongoDB (primary storage)
        analysis_id = None
        save_to_file = False
        try:
            # Import here to avoid circular dependencies
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from src.mongodb_storage import get_mongodb_storage

            mongo = get_mongodb_storage()
            if mongo:
                metadata = {
                    'filename': os.path.basename(filepath) if filepath else f'market_orders_{self.symbol}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                    'top_n': self.top_n
                }
                analysis_id = mongo.save_analysis('market_orders_intervals', export_data, metadata)
                print(f"{GREEN}✓ Saved to MongoDB with ID: {analysis_id}{RESET}")
                mongo.close()
            else:
                print(f"{YELLOW}Warning: MongoDB not available, saving to file instead{RESET}")
                save_to_file = True
        except Exception as e:
            print(f"{YELLOW}Warning: Could not save to MongoDB: {e}{RESET}")
            save_to_file = True

        # Optionally save to JSON file (backup or if MongoDB failed)
        if save_to_file and filepath:
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2)
            print(f"{GREEN}✓ Backup saved to {filepath}{RESET}")

        return analysis_id

    def close(self):
        """Close InfluxDB client"""
        self.client.close()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Analyze MARKET BUY/SELL orders only - aggressive whale trading'
    )

    parser.add_argument('--symbol', type=str, default='SPX_USDT',
                       help='Trading pair symbol (default: SPX_USDT)')
    parser.add_argument('--lookback', type=str, default='1h',
                       help='Time period to analyze (default: 1h)')
    parser.add_argument('--interval', type=str, default='30s',
                       help='Window size for aggregation (default: 30s)')
    parser.add_argument('--top', type=int, default=10,
                       help='Number of top intervals to show (default: 10)')
    parser.add_argument('--min-usd', type=float, default=10000,
                       help='Minimum total USD volume per interval (default: 10000)')
    parser.add_argument('--sort-by', type=str, choices=['volume', 'imbalance'], default='volume',
                       help='Sorting criteria (default: volume)')
    parser.add_argument('--output', type=str, choices=['terminal', 'json'], default='terminal',
                       help='Output format (default: terminal)')
    parser.add_argument('--export-path', type=str,
                       help='Path for JSON export (auto-generated if not specified)')

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_args()

    try:
        analyzer = MarketOrdersAnalyzer(
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
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
            os.makedirs(data_dir, exist_ok=True)

            if args.export_path:
                export_path = args.export_path
            else:
                filename = f"market_orders_{args.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                export_path = os.path.join(data_dir, filename)

            analyzer.export_json(results, export_path)

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
