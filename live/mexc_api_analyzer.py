#!/usr/bin/env python3
"""
MEXC API Response Analyzer
Captures and analyzes raw WebSocket responses from MEXC to understand the API structure
"""

import json
import asyncio
import websockets
import argparse
from datetime import datetime
from typing import Dict, Any
import sys

# ANSI colors for output
GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RED = '\033[91m'
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'


class MEXCAPIAnalyzer:
    """Analyzes MEXC WebSocket API responses"""

    def __init__(self, symbol: str, capture_count: int = 10):
        """
        Initialize API analyzer

        Args:
            symbol: Trading pair to analyze
            capture_count: Number of messages to capture
        """
        self.ws_url = "wss://contract.mexc.com/edge"
        self.symbol = symbol.upper()
        self.capture_count = capture_count
        self.messages = []
        self.message_types = {}
        self.running = False

    async def connect_and_capture(self):
        """Connect to WebSocket and capture raw messages"""
        print(f"{BOLD}{CYAN}Connecting to MEXC WebSocket...{RESET}")
        print(f"Capturing {self.capture_count} messages for {self.symbol}\n")

        captured = 0

        try:
            async with websockets.connect(self.ws_url) as ws:
                print(f"{GREEN}✓ Connected successfully{RESET}\n")

                # Subscribe to order book depth
                subscription = {
                    "method": "sub.depth",
                    "param": {
                        "symbol": self.symbol,
                        "limit": 5,  # Small limit for analysis
                        "compress": False
                    }
                }

                print(f"{YELLOW}Sending subscription request:{RESET}")
                print(json.dumps(subscription, indent=2))
                await ws.send(json.dumps(subscription))
                print()

                # Also subscribe to trades for comparison
                trade_subscription = {
                    "method": "sub.deal",
                    "param": {
                        "symbol": self.symbol
                    }
                }
                await ws.send(json.dumps(trade_subscription))

                # Capture messages
                while captured < self.capture_count:
                    message = await ws.recv()

                    try:
                        data = json.loads(message)
                        self.messages.append(data)
                        captured += 1

                        # Track message types
                        msg_type = self._identify_message_type(data)
                        self.message_types[msg_type] = self.message_types.get(msg_type, 0) + 1

                        print(f"{BOLD}Message #{captured}{RESET} - Type: {CYAN}{msg_type}{RESET}")

                    except json.JSONDecodeError:
                        print(f"{RED}Failed to parse message{RESET}")

        except Exception as e:
            print(f"{RED}Error: {e}{RESET}")

    def _identify_message_type(self, data: Dict) -> str:
        """Identify the type of message"""
        if 'channel' in data:
            return data['channel']
        elif 'code' in data:
            return f"response (code: {data['code']})"
        elif 'method' in data:
            return f"method: {data['method']}"
        else:
            return "unknown"

    def analyze_depth_message(self, msg: Dict):
        """Analyze a depth (order book) message"""
        print(f"\n{BOLD}{GREEN}=== ORDER BOOK (DEPTH) MESSAGE ANALYSIS ==={RESET}")

        # Basic structure
        print(f"\n{YELLOW}Message Structure:{RESET}")
        print(f"  Channel: {msg.get('channel', 'N/A')}")
        print(f"  Symbol: {msg.get('symbol', 'N/A')}")
        print(f"  Timestamp: {msg.get('data', {}).get('timestamp', 'N/A')}")

        data = msg.get('data', {})
        if data:
            # Timestamp analysis
            ts = data.get('timestamp', 0)
            if ts:
                dt = datetime.fromtimestamp(ts / 1000)
                print(f"  Readable Time: {dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                print(f"  Version: {data.get('version', 'N/A')}")

            # Bids analysis
            bids = data.get('bids', [])
            print(f"\n{YELLOW}Bids (Buy Orders):{RESET}")
            print(f"  Total Levels: {len(bids)}")
            if bids:
                print(f"  Best Bid: Price={bids[0][0]}, Volume={bids[0][1]}")
                print(f"  Data Format: {self._analyze_order_format(bids[0])}")

                # Show all bid levels
                print(f"\n  {CYAN}All Bid Levels:{RESET}")
                for i, bid in enumerate(bids, 1):
                    price = bid[0]
                    volume = bid[1]
                    order_count = bid[2] if len(bid) > 2 else 'N/A'
                    print(f"    Level {i}: Price={price}, Volume={volume}, Orders={order_count}")

            # Asks analysis
            asks = data.get('asks', [])
            print(f"\n{YELLOW}Asks (Sell Orders):{RESET}")
            print(f"  Total Levels: {len(asks)}")
            if asks:
                print(f"  Best Ask: Price={asks[0][0]}, Volume={asks[0][1]}")
                print(f"  Data Format: {self._analyze_order_format(asks[0])}")

                # Show all ask levels
                print(f"\n  {CYAN}All Ask Levels:{RESET}")
                for i, ask in enumerate(asks, 1):
                    price = ask[0]
                    volume = ask[1]
                    order_count = ask[2] if len(ask) > 2 else 'N/A'
                    print(f"    Level {i}: Price={price}, Volume={volume}, Orders={order_count}")

            # Calculate spread
            if bids and asks:
                spread = float(asks[0][0]) - float(bids[0][0])
                spread_pct = (spread / float(asks[0][0])) * 100
                print(f"\n{YELLOW}Market Metrics:{RESET}")
                print(f"  Spread: {spread:.6f} ({spread_pct:.3f}%)")
                print(f"  Mid Price: {(float(bids[0][0]) + float(asks[0][0])) / 2:.6f}")

    def analyze_deal_message(self, msg: Dict):
        """Analyze a deal (trade) message"""
        print(f"\n{BOLD}{GREEN}=== TRADE (DEAL) MESSAGE ANALYSIS ==={RESET}")

        print(f"\n{YELLOW}Message Structure:{RESET}")
        print(f"  Channel: {msg.get('channel', 'N/A')}")
        print(f"  Symbol: {msg.get('symbol', 'N/A')}")

        data = msg.get('data', [])
        if data:
            print(f"  Number of Trades: {len(data)}")

            for i, trade in enumerate(data, 1):
                print(f"\n  {CYAN}Trade #{i}:{RESET}")
                print(f"    Price (p): {trade.get('p', 'N/A')}")
                print(f"    Volume (v): {trade.get('v', 'N/A')}")
                print(f"    Trade Type (T): {trade.get('T', 'N/A')} (1=Buy, 2=Sell)")
                print(f"    Order Type (O): {trade.get('O', 'N/A')}")
                print(f"    Maker/Taker (M): {trade.get('M', 'N/A')} (1=Maker, 2=Taker)")
                print(f"    Timestamp (t): {trade.get('t', 'N/A')}")

                ts = trade.get('t', 0)
                if ts:
                    dt = datetime.fromtimestamp(ts / 1000)
                    print(f"    Readable Time: {dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

    def analyze_response_message(self, msg: Dict):
        """Analyze a response message"""
        print(f"\n{BOLD}{GREEN}=== RESPONSE MESSAGE ANALYSIS ==={RESET}")

        print(f"\n{YELLOW}Response Details:{RESET}")
        print(f"  Code: {msg.get('code', 'N/A')}")
        print(f"  Message: {msg.get('msg', 'N/A')}")
        print(f"  Channel: {msg.get('channel', 'N/A')}")

        if msg.get('code') == 0:
            print(f"  {GREEN}✓ Success{RESET}")
        else:
            print(f"  {RED}✗ Error{RESET}")

    def _analyze_order_format(self, order_data: list) -> str:
        """Analyze the format of order data"""
        if len(order_data) == 2:
            return "[price, volume]"
        elif len(order_data) == 3:
            return "[price, volume, order_count]"
        else:
            return f"Unknown format with {len(order_data)} elements"

    def analyze_all_messages(self):
        """Analyze all captured messages"""
        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}ANALYZING {len(self.messages)} CAPTURED MESSAGES{RESET}")
        print(f"{CYAN}{'='*60}{RESET}")

        # Summary
        print(f"\n{YELLOW}Message Type Summary:{RESET}")
        for msg_type, count in self.message_types.items():
            print(f"  {msg_type}: {count} messages")

        # Analyze each unique message type
        analyzed_types = set()

        for i, msg in enumerate(self.messages, 1):
            msg_type = self._identify_message_type(msg)

            # Only analyze first of each type for clarity
            if msg_type not in analyzed_types:
                print(f"\n{BOLD}{CYAN}--- Message #{i} ---{RESET}")

                # Raw JSON
                print(f"\n{YELLOW}Raw JSON:{RESET}")
                print(json.dumps(msg, indent=2))  # Show full JSON

                # Detailed analysis based on type
                if 'push.depth' in msg_type:
                    self.analyze_depth_message(msg)
                    analyzed_types.add(msg_type)
                elif 'push.deal' in msg_type:
                    self.analyze_deal_message(msg)
                    analyzed_types.add(msg_type)
                elif 'response' in msg_type:
                    self.analyze_response_message(msg)
                    analyzed_types.add(msg_type)

        # Save to file
        self.save_analysis()

    def save_analysis(self):
        """Save captured messages to file for further analysis"""
        filename = f"mexc_api_analysis_{self.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        analysis = {
            "symbol": self.symbol,
            "capture_time": datetime.now().isoformat(),
            "message_count": len(self.messages),
            "message_types": self.message_types,
            "raw_messages": self.messages
        }

        with open(filename, 'w') as f:
            json.dump(analysis, f, indent=2)

        print(f"\n{GREEN}✓ Analysis saved to {filename}{RESET}")

    def print_api_insights(self):
        """Print insights about the API based on captured data"""
        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}API INSIGHTS{RESET}")
        print(f"{CYAN}{'='*60}{RESET}")

        if not self.messages:
            print("No messages captured")
            return

        # Find depth messages
        depth_msgs = [m for m in self.messages if m.get('channel') == 'push.depth']

        if depth_msgs:
            print(f"\n{YELLOW}Order Book (Depth) Insights:{RESET}")

            # Check data format consistency
            formats = set()
            for msg in depth_msgs:
                data = msg.get('data', {})
                bids = data.get('bids', [])
                asks = data.get('asks', [])

                for bid in bids:
                    formats.add(f"bid_{len(bid)}_fields")
                for ask in asks:
                    formats.add(f"ask_{len(ask)}_fields")

            print(f"  Data Formats Found: {formats}")

            # Version analysis
            versions = [m.get('data', {}).get('version', 0) for m in depth_msgs]
            if len(versions) > 1:
                version_increments = [versions[i+1] - versions[i] for i in range(len(versions)-1)]
                print(f"  Version Increments: {set(version_increments)}")
                print(f"  Sequential Versions: {all(inc == 1 for inc in version_increments)}")

            # Timestamp analysis
            timestamps = [m.get('data', {}).get('timestamp', 0) for m in depth_msgs]
            if len(timestamps) > 1:
                intervals = [(timestamps[i+1] - timestamps[i]) for i in range(len(timestamps)-1)]
                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    print(f"  Average Update Interval: {avg_interval:.2f}ms")
                    print(f"  Min Interval: {min(intervals)}ms")
                    print(f"  Max Interval: {max(intervals)}ms")

        # Find deal messages
        deal_msgs = [m for m in self.messages if m.get('channel') == 'push.deal']

        if deal_msgs:
            print(f"\n{YELLOW}Trade (Deal) Insights:{RESET}")
            print(f"  Messages with Trades: {len(deal_msgs)}")

            total_trades = sum(len(m.get('data', [])) for m in deal_msgs)
            print(f"  Total Individual Trades: {total_trades}")

            if total_trades > 0:
                avg_trades_per_msg = total_trades / len(deal_msgs)
                print(f"  Avg Trades per Message: {avg_trades_per_msg:.2f}")

        print(f"\n{YELLOW}General API Characteristics:{RESET}")
        print(f"  ✓ Uses channel-based message routing")
        print(f"  ✓ Includes version numbers for order book updates")
        print(f"  ✓ Timestamps in milliseconds (Unix epoch)")
        print(f"  ✓ Order book format: [price, volume] or [price, volume, order_count]")
        print(f"  ✓ Trade data includes type, maker/taker info")
        print(f"  ✓ Response codes: 0 = success, non-zero = error")


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='MEXC WebSocket API Response Analyzer'
    )
    parser.add_argument(
        'symbol',
        type=str,
        help='Trading pair to analyze (e.g., BTC_USDT)'
    )
    parser.add_argument(
        '--messages',
        type=int,
        default=10,
        help='Number of messages to capture (default: 10)'
    )

    args = parser.parse_args()

    print(f"{BOLD}{CYAN}MEXC API Response Analyzer{RESET}")
    print(f"{CYAN}{'='*60}{RESET}\n")

    # Create analyzer
    analyzer = MEXCAPIAnalyzer(args.symbol, args.messages)

    # Capture messages
    await analyzer.connect_and_capture()

    # Analyze
    analyzer.analyze_all_messages()

    # Print insights
    analyzer.print_api_insights()


if __name__ == "__main__":
    asyncio.run(main())