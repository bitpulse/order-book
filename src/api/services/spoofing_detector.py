"""
Spoofing Detection Service
Analyzes order book data to identify potential market manipulation patterns
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict, deque
import statistics
from loguru import logger
import uuid

from ..models.spoofing_models import (
    SpoofingAlert,
    SpoofingIndicators,
    SpoofingAnalysis,
    OrderLifecycle,
    LayeringPattern,
    FlashOrderEvent,
    QuoteStuffingEvent,
    SuspiciousOrderTracking,
    SpoofingPatternType,
    AlertSeverity
)


class SpoofingDetector:
    """
    Detects various spoofing patterns in order book data
    """

    def __init__(self):
        # Thresholds for detection
        self.FLASH_ORDER_THRESHOLD_MS = 10000  # 10 seconds (more lenient for detection)
        self.HIGH_CANCELLATION_RATE = 85  # 85% cancellation rate
        self.LAYERING_MIN_LEVELS = 2  # Minimum levels for layering (lowered for better detection)
        self.QUOTE_STUFFING_RATE = 10  # Orders per second
        self.WHALE_VALUE_THRESHOLD = 30000  # $30K minimum (lowered to catch more whales)

        # Tracking data structures
        self.order_tracker: Dict[str, OrderLifecycle] = {}
        self.recent_alerts: deque = deque(maxlen=100)
        self.symbol_indicators: Dict[str, SpoofingIndicators] = {}
        self.flash_order_history: deque = deque(maxlen=1000)

        # Track whale history for comparison
        self.previous_whales: Dict[str, List[Dict]] = {}
        self.whale_timestamps: Dict[str, datetime] = {}

    def calculate_spoofing_probability(self, order: OrderLifecycle) -> float:
        """
        Calculate probability that an order is spoofing based on multiple factors
        """
        score = 0.0
        factors = 0

        # Factor 1: Lifespan (shorter = more suspicious)
        if order.lifespan_seconds:
            factors += 1
            if order.lifespan_seconds < 1:
                score += 30
            elif order.lifespan_seconds < 5:
                score += 20
            elif order.lifespan_seconds < 10:
                score += 10

        # Factor 2: Value (larger = more impactful)
        if order.value_usdt:
            factors += 1
            if order.value_usdt > 1000000:
                score += 25
            elif order.value_usdt > 500000:
                score += 20
            elif order.value_usdt > 100000:
                score += 15
            elif order.value_usdt > 50000:
                score += 10

        # Factor 3: Modifications (more = more suspicious)
        factors += 1
        if order.modifications > 10:
            score += 20
        elif order.modifications > 5:
            score += 15
        elif order.modifications > 2:
                score += 10

        # Factor 4: Status (cancelled = suspicious)
        if order.status == "cancelled":
            score += 15

        # Factor 5: Distance from mid (specific range = suspicious)
        # (Would need mid-price data to calculate)

        # Normalize to 0-100
        return min(score, 100)

    def detect_flash_orders(
        self,
        current_whales: List[Dict],
        symbol: str
    ) -> List[FlashOrderEvent]:
        """
        Detect flash orders that appear and disappear quickly
        """
        flash_orders = []

        # Get previous whales for this symbol
        previous_whales = self.previous_whales.get(symbol, [])
        previous_time = self.whale_timestamps.get(symbol)

        # Store current whales for next comparison
        self.previous_whales[symbol] = current_whales.copy()
        self.whale_timestamps[symbol] = datetime.now()

        if not previous_whales or not previous_time:
            return flash_orders  # Can't detect on first run

        # Calculate time difference
        time_diff_ms = (datetime.now() - previous_time).total_seconds() * 1000

        # Create lookups for comparison
        current_lookup = {
            f"{w.get('price', 0):.4f}_{w.get('side', '')}_{w.get('volume', 0):.0f}": w
            for w in current_whales
        }
        prev_lookup = {
            f"{w.get('price', 0):.4f}_{w.get('side', '')}_{w.get('volume', 0):.0f}": w
            for w in previous_whales
        }

        # Find whales that disappeared (were in previous but not in current)
        for whale_key, whale in prev_lookup.items():
            if whale_key not in current_lookup:
                # This whale disappeared!
                if time_diff_ms < self.FLASH_ORDER_THRESHOLD_MS:
                    flash_order = FlashOrderEvent(
                        symbol=symbol,
                        timestamp=datetime.now(),
                        order_id=str(uuid.uuid4()),
                        side=whale.get('side', 'unknown'),
                        price=float(whale.get('price', 0)),
                        volume=float(whale.get('volume', 0)),
                        value_usdt=float(whale.get('value_usdt', 0)),
                        lifespan_ms=int(time_diff_ms),
                        price_movement=None
                    )
                    flash_orders.append(flash_order)
                    self.flash_order_history.append(flash_order)

                    # Create alert for this flash order
                    self.create_alert(
                        symbol=symbol,
                        pattern_type=SpoofingPatternType.FLASH_ORDER,
                        severity=AlertSeverity.HIGH,
                        confidence=90.0,
                        description=f"Flash order detected: ${whale.get('value_usdt', 0):,.0f} disappeared in {time_diff_ms:.0f}ms",
                        evidence={'flash_order': flash_order.dict()}
                    )

        return flash_orders

    def detect_layering(
        self,
        orderbook: Dict[str, Any],
        min_levels: int = 2,
        value_threshold: float = 30000
    ) -> Optional[LayeringPattern]:
        """
        Detect layering patterns in the order book
        """
        for side in ['bids', 'asks']:
            levels = orderbook.get(side, [])
            if len(levels) < min_levels:
                continue

            # Look for multiple large orders at consecutive levels
            large_orders = []
            for i, level in enumerate(levels[:10]):  # Check top 10 levels
                if level.get('total_value', 0) > value_threshold:
                    large_orders.append((i, level))

            # Check if we have enough consecutive large orders
            if len(large_orders) >= min_levels:
                # Check if orders are at consecutive or near-consecutive levels
                consecutive_count = 1
                for i in range(1, len(large_orders)):
                    if large_orders[i][0] - large_orders[i-1][0] <= 2:  # Allow 1 level gap
                        consecutive_count += 1
                    else:
                        consecutive_count = 1

                    if consecutive_count >= min_levels:
                        # Layering detected
                        layer_details = [
                            {
                                'level': order[0],
                                'price': order[1].get('price'),
                                'volume': order[1].get('volume'),
                                'value': order[1].get('total_value')
                            }
                            for order in large_orders[i-consecutive_count+1:i+1]
                        ]

                        total_volume = sum(d['volume'] for d in layer_details)
                        total_value = sum(d['value'] for d in layer_details)
                        prices = [d['price'] for d in layer_details]

                        return LayeringPattern(
                            symbol=orderbook.get('symbol', 'UNKNOWN'),
                            timestamp=datetime.now(),
                            side=side[:-1],  # Remove 's' from bids/asks
                            num_layers=consecutive_count,
                            total_volume=total_volume,
                            total_value=total_value,
                            price_range={'min': min(prices), 'max': max(prices)},
                            distance_from_mid=0,  # Would need mid-price
                            layer_details=layer_details,
                            movement_detected=False
                        )

        return None

    def detect_quote_stuffing(
        self,
        order_events: List[Dict],
        time_window_seconds: int = 1
    ) -> Optional[QuoteStuffingEvent]:
        """
        Detect quote stuffing based on high order placement/cancellation rate
        """
        if not order_events:
            return None

        # Group events by time window
        now = datetime.now()
        recent_events = [
            e for e in order_events
            if (now - datetime.fromisoformat(e['timestamp'])).total_seconds() < time_window_seconds
        ]

        if len(recent_events) < self.QUOTE_STUFFING_RATE:
            return None

        # Calculate rates
        order_rate = len(recent_events) / time_window_seconds
        cancelled_count = sum(1 for e in recent_events if e.get('status') == 'cancelled')
        modification_count = sum(e.get('modifications', 0) for e in recent_events)

        if order_rate > self.QUOTE_STUFFING_RATE:
            return QuoteStuffingEvent(
                symbol=recent_events[0].get('symbol', 'UNKNOWN'),
                timestamp=now,
                duration_seconds=time_window_seconds,
                order_rate=order_rate,
                modification_rate=modification_count / time_window_seconds,
                affected_price_levels=len(set(e.get('price') for e in recent_events)),
                total_orders_placed=len(recent_events),
                total_orders_cancelled=cancelled_count
            )

        return None

    def calculate_indicators(
        self,
        symbol: str,
        orderbook: Dict,
        whale_orders: List[Dict],
        order_history: List[Dict]
    ) -> SpoofingIndicators:
        """
        Calculate real-time spoofing indicators for a symbol
        """
        # Cancellation rate
        if order_history:
            cancelled = sum(1 for o in order_history if o.get('status') == 'cancelled')
            cancellation_rate = (cancelled / len(order_history)) * 100
        else:
            cancellation_rate = 0

        # Flash order rate
        flash_count = sum(1 for f in self.flash_order_history if f.symbol == symbol)
        flash_order_rate = min((flash_count / max(len(order_history), 1)) * 100, 100)

        # Layering score
        layering = self.detect_layering(orderbook)
        layering_score = 100 if layering else 0

        # Quote stuffing rate (orders per second in last minute)
        recent_orders = [
            o for o in order_history
            if (datetime.now() - datetime.fromisoformat(o['timestamp'])).total_seconds() < 60
        ]
        quote_stuffing_rate = len(recent_orders) / 60 if recent_orders else 0

        # Modification rate
        total_mods = sum(o.get('modifications', 0) for o in order_history)
        modification_rate = total_mods / max(len(order_history), 1)

        # Phantom liquidity ratio
        filled = sum(1 for o in order_history if o.get('status') == 'filled')
        phantom_ratio = cancellation_rate / max(filled, 1) if filled else 0

        # Suspicious whale count
        suspicious_whales = sum(
            1 for w in whale_orders
            if w.get('distance_from_mid', 0) < 2 and w.get('value_usdt', 0) > 100000
        )

        # Overall manipulation score (weighted average)
        weights = {
            'cancellation': 0.25,
            'flash': 0.20,
            'layering': 0.25,
            'stuffing': 0.15,
            'phantom': 0.15
        }

        manipulation_score = (
            weights['cancellation'] * min(cancellation_rate, 100) +
            weights['flash'] * flash_order_rate +
            weights['layering'] * layering_score +
            weights['stuffing'] * min(quote_stuffing_rate * 10, 100) +
            weights['phantom'] * min(phantom_ratio * 10, 100)
        )

        return SpoofingIndicators(
            symbol=symbol,
            timestamp=datetime.now(),
            cancellation_rate=cancellation_rate,
            flash_order_rate=flash_order_rate,
            layering_score=layering_score,
            quote_stuffing_rate=quote_stuffing_rate,
            modification_rate=modification_rate,
            phantom_liquidity_ratio=phantom_ratio,
            suspicious_whale_count=suspicious_whales,
            overall_manipulation_score=min(manipulation_score, 100)
        )

    def create_alert(
        self,
        symbol: str,
        pattern_type: SpoofingPatternType,
        severity: AlertSeverity,
        confidence: float,
        description: str,
        evidence: Dict = None
    ) -> SpoofingAlert:
        """
        Create a spoofing alert
        """
        alert = SpoofingAlert(
            alert_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            symbol=symbol,
            pattern_type=pattern_type,
            severity=severity,
            confidence_score=confidence,
            description=description,
            evidence=evidence or {}
        )

        self.recent_alerts.append(alert)
        return alert

    def analyze_symbol(
        self,
        symbol: str,
        orderbook: Dict,
        whale_orders: List[Dict],
        order_history: List[Dict],
        analysis_period: str = "1h"
    ) -> SpoofingAnalysis:
        """
        Perform comprehensive spoofing analysis for a symbol
        """
        # Calculate current indicators
        indicators = self.calculate_indicators(symbol, orderbook, whale_orders, order_history)

        # Detect patterns and create alerts
        alerts = []

        # Check for flash orders
        flash_orders = self.detect_flash_orders(whale_orders, symbol)
        if flash_orders:
            alert = self.create_alert(
                symbol=symbol,
                pattern_type=SpoofingPatternType.FLASH_ORDER,
                severity=AlertSeverity.HIGH if len(flash_orders) > 3 else AlertSeverity.MEDIUM,
                confidence=85.0,
                description=f"Detected {len(flash_orders)} flash orders",
                evidence={'flash_orders': [f.dict() for f in flash_orders[:5]]}
            )
            alerts.append(alert)

        # Check for layering
        layering = self.detect_layering(orderbook)
        if layering:
            alert = self.create_alert(
                symbol=symbol,
                pattern_type=SpoofingPatternType.LAYERING,
                severity=AlertSeverity.HIGH if layering.num_layers > 5 else AlertSeverity.MEDIUM,
                confidence=90.0,
                description=f"Layering detected with {layering.num_layers} levels",
                evidence={'layering': layering.dict()}
            )
            alerts.append(alert)

        # Check for quote stuffing
        stuffing = self.detect_quote_stuffing(order_history)
        if stuffing:
            alert = self.create_alert(
                symbol=symbol,
                pattern_type=SpoofingPatternType.QUOTE_STUFFING,
                severity=AlertSeverity.MEDIUM,
                confidence=75.0,
                description=f"Quote stuffing detected: {stuffing.order_rate:.1f} orders/sec",
                evidence={'stuffing': stuffing.dict()}
            )
            alerts.append(alert)

        # Track suspicious orders
        tracked_orders = []
        for whale in whale_orders[:10]:  # Track top 10 whales
            lifecycle = OrderLifecycle(
                order_id=str(uuid.uuid4()),
                symbol=symbol,
                side=whale.get('side', 'unknown'),
                price=whale.get('price', 0),
                volume=whale.get('volume', 0),
                value_usdt=whale.get('value_usdt', 0),
                created_at=datetime.now(),
                status='active',
                modifications=0
            )
            lifecycle.spoofing_probability = self.calculate_spoofing_probability(lifecycle)
            tracked_orders.append(lifecycle)

        # Pattern distribution
        pattern_dist = defaultdict(int)
        for alert in self.recent_alerts:
            if alert.symbol == symbol:
                pattern_dist[alert.pattern_type.value] += 1

        # Determine risk level
        if indicators.overall_manipulation_score > 75:
            risk_level = AlertSeverity.CRITICAL
            action = "High manipulation detected. Consider halting trading or increasing monitoring."
        elif indicators.overall_manipulation_score > 50:
            risk_level = AlertSeverity.HIGH
            action = "Significant manipulation indicators. Increase monitoring and consider risk limits."
        elif indicators.overall_manipulation_score > 25:
            risk_level = AlertSeverity.MEDIUM
            action = "Moderate manipulation activity. Continue monitoring."
        else:
            risk_level = AlertSeverity.LOW
            action = "Normal market activity. Standard monitoring sufficient."

        return SpoofingAnalysis(
            symbol=symbol,
            analysis_period=analysis_period,
            timestamp=datetime.now(),
            indicators=indicators,
            recent_alerts=alerts,
            alert_count_24h=len([a for a in self.recent_alerts if a.symbol == symbol]),
            pattern_distribution=dict(pattern_dist),
            most_common_pattern=max(pattern_dist, key=pattern_dist.get) if pattern_dist else None,
            tracked_orders=tracked_orders,
            avg_suspicious_lifespan=statistics.mean([o.lifespan_seconds for o in tracked_orders if o.lifespan_seconds]) if any(o.lifespan_seconds for o in tracked_orders) else None,
            risk_level=risk_level,
            recommended_action=action
        )

    def track_suspicious_orders(
        self,
        symbol: str,
        whale_orders: List[Dict]
    ) -> SuspiciousOrderTracking:
        """
        Track suspicious whale orders over time
        """
        active_suspicious = []
        recently_cancelled = []

        for whale in whale_orders:
            # Create lifecycle tracking
            lifecycle = OrderLifecycle(
                order_id=str(uuid.uuid4()),
                symbol=symbol,
                side=whale.get('side', 'unknown'),
                price=whale.get('price', 0),
                volume=whale.get('volume', 0),
                value_usdt=whale.get('value_usdt', 0),
                created_at=datetime.now(),
                status='active'
            )

            # Calculate spoofing probability
            lifecycle.spoofing_probability = self.calculate_spoofing_probability(lifecycle)

            if lifecycle.spoofing_probability > 50:
                active_suspicious.append(lifecycle)

        # Calculate statistics
        total_tracked = len(active_suspicious) + len(recently_cancelled)
        avg_lifespan = statistics.mean(
            [o.lifespan_seconds for o in recently_cancelled if o.lifespan_seconds]
        ) if recently_cancelled and any(o.lifespan_seconds for o in recently_cancelled) else 0

        cancellation_ratio = (
            len(recently_cancelled) / total_tracked if total_tracked > 0 else 0
        )

        # Detect patterns
        coordinated = self._detect_coordinated_movement(active_suspicious)
        wall_building = self._detect_wall_building(active_suspicious)
        price_herding = self._detect_price_herding(active_suspicious)

        return SuspiciousOrderTracking(
            symbol=symbol,
            timestamp=datetime.now(),
            active_suspicious=active_suspicious,
            recently_cancelled=recently_cancelled,
            total_tracked=total_tracked,
            avg_lifespan=avg_lifespan,
            cancellation_ratio=cancellation_ratio,
            coordinated_movement=coordinated,
            wall_building=wall_building,
            price_herding=price_herding
        )

    def _detect_coordinated_movement(self, orders: List[OrderLifecycle]) -> bool:
        """Detect if orders move in coordination"""
        if len(orders) < 3:
            return False

        # Check if multiple orders at similar price levels
        prices = [o.price for o in orders]
        if prices:
            price_std = statistics.stdev(prices) if len(prices) > 1 else 0
            avg_price = statistics.mean(prices)
            # If standard deviation is less than 1% of average, likely coordinated
            return price_std < (avg_price * 0.01) if avg_price > 0 else False
        return False

    def _detect_wall_building(self, orders: List[OrderLifecycle]) -> bool:
        """Detect wall building activity"""
        if len(orders) < 3:
            return False

        # Check for multiple large orders on same side
        bid_value = sum(o.value_usdt for o in orders if o.side == 'bid')
        ask_value = sum(o.value_usdt for o in orders if o.side == 'ask')

        # Wall detected if one side has significantly more value
        total_value = bid_value + ask_value
        if total_value > 500000:  # Significant value
            ratio = max(bid_value, ask_value) / total_value
            return ratio > 0.8  # 80% on one side

        return False

    def _detect_price_herding(self, orders: List[OrderLifecycle]) -> bool:
        """Detect attempts to herd price in a direction"""
        if len(orders) < 3:
            return False

        # Check if orders are progressively moving in one direction
        bid_orders = sorted([o for o in orders if o.side == 'bid'], key=lambda x: x.price)
        ask_orders = sorted([o for o in orders if o.side == 'ask'], key=lambda x: x.price)

        # Check for progressive pricing (herding pattern)
        if len(bid_orders) >= 3:
            prices = [o.price for o in bid_orders]
            # Check if prices are in ascending order with similar gaps
            gaps = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
            if gaps and all(g > 0 for g in gaps):
                gap_std = statistics.stdev(gaps) if len(gaps) > 1 else 0
                avg_gap = statistics.mean(gaps)
                # Similar gaps indicate herding pattern
                return gap_std < (avg_gap * 0.2) if avg_gap > 0 else False

        return False