"""
Whale Tracking API Routes
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional

from ..models.responses import (
    WhaleOrder,
    WhaleStatistics,
    ErrorResponse
)
from ..services.influxdb_service import InfluxDBService

router = APIRouter(prefix="/whales", tags=["Whale Tracking"])


def get_db_service():
    """Dependency to get InfluxDB service"""
    return InfluxDBService()


@router.get("/recent", response_model=List[WhaleOrder])
async def get_recent_whales(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    min_value: float = Query(50000, ge=0, description="Minimum USD value"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get recent whale orders across all symbols or for a specific symbol

    Returns orders that exceed the minimum value threshold
    """
    try:
        whales = await db.get_recent_whales(symbol, limit, min_value)

        if not whales:
            return []  # Return empty list instead of 404

        return whales
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}", response_model=List[WhaleOrder])
async def get_symbol_whales(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
    min_value: float = Query(50000, ge=0),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get whale orders for a specific symbol

    Returns recent large orders for the specified trading pair
    """
    try:
        whales = await db.get_recent_whales(symbol, limit, min_value)

        if not whales:
            return []

        return whales
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary", response_model=WhaleStatistics)
async def get_whale_statistics(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    period: str = Query("-24h", description="Time period (e.g., -1h, -24h, -7d)"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get whale order statistics

    Returns counts and averages for whale orders
    """
    try:
        stats = await db.get_whale_statistics(symbol, period)

        if not stats:
            raise HTTPException(status_code=404, detail="No whale statistics available")

        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/active", response_model=List[dict])
async def get_active_whale_alerts(
    threshold: float = Query(100000, description="Alert threshold in USD"),
    max_distance: float = Query(1.0, description="Maximum % distance from mid-price"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get active whale alerts based on criteria

    Returns whale orders that are close to the mid-price and above threshold
    """
    try:
        # Get recent whales
        whales = await db.get_recent_whales(None, 100, threshold)

        # Filter by distance from mid
        alerts = []
        for whale in whales:
            if whale.get('distance_from_mid', 100) <= max_distance:
                alerts.append({
                    "alert_type": "whale_wall",
                    "symbol": whale.get('symbol'),
                    "side": whale.get('side'),
                    "price": whale.get('price'),
                    "value_usdt": whale.get('value_usdt'),
                    "distance_from_mid": whale.get('distance_from_mid'),
                    "timestamp": whale.get('timestamp'),
                    "severity": "high" if whale.get('value_usdt', 0) > 500000 else "medium"
                })

        return alerts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories/distribution", response_model=dict)
async def get_whale_distribution(
    symbol: Optional[str] = Query(None),
    period: str = Query("-24h"),
    db: InfluxDBService = Depends(get_db_service)
):
    """
    Get whale order distribution by value categories

    Categorizes whales as standard, large, huge, or mega based on value
    """
    try:
        whales = await db.get_recent_whales(symbol, 10000, 50000)

        # Categorize by value
        categories = {
            "standard": {"count": 0, "total_value": 0, "range": "$50K-$100K"},
            "large": {"count": 0, "total_value": 0, "range": "$100K-$500K"},
            "huge": {"count": 0, "total_value": 0, "range": "$500K-$1M"},
            "mega": {"count": 0, "total_value": 0, "range": ">$1M"}
        }

        for whale in whales:
            value = whale.get('value_usdt', 0)
            if value >= 1000000:
                cat = "mega"
            elif value >= 500000:
                cat = "huge"
            elif value >= 100000:
                cat = "large"
            else:
                cat = "standard"

            categories[cat]["count"] += 1
            categories[cat]["total_value"] += value

        # Calculate percentages
        total_count = sum(cat["count"] for cat in categories.values())
        total_value = sum(cat["total_value"] for cat in categories.values())

        for cat in categories.values():
            cat["count_percentage"] = (cat["count"] / total_count * 100) if total_count > 0 else 0
            cat["value_percentage"] = (cat["total_value"] / total_value * 100) if total_value > 0 else 0

        return {
            "period": period,
            "symbol": symbol,
            "total_whales": total_count,
            "total_value": total_value,
            "categories": categories
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))