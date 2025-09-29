"""
Spoofing Detection API Routes
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from ..models.spoofing_models import (
    SpoofingAlert,
    SpoofingAnalysis,
    SpoofingIndicators,
    OrderLifecycle,
    LayeringPattern,
    SuspiciousOrderTracking,
    ManipulationSummary,
    AlertSeverity
)
from ..services.influxdb_service import InfluxDBService
from ..services.spoofing_detector import SpoofingDetector

router = APIRouter(prefix="/spoofing", tags=["Spoofing Detection"])

# Initialize spoofing detector
detector = SpoofingDetector()


def get_db_service():
    """Dependency to get InfluxDB service"""
    return InfluxDBService()


@router.get("/alerts", response_model=List[SpoofingAlert])
async def get_spoofing_alerts(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    severity: Optional[AlertSeverity] = Query(None, description="Filter by severity"),
    limit: int = Query(50, ge=1, le=200, description="Number of alerts to return"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get real-time spoofing alerts

    Returns recent spoofing alerts filtered by symbol and severity
    """
    try:
        # Get recent alerts from detector
        alerts = list(detector.recent_alerts)

        # Filter by symbol if provided
        if symbol:
            alerts = [a for a in alerts if a.symbol == symbol]

        # Filter by severity if provided
        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        # Sort by timestamp (most recent first)
        alerts.sort(key=lambda x: x.timestamp, reverse=True)

        # Limit results
        return alerts[:limit]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analysis/{symbol}", response_model=SpoofingAnalysis)
async def get_spoofing_analysis(
    symbol: str,
    period: str = Query("1h", description="Analysis period (e.g., 1h, 24h, 7d)"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get comprehensive spoofing analysis for a symbol

    Provides detailed analysis including indicators, alerts, and recommendations
    """
    try:
        # Get current order book
        orderbook = await db.get_current_orderbook(symbol)

        # Get recent whale orders
        whales = await db.get_recent_whales(symbol, limit=100)

        # Get order history (would need to implement in InfluxDB service)
        order_history = []  # Placeholder - would fetch from InfluxDB

        # Perform analysis
        analysis = detector.analyze_symbol(
            symbol=symbol,
            orderbook=orderbook,
            whale_orders=whales,
            order_history=order_history,
            analysis_period=period
        )

        return analysis

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indicators/{symbol}", response_model=SpoofingIndicators)
async def get_spoofing_indicators(
    symbol: str,
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get real-time spoofing indicators for a symbol

    Returns current manipulation metrics and scores
    """
    try:
        # Get required data
        orderbook = await db.get_current_orderbook(symbol)
        whales = await db.get_recent_whales(symbol, limit=50)
        order_history = []  # Placeholder

        # Calculate indicators
        indicators = detector.calculate_indicators(
            symbol=symbol,
            orderbook=orderbook,
            whale_orders=whales,
            order_history=order_history
        )

        return indicators

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/layering", response_model=List[LayeringPattern])
async def get_layering_patterns(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    min_layers: int = Query(3, ge=2, le=10, description="Minimum number of layers"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Detect layering patterns in order books

    Returns detected layering/spoofing walls
    """
    try:
        patterns = []

        # Get symbols to analyze
        symbols = [symbol] if symbol else ["BTC_USDT", "ETH_USDT", "WIF_USDT"]

        for sym in symbols:
            orderbook = await db.get_current_orderbook(sym)

            # Detect layering
            pattern = detector.detect_layering(
                orderbook=orderbook,
                min_levels=min_layers
            )

            if pattern:
                patterns.append(pattern)

        return patterns

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suspicious-orders", response_model=SuspiciousOrderTracking)
async def get_suspicious_orders(
    symbol: str,
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Track suspicious whale orders

    Returns currently tracked suspicious orders with lifecycle information
    """
    try:
        # Get whale orders
        whales = await db.get_recent_whales(symbol, limit=50)

        # Track suspicious orders
        tracking = detector.track_suspicious_orders(
            symbol=symbol,
            whale_orders=whales
        )

        return tracking

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/flash-orders", response_model=List[Dict])
async def get_flash_orders(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    time_window_ms: int = Query(5000, ge=1000, le=30000, description="Flash order time window in milliseconds"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get detected flash orders

    Returns orders that appeared and disappeared within the specified time window
    """
    try:
        # Get flash orders from detector history
        flash_orders = list(detector.flash_order_history)

        # Filter by symbol if provided
        if symbol:
            flash_orders = [f for f in flash_orders if f.symbol == symbol]

        # Filter by time window
        flash_orders = [
            f for f in flash_orders
            if f.lifespan_ms <= time_window_ms
        ]

        # Sort by timestamp (most recent first)
        flash_orders.sort(key=lambda x: x.timestamp, reverse=True)

        # Convert to dict for response
        return [f.dict() for f in flash_orders[:50]]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=ManipulationSummary)
async def get_manipulation_summary(
    period: str = Query("24h", description="Summary period (e.g., 1h, 24h, 7d)"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get market manipulation summary

    Returns overview of manipulation activity across all monitored symbols
    """
    try:
        # Parse period
        if period == "1h":
            time_delta = timedelta(hours=1)
        elif period == "24h":
            time_delta = timedelta(days=1)
        elif period == "7d":
            time_delta = timedelta(days=7)
        else:
            time_delta = timedelta(days=1)

        # Get alerts within period
        cutoff_time = datetime.now() - time_delta
        recent_alerts = [
            a for a in detector.recent_alerts
            if a.timestamp > cutoff_time
        ]

        # Count by symbol
        symbol_counts = {}
        pattern_counts = {}

        for alert in recent_alerts:
            # Count by symbol
            if alert.symbol not in symbol_counts:
                symbol_counts[alert.symbol] = {
                    'count': 0,
                    'severity_sum': 0,
                    'patterns': []
                }
            symbol_counts[alert.symbol]['count'] += 1
            symbol_counts[alert.symbol]['patterns'].append(alert.pattern_type.value)

            # Count by pattern
            pattern = alert.pattern_type.value
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

        # Most manipulated symbols
        most_manipulated = [
            {
                'symbol': sym,
                'alert_count': data['count'],
                'most_common_pattern': max(set(data['patterns']), key=data['patterns'].count) if data['patterns'] else None
            }
            for sym, data in sorted(symbol_counts.items(), key=lambda x: x[1]['count'], reverse=True)
        ][:10]

        # Determine overall risk
        total_alerts = len(recent_alerts)
        if total_alerts > 100:
            overall_risk = AlertSeverity.CRITICAL
        elif total_alerts > 50:
            overall_risk = AlertSeverity.HIGH
        elif total_alerts > 20:
            overall_risk = AlertSeverity.MEDIUM
        else:
            overall_risk = AlertSeverity.LOW

        # Symbols at risk (those with high alert counts)
        symbols_at_risk = [
            sym for sym, data in symbol_counts.items()
            if data['count'] > 10
        ]

        return ManipulationSummary(
            period=period,
            timestamp=datetime.now(),
            most_manipulated_symbols=most_manipulated,
            pattern_counts=pattern_counts,
            peak_manipulation_hours=[],  # Would need hourly analysis
            overall_market_risk=overall_risk,
            symbols_at_risk=symbols_at_risk,
            estimated_false_volume=None,  # Would need volume analysis
            affected_traders_estimate=None  # Would need trader analysis
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-orderbook")
async def analyze_orderbook_snapshot(
    orderbook_data: Dict,
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Analyze a specific order book snapshot for spoofing

    Accepts order book data and returns immediate spoofing analysis
    """
    try:
        symbol = orderbook_data.get('symbol', 'UNKNOWN')

        # Detect patterns
        layering = detector.detect_layering(orderbook_data)

        # Get indicators (simplified without history)
        indicators = SpoofingIndicators(
            symbol=symbol,
            timestamp=datetime.now(),
            cancellation_rate=0,
            flash_order_rate=0,
            layering_score=100 if layering else 0,
            quote_stuffing_rate=0,
            modification_rate=0,
            phantom_liquidity_ratio=0,
            suspicious_whale_count=0,
            overall_manipulation_score=50 if layering else 10
        )

        # Create response
        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "layering_detected": layering is not None,
            "layering_details": layering.dict() if layering else None,
            "indicators": indicators.dict(),
            "risk_assessment": "HIGH" if layering else "LOW"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_detection_config():
    """
    Get current spoofing detection configuration

    Returns thresholds and parameters used for detection
    """
    return {
        "flash_order_threshold_ms": detector.FLASH_ORDER_THRESHOLD_MS,
        "high_cancellation_rate": detector.HIGH_CANCELLATION_RATE,
        "layering_min_levels": detector.LAYERING_MIN_LEVELS,
        "quote_stuffing_rate": detector.QUOTE_STUFFING_RATE,
        "whale_value_threshold": detector.WHALE_VALUE_THRESHOLD,
        "detection_enabled": True,
        "alert_queue_size": len(detector.recent_alerts)
    }