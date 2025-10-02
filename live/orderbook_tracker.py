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
import csv
import os
import aiohttp
from dotenv import load_dotenv

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

    def __init__(self, symbol: str, limit: int = 10, min_volume: float = 0,
                 min_usd: float = 0, max_usd: float = None,
                 min_distance_pct: float = None, max_distance_pct: float = None,
                 telegram_enabled: bool = False, telegram_bot_token: str = None,
                 telegram_chat_id: str = None):
        """
        Initialize order history tracker

        Args:
            symbol: Trading pair symbol
            limit: Order book depth to monitor
            min_volume: Minimum volume to display (filter noise)
            min_usd: Minimum USD value to display
            max_usd: Maximum USD value to display
            min_distance_pct: Minimum distance from mid-price in %
            max_distance_pct: Maximum distance from mid-price in %
            telegram_enabled: Enable Telegram notifications
            telegram_bot_token: Telegram bot token
            telegram_chat_id: Telegram chat ID
        """
        self.ws_url = "wss://contract.mexc.com/edge"
        self.symbol = symbol.upper()
        self.limit = limit if limit in [5, 10, 20] else 10
        self.min_volume = min_volume
        self.min_usd = min_usd
        self.max_usd = max_usd
        self.min_distance_pct = min_distance_pct
        self.max_distance_pct = max_distance_pct
        self.ws = None
        self.running = False

        # Telegram settings
        self.telegram_enabled = telegram_enabled
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.telegram_session = None

        # Track order book state
        self.previous_bids = {}
        self.previous_asks = {}

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

        # CSV logging
        self.csv_filename = f"logs/orderbook_{self.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.csv_file = None
        self.csv_writer = None

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

    async def _send_telegram_message(self, message: str):
        """Send message to Telegram channel"""
        if not self.telegram_enabled or not self.telegram_bot_token or not self.telegram_chat_id:
            return

        try:
            if not self.telegram_session:
                self.telegram_session = aiohttp.ClientSession()

            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }

            async with self.telegram_session.post(url, json=data) as response:
                if response.status != 200:
                    logger.warning(f"Telegram API error: {response.status}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def _print_header(self):
        """Print session header"""
        runtime = time.time() - self.session_start
        print(f"\n{BOLD}{CYAN}{'='*80}{RESET}")
        print(f"{BOLD}{WHITE}MEXC Order Book History - {self.symbol}{RESET}")
        print(f"Runtime: {runtime:.0f}s | Updates: {self.stats['updates']} | "
              f"{GREEN}New Bids: {self.stats['new_bids']}{RESET} | "
              f"{RED}New Asks: {self.stats['new_asks']}{RESET}")
        print(f"{CYAN}{'='*100}{RESET}")
        print(f"{DIM}{'Time':<12} {'Type':<12} {'Price':<12} {'Volume':<12} {'Value':<12} {'Distance':<10} {'Level':<7} {'Orders':<7} {'Total'}{RESET}")
        print(f"{DIM}{'-'*110}{RESET}")

    def _process_orderbook(self, data: Dict):
        """Process order book and detect new orders"""
        timestamp = data.get('ts', time.time() * 1000)
        dt = datetime.fromtimestamp(timestamp / 1000)
        time_str = dt.strftime('%H:%M:%S.%f')[:-3]

        # Parse current order book
        # MEXC format: [price, volume, order_count]
        # Field 0: price
        # Field 1: total volume (quantity)
        # Field 2: number of orders at this price
        bids = data.get('bids', [])
        asks = data.get('asks', [])

        # Store volume, order_count, and level
        # Bids are sorted high to low (best first), asks are sorted low to high (best first)
        current_bids = {}
        for level, bid in enumerate(bids, start=1):
            if len(bid) >= 3:
                price = float(bid[0])
                volume = float(bid[1])
                order_count = int(bid[2])
                current_bids[price] = (volume, order_count, level)

        current_asks = {}
        for level, ask in enumerate(asks, start=1):
            if len(ask) >= 3:
                price = float(ask[0])
                volume = float(ask[1])
                order_count = int(ask[2])
                current_asks[price] = (volume, order_count, level)

        # Track best bid/ask
        best_bid = max(current_bids.keys()) if current_bids else 0
        best_ask = min(current_asks.keys()) if current_asks else 0

        # Calculate mid-price
        mid_price = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0

        # Detect new bids
        for price, (volume, order_count, level) in current_bids.items():
            if volume < self.min_volume:
                continue

            usd_value = price * volume
            if usd_value < self.min_usd:
                continue
            if self.max_usd is not None and usd_value > self.max_usd:
                continue

            if price not in self.previous_bids:
                # New bid level appeared
                self.stats['new_bids'] += 1
                self.stats['total_bid_volume'] += volume

                # Calculate distance from mid-price
                if mid_price > 0:
                    distance_from_mid = ((mid_price - price) / mid_price) * 100
                    distance_str = f"{distance_from_mid:+.3f}%"
                else:
                    distance_from_mid = 0
                    distance_str = "N/A"

                # Filter by distance
                if self.min_distance_pct is not None and abs(distance_from_mid) < self.min_distance_pct:
                    continue
                if self.max_distance_pct is not None and abs(distance_from_mid) > self.max_distance_pct:
                    continue

                # Determine position relative to best bid
                position = "BEST" if price == best_bid else ""

                level_str = "BEST" if level == 1 else f"#{level}"
                print(f"{time_str:<12} "
                      f"{GREEN}{'BID':<12}{RESET} "
                      f"{GREEN}{self._format_price(price):<12}{RESET} "
                      f"{self._format_volume(volume):<12} "
                      f"{self._format_usd_value(price, volume):<12} "
                      f"{CYAN}{distance_str:<10}{RESET} "
                      f"{level_str:<7} "
                      f"{order_count:<7} "
                      f"{DIM}{self._format_volume(volume)}{RESET}")

                # Log to CSV
                distance_pct = distance_from_mid if mid_price > 0 else 0
                self._log_to_csv('new', 'bid', price, volume, usd_value,
                                distance_pct, best_bid, best_ask, f"total:{volume}", level, order_count)

                # Send Telegram notification
                if self.telegram_enabled:
                    emoji = "🟢"
                    side_text = "BID"
                    level_text = "BEST" if level == 1 else f"#{level}"
                    telegram_msg = (
                        f"{emoji} <b>{side_text}</b> {self.symbol}\n"
                        f"Time: <code>{time_str}</code>\n"
                        f"Price: <code>{self._format_price(price)}</code>\n"
                        f"Level: <b>{level_text}</b>\n"
                        f"Orders: <code>{order_count}</code>\n"
                        f"Volume: <code>{self._format_volume(volume)}</code>\n"
                        f"Value: <b>{self._format_usd_value(price, volume)}</b>\n"
                        f"Distance: <code>{distance_str}</code>"
                    )
                    asyncio.create_task(self._send_telegram_message(telegram_msg))

            elif price in self.previous_bids and self.previous_bids[price][0] != volume:
                # Bid volume changed
                prev_volume = self.previous_bids[price][0]
                change = volume - prev_volume
                if abs(change) >= self.min_volume:
                    change_usd = price * abs(change)
                    if change_usd < self.min_usd:
                        continue
                    if self.max_usd is not None and change_usd > self.max_usd:
                        continue

                    # Calculate distance from mid-price
                    if mid_price > 0:
                        distance_from_mid = ((mid_price - price) / mid_price) * 100
                        distance_str = f"{distance_from_mid:+.3f}%"
                    else:
                        distance_from_mid = 0
                        distance_str = "N/A"

                    # Filter by distance
                    if self.min_distance_pct is not None and abs(distance_from_mid) < self.min_distance_pct:
                        continue
                    if self.max_distance_pct is not None and abs(distance_from_mid) > self.max_distance_pct:
                        continue

                    if change > 0:
                        # Volume increased
                        level_str = "BEST" if level == 1 else f"#{level}"
                        print(f"{time_str:<12} "
                              f"{GREEN}{'BID ↑':<12}{RESET} "
                              f"{self._format_price(price):<12} "
                              f"+{self._format_volume(change):<11} "
                              f"{self._format_usd_value(price, change):<12} "
                              f"{CYAN}{distance_str:<10}{RESET} "
                              f"{level_str:<7} "
                              f"{order_count:<7} "
                              f"{DIM}{self._format_volume(volume)}{RESET}")

                        # Log to CSV
                        distance_pct = distance_from_mid if mid_price > 0 else 0
                        self._log_to_csv('increase', 'bid', price, change, change_usd,
                                        distance_pct, best_bid, best_ask, f"total:{volume}", level, order_count)

                        # Send Telegram notification
                        if self.telegram_enabled:
                            emoji = "🟢⬆️"
                            side_text = "BID ↑"
                            level_text = "BEST" if level == 1 else f"#{level}"
                            telegram_msg = (
                                f"{emoji} <b>{side_text}</b> {self.symbol}\n"
                                f"Time: <code>{time_str}</code>\n"
                                f"Price: <code>{self._format_price(price)}</code>\n"
                                f"Level: <b>{level_text}</b>\n"
                                f"Orders: <code>{order_count}</code>\n"
                                f"Change: <code>+{self._format_volume(change)}</code>\n"
                                f"Value: <b>{self._format_usd_value(price, change)}</b>\n"
                                f"Total: <code>{self._format_volume(volume)}</code>\n"
                                f"Distance: <code>{distance_str}</code>"
                            )
                            asyncio.create_task(self._send_telegram_message(telegram_msg))
                    else:
                        # Volume decreased
                        level_str = "BEST" if level == 1 else f"#{level}"
                        print(f"{time_str:<12} "
                              f"{DIM}{'BID ↓':<12}{RESET} "
                              f"{DIM}{self._format_price(price):<12}{RESET} "
                              f"{DIM}{self._format_volume(change):<11}{RESET} "
                              f"{DIM}{self._format_usd_value(price, abs(change)):<12}{RESET} "
                              f"{DIM}{distance_str:<10}{RESET} "
                              f"{DIM}{level_str:<7}{RESET} "
                              f"{DIM}{order_count:<7}{RESET} "
                              f"{DIM}{self._format_volume(volume)}{RESET}")

                        # Log to CSV
                        distance_pct = distance_from_mid if mid_price > 0 else 0
                        self._log_to_csv('decrease', 'bid', price, abs(change), change_usd,
                                        distance_pct, best_bid, best_ask, f"total:{volume}", level, order_count)

                        # Send Telegram notification
                        if self.telegram_enabled:
                            emoji = "⬇️"
                            side_text = "BID ↓"
                            level_text = "BEST" if level == 1 else f"#{level}"
                            telegram_msg = (
                                f"{emoji} <b>{side_text}</b> {self.symbol}\n"
                                f"Time: <code>{time_str}</code>\n"
                                f"Price: <code>{self._format_price(price)}</code>\n"
                                f"Level: <b>{level_text}</b>\n"
                                f"Orders: <code>{order_count}</code>\n"
                                f"Change: <code>{self._format_volume(change)}</code>\n"
                                f"Value: <b>{self._format_usd_value(price, abs(change))}</b>\n"
                                f"Total: <code>{self._format_volume(volume)}</code>\n"
                                f"Distance: <code>{distance_str}</code>"
                            )
                            asyncio.create_task(self._send_telegram_message(telegram_msg))

        # Detect new asks
        for price, (volume, order_count, level) in current_asks.items():
            if volume < self.min_volume:
                continue

            usd_value = price * volume
            if usd_value < self.min_usd:
                continue
            if self.max_usd is not None and usd_value > self.max_usd:
                continue

            if price not in self.previous_asks:
                # New ask level appeared
                self.stats['new_asks'] += 1
                self.stats['total_ask_volume'] += volume

                # Calculate distance from mid-price
                if mid_price > 0:
                    distance_from_mid = ((price - mid_price) / mid_price) * 100
                    distance_str = f"{distance_from_mid:+.3f}%"
                else:
                    distance_from_mid = 0
                    distance_str = "N/A"

                # Filter by distance
                if self.min_distance_pct is not None and abs(distance_from_mid) < self.min_distance_pct:
                    continue
                if self.max_distance_pct is not None and abs(distance_from_mid) > self.max_distance_pct:
                    continue

                # Determine position relative to best ask
                position = "BEST" if price == best_ask else ""

                level_str = "BEST" if level == 1 else f"#{level}"
                print(f"{time_str:<12} "
                      f"{RED}{'ASK':<12}{RESET} "
                      f"{RED}{self._format_price(price):<12}{RESET} "
                      f"{self._format_volume(volume):<12} "
                      f"{self._format_usd_value(price, volume):<12} "
                      f"{CYAN}{distance_str:<10}{RESET} "
                      f"{level_str:<7} "
                      f"{order_count:<7} "
                      f"{DIM}{self._format_volume(volume)}{RESET}")

                # Log to CSV
                distance_pct = distance_from_mid if mid_price > 0 else 0
                self._log_to_csv('new', 'ask', price, volume, usd_value,
                                distance_pct, best_bid, best_ask, f"total:{volume}", level, order_count)

                # Send Telegram notification
                if self.telegram_enabled:
                    emoji = "🔴"
                    side_text = "ASK"
                    level_text = "BEST" if level == 1 else f"#{level}"
                    telegram_msg = (
                        f"{emoji} <b>{side_text}</b> {self.symbol}\n"
                        f"Time: <code>{time_str}</code>\n"
                        f"Price: <code>{self._format_price(price)}</code>\n"
                        f"Level: <b>{level_text}</b>\n"
                        f"Orders: <code>{order_count}</code>\n"
                        f"Volume: <code>{self._format_volume(volume)}</code>\n"
                        f"Value: <b>{self._format_usd_value(price, volume)}</b>\n"
                        f"Distance: <code>{distance_str}</code>"
                    )
                    asyncio.create_task(self._send_telegram_message(telegram_msg))

            elif price in self.previous_asks and self.previous_asks[price][0] != volume:
                # Ask volume changed
                prev_volume = self.previous_asks[price][0]
                change = volume - prev_volume
                if abs(change) >= self.min_volume:
                    change_usd = price * abs(change)
                    if change_usd < self.min_usd:
                        continue
                    if self.max_usd is not None and change_usd > self.max_usd:
                        continue

                    # Calculate distance from mid-price
                    if mid_price > 0:
                        distance_from_mid = ((price - mid_price) / mid_price) * 100
                        distance_str = f"{distance_from_mid:+.3f}%"
                    else:
                        distance_from_mid = 0
                        distance_str = "N/A"

                    # Filter by distance
                    if self.min_distance_pct is not None and abs(distance_from_mid) < self.min_distance_pct:
                        continue
                    if self.max_distance_pct is not None and abs(distance_from_mid) > self.max_distance_pct:
                        continue

                    if change > 0:
                        # Volume increased
                        level_str = "BEST" if level == 1 else f"#{level}"
                        print(f"{time_str:<12} "
                              f"{RED}{'ASK ↑':<12}{RESET} "
                              f"{self._format_price(price):<12} "
                              f"+{self._format_volume(change):<11} "
                              f"{self._format_usd_value(price, change):<12} "
                              f"{CYAN}{distance_str:<10}{RESET} "
                              f"{level_str:<7} "
                              f"{order_count:<7} "
                              f"{DIM}{self._format_volume(volume)}{RESET}")

                        # Log to CSV
                        distance_pct = distance_from_mid if mid_price > 0 else 0
                        self._log_to_csv('increase', 'ask', price, change, change_usd,
                                        distance_pct, best_bid, best_ask, f"total:{volume}", level, order_count)

                        # Send Telegram notification
                        if self.telegram_enabled:
                            emoji = "🔴⬆️"
                            side_text = "ASK ↑"
                            level_text = "BEST" if level == 1 else f"#{level}"
                            telegram_msg = (
                                f"{emoji} <b>{side_text}</b> {self.symbol}\n"
                                f"Time: <code>{time_str}</code>\n"
                                f"Price: <code>{self._format_price(price)}</code>\n"
                                f"Level: <b>{level_text}</b>\n"
                                f"Orders: <code>{order_count}</code>\n"
                                f"Change: <code>+{self._format_volume(change)}</code>\n"
                                f"Value: <b>{self._format_usd_value(price, change)}</b>\n"
                                f"Total: <code>{self._format_volume(volume)}</code>\n"
                                f"Distance: <code>{distance_str}</code>"
                            )
                            asyncio.create_task(self._send_telegram_message(telegram_msg))
                    else:
                        # Volume decreased
                        level_str = "BEST" if level == 1 else f"#{level}"
                        print(f"{time_str:<12} "
                              f"{DIM}{'ASK ↓':<12}{RESET} "
                              f"{DIM}{self._format_price(price):<12}{RESET} "
                              f"{DIM}{self._format_volume(change):<11}{RESET} "
                              f"{DIM}{self._format_usd_value(price, abs(change)):<12}{RESET} "
                              f"{DIM}{distance_str:<10}{RESET} "
                              f"{DIM}{level_str:<7}{RESET} "
                              f"{DIM}{order_count:<7}{RESET} "
                              f"{DIM}{self._format_volume(volume)}{RESET}")

                        # Log to CSV
                        distance_pct = distance_from_mid if mid_price > 0 else 0
                        self._log_to_csv('decrease', 'ask', price, abs(change), change_usd,
                                        distance_pct, best_bid, best_ask, f"total:{volume}", level, order_count)

                        # Send Telegram notification
                        if self.telegram_enabled:
                            emoji = "⬇️"
                            side_text = "ASK ↓"
                            level_text = "BEST" if level == 1 else f"#{level}"
                            telegram_msg = (
                                f"{emoji} <b>{side_text}</b> {self.symbol}\n"
                                f"Time: <code>{time_str}</code>\n"
                                f"Price: <code>{self._format_price(price)}</code>\n"
                                f"Level: <b>{level_text}</b>\n"
                                f"Orders: <code>{order_count}</code>\n"
                                f"Change: <code>{self._format_volume(change)}</code>\n"
                                f"Value: <b>{self._format_usd_value(price, abs(change))}</b>\n"
                                f"Total: <code>{self._format_volume(volume)}</code>\n"
                                f"Distance: <code>{distance_str}</code>"
                            )
                            asyncio.create_task(self._send_telegram_message(telegram_msg))

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

    def _init_csv(self):
        """Initialize CSV file for logging"""
        import os
        os.makedirs('logs', exist_ok=True)
        self.csv_file = open(self.csv_filename, 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        # Write header
        self.csv_writer.writerow([
            'timestamp', 'type', 'side', 'price', 'volume', 'usd_value',
            'distance_from_mid_pct', 'best_bid', 'best_ask', 'spread', 'level', 'order_count', 'info'
        ])
        self.csv_file.flush()

    def _log_to_csv(self, event_type: str, side: str, price: float, volume: float,
                    usd_value: float, distance_pct: float, best_bid: float,
                    best_ask: float, info: str = "", level: int = 0, order_count: int = 0):
        """Log event to CSV"""
        if self.csv_writer:
            spread = best_ask - best_bid if (best_bid and best_ask) else 0
            self.csv_writer.writerow([
                datetime.now().isoformat(),
                event_type,
                side,
                price,
                volume,
                usd_value,
                distance_pct,
                best_bid,
                best_ask,
                spread,
                level,
                order_count,
                info
            ])
            self.csv_file.flush()

    async def connect(self):
        """Connect and start tracking"""
        self.running = True
        self._init_csv()
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

        # Close Telegram session
        if self.telegram_session:
            await self.telegram_session.close()

        # Close CSV file
        if self.csv_file:
            self.csv_file.close()

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
        print(f"\n{CYAN}Data saved to: {self.csv_filename}{RESET}")


async def main():
    """Main function"""
    # Load environment variables from .env file
    load_dotenv()

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
    parser.add_argument(
        '--max-usd',
        type=float,
        default=None,
        help='Maximum USD value to display'
    )
    parser.add_argument(
        '--min-distance',
        type=float,
        default=None,
        help='Minimum distance from mid-price in %% (e.g., 0.1 for 0.1%%)'
    )
    parser.add_argument(
        '--max-distance',
        type=float,
        default=None,
        help='Maximum distance from mid-price in %% (e.g., 0.5 for 0.5%%)'
    )
    parser.add_argument(
        '--telegram',
        action='store_true',
        help='Enable Telegram notifications'
    )

    args = parser.parse_args()

    # Get Telegram credentials from environment if enabled
    telegram_bot_token = None
    telegram_chat_id = None
    if args.telegram:
        telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

        if not telegram_bot_token or not telegram_chat_id:
            print(f"{RED}Error: --telegram requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables{RESET}")
            sys.exit(1)

    # Create history tracker
    tracker = OrderBookHistory(
        args.symbol,
        args.limit,
        min_volume=args.min_volume,
        min_usd=args.min_usd,
        max_usd=args.max_usd,
        min_distance_pct=args.min_distance,
        max_distance_pct=args.max_distance,
        telegram_enabled=args.telegram,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id
    )

    # Handle shutdown
    def signal_handler(signum, frame):
        logger.info("Shutdown signal received")
        asyncio.create_task(tracker.disconnect())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"\n{BOLD}{CYAN}Starting Order Book History for {args.symbol}{RESET}")
    print(f"{GREEN}BID = Large buy order appeared or increased{RESET}")
    print(f"{RED}ASK = Large sell order appeared or increased{RESET}")
    print(f"\nPress Ctrl+C to exit")

    try:
        await tracker.connect()
    except KeyboardInterrupt:
        pass
    finally:
        await tracker.disconnect()


if __name__ == "__main__":
    asyncio.run(main())