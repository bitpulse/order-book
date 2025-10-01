#!/usr/bin/env python3
"""
MEXC Futures Order Book History
Shows new bids in green and new asks in red as a scrolling history
"""

import json
import asyncio
import websockets
import argparse
import logging
from datetime import datetime
from typing import Dict, Set, Tuple, List
import signal
import sys
from collections import deque
import time

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
CLEAR_LINE = '\033[K'

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrderBookHistory:
    """Order book history tracker with scrolling display"""

    def __init__(self, symbol: str, limit: int = 10, min_volume: float = 0, min_usd: float = 0):
        """
        Initialize order history tracker

        Args:
            symbol: Trading pair symbol
            limit: Order book depth to monitor
            min_volume: Minimum volume to display (filter noise)
            min_usd: Minimum USD value to display (filter noise)
        """
        self.ws_url = "wss://contract.mexc.com/edge"
        self.symbol = symbol.upper()
        self.limit = limit if limit in [5, 10, 20] else 10
        self.min_volume = min_volume
        self.min_usd = min_usd
        self.ws = None
        self.running = False

        # Track order book state
        self.previous_bids = {}
        self.previous_asks = {}

        # History tracking
        self.history = deque(maxlen=1000)  # Keep last 1000 events

        # Statistics
        self.stats = {
            'updates': 0,
            'new_bids': 0,
            'new_asks': 0,
            'removed_bids': 0,
            'removed_asks': 0,
            'total_bid_volume': 0,
            'total_ask_volume': 0
        }

        self.last_best_bid = 0
        self.last_best_ask = 0
        self.session_start = time.time()

    async def _send_ping(self, ws):
        """Keep connection alive"""
        while self.running:
            try:
                await asyncio.sleep(15)
                if ws and ws.open:
                    await ws.ping()
            except Exception as e:
                logger.error(f"Ping error: {e}")
                break

    async def _subscribe(self, ws):
        """Subscribe to order book"""
        subscription = {
            "method": "sub.depth.full",
            "param": {
                "symbol": self.symbol,
                "limit": self.limit
            }
        }
        await ws.send(json.dumps(subscription))
        logger.info(f"Subscribed to {self.symbol} order book")

    def _format_price(self, price: float) -> str:
        """Format price based on magnitude"""
        if price >= 1000:
            return f"{price:.2f}"
        elif price >= 1:
            return f"{price:.4f}"
        else:
            return f"{price:.6f}"

    def _format_volume(self, volume: float) -> str:
        """Format volume with abbreviations"""
        if volume >= 1_000_000:
            return f"{volume/1_000_000:.1f}m"
        elif volume >= 1_000:
            return f"{volume/1_000:.1f}k"
        else:
            return f"{volume:.1f}"

    def _format_usd_value(self, price: float, volume: float) -> str:
        """Format USD value"""
        value = price * volume
        if value >= 1_000_000:
            return f"${value/1_000_000:.1f}m"
        elif value >= 1_000:
            return f"${value/1_000:.1f}k"
        else:
            return f"${value:.0f}"

    def _print_header(self):
        """Print session header"""
        runtime = time.time() - self.session_start
        print(f"\n{BOLD}{CYAN}{'='*80}{RESET}")
        print(f"{BOLD}{WHITE}MEXC Order Book History - {self.symbol}{RESET}")
        print(f"Runtime: {runtime:.0f}s | Updates: {self.stats['updates']} | "
              f"{GREEN}New Bids: {self.stats['new_bids']}{RESET} | "
              f"{RED}New Asks: {self.stats['new_asks']}{RESET}")
        print(f"{CYAN}{'='*80}{RESET}")
        print(f"{DIM}{'Time':<12} {'Type':<12} {'Price':<12} {'Volume':<12} {'Value':<12} {'Distance':<10} {'Info'}{RESET}")
        print(f"{DIM}{'-'*90}{RESET}")

    def _process_orderbook(self, data: Dict):
        """Process order book and detect new orders"""
        timestamp = data.get('ts', time.time() * 1000)
        dt = datetime.fromtimestamp(timestamp / 1000)
        time_str = dt.strftime('%H:%M:%S.%f')[:-3]

        # Parse current order book
        # MEXC format: [price, volume, order_count]
        bids = data.get('bids', [])
        asks = data.get('asks', [])

        current_bids = {float(bid[0]): float(bid[1]) for bid in bids if len(bid) >= 3}
        current_asks = {float(ask[0]): float(ask[1]) for ask in asks if len(ask) >= 3}

        # Track best bid/ask
        best_bid = max(current_bids.keys()) if current_bids else 0
        best_ask = min(current_asks.keys()) if current_asks else 0

        # Calculate mid-price
        mid_price = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0

        # Detect new bids
        for price, volume in current_bids.items():
            if volume < self.min_volume:
                continue

            usd_value = price * volume
            if usd_value < self.min_usd:
                continue

            if price not in self.previous_bids:
                # New bid appeared
                self.stats['new_bids'] += 1
                self.stats['total_bid_volume'] += volume

                # Calculate distance from mid-price
                if mid_price > 0:
                    distance_from_mid = ((mid_price - price) / mid_price) * 100
                    distance_str = f"{distance_from_mid:+.3f}%"
                else:
                    distance_str = "N/A"

                # Determine position relative to best bid
                position = "BEST" if price == best_bid else ""

                print(f"{time_str:<12} "
                      f"{GREEN}{'NEW BID':<12}{RESET} "
                      f"{GREEN}{self._format_price(price):<12}{RESET} "
                      f"{self._format_volume(volume):<12} "
                      f"{self._format_usd_value(price, volume):<12} "
                      f"{CYAN}{distance_str:<10}{RESET} "
                      f"{DIM}{position}{RESET}")

                self.history.append({
                    'time': time_str,
                    'type': 'new_bid',
                    'price': price,
                    'volume': volume
                })

            elif self.previous_bids[price] < volume:
                # Bid volume increased significantly
                increase = volume - self.previous_bids[price]
                if increase >= self.min_volume:
                    # Calculate distance from mid-price
                    if mid_price > 0:
                        distance_from_mid = ((mid_price - price) / mid_price) * 100
                        distance_str = f"{distance_from_mid:+.3f}%"
                    else:
                        distance_str = "N/A"

                    print(f"{time_str:<12} "
                          f"{GREEN}{'BID ↑':<12}{RESET} "
                          f"{self._format_price(price):<12} "
                          f"+{self._format_volume(increase):<11} "
                          f"{self._format_usd_value(price, increase):<12} "
                          f"{CYAN}{distance_str:<10}{RESET} "
                          f"{DIM}(total: {self._format_volume(volume)}){RESET}")

        # Detect removed bids
        for price, volume in self.previous_bids.items():
            if price not in current_bids and volume >= self.min_volume:
                self.stats['removed_bids'] += 1
                print(f"{time_str:<12} "
                      f"{DIM}{'BID REMOVED':<12}{RESET} "
                      f"{DIM}{self._format_price(price):<12}{RESET} "
                      f"{DIM}-{self._format_volume(volume):<11}{RESET} "
                      f"{DIM}{self._format_usd_value(price, volume):<12}{RESET}")

        # Detect new asks
        for price, volume in current_asks.items():
            if volume < self.min_volume:
                continue

            usd_value = price * volume
            if usd_value < self.min_usd:
                continue

            if price not in self.previous_asks:
                # New ask appeared
                self.stats['new_asks'] += 1
                self.stats['total_ask_volume'] += volume

                # Calculate distance from mid-price
                if mid_price > 0:
                    distance_from_mid = ((price - mid_price) / mid_price) * 100
                    distance_str = f"{distance_from_mid:+.3f}%"
                else:
                    distance_str = "N/A"

                # Determine position relative to best ask
                position = "BEST" if price == best_ask else ""

                print(f"{time_str:<12} "
                      f"{RED}{'NEW ASK':<12}{RESET} "
                      f"{RED}{self._format_price(price):<12}{RESET} "
                      f"{self._format_volume(volume):<12} "
                      f"{self._format_usd_value(price, volume):<12} "
                      f"{CYAN}{distance_str:<10}{RESET} "
                      f"{DIM}{position}{RESET}")

                self.history.append({
                    'time': time_str,
                    'type': 'new_ask',
                    'price': price,
                    'volume': volume
                })

            elif self.previous_asks[price] < volume:
                # Ask volume increased significantly
                increase = volume - self.previous_asks[price]
                if increase >= self.min_volume:
                    # Calculate distance from mid-price
                    if mid_price > 0:
                        distance_from_mid = ((price - mid_price) / mid_price) * 100
                        distance_str = f"{distance_from_mid:+.3f}%"
                    else:
                        distance_str = "N/A"

                    print(f"{time_str:<12} "
                          f"{RED}{'ASK ↑':<12}{RESET} "
                          f"{self._format_price(price):<12} "
                          f"+{self._format_volume(increase):<11} "
                          f"{self._format_usd_value(price, increase):<12} "
                          f"{CYAN}{distance_str:<10}{RESET} "
                          f"{DIM}(total: {self._format_volume(volume)}){RESET}")

        # Detect removed asks
        for price, volume in self.previous_asks.items():
            if price not in current_asks and volume >= self.min_volume:
                self.stats['removed_asks'] += 1
                print(f"{time_str:<12} "
                      f"{DIM}{'ASK REMOVED':<12}{RESET} "
                      f"{DIM}{self._format_price(price):<12}{RESET} "
                      f"{DIM}-{self._format_volume(volume):<11}{RESET} "
                      f"{DIM}{self._format_usd_value(price, volume):<12}{RESET}")

        # Check for spread changes
        if best_bid != self.last_best_bid or best_ask != self.last_best_ask:
            if best_bid and best_ask:
                spread = best_ask - best_bid
                spread_pct = (spread / best_ask) * 100

                # Only show significant spread changes
                if self.last_best_bid and self.last_best_ask:
                    old_spread = self.last_best_ask - self.last_best_bid
                    spread_change = spread - old_spread
                    if abs(spread_change) > 0.00001:
                        color = GREEN if spread_change < 0 else RED if spread_change > 0 else WHITE
                        print(f"{time_str:<12} "
                              f"{YELLOW}{'SPREAD':<12}{RESET} "
                              f"{self._format_price(spread):<12} "
                              f"{spread_pct:.3f}%".ljust(12) + " "
                              f"{color}{'↓' if spread_change < 0 else '↑'} {abs(spread_change):.6f}{RESET}")

        # Update state
        self.previous_bids = current_bids.copy()
        self.previous_asks = current_asks.copy()
        self.last_best_bid = best_bid
        self.last_best_ask = best_ask
        self.stats['updates'] += 1

        # Print summary every 100 updates
        if self.stats['updates'] % 100 == 0:
            self._print_summary()

    def _print_summary(self):
        """Print summary statistics"""
        print(f"\n{CYAN}{'─'*80}{RESET}")
        print(f"{BOLD}Summary after {self.stats['updates']} updates:{RESET}")
        print(f"  {GREEN}New Bids: {self.stats['new_bids']} "
              f"(Volume: {self._format_volume(self.stats['total_bid_volume'])}){RESET}")
        print(f"  {RED}New Asks: {self.stats['new_asks']} "
              f"(Volume: {self._format_volume(self.stats['total_ask_volume'])}){RESET}")
        print(f"  Removed: {self.stats['removed_bids']} bids, {self.stats['removed_asks']} asks")
        print(f"{CYAN}{'─'*80}{RESET}\n")

    async def connect(self):
        """Connect and start tracking"""
        self.running = True
        self._print_header()

        while self.running:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=15,
                    compression=None
                ) as ws:
                    self.ws = ws
                    logger.info("Connected to MEXC WebSocket")

                    await self._subscribe(ws)

                    # Start ping task
                    ping_task = asyncio.create_task(self._send_ping(ws))

                    # Process messages
                    async for message in ws:
                        try:
                            data = json.loads(message)

                            if data.get('channel') == 'push.depth.full':
                                self._process_orderbook(data.get('data', {}))
                            elif 'code' in data:
                                if data['code'] != 0:
                                    logger.error(f"Error: {data.get('msg', '')}")
                                else:
                                    logger.info(f"Success: {data.get('msg', 'Subscribed')}")

                        except json.JSONDecodeError:
                            logger.error("Failed to parse message")
                        except Exception as e:
                            logger.error(f"Processing error: {e}")

                    ping_task.cancel()

            except websockets.exceptions.ConnectionClosed:
                print(f"{YELLOW}Connection closed, reconnecting...{RESET}")
                if self.running:
                    await asyncio.sleep(5)
            except Exception as e:
                print(f"{RED}Connection error: {e}{RESET}")
                if self.running:
                    await asyncio.sleep(5)

    async def disconnect(self):
        """Disconnect and show final stats"""
        self.running = False
        if self.ws:
            await self.ws.close()

        runtime = time.time() - self.session_start
        print(f"\n{BOLD}{CYAN}{'='*80}{RESET}")
        print(f"{BOLD}{WHITE}Final Statistics - Runtime: {runtime:.0f}s{RESET}")
        print(f"{CYAN}{'='*80}{RESET}")
        print(f"Total Updates: {self.stats['updates']}")
        print(f"{GREEN}Total New Bids: {self.stats['new_bids']} "
              f"(Volume: {self._format_volume(self.stats['total_bid_volume'])}){RESET}")
        print(f"{RED}Total New Asks: {self.stats['new_asks']} "
              f"(Volume: {self._format_volume(self.stats['total_ask_volume'])}){RESET}")
        print(f"Removed Orders - Bids: {self.stats['removed_bids']} | Asks: {self.stats['removed_asks']}")

        # Save history to file
        if len(self.history) > 0:
            filename = f"order_history_{self.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump(list(self.history), f, indent=2)
            print(f"\nHistory saved to {filename}")


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='MEXC order book history tracker - shows new orders as they appear'
    )
    parser.add_argument(
        'symbol',
        type=str,
        help='Trading pair (e.g., BTC_USDT, ETH_USDT)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        choices=[5, 10, 20],
        default=10,
        help='Order book depth to monitor (default: 10)'
    )
    parser.add_argument(
        '--min-volume',
        type=float,
        default=0,
        help='Minimum volume to display (filters noise)'
    )
    parser.add_argument(
        '--min-usd',
        type=float,
        default=0,
        help='Minimum USD value to display'
    )

    args = parser.parse_args()

    # Create history tracker
    tracker = OrderBookHistory(
        args.symbol,
        args.limit,
        min_volume=args.min_volume,
        min_usd=args.min_usd
    )

    # Handle shutdown
    def signal_handler(signum, frame):
        logger.info("Shutdown signal received")
        asyncio.create_task(tracker.disconnect())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"\n{BOLD}{CYAN}Starting Order Book History for {args.symbol}{RESET}")
    print(f"{GREEN}Green = New Bids/Buy Orders{RESET}")
    print(f"{RED}Red = New Asks/Sell Orders{RESET}")
    print(f"{DIM}Dim = Removed Orders{RESET}")
    print(f"\nPress Ctrl+C to exit")

    try:
        await tracker.connect()
    except KeyboardInterrupt:
        pass
    finally:
        await tracker.disconnect()


if __name__ == "__main__":
    asyncio.run(main())