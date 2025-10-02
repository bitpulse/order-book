#!/usr/bin/env python3
"""
MEXC Order Book Price Monitor - Live InfluxDB Reader
Monitors real-time price data from InfluxDB with ASCII chart visualization
"""

import os
import sys
import time
import asyncio
import argparse
from datetime import datetime, timedelta
from collections import deque
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

# ANSI color codes
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'
WHITE = '\033[97m'
BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'

# Load environment variables
load_dotenv()


class OrderBookPriceMonitor:
    """Monitor live order book prices from InfluxDB with ASCII chart"""

    def __init__(self, symbol: str, refresh_interval: float = 1.0,
                 chart_width: int = 120, chart_height: int = 30, history_seconds: int = 300):
        self.symbol = symbol
        self.refresh_interval = refresh_interval
        self.chart_width = chart_width
        self.chart_height = chart_height
        self.history_seconds = history_seconds

        # InfluxDB connection
        influx_url = os.getenv('INFLUXDB_URL')
        influx_token = os.getenv('INFLUXDB_TOKEN')
        influx_org = os.getenv('INFLUXDB_ORG')
        self.influx_bucket = os.getenv('INFLUXDB_BUCKET')

        if not all([influx_url, influx_token, influx_org, self.influx_bucket]):
            print(f"{RED}Error: Missing InfluxDB credentials in .env{RESET}")
            sys.exit(1)

        self.client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
        self.query_api = self.client.query_api()

        # Price history (time, price) tuples
        self.price_history = deque(maxlen=1000)

        # Whale events history (time, event_type, side, usd_value, price, volume)
        self.whale_events = deque(maxlen=500)

        # Current state
        self.current_price = None
        self.best_bid = None
        self.best_ask = None
        self.spread = None
        self.last_update = None

        # Statistics
        self.total_updates = 0
        self.whale_buy_count = 0
        self.whale_sell_count = 0
        self.whale_bid_count = 0
        self.whale_ask_count = 0
        self.start_time = datetime.now()

    def _fetch_price_history(self):
        """Fetch price history from InfluxDB for charting"""
        query = f'''
from(bucket: "{self.influx_bucket}")
  |> range(start: -{self.history_seconds}s)
  |> filter(fn: (r) => r._measurement == "orderbook_price")
  |> filter(fn: (r) => r.symbol == "{self.symbol}")
  |> filter(fn: (r) => r._field == "mid_price")
  |> sort(columns: ["_time"])
'''

        try:
            result = self.query_api.query(query)

            self.price_history.clear()

            for table in result:
                for record in table.records:
                    timestamp = record.get_time()
                    price = record.get_value()
                    self.price_history.append((timestamp, price))

            return len(self.price_history) > 0

        except Exception as e:
            print(f"{RED}Error fetching history: {e}{RESET}")
            return False

    def _fetch_whale_events(self):
        """Fetch whale events from InfluxDB"""
        # Fetch recent events (last 2 minutes)
        query = f'''
from(bucket: "{self.influx_bucket}")
  |> range(start: -2m)
  |> filter(fn: (r) => r._measurement == "orderbook_whale_events")
  |> filter(fn: (r) => r.symbol == "{self.symbol}")
  |> filter(fn: (r) => r._field == "price" or r._field == "usd_value" or r._field == "volume")
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
'''

        try:
            result = self.query_api.query(query)

            # Collect all events first
            all_events = []
            for table in result:
                for record in table.records:
                    timestamp = record.get_time()
                    event_type = record.values.get('event_type', '')
                    side = record.values.get('side', '')
                    price = record.values.get('price', 0)
                    usd_value = record.values.get('usd_value', 0)
                    volume = record.values.get('volume', 0)

                    all_events.append((timestamp, event_type, side, usd_value, price, volume))

            # Sort by timestamp (most recent first) and keep only last 50
            all_events.sort(key=lambda x: x[0], reverse=True)
            all_events = all_events[:50]

            # Now populate whale_events and count
            self.whale_events.clear()
            self.whale_buy_count = 0
            self.whale_sell_count = 0
            self.whale_bid_count = 0
            self.whale_ask_count = 0

            for timestamp, event_type, side, usd_value, price, volume in all_events:
                self.whale_events.append((timestamp, event_type, side, usd_value, price, volume))

                # Count events by type
                if event_type == 'market_buy':
                    self.whale_buy_count += 1
                elif event_type == 'market_sell':
                    self.whale_sell_count += 1
                elif side == 'bid':
                    self.whale_bid_count += 1
                elif side == 'ask':
                    self.whale_ask_count += 1

            return len(self.whale_events) > 0

        except Exception as e:
            print(f"{RED}Error fetching whale events: {e}{RESET}")
            return False

    def _fetch_latest_data(self):
        """Fetch the most recent complete data from InfluxDB"""
        query = f'''
from(bucket: "{self.influx_bucket}")
  |> range(start: -1m)
  |> filter(fn: (r) => r._measurement == "orderbook_price")
  |> filter(fn: (r) => r.symbol == "{self.symbol}")
  |> last()
'''

        try:
            result = self.query_api.query(query)

            data = {}
            for table in result:
                for record in table.records:
                    field = record.values.get('_field')
                    value = record.get_value()
                    timestamp = record.get_time()
                    data[field] = value
                    if 'timestamp' not in data:
                        data['timestamp'] = timestamp

            if data:
                self.current_price = data.get('mid_price')
                self.best_bid = data.get('best_bid')
                self.best_ask = data.get('best_ask')
                self.spread = data.get('spread')
                self.last_update = data.get('timestamp')
                self.total_updates += 1
                return True

            return False

        except Exception as e:
            print(f"{RED}Error fetching data: {e}{RESET}")
            return False

    def _format_price(self, price: float) -> str:
        """Format price with appropriate precision"""
        if price is None:
            return "N/A"
        if price >= 1000:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:.4f}"
        else:
            return f"{price:.8f}"

    def _draw_chart(self) -> list:
        """Draw ASCII line chart from price history"""
        if len(self.price_history) < 2:
            return [f"{YELLOW}Collecting data...{RESET}"]

        # Extract prices
        prices = [p for t, p in self.price_history]

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
        step = max(1, len(prices) // self.chart_width)
        sampled_prices = []
        for i in range(0, len(prices), step):
            chunk = prices[i:i+step]
            sampled_prices.append(sum(chunk) / len(chunk))  # Average

        # Ensure we don't exceed chart width
        sampled_prices = sampled_prices[:self.chart_width]

        # Convert prices to row positions
        price_rows = []
        for price in sampled_prices:
            normalized = (price - min_price) / price_range
            row = int((1 - normalized) * (self.chart_height - 1))
            price_rows.append(row)

        # Create chart grid
        chart = []

        # Draw chart rows (top to bottom = high to low price)
        for row in range(self.chart_height):
            # Build line
            line_parts = []

            # Add price scale on the left
            if row == 0:
                label = f"{max_price:>11.4f} "
            elif row == self.chart_height - 1:
                label = f"{min_price:>11.4f} "
            elif row == self.chart_height // 2:
                label = f"{(max_price + min_price) / 2:>11.4f} "
            else:
                label = " " * 12

            line_parts.append(f"{DIM}{label}{RESET}")
            line_parts.append(f"{DIM}┃{RESET}")

            # Draw chart line
            for col in range(len(price_rows)):
                current_row = price_rows[col]

                # Determine color based on overall trend
                if col > 0:
                    prev_price = sampled_prices[col - 1]
                    curr_price = sampled_prices[col]
                    if curr_price > prev_price:
                        color = GREEN
                    elif curr_price < prev_price:
                        color = RED
                    else:
                        color = YELLOW
                else:
                    color = CYAN

                # Check if we should draw on this row
                if current_row == row:
                    # Draw the main line point
                    if col < len(price_rows) - 1:
                        next_row = price_rows[col + 1]
                        if next_row < current_row:  # Going up
                            line_parts.append(f"{color}╱{RESET}")
                        elif next_row > current_row:  # Going down
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

        # Add time axis
        time_axis_parts = [" " * 12, f"{DIM}┗{RESET}"]

        # Calculate time labels
        if len(self.price_history) > 0:
            start_time = self.price_history[0][0]
            end_time = self.price_history[-1][0]

            # Add horizontal line
            time_axis_parts.append(f"{DIM}{'━' * len(sampled_prices)}{RESET}")
            chart.append("".join(time_axis_parts))

            # Add time labels
            time_label = f" " * 13 + f"{DIM}"
            time_label += f"{start_time.strftime('%H:%M:%S')}"
            time_label += " " * (len(sampled_prices) - 25)
            time_label += f"{end_time.strftime('%H:%M:%S')}"
            time_label += f"{RESET}"
            chart.append(time_label)

        return chart

    def _format_event_type(self, event_type: str, side: str) -> tuple:
        """Format event type for display with color and icon"""
        event_map = {
            'market_buy': (f"{GREEN}🐋 MARKET BUY {RESET}", GREEN),
            'market_sell': (f"{RED}🐋 MARKET SELL{RESET}", RED),
            'new_bid': (f"{GREEN}BID WALL    {RESET}", GREEN),
            'new_ask': (f"{RED}ASK WALL    {RESET}", RED),
            'increase': (f"{CYAN}{'BID' if side == 'bid' else 'ASK'} ↑       {RESET}", CYAN if side == 'bid' else MAGENTA),
            'decrease': (f"{DIM}{'BID' if side == 'bid' else 'ASK'} ↓       {RESET}", DIM),
            'entered_top': (f"{YELLOW}{'BID' if side == 'bid' else 'ASK'}→TOP20  {RESET}", YELLOW),
            'left_top': (f"{DIM}{'BID' if side == 'bid' else 'ASK'}←OUT    {RESET}", DIM),
        }
        return event_map.get(event_type, (f"{WHITE}{event_type:<12}{RESET}", WHITE))

    def _draw_whale_panel(self):
        """Draw recent whale events list (Bloomberg style)"""
        if len(self.whale_events) == 0:
            print(f"{DIM}No whale activity in this time window{RESET}")
            return

        print(f"{BOLD}Recent Whale Activity:{RESET}")

        # Header
        print(f"{DIM}{'Time':<12} {'Event':<12} {'Price':<14} {'Volume':<12} {'Value':<14} {'Info'}{RESET}")
        print(f"{DIM}{'─'*80}{RESET}")

        # Show last 12 events (most recent first)
        recent_events = list(self.whale_events)[-12:]
        recent_events.reverse()

        for timestamp, event_type, side, usd_value, price, volume in recent_events:
            time_str = timestamp.strftime('%H:%M:%S')
            event_str, color = self._format_event_type(event_type, side)

            # Format price
            if price >= 1000:
                price_str = f"${price:,.2f}"
            elif price >= 1:
                price_str = f"${price:.4f}"
            else:
                price_str = f"${price:.8f}"

            # Format volume
            if volume >= 1_000_000:
                volume_str = f"{volume/1_000_000:.2f}M"
            elif volume >= 1_000:
                volume_str = f"{volume/1_000:.1f}k"
            else:
                volume_str = f"{volume:.1f}"

            # Format USD value
            if usd_value >= 1_000_000:
                value_str = f"${usd_value/1_000_000:.2f}M"
            elif usd_value >= 1_000:
                value_str = f"${usd_value/1_000:.1f}k"
            else:
                value_str = f"${usd_value:.0f}"

            # Additional info
            info = ""
            if event_type in ['market_buy', 'market_sell']:
                info = "Aggressive"
            elif event_type in ['new_bid', 'new_ask']:
                info = "New order"
            elif event_type == 'entered_top':
                info = "Entered view"
            elif event_type == 'left_top':
                info = "Left view"

            print(f"{time_str:<12} {event_str} {color}{price_str:<14}{RESET} "
                  f"{volume_str:<12} {color}{BOLD}{value_str:<14}{RESET} {DIM}{info}{RESET}")

    def _clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name != 'nt' else 'cls')

    def _display(self):
        """Display chart and current price information"""
        self._clear_screen()

        # Header
        print(f"{BOLD}{CYAN}{'═'*80}{RESET}")
        print(f"{BOLD}{WHITE}MEXC Order Book Price Chart - {self.symbol}{RESET}")
        print(f"{CYAN}{'═'*80}{RESET}\n")

        # Current price bar
        if self.current_price is not None:
            # Calculate price change
            if len(self.price_history) >= 2:
                start_price = self.price_history[0][1]
                price_change = self.current_price - start_price
                price_change_pct = (price_change / start_price * 100) if start_price > 0 else 0

                if price_change > 0:
                    change_color = GREEN
                    arrow = "↑"
                    sign = "+"
                elif price_change < 0:
                    change_color = RED
                    arrow = "↓"
                    sign = ""
                else:
                    change_color = WHITE
                    arrow = "─"
                    sign = ""

                change_str = f"{sign}{price_change:.2f} ({sign}{price_change_pct:.2f}%)"
            else:
                change_color = WHITE
                arrow = "─"
                change_str = "─"

            print(f"{BOLD}Current Price: {change_color}{arrow} ${self._format_price(self.current_price)}{RESET}  "
                  f"{change_color}{change_str}{RESET}  "
                  f"{DIM}|{RESET}  "
                  f"{BOLD}Whale Activity:{RESET} "
                  f"{GREEN}🐋 {self.whale_buy_count} Buys{RESET}  "
                  f"{RED}🐋 {self.whale_sell_count} Sells{RESET}")
            print(f"{GREEN}Best Bid: ${self._format_price(self.best_bid)}{RESET}  "
                  f"{RED}Best Ask: ${self._format_price(self.best_ask)}{RESET}  "
                  f"{YELLOW}Spread: ${self._format_price(self.spread)}{RESET}  "
                  f"{DIM}|{RESET}  "
                  f"{CYAN}{self.whale_bid_count} Bid Walls{RESET}  "
                  f"{MAGENTA}{self.whale_ask_count} Ask Walls{RESET}")

            # Data freshness
            if self.last_update:
                age = datetime.now(self.last_update.tzinfo) - self.last_update
                age_seconds = age.total_seconds()

                if age_seconds > 10:
                    age_color = RED
                elif age_seconds > 5:
                    age_color = YELLOW
                else:
                    age_color = GREEN

                print(f"{DIM}Last update: {self.last_update.strftime('%H:%M:%S.%f')[:-3]} "
                      f"({age_color}{age_seconds:.1f}s ago{RESET}{DIM}){RESET}")

                # Warning if data is stale
                if age_seconds > 30:
                    print(f"\n{RED}{BOLD}⚠️  WARNING: Data is stale (>30s old)! Is orderbook_tracker.py running with --influx?{RESET}")
                elif age_seconds > 10:
                    print(f"\n{YELLOW}⚠️  Caution: No new data for {age_seconds:.0f} seconds{RESET}")
        else:
            print(f"{YELLOW}Waiting for data...{RESET}")

        print(f"\n{CYAN}{'─'*80}{RESET}\n")

        # Draw chart
        chart_lines = self._draw_chart()
        for line in chart_lines:
            print(line)

        # Draw whale activity panel
        print(f"\n{CYAN}{'─'*80}{RESET}")
        self._draw_whale_panel()

        # Footer
        print(f"\n{CYAN}{'─'*80}{RESET}")
        uptime = datetime.now() - self.start_time
        uptime_str = str(uptime).split('.')[0]

        # Data source status
        if self.last_update:
            age = datetime.now(self.last_update.tzinfo) - self.last_update
            age_seconds = age.total_seconds()
            if age_seconds > 30:
                status = f"{RED}⚠️ STALE{RESET}"
            elif age_seconds > 10:
                status = f"{YELLOW}⚠️ DELAYED{RESET}"
            else:
                status = f"{GREEN}✓ LIVE{RESET}"
        else:
            status = f"{RED}⚠️ NO DATA{RESET}"

        print(f"{DIM}Updates: {self.total_updates} | Uptime: {uptime_str} | "
              f"History: {len(self.price_history)} points ({self.history_seconds}s) | "
              f"Refresh: {self.refresh_interval}s | Status: {status}{RESET}")
        print(f"{DIM}Press Ctrl+C to exit{RESET}")

    async def run(self):
        """Main monitoring loop"""
        print(f"{CYAN}Starting price chart for {self.symbol}...{RESET}")
        print(f"{DIM}Connecting to InfluxDB...{RESET}\n")

        try:
            while True:
                # Fetch history for chart
                self._fetch_price_history()

                # Fetch whale events
                self._fetch_whale_events()

                # Fetch latest data for current price
                self._fetch_latest_data()

                # Display
                self._display()

                # Wait
                await asyncio.sleep(self.refresh_interval)

        except KeyboardInterrupt:
            print(f"\n\n{CYAN}{'═'*80}{RESET}")
            print(f"{BOLD}{WHITE}Session Summary{RESET}")
            print(f"{CYAN}{'═'*80}{RESET}")

            uptime = datetime.now() - self.start_time
            print(f"Total Runtime: {str(uptime).split('.')[0]}")
            print(f"Total Updates: {self.total_updates}")

            if len(self.price_history) >= 2:
                prices = [p for t, p in self.price_history]
                print(f"\nPrice Statistics:")
                print(f"  High: ${max(prices):,.2f}")
                print(f"  Low:  ${min(prices):,.2f}")
                print(f"  Range: ${max(prices) - min(prices):,.2f}")

            print(f"{CYAN}{'═'*80}{RESET}\n")

        finally:
            self.client.close()


def main():
    parser = argparse.ArgumentParser(
        description='Monitor MEXC order book prices with ASCII chart',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f'''
Examples:
  {CYAN}# Monitor BTC price with default settings{RESET}
  python orderbook_monitor.py BTC_USDT

  {CYAN}# Monitor with custom refresh rate{RESET}
  python orderbook_monitor.py BTC_USDT --refresh 2.0

  {CYAN}# Monitor with 10 minutes of history{RESET}
  python orderbook_monitor.py BTC_USDT --history 600

  {CYAN}# Custom chart size{RESET}
  python orderbook_monitor.py BTC_USDT --width 100 --height 25

{DIM}Note: Requires orderbook_tracker.py to be running with --influx flag{RESET}
        '''
    )

    parser.add_argument('symbol', type=str, help='Trading pair symbol (e.g., BTC_USDT)')
    parser.add_argument(
        '--refresh',
        type=float,
        default=1.0,
        help='Refresh interval in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--history',
        type=int,
        default=300,
        help='History window in seconds (default: 300)'
    )
    parser.add_argument(
        '--width',
        type=int,
        default=120,
        help='Chart width in characters (default: 120)'
    )
    parser.add_argument(
        '--height',
        type=int,
        default=30,
        help='Chart height in rows (default: 30)'
    )

    args = parser.parse_args()

    # Validate symbol format
    if '_' not in args.symbol:
        print(f"{RED}Error: Symbol must be in format BASE_QUOTE (e.g., BTC_USDT){RESET}")
        sys.exit(1)

    # Create and run monitor
    monitor = OrderBookPriceMonitor(
        args.symbol,
        args.refresh,
        args.width,
        args.height,
        args.history
    )
    asyncio.run(monitor.run())


if __name__ == '__main__':
    main()
