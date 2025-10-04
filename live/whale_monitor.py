#!/usr/bin/env python3
"""
Whale Event Monitor
Shows top individual whale events ranked by USD value - no interval aggregation
"""

import os
import sys
import json
import csv
import argparse
from datetime import datetime, timedelta, timezone
from typing import List, Dict
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


class WhaleMonitor:
    """Monitor and rank individual whale events by size"""

    def __init__(self, symbol: str, lookback: str, min_usd: float = 5000,
                 top_n: int = 50, max_distance: float = None):
        """
        Initialize the whale monitor

        Args:
            symbol: Trading pair (e.g., BTC_USDT)
            lookback: Time period to analyze (e.g., 1h, 3h, 24h)
            min_usd: Minimum USD value for whale events
            top_n: Number of top events to return per category
            max_distance: Maximum distance from mid price as percentage (e.g., 5.0 = 5%)
        """
        self.symbol = symbol
        self.lookback = lookback
        self.min_usd = min_usd
        self.top_n = top_n
        self.max_distance = max_distance

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

    def get_whale_events(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get all whale events for time period"""
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
                usd_value = record.values.get('usd_value', 0)
                distance_from_mid_pct = record.values.get('distance_from_mid_pct', 0)

                # Filter by minimum USD
                if usd_value < self.min_usd:
                    continue

                # Filter by maximum distance from mid price
                if self.max_distance is not None and abs(distance_from_mid_pct) > self.max_distance:
                    continue

                events.append({
                    'time': record.get_time(),
                    'event_type': record.values.get('event_type', 'unknown'),
                    'side': record.values.get('side', 'unknown'),
                    'price': record.values.get('price', 0),
                    'volume': record.values.get('volume', 0),
                    'usd_value': usd_value,
                    'distance_from_mid_pct': distance_from_mid_pct,
                    'mid_price': record.values.get('mid_price', 0),
                    'best_bid': record.values.get('best_bid', 0),
                    'best_ask': record.values.get('best_ask', 0),
                })

        return events

    def get_price_data(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Get price data for chart context"""
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

    def categorize_events(self, events: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize events by type and rank by USD value"""
        categories = {
            'market_buy': [],
            'market_sell': [],
            'bid_increase': [],
            'ask_increase': [],
            'bid_decrease': [],
            'ask_decrease': [],
            'new_bid': [],
            'new_ask': [],
            'other': []
        }

        for event in events:
            etype = event['event_type']
            side = event['side']

            if etype == 'market_buy':
                categories['market_buy'].append(event)
            elif etype == 'market_sell':
                categories['market_sell'].append(event)
            elif etype == 'increase' and side == 'bid':
                categories['bid_increase'].append(event)
            elif etype == 'increase' and side == 'ask':
                categories['ask_increase'].append(event)
            elif etype == 'decrease' and side == 'bid':
                categories['bid_decrease'].append(event)
            elif etype == 'decrease' and side == 'ask':
                categories['ask_decrease'].append(event)
            elif etype == 'new_bid' or (etype.startswith('new') and side == 'bid'):
                categories['new_bid'].append(event)
            elif etype == 'new_ask' or (etype.startswith('new') and side == 'ask'):
                categories['new_ask'].append(event)
            else:
                categories['other'].append(event)

        # Sort each category by USD value (largest first)
        for category in categories:
            categories[category].sort(key=lambda x: x['usd_value'], reverse=True)

        return categories

    def get_price_around_event(self, event_time: datetime, before_minutes: int = 5, after_minutes: int = 5) -> List[Dict]:
        """Get price data before and after a specific event"""
        start_time = event_time - timedelta(minutes=before_minutes)
        end_time = event_time + timedelta(minutes=after_minutes)
        return self.get_price_data(start_time, end_time)
    def analyze(self) -> Dict:
        """
        Run full analysis: get whale events and categorize by type

        Returns:
            Dict with categorized events and summary stats
        """
        print(f"{CYAN}Monitoring whale events for {self.symbol}...{RESET}")
        filters = f"Lookback: {self.lookback}, Min USD: ${self.min_usd:,.0f}"
        if self.max_distance is not None:
            filters += f", Max Distance: {self.max_distance}%"
        print(f"{DIM}{filters}{RESET}\n")

        # Get all whale events and price data
        lookback_time = datetime.now(timezone.utc) - self._parse_lookback_to_timedelta(self.lookback)
        end_time = datetime.now(timezone.utc)

        all_events = self.get_whale_events(lookback_time, end_time)
        price_data = self.get_price_data(lookback_time, end_time)

        if not all_events:
            print(f"{YELLOW}No whale events found for {self.symbol}{RESET}")
            return {
                'symbol': self.symbol,
                'lookback': self.lookback,
                'min_usd': self.min_usd,
                'start_time': lookback_time.isoformat(),
                'end_time': end_time.isoformat(),
                'total_events': 0,
                'categories': {},
                'summary': {}
            }

        # Categorize events
        categories = self.categorize_events(all_events)

        # Calculate summary stats
        summary = {
            'total_events': len(all_events),
            'total_market_buy_usd': sum(e['usd_value'] for e in categories['market_buy']),
            'total_market_sell_usd': sum(e['usd_value'] for e in categories['market_sell']),
            'net_market_flow_usd': sum(e['usd_value'] for e in categories['market_buy']) -
                                   sum(e['usd_value'] for e in categories['market_sell']),
            'total_bid_increase_usd': sum(e['usd_value'] for e in categories['bid_increase']),
            'total_ask_increase_usd': sum(e['usd_value'] for e in categories['ask_increase']),
            'total_bid_decrease_usd': sum(e['usd_value'] for e in categories['bid_decrease']),
            'total_ask_decrease_usd': sum(e['usd_value'] for e in categories['ask_decrease']),
            'largest_event': max(all_events, key=lambda x: x['usd_value']) if all_events else None,
            'market_buy_count': len(categories['market_buy']),
            'market_sell_count': len(categories['market_sell']),
            'bid_events_count': len(categories['bid_increase']) + len(categories['bid_decrease']) + len(categories['new_bid']),
            'ask_events_count': len(categories['ask_increase']) + len(categories['ask_decrease']) + len(categories['new_ask'])
        }

        # Truncate to top N per category
        for category in categories:
            categories[category] = categories[category][:self.top_n]

        result = {
            'symbol': self.symbol,
            'lookback': self.lookback,
            'min_usd': self.min_usd,
            'start_time': lookback_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_events': len(all_events),
            'categories': categories,
            'summary': summary,
            'price_data': price_data
        }

        # Print summary
        self._print_summary(result)

        return result

    def _print_summary(self, result: Dict):
        """Print summary of whale events"""
        summary = result['summary']

        print(f"{BOLD}=== Whale Event Summary ==={RESET}\n")

        print(f"{BOLD}Total Events:{RESET} {summary['total_events']}")
        print(f"{BOLD}Largest Event:{RESET} ", end='')
        if summary['largest_event']:
            largest = summary['largest_event']
            color = self._get_event_color(largest['event_type'], largest['side'])
            print(f"{color}${largest['usd_value']:,.0f}{RESET} {largest['event_type']} at ${largest['price']:.2f}")
        else:
            print("N/A")
        print()

        # Market flow
        print(f"{BOLD}Market Order Flow:{RESET}")
        print(f"  {CYAN}Market Buys:{RESET}  ${summary['total_market_buy_usd']:>12,.0f} ({summary['market_buy_count']} events)")
        print(f"  {MAGENTA}Market Sells:{RESET} ${summary['total_market_sell_usd']:>12,.0f} ({summary['market_sell_count']} events)")
        net_flow = summary['net_market_flow_usd']
        flow_color = GREEN if net_flow > 0 else RED if net_flow < 0 else WHITE
        print(f"  {BOLD}Net Flow:{RESET}     {flow_color}${net_flow:>12,.0f}{RESET}")
        print()

        # Order book changes
        print(f"{BOLD}Order Book Changes:{RESET}")
        print(f"  {GREEN}Bid Increases:{RESET}  ${summary['total_bid_increase_usd']:>12,.0f}")
        print(f"  {RED}Ask Increases:{RESET}  ${summary['total_ask_increase_usd']:>12,.0f}")
        print(f"  {DIM}{RED}Bid Decreases:{RESET}  ${summary['total_bid_decrease_usd']:>12,.0f}")
        print(f"  {DIM}{GREEN}Ask Decreases:{RESET}  ${summary['total_ask_decrease_usd']:>12,.0f}")
        print()

        # Top events per category
        categories = result['categories']

        if categories['market_buy']:
            print(f"{BOLD}{CYAN}Top Market Buys:{RESET}")
            for i, event in enumerate(categories['market_buy'][:5], 1):
                print(f"  {i}. ${event['usd_value']:>10,.0f} @ ${event['price']:.2f} ({event['time'].strftime('%H:%M:%S')})")
            print()

        if categories['market_sell']:
            print(f"{BOLD}{MAGENTA}Top Market Sells:{RESET}")
            for i, event in enumerate(categories['market_sell'][:5], 1):
                print(f"  {i}. ${event['usd_value']:>10,.0f} @ ${event['price']:.2f} ({event['time'].strftime('%H:%M:%S')})")
            print()

        if categories['bid_increase']:
            print(f"{BOLD}{GREEN}Top Bid Increases:{RESET}")
            for i, event in enumerate(categories['bid_increase'][:5], 1):
                print(f"  {i}. ${event['usd_value']:>10,.0f} @ ${event['price']:.2f} ({event['time'].strftime('%H:%M:%S')})")
            print()

        if categories['ask_increase']:
            print(f"{BOLD}{RED}Top Ask Increases:{RESET}")
            for i, event in enumerate(categories['ask_increase'][:5], 1):
                print(f"  {i}. ${event['usd_value']:>10,.0f} @ ${event['price']:.2f} ({event['time'].strftime('%H:%M:%S')})")
            print()

    def _get_event_color(self, event_type: str, side: str = '') -> str:
        """Get color for event type"""
        if event_type == 'market_buy':
            return CYAN
        elif event_type == 'market_sell':
            return MAGENTA
        elif event_type == 'increase':
            return GREEN if side == 'bid' else RED
        elif event_type == 'decrease':
            return f"{DIM}{RED}" if side == 'bid' else f"{DIM}{GREEN}"
        elif 'bid' in event_type or 'buy' in event_type:
            return GREEN
        elif 'ask' in event_type or 'sell' in event_type:
            return RED
        else:
            return WHITE

    def export_json(self, result: Dict, output_file: str = None):
        """Export results to JSON file"""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"data/whale_monitor_{self.symbol}_{timestamp}.json"

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Convert datetime objects to ISO strings
        def serialize_event(event):
            return {
                **event,
                'time': event['time'].isoformat()
            }

        export_data = {
            **result,
            'categories': {
                cat: [serialize_event(e) for e in events]
                for cat, events in result['categories'].items()
            },
            'summary': {
                **result['summary'],
                'largest_event': serialize_event(result['summary']['largest_event'])
                                if result['summary'].get('largest_event') else None
            },
            'price_data': [
                {
                    'time': p['time'].isoformat(),
                    'mid_price': p['mid_price'],
                    'best_bid': p['best_bid'],
                    'best_ask': p['best_ask'],
                    'spread': p['spread']
                }
                for p in result.get('price_data', [])
            ]
        }

        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)

        print(f"{GREEN}Exported to: {output_file}{RESET}")
        return output_file

    def export_csv(self, result: Dict, output_file: str = None):
        """Export results to CSV file"""
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"data/whale_monitor_{self.symbol}_{timestamp}.csv"

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'Timestamp', 'Event Type', 'Side', 'USD Value', 'Price',
                'Volume', 'Distance from Mid %', 'Mid Price'
            ])

            # Combine all events and sort by time
            all_events = []
            for category, events in result['categories'].items():
                all_events.extend(events)

            all_events.sort(key=lambda x: x['time'], reverse=True)

            # Write events
            for event in all_events:
                writer.writerow([
                    event['time'].strftime('%Y-%m-%d %H:%M:%S'),
                    event['event_type'],
                    event['side'],
                    f"${event['usd_value']:.2f}",
                    f"${event['price']:.2f}",
                    event['volume'],
                    f"{event['distance_from_mid_pct']:.2f}%",
                    f"${event['mid_price']:.2f}"
                ])

        print(f"{GREEN}Exported to: {output_file}{RESET}")
        return output_file


def main():
    parser = argparse.ArgumentParser(description='Monitor top whale events by USD value')
    parser.add_argument('symbol', type=str, help='Trading pair (e.g., BTC_USDT)')
    parser.add_argument('--lookback', type=str, default='3h',
                       help='Time period to analyze (e.g., 1h, 3h, 24h)')
    parser.add_argument('--min-usd', type=float, default=5000,
                       help='Minimum USD value for whale events')
    parser.add_argument('--top', type=int, default=50,
                       help='Number of top events per category')
    parser.add_argument('--max-distance', type=float, default=None,
                       help='Maximum distance from mid price as percentage (e.g., 5.0 = 5%%)')
    parser.add_argument('--export-json', action='store_true',
                       help='Export results to JSON file')
    parser.add_argument('--export-csv', action='store_true',
                       help='Export results to CSV file')

    args = parser.parse_args()

    try:
        monitor = WhaleMonitor(
            symbol=args.symbol,
            lookback=args.lookback,
            min_usd=args.min_usd,
            top_n=args.top,
            max_distance=args.max_distance
        )

        result = monitor.analyze()

        if args.export_json:
            monitor.export_json(result)

        if args.export_csv:
            monitor.export_csv(result)

    except Exception as e:
        print(f"{RED}Error: {e}{RESET}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
