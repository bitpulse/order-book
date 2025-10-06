#!/usr/bin/env python3
"""
Live Terminal Chart - Shows price and whale events in real-time
Uses plotille for terminal-based charting with InfluxDB data
"""

import os
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import argparse
from collections import deque

try:
    import plotille
    from influxdb_client import InfluxDBClient
    from dotenv import load_dotenv
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Install with: pip install plotille influxdb-client python-dotenv")
    sys.exit(1)


class LiveChart:
    def __init__(self, symbol: str, lookback: str = "5m", min_usd: float = 5000):
        self.symbol = symbol
        self.lookback = lookback
        self.min_usd = min_usd

        # Load environment
        load_dotenv()

        # InfluxDB connection
        self.client = InfluxDBClient(
            url=os.getenv("INFLUXDB_URL"),
            token=os.getenv("INFLUXDB_TOKEN"),
            org=os.getenv("INFLUXDB_ORG")
        )
        self.query_api = self.client.query_api()
        self.bucket = os.getenv("INFLUXDB_BUCKET")

        # Data storage
        self.price_data = deque(maxlen=500)  # Keep last 500 points
        self.whale_events = []
        self.last_whale_timestamp = None

    def fetch_price_history(self):
        """Fetch price history from InfluxDB"""
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{self.lookback})
          |> filter(fn: (r) => r._measurement == "orderbook_price")
          |> filter(fn: (r) => r.symbol == "{self.symbol}")
          |> filter(fn: (r) => r._field == "mid_price")
          |> aggregateWindow(every: 1s, fn: last, createEmpty: false)
        '''

        tables = self.query_api.query(query)

        new_data = []
        for table in tables:
            for record in table.records:
                timestamp = record.get_time()
                price = record.get_value()
                new_data.append((timestamp, price))

        # Sort by time and update deque
        new_data.sort(key=lambda x: x[0])

        # Clear and refill (for initial load or if we need full refresh)
        if not self.price_data or len(new_data) > len(self.price_data):
            self.price_data.clear()
            self.price_data.extend(new_data)
        else:
            # Append only newer data
            if self.price_data:
                last_time = self.price_data[-1][0]
                for timestamp, price in new_data:
                    if timestamp > last_time:
                        self.price_data.append((timestamp, price))

    def fetch_whale_events(self, incremental: bool = False):
        """Fetch whale events from InfluxDB"""
        if incremental and self.last_whale_timestamp:
            # Incremental update
            start_time = self.last_whale_timestamp.isoformat().replace('+00:00', 'Z')
            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: time(v: "{start_time}"))
              |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
              |> filter(fn: (r) => r.symbol == "{self.symbol}")
              |> filter(fn: (r) => r._field == "usd_value" or r._field == "price" or r._field == "volume")
              |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> filter(fn: (r) => r.usd_value >= {self.min_usd})
              |> sort(columns: ["_time"], desc: false)
            '''
        else:
            # Initial load
            query = f'''
            from(bucket: "{self.bucket}")
              |> range(start: -{self.lookback})
              |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
              |> filter(fn: (r) => r.symbol == "{self.symbol}")
              |> filter(fn: (r) => r._field == "usd_value" or r._field == "price" or r._field == "volume")
              |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> filter(fn: (r) => r.usd_value >= {self.min_usd})
              |> sort(columns: ["_time"], desc: false)
            '''

        tables = self.query_api.query(query)

        new_events = []
        for table in tables:
            for record in table.records:
                timestamp = record.get_time()
                event = {
                    'time': timestamp,
                    'event_type': record.values.get('event_type'),
                    'side': record.values.get('side'),
                    'price': record.values.get('price'),
                    'volume': record.values.get('volume'),
                    'usd_value': record.values.get('usd_value')
                }
                new_events.append(event)

                # Update last timestamp
                if not self.last_whale_timestamp or timestamp > self.last_whale_timestamp:
                    self.last_whale_timestamp = timestamp

        if not incremental:
            self.whale_events = new_events
        else:
            self.whale_events.extend(new_events)

            # Keep only events within lookback period
            cutoff_time = datetime.now(self.whale_events[0]['time'].tzinfo) - self._parse_duration(self.lookback)
            self.whale_events = [e for e in self.whale_events if e['time'] > cutoff_time]

    def _parse_duration(self, duration: str) -> timedelta:
        """Parse duration string like '5m', '1h', '30s' into timedelta"""
        unit = duration[-1]
        value = int(duration[:-1])

        if unit == 's':
            return timedelta(seconds=value)
        elif unit == 'm':
            return timedelta(minutes=value)
        elif unit == 'h':
            return timedelta(hours=value)
        elif unit == 'd':
            return timedelta(days=value)
        else:
            raise ValueError(f"Unknown duration unit: {unit}")

    def render_chart(self):
        """Render a clean ASCII chart with whale events"""
        if not self.price_data:
            return "No price data available"

        # Get terminal dimensions
        try:
            rows, columns = os.popen('stty size', 'r').read().split()
            width = int(columns) - 10
            height = 20
        except:
            width = 120
            height = 20

        # Prepare data
        start_time = self.price_data[0][0]
        prices = [p for t, p in self.price_data]

        if not prices:
            return "No data to plot"

        # Create figure for multiple series
        fig = plotille.Figure()
        fig.width = width
        fig.height = height
        fig.color_mode = 'byte'

        # Set limits
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price
        if price_range == 0:
            price_range = max_price * 0.01

        fig.set_x_limits(0, len(prices) - 1)
        fig.set_y_limits(min_price - price_range * 0.05, max_price + price_range * 0.05)

        # Plot price line
        fig.plot(list(range(len(prices))), prices, lc=51, label='Price')  # Cyan

        # Create index mapping for whale events
        # Map timestamp to index in price_data
        time_to_idx = {}
        for idx, (t, p) in enumerate(self.price_data):
            time_to_idx[t] = idx

        # Only show significant whale events (top 20 by USD value)
        sorted_events = sorted(self.whale_events, key=lambda x: x['usd_value'], reverse=True)[:20]

        # Plot whale events as scatter points (no lines connecting them)
        for event in sorted_events:
            # Find closest price data point
            event_time = event['time']
            closest_idx = None
            min_diff = float('inf')

            for idx, (t, p) in enumerate(self.price_data):
                diff = abs((event_time - t).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    closest_idx = idx

            if closest_idx is not None and min_diff < 5:  # Within 5 seconds
                # Use the actual mid price at that time, not the event price
                price_at_time = self.price_data[closest_idx][1]

                # Plot single point (scatter)
                if event['side'] == 'bid':
                    fig.scatter([closest_idx], [price_at_time], lc=82, marker='▲')  # Green bids
                elif event['side'] == 'ask':
                    fig.scatter([closest_idx], [price_at_time], lc=196, marker='▼')  # Red asks

        fig.x_label = 'Time →'
        fig.y_label = 'Price'

        return fig.show(legend=False)

    def get_stats(self) -> Dict:
        """Get current statistics"""
        if not self.price_data:
            return {}

        current_price = self.price_data[-1][1]
        first_price = self.price_data[0][1]
        price_change = current_price - first_price
        price_change_pct = (price_change / first_price) * 100

        # Categorize events
        categories = self.categorize_events()

        # Calculate category stats
        market_buy_volume = sum(e['usd_value'] for e in categories['market_buy'])
        market_sell_volume = sum(e['usd_value'] for e in categories['market_sell'])
        bid_increase_volume = sum(e['usd_value'] for e in categories['bid_increase'])
        ask_increase_volume = sum(e['usd_value'] for e in categories['ask_increase'])
        bid_decrease_volume = sum(e['usd_value'] for e in categories['bid_decrease'])
        ask_decrease_volume = sum(e['usd_value'] for e in categories['ask_decrease'])

        return {
            'current_price': current_price,
            'price_change': price_change,
            'price_change_pct': price_change_pct,
            'total_events': len(self.whale_events),
            'market_buy_volume': market_buy_volume,
            'market_sell_volume': market_sell_volume,
            'market_buy_count': len(categories['market_buy']),
            'market_sell_count': len(categories['market_sell']),
            'bid_increase_volume': bid_increase_volume,
            'ask_increase_volume': ask_increase_volume,
            'bid_decrease_volume': bid_decrease_volume,
            'ask_decrease_volume': ask_decrease_volume,
            'bid_increase_count': len(categories['bid_increase']),
            'ask_increase_count': len(categories['ask_increase']),
            'bid_decrease_count': len(categories['bid_decrease']),
            'ask_decrease_count': len(categories['ask_decrease']),
            'categories': categories,
            'data_points': len(self.price_data)
        }

    def categorize_events(self):
        """Categorize whale events like whale_monitor.py"""
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

        for event in self.whale_events:
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

    def format_stats(self, stats: Dict) -> str:
        """Format statistics for display like whale_monitor.py"""
        if not stats:
            return "No data available"

        # ANSI colors
        GREEN = '\033[92m'
        RED = '\033[91m'
        CYAN = '\033[96m'
        MAGENTA = '\033[95m'
        WHITE = '\033[97m'
        BOLD = '\033[1m'
        DIM = '\033[2m'
        RESET = '\033[0m'

        lines = []

        # Header
        lines.append(f"{CYAN}Live Whale Monitor - {self.symbol}{RESET}")
        lines.append(f"{DIM}Lookback: {self.lookback} | Min USD: ${self.min_usd:,.0f} | Last Update: {datetime.now().strftime('%H:%M:%S')}{RESET}")
        lines.append("")

        # Price info
        price_change_color = GREEN if stats['price_change'] >= 0 else RED
        lines.append(f"{BOLD}Current Price:{RESET} ${stats['current_price']:.6f}")
        lines.append(f"{BOLD}Price Change:{RESET} {price_change_color}{stats['price_change']:+.6f} ({stats['price_change_pct']:+.2f}%){RESET}")
        lines.append("")

        # Summary
        lines.append(f"{BOLD}=== Whale Event Summary ==={RESET}")
        lines.append("")
        lines.append(f"{BOLD}Total Events:{RESET} {stats['total_events']}")
        lines.append("")

        # Market flow
        lines.append(f"{BOLD}Market Order Flow:{RESET}")
        lines.append(f"  {CYAN}Market Buys:{RESET}  ${stats['market_buy_volume']:>12,.0f} ({stats['market_buy_count']} events)")
        lines.append(f"  {MAGENTA}Market Sells:{RESET} ${stats['market_sell_volume']:>12,.0f} ({stats['market_sell_count']} events)")
        net_flow = stats['market_buy_volume'] - stats['market_sell_volume']
        flow_color = GREEN if net_flow > 0 else RED if net_flow < 0 else WHITE
        lines.append(f"  {BOLD}Net Flow:{RESET}     {flow_color}${net_flow:>12,.0f}{RESET}")
        lines.append("")

        # Order book changes
        lines.append(f"{BOLD}Order Book Changes:{RESET}")
        lines.append(f"  {GREEN}Bid Increases:{RESET}  ${stats['bid_increase_volume']:>12,.0f} ({stats['bid_increase_count']} events)")
        lines.append(f"  {RED}Ask Increases:{RESET}  ${stats['ask_increase_volume']:>12,.0f} ({stats['ask_increase_count']} events)")
        lines.append(f"  {DIM}{RED}Bid Decreases:{RESET}  ${stats['bid_decrease_volume']:>12,.0f} ({stats['bid_decrease_count']} events)")
        lines.append(f"  {DIM}{GREEN}Ask Decreases:{RESET}  ${stats['ask_decrease_volume']:>12,.0f} ({stats['ask_decrease_count']} events)")
        lines.append("")

        return "\n".join(lines)

    def format_top_events(self, stats: Dict, top_n: int = 3) -> str:
        """Format top whale events in a compact table"""
        if not stats or 'categories' not in stats:
            return ""

        # ANSI colors
        GREEN = '\033[92m'
        RED = '\033[91m'
        CYAN = '\033[96m'
        MAGENTA = '\033[95m'
        BOLD = '\033[1m'
        DIM = '\033[2m'
        RESET = '\033[0m'

        categories = stats['categories']
        lines = []

        lines.append(f"{BOLD}=== Recent Large Events ==={RESET}")
        lines.append("")

        # Combine and show most recent large events
        all_events = []
        all_events.extend([(e, 'BUY', CYAN) for e in categories['market_buy'][:top_n]])
        all_events.extend([(e, 'SELL', MAGENTA) for e in categories['market_sell'][:top_n]])
        all_events.extend([(e, 'BID+', GREEN) for e in categories['bid_increase'][:top_n]])
        all_events.extend([(e, 'ASK+', RED) for e in categories['ask_increase'][:top_n]])

        # Sort by time (most recent first)
        all_events.sort(key=lambda x: x[0]['time'], reverse=True)

        # Show top events
        for event, label, color in all_events[:10]:
            time_str = event['time'].strftime('%H:%M:%S')
            lines.append(f"{DIM}{time_str}{RESET} {color}{label:5s}{RESET} ${event['usd_value']:>10,.0f} @ ${event['price']:<10.2f}")

        lines.append("")
        return "\n".join(lines)

    def run(self, update_interval: int = 2, top_events: int = 5):
        """Run the live chart with auto-refresh"""
        print(f"Starting live chart for {self.symbol}...")
        print("Press Ctrl+C to exit\n")

        # Initial load
        print("Loading initial data...")
        self.fetch_price_history()
        self.fetch_whale_events(incremental=False)

        try:
            while True:
                # Clear screen
                os.system('clear' if os.name == 'posix' else 'cls')

                # Fetch updates
                self.fetch_price_history()
                self.fetch_whale_events(incremental=True)

                # Get stats
                stats = self.get_stats()

                # Render in clean layout
                print(self.format_stats(stats))
                print(self.format_top_events(stats, top_n=top_events))
                print()
                print(self.render_chart())
                print()
                print("\033[2mPress Ctrl+C to exit\033[0m")

                # Wait for next update
                time.sleep(update_interval)

        except KeyboardInterrupt:
            print("\n\nExiting...")
            self.client.close()
            sys.exit(0)

    def close(self):
        """Close InfluxDB connection"""
        self.client.close()


def main():
    parser = argparse.ArgumentParser(description='Live terminal chart showing price and whale events')
    parser.add_argument('symbol', help='Trading pair symbol (e.g., SPX_USDT)')
    parser.add_argument('--lookback', default='5m', help='Time window to display (e.g., 5m, 1h, 30s)')
    parser.add_argument('--min-usd', type=float, default=5000, help='Minimum USD value for whale events')
    parser.add_argument('--interval', type=int, default=2, help='Update interval in seconds')
    parser.add_argument('--top', type=int, default=5, help='Number of top events to show per category')

    args = parser.parse_args()

    chart = LiveChart(
        symbol=args.symbol,
        lookback=args.lookback,
        min_usd=args.min_usd
    )

    try:
        chart.run(update_interval=args.interval, top_events=args.top)
    finally:
        chart.close()


if __name__ == '__main__':
    main()
