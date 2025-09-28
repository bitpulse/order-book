import asyncio
import signal
import sys
from typing import Dict
from loguru import logger
from datetime import datetime

from .config import get_settings
from .mexc_websocket import MEXCWebSocketClient
from .orderbook_processor import OrderBookProcessor
from .influxdb_storage import InfluxDBStorage


class OrderBookCollector:
    """Main application for collecting MEXC order book data"""

    def __init__(self):
        self.settings = get_settings()
        self.setup_logging()
        self.running = False

        # Initialize components
        self.processor = OrderBookProcessor(
            whale_thresholds_func=self.settings.get_whale_thresholds
        )

        self.storage = InfluxDBStorage(
            url=self.settings.influxdb_url,
            token=self.settings.influxdb_token,
            org=self.settings.influxdb_org,
            bucket=self.settings.influxdb_bucket,
            batch_size=self.settings.batch_size,
            batch_timeout=self.settings.batch_timeout
        )

        self.websocket = MEXCWebSocketClient(
            url=self.settings.mexc_websocket_url,
            symbols=self.settings.get_trading_pairs_list(),
            on_message=self.handle_message
        )

        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def setup_logging(self):
        """Setup logging configuration"""
        logger.remove()  # Remove default handler

        # Console handler with color
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
            level=self.settings.log_level,
            colorize=True
        )

        # File handler
        logger.add(
            self.settings.log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
            level=self.settings.log_level,
            rotation="100 MB",
            retention="7 days",
            compression="zip"
        )

        logger.info("=" * 60)
        logger.info("MEXC Order Book Collector Starting")
        logger.info(f"Trading Pairs: {', '.join(self.settings.get_trading_pairs_list())}")
        logger.info(f"InfluxDB: {self.settings.influxdb_url}")
        logger.info(f"Order Book Depth: {self.settings.order_book_depth} levels")
        logger.info("=" * 60)

    async def handle_message(self, message: Dict):
        """Handle incoming WebSocket message"""
        try:
            # Process the message
            snapshot, depths, whales = self.processor.process(message)

            if snapshot:
                # Store in InfluxDB
                await self.storage.store_data(snapshot, depths, whales)

                # Log statistics
                logger.info(
                    f"📊 {snapshot.symbol} | "
                    f"Bid: ${snapshot.best_bid:,.2f} | "
                    f"Ask: ${snapshot.best_ask:,.2f} | "
                    f"Spread: {snapshot.spread_percentage:.3f}% | "
                    f"Imbalance: {snapshot.imbalance:.3f}"
                )

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    async def run(self):
        """Main application loop"""
        self.running = True

        # Test InfluxDB connection
        if not await self.storage.test_connection():
            logger.error("Failed to connect to InfluxDB. Please check your configuration.")
            return

        try:
            # Start periodic flush task
            flush_task = asyncio.create_task(self.storage.periodic_flush())

            # Start WebSocket client
            ws_task = asyncio.create_task(self.websocket.start())

            # Wait for tasks
            while self.running:
                await asyncio.sleep(1)

                # Check if tasks are still running
                if ws_task.done():
                    logger.error("WebSocket task ended unexpectedly")
                    break

            # Cleanup
            logger.info("Shutting down...")
            await self.websocket.stop()
            flush_task.cancel()

            # Final flush
            await self.storage.flush_batch()

        except Exception as e:
            logger.error(f"Application error: {e}")
        finally:
            self.storage.close()
            logger.info("Application stopped")

    async def main(self):
        """Entry point"""
        try:
            await self.run()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            sys.exit(1)


def main():
    """Main entry point"""
    collector = OrderBookCollector()
    asyncio.run(collector.main())


if __name__ == "__main__":
    main()