"""
Pydantic models for API responses
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class OrderLevel(BaseModel):
    """Single order book level"""
    price: float = Field(..., description="Price at this level")
    volume: float = Field(..., description="Volume in tokens")
    total_value: float = Field(..., description="Total value in USDT")


class OrderBookResponse(BaseModel):
    """Full order book response"""
    symbol: str = Field(..., description="Trading pair symbol")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    bids: List[Dict[str, float]] = Field(..., description="Bid levels")
    asks: List[Dict[str, float]] = Field(..., description="Ask levels")
    best_bid: Optional[float] = Field(None, description="Best bid price")
    best_ask: Optional[float] = Field(None, description="Best ask price")
    spread: Optional[float] = Field(None, description="Spread amount")
    spread_percentage: Optional[float] = Field(None, description="Spread percentage")


class OrderBookStats(BaseModel):
    """Order book statistics"""
    symbol: str
    timestamp: Optional[str]
    best_bid: Optional[float]
    best_ask: Optional[float]
    spread: Optional[float]
    spread_percentage: Optional[float]
    mid_price: Optional[float]
    bid_volume_total: Optional[float]
    ask_volume_total: Optional[float]
    bid_value_total: Optional[float]
    ask_value_total: Optional[float]
    imbalance: Optional[float]
    depth_10_bid: Optional[float]
    depth_10_ask: Optional[float]


class SpreadHistory(BaseModel):
    """Historical spread data point"""
    timestamp: str
    spread: Optional[float]
    spread_percentage: Optional[float]


class WhaleOrder(BaseModel):
    """Whale order details"""
    symbol: str
    timestamp: str
    side: str = Field(..., description="bid or ask")
    price: float
    volume: float
    value_usdt: float
    level: Optional[int] = Field(None, description="Position in order book")
    distance_from_mid: Optional[float] = Field(None, description="% distance from mid price")


class MarketDepth(BaseModel):
    """Market depth at a specific percentage"""
    depth_percentage: str
    timestamp: Optional[str]
    bid_volume: Optional[float]
    ask_volume: Optional[float]
    bid_orders: Optional[int]
    ask_orders: Optional[int]
    bid_value: Optional[float]
    ask_value: Optional[float]


class ImbalanceHistory(BaseModel):
    """Historical imbalance data point"""
    timestamp: str
    imbalance: float = Field(..., description="Order book imbalance (-1 to 1)")


class WhaleStatistics(BaseModel):
    """Whale order statistics"""
    period: str
    symbol: Optional[str]
    total_count: int
    bid_count: int
    ask_count: int
    average_value: Optional[float]
    categories: Optional[Dict[str, int]]


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None
    status_code: int


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    influxdb_connected: bool
    redis_connected: Optional[bool] = None
    uptime_seconds: Optional[float] = None