from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from loguru import logger
import time


@dataclass
class OrderLevel:
    """Represents a single order book level"""
    price: float
    volume: float
    order_count: int = 0
    total_value: float = field(init=False)

    def __post_init__(self):
        self.total_value = self.price * self.volume


@dataclass
class OrderBookSnapshot:
    """Represents a complete order book snapshot"""
    symbol: str
    exchange: str
    bids: List[OrderLevel]
    asks: List[OrderLevel]
    timestamp: int
    version: int = 0

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0

    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid if self.best_bid and self.best_ask else 0

    @property
    def spread_percentage(self) -> float:
        return (self.spread / self.best_ask * 100) if self.best_ask else 0

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2 if self.best_bid and self.best_ask else 0

    @property
    def bid_volume_total(self) -> float:
        return sum(level.volume for level in self.bids)

    @property
    def ask_volume_total(self) -> float:
        return sum(level.volume for level in self.asks)

    @property
    def bid_value_total(self) -> float:
        return sum(level.total_value for level in self.bids)

    @property
    def ask_value_total(self) -> float:
        return sum(level.total_value for level in self.asks)

    @property
    def imbalance(self) -> float:
        total = self.bid_volume_total + self.ask_volume_total
        if total == 0:
            return 0
        return (self.bid_volume_total - self.ask_volume_total) / total


@dataclass
class MarketDepth:
    """Market depth at various percentage levels from mid price"""
    symbol: str
    exchange: str
    depth_percentage: float
    bid_volume: float
    ask_volume: float
    bid_orders: int
    ask_orders: int
    bid_value: float
    ask_value: float
    timestamp: int


@dataclass
class WhaleOrder:
    """Represents a whale order"""
    symbol: str
    exchange: str
    side: str  # "bid" or "ask"
    price: float
    volume: float
    value_usdt: float
    level: int
    distance_from_mid: float
    distance_from_mid_abs: float
    timestamp: int


class OrderBookProcessor:
    """Processes order book data from MEXC WebSocket"""

    def __init__(self, whale_thresholds_func):
        self.whale_thresholds_func = whale_thresholds_func
        self.depth_percentages = [0.1, 0.5, 1.0, 2.0, 5.0]

    def parse_message(self, message: Dict, symbol: str = None) -> Optional[OrderBookSnapshot]:
        """Parse WebSocket message into OrderBookSnapshot"""
        try:
            if message.get("channel") != "push.depth":
                return None

            data = message.get("data", {})

            # Use provided symbol or try to extract from message
            if not symbol:
                symbol = data.get("symbol", "UNKNOWN_USDT")

            # Parse bids and asks
            bids = self._parse_order_levels(data.get("bids", []))
            asks = self._parse_order_levels(data.get("asks", []))

            # Create snapshot
            snapshot = OrderBookSnapshot(
                symbol=symbol,
                exchange="MEXC",
                bids=bids,
                asks=asks,
                timestamp=data.get("timestamp", int(time.time() * 1000)),
                version=data.get("version", 0)
            )

            logger.debug(f"Parsed order book for {symbol}: {len(bids)} bids, {len(asks)} asks")
            return snapshot

        except Exception as e:
            logger.error(f"Failed to parse message: {e}")
            return None

    def _parse_order_levels(self, levels: List) -> List[OrderLevel]:
        """Parse raw order levels into OrderLevel objects"""
        parsed_levels = []
        for level in levels:
            try:
                if len(level) >= 2:
                    price = float(level[0])
                    volume = float(level[1])
                    order_count = int(level[2]) if len(level) > 2 else 0

                    parsed_levels.append(OrderLevel(
                        price=price,
                        volume=volume,
                        order_count=order_count
                    ))
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse level {level}: {e}")
                continue

        return parsed_levels

    def calculate_market_depth(self, snapshot: OrderBookSnapshot) -> List[MarketDepth]:
        """Calculate market depth at various percentage levels"""
        depths = []
        mid_price = snapshot.mid_price

        if mid_price == 0:
            return depths

        for depth_pct in self.depth_percentages:
            bid_threshold = mid_price * (1 - depth_pct / 100)
            ask_threshold = mid_price * (1 + depth_pct / 100)

            # Calculate bid side depth
            bid_volume = 0
            bid_orders = 0
            bid_value = 0
            for level in snapshot.bids:
                if level.price >= bid_threshold:
                    bid_volume += level.volume
                    bid_orders += level.order_count if level.order_count else 1
                    bid_value += level.total_value

            # Calculate ask side depth
            ask_volume = 0
            ask_orders = 0
            ask_value = 0
            for level in snapshot.asks:
                if level.price <= ask_threshold:
                    ask_volume += level.volume
                    ask_orders += level.order_count if level.order_count else 1
                    ask_value += level.total_value

            depths.append(MarketDepth(
                symbol=snapshot.symbol,
                exchange=snapshot.exchange,
                depth_percentage=depth_pct,
                bid_volume=bid_volume,
                ask_volume=ask_volume,
                bid_orders=bid_orders,
                ask_orders=ask_orders,
                bid_value=bid_value,
                ask_value=ask_value,
                timestamp=snapshot.timestamp
            ))

        return depths

    def detect_whale_orders(self, snapshot: OrderBookSnapshot) -> List[WhaleOrder]:
        """Detect whale orders in the order book"""
        whales = []
        thresholds = self.whale_thresholds_func(snapshot.symbol)
        mid_price = snapshot.mid_price

        # Use only the "large" threshold as minimum for whale detection
        whale_min_value = thresholds.get("large", 50000)

        if mid_price == 0:
            return whales

        # Check bid side
        for level_idx, level in enumerate(snapshot.bids, 1):
            if level.total_value >= whale_min_value:
                whales.append(WhaleOrder(
                    symbol=snapshot.symbol,
                    exchange=snapshot.exchange,
                    side="bid",
                    price=level.price,
                    volume=level.volume,
                    value_usdt=level.total_value,
                    level=level_idx,
                    distance_from_mid=abs((level.price - mid_price) / mid_price * 100),
                    distance_from_mid_abs=abs(level.price - mid_price),
                    timestamp=snapshot.timestamp
                ))

        # Check ask side
        for level_idx, level in enumerate(snapshot.asks, 1):
            if level.total_value >= whale_min_value:
                whales.append(WhaleOrder(
                    symbol=snapshot.symbol,
                    exchange=snapshot.exchange,
                    side="ask",
                    price=level.price,
                    volume=level.volume,
                    value_usdt=level.total_value,
                    level=level_idx,
                    distance_from_mid=abs((level.price - mid_price) / mid_price * 100),
                    distance_from_mid_abs=abs(level.price - mid_price),
                    timestamp=snapshot.timestamp
                ))

        if whales:
            logger.info(f"Detected {len(whales)} whale orders in {snapshot.symbol}")

        return whales


    def process(self, message: Dict) -> Tuple[
        Optional[OrderBookSnapshot],
        List[MarketDepth],
        List[WhaleOrder]
    ]:
        """Process incoming order book message"""
        # Extract symbol if it's in the message
        symbol = message.get("symbol")
        snapshot = self.parse_message(message, symbol)
        if not snapshot:
            return None, [], []

        # Calculate market depth
        depths = self.calculate_market_depth(snapshot)

        # Detect whale orders
        whales = self.detect_whale_orders(snapshot)

        return snapshot, depths, whales