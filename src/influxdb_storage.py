from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS, ASYNCHRONOUS
from typing import List, Optional
from loguru import logger
import asyncio
from datetime import datetime
import time

from .orderbook_processor import OrderBookSnapshot, MarketDepth, WhaleOrder


class InfluxDBStorage:
    """Handles storage of order book data to InfluxDB"""

    def __init__(self, url: str, token: str, org: str, bucket: str,
                 batch_size: int = 100, batch_timeout: float = 1.0):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout

        # Initialize InfluxDB client
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=ASYNCHRONOUS)

        # Batch for points
        self.point_batch: List[Point] = []
        self.last_write = time.time()

        logger.info(f"Connected to InfluxDB at {url}")

    def create_snapshot_points(self, snapshot: OrderBookSnapshot) -> List[Point]:
        """Create InfluxDB points for order book snapshot"""
        points = []
        timestamp = datetime.utcfromtimestamp(snapshot.timestamp / 1000)

        # Store bid levels
        for level_idx, level in enumerate(snapshot.bids, 1):
            point = (
                Point("order_book_snapshot")
                .tag("symbol", snapshot.symbol)
                .tag("exchange", snapshot.exchange)
                .tag("side", "bid")
                .tag("level", str(level_idx))
                .field("price", float(level.price))
                .field("volume", float(level.volume))
                .field("order_count", level.order_count)
                .field("total_value", float(level.total_value))
                .time(timestamp, WritePrecision.MS)
            )
            points.append(point)

        # Store ask levels
        for level_idx, level in enumerate(snapshot.asks, 1):
            point = (
                Point("order_book_snapshot")
                .tag("symbol", snapshot.symbol)
                .tag("exchange", snapshot.exchange)
                .tag("side", "ask")
                .tag("level", str(level_idx))
                .field("price", float(level.price))
                .field("volume", float(level.volume))
                .field("order_count", level.order_count)
                .field("total_value", float(level.total_value))
                .time(timestamp, WritePrecision.MS)
            )
            points.append(point)

        return points

    def create_stats_point(self, snapshot: OrderBookSnapshot) -> Point:
        """Create InfluxDB point for aggregated stats"""
        timestamp = datetime.utcfromtimestamp(snapshot.timestamp / 1000)

        point = (
            Point("order_book_stats")
            .tag("symbol", snapshot.symbol)
            .tag("exchange", snapshot.exchange)
            .field("best_bid", float(snapshot.best_bid))
            .field("best_ask", float(snapshot.best_ask))
            .field("spread", float(snapshot.spread))
            .field("spread_percentage", float(snapshot.spread_percentage))
            .field("mid_price", float(snapshot.mid_price))
            .field("bid_volume_total", float(snapshot.bid_volume_total))
            .field("ask_volume_total", float(snapshot.ask_volume_total))
            .field("bid_value_total", float(snapshot.bid_value_total))
            .field("ask_value_total", float(snapshot.ask_value_total))
            .field("imbalance", float(snapshot.imbalance))
            .field("depth_10_bid", float(sum(level.volume for level in snapshot.bids[:10])))
            .field("depth_10_ask", float(sum(level.volume for level in snapshot.asks[:10])))
            .time(timestamp, WritePrecision.MS)
        )

        return point

    def create_depth_points(self, depths: List[MarketDepth]) -> List[Point]:
        """Create InfluxDB points for market depth"""
        points = []

        for depth in depths:
            timestamp = datetime.utcfromtimestamp(depth.timestamp / 1000)
            point = (
                Point("market_depth")
                .tag("symbol", depth.symbol)
                .tag("exchange", depth.exchange)
                .tag("depth_percentage", f"{depth.depth_percentage}%")
                .field("bid_volume", float(depth.bid_volume))
                .field("ask_volume", float(depth.ask_volume))
                .field("bid_orders", depth.bid_orders)
                .field("ask_orders", depth.ask_orders)
                .field("bid_value", float(depth.bid_value))
                .field("ask_value", float(depth.ask_value))
                .time(timestamp, WritePrecision.MS)
            )
            points.append(point)

        return points

    def create_whale_points(self, whales: List[WhaleOrder]) -> List[Point]:
        """Create InfluxDB points for whale orders"""
        points = []

        for whale in whales:
            timestamp = datetime.utcfromtimestamp(whale.timestamp / 1000)
            point = (
                Point("whale_orders")
                .tag("symbol", whale.symbol)
                .tag("exchange", whale.exchange)
                .tag("side", whale.side)
                .tag("order_type", whale.order_type)
                .tag("whale_category", whale.whale_category)
                .field("price", float(whale.price))
                .field("volume", float(whale.volume))
                .field("value_usdt", float(whale.value_usdt))
                .field("level", whale.level)
                .field("distance_from_mid", float(whale.distance_from_mid))
                .field("distance_from_mid_abs", float(whale.distance_from_mid_abs))
                .time(timestamp, WritePrecision.MS)
            )
            points.append(point)

            # Log whale detection for monitoring
            logger.warning(
                f"🐋 Whale {whale.whale_category.upper()} {whale.side.upper()} order detected: "
                f"{whale.symbol} @ ${whale.price:,.2f} - "
                f"Volume: {whale.volume:,.4f} - "
                f"Value: ${whale.value_usdt:,.0f}"
            )

        return points

    async def store_data(self, snapshot: OrderBookSnapshot,
                        depths: List[MarketDepth],
                        whales: List[WhaleOrder]):
        """Store all order book data to InfluxDB"""
        try:
            points = []

            # Create all points
            points.extend(self.create_snapshot_points(snapshot))
            points.append(self.create_stats_point(snapshot))
            points.extend(self.create_depth_points(depths))
            points.extend(self.create_whale_points(whales))

            # Add to batch
            self.point_batch.extend(points)

            # Write if batch is full or timeout reached
            current_time = time.time()
            if (len(self.point_batch) >= self.batch_size or
                current_time - self.last_write >= self.batch_timeout):
                await self.flush_batch()

            logger.debug(f"Added {len(points)} points to batch for {snapshot.symbol}")

        except Exception as e:
            logger.error(f"Failed to store data: {e}")

    async def flush_batch(self):
        """Flush the current batch to InfluxDB"""
        if not self.point_batch:
            return

        try:
            self.write_api.write(bucket=self.bucket, record=self.point_batch)
            logger.info(f"Flushed {len(self.point_batch)} points to InfluxDB")
            self.point_batch = []
            self.last_write = time.time()
        except Exception as e:
            logger.error(f"Failed to flush batch to InfluxDB: {e}")

    async def periodic_flush(self):
        """Periodically flush the batch"""
        while True:
            await asyncio.sleep(self.batch_timeout)
            await self.flush_batch()

    def close(self):
        """Close InfluxDB connection"""
        try:
            # Flush remaining points
            if self.point_batch:
                self.write_api.write(bucket=self.bucket, record=self.point_batch)
                logger.info(f"Flushed final {len(self.point_batch)} points")

            self.write_api.close()
            self.client.close()
            logger.info("Closed InfluxDB connection")
        except Exception as e:
            logger.error(f"Error closing InfluxDB: {e}")

    async def test_connection(self) -> bool:
        """Test InfluxDB connection"""
        try:
            # Try to get the health of the InfluxDB instance
            health = self.client.health()
            if health.status == "pass":
                logger.info("InfluxDB connection test successful")
                return True
            else:
                logger.error(f"InfluxDB health check failed: {health.message}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            return False