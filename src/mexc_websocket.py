import asyncio
import json
import websockets
from typing import Callable, Dict, List, Optional
from loguru import logger
from datetime import datetime
import time


class MEXCWebSocketClient:
    """WebSocket client for MEXC futures order book data"""

    def __init__(self, url: str, symbols: List[str], on_message: Callable):
        self.url = url
        self.symbols = symbols
        self.on_message = on_message
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.last_ping = time.time()
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        # For single symbol, we can track it (MEXC doesn't send symbol in depth message)
        self.current_symbol = symbols[0] if len(symbols) == 1 else None

    async def connect(self):
        """Connect to WebSocket server"""
        try:
            logger.debug(f"Attempting to connect to {self.url}")
            self.ws = await websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            self.running = True
            logger.info(f"Connected to MEXC WebSocket: {self.url}")
            self.reconnect_delay = 5  # Reset reconnect delay on successful connection
            return True
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def disconnect(self):
        """Disconnect from WebSocket server"""
        self.running = False
        if self.ws:
            await self.ws.close()
            logger.info("Disconnected from MEXC WebSocket")

    async def subscribe_to_depth(self, symbol: str, limit: int = 20):
        """Subscribe to order book depth for a symbol"""
        subscription = {
            "method": "sub.depth",
            "param": {
                "symbol": symbol,
                "limit": limit
            }
        }

        try:
            await self.ws.send(json.dumps(subscription))
            logger.info(f"Subscribed to depth for {symbol} (limit: {limit})")
        except Exception as e:
            logger.error(f"Failed to subscribe to {symbol}: {e}")

    async def unsubscribe_from_depth(self, symbol: str):
        """Unsubscribe from order book depth"""
        unsubscription = {
            "method": "unsub.depth",
            "param": {
                "symbol": symbol
            }
        }

        try:
            await self.ws.send(json.dumps(unsubscription))
            logger.info(f"Unsubscribed from depth for {symbol}")
        except Exception as e:
            logger.error(f"Failed to unsubscribe from {symbol}: {e}")

    async def ping(self):
        """Send ping to keep connection alive"""
        try:
            if self.ws and not self.ws.closed:
                await self.ws.ping()
                self.last_ping = time.time()
                logger.debug("Sent ping to MEXC WebSocket")
        except Exception as e:
            logger.error(f"Failed to send ping: {e}")

    async def handle_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)

            # Check if it's a depth update
            if data.get("channel") == "push.depth":
                # Add symbol to the data if we're tracking a single symbol
                if self.current_symbol:
                    data["symbol"] = self.current_symbol
                await self.on_message(data)
            elif "error" in data:
                logger.error(f"Error message from MEXC: {data}")
            elif "success" in data:
                logger.debug(f"Success response: {data}")
            else:
                logger.debug(f"Other message: {data}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def run(self):
        """Main WebSocket loop"""
        while self.running:
            try:
                # Connect if not connected
                if not self.ws or self.ws.closed:
                    logger.info("WebSocket not connected, attempting to connect...")
                    if not await self.connect():
                        logger.warning(f"Connection failed, retrying in {self.reconnect_delay} seconds")
                        await asyncio.sleep(self.reconnect_delay)
                        self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                        continue

                    # Subscribe to all symbols
                    for symbol in self.symbols:
                        await self.subscribe_to_depth(symbol)
                        await asyncio.sleep(0.1)  # Small delay between subscriptions

                # Create tasks for message handling and ping
                ping_task = asyncio.create_task(self.ping_loop())
                message_task = asyncio.create_task(self.message_loop())

                # Wait for either task to complete (likely due to error)
                done, pending = await asyncio.wait(
                    [ping_task, message_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def message_loop(self):
        """Handle incoming messages"""
        try:
            async for message in self.ws:
                await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Message loop error: {e}")

    async def ping_loop(self):
        """Send periodic pings"""
        while self.running and self.ws and not self.ws.closed:
            try:
                current_time = time.time()
                if current_time - self.last_ping > 15:  # Send ping every 15 seconds
                    await self.ping()
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Ping loop error: {e}")
                break

    async def start(self):
        """Start the WebSocket client"""
        try:
            logger.info(f"Starting MEXC WebSocket client for symbols: {self.symbols}")
            self.running = True
            await self.run()
        except Exception as e:
            logger.error(f"WebSocket client error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    async def stop(self):
        """Stop the WebSocket client"""
        logger.info("Stopping MEXC WebSocket client...")
        await self.disconnect()