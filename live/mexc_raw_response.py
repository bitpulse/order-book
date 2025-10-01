#!/usr/bin/env python3
"""
MEXC Raw Response Viewer
Shows complete raw JSON response from MEXC WebSocket
"""

import json
import asyncio
import websockets
import sys

async def get_raw_response(symbol: str = "WIF_USDT"):
    """Get and display raw MEXC response"""

    ws_url = "wss://contract.mexc.com/edge"

    try:
        async with websockets.connect(ws_url) as ws:
            print("Connected to MEXC WebSocket\n")

            # Subscribe to order book with all 20 levels
            subscription = {
                "method": "sub.depth",
                "param": {
                    "symbol": symbol,
                    "limit": 20,  # Get all 20 levels
                    "compress": False
                }
            }

            print("Sending subscription:")
            print(json.dumps(subscription, indent=2))
            await ws.send(json.dumps(subscription))

            # Capture messages
            captured = 0
            while captured < 5:  # Get first 5 messages
                message = await ws.recv()
                data = json.loads(message)

                print(f"\n{'='*80}")
                print(f"MESSAGE #{captured + 1}")
                print('='*80)

                # Show message type
                if 'channel' in data:
                    print(f"Type: {data['channel']}")

                    # Only show full JSON for order book messages
                    if data['channel'] == 'push.depth':
                        print(f"\nFULL RAW JSON:")
                        print(json.dumps(data, indent=2))

                        # Show statistics
                        depth_data = data.get('data', {})
                        bids = depth_data.get('bids', [])
                        asks = depth_data.get('asks', [])

                        print(f"\nSTATISTICS:")
                        print(f"  Bid Levels: {len(bids)}")
                        print(f"  Ask Levels: {len(asks)}")
                        print(f"  Version: {depth_data.get('version', 'N/A')}")

                        # Check order counts
                        bid_with_count = sum(1 for b in bids if len(b) > 2)
                        ask_with_count = sum(1 for a in asks if len(a) > 2)
                        print(f"  Bids with order count: {bid_with_count}/{len(bids)}")
                        print(f"  Asks with order count: {ask_with_count}/{len(asks)}")

                        # Show first few levels with interpretation
                        print(f"\nFIRST 3 BID LEVELS:")
                        for i, bid in enumerate(bids[:3], 1):
                            if len(bid) >= 3:
                                print(f"  Level {i}: Price={bid[0]}, Volume={bid[1]}, Orders={bid[2]}")
                                if bid[2] > 0:
                                    avg = bid[1] / bid[2]
                                    print(f"           Average order size: {avg:.2f} tokens")
                            else:
                                print(f"  Level {i}: Price={bid[0]}, Volume={bid[1]}")

                        print(f"\nFIRST 3 ASK LEVELS:")
                        for i, ask in enumerate(asks[:3], 1):
                            if len(ask) >= 3:
                                print(f"  Level {i}: Price={ask[0]}, Volume={ask[1]}, Orders={ask[2]}")
                                if ask[2] > 0:
                                    avg = ask[1] / ask[2]
                                    print(f"           Average order size: {avg:.2f} tokens")
                            else:
                                print(f"  Level {i}: Price={ask[0]}, Volume={ask[1]}")

                        captured += 1
                else:
                    print(f"Response: {json.dumps(data, indent=2)}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "WIF_USDT"
    print(f"Getting raw response for {symbol}\n")
    asyncio.run(get_raw_response(symbol))