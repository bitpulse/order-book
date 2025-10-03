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

    def get_price_data(self, start_time: datetime, end_time: datetime) -> List[Dict]:
        """
        Get all price points for a specific time interval

        Args:
            start_time: Start of interval
            end_time: End of interval

        Returns:
            List of price point dicts with time, mid_price, best_bid, best_ask, spread
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
            List of dicts with price change info, price data, and whale events
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
            # Calculate extended time window for context (before and after)
            interval_duration = change['end_time'] - change['start_time']

            # Get price data: before, during, and after the interval
            # Show equal time before and after for context
            extended_start = change['start_time'] - interval_duration
            extended_end = change['end_time'] + interval_duration
            price_data = self.get_price_data(extended_start, extended_end)

            # Get whale events for the interval only (not the extended period)
            whale_events = self.get_whale_events(change['start_time'], change['end_time'])

            # Also get whale events from before and after for context
            whale_events_before = self.get_whale_events(extended_start, change['start_time'])
            whale_events_after = self.get_whale_events(change['end_time'], extended_end)

            # Aggregate events by type (only for the main interval)
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
                'price_data': price_data,
                'whale_events': whale_events,
                'whale_events_before': whale_events_before,
                'whale_events_after': whale_events_after,
                'event_summary': dict(event_summary),
                'extended_start': extended_start,
                'extended_end': extended_end
            })

        return results

    def _draw_mini_chart(self, price_data: List[Dict], interval_start: datetime, interval_end: datetime,
                         width: int = 70, height: int = 15) -> List[str]:
        """Draw ASCII line chart from price data with interval highlighting"""
        if len(price_data) < 2:
            return [f"{YELLOW}Insufficient data for chart{RESET}"]

        # Extract prices and times
        prices = [p['mid_price'] for p in price_data]
        times = [p['time'] for p in price_data]

        # Calculate price range with padding
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price

        # Avoid division by zero and add padding
        if price_range == 0:
            price_range = max_price * 0.001 if max_price > 0 else 1.0

        # Add 2% padding to top and bottom
        padding = price_range * 0.02
        min_price -= padding
        max_price += padding
        price_range = max_price - min_price

        # Resample data to fit chart width
        step = max(1, len(prices) // width)
        sampled_prices = []
        sampled_times = []
        for i in range(0, len(prices), step):
            chunk = prices[i:i+step]
            sampled_prices.append(sum(chunk) / len(chunk))  # Average
            sampled_times.append(times[i])

        # Ensure we don't exceed chart width
        sampled_prices = sampled_prices[:width]
        sampled_times = sampled_times[:width]

        # Find the exact point where the biggest price change happened
        max_change_col = -1
        max_change_amount = 0
        for col in range(1, len(sampled_prices)):
            change = abs(sampled_prices[col] - sampled_prices[col - 1])
            if change > max_change_amount:
                max_change_amount = change
                max_change_col = col

        # Determine which columns are in the interval (for reference only)
        interval_cols = set()
        for col, t in enumerate(sampled_times):
            if interval_start <= t <= interval_end:
                interval_cols.add(col)

        # Convert prices to row positions
        price_rows = []
        for price in sampled_prices:
            normalized = (price - min_price) / price_range
            row = int((1 - normalized) * (height - 1))
            price_rows.append(row)

        # Create chart grid
        chart = []

        # Draw chart rows (top to bottom = high to low price)
        for row in range(height):
            # Build line
            line_parts = []

            # Add price scale on the left
            if row == 0:
                label = f"{max_price:>9.4f} "
            elif row == height - 1:
                label = f"{min_price:>9.4f} "
            elif row == height // 2:
                label = f"{(max_price + min_price) / 2:>9.4f} "
            else:
                label = " " * 10

            line_parts.append(f"{DIM}{label}{RESET}")
            line_parts.append(f"{DIM}┃{RESET}")

            # Draw chart line
            for col in range(len(price_rows)):
                current_row = price_rows[col]

                # Highlight the exact spike point
                is_spike = (col == max_change_col or col == max_change_col - 1)

                # Determine color based on trend
                if col > 0:
                    prev_price = sampled_prices[col - 1]
                    curr_price = sampled_prices[col]
                    if curr_price > prev_price:
                        base_color = GREEN
                    elif curr_price < prev_price:
                        base_color = RED
                    else:
                        base_color = WHITE
                else:
                    base_color = CYAN

                # Make spike point extremely bright, rest dimmed
                if is_spike:
                    color = f"{BOLD}{base_color}"
                else:
                    color = f"{DIM}{base_color}"

                # Check if we should draw on this row
                if current_row == row:
                    # Draw the main line point
                    if col < len(price_rows) - 1:
                        next_row = price_rows[col + 1]
                        if next_row < current_row:  # Going up
                            # Use special marker for spike
                            if is_spike:
                                line_parts.append(f"{color}▲{RESET}")
                            else:
                                line_parts.append(f"{color}╱{RESET}")
                        elif next_row > current_row:  # Going down
                            # Use special marker for spike
                            if is_spike:
                                line_parts.append(f"{color}▼{RESET}")
                            else:
                                line_parts.append(f"{color}╲{RESET}")
                        else:  # Flat
                            line_parts.append(f"{color}━{RESET}")
                    else:
                        line_parts.append(f"{color}●{RESET}")

                # Draw connecting lines between points
                elif col > 0:
                    prev_row = price_rows[col - 1]
                    next_row = price_rows[col]

                    # Check if line passes through this row
                    if prev_row < next_row:  # Line going down
                        if row > prev_row and row <= next_row:
                            line_parts.append(f"{color}│{RESET}")
                        else:
                            line_parts.append(" ")
                    elif prev_row > next_row:  # Line going up
                        if row < prev_row and row >= next_row:
                            line_parts.append(f"{color}│{RESET}")
                        else:
                            line_parts.append(" ")
                    else:
                        line_parts.append(" ")
                else:
                    line_parts.append(" ")

            chart.append("".join(line_parts))

        # Add time axis with interval markers
        time_axis_parts = [" " * 10, f"{DIM}┗{RESET}"]

        # Calculate time labels
        if len(price_data) > 0:
            start_time = price_data[0]['time']
            end_time = price_data[-1]['time']

            # Build horizontal line with spike marker
            axis_line = []
            for col in range(len(sampled_prices)):
                if col == max_change_col:
                    # Mark the exact spike point
                    if sampled_prices[col] > sampled_prices[col - 1]:
                        axis_line.append(f"{BOLD}{GREEN}▲{RESET}")
                    else:
                        axis_line.append(f"{BOLD}{RED}▼{RESET}")
                else:
                    axis_line.append(f"{DIM}━{RESET}")

            time_axis_parts.append("".join(axis_line))
            chart.append("".join(time_axis_parts))

            # Add time labels with spike marker
            time_label_parts = [" " * 11, f"{DIM}{start_time.strftime('%H:%M:%S')}{RESET}"]

            # Add spike marker label
            if max_change_col >= 0 and max_change_col < len(sampled_times):
                spike_time = sampled_times[max_change_col]

                # Calculate spacing
                spaces_before_spike = max(0, max_change_col - 8)
                if spaces_before_spike > 0:
                    time_label_parts.append(" " * spaces_before_spike)

                # Determine if price went up or down
                if sampled_prices[max_change_col] > sampled_prices[max_change_col - 1]:
                    spike_marker = f"{BOLD}{GREEN}↑SPIKE{RESET}"
                else:
                    spike_marker = f"{BOLD}{RED}↓SPIKE{RESET}"

                time_label_parts.append(spike_marker)

                spaces_after = max(0, len(sampled_prices) - max_change_col - 14)
                if spaces_after > 0:
                    time_label_parts.append(" " * spaces_after)
            else:
                time_label_parts.append(" " * (len(sampled_prices) - 16))

            time_label_parts.append(f"{DIM}{end_time.strftime('%H:%M:%S')}{RESET}")
            chart.append("".join(time_label_parts))

        return chart

    def display_terminal(self, results: List[Dict]):
        """Display results in terminal with color coding"""
        for result in results:
            change_pct = result['change_pct']
            color = GREEN if change_pct > 0 else RED

            print(f"{BOLD}{'='*80}{RESET}")
            print(f"{BOLD}Rank #{result['rank']}: {color}{change_pct:+.3f}%{RESET} price change{RESET}")
            print(f"{DIM}Time: {result['start_time']} → {result['end_time']}{RESET}")
            print(f"{DIM}Price: ${result['start_price']:.2f} → ${result['end_price']:.2f}{RESET}")
            print(f"{DIM}Price data points: {len(result['price_data'])}{RESET}")

            # Draw price chart (only if enough data points for meaningful visualization)
            if result['price_data'] and len(result['price_data']) >= 10:
                print(f"\n{BOLD}Price Movement:{RESET} {DIM}(spike point highlighted with ▲/▼ marker){RESET}")
                chart_lines = self._draw_mini_chart(
                    result['price_data'],
                    result['start_time'],
                    result['end_time']
                )
                for line in chart_lines:
                    print(line)
            elif result['price_data'] and len(result['price_data']) >= 2:
                print(f"\n{DIM}Price Movement: {len(result['price_data'])} data points (too few for chart, try larger interval){RESET}")

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
            export_result['extended_start'] = result['extended_start'].isoformat()
            export_result['extended_end'] = result['extended_end'].isoformat()

            # Convert price data times (includes before, during, and after)
            export_result['price_data'] = [
                {**point, 'time': point['time'].isoformat()}
                for point in result['price_data']
            ]

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
