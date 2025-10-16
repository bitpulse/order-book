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
import os
import aiohttp
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import ASYNCHRONOUS

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
    """Order book history tracker with scrolling display - tracks individual orders"""

    def __init__(self, symbol: str, limit: int = 20, min_volume: float = 0,
                 min_usd: float = 0, max_usd: float = None,
                 min_distance_pct: float = None, max_distance_pct: float = None,
                 telegram_enabled: bool = False, telegram_bot_token: str = None,
                 telegram_chat_id: str = None, track_trades: bool = True,
                 influx_enabled: bool = False, influx_url: str = None,
                 influx_token: str = None, influx_org: str = None, influx_bucket: str = None):
        """
        Initialize order history tracker

        Args:
            symbol: Trading pair symbol
            limit: Order book depth to monitor (5, 10, or 20) - default 20 (maximum)
            min_volume: Minimum volume to display (filter noise)
            min_usd: Minimum USD value to display
            max_usd: Maximum USD value to display
            min_distance_pct: Minimum distance from mid-price in %
            max_distance_pct: Maximum distance from mid-price in %
            telegram_enabled: Enable Telegram notifications
            telegram_bot_token: Telegram bot token
            telegram_chat_id: Telegram chat ID
            track_trades: Track trade executions (market orders)
            influx_enabled: Enable InfluxDB logging of all events
            influx_url: InfluxDB URL
            influx_token: InfluxDB token
            influx_org: InfluxDB organization
            influx_bucket: InfluxDB bucket
        """
        self.ws_url = "wss://contract.mexc.com/edge"
        self.rest_url = "https://contract.mexc.com"
        self.symbol = symbol.upper()
        self.limit = limit if limit in [5, 10, 20] else 20
        self.min_volume = min_volume
        self.min_usd = min_usd
        self.max_usd = max_usd
        self.min_distance_pct = min_distance_pct
        self.max_distance_pct = max_distance_pct
        self.ws = None
        self.running = False
        self.track_trades = track_trades

        # Telegram settings
        self.telegram_enabled = telegram_enabled
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.telegram_session = None

        # InfluxDB settings
        self.influx_enabled = influx_enabled
        self.influx_client = None
        self.influx_write_api = None
        self.influx_bucket = influx_bucket
        if self.influx_enabled and influx_url and influx_token and influx_org:
            try:
                self.influx_client = InfluxDBClient(url=influx_url, token=influx_token, org=influx_org)
                self.influx_write_api = self.influx_client.write_api(write_options=ASYNCHRONOUS)
                logger.info(f"InfluxDB client initialized: {influx_url}")
            except Exception as e:
                logger.error(f"Failed to initialize InfluxDB client: {e}")
                self.influx_enabled = False

        # Full order book state - track ALL price levels
        self.full_bids = {}  # {price: (volume, order_count)}
        self.full_asks = {}

        # Previous full order book state (for detecting truly new orders)
        self.previous_full_bids = {}
        self.previous_full_asks = {}

        # Previous visible window state (for comparison)
        self.previous_bids = {}
        self.previous_asks = {}

        # Version tracking for packet loss detection
        self.current_version = None
        self.version_errors = 0
        self.initialized = False

        # Trade tracking
        self.recent_trades = deque(maxlen=100)

        # Statistics
        self.stats = {
            'updates': 0,
            'new_bids': 0,
            'new_asks': 0,
            'removed_bids': 0,
            'removed_asks': 0,
            'total_bid_volume': 0,
            'total_ask_volume': 0,
            'trades': 0,
            'buy_volume': 0,
            'sell_volume': 0
        }

        self.last_best_bid = 0
        self.last_best_ask = 0
        self.session_start = time.time()

    async def _fetch_initial_snapshot(self):
        """Fetch initial order book snapshot from REST API"""
        try:
            url = f"{self.rest_url}/api/v1/contract/depth/{self.symbol}"

            if not self.telegram_session:
                self.telegram_session = aiohttp.ClientSession()

            async with self.telegram_session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    if data.get('success') and data.get('data'):
                        snapshot = data['data']

                        # Parse bids and asks
                        bids = snapshot.get('bids', [])
                        asks = snapshot.get('asks', [])

                        # Initialize full order book
                        for bid in bids:
                            if len(bid) >= 2:
                                price = float(bid[0])
                                volume = float(bid[1])
                                order_count = int(bid[2]) if len(bid) >= 3 else 1
                                if volume > 0:
                                    self.full_bids[price] = (volume, order_count)

                        for ask in asks:
                            if len(ask) >= 2:
                                price = float(ask[0])
                                volume = float(ask[1])
                                order_count = int(ask[2]) if len(ask) >= 3 else 1
                                if volume > 0:
                                    self.full_asks[price] = (volume, order_count)

                        self.initialized = True
                        logger.info(f"Initialized order book: {len(self.full_bids)} bids, {len(self.full_asks)} asks")
                        print(f"{GREEN}✓ Loaded initial snapshot: {len(self.full_bids)} bid levels, {len(self.full_asks)} ask levels{RESET}")
                        return True
                else:
                    logger.error(f"Failed to fetch snapshot: HTTP {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Error fetching snapshot: {e}")
            return False

    async def _send_ping(self, ws):
        """Keep connection alive with MEXC-specific ping"""
        while self.running:
            try:
                await asyncio.sleep(15)
                if ws and ws.open:
                    # Use MEXC's explicit ping format
                    await ws.send(json.dumps({"method": "ping"}))
            except Exception as e:
                logger.error(f"Ping error: {e}")
                break

    async def _subscribe(self, ws):
        """Subscribe to order book and trades"""
        # Subscribe to full depth updates
        depth_subscription = {
            "method": "sub.depth.full",
            "param": {
                "symbol": self.symbol,
                "limit": self.limit
            }
        }
        await ws.send(json.dumps(depth_subscription))
        logger.info(f"Subscribed to {self.symbol} order book depth")

        # Subscribe to trade executions if enabled
        if self.track_trades:
            await asyncio.sleep(0.1)  # Small delay between subscriptions
            trade_subscription = {
                "method": "sub.deal",
                "param": {
                    "symbol": self.symbol
                }
            }
            await ws.send(json.dumps(trade_subscription))
            logger.info(f"Subscribed to {self.symbol} trade executions")

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

    async def _process_trade(self, data: Dict):
        """Process trade execution data"""
        timestamp = data.get('t', time.time() * 1000)
        dt = datetime.fromtimestamp(timestamp / 1000)
        time_str = dt.strftime('%H:%M:%S.%f')[:-3]

        price = float(data.get('p', 0))
        volume = float(data.get('v', 0))
        trade_type = int(data.get('T', 0))  # 1=Buy, 2=Sell

        if volume < self.min_volume:
            return

        usd_value = price * volume
        if usd_value < self.min_usd:
            return
        if self.max_usd is not None and usd_value > self.max_usd:
            return

        # Calculate distance from mid-price
        mid_price = (self.last_best_bid + self.last_best_ask) / 2 if (self.last_best_bid and self.last_best_ask) else 0
        if mid_price > 0:
            distance_from_mid = ((price - mid_price) / mid_price) * 100
            distance_str = f"{distance_from_mid:+.3f}%"
        else:
            distance_from_mid = 0
            distance_str = "N/A"

        # Filter by distance
        if self.min_distance_pct is not None and abs(distance_from_mid) < self.min_distance_pct:
            return
        if self.max_distance_pct is not None and abs(distance_from_mid) > self.max_distance_pct:
            return

        # Update stats
        self.stats['trades'] += 1
        if trade_type == 1:
            self.stats['buy_volume'] += volume
        else:
            self.stats['sell_volume'] += volume

        # Store trade
        self.recent_trades.append({
            'time': timestamp,
            'price': price,
            'volume': volume,
            'type': trade_type
        })

        # Display trade
        if trade_type == 1:
            # Market BUY (aggressive buyer)
            print(f"{time_str:<12} "
                  f"{GREEN}{BOLD}{'MARKET BUY':<12}{RESET} "
                  f"{GREEN}{self._format_price(price):<12}{RESET} "
                  f"{self._format_volume(volume):<12} "
                  f"{BOLD}{self._format_usd_value(price, volume):<12}{RESET} "
                  f"{CYAN}{distance_str:<10}{RESET} "
                  f"{'---':<7} "
                  f"{'---':<7} "
                  f"{DIM}Aggressive{RESET}")
        else:
            # Market SELL (aggressive seller)
            print(f"{time_str:<12} "
                  f"{RED}{BOLD}{'MARKET SELL':<12}{RESET} "
                  f"{RED}{self._format_price(price):<12}{RESET} "
                  f"{self._format_volume(volume):<12} "
                  f"{BOLD}{self._format_usd_value(price, volume):<12}{RESET} "
                  f"{CYAN}{distance_str:<10}{RESET} "
                  f"{'---':<7} "
                  f"{'---':<7} "
                  f"{DIM}Aggressive{RESET}")

        # Log to CSV
        self._log_whale_event_to_influx(
            'market_buy' if trade_type == 1 else 'market_sell',
            'buy' if trade_type == 1 else 'sell',
            price, volume, usd_value, distance_from_mid,
            self.last_best_bid, self.last_best_ask,
            f"aggressive_trade", 0, 0
        )

        # Send Telegram notification
        if self.telegram_enabled:
            emoji = "🟢💥" if trade_type == 1 else "🔴💥"
            side_text = "MARKET BUY" if trade_type == 1 else "MARKET SELL"
            telegram_msg = (
                f"{emoji} <b>{side_text}</b> {self.symbol}\n"
                f"Time: <code>{time_str}</code>\n"
                f"Price: <code>{self._format_price(price)}</code>\n"
                f"Volume: <code>{self._format_volume(volume)}</code>\n"
                f"Value: <b>{self._format_usd_value(price, volume)}</b>\n"
                f"Distance: <code>{distance_str}</code>\n"
                f"Type: <i>Aggressive {('Buyer' if trade_type == 1 else 'Seller')}</i>"
            )
            asyncio.create_task(self._send_telegram_message(telegram_msg))

    def _print_header(self):
        """Print session header"""
        runtime = time.time() - self.session_start
        print(f"\n{BOLD}{CYAN}{'='*80}{RESET}")
        print(f"{BOLD}{WHITE}MEXC Order Book & Trade Tracker - {self.symbol}{RESET}")
        print(f"Runtime: {runtime:.0f}s | Updates: {self.stats['updates']} | "
              f"{GREEN}New Bids: {self.stats['new_bids']}{RESET} | "
              f"{RED}New Asks: {self.stats['new_asks']}{RESET} | "
              f"{YELLOW}Trades: {self.stats['trades']}{RESET}")
        print(f"{CYAN}{'='*120}{RESET}")
        print(f"{DIM}{'Time':<12} {'Type':<12} {'Price':<12} {'Volume':<12} {'Value':<12} {'Distance':<10} {'Level':<7} {'Orders':<7} {'Info'}{RESET}")
        print(f"{DIM}{'-'*120}{RESET}")

    def _process_orderbook(self, data: Dict):
        """Process order book and detect individual order changes with version tracking"""
        timestamp = data.get('ts', time.time() * 1000)
        dt = datetime.fromtimestamp(timestamp / 1000)
        time_str = dt.strftime('%H:%M:%S.%f')[:-3]

        # Version tracking for packet loss detection
        version = data.get('version')
        if version is not None:
            if self.current_version is not None:
                expected_version = self.current_version + 1
                if version != expected_version:
                    self.version_errors += 1
                    logger.debug(f"Version gap: Expected {expected_version}, got {version}")
                    # Version gaps are normal on high-volume pairs, just count them
            self.current_version = version

        # Parse current order book
        # MEXC format: [price, volume, order_count]
        # Field 0: price
        # Field 1: total volume (quantity)
        # Field 2: number of orders at this price
        bids = data.get('bids', [])
        asks = data.get('asks', [])

        # Parse incoming data into current visible window
        # Bids are sorted high to low (best first), asks are sorted low to high (best first)
        current_bids = {}
        for level, bid in enumerate(bids, start=1):
            if len(bid) >= 2:
                price = float(bid[0])
                volume = float(bid[1])
                order_count = int(bid[2]) if len(bid) >= 3 else 1

                # Update full order book state
                if volume == 0:
                    # Order removed - delete from full book
                    self.full_bids.pop(price, None)
                else:
                    # Update or add to full book
                    self.full_bids[price] = (volume, order_count)
                    current_bids[price] = (volume, order_count, level)

        current_asks = {}
        for level, ask in enumerate(asks, start=1):
            if len(ask) >= 2:
                price = float(ask[0])
                volume = float(ask[1])
                order_count = int(ask[2]) if len(ask) >= 3 else 1

                # Update full order book state
                if volume == 0:
                    # Order removed - delete from full book
                    self.full_asks.pop(price, None)
                else:
                    # Update or add to full book
                    self.full_asks[price] = (volume, order_count)
                    current_asks[price] = (volume, order_count, level)

        # Track best bid/ask
        best_bid = max(current_bids.keys()) if current_bids else 0
        best_ask = min(current_asks.keys()) if current_asks else 0

        # Calculate mid-price
        mid_price = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0

        # Log price data to InfluxDB (separate measurement)
        if best_bid and best_ask:
            self._log_price_to_influx(best_bid, best_ask)

        # Skip processing if not yet initialized (first snapshot)
        if not self.initialized:
            self.previous_bids = current_bids.copy()
            self.previous_asks = current_asks.copy()
            self.last_best_bid = best_bid
            self.last_best_ask = best_ask
            self.initialized = True
            return

        # Detect changes in BIDS (visible window)
        for price, (volume, order_count, level) in current_bids.items():
            if volume < self.min_volume:
                continue

            usd_value = price * volume
            if usd_value < self.min_usd:
                continue
            if self.max_usd is not None and usd_value > self.max_usd:
                continue

            if price not in self.previous_bids:
                # Bid level appeared in visible window - check if truly new or just moved into view
                was_in_full_book = price in self.previous_full_bids and self.stats['updates'] > 0

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

                if was_in_full_book:
                    # Order moved into visible window from below
                    event_type = "ENTERED TOP"
                    event_label = f"BID→TOP{self.limit}"
                    emoji = "🟢⬆️"
                    info_text = f"entered_top_{self.limit}"
                else:
                    # Truly new order placed
                    self.stats['new_bids'] += 1
                    self.stats['total_bid_volume'] += volume
                    event_type = "NEW BID"
                    event_label = "BID WALL"
                    emoji = "🟢"
                    info_text = f"new_order"

                level_str = "BEST" if level == 1 else f"#{level}"
                print(f"{time_str:<12} "
                      f"{GREEN}{event_label:<12}{RESET} "
                      f"{GREEN}{self._format_price(price):<12}{RESET} "
                      f"{self._format_volume(volume):<12} "
                      f"{BOLD}{self._format_usd_value(price, volume):<12}{RESET} "
                      f"{CYAN}{distance_str:<10}{RESET} "
                      f"{level_str:<7} "
                      f"{order_count:<7} "
                      f"{DIM}{info_text}{RESET}")

                # Log to CSV
                distance_pct = distance_from_mid if mid_price > 0 else 0
                self._log_whale_event_to_influx(event_type.lower().replace(' ', '_'), 'bid', price, volume, usd_value,
                                distance_pct, best_bid, best_ask, info_text, level, order_count)

                # Send Telegram notification
                if self.telegram_enabled:
                    telegram_msg = (
                        f"{emoji} <b>{event_type}</b> {self.symbol}\n"
                        f"Time: <code>{time_str}</code>\n"
                        f"Price: <code>{self._format_price(price)}</code>\n"
                        f"Level: <b>{level_str}</b>\n"
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
                        self._log_whale_event_to_influx('increase', 'bid', price, change, change_usd,
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
                        self._log_whale_event_to_influx('decrease', 'bid', price, abs(change), change_usd,
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
                # Ask level appeared in visible window - check if truly new or just moved into view
                was_in_full_book = price in self.previous_full_asks and self.stats['updates'] > 0

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

                if was_in_full_book:
                    # Order moved into visible window from above
                    event_type = "ENTERED TOP"
                    event_label = f"ASK→TOP{self.limit}"
                    emoji = "🔴⬆️"
                    info_text = f"entered_top_{self.limit}"
                else:
                    # Truly new order placed
                    self.stats['new_asks'] += 1
                    self.stats['total_ask_volume'] += volume
                    event_type = "NEW ASK"
                    event_label = "ASK WALL"
                    emoji = "🔴"
                    info_text = f"new_order"

                level_str = "BEST" if level == 1 else f"#{level}"
                print(f"{time_str:<12} "
                      f"{RED}{event_label:<12}{RESET} "
                      f"{RED}{self._format_price(price):<12}{RESET} "
                      f"{self._format_volume(volume):<12} "
                      f"{BOLD}{self._format_usd_value(price, volume):<12}{RESET} "
                      f"{CYAN}{distance_str:<10}{RESET} "
                      f"{level_str:<7} "
                      f"{order_count:<7} "
                      f"{DIM}{info_text}{RESET}")

                # Log to CSV
                distance_pct = distance_from_mid if mid_price > 0 else 0
                self._log_whale_event_to_influx(event_type.lower().replace(' ', '_'), 'ask', price, volume, usd_value,
                                distance_pct, best_bid, best_ask, info_text, level, order_count)

                # Send Telegram notification
                if self.telegram_enabled:
                    telegram_msg = (
                        f"{emoji} <b>{event_type}</b> {self.symbol}\n"
                        f"Time: <code>{time_str}</code>\n"
                        f"Price: <code>{self._format_price(price)}</code>\n"
                        f"Level: <b>{level_str}</b>\n"
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
                        self._log_whale_event_to_influx('increase', 'ask', price, change, change_usd,
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
                        self._log_whale_event_to_influx('decrease', 'ask', price, abs(change), change_usd,
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

        # Detect orders that left the visible window (were in previous but not in current)
        for price, (prev_volume, prev_order_count, prev_level) in self.previous_bids.items():
            if price not in current_bids:
                # Bid left the visible window
                usd_value = price * prev_volume
                if prev_volume >= self.min_volume and usd_value >= self.min_usd:
                    self.stats['removed_bids'] += 1

                    # Calculate distance from mid-price
                    if mid_price > 0:
                        distance_from_mid = ((mid_price - price) / mid_price) * 100
                        distance_str = f"{distance_from_mid:+.3f}%"
                    else:
                        distance_from_mid = 0
                        distance_str = "N/A"

                    print(f"{time_str:<12} "
                          f"{DIM}{'BID←OUT':<12}{RESET} "
                          f"{DIM}{self._format_price(price):<12}{RESET} "
                          f"{DIM}{self._format_volume(prev_volume):<12}{RESET} "
                          f"{DIM}{self._format_usd_value(price, prev_volume):<12}{RESET} "
                          f"{DIM}{'---':<10}{RESET} "
                          f"{DIM}{'---':<7}{RESET} "
                          f"{DIM}{prev_order_count:<7}{RESET} "
                          f"{DIM}left_top_{self.limit}{RESET}")

                    # Send Telegram notification
                    if self.telegram_enabled:
                        telegram_msg = (
                            f"⬇️ <b>BID LEFT TOP {self.limit}</b> {self.symbol}\n"
                            f"Time: <code>{time_str}</code>\n"
                            f"Price: <code>{self._format_price(price)}</code>\n"
                            f"Level: Was <b>#{prev_level}</b>\n"
                            f"Orders: <code>{prev_order_count}</code>\n"
                            f"Volume: <code>{self._format_volume(prev_volume)}</code>\n"
                            f"Value: <b>{self._format_usd_value(price, prev_volume)}</b>\n"
                            f"Distance: <code>{distance_str}</code>"
                        )
                        asyncio.create_task(self._send_telegram_message(telegram_msg))

        for price, (prev_volume, prev_order_count, prev_level) in self.previous_asks.items():
            if price not in current_asks:
                # Ask left the visible window
                usd_value = price * prev_volume
                if prev_volume >= self.min_volume and usd_value >= self.min_usd:
                    self.stats['removed_asks'] += 1

                    # Calculate distance from mid-price
                    if mid_price > 0:
                        distance_from_mid = ((price - mid_price) / mid_price) * 100
                        distance_str = f"{distance_from_mid:+.3f}%"
                    else:
                        distance_from_mid = 0
                        distance_str = "N/A"

                    print(f"{time_str:<12} "
                          f"{DIM}{'ASK←OUT':<12}{RESET} "
                          f"{DIM}{self._format_price(price):<12}{RESET} "
                          f"{DIM}{self._format_volume(prev_volume):<12}{RESET} "
                          f"{DIM}{self._format_usd_value(price, prev_volume):<12}{RESET} "
                          f"{DIM}{'---':<10}{RESET} "
                          f"{DIM}{'---':<7}{RESET} "
                          f"{DIM}{prev_order_count:<7}{RESET} "
                          f"{DIM}left_top_{self.limit}{RESET}")

                    # Send Telegram notification
                    if self.telegram_enabled:
                        telegram_msg = (
                            f"⬇️ <b>ASK LEFT TOP {self.limit}</b> {self.symbol}\n"
                            f"Time: <code>{time_str}</code>\n"
                            f"Price: <code>{self._format_price(price)}</code>\n"
                            f"Level: Was <b>#{prev_level}</b>\n"
                            f"Orders: <code>{prev_order_count}</code>\n"
                            f"Volume: <code>{self._format_volume(prev_volume)}</code>\n"
                            f"Value: <b>{self._format_usd_value(price, prev_volume)}</b>\n"
                            f"Distance: <code>{distance_str}</code>"
                        )
                        asyncio.create_task(self._send_telegram_message(telegram_msg))

        # Update state
        self.previous_bids = current_bids.copy()
        self.previous_asks = current_asks.copy()
        self.previous_full_bids = self.full_bids.copy()
        self.previous_full_asks = self.full_asks.copy()
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
        if self.track_trades:
            print(f"  {YELLOW}Trades: {self.stats['trades']}{RESET} | "
                  f"Buy: {self._format_volume(self.stats['buy_volume'])} | "
                  f"Sell: {self._format_volume(self.stats['sell_volume'])}")
        if self.version_errors > 0:
            print(f"  {DIM}Version gaps: {self.version_errors}{RESET}")
        print(f"{CYAN}{'─'*80}{RESET}\n")

    def _log_price_to_influx(self, best_bid: float, best_ask: float):
        """Log price data to InfluxDB (separate measurement for price tracking)"""
        if not self.influx_enabled or not self.influx_write_api:
            return

        try:
            mid_price = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0
            spread = best_ask - best_bid if (best_bid and best_ask) else 0

            point = Point("orderbook_price") \
                .tag("symbol", self.symbol) \
                .field("best_bid", float(best_bid)) \
                .field("best_ask", float(best_ask)) \
                .field("mid_price", float(mid_price)) \
                .field("spread", float(spread))

            self.influx_write_api.write(bucket=self.influx_bucket, record=point)
        except Exception as e:
            logger.error(f"Failed to write price to InfluxDB: {e}")

    def _log_whale_event_to_influx(self, event_type: str, side: str, price: float, volume: float,
                                    usd_value: float, distance_pct: float, best_bid: float,
                                    best_ask: float, info: str = "", level: int = 0, order_count: int = 0):
        """Log whale event to InfluxDB (separate measurement for whale events)"""
        if not self.influx_enabled or not self.influx_write_api:
            return

        try:
            mid_price = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0
            spread = best_ask - best_bid if (best_bid and best_ask) else 0

            point = Point("orderbook_whale_events") \
                .tag("symbol", self.symbol) \
                .tag("event_type", event_type) \
                .tag("side", side) \
                .field("price", float(price)) \
                .field("volume", float(volume)) \
                .field("usd_value", float(usd_value)) \
                .field("distance_from_mid_pct", float(distance_pct)) \
                .field("mid_price", float(mid_price)) \
                .field("best_bid", float(best_bid)) \
                .field("best_ask", float(best_ask)) \
                .field("spread", float(spread)) \
                .field("level", int(level)) \
                .field("order_count", int(order_count)) \
                .field("info", str(info))

            self.influx_write_api.write(bucket=self.influx_bucket, record=point)
        except Exception as e:
            logger.error(f"Failed to write whale event to InfluxDB: {e}")

    async def connect(self):
        """Connect and start tracking"""
        self.running = True

        # Fetch initial snapshot from REST API
        print(f"{CYAN}Fetching initial order book snapshot...{RESET}")
        snapshot_success = await self._fetch_initial_snapshot()
        if not snapshot_success:
            print(f"{YELLOW}⚠ Warning: Failed to fetch initial snapshot, starting with empty state{RESET}")

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
                    print(f"{GREEN}✓ Connected to MEXC WebSocket{RESET}")

                    await self._subscribe(ws)

                    # Start ping task
                    ping_task = asyncio.create_task(self._send_ping(ws))

                    # Process messages
                    async for message in ws:
                        try:
                            data = json.loads(message)

                            # Handle order book depth updates
                            if data.get('channel') == 'push.depth.full':
                                self._process_orderbook(data.get('data', {}))

                            # Handle trade executions
                            elif data.get('channel') == 'push.deal':
                                deals = data.get('data', [])
                                for deal in deals:
                                    await self._process_trade(deal)

                            # Handle pong responses
                            elif data.get('channel') == 'pong':
                                logger.debug("Received pong")

                            # Handle subscription responses
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

        # Close InfluxDB client
        if self.influx_client:
            self.influx_client.close()
            logger.info("InfluxDB client closed")

        runtime = time.time() - self.session_start
        print(f"\n{BOLD}{CYAN}{'='*100}{RESET}")
        print(f"{BOLD}{WHITE}Final Statistics - Runtime: {runtime:.0f}s{RESET}")
        print(f"{CYAN}{'='*100}{RESET}")
        print(f"Order Book Updates: {self.stats['updates']}")
        print(f"{GREEN}Total New Bids: {self.stats['new_bids']} "
              f"(Volume: {self._format_volume(self.stats['total_bid_volume'])}){RESET}")
        print(f"{RED}Total New Asks: {self.stats['new_asks']} "
              f"(Volume: {self._format_volume(self.stats['total_ask_volume'])}){RESET}")
        print(f"Removed from view - Bids: {self.stats['removed_bids']} | Asks: {self.stats['removed_asks']}")
        if self.track_trades:
            print(f"\n{YELLOW}Trade Executions: {self.stats['trades']}{RESET}")
            print(f"{GREEN}Buy Volume: {self._format_volume(self.stats['buy_volume'])}{RESET} | "
                  f"{RED}Sell Volume: {self._format_volume(self.stats['sell_volume'])}{RESET}")
        if self.version_errors > 0:
            print(f"\n{YELLOW}⚠ Version Errors (packet loss): {self.version_errors}{RESET}")
        if self.influx_enabled:
            print(f"\n{CYAN}✓ Data logged to InfluxDB: {self.influx_bucket}{RESET}")


async def main():
    """Main function"""
    # Load environment variables from .env file
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='MEXC Order Book & Trade Tracker - Track individual orders and whale activity in real-time',
        epilog='Example: python orderbook_tracker.py BTC_USDT --min-usd 50000 --limit 20'
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
        default=20,
        help='Order book depth to monitor (default: 20 - maximum allowed by MEXC API)'
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
    parser.add_argument(
        '--no-trades',
        action='store_true',
        help='Disable trade execution tracking (only show order book changes)'
    )
    parser.add_argument(
        '--influx',
        action='store_true',
        help='Enable InfluxDB logging of all events (reads credentials from .env)'
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

    # Get InfluxDB credentials from environment if enabled
    influx_url = None
    influx_token = None
    influx_org = None
    influx_bucket = None
    if args.influx:
        influx_url = os.getenv('INFLUXDB_URL')
        influx_token = os.getenv('INFLUXDB_TOKEN')
        influx_org = os.getenv('INFLUXDB_ORG')
        influx_bucket = os.getenv('INFLUXDB_BUCKET')

        if not all([influx_url, influx_token, influx_org, influx_bucket]):
            print(f"{RED}Error: --influx requires INFLUXDB_URL, INFLUXDB_TOKEN, INFLUXDB_ORG, and INFLUXDB_BUCKET in .env{RESET}")
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
        telegram_chat_id=telegram_chat_id,
        track_trades=not args.no_trades,
        influx_enabled=args.influx,
        influx_url=influx_url,
        influx_token=influx_token,
        influx_org=influx_org,
        influx_bucket=influx_bucket
    )

    # Handle shutdown
    def signal_handler(signum, frame):
        logger.info("Shutdown signal received")
        asyncio.create_task(tracker.disconnect())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"\n{BOLD}{CYAN}═══════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}{WHITE}MEXC Order Book & Trade Tracker{RESET}")
    print(f"{CYAN}═══════════════════════════════════════════════════════════════{RESET}")
    print(f"Symbol: {BOLD}{args.symbol}{RESET}")
    print(f"Depth: Top {args.limit} levels")
    if args.min_volume > 0:
        print(f"Min Volume Filter: {args.min_volume}")
    if args.min_usd > 0:
        print(f"Min USD Filter: ${args.min_usd:,.0f}")
    if args.max_usd:
        print(f"Max USD Filter: ${args.max_usd:,.0f}")
    if args.min_distance or args.max_distance:
        print(f"Distance Filter: {args.min_distance or 0}% - {args.max_distance or '∞'}%")
    print(f"Trade Tracking: {GREEN}Enabled{RESET}" if not args.no_trades else f"Trade Tracking: {DIM}Disabled{RESET}")
    if args.telegram:
        print(f"Telegram: {GREEN}Enabled{RESET}")
    if args.influx:
        print(f"InfluxDB: {GREEN}Enabled{RESET} → {influx_bucket}")
    print(f"\n{GREEN}🟢 BID WALL{RESET} = New buy order placed")
    print(f"{RED}🔴 ASK WALL{RESET} = New sell order placed")
    if not args.no_trades:
        print(f"{GREEN}{BOLD}💥 MARKET BUY{RESET} = Aggressive buyer (market order)")
        print(f"{RED}{BOLD}💥 MARKET SELL{RESET} = Aggressive seller (market order)")
    print(f"{DIM}↑/↓{RESET} = Volume changes | {DIM}→TOP/←OUT{RESET} = Moves in/out of visible window")
    print(f"\n{YELLOW}Press Ctrl+C to exit{RESET}\n")

    try:
        await tracker.connect()
    except KeyboardInterrupt:
        pass
    finally:
        await tracker.disconnect()


if __name__ == "__main__":
    asyncio.run(main())