"""
Pydantic models for spoofing detection and analysis
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class SpoofingPatternType(str, Enum):
    """Types of spoofing patterns"""
    FLASH_ORDER = "flash_order"
    LAYERING = "layering"
    QUOTE_STUFFING = "quote_stuffing"
    MOMENTUM_IGNITION = "momentum_ignition"
    WASH_TRADING = "wash_trading"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class OrderLifecycle(BaseModel):
    """Track an order's lifecycle for spoofing detection"""
    order_id: str = Field(..., description="Unique order identifier")
    symbol: str = Field(..., description="Trading pair")
    side: str = Field(..., description="bid or ask")
    price: float = Field(..., description="Order price")
    volume: float = Field(..., description="Order volume")
    value_usdt: float = Field(..., description="Order value in USDT")
    created_at: datetime = Field(..., description="Order creation time")
    cancelled_at: Optional[datetime] = Field(None, description="Order cancellation time")
    lifespan_seconds: Optional[float] = Field(None, description="Order lifespan in seconds")
    modifications: int = Field(0, description="Number of modifications")
    status: str = Field(..., description="Current status: active, filled, cancelled")
    spoofing_probability: Optional[float] = Field(None, description="Probability of being spoofing (0-100)")


class SpoofingAlert(BaseModel):
    """Individual spoofing alert"""
    alert_id: str = Field(..., description="Unique alert identifier")
    timestamp: datetime = Field(..., description="Alert timestamp")
    symbol: str = Field(..., description="Trading pair")
    pattern_type: SpoofingPatternType = Field(..., description="Type of spoofing pattern detected")
    severity: AlertSeverity = Field(..., description="Alert severity")
    confidence_score: float = Field(..., description="Confidence score (0-100)")
    description: str = Field(..., description="Human-readable description")
    affected_orders: List[str] = Field(default_factory=list, description="List of affected order IDs")
    price_impact: Optional[float] = Field(None, description="Estimated price impact percentage")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Supporting evidence")


class LayeringPattern(BaseModel):
    """Detected layering/stacking pattern"""
    symbol: str = Field(..., description="Trading pair")
    timestamp: datetime = Field(..., description="Detection timestamp")
    side: str = Field(..., description="Side of the book affected")
    num_layers: int = Field(..., description="Number of layers detected")
    total_volume: float = Field(..., description="Total volume across layers")
    total_value: float = Field(..., description="Total value in USDT")
    price_range: Dict[str, float] = Field(..., description="Price range of layers")
    distance_from_mid: float = Field(..., description="Average distance from mid-price (%)")
    layer_details: List[Dict[str, Any]] = Field(..., description="Details of each layer")
    movement_detected: bool = Field(False, description="Whether layers moved when price approached")


class SpoofingIndicators(BaseModel):
    """Real-time spoofing indicators for a symbol"""
    symbol: str = Field(..., description="Trading pair")
    timestamp: datetime = Field(..., description="Calculation timestamp")
    cancellation_rate: float = Field(..., description="Order cancellation rate (0-100)")
    flash_order_rate: float = Field(..., description="Flash order rate (0-100)")
    layering_score: float = Field(..., description="Layering detection score (0-100)")
    quote_stuffing_rate: float = Field(..., description="Quote stuffing rate (orders/sec)")
    modification_rate: float = Field(..., description="Order modification rate (mods/sec)")
    phantom_liquidity_ratio: float = Field(..., description="Ratio of cancelled to filled orders")
    suspicious_whale_count: int = Field(..., description="Number of suspicious whale orders")
    overall_manipulation_score: float = Field(..., description="Overall manipulation score (0-100)")


class SpoofingAnalysis(BaseModel):
    """Comprehensive spoofing analysis for a symbol"""
    symbol: str = Field(..., description="Trading pair")
    analysis_period: str = Field(..., description="Analysis time period")
    timestamp: datetime = Field(..., description="Analysis timestamp")

    # Current indicators
    indicators: SpoofingIndicators = Field(..., description="Current spoofing indicators")

    # Recent alerts
    recent_alerts: List[SpoofingAlert] = Field(default_factory=list, description="Recent alerts")
    alert_count_24h: int = Field(0, description="Alert count in last 24 hours")

    # Pattern statistics
    pattern_distribution: Dict[str, int] = Field(default_factory=dict, description="Distribution of pattern types")
    most_common_pattern: Optional[SpoofingPatternType] = Field(None, description="Most common pattern")

    # Lifecycle tracking
    tracked_orders: List[OrderLifecycle] = Field(default_factory=list, description="Currently tracked orders")
    avg_suspicious_lifespan: Optional[float] = Field(None, description="Average lifespan of suspicious orders")

    # Risk assessment
    risk_level: AlertSeverity = Field(..., description="Overall risk level")
    recommended_action: Optional[str] = Field(None, description="Recommended action")


class FlashOrderEvent(BaseModel):
    """Flash order detection event"""
    symbol: str = Field(..., description="Trading pair")
    timestamp: datetime = Field(..., description="Event timestamp")
    order_id: str = Field(..., description="Order identifier")
    side: str = Field(..., description="Order side")
    price: float = Field(..., description="Order price")
    volume: float = Field(..., description="Order volume")
    value_usdt: float = Field(..., description="Order value")
    lifespan_ms: int = Field(..., description="Order lifespan in milliseconds")
    price_movement: Optional[float] = Field(None, description="Price movement during lifespan")
    influenced_orders: List[str] = Field(default_factory=list, description="Orders potentially influenced")


class QuoteStuffingEvent(BaseModel):
    """Quote stuffing detection event"""
    symbol: str = Field(..., description="Trading pair")
    timestamp: datetime = Field(..., description="Event timestamp")
    duration_seconds: float = Field(..., description="Duration of stuffing event")
    order_rate: float = Field(..., description="Orders per second during event")
    modification_rate: float = Field(..., description="Modifications per second")
    affected_price_levels: int = Field(..., description="Number of price levels affected")
    total_orders_placed: int = Field(..., description="Total orders placed during event")
    total_orders_cancelled: int = Field(..., description="Total orders cancelled")


class SuspiciousOrderTracking(BaseModel):
    """Track suspicious whale orders over time"""
    symbol: str = Field(..., description="Trading pair")
    timestamp: datetime = Field(..., description="Current timestamp")
    active_suspicious: List[OrderLifecycle] = Field(..., description="Currently active suspicious orders")
    recently_cancelled: List[OrderLifecycle] = Field(..., description="Recently cancelled suspicious orders")

    # Statistics
    total_tracked: int = Field(..., description="Total orders being tracked")
    avg_lifespan: float = Field(..., description="Average lifespan of tracked orders")
    cancellation_ratio: float = Field(..., description="Ratio of cancelled to filled")

    # Patterns
    coordinated_movement: bool = Field(False, description="Detected coordinated movement")
    wall_building: bool = Field(False, description="Detected wall building activity")
    price_herding: bool = Field(False, description="Detected price herding attempts")


class ManipulationSummary(BaseModel):
    """Summary of market manipulation activity"""
    period: str = Field(..., description="Summary period (e.g., '1h', '24h')")
    timestamp: datetime = Field(..., description="Summary timestamp")

    # By symbol
    most_manipulated_symbols: List[Dict[str, Any]] = Field(..., description="Symbols with most manipulation")

    # By pattern
    pattern_counts: Dict[str, int] = Field(..., description="Count by pattern type")

    # By time
    peak_manipulation_hours: List[int] = Field(..., description="Hours with peak manipulation (0-23)")

    # Risk metrics
    overall_market_risk: AlertSeverity = Field(..., description="Overall market manipulation risk")
    symbols_at_risk: List[str] = Field(..., description="Symbols currently at high risk")

    # Economic impact
    estimated_false_volume: Optional[float] = Field(None, description="Estimated false volume created")
    affected_traders_estimate: Optional[int] = Field(None, description="Estimated number of affected traders")